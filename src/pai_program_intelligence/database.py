"""Independent PostgreSQL connection and transactional schema migrations."""

from __future__ import annotations

import os
from importlib.resources import files


def connect_database(dsn: str | None = None):
    """Use only this plugin's DB URL; never fall back to the PAI host database."""
    url = dsn or os.environ.get("PROGRAM_INTELLIGENCE_DATABASE_URL")
    if not url:
        raise ValueError("PROGRAM_INTELLIGENCE_DATABASE_URL is required")
    import psycopg

    return psycopg.connect(url)


def apply_migrations(conn) -> tuple[str, ...]:
    """Apply packaged SQL files once, recording versions in this plugin's schema."""
    with conn.transaction():
        conn.execute("create schema if not exists program_intelligence")
        conn.execute(
            "create table if not exists program_intelligence.schema_migrations "
            "(version text primary key, applied_at timestamptz not null default now())"
        )
        applied = {row[0] for row in conn.execute("select version from program_intelligence.schema_migrations")}
        completed: list[str] = []
        migration_dir = files("pai_program_intelligence").joinpath("migrations")
        for migration in sorted(migration_dir.iterdir(), key=lambda path: path.name):
            if migration.suffix != ".sql" or migration.name in applied:
                continue
            conn.execute(migration.read_text(encoding="utf-8"), prepare=False)
            conn.execute("insert into program_intelligence.schema_migrations (version) values (%s)", (migration.name,))
            completed.append(migration.name)
        return tuple(completed)
