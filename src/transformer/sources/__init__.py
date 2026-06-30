"""Source adapter registry + lightweight content sniffing.

Two ways to point the pipeline at a file:
  * explicit (CLI flags --csv/--ats/--notes/--github/--resume): always wins;
  * implicit (--input PATH): we sniff the type from extension + a peek inside.

Sniffing is best-effort and deterministic (same file -> same guess). Explicit
flags exist precisely for the cases sniffing can't disambiguate.
"""

from __future__ import annotations

from pathlib import Path

from .ats_json import AtsJsonAdapter
from .base import Adapter, safe_read_json, safe_read_text
from .github import GithubAdapter
from .linkedin import LinkedinAdapter
from .recruiter_csv import RecruiterCsvAdapter
from .recruiter_notes import RecruiterNotesAdapter
from .resume import ResumeAdapter

SOURCE_KEYS = ["csv", "ats", "notes", "github", "linkedin", "resume"]


def get_adapter(key: str) -> Adapter:
    """Instantiate the adapter for a source key."""
    if key == "csv":
        return RecruiterCsvAdapter()
    if key == "ats":
        return AtsJsonAdapter()
    if key == "notes":
        return RecruiterNotesAdapter()
    if key == "resume":
        return ResumeAdapter()
    if key == "github":
        return GithubAdapter()
    if key == "linkedin":
        return LinkedinAdapter()
    raise ValueError(f"unknown source key: {key}")


def sniff_source(path: str) -> str | None:
    """Guess a source key from a path. Returns None if we can't tell."""
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        return "csv"
    if ext in (".pdf", ".md"):
        return "resume"
    if ext == ".json":
        data = safe_read_json(path)
        if isinstance(data, dict):
            # Tell-tale keys distinguish the JSON sources; otherwise assume ATS.
            if any(k in data for k in ("login", "html_url", "public_repos")):
                return "github"
            if any(k in data for k in ("profileUrl", "fullName", "headline")):
                return "linkedin"
        return "ats"
    if ext == ".txt":
        text = safe_read_text(path) or ""
        # A resume has section headings on their OWN line ("EXPERIENCE").
        # Matching a standalone line (not the word buried in prose) keeps short
        # recruiter notes from being mistaken for a resume.
        headings = {"EXPERIENCE", "WORK EXPERIENCE", "EMPLOYMENT", "EDUCATION"}
        if any(line.strip().upper() in headings for line in text.splitlines()):
            return "resume"
        return "notes"
    return None


__all__ = ["Adapter", "SOURCE_KEYS", "get_adapter", "sniff_source"]
