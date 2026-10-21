"""Tests for the secret-safety PreToolUse hook and the two hooks.json files that wire it.

The script is run as a subprocess with a JSON payload on stdin, the way every host
runs it. The Claude Code cases pin the existing protocol; the Devin cases cover the
plugin-root hooks.json, which only Devin reads.

Run: ``python3 -m unittest discover -s plugins/aws-core/tests -v``
"""

import json
import os
import re
import subprocess  # nosec B404 — test-only, inputs are hardcoded literals
import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PLUGIN_ROOT / "com.anthropic.claude-code" / "hooks" / "secret-safety.py"
CLAUDE_HOOKS_JSON = PLUGIN_ROOT / "com.anthropic.claude-code" / "hooks" / "hooks.json"
DEVIN_HOOKS_JSON = PLUGIN_ROOT / "hooks.json"

DENY_MSG = (
    "Direct secret fetching is blocked. "
    "Use {{resolve:secretsmanager:secret-id:SecretString:key}} with asm-exec instead. "
    "Run /aws-secrets-manager for details."
)
CLAUDE_DENY = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": DENY_MSG,
    }
}
DEVIN_BLOCK = {"decision": "block", "reason": DENY_MSG}

GSV_CLI = "aws secretsmanager get-secret-value --secret-id prod/db"
GSV_CLI_FLAGS = "aws --region us-east-1 secretsmanager get-secret-value --secret-id prod/db"
BATCH_GSV_CLI = "aws secretsmanager batch-get-secret-value --secret-id-list a b"
SMA_CURL = "curl -H 'X-Aws-Parameters-Secrets-Token: t' localhost:2773/secretsmanager/get?secretId=prod/db"
INLINE_SDK = "python3 -c \"import boto3; print(boto3.client('secretsmanager').get_secret_value(SecretId='x'))\""
HEREDOC_SDK = "python3 <<'EOF'\nimport boto3\nboto3.client('secretsmanager').get_secret_value(SecretId='x')\nEOF"
CHAINED = "grep -rn foo . && " + GSV_CLI
CHAINED_SDK = "grep x . && " + INLINE_SDK


def run_script(payload, *args):
    return subprocess.run(  # nosec B603 — fixed interpreter and script path
        [sys.executable, str(SCRIPT), *args],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


def payload(tool_name, tool_input, host="claude"):
    data = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    if host == "devin":
        # Shape documented at docs.devin.ai/cli/extensibility/hooks/overview#command-hooks.
        data.update(session_id="3f8d1c2a", prompt_id="b71e9d40")
    else:
        data.update(session_id="abc", transcript_path="/tmp/t.jsonl", cwd="/tmp", permission_mode="default")
    return data


class HookAssertions(unittest.TestCase):
    def assertDecision(self, result, expected):
        self.assertEqual(result.returncode, 0, result.stderr)
        if expected is None:
            self.assertEqual(result.stdout, "")
        else:
            self.assertEqual(json.loads(result.stdout), expected)


class TestClaudeProtocol(HookAssertions):
    """Existing behaviour under Claude Code (and Codex, which shares its hooks.json)."""

    DENIED = [
        ("Bash", {"command": GSV_CLI}),
        ("Bash", {"command": GSV_CLI_FLAGS}),
        ("Bash", {"command": BATCH_GSV_CLI}),
        ("Bash", {"command": SMA_CURL}),
        ("Bash", {"command": INLINE_SDK}),
        ("Bash", {"command": HEREDOC_SDK}),
        ("Bash", {"command": CHAINED}),
        ("Bash", {"command": CHAINED_SDK}),
        ("use_aws", {"service_name": "secretsmanager", "operation_name": "get-secret-value"}),
        ("mcp__aws-mcp__aws___call_aws", {"service": "secretsmanager", "operation": "GetSecretValue"}),
        ("mcp__plugin_aws-core_aws-mcp__call_aws", {"cli_command": GSV_CLI}),
        ("mcp__aws-mcp__call_aws", {"cli_command": BATCH_GSV_CLI}),
        ("mcp__aws-mcp__run_script", {"code": "boto3.client('secretsmanager').get_secret_value(SecretId='x')"}),
        ("aws_run_script", {"code": "client.get_secret_value(SecretId='x')"}),
    ]

    ALLOWED = [
        ("Bash", {"command": "aws secretsmanager list-secrets"}),
        ("Bash", {"command": "aws secretsmanager describe-secret --secret-id prod/db"}),
        ("Bash", {"command": "grep -rn get-secret-value ."}),
        ("Bash", {"command": "cat notes.md"}),
        ("Bash", {"command": "ls -la"}),
        ("use_aws", {"service_name": "secretsmanager", "operation_name": "describe-secret"}),
        ("mcp__plugin_aws-core_aws-mcp__call_aws", {"cli_command": "aws secretsmanager list-secrets"}),
        ("Read", {"file_path": "/tmp/get-secret-value.txt"}),
        # Devin tool names mean nothing to the Claude protocol.
        ("exec", {"command": GSV_CLI}),
        ("mcp_call_tool", {"server_name": "aws-mcp", "tool_name": "call_aws", "arguments": {"cli_command": GSV_CLI}}),
    ]

    def test_denied(self):
        for tool_name, tool_input in self.DENIED:
            with self.subTest(tool_name=tool_name, tool_input=tool_input):
                self.assertDecision(run_script(payload(tool_name, tool_input)), CLAUDE_DENY)

    def test_allowed(self):
        for tool_name, tool_input in self.ALLOWED:
            with self.subTest(tool_name=tool_name, tool_input=tool_input):
                self.assertDecision(run_script(payload(tool_name, tool_input)), None)


class TestDevinProtocol(HookAssertions):
    """The same policy under Devin's tool names and output format."""

    DENIED = [
        ("exec", {"command": GSV_CLI, "shell_id": "main"}),
        ("exec", {"command": GSV_CLI_FLAGS}),
        ("exec", {"command": BATCH_GSV_CLI}),
        ("exec", {"command": SMA_CURL}),
        ("exec", {"command": INLINE_SDK}),
        ("exec", {"command": HEREDOC_SDK}),
        ("exec", {"command": CHAINED}),
        ("exec", {"command": CHAINED_SDK}),
        ("shell_command", {"command": GSV_CLI}),
        ("shell_command", {"command": ["bash", "-lc", GSV_CLI]}),
        ("write_to_process", {"shell_id": "main", "text_input": GSV_CLI + "\n"}),
        ("write_to_process", {"shell_id": "main", "bytes_input": GSV_CLI + "<CR>"}),
        ("write_to_process", {"shell_id": "main", "bytes_input": INLINE_SDK + "<CR>"}),
        ("write_to_process", {"shell_id": "main", "bytes_input": SMA_CURL + "<LF>"}),
        ("mcp__aws-mcp__call_aws", {"cli_command": GSV_CLI}),
        ("mcp__aws-mcp__call_aws", {"service": "secretsmanager", "operation": "BatchGetSecretValue"}),
        ("mcp_call_tool", {"server_name": "aws-mcp", "tool_name": "call_aws", "arguments": {"cli_command": GSV_CLI}}),
        ("mcp_call_tool", {"server_name": "aws-mcp", "tool_name": "call_aws",
                           "arguments": json.dumps({"cli_command": GSV_CLI})}),
        ("mcp_call_tool", {"server_name": "aws-mcp", "tool_name": "call_aws",
                           "arguments": json.dumps({"service": "secretsmanager", "operation": "GetSecretValue"})}),
        ("mcp_call_tool", {"server": "aws-mcp", "tool_name": "call_aws", "arguments": {"cli_command": GSV_CLI}}),
        # server_name is not documented; with no server key the call is checked anyway.
        ("mcp_call_tool", {"tool_name": "call_aws", "arguments": {"cli_command": GSV_CLI}}),
    ]

    ALLOWED = [
        ("exec", {"command": "ls -la", "shell_id": "main"}),
        ("exec", {"command": "aws secretsmanager list-secrets"}),
        ("exec", {"command": "grep -rn get-secret-value ."}),
        ("shell_command", {"command": "git status"}),
        ("write_to_process", {"shell_id": "main", "text_input": "y\n"}),
        ("write_to_process", {"shell_id": "main", "bytes_input": "y<CR>"}),
        ("mcp__aws-mcp__call_aws", {"cli_command": "aws secretsmanager describe-secret --secret-id prod/db"}),
        ("mcp_call_tool", {"server_name": "aws-mcp", "tool_name": "call_aws",
                           "arguments": {"cli_command": "aws s3 ls"}}),
        # Outside the AWS servers the Claude matcher covers, as there.
        ("mcp_call_tool", {"server_name": "github", "tool_name": "create_issue",
                           "arguments": {"body": GSV_CLI}}),
        ("mcp_call_tool", {"server": "github", "tool_name": "create_issue", "arguments": {"body": GSV_CLI}}),
        ("read", {"file_path": "/tmp/get-secret-value.txt"}),
    ]

    def test_denied(self):
        for tool_name, tool_input in self.DENIED:
            with self.subTest(tool_name=tool_name, tool_input=tool_input):
                result = run_script(payload(tool_name, tool_input, host="devin"), "--devin")
                self.assertDecision(result, DEVIN_BLOCK)

    def test_allowed(self):
        for tool_name, tool_input in self.ALLOWED:
            with self.subTest(tool_name=tool_name, tool_input=tool_input):
                result = run_script(payload(tool_name, tool_input, host="devin"), "--devin")
                self.assertDecision(result, None)


def entries(hooks_json):
    return json.loads(hooks_json.read_text())["hooks"]["PreToolUse"]


@unittest.skipIf(os.name == "nt", "POSIX shell")
class TestHooksJsonWiring(HookAssertions):
    """Against the shipped hooks.json files, not copies of their commands."""

    def run_command(self, command, data, env_var):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), env_var: str(PLUGIN_ROOT)}
        return subprocess.run(  # nosec B602 — exercising the shipped command
            command, shell=True, input=json.dumps(data), capture_output=True, text=True, env=env, timeout=10,
        )

    def test_claude_hooks_json_blocks_with_claude_output(self):
        for entry in entries(CLAUDE_HOOKS_JSON):
            for hook in entry["hooks"]:
                with self.subTest(matcher=entry["matcher"]):
                    tool = "Bash" if entry["matcher"] == "Bash" else "mcp__plugin_aws-core_aws-mcp__call_aws"
                    tool_input = {"command": GSV_CLI} if tool == "Bash" else {"cli_command": GSV_CLI}
                    result = self.run_command(hook["command"], payload(tool, tool_input), "CLAUDE_PLUGIN_ROOT")
                    self.assertDecision(result, CLAUDE_DENY)

    def test_devin_hooks_json_blocks_with_devin_output(self):
        cases = {
            "^(exec|shell_command|write_to_process)$": ("exec", {"command": GSV_CLI}),
            "^mcp__aws|^mcp_call_tool$": ("mcp_call_tool", {"server_name": "aws-mcp", "tool_name": "call_aws",
                                                           "arguments": {"cli_command": GSV_CLI}}),
        }
        self.assertEqual(sorted(e["matcher"] for e in entries(DEVIN_HOOKS_JSON)), sorted(cases))
        for entry in entries(DEVIN_HOOKS_JSON):
            tool, tool_input = cases[entry["matcher"]]
            for hook in entry["hooks"]:
                with self.subTest(matcher=entry["matcher"]):
                    self.assertIn("${DEVIN_PLUGIN_ROOT}/com.anthropic.claude-code/hooks/secret-safety.py",
                                  hook["command"])
                    result = self.run_command(hook["command"], payload(tool, tool_input, "devin"),
                                              "DEVIN_PLUGIN_ROOT")
                    self.assertDecision(result, DEVIN_BLOCK)
                    benign = self.run_command(hook["command"], payload("exec", {"command": "ls"}, "devin"),
                                              "DEVIN_PLUGIN_ROOT")
                    self.assertDecision(benign, None)

    def test_devin_matchers_select_devin_tools_only(self):
        # Devin matchers are regexes searched against tool_name.
        shell, mcp = (re.compile(e["matcher"]) for e in entries(DEVIN_HOOKS_JSON))
        for name in ("exec", "shell_command", "write_to_process"):
            self.assertTrue(shell.search(name), name)
        for name in ("Bash", "get_output", "kill_shell", "executor"):
            self.assertFalse(shell.search(name), name)
        for name in ("mcp__aws-mcp__call_aws", "mcp__awsknowledge__search", "mcp_call_tool"):
            self.assertTrue(mcp.search(name), name)
        for name in ("mcp__github__create_issue", "mcp_list_tools", "mcp__plugin_aws-core_aws-mcp__call_aws"):
            self.assertFalse(mcp.search(name), name)

    def test_no_default_hooks_dir(self):
        # Claude Code and Cursor auto-load hooks/hooks.json alongside their own wiring,
        # so a Devin file there would also run under them.
        self.assertFalse((PLUGIN_ROOT / "hooks" / "hooks.json").exists())


if __name__ == "__main__":
    unittest.main()
