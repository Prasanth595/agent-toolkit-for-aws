# Direct migration documentation assembler

Validate AI contributions from `references/report-sections/ai-guide.md` and `references/report-sections/ai-readme.md`, then pass both final targets and their contributions to `scripts/bma-runtime.py execute --request -`. That production entrypoint selects the direct writer, assembles in canonical order, performs each write, and rejects duplicate or existing final targets.
