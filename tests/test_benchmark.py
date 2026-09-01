from scripts.benchmark import run, run_scale


def test_representative_benchmark_stays_within_ci_budget():
    result = run(iterations=1)
    assert result["nodes"] == 26
    assert result["problems"] == 0
    assert result["elapsed_ms"] < 5000


def test_scale_benchmark_covers_release_target_sizes():
    result = run_scale(iterations=1, sizes=(25, 500, 1000))
    assert [item["nodes"] for item in result["benchmarks"]] == [26, 501, 1001]
    assert all(item["problems"] == 0 for item in result["benchmarks"])
