from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "scan-render-application.py"
FIXTURE = SCRIPT_DIR.parent / "fixtures/render-application"
AI_SCHEMA = SCRIPT_DIR.parent / "references/contracts/ai-workload-profile.schema.json"
DISCOVERY_SCHEMA = SCRIPT_DIR.parent / "references/shared/schema-render-ai-discovery.json"
spec = importlib.util.spec_from_file_location("scan_render_application", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_closed_scan_emits_strong_provider_neutral_profile_without_snippets() -> None:
    first = module.scan(FIXTURE)
    second = module.scan(FIXTURE)
    assert first == second
    assert {item["kind"] for item in first["signals"]} >= {"postgres_client", "key_value_client"}
    profile = first["ai_profile"]
    discovery = first["ai_discovery"]
    assert profile is not None and discovery is not None
    Draft7Validator(json.loads(AI_SCHEMA.read_text())).validate(profile)
    Draft202012Validator(json.loads(DISCOVERY_SCHEMA.read_text())).validate(discovery)
    assert "execution" not in profile
    openai_source = next(s for s in profile["ai_sources"] if s["provider"] == "openai" and s["source_service"] == "openai_api")
    assert "gpt-4o-mini" in openai_source["models"]
    assert {(s["provider"], s["source_service"]) for s in profile["ai_sources"]} == {("anthropic", "anthropic_api"), ("google", "gemini_api"), ("google", "vertex_ai"), ("openai", "openai_api")}
    assert profile["gateways"] == [{"product": "openrouter", "type": "llm_router", "upstream_evidence": "unresolved", "upstreams": []}]
    assert "gpt-4o-mini" in [model["observed_identifier"] for model in discovery["models"]]
    assert {provider["family"] for provider in discovery["providers"]} >= {"openai", "anthropic", "google_gemini", "google_vertex_ai", "amazon_bedrock", "openrouter"}
    assert {gateway["family"] for gateway in discovery["gateways"]} == {"openrouter"}
    capabilities = {capability for workload in discovery["workloads"] for capability in workload["capabilities"]}
    assert {"agent_orchestration", "agent_tools", "retrieval", "embedding", "reranking", "document_ingestion", "image", "speech"} <= capabilities
    serialized = json.dumps(first)
    assert "not retained by scanner" not in serialized
    assert "api_key=os.environ" not in serialized
    assert "OPENAI_API_KEY" in serialized


def test_environment_name_alone_does_not_cross_threshold(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text('name = "OPENAI_API_KEY"\n')
    result = module.scan(tmp_path)
    assert result["ai_profile"] is None
    assert result["ai_discovery"] is None


def test_openrouter_vendor_prefixed_model_yields_observed_upstream(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "import os\nfrom openai import OpenAI\n"
        'client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])\n'
        'client.chat.completions.create(model="anthropic/claude-3.5-sonnet")\n'
    )
    profile = module.scan(tmp_path)["ai_profile"]
    Draft7Validator(json.loads(AI_SCHEMA.read_text())).validate(profile)
    gateway = next(g for g in profile["gateways"] if g["product"] == "openrouter")
    assert gateway["upstream_evidence"] == "observed"
    assert gateway["upstreams"] == [{"provider": "anthropic", "source_service": "anthropic_api", "model_families": [{"family": "claude", "model_evidence": "observed", "models": ["claude-3.5-sonnet"]}]}]
    anthropic_source = next(s for s in profile["ai_sources"] if s["provider"] == "anthropic")
    observation = anthropic_source["model_observations"][0]
    assert observation["raw_model"] == "anthropic/claude-3.5-sonnet"
    assert observation["normalized_model"] == "claude-3.5-sonnet"
    assert observation["evidence"][0] == {"provenance": "code", "confidence": "confirmed", "detail": "app.py:4"}
    assert not any(s["provider"] == "openrouter" for s in profile["ai_sources"])


def test_symlink_secret_generated_binary_and_unsupported_files_are_metadata_only(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=secret")
    (tmp_path / "blob.py").write_bytes(b"abc\x00def")
    (tmp_path / "notes.txt").write_text("secret prose")
    generated = tmp_path / "node_modules"
    generated.mkdir()
    (generated / "index.js").write_text("OpenAI()")
    target = tmp_path / "target.py"
    target.write_text("print('safe')")
    (tmp_path / "link.py").symlink_to(target)
    result = module.scan(tmp_path)
    reasons = {item["reason"] for item in result["skipped"]}
    assert {"sensitive_name", "binary_file", "unsupported_type", "excluded_directory", "symlink"} <= reasons
    assert all("path" not in item and item["path_hash"].startswith("sha256:") for item in result["skipped"])
    assert "OPENAI_API_KEY=secret" not in json.dumps(result)


def test_minified_generated_javascript_contributes_no_metadata_or_signals(tmp_path: Path) -> None:
    (tmp_path / "bundle.min.js").write_text(
        'const client = new OpenAI(); client.chat.completions.create({model: "gpt-4o-mini"});'
    )
    result = module.scan(tmp_path)
    assert result["files"] == []
    assert result["signals"] == []
    assert result["ai_profile"] is None
    assert result["ai_discovery"] is None
    assert {item["reason"] for item in result["skipped"]} == {"generated_file"}


def test_non_utf8_and_file_bounds_skip_without_partial_content(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_bytes(b"\xff")
    (tmp_path / "large.py").write_bytes(b"x" * (module.MAX_FILE_BYTES + 1))
    result = module.scan(tmp_path)
    assert {item["reason"] for item in result["skipped"]} == {"invalid_utf8", "file_too_large"}


def test_root_must_be_absolute_regular_directory(tmp_path: Path) -> None:
    with pytest.raises(module.ScanError, match="workspace_root_invalid"):
        module.scan(Path("relative"))
    link = tmp_path / "link"
    target = tmp_path / "target"
    target.mkdir()
    link.symlink_to(target)
    with pytest.raises(module.ScanError, match="workspace_root_invalid"):
        module.scan(link)
