#!/usr/bin/env python3
"""Bootstrap rule for openspec/specs: create once, change via lifecycle."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

SPEC_RE = re.compile(r"(^|/)openspec/specs/[^/]+/spec\.md$", re.IGNORECASE)
SPECS_DIR_RE = re.compile(r"(^|/)openspec/specs/", re.IGNORECASE)
FR_RE = re.compile(r"(^|/)analytics/functional-requirements/", re.IGNORECASE)


def _norm(path):
    p = path.replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def run(event):
    path = _norm(_lib.path_from_event(event))
    if not path:
        return {"decision": "allow"}
    match = SPEC_RE.search(path)
    if match:
        rel = path[match.start():].lstrip("/")
        target = os.path.join(_lib.root(), *rel.split("/"))
        if os.path.exists(target):
            return {"decision": "block", "reason": (
                f"Спека capability уже существует: {rel}. Bootstrap-правило: прямое "
                "создание разрешено один раз; изменения существующей спеки идут "
                "только через OpenSpec change lifecycle.")}
        return {"decision": "allow"}
    if SPECS_DIR_RE.search(path):
        return {"decision": "block", "reason": (
            "В openspec/specs/ допускается только создание "
            f"<capability>/spec.md; получено: {path}.")}
    if FR_RE.search(path):
        return {"decision": "allow", "additionalContext": (
            "Напоминание: analytics/functional-requirements/*.adoc — производная от "
            "openspec/specs/<capability>/spec.md. Спека пишется первой; не редактируй "
            "FR-документ в обход спеки.")}
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
