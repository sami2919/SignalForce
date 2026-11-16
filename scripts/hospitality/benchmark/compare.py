"""Score the SignalForce list and the plain-Claude runs against the same ground truth."""

from collections.abc import Sequence
from itertools import combinations

from scripts.hospitality.benchmark.baseline import match_items
from scripts.hospitality.models import BaselineRun, BenchmarkResult, ScoredAccount, Venue
from scripts.hospitality.resolve.normalize import normalize_name

HINDSIGHT_NOTE = (
    "Hindsight leak favors the Claude baseline (it can read press published after the "
    "cutoff); a SignalForce win is conservative."
)
SCOPE_NOTE = (
    "Compares hits, precision@k, duplicates, non-venues and run-to-run variance only; "
    "lead time is not comparable (Claude gives no dated signal)."
)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def compare(
    sf_top: Sequence[ScoredAccount],
    sf_venues_by_group: dict[str, tuple[str, ...]],
    runs: Sequence[BaselineRun],
    truth: Sequence[Venue],
    universe: Sequence[Venue],
    k: int = 50,
) -> BenchmarkResult:
    """Hits against `truth` for the top-k SignalForce groups and for each Claude run.

    Claude items are matched to the venue universe deterministically: an item matching no
    venue is a non-venue (`claude_unmatched`); a second item matching an already-matched
    venue is a duplicate. Items matching a real, non-opening venue are neither.
    """
    truth_ids = {v.venue_id for v in truth}
    top = list(sf_top)[:k]
    sf_hits = sum(1 for a in top if truth_ids & set(sf_venues_by_group.get(a.group_id, ())))

    hits: list[int] = []
    precision: list[float] = []
    dupes: list[int] = []
    unmatched: list[int] = []
    keysets: list[frozenset[str]] = []
    for run in runs:
        items = run.items[:k]
        matches = match_items(items, universe)
        seen: set[str] = set()
        dup = miss = 0
        for i in range(len(items)):
            vid = matches[i]
            if vid is None:
                miss += 1
            elif vid in seen:
                dup += 1
            else:
                seen.add(vid)
        hit = len(seen & truth_ids)
        hits.append(hit)
        precision.append(hit / len(items) if items else 0.0)
        dupes.append(dup)
        unmatched.append(miss)
        names = {
            f"name:{normalize_name(it.name)}" for i, it in enumerate(items) if matches[i] is None
        }
        keysets.append(frozenset(seen | names))
    pairs = list(combinations(keysets, 2))
    jaccard = sum(_jaccard(a, b) for a, b in pairs) / len(pairs) if pairs else 1.0
    return BenchmarkResult(
        k=k,
        sf_hits=sf_hits,
        sf_precision_at_k=sf_hits / len(top) if top else 0.0,
        claude_hits=tuple(hits),
        claude_precision_at_k=tuple(precision),
        claude_duplicates=tuple(dupes),
        claude_unmatched=tuple(unmatched),
        claude_run_jaccard=jaccard,
        truth_total=len(truth_ids),
        notes=(HINDSIGHT_NOTE, SCOPE_NOTE),
    )
