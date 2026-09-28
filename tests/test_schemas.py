"""Milestone 1 contract tests; no live network or host dependency."""

import json
import unittest
from dataclasses import asdict
from importlib.resources import files

from pai_program_intelligence.schemas import (
    ApplicationWindow,
    ApplicantScope,
    CapabilityError,
    Cost,
    Credits,
    Duration,
    ErrorCode,
    FieldEvidence,
    Institution,
    Offering,
    ProgramDetails,
    ProgramRecord,
    Requirement,
    RequirementType,
    Source,
    Verification,
    VerificationStatus,
)


class SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Source(
            source_id="source-1",
            url="https://example.edu/programs/ai",
            title="MSc Artificial Intelligence",
            publisher="Example University",
            source_type="official_program_page",
            fetched_at="2026-09-28T10:00:00Z",
        )

    def _record(self, **changes: object) -> ProgramRecord:
        values = {
            "program_id": "program-1",
            "institution": Institution("institution-1", "Example University", "DE"),
            "program": ProgramDetails("MSc Artificial Intelligence", self.source.url),
            "sources": (self.source,),
            "verification": Verification(
                VerificationStatus.UNVERIFIED,
                (FieldEvidence("program.name", VerificationStatus.VERIFIED, ("source-1",)),),
            ),
        }
        values.update(changes)
        return ProgramRecord(**values)

    def test_record_keeps_raw_requirement_and_source_link(self) -> None:
        raw = "Applicants must hold a relevant bachelor's degree."
        requirement = Requirement(
            requirement_id="requirement-1",
            type=RequirementType.ACADEMIC_DEGREE,
            raw_text=raw,
            required=True,
            verification_status=VerificationStatus.VERIFIED,
            source_id="source-1",
            applies_to=ApplicantScope("international", ("DE",)),
            normalized={"level": "bachelors", "field": ["computer_science"]},
        )
        payload = json.loads(json.dumps(asdict(self._record(requirements=(requirement,)))))
        self.assertEqual(payload["requirements"][0]["raw_text"], raw)
        self.assertEqual(payload["requirements"][0]["source_id"], "source-1")
        self.assertEqual(payload["verification"]["fields"][0]["status"], "verified")

    def test_unknown_field_needs_no_invented_source(self) -> None:
        record = self._record(
            verification=Verification(
                VerificationStatus.UNVERIFIED,
                (FieldEvidence("offerings.deadline", VerificationStatus.NOT_FOUND),),
            )
        )
        self.assertEqual(record.verification.fields[0].source_ids, ())
        self.assertEqual(record.offerings, ())

    def test_conflict_requires_two_sources(self) -> None:
        with self.assertRaises(ValueError):
            FieldEvidence("requirements.language_test", VerificationStatus.CONFLICTING, ("source-1",))

    def test_invalid_contract_values_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Verification("made_up")
        with self.assertRaises(ValueError):
            Requirement("req-1", "made_up", "Raw requirement", True, VerificationStatus.VERIFIED, "source-1")
        with self.assertRaises(ValueError):
            CapabilityError("made_up", "Failure")
        with self.assertRaises(ValueError):
            Duration(-2, "years")

    def test_record_rejects_unattached_source(self) -> None:
        cost = Cost("tuition", 18000, "GBP", "academic_year", VerificationStatus.VERIFIED, "missing")
        with self.assertRaisesRegex(ValueError, "facts must reference sources"):
            self._record(costs=(cost,))

    def test_offering_allows_unknown_deadline_and_checks_window(self) -> None:
        self.assertIsNone(Offering("2027-fall").application_window)
        with self.assertRaisesRegex(ValueError, "closes before"):
            ApplicationWindow("2027-04-01", "2027-03-01")

    def test_nested_output_matches_handbook_shape(self) -> None:
        record = self._record(
            program=ProgramDetails(
                "MSc Artificial Intelligence",
                self.source.url,
                duration=Duration(2, "years"),
                credits=Credits(120, "ECTS"),
            ),
            offerings=(Offering("2027-fall", application_window=ApplicationWindow(closes="2027-03-15")),),
        )
        payload = json.loads(json.dumps(asdict(record)))
        self.assertEqual(payload["program"]["duration"], {"value": 2, "unit": "years"})
        self.assertEqual(payload["program"]["credits"], {"value": 120, "system": "ECTS"})
        self.assertEqual(payload["offerings"][0]["application_window"], {"opens": None, "closes": "2027-03-15"})

    def test_cost_preserves_original_currency_and_period(self) -> None:
        cost = Cost("tuition", 18000, "GBP", "academic_year", VerificationStatus.VERIFIED, "source-1")
        self.assertEqual((cost.amount, cost.currency, cost.period), (18000, "GBP", "academic_year"))
        with self.assertRaises(ValueError):
            Cost("tuition", float("nan"), "GBP", "academic_year", VerificationStatus.VERIFIED, "source-1")

    def test_source_requires_timestamp_with_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            Source("source-1", self.source.url, "Title", "Publisher", "official_program_page", "2026-09-28T10:00:00")

    def test_error_code_is_structured(self) -> None:
        error = CapabilityError(ErrorCode.SOURCE_UNAVAILABLE, "Official page could not be fetched")
        self.assertEqual(json.loads(json.dumps(asdict(error)))["code"], "source_unavailable")

    def test_manifest_lists_only_v1_capabilities(self) -> None:
        manifest = files("pai_program_intelligence").joinpath("manifest.yaml").read_text(encoding="utf-8")
        capability_lines = [line.strip() for line in manifest.splitlines() if line.startswith("  - program.")]
        self.assertEqual(
            capability_lines,
            [
                "- program.search",
                "- program.research",
                "- program.eligibility",
                "- program.compare",
            ],
        )


if __name__ == "__main__":
    unittest.main()
