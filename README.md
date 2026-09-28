# PAI OS Program Intelligence

Independent Program Intelligence plugin for Placement AI (`pai-os`).

> Status: repository foundation only. No capabilities, database schema, or
> runtime integration have been implemented yet.

The complete product and architecture contract is in the
[Developer Handbook](PAI_PROGRAM_INTELLIGENCE_DEVELOPER_HANDBOOK.md).

## Intended role

The plugin will research global education programs, verify material facts
against source evidence, evaluate documented requirements against task-scoped
student context, and return structured comparison data to PAI Operator.

Planned V1 capabilities:

- `program.search`
- `program.research`
- `program.eligibility`
- `program.compare`

## Integration boundary

This repository owns all Program Intelligence domain behavior plus its
independent public-program database and migrations. The `pai-os` host will own
the generic plugin loader,
capability registration, scoped Student Context bridge, and result transport.

The plugin must not import PAI Vault models, duplicate student data, modify PAI
Counselor or Operator domain logic, or expose a separate student-facing agent.

## Repository layout

```text
src/pai_program_intelligence/  Python package
tests/                         Test suite
```

The manifest, database migrations, provider adapters, and implementation
modules will be added only after their contracts are explicitly approved.
