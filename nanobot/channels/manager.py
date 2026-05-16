"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Union

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import Config

if TYPE_CHECKING:
    from nanobot.agent.manager import AgentManager


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    - Start/stop channels
    - Route outbound messages

    Supports two modes:
    1. Single bus mode: All channels share one MessageBus (backward compatible)
    2. Agent manager mode: Each channel uses the bus of its assigned agent
    """

    def __init__(self, config: Config, bus_or_manager: Union[MessageBus, AgentManager]):
        self.config = config
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_tasks: list[asyncio.Task] = []

        # Determine mode
        if isinstance(bus_or_manager, MessageBus):
            # Single bus mode (backward compatible)
            self._single_bus = bus_or_manager
            self._agent_manager = None
            logger.info("ChannelManager: single-bus mode")
        else:
            # Agent manager mode (multi-agent)
            self._single_bus = None
            self._agent_manager = bus_or_manager
            logger.info("ChannelManager: multi-agent mode")

        self._init_channels()

    def _get_bus(self, channel_name: str) -> MessageBus:
        """Get the appropriate MessageBus for a channel."""
        if self._single_bus:
            return self._single_bus
        if self._agent_manager:
            return self._agent_manager.get_bus(channel_name)
        raise RuntimeError("No bus available")

    def _init_channels(self) -> None:
        """Initialize channels based on config."""

        # Telegram channel
        if self.config.channels.telegram.enabled:
            try:
                from nanobot.channels.telegram import TelegramChannel
                self.channels["telegram"] = TelegramChannel(
                    self.config.channels.telegram,
                    self._get_bus("telegram"),
                    groq_api_key=self.config.providers.groq.api_key,
                )
                logger.info("Telegram channel enabled")
            except ImportError as e:
                logger.warning("Telegram channel not available: {}", e)

        # WhatsApp channel
        if self.config.channels.whatsapp.enabled:
            try:
                from nanobot.channels.whatsapp import WhatsAppChannel
                self.channels["whatsapp"] = WhatsAppChannel(
                    self.config.channels.whatsapp, self._get_bus("whatsapp")
                )
                logger.info("WhatsApp channel enabled")
            except ImportError as e:
                logger.warning("WhatsApp channel not available: {}", e)

        # Discord channel
        if self.config.channels.discord.enabled:
            try:
                from nanobot.channels.discord import DiscordChannel
                self.channels["discord"] = DiscordChannel(
                    self.config.channels.discord, self._get_bus("discord")
                )
                logger.info("Discord channel enabled")
            except ImportError as e:
                logger.warning("Discord channel not available: {}", e)

        # Feishu channel
        if self.config.channels.feishu.enabled:
            try:
                from nanobot.channels.feishu import FeishuChannel
                self.channels["feishu"] = FeishuChannel(
                    self.config.channels.feishu, self._get_bus("feishu")
                )
                logger.info("Feishu channel enabled")
            except ImportError as e:
                logger.warning("Feishu channel not available: {}", e)

        # Mochat channel
        if self.config.channels.mochat.enabled:
            try:
                from nanobot.channels.mochat import MochatChannel

                self.channels["mochat"] = MochatChannel(
                    self.config.channels.mochat, self._get_bus("mochat")
                )
                logger.info("Mochat channel enabled")
            except ImportError as e:
                logger.warning("Mochat channel not available: {}", e)

        # DingTalk channel
        if self.config.channels.dingtalk.enabled:
            try:
                from nanobot.channels.dingtalk import DingTalkChannel
                self.channels["dingtalk"] = DingTalkChannel(
                    self.config.channels.dingtalk, self._get_bus("dingtalk")
                )
                logger.info("DingTalk channel enabled")
            except ImportError as e:
                logger.warning("DingTalk channel not available: {}", e)

        # Email channel
        if self.config.channels.email.enabled:
            try:
                from nanobot.channels.email import EmailChannel
                self.channels["email"] = EmailChannel(
                    self.config.channels.email, self._get_bus("email")
                )
                logger.info("Email channel enabled")
            except ImportError as e:
                logger.warning("Email channel not available: {}", e)

        # Slack channel
        if self.config.channels.slack.enabled:
            try:
                from nanobot.channels.slack import SlackChannel
                self.channels["slack"] = SlackChannel(
                    self.config.channels.slack, self._get_bus("slack")
                )
                logger.info("Slack channel enabled")
            except ImportError as e:
                logger.warning("Slack channel not available: {}", e)

        # QQ channel
        if self.config.channels.qq.enabled:
            try:
                from nanobot.channels.qq import QQChannel
                self.channels["qq"] = QQChannel(
                    self.config.channels.qq,
                    self._get_bus("qq"),
                )
                logger.info("QQ channel enabled")
            except ImportError as e:
                logger.warning("QQ channel not available: {}", e)

        # Web channel
        if self.config.channels.web.enabled:
            try:
                from nanobot.channels.web import WebChannel
                self.channels["web"] = WebChannel(
                    self.config.channels.web,
                    self._get_bus("web"),
                )
                logger.info("Web channel enabled")
            except ImportError as e:
                logger.warning("Web channel not available: {}", e)

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """Start a channel and log any exceptions."""
        try:
            await channel.start()
        except Exception as e:
            logger.error("Failed to start channel {}: {}", name, e)

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher(s)."""
        if not self.channels:
            logger.warning("No channels enabled")
            return

        # Start outbound dispatcher(s)
        if self._single_bus:
            # Single bus mode: one dispatcher
            self._dispatch_tasks.append(asyncio.create_task(self._dispatch_outbound(self._single_bus)))
        elif self._agent_manager:
            # Multi-agent mode: one dispatcher per agent
            for name, instance in self._agent_manager.instances.items():
                self._dispatch_tasks.append(
                    asyncio.create_task(self._dispatch_outbound(instance.bus))
                )

        # Start channels
        tasks = []
        for name, channel in self.channels.items():
            logger.info("Starting {} channel...", name)
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher(s)."""
        logger.info("Stopping all channels...")

        # Stop dispatchers
        for task in self._dispatch_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._dispatch_tasks.clear()

        # Stop all channels
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info("Stopped {} channel", name)
            except Exception as e:
                logger.error("Error stopping {}: {}", name, e)

    async def _dispatch_outbound(self, bus: MessageBus) -> None:
        """Dispatch outbound messages from a specific bus to the appropriate channel."""
        logger.info("Outbound dispatcher started for bus")

        while True:
            try:
                msg = await asyncio.wait_for(
                    bus.consume_outbound(),
                    timeout=1.0
                )

                if msg.metadata.get("_progress"):
                    if msg.metadata.get("_tool_hint") and not self.config.channels.send_tool_hints:
                        continue
                    if not msg.metadata.get("_tool_hint") and not self.config.channels.send_progress:
                        continue

                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error("Error sending to {}: {}", msg.channel, e)
                else:
                    logger.warning("Unknown channel: {}", msg.channel)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)

    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        return {
            name: {
                "enabled": True,
                "running": channel.is_running
            }
            for name, channel in self.channels.items()
        }

    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.channels.keys())
