"""Tiny async TTL cache used by metadata-heavy APIs."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


class AsyncTTLCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    def _now(self) -> float:
        return time.monotonic()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at <= self._now():
                self._data.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int) -> Any:
        async with self._lock:
            self._data[key] = (self._now() + ttl, value)
        return value

    async def invalidate(self, prefix: str | None = None) -> None:
        async with self._lock:
            if prefix is None:
                self._data.clear()
                return
            for key in list(self._data.keys()):
                if key.startswith(prefix):
                    self._data.pop(key, None)

    async def get_or_set(
        self,
        key: str,
        ttl: int,
        builder: Callable[[], Awaitable[Any]],
    ) -> tuple[Any, bool]:
        cached = await self.get(key)
        if cached is not None:
            return cached, True

        async with self._lock:
            entry = self._data.get(key)
            if entry and entry[0] > self._now():
                return entry[1], True
            future = self._inflight.get(key)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future
                owner = True
            else:
                owner = False

        if owner:
            try:
                value = await builder()
                await self.set(key, value, ttl)
                future.set_result(value)
            except Exception as exc:
                future.set_exception(exc)
                raise
            finally:
                async with self._lock:
                    self._inflight.pop(key, None)
            return value, False

        value = await future
        return value, True


APP_CACHE = AsyncTTLCache()
