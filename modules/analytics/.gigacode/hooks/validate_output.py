#!/usr/bin/env python3
"""Output validation hook for GigaCode reverse-analysis artifacts."""

from __future__ import annotations

import json
import re
import subprocess
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
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
EVIDENCE_LABEL_RE = re.compile(r"(Источник|Source)\s*:", re.IGNORECASE)
STATUS_LABEL_RE = re.compile(r"(Статус|Status)\s*:", re.IGNORECASE)
SCOPE_CONFIRMED_RE = re.compile(
    r"^(Статус:\s*подтвержд[её]н|Status:\s*confirmed)\s*$", re.IGNORECASE | re.MULTILINE
)

SCOPES_DIR = Path("docs") / "scopes"


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


def changed_feature_files() -> list[str]:
    """Changed/untracked .adoc files under docs/features/ via git, [] on failure."""
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    files: list[str] = []
    for line in completed.stdout.splitlines():
        path = line[3:].strip().strip('"').replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if "docs/features/" in path and path.endswith(".adoc"):
            files.append(path)
    return files


def message_claims_output(message: str) -> bool:
    lowered = message.lower()
    return "docs/features/" in lowered or (
        "reverse" in lowered and "analysis" in lowered and "complete" in lowered
    )


def find_latest_scope() -> Path | None:
    if not SCOPES_DIR.exists():
        return None
    scopes = [p for p in SCOPES_DIR.glob("*.md") if p.is_file()]
    if not scopes:
        return None
    return max(scopes, key=lambda p: p.stat().st_mtime)


def find_feature_dir(message: str) -> tuple[Path | None, str | None]:
    """Resolve the feature directory; returns (dir, blocking_issue)."""
    scope = find_latest_scope()
    if scope is not None:
        try:
            text = scope.read_text(encoding="utf-8")
        except OSError as error:
            return None, f"{scope}: cannot read scope artifact ({error})"
        if not SCOPE_CONFIRMED_RE.search(text):
            return None, (
                f"{scope}: scope artifact is not confirmed "
                "(add 'Статус: подтвержден' after the analyst confirms scope)"
            )
        match = OUTPUT_PATH_RE.search(text.replace("\\", "/"))
        if match:
            return Path("docs") / "features" / match.group(1), None
        return None, (
            f"{scope}: scope artifact must state the output directory as "
            "'Каталог результата: docs/features/<feature-slug>/'"
        )

    match = OUTPUT_PATH_RE.search(message.replace("\\", "/"))
    if match:
        return Path("docs") / "features" / match.group(1), None

    features_dir = Path("docs") / "features"
    if features_dir.exists():
        candidates = [path for path in features_dir.iterdir() if path.is_dir()]
        if len(candidates) == 1:
            return candidates[0], None
    return None, None


def validate_file(path: Path) -> list[str]:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8")

    if not text.lstrip("\ufeff\r\n\t ").startswith("="):
        issues.append(f"{path}: missing AsciiDoc document title")
    if PLACEHOLDER_RE.search(text):
        issues.append(f"{path}: contains TODO/TBD/FIXME marker")
    if "```" in text:
        issues.append(f"{path}: contains Markdown fenced code block")
    if re.search(r"^#{1,6}\s", text, re.MULTILINE):
        issues.append(f"{path}: contains Markdown heading")
    if not CYRILLIC_RE.search(text):
        issues.append(f"{path}: must be written in Russian")
    if path.name == "questions.adoc":
        if not STATUS_LABEL_RE.search(text):
            issues.append(
                f"{path}: missing status labels (Статус: предположение / Статус: открытый вопрос)"
            )
    elif not EVIDENCE_LABEL_RE.search(text):
        issues.append(
            f"{path}: missing evidence labels (Источник: код / jira / confluence / пользователь)"
        )

    return issues


def main() -> int:
    event = read_event()
    message = str(event.get("last_assistant_message", "")).strip()

    changed = changed_feature_files()
    if not changed and not message_claims_output(message):
        return emit("allow", "No reverse-analysis output detected.")

    feature_dir, scope_issue = find_feature_dir(message)
    if scope_issue:
        return emit("block", "Scope artifact validation failed.", scope_issue)
    if feature_dir is None:
        return emit(
            "block",
            "Could not determine feature output directory.",
            "Record the confirmed scope in docs/scopes/<feature-slug>.md with "
            "'Каталог результата: docs/features/<feature-slug>/' or state the generated path "
            "as docs/features/<feature-name>/ and run validation again.",
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
