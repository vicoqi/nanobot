"""Agent CRUD and lifecycle API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from nanobot.manager.app import (
    get_config,
    get_db,
    get_process_manager,
    get_qr_service,
)
from nanobot.manager.auth import get_current_user
from nanobot.manager.database import Database
from nanobot.manager.models import (
    Agent,
    AgentStatus,
    AgentStatusResponse,
    CreateAgentRequest,
    QRCodeStatus,
    UpdateAgentRequest,
)
from nanobot.manager.services.agent_manager import AgentProcessManager
from nanobot.manager.services.config_builder import (
    build_agent_config,
    cleanup_agent_files,
    update_agent_daily_delivery_config,
    write_agent_files,
)
from nanobot.manager.services.skills import (
    get_installed_skill_names,
    install_skill,
    scan_available_skills,
    uninstall_skill,
)
from nanobot.manager.services.wechat_qr import WechatQRService

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _get_user_id(payload: dict) -> int:
    return int(payload["sub"])


def _check_owner(agent: Agent | None, user_id: int) -> Agent:
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your agent")
    return agent


class SkillActionRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    skill_name: str


@router.get("")
async def list_agents(payload: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    return await db.get_agents_by_user(_get_user_id(payload))


@router.post("")
async def create_agent(
    req: CreateAgentRequest,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    user_id = _get_user_id(payload)
    config = get_config()

    port = await db.allocate_port(config.port_range)
    agent_id_val = 0  # placeholder, will be set by DB

    agent_dir = str(config.configs_dir / f"agent-{port}")
    workspace_dir = str(config.workspaces_dir / f"agent-{port}")

    agent = await db.create_agent(
        user_id=user_id,
        name=req.name,
        soul=req.soul,
        language=req.language,
        city=req.city,
        gender=req.gender,
        config_path=f"{agent_dir}/config.json",
        workspace_path=workspace_dir,
        gateway_port=port,
    )

    agent_dict = build_agent_config(config, agent)
    write_agent_files(agent, agent_dict)

    await db.update_agent(agent.id, status=AgentStatus.STOPPED)
    agent = await db.get_agent(agent.id)
    return agent


@router.get("/{agent_id}")
async def get_agent(
    agent_id: int,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    agent = await db.get_agent(agent_id)
    return _check_owner(agent, _get_user_id(payload))


@router.put("/{agent_id}")
async def update_agent(
    agent_id: int,
    req: UpdateAgentRequest,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    pm: AgentProcessManager = Depends(get_process_manager),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))

    updates = {}
    daily_delivery_changed = (
        req.daily_delivery_enabled is not None
        and req.daily_delivery_enabled != agent.daily_delivery_enabled
    )
    if req.name is not None:
        updates["name"] = req.name
    if req.soul is not None:
        updates["soul"] = req.soul
    if req.language is not None:
        updates["language"] = req.language
    if req.city is not None:
        updates["city"] = req.city
    if req.gender is not None:
        updates["gender"] = req.gender
    if req.daily_delivery_enabled is not None:
        updates["daily_delivery_enabled"] = req.daily_delivery_enabled

    if updates:
        await db.update_agent(agent_id, **updates)
        updated = await db.get_agent(agent_id)
        # Regenerate SOUL.md with updated profile
        from nanobot.manager.services.config_builder import build_soul_md
        soul_path = Path(updated.workspace_path) / "SOUL.md"
        soul_path.write_text(build_soul_md(updated), encoding="utf-8")
        if req.daily_delivery_enabled is not None:
            update_agent_daily_delivery_config(updated)
        if daily_delivery_changed and updated.status == AgentStatus.RUNNING:
            restarted = await pm.restart_agent(updated, db)
            if restarted is not None:
                updated = restarted
        return updated
    return await db.get_agent(agent_id)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: int,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    pm: AgentProcessManager = Depends(get_process_manager),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))

    if agent.status == "running" and agent.pid:
        await pm.stop_agent(agent, db)

    cleanup_agent_files(agent)
    await db.delete_agent(agent_id)
    return {"detail": "deleted"}


@router.post("/{agent_id}/start")
async def start_agent(
    agent_id: int,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    pm: AgentProcessManager = Depends(get_process_manager),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    if agent.status == AgentStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Agent already running")
    updated = await pm.start_agent(agent, db)
    return updated or await db.get_agent(agent_id)


@router.post("/{agent_id}/stop")
async def stop_agent(
    agent_id: int,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    pm: AgentProcessManager = Depends(get_process_manager),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    if agent.status != AgentStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Agent not running")
    updated = await pm.stop_agent(agent, db)
    return updated or await db.get_agent(agent_id)


@router.get("/{agent_id}/status", response_model=AgentStatusResponse)
async def get_status(
    agent_id: int,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    pm: AgentProcessManager = Depends(get_process_manager),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    health = pm.check_health(agent)
    return AgentStatusResponse(
        status=agent.status,
        pid=agent.pid,
        alive=health,
        gateway_port=agent.gateway_port,
        wechat_bound=agent.wechat_bound,
        qr_code_status=agent.qr_code_status,
    )


@router.post("/{agent_id}/qrcode")
async def generate_qrcode(
    agent_id: int,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    qr: WechatQRService = Depends(get_qr_service),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    if agent.wechat_bound:
        raise HTTPException(status_code=400, detail="WeChat already bound")

    try:
        qr_code_id, qr_code_url = await qr.fetch_qr_code()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QR code generation failed: {e}")

    await db.update_agent(
        agent_id,
        qr_code_id=qr_code_id,
        qr_code_url=qr_code_url,
        qr_code_status=QRCodeStatus.PENDING,
    )
    qr.spawn_poll_task(agent_id, db)
    return {"qrCodeUrl": qr_code_url, "qrCodeId": qr_code_id}


@router.get("/{agent_id}/qrcode/status")
async def get_qrcode_status(
    agent_id: int,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    return {
        "qrCodeStatus": agent.qr_code_status,
        "wechatBound": agent.wechat_bound,
    }


@router.get("/{agent_id}/skills/available")
async def list_available_skills(
    agent_id: int,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    available = scan_available_skills()
    installed = get_installed_skill_names(agent.workspace_path)
    return {
        "skills": [
            {**s, "installed": s["name"] in installed}
            for s in available
        ],
    }


@router.post("/{agent_id}/skills/install")
async def install_skill_endpoint(
    agent_id: int,
    req: SkillActionRequest,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    pm: AgentProcessManager = Depends(get_process_manager),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    try:
        install_skill(req.skill_name, agent.workspace_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))

    was_running = agent.status == AgentStatus.RUNNING
    if was_running:
        await pm.restart_agent(agent, db)

    return {
        "success": True,
        "message": "Skill installed" + (" and agent restarted" if was_running else ""),
    }


@router.post("/{agent_id}/skills/uninstall")
async def uninstall_skill_endpoint(
    agent_id: int,
    req: SkillActionRequest,
    payload: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    agent = _check_owner(await db.get_agent(agent_id), _get_user_id(payload))
    try:
        uninstall_skill(req.skill_name, agent.workspace_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"success": True, "message": "Skill uninstalled"}
