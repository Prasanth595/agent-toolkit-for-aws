"""Review 5620455181 (vagmur-aws, PR #483 comment 4353203451).

Graviton app-code profiling is infrastructure work owned by gcp-to-aws. A delegated
GCP run must still yield `graviton_profile` entries with `source: "app_code"`, and
direct BMA must not gain any infrastructure/Graviton logic.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GCP = ROOT / "skills/gcp-to-aws/references"
BMA = ROOT / "skills/bedrock-migration-assessment"
CONTROLLER = GCP / "phases/discover/discover.md"
GRAVITON = GCP / "phases/discover/discover-app-graviton.md"
SHIM = GCP / "phases/discover/discover-app-code.md"
BMA_APP_CODE = BMA / "references/phases/discover/discover-app-code.md"


def _step_1b(text: str) -> str:
    start = text.index("**1b. Check for source code / dependency manifests:**")
    end = text.index("**1c. Check for billing data:**")
    return text[start:end]


def test_gcp_controller_loads_graviton_scan_for_any_source_and_shim_only_for_candidates() -> None:
    text = CONTROLLER.read_text()
    step = _step_1b(text)
    graviton_at = step.index("references/phases/discover/discover-app-graviton.md")
    shim_at = step.index("references/phases/discover/discover-app-code.md")
    assert graviton_at < shim_at
    assert "regardless of `AI_CANDIDATE`" in step
    shim_line = next(line for line in step.splitlines() if "discover-app-code.md" in line)
    assert "`AI_CANDIDATE: true`" in shim_line
    assert "`AI_CANDIDATE: false`" in step and "Do not load the shim" in step
    # Sub-discovery list and completion gate know about the GCP-owned file.
    assert "**discover-app-graviton.md**" in text
    assert "If `discover-app-graviton.md` ran" in text
    assert "If `discover-app-code.md` ran (`AI_CANDIDATE: true` only)" in text


def test_gcp_graviton_file_emits_app_code_profiles() -> None:
    text = GRAVITON.read_text()
    assert 'source: "app_code"' in text and "graviton_profile" in text
    assert "`references/shared/schema-graviton.md`" in text
    assert "`references/shared/graviton.md`" in text
    assert (GCP / "shared/schema-graviton.md").is_file() and (GCP / "shared/graviton.md").is_file()
    for rule in (
        'tier: "ready"', "risk signals", "`conditional`", 'tier: "incompatible"',
        "`import cuda`", "`torch.cuda`", 'route to G5/G6', "`Dockerfile`", "`FROM`",
    ):
        assert rule in text, rule
    assert re.search(r"^1\. .*language runtime", text, re.MULTILINE)
    assert re.search(r"^4\. .*Dockerfile", text, re.MULTILINE)
    assert "whether or not the run is an `AI_CANDIDATE`" in text
    assert "`bedrock-migration-assessment` never emits, modifies, or drops `graviton_profile`" in text
    # The shim points at the GCP owner and does not re-implement the scan.
    shim = SHIM.read_text()
    assert "discover-app-graviton.md" in shim and 'source: "app_code"' in shim
    assert "schema-graviton" not in shim and 'tier: "ready"' not in shim


def test_consumers_still_reference_app_code_profiles() -> None:
    iac = (GCP / "phases/discover/discover-iac.md").read_text()
    assert re.search(r'`source: "app_code"`.*app-code signals win', iac)
    compute = (GCP / "phases/clarify/clarify-compute.md").read_text()
    assert re.search(r"^\|.*no `app_code` profile.*\| \*\*Ask\*\* Q11b\s*\|", compute, re.MULTILINE)
    # The only emitter of app_code profiles in gcp-to-aws is the GCP-owned file.
    emitters = [
        path for path in (GCP / "phases").rglob("*.md")
        if "graviton_profile" in path.read_text() and 'source: "app_code"' in path.read_text()
        and re.search(r"Write a `graviton_profile` array", path.read_text())
    ]
    assert emitters == [GRAVITON]


def test_direct_bma_has_no_infrastructure_graviton_logic() -> None:
    text = BMA_APP_CODE.read_text()
    assert "Step 2.7" in text
    for token in ("schema-graviton", 'tier: "ready"', "machine_type", "torch.cuda", "node-gyp"):
        assert token not in text, token
    assert "do not emit, modify, or drop its `graviton_profile`" in text
    assert not list((BMA / "references/shared").glob("*graviton*"))
    assert not list(BMA.rglob("*graviton*"))
    closure = json.loads((BMA / "references/runtime/closure.json").read_text())
    assert not any("graviton" in entry["destination"] for entry in closure["entries"])
    # No BMA runtime file carries Graviton tier logic.
    for entry in closure["entries"]:
        member = (BMA / entry["destination"]).read_text(errors="ignore")
        assert 'tier: "ready"' not in member and "schema-graviton" not in member, entry["destination"]
