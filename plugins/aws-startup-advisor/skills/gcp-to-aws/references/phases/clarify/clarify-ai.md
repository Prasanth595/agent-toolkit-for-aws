# Compatibility shim — BMA combined AI Clarify contribution

Removal: issue #389 after stages 3b and 3c repoint all consumers and copied-layout tests pass.

Resolve `$BMA_BASE` as the exact sibling `<GCP_BASE>/../bedrock-migration-assessment`. Require completed delegated preflight, pass the existing `$MIGRATION_DIR` and delegated GCP wording mode, then load exactly `$BMA_BASE/references/phases/clarify/clarify-ai.md`. Require one validated non-writing `BMA_AI_CLARIFY_RESULT`; GCP's assembler remains the sole combined `preferences.json` writer. No fallback implementation exists here.
