#!/usr/bin/env python3
"""Spec-structure gate: protect openspec/ truth and enforce `openspec validate --strict`.

PreToolUse: deny direct writes to openspec/specs/ and openspec/changes/archive/.
PostToolUse: validate the written change; block only when the change is
structurally complete (otherwise advisory while artifacts are being created).
Stop: validate all active changes at PR-readiness moments."""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

DENY_RE = re.compile(r"(^|/)openspec/(specs|changes/archive)/")
CHANGE_RE = re.compile(r"(^|/)openspec/changes/([A-Za-z0-9][A-Za-z0-9._-]*)/")


def openspec_validate(args):
    """Returns (ok, detail): ok True/False, or None when the CLI is unavailable."""
    exe = os.environ.get("OPENSPEC_BIN") or shutil.which("openspec")
    if not exe:
        return None, "openspec CLI not found on PATH"
    cmd = [exe, "validate"] + args + ["--strict", "--no-interactive"]
    try:
        proc = subprocess.run(
            cmd, cwd=_lib.root(), text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"openspec validate could not run: {exc}"
    if proc.returncode == 0:
        return True, ""
    return False, "\n".join(proc.stdout.splitlines()[-30:])


def change_complete(change_id):
    base = os.path.join(_lib.root(), "openspec", "changes", change_id)
    has_delta = False
    for _dirpath, _dirs, files in os.walk(os.path.join(base, "specs")):
        if "spec.md" in files:
            has_delta = True
            break
    return (os.path.exists(os.path.join(base, "proposal.md"))
            and os.path.exists(os.path.join(base, "tasks.md"))
            and has_delta)


def active_changes():
    changes_dir = os.path.join(_lib.root(), "openspec", "changes")
    try:
        return [name for name in os.listdir(changes_dir)
                if name != "archive" and os.path.isdir(os.path.join(changes_dir, name))]
    except OSError:
        return []


def run(event):
    name = str(event.get("hook_event_name", ""))
    path = _lib.path_from_event(event)

    if name == "PreToolUse":
        if path and DENY_RE.search(path):
            return {"decision": "block", "reason": (
                f"Запись в '{path}' запрещена: openspec/specs/ и openspec/changes/archive/ "
                "обновляются только командой `openspec archive` (см. rules/openspec.md).")}
        return {"decision": "allow"}

    if name == "PostToolUse":
        match = CHANGE_RE.search(path or "")
        if not match or match.group(2) == "archive":
            return {"decision": "allow"}
        change_id = match.group(2)
        ok, detail = openspec_validate([change_id, "--type", "change"])
        if ok is None:
            _lib.journal_skip("gate_spec_structure", detail)
            return {"decision": "allow", "additionalContext": (
                f"gate_spec_structure: strict-валидация пропущена ({detail}). "
                "Зафиксируй пропуск в verification.md.")}
        if ok:
            return {"decision": "allow"}
        if change_complete(change_id):
            return {"decision": "block", "reason": (
                f"openspec validate {change_id} --strict failed:\n{detail}")}
        return {"decision": "allow", "additionalContext": (
            f"gate_spec_structure: change '{change_id}' ещё не проходит strict-валидацию "
            f"(артефакты не завершены):\n{detail}")}

    if name == "Stop":
        message = _lib.message_from_event(event).replace("\\", "/")
        if "openspec/changes" not in message and "docs/development/" not in message:
            return {"decision": "allow"}
        if not active_changes():
            return {"decision": "allow"}
        ok, detail = openspec_validate(["--changes"])
        if ok is None:
            _lib.journal_skip("gate_spec_structure", detail)
            return {"decision": "allow"}
        if not ok:
            return {"decision": "block", "reason": (
                f"openspec validate --changes --strict failed:\n{detail}\n"
                "Исправь структуру change или заархивируй завершённые changes.")}
        return {"decision": "allow"}

    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
