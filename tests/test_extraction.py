"""Saved text fixtures for conservative Program Intelligence extraction."""

import unittest

from pai_program_intelligence.extraction import extract_program
from pai_program_intelligence.schemas import Source, VerificationStatus
from pai_program_intelligence.sources import FetchedSource


def fixture(text: str) -> FetchedSource:
    source = Source(
        source_id="source-fixture",
        url="https://example.edu/programs/ai",
        title="MSc Artificial Intelligence",
        publisher="Example University",
        source_type="official_program_page",
        fetched_at="2026-09-28T10:00:00Z",
    )
    return FetchedSource(source, text)


class ExtractionTests(unittest.TestCase):
    def test_explicit_program_page_preserves_evidence(self):
        raw = """# MSc Artificial Intelligence
Duration: 2 years
Credits: 120 ECTS
## Entry requirements
- Bachelor's degree in computer science
- IELTS 6.5 overall
## Tuition
- GBP 18,000 per academic year for international students
## Application deadline
15 March 2027
"""
        result = extract_program(fixture(raw))
        by_field = {}
        for claim in result.claims:
            by_field.setdefault(claim.field, []).append(claim)
        self.assertEqual(result.raw_text, raw)
        self.assertEqual(by_field["program.name"][0].value, "MSc Artificial Intelligence")
        self.assertEqual(by_field["program.duration"][0].value.unit, "years")
        self.assertEqual(by_field["program.credits"][0].value.system, "ECTS")
        self.assertEqual(len(by_field["requirements"]), 2)
        self.assertEqual(by_field["costs.tuition"][0].value.currency, "GBP")
        self.assertEqual(by_field["offerings.application_window.closes"][0].value, "2027-03-15")
        self.assertEqual(by_field["requirements"][0].raw_text, "- Bachelor's degree in computer science")
        self.assertTrue(all(claim.source_id == "source-fixture" for claim in result.claims))
        self.assertTrue(all(claim.status != VerificationStatus.VERIFIED for claim in result.claims))
        self.assertEqual(result.not_observed_fields, ())

    def test_ambiguous_fields_remain_review_items(self):
        raw = """# University information
Tuition: $18,000 per year
Application deadline: 03/04/2027
Duration: 1-2 years
"""
        result = extract_program(fixture(raw))
        self.assertEqual(len(result.claims), 3)
        self.assertTrue(all(claim.value is None and claim.status == VerificationStatus.NEEDS_REVIEW for claim in result.claims))
        self.assertIn("program.name", result.not_observed_fields)
        self.assertIn("costs.tuition", {claim.field for claim in result.claims})

    def test_different_currencies_and_academic_systems_stay_distinct(self):
        raw = """# Master of Science in Computer Science
Credits: 120 ECTS
Tuition: EUR 18.000,00 per semester
## Entry requirements
- Minimum GPA 3.2/4.0
- Mathematics coursework required
"""
        result = extract_program(fixture(raw))
        costs = [claim.value for claim in result.claims if claim.field == "costs.tuition"]
        requirements = [claim.value for claim in result.claims if claim.field == "requirements"]
        self.assertEqual((costs[0].amount, costs[0].currency, costs[0].period), (18000, "EUR", "semester"))
        self.assertEqual(requirements[0].normalized, {"minimum": 3.2, "scale": 4.0})
        self.assertEqual(requirements[1].normalized, {"subjects": ["mathematics"]})

    def test_missing_deadline_is_not_invented(self):
        result = extract_program(fixture("# MSc Artificial Intelligence\nDuration: 2 years\n"))
        self.assertIn("offerings.application_window.closes", result.not_observed_fields)
        self.assertFalse(any(claim.field == "offerings.application_window.closes" for claim in result.claims))

    def test_inline_label_does_not_consume_unrelated_following_text(self):
        result = extract_program(fixture("Duration: 2 years\nContact: admissions office\n"))
        self.assertEqual(len(result.claims), 1)
        self.assertEqual(result.claims[0].field, "program.duration")

    def test_nested_requirements_inherit_parent_section(self):
        raw = """## Entry requirements
### Academic entry qualification overview
- Bachelor's degree in mathematics
### English language
- IELTS 6.5 overall
## Fees and funding
### Fees
GBP 18,000 per year for international students
### Policy on additional costs
Read the university policy for 2027 entrants.
"""
        result = extract_program(fixture(raw))
        self.assertEqual(len([claim for claim in result.claims if claim.field == "requirements"]), 2)
        self.assertEqual(len([claim for claim in result.claims if claim.field == "costs.fee"]), 1)

    def test_ambiguous_markdown_duration_remains_reviewable(self):
        raw = "* ![](https://example.edu/icon)Duration: **12 months (full-time), 24 months (part-time)**"
        result = extract_program(fixture(raw))
        self.assertEqual(len(result.claims), 1)
        self.assertEqual(result.claims[0].field, "program.duration")
        self.assertIsNone(result.claims[0].value)
        self.assertEqual(result.claims[0].status, VerificationStatus.NEEDS_REVIEW)

    def test_fee_section_ignores_text_without_amount(self):
        raw = """## Fees
Our fees are updated each year.
See guidance for all applicants.
Tuition is to be confirmed.
"""
        result = extract_program(fixture(raw))
        self.assertEqual(len(result.claims), 1)
        self.assertEqual(result.claims[0].status, VerificationStatus.NEEDS_REVIEW)

    def test_multiple_fee_amounts_keep_raw_evidence_for_review(self):
        line = "Domestic GBP 10,000; international GBP 20,000 per year"
        result = extract_program(fixture("## Tuition\n" + line))
        self.assertEqual(len(result.claims), 1)
        self.assertIsNone(result.claims[0].value)
        self.assertEqual(result.claims[0].raw_text, line)
        self.assertEqual(result.claims[0].status, VerificationStatus.NEEDS_REVIEW)


if __name__ == "__main__":
    unittest.main()
