#!/usr/bin/env python3
"""Offline unit tests for analytics quality gates. Run from modules/analytics:
    python scripts/test_gates.py
Gates load in-process; fixtures live in temp dirs via GIGACODE_ROOT."""
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

GOOD_TECHDOC = ("= Обзор фичи\n:feature: card-blocking\n:run-date: 2026-06-11\n"
                ":code-commit: abc1234\n\nПоведение подтверждено. Источник: код.\n")
GOOD_FINAL_ADOC = "= Кейс блокировки карты\n\nОсновной сценарий использования.\n"


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
    tmp = tempfile.mkdtemp(prefix="agates-")
    os.makedirs(os.path.join(tmp, "rules"))
    for rule in ("reverse-analysis.md", "openspec.md"):
        shutil.copy(os.path.join(ROOT, "rules", rule),
                    os.path.join(tmp, "rules"))
    os.makedirs(os.path.join(tmp, ".gigacode", "logs"))
    os.makedirs(os.path.join(tmp, "openspec", "specs"))
    os.makedirs(os.path.join(tmp, "docs", "features"))
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


def write_file(root_dir, rel, text):
    path = os.path.join(root_dir, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def write_qg(root_dir, config):
    write_file(root_dir, ".gigacode/quality-gates.json", json.dumps(config))


def file_event(path):
    return {"hook_event_name": "PostToolUse", "tool_name": "WriteFile",
            "tool_input": {"file_path": path}}


def test_git_guard():
    gate = load_gate("git_guard")
    check("gg_reset_hard",
          gate.run({"tool_input": {"command": "git reset --hard"}})["decision"] == "block")
    check("gg_shell_specs",
          gate.run({"tool_input": {"command": "echo x > openspec/specs/cap/spec.md"}})["decision"] == "block")
    check("gg_shell_archive",
          gate.run({"tool_input": {"command": "cp a.md openspec/changes/archive/a.md"}})["decision"] == "block")
    check("gg_file_specs_allowed",
          gate.run({"tool_input": {"file_path": "openspec/specs/cap/spec.md"}})["decision"] == "allow")
    check("gg_file_gigacode",
          gate.run({"tool_input": {"file_path": ".gigacode/hooks/router.py"}})["decision"] == "block")
    check("gg_env_ask",
          gate.run({"tool_input": {"file_path": ".env"}})["decision"] == "ask")
    check("gg_qwen_ask",
          gate.run({"tool_input": {"file_path": ".qwen/settings.json"}})["decision"] == "ask")
    check("gg_benign",
          gate.run({"tool_input": {"command": "git status"}})["decision"] == "allow")
    check("gg_file_archive",
          gate.run({"tool_input": {"file_path": "openspec/changes/archive/a.md"}})["decision"] == "block")
    check("gg_file_archive_traversal",
          gate.run({"tool_input": {"file_path": "openspec/specs/../changes/archive/a.md"}})["decision"] == "block")
    check("gg_shell_tee_specs",
          gate.run({"tool_input": {"command": "tee openspec/specs/cap/spec.md"}})["decision"] == "block")
    # symmetry with gate_spec_bootstrap: notebook_path is guarded on this channel too
    check("gg_notebook_gigacode",
          gate.run({"tool_input": {"notebook_path": ".gigacode/hooks/router.py"}})["decision"] == "block")

    # [1] case-insensitive self-protect: on Windows/macOS .GIGACODE/.GIT resolve to
    # the same dir, so altered casing must NOT dodge the file-tool block.
    check("gg_file_gigacode_uppercase",
          gate.run({"tool_input": {"file_path": ".Gigacode/hooks/router.py"}})["decision"] == "block")
    check("gg_file_dotgit_uppercase",
          gate.run({"tool_input": {"file_path": ".GIT/config"}})["decision"] == "block")
    # [2] absolute path under a /**-suffixed PROTECTED_PATHS dir without a hand-
    # written **/ twin (deploy/**) must still ASK — agents pass absolute paths.
    check("gg_abs_protected_deploy_ask",
          gate.run({"tool_input": {"file_path": "F:/Coding/proj/deploy/prod.yml"}})["decision"] == "ask")

    # --- Phase 4: engine hardening (ported from dev-flow) ---
    # CRITICAL regression: file-tool write to openspec/specs stays ALLOWED
    # (create-once split — governed by gate_spec_bootstrap, not git_guard).
    check("gg_file_specs_allowed_p4",
          gate.run({"tool_input": {"file_path": "openspec/specs/new-cap/spec.md"}})["decision"] == "allow")
    # shell write to specs still blocks
    check("gg_shell_specs_block_p4",
          gate.run({"tool_input": {"command": "echo x > openspec/specs/cap/spec.md"}})["decision"] == "block")
    # absolute / nested .gigacode (component-regex, not start-anchored glob)
    check("gg_abs_gigacode",
          gate.run({"tool_input": {"file_path": "/workspace/proj/modules/analytics/.gigacode/hooks/router.py"}})["decision"] == "block")
    # .git deletion by absolute and traversal path
    check("gg_rm_abs_dotgit",
          gate.run({"tool_input": {"command": "rm -rf /workspace/proj/.git"}})["decision"] == "block")
    check("gg_rm_traversal_dotgit",
          gate.run({"tool_input": {"command": "rm -rf ../../.git"}})["decision"] == "block")
    # fd-prefixed and argument-glued redirections to an enforcement path
    check("gg_fd_redirect",
          gate.run({"tool_input": {"command": "printf err 2>.gigacode/settings.json"}})["decision"] == "block")
    check("gg_glued_redirect",
          gate.run({"tool_input": {"command": "echo x>.gigacode/settings.json"}})["decision"] == "block")
    # unicode separator and command-substitution bypasses
    check("gg_nbsp_reset",
          gate.run({"tool_input": {"command": "git reset --hard"}})["decision"] == "block")
    check("gg_subst_reset",
          gate.run({"tool_input": {"command": "x=$(git reset --hard)"}})["decision"] == "block")

    # --- Phase 4: git-semantics fixes ---
    check("gg_clean_exclude_blocks",
          gate.run({"tool_input": {"command": "git clean -fd --exclude=node_modules"}})["decision"] == "block")
    check("gg_clean_dryrun_allows",
          gate.run({"tool_input": {"command": "git clean -fdn"}})["decision"] == "allow")
    check("gg_tee_multi_output",
          gate.run({"tool_input": {"command": "tee .gigacode/hooks/router.py /tmp/out"}})["decision"] == "block")
    check("gg_restore_default_blocks",
          gate.run({"tool_input": {"command": "git restore README.md"}})["decision"] == "block")
    check("gg_restore_staged_allows",
          gate.run({"tool_input": {"command": "git restore --staged README.md"}})["decision"] == "allow")
    check("gg_checkout_force_blocks",
          gate.run({"tool_input": {"command": "git checkout -f main"}})["decision"] == "block")
    check("gg_checkout_plain_allows",
          gate.run({"tool_input": {"command": "git checkout my-feature"}})["decision"] == "allow")

    # --- Codex round 5 (review on Phase 4 HEAD): residual engine gaps ---
    # move/rename OUT of the enforcement tree is destructive (the source file is
    # removed from .gigacode) — classify move sources, not just the destination.
    check("gg_mv_source_gigacode",
          gate.run({"tool_input": {"command": "mv .gigacode/hooks/router.py /tmp/router.py"}})["decision"] == "block")
    # round-7: the structural catch-all now blocks ANY non-read-only command that
    # merely names an enforcement path (supersedes the round-5 copy-out allowance).
    check("gg_cp_enforcement_ref_blocks",
          gate.run({"tool_input": {"command": "cp .gigacode/hooks/router.py /tmp/router.py"}})["decision"] == "block")
    check("gg_cp_benign_allows",
          gate.run({"tool_input": {"command": "cp README.md /tmp/x"}})["decision"] == "allow")
    # `>&file` / `>& file` is a combined stdout+stderr redirect to a real file.
    check("gg_amp_redirect_glued",
          gate.run({"tool_input": {"command": "echo x >&.gigacode/settings.json"}})["decision"] == "block")
    check("gg_amp_redirect_spaced",
          gate.run({"tool_input": {"command": "echo x >& .gigacode/settings.json"}})["decision"] == "block")
    # `2>&1` is fd duplication, not a file write — must stay allow (no false block).
    check("gg_fd_dup_allows",
          gate.run({"tool_input": {"command": "echo x 2>&1"}})["decision"] == "allow")
    # process substitution runs its inner command — destructive git inside blocks.
    check("gg_proc_subst_reset",
          gate.run({"tool_input": {"command": "cat <(git reset --hard)"}})["decision"] == "block")
    # git switch destructive forms discard working-tree edits like checkout/restore.
    check("gg_switch_force_blocks",
          gate.run({"tool_input": {"command": "git switch -f main"}})["decision"] == "block")
    check("gg_switch_discard_blocks",
          gate.run({"tool_input": {"command": "git switch --discard-changes main"}})["decision"] == "block")
    check("gg_switch_plain_allows",
          gate.run({"tool_input": {"command": "git switch my-feature"}})["decision"] == "allow")
    check("gg_switch_create_allows",
          gate.run({"tool_input": {"command": "git switch -c my-feature"}})["decision"] == "allow")

    # --- Codex round 6 (review on dcb436b): control blocks + target-directory ---
    # a destructive command after a control/group token must be inspected, not
    # just leaf[0] (`then`, `{`, `do`, …).
    check("gg_then_reset_blocks",
          gate.run({"tool_input": {"command": "if true; then git reset --hard; fi"}})["decision"] == "block")
    check("gg_brace_group_reset_blocks",
          gate.run({"tool_input": {"command": "{ git reset --hard; }"}})["decision"] == "block")
    check("gg_do_loop_reset_blocks",
          gate.run({"tool_input": {"command": "while true; do git reset --hard; done"}})["decision"] == "block")
    check("gg_if_benign_allows",
          gate.run({"tool_input": {"command": "if git diff --quiet; then echo clean; fi"}})["decision"] == "allow")
    # GNU -t/--target-directory: sources are written INTO the dir (the write target)
    check("gg_cp_target_dir_blocks",
          gate.run({"tool_input": {"command": "cp -t .gigacode/hooks router.py"}})["decision"] == "block")
    check("gg_cp_target_dir_eq_blocks",
          gate.run({"tool_input": {"command": "cp --target-directory=.gigacode/hooks router.py"}})["decision"] == "block")
    check("gg_cp_target_dir_benign_allows",
          gate.run({"tool_input": {"command": "cp -t /tmp router.py"}})["decision"] == "allow")

    # --- Codex round 7 (review on cb16246) ---
    # path-form checkout restores a file (discards edits); branch switch stays ok.
    check("gg_checkout_dot_blocks",
          gate.run({"tool_input": {"command": "git checkout ."}})["decision"] == "block")
    check("gg_checkout_path_blocks",  # README.md exists in the module cwd (tests run there)
          gate.run({"tool_input": {"command": "git checkout README.md"}})["decision"] == "block")
    # inline one-shot alias hiding a destructive subcommand (git skip the catch-all).
    check("gg_alias_reset_blocks",
          gate.run({"tool_input": {"command": "git -c alias.nuke='reset --hard' nuke"}})["decision"] == "block")
    check("gg_alias_shell_blocks",
          gate.run({"tool_input": {"command": "git -c alias.boom='!rm -rf .gigacode' boom"}})["decision"] == "block")
    # branch force-move and stash drop discard work, like delete/clear.
    check("gg_branch_force_move_blocks",
          gate.run({"tool_input": {"command": "git branch -f main other"}})["decision"] == "block")
    check("gg_stash_drop_blocks",
          gate.run({"tool_input": {"command": "git stash drop"}})["decision"] == "block")
    # structural catch-all: any non-read-only program merely naming an enforcement
    # path is blocked (touch/mkdir/ln/chmod/…), reads (cat) stay allowed.
    check("gg_touch_gigacode",
          gate.run({"tool_input": {"command": "touch .gigacode/hooks/router.py"}})["decision"] == "block")
    check("gg_mkdir_specs",
          gate.run({"tool_input": {"command": "mkdir -p openspec/specs/cap"}})["decision"] == "block")
    check("gg_ln_gigacode",
          gate.run({"tool_input": {"command": "ln -s /tmp/x .gigacode/x"}})["decision"] == "block")
    check("gg_chmod_gigacode",
          gate.run({"tool_input": {"command": "chmod 777 .gigacode/hooks/router.py"}})["decision"] == "block")
    check("gg_cat_gigacode_allows",  # reading an enforcement file is allow-listed
          gate.run({"tool_input": {"command": "cat .gigacode/hooks/router.py"}})["decision"] == "allow")

    # --- Codex round 8 (review on cad914a): deeper structural edges ---
    # a leading redirection must not hide the command (program = first positional)
    check("gg_leading_redirect_reset",
          gate.run({"tool_input": {"command": ">/tmp/out git reset --hard"}})["decision"] == "block")
    check("gg_leading_redirect_fd",
          gate.run({"tool_input": {"command": "2>/dev/null git reset --hard"}})["decision"] == "block")
    # alias defined via --config-env (value in an env var) — unresolvable → block
    check("gg_config_env_alias_blocks",
          gate.run({"tool_input": {"command": "git --config-env=alias.nuke=A nuke"}})["decision"] == "block")
    # GIT_CONFIG_* env-config alias mechanism → block; legit GIT_CONFIG_GLOBAL stays ok
    check("gg_git_config_env_alias_blocks",
          gate.run({"tool_input": {"command": "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.x GIT_CONFIG_VALUE_0='reset --hard' git x"}})["decision"] == "block")
    check("gg_git_config_global_allows",
          gate.run({"tool_input": {"command": "GIT_CONFIG_GLOBAL=/dev/null git status"}})["decision"] == "allow")
    # checkout pathspec magic (:/path) restores a tracked file, not a branch switch
    check("gg_checkout_pathspec_magic",
          gate.run({"tool_input": {"command": "git checkout :/README.md"}})["decision"] == "block")
    # find deleting via an indirect executor (sh -c) still targets enforcement
    check("gg_find_exec_sh_blocks",
          gate.run({"tool_input": {"command": "find .gigacode -exec sh -c 'rm -rf $1' sh {} +"}})["decision"] == "block")
    check("gg_find_read_allows",  # find without an active action is a read/list
          gate.run({"tool_input": {"command": "find .gigacode -name '*.py'"}})["decision"] == "allow")

    # --- Codex round 9 (review on 4136d1e) ---
    # git path-mutating subcommands (rm/mv) on enforcement paths
    check("gg_git_rm_gigacode",
          gate.run({"tool_input": {"command": "git rm .gigacode/hooks/router.py"}})["decision"] == "block")
    check("gg_git_mv_gigacode",
          gate.run({"tool_input": {"command": "git mv .gigacode/hooks/router.py /tmp/x"}})["decision"] == "block")
    check("gg_git_rm_benign_allows",
          gate.run({"tool_input": {"command": "git rm old.py"}})["decision"] == "allow")
    # destructive command hidden in a shell function body (header is a transparent prefix)
    check("gg_func_body_reset",
          gate.run({"tool_input": {"command": "f(){ git reset --hard; }; f"}})["decision"] == "block")
    check("gg_func_kw_body_reset",
          gate.run({"tool_input": {"command": "function f { git reset --hard; }; f"}})["decision"] == "block")
    check("gg_func_spaced_body",
          gate.run({"tool_input": {"command": "f () { rm -rf .gigacode; }; f"}})["decision"] == "block")
    # wrapper value-options consume their value, so the tail command is inspected
    check("gg_timeout_signal_reset",
          gate.run({"tool_input": {"command": "timeout -s TERM 5 git reset --hard"}})["decision"] == "block")
    check("gg_timeout_duration_suffix",
          gate.run({"tool_input": {"command": "timeout 5s git reset --hard"}})["decision"] == "block")
    check("gg_xargs_argfile_reset",
          gate.run({"tool_input": {"command": "xargs -a /dev/null git reset --hard"}})["decision"] == "block")
    check("gg_env_unset_reset",
          gate.run({"tool_input": {"command": "env -u FOO git reset --hard"}})["decision"] == "block")
    check("gg_timeout_benign_allows",  # benign wrapped command still allowed
          gate.run({"tool_input": {"command": "timeout -s TERM 5 git status"}})["decision"] == "allow")


def test_context_inject():
    gate = load_gate("gate_context_inject")
    with fixture_root() as tmp:
        result = gate.run({"hook_event_name": "SessionStart"})
        ctx = result.get("additionalContext", "")
        check("ci_session_rules", "reverse-analysis" in ctx, ctx[:200])
        check("ci_session_openspec", "create-once" in ctx, ctx[:400])
        check("ci_session_caps_none", "none" in ctx, ctx[-200:])
        os.makedirs(os.path.join(tmp, "openspec", "specs", "cap-a"))
        ctx2 = gate.run({"hook_event_name": "SessionStart"}).get("additionalContext", "")
        check("ci_session_caps_listed", "cap-a" in ctx2, ctx2[-200:])
        sub = gate.run({"hook_event_name": "SubagentStart", "agent_type": "documentation"})
        check("ci_subagent_search", "find_symbol" in sub.get("additionalContext", ""))
        cmd = gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "/reverse-analysis card"})
        check("ci_command_bootstrap", "bootstrap" in cmd.get("additionalContext", "").lower())
        other = gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "привет"})
        check("ci_other_prompt_silent", "additionalContext" not in other)
        ws = gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "  /reverse-analysis x"})
        check("ci_command_whitespace", "bootstrap" in ws.get("additionalContext", "").lower())
        check("ci_empty_event", gate.run({}) == {"decision": "allow"})


def test_preflight():
    gate = load_gate("preflight_check")
    check("pf_unrelated",
          gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "hello"})["decision"] == "allow")
    check("pf_missing_feature",
          gate.run({"hook_event_name": "UserPromptSubmit", "prompt": "сделай реверс-анализ"})["decision"] == "block")
    complete = "reverse-analysis feature Card Blocking jira ABC-123"
    check("pf_complete",
          gate.run({"hook_event_name": "UserPromptSubmit", "prompt": complete})["decision"] == "allow")
    # documented slash form: feature is the quoted argument, not a keyword prefix
    check("pf_slash_feature",
          gate.run({"hook_event_name": "UserPromptSubmit",
                    "prompt": '/reverse-analysis "Card Blocking" code-only'})["decision"] == "allow")
    # slash command carrying only a context flag (no feature) still asks
    check("pf_slash_no_feature",
          gate.run({"hook_event_name": "UserPromptSubmit",
                    "prompt": "/reverse-analysis code-only"})["decision"] == "block")
    check("pf_wrong_event",
          gate.run({"hook_event_name": "PreToolUse", "prompt": "реверс"})["decision"] == "allow")
    payload = b"\xef\xbb\xbf" + json.dumps(
        {"hook_event_name": "UserPromptSubmit", "prompt": "сделай реверс-анализ"}).encode("utf-8")
    proc = subprocess.run([sys.executable, os.path.join(GATES_DIR, "preflight_check.py")],
                          input=payload, stdout=subprocess.PIPE, timeout=60)
    data = json.loads(proc.stdout.decode("utf-8"))
    check("pf_cli_bom", data["decision"] == "block", repr(data))


def test_spec_bootstrap():
    gate = load_gate("gate_spec_bootstrap")
    with fixture_root() as tmp:
        ev = {"hook_event_name": "PreToolUse", "tool_name": "WriteFile",
              "tool_input": {"file_path": "openspec/specs/new-cap/spec.md"}}
        check("sb_new_allow", gate.run(ev)["decision"] == "allow")
        write_file(tmp, "openspec/specs/new-cap/spec.md", "# Spec\n")
        check("sb_existing_block", gate.run(ev)["decision"] == "block")
        other = {"tool_input": {"file_path": "openspec/specs/notes.md"}}
        check("sb_other_block", gate.run(other)["decision"] == "block")
        fr = gate.run({"tool_input": {"file_path": "analytics/functional-requirements/Card.adoc"}})
        check("sb_fr_advisory", fr["decision"] == "allow" and "additionalContext" in fr, repr(fr))
        check("sb_unrelated", gate.run({"tool_input": {"file_path": "src/Main.kt"}})["decision"] == "allow")
        # regression: a // that the OS collapses must not slip past create-once
        check("sb_double_slash_existing",
              gate.run({"tool_input": {"file_path": "openspec//specs/new-cap/spec.md"}})["decision"] == "block")
        # canonicalization must still ALLOW a genuinely new cap reached via //
        check("sb_double_slash_new",
              gate.run({"tool_input": {"file_path": "openspec//specs/fresh-cap/spec.md"}})["decision"] == "allow")
        # regression: NotebookEdit's notebook_path field must be guarded too
        nb = {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "openspec/specs/new-cap/spec.md"}}
        check("sb_notebook_block", gate.run(nb)["decision"] == "block")


def test_techdocs():
    gate = load_gate("gate_techdocs")
    with fixture_root() as tmp:
        rel = "docs/features/card-blocking/overview.adoc"
        write_file(tmp, rel, GOOD_TECHDOC)
        check("td_good", gate.run(file_event(rel))["decision"] == "allow")
        write_file(tmp, rel, "= Обзор\n\nБез атрибутов.\n")
        check("td_missing_attrs", gate.run(file_event(rel))["decision"] == "block")
        write_file(tmp, rel, GOOD_TECHDOC + "\n```code```\n")
        check("td_markdown", gate.run(file_event(rel))["decision"] == "block")
        write_file(tmp, rel, "= Overview\n:feature: x\n:run-date: d\n:code-commit: c\n\nEnglish only.\n")
        check("td_non_russian", gate.run(file_event(rel))["decision"] == "block")
        check("td_other_path",
              gate.run(file_event("docs/features/card-blocking/journal.md"))["decision"] == "allow")


def test_final_format():
    gate = load_gate("gate_final_format")
    with fixture_root() as tmp:
        rel = "analytics/use-case/CardBlocking.adoc"
        write_file(tmp, rel, GOOD_FINAL_ADOC)
        check("ff_good_adoc", gate.run(file_event(rel))["decision"] == "allow")
        bad = "analytics/use-case/cardBlocking.adoc"
        write_file(tmp, bad, GOOD_FINAL_ADOC)
        check("ff_lower_name", gate.run(file_event(bad))["decision"] == "block")
        check("ff_puml_misplaced",
              gate.run(file_event("analytics/use-case/Diagram.puml"))["decision"] == "block")
        write_file(tmp, "architecture/Context.puml", "@startuml\nA -> B\n@enduml\n")
        check("ff_puml_ok", gate.run(file_event("architecture/Context.puml"))["decision"] == "allow")
        write_file(tmp, "architecture/Broken.puml", "@startuml\nA -> B\n")
        check("ff_puml_tags", gate.run(file_event("architecture/Broken.puml"))["decision"] == "block")
        check("ff_sql_misplaced",
              gate.run(file_event("analytics/db/data-model/Init.sql"))["decision"] == "block")
        write_file(tmp, "analytics/db/data-model/Model.dbml", "Table users { id int }\n")
        check("ff_dbml_ok",
              gate.run(file_event("analytics/db/data-model/Model.dbml"))["decision"] == "allow")
        write_file(tmp, "analytics/api/event/CardEvent.json", "{broken")
        check("ff_bad_json",
              gate.run(file_event("analytics/api/event/CardEvent.json"))["decision"] == "block")
        check("ff_gitkeep",
              gate.run(file_event("analytics/use-case/.gitkeep"))["decision"] == "allow")
        fail_script = write_file(tmp, "fail.py", "import sys\nsys.exit(1)\n")
        write_qg(tmp, {"final_validators": [
            {"name": "always-fail", "command": f'python "{fail_script}"',
             "applies_to": ["analytics/use-case/**"], "timeout": 30}]})
        check("ff_validator_fail", gate.run(file_event(rel))["decision"] == "block")
        write_qg(tmp, {"final_validators": [
            {"name": "ghost", "command": "no-such-binary-xyz",
             "applies_to": ["analytics/**"], "timeout": 5}]})
        check("ff_validator_missing", gate.run(file_event(rel))["decision"] == "allow")
        write_qg(tmp, {"final_validators": [
            {"name": "off", "command": "", "applies_to": ["**"]}]})
        check("ff_validator_unconfigured", gate.run(file_event(rel))["decision"] == "allow")
        # absolute file_path (Claude Code's default) must be relativized against
        # the template root first, so the module dir (…/modules/analytics) is not
        # mistaken for the final-tree `analytics/` component.
        os.environ["GIGACODE_ROOT"] = "/work/modules/analytics"
        try:
            check("ff_abs_relativized",
                  gate.rel_tree_path("/work/modules/analytics/analytics/use-case/Foo.adoc")
                  == "analytics/use-case/Foo.adoc")
            check("ff_abs_module_file_ignored",
                  gate.rel_tree_path("/work/modules/analytics/README.md") == "")
        finally:
            os.environ["GIGACODE_ROOT"] = tmp  # restore for any later checks
        # the final tree is ROOT-level analytics/ + architecture/ only — a nested
        # source path like src/analytics/model.py must not be treated as a final
        # artifact (anchored match, not search-anywhere).
        check("ff_nested_analytics_ignored", gate.rel_tree_path("src/analytics/model.py") == "")
        check("ff_nested_architecture_ignored", gate.rel_tree_path("app/architecture/x.puml") == "")


def manifest(status, **extra):
    data = {"feature": "card-blocking", "run_date": "2026-06-11",
            "code_commit": "abc1234", "status": status,
            "capability": "card-blocking",
            "produced": {"technical": [], "spec": "", "final": []}}
    data.update(extra)
    return json.dumps(data, ensure_ascii=False)


def write_techdocs(tmp):
    for doc in ("overview", "flow", "integrations", "data", "questions"):
        write_file(tmp, f"docs/features/card-blocking/{doc}.adoc", GOOD_TECHDOC)


def test_validate_run_output():
    gate = load_gate("validate_run_output")
    with fixture_root() as tmp:
        check("vr_no_runs", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        write_file(tmp, "docs/features/card-blocking/manifest.json", manifest("scoping"))
        check("vr_scoping", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        write_file(tmp, "docs/features/card-blocking/manifest.json", manifest("draft"))
        check("vr_draft_missing", gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        write_techdocs(tmp)
        check("vr_draft_ready", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        write_file(tmp, "docs/features/card-blocking/manifest.json", manifest("confirmed"))
        check("vr_confirmed_no_spec", gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        write_file(tmp, "openspec/specs/card-blocking/spec.md", "## Requirements\n")
        check("vr_confirmed_ok", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        write_file(tmp, "docs/features/card-blocking/manifest.json",
                   manifest("complete", produced={
                       "technical": ["docs/features/card-blocking/overview.adoc"],
                       "spec": "openspec/specs/card-blocking/spec.md",
                       "final": ["analytics/use-case/CardBlocking.adoc"]}))
        check("vr_complete_missing_final",
              gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        write_file(tmp, "analytics/use-case/CardBlocking.adoc", GOOD_FINAL_ADOC)
        check("vr_complete_ok", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")
        # produced.final pointing only at a .gitkeep placeholder is not a real final
        write_file(tmp, "analytics/use-case/.gitkeep", "")
        write_file(tmp, "docs/features/card-blocking/manifest.json",
                   manifest("complete", produced={
                       "technical": ["docs/features/card-blocking/overview.adoc"],
                       "spec": "openspec/specs/card-blocking/spec.md",
                       "final": ["analytics/use-case/.gitkeep"]}))
        check("vr_complete_gitkeep_final",
              gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        # produced.final pointing at a directory (not a file) is not a real final
        write_file(tmp, "docs/features/card-blocking/manifest.json",
                   manifest("complete", produced={
                       "technical": ["docs/features/card-blocking/overview.adoc"],
                       "spec": "openspec/specs/card-blocking/spec.md",
                       "final": ["analytics/use-case"]}))
        check("vr_complete_dir_final",
              gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        # produced.final pointing at an existing file OUTSIDE the final tree
        # (root-level analytics/ + architecture/ only) is not a real final —
        # a manifest can't close a complete run by naming e.g. README.md.
        write_file(tmp, "README.md", "# readme\n")
        write_file(tmp, "docs/features/card-blocking/manifest.json",
                   manifest("complete", produced={
                       "technical": ["docs/features/card-blocking/overview.adoc"],
                       "spec": "openspec/specs/card-blocking/spec.md",
                       "final": ["README.md"]}))
        check("vr_complete_final_outside_tree",
              gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        # complete with empty produced.final must NOT pass (finals required)
        write_file(tmp, "docs/features/card-blocking/manifest.json",
                   manifest("complete", produced={
                       "technical": ["docs/features/card-blocking/overview.adoc"],
                       "spec": "openspec/specs/card-blocking/spec.md",
                       "final": []}))
        check("vr_complete_empty_final",
              gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        write_file(tmp, "docs/features/card-blocking/manifest.json", "{broken")
        check("vr_bad_manifest", gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        # regression: a non-iterable produced.<group> must not crash run()
        # (router would convert the crash to a fail-open allow on this non-safety
        # route). final is a non-empty existing file so the complete-rule is met;
        # technical stays non-iterable (7) — the crash-safety case under test.
        write_file(tmp, "docs/features/card-blocking/manifest.json",
                   manifest("complete", produced={"technical": 7,
                                                  "final": ["analytics/use-case/CardBlocking.adoc"]}))
        check("vr_produced_not_list", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")


def test_path_relativization():
    """Some runtimes (Qwen on Windows) report ABSOLUTE tool paths; gates compare
    against repo-relative globs/prefixes. path_from_event must relativize an
    absolute in-repo path so content gates don't silently skip it."""
    spec = importlib.util.spec_from_file_location(
        "alib", os.path.join(GATES_DIR, "_lib.py"))
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    with fixture_root() as tmp:
        rel = lib.path_from_event(file_event("docs/features/card/x.adoc"))
        check("rel_path_unchanged", rel == "docs/features/card/x.adoc", rel)
        absp = os.path.join(tmp, "docs", "features", "card", "x.adoc")
        got = lib.path_from_event(file_event(absp))
        check("abs_path_relativized", got == "docs/features/card/x.adoc", got)


def main():
    test_git_guard()
    test_path_relativization()
    test_context_inject()
    test_preflight()
    test_spec_bootstrap()
    test_techdocs()
    test_final_format()
    test_validate_run_output()
    print(f"All {PASSED} gate checks passed")


if __name__ == "__main__":
    main()
