from scripts.hospitality.models import GroupEvidence
from scripts.hospitality.resolve.groups import form_groups, merge_groups
from tests.hospitality.factories import make_license, make_venue

NO_HOSTS: frozenset[str] = frozenset()


def test_shared_legal_name_forms_group():
    lics = [
        make_license("a", legal_name="HAPPY COOKING LLC"),
        make_license("b", legal_name="Happy Cooking, LLC"),
    ]
    venues, groups = form_groups(
        [make_venue("v:a", license_ids=("a",)), make_venue("v:b", license_ids=("b",))],
        lics,
        ignore_domains=NO_HOSTS,
    )
    assert len(groups) == 1 and groups[0].resolution == "shared_legal_name"
    assert groups[0].group_id == "g:v:a" and {v.group_id for v in venues} == {"g:v:a"}


def test_generic_legal_name_does_not_merge():
    lics = [
        make_license("a", legal_name="Restaurant Management LLC"),
        make_license("b", legal_name="RESTAURANT MANAGEMENT, LLC"),
    ]
    _, groups = form_groups(
        [make_venue("v:a", license_ids=("a",)), make_venue("v:b", license_ids=("b",))],
        lics,
        ignore_domains=NO_HOSTS,
    )
    assert len(groups) == 2 and all(g.resolution == "singleton" for g in groups)


def test_shared_domain_forms_group():
    vs = [
        make_venue("v:a", website="https://www.foo.com/a"),
        make_venue("v:b", website="http://foo.com"),
        make_venue("v:c", website="https://bar.com"),
    ]
    _, groups = form_groups(vs, [], ignore_domains=NO_HOSTS)
    assert sorted(g.resolution for g in groups) == ["shared_domain", "singleton"]


def test_shared_host_domain_never_forms_group():
    vs = [
        make_venue("v:a", website="https://www.instagram.com/alpha"),
        make_venue("v:b", website="https://instagram.com/bravo"),
    ]
    _, groups = form_groups(vs, [], ignore_domains=frozenset({"instagram.com"}))
    assert [g.resolution for g in groups] == ["singleton", "singleton"]


def test_regroup_reapplies_evidence_over_fresh_grouping():
    from scripts.hospitality.resolve.groups import regroup

    vs = [make_venue("v:a", group_id="g:stale"), make_venue("v:b"), make_venue("v:c")]
    ev = [GroupEvidence(venue_ids=("v:b", "v:c"), name="G", resolution="press", evidence_ref="x")]
    venues, groups = regroup(vs, [], ev, ignore_domains=NO_HOSTS)
    assert {v.venue_id: v.group_id for v in venues} == {
        "v:a": "g:v:a",
        "v:b": "g:v:b",
        "v:c": "g:v:b",
    }
    assert sorted(g.resolution for g in groups) == ["press", "singleton"]


def test_merge_is_transitive():
    vs = [make_venue(f"v:{i}") for i in "abc"]
    _, gs = form_groups(vs, [], ignore_domains=NO_HOSTS)
    ev = [
        GroupEvidence(venue_ids=("v:a", "v:b"), name="G", resolution="press", evidence_ref="x"),
        GroupEvidence(
            venue_ids=("v:b", "v:c"), name="G", resolution="website_locations", evidence_ref="y"
        ),
    ]
    venues, groups = merge_groups(vs, gs, ev)
    assert len(groups) == 1 and groups[0].resolution == "website_locations"
    assert {v.group_id for v in venues} == {groups[0].group_id}
    assert groups[0].group_id == "g:v:a" and groups[0].name == "G"


def test_resolve_cli_saves_venues_groups_and_links(tmp_path, monkeypatch):
    from scripts.hospitality import cli
    from scripts.hospitality.models import Group, Venue
    from scripts.hospitality.store import DocStore
    from tests.hospitality.factories import make_inspection

    store = DocStore(f"sqlite:///{tmp_path}/t.db")
    store.save(
        "licenses",
        [
            make_license("l1"),
            make_license("l2", dba="Zzz Qqq", address="99 Far Ave", zip_code="10099"),
        ],
        key=lambda r: r.record_id,
    )
    store.save("inspections", [make_inspection("c1")], key=lambda r: r.camis)
    monkeypatch.setattr(cli, "DocStore", lambda: store)
    counts = cli.resolve()
    assert counts["venues"] == len(store.load("venues", Venue)) >= 2
    assert counts["groups"] == len(store.load("groups", Group))
