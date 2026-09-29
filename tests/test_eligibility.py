"""Conservative requirement matching; no student data is persisted."""

import unittest

from pai_program_intelligence.eligibility import MatchStatus, evaluate_eligibility
from pai_program_intelligence.schemas import ApplicantScope, Requirement, RequirementType, VerificationStatus


def requirement(
    kind: RequirementType,
    normalized: dict[str, object],
    raw: str,
    *,
    status: VerificationStatus = VerificationStatus.VERIFIED,
    required: bool = True,
    scope: ApplicantScope = ApplicantScope(),
) -> Requirement:
    return Requirement("req-1", kind, raw, required, status, "official-1", scope, normalized)


class EligibilityTests(unittest.TestCase):
    def test_handbook_scenario_requires_transcript_for_math(self):
        requirements = (
            requirement(RequirementType.ACADEMIC_DEGREE, {"level": "bachelors", "field": ["computer_science"]}, "Relevant bachelor's in CS"),
            requirement(RequirementType.LANGUAGE_TEST, {"test": "IELTS", "minimum_overall": 6.5}, "IELTS 6.5 overall"),
            requirement(RequirementType.COURSE_PREREQUISITE, {"subjects": ["mathematics"]}, "Mathematics coursework"),
        )
        context = {
            "education": {"current_or_highest": {"level": "bachelors", "completed": True, "field": "computer_science", "title": "BS Computer Science"}},
            "tests": [{"test": "IELTS", "overall": 7}],
        }
        result = evaluate_eligibility("program-1", requirements, context)
        self.assertEqual([item.status for item in result.requirements], [MatchStatus.MET, MatchStatus.MET, MatchStatus.UNKNOWN])
        self.assertEqual(result.overall, MatchStatus.NEEDS_REVIEW)
        self.assertEqual(result.status, "needs_context")
        self.assertEqual(result.missing_student_context, ("undergraduate_course_history",))
        self.assertEqual(result.required_context[0].scope, "education")
        self.assertEqual(result.requirements[0].program_source_id, "official-1")

    def test_comparable_grade_below_threshold_is_not_met(self):
        rule = requirement(RequirementType.MINIMUM_GRADE, {"minimum": 3.2, "scale": 4}, "Minimum GPA 3.2/4")
        context = {"education": {"current_or_highest": {"grade": {"value": 3.1, "scale": 4}}}}
        result = evaluate_eligibility("p", [rule], context)
        self.assertEqual(result.overall, MatchStatus.NOT_MET)
        self.assertEqual(result.requirements[0].status, MatchStatus.NOT_MET)

    def test_grade_scale_is_not_converted(self):
        rule = requirement(RequirementType.MINIMUM_GRADE, {"minimum": 80, "scale": 100}, "Minimum 80%")
        context = {"education": {"current_or_highest": {"grade": {"value": 3.8, "scale": 4}}}}
        self.assertEqual(evaluate_eligibility("p", [rule], context).overall, MatchStatus.NEEDS_REVIEW)

    def test_unknown_grade_direction_needs_review(self):
        rule = requirement(RequirementType.MINIMUM_GRADE, {"minimum": 1.5, "scale": 5}, "Minimum grade 1.5/5")
        context = {"education": {"current_or_highest": {"grade": {"value": 1.3, "scale": 5}}}}
        self.assertEqual(evaluate_eligibility("p", [rule], context).overall, MatchStatus.NEEDS_REVIEW)

    def test_language_below_threshold_is_not_met(self):
        rule = requirement(RequirementType.LANGUAGE_TEST, {"test": "IELTS", "minimum_overall": 6.5}, "IELTS 6.5 overall")
        result = evaluate_eligibility("p", [rule], {"tests": [{"test": "IELTS", "overall": 6}]})
        self.assertEqual(result.overall, MatchStatus.NOT_MET)

    def test_unverified_rule_cannot_be_met(self):
        rule = requirement(
            RequirementType.LANGUAGE_TEST, {"test": "IELTS", "minimum_overall": 6.5}, "IELTS 6.5 overall",
            status=VerificationStatus.CONFLICTING,
        )
        result = evaluate_eligibility("p", [rule], {"tests": [{"test": "IELTS", "overall": 7}]})
        self.assertEqual(result.requirements[0].status, MatchStatus.NEEDS_REVIEW)

    def test_applicant_scope(self):
        rule = requirement(
            RequirementType.LANGUAGE_TEST, {"test": "IELTS", "minimum_overall": 6.5}, "IELTS 6.5 for international applicants",
            scope=ApplicantScope("international", ("PK",)),
        )
        domestic = evaluate_eligibility("p", [rule], {"applicant": {"type": "domestic", "country": "PK"}})
        self.assertEqual(domestic.overall, MatchStatus.NOT_APPLICABLE)
        missing = evaluate_eligibility("p", [rule], {})
        self.assertEqual(missing.requirements[0].status, MatchStatus.UNKNOWN)
        self.assertEqual(missing.missing_student_context, ("type",))
        other_country = evaluate_eligibility("p", [rule], {"applicant": {"type": "international", "country": "DE"}})
        self.assertEqual(other_country.overall, MatchStatus.NOT_APPLICABLE)
        invalid_country = evaluate_eligibility("p", [rule], {"applicant": {"type": "international", "country": "Pakistan"}})
        self.assertEqual(invalid_country.requirements[0].status, MatchStatus.UNKNOWN)

    def test_course_absence_needs_complete_transcript_for_not_met(self):
        rule = requirement(RequirementType.COURSE_PREREQUISITE, {"subjects": ["mathematics"]}, "Mathematics coursework")
        partial = {"education": {"undergraduate_course_history": ["statistics"]}}
        self.assertEqual(evaluate_eligibility("p", [rule], partial).requirements[0].status, MatchStatus.UNKNOWN)
        complete = {"education": {"undergraduate_course_history": ["statistics"], "undergraduate_course_history_complete": True}}
        self.assertEqual(evaluate_eligibility("p", [rule], complete).requirements[0].status, MatchStatus.NOT_MET)
        found = {"education": {"undergraduate_course_history": [{"subject": "mathematics"}]}}
        self.assertEqual(evaluate_eligibility("p", [rule], found).requirements[0].status, MatchStatus.MET)

    def test_multiple_subjects_need_human_interpretation(self):
        rule = requirement(RequirementType.COURSE_PREREQUISITE, {"subjects": ["math", "statistics"]}, "Math or statistics")
        self.assertEqual(evaluate_eligibility("p", [rule], {}).requirements[0].status, MatchStatus.NEEDS_REVIEW)

    def test_relevant_degree_without_accepted_fields_needs_review(self):
        rule = requirement(RequirementType.ACADEMIC_DEGREE, {"level": "bachelors"}, "Relevant bachelor's degree")
        context = {"education": {"current_or_highest": {"level": "bachelors", "completed": True, "field": "computer_science"}}}
        self.assertEqual(evaluate_eligibility("p", [rule], context).requirements[0].status, MatchStatus.NEEDS_REVIEW)

    def test_unfinished_degree_is_not_marked_met(self):
        rule = requirement(RequirementType.ACADEMIC_DEGREE, {"level": "bachelors"}, "Bachelor's degree")
        context = {"education": {"current_or_highest": {"level": "bachelors", "completed": False}}}
        result = evaluate_eligibility("p", [rule], context)
        self.assertEqual(result.requirements[0].status, MatchStatus.NOT_MET)
        self.assertEqual(result.missing_student_context, ())

    def test_optional_missing_test_does_not_request_context(self):
        required = requirement(RequirementType.ACADEMIC_DEGREE, {"level": "bachelors"}, "Bachelor's degree")
        optional = requirement(RequirementType.LANGUAGE_TEST, {"test": "IELTS", "minimum_overall": 6.5}, "Optional IELTS", required=False)
        context = {"education": {"current_or_highest": {"level": "bachelors", "completed": True}}}
        result = evaluate_eligibility("p", [required, optional], context)
        self.assertEqual(result.overall, MatchStatus.MET)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.required_context, ())

    def test_invalid_input_and_empty_requirements(self):
        with self.assertRaises(ValueError):
            evaluate_eligibility("", [], {})
        with self.assertRaises(ValueError):
            evaluate_eligibility("p", [], [])
        self.assertEqual(evaluate_eligibility("p", [], {}).overall, MatchStatus.NEEDS_REVIEW)


if __name__ == "__main__":
    unittest.main()
