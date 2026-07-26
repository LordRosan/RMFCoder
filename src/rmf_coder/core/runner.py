from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rmf_coder.core.bus.events import RunFinishedEvent, RunStartedEvent
from rmf_coder.core.config import RMFConfig
from rmf_coder.core.context import ExecutionContext
from rmf_coder.core.events.bus import EventBus, EventHandler
from rmf_coder.core.events.writer import EventWriter
from rmf_coder.core.llm.base import LLMProvider
from rmf_coder.core.llm.provider import AnthropicProvider
from rmf_coder.core.loop import AgentLoop
from rmf_coder.core.runs import RUNS_DIR, new_run_id
from rmf_coder.core.task.manager import TaskManager
from rmf_coder.core.tools.builtin import (
    BashTool,
    ListDirTool,
    ReadFileTool,
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskUpdateTool,
    WriteFileTool,
)
from rmf_coder.core.tools.registry import ToolRegistry
from rmf_coder.core.trace.provider import TracingProvider
from rmf_coder.core.trace.writer import TraceWriter


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class RunOutcome:
    status: str
    result: str
    reason: str | None


class AgentRunner:
    def __init__(
            self,
            config: RMFConfig,
            *,
            bus: EventBus | None = None,
            provider: LLMProvider | None = None,
            extra_handlers: list[EventHandler] | None = None,
            runs_dir: Path | None = None,
            trace: TraceWriter | None = None,
    ) -> None:
        self._config = config
        self._bus = bus
        self._provider = provider
        self._extra_handlers: list[EventHandler] = extra_handlers or []
        self._run_dir = runs_dir or RUNS_DIR
        self._trace = trace

    def _build_registry(self, task_manager: TaskManager) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(BashTool())
        registry.register(WriteFileTool())
        registry.register(ListDirTool())
        registry.register(TaskCreateTool(task_manager))
        registry.register(TaskUpdateTool(task_manager))
        registry.register(TaskListTool(task_manager))
        registry.register(TaskGetTool(task_manager))
        return registry

    async def run(self, goal: str, *, run_id: str | None = None) -> None:
        await self.run_and_capture(goal, run_id=run_id)

    async def run_and_capture(self, goal: str, *, run_id: str | None = None) -> RunOutcome:
        run_id = run_id or new_run_id()
        run_path = self._run_dir / run_id
        run_path.mkdir(parents=True, exist_ok=True)

        task_manager = TaskManager(run_path / ".tasks")

        bus = self._bus if self._bus is not None else EventBus()
        for h in self._extra_handlers:
            bus.subscribe(h)

        context = ExecutionContext(
            run_id=run_id,
            goal=goal,
            max_steps=self._config.agent.max_steps,
        )

        async with EventWriter(run_path / "events.jsonl") as writer:
            writer.subscribe(bus)
            await bus.publish(RunStartedEvent(run_id=run_id, goal=goal, ts=_now()))

            provider: LLMProvider = self._provider or AnthropicProvider(self._config.llm.default_model)
            if self._trace is not None:
                provider = TracingProvider(
                    provider,
                    self._trace,
                    include_payload=self._config.trace.include_llm_payload,
                )

            registry = self._build_registry(task_manager)
            loop = AgentLoop(provider, registry, bus)

            cancelled = False
            try:
                await loop.run(context)
            except asyncio.CancelledError:
                cancelled = True
                if not context.is_done():
                    context.mark_failed("cancelled")

            await bus.publish(
                RunFinishedEvent(
                    run_id=run_id,
                    status=context.status,
                    reason=context.reason,
                    steps=context.step,
                    ts=_now(),
                )
            )

        if cancelled:
            raise asyncio.CancelledError()

        return RunOutcome(
            status=context.status,
            result=context.result,
            reason=context.reason,
        )
