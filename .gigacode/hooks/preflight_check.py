#!/usr/bin/env python3
import json
import sys


def respond(decision, reason=""):
    payload = {"decision": decision}
    if reason:
        payload["reason"] = reason
    print(json.dumps(payload, ensure_ascii=False))


def prompt_from_event(event):
    for key in ("prompt", "message", "user_prompt"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return ""


def has_any(text, words):
    lowered = text.lower()
    return any(word in lowered for word in words)


def main():
    try:
        # utf-8-sig: PowerShell pipes may prepend a UTF-8 BOM that breaks json.load
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        respond("allow")
        return

    prompt = prompt_from_event(event)
    lowered = prompt.lower()

    if "/develop-feature" not in lowered and "/fix-bug" not in lowered:
        respond("allow")
        return

    if len(prompt.strip().split()) < 3:
        respond("ask", "Укажите имя задачи или короткое описание.")
        return

    implement_mode = has_any(lowered, [" implement", " implementation", "реализ", "исправь", "сделай"])

    if "/develop-feature" in lowered and implement_mode:
        if not has_any(lowered, ["acceptance", "criteria", "критер", "поведение", "behavior"]):
            respond("ask", "Для implement mode по фиче нужны acceptance criteria или ожидаемое поведение.")
            return

    if "/fix-bug" in lowered and implement_mode:
        if not has_any(lowered, ["expected", "actual", "repro", "symptom", "ожид", "факт", "воспро", "симптом", "stack", "trace", "error"]):
            respond("ask", "Для implement mode по багу нужны симптом, expected/actual behavior, reproduction evidence или error details.")
            return

    reminder = "Проверьте analytics и Graphify при наличии; если их нет, используйте описанные fallbacks."
    respond("allow", reminder)


if __name__ == "__main__":
    main()
