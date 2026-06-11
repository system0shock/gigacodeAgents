#!/usr/bin/env python3
"""Offline tests for the analytics hook router. Run from modules/analytics:
    python scripts/test_router.py
Copies .gigacode/hooks into a temp sandbox so journal/state writes never
touch the working tree; drives router.py via subprocess."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_SRC = os.path.join(ROOT, ".gigacode", "hooks")
PASSED = 0

ALLOW_GATE = "def run(event):\n    return {'decision': 'allow'}\n"
BLOCK_GATE = "def run(event):\n    return {'decision': 'block', 'reason': 'fixture block'}\n"
CRASH_GATE = "def run(event):\n    raise RuntimeError('boom')\n"
BAD_GATE = "def run(event):\n    return ['nope']\n"


def check(name, condition, detail=""):
    # explicit raise (not assert) so python -O cannot neuter the suite
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


class Sandbox:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="arouter-")
        self.hooks = os.path.join(self.tmp, "hooks")
        shutil.copytree(HOOKS_SRC, self.hooks)
        config = os.path.join(self.hooks, "router.config.json")
        if os.path.exists(config):
            os.remove(config)  # each test writes its own
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def config(self, data):
        path = os.path.join(self.hooks, "router.config.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(data if isinstance(data, str) else json.dumps(data))

    def gate(self, name, body):
        path = os.path.join(self.hooks, "gates", name + ".py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)

    def run(self, payload, args=()):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        proc = subprocess.run(
            [sys.executable, os.path.join(self.hooks, "router.py"), *args],
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            raise SystemExit(f"router exit {proc.returncode}: {proc.stderr.decode(errors='replace')}")
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            raise SystemExit(f"router emitted non-JSON: {out!r}")


def test_stdin_safety():
    with Sandbox() as sb:
        sb.config({"version": 1, "routes": [
            {"event": "UserPromptSubmit", "gates": ["fixture_block"]}]})
        sb.gate("fixture_block", BLOCK_GATE)
        bom = b"\xef\xbb\xbf" + json.dumps({"hook_event_name": "UserPromptSubmit"}).encode("utf-8")
        check("rt_bom_parsed", sb.run(bom)["decision"] == "block")
        check("rt_garbage_allow", sb.run(b"not json")["decision"] == "allow")
        check("rt_nondict_allow", sb.run(b"[1, 2]")["decision"] == "allow")
        check("rt_unknown_args", sb.run({"hook_event_name": "Other"},
                                        args=("--weird", "x"))["decision"] == "allow")


def test_config_failclosed():
    with Sandbox() as sb:
        check("rt_missing_config",
              sb.run({"hook_event_name": "Stop"})["decision"] == "block")
        sb.config("{broken")
        check("rt_broken_config",
              sb.run({"hook_event_name": "Stop"})["decision"] == "block")


def test_routing():
    with Sandbox() as sb:
        sb.config({"version": 1, "routes": [
            {"event": "PreToolUse", "tool_pattern": "^(WriteFile|Edit)$",
             "gates": ["fixture_block"]},
            {"event": "SubagentStart", "agent_pattern": "^(code-mapping|documentation)$",
             "gates": ["fixture_block"]}]})
        sb.gate("fixture_block", BLOCK_GATE)
        check("rt_tool_match", sb.run({"hook_event_name": "PreToolUse",
                                       "tool_name": "Edit"})["decision"] == "block")
        check("rt_tool_anchored", sb.run({"hook_event_name": "PreToolUse",
                                          "tool_name": "MyEdit"})["decision"] == "allow")
        check("rt_agent_match", sb.run({"hook_event_name": "SubagentStart",
                                        "agent_type": "documentation"})["decision"] == "block")
        check("rt_agent_missing_skips",
              sb.run({"hook_event_name": "SubagentStart"})["decision"] == "allow")


def test_gate_failures():
    with Sandbox() as sb:
        sb.config({"version": 1, "routes": [
            {"event": "PreToolUse", "tool_pattern": "^Bash$",
             "gates": ["fixture_crash"], "safety_critical": True},
            {"event": "PostToolUse", "gates": ["fixture_crash"]},
            {"event": "Notification", "gates": ["fixture_bad"]}]})
        sb.gate("fixture_crash", CRASH_GATE)
        sb.gate("fixture_bad", BAD_GATE)
        check("rt_critical_crash_blocks",
              sb.run({"hook_event_name": "PreToolUse", "tool_name": "Bash"})["decision"] == "block")
        check("rt_noncritical_crash_allows",
              sb.run({"hook_event_name": "PostToolUse", "tool_name": "Edit"})["decision"] == "allow")
        check("rt_bad_result_allows",
              sb.run({"hook_event_name": "Notification"})["decision"] == "allow")


def test_stop_budget():
    with Sandbox() as sb:
        sb.config({"version": 1, "stop_block_budget": 1, "routes": [
            {"event": "Stop", "gates": ["fixture_block"]}]})
        sb.gate("fixture_block", BLOCK_GATE)
        ev = {"hook_event_name": "Stop", "session_id": "s1"}
        check("rt_stop_first_blocks", sb.run(ev)["decision"] == "block")
        degraded = sb.run(ev)
        check("rt_stop_degrades", degraded["decision"] == "allow"
              and "systemMessage" in degraded, repr(degraded))
        sb.gate("fixture_block", ALLOW_GATE)
        check("rt_stop_allow_resets", sb.run(ev)["decision"] == "allow")
        sb.gate("fixture_block", BLOCK_GATE)
        check("rt_stop_counts_again", sb.run(ev)["decision"] == "block")


def test_real_config():
    # No size checks: the 10k-character limit applies to agent .md files only,
    # not to Python scripts (user decision 2026-06-11).
    config_path = os.path.join(HOOKS_SRC, "router.config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
        for route in config.get("routes", []):
            for gate in route.get("gates", []):
                check(f"rt_gate_exists:{gate}",
                      os.path.exists(os.path.join(HOOKS_SRC, "gates", gate + ".py")))
    else:
        print("skip: router.config.json not wired yet")


def main():
    test_stdin_safety()
    test_config_failclosed()
    test_routing()
    test_gate_failures()
    test_stop_budget()
    test_real_config()
    print(f"All {PASSED} router checks passed")


if __name__ == "__main__":
    main()
