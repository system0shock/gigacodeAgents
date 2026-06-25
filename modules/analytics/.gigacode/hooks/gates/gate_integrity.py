#!/usr/bin/env python3
"""gate_integrity (Stop): S2 — control-plane integrity backstop (defense-in-depth).

Catches tampering of enforcement files via channels that bypass PreToolUse — a
future MCP tool not yet in the router TOOL_NAME_MAP, or one that fires no
PreToolUse hook at all. The known channels (Bash, Write/Edit, Serena MCP) are
already covered by git_guard at write time (S1); this is the channel-independent
backstop, in the same spirit as gate_stage_order's Stop-invariant.

Anchor: a sha256 manifest (.gigacode/integrity.manifest) generated OUT OF BAND by
a human via `python .gigacode/hooks/integrity.py generate` (git_guard blocks the
agent from running it, exactly like confirm.py). At Stop the gate recomputes the
hashes of the enforcement file set and BLOCKS on any mismatch / missing / extra.

Fail-open: with no manifest it ALLOWS and notes the absence — a fresh deploy
runs, and S2 activates the moment a baseline is generated.

Residual (documented, per the structural-over-patching principle — see the
security feedback memory): an unknown channel that can rewrite an enforcement
file AND the manifest in the same session defeats any in-band integrity check
(it could equally just disable this gate). The manifest lives under .gigacode,
which git_guard protects, so no *known* channel can forge it; S2 raises the bar
for unknown ones and makes any tampering visible in the journal.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

MANIFEST_NAME = "integrity.manifest"
# Runtime state and caches change every run by design — never part of the baseline.
_EXCLUDE_DIRS = ("logs", "approvals", "__pycache__")
# Enforcement is code + config; .jsonl journals and .ok markers are excluded by ext.
_INCLUDE_EXT = (".py", ".cjs", ".json")


def enforcement_files(gig_dir):
    """Sorted enforcement-file paths relative to gig_dir (forward slashes). The
    generator and the gate MUST share this set or the baseline drifts."""
    out = []
    for dirpath, dirnames, filenames in os.walk(gig_dir):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
        for fn in filenames:
            if fn == MANIFEST_NAME or not fn.endswith(_INCLUDE_EXT):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), gig_dir)
            out.append(rel.replace(os.sep, "/"))
    return sorted(out)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute(gig_dir):
    """rel_path -> sha256 over the current enforcement file set."""
    return {rel: _sha256(os.path.join(gig_dir, rel)) for rel in enforcement_files(gig_dir)}


def load_manifest(path):
    out = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            digest, _, rel = line.partition("  ")
            if rel:
                out[rel.strip()] = digest.strip()
    return out


def render_manifest(mapping):
    header = ["# control-plane integrity manifest (S2). DO NOT edit by hand.",
              "# Regenerate out-of-band after any enforcement change:",
              "#   python .gigacode/hooks/integrity.py generate"]
    body = [f"{mapping[rel]}  {rel}" for rel in sorted(mapping)]
    return "\n".join(header + body) + "\n"


def diff(gig_dir, manifest_path):
    """List of human-readable problems; empty when the tree matches the baseline."""
    expected = load_manifest(manifest_path)
    actual = compute(gig_dir)
    problems = []
    for rel, digest in expected.items():
        if rel not in actual:
            problems.append(f"missing: {rel}")
        elif actual[rel] != digest:
            problems.append(f"modified: {rel}")
    for rel in actual:
        if rel not in expected:
            problems.append(f"untracked enforcement file: {rel}")
    return sorted(problems)


def run(event):
    if event.get("hook_event_name") != "Stop":
        return {"decision": "allow"}
    gig = os.path.join(_lib.root(), ".gigacode")
    manifest_path = os.path.join(gig, MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        return {"decision": "allow",
                "reason": "integrity baseline absent — S2 inactive. "
                          "Generate via `python .gigacode/hooks/integrity.py generate`."}
    problems = diff(gig, manifest_path)
    if problems:
        return {"decision": "block",
                "reason": "Control-plane integrity violation — enforcement files changed "
                          "outside the out-of-band workflow: " + "; ".join(problems[:8])
                          + (" (+more)" if len(problems) > 8 else "")
                          + ". Revert the change, or — if intended — regenerate the baseline "
                          "via `python .gigacode/hooks/integrity.py generate`."}
    return {"decision": "allow"}
