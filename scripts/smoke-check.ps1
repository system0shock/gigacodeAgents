$ErrorActionPreference = "Stop"

$required = @(
  ".gigacode/settings.json",
  ".gigacode/skills/development-flow/SKILL.md",
  ".gigacode/commands/develop-feature.md",
  ".gigacode/commands/fix-bug.md",
  ".gigacode/hooks/git_guard.py",
  ".gigacode/hooks/preflight_check.py",
  ".gigacode/hooks/validate_development_output.py",
  "docs/templates/development-plan.md",
  "rules/development-flow.md",
  "rules/language-policy.md",
  "rules/git-safety.md",
  "rules/branch-naming.md",
  "openspec/config.yaml",
  "rules/openspec.md",
  ".gigacode/skills/openspec-propose/SKILL.md"
)

foreach ($path in $required) {
  if (-not (Test-Path $path)) {
    throw "Missing required file: $path"
  }
}

python -m json.tool .gigacode/settings.json | Out-Null

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

$block = '{"command":"git reset --hard HEAD"}' | python .gigacode/hooks/git_guard.py
if ($block -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block reset --hard"
}

$clean = '{"command":"git clean -f -d"}' | python .gigacode/hooks/git_guard.py
if ($clean -notmatch '"decision":\s*"block"') {
  throw "git_guard did not block destructive git clean"
}

$ask = '{"path":".github/workflows/deploy.yml"}' | python .gigacode/hooks/git_guard.py
if ($ask -notmatch '"decision":\s*"ask"') {
  throw "git_guard did not ask on protected path"
}

$feature = '{"prompt":"/develop-feature plan-only payment retry"}' | python .gigacode/hooks/preflight_check.py
if ($feature -notmatch '"decision":\s*"allow"') {
  throw "preflight did not allow complete plan-only feature prompt"
}

$missing = '{"last_assistant_message":"Complete in docs/development/sample-task/"}' | python .gigacode/hooks/validate_development_output.py
if ($missing -notmatch '"decision":\s*"block"') {
  throw "validate_development_output did not block missing artifacts"
}

if (Get-Command openspec -ErrorAction SilentlyContinue) {
  openspec list --specs | Out-Null
  Write-Host "openspec config valid"
} else {
  Write-Warning "SKIP: openspec CLI not installed; spec validation not run"
}

Write-Host "Smoke check passed"
