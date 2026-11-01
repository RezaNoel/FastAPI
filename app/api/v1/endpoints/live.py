"""Websocket and server-sent activity."""

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Query, Security, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_principal
from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models import User
from app.schemas.common import PROBLEMS
from app.services.events import hub

router = APIRouter(responses=PROBLEMS)


@router.get("/recent", operation_id="recentActivity")
async def recent(
    _: Annotated[User, Security(get_principal, scopes=["reports:read"])],
) -> dict:
    return {"items": list(hub.history)}


@router.get("/events", operation_id="streamActivity")
async def stream_activity(
    _: Annotated[User, Security(get_principal, scopes=["reports:read"])],
) -> StreamingResponse:
    async def generate():
        queue = hub.subscribe()
        try:
            hello = {"type": "hello", "payload": {"message": "wire open"}}
            yield f"event: hello\ndata: {json.dumps(hello)}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/ws")
async def activity_socket(websocket: WebSocket, token: str = Query()) -> None:
    """Browsers cannot set an Authorization header on a websocket.

    The access token is sent once, on the connection URL.
    """
    await websocket.accept()
    try:
        payload = decode_token(token)
    except ValueError:
        await websocket.close(code=4401)
        return
    if payload.get("typ") != "access":
        await websocket.close(code=4401)
        return

    async with SessionLocal() as session:
        session: AsyncSession
        user = await session.get(User, payload.get("sub"))
        if user is None or not user.is_active:
            await websocket.close(code=4401)
            return

    hub.subscribe_socket(websocket)
    try:
        while True:
            incoming = await websocket.receive_text()
            if incoming == "ping":
                await websocket.send_json({"type": "pong", "payload": {}})
    except WebSocketDisconnect:
        return
    finally:
        hub.unsubscribe_socket(websocket)
