# Repository instructions

## Purpose

This repository owns the complete PAI Program Intelligence plugin. It is
separate from `pai-os` and will later attach to that host through a stable,
generic plugin contract.

## Repository boundary

- Keep all Program Intelligence domain code, schemas, source adapters,
  persistence, migrations, tests, and the plugin manifest in this repository.
- Do not place Program Intelligence domain logic in `pai-os`.
- Do not edit the sibling `pai-os` repository unless the user explicitly asks
  for a host-side integration change.
- The `pai-os` repository owns only generic plugin infrastructure: discovery,
  loading, registration, scoped context delivery, result/error transport, and
  lifecycle hooks.

## Product boundary

The plugin will eventually expose:

- `program.search`
- `program.research`
- `program.eligibility`
- `program.compare`

It owns public program and institution intelligence. It must not own or copy
student identity, profile, memory, documents, journey state, or conversations.
Student data is accepted only as least-privilege, task-scoped context supplied
by the host. Never query PAI Vault tables directly.

The plugin is not a chatbot, counselor, admissions-probability engine,
application-submission system, or student-facing UI. It returns structured,
source-backed results to PAI Operator; PAI Counselor owns student-facing prose
and recommendations.

## Development rules

- Preserve raw source evidence beside normalized facts.
- Prefer official sources; search snippets are discovery leads only.
- Return explicit unknown, stale, partial, or conflicting states instead of
  guessing.
- Keep the domain independent from `pai-os` physical database models.
- Keep provider and host integration behind narrow contracts.
- Do not add speculative abstractions, dependencies, or infrastructure.

## Approval policy

Before web research, installing dependencies, using external services,
changing GitHub state, implementing a new phase, or making a material
architecture decision, explain the next step and obtain user confirmation.
Never expose or commit credentials.
