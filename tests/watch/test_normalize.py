"""Content hashing must be stable across cosmetic churn and sensitive to real change.

Every test here is either "these two must hash the same" (stability — a false
positive costs an LLM call) or "these two must hash differently" (sensitivity —
a false negative means a missed signal, which is far worse).
"""

from __future__ import annotations

from scripts.watch.normalize import content_hash, normalize_html


# --- STABILITY: cosmetic differences must NOT change the hash ---


def test_ignores_script_contents() -> None:
    a = "<html><body><h1>Jobs</h1><script>var t=1</script></body></html>"
    b = "<html><body><h1>Jobs</h1><script>var t=2</script></body></html>"
    assert content_hash(a) == content_hash(b)


def test_ignores_style_contents() -> None:
    a = "<html><body><style>.a{color:red}</style><p>Jobs</p></body></html>"
    b = "<html><body><style>.a{color:blue}</style><p>Jobs</p></body></html>"
    assert content_hash(a) == content_hash(b)


def test_ignores_whitespace_differences() -> None:
    assert content_hash("<div>  Senior   Engineer </div>") == content_hash(
        "<div>Senior Engineer</div>"
    )


def test_ignores_attribute_changes() -> None:
    """CSRF tokens, nonces, and cache-busting attrs differ on every request."""
    a = '<form csrf-token="abc123"><input name="q" data-v="1"></form>'
    b = '<form csrf-token="xyz789"><input name="q" data-v="2"></form>'
    assert content_hash(a) == content_hash(b)


def test_ignores_html_comments() -> None:
    a = "<div><!-- rendered 12:00:01 --><p>Jobs</p></div>"
    b = "<div><!-- rendered 12:04:37 --><p>Jobs</p></div>"
    assert content_hash(a) == content_hash(b)


def test_ignores_noscript_and_iframe_contents() -> None:
    a = "<div><p>Jobs</p><noscript>enable js</noscript><iframe src='/ad?1'></iframe></div>"
    b = "<div><p>Jobs</p><noscript>enable js</noscript><iframe src='/ad?2'></iframe></div>"
    assert content_hash(a) == content_hash(b)


def test_ignores_tag_structure_when_text_is_identical() -> None:
    """A CSS refactor that rewraps text must not read as a content change."""
    a = "<div><span>Senior</span> <span>Engineer</span></div>"
    b = "<div><p>Senior Engineer</p></div>"
    assert content_hash(a) == content_hash(b)


# --- SENSITIVITY: real content changes MUST change the hash ---


def test_detects_added_text() -> None:
    a = "<div><h2>Senior Engineer</h2></div>"
    b = "<div><h2>Senior Engineer</h2><h2>Staff Engineer</h2></div>"
    assert content_hash(a) != content_hash(b)


def test_detects_removed_text() -> None:
    a = "<div><h2>Senior Engineer</h2><h2>Staff Engineer</h2></div>"
    b = "<div><h2>Senior Engineer</h2></div>"
    assert content_hash(a) != content_hash(b)


def test_detects_changed_text() -> None:
    assert content_hash("<div>Senior Engineer</div>") != content_hash("<div>Staff Engineer</div>")


def test_word_boundaries_are_preserved() -> None:
    """Adjacent tags must not collapse into one word — 'AB' vs 'A B' are different
    pages, and a separator-less join would hash them identically."""
    assert content_hash("<span>A</span><span>B</span>") != content_hash("<span>AB</span>")


# --- ROBUSTNESS: malformed input must not raise ---


def test_handles_empty_string() -> None:
    assert content_hash("") == content_hash("")
    assert normalize_html("") == ""


def test_handles_document_with_no_body() -> None:
    assert isinstance(normalize_html("<html><head><title>x</title></html>"), str)


def test_handles_malformed_html() -> None:
    """Real pages are malformed constantly. A parser error must not kill a scan."""
    assert isinstance(normalize_html("<div><p>unclosed <span>tags"), str)


def test_handles_non_html_input() -> None:
    assert isinstance(normalize_html("just plain text, no tags at all"), str)


# --- HASH PROPERTIES ---


def test_hash_is_deterministic() -> None:
    html = "<div><h2>Senior Engineer</h2></div>"
    assert content_hash(html) == content_hash(html)


def test_hash_is_hex_sha256() -> None:
    digest = content_hash("<div>x</div>")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
