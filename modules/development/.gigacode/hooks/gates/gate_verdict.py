#!/usr/bin/env python3
"""gate_verdict (Stop): the MECHANICAL producer of docs/development/<slug>/verdict.json.

WI-11/ADR-3. verdict.json gates the delivery stage (gate_stage_order's
`verdict_pass` predicate reads result == "pass"), so its result must NOT be the
agent's self-report (P4): it is set from the REAL exit code of the configured
test command. The agent cannot write verdict.json itself — it is machine-owned
(gate_stage_order blocks agent file-tool writes to it, P6) and produced here, in
the router process, so there is no tool call for the agent to fake.

Runs at Stop, like gate_build: for each task dir with an uncommitted change and an
existing openspec change (tasks.md = we are at/after verify), it runs the test
command and writes the verdict. Returns allow — it produces, it does not block;
the delivery verdict_pass predicate does the gating. With no test command or no
active task it is a silent no-op (writes nothing).

risk fields are mechanical (from diff/journal). Some depend on not-yet-built
pieces and carry a documented v1 default: out_of_contract_files=null (WI-7
contract.json), overshoot_asks counts gate_scope_guard asks in the journal (0
until WI-8 produces them).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

VERDICT_TIMEOUT_CEILING = 620  # below the 630s Stop hook timeout (as gate_build)


def _active_slugs():
    """Task slugs with an uncommitted change under docs/development/<slug>/."""
    slugs, seen = [], set()
    base = os.path.join(_lib.root(), "docs", "development")
    for p in _lib.git_changed_paths():
        norm = p.replace("\\", "/")
        if norm.startswith("docs/development/"):
            slug = norm[len("docs/development/"):].split("/", 1)[0]
            if slug and slug not in seen and os.path.isdir(os.path.join(base, slug)):
                seen.add(slug)
                slugs.append(slug)
    return slugs


def _infer_modules(paths):
    """Distinct top-level modules touched: src/<m>/.. or modules/<m>/.. ."""
    mods = set()
    for p in paths:
        parts = p.replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[0] in ("src", "modules"):
            mods.add(parts[1])
    return mods


def _open_questions(slug):
    """Unresolved intake inputs (mechanical): length of intake.json missing_inputs.
    Empty required fields are already enforced before contract (intake_complete),
    so by verify the remaining signal is the explicitly-listed open inputs."""
    path = os.path.join(_lib.root(), "docs", "development", slug, "intake.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return 0
    missing = data.get("missing_inputs")
    return len(missing) if isinstance(missing, list) else 0


def _budget_left(event):
    """Remaining Stop budget for this session (from router-state.json)."""
    state_path = os.path.join(_lib.root(), ".gigacode", "logs", "router-state.json")
    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError):
        state = {}
    budget = 2  # router default stop_block_budget
    key = "stop:" + str(event.get("session_id", "default"))
    count = state.get(key, 0) if isinstance(state, dict) else 0
    count = count if isinstance(count, int) and count >= 0 else 0
    return max(0, budget - count)


def _overshoot_asks():
    """Count gate_scope_guard `ask` decisions in the journal (WI-8 signal).
    Yields 0 until gate_scope_guard exists — the count is real once it does."""
    path = os.path.join(_lib.root(), ".gigacode", "logs", "decisions.jsonl")
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (rec.get("kind") == "gate"
                        and rec.get("gate") == "gate_scope_guard"
                        and rec.get("decision") == "ask"):
                    count += 1
    except OSError:
        return 0
    return count


def compute_risk(slug, event):
    changed = _lib.changed_code_files()
    return {
        "scope_diff_files": len(changed),
        "modules_touched": len(_infer_modules(changed)),
        "open_questions": _open_questions(slug),
        "iteration_budget_left": _budget_left(event),
        "out_of_contract_files": None,   # WI-7: needs contract.json scope_globs
        "overshoot_asks": _overshoot_asks(),  # WI-8: gate_scope_guard asks (0 until then)
    }


def _write_verdict(slug, verdict):
    out = os.path.join(_lib.root(), "docs", "development", slug, "verdict.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(verdict, handle, ensure_ascii=False, indent=2)


def produce_for(slug, test_cmd, timeout, event):
    """Run the test command and write the verdict for one slug. Returns the verdict."""
    rc, tail = _lib.run_command(test_cmd, timeout)
    if rc == 0:
        result, findings = "pass", []
    elif rc == -1:
        result, findings = "fail", ["test command could not run: %s" % tail]
    elif rc == -2:
        result, findings = "fail", ["test command timed out after %ss" % timeout]
    else:
        result, findings = "fail", ["test command failed (exit %s):\n%s" % (rc, tail)]
    verdict = {"stage": "verify", "result": result,
               "risk": compute_risk(slug, event), "findings": findings}
    _write_verdict(slug, verdict)
    return verdict


def run(event):
    if event.get("hook_event_name") != "Stop":
        return {"decision": "allow"}
    qg = _lib.load_quality_gates()
    test_cfg = qg.get("test") if isinstance(qg.get("test"), dict) else {}
    test_cmd = (test_cfg.get("command") or "").strip()
    if not test_cmd:
        return {"decision": "allow"}  # no mechanical pass signal: no verdict (WI-1 wires it)
    timeout = test_cfg.get("timeout_seconds", 600)
    timeout = max(1, timeout) if isinstance(timeout, (int, float)) else 600
    timeout = min(int(timeout), VERDICT_TIMEOUT_CEILING)
    for slug in _active_slugs():
        # produce a verdict only once an openspec change exists (at/after verify)
        tasks = os.path.join(_lib.root(), "openspec", "changes", slug, "tasks.md")
        if os.path.isfile(tasks):
            produce_for(slug, test_cmd, timeout, event)
    return {"decision": "allow"}


def main():
    event = _lib.stdin_event()
    if event is None:
        _lib.emit({"decision": "allow"})
        return
    _lib.emit(run(event))


if __name__ == "__main__":
    main()
