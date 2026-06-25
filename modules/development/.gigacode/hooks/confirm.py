#!/usr/bin/env python3
"""confirm.py: out-of-band HUMAN approval recorder for stage transitions.

Writes an approval marker the AGENT cannot create (.gigacode/** is blocked for
agent writes/commands by git_guard), so approval cannot be self-granted (P6).
v1 marker is a timestamped JSON file; an HMAC stamp slots in here later
(WI-7/WI-21) without changing gate_stage_order's predicate contract.

Usage:  python .gigacode/hooks/confirm.py <stage> <slug>
"""
import json
import os
import sys
import time

ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
APPROVALS = os.path.join(ROOT, ".gigacode", "approvals")


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: confirm.py <stage> <slug>\n")
        return 2
    stage, slug = argv
    if not stage.isidentifier() and not stage.replace("-", "").isalnum():
        sys.stderr.write("invalid stage name\n")
        return 2
    if not slug.replace("-", "").replace("_", "").isalnum():
        sys.stderr.write("invalid slug\n")
        return 2
    out_dir = os.path.join(APPROVALS, slug)
    os.makedirs(out_dir, exist_ok=True)
    marker = os.path.join(out_dir, stage + ".ok")
    with open(marker, "w", encoding="utf-8") as handle:
        json.dump({"stage": stage, "slug": slug,
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "by": os.environ.get("USER")
                   or os.environ.get("USERNAME", "unknown")},
                  handle, ensure_ascii=False)
    sys.stdout.write("approved: %s / %s -> %s\n"
                     % (stage, slug, os.path.relpath(marker, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
