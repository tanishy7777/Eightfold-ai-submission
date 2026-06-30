"""Projection: path DSL, normalize override, on_missing policies, rename."""

import pytest

from transformer.config import FieldSpec, OutputConfig
from transformer.models import CanonicalProfile, Links, Location, Skill
from transformer.projection import ProjectionError, project


def _profile():
    return CanonicalProfile(
        candidate_id="c1",
        full_name="Jane",
        emails=["a@b.com", "c@d.com"],
        phones=["+14155550142"],
        location=Location(country="US"),
        links=Links(github="https://github.com/jane", other=["https://t.co/x"]),
        skills=[Skill(name="Python", confidence=0.9, sources=["ats_json"])],
        overall_confidence=0.5,
    )


def _spec(path, **kw):
    return FieldSpec(path=path, **kw)


def test_rename_index_map_and_dotted_paths():
    cfg = OutputConfig(fields=[
        _spec("name", **{"from": "full_name"}, type="string"),
        _spec("email", **{"from": "emails[0]"}, type="string"),
        _spec("skills", **{"from": "skills[].name"}, type="string[]"),
        _spec("country", **{"from": "location.country"}, type="string"),
        _spec("first_link", **{"from": "links.other[0]"}, type="string"),
    ])
    out = project(_profile(), cfg)
    assert out == {
        "name": "Jane", "email": "a@b.com", "skills": ["Python"],
        "country": "US", "first_link": "https://t.co/x",
    }


def test_normalize_override_applies_at_projection():
    cfg = OutputConfig(fields=[_spec("phone", **{"from": "phones[0]"}, type="string", normalize="E164")])
    assert project(_profile(), cfg)["phone"] == "+14155550142"


def test_on_missing_omit_drops_key():
    cfg = OutputConfig(fields=[_spec("headline", **{"from": "headline"}, type="string", on_missing="omit")])
    assert "headline" not in project(_profile(), cfg)


def test_on_missing_null_sets_none():
    cfg = OutputConfig(fields=[_spec("headline", **{"from": "headline"}, type="string", on_missing="null")])
    assert project(_profile(), cfg)["headline"] is None


def test_on_missing_error_raises():
    cfg = OutputConfig(fields=[_spec("headline", **{"from": "headline"}, type="string", on_missing="error")])
    with pytest.raises(ProjectionError):
        project(_profile(), cfg)


def test_include_confidence_attaches_overall():
    cfg = OutputConfig(fields=[_spec("name", **{"from": "full_name"}, type="string")],
                       include_confidence=True)
    assert project(_profile(), cfg)["overall_confidence"] == 0.5


def test_default_config_emits_full_profile_with_toggles_off():
    # No fields + both toggles off -> canonical dump minus provenance/confidence.
    cfg = OutputConfig()
    out = project(_profile(), cfg)
    assert "provenance" not in out
    assert "overall_confidence" not in out
    assert out["full_name"] == "Jane"
    assert "confidence" not in out["skills"][0]  # per-skill confidence stripped
