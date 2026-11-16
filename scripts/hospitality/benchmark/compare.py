"""Score the SignalForce list and the plain-Claude runs against the same ground truth.

Both sides are scored the same way: a list of at most k distinct venues, a hit being a venue
in the truth set. SignalForce's venues are the ones carrying a counted signal in its top groups,
in rank order; Claude's are its items matched to the venue universe by the strict name rule.
"""

from collections.abc import Sequence
from itertools import combinations

from scripts.hospitality.benchmark.baseline import match_items
from scripts.hospitality.models import BaselineRun, BenchmarkResult, ScoredAccount, Venue
from scripts.hospitality.resolve.normalize import normalize_name

FAIRNESS_NOTE = (
    "Residual biases run both ways, so the result is not a lower bound for either side. They favor the "
    "Claude baseline: web search can read press published after the cutoff, and its list is "
    "not limited to venues with a license. They favor SignalForce: the truth set is openings we "
    "could tie to an on-premise license, the population its license signals target, and venue "
    "grouping and license-to-site matching were built with today's data. They count against "
    "Claude: the strict name match scores a real venue spelled differently as a non-venue."
)
SCOPE_NOTE = (
    "Compares hits, precision@k, duplicates, non-venues and run-to-run variance only, on the "
    "same unit (distinct venues, at most k per list); lead time is not comparable (Claude gives "
    "no dated signal)."
)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def sf_venue_list(
    ranked: Sequence[ScoredAccount], venue_of_signal: dict[str, str], k: int
) -> list[str]:
    """SignalForce's prediction as venues: in rank order, each group's venues that carry a
    counted (non-zero) signal, strongest first; distinct, at most k."""
    out: list[str] = []
    for acct in ranked:
        for c in sorted(acct.contributions, key=lambda c: (-c.contribution, c.signal_id)):
            vid = venue_of_signal.get(c.signal_id)
            if c.contribution > 0 and vid is not None and vid not in out:
                out.append(vid)
                if len(out) == k:
                    return out
    return out


def compare(
    sf_ranked: Sequence[ScoredAccount],
    venue_of_signal: dict[str, str],
    runs: Sequence[BaselineRun],
    truth: Sequence[Venue],
    universe: Sequence[Venue],
    k: int = 50,
) -> BenchmarkResult:
    """Hits against `truth` for SignalForce's top-k venues and for each Claude run's top k.

    `venue_of_signal` maps a signal id to the venue it was observed on. Claude items are matched
    to the venue universe deterministically: an item matching no venue is a non-venue
    (`claude_unmatched`); an item whose venue was already listed is a duplicate. When an item
    names several venues (namesakes), it stands for a truth venue if any candidate is one.
    """
    truth_ids = {v.venue_id for v in truth}
    sf = sf_venue_list(sf_ranked, venue_of_signal, k)
    sf_hits = sum(1 for vid in sf if vid in truth_ids)

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
            candidates = matches[i]
            if not candidates:
                miss += 1
                continue
            in_truth = sorted(candidates & truth_ids)
            vid = in_truth[0] if in_truth else min(candidates)
            if vid in seen:
                dup += 1
            else:
                seen.add(vid)
        hit = len(seen & truth_ids)
        hits.append(hit)
        precision.append(hit / len(items) if items else 0.0)
        dupes.append(dup)
        unmatched.append(miss)
        names = {f"name:{normalize_name(it.name)}" for i, it in enumerate(items) if not matches[i]}
        keysets.append(frozenset(seen | names))
    pairs = list(combinations(keysets, 2))
    jaccard = sum(_jaccard(a, b) for a, b in pairs) / len(pairs) if pairs else 1.0
    return BenchmarkResult(
        k=k,
        sf_hits=sf_hits,
        sf_precision_at_k=sf_hits / len(sf) if sf else 0.0,
        claude_hits=tuple(hits),
        claude_precision_at_k=tuple(precision),
        claude_duplicates=tuple(dupes),
        claude_unmatched=tuple(unmatched),
        claude_run_jaccard=jaccard,
        truth_total=len(truth_ids),
        notes=(FAIRNESS_NOTE, SCOPE_NOTE),
    )
