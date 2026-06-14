#!/usr/bin/env python3
"""Build gate: run the configured build command on Stop, but only when
production code actually changed in the working tree — Stop fires on every
assistant turn and a full build per turn is unacceptable. Triggering off the
working tree (not the agent's message) closes the red-team bypass where
omitting a path from the final message silently skipped the build.

Deterministic -> may block. The router's stop budget (2 blocks, then degrade)
caps repeated failures."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib


def run(event):
    if not _lib.changed_code_files():
        return {"decision": "allow"}
    config = _lib.load_quality_gates().get("build") or {}
    command = (config.get("command") or "").strip()
    if not command:
        # shipped default is an empty command: allow silently (same as lint)
        return {"decision": "allow"}
    timeout = config.get("timeout_seconds", 600)
    timeout = max(1, timeout) if isinstance(timeout, (int, float)) else 600
    # ceiling below the 630s Stop hook timeout: past it the harness kills the
    # router mid-build and the gate would block instead of advising
    timeout = min(timeout, 620)
    rc, tail = _lib.run_command(command, timeout)
    if rc == -2:
        _lib.journal_skip("gate_build", f"{command}: timed out")
        return {"decision": "allow", "additionalContext": (
            f"gate_build: сборка '{command}' превысила таймаут {timeout}s. "
            "Зафиксируй пропуск в verification.md.")}
    if rc < 0:
        _lib.journal_skip("gate_build", f"{command}: {tail}")
        return {"decision": "allow", "additionalContext": (
            f"gate_build: сборку '{command}' не удалось запустить ({tail}). "
            "Зафиксируй пропуск в verification.md.")}
    if rc != 0:
        return {"decision": "block", "reason": f"Build failed (exit {rc}):\n{tail}"}
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    _lib.emit(run(event or {}))


if __name__ == "__main__":
    main()
