# GigaCode Developer Flow Enforcement Design

## Goal

Harden the GigaCode developer template so that agents stop ignoring existing
code and stop producing files that do not follow the project specification
format. The current developer design (`docs/superpowers/specs/2026-05-17-gigacode-developer-template-design.md`)
relies almost entirely on *advisory* instructions in the skill and agent
prompts. Agents drift away from those instructions, which is the root cause of
the two reported problems.

This design adds an **enforcement layer** (a hook router plus single-purpose
quality gates), adopts the **OpenSpec** specification format with machine
validation, and integrates **context-providing MCP servers** so existing code
is discoverable and library APIs are accurate.

Scope for this design is the **developer template first**. The analyst template
reuses the same shared mechanisms in a later iteration.

## Problems Addressed

1. **Agents ignore existing code and write new implementations.**
   Cause: "code is the source of truth" and "map code before editing" are only
   text in the skill/agents. There is no semantic code index that makes existing
   symbols cheaply discoverable, no mechanical anti-duplication check, and read
   context is lost on compaction.

2. **Agents produce files that do not follow the spec format.**
   Cause: specs are bespoke Markdown under `docs/superpowers/specs`, which is not
   machine-validatable. The existing `validate_development_output.py` checks task
   artifacts, not the structure of the specs that drive the work.

## Confirmed Runtime Substrate: Qwen Code Hooks

GigaCode is a fork of Qwen Code. Qwen Code provides a rich, Claude-Code-compatible
hook system. This removes the hedging in the prior developer design ("if hook
semantics cannot intercept a specific operation"). The relevant facts the design
relies on:

- **14 hook events**, including `UserPromptSubmit`, `SessionStart`,
  `SubagentStart`, `SubagentStop`, `PreToolUse`, `PostToolUse`, `Stop`,
  `PreCompact`, `PostCompact`.
- Command hooks receive **input JSON on stdin** containing at least
  `hook_event_name`, `session_id`, `cwd`, `permission_mode`, and for tool events
  `tool_name`, `tool_input`, `tool_use_id` (and `tool_response` for `PostToolUse`).
- **Control via exit code**: `0` = success (parse stdout JSON for control),
  `2` = blocking error (stdout ignored, stderr returned as feedback), other =
  non-blocking.
- **Control via stdout JSON**: `continue`, `decision` (`allow|deny|block|ask`),
  `reason`, `systemMessage`, and `hookSpecificOutput`. For `PreToolUse`,
  `hookSpecificOutput` carries `permissionDecision` (`allow|deny|ask`),
  `permissionDecisionReason`, `updatedInput` (modify tool parameters), and
  `additionalContext` (inject text into the conversation).
- **Matchers** are regex against the tool name (tool events), the agent type
  (`SubagentStart`/`SubagentStop`), the source (`SessionStart`), or exact match
  (`PreCompact`, `Notification`). `UserPromptSubmit` and `Stop` take no matcher.
- Known tool names include `Bash`, `WriteFile`, `ReadFile`, `Edit`, `Explorer`,
  `Plan`, `Task`, `Shell`.
- Hooks run in parallel by default; `sequential: true` enforces order and lets a
  hook modify input for subsequent hooks; `async: true` runs in background;
  `disableAllHooks: true` is the global off switch.

All hook tool names, JSON field names, and event names in this design follow the
Qwen Code documentation. If a future GigaCode fork renames or removes an event,
the affected gate degrades to an instruction embedded in the skill/agent prompt
(defense in depth), consistent with the prior design's stance.

## Event-to-Mechanism Map

| Event (matcher) | Mechanism | Control used |
|---|---|---|
| `UserPromptSubmit` | preflight validation + rule injection | `decision: block` / `additionalContext` |
| `SessionStart` | inject coding/test rules + module index | `additionalContext` |
| `SubagentStart` (`coder`) | inject rules + discovered existing code for the implementer | `additionalContext` |
| `PreToolUse` (`WriteFile\|Edit`) | existing-code gate, spec-structure gate | `permissionDecision: deny` / `updatedInput` / `additionalContext` |
| `PreToolUse` (`^Bash$`) | git guard | `permissionDecision: deny` |
| `PostToolUse` (`WriteFile\|Edit`) | lint + clean-code on changed files | `decision: block` |
| `Stop` | build gate + artifact validation before PR readiness | `decision: block` |
| `SubagentStop` | validate the subagent's output | `decision: block` |

## Architecture

### 0. Enforcement Hierarchy (revision 2026-06-10)

Context injection is the primary mechanism: the cheapest place to stop a
violation is before generation, by making existing code and rules visible to
the agent up front. Blocking gates are the backstop. Only deterministic checks
may block (git safety, `openspec validate`, build, lint on changed files).
Heuristic checks (duplicate detection, clean-code) are **advisory-only**: they
inject warnings via `additionalContext`, never deny, until data from the
decision journal justifies promoting a specific rule to blocking.

### 1. Hook Router

A single dispatcher script, `.gigacode/hooks/router.py`, is registered in
`.gigacode/settings.json` for every relevant `(event, matcher)` pair. It is the
only script wired into the hook configuration.

Responsibilities:

- Read the event JSON from stdin.
- Read `hook_event_name`, `tool_name`, `tool_input`, `cwd`, `permission_mode`,
  and (when present) the agent type.
- Look up matching gates in a **config table**, `.gigacode/hooks/router.config.json`,
  which maps `(event, tool/agent/path/command pattern)` to an ordered list of
  gate scripts.
- Run each matching gate, passing the original event JSON through.
- Aggregate gate results: any `deny`/`block` wins; `additionalContext` and
  `systemMessage` fragments are concatenated; `updatedInput` from the last gate
  that sets it is used (gates that rewrite input must be marked `exclusive` in
  config to avoid conflicting rewrites).
- Emit one combined JSON decision (and the correct exit code) back to GigaCode.

Design constraints:

- The router file must stay below 10,000 characters. All matching/aggregation
  logic that grows beyond that moves into a small shared helper module under
  `.gigacode/hooks/lib/`.
- The router contains **no gate-specific logic**. Adding a gate is a config
  edit plus a new gate file, never a router edit.
- The router must be safe by default: if a gate script crashes or times out, the
  router records the failure and, for safety-critical gates (git guard,
  spec-structure), treats the failure as a soft block with a clear
  reason rather than silently allowing the action. Every soft-block reason must
  name the escape hatch (`disableAllHooks`) so a broken Python environment never
  leaves the template unusable without explanation.
- The router reads stdin as `utf-8-sig`: PowerShell pipes prepend a UTF-8 BOM
  that breaks naive `json.load`, and a parse failure must never silently allow
  (this exact bug made `git_guard` a no-op on Windows before 2026-06-10).
- The router appends every decision (event, gate, verdict, reason) to
  `.gigacode/hooks/decisions.jsonl`. This journal is the data source for tuning
  advisory rules and false-positive rates.
- Stop-loop protection: a gate may block a `Stop` event at most twice per
  session; the third trigger degrades to a warning with a report. Without this,
  build/artifact gates can trap the agent in an infinite stop-fix-stop loop.
- Latency budget: `PreToolUse` handling (router + matching gates) stays under
  200 ms; matchers in the config table are narrow so the router is not spawned
  for irrelevant tools.

### 2. Quality Gates

Single-purpose scripts under `.gigacode/hooks/gates/`. Each gate reads the event
JSON on stdin and returns a gate result (decision, reason, optional
`additionalContext`/`updatedInput`). Gates are independently testable with sample
JSON and have no knowledge of the router's aggregation.

| Gate | Trigger | Purpose | Problem |
|---|---|---|---|
| `gate_context_inject` | `SessionStart`, `SubagentStart`, `UserPromptSubmit` | Inject coding rules, test rules, and a module/symbol index so the agent starts grounded | 1 |
| `gate_existing_code` | `PreToolUse` on `WriteFile`/new-file `Edit` | Detect symbol-name collisions and near-duplicate blocks against the existing tree; **advisory-only**: inject "this already exists at X" via `additionalContext`, never deny (promotion to blocking requires decision-journal evidence) | 1 |
| `gate_spec_structure` | `PreToolUse`/`PostToolUse` on writes under `openspec/` or `docs/development/<task>/` | Run OpenSpec validation; block on structure violations and unresolved placeholders | 2 |
| `gate_lint` | `PostToolUse` on changed code files | Run the project linter on changed files only | quality |
| `gate_build` | `Stop` / before PR readiness | Run the project build/compile check | quality |
| `gate_clean_code` | `PostToolUse` / `Stop` | Heuristics: file size, function length, duplication, residual `TODO`/`FIXME` | quality |
| `git_guard` | `PreToolUse` on `Bash` | Existing git-safety rules (protected branches, destructive ops, protected paths) | safety |
| `preflight` | `UserPromptSubmit` | Existing developer-prompt validation | safety |
| `validate_development_output` | `Stop` / `SubagentStop` | Existing artifact-completion validation | safety |

`git_guard`, `preflight`, and `validate_development_output` from the prior design
are **refactored into gates behind the router**, not kept as separate hook
entries. Their rules are unchanged; only their invocation path changes.

### 3. Language-Agnostic Gate Configuration

The template is language-agnostic. `gate_lint`, `gate_build`, and the
configurable parts of `gate_clean_code` read their commands from
`.gigacode/quality-gates.json`, for example:

```json
{
  "lint": { "command": "npm run lint --", "applies_to": ["**/*.ts", "**/*.tsx"] },
  "build": { "command": "npm run build" },
  "clean_code": { "max_file_lines": 400, "max_function_lines": 60 }
}
```

If a command is not configured, the gate returns **skip-with-record**: it does
not block, and it records in the task's `verification.md` that the check was
skipped and why. This keeps smoke checks fully offline and keeps the template
usable in a repo before any project commands are wired up.

### 4. Performance Discipline

Gates must not make every tool call slow:

- `gate_build` runs only on `Stop`/PR readiness, never per edit.
- `gate_lint` and `gate_clean_code` run only on **changed files**.
- `gate_existing_code` scopes its search to plausible locations (same package,
  same symbol kind) rather than the whole tree, and prefers the Serena MCP index
  when available, falling back to `rg`/symbol search.
- Long checks may use `async: true` where a blocking decision is not required.

### 5. MCP Integration

MCP servers are **optional supporting context** and are never required for smoke
checks. They are declared in `.gigacode/settings.json` with an allowlist; the
template documents setup but does not ship credentials.

- **Serena MCP (priority 1).** Semantic code search and symbol navigation.
  Agent prompts are updated so that, before proposing any new function, type, or
  file, the agent must search for an existing implementation through Serena.
  `gate_existing_code` prefers Serena's index when present. This is the most
  direct lever on problem 1. Before Phase 4 builds on it, Serena must be
  installed and exercised end-to-end once (Java via Eclipse JDT LS is mature;
  Kotlin LSP support is weaker and must be verified on real project code).
- **Graphify (priority 2, skill not MCP).** Repository knowledge graph; its
  JSON output feeds `gate_context_inject` as a module/relationship map. For
  event-driven codebases it covers what symbol search cannot: producer ->
  topic -> consumer flows.
- **Context7 (priority 3).** Up-to-date library/framework documentation, to
  reduce API hallucination when new code is genuinely needed.

When a server is unavailable, the workflow continues with `rg`/symbol search and
user-provided context, and records the limitation, exactly like the existing
Graphify fallback policy.

### 6. OpenSpec Adoption (Full Tool)

The project adopts OpenSpec as the specification engine.

- Initialize with `openspec init`, producing the `openspec/` tree:

  ```text
  openspec/
    project.md
    specs/
      <capability>/spec.md        # current truth, per capability
    changes/
      <change-id>/
        proposal.md               # why + what
        tasks.md                  # implementation checklist
        design.md                 # technical approach
        specs/<capability>/spec.md  # delta (ADDED/MODIFIED/REMOVED)
      archive/
  ```

- Migrate the two existing designs (analyst and developer templates) into
  `openspec/specs/` as current-truth capabilities, and convert this enforcement
  work into an `openspec/changes/<id>/` proposal.
- `gate_spec_structure` runs `openspec validate --strict` as its engine.
- The `/develop-feature` and `/fix-bug` commands wrap the OpenSpec cycle
  (propose -> apply -> archive). Developer task artifacts under
  `docs/development/<task-slug>/` are retained for human-facing run notes; the
  authoritative spec lives in `openspec/`.
- Run notes are three files (revision 2026-06-10): `journal.md` (context,
  impact map, plan, implementation notes), `verification.md`, `pr-summary.md`.
  The earlier five-file scheme duplicated OpenSpec content and taxed every
  small fix. Legacy designs under `docs/superpowers/` are archived as-is once
  migrated into `openspec/specs/`.

### 7. Agent Pipeline (revision 2026-06-10)

The developer template runs three agents instead of the original seven:
`repo-context` (project intelligence + impact map, including event flows),
`coder` (scoped edits), `verifier` (verification evidence + PR notes). Intake
stays in the main session because only the main session can ask the user
questions; implementation planning lives in the OpenSpec change artifacts.
Fewer handoffs mean less context loss between subagents — the enforcement
layer, not pipeline structure, now carries the discipline.

**Residual compatibility risk to verify in Phase 1 (cheap check):** OpenSpec
natively generates slash commands and agent instructions for some tools
(Claude, Copilot). It may not generate them for Qwen/GigaCode. If it does not,
`/opsx`-style commands are **not** free: the `openspec` CLI is used as the
engine, and `.gigacode/commands/*` are hand-authored wrappers that call the CLI.
This does not change the architecture or the plan; it only changes how much
command scaffolding is generated versus hand-written.

## Phased Plan

Each phase is its own OpenSpec change with its own smoke checks.

- **Phase 0 — Substrate verification.** Done: the Qwen Code hook model is
  confirmed and documented above.
- **Phase 1 — OpenSpec.** Run `openspec init`; verify the GigaCode command
  compatibility question above; migrate the two existing specs into
  `openspec/specs/`; record this enforcement work as a change; update README and
  conventions. Addresses problem 2 at the format level.
- **Phase 2 — Serena MCP.** Declare Serena in `settings.json`; update agent
  prompts to require searching for existing code through Serena before proposing
  new code. Fast, high-impact strike on problem 1.
- **Phase 3 — Hook router.** Step 0: run a logging-only hook against a live
  GigaCode build to confirm real event and tool names before anything is wired
  (the hook model above is documented Qwen behavior; fork drift is a real
  risk). Then build `router.py` and `router.config.json`; move `git_guard`,
  `preflight`, and `validate_development_output` behind the router with narrow
  matchers; add smoke tests that feed sample event JSON for each registered
  `(event, matcher)`.
- **Phase 4 — Quality gates.** Implement `gate_context_inject`,
  `gate_existing_code`, `gate_spec_structure`, `gate_lint`, `gate_build`,
  `gate_clean_code`, wired through the router and `quality-gates.json`. Main
  strike on both problems at enforcement time.
- **Phase 5 — Context7 + Graphify.** Declare Context7 as an MCP server; wire
  Graphify output into `gate_context_inject`. Optional; document fallbacks.

## Settings

`.gigacode/settings.json` gains:

- One `hooks` block that registers `router.py` for each relevant `(event,
  matcher)` pair listed in the Event-to-Mechanism Map.
- An MCP allowlist entry for Serena (Phase 2), Context7 and context-mode
  (Phase 5).
- The existing permission and protected-path rules from the prior design.

`.gigacode/quality-gates.json` is new and holds language-specific commands and
clean-code thresholds. Neither file contains secrets, credentials, personal
paths, or mandatory MCP tokens.

## Smoke Checks

The existing `scripts/smoke-check.ps1` and `scripts/smoke-check.sh` are extended
to verify, without GigaCode, MCP, or network access:

- `router.py` and every gate execute against sample event JSON and return
  well-formed decisions.
- `router.config.json` references only gate files that exist.
- `git_guard` still blocks protected-branch commit scenarios in dry-run samples.
- `gate_spec_structure` fails a deliberately malformed OpenSpec fixture and
  passes a valid one. If the `openspec` CLI is unavailable in the check
  environment, this assertion is skipped-with-record rather than failing the
  suite.
- Unconfigured `gate_lint`/`gate_build` return skip-with-record, not a block.
- Hooks parse BOM-prefixed stdin (`utf-8-sig`) — PowerShell pipe samples.
- A missing or crashing gate script produces a soft block with a reason naming
  the escape hatch, never a silent allow.
- Stop-loop protection: the third consecutive `Stop` block from the same gate
  degrades to a warning in the sample run.
- Router decisions are appended to `decisions.jsonl`.
- `PreToolUse` routing latency is measured and stays under the 200 ms budget.
- `router.py` and each gate file stay below 10,000 characters.

## Out of Scope

- Applying these mechanisms to the analyst template (a later iteration).
- **context-mode (dropped 2026-06-10).** Its unique value is output compression
  and surviving compaction, which addresses a problem not yet measured, and its
  `ctx_execute` would route shell commands around `git_guard`'s `^Bash$`
  matcher. Re-entry condition: if `decisions.jsonl` after Phases 3-4 shows
  sessions suffering from compaction or oversized build logs, add it back as an
  optional compressor with explicit git-command routing rules.
- **Repomix (dropped 2026-06-10).** Static snapshots go stale and duplicate
  Serena + Graphify + direct inspection.
- Shipping MCP credentials or auto-installing MCP servers.
- Auto-commit, auto-push, auto-PR (unchanged from the prior design).
- Guaranteeing OpenSpec native command generation for GigaCode (verified, not
  assumed, in Phase 1).

## Success Criteria

- A single `hook_router` dispatches all developer-flow hooks via a config table;
  adding a gate requires no router edit.
- `gate_existing_code` warns on duplicate symbols/blocks (advisory-only), and
  agents are instructed and able to find existing code through Serena before
  writing new code. Problem 1 is attacked primarily by context injection;
  `decisions.jsonl` provides the evidence base for any future promotion of the
  advisory gate to blocking.
- Specs live in an `openspec/` structure and `gate_spec_structure` blocks writes
  that fail `openspec validate --strict`. Problem 2 is enforced mechanically.
- `gate_lint`, `gate_build`, and `gate_clean_code` run on the right events,
  scoped to changed files, and skip-with-record when unconfigured.
- Serena, Graphify, and Context7 are integrated as optional context providers
  with documented fallbacks; none is required for smoke checks.
- Smoke checks pass offline on Windows and Linux shells.
- `router.py` and every gate file stay below 10,000 characters.
