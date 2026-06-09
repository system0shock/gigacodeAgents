"""Gradle/Maven autodetection with wrapper preference."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


GRADLE_FILES = ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")
MAVEN_FILES = ("pom.xml",)
LINT_PLUGINS = ("ktlint", "detekt", "checkstyle", "spotless")


def detect(root: Path | None = None) -> dict[str, object]:
    root = root or Path(".")
    build_files = [name for name in GRADLE_FILES + MAVEN_FILES if (root / name).exists()]
    system = None
    if any(name in build_files for name in GRADLE_FILES):
        system = "gradle"
    elif any(name in build_files for name in MAVEN_FILES):
        system = "maven"

    wrapper = None
    if system == "gradle":
        for candidate in ("gradlew.bat", "gradlew") if sys.platform == "win32" else ("gradlew",):
            if (root / candidate).exists():
                wrapper = f"./{candidate}" if candidate == "gradlew" else candidate
                break
    elif system == "maven":
        for candidate in ("mvnw.cmd", "mvnw") if sys.platform == "win32" else ("mvnw",):
            if (root / candidate).exists():
                wrapper = f"./{candidate}" if candidate == "mvnw" else candidate
                break

    lint_plugins: list[str] = []
    for name in build_files:
        try:
            text = (root / name).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for plugin in LINT_PLUGINS:
            if plugin in text and plugin not in lint_plugins:
                lint_plugins.append(plugin)

    return {
        "system": system,
        "wrapper": wrapper,
        "build_files": build_files,
        "lint_plugins": lint_plugins,
    }


def runner(info: dict[str, object]) -> str | None:
    """Return the executable to run builds with, or None when unavailable."""
    if info.get("wrapper"):
        return str(info["wrapper"])
    if info.get("system") == "gradle" and shutil.which("gradle"):
        return "gradle"
    if info.get("system") == "maven" and shutil.which("mvn"):
        return "mvn"
    return None


def commands(info: dict[str, object]) -> dict[str, list[str]]:
    """Build/test/lint command lines for the detected system, wrapper-first."""
    exe = runner(info)
    if not exe:
        return {}
    if info.get("system") == "gradle":
        result = {
            "compile": [exe, "--no-daemon", "-q", "testClasses"],
            "test": [exe, "--no-daemon", "-q", "test"],
        }
        lint_tasks = {
            "ktlint": "ktlintCheck",
            "detekt": "detekt",
            "checkstyle": "checkstyleMain",
            "spotless": "spotlessCheck",
        }
        lint = [lint_tasks[p] for p in info.get("lint_plugins", []) if p in lint_tasks]
        if lint:
            result["lint"] = [exe, "--no-daemon", "-q", *lint]
        return result
    if info.get("system") == "maven":
        result = {
            "compile": [exe, "-q", "test-compile"],
            "test": [exe, "-q", "test"],
        }
        if "checkstyle" in info.get("lint_plugins", []):
            result["lint"] = [exe, "-q", "checkstyle:check"]
        elif "spotless" in info.get("lint_plugins", []):
            result["lint"] = [exe, "-q", "spotless:check"]
        return result
    return {}


def summary(info: dict[str, object]) -> str:
    if not info.get("system"):
        return (
            "Build system: none detected. "
            "Limitation: compile/test/lint checks cannot run; rely on static checks."
        )
    parts = [f"Build system: {info['system']}"]
    parts.append(f"wrapper: {info['wrapper'] or 'absent'}")
    plugins = info.get("lint_plugins") or []
    parts.append(f"lint plugins in build files: {', '.join(plugins) if plugins else 'none'}")
    return ". ".join(str(p) for p in parts) + "."
