"""Hook event parsing and result helpers tolerant to fork field naming."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field


SEVERITY = {"allow": 0, "ask": 1, "block": 2}


@dataclass
class Result:
    decision: str = "allow"
    reason: str = ""
    stop_reason: str | None = None
    context: str | None = None


def read_event() -> dict[str, object]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _first(event: dict[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in event:
            return event[key]
    return None


def prompt(event: dict[str, object]) -> str:
    return str(_first(event, ("prompt", "user_prompt", "userPrompt")) or "").strip()


def last_message(event: dict[str, object]) -> str:
    return str(
        _first(event, ("last_assistant_message", "lastAssistantMessage", "message"))
        or ""
    ).strip()


def tool_name(event: dict[str, object]) -> str:
    return str(_first(event, ("tool_name", "toolName", "tool")) or "")


def tool_input(event: dict[str, object]) -> dict[str, object]:
    value = _first(event, ("tool_input", "toolInput", "input", "parameters"))
    return value if isinstance(value, dict) else {}


def file_path(event: dict[str, object]) -> str:
    payload = tool_input(event)
    value = _first(payload, ("file_path", "filePath", "path", "file"))
    return str(value or "").replace("\\", "/")


def bash_command(event: dict[str, object]) -> str:
    payload = tool_input(event)
    value = _first(payload, ("command", "cmd"))
    return str(value or "")


def infer_event_name(event: dict[str, object]) -> str:
    declared = str(
        _first(event, ("hook_event_name", "hookEventName", "event")) or ""
    )
    if declared:
        return declared
    if prompt(event):
        return "UserPromptSubmit"
    if _first(event, ("tool_response", "toolResponse", "tool_result", "toolResult")):
        return "PostToolUse"
    if tool_name(event):
        return "PreToolUse"
    if last_message(event):
        return "Stop"
    return "Stop"


def merge(results: list[Result]) -> Result:
    merged = Result()
    reasons: list[str] = []
    stop_reasons: list[str] = []
    contexts: list[str] = []
    for result in results:
        if SEVERITY.get(result.decision, 0) > SEVERITY.get(merged.decision, 0):
            merged.decision = result.decision
        if result.reason and result.decision != "allow":
            reasons.append(result.reason)
        if result.stop_reason:
            stop_reasons.append(result.stop_reason)
        if result.context:
            contexts.append(result.context)
    if not reasons:
        reasons = [r.reason for r in results if r.reason]
    merged.reason = "; ".join(reasons) or "No checks matched."
    merged.stop_reason = "\n".join(stop_reasons) or None
    merged.context = "\n\n".join(contexts) or None
    return merged


def emit(event_name: str, result: Result) -> int:
    payload: dict[str, object] = {
        "decision": result.decision,
        "reason": result.reason,
    }
    if result.stop_reason:
        payload["stopReason"] = result.stop_reason
    hook_specific: dict[str, object] = {}
    if result.context:
        hook_specific["additionalContext"] = result.context
    if event_name == "PreToolUse":
        # Superset payload: legacy "decision" plus the newer permissionDecision
        # schema so both hook contract generations are satisfied.
        permission = {"allow": "allow", "ask": "ask", "block": "deny"}[
            result.decision if result.decision in SEVERITY else "allow"
        ]
        hook_specific["hookEventName"] = "PreToolUse"
        hook_specific["permissionDecision"] = permission
        hook_specific["permissionDecisionReason"] = result.reason
    if hook_specific:
        payload["hookSpecificOutput"] = hook_specific
    print(json.dumps(payload, ensure_ascii=False))
    return 0
