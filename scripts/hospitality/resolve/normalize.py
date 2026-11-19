"""Deterministic name, address, distance and domain normalization primitives."""

from __future__ import annotations

import math
import re
import unicodedata
from urllib.parse import urlparse

from rapidfuzz import fuzz

_CORP_SUFFIXES = frozenset({"llc", "inc", "corp", "co", "ltd", "lp"})
_ORDINALS = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
    "eleventh": "11",
    "twelfth": "12",
}
_ABBREVIATIONS = {
    "west": "w",
    "east": "e",
    "north": "n",
    "south": "s",
    "street": "st",
    "avenue": "ave",
    "place": "pl",
    "boulevard": "blvd",
    "road": "rd",
}
_UNIT_TAIL = re.compile(r"(?:#|\b(?:suite|ste|floor|fl|apt)\b).*$")
_ORDINAL_SUFFIX = re.compile(r"^(\d+)(?:st|nd|rd|th)$")
_EARTH_RADIUS_M = 6_371_000.0
# Second-level labels that form a public suffix with a 2-letter country code (e.g. co.uk).
_SLD_LABELS = frozenset({"co", "com", "org", "net", "gov", "edu", "ac"})


def normalize_name(raw: str) -> str:
    """Lowercase a business name, drop punctuation, the leading 'the' and corp suffixes."""
    text = raw.lower().replace("&", " and ")
    text = re.sub(r"['’]", "", text)
    tokens = re.sub(r"[^a-z0-9]+", " ", text).split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1] in _CORP_SUFFIXES:
        tokens = tokens[:-1]
    return " ".join(tokens)


def normalize_address(raw: str, *, strip_unit: bool = True) -> str:
    """Canonicalize a street address so spelling variants compare equal.

    `strip_unit=False` keeps a trailing suite / floor (for running page text, where everything
    after a "suite" is not a unit).
    """
    text = _UNIT_TAIL.sub("", raw.lower()) if strip_unit else raw.lower()
    tokens = re.sub(r"[^a-z0-9]+", " ", text).split()
    out: list[str] = []
    for token in tokens:
        match = _ORDINAL_SUFFIX.match(token)
        if match:
            token = match.group(1)
        token = _ORDINALS.get(token, token)
        out.append(_ABBREVIATIONS.get(token, token))
    return " ".join(out)


def name_similarity(a: str, b: str) -> float:
    """Token-set similarity of two normalized names, in [0, 1]."""
    return float(fuzz.token_set_ratio(normalize_name(a), normalize_name(b))) / 100.0


# Tokens that carry no identity at all: English articles, corporate filler, place filler. Dropped
# before a strict comparison ("NOORTWYCK LLC, THE" == "The Noortwyck"). Foreign articles stay in
# the compared name ("El Quijote" is not the Queens "QUIJOTE") but are generic below.
_NOISE_NAME_TOKENS = frozenset(
    {
        "a", "an", "and", "at", "by", "for", "in", "of", "on", "the", "to",
        "associates", "co", "company", "corp", "corporation", "enterprises", "holding",
        "holdings", "inc", "international", "llc", "lp", "ltd", "management", "mgmt",
        "partners", "services", "ventures",
        "city", "new", "ny", "nyc", "york",
    }
)  # fmt: skip
# Words that say what kind of business a name is, not which one. A name made only of these and
# noise tokens identifies nobody, so it can never carry a strict name match.
GENERIC_NAME_TOKENS = _NOISE_NAME_TOKENS | frozenset(
    {
        "d", "da", "de", "del", "della", "des", "di", "du", "e", "el", "il", "l", "la", "le",
        "les", "lo", "los", "y",
        "bar", "bars", "bistro", "brasserie", "cafe", "caterers", "catering", "club", "clubs",
        "coffee", "concepts", "dining", "diner", "eatery", "food", "foods", "foodservice",
        "grill", "group", "groups", "hospitality", "hotel", "hotels", "house", "inn",
        "kitchen", "lounge", "park", "pub", "restaurant", "restaurants", "tavern",
    }
)  # fmt: skip
# Deliberately code, not config (M2): this match decides who is a Loyalist customer (Review
# Focus 4), which press / job-board names merge groups, and which benchmark items count. A
# lower value in a user YAML would silently re-open the C1 leak, so it is pinned by tests here.
STRICT_NAME_THRESHOLD = 0.9


def _fold(raw: str) -> str:
    """Strip accents (Rezdôra -> Rezdora) so a spelling without them compares equal."""
    return "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))


def _strict_tokens(raw: str) -> list[str]:
    return [t for t in normalize_name(_fold(raw)).split() if t not in _NOISE_NAME_TOKENS]


def distinctive_tokens(raw: str) -> frozenset[str]:
    """The normalized tokens of a name that are not generic business words."""
    return frozenset(_strict_tokens(raw)) - GENERIC_NAME_TOKENS


def strict_name_match(a: str, b: str, threshold: float = STRICT_NAME_THRESHOLD) -> bool:
    """Near-exact name equality, for decisions a namesake must never pass (customer labels).

    Both names need a distinctive token, they must share one, and the whole names must be
    near-equal by `token_sort_ratio` (order-insensitive, but a token subset is NOT a match:
    "Major Food Group" never matches "FOOD", "Hotel Chelsea" never "THE GEM HOTEL CHELSEA").
    """
    da, db = distinctive_tokens(a), distinctive_tokens(b)
    ta, tb = _strict_tokens(a), _strict_tokens(b)
    # A shared distinctive token, or the same letters split differently ("NOORT WYCK").
    if not da or not db or not (da & db or "".join(ta) == "".join(tb)):
        return False
    return float(fuzz.token_sort_ratio(" ".join(ta), " ".join(tb))) / 100.0 >= threshold


def name_prefix_match(prefix: str, name: str) -> bool:
    """True when `name`'s tokens start with all of `prefix`'s tokens and the prefix is distinctive.

    Only for a brand a human has marked as a prefix in the seed list ("Momofuku*" covers
    "MOMOFUKU NOODLE BAR"); never applied to a name on its own.
    """
    if not distinctive_tokens(prefix):
        return False
    p, n = _strict_tokens(prefix), _strict_tokens(name)
    return len(n) >= len(p) and n[: len(p)] == p


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def registrable_domain(url: str) -> str | None:
    """Return the registrable domain (eTLD+1, heuristic) of a URL, or None if unparseable."""
    raw = url.strip()
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").strip(".").lower()
    labels = host.split(".")
    if len(labels) < 2 or not all(labels):
        return None
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SLD_LABELS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


# NYC ZIP prefix -> borough (lowercase).
ZIP_BOROUGH_PREFIX: tuple[tuple[tuple[str, ...], str], ...] = (
    (("100", "101", "102"), "manhattan"),
    (("103",), "staten island"),
    (("104",), "bronx"),
    (("112",), "brooklyn"),
    (("110", "111", "113", "114", "116"), "queens"),
)


def borough_of_zip(zip_code: str) -> str | None:
    """NYC borough (lowercase) for a ZIP code, or None outside the five boroughs."""
    for prefixes, borough in ZIP_BOROUGH_PREFIX:
        if zip_code.startswith(prefixes):
            return borough
    return None
