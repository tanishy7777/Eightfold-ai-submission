"""Phone -> E.164 (e.g. +14155550100)."""

from __future__ import annotations

import phonenumbers

# A national number like "(415) 555-0100" has no country code, so the parser
# needs a default region to interpret it. Configurable per run; US is the
# documented default. A number written with a leading "+" ignores this.
DEFAULT_REGION = "US"


def to_e164(raw: object, default_region: str = DEFAULT_REGION) -> str | None:
    """Return the E.164 string, or None if the value is not a valid phone.

    We require `is_valid_number` (not just parseable): "call me" or "555-CALL"
    fail and become None rather than a fabricated number. The raw value is
    kept by the caller for provenance."""
    if raw is None:
        return None
    try:
        num = phonenumbers.parse(str(raw), default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
