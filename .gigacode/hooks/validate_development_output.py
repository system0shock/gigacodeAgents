#!/usr/bin/env python3
import json
import os
import re
import sys

REQUIRED_FILES = [
    "context.md",
    "plan.md",
    "implementation.md",
    "verification.md",
    "pr-summary.md",
]

PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b", re.IGNORECASE)
TASK_DIR_RE = re.compile(r"docs/development/([a-z0-9][a-z0-9-]*)/?")


def respond(decision, reason=""):
    payload = {"decision": decision}
    if reason:
        payload["reason"] = reason
    print(json.dumps(payload, ensure_ascii=False))


def last_message(event):
    for key in ("last_assistant_message", "message", "response"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return ""


def find_task_dir(message):
    match = TASK_DIR_RE.search(message.replace("\\", "/"))
    if not match:
        return ""
    return os.path.join("docs", "development", match.group(1))


def read_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def main():
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        respond("allow")
        return

    message = last_message(event)
    if "docs/development/" not in message.replace("\\", "/"):
        respond("allow")
        return

    task_dir = find_task_dir(message)
    if not task_dir:
        respond("block", "Сообщение упоминает docs/development, но не содержит валидный task directory.")
        return

    missing = [name for name in REQUIRED_FILES if not os.path.exists(os.path.join(task_dir, name))]
    if missing:
        respond("block", f"Не хватает development artifact files: {', '.join(missing)}")
        return

    for name in REQUIRED_FILES:
        path = os.path.join(task_dir, name)
        content = read_file(path)
        if PLACEHOLDER_RE.search(content):
            respond("block", f"Placeholder marker найден в {path}.")
            return

    verification = read_file(os.path.join(task_dir, "verification.md")).lower()
    if "passed" in message.lower() and "command" not in verification and "exit" not in verification:
        respond("block", "Сообщение заявляет passing checks без command evidence в verification.md.")
        return

    respond("allow")


if __name__ == "__main__":
    main()
