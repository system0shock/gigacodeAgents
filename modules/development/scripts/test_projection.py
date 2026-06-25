#!/usr/bin/env python3
"""Offline unit tests for projection.py. Run from the repo root:
    python scripts/test_projection.py

projection.py is loaded in-process; each test builds a throwaway template root
in a temp dir and points _lib.root() at it via the GIGACODE_ROOT env override
(same pattern as test_stage_order.py)."""
import importlib.util
import json
import os
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(ROOT, ".gigacode", "hooks")
PASSED = 0


def load_projection():
    path = os.path.join(HOOKS_DIR, "projection.py")
    spec = importlib.util.spec_from_file_location("projection_under_test", path)
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
    """Context manager: point _lib.root() at a fixture tree, clean up after."""

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


def make_root(journal_lines=None):
    """Temp root with an optional .gigacode/logs/decisions.jsonl.
    journal_lines is a list of raw strings (already including any broken ones)."""
    tmp = tempfile.mkdtemp(prefix="projection-test-")
    if journal_lines is not None:
        logs = os.path.join(tmp, ".gigacode", "logs")
        os.makedirs(logs)
        with open(os.path.join(logs, "decisions.jsonl"), "w", encoding="utf-8") as h:
            h.write("\n".join(journal_lines) + ("\n" if journal_lines else ""))
    return tmp


def rec(**kw):
    base = {"session_id": "", "feature": "", "agent": "", "kind": "final",
            "event": "PreToolUse", "tool": "Edit", "decision": "allow",
            "ts": "2026-06-25T10:00:00+0300"}
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


def test_journal_reader():
    proj = load_projection()
    # missing journal -> [] (no crash)
    with root_at(make_root(journal_lines=None)):
        check("missing_journal_empty", proj.read_decisions() == [])
    # broken lines are skipped; good lines parsed; tail_n respected; oldest-first
    lines = [rec(decision="allow", tool="A"),
             "{ this is not json",
             "",
             rec(decision="block", tool="B"),
             rec(decision="ask", tool="C")]
    with root_at(make_root(journal_lines=lines)):
        out = proj.read_decisions(tail_n=2)
        check("skips_broken_and_tails", len(out) == 2, out)
        check("tail_oldest_first",
              out[0]["tool"] == "B" and out[1]["tool"] == "C", out)
    # latest_session picks the last non-empty session_id
    lines = [rec(session_id="s-1"), rec(session_id=""), rec(session_id="s-2")]
    with root_at(make_root(journal_lines=lines)):
        decisions = proj.read_decisions(tail_n=10)
        check("latest_session", proj.latest_session(decisions) == "s-2",
              proj.latest_session(decisions))
        check("latest_session_none", proj.latest_session([]) is None)


if __name__ == "__main__":
    test_journal_reader()
    print(f"\n{PASSED} checks passed")
