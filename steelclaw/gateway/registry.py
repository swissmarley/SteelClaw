"""Connector registry — lazy-loads and manages the lifecycle of platform connectors."""

from __future__ import annotations

import importlib
import logging

from steelclaw.gateway.base import BaseConnector, MessageHandler
from steelclaw.settings import ConnectorConfig, GatewaySettings

logger = logging.getLogger("steelclaw.gateway")

_CONNECTOR_CLASSES: dict[str, str] = {
    "telegram": "steelclaw.gateway.connectors.telegram.TelegramConnector",
    "discord": "steelclaw.gateway.connectors.discord.DiscordConnector",
    "whatsapp": "steelclaw.gateway.connectors.whatsapp.WhatsAppConnector",
    "slack": "steelclaw.gateway.connectors.slack.SlackConnector",
    "signal": "steelclaw.gateway.connectors.signal.SignalConnector",
    "imessage": "steelclaw.gateway.connectors.imessage.IMessageConnector",
    "mattermost": "steelclaw.gateway.connectors.mattermost.MattermostConnector",
    "matrix": "steelclaw.gateway.connectors.matrix.MatrixConnector",
    "teams": "steelclaw.gateway.connectors.teams.TeamsConnector",
}


class ConnectorRegistry:
    def __init__(self, gateway_settings: GatewaySettings) -> None:
        self._settings = gateway_settings
        self._connectors: dict[str, BaseConnector] = {}
        self._handler: MessageHandler | None = None

    def set_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    @staticmethod
    def _import_connector(dotted_path: str) -> type[BaseConnector]:
        module_path, class_name = dotted_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    async def start_all(self) -> None:
        for name, conf in self._settings.connectors.items():
            if not conf.enabled:
                continue
            if name not in _CONNECTOR_CLASSES:
                logger.warning("Unknown connector: %s — skipping", name)
                continue
            try:
                cls = self._import_connector(_CONNECTOR_CLASSES[name])
            except (ImportError, AttributeError):
                logger.error("Failed to import connector %s — is the dependency installed?", name)
                continue
            connector = cls(config=conf, handler=self._handler or self._noop_handler)
            await connector.start()
            self._connectors[name] = connector

    async def stop_all(self) -> None:
        for connector in self._connectors.values():
            await connector.stop()
        self._connectors.clear()

    async def start_connector(
        self, name: str, conf: ConnectorConfig
    ) -> tuple[BaseConnector | None, str | None]:
        """Import, verify, and start a single connector.

        Returns (connector, None) on success, (connector, error_string) if verify fails.
        If the connector name is unknown or import fails, returns (None, error_string).
        """
        if name not in _CONNECTOR_CLASSES:
            return None, f"Unknown connector: {name}"

        # Stop existing instance if running
        if name in self._connectors:
            await self._connectors[name].stop()
            del self._connectors[name]

        try:
            cls = self._import_connector(_CONNECTOR_CLASSES[name])
        except (ImportError, AttributeError) as exc:
            return None, f"Failed to import connector {name}: {exc}"

        connector = cls(config=conf, handler=self._handler or self._noop_handler)

        # Pre-flight check before creating asyncio task
        error = await connector.verify()
        if error:
            connector.last_error = error
            logger.error("Connector %s verify failed: %s", name, error)
            return connector, error

        await connector.start()
        self._connectors[name] = connector
        logger.info("Connector %s live-started", name)
        return connector, None

    async def stop_connector(self, name: str) -> None:
        """Stop and remove a single connector."""
        connector = self._connectors.pop(name, None)
        if connector:
            await connector.stop()
            logger.info("Connector %s stopped", name)

    def get(self, platform: str) -> BaseConnector | None:
        return self._connectors.get(platform)

    @property
    def active_connectors(self) -> dict[str, BaseConnector]:
        return dict(self._connectors)

    @staticmethod
    async def _noop_handler(msg: object) -> None:
        pass
