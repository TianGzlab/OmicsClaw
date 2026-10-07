"""One deadline shared by connection, SDK retries and stream reads."""

import asyncio
import inspect
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from .base import ProviderDeadlineExceeded

T = TypeVar("T")


class RequestDeadline:
    def __init__(self, seconds: float, provider: str) -> None:
        self.seconds = seconds
        self.provider = provider
        self.at = asyncio.get_running_loop().time() + seconds

    @asynccontextmanager
    async def wait(self) -> AsyncIterator[None]:
        if asyncio.get_running_loop().time() >= self.at:
            raise ProviderDeadlineExceeded(
                f"request deadline exceeded ({self.seconds:g}s)", provider=self.provider,
            )
        timer = asyncio.timeout_at(self.at)
        try:
            async with timer:
                yield
        except TimeoutError as exc:
            if not timer.expired():
                raise
            raise ProviderDeadlineExceeded(
                f"request deadline exceeded ({self.seconds:g}s)", provider=self.provider,
            ) from exc

    async def iterate(self, stream: AsyncIterable[T]) -> AsyncIterator[T]:
        iterator = aiter(stream)
        while True:
            try:
                async with self.wait():
                    item = await anext(iterator)
            except StopAsyncIteration:
                return
            # Never leave a timer armed while control belongs to the consumer.
            yield item


async def close_stream(stream: Any, timeout: float = 1.0) -> None:
    """Allow bounded cleanup without masking the answer, failure or cancellation."""
    closer = getattr(stream, "close", None)
    if closer is None:
        return
    try:
        result = closer()
        if inspect.isawaitable(result):
            async with asyncio.timeout(min(timeout, 1.0)):
                await result
    except Exception:
        # Cancellation is a BaseException and must still reach the caller.
        pass
