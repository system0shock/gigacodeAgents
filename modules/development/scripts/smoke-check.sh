#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

required=(
  ".gigacode/settings.json"
  ".gigacode/skills/feature-development/SKILL.md"
  ".gigacode/skills/junit-testing/SKILL.md"
  ".gigacode/commands/develop.md"
  ".gigacode/commands/write-tests.md"
  ".gigacode/hooks/router.py"
  ".gigacode/hooks/router_config.json"
  "docs/templates/plan-template.md"
  "docs/serena-mcp.sample.json"
  "rules/development.md"
  "rules/plan-format.md"
  "rules/testing.md"
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
python -m json.tool .gigacode/hooks/router_config.json >/dev/null
python -m json.tool docs/serena-mcp.sample.json >/dev/null
python -m compileall -q .gigacode/hooks >/dev/null

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

for doc in .gigacode/skills/*/SKILL.md .gigacode/commands/*.md; do
  boundaries="$(grep -c '^---$' "$doc")"
  if [[ "$boundaries" -lt 2 ]]; then
    echo "File missing YAML frontmatter boundaries: $doc" >&2
    exit 1
  fi
done

for ref in junit-rules kotlin-style java-style mocking assertions build-tools; do
  if [[ ! -e "reference/$ref.md" ]]; then
    echo "Missing reference file: reference/$ref.md" >&2
    exit 1
  fi
  if ! grep -q '^## Digest' "reference/$ref.md"; then
    echo "Reference file missing '## Digest' section: reference/$ref.md" >&2
    exit 1
  fi
done

run_router() {
  printf '%s' "$1" | python .gigacode/hooks/router.py "$2"
}

decision_of() {
  python -c 'import json,sys; print(json.load(sys.stdin)["decision"])'
}

decision="$(run_router '{"prompt":"hello"}' UserPromptSubmit | decision_of)"
if [[ "$decision" != "allow" ]]; then
  echo "Expected unrelated prompt to allow, got $decision" >&2
  exit 1
fi

output="$(run_router '{"prompt":"implement card blocking limit DEV-123"}' UserPromptSubmit)"
decision="$(printf '%s' "$output" | decision_of)"
if [[ "$decision" != "allow" ]]; then
  echo "Expected complete dev prompt to allow, got $decision" >&2
  exit 1
fi
if ! printf '%s' "$output" | grep -q 'additionalContext'; then
  echo "Expected dev prompt to inject additional context" >&2
  exit 1
fi

decision="$(run_router '{"prompt":"implement stuff"}' UserPromptSubmit | decision_of)"
if [[ "$decision" != "ask" ]]; then
  echo "Expected incomplete dev prompt to ask, got $decision" >&2
  exit 1
fi

decision="$(run_router '{"tool_name":"Write","tool_input":{"file_path":"src/main/kotlin/com/example/Foo.kt","content":"x"}}' PreToolUse | decision_of)"
if [[ "$decision" != "ask" ]]; then
  echo "Expected source edit without plan to ask, got $decision" >&2
  exit 1
fi

decision="$(run_router '{"tool_name":"Bash","tool_input":{"command":"rm -rf build"}}' PreToolUse | decision_of)"
if [[ "$decision" != "block" ]]; then
  echo "Expected dangerous command to block, got $decision" >&2
  exit 1
fi

output="$(run_router '{"tool_name":"Write","tool_input":{"file_path":"src/test/kotlin/com/example/FooTest.kt","content":"x"}}' PreToolUse)"
if ! printf '%s' "$output" | grep -q 'junit-rules'; then
  echo "Expected test-file edit to inject junit reference digest" >&2
  exit 1
fi

cp scripts/fixtures/sample-plan-good.md docs/plans/tmp-smoke-plan.md
decision="$(run_router '{"tool_name":"Write","tool_input":{"file_path":"src/main/kotlin/com/example/Foo.kt","content":"x"}}' PreToolUse | decision_of)"
rm docs/plans/tmp-smoke-plan.md
if [[ "$decision" != "allow" ]]; then
  echo "Expected source edit with approved plan to allow, got $decision" >&2
  exit 1
fi

decision="$(run_router '{"tool_name":"Write","tool_input":{"file_path":"scripts/fixtures/BadService.java"}}' PostToolUse | decision_of)"
if [[ "$decision" != "block" ]]; then
  echo "Expected bad production fixture to block, got $decision" >&2
  exit 1
fi

decision="$(run_router '{"tool_name":"Write","tool_input":{"file_path":"scripts/fixtures/BadServiceTest.java"}}' PostToolUse | decision_of)"
if [[ "$decision" != "block" ]]; then
  echo "Expected JUnit 4 test fixture to block, got $decision" >&2
  exit 1
fi

decision="$(run_router '{"tool_name":"Write","tool_input":{"file_path":"scripts/fixtures/GoodService.kt"}}' PostToolUse | decision_of)"
if [[ "$decision" != "allow" ]]; then
  echo "Expected clean fixture to allow, got $decision" >&2
  exit 1
fi

decision="$(run_router '{"last_assistant_message":"thinking..."}' Stop | decision_of)"
if [[ "$decision" != "allow" ]]; then
  echo "Expected non-completion message to allow on Stop, got $decision" >&2
  exit 1
fi

python - <<'EOF'
import sys
sys.path.insert(0, ".gigacode/hooks")
from pathlib import Path
from hooklib import plandoc

good = Path("scripts/fixtures/sample-plan-good.md")
bad = Path("scripts/fixtures/sample-plan-bad.md")
assert plandoc.validate(good) == [], plandoc.validate(good)
assert plandoc.is_approved(good)
assert plandoc.validate(bad), "bad plan must produce issues"
assert not plandoc.is_approved(bad)
EOF

echo "Development module smoke check passed."
