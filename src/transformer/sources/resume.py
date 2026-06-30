"""Resume (UNSTRUCTURED source): plain-text / Markdown prose, optional PDF.

We parse by simple section headings (SKILLS / EXPERIENCE / EDUCATION). This is
heuristic and tuned for clean, single-column prose — heavy PDF/DOCX layout is
explicitly descoped. PDF support is optional and guarded: if `pypdf` is not
installed, a .pdf resume is skipped with a warning, never a crash.

Methods: the name is a guess (first line) -> `inferred`; emails/phones/skills/
experience/education are pulled by pattern -> `regex_extract`.
"""

from __future__ import annotations

import re

from .. import trust
from ..models import SourceRecord
from ..normalize import (
    canonical_skill, clean_email, clean_name, split_skills, to_e164, to_year, to_year_month,
)
from .base import EMAIL_RE, PHONE_RE, extract_links, log, safe_read_text

# heading text (lower-cased, ':' stripped) -> section name we use internally
_HEADINGS = {
    "skills": "skills", "technical skills": "skills",
    "experience": "experience", "work experience": "experience",
    "employment": "experience",
    "education": "education",
}
# "Title, Company (Start - End)". start/end are non-greedy so the separator
# (dash, en/em-dash, or the word "to") splits them without excluding any
# letters from the date text (e.g. months like "Oct"/"Nov" must still parse).
_EXP = re.compile(
    r"^(?P<title>[^,]+),\s*(?P<company>[^()]+?)\s*\("
    r"(?P<start>.+?)\s*(?:-|–|—|\bto\b)\s*(?P<end>.+?)\)\s*$"
)
_DEGREE = re.compile(
    r"\b(B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?|Ph\.?D\.?|B\.?Tech|M\.?Tech|MBA|"
    r"Bachelor(?:'s)?|Master(?:'s)?)\b\.?",
    re.IGNORECASE,
)
_YEAR_ONLY = re.compile(r"^(19|20)\d{2}$")


def _read(path: str) -> str | None:
    """Read prose from .txt/.md directly; .pdf via pypdf if available."""
    if path.lower().endswith(".pdf"):
        try:
            import pypdf
        except ImportError:
            log.warning("skipping PDF resume %s: pypdf not installed (pip install '.[pdf]')", path)
            return None
        try:
            reader = pypdf.PdfReader(path)
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # any pypdf failure -> skip, don't crash
            log.warning("skipping unreadable PDF %s (%s)", path, exc)
            return None
    return safe_read_text(path)


def _sections(text: str) -> dict[str, list[str]]:
    """Bucket lines under their heading. Lines before any heading go to '_top'."""
    sections: dict[str, list[str]] = {"_top": []}
    current = "_top"
    for line in text.splitlines():
        key = line.strip().lower().rstrip(":")
        if key in _HEADINGS:
            current = _HEADINGS[key]
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


def _parse_education(line: str) -> dict | None:
    parts = [p.strip() for p in line.split(",") if p.strip()]
    degree = field = institution = None
    end_year = None
    leftover: list[str] = []
    for part in parts:
        if end_year is None and _YEAR_ONLY.match(part):
            end_year = int(part)
            continue
        match = _DEGREE.search(part)
        if match and degree is None:
            degree = match.group(0)
            rest = (part[: match.start()] + part[match.end():]).strip(" .,-")
            field = rest or None
            continue
        leftover.append(part)
    if leftover:
        institution = leftover[0]
    if not any([degree, field, institution, end_year]):
        return None
    return {"institution": institution, "degree": degree, "field": field, "end_year": end_year}


class ResumeAdapter:
    source_name = trust.RESUME

    def extract(self, path: str) -> list[SourceRecord]:
        text = _read(path)
        if text is None:
            return []
        rec = SourceRecord(source=self.source_name)
        sections = _sections(text)

        # Name: first non-empty line of the header block (a guess -> inferred).
        for line in sections.get("_top", []):
            if line.strip():
                rec.add("full_name", clean_name(line), "inferred", line.strip())
                break

        for raw in dict.fromkeys(EMAIL_RE.findall(text)):
            rec.add("emails", clean_email(raw), "regex_extract", raw)
        for raw in dict.fromkeys(PHONE_RE.findall(text)):
            e164 = to_e164(raw)
            if e164:
                rec.add("phones", e164, "regex_extract", raw)

        # Profile links (github/linkedin) — the match key that ties this resume
        # to an email-less GitHub API record for the same person.
        for field, url, raw in extract_links(text):
            rec.add(field, url, "regex_extract", raw)

        for line in sections.get("skills", []):
            for tok in split_skills(line):
                rec.add("skills", canonical_skill(tok), "regex_extract", tok)

        for line in sections.get("experience", []):
            match = _EXP.match(line.strip())
            if match:
                rec.add(
                    "experience",
                    {
                        "company": clean_name(match["company"]),
                        "title": clean_name(match["title"]),
                        "start": to_year_month(match["start"]),
                        "end": to_year_month(match["end"]),  # "Present" -> None
                        "summary": None,
                    },
                    "regex_extract",
                    line.strip(),
                )

        for line in sections.get("education", []):
            if not line.strip():
                continue
            edu = _parse_education(line)
            if edu:
                rec.add("education", edu, "regex_extract", line.strip())

        return [rec] if rec.claims else []
