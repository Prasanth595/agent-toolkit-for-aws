from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT = SCRIPT_DIR / "normalize-render-capture.py"
spec = importlib.util.spec_from_file_location("normalize_render_capture", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ATTEMPT = "12345678-1234-4234-9234-123456789abc"
DIGEST = "sha256:" + "a" * 64
INDEX_DIGEST = "sha256:" + "c" * 64
CAPTURED_AT = "2026-10-21T12:00:00Z"


def load_script(name: str, module_name: str) -> Any:
    script_spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / name)
    assert script_spec and script_spec.loader
    loaded = importlib.util.module_from_spec(script_spec)
    script_spec.loader.exec_module(loaded)
    return loaded


def write_capture(root: Path, name: str, transport: str, category: str, value: dict[str, Any]) -> dict[str, Any]:
    path = root / name
    payload = module.canonical_bytes(value)
    path.write_bytes(payload)
    live_capture = transport in {"cli", "rest"}
    return {
        "transport": transport,
        "category": category,
        "captured_at": value.get("captured_at", CAPTURED_AT),
        "workspace_id": value.get("workspace_id", "tea-safe"),
        "status": value.get("status", "ok"),
        "page_count": value.get("page_count") if live_capture else None,
        "ownership_index_digest": value.get("ownership_index_digest") if live_capture else None,
        "path": name,
        "digest": module.sha256_digest(payload),
    }


def live(transport: str, category: str, data: Any, resource_id: str | None = None, status: str = "ok") -> dict[str, Any]:
    return {
        "schema_version": "1.0", "transport": "render_cli_2.30.0" if transport == "cli" else "render_rest_v1",
        "category": category, "captured_at": CAPTURED_AT, "attempt_id": ATTEMPT,
        "workspace_id": "tea-safe", "consent_digest": DIGEST,
        "raw_shape": "array", "command_digest": "sha256:" + "b" * 64,
        "ownership_index_digest": INDEX_DIGEST, "status": status, "page_count": 1 if transport == "rest" else None, "raw_shapes": ["array"],
        "request": {"resource_id": resource_id, "start": None, "end": None, "resolution_seconds": None, "limit": 100}, "data": data,
    }


def build_estate(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    captures: list[dict[str, Any]] = []
    blueprint_parser = load_script("parse-render-blueprint.py", "blueprint_for_normalize")
    blueprint_root = SCRIPT_DIR.parent / "fixtures/render-blueprint"
    identity = {"schema_version": "1.0", "status": "active", "identity_scope": "live", "attempt_id": ATTEMPT, "workspace_id": "tea-safe", "local_identity": None, "consent_digest": DIGEST, "ownership_index_digest": INDEX_DIGEST}
    source = blueprint_root / "valid-full.yaml"
    evidence_path = tmp_path / "semantic-evidence.json"
    evidence_path.write_text(json.dumps({
        "schema_version": "1.0", "source_path": "valid-full.yaml",
        "source_digest": module.sha256_digest(source.read_bytes()),
        "manifest_digest": module.sha256_digest(module.canonical_bytes(identity)),
        "attempt_id": ATTEMPT, "workspace_id": "tea-safe", "consent_digest": DIGEST,
        "validated_at": "2026-10-21T12:00:00Z", "outcome": "valid", "errors": [],
    }))
    blueprint = blueprint_parser.parse_blueprint(source, blueprint_root, tmp_path, evidence_path)
    captures.append(write_capture(tmp_path, "blueprint.json", "blueprint", "blueprint", blueprint))
    captures.append(write_capture(tmp_path, "projects.json", "rest", "projects_list", live("rest", "projects_list", [{"id": "prj-safe", "name": "project", "ownerId": "tea-safe"}])))
    captures.append(write_capture(tmp_path, "environments.json", "rest", "environments_list", live("rest", "environments_list", [{"id": "evm-safe-prod", "name": "production", "projectId": "prj-safe", "serviceIds": ["srv-safe-api"], "databasesIds": [], "redisIds": [], "envGroupIds": []}], "prj-safe")))
    services = [{"id": "srv-safe-api", "name": "root-api", "ownerId": "tea-safe", "type": "web_service", "projectId": None, "region": "ohio", "repo": "https://github.com/example/live-drift", "serviceDetails": {"plan": "0.5c-512mb", "buildPlan": "starter", "runtime": "python", "numInstances": 1}}]
    captures.append(write_capture(tmp_path, "services.json", "rest", "services_list", live("rest", "services_list", services)))
    build_source = [{"id": "bld-safe", "name": "shared-build", "ownerId": "tea-safe", "repo": "https://github.com/example/safe-app", "branch": "main", "commit": "0123456789abcdef", "artifact": {"id": "artifact-safe", "digest": "sha256:" + "d" * 64}, "buildCommand": "docker build .", "serviceIds": ["srv-safe-api"], "environmentIds": ["evm-safe-prod"], "buildEnvVarNames": ["BUILD_MODE"], "runtimeEnvVarNames": ["PORT"]}]
    captures.append(write_capture(tmp_path, "build-sources.json", "rest", "build_sources_list", live("rest", "build_sources_list", build_source)))
    deploys = [{"id": "dep-old", "status": "live", "createdAt": "2026-10-20T12:00:00Z", "commit": {"id": "abc"}}, {"id": "dep-new", "status": "update_failed", "createdAt": "2026-10-21T12:00:00Z", "finishedAt": "2026-10-21T12:02:00Z", "commit": {"id": "abc"}}]
    captures.append(write_capture(tmp_path, "deploys.json", "rest", "deploys_list", live("rest", "deploys_list", deploys, "srv-safe-api")))
    events = [{"id": "evt-safe", "resourceId": "srv-safe-api", "type": "deploy_live", "timestamp": "2026-10-20T12:00:00Z", "statusCode": 200}]
    captures.append(write_capture(tmp_path, "events.json", "rest", "service_events", live("rest", "service_events", events, "srv-safe-api")))
    captures.append(write_capture(tmp_path, "workflows.json", "rest", "workflows_list", live("rest", "workflows_list", [{"id": "wfl-safe", "name": "workflow", "ownerId": "tea-safe", "type": "workflow", "environmentId": "evm-safe-prod"}])))
    captures.append(write_capture(tmp_path, "workflow-versions.json", "rest", "workflow_versions_list", live("rest", "workflow_versions_list", [{"id": "wfv-safe", "name": "v1", "workflowId": "wfl-safe", "ownerId": "tea-safe"}], "wfl-safe")))
    captures.append(write_capture(tmp_path, "workflow-tasks.json", "rest", "workflow_tasks_list", live("rest", "workflow_tasks_list", [{"id": "tsk-safe", "name": "task", "workflowVersionId": "wfv-safe", "ownerId": "tea-safe"}], "wfl-safe")))
    captures.append(write_capture(tmp_path, "workflow-runs.json", "rest", "workflow_task_runs_list", live("rest", "workflow_task_runs_list", [{"id": "run-safe", "name": "run", "taskId": "tsk-safe", "ownerId": "tea-safe", "attempts": [{"id": "att-safe", "name": "attempt-1", "status": "succeeded"}]}], "wfl-safe")))
    scanner = load_script("scan-render-application.py", "scanner_for_normalize")
    application = scanner.scan(SCRIPT_DIR.parent / "fixtures/render-application")
    captures.append(write_capture(tmp_path, "application.json", "application", "application", application))
    billing_parser = load_script("parse-render-billing.py", "billing_for_normalize")
    billing_data = (SCRIPT_DIR.parent / "fixtures/render-billing/user-stated.json").read_bytes()
    billing = billing_parser.parse(billing_data, ".json")
    captures.append(write_capture(tmp_path, "billing.json", "billing", "billing", billing))
    manifest = {"schema_version": "1.0", "status": "active", "identity_scope": "live", "attempt_id": ATTEMPT, "workspace_id": "tea-safe", "local_identity": None, "consent_digest": DIGEST, "ownership_index_digest": INDEX_DIGEST, "captures": captures}
    (tmp_path / "manifest.json").write_bytes(module.canonical_bytes(manifest))
    return tmp_path / "manifest.json"


def test_mixed_estate_normalizes_drift_lifecycle_build_sources_workflows_and_ai(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_manifest = build_estate(first_root)
    second_manifest = build_estate(second_root)
    first_inventory, first_clusters, first_ai, first_discovery = module.normalize(first_root, first_manifest, ATTEMPT)
    second_inventory, second_clusters, second_ai, second_discovery = module.normalize(second_root, second_manifest, ATTEMPT)
    assert module.canonical_bytes(first_inventory) == module.canonical_bytes(second_inventory)
    assert module.canonical_bytes(first_clusters) == module.canonical_bytes(second_clusters)
    assert module.canonical_bytes(first_ai) == module.canonical_bytes(second_ai)
    assert module.canonical_bytes(first_discovery) == module.canonical_bytes(second_discovery)
    kinds = {resource["kind"] for resource in first_inventory["resources"]}
    assert {
        "render.web_service", "render.static_site", "render.private_service",
        "render.background_worker", "render.cron_job", "render.postgres",
        "render.key_value", "render.persistent_disk", "render.project",
        "render.environment", "render.environment_group", "render.custom_domain",
        "render.preview_environment", "render.build_source", "render.build_artifact",
        "render.workflow", "render.workflow_version", "render.workflow_task",
        "render.task_run", "render.task_attempt",
    } <= kinds
    edge_types = {edge["type"] for edge in first_inventory["edges"]}
    assert {"service_to_key_value", "private_network_peer", "shares_repository", "service_uses_build_source", "build_source_produces_artifact", "environment_promotes_artifact", "workflow_has_version", "workflow_version_has_task", "workflow_task_has_run", "task_run_has_attempt"} <= edge_types
    api = next(
        resource for resource in first_inventory["resources"]
        if resource["kind"] == "render.web_service" and resource["name"] == "root-api"
    )
    assert api["region"] == "ohio"
    assert api["environment_id"] == "evm-safe-prod"
    assert api["project_id"] == "prj-safe"
    assert api["provenance"]["environment_id"] == "rest:environments_list"
    assert api["config"]["repo"] == "https://github.com/example/shared-app"
    repo_drift = next(item for item in first_inventory["drift"] if item["resource_id"] == api["id"] and item["field"] == "config.repo")
    assert repo_drift["selection_reason"] == "declared_repository_intent_prefers_blueprint"
    membership_edges = [edge for edge in first_inventory["edges"] if edge["from_id"] == api["id"] and edge["type"] in {"member_of_environment", "member_of_project"}]
    assert {edge["type"] for edge in membership_edges} == {"member_of_environment", "member_of_project"}
    disk = next(resource for resource in first_inventory["resources"] if resource["kind"] == "render.persistent_disk")
    disk_edge = next(edge for edge in first_inventory["edges"] if edge["type"] == "service_to_disk" and edge["to_id"] == disk["id"])
    disk_owner = next(resource for resource in first_inventory["resources"] if resource["id"] == disk_edge["from_id"])
    assert disk["region"] == disk_owner["region"] == "virginia"
    assert disk_edge["attributes"] == {
        "mountPath": "/var/data",
        "sizeGB": 5,
        "capacity_unit": "GB",
        "region": "virginia",
        "region_provenance": disk["provenance"]["region"],
        "source": "declared",
    }
    assert len([edge for edge in first_inventory["edges"] if edge["type"] == "service_to_disk" and edge["to_id"] == disk["id"]]) == 1
    production_environment = next(
        resource for resource in first_inventory["resources"]
        if resource["kind"] == "render.environment" and resource["name"] == "production"
    )
    assert production_environment["render_id"] == "evm-safe-prod"
    assert production_environment["environment_id"] == "evm-safe-prod"
    production_cluster = next(
        cluster for cluster in first_clusters["clusters"]
        if api["id"] in cluster["member_ids"]
    )
    assert production_environment["id"] in production_cluster["member_ids"]
    assert production_cluster["seed"] == "evm-safe-prod"
    assert not any(cluster["seed"] == "production" for cluster in first_clusters["clusters"])
    assert api["config"]["lifecycle_evidence"]["live_deploy_id"] == "dep-old"
    assert api["config"]["lifecycle_evidence"]["newest_deploy_id"] == "dep-new"
    assert any(item["field"] in {"region", "config.plan"} for item in first_inventory["drift"])
    accounted = first_inventory["accounting"]["accounted_resource_ids"]
    clustered = [item for cluster in first_clusters["clusters"] for item in cluster["member_ids"]] + first_clusters["unclustered_resource_ids"]
    assert sorted(accounted) == sorted(clustered) and len(clustered) == len(set(clustered))
    assert "execution" not in first_ai and first_ai["schema_version"] == "1.0"
    assert first_inventory["resources"] == sorted(first_inventory["resources"], key=lambda item: item["id"].encode())


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("missing", "environment_membership_unresolved"),
        ("duplicate", "environment_membership_duplicate"),
        ("wrong_kind", "environment_membership_wrong_kind"),
        ("conflict", "environment_membership_conflict"),
    ],
)
def test_environment_membership_arrays_fail_closed(tmp_path: Path, mutation: str, error: str) -> None:
    manifest = build_estate(tmp_path)
    document = json.loads(manifest.read_text())
    entry = next(item for item in document["captures"] if item["category"] == "environments_list")
    capture_path = tmp_path / entry["path"]
    capture = json.loads(capture_path.read_text())
    environment = capture["data"][0]
    if mutation == "missing":
        environment["serviceIds"] = ["srv-missing"]
    elif mutation == "duplicate":
        environment["serviceIds"] = ["srv-safe-api", "srv-safe-api"]
    elif mutation == "wrong_kind":
        environment["databasesIds"] = ["srv-safe-api"]
    else:
        capture["data"].append({
            "id": "evm-safe-other", "name": "other", "projectId": "prj-safe",
            "serviceIds": ["srv-safe-api"], "databasesIds": [], "redisIds": [], "envGroupIds": [],
        })
    capture_path.write_bytes(module.canonical_bytes(capture))
    entry["digest"] = module.sha256_digest(capture_path.read_bytes())
    manifest.write_bytes(module.canonical_bytes(document))
    with pytest.raises(module.NormalizeError, match=error):
        module.normalize(tmp_path, manifest, ATTEMPT)


def test_manifest_digest_attempt_and_secret_fail_without_outputs(tmp_path: Path) -> None:
    manifest = build_estate(tmp_path)
    document = json.loads(manifest.read_text())
    document["captures"][0]["digest"] = "sha256:" + "0" * 64
    manifest.write_bytes(module.canonical_bytes(document))
    with pytest.raises(module.NormalizeError, match="capture_digest_mismatch"):
        module.normalize(tmp_path, manifest, ATTEMPT)
    assert not (tmp_path / "inventory.json").exists()

    manifest = build_estate(tmp_path)
    document = json.loads(manifest.read_text())
    del document["captures"][0]["captured_at"]
    manifest.write_bytes(module.canonical_bytes(document))
    with pytest.raises(module.NormalizeError, match="manifest_invalid"):
        module.normalize(tmp_path, manifest, ATTEMPT)

    manifest = build_estate(tmp_path)
    with pytest.raises(module.NormalizeError, match="manifest_invalid"):
        module.normalize(tmp_path, manifest, "87654321-4321-4321-8321-cba987654321")


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("captured_at", "2026-10-21T12:00:01Z"),
        ("workspace_id", "tea-other"),
        ("status", "successful_empty"),
        ("page_count", 2),
    ],
)
def test_manifest_capture_evidence_must_match_child(tmp_path: Path, field: str, replacement: object) -> None:
    manifest = build_estate(tmp_path)
    document = json.loads(manifest.read_text())
    live_entry = next(entry for entry in document["captures"] if entry["transport"] == "rest")
    live_entry[field] = replacement
    manifest.write_bytes(module.canonical_bytes(document))
    with pytest.raises(module.NormalizeError, match="capture_evidence_mismatch"):
        module.normalize(tmp_path, manifest, ATTEMPT)


def test_cli_child_from_previous_ownership_index_generation_is_rejected(tmp_path: Path) -> None:
    old_child = live("cli", "projects_list", [{"id": "prj-safe", "name": "project", "ownerId": "tea-safe"}])
    entry = write_capture(tmp_path, "projects-cli.json", "cli", "projects_list", old_child)
    new_index_digest = "sha256:" + "d" * 64
    entry["ownership_index_digest"] = new_index_digest
    manifest = {
        "schema_version": "1.0",
        "status": "active",
        "identity_scope": "live",
        "attempt_id": ATTEMPT,
        "workspace_id": "tea-safe",
        "local_identity": None,
        "consent_digest": DIGEST,
        "ownership_index_digest": new_index_digest,
        "captures": [entry],
    }
    path = tmp_path / "manifest.json"
    path.write_bytes(module.canonical_bytes(manifest))
    with pytest.raises(module.NormalizeError, match="capture_evidence_mismatch"):
        module.normalize(tmp_path, path, ATTEMPT)


def test_blueprint_only_discover_accepts_absent_or_stale_semantic_evidence(tmp_path: Path) -> None:
    for semantic in (
        {"status": "not_provided", "requires_renewed_consent": True},
        {"status": "stale", "evidence_source_digest": "sha256:" + "f" * 64, "requires_renewed_consent": True},
    ):
        root = tmp_path / semantic["status"]
        manifest = build_estate(root)
        document = json.loads(manifest.read_text())
        document["captures"] = [document["captures"][0]]
        local_identity = "sha256:" + "e" * 64
        document.update({
            "identity_scope": "local",
            "workspace_id": None,
            "local_identity": local_identity,
            "consent_digest": None,
            "ownership_index_digest": None,
        })
        document["captures"][0]["workspace_id"] = None
        document["captures"][0]["ownership_index_digest"] = None
        blueprint_path = root / "blueprint.json"
        blueprint = json.loads(blueprint_path.read_text())
        blueprint["semantic_validation"] = semantic
        blueprint_path.write_bytes(module.canonical_bytes(blueprint))
        document["captures"][0]["digest"] = module.sha256_digest(blueprint_path.read_bytes())
        manifest.write_bytes(module.canonical_bytes(document))

        inventory, clusters, ai_profile, ai_discovery = module.normalize(root, manifest, ATTEMPT)
        assert inventory["discovery_sources"] == ["render_blueprint"]
        assert inventory["workspace_id"] == "local:" + local_identity.removeprefix("sha256:")
        assert all(resource["workspace_id"] == inventory["workspace_id"] for resource in inventory["resources"])
        assert inventory["resources"]
        assert clusters["clusters"] or clusters["unclustered_resource_ids"]
        assert ai_profile is None
        assert ai_discovery is None


def test_live_only_discover_has_no_blueprint_provenance(tmp_path: Path) -> None:
    capture = live("rest", "services_list", [{
        "id": "srv-live-only", "name": "live-only", "ownerId": "tea-safe",
        "type": "web_service", "serviceDetails": {"runtime": "python"},
    }])
    entry = write_capture(tmp_path, "services.json", "rest", "services_list", capture)
    manifest = {
        "schema_version": "1.0", "status": "active", "identity_scope": "live", "attempt_id": ATTEMPT,
        "workspace_id": "tea-safe", "local_identity": None, "consent_digest": DIGEST,
        "ownership_index_digest": INDEX_DIGEST, "captures": [entry],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(module.canonical_bytes(manifest))

    inventory, _, _, _ = module.normalize(tmp_path, manifest_path, ATTEMPT)
    assert inventory["discovery_sources"] == ["render_rest"]
    assert "render_blueprint" not in inventory["discovery_sources"]


def test_blueprint_semantic_tuple_and_local_references_fail_closed(tmp_path: Path) -> None:
    manifest = build_estate(tmp_path)
    document = json.loads(manifest.read_text())
    blueprint_path = tmp_path / "blueprint.json"
    blueprint = json.loads(blueprint_path.read_text())
    blueprint["semantic_validation"]["outcome"] = "semantic_invalid"
    blueprint["semantic_validation"]["status"] = "invalid"
    blueprint_path.write_bytes(module.canonical_bytes(blueprint))
    document["captures"][0]["digest"] = module.sha256_digest(blueprint_path.read_bytes())
    manifest.write_bytes(module.canonical_bytes(document))
    with pytest.raises(module.NormalizeError, match="blueprint_semantic_validation_invalid"):
        module.normalize(tmp_path, manifest, ATTEMPT)

    manifest = build_estate(tmp_path)
    blueprint = json.loads(blueprint_path.read_text())
    blueprint["local_reference_validation"] = {"status": "semantic_invalid", "errors": [{"code": "broken_reference"}]}
    blueprint_path.write_bytes(module.canonical_bytes(blueprint))
    document = json.loads(manifest.read_text())
    document["captures"][0]["digest"] = module.sha256_digest(blueprint_path.read_bytes())
    manifest.write_bytes(module.canonical_bytes(document))
    with pytest.raises(module.NormalizeError, match="blueprint_local_references_invalid"):
        module.normalize(tmp_path, manifest, ATTEMPT)


def test_multi_output_commit_rolls_back_every_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = [tmp_path / "inventory.json", tmp_path / "clusters.json", tmp_path / "ai.json"]
    for index, path in enumerate(paths):
        path.write_text(f"old-{index}\n")
    real_replace = module.os.replace
    replacements = 0

    def fail_second(source: object, destination: object) -> None:
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("injected commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_second)
    with pytest.raises(OSError, match="injected commit failure"):
        module._write_generation([(paths[0], {"new": 1}), (paths[1], {"new": 2}), (paths[2], None)])
    assert [path.read_text() for path in paths] == ["old-0\n", "old-1\n", "old-2\n"]


def test_duplicate_live_identity_rejects_instead_of_suffixing(tmp_path: Path) -> None:
    captures = []
    duplicate = [{"id": "srv-duplicate", "name": "one", "ownerId": "tea-safe", "type": "web_service"}, {"id": "srv-duplicate", "name": "two", "ownerId": "tea-safe", "type": "web_service"}]
    captures.append(write_capture(tmp_path, "services.json", "rest", "services_list", live("rest", "services_list", duplicate)))
    manifest = {"schema_version": "1.0", "status": "active", "identity_scope": "live", "attempt_id": ATTEMPT, "workspace_id": "tea-safe", "local_identity": None, "consent_digest": DIGEST, "ownership_index_digest": INDEX_DIGEST, "captures": captures}
    path = tmp_path / "manifest.json"
    path.write_bytes(module.canonical_bytes(manifest))
    with pytest.raises(module.NormalizeError, match="duplicate_resource_identity"):
        module.normalize(tmp_path, path, ATTEMPT)
