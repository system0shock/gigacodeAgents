"""Stop: final deterministic validation of all changed source files.

Duplicates the plan gate and static checks so the guarantees hold even on
GigaCode builds where PreToolUse/PostToolUse events never fire.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from checks.posttool_static import scan_file
from hooklib import plandoc, sources
from hooklib.event import Result, last_message


COMPLETION_MARKERS = (
    "implementation complete",
    "task complete",
    "all steps",
    "done",
    "готово",
    "реализовано",
    "выполнено",
    "завершено",
)


def should_validate(message: str) -> bool:
    lowered = message.lower()
    if "src/" in lowered:
        return True
    return any(marker in lowered for marker in COMPLETION_MARKERS)


def changed_source_files() -> list[str] | None:
    """Changed/untracked .java/.kt/.kts files via git; None when git fails."""
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    files: list[str] = []
    for line in completed.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if sources.is_source(path):
            files.append(path.replace("\\", "/"))
    return files


def run(event: dict[str, object], options: dict[str, object]) -> Result:
    message = last_message(event)
    if not should_validate(message):
        return Result(decision="allow", reason="No completion claim detected.")

    changed = changed_source_files()
    if changed is None:
        mentioned = re.findall(r"src/[\w./-]+\.(?:java|kt|kts)", message)
        changed = sorted(set(mentioned))
    if not changed:
        return Result(decision="allow", reason="No changed source files to validate.")

    issues: list[str] = []
    notes: list[str] = []

    plan = plandoc.find_latest_plan()
    if plan is None:
        issues.append("source files changed without a plan; create and approve docs/plans/<task-slug>.md")
        skip_tests = False
    else:
        issues.extend(plandoc.validate(plan))
        if not plandoc.is_approved(plan):
            issues.append(f"{plan}: plan is not approved (Status: approved missing)")
        skip_tests = plandoc.allows_skipping_tests(plan)
        planned = {p.lstrip("./") for p in plandoc.affected_files(plan)}
        unexpected = [
            path for path in changed
            if path.lstrip("./") not in planned and not sources.is_test(path)
        ]
        if planned and unexpected:
            notes.append(
                "Changed files not listed in the plan's Affected files: " + ", ".join(unexpected)
            )

    for path in changed:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        blocking, warnings = scan_file(path, text)
        issues.extend(blocking)
        notes.extend(w for w in warnings if "no test file" not in w)
        if not sources.is_test(path) and "/src/main/" in "/" + path.lstrip("/"):
            if not sources.has_test(path):
                target = notes if skip_tests else issues
                target.append(f"{path}: missing test file for changed production class")

    if issues:
        return Result(
            decision="block",
            reason="Development output validation failed.",
            stop_reason="\n".join(issues + notes),
        )

    reason = "Development output validation passed."
    if notes:
        reason += " Notes: " + " | ".join(notes)
    return Result(decision="allow", reason=reason)
