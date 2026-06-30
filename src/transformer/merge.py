"""Merge one candidate's pooled claims into a single CanonicalProfile.

Two field shapes, two strategies:

* SCALAR fields (full_name, headline, years_experience, location, the named
  links) -> pick ONE winner. Winner = highest claim confidence; ties broken
  deterministically (fixed source order, then value sort). All competing claims
  are still recorded in provenance.

* LIST fields (emails, phones, skills, experience, education, links.other) ->
  deduplicated UNION. Two phones are not a conflict, they're two phones; we keep
  both. Skills/experience/education are deduped by identity and back-filled.

Provenance records every (field, source, method) that contributed — including
the losers of a scalar conflict — so every output value is traceable.
"""

from __future__ import annotations

from collections import defaultdict

from . import confidence as conf
from .matching import candidate_id_for
from .models import (
    CanonicalProfile, Claim, EducationItem, ExperienceItem, Links, Location,
    ProvenanceEntry, Skill, SourceRecord,
)
from .normalize import UNKNOWN_SKILL_PENALTY, is_known
from .trust import source_rank

# A provenance entry is collected as a (field, source, method) tuple, then
# deduped + sorted at the end for byte-stable output.
Prov = set


def merge_group(group: list[SourceRecord]) -> CanonicalProfile:
    """Collapse a matched group of source records into one canonical profile."""
    by_field: dict[str, list[Claim]] = defaultdict(list)
    for rec in group:
        for claim in rec.claims:
            by_field[claim.field].append(claim)

    prov: set[tuple[str, str, str]] = set()
    per_field_conf: dict[str, float] = {}

    # --- scalar fields (pick a winner) ---
    full_name, per_field_conf["full_name"] = _pick_scalar(by_field["full_name"], prov, "full_name")
    headline, _ = _pick_scalar(by_field["headline"], prov, "headline")
    years, _ = _pick_scalar(by_field["years_experience"], prov, "years_experience")
    location = _pick_location(by_field["location"], prov)
    links = Links(
        linkedin=_pick_scalar(by_field["links.linkedin"], prov, "links.linkedin")[0],
        github=_pick_scalar(by_field["links.github"], prov, "links.github")[0],
        portfolio=_pick_scalar(by_field["links.portfolio"], prov, "links.portfolio")[0],
        other=_union_strings(by_field["links.other"], prov, "links.other"),
    )

    # --- list fields (deduplicated union) ---
    emails = _union_strings(by_field["emails"], prov, "emails")
    phones = _union_strings(by_field["phones"], prov, "phones")
    per_field_conf["emails"] = conf.presence_confidence(_nonnull(by_field["emails"]))
    per_field_conf["phones"] = conf.presence_confidence(_nonnull(by_field["phones"]))
    skills, per_field_conf["skills"] = _merge_skills(by_field["skills"], prov)
    experience, per_field_conf["experience"] = _merge_experience(by_field["experience"], prov)
    education = _merge_education(by_field["education"], prov)

    provenance = [ProvenanceEntry(field=f, source=s, method=m) for (f, s, m) in sorted(prov)]
    return CanonicalProfile(
        candidate_id=candidate_id_for(group),
        full_name=full_name,
        emails=emails,
        phones=phones,
        location=location,
        links=links,
        headline=headline,
        years_experience=years,
        skills=skills,
        experience=experience,
        education=education,
        provenance=provenance,
        overall_confidence=conf.overall_confidence(per_field_conf),
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #
def _nonnull(claims: list[Claim]) -> list[Claim]:
    return [c for c in claims if c.value is not None]


def _add_prov(prov: set, field: str, claims: list[Claim]) -> None:
    for c in claims:
        prov.add((field, c.source, c.method))


def _norm_key(value) -> str:
    """Equality key for agreement: case-insensitive for strings so 'Jane Doe'
    and 'jane doe' count as the SAME value (agreement), not a conflict."""
    return value.casefold() if isinstance(value, str) else str(value)


def _pick_scalar(claims: list[Claim], prov: set, field: str):
    """Return (winning_value, confidence) for a single-valued field."""
    claims = _nonnull(claims)
    if not claims:
        return (None, 0.0)
    _add_prov(prov, field, claims)
    # Highest confidence wins; ties -> fixed source priority -> value sort.
    ranked = sorted(
        claims,
        key=lambda c: (-conf.claim_confidence(c), source_rank(c.source), str(c.value)),
    )
    winner = ranked[0]
    wkey = _norm_key(winner.value)
    agreeing = [c for c in claims if _norm_key(c.value) == wkey]
    return (winner.value, conf.value_confidence(agreeing, claims))


def _pick_location(claims: list[Claim], prov: set) -> Location:
    """Location is one object claim (we don't stitch sub-fields from different
    sources -> no Frankenstein location). We pick the MOST COMPLETE claim, then
    break ties by trust: a fuller address ("San Francisco, CA, US") is strictly
    more useful than a partial one ("San Francisco Bay Area"), even if the
    partial one came from a slightly more trusted source."""
    claims = _nonnull(claims)
    if not claims:
        return Location()
    _add_prov(prov, "location", claims)
    completeness = lambda c: sum(1 for v in c.value.values() if v)  # noqa: E731
    ranked = sorted(
        claims,
        key=lambda c: (-completeness(c), -conf.claim_confidence(c), source_rank(c.source), str(c.value)),
    )
    w = ranked[0].value
    return Location(city=w.get("city"), region=w.get("region"), country=w.get("country"))


def _union_strings(claims: list[Claim], prov: set, field: str) -> list[str]:
    """Deduped union of string values (emails, phones, links.other), ordered by
    best claim confidence then value. So `phones[0]`/`emails[0]` is the
    most-trusted value (the conflict "winner"), while every value is kept."""
    claims = _nonnull(claims)
    _add_prov(prov, field, claims)
    best: dict[str, float] = {}
    for c in claims:
        score = conf.claim_confidence(c)
        if c.value not in best or score > best[c.value]:
            best[c.value] = score
    return [value for value, _ in sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))]


def _merge_skills(claims: list[Claim], prov: set):
    """Union skills by canonical name. Each skill's confidence = noisy-OR over
    the sources that named it, discounted if it's not a recognized skill."""
    claims = _nonnull(claims)
    _add_prov(prov, "skills", claims)
    by_name: dict[str, list[Claim]] = defaultdict(list)
    for c in claims:
        by_name[c.value].append(c)

    skills: list[Skill] = []
    for name in sorted(by_name):  # sorted -> deterministic output order
        cs = by_name[name]
        score = conf.noisy_or(conf.claim_confidence(c) for c in cs)
        if not is_known(name):
            score *= UNKNOWN_SKILL_PENALTY  # kept, but discounted
        skills.append(Skill(
            name=name,
            confidence=round(min(max(score, 0.0), 1.0), 2),
            sources=sorted({c.source for c in cs}),
        ))
    skills_conf = round(sum(s.confidence for s in skills) / len(skills), 2) if skills else 0.0
    return skills, skills_conf


def _dedup_items(claims: list[Claim], identity_fields, fill_fields):
    """Shared dedupe for experience/education: process claims best-trust-first,
    keep the first item per identity, then back-fill empty fields from weaker
    duplicates (so a date present only in the resume survives)."""
    merged: dict[tuple, dict] = {}
    ordered = sorted(claims, key=lambda c: (-conf.claim_confidence(c), source_rank(c.source)))
    for c in ordered:
        v = c.value
        key = tuple((v.get(f) or "").casefold() for f in identity_fields)
        if key == tuple("" for _ in identity_fields):
            key = (str(v),)  # don't collapse multiple empty-identity items
        if key not in merged:
            merged[key] = dict(v)
        else:
            for f in fill_fields:
                if not merged[key].get(f) and v.get(f):
                    merged[key][f] = v[f]
    return list(merged.values())


def _merge_experience(claims: list[Claim], prov: set):
    claims = _nonnull(claims)
    _add_prov(prov, "experience", claims)
    rows = _dedup_items(claims, ("company", "title"),
                        ("company", "title", "start", "end", "summary"))
    items = [ExperienceItem(**r) for r in rows]
    items.sort(key=lambda e: (e.company or ""))                      # tiebreak
    items.sort(key=lambda e: (e.start or "0000-00"), reverse=True)   # most recent first
    return items, conf.presence_confidence(claims)


def _merge_education(claims: list[Claim], prov: set):
    claims = _nonnull(claims)
    _add_prov(prov, "education", claims)
    rows = _dedup_items(claims, ("institution", "degree"),
                        ("institution", "degree", "field", "end_year"))
    items = [EducationItem(**r) for r in rows]
    items.sort(key=lambda e: (e.institution or ""))
    items.sort(key=lambda e: (e.end_year or 0), reverse=True)
    return items
