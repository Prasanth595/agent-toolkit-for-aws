#!/usr/bin/env python3
"""Read-only route classification and authoritative BMA closure preflight.

AI_CANDIDATE requires AI evidence: an AI signal in source or manifest files
(provider SDK import/dependency, AI endpoint host, provider env var name, or
model identifier from ``ai_signals`` in the patterns file), explicit provider
intent, Vertex-strong IaC, or a durable AI route. Source presence alone
(``SOURCE_CONTAINING``) is informational and never makes a run a candidate.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

BASE = "9ab50636d12510dc351ff02fd7966efa4dba4341"
SCHEMA = 1
DESTINATION_ROOT = "skills/bedrock-migration-assessment"
BMA_OWNER = "bedrock-migration-assessment"
PATTERN_KEYS = {
    "schema_version", "selected_base", "terraform", "module_directories",
    "source", "manifest", "billing", "exclude_roots", "secret_excludes",
    "vertex_strong_tokens", "ai_signals",
}
AI_SIGNAL_FAMILIES = {"imports", "dependencies", "endpoints", "env_vars", "model_prefixes"}
# Families scanned per inventory category. Dependencies are manifest-only so a bare
# package name such as ``openai`` in prose cannot flag a source file.
AI_SIGNAL_SCOPE = {
    "source": ("imports", "endpoints", "env_vars", "model_prefixes"),
    "manifest": ("dependencies", "endpoints", "env_vars", "model_prefixes"),
}
CLOSURE_KEYS = {
    "schema_version", "selected_base", "destination_root", "entrypoints",
    "entries", "runtime_exclusions", "self_hash",
}
ENTRY_KEYS = {
    "logical_id", "origin", "destination", "type", "sha256",
    "canonical_owner", "parity", "runtime_references",
}
ENTRYPOINTS = [
    "SKILL.md", "scripts/bma-runtime.py", "scripts/emit-plan-json.py",
    "scripts/validate-migration-report.py",
    "scripts/validate-startup-program-artifacts.py",
    "references/phases/discover/discover.md",
    "references/phases/clarify/clarify.md",
    "references/phases/design/design.md",
    "references/phases/estimate/estimate.md",
    "references/phases/generate/generate.md",
    "references/assemblers/decision-report.md",
    "references/assemblers/migration-docs.md",
    "references/assemblers/migration-report.md",
]
RUNTIME_EXCLUSIONS = [
    "telemetry/**", "references/phases/**/*infra*",
    "references/phases/**/*billing*", "fixtures/**", "tests/**",
    "scripts/contracts/estimation-ai.schema.json",
    "scripts/contracts/generation-ai.schema.json",
]
ORIGINS = {"bma-native", "selected-base-source", "canonical-shared", "canonical-plugin"}
PARITY = {
    "bma-native": "native", "selected-base-source": "adapted",
    "canonical-shared": "byte-identical", "canonical-plugin": "byte-identical",
}
TYPES = {"instruction", "script", "data"}
TOKEN = re.compile(r"`((?:scripts|references)/[A-Za-z0-9_.\-/]+\.(?:md|json|py))`")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(data: bytes) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique)


def matches(path: Path, pattern: str, directory: bool = False) -> bool:
    value = path.as_posix() + ("/" if directory else "")
    return fnmatch.fnmatchcase(value, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(value, pattern[3:])
    )


def audit(events: list[dict[str, str]], operation: str, path: Path) -> None:
    events.append({"op": operation, "path": str(path.resolve(strict=False))})


def regular(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def directory(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def checked_root(path: Path, reason: str) -> Path:
    if not directory(path):
        raise ValueError(f"{reason}_invalid")
    return path.resolve()


def safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and "." not in path.parts and ".." not in path.parts and path.as_posix() == value


def bootstrap(script: Path, patterns: Path, manifest: Path, expected: str,
              events: list[dict[str, str]]) -> tuple[dict[str, Any], str]:
    for path in (script, patterns, manifest):
        audit(events, "lstat", path)
        if not regular(path):
            raise ValueError("bootstrap_material_missing")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("bootstrap_manifest_hash_malformed")
    audit(events, "read", manifest)
    raw = manifest.read_bytes()
    if digest(raw) != expected:
        raise ValueError("bootstrap_manifest_hash_mismatch")
    value = load_json(raw)
    required = {
        "schema_version", "selected_base", "classifier", "patterns", "closure",
        "destination_identity", "compatibility", "self_hash",
    }
    if set(value) != required:
        raise ValueError("bootstrap_manifest_schema_invalid")
    if value["schema_version"] != SCHEMA or value["selected_base"] != BASE:
        raise ValueError("bootstrap_manifest_version_invalid")
    if value["destination_identity"] != "gcp-to-aws":
        raise ValueError("bootstrap_manifest_destination_invalid")
    if value["compatibility"] != {"classifier_schema": 1, "patterns_schema": 1, "closure_schema": 1}:
        raise ValueError("bootstrap_manifest_compatibility_invalid")
    unsigned = dict(value)
    claimed = unsigned.pop("self_hash")
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    if not isinstance(claimed, str) or digest(canonical) != claimed:
        raise ValueError("bootstrap_manifest_self_hash_mismatch")
    expected_paths = {
        "classifier": "scripts/bma-route-classifier.py",
        "patterns": "references/runtime/bma-input-patterns.json",
        "closure": "references/runtime/closure.json",
    }
    for key, relative in expected_paths.items():
        row = value.get(key)
        if set(row or {}) != {"path", "sha256"} or row["path"] != relative or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ValueError("bootstrap_manifest_path_invalid")
    base = script.parent.parent
    if patterns.resolve() != (base / expected_paths["patterns"]).resolve():
        raise ValueError("bootstrap_manifest_path_invalid")
    if manifest.resolve() != (base / "references/runtime/bma-bootstrap-manifest.json").resolve():
        raise ValueError("bootstrap_manifest_path_invalid")
    audit(events, "read", script)
    audit(events, "read", patterns)
    if digest(script.read_bytes()) != value["classifier"]["sha256"]:
        raise ValueError("bootstrap_classifier_hash_mismatch")
    pattern_bytes = patterns.read_bytes()
    if digest(pattern_bytes) != value["patterns"]["sha256"]:
        raise ValueError("bootstrap_pattern_hash_mismatch")
    config = load_json(pattern_bytes)
    if set(config) != PATTERN_KEYS or config["schema_version"] != SCHEMA or config["selected_base"] != BASE:
        raise ValueError("pattern_schema_invalid")
    for key in PATTERN_KEYS - {"schema_version", "selected_base", "ai_signals"}:
        if not token_list(config[key]):
            raise ValueError("pattern_schema_invalid")
    signals = config["ai_signals"]
    if not isinstance(signals, dict) or set(signals) != AI_SIGNAL_FAMILIES or not all(token_list(signals[family]) for family in AI_SIGNAL_FAMILIES):
        raise ValueError("pattern_schema_invalid")
    return config, value["closure"]["sha256"]


def token_list(value: Any) -> bool:
    return (isinstance(value, list) and bool(value) and len(value) == len(set(value))
            and all(isinstance(item, str) and item for item in value))


def signal_patterns(signals: dict[str, list[str]]) -> dict[str, re.Pattern[bytes]]:
    """Compile one bytes regex per family; tokens must start at a word-ish boundary."""
    boundary = rb"(?<![A-Za-z0-9_.\-@])"
    end = rb"(?![A-Za-z0-9_])"
    compiled = {}
    for family, tokens in signals.items():
        alternatives = []
        for token in tokens:
            escaped = re.escape(token.encode())
            if family == "imports":
                alternatives.append(rb"(?:^|[\s;])(?:import|from)\s+" + escaped + end)
                alternatives.append(rb"(?:from\s+|require\(\s*|import\(\s*)[\"']" + escaped + end)
                if "/" in token:
                    alternatives.append(rb"[\"']" + escaped + end)
            elif family == "model_prefixes":
                alternatives.append(boundary + escaped)
            else:
                alternatives.append(boundary + escaped + end)
        compiled[family] = re.compile(b"|".join(alternatives), re.MULTILINE)
    return compiled


def provider_intent(value: str) -> bool:
    if not value:
        raise ValueError("provider_intent_invalid")
    parts = value.split(",")
    allowed = {"none", "openai", "anthropic", "openrouter"}
    if any(part not in allowed for part in parts) or parts != sorted(set(parts)):
        raise ValueError("provider_intent_invalid")
    if "none" in parts and len(parts) != 1:
        raise ValueError("provider_intent_invalid")
    return parts != ["none"]


def inventory(root: Path, config: dict[str, Any], events: list[dict[str, str]]):
    found = {key: [] for key in ("terraform", "module_directories", "source", "manifest", "billing")}
    vertex = False
    signal_files: list[str] = []
    patterns = signal_patterns(config["ai_signals"])
    audit(events, "walk", root)
    for candidate in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = candidate.relative_to(root)
        if candidate.is_symlink() or any(matches(relative, p, candidate.is_dir()) for p in config["exclude_roots"]):
            continue
        if candidate.is_dir():
            if any(matches(relative, p, True) for p in config["module_directories"]):
                found["module_directories"].append(relative.as_posix() + "/")
                audit(events, "classify_directory", candidate)
            continue
        if any(matches(relative, p) for p in config["secret_excludes"]):
            continue
        for category in ("terraform", "source", "manifest", "billing"):
            if any(matches(relative, pattern) for pattern in config[category]):
                found[category].append(relative.as_posix())
                if category == "terraform":
                    audit(events, "read", candidate)
                    raw = candidate.read_bytes()
                    vertex = vertex or any(token.encode() in raw for token in config["vertex_strong_tokens"])
                elif category in AI_SIGNAL_SCOPE:
                    audit(events, "read", candidate)
                    raw = candidate.read_bytes()
                    if any(patterns[family].search(raw) for family in AI_SIGNAL_SCOPE[category]):
                        signal_files.append(relative.as_posix())
    return found, vertex, bool(signal_files), sorted(set(signal_files))


def durable(resume: Path | None, root: Path, events: list[dict[str, str]]):
    if resume is None:
        return False, []
    run = checked_root(resume, "resume_dir")
    try:
        run.relative_to((root / ".migration").resolve())
    except ValueError as exc:
        raise ValueError("resume_dir_invalid") from exc
    audit(events, "list", run)
    reasons = []
    anchors = {
        "ai-workload-profile.json", "openai-usage-profile.json",
        "anthropic-usage-profile.json", "openrouter-usage-profile.json",
        "aws-design-ai.json", "estimation-ai.json", "generation-ai.json",
    }
    names = {item.name for item in run.iterdir() if not item.is_symlink()}
    reasons.extend(f"artifact:{name}" for name in sorted(names & anchors))
    if directory(run / "ai-migration"):
        reasons.append("directory:ai-migration")
    state = run / ".phase-status.json"
    if regular(state):
        audit(events, "read", state)
        try:
            value = load_json(state.read_bytes())
            route_text = json.dumps(value.get("active_routes", value.get("active_route", "")))
            if "ai" in route_text.lower() or str(value.get("current_phase", "")).startswith("ai_"):
                reasons.append("state:active_ai")
        except Exception:
            reasons.append("state:corrupt")
    for name in ("preferences-draft.json", "preferences.json"):
        path = run / name
        if regular(path):
            audit(events, "read", path)
            try:
                value = load_json(path.read_bytes())
                if value.get("ai_constraints"):
                    reasons.append(f"preferences:{name}:ai_constraints")
                if value.get("workloads"):
                    reasons.append(f"preferences:{name}:workloads")
            except Exception:
                reasons.append(f"preferences:{name}:corrupt")
    return bool(reasons), sorted(set(reasons))


def parsed_references(path: Path) -> list[str]:
    if path.suffix not in {".md", ".py"}:
        return []
    return sorted(set(TOKEN.findall(path.read_text(encoding="utf-8"))))


def validate_closure(base: Path, events: list[dict[str, str]], expected_sha256: str | None = None) -> dict[str, Any]:
    root = checked_root(base, "bma_base")
    skill = root / "SKILL.md"
    audit(events, "lstat", skill)
    if not regular(skill):
        raise ValueError("BEDROCK_MIGRATION_ASSESSMENT_SIBLING_MISSING")
    audit(events, "read", skill)
    frontmatter = skill.read_text(encoding="utf-8").split("---", 2)
    if len(frontmatter) < 3 or "\nname: bedrock-migration-assessment\n" not in "\n" + frontmatter[1] + "\n":
        raise ValueError("BEDROCK_MIGRATION_ASSESSMENT_SIBLING_MISSING")
    closure_path = root / "references/runtime/closure.json"
    audit(events, "lstat", closure_path)
    if not regular(closure_path):
        raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    audit(events, "read", closure_path)
    raw = closure_path.read_bytes()
    if expected_sha256 is not None and (not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or digest(raw) != expected_sha256):
        raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    closure = load_json(raw)
    if set(closure) != CLOSURE_KEYS or closure.get("schema_version") != SCHEMA or closure.get("selected_base") != BASE:
        raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    unsigned = dict(closure)
    claimed_self_hash = unsigned.pop("self_hash")
    if not isinstance(claimed_self_hash, str) or digest(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()) != claimed_self_hash:
        raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    if closure["destination_root"] != DESTINATION_ROOT or closure["entrypoints"] != ENTRYPOINTS or closure["runtime_exclusions"] != RUNTIME_EXCLUSIONS:
        raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    entries = closure["entries"]
    if not isinstance(entries, list) or len(entries) != 65:
        raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    destinations: list[str] = []
    logical_ids: list[str] = []
    for entry in entries:
        keys = set(entry) if isinstance(entry, dict) else set()
        origin = entry.get("origin") if isinstance(entry, dict) else None
        required = ENTRY_KEYS | ({"source_path"} if origin != "bma-native" else set())
        if keys != required or origin not in ORIGINS or entry.get("parity") != PARITY[origin]:
            raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
        destination = entry.get("destination")
        source_path = entry.get("source_path")
        if not safe_relative(destination) or entry.get("type") not in TYPES or not re.fullmatch(r"bma\.runtime\.\d{2}", str(entry.get("logical_id"))):
            raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256"))) or not isinstance(entry.get("runtime_references"), list):
            raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
        if origin == "bma-native":
            if entry.get("canonical_owner") != BMA_OWNER:
                raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
        else:
            if not safe_relative(source_path):
                raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
            if origin == "selected-base-source" and entry.get("canonical_owner") != BMA_OWNER:
                raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
            if origin == "canonical-shared" and (not source_path.startswith("skills/shared/") or entry.get("canonical_owner") != source_path):
                raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
            if origin == "canonical-plugin" and (not source_path.startswith("scripts/") or entry.get("canonical_owner") != source_path):
                raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
        destinations.append(destination)
        logical_ids.append(entry["logical_id"])
    if len(set(destinations)) != 65 or len(set(logical_ids)) != 65:
        raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    known = set(destinations)
    if set(ENTRYPOINTS) - known:
        raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    for entry in entries:
        path = root / entry["destination"]
        audit(events, "lstat", path)
        if not regular(path):
            raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
        audit(events, "read", path)
        if digest(path.read_bytes()) != entry["sha256"]:
            raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
        parsed = parsed_references(path)
        if parsed != entry["runtime_references"] or any(target not in known for target in parsed):
            raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    reached = set(ENTRYPOINTS)
    changed = True
    while changed:
        changed = False
        for entry in entries:
            if entry["destination"] in reached:
                before = len(reached)
                reached.update(entry["runtime_references"])
                changed = changed or len(reached) != before
    if reached != known:
        raise ValueError("BMA_STANDALONE_CLOSURE_INVALID")
    return {
        "closure_entries": len(entries),
        "closure_sha256": digest(raw),
        "closure_self_hash": claimed_self_hash,
        "closure_audit_complete": True,
    }


def classify(args, events: list[dict[str, str]]) -> dict[str, Any]:
    root = checked_root(args.project_root, "project_root")
    config, closure_sha256 = bootstrap(Path(__file__).resolve(), args.patterns, args.bootstrap_manifest,
                                       args.expected_bootstrap_manifest_sha256, events)
    provider = provider_intent(args.provider_intent)
    found, vertex, ai_signal, signal_files = inventory(root, config, events)
    is_durable, reasons = durable(args.resume_dir, root, events)
    source = bool(found["source"] or found["manifest"])
    # SOURCE_CONTAINING is informational only; AI evidence drives candidacy.
    candidate = ai_signal or provider or vertex or is_durable
    infrastructure = bool(found["terraform"] or found["billing"])
    result = {
        "ok": True, "SOURCE_CONTAINING": source, "AI_SIGNAL_CANDIDATE": ai_signal,
        "ai_signal_files": signal_files,
        "PROVIDER_USAGE_INTENT": provider, "VERTEX_STRONG_CANDIDATE": vertex,
        "DURABLE_AI_ROUTE": is_durable, "AI_CANDIDATE": candidate,
        "PURE_INFRASTRUCTURE": infrastructure and not candidate,
        "inventory": found, "durable_reasons": reasons,
        "mutation_count": 0, "audit": events,
    }
    if args.bma_base is not None:
        if not candidate:
            raise ValueError("bma_preflight_not_authorized_for_non_candidate")
        expected_sibling = (Path(__file__).resolve().parent.parent.parent / BMA_OWNER).resolve()
        supplied_base = args.bma_base.resolve()
        if supplied_base != expected_sibling:
            raise ValueError("BEDROCK_MIGRATION_ASSESSMENT_SIBLING_MISSING")
        result.update(validate_closure(args.bma_base, events, closure_sha256))
        result["exact_sibling"] = str(expected_sibling)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("classify")
    command.add_argument("--project-root", required=True, type=Path)
    command.add_argument("--patterns", required=True, type=Path)
    command.add_argument("--bootstrap-manifest", required=True, type=Path)
    command.add_argument("--expected-bootstrap-manifest-sha256", required=True)
    command.add_argument("--provider-intent", required=True)
    command.add_argument("--resume-dir", type=Path)
    command.add_argument("--bma-base", type=Path)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--bma-base", required=True, type=Path)
    preflight.add_argument("--expected-closure-sha256")
    args = parser.parse_args()
    events: list[dict[str, str]] = []
    try:
        value = classify(args, events) if args.command == "classify" else {
            "ok": True,
            **validate_closure(args.bma_base, events, args.expected_closure_sha256),
            "mutation_count": 0,
            "audit": events,
        }
        print(json.dumps(value, sort_keys=True))
        return 0
    except ValueError as error:
        print(json.dumps({"ok": False, "reason": str(error), "mutation_count": 0, "audit": events}, sort_keys=True))
        return 2
    except Exception:
        print("BMA_BOOTSTRAP_UNEXPECTED", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
