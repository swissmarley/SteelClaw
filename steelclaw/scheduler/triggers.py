"""Extended trigger types — file watcher, RSS polling, API polling."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger("steelclaw.scheduler.triggers")

TriggerCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class FileWatcherTrigger:
    """Watch a directory for new or modified files."""

    def __init__(
        self,
        watch_path: str,
        callback: TriggerCallback,
        poll_seconds: int = 10,
    ) -> None:
        self._path = Path(watch_path)
        self._callback = callback
        self._poll_seconds = poll_seconds
        self._known: dict[str, float] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        # Snapshot existing files on first run
        if self._path.exists():
            for f in self._path.iterdir():
                if f.is_file():
                    self._known[str(f)] = f.stat().st_mtime

        while True:
            await asyncio.sleep(self._poll_seconds)
            if not self._path.exists():
                continue
            for f in self._path.iterdir():
                if not f.is_file():
                    continue
                mtime = f.stat().st_mtime
                prev = self._known.get(str(f))
                if prev is None or mtime > prev:
                    self._known[str(f)] = mtime
                    await self._callback({
                        "event": "file_changed",
                        "path": str(f),
                        "name": f.name,
                        "is_new": prev is None,
                    })


class RSSPollingTrigger:
    """Poll an RSS/Atom feed for new items."""

    def __init__(
        self,
        feed_url: str,
        callback: TriggerCallback,
        poll_seconds: int = 300,
    ) -> None:
        self._url = feed_url
        self._callback = callback
        self._poll_seconds = poll_seconds
        self._seen_ids: set[str] = set()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        # Initial fetch seeds the known IDs without firing callbacks
        await self._check_feed(seed=True)
        while True:
            await asyncio.sleep(self._poll_seconds)
            await self._check_feed()

    async def _check_feed(self, seed: bool = False) -> None:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self._url)
                resp.raise_for_status()

                # Simple XML parsing for <item> or <entry> elements
                items = re.findall(
                    r"<(?:item|entry)>(.*?)</(?:item|entry)>",
                    resp.text,
                    re.DOTALL,
                )
                for item_xml in items:
                    id_match = re.search(r"<(?:guid|id)>(.*?)</(?:guid|id)>", item_xml)
                    link_match = re.search(r"<link[^>]*href=[\"']([^\"']+)", item_xml)
                    if not link_match:
                        link_match = re.search(r"<link>(.*?)</link>", item_xml)

                    item_id = (
                        id_match.group(1) if id_match
                        else link_match.group(1) if link_match
                        else hashlib.md5(item_xml.encode()).hexdigest()
                    )

                    if item_id in self._seen_ids:
                        continue
                    self._seen_ids.add(item_id)

                    if not seed:
                        title_match = re.search(r"<title>(.*?)</title>", item_xml)
                        title = title_match.group(1) if title_match else "Untitled"
                        link = link_match.group(1) if link_match else ""
                        await self._callback({
                            "event": "rss_new_item",
                            "title": title,
                            "link": link,
                            "id": item_id,
                        })
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("RSS poll failed for %s", self._url)


class APIPollingTrigger:
    """Poll an API URL and trigger when response changes or matches a pattern."""

    def __init__(
        self,
        url: str,
        callback: TriggerCallback,
        poll_seconds: int = 60,
        match_pattern: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._url = url
        self._callback = callback
        self._poll_seconds = poll_seconds
        self._match_pattern = match_pattern
        self._headers = headers or {}
        self._last_hash: str = ""
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        while True:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(self._url, headers=self._headers)
                    content_hash = hashlib.md5(resp.content).hexdigest()

                    triggered = False
                    if self._last_hash and content_hash != self._last_hash:
                        await self._callback({
                            "event": "api_changed",
                            "url": self._url,
                            "status": resp.status_code,
                        })
                        triggered = True

                    if self._match_pattern and not triggered:
                        if re.search(self._match_pattern, resp.text):
                            await self._callback({
                                "event": "api_match",
                                "url": self._url,
                                "pattern": self._match_pattern,
                            })

                    self._last_hash = content_hash
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("API poll failed for %s", self._url)

            await asyncio.sleep(self._poll_seconds)
