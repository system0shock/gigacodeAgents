---
description: Run the one-time reverse-analysis bootstrap for one business feature.
---

Use the `reverse-analysis` skill.

Analyze exactly one business feature from these user arguments:

{{args}}

Follow the skill's pipeline and manifest lifecycle:

1. Do intake in this session; record scope in
   `docs/features/<feature>/journal.md` and create `manifest.json`
   (status `scoping`, from `docs/templates/manifest.json`).
2. Use Jira/Confluence only if Atlassian MCP is available; otherwise state the
   limitation explicitly.
3. Run code mapping, then stop and ask me to confirm scope.
4. Draft the five technical `.adoc` files (status `draft`), then run evidence
   review (status `confirmed`).
5. Derive the capability spec under `openspec/specs/<capability>/spec.md`.
6. Generate the final `analytics/` + `architecture/` tree.
7. Run derivation verification and close the run (status `complete`).

Separate facts, assumptions, gaps, contradictions, and open questions throughout.
