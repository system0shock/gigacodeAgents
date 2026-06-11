#!/usr/bin/env python3
"""Offline tests for the hook router. Run from the repo root: python scripts/test_router.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTER = os.path.join(ROOT, ".gigacode", "hooks", "router.py")
HOOKS_DIR = os.path.join(ROOT, ".gigacode", "hooks")
PASSED = 0


def run_router(event_name, payload, router=ROUTER, bom=False, raw=None, extra_args=None):
    """Run the router subprocess.

    raw: if provided, send these bytes as stdin instead of json.dumps(payload).
    extra_args: optional list of extra CLI arguments appended after --event NAME.
    """
    if raw is not None:
        data = raw
    else:
        data = json.dumps(payload).encode("utf-8")
        if bom:
            data = b"\xef\xbb\xbf" + data
    cmd = [sys.executable, router, "--event", event_name]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.run(
        cmd,
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    if proc.returncode != 0:
        raise SystemExit(f"router exited {proc.returncode}: {proc.stderr.decode()}")
    return json.loads(proc.stdout.decode("utf-8"))


def check(name, condition, detail=""):
    # FIX 6: explicit raise so python -O cannot neuter the suite
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


def temp_hooks_copy():
    tmp = tempfile.mkdtemp(prefix="router-test-")
    shutil.copytree(HOOKS_DIR, os.path.join(tmp, "hooks"))
    return tmp, os.path.join(tmp, "hooks", "router.py"), os.path.join(tmp, "hooks", "router.config.json")


def main():
    # 1. Destructive git through BOM-prefixed stdin is blocked
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git -C . reset --hard HEAD"}}, bom=True)
    check("bom_destructive_block", result["decision"] == "block", result)

    # 2. Benign git command is allowed
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git status --short"}})
    check("benign_allow", result["decision"] == "allow", result)

    # 3. Unmatched tool produces allow without running gates
    result = run_router("PreToolUse", {"tool_name": "ReadFile", "tool_input": {"path": "README.md"}})
    check("unmatched_tool_allow", result["decision"] == "allow", result)

    # 4. Protected path write asks
    result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": ".github/workflows/deploy.yml"}})
    check("protected_path_ask", result["decision"] == "ask", result)

    # 5. Valid plan-only feature prompt allowed
    result = run_router("UserPromptSubmit", {"prompt": "/develop-feature plan-only payment retry"})
    check("preflight_allow", result["decision"] == "allow", result)

    # 6. Stop with missing artifacts blocks
    # Unique session id: the stop budget counts consecutive blocks per session,
    # so reusing one id would degrade to allow on the third smoke run.
    session = f"t-main-{os.getpid()}-{int(time.time())}"
    result = run_router("Stop", {"last_assistant_message": "Complete in docs/development/sample-task/", "session_id": session})
    check("stop_missing_artifacts_block", result["decision"] == "block", result)

    # 7. Decisions journal is written
    journal = os.path.join(ROOT, ".gigacode", "logs", "decisions.jsonl")
    check("journal_written", os.path.exists(journal) and os.path.getsize(journal) > 0, journal)

    # 8. Corrupt config soft-blocks with escape hatch
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    with open(tmp_config, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, router=tmp_router)
    check("config_error_block", result["decision"] == "block" and "disableAllHooks" in result.get("reason", ""), result)
    shutil.rmtree(tmp, ignore_errors=True)

    # 9. Missing safety-critical gate soft-blocks with escape hatch
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    with open(tmp_config, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "stop_block_budget": 2, "routes": [
            {"event": "PreToolUse", "tool_pattern": "^Bash$", "gates": ["nonexistent_gate"], "safety_critical": True}
        ]}, handle)
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, router=tmp_router)
    check("missing_gate_soft_block", result["decision"] == "block" and "disableAllHooks" in result.get("reason", ""), result)

    # 10. Missing non-critical gate degrades to allow
    with open(tmp_config, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "stop_block_budget": 2, "routes": [
            {"event": "PreToolUse", "tool_pattern": "^Bash$", "gates": ["nonexistent_gate"]}
        ]}, handle)
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, router=tmp_router)
    check("missing_gate_noncritical_allow", result["decision"] == "allow", result)
    shutil.rmtree(tmp, ignore_errors=True)

    # 11. Stop budget: third consecutive block degrades to warning
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    payload = {"last_assistant_message": "Complete in docs/development/sample-task/", "session_id": "t-budget"}
    first = run_router("Stop", payload, router=tmp_router)
    second = run_router("Stop", payload, router=tmp_router)
    third = run_router("Stop", payload, router=tmp_router)
    check("stop_budget_first_block", first["decision"] == "block", first)
    check("stop_budget_second_block", second["decision"] == "block", second)
    check("stop_budget_third_degrades", third["decision"] == "allow" and "systemMessage" in third, third)

    # FIX 4: stop-budget reset — an allow-Stop clears the counter; next block restarts budget
    allow_payload = {"last_assistant_message": "hello", "session_id": "t-budget"}
    reset_result = run_router("Stop", allow_payload, router=tmp_router)
    check("stop_budget_reset_allow", reset_result["decision"] == "allow", reset_result)
    # After reset, same blocking payload must block again (not degrade)
    restart_first = run_router("Stop", payload, router=tmp_router)
    check("stop_budget_restart_blocks", restart_first["decision"] == "block", restart_first)

    shutil.rmtree(tmp, ignore_errors=True)

    # 12. Latency: full router run on a benign PreToolUse sample
    start = time.monotonic()
    run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git status --short"}})
    elapsed_ms = (time.monotonic() - start) * 1000
    print(f"latency: {elapsed_ms:.0f} ms (budget 200 ms, hard limit 1000 ms)")
    check("latency_hard_limit", elapsed_ms < 1000, f"{elapsed_ms:.0f} ms")
    if elapsed_ms > 200:
        print(f"WARNING: latency {elapsed_ms:.0f} ms exceeds the 200 ms design budget")

    # 13. Size limits: router and every gate below 10,000 characters
    for path in [ROUTER] + [os.path.join(HOOKS_DIR, "gates", name) for name in os.listdir(os.path.join(HOOKS_DIR, "gates")) if name.endswith(".py")]:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        check(f"size_{os.path.basename(path)}", len(content) < 10000, f"{len(content)} chars")

    # 14. Config references only existing gate files
    with open(os.path.join(HOOKS_DIR, "router.config.json"), "r", encoding="utf-8") as handle:
        config = json.load(handle)
    for route in config["routes"]:
        for gate in route["gates"]:
            gate_path = os.path.join(HOOKS_DIR, "gates", gate + ".py")
            check(f"gate_exists_{gate}", os.path.exists(gate_path), gate_path)

    # FIX 3a: garbage stdin → allow, exit 0
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    result = run_router("PreToolUse", None, router=tmp_router, raw=b"{not json")
    check("garbage_stdin_allow", result["decision"] == "allow", result)

    # FIX 3b: non-dict JSON (null) stdin → allow, exit 0
    result = run_router("Stop", None, router=tmp_router, raw=b"null")
    check("non_dict_stdin_allow", result["decision"] == "allow", result)

    # FIX 3c: invalid regex config → fail-closed block with disableAllHooks, exit 0
    with open(tmp_config, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "stop_block_budget": 2, "routes": [
            {"event": "PreToolUse", "tool_pattern": "^(Bash",
             "gates": ["git_guard"], "safety_critical": True}
        ]}, handle)
    bad_regex_payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}}
    ).encode("utf-8")
    result = run_router("PreToolUse", None, router=tmp_router, raw=bad_regex_payload)
    check("invalid_regex_fail_closed",
          result["decision"] == "block" and "disableAllHooks" in result.get("reason", ""),
          result)

    shutil.rmtree(tmp, ignore_errors=True)

    # FIX 3d: unknown CLI arg → exit 0, decision allow (argparse exit 2 is gone)
    # Use a fresh temp copy with a valid config to isolate from the bad-regex config above
    tmp2, tmp_router2, _ = temp_hooks_copy()
    benign = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    ).encode("utf-8")
    result = run_router("PreToolUse", None, router=tmp_router2, raw=benign,
                        extra_args=["--bogus"])
    check("unknown_arg_no_abort", result["decision"] == "allow", result)
    shutil.rmtree(tmp2, ignore_errors=True)

    # 15. agent_pattern routes match the subagent type
    tmp3, tmp_router3, tmp_config3 = temp_hooks_copy()
    with open(tmp_config3, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "stop_block_budget": 2, "routes": [
            {"event": "SubagentStart", "agent_pattern": "^coder$",
             "gates": ["nonexistent_gate"], "safety_critical": True}
        ]}, handle)
    result = run_router("SubagentStart", {"agent_type": "coder"}, router=tmp_router3)
    check("agent_pattern_match", result["decision"] == "block", result)
    result = run_router("SubagentStart", {"agent_type": "verifier"}, router=tmp_router3)
    check("agent_pattern_no_match", result["decision"] == "allow", result)
    # alternative field name fork-drift tolerance
    result = run_router("SubagentStart", {"subagent_type": "coder"}, router=tmp_router3)
    check("agent_pattern_alt_field", result["decision"] == "block", result)
    # invalid agent_pattern regex must fail-closed, same as tool_pattern
    with open(tmp_config3, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "stop_block_budget": 2, "routes": [
            {"event": "SubagentStart", "agent_pattern": "^(coder",
             "gates": ["nonexistent_gate"], "safety_critical": True}
        ]}, handle)
    result = run_router("SubagentStart", {"agent_type": "coder"}, router=tmp_router3)
    check("invalid_agent_pattern_fail_closed",
          result["decision"] == "block" and "disableAllHooks" in result.get("reason", ""),
          result)
    shutil.rmtree(tmp3, ignore_errors=True)

    # 16. Spec truth is write-protected through the full router path
    result = run_router("PreToolUse", {"tool_name": "WriteFile",
                                       "tool_input": {"file_path": "openspec/specs/payments/spec.md",
                                                      "content": "x"}})
    check("spec_truth_write_block", result["decision"] == "block", result)

    print(f"\nAll {PASSED} router checks passed")


if __name__ == "__main__":
    main()
