from datetime import date

from scripts.hospitality.models import EntityLink, MatchPair, MatchResult
from scripts.hospitality.resolve.venues import build_venues
from tests.hospitality.factories import make_inspection, make_license


def test_unmatched_license_becomes_its_own_venue():
    venues = build_venues(
        [make_license("l9")],
        [],
        MatchResult(pairs=(), links=(), unmatched_licenses=("l9",), unmatched_camis=()),
    )
    assert venues[0].venue_id == "v:lic:l9" and venues[0].camis is None
    assert venues[0].group_id == "g:v:lic:l9"


def test_pair_merges_license_into_inspection_venue_with_latest_license_class():
    old = make_license(
        "l1", license_class="OP", description="Old", original_issue_date=date(2020, 1, 1)
    )
    new = make_license(
        "l2", license_class="RW", description="New", original_issue_date=date(2024, 1, 1)
    )
    ins = make_inspection("c1", first=date(2025, 1, 1))
    pairs = (
        MatchPair(license_id="l1", camis="c1", probability=1.0, method="m"),
        MatchPair(license_id="l2", camis="c1", probability=1.0, method="m"),
    )
    res = MatchResult(pairs=pairs, links=(), unmatched_licenses=(), unmatched_camis=())
    venues = build_venues([old, new], [ins], res)
    assert len(venues) == 1
    v = venues[0]
    assert v.venue_id == "v:c1" and v.camis == "c1"
    assert v.license_ids == ("l1", "l2")
    assert (v.license_class, v.license_description) == ("RW", "New")
    assert v.first_inspection_date == date(2025, 1, 1)


def test_possibly_same_link_does_not_merge():
    lic, ins = make_license("l1"), make_inspection("c1")
    link = EntityLink(
        left_id="l1", right_id="c1", kind="possibly_same", probability=0.7, method="m"
    )
    res = MatchResult(pairs=(), links=(link,), unmatched_licenses=("l1",), unmatched_camis=("c1",))
    ids = {v.venue_id for v in build_venues([lic], [ins], res)}
    assert ids == {"v:lic:l1", "v:c1"}
