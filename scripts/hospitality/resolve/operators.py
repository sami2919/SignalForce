"""Who is behind a licence company, from its registry record; cluster companies by operator.

A record whose process name or address belongs to a registered agent, law firm, accountant or
other service (one firm represents hundreds of unrelated companies) never groups anything:
caught by marker words, or by the party or office receiving papers for more companies than
`max_companies_per_address` registry-wide (summed across spellings). Otherwise companies that
share the person named on the record, or (when the record names only the company itself)
share an office address including its suite, are one operator. Clusters that touch each other
through a shared group are merged, so a group appears once.
"""

import re
import string
from collections.abc import Mapping, Sequence
from typing import Literal

from scripts.hospitality.config import RegistryConfig
from scripts.hospitality.models import AddressCount, OperatorCluster, RegistryRecord
from scripts.hospitality.resolve.normalize import normalize_address
from scripts.hospitality.sources.registry import (
    COUNTS,
    NAME_COUNTS,
    count_key,
    name_count_key,
    normalize_company,
)
from scripts.hospitality.store import DocStore

Kind = Literal["person", "office"]

__all__ = [
    "cluster_operators",
    "is_agent",
    "name_count_key",
    "office_key",
    "operator_key",
    "stored_counts",
]

# What the registry writes in the process name when the company receives its own papers, or a
# role rather than a name: never an operator.
_SELF_PLACEHOLDERS = frozenset(
    {"THE LIMITED LIABILITY COMPANY", "LIMITED LIABILITY COMPANY", "THE LLC", "LLC", "INC",
     "CORP", "THE CORPORATION", "CORPORATION", "THE COMPANY", "COMPANY", "THE ENTITY",
     "THE CORPORATE", "MEMBER", "MEMBERS", "THE MEMBER", "THE MEMBERS", "MANAGING MEMBER",
     "THE MANAGING MEMBER", "MANAGER", "PRESIDENT", "OWNER", "N A", "NA", "NONE", "SAME"}
)  # fmt: skip
_PREFIX = re.compile(r"^\s*(c\s*/\s*o|attn\.?:?|attention:?)\s+", re.IGNORECASE)


def office_key(address: str, zip_code: str) -> str:
    """Address (suite kept: different tenants of one tower are different offices) + ZIP."""
    return f"{normalize_address(address, strip_unit=False)}|{(zip_code or '')[:5]}"


def stored_counts(records: Sequence[RegistryRecord], store: DocStore) -> dict[str, int]:
    """Cached registry-wide counts, keyed the way `is_agent` reads them: per office, summed
    across every spelling of that office seen; per party name receiving papers."""
    by_count_key = {c.key: c.companies for c in store.load(COUNTS, AddressCount)}
    out: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for r in records:
        line = r.process_address_1 or r.process_address
        if r.process_address and line and r.process_zip:
            ck = count_key(line, r.process_zip)
            ok = office_key(r.process_address, r.process_zip)
            if ck in by_count_key and (ok, ck) not in seen:
                seen.add((ok, ck))
                out[ok] = out.get(ok, 0) + by_count_key[ck]
    for c in store.load(NAME_COUNTS, AddressCount):
        out[c.key] = c.companies
    return out


def _marker_hit(text: str, marker: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(marker.lower())}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def is_agent(record: RegistryRecord, cfg: RegistryConfig, counts: Mapping[str, int]) -> bool:
    """True when the record points at an agent, law firm or service firm, not an operator."""
    text = " ".join(p for p in (record.process_name, record.process_address) if p).lower()
    if any(_marker_hit(text, m) for m in cfg.agent_markers):
        return True
    limit = cfg.max_companies_per_address
    office = office_key(record.process_address or "", record.process_zip or "")
    if record.process_address and counts.get(office, 0) > limit:
        return True
    party = name_count_key(_PREFIX.sub("", record.process_name or ""))
    return bool(record.process_name) and counts.get(party, 0) > limit


def _person(name: str) -> str:
    text = _PREFIX.sub("", name)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text.lower())).strip()


def operator_key(record: RegistryRecord) -> tuple[Kind, str] | None:
    """('person', name) when a named party other than the company receives its papers;
    ('office', address key) when the company names only itself (or a placeholder or role);
    None without usable process data."""
    if not record.found:
        return None
    own = normalize_company(record.entity_name or record.legal_name)
    name = _PREFIX.sub("", record.process_name or "")
    norm = normalize_company(name)
    usable = bool(name) and norm not in _SELF_PLACEHOLDERS and norm != own
    person = _person(name) if usable else ""
    if person and len(person.split()) >= 2:
        return ("person", person)
    if record.process_address:
        return ("office", office_key(record.process_address, record.process_zip or ""))
    return None


def _label(kind: Kind, first: RegistryRecord) -> str:
    if kind == "person":
        name = _PREFIX.sub("", first.process_name or "")
        return f"{string.capwords(name.strip().lower())} (operator)"
    return f"Office at {string.capwords((first.process_address or '').strip().lower())}"


def cluster_operators(
    records_by_group: Mapping[str, Sequence[RegistryRecord]],
    group_names: Mapping[str, str],
    named_group_ids: frozenset[str],
    cfg: RegistryConfig,
    counts: Mapping[str, int],
    *,
    require_counts: bool = False,
) -> list[OperatorCluster]:
    """Clusters of groups that share an operator. Only clusters spanning 2+ groups, or holding
    a named group, are returned: a lone one-venue company is not a group.

    `require_counts`: a record whose office has no stored count (a run stopped mid-counting)
    is left out rather than trusted, so an uncounted law firm cannot form a cluster.
    """
    rows: list[tuple[tuple[Kind, str], str, RegistryRecord]] = []
    for group_id, records in records_by_group.items():
        for record in records:
            if is_agent(record, cfg, counts):
                continue
            if (
                require_counts
                and record.process_address
                and (office_key(record.process_address, record.process_zip or "") not in counts)
            ):
                continue
            key = operator_key(record)
            if key is not None:
                rows.append((key, group_id, record))
    # Union keys that share a group, so one group lands in one cluster.
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for key, group_id, _ in rows:
        a, b = find(f"k:{key[0]}:{key[1]}"), find(f"g:{group_id}")
        if a != b:
            parent[a] = b
    components: dict[str, list[tuple[tuple[Kind, str], str, RegistryRecord]]] = {}
    for row in rows:
        components.setdefault(find(f"g:{row[1]}"), []).append(row)
    out: list[OperatorCluster] = []
    for comp in components.values():
        group_ids = tuple(dict.fromkeys(g for _, g, _ in comp))
        named = [g for g in group_ids if g in named_group_ids]
        if len(group_ids) < 2 and not named:
            continue
        kind, value = comp[0][0]
        label = group_names.get(named[0], named[0]) if named else _label(kind, comp[0][2])
        out.append(
            OperatorCluster(
                cluster_id=f"{kind}:{value}",
                kind="named_group" if named else kind,
                label=label,
                group_ids=group_ids,
                members=tuple(r for _, _, r in comp),
            )
        )
    return sorted(out, key=lambda c: c.label)
