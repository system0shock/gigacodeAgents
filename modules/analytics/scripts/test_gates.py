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
    shutil.copy(os.path.join(ROOT, "rules", "reverse-analysis.md"),
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


def test_context_inject():
    gate = load_gate("gate_context_inject")
    with fixture_root() as tmp:
        result = gate.run({"hook_event_name": "SessionStart"})
        ctx = result.get("additionalContext", "")
        check("ci_session_rules", "reverse-analysis" in ctx, ctx[:200])
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


def main():
    test_git_guard()
    test_context_inject()
    print(f"All {PASSED} gate checks passed")


if __name__ == "__main__":
    main()
