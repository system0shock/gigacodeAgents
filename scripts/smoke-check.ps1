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
  ".gigacode/quality-gates.json",
  "scripts/build_module_map.py",
  "scripts/test_module_map.py"
)

foreach ($path in $required) {
  if (-not (Test-Path $path)) {
    throw "Missing required file: $path"
  }
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

$ask = '{"path":".github/workflows/deploy.yml"}' | python .gigacode/hooks/gates/git_guard.py
if ($ask -notmatch '"decision":\s*"ask"') {
  throw "git_guard did not ask on protected path"
}

$feature = '{"prompt":"/develop-feature plan-only payment retry"}' | python .gigacode/hooks/gates/preflight_check.py
if ($feature -notmatch '"decision":\s*"allow"') {
  throw "preflight did not allow complete plan-only feature prompt"
}

$missing = '{"last_assistant_message":"Complete in docs/development/sample-task/"}' | python .gigacode/hooks/gates/validate_development_output.py
if ($missing -notmatch '"decision":\s*"block"') {
  throw "validate_development_output did not block missing artifacts"
}

python -m json.tool .gigacode/hooks/router.config.json | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "invalid JSON: .gigacode/hooks/router.config.json"
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

python scripts/test_module_map.py
if ($LASTEXITCODE -ne 0) {
  throw "module-map tests failed"
}

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

Write-Host "Smoke check passed"
