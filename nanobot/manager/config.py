"""Manager configuration schema and loading utilities."""

import json
import secrets
from pathlib import Path
from typing import Any

import pydantic
from loguru import logger
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from nanobot.config.schema import ProvidersConfig


class Base(BaseModel):
    """Base model accepting both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ManagerServerConfig(Base):
    """Manager HTTP server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080
    admin_password: str = "changeme"
    secret_key: str = secrets.token_hex(32)


class AgentDefaultsConfig(Base):
    """Default agent settings inherited by all new agents."""

    model: str = "anthropic/claude-sonnet-4-6"
    provider: str = "auto"
    max_tokens: int = 8192
    context_window_tokens: int = 65536


class ManagerConfig(Base):
    """Root configuration for the agent manager."""

    manager: ManagerServerConfig = ManagerServerConfig()
    providers: ProvidersConfig = ProvidersConfig()
    agent_defaults: AgentDefaultsConfig = AgentDefaultsConfig()
    port_range: list[int] = [19000, 19999]

    @property
    def data_dir(self) -> Path:
        """Manager data directory derived from config file location."""
        return self._config_path.parent if self._config_path else Path.home() / ".nanobot-manager"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "manager.db"

    @property
    def configs_dir(self) -> Path:
        return self.data_dir / "configs"

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    def __init__(self, **data: Any):
        super().__init__(**data)
        self._config_path: Path | None = None


_DEFAULT_CONFIG_PATH = Path.home() / ".nanobot-manager" / "manager-config.json"


def load_manager_config(config_path: Path | None = None) -> ManagerConfig:
    """Load manager config from file or create default."""
    path = config_path or _DEFAULT_CONFIG_PATH
    config = ManagerConfig()
    config._config_path = path

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            config = ManagerConfig.model_validate(data)
            config._config_path = path
        except (json.JSONDecodeError, ValueError, pydantic.ValidationError) as e:
            logger.warning("Failed to load manager config from {}: {}", path, e)
            logger.warning("Using default configuration.")

    return config


def save_manager_config(config: ManagerConfig, config_path: Path | None = None) -> None:
    """Save manager config to file."""
    path = config_path or config._config_path or _DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(mode="json", by_alias=True, exclude={"_config_path"})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
