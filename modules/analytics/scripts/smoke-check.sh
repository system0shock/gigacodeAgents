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
if [[ "$agent_count" != "4" ]]; then
  echo "Expected 4 agent files, found $agent_count" >&2
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

for doc in .gigacode/skills/reverse-analysis/SKILL.md .gigacode/commands/reverse-analysis.md; do
  boundaries="$(grep -c '^---$' "$doc")"
  if [[ "$boundaries" -lt 2 ]]; then
    echo "File missing YAML frontmatter boundaries: $doc" >&2
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

cleanup_smoke() {
  rm -rf docs/features/tmp-smoke docs/scopes/tmp-smoke.md
}
trap cleanup_smoke EXIT

mkdir -p docs/features/tmp-smoke
printf '= Обзор\n\nИсточник: код\n\nОписание функции.\n' > docs/features/tmp-smoke/overview.adoc
printf '= Поток\n\nИсточник: код\n\nОсновной сценарий.\n' > docs/features/tmp-smoke/flow.adoc
printf '= Интеграции\n\nИсточник: код\n\nВнешние системы.\n' > docs/features/tmp-smoke/integrations.adoc
printf '= Данные\n\nИсточник: код\n\nСущности и таблицы.\n' > docs/features/tmp-smoke/data.adoc
printf '= Вопросы\n\nСтатус: открытый вопрос\n\nУточнить лимиты.\n' > docs/features/tmp-smoke/questions.adoc
printf '# Область анализа: tmp-smoke\n\nСтатус: подтвержден\n\nКаталог результата: docs/features/tmp-smoke/\n' > docs/scopes/tmp-smoke.md

decision="$(
  printf '%s' '{"last_assistant_message":"Reverse analysis complete in docs/features/tmp-smoke/"}' |
    python .gigacode/hooks/validate_output.py |
    python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
)"
if [[ "$decision" != "allow" ]]; then
  echo "Expected valid scoped output to allow, got $decision" >&2
  exit 1
fi

printf '= Обзор\n\nОписание функции без меток.\n' > docs/features/tmp-smoke/overview.adoc
decision="$(
  printf '%s' '{"last_assistant_message":"Reverse analysis complete in docs/features/tmp-smoke/"}' |
    python .gigacode/hooks/validate_output.py |
    python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
)"
if [[ "$decision" != "block" ]]; then
  echo "Expected missing evidence labels to block, got $decision" >&2
  exit 1
fi

cleanup_smoke
trap - EXIT

echo "Analytics module smoke check passed."
