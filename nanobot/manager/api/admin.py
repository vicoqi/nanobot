"""Admin dashboard API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from nanobot.manager.auth import create_admin_token, create_access_token, decode_access_token, get_current_admin
from nanobot.manager.database import Database
from nanobot.manager.models import AdminStatsResponse, AgentStatus
from nanobot.manager.app import get_config, get_db, get_process_manager
from nanobot.manager.services.agent_manager import AgentProcessManager

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/auth/login")
async def admin_login(body: dict):
    password = body.get("password", "")
    config = get_config()
    token = create_admin_token(password, config.manager.admin_password, config.manager.secret_key)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return {"token": token}


@router.get("/agents")
async def list_all_agents(
    _admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db),
):
    return await db.list_all_agents()


@router.get("/agents/{agent_id}")
async def get_agent_detail(
    agent_id: int,
    _admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db),
):
    agent = await db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("/agents/{agent_id}/start")
async def admin_start_agent(
    agent_id: int,
    _admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db),
    pm: AgentProcessManager = Depends(get_process_manager),
):
    agent = await db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status == AgentStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Agent already running")
    updated = await pm.start_agent(agent, db)
    return updated or await db.get_agent(agent_id)


@router.post("/agents/{agent_id}/stop")
async def admin_stop_agent(
    agent_id: int,
    _admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db),
    pm: AgentProcessManager = Depends(get_process_manager),
):
    agent = await db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status != AgentStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Agent not running")
    updated = await pm.stop_agent(agent, db)
    return updated or await db.get_agent(agent_id)


@router.get("/users")
async def list_users(
    _admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db),
):
    return await db.get_user_agent_counts()


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    _admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db),
):
    users = await db.list_users()
    agents = await db.list_all_agents()
    return AdminStatsResponse(
        total_users=len(users),
        total_agents=len(agents),
        running_agents=sum(1 for a in agents if a.status == AgentStatus.RUNNING),
        stopped_agents=sum(1 for a in agents if a.status == AgentStatus.STOPPED),
        error_agents=sum(1 for a in agents if a.status == AgentStatus.ERROR),
    )
