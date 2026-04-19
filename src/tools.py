"""
HVAC tool dispatcher — 5 tools that Gemma 4 can call during an On-Site session.

Schemas are loaded from shared/hvac_tools.json (frozen contract shared with
the iOS scaffold). Each session gets its own HVACToolDispatcher bound to
a FindingsStore + KBStore so findings and safety state are per-tech.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.findings_store import FindingsStore
from src.kb_store import KBStore, get_kb_store

logger = logging.getLogger(__name__)


def _load_hvac_schemas() -> list[dict[str, Any]]:
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "shared" / "hvac_tools.json"
    with path.open() as f:
        data = json.load(f)
    return data["tools"]


TOOL_SCHEMAS: list[dict[str, Any]] = _load_hvac_schemas()


def get_tools_json() -> str:
    """Return the HVAC tool schemas as a JSON string for Cactus."""
    return json.dumps(TOOL_SCHEMAS)


class HVACToolDispatcher:
    """Per-session dispatcher for the 5 HVAC tools."""

    def __init__(
        self,
        kb_store: KBStore | None = None,
        findings_store: FindingsStore | None = None,
    ):
        self.kb = kb_store or get_kb_store()
        self.findings = findings_store or FindingsStore()

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Run a tool by name. Always returns a JSON string."""
        tool_name = (tool_name or "").strip()  # Gemma 4 sometimes emits leading whitespace
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            logger.error(f"Unknown tool: {tool_name!r}")
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        try:
            logger.info(f"🔧 {tool_name}({arguments})")
            result = handler(**arguments)
            return result if isinstance(result, str) else json.dumps(result)
        except TypeError as e:
            logger.error(f"{tool_name} bad arguments: {e}")
            return json.dumps({"error": f"Invalid arguments: {e}"})
        except Exception as e:
            logger.error(f"{tool_name} failed: {e}")
            return json.dumps({"error": str(e)})

    def handle_function_calls(self, function_calls: list[dict]) -> list[dict]:
        """Process a batch of function calls, return tool messages for next turn."""
        out: list[dict] = []
        for call in function_calls:
            name = call.get("name", "")
            args = call.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result = self.execute(name, args)
            out.append({
                "role": "tool",
                "content": json.dumps({"name": name, "content": result}),
            })
        return out

    # ── Tool handlers ────────────────────────────────────────────

    def _tool_query_kb(
        self,
        query: str,
        equipment_model: str | None = None,
        top_k: int = 3,
        **_: Any,
    ) -> dict[str, Any]:
        results = self.kb.search(query, equipment_model=equipment_model, top_k=top_k)
        return {
            "query": query,
            "equipment_model": equipment_model,
            "result_count": len(results),
            "results": results,
        }

    def _tool_log_finding(
        self,
        location: str,
        issue: str,
        severity: str,
        part_number: str | None = None,
        notes: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        finding = self.findings.add_finding(
            location=location,
            issue=issue,
            severity=severity,
            part_number=part_number,
            notes=notes,
        )
        return {"logged": True, "finding": finding.to_dict(), "finding_count": len(self.findings.findings)}

    def _tool_flag_safety(
        self,
        hazard: str,
        immediate_action: str,
        level: str,
        **_: Any,
    ) -> dict[str, Any]:
        alert = self.findings.add_safety(
            hazard=hazard,
            immediate_action=immediate_action,
            level=level,
        )
        return {"flagged": True, "alert": alert.to_dict(), "is_stopped": self.findings.is_stopped}

    def _tool_flag_scope_change(
        self,
        original_scope: str,
        new_scope: str,
        reason: str,
        estimated_extra_time_minutes: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        change = self.findings.add_scope_change(
            original_scope=original_scope,
            new_scope=new_scope,
            reason=reason,
            estimated_extra_time_minutes=estimated_extra_time_minutes,
        )
        return {"flagged": True, "scope_change": change.to_dict()}

    def _tool_close_job(
        self,
        summary: str,
        parts_used: list[str],
        follow_up_required: bool,
        follow_up_notes: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        closure = self.findings.close_job(
            summary=summary,
            parts_used=parts_used,
            follow_up_required=follow_up_required,
            follow_up_notes=follow_up_notes,
        )
        return {"closed": True, "closure": closure.to_dict(), "session": self.findings.snapshot()}

    def _tool_search_online_hvac(self, query: str, **_: Any) -> dict[str, Any]:
        """Online escalation — the one tool that leaves this Mac. Imported
        lazily so the requests/praw import cost isn't paid at app load."""
        from src.online_search import search as _online_search
        return _online_search(query)


# ── Backward-compat shims for src/agent.py (legacy single-dispatcher path) ──

_DEFAULT_DISPATCHER: HVACToolDispatcher | None = None


def _default_dispatcher() -> HVACToolDispatcher:
    global _DEFAULT_DISPATCHER
    if _DEFAULT_DISPATCHER is None:
        _DEFAULT_DISPATCHER = HVACToolDispatcher()
    return _DEFAULT_DISPATCHER


def execute_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    return _default_dispatcher().execute(tool_name, arguments)


def handle_function_calls(function_calls: list[dict]) -> list[dict]:
    return _default_dispatcher().handle_function_calls(function_calls)


def register_tool(*_args: Any, **_kwargs: Any) -> None:
    """Deprecated in the HVAC build; tools are defined in shared/hvac_tools.json."""
    logger.warning("register_tool is a no-op; edit shared/hvac_tools.json instead.")
