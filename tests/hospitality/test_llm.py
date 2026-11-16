from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from scripts.hospitality import llm
from scripts.hospitality.budget import BudgetExceeded


class Probe(BaseModel):
    ok: bool


@pytest.fixture(autouse=True)
def _fresh_budget() -> None:
    llm.reset_budget()


def _fake(stop_reason: str = "end_turn") -> Mock:
    fake = Mock()
    resp = fake.beta.messages.parse.return_value
    resp.parsed_output = Probe(ok=True)
    resp.stop_reason = stop_reason
    return fake


def test_structured_calls_parse_with_configured_model() -> None:
    fake = _fake()
    out = llm.structured(Probe, system="s", user="u", client=fake)
    kwargs = fake.beta.messages.parse.call_args.kwargs
    assert out == Probe(ok=True)
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["fallbacks"] == "default"
    assert kwargs["output_format"] is Probe


def test_structured_raises_on_refusal() -> None:
    with pytest.raises(llm.LLMRefusal):
        llm.structured(Probe, system="s", user="u", client=_fake("refusal"))


def test_structured_spends_budget() -> None:
    fake = _fake()
    for _ in range(600):
        llm.structured(Probe, system="s", user="u", client=fake)
    with pytest.raises(BudgetExceeded):
        llm.structured(Probe, system="s", user="u", client=fake)
