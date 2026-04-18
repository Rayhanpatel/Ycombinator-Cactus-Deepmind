"""Tests for the tools module."""

import json
from src.tools import (
    get_tools_json,
    execute_tool,
    handle_function_calls,
    register_tool,
)


def test_get_tools_json():
    """Tool schemas should be valid JSON."""
    tools_str = get_tools_json()
    tools = json.loads(tools_str)
    assert isinstance(tools, list)
    assert len(tools) >= 2  # get_current_time + get_weather


def test_execute_known_tool():
    """Executing a known tool should return valid JSON."""
    result = execute_tool("get_current_time", {})
    parsed = json.loads(result)
    assert "date" in parsed
    assert "time" in parsed


def test_execute_unknown_tool():
    """Executing an unknown tool should return an error."""
    result = execute_tool("nonexistent_tool", {})
    parsed = json.loads(result)
    assert "error" in parsed


def test_handle_function_calls():
    """Should process a list of function calls."""
    calls = [
        {"name": "get_current_time", "arguments": {}},
        {"name": "get_weather", "arguments": {"location": "NYC"}},
    ]
    results = handle_function_calls(calls)
    assert len(results) == 2
    assert all(r["role"] == "tool" for r in results)


def test_register_tool():
    """Dynamically registered tools should be callable."""

    def my_tool(x: str = "", **kwargs) -> str:
        return json.dumps({"echo": x})

    schema = {
        "type": "function",
        "function": {
            "name": "echo",
            "description": "Echo input",
            "parameters": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
        },
    }

    register_tool("echo", schema, my_tool)
    result = execute_tool("echo", {"x": "hello"})
    parsed = json.loads(result)
    assert parsed["echo"] == "hello"
