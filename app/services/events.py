"""In-process fan-out for websockets and server-sent events."""

import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Any


class EventHub:
    def __init__(self, history: int = 40) -> None:
        self._sockets: set[Any] = set()
        self._queues: set[asyncio.Queue] = set()
        self.history: deque[dict[str, Any]] = deque(maxlen=history)

    def subscribe_socket(self, socket: Any) -> None:
        self._sockets.add(socket)

    def unsubscribe_socket(self, socket: Any) -> None:
        self._sockets.discard(socket)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "type": event_type,
            "at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        self.history.append(event)
        dead: list[Any] = []
        for socket in self._sockets:
            try:
                await socket.send_json(event)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self._sockets.discard(socket)
        for queue in list(self._queues):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)
        return event


hub = EventHub()
