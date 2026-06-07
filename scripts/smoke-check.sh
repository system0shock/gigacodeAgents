#!/usr/bin/env bash
set -euo pipefail

required=(
  ".gigacode/settings.json"
  ".gigacode/skills/development-flow/SKILL.md"
  ".gigacode/commands/develop-feature.md"
  ".gigacode/commands/fix-bug.md"
  ".gigacode/hooks/git_guard.py"
  ".gigacode/hooks/preflight_check.py"
  ".gigacode/hooks/validate_development_output.py"
  "docs/templates/development-plan.md"
  "rules/development-flow.md"
  "rules/language-policy.md"
  "rules/git-safety.md"
  "rules/branch-naming.md"
  "openspec/config.yaml"
  "rules/openspec.md"
  ".gigacode/skills/openspec-propose/SKILL.md"
)

for path in "${required[@]}"; do
  test -f "$path" || { echo "Missing required file: $path" >&2; exit 1; }
done

python_cmd=""
if command -v python >/dev/null 2>&1; then
  python_cmd="python"
elif command -v python3 >/dev/null 2>&1; then
  python_cmd="python3"
else
  echo "Python 3 is required" >&2
  exit 1
fi

"$python_cmd" -m json.tool .gigacode/settings.json >/dev/null

for path in .gigacode/agents/*.md; do
  chars="$(wc -m < "$path")"
  if [ "$chars" -ge 10000 ]; then
    echo "$path exceeds 10000 characters" >&2
    exit 1
  fi
  boundaries="$(grep -c '^---$' "$path")"
  if [ "$boundaries" -lt 2 ]; then
    echo "$path missing frontmatter" >&2
    exit 1
  fi
done

block="$(printf '%s' '{"command":"git reset --hard HEAD"}' | "$python_cmd" .gigacode/hooks/git_guard.py)"
printf '%s' "$block" | grep -q '"decision": "block"'

clean="$(printf '%s' '{"command":"git clean -f -d"}' | "$python_cmd" .gigacode/hooks/git_guard.py)"
printf '%s' "$clean" | grep -q '"decision": "block"'

ask="$(printf '%s' '{"path":".github/workflows/deploy.yml"}' | "$python_cmd" .gigacode/hooks/git_guard.py)"
printf '%s' "$ask" | grep -q '"decision": "ask"'

feature="$(printf '%s' '{"prompt":"/develop-feature plan-only payment retry"}' | "$python_cmd" .gigacode/hooks/preflight_check.py)"
printf '%s' "$feature" | grep -q '"decision": "allow"'

missing="$(printf '%s' '{"last_assistant_message":"Complete in docs/development/sample-task/"}' | "$python_cmd" .gigacode/hooks/validate_development_output.py)"
printf '%s' "$missing" | grep -q '"decision": "block"'

if command -v openspec >/dev/null 2>&1; then
  openspec list --specs >/dev/null
  echo "openspec config valid"
else
  echo "SKIP: openspec CLI not installed; spec validation not run" >&2
fi

echo "Smoke check passed"
