"""
M.A.Y.D.A.Y Base Tool — Abstract base class for all tools.
"""
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base for all MAYDAY tools. Every tool dispatches on _tool_name."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool category name (e.g., 'file', 'browser')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable tool description."""
        ...

    @abstractmethod
    def execute(self, parameters: dict) -> dict:
        """
        Execute the tool action.
        L3 FIX: parameters always contains '_tool_name' injected by engine.py.
        Implementations must dispatch on _tool_name.
        """
        ...

    def get_capabilities(self) -> list[str]:
        """Return list of sub-actions this tool supports."""
        return []

    def validate_parameters(self, parameters: dict) -> bool:
        """Validate parameters before execution. Override in subclasses."""
        return True
