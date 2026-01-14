"""WebSocket endpoint for real-time updates."""

import asyncio
import logging
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()

# Active WebSocket connections
active_connections: Set[WebSocket] = set()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time deal updates."""
    await websocket.accept()
    active_connections.add(websocket)
    logger.info(f"WebSocket connected. Total connections: {len(active_connections)}")

    try:
        # Send initial ping
        await websocket.send_json({
            "type": "connected",
            "message": "🔥 ПОДКЛЮЧЕН К ТЕРМИНАЛУ!",
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for ping from client
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                # Respond to ping
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
            except asyncio.TimeoutError:
                # Send ping if no message received
                await websocket.send_json({
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat(),
                })

    except WebSocketDisconnect:
        active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(active_connections)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        active_connections.discard(websocket)


async def broadcast_new_deal(deal_data: dict):
    """Broadcast new deal to all connected clients."""
    if not active_connections:
        return

    message = {
        "type": "new_deal",
        "data": deal_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Send to all connections
    disconnected = set()
    for connection in active_connections:
        try:
            await connection.send_json(message)
        except Exception as e:
            logger.error(f"Error broadcasting to client: {e}")
            disconnected.add(connection)

    # Remove disconnected clients
    active_connections.difference_update(disconnected)


async def broadcast_market_update(overview_data: dict):
    """Broadcast market overview update."""
    if not active_connections:
        return

    message = {
        "type": "market_update",
        "data": overview_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    disconnected = set()
    for connection in active_connections:
        try:
            await connection.send_json(message)
        except Exception as e:
            logger.error(f"Error broadcasting to client: {e}")
            disconnected.add(connection)

    active_connections.difference_update(disconnected)
