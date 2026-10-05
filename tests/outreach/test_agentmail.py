"""Tests for scripts/outreach/agentmail.py.

Every field name here is verified against AgentMail's real, live API docs
(fetched directly during Task 5.1, not assumed from the plan's reference code)
-- see the module docstring for the specific corrections this made. The
plan's own reference code read `data["address"]` for the inbox's email
address; the real API returns that field as `email`. A test built from the
plan's literal reference would have passed against a mock that encoded the
same wrong assumption and failed the moment it touched the real API.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.api_client import APIError
from scripts.outreach.agentmail import AgentMailClient


@patch.object(AgentMailClient, "post")
def test_create_inbox_returns_id_and_email(mock_post):
    mock_post.return_value = {
        "pod_id": "pod_1",
        "inbox_id": "ib_123",
        "email": "a@x.agentmail.to",
        "updated_at": "2026-08-07T00:00:00Z",
        "created_at": "2026-08-07T00:00:00Z",
    }
    inbox = AgentMailClient(api_key="k").create_inbox("outbound")
    assert inbox.inbox_id == "ib_123"
    assert inbox.email == "a@x.agentmail.to"


@patch.object(AgentMailClient, "post")
def test_create_inbox_sends_username_and_domain(mock_post):
    mock_post.return_value = {
        "pod_id": "pod_1",
        "inbox_id": "ib_123",
        "email": "a@custom.com",
        "updated_at": "2026-08-07T00:00:00Z",
        "created_at": "2026-08-07T00:00:00Z",
    }
    AgentMailClient(api_key="k").create_inbox("outbound", domain="custom.com")
    mock_post.assert_called_once_with(
        "/inboxes", json_data={"username": "outbound", "domain": "custom.com"}
    )


@patch.object(AgentMailClient, "post")
def test_create_inbox_omits_domain_when_not_given(mock_post):
    mock_post.return_value = {
        "pod_id": "pod_1",
        "inbox_id": "ib_123",
        "email": "a@agentmail.to",
        "updated_at": "2026-08-07T00:00:00Z",
        "created_at": "2026-08-07T00:00:00Z",
    }
    AgentMailClient(api_key="k").create_inbox("outbound")
    mock_post.assert_called_once_with("/inboxes", json_data={"username": "outbound"})


@patch.object(AgentMailClient, "post")
def test_send_returns_thread_id_and_message_id(mock_post):
    mock_post.return_value = {"thread_id": "th_9", "message_id": "msg_1"}
    sent = AgentMailClient(api_key="k").send(
        inbox_id="ib_123", to="p@acme.com", subject="s", text="b"
    )
    assert sent.thread_id == "th_9"
    assert sent.message_id == "msg_1"


@patch.object(AgentMailClient, "post")
def test_send_posts_the_correct_endpoint_and_body(mock_post):
    mock_post.return_value = {"thread_id": "th_9", "message_id": "msg_1"}
    AgentMailClient(api_key="k").send(inbox_id="ib_123", to="p@acme.com", subject="s", text="b")
    mock_post.assert_called_once_with(
        "/inboxes/ib_123/messages/send",
        json_data={"to": ["p@acme.com"], "subject": "s", "text": "b"},
    )


@patch.object(AgentMailClient, "get")
def test_get_thread_returns_the_raw_response(mock_get):
    mock_get.return_value = {"thread_id": "th_9", "message_count": 2}
    result = AgentMailClient(api_key="k").get_thread(inbox_id="ib_123", thread_id="th_9")
    assert result == {"thread_id": "th_9", "message_count": 2}
    mock_get.assert_called_once_with("/inboxes/ib_123/threads/th_9")


@patch.object(AgentMailClient, "post")
def test_api_errors_propagate_from_create_inbox(mock_post):
    mock_post.side_effect = APIError(status_code=401, message="bad key", url="/inboxes")
    with pytest.raises(APIError):
        AgentMailClient(api_key="bad").create_inbox("x")


@patch.object(AgentMailClient, "post")
def test_api_errors_propagate_from_send(mock_post):
    mock_post.side_effect = APIError(status_code=401, message="bad key", url="/messages/send")
    with pytest.raises(APIError):
        AgentMailClient(api_key="bad").send(inbox_id="ib_1", to="p@acme.com", subject="s", text="b")


def test_client_sets_bearer_auth_header():
    client = AgentMailClient(api_key="sk-test-123")
    assert client._session.headers["Authorization"] == "Bearer sk-test-123"


def test_client_uses_the_real_v0_base_url():
    client = AgentMailClient(api_key="k")
    assert client.base_url == "https://api.agentmail.to/v0"
