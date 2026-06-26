#!/usr/bin/env node
// Offline tests for run-hook.cjs interpreter selection + fail-closed behavior.
// Run:  node scripts/test_launcher.cjs
const path = require("path");
const hook = require(path.join(__dirname, "..", ".gigacode", "hooks", "run-hook.cjs"));

let passed = 0;
function check(name, cond, detail) {
  if (!cond) { console.error("FAIL " + name + (detail ? ": " + detail : "")); process.exit(1); }
  passed++; console.log("ok: " + name);
}

const ALLOW = Buffer.from('{"decision":"allow"}\n');
function shim() { return { status: 9009, stdout: Buffer.alloc(0), stderr: Buffer.from("Python was not found"), error: null }; }
function works() { return { status: 0, stdout: ALLOW, stderr: Buffer.alloc(0), error: null }; }
function enoent() { return { error: { code: "ENOENT" } }; }
function timedout() { return { error: { code: "ETIMEDOUT" }, signal: "SIGTERM" }; }

// Build an injected spawnSync that returns scripted results per invocation.
function seq(results) {
  let i = 0;
  return () => results[Math.min(i++, results.length - 1)];
}
function run(results, { event = "PreToolUse", platform = "win32" } = {}) {
  let out = "";
  const code = hook.main({
    spawnSync: seq(results),
    argv: ["--event", event],
    input: Buffer.from("{}"),
    stdout: (s) => { out += s; },
    stderr: () => {},
    platform,
    env: {},
  });
  return { out, code };
}

// 1. MS-Store shim first, real Python next -> must fall through to the working one.
const r1 = run([shim(), works()], { event: "PreToolUse" });
check("shim_then_working_uses_working", r1.out.includes('"decision":"allow"'), r1.out);

// 2. ENOENT first, working next -> fall through (existing behavior preserved).
const r2 = run([enoent(), works()], { event: "PreToolUse" });
check("enoent_then_working", r2.out.includes('"decision":"allow"'), r2.out);

// 3. All candidates are dead shims, gating event (PreToolUse) -> FAIL CLOSED (deny).
const r3 = run([shim(), shim(), shim()], { event: "PreToolUse" });
check("all_dead_pretooluse_fails_closed",
  r3.out.includes('"permissionDecision":"deny"') && r3.out.includes('"decision":"block"'), r3.out);

// 4. All dead shims, gating Stop -> FAIL CLOSED (block).
const r4 = run([shim(), shim(), shim()], { event: "Stop" });
check("all_dead_stop_fails_closed", r4.out.includes('"decision":"block"'), r4.out);

// 5. All dead shims, NON-gating event -> fail open (do not brick logging/context).
const r5 = run([shim(), shim(), shim()], { event: "PostToolUse" });
check("all_dead_nongating_fails_open", r5.out.trim() === "{}", r5.out);

// 6. Timeout (hang) on a gating event -> FAIL CLOSED, never silently allow.
const r6 = run([timedout()], { event: "Stop" });
check("timeout_stop_fails_closed", r6.out.includes('"decision":"block"'), r6.out);

console.log("\nAll " + passed + " launcher checks passed");
