$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$required = @(
  ".gigacode/settings.json",
  ".gigacode/skills/reverse-analysis/SKILL.md",
  ".gigacode/commands/reverse-analysis.md",
  ".gigacode/hooks/preflight_check.py",
  ".gigacode/hooks/validate_output.py",
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

Get-Content ".gigacode/settings.json" -Raw | ConvertFrom-Json | Out-Null

$agents = Get-ChildItem ".gigacode/agents/*.md"
if ($agents.Count -ne 4) {
  throw "Expected 4 agent files, found $($agents.Count)"
}

foreach ($agent in $agents) {
  $text = Get-Content $agent.FullName -Raw
  if ($text.Length -ge 10000) {
    throw "Agent file exceeds 10,000 characters: $($agent.Name)"
  }
  if (($text -split "`n" | Select-String -Pattern "^---$").Count -lt 2) {
    throw "Agent file missing YAML frontmatter boundaries: $($agent.Name)"
  }
}

$skillBoundaries = (Get-Content ".gigacode/skills/reverse-analysis/SKILL.md" | Select-String -Pattern "^---$").Count
if ($skillBoundaries -lt 2) {
  throw "Skill file missing YAML frontmatter boundaries"
}

$commandBoundaries = (Get-Content ".gigacode/commands/reverse-analysis.md" | Select-String -Pattern "^---$").Count
if ($commandBoundaries -lt 2) {
  throw "Command file missing YAML frontmatter boundaries"
}

$preflightOk = '{"prompt":"reverse-analysis feature Card Blocking jira ABC-123"}' | python .gigacode/hooks/preflight_check.py | ConvertFrom-Json
if ($preflightOk.decision -ne "allow") {
  throw "Expected complete preflight sample to allow, got $($preflightOk.decision)"
}

$preflightIgnored = '{"prompt":"hello"}' | python .gigacode/hooks/preflight_check.py | ConvertFrom-Json
if ($preflightIgnored.decision -ne "allow") {
  throw "Expected unrelated prompt to allow, got $($preflightIgnored.decision)"
}

$validationMissing = '{"last_assistant_message":"Reverse analysis complete in docs/features/card-blocking/"}' | python .gigacode/hooks/validate_output.py | ConvertFrom-Json
if ($validationMissing.decision -ne "block") {
  throw "Expected missing output validation sample to block, got $($validationMissing.decision)"
}

$template = Get-Content "docs/templates/feature-analysis.adoc" -Raw
if (-not $template.TrimStart().StartsWith("=")) {
  throw "AsciiDoc template must start with a document title"
}

try {
  New-Item -ItemType Directory -Force -Path "docs/features/tmp-smoke" | Out-Null
  Set-Content -Path "docs/features/tmp-smoke/overview.adoc" -Value "= Обзор`n`nИсточник: код`n`nОписание функции." -Encoding UTF8
  Set-Content -Path "docs/features/tmp-smoke/flow.adoc" -Value "= Поток`n`nИсточник: код`n`nОсновной сценарий." -Encoding UTF8
  Set-Content -Path "docs/features/tmp-smoke/integrations.adoc" -Value "= Интеграции`n`nИсточник: код`n`nВнешние системы." -Encoding UTF8
  Set-Content -Path "docs/features/tmp-smoke/data.adoc" -Value "= Данные`n`nИсточник: код`n`nСущности и таблицы." -Encoding UTF8
  Set-Content -Path "docs/features/tmp-smoke/questions.adoc" -Value "= Вопросы`n`nСтатус: открытый вопрос`n`nУточнить лимиты." -Encoding UTF8
  Set-Content -Path "docs/scopes/tmp-smoke.md" -Value "# Область анализа: tmp-smoke`n`nСтатус: подтвержден`n`nКаталог результата: docs/features/tmp-smoke/" -Encoding UTF8

  $decision = ('{"last_assistant_message":"Reverse analysis complete in docs/features/tmp-smoke/"}' | python .gigacode/hooks/validate_output.py | ConvertFrom-Json).decision
  if ($decision -ne "allow") {
    throw "Expected valid scoped output to allow, got $decision"
  }

  Set-Content -Path "docs/features/tmp-smoke/overview.adoc" -Value "= Обзор`n`nОписание функции без меток." -Encoding UTF8
  $decision = ('{"last_assistant_message":"Reverse analysis complete in docs/features/tmp-smoke/"}' | python .gigacode/hooks/validate_output.py | ConvertFrom-Json).decision
  if ($decision -ne "block") {
    throw "Expected missing evidence labels to block, got $decision"
  }
} finally {
  Remove-Item -Recurse -Force "docs/features/tmp-smoke" -ErrorAction SilentlyContinue
  Remove-Item -Force "docs/scopes/tmp-smoke.md" -ErrorAction SilentlyContinue
}

Write-Host "Analytics module smoke check passed."
