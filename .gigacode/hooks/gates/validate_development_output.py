#!/usr/bin/env python3
"""Development-output gate (Stop): validate the docs/development/<slug>/ task
artifacts.

Triggers from the working tree / disk, never from the agent's final message:
the message is attacker-controlled and omitting `docs/development/` used to
unlock the gate entirely (red-team "flow theater"). The gate fires when a
development task dir exists on disk OR production code changed; it then requires
each task dir to carry complete, placeholder-free, evidence-backed artifacts."""
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
    """docs/development/<slug>/ dirs that are part of the CURRENT change.

    Only dirs with an uncommitted change under them are validated. A stale or
    already-completed task's artifacts (e.g. a legacy dir whose prose contains
    TODO) must not block every future Stop in the repo — scanning ALL dirs on
    disk was a false-block + protection-budget burn (red-team #15)."""
    base = os.path.join(_lib.root(), "docs", "development")
    slugs, seen = [], set()
    for p in _lib.git_changed_paths():
        norm = p.replace("\\", "/")
        if norm.startswith("docs/development/"):
            slug = norm[len("docs/development/"):].split("/", 1)[0]
            if slug and slug not in seen and os.path.isdir(os.path.join(base, slug)):
                seen.add(slug)
                slugs.append(slug)
    return [os.path.join(base, slug) for slug in slugs]


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
    event = _lib.stdin_event()
    if event is None:  # parse error / non-dict stdin -> fail open
        _lib.emit({"decision": "allow"})
        return
    _lib.emit(run(event))


if __name__ == "__main__":
    main()
