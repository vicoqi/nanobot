"""Generate nanobot-compatible config.json for each agent."""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from nanobot.manager.config import ManagerConfig
from nanobot.manager.models import Agent


def build_agent_config(manager_config: ManagerConfig, agent: Agent) -> dict:
    """Build a nanobot-compatible config dict for an agent worker process."""
    defaults = manager_config.agent_defaults
    providers_data = manager_config.providers.model_dump(mode="json", by_alias=True, exclude_none=True)

    return {
        "agents": {
            "defaults": {
                "workspace": agent.workspace_path,
                "model": defaults.model,
                "provider": defaults.provider,
                "maxTokens": defaults.max_tokens,
                "contextWindowTokens": defaults.context_window_tokens,
            },
        },
        "providers": providers_data,
        "gateway": {
            "host": "127.0.0.1",
            "port": agent.gateway_port,
        },
        "channels": {
            "weixin": {
                "enabled": agent.wechat_bound,
                "token": agent.wechat_bot_token,
                "stateDir": str(Path(agent.workspace_path) / "weixin"),
                "allowFrom": ["*"],
            },
        },
    }


def write_agent_files(agent: Agent, config: dict) -> None:
    """Create config dir, workspace dir, config.json, SOUL.md, and subdirectories."""
    config_path = Path(agent.config_path)
    workspace_path = Path(agent.workspace_path)

    # Config directory
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    # Workspace directories
    workspace_path.mkdir(parents=True, exist_ok=True)
    (workspace_path / "memory").mkdir(exist_ok=True)
    (workspace_path / "sessions").mkdir(exist_ok=True)
    (workspace_path / "weixin").mkdir(exist_ok=True)

    # SOUL.md
    soul_path = workspace_path / "SOUL.md"
    soul_path.write_text(agent.soul or f"# {agent.name}\n", encoding="utf-8")

    logger.info("Agent files written: config={}, workspace={}", config_path, workspace_path)


def cleanup_agent_files(agent: Agent) -> None:
    """Remove config and workspace directories for a deleted agent."""
    import shutil

    config_path = Path(agent.config_path)
    workspace_path = Path(agent.workspace_path)

    if config_path.parent.exists():
        shutil.rmtree(config_path.parent, ignore_errors=True)
        logger.info("Cleaned up config dir: {}", config_path.parent)

    if workspace_path.exists():
        shutil.rmtree(workspace_path, ignore_errors=True)
        logger.info("Cleaned up workspace: {}", workspace_path)
