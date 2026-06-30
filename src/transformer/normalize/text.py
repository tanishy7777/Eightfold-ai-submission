"""Name and email cleanup."""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")
# Deliberately loose email check: we only reject obvious non-emails. Strict
# RFC validation rejects many real addresses; "wrong-but-confident" is worse
# than letting an odd-but-plausible address through.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_name(raw: object) -> str | None:
    """Trim and collapse inner whitespace. Case is left as-is on purpose:
    title-casing mangles names like 'McDonald' or 'van der Berg'."""
    if raw is None:
        return None
    name = _WS.sub(" ", str(raw).strip().strip(",;|"))
    return name or None


def clean_email(raw: object) -> str | None:
    """Lower-case and validate shape. Lower-casing matters because email is our
    primary match key — 'Jane@X.com' and 'jane@x.com' must collide, not split
    one person into two profiles."""
    if raw is None:
        return None
    e = str(raw).strip().strip("<>").lower()
    return e if _EMAIL.match(e) else None
