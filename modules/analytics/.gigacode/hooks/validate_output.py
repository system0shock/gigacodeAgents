#!/usr/bin/env python3
"""Output validation hook for GigaCode reverse-analysis artifacts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REQUIRED_FILES = (
    "overview.adoc",
    "flow.adoc",
    "integrations.adoc",
    "data.adoc",
    "questions.adoc",
)

PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b", re.IGNORECASE)
OUTPUT_PATH_RE = re.compile(r"docs/features/([A-Za-z0-9][A-Za-z0-9_.-]*)/?")


def emit(decision: str, reason: str, stop_reason: str | None = None) -> int:
    payload: dict[str, object] = {"decision": decision, "reason": reason}
    if stop_reason:
        payload["stopReason"] = stop_reason
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def read_event() -> dict[str, object]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def should_validate(message: str) -> bool:
    lowered = message.lower()
    return "docs/features/" in lowered or (
        "reverse" in lowered and "analysis" in lowered and "complete" in lowered
    )


def find_feature_dir(message: str) -> Path | None:
    match = OUTPUT_PATH_RE.search(message.replace("\\", "/"))
    if match:
        return Path("docs") / "features" / match.group(1)

    features_dir = Path("docs") / "features"
    if not features_dir.exists():
        return None

    candidates = [path for path in features_dir.iterdir() if path.is_dir()]
    if len(candidates) == 1:
        return candidates[0]
    return None


def validate_file(path: Path) -> list[str]:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8")

    if not text.lstrip().startswith("="):
        issues.append(f"{path}: missing AsciiDoc document title")
    if PLACEHOLDER_RE.search(text):
        issues.append(f"{path}: contains TODO/TBD/FIXME marker")
    if "```" in text:
        issues.append(f"{path}: contains Markdown fenced code block")
    if re.search(r"^#{1,6}\s", text, re.MULTILINE):
        issues.append(f"{path}: contains Markdown heading")

    return issues


def main() -> int:
    event = read_event()
    message = str(event.get("last_assistant_message", "")).strip()

    if not should_validate(message):
        return emit("allow", "No reverse-analysis output claim detected.")

    feature_dir = find_feature_dir(message)
    if feature_dir is None:
        return emit(
            "block",
            "Could not determine feature output directory.",
            "State the generated path as docs/features/<feature-name>/ and run validation again.",
        )

    issues: list[str] = []
    if not feature_dir.exists():
        issues.append(f"{feature_dir}: directory does not exist")
    else:
        for filename in REQUIRED_FILES:
            path = feature_dir / filename
            if not path.exists():
                issues.append(f"{path}: missing required file")
            else:
                issues.extend(validate_file(path))

    if issues:
        return emit(
            "block",
            "Reverse-analysis output validation failed.",
            "\n".join(issues),
        )

    return emit("allow", "Reverse-analysis output validation passed.")


if __name__ == "__main__":
    raise SystemExit(main())
