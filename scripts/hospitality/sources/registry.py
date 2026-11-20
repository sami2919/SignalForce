"""NY company registry (data.ny.gov `n9v6-gdp6`): who receives each licence company's papers.

A licence company is usually one venue's own LLC. Its registry record names who receives its
legal papers: sometimes the operator (a person), sometimes an office the group's other companies
share, sometimes a law firm or registered agent (which says nothing). Lookups are exact-name,
cached in the store (found or not) and paid from a budget before every request.
"""

import re
from collections.abc import Sequence
from datetime import date

from scripts.hospitality.budget import CallBudget
from scripts.hospitality.models import AddressCount, RegistryRecord
from scripts.hospitality.store import DocStore

DOMAIN = "data.ny.gov"
DATASET = "n9v6-gdp6"
RECORDS = "registry_records"
COUNTS = "registry_address_counts"
NAME_COUNTS = "registry_name_counts"

_SUFFIXES = (
    (re.compile(r"\bL\s*\.?\s*L\s*\.?\s*C\b\.?"), "LLC"),
    (re.compile(r"\bINC\b\.?"), "INC"),
    (re.compile(r"\bCORP\b\.?"), "CORP"),
)


def normalize_company(name: str) -> str:
    """Uppercase, unify LLC / INC / CORP spellings, drop other punctuation, collapse spaces."""
    text = name.upper().replace("&", " AND ")
    for pattern, canon in _SUFFIXES:
        text = pattern.sub(canon, text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_SUFFIX_FORMS = {
    "LLC": ("LLC", "L.L.C.", "L.L.C"),
    "INC": ("INC", "INC."),
    "CORP": ("CORP", "CORP."),
}


_RAW_SUFFIX = re.compile(r",?\s*(L\.?\s*L\.?\s*C\.?|INC\.?|CORP\.?)\s*$")


def name_variants(name: str) -> list[str]:
    """Exact spellings to ask the registry for: the name as given, its normalised form, and
    each base (raw and normalised) with each common spelling of its legal suffix, with and
    without a comma. Bounded and exact: the results are still compared by `normalize_company`."""
    raw = re.sub(r"\s+", " ", name.upper().strip())
    key = normalize_company(name)
    out = {raw, key}
    suffix = key.rpartition(" ")[2]
    bases = {key.rpartition(" ")[0]}
    if _RAW_SUFFIX.search(raw):
        bases.add(_RAW_SUFFIX.sub("", raw).strip())
    for base in bases:
        for form in _SUFFIX_FORMS.get(suffix, ()):
            out |= {f"{base} {form}", f"{base}, {form}"}
    return sorted(out)


def registry_link(dos_id: str) -> str:
    return f"https://data.ny.gov/resource/{DATASET}.json?dos_id={dos_id}"


def _quote(text: str) -> str:
    return text.replace("'", "''")


def _filed(row: dict) -> date | None:
    raw = row.get("initial_dos_filing_date") or ""
    try:
        return date.fromisoformat(raw[:10]) if raw else None
    except ValueError:
        return None


def _record(legal_name: str, rows: list[dict]) -> RegistryRecord:
    key = normalize_company(legal_name)
    same = [r for r in rows if normalize_company(r.get("current_entity_name", "")) == key]
    if not same:
        return RegistryRecord(name_key=key, legal_name=legal_name, found=False)
    same.sort(key=lambda r: (_filed(r) or date.min, r.get("dos_id", "")), reverse=True)
    best = same[0]
    address = " ".join(
        part
        for part in (best.get("dos_process_address_1"), best.get("dos_process_address_2"))
        if part
    )
    return RegistryRecord(
        name_key=key,
        legal_name=legal_name,
        found=True,
        dos_id=best.get("dos_id"),
        entity_name=best.get("current_entity_name"),
        filed=_filed(best),
        process_name=best.get("dos_process_name") or None,
        process_address=address or None,
        process_address_1=best.get("dos_process_address_1") or None,
        process_zip=(best.get("dos_process_zip") or "")[:5] or None,
        note=f"{len(same)} registry records with this name; newest filing used"
        if len(same) > 1
        else "",
    )


def lookup_companies(
    names: Sequence[str], client, budget: CallBudget, store: DocStore
) -> list[RegistryRecord]:
    """Registry records for `names`, from the cache or one request each (budget spent first).

    Each new lookup is saved as soon as it is made, so `BudgetExceeded` or an API error loses
    nothing already paid for.
    """
    cached = {r.name_key: r for r in store.load(RECORDS, RegistryRecord)}
    out: list[RegistryRecord] = []
    for name in dict.fromkeys(names):
        key = normalize_company(name)
        if key in cached:
            out.append(cached[key])
            continue
        budget.spend()
        where = " OR ".join(
            f"upper(current_entity_name) = '{_quote(v)}'" for v in name_variants(name)
        )
        rows = list(client.rows(DATASET, where=where))
        rec = _record(name, rows)
        store.save(RECORDS, [rec], key=lambda r: r.name_key)  # type: ignore[attr-defined]
        cached[key] = rec
        out.append(rec)
    return out


def name_count_key(name: str) -> str:
    return f"name|{normalize_company(name)}"


def count_companies_named(name: str, client, budget: CallBudget, store: DocStore) -> int:
    """How many registry companies name this party to receive their papers (cached). A real
    restaurateur has a handful; a law firm, accountant or management service has dozens."""
    key = name_count_key(name)
    for c in store.load(NAME_COUNTS, AddressCount):
        if c.key == key:
            return c.companies
    budget.spend()
    n = client.count(DATASET, where=f"upper(dos_process_name) = '{_quote(name.upper().strip())}'")
    store.save(NAME_COUNTS, [AddressCount(key=key, companies=n)], key=lambda c: c.key)  # type: ignore[attr-defined]
    return n


def count_key(address: str, zip_code: str) -> str:
    return f"{normalize_company(address)}|{zip_code}"


def count_companies_at(
    address: str, zip_code: str, client, budget: CallBudget, store: DocStore
) -> int:
    """How many registry companies receive papers at this address line and ZIP (cached)."""
    key = count_key(address, zip_code)
    for c in store.load(COUNTS, AddressCount):
        if c.key == key:
            return c.companies
    budget.spend()
    where = (
        f"upper(dos_process_address_1) = '{_quote(address.upper())}' "
        f"AND dos_process_zip like '{_quote(zip_code)}%'"
    )
    n = client.count(DATASET, where=where)
    store.save(COUNTS, [AddressCount(key=key, companies=n)], key=lambda c: c.key)  # type: ignore[attr-defined]
    return n
