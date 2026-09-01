import asyncio
from datetime import datetime

import pytest
from sdpstudio_server.scheduler import ScheduleWorker, next_fire, schedule_matches


def test_cli_exposes_dedicated_worker_command():
    from sdpstudio_cli.main import build_parser

    args = build_parser().parse_args(["worker", "--interval", "5"])
    assert args.command == "worker"
    assert args.interval == 5


def test_schedule_matches_five_field_cron():
    moment = datetime(2026, 8, 24, 0, 0)
    assert schedule_matches("0 0 * * *", moment)
    assert not schedule_matches("5 0 * * *", moment)
    assert schedule_matches("0 0 20-30 8 *", moment)


def test_next_fire_is_timezone_aware_and_bounded():
    after = datetime(2026, 8, 24, 23, 59)
    result = next_fire("0 0 * * *", after, "Europe/Madrid")
    assert result is not None
    assert result.hour == 0 and result.tzinfo is not None
    with pytest.raises(ValueError, match="Unknown timezone"):
        next_fire("0 0 * * *", after, "Mars/Olympus")


@pytest.mark.asyncio
async def test_worker_dispatches_enabled_schedule_once_per_minute():
    dispatched: list[str] = []
    worker = ScheduleWorker(
        lambda: [{"id": "a", "cron": "0 0 * * *", "enabled": True}],
        lambda schedule: _record(dispatched, schedule["id"]),
    )
    moment = datetime(2026, 8, 24, 0, 0)
    assert await worker.tick(moment) == 1
    assert await worker.tick(moment) == 0
    assert dispatched == ["a"]


@pytest.mark.asyncio
async def test_worker_runs_one_missed_fire_on_startup_when_configured():
    dispatched: list[str] = []
    worker = ScheduleWorker(
        lambda: [
            {
                "id": "a",
                "cron": "0 * * * *",
                "enabled": True,
                "missed_run_policy": "run_once",
                "last_claim_marker": "2026-08-23T22:00",
            }
        ],
        lambda schedule: _record(dispatched, schedule["id"]),
    )
    assert await worker.tick(datetime(2026, 8, 24, 0, 30)) == 1
    assert dispatched == ["a"]


@pytest.mark.asyncio
async def test_worker_forbids_overlapping_dispatches():
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def dispatch(_schedule):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    worker = ScheduleWorker(
        lambda: [{"id": "a", "cron": "0 0 * * *", "enabled": True, "concurrency_policy": "forbid"}],
        dispatch,
    )
    first = asyncio.create_task(worker.tick(datetime(2026, 8, 24, 0, 0)))
    await started.wait()
    worker._last_minute = None
    assert await worker.tick(datetime(2026, 8, 24, 0, 1)) == 0
    release.set()
    await first
    assert calls == 1


@pytest.mark.asyncio
async def test_worker_accepts_async_schedule_listing():
    dispatched: list[str] = []

    async def schedules() -> list[dict[str, object]]:
        return [{"id": "s1", "cron": "* * * * *", "enabled": True}]

    async def dispatch(schedule: dict[str, object]) -> None:
        dispatched.append(str(schedule["id"]))

    worker = ScheduleWorker(schedules, dispatch)
    assert await worker.tick(datetime(2026, 1, 1, 0, 0)) == 1
    assert dispatched == ["s1"]


@pytest.mark.asyncio
async def test_worker_replaces_an_in_flight_dispatch():
    started: list[str] = []
    cancelled = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(schedule):
        started.append(str(schedule["id"]))
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    worker = ScheduleWorker(
        lambda: [
            {"id": "a", "cron": "* * * * *", "enabled": True, "concurrency_policy": "replace"}
        ],
        dispatch,
    )
    await worker.tick(datetime(2026, 8, 24, 0, 0))
    worker._last_minute = None
    assert await worker.tick(datetime(2026, 8, 24, 0, 1)) == 1
    await cancelled.wait()
    assert started == ["a", "a"]
    release.set()
    await worker.stop()


async def _record(target: list[str], value: str) -> None:
    target.append(value)
