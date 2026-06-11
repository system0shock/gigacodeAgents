# GigaCode Analytics Flow Overhaul Design

## Goal

Overhaul the analyst template's reverse-analysis flow (`modules/analytics/` on
`feature/analytics-template`) so that it matches the dev-flow enforcement
standard (hook router + quality gates, OpenSpec, context providers) and so that
its final deliverables follow the corporate documentation standard (type-based
`analytics/` + `architecture/` tree, multi-format artifacts).

The defining insight of this design: **reverse analysis is a one-time bootstrap
per feature.** It creates the documentation baseline from existing code. After
the bootstrap, documentation evolves through the normal OpenSpec change
lifecycle (a future, separate flow). Everything below follows from that.

Prior design: `docs/superpowers/specs/2026-05-17-gigacode-analyst-template-design.md`
(generation 1, May 2026). Reference standard:
`docs/superpowers/specs/2026-06-07-gigacode-dev-flow-enforcement-design.md` and
its implementation on `feature/dev-flow-enforcement` (PR #1).

## Problems Addressed

1. **No machine-validatable artifacts.** Scope brief and code map live only in
   chat and die with the session. Nothing in the flow can be checked by
   automation.
2. **Output contract mismatch.** The flow produces 5 fixed AsciiDoc files per
   feature; the corporate standard requires a type-organized, multi-format tree
   (AsciiDoc, PlantUML C4, DBML, SQL, OpenAPI, AsyncAPI, JSON Schema) with
   `UpperCamelCase` file names and `kebab-case/` directories.
3. **Generation-1 hook layer.** Two standalone hooks wired directly into
   settings: BOM on stdin silently disables validation (`json.loads` throws,
   hook answers `allow`), `Stop` blocking has no retry budget (loop risk),
   output validation sniffs `last_assistant_message` substrings instead of
   checking repo state, no decisions journal, no git guard at all.
4. **Intake-subagent anti-pattern.** `intake-scope` is a subagent whose job is
   asking the user questions; only the main session can hold a dialogue. The
   same flaw was already identified and fixed in the dev-flow (2026-06-10 agent
   review).

## Decision 1: Two-Layer Output Contract

### Technical layer — bootstrap snapshot

The 5-document structure survives as the **working layer** under
`docs/features/<feature-name>/` (file names stay lowercase and fixed — the
corporate naming convention applies to the final tree only):

- `overview.adoc`, `flow.adoc`, `integrations.adoc`, `data.adoc`,
  `questions.adoc` — Russian AsciiDoc with evidence labels
  (`Источник: код|jira|confluence|пользователь`, `Статус: предположение|открытый вопрос`).
- A run journal `journal.md` (scope brief, code map, decisions) and a run
  manifest `manifest.json` (see Decision 5) live in the same directory.

Lifecycle: drafted during the run, evidence-reviewed, then **frozen**. Each
file carries a metadata header: feature, run date, code commit, links to the
produced final artifacts, and the note that this is a primary reverse-analysis
artifact whose current state lives in the final documentation and
`openspec/specs/`. The technical layer is never updated after the run; the
final tree is expected to evolve past it through the change lifecycle. No
freshness gates — divergence after bootstrap is the norm, not an error.

The evidence layer (assumptions, open questions, contradictions) lives **only**
here. `questions.adoc` has no final-tree counterpart by design.

### Final layer — corporate documentation tree

Generated at the repository root of the analyzed project:

```text
architecture/                       # PlantUML C4 + sequence diagrams (.puml)
analytics/
├── db/
│   ├── ddl/                        # not populated by bootstrap (change-cycle artifact)
│   ├── dml/                        # not populated by bootstrap (change-cycle artifact)
│   └── data-model/                 # DBML model of existing schema
├── functional-requirements/        # .adoc, derived from openspec spec
├── integration/                    # external APIs
│   ├── event/                      # AsyncAPI .yaml
│   ├── rest/                       # OpenAPI .yaml
│   ├── mapping/                    # service-to-DB mapping .adoc
│   └── nfr and contact/            # NFR + neighbor-team contacts .adoc
├── api/                            # internal APIs
│   ├── event/                      # AsyncAPI .yaml
│   ├── rest/public/ , rest/private/  # OpenAPI .yaml
│   ├── mapping/
│   └── nfr/
├── use-case/                       # .adoc
└── glossary/                       # domain + project glossary .adoc
```

Conventions: files `UpperCamelCase.adoc` / `UpperCamelCase.puml`; directories
`kebab-case/` (the two standard-mandated names `nfr and contact` and
`data-model` are used verbatim). AsciiDoc content in Russian. PlantUML files
use `@startuml`/`@enduml`. Event schemas are JSON Schema (`.json`).

Mapping from the technical layer:

| Technical source | Final artifacts |
|---|---|
| `overview.adoc` + `flow.adoc` | `functional-requirements/` (via spec), `use-case/`, sequence `.puml` |
| `integrations.adoc` | `api/` (internal) and `integration/` (external): OpenAPI/AsyncAPI, mapping, NFR |
| `data.adoc` | `db/data-model/` (DBML) |
| code map (journal) | `architecture/` C4 diagrams |
| terminology across all docs | `glossary/` entries (append/merge) |
| `questions.adoc` | nothing — stays technical |

Bootstrap populates `db/data-model/` only; `ddl/`/`dml/` hold change scripts
and belong to the future change-cycle flow.

## Decision 2: OpenSpec A-lite — Spec as Output, Not Process

Reverse analysis uses the **specs half** of OpenSpec and skips the change
lifecycle entirely. There is no `proposal.md`/`tasks.md`/`archive` for an
analysis run: the code already exists, nothing needs approval, and those
artifacts would be boilerplate nobody re-reads.

- The run writes functional requirements **directly** to
  `openspec/specs/<capability>/spec.md` in Requirement/Scenario format.
  Structural keywords stay English (`### Requirement:`, SHALL, `#### Scenario:`,
  WHEN/THEN — required by the validator); requirement prose is Russian.
- Gate: `openspec validate --specs --strict` must pass (exact CLI flag
  combination to be verified at implementation — cf. the Phase 1 finding that
  ambiguous names require `--type change`).
- **Bootstrap rule (deterministic):** direct writes to
  `openspec/specs/<capability>/spec.md` are allowed only while that capability
  spec does not yet exist. Modifying an existing spec requires the change
  lifecycle. The check is a file-existence test — stdlib-only, and equally
  correct for both templates if they ever share a repository.
- **Derivation rule:** the spec is primary for functional requirements;
  `analytics/functional-requirements/*.adoc` is its derived human-readable
  Russian rendering and is never edited directly. A gate treats a
  `functional-requirements/` write without a corresponding spec write in the
  same run as an advisory warning.

This preserves the cross-flow prize: analysts populate `openspec/specs/` as
current truth; developer-flow agents read it when planning changes.

## Decision 3: Derivation Discipline — Fixes Flow Up, Content Flows Down

Authority chain: **code → technical docs → spec → final tree.** Any content
error discovered downstream (during spec extraction, final generation, or
verification) is fixed in the technical docs first, then derived artifacts are
regenerated. Final docs and specs are never corrected "in place" past the
technical layer. The final verification step checks derivation consistency,
not new content.

## Decision 4: Run Pipeline

Evidence review happens on the technical layer **before** any derivation, so
at run completion the technical docs and the final tree are equivalent by
construction.

1. **Launch.** `/reverse-analysis "<feature>"`; preflight gate validates the
   request (feature name, Jira/Confluence reference or explicit refusal).
2. **Intake in the main session** (no intake subagent). Scope — feature,
   included/excluded, sources, known systems — is recorded in `journal.md`;
   a stdlib gate validates the journal's required structure.
3. **Code mapping.** `code-mapping` agent (Serena `find_symbol` → `rg`
   fallback, module map when present) produces entry points, call chains,
   integrations, data stores, unclear paths. **Stop: analyst confirms scope.**
4. **Technical draft.** `documentation` agent writes the 5 technical docs with
   evidence labels.
5. **Evidence review on technical docs.** `verifier` agent checks unsupported
   claims, contradictions, missing labels; fixes land in the technical docs;
   the layer reaches "confirmed" status (recorded in the manifest).
6. **Spec extraction.** `documentation` agent derives the capability spec from
   confirmed technical docs; `openspec validate --specs --strict` gate blocks
   until it passes.
7. **Final generation.** `documentation` agent generates the final tree from
   the confirmed technical layer + spec; format gates check each written file.
8. **Derivation verification.** `verifier` agent checks final ↔ spec ↔
   technical consistency and structural completeness.
9. **Close.** Manifest finalized; final-artifact links appended to the
   technical docs' metadata headers; the technical layer is frozen.

## Decision 5: Run Manifest

`docs/features/<feature-name>/manifest.json` — machine-readable audit trail
and the linkage between a bootstrap run and its outputs:

```json
{
  "feature": "bonus-accrual",
  "run_date": "2026-06-11",
  "code_commit": "<sha>",
  "status": "scoping|draft|confirmed|complete",
  "scope": {"included": "...", "excluded": "...", "sources": ["code", "user"]},
  "capability": "bonus-accrual",
  "produced": {
    "technical": ["docs/features/bonus-accrual/overview.adoc", "..."],
    "spec": "openspec/specs/bonus-accrual/spec.md",
    "final": ["analytics/functional-requirements/BonusAccrual.adoc", "..."]
  }
}
```

Gates read it: the Stop gate validates run completion from manifest `status`
plus repo state (replacing `last_assistant_message` sniffing), and the
derivation-warning gate uses `produced` to map final files to their run.

## Decision 6: Three Agents, Intake in the Main Session

| Agent | Role | Access |
|---|---|---|
| `code-mapping` | code map for the confirmed scope (Serena, module map, `rg`) | read-oriented |
| `documentation` | technical docs → spec → final tree (multi-format) | writes to `docs/features/<feature>/`, `openspec/specs/`, `analytics/`, `architecture/` |
| `verifier` | evidence review (step 5) + derivation verification (step 8); merges the old `evidence-gap` + `review` | read-oriented |

`intake-scope` is dissolved into the skill + preflight gate: intake questions
are asked by the main session. Each agent file stays below 10,000 characters.
Kept invariants from generation 1: one feature per run, code over Jira/
Confluence, explicit limitation statement when Atlassian context is absent,
stop for scope confirmation, no invented facts.

## Decision 7: Hook Layer — Router and Gates, Copied from Dev-Flow

Per the agreed topology, the flows stay separate: `router.py`, `_lib.py`, and
the reusable gates are **copied** into `modules/analytics/.gigacode/hooks/`,
not extracted into shared infrastructure. All dev-flow safety properties carry
over: `utf-8-sig` stdin (fixes the BOM silent-allow bug), fail-open on garbage
stdin, fail-closed with the `disableAllHooks` escape hatch on config or
internal errors, exactly one JSON on stdout with exit 0, Stop block budget of 2
then degrade-to-warning, decisions journal `.gigacode/logs/decisions.jsonl`,
state pruning, PreToolUse latency budget.

Routes (`router.config.json`):

| Event (matcher) | Gates | Notes |
|---|---|---|
| `UserPromptSubmit` | `preflight_check`, `gate_context_inject` | marker-based request detection retained from gen-1, rewritten as a gate |
| `SessionStart` | `gate_context_inject` | module map injection |
| `SubagentStart` (`^(code-mapping\|documentation)$`) | `gate_context_inject` | |
| `PreToolUse` (`^(Bash\|Shell)$`) | `git_guard` | safety-critical |
| `PreToolUse` (`^(WriteFile\|Edit)$`) | `git_guard` | safety-critical |
| `PreToolUse` (`^(WriteFile\|Edit)$`) | `gate_spec_bootstrap` | bootstrap rule for `openspec/specs/` |
| `PostToolUse` (`^(WriteFile\|Edit)$`) | `gate_techdocs`, `gate_final_format` | each gate self-filters by path |
| `Stop` | `validate_run_output` | manifest- and repo-state-driven |

Gate inventory:

- `preflight_check` — request validation (rewritten from gen-1 hook).
- `gate_context_inject` — injects rules and `.gigacode/context/module-map.md`
  when present.
- `git_guard` — copied as-is from dev-flow.
- `gate_spec_bootstrap` — blocks writes to an **existing**
  `openspec/specs/<capability>/spec.md`; allows creation. Advisory warning for
  `analytics/functional-requirements/` writes with no spec write in the run.
- `gate_techdocs` — for `docs/features/**/*.adoc`: AsciiDoc title, no Markdown
  fences/headings, Russian content, metadata header present (feature, run
  date, code commit; links to final artifacts are appended at close, so the
  gate does not require them).
- `gate_final_format` — for `analytics/**` and `architecture/**`:
  deterministic offline checks (naming conventions, placement by type and
  extension, `@startuml`/`@enduml` pairing, JSON Schema parses via
  `json.loads`, Russian in `.adoc`); deeper validation (OpenAPI/AsyncAPI
  schema validation, `plantuml -checkonly`, spectral) runs through commands in
  `.gigacode/quality-gates.json` — an unconfigured command is a silent allow,
  same semantics as dev-flow `gate_lint`/`gate_build`. Offline gates stay
  stdlib-only (no PyYAML), so YAML validity beyond naming/placement is
  delegated to configured commands.
- `validate_run_output` — Stop gate: for every run manifest, checks
  stage-appropriate completeness (`scoping`: nothing, so the mandatory
  scope-confirmation stop is never blocked; `draft`: the 5 technical docs;
  `confirmed`: plus the capability spec; `complete`: plus every `produced`
  file) and runs spec validation via the configured command; subject to the
  Stop budget.

Testing mirrors dev-flow: offline `scripts/test_router.py` and
`scripts/test_gates.py` analogs inside the module, wired into both smoke
checks. `hook_probe.py` is copied too; live verification of real GigaCode
tool/event names remains a pending step shared with the dev-flow (matchers are
anchored to the documented Qwen Code names until probed).

## Decision 8: Tools and MCP

| Tool | Shipping | Analyst burden |
|---|---|---|
| Serena | declared in `settings.json`, async hooks | needs `uv`; absent → `rg` fallback, non-blocking |
| graphify | CLI + `build_module_map.py` + context-inject gate | optional; no map → gate silent |
| Atlassian | documented only, read-only policy | installs personally; absent → code + user context with explicit limitation |
| Context7 | README copy-paste snippet, **not** in default settings | zero until self-enabled |

Rejected: Repomix (removed everywhere — agents, rules, permissions, README,
matching the dev-flow decision), database MCP, Kafka Schema Registry MCP.
Known caveat carried from dev-flow: Serena's Kotlin LSP support is weak and
must be verified on real code before the flow depends on it.

## Settings

`modules/analytics/.gigacode/settings.json` is rebuilt: one `hooks` block
registering `router.py` per the route table (PreToolUse matcher anchored
`^(Bash|Shell|WriteFile|Edit)$` pending probe results); `mcpServers.serena`;
permissions updated — `repomix` removed, `Edit` allow extended to
`docs/features/**`, `openspec/specs/**`, `analytics/**`, `architecture/**`;
existing secret/destructive-command denies retained. `.gigacode/quality-gates.json`
is new and holds optional validator commands. No secrets, no credentials.

## Smoke Checks

`modules/analytics/scripts/smoke-check.ps1` / `.sh` extended to run fully
offline without GigaCode, MCP, or network: router/gate test suites pass;
`router.config.json` references only existing gates; `gate_spec_bootstrap`
blocks an existing-spec fixture and allows a new-capability fixture;
`gate_final_format` rejects wrong-naming/wrong-placement fixtures;
`validate_run_output` blocks an incomplete-manifest fixture; BOM-prefixed
stdin parses correctly; unconfigured quality-gate commands are silent allows;
`openspec` CLI assertions skip-with-record when the CLI is unavailable. The
10,000-character limit applies to agent `.md` files only, not Python scripts.

## Out of Scope

- The ongoing analytics flow (OpenSpec change lifecycle for maintaining the
  documentation after bootstrap, including `db/ddl/` and `db/dml/` scripts).
  This design only fixes its interfaces: the manifest format, the
  capability-per-feature spec layout, and the derivation rule.
- Re-running reverse analysis on an already-bootstrapped feature (incremental
  re-analysis).
- Shared hook infrastructure between the developer and analyst templates
  (explicitly decided: copy).
- Installing MCP servers or shipping credentials.
- Live GigaCode runtime verification (probe ported; run pending, as in dev-flow).
- CI, auto-commit, auto-push, auto-PR.

## Success Criteria

- A single router dispatches all analytics hooks via the config table; the BOM
  silent-allow bug is gone (verified by a BOM fixture in the test suite).
- A completed run leaves: 5 frozen technical docs with metadata headers, a
  validated `openspec/specs/<capability>/spec.md`, final artifacts in the
  corporate tree passing format gates, and a complete `manifest.json` linking
  them.
- `gate_spec_bootstrap` mechanically enforces "create once, change via
  lifecycle" for capability specs.
- Intake happens in the main session; the template ships exactly 3 agents,
  each below 10,000 characters.
- Repomix is absent from the module; Serena/graphify/Atlassian/Context7 are
  optional with documented fallbacks; smoke checks pass offline on Windows and
  Linux shells.

## Risks

- **Serena Kotlin LSP is weak** — `rg` fallback is mandatory in agent prompts,
  not just documented.
- **Hook tool/event names assumed from Qwen Code docs** — probe before
  trusting matchers against a real GigaCode build (fork drift).
- **Deep YAML validation is not stdlib** — offline gates check structure and
  placement only; teams get real OpenAPI/AsyncAPI validation only after
  configuring `quality-gates.json` commands.
- **Normative SHALL format for descriptive behavior** — analysts review specs
  the agent writes; the format discipline lives on the agent, the analyst
  carries review burden only.
