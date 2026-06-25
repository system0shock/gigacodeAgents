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
import argparse
import json
import os
import queue
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


def _empty_snapshot(slug):
    return {"_contract": CONTRACT, "session": None, "slug": slug, "slug_candidates": [],
            "stage": {"current": None, "stages": []},
            "budget": {"used": None, "limit": None}, "scope": None, "decisions": [],
            "intake": None, "verdict": None, "blocker": None,
            "vitals": {"total": 0, "block": 0, "ask": 0, "allow": 0, "per_min": 0,
                       "idle_sec": None, "session_sec": 0, "tools": {}}}


def build_snapshot(slug=None, tail_n=12, now=None):
    if now is None:
        now = datetime.now().astimezone()
    try:
        snapshot = projection.collect(slug, tail_n)
        decisions = projection.read_decisions(0)   # full journal for vitals/blocker
        return enrich(snapshot, decisions, now)
    except Exception:
        return _empty_snapshot(slug)


def format_sse(event, data):
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(data, ensure_ascii=False))


HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "observer.html")


class Observer:
    def __init__(self, slug=None):
        self.slug = slug
        self._clients = set()
        self._lock = threading.Lock()

    def register(self):
        q = queue.Queue(maxsize=1000)
        with self._lock:
            self._clients.add(q)
        return q

    def unregister(self, q):
        with self._lock:
            self._clients.discard(q)

    def broadcast(self, msg):
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass  # slow client: drop, never block the broadcaster


def broadcaster(observer, stop_event, interval=2.0):
    """Tail decisions.jsonl: push `decision` events for new records, and a fresh
    `snapshot` every `interval` seconds so derived panels stay live. Read-only."""
    path = projection.log_path()
    try:
        offset = os.path.getsize(path)
    except OSError:
        offset = 0
    while not stop_event.is_set():
        records, offset = projection.read_from_offset(path, offset)
        for rec in records:
            observer.broadcast(format_sse("decision", rec))
        if observer._clients:
            observer.broadcast(format_sse("snapshot", build_snapshot(observer.slug)))
        stop_event.wait(interval)


def _make_handler(observer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass  # quiet

        def _slug(self):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            return (q.get("slug") or [observer.slug])[0]

        def _send_json(self, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = self.path.split("?", 1)[0]
            if route == "/":
                try:
                    with open(HTML_PATH, "rb") as h:
                        body = h.read()
                except OSError:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif route == "/api/snapshot":
                self._send_json(build_snapshot(self._slug()))
            elif route == "/stream":
                self._serve_stream(self._slug())
            else:
                self.send_error(404)

        def _serve_stream(self, slug):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = observer.register()
            try:
                self.wfile.write(format_sse("snapshot", build_snapshot(slug)).encode("utf-8"))
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=15)
                    except queue.Empty:
                        msg = ": ping\n\n"  # heartbeat
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # client disconnected
            finally:
                observer.unregister(q)

    return Handler


def make_server(port=8787, slug=None):
    """Build a ThreadingHTTPServer bound to 127.0.0.1 with a started broadcaster.
    The broadcaster runs as a daemon thread; its stop event is attached as
    httpd._broadcaster_stop."""
    observer = Observer(slug=slug)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(observer))
    stop_event = threading.Event()
    httpd._broadcaster_stop = stop_event
    threading.Thread(target=broadcaster, args=(observer, stop_event), daemon=True).start()
    return httpd


def serve(port=8787, slug=None):
    httpd = make_server(port, slug)
    host, real = httpd.server_address
    sys.stderr.write("observer on http://%s:%d  (Ctrl-C to stop)\n" % (host, real))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd._broadcaster_stop.set()
        httpd.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only GigaCode flow web observer.")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--slug", default=None)
    args = parser.parse_args(argv)
    serve(args.port, args.slug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
