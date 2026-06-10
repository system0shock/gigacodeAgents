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


def run_router(event_name, payload, router=ROUTER, bom=False):
    data = json.dumps(payload).encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    proc = subprocess.run(
        [sys.executable, router, "--event", event_name],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    assert proc.returncode == 0, f"router exited {proc.returncode}: {proc.stderr.decode()}"
    return json.loads(proc.stdout.decode("utf-8"))


def check(name, condition, detail=""):
    global PASSED
    assert condition, f"{name}: {detail}"
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

    print(f"\nAll {PASSED} router checks passed")


if __name__ == "__main__":
    main()
