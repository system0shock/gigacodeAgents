#!/usr/bin/env python3
"""Out-of-band manager for the S2 control-plane integrity baseline.

Human-only (the agent cannot run it — git_guard blocks any command naming a
.gigacode path, exactly like confirm.py). Run it after any intended change to
enforcement code/config so the Stop-time gate_integrity baseline stays current.

Usage:
  python .gigacode/hooks/integrity.py generate   # write .gigacode/integrity.manifest
  python .gigacode/hooks/integrity.py verify      # exit 0 if pristine, 1 + report otherwise
"""
import os
import sys

_HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HOOKS, "gates"))
import gate_integrity as gi  # noqa: E402
import _lib  # noqa: E402


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "generate"
    gig = os.path.join(_lib.root(), ".gigacode")
    manifest_path = os.path.join(gig, gi.MANIFEST_NAME)
    if cmd == "generate":
        mapping = gi.compute(gig)
        with open(manifest_path, "w", encoding="utf-8") as fh:
            fh.write(gi.render_manifest(mapping))
        print(f"integrity baseline written: {manifest_path} ({len(mapping)} files)")
        return 0
    if cmd == "verify":
        res = gi.run({"hook_event_name": "Stop"})
        print(res.get("reason", res["decision"]))
        return 0 if res["decision"] == "allow" else 1
    print("usage: integrity.py [generate|verify]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
