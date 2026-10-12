#!/usr/bin/env python3
"""Consent-disclosure drift lint for usage-API discovery sub-files.

Fails when a `discover-*-api.md` sub-file's Capture Endpoint Table calls a
non-`GET` HTTP method, but the file ALSO carries an unqualified "GET only"
style claim somewhere else that does not call out that method as an explicit
exception.

Why this exists: PR #436 added a read-only `POST /analytics/query` call to
`discover-openrouter-api.md` (both the gcp-to-aws and azure-to-aws copies).
The reviewer found the SAME contradiction reintroduced three separate times
in that one PR, in three different sections, over three review rounds:

  - Round 1: Step 0's consent text still said "This runs GET requests only."
  - Round 2 (after Step 0 was fixed): the Scope Boundary's FORBIDDEN bullet
    still banned "any non-GET method" with no exception.
  - Each fix only patched the one location flagged that round; the sibling
    location kept the stale blanket claim until the NEXT round caught it.

A consent promise that is accurate in one place and wrong in another is, from
the user's point of view, simply wrong: they read whichever one is in front
of them. This script makes the cost of adding a new non-GET capture endpoint
visible immediately — at authoring time, not three AI-review rounds later —
by checking every blanket GET-restriction claim in the file against what the
Capture Endpoint Table actually calls.

This is a textual contradiction check, not an HTTP conformance check: it does
not call any API. It reads two things out of each `discover-*-api.md` file:

  1. The real HTTP methods, from the Capture Endpoint Table (the "## Step 2:
     Capture" section): either a per-row `` `METHOD /path` `` cell, or the
     table's own "Endpoint (METHOD, ...)" header-column convention (the shape
     the Anthropic and Azure-OpenAI tables use, where every row lists only a
     path). If a table is present but neither shape is recognized, this is
     reported as a failure (an unrecognized table shape), never silently
     skipped as if the file were GET-only.
  2. Every blanket "GET only" / "non-GET" claim anywhere in the file (Security
     Contract, Step 0 consent copy, Scope Boundary FORBIDDEN bullets, or any
     other prose) via a fixed set of phrasings.

A claim is UNQUALIFIED (and so a failure) when the file has at least one
non-GET endpoint and that claim's own line contains neither "except" nor
"plus" alongside the actual method name. This matches the fix pattern PR #436
converged on in every location: "GET ... EXCEPT the one read-only POST
<endpoint>" / "GET requests against ... plus one read-only POST <endpoint>".

Stdlib only. Exit 0 = clean.

Modes (run from anywhere; paths resolve relative to this file):
    python3 plugins/aws-startup-advisor/scripts/consent-disclosure-audit.py
    python3 plugins/aws-startup-advisor/scripts/consent-disclosure-audit.py --plugin-root <dir>
        # check a copy of the plugin tree somewhere else (used by the tests)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# scripts/consent-disclosure-audit.py -> plugins/aws-startup-advisor/
DEFAULT_PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# Only usage-API discovery sub-files declare a Capture Endpoint Table and make
# a consent promise about which HTTP methods they call — scope the check to
# them, not every markdown file in the plugin.
TARGET_GLOB = "references/phases/discover/discover-*-api.md"

SELF = Path(__file__).resolve()

_HTTP_METHOD = r"GET|POST|PUT|PATCH|DELETE"

# A real call site: an HTTP verb immediately followed by a path or full URL,
# inside backticks or in the table's Endpoint column — e.g. `` `GET /credits` ``,
# `` `POST /analytics/query` ``, "All are `GET` against `https://...`". Scoped
# to the Step 2 Capture section below so Error Handling / Scope Boundary prose
# that merely DISCUSSES methods is never read as a call site.
_METHOD_CALL_RE = re.compile(
    rf"\b({_HTTP_METHOD})\b\s*(?:to that same base|against)?\s*[`/]"
)
# The table's OWN header-column convention when every row shares one method,
# written as a parenthesized qualifier on the "Endpoint" column header itself
# — e.g. "| # | Endpoint (GET, `https://api.openai.com`) | ..." or
# "Endpoint (GET)". Anchored to "Endpoint (" (not a bare word search) so it
# only ever reads the table's own declared method, never an unrelated verb
# mentioned anywhere else in the section — and so it has no length limit to
# evade: the real Anthropic/Azure-OpenAI tables put this 600-800+ characters
# after the words "Capture Endpoint Table", which a bounded slice would miss.
_METHOD_IN_HEADER_CELL_RE = re.compile(rf"Endpoint\s*\(\s*({_HTTP_METHOD})\b")

# A markdown table is present in this section: a header-separator row, e.g.
# "| - | --- | --- |" or "|---|---|". If this matches but no method was read
# by either pattern above, the table's shape wasn't recognized — that is a
# gap in this script, not a GET-only file, and must fail rather than skip.
_TABLE_PRESENT_RE = re.compile(r"^\s*\|[\s:-]+\|[\s:-]+\|", re.MULTILINE)

_STEP_HEADING_RE = re.compile(r"^##\s", re.MULTILINE)

# Phrasings that make a BLANKET (unqualified unless the same line carries an
# exception) claim that this flow calls GET only / never calls non-GET. Each
# is checked line-by-line so the exact offending line can be reported.
_BLANKET_CLAIM_PATTERNS = [
    re.compile(r"get requests? only", re.IGNORECASE),
    re.compile(r"\bget-only\b", re.IGNORECASE),
    re.compile(r"\bget only\b", re.IGNORECASE),
    re.compile(r"only call(?:s|ed)? get\b", re.IGNORECASE),
    re.compile(r"i only call get\b", re.IGNORECASE),
    re.compile(r"non-get (?:method|request)", re.IGNORECASE),
    re.compile(r"every row is `?get`?\b", re.IGNORECASE),
    re.compile(r"any other http method\b", re.IGNORECASE),
]

# A claim line is QUALIFIED (not a failure) when it names its own exception
# inline — the fix pattern PR #436 converged on in every location.
_EXCEPTION_MARKERS = ("except", "plus one", "plus a")


def _methods_in_capture_section(text: str) -> tuple[set[str], bool]:
    """Returns (real HTTP methods this file's Capture Endpoint Table calls,
    unrecognized_table) — `unrecognized_table` is True when Step 2 plainly
    contains a markdown table but neither method pattern read anything from
    it, meaning this script's table-shape coverage is incomplete for this
    file, not that the file is GET-only.

    Scoped to the "## Step 2: Capture" section (up to the next "## " heading)
    so a method named only in Error Handling, Security Contract prose, or the
    Scope Boundary's own FORBIDDEN list is never mistaken for a real call —
    those sections describe policy, not endpoints."""
    match = re.search(r"^##\s+Step 2:.*$", text, re.MULTILINE)
    if not match:
        return set(), False
    rest = text[match.end() :]
    end = _STEP_HEADING_RE.search(rest)
    section = rest[: end.start()] if end else rest

    methods: set[str] = set()

    # Per-row calls, e.g. `` `GET /credits` `` or `` `POST /analytics/query` ``.
    for line in section.splitlines():
        if "|" not in line and "`" not in line:
            continue
        for m in _METHOD_CALL_RE.finditer(line):
            methods.add(m.group(1))

    # The table's own "Endpoint (METHOD, ...)" header-column convention,
    # read anywhere in the section (no length-limited slice) — this is the
    # shape the real Anthropic and Azure-OpenAI tables use, with every row
    # listing only a path.
    for m in _METHOD_IN_HEADER_CELL_RE.finditer(section):
        methods.add(m.group(1))

    if methods:
        return methods, False

    # Nothing read. If the section has no markdown table at all, there is
    # genuinely nothing to extract (not every discovery sub-file necessarily
    # has one) — that is NOT an error.
    if not _TABLE_PRESENT_RE.search(section):
        return set(), False

    # A table IS present and neither pattern matched it: an unrecognized
    # table shape, not a GET-only file. Must not be treated the same as "no
    # non-GET method found" (which skips the file as clean) — report it so
    # the caller fails closed instead of silently passing an unchecked file.
    return set(), True


def _paragraphs_with_line_numbers(text: str) -> list[tuple[int, str]]:
    """Split into blank-line-delimited paragraphs, each tagged with its
    starting line number. A Markdown bullet that wraps across lines (common
    in this plugin's prose) is one paragraph, so an exception clause stated
    two sentences into the same bullet still counts as qualifying it — only a
    DIFFERENT paragraph repeating the claim with no exception is a failure."""
    paragraphs: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 1
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip() == "":
            if buf:
                paragraphs.append((start, "\n".join(buf)))
                buf = []
            continue
        if not buf:
            start = i
        buf.append(line)
    if buf:
        paragraphs.append((start, "\n".join(buf)))
    return paragraphs


def _unqualified_claims(text: str, non_get_methods: set[str]) -> list[tuple[int, str]]:
    """Every (line_number, offending_line) carrying a blanket GET-only claim
    with no inline exception, anywhere in its own paragraph, for the non-GET
    methods this file actually calls."""
    if not non_get_methods:
        return []
    failures: list[tuple[int, str]] = []
    for para_start, para in _paragraphs_with_line_numbers(text):
        lowered_para = para.lower()
        has_exception = any(marker in lowered_para for marker in _EXCEPTION_MARKERS) and any(
            method.lower() in lowered_para for method in non_get_methods
        )
        if has_exception:
            continue
        for offset, line in enumerate(para.splitlines()):
            if any(p.search(line) for p in _BLANKET_CLAIM_PATTERNS):
                failures.append((para_start + offset, line.strip()))
    return failures


def audit(plugin: Path) -> tuple[list[str], list[str], int]:
    """Return (setup errors, failures, files-checked count)."""
    files = sorted(plugin.glob(f"skills/*/{TARGET_GLOB}"))
    if not files:
        return (
            [
                f"consent-disclosure audit: found ZERO files matching "
                f"skills/*/{TARGET_GLOB} — the discovery sub-file layout may "
                f"have changed. Refusing to run a no-op gate."
            ],
            [],
            0,
        )

    failures: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(path.relative_to(plugin))

        real_methods, unrecognized_table = _methods_in_capture_section(text)
        if unrecognized_table:
            failures.append(
                f"{rel}: Step 2 contains a Capture Endpoint Table but no HTTP "
                f"method could be read from it (neither a per-row `METHOD "
                f"/path` cell nor an 'Endpoint (METHOD, ...)' header cell "
                f"matched) — fix the table shape, or this script's method "
                f"patterns, rather than letting this file pass unchecked"
            )
            continue

        non_get = real_methods - {"GET"}
        if not non_get:
            continue  # GET-only flow: no disclosure gap is even possible.

        for line_no, line in _unqualified_claims(text, non_get):
            failures.append(
                f"{rel}:{line_no}: claims a GET-only restriction, but the "
                f"Capture Endpoint Table calls {'/'.join(sorted(non_get))} too "
                f"— add an inline exception naming the method, or the "
                f"endpoint, to this line: {line!r}"
            )

    return [], failures, len(files)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--plugin-root",
        type=Path,
        default=DEFAULT_PLUGIN_ROOT,
        help="plugin directory to check (default: the plugin this script lives in)",
    )
    args = ap.parse_args()

    plugin = args.plugin_root.resolve()
    if not plugin.is_dir():
        print(f"Plugin directory not found: {plugin}", file=sys.stderr)
        return 2

    errors, failures, checked = audit(plugin)
    if errors:
        print(f"consent-disclosure audit: {len(errors)} setup problem(s)", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if failures:
        print(f"consent-disclosure audit: {len(failures)} problem(s)", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"consent-disclosure audit: OK ({checked} discovery sub-file(s) checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
