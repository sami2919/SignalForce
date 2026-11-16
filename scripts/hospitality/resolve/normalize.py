"""Deterministic name, address, distance and domain normalization primitives."""

from __future__ import annotations

import math
import re
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


def normalize_address(raw: str) -> str:
    """Canonicalize a street address so spelling variants compare equal."""
    text = _UNIT_TAIL.sub("", raw.lower())
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
