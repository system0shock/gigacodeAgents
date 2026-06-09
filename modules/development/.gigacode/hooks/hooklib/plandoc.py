"""Deterministic validation of task plan documents in docs/plans/."""

from __future__ import annotations

import re
from pathlib import Path


PLANS_DIR = Path("docs") / "plans"

SECTIONS: tuple[tuple[str, str], ...] = (
    ("Goal", r"^##\s*(Goal|Цель)\b"),
    ("Scope", r"^##\s*(Scope|Объ[её]м)\b"),
    ("Steps", r"^##\s*(Steps|Шаги)\b"),
    ("Affected files", r"^##\s*(Affected\s+files|Затрагиваемые\s+файлы)\b"),
    ("Verification", r"^##\s*(Verification|Test\s+strategy|Проверка|Стратегия\s+тестирования)\b"),
    ("Risks", r"^##\s*(Risks|Риски)\b"),
)

APPROVED_RE = re.compile(r"^(Status:\s*approved|Статус:\s*утвержд[её]н)\s*$", re.IGNORECASE | re.MULTILINE)
PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b", re.IGNORECASE)
PATH_TOKEN_RE = re.compile(r"[\w./-]+\.(java|kt|kts|gradle|xml|properties|md|sql|yml|yaml)\b")
NUMBERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+\S", re.MULTILINE)
NO_TESTS_RE = re.compile(r"no-tests:\s*\S", re.IGNORECASE)
BUILD_CHECK_RE = re.compile(r"build-check:\s*on\b", re.IGNORECASE)


def find_latest_plan(root: Path | None = None) -> Path | None:
    plans_dir = (root or Path(".")) / PLANS_DIR
    if not plans_dir.exists():
        return None
    plans = [p for p in plans_dir.glob("*.md") if p.is_file()]
    if not plans:
        return None
    return max(plans, key=lambda p: p.stat().st_mtime)


def _section_body(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    rest = text[match.end():]
    next_heading = re.search(r"^##\s", rest, re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def validate(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"{path}: cannot read plan ({error})"]

    for name, pattern in SECTIONS:
        body = _section_body(text, pattern)
        if body is None:
            issues.append(f"{path}: missing required section '{name}'")
            continue
        if not body.strip():
            issues.append(f"{path}: section '{name}' is empty")
            continue
        if name == "Steps" and len(NUMBERED_ITEM_RE.findall(body)) < 2:
            issues.append(f"{path}: section 'Steps' needs a numbered list with at least 2 items")
        if name == "Affected files" and not PATH_TOKEN_RE.search(body):
            issues.append(f"{path}: section 'Affected files' must list at least one file path")
        if name == "Verification":
            lowered = body.lower()
            if not ("test" in lowered or "junit" in lowered or "тест" in lowered or NO_TESTS_RE.search(body)):
                issues.append(
                    f"{path}: section 'Verification' must mention tests or state 'no-tests: <reason>'"
                )

    if PLACEHOLDER_RE.search(text):
        issues.append(f"{path}: contains TODO/TBD/FIXME marker")

    return issues


def is_approved(path: Path) -> bool:
    try:
        return bool(APPROVED_RE.search(path.read_text(encoding="utf-8")))
    except OSError:
        return False


def allows_skipping_tests(path: Path) -> bool:
    try:
        return bool(NO_TESTS_RE.search(path.read_text(encoding="utf-8")))
    except OSError:
        return False


def build_check_enabled(path: Path) -> bool:
    try:
        return bool(BUILD_CHECK_RE.search(path.read_text(encoding="utf-8")))
    except OSError:
        return False


def affected_files(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    body = _section_body(text, SECTIONS[3][1]) or ""
    return [match.group(0) for match in PATH_TOKEN_RE.finditer(body)]
