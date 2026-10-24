from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "skills/shared/migration/bma-route-classifier.py"
GCP_COPY = ROOT / "skills/gcp-to-aws/scripts/bma-route-classifier.py"
BMA_COPY = ROOT / "skills/bedrock-migration-assessment/scripts/bma-route-classifier.py"
GCP_RUNTIME = ROOT / "skills/gcp-to-aws/references/runtime"
MANIFEST = GCP_RUNTIME / "bma-bootstrap-manifest.json"
PATTERNS = GCP_RUNTIME / "bma-input-patterns.json"


def classify(tmp_path: Path, filename: str, source: str) -> dict:
    project = tmp_path / filename.replace(".", "-")
    project.mkdir()
    (project / filename).write_text(source, encoding="utf-8")
    manifest_sha = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    proc = subprocess.run(
        [sys.executable, "-B", str(GCP_COPY), "classify",
         "--project-root", str(project),
         "--patterns", str(PATTERNS),
         "--bootstrap-manifest", str(MANIFEST),
         "--expected-bootstrap-manifest-sha256", manifest_sha,
         "--provider-intent", "none"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize(("source", "expected"), [
    ("from google.cloud import speech_v1\n", True),
    ("from google.cloud import documentai_v1\n", True),
    ("from google.cloud.speech_v1 import SpeechClient\n", True),
    ("import google.cloud.documentai_v1\n", True),
    ("from google.cloud import speech\n", True),
])
def test_versioned_google_ai_imports_are_candidates(tmp_path: Path, source: str, expected: bool) -> None:
    result = classify(tmp_path, "app.py", source)
    assert result["AI_CANDIDATE"] is expected
    assert result["ai_signal_files"] == ["app.py"]


@pytest.mark.parametrize("source", [
    "from google.cloud import storage\n",
    "from google.cloud import storage_v1\n",
    'print("rotate logs")\n',
])
def test_storage_and_plain_source_are_not_candidates(tmp_path: Path, source: str) -> None:
    result = classify(tmp_path, "app.py", source)
    assert result["AI_CANDIDATE"] is False


def test_bma_and_gcp_copies_match_canonical_classifier() -> None:
    canonical = CANONICAL.read_bytes()
    assert GCP_COPY.read_bytes() == canonical
    assert BMA_COPY.read_bytes() == canonical
