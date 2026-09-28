"""Public Program Intelligence data contracts.

These models describe public program facts only. Student context is supplied
per task by the host and is never part of a ProgramRecord.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from math import isfinite
from urllib.parse import urlsplit


def _required(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _url(name: str, value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be an HTTP(S) URL")


def _date(name: str, value: str | None) -> None:
    if value is not None:
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an ISO 8601 date") from exc


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"
    STALE = "stale"
    NEEDS_REVIEW = "needs_review"
    NOT_FOUND = "not_found"


class RequirementType(StrEnum):
    ACADEMIC_DEGREE = "academic_degree"
    MINIMUM_GRADE = "minimum_grade"
    SUBJECT_PREREQUISITE = "subject_prerequisite"
    COURSE_PREREQUISITE = "course_prerequisite"
    LANGUAGE_TEST = "language_test"
    STANDARDIZED_TEST = "standardized_test"
    WORK_EXPERIENCE = "work_experience"
    PORTFOLIO = "portfolio"
    INTERVIEW = "interview"
    AUDITION = "audition"
    REFERENCE = "reference"
    STATEMENT = "statement"
    RESEARCH_PROPOSAL = "research_proposal"
    OTHER = "other"


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    PROGRAM_NOT_FOUND = "program_not_found"
    INSTITUTION_NOT_FOUND = "institution_not_found"
    SOURCE_UNAVAILABLE = "source_unavailable"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    CONFLICTING_SOURCES = "conflicting_sources"
    UNSUPPORTED_SOURCE = "unsupported_source"
    RATE_LIMITED = "rate_limited"
    PROVIDER_ERROR = "provider_error"
    RESEARCH_INCOMPLETE = "research_incomplete"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    url: str
    title: str
    publisher: str
    source_type: str
    fetched_at: str
    status: str = "accessible"

    def __post_init__(self) -> None:
        for name in ("source_id", "title", "publisher", "source_type", "status"):
            _required(name, getattr(self, name))
        _url("url", self.url)
        try:
            timestamp = datetime.fromisoformat(self.fetched_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ValueError("fetched_at must be an ISO 8601 timestamp") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("fetched_at must include a timezone")


@dataclass(frozen=True, slots=True)
class FieldEvidence:
    field: str
    status: VerificationStatus
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _required("field", self.field)
        if not isinstance(self.status, VerificationStatus):
            raise ValueError("status must be a verification state")
        if self.status == VerificationStatus.VERIFIED and not self.source_ids:
            raise ValueError("verified field must cite a source")
        if self.status == VerificationStatus.CONFLICTING and len(self.source_ids) < 2:
            raise ValueError("conflicting field must cite at least two sources")


@dataclass(frozen=True, slots=True)
class Verification:
    status: VerificationStatus
    fields: tuple[FieldEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, VerificationStatus):
            raise ValueError("status must be a verification state")


@dataclass(frozen=True, slots=True)
class ApplicantScope:
    applicant_type: str | None = None
    countries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for country in self.countries:
            if len(country) != 2 or not country.isalpha() or not country.isupper():
                raise ValueError("countries must use ISO 3166-1 alpha-2 codes")


@dataclass(frozen=True, slots=True)
class Requirement:
    requirement_id: str
    type: RequirementType
    raw_text: str
    required: bool
    verification_status: VerificationStatus
    source_id: str
    applies_to: ApplicantScope = field(default_factory=ApplicantScope)
    normalized: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("requirement_id", "raw_text", "source_id"):
            _required(name, getattr(self, name))
        if not isinstance(self.type, RequirementType):
            raise ValueError("type must be a requirement type")
        if not isinstance(self.required, bool):
            raise ValueError("required must be a boolean")
        if not isinstance(self.verification_status, VerificationStatus):
            raise ValueError("verification_status must be a verification state")


@dataclass(frozen=True, slots=True)
class ApplicationWindow:
    opens: str | None = None
    closes: str | None = None

    def __post_init__(self) -> None:
        _date("opens", self.opens)
        _date("closes", self.closes)
        if self.opens and self.closes and self.opens > self.closes:
            raise ValueError("application window closes before it opens")


@dataclass(frozen=True, slots=True)
class Offering:
    intake_id: str
    term: str | None = None
    academic_year: str | None = None
    start_date: str | None = None
    application_window: ApplicationWindow | None = None
    deadline_type: str | None = None
    applicant_scope: str | None = None
    status: str | None = None
    source_id: str | None = None

    def __post_init__(self) -> None:
        _required("intake_id", self.intake_id)
        _date("start_date", self.start_date)


@dataclass(frozen=True, slots=True)
class Cost:
    type: str
    amount: int | float
    currency: str
    period: str
    verification_status: VerificationStatus
    source_id: str
    applicant_scope: str | None = None
    academic_year: str | None = None

    def __post_init__(self) -> None:
        for name in ("type", "period", "source_id"):
            _required(name, getattr(self, name))
        if not isinstance(self.verification_status, VerificationStatus):
            raise ValueError("verification_status must be a verification state")
        if isinstance(self.amount, bool) or not isinstance(self.amount, (int, float)):
            raise ValueError("amount must be a non-negative number")
        if not isfinite(self.amount) or self.amount < 0:
            raise ValueError("amount must be a non-negative finite number")
        if len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
            raise ValueError("currency must use an ISO 4217 code")


@dataclass(frozen=True, slots=True)
class Institution:
    institution_id: str
    name: str
    country: str
    city: str | None = None
    official_url: str | None = None

    def __post_init__(self) -> None:
        _required("institution_id", self.institution_id)
        _required("institution name", self.name)
        if len(self.country) != 2 or not self.country.isalpha() or not self.country.isupper():
            raise ValueError("country must use an ISO 3166-1 alpha-2 code")
        if self.official_url is not None:
            _url("institution official_url", self.official_url)


@dataclass(frozen=True, slots=True)
class Duration:
    value: int | float
    unit: str

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValueError("duration value must be a positive number")
        if not isfinite(self.value) or self.value <= 0:
            raise ValueError("duration value must be positive and finite")
        _required("duration unit", self.unit)


@dataclass(frozen=True, slots=True)
class Credits:
    value: int | float
    system: str

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValueError("credits value must be a positive number")
        if not isfinite(self.value) or self.value <= 0:
            raise ValueError("credits value must be positive and finite")
        _required("credits system", self.system)


@dataclass(frozen=True, slots=True)
class ProgramDetails:
    name: str
    official_url: str
    award: str | None = None
    level: str | None = None
    field: tuple[str, ...] = ()
    mode: str | None = None
    campus: str | None = None
    duration: Duration | None = None
    credits: Credits | None = None

    def __post_init__(self) -> None:
        _required("program name", self.name)
        _url("program official_url", self.official_url)


@dataclass(frozen=True, slots=True)
class FundingLink:
    title: str
    url: str
    source_id: str

    def __post_init__(self) -> None:
        _required("title", self.title)
        _required("source_id", self.source_id)
        _url("funding url", self.url)


@dataclass(frozen=True, slots=True)
class ProgramRecord:
    program_id: str
    institution: Institution
    program: ProgramDetails
    sources: tuple[Source, ...]
    verification: Verification
    offerings: tuple[Offering, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    costs: tuple[Cost, ...] = ()
    funding: tuple[FundingLink, ...] = ()
    curriculum: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required("program_id", self.program_id)
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source IDs must be unique within a program")
        if self.verification.status == VerificationStatus.VERIFIED and not source_ids:
            raise ValueError("a verified program must include sources")
        requirement_ids = [requirement.requirement_id for requirement in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirement IDs must be unique within a program")
        known_sources = set(source_ids)
        referenced_sources = [item.source_id for item in self.requirements]
        referenced_sources += [item.source_id for item in self.costs]
        referenced_sources += [item.source_id for item in self.funding]
        referenced_sources += [item.source_id for item in self.offerings if item.source_id]
        for evidence in self.verification.fields:
            referenced_sources.extend(evidence.source_ids)
        if not set(referenced_sources) <= known_sources:
            raise ValueError("facts must reference sources in the program record")


@dataclass(frozen=True, slots=True)
class CapabilityError:
    code: ErrorCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, ErrorCode):
            raise ValueError("code must be a supported error code")
        _required("message", self.message)
