-- Public program intelligence only. No student profiles or PAI Vault references.
create table program_intelligence.program_institutions (
    institution_id text primary key,
    name text not null,
    country text not null check (country ~ '^[A-Z]{2}$'),
    city text,
    official_url text
);

create table program_intelligence.program_records (
    program_id text primary key,
    institution_id text not null references program_intelligence.program_institutions(institution_id),
    name text not null,
    official_url text not null,
    award text,
    level text,
    fields text[] not null default '{}',
    mode text,
    campus text,
    duration_value numeric,
    duration_unit text,
    credits_value numeric,
    credits_system text,
    curriculum jsonb not null default '{}',
    updated_at timestamptz not null default now(),
    check ((duration_value is null) = (duration_unit is null)),
    check ((credits_value is null) = (credits_system is null))
);
create index program_records_institution_idx on program_intelligence.program_records(institution_id);

create table program_intelligence.program_sources (
    source_id text primary key,
    url text not null unique,
    title text not null,
    publisher text not null,
    source_type text not null,
    fetched_at timestamptz not null,
    status text not null
);

create table program_intelligence.program_record_sources (
    program_id text not null references program_intelligence.program_records(program_id) on delete cascade,
    source_id text not null references program_intelligence.program_sources(source_id),
    primary key (program_id, source_id)
);
create index program_record_sources_source_idx on program_intelligence.program_record_sources(source_id);

create table program_intelligence.program_offerings (
    program_id text not null references program_intelligence.program_records(program_id) on delete cascade,
    intake_id text not null,
    term text,
    academic_year text,
    start_date date,
    application_opens date,
    application_closes date,
    deadline_type text,
    applicant_scope text,
    status text,
    source_id text,
    primary key (program_id, intake_id),
    foreign key (program_id, source_id)
        references program_intelligence.program_record_sources(program_id, source_id),
    check (application_opens is null or application_closes is null or application_opens <= application_closes)
);
create index program_offerings_source_idx on program_intelligence.program_offerings(program_id, source_id);

create table program_intelligence.program_requirements (
    program_id text not null references program_intelligence.program_records(program_id) on delete cascade,
    requirement_id text not null,
    type text not null,
    raw_text text not null,
    required boolean not null,
    verification_field text not null,
    verification_status text not null check (verification_status in ('verified', 'unverified', 'conflicting', 'stale', 'needs_review', 'not_found')),
    source_id text not null,
    applies_to jsonb not null default '{}',
    normalized jsonb not null default '{}',
    primary key (program_id, requirement_id),
    foreign key (program_id, source_id)
        references program_intelligence.program_record_sources(program_id, source_id)
);
create index program_requirements_source_idx on program_intelligence.program_requirements(program_id, source_id);

create table program_intelligence.program_costs (
    cost_key text primary key,
    program_id text not null references program_intelligence.program_records(program_id) on delete cascade,
    source_id text not null,
    type text not null,
    amount numeric not null check (amount >= 0),
    currency text not null check (currency ~ '^[A-Z]{3}$'),
    period text not null,
    applicant_scope text,
    academic_year text,
    verification_field text not null,
    verification_status text not null check (verification_status in ('verified', 'unverified', 'conflicting', 'stale', 'needs_review', 'not_found')),
    foreign key (program_id, source_id)
        references program_intelligence.program_record_sources(program_id, source_id)
);
create index program_costs_program_idx on program_intelligence.program_costs(program_id);
create index program_costs_source_idx on program_intelligence.program_costs(program_id, source_id);

create table program_intelligence.program_funding (
    funding_key text primary key,
    program_id text not null references program_intelligence.program_records(program_id) on delete cascade,
    source_id text not null,
    title text not null,
    url text not null,
    foreign key (program_id, source_id)
        references program_intelligence.program_record_sources(program_id, source_id)
);
create index program_funding_program_idx on program_intelligence.program_funding(program_id);
create index program_funding_source_idx on program_intelligence.program_funding(program_id, source_id);

create table program_intelligence.program_research_snapshots (
    snapshot_id bigint generated always as identity primary key,
    program_id text not null,
    source_id text not null,
    fetched_at timestamptz not null,
    raw_text text not null,
    content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    unique (program_id, source_id, fetched_at, content_sha256),
    foreign key (program_id, source_id)
        references program_intelligence.program_record_sources(program_id, source_id)
);
create index program_snapshots_program_time_idx on program_intelligence.program_research_snapshots(program_id, fetched_at desc);
create index program_snapshots_source_idx on program_intelligence.program_research_snapshots(program_id, source_id);

create table program_intelligence.program_claims (
    claim_id bigint generated always as identity primary key,
    snapshot_id bigint not null references program_intelligence.program_research_snapshots(snapshot_id) on delete cascade,
    claim_key text not null,
    field text not null,
    value_json jsonb,
    raw_text text not null,
    line_number integer not null check (line_number > 0),
    status text not null check (status in ('verified', 'unverified', 'conflicting', 'stale', 'needs_review', 'not_found')),
    unique (snapshot_id, claim_key)
);
create index program_claims_snapshot_idx on program_intelligence.program_claims(snapshot_id);

create table program_intelligence.program_verification_runs (
    verification_id bigint generated always as identity primary key,
    program_id text not null references program_intelligence.program_records(program_id) on delete cascade,
    verified_at timestamptz not null,
    overall_status text not null check (overall_status in ('verified', 'unverified', 'conflicting', 'stale', 'needs_review', 'not_found'))
);
create index program_verification_program_time_idx on program_intelligence.program_verification_runs(program_id, verified_at desc);

create table program_intelligence.program_verified_fields (
    verification_id bigint not null references program_intelligence.program_verification_runs(verification_id) on delete cascade,
    field text not null,
    status text not null check (status in ('verified', 'unverified', 'conflicting', 'stale', 'needs_review', 'not_found')),
    source_ids text[] not null default '{}',
    primary key (verification_id, field)
);
