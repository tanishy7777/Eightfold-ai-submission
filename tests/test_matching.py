"""Matching: union by email/phone, transitive, and the no-fuzzy-name rule."""

from transformer.matching import cluster
from transformer.models import SourceRecord
from transformer.sources.base import extract_links


def _rec(source, emails=(), phones=(), name=None, linkedin=None, github=None, skill=None):
    r = SourceRecord(source=source)
    for e in emails:
        r.add("emails", e, "direct_field")
    for p in phones:
        r.add("phones", p, "direct_field")
    if name:
        r.add("full_name", name, "direct_field")
    if linkedin:
        r.add("links.linkedin", linkedin, "direct_field")
    if github:
        r.add("links.github", github, "direct_field")
    if skill:
        r.add("skills", skill, "direct_field")
    return r


def test_same_email_merges():
    groups = cluster([_rec("a", emails=["x@y.com"]), _rec("b", emails=["x@y.com"])])
    assert len(groups) == 1


def test_same_phone_merges():
    groups = cluster([_rec("a", phones=["+14155550142"]), _rec("b", phones=["+14155550142"])])
    assert len(groups) == 1


def test_transitive_merge_via_shared_keys():
    # A~B share email; B~C share phone => all one candidate.
    a = _rec("a", emails=["x@y.com"])
    b = _rec("b", emails=["x@y.com"], phones=["+14155550142"])
    c = _rec("c", phones=["+14155550142"])
    assert len(cluster([a, b, c])) == 1


def test_same_name_does_NOT_merge():
    # Two different people who happen to share a name must stay separate.
    a = _rec("a", emails=["jane1@y.com"], name="Jane Doe")
    b = _rec("b", emails=["jane2@y.com"], name="Jane Doe")
    assert len(cluster([a, b])) == 2


def test_linkedin_url_merges_across_scheme_and_case():
    # Same handle written differently, and one source has NO email/phone.
    a = _rec("ats", emails=["jane@y.com"], linkedin="https://linkedin.com/in/jane")
    b = _rec("li", linkedin="https://www.LinkedIn.com/in/Jane/")
    assert len(cluster([a, b])) == 1


def test_github_url_merges():
    a = _rec("gh", github="https://github.com/janedoe")
    b = _rec("ats", emails=["j@y.com"], github="github.com/janedoe")
    assert len(cluster([a, b])) == 1


def test_emailless_github_links_via_resume_url():
    # The realistic case: GitHub API returns no email/phone. The record links
    # only because the resume mentions the same github handle.
    gh = _rec("github", name="Jane Doe", github="https://github.com/janedoe")
    resume = _rec("resume", emails=["jane@y.com"])
    for field, url, raw in extract_links("see github.com/janedoe/somerepo"):
        resume.add(field, url, "regex_extract", raw)
    assert len(cluster([gh, resume])) == 1


def test_extract_links_normalizes_handles():
    links = extract_links("https://github.com/janedoe/repo and www.linkedin.com/in/jane-d/")
    fields = dict((f, u) for f, u, _ in links)
    assert fields["links.github"] == "https://github.com/janedoe"
    assert fields["links.linkedin"] == "https://linkedin.com/in/jane-d"


def test_shared_skill_does_NOT_merge():
    # Two different people who both list Python must stay separate (weak field).
    a = _rec("a", emails=["jane@y.com"], skill="Python")
    b = _rec("b", emails=["sam@y.com"], skill="Python")
    assert len(cluster([a, b])) == 2


def test_keyless_record_stands_alone():
    a = _rec("a", name="No Keys")  # no email/phone
    b = _rec("b", emails=["x@y.com"])
    assert len(cluster([a, b])) == 2


def test_clustering_is_order_independent():
    a = _rec("a", emails=["x@y.com"])
    b = _rec("b", emails=["x@y.com"], phones=["+14155550142"])
    c = _rec("c", phones=["+14155550142"])
    assert len(cluster([a, b, c])) == len(cluster([c, b, a])) == 1
