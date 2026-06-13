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
        write_file(tmp, "docs/features/card-blocking/manifest.json", "{broken")
        check("vr_bad_manifest", gate.run({"hook_event_name": "Stop"})["decision"] == "block")
        # regression: a non-iterable produced.<group> must not crash run()
        # (router would convert the crash to a fail-open allow on this non-safety route)
        write_file(tmp, "docs/features/card-blocking/manifest.json",
                   manifest("complete", produced={"technical": 7, "final": []}))
        check("vr_produced_not_list", gate.run({"hook_event_name": "Stop"})["decision"] == "allow")


def main():
    test_git_guard()
    test_context_inject()
    test_preflight()
    test_spec_bootstrap()
    test_techdocs()
    test_final_format()
    test_validate_run_output()
    print(f"All {PASSED} gate checks passed")


if __name__ == "__main__":
    main()
