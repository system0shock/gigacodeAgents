"""UserPromptSubmit: never-blocking context injection for dev prompts."""

from __future__ import annotations

import re

from hooklib import buildsystem
from hooklib.event import Result, prompt


TEST_MARKERS = re.compile(r"\b(test|junit|mock)\b|тест|мок", re.IGNORECASE)
DEV_MARKERS = re.compile(
    r"/develop|/write-tests|implement|refactor|реализ|доработ|исправ|рефактор",
    re.IGNORECASE,
)


def run(event: dict[str, object], options: dict[str, object]) -> Result:
    text = prompt(event)
    if not DEV_MARKERS.search(text) and not TEST_MARKERS.search(text):
        return Result(decision="allow", reason="")

    lines: list[str] = []
    if DEV_MARKERS.search(text):
        lines.append(buildsystem.summary(buildsystem.detect()))
        lines.append("Plan format rules: rules/plan-format.md (plan lives in docs/plans/<task-slug>.md).")
    if TEST_MARKERS.search(text):
        lines.append(
            "Before writing tests read reference/junit-rules.md and reference/mocking.md."
        )

    return Result(decision="allow", reason="Context injected.", context="\n".join(lines))
