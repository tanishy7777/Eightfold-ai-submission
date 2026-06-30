"""Group the SourceRecords that refer to the same candidate.

Match keys are STRONG identifiers only — ones that are 1:1 with a person:
normalized email, E.164 phone, and canonicalized profile URLs (LinkedIn,
GitHub). Records that share ANY key are unioned, so matches are transitive
(A~B via email, B~C via phone => A,B,C are one person) and independent of
input order.

WHY ONLY STRONG KEYS (no name/company/skill/location matching): the brief says
a wrong-but-confident profile is the worst outcome, because a bad value
silently pollutes hiring decisions. Two different people share a name, a city,
an employer, a skill (our own sample has two candidates who both list Python).
Matching on those would fabricate a merged person. So we match only on exact,
identifying keys and accept that we will sometimes *miss* a merge (two profiles
for one person) rather than ever *invent* one.

A profile URL qualifies as strong because a handle (linkedin.com/in/janedoe,
github.com/janedoe) belongs to one person, just like an email — adding it lets
a source that carries no email/phone still link, with negligible over-merge
risk.

Known limitation: a shared generic phone (e.g. a recruiting desk line) could
over-merge. We accept exact-match only and document it rather than adding
fuzzy logic we'd have to defend as safe.
"""

from __future__ import annotations

import hashlib

from .models import SourceRecord
from .normalize import canonical_url

# Strong-identifier link fields safe to match on. Excludes links.portfolio: a
# personal site is usually unique but a shared agency/company domain could
# over-merge, so it stays an attribute, not a key.
_URL_KEY_FIELDS = ("links.linkedin", "links.github")


def _keys(rec: SourceRecord) -> set[tuple[str, str]]:
    """Identifying keys a record exposes: ('email', x), ('phone', y), ('url', z)."""
    keys = {("email", e) for e in rec.values("emails")}
    keys |= {("phone", p) for p in rec.values("phones")}
    for field in _URL_KEY_FIELDS:
        for raw in rec.values(field):
            canon = canonical_url(raw)
            if canon:
                keys.add(("url", canon))
    return keys


def cluster(records: list[SourceRecord]) -> list[list[SourceRecord]]:
    """Partition records into per-candidate groups via union-find.

    A record with no email/phone shares no key, so it forms its own group
    ("stands alone"). Output groups are sorted deterministically so the same
    inputs always yield the same ordering.
    """
    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # path compression
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)  # min-root keeps it deterministic

    # First record to expose a key owns it; later sharers union with that owner.
    key_owner: dict[tuple[str, str], int] = {}
    for i, rec in enumerate(records):
        for key in _keys(rec):
            if key in key_owner:
                union(i, key_owner[key])
            else:
                key_owner[key] = i

    groups: dict[int, list[SourceRecord]] = {}
    for i in range(len(records)):
        groups.setdefault(find(i), []).append(records[i])

    return sorted(groups.values(), key=_group_sort_key)


def _group_sort_key(group: list[SourceRecord]) -> tuple:
    """Stable ordering key for a group (smallest email, then phone, then name)."""
    emails = sorted(e for r in group for e in r.values("emails"))
    phones = sorted(p for r in group for p in r.values("phones"))
    names = sorted(str(n) for r in group for n in r.values("full_name"))
    return (emails[0] if emails else "~",
            phones[0] if phones else "~",
            names[0] if names else "~")


def candidate_id_for(group: list[SourceRecord]) -> str:
    """Deterministic id from the group's identifying keys (no RNG, no clock).

    Same person (same emails/phones) -> same id across runs. Falls back to name,
    then source, so even a keyless record gets a stable id."""
    # Dedup to a SET first: the id must depend only on the distinct key set, not
    # on how many sources happened to repeat a key (else adding a source that
    # shares an email would change the id — a determinism bug).
    keys = sorted({f"{t}:{v}" for r in group for (t, v) in _keys(r)})
    if not keys:
        keys = sorted({f"name:{n}" for r in group for n in r.values("full_name")})
    if not keys:
        keys = sorted({f"src:{r.source}" for r in group})
    digest = hashlib.sha1("|".join(keys).encode("utf-8")).hexdigest()[:12]
    return f"cand_{digest}"
