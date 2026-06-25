# WI-14/15: Observer — веб-проекция флоу (SSE) + контракт `/stream`

> **Назначение:** самодостаточная спецификация observer-сервиса (WI-14) и его
> data-API контракта `/stream` (WI-15) — read-only веб-вида поверх того же
> event-log'а, что и CLI-проекция WI-13.
>
> **Целевое место в репо:** `docs/2026-06-25-wi14-15-observer-spec.md`
> **Реализует:** RFC ADR-5 (📡 projection), ADR-6 (observer как read-model / CQRS),
> WI-14 (сервис), WI-15 (`/stream` контракт).
> **Опирается на:** WI-13 (`projection.collect` / `read_from_offset` / `_stage`),
> WI-2 (идентичность журнала session/feature/agent), WI-11 (`verdict.json`),
> WI-20 (`intake.json`), WI-7/8 (`contract.json` / scope).
> **Визуальный референс:** `docs/wi14_journal_projection_dashboard_v2.html` (макет
> коллеги) → пересобран под zero-dep в брейнсторме (v7).
> **Статус:** design / к реализации. **Приоритет:** P3 (после WI-13; дашборд —
> «приятный вид», CLI+журнал — гарантированный фолбэк P7).
> **Язык:** ru-проза; технические идентификаторы (пути, поля, события) — English/ASCII.

---

## 1. Проблема

WI-13 дал человекочитаемую проекцию флоу в CLI. Но во время прогона удобнее
держать живой веб-вид во втором окне: граф стадий, бюджет, поток решений с
reason'ами, scope, и — главное — **что агент вообще делает и не застрял ли он**.
RFC ADR-6 описывает это как локальную лёгкую приложеньку-наблюдатель. Ключевой
запрос с брейнсторма: текущий технический event-log **не отвечает на человеческие
вопросы** «какая задача? чего ждёт? идёт прогресс или встал?».

## 2. Что это (и чем НЕ является)

**Read-model поверх event-log'а (CQRS).** Observer — проекция: перестраиваемая,
**read-only**, не в критическом пути enforcement (P5). Поломка/остановка observer
**никогда** не влияет на решения гейтов.

- **НЕ control-plane.** Ни approve, ни конфиг, ни запуск процессов из вьюшки. Если
  когда-нибудь добавляется управление — только через тот же штамп-spine
  (`confirm.py`-маркеры), а не из observer (ADR-6, contested).
- **НЕ источник истины.** Источник — `decisions.jsonl` + артефакты; расходится с
  observer → прав журнал.
- **НЕ единственное окно.** WI-13 (CLI) — гарантированный фолбэк (P7): нет браузера
  → есть терминал.
- **НЕ VueFlow (в v1).** Граф стадий рисуется статическим SVG/flex (zero-dep).
  VueFlow-библиотека (drag/zoom/pan, npm) — отложенный апгрейд на тот же `/stream`.

## 3. Решения брейнсторма (зафиксировано)

| # | Вопрос | Решение |
|---|--------|---------|
| 1 | Объём v1 | Полный observer по ADR-6 (граф/бюджет/решения/scope/risk/swimlanes), **VueFlow отложен**. WI-14 + WI-15 одной спекой. |
| 2 | Размещение | `modules/development/.gigacode/hooks/observer.py` — single-module, рядом с `projection.py`/`confirm.py`. Переезд в `modules/_shared/` — забота WI-3; `/stream` держит релокабельным. |
| 3 | Данные | **Импорт функций `projection.py`** (`collect`, `read_from_offset`, `read_decisions`) — третий читатель, ноль нового абстрагирования, ноль дрейфа. |
| 4 | Доставка | **Чистый file-tail** (поллинг журнала), **без** hook-side push. Enforcement не в критическом пути (P5). |
| 5 | Свежесть | `snapshot` переэмитится и после новых решений, **и по таймеру (~2 с)** — дериватные данные (бюджет, стадия через approval-маркеры, scope, config) меняются БЕЗ записи в журнал. |
| 6 | Фронт | Один статический HTML, vanilla JS (`EventSource`), инлайн CSS с `:root`-переменными. **Ноль внешних ассетов** (нет Tabler/CDN/дизайн-системы/VueFlow). |
| 7 | Темы | mint (default) + ultra-pink; переключатель в шапке; выбор в `localStorage`. Тема = смена класса `.dash` (один блок `:root`-переменных). |
| 8 | Подсказки | «?»-бейдж в углу каждого блока + пер-узловые тултипы на графе. `data-tip` + CSS `:hover/:focus::after`. Zero-dep, доступно с клавиатуры. |

## 4. Источники данных (всё уже существует; observer ничего не добавляет)

| Сигнал | Источник | Через |
|---|---|---|
| стадия / scope / бюджет / решения | `projection.collect(slug)` → Snapshot | WI-13 (реюз) |
| инкрементальный хвост журнала | `projection.read_from_offset(path, off)` | WI-13 (реюз) |
| стадии + предикаты | `_stage.stage_status` / `current_stage` | WI-13/WI-22 (через collect) |
| задача (шапка) | `docs/development/<slug>/intake.json` | WI-20 |
| текущий блокер | последняя `decision:"block"` запись журнала | вывод в observer |
| vital signs | агрегация `decisions.jsonl` (счётчики/темп/idle/длительность/tools) | вывод в observer |
| вердикт | `docs/development/<slug>/verdict.json` | WI-11 (через collect/доп.чтение) |
| бюджет-лимит | `router.config.json` `stop_block_budget` | WI-13 `read_budget` |

**Read-only инвариант (наследуется от WI-13):** ни один путь observer не пишет
файлы и **не вызывает** `_lib.changed_code_files` / `git_changed_paths` /
`journal_skip` (они аппендят в `decisions.jsonl` при сбое git). Только чистое
чтение. Vital signs/idle используют **wall-clock сервера** (это не запись — ок).

## 5. Архитектура (WI-14)

Один файл `modules/development/.gigacode/hooks/observer.py`, zero-dep stdlib,
manual CLI (не хук; не в `router.config.json`/`settings.json`):

```
observer.py   python .gigacode/hooks/observer.py [--port 8787] [--slug card]
├── http.server.ThreadingHTTPServer  — bind 127.0.0.1 ТОЛЬКО (никогда 0.0.0.0)
│   GET /             → встроенный статический HTML (vanilla JS, инлайн CSS)
│   GET /api/snapshot?slug=<opt> → JSON Snapshot (стартовое состояние / фолбэк)
│   GET /stream?slug=<opt>       → text/event-stream (SSE)
├── tail-loop (фоновый поток на каждого SSE-клиента ИЛИ один общий broadcaster):
│   read_from_offset() по интервалу → новым строкам шлёт `event: decision`;
│   плюс по таймеру (~2 с) шлёт свежий `event: snapshot` (дериватные данные)
├── enrich(snapshot): добавляет vital signs + current_blocker + intake к Snapshot
└── reuse: projection.collect / read_from_offset / read_decisions / _stage
```

- **Конкурентность:** ThreadingHTTPServer; единственный мутабельный стейт сервера —
  множество подключённых SSE-клиентов (очередь на клиента). К журналу/артефактам —
  только чтение, гонок за enforcement-состоянием нет (ADR-4/P5).
- **Lifecycle:** запускается человеком во втором терминале (документированный
  one-liner). **Не** авто-спавнится из хука (ADR-6 — лишняя поверхность).
- **fail-open:** битый журнал → пропуск строк; нет артефакта → блок «нет данных»;
  `collect()` упал → Snapshot с null-ами. Сервер **никогда не 500-ит на данных**.

## 6. Контракт `/stream` + `/api/snapshot` (WI-15)

Стабильная data-API поверхность, развязывающая фронт от данных (задел под VueFlow).

### 6.1 `GET /api/snapshot?slug=<opt>` → `200 application/json`

`enrich(projection.collect(slug))` — Snapshot WI-13 плюс observer-поля:

```json
{
  "_contract": "wi15/1",
  "session": "s-42", "slug": "card", "slug_candidates": ["card"],
  "stage": {"current":"contract","stages":[{"id","order","enterable","met":[],"unmet":[]}]},
  "budget": {"used":0,"limit":2},
  "scope":  {"scope_globs":[...],"modules":[...]},
  "decisions": [<последние N записей журнала>],
  "intake": {"task_type":"feature","scope_intent":"...","acceptance":[...],
             "constraints":[...],"understanding":"..."},
  "blocker": {"active":true,"stage":"plan","unmet":"approval:contract",
              "command":"python .gigacode/hooks/confirm.py contract card",
              "reason":"...","ts":"..."},
  "vitals": {"total":14,"block":1,"ask":1,"allow":12,"per_min":3.2,
             "idle_sec":8,"session_sec":720,"tools":{"Edit":7,"Bash":4,"Write":3}},
  "verdict": {"result":"pass","risk":{...},"findings":[...]} 
}
```
`intake`/`verdict`/`blocker` → `null`, если артефакта/блока нет (fail-open).

### 6.2 `GET /stream?slug=<opt>` → `text/event-stream`

```
event: snapshot          ← при подключении, после каждой пачки решений, и по таймеру ~2с
data: {<тот же enriched Snapshot>}

event: decision          ← на каждую новую запись журнала (живой append/подсветка)
data: {"session_id","feature","agent","kind","event","tool","gate","decision","reason","ts"}

: ping                    ← SSE-комментарий ~15с (heartbeat против idle-timeout)
```

Два события, потому что стадия/бюджет/scope/vitals **деривируются** (не лежат в
журнале): `decision` несёт сырую запись (фронт раскладывает по swimlanes
session/feature/agent и подсвечивает новое), `snapshot` обновляет все панели.
Таймерный `snapshot` ловит изменения без журнальной строки (approval-маркер →
смена стадии; правка `stop_block_budget`; запись contract).

### 6.3 Дисциплина контракта

- `_contract:"wi15/1"` — версия (фронт ловит несовместимость).
- `?slug` сужает snapshot и поток; без него — всё (swimlanes разводят по WI-2).
- `404` на неизвестный путь; **никогда 500 на данных** (fail-open).
- Все endpoint'ы read-only. Контракт стабилен — фронт сменяем (HTML сейчас,
  VueFlow позже на тот же `/stream`).

## 7. Фронт (WI-14) — раскладка и поведение

Один статический HTML; vanilla JS открывает `EventSource('/stream')`, рендерит из
`snapshot`-событий (панели) и `decision`-событий (живая лента). Раскладка (v7,
сверху вниз — «пульт ситуационной осознанности»):

1. **Header** — `GigaCode flow · observer`, session/SSE-метка, **переключатель темы
   mint/ultra-pink**, индикатор **live/pause** (pause = не авто-скроллить/не
   дёргать ленту; поток продолжает копиться).
2. **Шапка задачи (intake)** — `[task_type] slug · scope_intent`, acceptance-чипы,
   `understanding`-рестейт агента. Источник `intake.json`. Нет файла → блок скрыт.
3. **Баннер «заблокировано»** — когда есть активный блок: стадия + чего ждёт +
   готовая команда `confirm.py <stage> <slug>`. Источник — последняя `block`-запись.
   Нет блока → баннер скрыт (или тихая строка «flowing»).
4. **Vital signs** — счётчики block/ask/allow, темп (реш./мин), idle (сек с
   последней записи), длительность сессии, микс инструментов. Источник — агрегация
   журнала.
5. **Stage graph** — узлы `intake→contract→plan→verify→delivery` на responsive-flex
   (узлы + стрелки-разделители, переносятся на узкой ширине). Цвет = `stage_status`
   (done/current/locked). Под графом — строка перехода `met (✓) / unmet (☐)`.
   Пер-узловые подсказки: entry-предикаты + артефакт стадии.
6. **Budget / scope / verdict** — три карточки. Бюджет `used/limit` (лимит живой из
   конфига). Scope — `scope_globs`/`modules` (+ `out_of_contract` из verdict, если
   есть; пофайловая зелёный/красный адгезия — **best-effort**, см. §10). Вердикт —
   `result` + risk-поля + findings; нет файла → empty-state.
7. **Decision swimlanes** — лента решений по дорожкам `session/feature/agent` (WI-2),
   строка: ts, decision (badge), gate, tool, объект, reason; block/ask подсвечены.
   Чипы-фильтры all/block/ask/allow.

**fail-open в UI:** любой блок без данных показывает «нет данных»/скрыт, не ломая
страницу. Не-данные (соединение оборвалось) → индикатор `live` гаснет, оверлей
«переподключение».

### 7.1 Темы

mint (default) и ultra-pink — два блока `:root`-переменных в `<style>`, класс на
корневом `.dash`. Переключатель в шапке меняет класс; выбор хранится в
`localStorage` (на перезагрузку остаётся). Все цвета (фон, панели, чипы,
locked-узлы, тултипы) — через переменные, поэтому переключение полное и мгновенное.
Палитры: mint — фон `#0f1218`, акцент `#6fb3ff`; ultra-pink — фон `#08060a`,
акцент `#ff5cad`, block `#ff3d80`, allow остаётся мятным (тихое «ок»), без
неонового свечения.

### 7.2 Подсказки

«?»-бейдж в углу каждого блока (общее описание блока + источник данных) и
пер-узловые тултипы на узлах графа (entry-предикаты + артефакт). Реализация —
`data-tip="..."` + `:hover/:focus::after` нашими же CSS-переменными (тема-aware).
`tabindex=0` → доступно с клавиатуры. Текст живёт в DOM (не только визуально).
Zero-dep, без JS-библиотек.

## 8. Банковская поверхность / модель угроз

- **bind строго `127.0.0.1`**, **никогда `0.0.0.0`**. Loopback не выходит за хост,
  прокси/файрвол его не трогают, интернет не нужен.
- **Ноль внешних ассетов** (нет CDN/шрифтов/иконочных пакетов/VueFlow) → **ноль
  phone-home**; всё инлайн в одном HTML. Тривиально ревьюится (zero-dep Python +
  один HTML) — критично для банка.
- **Read-only**, ноль записи в enforcement-состояние/артефакты/журнал.
- Журнал несёт пути/диффы/тикеты → observer наследует чувствительность; на
  shared-машине/Citrix даже loopback бывает виден другим локальным юзерам — отметить.
- **Работает локально/автономно.** Единственная зависимость — локальный браузер к
  loopback на той же машине. Нет браузера (залоченный Citrix) → фолбэк WI-13 CLI (P7).

## 9. Границы (что НЕ делает)

- Не управляет (no approve/config/spawn из вьюшки). Не сервер истины. Не VueFlow в
  v1. Не multi-module (один observer на оба модуля — после `modules/_shared`/WI-3).
- Не push из хука (file-tail только). Не авто-спавн из хука (ручной one-liner).

## 10. Зависимости и отложенное

- **Готово сегодня:** WI-13 (collect/tail/_stage), WI-2 (swimlanes), WI-11
  (verdict), WI-20 (intake), WI-7/8 (contract/scope-поля). Не блокируется ничем.
- **Best-effort/отложено:** пофайловая scope-адгезия (зелёный/красный по каждому
  изменённому файлу) требует множества изменённых файлов. Источник без записи —
  пути из write-событий журнала (Edit/Write/MultiEdit) vs `scope_globs`; **нельзя**
  `_lib.changed_code_files` (журналит). v1 показывает `scope_globs`/`modules` +
  `out_of_contract`-счётчик из вердикта; пофайловый список — когда появится
  read-only changed-files источник. (Совпадает с «заделом» из WI-13 §3.)
- **Переезд в `modules/_shared/`** + multi-module — часть WI-3 union merge.
- **VueFlow граф-вью** — отдельная итерация на стабильный `/stream`.

## 11. Acceptance criteria

- [ ] `observer.py` поднимает `ThreadingHTTPServer` на `127.0.0.1:<port>`; `GET /`
      отдаёт встроенный HTML; `/api/snapshot` — валидный enriched Snapshot;
      `/stream` — корректный SSE (`snapshot` при connect, `decision` на новые
      строки, heartbeat).
- [ ] `snapshot` переэмитится по таймеру → смена бюджета/стадии/scope без новой
      журнальной строки видна в UI.
- [ ] Чисто read-only: прогон observer **не меняет** ни один файл (хэши до/после),
      **не** вызывает журналирующие `_lib`-функции, **не** регистрируется как хук.
- [ ] Bind только `127.0.0.1` (проверить, что `0.0.0.0` не используется); ноль
      внешних сетевых запросов из HTML (ноль внешних ассетов).
- [ ] Fail-open: пустой/битый журнал, отсутствующие `intake.json`/`verdict.json`/
      `contract.json`, отсутствие блока — UI не падает, блоки показывают «нет
      данных»/скрыты; сервер не 500-ит на данных.
- [ ] Темы mint/ultra-pink переключаются в шапке, выбор сохраняется в `localStorage`;
      переключение полное (все цвета через переменные).
- [ ] Подсказки: «?» на каждом блоке + пер-узловые на графе; работают по hover и
      `:focus` (клавиатура).
- [ ] Юнит-тесты: `enrich`/vitals/blocker-вывод на фикстурах журнала (паттерн
      `GIGACODE_ROOT`-override); SSE-форматирование событий; парсинг `/api/snapshot`.
- [ ] **Live-приёмка:** запустить observer на реальном стенде
      (`F:\Coding\qwen_flow_test\greeter`, живой `decisions.jsonl`), открыть в
      браузере, увидеть поток реальных решений, граф, бюджет, swimlanes.

## 12. Открытые вопросы

- Tail-loop: поток-на-клиента или один общий broadcaster + очереди? (broadcaster
  экономнее на N клиентов; для локального 1–2 окон оба ок).
- Таймер `snapshot`: фиксированные ~2 с или слать только при изменении (diff против
  последнего, экономия трафика)?
- `--slug` по умолчанию: авто-выбор свежего (как WI-13) или показывать все swimlanes
  сразу?
- Порт по умолчанию (8787?) и поведение при занятом порте (инкремент/ошибка).
