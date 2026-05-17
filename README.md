# GigaCode Developer Template

Этот репозиторий является проектным шаблоном GigaCode для enterprise-процессов разработки.

Язык workflow по умолчанию - русский. GigaCode задает уточняющие вопросы, объясняет блокеры и пишет Markdown-артефакты разработки на русском языке, если пользователь явно не попросил другой язык. Технические идентификаторы, такие как file paths, commands, branch names, hook names, code symbols, package names и raw command output, остаются без перевода.

Шаблон предоставляет две проектные команды:

- `/develop-feature`: спланировать или реализовать фичу.
- `/fix-bug`: расследовать, спланировать или исправить баг.

Обе команды используют skill `development-flow` и поддерживают два режима:

- `plan-only`: подготовить Markdown-артефакты разработки без изменения исходного кода.
- `implement`: спланировать работу, пройти git safety checks, внести scoped edits, проверить поведение и подготовить PR-ready notes.

## Требования

- GigaCode CLI
- Git
- Python 3
- PowerShell на Windows
- Bash для Linux-compatible smoke checks

## Быстрый старт

Запустите из корня репозитория:

```powershell
gigacode
```

Пример для фичи:

```text
/develop-feature plan-only payment retry with acceptance criteria: retry failed provider calls once after transient timeout
```

Пример для бага:

```text
/fix-bug plan-only card blocking timeout expected: user sees final status actual: request hangs after provider timeout
```

## Выходные артефакты

Артефакты разработки создаются как Markdown-файлы в каталоге:

```text
docs/development/<task-slug>/
```

Ожидаемые файлы:

- `context.md`
- `plan.md`
- `implementation.md`
- `verification.md`
- `pr-summary.md`

## Project Intelligence

Workflow использует project analytics, Repomix и Graphify, когда они доступны.

Fallbacks:

- Если analytics отсутствует, workflow продолжает работу с кодом, тестами, локальной документацией и контекстом от пользователя.
- Если Repomix отсутствует, используется direct repository inspection.
- Если Graphify отсутствует, используется manual impact mapping.

## Enterprise Git Safety

Шаблон блокирует реализацию и git write operations на защищенных ветках, включая `main`, `master`, `develop`, `release/*`, `hotfix/*`, `production`, `staging` и `uat`.

Шаблон по умолчанию блокирует destructive git operations, включая `git reset --hard`, destructive `git clean` variants, forced pushes, branch deletion, remote URL changes и direct protected-branch commits.

В v1 шаблон не выполняет auto-commit и auto-push. PR readiness означает, что workflow готовит reviewer-facing notes и verification evidence для человека или CI workflow.

## Smoke Checks

Windows:

```powershell
.\scripts\smoke-check.ps1
```

Linux-compatible shell:

```bash
bash scripts/smoke-check.sh
```

Smoke checks не требуют GigaCode, Repomix, Graphify, MCP servers, network access или enterprise credentials.

## Адаптация под команду

Обновите `rules/git-safety.md` под protected branches и protected paths вашей команды.

Обновляйте `.gigacode/settings.json` только project-safe defaults. Не храните в репозитории secrets, tokens, personal paths или environment-specific credentials.
