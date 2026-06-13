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


def run_router(event_name, payload, router=ROUTER, bom=False, raw=None, extra_args=None, env=None):
    """Run the router subprocess.

    raw: if provided, send these bytes as stdin instead of json.dumps(payload).
    extra_args: optional list of extra CLI arguments appended after --event NAME.
    env: optional dict merged over os.environ for the child — e.g. GIGACODE_ROOT
         to point the gates' working-tree Stop triggers at a controlled fixture.
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
    child_env = None
    if env:
        child_env = dict(os.environ)
        child_env.update(env)
    proc = subprocess.run(
        cmd,
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        env=child_env,
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


def make_code_fixture():
    """Temp git repo with a changed code file and NO openspec change, so the
    Stop gates (gate_spec_structure / validate_development_output) block
    deterministically. Point GIGACODE_ROOT here via run_router(env=...)."""
    tmp = tempfile.mkdtemp(prefix="router-code-")
    os.makedirs(os.path.join(tmp, "src"))
    with open(os.path.join(tmp, "src", "Foo.kt"), "w", encoding="utf-8") as handle:
        handle.write("class Foo\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "-A"], cwd=tmp, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return tmp


def make_clean_fixture():
    """Temp dir: no git repo, no changed code, no openspec change -> every Stop
    gate allows. Used to verify the budget counter resets on an allow."""
    return tempfile.mkdtemp(prefix="router-clean-")


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

    # 6. Stop with changed code but no OpenSpec change blocks (working-tree trigger).
    # GIGACODE_ROOT points the gates at a fixture repo; the message is irrelevant.
    # Unique session id: the stop budget counts consecutive blocks per session,
    # so reusing one id would degrade to allow on the third smoke run.
    session = f"t-main-{os.getpid()}-{int(time.time())}"
    code_fix = make_code_fixture()
    result = run_router("Stop", {"last_assistant_message": "Done.", "session_id": session},
                        env={"GIGACODE_ROOT": code_fix})
    check("stop_missing_artifacts_block", result["decision"] == "block", result)
    shutil.rmtree(code_fix, ignore_errors=True)

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

    # 11. Stop budget: third consecutive block degrades to warning.
    # Budget state is isolated in the temp hooks copy (STATE_PATH follows the
    # router's own dir, NOT GIGACODE_ROOT); the block trigger comes from a
    # fixture repo with changed code and no OpenSpec change. The two concerns
    # are orthogonal, which is what makes this deterministic.
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    code_fix = make_code_fixture()
    code_env = {"GIGACODE_ROOT": code_fix}
    payload = {"last_assistant_message": "Done.", "session_id": "t-budget"}
    first = run_router("Stop", payload, router=tmp_router, env=code_env)
    second = run_router("Stop", payload, router=tmp_router, env=code_env)
    third = run_router("Stop", payload, router=tmp_router, env=code_env)
    check("stop_budget_first_block", first["decision"] == "block", first)
    check("stop_budget_second_block", second["decision"] == "block", second)
    check("stop_budget_third_degrades", third["decision"] == "allow" and "systemMessage" in third, third)

    # FIX 4: stop-budget reset — an allow-Stop clears the counter; next block
    # restarts the budget. A clean fixture (no changed code) makes the gates allow.
    clean_fix = make_clean_fixture()
    reset_result = run_router("Stop", payload, router=tmp_router, env={"GIGACODE_ROOT": clean_fix})
    check("stop_budget_reset_allow", reset_result["decision"] == "allow", reset_result)
    # After reset, the blocking fixture must block again (not degrade)
    restart_first = run_router("Stop", payload, router=tmp_router, env=code_env)
    check("stop_budget_restart_blocks", restart_first["decision"] == "block", restart_first)

    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(code_fix, ignore_errors=True)
    shutil.rmtree(clean_fix, ignore_errors=True)

    # 12. Latency: full router run on a benign PreToolUse sample
    start = time.monotonic()
    run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git status --short"}})
    elapsed_ms = (time.monotonic() - start) * 1000
    print(f"latency: {elapsed_ms:.0f} ms (budget 200 ms, hard limit 1000 ms)")
    check("latency_hard_limit", elapsed_ms < 1000, f"{elapsed_ms:.0f} ms")
    if elapsed_ms > 200:
        print(f"WARNING: latency {elapsed_ms:.0f} ms exceeds the 200 ms design budget")

    # 13. Size report: informational only — Python gate/router files may be any
    # size (there is no character cap). Each must still be non-empty and parse.
    import ast as _ast
    for path in [ROUTER] + [os.path.join(HOOKS_DIR, "gates", name) for name in os.listdir(os.path.join(HOOKS_DIR, "gates")) if name.endswith(".py")]:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        try:
            _ast.parse(content)
            parses = True
        except SyntaxError:
            parses = False
        print(f"size: {os.path.basename(path)} = {len(content)} chars")
        check(f"parses_{os.path.basename(path)}", bool(content.strip()) and parses, f"{len(content)} chars")

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

    # 17. git_guard hardening — destructive git through wrappers/chaining/quoting MUST block
    GUARD_BLOCK = [
        # chaining / wrappers / env-prefix / abs-path / .exe (finding C1)
        "cd repo && git reset --hard",
        "true; git reset --hard",
        "(git reset --hard)",
        "env GIT_DIR=.git git reset --hard",
        "GIT_DIR=x git push --force origin main",
        "bash -c \"git reset --hard\"",
        "/usr/bin/git reset --hard",
        "git.exe reset --hard",
        # quoting (posix=False kept quote chars)
        "git reset \"--hard\"",
        "git \"reset\" --hard",
        "git push \"--force\"",
        "git clean \"-f\" \"-d\"",
        # short force flag + plus-refspec
        "git push -f",
        "git push -f origin main",
        "git push origin +main",
        "git push origin +main:main",
        # wrappers with value-arguments (flag-value or positional) must still block
        "timeout 30 git reset --hard",
        "nice -n 10 git reset --hard",
        "sudo -u root git reset --hard",
        "ionice -c 2 git reset --hard",
        "stdbuf -o 0 git reset --hard",
        "nice -n 10 rm -rf .git",
        # combined -c flag wrappers
        "bash -ce \"git reset --hard\"",
        "sh -ec \"git clean -fd\"",
        # uncovered destructive subcommands
        "git update-ref -d refs/heads/main",
        "git reflog expire --expire=now --all",
        "git gc --prune=now",
        "git checkout -- src/",
        "git restore --worktree .",
        "git push origin --mirror",
        "git worktree remove --force wt",
        "git stash clear",
        "git filter-branch --force --all",
        # non-git repo destruction (Windows-primary)
        "Remove-Item -Recurse -Force .git",
        "rm -r .git",
        "cmd /c rmdir /s /q .git",
    ]
    for cmd in GUARD_BLOCK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"guard_block::{cmd[:38]}", result["decision"] == "block", (cmd, result))

    # 18. Shell writes to protected / openspec-truth / enforcement paths
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "echo x > .gigacode/hooks/gates/git_guard.py"}})
    check("guard_shell_self_block", result["decision"] == "block", result)
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "cp evil openspec/specs/auth/spec.md"}})
    check("guard_shell_openspec_block", result["decision"] == "block", result)
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "printf x >> .env"}})
    check("guard_shell_protected_ask", result["decision"] in ("ask", "block"), result)
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "echo x > .github/workflows/deploy.yml"}})
    check("guard_shell_ci_ask", result["decision"] in ("ask", "block"), result)

    # 19. WriteFile/Edit to enforcement-owned paths MUST block (self-protection).
    # The logs/* entries are the PRIMARY closure of the Stop-budget-seed and
    # journal-tamper findings: if the agent cannot write router-state.json, it
    # cannot pre-seed the budget counter regardless of load_state sanitizing.
    for p in (".gigacode/hooks/gates/git_guard.py", ".gigacode/hooks/router.config.json",
              ".gigacode/quality-gates.json", ".gigacode/settings.json",
              ".gigacode/logs/router-state.json", ".gigacode/logs/decisions.jsonl"):
        result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": p}})
        check(f"guard_self::{p[-24:]}", result["decision"] == "block", (p, result))
    # and via shell redirection (the no-file_path channel)
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "echo {} > .gigacode/logs/router-state.json"}})
    check("guard_shell_state_block", result["decision"] == "block", result)

    # 20. Benign controls MUST still allow (no over-blocking regressions)
    GUARD_ALLOW = [
        "git status --short", "git diff", "git log --oneline -5", "git fetch origin",
        "git add .", "git commit -m wip", "git push origin feature/x",
        "git checkout -b feature/new", "git checkout main", "git switch main",
        "git restore --staged file.kt", "git stash", "git stash pop",
        "git reset --soft HEAD~1", "git reset file.kt", "git clean -n", "git clean -fn",
        "timeout 30 git status", "nice -n 5 git diff", "sudo -i git status",
        "git reflog", "git reflog show", "git gc --auto", "git gc",
        "echo hello", "ls -la", "cat README.md", "cp a.txt b.txt", "rm build/tmp.o",
    ]
    for cmd in GUARD_ALLOW:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"guard_allow::{cmd[:38]}", result["decision"] == "allow", (cmd, result))
    # benign source write still allowed
    result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": "src/Foo.kt"}})
    check("guard_allow_src_write", result["decision"] == "allow", result)

    # 21. Pre-seeded budget counter must NOT pre-exhaust the budget
    # STATE_PATH in router.py: LOGS_DIR = hooks/../logs  =>  tmp/logs/router-state.json
    tmp4, tmp_router4, _ = temp_hooks_copy()
    state_path = os.path.join(tmp4, "logs", "router-state.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump({"stop:t-seed": 99}, handle)
    code_fix = make_code_fixture()
    payload = {"last_assistant_message": "Done.", "session_id": "t-seed"}
    result = run_router("Stop", payload, router=tmp_router4, env={"GIGACODE_ROOT": code_fix})
    check("budget_preseed_still_blocks", result["decision"] == "block", result)
    shutil.rmtree(tmp4, ignore_errors=True)
    shutil.rmtree(code_fix, ignore_errors=True)

    print(f"\nAll {PASSED} router checks passed")


if __name__ == "__main__":
    main()
