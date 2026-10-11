"""Guard: PR #436 review-round fixes for OpenRouter BYOK detection.

Four findings from PR #436's review (databaseIds 4240399949, 4240401481,
4240399951, 4240399955), fixed per
`.agents/tasks/pr436-openrouter-fix-round/plan.md`:

Finding 1 — the Step 3 `cost_provenance` join must key on `/activity`'s
`model_permaslug` field (the stable identifier Analytics' `model` dimension
actually returns), not `/activity`'s short `model` field, which only matches
when a model has never had more than one dated release. The fix rolls the
per-permaslug classification back up onto the existing short `model` id in
`usage_by_model[]` — the public-facing field never changes shape.

Finding 2 — the Scope Boundary section's FORBIDDEN bullet still said "any
non-GET method", contradicting the one permitted read-only
`POST /analytics/query` call the Security Contract and Step 0/2c already
exempt.

Finding 3 — cross-file orchestration gaps: (a) GCP's discover.md routed
`/activity: ok` straight to Step 3 without checking for a pending
Analytics-only retry; (b) Azure's re-entry check only looked at whether
`openrouter-usage-profile.json` existed, missing a mid-retry state with no
profile written yet; (c) a delayed retry of the Analytics row alone rebuilt
`time_range` from "now" instead of reusing the original capture's window,
desyncing it from the already-captured, time-frozen `/activity.json`.

Finding 4 — the `"mixed"` cost_provenance exclusion branch in
`llm-to-bedrock/SKILL.md` Step 1.5 dropped the undercount disclosure that
only the `"unknown"` branch carried forward — a regression, since a `"mixed"`
row's exclusion also discards real, independent OpenRouter-funded spend that
has no other home in the baseline.

These are documentation-contract checks (string/shape assertions against the
markdown), matching the existing `test_cost_completeness.py` /
`test_credential_lifecycle.py` pattern — this plugin's skill files are agent
instructions, not executable code, so there is no runtime harness to
exercise instead.
"""
from __future__ import annotations

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _normalize(text: str) -> str:
    """Collapse runs of whitespace (including newlines) to a single space, so
    assertions on multi-sentence phrases are robust to the markdown's hard
    line-wrapping."""
    return re.sub(r"\s+", " ", text)

OPENROUTER_DISCOVER_FILES = [
    PLUGIN_ROOT
    / "skills"
    / "gcp-to-aws"
    / "references"
    / "phases"
    / "discover"
    / "discover-openrouter-api.md",
    PLUGIN_ROOT
    / "skills"
    / "azure-to-aws"
    / "references"
    / "phases"
    / "discover"
    / "discover-openrouter-api.md",
]

GCP_DISCOVER_MD = (
    PLUGIN_ROOT
    / "skills"
    / "gcp-to-aws"
    / "references"
    / "phases"
    / "discover"
    / "discover.md"
)

AZURE_DISCOVER_MD = (
    PLUGIN_ROOT
    / "skills"
    / "azure-to-aws"
    / "references"
    / "phases"
    / "discover"
    / "discover.md"
)

SKILL_MD = PLUGIN_ROOT / "skills" / "llm-to-bedrock" / "SKILL.md"


# ---------------------------------------------------------------------------
# Finding 1 — join key is model_permaslug, not model
# ---------------------------------------------------------------------------


def test_cost_provenance_join_key_is_model_permaslug_not_model() -> None:
    for f in OPENROUTER_DISCOVER_FILES:
        text = f.read_text(encoding="utf-8")
        marker = "**`cost_provenance` — now derived from `/analytics/query`"
        assert marker in text, f"{f}: cost_provenance block marker missing"
        section_start = text.index(marker)
        # Scope to the classification block only (up to the write-profile step).
        section_end = text.index("Write `$MIGRATION_DIR/openrouter-usage-profile.json`")
        section = text[section_start:section_end]

        assert "join key is `/activity`'s `model_permaslug` field" in section, (
            f"{f}: Step 3 classification no longer documents joining on "
            f"/activity's model_permaslug field"
        )
        assert "not its `model`\n  field" in section or "not its `model` field" in section, (
            f"{f}: must explicitly rule out joining on /activity's model field"
        )
        assert "model_permaslug" in section
        # Must still roll the result back up to the short public model id used
        # by usage_by_model[] — do not let model_permaslug leak into the output.
        assert "usage_by_model[].model` stays in whatever short form it already uses" in section, (
            f"{f}: must document rolling the permaslug-keyed classification "
            f"back up onto the existing short model id"
        )
        assert "never leaks into the output" in section


def test_cost_provenance_handles_multiple_permaslugs_per_short_model() -> None:
    for f in OPENROUTER_DISCOVER_FILES:
        text = f.read_text(encoding="utf-8")
        marker = "**`cost_provenance` — now derived from `/analytics/query`"
        section_start = text.index(marker)
        section_end = text.index("Write `$MIGRATION_DIR/openrouter-usage-profile.json`")
        section = text[section_start:section_end]
        assert "multiple `model_permaslug` values" in section, (
            f"{f}: must document the differing-slug case (same short model id, "
            f"multiple permaslugs observed in the same window)"
        )
        assert "do not just take the last-seen permaslug" in section.lower(), (
            f"{f}: must rule out naively taking only the last-seen permaslug's "
            f"classification when a short model id has multiple permaslug rows"
        )


def test_openrouter_discover_copies_remain_mirrored_for_join_fix() -> None:
    gcp_text = OPENROUTER_DISCOVER_FILES[0].read_text(encoding="utf-8")
    azure_text = OPENROUTER_DISCOVER_FILES[1].read_text(encoding="utf-8")
    marker = "**`cost_provenance` — now derived from `/analytics/query`"
    assert marker in gcp_text and marker in azure_text
    gcp_block = gcp_text[gcp_text.index(marker):gcp_text.index(marker) + 3200]
    azure_block = azure_text[azure_text.index(marker):azure_text.index(marker) + 3200]
    assert gcp_block == azure_block, (
        "the Finding-1 join-key fix text has drifted between the gcp-to-aws "
        "and azure-to-aws discover-openrouter-api.md copies"
    )


def test_cost_provenance_join_fixture_openai_gpt41_classifies_mixed() -> None:
    """Reproduce the reviewer's own fixture: /activity's `model` and
    `model_permaslug` differ, and the OLD (model-keyed) join missed the
    match entirely, misclassifying the model `"unknown"` and losing its real
    cost_provenance signal. The fixed join (on model_permaslug) must match
    and classify it `"mixed"` ($10 byok_usage + $140 openrouter_usage, both
    over the $0.005 threshold), reproducing the review's "$50 vs $150"
    framing: /activity's own `usage` total for this model is $150, and a
    buggy join that fails to classify it loses that figure instead of
    allowing a downstream consumer to correctly include its $140
    independent portion.
    """
    activity_row = {
        "model": "openai/gpt-4.1",
        "model_permaslug": "openai/gpt-4.1-2025-04-14",
        "usage": 150.00,
    }
    analytics_map = {
        # Analytics' `model` dimension returns the permaslug form.
        "openai/gpt-4.1-2025-04-14": {"byok_usage": 10.00, "openrouter_usage": 140.00},
    }

    def classify(byok_usage: float, openrouter_usage: float) -> str:
        if byok_usage > 0.005 and openrouter_usage <= 0.005:
            return "byok_passthrough"
        if byok_usage > 0.005 and openrouter_usage > 0.005:
            return "mixed"
        if byok_usage <= 0.005 and openrouter_usage > 0.005:
            return "no_byok"
        return "unknown"

    # OLD (buggy) join: look up /activity's `model` field in the Analytics map.
    old_entry = analytics_map.get(activity_row["model"])
    old_classification = (
        classify(old_entry["byok_usage"], old_entry["openrouter_usage"])
        if old_entry is not None
        else "unknown"
    )
    assert old_classification == "unknown", (
        "sanity check: the old model-keyed join must fail to match this "
        "fixture (that is the bug being fixed)"
    )

    # FIXED join: look up /activity's `model_permaslug` field instead.
    new_entry = analytics_map.get(activity_row["model_permaslug"])
    assert new_entry is not None, "fixed join must find the permaslug-keyed row"
    new_classification = classify(new_entry["byok_usage"], new_entry["openrouter_usage"])
    assert new_classification == "mixed", (
        "fixed join must classify this fixture 'mixed' ($10 byok_usage + "
        "$140 openrouter_usage, both over threshold) — reproducing the "
        "reviewer's $50-vs-$150 scenario where the buggy join silently "
        "lost the real classification"
    )
    assert activity_row["usage"] == 150.00


# ---------------------------------------------------------------------------
# Finding 2 — Scope Boundary exempts the one read-only POST
# ---------------------------------------------------------------------------


def test_scope_boundary_exempts_post_analytics_query() -> None:
    for f in OPENROUTER_DISCOVER_FILES:
        text = f.read_text(encoding="utf-8")
        scope_idx = text.index("## Scope Boundary")
        scope_section = text[scope_idx:]
        assert "non-GET method" not in scope_section, (
            f"{f}: Scope Boundary still contains a blanket 'non-GET method' "
            f"claim with no /analytics/query exemption — contradicts the "
            f"Security Contract's permitted read-only POST"
        )
        assert "any HTTP method other than `GET`" in scope_section, (
            f"{f}: Scope Boundary's FORBIDDEN bullet must spell out GET-except "
            f"phrasing, matching the Security Contract's style"
        )
        assert "EXCEPT the one read-only `POST /analytics/query`" in scope_section, (
            f"{f}: Scope Boundary must explicitly exempt the one read-only "
            f"POST /analytics/query, matching the exact phrasing used "
            f"elsewhere in the file"
        )


def test_no_blanket_get_only_claim_without_analytics_exemption_anywhere() -> None:
    """Scan the ENTIRE file for a blanket GET-only / non-GET claim and confirm
    it is consistently qualified everywhere the POST exception applies, so a
    future edit can't reintroduce the Finding-2 contradiction."""
    for f in OPENROUTER_DISCOVER_FILES:
        text = f.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            if "non-get" in lowered or ("get only" in lowered and "except" not in lowered):
                assert "/analytics/query" in line or "analytics" in lowered, (
                    f"{f}: line {line_no} makes a blanket GET-only/non-GET "
                    f"claim without qualifying the /analytics/query POST "
                    f"exception: {line!r}"
                )


# ---------------------------------------------------------------------------
# Finding 3a — GCP's discover.md checks the Analytics entry before routing
# /activity: ok straight to Step 3
# ---------------------------------------------------------------------------


def test_gcp_discover_checks_analytics_entry_before_routing_activity_ok_to_step3() -> None:
    text = GCP_DISCOVER_MD.read_text(encoding="utf-8")
    idx = text.index("**1f. OpenRouter usage discovery")
    next_idx = text.index("**1g.")
    section = text[idx:next_idx]

    assert "/activity: ok` does NOT mean route straight to Step 3" in section, (
        "GCP discover.md 1f no longer documents that /activity: ok alone is "
        "insufficient to route to Step 3"
    )
    assert "/analytics/query` entry" in section
    assert '"failed"' in section
    assert "Step 2 retry path for the Analytics row only" in section, (
        "GCP discover.md 1f must invoke discover-openrouter-api.md's Step 2 "
        "Analytics-only retry path on a pending Analytics retry, not just "
        "describe the gap"
    )


# ---------------------------------------------------------------------------
# Finding 3b — Azure's discover.md re-entry check inspects the manifest, not
# just final-profile existence
# ---------------------------------------------------------------------------


def test_azure_discover_reentry_checks_manifest_not_just_profile_existence() -> None:
    text = AZURE_DISCOVER_MD.read_text(encoding="utf-8")
    idx = text.index("### OpenRouter usage-API consent + capture")
    next_idx = text.index("### Anthropic usage-API consent + capture")
    section = text[idx:next_idx]

    assert "openrouter-capture/manifest.json` FIRST" in section, (
        "Azure discover.md's OpenRouter re-entry check no longer checks the "
        "manifest first"
    )
    assert "No manifest" in section
    assert '`/analytics/query` entry `"failed"`' in section, (
        "Azure discover.md must distinguish a pending Analytics-only retry "
        "state from a fully-completed prior attempt"
    )
    assert "do NOT re-offer consent" in section
    assert "resume `discover-openrouter-api.md` from its Step 2 Analytics-only retry path" in _normalize(section)


def test_azure_discover_reentry_still_reoffers_consent_for_fully_completed_run() -> None:
    text = AZURE_DISCOVER_MD.read_text(encoding="utf-8")
    idx = text.index("### OpenRouter usage-API consent + capture")
    next_idx = text.index("### Anthropic usage-API consent + capture")
    section = text[idx:next_idx]
    assert "a prior attempt fully\n     completed" in section or "a prior attempt fully completed" in section, (
        "Azure discover.md must still re-offer Step 0 consent when a prior "
        "attempt already fully completed (not just when a retry is pending)"
    )


# ---------------------------------------------------------------------------
# Finding 3c — retry reuses the original capture's time_range window
# ---------------------------------------------------------------------------


def test_both_openrouter_discover_copies_reuse_original_capture_window_on_retry() -> None:
    for f in OPENROUTER_DISCOVER_FILES:
        text = f.read_text(encoding="utf-8")
        row4_idx = text.index("Row 4 `/analytics/query` sends this exact JSON body")
        table_notes_end = text.index("```json", row4_idx)
        row4_section = text[row4_idx:table_notes_end]

        assert "On the FIRST attempt (no retry" in row4_section, (
            f"{f}: Step 2c row 4 no longer distinguishes a first attempt from "
            f"a retry when building time_range"
        )
        assert "On a retry of this row alone" in _normalize(row4_section), (
            f"{f}: Step 2c row 4 must document reusing the original window on "
            f"a retry"
        )
        assert "manifest's existing top-level `captured_at` timestamp" in _normalize(row4_section), (
            f"{f}: retry path must reuse the manifest's captured_at, not "
            f"rebuild start/end from the current now"
        )

    # Step 2d's Analytics-retry bullet must also reference reusing captured_at.
    for f in OPENROUTER_DISCOVER_FILES:
        text = f.read_text(encoding="utf-8")
        idx = text.index('`/analytics/query` entry\'s `status` is `failed` → retry ONLY that row')
        bullet = text[idx:idx + 300]
        assert "reusing the manifest's original `captured_at`" in bullet, (
            f"{f}: Step 2d's /analytics/query retry bullet must document "
            f"reusing captured_at, not a fresh now-based timestamp"
        )


def test_openrouter_discover_copies_remain_mirrored_for_retry_window_fix() -> None:
    gcp_text = OPENROUTER_DISCOVER_FILES[0].read_text(encoding="utf-8")
    azure_text = OPENROUTER_DISCOVER_FILES[1].read_text(encoding="utf-8")
    marker = "Row 4 `/analytics/query` sends this exact JSON body"
    assert marker in gcp_text and marker in azure_text
    gcp_block = gcp_text[gcp_text.index(marker):gcp_text.index(marker) + 2200]
    azure_block = azure_text[azure_text.index(marker):azure_text.index(marker) + 2200]
    assert gcp_block == azure_block, (
        "the Finding-3c retry-window fix text has drifted between the "
        "gcp-to-aws and azure-to-aws discover-openrouter-api.md copies"
    )


# ---------------------------------------------------------------------------
# Finding 4 — mixed-row exclusion carries an undercount disclosure
# ---------------------------------------------------------------------------


def test_skill_md_mixed_exclusion_carries_undercount_disclosure() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    step15_idx = text.index("## Step 1.5")
    phase_a_idx = text.index("## Phase A")
    step15_section = text[step15_idx:phase_a_idx]

    mixed_idx = step15_section.index('row\'s `cost_provenance` is `"mixed"` →')
    byok_only_idx = step15_section.index('row\'s `cost_provenance` is `"byok_passthrough"` →')
    no_byok_idx = step15_section.index('row\'s `cost_provenance` is `"no_byok"` →')

    # The mixed bullet must be textually separate from byok_passthrough.
    assert byok_only_idx < mixed_idx < no_byok_idx

    mixed_bullet = step15_section[mixed_idx:no_byok_idx]
    assert "independent" in mixed_bullet
    assert "NOT reflected" in mixed_bullet or "undercount" in mixed_bullet.lower()
    assert "do NOT silently drop the independent portion" in mixed_bullet or \
        "do not silently drop the independent portion" in mixed_bullet.lower()
    assert "Do NOT attempt to estimate" in mixed_bullet, (
        "mixed-row disclosure must explicitly rule out estimating the "
        "independent portion's dollar/token split from the enum alone"
    )
    assert "savings" in mixed_bullet.lower(), (
        "mixed-row disclosure must rule out an unsupported savings claim, "
        "matching the honest-disclosure pattern of cost_unavailable/"
        "partial_window"
    )


def test_skill_md_byok_passthrough_bullet_has_no_mixed_language() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    step15_idx = text.index("## Step 1.5")
    phase_a_idx = text.index("## Phase A")
    step15_section = text[step15_idx:phase_a_idx]

    byok_only_idx = step15_section.index('row\'s `cost_provenance` is `"byok_passthrough"` →')
    mixed_idx = step15_section.index('row\'s `cost_provenance` is `"mixed"` →')
    byok_bullet = step15_section[byok_only_idx:mixed_idx]

    assert "independent" not in byok_bullet, (
        "byok_passthrough-only bullet must not claim an undercount "
        "disclosure is needed — a pure byok_passthrough row has no "
        "independent portion to lose"
    )
    assert "No further disclosure needed" in _normalize(byok_bullet)
