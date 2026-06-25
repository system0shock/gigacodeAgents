#!/usr/bin/env bash
set -euo pipefail

required=(
  ".gigacode/settings.json"
  ".gigacode/skills/development-flow/SKILL.md"
  ".gigacode/commands/develop-feature.md"
  ".gigacode/commands/fix-bug.md"
  ".gigacode/hooks/gates/git_guard.py"
  ".gigacode/hooks/gates/preflight_check.py"
  ".gigacode/hooks/gates/validate_development_output.py"
  ".gigacode/hooks/router.py"
  ".gigacode/hooks/router.config.json"
  ".gigacode/hooks/hook_probe.py"
  "docs/templates/development-journal.md"
  "rules/development-flow.md"
  "rules/language-policy.md"
  "rules/git-safety.md"
  "rules/branch-naming.md"
  "openspec/config.yaml"
  "rules/openspec.md"
  ".gigacode/skills/openspec-propose/SKILL.md"
  ".serena/project.yml"
  ".gigacode/hooks/gates/_lib.py"
  ".gigacode/hooks/gates/gate_context_inject.py"
  ".gigacode/hooks/gates/gate_spec_structure.py"
  ".gigacode/hooks/gates/gate_lint.py"
  ".gigacode/hooks/gates/gate_build.py"
  ".gigacode/hooks/gates/gate_clean_code.py"
  ".gigacode/hooks/gates/gate_existing_code.py"
  ".gigacode/hooks/gates/gate_stage_order.py"
  ".gigacode/hooks/confirm.py"
  ".gigacode/stages.json"
  ".gigacode/quality-gates.json"
  "scripts/build_module_map.py"
  "scripts/test_module_map.py"
  "scripts/test_stage_order.py"
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

command -v node >/dev/null 2>&1 || { echo "Node.js is required (GigaCode runtime + hook launcher)" >&2; exit 1; }

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

block="$(printf '%s' '{"command":"git reset --hard HEAD"}' | "$python_cmd" .gigacode/hooks/gates/git_guard.py)"
printf '%s' "$block" | grep -q '"decision": "block"'

clean="$(printf '%s' '{"command":"git clean -f -d"}' | "$python_cmd" .gigacode/hooks/gates/git_guard.py)"
printf '%s' "$clean" | grep -q '"decision": "block"'

flag_bypass="$(printf '%s' '{"command":"git -C . reset --hard HEAD"}' | "$python_cmd" .gigacode/hooks/gates/git_guard.py)"
printf '%s' "$flag_bypass" | grep -q '"decision": "block"'

config_bypass="$(printf '%s' '{"command":"git -c core.pager=cat clean -f -d"}' | "$python_cmd" .gigacode/hooks/gates/git_guard.py)"
printf '%s' "$config_bypass" | grep -q '"decision": "block"'

ask="$(printf '%s' '{"path":".github/workflows/deploy.yml"}' | "$python_cmd" .gigacode/hooks/gates/git_guard.py)"
printf '%s' "$ask" | grep -q '"decision": "ask"'

feature="$(printf '%s' '{"prompt":"/develop-feature plan-only payment retry"}' | "$python_cmd" .gigacode/hooks/gates/preflight_check.py)"
printf '%s' "$feature" | grep -q '"decision": "allow"'

# validate_development_output triggers from the working tree, not the message,
# and validates only dev dirs in the CURRENT change. Use an isolated GIGACODE_ROOT
# git fixture with a CHANGED but incomplete dev dir so the check is deterministic.
vdo_root="$(mktemp -d)"
mkdir -p "$vdo_root/docs/development/sample"
printf 'partial\n' > "$vdo_root/docs/development/sample/journal.md"
git -C "$vdo_root" init -q
git -C "$vdo_root" add -A
missing="$(printf '%s' '{"hook_event_name":"Stop","last_assistant_message":"done"}' | GIGACODE_ROOT="$vdo_root" "$python_cmd" .gigacode/hooks/gates/validate_development_output.py)"
rm -rf "$vdo_root"
printf '%s' "$missing" | grep -q '"decision": "block"'

"$python_cmd" -m json.tool .gigacode/hooks/router.config.json >/dev/null
"$python_cmd" -m json.tool .gigacode/stages.json >/dev/null
"$python_cmd" scripts/test_router.py
"$python_cmd" -m json.tool .gigacode/quality-gates.json >/dev/null
"$python_cmd" scripts/test_gates.py
"$python_cmd" scripts/test_stage_order.py
"$python_cmd" scripts/test_module_map.py

# gate_stage_order: a contract-stage write without the intake approval is a hard
# stop (direct gate call, mirrors the git_guard block cases above).
stage_block="$(printf '%s' '{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"docs/development/smoke-nope/contract.json"}}' | "$python_cmd" .gigacode/hooks/gates/gate_stage_order.py)"
printf '%s' "$stage_block" | grep -q '"decision": "block"'

# and the same write denied through the live router route (proves it is wired).
stage_route="$(printf '%s' '{"tool_name":"Edit","tool_input":{"file_path":"docs/development/smoke-nope/contract.json"}}' | node .gigacode/hooks/run-hook.cjs --event PreToolUse)"
printf '%s' "$stage_route" | grep -q '"permissionDecision": "deny"'
echo "gate_stage_order round-trip: block + route deny OK"

if command -v openspec >/dev/null 2>&1; then
  # Use 'list --specs' not 'validate --strict': validate requires --type change
  # when the name is ambiguous, and strict validation needs populated specs.
  openspec list --specs >/dev/null
  echo "openspec config valid"
else
  echo "SKIP: openspec CLI not installed; spec validation not run" >&2
fi

if command -v serena >/dev/null 2>&1; then
  echo "serena CLI available"
else
  echo "NOTE: serena CLI not installed; Serena MCP will not start. Install with: uv tool install -p 3.13 serena-agent" >&2
fi

launcher="$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git reset --hard HEAD"}}' | node .gigacode/hooks/run-hook.cjs --event PreToolUse)"
printf '%s' "$launcher" | grep -q '"permissionDecision": "deny"'
echo "launcher round-trip: deny OK"

echo "Smoke check passed"
