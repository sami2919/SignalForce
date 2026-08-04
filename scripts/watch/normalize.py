"""Normalize HTML to a stable text representation before hashing.

The two-tier watch/verify design depends entirely on this being stable. Raw HTML
differs between two requests to an unchanged page — CSRF tokens, build hashes,
render timestamps, rotating ad slots. Hashing it directly makes every source look
changed on every run, which collapses the cheap watch layer into the expensive
verify layer and turns markup churn into "signals".

Strategy: drop non-content elements, extract visible text with word boundaries
preserved, collapse whitespace, hash. Attributes are excluded implicitly by
taking text only.

    <div class="x" data-nonce="9f3">  Senior   Engineer </div>
        -> "Senior Engineer"
        -> sha256 -> 3a7f...
"""

from __future__ import annotations

import hashlib
import logging
import re

from selectolax.parser import HTMLParser

logger = logging.getLogger(__name__)

# Elements whose contents are never user-visible content. Their text would
# otherwise churn the hash on every request.
_DROP_TAGS = ("script", "style", "noscript", "svg", "iframe", "template", "canvas")

_WHITESPACE = re.compile(r"\s+")


def normalize_html(raw: str) -> str:
    """Return the stable visible text of an HTML document.

    Never raises. Real pages are malformed constantly, and a parser failure must
    degrade to "treat the raw bytes as text" rather than kill an entire scan run.
    """
    if not raw:
        return ""

    try:
        tree = HTMLParser(raw)
        for tag in _DROP_TAGS:
            for node in tree.css(tag):
                node.decompose()
        for comment in tree.css("comment"):
            comment.decompose()
        # separator=" " keeps word boundaries: <span>A</span><span>B</span>
        # must not collapse to "AB", which would hash identically to a page
        # that genuinely says "AB".
        root = tree.body if tree.body is not None else tree.root
        text = root.text(separator=" ") if root is not None else ""
    except Exception:  # noqa: BLE001
        # Deliberate broad catch with a log: one unparseable page must not
        # abort a scan over thousands of sources. Falling back to the raw
        # string keeps the hash meaningful (it still changes when the page
        # changes) at the cost of being churn-sensitive for that one source.
        logger.warning("HTML parse failed; falling back to raw text", exc_info=True)
        text = raw

    return _WHITESPACE.sub(" ", text).strip()


def content_hash(raw: str) -> str:
    """sha256 hex digest of the normalized text. Stable across cosmetic churn."""
    return hashlib.sha256(normalize_html(raw).encode("utf-8")).hexdigest()
