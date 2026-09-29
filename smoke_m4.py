"""Apply plugin-only PostgreSQL migrations after provisioning its separate DB."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from pai_program_intelligence.database import apply_migrations, connect_database  # noqa: E402


def _local_database_url() -> str | None:
    value = os.environ.get("PROGRAM_INTELLIGENCE_DATABASE_URL")
    if value:
        return value
    env_file = REPO_ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("PROGRAM_INTELLIGENCE_DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"\'') or None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply pending migrations to the separate plugin database")
    args = parser.parse_args()
    if not args.apply:
        parser.error("pass --apply only after confirming this URL points to the plugin's own database")
    url = _local_database_url()
    if not url:
        raise SystemExit("Missing PROGRAM_INTELLIGENCE_DATABASE_URL in the plugin repo .env or process environment")
    with connect_database(url) as conn:
        applied = apply_migrations(conn)
        count = conn.execute(
            "select count(*) from pg_catalog.pg_tables where schemaname=%s",
            ("program_intelligence",),
        ).fetchone()[0]
    print("applied_migrations:", ", ".join(applied) or "none")
    print("plugin_schema_tables:", count)


if __name__ == "__main__":
    main()
