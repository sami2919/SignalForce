"""Turn user-typed text into clean registrable-looking domains, or say why not."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_SPLIT = re.compile(r"[\s,;]+")


class InvalidDomain(ValueError):
    pass


def normalize_domain(raw: str) -> str:
    """Return a lowercase hostname without scheme, userinfo, port, path or leading www."""
    text = raw.strip().lower()
    if not text:
        raise InvalidDomain("empty entry")
    host = urlsplit(text).netloc if "//" in text else text.split("/")[0]
    host = host.split("@")[-1].split(":")[0].rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    if len(host) > 253 or len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        raise InvalidDomain(f"{raw.strip()!r} is not a domain")
    if host.replace(".", "").isdigit():
        raise InvalidDomain(f"{raw.strip()!r} looks like an IP address")
    return host


def parse_domain_list(raw: str, limit: int) -> list[str]:
    """Split, normalize and de-duplicate (keeping order). Raises InvalidDomain naming every bad entry."""
    entries = [e for e in _SPLIT.split(raw) if e]
    good: list[str] = []
    bad: list[str] = []
    for entry in entries:
        try:
            domain = normalize_domain(entry)
        except InvalidDomain:
            bad.append(entry)
            continue
        if domain not in good:
            good.append(domain)
    if bad:
        raise InvalidDomain("not valid domains: " + ", ".join(bad))
    if len(good) > limit:
        raise InvalidDomain(f"at most {limit} domains at a time")
    return good
