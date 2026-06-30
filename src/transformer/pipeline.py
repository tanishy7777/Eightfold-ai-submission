"""Pipeline orchestrator — the readable table of contents of the whole system.

Conceptual stages from the design:
    detect -> extract -> normalize -> match -> merge -> confidence -> project -> validate

In code, detect+extract+normalize happen INSIDE each adapter (an adapter routes
its file, parses it, and calls the pure normalize/ functions as it builds
records). The remaining stages are explicit below:

    build_profiles():   match  -> merge (+confidence)
    project_profiles(): project -> validate

Splitting "build" from "project" matters: profiles are built ONCE (the
expensive part) and can then be projected through many configs cheaply, and
tests can assert on the canonical profile directly.
"""

from __future__ import annotations

import logging

from .config import DEFAULT_CONFIG, OutputConfig
from .matching import cluster
from .merge import merge_group
from .models import CanonicalProfile
from .projection import project
from .sources import get_adapter
from .validation import OutputValidationError, validate_output

log = logging.getLogger("transformer")


def build_profiles(
    sources: list[tuple[str, str]],
) -> list[CanonicalProfile]:
    """sources = [(source_key, path), ...] -> canonical profiles (sorted, stable)."""
    records = []
    for key, path in sources:
        # A bad source returns [] (logged warning), so the run never crashes.
        records.extend(get_adapter(key).extract(path))

    profiles = [merge_group(group) for group in cluster(records)]
    # Drop phantom profiles with no identifying value. A record that contributes
    # only a stray link (e.g. a live GitHub fetch of an unrelated handle that has
    # no public email/name) clusters alone and would otherwise surface as a
    # nameless profile that pollutes output and can never be matched.
    profiles = [p for p in profiles if _has_identity(p)]
    # Deterministic profile order regardless of source/file ordering.
    profiles.sort(key=lambda p: p.candidate_id)
    return profiles


def _has_identity(profile: CanonicalProfile) -> bool:
    """A profile is a real candidate only if it carries at least one identifying
    value: a name, an email, or a phone. Anything else is unidentifiable noise."""
    return bool(profile.full_name or profile.emails or profile.phones)


def project_profiles(
    profiles: list[CanonicalProfile], config: OutputConfig = DEFAULT_CONFIG
) -> list[dict]:
    """Project each profile through the config and validate before returning.

    A profile that fails its contract is skipped with a warning rather than
    crashing the whole run — symmetric with how a garbage *source* is skipped.
    One bad profile must not drop the good ones.
    """
    outputs = []
    for profile in profiles:
        projected = project(profile, config)
        try:
            validate_output(projected, config)  # raises if the shape breaks the contract
        except OutputValidationError as exc:
            log.warning("skipping profile %s: %s", profile.candidate_id, exc)
            continue
        outputs.append(projected)
    return outputs


def run_pipeline(
    sources: list[tuple[str, str]],
    config: OutputConfig = DEFAULT_CONFIG,
) -> list[dict]:
    """End-to-end: messy source files -> list of validated output dicts."""
    return project_profiles(build_profiles(sources), config)
