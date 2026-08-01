"""FastAPI application factory for the agent manager."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from loguru import logger

from nanobot.manager.config import ManagerConfig, load_manager_config
from nanobot.manager.database import Database
from nanobot.manager.services.agent_manager import AgentProcessManager
from nanobot.manager.services.wechat_qr import WechatQRService

# Module-level singletons set during create_app()
_app_state: _AppState | None = None


class _AppState:
    config: ManagerConfig
    db: Database
    process_manager: AgentProcessManager
    qr_service: WechatQRService
    monitor_task: asyncio.Task | None = None


def get_config() -> ManagerConfig:
    assert _app_state is not None, "App not initialized"
    return _app_state.config


def get_db() -> Database:
    assert _app_state is not None, "App not initialized"
    return _app_state.db


def get_process_manager() -> AgentProcessManager:
    assert _app_state is not None, "App not initialized"
    return _app_state.process_manager


def get_qr_service() -> WechatQRService:
    assert _app_state is not None, "App not initialized"
    return _app_state.qr_service


def create_app(config_path: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    global _app_state

    config = load_manager_config(config_path)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.configs_dir.mkdir(parents=True, exist_ok=True)
    config.workspaces_dir.mkdir(parents=True, exist_ok=True)

    state = _AppState()
    state.config = config
    state.db = Database(config.db_path)
    state.process_manager = AgentProcessManager()
    state.qr_service = WechatQRService()
    _app_state = state

    app = FastAPI(title="nanobot Manager", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from nanobot.manager.api.admin import router as admin_router
    from nanobot.manager.api.agents import router as agents_router
    from nanobot.manager.api.auth import router as auth_router
    from nanobot.manager.api.marketplace import router as marketplace_router

    app.include_router(auth_router)
    app.include_router(agents_router)
    app.include_router(admin_router)
    app.include_router(marketplace_router)

    # Serve frontend static files in production
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir() and (static_dir / "index.html").exists():
        index_html = static_dir / "index.html"

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            file = static_dir / path
            if path and file.is_file():
                return FileResponse(file)
            return FileResponse(index_html)

    @app.on_event("startup")
    async def startup():
        await state.db.init()

        # Resume agents that were RUNNING before restart/crash
        from nanobot.manager.models import AgentStatus

        previously_running = await state.db.get_agents_by_status(AgentStatus.RUNNING)
        if previously_running:
            logger.info("Resuming {} previously running agent(s)...", len(previously_running))
            for agent in previously_running:
                logger.info("Restarting agent '{}' (was pid={})", agent.name, agent.pid)
                await state.process_manager.start_agent(agent, state.db)

        state.monitor_task = asyncio.create_task(
            state.process_manager.monitor_loop(state.db)
        )
        logger.info("Manager started on {}:{}", config.manager.host, config.manager.port)

    @app.on_event("shutdown")
    async def shutdown():
        if state.monitor_task:
            state.monitor_task.cancel()
        await state.qr_service.close()
        await state.db.close()
        logger.info("Manager shut down")

    return app
