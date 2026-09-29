"""Field-specific cache expiry is configurable and timezone-aware."""

import unittest
from datetime import datetime, timezone

from pai_program_intelligence.freshness import is_stale, stale_after
from pai_program_intelligence.schemas import Source


class FreshnessTests(unittest.TestCase):
    def test_deadlines_expire_before_program_identity(self):
        source = Source("one", "https://example.edu/program", "Program", "Example University", "official_program_page", "2026-09-20T12:00:00Z")
        now = datetime(2026, 9, 29, tzinfo=timezone.utc)
        self.assertTrue(is_stale(source, "offerings.application_window.closes", now=now))
        self.assertFalse(is_stale(source, "program.name", now=now))
        self.assertEqual(stale_after(source, "requirements").day, 27)
        self.assertFalse(is_stale(source, "requirements", now=now, max_age_days={"requirements": 10}))

    def test_naive_now_is_rejected(self):
        source = Source("one", "https://example.edu/program", "Program", "Example University", "official_program_page", "2026-09-20T12:00:00Z")
        with self.assertRaises(ValueError):
            is_stale(source, "requirements", now=datetime(2026, 9, 29))


if __name__ == "__main__":
    unittest.main()
