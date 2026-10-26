"""Opt-in ASGI request deadline for the frontend's 120-second external rewrite."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar

_deadline: ContextVar[float | None] = ContextVar("intermind_request_deadline", default=None)


def seconds_remaining() -> float | None:
    deadline = _deadline.get()
    return None if deadline is None else deadline - asyncio.get_running_loop().time()


class RequestDeadlineMiddleware:
    def __init__(self, app, *, seconds: float) -> None:
        if not 0 < seconds < 120:
            raise ValueError("request deadline must be between 0 and 120 seconds")
        self.app = app
        self.seconds = seconds

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        loop = asyncio.get_running_loop()
        token = _deadline.set(loop.time() + self.seconds)
        started = False

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            async with asyncio.timeout(self.seconds):
                await self.app(scope, receive, tracked_send)
        except TimeoutError:
            if started:
                raise
            body = b'{"detail":"Request timed out. Please try again."}'
            await send({"type": "http.response.start", "status": 504, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())
            ]})
            await send({"type": "http.response.body", "body": body})
        finally:
            _deadline.reset(token)
