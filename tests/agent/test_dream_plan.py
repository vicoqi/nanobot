"""Tests for the DreamPlan class — plan-only proactive delivery maintenance."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.memory import DreamPlan, MemoryStore
from nanobot.agent.runner import AgentRunResult
from nanobot.daily_delivery import DAILY_DELIVERY_PLAN_PATH
from nanobot.utils.helpers import sync_workspace_templates


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(tmp_path)
    s.write_user("# User\n- Likes concise updates")
    s.write_memory("# Memory\n- User follows markets")
    sync_workspace_templates(tmp_path, silent=True)
    return s


@pytest.fixture
def mock_provider():
    p = MagicMock()
    p.chat_with_retry = AsyncMock()
    return p


@pytest.fixture
def mock_runner():
    return MagicMock()


@pytest.fixture
def dream_plan(store, mock_provider, mock_runner):
    d = DreamPlan(store=store, provider=mock_provider, model="test-model", max_batch_size=5)
    d._runner = mock_runner
    return d


def _make_run_result(
    stop_reason="completed",
    final_content=None,
    tool_events=None,
    usage=None,
):
    return AgentRunResult(
        final_content=final_content or stop_reason,
        stop_reason=stop_reason,
        messages=[],
        tools_used=[],
        usage=usage or {},
        tool_events=tool_events or [],
    )


def _strict_today_plan(date: str) -> str:
    return (
        "---\n"
        f'last_daily_reviewed_on: "{date}"\n'
        "status: active\n"
        "---\n\n"
        "# Daily Intent Layer\n\n"
        "## Today Delivery Intent\n\n"
        f'- date: "{date}"\n'
        "- status: ready\n"
        "- delivery_type: action_offer\n"
        "- topic: market follow-up\n"
        "- why_today: user recently discussed markets\n"
        "- signal_source: memory\n"
        "- audience: weixin user\n"
        "- tone: concise\n"
        "- message_goal: offer one useful next step\n"
        "- hook: market structure may be worth tracking\n"
        "- reply_question: 要不要我帮你看一下ETF放量？\n"
        "- fetch_policy: use available market skills if needed\n"
        "- output_contract: 1-3 concise sentences ending with one concrete question\n"
    )


class TestDreamPlanRun:
    async def test_noop_when_no_unprocessed_history(self, dream_plan, mock_provider, mock_runner):
        today = datetime.now().strftime("%Y-%m-%d")
        plan_path = dream_plan.store.workspace / DAILY_DELIVERY_PLAN_PATH
        plan_path.write_text(
            _strict_today_plan(today),
            encoding="utf-8",
        )

        result = await dream_plan.run(default_since_cursor=0)
        assert result is False
        mock_provider.chat_with_retry.assert_not_called()
        mock_runner.run.assert_not_called()

    async def test_same_day_invalid_today_intent_schema_refreshes(
        self, dream_plan, mock_provider, mock_runner, store,
    ):
        today = datetime.now().strftime("%Y-%m-%d")
        plan_path = store.workspace / DAILY_DELIVERY_PLAN_PATH
        plan_path.write_text(
            "---\n"
            f'last_daily_reviewed_on: "{today}"\n'
            "status: active\n"
            "---\n\n"
            "# Daily Intent Layer\n\n"
            "## Today Delivery Intent\n\n"
            "- type: action_offer\n"
            "- intent: ask whether to monitor ETF volume\n",
            encoding="utf-8",
        )
        mock_provider.chat_with_retry.return_value = MagicMock(
            content="[PLAN] rewrite today's intent using strict V2 keys",
        )
        mock_runner.run = AsyncMock(return_value=_make_run_result())

        result = await dream_plan.run(default_since_cursor=0)

        assert result is True
        mock_provider.chat_with_retry.assert_called_once()
        user_msg = mock_provider.chat_with_retry.call_args.kwargs["messages"][1]["content"]
        assert "## Review Mode\ndaily_refresh" in user_msg

    async def test_daily_refresh_without_unprocessed_history_when_plan_is_stale(
        self, dream_plan, mock_provider, mock_runner, store,
    ):
        plan_path = store.workspace / DAILY_DELIVERY_PLAN_PATH
        plan_path.write_text(
            '---\nlast_daily_reviewed_on: "2000-01-01"\n'
            "status: active\n---\n\n# Daily Intent Layer\n",
            encoding="utf-8",
        )
        mock_provider.chat_with_retry.return_value = MagicMock(
            content="[PLAN] refresh today's intent with a cautious market follow-up",
        )
        mock_runner.run = AsyncMock(return_value=_make_run_result(
            tool_events=[{"name": "edit_file", "status": "ok", "detail": "updated"}],
        ))

        result = await dream_plan.run(default_since_cursor=0)

        assert result is True
        mock_provider.chat_with_retry.assert_called_once()
        mock_runner.run.assert_called_once()
        assert store.get_last_dream_plan_cursor() == 0
        user_msg = mock_provider.chat_with_retry.call_args.kwargs["messages"][1]["content"]
        assert "## Review Mode\ndaily_refresh" in user_msg
        assert "no new archived history since cursor 0" in user_msg

    async def test_advances_dream_plan_cursor(self, dream_plan, mock_provider, mock_runner, store):
        store.append_history("User often wants a concise market opener.")
        store.append_history("A brief morning market check-in would help.")
        mock_provider.chat_with_retry.return_value = MagicMock(
            content="[PLAN] market opener remains the best proactive topic",
        )
        mock_runner.run = AsyncMock(return_value=_make_run_result())

        await dream_plan.run(default_since_cursor=0)

        assert store.get_last_dream_plan_cursor() == 2

    async def test_failed_first_run_keeps_seed_cursor_for_retry(
        self, dream_plan, mock_provider, mock_runner, store,
    ):
        store.append_history("old entry")
        store.set_last_dream_cursor(1)
        store.append_history("new plan-worthy entry")
        mock_provider.chat_with_retry.return_value = MagicMock(
            content="[PLAN] propose a contextual check-in about the user's trading day",
        )
        mock_runner.run = AsyncMock(return_value=_make_run_result(stop_reason="max_iterations"))

        await dream_plan.run(default_since_cursor=1)

        assert store.has_last_dream_plan_cursor() is True
        assert store.get_last_dream_plan_cursor() == 1

        mock_runner.run = AsyncMock(return_value=_make_run_result())
        await dream_plan.run()

        assert store.get_last_dream_plan_cursor() == 2

    async def test_phase1_prompt_includes_current_plan_context(
        self, dream_plan, mock_provider, mock_runner, store,
    ):
        plan_path = store.workspace / DAILY_DELIVERY_PLAN_PATH
        plan_path.write_text(
            "---\nstatus: active\nconfidence: low\n---\n\n# Dream Managed State\n\n## Active Delivery\n- id: market-open\n",
            encoding="utf-8",
        )
        store.append_history("User is still focused on market context before trading.")
        mock_provider.chat_with_retry.return_value = MagicMock(
            content="[PLAN] keep market-open active but cautious",
        )
        mock_runner.run = AsyncMock(return_value=_make_run_result())

        await dream_plan.run(default_since_cursor=0)

        user_msg = mock_provider.chat_with_retry.call_args.kwargs["messages"][1]["content"]
        assert f"## Current {DAILY_DELIVERY_PLAN_PATH}" in user_msg
        assert "status: active" in user_msg

    async def test_phase1_prompt_encourages_candidate_checkins_and_help(
        self, dream_plan, mock_provider, mock_runner, store,
    ):
        store.append_history("Maybe you can occasionally remind me about my main priorities.")
        mock_provider.chat_with_retry.return_value = MagicMock(content="[SKIP]")
        mock_runner.run = AsyncMock(return_value=_make_run_result())

        await dream_plan.run(default_since_cursor=0)

        system_msg = mock_provider.chat_with_retry.call_args.kwargs["messages"][0]["content"]
        assert "contextual check-in" in system_msg
        assert "offer of help" in system_msg
        assert "exact V2 keys" in system_msg
        assert "`delivery_type`" in system_msg
        assert "Do not use aliases" in system_msg
        assert "candidate backup" in system_msg
        assert "Do not output [FILE], [FILE-REMOVE], or [SKILL] lines." in system_msg

    async def test_tools_cannot_modify_daily_delivery_skill_file(self, dream_plan, store):
        edit_tool = dream_plan._tools.get("edit_file")
        write_tool = dream_plan._tools.get("write_file")
        assert edit_tool is not None
        assert write_tool is not None

        edit_result = await edit_tool.execute(
            path="skills/daily-channel-delivery/SKILL.md",
            old_text="Daily Channel Delivery",
            new_text="Changed",
        )
        write_result = await write_tool.execute(
            path="skills/daily-channel-delivery/SKILL.md",
            content="changed",
        )

        assert "outside allowed directory" in edit_result
        assert "outside allowed directory" in write_result
        assert "Daily Channel Delivery" in (
            store.workspace / "skills" / "daily-channel-delivery" / "SKILL.md"
        ).read_text(encoding="utf-8")
