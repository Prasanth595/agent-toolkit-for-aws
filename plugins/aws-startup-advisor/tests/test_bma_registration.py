from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent


def names() -> list[str]:
    result = []
    for skill in (ROOT / "skills").glob("*/SKILL.md"):
        match = re.search(r"^name:\s*([^\n]+)$", skill.read_text(), re.MULTILINE)
        if match:
            result.append(match.group(1).strip())
    return sorted(result)


def test_public_identity_and_count() -> None:
    found = names()
    assert len(found) == 13
    assert found.count("bedrock-migration-assessment") == 1
    assert "ai-to-bedrock" not in found
    readme = (ROOT / "README.md").read_text()
    assert "thirteen skills" in readme and "Install all 13 skills" in readme
    assert "assesses and plans; `llm-to-bedrock` performs application source rewrites" in readme


def test_metadata_and_fixture_only_boundary() -> None:
    for path in (ROOT / ".claude-plugin/plugin.json", ROOT / ".cursor-plugin/plugin.json", REPO / ".claude-plugin/marketplace.json", REPO / ".cursor-plugin/marketplace.json"):
        json.loads(path.read_text())
    contracts = json.loads((ROOT / "scripts/artifact-contracts.json").read_text())
    assert "bedrock-migration-assessment" in contracts["skills"]
    assert contracts["shared"]["estimation-ai.json"]["fixture_only"] is True
    assert contracts["shared"]["generation-ai.json"]["fixture_only"] is True


def test_direct_runtime_is_source_neutral_and_gcp_behavior_is_mode_gated() -> None:
    bma = ROOT / "skills/bedrock-migration-assessment"
    skill = (bma / "SKILL.md").read_text()
    assert "Direct mode" in skill and "emits no telemetry" in skill
    app = (bma / "references/phases/discover/discover-app-code.md").read_text()
    preview = (bma / "references/phases/discover/discover-preview.md").read_text()
    design = (bma / "references/phases/design/design-ai.md").read_text()
    estimate = (bma / "references/phases/estimate/estimate-ai.md").read_text()
    generate = (bma / "references/phases/generate/generate-artifacts-ai.md").read_text()
    state = (bma / "references/shared/schema-phase-status.md").read_text()
    gates = (bma / "references/shared/handoff-gates.md").read_text()
    assert "Direct BMA MUST skip both sections" in app
    assert "Direct BMA MUST NOT read `gcp-resource-inventory.json`" in preview
    assert "Direct mode uses compliance" in design and "never infers a source cloud" in design
    assert "never describes an unknown source as GCP" in estimate
    assert "Never emit delegated branding in a direct artifact" in generate
    assert '"owning_skill": "BEDROCK_MIGRATION_ASSESSMENT"' in state
    assert "In direct mode, return after recording it—there is no telemetry reconciliation" in gates


def test_limitation_and_no_telemetry_runtime() -> None:
    skill = (ROOT / "skills/bedrock-migration-assessment/SKILL.md").read_text()
    assert "The equivalence harness carries its own copy of model-mapping, pricing, generated-file, and report-section rules." in skill
    assert "will NOT detect a future edit to the Markdown" in skill
    closure = json.loads((ROOT / "skills/bedrock-migration-assessment/references/runtime/closure.json").read_text())
    assert all("telemetry" not in entry["destination"] for entry in closure["entries"])
