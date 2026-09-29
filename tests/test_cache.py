"""Public cache keeps raw evidence and refreshes source-scoped current facts."""

import unittest
from contextlib import nullcontext
from datetime import datetime, timezone

from pai_program_intelligence.cache import load_latest_sources, save_public_research
from pai_program_intelligence.extraction import extract_program
from pai_program_intelligence.schemas import Institution, ProgramDetails, Source, VerificationStatus
from pai_program_intelligence.sources import FetchedSource


class QueryResult:
    def __init__(self, rows=()):
        self.rows = rows

    def fetchone(self):
        return self.rows[0]

    def __iter__(self):
        return iter(self.rows)


class FakeConnection:
    def __init__(self, cached_rows=()):
        self.cached_rows = cached_rows
        self.queries = []

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=None):
        if params is not None:
            assert query.count("%s") == len(params)
        self.queries.append((query, params))
        if query.startswith("select distinct on"):
            return QueryResult(self.cached_rows)
        if "returning snapshot_id" in query:
            return QueryResult([(1,)])
        if "returning verification_id" in query:
            return QueryResult([(2,)])
        return QueryResult()


def research(source_id: str, text: str):
    source = Source(source_id, f"https://example.edu/{source_id}", "MSc Statistics", "Example University", "official_program_page", "2026-09-28T12:00:00Z")
    return extract_program(FetchedSource(source, text))


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.institution = Institution("uni-1", "Example University", "GB", official_url="https://example.edu")
        self.program = ProgramDetails("MSc Statistics", "https://example.edu/program/statistics", award="MSc")
        self.now = datetime(2026, 9, 29, tzinfo=timezone.utc)

    def test_saves_raw_snapshot_claims_and_verification(self):
        conn = FakeConnection()
        pages = [research("one", "# MSc Statistics\n## Entry requirements\n- IELTS 6.5 overall\nTuition: GBP 18,000 per year")]
        identifier, verification = save_public_research(conn, self.institution, self.program, pages, verified_at=self.now)
        self.assertTrue(identifier.startswith("program-"))
        self.assertEqual(verification.status, VerificationStatus.UNVERIFIED)
        queries = "\n".join(query for query, _ in conn.queries)
        for table in ("program_research_snapshots", "program_claims", "program_requirements", "program_costs", "program_verification_runs"):
            self.assertIn("insert into program_intelligence." + table, queries)
        self.assertIn(pages[0].raw_text, [item for _, params in conn.queries if params for item in params if isinstance(item, str)])
        self.assertIn("delete from program_intelligence.program_requirements", queries)

    def test_cached_source_is_reused_when_new_page_arrives(self):
        cached = (
            "one", "https://example.edu/one", "MSc Statistics", "Example University",
            "official_program_page", self.now, "accessible", "Duration: 2 years",
        )
        conn = FakeConnection([cached])
        pages = [research("two", "# MSc Statistics\nDuration: 2 years")]
        loaded = load_latest_sources(conn, "program-test")
        self.assertEqual(loaded[0].raw_text, "Duration: 2 years")
        _, verification = save_public_research(conn, self.institution, self.program, pages, verified_at=self.now)
        field = next(item for item in verification.fields if item.field == "program.duration")
        self.assertEqual(field.status, VerificationStatus.VERIFIED)

    def test_duplicate_source_in_one_batch_is_rejected(self):
        conn = FakeConnection()
        page = research("one", "Duration: 2 years")
        with self.assertRaises(ValueError):
            save_public_research(conn, self.institution, self.program, [page, page], verified_at=self.now)
        self.assertEqual(conn.queries, [])

    def test_older_page_cannot_replace_newer_cached_source(self):
        cached = (
            "one", "https://example.edu/one", "MSc Statistics", "Example University",
            "official_program_page", self.now, "accessible", "Duration: 2 years",
        )
        conn = FakeConnection([cached])
        with self.assertRaisesRegex(ValueError, "older"):
            save_public_research(conn, self.institution, self.program, [research("one", "Duration: 3 years")], verified_at=self.now)
        self.assertFalse(any(query.startswith("insert into") for query, _ in conn.queries))


if __name__ == "__main__":
    unittest.main()
