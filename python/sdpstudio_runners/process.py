"""Bounded, cancellable subprocess execution shared by runtime adapters."""

from __future__ import annotations

import asyncio
import inspect
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


def _redact(value: str) -> str:
    return re.sub(r"(?i)(token|password|secret)=([^;\s,&]+)", r"\1=***REDACTED***", value)


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    pid: int
    output: str
    timed_out: bool = False


async def run_process(
    args: list[str],
    *,
    cwd: str,
    timeout: float | None = None,
    extra_env: dict[str, str] | None = None,
    max_output_bytes: int = 8 * 1024 * 1024,
    on_line: Callable[[str], Awaitable[None] | None] | None = None,
) -> ProcessResult:
    """Run an argument-array command with bounded redacted output and cancellation."""
    if not args or any("\x00" in value for value in args):
        raise ValueError("process arguments must be non-empty and NUL-free")
    environment = dict(os.environ)
    if extra_env:
        environment.update(extra_env)
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    lines: list[str] = []
    size = 0

    async def collect() -> None:
        nonlocal size
        assert process.stdout is not None
        async for raw in process.stdout:
            line = _redact(raw.decode(errors="replace").rstrip())
            encoded_size = len(line.encode("utf-8"))
            if size < max_output_bytes:
                remaining = max_output_bytes - size
                lines.append(line[:remaining])
                size += min(encoded_size, remaining)
            if on_line is not None:
                callback = on_line(line)
                if inspect.isawaitable(callback):
                    await callback

    timed_out = False
    reader = asyncio.create_task(collect())
    try:
        await asyncio.wait_for(reader, timeout=timeout)
        code = await process.wait()
    except TimeoutError:
        timed_out = True
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
        code = -1
    return ProcessResult(code, int(process.pid or -1), "\n".join(lines), timed_out)
