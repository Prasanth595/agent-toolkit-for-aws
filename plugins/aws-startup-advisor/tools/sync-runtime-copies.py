#!/usr/bin/env python3
"""Generate and verify the BMA bootstrap runtime copies."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tools/runtime-copy-manifest.json"
BASE = "4a51ac3f086499dcd1e1154992109e77f0bebaa6"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_bootstrap() -> bytes:
    classifier = ROOT / "skills/shared/migration/bma-route-classifier.py"
    patterns = ROOT / "skills/shared/migration/bma-input-patterns.json"
    closure = ROOT / "skills/bedrock-migration-assessment/references/runtime/closure.json"
    value = {
        "classifier": {"path": "scripts/bma-route-classifier.py", "sha256": sha(classifier)},
        "closure": {"path": "references/runtime/closure.json", "sha256": sha(closure)},
        "compatibility": {"classifier_schema": 1, "patterns_schema": 1, "closure_schema": 1},
        "destination_identity": "gcp-to-aws",
        "patterns": {"path": "references/runtime/bma-input-patterns.json", "sha256": sha(patterns)},
        "schema_version": 1,
        "selected_base": BASE,
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    value["self_hash"] = hashlib.sha256(canonical).hexdigest()
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if set(config) != {"schema_version", "selected_base", "copies"} or config["selected_base"] != BASE:
        print("FAIL — runtime copy manifest schema")
        return 1
    bootstrap = ROOT / "skills/shared/migration/bma-bootstrap-manifest.json"
    expected_bootstrap = build_bootstrap()
    failures = []
    if args.check:
        if not bootstrap.is_file() or bootstrap.read_bytes() != expected_bootstrap:
            failures.append("canonical bootstrap manifest is stale")
    else:
        bootstrap.parent.mkdir(parents=True, exist_ok=True)
        bootstrap.write_bytes(expected_bootstrap)
    for row in config["copies"]:
        canonical = ROOT / row["canonical"]
        if not canonical.is_file() or canonical.is_symlink():
            failures.append(f"missing canonical {row['canonical']}")
            continue
        expected_mode = int(row["mode"], 8)
        if not args.check:
            os.chmod(canonical, expected_mode)
        for destination_name in row["destinations"]:
            destination = ROOT / destination_name
            if args.check:
                if not destination.is_file() or destination.is_symlink() or destination.read_bytes() != canonical.read_bytes():
                    failures.append(f"copy drift: {destination_name}")
                elif destination.stat().st_mode & 0o777 != expected_mode:
                    failures.append(f"mode drift: {destination_name}")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(canonical, destination)
                os.chmod(destination, expected_mode)
    if failures:
        print("FAIL — " + "; ".join(failures))
        return 1
    print(f"PASS — runtime copies exact; bootstrap_sha256={sha(bootstrap)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
