# Analytics Overhaul — Phase 3 (MCP + Docs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the optional context/MCP providers into the analytics template — Serena (semantic search), Graphify (module map), Context7 (library docs) — and rewrite the README onto the Phase-2 reality (3 agents, two-layer output, 9-step pipeline), all with documented fallbacks and none required by smoke checks.

**Architecture:** Serena is declared in `.gigacode/settings.json` (`mcpServers.serena`) with async reminder hooks (remind/auto-approve/activate/cleanup) that no-op when `serena` is absent; a `.serena/project.yml` scaffold ships in the module. A new stdlib-only `scripts/build_module_map.py` renders Graphify's `graphify-out/graph.json` into `.gigacode/context/module-map.md` — the exact file the Phase-1 `gate_context_inject` already injects (it silently skips the file when absent, so nothing breaks without Graphify). Context7 is **documented as a README copy-paste snippet only** — it is deliberately NOT placed in `settings.json` (design Decision 8: "zero until self-enabled"). The README is rewritten to match Phase 2.

**Tech Stack:** Python 3 stdlib (json, argparse, collections), Serena MCP (`serena-agent` via `uv`), Graphify (`graphifyy` pip pkg, networkx node-link JSON), Context7 MCP (`npx @upstash/context7-mcp`, Node 18+), Bash + PowerShell smoke checks. All MCP/tool deps optional.

**Reference spec:** `docs/superpowers/specs/2026-06-11-gigacode-analytics-flow-overhaul-design.md` (Decision 8 "Tools and MCP" + "Settings"). **Predecessor:** Phase 2 plan `docs/superpowers/plans/2026-06-13-analytics-overhaul-phase2-flow.md` (executed; branch `feature/analytics-overhaul` HEAD `f14f5f2`).

**Base branch / working directory:** `feature/analytics-overhaul`, worktree `F:/Coding/gigacode_agents/.worktrees/analytics-overhaul`. **All tasks run from the worktree root; every file path below is prefixed `modules/analytics/`.** The plan document itself lives on `master`.

**Co-author line for every commit:**
```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
```

---

## What Phase 1 + Phase 2 already provide (do NOT re-do)

- Hook router + 6 gates (untouched this phase). `gate_context_inject` **already reads** `MODULE_MAP = .gigacode/context/module-map.md` (relative to `_lib.root()`) and injects it on SessionStart/SubagentStart; missing file → silently skipped. This phase only adds the *producer* of that file; the gate needs no change.
- 3 agents (`code-mapping`, `documentation`, `verifier`); SKILL 9-step pipeline; rules; `openspec/`; final-tree skeleton; templates. repomix already purged from agents/rules (Phase 2). **README still names 5 agents + repomix — this phase fixes that.**
- `settings.json` has `ui`, `permissions`, `hooks` (router entries) — but **no `mcpServers` block yet**. Phase 3 adds it.
- Suites green at: `test_router` 28, `test_gates` 60, both smoke checks pass.

## Verified facts (research 2026-06-13, ported from dev-flow)

- **Serena** install: `uv tool install -p 3.13 serena-agent` (needs `uv`); MCP server cmd `serena start-mcp-server --context ide --project-from-cwd`; key tool `mcp__serena__find_symbol`. Reminder hooks: `serena-hooks remind|auto-approve|activate|cleanup --client=claude-code`. All hook entries use `"async": true` so a missing `serena` binary never blocks the flow.
- **Graphify**: pip pkg `graphifyy`; skill `/graphify .`; output `graphify-out/graph.json` (networkx node-link: `nodes[{id,label,community,source_file?}]`, `links[{source,target,relation}]`, `hyperedges[{id,label,nodes}]`). Community human-labels are NOT in the JSON — the builder derives module identity from top-degree members. `build_module_map.py` is stdlib-only/offline (reads the JSON graphify already wrote; never calls graphify). Missing/empty graph → exit 1 (humans + smoke notice); runtime gate path unaffected (gate reads the `.md`, not the `.json`).
- **Context7** MCP: `npx -y @upstash/context7-mcp` (Node 18+); optional `--api-key`. **Analytics keeps it README-only, NOT in `settings.json`** (design Decision 8; user: "analysts hate installing things").
- `gate_context_inject` test fixture asserts the map starts with `# Module Map`; `build_module_map.py` emits exactly that header.
- Smoke style: `.sh` uses `set -euo pipefail` + a `required=(...)` array + bare commands; `.ps1` uses a `$required = @(...)` array + `$LASTEXITCODE -ne 0 → throw` after each python suite. New invocations copy these styles.
- Test style: `python scripts/test_*.py` use a module-level `PASSED` counter + `check(name, condition, detail)` raising `SystemExit` (explicit raise so `python -O` cannot neuter it).

## File structure (Phase 3)

Created:
- `modules/analytics/scripts/build_module_map.py` — graph.json → module-map.md (render only; never analyze).
- `modules/analytics/scripts/test_module_map.py` — offline tests for the builder.
- `modules/analytics/.serena/project.yml` — per-project Serena scaffold.

Modified:
- `modules/analytics/.gitignore` — ignore `graphify-out/`.
- `modules/analytics/.gigacode/settings.json` — add `mcpServers.serena` + async serena reminder hooks. (No Context7.)
- `modules/analytics/README.md` — full rewrite (3 agents, two-layer, 9-step, Serena/Graphify/Context7/Atlassian + fallbacks; repomix gone).
- `modules/analytics/scripts/smoke-check.sh` + `.ps1` — required files + `test_module_map.py` invocation + README-repomix-free assertion.

Not touched: the gates, `router.config.json`, `quality-gates.json`, agents, skill, command, rules, openspec, templates, final-tree skeleton (all Phase 1/2).

---

### Task 1: Module-map builder + tests (Graphify → context)

**Files:**
- Create: `modules/analytics/scripts/build_module_map.py`
- Create: `modules/analytics/scripts/test_module_map.py`
- Modify: `modules/analytics/.gitignore`

- [ ] **Step 1: Write the failing tests — create `modules/analytics/scripts/test_module_map.py`**

```python
#!/usr/bin/env python3
"""Offline tests for scripts/build_module_map.py. Run from modules/analytics:
    python scripts/test_module_map.py"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER = os.path.join(ROOT, "scripts", "build_module_map.py")
PASSED = 0


def check(name, condition, detail=""):
    # explicit raise (not assert) so python -O cannot neuter the suite
    global PASSED
    if not condition:
        raise SystemExit(f"FAIL {name}: {detail}")
    PASSED += 1
    print(f"ok: {name}")


def sample_graph():
    return {
        "nodes": [
            {"id": "a_PaymentService", "label": "PaymentService",
             "community": 0, "source_file": "src/PaymentService.kt"},
            {"id": "a_PaymentRepo", "label": "PaymentRepo",
             "community": 0, "source_file": "src/PaymentRepo.kt"},
            {"id": "b_FraudCheck", "label": "FraudCheck",
             "community": 1, "source_file": "src/FraudCheck.kt"},
        ],
        "links": [
            {"source": "a_PaymentService", "target": "a_PaymentRepo",
             "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "a_PaymentService", "target": "b_FraudCheck",
             "relation": "shares_data_with", "confidence": "INFERRED"},
        ],
        "hyperedges": [
            {"id": "payment_flow", "label": "Payment flow",
             "nodes": ["a_PaymentService", "a_PaymentRepo", "b_FraudCheck"],
             "relation": "participate_in"},
        ],
    }


def run_builder(tmp, graph=None, extra_args=None):
    """Run the builder CLI; returns (rc, combined_output, map_text)."""
    graph_path = os.path.join(tmp, "graph.json")
    if graph is not None:
        with open(graph_path, "w", encoding="utf-8") as handle:
            json.dump(graph, handle)
    out_path = os.path.join(tmp, "module-map.md")
    cmd = [sys.executable, BUILDER, "--graph", graph_path, "--out", out_path]
    cmd += extra_args or []
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", timeout=30)
    text = ""
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    return proc.returncode, proc.stdout, text


def main():
    with tempfile.TemporaryDirectory(prefix="module-map-test-") as tmp:
        rc, out, text = run_builder(tmp, sample_graph())
        check("map_builds", rc == 0, out)
        check("map_header", text.startswith("# Module Map"), text[:80])
        check("map_module_section", "## Module 0 (2 nodes)" in text, text)
        check("map_key_symbol", "PaymentService (src/PaymentService.kt)" in text, text)
        check("map_bridge",
              "PaymentService (M0) --shares_data_with--> FraudCheck (M1)" in text, text)
        check("map_hyperedge", "Payment flow: " in text, text)

    with tempfile.TemporaryDirectory(prefix="module-map-test-") as tmp:
        rc, out, text = run_builder(tmp, sample_graph(), ["--max-lines", "5"])
        check("map_line_cap", rc == 0 and "truncated" in text, text)

    with tempfile.TemporaryDirectory(prefix="module-map-test-") as tmp:
        rc, out, _ = run_builder(tmp, None)  # graph file absent
        check("map_missing_graph_fails", rc != 0, (rc, out))
        rc, out, _ = run_builder(tmp, {"nodes": [], "links": []})
        check("map_empty_graph_fails", rc != 0, (rc, out))

    print(f"\nAll {PASSED} module-map checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python modules/analytics/scripts/test_module_map.py
```
Expected: FAIL — `map_builds` fails because `scripts/build_module_map.py` does not exist yet (subprocess rc != 0).

- [ ] **Step 3: Create `modules/analytics/scripts/build_module_map.py`**

```python
#!/usr/bin/env python3
"""Build .gigacode/context/module-map.md from graphify-out/graph.json.

The map is injected into agent context by gate_context_inject (SessionStart /
SubagentStart), so it must stay compact: communities with their key symbols,
cross-module links and named flows, capped at --max-lines.

Stdlib-only and offline: reads the JSON graphify already wrote; never calls
graphify itself. A missing or empty graph exits 1 so humans and smoke runs
notice, while the gate simply skips the absent map file at runtime."""
import argparse
import json
import os
import sys
from collections import defaultdict


def load_graph(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        sys.exit(f"module-map: cannot read graph: {exc}")
    except json.JSONDecodeError as exc:
        sys.exit(f"module-map: graph is not valid JSON: {exc}")
    if not isinstance(data, dict) or not data.get("nodes"):
        sys.exit("module-map: graph has no nodes; run /graphify first")
    return data


def build_lines(data, graph_path):
    nodes = {n["id"]: n for n in data.get("nodes", [])
             if isinstance(n, dict) and "id" in n}
    links = [lnk for lnk in data.get("links", []) if isinstance(lnk, dict)]
    degree = defaultdict(int)
    for link in links:
        # count only endpoints that exist: dangling links must not inflate
        # a real node's rank in the degree sort below
        for endpoint in (link.get("source"), link.get("target")):
            if endpoint in nodes:
                degree[endpoint] += 1
    communities = defaultdict(list)
    for node in nodes.values():
        communities[node.get("community")].append(node)

    lines = ["# Module Map", "",
             f"Generated from {graph_path}: {len(nodes)} nodes, "
             f"{len(links)} edges, {len(communities)} communities.", ""]
    for cid, members in sorted(communities.items(),
                               key=lambda kv: (-len(kv[1]), str(kv[0]))):
        members.sort(key=lambda n: -degree[n["id"]])
        cid_label = "unassigned" if cid is None else cid
        lines.append(f"## Module {cid_label} ({len(members)} nodes)")
        for node in members[:8]:
            label = node.get("label") or node["id"]
            src = node.get("source_file") or ""
            lines.append(f"- {label}" + (f" ({src})" if src else ""))
        lines.append("")

    bridges = []
    for link in links:
        a = nodes.get(link.get("source"))
        b = nodes.get(link.get("target"))
        if not a or not b or a.get("community") == b.get("community"):
            continue
        bridges.append(f"- {a.get('label') or a['id']} (M{a.get('community')}) "
                       f"--{link.get('relation', '?')}--> "
                       f"{b.get('label') or b['id']} (M{b.get('community')})")
    if bridges:
        lines.append("## Cross-module links")
        lines.extend(bridges[:10])
        lines.append("")

    hyper = [h for h in data.get("hyperedges", []) if isinstance(h, dict)]
    if hyper:
        lines.append("## Flows / groups")
        for edge in hyper[:10]:
            participants = [(nodes.get(nid) or {}).get("label", nid)
                            for nid in edge.get("nodes", [])[:6]]
            lines.append(f"- {edge.get('label') or edge.get('id', '?')}: "
                         + ", ".join(participants))
        lines.append("")
    return lines


def main():
    parser = argparse.ArgumentParser(
        description="Render graphify graph.json into .gigacode/context/module-map.md. "
                    "Run from the repo root: the default paths are relative.")
    parser.add_argument("--graph", default=os.path.join("graphify-out", "graph.json"))
    parser.add_argument("--out",
                        default=os.path.join(".gigacode", "context", "module-map.md"))
    parser.add_argument("--max-lines", type=int, default=120)
    args = parser.parse_args()
    if args.max_lines < 4:
        sys.exit("module-map: --max-lines must be >= 4 (the header alone takes 4 lines)")

    data = load_graph(args.graph)
    lines = build_lines(data, args.graph.replace("\\", "/"))
    total = len(lines)
    if total > args.max_lines:
        lines = lines[:args.max_lines] + ["", "(truncated: --max-lines reached)"]
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    note = f"{len(lines)} lines" if total <= args.max_lines \
        else f"{args.max_lines} of {total} lines, truncated"
    print(f"module-map: wrote {args.out} ({note})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python modules/analytics/scripts/test_module_map.py | tail -1
```
Expected: `All 9 module-map checks passed`.

- [ ] **Step 5: Ignore the graphify output dir — append to `modules/analytics/.gitignore`**

The file currently is:
```
__pycache__/
*.pyc
.gigacode/logs/
.gigacode/tmp/
```
Append one line so it becomes:
```
__pycache__/
*.pyc
.gigacode/logs/
.gigacode/tmp/
graphify-out/
```

- [ ] **Step 6: Regression — existing suites stay green**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python modules/analytics/scripts/test_gates.py | tail -1
python modules/analytics/scripts/test_router.py | tail -1
```
Expected: `All 60 gate checks passed` and `All 28 router checks passed`.

- [ ] **Step 7: Commit**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git add modules/analytics/scripts/build_module_map.py modules/analytics/scripts/test_module_map.py modules/analytics/.gitignore
git commit -m "Add module-map builder rendering graphify graph for context injection

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Serena per-project scaffold

**Files:**
- Create: `modules/analytics/.serena/project.yml`

- [ ] **Step 1: Create `modules/analytics/.serena/project.yml` with EXACTLY:**

```yaml
# Serena per-project configuration.
# Generated by the GigaCode analytics template.
# See https://oraios.github.io/serena for full options.

# project_name is used in Serena's dashboard and logs.
# Replace with your actual project name.
project_name: my-project

# ignored_paths lists directories Serena will skip when indexing.
# Adjust for your build output, dependency, and generated-file paths.
ignored_paths:
  - node_modules
  - .git
  - dist
  - build
  - target
  - __pycache__
  - .venv
  - venv
  - graphify-out
```

- [ ] **Step 2: Verify (stdlib-only — no PyYAML dependency)**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
test -f modules/analytics/.serena/project.yml && grep -q '^project_name:' modules/analytics/.serena/project.yml && grep -q 'ignored_paths:' modules/analytics/.serena/project.yml && echo OK
```
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git add modules/analytics/.serena/project.yml
git commit -m "Add Serena per-project config scaffold to analytics template

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Wire Serena into `settings.json` (mcpServers + async reminder hooks)

Replaces `.gigacode/settings.json` wholesale (safer than surgical JSON edits). This adds a new `mcpServers` block (serena only — NOT Context7) and four async `serena-hooks` entries alongside the existing router hooks. Everything else (ui, permissions, all router hook entries) is preserved byte-for-byte.

**Files:**
- Modify: `modules/analytics/.gigacode/settings.json`

- [ ] **Step 1: Replace `modules/analytics/.gigacode/settings.json` with EXACTLY:**

```json
{
  "ui": {
    "showCitations": true,
    "showLineNumbers": true,
    "hideTips": true,
    "shellOutputMaxLines": 20
  },
  "permissions": {
    "allow": [
      "Read",
      "Bash(git status*)",
      "Bash(git branch*)",
      "Bash(git diff*)",
      "Bash(git log*)",
      "Bash(rg *)",
      "Bash(graphify*)",
      "Bash(python .gigacode/hooks/*)",
      "Bash(python scripts/*)",
      "Edit(docs/features/**)",
      "Edit(openspec/specs/**)",
      "Edit(analytics/**)",
      "Edit(architecture/**)"
    ],
    "ask": [
      "Edit",
      "Bash(git add*)",
      "Bash(git commit*)"
    ],
    "deny": [
      "Read(.env)",
      "Read(.env.*)",
      "Bash(rm -rf *)",
      "Bash(del /s *)",
      "Bash(format *)"
    ]
  },
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=UserPromptSubmit"}
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=SessionStart"}
        ]
      },
      {
        "matcher": "",
        "async": true,
        "hooks": [
          {"type": "command", "command": "serena-hooks activate --client=claude-code", "timeout": 10000}
        ]
      }
    ],
    "SubagentStart": [
      {
        "matcher": "code-mapping|documentation",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=SubagentStart"}
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "^(Bash|Shell|WriteFile|Edit)$",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=PreToolUse"}
        ]
      },
      {
        "matcher": "",
        "async": true,
        "hooks": [
          {"type": "command", "command": "serena-hooks remind --client=claude-code", "timeout": 5000}
        ]
      },
      {
        "matcher": "mcp__serena__*",
        "async": true,
        "hooks": [
          {"type": "command", "command": "serena-hooks auto-approve --client=claude-code", "timeout": 5000}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "^(WriteFile|Edit)$",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=PostToolUse"}
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {"type": "command", "command": "python .gigacode/hooks/router.py --event=Stop"}
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "async": true,
        "hooks": [
          {"type": "command", "command": "serena-hooks cleanup --client=claude-code", "timeout": 5000}
        ]
      }
    ]
  },
  "mcpServers": {
    "serena": {
      "command": "serena",
      "args": ["start-mcp-server", "--context", "ide", "--project-from-cwd"]
    }
  }
}
```

- [ ] **Step 2: Verify JSON validity + serena present + Context7 absent + router untouched**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python -m json.tool modules/analytics/.gigacode/settings.json >/dev/null && echo "JSON OK"
python -c "import json; d=json.load(open('modules/analytics/.gigacode/settings.json',encoding='utf-8')); assert 'serena' in d['mcpServers'], 'no serena'; assert 'context7' not in d['mcpServers'], 'context7 must not be in settings'; assert d['hooks']['PreToolUse'][0]['hooks'][0]['command']=='python .gigacode/hooks/router.py --event=PreToolUse', 'router PreToolUse changed'; print('SETTINGS OK')"
```
Expected: prints `JSON OK` then `SETTINGS OK`.

- [ ] **Step 3: Run both smoke checks (router unaffected — must still pass)**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul/modules/analytics && bash scripts/smoke-check.sh 2>&1 | tail -1; cd ../../..
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul/modules/analytics && powershell -NoProfile -File scripts/smoke-check.ps1 2>&1 | tail -1; cd ../../..
```
Expected: each prints `Analytics module smoke check passed.`

- [ ] **Step 4: Commit**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git add modules/analytics/.gigacode/settings.json
git commit -m "Declare Serena MCP and async reminder hooks in analytics settings

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Rewrite `README.md` (3 agents, two-layer, 9-step, providers + fallbacks)

**Files:**
- Modify: `modules/analytics/README.md`

- [ ] **Step 1: Replace `modules/analytics/README.md` with EXACTLY:**

```markdown
# Модуль аналитики GigaCode

Проектная конфигурация GigaCode для аналитиков: одноразовый обратный анализ
(reverse-analysis) одной бизнес-функции по существующему коду с явными
источниками доказательств. Результат двухслойный — замороженный технический
снимок плюс корпоративное дерево документации и спецификация OpenSpec.

Итоговые документы аналитика пишутся на русском. Технические идентификаторы
(пути, команды, имена символов и хуков) не переводятся.

## Состав модуля

- `.gigacode/settings.json` — настройки проекта, разрешения, hooks, mcpServers.
- `.gigacode/skills/reverse-analysis/SKILL.md` — 9-шаговый процесс reverse-analysis.
- `.gigacode/agents/` — три субагента: `code-mapping`, `documentation`, `verifier`
  (intake выполняется в основной сессии, отдельного агента нет).
- `.gigacode/hooks/` — единый роутер и гейты качества.
- `.gigacode/commands/reverse-analysis.md` — проектная slash-команда.
- `openspec/` — `config.yaml` и `specs/` (спека как текущая истина).
- `docs/templates/` — шаблон техдока (`feature-analysis.adoc`) и `manifest.json`.
- `rules/` — правила анализа, OpenSpec и именования веток.
- `scripts/build_module_map.py` — карта модулей из графа Graphify.

## Требования

- GigaCode CLI (команда `gigacode`).
- Git, Python 3.
- PowerShell (Windows) / Bash (Linux) для smoke-проверок.
- Опционально: Serena MCP — семантический поиск кода (нужен `uv`).
- Опционально: Graphify — карта модулей.
- Опционально: Context7 MCP — свежая документация библиотек (нужен Node.js 18+).
- Опционально: Atlassian MCP — Jira/Confluence (настраивает команда).

Репозиторий не устанавливает MCP-серверы и не хранит учётные данные. Любой
опциональный инструмент можно не ставить — для каждого есть фолбэк.

## Быстрый старт

Windows:

```powershell
cd <repo>\modules\analytics
.\scripts\smoke-check.ps1
gigacode
```

Linux:

```bash
cd <repo>/modules/analytics
bash scripts/smoke-check.sh
gigacode
```

Затем в GigaCode:

```text
/reverse-analysis feature "Card Blocking" jira ABC-123
```

Анализ только по коду (без Jira/Confluence):

```text
/reverse-analysis feature "Card Blocking" code-only, no Jira, no Confluence
```

## Результат: два слоя

**Технический слой** — `docs/features/<feature>/`: `overview.adoc`, `flow.adoc`,
`integrations.adoc`, `data.adoc`, `questions.adoc`, плюс `journal.md` и
`manifest.json`. Русский AsciiDoc с метками источников; обязательный заголовок с
атрибутами `:feature:`, `:run-date:`, `:code-commit:`. После прогона
замораживается.

**Спека** — `openspec/specs/<capability>/spec.md`: функциональные требования как
текущая истина (см. `rules/openspec.md`). Пишется один раз на новую capability.

**Финальный слой** — `analytics/` + `architecture/` в корне проекта: дерево по
типам (файлы `UpperCamelCase`, каталоги `kebab-case`), производное от
технического слоя и спеки.

## Процесс (9 шагов)

1. Запуск `/reverse-analysis "<feature>"`; preflight проверяет полноту запроса.
2. Intake в основной сессии: область в `journal.md`, `manifest.json` (статус `scoping`).
3. Code mapping (`code-mapping`) → карта в `journal.md`. Остановка: подтверждение области.
4. Технический черновик (`documentation`) → пять `.adoc` (статус `draft`).
5. Проверка доказуемости (`verifier`) по техслою → статус `confirmed`.
6. Извлечение спеки (`documentation`) → `openspec/specs/<capability>/spec.md`.
7. Финальная генерация (`documentation`) → `analytics/` + `architecture/`.
8. Проверка деривации (`verifier`): финал ↔ спека ↔ техслой.
9. Закрытие: `manifest.json` (статус `complete`), заморозка технического слоя.

## Serena MCP — семантический поиск кода

Без Serena агенты ищут через `rg`. С Serena — находят символы семантически и
расширяют их вместо дублирования.

Предварительно (один раз на машину):

```text
pip install uv          # или см. https://docs.astral.sh/uv/
uv tool install -p 3.13 serena-agent
serena init             # инициализирует LSP-бэкенд
```

Per-project:

```text
serena project create   # создаёт .serena/project.yml
```

Шаблон уже содержит `.serena/project.yml` — замените `project_name` и
`ignored_paths` под свой проект. Serena объявлена в `settings.json`
(`mcpServers.serena`); напоминания подключены асинхронными hooks. **Фолбэк:**
если `serena` недоступен, агенты переключаются на `rg`, а smoke-проверки
проходят без него.

## Карта модулей (Graphify)

`gate_context_inject` на старте сессии инжектит `.gigacode/context/module-map.md`
— компактную карту модулей. Карта генерируется из графа знаний Graphify:

1. `pip install graphifyy`
2. `/graphify .` (повторный прогон — `/graphify . --update`)
3. `python scripts/build_module_map.py` — читает `graphify-out/graph.json`, пишет
   `.gigacode/context/module-map.md` (лимит размера `--max-lines 120`).

Перегенерируйте карту после заметных изменений архитектуры. Коммитить
`module-map.md` или нет — решение команды. **Фолбэк:** нет файла — гейт молча
пропускает секцию; ручная карта в `journal.md` тоже работает.

## Context7 MCP — документация библиотек (опционально)

Context7 **не** включён в `settings.json` по умолчанию. Чтобы включить, добавьте
в `.gigacode/settings.json` в блок `mcpServers`:

```json
"context7": {
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp"]
}
```

Нужен Node.js 18+. API-ключ опционален (повышает rate limit): добавьте
`"--api-key", "<ключ>"` в `args` — ключи в репозиторий не коммитим. **Фолбэк:**
без Context7 анализ идёт на знаниях модели и официальной документации.

## Jira / Confluence (Atlassian MCP)

Atlassian MCP настраивает команда; шаблон его не устанавливает и не хранит
токены. Если он недоступен, анализ продолжается по коду и вводу пользователя, а
в результате явно фиксируется это ограничение. Код всегда приоритетнее Jira и
Confluence как источник текущей реализации.

## Ограничение размера субагентов

Каждый файл субагента — короче 10 000 символов. Переиспользуемые детали выносите
в `rules/` или шаблоны, а не раздувайте промпты субагентов.

## Проверка семантики хуков вашей сборки GigaCode

Имена событий и тулов в `router.config.json` соответствуют документации Qwen
Code. GigaCode — форк, поэтому перед продакшеном один раз проверьте реальные
имена: временно зарегистрируйте `python .gigacode/hooks/hook_probe.py` на нужные
события, выполните типовые действия (запрос, правка файла, git-команда) и сверьте
`hook_event_name`/`tool_name` в `.gigacode/logs/hook-probe.jsonl` с матчерами в
`router.config.json`.

## Адаптация для командного репозитория

Используйте модуль как корень проекта аналитика. Обновляйте `settings.json`
только безопасными для проекта значениями; не храните secrets, токены и
персональные пути. Если ваш форк GigaCode ожидает `.gigacode/` в другом месте,
сохраните внутреннюю структуру и измените только внешний путь модуля.
```

- [ ] **Step 2: Verify — no repomix, 3 agents, no stale 5-agent text**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
! grep -qi 'repomix' modules/analytics/README.md && echo "repomix-free"
for s in 'code-mapping' 'documentation' 'verifier' 'два слоя' 'build_module_map.py'; do grep -qF "$s" modules/analytics/README.md || { echo "missing: $s"; exit 1; }; done
! grep -qiE 'пять .*субагент|intake-scope|evidence-gap' modules/analytics/README.md && echo "no-stale"
```
Expected: prints `repomix-free` and `no-stale` (and no "missing:" lines).

- [ ] **Step 3: Commit**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git add modules/analytics/README.md
git commit -m "Rewrite README for 3 agents, two-layer output, MCP providers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Wire module-map tests + README sweep into smoke checks

**Files:**
- Modify: `modules/analytics/scripts/smoke-check.sh`
- Modify: `modules/analytics/scripts/smoke-check.ps1`

- [ ] **Step 1: `smoke-check.sh` — add required files**

In the `required=(` array, after `".gigacode/commands/reverse-analysis.md"` (or any existing entry), add:
```bash
  "scripts/build_module_map.py"
  "scripts/test_module_map.py"
  ".serena/project.yml"
```

- [ ] **Step 2: `smoke-check.sh` — add README repomix-free assertion**

After the existing repomix sweep block (`if grep -rIli 'repomix' .gigacode/agents rules ...; fi`), add:
```bash
if grep -qi 'repomix' README.md; then
  echo "repomix must not appear in README" >&2
  exit 1
fi
```

- [ ] **Step 3: `smoke-check.sh` — run the module-map suite**

After the existing `python scripts/test_gates.py` line, add:
```bash
python scripts/test_module_map.py
```

- [ ] **Step 4: `smoke-check.ps1` — add required files**

In the `$required = @(` array, after the command entry, add:
```powershell
  "scripts/build_module_map.py",
  "scripts/test_module_map.py",
  ".serena/project.yml",
```

- [ ] **Step 5: `smoke-check.ps1` — add README repomix-free assertion**

After the existing PowerShell repomix sweep block (the `$repomix = Get-ChildItem -Recurse -File ...` / `if ($repomix) { throw ... }`), add:
```powershell
if (Select-String -Path "README.md" -Pattern 'repomix' -SimpleMatch -Quiet) {
  throw "repomix must not appear in README"
}
```

- [ ] **Step 6: `smoke-check.ps1` — run the module-map suite**

After the existing `python scripts/test_gates.py` / `if ($LASTEXITCODE -ne 0) { throw "test_gates.py failed" }` block, add:
```powershell
python scripts/test_module_map.py
if ($LASTEXITCODE -ne 0) { throw "test_module_map.py failed" }
```

- [ ] **Step 7: Run both smoke checks**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul/modules/analytics && bash scripts/smoke-check.sh 2>&1 | tail -2; cd ../../..
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul/modules/analytics && powershell -NoProfile -File scripts/smoke-check.ps1 2>&1 | tail -2; cd ../../..
```
Expected: each shows `All 9 module-map checks passed` (or the count) somewhere above, then `Analytics module smoke check passed.`

- [ ] **Step 8: Commit**

```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git add modules/analytics/scripts/smoke-check.sh modules/analytics/scripts/smoke-check.ps1
git commit -m "Wire module-map tests and README repomix sweep into smoke checks

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Full verification sweep

**Files:** none committed (verification only).

- [ ] **Step 1: All offline suites**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul/modules/analytics
python scripts/test_router.py | tail -1
python scripts/test_gates.py | tail -1
python scripts/test_module_map.py | tail -1
```
Expected: `All 28 router checks passed`, `All 60 gate checks passed`, `All 9 module-map checks passed`.

- [ ] **Step 2: Both smoke checks end-to-end**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul/modules/analytics && bash scripts/smoke-check.sh 2>&1 | tail -1 && powershell -NoProfile -File scripts/smoke-check.ps1 2>&1 | tail -1; cd ../../..
```
Expected: `Analytics module smoke check passed.` twice.

- [ ] **Step 3: repomix fully gone (agents + rules + README)**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
grep -rIli repomix modules/analytics/.gigacode/agents modules/analytics/rules modules/analytics/README.md || echo "no repomix anywhere"
```
Expected: prints `no repomix anywhere`.

- [ ] **Step 4: Settings has serena, not context7**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
python -c "import json; d=json.load(open('modules/analytics/.gigacode/settings.json',encoding='utf-8')); print('serena' in d['mcpServers'], 'context7' not in d['mcpServers'])"
```
Expected: `True True`.

- [ ] **Step 5: Phase-3 commit log**

Run:
```bash
cd F:/Coding/gigacode_agents/.worktrees/analytics-overhaul
git log --oneline f14f5f2..HEAD
```
Expected: the five Task 1–5 commits on top of the Phase-2 history (`f14f5f2 ...`).

---

## Self-Review Notes

- **Spec coverage (design Decision 8 + Settings):**
  - Serena "declared in settings.json, async hooks" → Task 3 (mcpServers.serena + 4 async serena-hooks) + Task 2 (`.serena/project.yml`). Fallback documented (README Task 4); smoke does not require serena.
  - graphify "CLI + build_module_map.py + context-inject gate" → Task 1 (builder + tests; gate already reads the output from Phase 1). Fallback: gate skips missing map.
  - Context7 "README copy-paste snippet, NOT in default settings" → Task 4 README section only; Task 3 explicitly asserts context7 NOT in settings.json.
  - Atlassian "documented only, read-only" → Task 4 README section.
  - Repomix "removed everywhere" → was removed from agents/rules in Phase 2; Task 4 removes the last mentions (README); Task 5 + Task 6 assert it's gone everywhere.
  - README rewrite (3 agents, two-layer, 9-step) → Task 4.
- **No Phase-1/2 churn:** gates, router.config.json, quality-gates.json, agents, skill, command, rules, openspec, templates, final-tree skeleton untouched. Only `settings.json` gains `mcpServers` + serena hooks; the router hook entries are preserved byte-for-byte (Task 3 Step 2 asserts this).
- **Test integrity:** `test_module_map.py` is offline (reads a fixture JSON; never calls graphify). `test_gates`/`test_router` use `GIGACODE_ROOT` fixtures, unaffected by the new real files. Counts: gates 60, router 28 (unchanged), module-map 9 (new). Smoke checks gain the module-map suite + the `.serena`/builder required files + README repomix sweep.
- **Placeholder scan:** all file contents given in full; the only `<...>` tokens are intentional template placeholders (README quickstart, settings snippet, `.serena` project_name).
- **Type/name consistency:** `module-map.md` path, `graphify-out/graph.json`, `serena-hooks ... --client=claude-code`, `mcpServers.serena`, and the 3 agent names match across builder, settings, README, and the Phase-1 gate that consumes the map.
- **Out of scope (correctly deferred):** live GigaCode runtime probe of real tool/event names (shared pending item, design "Out of Scope"); Serena Kotlin-LSP verification on real code (design Risk); finishing-a-development-branch (merge/PR) — a post-phase decision.
