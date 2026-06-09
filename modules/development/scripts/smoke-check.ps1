$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$required = @(
  ".gigacode/settings.json",
  ".gigacode/skills/feature-development/SKILL.md",
  ".gigacode/skills/junit-testing/SKILL.md",
  ".gigacode/commands/develop.md",
  ".gigacode/commands/write-tests.md",
  ".gigacode/hooks/router.py",
  ".gigacode/hooks/router_config.json",
  "docs/templates/plan-template.md",
  "docs/serena-mcp.sample.json",
  "rules/development.md",
  "rules/plan-format.md",
  "rules/testing.md",
  "rules/branch-naming.md",
  "README.md"
)

foreach ($path in $required) {
  if (-not (Test-Path $path)) {
    throw "Missing required file: $path"
  }
}

Get-Content ".gigacode/settings.json" -Raw | ConvertFrom-Json | Out-Null
Get-Content ".gigacode/hooks/router_config.json" -Raw | ConvertFrom-Json | Out-Null
Get-Content "docs/serena-mcp.sample.json" -Raw | ConvertFrom-Json | Out-Null
python -m compileall -q .gigacode/hooks | Out-Null

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

$docs = @(
  ".gigacode/skills/feature-development/SKILL.md",
  ".gigacode/skills/junit-testing/SKILL.md",
  ".gigacode/commands/develop.md",
  ".gigacode/commands/write-tests.md"
)
foreach ($doc in $docs) {
  $boundaries = (Get-Content $doc | Select-String -Pattern "^---$").Count
  if ($boundaries -lt 2) {
    throw "File missing YAML frontmatter boundaries: $doc"
  }
}

$references = @("junit-rules", "kotlin-style", "java-style", "mocking", "assertions", "build-tools")
foreach ($ref in $references) {
  $refPath = "reference/$ref.md"
  if (-not (Test-Path $refPath)) {
    throw "Missing reference file: $refPath"
  }
  if (-not (Get-Content $refPath | Select-String -Pattern "^## Digest")) {
    throw "Reference file missing '## Digest' section: $refPath"
  }
}

$decision = ('{"prompt":"hello"}' | python .gigacode/hooks/router.py UserPromptSubmit | ConvertFrom-Json).decision
if ($decision -ne "allow") {
  throw "Expected unrelated prompt to allow, got $decision"
}

$outputRaw = '{"prompt":"implement card blocking limit DEV-123"}' | python .gigacode/hooks/router.py UserPromptSubmit
$output = $outputRaw | ConvertFrom-Json
if ($output.decision -ne "allow") {
  throw "Expected complete dev prompt to allow, got $($output.decision)"
}
if ($outputRaw -notmatch "additionalContext") {
  throw "Expected dev prompt to inject additional context"
}

$decision = ('{"prompt":"implement stuff"}' | python .gigacode/hooks/router.py UserPromptSubmit | ConvertFrom-Json).decision
if ($decision -ne "ask") {
  throw "Expected incomplete dev prompt to ask, got $decision"
}

$decision = ('{"tool_name":"Write","tool_input":{"file_path":"src/main/kotlin/com/example/Foo.kt","content":"x"}}' | python .gigacode/hooks/router.py PreToolUse | ConvertFrom-Json).decision
if ($decision -ne "ask") {
  throw "Expected source edit without plan to ask, got $decision"
}

$decision = ('{"tool_name":"Bash","tool_input":{"command":"rm -rf build"}}' | python .gigacode/hooks/router.py PreToolUse | ConvertFrom-Json).decision
if ($decision -ne "block") {
  throw "Expected dangerous command to block, got $decision"
}

$outputRaw = '{"tool_name":"Write","tool_input":{"file_path":"src/test/kotlin/com/example/FooTest.kt","content":"x"}}' | python .gigacode/hooks/router.py PreToolUse
if ($outputRaw -notmatch "junit-rules") {
  throw "Expected test-file edit to inject junit reference digest"
}

Copy-Item "scripts/fixtures/sample-plan-good.md" "docs/plans/tmp-smoke-plan.md"
try {
  $decision = ('{"tool_name":"Write","tool_input":{"file_path":"src/main/kotlin/com/example/Foo.kt","content":"x"}}' | python .gigacode/hooks/router.py PreToolUse | ConvertFrom-Json).decision
} finally {
  Remove-Item "docs/plans/tmp-smoke-plan.md"
}
if ($decision -ne "allow") {
  throw "Expected source edit with approved plan to allow, got $decision"
}

$decision = ('{"tool_name":"Write","tool_input":{"file_path":"scripts/fixtures/BadService.java"}}' | python .gigacode/hooks/router.py PostToolUse | ConvertFrom-Json).decision
if ($decision -ne "block") {
  throw "Expected bad production fixture to block, got $decision"
}

$decision = ('{"tool_name":"Write","tool_input":{"file_path":"scripts/fixtures/BadServiceTest.java"}}' | python .gigacode/hooks/router.py PostToolUse | ConvertFrom-Json).decision
if ($decision -ne "block") {
  throw "Expected JUnit 4 test fixture to block, got $decision"
}

$decision = ('{"tool_name":"Write","tool_input":{"file_path":"scripts/fixtures/GoodService.kt"}}' | python .gigacode/hooks/router.py PostToolUse | ConvertFrom-Json).decision
if ($decision -ne "allow") {
  throw "Expected clean fixture to allow, got $decision"
}

$decision = ('{"last_assistant_message":"thinking..."}' | python .gigacode/hooks/router.py Stop | ConvertFrom-Json).decision
if ($decision -ne "allow") {
  throw "Expected non-completion message to allow on Stop, got $decision"
}

$probe = @"
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
"@
$probe | python -

Write-Host "Development module smoke check passed."
