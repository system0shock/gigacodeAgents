#!/usr/bin/env python3
"""Shared helpers for quality gates.

Each gate imports this module after putting the gates directory on sys.path:

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _lib
"""
import fnmatch
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

GATES_DIR = os.path.dirname(os.path.abspath(__file__))


def root():
    """Template repo root, derived from this file's location (not cwd).

    GIGACODE_ROOT overrides for tests."""
    override = os.environ.get("GIGACODE_ROOT")
    if override:
        return override
    return os.path.normpath(os.path.join(GATES_DIR, "..", "..", ".."))


def journal_skip(gate, reason):
    """Skip-with-record: append a skip entry to the decisions journal."""
    path = os.path.join(root(), ".gigacode", "logs", "decisions.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {"kind": "skip", "gate": gate, "reason": reason,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                ensure_ascii=False) + "\n")
    except OSError:
        pass  # journaling must never change a decision


def load_quality_gates():
    path = os.path.join(root(), ".gigacode", "quality-gates.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def path_from_event(event):
    for key in ("path", "file_path", "filename", "notebook_path"):
        value = event.get(key)
        if isinstance(value, str):
            return value.replace("\\", "/")
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("path", "file_path", "filename", "notebook_path"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value.replace("\\", "/")
    return ""


def content_from_event(event):
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("content", "new_string", "text"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value
    return ""


def message_from_event(event):
    for key in ("last_assistant_message", "message", "response"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    return ""


def matches_globs(path, globs):
    # fnmatch '*' crosses directory separators (unlike POSIX glob), so
    # 'src/*.kt' also matches 'src/a/Main.kt'. Use '**/*.kt' for all depths.
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    for pattern in globs:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        # fnmatch's '*' crosses '/', but '**/*.kt' still demands one slash;
        # also match root-level files against the suffix.
        if pattern.startswith("**/") and fnmatch.fnmatch(normalized, pattern[3:]):
            return True
    return False


def run_command(command, timeout, extra_args=None):
    """Run a configured command string from the repo root.

    Returns (rc, output_tail). rc -1 = could not run, -2 = timeout."""
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.split()
    # posix=False keeps Windows backslash paths intact but leaves surrounding
    # quotes on tokens; strip them so quoted space-containing args work.
    tokens = [token[1:-1] if len(token) >= 2 and token[0] == token[-1]
              and token[0] in "\"'" else token for token in tokens]
    if not tokens:
        return -1, "empty command"
    exe = shutil.which(tokens[0]) or shutil.which(tokens[0], path=root())
    if not exe:
        candidate = os.path.join(root(), tokens[0])
        if os.path.exists(candidate):
            exe = candidate
        else:
            return -1, f"command not found: {tokens[0]}"
    try:
        proc = subprocess.run(
            [exe] + tokens[1:] + list(extra_args or []),
            cwd=root(), text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return -2, f"timed out after {timeout}s"
    except OSError as exc:
        return -1, str(exc)
    tail = "\n".join(proc.stdout.splitlines()[-30:])
    return proc.returncode, tail


def stdin_event():
    """CLI entry helper: parse the hook event from stdin (BOM-safe)."""
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None
