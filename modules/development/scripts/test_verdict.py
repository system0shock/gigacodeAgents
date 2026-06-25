#!/usr/bin/env python3
"""Offline tests for gate_verdict (WI-11): the mechanical verdict.json producer.
Run from modules/development:  python scripts/test_verdict.py

Each test builds a throwaway git repo (so git_changed_paths sees the tree) with a
fake test command whose exit code is controllable, runs the Stop gate against it
via the GIGACODE_ROOT override, and inspects the produced verdict.json."""
import importlib.util
import json
import os
import shutil
import subprocess
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
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


def make_repo(test_exit=0, with_tasks=True, with_code=True, test_command=None,
              slug="card", state=None, missing_inputs=None, contract=None):
    tmp = tempfile.mkdtemp(prefix="verdict-test-")
    os.makedirs(os.path.join(tmp, ".gigacode", "logs"))
    # the fake test script lives under .gigacode/ so it is NOT counted as changed
    # product code (changed_code_files excludes .gigacode/) — matching reality
    # where the test command (./gradlew test) is not product source.
    with open(os.path.join(tmp, ".gigacode", "fake_test.py"), "w", encoding="utf-8") as h:
        h.write("import sys\nsys.exit(%d)\n" % test_exit)
    cmd = "python .gigacode/fake_test.py" if test_command is None else test_command
    with open(os.path.join(tmp, ".gigacode", "quality-gates.json"), "w", encoding="utf-8") as h:
        json.dump({"test": {"command": cmd, "timeout_seconds": 30}}, h)
    devdir = os.path.join(tmp, "docs", "development", slug)
    os.makedirs(devdir)
    with open(os.path.join(devdir, "journal.md"), "w", encoding="utf-8") as h:
        h.write("notes\n")
    with open(os.path.join(devdir, "intake.json"), "w", encoding="utf-8") as h:
        json.dump({"task_type": "feature", "missing_inputs": missing_inputs or []}, h)
    if contract is not None:
        with open(os.path.join(devdir, "contract.json"), "w", encoding="utf-8") as h:
            json.dump(contract, h)
    if with_tasks:
        td = os.path.join(tmp, "openspec", "changes", slug)
        os.makedirs(td)
        with open(os.path.join(td, "tasks.md"), "w", encoding="utf-8") as h:
            h.write("# tasks\n")
    if with_code:
        cd = os.path.join(tmp, "src", "cards")
        os.makedirs(cd)
        with open(os.path.join(cd, "CardService.kt"), "w", encoding="utf-8") as h:
            h.write("class CardService\n")
    if state is not None:
        with open(os.path.join(tmp, ".gigacode", "logs", "router-state.json"),
                  "w", encoding="utf-8") as h:
            json.dump(state, h)
    subprocess.run(["git", "init", "-q"], cwd=tmp,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return tmp


class root_at:
    def __init__(self, tmp):
        self.tmp = tmp

    def __enter__(self):
        self._orig = os.environ.get("GIGACODE_ROOT")
        os.environ["GIGACODE_ROOT"] = self.tmp
        return self.tmp

    def __exit__(self, *exc):
        if self._orig is None:
            os.environ.pop("GIGACODE_ROOT", None)
        else:
            os.environ["GIGACODE_ROOT"] = self._orig
        return False


def stop_event(**kw):
    e = {"hook_event_name": "Stop", "session_id": "s1"}
    e.update(kw)
    return e


def verdict_path(root, slug="card"):
    return os.path.join(root, "docs", "development", slug, "verdict.json")


def read_verdict(root, slug="card"):
    with open(verdict_path(root, slug), "r", encoding="utf-8") as h:
        return json.load(h)


def test_pass():
    g = load_gate("gate_verdict")
    root = make_repo(test_exit=0)
    try:
        with root_at(root):
            res = g.run(stop_event())
        check("verdict_decision_allow", res["decision"] == "allow", res)
        v = read_verdict(root)
        check("verdict_stage_verify", v["stage"] == "verify", v)
        check("verdict_result_pass", v["result"] == "pass", v)
        check("verdict_findings_empty_on_pass", v["findings"] == [], v)
        check("verdict_scope_diff_files", v["risk"]["scope_diff_files"] >= 1, v["risk"])
        check("verdict_modules_touched", v["risk"]["modules_touched"] >= 1, v["risk"])
        check("verdict_out_of_contract_null", v["risk"]["out_of_contract_files"] is None, v["risk"])
        check("verdict_overshoot_zero", v["risk"]["overshoot_asks"] == 0, v["risk"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_fail():
    g = load_gate("gate_verdict")
    root = make_repo(test_exit=1)
    try:
        with root_at(root):
            g.run(stop_event())
        v = read_verdict(root)
        check("verdict_result_fail", v["result"] == "fail", v)
        check("verdict_findings_on_fail", len(v["findings"]) >= 1, v)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_production():
    g = load_gate("gate_verdict")
    # no test command -> no verdict (no mechanical pass signal)
    root = make_repo(test_command="")
    try:
        with root_at(root):
            g.run(stop_event())
        check("no_test_cmd_no_verdict", not os.path.exists(verdict_path(root)))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # before verify (no openspec tasks.md) -> no verdict
    root = make_repo(test_exit=0, with_tasks=False)
    try:
        with root_at(root):
            g.run(stop_event())
        check("no_tasks_no_verdict", not os.path.exists(verdict_path(root)))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # non-Stop event -> no verdict
    root = make_repo(test_exit=0)
    try:
        with root_at(root):
            g.run({"hook_event_name": "PreToolUse"})
        check("non_stop_no_verdict", not os.path.exists(verdict_path(root)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_mechanical_risk_fields():
    g = load_gate("gate_verdict")
    # iteration_budget_left = budget(2) - state count
    root = make_repo(test_exit=0, state={"stop:s1": 1})
    try:
        with root_at(root):
            g.run(stop_event(session_id="s1"))
        v = read_verdict(root)
        check("budget_left_from_state", v["risk"]["iteration_budget_left"] == 1, v["risk"])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # open_questions = len(intake.missing_inputs)
    root = make_repo(test_exit=0, missing_inputs=["env?", "creds?"])
    try:
        with root_at(root):
            g.run(stop_event())
        v = read_verdict(root)
        check("open_questions_from_missing_inputs", v["risk"]["open_questions"] == 2, v["risk"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_out_of_contract():
    # WI-8: out_of_contract_files is now computed from contract.scope_globs.
    g = load_gate("gate_verdict")
    # the changed file src/cards/CardService.kt is inside the contract scope -> 0
    root = make_repo(test_exit=0,
                     contract={"scope_globs": ["src/cards/**"], "modules": ["cards"]})
    try:
        with root_at(root):
            g.run(stop_event())
        v = read_verdict(root)
        check("out_of_contract_zero_in_scope", v["risk"]["out_of_contract_files"] == 0, v["risk"])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # the changed file is OUTSIDE the contract scope -> counted
    root = make_repo(test_exit=0,
                     contract={"scope_globs": ["src/other/**"], "modules": ["other"]})
    try:
        with root_at(root):
            g.run(stop_event())
        v = read_verdict(root)
        check("out_of_contract_counted", v["risk"]["out_of_contract_files"] >= 1, v["risk"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    test_pass()
    test_fail()
    test_no_production()
    test_mechanical_risk_fields()
    test_out_of_contract()
    print(f"\nAll {PASSED} verdict checks passed")


if __name__ == "__main__":
    main()
