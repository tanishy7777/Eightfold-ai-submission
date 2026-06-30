"""LinkedIn profile (UNSTRUCTURED source).

Accepts a file path (cached JSON export) or a LinkedIn profile URL
(https://linkedin.com/in/...). For URLs, the adapter attempts a live HTTP
fetch and extracts schema.org/Person JSON-LD from the page. LinkedIn blocks
most unauthenticated requests — the fetch degrades gracefully to an empty
result rather than crashing the run.

LinkedIn is the strongest source for headline / experience / education (trust.py),
so those fields tend to win when a profile is present.
"""

from __future__ import annotations

import json
import re
import urllib.request

from .. import trust
from ..models import SourceRecord
from ..normalize import (
    canonical_skill, clean_email, clean_name, parse_location_string, to_year, to_year_month,
)
from .base import log, safe_read_json

_LINKEDIN_URL_PREFIX = "https://www.linkedin.com/"
_LINKEDIN_URL_PREFIX_SHORT = "https://linkedin.com/"
_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _fetch_live(url: str) -> dict | None:
    """Best-effort live fetch from a LinkedIn profile URL.

    Parses schema.org/Person JSON-LD embedded in the page. LinkedIn blocks most
    unauthenticated requests, so the result is often minimal or None.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; candidate-transformer/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 (https only)
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        log.warning("linkedin live fetch failed for %s (%s)", url, exc)
        return None

    for m in _JSONLD_RE.finditer(html):
        try:
            obj = json.loads(m.group(1))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        types = obj.get("@type", "")
        if "Person" not in (types if isinstance(types, str) else " ".join(types)):
            continue
        addr = obj.get("address") or {}
        location_parts = [
            addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")
        ] if isinstance(addr, dict) else []
        location_str = ", ".join(p for p in location_parts if p) or None
        return {
            "fullName": obj.get("name"),
            "headline": obj.get("description") or obj.get("jobTitle"),
            "profileUrl": url,
            "location": location_str,
            "skills": [],
            "experience": [],
            "education": [],
        }

    log.warning(
        "linkedin: no parseable structured data at %s "
        "(LinkedIn likely blocked unauthenticated access)",
        url,
    )
    return None


class LinkedinAdapter:
    source_name = trust.LINKEDIN

    def extract(self, path: str) -> list[SourceRecord]:
        if path.startswith(_LINKEDIN_URL_PREFIX) or path.startswith(_LINKEDIN_URL_PREFIX_SHORT):
            data = _fetch_live(path)
        else:
            data = safe_read_json(path)
        if not isinstance(data, dict):
            return []

        rec = SourceRecord(source=self.source_name)
        if data.get("email"):
            rec.add("emails", clean_email(data["email"]), "direct_field", str(data["email"]))
        if data.get("fullName"):
            rec.add("full_name", clean_name(data["fullName"]), "direct_field", str(data["fullName"]))
        if data.get("headline"):
            rec.add("headline", str(data["headline"]).strip(), "direct_field", str(data["headline"]))
        if data.get("profileUrl"):
            rec.add("links.linkedin", str(data["profileUrl"]).strip(), "direct_field", str(data["profileUrl"]))
        if data.get("location"):
            city, region, country = parse_location_string(data["location"])
            rec.add("location", {"city": city, "region": region, "country": country},
                    "direct_field", str(data["location"]))

        for skill in data.get("skills", []):
            rec.add("skills", canonical_skill(skill), "direct_field", str(skill))

        for exp in data.get("experience", []):
            if not isinstance(exp, dict):
                continue
            rec.add("experience", {
                "company": clean_name(exp.get("company")),
                "title": clean_name(exp.get("title")),
                "start": to_year_month(exp.get("start")),
                "end": to_year_month(exp.get("end")),     # "Present" -> None
                "summary": (str(exp["summary"]).strip() if exp.get("summary") else None),
            }, "direct_field", str(exp))

        for edu in data.get("education", []):
            if not isinstance(edu, dict):
                continue
            rec.add("education", {
                "institution": clean_name(edu.get("school") or edu.get("institution")),
                "degree": clean_name(edu.get("degree")),
                "field": clean_name(edu.get("field")),
                "end_year": to_year(edu.get("end") or edu.get("end_year")),
            }, "direct_field", str(edu))

        return [rec] if rec.claims else []
