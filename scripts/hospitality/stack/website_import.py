"""Hand-filled website CSV import (the fallback when search cannot find a site).

The file is untrusted: blank rows, extra columns, unknown ids, malformed URLs and filtered
domains are skipped and logged. Imported sites are marked `manual`. An existing site that was
found by search (or any non-manual source) is kept unless `overwrite` is set.
"""

import csv
import logging
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict

from scripts.hospitality.models import Venue, WebsiteLookup
from scripts.hospitality.resolve.normalize import registrable_domain
from scripts.hospitality.stack.website_search import NEVER_FETCH_DOMAINS, is_fetchable

logger = logging.getLogger(__name__)

MANUAL = "manual"
MAX_ROWS = 100_000
MAX_URL_LEN = 2048
_BAD_CHARS = re.compile(r"[\s\x00-\x1f\x7f]")


class ImportCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    imported: int = 0
    replaced: int = 0  # imported over an existing website (needs overwrite, or was manual)
    blank: int = 0
    unknown_id: int = 0
    bad_url: int = 0
    filtered_domain: int = 0
    duplicate: int = 0
    protected: int = 0  # existing non-manual site kept (no overwrite)


def clean_url(raw: str, excluded: Sequence[str]) -> tuple[str | None, str | None]:
    """(url, None) for an acceptable site, else (None, "bad_url" | "filtered_domain")."""
    text = raw.strip()
    if not text or len(text) > MAX_URL_LEN or _BAD_CHARS.search(text):
        return None, "bad_url"
    if "://" not in text:
        if ":" in text.split("/")[0]:  # javascript:, mailto: and friends
            return None, "bad_url"
        text = f"https://{text}"
    try:
        parts = urlsplit(text)
        host = parts.hostname
    except ValueError:
        return None, "bad_url"
    if (
        parts.scheme not in ("http", "https")
        or not host
        or "." not in host
        or parts.username
        or parts.password
    ):
        return None, "bad_url"
    domain = registrable_domain(text)
    if domain is None:
        return None, "bad_url"
    if domain in {d.lower() for d in excluded} | set(NEVER_FETCH_DOMAINS) or not is_fetchable(text):
        return None, "filtered_domain"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")), None


def plan_import(
    path: Path,
    venues: Sequence[Venue],
    existing: Sequence[WebsiteLookup],
    excluded: Sequence[str],
    *,
    overwrite: bool,
    today: date,
) -> tuple[list[WebsiteLookup], ImportCounts]:
    """The lookups to save from a CSV (columns `venue_id` or `camis`, and `website`)."""
    by_id = {v.venue_id: v for v in venues}
    by_camis = {v.camis: v.venue_id for v in venues if v.camis}
    known = {w.venue_id: w for w in existing}
    tally = dict.fromkeys(ImportCounts.model_fields, 0)
    out: dict[str, WebsiteLookup] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fields = {(f or "").strip().lower(): f for f in reader.fieldnames or []}
        if "website" not in fields or not ({"venue_id", "camis"} & fields.keys()):
            raise SystemExit(
                f"{path}: needs a `website` column and a `venue_id` (or `camis`) column; "
                f"found {sorted(fields)}"
            )

        def cell(row: dict, name: str) -> str:
            col = fields.get(name)
            return (row.get(col) or "").strip() if col else ""

        for n, row in enumerate(reader, start=2):
            if n > MAX_ROWS:
                logger.warning("import stopped at %d rows", MAX_ROWS)
                break
            vid, camis, raw = cell(row, "venue_id"), cell(row, "camis"), cell(row, "website")
            if not (vid or camis or raw):
                tally["blank"] += 1
                continue
            venue_id = vid if vid in by_id else by_camis.get(camis) if not vid else None
            if venue_id is None:
                logger.warning("import row %d skipped: unknown id %r", n, vid or camis)
                tally["unknown_id"] += 1
                continue
            url, why = clean_url(raw, excluded)
            if url is None:
                logger.warning("import row %d skipped (%s): %r", n, why, raw[:200])
                tally[why or "bad_url"] += 1
                continue
            if venue_id in out:
                logger.warning("import row %d skipped: %s repeated in the file", n, venue_id)
                tally["duplicate"] += 1
                continue
            prior = known.get(venue_id)
            current = (prior.website if prior else None) or by_id[venue_id].website
            manual = prior is not None and prior.verified_by == MANUAL
            if current and not manual and not overwrite:
                logger.warning(
                    "import row %d kept the existing site for %s (use --overwrite)", n, venue_id
                )
                tally["protected"] += 1
                continue
            if current:
                tally["replaced"] += 1
            tally["imported"] += 1
            out[venue_id] = WebsiteLookup(
                venue_id=venue_id,
                website=url,
                looked_up_on=today,
                source=MANUAL,
                verified_by=MANUAL,
            )
    return list(out.values()), ImportCounts(**tally)
