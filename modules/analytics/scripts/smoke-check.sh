#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

required=(
  ".gigacode/settings.json"
  ".gigacode/quality-gates.json"
  ".gigacode/skills/reverse-analysis/SKILL.md"
  ".gigacode/commands/reverse-analysis.md"
  ".gigacode/hooks/router.py"
  ".gigacode/hooks/router.config.json"
  ".gigacode/hooks/hook_probe.py"
  ".gigacode/hooks/gates/_lib.py"
  ".gigacode/hooks/gates/git_guard.py"
  ".gigacode/hooks/gates/gate_context_inject.py"
  ".gigacode/hooks/gates/preflight_check.py"
  ".gigacode/hooks/gates/gate_spec_bootstrap.py"
  ".gigacode/hooks/gates/gate_techdocs.py"
  ".gigacode/hooks/gates/gate_final_format.py"
  ".gigacode/hooks/gates/validate_run_output.py"
  "docs/templates/feature-analysis.adoc"
  "rules/reverse-analysis.md"
  "rules/branch-naming.md"
  "README.md"
)

for path in "${required[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
done

python -m json.tool .gigacode/settings.json >/dev/null
python -m json.tool .gigacode/hooks/router.config.json >/dev/null
python -m json.tool .gigacode/quality-gates.json >/dev/null

agent_count="$(find .gigacode/agents -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')"
if [[ "$agent_count" != "5" ]]; then
  echo "Expected 5 agent files, found $agent_count" >&2
  exit 1
fi

for agent in .gigacode/agents/*.md; do
  chars="$(wc -m < "$agent" | tr -d ' ')"
  if [[ "$chars" -ge 10000 ]]; then
    echo "Agent file exceeds 10,000 characters: $agent" >&2
    exit 1
  fi
  boundaries="$(grep -c '^---$' "$agent")"
  if [[ "$boundaries" -lt 2 ]]; then
    echo "Agent file missing YAML frontmatter boundaries: $agent" >&2
    exit 1
  fi
done

decision="$(
  printf '%s' '{"hook_event_name":"SessionStart"}' |
    python .gigacode/hooks/router.py --event=SessionStart |
    python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
)"
if [[ "$decision" != "allow" ]]; then
  echo "Expected SessionStart routing to allow, got $decision" >&2
  exit 1
fi

decision="$(
  printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"reverse-analysis missing info"}' |
    python .gigacode/hooks/router.py --event=UserPromptSubmit |
    python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
)"
if [[ "$decision" != "block" ]]; then
  echo "Expected incomplete reverse-analysis prompt to block, got $decision" >&2
  exit 1
fi

if ! grep -q '^=' docs/templates/feature-analysis.adoc; then
  echo "AsciiDoc template must contain a document title" >&2
  exit 1
fi

python scripts/test_router.py
python scripts/test_gates.py

echo "Analytics module smoke check passed."
