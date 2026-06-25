#!/usr/bin/env python3
"""gate_scope_guard (PreToolUse): keep code writes inside the frozen contract scope.

WI-8/ADR-2. Once a contract.json is approved (scope frozen), a write to a CODE
file OUTSIDE its scope_globs is an overshoot: allowed only via `ask` (the human
confirms the expansion), and the router journals the ask so it surfaces in
verdict.overshoot_asks. Writes inside scope pass.

The guard engages ONLY while a flow is active — at least one active, approved
contract on disk; otherwise normal editing is untouched (no false blocks on a
repo where no GigaCode task is in progress). It governs PRODUCT CODE only
(_lib.CODE_SUFFIXES, outside openspec/ docs/ .gigacode/) — workflow/spec/
enforcement artifacts are gate_stage_order's and git_guard's job.

v1 collapses the RFC's 'foreign module -> block' into the overshoot `ask`: a
reliable path->module mapping is project-specific and deferred. .gigacode/.git
stay hard-blocked by git_guard.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

_EXCLUDED_PREFIXES = ("openspec/", "docs/", ".gigacode/")


def _norm(p):
    p = str(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def _is_product_code(path):
    return path.endswith(_lib.CODE_SUFFIXES) and not path.startswith(_EXCLUDED_PREFIXES)


def active_scope():
    """Union of scope_globs across active, APPROVED contracts.

    Returns (globs, active): active is True iff at least one frozen contract
    exists, which is what arms the guard."""
    base = os.path.join(_lib.root(), "docs", "development")
    approvals = os.path.join(_lib.root(), ".gigacode", "approvals")
    globs, active = [], False
    try:
        slugs = os.listdir(base)
    except OSError:
        return globs, active
    for slug in slugs:
        contract = os.path.join(base, slug, "contract.json")
        marker = os.path.join(approvals, slug, "contract.ok")
        if not (os.path.isfile(contract) and os.path.isfile(marker)):
            continue  # only a human-approved (frozen) contract arms the guard
        try:
            with open(contract, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("status") == "superseded":
            continue
        sg = data.get("scope_globs")
        if isinstance(sg, list):
            globs.extend(g for g in sg if isinstance(g, str))
            active = True
    return globs, active


def run(event):
    path = _norm(_lib.path_from_event(event))
    if not path or not _is_product_code(path):
        return {"decision": "allow"}
    globs, active = active_scope()
    if not active:
        return {"decision": "allow"}  # no frozen contract -> scope not enforced
    if _lib.matches_globs(path, globs):
        return {"decision": "allow"}
    return {"decision": "ask", "reason": (
        "overshoot: '%s' вне замороженного scope контракта (%s). Подтверди "
        "расширение явно или внеси путь в scope через re-approval контракта."
        % (path, ", ".join(globs) or "(scope пуст)"))}


def main():
    event = _lib.stdin_event()
    _lib.emit(run(event or {}))


if __name__ == "__main__":
    main()
