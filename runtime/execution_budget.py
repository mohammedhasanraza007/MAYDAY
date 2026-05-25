from __future__ import annotations

from dataclasses import dataclass


MAX_STEPS_PER_TASK = 7
MAX_RETRIES = 2
MAX_RECOVERY_DEPTH = 1
MAX_PLANNING_DEPTH = 1
MAX_CONTEXT_GROWTH = 6000
MAX_BROWSER_CHAIN = 8
MAX_TOOL_CHAIN = 8


class ExecutionBudgetExceeded(RuntimeError):
    pass


@dataclass
class ExecutionBudget:
    max_steps: int = MAX_STEPS_PER_TASK
    max_retries: int = MAX_RETRIES
    max_recovery_depth: int = MAX_RECOVERY_DEPTH
    max_planning_depth: int = MAX_PLANNING_DEPTH
    max_context_growth: int = MAX_CONTEXT_GROWTH
    max_browser_chain: int = MAX_BROWSER_CHAIN
    max_tool_chain: int = MAX_TOOL_CHAIN

    steps: int = 0
    retries: int = 0
    recovery_depth: int = 0
    planning_depth: int = 0
    context_growth: int = 0
    browser_chain: int = 0
    tool_chain: int = 0

    def consume_step(self) -> None:
        self.steps += 1
        self._assert(self.steps <= self.max_steps, "MAX_STEPS_PER_TASK exceeded")

    def consume_retry(self) -> None:
        self.retries += 1
        self._assert(self.retries <= self.max_retries, "MAX_RETRIES exceeded")

    def enter_recovery(self) -> None:
        self.recovery_depth += 1
        self._assert(self.recovery_depth <= self.max_recovery_depth, "MAX_RECOVERY_DEPTH exceeded")

    def exit_recovery(self) -> None:
        self.recovery_depth = max(0, self.recovery_depth - 1)

    def enter_planning(self) -> None:
        self.planning_depth += 1
        self._assert(self.planning_depth <= self.max_planning_depth, "MAX_PLANNING_DEPTH exceeded")

    def exit_planning(self) -> None:
        self.planning_depth = max(0, self.planning_depth - 1)

    def add_context_growth(self, chars: int) -> None:
        self.context_growth += max(0, chars)
        self._assert(self.context_growth <= self.max_context_growth, "MAX_CONTEXT_GROWTH exceeded")

    def set_chain_lengths(self, tool_chain: int, browser_chain: int) -> None:
        self.tool_chain = max(self.tool_chain, tool_chain)
        self.browser_chain = max(self.browser_chain, browser_chain)
        self._assert(self.tool_chain <= self.max_tool_chain, "MAX_TOOL_CHAIN exceeded")
        self._assert(self.browser_chain <= self.max_browser_chain, "MAX_BROWSER_CHAIN exceeded")

    @staticmethod
    def _assert(condition: bool, message: str) -> None:
        if not condition:
            raise ExecutionBudgetExceeded(message)
