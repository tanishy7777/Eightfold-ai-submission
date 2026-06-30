"""Trust policy — the single source of truth for "how much do we believe X".

Both merge.py (to pick a winner) and confidence.py (to score a value) need the
same notion of how trustworthy a claim is. Keeping the tables here means there
is exactly ONE place to read, tune, and defend on camera — no drift between the
two modules.

A claim's base score = trust(source, field) x method_factor(method).
  - trust: a fixed table of "field-source affinity" — which source is
    authoritative for which kind of field (contact info from CSV/ATS,
    skills from GitHub/resume, experience from LinkedIn/resume, ...).
  - method_factor: how the value was obtained (a direct structured field beats
    a regex pull from free text beats an inference).

Everything is a fixed constant: determinism requires no randomness and no
runtime tuning. Same inputs -> same scores -> same winners.
"""

from __future__ import annotations

from .models import Method

# Canonical source names (must match adapter `source` strings).
RECRUITER_CSV = "recruiter_csv"
ATS_JSON = "ats_json"
RECRUITER_NOTES = "recruiter_notes"
GITHUB = "github"
RESUME = "resume"
LINKEDIN = "linkedin"

# A new/unknown source is believed only weakly — never over-trust a stranger.
_DEFAULT_TRUST = 0.4

# Field-source affinity, grouped by field "category".
# Rows = category, columns = source. Values in [0,1].
# Rationale per row is in the inline comment so each number is defendable.
_TRUST: dict[str, dict[str, float]] = {
    # Contact info is the recruiting system's job; CSV/ATS are authoritative.
    "contact": {RECRUITER_CSV: 0.95, ATS_JSON: 0.90, RESUME: 0.70,
                LINKEDIN: 0.60, RECRUITER_NOTES: 0.50, GITHUB: 0.30},
    # Name appears everywhere; structured sources slightly ahead.
    "identity": {RECRUITER_CSV: 0.90, ATS_JSON: 0.90, LINKEDIN: 0.80,
                 RESUME: 0.80, GITHUB: 0.70, RECRUITER_NOTES: 0.60},
    # Where someone lives: profiles/ATS know it best.
    "location": {LINKEDIN: 0.85, ATS_JSON: 0.80, RECRUITER_CSV: 0.70,
                 RESUME: 0.70, GITHUB: 0.50, RECRUITER_NOTES: 0.50},
    # A one-line headline is a profile concept (LinkedIn owns it).
    "headline": {LINKEDIN: 0.90, RESUME: 0.60, ATS_JSON: 0.50,
                 GITHUB: 0.40, RECRUITER_NOTES: 0.40, RECRUITER_CSV: 0.30},
    # Years of experience: profiles/resume state it; CSV rarely does.
    "years": {LINKEDIN: 0.80, RESUME: 0.70, ATS_JSON: 0.60,
              RECRUITER_NOTES: 0.40, RECRUITER_CSV: 0.30, GITHUB: 0.30},
    # Skills: code (GitHub) and resume are the strongest evidence.
    "skills": {GITHUB: 0.90, RESUME: 0.85, LINKEDIN: 0.70,
               ATS_JSON: 0.60, RECRUITER_CSV: 0.40, RECRUITER_NOTES: 0.40},
    # Work history: LinkedIn/resume are written for exactly this.
    "experience": {LINKEDIN: 0.90, RESUME: 0.85, ATS_JSON: 0.70,
                   RECRUITER_CSV: 0.40, RECRUITER_NOTES: 0.40, GITHUB: 0.30},
    # Education: resume/LinkedIn state degrees; GitHub almost never.
    "education": {RESUME: 0.90, LINKEDIN: 0.85, ATS_JSON: 0.70,
                  RECRUITER_CSV: 0.40, RECRUITER_NOTES: 0.30, GITHUB: 0.20},
    # Links: each link's home source is most authoritative for it.
    "links": {GITHUB: 0.95, LINKEDIN: 0.80, ATS_JSON: 0.60,
              RESUME: 0.60, RECRUITER_CSV: 0.50, RECRUITER_NOTES: 0.40},
}

# Map every canonical field id to its trust category.
_FIELD_CATEGORY: dict[str, str] = {
    "full_name": "identity",
    "emails": "contact",
    "phones": "contact",
    "location": "location",
    "links.linkedin": "links",
    "links.github": "links",
    "links.portfolio": "links",
    "links.other": "links",
    "headline": "headline",
    "years_experience": "years",
    "skills": "skills",
    "experience": "experience",
    "education": "education",
}

# How the value was obtained -> multiplier. Direct structured field is gold.
_METHOD_FACTOR: dict[Method, float] = {
    "direct_field": 1.0,
    "regex_extract": 0.8,
    "inferred": 0.6,
}


def field_category(field: str) -> str:
    """Trust category for a canonical field id (default 'identity' is neutral)."""
    return _FIELD_CATEGORY.get(field, "identity")


def trust(source: str, field: str) -> float:
    """How much we trust `source` for `field` (field-source affinity)."""
    row = _TRUST.get(field_category(field), {})
    return row.get(source, _DEFAULT_TRUST)


def method_factor(method: Method) -> float:
    return _METHOD_FACTOR.get(method, 0.6)


def base_claim_confidence(source: str, field: str, method: Method) -> float:
    """The score of one claim before agreement/conflict adjustments.

    Used by merge (rank claims to pick a winner) AND confidence (the c_i that
    feed noisy-OR). Both calling the same function is the whole point of this
    module."""
    return trust(source, field) * method_factor(method)


# Deterministic tiebreaker when two claims score equally: prefer this source
# order, then fall back to value sort in merge.py. Fixed list -> stable result.
SOURCE_PRIORITY: list[str] = [
    RECRUITER_CSV, ATS_JSON, LINKEDIN, RESUME, GITHUB, RECRUITER_NOTES,
]


def source_rank(source: str) -> int:
    """Lower = higher priority. Unknown sources sort last."""
    return SOURCE_PRIORITY.index(source) if source in SOURCE_PRIORITY else len(SOURCE_PRIORITY)
