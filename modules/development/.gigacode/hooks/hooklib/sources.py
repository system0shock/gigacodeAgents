"""Classification of Java/Kotlin source paths into prod and test code."""

from __future__ import annotations

import re
from pathlib import Path


SOURCE_SUFFIXES = (".java", ".kt", ".kts")
TEST_NAME_RE = re.compile(r"(Test|Tests|IT)\.(java|kt)$")
TEST_DIR_MARKERS = ("/src/test/", "/src/integrationTest/", "/src/testFixtures/")


def is_source(path: str) -> bool:
    return path.endswith(SOURCE_SUFFIXES)


def is_test(path: str) -> bool:
    normalized = "/" + path.replace("\\", "/").lstrip("/")
    if any(marker in normalized for marker in TEST_DIR_MARKERS):
        return True
    return bool(TEST_NAME_RE.search(normalized))


def language(path: str) -> str:
    if path.endswith(".java"):
        return "java"
    if path.endswith((".kt", ".kts")):
        return "kotlin"
    return "unknown"


def expected_test_paths(prod_path: str) -> list[Path]:
    """Mirror src/main/<lang>/pkg/Foo.<ext> into candidate test file paths."""
    normalized = prod_path.replace("\\", "/")
    if "/src/main/" not in "/" + normalized.lstrip("/"):
        return []
    stem = Path(normalized).stem
    candidates: list[Path] = []
    for src_set in ("java", "kotlin"):
        marker = f"src/main/{src_set}/"
        index = normalized.find(marker)
        if index == -1:
            continue
        relative = Path(normalized[index + len(marker):]).parent
        for test_set in ("java", "kotlin"):
            for suffix in (".java", ".kt"):
                candidates.append(
                    Path(normalized[:index])
                    / f"src/test/{test_set}"
                    / relative
                    / f"{stem}Test{suffix}"
                )
    return candidates


def has_test(prod_path: str, root: Path | None = None) -> bool:
    root = root or Path(".")
    for candidate in expected_test_paths(prod_path):
        if (root / candidate).exists():
            return True
    stem = Path(prod_path.replace("\\", "/")).stem
    test_root = root / "src" / "test"
    if test_root.exists():
        for pattern in (f"{stem}Test.*", f"{stem}Tests.*", f"{stem}IT.*"):
            if any(test_root.rglob(pattern)):
                return True
    return False
