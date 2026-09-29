"""Conservative, stable identity for public program records."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import urlsplit

from .schemas import Institution, ProgramDetails


def _key(text: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    return " ".join(re.findall(r"\w+", normalized))


def program_id(institution: Institution, program: ProgramDetails, *, program_code: str | None = None) -> str:
    """Collapse page aliases, but keep different awards/campuses/codes distinct."""
    host = urlsplit(institution.official_url).hostname if institution.official_url else None
    institution_key = host.removeprefix("www.") if host else f"{_key(institution.name)}:{institution.country}"
    identity = "\0".join(
        (institution_key, _key(program.name), _key(program.award), _key(program.campus), _key(program_code))
    )
    return "program-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
