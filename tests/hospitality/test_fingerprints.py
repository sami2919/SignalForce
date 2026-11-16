from pathlib import Path

from scripts.hospitality.stack.fingerprints import (
    EVENTS,
    QSR_LOYALTY,
    RESERVATION,
    detect_platforms,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "hospitality"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_widget_links_detected():
    found = dict(detect_platforms(fixture_text("site_resy_tripleseat.html")))
    assert {"resy", "tripleseat"} <= found.keys()
    assert "resy" in RESERVATION and "tripleseat" in EVENTS


def test_text_mention_is_not_detection():
    assert detect_platforms("<p>Find us on Resy and Tock!</p>") == ()


def test_text_only_fixture_and_comment_not_detected():
    assert detect_platforms(fixture_text("site_text_only.html")) == ()


def test_loyalist_schema_property_detected():
    html = '<script type="application/ld+json">{"propertyID":"loyalist-venue-id"}</script>'
    assert dict(detect_platforms(html))["loyalist"]


def test_loyalist_embed_fixture():
    found = dict(detect_platforms(fixture_text("site_loyalist_embed.html")))
    assert "loyalist" in found


def test_olo_does_not_match_unrelated_domains():
    assert detect_platforms('<a href="https://polo.com/x">x</a>') == ()


def test_subdomain_matches_and_punchh_fixture():
    found = dict(detect_platforms(fixture_text("site_punchh.html")))
    assert {"punchh", "olo"} <= found.keys()
    assert {"punchh", "olo"} <= QSR_LOYALTY


def test_script_body_url_detected_and_sorted_one_per_platform():
    html = (
        '<script>load("https://widget.resy.com/a"); load("https://resy.com/b")</script>'
        '<form action="https://www.opentable.com/x"></form>'
        '<div data-embed="https://exploretock.com/z"></div>'
    )
    result = detect_platforms(html)
    names = [p for p, _ in result]
    assert names == sorted(names) == ["opentable", "resy", "tock"]


def test_domain_in_path_or_query_is_not_host_match():
    html = '<a href="https://example.com/redirect?u=resy.com">x</a><a href="/resy.com">y</a>'
    assert detect_platforms(html) == ()


def test_evidence_truncated_to_120_chars():
    html = f'<a href="https://resy.com/{"a" * 300}">x</a>'
    assert len(dict(detect_platforms(html))["resy"]) == 120


def test_loyalist_id_in_visible_text_not_detected():
    assert detect_platforms("<p>loyalist-venue-id</p>") == ()
