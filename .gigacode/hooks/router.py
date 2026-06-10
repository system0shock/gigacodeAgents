#!/usr/bin/env python3
"""Hook router: the single dispatcher for all GigaCode hook events.

Registered once per event in .gigacode/settings.json. Matches routes in
router.config.json, runs gate modules from gates/ in-process, aggregates
decisions (block > ask > allow), journals every decision to
.gigacode/logs/decisions.jsonl, and degrades repeated Stop blocks to a
warning after the configured budget.
"""
import importlib.util
import json
import os
import re
import sys
import time

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HOOKS_DIR, "router.config.json")
GATES_DIR = os.path.join(HOOKS_DIR, "gates")
LOGS_DIR = os.path.normpath(os.path.join(HOOKS_DIR, "..", "logs"))
JOURNAL_PATH = os.path.join(LOGS_DIR, "decisions.jsonl")
STATE_PATH = os.path.join(LOGS_DIR, "router-state.json")

ESCAPE_HATCH = (
    'If the hooks themselves are broken, set "disableAllHooks": true in '
    ".gigacode/settings.json temporarily and report the issue."
)

SEVERITY = {"allow": 0, "ask": 1, "block": 2}


def journal(record):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")  # FIX 7: timezone
        with open(JOURNAL_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # journaling must never change a decision


def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        # FIX 5: prune to 50 most-recent keys so the file stays bounded
        if len(state) > 50:
            state = dict(list(state.items())[-50:])
        with open(STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
    except OSError:
        pass


def run_gate(name, event, safety_critical):
    try:
        path = os.path.join(GATES_DIR, name + ".py")
        spec = importlib.util.spec_from_file_location("gate_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.run(event)
        if not isinstance(result, dict) or result.get("decision") not in SEVERITY:
            raise ValueError(f"invalid gate result: {result!r}")
        return result, ""
    except Exception as exc:  # crash isolation: a broken gate must not kill routing
        if safety_critical:
            return {"decision": "block", "reason": f"Safety gate '{name}' failed: {exc}. {ESCAPE_HATCH}"}, str(exc)
        return {"decision": "allow"}, str(exc)


def aggregate(results):
    final = {"decision": "allow"}
    reasons = []
    contexts = []
    for result in results:
        if SEVERITY[result["decision"]] > SEVERITY[final["decision"]]:
            final["decision"] = result["decision"]
        if result.get("reason"):
            reasons.append(result["reason"])
        if result.get("additionalContext"):
            contexts.append(result["additionalContext"])
    if reasons:
        final["reason"] = " ".join(reasons)
    if contexts:
        final["additionalContext"] = "\n".join(contexts)
    return final


def apply_stop_budget(event_name, final, config, event):
    if event_name != "Stop":
        return final
    # sessions without session_id share one budget key — acceptable v1 tradeoff
    key = "stop:" + str(event.get("session_id", "default"))
    state = load_state()
    if final["decision"] != "block":
        if key in state:
            state.pop(key)
            save_state(state)
        return final
    count = state.get(key, 0) + 1
    state[key] = count
    save_state(state)
    budget = config.get("stop_block_budget", 2)
    if count > budget:
        journal({"kind": "stop_budget_exhausted", "session": key, "count": count})
        return {
            "decision": "allow",
            "systemMessage": f"Stop gate blocked {count} times; degraded to a warning. Unresolved: {final.get('reason', '')}",
        }
    return final


def event_arg(argv):
    """FIX 2: manual scan so unknown args never trigger argparse exit 2."""
    for i, token in enumerate(argv):
        if token == "--event" and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith("--event="):
            return token.split("=", 1)[1]
    return ""


def decide(event, event_name, tool_name, config):
    """Core routing logic. Returns the final decision dict."""
    results = []
    for route in config.get("routes", []):
        if route.get("event") != event_name:
            continue
        pattern = route.get("tool_pattern")
        if pattern and not re.search(pattern, tool_name):
            continue
        agent_pattern = route.get("agent_pattern")
        if agent_pattern:
            # Missing/non-string agent field resolves to "" which won't match a
            # non-empty pattern, so the route is SKIPPED. agent_pattern scopes a
            # gate to named agents; routes that must fire for all agents
            # (including unknown ones) must omit it rather than use ".*".
            agent = ""
            for key in ("agent_type", "subagent_type", "agent_name"):
                value = event.get(key)
                if isinstance(value, str) and value:
                    agent = value
                    break
            if not re.search(agent_pattern, agent):
                continue
        for gate_name in route.get("gates", []):
            result, error = run_gate(gate_name, event, route.get("safety_critical", False))
            journal({"kind": "gate", "event": event_name, "tool": tool_name,
                     "gate": gate_name, "decision": result["decision"],
                     "reason": result.get("reason", ""), "error": error})
            results.append(result)
    final = aggregate(results)
    final = apply_stop_budget(event_name, final, config, event)
    journal({"kind": "final", "event": event_name, "tool": tool_name,
             "decision": final["decision"]})
    return final


def main():
    # Ensure UTF-8 output even on Windows where the console codepage may differ
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # FIX 2: no argparse — unknown args are silently ignored
    ev_name_from_arg = event_arg(sys.argv[1:])

    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError as exc:
        journal({"kind": "parse_error", "error": str(exc)})
        print(json.dumps({"decision": "allow"}))
        return

    # FIX 1a: non-dict JSON (null, [], "x") treated same as parse error
    if not isinstance(event, dict):
        journal({"kind": "parse_error", "error": f"expected object, got {type(event).__name__}"})
        print(json.dumps({"decision": "allow"}))
        return

    event_name = ev_name_from_arg or str(event.get("hook_event_name", ""))
    tool_name = str(event.get("tool_name", ""))
    event["hook_event_name"] = event_name  # canonical name so gates can branch on it

    # FIX 1b: load config, then wrap ALL remaining logic fail-closed
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        journal({"kind": "config_error", "error": str(exc)})
        print(json.dumps({"decision": "block",
                          "reason": f"router.config.json unreadable: {exc}. {ESCAPE_HATCH}"},
                         ensure_ascii=False))
        return

    try:
        final = decide(event, event_name, tool_name, config)
    except Exception as exc:
        journal({"kind": "router_error", "error": str(exc)})
        print(json.dumps({"decision": "block",
                          "reason": f"Hook router internal error: {exc}. {ESCAPE_HATCH}"},
                         ensure_ascii=False))
        return

    print(json.dumps(final, ensure_ascii=False))


if __name__ == "__main__":
    main()
