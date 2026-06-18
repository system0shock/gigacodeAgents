# OpenSpec Format Rules

GigaCode developer workflows manage their authoritative specifications with
OpenSpec. Agents MUST follow these conventions. Human-facing run notes still go
under `docs/development/<task-slug>/`; the authoritative, validatable spec lives
under `openspec/`.

## Directory layout

```
openspec/
  config.yaml
  specs/<capability>/spec.md        # current truth, per capability
  changes/<change-id>/
    proposal.md                     # why + what
    design.md                       # how
    tasks.md                        # implementation checklist
    specs/<capability>/spec.md      # delta for this change
  changes/archive/                  # completed changes
```

## Spec requirement format

Every requirement MUST have at least one scenario. Use these literal headers:

```markdown
## ADDED Requirements

### Requirement: Short imperative name
The system SHALL ...

#### Scenario: Named scenario
- **WHEN** <condition>
- **THEN** <expected outcome>
```

In a change's delta spec, the top-level section is one of:
`## ADDED Requirements`, `## MODIFIED Requirements`, `## REMOVED Requirements`,
`## RENAMED Requirements`.

## Change artifacts

- `proposal.md` sections: `## Why`, `## What Changes`, `## Capabilities`
  (`### New Capabilities`, `### Modified Capabilities`), `## Impact`.
- `design.md` sections: `## Context`, `## Goals / Non-Goals`, `## Decisions`,
  `## Risks / Trade-offs`.
- `tasks.md`: numbered task groups (`## 1. Group`) with `- [ ]` checkbox items.

## Validation

A change is not "ready" until `openspec validate <change-id> --strict` passes.
Run `openspec validate --specs` to validate current-truth specs. Treat a
non-zero exit as a blocking failure; fix the structure, do not bypass it.

## Lifecycle

1. `/opsx:propose "<idea>"` — create the change and all artifacts.
2. `/opsx:apply` — implement the tasks.
3. `/opsx:archive` — move the completed change to `changes/archive/` and update
   `openspec/specs/`.
