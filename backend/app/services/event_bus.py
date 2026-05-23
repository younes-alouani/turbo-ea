from __future__ import annotations

import asyncio
import json
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event

# Set by `OriginMiddleware` in `app.main` from the `X-Turbo-EA-Origin`
# request header. ``publish()`` reads this and stamps the event payload so
# admins can filter MCP-driven writes out of the audit log separately from
# web-UI actions. Unset (None) means a request without the header — typical
# web-UI or system-initiated event — and we omit the key entirely so the
# audit log stays clean for pre-existing rows.
request_origin: ContextVar[str | None] = ContextVar("request_origin", default=None)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    async def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        db: AsyncSession | None = None,
        card_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> None:
        origin = request_origin.get()
        if origin and "origin" not in data:
            # Stamp into the JSONB payload so downstream queries (the
            # /events endpoint, the per-card history timeline, the SSE
            # stream) all see the origin without a schema change.
            data = {**data, "origin": origin}
        if db:
            event = Event(
                card_id=card_id,
                user_id=user_id,
                event_type=event_type,
                data=data,
            )
            db.add(event)
            await db.flush()

        message = {
            "event": event_type,
            "data": data,
            "card_id": str(card_id) if card_id else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        dead: list[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        try:
            while True:
                msg = await q.get()
                yield f"data: {json.dumps(msg, default=str)}\n\n"
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)


event_bus = EventBus()
