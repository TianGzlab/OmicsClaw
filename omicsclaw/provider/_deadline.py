"""One deadline shared by connection, SDK retries and stream reads."""

import asyncio
from contextlib import asynccontextmanager

from .base import ProviderDeadlineExceeded


class RequestDeadline:
    def __init__(self, seconds: float, provider: str):
        self.seconds = seconds
        self.provider = provider
        self.at = asyncio.get_running_loop().time() + seconds

    @asynccontextmanager
    async def wait(self):
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

    async def iterate(self, stream):
        iterator = aiter(stream)
        while True:
            try:
                async with self.wait():
                    item = await anext(iterator)
            except StopAsyncIteration:
                return
            # Never leave a timer armed while control belongs to the consumer.
            yield item
