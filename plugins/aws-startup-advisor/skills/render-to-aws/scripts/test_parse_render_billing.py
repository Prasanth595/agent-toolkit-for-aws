from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "parse-render-billing.py"
FIXTURES = SCRIPT_DIR.parent / "fixtures/render-billing"
SCHEMA = SCRIPT_DIR.parent / "references/shared/schema-render-billing.json"
spec = importlib.util.spec_from_file_location("parse_render_billing", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_user_stated_and_csv_aggregate_are_closed_and_deterministic() -> None:
    stated_data = (FIXTURES / "user-stated.json").read_bytes()
    stated = module.parse(stated_data, ".json")
    assert stated["monthly_total"] == "123.45"
    export_data = (FIXTURES / "export.csv").read_bytes()
    first = module.parse(export_data, ".csv")
    second = module.parse(export_data, ".csv")
    assert first == second
    assert first["monthly_total"] == "56.56"
    assert first["line_item_count"] == 2
    assert "service_id" not in json.dumps(first)
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator(schema).validate(stated)
    Draft202012Validator(schema).validate(first)


def test_unknown_headers_and_properties_reject_before_rows() -> None:
    with pytest.raises(module.BillingError, match="csv_header_invalid"):
        module.parse(b"service_id,amount,secret\nsrv,1,nope\n", ".csv")
    document = {"schema_version": "1.0.0", "source": "user_stated", "monthly_amount": "1.00", "currency": "USD", "as_of": "2026-10-21", "raw_rows": []}
    with pytest.raises(module.BillingError, match="properties_invalid"):
        module.parse(json.dumps(document).encode(), ".json")


def test_decimal_dates_overlap_and_currency_fail_closed() -> None:
    base = {"schema_version": "1.0.0", "lines": [
        {"line_id": "line-1", "service_id": "srv-safe", "period_start": "2026-09-01", "period_end": "2026-10-01", "amount": "10.00", "currency": "USD", "amount_basis": "subtotal_before_tax"},
        {"line_id": "line-2", "service_id": "srv-safe", "period_start": "2026-09-15", "period_end": "2026-10-15", "amount": "10.00", "currency": "USD", "amount_basis": "subtotal_before_tax"},
    ]}
    with pytest.raises(module.BillingError, match="overlapping_period"):
        module.parse(json.dumps(base).encode(), ".json")
    base["lines"][1]["service_id"] = "srv-other"
    base["lines"][1]["currency"] = "EUR"
    with pytest.raises(module.BillingError, match="mixed_currency_without_conversion"):
        module.parse(json.dumps(base).encode(), ".json")
    base["target_currency"] = "USD"
    base["conversions"] = [{"from": "EUR", "to": "USD", "rate": "1.10", "as_of": "2026-10-21"}]
    result = module.parse(json.dumps(base).encode(), ".json")
    assert result["monthly_total"] == "21.31"


def test_negative_exponent_nan_and_bad_dates_reject() -> None:
    for amount in ("-1.00", "1e3", "NaN", "Infinity"):
        document = {"schema_version": "1.0.0", "source": "user_stated", "monthly_amount": amount, "currency": "USD", "as_of": "2026-10-21"}
        with pytest.raises(module.BillingError, match="amount_invalid"):
            module.parse(json.dumps(document).encode(), ".json")
    bad_date = {"schema_version": "1.0.0", "source": "user_stated", "monthly_amount": "1.00", "currency": "USD", "as_of": "2026-02-30"}
    with pytest.raises(module.BillingError, match="as_of_invalid"):
        module.parse(json.dumps(bad_date).encode(), ".json")


def test_json_input_version_is_exact_and_output_version_is_independent() -> None:
    document = {
        "schema_version": "1.0.0",
        "lines": [{
            "line_id": "line-1",
            "period_start": "2026-09-01",
            "period_end": "2026-10-01",
            "currency": "USD",
            "amount": "10.00",
            "amount_basis": "subtotal_before_tax",
        }],
    }
    assert module.parse(json.dumps(document).encode(), ".json")["schema_version"] == "1.0"
    document["schema_version"] = "1.0"
    with pytest.raises(module.BillingError, match="schema_version_invalid"):
        module.parse(json.dumps(document).encode(), ".json")
