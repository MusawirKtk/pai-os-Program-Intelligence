# PAI OS Program Intelligence

Independent Program Intelligence plugin for Placement AI (`pai-os`).

> Status: Milestones 1–3 are implemented. Milestone 4 now has offline verification,
> deduplication, freshness, PostgreSQL migrations, and cache code. Applying the
> migration against a separate live database remains untested until one is provided.

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
priority while preserving search rank among equal-priority pages. Search
snippets are leads only. A fetched page retains its extracted
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

## Extraction and normalization

`extract_program` reads fetched Markdown and returns source-linked claims plus
the original extracted text. It parses explicit program headings, duration,
ECTS credits, requirements, tuition or other fees, and application deadlines. A single source
produces `unverified` claims; ambiguous currencies, dates, qualification
equivalencies, and unsupported formats remain `needs_review`. Missing values
are reported as not observed, never guessed.

For a live one-source check, create `.env` beside this README using
[`.env.example`](.env.example) and place `TAVILY_API_KEY` there. The `.env` file
is ignored by Git. The library reads only process environment variables; the
standalone `smoke_m3.py` script can also read this repository's own `.env`.
It never reads the separate `pai-os` repository's configuration.

```powershell
python -B smoke_m3.py --domain manchester.ac.uk --url https://www.manchester.ac.uk/study/masters/courses/list/02362/msc-statistics --publisher "University of Manchester" --expected-name "MSc Statistics"
```

The script also accepts `--query` instead of `--url`. Use `--expected-name` to
reject a fetched page that does not establish the requested program identity.
It reports claim counts and field names, not the key or page text. Live pages
often contain ambiguous prose, so review-needed claims are expected; this
smoke test does not perform cross-source verification.

Run the offline test suite with `PYTHONPATH=src` set (or install this package
in editable mode). For example, in PowerShell:

```powershell
$env:PYTHONPATH='src'; python -B -m unittest discover -s tests
```

## Verification and public cache

Milestone 4 cross-checks current official pages for a resolved program. Two
distinct, non-identical pages can corroborate a fact; conflicting values retain
both source IDs. Stale, ambiguous, and missing facts stay explicit. The public
cache keeps raw page snapshots and claims alongside the latest normalized
requirements, costs, and verification states.

The cache uses its own PostgreSQL database and `program_intelligence` schema.
Set `PROGRAM_INTELLIGENCE_DATABASE_URL` in the plugin process environment;
`connect_database()` intentionally does not read the PAI host's `DATABASE_URL`
or any host database. `apply_migrations()` applies packaged SQL migrations
transactionally. A placeholder is in [`.env.example`](.env.example); the
library does not load `.env` automatically. Do not point this variable at the
PAI application database during standalone development. No database has been
created or migrated by the repository's offline tests.

After provisioning a separate PostgreSQL database, add its URL to this repo's
ignored `.env`, confirm it is **not** the PAI application database, then run:

```powershell
python -B smoke_m4.py --apply
```

The command reports applied migration names and table count, never the URL.
It has not been run against a live database yet.

The actual PAI Core registration and student-context bridge remain Milestone 7.

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
