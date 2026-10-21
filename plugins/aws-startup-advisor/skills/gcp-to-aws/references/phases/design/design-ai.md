# Compatibility shim — BMA AI Design

Removal: issue #389 after stages 3b and 3c repoint all consumers and copied-layout tests pass.

Resolve `$BMA_BASE` as the exact sibling `<GCP_BASE>/../bedrock-migration-assessment`. Require completed delegated preflight, pass the existing `$MIGRATION_DIR`, and load exactly `$BMA_BASE/references/phases/design/design-ai.md`. BMA alone writes `aws-design-ai.json`; do not implement mappings, validation, state changes, or fallback behavior here.
