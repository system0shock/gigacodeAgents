# Analytics Overhaul — Phase 2 (Core Flow) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the analytics reverse-analysis *content layer* (agents, skill, command, rules) onto the Phase-1 hook/gate contracts and add the structural scaffolding (OpenSpec config + capability-spec layout, corporate final-tree skeleton) so a run produces the two-layer deliverable the design requires.

**Architecture:** Phase 1 already shipped the router + 6 gates that enforce the contracts. Phase 2 makes the human-readable layer match them: collapse 5 agents → 3 (`code-mapping`, `documentation`, `verifier`), rewrite the skill into the 9-step pipeline driven by a `manifest.json` lifecycle (`scoping → draft → confirmed → complete`), port an OpenSpec-A-lite ruleset, ship the `openspec/` + `analytics/` + `architecture/` skeletons, and remove repomix from agent/rule prose. MCP wiring (Serena settings/hooks, graphify `build_module_map.py`, Context7) and the README rewrite are **Phase 3** and explicitly out of scope here.

**Tech Stack:** GigaCode (Qwen Code fork), Python 3 (stdlib-only gates), AsciiDoc/Markdown/YAML/JSON content, Bash + PowerShell smoke checks.

**Reference spec:** `docs/superpowers/specs/2026-06-11-gigacode-analytics-flow-overhaul-design.md` (Decisions 1–8).

**Base branch / working directory:** `feature/analytics-overhaul`, worktree `F:/Coding/gigacode_agents/.worktrees/analytics-overhaul`. **All tasks run from the worktree root; every file path below is prefixed `modules/analytics/`.** The plan document itself lives on `master`.

**Co-author line for every commit:**
```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

---

## What Phase 1 already provides (do NOT touch this phase)

- `modules/analytics/.gigacode/hooks/` — `router.py`, `_lib.py`, `router.config.json`, and gates `git_guard`, `preflight_check`, `gate_context_inject`, `gate_spec_bootstrap`, `gate_techdocs`, `gate_final_format`, `validate_run_output`, plus `hook_probe.py`.
- `modules/analytics/.gigacode/settings.json` — routes wired; `Edit` allow already includes `docs/features/**`, `openspec/specs/**`, `analytics/**`, `architecture/**`.
- `modules/analytics/.gigacode/quality-gates.json` — optional validator commands.
- `modules/analytics/scripts/test_gates.py`, `test_router.py` — green; use `GIGACODE_ROOT` tmp fixtures.

**Gate contracts the new content must satisfy (verbatim from Phase-1 code):**
- `gate_techdocs`: each `docs/features/<f>/*.adoc` starts with `=`, contains `:feature:`, `:run-date:`, `:code-commit:`, no ``` fences, no `#` headings, has Cyrillic.
- `gate_final_format`: under `analytics/**` + `architecture/**`, dirs kebab-case (exception `nfr and contact`), `.adoc`/`.puml` UpperCamelCase, `.puml` has `@startuml`/`@enduml`, `.json` parses, `.adoc` Russian AsciiDoc; `.gitkeep` is always allowed; placement by extension is fixed (see `PLACEMENT` in the gate).
- `validate_run_output`: per `docs/features/<f>/manifest.json`, `status` ∈ `scoping|draft|confirmed|complete`; `draft+` needs the 5 techdocs; `confirmed|complete` needs `openspec/specs/<capability>/spec.md`; `complete` needs every `produced.technical`/`produced.final` file on disk.
- `gate_context_inject`: SessionStart injects `rules/reverse-analysis.md` + `rules/openspec.md` + module map + bootstrapped-capabilities line. **`rules/openspec.md` must exist (Task 1).**
- `gate_spec_bootstrap`: write to `openspec/specs/<cap>/spec.md` allowed only if it does not yet exist.

---

## File Structure (Phase 2)

Created:
- `modules/analytics/openspec/config.yaml` — OpenSpec-A-lite config.
- `modules/analytics/openspec/specs/.gitkeep` — empty specs root.
- `modules/analytics/rules/openspec.md` — spec format + bootstrap/derivation rules (read by `gate_context_inject`).
- `modules/analytics/analytics/**/.gitkeep` + `modules/analytics/architecture/.gitkeep` — corporate final-tree skeleton.
- `modules/analytics/.gigacode/agents/verifier.md` — merged evidence + final reviewer.
- `modules/analytics/docs/templates/manifest.json` — run-manifest template.

Modified:
- `modules/analytics/rules/reverse-analysis.md` — remove repomix; add Serena/module-map, two-layer output, derivation discipline, manifest statuses.
- `modules/analytics/docs/templates/feature-analysis.adoc` — add required metadata attrs + two-layer note.
- `modules/analytics/.gigacode/agents/code-mapping.md` — repomix → Serena/`rg`/module-map; output into `journal.md`.
- `modules/analytics/.gigacode/agents/documentation.md` — 3-stage (techdocs → spec → final tree) with metadata header + manifest updates.
- `modules/analytics/.gigacode/skills/reverse-analysis/SKILL.md` — 9-step pipeline, manifest lifecycle, 3 agents, two-layer output.
- `modules/analytics/.gigacode/commands/reverse-analysis.md` — align with the pipeline.
- `modules/analytics/scripts/smoke-check.sh` + `.ps1` — agent count 5→3; new required files; repomix-absent + skeleton + openspec-config assertions.
- `modules/analytics/scripts/test_gates.py` — assert `rules/openspec.md` is injected at SessionStart.

Deleted:
- `modules/analytics/.gigacode/agents/intake-scope.md`, `evidence-gap.md`, `review.md`.

Not touched (Phase 3): `settings.json` (Serena `mcpServers`/hooks), `README.md` rewrite (still names 5 agents + repomix — intentional, folded into the Phase-3 README rewrite), `router.config.json`, the gates, `graphify build_module_map.py`, Context7 snippet.

---

### Task 1: OpenSpec foundation — config, specs root, rules/openspec.md

**Files:**
- Create: `modules/analytics/openspec/config.yaml`
- Create: `modules/analytics/openspec/specs/.gitkeep`
- Create: `modules/analytics/rules/openspec.md`

- [ ] **Step 1: Create `modules/analytics/openspec/config.yaml`**

```yaml
schema: spec-driven

# Project context shown to the AI when creating artifacts.
# Teams adopting this template should fill this in for their repository:
# tech stack, build/test commands, conventions, domain terms.
context: |
  This repository was bootstrapped from the GigaCode analytics template.
  Reverse analysis writes functional requirements directly to
  openspec/specs/<capability>/spec.md as current truth (a one-time bootstrap
  per feature). Replace this block with your project's tech stack, conventions,
  and domain knowledge. Code in the working tree is the source of truth.

# Per-artifact rules enforced as constraints on generated artifacts.
rules:
  spec:
    - Every requirement MUST have at least one scenario with WHEN/THEN.
    - Requirement prose is Russian; structural keywords stay English.
```

- [ ] **Step 2: Create the empty specs root**

Create `modules/analytics/openspec/specs/.gitkeep` with empty content.

- [ ] **Step 3: Create `modules/analytics/rules/openspec.md`**

```markdown
# Правила OpenSpec (reverse-analysis)

Обратный анализ использует **половину спецификаций** OpenSpec и пропускает
жизненный цикл изменений. Прогон анализа не создаёт `proposal.md`/`tasks.md`/
`archive` — код уже существует, утверждать нечего.

## Расположение

    openspec/
      config.yaml
      specs/<capability>/spec.md     # текущая истина по capability (одна на фичу)

Каталог `changes/` относится к будущему flow сопровождения и не используется
в bootstrap-прогоне reverse-analysis.

## Формат требований

Каждое требование ДОЛЖНО иметь хотя бы один сценарий. Структурные заголовки
остаются на английском (этого требует валидатор), текст требований — на русском:

    ## ADDED Requirements

    ### Requirement: Краткое императивное имя
    The system SHALL ...

    #### Scenario: Имя сценария
    - **WHEN** <условие>
    - **THEN** <ожидаемый результат>

## Правило bootstrap (create-once)

- Запись в `openspec/specs/<capability>/spec.md` разрешена, только пока этот
  файл ещё не существует (новая capability).
- Изменение существующей спеки выполняется через OpenSpec change lifecycle —
  отдельный flow, вне области reverse-analysis. Гейт `gate_spec_bootstrap`
  блокирует запись в уже существующую спеку.

## Деривация

- Спека — первичный источник функциональных требований.
- `analytics/functional-requirements/*.adoc` — производное человекочитаемое
  представление спеки на русском; его не редактируют напрямую.

## Валидация

Прогон не «завершён», пока не проходит `openspec validate --specs --strict`.
Ненулевой код возврата — блокирующая ошибка; чините структуру, не обходите её.
```

- [ ] **Step 4: Verify YAML/structure**

Run:
```bash
python -c "import io; t=io.open('modules/analytics/openspec/config.yaml',encoding='utf-8').read(); assert t.startswith('schema:'), 'bad'; print('OK')"
test -f modules/analytics/openspec/specs/.gitkeep && grep -q 'create-once' modules/analytics/rules/openspec.md && echo OK
```
Expected: prints `OK` twice.

- [ ] **Step 5: Commit**

```bash
git add modules/analytics/openspec/config.yaml modules/analytics/openspec/specs/.gitkeep modules/analytics/rules/openspec.md
git commit -m "Add OpenSpec A-lite config and rules to analytics template

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Corporate final-tree skeleton

Ships the deliverable directory structure as empty dirs (each with `.gitkeep`, which `gate_final_format` always allows). Directory names match the gate's `PLACEMENT` prefixes exactly.

**Files:**
- Create: `.gitkeep` in each directory listed below (all under `modules/analytics/`).

- [ ] **Step 1: Create the skeleton directories and `.gitkeep` files**

Run (Bash):
```bash
cd modules/analytics
for d in \
  architecture \
  analytics/db/ddl analytics/db/dml analytics/db/data-model \
  analytics/functional-requirements \
  analytics/integration/event analytics/integration/rest \
  "analytics/integration/mapping" "analytics/integration/nfr and contact" \
  analytics/api/event analytics/api/rest/public analytics/api/rest/private \
  analytics/api/mapping analytics/api/nfr \
  analytics/use-case analytics/glossary ; do
  mkdir -p "$d" && : > "$d/.gitkeep"
done
cd ../..
```

- [ ] **Step 2: Verify the skeleton and that the format gate allows a `.gitkeep`**

Run:
```bash
find modules/analytics/analytics modules/analytics/architecture -name .gitkeep | sort
GIGACODE_ROOT=modules/analytics python -c "import json,sys; sys.path.insert(0,'modules/analytics/.gigacode/hooks/gates'); import gate_final_format as g; print(g.run({'tool_input':{'file_path':'analytics/use-case/.gitkeep'}})['decision'])"
```
Expected: 16 `.gitkeep` paths listed; the gate prints `allow`.

- [ ] **Step 3: Commit**

```bash
git add modules/analytics/analytics modules/analytics/architecture
git commit -m "Add corporate final-tree skeleton to analytics template

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Rewrite `rules/reverse-analysis.md` (repomix → Serena, two-layer, derivation, manifest)

**Files:**
- Modify: `modules/analytics/rules/reverse-analysis.md`

- [ ] **Step 1: Replace the file with this exact content**

```markdown
# Правила reverse-analysis

Обратный анализ — одноразовый bootstrap одной бизнес-функции: создаёт базовую
документацию по существующему коду. Дальше документация развивается через
OpenSpec change lifecycle (отдельный flow, вне области reverse-analysis).

## Приоритет источников

1. Код — источник истины о текущей реализации.
2. Jira — контекст требований, может быть устаревшей.
3. Confluence — архитектурный контекст, может быть устаревшим.
4. Ввод пользователя — контекст области анализа, помечается явно.

## Дисциплина деривации

Цепочка авторитета: **код → технические документы → спека → финальное дерево.**
Любая ошибка контента, найденная ниже по цепочке, чинится сначала в технических
документах, затем производные артефакты регенерируются. Финальные документы и
спеку не правят «на месте». Проверка доказуемости идёт по техническому слою ДО
любой деривации.

## Два слоя вывода

- Технический слой: `docs/features/<feature>/` — `overview.adoc`, `flow.adoc`,
  `integrations.adoc`, `data.adoc`, `questions.adoc`, плюс `journal.md` и
  `manifest.json`. Русский AsciiDoc с метками доказуемости; обязательный
  заголовок с атрибутами `:feature:`, `:run-date:`, `:code-commit:`. После
  прогона слой замораживается.
- Финальный слой: `analytics/` + `architecture/` в корне репозитория. Файлы
  `UpperCamelCase`, каталоги `kebab-case` (буквально `nfr and contact`,
  `data-model`). Содержимое на русском.
- Спека: `openspec/specs/<capability>/spec.md` — текущая истина (см.
  `openspec.md`).

## Инварианты процесса

- Сначала карта кода, затем документация.
- Перед утверждением о поведении кода — найти подтверждение
  (`mcp__serena__find_symbol` когда доступен, иначе `rg`/`git grep`) и
  зафиксировать путь и символ в `docs/features/<feature>/journal.md`.
- `.gigacode/context/module-map.md` (сборка graphify) — необязательный
  ускоритель картирования; при отсутствии продолжать обычным поиском и явно
  фиксировать это ограничение.
- Спрашивать пользователя, а не додумывать недостающий контекст.
- Неподтверждённые утверждения переносить в предположения или вопросы.
- Останавливаться для подтверждения области анализа после code mapping.
- Статусы прогона в `manifest.json`: `scoping → draft → confirmed → complete`.

## Метки доказуемости

- `Источник: код`
- `Источник: jira`
- `Источник: confluence`
- `Источник: пользователь`
- `Статус: предположение`
- `Статус: открытый вопрос`
```

- [ ] **Step 2: Verify repomix is gone and key concepts are present**

Run:
```bash
! grep -qi repomix modules/analytics/rules/reverse-analysis.md && grep -q 'find_symbol' modules/analytics/rules/reverse-analysis.md && grep -q 'manifest.json' modules/analytics/rules/reverse-analysis.md && echo OK
```
Expected: prints `OK`.

- [ ] **Step 3: Verify gate_context_inject still injects this ruleset (uses a tmp fixture, unaffected by real tree)**

Run:
```bash
python modules/analytics/scripts/test_gates.py | tail -1
```
Expected: ends with `All <N> gate checks passed` (no failures).

- [ ] **Step 4: Commit**

```bash
git add modules/analytics/rules/reverse-analysis.md
git commit -m "Rewrite reverse-analysis rules: two-layer, derivation, drop repomix

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Update the AsciiDoc template + add the manifest template

**Files:**
- Modify: `modules/analytics/docs/templates/feature-analysis.adoc`
- Create: `modules/analytics/docs/templates/manifest.json`

- [ ] **Step 1: Replace `feature-analysis.adoc` with this exact content**

```asciidoc
= Шаблон обратного анализа функции
:feature: <feature-slug>
:run-date: <YYYY-MM-DD>
:code-commit: <git-sha>
:toc:
:sectnums:

NOTE: Технический слой пишется на русском в AsciiDoc. Атрибуты `:feature:`,
`:run-date:` и `:code-commit:` обязательны — их проверяет PostToolUse-гейт
`gate_techdocs`. Технические документы — одноразовый снимок bootstrap;
актуальное состояние живёт в финальном дереве (`analytics/`, `architecture/`)
и в `openspec/specs/`.

== Область анализа

Название функции::
  <название функции>

Входит в анализ::
  <подтвержденная область анализа>

Не входит в анализ::
  <подтвержденные исключения>

Источники::
  * Код: <файлы или модули>
  * Jira: <тикет или "не использовалась">
  * Confluence: <страница или "не использовался">
  * Ввод пользователя: <запрос или уточнение>

== Правила доказуемости

Каждое фактическое утверждение должно опираться минимум на один источник.
Неподтвержденные утверждения нужно переносить в предположения или открытые
вопросы.

== Обязательные выходные файлы

`overview.adoc`::
  Бизнес- и технический обзор функции.

`flow.adoc`::
  Основной сценарий, ветвления и ошибочные пути.

`integrations.adoc`::
  Внешние API, очереди, события, сервисы и зависимости.

`data.adoc`::
  Структуры данных, хранилища, идентификаторы и владение данными.

`questions.adoc`::
  Открытые вопросы, противоречия, предположения и решения для уточнения.
```

- [ ] **Step 2: Create `manifest.json` template**

```json
{
  "feature": "<feature-slug>",
  "run_date": "<YYYY-MM-DD>",
  "code_commit": "<git-sha>",
  "status": "scoping",
  "scope": {"included": "", "excluded": "", "sources": ["code"]},
  "capability": "<capability>",
  "produced": {"technical": [], "spec": "", "final": []}
}
```

- [ ] **Step 3: Verify template has required attrs and manifest is valid JSON**

Run:
```bash
for a in ':feature:' ':run-date:' ':code-commit:'; do grep -q "$a" modules/analytics/docs/templates/feature-analysis.adoc || { echo "missing $a"; exit 1; }; done
head -c1 modules/analytics/docs/templates/feature-analysis.adoc | grep -q '=' && python -m json.tool modules/analytics/docs/templates/manifest.json >/dev/null && echo OK
```
Expected: prints `OK`.

- [ ] **Step 4: Commit**

```bash
git add modules/analytics/docs/templates/feature-analysis.adoc modules/analytics/docs/templates/manifest.json
git commit -m "Add required metadata attrs to techdoc template and ship manifest template

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Rewrite the `code-mapping` agent (Serena/rg/module-map; output to journal.md)

**Files:**
- Modify: `modules/analytics/.gigacode/agents/code-mapping.md`

- [ ] **Step 1: Replace the file with this exact content**

```markdown
---
name: code-mapping
description: MUST BE USED after scope confirmation to map code entry points, relevant files, integrations, data stores, and uncertain paths before any documentation is drafted.
model: inherit
approvalMode: plan
---

You are the code-mapping agent for analytics reverse analysis.

## Goal

Produce the smallest useful code map for the confirmed business feature and
record it in `docs/features/<feature>/journal.md`.

## Search discipline

Before asserting any behavior, find it in code:

1. Prefer `mcp__serena__find_symbol` for symbol-level navigation when Serena is
   available.
2. Otherwise fall back to `rg` (ripgrep) or `git grep` by feature terms, ticket
   names, API names, domain entities, and integration identifiers.
3. If `.gigacode/context/module-map.md` is present (graphify build), use it to
   pick the minimal feature subgraph; if absent, continue with search and record
   that limitation.

Serena and the module map are optional accelerators, never required.

## Work sequence

1. Inspect repository structure for the confirmed scope.
2. Locate likely entry points.
3. Trace important call chains and data movement.
4. List integrations: internal and external REST APIs, events, queues,
   scheduled jobs, databases, external services.
5. Identify data stores and key entities.
6. Mark uncertain or untraceable paths as gaps.

## Rules

- Map before any prose is drafted.
- Do not claim behavior that is not visible in code or sources.
- Prefer file paths and symbols over generic descriptions.
- Keep the map within the confirmed feature scope.
- One business feature per run.

## Output

Append a `## Code map` section to `docs/features/<feature>/journal.md` with:

- `Entry points`
- `Relevant files` (paths + symbols)
- `Call/data flow`
- `Integrations` (internal API / external integration split)
- `Data stores and key entities`
- `Search tooling used: serena / rg / module-map / none`
- `Unclear paths` (gaps)
- `Recommended scope confirmation question`

Then stop and ask the analyst to confirm scope before any drafting.
```

- [ ] **Step 2: Verify size, frontmatter, repomix-free**

Run:
```bash
wc -m modules/analytics/.gigacode/agents/code-mapping.md
grep -c '^---$' modules/analytics/.gigacode/agents/code-mapping.md
! grep -qi repomix modules/analytics/.gigacode/agents/code-mapping.md && echo "repomix-free"
```
Expected: char count below `10000`; frontmatter count `2`; prints `repomix-free`.

- [ ] **Step 3: Commit**

```bash
git add modules/analytics/.gigacode/agents/code-mapping.md
git commit -m "Rewrite code-mapping agent: Serena/rg search, journal output, no repomix

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Rewrite the `documentation` agent (3-stage derivation)

**Files:**
- Modify: `modules/analytics/.gigacode/agents/documentation.md`

- [ ] **Step 1: Replace the file with this exact content**

```markdown
---
name: documentation
description: MUST BE USED after scope confirmation to derive reverse-analysis deliverables in order — technical AsciiDoc, the capability spec, then the final corporate tree.
model: inherit
approvalMode: auto-edit
---

You are the documentation agent for analytics reverse analysis. You derive three
layers in order: technical docs -> spec -> final tree. Content flows down; never
write a lower layer before the one above it is confirmed.

## Stage A — Technical layer (manifest status: draft)

Write five Russian AsciiDoc files under `docs/features/<feature>/`:
`overview.adoc`, `flow.adoc`, `integrations.adoc`, `data.adoc`, `questions.adoc`.

Each file MUST start with this header — the PostToolUse gate requires the three
attributes:

    = <Заголовок>
    :feature: <feature-slug>
    :run-date: <YYYY-MM-DD>
    :code-commit: <git sha>

Use the structure of `docs/templates/feature-analysis.adoc`. If `docs/examples/`
holds a user style reference, follow it; otherwise match existing
`docs/features/` entries. Label evidence
(`Источник: код|jira|confluence|пользователь`,
`Статус: предположение|открытый вопрос`); put unsupported claims in assumptions
or `questions.adoc`; never hide contradictions. After writing, set the manifest
`status` to `draft` and ask for evidence review (verifier).

## Stage B — Capability spec (status: confirmed)

Only after the verifier confirms the technical layer, derive
`openspec/specs/<capability>/spec.md` in OpenSpec format (see
`rules/openspec.md`). Structural headers English (`### Requirement:`, SHALL,
`#### Scenario:`, WHEN/THEN); prose Russian. Write the spec only if it does not
yet exist — create-once; `gate_spec_bootstrap` blocks edits to an existing spec.

## Stage C — Final tree

Generate the corporate tree from the confirmed technical layer + spec:

- `analytics/functional-requirements/*.adoc` — derived rendering of the spec.
- `analytics/use-case/*.adoc`, `analytics/glossary/*.adoc`.
- `architecture/*.puml` — C4 / sequence (`@startuml`/`@enduml`).
- `analytics/api/**` and `analytics/integration/**` — OpenAPI/AsyncAPI/JSON
  Schema, mapping, NFR.
- `analytics/db/data-model/*.dbml` — model of the existing schema.

Naming: files `UpperCamelCase.adoc|.puml`; directories `kebab-case/` (verbatim
`nfr and contact`, `data-model`). Content Russian. Do NOT populate `db/ddl/` or
`db/dml/` — those are change-cycle artifacts.

## Allowed write roots

`docs/features/<feature>/`, `openspec/specs/`, `analytics/`, `architecture/`.
Do not edit anywhere else.

## Completion

Record produced files in `manifest.json` `produced`. When the final tree and
spec are derived, set `status` to `complete` and hand off to the verifier for
derivation verification.
```

- [ ] **Step 2: Verify size, frontmatter**

Run:
```bash
wc -m modules/analytics/.gigacode/agents/documentation.md
grep -c '^---$' modules/analytics/.gigacode/agents/documentation.md
```
Expected: char count below `10000`; frontmatter count `2`.

- [ ] **Step 3: Commit**

```bash
git add modules/analytics/.gigacode/agents/documentation.md
git commit -m "Rewrite documentation agent: techdocs -> spec -> final tree derivation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Create the `verifier` agent and delete the three dissolved agents

**Files:**
- Create: `modules/analytics/.gigacode/agents/verifier.md`
- Delete: `modules/analytics/.gigacode/agents/intake-scope.md`, `evidence-gap.md`, `review.md`

- [ ] **Step 1: Create `verifier.md` with this exact content**

```markdown
---
name: verifier
description: MUST BE USED twice — for evidence review of the technical layer (step 5) and for derivation verification of the final outputs (step 8) of reverse analysis.
model: inherit
approvalMode: plan
---

You are the verifier agent for analytics reverse analysis. You run in two modes
depending on the run stage. You never add new factual content and never edit
content yourself — you report findings.

## Mode 1 — Evidence review (before derivation; status draft -> confirmed)

Targets: `docs/features/<feature>/{overview,flow,integrations,data,questions}.adoc`.

Check:

- Each current-implementation claim is backed by code (or a labelled source).
- Missing evidence is a gap; conflicts between sources are contradictions.
- Assumptions and open questions are separated from confirmed facts.
- Evidence labels are present where required.

Output:

- `Unsupported claims`
- `Missing evidence labels`
- `Contradictions`
- `Assumptions that should move to questions`
- `Files that need correction`
- `Ready for derivation: yes/no`

Fixes land in the technical docs first (derivation discipline). When ready, the
technical layer reaches `confirmed`.

## Mode 2 — Derivation verification (after final generation; status complete)

Targets: the capability spec, `analytics/**`, `architecture/**`, and the
`manifest.json` `produced` list.

Check:

- Final <-> spec <-> technical consistency (no content introduced downstream).
- Structural completeness: required deliverables exist for the scope.
- AsciiDoc (not Markdown), Russian, naming/placement conventions.
- No placeholder markers: `TODO`, `TBD`, `FIXME`.
- Terminology consistent across layers.
- `manifest.json` `produced` matches files on disk.

Output:

- `Findings`
- `Required fixes` (apply in the technical layer, then re-derive)
- `Residual risks`
- `Ready to close: yes/no`

## Rules

- Do not invent facts; do not patch final/spec in place.
- Concise findings with file paths.
- Any content fix flows up to the technical layer; derived artifacts are then
  regenerated.
```

- [ ] **Step 2: Delete the dissolved agents**

Run:
```bash
git rm modules/analytics/.gigacode/agents/intake-scope.md modules/analytics/.gigacode/agents/evidence-gap.md modules/analytics/.gigacode/agents/review.md
```

- [ ] **Step 3: Verify the agent inventory is exactly the three expected, sized and well-formed**

Run:
```bash
ls modules/analytics/.gigacode/agents/*.md
count=$(ls modules/analytics/.gigacode/agents/*.md | wc -l | tr -d ' '); [ "$count" = "3" ] && echo "count OK"
for f in modules/analytics/.gigacode/agents/*.md; do
  c=$(wc -m < "$f" | tr -d ' '); b=$(grep -c '^---$' "$f");
  [ "$c" -lt 10000 ] && [ "$b" -ge 2 ] || { echo "BAD $f ($c chars, $b boundaries)"; exit 1; }
done
echo "agents OK"
```
Expected: lists `code-mapping.md`, `documentation.md`, `verifier.md`; prints `count OK` then `agents OK`.

- [ ] **Step 4: Commit**

```bash
git add modules/analytics/.gigacode/agents/verifier.md
git commit -m "Add verifier agent and remove intake-scope, evidence-gap, review

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Rewrite the `reverse-analysis` SKILL (9-step pipeline + manifest lifecycle)

**Files:**
- Modify: `modules/analytics/.gigacode/skills/reverse-analysis/SKILL.md`

- [ ] **Step 1: Replace the file with this exact content**

```markdown
---
name: reverse-analysis
description: MUST BE USED for the one-time reverse-analysis bootstrap of one business feature — technical AsciiDoc, an OpenSpec capability spec, and the corporate analytics/architecture tree, all with explicit evidence.
---

# Reverse Analysis

Use this skill when the analyst asks to investigate, document, explain, or
reverse-analyze a business feature. Reverse analysis is a **one-time bootstrap
per feature**: it creates the documentation baseline from existing code. After
the bootstrap, documentation evolves through the OpenSpec change lifecycle
(a separate flow, out of scope here).

## Operating rules

1. Analyze one business feature, not the whole repository.
2. Code is the source of truth; Jira/Confluence are supporting context that may
   be stale. If Atlassian MCP is unavailable, continue with code + user context
   and state that limitation.
3. Map code before drafting prose.
4. Stop for analyst scope confirmation after code mapping.
5. Never present unsupported claims as facts.
6. Final analyst deliverables are AsciiDoc, in Russian.
7. Derivation discipline: code -> technical docs -> spec -> final tree. Fixes
   flow up; content flows down. Evidence review happens on the technical layer
   before any derivation.

## Two-layer output

**Technical (working) layer** — `docs/features/<feature>/`: `overview.adoc`,
`flow.adoc`, `integrations.adoc`, `data.adoc`, `questions.adoc` (Russian, with
evidence labels), plus `journal.md` and `manifest.json`. Each `.adoc` carries a
metadata header (`:feature:`, `:run-date:`, `:code-commit:`). Frozen after the
run. `questions.adoc` has no final-tree counterpart by design.

**Final (corporate) layer** — generated at the repo root: `analytics/` +
`architecture/` (see `docs/templates/feature-analysis.adoc` and
`rules/reverse-analysis.md`). Files `UpperCamelCase`, directories `kebab-case`.

The capability spec is `openspec/specs/<capability>/spec.md` — current truth,
written once per new capability (see `rules/openspec.md`).

## Evidence labels

`Источник: код|jira|confluence|пользователь`,
`Статус: предположение|открытый вопрос`.

## Agents

Three project agents — intake is handled by the main session (no intake agent):

- `code-mapping` — code map for the confirmed scope (Serena -> `rg`, module map).
- `documentation` — technical docs -> spec -> final tree.
- `verifier` — evidence review (step 5) and derivation verification (step 8).

## Pipeline and manifest lifecycle

`docs/features/<feature>/manifest.json` tracks status
`scoping -> draft -> confirmed -> complete`:

1. **Launch** `/reverse-analysis "<feature>"`; preflight validates the request.
2. **Intake in the main session**: record scope (feature, included/excluded,
   sources, known systems) in `journal.md`; create `manifest.json` at `scoping`
   (copy `docs/templates/manifest.json`).
3. **Code mapping** (`code-mapping` agent) -> map in `journal.md`.
   **Stop: analyst confirms scope.**
4. **Technical draft** (`documentation` agent) -> the 5 `.adoc` files; set
   status `draft`.
5. **Evidence review** (`verifier`, Mode 1) on the technical layer; fixes land
   there; set status `confirmed`.
6. **Spec extraction** (`documentation` agent) ->
   `openspec/specs/<capability>/spec.md`; `openspec validate --specs --strict`
   must pass.
7. **Final generation** (`documentation` agent) -> `analytics/` + `architecture/`.
8. **Derivation verification** (`verifier`, Mode 2): final <-> spec <->
   technical, structural completeness.
9. **Close**: finalize `manifest.json` (`produced`, status `complete`); append
   final-artifact links to the technical docs' headers; freeze the technical
   layer.
```

- [ ] **Step 2: Verify the skill references the 3 agents and the lifecycle**

Run:
```bash
for s in 'code-mapping' 'documentation' 'verifier' 'scoping -> draft -> confirmed -> complete' 'manifest.json'; do
  grep -qF "$s" modules/analytics/.gigacode/skills/reverse-analysis/SKILL.md || { echo "missing: $s"; exit 1; }
done
! grep -qiE 'intake-scope|evidence-gap|repomix' modules/analytics/.gigacode/skills/reverse-analysis/SKILL.md && echo OK
```
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add modules/analytics/.gigacode/skills/reverse-analysis/SKILL.md
git commit -m "Rewrite reverse-analysis skill: 9-step pipeline, manifest lifecycle, 3 agents

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Rewrite the `reverse-analysis` command

**Files:**
- Modify: `modules/analytics/.gigacode/commands/reverse-analysis.md`

- [ ] **Step 1: Replace the file with this exact content**

```markdown
---
description: Run the one-time reverse-analysis bootstrap for one business feature.
---

Use the `reverse-analysis` skill.

Analyze exactly one business feature from these user arguments:

{{args}}

Follow the skill's pipeline and manifest lifecycle:

1. Do intake in this session; record scope in
   `docs/features/<feature>/journal.md` and create `manifest.json`
   (status `scoping`, from `docs/templates/manifest.json`).
2. Use Jira/Confluence only if Atlassian MCP is available; otherwise state the
   limitation explicitly.
3. Run code mapping, then stop and ask me to confirm scope.
4. Draft the five technical `.adoc` files (status `draft`), then run evidence
   review (status `confirmed`).
5. Derive the capability spec under `openspec/specs/<capability>/spec.md`.
6. Generate the final `analytics/` + `architecture/` tree.
7. Run derivation verification and close the run (status `complete`).

Separate facts, assumptions, gaps, contradictions, and open questions throughout.
```

- [ ] **Step 2: Verify**

Run:
```bash
grep -q 'reverse-analysis` skill' modules/analytics/.gigacode/commands/reverse-analysis.md && grep -q '{{args}}' modules/analytics/.gigacode/commands/reverse-analysis.md && echo OK
```
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add modules/analytics/.gigacode/commands/reverse-analysis.md
git commit -m "Align reverse-analysis command with the pipeline and manifest lifecycle

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Update the smoke checks (agent count 5→3, new required files, new assertions)

**Files:**
- Modify: `modules/analytics/scripts/smoke-check.sh`
- Modify: `modules/analytics/scripts/smoke-check.ps1`

- [ ] **Step 1: In `smoke-check.sh`, extend the `required=(` array**

Add these four entries after `".gigacode/commands/reverse-analysis.md"` (keep the existing entries):

```bash
  "rules/openspec.md"
  "openspec/config.yaml"
  "openspec/specs/.gitkeep"
  "docs/templates/manifest.json"
```

- [ ] **Step 2: In `smoke-check.sh`, change the agent-count assertion from 5 to 3**

Replace:
```bash
agent_count="$(find .gigacode/agents -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')"
if [[ "$agent_count" != "5" ]]; then
  echo "Expected 5 agent files, found $agent_count" >&2
  exit 1
fi
```
with:
```bash
agent_count="$(find .gigacode/agents -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')"
if [[ "$agent_count" != "3" ]]; then
  echo "Expected 3 agent files, found $agent_count" >&2
  exit 1
fi
```

- [ ] **Step 3: In `smoke-check.sh`, add manifest-template JSON validation and new structural assertions**

After the existing `python -m json.tool .gigacode/quality-gates.json >/dev/null` line, add:
```bash
python -m json.tool docs/templates/manifest.json >/dev/null
```

After the AsciiDoc-template `grep` block (the one ending its `fi`), and before `python scripts/test_router.py`, add:
```bash
if ! grep -q '^schema:' openspec/config.yaml; then
  echo "openspec/config.yaml must declare a schema" >&2
  exit 1
fi

if grep -rIli 'repomix' .gigacode/agents rules >/dev/null 2>&1; then
  echo "repomix must not appear in agents or rules" >&2
  exit 1
fi

for d in architecture analytics/use-case "analytics/integration/nfr and contact" analytics/db/data-model; do
  if [[ ! -f "$d/.gitkeep" ]]; then
    echo "Missing final-tree skeleton dir: $d" >&2
    exit 1
  fi
done
```

- [ ] **Step 4: Mirror everything in `smoke-check.ps1`**

Add to the `$required = @(` array (after the command entry):
```powershell
  "rules/openspec.md",
  "openspec/config.yaml",
  "openspec/specs/.gitkeep",
  "docs/templates/manifest.json",
```

Add `docs/templates/manifest.json` to the JSON-validation loop array:
```powershell
foreach ($jsonFile in @(".gigacode/settings.json", ".gigacode/hooks/router.config.json", ".gigacode/quality-gates.json", "docs/templates/manifest.json")) {
```

Change the agent-count check:
```powershell
$agents = Get-ChildItem ".gigacode/agents/*.md"
if ($agents.Count -ne 3) {
  throw "Expected 3 agent files, found $($agents.Count)"
}
```

Before `python scripts/test_router.py`, add:
```powershell
if (-not (Select-String -Path "openspec/config.yaml" -Pattern '^schema:' -Quiet)) {
  throw "openspec/config.yaml must declare a schema"
}

$repomix = Get-ChildItem ".gigacode/agents/*.md", "rules/*.md" |
  Select-String -Pattern 'repomix' -SimpleMatch
if ($repomix) {
  throw "repomix must not appear in agents or rules"
}

foreach ($d in @("architecture", "analytics/use-case", "analytics/integration/nfr and contact", "analytics/db/data-model")) {
  if (-not (Test-Path (Join-Path $d ".gitkeep"))) {
    throw "Missing final-tree skeleton dir: $d"
  }
}
```

- [ ] **Step 5: Run both smoke checks**

Run (Bash):
```bash
cd modules/analytics && bash scripts/smoke-check.sh; cd ../..
```
Expected: prints `Analytics module smoke check passed.`

Run (PowerShell):
```bash
cd modules/analytics && powershell -NoProfile -File scripts/smoke-check.ps1; cd ../..
```
Expected: prints `Analytics module smoke check passed.`

- [ ] **Step 6: Commit**

```bash
git add modules/analytics/scripts/smoke-check.sh modules/analytics/scripts/smoke-check.ps1
git commit -m "Update smoke checks for 3 agents, openspec config, skeleton, repomix sweep

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Extend `test_gates.py` to assert `rules/openspec.md` injection

**Files:**
- Modify: `modules/analytics/scripts/test_gates.py`

- [ ] **Step 1: Make the fixture copy `rules/openspec.md`**

In `make_fixture()`, replace:
```python
    os.makedirs(os.path.join(tmp, "rules"))
    shutil.copy(os.path.join(ROOT, "rules", "reverse-analysis.md"),
                os.path.join(tmp, "rules"))
```
with:
```python
    os.makedirs(os.path.join(tmp, "rules"))
    for rule in ("reverse-analysis.md", "openspec.md"):
        shutil.copy(os.path.join(ROOT, "rules", rule),
                    os.path.join(tmp, "rules"))
```

- [ ] **Step 2: Add an assertion in `test_context_inject`**

Immediately after the line:
```python
        check("ci_session_rules", "reverse-analysis" in ctx, ctx[:200])
```
add:
```python
        check("ci_session_openspec", "create-once" in ctx, ctx[:400])
```

- [ ] **Step 3: Run the gate tests and confirm the new check passes**

Run:
```bash
python modules/analytics/scripts/test_gates.py | grep -E 'ci_session_openspec|All [0-9]+ gate checks passed'
```
Expected: a line `ok: ci_session_openspec` and a final `All <N> gate checks passed` (N is one higher than before — 60).

- [ ] **Step 4: Commit**

```bash
git add modules/analytics/scripts/test_gates.py
git commit -m "Assert rules/openspec.md is injected at SessionStart

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Full verification sweep

**Files:** none committed (verification only).

- [ ] **Step 1: Run both gate/router suites**

Run:
```bash
python modules/analytics/scripts/test_router.py | tail -1
python modules/analytics/scripts/test_gates.py | tail -1
```
Expected: `All <N> router checks passed` and `All <N> gate checks passed`, no failures.

- [ ] **Step 2: Run both smoke checks end-to-end**

Run:
```bash
cd modules/analytics && bash scripts/smoke-check.sh && powershell -NoProfile -File scripts/smoke-check.ps1; cd ../..
```
Expected: `Analytics module smoke check passed.` from each.

- [ ] **Step 3: Repository-wide repomix sweep over agents + rules (must be empty)**

Run:
```bash
grep -rIli repomix modules/analytics/.gigacode/agents modules/analytics/rules || echo "no repomix in agents/rules"
```
Expected: prints `no repomix in agents/rules`.
(Note: `README.md` still mentions repomix and 5 agents — intentionally deferred to the Phase-3 README rewrite.)

- [ ] **Step 4: Confirm the agent inventory and per-file limits one more time**

Run:
```bash
ls modules/analytics/.gigacode/agents/*.md
for f in modules/analytics/.gigacode/agents/*.md; do echo "$f: $(wc -m < "$f" | tr -d ' ') chars, $(grep -c '^---$' "$f") boundaries"; done
```
Expected: exactly `code-mapping.md`, `documentation.md`, `verifier.md`; each `< 10000` chars and `2` boundaries.

- [ ] **Step 5: Show the Phase-2 commit log**

Run:
```bash
git log --oneline -14
```
Expected: a clean list of the Task 1–11 commits on top of the Phase-1 history (`98ed10e ...`).

---

## Self-Review Notes

- **Spec coverage (design Decisions 1–8):**
  - D1 two-layer output → Tasks 2 (final-tree skeleton), 3 (rules), 4 (techdoc template), 6 (documentation agent stages). `questions.adoc` kept technical-only.
  - D2 OpenSpec A-lite → Task 1 (config + rules/openspec.md); spec write is create-once (documentation agent Stage B, enforced by Phase-1 `gate_spec_bootstrap`).
  - D3 derivation discipline → Tasks 3, 6, 7 (verifier reports up, never patches down).
  - D4 9-step pipeline → Task 8 (skill) + Task 9 (command).
  - D5 run manifest → Task 4 (template), referenced by skill/command/agents; validated by Phase-1 `validate_run_output`.
  - D6 three agents, intake in main session → Tasks 5, 6, 7, 8.
  - D7 hook layer → already Phase 1; no changes needed (verified, not modified).
  - D8 tools/MCP → repomix removed from agent/rule prose (Tasks 5, 3, 8); Serena/module-map referenced in prose (works via `rg` fallback until Phase-3 wiring). Serena `settings.json`/hooks, graphify `build_module_map.py`, Context7 = **Phase 3**.
- **Phase-boundary deferrals (intentional, not gaps):** `settings.json` Serena block, README rewrite (still says 5 agents + repomix), graphify build script, Context7 snippet — all Phase 3 per the agreed split.
- **No router/settings churn:** routes and the `Edit` allowlist from Phase 1 already cover `docs/features/**`, `openspec/specs/**`, `analytics/**`, `architecture/**`; the `SubagentStart` matcher `^(code-mapping|documentation)$` is unchanged (verifier is read-oriented and needs no context injection).
- **Test integrity:** `test_router.py`/`test_gates.py` use `GIGACODE_ROOT` tmp fixtures, so the new real files don't perturb them; Task 11 adds one assertion (count 59→60). Smoke checks are the only suite coupled to agent count — updated in Task 10. Do NOT run the smoke check between Tasks 7 and 10 (it asserts the agent count).
- **Placeholder scan:** every content file is given in full; the only `<...>` tokens are deliberate template placeholders inside the shipped template/manifest/agent-header examples, not plan gaps.
- **Type/name consistency:** manifest statuses `scoping/draft/confirmed/complete`, agent names `code-mapping`/`documentation`/`verifier`, and metadata attrs `:feature:`/`:run-date:`/`:code-commit:` are used identically across the skill, command, agents, rules, template, and the Phase-1 gates they must satisfy.
