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
one definition of "stage" and cannot drift.

TWO layers:
- PreToolUse (file-tool writes): early, per-write block — fast feedback.
- Stop (`_stop_invariant`): channel-INDEPENDENT. Derives truth from the working
  tree, so a write through ANY channel (notably a shell `echo > artifact`, which
  the PreToolUse path never sees) cannot COMPLETE the flow out of order. A present
  stage artifact with unmet entry_requires, or changed source without a complete
  approved contract covering it, blocks Stop. This closes the former shell-channel
  residual AND the WI-8 source-ordering deferral. (PreToolUse alone was bypassable
  via shell — found live on petclinic, 2026-06-25.)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib
import _stage

ESCAPE = ('If stages.json itself is broken, set "disableAllHooks": true in '
          ".gigacode/settings.json temporarily and report the issue.")


def _active_slugs():
    """Slugs with an uncommitted change under docs/development/<slug>/ or
    openspec/changes/<slug>/ — the CURRENT task(s). Scoping to changed paths
    avoids false-blocking on stale, already-completed task dirs."""
    slugs = set()
    for p in _lib.git_changed_paths():
        norm = p.replace("\\", "/")
        for rx in (_stage.DEV_SLUG_RE, _stage.OSX_SLUG_RE):
            m = rx.search(norm)
            if m:
                slugs.add(m.group(1))
    return slugs


def _concrete(glob, slug):
    """Resolve a writes-glob to a slug-concrete relative path (the '*' segment is
    the slug)."""
    return (glob.replace("docs/development/*/", "docs/development/%s/" % slug)
                .replace("openspec/changes/*/", "openspec/changes/%s/" % slug))


def _approved_contract_scope(slug, cfg):
    """(scope_globs, approved): the contract's scope if it is COMPLETE and
    human-approved (approval:contract), else ([], False)."""
    try:
        complete, _ = _stage.predicate_holds({"type": "contract_complete"}, slug, cfg)
    except ValueError:
        complete = False
    marker = os.path.join(_stage.approvals_dir(), slug, "contract.ok")
    if not (complete and os.path.isfile(marker)):
        return [], False
    try:
        with open(_stage.artifact_path("docs/development/<slug>/contract.json", slug),
                  "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return [], False
    sg = data.get("scope_globs")
    return ([g for g in sg if isinstance(g, str)] if isinstance(sg, list) else []), True


def _stop_invariant():
    """Channel-INDEPENDENT enforcement at Stop: derive the flow's truth from the
    working tree, not from a tool call. Closes the gap that gate_stage_order's
    PreToolUse path only sees file-tool writes — a shell write (echo > artifact)
    slips past it. Here a present stage artifact whose entry_requires are unmet,
    or changed source code without an approved contract covering it, blocks Stop —
    so the flow cannot be COMPLETED out of order regardless of write channel."""
    active = _active_slugs()
    try:
        doc = _stage.load_doc()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return ({"decision": "block",
                 "reason": "stages.json unreadable at Stop: %s. %s" % (exc, ESCAPE)}
                if active else {"decision": "allow"})
    stages = doc["stages"]
    cfg = _stage.cfg_from_doc(doc)
    root = _lib.root()
    bad = []
    for slug in sorted(active):
        for st in stages:
            present = any(
                os.path.isfile(os.path.join(root, *_concrete(g, slug).split("/")))
                for g in st.get("writes", []))
            if not present:
                continue
            try:
                for pred in st.get("entry_requires", []):
                    ok, label = _stage.predicate_holds(pred, slug, cfg)
                    if not ok:
                        bad.append("артефакт стадии '%s' (%s) есть, но НЕ выполнено %s"
                                   % (st.get("id"), slug, label))
            except ValueError as exc:
                bad.append("предикат стадии '%s' сломан: %s" % (st.get("id"), exc))
    # Source-ordering (closes the WI-8 deferral): changed product code requires a
    # complete, approved contract whose scope covers it.
    changed = _lib.changed_code_files()
    if changed:
        union, approved = [], False
        for slug in active:
            sg, ok = _approved_contract_scope(slug, cfg)
            if ok:
                union.extend(sg)
                approved = True
        if not approved:
            bad.append("изменён код (%d файлов), но нет полного одобренного "
                       "contract.json — заморозь scope и подтверди "
                       "(python .gigacode/hooks/confirm.py contract <slug>)" % len(changed))
        else:
            oos = [p for p in changed if not _lib.matches_globs(p, union)]
            if oos:
                bad.append("код вне scope контракта: " + ", ".join(oos[:4]))
    if bad:
        return {"decision": "block", "reason": (
            "Stop: порядок флоу нарушен (возможна запись мимо стопов, напр. через "
            "shell): " + " | ".join(bad[:4]) + ". Приведи стадии/одобрения в "
            "порядок или удали преждевременные артефакты. " + ESCAPE)}
    return {"decision": "allow"}


def run(event):
    if event.get("hook_event_name") == "Stop":
        return _stop_invariant()
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
