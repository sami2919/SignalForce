"""Platform fingerprints: which booking/CRM/events tools a venue's page embeds.

Detection reads only link/script/form attributes (`href`, `src`, `action`, `data-*`) and
`<script>` bodies, never visible text or comments, so a page that merely says "Resy" or a
theme-demo snippet does not count (Review Focus 3).
"""

import re
from urllib.parse import urlparse

from selectolax.parser import HTMLParser

FINGERPRINTS: dict[str, tuple[str, ...]] = {
    "resy": ("resy.com",),
    "opentable": ("opentable.com", "otstatic.com"),
    "sevenrooms": ("sevenrooms.com",),
    "tock": ("exploretock.com",),
    "toast": ("toasttab.com",),
    "square": ("squareup.com", "square.site"),
    "tripleseat": ("tripleseat.com",),
    "perfect_venue": ("perfectvenue.com",),
    "loyalist": ("eatloyalist.com", "loyalist-venue-id"),
    "bentobox": ("getbento.com",),
    "mailchimp": ("list-manage.com",),
    "punchh": ("punchh.com",),
    "thanx": ("thanx.com",),
    "olo": ("olo.com",),
    "incentivio": ("incentivio.com",),
}
RESERVATION = frozenset({"resy", "opentable", "sevenrooms", "tock"})
EVENTS = frozenset({"tripleseat", "perfect_venue"})
QSR_LOYALTY = frozenset({"punchh", "thanx", "olo", "incentivio"})

EVIDENCE_MAX = 120
_URL_ATTRS = ("href", "src", "action")
_SCRIPT_URL_RE = re.compile(r"(?:https?:)?//([^/\s\"'\\?#<>()]+)", re.IGNORECASE)


def _host_matches(host: str, pattern: str) -> bool:
    host = host.lower().rstrip(".")
    return host == pattern or host.endswith("." + pattern)


def _host_of(value: str) -> str:
    candidate = value.strip()
    if "//" not in candidate:
        candidate = "//" + candidate
    try:
        return urlparse(candidate).hostname or ""
    except ValueError:
        return ""


def detect_platforms(html: str) -> tuple[tuple[str, str], ...]:
    """Return `(platform, evidence)` pairs, sorted by platform, one per platform."""
    tree = HTMLParser(html)
    # (candidate host, evidence) pairs; a domain pattern must match the host on a boundary.
    hosts: list[tuple[str, str]] = []
    script_bodies: list[str] = []
    for node in tree.css("*"):
        for name, value in node.attributes.items():
            if not value:
                continue
            if name in _URL_ATTRS or name.startswith("data-"):
                hosts.append((_host_of(value), value))
        if node.tag == "script":
            body = node.text(deep=True) or ""
            if body:
                script_bodies.append(body)
                hosts.extend((m.group(1), m.group(0)) for m in _SCRIPT_URL_RE.finditer(body))

    found: dict[str, str] = {}
    for platform, patterns in FINGERPRINTS.items():
        for pattern in patterns:
            if "." in pattern:
                evidence = next(
                    (ev for host, ev in hosts if host and _host_matches(host, pattern)), None
                )
            else:
                body = next((b for b in script_bodies if pattern in b), None)
                evidence = pattern if body else None
            if evidence is not None:
                found[platform] = evidence[:EVIDENCE_MAX]
                break
    return tuple(sorted(found.items()))
