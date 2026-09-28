"""Country-neutral parsing tests using explicit source statements."""

import unittest

from pai_program_intelligence.normalization import (
    normalize_cost,
    normalize_credits,
    normalize_deadline,
    normalize_duration,
    normalize_program_heading,
    normalize_requirement,
)
from pai_program_intelligence.schemas import RequirementType, VerificationStatus


class NormalizationTests(unittest.TestCase):
    def test_degree_heading_and_duration(self):
        self.assertEqual(normalize_program_heading("MSc Artificial Intelligence"), ("MSc Artificial Intelligence", "MSc", "masters"))
        self.assertEqual(normalize_program_heading("M.Sc. Artificial Intelligence"), ("M.Sc. Artificial Intelligence", "MSc", "masters"))
        self.assertEqual(normalize_duration("18 months").value, 18)
        self.assertIsNone(normalize_duration("1-2 years"))

    def test_credits_need_explicit_system(self):
        self.assertEqual(normalize_credits("120 ECTS").system, "ECTS")
        self.assertIsNone(normalize_credits("120 credits"))

    def test_cost_keeps_original_currency_period_and_scope(self):
        uk = normalize_cost("International tuition: GBP 18,000 per academic year", "source-1")
        self.assertEqual((uk.amount, uk.currency, uk.period, uk.applicant_scope), (18000, "GBP", "academic_year", "international"))
        europe = normalize_cost("Tuition: EUR 18.000,00 per semester", "source-2")
        self.assertEqual((europe.amount, europe.currency, europe.period), (18000, "EUR", "semester"))
        australia = normalize_cost("Tuition: AUD 42,000 per year", "source-3")
        self.assertEqual((australia.amount, australia.currency), (42000, "AUD"))
        dated = normalize_cost("Tuition: GBP 18,000 per year in 2026/2027", "source-4")
        self.assertEqual((dated.amount, dated.academic_year), (18000, "2026/2027"))

    def test_ambiguous_cost_is_not_converted(self):
        self.assertIsNone(normalize_cost("Tuition: $18,000 per year", "source-1"))
        self.assertIsNone(normalize_cost("Tuition: CAD 18,000", "source-1"))
        self.assertIsNone(normalize_cost("Domestic: GBP 10,000; international: GBP 20,000 per year", "source-1"))
        self.assertIsNone(normalize_cost("Tuition: GBP 10,000 or 20,000 per year", "source-1"))
        self.assertIsNone(normalize_cost("Tuition: GBP 10,000 or £20,000 per year", "source-1"))
        self.assertIsNone(normalize_cost("Tuition: GBP 10,000 per year or per semester", "source-1"))
        self.assertIsNone(normalize_cost("Tuition: GBP 10,000 per year for domestic and international applicants", "source-1"))

    def test_deadline_needs_one_explicit_unambiguous_date(self):
        self.assertEqual(normalize_deadline("15 March 2027"), "2027-03-15")
        self.assertEqual(normalize_deadline("March 15, 2027"), "2027-03-15")
        self.assertEqual(normalize_deadline("2027-03-15"), "2027-03-15")
        self.assertIsNone(normalize_deadline("03/04/2027"))
        self.assertIsNone(normalize_deadline("15 March"))
        self.assertIsNone(normalize_deadline("15 March 2027 or 15 June 2027"))

    def test_requirement_keeps_raw_text_and_does_not_convert_grades(self):
        grade = normalize_requirement("Minimum GPA 3.2/4.0", "source-1")
        self.assertEqual(grade.type, RequirementType.MINIMUM_GRADE)
        self.assertEqual(grade.normalized, {"minimum": 3.2, "scale": 4.0})
        self.assertEqual(grade.raw_text, "Minimum GPA 3.2/4.0")
        language = normalize_requirement("IELTS 6.5 overall", "source-1")
        self.assertEqual(language.normalized, {"test": "IELTS", "minimum_overall": 6.5})

    def test_equivalence_and_multiple_language_scores_need_review(self):
        equivalence = normalize_requirement("Bachelor's degree or country-specific equivalent", "source-1")
        self.assertEqual(equivalence.verification_status, VerificationStatus.NEEDS_REVIEW)
        language = normalize_requirement("IELTS 6.5 overall and 6.0 in each band", "source-1")
        self.assertEqual(language.verification_status, VerificationStatus.NEEDS_REVIEW)
        self.assertNotIn("minimum_overall", language.normalized)


if __name__ == "__main__":
    unittest.main()
