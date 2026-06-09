"""PreToolUse: block dangerous Bash commands, confirm build-file edits."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from hooklib.event import Result, bash_command, file_path, tool_name


BLOCKED_COMMANDS = (
    (re.compile(r"\brm\s+-[a-z]*[rf][a-z]*[rf][a-z]*\b"), "recursive force delete"),
    (re.compile(r"\bgit\s+push\s+(--force\b|-f\b)"), "force push"),
    (re.compile(r"\bmvn\s+[^|;&]*\bdeploy\b"), "maven deploy"),
    (re.compile(r"\bgradlew?\s+[^|;&]*\bpublish"), "gradle publish"),
    (re.compile(r"\bchmod\s+-R\s+777\b"), "world-writable chmod"),
)

ASK_COMMANDS = ((re.compile(r"\bgit\s+push\b"), "git push"),)

BUILD_FILES = {
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "gradle.properties",
    "pom.xml",
}


def run(event: dict[str, object], options: dict[str, object]) -> Result:
    if tool_name(event) == "Bash":
        command = bash_command(event)
        for pattern, label in BLOCKED_COMMANDS:
            if pattern.search(command):
                return Result(
                    decision="block",
                    reason=f"Command blocked by development guard: {label}.",
                )
        for pattern, label in ASK_COMMANDS:
            if pattern.search(command):
                return Result(decision="ask", reason=f"Confirm {label}.")
        return Result(decision="allow", reason="")

    path = file_path(event)
    if not path:
        return Result(decision="allow", reason="")
    name = PurePosixPath(path).name
    if name in BUILD_FILES or "gradle/wrapper/" in path:
        return Result(
            decision="ask",
            reason=f"Build configuration change in {path} - confirm before editing.",
        )
    return Result(decision="allow", reason="")
