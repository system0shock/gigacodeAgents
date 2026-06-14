#!/usr/bin/env python3
"""Format and placement gate for the final documentation tree (PostToolUse)."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

TREE_RE = re.compile(r"(^|/)(analytics|architecture)/", re.IGNORECASE)
UPPER_CAMEL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*\.[a-z]+$")
KEBAB_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DIR_EXCEPTIONS = {"nfr and contact"}
MD_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

YAML_DIRS = ("analytics/api/event/", "analytics/api/rest/public/",
             "analytics/api/rest/private/", "analytics/integration/event/",
             "analytics/integration/rest/")
PLACEMENT = {
    ".puml": ("architecture/",),
    ".adoc": ("analytics/functional-requirements/", "analytics/use-case/",
              "analytics/glossary/", "analytics/integration/mapping/",
              "analytics/integration/nfr and contact/",
              "analytics/api/mapping/", "analytics/api/nfr/"),
    ".yaml": YAML_DIRS,
    ".yml": YAML_DIRS,
    ".json": ("analytics/api/event/", "analytics/integration/event/"),
    ".dbml": ("analytics/db/data-model/",),
    ".sql": ("analytics/db/ddl/", "analytics/db/dml/"),
}


def rel_tree_path(path):
    p = path.replace("\\", "/")
    # Relativize against the template root first: the module directory itself is
    # …/modules/analytics, so an absolute file_path (Claude Code's default) would
    # otherwise let the module's own `analytics/` component pose as the final-tree
    # root — double-counting `analytics/` or flagging module files (README.md,
    # scripts/…) as misplaced final artifacts.
    root = _lib.root().replace("\\", "/").rstrip("/")
    pl, rl = p.lower(), root.lower()
    if root and (pl == rl or pl.startswith(rl + "/")):
        p = p[len(root):].lstrip("/")
    match = TREE_RE.search(p)
    return p[match.start():].lstrip("/") if match else ""


def read_target(rel):
    target = os.path.join(_lib.root(), *rel.split("/"))
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as handle:
            return target, handle.read()
    except OSError:
        return target, None


def structure_issues(rel):
    issues = []
    segments = rel.split("/")
    name = segments[-1]
    for segment in segments[:-1]:
        if not (KEBAB_RE.match(segment) or segment in DIR_EXCEPTIONS):
            issues.append(f"каталог не в kebab-case: {segment!r}")
    ext = os.path.splitext(name)[1].lower()
    allowed = PLACEMENT.get(ext)
    if allowed is None:
        issues.append(f"неожиданный тип файла: {name}")
        return issues
    if not any(rel.startswith(prefix) for prefix in allowed):
        issues.append(f"{name}: файл {ext} не размещается в {os.path.dirname(rel)}/")
    if ext in (".adoc", ".puml") and not UPPER_CAMEL_RE.match(name):
        issues.append(f"имя не UpperCamelCase: {name}")
    return issues


def content_issues(rel, text):
    if text is None:
        return []
    ext = os.path.splitext(rel)[1].lower()
    issues = []
    if ext == ".puml":
        if "@startuml" not in text or "@enduml" not in text:
            issues.append("нет пары @startuml/@enduml")
    elif ext == ".json":
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            issues.append(f"невалидный JSON: {exc}")
    elif ext == ".adoc":
        if not text.lstrip("﻿\r\n\t ").startswith("="):
            issues.append("нет заголовка AsciiDoc (=)")
        if "```" in text or MD_HEADING_RE.search(text):
            issues.append("Markdown-синтаксис в AsciiDoc")
        if not CYRILLIC_RE.search(text):
            issues.append("документ должен быть на русском")
    return issues


def validator_issues(rel, target):
    issues = []
    config = _lib.load_quality_gates()
    for spec in config.get("final_validators", []):
        if not isinstance(spec, dict):
            continue
        command = str(spec.get("command", "")).strip()
        if not command:
            continue  # unconfigured = silent allow
        globs = spec.get("applies_to", [])
        if globs and not _lib.matches_globs(rel, globs):
            continue
        try:
            timeout = max(1, int(spec.get("timeout", 60)))
        except (TypeError, ValueError):
            timeout = 60
        rc, tail = _lib.run_command(command, timeout, [target])
        name = str(spec.get("name", "validator"))
        if rc == -1:
            _lib.journal_skip("gate_final_format", f"{name}: {tail}")
        elif rc == -2:
            _lib.journal_skip("gate_final_format", f"{name} timed out")
        elif rc != 0:
            issues.append(f"{name} (rc={rc}): {tail}")
    return issues


def run(event):
    rel = rel_tree_path(_lib.path_from_event(event))
    if not rel or rel.endswith(".gitkeep"):
        return {"decision": "allow"}
    issues = structure_issues(rel)
    target, text = read_target(rel)
    issues.extend(content_issues(rel, text))
    if not issues:
        issues.extend(validator_issues(rel, target))
    if issues:
        return {"decision": "block",
                "reason": f"Финальный артефакт {rel}: " + "; ".join(issues)}
    return {"decision": "allow"}


def main():
    # Match the router's idiom: sys.stdout may use a legacy console code page
    # (e.g. cp1251 on Windows) that cannot encode the Cyrillic reason strings.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
