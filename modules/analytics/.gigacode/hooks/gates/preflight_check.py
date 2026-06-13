#!/usr/bin/env python3
"""Preflight gate for reverse-analysis prompts (UserPromptSubmit)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

REVERSE_MARKERS = ("reverse-analysis", "reverse analysis", "reverse analyze",
                   "реверс", "обратн")
FEATURE_RES = (
    r"\bfeature\s+['\"]?[\w .:/-]+",
    r"\bfunction\s+['\"]?[\w .:/-]+",
    r"функци[ияю]\s+['\"]?[\w .:/-]+",
    r"фич[ауи]\s+['\"]?[\w .:/-]+",
)
CONTEXT_RES = (
    r"\bjira\b", r"\bconfluence\b", r"[A-Z][A-Z0-9]+-\d+",
    r"код[- ]?only", r"code[- ]?only", r"без\s+jira", r"без\s+confluence",
    r"только\s+код", r"without\s+jira", r"without\s+confluence",
)


def matches_any(patterns, text):
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def run(event):
    if str(event.get("hook_event_name", "")) != "UserPromptSubmit":
        return {"decision": "allow"}
    prompt = str(event.get("prompt", "")).strip()
    if not any(marker in prompt.lower() for marker in REVERSE_MARKERS):
        return {"decision": "allow"}
    questions = []
    if not matches_any(FEATURE_RES, prompt):
        questions.append("Какую бизнес-фичу анализируем (укажи: feature/фича <название>)?")
    if not matches_any(CONTEXT_RES, prompt):
        questions.append("Есть ли Jira/Confluence-контекст (тикет, страница) или анализ только по коду?")
    if questions:
        return {"decision": "block",
                "reason": "Запрос на реверс-анализ неполон. " + " ".join(questions)}
    return {"decision": "allow"}


def main():
    # Match the router's idiom: sys.stdout may use a legacy console code page
    # (e.g. cp1251 on Windows) that cannot encode the Cyrillic reason strings.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
