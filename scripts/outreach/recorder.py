"""Connects AgentMailClient.send() (Task 5.1) to the Outreach table (Task 5.0).

Neither knew about the other before this task (ADR-0023) -- sending a real
message created no Outreach row, so the reply webhook (Task 5.2) had nothing
to match a real inbound reply against.

`account_id` is a required argument, not derived from the contact's email
domain (ADR-0023 Decision 1): outreach in this system always follows a
persona/audience match against an account the resolver/scanner pipeline
already resolved, and a contact's email domain is not a reliable proxy for
that (personal addresses, subdomains, forwarding services).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.storage.models import Contact, Outreach


def _find_or_create_contact(
    session: Session,
    *,
    tenant_id: int,
    account_id: int,
    email: str,
    name: str,
    title: str,
    persona_id: int | None,
) -> Contact:
    existing = session.execute(
        select(Contact).where(Contact.tenant_id == tenant_id, Contact.email == email)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    contact = Contact(
        tenant_id=tenant_id,
        account_id=account_id,
        email=email,
        name=name,
        title=title,
        persona_id=persona_id,
    )
    session.add(contact)
    session.flush()
    return contact


def record_outreach(
    session: Session,
    *,
    tenant_id: int,
    account_id: int,
    contact_email: str,
    agentmail_inbox_id: str,
    agentmail_thread_id: str,
    sent_at: datetime,
    contact_name: str = "",
    contact_title: str = "",
    persona_id: int | None = None,
    audience_id: int | None = None,
    triggering_signal_ids: list[int] | None = None,
) -> Outreach:
    """Record a message that was actually sent via AgentMailClient.send().

    Call this AFTER a successful send, with that call's real inbox_id and
    thread_id -- Outreach.agentmail_thread_id is globally unique (ADR-0019),
    so recording the same thread twice raises IntegrityError on commit
    rather than silently duplicating or overwriting (ADR-0023 Decision 2).
    Does not commit; the caller controls the transaction boundary.
    """
    contact = _find_or_create_contact(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        email=contact_email,
        name=contact_name,
        title=contact_title,
        persona_id=persona_id,
    )

    outreach = Outreach(
        tenant_id=tenant_id,
        contact_id=contact.id,
        audience_id=audience_id,
        agentmail_inbox_id=agentmail_inbox_id,
        agentmail_thread_id=agentmail_thread_id,
        sent_at=sent_at,
        triggering_signal_ids=triggering_signal_ids or [],
    )
    session.add(outreach)
    session.flush()
    return outreach
