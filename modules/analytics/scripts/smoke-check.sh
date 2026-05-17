#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

required=(
  ".gigacode/settings.json"
  ".gigacode/skills/reverse-analysis/SKILL.md"
  ".gigacode/commands/reverse-analysis.md"
  ".gigacode/hooks/preflight_check.py"
  ".gigacode/hooks/validate_output.py"
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
  printf '%s' '{"prompt":"reverse-analysis feature Card Blocking jira ABC-123"}' |
    python .gigacode/hooks/preflight_check.py |
    python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
)"
if [[ "$decision" != "allow" ]]; then
  echo "Expected complete preflight sample to allow, got $decision" >&2
  exit 1
fi

decision="$(
  printf '%s' '{"prompt":"hello"}' |
    python .gigacode/hooks/preflight_check.py |
    python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
)"
if [[ "$decision" != "allow" ]]; then
  echo "Expected unrelated prompt to allow, got $decision" >&2
  exit 1
fi

decision="$(
  printf '%s' '{"last_assistant_message":"Reverse analysis complete in docs/features/card-blocking/"}' |
    python .gigacode/hooks/validate_output.py |
    python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
)"
if [[ "$decision" != "block" ]]; then
  echo "Expected missing output validation sample to block, got $decision" >&2
  exit 1
fi

if ! grep -q '^=' docs/templates/feature-analysis.adoc; then
  echo "AsciiDoc template must contain a document title" >&2
  exit 1
fi

echo "Analytics module smoke check passed."
