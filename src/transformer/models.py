"""Data models for the transformer.

Two layers live here, kept deliberately separate:

1. The INTERNAL model (`Claim`, `SourceRecord`) — what a single source said
   about a single person, already translated into our canonical field names.
   This is the messy, partial, per-source view that flows through the pipeline.

2. The CANONICAL OUTPUT model (`CanonicalProfile` and its parts) — the one
   clean profile we emit after merging. This matches the fixed schema in the
   assignment.

Why pydantic: it validates types for free and gives us a single place to
declare the output shape, which we reuse when validating projected output.

Design choice: every canonical field is Optional / defaulted-empty. A sparse
or near-empty profile must never fail to *construct* — robustness rule:
"unknown becomes null, never invented, never crash". Whether a field is
*required* is decided later by the runtime config, not by the model.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# How a value was obtained. Drives the confidence "method factor" later.
#   direct_field  -> read straight from a structured field (most trusted)
#   regex_extract -> pulled out of free text with a pattern (less trusted)
#   inferred      -> derived/guessed from other signals (least trusted)
Method = Literal["direct_field", "regex_extract", "inferred"]


# --------------------------------------------------------------------------- #
# Internal model: one source's claims about one person                        #
# --------------------------------------------------------------------------- #
class Claim(BaseModel):
    """A single piece of evidence: 'source S says field F = value V'.

    `raw` keeps the original string *before* normalization, so an
    un-normalizable value (e.g. phone "call me") is never lost — we record
    that the source had something even when we could not normalize it.
    """

    field: str          # canonical field id, e.g. "full_name", "emails", "links.github"
    value: Any          # normalized value (None if normalization failed)
    method: Method = "direct_field"
    raw: str | None = None
    source: str = ""    # adapter name, e.g. "recruiter_csv"; filled by SourceRecord.add


class SourceRecord(BaseModel):
    """All claims from one source about one candidate (a partial profile).

    We model a source's output as a flat list of claims rather than a half-
    filled profile object. That keeps merge/confidence uniform: every field is
    just "the claims whose .field matches", regardless of which source or how
    many values it had.
    """

    source: str
    claims: list[Claim] = Field(default_factory=list)

    def add(
        self,
        field: str,
        value: Any,
        method: Method = "direct_field",
        raw: str | None = None,
    ) -> None:
        """Record one claim. We keep claims even when value is None so the raw
        attempt survives in provenance; downstream merge ignores None values
        when choosing a winner."""
        self.claims.append(
            Claim(field=field, value=value, method=method, raw=raw, source=self.source)
        )

    def values(self, field: str) -> list[Any]:
        """Non-null values this source claimed for a field (used by matching)."""
        return [c.value for c in self.claims if c.field == field and c.value is not None]


# --------------------------------------------------------------------------- #
# Canonical output model: the one clean profile we emit                       #
# --------------------------------------------------------------------------- #
class Location(BaseModel):
    city: str | None = None
    region: str | None = None
    country: str | None = None  # ISO-3166 alpha-2


class Links(BaseModel):
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    name: str               # canonical skill name
    confidence: float       # [0,1], this skill's own confidence
    sources: list[str]      # sources that mentioned it (sorted, deduped)


class ExperienceItem(BaseModel):
    company: str | None = None
    title: str | None = None
    start: str | None = None   # YYYY-MM
    end: str | None = None     # YYYY-MM, or None for "present"
    summary: str | None = None


class EducationItem(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    end_year: int | None = None


class ProvenanceEntry(BaseModel):
    """Where one field's value came from. Output shape is intentionally tiny
    ({field, source, method}); raw values stay internal to the Claim."""

    field: str
    source: str
    method: Method


class CanonicalProfile(BaseModel):
    """The fixed canonical schema from the assignment. This is our source of
    truth; the projection layer reads from it but never mutates it."""

    candidate_id: str
    full_name: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)        # E.164
    location: Location = Field(default_factory=Location)
    links: Links = Field(default_factory=Links)
    headline: str | None = None
    years_experience: float | None = None
    skills: list[Skill] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)
    overall_confidence: float = 0.0
