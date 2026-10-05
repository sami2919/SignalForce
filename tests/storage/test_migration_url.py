"""Alembic must use the DIRECT endpoint, never the pooled one.

PgBouncer in transaction mode can route consecutive statements to different
backend connections. A migration sent through it can partially apply and still
exit zero — a success report over a half-migrated schema.
"""

from __future__ import annotations

import pytest

from scripts.storage.session import migration_url

DIRECT = "postgresql+psycopg://u:p@ep-x.us-west-2.aws.neon.tech/db?sslmode=require"
POOLED = "postgresql+psycopg://u:p@ep-x-pooler.us-west-2.aws.neon.tech/db?sslmode=require"


def test_prefers_direct_when_both_are_set(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", POOLED)
    monkeypatch.setenv("DATABASE_URL_DIRECT", DIRECT)
    assert migration_url() == DIRECT


def test_falls_back_to_database_url_when_direct_absent(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", POOLED)
    monkeypatch.delenv("DATABASE_URL_DIRECT", raising=False)
    assert migration_url() == POOLED


def test_raises_when_neither_is_set(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_DIRECT", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        migration_url()


def test_empty_direct_falls_back_rather_than_using_empty_string(monkeypatch) -> None:
    """An empty env var is 'unset', not 'use the empty string'."""
    monkeypatch.setenv("DATABASE_URL", POOLED)
    monkeypatch.setenv("DATABASE_URL_DIRECT", "")
    assert migration_url() == POOLED
