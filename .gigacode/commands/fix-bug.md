---
description: Investigate, plan, or implement a bug fix through the enterprise developer workflow.
---

Use the `development-flow` skill.

Run the bug workflow for these user arguments:

{{args}}

Follow this sequence:

1. Identify mode: `plan-only` unless implement mode is explicit.
2. Communicate with the user in Russian and write Markdown workflow artifacts in Russian unless the user asks otherwise.
3. Clarify symptom, expected behavior, actual behavior, reproduction evidence, affected environment, severity, and workarounds.
4. Inspect analytics, Repomix, and Graphify when available.
5. Use documented fallbacks when optional context is unavailable.
6. Map impacted code and likely failing paths before planning edits.
7. In implement mode, run git safety checks before editing source files.
8. Prefer regression evidence before making the fix when feasible.
9. Produce Markdown artifacts under `docs/development/<task-slug>/`.
10. Record verification evidence before claiming completion.
11. Do not auto-commit or auto-push.
