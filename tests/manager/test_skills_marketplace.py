"""Tests for marketplace search/trending ported to the global skills dir.

These tests mock the httpx clients so no real network egress happens. They
verify response parsing, installed-skill marking (now read from ``global_dir``
instead of the upstream ``workspace_path``), provider routing, validation,
and trend loading.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from nanobot.manager.services import skills_marketplace as sm
from nanobot.manager.services.skills_marketplace import (
    SkillsMarketplaceError,
    _installed_skill_names,
    _load_skill_page_trends,
    _load_weekly_installs,
    _marketplace_skill,
    _response_json_object,
    _skillhub_skill,
    _valid_provider,
    _valid_skill_id,
    _valid_skill_refs,
    marketplace_skill_trends,
    search_marketplace_skills,
    skills_install_supported,
    trending_marketplace_skills,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_installed(global_dir: Path, name: str) -> None:
    """Create a skill directory with SKILL.md inside ``global_dir``."""
    d = global_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\ndescription: x\n---\n", encoding="utf-8")


def _make_response(status: int = 200, *, json=None, text: str | None = None) -> httpx.Response:
    """Build an httpx.Response with a request attached (raise_for_status-safe)."""
    request = httpx.Request("GET", "https://example.com/")
    return httpx.Response(status, json=json, text=text, request=request)


def _mock_client_factory(response: httpx.Response) -> MagicMock:
    """Return a mock matching ``_skills_client()`` / ``_skillhub_client()`` shape.

    The returned object is callable (``client()``) and synchronously returns an
    async-context-manager whose ``.get`` resolves to ``response``.
    """
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    # AsyncMock's default __aenter__ returns a child mock, not ``client``.
    # Bind it explicitly so ``async with client as c`` yields our configured
    # client with the stubbed ``.get``.
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=client)


async def _reset_weekly_cache() -> None:
    """Clear module-global trend cache so tests do not leak state."""
    sm._weekly_cache = {}
    sm._weekly_cache_expires_at = 0.0


# ---------------------------------------------------------------------------
# _response_json_object / pure helpers
# ---------------------------------------------------------------------------


def test_response_json_object_dict() -> None:
    resp = _make_response(json={"a": 1})
    assert _response_json_object(resp) == {"a": 1}


def test_response_json_object_non_dict_returns_none() -> None:
    resp = _make_response(json=[1, 2, 3])
    assert _response_json_object(resp) is None


def test_skills_install_supported_returns_bool() -> None:
    assert isinstance(skills_install_supported(), bool)


# ---------------------------------------------------------------------------
# _installed_skill_names — reads global_dir directly (key adaptation)
# ---------------------------------------------------------------------------


def test_installed_skill_names_reads_global_dir(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    _make_installed(global_dir, "alpha")
    _make_installed(global_dir, "beta")
    # Directory without SKILL.md is ignored.
    (global_dir / "not-a-skill").mkdir(parents=True)
    assert _installed_skill_names(global_dir) == {"alpha", "beta"}


def test_installed_skill_names_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert _installed_skill_names(tmp_path / "missing") == set()


# ---------------------------------------------------------------------------
# _marketplace_skill / _skillhub_skill parsing
# ---------------------------------------------------------------------------


def test_marketplace_skill_valid() -> None:
    row = {"source": "owner/repo", "skillId": "my-skill", "name": "My", "installs": 7}
    skill = _marketplace_skill(row, set())
    assert skill is not None
    assert skill["id"] == "owner/repo/my-skill"
    assert skill["skill_id"] == "my-skill"
    assert skill["installed"] is False
    assert skill["installs"] == 7
    assert skill["provider"] == "skills_sh"


def test_marketplace_skill_marks_installed() -> None:
    row = {"source": "owner/repo", "skillId": "my-skill", "name": "My"}
    skill = _marketplace_skill(row, {"my-skill"})
    assert skill is not None
    assert skill["installed"] is True


def test_marketplace_skill_rejects_bad_source() -> None:
    row = {"source": "bad", "skillId": "ok", "name": "x"}
    assert _marketplace_skill(row, set()) is None


def test_skillhub_skill_valid() -> None:
    row = {
        "slug": "hub-skill",
        "displayName": "Hub",
        "namespace": {"handle": "alice"},
        "installs": 3,
        "downloads": 10,
        "publisher": {"verified": True},
        "labels": {"requires_api_key": "true"},
        "version": "1.2.3",
    }
    skill = _skillhub_skill(row, set())
    assert skill is not None
    assert skill["skill_id"] == "hub-skill"
    assert skill["source"] == "@alice/hub-skill"
    assert skill["installed"] is False
    assert skill["verified"] is True
    assert skill["requires_api_key"] is True
    assert skill["version"] == "1.2.3"


def test_skillhub_skill_rejects_bad_slug() -> None:
    row = {"slug": "Invalid Slug"}
    assert _skillhub_skill(row, set()) is None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def test_valid_provider_defaults_to_all() -> None:
    assert _valid_provider("") == "all"


def test_valid_provider_rejects_unknown() -> None:
    with pytest.raises(SkillsMarketplaceError):
        _valid_provider("nope")


def test_valid_provider_allow_all_false_rejects_all() -> None:
    with pytest.raises(SkillsMarketplaceError):
        _valid_provider("all", allow_all=False)


def test_valid_skill_id_accepts_kebab() -> None:
    assert _valid_skill_id("foo-bar-123") is True


def test_valid_skill_id_rejects_uppercase() -> None:
    assert _valid_skill_id("FooBar") is False


def test_valid_skill_refs_parses_owner_repo_skill() -> None:
    """A ref shaped like owner/repo/skill-id splits into (owner/repo, skill-id)."""
    refs = _valid_skill_refs(["owner/repo/foo-bar", "bad-no-slash", "x"])
    assert ("owner/repo", "foo-bar") in refs
    assert len(refs) == 1


def test_valid_skill_refs_dedupes() -> None:
    refs = _valid_skill_refs(["owner/repo/foo", "owner/repo/foo"])
    assert refs == [("owner/repo", "foo")]


# ---------------------------------------------------------------------------
# search_marketplace_skills — skills.sh
# ---------------------------------------------------------------------------


async def test_search_skills_sh_marks_installed(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    _make_installed(global_dir, "already-installed")

    fake_resp = _make_response(
        json={
            "skills": [
                {
                    "source": "owner/repo",
                    "skillId": "already-installed",
                    "name": "Already",
                    "installs": 1,
                },
                {
                    "source": "owner/repo",
                    "skillId": "new-one",
                    "name": "New",
                    "installs": 0,
                },
            ]
        },
    )
    with patch.object(sm, "_skills_client", _mock_client_factory(fake_resp)):
        result = await search_marketplace_skills("query", global_dir, provider="skills_sh")

    skills = {s["skill_id"]: s for s in result["skills"]}
    assert skills["already-installed"]["installed"] is True
    assert skills["new-one"]["installed"] is False
    assert result["provider"] == "skills_sh"


async def test_search_skills_sh_query_too_short(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="at least 2"):
        await search_marketplace_skills("q", tmp_path, provider="skills_sh")


async def test_search_skills_sh_query_too_long(tmp_path: Path) -> None:
    with pytest.raises(SkillsMarketplaceError, match="too long"):
        await search_marketplace_skills("x" * 101, tmp_path, provider="skills_sh")


async def test_search_skills_sh_http_error_raises_502(tmp_path: Path) -> None:
    fake_resp = _make_response(500, text="boom")
    with patch.object(sm, "_skills_client", _mock_client_factory(fake_resp)):
        with pytest.raises(SkillsMarketplaceError) as exc:
            await search_marketplace_skills("query", tmp_path, provider="skills_sh")
    assert exc.value.status == 502


# ---------------------------------------------------------------------------
# search_marketplace_skills — skillhub
# ---------------------------------------------------------------------------


async def test_search_skillhub_marks_installed(tmp_path: Path) -> None:
    global_dir = tmp_path / "manager-skills"
    _make_installed(global_dir, "hub-installed")

    fake_resp = _make_response(
        json={
            "results": [
                {"slug": "hub-installed", "displayName": "HubInst"},
                {"slug": "hub-new", "displayName": "HubNew"},
            ]
        },
    )
    with patch.object(sm, "_skillhub_client", _mock_client_factory(fake_resp)):
        result = await search_marketplace_skills("query", global_dir, provider="skillhub")

    skills = {s["skill_id"]: s for s in result["skills"]}
    assert skills["hub-installed"]["installed"] is True
    assert skills["hub-new"]["installed"] is False
    assert result["provider"] == "skillhub"


# ---------------------------------------------------------------------------
# search_marketplace_skills — "all" combines both providers
# ---------------------------------------------------------------------------


async def test_search_all_combines_both_providers(tmp_path: Path) -> None:
    skills_sh_resp = _make_response(
        json={"skills": [{"source": "owner/repo", "skillId": "sh-one", "name": "SH"}]},
    )
    skillhub_resp = _make_response(
        json={"results": [{"slug": "hub-one", "displayName": "Hub"}]},
    )
    with (
        patch.object(sm, "_skills_client", _mock_client_factory(skills_sh_resp)),
        patch.object(sm, "_skillhub_client", _mock_client_factory(skillhub_resp)),
    ):
        result = await search_marketplace_skills("query", tmp_path, provider="all")

    ids = [s["skill_id"] for s in result["skills"]]
    assert "sh-one" in ids
    assert "hub-one" in ids
    assert result["provider"] == "all"


async def test_search_all_both_fail_raises_502(tmp_path: Path) -> None:
    bad = _make_response(503, text="down")
    with (
        patch.object(sm, "_skills_client", _mock_client_factory(bad)),
        patch.object(sm, "_skillhub_client", _mock_client_factory(bad)),
    ):
        with pytest.raises(SkillsMarketplaceError) as exc:
            await search_marketplace_skills("query", tmp_path, provider="all")
    assert exc.value.status == 502


# ---------------------------------------------------------------------------
# trending_marketplace_skills
# ---------------------------------------------------------------------------


async def test_trending_skills_sh_source_diversity(tmp_path: Path) -> None:
    """Trending picks one skill per source until the limit is reached."""
    fake_resp = _make_response(
        json={
            "skills": [
                {"source": "alice/a", "skillId": "one", "name": "One"},
                {"source": "alice/a", "skillId": "two", "name": "Two"},  # dup source
                {"source": "bob/b", "skillId": "three", "name": "Three"},
            ]
        },
    )
    with patch.object(sm, "_skills_client", _mock_client_factory(fake_resp)):
        result = await trending_marketplace_skills(tmp_path, limit=8, provider="skills_sh")

    sources = [s["source"] for s in result["skills"]]
    assert sources == ["alice/a", "bob/b"]
    assert result["period"] == "24h"
    # Rank reflects original leaderboard position (skipped dup still consumes rank).
    assert [s["rank"] for s in result["skills"]] == [1, 3]


async def test_trending_skillhub_caps_at_limit(tmp_path: Path) -> None:
    rows = [
        {"slug": f"skill-{i}", "displayName": f"S{i}"}
        for i in range(5)
    ]
    fake_resp = _make_response(json={"skills": rows})
    with patch.object(sm, "_skillhub_client", _mock_client_factory(fake_resp)):
        result = await trending_marketplace_skills(tmp_path, limit=2, provider="skillhub")
    assert len(result["skills"]) == 2
    assert result["period"] == "trending"


async def test_trending_all_combines(tmp_path: Path) -> None:
    skills_sh_resp = _make_response(
        json={"skills": [{"source": "alice/a", "skillId": "sh", "name": "SH"}]},
    )
    skillhub_resp = _make_response(
        json={"skills": [{"slug": "hub", "displayName": "Hub"}]},
    )
    with (
        patch.object(sm, "_skills_client", _mock_client_factory(skills_sh_resp)),
        patch.object(sm, "_skillhub_client", _mock_client_factory(skillhub_resp)),
    ):
        result = await trending_marketplace_skills(tmp_path, provider="all")
    ids = [s["skill_id"] for s in result["skills"]]
    assert "sh" in ids
    assert "hub" in ids
    assert result["provider"] == "all"


# ---------------------------------------------------------------------------
# marketplace_skill_trends + _load_weekly_installs + _load_skill_page_trends
# ---------------------------------------------------------------------------


async def test_load_weekly_installs_parses_values() -> None:
    await _reset_weekly_cache()
    resp = _make_response(
        json={
            "skills": [
                {
                    "source": "owner/repo",
                    "skillId": "trending-skill",
                    "weeklyInstalls": [1, 2, 3],
                }
            ]
        },
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    history = await _load_weekly_installs(client)
    assert history[("owner/repo", "trending-skill")] == [1, 2, 3]


async def test_load_skill_page_trends_extracts_values() -> None:
    page = _make_response(text='<script>data=\\"values\\": [10, 20, 30]</script>')
    client = AsyncMock()
    client.get = AsyncMock(return_value=page)
    result = await _load_skill_page_trends(client, [("owner/repo", "x")])
    assert result == {("owner/repo", "x"): [10, 20, 30]}


async def test_marketplace_skill_trends_returns_requested(tmp_path: Path) -> None:
    """End-to-end: weekly cache hit serves the requested skill ref."""
    await _reset_weekly_cache()
    weekly_resp = _make_response(
        json={
            "skills": [
                {
                    "source": "owner/repo",
                    "skillId": "wk",
                    "weeklyInstalls": [5, 6],
                }
            ]
        },
    )
    client = AsyncMock()
    client.get = AsyncMock(return_value=weekly_resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    # ``_skills_client`` must return the client synchronously (not a coroutine)
    # because marketplace_skill_trends does ``async with _skills_client() as c``.
    with patch.object(sm, "_skills_client", MagicMock(return_value=client)):
        result = await marketplace_skill_trends(["owner/repo/wk"])
    assert result["trends"]["owner/repo/wk"] == [5, 6]
