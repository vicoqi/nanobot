"""Skills filesystem operations for the agent manager."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import yaml
from loguru import logger

_STRIP_FRONTMATTER = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?",
    re.DOTALL,
)
# Whitelist for skill directory names. Matches the marketplace service's
# ``_SKILL_RE`` (skills_marketplace.py): lowercase alphanumerics joined by
# single hyphens. Rejecting anything else (``..``, ``a/b``, ``A-Bad``, ...)
# blocks path traversal in ``uninstall_global_skill`` before it ever reaches
# ``shutil.rmtree``.
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def global_skills_dir(config) -> Path:
    """Resolve the global manager-skills repo path from a ManagerConfig."""
    return Path(config.data_dir) / "manager-skills"


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


def scan_available_skills(global_dir: Path) -> list[dict]:
    """Scan a global skills repo directory and return skill metadata."""
    global_dir = Path(global_dir)
    skills: list[dict] = []
    if not global_dir.is_dir():
        return skills

    for skill_dir in sorted(global_dir.iterdir()):
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


def install_skill(skill_name: str, workspace_path: str, global_dir: Path) -> None:
    """Symlink a skill from the global repo into the workspace's skills dir."""
    src = Path(global_dir) / skill_name
    if not src.is_dir():
        raise FileNotFoundError(f"Skill not found: {skill_name}")

    dst = Path(workspace_path) / "skills" / skill_name
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(src.resolve(), dst)
    except FileExistsError:
        raise FileExistsError(f"Skill already installed: {skill_name}") from None
    logger.info("Installed skill '{}' to {}", skill_name, workspace_path)


def uninstall_skill(skill_name: str, workspace_path: str) -> None:
    dst = Path(workspace_path) / "skills" / skill_name
    if not dst.exists():
        raise FileNotFoundError(f"Skill not installed: {skill_name}")
    dst.unlink()
    logger.info("Uninstalled skill '{}' from {}", skill_name, workspace_path)


def uninstall_global_skill(
    skill_name: str, global_dir: Path, workspaces_dir: Path
) -> int:
    """Remove a skill from the global repo and cascade-clean agent workspaces.

    When a global skill is removed, any symlinks pointing at it from agent
    workspaces would be left dangling. This walks every workspace and unlinks
    the matching symlink before removing the global repo copy.

    Returns the number of workspace symlinks that were removed.

    Raises ``FileNotFoundError`` if ``skill_name`` is not a strict whitelist
    match — this is a security guard: without it, ``DELETE /api/admin/skills/..``
    would resolve ``Path(global_dir) / ".."`` and let ``shutil.rmtree`` walk and
    delete the entire ``data_dir`` (database, config, every workspace).
    """
    if not isinstance(skill_name, str) or not _SKILL_NAME_RE.fullmatch(skill_name):
        raise FileNotFoundError(f"Invalid skill name: {skill_name!r}")

    cleaned = 0
    # ① Walk every agent workspace and unlink dangling symlinks. The iterdir
    # walk is best-effort: an OSError mid-iteration (race, permission, broken
    # NFS mount) must not prevent step ② from removing the global repo copy.
    if Path(workspaces_dir).is_dir():
        try:
            for ws in Path(workspaces_dir).iterdir():
                link = ws / "skills" / skill_name
                if link.is_symlink():
                    try:
                        link.unlink()
                        cleaned += 1
                    except OSError:
                        # Race or permission issue — skip but keep going so the
                        # global repo copy still gets removed.
                        pass
        except OSError:
            pass
    # ② Remove the global repo directory itself.
    target = Path(global_dir) / skill_name
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    logger.info(
        "Uninstalled global skill '{}', cleaned {} workspace symlinks",
        skill_name,
        cleaned,
    )
    return cleaned
