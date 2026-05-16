"""Agent worker process lifecycle management."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from nanobot.manager.models import AgentStatus

if TYPE_CHECKING:
    from nanobot.manager.database import Database
    from nanobot.manager.models import Agent


class AgentProcessManager:
    """Start, stop, and monitor agent worker subprocesses."""

    async def start_agent(self, agent: Agent, db: Database) -> Agent | None:
        """Start a nanobot gateway subprocess for the given agent."""
        if not os.path.isfile(agent.config_path):
            logger.error("Agent config not found: {}", agent.config_path)
            return await db.update_agent(agent.id, status=AgentStatus.ERROR)

        try:
            log_dir = Path(agent.workspace_path) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = open(log_dir / "gateway.log", "a", encoding="utf-8")

            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "nanobot", "gateway",
                "--config", agent.config_path,
                cwd=agent.workspace_path,
                stdout=log_file,
                stderr=log_file,
            )
            updated = await db.update_agent(agent.id, pid=process.pid, status=AgentStatus.RUNNING)
            logger.info("Agent {} started (pid={})", agent.name, process.pid)
            return updated
        except Exception:
            logger.exception("Failed to start agent {}", agent.name)
            return await db.update_agent(agent.id, status=AgentStatus.ERROR)

    async def stop_agent(self, agent: Agent, db: Database) -> Agent | None:
        """Stop an agent worker process gracefully."""
        if not agent.pid:
            return await db.update_agent(agent.id, status=AgentStatus.STOPPED)

        try:
            os.kill(agent.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        # Wait up to 10s for graceful shutdown
        for _ in range(10):
            if not self._is_alive(agent.pid):
                break
            await asyncio.sleep(1)
        else:
            try:
                os.kill(agent.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        updated = await db.update_agent(agent.id, pid=None, status=AgentStatus.STOPPED)
        logger.info("Agent {} stopped", agent.name)
        return updated

    async def restart_agent(self, agent: Agent, db: Database) -> Agent | None:
        """Stop and start an agent, used after config changes."""
        await self.stop_agent(agent, db)
        agent = await db.get_agent(agent.id)
        return await self.start_agent(agent, db)

    def check_health(self, agent: Agent) -> bool:
        """Check if an agent process is alive."""
        return agent.pid is not None and self._is_alive(agent.pid)

    async def monitor_loop(self, db: Database) -> None:
        """Background task: detect crashed agents every 30s."""
        while True:
            try:
                running = await db.get_agents_by_status(AgentStatus.RUNNING)
                for agent in running:
                    if agent.pid and not self._is_alive(agent.pid):
                        logger.warning("Agent {} (pid={}) died unexpectedly", agent.name, agent.pid)
                        await db.update_agent(agent.id, status=AgentStatus.ERROR, pid=None)
            except Exception:
                logger.exception("Health monitor error")
            await asyncio.sleep(30)

    @staticmethod
    def _is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
