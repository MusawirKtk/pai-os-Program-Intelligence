"""Evaluate documented program requirements against task-scoped student context.

No student context is stored here or written to the public program cache.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from .schemas import Requirement, RequirementType, VerificationStatus


class MatchStatus(StrEnum):
    MET = "MET"
    NOT_MET = "NOT_MET"
    UNKNOWN = "UNKNOWN"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class ContextRequest:
    scope: str
    field: str
    reason: str


@dataclass(frozen=True, slots=True)
class RequirementMatch:
    requirement_id: str
    requirement: str
    status: MatchStatus
    program_source_id: str
    required: bool
    student_evidence: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    program_id: str
    overall: MatchStatus
    requirements: tuple[RequirementMatch, ...]
    status: str
    missing_student_context: tuple[str, ...] = ()
    required_context: tuple[ContextRequest, ...] = ()


def _section(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _canonical(value: object) -> str | None:
    text = _text(value)
    return "_".join(text.casefold().replace("-", " ").replace("_", " ").split()) if text else None


def _number(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _result(
    requirement: Requirement,
    status: MatchStatus,
    *,
    evidence: str | None = None,
    reason: str | None = None,
    needed: ContextRequest | None = None,
) -> tuple[RequirementMatch, ContextRequest | None]:
    return (
        RequirementMatch(
            requirement.requirement_id,
            requirement.raw_text,
            status,
            requirement.source_id,
            requirement.required,
            evidence,
            reason,
        ),
        needed,
    )


def _scope(requirement: Requirement, context: Mapping[str, object]):
    scope = requirement.applies_to
    applicant = _section(context.get("applicant"))
    if scope.applicant_type:
        applicant_type = _canonical(applicant.get("type"))
        if applicant_type is None:
            return _result(
                requirement, MatchStatus.UNKNOWN, reason="Applicant type not supplied",
                needed=ContextRequest("applicant", "type", "Required to select the applicable requirement"),
            )
        if applicant_type != _canonical(scope.applicant_type):
            return _result(requirement, MatchStatus.NOT_APPLICABLE, reason="Requirement applies to another applicant type")
    if scope.countries:
        country = _text(applicant.get("country"))
        if country is None or len(country) != 2 or not country.isalpha():
            return _result(
                requirement, MatchStatus.UNKNOWN, reason="Applicant ISO country code not supplied",
                needed=ContextRequest("applicant", "country", "Required to select the country-specific rule"),
            )
        if country.upper() not in scope.countries:
            return _result(requirement, MatchStatus.NOT_APPLICABLE, reason="Requirement applies to another country")
    return None


def _academic(requirement: Requirement, context: Mapping[str, object]):
    education = _section(context.get("education"))
    degrees = [education.get("current_or_highest")]
    history = education.get("history")
    if isinstance(history, list):
        degrees.extend(history)
    degrees = [_section(degree) for degree in degrees if isinstance(degree, Mapping)]
    if not degrees:
        return _result(
            requirement, MatchStatus.UNKNOWN, reason="Completed qualification not supplied",
            needed=ContextRequest("education", "current_or_highest", "Required to evaluate the degree requirement"),
        )
    required_level = _canonical(requirement.normalized.get("level"))
    if required_level not in {"bachelors", "masters", "doctoral"}:
        return _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Degree level is not safely normalized")
    matching = [degree for degree in degrees if _canonical(degree.get("level")) == required_level]
    if not matching:
        return _result(
            requirement, MatchStatus.UNKNOWN, reason="A matching completed degree is not documented",
            needed=ContextRequest("education", "history", "Required to check prior qualifications"),
        )
    completed = [degree for degree in matching if degree.get("completed") is True]
    if not completed:
        if all(degree.get("completed") is False for degree in matching):
            return _result(requirement, MatchStatus.NOT_MET, reason="Qualification is not yet awarded")
        return _result(
            requirement, MatchStatus.UNKNOWN, reason="Degree completion is not documented",
            needed=ContextRequest("education", "current_or_highest.completed", "Required to confirm the qualification was awarded"),
        )
    matching = completed
    fields = requirement.normalized.get("field")
    if fields is not None and (not isinstance(fields, (list, tuple)) or not all(isinstance(item, str) for item in fields)):
        return _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Accepted degree fields are ambiguous")
    accepted = {_canonical(item) for item in fields or ()}
    if accepted:
        for degree in matching:
            field = _canonical(degree.get("field"))
            if field and field in accepted:
                return _result(requirement, MatchStatus.MET, evidence=_text(degree.get("title")) or f"{required_level}: {field}")
        if not any(_text(degree.get("field")) for degree in matching):
            return _result(
                requirement, MatchStatus.UNKNOWN, reason="Degree field not supplied",
                needed=ContextRequest("education", "current_or_highest.field", "Required to check degree relevance"),
            )
        return _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Field equivalence needs human review")
    if any(word in requirement.raw_text.casefold() for word in ("relevant", "related", "equivalent")):
        return _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Degree relevance is not normalized")
    return _result(requirement, MatchStatus.MET, evidence=_text(matching[0].get("title")) or required_level)


def _grade(requirement: Requirement, context: Mapping[str, object]):
    minimum = _number(requirement.normalized.get("minimum"))
    scale = _number(requirement.normalized.get("scale"))
    if minimum is None or scale is None or scale <= 0 or not 0 <= minimum <= scale:
        return _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Grade threshold is not safely normalized")
    grade = _section(_section(_section(context.get("education")).get("current_or_highest")).get("grade"))
    value = _number(grade.get("value"))
    student_scale = _number(grade.get("scale"))
    if value is None or student_scale is None:
        return _result(
            requirement, MatchStatus.UNKNOWN, reason="Comparable grade not supplied",
            needed=ContextRequest("education", "current_or_highest.grade", "Required to evaluate the minimum grade"),
        )
    if student_scale != scale or not 0 <= value <= student_scale:
        return _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Grade scales are not directly comparable")
    direction = _canonical(requirement.normalized.get("direction"))
    if direction is None and ("gpa" in requirement.raw_text.casefold() or "%" in requirement.raw_text):
        direction = "higher_is_better"
    if direction not in {"higher_is_better", "lower_is_better"}:
        return _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Grade scale direction is unknown")
    met = value >= minimum if direction == "higher_is_better" else value <= minimum
    return _result(requirement, MatchStatus.MET if met else MatchStatus.NOT_MET, evidence=f"{value}/{student_scale}")


def _language(requirement: Requirement, context: Mapping[str, object]):
    test = _text(requirement.normalized.get("test"))
    minimum = _number(requirement.normalized.get("minimum_overall"))
    if test is None or minimum is None or minimum < 0:
        return _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Test threshold is not safely normalized")
    tests = context.get("tests")
    if not isinstance(tests, list):
        tests = []
    matching = [_section(item) for item in tests if _canonical(_section(item).get("test")) == _canonical(test)]
    scores = [score for item in matching if (score := _number(item.get("overall"))) is not None and score >= 0]
    if not scores:
        return _result(
            requirement, MatchStatus.UNKNOWN, reason=f"{test.upper()} overall score not supplied",
            needed=ContextRequest("tests", test.upper(), "Required to evaluate the documented test threshold"),
        )
    best = max(scores)
    return _result(
        requirement, MatchStatus.MET if best >= minimum else MatchStatus.NOT_MET,
        evidence=f"{test.upper()} {best}",
    )


def _course(requirement: Requirement, context: Mapping[str, object]):
    subjects = requirement.normalized.get("subjects")
    if not isinstance(subjects, (list, tuple)) or len(subjects) != 1 or not isinstance(subjects[0], str):
        return _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Course condition is not safely normalized")
    education = _section(context.get("education"))
    courses = education.get("undergraduate_course_history")
    if not isinstance(courses, list):
        return _result(
            requirement, MatchStatus.UNKNOWN, reason="Transcript course-level evidence not supplied",
            needed=ContextRequest("education", "undergraduate_course_history", "Required to evaluate the prerequisite"),
        )
    subject = _canonical(subjects[0])
    for course in courses:
        name = _canonical(course if isinstance(course, str) else _section(course).get("subject"))
        if name == subject:
            return _result(requirement, MatchStatus.MET, evidence=f"{subjects[0]} coursework")
    if education.get("undergraduate_course_history_complete") is True:
        return _result(requirement, MatchStatus.NOT_MET, reason="Complete supplied course history lacks this prerequisite")
    return _result(
        requirement, MatchStatus.UNKNOWN, reason="Supplied course history may be incomplete",
        needed=ContextRequest("education", "undergraduate_course_history", "Complete transcript needed to rule out this prerequisite"),
    )


def evaluate_eligibility(
    program_id: str,
    requirements: Sequence[Requirement],
    context: Mapping[str, object],
) -> EligibilityResult:
    """Return documented matches only; never predict admission or retain context."""
    if not isinstance(program_id, str) or not program_id.strip():
        raise ValueError("program_id must be a non-empty string")
    if not isinstance(context, Mapping):
        raise ValueError("context must be an object")
    matches: list[RequirementMatch] = []
    requests: dict[tuple[str, str], ContextRequest] = {}
    for requirement in requirements:
        if not isinstance(requirement, Requirement):
            raise ValueError("requirements must contain Requirement objects")
        if requirement.verification_status != VerificationStatus.VERIFIED:
            match, needed = _result(requirement, MatchStatus.NEEDS_REVIEW, reason="Requirement is not verified and current")
        else:
            scoped = _scope(requirement, context)
            if scoped is not None:
                match, needed = scoped
            elif requirement.type == RequirementType.ACADEMIC_DEGREE:
                match, needed = _academic(requirement, context)
            elif requirement.type == RequirementType.MINIMUM_GRADE:
                match, needed = _grade(requirement, context)
            elif requirement.type == RequirementType.LANGUAGE_TEST:
                match, needed = _language(requirement, context)
            elif requirement.type in {RequirementType.COURSE_PREREQUISITE, RequirementType.SUBJECT_PREREQUISITE}:
                match, needed = _course(requirement, context)
            else:
                match, needed = _result(requirement, MatchStatus.NEEDS_REVIEW, reason="No safe automated rule for this requirement type")
        matches.append(match)
        if needed is not None and requirement.required:
            requests.setdefault((needed.scope, needed.field), needed)
    required = [match.status for match in matches if match.required and match.status != MatchStatus.NOT_APPLICABLE]
    if MatchStatus.NOT_MET in required:
        overall = MatchStatus.NOT_MET
    elif not required or any(status in {MatchStatus.UNKNOWN, MatchStatus.NEEDS_REVIEW} for status in required):
        overall = MatchStatus.NEEDS_REVIEW
    else:
        overall = MatchStatus.MET
    if matches and all(match.status == MatchStatus.NOT_APPLICABLE for match in matches):
        overall = MatchStatus.NOT_APPLICABLE
    needed_context = tuple(requests.values())
    return EligibilityResult(
        program_id,
        overall,
        tuple(matches),
        "needs_context" if needed_context else "complete",
        tuple(request.field for request in needed_context),
        needed_context,
    )
