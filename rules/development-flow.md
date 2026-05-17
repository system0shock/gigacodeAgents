# Development Flow Rules

Эти правила используются для разработки функций и исправления дефектов.

Пользовательские вопросы, блокеры, резюме и generated developer workflow artifacts по умолчанию пишутся на русском языке. Технические идентификаторы, такие как filenames, commands, branch names, hook names, code symbols, package names, config keys и raw command output, остаются ASCII/English, если проектная конвенция не требует иного.

Operating modes:

- `plan-only`: анализировать задачу и писать Markdown-артефакты разработки без изменения исходного кода.
- `implement`: анализировать задачу, проверять git safety, делать scoped edits, проверять поведение и готовить PR-ready notes.

Required context order:

1. Прочитать project analytics, если они есть.
2. Использовать `Repomix` output, если он есть.
3. Использовать `Graphify` output, если он есть.
4. Если optional tools недоступны, перейти к direct repository inspection и manual impact mapping.
5. Подтвердить текущее поведение по live code до редактирования файлов.

Fallbacks:

- Если analytics отсутствует, зафиксировать это в плане и не делать выводы о проекте без проверки кода.
- Если `Repomix` output отсутствует или устарел, читать релевантные файлы напрямую.
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
