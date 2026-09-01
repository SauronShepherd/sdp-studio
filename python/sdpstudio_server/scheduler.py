from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    for item in field.split(","):
        if item.isdigit() and int(item) == value:
            return True
        if "-" in item:
            try:
                start, end = (int(part) for part in item.split("-", 1))
            except ValueError:
                continue
            if start <= value <= end:
                return True
    return False


def schedule_matches(cron: str, moment: datetime) -> bool:
    fields = cron.split()
    if len(fields) != 5:
        return False
    minute, hour, day, month, weekday = fields
    return all(
        (
            _matches(minute, moment.minute),
            _matches(hour, moment.hour),
            _matches(day, moment.day),
            _matches(month, moment.month),
            _matches(weekday, (moment.weekday() + 1) % 7),
        )
    )


def _missed_since(cron: str, last_marker: str | None, moment: datetime) -> bool:
    """Return whether a run-once schedule fired between its claim and startup."""
    if not last_marker:
        return False
    try:
        previous = datetime.strptime(last_marker, "%Y-%m-%dT%H:%M").replace(tzinfo=moment.tzinfo)
    except ValueError:
        return False
    cursor = previous + timedelta(minutes=1)
    current = moment.replace(second=0, microsecond=0)
    # A bounded scan prevents malformed/stale markers from causing unbounded work.
    for _ in range(366 * 24 * 60):
        if cursor > current:
            return False
        if schedule_matches(cron, cursor):
            return True
        cursor += timedelta(minutes=1)
    return False


def next_fire(cron: str, after: datetime, timezone: str = "UTC") -> datetime | None:
    """Return the next matching minute in an IANA timezone."""
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone {timezone!r}") from exc
    current = after.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        if schedule_matches(cron, current):
            return current
        current += timedelta(minutes=1)
    return None


class ScheduleWorker:
    """In-process local scheduler; it runs only for the lifetime of the server."""

    def __init__(
        self,
        list_schedules: Callable[[], list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]],
        dispatch: Callable[[dict[str, Any]], Awaitable[None]],
        interval_seconds: float = 30.0,
        claim: Callable[[str, str], bool | Awaitable[bool]] | None = None,
    ) -> None:
        self.list_schedules = list_schedules
        self.dispatch = dispatch
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._last_minute: str | None = None
        self._running: set[str] = set()
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self.claim = claim

    async def tick(self, moment: datetime) -> int:
        marker = moment.strftime("%Y-%m-%dT%H:%M")
        if marker == self._last_minute:
            return 0
        starting = self._last_minute is None
        self._last_minute = marker
        count = 0
        schedules = self.list_schedules()
        if inspect.isawaitable(schedules):
            schedules = await schedules
        for schedule in schedules:
            cron = str(schedule.get("cron", ""))
            due = schedule_matches(cron, moment)
            if (
                not due
                and starting
                and str(schedule.get("missed_run_policy", "skip")) == "run_once"
            ):
                due = _missed_since(cron, schedule.get("last_claim_marker"), moment)
            if schedule.get("enabled") and due:
                schedule_id = str(schedule.get("id", ""))
                if self.claim is not None:
                    claimed = self.claim(schedule_id, marker)
                    if inspect.isawaitable(claimed):
                        claimed = await claimed
                    if not claimed:
                        continue
                if schedule_id in self._running:
                    policy = str(schedule.get("concurrency_policy", "skip"))
                    if policy in {"skip", "forbid"}:
                        continue
                    if policy == "replace":
                        task = self._running_tasks.get(schedule_id)
                        if task is not None:
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                self._running.add(schedule_id)
                task = asyncio.ensure_future(self.dispatch(schedule))
                self._running_tasks[schedule_id] = task

                def on_done(completed: asyncio.Future[None], sid: str = schedule_id) -> None:
                    self._dispatch_finished(sid, completed)

                task.add_done_callback(on_done)
                count += 1
        # Give newly-created dispatch tasks one scheduling turn so callers can
        # observe startup/overlap state without making tick block on a run.
        await asyncio.sleep(0)
        return count

    def _dispatch_finished(self, schedule_id: str, task: asyncio.Future[None]) -> None:
        self._running_tasks.pop(schedule_id, None)
        self._running.discard(schedule_id)
        # Consume exceptions here; the worker must not emit unhandled-task
        # warnings when a scheduled dispatch fails after tick() returns.
        if not task.cancelled():
            task.exception()

    async def _run(self) -> None:
        while True:
            await self.tick(datetime.now().astimezone())
            await asyncio.sleep(self.interval_seconds)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        tasks = list(self._running_tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            self._running_tasks.clear()
            self._running.clear()
