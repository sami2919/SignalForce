import pytest

from scripts.registry.domains import InvalidDomain, normalize_domain, parse_domain_list


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("stripe.com", "stripe.com"),
        ("  Stripe.COM  ", "stripe.com"),
        ("https://www.stripe.com/jobs?x=1", "stripe.com"),
        ("http://stripe.com:8080/path", "stripe.com"),
        ("user:pw@evil.example", "evil.example"),
        ("stripe.com.", "stripe.com"),
        ("careers.example.co.uk", "careers.example.co.uk"),
    ],
)
def test_normalizes_common_inputs(raw, expected):
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "localhost", "10.0.0.1", "2130706433", "-bad.com", "bad-.com",
     "exa mple.com", "a..com", "http://", "foo_bar.com", "x" * 64 + ".com"],
)
def test_rejects_non_domains(raw):
    with pytest.raises(InvalidDomain):
        normalize_domain(raw)


def test_parse_splits_on_whitespace_commas_and_newlines_and_dedupes_in_order():
    assert parse_domain_list("a.com, b.com\nA.com  c.com;d.com", limit=25) == [
        "a.com", "b.com", "c.com", "d.com",
    ]


def test_parse_names_every_bad_entry():
    with pytest.raises(InvalidDomain, match="localhost.*10.0.0.1|10.0.0.1.*localhost"):
        parse_domain_list("good.com localhost 10.0.0.1", limit=25)


def test_parse_rejects_more_than_the_limit():
    raw = " ".join(f"d{i}.example.com" for i in range(26))
    with pytest.raises(InvalidDomain, match="at most 25"):
        parse_domain_list(raw, limit=25)
