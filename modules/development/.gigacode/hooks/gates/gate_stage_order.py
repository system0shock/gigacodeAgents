#!/usr/bin/env python3
"""gate_stage_order: enforce workflow-stage ordering and explicit stops.

A write to a stage's owned artifact is allowed only when that stage's
entry_requires all hold. Confirmations are READ from artifacts/approval
markers (the source of truth) — not from a mutable manifest status field,
so there is no second state to desync. PreToolUse + fail-closed: the agent
cannot 'ask to validate and run ahead' because the next-stage write blocks
until its confirmation exists. Not under stop_block_budget (PreToolUse, not Stop).

Self-contained except _lib and _stage. The stage resolver (slug, stages.json,
predicates) lives in _stage so the projection read-model and this enforcer share
one definition of "stage" and cannot drift. Governs file-tool writes to the
workflow tree only; shell-channel writes are covered by git_guard (path
protection) — stage-order on shell is a documented residual. Source-code writes
are governed by gate_scope_guard.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
import _stage

ESCAPE = ('If stages.json itself is broken, set "disableAllHooks": true in '
          ".gigacode/settings.json temporarily and report the issue.")


def run(event):
    path = _stage.norm(_lib.path_from_event(event))
    if not path:
        return {"decision": "allow"}
    in_flow_tree = _stage.in_flow_tree(path)
    try:
        doc = _stage.load_doc()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        # fail-closed ONLY if the write targets the workflow tree; otherwise a
        # missing stages.json must not brick unrelated edits.
        if in_flow_tree:
            return {"decision": "block",
                    "reason": "stages.json unreadable: %s. %s" % (exc, ESCAPE)}
        return {"decision": "allow"}
    # Machine-owned artifacts (e.g. verdict.json) are produced by a gate in the
    # router process, never by the agent — a verdict the agent could write would
    # let it self-grant `result: pass` and make the delivery stop theater (P6).
    machine_owned = doc.get("machine_owned", [])
    if machine_owned and _lib.matches_globs(path, machine_owned):
        return {"decision": "block", "reason": (
            "'%s' — машинно-производимый артефакт (его пишет gate_verdict в "
            "процессе роутера из реальных тестов). Агент его не пишет: result "
            "нельзя проставить вручную. %s" % (path, ESCAPE))}
    # Frozen-after-approval (WI-8/P6): once a stage artifact has been approved
    # (its scope confirmed), the agent cannot edit it — an amend must go through
    # a fresh human re-approval. Otherwise the agent could widen contract.scope
    # after approval and walk gate_scope_guard's frozen scope right open.
    for rule in doc.get("frozen_after", []):
        glob = rule.get("glob", "")
        if glob and _lib.matches_globs(path, [glob]):
            fslug = _stage.slug_from_path(path)
            marker = os.path.join(_stage.approvals_dir(), fslug, rule.get("approval", "") + ".ok")
            if fslug and os.path.isfile(marker):
                return {"decision": "block", "reason": (
                    "'%s' заморожен после подтверждения (approval:%s). Правка = "
                    "amend: нужно повторное подтверждение человеком (удалить "
                    "approvals/%s/%s.ok и пере-подтвердить). %s"
                    % (path, rule.get("approval"), fslug, rule.get("approval"), ESCAPE))}
    stages = doc["stages"]
    cfg = _stage.cfg_from_doc(doc)
    st = _stage.target_stage(path, stages)
    if not st:
        return {"decision": "allow"}  # not a governed artifact (journal, notes, src)
    slug = _stage.slug_from_path(path)
    if not slug:
        return {"decision": "block", "reason": (
            "Stage-governed write '%s' without a resolvable task slug. %s"
            % (path, ESCAPE))}
    unmet = []
    try:
        for pred in st.get("entry_requires", []):
            ok, label = _stage.predicate_holds(pred, slug, cfg)
            if not ok:
                unmet.append(label)
    except ValueError as exc:
        return {"decision": "block",
                "reason": "stage predicate error: %s. %s" % (exc, ESCAPE)}
    if unmet:
        return {"decision": "block", "reason": (
            "Стадия '%s' для '%s' ещё не разблокирована: не выполнено %s. "
            "Это явная остановка — заверши/подтверди предыдущую стадию. "
            "Подтверждение человеком (вне сессии агента): "
            "python .gigacode/hooks/confirm.py <stage> %s"
            % (st.get("id"), slug, ", ".join(unmet), slug))}
    return {"decision": "allow"}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
