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


def _norm_path(value):
    """Normalize a file path: forward slashes, collapse // and /./, resolve ..,
    strip a leading ./  so regex guards cannot be bypassed by case, redundant
    separators, or dot-dot traversal."""
    p = value.replace("\\", "/")
    p = os.path.normpath(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def path_from_event(event):
    for key in ("path", "file_path", "filename"):
        value = event.get(key)
        if isinstance(value, str):
            return _norm_path(value)
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("path", "file_path", "filename"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return _norm_path(value)
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
    name = tokens[0]
    # Detect whether the token is an explicit path (starts with . / \ or contains a
    # path separator, or is absolute).  Only explicit paths are resolved relative to
    # root() — bare names like "gradlew" or "mvnw" are resolved ONLY against the
    # trusted system PATH (shutil.which) so a planted file at the repo root cannot
    # be elevated to an executable inside the gate process.
    is_explicit = (
        name.startswith((".", "/", "\\"))
        or os.path.isabs(name)
        or ("/" in name)
        or ("\\" in name)
    )
    if is_explicit:
        # explicit path: resolve relative to root(), fall back to PATH
        candidate = name if os.path.isabs(name) else os.path.join(root(), name)
        exe = candidate if os.path.exists(candidate) else shutil.which(name)
    else:
        # bare name: ONLY the trusted system PATH — never the repo root
        exe = shutil.which(name)
    if not exe:
        return -1, f"command not found: {name}"
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


def git_changed_paths():
    """Tracked+untracked changed paths (forward-slash, repo-relative), or [].

    Stop gates derive their trigger from the real working tree here instead of
    the agent's final message, which is attacker-controlled and was the root of
    the red-team "flow theater" bypass: omitting a path from the message used to
    silently unlock every Stop guarantee."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root(), text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    paths = []
    for line in proc.stdout.splitlines():
        # porcelain v1: 2 status chars + 1 space, then the path
        entry = line[3:].strip().strip('"')
        if " -> " in entry:  # rename: keep the destination
            entry = entry.split(" -> ", 1)[1].strip().strip('"')
        if entry:
            paths.append(entry.replace("\\", "/"))
    return paths


# Production-code suffixes whose change should engage the development flow.
# Markup/spec/enforcement files are excluded by prefix in changed_code_files.
CODE_SUFFIXES = (".kt", ".kts", ".java", ".py", ".ts", ".tsx", ".js", ".jsx",
                 ".go", ".rs", ".cs", ".scala")


def changed_code_files():
    """Changed production-code files: code suffix, outside openspec/ docs/
    .gigacode/ (those are spec/doc/enforcement edits, not shipped product code)."""
    return [p for p in git_changed_paths()
            if p.endswith(CODE_SUFFIXES)
            and not p.startswith(("openspec/", "docs/", ".gigacode/"))]


def stdin_event():
    """CLI entry helper: parse the hook event from stdin (BOM-safe)."""
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None
