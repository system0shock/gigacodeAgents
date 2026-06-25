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
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gates"))
import _lib  # pure reads only (root, matches_globs) — see READ-ONLY CONTRACT
import _stage  # shared stage resolver (gate + projection share one definition)

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


STATE_REL = (".gigacode", "logs", "router-state.json")
CONFIG_REL = (".gigacode", "hooks", "router.config.json")
DEV_REL = ("docs", "development")


def _read_json(parts):
    """Read a stdlib-JSON file under root(); None on absence/parse error."""
    try:
        with open(os.path.join(_lib.root(), *parts), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def resolve_slug(explicit):
    if explicit:
        return explicit, [explicit]
    base = os.path.join(_lib.root(), *DEV_REL)
    try:
        entries = [(name, os.path.getmtime(os.path.join(base, name)))
                   for name in os.listdir(base)
                   if os.path.isdir(os.path.join(base, name))]
    except OSError:
        return None, []
    entries.sort(key=lambda pair: pair[1], reverse=True)
    slugs = [name for name, _ in entries]
    return (slugs[0] if slugs else None), slugs


def read_budget(session):
    config = _read_json(CONFIG_REL) or {}
    limit = config.get("stop_block_budget")
    used = None
    state = _read_json(STATE_REL)
    if isinstance(state, dict) and session:
        raw = state.get("stop:" + session)
        used = raw if isinstance(raw, int) else None
    return {"used": used, "limit": limit if isinstance(limit, int) else None}


def read_scope(slug):
    if not slug:
        return None
    data = _read_json(("docs", "development", slug, "contract.json"))
    if not isinstance(data, dict):
        return None
    return {"scope_globs": data.get("scope_globs", []),
            "modules": data.get("modules", [])}


def read_stage(slug):
    empty = {"current": None, "stages": []}
    if not slug:
        return empty
    try:
        doc = _stage.load_doc()
    except (OSError, json.JSONDecodeError, ValueError):
        return empty
    status = _stage.stage_status(slug, doc)
    return {"current": _stage.current_stage(status), "stages": status}


def collect(slug=None, tail_n=8):
    decisions = read_decisions(tail_n)
    session = latest_session(read_decisions(0))  # scan whole log for session id
    resolved, candidates = resolve_slug(slug)
    return {
        "session": session,
        "slug": resolved,
        "slug_candidates": candidates,
        "stage": read_stage(resolved),
        "budget": read_budget(session),
        "decisions": decisions,
        "scope": read_scope(resolved),
    }


_ANSI = {"block": "\x1b[31m", "ask": "\x1b[33m", "allow": "\x1b[32m"}
_RESET = "\x1b[0m"


def _color(text, decision, enable):
    code = _ANSI.get(decision)
    return (code + text + _RESET) if (enable and code) else text


def _short_ts(ts):
    # "2026-06-25T14:03:01+0300" -> "14:03:01"; fall back to the raw value.
    if isinstance(ts, str) and "T" in ts:
        tail = ts.split("T", 1)[1]
        return tail[:8]
    return ts or "--:--:--"


def render_decision(obj, color=False):
    """Format a single journal record as a one- or two-line string.

    First line: timestamp, decision, gate/kind, tool (colour-coded).
    Second line (only if obj has a 'reason'): indented arrow + reason text.
    Lines are joined with a newline so callers can append to a list directly.
    """
    decision = obj.get("decision", "?")
    head = "  %s  %-5s  %-18s %s" % (
        _short_ts(obj.get("ts")), decision,
        obj.get("gate") or obj.get("kind") or "-", obj.get("tool") or "")
    line = _color(head, decision, color)
    reason = obj.get("reason")
    if reason:
        line = line + "\n" + "            → %s" % reason
    return line


def render_snapshot(snap, color=False):
    lines = []
    lines.append("GigaCode flow · session %s" % (snap.get("session") or "—"))
    lines.append("")

    stage = snap.get("stage") or {}
    current = stage.get("current") or "—"
    marks = []
    for st in stage.get("stages", []):
        for label in st.get("met", []):
            marks.append("✓ " + label)
        for label in st.get("unmet", []):
            marks.append("☐ " + label)
    lines.append("stage    : %s   %s" % (current, "  ".join(marks)))

    budget = snap.get("budget") or {}
    used, limit = budget.get("used"), budget.get("limit")
    if used is None and limit is None:
        lines.append("budget   : нет данных")
    else:
        lines.append("budget   : stop %s/%s used" % (
            used if used is not None else "?", limit if limit is not None else "?"))

    scope = snap.get("scope")
    if scope:
        globs = ", ".join(scope.get("scope_globs", [])) or "—"
        lines.append("scope    : %s  (%s)" % (
            ", ".join(scope.get("modules", [])) or "—", globs))
    else:
        lines.append("scope    : нет contract.json")

    candidates = snap.get("slug_candidates") or []
    if len(candidates) > 1:
        lines.append("note     : несколько активных задач (%s) — сузь через --slug"
                     % ", ".join(candidates))

    decisions = snap.get("decisions") or []
    lines.append("")
    lines.append("recent decisions (last %d)" % len(decisions))
    for obj in decisions:
        lines.append(render_decision(obj, color))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Incremental tail reader
# ---------------------------------------------------------------------------

def read_from_offset(path, offset):
    """Return (new_records, new_offset) reading from byte *offset*.

    Truncation/rotation: if the file is now smaller than offset, re-read from 0.
    Missing file: return ([], offset).  Never writes.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], offset
    if size < offset:
        offset = 0  # truncation/rotation detected
    records = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            handle.seek(offset)
            for line in handle:
                obj = parse_line(line)
                if obj is not None:
                    records.append(obj)
            new_offset = handle.tell()
    except OSError:
        return [], offset
    return records, new_offset


# ---------------------------------------------------------------------------
# Follow / tail loop
# ---------------------------------------------------------------------------

def follow(slug=None, tail_n=8, interval=1.0, _max_polls=None):
    """Print a full snapshot, then stream new decision lines as they arrive.

    _max_polls=None runs forever (interactive); pass a small int for tests.
    """
    print(render_snapshot(collect(slug, tail_n), color=sys.stdout.isatty()))
    print("\n— follow (Ctrl-C to stop) —")
    path = log_path()
    try:
        offset = os.path.getsize(path)
    except OSError:
        offset = 0
    polls = 0
    while _max_polls is None or polls < _max_polls:
        records, offset = read_from_offset(path, offset)
        for obj in records:
            print(render_decision(obj, color=sys.stdout.isatty()))
        time.sleep(interval)
        polls += 1


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main(argv=None):
    """Parse CLI args and run one-shot snapshot or follow mode."""
    parser = argparse.ArgumentParser(description="Read-only GigaCode flow digest.")
    parser.add_argument("--follow", action="store_true", help="tail the journal")
    parser.add_argument("--tail", type=int, default=8,
                        help="number of recent decisions to show (default 8)")
    parser.add_argument("--slug", default=None,
                        help="narrow output to one task slug")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.follow:
        try:
            follow(args.slug, args.tail)
        except KeyboardInterrupt:
            pass
        return 0
    print(render_snapshot(collect(args.slug, args.tail),
                          color=sys.stdout.isatty()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
