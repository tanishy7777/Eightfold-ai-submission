"""Projection layer: canonical profile + config -> the requested output shape.

This layer is strictly READ-ONLY over the canonical record (we operate on a
dump of it). It never changes how a value was computed — it only selects,
renames, re-normalizes, and reshapes. That clean separation is why the same
engine serves any number of output schemas with no code changes.

Path DSL for a field's "from":
  dotted.path        -> nested lookup           ("location.country")
  name[0]            -> index into a list        ("emails[0]")
  name[].child       -> map over a list, pull child from each ("skills[].name")
These compose: "experience[0].company".
"""

from __future__ import annotations

import re

from .config import OutputConfig
from .models import CanonicalProfile
from .normalize import canonical_skill, country_to_iso2, to_e164, to_year_month

_MISSING = object()  # distinct from None: "path not found" vs "value is null"
_TOKEN = re.compile(r"^([A-Za-z0-9_]+)(?:\[(\d+)\]|(\[\]))?$")

# normalize name -> function applied at projection time
_NORMALIZERS = {
    "E164": to_e164,
    "canonical": canonical_skill,
    "iso2": country_to_iso2,
    "yyyy_mm": to_year_month,
}


class ProjectionError(Exception):
    """Raised for a bad path/normalize, or on_missing == 'error'."""


def project(profile: CanonicalProfile, config: OutputConfig) -> dict:
    """Build the output dict described by `config` from `profile`."""
    data = profile.model_dump()
    if not config.fields:
        return _project_full(data, config)

    out: dict = {}
    for spec in config.fields:
        value = _resolve(data, _tokenize(spec.source_path))
        if value is _MISSING:
            value = None
        if spec.normalize and value is not None:
            value = _apply_normalize(value, spec.normalize)

        if _is_missing(value):
            policy = spec.on_missing or config.on_missing
            if policy == "omit":
                continue
            if policy == "error":
                raise ProjectionError(
                    f"missing value for '{spec.path}' (from '{spec.source_path}') "
                    f"and on_missing='error'"
                )
            value = None  # policy == "null"

        _set_path(out, spec.path, value)

    # Toggles also apply to a custom shape: attach the profile-level confidence
    # and/or full provenance alongside the selected fields (matches the example
    # config, which selects fields AND sets include_confidence).
    if config.include_confidence:
        out["overall_confidence"] = data.get("overall_confidence")
    if config.include_provenance:
        out["provenance"] = data.get("provenance")
    return out


def _project_full(data: dict, config: OutputConfig) -> dict:
    """Default schema: the full canonical profile, with toggles applied.
    provenance/sources are 'where it came from'; confidence is 'how sure'."""
    if not config.include_provenance:
        data.pop("provenance", None)
        for skill in data.get("skills", []):
            skill.pop("sources", None)
    if not config.include_confidence:
        data.pop("overall_confidence", None)
        for skill in data.get("skills", []):
            skill.pop("confidence", None)
    return data


# --- path DSL ------------------------------------------------------------- #
def _tokenize(path: str) -> list[tuple[str, str, int | None]]:
    """'skills[].name' -> [('skills','map',None), ('name','plain',None)]."""
    tokens: list[tuple[str, str, int | None]] = []
    for part in path.split("."):
        m = _TOKEN.match(part)
        if not m:
            raise ProjectionError(f"bad path segment '{part}' in '{path}'")
        name, index, mapped = m.group(1), m.group(2), m.group(3)
        if index is not None:
            tokens.append((name, "index", int(index)))
        elif mapped is not None:
            tokens.append((name, "map", None))
        else:
            tokens.append((name, "plain", None))
    return tokens


def _resolve(value, tokens):
    """Walk the token list. Returns the value, a list (for map), or _MISSING."""
    if not tokens:
        return value
    name, kind, arg = tokens[0]
    rest = tokens[1:]
    child = value.get(name, _MISSING) if isinstance(value, dict) else _MISSING
    if child is _MISSING:
        return _MISSING

    if kind == "plain":
        return _resolve(child, rest)
    if kind == "index":
        if isinstance(child, (list, tuple)) and -len(child) <= arg < len(child):
            return _resolve(child[arg], rest)
        return _MISSING
    if kind == "map":
        if not isinstance(child, (list, tuple)):
            return _MISSING
        collected = []
        for item in child:
            r = _resolve(item, rest)
            if r is not _MISSING and r is not None:
                collected.append(r)
        return collected
    return _MISSING


def _apply_normalize(value, name: str):
    fn = _NORMALIZERS.get(name)
    if fn is None:
        raise ProjectionError(f"unknown normalize '{name}'")
    if isinstance(value, list):
        return [fn(v) for v in value]
    return fn(value)


def _is_missing(value) -> bool:
    """Absent for output purposes: null, empty list, or empty string."""
    return value is None or value == [] or value == ""


def _set_path(out: dict, dotted: str, value) -> None:
    """Set a (possibly nested) output path, creating intermediate dicts."""
    parts = dotted.split(".")
    cur = out
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value
