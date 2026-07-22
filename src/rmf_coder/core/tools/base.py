from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    error_type: str | None = None


class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict[str, object]

    @abstractmethod
    async def invoke(self, params: dict[str, object]) -> ToolResult: ...
