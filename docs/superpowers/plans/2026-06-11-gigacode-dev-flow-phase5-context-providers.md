# GigaCode Dev-Flow Phase 5: Context Providers (Graphify + Context7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Graphify's repository knowledge graph into `gate_context_inject` via a generated module map, and declare Context7 as an optional MCP server — both with documented fallbacks, neither required for smoke checks.

**Architecture:** Graphify (a skill + pip package, NOT an MCP here) writes `graphify-out/graph.json` (networkx node-link JSON with per-node `community` ids and optional `hyperedges`). A new stdlib-only converter `scripts/build_module_map.py` renders that JSON into a compact, token-bounded `.gigacode/context/module-map.md` — the exact file `gate_context_inject` already injects on SessionStart/SubagentStart (hook point shipped in Phase 4; the gate silently skips the file when absent, so nothing breaks without Graphify). Context7 is a one-entry `mcpServers` declaration (`npx -y @upstash/context7-mcp`, stdio) mirroring the existing serena entry; API key optional.

**Tech Stack:** Python 3 stdlib (json, argparse, collections), networkx node-link JSON schema (read-only), npx/Node 18+ (Context7, optional), existing offline test harness style (`check()` + explicit `SystemExit`).

---

## Verified facts (research 2026-06-11)

- `gate_context_inject.py` reads `MODULE_MAP = os.path.join(".gigacode", "context", "module-map.md")` relative to `_lib.root()` and injects its full text on SessionStart and SubagentStart; missing file → `read_text` returns `""` and the section is silently dropped. The gate test fixture writes a map starting with `# Module Map`.
- Graphify `to_json` schema (inspected from installed `graphify.export.to_json`): `{"nodes": [{id, label, community, norm_label, source_file?, file_type?, ...}], "links": [{source, target, relation, confidence, confidence_score, ...}], "hyperedges": [{id, label, nodes: [ids], relation, ...}]}`. Community human labels are NOT stored in graph.json (only integer ids) — the converter derives module identity from top-degree member nodes instead.
- Graphify is installed in the dev env (`pip install graphifyy`); output dir convention is `graphify-out/` in the analyzed repo root.
- Context7 MCP: package `@upstash/context7-mcp`, local stdio run via `npx -y @upstash/context7-mcp`; API key from context7.com is optional (higher rate limits), passed as `--api-key KEY` arg when present. Requires Node 18+; `node`/`npx` ARE present in the dev env but must NOT be required by smoke checks.
- `docs/flow-overview.md` §6 already documents all three MCP/context providers with fallbacks (Graphify fallback: «ручная карта в journal.md»). Docs only need the regeneration command, not a new concept.
- Existing smoke scripts: `scripts/smoke-check.ps1` (PS 5.1, `$required` array, `$LASTEXITCODE -ne 0 → throw` after each python suite, `python -m json.tool X | Out-Null` + explicit throw) and `scripts/smoke-check.sh` (`set -euo pipefail`, `required=()` array, bare commands). New invocations must copy these styles exactly.
- Test style: `scripts/test_gates.py` / `test_router.py` use a module-level `PASSED` counter and `check(name, condition, detail)` raising `SystemExit` (explicit raise so `python -O` cannot neuter the suite). The new `test_module_map.py` follows the same style.
- Suites currently green at: `All 55 gate checks passed`, `All 50 router checks passed`. Counts may drift upward; task prompts must expect "all passed", not exact numbers.

## Design decisions

- **Converter is stdlib-only and offline.** It never invokes graphify; it only reads the JSON graphify already wrote. Missing/empty/corrupt graph → exit 1 with a one-line message (humans and smoke runs notice), while the runtime gate path stays unaffected (gate reads the .md, not the .json).
- **Token budget:** output capped by `--max-lines` (default 120) with an explicit truncation marker. The map is injected into every session start — compactness beats completeness.
- **Module rendering:** communities sorted by size desc; each lists its top-8 members by degree (degree computed from `links`). Cross-community links (max 10) form a «Cross-module links» section — these are the architecture seams. `hyperedges` (max 10) render as «Flows / groups» — for Kafka-style producer→topic→consumer groupings when semantic extraction captured them.
- **Output header starts with `# Module Map`** — matches what the Phase 4 gate test already asserts (`"Module Map" in ctx`).
- **Context7 ships WITHOUT an API key** in the template; the README documents how a team adds `--api-key`. No secrets in the template (design "Settings" rule: no shipped MCP credentials).
- **`module-map.md` is NOT gitignored and NOT shipped**: end-user teams decide whether to commit their generated map. The template ships only the builder + docs.
- **English output in module-map.md** (agent-facing context, same language as `rules/*.md`); README/SKILL doc prose in Russian per language policy.

## File structure

- Create: `scripts/build_module_map.py` — graph.json → module-map.md converter (single responsibility: render, never analyze).
- Create: `scripts/test_module_map.py` — offline tests for the converter.
- Modify: `.gigacode/settings.json` — `mcpServers.context7` entry.
- Modify: `scripts/smoke-check.ps1`, `scripts/smoke-check.sh` — required files + `test_module_map.py` invocation.
- Modify: `README.md`, `docs/flow-overview.md`, `.gigacode/skills/development-flow/SKILL.md` — regeneration command + Context7 setup/fallback.

---

### Task 1: `scripts/build_module_map.py` — graph.json → module-map.md

**Files:**
- Create: `scripts/build_module_map.py`
- Test: `scripts/test_module_map.py`

- [ ] **Step 1: Write the failing tests**

Create `scripts/test_module_map.py` with exactly this content:

```python
#!/usr/bin/env python3
"""Offline tests for scripts/build_module_map.py. Run from the repo root:
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

Run: `python scripts/test_module_map.py`
Expected: FAIL — `map_builds` fails because `scripts/build_module_map.py` does not exist (subprocess rc != 0).

- [ ] **Step 3: Create `scripts/build_module_map.py`**

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
    links = [l for l in data.get("links", []) if isinstance(l, dict)]
    degree = defaultdict(int)
    for link in links:
        degree[link.get("source")] += 1
        degree[link.get("target")] += 1
    communities = defaultdict(list)
    for node in nodes.values():
        communities[node.get("community")].append(node)

    lines = ["# Module Map", "",
             f"Generated from {graph_path}: {len(nodes)} nodes, "
             f"{len(links)} edges, {len(communities)} communities.", ""]
    for cid, members in sorted(communities.items(),
                               key=lambda kv: (-len(kv[1]), str(kv[0]))):
        members.sort(key=lambda n: -degree[n["id"]])
        lines.append(f"## Module {cid} ({len(members)} nodes)")
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
        description="Render graphify graph.json into .gigacode/context/module-map.md")
    parser.add_argument("--graph", default=os.path.join("graphify-out", "graph.json"))
    parser.add_argument("--out",
                        default=os.path.join(".gigacode", "context", "module-map.md"))
    parser.add_argument("--max-lines", type=int, default=120)
    args = parser.parse_args()

    data = load_graph(args.graph)
    lines = build_lines(data, args.graph.replace("\\", "/"))
    if len(lines) > args.max_lines:
        lines = lines[:max(args.max_lines, 1)] + ["", "(truncated: --max-lines reached)"]
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print(f"module-map: wrote {args.out} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/test_module_map.py`
Expected: `All 9 module-map checks passed`

- [ ] **Step 5: Regression — run the existing suites**

Run: `python scripts/test_gates.py` then `python scripts/test_router.py`
Expected: both end with `All N ... checks passed` (no failures; counts unchanged by this task).

- [ ] **Step 6: Commit**

```bash
git add scripts/build_module_map.py scripts/test_module_map.py
git commit -m "Add module-map builder rendering graphify graph for context injection"
```

---

### Task 2: Context7 declaration + smoke-check wiring

**Files:**
- Modify: `.gigacode/settings.json` (mcpServers block)
- Modify: `scripts/smoke-check.ps1` (required files + test invocation)
- Modify: `scripts/smoke-check.sh` (required files + test invocation)

- [ ] **Step 1: Add Context7 to `mcpServers` in `.gigacode/settings.json`**

The block currently ends with:

```json
  "mcpServers": {
    "serena": {
      "command": "serena",
      "args": ["start-mcp-server", "--context", "ide", "--project-from-cwd"]
    }
  }
```

Change it to:

```json
  "mcpServers": {
    "serena": {
      "command": "serena",
      "args": ["start-mcp-server", "--context", "ide", "--project-from-cwd"]
    },
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }
  }
```

No API key in the template (teams add `--api-key <key>` themselves; documented in Task 3).

- [ ] **Step 2: Wire into `scripts/smoke-check.ps1`**

1. Append two entries to the `$required` array (after `".gigacode/quality-gates.json"`, adding a trailing comma to it):

```powershell
  ".gigacode/quality-gates.json",
  "scripts/build_module_map.py",
  "scripts/test_module_map.py"
```

2. After the `python scripts/test_gates.py` block (which ends with its `throw "gate tests failed"` check), add:

```powershell
python scripts/test_module_map.py
if ($LASTEXITCODE -ne 0) {
  throw "module-map tests failed"
}
```

- [ ] **Step 3: Wire into `scripts/smoke-check.sh`**

1. Append to the `required=(...)` array (after `.gigacode/quality-gates.json`):

```bash
  scripts/build_module_map.py
  scripts/test_module_map.py
```

2. After the `"$python_cmd" scripts/test_gates.py` line, add:

```bash
"$python_cmd" scripts/test_module_map.py
```

(`set -euo pipefail` handles failure propagation — match the file's existing style, no explicit check.)

- [ ] **Step 4: Validate settings.json and run both smoke suites**

Run: `python -m json.tool .gigacode/settings.json`
Expected: pretty-printed JSON, exit 0.

Run: `powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1`
Expected: ends with `Smoke check passed` (module-map checks line included).

Run: `bash scripts/smoke-check.sh` (or `& "C:\Program Files\Git\bin\bash.exe" scripts/smoke-check.sh`)
Expected: ends with `Smoke check passed`.

- [ ] **Step 5: Commit**

```bash
git add .gigacode/settings.json scripts/smoke-check.ps1 scripts/smoke-check.sh
git commit -m "Declare Context7 MCP server and wire module-map tests into smoke checks"
```

---

### Task 3: Documentation

**Files:**
- Modify: `README.md` (new RU section after the quality-gates section)
- Modify: `docs/flow-overview.md` (§6 MCP table: Graphify row regeneration command)
- Modify: `.gigacode/skills/development-flow/SKILL.md` (module-map note)

Read each target file first and match its existing heading levels and style. Russian prose, English identifiers/paths/commands.

- [ ] **Step 1: README — add section «Карта модулей (Graphify) и Context7»**

Append after the quality-gates section (match the README's existing heading level for sections; content below is normative, exact wording may be adjusted to the file's voice):

```markdown
## Карта модулей (Graphify) и Context7

### Graphify → module-map

`gate_context_inject` на старте сессии инжектит `.gigacode/context/module-map.md` —
компактную карту модулей репозитория. Карта генерируется из графа знаний Graphify:

1. Установи graphify: `pip install graphifyy`.
2. Построй граф репозитория: `/graphify .` (скилл; повторный прогон — `/graphify . --update`).
3. Сгенерируй карту: `python scripts/build_module_map.py`
   (читает `graphify-out/graph.json`, пишет `.gigacode/context/module-map.md`,
   лимит размера `--max-lines 120`).

Перегенерируй карту после заметных изменений архитектуры (новые модули,
новые Kafka-потоки). Коммитить `module-map.md` или нет — решение команды.

**Фолбэк:** если Graphify не используется, файла просто нет — гейт молча
пропускает секцию. Ручная карта в том же файле тоже работает.

### Context7

Context7 объявлен в `settings.json` (`mcpServers.context7`) и поднимается через
`npx -y @upstash/context7-mcp` — нужен Node.js 18+. Даёт свежую документацию
библиотек (Spring Kafka, kotlinx.coroutines, JUnit 5) при написании нового кода.

API-ключ опционален (повышает rate limit): добавь `--api-key <ключ>` в `args`.
Ключи в шаблон не коммитим.

**Фолбэк:** без Node/ключа сервер просто не стартует — flow продолжает работать
на знаниях модели; проверяй API по официальным докам и фиксируй это в
`verification.md`.
```

- [ ] **Step 2: flow-overview §6 — regeneration command in the Graphify row**

In the MCP table, extend the Graphify row's description (keep the row's column structure intact) so it mentions the converter, e.g. change the description cell to end with: «карта генерируется `scripts/build_module_map.py` из `graphify-out/graph.json` в `.gigacode/context/module-map.md`». The fallback cell stays «ручная карта в journal.md».

- [ ] **Step 3: SKILL.md — module-map note**

In `.gigacode/skills/development-flow/SKILL.md`, append to the section that describes context/search (the "Search Before Create" section) a short paragraph:

```markdown
Карта модулей: на старте сессии хук инжектит `.gigacode/context/module-map.md`
(если файл есть). После заметных изменений архитектуры перегенерируй её:
`python scripts/build_module_map.py` (требует готовый `graphify-out/graph.json`,
см. README «Карта модулей»).
```

- [ ] **Step 4: Verify nothing broke**

Run: `python scripts/test_gates.py`, `python scripts/test_router.py`, `python scripts/test_module_map.py`
Expected: all three end with `All N ... passed`.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/flow-overview.md .gigacode/skills/development-flow/SKILL.md
git commit -m "Document Graphify module map and Context7 setup with fallbacks"
```

---

### Task 4: Final review

Controller-level task (not a subagent implementation task): dispatch a final reviewer over the whole Phase 5 diff (from the commit before Task 1 to HEAD) checking cross-cutting consistency (converter vs gate hook point, settings vs docs, smoke wiring on both platforms), then run the full offline verification:

- `python scripts/test_module_map.py`
- `python scripts/test_gates.py`
- `python scripts/test_router.py`
- `powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1`
- `bash scripts/smoke-check.sh`

Apply APPROVED-with-recommendations fixes inline; commit.
