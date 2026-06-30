"""Adapter contract + robust file readers shared by every source.

Robustness rule (from the brief): a missing or garbage source must NOT crash
the run. So the readers here catch their own errors, log a warning, and return
None; an adapter that gets None simply returns an empty list of records. The
pipeline then continues with whatever other sources succeeded.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..models import SourceRecord

log = logging.getLogger("transformer")

# Shared extraction patterns for the free-text adapters (notes, resume).
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}")
# Permissive phone candidate; to_e164() does the real validation afterwards.
PHONE_RE = re.compile(r"\+?\d[\d\-\.\s()]{7,}\d")

# Profile-URL patterns. We capture the HANDLE (first path segment) and rebuild
# the canonical profile URL, so a deep/repo link (github.com/jane/repo) or a
# www/https variant still resolves to the one person. These feed links.github /
# links.linkedin claims, which matching uses as strong keys — the path by which
# an email-less GitHub API record links to the candidate's resume/notes.
LINKEDIN_RE = re.compile(r"linkedin\.com/in/([A-Za-z0-9_-]+)", re.IGNORECASE)
GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9-]+)", re.IGNORECASE)


def extract_links(text: str) -> list[tuple[str, str, str]]:
    """Find profile URLs in free text -> [(canonical_field, url, raw_handle), ...].

    Order-preserving and deduped. The URL is rebuilt from the handle so that
    canonical_url() in matching produces the same key as the GitHub/LinkedIn
    adapters' own html_url/profileUrl."""
    links: list[tuple[str, str, str]] = []
    for handle in dict.fromkeys(LINKEDIN_RE.findall(text)):
        links.append(("links.linkedin", f"https://linkedin.com/in/{handle}", handle))
    for handle in dict.fromkeys(GITHUB_RE.findall(text)):
        links.append(("links.github", f"https://github.com/{handle}", handle))
    return links


@runtime_checkable
class Adapter(Protocol):
    """Every source adapter looks the same to the pipeline: a name + extract().
    Adding a new source means writing one class that satisfies this."""

    source_name: str

    def extract(self, path: str) -> list[SourceRecord]:
        ...


def safe_read_text(path: str) -> str | None:
    """Read a text file, or warn + return None (missing/unreadable -> skip)."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("skipping source: cannot read %s (%s)", path, exc)
        return None


def safe_read_json(path: str) -> Any | None:
    """Parse a JSON file, or warn + return None (missing/broken JSON -> skip)."""
    text = safe_read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("skipping source: invalid JSON in %s (%s)", path, exc)
        return None
