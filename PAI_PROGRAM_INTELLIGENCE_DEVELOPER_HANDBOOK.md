# PAI Program Intelligence — Developer Handbook
**Package ID:** `pai.program_intelligence`  
**Product:** Placement AI (PAI)  
**Audience:** Backend, AI, data, research, and platform developers  
**Status:** Architecture/implementation contract for V1  
**Repository:** `MusawirKtk/pai-os-Program-Intelligence`  
**Host product:** `memsa771-hub/pai-os` (`v3`)  

## 1. Purpose
PAI Program Intelligence is the education-opportunity intelligence capability of Placement AI.

Its job is to answer one core question:

> **What educational programs exist, what is actually true about them right now, and how do their documented requirements compare with this student's current profile and constraints?**

This is not a chatbot, not a second counselor, and not a separate student-facing agent. It is a domain capability used by PAI Operator.

The student continues to interact only with **PAI Counselor**. PAI Counselor understands the student and the journey. PAI Operator coordinates execution. Program Intelligence performs specialized university/program research and returns structured, source-backed results.

The capability must be designed for a **global student community**, not for one country, one qualification system, or one university type.

### 1.1 Repository and deployment boundary
Program Intelligence is developed and versioned in this standalone repository.
It is not implemented inside the `pai-os` source tree and must not depend on
`pai-os` physical models, database sessions, or private modules.

This repository owns:

- all Program Intelligence domain code and schemas
- source, extraction, normalization, verification, eligibility, and comparison logic
- its independent public-program database, connection configuration, and migrations
- its manifest, tests, fixtures, and release artifacts

The `pai-os` host owns only generic plugin infrastructure: discovery/loading,
capability registration, task-scoped Student Context delivery, result/error
transport, and lifecycle hooks. The final package-or-service deployment binding
will be selected when that host contract is approved; do not couple the domain
to either form prematurely.

## 2. Position in PAI

```text
                         STUDENT

                 ┌──────────┴──────────┐
                 ▼                     ▼
          STUDENT VAULT          STUDENT JOURNEY
          canonical facts        active journey state
                 │                     │
                 └──────────┬──────────┘
                            ▼
                      PAI COUNSELOR
                            │
                            ▼
                       PAI OPERATOR
                            │
                            ▼
                    CAPABILITY ROUTER
                            │
                            ▼
                PAI PROGRAM INTELLIGENCE
                            │
          ┌─────────────────┼──────────────────┐
          ▼                 ▼                  ▼
     Official web      Structured data      Public APIs
       sources           providers          when available
```

Program Intelligence must never bypass this architecture.

## 3. What Program Intelligence Owns
Program Intelligence owns **external education opportunity intelligence**.

It may own/cache public domain data such as:

- institutions
- schools/faculties
- programs
- program levels
- program locations/campuses
- modes of study
- duration
- credits
- intakes
- application windows
- deadlines
- academic entry requirements
- prerequisite subjects/courses
- grade requirements
- language requirements
- standardized test requirements
- work-experience requirements
- portfolios/auditions/interviews when documented
- required application materials
- tuition and mandatory program fees
- deposits where documented
- official funding/scholarship links associated with the institution/program
- program curriculum/areas of concentration where documented
- accreditation/status where relevant and verifiable
- official source URLs
- source timestamps
- verification/conflict/freshness state

Program Intelligence may also evaluate a supplied student context against documented program requirements and return an **evidence-based requirement match**.

## 4. What Program Intelligence Does NOT Own
Program Intelligence must not own or duplicate:

- student identity
- student education records
- student goals
- student finances
- student test history
- student documents
- student preferences
- student memory
- student journey/roadmap
- counseling state
- application documents such as SOP/CV
- application submission
- student conversations

### Non-negotiable rule
> **Plugins consume Student Context; plugins do not own Student Data.**

Do not create a `program_intelligence_student_profile` table or any equivalent copy of the Vault.

## 5. Student Data Access
Program Intelligence must receive task-scoped student context through the PAI Student Context Gateway / capability context contract.

It must not query Vault tables directly.

Example requested context for a program-matching task:

```json
{
  "education": {
    "current_or_highest": {},
    "history": []
  },
  "goals": {
    "target_level": "masters",
    "target_field": "artificial intelligence"
  },
  "tests": [],
  "finance": {"budget": {}},
  "preferences": {
    "target_countries": ["DE"],
    "study_mode": ["on_campus"]
  }
}
```

Do not request unnecessary personal data. A general MSc AI search normally does not require preferred name, gender, exact DOB, passport number, or phone number.

Use least-privilege context.

## 6. Global-First Design Rules
The implementation must not assume:

- GPA is always on a 4.0 scale
- every student completed A Levels
- every program is called a bachelor's or master's
- every institution is a university
- every program uses semesters
- every fee is annual
- every deadline is a single date
- every applicant uses IELTS
- all international students have the same requirements
- program requirements are identical across nationalities
- admission requirements are expressed numerically

Support global variation.

Use standard identifiers where practical:

- countries: ISO 3166-1 alpha-2
- currencies: ISO 4217
- languages: stable canonical/BCP-47 codes
- dates: ISO 8601
- URLs: canonical HTTPS URL when available

Never convert local academic systems into a fake universal number unless an official equivalency or a PAI-approved normalization rule exists.

Always retain original/raw requirement text alongside normalized structure.

## 7. Capability Surface — V1
V1 should expose a small number of high-value capabilities.

### 7.1 `program.search`
Discover candidate educational programs matching structured constraints.

Typical inputs:
- target level
- field/discipline
- countries/regions
- intake
- mode
- language
- budget constraints
- explicit filters
- result limit

Typical output:
- candidate program identities
- institution
- official program URL
- high-level location/level
- preliminary verification state
- sources
- missing/uncertain fields

`program.search` is discovery, not final recommendation.

### 7.2 `program.research`
Perform deep research on one or more specified programs.

Research should attempt to collect:
- official program identity
- institution
- school/faculty
- award/level
- mode
- campus/location
- duration
- credits
- intakes
- application deadline/window
- academic requirements
- prerequisite subjects/courses
- language requirements
- standardized tests
- work experience
- required documents
- tuition/fees
- funding links
- curriculum
- official sources
- conflicts/unknowns
- fetched timestamps

A missing fact must be returned as unknown, not invented.

### 7.3 `program.eligibility`
Compare supplied Student Context against verified program requirements.

Allowed requirement states:

```text
MET
NOT_MET
UNKNOWN
NEEDS_REVIEW
NOT_APPLICABLE
```

Do not return unsupported admission probabilities. Eligibility here means **documented requirement match**, not predicted acceptance.

### 7.4 `program.compare`
Compare previously researched programs using normalized dimensions such as:
- academic requirements
- prerequisite gaps
- language/test requirements
- tuition
- duration
- location
- mode
- intake
- deadlines
- curriculum focus
- required application materials
- verified funding links

Return an evidence matrix. Do not hide missing/conflicting data.

### Optional later capabilities
Not required for initial V1:

```text
institution.research
program.watch
program.deadline_watch
program.funding_search
program.curriculum_compare
```

Do not expand scope until V1 is reliable.

## 8. Do Not Build `program.shortlist` as a Black Box
Program Intelligence may return candidates and structured match evidence.

The final student-facing recommendation belongs to PAI Counselor using:
- Vault
- Student Journey
- Counseling Policy
- Program Intelligence findings

Avoid opaque plugin-specific scores such as `91/100` for V1. Prefer evidence states.

Example:

```json
{
  "academic_requirements": "MET",
  "language_requirement": "MET",
  "budget_constraint": "NEEDS_REVIEW",
  "prerequisites": "UNKNOWN",
  "deadline": "OPEN",
  "evidence_quality": "HIGH"
}
```

## 9. Program Data Model
Use a stable normalized output schema. The physical database may differ, but the capability contract should remain stable.

```json
{
  "program_id": "stable-internal-id",
  "institution": {
    "institution_id": "stable-internal-id",
    "name": "Example University",
    "country": "DE",
    "city": "Munich",
    "official_url": "https://..."
  },
  "program": {
    "name": "MSc Artificial Intelligence",
    "award": "MSc",
    "level": "masters",
    "field": ["artificial_intelligence", "computer_science"],
    "mode": "on_campus",
    "campus": "Main Campus",
    "official_url": "https://...",
    "duration": {"value": 2, "unit": "years"},
    "credits": {"value": 120, "system": "ECTS"}
  },
  "offerings": [],
  "requirements": [],
  "costs": [],
  "funding": [],
  "curriculum": {},
  "sources": [],
  "verification": {}
}
```

Do not force a field to exist when the institution does not publish it.

## 10. Program Offering / Intake Model
A program can have multiple offerings.

```json
{
  "intake_id": "2027-fall",
  "term": "fall",
  "academic_year": "2027/2028",
  "start_date": "2027-10-01",
  "application_window": {
    "opens": "2026-12-01",
    "closes": "2027-03-15"
  },
  "deadline_type": "hard",
  "applicant_scope": "international",
  "status": "open"
}
```

Do not assume domestic/international deadlines are identical or that there is only one intake.

## 11. Requirement Model
Requirements are the hardest part of global education research. Keep both original evidence and normalized interpretation.

```json
{
  "requirement_id": "req-123",
  "type": "academic_degree",
  "applies_to": {
    "applicant_type": "international",
    "countries": []
  },
  "raw_text": "Applicants must hold a relevant bachelor's degree...",
  "normalized": {
    "level": "bachelors",
    "field": ["computer_science", "related_field"]
  },
  "required": true,
  "verification_status": "verified",
  "source_id": "source-456"
}
```

Possible requirement types:

```text
academic_degree
minimum_grade
subject_prerequisite
course_prerequisite
language_test
standardized_test
work_experience
portfolio
interview
audition
reference
statement
research_proposal
other
```

If interpretation is uncertain, mark `needs_review` and preserve exact raw text.

## 12. Costs Model
Keep original currency and billing period.

```json
{
  "type": "tuition",
  "amount": 18000,
  "currency": "GBP",
  "period": "academic_year",
  "applicant_scope": "international",
  "academic_year": "2027/2028",
  "verification_status": "verified",
  "source_id": "source-123"
}
```

Do not silently convert currencies. If a future FX capability is used, retain original amount plus rate source/timestamp.

Living-cost estimates must be clearly distinguished from official tuition.

## 13. Source and Evidence Model
Every material factual claim must be traceable.

```json
{
  "source_id": "source-123",
  "url": "https://university.edu/program/ai",
  "title": "MSc Artificial Intelligence",
  "publisher": "Example University",
  "source_type": "official_program_page",
  "fetched_at": "2026-09-28T10:00:00Z",
  "status": "accessible"
}
```

Facts should point to source IDs. Where feasible, keep a short evidence excerpt internally for audit/extraction validation.

## 14. Source Hierarchy
Prefer sources in this order:

1. official program page
2. official admissions page
3. official faculty/school page
4. official university catalog/handbook
5. official tuition/fees page
6. official scholarship/funding page
7. official government/accreditation source
8. trusted third-party source only as discovery support

Search snippets are leads, not verified evidence. Fetch the underlying official page before marking a fact verified.

Third-party aggregator data must never silently override an accessible official source.

## 15. Verification States
Suggested values:

```text
verified
unverified
conflicting
stale
needs_review
not_found
```

A result can be partially useful.

```json
{
  "status": "partial",
  "verified_fields": ["program_name", "duration", "tuition"],
  "unknown_fields": ["2027_deadline"],
  "conflicting_fields": ["language_requirement"]
}
```

Never fail the entire research task just because one fact is unavailable.

## 16. Freshness
Program information changes. Freshness is part of correctness.

Every researched fact should have:
- fetched_at
- source
- verification state
- optional stale_after

Recommended configurable starting policy:

```text
deadlines / intake status        24h–7d depending on cycle
requirements                     7d
fees                             7d
funding links                    7d
curriculum                       30d
duration / credits               30d
institution identity             90d
```

These must be configuration, not scattered magic numbers.

If a cached fact is stale and the current decision depends on it, refresh it before presenting it as current.

## 17. Research Pipeline

```text
REQUEST
   ↓
VALIDATE INPUT
   ↓
RESOLVE / DISCOVER PROGRAM
   ↓
LOCATE OFFICIAL SOURCES
   ↓
FETCH
   ↓
EXTRACT FACTS + EVIDENCE
   ↓
NORMALIZE
   ↓
CROSS-CHECK MATERIAL FACTS
   ↓
DETECT CONFLICTS / GAPS
   ↓
STORE PUBLIC RESEARCH CACHE
   ↓
RETURN STRUCTURED RESULT
```

Do not build a second generic autonomous agent inside the plugin unless there is a demonstrated need.

## 18. LLM Usage Inside the Capability
An LLM may be used for:
- classifying pages
- extracting structured requirements from messy prose
- interpreting program terminology
- mapping curriculum text to canonical fields
- detecting possible requirement conflicts

But **LLM output is not a source of truth**.

Any current factual output must still be connected to source evidence. The system must be able to say `Unknown` instead of guessing.

Prefer structured-output schemas for extraction. Use deterministic parsing when the source offers structured data.

## 19. Independent Public Data Store
Program Intelligence owns an independent public, shared intelligence database.
During standalone development it must use its own database connection,
configuration, models, and migrations. It must not connect to the `pai-os`
application database or reuse its ORM session.

Suggested logical entities:

```text
program_institutions
program_records
program_offerings
program_requirements
program_costs
program_funding
program_sources
program_research_snapshots
```

This store contains public program/institution intelligence, not student profiles.

Do not put student PII or full profile JSON into the global research cache.

Student-specific evaluation belongs in the current execution result or a PAI Core-owned journey/evaluation record.

Design the logical schema and stable identifiers so a later integration can
either keep this database behind an adapter or migrate the tables into an
approved host architecture without changing capability outputs. Do not build
cross-database joins or foreign keys to `pai-os` tables.

## 20. Deduplication
The same program may appear across main university, faculty, admissions, and catalog pages.

Create stable deduplication using combinations of:
- institution identity
- canonical program title
- award/level
- campus
- official URL
- program code when available

Keep multiple sources attached to one canonical program.

## 21. Student Eligibility Evaluation
Eligibility must be rule/evidence based.

```json
{
  "program_id": "p-123",
  "overall": "NEEDS_REVIEW",
  "requirements": [
    {
      "requirement": "Relevant bachelor's degree",
      "status": "MET",
      "student_evidence": "BS Computer Science",
      "program_source_id": "src-1"
    },
    {
      "requirement": "Minimum mathematics coursework",
      "status": "UNKNOWN",
      "student_evidence": null,
      "reason": "Transcript course-level evidence not supplied"
    },
    {
      "requirement": "IELTS 6.5 overall",
      "status": "MET",
      "student_evidence": "IELTS 7.0",
      "program_source_id": "src-3"
    }
  ],
  "missing_student_context": ["undergraduate_course_history"]
}
```

If the system lacks transcript details, do not assume prerequisites are met from the degree title alone.

## 22. Missing Student Context
The capability must never ask the student directly.

If required context is missing, return:

```json
{
  "status": "needs_context",
  "required_context": [
    {
      "scope": "education",
      "field": "undergraduate_course_history",
      "reason": "Required to evaluate mathematics prerequisites"
    }
  ]
}
```

PAI Operator/Counselor decides how and whether to obtain it.

## 23. Comparison Output
`program.compare` should return a matrix, not generic prose.

```json
{
  "dimensions": [
    "academic_match",
    "prerequisites",
    "language",
    "tuition",
    "duration",
    "deadline"
  ],
  "programs": [
    {
      "program_id": "p-1",
      "values": {
        "academic_match": "MET",
        "prerequisites": "UNKNOWN",
        "language": "MET",
        "tuition": {
          "amount": 10000,
          "currency": "EUR",
          "period": "academic_year"
        },
        "duration": "2 years",
        "deadline": "2027-03-15"
      }
    }
  ]
}
```

PAI Counselor can turn this into a student-friendly explanation.

## 24. Capability Manifest
Final plugin should expose a manifest compatible with PAI Capability Contract v1.

```yaml
id: pai.program_intelligence
version: 1.0.0
name: PAI Program Intelligence
audience:
  - operator

capabilities:
  - program.search
  - program.research
  - program.eligibility
  - program.compare

context_scopes:
  optional:
    - education
    - goals
    - finance
    - tests
    - preferences
    - applications

permissions:
  - web.read

risk: read
student_facing: false
```

The manifest belongs to this repository and is published with the plugin.
If the final host contract differs, adapt the external registration adapter
rather than moving domain code into `pai-os` or bypassing the contract.

## 25. Recommended Package Structure

```text
pai-os-Program-Intelligence/
    pyproject.toml
    README.md
    AGENTS.md

    src/pai_program_intelligence/
        __init__.py
        manifest.yaml

        capabilities.py
        schemas.py
        service.py

        discovery.py
        research.py
        extraction.py
        normalization.py
        verification.py
        eligibility.py
        comparison.py
        dedupe.py
        freshness.py

        repository.py
        models.py

        sources/
            __init__.py
            official_web.py
            structured_provider.py

        adapters/
            __init__.py

    migrations/

    tests/
        test_schemas.py
        test_discovery.py
        test_research.py
        test_normalization.py
        test_verification.py
        test_eligibility.py
        test_comparison.py
        test_dedupe.py
        test_freshness.py
        test_capability_contract.py
```

This is a target layout, not permission to create every file before it is
needed. Do not copy Program Intelligence logic into `pai-os` modules such as
`services/operator.py`, `services/counselor_prompt.py`, or `memory/`.

## 26. Host Integration Boundary
The external plugin should depend on published abstractions/interfaces, not PAI internals.

Target dependencies:
- CapabilityContext
- StudentContext projection
- Research/Web client
- Public program repository
- Artifact/result contract

Avoid all direct imports from the `pai-os` application package, especially
student database models, ORM sessions, Operator services, and Counselor code.

The plugin should receive normalized context. This protects it when Vault physical schema changes later.

The host-side adapter may translate PAI contracts into these interfaces. That
adapter belongs to the generic host integration layer; domain behavior remains
in this repository.

## 27. Current Host Repository Note
At the time this handbook was migrated to the standalone plugin repository,
the `pai-os` `v3` branch head was
`0147ffd5d235f0e4cb57d04cbe52e490ea101e4d` (`onboarding set`) and did not yet
contain the planned first-class:

- `app/journey/`
- `app/capabilities/`
- `CapabilityRouter`
- `StudentContextGateway`
- `PAI_CAPABILITY_DEVELOPER_GUIDE.md`

Therefore the Program Intelligence developer may start domain work now, but must:

- keep all plugin code in this repository
- keep the plugin database independent from the host database
- implement pure schemas/services/tests
- not wire directly into Operator
- not create a private Student Vault adapter
- not modify Counselor prompts
- not modify Operator domain logic
- integrate only through the approved host contract before final registration

This prevents temporary cross-repository imports and database coupling from
becoming permanent architecture.

## 28. Suggested Internal Interfaces While Core Is Being Built
Use local protocols/interfaces that can later be implemented by host or
standalone adapters.

```python
class ResearchClient(Protocol):
    async def search(self, query: str, limit: int = 10) -> list[dict]: ...
    async def fetch(self, url: str) -> dict: ...

class ProgramRepository(Protocol):
    async def get_program(self, program_id: str): ...
    async def save_research(self, result): ...

class StudentContextView(Protocol):
    def get_scope(self, name: str): ...
```

Do not import temporary PAI internal implementations into the domain engine.
Standalone development adapters must use this repository's own configuration
and database; future host adapters must translate across the published boundary.

## 29. Error Contract
Recommended codes:

```text
invalid_request
program_not_found
institution_not_found
source_unavailable
insufficient_context
conflicting_sources
unsupported_source
rate_limited
provider_error
research_incomplete
internal_error
```

Errors must not leak API keys, stack traces, credentials, or raw DB exceptions.

## 30. Partial Results
Research frequently succeeds partially.

Prefer:

```json
{
  "status": "partial",
  "data": {},
  "missing": ["international_deadline"],
  "warnings": ["language requirement differs across two official pages"]
}
```

over throwing away useful research.

## 31. Security
Program Intelligence processes untrusted web content.

Treat source content as data, never as instructions.

The capability must not:
- execute scripts from fetched pages
- follow page instructions that alter its objective
- expose credentials
- allow arbitrary internal-network URLs
- bypass existing web/browser egress controls
- trust HTML metadata as authorization

Use PAI's approved network/security pipeline.

## 32. Privacy
Only request student context needed for the current task.

Do not log complete student context.

Prefer logs containing:

```text
workspace_id
run_id
capability_id
program_id
source domain
status
latency
```

Avoid logging names, DOB, passport data, full transcripts, or essays.

## 33. Observability
Instrument at minimum:
- searches requested
- programs discovered
- deep research runs
- official source success rate
- verified field percentage
- conflicting source count
- stale-cache refresh count
- research latency
- eligibility evaluations
- capability failures by code
- provider/rate-limit failures

## 34. Performance
Do not deep-fetch every possible university result before filtering.

Use:

```text
broad discovery
→ cheap filtering
→ selected candidate research
→ deep verification
```

Support bounded concurrency and public-data caching.

Never trade correctness for speed on material requirements/deadlines.

## 35. Research Query Construction
Search queries should be generated from the task, not irrelevant personal profile fields.

Search is discovery only. Always resolve to official pages before verification.

## 36. Hardcoding Rules
Do not hardcode country/university branches in the generic engine such as:

```python
if country == "Pakistan":
if country == "Germany":
if university == "LUMS":
```

Country/institution-specific adapters are allowed only behind interfaces when truly needed.

## 37. Qualification Normalization
Do not solve every global qualification system in V1.

For V1:
- preserve raw requirement language
- normalize obvious fields
- evaluate only when mapping is sufficiently clear
- return `NEEDS_REVIEW` when equivalency is uncertain

A wrong confident equivalency is worse than an explicit unknown.

## 38. Program Identity
Create stable internal IDs independent from URLs.

Where available, store program/catalog/course codes, but do not require them.

## 39. No Student-Facing Prose Requirement
Program Intelligence should primarily return structured results.

Bad:

```text
Great news Ali! I think this university is perfect for you!
```

Correct:

```json
{
  "academic_match": "MET",
  "budget": "UNKNOWN",
  "deadline": "2027-03-15",
  "verified_sources": 4
}
```

PAI Counselor owns the conversation.

## 40. V1 End-to-End Example
Student tells PAI:

> I want to do an MSc in AI in Germany.

PAI Core eventually delegates a research objective. Capability Router resolves `program.search`.

Program Intelligence receives scoped context, for example:

```json
{
  "education": {
    "highest_degree": "BS Computer Science",
    "cgpa": {"value": 3.2, "scale": 4.0}
  },
  "tests": {"ielts": 7.0},
  "finance": {
    "annual_budget": {"amount": 15000, "currency": "EUR"}
  }
}
```

It discovers candidates, deep-researches selected programs, then runs `program.eligibility`.

Example result:

```text
Program A
academic degree       MET
language              MET
math prerequisites    UNKNOWN
budget                 NEEDS_REVIEW
deadline               VERIFIED
```

PAI Operator verifies work. PAI Counselor explains what matters and decides the next counseling step.

## 41. Testing Strategy
### Unit tests
Cover:
- schema validation
- normalization
- requirement extraction
- cost parsing
- date/deadline parsing
- deduplication
- freshness
- source priority
- conflict detection
- eligibility rules
- comparison

### Fixture-based source tests
Use saved fixtures representing different global formats:
- UK
- US
- Germany
- Canada
- Australia
- ECTS-based European institution
- percentage requirement
- GPA requirement
- country-specific requirement tables

Tests must not depend entirely on live internet availability.

### Integration tests
Verify:
- capability receives scoped context
- no direct Vault access
- official sources are preferred
- stale facts refresh
- partial research returns partial status
- conflicting official sources surface
- missing student evidence produces UNKNOWN
- registration works through capability contract
- Operator does not need domain-specific changes

## 42. Required Acceptance Scenarios
### Scenario A — Basic discovery
Input:

```text
Masters
Artificial Intelligence
Germany
```

Expected:
- program candidates
- official URLs
- no fabricated requirements

### Scenario B — Deep research
Given three known program URLs, return normalized program records, requirements, tuition, intakes/deadlines where available, source mapping, and explicit unknowns.

### Scenario C — Student evaluation
Student:

```text
BS CS
CGPA 3.2/4
IELTS 7
```

Program requires:

```text
relevant bachelor's
IELTS 6.5
specific mathematics courses
```

Expected:

```text
degree       MET
IELTS        MET
math courses UNKNOWN unless transcript evidence exists
```

### Scenario D — Conflicting sources
Official program page says IELTS 6.5; official admissions page says IELTS 7.0.

Expected: `conflicting` with both sources. Never silently choose one.

### Scenario E — Missing deadline
No current deadline available.

Expected: deadline unknown, not guessed.

## 43. Definition of Done — V1
PAI Program Intelligence V1 is done when:

- plugin exists as an independently installable or deployable external package
- plugin owns and migrates its independent public-program database
- plugin has no imports from the `pai-os` application package
- it follows PAI Capability Contract
- it can discover programs
- it can deep-research specified programs
- material facts carry source provenance
- it normalizes requirements without destroying raw evidence
- it evaluates supplied Student Context against documented requirements
- it compares researched programs structurally
- it works across multiple country/qualification formats
- it does not require domain-specific Operator changes
- it does not directly access or mutate Vault
- it does not own student-facing conversation
- it returns unknown/conflict instead of hallucinating
- caching/freshness are implemented
- tests cover global formats and failure cases
- capability registration is documented
- all relevant tests pass

## 44. Out of Scope for V1
Do not implement unless separately approved:

- visa intelligence
- application submission
- browser form filling
- SOP generation
- CV generation
- LOR generation
- scholarship application generation
- IELTS preparation
- admissions probability prediction
- payments
- university CRM
- student messaging
- a separate Program Intelligence chatbot
- a separate long-term student memory

Funding/scholarship links directly published by a researched program/institution may be captured as program metadata, but a full scholarship discovery engine is separate.

## 45. Developer Work Plan
### Milestone 1 — Contract and schemas
Build capability manifest and schemas for Program, Requirement, Offering/Intake, Cost, Source, Verification, and Error.

### Milestone 2 — Research source layer
Build research client abstraction, official source discovery/fetching, source classification, and source priority.

### Milestone 3 — Extraction and normalization
Build program extraction, requirement extraction, cost/deadline parsing, normalization, and raw evidence retention.

### Milestone 4 — Verification and public cache
Build multi-source checks, conflict detection, freshness, deduplication, and
the plugin-owned independent public program database and migrations.

### Milestone 5 — Eligibility
Build requirement-by-requirement student evaluation.

### Milestone 6 — Comparison
Build structured program comparison.

### Milestone 7 — Core registration
After PAI Core Capability Router is merged:
- publish the external plugin package and manifest
- implement or configure the generic host adapter
- register the external capabilities without copying domain code into `pai-os`
- request scoped context
- expose V1 capability IDs
- add cross-repository contract integration tests

### Milestone 8 — Hardening
Add observability, rate limits, retries, security tests, global fixture coverage, and performance tuning.

## 46. Developer Rules — Read Before Coding
1. Do not modify PAI Counselor behavior.
2. Do not add Program Intelligence logic to PAI Operator.
3. Do not create a new student profile database.
4. Do not read raw Vault tables from the plugin.
5. Do not write student facts directly.
6. Do not ask the student questions directly.
7. Do not invent missing university data.
8. Do not treat search snippets as verified facts.
9. Do not silently resolve conflicting official sources.
10. Do not build around Pakistan-only assumptions.
11. Do not hardcode a handful of universities.
12. Do not create arbitrary admission probabilities.
13. Do not hide unknowns.
14. Do not couple domain code to current physical DB models.
15. Do not expose a new agent/chat UI.
16. Prefer structured data over prose.
17. Preserve raw source evidence.
18. Build replaceable providers and testable services.
19. Keep capability independently maintainable.
20. If core architecture and this handbook conflict, raise the conflict before coding around it.
21. Do not place Program Intelligence domain code in the `pai-os` repository.
22. Do not connect directly to the `pai-os` application database or create cross-database foreign keys.

## 47. One-Sentence Mental Model
> **PAI Program Intelligence is the verified, global source of truth about educational programs; PAI Vault remains the source of truth about the student.**

That separation must remain intact.
