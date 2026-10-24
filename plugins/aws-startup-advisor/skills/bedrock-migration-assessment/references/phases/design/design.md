# Design Bedrock target

Submit the planned `aws-design-ai.json` write to `scripts/bma-runtime.py execute --request -`; only write through that production entrypoint after it selects `bedrock-migration-assessment` as writer and accepts the current state. A same-route rerun must supply the prior SHA-256 of the existing file. The runtime enforces phase authority: it replaces the file only when the state marks downstream stale, or when no later phase is completed.

After Clarify is completed, load `references/phases/design/design-ai.md` and validate its current named-skill shape with `references/shared/schema-design-aws-ai.md`. BMA alone writes `aws-design-ai.json`.
