#!/usr/bin/env python3
"""Stop gate: validate reverse-analysis run state from manifests + repo files."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

REQUIRED_TECHDOCS = ("overview.adoc", "flow.adoc", "integrations.adoc",
                     "data.adoc", "questions.adoc")
STATUSES = ("scoping", "draft", "confirmed", "complete")


def load_manifest(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def missing_files(root_dir, paths):
    missing = []
    for rel in paths:
        if not isinstance(rel, str) or not rel:
            continue
        if not os.path.exists(os.path.join(root_dir, *rel.replace("\\", "/").split("/"))):
            missing.append(rel)
    return missing


def check_feature(root_dir, feature_dir, manifest):
    name = os.path.basename(feature_dir)
    status = manifest.get("status", "")
    if status not in STATUSES:
        return [f"{name}: некорректный status {status!r} в manifest.json"]
    if status == "scoping":
        return []
    issues = []
    for doc in REQUIRED_TECHDOCS:
        if not os.path.exists(os.path.join(feature_dir, doc)):
            issues.append(f"{name}: отсутствует {doc}")
    if status in ("confirmed", "complete"):
        capability = str(manifest.get("capability", "")) or name
        spec_rel = f"openspec/specs/{capability}/spec.md"
        if not os.path.exists(os.path.join(root_dir, *spec_rel.split("/"))):
            issues.append(f"{name}: нет {spec_rel}")
    if status == "complete":
        produced = manifest.get("produced", {})
        if not isinstance(produced, dict):
            produced = {}
        for group in ("technical", "final"):
            for rel in missing_files(root_dir, produced.get(group, []) or []):
                issues.append(f"{name}: заявленный файл отсутствует: {rel}")
    return issues


def openspec_issue():
    config = _lib.load_quality_gates().get("openspec_validate", {})
    command = str(config.get("command", "")).strip() if isinstance(config, dict) else ""
    if not command:
        return ""
    try:
        timeout = max(1, int(config.get("timeout", 120)))
    except (TypeError, ValueError):
        timeout = 120
    rc, tail = _lib.run_command(command, timeout)
    if rc == -1:
        _lib.journal_skip("validate_run_output", f"openspec CLI unavailable: {tail}")
        return ""
    if rc == -2:
        _lib.journal_skip("validate_run_output", "openspec validate timed out")
        return ""
    return f"openspec validate failed: {tail}" if rc != 0 else ""


def run(event):
    root_dir = _lib.root()
    features_dir = os.path.join(root_dir, "docs", "features")
    issues = []
    needs_spec_check = False
    try:
        entries = sorted(os.listdir(features_dir))
    except OSError:
        entries = []
    for entry in entries:
        feature_dir = os.path.join(features_dir, entry)
        manifest_path = os.path.join(feature_dir, "manifest.json")
        if not os.path.isdir(feature_dir) or not os.path.exists(manifest_path):
            continue
        manifest = load_manifest(manifest_path)
        if manifest is None:
            issues.append(f"{entry}: manifest.json не читается или не объект")
            continue
        if manifest.get("status") in ("confirmed", "complete"):
            needs_spec_check = True
        issues.extend(check_feature(root_dir, feature_dir, manifest))
    if needs_spec_check and not issues:
        problem = openspec_issue()
        if problem:
            issues.append(problem)
    if issues:
        return {"decision": "block",
                "reason": "Прогон реверс-анализа не завершён: " + "; ".join(issues)}
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
