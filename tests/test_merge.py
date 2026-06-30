"""Merge: scalar conflict resolution, list union, skill scoring + penalty."""

from transformer.merge import merge_group
from transformer.models import SourceRecord


def test_scalar_conflict_picks_higher_trust():
    # years: ATS direct (0.6) beats notes regex (0.32) -> 8 wins.
    ats = SourceRecord(source="ats_json")
    ats.add("emails", "x@y.com", "direct_field")
    ats.add("years_experience", 8.0, "direct_field")
    notes = SourceRecord(source="recruiter_notes")
    notes.add("emails", "x@y.com", "regex_extract")
    notes.add("years_experience", 9.0, "regex_extract")
    profile = merge_group([ats, notes])
    assert profile.years_experience == 8.0


def test_phones_union_keeps_all_trust_ordered():
    ats = SourceRecord(source="ats_json")
    ats.add("phones", "+14155550199", "direct_field")   # contact 0.90
    csv = SourceRecord(source="recruiter_csv")
    csv.add("phones", "+14155550142", "direct_field")   # contact 0.95 -> first
    profile = merge_group([ats, csv])
    assert profile.phones == ["+14155550142", "+14155550199"]  # both kept, CSV first


def test_skill_agreement_raises_confidence():
    # Skills trust favors code/resume over ATS: ats skills = 0.60 (direct),
    # notes skills = 0.40 * 0.8 (regex) = 0.32. Agreement combines via noisy-OR.
    ats = SourceRecord(source="ats_json")
    ats.add("skills", "Python", "direct_field")
    notes = SourceRecord(source="recruiter_notes")
    notes.add("skills", "Python", "regex_extract")
    profile = merge_group([ats, notes])
    py = next(s for s in profile.skills if s.name == "Python")
    assert py.confidence == round(1 - (1 - 0.60) * (1 - 0.32), 2)  # 0.73
    assert py.confidence > 0.60                                     # > either source alone
    assert py.sources == ["ats_json", "recruiter_notes"]


def test_unknown_skill_is_penalized():
    ats = SourceRecord(source="ats_json")
    ats.add("skills", "Python", "direct_field")        # known:   0.60
    ats.add("skills", "Frobnicator", "direct_field")   # unknown: 0.60 * 0.7 = 0.42
    profile = merge_group([ats])
    known = next(s for s in profile.skills if s.name == "Python").confidence
    unknown = next(s for s in profile.skills if s.name == "Frobnicator").confidence
    assert unknown == 0.42
    assert unknown < known


def test_experience_dedup_backfills_dates():
    # CSV has the role but no dates; resume has the same role WITH dates.
    csv = SourceRecord(source="recruiter_csv")
    csv.add("experience", {"company": "Acme", "title": "Engineer",
                           "start": None, "end": None, "summary": None}, "direct_field")
    resume = SourceRecord(source="resume")
    resume.add("experience", {"company": "Acme", "title": "Engineer",
                              "start": "2021-01", "end": None, "summary": None}, "regex_extract")
    profile = merge_group([csv, resume])
    assert len(profile.experience) == 1                 # deduped into one
    assert profile.experience[0].start == "2021-01"     # date backfilled
