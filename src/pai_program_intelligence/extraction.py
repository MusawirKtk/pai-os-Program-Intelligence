"""Extract explicit claims from fetched Markdown without inventing missing facts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalization import (
    normalize_cost,
    normalize_credits,
    normalize_deadline,
    normalize_duration,
    normalize_program_heading,
    normalize_requirement,
)
from .schemas import Source, VerificationStatus
from .sources import FetchedSource


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    field: str
    value: object | None
    raw_text: str
    source_id: str
    line_number: int
    status: VerificationStatus


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    source: Source
    raw_text: str
    claims: tuple[ExtractedClaim, ...]
    not_observed_fields: tuple[str, ...]


_TARGET_FIELDS = (
    "program.name",
    "program.duration",
    "program.credits",
    "requirements",
    "costs.tuition",
    "offerings.application_window.closes",
)


def _section(label: str) -> str | None:
    normalized = " ".join(label.lower().replace("-", " ").split())
    if normalized in {"duration", "length of study", "programme duration", "program duration"}:
        return "duration"
    if normalized in {"credits", "credit points", "ects"}:
        return "credits"
    if "tuition" in normalized:
        return "tuition"
    if normalized in {"fees", "mandatory fees", "program fees", "programme fees"}:
        return "fee"
    if normalized in {"deadline", "application deadline", "applications close", "apply by"}:
        return "deadline"
    if normalized in {
        "requirements",
        "entry requirements",
        "admission requirements",
        "academic requirements",
        "language requirements",
        "eligibility requirements",
    }:
        return "requirements"
    return None


def _claim(field: str, value: object | None, raw: str, source_id: str, line_number: int) -> ExtractedClaim:
    status = VerificationStatus.UNVERIFIED if value is not None else VerificationStatus.NEEDS_REVIEW
    return ExtractedClaim(field, value, raw, source_id, line_number, status)


def _cost_statement(text: str) -> bool:
    return bool(
        re.search(r"\b[A-Z]{3}\s+\d|\b\d[\d.,]*\s+[A-Z]{3}\b|[$£€]\s*\d", text)
        or re.search(r"\b(?:not yet set|to be confirmed|tba)\b", text, re.IGNORECASE)
    )


def extract_program(source: FetchedSource) -> ExtractionResult:
    """Parse high-confidence fields; leave all other evidence for review.

    A single source cannot verify a factual claim. Verification and conflict
    handling belong to the next milestone.
    """
    claims: list[ExtractedClaim] = []
    headings: list[tuple[int, str | None]] = []
    has_name = False
    for line_number, raw_line in enumerate(source.raw_text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            title = heading[2].strip()
            heading_level = len(heading[1])
            if heading_level == 1 and not has_name:
                program = normalize_program_heading(title)
                if program:
                    name, award, level = program
                    claims.extend(
                        (
                            _claim("program.name", name, raw_line, source.source.source_id, line_number),
                            _claim("program.award", award, raw_line, source.source.source_id, line_number),
                            _claim("program.level", level, raw_line, source.source.source_id, line_number),
                        )
                    )
                    has_name = True
            while headings and headings[-1][0] >= heading_level:
                headings.pop()
            section = _section(title)
            headings.append((heading_level, section if section is not None else headings[-1][1] if headings else None))
            continue
        cleaned = re.sub(r"^[-*•]\s+|^\d+[.)]\s+", "", line).strip()
        cleaned = re.sub(r"^!\[[^]]*\]\([^)]+\)\s*", "", cleaned).strip()
        label_match = re.match(r"^\*{0,2}([^:]{2,60}?)\*{0,2}:\s*(.*)$", cleaned)
        active_section = headings[-1][1] if headings else None
        if label_match:
            detected = _section(label_match[1].strip("* "))
            if detected:
                active_section = detected
                cleaned = label_match[2].strip("*_ ")
                if not cleaned:
                    continue
            else:
                continue
        if active_section == "duration":
            claims.append(_claim("program.duration", normalize_duration(cleaned), raw_line, source.source.source_id, line_number))
        elif active_section == "credits":
            claims.append(_claim("program.credits", normalize_credits(cleaned), raw_line, source.source.source_id, line_number))
        elif active_section in {"tuition", "fee"}:
            if _cost_statement(cleaned):
                cost = normalize_cost(cleaned, source.source.source_id, kind="tuition" if active_section == "tuition" else "fee")
                claims.append(_claim("costs.tuition" if active_section == "tuition" else "costs.fee", cost, raw_line, source.source.source_id, line_number))
        elif active_section == "deadline":
            claims.append(_claim("offerings.application_window.closes", normalize_deadline(cleaned), raw_line, source.source.source_id, line_number))
        elif active_section == "requirements":
            requirement = normalize_requirement(cleaned, source.source.source_id)
            claims.append(
                ExtractedClaim(
                    "requirements",
                    requirement,
                    raw_line,
                    source.source.source_id,
                    line_number,
                    requirement.verification_status,
                )
            )
    observed = {claim.field for claim in claims}
    return ExtractionResult(
        source.source,
        source.raw_text,
        tuple(claims),
        tuple(field for field in _TARGET_FIELDS if field not in observed),
    )
