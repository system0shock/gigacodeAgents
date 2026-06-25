#!/usr/bin/env python3
"""gate_stage_order: enforce workflow-stage ordering and explicit stops.

A write to a stage's owned artifact is allowed only when that stage's
entry_requires all hold. Confirmations are READ from artifacts/approval
markers (the source of truth) — not from a mutable manifest status field,
so there is no second state to desync. PreToolUse + fail-closed: the agent
cannot 'ask to validate and run ahead' because the next-stage write blocks
until its confirmation exists. Not under stop_block_budget (PreToolUse, not Stop).

Self-contained except _lib. Governs file-tool writes to the workflow tree only;
shell-channel writes are covered by git_guard (path protection) — stage-order on
shell is a documented residual. Source-code writes are governed by gate_scope_guard.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

ESCAPE = ('If stages.json itself is broken, set "disableAllHooks": true in '
          ".gigacode/settings.json temporarily and report the issue.")

DEV_SLUG_RE = re.compile(r"(?:^|/)docs/development/([^/]+)/", re.IGNORECASE)
OSX_SLUG_RE = re.compile(r"(?:^|/)openspec/changes/([^/]+)/", re.IGNORECASE)


def _stages_path():
    return os.path.join(_lib.root(), ".gigacode", "stages.json")


def _approvals_dir():
    return os.path.join(_lib.root(), ".gigacode", "approvals")


def _norm(p):
    p = str(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def load_doc():
    with open(_stages_path(), "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("stages"), list):
        raise ValueError("stages.json: 'stages' must be a list")
    return data


def load_stages():
    return load_doc()["stages"]


def _intake_empty(value):
    """A required intake field counts as MISSING when it is null, a blank/
    whitespace-only string, or an empty list/dict. Numbers/bools count as set."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple)):
        return len(value) == 0
    return False


def slug_from_path(path):
    for rx in (DEV_SLUG_RE, OSX_SLUG_RE):
        m = rx.search(path)
        if m:
            return m.group(1)
    return ""


def target_stage(path, stages):
    """First stage whose writes-glob matches the path; None if ungoverned."""
    for st in stages:
        for glob in st.get("writes", []):
            if _lib.matches_globs(path, [glob]):
                return st
    return None


def _artifact_path(rel, slug):
    rel = rel.replace("<slug>", slug)
    return os.path.join(_lib.root(), *rel.split("/"))


def predicate_holds(pred, slug, intake_required):
    """Return (ok, label). Unknown type raises -> caller fails closed."""
    ptype = pred.get("type")
    if ptype == "approval":
        stage = pred.get("stage", "")
        marker = os.path.join(_approvals_dir(), slug, stage + ".ok")
        return os.path.isfile(marker), "approval:" + stage
    if ptype == "file_exists":
        target = _artifact_path(pred.get("artifact", ""), slug)
        return os.path.isfile(target), "file_exists:" + pred.get("artifact", "")
    if ptype == "verdict_pass":
        target = _artifact_path(pred.get("artifact", ""), slug)
        try:
            with open(target, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False, "verdict:pass"
        return data.get("result") == "pass", "verdict:pass"
    if ptype == "intake_complete":
        # WI-20/ADR-7: the questions are DERIVED from the empty required fields of
        # intake.json (per task_type), not from prompt keyword-sniffing. An absent/
        # unreadable intake, an unknown task_type, or any empty required field
        # blocks the intake->contract transition and names exactly what to fill.
        target = _artifact_path("docs/development/<slug>/intake.json", slug)
        try:
            with open(target, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False, "intake.json отсутствует или не читается — заполни его"
        ttype = data.get("task_type")
        required = intake_required.get(ttype) if isinstance(ttype, str) else None
        if required is None:
            return False, ("intake.json: task_type должен быть одним из %s"
                           % ", ".join(sorted(intake_required)) or "(не задано)")
        missing = [field for field in required if _intake_empty(data.get(field))]
        if missing:
            return False, "заполни required-поля intake.json: " + ", ".join(missing)
        return True, "intake_complete"
    raise ValueError("unknown predicate type: " + repr(ptype))


def run(event):
    path = _norm(_lib.path_from_event(event))
    if not path:
        return {"decision": "allow"}
    in_flow_tree = bool(DEV_SLUG_RE.search(path) or OSX_SLUG_RE.search(path))
    try:
        doc = load_doc()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        # fail-closed ONLY if the write targets the workflow tree; otherwise a
        # missing stages.json must not brick unrelated edits.
        if in_flow_tree:
            return {"decision": "block",
                    "reason": "stages.json unreadable: %s. %s" % (exc, ESCAPE)}
        return {"decision": "allow"}
    stages = doc["stages"]
    intake_required = doc.get("intake_required", {})
    st = target_stage(path, stages)
    if not st:
        return {"decision": "allow"}  # not a governed artifact (journal, notes, src)
    slug = slug_from_path(path)
    if not slug:
        return {"decision": "block", "reason": (
            "Stage-governed write '%s' without a resolvable task slug. %s"
            % (path, ESCAPE))}
    unmet = []
    try:
        for pred in st.get("entry_requires", []):
            ok, label = predicate_holds(pred, slug, intake_required)
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
