#!/usr/bin/env python3
"""observer.py: read-only web view of the GigaCode flow (SSE).

A MANUAL CLI (not a hook): not registered in router.config.json/settings.json.
Run it in a second terminal; open http://127.0.0.1:<port> in a browser.

READ-ONLY CONTRACT (inherited from projection.py): never writes a file, never
calls _lib.changed_code_files / git_changed_paths / journal_skip. A third reader
over projection.py's pure functions. Wall-clock (datetime.now) is read, not a write.

Usage:
    python .gigacode/hooks/observer.py [--port 8787] [--slug card]
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gates"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projection  # WI-13: collect / read_decisions / read_from_offset / _read_json

CONTRACT = "wi15/1"


def read_intake(slug):
    if not slug:
        return None
    data = projection._read_json(("docs", "development", slug, "intake.json"))
    if not isinstance(data, dict):
        return None
    return {"task_type": data.get("task_type"),
            "scope_intent": data.get("scope_intent"),
            "acceptance": data.get("acceptance", []),
            "constraints": data.get("constraints", []),
            "understanding": data.get("understanding")}


def read_verdict(slug):
    if not slug:
        return None
    data = projection._read_json(("docs", "development", slug, "verdict.json"))
    if not isinstance(data, dict):
        return None
    return {"result": data.get("result"), "risk": data.get("risk", {}),
            "findings": data.get("findings", [])}


def parse_ts(s):
    if not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except (ValueError, TypeError):
        return None


def vitals(decisions, now):
    total = len(decisions)
    counts = {"block": 0, "ask": 0, "allow": 0}
    tools = {}
    times = []
    for d in decisions:
        dec = d.get("decision")
        if dec in counts:
            counts[dec] += 1
        tool = d.get("tool")
        if tool and tool != "-":
            tools[tool] = tools.get(tool, 0) + 1
        ts = parse_ts(d.get("ts"))
        if ts:
            times.append(ts)
    session_sec = int((max(times) - min(times)).total_seconds()) if len(times) >= 2 else 0
    idle_sec = int((now - max(times)).total_seconds()) if times else None
    per_min = round(total / (session_sec / 60.0), 1) if session_sec > 0 else float(total)
    return {"total": total, "block": counts["block"], "ask": counts["ask"],
            "allow": counts["allow"], "per_min": per_min, "idle_sec": idle_sec,
            "session_sec": session_sec, "tools": tools}


def blocker(snapshot, decisions):
    """Active blocker derived from stage_status unmet predicates (mechanical).
    An 'approval:<stage>' unmet yields the exact confirm.py command."""
    slug = snapshot.get("slug")
    stage = snapshot.get("stage") or {}
    unmet_all = []
    for st in stage.get("stages", []):
        if not st.get("enterable", True):
            unmet_all.extend(st.get("unmet", []))
    if not unmet_all:
        return None
    unmet = unmet_all[0]
    command = None
    if unmet.startswith("approval:") and slug:
        command = "python .gigacode/hooks/confirm.py %s %s" % (unmet.split(":", 1)[1], slug)
    last_block = next((d for d in reversed(decisions) if d.get("decision") == "block"), None)
    return {"active": True, "stage": stage.get("current"), "unmet": unmet,
            "command": command, "reason": last_block.get("reason") if last_block else None}


def enrich(snapshot, decisions, now):
    slug = snapshot.get("slug")
    out = dict(snapshot)
    out["_contract"] = CONTRACT
    out["intake"] = read_intake(slug)
    out["verdict"] = read_verdict(slug)
    out["blocker"] = blocker(snapshot, decisions)
    out["vitals"] = vitals(decisions, now)
    return out
