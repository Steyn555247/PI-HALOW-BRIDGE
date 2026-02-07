"""
Telemetry WebSocket Server Module

Real-time telemetry streaming to web clients via WebSocket.
"""

import asyncio
import json
import logging
import threading
from typing import Set, Optional
import websockets
from websockets.server import WebSocketServerProtocol

from telemetry_buffer import TelemetryBuffer
from telemetry_metrics import add_derived_metrics


logger = logging.getLogger(__name__)


class TelemetryWebSocketServer:
    """
    WebSocket server for real-time telemetry streaming.

    Broadcasts telemetry updates to all connected clients.
    """

    def __init__(self, port: int = 5005, buffer: Optional[TelemetryBuffer] = None):
        """
        Initialize WebSocket server.

        Args:
            port: WebSocket server port
            buffer: TelemetryBuffer instance for historical data
        """
        self.port = port
        self.buffer = buffer
        self.clients: Set[WebSocketServerProtocol] = set()
        self.running = False
        self.server = None
        self.loop = None

    async def start(self):
        """Start the WebSocket server."""
        self.running = True
        self.loop = asyncio.get_event_loop()

        try:
            self.server = await websockets.serve(
                self.handle_client,
                "0.0.0.0",
                self.port
            )
            logger.info(f"Telemetry WebSocket server started on port {self.port}")

            # Keep server running
            await asyncio.Future()  # Run forever

        except Exception as e:
            logger.error(f"WebSocket server error: {e}")
        finally:
            self.running = False

    async def handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """
        Handle a new WebSocket client connection.

        Args:
            websocket: WebSocket connection
            path: Request path
        """
        client_addr = websocket.remote_address
        logger.info(f"WebSocket client connected: {client_addr}")

        # Register client
        self.clients.add(websocket)

        try:
            # Send latest telemetry immediately on connect
            if self.buffer:
                latest = self.buffer.get_latest()
                if latest:
                    enhanced = add_derived_metrics(latest)
                    await websocket.send(json.dumps(enhanced))

            # Wait for messages (mainly to detect disconnection)
            async for message in websocket:
                # Handle client messages if needed (e.g., subscription preferences)
                pass

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket client disconnected: {client_addr}")
        except Exception as e:
            logger.error(f"Error handling WebSocket client {client_addr}: {e}")
        finally:
            # Unregister client
            self.clients.discard(websocket)

    async def broadcast_telemetry(self, telemetry: dict):
        """
        Broadcast telemetry to all connected clients.

        Args:
            telemetry: Telemetry dictionary to broadcast
        """
        if not self.clients:
            return

        # Add derived metrics
        enhanced = add_derived_metrics(telemetry)
        message = json.dumps(enhanced)

        # Broadcast to all clients
        disconnected_clients = set()
        for client in self.clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected_clients.add(client)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected_clients.add(client)

        # Remove disconnected clients
        self.clients -= disconnected_clients

    def broadcast_telemetry_sync(self, telemetry: dict):
        """
        Synchronous wrapper for broadcast_telemetry.

        Schedules the broadcast on the event loop.

        Args:
            telemetry: Telemetry dictionary to broadcast
        """
        if self.loop and self.running:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_telemetry(telemetry),
                self.loop
            )

    async def stop(self):
        """Stop the WebSocket server."""
        self.running = False

        # Close all client connections
        if self.clients:
            await asyncio.gather(
                *[client.close() for client in self.clients],
                return_exceptions=True
            )

        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        logger.info("Telemetry WebSocket server stopped")


def run_websocket_server(server: TelemetryWebSocketServer):
    """
    Run WebSocket server in a thread.

    Args:
        server: TelemetryWebSocketServer instance
    """
    asyncio.run(server.start())
