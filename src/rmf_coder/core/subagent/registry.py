from __future__ import annotations

import asyncio

from rmf_coder.core.context import ExecutionContext


class BackgroundTaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, tuple[asyncio.Task[None], ExecutionContext]] = {}

    def register(
            self,
            run_id: str,
            task: asyncio.Task[None],
            context: ExecutionContext
    ) -> None:
        self._tasks[run_id] = (task, context)

    def get(self, run_id: str) -> tuple[asyncio.Task[None], ExecutionContext] | None:
        return self._tasks.get(run_id)

    def all(self) -> list[tuple[asyncio.Task[None], ExecutionContext]]:
        return list(self._tasks.values())
