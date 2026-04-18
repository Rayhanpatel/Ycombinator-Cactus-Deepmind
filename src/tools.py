"""
Tool Definitions — function calling tools for the voice agent.

Define tools that the on-device model (FunctionGemma / Gemma 4) can invoke.
Each tool follows the OpenAI-compatible function calling schema used by Cactus.

Usage:
    from src.tools import get_tools_json, execute_tool
    tools_str = get_tools_json()
    result = execute_tool("get_weather", {"location": "San Francisco"})
"""

import json
import logging
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# Tool Registry
# ══════════════════════════════════════════════════════════════
# Add your tools here. Each tool needs:
#   1. A schema (for the model to know how to call it)
#   2. An implementation function

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, e.g. 'San Francisco, CA'",
                    },
                },
                "required": ["location"],
            },
        },
    },
    # ── Add more tool schemas below ──
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "your_tool_name",
    #         "description": "What this tool does",
    #         "parameters": { ... },
    #     },
    # },
]

# ══════════════════════════════════════════════════════════════
# Tool Implementations
# ══════════════════════════════════════════════════════════════


def _get_current_time(**kwargs) -> str:
    """Return the current date/time."""
    now = datetime.now()
    return json.dumps({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day": now.strftime("%A"),
    })


def _get_weather(location: str = "Unknown", **kwargs) -> str:
    """
    Stub weather tool — replace with a real API call.

    TODO: Integrate with OpenWeatherMap, WeatherAPI, etc.
    """
    # Placeholder response
    return json.dumps({
        "location": location,
        "temperature": "72°F",
        "condition": "Sunny",
        "humidity": "45%",
        "note": "This is a stub — replace with a real weather API.",
    })


# Map tool names to their implementations
_TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "get_current_time": _get_current_time,
    "get_weather": _get_weather,
}


# ══════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════


def get_tools_json() -> str:
    """Return the tool schemas as a JSON string for Cactus."""
    return json.dumps(TOOL_SCHEMAS)


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """
    Execute a tool by name with the given arguments.

    Returns the tool result as a JSON string.
    """
    if tool_name not in _TOOL_REGISTRY:
        logger.error(f"Unknown tool: {tool_name}")
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        logger.info(f"🔧 Executing tool: {tool_name}({arguments})")
        result = _TOOL_REGISTRY[tool_name](**arguments)
        logger.info(f"🔧 Tool result: {result}")
        return result
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return json.dumps({"error": str(e)})


def handle_function_calls(function_calls: list[dict]) -> list[dict]:
    """
    Process a list of function calls from a Cactus completion response.

    Args:
        function_calls: List of dicts with 'name' and 'arguments' keys
                       (from result["function_calls"])

    Returns:
        List of tool results formatted as message dicts for the next turn.
    """
    results = []
    for call in function_calls:
        name = call.get("name", "")
        args = call.get("arguments", {})
        if isinstance(args, str):
            args = json.loads(args)

        result = execute_tool(name, args)
        results.append({
            "role": "tool",
            "content": json.dumps({"name": name, "content": result}),
        })

    return results


def register_tool(name: str, schema: dict, implementation: Callable[..., str]) -> None:
    """
    Dynamically register a new tool at runtime.

    Args:
        name: Tool name (must match schema)
        schema: Tool schema dict (OpenAI function calling format)
        implementation: Function that takes **kwargs and returns a JSON string
    """
    TOOL_SCHEMAS.append(schema)
    _TOOL_REGISTRY[name] = implementation
    logger.info(f"🔧 Registered new tool: {name}")
