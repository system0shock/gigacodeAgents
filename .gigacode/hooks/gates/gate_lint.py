#!/usr/bin/env python3
"""Lint gate: run the configured project linter on the file just written.

Deterministic -> may block. Unconfigured -> skip-with-record (journal only).
Configured but unable to run -> allow with an anomaly note."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib


def lint_configs():
    config = _lib.load_quality_gates().get("lint")
    if isinstance(config, dict):
        return [config]
    if isinstance(config, list):
        return [entry for entry in config if isinstance(entry, dict)]
    return []


def run(event):
    path = _lib.path_from_event(event)
    if not path:
        return {"decision": "allow"}
    configs = lint_configs()
    if not configs:
        return {"decision": "allow"}  # no lint section at all — silent
    if not any((entry.get("command") or "").strip() for entry in configs):
        # section exists with empty commands (the shipped default): allow
        # silently — journaling here would write one line per file edit
        return {"decision": "allow"}
    notes = []
    for entry in configs:
        command = (entry.get("command") or "").strip()
        if not command:
            continue
        globs = entry.get("applies_to") or []
        if globs and not _lib.matches_globs(path, globs):
            continue
        timeout = entry.get("timeout_seconds", 120)
        # non-numeric -> default; <=0 -> clamp (subprocess timeout must be >0)
        timeout = max(1, timeout) if isinstance(timeout, (int, float)) else 120
        rc, tail = _lib.run_command(command, timeout, [path])
        if rc == -2:
            _lib.journal_skip("gate_lint", f"{command}: timed out")
            notes.append(f"gate_lint: линтер '{command}' превысил таймаут {timeout}s. "
                         "Зафиксируй пропуск в verification.md.")
            continue
        if rc < 0:
            _lib.journal_skip("gate_lint", f"{command}: {tail}")
            notes.append(f"gate_lint: линтер '{command}' не удалось запустить ({tail}). "
                         "Зафиксируй пропуск в verification.md.")
            continue
        if rc != 0:
            return {"decision": "block",
                    "reason": f"Lint failed for {path} (exit {rc}):\n{tail}"}
    if notes:
        return {"decision": "allow", "additionalContext": "\n".join(notes)}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    _lib.emit(run(event or {}))


if __name__ == "__main__":
    main()
