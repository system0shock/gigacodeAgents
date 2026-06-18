#!/usr/bin/env node
// Cross-platform hook launcher. GigaCode/Qwen hook commands are a single string
// for every OS, but `python` is absent on macOS/Linux (python3) and `python3`
// is absent on Windows (python / py). Node is the GigaCode runtime, so it is the
// one interpreter guaranteed present: resolve a working Python here and exec the
// in-tree router, piping stdin/stdout/exit through unchanged.
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const router = path.join(__dirname, "router.py");
const args = process.argv.slice(2); // e.g. ["--event", "PreToolUse"]
let input;
try {
  input = fs.readFileSync(0); // stdin (fd 0)
} catch (e) {
  process.stderr.write("run-hook: stdin read failed: " + String(e) + "\n");
  input = Buffer.alloc(0);
}

// Windows: try `python` (real install) and the `py` launcher before `python3`,
// whose Microsoft Store alias can hang opening the Store instead of running.
const candidates =
  process.platform === "win32"
    ? [["python"], ["py", "-3"], ["python3"]]
    : [["python3"], ["python"]];

const env = { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };

for (const [cmd, ...pre] of candidates) {
  // timeout bounds a pathological hang (e.g. a Windows MS-Store `python3` alias
  // opening the Store); 630s matches the Stop hook budget so it never kills a
  // legitimate long gate run. On timeout spawnSync sets r.error -> fail-open below.
  const r = spawnSync(cmd, [...pre, router, ...args], { input, env, timeout: 630000 });
  if (r.error && r.error.code === "ENOENT") continue; // not installed; try next
  if (r.error) {
    process.stderr.write("run-hook: " + String(r.error) + "\n");
    process.stdout.write("{}\n");
    process.exit(0);
  }
  if (r.stdout && r.stdout.length) process.stdout.write(r.stdout);
  if (r.stderr && r.stderr.length) process.stderr.write(r.stderr);
  process.exit(r.status == null ? 0 : r.status);
}

// No interpreter found: do NOT brick the session. Warn loudly; allow.
process.stderr.write(
  "run-hook: no Python 3 found (tried " +
    candidates.map((c) => c.join(" ")).join(", ") +
    "). GigaCode enforcement is OFF until Python 3 is on PATH.\n"
);
process.stdout.write("{}\n");
process.exit(0);
