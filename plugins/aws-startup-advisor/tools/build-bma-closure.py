#!/usr/bin/env python3
"""Materialize and validate the exact BMA standalone runtime closure."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import types
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
BMA = PLUGIN / "skills/bedrock-migration-assessment"
BASE = "4a51ac3f086499dcd1e1154992109e77f0bebaa6"

COPIES = {
    "SKILL.md": "skills/gcp-to-aws/SKILL.md",
    "scripts/emit-plan-json.py": "scripts/emit-plan-json.py",
    "scripts/validate-migration-report.py": "scripts/validate-migration-report.py",
    "scripts/validate-startup-program-artifacts.py": "scripts/validate-startup-program-artifacts.py",
    "references/phases/discover/discover-app-code.md": "skills/gcp-to-aws/references/phases/discover/discover-app-code.md",
    "references/phases/discover/discover-openai-api.md": "skills/gcp-to-aws/references/phases/discover/discover-openai-api.md",
    "references/phases/discover/discover-anthropic-api.md": "skills/gcp-to-aws/references/phases/discover/discover-anthropic-api.md",
    "references/phases/discover/discover-openrouter-api.md": "skills/gcp-to-aws/references/phases/discover/discover-openrouter-api.md",
    "references/phases/discover/discover-preview.md": "skills/gcp-to-aws/references/phases/discover/discover-preview.md",
    "references/phases/clarify/clarify-ai-only.md": "skills/gcp-to-aws/references/phases/clarify/clarify-ai-only.md",
    "references/phases/clarify/clarify-ai.md": "skills/gcp-to-aws/references/phases/clarify/clarify-ai.md",
    "references/phases/design/design-ai.md": "skills/gcp-to-aws/references/phases/design/design-ai.md",
    "references/phases/estimate/estimate-ai.md": "skills/gcp-to-aws/references/phases/estimate/estimate-ai.md",
    "references/phases/generate/generate-ai.md": "skills/gcp-to-aws/references/phases/generate/generate-ai.md",
    "references/phases/generate/generate-artifacts-ai.md": "skills/gcp-to-aws/references/phases/generate/generate-artifacts-ai.md",
    "references/design-refs/ai.md": "skills/gcp-to-aws/references/design-refs/ai.md",
    "references/design-refs/ai-gemini-to-bedrock.md": "skills/gcp-to-aws/references/design-refs/ai-gemini-to-bedrock.md",
    "references/shared/handoff-gates.md": "skills/gcp-to-aws/references/shared/handoff-gates.md",
    "references/shared/migration-complexity.md": "skills/gcp-to-aws/references/shared/migration-complexity.md",
    "references/shared/openai-on-bedrock.md": "skills/gcp-to-aws/references/shared/openai-on-bedrock.md",
    "references/shared/pricing-cache.md": "skills/gcp-to-aws/references/shared/pricing-cache.md",
    "references/shared/pricing-fallback.md": "skills/gcp-to-aws/references/shared/pricing-fallback.md",
    "references/shared/retarget-gotchas.md": "skills/gcp-to-aws/references/shared/retarget-gotchas.md",
    "references/shared/schema-discover-ai.md": "skills/gcp-to-aws/references/shared/schema-discover-ai.md",
    "references/shared/schema-design-aws-ai.md": "skills/gcp-to-aws/references/shared/schema-design-aws-ai.md",
    "references/shared/schema-preferences.md": "skills/gcp-to-aws/references/shared/schema-preferences.md",
    "references/shared/schema-phase-status.md": "skills/gcp-to-aws/references/shared/schema-phase-status.md",
    "references/shared/validate-artifacts.md": "skills/gcp-to-aws/references/shared/validate-artifacts.md",
    "references/shared/validate-migration-report.md": "skills/gcp-to-aws/references/shared/validate-migration-report.md",
}
for name in (
    "ai-anthropic-to-bedrock.md", "ai-gemini-to-bedrock.md", "ai-migration-guardrails.md",
    "ai-model-lifecycle.md", "ai-openai-to-bedrock.md", "ai-openrouter-to-bedrock.md",
    "bedrock-pricing-cache.md", "bedrock-quotas.md", "design-ref-agentic-to-agentcore.md",
    "design-ref-harness.md", "sdk-capability-map.json",
):
    COPIES[f"references/vendored/ai/{name}"] = f"skills/shared/ai/{name}"
for name in ("clarify-availability.md", "clarify-compliance.md", "clarify-cost-appetite.md", "clarify-multicloud.md", "clarify-region.md"):
    COPIES[f"references/vendored/clarify/{name}"] = f"skills/shared/clarify/{name}"

NATIVE = {
    "references/runtime/bedrock-region-map.json": '{"schema_version":1,"default":"us-east-1","compliance":{"fedramp":"us-gov-west-1","gdpr":"eu-west-1","hipaa":"us-east-1"}}\n',
    "references/runtime/plugin.json": '{"name":"aws-startup-advisor","skill":"bedrock-migration-assessment","version":"2.0.3"}\n',
    "references/runtime/bma-ai-clarify-result.schema.json": json.dumps({"$schema":"https://json-schema.org/draft/2020-12/schema","title":"BMA_AI_CLARIFY_RESULT","type":"object","additionalProperties":False,"required":["schema_version","kind","constraints","workloads","question_metadata"],"properties":{"schema_version":{"const":1},"kind":{"const":"BMA_AI_CLARIFY_RESULT"},"constraints":{"type":"object"},"workloads":{"type":"array"},"question_metadata":{"type":"object"}}}, indent=2) + "\n",
    "references/runtime/content-contribution.schema.json": (BMA / "references/runtime/content-contribution.schema.json").read_text(encoding="utf-8"),
    "references/shared/bma-ai-clarify-result.md": "# BMA AI Clarify result\n\nDelegated combined Clarify returns one validated, non-writing `BMA_AI_CLARIFY_RESULT`. GCP alone writes `preferences.json`; direct BMA writes its own preferences.\n",
    "references/phases/discover/discover.md": "# Discover AI workloads\n\nRun `discover-app-code.md`, then consent-gated provider discovery in this order: `discover-openai-api.md`, `discover-openrouter-api.md`, `discover-anthropic-api.md`, then `discover-preview.md`. Source-containing input is scanned once; confidence below 70% writes no AI profile.\n",
    "references/phases/clarify/clarify.md": "# Clarify AI requirements\n\nDirect mode loads `clarify-ai-only.md`. Delegated combined mode loads `clarify-ai.md`, validates one result against `references/runtime/bma-ai-clarify-result.schema.json`, and returns it without writing preferences.\n",
    "references/phases/design/design.md": "# Design Bedrock target\n\nAfter Clarify is completed, load `design-ai.md`. BMA alone writes `aws-design-ai.json`.\n",
    "references/phases/estimate/estimate.md": "# Estimate Bedrock costs\n\nAfter Design is completed, load `estimate-ai.md`. Preserve cached pricing, provenance, and unknown-versus-zero semantics. BMA alone writes `estimation-ai.json`.\n",
    "references/phases/generate/generate.md": "# Generate migration support artifacts\n\nGenerate is opt-in. Load `generate-ai.md`, then `generate-artifacts-ai.md`. BMA alone writes neutral plans and `ai-migration/`; the outer controller owns final assembly and state.\n",
    "references/report-sections/ai-guide.md": "# AI guide contribution\n\nReturn ordered `ai.*` guide steps; do not write a combined document.\n",
    "references/report-sections/ai-readme.md": "# AI README contribution\n\nReturn ordered `ai.*` catalog and Start-here rows; do not write a combined README.\n",
    "references/report-sections/ai-decision-report.md": "# AI decision contribution\n\nReturn ordered `ai.*` decision sections; do not write a combined report.\n",
    "references/report-sections/ai-migration-report.md": "# AI migration report contribution\n\nReturn ordered `ai.*` migration-report sections; do not write a combined report.\n",
    "references/assemblers/decision-report.md": "# Direct decision report assembler\n\nValidate `references/runtime/content-contribution.schema.json`, reject duplicate IDs/order keys, sort by bucket/source_order/UTF-8 ID, escape content, and write `decision-report.html` and `DECISION.md` exactly once.\n",
    "references/assemblers/migration-docs.md": "# Direct migration documentation assembler\n\nValidate AI contributions and write `MIGRATION_GUIDE.md` and `README.md` exactly once.\n",
    "references/assemblers/migration-report.md": "# Direct migration report assembler\n\nValidate AI contributions and artifacts, then write `migration-report.html` exactly once. Report failure remains optional and nonblocking.\n",
}

SPECIAL = {"scripts/bma-runtime.py", "scripts/bma-route-classifier.py", "references/runtime/bma-input-patterns.json"}
DESTINATIONS = ["SKILL.md", *sorted(SPECIAL), *sorted(key for key in COPIES if key != "SKILL.md"), *sorted(NATIVE)]
assert len(DESTINATIONS) == 65, len(DESTINATIONS)
TOKEN = re.compile(r"`((?:scripts|references)/[A-Za-z0-9_.\-/]+\.(?:md|json|py))`")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_for(destination: str) -> Path | None:
    source = COPIES.get(destination)
    return PLUGIN / source if source else None


def references(destination: str) -> list[str]:
    text = (BMA / destination).read_text(encoding="utf-8", errors="ignore")
    return sorted({match for match in TOKEN.findall(text) if match in set(DESTINATIONS)})


def build_value() -> dict:
    entries = []
    for index, destination in enumerate(DESTINATIONS, 1):
        source = source_for(destination)
        if destination in SPECIAL or destination in NATIVE:
            origin = "bma-native"
        elif source and "skills/shared/" in str(source):
            origin = "canonical-shared"
        elif source and "/scripts/" in str(source):
            origin = "canonical-plugin"
        else:
            origin = "selected-base-source"
        entry = {
            "logical_id": f"bma.runtime.{index:02d}", "origin": origin,
            "destination": destination,
            "type": "script" if destination.endswith(".py") else "data" if destination.endswith(".json") else "instruction",
            "sha256": sha(BMA / destination), "canonical_owner": "bedrock-migration-assessment" if origin in {"bma-native", "selected-base-source"} else source.relative_to(PLUGIN).as_posix(),
            "parity": "adapted" if origin == "selected-base-source" else "byte-identical" if origin.startswith("canonical-") else "native",
            "runtime_references": references(destination),
        }
        if source is not None:
            entry["source_path"] = source.relative_to(PLUGIN).as_posix()
        entries.append(entry)
    value = {
        "schema_version": 1, "selected_base": BASE,
        "destination_root": "skills/bedrock-migration-assessment",
        "entrypoints": ["SKILL.md", "scripts/bma-runtime.py", "scripts/emit-plan-json.py", "scripts/validate-migration-report.py", "scripts/validate-startup-program-artifacts.py", "references/phases/discover/discover.md", "references/phases/clarify/clarify.md", "references/phases/design/design.md", "references/phases/estimate/estimate.md", "references/phases/generate/generate.md", "references/assemblers/decision-report.md", "references/assemblers/migration-docs.md", "references/assemblers/migration-report.md"],
        "entries": entries,
        "runtime_exclusions": ["telemetry/**", "references/phases/**/*infra*", "references/phases/**/*billing*", "fixtures/**", "tests/**", "scripts/contracts/estimation-ai.schema.json", "scripts/contracts/generation-ai.schema.json"],
    }
    value["self_hash"] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return value


def validate(value: dict) -> list[str]:
    """Use the production classifier as the sole closure validator."""
    classifier = PLUGIN / "skills/shared/migration/bma-route-classifier.py"
    module = types.ModuleType("bma_production_closure_validator")
    exec(compile(classifier.read_text(encoding="utf-8"), str(classifier), "exec"), module.__dict__)
    try:
        module.validate_closure(BMA, [])
    except Exception as error:
        return [str(error)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    closure_path = BMA / "references/runtime/closure.json"
    current = build_value()
    if not args.check:
        closure_path.parent.mkdir(parents=True, exist_ok=True)
        closure_path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not closure_path.is_file():
        print("FAIL — closure missing"); return 1
    stored = json.loads(closure_path.read_text(encoding="utf-8"))
    errors = validate(stored)
    if stored != current:
        errors.append("closure stale")
    if errors:
        print("FAIL — " + "; ".join(errors)); return 1
    print(f"PASS — exact BMA closure entries=65 sha256={sha(closure_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
