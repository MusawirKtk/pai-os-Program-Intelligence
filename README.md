# PAI OS Program Intelligence

Independent Program Intelligence plugin for Placement AI (`pai-os`).

> Status: Milestones 1–6 are implemented, with a standalone end-to-end runner.
> The Milestone 4 migration and a live one-program research run have been
> exercised against the isolated local PostgreSQL database. Host registration
> remains Milestone 7.

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
It is safe to rerun: previously applied migrations are skipped.

## Eligibility (Milestone 5)

`evaluate_eligibility(program_id, requirements, context)` evaluates documented
requirements against a task-scoped context in memory. It returns a status for
each requirement, cited program source IDs, an overall documented match, and
the specific context still needed. It never stores student data, queries the
PAI Vault, or predicts admission. Only requirements marked `verified` can
yield `MET` or `NOT_MET`; the caller must refresh stale source verification
before evaluation. Degree evidence must explicitly say `completed: true` to
count as an awarded qualification. Ambiguous equivalences and incomparable
grading scales remain `NEEDS_REVIEW`.

Run the synthetic handbook-style example without network or database access:

```powershell
python -B smoke_m5.py
```

To try your own **task-scoped** context, copy
[`examples/m5_demo.json`](examples/m5_demo.json) outside the Git repository,
edit its `context` and public `requirements`, then run
`python -B smoke_m5.py --input C:\path\to\your-fixture.json`. Do not put real
student identity or full profiles in a committed fixture. A `verified` label
in hand-written JSON is only test input, not evidence that a real requirement
has been verified. The eventual live flow must use researched source-backed
requirements.

This simpler context-to-requirement test remains useful when you already have
documented requirements. It does not research or verify the JSON claims.

## Comparison and standalone end-to-end test (Milestone 6)

`compare_programs()` returns a 12-dimension evidence matrix for two or more
researched programs, including requirement matches, tuition, duration, location,
mode, intakes, deadlines, curriculum, application materials, and funding. Each
cell retains verification state and source IDs. Missing, stale, and conflicting
values stay visible; the plugin never ranks programs or converts currencies.
Only dimensions with source-backed data can be verified.

The standalone runner executes official-source discovery/fetch, extraction,
verification, public-cache persistence (live mode), eligibility, and comparison
without PAI/V3. It accepts **task-scoped** local JSON, not a student profile.
`context` is used in memory for matching and is never sent to Tavily or stored
in the public database. Keep real student identity and full profiles out of the
repository and search queries.

Run the fully offline synthetic two-program example (no key or DB required):

```powershell
.\.venv\Scripts\python.exe -B standalone_cli.py --input examples/standalone_demo.json
```

To try your own context, copy the example JSON **outside** the repository,
replace `context`, and keep the synthetic `pages` or supply your own public-page
fixtures. The `as_of` timestamp is available only in offline mode, for
repeatable freshness tests. Synthetic pages can exercise logic but do not prove
real-world program facts.

For a live one-program run using this repo's ignored `.env` and the **separate
plugin PostgreSQL database**:

```powershell
.\.venv\Scripts\python.exe -B standalone_cli.py --input examples/live_demo.json --live
```

Live input may contain multiple program targets for comparison. For each,
provide `institution` (`institution_id`, `name`, ISO country), `expected_name`,
`official_domains`, and either `official_url`, `query`, or both. Optional
`source_urls` lets you add more official pages for cross-checking. Every fetched
page must establish the expected program name in its heading; rejected URLs
are reported. Search snippets are only leads. At least two distinct current
official pages making the same claim are needed for verification, so a normal
one-page live run will often return `unverified`/`needs_review`.

The current extractor handles only explicit headings and selected duration,
ECTS, tuition, deadline, and requirement patterns. Other handbook dimensions
may correctly appear as `not_found` or `needs_review`; the runner is a way to
expose and test these gaps before PAI integration, not proof that every global
program page is fully understood. Live Tavily access requires network egress.

The actual PAI Core registration and student-context bridge remain Milestone 7;
they are **not** required to test the plugin standalone.

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
