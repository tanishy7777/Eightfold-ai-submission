"""Normalizers: correct formats, and the key 'never invent' behavior."""

from transformer.normalize import (
    canonical_skill, clean_email, clean_name, country_to_iso2, is_known,
    parse_location_string, split_skills, to_e164, to_year, to_year_month,
)


def test_phone_to_e164():
    assert to_e164("(415) 555-0142") == "+14155550142"
    assert to_e164("+1 415-555-0142") == "+14155550142"


def test_phone_garbage_is_none_not_invented():
    assert to_e164("call me after 5pm") is None
    assert to_e164("") is None
    assert to_e164(None) is None


def test_dates_with_month():
    assert to_year_month("Jan 2020") == "2020-01"
    assert to_year_month("2020-3") == "2020-03"
    assert to_year_month("03/2020") == "2020-03"
    assert to_year_month("Oct 2019") == "2019-10"  # regression: 'o','t' in month


def test_dates_unparseable_or_year_only_is_none():
    # Year-only returns None on purpose: we will not invent a month.
    assert to_year_month("2020") is None
    assert to_year_month("Summer 2018") is None
    assert to_year_month("present") is None


def test_to_year_extracts_year():
    assert to_year("class of 2019") == 2019
    assert to_year("no year here") is None


def test_country_iso2():
    assert country_to_iso2("U.S.A.") == "US"
    assert country_to_iso2("United States") == "US"
    assert country_to_iso2("india") == "IN"
    assert country_to_iso2("Wakanda") is None  # unknown -> not guessed


def test_location_split():
    assert parse_location_string("San Francisco, CA, USA") == ("San Francisco", "CA", "US")
    assert parse_location_string("Bangalore, India") == ("Bangalore", None, "IN")
    assert parse_location_string("") == (None, None, None)


def test_skill_canonicalization():
    assert canonical_skill("js") == "JavaScript"
    assert canonical_skill("  PYTHON ") == "Python"
    assert canonical_skill("react.js") == "React"
    assert is_known("JavaScript") is True


def test_unknown_skill_kept_but_flagged():
    assert canonical_skill("Frobnicator") == "Frobnicator"  # kept, not dropped
    assert is_known("Frobnicator") is False                  # flagged for discount


def test_split_skills():
    assert split_skills("Python, JS and Go") == ["Python", "JS", "Go"]


def test_email_and_name_cleanup():
    assert clean_email("  JANE@X.COM ") == "jane@x.com"  # lowercased for matching
    assert clean_email("not-an-email") is None
    assert clean_name("  jane   doe ") == "jane doe"
