"""Conservative normalization of explicit program-page statements.

None means the text cannot be interpreted safely. Callers keep the original
statement as review-needed evidence rather than guessing a value.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from decimal import Decimal

from .schemas import (
    ApplicantScope,
    Cost,
    Credits,
    Duration,
    Requirement,
    RequirementType,
    VerificationStatus,
)


def normalize_program_heading(text: str) -> tuple[str, str, str] | None:
    name = " ".join(text.split())
    awards = (
        (r"M\.?Sc\.?(?=\s|$)", "MSc", "masters"),
        (r"M\.?Eng\.?(?=\s|$)", "MEng", "masters"),
        (r"MBA\b", "MBA", "masters"),
        (r"M\.?A\.?(?=\s|$)", "MA", "masters"),
        (r"M\.?S\.?(?=\s|$)", "MS", "masters"),
        (r"Master(?:'s)? of Science\b", "Master of Science", "masters"),
        (r"Master(?:'s)? of Arts\b", "Master of Arts", "masters"),
        (r"B\.?Sc\.?(?=\s|$)", "BSc", "bachelors"),
        (r"B\.?Eng\.?(?=\s|$)", "BEng", "bachelors"),
        (r"B\.?A\.?(?=\s|$)", "BA", "bachelors"),
        (r"B\.?S\.?(?=\s|$)", "BS", "bachelors"),
        (r"Bachelor(?:'s)? of Science\b", "Bachelor of Science", "bachelors"),
        (r"Bachelor(?:'s)? of Arts\b", "Bachelor of Arts", "bachelors"),
        (r"Ph\.?D\.?(?=\s|$)", "PhD", "doctoral"),
        (r"Doctor of Philosophy\b", "Doctor of Philosophy", "doctoral"),
    )
    for pattern, award, level in awards:
        if re.match(pattern, name, re.IGNORECASE):
            return name, award, level
    return None


def normalize_duration(text: str) -> Duration | None:
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s+(years?|months?|semesters?|terms?)\s*",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = float(match[1])
    unit = match[2].lower().rstrip("s") + "s"
    return Duration(int(value) if value.is_integer() else value, unit)


def normalize_credits(text: str) -> Credits | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s+ECTS(?:\s+credits?)?\s*", text, re.IGNORECASE)
    if not match:
        return None
    value = float(match[1])
    return Credits(int(value) if value.is_integer() else value, "ECTS")


def _amount(token: str) -> int | float | None:
    if re.fullmatch(r"\d+", token):
        decimal = Decimal(token)
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", token):
        decimal = Decimal(token.replace(",", ""))
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", token):
        decimal = Decimal(token.replace(".", "").replace(",", "."))
    elif re.fullmatch(r"\d+[.,]\d{1,2}", token):
        decimal = Decimal(token.replace(",", "."))
    else:
        return None
    return int(decimal) if decimal == decimal.to_integral_value() else float(decimal)


def normalize_cost(text: str, source_id: str, *, kind: str = "tuition") -> Cost | None:
    """Require an explicit currency code and billing period; never infer FX."""
    first = list(re.finditer(r"\b([A-Z]{3})\s+(\d[\d.,]*)\b", text))
    second = list(re.finditer(r"\b(\d[\d.,]*)\s+([A-Z]{3})\b", text))
    if len(first) + len(second) != 1:
        return None
    money_match = (first or second)[0]
    year = re.search(r"\b(20\d{2}/20\d{2})\b", text)
    if any(
        not (money_match.start() <= number.start() and number.end() <= money_match.end())
        and not (year and year.start() <= number.start() and number.end() <= year.end())
        for number in re.finditer(r"\b\d[\d.,]*\b", text)
    ):
        return None
    if first:
        currency, token = money_match[1], money_match[2]
    elif second:
        token, currency = money_match[1], money_match[2]
    amount = _amount(token)
    if amount is None:
        return None
    lower = text.lower()
    periods = (
        (r"\bper academic year\b", "academic_year"),
        (r"\bper (?:year|annum)\b|/year\b|\bannually\b", "year"),
        (r"\bper semester\b|/semester\b", "semester"),
        (r"\bper term\b|/term\b", "term"),
        (r"\bper credit\b|/credit\b", "credit"),
        (r"\btotal\b|\bfor the full program(?:me)?\b", "total"),
    )
    matching_periods = [value for pattern, value in periods if re.search(pattern, lower)]
    if len(matching_periods) != 1:
        return None
    period = matching_periods[0]
    if sum(label in lower for label in ("non-eu", "international", "domestic")) > 1:
        return None
    if "non-eu" in lower:
        applicant_scope = "non_eu"
    elif "international" in lower:
        applicant_scope = "international"
    elif "domestic" in lower:
        applicant_scope = "domestic"
    else:
        applicant_scope = None
    return Cost(
        type=kind,
        amount=amount,
        currency=currency,
        period=period,
        verification_status=VerificationStatus.UNVERIFIED,
        source_id=source_id,
        applicant_scope=applicant_scope,
        academic_year=year[1] if year else None,
    )


def normalize_deadline(text: str) -> str | None:
    """Accept an explicit year and one unambiguous date only."""
    patterns = (
        (r"\b\d{4}-\d{2}-\d{2}\b", "%Y-%m-%d"),
        (r"\b\d{1,2} [A-Za-z]+ \d{4}\b", "%d %B %Y"),
        (r"\b[A-Za-z]+ \d{1,2},? \d{4}\b", None),
    )
    found: list[str] = []
    for pattern, format_string in patterns:
        for match in re.finditer(pattern, text):
            try:
                if format_string is None:
                    value = datetime.strptime(match[0].replace(",", ""), "%B %d %Y")
                else:
                    value = datetime.strptime(match[0], format_string)
            except ValueError:
                continue
            found.append(value.date().isoformat())
    return found[0] if len(found) == 1 else None


def normalize_requirement(text: str, source_id: str) -> Requirement:
    raw = " ".join(text.split())
    if not raw:
        raise ValueError("requirement text cannot be empty")
    lower = raw.lower()
    status = VerificationStatus.UNVERIFIED
    normalized: dict[str, object] = {}
    if "ielts" in lower or "toefl" in lower:
        kind = RequirementType.LANGUAGE_TEST
        test = "IELTS" if "ielts" in lower else "TOEFL"
        scores = re.findall(r"\b\d+(?:\.\d+)?\b", raw)
        normalized["test"] = test
        if len(scores) == 1:
            normalized["minimum_overall"] = float(scores[0])
        else:
            status = VerificationStatus.NEEDS_REVIEW
    elif "bachelor" in lower or "undergraduate degree" in lower:
        kind = RequirementType.ACADEMIC_DEGREE
        normalized["level"] = "bachelors"
        if "equivalent" in lower:
            status = VerificationStatus.NEEDS_REVIEW
    elif "master" in lower and "degree" in lower:
        kind = RequirementType.ACADEMIC_DEGREE
        normalized["level"] = "masters"
        if "equivalent" in lower:
            status = VerificationStatus.NEEDS_REVIEW
    elif "gpa" in lower or "cgpa" in lower or "%" in raw:
        kind = RequirementType.MINIMUM_GRADE
        scaled = re.search(r"\b(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\b", raw)
        percentage = re.search(r"\b(\d+(?:\.\d+)?)\s*%", raw)
        if scaled:
            normalized = {"minimum": float(scaled[1]), "scale": float(scaled[2])}
        elif percentage:
            normalized = {"minimum": float(percentage[1]), "scale": 100}
        else:
            status = VerificationStatus.NEEDS_REVIEW
    elif any(term in lower for term in ("course", "coursework", "credits in")):
        kind = RequirementType.COURSE_PREREQUISITE
        subjects = [term for term in ("mathematics", "statistics", "calculus", "programming") if term in lower]
        if subjects:
            normalized["subjects"] = subjects
        else:
            status = VerificationStatus.NEEDS_REVIEW
    elif "work experience" in lower:
        kind = RequirementType.WORK_EXPERIENCE
        status = VerificationStatus.NEEDS_REVIEW
    else:
        kind = RequirementType.OTHER
        status = VerificationStatus.NEEDS_REVIEW
    applicant_type = "international" if "international" in lower else None
    return Requirement(
        requirement_id="req-" + hashlib.sha256(f"{source_id}\0{raw}".encode("utf-8")).hexdigest()[:16],
        type=kind,
        raw_text=raw,
        required="optional" not in lower,
        verification_status=status,
        source_id=source_id,
        applies_to=ApplicantScope(applicant_type=applicant_type),
        normalized=normalized,
    )
