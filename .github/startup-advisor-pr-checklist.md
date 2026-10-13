# Startup Advisor PR checklist

The bot checks that PRs changing `plugins/aws-startup-advisor/` include the required author confirmations from the [Startup Advisor PR template](PULL_REQUEST_TEMPLATE/startup-advisor.md).

## What the bot checks

- The PR description contains the `Startup Advisor review checklist` section.
- All four confirmation items are present with their original wording, exactly once.
- All four items are checked.

Missing, altered, duplicated, or unchecked items fail the `Startup Advisor author checklist` check.
The bot posts a reminder listing the missing confirmations and linking to the template.
It updates the same reminder when the author edits the description; completed confirmations turn the check green.
Removing or unchecking an item makes the check fail again.

Authors can use the dedicated template or copy its checklist into an existing PR description.
Using the repository's default template alone is insufficient.
The bot validates the description's content, not which creation link the author used.
Summary, user impact, validation evidence, and other prose remain for reviewers to assess.
Checkboxes inside comments, quoted text, or code examples do not count.
The same checks apply to Draft and ready PRs.

## GitHub workflow

Once available on `main`, `.github/workflows/startup-advisor-pr-checklist.yml` handles PR creation, description edits, new commits, reopening, and Draft/ready transitions.
It reads the latest PR and complete changed-file inventory, including deletions and renames into or out of the plugin.
Unrelated PRs receive a neutral check and no new reminder.
Incomplete inventories, API failures, and concurrent changes fail the check rather than reporting an unverified success.

The workflow uses `pull_request_target` to support reminders on fork PRs.
Its job with write permissions executes only trusted base-branch code; PR content is passed as data.
The separate test job runs proposed code with read-only permissions.

This bot reports checklist completion and reminds authors. It does not start or block code reviews.
If maintainers want to block merging, they can configure `Startup Advisor author checklist` as a required status check.

## Validation

```sh
node --test .github/scripts/startup-advisor-pr-checklist.test.cjs
```
