"""Confidence math: noisy-OR reinforcement, conflict penalty, overall mean."""

from transformer import confidence as conf
from transformer.models import Claim


def _claim(source, field, method="direct_field", value="x"):
    return Claim(field=field, value=value, method=method, source=source)


def test_noisy_or_reinforces():
    # Two 0.5 sources agreeing beat either alone: 1 - 0.5*0.5 = 0.75.
    assert conf.noisy_or([0.5, 0.5]) == 0.75
    assert conf.noisy_or([]) == 0.0


def test_value_confidence_no_conflict():
    a = _claim("ats_json", "emails")          # trust 0.9 * 1.0 = 0.9
    assert conf.value_confidence([a], [a]) == 0.9


def test_value_confidence_conflict_penalty():
    a = _claim("ats_json", "emails", value="A")     # winner, 0.9
    b = _claim("ats_json", "emails", value="B")     # disagrees
    # disagree_fraction = 1/2 -> 0.9 * (1 - 0.5*0.5) = 0.675 -> 0.68
    assert conf.value_confidence([a], [a, b]) == 0.68


def test_overall_confidence_missing_fields_contribute_zero():
    # Only 2 of 5 core fields known -> (0.9 + 0.9 + 0 + 0 + 0)/5 = 0.36.
    per_field = {"full_name": 0.9, "emails": 0.9}
    assert conf.overall_confidence(per_field) == 0.36
