from sdpstudio_server.app import _typed_run_event


def test_run_event_adds_normative_typed_envelope_without_losing_legacy_fields():
    event = {"seq": 4, "kind": "problem", "message": "failed", "data": {"code": "E1"}}
    typed = _typed_run_event(event)
    assert typed["type"] == "run.problem"
    assert typed["payload"] == {"code": "E1"}
    assert typed["kind"] == "problem"


def test_run_event_envelopes_cover_all_normative_kinds():
    expected = {
        "status": "run.status",
        "log": "run.log",
        "problem": "run.problem",
        "metrics": "node.metrics",
    }
    for kind, event_type in expected.items():
        assert _typed_run_event({"kind": kind, "data": {}})["type"] == event_type
