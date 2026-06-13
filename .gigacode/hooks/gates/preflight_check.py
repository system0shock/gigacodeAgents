#!/usr/bin/env python3
import json
import sys


def prompt_from_event(event):
    for key in ("prompt", "message", "user_prompt"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return ""


def has_any(text, words):
    lowered = text.lower()
    return any(word in lowered for word in words)


def run(event):
    prompt = prompt_from_event(event)
    lowered = prompt.lower()

    if "/develop-feature" not in lowered and "/fix-bug" not in lowered:
        return {"decision": "allow"}

    if len(prompt.strip().split()) < 3:
        return {"decision": "ask", "reason": "Укажите имя задачи или короткое описание."}

    implement_mode = has_any(lowered, [" implement", " implementation", "реализ", "исправь", "сделай"])

    if "/develop-feature" in lowered and implement_mode:
        if not has_any(lowered, ["acceptance", "criteria", "критер", "поведение", "behavior"]):
            return {"decision": "ask", "reason": "Для implement mode по фиче нужны acceptance criteria или ожидаемое поведение."}

    if "/fix-bug" in lowered and implement_mode:
        if not has_any(lowered, ["expected", "actual", "repro", "symptom", "ожид", "факт", "воспро", "симптом", "stack", "trace", "error"]):
            return {"decision": "ask", "reason": "Для implement mode по багу нужны симптом, expected/actual behavior, reproduction evidence или error details."}

    return {"decision": "allow", "reason": "Проверьте analytics и Graphify при наличии; если их нет, используйте описанные fallbacks."}


def main():
    # UTF-8 stdout so the Russian reason survives a cp1251 console when this gate
    # is run standalone or piped in smoke-check.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass
    try:
        # utf-8-sig: PowerShell pipes may prepend a UTF-8 BOM that breaks json.load
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}, ensure_ascii=False))
        return
    print(json.dumps(run(event), ensure_ascii=False))


if __name__ == "__main__":
    main()
