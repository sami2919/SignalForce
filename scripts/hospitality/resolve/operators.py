"""Who is behind a licence company, from its registry record; cluster companies by operator.

A record whose process name or address belongs to a registered agent or law firm says nothing
about the operator (one firm represents hundreds of unrelated companies), so it never groups
anything. Otherwise companies that share the person named on the record, or (when the record
names only the company itself) share an office address, are one operator.
"""

import re
import string
from collections.abc import Mapping, Sequence
from typing import Literal

from scripts.hospitality.config import RegistryConfig
from scripts.hospitality.models import AddressCount, OperatorCluster, RegistryRecord
from scripts.hospitality.resolve.normalize import normalize_address
from scripts.hospitality.sources.registry import COUNTS, count_key, normalize_company
from scripts.hospitality.store import DocStore

Kind = Literal["person", "office"]


def office_key(address: str, zip_code: str) -> str:
    return f"{normalize_address(address)}|{(zip_code or '')[:5]}"


def stored_counts(records: Sequence[RegistryRecord], store: DocStore) -> dict[str, int]:
    """Cached registry-wide company counts, keyed the way `is_agent` reads them."""
    cached = {c.key: c.companies for c in store.load(COUNTS, AddressCount)}
    out: dict[str, int] = {}
    for r in records:
        line = r.process_address_1 or r.process_address
        if r.process_address and line and r.process_zip:
            n = cached.get(count_key(line, r.process_zip))
            if n is not None:
                out[office_key(r.process_address, r.process_zip)] = n
    return out


def _marker_hit(text: str, marker: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(marker.lower())}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def is_agent(record: RegistryRecord, cfg: RegistryConfig, counts: Mapping[str, int]) -> bool:
    """True when the record points at a registered agent or law firm, not an operator."""
    text = " ".join(p for p in (record.process_name, record.process_address) if p).lower()
    if any(_marker_hit(text, m) for m in cfg.agent_markers):
        return True
    if record.process_address:
        n = counts.get(office_key(record.process_address, record.process_zip or ""), 0)
        if n > cfg.max_companies_per_address:
            return True
    return False


def _person(name: str) -> str:
    text = re.sub(r"^\s*c\s*/\s*o\s+", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text.lower())).strip()


# What the registry writes in the process name when the company receives its own papers.
_SELF_PLACEHOLDERS = frozenset(
    {"THE LIMITED LIABILITY COMPANY", "LIMITED LIABILITY COMPANY", "THE LLC", "THE CORPORATION",
     "THE COMPANY", "CORPORATION", "THE ENTITY"}
)  # fmt: skip


def operator_key(record: RegistryRecord) -> tuple[Kind, str] | None:
    """('person', name) when someone other than the company receives its papers; ('office',
    address key) when the company names only itself; None without usable process data."""
    if not record.found:
        return None
    own = normalize_company(record.entity_name or record.legal_name)
    placeholder = normalize_company(record.process_name or "") in _SELF_PLACEHOLDERS
    if record.process_name and not placeholder and normalize_company(record.process_name) != own:
        person = _person(record.process_name)
        if person:
            return ("person", person)
    if record.process_address:
        return ("office", office_key(record.process_address, record.process_zip or ""))
    return None


def _label(kind: Kind, first: RegistryRecord) -> str:
    if kind == "person":
        name = re.sub(r"^\s*c\s*/\s*o\s+", "", first.process_name or "", flags=re.IGNORECASE)
        return f"{string.capwords(name.strip().lower())} (operator)"
    return f"Office at {string.capwords((first.process_address or '').strip().lower())}"


def cluster_operators(
    records_by_group: Mapping[str, Sequence[RegistryRecord]],
    group_names: Mapping[str, str],
    named_group_ids: frozenset[str],
    cfg: RegistryConfig,
    counts: Mapping[str, int],
) -> list[OperatorCluster]:
    """Clusters of groups that share an operator. Only clusters spanning 2+ groups, or holding
    a named group, are returned: a lone one-venue company is not a group."""
    members: dict[tuple[Kind, str], list[tuple[str, RegistryRecord]]] = {}
    for group_id, records in records_by_group.items():
        for record in records:
            if is_agent(record, cfg, counts):
                continue
            key = operator_key(record)
            if key is not None:
                members.setdefault(key, []).append((group_id, record))
    out: list[OperatorCluster] = []
    for (kind, value), rows in members.items():
        group_ids = tuple(dict.fromkeys(g for g, _ in rows))
        named = [g for g in group_ids if g in named_group_ids]
        if len(group_ids) < 2 and not named:
            continue
        label = group_names.get(named[0], named[0]) if named else _label(kind, rows[0][1])
        out.append(
            OperatorCluster(
                cluster_id=f"{kind}:{value}",
                kind="named_group" if named else kind,
                label=label,
                group_ids=group_ids,
                members=tuple(r for _, r in rows),
            )
        )
    return sorted(out, key=lambda c: c.label)
