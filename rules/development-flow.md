# Development Flow Rules

Эти правила используются для разработки функций и исправления дефектов.

Пользовательские вопросы, блокеры, резюме и generated developer workflow artifacts по умолчанию пишутся на русском языке. Технические идентификаторы, такие как filenames, commands, branch names, hook names, code symbols, package names, config keys и raw command output, остаются ASCII/English, если проектная конвенция не требует иного.

Operating modes:

- `plan-only`: анализировать задачу и писать Markdown-артефакты разработки без изменения исходного кода.
- `implement`: анализировать задачу, проверять git safety, делать scoped edits, проверять поведение и готовить PR-ready notes.

Required context order:

1. Прочитать project analytics, если они есть.
2. Использовать `Graphify` output, если он есть.
3. Если optional tools недоступны, перейти к direct repository inspection и manual impact mapping.
4. Подтвердить текущее поведение по live code до редактирования файлов.

Fallbacks:

- Если analytics отсутствует, зафиксировать это в плане и не делать выводы о проекте без проверки кода.
- Если `Graphify` output отсутствует или не покрывает область задачи, вручную составить `Impact Map`.

Implementation invariants:

- Классифицировать запрос как feature, bug или unclear.
- Спрашивать уточнение, когда scope или safety неясны.
- Сначала картировать релевантный код, затем редактировать.
- Защищать существующие пользовательские изменения.
- Работать на safe task branch перед изменением source files.
- Держать изменения строго в рамках запроса.
- Добавлять или обновлять tests пропорционально риску.
- Фиксировать verification evidence до заявления о завершении.
- Не выполнять auto-commit или auto-push в v1.

## Serena: Search Before Create

When Serena MCP is available (`mcp__serena__find_symbol` tool is present):

1. Before proposing a new function, class, or module, call `find_symbol` with
   the intended name.
2. If a match is found anywhere in the repository, read it and reuse or extend
   it; do not write a duplicate.
3. Record the search result (found / not found / Serena unavailable) in
   `docs/development/<task-slug>/journal.md`.

When Serena is unavailable:
- Fall back to `rg` symbol search as documented in the `development-flow` skill.
- Record that Serena was unavailable in `journal.md`.
