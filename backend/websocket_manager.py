"""
websocket_manager.py — SkyGuard AI
------------------------------------
Push live station updates to connected dashboards instead of making
them poll GET /stations/{id}/status on a timer.

Import this into main.py and:
  1. create one shared `manager = ConnectionManager()`
  2. add the /ws endpoint below
  3. call `await manager.broadcast(status_response)` right after you
     compute the anomaly result inside your /ingest handler — use the
     exact same dict shape you already return from GET /status.
"""

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict) -> None:
        """Sends to everyone connected. Drops any socket that fails
        (closed tab, dead connection) instead of crashing the loop for
        everyone else."""
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()