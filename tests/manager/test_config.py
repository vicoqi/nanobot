"""Tests for manager config schema."""

import json
from pathlib import Path

from nanobot.manager.config import (
    AgentDefaultsConfig,
    ManagerConfig,
    ManagerServerConfig,
    load_manager_config,
    save_manager_config,
)


class TestManagerServerConfig:
    def test_defaults(self):
        cfg = ManagerServerConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8080
        assert cfg.admin_password == "changeme"
        assert len(cfg.secret_key) == 64

    def test_camel_case_alias(self):
        cfg = ManagerServerConfig(admin_password="secret")
        dumped = cfg.model_dump(by_alias=True)
        assert "adminPassword" in dumped


class TestManagerConfig:
    def test_defaults(self):
        cfg = ManagerConfig()
        assert cfg.port_range == [19000, 19999]
        assert cfg.agent_defaults.model == "deepseek-chat"

    def test_camel_case_roundtrip(self):
        cfg = ManagerConfig(
            manager=ManagerServerConfig(port=9090),
            agent_defaults=AgentDefaultsConfig(model="gpt-4o"),
        )
        dumped = cfg.model_dump(mode="json", by_alias=True)
        assert dumped["agentDefaults"]["model"] == "gpt-4o"
        restored = ManagerConfig.model_validate(dumped)
        assert restored.agent_defaults.model == "gpt-4o"
        assert restored.manager.port == 9090


class TestLoadSaveConfig:
    def test_save_and_load(self, tmp_path: Path):
        config_path = tmp_path / "manager-config.json"
        cfg = ManagerConfig(manager=ManagerServerConfig(port=7070, admin_password="test123"))
        save_manager_config(cfg, config_path)

        assert config_path.exists()
        with open(config_path) as f:
            data = json.load(f)
        assert data["manager"]["port"] == 7070

        loaded = load_manager_config(config_path)
        assert loaded.manager.port == 7070
        assert loaded.manager.admin_password == "test123"

    def test_load_missing_file_returns_defaults(self, tmp_path: Path):
        loaded = load_manager_config(tmp_path / "nonexistent.json")
        assert loaded.manager.port == 8080

    def test_load_invalid_json_returns_defaults(self, tmp_path: Path):
        bad_path = tmp_path / "bad-config.json"
        bad_path.write_text("not json")
        loaded = load_manager_config(bad_path)
        assert loaded.manager.port == 8080
