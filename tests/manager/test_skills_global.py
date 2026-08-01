"""Tests for skills service operating against the global skills repo."""

from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.manager.config import ManagerConfig
from nanobot.manager.services.skills import (
    get_installed_skill_names,
    global_skills_dir,
    install_skill,
    scan_available_skills,
    uninstall_global_skill,
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


def test_install_copies_real_files_into_workspace(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    _make_skill(global_dir, "alpha")
    install_skill("alpha", workspace, global_dir)
    installed = get_installed_skill_names(workspace)
    assert "alpha" in installed
    # Must be a real directory with real files inside the workspace — NOT a
    # symlink to the global repo. A symlink resolves outside the workspace and
    # the agent refuses to read through it (marketplace skill access bug).
    skill_dir = workspace / "skills" / "alpha"
    assert not skill_dir.is_symlink()
    assert skill_dir.is_dir()
    assert (skill_dir / "SKILL.md").is_file()
    # The copy must resolve inside the workspace (no symlink escape).
    assert workspace.resolve() in skill_dir.resolve().parents


def test_install_missing_skill_raises(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    global_dir.mkdir(parents=True)
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="nope"):
        install_skill("nope", workspace, global_dir)


def test_install_twice_raises_file_exists(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    _make_skill(global_dir, "alpha")
    install_skill("alpha", workspace, global_dir)
    with pytest.raises(FileExistsError, match="already installed"):
        install_skill("alpha", workspace, global_dir)


def test_uninstall_removes_installed_copy(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    _make_skill(global_dir, "alpha")
    install_skill("alpha", workspace, global_dir)
    uninstall_skill("alpha", workspace)
    assert not (workspace / "skills" / "alpha").exists()


def test_uninstall_removes_legacy_symlink(tmp_path: Path) -> None:
    """uninstall_skill must still remove legacy symlink installs (pre-copy era)."""
    global_dir = tmp_path / "manager-skills"
    workspace = tmp_path / "ws"
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True)
    src = global_dir / "alpha"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text("---\ndescription: d\n---\n", encoding="utf-8")
    (skills_dir / "alpha").symlink_to(src.resolve())
    uninstall_skill("alpha", workspace)
    assert not (skills_dir / "alpha").exists()


def test_uninstall_rejects_traversal_name(tmp_path: Path) -> None:
    """A traversal ``skill_name`` must not resolve outside the workspace.

    Regression for the authenticated path-traversal issue (Codex P1): without
    name validation, ``uninstall_skill("../../manager.db", ws)`` would
    ``unlink()`` a file outside the workspace (e.g. the manager database).
    """
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    sentinel = tmp_path / "manager.db"
    sentinel.write_text("important", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        uninstall_skill("../../manager.db", workspace)
    assert sentinel.read_text(encoding="utf-8") == "important"


def test_uninstall_rejects_invalid_name(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    for bad in ("../etc", "A-Bad", "a/b", "UPPER", ""):
        with pytest.raises(FileNotFoundError):
            uninstall_skill(bad, workspace)


def test_global_skills_dir_uses_config(tmp_path: Path, monkeypatch) -> None:
    cfg = ManagerConfig()
    monkeypatch.setattr(cfg, "_config_path", tmp_path / "manager-config.json")
    assert global_skills_dir(cfg) == tmp_path / "manager-skills"


# --- uninstall_global_skill (Task 7) ----------------------------------------


def test_uninstall_global_cleans_all_workspaces(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    workspaces = tmp_path / "workspaces"
    _make_skill(global_dir, "alpha")
    # Two agent workspaces both symlinked alpha — these would go stale once
    # the global repo copy is removed.
    for ws in ("agent-1", "agent-2"):
        ws_dir = workspaces / ws
        (ws_dir / "skills").mkdir(parents=True)
        (ws_dir / "skills" / "alpha").symlink_to((global_dir / "alpha").resolve())

    cleaned = uninstall_global_skill("alpha", global_dir, workspaces)

    assert cleaned == 2
    assert not (global_dir / "alpha").exists()
    assert not (workspaces / "agent-1" / "skills" / "alpha").exists()
    assert not (workspaces / "agent-2" / "skills" / "alpha").exists()


def test_uninstall_global_tolerates_missing(tmp_path: Path) -> None:
    # Nothing exists — neither global repo entry nor any workspace symlinks.
    cleaned = uninstall_global_skill("nope", tmp_path, tmp_path)
    assert cleaned == 0


def test_uninstall_global_skips_non_symlink_dirs(tmp_path: Path) -> None:
    # A real directory under skills/ (not a symlink) must not be touched.
    global_dir = tmp_path / "manager-skills"
    workspaces = tmp_path / "workspaces"
    _make_skill(global_dir, "alpha")
    ws_dir = workspaces / "agent-1"
    regular = ws_dir / "skills" / "alpha"
    regular.mkdir(parents=True)
    (regular / "SKILL.md").write_text("real", encoding="utf-8")

    cleaned = uninstall_global_skill("alpha", global_dir, workspaces)

    assert cleaned == 0
    # Regular dir survived; global repo copy still removed.
    assert regular.exists()
    assert not (global_dir / "alpha").exists()


def test_uninstall_global_tolerates_broken_symlink(tmp_path: Path) -> None:
    # A dangling (already-broken) symlink should still count and be unlinked.
    global_dir = tmp_path / "manager-skills"
    workspaces = tmp_path / "workspaces"
    ws_dir = workspaces / "agent-1"
    (ws_dir / "skills").mkdir(parents=True)
    broken = ws_dir / "skills" / "alpha"
    broken.symlink_to(tmp_path / "does-not-exist")

    cleaned = uninstall_global_skill("alpha", global_dir, workspaces)

    assert cleaned == 1
    assert not broken.exists()


# --- uninstall_global_skill path-traversal guard (Fix Round 1) --------------


@pytest.mark.parametrize(
    "bad_name",
    [
        "..",          # headline traversal: Path(global_dir)/".." == data_dir
        "/etc",        # absolute-path override after Path join
        "a/b",         # nested path escape
        "A-Bad",       # uppercase rejected by whitelist
        "a_b",         # underscore is not in [a-z0-9-]
        "",            # empty
        ".hidden",     # leading dot
        "trailing-",   # trailing hyphen
        "-leading",    # leading hyphen
    ],
)
def test_uninstall_global_rejects_invalid_skill_name(
    tmp_path: Path, bad_name: str
) -> None:
    # Regardless of filesystem state, an invalid name must raise before any
    # rmtree ever runs — this is what blocks path traversal.
    with pytest.raises(FileNotFoundError, match="Invalid skill name"):
        uninstall_global_skill(
            bad_name, tmp_path / "manager-skills", tmp_path / "workspaces"
        )


def test_uninstall_global_does_not_delete_parent_on_traversal(tmp_path: Path) -> None:
    # The headline attack: ``DELETE /api/admin/skills/..`` would resolve
    # ``Path(global_dir) / ".."`` to the data_dir itself and rmtree it
    # (database, config, every workspace). The guard must fire before that.
    data_dir = tmp_path / "data"
    global_dir = data_dir / "manager-skills"
    workspaces = data_dir / "workspaces"
    global_dir.mkdir(parents=True)
    workspaces.mkdir()
    (global_dir / "real-skill").mkdir()
    (global_dir / "real-skill" / "SKILL.md").write_text("real", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        uninstall_global_skill("..", global_dir, workspaces)

    # data_dir and its contents survived — nothing was rmtree'd.
    assert data_dir.exists()
    assert (global_dir / "real-skill" / "SKILL.md").exists()


def test_uninstall_global_rejects_non_string(tmp_path: Path) -> None:
    # A None / int skill_name must be rejected, not coerced.
    for bad in (None, 123, ["a", "b"]):
        with pytest.raises(FileNotFoundError, match="Invalid skill name"):
            uninstall_global_skill(
                bad, tmp_path / "manager-skills", tmp_path / "workspaces"  # type: ignore[arg-type]
            )
