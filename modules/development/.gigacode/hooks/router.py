#!/usr/bin/env python3
"""Single entry point for all development-module hooks.

Usage: python .gigacode/hooks/router.py <EventName>

Reads the hook event JSON from stdin, dispatches to the check modules
configured in router_config.json, merges their decisions (block > ask >
allow) and prints one JSON decision. A failing check never blocks: it is
downgraded to allow and reported on stderr.
"""

from __future__ import annotations

import fnmatch
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hooklib import event as eventlib


def load_config() -> dict[str, list[dict[str, object]]]:
    config_path = Path(__file__).resolve().parent / "router_config.json"
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"router: cannot load router_config.json: {error}", file=sys.stderr)
        return {}


def matches(entry: dict[str, object], event: dict[str, object]) -> bool:
    tools = entry.get("tools")
    if tools:
        if eventlib.tool_name(event) not in tools:
            return False
    paths = entry.get("paths")
    if paths:
        path = eventlib.file_path(event)
        if not path:
            return False
        normalized = path.lstrip("./")
        if not any(
            fnmatch.fnmatch(normalized, str(pattern)) or fnmatch.fnmatch(path, str(pattern))
            for pattern in paths
        ):
            return False
    return True


def run_check(name: str, event: dict[str, object], options: dict[str, object]) -> eventlib.Result:
    module = importlib.import_module(f"checks.{name}")
    return module.run(event, options)


def main(argv: list[str]) -> int:
    event = eventlib.read_event()
    event_name = argv[1] if len(argv) > 1 else eventlib.infer_event_name(event)

    config = load_config()
    results: list[eventlib.Result] = []
    for entry in config.get(event_name, []):
        if not matches(entry, event):
            continue
        name = str(entry.get("check", ""))
        options = entry.get("options")
        options = options if isinstance(options, dict) else {}
        try:
            results.append(run_check(name, event, options))
        except Exception as error:  # noqa: BLE001 - a broken check must never block
            print(f"router: check '{name}' failed: {error}", file=sys.stderr)
            results.append(eventlib.Result(decision="allow", reason=""))

    if not results:
        results.append(eventlib.Result(decision="allow", reason="No checks configured for event."))

    return eventlib.emit(event_name, eventlib.merge(results))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
