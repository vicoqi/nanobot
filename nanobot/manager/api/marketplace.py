"""Admin API endpoints for the agent skills marketplace.

Exposes search/trending/install/uninstall against the global manager-skills
repo via the service layer. All endpoints require an admin JWT via
``get_current_admin``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from nanobot.manager.app import get_config
from nanobot.manager.auth import get_current_admin
from nanobot.manager.services.skills import (
    global_skills_dir,
    scan_available_skills,
    uninstall_global_skill,
)
from nanobot.manager.services.skills_marketplace import (
    SkillsMarketplaceError,
    install_marketplace_skill,
    search_marketplace_skills,
    trending_marketplace_skills,
)

router = APIRouter(prefix="/api/admin/skills", tags=["admin-skills"])


class InstallRequest(BaseModel):
    # Accept ``skillId`` on the wire (camelCase alias) while keeping the
    # Python identifier snake_case — matches the convention in agents.py.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    skill_id: str
    source: str
    provider: str = "skills_sh"
    version: str = ""


@router.get("/marketplace/search")
async def search(
    q: str,
    source: str = "all",
    _admin: dict = Depends(get_current_admin),
):
    config = get_config()
    try:
        return await search_marketplace_skills(q, global_skills_dir(config), provider=source)
    except SkillsMarketplaceError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status", None) or 400,
            detail=str(exc),
        ) from exc


@router.get("/marketplace/trending")
async def trending(
    source: str = "all",
    _admin: dict = Depends(get_current_admin),
):
    config = get_config()
    try:
        return await trending_marketplace_skills(global_skills_dir(config), provider=source)
    except SkillsMarketplaceError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status", None) or 400,
            detail=str(exc),
        ) from exc


@router.post("/marketplace/install")
async def install(
    req: InstallRequest,
    _admin: dict = Depends(get_current_admin),
):
    config = get_config()
    try:
        return await install_marketplace_skill(
            req.source,
            req.skill_id,
            global_skills_dir(config),
            provider=req.provider,
            version=req.version,
        )
    except SkillsMarketplaceError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status", None) or 400,
            detail=str(exc),
        ) from exc


@router.get("")
async def installed(_admin: dict = Depends(get_current_admin)):
    config = get_config()
    return {"skills": scan_available_skills(global_skills_dir(config))}


@router.delete("/{skill_name}")
async def uninstall(skill_name: str, _admin: dict = Depends(get_current_admin)):
    """Remove a skill from the global repo and cascade-clean agent workspaces.

    Decision 5a: rather than leaving dangling symlinks across agent workspaces
    when a global skill is removed, we walk every workspace and unlink the
    matching symlink before deleting the global repo directory.
    """
    config = get_config()
    cleaned = uninstall_global_skill(
        skill_name, global_skills_dir(config), config.workspaces_dir
    )
    return {"success": True, "cleanedWorkspaces": cleaned}
