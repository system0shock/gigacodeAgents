#!/usr/bin/env python3
"""Offline unit tests for observer.py. Run from the repo root:
    python scripts/test_observer.py

observer.py is loaded in-process; fixtures point _lib.root() at a temp tree via
the GIGACODE_ROOT env override (same pattern as test_projection.py)."""
import importlib.util
import json
import os
import shutil
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(ROOT, ".gigacode", "hooks")
PASSED = 0


def load_mod(name):
    path = os.path.join(HOOKS_DIR, name + ".py")
    spec = importlib.util.spec_from_file_location(name + "_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(name, condition, detail=""):
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


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
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def _write(tmp, rel, obj):
    dest = os.path.join(tmp, *rel.split("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as h:
        h.write(obj if isinstance(obj, str) else json.dumps(obj))


def make_root(intake=None, verdict=None):
    tmp = tempfile.mkdtemp(prefix="observer-test-")
    if intake is not None:
        _write(tmp, "docs/development/card/intake.json", intake)
    if verdict is not None:
        _write(tmp, "docs/development/card/verdict.json", verdict)
    return tmp


TS = "2026-06-25T15:00:00+0300"
NOW = datetime.strptime("2026-06-25T15:00:30+0300", "%Y-%m-%dT%H:%M:%S%z")


def rec(ts, decision="allow", tool="Edit", kind="gate", gate="g"):
    return {"session_id": "s-1", "feature": "card", "agent": "coder", "kind": kind,
            "gate": gate, "decision": decision, "tool": tool, "ts": ts, "reason": ""}


def test_readers():
    obs = load_mod("observer")
    with root_at(make_root(intake={"task_type": "feature", "scope_intent": "x",
                                   "acceptance": ["a"], "constraints": [],
                                   "understanding": "u"})):
        ik = obs.read_intake("card")
        check("intake_subset", ik["task_type"] == "feature" and ik["understanding"] == "u", ik)
    with root_at(make_root()):
        check("intake_absent_none", obs.read_intake("card") is None)
        check("verdict_absent_none", obs.read_verdict("card") is None)
    with root_at(make_root(verdict={"result": "pass", "risk": {"out_of_contract_files": 0},
                                    "findings": []})):
        vd = obs.read_verdict("card")
        check("verdict_subset", vd["result"] == "pass", vd)


def test_vitals():
    obs = load_mod("observer")
    decisions = [rec("2026-06-25T15:00:00+0300", "allow", "Edit"),
                 rec("2026-06-25T15:00:10+0300", "block", "Bash"),
                 rec("2026-06-25T15:00:20+0300", "allow", "Edit")]
    v = obs.vitals(decisions, NOW)
    check("vitals_total", v["total"] == 3, v)
    check("vitals_counts", v["block"] == 1 and v["allow"] == 2, v)
    check("vitals_idle", v["idle_sec"] == 10, v)         # NOW - last(15:00:20) = 10s
    check("vitals_session", v["session_sec"] == 20, v)   # 15:00:20 - 15:00:00
    check("vitals_tools", v["tools"]["Edit"] == 2 and v["tools"]["Bash"] == 1, v)
    empty = obs.vitals([], NOW)
    check("vitals_empty_total", empty["total"] == 0, empty)
    check("vitals_empty_idle", empty["idle_sec"] is None, empty)
    check("vitals_empty_session", empty["session_sec"] == 0, empty)
    check("vitals_empty_tools", empty["tools"] == {}, empty)


def test_blocker():
    obs = load_mod("observer")
    snap = {"slug": "card", "stage": {"current": "contract", "stages": [
        {"id": "intake", "order": 0, "enterable": True, "met": [], "unmet": []},
        {"id": "plan", "order": 2, "enterable": False, "met": [], "unmet": ["approval:contract"]}]}}
    b = obs.blocker(snap, [rec(TS, "block", "Edit")])
    check("blocker_active", b["active"] is True, b)
    check("blocker_unmet", b["unmet"] == "approval:contract", b)
    check("blocker_command",
          b["command"] == "python .gigacode/hooks/confirm.py contract card", b)
    clear = {"slug": "card", "stage": {"current": "delivery", "stages": [
        {"id": "delivery", "order": 4, "enterable": True, "met": [], "unmet": []}]}}
    check("blocker_none_when_clear", obs.blocker(clear, [rec(TS, "allow")]) is None)


def test_enrich():
    obs = load_mod("observer")
    snap = {"session": "s-1", "slug": "card", "slug_candidates": ["card"],
            "stage": {"current": "contract", "stages": [
                {"id": "plan", "order": 2, "enterable": False, "met": [],
                 "unmet": ["approval:contract"]}]},
            "budget": {"used": 0, "limit": 2}, "scope": None, "decisions": []}
    with root_at(make_root(intake={"task_type": "feature", "scope_intent": "x",
                                   "acceptance": [], "constraints": [], "understanding": "u"})):
        out = obs.enrich(snap, [rec(TS, "block", "Edit")], NOW)
    check("enrich_contract", out["_contract"] == "wi15/1", out.get("_contract"))
    check("enrich_keeps_base", out["budget"] == {"used": 0, "limit": 2})
    check("enrich_intake", out["intake"]["task_type"] == "feature")
    check("enrich_vitals", out["vitals"]["total"] == 1)
    check("enrich_blocker", out["blocker"]["active"] is True)
    check("enrich_verdict_none", out["verdict"] is None)


def test_parse_ts():
    obs = load_mod("observer")
    check("parse_ts_valid", obs.parse_ts("2026-06-25T15:00:00+0300") is not None)
    check("parse_ts_none", obs.parse_ts(None) is None)
    check("parse_ts_int", obs.parse_ts(12345) is None)
    check("parse_ts_garbage", obs.parse_ts("not-a-timestamp") is None)
    check("parse_ts_empty", obs.parse_ts("") is None)


if __name__ == "__main__":
    test_readers()
    test_vitals()
    test_blocker()
    test_enrich()
    test_parse_ts()
    print(f"\n{PASSED} checks passed")
