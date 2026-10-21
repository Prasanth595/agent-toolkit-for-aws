from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BMA = ROOT / "skills/bedrock-migration-assessment"
BUILDER = ROOT / "tools/build-bma-closure.py"


def test_exact_closed_runtime_manifest() -> None:
    value = json.loads((BMA / "references/runtime/closure.json").read_text())
    assert len(value["entries"]) == 65
    assert len({entry["destination"] for entry in value["entries"]}) == 65
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
    assert json.loads(preflight.stdout)["closure_entries"] == 65
