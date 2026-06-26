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

    # 1b. A PreToolUse block must reach the runtime as permissionDecision=deny
    # (Qwen/GigaCode ignores the legacy top-level decision for PreToolUse).
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}})
    hso = result.get("hookSpecificOutput", {})
    check("pretool_permissiondecision_deny",
          hso.get("permissionDecision") == "deny" and hso.get("hookEventName") == "PreToolUse", result)
    # 1b2. A benign/allow PreToolUse MUST NOT carry a permissionDecision —
    # emitting one auto-approves the call and silently nullifies permissions.ask.
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git status --short"}})
    check("pretool_allow_no_permissiondecision",
          result["decision"] == "allow" and "permissionDecision" not in result.get("hookSpecificOutput", {}), result)
    # 1b3. An ask decision must carry permissionDecision=ask (not allow or deny).
    result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": ".qwen/settings.json"}})
    check("pretool_ask_permissiondecision",
          result.get("hookSpecificOutput", {}).get("permissionDecision") == "ask", result)
    # 1c. SessionStart context must be mirrored into hookSpecificOutput.additionalContext
    result = run_router("SessionStart", {})
    hso = result.get("hookSpecificOutput", {})
    check("sessionstart_context_mirrored",
          bool(hso.get("additionalContext")) and hso.get("hookEventName") == "SessionStart", result)

    # 2. Benign git command is allowed
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "git status --short"}})
    check("benign_allow", result["decision"] == "allow", result)

    # 3. Unmatched tool produces allow without running gates
    result = run_router("PreToolUse", {"tool_name": "ReadFile", "tool_input": {"path": "README.md"}})
    check("unmatched_tool_allow", result["decision"] == "allow", result)

    # 3b. Raw Qwen tool ids are normalized before matching: run_shell_command ->
    # Bash routes to git_guard; write_file -> WriteFile hits self-protect.
    result = run_router("PreToolUse", {"tool_name": "run_shell_command", "tool_input": {"command": "git reset --hard"}})
    check("raw_shell_normalized_block", result["decision"] == "block", result)
    result = run_router("PreToolUse", {"tool_name": "write_file", "tool_input": {"file_path": ".gigacode/settings.json"}})
    check("raw_write_normalized_block", result["decision"] == "block", result)

    # 3c. S1: symbol-level MCP servers (Serena) mutate files through their OWN
    # tool ids, not write_file/replace, AND name the target in `relative_path`,
    # AND the MCP runtime prefixes the id (mcp__serena__...). All three are
    # normalized so the same PreToolUse gates (git_guard et al.) still fire —
    # else the agent could edit .gigacode or forge an approval marker via Serena.
    result = run_router("PreToolUse", {"tool_name": "replace_symbol_body",
                                       "tool_input": {"relative_path": ".gigacode/hooks/gates/git_guard.py",
                                                      "name_path": "main", "body": "pass"}})
    check("serena_replace_symbol_gigacode_block", result["decision"] == "block", result)
    result = run_router("PreToolUse", {"tool_name": "mcp__serena__create_text_file",
                                       "tool_input": {"relative_path": ".gigacode/approvals/x/intake.ok",
                                                      "content": "ok"}})
    check("serena_mcp_prefixed_forge_block", result["decision"] == "block", result)
    # read-only Serena tools must NOT be force-mapped to a write id (no over-block)
    result = run_router("PreToolUse", {"tool_name": "mcp__serena__find_symbol",
                                       "tool_input": {"name_path": "Foo"}})
    check("serena_readonly_allow", result["decision"] == "allow", result)

    # 3d. Serena's OWN shell tool must normalize to Bash and hit git_guard — else
    # the safety-critical shell guard runs ZERO gates (full bypass).
    result = run_router("PreToolUse", {"tool_name": "mcp__serena__execute_shell_command",
                                       "tool_input": {"command": "git push origin master --force"}})
    check("serena_shell_normalized_block", result["decision"] == "block", result)

    # 3e. An unmapped file-mutating MCP tool (not in TOOL_NAME_MAP) must still hit
    # the write gates via the mutator catch-all — no silent .gigacode/scope bypass.
    result = run_router("PreToolUse", {"tool_name": "mcp__fs__delete_file",
                                       "tool_input": {"file_path": ".gigacode/hooks/router.py"}})
    check("unmapped_mutator_gigacode_block", result["decision"] == "block", result)
    # ...but a read-only-named unmapped tool stays allow (no over-block).
    result = run_router("PreToolUse", {"tool_name": "mcp__fs__read_file",
                                       "tool_input": {"file_path": "README.md"}})
    check("unmapped_readonly_allow", result["decision"] == "allow", result)

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

    # 11. Stop blocks are PERSISTENT (no auto-degrade): consecutive blocks keep
    # blocking. Budget state is isolated in the temp hooks copy (STATE_PATH
    # follows the router's own dir, NOT GIGACODE_ROOT); the block trigger comes
    # from a fixture repo with changed code and no OpenSpec change. The two
    # concerns are orthogonal, which is what makes this deterministic.
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    code_fix = make_code_fixture()
    code_env = {"GIGACODE_ROOT": code_fix}
    payload = {"last_assistant_message": "Done.", "session_id": "t-budget"}
    first = run_router("Stop", payload, router=tmp_router, env=code_env)
    second = run_router("Stop", payload, router=tmp_router, env=code_env)
    third = run_router("Stop", payload, router=tmp_router, env=code_env)
    fourth = run_router("Stop", payload, router=tmp_router, env=code_env)
    check("stop_budget_first_block", first["decision"] == "block", first)
    check("stop_budget_second_block", second["decision"] == "block", second)
    # No degrade-to-allow: the third (and every later) consecutive block blocks.
    check("stop_budget_third_still_blocks",
          third["decision"] == "block" and "systemMessage" not in third, third)
    check("stop_budget_fourth_still_blocks", fourth["decision"] == "block", fourth)

    # stop-budget reset — an allow-Stop clears the counter (the clamp + counter
    # still track consecutive blocks for journaling/reset). A clean fixture (no
    # changed code) makes the gates allow.
    clean_fix = make_clean_fixture()
    reset_result = run_router("Stop", payload, router=tmp_router, env={"GIGACODE_ROOT": clean_fix})
    check("stop_budget_reset_allow", reset_result["decision"] == "allow", reset_result)
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

    # 16. Spec-truth write now ASKs (the legitimate /opsx:sync /opsx:archive
    # lifecycle writes it; a direct edit still needs human confirmation)
    result = run_router("PreToolUse", {"tool_name": "WriteFile",
                                       "tool_input": {"file_path": "openspec/specs/payments/spec.md",
                                                      "content": "x"}})
    check("spec_truth_write_ask", result["decision"] == "ask", result)

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
        # [5] git rm/mv of an enforcement path (git was exempt from the catch-all
        # and git_destructive lacked rm/mv — analytics handled it, dev did not).
        "git rm -rf .gigacode",
        "git rm -f .gigacode/hooks/router.py",
        "git mv .gigacode/hooks/router.py /tmp/x",
        # [13] cd into the enforcement tree then write via a now-relative path
        # (cd was allow-listed, so the catch-all never saw the .gigacode target).
        "cd .gigacode/approvals && echo {} > demo/intake.ok",
        "cd .gigacode && echo x > hooks/router.py",
        "pushd .gigacode/approvals && echo {} > demo/contract.ok",
        # [17] forge the machine-owned verdict via the shell channel (docs/
        # development is not under .gigacode, so it was unprotected on shell).
        "echo {\"result\":\"pass\"} > docs/development/demo/verdict.json",
        "printf x > docs/development/demo/verdict.json",
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
    check("guard_shell_openspec_ask", result["decision"] == "ask", result)
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "printf x >> .env"}})
    check("guard_shell_protected_ask", result["decision"] == "ask", result)
    result = run_router("PreToolUse", {"tool_name": "Bash",
                        "tool_input": {"command": "echo x > .github/workflows/deploy.yml"}})
    check("guard_shell_ci_ask", result["decision"] == "ask", result)
    # .qwen holds disableAllHooks; writing it must ASK (not silently allow).
    result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": ".qwen/settings.json"}})
    check("qwen_write_ask", result["decision"] == "ask", result)
    result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "echo x > .qwen/settings.json"}})
    check("qwen_shell_ask", result["decision"] == "ask", result)

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
    # #11 the REAL Claude Code write tools must route to git_guard too (superset
    # matcher), not just the Qwen-fork WriteFile/Edit names.
    for tool in ("Write", "MultiEdit", "NotebookEdit"):
        result = run_router("PreToolUse", {"tool_name": tool,
                            "tool_input": {"file_path": ".gigacode/hooks/router.py"}})
        check(f"route_self::{tool}", result["decision"] == "block", (tool, result))
        result = run_router("PreToolUse", {"tool_name": tool,
                            "tool_input": {"file_path": "src/Foo.kt"}})
        check(f"route_allow::{tool}", result["decision"] == "allow", (tool, result))

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

    # 21. A pre-seeded budget counter must NOT pre-exhaust the budget. The clamp
    # min(prior, budget-1)+1 keeps the first block a block for ANY seed value,
    # including the boundary range [budget, 10] that load_state's 0..10 window
    # admits (99 is dropped by load_state; 2/5/10 are clamped). No degrade path.
    # STATE_PATH in router.py: LOGS_DIR = hooks/../logs  =>  tmp/logs/router-state.json
    tmp4, tmp_router4, _ = temp_hooks_copy()
    state_path = os.path.join(tmp4, "logs", "router-state.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    code_fix = make_code_fixture()
    for seed in (2, 5, 10, 99):
        with open(state_path, "w", encoding="utf-8") as handle:
            json.dump({"stop:t-seed": seed}, handle)
        payload = {"last_assistant_message": "Done.", "session_id": "t-seed"}
        result = run_router("Stop", payload, router=tmp_router4, env={"GIGACODE_ROOT": code_fix})
        check(f"budget_preseed_still_blocks::{seed}",
              result["decision"] == "block" and "systemMessage" not in result, (seed, result))
    shutil.rmtree(tmp4, ignore_errors=True)
    shutil.rmtree(code_fix, ignore_errors=True)

    # 22. Round-2 hardening (T6 review): wrapper / redirect / deletion /
    # substitution bypasses that MUST now block.
    R2_BLOCK = [
        # #1 `command` builtin was a universal kill-switch
        "command git reset --hard", "command rm -rf .git",
        # PR review P1: git restore defaults to --worktree (discards edits)
        "git restore .", "git restore src/Foo.kt", "git restore --worktree .",
        # #2 writes that corrupt the .git repo
        "echo x > .git/config", "cp evil .git/config", "echo x | tee .git/config",
        # #4 deletion of the enforcement tree / openspec truth; find -delete
        "rm -rf .gigacode", "find .git -delete", "find .gigacode -delete",
        # #6 PowerShell write-cmdlets to self-protect (.gigacode)
        "Set-Content .gigacode/settings.json x", "Out-File .gigacode/settings.json",
        "Add-Content .gigacode/hooks/gates/git_guard.py x",
        # #7 fd-prefixed / clobber redirects + writer programs
        "echo x 1> .gigacode/settings.json",
        "dd if=/tmp/evil of=.gigacode/hooks/router.py",
        "sed -i s/a/b/ .gigacode/hooks/router.py",
        "cat evil >| .gigacode/hooks/gates/git_guard.py",
        # #8 WRITE_VERB destination spoofed by a trailing / stdin redirect
        "cp evil.txt .gigacode/settings.json 2>/dev/null",
        "tee .gigacode/hooks/gates/git_guard.py < /tmp/evil",
        # #9 eval / command-substitution / env -S hiding a destructive git
        'eval "git reset --hard"', "x=$(git reset --hard)",
        "echo `git reset --hard`", "env -S 'git reset --hard'",
        # #12 NBSP separators (PowerShell primary platform)
        "git reset --hard",
    ]
    for cmd in R2_BLOCK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r2_block::{cmd[:32]}", result["decision"] == "block", (cmd, result))

    # #3 absolute-path writes to enforcement-owned paths MUST block (component-
    # aware, not start-anchored). Claude Code passes absolute file_path by default.
    for p in ("C:/proj/.worktrees/x/.gigacode/settings.json",
              "/home/u/proj/.gigacode/hooks/router.py", "C:/proj/.git/config"):
        result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": p}})
        check(f"r2_self_abs::{p[-20:]}", result["decision"] == "block", (p, result))

    # protected paths via the new write channels MUST ask
    R2_ASK = ["Set-Content .env x", "echo x 1> .github/workflows/deploy.yml",
              "Out-File secrets/key.pem",
              # openspec truth now ASKs (the /opsx sync/archive lifecycle writes it)
              "Set-Content openspec/specs/auth/spec.md x",
              "cp evil openspec/changes/archive/x/spec.md"]
    for cmd in R2_ASK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r2_ask::{cmd[:32]}", result["decision"] == "ask", (cmd, result))

    # benign controls MUST still allow (no over-block from the new parsing)
    R2_ALLOW = [
        "command ls", "command -v git", "exec ls -la", "eval ls",
        "Set-Content notes.txt hello", "Out-File build/log.txt",
        "dd if=a.img of=b.img", "sed -i s/a/b/ src/Foo.kt",
        "find . -name Foo.kt", "find src -type f",
        "echo x > out.txt", "cp a.txt b.txt 2>/dev/null",
        "git status", "tee out.log < in.txt",
    ]
    for cmd in R2_ALLOW:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r2_allow::{cmd[:32]}", result["decision"] == "allow", (cmd, result))

    # 22b. Backslash path-separator self-protect (WI-3 fix). On cmd/PowerShell a
    # backslash is a directory separator, but the posix tokenizer CONSUMED it,
    # collapsing `.gigacode\hooks\x` -> `.gigacodehooksx` and dodging the
    # self-protect catch-all (and cp/mv/rm path scans). _normalize_ws now folds a
    # path-separator backslash to "/" so the backslash spelling matches the
    # slash spelling. These MUST block:
    BS_BLOCK = [
        # the WI-22 self-approval vector: agent running confirm.py via backslashes
        "python .gigacode\\hooks\\confirm.py intake card",
        "cp evil .gigacode\\settings.json",
        "rm .gigacode\\hooks\\git_guard.py",
        "Set-Content .gigacode\\hooks\\router.py x",
        "mv a .git\\hooks\\pre-commit",
        "echo x > .git\\config",            # .git\config -> .git/config (GIT_DIR_LOOSE)
        "cp evil .gigacode\\hooks/x",       # mixed separators
    ]
    for cmd in BS_BLOCK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"bs_block::{cmd[:32]}", result["decision"] == "block", (cmd, result))

    # legitimate Windows backslash paths and look-alikes MUST still allow (the
    # fold must not over-block, and the LOOSE lookahead must reject .gigacoder /
    # .gitignore which are NOT enforcement paths):
    BS_ALLOW = [
        "cp src\\main.py build\\out.py",
        "git -C some\\dir status",
        "cat .gigacoder\\notes.txt",        # .gigacoder != .gigacode
        "type docs\\.gitignore.sample",     # .gitignore* != .git
    ]
    for cmd in BS_ALLOW:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"bs_allow::{cmd[:32]}", result["decision"] == "allow", (cmd, result))

    # 23. PR review round 3 (T6 follow-up): newly closed git_guard bypasses.
    R3_BLOCK = [
        # escaped quote must NOT swallow the && segment (\" is a literal quote)
        'echo \\" && git reset --hard',
        # process substitutions execute their contents
        "cat <(git reset --hard)",
        "tee >(git reset --hard) < x",
        # one-shot -c alias hiding a destructive subcommand (git + shell alias)
        "git -c alias.wipe='reset --hard' wipe",
        "git -c alias.x='!rm -rf .gigacode' x",
        # xargs replacement operand must be skipped, not taken as the command
        "printf x | xargs -I {} git reset --hard",
        # >& / &> redirection targets to enforcement paths (glued and spaced)
        "echo x >& .gigacode/settings.json",
        "echo x &> .gigacode/settings.json",
        "echo x >&.gigacode/settings.json",
        # checkout -f / switch --discard-changes / switch -f discard edits
        "git checkout -f main",
        "git switch --discard-changes main",
        "git switch -f main",
        # push to a protected branch by refspec (current-branch check misses these)
        "git push origin main",
        "git push origin HEAD:main",
        "git push origin HEAD:refs/heads/master",
    ]
    for cmd in R3_BLOCK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r3_block::{cmd[:34]}", result["decision"] == "block", (cmd, result))

    # case-altered self-protect paths (case-insensitive FS) MUST block
    for p in (".GIGACODE/settings.json", "C:/proj/.Git/config", ".Gigacode/hooks/router.py"):
        result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": p}})
        check(f"r3_self_case::{p[-20:]}", result["decision"] == "block", (p, result))

    # NotebookEdit identifies its target via notebook_path
    result = run_router("PreToolUse", {"tool_name": "NotebookEdit",
                        "tool_input": {"notebook_path": ".gigacode/x.ipynb"}})
    check("r3_notebook_self_block", result["decision"] == "block", result)
    result = run_router("PreToolUse", {"tool_name": "NotebookEdit",
                        "tool_input": {"notebook_path": "notebooks/clean.ipynb"}})
    check("r3_notebook_clean_allow", result["decision"] == "allow", result)

    # absolute protected (deploy / k8s / config-prod) paths MUST ask, not allow
    for p in ("/home/u/proj/deploy/foo.yml", "/home/u/proj/k8s/x.yml",
              "/home/u/proj/config/prod/app.yml"):
        result = run_router("PreToolUse", {"tool_name": "WriteFile", "tool_input": {"file_path": p}})
        check(f"r3_abs_protected::{p[-18:]}", result["decision"] == "ask", (p, result))

    # benign new forms MUST still allow (no over-block from the round-3 parsing)
    R3_ALLOW = [
        "git push origin feature/x", "git push origin HEAD:feature/x",
        "git checkout -b feature/new", "git switch -c feature/new",
        "git -c user.name=x commit -m y", "xargs -n 4 echo",
        "cat <(git status)", "echo x >&2", "ls 2>&1 | grep foo",
    ]
    for cmd in R3_ALLOW:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r3_allow::{cmd[:34]}", result["decision"] == "allow", (cmd, result))

    # 24. PR review round 4 (structural hardening): a defense-in-depth self-protect
    # catch-all (any non-read-only command NAMING a .gigacode/.git path blocks,
    # even via a writer this gate doesn't model), plus shell-field bypasses and
    # the remaining destructive-git discard/destroy forms.
    R4_BLOCK = [
        # self-protect catch-all: writers / interpreters not modeled elsewhere
        "ln -sf evil .gigacode/settings.json",
        "rsync evil .gigacode/",
        "New-Item -Path .gigacode/x -ItemType File",
        "python -c \"open('.gigacode/x','w')\"",
        "python3 -c \"import os; os.remove('.git/index')\"",
        "chmod -R 777 .gigacode",
        "tar czf b.tgz .git",
        "install evil .gigacode/settings.json",
        # $IFS field-splitting and backslash-newline line continuation
        "git${IFS}reset${IFS}--hard",
        "git reset \\\n--hard",
        # remaining destructive git forms
        "git checkout .",
        "git checkout HEAD .",
        "git stash drop",
        "git branch -f main start",
        "git branch -d old",
    ]
    for cmd in R4_BLOCK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r4_block::{cmd[:30]!r}", result["decision"] == "block", (cmd, result))

    # reads/inspection of enforcement files MUST still allow (catch-all allow-list),
    # and rename (vs delete/force-move) stays allowed.
    R4_ALLOW = [
        "cat .gigacode/settings.json", "grep foo .gigacode/quality-gates.json",
        "ls -la .gigacode/hooks", "find .gigacode -name '*.py'",
        "head .git/HEAD", "Get-Content .gigacode/settings.json",
        "test -f .gigacode/settings.json", "cd .gigacode && ls",
        "git branch -m newname", "git branch -M main",
        "cp .gitignore backup.txt", "ln -s a.txt b.txt", "rsync -a src/ dst/",
    ]
    for cmd in R4_ALLOW:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r4_allow::{cmd[:30]}", result["decision"] == "allow", (cmd, result))

    # 25. PR review round 5 (fresh Codex P1s on the round 3/4 commits).
    R5_BLOCK = [
        # `--no-dry-run` is the OPPOSITE of dry-run; the old substring-n let it pass
        "git clean -f --no-dry-run", "git clean -fd --no-dry-run",
        # checkout of an existing path discards that file (README.md exists at root)
        "git checkout README.md",
        # aliases/config loaded from env or an include file can't be inspected
        "git --config-env=alias.wipe=ALIAS wipe",
        "git -c include.path=/tmp/cfg wipe",
        "git -c includeIf.gitdir:/x.path=/tmp/cfg status",
        # GIT_CONFIG_* env vars inject config/aliases from the environment
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0='reset --hard' git x",
        "GIT_CONFIG_GLOBAL=/tmp/cfg git wipe",
        # magic / glob pathspecs discard files (refs can't contain : * ? [)
        "git checkout :/",
        "git checkout '*.kt'",
        # find write/exec actions reach the self-protect catch-all
        "find . -maxdepth 0 -fprintf .gigacode/settings.json x",
    ]
    for cmd in R5_BLOCK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r5_block::{cmd[:32]}", result["decision"] == "block", (cmd, result))

    R5_ALLOW = [
        "git clean -fn", "git clean -f --dry-run",          # dry-run preview is safe
        "git checkout feature/no-such-branch-zzz",          # no such file -> branch
        "git checkout HEAD~1", "git checkout origin/main",  # rev/remote ref, not a path
        "GIT_AUTHOR_NAME=x git commit -m y",                # not a GIT_CONFIG_* var
        "find . -name Foo.kt", "find . -exec grep foo {} +",  # pure read / read-via-exec
    ]
    for cmd in R5_ALLOW:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r5_allow::{cmd[:32]}", result["decision"] == "allow", (cmd, result))

    # 26. PR review round 6: destructive git hidden by case-folded flags, shell
    # control keywords, dry-run ordering, and the spaced --config-env form.
    R6_BLOCK = [
        "git switch -C main HEAD~1",            # force-create resets the branch ref
        "git switch --force-create main HEAD~1",
        "git restore --staged -W .",            # -W short worktree flag still discards
        "if true; then git reset --hard; fi",   # command after a control keyword
        "for x in 1; do git reset --hard; done",
        "{ git reset --hard; }",
        "git clean -f --dry-run --no-dry-run",  # --no-dry-run wins (deletes)
        "git clean -fn --no-dry-run",
        "git --config-env alias.wipe=ALIAS wipe",  # space-separated config-env alias
    ]
    for cmd in R6_BLOCK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r6_block::{cmd[:34]}", result["decision"] == "block", (cmd, result))

    R6_ALLOW = [
        "git switch -c feature/new",            # lowercase -c create is benign
        "git restore --staged file.kt",         # index-only unstage is safe
        "git clean -f --no-dry-run --dry-run",  # later --dry-run wins (preview)
        "if true; then echo ok; fi",            # benign command after a keyword
        "git -c alias.st=status st",            # -c alias expands; benign -> allow
    ]
    for cmd in R6_ALLOW:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r6_allow::{cmd[:34]}", result["decision"] == "allow", (cmd, result))

    # 27. PR review round 7: value-taking wrapper options, push short clusters,
    # checkout -B branch reset.
    R7_BLOCK = [
        "env --unset FOO git reset --hard",     # env value-opt operand
        "env -C /tmp git reset --hard",
        "env -S 'git reset --hard'",            # -S carries the command
        "timeout -s KILL 5 git reset --hard",
        "git push -uf origin feature/x",        # force in a short cluster
        "git push -fu origin feature/x",
        "git push -d origin feature/x",         # short delete flag
        "git checkout -B main HEAD~1",          # force-create resets the ref
    ]
    for cmd in R7_BLOCK:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r7_block::{cmd[:34]}", result["decision"] == "block", (cmd, result))

    R7_ALLOW = [
        "env -i git status",                    # -i is boolean; must not eat `git`
        "env FOO=bar git status",
        "git push -u origin feature/x",         # set-upstream, not force/delete
        "git checkout -b feature/new",          # lowercase create is benign
    ]
    for cmd in R7_ALLOW:
        result = run_router("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        check(f"r7_allow::{cmd[:34]}", result["decision"] == "allow", (cmd, result))

    # 25. WI-2: every journal record carries session_id / feature / agent.
    tmp, tmp_router, tmp_config = temp_hooks_copy()
    with open(os.path.join(tmp, "hooks", "gates", "fixture_allow.py"), "w", encoding="utf-8") as handle:
        handle.write("def run(event):\n    return {'decision': 'allow'}\n")
    with open(tmp_config, "w", encoding="utf-8") as handle:
        json.dump({"version": 1,
                   "feature_patterns": ["(?:^|/)docs/development/([^/]+)/"],
                   "routes": [{"event": "PreToolUse", "tool_pattern": "^Edit$",
                               "gates": ["fixture_allow"]}]}, handle)
    run_router("PreToolUse",
               {"tool_name": "Edit", "session_id": "s-42", "agent_type": "coder",
                "tool_input": {"file_path": "docs/development/card-blocking/contract.json"}},
               router=tmp_router)
    with open(os.path.join(tmp, "logs", "decisions.jsonl"), encoding="utf-8") as handle:
        recs = [json.loads(line) for line in handle if line.strip()]
    check("ji_has_records", len(recs) >= 2, recs)  # at least a gate + a final
    for rec in recs:
        tag = rec.get("kind", "?")
        check(f"ji_session::{tag}", rec.get("session_id") == "s-42", rec)
        check(f"ji_feature::{tag}", rec.get("feature") == "card-blocking", rec)
        check(f"ji_agent::{tag}", rec.get("agent") == "coder", rec)
    shutil.rmtree(tmp, ignore_errors=True)

    # 25b. WI-2: pathless event (Stop) -> session stamped, feature/agent empty.
    tmp2, tmp_router2, tmp_config2 = temp_hooks_copy()
    with open(os.path.join(tmp2, "hooks", "gates", "fixture_allow.py"), "w", encoding="utf-8") as handle:
        handle.write("def run(event):\n    return {'decision': 'allow'}\n")
    with open(tmp_config2, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "routes": [
            {"event": "Stop", "gates": ["fixture_allow"]}]}, handle)
    run_router("Stop", {"session_id": "s-9"}, router=tmp_router2)
    with open(os.path.join(tmp2, "logs", "decisions.jsonl"), encoding="utf-8") as handle:
        recs2 = [json.loads(line) for line in handle if line.strip()]
    final2 = [r for r in recs2 if r.get("kind") == "final"][0]
    check("ji_stop_session", final2.get("session_id") == "s-9", final2)
    check("ji_stop_feature_empty", final2.get("feature") == "", final2)
    check("ji_stop_agent_empty", final2.get("agent") == "", final2)
    shutil.rmtree(tmp2, ignore_errors=True)

    print(f"\nAll {PASSED} router checks passed")


if __name__ == "__main__":
    main()
