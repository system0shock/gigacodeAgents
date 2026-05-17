---
description: Plan or implement a feature through the enterprise developer workflow.
---

Use the `development-flow` skill.

Run the feature workflow for these user arguments:

{{args}}

Follow this sequence:

1. Identify mode: `plan-only` unless implement mode is explicit.
2. Communicate with the user in Russian and write Markdown workflow artifacts in Russian unless the user asks otherwise.
3. Clarify feature goal, acceptance criteria, included scope, excluded scope, and constraints.
4. Inspect analytics, Repomix, and Graphify when available.
5. Use documented fallbacks when optional context is unavailable.
6. Map impacted code before planning edits.
7. In implement mode, run git safety checks before editing source files.
8. Produce Markdown artifacts under `docs/development/<task-slug>/`.
9. Record verification evidence before claiming completion.
10. Do not auto-commit or auto-push.
