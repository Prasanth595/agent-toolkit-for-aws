from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BMA = ROOT / "skills/bedrock-migration-assessment"
BUILDER = ROOT / "tools/build-bma-closure.py"
GCP = ROOT / "skills/gcp-to-aws"
SHARED = ROOT / "skills/shared/migration"

# Review 5620455181 (vagmur-aws): selected_base must be a commit on main. Ancestry is
# proven with `git merge-base --is-ancestor <selected_base> upstream/main` outside the
# suite; this test pins that every copy of the value agrees so a re-baseline cannot drift.
SELECTED_BASE_JSON = [
    BMA / "references/runtime/closure.json",
    SHARED / "bma-bootstrap-manifest.json",
    GCP / "references/runtime/bma-bootstrap-manifest.json",
    SHARED / "bma-input-patterns.json",
    GCP / "references/runtime/bma-input-patterns.json",
    BMA / "references/runtime/bma-input-patterns.json",
    ROOT / "tools/runtime-copy-manifest.json",
    ROOT / "fixtures/bedrock-migration-assessment/semantic-trace-cases.json",
    ROOT / "fixtures/bedrock-migration-assessment/selected-base-semantic-projections.json",
]
SELECTED_BASE_SOURCE = [
    SHARED / "bma-route-classifier.py",
    GCP / "scripts/bma-route-classifier.py",
    BMA / "scripts/bma-route-classifier.py",
    ROOT / "tools/build-bma-closure.py",
    ROOT / "tools/sync-runtime-copies.py",
]


def test_exact_closed_runtime_manifest() -> None:
    value = json.loads((BMA / "references/runtime/closure.json").read_text())
    assert len(value["entries"]) == 66
    assert len({entry["destination"] for entry in value["entries"]}) == 66
    assert all(entry["origin"] in {"bma-native", "selected-base-source", "canonical-shared", "canonical-plugin"} for entry in value["entries"])
    assert all("telemetry" not in entry["destination"] and "billing" not in entry["destination"] for entry in value["entries"])
    assert all("source_path" not in entry for entry in value["entries"] if entry["origin"] == "bma-native")


def test_builder_check_and_isolated_copy(tmp_path: Path) -> None:
    completed = subprocess.run([sys.executable, str(BUILDER), "--check"], cwd=ROOT, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    value = json.loads((BMA / "references/runtime/closure.json").read_text())
    isolated = tmp_path / "bedrock-migration-assessment"
    for entry in value["entries"]:
        source = BMA / entry["destination"]; target = isolated / entry["destination"]
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
    closure = isolated / "references/runtime/closure.json"; closure.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BMA / "references/runtime/closure.json", closure)
    preflight = subprocess.run([sys.executable, "-B", str(isolated / "scripts/bma-route-classifier.py"), "preflight", "--bma-base", str(isolated)], text=True, capture_output=True)
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    assert json.loads(preflight.stdout)["closure_entries"] == 66


def test_selected_base_pins_agree_and_are_consistent() -> None:
    expected = json.loads((BMA / "references/runtime/closure.json").read_text())["selected_base"]
    assert re.fullmatch(r"[0-9a-f]{40}", expected), expected
    for path in SELECTED_BASE_JSON:
        assert json.loads(path.read_text())["selected_base"] == expected, path
    for path in SELECTED_BASE_SOURCE:
        pins = re.findall(r'^BASE = "([0-9a-f]{40})"$', path.read_text(), flags=re.MULTILINE)
        assert pins == [expected], (path, pins)
