#!/usr/bin/env python3
"""Technical-layer AsciiDoc checks for docs/features/ (PostToolUse)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

TECHDOC_RE = re.compile(r"(^|/)docs/features/[^/]+/[^/]+\.adoc$", re.IGNORECASE)
MD_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
REQUIRED_ATTRS = (":feature:", ":run-date:", ":code-commit:")


def run(event):
    path = _lib.path_from_event(event)
    match = TECHDOC_RE.search(path.replace("\\", "/"))
    if not match:
        return {"decision": "allow"}
    normalized = path.replace("\\", "/")
    idx = normalized.lower().find("docs/features/")
    rel = normalized[idx:]
    target = os.path.join(_lib.root(), *rel.split("/"))
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return {"decision": "allow"}  # nothing on disk yet — not this gate's failure
    issues = []
    if not text.lstrip("﻿\r\n\t ").startswith("="):
        issues.append("нет заголовка AsciiDoc (=)")
    for attr in REQUIRED_ATTRS:
        if attr not in text:
            issues.append(f"нет атрибута {attr}")
    if "```" in text:
        issues.append("Markdown fenced-блок (```)")
    if MD_HEADING_RE.search(text):
        issues.append("Markdown-заголовок (#)")
    if not CYRILLIC_RE.search(text):
        issues.append("документ должен быть на русском")
    if issues:
        return {"decision": "block",
                "reason": f"Технический документ {rel}: " + "; ".join(issues) + "."}
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
