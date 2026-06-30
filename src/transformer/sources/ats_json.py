"""ATS JSON blob (STRUCTURED source) with its OWN field names.

The whole point of this adapter is the REMAP: the ATS calls things
"candidateName", "primaryEmail", "skillSet", ... and we translate every one of
those to our canonical field via an explicit table (FIELD_MAP). Showing that
table is the deliverable here.

Input may be a single object, a list of objects, or {"candidates": [...]}.
"""

from __future__ import annotations

from .. import trust
from ..models import SourceRecord
from ..normalize import (
    canonical_skill, clean_email, clean_name, country_to_iso2, split_skills, to_e164,
)
from .base import safe_read_json

# ---- THE MAPPING TABLE: their field name -> our canonical field id ---------- #
# Internal sentinels "_company"/"_title" are combined into one experience item.
FIELD_MAP: dict[str, str] = {
    "candidateName": "full_name", "name": "full_name", "fullName": "full_name",
    "primaryEmail": "emails", "email": "emails", "emailAddress": "emails",
    "mobile": "phones", "phone": "phones", "phoneNumber": "phones",
    "city": "location.city", "state": "location.region", "region": "location.region",
    "country": "location.country",
    "currentTitle": "_title", "jobTitle": "_title", "title": "_title",
    "employer": "_company", "company": "_company", "currentCompany": "_company",
    "skills": "skills", "skillSet": "skills",
    "linkedinUrl": "links.linkedin", "linkedin": "links.linkedin",
    "githubUrl": "links.github", "github": "links.github",
    "portfolioUrl": "links.portfolio", "website": "links.portfolio",
    "yearsOfExperience": "years_experience", "yearsExp": "years_experience",
    "headline": "headline", "summary": "headline",
}


def _to_number(value: object) -> float | None:
    """Pull a number out of e.g. 7, '7', '7 years'. None if not numeric."""
    try:
        return float(str(value).strip().split()[0])
    except (ValueError, IndexError):
        return None


class AtsJsonAdapter:
    source_name = trust.ATS_JSON

    def extract(self, path: str) -> list[SourceRecord]:
        data = safe_read_json(path)
        if data is None:
            return []
        if isinstance(data, dict):
            people = data.get("candidates", [data])
        elif isinstance(data, list):
            people = data
        else:
            return []

        records: list[SourceRecord] = []
        for person in people:
            if not isinstance(person, dict):
                continue
            records.append(self._one(person))
        return [r for r in records if r.claims]

    def _one(self, person: dict) -> SourceRecord:
        rec = SourceRecord(source=self.source_name)
        loc = {"city": None, "region": None, "country": None}
        company = title = None

        for key, value in person.items():
            our = FIELD_MAP.get(key)
            if our is None or value in (None, "", []):
                continue
            raw = str(value)
            if our == "full_name":
                rec.add("full_name", clean_name(value), "direct_field", raw)
            elif our == "emails":
                rec.add("emails", clean_email(value), "direct_field", raw)
            elif our == "phones":
                rec.add("phones", to_e164(value), "direct_field", raw)
            elif our == "location.city":
                loc["city"] = clean_name(value)
            elif our == "location.region":
                loc["region"] = clean_name(value)
            elif our == "location.country":
                loc["country"] = country_to_iso2(value)
            elif our == "_company":
                company = clean_name(value)
            elif our == "_title":
                title = clean_name(value)
            elif our == "skills":
                tokens = value if isinstance(value, list) else split_skills(value)
                for tok in tokens:
                    rec.add("skills", canonical_skill(tok), "direct_field", str(tok))
            elif our == "years_experience":
                rec.add("years_experience", _to_number(value), "direct_field", raw)
            elif our == "headline":
                rec.add("headline", str(value).strip() or None, "direct_field", raw)
            elif our.startswith("links."):
                rec.add(our, raw.strip() or None, "direct_field", raw)

        if any(loc.values()):
            rec.add("location", loc, "direct_field")
        if company or title:
            rec.add(
                "experience",
                {"company": company, "title": title,
                 "start": None, "end": None, "summary": None},
                "direct_field",
            )
        return rec
