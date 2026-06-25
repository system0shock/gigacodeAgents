#!/usr/bin/env python3
"""Shared stage-resolution helpers.

Single source of truth for "what stage is this slug in, and which entry
predicates hold" — imported by BOTH gate_stage_order (the enforcer) and the
read-only projection (tools/projection.py). Keeping the resolver here is what
stops the gate's idea of "stage" and the projection's idea of "stage" from
drifting apart (the WI-13 open question).

Self-contained except _lib (same gates/ dir). Reads stages.json + artifacts +
approval markers; never writes. predicate_holds raises ValueError on an unknown
predicate type so the enforcer can fail closed; the projection catches it.
"""
import json
import os
import re

import _lib

DEV_SLUG_RE = re.compile(r"(?:^|/)docs/development/([^/]+)/", re.IGNORECASE)
OSX_SLUG_RE = re.compile(r"(?:^|/)openspec/changes/([^/]+)/", re.IGNORECASE)


def stages_path():
    return os.path.join(_lib.root(), ".gigacode", "stages.json")


def approvals_dir():
    return os.path.join(_lib.root(), ".gigacode", "approvals")


def norm(p):
    p = str(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def load_doc():
    """Parse stages.json. Raises OSError/JSONDecodeError/ValueError on trouble —
    callers decide whether that is fail-closed (gate) or 'no data' (projection)."""
    with open(stages_path(), "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("stages"), list):
        raise ValueError("stages.json: 'stages' must be a list")
    return data


def load_stages():
    return load_doc()["stages"]


def cfg_from_doc(doc):
    """The declarative required-field maps predicate_holds needs."""
    return {"intake_required": doc.get("intake_required", {}),
            "contract_required": doc.get("contract_required", [])}


def _intake_empty(value):
    """A required field counts as MISSING when it is null, a blank/whitespace
    string, or an empty list/dict. Numbers/bools count as set."""
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


def in_flow_tree(path):
    return bool(DEV_SLUG_RE.search(path) or OSX_SLUG_RE.search(path))


def target_stage(path, stages):
    """First stage whose writes-glob matches the path; None if ungoverned."""
    for st in stages:
        for glob in st.get("writes", []):
            if _lib.matches_globs(path, [glob]):
                return st
    return None


def artifact_path(rel, slug):
    rel = rel.replace("<slug>", slug)
    return os.path.join(_lib.root(), *rel.split("/"))


def predicate_holds(pred, slug, cfg):
    """Return (ok, label). Unknown type raises -> caller fails closed.

    cfg carries the declarative required-field maps from stages.json
    (intake_required per task_type, contract_required flat list)."""
    intake_required = cfg.get("intake_required", {})
    ptype = pred.get("type")
    if ptype == "approval":
        stage = pred.get("stage", "")
        marker = os.path.join(approvals_dir(), slug, stage + ".ok")
        return os.path.isfile(marker), "approval:" + stage
    if ptype == "file_exists":
        target = artifact_path(pred.get("artifact", ""), slug)
        return os.path.isfile(target), "file_exists:" + pred.get("artifact", "")
    if ptype == "verdict_pass":
        target = artifact_path(pred.get("artifact", ""), slug)
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
        target = artifact_path("docs/development/<slug>/intake.json", slug)
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
    if ptype == "contract_complete":
        # WI-7/ADR-2: the scope freeze must be substantive before plan. Absent/
        # unreadable contract or an empty required field (scope_globs/modules)
        # blocks plan and names what to fill. The human then confirms the scope
        # (approval:contract) — the second checkpoint, after understanding.
        target = artifact_path("docs/development/<slug>/contract.json", slug)
        try:
            with open(target, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False, "contract.json отсутствует или не читается — заморозь scope"
        contract_required = cfg.get("contract_required", [])
        missing = [field for field in contract_required if _intake_empty(data.get(field))]
        if missing:
            return False, "заполни поля contract.json: " + ", ".join(missing)
        return True, "contract_complete"
    raise ValueError("unknown predicate type: " + repr(ptype))


def stage_status(slug, doc):
    """Read-model view of a slug's position in the flow.

    Returns an ordered list of per-stage dicts:
        {id, order, enterable, met:[labels], unmet:[labels]}
    `enterable` is True when every entry_requires predicate holds. The projection
    derives the 'current' stage as the highest-order enterable stage; earlier
    enterable stages are 'done', later ones are 'locked'. An unknown predicate
    type makes that stage not enterable (the projection never raises)."""
    cfg = cfg_from_doc(doc)
    stages = sorted(doc.get("stages", []), key=lambda s: s.get("order", 0))
    out = []
    for st in stages:
        met, unmet = [], []
        for pred in st.get("entry_requires", []):
            try:
                ok, label = predicate_holds(pred, slug, cfg)
            except ValueError as exc:
                ok, label = False, "predicate error: %s" % exc
            (met if ok else unmet).append(label)
        out.append({"id": st.get("id"), "order": st.get("order", 0),
                    "enterable": not unmet, "met": met, "unmet": unmet})
    return out


def current_stage(status):
    """Highest-order enterable stage id from a stage_status() list, or None."""
    enterable = [s for s in status if s["enterable"]]
    if not enterable:
        return None
    return max(enterable, key=lambda s: s["order"])["id"]
