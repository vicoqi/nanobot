"""Tests for manager API endpoints using httpx AsyncClient."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from nanobot.manager.app import create_app, _AppState
from nanobot.manager.auth import hash_password, create_access_token
from nanobot.manager.config import ManagerConfig, ManagerServerConfig
from nanobot.manager.database import Database


@pytest.fixture
async def client(tmp_path: Path) -> AsyncClient:
    config_path = tmp_path / "manager-config.json"
    secret = "test-secret-key-for-tests"
    config = ManagerConfig(
        manager=ManagerServerConfig(secret_key=secret, admin_password="admin123"),
    )
    config._config_path = config_path
    # Write config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config.model_dump(mode="json", by_alias=True, exclude={"_config_path"})))

    app = create_app(config_path)

    # on_event("startup") doesn't fire with ASGITransport, so init DB manually
    from nanobot.manager.app import _app_state
    assert _app_state is not None
    await _app_state.db.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await _app_state.db.close()


def _auth_header(secret: str, user_id: int = 1) -> dict:
    token = create_access_token({"sub": str(user_id)}, secret)
    return {"Authorization": f"Bearer {token}"}


class TestAuthEndpoints:
    async def test_register_and_login(self, client: AsyncClient):
        resp = await client.post("/api/auth/register", json={"username": "alice", "password": "pass123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data

        resp = await client.post("/api/auth/login", json={"username": "alice", "password": "pass123"})
        assert resp.status_code == 200
        assert "token" in resp.json()

    async def test_register_duplicate(self, client: AsyncClient):
        await client.post("/api/auth/register", json={"username": "bob", "password": "p"})
        resp = await client.post("/api/auth/register", json={"username": "bob", "password": "p"})
        assert resp.status_code == 400

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post("/api/auth/register", json={"username": "charlie", "password": "right"})
        resp = await client.post("/api/auth/login", json={"username": "charlie", "password": "wrong"})
        assert resp.status_code == 401


class TestAgentCRUD:
    async def test_create_and_list(self, client: AsyncClient):
        reg = await client.post("/api/auth/register", json={"username": "alice", "password": "p"})
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/agents", json={"name": "My Agent", "soul": "Be helpful"}, headers=headers)
        assert resp.status_code == 200
        agent = resp.json()
        assert agent["name"] == "My Agent"
        assert agent["status"] == "stopped"
        assert agent["dailyDeliveryEnabled"] is False

        config_path = Path(agent["configPath"])
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        assert config_data["agents"]["defaults"]["dailyDelivery"]["enabled"] is False

        resp = await client.get("/api/agents", headers=headers)
        assert resp.status_code == 200
        agents = resp.json()
        assert len(agents) == 1
        assert agents[0]["name"] == "My Agent"

    async def test_update_agent(self, client: AsyncClient):
        reg = await client.post("/api/auth/register", json={"username": "bob", "password": "p"})
        headers = {"Authorization": f"Bearer {reg.json()['token']}"}

        create = await client.post("/api/agents", json={"name": "Old"}, headers=headers)
        created = create.json()
        agent_id = created["id"]
        config_path = Path(created["configPath"])

        resp = await client.put(
            f"/api/agents/{agent_id}",
            json={"name": "New", "dailyDeliveryEnabled": True},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"
        assert resp.json()["dailyDeliveryEnabled"] is True

        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        assert config_data["agents"]["defaults"]["dailyDelivery"]["enabled"] is True
        assert config_data["agents"]["defaults"]["dailyDelivery"]["cron"] == "0 8 * * *"

    async def test_delete_agent(self, client: AsyncClient):
        reg = await client.post("/api/auth/register", json={"username": "carol", "password": "p"})
        headers = {"Authorization": f"Bearer {reg.json()['token']}"}

        create = await client.post("/api/agents", json={"name": "ToDelete"}, headers=headers)
        agent_id = create.json()["id"]

        resp = await client.delete(f"/api/agents/{agent_id}", headers=headers)
        assert resp.status_code == 200

        resp = await client.get("/api/agents", headers=headers)
        assert len(resp.json()) == 0

    async def test_unauthorized_access(self, client: AsyncClient):
        resp = await client.get("/api/agents")
        assert resp.status_code == 401

    async def test_agent_ownership_check(self, client: AsyncClient):
        r1 = await client.post("/api/auth/register", json={"username": "u1", "password": "p"})
        r2 = await client.post("/api/auth/register", json={"username": "u2", "password": "p"})
        h1 = {"Authorization": f"Bearer {r1.json()['token']}"}
        h2 = {"Authorization": f"Bearer {r2.json()['token']}"}

        create = await client.post("/api/agents", json={"name": "A1"}, headers=h1)
        agent_id = create.json()["id"]

        resp = await client.get(f"/api/agents/{agent_id}", headers=h2)
        assert resp.status_code == 403

    async def test_get_status(self, client: AsyncClient):
        reg = await client.post("/api/auth/register", json={"username": "dave", "password": "p"})
        headers = {"Authorization": f"Bearer {reg.json()['token']}"}

        create = await client.post("/api/agents", json={"name": "A"}, headers=headers)
        agent_id = create.json()["id"]

        resp = await client.get(f"/api/agents/{agent_id}/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"
        assert data["alive"] is False


class TestAdminEndpoints:
    async def test_admin_login(self, client: AsyncClient):
        resp = await client.post("/admin/auth/login", json={"password": "admin123"})
        assert resp.status_code == 200
        assert "token" in resp.json()

    async def test_admin_login_wrong(self, client: AsyncClient):
        resp = await client.post("/admin/auth/login", json={"password": "wrong"})
        assert resp.status_code == 401

    async def test_admin_stats(self, client: AsyncClient):
        admin = await client.post("/admin/auth/login", json={"password": "admin123"})
        headers = {"Authorization": f"Bearer {admin.json()['token']}"}

        # Create a user and agent
        await client.post("/api/auth/register", json={"username": "alice", "password": "p"})

        resp = await client.get("/admin/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalUsers"] == 1
        assert data["totalAgents"] == 0

    async def test_admin_users_list(self, client: AsyncClient):
        admin = await client.post("/admin/auth/login", json={"password": "admin123"})
        headers = {"Authorization": f"Bearer {admin.json()['token']}"}

        await client.post("/api/auth/register", json={"username": "bob", "password": "p"})
        resp = await client.get("/admin/users", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["username"] == "bob"

    async def test_admin_requires_auth(self, client: AsyncClient):
        resp = await client.get("/admin/agents")
        assert resp.status_code == 401
