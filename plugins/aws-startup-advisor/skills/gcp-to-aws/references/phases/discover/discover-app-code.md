# Compatibility shim — BMA app discovery

Removal: issue #389 after stages 3b and 3c repoint all consumers and copied-layout tests pass.

Resolve `$BMA_BASE` as the exact sibling `<GCP_BASE>/../bedrock-migration-assessment`. The outer GCP controller must already have completed candidate-only closure preflight. Pass the existing `$MIGRATION_DIR`, delegated mode, and any Vertex-seeded profile. Load exactly `$BMA_BASE/references/phases/discover/discover-app-code.md`; do not create a run, advance state, or use a fallback implementation.
Graviton/compute profiling is not delegated: `references/phases/discover/discover-app-graviton.md` (GCP-owned, loaded by the controller before this shim) owns `graviton_profile` with `source: "app_code"`. This shim is loaded only when preflight returned `AI_CANDIDATE: true`.
