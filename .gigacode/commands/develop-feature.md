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
4. Inspect analytics and Graphify when available.
5. Use documented fallbacks when optional context is unavailable.
6. Map impacted code before planning edits.
7. In implement mode, run git safety checks before editing source files.
8. Create or continue an OpenSpec change with `/opsx:propose`; keep the
   authoritative spec under `openspec/changes/<change-id>/` and validate it with
   `openspec validate <change-id> --strict`.
9. Produce human run notes under `docs/development/<task-slug>/` that link to the
   OpenSpec change.
10. Record verification evidence before claiming completion.
11. Do not auto-commit or auto-push.
