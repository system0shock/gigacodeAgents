"""PreToolUse: source edits require a valid approved plan in docs/plans/."""

from __future__ import annotations

from hooklib import plandoc
from hooklib.event import Result, file_path


def run(event: dict[str, object], options: dict[str, object]) -> Result:
    path = file_path(event)
    plan = plandoc.find_latest_plan()
    if plan is None:
        return Result(
            decision="ask",
            reason=(
                f"Editing {path} without a plan. Create docs/plans/<task-slug>.md from "
                "docs/templates/plan-template.md, get it approved (Status: approved), or confirm to proceed."
            ),
        )

    issues = plandoc.validate(plan)
    if issues:
        return Result(
            decision="ask",
            reason=f"Plan {plan} is invalid; fix it or confirm to proceed.",
            context="Plan defects:\n" + "\n".join(issues),
        )

    if not plandoc.is_approved(plan):
        return Result(
            decision="ask",
            reason=(
                f"Plan {plan} is not approved (Status: approved missing). "
                "Ask the user to approve the plan or confirm to proceed."
            ),
        )

    return Result(decision="allow", reason="Approved plan found.")
