import pytest

from scripts.hospitality.budget import BudgetExceeded, CallBudget


def test_budget_hard_stops() -> None:
    b = CallBudget("places", limit=2)
    b.spend()
    b.spend()
    assert b.used == 2
    with pytest.raises(BudgetExceeded):
        b.spend()
    assert b.used == 2
