"""Agent manager for multi-agent support."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.bus.queue import MessageBus
from nanobot.config.schema import AgentDefinition, Config

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.session.manager import SessionManager


class AgentInstance:
    """Container for a single agent's resources."""

    def __init__(
        self,
        name: str,
        bus: MessageBus,
        agent: AgentLoop,
        workspace: Path,
        definition: AgentDefinition,
    ):
        self.name = name
        self.bus = bus
        self.agent = agent
        self.workspace = workspace
        self.definition = definition


class AgentManager:
    """
    Manages multiple agent instances.

    Each agent has:
    - Independent MessageBus (isolated message routing)
    - Independent AgentLoop (own context, sessions, tools)
    - Independent workspace (memory, skills, sessions)
    - Channel binding (1:1 mapping)

    Usage:
        manager = AgentManager(config)
        manager.setup()  # Create all agents
        bus = manager.get_bus("telegram")  # Get bus for channel
        await manager.start_all()  # Start all agent loops
    """

    def __init__(self, config: Config):
        self.config = config
        self.instances: dict[str, AgentInstance] = {}
        self.channel_mapping: dict[str, str] = {}  # channel -> agent name
        self._default_agent_name: str = "default"

    def setup(self) -> None:
        """Create all agent instances based on configuration."""
        definitions = self.config.agents.definitions

        if not definitions:
            # No multi-agent definitions, create single default agent
            logger.info("No agent definitions found, using single-agent mode")
            self._create_default_agent()
            return

        logger.info("Setting up {} agent(s)", len(definitions))

        for defn in definitions:
            self._create_agent(defn)

        # Ensure we have a fallback for unmapped channels
        if self._default_agent_name not in self.instances:
            self._create_default_agent()

    def _create_default_agent(self) -> None:
        """Create the default agent using global defaults config."""
        defaults = self.config.agents.defaults
        workspace = Path(defaults.workspace).expanduser()

        # Create a synthetic definition for the default agent
        defn = AgentDefinition(
            name=self._default_agent_name,
            channels=[],
            workspace=str(workspace),
            model=defaults.model,
        )

        self._create_agent(defn, is_default=True)

    def _create_agent(self, defn: AgentDefinition, is_default: bool = False) -> None:
        """Create a single agent instance."""
        from nanobot.agent.loop import AgentLoop
        from nanobot.session.manager import SessionManager
        from nanobot.config.loader import get_data_dir
        from nanobot.cron.service import CronService

        # Determine workspace
        if defn.workspace:
            workspace = Path(defn.workspace).expanduser()
        else:
            workspace = Path.home() / ".nanobot" / "agents" / defn.name

        # Ensure workspace exists
        workspace.mkdir(parents=True, exist_ok=True)

        # Create MessageBus for this agent
        bus = MessageBus()

        # Create provider
        model = defn.model or self.config.agents.defaults.model
        provider = self._make_provider(model)

        # Create session manager
        session_manager = SessionManager(workspace)

        # Create cron service (each agent has its own cron)
        cron_store_path = get_data_dir() / "cron" / f"jobs_{defn.name}.json"
        cron = CronService(cron_store_path)

        # Create AgentLoop
        agent = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=workspace,
            model=model,
            temperature=self.config.agents.defaults.temperature,
            max_tokens=self.config.agents.defaults.max_tokens,
            max_iterations=self.config.agents.defaults.max_tool_iterations,
            memory_window=self.config.agents.defaults.memory_window,
            brave_api_key=self.config.tools.web.search.api_key or None,
            exec_config=self.config.tools.exec,
            cron_service=cron,
            restrict_to_workspace=self.config.tools.restrict_to_workspace,
            session_manager=session_manager,
            mcp_servers=self.config.tools.mcp_servers,
            channels_config=self.config.channels,
        )

        # Set up cron callback
        async def on_cron_job(job) -> str | None:
            """Execute a cron job through this agent."""
            response = await agent.process_direct(
                job.payload.message,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
            if job.payload.deliver and job.payload.to:
                from nanobot.bus.events import OutboundMessage
                await bus.publish_outbound(OutboundMessage(
                    channel=job.payload.channel or "cli",
                    chat_id=job.payload.to,
                    content=response or ""
                ))
            return response

        cron.on_job = on_cron_job

        # Store instance
        instance = AgentInstance(
            name=defn.name,
            bus=bus,
            agent=agent,
            workspace=workspace,
            definition=defn,
        )
        self.instances[defn.name] = instance

        # Record channel mappings
        for channel in defn.channels:
            self.channel_mapping[channel] = defn.name
            logger.info("Channel '{}' -> agent '{}'", channel, defn.name)

        if is_default:
            logger.info("Created default agent with workspace: {}", workspace)
        else:
            logger.info("Created agent '{}' with workspace: {}", defn.name, workspace)

    def _make_provider(self, model: str):
        """Create LLM provider for the given model."""
        from nanobot.providers.litellm_provider import LiteLLMProvider
        from nanobot.providers.openai_codex_provider import OpenAICodexProvider
        from nanobot.providers.custom_provider import CustomProvider

        provider_name = self.config.get_provider_name(model)
        p = self.config.get_provider(model)

        # OpenAI Codex (OAuth)
        if provider_name == "openai_codex" or model.startswith("openai-codex/"):
            return OpenAICodexProvider(default_model=model)

        # Custom: direct OpenAI-compatible endpoint
        if provider_name == "custom":
            return CustomProvider(
                api_key=p.api_key if p else "no-key",
                api_base=self.config.get_api_base(model) or "http://localhost:8000/v1",
                default_model=model,
            )

        from nanobot.providers.registry import find_by_name
        spec = find_by_name(provider_name)
        if not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and spec.is_oauth):
            raise ValueError(f"No API key configured for model: {model}")

        return LiteLLMProvider(
            api_key=p.api_key if p else None,
            api_base=self.config.get_api_base(model),
            default_model=model,
            extra_headers=p.extra_headers if p else None,
            provider_name=provider_name,
        )

    def get_bus(self, channel: str) -> MessageBus:
        """Get the MessageBus for the agent handling this channel."""
        agent_name = self.channel_mapping.get(channel, self._default_agent_name)
        instance = self.instances.get(agent_name)
        if instance:
            return instance.bus
        # Fallback to first available agent
        if self.instances:
            return next(iter(self.instances.values())).bus
        raise RuntimeError(f"No agent available for channel: {channel}")

    def get_agent(self, channel: str) -> AgentLoop | None:
        """Get the AgentLoop for the agent handling this channel."""
        agent_name = self.channel_mapping.get(channel, self._default_agent_name)
        instance = self.instances.get(agent_name)
        if instance:
            return instance.agent
        return None

    def get_agent_by_name(self, name: str) -> AgentLoop | None:
        """Get an agent by its name."""
        instance = self.instances.get(name)
        return instance.agent if instance else None

    def get_instance(self, channel: str) -> AgentInstance | None:
        """Get the AgentInstance for the agent handling this channel."""
        agent_name = self.channel_mapping.get(channel, self._default_agent_name)
        return self.instances.get(agent_name)

    async def start_all(self) -> None:
        """Start all agent loops."""
        tasks = []
        for name, instance in self.instances.items():
            logger.info("Starting agent '{}'", name)
            tasks.append(asyncio.create_task(instance.agent.run()))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Stop all agent loops."""
        logger.info("Stopping all agents...")
        for name, instance in self.instances.items():
            instance.agent.stop()
            await instance.agent.close_mcp()
            logger.info("Stopped agent '{}'", name)

    def get_status(self) -> dict[str, Any]:
        """Get status of all agents."""
        return {
            name: {
                "workspace": str(instance.workspace),
                "model": instance.agent.model,
                "channels": instance.definition.channels,
            }
            for name, instance in self.instances.items()
        }

    @property
    def has_multiple_agents(self) -> bool:
        """Check if multiple agents are configured."""
        return len(self.instances) > 1
