"""Tests for manager database layer."""

from pathlib import Path

import pytest

from nanobot.manager.database import Database
from nanobot.manager.models import AgentStatus


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.init()
    yield database
    await database.close()


class TestDatabaseInit:
    async def test_creates_tables(self, db: Database):
        cursor = await db.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in await cursor.fetchall()}
        assert "users" in tables
        assert "agents" in tables
        assert "wechat_bindings" in tables

    async def test_creates_db_file(self, tmp_path: Path):
        db_path = tmp_path / "subdir" / "test.db"
        db = Database(db_path)
        await db.init()
        assert db_path.exists()
        await db.close()


class TestUserCRUD:
    async def test_create_and_get(self, db: Database):
        user = await db.create_user("alice", "hash123")
        assert user.id is not None
        assert user.username == "alice"

        found = await db.get_user_by_username("alice")
        assert found is not None
        assert found.password_hash == "hash123"

    async def test_get_by_id(self, db: Database):
        user = await db.create_user("bob", "hash456")
        found = await db.get_user_by_id(user.id)
        assert found is not None
        assert found.username == "bob"

    async def test_unique_username(self, db: Database):
        await db.create_user("charlie", "hash1")
        with pytest.raises(Exception):
            await db.create_user("charlie", "hash2")

    async def test_get_nonexistent(self, db: Database):
        assert await db.get_user_by_username("nobody") is None
        assert await db.get_user_by_id(9999) is None

    async def test_list_users(self, db: Database):
        await db.create_user("u1", "h1")
        await db.create_user("u2", "h2")
        users = await db.list_users()
        assert len(users) == 2


class TestAgentCRUD:
    async def test_create_and_get(self, db: Database):
        user = await db.create_user("alice", "hash")
        agent = await db.create_agent(
            user_id=user.id,
            name="My Agent",
            soul="You are helpful",
            config_path="/tmp/config.json",
            workspace_path="/tmp/workspace",
            gateway_port=19001,
            daily_delivery_enabled=True,
        )
        assert agent.id is not None
        assert agent.name == "My Agent"
        assert agent.status == AgentStatus.CREATING
        assert agent.daily_delivery_enabled is True

        found = await db.get_agent(agent.id)
        assert found is not None
        assert found.soul == "You are helpful"
        assert found.daily_delivery_enabled is True

    async def test_get_agents_by_user(self, db: Database):
        u1 = await db.create_user("alice", "h")
        u2 = await db.create_user("bob", "h")
        await db.create_agent(user_id=u1.id, name="A1")
        await db.create_agent(user_id=u1.id, name="A2")
        await db.create_agent(user_id=u2.id, name="B1")

        alice_agents = await db.get_agents_by_user(u1.id)
        assert len(alice_agents) == 2
        bob_agents = await db.get_agents_by_user(u2.id)
        assert len(bob_agents) == 1

    async def test_update_agent(self, db: Database):
        user = await db.create_user("alice", "h")
        agent = await db.create_agent(user_id=user.id, name="Old Name")
        updated = await db.update_agent(
            agent.id,
            name="New Name",
            status="running",
            daily_delivery_enabled=True,
        )
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.status == "running"
        assert updated.daily_delivery_enabled is True

    async def test_delete_agent(self, db: Database):
        user = await db.create_user("alice", "h")
        agent = await db.create_agent(user_id=user.id, name="To Delete")
        assert await db.delete_agent(agent.id) is True
        assert await db.get_agent(agent.id) is None

    async def test_delete_nonexistent(self, db: Database):
        assert await db.delete_agent(9999) is False

    async def test_get_agents_by_status(self, db: Database):
        user = await db.create_user("alice", "h")
        a1 = await db.create_agent(user_id=user.id, name="A1")
        await db.create_agent(user_id=user.id, name="A2")
        await db.update_agent(a1.id, status="running")
        running = await db.get_agents_by_status("running")
        assert len(running) == 1
        assert running[0].name == "A1"


class TestPortAllocation:
    async def test_allocate_first_port(self, db: Database):
        port = await db.allocate_port([19000, 19999])
        assert port == 19000

    async def test_allocate_skips_used(self, db: Database):
        user = await db.create_user("alice", "h")
        await db.create_agent(user_id=user.id, name="A", gateway_port=19000)
        await db.create_agent(user_id=user.id, name="B", gateway_port=19001)
        port = await db.allocate_port([19000, 19999])
        assert port == 19002

    async def test_allocate_exhausted(self, db: Database):
        user = await db.create_user("alice", "h")
        await db.create_agent(user_id=user.id, name="A", gateway_port=100)
        with pytest.raises(RuntimeError, match="No available ports"):
            await db.allocate_port([100, 100])


class TestWechatBinding:
    async def test_create_and_get(self, db: Database):
        user = await db.create_user("alice", "h")
        agent = await db.create_agent(user_id=user.id, name="A")
        binding = await db.create_wechat_binding(agent.id, "wx_user_123")
        assert binding.id is not None
        assert binding.wechat_user_id == "wx_user_123"

        bindings = await db.get_wechat_bindings_by_agent(agent.id)
        assert len(bindings) == 1
        assert bindings[0].wechat_user_id == "wx_user_123"
