"""SQLite database layer for the agent manager."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger

from nanobot.manager.models import Agent, User, WechatBinding

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    soul TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'creating',
    config_path TEXT NOT NULL DEFAULT '',
    workspace_path TEXT NOT NULL DEFAULT '',
    gateway_port INTEGER NOT NULL DEFAULT 0,
    pid INTEGER,
    wechat_bound INTEGER NOT NULL DEFAULT 0,
    qr_code_id TEXT DEFAULT '',
    qr_code_url TEXT DEFAULT '',
    qr_code_status TEXT DEFAULT '',
    wechat_bot_id TEXT DEFAULT '',
    wechat_bot_token TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wechat_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    wechat_user_id TEXT NOT NULL,
    bound_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """Async SQLite database for the agent manager."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open connection and create tables if needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("Manager database initialized at {}", self.db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not initialized. Call init() first."
        return self._db

    # -- User CRUD --

    async def create_user(self, username: str, password_hash: str) -> User:
        cursor = await self.db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        await self.db.commit()
        return User(id=cursor.lastrowid, username=username, password_hash=password_hash)

    async def get_user_by_username(self, username: str) -> User | None:
        cursor = await self.db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    async def get_user_by_id(self, user_id: int) -> User | None:
        cursor = await self.db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    async def list_users(self) -> list[User]:
        cursor = await self.db.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [self._row_to_user(row) for row in rows]

    async def get_user_agent_counts(self) -> list[dict]:
        cursor = await self.db.execute(
            "SELECT u.id, u.username, u.created_at, COUNT(a.id) AS agent_count "
            "FROM users u LEFT JOIN agents a ON a.user_id = u.id "
            "GROUP BY u.id ORDER BY u.created_at DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]

    # -- Agent CRUD --

    async def create_agent(
        self,
        user_id: int,
        name: str,
        soul: str = "",
        config_path: str = "",
        workspace_path: str = "",
        gateway_port: int = 0,
    ) -> Agent:
        cursor = await self.db.execute(
            "INSERT INTO agents (user_id, name, soul, config_path, workspace_path, gateway_port) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, soul, config_path, workspace_path, gateway_port),
        )
        await self.db.commit()
        return Agent(
            id=cursor.lastrowid,
            user_id=user_id,
            name=name,
            soul=soul,
            config_path=config_path,
            workspace_path=workspace_path,
            gateway_port=gateway_port,
        )

    async def get_agent(self, agent_id: int) -> Agent | None:
        cursor = await self.db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = await cursor.fetchone()
        return self._row_to_agent(row) if row else None

    async def get_agents_by_user(self, user_id: int) -> list[Agent]:
        cursor = await self.db.execute(
            "SELECT * FROM agents WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_agent(row) for row in rows]

    async def get_agents_by_status(self, status: str) -> list[Agent]:
        cursor = await self.db.execute("SELECT * FROM agents WHERE status = ?", (status,))
        rows = await cursor.fetchall()
        return [self._row_to_agent(row) for row in rows]

    async def list_all_agents(self) -> list[Agent]:
        cursor = await self.db.execute("SELECT * FROM agents ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [self._row_to_agent(row) for row in rows]

    async def update_agent(self, agent_id: int, **fields: Any) -> Agent | None:
        if not fields:
            return await self.get_agent(agent_id)
        fields["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [agent_id]
        await self.db.execute(f"UPDATE agents SET {set_clause} WHERE id = ?", values)
        await self.db.commit()
        return await self.get_agent(agent_id)

    async def delete_agent(self, agent_id: int) -> bool:
        cursor = await self.db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        await self.db.commit()
        return cursor.rowcount > 0

    async def allocate_port(self, port_range: list[int]) -> int:
        """Find the next available port in the given range."""
        low, high = port_range[0], port_range[1]
        cursor = await self.db.execute("SELECT gateway_port FROM agents WHERE gateway_port > 0")
        rows = await cursor.fetchall()
        used = {row["gateway_port"] for row in rows}
        for port in range(low, high + 1):
            if port not in used:
                return port
        raise RuntimeError(f"No available ports in range {low}-{high}")

    # -- Wechat Binding CRUD --

    async def create_wechat_binding(self, agent_id: int, wechat_user_id: str) -> WechatBinding:
        cursor = await self.db.execute(
            "INSERT INTO wechat_bindings (agent_id, wechat_user_id) VALUES (?, ?)",
            (agent_id, wechat_user_id),
        )
        await self.db.commit()
        return WechatBinding(id=cursor.lastrowid, agent_id=agent_id, wechat_user_id=wechat_user_id)

    async def get_wechat_bindings_by_agent(self, agent_id: int) -> list[WechatBinding]:
        cursor = await self.db.execute(
            "SELECT * FROM wechat_bindings WHERE agent_id = ?",
            (agent_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_binding(row) for row in rows]

    # -- Helpers --

    @staticmethod
    def _row_to_user(row: aiosqlite.Row) -> User:
        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_agent(row: aiosqlite.Row) -> Agent:
        return Agent(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            soul=row["soul"],
            status=row["status"],
            config_path=row["config_path"],
            workspace_path=row["workspace_path"],
            gateway_port=row["gateway_port"],
            pid=row["pid"],
            wechat_bound=bool(row["wechat_bound"]),
            qr_code_id=row["qr_code_id"],
            qr_code_url=row["qr_code_url"],
            qr_code_status=row["qr_code_status"],
            wechat_bot_id=row["wechat_bot_id"],
            wechat_bot_token=row["wechat_bot_token"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_binding(row: aiosqlite.Row) -> WechatBinding:
        return WechatBinding(
            id=row["id"],
            agent_id=row["agent_id"],
            wechat_user_id=row["wechat_user_id"],
            bound_at=row["bound_at"],
        )
