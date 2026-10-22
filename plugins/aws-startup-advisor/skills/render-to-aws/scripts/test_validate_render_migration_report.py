"""Tests for the Render migration report validator."""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 - fixed local command, no shell
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("validate-render-migration-report.py")
SKILL_ROOT = Path(__file__).resolve().parents[1]
EXPECTED = SKILL_ROOT / "fixtures/expected"
GENERATED = EXPECTED / "generated"


def prepared(tmp_path: Path) -> tuple[Path, Path]:
    migration = tmp_path / "migration"
    shutil.copytree(GENERATED, migration)
    for name in ("aws-design.json", "estimation-infra.json"):
        shutil.copy2(EXPECTED / name, migration / name)
    return migration, migration / "migration-report.html"


def run(report: Path, migration: Path) -> tuple[int, str]:
    result = subprocess.run(  # nosec B603
        [sys.executable, str(SCRIPT), str(report), "--migration-dir", str(migration)],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def test_complete_report_passes_with_exact_status(tmp_path: Path) -> None:
    migration, report = prepared(tmp_path)
    code, output = run(report, migration)
    assert code == 0, output
    assert output == "REPORT_OK\n"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda text: text.replace("ECS on Fargate", "Amazon App Runner", 1), "TARGET_MAPPING_MISMATCH"),
        (lambda text: text.replace('<td data-cost-key="capacity_preserving">$352</td>', '<td data-cost-key="capacity_preserving">$999</td>'), "COST_CAPACITY_PRESERVING_MISMATCH"),
        (lambda text: text.replace('data-accounted-count="15"', 'data-accounted-count="14"'), "REPORT_ACCOUNTED_COUNT_MISMATCH"),
        (lambda text: text.replace("establish writer quiescence, apply", "establish pause writes, apply"), "CONTENT_CUTOVER_WRITER_QUIESCENCE"),
        (lambda text: text.replace("honor the source retention window", "honor the source hold window"), "CONTENT_ROLLBACK_SOURCE_RETENTION"),
        (lambda text: text.replace('scope="col"', "", 1), "ACCESSIBILITY"),
        (lambda text: text.replace("deferred_shared_ai_engine", "AI later"), "AI_DEFERRED_STATE_MISSING"),
        (lambda text: text.replace("draft for review", "final report"), "DRAFT_FOOTER_MISSING"),
        (lambda text: text.replace("</footer>", " contact user@example.com</footer>"), "PRIVACY_EMAIL"),
    ],
)
def test_report_mutations_fail_closed(tmp_path: Path, mutation, expected: str) -> None:
    migration, report = prepared(tmp_path)
    report.write_text(mutation(report.read_text(encoding="utf-8")), encoding="utf-8")
    code, output = run(report, migration)
    assert code == 1
    assert output.startswith("REPORT_FAIL |")
    assert expected in output


def test_ledger_duplicate_and_missing_warning_fail(tmp_path: Path) -> None:
    migration, report = prepared(tmp_path)
    ledger_path = migration / "generation-warnings.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["unsupported"].append(dict(ledger["generated"][0]))
    ledger["warnings"] = [row for row in ledger["warnings"] if row["code"] != "conditional_workflow_generation_unsupported"]
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    code, output = run(report, migration)
    assert code == 1
    assert "ACCOUNTING_DUPLICATE_SOURCE" in output
    assert "WORKFLOW_WARNING_MISSING" in output


def test_relative_report_path_is_rejected(tmp_path: Path) -> None:
    migration, _ = prepared(tmp_path)
    code, output = run(Path("migration-report.html"), migration)
    assert code == 1
    assert "PATHS_MUST_BE_ABSOLUTE" in output


def test_validator_is_skill_local() -> None:
    assert SCRIPT.is_file()
    assert SCRIPT.parent.name == "scripts"
    assert SCRIPT.parent.parent.name == "render-to-aws"
