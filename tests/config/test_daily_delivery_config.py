from nanobot.config.schema import DailyDeliveryConfig
from nanobot.cron.types import CronJob, CronPayload, CronSchedule
from nanobot.daily_delivery import (
    DAILY_DELIVERY_PLAN_MISSING_HASH,
    DAILY_DELIVERY_PLAN_PATH,
    DAILY_DELIVERY_STATE_PATH,
    hash_daily_delivery_plan,
    load_daily_delivery_state,
    resolve_daily_delivery_schedule,
    save_daily_delivery_state,
)


def _job(job_id: str, expr: str, *, kind: str = "agent_turn", enabled: bool = True) -> CronJob:
    return CronJob(
        id=job_id,
        name=job_id,
        enabled=enabled,
        schedule=CronSchedule(kind="cron", expr=expr, tz="Asia/Shanghai"),
        payload=CronPayload(kind=kind),
    )


def test_daily_delivery_config_defaults_to_disabled_daily_cron() -> None:
    cfg = DailyDeliveryConfig()

    assert cfg.enabled is False
    assert cfg.cron == "0 8 * * *"


def test_daily_delivery_plan_hash_and_runtime_state(tmp_path) -> None:
    assert hash_daily_delivery_plan(tmp_path) == DAILY_DELIVERY_PLAN_MISSING_HASH
    assert load_daily_delivery_state(tmp_path) == {"version": 1}

    plan_path = tmp_path / DAILY_DELIVERY_PLAN_PATH
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("today: ask how the user is doing\n", encoding="utf-8")
    plan_hash = hash_daily_delivery_plan(tmp_path)

    assert plan_hash.startswith("sha256:")

    save_daily_delivery_state(
        tmp_path,
        {
            "lastPlanHash": plan_hash,
            "lastStatus": "sent",
        },
    )

    assert (tmp_path / DAILY_DELIVERY_STATE_PATH).exists()
    assert load_daily_delivery_state(tmp_path)["lastPlanHash"] == plan_hash


def test_daily_delivery_builds_cron_schedule_with_timezone() -> None:
    cfg = DailyDeliveryConfig(cron="15 7 * * *")

    schedule = cfg.build_schedule("Asia/Shanghai")

    assert schedule.kind == "cron"
    assert schedule.expr == "15 7 * * *"
    assert schedule.tz == "Asia/Shanghai"


def test_daily_delivery_describe_schedule() -> None:
    cfg = DailyDeliveryConfig(cron="30 9 * * 1-5")

    assert cfg.describe_schedule() == "cron 30 9 * * 1-5"


def test_daily_delivery_auto_shifts_away_from_conflicting_user_job() -> None:
    schedule = CronSchedule(kind="cron", expr="0 8 * * *", tz="Asia/Shanghai")

    resolved, offset = resolve_daily_delivery_schedule(
        schedule,
        [_job("weather", "0 8 * * *")],
        now_ms=0,
    )

    assert resolved.expr == "10 8 * * *"
    assert offset == 10


def test_daily_delivery_auto_shift_skips_system_jobs() -> None:
    schedule = CronSchedule(kind="cron", expr="0 8 * * *", tz="Asia/Shanghai")

    resolved, offset = resolve_daily_delivery_schedule(
        schedule,
        [_job("dream", "0 8 * * *", kind="system_event")],
        now_ms=0,
    )

    assert resolved.expr == "0 8 * * *"
    assert offset == 0


def test_daily_delivery_auto_shift_finds_next_open_slot() -> None:
    schedule = CronSchedule(kind="cron", expr="0 8 * * *", tz="Asia/Shanghai")

    resolved, offset = resolve_daily_delivery_schedule(
        schedule,
        [
            _job("weather", "0 8 * * *"),
            _job("standup", "10 8 * * *"),
        ],
        now_ms=0,
    )

    assert resolved.expr == "20 8 * * *"
    assert offset == 20
