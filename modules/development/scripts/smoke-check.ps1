$ErrorActionPreference = "Stop"

$required = @(
  ".gigacode/settings.json",
  ".gigacode/skills/development-flow/SKILL.md",
  ".gigacode/commands/develop-feature.md",
  ".gigacode/commands/fix-bug.md",
  ".gigacode/hooks/gates/git_guard.py",
  ".gigacode/hooks/gates/preflight_check.py",
  ".gigacode/hooks/gates/validate_development_output.py",
  ".gigacode/hooks/router.py",
  ".gigacode/hooks/router.config.json",
  ".gigacode/hooks/hook_probe.py",
  "docs/templates/development-journal.md",
  "rules/development-flow.md",
  "rules/language-policy.md",
  "rules/git-safety.md",
  "rules/branch-naming.md",
  "openspec/config.yaml",
  "rules/openspec.md",
  ".gigacode/skills/openspec-propose/SKILL.md",
  ".serena/project.yml",
  ".gigacode/hooks/gates/_lib.py",
  ".gigacode/hooks/gates/gate_context_inject.py",
  ".gigacode/hooks/gates/gate_spec_structure.py",
  ".gigacode/hooks/gates/gate_lint.py",
  ".gigacode/hooks/gates/gate_build.py",
  ".gigacode/hooks/gates/gate_clean_code.py",
  ".gigacode/hooks/gates/gate_existing_code.py",
  ".gigacode/hooks/gates/gate_stage_order.py",
  ".gigacode/hooks/confirm.py",
  ".gigacode/stages.json",
  ".gigacode/quality-gates.json",
  "scripts/build_module_map.py",
  "scripts/test_module_map.py",
  "scripts/test_stage_order.py"
)

foreach ($path in $required) {
  if (-not (Test-Path $path)) {
    throw "Missing required file: $path"
  }
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw "Node.js is required (GigaCode runtime + hook launcher)"
}

python -m json.tool .gigacode/settings.json | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "invalid JSON: .gigacode/settings.json"
}

Get-ChildItem .gigacode/agents/*.md | ForEach-Object {
  $content = Get-Content $_ -Raw
  if ($content.Length -ge 10000) {
    throw "$($_.Name) exceeds 10000 characters"
  }
  $frontmatter = Select-String $_ -Pattern '^---$'
  if ($frontmatter.Count -lt 2) {
    throw "$($_.Name) missing frontmatter"
  }
}

$block = '{"command":"git reset --hard HEAD"}' | python .gigacode/hooks/gates/git_guard.py
if ($block -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block reset --hard"
}

$clean = '{"command":"git clean -f -d"}' | python .gigacode/hooks/gates/git_guard.py
if ($clean -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block destructive git clean"
}

$flagBypass = '{"command":"git -C . reset --hard HEAD"}' | python .gigacode/hooks/gates/git_guard.py
if ($flagBypass -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block reset --hard behind global -C flag"
}

$configBypass = '{"command":"git -c core.pager=cat clean -f -d"}' | python .gigacode/hooks/gates/git_guard.py
if ($configBypass -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block git clean behind global -c flag"
}

$wrapBypass = '{"tool_input":{"command":"cd . && git reset --hard HEAD~5"}}' | python .gigacode/hooks/gates/git_guard.py
if ($wrapBypass -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block chained git reset --hard"
}
$selfEdit = '{"tool_name":"WriteFile","tool_input":{"file_path":".gigacode/hooks/gates/git_guard.py"}}' | python .gigacode/hooks/gates/git_guard.py
if ($selfEdit -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block self-edit of enforcement file"
}

$ask = '{"path":".github/workflows/deploy.yml"}' | python .gigacode/hooks/gates/git_guard.py
if ($ask -notmatch '"decision":\s*"ask"') {
  throw "git_guard did not ask on protected path"
}

$feature = '{"prompt":"/develop-feature plan-only payment retry"}' | python .gigacode/hooks/gates/preflight_check.py
if ($feature -notmatch '"decision":\s*"allow"') {
  throw "preflight did not allow complete plan-only feature prompt"
}

# validate_development_output triggers from the working tree, not the message,
# and validates only dev dirs in the CURRENT change. Use an isolated GIGACODE_ROOT
# git fixture with a CHANGED but incomplete dev dir so the check is deterministic.
$vdoRoot = Join-Path $env:TEMP "gigacode-smoke-vdo"
Remove-Item -Recurse -Force $vdoRoot -ErrorAction SilentlyContinue
$vdoDev = Join-Path $vdoRoot "docs/development/sample"
New-Item -ItemType Directory -Force -Path $vdoDev | Out-Null
Set-Content -Path (Join-Path $vdoDev "journal.md") -Value "partial" -Encoding utf8
git -C $vdoRoot init -q
git -C $vdoRoot add -A
$env:GIGACODE_ROOT = $vdoRoot
$missing = '{"hook_event_name":"Stop","last_assistant_message":"done"}' | python .gigacode/hooks/gates/validate_development_output.py
Remove-Item Env:\GIGACODE_ROOT
Remove-Item -Recurse -Force $vdoRoot -ErrorAction SilentlyContinue
if ($missing -notmatch '"decision":\s*"block"') {
  throw "validate_development_output did not block a changed dev dir with missing artifacts"
}

python -m json.tool .gigacode/hooks/router.config.json | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "invalid JSON: .gigacode/hooks/router.config.json"
}

python -m json.tool .gigacode/stages.json | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "invalid JSON: .gigacode/stages.json"
}

python scripts/test_router.py
if ($LASTEXITCODE -ne 0) {
  throw "router tests failed"
}

python -m json.tool .gigacode/quality-gates.json | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "invalid JSON: .gigacode/quality-gates.json"
}

python scripts/test_gates.py
if ($LASTEXITCODE -ne 0) {
  throw "gate tests failed"
}

python scripts/test_stage_order.py
if ($LASTEXITCODE -ne 0) {
  throw "stage-order tests failed"
}

python scripts/test_module_map.py
if ($LASTEXITCODE -ne 0) {
  throw "module-map tests failed"
}

# gate_stage_order: a contract-stage write without the intake approval is a hard
# stop (direct gate call, mirrors the git_guard block cases above).
$stageBlock = '{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"docs/development/smoke-nope/contract.json"}}' | python .gigacode/hooks/gates/gate_stage_order.py
if ($stageBlock -notmatch '"decision":\s*"block"') {
  throw "gate_stage_order did not block a contract write without intake approval"
}

# and the same write denied through the live router route (proves it is wired).
$stageRoute = '{"tool_name":"Edit","tool_input":{"file_path":"docs/development/smoke-nope/contract.json"}}' | node .gigacode/hooks/run-hook.cjs --event PreToolUse
if ($stageRoute -notmatch '"permissionDecision":\s*"deny"') {
  throw "router did not deny a contract write without intake approval"
}
Write-Host "gate_stage_order round-trip: block + route deny OK"

if (Get-Command openspec -ErrorAction SilentlyContinue) {
  # Use 'list --specs' not 'validate --strict': validate requires --type change
  # when the name is ambiguous, and strict validation needs populated specs.
  openspec list --specs | Out-Null
  Write-Host "openspec config valid"
} else {
  Write-Warning "SKIP: openspec CLI not installed; spec validation not run"
}

if (Get-Command serena -ErrorAction SilentlyContinue) {
  Write-Host "serena CLI available"
} else {
  Write-Warning "NOTE: serena CLI not installed; Serena MCP will not start. Install with: uv tool install -p 3.13 serena-agent"
}

$launcher = '{"tool_name":"Bash","tool_input":{"command":"git reset --hard HEAD"}}' | node .gigacode/hooks/run-hook.cjs --event PreToolUse
if ($launcher -notmatch '"permissionDecision":\s*"deny"') {
  throw "launcher round-trip did not return permissionDecision: deny"
}
Write-Host "launcher round-trip: deny OK"

Write-Host "Smoke check passed"
