#!/usr/bin/env node
// Cross-platform hook launcher. GigaCode/Qwen hook commands are a single string
// for every OS, but `python` is absent on macOS/Linux (python3) and `python3`
// is absent on Windows (python / py). Node is the GigaCode runtime, so it is the
// one interpreter guaranteed present: resolve a WORKING Python here and exec the
// in-tree router, piping stdin/stdout/exit through unchanged.
//
// Security posture: router.py ALWAYS prints a JSON decision to stdout and exits 0
// (even its error paths emit a block + return). So "this interpreter actually ran
// the router" == it produced non-empty stdout. A candidate that exits without any
// stdout (notably the Windows Microsoft-Store App-Execution-Alias shim, which
// exits 9009 with empty stdout and does NOT raise ENOENT) is a dead interpreter:
// we must try the next candidate, not accept its silence as "allow". If NO
// interpreter runs the router — or a run times out — gating events (PreToolUse,
// Stop) FAIL CLOSED (block) instead of silently allowing an unguarded action or a
// forged completion. Non-gating events fail open so a bad deploy never bricks
// context injection / logging.
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROUTER = path.join(__dirname, "router.py");

// Events whose whole purpose is to STOP something dangerous. If the engine cannot
// run, these block; everything else (SessionStart/PostToolUse/UserPromptSubmit/…)
// allows so a missing interpreter cannot brick the session outright.
const GATING = new Set(["PreToolUse", "Stop"]);

// Sequential build+test on Stop can each take up to ~620s (their gate ceilings),
// so the launcher budget must exceed their SUM, not a single command. Below this,
// a normal slow build+test would time out and (now) fail closed — block a
// legitimate Stop. 1260s > 620+620.
const DEFAULT_TIMEOUT_MS = 1260000;

function eventName(argv) {
  const i = argv.indexOf("--event");
  return i >= 0 && argv[i + 1] ? argv[i + 1] : "";
}

function failClosedDecision(event, reason) {
  if (event === "PreToolUse") {
    return JSON.stringify({
      decision: "block",
      reason,
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: reason,
      },
    }) + "\n";
  }
  return JSON.stringify({ decision: "block", reason }) + "\n";
}

// A finished spawn "ran the router" iff it produced a decision on stdout.
function ranRouter(r) {
  return !r.error && r.stdout && r.stdout.length > 0;
}

function main(opts) {
  opts = opts || {};
  const spawn = opts.spawnSync || spawnSync;
  const argv = opts.argv || process.argv.slice(2); // e.g. ["--event","PreToolUse"]
  const out = opts.stdout || ((s) => process.stdout.write(s));
  const err = opts.stderr || ((s) => process.stderr.write(s));
  const platform = opts.platform || process.platform;
  const timeout = opts.timeout || DEFAULT_TIMEOUT_MS;
  let input = opts.input;
  if (input === undefined) {
    try {
      input = fs.readFileSync(0); // stdin (fd 0)
    } catch (e) {
      err("run-hook: stdin read failed: " + String(e) + "\n");
      input = Buffer.alloc(0);
    }
  }

  const event = eventName(argv);
  // Windows: try `python` and the `py` launcher before `python3`, whose MS-Store
  // alias can hang opening the Store instead of running.
  const candidates =
    platform === "win32"
      ? [["python"], ["py", "-3"], ["python3"]]
      : [["python3"], ["python"]];
  const env = { ...(opts.env || process.env), PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" };

  let timedOut = false;
  for (const [cmd, ...pre] of candidates) {
    const r = spawn(cmd, [...pre, ROUTER, ...argv], { input, env, timeout });
    if (r.error && r.error.code === "ENOENT") continue; // not installed; try next
    if (r.error && (r.error.code === "ETIMEDOUT" || r.signal === "SIGTERM")) {
      // a run hung (e.g. build+test overran the budget) — do not try another
      // interpreter on the same hang; fail closed below.
      timedOut = true;
      break;
    }
    if (r.error) {
      // other spawn error: record and try the next candidate.
      err("run-hook: " + String(r.error) + "\n");
      continue;
    }
    if (ranRouter(r)) {
      out(r.stdout.toString());
      if (r.stderr && r.stderr.length) err(r.stderr.toString());
      return r.status == null ? 0 : r.status;
    }
    // Ran but produced no decision (dead shim: nonzero exit, empty stdout). The
    // router never does this, so the interpreter didn't run it — try the next.
    if (r.stderr && r.stderr.length) err(r.stderr.toString());
  }

  // No interpreter produced a decision, or a run hung. Fail CLOSED for gating
  // events; open (with a loud warning) for the rest.
  const why = timedOut
    ? "GigaCode: enforcement hook timed out; blocking for safety. Re-run, or raise the gate timeout if the build/test is legitimately long."
    : "GigaCode: no working Python 3 found (tried " +
      candidates.map((c) => c.join(" ")).join(", ") +
      "). Enforcement cannot run — install Python 3 on PATH. Gating actions are blocked for safety.";
  err("run-hook: " + why + "\n");
  if (GATING.has(event)) {
    out(failClosedDecision(event, why));
  } else {
    out("{}\n");
  }
  return 0;
}

module.exports = { main, failClosedDecision, ranRouter, eventName, GATING };

if (require.main === module) {
  process.exit(main({}));
}
