import asyncio

from fastapi import WebSocket


class WebSocketConnectionManager:
    def __init__(self) -> None:
        self._active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._active_connections.discard(websocket)

    async def broadcast_json(self, message: dict) -> None:
        async with self._lock:
            connections = list(self._active_connections)

        stale_connections: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                stale_connections.append(connection)

        if stale_connections:
            async with self._lock:
                for connection in stale_connections:
                    self._active_connections.discard(connection)

    async def active_count(self) -> int:
        async with self._lock:
            return len(self._active_connections)


ws_connection_manager = WebSocketConnectionManager()

