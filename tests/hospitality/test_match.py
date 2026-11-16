import pytest

from scripts.hospitality.config import load_config
from scripts.hospitality.resolve.match import match_licenses, pair_probability
from tests.hospitality.factories import make_inspection, make_license


@pytest.fixture
def cfg():
    return load_config()


def test_same_address_same_name_auto_matches(cfg):
    lic = make_license("l1", dba="The Noortwyck", address="289 Bleecker Street", zip_code="10014")
    ins = make_inspection("c1", dba="NOORTWYCK", address="289 BLEECKER ST", zip_code="10014")
    res = match_licenses([lic], [ins], cfg)
    assert res.pairs[0].camis == "c1" and res.pairs[0].probability >= 0.9
    assert res.pairs[0].method == "address+name"
    assert res.unmatched_licenses == () and res.unmatched_camis == ()


def test_near_but_different_name_becomes_link_not_merge(cfg):
    lic = make_license(
        "l2", dba="Oriana", address="1 Main St", lat=40.0, lon=-74.0, zip_code="10012"
    )
    ins = make_inspection(
        "c2", dba="Oriana Wine Bar", address="3 Main St", lat=40.0001, lon=-74.0, zip_code="10012"
    )
    res = match_licenses([lic], [ins], cfg)
    assert res.pairs == () and res.links[0].kind == "possibly_same"
    assert (res.links[0].left_id, res.links[0].right_id) == ("l2", "c2")
    assert res.unmatched_camis == ("c2",)


def test_different_zip_never_compared(cfg):
    lic = make_license("l3", dba="X", address="1 A St", zip_code="10001")
    ins = make_inspection("c3", dba="X", address="1 A St", zip_code="11201")
    assert match_licenses([lic], [ins], cfg).unmatched_licenses == ("l3",)


def test_name_only_when_no_location_evidence(cfg):
    lic = make_license("l4", dba="Zed", address="1 A St", lat=None, lon=None)
    ins = make_inspection("c4", dba="Zed", address="9 B St", lat=None, lon=None)
    p, method = pair_probability(lic, ins, cfg.match_max_distance_m)
    assert method == "name_only" and p == pytest.approx(0.4)
    assert match_licenses([lic], [ins], cfg).unmatched_licenses == ("l4",)


def test_best_candidate_wins_and_camis_may_have_many_licenses(cfg):
    good = make_inspection("good", dba="Acme", address="1 Main St")
    other = make_inspection("other", dba="Zzz Qqq", address="5 Elm St", lat=None, lon=None)
    lics = [make_license("a"), make_license("b", license_class="CT")]
    res = match_licenses(lics, [other, good], cfg)
    assert [(p.license_id, p.camis) for p in res.pairs] == [("a", "good"), ("b", "good")]
    assert res.unmatched_camis == ("other",)
