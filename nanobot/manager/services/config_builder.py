"""Generate nanobot-compatible config.json for each agent."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from loguru import logger

from nanobot.manager.config import ManagerConfig
from nanobot.manager.models import Agent

DEFAULT_FRIENDLY_DELIVERY_CRON = "0 8 * * *"


def build_soul_md(agent: Agent) -> str:
    """Build SOUL.md content with profile info and user-defined personality."""
    gender_map = {"female": "女性", "male": "男性"}
    lang_map = {"zh": "中文", "en": "English"}
    gender = gender_map.get(agent.gender, agent.gender)
    lang = lang_map.get(agent.language, agent.language)

    lines = [f"# {agent.name}", ""]
    lines.append(f"你是{agent.name}，{gender}，说{lang}，生活在{agent.city}。")
    if agent.soul:
        lines.append("")
        lines.append(agent.soul)
    lines.append("")
    return "\n".join(lines)


def build_agent_config(manager_config: ManagerConfig, agent: Agent) -> dict:
    """Build a nanobot-compatible config dict for an agent worker process."""
    defaults = manager_config.agent_defaults
    providers_data = manager_config.providers.model_dump(mode="json", by_alias=True, exclude_none=True)
    tools_config = manager_config.tools

    return {
        "agents": {
            "defaults": {
                "workspace": agent.workspace_path,
                "model": defaults.model,
                "provider": defaults.provider,
                "maxTokens": defaults.max_tokens,
                "contextWindowTokens": defaults.context_window_tokens,
                "timezone": "Asia/Shanghai",
                "dailyDelivery": {
                    "enabled": agent.daily_delivery_enabled,
                    "cron": DEFAULT_FRIENDLY_DELIVERY_CRON,
                },
            },
        },
        "providers": providers_data,
        "gateway": {
            "host": "127.0.0.1",
            "port": agent.gateway_port,
        },
        "tools": {
            "restrictToWorkspace": True,
            "imageGeneration": {
                "enabled": tools_config.image_generation.enabled,
                "provider": tools_config.image_generation.provider,
                "model": tools_config.image_generation.model,
            },
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

    # Default cron jobs (daily weather push)
    _write_default_cron_jobs(workspace_path, agent)

    # SOUL.md
    soul_path = workspace_path / "SOUL.md"
    soul_path.write_text(build_soul_md(agent), encoding="utf-8")

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


def _write_default_cron_jobs(workspace_path: Path, agent: Agent) -> None:
    """Write default cron jobs (daily weather push) to workspace."""
    cron_dir = workspace_path / "cron"
    cron_dir.mkdir(exist_ok=True)

    jobs_path = cron_dir / "jobs.json"
    if jobs_path.exists():
        return

    city = agent.city or "Shanghai"
    city_url = quote(city, safe="")
    lang = agent.language or "zh"

    if lang == "en":
        message = (
            f"Push today's weather for {city}. Use curl to get real-time weather: "
            f'curl -s "wttr.in/{city_url}?1&lang=en&T", then format it in a clean, '
            "friendly way and send to the user. Include: current temperature and "
            "feels-like, hourly forecast, rain probability, and travel tips."
        )
    else:
        message = (
            f"给老板推送今日{city}天气播报。使用 curl 获取{city}实时天气："
            f'curl -s "wttr.in/{city_url}?1&lang=zh&T"，然后整理成简洁友好的格式发送给老板。'
            "包括：当前温度和体感、全天各时段天气、降雨概率、出行建议。"
            "最后祝老板新的一天顺顺利利！"
        )

    now_ms = int(time.time() * 1000)
    jobs = [
        {
            "id": uuid.uuid4().hex[:8],
            "name": "每日天气播报",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 8 * * *", "tz": "Asia/Shanghai"},
            "payload": {"kind": "agent_turn", "message": message, "deliver": True},
            "state": {
                "nextRunAtMs": 0,
                "lastRunAtMs": None,
                "lastStatus": None,
                "lastError": None,
                "runHistory": [],
            },
            "createdAtMs": now_ms,
            "updatedAtMs": now_ms,
            "deleteAfterRun": False,
        }
    ]

    store = {"version": 1, "jobs": jobs}
    jobs_path.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


def update_agent_weixin_config(agent: Agent) -> None:
    """Update agent config.json to enable weixin channel after QR binding."""
    config_path = Path(agent.config_path)
    if not config_path.exists():
        logger.warning("Agent config not found: {}", config_path)
        return

    data = json.loads(config_path.read_text(encoding="utf-8"))
    data.setdefault("channels", {}).setdefault("weixin", {}).update({
        "enabled": True,
        "token": agent.wechat_bot_token,
    })
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Updated agent config: weixin enabled for agent {}", agent.id)


def update_agent_daily_delivery_config(agent: Agent) -> None:
    """Update agent config.json to reflect the friendly-delivery toggle."""
    config_path = Path(agent.config_path)
    if not config_path.exists():
        logger.warning("Agent config not found: {}", config_path)
        return

    data = json.loads(config_path.read_text(encoding="utf-8"))
    defaults = data.setdefault("agents", {}).setdefault("defaults", {})
    current = defaults.get("dailyDelivery")
    cron = DEFAULT_FRIENDLY_DELIVERY_CRON
    if isinstance(current, dict):
        existing_cron = current.get("cron")
        if isinstance(existing_cron, str) and existing_cron.strip():
            cron = existing_cron.strip()
    defaults["dailyDelivery"] = {
        "enabled": agent.daily_delivery_enabled,
        "cron": cron,
    }
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Updated agent config: dailyDelivery enabled={} for agent {}", agent.daily_delivery_enabled, agent.id)
