#!/usr/bin/env python3
"""Offline unit tests for gate_stage_order. Run from the repo root:
    python scripts/test_stage_order.py

The gate is loaded in-process; each test builds a throwaway template root in a
temp dir and points _lib.root() at it via the GIGACODE_ROOT env override (same
pattern as test_gates.py). The gate reads root() at call time, so no reload is
needed between scenarios."""
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


# Full predicate matrix — exercises every entry_requires type. The LIVE
# stages.json defers plan->contract (WI-7); this fixture keeps it so the
# predicate engine is proven end-to-end regardless of the shipped config.
FULL_STAGES = {
    "version": 1,
    "stages": [
        {"id": "intake", "order": 0,
         "writes": ["docs/development/*/intake.json"], "entry_requires": []},
        {"id": "contract", "order": 1,
         "writes": ["docs/development/*/contract.json"],
         "entry_requires": [{"type": "approval", "stage": "intake"}]},
        {"id": "plan", "order": 2,
         "writes": ["openspec/changes/*/proposal.md",
                    "openspec/changes/*/design.md",
                    "openspec/changes/*/tasks.md"],
         "entry_requires": [{"type": "file_exists",
                             "artifact": "docs/development/<slug>/contract.json"}]},
        {"id": "verify", "order": 3,
         "writes": ["docs/development/*/verdict.json"],
         "entry_requires": [{"type": "file_exists",
                             "artifact": "openspec/changes/<slug>/tasks.md"}]},
        {"id": "delivery", "order": 4,
         "writes": ["docs/development/*/pr-summary.md"],
         "entry_requires": [{"type": "verdict_pass",
                             "artifact": "docs/development/<slug>/verdict.json"}]},
    ],
}


def make_root(stages_obj, files=None, approvals=None):
    """Temp template root with .gigacode/stages.json, optional artifact files
    (path -> content) and approval markers (list of (stage, slug))."""
    tmp = tempfile.mkdtemp(prefix="stageorder-test-")
    gig = os.path.join(tmp, ".gigacode")
    os.makedirs(gig)
    if stages_obj is not None:
        with open(os.path.join(gig, "stages.json"), "w", encoding="utf-8") as h:
            if isinstance(stages_obj, str):
                h.write(stages_obj)  # raw (for the broken-JSON case)
            else:
                json.dump(stages_obj, h)
    for rel, content in (files or {}).items():
        dest = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as h:
            h.write(content)
    for stage, slug in (approvals or []):
        adir = os.path.join(gig, "approvals", slug)
        os.makedirs(adir, exist_ok=True)
        with open(os.path.join(adir, stage + ".ok"), "w", encoding="utf-8") as h:
            h.write("{}")
    return tmp


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


def ev(path, tool="Edit"):
    return {"hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": {"file_path": path}}


def decide(gate, path, **kw):
    with root_at(make_root(**kw)):
        return gate.run(ev(path))["decision"]


def decide_full(gate, path, **kw):
    with root_at(make_root(**kw)):
        return gate.run(ev(path))


# WI-20/ADR-7: intake_complete predicate — empty required fields derive the questions.
INTAKE_STAGES = {
    "version": 1,
    "intake_required": {
        "feature": ["scope_intent", "acceptance", "understanding"],
        "bug": ["repro", "expected", "actual", "severity", "understanding"],
    },
    "stages": [
        {"id": "intake", "order": 0,
         "writes": ["docs/development/*/intake.json"], "entry_requires": []},
        {"id": "contract", "order": 1,
         "writes": ["docs/development/*/contract.json"],
         "entry_requires": [{"type": "intake_complete"},
                            {"type": "approval", "stage": "intake"}]},
    ],
}
FULL_FEATURE = {"task_type": "feature", "scope_intent": "block card on fraud",
                "acceptance": ["status -> BLOCKED"], "understanding": "restate ..."}
FULL_BUG = {"task_type": "bug", "repro": "POST /x 500", "expected": "200",
            "actual": "500", "severity": "high", "understanding": "restate ..."}


def _intake_file(slug, obj):
    return {"docs/development/%s/intake.json" % slug: json.dumps(obj)}


def test_intake_complete():
    g = load_gate("gate_stage_order")
    contract = "docs/development/card/contract.json"

    # complete feature intake + approval -> allow
    check("intake_feature_complete_allow",
          decide(g, contract, stages_obj=INTAKE_STAGES,
                 files=_intake_file("card", FULL_FEATURE),
                 approvals=[("intake", "card")]) == "allow")

    # complete bug intake + approval -> allow
    check("intake_bug_complete_allow",
          decide(g, contract, stages_obj=INTAKE_STAGES,
                 files=_intake_file("card", FULL_BUG),
                 approvals=[("intake", "card")]) == "allow")

    # missing a required field -> block, and the missing field is NAMED (the question)
    no_acc = {k: v for k, v in FULL_FEATURE.items() if k != "acceptance"}
    res = decide_full(g, contract, stages_obj=INTAKE_STAGES,
                      files=_intake_file("card", no_acc), approvals=[("intake", "card")])
    check("intake_missing_field_block", res["decision"] == "block", res)
    check("intake_missing_field_named", "acceptance" in res.get("reason", ""), res)

    # empty list / whitespace-only count as MISSING
    empty_acc = dict(FULL_FEATURE, acceptance=[])
    check("intake_empty_list_block",
          decide(g, contract, stages_obj=INTAKE_STAGES,
                 files=_intake_file("card", empty_acc),
                 approvals=[("intake", "card")]) == "block")
    blank_under = dict(FULL_FEATURE, understanding="   ")
    check("intake_blank_string_block",
          decide(g, contract, stages_obj=INTAKE_STAGES,
                 files=_intake_file("card", blank_under),
                 approvals=[("intake", "card")]) == "block")

    # bug missing severity -> block (per-task_type required set)
    no_sev = {k: v for k, v in FULL_BUG.items() if k != "severity"}
    check("intake_bug_missing_severity_block",
          decide(g, contract, stages_obj=INTAKE_STAGES,
                 files=_intake_file("card", no_sev),
                 approvals=[("intake", "card")]) == "block")

    # intake.json absent entirely -> block
    check("intake_absent_block",
          decide(g, contract, stages_obj=INTAKE_STAGES,
                 approvals=[("intake", "card")]) == "block")

    # unknown / missing task_type -> block (fail-closed: cannot derive required set)
    check("intake_unknown_tasktype_block",
          decide(g, contract, stages_obj=INTAKE_STAGES,
                 files=_intake_file("card", {"task_type": "chore", "scope_intent": "x"}),
                 approvals=[("intake", "card")]) == "block")

    # complete intake but NO approval -> still block (the approval predicate);
    # a complete intake does not let the agent skip the human understanding ack
    check("intake_complete_no_approval_block",
          decide(g, contract, stages_obj=INTAKE_STAGES,
                 files=_intake_file("card", FULL_FEATURE)) == "block")


def test_machine_owned():
    """WI-11/P6: an agent file-tool write to a machine-owned artifact (verdict.json)
    is blocked — it is produced by gate_verdict in the router process, so the agent
    cannot self-grant result:pass."""
    g = load_gate("gate_stage_order")
    mo = {"version": 1,
          "machine_owned": ["docs/development/*/verdict.json"],
          "stages": [{"id": "delivery", "order": 0,
                      "writes": ["docs/development/*/pr-summary.md"],
                      "entry_requires": []}]}
    check("verdict_agent_write_block",
          decide(g, "docs/development/card/verdict.json", stages_obj=mo) == "block")
    # a non-machine-owned path under the same tree is unaffected
    check("journal_not_machine_owned",
          decide(g, "docs/development/card/journal.md", stages_obj=mo) == "allow")
    # machine_owned blocks via any write tool form
    with root_at(make_root(stages_obj=mo)):
        ev2 = {"hook_event_name": "PreToolUse", "tool_name": "Write",
               "tool_input": {"file_path": "docs/development/card/verdict.json"}}
        check("verdict_machine_owned_any_tool", g.run(ev2)["decision"] == "block")


def test_matrix():
    g = load_gate("gate_stage_order")

    # 1. intake write, no requires -> allow
    check("intake_no_requires_allow",
          decide(g, "docs/development/card/intake.json", stages_obj=FULL_STAGES)
          == "allow")

    # 2. contract without approval:intake -> block
    check("contract_no_approval_block",
          decide(g, "docs/development/card/contract.json", stages_obj=FULL_STAGES)
          == "block")

    # 3. contract with approvals/<slug>/intake.ok -> allow
    check("contract_with_approval_allow",
          decide(g, "docs/development/card/contract.json", stages_obj=FULL_STAGES,
                 approvals=[("intake", "card")]) == "allow")

    # 4. plan without contract.json -> block (full-matrix fixture)
    check("plan_no_contract_block",
          decide(g, "openspec/changes/card/proposal.md", stages_obj=FULL_STAGES)
          == "block")

    # 5. plan with contract.json -> allow
    check("plan_with_contract_allow",
          decide(g, "openspec/changes/card/proposal.md", stages_obj=FULL_STAGES,
                 files={"docs/development/card/contract.json": "{}"}) == "allow")

    # 6. verify without openspec/changes/<slug>/tasks.md -> block
    check("verify_no_tasks_block",
          decide(g, "docs/development/card/verdict.json", stages_obj=FULL_STAGES)
          == "block")

    # 6b. verify with tasks.md -> allow
    check("verify_with_tasks_allow",
          decide(g, "docs/development/card/verdict.json", stages_obj=FULL_STAGES,
                 files={"openspec/changes/card/tasks.md": "# tasks"}) == "allow")

    # 7. delivery with verdict result=fail -> block
    check("delivery_verdict_fail_block",
          decide(g, "docs/development/card/pr-summary.md", stages_obj=FULL_STAGES,
                 files={"docs/development/card/verdict.json":
                        json.dumps({"result": "fail"})}) == "block")

    # 8. delivery with verdict result=pass -> allow
    check("delivery_verdict_pass_allow",
          decide(g, "docs/development/card/pr-summary.md", stages_obj=FULL_STAGES,
                 files={"docs/development/card/verdict.json":
                        json.dumps({"result": "pass"})}) == "allow")

    # 8b. delivery with missing/corrupt verdict.json -> block (not crash)
    check("delivery_missing_verdict_block",
          decide(g, "docs/development/card/pr-summary.md", stages_obj=FULL_STAGES)
          == "block")

    # 9. write to an early stage after later stages exist -> allow (fix-up upward)
    check("early_stage_fixup_allow",
          decide(g, "docs/development/card/intake.json", stages_obj=FULL_STAGES,
                 files={"docs/development/card/pr-summary.md": "done"}) == "allow")

    # 10. ungoverned path (journal / notes / source) -> allow
    check("journal_path_allow",
          decide(g, "docs/development/card/journal.md", stages_obj=FULL_STAGES)
          == "allow")
    check("source_path_allow",
          decide(g, "src/cards/CardService.kt", stages_obj=FULL_STAGES) == "allow")

    # 11. broken stages.json, path inside flow tree -> block (fail-closed)
    check("broken_stages_in_tree_block",
          decide(g, "docs/development/card/contract.json", stages_obj="{ not json")
          == "block")

    # 12. broken stages.json, path outside flow tree -> allow (must not brick)
    check("broken_stages_out_of_tree_allow",
          decide(g, "src/cards/CardService.kt", stages_obj="{ not json") == "allow")

    # 13. governed path without a resolvable slug -> block
    weird = {"version": 1, "stages": [
        {"id": "weird", "order": 0, "writes": ["docs/special/*"],
         "entry_requires": []}]}
    check("governed_no_slug_block",
          decide(g, "docs/special/file.md", stages_obj=weird) == "block")

    # 14. unknown predicate type -> block (fail-closed)
    bad = {"version": 1, "stages": [
        {"id": "delivery", "order": 0, "writes": ["docs/development/*/pr-summary.md"],
         "entry_requires": [{"type": "nope"}]}]}
    check("unknown_predicate_block",
          decide(g, "docs/development/card/pr-summary.md", stages_obj=bad) == "block")

    # 15. no path in event -> allow (nothing to govern)
    with root_at(make_root(stages_obj=FULL_STAGES)):
        check("no_path_allow", g.run({"hook_event_name": "PreToolUse",
                                      "tool_name": "Edit", "tool_input": {}})
              ["decision"] == "allow")


def test_live_stages_deferral():
    """Lock the v1 decision: the SHIPPED stages.json defers plan->contract and
    keeps the contract<-approval:intake human-stop."""
    with open(os.path.join(ROOT, ".gigacode", "stages.json"), encoding="utf-8") as h:
        data = json.load(h)
    by_id = {s["id"]: s for s in data["stages"]}
    check("live_plan_deferred", by_id["plan"]["entry_requires"] == [],
          by_id["plan"]["entry_requires"])
    check("live_contract_requires_intake_approval",
          {"type": "approval", "stage": "intake"} in by_id["contract"]["entry_requires"])
    check("live_delivery_requires_verdict_pass",
          any(p.get("type") == "verdict_pass"
              for p in by_id["delivery"]["entry_requires"]))
    # WI-11: verdict.json is machine-owned (agent writes blocked); the verify
    # stage no longer governs an agent-written artifact (gate_verdict produces it).
    g = load_gate("gate_stage_order")
    check("live_verdict_machine_owned",
          any("verdict.json" in glob for glob in data.get("machine_owned", [])),
          data.get("machine_owned"))
    check("live_verdict_agent_write_blocked",
          g.run({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                 "tool_input": {"file_path": "docs/development/x/verdict.json"}})["decision"]
          == "block")
    # WI-20: the live contract stage gates on intake completeness, and the
    # required-field map covers both task types.
    check("live_contract_requires_intake_complete",
          any(p.get("type") == "intake_complete"
              for p in by_id["contract"]["entry_requires"]))
    req = data.get("intake_required", {})
    check("live_intake_required_feature",
          isinstance(req.get("feature"), list) and req["feature"], req)
    check("live_intake_required_bug",
          isinstance(req.get("bug"), list) and req["bug"], req)


def test_confirm_is_agent_blocked():
    """DoD: the agent cannot run confirm.py — git_guard blocks any command that
    names a .gigacode path (P6, self-approval impossible)."""
    # The documented invocation uses forward slashes (`python .gigacode/hooks/
    # confirm.py ...`); that is the form Bash emits and the form the agent is
    # told to avoid. RESIDUAL: git_guard's shell tokenizer treats `\` as an
    # escape, so a backslash path (`.gigacode\hooks\confirm.py`) collapses to
    # `.gigacodehooksconfirm.py` and slips the self-protect regex. That is a
    # pre-existing git_guard tokenizer gap (broader than confirm.py), tracked
    # for WI-3 git_guard hardening — not introduced or owned by WI-22.
    gg = load_gate("git_guard")
    for cmd in ("python .gigacode/hooks/confirm.py intake card",
                "python ./.gigacode/hooks/confirm.py intake card",
                "py -3 .gigacode/hooks/confirm.py intake card"):
        ev_cmd = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                  "tool_input": {"command": cmd}}
        check("git_guard_blocks_confirm::" + cmd,
              gg.run(ev_cmd)["decision"] == "block", cmd)


def test_confirm_records_marker():
    """confirm.py (run by a human, no hooks) writes the approval marker that
    gate_stage_order then reads to unblock the contract stage."""
    tmp = make_root(stages_obj=FULL_STAGES)
    try:
        confirm = os.path.join(ROOT, ".gigacode", "hooks", "confirm.py")
        # confirm.py derives ROOT from its own location, so copy it into the
        # fixture tree to record the marker under the fixture's .gigacode.
        dest_hooks = os.path.join(tmp, ".gigacode", "hooks")
        os.makedirs(dest_hooks, exist_ok=True)
        shutil.copy(confirm, dest_hooks)
        rc = subprocess.run(
            [sys.executable, os.path.join(dest_hooks, "confirm.py"), "intake", "card"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        check("confirm_returns_zero", rc == 0, rc)
        marker = os.path.join(tmp, ".gigacode", "approvals", "card", "intake.ok")
        check("confirm_writes_marker", os.path.isfile(marker))
        # and the gate now allows the contract write
        g = load_gate("gate_stage_order")
        with root_at(tmp):
            check("contract_allowed_after_confirm",
                  g.run(ev("docs/development/card/contract.json"))["decision"]
                  == "allow")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    test_matrix()
    test_intake_complete()
    test_machine_owned()
    test_live_stages_deferral()
    test_confirm_is_agent_blocked()
    test_confirm_records_marker()
    print(f"\nAll {PASSED} stage_order checks passed")


if __name__ == "__main__":
    main()
