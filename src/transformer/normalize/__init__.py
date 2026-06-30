"""Pure, deterministic normalizers — one concern per file.

Contract for every function here:
  * takes a raw value, returns the canonical value OR None,
  * never raises (a bad value yields None, the pipeline stays alive),
  * never invents data (un-parseable -> None; the caller keeps the raw string).

Re-exported here so adapters can `from ..normalize import to_e164, ...`.
"""

from .dates import to_year, to_year_month
from .locations import country_to_iso2, parse_location_string
from .phones import to_e164
from .skills import UNKNOWN_SKILL_PENALTY, canonical_skill, is_known, split_skills
from .text import clean_email, clean_name
from .urls import canonical_url

__all__ = [
    "to_year", "to_year_month",
    "country_to_iso2", "parse_location_string",
    "to_e164",
    "UNKNOWN_SKILL_PENALTY", "canonical_skill", "is_known", "split_skills",
    "clean_email", "clean_name",
    "canonical_url",
]
