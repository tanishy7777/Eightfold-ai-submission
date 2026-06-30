"""Validate the PROJECTED output against the config's declared schema.

We check the contract the config promised: each field's declared `type` and its
`required` flag. This runs AFTER projection and BEFORE returning, so a config
that asks for something the data can't satisfy fails loudly instead of emitting
a silently-wrong shape.

For the default schema (no explicit fields) the output is a dump of the
CanonicalProfile pydantic model, which is valid by construction — so we only
sanity-check it is an object.
"""

from __future__ import annotations

from .config import OutputConfig


class OutputValidationError(Exception):
    """Raised when projected output violates the requested schema."""


def validate_output(out: dict, config: OutputConfig) -> dict:
    """Return `out` unchanged if valid; otherwise raise OutputValidationError."""
    if not config.fields:
        if not isinstance(out, dict):
            raise OutputValidationError("default output is not an object")
        return out

    errors: list[str] = []
    for spec in config.fields:
        present, value = _lookup(out, spec.path)
        if not present or value is None:
            if spec.required:
                errors.append(f"required field '{spec.path}' is missing or null")
            continue  # absent-but-optional is fine
        if not _type_ok(value, spec.type):
            errors.append(
                f"field '{spec.path}': expected {spec.type}, got {type(value).__name__}"
            )

    if errors:
        raise OutputValidationError("; ".join(errors))
    return out


def _lookup(out: dict, dotted: str) -> tuple[bool, object]:
    """(present?, value) for a possibly-nested output path."""
    cur: object = out
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return (False, None)
    return (True, cur)


def _type_ok(value, declared: str) -> bool:
    if declared == "string":
        return isinstance(value, str)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "string[]":
        return isinstance(value, list) and all(isinstance(x, str) for x in value)
    if declared == "object":
        return isinstance(value, dict)
    if declared == "object[]":
        return isinstance(value, list) and all(isinstance(x, dict) for x in value)
    return True  # unknown declared type -> don't block (forward-compatible)
