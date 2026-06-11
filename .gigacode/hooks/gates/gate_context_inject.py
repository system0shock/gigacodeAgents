#!/usr/bin/env python3
"""Advisory gate: inject rules, the module map and active OpenSpec changes.

Primary enforcement mechanism (design revision 2026-06-10): ground the agent
before generation. Never blocks."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

RULE_FILES = ["development-flow.md", "openspec.md"]
MODULE_MAP = os.path.join(".gigacode", "context", "module-map.md")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def active_changes():
    changes_dir = os.path.join(_lib.root(), "openspec", "changes")
    try:
        return sorted(
            name for name in os.listdir(changes_dir)
            if name != "archive" and os.path.isdir(os.path.join(changes_dir, name))
        )
    except OSError:
        return []


def changes_line():
    changes = active_changes()
    return "Active OpenSpec changes: " + (", ".join(changes) if changes else "none") + "."


def run(event):
    name = str(event.get("hook_event_name", ""))
    if name == "SessionStart":
        parts = [read_text(os.path.join(_lib.root(), "rules", rule)) for rule in RULE_FILES]
        parts.append(read_text(os.path.join(_lib.root(), MODULE_MAP)))
        parts.append(changes_line())
        return {"decision": "allow",
                "additionalContext": "\n\n".join(part for part in parts if part)}
    if name == "SubagentStart":
        parts = [
            "Before creating any function, class or module: search for an existing "
            "implementation first (mcp__serena__find_symbol when available, else "
            "rg / git grep). Reuse or extend matches; record the search result in "
            "docs/development/<task-slug>/journal.md.",
            read_text(os.path.join(_lib.root(), MODULE_MAP)),
            changes_line(),
        ]
        return {"decision": "allow",
                "additionalContext": "\n\n".join(part for part in parts if part)}
    if name == "UserPromptSubmit":
        # lstrip: a slash command preceded by accidental whitespace still counts
        prompt = str(event.get("prompt", "")).lstrip()
        if prompt.startswith(("/develop-feature", "/fix-bug")):
            return {"decision": "allow", "additionalContext": changes_line() + (
                " Каждая фича/багфикс проходит через OpenSpec change "
                "(см. rules/openspec.md): propose -> apply -> archive.")}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
