# Direct decision report assembler

Validate `references/runtime/content-contribution.schema.json`, consume `references/report-sections/ai-decision-report.md`, and submit both final targets through `scripts/bma-runtime.py execute --request -`. The production entrypoint rejects duplicate IDs/order keys and existing targets, sorts by bucket/source_order/UTF-8 ID, selects the direct writer, and performs each write. Run `scripts/emit-plan-json.py` after the successful decision writes.
