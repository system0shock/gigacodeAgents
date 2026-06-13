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

    # Task 3: run_command exe-resolution hardening
    with fixture_root() as fix:
        # (a) planted repo-root script must NOT be auto-resolved as a bare command
        with open(os.path.join(fix, "gradlew.bat"), "w", encoding="utf-8") as h:
            h.write("@echo off\nexit /b 0\n")
        rc, tail = lib.run_command("gradlew", 5)
        check("lib_no_reporoot_exe", rc == -1, (rc, tail))
        # (b) explicit relative path still resolves and runs
        with open(os.path.join(fix, "ok.bat"), "w", encoding="utf-8") as h:
            h.write("@echo off\nexit /b 0\n")
        rc, tail = lib.run_command("./ok.bat", 5)
        check("lib_explicit_relpath_runs", rc == 0, (rc, tail))


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

        # Path normalization & case-insensitivity: all variants must BLOCK
        for variant in ("OpenSpec/Specs/payments/spec.md",
                        "openspec//specs/payments/spec.md",
                        "openspec/changes/../specs/payments/spec.md",
                        "./openspec/specs/payments/spec.md"):
            result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                               "tool_input": {"file_path": variant}})
            check(f"ss_pre_variant::{variant[:30]}", result["decision"] == "block", (variant, result))
        # benign nearby path still allowed
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "openspec/changes/my-change/proposal.md"}})
        check("ss_pre_change_still_allow", result["decision"] == "allow", result)

        # Stop on a clean tree (no active change, no changed code) -> allow.
        # Deterministic regardless of whether the openspec CLI is installed.
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "done"})
        check("ss_stop_clean_allow", result["decision"] == "allow", result)

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

            # Stop with an active but invalid change -> block (message ignored;
            # the active change on disk is the trigger, not the message text)
            result = gate.run({"hook_event_name": "Stop",
                               "last_assistant_message": "done"})
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
    # (1) no changed code -> no build, even with a failing command configured
    with fixture_root() as fix:
        write_script(fix, "fail.py", 1)
        write_qg(fix, {"build": {"command": "python fail.py", "timeout_seconds": 30}})
        # fixture is not a git repo -> changed_code_files() == [] -> allow
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "hi"})
        check("build_no_code_change_allow", result["decision"] == "allow", result)

    # (2..) production code changed -> the build runs; outcome follows the command
    with fixture_root() as fix:
        srcdir = os.path.join(fix, "src")
        os.makedirs(srcdir)
        with open(os.path.join(srcdir, "Foo.kt"), "w", encoding="utf-8") as handle:
            handle.write("class Foo\n")
        init_git(fix)  # Foo.kt is a changed code file -> the build is engaged
        write_script(fix, "fail.py", 1)
        write_script(fix, "pass.py", 0)

        # unconfigured -> silent allow (journal-only skip)
        write_qg(fix, {"build": {"command": ""}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "done"})
        check("build_unconfigured_allow",
              result["decision"] == "allow" and "additionalContext" not in result, result)

        # failing build blocks
        write_qg(fix, {"build": {"command": "python fail.py", "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "done"})
        check("build_fail_block", result["decision"] == "block", result)

        # passing build allows
        write_qg(fix, {"build": {"command": "python pass.py", "timeout_seconds": 30}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "done"})
        check("build_pass_allow", result["decision"] == "allow", result)

        # configured-but-broken command -> allow with anomaly note
        write_qg(fix, {"build": {"command": "definitely-missing-tool-xyz"}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "done"})
        check("build_broken_command_note",
              result["decision"] == "allow" and "additionalContext" in result, result)

        # hanging build -> timeout note, allow (costs ~1 s: timeout clamps to 1)
        with open(os.path.join(fix, "hang.py"), "w", encoding="utf-8") as handle:
            handle.write("import time\ntime.sleep(30)\n")
        write_qg(fix, {"build": {"command": "python hang.py", "timeout_seconds": 0}})
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "done"})
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

        # non-code extension: early exit, no analysis
        md_path = os.path.join(src, "notes.md")
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write("TODO: write docs\n" * 500)
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": md_path}})
        check("cc_non_code_silent", "additionalContext" not in result, result)

        # markers configured as a bare string: fall back to defaults,
        # not char-by-char iteration (which would warn on this clean file)
        write_qg(fix, {"clean_code": {"placeholder_markers": "TODO"}})
        path = write_kt("Str.kt", "fun s() {\n    println(\"D O T\")\n}\n")
        result = gate.run({"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": path}})
        check("cc_marker_string_fallback", "additionalContext" not in result, result)


def init_git(root_dir):
    subprocess.run(["git", "init", "-q"], cwd=root_dir, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "-A"], cwd=root_dir, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_existing_code():
    gate = load_gate("gate_existing_code")
    with fixture_root() as fix:
        src = os.path.join(fix, "src")
        os.makedirs(src)
        with open(os.path.join(src, "Existing.kt"), "w", encoding="utf-8") as handle:
            handle.write('class PaymentService(\n    @KafkaListener(topics = ["payment-events"])\n)\n')
        init_git(fix)

        # duplicate class name -> advisory context naming the existing file
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/new/PaymentService2.kt",
                                          "content": "class PaymentService { }"}})
        check("ec_duplicate_symbol_warn", "Existing.kt" in result.get("additionalContext", ""), result)
        check("ec_advisory_allow", result["decision"] == "allow", result)

        # duplicate Kafka topic literal -> advisory context
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/new/AnotherConsumer.kt",
                                          "content": '@KafkaListener(topics = ["payment-events"])\nclass AnotherConsumer { }'}})
        check("ec_topic_warn", "payment-events" in result.get("additionalContext", ""), result)

        # no declarations in content -> silent allow
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/notes.txt", "content": "x = 1"}})
        check("ec_no_symbols_silent", "additionalContext" not in result, result)

        # Edit of an existing file is skipped
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                           "tool_input": {"file_path": os.path.join(src, "Existing.kt"),
                                          "new_string": "class PaymentService { }"}})
        check("ec_edit_existing_skip", "additionalContext" not in result, result)

        # WriteFile-overwrite of an existing file is skipped too
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": os.path.join(src, "Existing.kt"),
                                          "content": "class PaymentService { }"}})
        check("ec_overwrite_existing_skip", "additionalContext" not in result, result)

        # enum class: the enum's NAME is the symbol, not the keyword 'class'
        # (keyword capture would make every repo class a false hit)
        with open(os.path.join(src, "Status.kt"), "w", encoding="utf-8") as handle:
            handle.write("enum class PaymentStatus { PENDING, DONE }\n")
        subprocess.run(["git", "add", "-A"], cwd=fix, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/new/States.kt",
                                          "content": "enum class PaymentStatus { X }"}})
        check("ec_enum_class_warn", "Status.kt" in result.get("additionalContext", ""), result)
        result = gate.run({"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
                           "tool_input": {"file_path": "src/new/Fresh.kt",
                                          "content": "enum class TotallyFreshEnum { X }"}})
        check("ec_enum_unique_silent", "additionalContext" not in result, result)


def write_dev_dir(root_dir, slug, files):
    """Create docs/development/<slug>/ with the given {name: content} files."""
    path = os.path.join(root_dir, "docs", "development", slug)
    os.makedirs(path)
    for name, content in files.items():
        with open(os.path.join(path, name), "w", encoding="utf-8") as handle:
            handle.write(content)
    return path


def test_flow_integrity():
    """gate_spec_structure Stop now triggers from the working tree, not the
    agent's message: changed production code with no active OpenSpec change
    must block regardless of what the final message says."""
    gate = load_gate("gate_spec_structure")
    with fixture_root() as fix:
        srcdir = os.path.join(fix, "src")
        os.makedirs(srcdir)
        with open(os.path.join(srcdir, "Foo.kt"), "w", encoding="utf-8") as handle:
            handle.write("class Foo\n")
        init_git(fix)  # Foo.kt becomes a tracked change; no openspec/changes/<id>
        # message deliberately omits the old trigger paths
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "Done."})
        check("fi_code_without_change_blocks", result["decision"] == "block", result)
    with fixture_root() as fix:
        init_git(fix)  # git repo, no code change, no active change
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "Done."})
        check("fi_no_change_allows", result["decision"] == "allow", result)
    with fixture_root() as fix:
        # a docs-only change is NOT production code -> Stop must allow (the
        # openspec/ docs/ .gigacode/ exclusion must not regress into an over-block)
        os.makedirs(os.path.join(fix, "docs"))
        with open(os.path.join(fix, "docs", "notes.md"), "w", encoding="utf-8") as handle:
            handle.write("notes\n")
        init_git(fix)
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "Done."})
        check("fi_docs_only_allows", result["decision"] == "allow", result)


def commit_all(root_dir):
    """git init + add + commit so a dir is 'committed' (not a working-tree
    change) — used to make a dev dir stale relative to the current change."""
    init_git(root_dir)
    subprocess.run(["git", "-c", "user.email=t@t.invalid", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], cwd=root_dir, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_validate_output():
    """validate_development_output triggers from the working tree and validates
    only docs/development/<slug>/ dirs that are part of the CURRENT change."""
    gate = load_gate("validate_development_output")
    stop = {"hook_event_name": "Stop", "last_assistant_message": "done"}

    # (a) a CHANGED dev dir missing required artifacts -> block
    with fixture_root() as fix:
        write_dev_dir(fix, "sample", {"journal.md": "did work\n"})  # partial
        init_git(fix)  # the partial dir is a tracked change
        result = gate.run(stop)
        check("vdo_missing_artifacts_block", result["decision"] == "block", result)
    # (b) a CHANGED complete dev dir with evidence -> allow
    with fixture_root() as fix:
        write_dev_dir(fix, "sample", {
            "journal.md": "did work\n",
            "verification.md": "ran command X\nexit 0\n",
            "pr-summary.md": "summary\n"})
        init_git(fix)
        result = gate.run(stop)
        check("vdo_complete_allow", result["decision"] == "allow", result)
    # (c) a CHANGED dev dir with a placeholder marker -> block
    with fixture_root() as fix:
        write_dev_dir(fix, "sample", {
            "journal.md": "TODO finish\n",
            "verification.md": "ran command X\nexit 0\n",
            "pr-summary.md": "summary\n"})
        init_git(fix)
        result = gate.run(stop)
        check("vdo_placeholder_block", result["decision"] == "block", result)
    # (d) nothing changed, no dev dir -> allow (no false block)
    with fixture_root() as fix:
        init_git(fix)
        result = gate.run(stop)
        check("vdo_nothing_allow", result["decision"] == "allow", result)
    # (e) production code changed but no dev dir at all -> block
    with fixture_root() as fix:
        srcdir = os.path.join(fix, "src")
        os.makedirs(srcdir)
        with open(os.path.join(srcdir, "Foo.kt"), "w", encoding="utf-8") as handle:
            handle.write("class Foo\n")
        init_git(fix)
        result = gate.run(stop)
        check("vdo_code_no_dir_block", result["decision"] == "block", result)
    # (f) #15: a STALE (committed, unchanged) dev dir with a TODO must NOT block
    # the current Stop — only dirs in the current change are validated.
    with fixture_root() as fix:
        write_dev_dir(fix, "old-feature", {
            "journal.md": "TODO leftover\n",
            "verification.md": "ran command X\nexit 0\n",
            "pr-summary.md": "summary\n"})
        commit_all(fix)  # committed -> not a working-tree change
        result = gate.run(stop)
        check("vdo_stale_dir_no_block", result["decision"] == "allow", result)
    # (g) claims "passed" but verification.md carries no command/exit evidence
    with fixture_root() as fix:
        write_dev_dir(fix, "sample", {
            "journal.md": "did work\n",
            "verification.md": "looks good\n",   # no command / exit evidence
            "pr-summary.md": "summary\n"})
        init_git(fix)
        result = gate.run({"hook_event_name": "Stop", "last_assistant_message": "all tests passed"})
        check("vdo_passed_no_evidence_block", result["decision"] == "block", result)


def test_cyrillic():
    """Cyrillic-named code is detected with its real UTF-8 path (not git's
    octal-escaped mojibake), and gate CLIs emit valid UTF-8 JSON."""
    lib = load_gate("_lib")
    with fixture_root() as fix:
        srcdir = os.path.join(fix, "src")
        os.makedirs(srcdir)
        with open(os.path.join(srcdir, "Главный.kt"), "w", encoding="utf-8") as handle:
            handle.write("class Main\n")
        init_git(fix)
        changed = lib.changed_code_files()
        # the real path survives (octal mangling would keep .kt but lose the stem)
        check("cyr_real_path", any(p.endswith("Главный.kt") for p in changed), changed)

    # a gate CLI must emit valid UTF-8 JSON for a Russian reason (defect 2)
    gate_path = os.path.join(GATES_DIR, "validate_development_output.py")
    with fixture_root() as fix:
        write_dev_dir(fix, "sample", {"journal.md": "x\n"})  # partial -> Russian reason
        init_git(fix)
        env = dict(os.environ)
        env["GIGACODE_ROOT"] = fix
        proc = subprocess.run(
            [sys.executable, gate_path],
            input=b'{"hook_event_name":"Stop","last_assistant_message":"done"}',
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        text = proc.stdout.decode("utf-8")  # raises if the gate emitted cp1251 bytes
        obj = json.loads(text)
        check("cyr_cli_utf8",
              obj["decision"] == "block" and "development" in obj.get("reason", ""),
              (text, obj))


def main():
    test_lib()
    test_context_inject()
    test_spec_structure()
    test_lint()
    test_build()
    test_clean_code()
    test_existing_code()
    test_flow_integrity()
    test_validate_output()
    test_cyrillic()
    print(f"\nAll {PASSED} gate checks passed")


if __name__ == "__main__":
    main()
