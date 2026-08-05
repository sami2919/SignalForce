"""SQLAlchemy ORM for SignalForce. Every table carries tenant_id."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

# JSONB on Postgres, JSON on SQLite (tests)
JSONType = JSONB().with_variant(JSON(), "sqlite")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_yaml: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "domain"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    account_metadata: Mapped[dict] = mapped_column(JSONType, default=dict)

    tenant: Mapped[Tenant] = relationship()
    sources: Mapped[list["AccountSource"]] = relationship(back_populates="account")


class AccountSource(Base):
    """The URL registry. Resolved once, reused forever."""

    __tablename__ = "account_sources"
    __table_args__ = (
        UniqueConstraint("account_id", "source_type"),
        Index("ix_sources_due", "tenant_id", "active", "last_fetched_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolution_method: Mapped[str] = mapped_column(String(32), default="heuristic")
    last_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant: Mapped[Tenant] = relationship()
    account: Mapped[Account] = relationship(back_populates="sources")


class Probe(Base):
    """High-volume watch-layer log, one row per fetch.

    For independent ground-truth recall measurement, see `HoldoutScan`
    (ADR-0010) -- a separate table, not this one.
    """

    __tablename__ = "probes"
    __table_args__ = (Index("ix_probes_source_time", "account_source_id", "fetched_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    account_source_id: Mapped[int] = mapped_column(ForeignKey("account_sources.id"), nullable=False)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed: Mapped[bool] = mapped_column(Boolean, default=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped[Tenant] = relationship()
    account_source: Mapped[AccountSource] = relationship()
    scan_run: Mapped["ScanRun"] = relationship(back_populates="probes")


class HoldoutScan(Base):
    """Ground-truth deep-scan log for a small holdout of accounts (ADR-0010).

    Structurally close to `Probe` but deliberately NOT tied to a `ScanRun` --
    the deep scan has no watch-layer scan run to attach to (Decision 2).
    `changed` is computed against the most recent prior `HoldoutScan` row for
    the same `account_source_id`, never against `AccountSource.last_hash` --
    that field is the watch layer's own confirm-on-change state and this
    table must never write to it. Query `probes` for operational watch-layer
    behavior; query this table for independent recall ground truth.
    """

    __tablename__ = "holdout_scans"
    __table_args__ = (Index("ix_holdout_scans_source_time", "account_source_id", "fetched_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    account_source_id: Mapped[int] = mapped_column(ForeignKey("account_sources.id"), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed: Mapped[bool] = mapped_column(Boolean, default=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped[Tenant] = relationship()
    account_source: Mapped[AccountSource] = relationship()


class SignalEvent(Base):
    """A signal is a DIFF, not a snapshot."""

    __tablename__ = "signal_events"
    __table_args__ = (
        Index("ix_signal_events_account", "tenant_id", "account_id", "detected_at"),
        Index("ix_signal_events_type_time", "tenant_id", "signal_type", "detected_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    account_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_sources.id"), nullable=True
    )
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    scan_run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"), nullable=True)

    tenant: Mapped[Tenant] = relationship()
    account: Mapped[Account] = relationship()
    account_source: Mapped[AccountSource | None] = relationship()
    scan_run: Mapped["ScanRun | None"] = relationship(back_populates="signal_events")


class Score(Base):
    """Replayable trace."""

    __tablename__ = "scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    trace: Mapped[dict] = mapped_column(JSONType, default=dict)
    config_version: Mapped[str] = mapped_column(String(32), default="v1")

    tenant: Mapped[Tenant] = relationship()
    account: Mapped[Account] = relationship()


class RepoObservation(Base):
    """Ledger of GitHub repos seen by the agent+email scanner (ADR-0006, Task 2.2).

    Load-bearing state, not a cache: a repo is "new to us" iff it has no row
    here. Truncating this table silently re-seeds the next run and suppresses
    a day of signals (ADR-0006, Decision 5).
    """

    __tablename__ = "repo_observations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "full_name"),
        Index("ix_repo_observations_first_seen", "tenant_id", "first_seen_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    owner_login: Mapped[str] = mapped_column(String(255), nullable=False)
    html_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_gh: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pushed_at_gh: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stars_at_first_seen: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    tenant: Mapped[Tenant] = relationship()


class ScanRun(Base):
    """Run-level operational metrics."""

    __tablename__ = "scan_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    accounts_probed: Mapped[int] = mapped_column(Integer, default=0)
    sources_probed: Mapped[int] = mapped_column(Integer, default=0)
    changes_detected: Mapped[int] = mapped_column(Integer, default=0)
    confirm_rejected: Mapped[int] = mapped_column(Integer, default=0)
    robots_blocked: Mapped[int] = mapped_column(Integer, default=0)
    verify_calls: Mapped[int] = mapped_column(Integer, default=0)
    signals_emitted: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    p50_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    p95_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    tenant: Mapped[Tenant] = relationship()
    probes: Mapped[list[Probe]] = relationship(back_populates="scan_run")
    signal_events: Mapped[list[SignalEvent]] = relationship(back_populates="scan_run")
