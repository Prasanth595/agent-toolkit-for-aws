"""Regression guards for PR #369 (Astra model/API) behavior now owned by Bedrock Migration Assessment."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
BMA = SKILLS / "bedrock-migration-assessment/references"
GCP = SKILLS / "gcp-to-aws/references"
def text(relative: str) -> str:
    return (BMA / relative).read_text(encoding="utf-8")
def test_design_keeps_astra_api_quota_and_per_unit_contract() -> None:
    design = text("phases/design/design-ai.md")
    for needle in ("mantle_openai_chat", "mantle_openai_responses", "invocation_model_id", "runtime_openai_cris",
                   'required_client_api: "converse"', "Astra runtime (10× output burndown)",
                   "Unverified model/endpoint quota", "retain that unavailable comparison",
                   "per-model `required_client_api` selects the runtime API"):
        assert needle in design, needle
    # 483 source-neutral schema rows survive next to #369's migration_path row.
    assert "empty in direct runs without explicit source AI infrastructure evidence" in design
    assert "never infer a source cloud in direct mode" in design
def _roi_code(estimate: str) -> str:
    roi = estimate.split("## Part 5: ROI Analysis", 1)[1].split("## Part 6:", 1)[0]
    return re.search(r"```python\n(.*?)\n```", roi, re.S).group(1)
@pytest.mark.parametrize("source,target,expected", [(60, 60, 0), (60, 66, 10), (120, 60, -50), (0, 60, None)])
def test_estimate_roi_is_rate_derived(source, target, expected) -> None:
    namespace = {"source_monthly": source, "bedrock_monthly": target}
    exec(compile(_roi_code(text("phases/estimate/estimate-ai.md")), "ROI", "exec"), namespace)  # nosec B102 - committed formula
    assert namespace["percentage_difference"] == expected
    assert namespace["monthly_difference"] == target - source
def test_estimate_keeps_astra_tiers_and_no_fixed_premium() -> None:
    estimate = text("phases/estimate/estimate-ai.md")
    assert "Astra context and inference option" in estimate
    assert "272K" in estimate
    assert "computed Part 5 result, not a fixed premium" in estimate
    assert "mark the source comparison unavailable" in estimate
    assert "about 10% higher" not in estimate
    assert "Mode contract:" in estimate
    assert "Delegated GCP mode retains the selected-base" in estimate
def test_clarify_keeps_astra_same_model_row_and_direct_wording() -> None:
    clarify = text("phases/clarify/clarify-ai-only.md")
    assert "Astra" in clarify and "us-east-1" in clarify and "us-west-2" in clarify
    assert "Invocation wording contract" in clarify
def test_generate_keeps_chat_prefix_streaming_and_iam() -> None:
    generate = text("phases/generate/generate-ai.md")
    assert "mantle_openai_chat" in generate
    assert "Do not switch the recorded endpoint to obtain streaming" in generate
def test_generate_artifacts_keeps_astra_wire_contract() -> None:
    artifacts = text("phases/generate/generate-artifacts-ai.md")
    for needle in ("migrate_to_mantle.sh", "--target-only", "bedrock-mantle:CallWithBearerToken", "project/default",
                   "application-inference-profile", "do not emit or import a provider-adapter stub",
                   "openai>=2.45.0,<3", "/openai/v1",
                   "{direct: Bedrock Migration Assessment | delegated: GCP-to-AWS migration plugin}"):
        assert needle in artifacts, needle
@pytest.mark.parametrize("root", [BMA, GCP], ids=["bma", "gcp"])
def test_discover_preview_keeps_pro_source_choice(root: Path) -> None:
    preview = (root / "phases/discover/discover-preview.md").read_text(encoding="utf-8")
    assert "Pro sources need a choice" in preview
    assert "openai.gpt-6-astra" in preview and "openai.gpt-5.6-sol" in preview
    assert 'route = "ai_only"' in (BMA / "phases/discover/discover-preview.md").read_text(encoding="utf-8")
def test_openai_on_bedrock_facts_and_copy_parity() -> None:
    facts = text("shared/openai-on-bedrock.md")
    for needle in ("openai.gpt-6-astra", "us.openai.gpt-6-astra", "global.openai.gpt-6-astra", "1,050,000",
                   "128,000", "Astra does **not** support", "10x output-token burndown"):
        assert needle in facts, needle
    assert (BMA / "shared/openai-on-bedrock.md").read_bytes() == (GCP / "shared/openai-on-bedrock.md").read_bytes()
@pytest.mark.parametrize("name", ["ai-openai-to-bedrock.md", "ai-model-lifecycle.md",
                                  "ai-migration-guardrails.md", "bedrock-quotas.md"])
def test_vendored_ai_guides_match_canonical_and_keep_astra(name: str) -> None:
    canonical = (SKILLS / "shared/ai" / name).read_bytes()
    assert b"Astra" in canonical
    assert (BMA / "vendored/ai" / name).read_bytes() == canonical
def test_closure_hashes_cover_every_ported_file() -> None:
    closure = json.loads((BMA / "runtime/closure.json").read_text(encoding="utf-8"))
    entries = closure["entries"] if isinstance(closure, dict) else closure
    by_path = {entry["destination"]: entry["sha256"] for entry in entries}
    ported = ["phases/clarify/clarify-ai-only.md", "phases/design/design-ai.md", "phases/discover/discover-preview.md",
              "phases/estimate/estimate-ai.md", "phases/generate/generate-ai.md",
              "phases/generate/generate-artifacts-ai.md", "shared/openai-on-bedrock.md",
              *(f"vendored/ai/{n}" for n in ("ai-openai-to-bedrock.md", "ai-model-lifecycle.md",
                                              "ai-migration-guardrails.md", "bedrock-quotas.md"))]
    matched = 0
    for relative in ported:
        key = f"references/{relative}"
        assert key in by_path, key
        assert by_path[key] == hashlib.sha256((BMA / relative).read_bytes()).hexdigest(), key
        matched += 1
    assert matched == len(ported)
def test_gcp_estimate_controller_accepts_astra_chat_path() -> None:
    estimate = (GCP / "phases/estimate/estimate.md").read_text(encoding="utf-8")
    assert '"mantle_openai_chat"' in estimate
