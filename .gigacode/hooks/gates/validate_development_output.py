#!/usr/bin/env python3
import json
import os
import re
import sys

REQUIRED_FILES = [
    "journal.md",
    "verification.md",
    "pr-summary.md",
]

PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b", re.IGNORECASE)
TASK_DIR_RE = re.compile(r"docs/development/([a-z0-9][a-z0-9-]*)/?")


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
    # errors="replace": a non-UTF-8 artifact must not crash the gate
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def run(event):
    message = last_message(event)
    if "docs/development/" not in message.replace("\\", "/"):
        return {"decision": "allow"}

    task_dir = find_task_dir(message)
    if not task_dir:
        return {"decision": "block", "reason": "Сообщение упоминает docs/development, но не содержит валидный task directory."}

    missing = [name for name in REQUIRED_FILES if not os.path.exists(os.path.join(task_dir, name))]
    if missing:
        return {"decision": "block", "reason": f"Не хватает development artifact files: {', '.join(missing)}"}

    for name in REQUIRED_FILES:
        path = os.path.join(task_dir, name)
        content = read_file(path)
        if PLACEHOLDER_RE.search(content):
            return {"decision": "block", "reason": f"Placeholder marker найден в {path}."}

    verification = read_file(os.path.join(task_dir, "verification.md")).lower()
    if "passed" in message.lower() and "command" not in verification and "exit" not in verification:
        return {"decision": "block", "reason": "Сообщение заявляет passing checks без command evidence в verification.md."}

    return {"decision": "allow"}


def main():
    try:
        # utf-8-sig: PowerShell pipes may prepend a UTF-8 BOM that breaks json.load
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}, ensure_ascii=False))
        return
    print(json.dumps(run(event), ensure_ascii=False))


if __name__ == "__main__":
    main()
