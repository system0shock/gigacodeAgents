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
CONTEXT_GATE = ("def run(event):\n"
                "    return {'decision': 'allow', 'additionalContext': 'ctx-marker'}\n")


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
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join(self.hooks, "router.py"), *args],
                input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        except subprocess.TimeoutExpired:
            raise SystemExit("FAIL harness: router timed out (>60s)")
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
            {"event": "PreToolUse", "tool_pattern": "^(WriteFile|Edit|NotebookEdit)$",
             "gates": ["fixture_block"]},
            {"event": "SubagentStart", "agent_pattern": "^(code-mapping|documentation)$",
             "gates": ["fixture_block"]},
            {"event": "SessionStart", "gates": ["fixture_context"]}]})
        sb.gate("fixture_block", BLOCK_GATE)
        sb.gate("fixture_context", CONTEXT_GATE)
        check("rt_tool_match", sb.run({"hook_event_name": "PreToolUse",
                                       "tool_name": "Edit"})["decision"] == "block")
        pre = sb.run({"hook_event_name": "PreToolUse", "tool_name": "Edit"})
        phso = pre.get("hookSpecificOutput", {})
        check("rt_pretool_permissiondecision",
              phso.get("permissionDecision") == "deny"
              and phso.get("hookEventName") == "PreToolUse", repr(pre))
        # An allow PreToolUse MUST NOT carry permissionDecision — emitting one
        # auto-approves the call and silently nullifies the user's permissions.ask.
        allow_pre = sb.run({"hook_event_name": "PreToolUse", "tool_name": "MyEdit"})
        check("rt_pretool_allow_no_pd",
              allow_pre["decision"] == "allow" and "permissionDecision" not in allow_pre.get("hookSpecificOutput", {}),
              repr(allow_pre))
        check("rt_tool_anchored", sb.run({"hook_event_name": "PreToolUse",
                                          "tool_name": "MyEdit"})["decision"] == "allow")
        # Qwen/GigaCode raw tool ids normalize to the canonical names the
        # tool_pattern matches on. write_file -> WriteFile must route + block.
        check("rt_raw_write_file_normalized",
              sb.run({"hook_event_name": "PreToolUse",
                      "tool_name": "write_file"})["decision"] == "block")
        check("rt_raw_replace_normalized",
              sb.run({"hook_event_name": "PreToolUse",
                      "tool_name": "replace"})["decision"] == "block")
        check("rt_notebookedit_routes",
              sb.run({"hook_event_name": "PreToolUse",
                      "tool_name": "NotebookEdit"})["decision"] == "block")
        check("rt_agent_match", sb.run({"hook_event_name": "SubagentStart",
                                        "agent_type": "documentation"})["decision"] == "block")
        check("rt_agent_missing_skips",
              sb.run({"hook_event_name": "SubagentStart"})["decision"] == "allow")
        ctx = sb.run({"hook_event_name": "SessionStart"})
        check("rt_context_passthrough",
              ctx["decision"] == "allow" and ctx.get("additionalContext") == "ctx-marker",
              repr(ctx))
        # GigaCode/Claude-style consumers read injected context from
        # hookSpecificOutput.additionalContext; the router must mirror it there
        # (keeping the top-level field) or context-inject silently delivers nothing.
        hso = ctx.get("hookSpecificOutput", {})
        check("rt_context_hookspecific",
              hso.get("additionalContext") == "ctx-marker"
              and hso.get("hookEventName") == "SessionStart", repr(ctx))


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
        pre_file_routes = [r for r in config.get("routes", [])
                           if r.get("event") == "PreToolUse"
                           and set(r.get("gates", [])) & {"git_guard", "gate_spec_bootstrap"}
                           and "WriteFile" in (r.get("tool_pattern") or "")]
        for r in pre_file_routes:
            check(f"rt_notebookedit_wired:{','.join(r['gates'])}",
                  "NotebookEdit" in (r.get("tool_pattern") or ""),
                  r.get("tool_pattern"))
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
