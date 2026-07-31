"""Tests for the admin marketplace API endpoints.

Mirrors the fixture/auth pattern in ``tests/manager/test_api.py``: a single
``client`` fixture builds a real FastAPI app over ``tmp_path`` and tests log in
via ``/admin/auth/login`` to obtain an admin bearer token. Service-layer
functions (``search_marketplace_skills`` etc.) are mocked at the marketplace
module's namespace so no real network calls are made.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from nanobot.manager.app import create_app
from nanobot.manager.config import ManagerConfig, ManagerServerConfig


@pytest.fixture
async def client(tmp_path: Path) -> AsyncClient:
    config_path = tmp_path / "manager-config.json"
    config = ManagerConfig(
        manager=ManagerServerConfig(secret_key="test-secret", admin_password="admin123"),
    )
    config._config_path = config_path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config.model_dump(mode="json", by_alias=True, exclude={"_config_path"}))
    )

    app = create_app(config_path)

    from nanobot.manager.app import _app_state

    assert _app_state is not None
    await _app_state.db.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await _app_state.db.close()


async def _admin_headers(client: AsyncClient) -> dict:
    resp = await client.post("/admin/auth/login", json={"password": "admin123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


class TestMarketplaceSearch:
    async def test_search_requires_admin(self, client: AsyncClient):
        resp = await client.get("/api/admin/skills/marketplace/search?q=foo")
        assert resp.status_code == 401

    async def test_search_returns_results(self, client: AsyncClient):
        payload = {"skills": [{"id": "a/b", "installed": False}], "provider": "all"}
        with patch(
            "nanobot.manager.api.marketplace.search_marketplace_skills",
            new=AsyncMock(return_value=payload),
        ):
            resp = await client.get(
                "/api/admin/skills/marketplace/search?q=foo&source=all",
                headers=await _admin_headers(client),
            )
        assert resp.status_code == 200
        assert resp.json() == payload

    async def test_search_passes_query_and_source(self, client: AsyncClient):
        captured: dict = {}

        async def fake(query, global_dir, *, provider="all"):
            captured.update(query=query, provider=provider)
            return {"skills": [], "provider": provider}

        with patch(
            "nanobot.manager.api.marketplace.search_marketplace_skills",
            new=fake,
        ):
            resp = await client.get(
                "/api/admin/skills/marketplace/search?q=bar&source=skillhub",
                headers=await _admin_headers(client),
            )
        assert resp.status_code == 200
        assert captured == {"query": "bar", "provider": "skillhub"}

    async def test_search_defaults_source_to_all(self, client: AsyncClient):
        # Omitting the `source` query param must fall through to "all".
        captured: dict = {}

        async def fake(query, global_dir, *, provider="all"):
            captured.update(provider=provider)
            return {"skills": [], "provider": provider}

        with patch(
            "nanobot.manager.api.marketplace.search_marketplace_skills",
            new=fake,
        ):
            resp = await client.get(
                "/api/admin/skills/marketplace/search?q=foo",
                headers=await _admin_headers(client),
            )
        assert resp.status_code == 200
        assert captured == {"provider": "all"}


class TestMarketplaceTrending:
    async def test_trending_requires_admin(self, client: AsyncClient):
        resp = await client.get("/api/admin/skills/marketplace/trending")
        assert resp.status_code == 401

    async def test_trending_returns_results(self, client: AsyncClient):
        payload = {"skills": [{"id": "trending/one"}], "period": "24h"}
        with patch(
            "nanobot.manager.api.marketplace.trending_marketplace_skills",
            new=AsyncMock(return_value=payload),
        ):
            resp = await client.get(
                "/api/admin/skills/marketplace/trending?source=skills_sh",
                headers=await _admin_headers(client),
            )
        assert resp.status_code == 200
        assert resp.json() == payload

    async def test_trending_passes_source(self, client: AsyncClient):
        captured: dict = {}

        async def fake(global_dir, *, provider="all"):
            captured.update(provider=provider)
            return {"skills": [], "provider": provider}

        with patch(
            "nanobot.manager.api.marketplace.trending_marketplace_skills",
            new=fake,
        ):
            resp = await client.get(
                "/api/admin/skills/marketplace/trending?source=skillhub",
                headers=await _admin_headers(client),
            )
        assert resp.status_code == 200
        assert captured == {"provider": "skillhub"}


class TestMarketplaceInstall:
    async def test_install_requires_admin(self, client: AsyncClient):
        resp = await client.post(
            "/api/admin/skills/marketplace/install",
            json={"skillId": "x", "source": "owner/repo"},
        )
        assert resp.status_code == 401

    async def test_install_success(self, client: AsyncClient):
        captured: dict = {}

        async def fake(source, skill_id, global_dir, *, provider="skills_sh", version=""):
            captured.update(
                source=source,
                skill_id=skill_id,
                provider=provider,
                version=version,
                global_dir=global_dir,
            )
            return {"installed": True, "already_installed": False, "name": skill_id}

        with patch(
            "nanobot.manager.api.marketplace.install_marketplace_skill",
            new=fake,
        ):
            resp = await client.post(
                "/api/admin/skills/marketplace/install",
                json={
                    "skillId": "my-skill",
                    "source": "owner/repo",
                    "provider": "skills_sh",
                    "version": "1.2.0",
                },
                headers=await _admin_headers(client),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "installed": True,
            "already_installed": False,
            "name": "my-skill",
        }
        # Service called with the configured global skills dir + forwarded kwargs
        assert captured["source"] == "owner/repo"
        assert captured["skill_id"] == "my-skill"
        assert captured["provider"] == "skills_sh"
        assert captured["version"] == "1.2.0"
        assert captured["global_dir"].name == "manager-skills"

    async def test_install_defaults_provider_and_version(self, client: AsyncClient):
        captured: dict = {}

        async def fake(source, skill_id, global_dir, *, provider="skills_sh", version=""):
            captured.update(provider=provider, version=version)
            return {"installed": True, "name": skill_id}

        with patch(
            "nanobot.manager.api.marketplace.install_marketplace_skill",
            new=fake,
        ):
            resp = await client.post(
                "/api/admin/skills/marketplace/install",
                json={"skillId": "my-skill", "source": "owner/repo"},
                headers=await _admin_headers(client),
            )
        assert resp.status_code == 200
        assert captured == {"provider": "skills_sh", "version": ""}

    async def test_install_marketplace_error_returns_400(self, client: AsyncClient):
        from nanobot.manager.services.skills_marketplace import SkillsMarketplaceError

        with patch(
            "nanobot.manager.api.marketplace.install_marketplace_skill",
            new=AsyncMock(side_effect=SkillsMarketplaceError("boom")),
        ):
            resp = await client.post(
                "/api/admin/skills/marketplace/install",
                json={"skillId": "x", "source": "owner/repo"},
                headers=await _admin_headers(client),
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "boom"


class TestInstalledSkills:
    async def test_installed_requires_admin(self, client: AsyncClient):
        resp = await client.get("/api/admin/skills")
        assert resp.status_code == 401

    async def test_installed_empty_when_no_global_dir(self, client: AsyncClient):
        # tmp_path/manager-skills does not exist yet → scan returns []
        resp = await client.get("/api/admin/skills", headers=await _admin_headers(client))
        assert resp.status_code == 200
        assert resp.json() == {"skills": []}

    async def test_installed_returns_scanned_skills(self, client: AsyncClient, tmp_path: Path):
        scanned = [{"name": "alpha", "description": "desc"}]
        with patch(
            "nanobot.manager.api.marketplace.scan_available_skills",
            return_value=scanned,
        ):
            resp = await client.get(
                "/api/admin/skills", headers=await _admin_headers(client)
            )
        assert resp.status_code == 200
        assert resp.json() == {"skills": scanned}
