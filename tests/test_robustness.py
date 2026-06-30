"""Robustness: a missing/garbage/empty source must never crash the run."""

from pathlib import Path

from transformer.config import FieldSpec, OutputConfig
from transformer.models import CanonicalProfile
from transformer.pipeline import build_profiles, project_profiles
from transformer.sources import get_adapter
from transformer.sources.base import safe_read_json

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_broken_json_returns_none():
    assert safe_read_json(str(SAMPLES / "garbage.json")) is None


def test_garbage_source_yields_no_records():
    assert get_adapter("ats").extract(str(SAMPLES / "garbage.json")) == []


def test_missing_file_yields_no_records():
    assert get_adapter("csv").extract("/no/such/path/file.csv") == []


def test_empty_csv_yields_no_records(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("Name,Email\n")  # header only, no rows
    assert get_adapter("csv").extract(str(empty)) == []


def test_pipeline_completes_with_only_a_garbage_source():
    # The whole run degrades to "no profiles", not an exception.
    assert build_profiles([("ats", str(SAMPLES / "garbage.json"))]) == []


def test_pipeline_skips_garbage_but_keeps_good_sources():
    profiles = build_profiles([
        ("csv", str(SAMPLES / "recruiter.csv")),
        ("ats", str(SAMPLES / "garbage.json")),  # skipped
    ])
    assert len(profiles) == 2  # Jane + Sam still produced


def test_phantom_profile_with_no_identity_is_dropped(tmp_path):
    # A GitHub fixture exposing only a link (no email/name) clusters alone and
    # must NOT surface as a nameless phantom profile. Reproduces the live-fetch
    # case where a real handle returns an unrelated, near-empty profile.
    fixture = tmp_path / "ghost.json"
    fixture.write_text('{"html_url": "https://github.com/ghost"}')
    assert build_profiles([("github", str(fixture))]) == []


def test_one_invalid_projection_is_skipped_not_fatal():
    # A profile that fails the config contract is skipped + warned; the run
    # completes and the valid profiles still come through.
    config = OutputConfig(fields=[FieldSpec(path="full_name", type="string", required=True)])
    profiles = [
        CanonicalProfile(candidate_id="cand_ok", full_name="Jane Doe"),
        CanonicalProfile(candidate_id="cand_bad", emails=["x@example.com"]),  # no full_name
    ]
    outputs = project_profiles(profiles, config)
    assert outputs == [{"full_name": "Jane Doe"}]
