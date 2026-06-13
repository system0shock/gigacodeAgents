$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$required = @(
  ".gigacode/settings.json",
  ".gigacode/quality-gates.json",
  ".gigacode/skills/reverse-analysis/SKILL.md",
  ".gigacode/commands/reverse-analysis.md",
  "rules/openspec.md",
  "openspec/config.yaml",
  "openspec/specs/.gitkeep",
  "docs/templates/manifest.json",
  ".gigacode/hooks/router.py",
  ".gigacode/hooks/router.config.json",
  ".gigacode/hooks/hook_probe.py",
  ".gigacode/hooks/gates/_lib.py",
  ".gigacode/hooks/gates/git_guard.py",
  ".gigacode/hooks/gates/gate_context_inject.py",
  ".gigacode/hooks/gates/preflight_check.py",
  ".gigacode/hooks/gates/gate_spec_bootstrap.py",
  ".gigacode/hooks/gates/gate_techdocs.py",
  ".gigacode/hooks/gates/gate_final_format.py",
  ".gigacode/hooks/gates/validate_run_output.py",
  "docs/templates/feature-analysis.adoc",
  "rules/reverse-analysis.md",
  "rules/branch-naming.md",
  "README.md"
)

foreach ($path in $required) {
  if (-not (Test-Path $path)) {
    throw "Missing required file: $path"
  }
}

foreach ($jsonFile in @(".gigacode/settings.json", ".gigacode/hooks/router.config.json", ".gigacode/quality-gates.json", "docs/templates/manifest.json")) {
  Get-Content $jsonFile -Raw | ConvertFrom-Json | Out-Null
}

$agents = Get-ChildItem ".gigacode/agents/*.md"
if ($agents.Count -ne 3) {
  throw "Expected 3 agent files, found $($agents.Count)"
}

foreach ($agent in $agents) {
  $text = Get-Content $agent.FullName -Raw
  if ($text.Length -ge 10000) {
    throw "Agent file exceeds 10,000 characters: $($agent.Name)"
  }
  if (([regex]::Matches($text, "(?m)^---\s*$")).Count -lt 2) {
    throw "Agent file missing YAML frontmatter boundaries: $($agent.Name)"
  }
}

$session = '{"hook_event_name":"SessionStart"}' | python .gigacode/hooks/router.py --event=SessionStart | ConvertFrom-Json
if ($session.decision -ne "allow") {
  throw "Expected SessionStart routing to allow, got $($session.decision)"
}

$incomplete = '{"hook_event_name":"UserPromptSubmit","prompt":"reverse-analysis missing info"}' | python .gigacode/hooks/router.py --event=UserPromptSubmit | ConvertFrom-Json
if ($incomplete.decision -ne "block") {
  throw "Expected incomplete reverse-analysis prompt to block, got $($incomplete.decision)"
}

$template = Get-Content "docs/templates/feature-analysis.adoc" -Raw
if (-not $template.TrimStart().StartsWith("=")) {
  throw "AsciiDoc template must start with a document title"
}

if (-not (Select-String -Path "openspec/config.yaml" -Pattern '^schema:' -Quiet)) {
  throw "openspec/config.yaml must declare a schema"
}

$repomix = Get-ChildItem -Recurse -File ".gigacode/agents", "rules" |
  Select-String -Pattern 'repomix' -SimpleMatch
if ($repomix) {
  throw "repomix must not appear in agents or rules"
}

foreach ($d in @("architecture", "analytics/use-case", "analytics/integration/nfr and contact", "analytics/db/data-model")) {
  if (-not (Test-Path (Join-Path $d ".gitkeep"))) {
    throw "Missing final-tree skeleton dir: $d"
  }
}

python scripts/test_router.py
if ($LASTEXITCODE -ne 0) { throw "test_router.py failed" }
python scripts/test_gates.py
if ($LASTEXITCODE -ne 0) { throw "test_gates.py failed" }

Write-Host "Analytics module smoke check passed."
