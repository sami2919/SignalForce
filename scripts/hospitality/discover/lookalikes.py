"""Lookalikes: Exa findSimilar seeded with customer sites (working backwards from who bought).

A result becomes a low-prior `lookalike` signal only if its registrable domain is the website of
a known, non-customer venue. A similar website is not evidence that a venue exists in NYC, so
unresolved domains are logged for manual review and never become venues. Results that are
themselves customers (seed domain, or a venue the labels match) are dropped.
"""

import hashlib
import logging
from collections.abc import Sequence
from datetime import datetime

from scripts.hospitality.budget import BudgetExceeded
from scripts.hospitality.discover.exa import ExaClient
from scripts.hospitality.labels import customer_groups
from scripts.hospitality.models import CustomerLabel, Group, Signal, Venue
from scripts.hospitality.resolve.normalize import registrable_domain

logger = logging.getLogger(__name__)


def seed_url(seed: CustomerLabel) -> str | None:
    """The seed's site URL, or None when it has no usable domain."""
    domain = registrable_domain(seed.website_domain) if seed.website_domain else None
    return f"https://{domain}" if domain else None


def lookalike_signals(
    exa: ExaClient,
    seeds: Sequence[CustomerLabel],
    venues: Sequence[Venue],
    now: datetime,
    per_seed: int = 10,
    *,
    groups: Sequence[Group],
) -> list[Signal]:
    """One `lookalike` signal per (seed, resolved non-customer venue, result URL).

    `groups` is required so the customer gate also matches group names, exactly as every other
    consumer does (seeds are the full customer evidence, see `labels.customer_evidence`).
    """
    customer_gids = set(customer_groups(seeds, venues, groups))
    customer_domains = {
        d for s in seeds if s.website_domain and (d := registrable_domain(s.website_domain))
    }
    by_domain: dict[str, list[Venue]] = {}
    for v in venues:
        if v.group_id in customer_gids or not v.website:
            continue
        if (d := registrable_domain(v.website)) and d not in customer_domains:
            by_domain.setdefault(d, []).append(v)
    customer_domains |= {
        d
        for v in venues
        if v.group_id in customer_gids and v.website and (d := registrable_domain(v.website))
    }

    signals: dict[str, Signal] = {}
    for seed in seeds:
        url = seed_url(seed)
        if url is None:
            logger.info("skipping lookalike seed without a domain: %s", seed.name)
            continue
        try:
            results = exa.find_similar(url, num_results=per_seed)
        except BudgetExceeded as exc:  # keep what was found; the budget is a hard stop
            logger.warning("exa budget spent during lookalikes at seed %s: %s", seed.name, exc)
            break
        for res in results:
            domain = registrable_domain(res.url)
            if domain is None or domain in customer_domains:
                continue
            matched = by_domain.get(domain)
            if not matched:
                logger.info(
                    "unresolved lookalike domain %s (seed %s): %s", domain, seed.name, res.url
                )
                continue
            key = hashlib.sha1(f"{url}|{res.url}".encode()).hexdigest()[:8]
            for venue in matched:
                sid = f"lookalike:{venue.venue_id}:{key}"
                signals.setdefault(
                    sid,
                    Signal(
                        signal_id=sid,
                        signal_type="lookalike",
                        entity_id=venue.venue_id,
                        observed_at=now,
                        occurred_at=None,
                        source="exa_lookalike",
                        evidence_ref=f"{seed.name} ({url}) -> {res.url}",
                        detail=f"similar to customer {seed.name}",
                    ),
                )
    return list(signals.values())
