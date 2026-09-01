from scripts import spark_row_trace_smoke


def test_spark_row_trace_smoke_propagates_spark_runtime_environment(monkeypatch):
    captured = {}

    monkeypatch.setenv("SDPSTUDIO_SPARK_PYTHON", "python312")
    monkeypatch.setenv("JAVA_HOME", "C:/jdk-21")

    def fake_run(command, *, env, check):
        captured["command"] = command
        captured["env"] = env
        captured["check"] = check
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(spark_row_trace_smoke.subprocess, "run", fake_run)
    assert spark_row_trace_smoke.main() == 0
    assert captured["command"] == [
        "python312",
        "-m",
        "pytest",
        "-q",
        "tests/test_debug.py",
        "-k",
        "spark_subgraph",
    ]
    assert captured["env"]["SDPSTUDIO_RUN_SPARK_TRACE_TESTS"] == "1"
    assert captured["env"]["PYSPARK_PYTHON"] == "python312"
    assert captured["env"]["PYSPARK_DRIVER_PYTHON"] == "python312"
    assert captured["check"] is False
