#!/usr/bin/env python3
"""Existing-code gate: detect declarations (and Kafka topic literals) in the
content about to be written that already exist in the tree. ADVISORY-ONLY —
always allow; never deny (promotion needs decision-journal evidence).

Search engine: rg when available, else `git grep` (tracked files), else
skip-with-record. Serena stays an agent-side tool; hooks use text search."""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

DECL_KEYWORDS = "class|interface|object|enum|fun|def|function"
SYMBOL_RE = re.compile(r"\b(?:" + DECL_KEYWORDS + r")\s+([A-Za-z_][A-Za-z0-9_]{2,})")
TOPIC_RE = re.compile(r"topics?\s*=\s*[\[{]?\s*\"([^\"]+)\"")
EXCLUDED = ("build", "target", "out", "dist", "node_modules")


def resolve(path):
    if os.path.isabs(path):
        return path
    candidate = os.path.abspath(path)
    if os.path.exists(candidate):
        return candidate
    return os.path.join(_lib.root(), path)


def search(pattern):
    """Returns (hit_lines, skip_reason)."""
    rg = shutil.which("rg")
    if rg:
        cmd = [rg, "-n", "--no-heading", "-m", "20",
               "-g", "!{" + ",".join((".git",) + EXCLUDED) + "}", "-e", pattern]
    else:
        git = shutil.which("git")
        if not git:
            return [], "neither rg nor git available"
        cmd = [git, "grep", "-n", "-I", "-E", pattern, "--", "."]
        cmd += [":!{0}".format(name) for name in EXCLUDED]
    try:
        proc = subprocess.run(cmd, cwd=_lib.root(), text=True, encoding="utf-8",
                              errors="replace", stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], str(exc)
    if proc.returncode not in (0, 1):
        return [], f"search exited {proc.returncode}"
    return proc.stdout.splitlines(), ""


def run(event):
    tool = str(event.get("tool_name", ""))
    path = _lib.path_from_event(event)
    content = _lib.content_from_event(event)
    if not content:
        return {"decision": "allow"}
    if tool == "Edit" and path and os.path.exists(resolve(path)):
        return {"decision": "allow"}  # only new files are checked

    boundary = "(^|[^A-Za-z0-9_])"
    patterns = []
    symbols = []
    for name in SYMBOL_RE.findall(content):
        if name not in symbols:
            symbols.append(name)
    if symbols:
        names = "|".join(re.escape(s) for s in symbols[:5])
        patterns.append(f"{boundary}({DECL_KEYWORDS})[ \\t]+({names})([^A-Za-z0-9_]|$)")
    topics = []
    for topic in TOPIC_RE.findall(content):
        if topic not in topics:
            topics.append(topic)
    if topics:
        patterns.append("|".join(re.escape(t) for t in topics[:5]))
    if not patterns:
        return {"decision": "allow"}

    normalized = (path or "").replace("\\", "/").lstrip("./")
    hits = []
    for pattern in patterns:
        lines, skip = search(pattern)
        if skip:
            _lib.journal_skip("gate_existing_code", skip)
            return {"decision": "allow"}
        hits.extend(line for line in lines
                    if normalized and normalized not in line.replace("\\", "/"))
    if not hits:
        return {"decision": "allow"}
    return {"decision": "allow", "additionalContext": (
        "gate_existing_code (advisory): найдены существующие объявления/топики "
        "с теми же именами:\n" + "\n".join(hits[:10]) +
        "\nПрочитай их и переиспользуй/расширь вместо дубликата; "
        "результат поиска зафиксируй в journal.md.")}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
