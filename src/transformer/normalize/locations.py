"""Location parsing: country -> ISO-3166 alpha-2, plus a "City, Region, Country"
splitter.

The alias map is intentionally small and explicit (the common cases in our
data). An unrecognized country returns None — we never guess a code, because a
wrong country silently corrupts downstream filtering.
"""

from __future__ import annotations

# Dots are stripped before lookup, so "U.S.A." -> "usa" matches.
_ISO2: dict[str, str] = {
    "united states": "US", "united states of america": "US", "usa": "US",
    "us": "US", "america": "US",
    "india": "IN",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB", "britain": "GB",
    "england": "GB",
    "canada": "CA",
    "germany": "DE", "deutschland": "DE",
    "france": "FR",
    "spain": "ES", "italy": "IT", "netherlands": "NL", "ireland": "IE",
    "australia": "AU", "singapore": "SG", "japan": "JP", "china": "CN",
    "brazil": "BR", "mexico": "MX",
}
_VALID_CODES = set(_ISO2.values())


def country_to_iso2(raw: object) -> str | None:
    """Map a country name (or an already-correct 2-letter code) to ISO alpha-2."""
    if raw is None:
        return None
    s = str(raw).strip().replace(".", "").lower()
    if s in _ISO2:
        return _ISO2[s]
    up = s.upper()
    if len(up) == 2 and up in _VALID_CODES:  # already a code we recognize
        return up
    return None


def parse_location_string(raw: object) -> tuple[str | None, str | None, str | None]:
    """Heuristic split of "City, Region, Country" -> (city, region, country_iso).

    Rule: if the last comma-part is a recognizable country, peel it off as the
    ISO country; the remaining parts fill city then region. We do NOT ISO-ify
    the region (schema keeps region as free text). Anything we cannot place is
    left None rather than misfiled."""
    parts = [p.strip() for p in str(raw or "").split(",") if p.strip()]
    if not parts:
        return (None, None, None)
    country = country_to_iso2(parts[-1])
    rest = parts[:-1] if country else parts
    city = rest[0] if len(rest) >= 1 else None
    region = rest[1] if len(rest) >= 2 else None
    return (city, region, country)
