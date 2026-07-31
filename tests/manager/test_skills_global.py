"""Tests for skills service operating against the global skills repo."""

from __future__ import annotations

from pathlib import Path

from nanobot.manager.config import ManagerConfig
from nanobot.manager.services.skills import (
    get_installed_skill_names,
    global_skills_dir,
    install_skill,
    scan_available_skills,
    uninstall_skill,
)


def _make_skill(global_dir: Path, name: str, desc: str = "test") -> None:
    d = global_dir / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\ndescription: {desc}\n---\nbody", encoding="utf-8"
    )


def test_scan_reads_global_dir(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    _make_skill(global_dir, "alpha")
    result = scan_available_skills(global_dir)
    assert [s["name"] for s in result] == ["alpha"]
    assert result[0]["description"] == "test"


def test_scan_returns_empty_when_missing(tmp_path: Path) -> None:
    # global_dir does not exist
    result = scan_available_skills(tmp_path / "manager-skills")
    assert result == []


def test_install_symlinks_from_global_to_workspace(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    _make_skill(global_dir, "alpha")
    install_skill("alpha", workspace, global_dir)
    installed = get_installed_skill_names(workspace)
    assert "alpha" in installed
    # Symlink must point at the global repo copy
    assert (workspace / "skills" / "alpha").is_symlink()


def test_install_missing_skill_raises(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    global_dir.mkdir(parents=True)
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    try:
        install_skill("nope", workspace, global_dir)
    except FileNotFoundError as e:
        assert "nope" in str(e)
    else:
        raise AssertionError("Expected FileNotFoundError")


def test_uninstall_removes_symlink(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    _make_skill(global_dir, "alpha")
    install_skill("alpha", workspace, global_dir)
    uninstall_skill("alpha", workspace)
    assert not (workspace / "skills" / "alpha").exists()


def test_global_skills_dir_uses_config(tmp_path: Path, monkeypatch) -> None:
    cfg = ManagerConfig()
    monkeypatch.setattr(cfg, "_config_path", tmp_path / "manager-config.json")
    assert global_skills_dir(cfg) == tmp_path / "manager-skills"
