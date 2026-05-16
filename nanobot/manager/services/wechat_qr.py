"""WeChat QR code binding service using the ilinkai HTTP API."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from nanobot.channels.weixin import (
    ILINK_APP_CLIENT_VERSION,
    ILINK_APP_ID,
    MAX_QR_REFRESH_COUNT,
)
from nanobot.manager.models import QRCodeStatus

if TYPE_CHECKING:
    from nanobot.manager.database import Database


class WechatQRService:
    """Manage WeChat QR code generation and scan-status polling."""

    def __init__(self, base_url: str = "https://ilinkai.weixin.qq.com"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)
        self._poll_tasks: dict[int, asyncio.Task] = {}

    async def close(self) -> None:
        for task in self._poll_tasks.values():
            task.cancel()
        await self._client.aclose()

    @staticmethod
    def _get_pm():
        from nanobot.manager.app import get_process_manager
        return get_process_manager()

    # -- HTTP helpers (mirrors WeixinChannel) --

    @staticmethod
    def _random_wechat_uin() -> str:
        uint32 = int.from_bytes(os.urandom(4), "big")
        return base64.b64encode(str(uint32).encode()).decode()

    def _make_headers(self) -> dict[str, str]:
        return {
            "X-WECHAT-UIN": self._random_wechat_uin(),
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        }

    async def _api_get(self, url: str, params: dict | None = None) -> dict:
        resp = await self._client.get(url, params=params, headers=self._make_headers())
        resp.raise_for_status()
        return resp.json()

    # -- Public API --

    async def fetch_qr_code(self) -> tuple[str, str]:
        """Fetch a fresh QR code from ilinkai. Returns (qrcode_id, scan_url)."""
        url = f"{self.base_url}/ilink/bot/get_bot_qrcode"
        data = await self._api_get(url, params={"bot_type": "3"})
        qrcode_img_content = data.get("qrcode_img_content", "")
        qrcode_id = data.get("qrcode", "")
        if not qrcode_id:
            raise RuntimeError(f"Failed to get QR code: {data}")
        return qrcode_id, (qrcode_img_content or qrcode_id)

    async def poll_qr_status(self, qrcode_id: str, poll_base_url: str | None = None) -> dict:
        """Poll QR code scan status once. Returns raw status dict."""
        base = poll_base_url or self.base_url
        url = f"{base}/ilink/bot/get_qrcode_status"
        data = await self._api_get(url, params={"qrcode": qrcode_id})
        return data if isinstance(data, dict) else {}

    async def start_qr_polling(self, agent_id: int, db: Database) -> None:
        """Background task: poll QR status until confirmed or expired."""
        try:
            await self._poll_loop(agent_id, db)
        finally:
            self._poll_tasks.pop(agent_id, None)

    async def _poll_loop(self, agent_id: int, db: Database) -> None:
        agent = await db.get_agent(agent_id)
        if not agent or not agent.qr_code_id:
            return

        poll_base_url = self.base_url
        refresh_count = 0

        while True:
            try:
                status_data = await self.poll_qr_status(agent.qr_code_id, poll_base_url)
            except (httpx.TimeoutException, httpx.TransportError):
                await asyncio.sleep(2)
                continue
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    await asyncio.sleep(2)
                    continue
                logger.error("QR poll HTTP error for agent {}: {}", agent_id, e)
                break

            qr_status = status_data.get("status", "")

            if qr_status == QRCodeStatus.CONFIRMED:
                token = status_data.get("bot_token", "")
                bot_id = status_data.get("ilink_bot_id", "")
                user_id = status_data.get("ilink_user_id", "")
                new_base = status_data.get("baseurl", "")

                if not token:
                    logger.error("QR confirmed but no bot_token for agent {}", agent_id)
                    break

                updates = {
                    "qr_code_status": QRCodeStatus.CONFIRMED,
                    "wechat_bot_id": bot_id,
                    "wechat_bot_token": token,
                    "wechat_bound": True,
                }
                await db.update_agent(agent_id, **updates)

                weixin_dir = Path(agent.workspace_path) / "weixin"
                weixin_dir.mkdir(parents=True, exist_ok=True)
                state = {
                    "token": token,
                    "ilink_bot_id": bot_id,
                    "ilink_user_id": user_id,
                    "base_url": new_base or self.base_url,
                }
                (weixin_dir / "account.json").write_text(
                    json.dumps(state, ensure_ascii=False), encoding="utf-8"
                )

                if user_id:
                    await db.create_wechat_binding(agent_id, user_id)

                # Update agent config.json to enable weixin channel
                agent = await db.get_agent(agent_id)
                from nanobot.manager.services.config_builder import update_agent_weixin_config
                update_agent_weixin_config(agent)

                # Restart gateway so the weixin channel activates
                if agent.pid:
                    pm = self._get_pm()
                    await pm.restart_agent(agent, db)

                logger.info("Agent {} WeChat bound: bot_id={}, user_id={}", agent_id, bot_id, user_id)
                break

            elif qr_status == QRCodeStatus.SCAN_REDIRECT:
                redirect_host = str(status_data.get("redirect_host", "") or "").strip()
                if redirect_host:
                    if not redirect_host.startswith("http"):
                        redirect_host = f"https://{redirect_host}"
                    poll_base_url = redirect_host

            elif qr_status == QRCodeStatus.EXPIRED:
                refresh_count += 1
                if refresh_count > MAX_QR_REFRESH_COUNT:
                    await db.update_agent(agent_id, qr_code_status=QRCodeStatus.EXPIRED)
                    break
                try:
                    new_id, new_url = await self.fetch_qr_code()
                    await db.update_agent(
                        agent_id,
                        qr_code_id=new_id,
                        qr_code_url=new_url,
                        qr_code_status=QRCodeStatus.PENDING,
                    )
                    agent.qr_code_id = new_id
                    poll_base_url = self.base_url
                except Exception:
                    logger.exception("QR refresh failed for agent {}", agent_id)
                    break

            await asyncio.sleep(2)

    def spawn_poll_task(self, agent_id: int, db: Database) -> None:
        """Start a background polling task for an agent's QR code."""
        if agent_id in self._poll_tasks:
            self._poll_tasks[agent_id].cancel()
        self._poll_tasks[agent_id] = asyncio.create_task(self.start_qr_polling(agent_id, db))
