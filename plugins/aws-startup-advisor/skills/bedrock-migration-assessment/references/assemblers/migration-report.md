# Direct migration report assembler

Validate `references/report-sections/ai-migration-report.md` contributions and artifacts, then submit the final `migration-report.html` assembly through `scripts/bma-runtime.py execute --request -`. The production entrypoint selects the direct writer and rejects duplicate or existing targets. After it writes, run `scripts/validate-migration-report.py`. Report failure remains optional and nonblocking.
