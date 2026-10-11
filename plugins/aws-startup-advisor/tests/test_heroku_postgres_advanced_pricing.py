"""Guard: Heroku Postgres Advanced tier pricing is modeled, not silently omitted.

Design: .agents/tasks/heroku-postgres-advanced-pricing/design.md

Heroku Postgres Advanced bills compute by the compute-month (not a flat
plan-name -> $/month lookup like every other row in
`heroku-pricing-cache.md`) and bills storage overage separately. Before this
change, an Advanced-tier `heroku-postgresql` addon had no row in the cache's
flat tables, so it fell through the pricing cache's rung-3 lookup, was marked
`"unpriced_heroku"`, and was silently excluded from the Heroku cost total —
materially wrong for a tier whose compute line alone runs $150-$900+/month
and whose storage overage can exceed the compute line for large,
storage-heavy clusters.

This is a documentation-contract check (string/shape assertions against the
markdown), matching the existing `test_cost_completeness.py` /
`test_decision_gate_wiring.py` pattern — this plugin's skill files are
instructions read by an LLM agent, not executable code, so there is no
runtime harness to exercise instead.
"""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

PRICING_CACHE = (
    PLUGIN_ROOT
    / "skills"
    / "heroku-to-aws"
    / "references"
    / "shared"
    / "heroku-pricing-cache.md"
)

COST_ENGINE = (
    PLUGIN_ROOT
    / "skills"
    / "heroku-to-aws"
    / "references"
    / "phases"
    / "estimate"
    / "estimate-cost-engine.md"
)

CAPTURE_MD = (
    PLUGIN_ROOT
    / "skills"
    / "heroku-to-aws"
    / "references"
    / "phases"
    / "discover"
    / "discover-live-capture.md"
)

DISCOVER_LIVE = (
    PLUGIN_ROOT
    / "skills"
    / "heroku-to-aws"
    / "references"
    / "phases"
    / "discover"
    / "discover-live.md"
)

SCHEMA_HEROKU = (
    PLUGIN_ROOT
    / "skills"
    / "heroku-to-aws"
    / "references"
    / "shared"
    / "schema-discover-heroku.md"
)

ADVANCED_LEVELS = [
    "4G-Performance",
    "8G-Performance",
    "16G-Performance",
    "32G-Performance",
    "64G-Performance",
    "128G-Performance",
    "256G-Performance",
    "384G-Performance",
    "512G-Performance",
    "768G-Performance",
    "1536G-Performance",
]

# Rates could not be confirmed from Heroku's static docs (JS-rendered
# Elements calculator) — these rows must be marked "unverified", not guessed.
UNVERIFIED_LEVELS = [
    "64G-Performance",
    "128G-Performance",
    "256G-Performance",
    "384G-Performance",
    "512G-Performance",
    "768G-Performance",
    "1536G-Performance",
]

# Confirmed rates (from Heroku's static docs) — must remain real numbers.
CONFIRMED_LEVEL_RATES = {
    "4G-Performance": "150",
    "8G-Performance": "300",
    "16G-Performance": "500",
    "32G-Performance": "900",
}


def test_pricing_cache_has_advanced_tier_heading() -> None:
    text = PRICING_CACHE.read_text(encoding="utf-8")
    assert "### Advanced Tier" in text


def test_pricing_cache_advanced_tier_lists_all_eleven_levels() -> None:
    text = PRICING_CACHE.read_text(encoding="utf-8")
    advanced_idx = text.index("### Advanced Tier")
    deprecated_idx = text.index("### Deprecated Plans")
    section = text[advanced_idx:deprecated_idx]
    for level in ADVANCED_LEVELS:
        assert level in section, f"Advanced Tier section missing level {level}"


def test_pricing_cache_advanced_tier_marks_unconfirmed_rates_unverified() -> None:
    text = PRICING_CACHE.read_text(encoding="utf-8")
    advanced_idx = text.index("### Advanced Tier")
    deprecated_idx = text.index("### Deprecated Plans")
    section = text[advanced_idx:deprecated_idx]
    assert section.count("unverified") >= len(UNVERIFIED_LEVELS), (
        "Expected one 'unverified' marker per unconfirmed Advanced Tier level"
    )
    for level, rate in CONFIRMED_LEVEL_RATES.items():
        # Confirmed levels must carry a real numeric rate, not "unverified".
        row_idx = section.index(level)
        row_line = section[row_idx: section.index("\n", row_idx)]
        assert "unverified" not in row_line, (
            f"{level} is a confirmed rate and must not be marked unverified"
        )
        assert rate in row_line, f"{level} row missing expected rate {rate}"


def test_pricing_cache_advanced_tier_states_storage_overage_rate() -> None:
    text = PRICING_CACHE.read_text(encoding="utf-8")
    assert "100 GB" in text
    assert "$0.20 per GB-month" in text


def test_pricing_cache_usage_rules_document_advanced_formula() -> None:
    text = PRICING_CACHE.read_text(encoding="utf-8")
    usage_rules_idx = text.index("## Usage Rules")
    rules = text[usage_rules_idx:]
    assert "compute-month" in rules
    assert "data_size_gb" in rules
    assert "unpriced_heroku" in rules


def test_pricing_cache_advanced_tier_documents_multi_pool_known_limitation() -> None:
    # Original design (§2.3, §3.4) required this gap be either resolved or
    # explicitly documented as a known limitation. It was NOT resolved in that
    # round (Discover's addon schema had no pool-count field at the time), so
    # the cache documented it as a known limitation and priced one instance
    # only. This PR's fix resolves the gap for LIVE discovery: Discover now
    # captures `data:pg:info` and populates `advanced_pools[]` with per-pool
    # level/instance_count/ha, so the formula sums `rate[level] × instance_count`
    # across every captured pool. The known-limitation note is now narrowed to
    # Terraform-only discovery (no live capture → no `advanced_pools` → cache
    # miss), not "every Advanced addon is under-priced".
    text = PRICING_CACHE.read_text(encoding="utf-8")
    advanced_idx = text.index("### Advanced Tier")
    deprecated_idx = text.index("### Deprecated Plans")
    section = text[advanced_idx:deprecated_idx]
    assert "Known limitation" in section
    assert "advanced_pools" in section
    assert "Terraform" in section
    assert "unpriced_heroku" in section

    usage_rules_idx = text.index("## Usage Rules")
    rules = text[usage_rules_idx:]
    assert "instance_count" in rules, (
        "Usage Rule 9 must reference the advanced_pools[].instance_count field "
        "now that Discover populates it from live data:pg:info captures"
    )
    assert "advanced_pools" in rules
    assert "rate[pool.level] × pool.instance_count" in rules or "rate[pool.level] x pool.instance_count" in rules


def test_pricing_cache_classic_tier_rows_untouched() -> None:
    # Guard against accidental edits to existing flat-lookup Classic rows.
    text = PRICING_CACHE.read_text(encoding="utf-8")
    assert "| standard-0 | 50      | 4 GB   | 64 GB   | 200         |" in text
    assert "| premium-0 | 200     | 4 GB   | 64 GB   | 200         |" in text
    assert "| private-0 | 200     | 4 GB   | 64 GB   | 200         |" in text
    assert "| shield-0 | 200     | 4 GB   | 64 GB   | 200         |" in text


def test_cost_engine_rung3_references_advanced_tier_formula() -> None:
    text = COST_ENGINE.read_text(encoding="utf-8")
    rung3_idx = text.index("3. **Heroku pricing cache**")
    rung4_idx = text.index("4. **User-provided**")
    rung3 = text[rung3_idx:rung4_idx]
    assert "Heroku Postgres Advanced" in rung3
    assert "data_size_gb" in rung3
    assert "baseline_note" in rung3
    assert "instance_count" in rung3, (
        "rung-3 must reference advanced_pools[].instance_count now that "
        "Discover populates it from live data:pg:info captures"
    )
    assert "advanced_pools" in rung3
    assert "Terraform" in rung3 and "unpriced_heroku" in rung3


def test_discover_live_capture_probes_both_postgres_tiers() -> None:
    text = CAPTURE_MD.read_text(encoding="utf-8")
    assert "heroku data:pg:info" in text
    assert "heroku pg:info" in text
    assert "pg-advanced-<app>.out" in text
    assert "pg-<app>.out" in text
    step3c_idx = text.index("3c. Per-command error handling")
    step3c = text[step3c_idx:]
    assert "skipped" in step3c
    assert "tier" in step3c.lower()


def test_discover_live_parses_advanced_pool_blocks() -> None:
    text = DISCOVER_LIVE.read_text(encoding="utf-8")
    assert "pg-advanced-<app>.out" in text
    assert "instances of" in text
    assert "(HA)" in text
    assert "advanced_pools" in text
    assert "tier" in text
    assert "pg-<app>.out" in text


def test_schema_documents_advanced_tier_fields() -> None:
    text = SCHEMA_HEROKU.read_text(encoding="utf-8")
    assert "tier" in text
    assert "advanced_pools" in text
    assert "instance_count" in text
    assert "leader" in text
    assert "follower" in text
