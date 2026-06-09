"""UserPromptSubmit: completeness check for development requests."""

from __future__ import annotations

import re

from hooklib.event import Result, prompt


DEV_MARKERS = (
    "/develop",
    "/write-tests",
    "implement",
    "refactor",
    "write tests",
    "реализуй",
    "реализовать",
    "доработ",
    "исправ",
    "рефактор",
    "напиши тест",
)

TRACKER_MARKERS = (
    r"[A-Z][A-Z0-9]+-\d+",
    r"\bno\s+jira\b",
    r"\bwithout\s+jira\b",
    r"без\s+jira",
    r"без\s+задачи",
    r"без\s+тикета",
)

MIN_MEANINGFUL_TOKENS = 4


def run(event: dict[str, object], options: dict[str, object]) -> Result:
    text = prompt(event)
    normalized = text.lower()

    if not any(marker in normalized for marker in DEV_MARKERS):
        return Result(decision="allow", reason="Prompt is not a development request.")

    missing: list[str] = []
    tokens = [token for token in re.split(r"\s+", text) if len(token) > 2]
    if len(tokens) < MIN_MEANINGFUL_TOKENS:
        missing.append("task description")
    if not any(re.search(pattern, text, re.IGNORECASE) for pattern in TRACKER_MARKERS):
        missing.append("Jira reference or explicit no-tracker statement")

    if missing:
        questions = [
            "Describe the task: what behavior must change and where.",
            "Provide a Jira ticket (ABC-123) or explicitly say the task has no tracker reference.",
        ]
        return Result(
            decision="ask",
            reason="Development request is missing: " + ", ".join(missing) + ".",
            context="\n".join(questions),
        )

    return Result(
        decision="allow",
        reason="Development preflight passed.",
        context="Follow the feature-development skill: plan in docs/plans/ first, get it approved, then edit src/.",
    )
