"""URL -> a canonical form used as an identity match key.

A profile URL (LinkedIn, GitHub) is a strong identifier: one handle == one
person, like an email or phone. But two sources write the same handle many
ways ("https://www.LinkedIn.com/in/Jane/", "linkedin.com/in/jane"). To union
records on it we first collapse those to one canonical string.

Same contract as the other normalizers: never raises, returns None on garbage.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def canonical_url(raw: object) -> str | None:
    """Canonicalize a URL for matching: drop scheme/`www.`/query/fragment,
    lowercase, strip trailing slash. Returns None if there's nothing usable.

    Examples:
      https://www.LinkedIn.com/in/Jane/?utm=x  -> linkedin.com/in/jane
      linkedin.com/in/jane                     -> linkedin.com/in/jane
    """
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    # Without a scheme, urlsplit puts the host in `path`, not `netloc`. Add a
    # placeholder scheme so host and path parse consistently either way.
    if "://" not in text:
        text = "//" + text
    parts = urlsplit(text)
    host = parts.netloc.removeprefix("www.")
    path = parts.path.rstrip("/")
    canon = (host + path).strip("/")
    return canon or None
