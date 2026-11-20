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


# --- final-review fix pass --------------------------------------------------------------


def test_c1_address_counts_add_up_across_spellings(tmp_path) -> None:
    from scripts.hospitality.models import AddressCount
    from scripts.hospitality.resolve.operators import stored_counts
    from scripts.hospitality.sources.registry import COUNTS, count_key
    from scripts.hospitality.store import DocStore

    store = DocStore(f"sqlite:///{tmp_path}/m.db")
    store.save(COUNTS, [AddressCount(key=count_key("515 West 20th Street", "10011"), companies=14),
                        AddressCount(key=count_key("515 W 20TH ST", "10011"), companies=25)],
               key=lambda c: c.key)  # fmt: skip
    a = rec("A LLC", "Ozaneaux Ltd", "515 West 20th Street", "10011")
    b = rec("B LLC", "Ozaneaux Ltd", "515 W 20TH ST", "10011")
    counts = stored_counts([a, b], store)
    assert is_agent(a, CFG, counts) and is_agent(b, CFG, counts)


def test_c1_a_name_receiving_papers_for_many_companies_is_an_agent() -> None:
    from scripts.hospitality.resolve.operators import name_count_key

    r = rec("A LLC", "Ozaneaux Ltd", "515 West 20th Street", "10011")
    assert is_agent(r, CFG, {name_count_key("Ozaneaux Ltd"): 39})
    assert not is_agent(r, CFG, {name_count_key("Ozaneaux Ltd"): 3})


def test_i1_generic_process_names_never_form_a_person() -> None:
    for generic in ("C/O THE LLC", "LLC", "Attn: Managing Member", "THE CORPORATION", "N/A",
                    "Owner"):  # fmt: skip
        r = rec("A LLC", generic, "1 Main Street", "10001")
        assert operator_key(r) is None or operator_key(r)[0] == "office", generic
    a = rec("A LLC", "C/O THE LLC", "1 Main Street", "10001")
    b = rec("B LLC", "C/O THE LLC", "9 Other Road", "11211")
    assert cluster_operators({"g:a": [a], "g:b": [b]}, {}, frozenset(), CFG, {}) == []


def test_i2_accountants_and_law_firms_without_marker_spelling_are_agents() -> None:
    for name in ("Smith & Jones PC", "Acme Law Group", "Rivera Legal", "John Doe Esquire",
                 "Lee CPA", "Kim CPAs", "Park Accounting", "Best Accountants", "Tax Pros Inc",
                 "Doe & Associates"):  # fmt: skip
        assert is_agent(rec("A LLC", name, "1 Main Street", "10001"), CFG, {}), name


def test_i3_different_suites_are_different_offices() -> None:
    assert office_key("1 Main Street Suite 400", "10001") != office_key(
        "1 Main Street Suite 900", "10001"
    )


def test_i5_a_group_with_two_operator_keys_appears_once() -> None:
    a1 = rec("A1 LLC", "Pat Owner", "1 Main Street", "10001")
    a2 = rec("A2 LLC", "Sam Partner", "2 Main Street", "10001")
    b = rec("B LLC", "Pat Owner", "1 Main Street", "10001")
    c = rec("C LLC", "Sam Partner", "2 Main Street", "10001")
    clusters = cluster_operators({"g:a": [a1, a2], "g:b": [b], "g:c": [c]},
                                 {"g:a": "A", "g:b": "B", "g:c": "C"}, frozenset(), CFG, {})  # fmt: skip
    assert len(clusters) == 1 and set(clusters[0].group_ids) == {"g:a", "g:b", "g:c"}


def test_i6_a_record_without_a_known_count_is_not_clustered_when_counts_are_required() -> None:
    a = rec("A LLC", "Pat Owner", "1 Main Street", "10001")
    b = rec("B LLC", "Pat Owner", "1 Main Street", "10001")
    out = cluster_operators({"g:a": [a], "g:b": [b]}, {}, frozenset(), CFG, {},
                            require_counts=True)  # fmt: skip
    assert out == []
