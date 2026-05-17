# Модуль аналитики GigaCode

Модуль содержит проектную конфигурацию GigaCode для аналитиков, которым нужно провести обратный анализ одной бизнес-функции и подготовить документацию с явными источниками.

Рабочий контур использует проектную конфигурацию GigaCode и каталог `.gigacode/`.

## Состав модуля

- `.gigacode/settings.json` - настройки проекта, разрешения и подключение hooks.
- `.gigacode/skills/reverse-analysis/SKILL.md` - правила рабочего процесса reverse-analysis.
- `.gigacode/agents/` - пять специализированных субагентов: intake, mapping, documentation, evidence review и final review.
- `.gigacode/hooks/` - hooks для предварительной проверки и валидации результата.
- `.gigacode/commands/reverse-analysis.md` - проектная slash-команда.
- `docs/templates/feature-analysis.adoc` - шаблон результата в AsciiDoc.
- `rules/` - общие правила анализа и именования веток.

## Требования

- GigaCode CLI, доступный как команда `gigacode`.
- Git.
- Python 3, доступный как команда `python`.
- Опционально: Atlassian MCP, настроенный вашей командой, если нужен доступ к Jira или Confluence.
- Опционально: `repomix` для компактной карты репозитория.
- Опционально: `graphify` для выделения графа зависимостей и минимального подграфа функции.

Этот репозиторий не устанавливает MCP-серверы и не хранит учетные данные.

Если `repomix` или `graphify` не установлены, GigaCode должен продолжить анализ обычным поиском по коду и указать это ограничение в результате code mapping.

## Быстрый старт на Windows

```powershell
git clone <repo-url>
cd <repo>\modules\analytics
.\scripts\smoke-check.ps1
gigacode
```

Затем выполните внутри GigaCode:

```text
/reverse-analysis feature "Card Blocking" jira ABC-123
```

## Быстрый старт на Linux

```bash
git clone <repo-url>
cd <repo>/modules/analytics
bash scripts/smoke-check.sh
gigacode
```

Затем выполните внутри GigaCode:

```text
/reverse-analysis feature "Card Blocking" jira ABC-123
```

## Анализ только по коду

Если Jira и Confluence недоступны, укажите это явно:

```text
/reverse-analysis feature "Card Blocking" code-only, no Jira, no Confluence
```

Сгенерированные файлы должны явно указать, что внешний контекст не использовался.

## Ожидаемый результат

GigaCode должен создать AsciiDoc-файлы в каталоге:

```text
docs/features/<feature-name>/
```

Обязательные файлы:

- `overview.adoc`
- `flow.adoc`
- `integrations.adoc`
- `data.adoc`
- `questions.adoc`

Все итоговые документы аналитика должны быть написаны на русском языке.

## Рабочий процесс

1. Intake проверяет название функции и доступность источников.
2. Code mapping при наличии использует `repomix` и `graphify`, затем определяет точки входа, файлы, потоки, интеграции и пробелы.
3. Аналитик подтверждает область анализа.
4. Документация составляется в AsciiDoc на русском языке.
5. Evidence and gap review проверяет неподтвержденные утверждения.
6. Final review проверяет структуру и терминологию.
7. Hooks валидируют запрос и результат.

## Ограничение размера субагентов

Каждый файл субагента должен оставаться короче 10 000 символов. Повторно используемые детали нужно переносить в `rules/` или шаблоны, а не раздувать промпты субагентов.

## Адаптация для командного репозитория

Используйте этот модуль как корень проекта для аналитиков. Если ваш форк GigaCode ожидает `.gigacode/` в другом месте, сохраните внутреннюю структуру и измените только внешний путь модуля.
