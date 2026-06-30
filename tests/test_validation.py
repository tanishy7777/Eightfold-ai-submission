"""Validation of projected output against the config's declared schema."""

import pytest

from transformer.config import FieldSpec, OutputConfig
from transformer.validation import OutputValidationError, validate_output


def _cfg(*fields):
    return OutputConfig(fields=list(fields))


def test_valid_output_passes():
    cfg = _cfg(
        FieldSpec(path="name", type="string", required=True),
        FieldSpec(path="age", type="number"),
        FieldSpec(path="skills", type="string[]"),
    )
    out = {"name": "Jane", "age": 7, "skills": ["Python"]}
    assert validate_output(out, cfg) == out


def test_required_missing_raises():
    cfg = _cfg(FieldSpec(path="name", type="string", required=True))
    with pytest.raises(OutputValidationError):
        validate_output({}, cfg)


def test_required_null_raises():
    cfg = _cfg(FieldSpec(path="name", type="string", required=True))
    with pytest.raises(OutputValidationError):
        validate_output({"name": None}, cfg)


def test_wrong_type_raises():
    cfg = _cfg(FieldSpec(path="name", type="string"))
    with pytest.raises(OutputValidationError):
        validate_output({"name": 123}, cfg)


def test_string_array_type_checked():
    cfg = _cfg(FieldSpec(path="skills", type="string[]"))
    validate_output({"skills": ["a", "b"]}, cfg)  # ok
    with pytest.raises(OutputValidationError):
        validate_output({"skills": [1, 2]}, cfg)


def test_optional_absent_is_fine():
    cfg = _cfg(FieldSpec(path="age", type="number"))  # not required
    assert validate_output({}, cfg) == {}
