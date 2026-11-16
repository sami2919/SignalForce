import pytest

from scripts.hospitality.resolve.normalize import (
    haversine_m,
    name_similarity,
    normalize_address,
    normalize_name,
    registrable_domain,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Carbone LLC", "carbone"),
        ("The Noortwyck, Inc.", "noortwyck"),
        ("Joe & Pat's Pizzeria Corp", "joe and pats pizzeria"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("289 Bleecker Street", "289 bleecker st"),
        ("289 BLEECKER ST #2", "289 bleecker st"),
        ("10 West 21st Street, Floor 3", "10 w 21 st"),
        ("1 Fifth Avenue", "1 5 ave"),
    ],
)
def test_normalize_address(raw, expected):
    assert normalize_address(raw) == expected


def test_name_similarity():
    assert name_similarity("Carbone LLC", "CARBONE") == 1.0
    assert name_similarity("Carbone", "Zzzzz") < 0.5


def test_haversine_known_distance():
    assert haversine_m(40.7308, -74.0018, 40.7317, -74.0018) == pytest.approx(100, rel=0.05)


def test_registrable_domain():
    assert registrable_domain("https://www.oriananewyork.com/reserve") == "oriananewyork.com"


def test_registrable_domain_edge_cases():
    assert registrable_domain("oriananewyork.com/x") == "oriananewyork.com"
    assert registrable_domain("") is None
    assert registrable_domain("https://shop.example.co.uk/") == "example.co.uk"
