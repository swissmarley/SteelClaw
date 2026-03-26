"""Connector registry — lazy-loads and manages the lifecycle of platform connectors."""

from __future__ import annotations

import importlib
import logging

from steelclaw.gateway.base import BaseConnector, MessageHandler
from steelclaw.settings import GatewaySettings

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

    def get(self, platform: str) -> BaseConnector | None:
        return self._connectors.get(platform)

    @property
    def active_connectors(self) -> dict[str, BaseConnector]:
        return dict(self._connectors)

    @staticmethod
    async def _noop_handler(msg: object) -> None:
        pass
