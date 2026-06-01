from nanobot.config.schema import DailyDeliveryConfig
from nanobot.cron.types import CronJob, CronPayload, CronSchedule
from nanobot.daily_delivery import resolve_daily_delivery_schedule


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
