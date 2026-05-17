#!/usr/bin/env python3
"""Preflight hook for GigaCode reverse-analysis prompts."""

from __future__ import annotations

import json
import re
import sys


REVERSE_ANALYSIS_MARKERS = (
    "reverse-analysis",
    "reverse analysis",
    "reverse analyze",
    "реверс",
    "обратн",
)

FEATURE_MARKERS = (
    r"\bfeature\s+['\"]?[\w .:/-]+",
    r"\bfunction\s+['\"]?[\w .:/-]+",
    r"функци[ияю]\s+['\"]?[\w .:/-]+",
    r"фич[ауи]\s+['\"]?[\w .:/-]+",
)

EXTERNAL_CONTEXT_MARKERS = (
    r"\bjira\b",
    r"\bconfluence\b",
    r"[A-Z][A-Z0-9]+-\d+",
    r"код[- ]?only",
    r"code[- ]?only",
    r"без\s+jira",
    r"без\s+confluence",
    r"только\s+код",
    r"without\s+jira",
    r"without\s+confluence",
)


def emit(decision: str, reason: str, additional_context: str | None = None) -> int:
    payload: dict[str, object] = {"decision": decision, "reason": reason}
    if additional_context:
        payload["hookSpecificOutput"] = {"additionalContext": additional_context}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def read_event() -> dict[str, object]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def contains_any(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def main() -> int:
    event = read_event()
    prompt = str(event.get("prompt", "")).strip()
    normalized = prompt.lower()

    if not any(marker in normalized for marker in REVERSE_ANALYSIS_MARKERS):
        return emit("allow", "Prompt is not a reverse-analysis request.")

    missing: list[str] = []
    if not contains_any(FEATURE_MARKERS, prompt):
        missing.append("feature name")
    if not contains_any(EXTERNAL_CONTEXT_MARKERS, prompt):
        missing.append("Jira/Confluence reference or explicit code-only statement")

    if missing:
        questions = [
            "Specify the business feature name.",
            "Provide Jira/Confluence context or explicitly say that analysis is code-only.",
        ]
        return emit(
            "ask",
            "Reverse-analysis request is missing: " + ", ".join(missing) + ".",
            "\n".join(questions),
        )

    return emit(
        "allow",
        "Reverse-analysis preflight passed.",
        "Follow the reverse-analysis skill and produce final analyst artifacts as AsciiDoc.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
