#!/usr/bin/env python3
"""projection.py: read-only human digest of the GigaCode flow.

A MANUAL CLI (not a hook): the router dispatches gates from router.config.json,
so a file living here is never auto-invoked. Run it in a second terminal to see
stage / stop-budget / recent gate decisions / declared scope while an agent works.

READ-ONLY CONTRACT: collect() and its readers never write a file and never call
_lib.changed_code_files / git_changed_paths / journal_skip (those append to
decisions.jsonl on git failure). Only pure _lib reads are used.

Usage:
    python .gigacode/hooks/projection.py            # one-shot snapshot
    python .gigacode/hooks/projection.py --follow    # tail mode
    python .gigacode/hooks/projection.py --tail 20    # last N decisions
    python .gigacode/hooks/projection.py --slug card  # narrow to one task
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gates"))
import _lib  # pure reads only (root, matches_globs) — see READ-ONLY CONTRACT

LOG_REL = (".gigacode", "logs", "decisions.jsonl")


def log_path():
    return os.path.join(_lib.root(), *LOG_REL)


def parse_line(line):
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def read_decisions(tail_n=8):
    """Last tail_n journal records, oldest-first; [] if the file is missing.
    Broken lines are skipped (fail-open)."""
    try:
        with open(log_path(), "r", encoding="utf-8") as handle:
            records = [obj for obj in (parse_line(ln) for ln in handle)
                       if obj is not None]
    except OSError:
        return []
    return records[-tail_n:] if tail_n else records


def latest_session(decisions):
    for obj in reversed(decisions):
        sid = obj.get("session_id")
        if sid:
            return sid
    return None
