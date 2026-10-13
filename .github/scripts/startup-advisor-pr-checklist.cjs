const { execFileSync, spawnSync } = require("node:child_process");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");

const CHECK_NAME = "Startup Advisor author checklist";
const COMMENT_MARKER = "<!-- startup-advisor-author-checklist -->";
const PLUGIN_PREFIX = "plugins/aws-startup-advisor/";
const TEMPLATE_PATH = ".github/PULL_REQUEST_TEMPLATE/startup-advisor.md";
const HEADING = "## Startup Advisor review checklist";

function checklistItems(markdown) {
  const items = [];
  let inSection = false;
  let fence = null;
  for (const line of (markdown || "").replace(/<!--[\s\S]*?(?:-->|$)/g, "").split(/\r?\n/)) {
    const fenceMatch = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (fenceMatch) {
      if (!fence) fence = fenceMatch[1];
      else if (fenceMatch[1][0] === fence[0] && fenceMatch[1].length >= fence.length) fence = null;
      continue;
    }
    if (fence) continue;
    if (line.trim() === HEADING) {
      inSection = true;
      continue;
    }
    if (/^ {0,3}#{1,2}\s/.test(line)) inSection = false;
    const item = inSection && line.match(/^ {0,3}- \[([ xX])\] (.+?)\s*$/);
    if (item) items.push({ text: item[2], checked: item[1].toLowerCase() === "x" });
  }
  return items;
}

function evaluate(pr, files, template) {
  const expected = checklistItems(template).map((item) => item.text);
  if (expected.length !== 4 || new Set(expected).size !== expected.length) {
    throw new Error("The trusted template must contain four distinct confirmations.");
  }
  if (files.length !== pr.changed_files || new Set(files.map((file) => file.filename)).size !== files.length) {
    throw new Error("Incomplete PR file inventory; review readiness is unknown.");
  }
  const inScope = files.some((file) =>
    [file.filename, file.previous_filename].some((name) => name?.startsWith(PLUGIN_PREFIX)));
  const items = checklistItems(pr.body);
  const missing = expected.filter((text) => {
    const matches = items.filter((item) => item.text === text);
    return matches.length !== 1 || !matches[0].checked;
  });
  return {
    number: pr.number,
    head: pr.head.sha,
    inScope,
    missing,
    checklistComplete: missing.length === 0,
    reviewReady: inScope && pr.state === "open" && !pr.draft && missing.length === 0,
  };
}

function unchanged(before, after) {
  return before.head.sha === after.head.sha && before.base.sha === after.base.sha &&
    before.state === after.state && before.draft === after.draft &&
    before.body === after.body && before.changed_files === after.changed_files;
}

function githubApi(method, endpoint, body) {
  const args = ["api", "--method", method, endpoint];
  if (body !== undefined) args.push("--input", "-");
  return JSON.parse(execFileSync("gh", args, {
    encoding: "utf8",
    input: body === undefined ? undefined : JSON.stringify(body),
    stdio: ["pipe", "pipe", "pipe"],
  }));
}

async function pages(api, endpoint) {
  const results = [];
  for (let page = 1; ; page++) {
    const rows = await api("GET", `${endpoint}?per_page=100&page=${page}`);
    results.push(...rows);
    if (rows.length < 100) return results;
  }
}

async function inspect(api, repository, number, template, expectedHead) {
  const endpoint = `repos/${repository}/pulls/${number}`;
  const pr = await api("GET", endpoint);
  if (expectedHead && pr.head.sha !== expectedHead) throw new Error("PR head changed before the review gate.");
  const files = await pages(api, `${endpoint}/files`);
  const current = await api("GET", endpoint);
  if (!unchanged(pr, current)) throw new Error("PR changed during the review gate; retry with fresh data.");
  return { pr: current, result: evaluate(current, files, template) };
}

async function startReview(api, repository, number, template, expectedHead, launch) {
  if (!/^[a-f0-9]{40}$/.test(expectedHead || "")) throw new Error("Review requires an expected commit SHA.");
  const { result } = await inspect(api, repository, number, template, expectedHead);
  if (!result.reviewReady) return { ...result, exitCode: 1 };
  return { ...result, exitCode: await launch(result.head) };
}

function reminder(repository, result) {
  const templateUrl = `https://github.com/${repository}/blob/main/${TEMPLATE_PATH}`;
  if (!result.inScope) {
    return `${COMMENT_MARKER}\nThis PR does not change Startup Advisor. Its author checklist is not required.`;
  }
  if (result.checklistComplete) {
    return `${COMMENT_MARKER}\nAll four Startup Advisor author confirmations are complete.\n\n` +
      (result.reviewReady
        ? "This PR is eligible for the review queue. CI and reviewers still need to verify the change."
        : "This PR is still a draft. Mark it ready for review when you want review to start.");
  }
  return `${COMMENT_MARKER}\nThis PR changes Startup Advisor and is awaiting author confirmation.\n\n` +
    `Add the checklist from [the Startup Advisor PR template](${templateUrl}) to the PR description, ` +
    "then complete the following confirmations there:\n\n" +
    result.missing.map((text) => `- ${text}`).join("\n") +
    "\n\nAutomatic review must wait until these confirmations are complete and the PR is ready for review.";
}

async function notify(api, repository, number, template, expectedHead) {
  if (!/^[a-f0-9]{40}$/.test(expectedHead || "")) throw new Error("Notification requires the event's head SHA.");
  const check = await api("POST", `repos/${repository}/check-runs`, {
    name: CHECK_NAME,
    head_sha: expectedHead,
    status: "in_progress",
    external_id: `startup-advisor-checklist-${number}`,
  });
  try {
    const { pr, result } = await inspect(api, repository, number, template, expectedHead);
    if (pr.state !== "open") {
      await api("PATCH", `repos/${repository}/check-runs/${check.id}`, {
        status: "completed",
        conclusion: "neutral",
        output: { title: "PR closed", summary: "This PR is closed and is not eligible for review." },
      });
      return result;
    }
    const comments = await pages(api, `repos/${repository}/issues/${number}/comments`);
    const existing = comments.find((comment) =>
      comment.user?.login === "github-actions[bot]" &&
      comment.user?.type === "Bot" && comment.body?.startsWith(COMMENT_MARKER));
    const current = await api("GET", `repos/${repository}/pulls/${number}`);
    if (!unchanged(pr, current)) throw new Error("PR changed before the reminder; retry with fresh data.");
    const body = reminder(repository, result);
    if (existing && existing.body !== body) {
      await api("PATCH", `repos/${repository}/issues/comments/${existing.id}`, { body });
    } else if (!existing && result.inScope && !result.checklistComplete) {
      await api("POST", `repos/${repository}/issues/${number}/comments`, { body });
    }
    const finalPr = await api("GET", `repos/${repository}/pulls/${number}`);
    if (!unchanged(pr, finalPr)) throw new Error("PR changed before the check completed; retry with fresh data.");
    await api("PATCH", `repos/${repository}/check-runs/${check.id}`, {
      status: "completed",
      conclusion: !result.inScope ? "neutral" : result.checklistComplete ? "success" : "failure",
      output: {
        title: !result.inScope ? "Startup Advisor checklist not required" :
          result.checklistComplete ? "Author confirmations complete" : "Awaiting author confirmation",
        summary: body,
      },
    });
    return result;
  } catch (error) {
    await api("PATCH", `repos/${repository}/check-runs/${check.id}`, {
      status: "completed",
      conclusion: "failure",
      output: { title: "Readiness could not be verified", summary: error.message },
    });
    throw error;
  }
}

async function main() {
  const [mode, repository, number, expectedHead, separator, ...command] = process.argv.slice(2);
  if (!["check", "notify", "review"].includes(mode) || !/^[\w.-]+\/[\w.-]+$/.test(repository || "") ||
      !/^[1-9]\d*$/.test(number || "") || (expectedHead && !/^[a-f0-9]{40}$/.test(expectedHead)) ||
      (mode === "notify" && !expectedHead) ||
      (mode === "review" && (!expectedHead || separator !== "--" || !command.length)) ||
      (mode !== "review" && separator !== undefined)) {
    throw new Error("Usage: node startup-advisor-pr-checklist.cjs check <owner/repo> <pr-number> [expected-head]\n" +
      "       node startup-advisor-pr-checklist.cjs notify <owner/repo> <pr-number> <event-head>\n" +
      "       node startup-advisor-pr-checklist.cjs review <owner/repo> <pr-number> <expected-head> -- <command> [args...]");
  }
  const template = readFileSync(resolve(__dirname, "../PULL_REQUEST_TEMPLATE/startup-advisor.md"), "utf8");
  if (mode === "review") {
    const result = await startReview(githubApi, repository, Number(number), template, expectedHead, (head) => {
      const child = spawnSync(command[0], command.slice(1), {
        stdio: "inherit",
        env: { ...process.env, STARTUP_ADVISOR_REVIEW_HEAD: head },
      });
      if (child.error) throw child.error;
      return child.status ?? 1;
    });
    console.log(JSON.stringify(result));
    process.exitCode = result.exitCode;
    return;
  }
  const result = mode === "notify"
    ? await notify(githubApi, repository, Number(number), template, expectedHead)
    : (await inspect(githubApi, repository, Number(number), template, expectedHead)).result;
  console.log(JSON.stringify(result));
  if (mode === "check" && !result.reviewReady) process.exitCode = 1;
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

module.exports = { CHECK_NAME, COMMENT_MARKER, checklistItems, evaluate, inspect, startReview, notify };
