# WI-22: `gate_stage_order` — Implementation Plan

> **For agentic workers:** реализуйте задача-за-задачей; шаги в checkbox-формате
> (`- [ ]`). Каждый шаг — атомарный коммит. Не редактируйте `.gigacode/**` в обход
> человека — конечный артефакт ставит человек (см. Task 3).
>
> **Целевое место в репо:** `docs/superpowers/plans/2026-06-23-wi22-gate-stage-order.md`
> **Реализует:** RFC ADR-8 (энфорсмент стадий и непробиваемые остановки), WI-22.
> **Модуль-цель:** `modules/development` (паттерн переносится в `modules/analytics`).

**Goal:** сделать переходы между стадиями флоу детерминированно
энфорсимыми, а «провалидируй» — **жёсткой остановкой**. Запись артефакта стадии
N+1 блокируется, пока не выполнены `entry_requires` этой стадии. Запрос
валидации не блокируется — блокируется только *продолжение*, поэтому «попросил
проверить и побежал дальше» становится структурно невозможным.

**Architecture:** новый гейт `gate_stage_order` на `PreToolUse`
(`WriteFile|Edit|NotebookEdit`), `safety_critical` (fail-closed). Источник истины
о пройденных стадиях — **сами артефакты и approval-маркеры**, а не мутабельное
поле `status` манифеста (нет второго состояния → нечему рассинхронизироваться,
P5). Конфигурация — декларативный `.gigacode/stages.json` (gate-owned,
self-protected git_guard'ом). Подтверждение человеком — out-of-band `confirm.py`,
который агент запустить не может (git_guard режет `python .gigacode/...`).

**Tech Stack:** Python 3, идиомы существующих гейтов (`run(event)` + `_lib`,
UTF-8 `main()`), JSON-конфиг, тесты в стиле `scripts/test_gates.py`
(`GIGACODE_ROOT`-override).

---

## Границы v1 (явное решение по скоупу)

`gate_stage_order` в v1 энфорсит **порядок workflow-артефактов**
(intake → contract → plan → verify → delivery), все они живут на детерминированных
slug-несущих путях (`docs/development/<slug>/**`, `openspec/changes/<slug>/**`).
Slug извлекается из пути.

**Записи исходного кода (стадия implement) гейт НЕ трогает** — они под
`gate_scope_guard` (WI-8, scope контракта). Это снимает проблему «какому таску
принадлежит этот `.kt`» и при этом бьёт точно по текущей боли: «просит
провалидировать и бежит дальше» — это про workflow-артефакты (verify → delivery),
а не про исходники. Source-ordering через active-task-pointer — отдельное
расширение после WI-8.

Канал: гейт смотрит file-tool записи. Shell-канал (`echo > file`) закрыт
`git_guard` (защита путей), stage-order на shell — задокументированный остаток
(как у `gate_spec_bootstrap`).

---

## File Structure

- Create `modules/development/.gigacode/stages.json` — декларативная stage-map.
- Create `modules/development/.gigacode/hooks/gates/gate_stage_order.py` — гейт.
- Create `modules/development/.gigacode/hooks/confirm.py` — out-of-band подтверждение человеком.
- Create `modules/development/.gigacode/approvals/.gitkeep` — каталог маркеров.
- Edit `modules/development/.gigacode/hooks/router.config.json` — маршрут гейта.
- Edit `modules/development/.gitignore` — игнор runtime-маркеров approvals.
- Edit `modules/development/.gigacode/skills/development-flow/SKILL.md` — поведенческая инструкция про явные остановки.
- Create `modules/development/scripts/test_stage_order.py` — тесты гейта.
- Edit `modules/development/scripts/smoke-check.sh` / `.ps1` — round-trip гейта в smoke.

Все пути ниже относительны `modules/development/`.

---

## Task 1: Stage-map (`stages.json`)

**Files:** Create `.gigacode/stages.json`

- [ ] **Step 1: создать декларативную карту стадий.**

```json
{
  "version": 1,
  "stages": [
    {
      "id": "intake",
      "order": 0,
      "writes": ["docs/development/*/intake.json"],
      "entry_requires": []
    },
    {
      "id": "contract",
      "order": 1,
      "writes": ["docs/development/*/contract.json"],
      "entry_requires": [
        {"type": "approval", "stage": "intake"}
      ]
    },
    {
      "id": "plan",
      "order": 2,
      "writes": [
        "openspec/changes/*/proposal.md",
        "openspec/changes/*/design.md",
        "openspec/changes/*/tasks.md"
      ],
      "entry_requires": [
        {"type": "file_exists", "artifact": "docs/development/<slug>/contract.json"}
      ]
    },
    {
      "id": "verify",
      "order": 3,
      "writes": ["docs/development/*/verdict.json"],
      "entry_requires": [
        {"type": "file_exists", "artifact": "openspec/changes/<slug>/tasks.md"}
      ]
    },
    {
      "id": "delivery",
      "order": 4,
      "writes": ["docs/development/*/pr-summary.md"],
      "entry_requires": [
        {"type": "verdict_pass", "artifact": "docs/development/<slug>/verdict.json"}
      ]
    }
  ]
}
```

Заметки по дизайну:
- **`contract` гейтится `approval:intake`** — это understanding-checkpoint
  (ADR-7/WI-21): человек подтвердил, что агент верно понял задачу, до того как
  замораживать scope. Единственный человек-stop в v1.
- **`delivery` гейтится `verdict_pass`** — машинная остановка: нельзя писать
  pr-summary, пока verifier не дал `pass`. Это и есть «нельзя побежать дальше
  без валидации».
- `plan`/`verify` в v1 гейтятся структурно (`file_exists`). Когда приедут
  contract-stamp/plan-stamp (WI-7/WI-21), сюда добавляются
  `{"type":"approval","stage":"contract"}` / `"plan"` — контракт предиката не
  меняется, правится только эта карта.
- `<slug>` в `artifact` резолвится гейтом из пути записи.

---

## Task 2: Гейт `gate_stage_order.py`

**Files:** Create `.gigacode/hooks/gates/gate_stage_order.py`

- [ ] **Step 2: реализовать гейт.** Пути считаются через `_lib.root()` внутри
  функций (не module-level) — чтобы тесты могли переопределять `GIGACODE_ROOT`.

```python
#!/usr/bin/env python3
"""gate_stage_order: enforce workflow-stage ordering and explicit stops.

A write to a stage's owned artifact is allowed only when that stage's
entry_requires all hold. Confirmations are READ from artifacts/approval
markers (the source of truth) — not from a mutable manifest status field,
so there is no second state to desync. PreToolUse + fail-closed: the agent
cannot 'ask to validate and run ahead' because the next-stage write blocks
until its confirmation exists. Not under stop_block_budget (PreToolUse, not Stop).

Self-contained except _lib. Governs file-tool writes to the workflow tree only;
shell-channel writes are covered by git_guard (path protection) — stage-order on
shell is a documented residual. Source-code writes are governed by gate_scope_guard.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib

ESCAPE = ('If stages.json itself is broken, set "disableAllHooks": true in '
          ".gigacode/settings.json temporarily and report the issue.")

DEV_SLUG_RE = re.compile(r"(?:^|/)docs/development/([^/]+)/", re.IGNORECASE)
OSX_SLUG_RE = re.compile(r"(?:^|/)openspec/changes/([^/]+)/", re.IGNORECASE)


def _stages_path():
    return os.path.join(_lib.root(), ".gigacode", "stages.json")


def _approvals_dir():
    return os.path.join(_lib.root(), ".gigacode", "approvals")


def _norm(p):
    p = str(p).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def load_stages():
    with open(_stages_path(), "r", encoding="utf-8") as handle:
        data = json.load(handle)
    stages = data.get("stages")
    if not isinstance(stages, list):
        raise ValueError("stages.json: 'stages' must be a list")
    return stages


def slug_from_path(path):
    for rx in (DEV_SLUG_RE, OSX_SLUG_RE):
        m = rx.search(path)
        if m:
            return m.group(1)
    return ""


def target_stage(path, stages):
    """First stage whose writes-glob matches the path; None if ungoverned."""
    for st in stages:
        for glob in st.get("writes", []):
            if _lib.matches_globs(path, [glob]):
                return st
    return None


def _artifact_path(rel, slug):
    rel = rel.replace("<slug>", slug)
    return os.path.join(_lib.root(), *rel.split("/"))


def predicate_holds(pred, slug):
    """Return (ok, label). Unknown type raises -> caller fails closed."""
    ptype = pred.get("type")
    if ptype == "approval":
        stage = pred.get("stage", "")
        marker = os.path.join(_approvals_dir(), slug, stage + ".ok")
        return os.path.isfile(marker), "approval:" + stage
    if ptype == "file_exists":
        target = _artifact_path(pred.get("artifact", ""), slug)
        return os.path.isfile(target), "file_exists:" + pred.get("artifact", "")
    if ptype == "verdict_pass":
        target = _artifact_path(pred.get("artifact", ""), slug)
        try:
            with open(target, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return False, "verdict:pass"
        return data.get("result") == "pass", "verdict:pass"
    raise ValueError("unknown predicate type: " + repr(ptype))


def run(event):
    path = _norm(_lib.path_from_event(event))
    if not path:
        return {"decision": "allow"}
    in_flow_tree = bool(DEV_SLUG_RE.search(path) or OSX_SLUG_RE.search(path))
    try:
        stages = load_stages()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        # fail-closed ONLY if the write targets the workflow tree; otherwise a
        # missing stages.json must not brick unrelated edits.
        if in_flow_tree:
            return {"decision": "block", "reason": "stages.json unreadable: %s. %s" % (exc, ESCAPE)}
        return {"decision": "allow"}
    st = target_stage(path, stages)
    if not st:
        return {"decision": "allow"}  # not a governed artifact (journal, notes, src)
    slug = slug_from_path(path)
    if not slug:
        return {"decision": "block", "reason": (
            "Stage-governed write '%s' without a resolvable task slug. %s" % (path, ESCAPE))}
    unmet = []
    try:
        for pred in st.get("entry_requires", []):
            ok, label = predicate_holds(pred, slug)
            if not ok:
                unmet.append(label)
    except ValueError as exc:
        return {"decision": "block", "reason": "stage predicate error: %s. %s" % (exc, ESCAPE)}
    if unmet:
        return {"decision": "block", "reason": (
            "Стадия '%s' для '%s' ещё не разблокирована: не выполнено %s. "
            "Это явная остановка — заверши/подтверди предыдущую стадию. "
            "Подтверждение человеком (вне сессии агента): "
            "python .gigacode/hooks/confirm.py <stage> %s"
            % (st.get("id"), slug, ", ".join(unmet), slug))}
    return {"decision": "allow"}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    event = _lib.stdin_event()
    print(json.dumps(run(event or {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

---

## Task 3: Подтверждение человеком (`confirm.py`)

**Files:** Create `.gigacode/hooks/confirm.py`, `.gigacode/approvals/.gitkeep`

- [ ] **Step 3a: реализовать out-of-band recorder.** Пишет маркер под
  `.gigacode/approvals/<slug>/<stage>.ok`. **Агент его запустить не может**:
  `python .gigacode/hooks/confirm.py ...` — это команда с writer-интерпретатором,
  именующая `.gigacode`-путь, её режет `_self_protect_catch_all` в `git_guard`.
  Запускает только человек в своём терминале (без хуков). Это и делает approval
  P6-safe — самоподтверждение невозможно.

```python
#!/usr/bin/env python3
"""confirm.py: out-of-band HUMAN approval recorder for stage transitions.

Writes an approval marker the AGENT cannot create (.gigacode/** is blocked for
agent writes/commands by git_guard), so approval cannot be self-granted (P6).
v1 marker is a timestamped JSON file; an HMAC stamp slots in here later
(WI-7/WI-21) without changing gate_stage_order's predicate contract.

Usage:  python .gigacode/hooks/confirm.py <stage> <slug>
"""
import json
import os
import sys
import time

ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
APPROVALS = os.path.join(ROOT, ".gigacode", "approvals")


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: confirm.py <stage> <slug>\n")
        return 2
    stage, slug = argv
    if not stage.isidentifier() and not stage.replace("-", "").isalnum():
        sys.stderr.write("invalid stage name\n")
        return 2
    out_dir = os.path.join(APPROVALS, slug)
    os.makedirs(out_dir, exist_ok=True)
    marker = os.path.join(out_dir, stage + ".ok")
    with open(marker, "w", encoding="utf-8") as handle:
        json.dump({"stage": stage, "slug": slug,
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "by": os.environ.get("USER") or os.environ.get("USERNAME", "unknown")},
                  handle, ensure_ascii=False)
    sys.stdout.write("approved: %s / %s -> %s\n"
                     % (stage, slug, os.path.relpath(marker, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 3b:** создать `.gigacode/approvals/.gitkeep` (пустой).

---

## Task 4: Маршрут в роутере и игнор

**Files:** Edit `.gigacode/hooks/router.config.json`, `.gitignore`

- [ ] **Step 4a: добавить маршрут** в `routes` (имя гейта = stem файла,
  `safety_critical` → fail-closed агрегация в роутере):

```json
{
  "event": "PreToolUse",
  "tool_pattern": "^(WriteFile|Edit|NotebookEdit)$",
  "gates": ["gate_stage_order"],
  "safety_critical": true
}
```

`settings.json` уже шлёт `PreToolUse` Edit/WriteFile в `router.py` — менять
settings не нужно. Гейт `gate_stage_order` НЕ на Stop → автоматически вне
`stop_block_budget` (его нельзя «пересидеть»).

- [ ] **Step 4b: игнор runtime-маркеров** — добавить в `.gitignore`:

```gitignore
.gigacode/approvals/
```

(approvals — локальное состояние прогона, как `.gigacode/logs/`.)

---

## Task 5: Поведенческая инструкция агенту

**Files:** Edit `.gigacode/skills/development-flow/SKILL.md`

- [ ] **Step 5:** в раздел про стадии/остановки добавить (чтобы агент не воевал с
  гейтом, а корректно уступал ход):

```text
## Явные остановки (enforced)

Переходы между стадиями энфорсятся `gate_stage_order`. На точке валидации
ОСТАНОВИСЬ и уступи ход — не продолжай в том же ответе. Запись артефакта
следующей стадии будет заблокирована, пока:
- intake → contract: человек не подтвердит понимание задачи
  (`python .gigacode/hooks/confirm.py intake <slug>`);
- verify → delivery: verifier не запишет verdict.json с result=pass.

Запрос валидации не блокируется — блокируется только продолжение. Не пытайся
обойти остановку; дождись подтверждения или прохождения проверки.
```

---

## Task 6: Тесты

**Files:** Create `scripts/test_stage_order.py`; Edit `scripts/smoke-check.sh`/`.ps1`

- [ ] **Step 6a: контрактные тесты гейта** (паттерн `GIGACODE_ROOT`-override,
  как в `test_gates.py`). Покрыть минимум:

```text
[ ] intake-запись без requires                         -> allow
[ ] contract без approval:intake                        -> block
[ ] contract при наличии approvals/<slug>/intake.ok     -> allow
[ ] plan без contract.json                              -> block
[ ] plan при contract.json                              -> allow
[ ] verify без openspec/changes/<slug>/tasks.md         -> block
[ ] delivery при verdict result=fail                    -> block
[ ] delivery при verdict result=pass                    -> allow
[ ] запись в раннюю стадию после поздних подтверждений  -> allow (fix-up вверх)
[ ] журнал/notes/src путь (вне writes-глобов)           -> allow
[ ] stages.json битый, путь в flow-дереве               -> block (fail-closed)
[ ] stages.json битый, путь вне flow-дерева             -> allow
[ ] flow-путь без резолва slug                          -> block
[ ] неизвестный тип предиката                           -> block
```

Скелет одного кейса:

```python
import importlib, json, os, tempfile

def run_gate(event, root):
    os.environ["GIGACODE_ROOT"] = root
    import gate_stage_order as g
    importlib.reload(g)
    return g.run(event)

def test_contract_blocked_without_intake_approval(tmp):
    # tmp содержит .gigacode/stages.json (копия Task 1), без approvals/<slug>/intake.ok
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
          "tool_input": {"file_path": "docs/development/card-blocking/contract.json"}}
    assert run_gate(ev, tmp)["decision"] == "block"
```

- [ ] **Step 6b: round-trip в smoke-check** — добавить вызов `gate_stage_order.py`
  с заблокированным кейсом (как уже сделано для `run-hook.cjs` deny), чтобы CI
  ловил регресс конфигурации.

---

## Definition of Done

- [ ] `gate_stage_order` зарегистрирован, `safety_critical`, проходит все кейсы Task 6.
- [ ] `confirm.py` создаёт маркер; **попытка агента** запустить его режется
  `git_guard` (проверить отдельным тестом: команда `python .gigacode/hooks/confirm.py ...`
  → `block` в `git_guard`).
- [ ] Запись `delivery`-артефакта при `verdict.result != pass` → `block`.
- [ ] Запись `contract`-артефакта без `approval:intake` → `block`; после
  `confirm.py intake <slug>` → `allow`.
- [ ] Битый `stages.json` не бричит правки вне flow-дерева.
- [ ] smoke-check (Linux + Windows) зелёный, включает round-trip гейта.

---

## Резолв открытого вопроса RFC

Этот план **резолвит** открытый вопрос «stage-map в `router.config.json` или
отдельный `stages.json`»: выбран **отдельный `.gigacode/stages.json`** (gate-owned,
self-protected, не раздувает router-конфиг). Обновить §10 RFC соответствующе.

## Отложено (вне WI-22)

- **Source-ordering** (implement-записи по active-task-pointer) — после WI-8.
- **HMAC-stamp** для `approval` (сейчас — file-маркер) — WI-7/WI-21; контракт
  предиката `approval` не меняется, добавляется проверка подписи в `predicate_holds`.
- **`plan-only` mode:** какие стадии пропускаются (нет implement → нет verify/
  delivery записей) — уточнить в WI-20/intake (`mode` уже в `intake.json`).
- Перенос гейта в `modules/analytics` (свой `stages.json` под status-машину
  `scoping→draft→confirmed→complete`) — после стабилизации в development.
