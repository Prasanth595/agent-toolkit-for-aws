# Compatibility shim — BMA AI Estimate

Removal: issue #389 after stages 3b and 3c repoint all consumers and copied-layout tests pass.

Resolve `$BMA_BASE` as the exact sibling `<GCP_BASE>/../bedrock-migration-assessment`. Require completed delegated preflight, pass the existing `$MIGRATION_DIR`, and load exactly `$BMA_BASE/references/phases/estimate/estimate-ai.md`. BMA alone writes `estimation-ai.json`; do not implement pricing, calculations, state changes, or fallback behavior here.
