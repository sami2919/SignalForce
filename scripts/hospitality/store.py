"""SQLite document store: one table per kind, rows of (id, json, updated_at)."""

import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, delete, select
from sqlalchemy.dialects.sqlite import insert

T = TypeVar("T", bound=BaseModel)

_KIND_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DocStore:
    def __init__(self, url: str = "sqlite:///data/magic/magic.db") -> None:
        if url.startswith("sqlite:///") and ":memory:" not in url:
            from pathlib import Path

            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self._engine = create_engine(url)
        self._meta = MetaData()

    def _table(self, kind: str) -> Table:
        if not _KIND_RE.match(kind):
            raise ValueError(f"invalid kind: {kind!r}")
        table = self._meta.tables.get(kind)
        if table is None:
            table = Table(
                kind,
                self._meta,
                Column("id", String, primary_key=True),
                Column("json", Text, nullable=False),
                Column("updated_at", String, nullable=False),
            )
        table.create(self._engine, checkfirst=True)
        return table

    def save(self, kind: str, items: Sequence[BaseModel], key: Callable[[BaseModel], str]) -> int:
        """Upsert items by key; returns the number of distinct rows written."""
        table = self._table(kind)
        now = datetime.now(UTC).isoformat()
        rows = {key(i): i.model_dump_json() for i in items}
        if not rows:
            return 0
        with self._engine.begin() as conn:
            for k, js in rows.items():
                stmt = insert(table).values(id=k, json=js, updated_at=now)
                conn.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["id"], set_={"json": js, "updated_at": now}
                    )
                )
        return len(rows)

    def load(self, kind: str, model: type[T]) -> list[T]:
        table = self._table(kind)
        with self._engine.connect() as conn:
            rows = conn.execute(select(table.c.json).order_by(table.c.id)).all()
        return [model.model_validate_json(r[0]) for r in rows]

    def clear(self, kind: str) -> None:
        table = self._table(kind)
        with self._engine.begin() as conn:
            conn.execute(delete(table))
