"""Confidence scoring.

The whole model in three rules, kept deliberately simple so it can be explained
on camera:

1. A single claim's confidence = trust(source, field) x method_factor(method).
   (Both come from trust.py — see base_claim_confidence.)

2. When several sources AGREE on a value, agreement should *reinforce* belief.
   We combine them with noisy-OR: c = 1 - Π(1 - c_i). Two so-so sources that
   agree beat either one alone, but it never reaches 1.

3. When sources CONFLICT, belief should drop. We keep the winner's combined
   confidence and multiply by (1 - 0.5 * disagree_fraction): the more competing
   claims we overruled, the larger the penalty (up to halving at total conflict).

overall_confidence is an equal-weighted mean over the core fields; a missing
field contributes 0 (honest about gaps). Everything clamps to [0,1], 2 dp.
"""

from __future__ import annotations

from typing import Iterable

from .models import Claim
from .trust import base_claim_confidence

# Fields that define "do we actually know this person?" Equal weights are a
# deliberate simplicity choice — trivial to justify and to re-tune later.
CORE_FIELDS = ["full_name", "emails", "phones", "skills", "experience"]


def claim_confidence(claim: Claim) -> float:
    """Score of one claim before agreement/conflict adjustments."""
    return base_claim_confidence(claim.source, claim.field, claim.method)


def noisy_or(confidences: Iterable[float]) -> float:
    """1 - Π(1 - c_i): independent sources agreeing reinforce each other."""
    product = 1.0
    for c in confidences:
        product *= (1.0 - c)
    return 1.0 - product


def value_confidence(agreeing: list[Claim], competitors: list[Claim]) -> float:
    """Confidence in a chosen scalar value: reinforce agreement, penalize conflict."""
    if not agreeing:
        return 0.0
    agreed = noisy_or(claim_confidence(c) for c in agreeing)
    total = len(competitors)
    disagree_fraction = (total - len(agreeing)) / total if total else 0.0
    return _clamp_round(agreed * (1.0 - 0.5 * disagree_fraction))


def presence_confidence(claims: list[Claim]) -> float:
    """For list fields (emails/phones/...): how sure we are the field is
    populated at all — noisy-OR over every contributing claim."""
    if not claims:
        return 0.0
    return _clamp_round(noisy_or(claim_confidence(c) for c in claims))


def overall_confidence(per_field: dict[str, float]) -> float:
    """Equal-weighted mean over CORE_FIELDS; missing field contributes 0."""
    values = [per_field.get(f, 0.0) for f in CORE_FIELDS]
    return _clamp_round(sum(values) / len(CORE_FIELDS))


def _clamp_round(x: float) -> float:
    return round(min(max(x, 0.0), 1.0), 2)
