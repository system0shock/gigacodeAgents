#!/usr/bin/env python3
"""Build gate: run the configured build command on Stop, but only at
PR-readiness moments (the message mentions task artifacts) — Stop fires on
every assistant turn and a full build per turn is unacceptable.

Deterministic -> may block. The router's stop budget (2 blocks, then degrade)
caps repeated failures."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib


def run(event):
    message = _lib.message_from_event(event).replace("\\", "/")
    if "docs/development/" not in message and "openspec/changes" not in message:
        return {"decision": "allow"}
    config = _lib.load_quality_gates().get("build") or {}
    command = (config.get("command") or "").strip()
    if not command:
        _lib.journal_skip("gate_build", "build command not configured")
        return {"decision": "allow"}
    rc, tail = _lib.run_command(command, config.get("timeout_seconds", 600))
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
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
