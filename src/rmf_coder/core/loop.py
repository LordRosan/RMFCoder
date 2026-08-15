from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from rmf_coder.core.bus.events import StepStartedEvent, StepFinishedEvent
from rmf_coder.core.context import ExecutionContext
from rmf_coder.core.events.bus import EventBus
from rmf_coder.core.llm.base import LLMProvider
from rmf_coder.core.tools.invocation import invoke_tool
from rmf_coder.core.tools.registry import ToolRegistry


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AgentLoop:
    def __init__(
            self,
            provider: LLMProvider,
            registry: ToolRegistry,
            bus: EventBus,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._bus = bus

    async def run(self, context: ExecutionContext) -> None:
        while not context.is_done():
            context.step += 1
            await self._bus.publish(
                StepStartedEvent(run_id=context.run_id, step=context.step, ts=_now())
            )
            try:
                response = await self._provider.chat(
                    messages=context.messages,
                    tool_schemas=self._registry.tool_schemas(),
                    bus=self._bus,
                    run_id=context.run_id,
                    step=context.step,
                    system=context.system_prompt(
                        "you are a helpful AI assistant. "
                        "Use the available tools to complete the user's goal. "
                        "When the goal is fully achieved, respond with a final answer "
                        "and do not call any more tools."
                    ),
                )
            except asyncio.CancelledError:
                context.mark_failed("cancelled")
                raise
            except Exception:
                context.mark_failed("llm_error")
                break

            blocks: list[dict[str, object]] = []
            if response.text:
                blocks.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input})
            context.add_assistant_message(blocks)

            if response.stop_reason == "tool_use":
                for tc in response.tool_calls:
                    result = await invoke_tool(self._registry, tc, self._bus, context.run_id)
                    context.add_tool_result(tc.id, result.content, is_error=result.is_error)

            if response.stop_reason == "end_turn":
                context.result = response.text or ""
                context.mark_success()
            elif context.step >= context.max_steps:
                context.mark_failed("exceeded_max_steps")

            await self._bus.publish(StepFinishedEvent(run_id=context.run_id, step=context.step, ts=_now()))
