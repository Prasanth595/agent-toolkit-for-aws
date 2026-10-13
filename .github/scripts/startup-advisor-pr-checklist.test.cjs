const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { resolve } = require("node:path");
const test = require("node:test");
const { COMMENT_MARKER, checklistItems, evaluate, inspect, startReview, notify: runNotify } = require("./startup-advisor-pr-checklist.cjs");

const template = readFileSync(resolve(__dirname, "../PULL_REQUEST_TEMPLATE/startup-advisor.md"), "utf8");
const complete = template.replaceAll("- [ ]", "- [x]");
const pluginFile = { filename: "plugins/aws-startup-advisor/README.md" };
const repository = "example/toolkit";
const pullEndpoint = `repos/${repository}/pulls/42`;
const notify = (...args) => runNotify(...args, "a".repeat(40));

function pull(overrides = {}) {
  return {
    number: 42, head: { sha: "a".repeat(40) }, base: { sha: "b".repeat(40) },
    state: "open", draft: false, body: complete, changed_files: 1, ...overrides,
  };
}

function fixture({ pr = pull(), files = [pluginFile], comments = [], mutate } = {}) {
  const writes = [];
  let reads = 0;
  const api = async (method, endpoint, body) => {
    if (method !== "GET") {
      writes.push({ method, endpoint, body });
      if (endpoint.endsWith("/check-runs") && method === "POST") return { id: 11 };
      if (endpoint.endsWith("/comments") && method === "POST") {
        comments.push({ id: 12, body: body.body, user: { login: "github-actions[bot]", type: "Bot" } });
      } else if (endpoint.includes("/issues/comments/") && method === "PATCH") {
        comments.find((comment) => endpoint.endsWith(`/${comment.id}`)).body = body.body;
      }
      return {};
    }
    if (endpoint === pullEndpoint) {
      reads++;
      if (mutate) mutate(pr, reads);
      return structuredClone(pr);
    }
    const page = Number(new URL(`https://api.github.com/${endpoint}`).searchParams.get("page"));
    if (endpoint.startsWith(`${pullEndpoint}/files?`)) return files.slice((page - 1) * 100, page * 100);
    if (endpoint.includes("/comments?")) return comments.slice((page - 1) * 100, page * 100);
    throw new Error(`Unexpected API request: ${method} ${endpoint}`);
  };
  return { api, pr, files, comments, writes };
}

test("requires the four confirmations in the dedicated section", () => {
  assert.equal(evaluate(pull(), [pluginFile], template).reviewReady, true);
  for (const body of [null, "", template, complete.replace("## Startup Advisor review checklist", "## Other")]) {
    assert.equal(evaluate(pull({ body }), [pluginFile], template).reviewReady, false);
  }
  for (const item of checklistItems(template)) {
    const checkedLine = `- [x] ${item.text}`;
    for (const body of [
      complete.replace(checkedLine, ""),
      complete.replace(checkedLine, checkedLine.replace("[x]", "[ ]")),
      complete.replace(checkedLine, `${checkedLine}\n${checkedLine}`),
      complete.replace(checkedLine, `${checkedLine} (changed text)`),
    ]) {
      assert.equal(evaluate(pull({ body }), [pluginFile], template).reviewReady, false);
    }
  }
});

test("accepts uppercase checks and CRLF, but excludes quoted, fenced, and commented examples", () => {
  assert.equal(evaluate(pull({ body: complete.replaceAll("[x]", "[X]").replaceAll("\n", "\r\n") }),
    [pluginFile], template).reviewReady, true);
  for (const body of [
    `\`\`\`markdown\n${complete}\n\`\`\``,
    `~~~markdown\n${complete}\n~~~`,
    `<!--\n${complete}\n-->`,
    `<!--\n${complete}`,
    complete.split("\n").map((line) => `> ${line}`).join("\n"),
  ]) {
    assert.equal(evaluate(pull({ body }), [pluginFile], template).reviewReady, false);
  }
});

test("Draft and closed PRs never pass the review gate even with all confirmations", () => {
  assert.equal(evaluate(pull({ draft: true }), [pluginFile], template).reviewReady, false);
  assert.equal(evaluate(pull({ state: "closed" }), [pluginFile], template).reviewReady, false);
});

test("includes deletions, mixed PRs, and renames into or out of the plugin", () => {
  for (const files of [
    [{ ...pluginFile, status: "removed" }],
    [{ filename: "README.md" }, pluginFile],
    [{ filename: "docs/moved.md", previous_filename: pluginFile.filename }],
    [{ ...pluginFile, previous_filename: "docs/moved.md" }],
  ]) {
    assert.equal(evaluate(pull({ changed_files: files.length }), files, template).reviewReady, true);
  }
  for (const filename of ["README.md", "plugins/another/README.md", "plugins/aws-startup-advisor-copy/README.md"]) {
    assert.equal(evaluate(pull(), [{ filename }], template).inScope, false);
  }
});

test("incomplete inventories and broken trusted templates fail closed", () => {
  assert.throws(() => evaluate(pull({ changed_files: 2 }), [pluginFile], template), /Incomplete/);
  assert.throws(() => evaluate(pull({ changed_files: 2 }), [pluginFile, pluginFile], template), /Incomplete/);
  assert.throws(() => evaluate(pull(), [pluginFile], ""), /four distinct/);
});

test("the read-only review gate paginates and checks the expected head", async () => {
  const files = Array.from({ length: 100 }, (_, i) => ({ filename: `docs/${i}.md` })).concat(pluginFile);
  const f = fixture({ pr: pull({ changed_files: files.length }), files });
  const { result } = await inspect(f.api, repository, 42, template, "a".repeat(40));
  assert.equal(result.reviewReady, true);
  assert.deepEqual(f.writes, []);
  await assert.rejects(inspect(f.api, repository, 42, template, "c".repeat(40)), /head changed/);
});

test("API errors and edits during inventory inspection cannot authorize review", async () => {
  await assert.rejects(inspect(async () => { throw new Error("API unavailable"); },
    repository, 42, template), /API unavailable/);
  for (const change of [
    (pr) => { pr.body = template; },
    (pr) => { pr.head.sha = "c".repeat(40); },
    (pr) => { pr.base.sha = "c".repeat(40); },
    (pr) => { pr.draft = true; },
    (pr) => { pr.state = "closed"; },
  ]) {
    const f = fixture({ mutate: (pr, reads) => { if (reads === 2) change(pr); } });
    await assert.rejects(inspect(f.api, repository, 42, template), /changed during/);
    assert.deepEqual(f.writes, []);
  }
});

test("the review entrypoint never launches a reviewer before author confirmation", async () => {
  for (const overrides of [{ body: null }, { body: template }, { draft: true }, { state: "closed" }]) {
    const f = fixture({ pr: pull(overrides) });
    let launches = 0;
    const result = await startReview(f.api, repository, 42, template, "a".repeat(40), () => { launches++; });
    assert.equal(result.exitCode, 1);
    assert.equal(launches, 0);
    assert.deepEqual(f.writes, []);
  }
});

test("the review entrypoint launches only the checked head and propagates the review result", async () => {
  const f = fixture();
  const launchedHeads = [];
  const result = await startReview(f.api, repository, 42, template, "a".repeat(40), (head) => {
    launchedHeads.push(head);
    return 7;
  });
  assert.deepEqual(launchedHeads, ["a".repeat(40)]);
  assert.equal(result.exitCode, 7);
  for (const head of [undefined, "c".repeat(40)]) {
    await assert.rejects(startReview(f.api, repository, 42, template, head, () => {
      assert.fail("The reviewer must not start for an unknown or stale head.");
    }));
  }
});

test("the CLI starts a real child process only after the checklist passes", () => {
  const directory = mkdtempSync(resolve(tmpdir(), "startup-advisor-checklist-"));
  try {
    const gh = resolve(directory, "gh");
    writeFileSync(gh, `#!/usr/bin/env node
const fixture = JSON.parse(process.env.CHECKLIST_TEST_FIXTURE);
console.log(JSON.stringify(process.argv.at(-1).includes("/files?") ? fixture.files : fixture.pr));
`, { mode: 0o755 });
    for (const [index, pr] of [pull({ body: template }), pull(), pull({ draft: true })].entries()) {
      const marker = resolve(directory, `review-${index}`);
      const child = spawnSync(process.execPath, [
        resolve(__dirname, "startup-advisor-pr-checklist.cjs"), "review", repository, "42", "a".repeat(40),
        "--", process.execPath, "-e", "require('node:fs').writeFileSync(process.argv[1], 'started')", marker,
      ], {
        encoding: "utf8",
        env: {
          ...process.env,
          PATH: `${directory}:${process.env.PATH}`,
          CHECKLIST_TEST_FIXTURE: JSON.stringify({ pr, files: [pluginFile] }),
        },
      });
      assert.equal(child.status, index === 1 ? 0 : 1, child.stderr);
      assert.equal(existsSync(marker), index === 1);
      assert.equal(JSON.parse(child.stdout).reviewReady, index === 1);
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("unrelated and closed PRs get a neutral check and no reminder", async () => {
  const unrelated = fixture({ files: [{ filename: "README.md" }] });
  await notify(unrelated.api, repository, 42, template);
  assert.deepEqual(unrelated.comments, []);
  assert.equal(unrelated.writes.at(-1).body.conclusion, "neutral");
  const closed = fixture({ pr: pull({ state: "closed", body: template }) });
  await notify(closed.api, repository, 42, template);
  assert.deepEqual(closed.comments, []);
  assert.equal(closed.writes.at(-1).body.conclusion, "neutral");
});

test("a failed inventory or stale event completes a failing check instead of leaving an old success", async () => {
  for (const pr of [pull({ changed_files: 2 }), pull({ head: { sha: "c".repeat(40) } })]) {
    const f = fixture({ pr });
    await assert.rejects(notify(f.api, repository, 42, template));
    assert.equal(f.writes[0].body.status, "in_progress");
    assert.equal(f.writes[0].body.head_sha, "a".repeat(40));
    assert.equal(f.writes.at(-1).body.conclusion, "failure");
    assert.deepEqual(f.comments, []);
  }
});
test("removing the plugin from a PR clears its previous reminder and blocking check", async () => {
  const f = fixture({ pr: pull({ body: template }) });
  await notify(f.api, repository, 42, template);
  f.files[0] = { filename: "README.md" };
  const result = await notify(f.api, repository, 42, template);
  assert.equal(result.inScope, false);
  assert.equal(f.writes.at(-1).body.conclusion, "neutral");
  assert.equal(f.comments.length, 1);
  assert.match(f.comments[0].body, /checklist is not required/);
});
test("unchecked -> checked -> unchecked updates one reminder and the check outcome", async () => {
  const f = fixture({ pr: pull({ body: template }) });
  const outcomes = [];
  for (const body of [template, template, complete, template]) {
    f.pr.body = body;
    const result = await notify(f.api, repository, 42, template);
    outcomes.push(result.reviewReady);
  }
  assert.deepEqual(outcomes, [false, false, true, false]);
  assert.equal(f.comments.length, 1);
  assert.equal(f.writes.filter((write) => write.method === "POST" && write.endpoint.endsWith("/comments")).length, 1);
  assert.equal(f.writes.filter((write) => write.method === "PATCH" && write.endpoint.includes("/issues/comments/")).length, 2);
  assert.deepEqual(f.writes.filter((write) => write.body.conclusion).map((write) => write.body.conclusion),
    ["failure", "failure", "success", "failure"]);
  assert.match(f.comments[0].body, /awaiting author confirmation/);
});

test("a completed checklist does not publish an unsolicited success comment", async () => {
  const f = fixture();
  await notify(f.api, repository, 42, template);
  assert.deepEqual(f.comments, []);
  assert.equal(f.writes.at(-1).body.conclusion, "success");
});

test("only updates our GitHub Actions reminder, including on later comment pages", async () => {
  const comments = Array.from({ length: 100 }, (_, i) =>
    ({ id: i + 100, body: "Unrelated", user: { login: "person", type: "User" } }));
  comments[0].body = `${COMMENT_MARKER}\nCopied marker`;
  comments.push({ id: 999, body: `${COMMENT_MARKER}\nOld reminder`, user: { login: "github-actions[bot]", type: "Bot" } });
  const f = fixture({ comments, pr: pull({ body: template }) });
  await notify(f.api, repository, 42, template);
  const edits = f.writes.filter((write) => write.endpoint.includes("/issues/comments/"));
  assert.equal(edits.length, 1);
  assert.ok(edits[0].endpoint.endsWith("/999"));
});

test("a mid-run edit fails the check instead of publishing a stale success", async () => {
  for (const editOnRead of [3, 4]) {
    const f = fixture({ mutate: (pr, reads) => { if (reads === editOnRead) pr.body = template; } });
    await assert.rejects(notify(f.api, repository, 42, template), /PR changed/);
    assert.equal(f.writes.at(-1).body.conclusion, "failure");
    assert.ok(f.writes.every((write) => write.body.conclusion !== "success"));
  }
});

test("draft confirmations pass the checklist check but keep review blocked", async () => {
  const f = fixture({ pr: pull({ draft: true, body: template }) });
  await notify(f.api, repository, 42, template);
  f.pr.body = complete;
  const result = await notify(f.api, repository, 42, template);
  assert.equal(result.checklistComplete, true);
  assert.equal(result.reviewReady, false);
  assert.match(f.comments[0].body, /still a draft/);
  f.pr.draft = false;
  assert.equal((await notify(f.api, repository, 42, template)).reviewReady, true);
  assert.match(f.comments[0].body, /eligible for the review queue/);
});
