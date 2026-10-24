# Compatibility shim — BMA AI artifact generation

Removal: issue #389 after stage 3c repoints consumers and copied-layout tests pass.

Resolve `$BMA_BASE` as the exact sibling `<GCP_BASE>/../bedrock-migration-assessment`. Require completed delegated preflight and explicit outer Generate consent, pass the existing `$MIGRATION_DIR`, and load exactly `$BMA_BASE/references/phases/generate/generate-artifacts-ai.md`. BMA alone writes `ai-migration/**`; do not implement generators, writers, state changes, or fallback behavior here.
