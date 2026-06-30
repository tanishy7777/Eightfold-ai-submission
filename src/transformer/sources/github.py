"""GitHub profile (UNSTRUCTURED source).

Accepts a file path (cached JSON fixture), a GitHub profile URL
(https://github.com/username), or a bare username — the adapter auto-detects
which form was given and routes accordingly. Network errors degrade to an empty
result so the run never crashes.

Field methods reflect how solid each signal is:
  * name, bio, html_url  -> direct_field (literal profile fields)
  * languages -> skills  -> inferred (a repo's language is a proxy for a skill,
    not a stated skill), so these get the lowest method factor.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from .. import trust
from ..models import SourceRecord
from ..normalize import canonical_skill, clean_email, clean_name, parse_location_string
from .base import log, safe_read_json

_GITHUB_URL_PREFIX = "https://github.com/"
_GITHUB_API_PREFIX = "https://api.github.com/users/"


def _fetch_live(username: str) -> dict | None:
    """Minimal, guarded live fetch of the public user profile.
    Network errors degrade to None -> the source is simply skipped."""
    url = f"{_GITHUB_API_PREFIX}{username}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 (https only)
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # broad on purpose: any network/parse failure = skip
        log.warning("skipping github live fetch for %s (%s)", username, exc)
        return None


def _resolve(path: str) -> dict | None:
    """Route path to live fetch or fixture read based on its form."""
    if path.startswith(_GITHUB_URL_PREFIX):
        username = path.rstrip("/").removeprefix(_GITHUB_URL_PREFIX).split("/")[0]
        return _fetch_live(username)
    if path.startswith(_GITHUB_API_PREFIX):
        username = path.rstrip("/").removeprefix(_GITHUB_API_PREFIX).split("/")[0]
        return _fetch_live(username)
    # Bare username: no path separators, no file extension, file doesn't exist.
    p = Path(path)
    if not p.exists() and "/" not in path and "." not in path:
        return _fetch_live(path)
    return safe_read_json(path)


class GithubAdapter:
    source_name = trust.GITHUB

    def extract(self, path: str) -> list[SourceRecord]:
        data = _resolve(path)
        if not isinstance(data, dict):
            return []

        rec = SourceRecord(source=self.source_name)
        # A public email lets this profile MATCH the same person from other
        # sources (GitHub has no phone). Without it, the record stands alone.
        if data.get("email"):
            rec.add("emails", clean_email(data["email"]), "direct_field", str(data["email"]))
        if data.get("name"):
            rec.add("full_name", clean_name(data["name"]), "direct_field", str(data["name"]))
        if data.get("bio"):
            rec.add("headline", str(data["bio"]).strip(), "direct_field", str(data["bio"]))
        if data.get("html_url"):
            rec.add("links.github", str(data["html_url"]).strip(), "direct_field", str(data["html_url"]))
        if data.get("blog"):
            rec.add("links.portfolio", str(data["blog"]).strip(), "direct_field", str(data["blog"]))
        if data.get("location"):
            city, region, country = parse_location_string(data["location"])
            rec.add("location", {"city": city, "region": region, "country": country},
                    "inferred", str(data["location"]))
        # languages -> skills, marked inferred (a proxy, not a stated skill).
        for lang in data.get("languages", []):
            rec.add("skills", canonical_skill(lang), "inferred", str(lang))

        return [rec] if rec.claims else []
