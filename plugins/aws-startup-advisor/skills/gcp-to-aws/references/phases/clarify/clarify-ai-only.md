# Compatibility shim — BMA AI-only Clarify

Removal: issue #389 after stages 3b and 3c repoint all consumers and copied-layout tests pass.

Resolve `$BMA_BASE` as the exact sibling `<GCP_BASE>/../bedrock-migration-assessment`. Require completed delegated preflight, pass delegated GCP wording mode and the existing `$MIGRATION_DIR`, and load exactly `$BMA_BASE/references/phases/clarify/clarify-ai-only.md`. BMA is the sole preferences writer on this AI-only route; do not duplicate questions, state logic, or fallback behavior here.
