from scripts.kana_demo import (
    build_queue_entries,
    format_queue_table,
    load_customer_zero_brief,
    run_kana_scan,
)


def test_run_kana_scan_sample_returns_results():
    config, results = run_kana_scan(sample=True)
    assert config.company.name == "Kana"
    assert results
    assert results[0].company_name == "Warmly"


def test_build_queue_entries_contains_required_operator_fields():
    config, results = run_kana_scan(sample=True)
    entries = build_queue_entries(results, config)
    first = entries[0]
    assert first.company
    assert first.recommended_titles
    assert "HubSpot" in first.hubspot_sync
    assert first.experiment_tag.endswith("-v1")


def test_format_queue_table_includes_route_and_next_action():
    config, results = run_kana_scan(sample=True)
    entries = build_queue_entries(results, config)
    table = format_queue_table(entries)
    assert "OPERATING QUEUE" in table
    assert "NEXT ACTION" in table
    assert entries[0].company in table


def test_load_customer_zero_brief_has_agents_and_plan():
    brief = load_customer_zero_brief()
    assert brief.agents
    assert brief.channel_plan
    assert "Customer Zero" in brief.title
