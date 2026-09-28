# PAI OS Program Intelligence

Independent Program Intelligence plugin for Placement AI (`pai-os`).

> Status: Milestone 1 data contracts and Milestone 2 source layer are implemented.
> Fact extraction, database persistence, and host integration are pending.

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

## Source layer

`ResearchClient` provides search and fetch operations. Discovery accepts
trusted official institution domains from a vetted source, filters search
results to those domains, classifies page URLs, and orders them by source
priority. Search snippets are leads only. A fetched page retains its extracted
text and source metadata for later fact extraction; fetching does not verify
any requirement, fee, or deadline.

`TavilyResearchClient` implements the interface using Tavily Search and Extract.
It reads `TAVILY_API_KEY` (or the existing `WEB_SEARCH_API_KEY`) from the process
environment, or accepts a key injected by the application. It does not load
`.env` files itself. The `.env` file is gitignored; never commit a key.

Only the fixed Tavily API host is called by this adapter. Tavily reports an
extracted URL, but its response does not prove the full redirect chain. The
source layer checks the reported URL against the trusted domains; network
egress and redirect policy remain the responsibility of the approved provider
or host integration.

Tavily API behavior was checked against the official
[Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)
and [Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)
documentation. Tests use local fake responses and require no API key.

## Integration boundary

This repository owns all Program Intelligence domain behavior plus its
independent public-program database and migrations. The `pai-os` host will own
the generic plugin loader, capability registration, scoped Student Context
bridge, and result transport.

The plugin must not import PAI Vault models, duplicate student data, modify PAI
Counselor or Operator domain logic, or expose a separate student-facing agent.

## Repository layout

```text
src/pai_program_intelligence/  Python package, schemas, source layer, manifest
tests/                         Test suite
```

The manifest follows the handbook's proposed Capability Contract v1 shape.
The current `pai-os` V3 checkout has no published host contract yet, so the
registration adapter and final compatibility check belong to Milestone 7.
