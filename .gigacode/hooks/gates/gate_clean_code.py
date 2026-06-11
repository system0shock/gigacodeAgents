#!/usr/bin/env python3
"""Clean-code gate: heuristics on the file just written. ADVISORY-ONLY —
always returns allow; findings go through additionalContext. Promotion to
blocking requires decision-journal evidence (design revision 2026-06-10)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

CODE_EXTS = (".kt", ".kts", ".java", ".py", ".ts", ".tsx", ".js", ".jsx",
             ".go", ".rs", ".cs")
CONTROL_RE = re.compile(r"^(if|for|while|when|switch|try|do|else|catch|synchronized)\b")
TEST_FILE_RE = re.compile(r"(test|spec)", re.IGNORECASE)


def resolve(path):
    if os.path.isabs(path):
        return path
    candidate = os.path.abspath(path)
    if os.path.exists(candidate):
        return candidate
    return os.path.join(_lib.root(), path)


def long_blocks(lines, max_len):
    """Naive brace-depth scan; function-like = the opening line has '(' and is
    not a control-flow statement. Heuristic by design — advisory only."""
    warnings = []
    stack = []
    for lineno, line in enumerate(lines, 1):
        for char in line:
            if char == "{":
                head = line.lstrip()
                func_like = "(" in line and not CONTROL_RE.match(head)
                stack.append((lineno, func_like))
            elif char == "}" and stack:
                start, func_like = stack.pop()
                length = lineno - start + 1
                if func_like and length > max_len:
                    warnings.append(
                        f"строка {start}: блок на {length} строк (максимум {max_len})")
    return warnings


def run(event):
    path = _lib.path_from_event(event)
    if not path or not path.endswith(CODE_EXTS):
        return {"decision": "allow"}
    target = resolve(path)
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return {"decision": "allow"}
    config = _lib.load_quality_gates().get("clean_code") or {}
    max_file = int(config.get("max_file_lines", 400))
    max_func = int(config.get("max_function_lines", 60))
    markers = config.get("placeholder_markers") or ["TODO", "FIXME", "XXX"]

    warnings = []
    if len(lines) > max_file:
        warnings.append(f"файл {len(lines)} строк (максимум {max_file})")
    marker_re = re.compile(r"\b(" + "|".join(re.escape(m) for m in markers) + r")\b")
    marker_lines = [str(i) for i, line in enumerate(lines, 1) if marker_re.search(line)]
    if marker_lines:
        warnings.append("маркеры " + "/".join(markers)
                        + " на строках: " + ", ".join(marker_lines[:10]))
    warnings.extend(long_blocks(lines, max_func)[:5])
    if TEST_FILE_RE.search(os.path.basename(path)) and any(
            "Thread.sleep" in line for line in lines):
        warnings.append("Thread.sleep в тестовом файле — используй Awaitility "
                        "или другой механизм ожидания вместо sleep")

    if not warnings:
        return {"decision": "allow"}
    return {"decision": "allow", "additionalContext": (
        f"gate_clean_code (advisory) для {path}:\n- " + "\n- ".join(warnings))}


def main():
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
