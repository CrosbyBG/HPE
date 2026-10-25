from typing import List
from fastapi import WebSocket

ONLINE_USERS = set()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections = {}

    async def connect(self, websocket: WebSocket, login: str):
        await websocket.accept()
        self.active_connections.append(websocket)
        if login not in self.user_connections:
            self.user_connections[login] = []
        self.user_connections[login].append(websocket)
        ONLINE_USERS.add(login)

    def disconnect(self, websocket: WebSocket, login: str):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if login in self.user_connections and websocket in self.user_connections[login]:
            self.user_connections[login].remove(websocket)
            if not self.user_connections[login]: 
                del self.user_connections[login]
                if login in ONLINE_USERS:
                    ONLINE_USERS.remove(login)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()