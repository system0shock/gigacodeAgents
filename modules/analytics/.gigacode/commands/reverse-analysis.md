---
description: Run reverse analysis for one business feature and produce AsciiDoc documentation.
---

Use the `reverse-analysis` skill.

Analyze exactly one business feature from these user arguments:

{{args}}

Follow this sequence:

1. Run intake and identify missing inputs.
2. Use Jira/Confluence only if Atlassian MCP is available.
3. Map relevant code before writing documentation.
4. Ask me to confirm scope before drafting final files.
5. After my confirmation, record the scope in `docs/scopes/<feature-slug>.md` with `Статус: подтвержден` and `Каталог результата: docs/features/<feature-slug>/`.
6. Produce Russian-language AsciiDoc files under `docs/features/<feature-name>/`.
7. Separate facts, assumptions, gaps, contradictions, and open questions.
8. Validate the output before claiming completion.
