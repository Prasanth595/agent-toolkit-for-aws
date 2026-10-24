"""BMA never imports, references the path of, or invokes the GCP boundary adapter or gcp-to-aws scripts."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BMA = ROOT / "skills/bedrock-migration-assessment"

# Imports, script paths, or invocations of the GCP side. Matched case-insensitively.
FORBIDDEN = re.compile(
    r"gcp[-_]ai[-_]profile[-_]adapter"
    r"|skills/gcp-to-aws/scripts"
    r"|gcp-to-aws/scripts"
    r"|\.\./gcp-to-aws"
    r"|(?:import|from)\s+[\w.]*gcp[-_]to[-_]aws",
    re.IGNORECASE,
)
GCP_IDENTITY = re.compile(r"gcp[-_]to[-_]aws", re.IGNORECASE)
# JSON data files (closure, manifests) record provenance of GCP-owned copies, so they are not scanned.
CODE_SUFFIXES = {".py", ".md", ".sh"}
# Known string identities that name the GCP owner or destination. They are labels, not invocations.
KNOWN_IDENTITY_LINES = {
    ("scripts/bma-runtime.py", 'GCP_OWNER = "gcp-to-aws"'),
    ("scripts/bma-route-classifier.py", 'if value["destination_identity"] != "gcp-to-aws":'),
    ("scripts/bma-runtime.py", 'OWNER_DELEGATED = "GCP_TO_AWS"'),
    ("scripts/emit-plan-json.py", '"GCP_TO_AWS": "GCP",'),
}


def _bma_files(suffixes: set[str]) -> list[Path]:
    return sorted(
        path for path in BMA.rglob("*")
        if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts
        and not path.name.startswith(".")
    )


def test_bma_has_no_import_path_or_invocation_of_gcp_side():
    hits = []
    for path in _bma_files(CODE_SUFFIXES):
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if FORBIDDEN.search(line):
                hits.append(f"{path.relative_to(BMA).as_posix()}:{number}: {line.strip()}")
    assert hits == []


def test_bma_gcp_identity_lines_in_scripts_are_known_labels_only():
    found = set()
    for path in _bma_files({".py"}):
        if "scripts" not in path.relative_to(BMA).parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if GCP_IDENTITY.search(line):
                found.add((path.relative_to(BMA).as_posix(), line.strip()))
    assert found == KNOWN_IDENTITY_LINES

