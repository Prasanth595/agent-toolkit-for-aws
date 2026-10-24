from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BMA = ROOT / "skills/bedrock-migration-assessment"
GCP = ROOT / "skills/gcp-to-aws"
FIXTURES = ROOT / "fixtures/bedrock-migration-assessment/remote-smoke"
EVIDENCE = Path("/Users/lkleier/Downloads/startups-pr/.agents/tasks/bedrock-migration-assessment-extraction/practical-equivalence-evidence/remote-smoke")
CLAUDE = Path("/opt/homebrew/bin/claude")
MODEL = "claude-sonnet-4-5-20250929"
SECRET = re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|Bearer\s+\S+|/Users/|\.git/|[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD)\s*=\s*\S+)")

SCENARIOS = {
    "ordinary-batch1": [(BMA / "references/phases/clarify/clarify-ai-only.md", 98, 260)],
    "direct-openai-design": [(BMA / "SKILL.md", 1, 18), (BMA / "references/phases/design/design-ai.md", 1, 55)],
    "anthropic-capture-outcomes": [(BMA / "references/phases/discover/discover-anthropic-api.md", 50, 70), (BMA / "references/phases/discover/discover-anthropic-api.md", 112, 120), (BMA / "references/phases/discover/discover-anthropic-api.md", 274, 291)],
    "openrouter-multi-upstream": [(BMA / "references/phases/discover/discover-openrouter-api.md", 1, 25), (BMA / "references/phases/discover/discover-openrouter-api.md", 600, 710)],
    "delegated-gcp-combined": [(BMA / "SKILL.md", 1, 18), (GCP / "references/phases/clarify/clarify-assemble.md", 1, 48)],
    "resumed-generate": [(GCP / "references/phases/generate/generate.md", 1, 140), (BMA / "references/phases/generate/generate.md", 1, 10)],
}
EXPECTED_TOKENS = {
    "ordinary-batch1": (("preferences-draft.json",), ("technical", "batch 2")),
    "direct-openai-design": (("bedrock_migration_assessment", "bedrock-migration-assessment"), ("openai",), ("gpt-5.6-terra",), ("no telemetry", "telemetry\": null", "telemetry_owner\": null", "telemetry\": \"none", "telemetry_emitted\": false", "telemetry_emission\": null", "telemetry_emission\": false", "telemetry_emission\": \"none", "telemetry_emission\": \"disabled")),
    "anthropic-capture-outcomes": (("declined",), ("retry",), ("null", "unknown")),
    "openrouter-multi-upstream": (("openrouter",), ("anthropic",), ("openai",), ("claude-sonnet-5",), ("claude-haiku-4.5",), ("gpt-5.6-terra",)),
    "delegated-gcp-combined": (("gcp_to_aws", "gcp-to-aws", "\"gcp\""), ("bedrock_migration_assessment", "bedrock-migration-assessment", "\"bma\""), ("1", "one")),
    "resumed-generate": (("consent", "explicit_execute"), ("generate",), ("decide_and_execute", "stage_1_planning", "dirty_state")),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_bytes(path: Path) -> bytes:
    assert path.is_file() and not path.is_symlink()
    data = path.read_bytes()
    assert len(data) <= 32768
    data.decode("utf-8")
    assert not SECRET.search(data.decode("utf-8"))
    return data


def build_payload(scenario: str) -> tuple[bytes, list[dict[str, object]]]:
    generic = safe_bytes(FIXTURES / "public-instructions.md").decode()
    chunks = [generic]
    sources = []
    for source, start, end in SCENARIOS[scenario]:
        all_lines = source.read_text(encoding="utf-8").splitlines()
        excerpt = "\n".join(all_lines[start - 1:end]) + "\n"
        assert excerpt.strip() and excerpt in source.read_text(encoding="utf-8")
        relative = source.relative_to(ROOT).as_posix()
        chunks.append(f"\n## Public production excerpt: {relative}:{start}-{end}\n{excerpt}")
        sources.append({"source": relative, "start_line": start, "end_line": end, "sha256": digest(excerpt.encode())})
    payload = "".join(chunks).encode()
    assert len(payload) <= 32768 and not SECRET.search(payload.decode())
    return payload, sources


def observed_controls(outer: dict) -> dict[str, object]:
    usage = outer.get("usage") or {}
    server = usage.get("server_tool_use") or {}
    return {
        "permission_denials": len(outer.get("permission_denials") or []),
        "num_turns": outer.get("num_turns"),
        "web_search_requests": server.get("web_search_requests"),
        "web_fetch_requests": server.get("web_fetch_requests"),
        "tool_iterations": usage.get("tool_iterations"),
        "subagent_calls": usage.get("subagent_calls"),
        "tools_enabled_by_command": [],
        "mcp_servers_enabled_by_command": [],
    }


@pytest.mark.skipif(os.environ.get("BMA_REMOTE_SMOKE") != "1", reason="authorized opt-in remote smoke")
def test_six_representative_remote_smokes() -> None:
    fixtures = sorted(FIXTURES.glob("*.json"))
    assert len(fixtures) == 6
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    payload_dir = EVIDENCE / "payloads"; payload_dir.mkdir(exist_ok=True)
    version = subprocess.run([str(CLAUDE), "--version"], text=True, capture_output=True, check=True).stdout.strip()
    executable_sha = digest(CLAUDE.read_bytes())
    records = []
    semantic_failures = []
    for fixture in fixtures:
        fixture_bytes = safe_bytes(fixture)
        scenario = json.loads(fixture_bytes)["scenario_id"]
        payload, sources = build_payload(scenario)
        payload_path = payload_dir / f"{scenario}.md"; payload_path.write_bytes(payload)
        assert safe_bytes(payload_path) == payload
        command = [str(CLAUDE), "--safe-mode", "--restricted", "--strict-mcp-config",
                   "--mcp-config", '{"mcpServers":{}}', "--setting-sources", "",
                   "--no-session-persistence", "--permission-mode", "dontAsk", "--tools", "",
                   "--model", MODEL, "--effort", "low", "--max-budget-usd", "0.10",
                   "--system-prompt-file", str(payload_path), "--output-format", "json", "-p",
                   fixture_bytes.decode("utf-8")]
        started = time.monotonic()
        completed = subprocess.run(command, text=True, capture_output=True,
                                   env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
        duration = time.monotonic() - started
        assert completed.returncode == 0, completed.stderr or completed.stdout
        outer = json.loads(completed.stdout)
        result_text = outer.get("result", "").strip()
        if result_text.startswith("```json") and result_text.endswith("```"):
            result_text = result_text[7:-3].strip()
        result = json.loads(result_text)
        assert result["scenario_id"] == scenario and isinstance(result["actions"], (dict, list))
        rendered = json.dumps(result["actions"], sort_keys=True).lower()
        semantic_ok = all(any(token.lower() in rendered for token in alternatives) for alternatives in EXPECTED_TOKENS[scenario])
        if not semantic_ok:
            semantic_failures.append({"scenario": scenario, "expected_tokens": EXPECTED_TOKENS[scenario], "actions": result["actions"]})
        limitation = result["limitation"].lower()
        assert "representative" in limitation and "formal" in limitation
        controls = observed_controls(outer)
        assert controls["permission_denials"] == 0
        record = {
            "scenario_id": scenario, "fixture": fixture.name,
            "production_excerpt_sources": sources,
            "instruction_bytes": len(payload), "instruction_sha256": digest(payload),
            "fixture_bytes": len(fixture_bytes), "fixture_sha256": digest(fixture_bytes),
            "response_sha256": digest(completed.stdout.encode()), "stderr_sha256": digest(completed.stderr.encode()),
            "exit_status": completed.returncode, "duration_seconds": round(duration, 3),
            "cli": str(CLAUDE), "cli_version": version, "cli_sha256": executable_sha,
            "requested_model": MODEL, "host_model_usage": outer.get("modelUsage", {}),
            "total_cost_usd": outer.get("total_cost_usd"), "host_observed_controls": controls,
            "command": ["claude", *command[1:-1], "<fabricated-fixture-bytes>"],
            "assertions": [list(group) for group in EXPECTED_TOKENS[scenario]], "semantic_assertions_passed": semantic_ok,
            "observed_actions": result["actions"],
            "limitation": "Representative nondeterministic smoke evidence; not exhaustive conversational-equivalence proof.",
        }
        records.append(record)
        (EVIDENCE / f"{scenario}.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    index = {
        "schema_version": 2, "status": "PASS" if not semantic_failures else "FAIL", "scenarios": records,
        "limitation": "Complete equivalence of nondeterministic LLM interpretation cannot be formally proven.",
    }
    (EVIDENCE / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    assert not semantic_failures, semantic_failures
