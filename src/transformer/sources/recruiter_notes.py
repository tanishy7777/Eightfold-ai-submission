"""Recruiter notes (.txt) — UNSTRUCTURED free text.

We only pull out what we can find with confident, explicit patterns: emails,
phones, an optional "Name:" / "Skills:" / "Years:" label. Everything extracted
here is method `regex_extract` (weaker than a structured field). We do NOT try
to guess a name from arbitrary prose — guessing identity risks a wrong merge.
"""

from __future__ import annotations

import re

from .. import trust
from ..models import SourceRecord
from ..normalize import canonical_skill, clean_email, clean_name, split_skills, to_e164
from .base import EMAIL_RE, PHONE_RE, extract_links, safe_read_text

_NAME_LABEL = re.compile(r"^\s*name\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_SKILLS_LABEL = re.compile(r"skills?\s*[:\-]\s*(.+)", re.IGNORECASE)
_YEARS = re.compile(r"(\d{1,2})\+?\s*(?:years|yrs)\b", re.IGNORECASE)


class RecruiterNotesAdapter:
    source_name = trust.RECRUITER_NOTES

    def extract(self, path: str) -> list[SourceRecord]:
        text = safe_read_text(path)
        if text is None:
            return []
        rec = SourceRecord(source=self.source_name)

        # Email is the strongest identity signal in notes -> still regex method.
        for raw in dict.fromkeys(EMAIL_RE.findall(text)):  # dedupe, keep order
            rec.add("emails", clean_email(raw), "regex_extract", raw)
        for raw in dict.fromkeys(PHONE_RE.findall(text)):
            e164 = to_e164(raw)
            if e164:  # only record phone-shaped strings that actually validate
                rec.add("phones", e164, "regex_extract", raw)

        # Profile links mentioned in the note become strong match keys too.
        for field, url, raw in extract_links(text):
            rec.add(field, url, "regex_extract", raw)

        name_m = _NAME_LABEL.search(text)
        if name_m:
            raw = name_m.group(1).strip()
            rec.add("full_name", clean_name(raw), "regex_extract", raw)

        skills_m = _SKILLS_LABEL.search(text)
        if skills_m:
            for tok in split_skills(skills_m.group(1)):
                rec.add("skills", canonical_skill(tok), "regex_extract", tok)

        years_m = _YEARS.search(text)
        if years_m:
            rec.add("years_experience", float(years_m.group(1)), "regex_extract", years_m.group(0))

        return [rec] if rec.claims else []
