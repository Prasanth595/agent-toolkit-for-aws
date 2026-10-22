---
_phase: discover
_title: "Discover Render Resources"
_init: true
_input: workspace
_interactive: false
_exec:
  _agent: rw
_fragments:
  - _id: blueprint
    _trigger: { _glob: "**/render.yaml" }
    _file: phases/discover/discover-blueprint.md
  - _id: live
    _trigger: { _when: "$MIGRATION_DIR/live-capture/manifest.json exists and is bound to the current consented attempt" }
    _file: phases/discover/discover-live.md
  - _id: app-code
    _trigger: { _when: "supported application source or dependency manifests exist" }
    _file: phases/discover/discover-app-code.md
  - _id: billing
    _trigger: { _when: "the user supplied a Render invoice, billing export, or monthly amount" }
    _file: phases/discover/discover-billing.md
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - render-resource-inventory.json
  - render-resource-clusters.json
  - { file: ai-workload-profile.json, _when: "provider-neutral AI evidence reaches the documented threshold" }
  - { file: render-ai-discovery.json, _when: "provider-neutral AI evidence reaches the documented threshold" }
_advances_to: clarify
_re_entry_guard:
  _stale_if_completed: clarify
  _stale_artifact: preferences.json
  _on_reentry: stop_unless_confirmed
  _on_confirm: reset_downstream_to_pending
_preconditions:
  - _check_single_active_phase: true
    _on_failure: _halt_and_inform
  - _assert: "main-window pre-work recorded either a local-only attempt identity for Blueprint/application/billing producers or an explicit workspace selection and read-only live-discovery consent disposition; a live decline invalidated every stale live manifest"
    _on_failure: _halt_and_inform
  - _assert: "at least one Blueprint, application source, current-spend input, or fresh consented live capture is available"
    _on_failure: _unrecoverable
_postconditions:
  - _check_file_exists: [render-resource-inventory.json, render-resource-clusters.json]
    _on_failure: _halt_and_inform
  - _validate_json: [render-resource-inventory.json, render-resource-clusters.json]
    _on_failure: _halt_and_inform
  - _assert: "every resource has a canonical Render kind, deterministic identity, field provenance, confidence, and exactly one accounting disposition; every disagreement is retained in drift[]"
    _on_failure: _halt_and_inform
  - _assert: "no secret values, credentials, connection information, application text, or database and Key Value contents occur in produced artifacts"
    _on_failure: _halt_and_inform
  - _assert: "when ai-workload-profile.json exists it validates against references/contracts/ai-workload-profile.schema.json (shared #415 contract), render-ai-discovery.json exists and validates against references/shared/schema-render-ai-discovery.json, and neither artifact carries an execution block"
    _on_failure: _halt_and_inform
_forbids_files:
  - preferences.json
  - aws-design.json
  - estimation-infra.json
  - "terraform/**"
---

# Phase 1: Discover Render resources

The main window first determines whether the user selected live capture. For a local-only Blueprint, application, or billing run, it does not require the Render CLI, authentication, workspace enumeration, workspace confirmation, or live consent. It mints a UUIDv4 attempt ID, computes a deterministic `local_identity` from the canonical producer paths and input digests, and writes a local manifest with `identity_scope: local`, null `workspace_id`, `consent_digest`, and `ownership_index_digest`, and no CLI/REST entries. Canonical outputs use the explicit `local:<digest>` identity and never describe it as a confirmed Render workspace. Blueprint-backed Generate still requires renewed main-window semantic validation before execution.

Only when live capture is selected does the main window check for exactly Render CLI 2.30.0, check authentication without initiating `render login`, enumerate accessible workspaces, ask the user to confirm exactly one workspace ID, and present the read-only consent gate with the exact CLI categories and GET-only API scope.

For every live consent decision or re-entry, mint a new UUIDv4 attempt ID and consent digest. Before capture, atomically replace any old active marker with an invalid disposition and remove stale manifest/index activation; a decline leaves no active live manifest but does not disable selected local producers. Write a fresh ownership index only from sanitized workspace-scoped CLI inventory, hash its exact bytes, and bind every child CLI/REST capture to that ownership-index digest and the same attempt/workspace/consent tuple. Each manifest entry records the child capture's exact RFC3339 timestamp, workspace, accepted status, page count (REST only), output path/digest, and ownership-index digest. Atomically activate the manifest only after every listed field and file reconciles with its sanitized child envelope; an earlier index generation or mismatched timestamp/status/page count is stale and must fail closed. Never initiate browser login, reuse stale captures, or treat process exit success as ownership proof.

Run all helpers as `uv run --project "$SKILL_BASE/scripts" --frozen python ...`. Only the main window may run consented commands. The dispatched worker reads workspace and active capture files, runs triggered local producers, and assembles canonical inventory and clusters. It performs no network requests, Render commands, prompts, state writes, or handoff. The main window re-reads outputs, applies postconditions, and alone emits `HANDOFF_OK`.
