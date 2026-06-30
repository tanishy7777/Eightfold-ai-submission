"""End-to-end 'gold profile' test on the sample inputs.

Locks the canonical behavior (including an exact overall_confidence) so any
change to normalization/merge/confidence that shifts the output is caught. Also
asserts the run is byte-stable (deterministic), and that the custom config's
on_missing policies behave.
"""

from pathlib import Path

from transformer.config import load_config
from transformer.pipeline import build_profiles, project_profiles, run_pipeline

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
CONFIGS = ROOT / "data" / "configs"

SOURCES = [
    ("csv", str(SAMPLES / "recruiter.csv")),
    ("ats", str(SAMPLES / "ats.json")),
    ("ats", str(SAMPLES / "garbage.json")),  # malformed -> skipped
    ("notes", str(SAMPLES / "notes.txt")),
    ("github", str(SAMPLES / "github_jane.json")),
    ("linkedin", str(SAMPLES / "linkedin_jane.json")),
    ("resume", str(SAMPLES / "resume_jane.pdf")),
]


def _jane(profiles):
    return next(p for p in profiles if "jane.doe@example.com" in p.emails)


def test_two_candidates_after_dedup():
    profiles = build_profiles(SOURCES)
    assert len(profiles) == 2  # Jane (6 sources) + Sam, garbage skipped


def test_phone_conflict_keeps_both_trust_ordered():
    jane = _jane(build_profiles(SOURCES))
    # Edge case 1: both phones kept; CSV (higher trust) is primary.
    assert jane.phones == ["+14155550142", "+14155550199"]


def test_unnormalizable_and_unknown_handled():
    jane = _jane(build_profiles(SOURCES))
    # "Summer 2018" start could not be normalized -> null (not invented).
    globex = next(e for e in jane.experience if e.company == "Globex")
    assert globex.start is None
    assert globex.end == "2020-12"
    # Unknown skill kept but lower-confidence than a known one.
    fro = next(s for s in jane.skills if s.name == "Frobnicator")
    py = next(s for s in jane.skills if s.name == "Python")
    assert fro.confidence < py.confidence


def test_experience_backfill_and_location():
    jane = _jane(build_profiles(SOURCES))
    senior = next(e for e in jane.experience
                  if e.company == "Acme Corp" and e.title == "Senior Software Engineer")
    assert senior.start == "2021-01"          # date backfilled from resume/LinkedIn
    assert jane.location.country == "US"
    assert jane.years_experience == 8.0       # ATS beats notes' 9


def test_linkedin_wins_headline_and_adds_experience():
    jane = _jane(build_profiles(SOURCES))
    # LinkedIn is the trusted source for headline -> it beats the GitHub bio.
    assert jane.headline == "Senior Software Engineer at Acme Corp"
    # LinkedIn contributes an experience entry no other source has.
    assert any(e.company == "Initech" for e in jane.experience)


def test_gold_overall_confidence():
    # Exact value: pins the trust table + confidence formula + determinism.
    jane = _jane(build_profiles(SOURCES))
    assert jane.overall_confidence == 0.94


def test_output_is_byte_stable():
    assert run_pipeline(SOURCES) == run_pipeline(SOURCES)


def test_custom_config_on_missing_policies():
    profiles = build_profiles(SOURCES)
    projected = project_profiles(profiles, load_config(str(CONFIGS / "custom_compact.json")))
    sam = next(o for o in projected if o["full_name"] == "Sam Lee")
    assert "github" not in sam       # on_missing: omit (Sam has no github link)
    assert sam["twitter"] is None    # on_missing: null (nobody has links.other)
