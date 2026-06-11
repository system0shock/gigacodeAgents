#!/usr/bin/env python3
"""Advisory gate: inject rules, the module map and bootstrapped capabilities.

Primary enforcement mechanism: ground the agent before generation. Never blocks."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

RULE_FILES = ["reverse-analysis.md", "openspec.md"]
MODULE_MAP = os.path.join(".gigacode", "context", "module-map.md")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def bootstrapped_capabilities():
    specs_dir = os.path.join(_lib.root(), "openspec", "specs")
    try:
        return sorted(
            name for name in os.listdir(specs_dir)
            if os.path.isdir(os.path.join(specs_dir, name))
        )
    except OSError:
        return []


def specs_line():
    caps = bootstrapped_capabilities()
    return ("Bootstrapped capabilities (openspec/specs): "
            + (", ".join(caps) if caps else "none") + ".")


def run(event):
    name = str(event.get("hook_event_name", ""))
    if name == "SessionStart":
        parts = [read_text(os.path.join(_lib.root(), "rules", rule)) for rule in RULE_FILES]
        parts.append(read_text(os.path.join(_lib.root(), MODULE_MAP)))
        parts.append(specs_line())
        return {"decision": "allow",
                "additionalContext": "\n\n".join(part for part in parts if part)}
    if name == "SubagentStart":
        parts = [
            "Перед любым утверждением о поведении кода: найди подтверждение "
            "(mcp__serena__find_symbol когда доступен, иначе rg / git grep) и "
            "зафиксируй путь и символ в docs/features/<feature>/journal.md.",
            read_text(os.path.join(_lib.root(), MODULE_MAP)),
            specs_line(),
        ]
        return {"decision": "allow",
                "additionalContext": "\n\n".join(part for part in parts if part)}
    if name == "UserPromptSubmit":
        # lstrip: a slash command preceded by accidental whitespace still counts
        prompt = str(event.get("prompt", "")).lstrip()
        if prompt.startswith("/reverse-analysis"):
            return {"decision": "allow", "additionalContext": specs_line() + (
                " Реверс-анализ — одноразовый bootstrap: ФТ пишутся в "
                "openspec/specs/<capability>/spec.md только для новой capability; "
                "существующие спеки меняются через OpenSpec change lifecycle.")}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
