---
name: development-flow
description: MUST BE USED for GigaCode developer workflows that plan or implement features and bug fixes with enterprise git safety, project context, verification, and PR-ready Markdown artifacts.
---

# Development Flow

Use this skill when the developer asks to plan, implement, fix, debug, or prepare a code change.

## Language

Use Russian by default for user-facing interaction and Markdown workflow artifacts. Keep technical identifiers such as paths, commands, branch names, hook names, code symbols, package names, configuration keys, and raw command output unchanged.

## Modes

- `plan-only`: analyze, map impact, and write Markdown artifacts without editing source code.
- `implement`: run the full plan-only flow, pass git safety checks, make scoped edits, verify behavior, and prepare PR-ready notes.

Default to `plan-only` when the requested mode is unclear, high-risk, or missing acceptance criteria.

## Request Types

- Feature work starts from a desired capability, behavior, or technical improvement.
- Bug work starts from an observed failure, regression, incident, error, failing test, or mismatch between expected and actual behavior.
- If the request type is unclear, ask before planning implementation.

Intake is done by the main session, not a subagent — only the main session can
ask the user questions. Before dispatching any agent, settle: task type
(`feature`/`bug`), mode, task slug (lowercase ASCII, digits, hyphens), included
and excluded scope, missing inputs, and safety blockers.

### Объявленный intake (`intake.json`)

Запиши намерение в `docs/development/<slug>/intake.json` — это первый артефакт
стадии. Не «спрашивай, если что-то неясно» — **заполни поля; чего не хватает,
назовёт гейт**. `gate_stage_order` не даст перейти к contract, пока пусты
required-поля (`intake_complete`); в блок-сообщении перечислены ровно недостающие
поля — это и есть вопросы к пользователю. Набор required зависит от `task_type`
(см. `.gigacode/stages.json` → `intake_required`):

- **feature:** `scope_intent`, `acceptance` (≥1), `understanding`.
- **bug:** `repro`, `expected`, `actual`, `severity`, `understanding`.

Поле `understanding` — твой **рестейт задачи своими словами** (in/out scope,
открытые вопросы): на нём стоит understanding-checkpoint. Человек читает
`understanding` и подтверждает понимание командой
`python .gigacode/hooks/confirm.py intake <slug>` (вне сессии агента) — только
после этого contract разблокируется. Шаблон: `docs/templates/intake.json`.

## Required Context

Before planning or editing:

1. Read project analytics when present.
2. Use Graphify output or the Graphify skill when present.
3. If Graphify is absent, build a manual impact map from entry points, imports, call sites, tests, and configuration.
4. Inspect the repository directly with file listing and targeted search.
5. Confirm current behavior from live files before editing.

Record missing optional context in `docs/development/<task-slug>/journal.md`.

## Search Before Create

Before proposing any new function, class, module, or file, search for an existing
implementation using Serena's `find_symbol` tool:

```
mcp__serena__find_symbol(name_or_pattern="<SymbolName>")
```

If Serena is unavailable, use `rg` to search by symbol name across the repository:

```bash
rg -n "def <symbol_name>|class <SymbolName>|function <symbolName>" --type-add 'code:*.{py,ts,js,go,java,rs,rb,cs}' -t code
```

If a matching symbol is found:
1. Record its location in `docs/development/<task-slug>/journal.md`.
2. Read the existing implementation before proposing changes.
3. Extend or adapt the existing code; do not write a duplicate.

If no match is found, record that in `journal.md` and proceed with new implementation.
This rule applies in both plan-only and implement modes.

Карта модулей: хук инжектит `.gigacode/context/module-map.md` на старте сессии
и при запуске субагента coder (если файл есть). После заметных изменений архитектуры перегенерируй её:
`python scripts/build_module_map.py` (требует готовый `graphify-out/graph.json`,
см. README «Карта модулей»).

## Git Safety

Before source edits in implement mode:

1. Run `git status --short`.
2. Run `git branch --show-current`.
3. Run `git rev-list --left-right --count HEAD...@{u}` when upstream exists.
4. Stop on protected branches.
5. Stop when unrelated user changes overlap with planned edits.
6. Do not commit or push by default.

Never run destructive git operations, force pushes, branch deletion, or remote URL changes unless the user gives explicit instruction outside the normal workflow.

## Feature Flow

1. Clarify feature goal, acceptance criteria, included scope, excluded scope, and constraints.
2. Collect project context.
3. Map impact.
4. Write plan and verification strategy.
5. Stop for clarification if scope or safety is unclear.
6. In implement mode, edit only after git guard passes.
7. Verify behavior.
8. Write PR-ready notes.

## Bug Flow

1. Clarify symptom, expected behavior, actual behavior, reproduction steps, affected environment, severity, and workarounds.
2. Collect project context.
3. Plan reproduction.
4. Identify likely root cause.
5. Write fix plan and regression strategy.
6. Stop for clarification if reproduction or impact is unclear.
7. In implement mode, edit only after git guard passes.
8. Verify the regression fix first, then broader checks.
9. Write PR-ready notes.

## Specs and Output Files

Authoritative specifications use OpenSpec under `openspec/` (see
`rules/openspec.md`). Drive specs through the change lifecycle:

1. Create or continue a change with `/opsx:propose "<idea>"` (or `openspec new
   change "<id>"`). This produces `openspec/changes/<change-id>/` with
   `proposal.md`, `design.md`, `tasks.md`, and delta specs.
2. Keep the authoritative requirement/scenario detail in the change's spec
   delta, not in free-form notes.
3. A change is not ready for implementation until
   `openspec validate <change-id> --strict` passes.

Human-facing run notes remain Markdown under `docs/development/<task-slug>/`:

- `journal.md` — context, impact map, plan, and implementation notes
- `verification.md` — commands run, evidence, skipped checks
- `pr-summary.md` — reviewer-facing summary

Run notes summarize and link to the OpenSpec change; they do not replace it.
Plan-only artifacts must clearly state when implementation or verification was
not executed.

## Agents

Use these project agents when appropriate:

1. `repo-context` — project intelligence and impact map (including event flows).
2. `coder` — scoped edits in implement mode after git safety passes.
3. `verifier` — verification evidence and reviewer-facing PR notes.

Intake and implementation planning stay in the main session: intake needs user
dialogue, and the plan lives in the OpenSpec change (`proposal.md`, `design.md`,
`tasks.md`), not in a separate planning artifact.

Each agent file and role description must remain below 10,000 characters.

## Quality Gates

Hook-гейты сопровождают весь цикл: контекст инъецируется на старте сессии и
сабагентов (`^coder$`); записи в `openspec/specs/` и
`openspec/changes/archive/` требуют подтверждения (ask) — легитимны в рамках
`/opsx:sync` / `/opsx:archive`, прямая правка всплывает человеку; после
каждой записи файла запускаются линтер и advisory-эвристики; на Stop в момент
готовности PR — strict-валидация changes и сборка. Команды настраиваются в
`.gigacode/quality-gates.json`; ненастроенная команда = silent allow (без
записи в журнал).

## Явные остановки (enforced)

Переходы между стадиями энфорсятся `gate_stage_order` (`PreToolUse`,
fail-closed). На точке валидации **ОСТАНОВИСЬ и уступи ход** — не продолжай в
том же ответе. Запрос валидации не блокируется; блокируется только *продолжение*:
запись артефакта следующей стадии отклоняется, пока не выполнено условие входа.
Поэтому «попросил проверить и побежал дальше» структурно невозможно.

Активные остановки v1:

- **contract → нужен полный intake + подтверждение понимания (человек).** Запись
  `docs/development/<slug>/contract.json` заблокирована, пока (1) в `intake.json`
  не заполнены все required-поля для `task_type` (`intake_complete` — гейт назовёт
  недостающие) И (2) человек **вне сессии агента** не выполнит
  `python .gigacode/hooks/confirm.py intake <slug>`, подтвердив рестейт
  `understanding`. Сам агент эту команду запустить не может — её режет `git_guard`.
- **plan → нужен замороженный scope (человек).** После approval:intake **до
  записи openspec-пропозала** заморозь scope в `docs/development/<slug>/contract.json`
  (поля `scope_globs` и `modules` обязательны — `contract_complete`; шаблон
  `docs/templates/contract.json`). Запись `openspec/changes/<slug>/proposal.md`
  заблокирована, пока контракт не полон И человек не подтвердит scope:
  `python .gigacode/hooks/confirm.py contract <slug>`. Это второй чекпоинт —
  понимание **подхода/границ** после понимания задачи.
- **delivery → нужен прошедший verdict (машина).** Запись
  `docs/development/<slug>/pr-summary.md` заблокирована, пока `verdict.json` не
  получит `result: "pass"`. Вердикт производит **`gate_verdict` на Stop** из
  реального exit-кода `test.command` — не агент: `verdict.json` machine-owned,
  попытка записать его файловым инструментом блокируется (нельзя проставить
  `pass` вручную). Чтобы пройти — добейся, чтобы тесты реально прошли.

Не пытайся обойти остановку (переименование пути, shell-запись, другой
инструмент) — дождись подтверждения или прохождения проверки. Карта стадий и
условий входа — `.gigacode/stages.json`. Полный жизненный цикл контракта
(amend/restart, заморозка после подтверждения, журнал overshoots) приедет вместе
с `gate_scope_guard` (WI-8), который и потребляет `scope_globs` контракта.
