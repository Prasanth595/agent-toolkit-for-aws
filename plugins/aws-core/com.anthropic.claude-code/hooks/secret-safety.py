#!/usr/bin/env python3
"""PreToolUse hook: block direct secret fetching from AWS Secrets Manager.

Reads JSON from stdin, checks tool_name and tool_input, and returns
a deny decision if the call would fetch secret values directly.

Use {{resolve:secretsmanager:secret-id:SecretString:key}} with asm-exec instead.

One policy, two hosts. With no arguments it speaks the Claude Code hook protocol
(also used by Codex), wired from com.anthropic.claude-code/hooks/hooks.json.
With --devin it maps Devin's tool names onto the same checks and answers in
Devin's format; that mode is wired from the plugin-root hooks.json, which only
Devin reads.
"""

import json
import re
import sys

DENY_MSG = (
    "Direct secret fetching is blocked. "
    "Use {{resolve:secretsmanager:secret-id:SecretString:key}} with asm-exec instead. "
    "Run /aws-secrets-manager for details."
)

SMA_PATTERN = re.compile(
    r'(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|::1):2773/secretsmanager/get'
)

# AWS CLI invocation shape. Shared by the Bash and MCP branches so the two paths
# cannot drift. Tolerates global flags interleaved before the service name or the
# operation (e.g. `aws --region us-east-1 secretsmanager get-secret-value`).
#
# A flag token is `-` plus greedy non-whitespace, so it has exactly one possible
# parse; an optional value token must not itself start with `-`. Both properties,
# plus the bounded repetition, keep this linear — an ambiguous flag pattern here
# backtracks catastrophically on long flag runs, and because the hook has a 5s
# timeout in hooks.json, a hang would let the tool call through (fail-open).
_CLI_FLAGS = r'(?:-\S+(?:\s+[^-\s]\S*)?\s+){0,12}'
CLI_GSV_PATTERN = re.compile(
    rf'aws\s+{_CLI_FLAGS}secretsmanager\s+{_CLI_FLAGS}(?:batch-)?get-secret-value\b',
    re.I
)

# Structured operation names normalized to lowercase, no separators.
GSV_OPERATIONS = ("getsecretvalue", "batchgetsecretvalue")

# SDK call invocation shapes — matches actual method calls / constructors, not bare text.
# boto3:  client.get_secret_value(...)
# JS v3:  GetSecretValueCommand(...)
# Generic SDK: (Batch)GetSecretValue(Request|Command)?(...)
SDK_CALL_PATTERN = re.compile(
    r'\.\s*(batch[-_]?)?get[-_]?secret[-_]?value\s*\('       # boto3/ruby/go style
    r'|GetSecretValueCommand\s*\('                            # JS SDK v3
    r'|(Batch)?GetSecretValue(Request|Command)?\s*\(',        # other SDKs
    re.I
)

# Read-only text tools that should never be blocked for merely mentioning an API name.
_READ_ONLY_PREFIXES = (
    'grep', 'egrep', 'fgrep', 'rg', 'ag', 'ack',
    'cat', 'less', 'more', 'head', 'tail', 'bat',
    'git', 'gh', 'find', 'ls', 'wc', 'diff',
    'awk', 'sed', 'sort', 'uniq', 'cut', 'tr',
    'echo', 'printf', 'man', 'help',
)

# Interpreter flags that indicate inline code execution.
_INTERPRETER_INLINE_RE = re.compile(
    r'(?:python[23]?|python3\.\d+|node|ruby|perl)\s+(?:-[a-zA-Z]*c|-e)\s'
)

# Shell compound operators that indicate the command has multiple parts.
_COMPOUND_OPERATORS_RE = re.compile(r'[;&|`]|\$\(')


def _normalize_op(operation):
    """Collapse casing and -/_ separators so GetSecretValue == get-secret-value."""
    return operation.lower().replace("-", "").replace("_", "")


def _is_read_only_command(command):
    """Check if the command's leading token is a known read-only text tool."""
    stripped = command.lstrip()
    # Skip common prefixes: env vars (FOO=bar), sudo, env, time, etc.
    while True:
        # Skip env var assignments at the start
        if re.match(r'[A-Za-z_][A-Za-z0-9_]*=\S*\s', stripped):
            stripped = re.sub(r'^[A-Za-z_][A-Za-z0-9_]*=\S*\s+', '', stripped)
            continue
        # Skip common wrapper commands
        if re.match(r'(sudo|env|time|nice|nohup|command|builtin)\s', stripped):
            stripped = re.sub(r'^(sudo|env|time|nice|nohup|command|builtin)\s+', '', stripped)
            continue
        break
    first_token = stripped.split()[0] if stripped.split() else ''
    # Strip path prefix (e.g., /usr/bin/grep -> grep)
    first_token = first_token.rsplit('/', 1)[-1]
    return first_token in _READ_ONLY_PREFIXES


def _has_sdk_call_in_inline_code(command):
    """Check if the command executes inline interpreter code containing an SDK call."""
    if _INTERPRETER_INLINE_RE.search(command):
        return SDK_CALL_PATTERN.search(command)
    return False


def _aws_tool_input_denied(tool_input):
    """Structured AWS tool calls (use_aws or MCP AWS tools)."""
    service = (tool_input.get("service_name") or tool_input.get("service") or tool_input.get("serviceName") or "").lower()
    operation = tool_input.get("operation_name") or tool_input.get("operation") or tool_input.get("operationName") or ""
    if service == "secretsmanager" and _normalize_op(operation) in GSV_OPERATIONS:
        return True
    # Only deny if tool input contains an actual SDK call shape (not just a mention)
    input_str = json.dumps(tool_input)
    if SDK_CALL_PATTERN.search(input_str):
        if "secretsmanager" in input_str.lower():
            return True
    # AWS CLI command strings routed through an MCP proxy (e.g. call_aws's
    # cli_command), which carry neither structured fields nor SDK call syntax.
    if CLI_GSV_PATTERN.search(input_str):
        return True
    return False


def _shell_command_denied(command):
    # AWS CLI secret fetching (shape-aware: actual `aws secretsmanager get-secret-value`)
    if CLI_GSV_PATTERN.search(command):
        return True
    # Direct SMA access (shape-aware: actual URL to the agent)
    if SMA_PATTERN.search(command):
        return True
    # Skip read-only commands that merely mention the API name,
    # but only for simple commands (no compound operators that could
    # chain a secret-fetching command after the read-only prefix).
    if _is_read_only_command(command) and not _COMPOUND_OPERATORS_RE.search(command):
        return False
    # SDK call invocations in inline interpreter code
    if _has_sdk_call_in_inline_code(command):
        return True
    # Piped interpreter execution with SDK calls (e.g., heredoc | python3)
    if SDK_CALL_PATTERN.search(command) and "secretsmanager" in command.lower():
        return True
    return False


def claude_denied(tool_name, tool_input):
    if tool_name == "use_aws" or tool_name.startswith("mcp__"):
        return _aws_tool_input_denied(tool_input)

    # Check run_script tools for secret fetching in code
    if "run_script" in tool_name:
        for key, val in tool_input.items():
            if isinstance(val, str) and SDK_CALL_PATTERN.search(val):
                return True
        return False

    if tool_name == "Bash":
        return _shell_command_denied(tool_input.get("command", ""))

    return False


def devin_denied(tool_name, tool_input):
    """Devin's names for the same tools (docs.devin.ai lifecycle-hooks).

    exec is the documented shell tool. The CLI also has shell_command (an
    alternative shell tool) and write_to_process (types into a running shell),
    so a command sent through either is checked the same way.
    """
    if tool_name in ("exec", "shell_command"):
        command = tool_input.get("command") or ""
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)
        return _shell_command_denied(command)

    if tool_name == "write_to_process":
        # The schema takes exactly one of text_input or bytes_input; the latter
        # spells keys in angle brackets, e.g. "<CR>" for Enter.
        typed = (tool_input.get("text_input") or "") + "\n" + (tool_input.get("bytes_input") or "")
        return _shell_command_denied(re.sub(r"<(CR|LF)>", "\n", typed))

    if tool_name.startswith("mcp__"):
        return _aws_tool_input_denied(tool_input)

    # Devin's generic MCP invoker. The hooks.json matcher cannot see which
    # server is called, so scope it here to the same AWS servers that the
    # mcp__aws matcher selects. If no server is named, check the call anyway.
    if tool_name == "mcp_call_tool":
        server = str(tool_input.get("server_name") or tool_input.get("server") or "")
        if server and not server.lower().startswith("aws"):
            return False
        arguments = tool_input.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                pass
        if not isinstance(arguments, dict):
            arguments = {"arguments": arguments}
        return _aws_tool_input_denied(arguments)

    return False


def deny(host):
    if host == "devin":
        # Exit 0 with a JSON decision rather than exit 2: in the hooks.json
        # wrapper (python3 || python || py -3) a non-zero exit runs the next
        # interpreter, whose exit status replaces the 2 and lets the call through.
        json.dump({"decision": "block", "reason": DENY_MSG}, sys.stdout)
    else:
        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": DENY_MSG
            }
        }, sys.stdout)
    sys.exit(0)


def allow():
    sys.exit(0)


def main():
    host = "devin" if "--devin" in sys.argv[1:] else "claude"
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    denied = devin_denied if host == "devin" else claude_denied
    if denied(tool_name, tool_input):
        deny(host)
    allow()


if __name__ == "__main__":
    main()
