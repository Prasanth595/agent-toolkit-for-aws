const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const test = require("node:test");
const { COMMENT_MARKER, checklistItems, evaluate, inspect, notify: runNotify } = require("./startup-advisor-pr-checklist.cjs");

const template = readFileSync(resolve(__dirname, "../PULL_REQUEST_TEMPLATE/startup-advisor.md"), "utf8");
const [typeSection, confirmationSection] = template.split("## Startup Advisor review checklist");
const complete = typeSection.replace("- [ ] Bug fix", "- [x] Bug fix") +
  "## Startup Advisor review checklist" + confirmationSection.replaceAll("- [ ]", "- [x]");
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
  assert.equal(evaluate(pull(), [pluginFile], template).checklistComplete, true);
  for (const body of [null, "", template, complete.replace("## Startup Advisor review checklist", "## Other")]) {
    assert.equal(evaluate(pull({ body }), [pluginFile], template).checklistComplete, false);
  }
  for (const item of checklistItems(template)) {
    const checkedLine = `- [x] ${item.text}`;
    for (const body of [
      complete.replace(checkedLine, ""),
      complete.replace(checkedLine, checkedLine.replace("[x]", "[ ]")),
      complete.replace(checkedLine, `${checkedLine}\n${checkedLine}`),
      complete.replace(checkedLine, `${checkedLine} (changed text)`),
    ]) {
      assert.equal(evaluate(pull({ body }), [pluginFile], template).checklistComplete, false);
    }
  }
});

test("one or multiple change types pass without selecting every type", () => {
  for (const body of [complete, complete.replace("- [ ] Documentation update", "- [x] Documentation update")]) {
    const result = evaluate(pull({ body }), [pluginFile], template);
    assert.equal(result.changeTypeSelected, true);
    assert.equal(result.checklistComplete, true);
    assert.ok(body.includes("- [ ] New skill"));
  }
  const body = complete.replace("- [x] Bug fix", "- [ ] Bug fix");
  const result = evaluate(pull({ body }), [pluginFile], template);
  assert.equal(result.changeTypeSelected, false);
  assert.equal(result.checklistComplete, false);
  assert.deepEqual(result.missing, []);
});

test("a change type must be a recognized option in its own visible section", () => {
  const confirmations = complete.slice(complete.indexOf("## Startup Advisor review checklist"));
  const selectedTypes = complete.slice(0, complete.indexOf("## Startup Advisor review checklist"));
  for (const body of [
    confirmations,
    complete.replace("## Type of Change", "## Other section"),
    complete.replace("- [x] Bug fix", "- [x] Unknown type"),
    `\`\`\`markdown\n${selectedTypes}\n\`\`\`\n${confirmations}`,
    `<!--\n${selectedTypes}\n-->\n${confirmations}`,
    selectedTypes.split("\n").map((line) => `> ${line}`).join("\n") + "\n" + confirmations,
  ]) {
    const result = evaluate(pull({ body }), [pluginFile], template);
    assert.equal(result.changeTypeSelected, false);
    assert.equal(result.checklistComplete, false);
  }
});

test("selecting every change type does not satisfy unchecked author confirmations", () => {
  const body = typeSection.replaceAll("- [ ]", "- [x]") +
    "## Startup Advisor review checklist" + confirmationSection;
  const result = evaluate(pull({ body }), [pluginFile], template);
  assert.equal(result.changeTypeSelected, true);
  assert.equal(result.checklistComplete, false);
  assert.equal(result.missing.length, 4);
});

test("accepts uppercase checks and CRLF, but excludes quoted, fenced, and commented examples", () => {
  assert.equal(evaluate(pull({ body: complete.replaceAll("[x]", "[X]").replaceAll("\n", "\r\n") }),
    [pluginFile], template).checklistComplete, true);
  for (const body of [
    `\`\`\`markdown\n${complete}\n\`\`\``,
    `~~~markdown\n${complete}\n~~~`,
    `<!--\n${complete}\n-->`,
    `<!--\n${complete}`,
    complete.split("\n").map((line) => `> ${line}`).join("\n"),
  ]) {
    assert.equal(evaluate(pull({ body }), [pluginFile], template).checklistComplete, false);
  }
});

test("the default template fails, but adding our completed checklist to it passes", () => {
  const defaultTemplate = readFileSync(resolve(__dirname, "../pull_request_template.md"), "utf8")
    .replaceAll("- [ ]", "- [x]");
  assert.equal(evaluate(pull({ body: defaultTemplate }), [pluginFile], template).checklistComplete, false);
  const section = complete.slice(complete.indexOf("## Startup Advisor review checklist")).split("\n\n*By submitting")[0];
  const body = `${defaultTemplate}\n\n${section}\n\n## Additional context\nCustom author content.\n`;
  assert.equal(evaluate(pull({ body }), [pluginFile], template).checklistComplete, true);
});

test("includes deletions, mixed PRs, and renames into or out of the plugin", () => {
  for (const files of [
    [{ ...pluginFile, status: "removed" }],
    [{ filename: "README.md" }, pluginFile],
    [{ filename: "docs/moved.md", previous_filename: pluginFile.filename }],
    [{ ...pluginFile, previous_filename: "docs/moved.md" }],
  ]) {
    assert.equal(evaluate(pull({ changed_files: files.length }), files, template).inScope, true);
  }
  for (const filename of ["README.md", "plugins/another/README.md", "plugins/aws-startup-advisor-copy/README.md"]) {
    assert.equal(evaluate(pull(), [{ filename }], template).inScope, false);
  }
});

test("incomplete inventories and broken trusted templates fail closed", () => {
  assert.throws(() => evaluate(pull({ changed_files: 2 }), [pluginFile], template), /Incomplete/);
  assert.throws(() => evaluate(pull({ changed_files: 2 }), [pluginFile, pluginFile], template), /Incomplete/);
  assert.throws(() => evaluate(pull(), [pluginFile], ""), /four distinct/);
  assert.throws(() => evaluate(pull(), [pluginFile], template.replace("## Type of Change", "## Other")), /change type/);
});

test("checklist inspection paginates and checks the expected head", async () => {
  const files = Array.from({ length: 100 }, (_, i) => ({ filename: `docs/${i}.md` })).concat(pluginFile);
  const f = fixture({ pr: pull({ changed_files: files.length }), files });
  const { result } = await inspect(f.api, repository, 42, template, "a".repeat(40));
  assert.equal(result.inScope, true);
  assert.equal(result.checklistComplete, true);
  assert.deepEqual(f.writes, []);
  await assert.rejects(inspect(f.api, repository, 42, template, "c".repeat(40)), /head changed/);
});

test("API errors and edits during inventory inspection cannot produce a checklist result", async () => {
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
    outcomes.push(result.checklistComplete);
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

test("a missing change type gets a targeted reminder that clears after selection", async () => {
  const f = fixture({ pr: pull({ body: complete.replace("- [x] Bug fix", "- [ ] Bug fix") }) });
  await notify(f.api, repository, 42, template);
  assert.equal(f.writes.at(-1).body.conclusion, "failure");
  assert.match(f.comments[0].body, /Select at least one option under `Type of Change`/);
  assert.ok(!f.comments[0].body.includes("- I have reviewed"));
  f.pr.body = complete;
  await notify(f.api, repository, 42, template);
  assert.equal(f.writes.at(-1).body.conclusion, "success");
  assert.equal(f.comments.length, 1);
  assert.match(f.comments[0].body, /A change type is selected/);
  f.pr.body = complete.replace("- [x] Bug fix", "- [ ] Bug fix");
  await notify(f.api, repository, 42, template);
  assert.equal(f.writes.at(-1).body.conclusion, "failure");
  assert.equal(f.comments.length, 1);
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

test("the checklist check behaves the same for Draft and ready PRs", async () => {
  const f = fixture({ pr: pull({ draft: true, body: template }) });
  await notify(f.api, repository, 42, template);
  f.pr.body = complete;
  const result = await notify(f.api, repository, 42, template);
  assert.equal(result.checklistComplete, true);
  assert.equal(f.writes.at(-1).body.conclusion, "success");
  const completedReminder = f.comments[0].body;
  f.pr.draft = false;
  assert.equal((await notify(f.api, repository, 42, template)).checklistComplete, true);
  assert.equal(f.comments[0].body, completedReminder);
});
