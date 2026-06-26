#!/usr/bin/env python3
"""Hook router: the single dispatcher for all GigaCode hook events.

Registered once per event in .gigacode/settings.json. Matches routes in
router.config.json, runs gate modules from gates/ in-process, aggregates
decisions (block > ask > allow), journals every decision to
.gigacode/logs/decisions.jsonl. Stop blocks are agent-fixable and PERSIST until
fixed (no auto-degrade); a genuinely stuck gate is cleared by the human
disableAllHooks escape hatch, not by outwaiting a budget.
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

# Qwen/GigaCode hook payloads carry the RAW tool id (run_shell_command,
# write_file, replace, ...), not the canonical Bash/WriteFile/Edit names the
# route tool_patterns match on. Normalize before routing so git_guard et al.
# actually fire. Idempotent: canonical names are not keys, so they pass through.
TOOL_NAME_MAP = {
    "run_shell_command": "Bash",
    "shell": "Bash",
    # MCP servers expose their own shell tool ids (Serena: execute_shell_command).
    # Map them to Bash so the safety_critical git_guard route fires — else a shell
    # command via such a tool runs ZERO gates (force-push, .gigacode write slip
    # through).
    "execute_shell_command": "Bash",
    "run_command": "Bash",
    "exec_command": "Bash",
    "write_file": "WriteFile",
    "replace": "Edit",
    "edit": "Edit",
    "edit_file": "Edit",
    "notebook_edit": "NotebookEdit",
    # Symbol-level MCP servers (Serena) mutate files through their OWN tool ids,
    # not write_file/replace. Map the MUTATORS to canonical write ids so the same
    # PreToolUse gates (git_guard, gate_stage_order, gate_scope_guard) fire —
    # else the agent could edit .gigacode or forge an approval marker via Serena.
    # Read-only Serena tools (find_symbol, get_symbols_overview, read_file) are
    # deliberately absent so they stay unmatched → allow (no over-block).
    "replace_symbol_body": "Edit",
    "insert_after_symbol": "Edit",
    "insert_before_symbol": "Edit",
    "replace_regex": "Edit",
    "create_text_file": "WriteFile",
}


def normalize_tool_name(raw):
    """Canonicalize a raw tool id. MCP runtimes prefix the id
    (``mcp__serena__replace_symbol_body``, ``serena__...``, ``serena.replace``);
    strip the prefix to the bare tool name before mapping. Unknown ids pass
    through unchanged (unmatched → allow, as before)."""
    raw = str(raw)
    base = raw.split("__")[-1].rsplit(".", 1)[-1] if ("__" in raw or "." in raw) else raw
    return TOOL_NAME_MAP.get(base, TOOL_NAME_MAP.get(raw, raw))


# WI-2: every journal record carries session_id/feature/agent so the read-model
# (projection/observer) can draw swimlanes, attribute per-agent activity, and
# separate fan-out lines. Set once per run in main() from the event; empty
# strings when unknown so the schema is stable. The feature (task slug) is
# derived from the write path via config-declared patterns — the convention is
# module-specific (dev: docs/development/<slug>; analytics: docs/features/<slug>),
# so the shared router stays generic and reads `feature_patterns` from the config.
_IDENTITY = {}
_PATH_KEYS = ("path", "file_path", "filename", "notebook_path")


def _event_path(event):
    for key in _PATH_KEYS:
        value = event.get(key)
        if isinstance(value, str):
            return value.replace("\\", "/")
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for key in _PATH_KEYS:
            value = tool_input.get(key)
            if isinstance(value, str):
                return value.replace("\\", "/")
    return ""


def _feature_of(event, feature_patterns):
    path = _event_path(event)
    if not path:
        return ""
    for pattern in feature_patterns or []:
        try:
            match = re.search(pattern, path, re.IGNORECASE)
        except re.error:
            continue  # a broken pattern must not break journaling
        if match and match.groups():
            return match.group(1)
    return ""


def identity_of(event, feature_patterns=()):
    """WI-2 line identifiers: session_id + feature (task slug from the path via
    config patterns) + agent (subagent type). Always present (empty when unknown)."""
    sid = event.get("session_id")
    agent = ""
    for key in ("agent_type", "subagent_type", "agent_name"):
        value = event.get(key)
        if isinstance(value, str) and value:
            agent = value
            break
    return {"session_id": sid if isinstance(sid, str) else "",
            "feature": _feature_of(event, feature_patterns),
            "agent": agent}


def journal(record):
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        record = {**_IDENTITY, **record}  # WI-2 identity; record fields win on conflict
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")  # FIX 7: timezone
        with open(JOURNAL_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # journaling must never change a decision


def load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    # Distrust agent-writable counters: keep only small non-negative ints (0..10).
    # Genuine consecutive-block counts never exceed stop_block_budget + 1 before a
    # budget-exhausted allow resets the key; 10 is well above any realistic budget
    # while rejecting a pre-seeded huge value (e.g. 99) that would otherwise
    # pre-exhaust the budget on the first real block.
    return {k: v for k, v in raw.items() if isinstance(v, int) and 0 <= v <= 10}


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
    """Track consecutive Stop-blocks per session.

    The prior count is clamped into [0, budget-1] before incrementing, so
    `min(prior, budget-1) + 1 <= budget`: a block always stays a block. A
    pre-seeded counter in [budget, 10] (which load_state's 0..10 window would
    otherwise admit) therefore cannot skip the first genuine block.

    There is NO auto-degrade-to-allow: a single persisted integer cannot be both
    seed-proof and degrade-after-N (the clamp that defeats a seed also caps the
    count below the degrade threshold). The earlier degrade was itself a soft
    bypass — Stop blocks are agent-fixable, so they now persist until fixed; a
    genuinely stuck/buggy gate is resolved by the human disableAllHooks escape
    hatch, not by the agent outwaiting the budget. git_guard additionally
    write-protects the state file, so seeding requires a separate write bypass."""
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
    budget = config.get("stop_block_budget", 2)
    count = min(max(state.get(key, 0), 0), max(budget - 1, 0)) + 1
    state[key] = count
    save_state(state)
    journal({"kind": "stop_block", "session": key, "count": count, "budget": budget})
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


def to_wire(event_name, final):
    """Add the hookSpecificOutput shape Qwen/GigaCode actually reads, WITHOUT
    dropping the top-level fields (kept for the offline suite and for
    Stop/PostToolUse, which read top-level). Top-level decision stays the source
    of truth; this only re-expresses it where the runtime looks.

    For PreToolUse: emit hookSpecificOutput ONLY when the decision is ask or
    block (deny). On allow, emit nothing extra so the runtime's own permission
    flow applies (respecting the user's settings.json permissions.ask/allow/deny
    config). Emitting permissionDecision:"allow" on every benign call would
    auto-approve the tool call and silently nullify the user's permission config."""
    decision = final.get("decision", "allow")
    if event_name == "PreToolUse":
        if decision in ("ask", "block"):
            final["hookSpecificOutput"] = {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny" if decision == "block" else "ask",
                "permissionDecisionReason": final.get("reason") or "Blocked by GigaCode gate",
            }
        # allow: emit no hookSpecificOutput so the runtime's own permission flow applies
    elif event_name in ("SessionStart", "SubagentStart", "UserPromptSubmit", "PostToolUse"):
        if final.get("additionalContext"):
            final["hookSpecificOutput"] = {
                "hookEventName": event_name,
                "additionalContext": final["additionalContext"],
            }
    return final


def emit(event_name, final):
    print(json.dumps(to_wire(event_name, final), ensure_ascii=False))


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
        emit(ev_name_from_arg, {"decision": "allow"})
        return

    # FIX 1a: non-dict JSON (null, [], "x") treated same as parse error
    if not isinstance(event, dict):
        journal({"kind": "parse_error", "error": f"expected object, got {type(event).__name__}"})
        emit(ev_name_from_arg, {"decision": "allow"})
        return

    event_name = ev_name_from_arg or str(event.get("hook_event_name", ""))
    tool_name = normalize_tool_name(event.get("tool_name", ""))
    event["hook_event_name"] = event_name  # canonical name so gates can branch on it
    event["tool_name"] = tool_name         # canonical tool id for gates that read it

    # FIX 1b: load config, then wrap ALL remaining logic fail-closed
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        journal({"kind": "config_error", "error": str(exc)})
        emit(ev_name_from_arg, {"decision": "block",
                                "reason": f"router.config.json unreadable: {exc}. {ESCAPE_HATCH}"})
        return

    global _IDENTITY  # WI-2: stamp every subsequent journal record for this run
    _IDENTITY = identity_of(event, config.get("feature_patterns", []))

    try:
        final = decide(event, event_name, tool_name, config)
    except Exception as exc:
        journal({"kind": "router_error", "error": str(exc)})
        emit(ev_name_from_arg, {"decision": "block",
                                "reason": f"Hook router internal error: {exc}. {ESCAPE_HATCH}"})
        return

    emit(event_name, final)


if __name__ == "__main__":
    main()
