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


# Global git flags that consume a separate value token (git -C <path> reset ...).
GIT_GLOBAL_VALUE_FLAGS = {
    "-c",
    "-C",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--super-prefix",
    "--exec-path",
    "--config-env",
    "--attr-source",
    "--list-cmds",
}


def git_subcommand_index(tokens):
    """Index of the git subcommand, skipping global flags like `-C <path>` or `-c k=v`."""
    if not tokens or tokens[0].lower() != "git":
        return -1
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if not token.startswith("-"):
            return i
        if token in GIT_GLOBAL_VALUE_FLAGS and "=" not in token:
            i += 2
        else:
            i += 1
    return -1


def is_destructive_git_command(command):
    tokens = split_command(command)
    lowered = [token.lower() for token in tokens]
    sub_idx = git_subcommand_index(tokens)
    if sub_idx < 0:
        return False, ""
    subcommand = lowered[sub_idx]
    rest = lowered[sub_idx + 1:]

    if subcommand == "reset" and "--hard" in rest:
        return True, "Blocked `git reset --hard`."

    if subcommand == "clean":
        flags = [token for token in rest if token.startswith("-")]
        combined = "".join(flag.lstrip("-") for flag in flags)
        if "f" in combined and "d" in combined:
            return True, "Blocked destructive `git clean` with force and directory flags."

    if subcommand == "push":
        if any(token.startswith("--force") for token in rest):
            return True, "Blocked force push."
        if "--delete" in rest:
            return True, "Blocked remote branch deletion."
        if any(re.match(r"^:[^:\s]+$", token) for token in rest):
            return True, "Blocked remote branch deletion by refspec."

    if subcommand == "branch" and any(token in ("-d", "--delete") for token in rest):
        return True, "Blocked local branch deletion."

    if subcommand == "remote" and rest and rest[0] == "set-url":
        return True, "Blocked remote URL change."

    return False, ""


def is_branch_write(command):
    tokens = split_command(command.lower())
    sub_idx = git_subcommand_index(tokens)
    return sub_idx >= 0 and tokens[sub_idx] in ("commit", "push", "rebase")


def run(event):
    """Gate contract: event dict in, decision dict out."""
    command = command_from_event(event)
    file_path = path_from_event(event)

    if command:
        blocked, reason = is_destructive_git_command(command)
        if blocked:
            return {"decision": "block", "reason": reason + " Use an explicit human-approved recovery workflow."}
        branch = current_branch()
        if is_protected_branch(branch) and is_branch_write(command):
            return {"decision": "block", "reason": f"Blocked git write operation on protected branch '{branch}'. Create a feature or bugfix branch first."}

    if protected_path(file_path):
        return {"decision": "ask", "reason": f"Protected path '{file_path}' requires explicit confirmation with risk explanation."}

    return {"decision": "allow"}


def main():
    try:
        # utf-8-sig: PowerShell pipes may prepend a UTF-8 BOM that breaks json.load
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}, ensure_ascii=False))
        return
    print(json.dumps(run(event), ensure_ascii=False))


if __name__ == "__main__":
    main()
