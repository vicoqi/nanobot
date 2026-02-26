"""Web channel implementation using FastAPI for HTTP API access."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger
from pydantic import BaseModel, Field
import threading

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import WebConfig


# ============================================================================
# Request/Response Models
# ============================================================================


class ChatRequest(BaseModel):
    """Request body for /chat endpoint."""

    message: str = Field(..., description="User message to send to the agent")
    chat_id: str = Field(default="default", description="Session/chat identifier")
    sender_id: str = Field(default="web_user", description="Sender identifier")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class ChatResponse(BaseModel):
    """Response from /chat endpoint."""

    response: str = Field(..., description="Agent's response")
    chat_id: str = Field(..., description="Session identifier")
    request_id: str = Field(..., description="Unique request identifier")
    timestamp: str = Field(..., description="Response timestamp")


class StatusResponse(BaseModel):
    """Health/status response."""

    status: str = "ok"
    channel: str = "web"


# ============================================================================
# Pending Response Tracker
# ============================================================================


class PendingResponse:
    """Tracks a pending response for an HTTP request."""

    def __init__(self, request_id: str, timeout: float = 120.0):
        self.request_id = request_id
        self.timeout = timeout
        self.event = asyncio.Event()
        self.response: OutboundMessage | None = None
        self.error: str | None = None
        self.created_at = datetime.now()

    def set_response(self, msg: OutboundMessage) -> None:
        """Set the response and signal completion."""
        self.response = msg
        self.event.set()

    def set_error(self, error: str) -> None:
        """Set an error and signal completion."""
        self.error = error
        self.event.set()

    async def wait(self) -> OutboundMessage | None:
        """Wait for the response with timeout."""
        try:
            await asyncio.wait_for(self.event.wait(), timeout=self.timeout)
            return self.response
        except asyncio.TimeoutError:
            self.error = "Request timeout"
            return None


# ============================================================================
# Web Channel
# ============================================================================


class WebChannel(BaseChannel):
    """
    Web channel using FastAPI for HTTP API access.

    Provides a RESTful API for chat interactions:
    - POST /chat - Send a message, receive AI response (synchronous)
    - GET /health - Health check endpoint
    - GET /status - Channel status

    Key design: Uses pending response tracking to bridge async message bus
    with synchronous HTTP request-response pattern.
    """

    name = "web"

    def __init__(self, config: WebConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: WebConfig = config
        self._app: FastAPI | None = None
        self._server: Any = None  # uvicorn.Server instance
        self._server_task: asyncio.Task | None = None
        self._pending_responses: dict[str, PendingResponse] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._lock = threading.Lock()  # Protect concurrent access to _pending_responses

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """FastAPI lifespan context manager."""
        logger.info("Web channel starting...")
        yield
        logger.info("Web channel shutting down...")
        # Cleanup pending responses
        with self._lock:
            for pending in list(self._pending_responses.values()):
                pending.set_error("Server shutting down")
            self._pending_responses.clear()

    def _create_app(self) -> FastAPI:
        """Create and configure the FastAPI application."""
        app = FastAPI(
            title="nanobot Web API",
            description="HTTP API for nanobot AI assistant",
            version="1.0.0",
            lifespan=self._lifespan,
        )

        # Add CORS middleware if configured
        if self.config.cors_origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self.config.cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # Register routes
        app.post("/chat")(self._handle_chat)
        app.get("/health")(self._handle_health)
        app.get("/status")(self._handle_status)
        app.get("/", response_class=HTMLResponse)(self._handle_ui)

        # Exception handler
        @app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            logger.error("Unhandled exception in web channel: {}", exc, exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"error": "Internal server error", "detail": str(exc)},
            )

        return app

    async def start(self) -> None:
        """Start the FastAPI server."""
        if not self.config.enabled:
            logger.info("Web channel is disabled")
            return

        self._running = True
        self._app = self._create_app()

        # Start cleanup task for stale pending responses
        self._cleanup_task = asyncio.create_task(self._cleanup_stale_responses())

        # Start uvicorn server
        import uvicorn

        config = uvicorn.Config(
            app=self._app,
            host=self.config.host,
            port=self.config.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        logger.info("Starting web channel on {}:{}", self.config.host, self.config.port)

        try:
            await self._server.serve()
        except asyncio.CancelledError:
            logger.info("Web channel server cancelled")
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the web channel gracefully."""
        self._running = False

        # Stop cleanup task first
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        # Signal all pending responses
        with self._lock:
            for pending in list(self._pending_responses.values()):
                pending.set_error("Channel stopped")
            self._pending_responses.clear()

        # Gracefully shutdown uvicorn server
        if self._server:
            self._server.should_exit = True
            # Give server time to shutdown gracefully
            await asyncio.sleep(0.5)

        logger.info("Web channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """
        Handle outgoing message from the agent.

        This is called by ChannelManager when a response is available.
        Matches the response to a pending HTTP request via metadata.request_id.

        Note: Progress messages (metadata._progress=True) are ignored since
        we only want to return the final complete response to the HTTP client.
        """
        # Ignore progress messages - we only want the final response
        if msg.metadata.get("_progress"):
            logger.debug("Web channel ignoring progress message")
            return

        request_id = msg.metadata.get("request_id")

        if not request_id:
            logger.warning(
                "Web channel received message without request_id: {}", msg.content[:50]
            )
            return

        with self._lock:
            pending = self._pending_responses.get(request_id)

        if pending:
            pending.set_response(msg)
            logger.debug("Web channel matched response to request: {}", request_id)
        else:
            logger.warning(
                "Web channel received response for unknown request: {}", request_id
            )

    # ========================================================================
    # API Handlers
    # ========================================================================

    async def _handle_chat(
        self,
        request: ChatRequest,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> ChatResponse:
        """
        Handle POST /chat requests.

        Sends message to agent and waits for response.
        """
        # Authenticate if API key is configured
        if self.config.api_key:
            if not x_api_key or x_api_key != self.config.api_key:
                raise HTTPException(status_code=401, detail="Invalid API key")

        # Check sender permission
        sender_id = request.sender_id or "web_user"
        if not self.is_allowed(sender_id):
            raise HTTPException(status_code=403, detail="Sender not allowed")

        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Create pending response tracker
        pending = PendingResponse(
            request_id=request_id, timeout=float(self.config.request_timeout)
        )
        with self._lock:
            self._pending_responses[request_id] = pending

        try:
            # Build metadata with request_id for response matching
            metadata = {
                **request.metadata,
                "request_id": request_id,
                "timestamp": datetime.now().isoformat(),
            }

            # Send message to agent via bus
            await self._handle_message(
                sender_id=sender_id,
                chat_id=request.chat_id,
                content=request.message,
                metadata=metadata,
            )

            # Wait for response
            response_msg = await pending.wait()

            if pending.error:
                if pending.error == "Request timeout":
                    raise HTTPException(status_code=504, detail="Agent response timeout")
                raise HTTPException(status_code=500, detail=pending.error)

            if response_msg is None:
                raise HTTPException(status_code=500, detail="No response from agent")

            return ChatResponse(
                response=response_msg.content,
                chat_id=request.chat_id,
                request_id=request_id,
                timestamp=datetime.now().isoformat(),
            )

        finally:
            # Cleanup pending response
            with self._lock:
                self._pending_responses.pop(request_id, None)

    async def _handle_health(self) -> StatusResponse:
        """Health check endpoint."""
        return StatusResponse(status="ok", channel="web")

    async def _handle_status(self) -> dict[str, Any]:
        """Detailed status endpoint."""
        return {
            "status": "ok" if self._running else "stopped",
            "channel": self.name,
            "pending_requests": len(self._pending_responses),
            "config": {
                "host": self.config.host,
                "port": self.config.port,
                "cors_enabled": bool(self.config.cors_origins),
            },
        }

    async def _handle_ui(self) -> HTMLResponse:
        """Serve the web chat UI."""
        static_dir = Path(__file__).parent.parent / "static"
        index_path = static_dir / "index.html"

        if not index_path.exists():
            return HTMLResponse(
                content="<html><body><h1>Web UI not found</h1></body></html>",
                status_code=404
            )

        return HTMLResponse(content=index_path.read_text())

    # ========================================================================
    # Background Tasks
    # ========================================================================

    async def _cleanup_stale_responses(self) -> None:
        """Periodically cleanup stale pending responses."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Check every minute

                now = datetime.now()
                stale_ids = []

                with self._lock:
                    for request_id, pending in self._pending_responses.items():
                        age = (now - pending.created_at).total_seconds()
                        if age > pending.timeout + 30:  # Grace period
                            stale_ids.append(request_id)

                    for request_id in stale_ids:
                        pending = self._pending_responses.pop(request_id, None)
                        if pending:
                            pending.set_error("Request expired")
                            logger.warning("Cleaned up stale request: {}", request_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in cleanup task: {}", e, exc_info=True)
