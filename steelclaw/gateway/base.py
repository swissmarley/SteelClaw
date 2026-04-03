"""Abstract base class for all messaging-platform connectors."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from steelclaw.schemas.messages import InboundMessage, OutboundMessage
from steelclaw.settings import ConnectorConfig

MessageHandler = Callable[[InboundMessage], Awaitable[None]]

logger = logging.getLogger("steelclaw.gateway")


class BaseConnector(ABC):
    """Every platform connector must subclass this and implement ``_run`` and ``send``."""

    platform_name: str  # set as a class variable on each subclass

    def __init__(self, config: ConnectorConfig, handler: MessageHandler) -> None:
        self.config = config
        self._handler = handler
        self._task: asyncio.Task | None = None
        self._typing_tasks: dict[str, asyncio.Task] = {}  # chat_id → typing loop task

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"connector-{self.platform_name}")
        logger.info("Connector %s started", self.platform_name)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Cancel any active typing indicators
        for task in self._typing_tasks.values():
            task.cancel()
        self._typing_tasks.clear()
        logger.info("Connector %s stopped", self.platform_name)

    @abstractmethod
    async def _run(self) -> None:
        """Main loop — poll or listen for messages, call ``self.dispatch()`` for each."""
        ...

    @abstractmethod
    async def send(self, message: OutboundMessage) -> None:
        """Translate an ``OutboundMessage`` into the platform's native API call."""
        ...

    async def send_typing(self, chat_id: str) -> None:
        """Send a one-shot typing indicator. Override in subclasses that support it."""
        pass

    async def start_typing(self, chat_id: str) -> None:
        """Start a persistent typing indicator that auto-refreshes.

        Platforms like Telegram expire typing after ~5s so we loop.
        """
        self.stop_typing(chat_id)

        async def _typing_loop():
            try:
                while True:
                    await self.send_typing(chat_id)
                    await asyncio.sleep(4)  # Refresh before 5s expiry
            except asyncio.CancelledError:
                pass

        self._typing_tasks[chat_id] = asyncio.create_task(_typing_loop())

    def stop_typing(self, chat_id: str) -> None:
        """Cancel the persistent typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def dispatch(self, message: InboundMessage) -> None:
        """Forward a normalised inbound message to the central handler."""
        await self._handler(message)
