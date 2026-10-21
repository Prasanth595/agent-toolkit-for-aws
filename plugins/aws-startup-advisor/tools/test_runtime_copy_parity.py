from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_runtime_copies_are_current() -> None:
    result = subprocess.run([sys.executable, "tools/sync-runtime-copies.py", "--check"], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
