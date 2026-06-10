#!/usr/bin/env python3
"""Hook probe: log raw hook events to verify GigaCode's real event/tool names.

Register temporarily for any event in .gigacode/settings.json:
    {"type": "command", "command": "python .gigacode/hooks/hook_probe.py"}
Then exercise the flow and inspect .gigacode/logs/hook-probe.jsonl.
Always answers "allow"; never blocks anything.
"""
import json
import os
import sys
import time

LOGS_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs"))


def main():
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "raw": raw}
    try:
        event = json.loads(raw)
        record["hook_event_name"] = event.get("hook_event_name", "")
        record["tool_name"] = event.get("tool_name", "")
        record["keys"] = sorted(event.keys())
    except json.JSONDecodeError as exc:
        record["parse_error"] = str(exc)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(os.path.join(LOGS_DIR, "hook-probe.jsonl"), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass
    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
