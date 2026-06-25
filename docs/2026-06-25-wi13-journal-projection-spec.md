# WI-13: Journal Projection — человекочитаемое окно во флоу

> **Назначение:** самодостаточная спецификация отдельной фичи — CLI-проекции
> журнала решений. По ней WI-13 можно реализовать независимо от остального
> бэклога.
>
> **Целевое место в репо:** `docs/2026-06-25-wi13-journal-projection-spec.md`
> **Реализует:** RFC ADR-5 (📡 projection), ADR-6 (observer как read-model), WI-13.
> **Статус:** design / к реализации
> **Приоритет:** P1 (самый дешёвый шаг под боль «по CLI непонятно, что делает агент»)
> **Язык:** ru-проза; технические идентификаторы (пути, поля, события) — English/ASCII.

---

## 1. Проблема

Энфорсмент-ядро (router + гейты) пишет каждое решение в `decisions.jsonl`, но
во время прогона агента человек видит только разрозненные block/ask в потоке
инструмента. Нет единого ответа на вопросы: **на какой стадии флоу? сколько
осталось бюджета? что и почему гейты только что решили? не уехал ли scope?**
Боль зафиксирована в RFC (ADR-5): «по CLI непонятно, что делает агент»; «сидеть
и ждать — не про этот флоу».

## 2. Что это

**Read-only проекция поверх event-log'а.** WI-13 не энфорсит и не пишет в
управляющее состояние — он **читает** журнал и рендерит сводку. Это прямое
следствие инвариантов:

- **P5 — события источник истины, проекции безвластны.** `decisions.jsonl` —
  event log; проекция перестраиваема, не в критическом пути хука, fail-open.
  Поломка/отсутствие проекции **никогда** не влияет на решения гейтов.
- **P7 — у всего опционального есть фолбэк.** WI-13 (CLI) — гарантированный
  фолбэк к будущему веб-observer'у (WI-14/15): нет дашборда → есть CLI + журнал.

Аналогия: CQRS read-model. «App предлагает — гейт располагает»; здесь app даже не
предлагает, только показывает.

## 3. Что показывает

Четыре блока (из ADR-5):

1. **Стадия** — где сейчас флоу: `intake → contract → plan → verify → delivery`.
   Выводится не из журнала (он стадию пока не пишет), а из **артефактов и
   approval-маркеров** на диске — тем же способом, что и `gate_stage_order`:
   наличие `docs/development/<slug>/{intake,contract,verdict}.json`,
   `.gigacode/approvals/<slug>/*.ok`, `openspec/changes/<slug>/tasks.md`.
2. **Бюджет** — остаток stop-budget по сессии: `router-state.json` (`stop:<session>`
   → count) против `stop_block_budget` из `router.config.json`.
3. **Поток решений** — последние N записей журнала с **reason'ами**: какой гейт,
   какое решение (allow/ask/block), почему, по какому tool/event, когда.
   Подсветка block/ask.
4. **Scope-адгезия** — изменённые файлы против `contract.json` `scope_globs`
   (зелёный = в scope, красный = вне). Частично сейчас (нужен `contract.json` от
   WI-7 — уже есть), полнее после WI-8 (`gate_scope_guard` + журнал overshoot).

## 4. Источники данных (всё уже существует)

| Сигнал | Источник | Формат |
|---|---|---|
| решения гейтов | `.gigacode/logs/decisions.jsonl` | `{kind:"gate", gate, decision, reason, event, tool, error, ts}` |
| финальные решения | то же | `{kind:"final", event, tool, decision, ts}` |
| stop-блоки | то же | `{kind:"stop_block", session, count, budget, ts}` |
| skip/parse-error | то же | `{kind:"skip"\|"parse_error", ...}` |
| бюджет-состояние | `.gigacode/logs/router-state.json` | `{"stop:<session>": <int>}` |
| карта стадий | `.gigacode/stages.json` | стадии + entry_requires |
| артефакты стадий | `docs/development/<slug>/*`, `openspec/changes/<slug>/*` | файлы на диске |
| approval-маркеры | `.gigacode/approvals/<slug>/<stage>.ok` | файлы на диске |
| scope контракта | `docs/development/<slug>/contract.json` | `scope_globs`, `modules` |

WI-13 **ничего не добавляет** в эти источники — только форматирует.

## 5. Поведение (CLI)

Команда (deployed в `.gigacode/`), запускается человеком во втором терминале:

```
python .gigacode/hooks/projection.py            # одноразовый дайджест (snapshot)
python .gigacode/hooks/projection.py --follow    # tail-режим, обновление по мере записи
python .gigacode/hooks/projection.py --tail 20    # последние N решений
python .gigacode/hooks/projection.py --slug card  # сузить до одной задачи
```

Эскиз вывода:

```
GigaCode flow · session s-42 · 2026-06-25T14:03

stage    : contract  ✓ intake approved   ☐ contract approval pending
budget   : stop 0/2 used
scope    : contract card  (src/cards/**, src/common/dto/CardStatus.kt)

recent decisions (last 8)
  14:03:01  block  gate_stage_order  Edit  openspec/changes/card/proposal.md
            → стадия 'plan' не разблокирована: не выполнено approval:contract
  14:02:48  allow  gate_lint         Edit  src/cards/CardService.kt
  14:02:30  ask    git_guard         Bash  cp evil .github/workflows/ci.yml
  ...
```

В `--follow` блок «recent decisions» дописывается по мере появления строк в
журнале (file-tail; bounded-память — читать только хвост).

## 6. Реализация

- **Zero-dep Python** (stdlib), один файл `.gigacode/hooks/projection.py`. Без
  билд-чейна, тривиально ревьюится — критично для банка.
- **Только чтение.** Никаких записей в `decisions.jsonl`/`router-state.json`/
  артефакты. Не регистрируется ни в `router.config.json`, ни в `settings.json` —
  это **не** хук, а ручной CLI.
- **fail-open / robust:** битая строка журнала — пропустить; отсутствует файл —
  показать «нет данных», не падать. Журнал append-only → читать инкрементально.
- **UTF-8** вывод (как `_lib.emit`/гейты) — кириллица в reason'ах должна выживать
  на cp1251-консоли.
- **bind ничего** — это локальный CLI, не сервер; нулевой phone-home.
- Перенос вычисления стадии/scope лучше шарить с `gate_stage_order` (общие
  хелперы: резолв slug, чтение stages.json, проверка предикатов) — чтобы
  «стадия» в проекции и в гейте не разъезжались.

## 7. Границы (что НЕ делает)

- **Не управляет.** Ни approve, ни конфиг, ни запуск процессов. Соблазн «апрув
  прямо здесь» — именно то место, где вьюшка становится властью и подрывает
  гейты (ADR-6, contested). Если когда-нибудь добавляем управление — только через
  тот же штамп-spine (`confirm.py`-маркеры), а не из проекции.
- **Не сервер.** Веб-вид (SSE `/stream` + HTML/VueFlow) — это WI-14/WI-15,
  отдельно и поверх того же event-log'а. WI-13 — CLI-фолбэк.
- **Не источник истины.** Если проекция и журнал расходятся — прав журнал.

## 8. Зависимости и связи

- **Работает уже сегодня** на текущей схеме журнала: стадия (из артефактов),
  бюджет, поток решений с reason'ами. Не блокируется ничем.
- **WI-2** (`session_id`/`feature`/`agent` в каждой записи журнала) — *усиливает*:
  добавляет **swimlanes** (раздельные дорожки по сессии/фиче/агенту) и корректное
  разведение fan-out. До WI-2 поток решений — единый, без дорожек.
- **WI-7** (`contract.json`) — уже готов → блок «scope» имеет данные.
- **WI-8** (`gate_scope_guard`) — добавит в журнал overshoot-asks и out-of-contract
  → блок «scope-адгезия» становится полным (зелёный/красный по файлам).
- **WI-14/WI-15** — веб-версия той же проекции; стабильный контракт чтения
  (`/stream`) развязывает фронт от данных.

## 9. Банковская поверхность

- Журнал несёт пути/диффы/тикеты → проекция наследует чувствительность. Локальный
  CLI, без сети — риск минимален; на shared-машине/Citrix вывод виден тому, кто за
  терминалом (как любой CLI).
- Ноль телеметрии, ноль bind, ноль записи.

## 10. Acceptance criteria

- [ ] `projection.py` рендерит snapshot из реального `decisions.jsonl` +
      `router-state.json` + артефактов; не падает на пустом/битом журнале.
- [ ] Показывает стадию (из артефактов/approvals), остаток бюджета, последние N
      решений с reason'ами, и (при наличии `contract.json`) scope.
- [ ] `--follow` дописывает новые решения без перечитывания всего файла.
- [ ] Чисто read-only: прогон проекции **не меняет** ни один файл (проверить
      хэшами до/после) и **не** регистрируется как хук.
- [ ] Zero-dep (stdlib only); UTF-8 вывод корректен с кириллицей.
- [ ] Юнит-тесты на парсинг журнала + вычисление стадии/бюджета на фикстурах
      (паттерн `GIGACODE_ROOT`-override, как в `test_gates.py`).

## 11. Открытые вопросы

- Шарить ли резолв стадии с `gate_stage_order` через общий модуль, или дублировать
  (дублирование рискует разъездом «стадии»)?
- `--follow` поллингом файла или через `SubagentStop`/события (probe WI-V4)?
- Куда класть: `.gigacode/hooks/projection.py` (рядом с гейтами) или
  `.gigacode/tools/` (подчеркнуть, что это не хук)?
