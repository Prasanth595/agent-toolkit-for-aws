from __future__ import annotations

import hashlib
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "skills/bedrock-migration-assessment/scripts/bma-runtime.py"

runtime = types.ModuleType("bma_runtime_reentry")
exec(compile(PATH.read_text(encoding="utf-8"), str(PATH), "exec"), runtime.__dict__)

PHASES_THROUGH_DESIGN = {"discover": "completed", "clarify": "completed", "design": "completed",
                         "estimate": "pending", "generate": "pending"}
PHASES_THROUGH_ESTIMATE = {"discover": "completed", "clarify": "completed", "design": "completed",
                           "estimate": "completed", "generate": "pending"}
GENERATE_IN_PROGRESS = {"discover": "completed", "clarify": "completed", "design": "completed",
                        "estimate": "completed", "generate": "in_progress"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def request(run: Path, state: dict, writes: list[dict]) -> dict:
    return {
        "schema_version": 1, "mode": "direct", "scenario": "reentry", "run_dir": str(run),
        "state": state, "consent": [], "writes": writes, "assemblies": [],
    }


def design_write(payload: dict, expected: str | None = None, phase: str = "design") -> dict:
    value = {"phase": phase, "path": "aws-design-ai.json", "payload": payload,
             "logical_owner": "bedrock-migration-assessment"}
    if expected is not None:
        value["expected_sha256"] = expected
    return value


@pytest.fixture
def design_run(tmp_path: Path) -> tuple[Path, str]:
    run = tmp_path / "design"
    run.mkdir()
    runtime.execute_contract(request(run, {}, [design_write({"design": "first"})]))
    return run, sha(run / "aws-design-ai.json")


def test_design_rerun_with_prior_hash_succeeds_before_estimate(design_run: tuple[Path, str]) -> None:
    run, prior = design_run
    runtime.execute_contract(request(run, {"phases": PHASES_THROUGH_DESIGN}, [design_write({"design": "rerun"}, prior)]))
    assert '"design": "rerun"' in (run / "aws-design-ai.json").read_text()


def test_design_rerun_after_estimate_needs_stale_downstream(design_run: tuple[Path, str]) -> None:
    run, prior = design_run
    state = {"phases": PHASES_THROUGH_ESTIMATE}
    with pytest.raises(ValueError, match="replacement_not_authorized"):
        runtime.execute_contract(request(run, state, [design_write({"design": "rerun"}, prior)]))
    assert '"design": "first"' in (run / "aws-design-ai.json").read_text()
    runtime.execute_contract(request(run, {**state, "stale_downstream": True}, [design_write({"design": "rerun"}, prior)]))
    assert '"design": "rerun"' in (run / "aws-design-ai.json").read_text()


def test_reconstructed_state_never_authorizes_replacement(design_run: tuple[Path, str]) -> None:
    run, prior = design_run
    with pytest.raises(ValueError, match="replacement_not_authorized"):
        runtime.execute_contract(request(run, {"stale_downstream": True}, [design_write({"design": "rerun"}, prior)]))


def test_stale_prior_hash_is_rejected(design_run: tuple[Path, str]) -> None:
    run, _ = design_run
    with pytest.raises(ValueError, match="expected_prior_hash_mismatch"):
        runtime.execute_contract(request(run, {"phases": PHASES_THROUGH_DESIGN}, [design_write({"design": "rerun"}, "0" * 64)]))


def test_same_request_duplicate_is_rejected_even_with_hash(design_run: tuple[Path, str]) -> None:
    run, prior = design_run
    writes = [design_write({"design": "a"}, prior), design_write({"design": "b"}, prior)]
    with pytest.raises(ValueError, match="duplicate_final_write"):
        runtime.execute_contract(request(run, {"phases": PHASES_THROUGH_DESIGN}, writes))


def test_replacement_requires_owning_phase(design_run: tuple[Path, str]) -> None:
    run, prior = design_run
    with pytest.raises(ValueError, match="write_phase_invalid"):
        runtime.execute_contract(request(run, {"phases": PHASES_THROUGH_DESIGN},
                                         [design_write({"design": "rerun"}, prior, phase="estimate")]))


def test_replacement_without_hash_is_still_duplicate(design_run: tuple[Path, str]) -> None:
    run, _ = design_run
    with pytest.raises(ValueError, match="duplicate_final_write"):
        runtime.execute_contract(request(run, {"phases": PHASES_THROUGH_DESIGN}, [design_write({"design": "rerun"})]))


GENERATE_PATHS = ["generation-ai.json", "ai-migration/anthropic-adapter.ts"]


def generate_writes(payload: str, hashes: dict[str, str] | None = None) -> list[dict]:
    writes = []
    for path in GENERATE_PATHS:
        value = {"phase": "generate", "path": path, "payload": {"v": payload} if path.endswith(".json") else payload,
                 "logical_owner": "bedrock-migration-assessment"}
        if hashes is not None:
            value["expected_sha256"] = hashes[path]
        writes.append(value)
    return writes


def test_partial_generate_recovery_replaces_with_prior_hashes(tmp_path: Path) -> None:
    run = tmp_path / "generate"
    run.mkdir()
    runtime.execute_contract(request(run, {"phases": PHASES_THROUGH_ESTIMATE, "dirty_state": {"phase": "generate", "stage": "stage_1_planning"}},
                                     generate_writes("first")))
    prior = {path: sha(run / path) for path in GENERATE_PATHS}
    state = {"phases": GENERATE_IN_PROGRESS, "dirty_state": {"phase": "generate", "stage": "stage_1_planning"}}
    runtime.execute_contract(request(run, state, generate_writes("rerun", prior)))
    assert (run / "ai-migration/anthropic-adapter.ts").read_text() == "rerun"


def test_partial_generate_recovery_without_hashes_is_rejected(tmp_path: Path) -> None:
    run = tmp_path / "generate-control"
    run.mkdir()
    runtime.execute_contract(request(run, {}, generate_writes("first")))
    state = {"phases": GENERATE_IN_PROGRESS, "dirty_state": {"phase": "generate", "stage": "stage_1_planning"}}
    with pytest.raises(ValueError, match="duplicate_final_write"):
        runtime.execute_contract(request(run, state, generate_writes("rerun")))


def test_replacement_publish_failure_restores_prior_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = tmp_path / "rollback"
    run.mkdir()
    runtime.execute_contract(request(run, {}, generate_writes("first")))
    prior = {path: sha(run / path) for path in GENERATE_PATHS}
    before = tree_bytes(run)
    real_replace = runtime.os.replace
    calls = 0

    def fail_second_publish(source: object, target: object) -> None:
        nonlocal calls
        calls += 1
        # Calls 1 and 3 back up the two prior files; call 4 publishes the second staged file.
        if calls == 4:
            raise OSError("synthetic publish failure")
        real_replace(source, target)

    monkeypatch.setattr(runtime.os, "replace", fail_second_publish)
    state = {"phases": GENERATE_IN_PROGRESS, "dirty_state": {"phase": "generate", "stage": "stage_1_planning"}}
    with pytest.raises(OSError, match="synthetic publish failure"):
        runtime.execute_contract(request(run, state, generate_writes("rerun", prior)))
    assert tree_bytes(run) == before
