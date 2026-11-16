"""Hard per-run call budgets for paid APIs."""


class BudgetExceeded(RuntimeError):
    """Raised when a call budget has been spent."""


class CallBudget:
    """Counts calls against a limit; raises BudgetExceeded once the limit is passed."""

    def __init__(self, name: str, limit: int) -> None:
        self.name = name
        self.limit = limit
        self.used = 0

    def spend(self, n: int = 1) -> None:
        if self.used + n > self.limit:
            raise BudgetExceeded(
                f"{self.name} budget exhausted: used {self.used} of {self.limit}, asked for {n}"
            )
        self.used += n
