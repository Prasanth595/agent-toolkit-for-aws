const { spawn } = require("node:child_process");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { text } = require("node:stream/consumers");

const CHECK_NAME = "Startup Advisor author checklist";
const COMMENT_MARKER = "<!-- startup-advisor-author-checklist -->";
const PLUGIN_PREFIX = "plugins/aws-startup-advisor/";
const TEMPLATE_PATH = ".github/PULL_REQUEST_TEMPLATE/startup-advisor.md";
const HEADING = "## Startup Advisor review checklist";
const TYPE_HEADING = "## Type of Change";

function htmlBlockEnd(line, paragraphOpen) {
  if (/^ {0,3}<(?:pre|script|style|textarea)(?=[ \t>]|$)/i.test(line)) {
    return /<\/(?:pre|script|style|textarea)>/i;
  }
  if (/^ {0,3}<!--/.test(line)) return /-->/;
  if (/^ {0,3}<\?/.test(line)) return /\?>/;
  if (/^ {0,3}<![A-Z]/.test(line)) return />/;
  if (/^ {0,3}<!\[CDATA\[/.test(line)) return /\]\]>/;
  if (/^ {0,3}<\/?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|source|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)(?=[ \t/>]|$)/i.test(line)) {
    return /^[ \t]*$/;
  }
  // Other complete HTML tags start a block only outside a paragraph.
  if (!paragraphOpen && /^ {0,3}(?:<\/[a-z][a-z0-9-]*[ \t]*>|<[a-z][a-z0-9-]*(?:[ \t]+[a-z_:][a-z0-9_.:-]*(?:[ \t]*=[ \t]*(?:[^ \t"'=<>`]+|'[^']*'|"[^"]*"))?)*[ \t]*\/?>)[ \t]*$/i.test(line)) {
    return /^[ \t]*$/;
  }
  return null;
}

function columnAfter(value, column = 0) {
  for (const character of value) column += character === "\t" ? 4 - column % 4 : 1;
  return column;
}

function checklistItems(markdown, heading = HEADING) {
  const items = [];
  let inSection = false;
  let fence = null;
  let htmlEnd = null;
  let paragraphOpen = false;
  let listItem = null;
  // Accept the template's top-level headings and single-line task items only.
  for (const line of (markdown || "").split(/\r\n|\r|\n/)) {
    if (fence) {
      const closing = line.match(/^ {0,3}(`{3,}|~{3,})[ \t]*$/);
      if (closing && closing[1][0] === fence[0] && closing[1].length >= fence.length) fence = null;
      continue;
    }
    if (htmlEnd) {
      if (htmlEnd.test(line)) htmlEnd = null;
      continue;
    }
    if (/^[ \t]*$/.test(line)) {
      if (listItem) listItem.separated = true;
      paragraphOpen = false;
      continue;
    }
    const opening = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    const opensFence = opening && (opening[1][0] === "~" || !opening[2].includes("`"));
    const isHeading = /^ {0,3}#{1,6}(?:[ \t]|$)/.test(line);
    const isDivider = /^ {0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$/.test(line);
    const marker = line.match(/^( {0,3})([-+*]|\d{1,9}[.)])([ \t]+|$)/);
    if (listItem) {
      const indent = columnAfter(line.match(/^[ \t]*/)[0]);
      const interrupts = isHeading || isDivider || marker || opensFence || /^ {0,3}>/.test(line) ||
        htmlBlockEnd(line, listItem.item ? true : paragraphOpen);
      if (indent >= listItem.indent || (!listItem.separated && !interrupts)) {
        if (listItem.item) listItem.item.continued = true;
        listItem.separated = false;
        continue;
      }
      listItem = null;
    }
    htmlEnd = htmlBlockEnd(line, paragraphOpen);
    if (htmlEnd) {
      paragraphOpen = false;
      if (htmlEnd.test(line)) htmlEnd = null;
      continue;
    }
    if (opensFence) {
      fence = opening[1];
      paragraphOpen = false;
      continue;
    }
    if (!paragraphOpen && /^(?: {4}|\t)/.test(line)) continue;
    if (isHeading) {
      if (line.trimEnd() === heading) inSection = true;
      else if (/^ {0,3}#{1,2}(?:[ \t]|$)/.test(line)) inSection = false;
      paragraphOpen = false;
      continue;
    }
    if (isDivider) {
      paragraphOpen = false;
      continue;
    }
    paragraphOpen = true;
    if (marker) {
      const markerEnd = marker[1].length + marker[2].length;
      const spacing = columnAfter(marker[3], markerEnd) - markerEnd;
      listItem = { indent: markerEnd + (spacing >= 1 && spacing <= 4 ? spacing : 1), separated: false };
      const item = inSection && line.match(/^- \[([ xX])\] (.+?)\s*$/);
      if (item) {
        listItem.item = { text: item[2], checked: item[1].toLowerCase() === "x", continued: false };
        items.push(listItem.item);
      }
      const content = line.slice(marker[0].length);
      const contentFence = content.match(/^(`{3,}|~{3,})(.*)$/);
      if ((contentFence && (contentFence[1][0] === "~" || !contentFence[2].includes("`"))) ||
          htmlBlockEnd(content, false)) paragraphOpen = false;
    }
  }
  return items;
}

function evaluate(pr, files, template) {
  const confirmations = checklistItems(template);
  const expected = confirmations.map((item) => item.text);
  if (expected.length !== 4 || new Set(expected).size !== expected.length || confirmations.some((item) => item.continued)) {
    throw new Error("The trusted template must contain four distinct single-line confirmations.");
  }
  const options = checklistItems(template, TYPE_HEADING);
  const changeTypes = options.map((item) => item.text);
  if (!changeTypes.length || new Set(changeTypes).size !== changeTypes.length || options.some((item) => item.continued)) {
    throw new Error("The trusted template must contain distinct single-line change type options.");
  }
  if (files.length !== pr.changed_files || new Set(files.map((file) => file.filename)).size !== files.length) {
    throw new Error("Incomplete PR file inventory; checklist requirements are unknown.");
  }
  const inScope = files.some((file) =>
    [file.filename, file.previous_filename].some((name) => name?.startsWith(PLUGIN_PREFIX)));
  const items = checklistItems(pr.body);
  const missing = expected.filter((text) => {
    const matches = items.filter((item) => item.text === text);
    return matches.length !== 1 || !matches[0].checked || matches[0].continued;
  });
  const changeTypeSelected = checklistItems(pr.body, TYPE_HEADING)
    .some((item) => item.checked && !item.continued && changeTypes.includes(item.text));
  return {
    number: pr.number,
    head: pr.head.sha,
    inScope,
    missing,
    changeTypeSelected,
    checklistComplete: changeTypeSelected && missing.length === 0,
  };
}

function unchanged(before, after) {
  return before.head.sha === after.head.sha && before.base.sha === after.base.sha &&
    before.state === after.state && before.draft === after.draft &&
    before.body === after.body && before.changed_files === after.changed_files;
}

async function githubApi(method, endpoint, body) {
  const args = ["api", "--method", method, endpoint];
  if (body !== undefined) args.push("--input", "-");
  const input = body === undefined ? undefined : JSON.stringify(body);
  const child = spawn("gh", args, { stdio: ["pipe", "pipe", "pipe"] });
  // Stream both pipes instead of imposing execFileSync's 1 MiB capture limit.
  const completion = new Promise((resolve, reject) => {
    child.once("error", reject);
    child.stdin.on("error", reject);
    child.once("close", (code, signal) => resolve({ code, signal }));
  });
  const output = Promise.all([text(child.stdout), text(child.stderr), completion]);
  child.stdin.end(input);
  const [stdout, stderr, { code, signal }] = await output;
  if (code !== 0) throw new Error(`gh api failed (${signal || code}): ${stderr.trim()}`);
  return JSON.parse(stdout);
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
  if (expectedHead && pr.head.sha !== expectedHead) throw new Error("PR head changed before checklist inspection.");
  const files = await pages(api, `${endpoint}/files`);
  const current = await api("GET", endpoint);
  if (!unchanged(pr, current)) throw new Error("PR changed during checklist inspection; retry with fresh data.");
  return { pr: current, result: evaluate(current, files, template) };
}

function reminder(repository, result) {
  const templateUrl = `https://github.com/${repository}/blob/main/${TEMPLATE_PATH}`;
  if (!result.inScope) {
    return `${COMMENT_MARKER}\nThis PR does not change Startup Advisor. Its author checklist is not required.`;
  }
  if (result.checklistComplete) {
    return `${COMMENT_MARKER}\nA change type is selected and all four Startup Advisor author confirmations are complete.\n\n` +
      "The author checklist check now passes. CI and reviewers still need to verify the change.";
  }
  const requiredUpdates = [
    ...(!result.changeTypeSelected ? ["Select at least one option under `Type of Change`."] : []),
    ...result.missing,
  ];
  return `${COMMENT_MARKER}\nThis PR changes Startup Advisor and is awaiting author confirmation.\n\n` +
    `Use [the Startup Advisor PR template](${templateUrl}) to update the following items in the PR description:\n\n` +
    requiredUpdates.map((text) => `- ${text}`).join("\n") +
    "\n\nSelect one or more change types. Keep all four author confirmations exactly once, with their original wording, and check every confirmation. " +
    "Paste the headings and checkbox lines without indentation, and keep each checkbox on one line. " +
    "Put notes in a separate unindented paragraph after a blank line. The check will run again when you update the description.";
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
        output: { title: "PR closed", summary: "This PR is closed; no author checklist is required." },
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
          result.checklistComplete ? "PR checklist complete" : "PR checklist incomplete",
        summary: body,
      },
    });
    return result;
  } catch (error) {
    await api("PATCH", `repos/${repository}/check-runs/${check.id}`, {
      status: "completed",
      conclusion: "failure",
      output: { title: "Checklist could not be verified", summary: error.message },
    });
    throw error;
  }
}

async function main() {
  const [repository, number, expectedHead, ...extra] = process.argv.slice(2);
  if (!/^[\w.-]+\/[\w.-]+$/.test(repository || "") || !/^[1-9]\d*$/.test(number || "") ||
      !/^[a-f0-9]{40}$/.test(expectedHead || "") || extra.length) {
    throw new Error("Usage: node startup-advisor-pr-checklist.cjs <owner/repo> <pr-number> <event-head>");
  }
  const template = readFileSync(resolve(__dirname, "../PULL_REQUEST_TEMPLATE/startup-advisor.md"), "utf8");
  const result = await notify(githubApi, repository, Number(number), template, expectedHead);
  console.log(JSON.stringify(result));
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

module.exports = { CHECK_NAME, COMMENT_MARKER, checklistItems, evaluate, inspect, notify };
