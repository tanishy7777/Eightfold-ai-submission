"""Recruiter CSV export (STRUCTURED source).

Rows of (name, email, phone, current_company, title). Header names vary a bit
between exports, so we resolve each column to one of our fields via an alias
set. One row -> one SourceRecord. Everything is a `direct_field` (it came from
a labelled column), which is the most trusted method.
"""

from __future__ import annotations

import csv
import io

from .. import trust
from ..models import SourceRecord
from ..normalize import clean_email, clean_name, to_e164
from .base import log, safe_read_text

# our field  <-  accepted header names (compared lower-cased, spaces/underscores
# stripped). Explicit so a surprise header never maps silently to the wrong field.
_HEADER_ALIASES: dict[str, set[str]] = {
    "full_name": {"name", "fullname", "candidate", "candidatename"},
    "emails": {"email", "emailaddress", "e-mail", "mail"},
    "phones": {"phone", "phonenumber", "mobile", "cell", "contact"},
    "company": {"currentcompany", "company", "employer"},
    "title": {"title", "currenttitle", "role", "jobtitle", "position"},
}


def _resolve_header(header: str) -> str | None:
    key = header.strip().lower().replace("_", "").replace(" ", "")
    for our_field, aliases in _HEADER_ALIASES.items():
        if key in aliases:
            return our_field
    return None


class RecruiterCsvAdapter:
    source_name = trust.RECRUITER_CSV

    def extract(self, path: str) -> list[SourceRecord]:
        text = safe_read_text(path)
        if text is None:
            return []
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            log.warning("skipping source: empty CSV %s", path)
            return []

        colmap = {h: _resolve_header(h) for h in reader.fieldnames}
        records: list[SourceRecord] = []
        for row in reader:
            rec = SourceRecord(source=self.source_name)
            company = title = None
            for header, our in colmap.items():
                raw = (row.get(header) or "").strip()
                if not our or not raw:
                    continue
                if our == "full_name":
                    rec.add("full_name", clean_name(raw), "direct_field", raw)
                elif our == "emails":
                    rec.add("emails", clean_email(raw), "direct_field", raw)
                elif our == "phones":
                    rec.add("phones", to_e164(raw), "direct_field", raw)
                elif our == "company":
                    company = clean_name(raw)
                elif our == "title":
                    title = clean_name(raw)
            # A CSV row's company+title is a (dateless) experience entry.
            if company or title:
                rec.add(
                    "experience",
                    {"company": company, "title": title,
                     "start": None, "end": None, "summary": None},
                    "direct_field",
                )
            if rec.claims:
                records.append(rec)
        return records
