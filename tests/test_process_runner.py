import sys

import pytest
from sdpstudio_runners.process import run_process


@pytest.mark.asyncio
async def test_process_runner_streams_bounded_redacted_output(tmp_path):
    lines: list[str] = []
    result = await run_process(
        [sys.executable, "-c", "print('token=super-secret-value')"],
        cwd=str(tmp_path),
        on_line=lines.append,
    )
    assert result.returncode == 0
    assert result.pid > 0
    assert "super-secret-value" not in result.output
    assert lines == ["token=***REDACTED***"]


@pytest.mark.asyncio
async def test_process_runner_terminates_timed_out_process(tmp_path):
    result = await run_process(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        cwd=str(tmp_path),
        timeout=0.05,
    )
    assert result.timed_out is True
    assert result.returncode == -1
