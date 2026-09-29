"""Multi-source checks must not invent consensus or hide disagreements."""

import unittest
from datetime import datetime, timezone

from pai_program_intelligence.extraction import extract_program
from pai_program_intelligence.schemas import Source, VerificationStatus
from pai_program_intelligence.sources import FetchedSource
from pai_program_intelligence.verification import verify_extractions


NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def extracted(source_id: str, text: str, *, fetched_at: str = "2026-09-28T12:00:00Z"):
    source = Source(source_id, f"https://example.edu/{source_id}", source_id, "Example University", "official_program_page", fetched_at)
    return extract_program(FetchedSource(source, text))


def field_status(results, field: str):
    verification = verify_extractions(results, now=NOW)
    return next(item for item in verification.fields if item.field == field)


class VerificationTests(unittest.TestCase):
    def test_two_distinct_current_sources_verify_same_fact(self):
        pages = [extracted("one", "# MSc Statistics\nDuration: 2 years"), extracted("two", "Duration: 2 years")]
        field = field_status(pages, "program.duration")
        self.assertEqual(field.status, VerificationStatus.VERIFIED)
        self.assertEqual(field.source_ids, ("one", "two"))

    def test_repeated_snapshot_of_one_source_is_not_corroboration(self):
        page = extracted("one", "Duration: 2 years")
        self.assertEqual(field_status([page, page], "program.duration").status, VerificationStatus.UNVERIFIED)

    def test_identical_mirrored_page_is_not_independent_corroboration(self):
        pages = [extracted("one", "Duration: 2 years"), extracted("two", "Duration: 2 years")]
        self.assertEqual(field_status(pages, "program.duration").status, VerificationStatus.UNVERIFIED)

    def test_conflicting_ielts_scores_include_both_sources(self):
        pages = [
            extracted("program", "## Entry requirements\n- IELTS 6.5 overall"),
            extracted("admissions", "## Entry requirements\n- IELTS 7.0 overall"),
        ]
        field = field_status(pages, "requirements.language_test:IELTS:all")
        self.assertEqual(field.status, VerificationStatus.CONFLICTING)
        self.assertEqual(field.source_ids, ("admissions", "program"))

    def test_stale_pages_cannot_verify_current_fact(self):
        pages = [
            extracted("one", "## Entry requirements\n- IELTS 6.5 overall", fetched_at="2026-09-01T12:00:00Z"),
            extracted("two", "## Entry requirements\n- IELTS 6.5 overall", fetched_at="2026-09-01T12:00:00Z"),
        ]
        self.assertEqual(field_status(pages, "requirements.language_test:IELTS:all").status, VerificationStatus.STALE)

    def test_stale_second_page_is_not_counted_as_corroboration(self):
        pages = [
            extracted("current", "Duration: 2 years"),
            extracted("old", "Duration: 2 years", fetched_at="2026-07-01T12:00:00Z"),
        ]
        field = field_status(pages, "program.duration")
        self.assertEqual(field.status, VerificationStatus.UNVERIFIED)
        self.assertEqual(field.source_ids, ("current",))

    def test_unknown_deadline_stays_not_found(self):
        field = field_status([extracted("one", "# MSc Statistics")], "offerings.application_window.closes")
        self.assertEqual(field.status, VerificationStatus.NOT_FOUND)

    def test_ambiguous_fee_stays_review_needed(self):
        page = extracted("one", "Tuition: GBP 10,000 or GBP 20,000 per year")
        self.assertEqual(field_status([page], "costs.tuition").status, VerificationStatus.NEEDS_REVIEW)

    def test_different_applicant_scopes_are_not_conflicts(self):
        pages = [
            extracted("one", "Tuition: GBP 10,000 per year for domestic applicants"),
            extracted("two", "Tuition: GBP 20,000 per year for international applicants"),
        ]
        verification = verify_extractions(pages, now=NOW)
        self.assertFalse(any(field.status == VerificationStatus.CONFLICTING for field in verification.fields))


if __name__ == "__main__":
    unittest.main()
