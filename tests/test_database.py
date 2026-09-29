"""Migration and connection setup do not depend on the PAI host database."""

import os
import unittest
from contextlib import nullcontext
from unittest.mock import patch

from pai_program_intelligence.database import apply_migrations, connect_database


class FakeConnection:
    def __init__(self):
        self.applied = set()
        self.queries = []

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=None, **kwargs):
        self.queries.append((query, params, kwargs))
        if query.startswith("select version"):
            return [(version,) for version in self.applied]
        if query.startswith("insert into program_intelligence.schema_migrations"):
            self.applied.add(params[0])
        return []


class DatabaseTests(unittest.TestCase):
    def test_migration_is_packaged_and_applied_once(self):
        conn = FakeConnection()
        self.assertEqual(apply_migrations(conn), ("0001_public_cache.sql",))
        self.assertEqual(apply_migrations(conn), ())
        migration_sql = next(query for query, _, _ in conn.queries if "create table program_intelligence.program_research_snapshots" in query)
        for table in ("program_institutions", "program_records", "program_offerings", "program_requirements", "program_costs", "program_funding", "program_sources", "program_research_snapshots"):
            self.assertIn("create table program_intelligence." + table, migration_sql)
        self.assertFalse(any("student_profile" in query.lower() for query, _, _ in conn.queries))

    def test_connection_requires_plugin_specific_configuration(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://host-only"}, clear=True):
            with self.assertRaisesRegex(ValueError, "PROGRAM_INTELLIGENCE_DATABASE_URL"):
                connect_database()


if __name__ == "__main__":
    unittest.main()
