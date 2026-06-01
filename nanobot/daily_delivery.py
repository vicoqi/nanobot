"""Shared constants for Dream-managed daily channel delivery."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from nanobot.cron.service import _compute_next_run
from nanobot.cron.types import CronJob, CronSchedule


DAILY_DELIVERY_SKILL_NAME = "daily-channel-delivery"
DAILY_DELIVERY_DIR = Path("skills") / DAILY_DELIVERY_SKILL_NAME
DAILY_DELIVERY_SKILL_PATH = DAILY_DELIVERY_DIR / "SKILL.md"
DAILY_DELIVERY_PLAN_PATH = DAILY_DELIVERY_DIR / "PLAN.md"

DAILY_DELIVERY_JOB_ID = "daily-delivery"
DAILY_DELIVERY_JOB_NAME = "daily-delivery"

DAILY_DELIVERY_SUPPRESS_RESPONSE = "All clear."
DAILY_DELIVERY_AUTO_SHIFT_STEP_MINUTES = 10
DAILY_DELIVERY_AUTO_SHIFT_MAX_MINUTES = 180
DAILY_DELIVERY_CONFLICT_LOOKAHEAD = 30


def _shift_fixed_clock_cron(expr: str, offset_minutes: int) -> str | None:
    """Shift a fixed minute/hour cron expression within the same day."""
    parts = expr.split()
    if len(parts) != 5 or not parts[0].isdigit() or not parts[1].isdigit():
        return None

    minute = int(parts[0])
    hour = int(parts[1])
    total_minutes = hour * 60 + minute + offset_minutes
    if total_minutes >= 24 * 60:
        return None

    new_hour, new_minute = divmod(total_minutes, 60)
    parts[0] = str(new_minute)
    parts[1] = str(new_hour)
    return " ".join(parts)


def _next_occurrences(schedule: CronSchedule, *, start_ms: int, limit: int) -> list[int]:
    """Return the next ``limit`` run timestamps for a schedule."""
    occurrences: list[int] = []
    cursor = start_ms
    for _ in range(limit):
        next_run = _compute_next_run(schedule, cursor)
        if next_run is None:
            break
        occurrences.append(next_run)
        cursor = next_run if schedule.kind == "every" else next_run + 1
    return occurrences


def _jobs_that_can_conflict(existing_jobs: Iterable[CronJob]) -> list[CronJob]:
    """Keep only enabled non-system jobs that share the scheduler surface."""
    return [
        job
        for job in existing_jobs
        if job.enabled
        and job.id != DAILY_DELIVERY_JOB_ID
        and job.payload.kind != "system_event"
    ]


def resolve_daily_delivery_schedule(
    base_schedule: CronSchedule,
    existing_jobs: Iterable[CronJob],
    *,
    now_ms: int,
) -> tuple[CronSchedule, int]:
    """Auto-shift fixed-time daily-delivery cron schedules away from conflicts.

    Returns the chosen schedule plus the applied positive minute offset.
    """
    if base_schedule.kind != "cron" or not base_schedule.expr:
        return base_schedule, 0

    jobs = _jobs_that_can_conflict(existing_jobs)
    if not jobs:
        return base_schedule, 0

    for offset_minutes in range(
        0,
        DAILY_DELIVERY_AUTO_SHIFT_MAX_MINUTES + DAILY_DELIVERY_AUTO_SHIFT_STEP_MINUTES,
        DAILY_DELIVERY_AUTO_SHIFT_STEP_MINUTES,
    ):
        shifted_expr = (
            base_schedule.expr
            if offset_minutes == 0
            else _shift_fixed_clock_cron(base_schedule.expr, offset_minutes)
        )
        if shifted_expr is None:
            break

        candidate = CronSchedule(
            kind="cron",
            expr=shifted_expr,
            tz=base_schedule.tz,
        )
        candidate_runs = set(
            _next_occurrences(
                candidate,
                start_ms=now_ms,
                limit=DAILY_DELIVERY_CONFLICT_LOOKAHEAD,
            )
        )
        if not candidate_runs:
            return candidate, offset_minutes

        if all(
            candidate_runs.isdisjoint(
                _next_occurrences(
                    job.schedule,
                    start_ms=now_ms,
                    limit=DAILY_DELIVERY_CONFLICT_LOOKAHEAD,
                )
            )
            for job in jobs
        ):
            return candidate, offset_minutes

    return base_schedule, 0
