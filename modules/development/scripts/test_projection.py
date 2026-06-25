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


def make_root(journal_lines=None, state=None, config=None, stages=None,
              contracts=None, dev_dirs=None):
    """Temp root. All args optional:
      journal_lines: list[str] -> .gigacode/logs/decisions.jsonl
      state:   dict -> .gigacode/logs/router-state.json
      config:  dict -> .gigacode/hooks/router.config.json
      stages:  dict -> .gigacode/stages.json
      contracts: {slug: dict} -> docs/development/<slug>/contract.json
      dev_dirs: list[str] -> empty docs/development/<slug>/ dirs (for slug resolve)
    """
    tmp = tempfile.mkdtemp(prefix="projection-test-")

    def _write(rel, obj):
        dest = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as h:
            h.write(obj if isinstance(obj, str) else json.dumps(obj))

    if journal_lines is not None:
        logs = os.path.join(tmp, ".gigacode", "logs")
        os.makedirs(logs)
        with open(os.path.join(logs, "decisions.jsonl"), "w", encoding="utf-8") as h:
            h.write("\n".join(journal_lines) + ("\n" if journal_lines else ""))
    if state is not None:
        _write(".gigacode/logs/router-state.json", state)
    if config is not None:
        _write(".gigacode/hooks/router.config.json", config)
    if stages is not None:
        _write(".gigacode/stages.json", stages)
    for slug, body in (contracts or {}).items():
        _write(f"docs/development/{slug}/contract.json", body)
    for slug in (dev_dirs or []):
        os.makedirs(os.path.join(tmp, "docs", "development", slug), exist_ok=True)
    return tmp


STAGES_FIXTURE = {
    "version": 1,
    "stages": [
        {"id": "intake", "order": 0,
         "writes": ["docs/development/*/intake.json"], "entry_requires": []},
        {"id": "contract", "order": 1,
         "writes": ["docs/development/*/contract.json"],
         "entry_requires": [{"type": "approval", "stage": "intake"}]},
    ],
}


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


def test_budget():
    proj = load_projection()
    with root_at(make_root(config={"stop_block_budget": 2},
                           state={"stop:s-9": 1})):
        b = proj.read_budget("s-9")
        check("budget_used_limit", b == {"used": 1, "limit": 2}, b)
    with root_at(make_root()):  # nothing present
        b = proj.read_budget("s-9")
        check("budget_no_data", b == {"used": None, "limit": None}, b)


def test_scope():
    proj = load_projection()
    contract = {"scope_globs": ["src/cards/**"], "modules": ["cards"]}
    with root_at(make_root(contracts={"card": contract})):
        s = proj.read_scope("card")
        check("scope_present",
              s == {"scope_globs": ["src/cards/**"], "modules": ["cards"]}, s)
    with root_at(make_root()):
        check("scope_absent", proj.read_scope("card") is None)
        check("scope_no_slug", proj.read_scope(None) is None)


def test_resolve_slug():
    proj = load_projection()
    with root_at(make_root(dev_dirs=["alpha", "beta"])):
        slug, cands = proj.resolve_slug(None)
        check("slug_auto_picks_one", slug in ("alpha", "beta"), slug)
        check("slug_lists_all", sorted(cands) == ["alpha", "beta"], cands)
    with root_at(make_root(dev_dirs=["alpha"])):
        check("slug_explicit", proj.resolve_slug("zzz") == ("zzz", ["zzz"]))
    with root_at(make_root()):
        check("slug_none", proj.resolve_slug(None) == (None, []))


def test_read_stage():
    proj = load_projection()
    with root_at(make_root(stages=STAGES_FIXTURE)):
        st = proj.read_stage("card")  # no intake approval -> contract not enterable
        ids = [s["id"] for s in st["stages"]]
        check("stage_lists_stages", ids == ["intake", "contract"], ids)
        check("stage_current_intake", st["current"] == "intake", st["current"])
    with root_at(make_root()):  # no stages.json
        check("stage_no_data", proj.read_stage("card") == {"current": None, "stages": []})


def test_collect():
    proj = load_projection()
    lines = [rec(session_id="s-7", kind="gate", gate="gate_lint", decision="block",
                 reason="ktlint", tool="Edit")]
    with root_at(make_root(journal_lines=lines, stages=STAGES_FIXTURE,
                           config={"stop_block_budget": 2}, state={"stop:s-7": 1},
                           contracts={"card": {"scope_globs": ["src/**"], "modules": ["c"]}},
                           dev_dirs=["card"])):
        snap = proj.collect(tail_n=5)
        check("collect_session", snap["session"] == "s-7", snap["session"])
        check("collect_slug", snap["slug"] == "card", snap["slug"])
        check("collect_budget", snap["budget"] == {"used": 1, "limit": 2}, snap["budget"])
        check("collect_decisions", len(snap["decisions"]) == 1, snap["decisions"])
        check("collect_scope", snap["scope"]["modules"] == ["c"], snap["scope"])
        check("collect_stage_current", snap["stage"]["current"] == "intake",
              snap["stage"])


def test_render():
    proj = load_projection()
    snap = {
        "session": "s-7", "slug": "card", "slug_candidates": ["card", "other"],
        "stage": {"current": "contract",
                  "stages": [
                      {"id": "intake", "order": 0, "enterable": True,
                       "met": [], "unmet": []},
                      {"id": "contract", "order": 1, "enterable": True,
                       "met": ["approval:intake"], "unmet": []},
                      {"id": "plan", "order": 2, "enterable": False,
                       "met": [], "unmet": ["approval:contract"]}]},
        "budget": {"used": 1, "limit": 2},
        "decisions": [
            {"ts": "2026-06-25T14:02:30+0300", "kind": "gate", "decision": "ask",
             "gate": "git_guard", "tool": "Bash", "reason": "writes .github/"},
            {"ts": "2026-06-25T14:03:01+0300", "kind": "gate", "decision": "block",
             "gate": "gate_stage_order", "tool": "Edit",
             "reason": "стадия 'plan' не разблокирована"}],
        "scope": {"scope_globs": ["src/cards/**"], "modules": ["cards"]},
    }
    out = proj.render_snapshot(snap, color=False)
    check("render_has_session", "s-7" in out, out)
    check("render_current_stage", "contract" in out, out)
    check("render_budget", "1/2" in out, out)
    check("render_scope_glob", "src/cards/**" in out, out)
    check("render_decision_reason", "git_guard" in out and "block" in out, out)
    check("render_multi_hint", "other" in out, out)  # >1 candidate -> hint lists them
    check("render_no_ansi_when_off", "\x1b[" not in out, repr(out))
    # empty/None snapshot must not crash
    blank = {"session": None, "slug": None, "slug_candidates": [],
             "stage": {"current": None, "stages": []},
             "budget": {"used": None, "limit": None}, "decisions": [], "scope": None}
    blank_out = proj.render_snapshot(blank, color=False)
    check("render_blank_ok", isinstance(blank_out, str) and blank_out, repr(blank_out))
    # color=True emits ANSI for a block/ask decision
    colored = proj.render_snapshot(snap, color=True)
    check("render_ansi_when_on", "\x1b[" in colored)


if __name__ == "__main__":
    test_journal_reader()
    test_budget()
    test_scope()
    test_resolve_slug()
    test_read_stage()
    test_collect()
    test_render()
    print(f"\n{PASSED} checks passed")
