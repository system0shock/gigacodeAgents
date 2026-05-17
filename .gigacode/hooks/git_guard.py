#!/usr/bin/env python3
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED_BRANCHES = [
    "main",
    "master",
    "develop",
    "development",
    "release",
    "release/*",
    "hotfix/*",
    "production",
    "prod",
    "staging",
    "uat",
]

PROTECTED_PATHS = [
    ".github/workflows/**",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    "ci/**",
    "deploy/**",
    "deployment/**",
    "k8s/**",
    "helm/**",
    "terraform/**",
    "infra/**",
    ".env",
    ".env.*",
    "secrets/**",
    "config/prod/**",
    "config/production/**",
    "config/staging/**",
    "config/uat/**",
]


def respond(decision, reason=""):
    payload = {"decision": decision}
    if reason:
        payload["reason"] = reason
    print(json.dumps(payload, ensure_ascii=False))


def run_git(args):
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=os.getcwd(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def current_branch():
    return run_git(["branch", "--show-current"])


def is_protected_branch(branch):
    if not branch:
        return False
    return any(fnmatch.fnmatch(branch, pattern) for pattern in PROTECTED_BRANCHES)


def command_from_event(event):
    for key in ("command", "tool_input", "input"):
        value = event.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            command = value.get("command") or value.get("cmd")
            if isinstance(command, str):
                return command
    return ""


def path_from_event(event):
    for key in ("path", "file_path", "filename"):
        value = event.get(key)
        if isinstance(value, str):
            return value.replace("\\", "/")
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("path", "file_path", "filename"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value.replace("\\", "/")
    return ""


def protected_path(path):
    if not path:
        return False
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in PROTECTED_PATHS)


def split_command(command):
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return command.split()


def is_git_command(tokens, subcommand=None):
    if not tokens or tokens[0].lower() != "git":
        return False
    if subcommand is None:
        return True
    return len(tokens) > 1 and tokens[1].lower() == subcommand


def clean_flags_are_destructive(tokens):
    flags = [token for token in tokens[2:] if token.startswith("-")]
    combined = "".join(flag.lstrip("-") for flag in flags)
    return "f" in combined and "d" in combined


def is_destructive_git_command(command):
    tokens = split_command(command)
    lowered = [token.lower() for token in tokens]

    if is_git_command(lowered, "reset") and "--hard" in lowered:
        return True, "Blocked `git reset --hard`."

    if is_git_command(lowered, "clean") and clean_flags_are_destructive(lowered):
        return True, "Blocked destructive `git clean` with force and directory flags."

    if is_git_command(lowered, "push"):
        if any(token.startswith("--force") for token in lowered):
            return True, "Blocked force push."
        if "--delete" in lowered:
            return True, "Blocked remote branch deletion."
        if any(re.match(r"^:[^:\s]+$", token) for token in lowered[2:]):
            return True, "Blocked remote branch deletion by refspec."

    if is_git_command(lowered, "branch") and any(token in ("-d", "-D", "--delete") for token in tokens):
        return True, "Blocked local branch deletion."

    if is_git_command(lowered, "remote") and len(lowered) > 2 and lowered[2] == "set-url":
        return True, "Blocked remote URL change."

    return False, ""


def is_branch_write(command):
    tokens = split_command(command.lower())
    if is_git_command(tokens, "commit"):
        return True
    if is_git_command(tokens, "push"):
        return True
    if is_git_command(tokens, "rebase"):
        return True
    return False


def main():
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        respond("allow")
        return

    command = command_from_event(event)
    file_path = path_from_event(event)
    branch = current_branch()

    if command:
        blocked, reason = is_destructive_git_command(command)
        if blocked:
            respond("block", reason + " Use an explicit human-approved recovery workflow.")
            return

        if is_protected_branch(branch) and is_branch_write(command):
            respond("block", f"Blocked git write operation on protected branch '{branch}'. Create a feature or bugfix branch first.")
            return

    if protected_path(file_path):
        respond("ask", f"Protected path '{file_path}' requires explicit confirmation with risk explanation.")
        return

    respond("allow")


if __name__ == "__main__":
    main()
