"""Comparison keeps per-program evidence, gaps, and conflicts visible."""

import unittest
from datetime import datetime, timezone

from pai_program_intelligence.comparison import DIMENSIONS, compare_programs
from pai_program_intelligence.eligibility import MatchStatus, evaluate_eligibility
from pai_program_intelligence.schemas import (
    Cost, Duration, FieldEvidence, Institution, ProgramDetails, ProgramRecord,
    Requirement, RequirementType, Source, Verification, VerificationStatus,
)
from pai_program_intelligence.verification import _requirement_key


NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def record(program_id, *, language_score=6.5, verified=True):
    source = Source(f"{program_id}-src", f"https://example.edu/{program_id}", "Program", "Example University",
                    "official_program_page", "2026-09-29T00:00:00Z")
    requirement = Requirement(f"{program_id}-ielts", RequirementType.LANGUAGE_TEST, f"IELTS {language_score} overall",
                              True, VerificationStatus.VERIFIED, source.source_id,
                              normalized={"test": "IELTS", "minimum_overall": language_score})
    status = VerificationStatus.VERIFIED if verified else VerificationStatus.CONFLICTING
    fields = (
        FieldEvidence(_requirement_key(requirement)[0], status, (source.source_id, "other-source") if not verified else (source.source_id,)),
        FieldEvidence("program.duration", VerificationStatus.VERIFIED, (source.source_id,)),
    )
    sources = (source, Source("other-source", "https://example.edu/other", "Other", "Example University",
                              "official_admissions_page", "2026-09-29T00:00:00Z")) if not verified else (source,)
    return ProgramRecord(
        program_id, Institution("uni", "Example University", "GB"),
        ProgramDetails(f"MSc {program_id}", source.url, duration=Duration(2, "years")),
        sources, Verification(status, fields), requirements=(requirement,),
        costs=(Cost("tuition", 10000, "GBP", "year", VerificationStatus.UNVERIFIED, source.source_id),),
    )


class ComparisonTests(unittest.TestCase):
    def test_matrix_preserves_match_and_unverified_cost(self):
        first, second = record("one"), record("two", language_score=7.5)
        context = {"tests": [{"test": "IELTS", "overall": 7}]}
        matches = {item.program_id: evaluate_eligibility(item.program_id, item.requirements, context) for item in (first, second)}
        result = compare_programs((first, second), matches, now=NOW)
        self.assertEqual(result.dimensions, DIMENSIONS)
        self.assertEqual(result.programs[0].values["language"].value[0]["match"], MatchStatus.MET)
        self.assertEqual(result.programs[1].values["language"].value[0]["match"], MatchStatus.NOT_MET)
        self.assertEqual(result.programs[0].values["tuition"].verification_status, VerificationStatus.NEEDS_REVIEW)
        self.assertEqual(result.programs[0].values["deadline"].verification_status, VerificationStatus.NOT_FOUND)
        self.assertEqual(result.programs[0].values["duration"].source_ids, ("one-src",))

    def test_conflict_and_stale_cannot_show_met(self):
        first, second = record("one", verified=False), record("two")
        matches = {item.program_id: evaluate_eligibility(item.program_id, item.requirements, {"tests": [{"test": "IELTS", "overall": 8}]}) for item in (first, second)}
        result = compare_programs((first, second), matches, now=NOW)
        self.assertEqual(result.programs[0].values["language"].verification_status, VerificationStatus.CONFLICTING)
        self.assertEqual(result.programs[0].values["language"].value[0]["match"], MatchStatus.NEEDS_REVIEW)
        future = datetime(2026, 10, 8, tzinfo=timezone.utc)
        stale = compare_programs((first, second), matches, now=future)
        self.assertEqual(stale.programs[1].values["language"].verification_status, VerificationStatus.STALE)
        self.assertEqual(stale.programs[1].values["language"].value[0]["match"], MatchStatus.NEEDS_REVIEW)

    def test_reject_duplicate_or_mismatched_programs(self):
        first, second = record("one"), record("two")
        with self.assertRaises(ValueError):
            compare_programs((first, first))
        with self.assertRaises(ValueError):
            compare_programs((first, second), {"other": evaluate_eligibility("other", (), {})})


if __name__ == "__main__":
    unittest.main()
