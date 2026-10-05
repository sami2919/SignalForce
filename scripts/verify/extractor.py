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
from urllib.parse import urlsplit

import anthropic
import pydantic
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

You will be given a reduced representation of a careers/jobs listing page, in up to
three sections:

- the page's visible body text;
- an optional "PAGE DATA (JSON):" section containing the raw JSON payloads embedded
  in the page (Next.js/Nuxt hydration state, schema.org JobPosting ld+json). On many
  sites this is where the REAL, COMPLETE job list lives while the rendered text shows
  only a few roles or none at all — read it carefully and treat job records found
  there as first-class, not as a fallback;
- a "LINKS:" section listing every link on the page as `link text <href>`.

This is NOT the raw page — non-content markup has already been stripped — but every
link's href is preserved exactly as it appeared in the HTML. If a section ends with
"[truncated]", the page exceeded a size cap and you are seeing a prefix; extract what
is present and do not infer anything about what was cut.

Your job is to identify every open job posting and extract, for each one:

- title: the job title exactly as displayed (e.g. "Senior Backend Engineer").
- location: the location as displayed, if the page shows one (e.g. "Remote - US",
  "San Francisco, CA"). Use null if no location is shown for that posting.
- url: the href from the matching entry in the LINKS section, exactly as it appears
  there — copy it verbatim. Do not invent, normalize, or resolve a relative URL to
  absolute. If the posting came from the PAGE DATA section, use the url/path field
  from that record verbatim instead. Use null only if the posting has genuinely no
  matching link — null is correct and safe; a reconstructed URL is not.

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
   requires JavaScript to render and neither the body text nor the PAGE DATA section
   has job content), return an empty jobs list rather than guessing.

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


# Minimum digits for a whole path segment to be trusted as a stable ATS id.
#
# Justification for 6 (this number is load-bearing and is pinned from BOTH sides by
# tests — `test_five_digit_segment_is_below_the_floor_and_degrades` fails if it drops
# to 5, `test_six_digit_segment_is_at_the_floor_and_is_accepted` fails if it rises to 7):
#   - 4 is wrong and was the original bug: a YEAR is exactly four digits, so
#     `/careers/2026/backend-eng` and `/careers/2026/frontend-eng` both resolved to a
#     confident, non-degraded identity_key of "2026" — two different jobs sharing one
#     key, which is precisely the whole-object-identity failure ADR-0007 Decision 1
#     exists to prevent, except worse because `identity_degraded` said False.
#   - 5 is still wrong: a US zip code, a short ordinal, or a page counter.
#   - 6 is the smallest floor that cannot collide with either. Measured real ids sit
#     well above it: Greenhouse 10 digits (5023394008, 50/50 on the live Anthropic
#     board), SmartRecruiters 15.
# Anything below the floor degrades visibly rather than being guessed at.
_MIN_NUMERIC_ID_DIGITS = 6

# A stable numeric id must be an ENTIRE path segment, not a digit run found anywhere
# in the URL. `re.search` over the whole URL was the original bug's second half: it
# matched the host (`acme2024.com` -> "2024"), the query string
# (`?limit=1000` -> "1000"), and digits embedded inside a longer slug
# (`senior-engineer-2026` -> "2026"). Anchoring to a full segment removes all three.
_NUMERIC_ID_SEGMENT_PATTERN = re.compile(rf"^\d{{{_MIN_NUMERIC_ID_DIGITS},}}$")

# Some ATS platforms (Ashby, observed on modal.com's Ashby-hosted board; Lever) key
# jobs by a UUID path segment instead of a Greenhouse-style plain number. A UUID is
# exactly as stable as a numeric id. It is checked as its own path first because
# scanning for a digit run would otherwise grab an arbitrary substring from inside
# the UUID (e.g. "8258950" out of "...-dd8258950aec") and silently call that "the id".
_UUID_SEGMENT_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _path_segments(url: str) -> list[str]:
    """Non-empty path segments of `url`, with scheme, host, query and fragment gone.

    `urlsplit` handles absolute and relative URLs alike, so the host can never leak a
    digit run into the id and neither can a tracking parameter.
    """
    return [segment for segment in urlsplit(url).path.split("/") if segment]


def _derive_identity(raw: _RawJob) -> tuple[str, bool]:
    """Return (identity_key, degraded) for a raw job extraction.

    Preferred identity: a stable id that occupies a WHOLE segment of the URL's path —
    either a UUID (Ashby, Lever) or a numeric id of at least `_MIN_NUMERIC_ID_DIGITS`
    digits (Greenhouse and similar). Only the path is searched: the scheme, host,
    query string and fragment are discarded first, because none of them carry a job
    id and all of them carry digits that look like one.

    Ambiguity degrades, it never guesses. If two or more segments are plausible ids,
    picking "the first one" would be a silent coin flip on which is the real key, so
    the fallback is taken instead and flagged.

    Where no URL or no unambiguous stable id is present, fall back to a declared tuple
    of semantically identifying fields (title + location) — visibly marked degraded.
    `identity_degraded=True` makes the fallback observable to any downstream consumer
    (the differ, source health, a human reading a dump) rather than reintroducing
    whole-object/title-only identity wearing a hat.

    Known accepted cost: a job board that carries its id ONLY in a query parameter
    (e.g. a Greenhouse iframe embed's `?gh_jid=5023394008`) now degrades instead of
    resolving. That is deliberate. Reading ids out of arbitrary query parameters is
    what produced `?limit=1000` -> "1000"; degrading is visibly wrong-but-known,
    whereas guessing is invisibly wrong. Revisit with a named-parameter allowlist if
    a real source is measured to need it.
    """
    if raw.url:
        segments = _path_segments(raw.url)

        uuids = [seg for seg in segments if _UUID_SEGMENT_PATTERN.match(seg)]
        if len(uuids) == 1:
            return uuids[0], False

        numerics = [seg for seg in segments if _NUMERIC_ID_SEGMENT_PATTERN.match(seg)]
        if len(uuids) == 0 and len(numerics) == 1:
            return numerics[0], False

        if len(uuids) > 1 or len(numerics) > 1:
            logger.warning(
                "ambiguous stable id in job url %r (%d uuid, %d numeric candidates); "
                "degrading to title+location rather than guessing",
                raw.url,
                len(uuids),
                len(numerics),
            )

    fallback_key = f"title:{raw.title}|location:{raw.location or ''}"
    return fallback_key, True


# Non-content tags whose text/attributes never carry a job. Superset of
# scripts/watch/normalize.py's _DROP_TAGS: extraction also drops <head>, <link>,
# and <meta>, which normalize_html leaves (harmless there — .text() never reads
# them anyway) but which are pure noise once we're emitting an href-annotated
# text blob.
#
# `script` IS in this list, but only AFTER `_collect_script_data` has lifted the
# inert JSON payloads out of it — see that function for why that ordering matters.
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

# <script> types that are DATA, not code. Both are inert to a browser and to us,
# and both routinely carry the complete job list on pages where the rendered HTML
# carries only part of it (or none of it):
#   - application/json      — Next.js `__NEXT_DATA__`, Nuxt, SvelteKit hydration
#                             payloads. Measured live: a page with one static
#                             anchor plus two jobs in `__NEXT_DATA__` extracted
#                             4 jobs from raw HTML and 1 after a blanket script
#                             drop — a silent recall regression, no error, no
#                             degraded flag.
#   - application/ld+json   — schema.org JobPosting, the standard structured
#                             representation of a careers page and the single
#                             highest-quality source of job facts available.
# Everything else (no type, text/javascript, module) is executable code and stays
# dropped. This narrows the drop; it does not remove it.
_DATA_SCRIPT_TYPES = frozenset({"application/json", "application/ld+json"})

# Cap on the non-link body text carried alongside the link list, characters not
# tokens (a token-precise cap needs a tokenizer call per page; this is a coarse,
# free guard against a pathological page with megabytes of body prose and no
# links). Generous relative to every page measured in the ADR-0008 appendix.
_MAX_BODY_CHARS = 20_000

# Cap on the LINKS section. Previously uncapped, which meant the body cap only
# guarded half the request: a page with 3,000 job-shaped anchors measured ~87,800
# tokens after stripping — 16.8x the 5,236-token Greenhouse figure ADR-0008's
# amended cost model is built on. 40,000 chars is ~11k tokens, roughly 2x the
# measured Greenhouse page, which keeps every real board seen so far intact.
_MAX_LINKS_CHARS = 40_000

# Cap on the lifted script-data section. `__NEXT_DATA__` blobs are routinely
# hundreds of kilobytes, most of it routing and i18n state rather than jobs, so
# this section needs a bound for the same reason the other two do.
_MAX_SCRIPT_DATA_CHARS = 20_000

_TRUNCATION_MARKER = "\n[truncated]"


def _collect_script_data(tree: HTMLParser) -> str:
    """Return the concatenated text of inert JSON <script> payloads, capped.

    Must run BEFORE the `_DROP_TAGS` sweep, for two reasons: that sweep decomposes
    `script`, and it also decomposes `head` — where `application/ld+json` almost
    always lives. Lifting the payload into its own section is what lets both tags
    stay in the drop list.
    """
    blocks: list[str] = []
    used = 0
    truncated = False
    for node in tree.css("script"):
        script_type = (node.attributes.get("type") or "").strip().lower()
        if script_type not in _DATA_SCRIPT_TYPES:
            continue
        text = (node.text() or "").strip()
        if not text:
            continue
        remaining = _MAX_SCRIPT_DATA_CHARS - used
        if remaining <= 0:
            truncated = True
            break
        if len(text) > remaining:
            text = text[:remaining]
            truncated = True
        blocks.append(text)
        used += len(text)

    if not blocks:
        return ""
    if truncated:
        logger.warning(
            "script-data section truncated at %d chars; a hydration payload larger "
            "than the cap may hide jobs from extraction",
            _MAX_SCRIPT_DATA_CHARS,
        )
        blocks.append(_TRUNCATION_MARKER)
    return "\n".join(blocks)


def _collect_links(root) -> str:
    """Return the `link text <href>` list for every anchor under `root`, capped."""
    parts: list[str] = []
    used = 0
    for anchor in root.css("a"):
        href = anchor.attributes.get("href", "")
        text = anchor.text(separator=" ", strip=True)
        if not (text or href):
            continue
        entry = f"{text} <{href}>"
        if used + len(entry) > _MAX_LINKS_CHARS:
            logger.warning(
                "links section truncated at %d chars (%d links emitted); a link-dense "
                "page may have jobs beyond the cap",
                _MAX_LINKS_CHARS,
                len(parts),
            )
            parts.append(_TRUNCATION_MARKER)
            break
        parts.append(entry)
        used += len(entry) + 1
    return "\n".join(parts)


def _strip_for_extraction(html: str) -> str:
    """Href-preserving reduction: lift inert JSON payloads, drop non-content tags,
    keep every anchor's link text paired with its href, cap each section.

    Measured (ADR-0008 Decision 1 amendment, Task 2.1c):
      greenhouse/anthropic  33,411 -> ~5,236 tokens  (84% cut), job ids survive
      railway.app          179,561 -> ~2,662 tokens  (99% cut), job ids survive

    This is NOT scripts.watch.normalize.normalize_html and must never become it:
    that function is documented to exclude every attribute for hashing stability.
    This one exists specifically to KEEP the href that carries a fact's identity
    key (ADR-0007 Decision 1) while discarding the surrounding markup weight.

    Every section is capped and every truncation is logged. The failure mode of
    stripping is silent data loss, so nothing here is allowed to shrink the input
    without saying so.
    """
    if not html:
        return ""

    try:
        tree = HTMLParser(html)

        # Before the drop sweep: <script> and <head> are both dropped below.
        script_data = _collect_script_data(tree)

        for tag in _DROP_TAGS:
            for node in tree.css(tag):
                node.decompose()

        root = tree.body if tree.body is not None else tree.root
        if root is None:
            return html

        links = _collect_links(root)
        body_text = " ".join(root.text(separator=" ").split())[:_MAX_BODY_CHARS]

        sections = [body_text]
        if script_data:
            sections.append("PAGE DATA (JSON):\n" + script_data)
        sections.append("LINKS:\n" + links)
        return "\n\n".join(sections)
    except Exception:  # noqa: BLE001
        # Same posture as normalize_html: a parse failure must degrade to sending
        # the raw bytes, never abort the extraction over one malformed page.
        logger.warning("HTML strip-for-extraction failed; sending raw HTML", exc_info=True)
        return html


def _default_client() -> Anthropic:
    """Build the default client, or raise `ExtractorError` if the key is absent.

    Uses the module's own error class rather than `ValueError` so that a caller can
    wrap the whole extraction in one `except ExtractorError` and be sure nothing
    from this module escapes it.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ExtractorError("ANTHROPIC_API_KEY not set — run: export ANTHROPIC_API_KEY=sk-...")
    return Anthropic(api_key=api_key)


def _warn_on_identity_collisions(jobs: list[JobFact]) -> None:
    """Log any identity key claimed by more than one fact in a single snapshot.

    The extractor never merges colliding facts — every extracted job is returned —
    but a downstream differ keyed by `identity_key` would, and one of the two would
    vanish as a spurious `removed` (ADR-0007 Decision 3's flood in miniature).

    The degraded fallback key is title+location, so two genuinely different reqs
    with the same title and location collide by construction. That is not an edge
    case: railway.app measured 16/16 facts on the degraded path, and duplicate-titled
    open reqs are routine on self-hosted boards. `identity_degraded=True` says "no
    stable id was found"; it does not say "this key is ambiguous". This does.
    """
    seen: dict[str, int] = {}
    for job in jobs:
        seen[job.identity_key] = seen.get(job.identity_key, 0) + 1
    for key, count in seen.items():
        if count > 1:
            logger.warning(
                "identity key collision: %d facts share identity key %r in one "
                "snapshot; a differ keyed on it would lose %d of them",
                count,
                key,
                count - 1,
            )


def extract_careers(html: str, *, client: Anthropic | None = None) -> CareersFacts:
    """Extract structured job facts from a careers page's raw HTML.

    Pure function: raw HTML in, `CareersFacts` out. Never call `normalize_html` on
    `html` before this — normalization strips the `href` attributes this function
    depends on (ADR-0008 Decision 1).

    Raises `ExtractorError` on any API failure. Never returns an empty `CareersFacts`
    to signal a failure — a page with genuinely zero open roles and a failed
    extraction call must never look the same to a caller.

    Thin wrapper over `extract_careers_with_usage` — see that function for a variant
    that also returns token usage (needed by scripts/verify/wiring.py for cost
    tracking, ADR-0014 Decision 5). This function's own behavior is unchanged by
    that split; it simply discards the usage half.
    """
    facts, _usage = extract_careers_with_usage(html, client=client)
    return facts


def extract_careers_with_usage(
    html: str, *, client: Anthropic | None = None
) -> tuple[CareersFacts, object]:
    """Same as `extract_careers`, but also returns the raw Anthropic `usage` object
    (the same one `extract_careers` already logs internally) for callers that need
    to compute a per-call cost — see scripts/verify/wiring.py.
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
    except (anthropic.AnthropicError, pydantic.ValidationError) as exc:
        # `anthropic.AnthropicError` is the SDK's own base, so this covers every
        # status error (rate limit, auth, overloaded, request-too-large, 5xx) and
        # every connection error (including APITimeoutError) in one clause, plus
        # APIResponseValidationError, which is NOT an APIStatusError and used to
        # escape.
        #
        # `pydantic.ValidationError` is the one that actually bites: when the model
        # hits max_tokens mid-JSON, Messages.parse -> parse_response -> parse_text
        # calls TypeAdapter.validate_json on truncated text and raises pydantic's
        # error directly, which is not an AnthropicError at all. That failure lands
        # on the biggest, highest-intent boards — exactly where an unhandled
        # exception is least acceptable.
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

    _warn_on_identity_collisions(jobs)
    return CareersFacts(jobs=tuple(jobs)), usage


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m scripts.verify.extractor <path-to-html-file>", file=sys.stderr)
        raise SystemExit(2)

    with open(sys.argv[1], encoding="utf-8") as fh:
        page_html = fh.read()

    result = extract_careers(page_html)
    print(result.model_dump_json(indent=2))
