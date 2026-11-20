"""Who is behind a licence company: drop agents and law firms, cluster by person or office."""

from scripts.hospitality.config import RegistryConfig
from scripts.hospitality.models import RegistryRecord
from scripts.hospitality.resolve.operators import (
    cluster_operators,
    is_agent,
    office_key,
    operator_key,
)

CFG = RegistryConfig()


def rec(legal: str, process: str | None, address: str | None, zip_code: str = "10016",
        found: bool = True) -> RegistryRecord:  # fmt: skip
    return RegistryRecord(
        name_key=legal.upper(),
        legal_name=legal,
        found=found,
        dos_id=f"id-{legal}" if found else None,
        entity_name=legal.upper() if found else None,
        process_name=process,
        process_address=address,
        process_zip=zip_code if found else None,
    )


def test_agent_markers_are_dropped() -> None:
    csc = rec("Cosme NY LLC", "CORPORATION SERVICE COMPANY", "80 STATE STREET", "12207")
    firm = rec(
        "Wonderworth LLC",
        "c/o golenbock eiseman assor bell & peskoe llp",
        "Attn: lawrence r. haut, esq. 711 third avenue, floor 17",
        "10017",
    )
    assert is_agent(csc, CFG, {}) and is_agent(firm, CFG, {})
    assert not is_agent(rec("Rip Raf LLC", "Matthew Maddy", "716 Marcy Avenue", "11216"), CFG, {})


def test_over_shared_address_is_dropped() -> None:
    r = rec("Some LLC", "Jane Doe", "1 Main Street", "10001")
    assert is_agent(r, CFG, {office_key("1 Main Street", "10001"): 26})
    assert not is_agent(r, CFG, {office_key("1 Main Street", "10001"): 25})


def test_office_key_unifies_spelling() -> None:
    assert office_key("16 East 40th Street", "10016") == office_key("16 E 40TH ST", "10016")


def test_operator_key_person_vs_office() -> None:
    assert operator_key(rec("Rip Raf LLC", "Matthew Maddy", "716 Marcy Avenue")) == (
        "person",
        "matthew maddy",
    )
    own = rec("65th Street Restaurant, LLC", "65TH STREET RESTAURANT, LLC", "16 EAST 40TH STREET")
    assert operator_key(own) == ("office", office_key("16 EAST 40TH STREET", "10016"))
    assert operator_key(rec("HTNY 1 Inc", None, None, found=False)) is None


def test_same_person_clusters_across_groups() -> None:
    clusters = cluster_operators(
        {
            "g:a": [rec("Rip Raf LLC", "Matthew Maddy", "716 Marcy Avenue")],
            "g:b": [rec("Bar Two LLC", "MATTHEW MADDY", "716 Marcy Ave")],
        },
        {"g:a": "RIP RAF LLC", "g:b": "BAR TWO LLC"},
        frozenset(),
        CFG,
        {},
    )
    [c] = clusters
    assert c.kind == "person" and set(c.group_ids) == {"g:a", "g:b"}
    assert c.label == "Matthew Maddy (operator)"


def test_same_office_clusters() -> None:
    clusters = cluster_operators(
        {
            "g:a": [rec("A Rest LLC", "A REST LLC", "16 East 40th Street")],
            "g:b": [rec("B Rest LLC", "B Rest, LLC", "16 E 40TH ST")],
        },
        {"g:a": "A REST LLC", "g:b": "B REST LLC"},
        frozenset(),
        CFG,
        {},
    )
    [c] = clusters
    assert c.kind == "office" and c.label == "Office at 16 East 40th Street"


def test_law_firm_never_clusters() -> None:
    firm = ("c/o golenbock eiseman assor bell & peskoe llp", "711 third avenue")
    records = {f"g:{i}": [rec(f"Co {i} LLC", *firm, "10017")] for i in range(3)}
    names = {g: g for g in records}
    assert cluster_operators(records, names, frozenset(), CFG, {}) == []


def test_named_group_label_wins() -> None:
    clusters = cluster_operators(
        {
            "g:a": [rec("Rip Raf LLC", "Matthew Maddy", "716 Marcy Avenue")],
            "g:b": [rec("Bar Two LLC", "Matthew Maddy", "716 Marcy Avenue")],
        },
        {"g:a": "Bar Susanne Group", "g:b": "BAR TWO LLC"},
        frozenset({"g:a"}),
        CFG,
        {},
    )
    assert clusters[0].label == "Bar Susanne Group"


def test_single_unnamed_group_is_not_a_cluster() -> None:
    clusters = cluster_operators(
        {"g:a": [rec("Rip Raf LLC", "Matthew Maddy", "716 Marcy Avenue")]},
        {"g:a": "RIP RAF LLC"},
        frozenset(),
        CFG,
        {},
    )
    assert clusters == []


def test_registry_placeholder_name_is_the_company_itself_not_a_person() -> None:
    # The registry writes "THE LIMITED LIABILITY COMPANY" when a company names itself; it is
    # not an operator, so two such companies at different addresses must not cluster.
    a = rec("Amis79 LLC", "THE LIMITED LIABILITY COMPANY", "79 Macdougal Street", "10012")
    b = rec("93 Greenwich LLC", "THE LIMITED LIABILITY COMPANY", "93 Greenwich Avenue", "10014")
    assert operator_key(a) == ("office", office_key("79 Macdougal Street", "10012"))
    clusters = cluster_operators({"g:a": [a], "g:b": [b]}, {"g:a": "A", "g:b": "B"},
                                 frozenset(), CFG, {})  # fmt: skip
    assert clusters == []
