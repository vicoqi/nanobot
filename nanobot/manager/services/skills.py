"""Skills filesystem operations for the agent manager."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from loguru import logger
import yaml

_STRIP_FRONTMATTER = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?",
    re.DOTALL,
)

MANAGER_SKILLS_DIR = Path.home() / ".nanobot" / "manager" / "skills"


def _parse_frontmatter(content: str) -> dict | None:
    if not content.startswith("---"):
        return None
    match = _STRIP_FRONTMATTER.match(content)
    if not match:
        return None
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    return parsed if isinstance(parsed, dict) else None


def scan_available_skills() -> list[dict]:
    skills: list[dict] = []
    if not MANAGER_SKILLS_DIR.is_dir():
        return skills

    for skill_dir in sorted(MANAGER_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        content = skill_file.read_text(encoding="utf-8")
        frontmatter = _parse_frontmatter(content) or {}
        skills.append({
            "name": skill_dir.name,
            "description": frontmatter.get("description", skill_dir.name),
        })
    return skills


def get_installed_skill_names(workspace_path: str) -> set[str]:
    ws_skills = Path(workspace_path) / "skills"
    if not ws_skills.is_dir():
        return set()
    return {
        d.name
        for d in ws_skills.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    }


def install_skill(skill_name: str, workspace_path: str) -> None:
    src = MANAGER_SKILLS_DIR / skill_name
    if not src.is_dir():
        raise FileNotFoundError(f"Skill not found: {skill_name}")

    dst = Path(workspace_path) / "skills" / skill_name
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(src, dst)
    except FileExistsError:
        raise FileExistsError(f"Skill already installed: {skill_name}") from None
    logger.info("Installed skill '{}' to {}", skill_name, workspace_path)


def uninstall_skill(skill_name: str, workspace_path: str) -> None:
    dst = Path(workspace_path) / "skills" / skill_name
    if not dst.is_dir():
        raise FileNotFoundError(f"Skill not installed: {skill_name}")
    shutil.rmtree(dst, ignore_errors=True)
    logger.info("Uninstalled skill '{}' from {}", skill_name, workspace_path)
