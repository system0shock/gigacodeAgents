#!/usr/bin/env python3
"""Offline unit tests for quality gates. Run from the repo root:
    python scripts/test_gates.py
Gates are loaded in-process; fixtures live in temp dirs pointed at via
the GIGACODE_ROOT env override."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES_DIR = os.path.join(ROOT, ".gigacode", "hooks", "gates")
PASSED = 0


def load_gate(name):
    path = os.path.join(GATES_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location("test_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(name, condition, detail=""):
    # explicit raise (not assert) so python -O cannot neuter the suite
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


def make_fixture():
    """Temp template root: rules/, openspec/changes/, .gigacode/logs/."""
    tmp = tempfile.mkdtemp(prefix="gates-test-")
    os.makedirs(os.path.join(tmp, "rules"))
    for rule in ("development-flow.md", "openspec.md"):
        shutil.copy(os.path.join(ROOT, "rules", rule), os.path.join(tmp, "rules"))
    os.makedirs(os.path.join(tmp, "openspec", "changes", "archive"))
    src_config = os.path.join(ROOT, "openspec", "config.yaml")
    if os.path.exists(src_config):
        shutil.copy(src_config, os.path.join(tmp, "openspec"))
    os.makedirs(os.path.join(tmp, ".gigacode", "logs"))
    return tmp


class fixture_root:
    """Context manager: point _lib.root() at a fresh fixture tree."""

    def __enter__(self):
        self.tmp = make_fixture()
        self._orig = os.environ.get("GIGACODE_ROOT")
        os.environ["GIGACODE_ROOT"] = self.tmp
        return self.tmp

    def __exit__(self, *exc):
        if self._orig is None:
            os.environ.pop("GIGACODE_ROOT", None)
        else:
            os.environ["GIGACODE_ROOT"] = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def write_qg(root_dir, config):
    path = os.path.join(root_dir, ".gigacode", "quality-gates.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)


def write_script(root_dir, name, exit_code):
    """Tiny python script used as a fake lint/build command."""
    with open(os.path.join(root_dir, name), "w", encoding="utf-8") as handle:
        handle.write(f"import sys\nsys.exit({exit_code})\n")


def test_lib():
    lib = load_gate("_lib")
    check("lib_glob_root_file", lib.matches_globs("Main.kt", ["**/*.kt"]))
    check("lib_glob_nested", lib.matches_globs("src/a/B.kt", ["**/*.kt"]))
    check("lib_glob_nonmatch", not lib.matches_globs("README.md", ["**/*.kt"]))
    rc, tail = lib.run_command("definitely-missing-tool-xyz", 5)
    check("lib_missing_command", rc == -1, (rc, tail))
    with fixture_root() as fix:
        lib.journal_skip("gate_test", "test reason")
        journal = os.path.join(fix, ".gigacode", "logs", "decisions.jsonl")
        with open(journal, "r", encoding="utf-8") as handle:
            line = handle.read()
        check("lib_journal_skip", '"gate_test"' in line and '"skip"' in line, line)


def test_context_inject():
    gate = load_gate("gate_context_inject")
    with fixture_root() as fix:
        os.makedirs(os.path.join(fix, "openspec", "changes", "add-sample"))
        os.makedirs(os.path.join(fix, ".gigacode", "context"))
        map_path = os.path.join(fix, ".gigacode", "context", "module-map.md")
        with open(map_path, "w", encoding="utf-8") as handle:
            handle.write("# Module Map\npayments: core/payments\n")
        result = gate.run({"hook_event_name": "SessionStart"})
        ctx = result.get("additionalContext", "")
        check("ci_session_decision", result["decision"] == "allow", result)
        check("ci_session_rules", "Development Flow Rules" in ctx, ctx[:200])
        check("ci_session_module_map", "Module Map" in ctx, ctx[-400:])
        check("ci_session_changes", "add-sample" in ctx, ctx[-200:])

        result = gate.run({"hook_event_name": "SubagentStart", "agent_type": "coder"})
        ctx = result.get("additionalContext", "")
        check("ci_subagent_search", "find_symbol" in ctx, ctx[:200])
        check("ci_subagent_changes", "add-sample" in ctx, ctx[-200:])

        result = gate.run({"hook_event_name": "UserPromptSubmit",
                           "prompt": "/develop-feature implement payment retry"})
        ctx = result.get("additionalContext", "")
        check("ci_prompt_changes", "add-sample" in ctx, result)

        result = gate.run({"hook_event_name": "UserPromptSubmit",
                           "prompt": "/fix-bug payment NPE on empty cart"})
        check("ci_fix_bug_changes",
              "add-sample" in result.get("additionalContext", ""), result)

        result = gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "привет"})
        check("ci_plain_prompt_silent", "additionalContext" not in result, result)


def write_change(root_dir, change_id, complete=True, valid=False):
    """OpenSpec change fixture. complete=False omits tasks.md and the delta."""
    base = os.path.join(root_dir, "openspec", "changes", change_id)
    os.makedirs(os.path.join(base, "specs", "sample"), exist_ok=True)
    with open(os.path.join(base, "proposal.md"), "w", encoding="utf-8") as handle:
        handle.write("## Why\nReason.\n\n## What Changes\n- change\n\n## Impact\n- none\n")
    if complete:
        with open(os.path.join(base, "tasks.md"), "w", encoding="utf-8") as handle:
            handle.write("## 1. Group\n- [ ] 1.1 Do it\n")
        if valid:
            spec = ("## ADDED Requirements\n\n### Requirement: Sample\n"
                    "The system SHALL sample.\n\n#### Scenario: Works\n"
                    "- **WHEN** invoked\n- **THEN** it works\n")
        else:
            spec = "## ADDED Requirements\n\n### Requirement: Sample\nNo scenario here.\n"
        with open(os.path.join(base, "specs", "sample", "spec.md"), "w", encoding="utf-8") as handle:
            handle.write(spec)
    return base


def test_spec_structure():
    gate = load_gate("gate_spec_structure")
    with fixture_root() as fix:
        # PreToolUse: spec truth and archive are write-protected
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "openspec/specs/payments/spec.md"}})
        check("ss_pre_specs_block", result["decision"] == "block", result)
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "openspec/changes/archive/old/proposal.md"}})
        check("ss_pre_archive_block", result["decision"] == "block", result)
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "openspec/changes/my-change/proposal.md"}})
        check("ss_pre_change_allow", result["decision"] == "allow", result)

        # PostToolUse: CLI unavailable -> skip-with-record + advisory context
        write_change(fix, "my-change", complete=True, valid=False)
        os.environ["OPENSPEC_BIN"] = os.path.join(fix, "missing-openspec")
        try:
            result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": "openspec/changes/my-change/tasks.md"}})
        finally:
            os.environ.pop("OPENSPEC_BIN", None)
        check("ss_post_cli_missing_allow", result["decision"] == "allow", result)
        check("ss_post_cli_missing_note", "пропущена" in result.get("additionalContext", ""), result)

        # Stop: no PR-readiness mention -> no validation at all
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "hello"})
        check("ss_stop_no_mention_allow", result["decision"] == "allow", result)

        # PostToolUse on a non-openspec path: fast allow, no CLI spawn
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/main/kotlin/Main.kt"}})
        check("ss_post_non_openspec_allow",
              result["decision"] == "allow" and "additionalContext" not in result, result)

        if shutil.which("openspec"):
            # PostToolUse: complete but invalid change -> block
            result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": "openspec/changes/my-change/specs/sample/spec.md"}})
            check("ss_post_invalid_block", result["decision"] == "block", result)

            # PostToolUse: incomplete invalid change -> advisory only
            write_change(fix, "draft-change", complete=False)
            result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": "openspec/changes/draft-change/proposal.md"}})
            check("ss_post_incomplete_advisory",
                  result["decision"] == "allow" and "additionalContext" in result, result)

            # Stop with PR-readiness mention and an invalid change -> block
            result = gate.run({"hook_event_name": "Stop",
                               "last_assistant_message": "Готово, см. openspec/changes/my-change/"})
            check("ss_stop_invalid_block", result["decision"] == "block", result)

            # Valid change passes PostToolUse
            shutil.rmtree(os.path.join(fix, "openspec", "changes", "draft-change"))
            shutil.rmtree(os.path.join(fix, "openspec", "changes", "my-change"))
            write_change(fix, "good-change", complete=True, valid=True)
            result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": "openspec/changes/good-change/tasks.md"}})
            check("ss_post_valid_allow", result["decision"] == "allow", result)
        else:
            print("SKIP: openspec CLI not on PATH; live validation tests skipped")


def test_lint():
    gate = load_gate("gate_lint")
    with fixture_root() as fix:
        event = {"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                 "tool_input": {"file_path": "src/Main.kt"}}

        # unconfigured -> silent allow (journal-only skip)
        write_qg(fix, {"lint": {"command": "", "applies_to": ["**/*.kt"]}})
        result = gate.run(event)
        check("lint_unconfigured_allow",
              result["decision"] == "allow" and "additionalContext" not in result, result)

        # failing linter blocks
        write_script(fix, "fail.py", 1)
        write_qg(fix, {"lint": {"command": "python fail.py", "applies_to": ["**/*.kt"],
                                "timeout_seconds": 30}})
        result = gate.run(event)
        check("lint_fail_block", result["decision"] == "block", result)
        check("lint_fail_reason", "exit 1" in result.get("reason", ""), result)

        # passing linter allows
        write_script(fix, "pass.py", 0)
        write_qg(fix, {"lint": {"command": "python pass.py", "applies_to": ["**/*.kt"],
                                "timeout_seconds": 30}})
        result = gate.run(event)
        check("lint_pass_allow", result["decision"] == "allow", result)

        # non-matching file skipped even with a failing command
        write_qg(fix, {"lint": {"command": "python fail.py", "applies_to": ["**/*.kt"],
                                "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "README.md"}})
        check("lint_nonmatching_skip", result["decision"] == "allow", result)

        # configured-but-broken command -> allow with anomaly note
        write_qg(fix, {"lint": {"command": "definitely-missing-tool-xyz",
                                "applies_to": ["**/*.kt"], "timeout_seconds": 30}})
        result = gate.run(event)
        check("lint_broken_command_note",
              result["decision"] == "allow" and "additionalContext" in result, result)

        # hanging linter -> timeout note, allow (costs ~1 s: timeout clamps to 1)
        with open(os.path.join(fix, "hang.py"), "w", encoding="utf-8") as handle:
            handle.write("import time\ntime.sleep(30)\n")
        write_qg(fix, {"lint": {"command": "python hang.py", "applies_to": ["**/*.kt"],
                                "timeout_seconds": 0}})
        result = gate.run(event)
        check("lint_timeout_note",
              result["decision"] == "allow"
              and "таймаут" in result.get("additionalContext", ""), result)

        # list form: kotlin + java linters side by side
        write_script(fix, "fail2.py", 2)
        write_qg(fix, {"lint": [
            {"command": "python pass.py", "applies_to": ["**/*.kt"], "timeout_seconds": 30},
            {"command": "python fail2.py", "applies_to": ["**/*.java"], "timeout_seconds": 30},
        ]})
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/Main.java"}})
        check("lint_list_java_block", result["decision"] == "block", result)


def test_build():
    gate = load_gate("gate_build")
    with fixture_root() as fix:
        write_script(fix, "fail.py", 1)
        write_script(fix, "pass.py", 0)

        # not a PR-readiness moment -> no build even with a failing command
        write_qg(fix, {"build": {"command": "python fail.py", "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "hi"})
        check("build_not_pr_moment", result["decision"] == "allow", result)

        pr_message = "Готово: docs/development/sample-task/pr-summary.md"

        # unconfigured -> silent allow (journal-only skip)
        write_qg(fix, {"build": {"command": ""}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": pr_message})
        check("build_unconfigured_allow",
              result["decision"] == "allow" and "additionalContext" not in result, result)

        # failing build blocks
        write_qg(fix, {"build": {"command": "python fail.py", "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": pr_message})
        check("build_fail_block", result["decision"] == "block", result)

        # passing build allows
        write_qg(fix, {"build": {"command": "python pass.py", "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": pr_message})
        check("build_pass_allow", result["decision"] == "allow", result)

        # configured-but-broken command -> allow with anomaly note
        write_qg(fix, {"build": {"command": "definitely-missing-tool-xyz"}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": pr_message})
        check("build_broken_command_note",
              result["decision"] == "allow" and "additionalContext" in result, result)

        # hanging build -> timeout note, allow (costs ~1 s: timeout clamps to 1)
        with open(os.path.join(fix, "hang.py"), "w", encoding="utf-8") as handle:
            handle.write("import time\ntime.sleep(30)\n")
        write_qg(fix, {"build": {"command": "python hang.py", "timeout_seconds": 0}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": pr_message})
        check("build_timeout_note",
              result["decision"] == "allow"
              and "таймаут" in result.get("additionalContext", ""), result)


def test_clean_code():
    gate = load_gate("gate_clean_code")
    with fixture_root() as fix:
        write_qg(fix, {"clean_code": {"max_file_lines": 400, "max_function_lines": 60,
                                      "placeholder_markers": ["TODO", "FIXME", "XXX"]}})
        src = os.path.join(fix, "src")
        os.makedirs(src)

        def write_kt(name, text):
            path = os.path.join(src, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            return path

        # long file warns
        path = write_kt("Big.kt", "\n".join(["// line"] * 450))
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_long_file_warn", "450" in result.get("additionalContext", ""), result)
        check("cc_long_file_allow", result["decision"] == "allow", result)

        # TODO marker warns
        path = write_kt("Todo.kt", "fun a() {\n    // TODO finish\n}\n")
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_todo_warn", "TODO" in result.get("additionalContext", ""), result)

        # long function warns
        body = "fun bigFunction(x: Int) {\n" + "    println(x)\n" * 70 + "}\n"
        path = write_kt("LongFun.kt", body)
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_long_function_warn", "блок" in result.get("additionalContext", ""), result)

        # Thread.sleep in a test file warns
        path = write_kt("PaymentServiceTest.kt",
                        "class PaymentServiceTest {\n    fun t() { Thread.sleep(1000) }\n}\n")
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_sleep_in_test_warn", "Thread.sleep" in result.get("additionalContext", ""), result)

        # clean small file is silent
        path = write_kt("Ok.kt", "fun ok() {\n    println(1)\n}\n")
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_clean_silent", "additionalContext" not in result, result)


def main():
    test_lib()
    test_context_inject()
    test_spec_structure()
    test_lint()
    test_build()
    test_clean_code()
    print(f"\nAll {PASSED} gate checks passed")


if __name__ == "__main__":
    main()
