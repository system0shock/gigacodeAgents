#!/usr/bin/env python3
"""Development-output gate (Stop): validate the docs/development/<slug>/ task
artifacts.

Triggers from the working tree / disk, never from the agent's final message:
the message is attacker-controlled and omitting `docs/development/` used to
unlock the gate entirely (red-team "flow theater"). The gate fires when a
development task dir exists on disk OR production code changed; it then requires
each task dir to carry complete, placeholder-free, evidence-backed artifacts."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

REQUIRED_FILES = [
    "journal.md",
    "verification.md",
    "pr-summary.md",
]

PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b", re.IGNORECASE)


def last_message(event):
    for key in ("last_assistant_message", "message", "response"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return ""


def discovered_task_dirs():
    """Every docs/development/<slug>/ directory on disk (absolute paths)."""
    base = os.path.join(_lib.root(), "docs", "development")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    return [os.path.join(base, name) for name in names
            if os.path.isdir(os.path.join(base, name))]


def _rel(path):
    return os.path.relpath(path, _lib.root()).replace("\\", "/")


def read_file(path):
    # errors="replace": a non-UTF-8 artifact must not crash the gate
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def run(event):
    message = last_message(event)
    task_dirs = discovered_task_dirs()
    code_changed = bool(_lib.changed_code_files())

    # Trigger off disk/working tree, not the message.
    if not task_dirs and not code_changed:
        return {"decision": "allow"}
    if not task_dirs and code_changed:
        return {"decision": "block", "reason": (
            "Stop заблокирован: изменён production-код, но нет каталога "
            "docs/development/<slug>/. Пройди development-flow и зафиксируй "
            "journal.md / verification.md / pr-summary.md перед завершением.")}

    # A dev task dir exists: each one must be complete, placeholder-free, evidenced.
    for task_dir in task_dirs:
        missing = [name for name in REQUIRED_FILES
                   if not os.path.exists(os.path.join(task_dir, name))]
        if missing:
            return {"decision": "block", "reason": (
                f"Не хватает development artifact files в {_rel(task_dir)}: "
                f"{', '.join(missing)}")}
        for name in REQUIRED_FILES:
            content = read_file(os.path.join(task_dir, name))
            if PLACEHOLDER_RE.search(content):
                return {"decision": "block", "reason": (
                    f"Placeholder marker найден в {_rel(os.path.join(task_dir, name))}.")}
        verification = read_file(os.path.join(task_dir, "verification.md")).lower()
        if "passed" in message.lower() and "command" not in verification and "exit" not in verification:
            return {"decision": "block", "reason": (
                "Сообщение заявляет passing checks без command evidence в "
                f"{_rel(os.path.join(task_dir, 'verification.md'))}.")}

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
