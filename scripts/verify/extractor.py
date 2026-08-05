"""Verify-layer extraction: raw HTML -> structured facts.

ADR-0008 (docs/decisions/0008-verify-layer-extraction.md) is the spec. Three decisions
from that ADR shape this module:

1. **Raw HTML in, never `normalize_html`'s output.** `scripts/watch/normalize.py` strips
   every attribute (including `href`) to build a stable hash for the watch layer — that
   destroys the job id ADR-0007 Decision 1 depends on, so this module never calls it.
   What IS sent to the model is `_strip_for_extraction`'s href-preserving reduction (Task
   2.1c, ADR-0008 Decision 1 amendment, 2026-08-05): drop script/style/svg/etc., keep
   anchor hrefs paired with their link text. Measured 84-99% token reduction with the
   job ids fully preserved — this is NOT the watch layer's normalizer; it is a separate,
   extraction-specific reduction gated on reproducing the raw-HTML extraction baseline
   exactly (Task 2.1a Step 5: 50/50 stable ids on Greenhouse, 16 jobs on railway.app).
2. **Structured outputs, not prompt-and-parse.** `client.messages.parse(...)` with a
   Pydantic `output_format` constrains and validates the response inside the API.
   No "respond with only JSON" + `json.loads` retry loop, and no assistant-turn
   prefill (HTTP 400 on claude-opus-5).
3. **Every fact type declares an identity key** (ADR-0007 Decision 1). `Fact` enforces
   this at class-definition time via `__init_subclass__`, so a fact type missing a key
   fails at import, not at diff time.

Careers is the only source type implemented here (Task 2.1a). Adding another source
type means: a `_RawXFact`/`_RawXExtraction` pair (what the model extracts), an
`XFact(Fact)` with a declared `identity_fields`, an `XFacts` container, and an
`extract_x` function following the same shape as `extract_careers` below.
"""

from __future__ import annotations

import logging
import os
import re
from typing import ClassVar

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict
from selectolax.parser import HTMLParser

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5"
MAX_TOKENS = 8192

# The stable, cacheable half of the request. claude-opus-5's minimum cacheable prefix
# is 512 tokens — this prompt is deliberately long enough to clear that bar; if it were
# trimmed thin, caching would silently stop applying and nothing here would surface it
# (that is why Step 5 of the brief checks `usage.cache_read_input_tokens` directly
# rather than assuming this text is long enough forever).
_CAREERS_SYSTEM_PROMPT = """You are a structured-data extractor for company careers pages.

You will be given a reduced representation of a careers/jobs listing page: the page's
visible body text, followed by a "LINKS:" section listing every link on the page as
`link text <href>`. This is NOT the raw page — non-content markup has already been
stripped — but every link's href is preserved exactly as it appeared in the HTML.
Your job is to identify every open job posting and extract, for each one:

- title: the job title exactly as displayed (e.g. "Senior Backend Engineer").
- location: the location as displayed, if the page shows one (e.g. "Remote - US",
  "San Francisco, CA"). Use null if no location is shown for that posting.
- url: the href from the matching entry in the LINKS section, exactly as it appears
  there — copy it verbatim. Do not invent, normalize, or resolve a relative URL to
  absolute. Use null only if the posting has genuinely no matching link.

Rules that matter for correctness:

1. The href for each job is load-bearing: many job boards (Greenhouse, Lever, and
   similar ATS platforms) encode a stable numeric job id in that URL, and that id is
   how this page's changes get tracked over time. Losing it by paraphrasing or
   reconstructing the URL from the link text defeats the entire point of this
   extraction — always copy url from the LINKS section, never reconstruct it.

2. A page with zero open roles (e.g. "no open positions right now") is a completely
   legitimate result. Return an empty jobs list. Do not treat this as a failure, and
   do not invent placeholder jobs to avoid returning an empty list.

3. Do not deduplicate, merge, reorder, or editorialize. If the same job title appears
   twice with two different URLs, they are two separate postings — extract both. If
   the page lists the same posting twice with the same URL, extract it once.

4. Ignore navigation chrome, footer links, "life at company" content, benefits
   descriptions, and anything that is not itself a specific open job posting. A link
   to a general "/careers" or "/jobs" index page is not a job posting.

5. If the page is not a careers/jobs listing at all (wrong page, error page, page
   requires JavaScript to render and the raw HTML has no job content), return an
   empty jobs list rather than guessing.

Be exhaustive: a careers page with 50 open roles should yield 50 extracted jobs, not
a sample. Precision matters as much as recall — do not fabricate a job that is not
actually present in the HTML."""


class ExtractorError(Exception):
    """Raised when extraction fails outright.

    An API failure must never be swallowed into an empty `CareersFacts` — an empty
    result must be unambiguously "the page has no jobs", never "the call errored".
    Conflating the two is exactly the ambiguity Phase 3 exists to measure and remove.
    """


# ---------------------------------------------------------------------------
# Fact base: every fact type must declare a non-empty identity key at
# class-definition time (ADR-0007 Decision 1).
# ---------------------------------------------------------------------------


class Fact(BaseModel):
    """Base class for all verify-layer fact types.

    Subclasses MUST declare a non-empty `identity_fields: ClassVar[tuple[str, ...]]`
    naming the field(s) that make a fact the *same* fact across two snapshots. A
    subclass that omits this fails at class-definition time (import time), not
    silently at diff time — that is the whole point of ADR-0007 Decision 1.
    """

    model_config = ConfigDict(frozen=True)

    identity_fields: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        fields = getattr(cls, "identity_fields", ())
        if not fields:
            raise TypeError(
                f"{cls.__name__} must declare a non-empty `identity_fields` "
                "ClassVar naming its identity key(s) (ADR-0007 Decision 1: fact "
                "identity is a declared stable key, never the whole object)."
            )


# ---------------------------------------------------------------------------
# What the model extracts (LLM-facing schema — no identity-key logic here).
# ---------------------------------------------------------------------------


class _RawJob(BaseModel):
    """Raw per-job fields as extracted from the page, before identity derivation."""

    model_config = ConfigDict(frozen=True)

    title: str
    location: str | None = None
    url: str | None = None


class _RawCareersExtraction(BaseModel):
    """The `output_format` schema handed to `client.messages.parse`."""

    model_config = ConfigDict(frozen=True)

    jobs: list[_RawJob]


# ---------------------------------------------------------------------------
# What the extractor returns (identity-key logic lives here, in plain Python,
# not in the model's output — deterministic and independently testable).
# ---------------------------------------------------------------------------


class JobFact(Fact):
    """A single open job posting, keyed by its stable id where one exists."""

    identity_fields: ClassVar[tuple[str, ...]] = ("identity_key",)

    identity_key: str
    identity_degraded: bool
    title: str
    location: str | None = None
    url: str | None = None


class CareersFacts(BaseModel):
    """The structured result of extracting a careers page."""

    model_config = ConfigDict(frozen=True)

    jobs: tuple[JobFact, ...]


# A numeric id of 4+ digits embedded in the URL path/query, e.g. Greenhouse's
# `/jobs/5023394008`. Measured on the live Anthropic board (ADR-0008 appendix):
# 50 of 50 postings carry one. Short numbers (page params, years) are excluded by
# the length floor to avoid false-positive "stable ids" on paginated listings.
_NUMERIC_ID_PATTERN = re.compile(r"(\d{4,})")

# Some ATS platforms (Ashby, observed on modal.com's Ashby-hosted board) key jobs by
# a UUID as the final URL path segment instead of a Greenhouse-style plain number.
# A UUID is exactly as stable as a numeric id — scanning the whole URL for *any*
# digit run would instead grab an arbitrary substring from inside the UUID (e.g.
# "4430" out of "...-4430-...") and silently call that "the id", which is wrong even
# though it happens to still be unique per URL. Checked as its own path first.
_UUID_SEGMENT_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _derive_identity(raw: _RawJob) -> tuple[str, bool]:
    """Return (identity_key, degraded) for a raw job extraction.

    Preferred identity: a stable id found in the job's URL — either a UUID path
    segment (Ashby and similar) or a plain numeric id embedded anywhere in the URL
    (Greenhouse and similar). Where no URL or no stable id of either shape is
    present, fall back to a declared tuple of semantically identifying fields
    (title + location) — visibly marked degraded. This is never silent:
    `identity_degraded=True` on the fact makes the fallback path observable to any
    downstream consumer (the differ, source health, a human reading a dump), rather
    than reintroducing whole-object/title-only identity wearing a hat.
    """
    if raw.url:
        last_segment = raw.url.rstrip("/").split("/")[-1].split("?")[0]
        if _UUID_SEGMENT_PATTERN.match(last_segment):
            return last_segment, False

        match = _NUMERIC_ID_PATTERN.search(raw.url)
        if match:
            return match.group(1), False

    fallback_key = f"title:{raw.title}|location:{raw.location or ''}"
    return fallback_key, True


# Non-content tags whose text/attributes never carry a job. Superset of
# scripts/watch/normalize.py's _DROP_TAGS: extraction also drops <head>, <link>,
# and <meta>, which normalize_html leaves (harmless there — .text() never reads
# them anyway) but which are pure noise once we're emitting an href-annotated
# text blob.
_DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "template",
    "canvas",
    "head",
    "link",
    "meta",
)

# Cap on the non-link body text carried alongside the link list, characters not
# tokens (a token-precise cap needs a tokenizer call per page; this is a coarse,
# free guard against a pathological page with megabytes of body prose and no
# links). Generous relative to every page measured in the ADR-0008 appendix.
_MAX_BODY_CHARS = 20_000


def _strip_for_extraction(html: str) -> str:
    """Href-preserving reduction: drop non-content tags, keep every anchor's
    link text paired with its href, cap incidental body text.

    Measured (ADR-0008 Decision 1 amendment, Task 2.1c):
      greenhouse/anthropic  33,411 -> ~5,236 tokens  (84% cut), job ids survive
      railway.app          179,561 -> ~2,662 tokens  (99% cut), job ids survive

    This is NOT scripts.watch.normalize.normalize_html and must never become it:
    that function is documented to exclude every attribute for hashing stability.
    This one exists specifically to KEEP the href that carries a fact's identity
    key (ADR-0007 Decision 1) while discarding the surrounding markup weight.
    """
    if not html:
        return ""

    try:
        tree = HTMLParser(html)
        for tag in _DROP_TAGS:
            for node in tree.css(tag):
                node.decompose()

        root = tree.body if tree.body is not None else tree.root
        if root is None:
            return html

        links: list[str] = []
        for anchor in root.css("a"):
            href = anchor.attributes.get("href", "")
            text = anchor.text(separator=" ", strip=True)
            if text or href:
                links.append(f"{text} <{href}>")

        body_text = " ".join(root.text(separator=" ").split())[:_MAX_BODY_CHARS]
        return body_text + "\n\nLINKS:\n" + "\n".join(links)
    except Exception:  # noqa: BLE001
        # Same posture as normalize_html: a parse failure must degrade to sending
        # the raw bytes, never abort the extraction over one malformed page.
        logger.warning("HTML strip-for-extraction failed; sending raw HTML", exc_info=True)
        return html


def _default_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set — run: export ANTHROPIC_API_KEY=sk-...")
    return Anthropic(api_key=api_key)


def extract_careers(html: str, *, client: Anthropic | None = None) -> CareersFacts:
    """Extract structured job facts from a careers page's raw HTML.

    Pure function: raw HTML in, `CareersFacts` out. Never call `normalize_html` on
    `html` before this — normalization strips the `href` attributes this function
    depends on (ADR-0008 Decision 1).

    Raises `ExtractorError` on any API failure. Never returns an empty `CareersFacts`
    to signal a failure — a page with genuinely zero open roles and a failed
    extraction call must never look the same to a caller.
    """
    if client is None:
        client = _default_client()

    reduced = _strip_for_extraction(html)

    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": _CAREERS_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": reduced}],
            output_format=_RawCareersExtraction,
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        raise ExtractorError(f"careers extraction failed: {exc}") from exc

    parsed = response.parsed_output
    if parsed is None:
        raise ExtractorError(
            "careers extraction returned no parsed output "
            f"(stop_reason={getattr(response, 'stop_reason', 'unknown')!r})"
        )

    usage = response.usage
    logger.info(
        "careers extraction usage: input=%s output=%s cache_read=%s cache_creation=%s",
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
        getattr(usage, "cache_read_input_tokens", None),
        getattr(usage, "cache_creation_input_tokens", None),
    )

    jobs = []
    for raw in parsed.jobs:
        identity_key, degraded = _derive_identity(raw)
        jobs.append(
            JobFact(
                identity_key=identity_key,
                identity_degraded=degraded,
                title=raw.title,
                location=raw.location,
                url=raw.url,
            )
        )
    return CareersFacts(jobs=tuple(jobs))


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m scripts.verify.extractor <path-to-html-file>", file=sys.stderr)
        raise SystemExit(2)

    with open(sys.argv[1], encoding="utf-8") as fh:
        page_html = fh.read()

    result = extract_careers(page_html)
    print(result.model_dump_json(indent=2))
