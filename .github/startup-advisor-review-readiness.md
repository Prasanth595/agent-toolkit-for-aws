# Startup Advisor review readiness

Authors must complete the four confirmations in the [Startup Advisor PR template](PULL_REQUEST_TEMPLATE/startup-advisor.md) before automatic review starts.
This records the author's self-check; CI and reviewers still verify the change.

## Author workflow

1. Open a PR that changes Startup Advisor and include the template's checklist in the PR description.
2. Complete the confirmations. If any are missing, the bot posts a reminder with a template link and the missing items.
3. Mark the PR ready for review. The review entrypoint starts the reviewer only after all confirmations are complete.

| PR state | Checklist check | Review entrypoint |
| --- | --- | --- |
| Missing or unchecked confirmations | Failure; reminder lists missing items | Does not start review |
| All confirmations complete, still Draft | Success | Does not start review |
| All confirmations complete, ready for review | Success | Starts the configured reviewer |
| A confirmation is later unchecked or removed | Failure; existing reminder is updated | Does not start another review |
| Unrelated PR | Neutral; no checklist required | Does not start Startup Advisor review |
| Closed PR or readiness cannot be verified | No eligibility for review | Does not start review |

The bot edits its existing reminder instead of posting a new comment on every change.
It reads the PR description; checking boxes in a comment does not satisfy the requirement.
Changes to other plugins are unaffected. Mixed PRs, deletions, and renames into or out of `plugins/aws-startup-advisor/` are included.
The author must keep the wording of all four confirmations from the template.

## GitHub configuration

Once available on `main`, `.github/workflows/startup-advisor-pr-checklist.yml` handles PR creation, description edits, new commits, reopening, and Draft/ready transitions.
It reads the latest PR and complete changed-file inventory and publishes the `Startup Advisor author checklist` check on the PR's head commit.
Unrelated PRs receive a neutral check so they are not blocked if maintainers make the check required.
Incomplete inventories and API failures never authorize review.

The workflow uses `pull_request_target` so it can update reminders on fork PRs.
Only trusted base-branch code is checked out and executed by the job with write permissions; PR content is passed as data.
The separate test job runs the proposed code with read-only permissions.

If maintainers also want to block merging, they can add `Startup Advisor author checklist` as a required status check.
That repository setting is separate from the review entrypoint.
GitHub does not disable the manual review UI based on a custom checklist.

## Connect the automatic reviewer

The existing reviewer must be launched through the `review` entrypoint from a trusted checkout containing this change:

```sh
node .github/scripts/startup-advisor-pr-checklist.cjs review \
  aws/agent-toolkit-for-aws "$PR_NUMBER" "$EXPECTED_HEAD_SHA" \
  -- review-command argument
```

Replace `review-command argument` with the existing reviewer's executable and arguments.
The entrypoint requires Node.js and authenticated GitHub CLI read access.
It checks the live PR description, open/non-Draft state, complete plugin path scope, and expected head immediately before starting the command.
Missing confirmations, an API failure, or a stale head cause a nonzero exit without launching the reviewer.
The reviewed head is available to the command as `STARTUP_ADVISOR_REVIEW_HEAD`.
An allowed command's exit status is returned to the caller.

For reviewers with an existing dispatch process, use the read-only check as a mandatory precondition:

```sh
node .github/scripts/startup-advisor-pr-checklist.cjs check \
  aws/agent-toolkit-for-aws "$PR_NUMBER" "$EXPECTED_HEAD_SHA"
```

Only exit code 0 authorizes dispatch. Check again before publishing review results to stop publication if the author withdraws a confirmation while a review is running.
A previously green GitHub check is insufficient because the PR description can change without a new commit.
An already running review process is not terminated by the reminder workflow.

The current Codex coordinator runs outside this repository. Its launcher and publication preconditions must be connected to this check when this proposal is adopted.
The gate and its tests are provided here; merging the workflow alone does not configure that external coordinator.

## Validation

```sh
node --test .github/scripts/startup-advisor-pr-checklist.test.cjs
```

The tests cover missing, completed, removed, duplicated, and quoted confirmations; Draft transitions; renames; pagination; API failures; stale heads; reminder reuse; and the review entrypoint's refusal to launch without confirmation.
The repository workflow runs these tests when this template, script, tests, or workflow changes.
