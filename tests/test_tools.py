"""Tests for the HVAC tools module."""

import json

from src.tools import (
    HVACToolDispatcher,
    TOOL_SCHEMAS,
    execute_tool,
    get_tools_json,
    handle_function_calls,
)
from src.findings_store import FindingsStore
from src.kb_store import KBStore
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _fresh_dispatcher() -> HVACToolDispatcher:
    kb = KBStore(REPO_ROOT / "kb")
    kb.load()
    return HVACToolDispatcher(kb_store=kb, findings_store=FindingsStore())


def test_schemas_loaded_from_shared():
    """All 6 HVAC tool schemas should be present (5 on-device + 1 online escalation)."""
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert names == {
        "query_kb",
        "log_finding",
        "flag_safety",
        "flag_scope_change",
        "close_job",
        "search_online_hvac",
    }


def test_get_tools_json():
    tools = json.loads(get_tools_json())
    assert len(tools) == 6


def test_query_kb_returns_carrier():
    d = _fresh_dispatcher()
    out = json.loads(d.execute("query_kb", {"query": "Carrier 58STA intermittent cooling clicking"}))
    assert out["result_count"] >= 1
    assert out["results"][0]["id"] == "carrier-58sta-capacitor"


def test_query_kb_gas_smell_routes_to_safety_entry():
    d = _fresh_dispatcher()
    out = json.loads(d.execute("query_kb", {"query": "gas smell furnace evacuate"}))
    assert out["results"][0]["id"] == "generic-gas-furnace-gas-smell"


def test_log_finding_persists():
    d = _fresh_dispatcher()
    out = json.loads(d.execute(
        "log_finding",
        {"location": "outdoor condenser", "issue": "failed run capacitor", "severity": "major", "part_number": "P291-4554RS"},
    ))
    assert out["logged"] is True
    assert out["finding_count"] == 1
    assert d.findings.findings[0].part_number == "P291-4554RS"


def test_flag_safety_sets_stopped():
    d = _fresh_dispatcher()
    out = json.loads(d.execute(
        "flag_safety",
        {"hazard": "gas smell", "immediate_action": "evacuate and call utility", "level": "stop"},
    ))
    assert out["is_stopped"] is True


def test_flag_scope_change():
    d = _fresh_dispatcher()
    out = json.loads(d.execute(
        "flag_scope_change",
        {
            "original_scope": "replace capacitor",
            "new_scope": "also replace contactor",
            "reason": "contactor visibly pitted",
            "estimated_extra_time_minutes": 15,
        },
    ))
    assert out["flagged"] is True
    assert out["scope_change"]["estimated_extra_time_minutes"] == 15


def test_close_job_emits_snapshot():
    d = _fresh_dispatcher()
    d.execute("log_finding", {"location": "outdoor", "issue": "bulged capacitor", "severity": "major"})
    out = json.loads(d.execute(
        "close_job",
        {
            "summary": "Replaced run capacitor, unit cooling normally",
            "parts_used": ["P291-4554RS"],
            "follow_up_required": False,
        },
    ))
    assert out["closed"] is True
    assert out["session"]["closure"]["summary"].startswith("Replaced")
    assert len(out["session"]["findings"]) == 1


def test_unknown_tool_errors_cleanly():
    d = _fresh_dispatcher()
    out = json.loads(d.execute("nope", {}))
    assert "error" in out


def test_bad_arguments_error_message():
    d = _fresh_dispatcher()
    out = json.loads(d.execute("log_finding", {}))  # missing required
    assert "error" in out


def test_handle_function_calls_batch():
    d = _fresh_dispatcher()
    msgs = d.handle_function_calls([
        {"name": "query_kb", "arguments": {"query": "Trane contactor humming"}},
        {"name": "log_finding", "arguments": {"location": "disconnect", "issue": "pitted contactor", "severity": "major"}},
    ])
    assert len(msgs) == 2
    assert all(m["role"] == "tool" for m in msgs)


def test_legacy_global_execute_tool_still_works():
    """Backward-compat shim used by src/agent.py should still route."""
    result = json.loads(execute_tool("query_kb", {"query": "mini split blinking error"}))
    assert result["result_count"] >= 1


def test_legacy_handle_function_calls():
    results = handle_function_calls([
        {"name": "query_kb", "arguments": {"query": "goodman low refrigerant"}},
    ])
    assert len(results) == 1
    assert results[0]["role"] == "tool"
