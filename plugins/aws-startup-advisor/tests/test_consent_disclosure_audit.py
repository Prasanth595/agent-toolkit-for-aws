"""Tests for `scripts/consent-disclosure-audit.py`.

Builds throwaway `discover-*-api.md` fixtures under a scratch plugin tree so
the committed skill files are never edited by the test run itself. Each test
constructs a minimal file with just the two sections the script reads: a
"## Step 2: Capture" section containing a Capture Endpoint Table, and a
blanket GET-only claim somewhere else in the file.

Run: ``uv run --with pytest python -m pytest plugins/aws-startup-advisor/tests/test_consent_disclosure_audit.py``
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PLUGIN_ROOT / "scripts" / "consent-disclosure-audit.py"
TARGET_REL = "skills/example-skill/references/phases/discover/discover-example-api.md"


def _load():
    spec = importlib.util.spec_from_file_location("consent_disclosure_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _run(plugin_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--plugin-root", str(plugin_root)],
        capture_output=True,
        text=True,
    )


def _write_fixture(tmp_path: Path, text: str) -> Path:
    root = tmp_path / "plugin"
    path = root / TARGET_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return root


# A minimal GET-only file: Step 0 claims GET-only, the table is all GET.
_GET_ONLY_FILE = """\
# Discover Phase: Example Usage API Discovery

## Security Contract (applies to every step)

1. Exact-endpoint allowlist, GET only. Call ONLY the endpoints below.

## Step 0: Consent Gate

This runs GET requests only, against a fixed list of usage endpoints.

## Step 2: Capture

**2c. Capture Endpoint Table.** Every row is `GET` against
`https://example.com/api/v1`.

| # | Endpoint (GET) | Purpose | Output file |
| - | -------------- | ------- | ------------ |
| 1 | `/usage`       | usage   | usage.json   |

## Scope Boundary

- Any non-GET method is forbidden.
"""

# Same file, but a POST row was added to the table and NO claim was updated —
# the exact shape of PR #436's round-1 bug, reproduced across all three
# sections it occurred in (Step 0, the table lead-in, Scope Boundary).
_UNQUALIFIED_POST_FILE = _GET_ONLY_FILE.replace(
    "| 1 | `/usage`       | usage   | usage.json   |",
    "| 1 | `/usage`       | usage   | usage.json   |\n"
    "| 2 | `POST /analytics/query` | per-model split | analytics.json |",
)

# The same POST addition, but every blanket claim was updated with an inline
# exception naming the method — the fix shape PR #436 converged on.
_QUALIFIED_POST_FILE = """\
# Discover Phase: Example Usage API Discovery

## Security Contract (applies to every step)

1. Exact-endpoint allowlist, GET + one scoped POST. All are `GET` EXCEPT
   `POST /analytics/query`, a read-only aggregate query.

## Step 0: Consent Gate

This runs GET requests against a fixed list of usage endpoints, plus one
read-only POST to /analytics/query for an aggregate split.

## Step 2: Capture

**2c. Capture Endpoint Table.** Row 1 is `GET` against
`https://example.com/api/v1`. Row 2 is `POST` to that same base, read-only.

| # | Endpoint                | Purpose          | Output file      |
| - | ------------------------ | ---------------- | ----------------- |
| 1 | `GET /usage`             | usage            | usage.json        |
| 2 | `POST /analytics/query`  | per-model split  | analytics.json    |

## Scope Boundary

- Any HTTP method other than GET EXCEPT the one read-only POST
  /analytics/query aggregate query is forbidden.
"""


def test_clean_get_only_file_passes(tmp_path: Path) -> None:
    root = _write_fixture(tmp_path, _GET_ONLY_FILE)
    result = _run(root)
    assert result.returncode == 0, result.stderr
    assert "consent-disclosure audit: OK" in result.stdout


def test_unqualified_post_claim_fails_in_every_section(tmp_path: Path) -> None:
    """Reproduces PR #436 round 1: a POST row with no exception anywhere.
    All three historically-affected sections (Security Contract lead-in via
    Step 0's consent text, the table's own lead-in, and Scope Boundary) must
    each be reported — not just the first one found."""
    root = _write_fixture(tmp_path, _UNQUALIFIED_POST_FILE)
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "GET requests only" in result.stderr
    assert "Every row is `GET`" in result.stderr or "Every row is" in result.stderr
    assert "non-GET method" in result.stderr
    assert TARGET_REL in result.stderr


def test_qualified_post_claim_passes(tmp_path: Path) -> None:
    """The fix shape PR #436 converged on: every blanket claim rewritten with
    an inline exception naming the actual non-GET method/endpoint."""
    root = _write_fixture(tmp_path, _QUALIFIED_POST_FILE)
    result = _run(root)
    assert result.returncode == 0, result.stderr


def test_exception_naming_the_wrong_method_still_fails(tmp_path: Path) -> None:
    """An 'except' clause that doesn't name one of the file's actual non-GET
    methods must not silence a real gap (e.g. a stale exception left over
    from a different, now-removed endpoint)."""
    text = _GET_ONLY_FILE.replace(
        "This runs GET requests only, against a fixed list of usage endpoints.",
        "This runs GET requests only, against a fixed list of usage "
        "endpoints, except for an unrelated PATCH on a retired endpoint.",
    )
    text = text.replace(
        "| 1 | `/usage`       | usage   | usage.json   |",
        "| 1 | `/usage`       | usage   | usage.json   |\n"
        "| 2 | `POST /analytics/query` | per-model split | analytics.json |",
    )
    root = _write_fixture(tmp_path, text)
    result = _run(root)
    assert result.returncode == 1, result.stdout
    assert "the Capture Endpoint Table calls POST too" in result.stderr


def test_scope_outside_the_discover_api_file_pattern_is_ignored(tmp_path: Path) -> None:
    """A SKILL.md or any other file describing HTTP methods is out of scope
    — only discover-*-api.md sub-files make a consent promise this script
    checks."""
    root = tmp_path / "plugin"
    other = root / "skills" / "example-skill" / "SKILL.md"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text(
        "This flow runs GET requests only.\n\n"
        "| 1 | `POST /x` | y | z.json |\n",
        encoding="utf-8",
    )
    (
        root / "skills" / "example-skill" / "references" / "phases" / "discover"
    ).mkdir(parents=True, exist_ok=True)
    target = (
        root
        / "skills"
        / "example-skill"
        / "references"
        / "phases"
        / "discover"
        / "discover-example-api.md"
    )
    target.write_text(_GET_ONLY_FILE, encoding="utf-8")
    result = _run(root)
    assert result.returncode == 0, result.stderr


def test_no_matching_files_is_a_setup_error_not_a_silent_pass(tmp_path: Path) -> None:
    root = tmp_path / "plugin"
    (root / "skills").mkdir(parents=True)
    result = _run(root)
    assert result.returncode == 1
    assert "found ZERO files" in result.stderr


def test_methods_in_capture_section_reads_table_rows() -> None:
    mod = _load()
    methods = mod._methods_in_capture_section(_UNQUALIFIED_POST_FILE)
    assert methods == {"GET", "POST"}


def test_methods_in_capture_section_ignores_scope_boundary_mentions() -> None:
    """A method named only in Scope Boundary/Error Handling prose (never in
    the Capture Endpoint Table itself) must not be read as a real call."""
    mod = _load()
    text = _GET_ONLY_FILE  # Scope Boundary mentions "non-GET" but never POST.
    methods = mod._methods_in_capture_section(text)
    assert methods == {"GET"}


def test_real_plugin_discovery_files_pass_on_main() -> None:
    """Smoke test against the actual committed discover-*-api.md files (not
    a scratch fixture) — this is the gate's real-world assertion: whatever
    ships in this plugin today must already be internally consistent."""
    result = _run(PLUGIN_ROOT)
    assert result.returncode == 0, result.stderr
    assert "consent-disclosure audit: OK" in result.stdout
