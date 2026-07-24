from __future__ import annotations

import asyncio
import datetime
import fnmatch
import json
import logging
import signal
import time
from typing import Any

import rmf_coder
from rmf_coder.core.bus.commands import (
    AgentRunCommand,
    AgentRunResult,
    EventSubscribeCommand,
    EventSubscribeResult,
    PongResult, )
from rmf_coder.core.bus.envelope import EventPushEnvelope
from rmf_coder.core.config import RMFConfig, get_config
from rmf_coder.core.events.bus import EventBus
from rmf_coder.core.logging_setup import setup_logging
from rmf_coder.core.runner import AgentRunner
from rmf_coder.core.runs import events_file, new_run_id
from rmf_coder.core.transport.ipc_broadcaster import IpcEventBroadcaster
from rmf_coder.core.transport.socket_server import SocketServer, get_connection_writer

logger = logging.getLogger(__name__)


class CoreApp:
    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._bus = EventBus()
        self._broadcaster = IpcEventBroadcaster()
        self._bus.subscribe(self._broadcaster.handle)
        self._current_run_task: asyncio.Task[None] | None = None
        self._config: RMFConfig | None = None

    async def _ping_handler(self, params: dict[str, Any]) -> PongResult:
        client = params.get("client", "unknown")
        logger.debug("ping from %s", client)
        return PongResult(
            server_version=rmf_coder.__version__,
            uptime_ms=int((time.monotonic() - self._start_time) * 1000),
            received_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    async def _agent_run_handler(self, params: dict[str, Any]) -> AgentRunResult:
        assert self._config is not None
        cmd = AgentRunCommand.model_validate(params)

        if self._current_run_task is not None and not self._current_run_task.done():
            raise RuntimeError("a run is already in progress")

        run_id = new_run_id()
        runner = AgentRunner(self._config, bus=self._bus)
        self._current_run_task = asyncio.create_task(
            runner.run(cmd.goal, run_id=run_id)
        )

        return AgentRunResult(run_id=run_id)

    async def _subscribe_handler(self, params: dict[str, Any]) -> EventSubscribeResult:
        cmd = EventSubscribeCommand.model_validate(params)
        writer = get_connection_writer()

        replayed_count = 0
        if cmd.replay_from_run is not None:
            replayed_count = await self._replay_events(
                cmd.replay_from_run, writer, cmd.topics
            )

        sub_id = self._broadcaster.subscribe(writer, cmd.topics, cmd.scope)
        return EventSubscribeResult(subscription_id=sub_id, replayed_count=replayed_count)

    async def _replay_events(
            self,
            run_id: str,
            writer: asyncio.StreamWriter,
            topics: list[str],
    ) -> int:
        path = events_file(run_id)
        if not path.exists():
            return 0

        count = 0
        for line in path.read_text().splitlines():
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type", "")
            if not any(fnmatch.fnmatch(event_type, p) for p in topics):
                continue
            envelope = EventPushEnvelope(event=event)
            writer.write(envelope.model_dump_json().encode() + b"\n")
            count += 1

        if count:
            await writer.drain()
        return count

    async def run(self) -> None:
        self._start_time = time.monotonic()
        self._config = get_config()
        setup_logging(self._config)

        server = SocketServer(self._config.host, self._config.port, self._broadcaster)
        server.register("core.ping", self._ping_handler)
        server.register("agent.run", self._agent_run_handler)
        server.register("event.subscribe", self._subscribe_handler)

        addr = await server.start()
        logger.info("rmf-core %s listening addr=%s", rmf_coder.__version__, addr)
        logger.info("config: %s", self._config)

        loop = asyncio.get_event_loop()
        shutdown = asyncio.Event()
        try:
            loop.add_signal_handler(signal.SIGINT, shutdown.set)
            loop.add_signal_handler(signal.SIGTERM, shutdown.set)
        except NotImplementedError:
            pass
        await shutdown.wait()
        logger.info("shutting down")
        await server.stop()


def run() -> None:
    asyncio.run(CoreApp().run())
