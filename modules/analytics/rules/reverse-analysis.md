# Reverse Analysis Rules

Reverse analysis is performed for one business feature at a time.

## Source Priority

1. Code is the source of current implementation truth.
2. Jira is requirements context and may be stale.
3. Confluence is architecture context and may be stale.
4. User input is accepted scope context and must be labeled.

## Workflow Invariants

- Map code before drafting documentation.
- Ask before inventing missing context.
- Put unsupported statements in assumptions or questions.
- Use AsciiDoc for final analyst deliverables.
- Save feature outputs under `docs/features/<feature-name>/`.
- Stop for analyst confirmation after code mapping and before final writing.

## Evidence Labels

Use clear labels in generated AsciiDoc:

- `Source: code`
- `Source: jira`
- `Source: confluence`
- `Source: user`
- `Status: assumption`
- `Status: open question`
