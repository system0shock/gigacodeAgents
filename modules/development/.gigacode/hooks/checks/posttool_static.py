"""PostToolUse: pure-stdlib static checks on the just-written source file.

scan_file() is shared with the Stop-stage re-scan in stop_final.
"""

from __future__ import annotations

import re
from pathlib import Path

from hooklib import sources
from hooklib.event import Result, file_path


PROD_BLOCKERS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("print-stacktrace", re.compile(r"\.printStackTrace\s*\("), "printStackTrace call; use SLF4J logging"),
    ("system-out", re.compile(r"\bSystem\.out\.print"), "System.out output; use SLF4J logging"),
    ("placeholder", re.compile(r"\b(TODO|TBD|FIXME)\b"), "leftover TODO/TBD/FIXME marker"),
    ("wildcard-import", re.compile(r"^import\s+(static\s+)?[\w.]+\.\*", re.MULTILINE), "wildcard import"),
)

KOTLIN_PROD_BLOCKERS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("println", re.compile(r"^\s*println\s*\(", re.MULTILINE), "println output; use SLF4J logging"),
    ("not-null-assertion", re.compile(r"!!"), "Kotlin !! operator; use requireNotNull or ?:"),
)

TEST_BLOCKERS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "junit4-import",
        re.compile(r"^import\s+(org\.junit\.(Test|Before|After|Assert|Ignore)\b|junit\.framework)", re.MULTILINE),
        "JUnit 4 import; use org.junit.jupiter (JUnit 5)",
    ),
    (
        "disabled-without-reason",
        re.compile(r"@(Disabled|Ignore)\b(?!\s*\(\s*\")"),
        "@Disabled/@Ignore without a reason string",
    ),
    (
        "lazy-test-name",
        re.compile(r"\b(fun|void)\s+test\d+\s*\("),
        "lazy test name like test1(); describe the behavior",
    ),
)

ASSERTION_RE = re.compile(
    r"assert\w*\s*[({.]|\bverify\s*[({]|confirmVerified|verifyNoMoreInteractions|expectThat|shouldBe|\.isEqualTo"
)
TEST_ANNOTATION_RE = re.compile(r"@(Test|ParameterizedTest|RepeatedTest)\b")
MAX_FILE_LINES = 500


def scan_file(path: str, text: str, warn_only: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Return (blocking_issues, warnings) for one source file."""
    warn_only = warn_only or set()
    blocking: list[str] = []
    warnings: list[str] = []

    def add(check_id: str, message: str) -> None:
        target = warnings if check_id in warn_only else blocking
        target.append(f"{path}: {message}")

    if sources.is_test(path):
        for check_id, pattern, message in TEST_BLOCKERS:
            if pattern.search(text):
                add(check_id, message)
        if TEST_ANNOTATION_RE.search(text) and not ASSERTION_RE.search(text):
            add("no-assertions", "test file has @Test methods but no assertions or verifications")
    else:
        for check_id, pattern, message in PROD_BLOCKERS:
            if pattern.search(text):
                add(check_id, message)
        if sources.language(path) == "kotlin":
            for check_id, pattern, message in KOTLIN_PROD_BLOCKERS:
                if pattern.search(text):
                    add(check_id, message)
        if "/src/main/" in "/" + path.lstrip("/") and not sources.has_test(path):
            warnings.append(f"{path}: no test file found for this class; write it before finishing")

    if text.count("\n") + 1 > MAX_FILE_LINES:
        warnings.append(f"{path}: file longer than {MAX_FILE_LINES} lines; consider splitting")

    return blocking, warnings


def run(event: dict[str, object], options: dict[str, object]) -> Result:
    path = file_path(event)
    if not sources.is_source(path):
        return Result(decision="allow", reason="")
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return Result(decision="allow", reason="")

    warn_only = {str(item) for item in options.get("warn_only", [])}
    blocking, warnings = scan_file(path, text, warn_only)

    if blocking:
        return Result(
            decision="block",
            reason="Static code check failed.",
            context="Fix these findings:\n" + "\n".join(blocking + warnings),
        )
    if warnings:
        return Result(decision="allow", reason="Static warnings.", context="\n".join(warnings))
    return Result(decision="allow", reason="Static code check passed.")
