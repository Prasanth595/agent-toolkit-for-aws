# Compatibility shim — BMA OpenRouter discovery

Removal: issue #389 after stages 3b and 3c repoint all consumers and copied-layout tests pass.

Resolve `$BMA_BASE` as the exact sibling `<GCP_BASE>/../bedrock-migration-assessment`. Require completed delegated preflight and pass the existing `$MIGRATION_DIR`. Load exactly `$BMA_BASE/references/phases/discover/discover-openrouter-api.md`; preserve the BMA file's consent/capture result and do not implement, write, or fall back here.
