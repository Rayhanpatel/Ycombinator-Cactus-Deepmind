"""
HVAC Tool Handlers — All 5 HVAC-specific tool implementations.

Runs entirely without a model. Pure data logic:
  - query_kb:           Cosine similarity over pre-computed embeddings
  - log_finding:        SQLite insert
  - flag_safety:        Safety alert + SQLite insert
  - flag_scope_change:  Scope change notification + SQLite insert
  - close_job:          Aggregate findings → JSON export

Usage:
    from src.hvac_tools import HVACToolkit
    toolkit = HVACToolkit()
    result = toolkit.execute("query_kb", {"query": "Carrier short cycling"})
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.db import HVACDatabase
from src.kb_engine import KBEngine

logger = logging.getLogger(__name__)

# Default export directory — ~/Downloads on macOS
DEFAULT_EXPORT_DIR = Path.home() / "Downloads"


class HVACToolkit:
    """
    All 5 HVAC tool handlers in one class.

    State:
      - current_job_id: tracks the active job for log_finding / close_job
      - safety_state: set to True when flag_safety(level=stop) is called
    """

    def __init__(
        self,
        db_path: str = "data/findings.db",
        kb_dir: str = "kb",
        kb_index: str = "kb/kb_index.json",
        export_dir: Optional[str] = None,
    ):
        self.db = HVACDatabase(db_path)
        self.db.init_db()

        self.kb = KBEngine(kb_dir=kb_dir, index_file=kb_index)
        self.kb.load()
        # Pay the ~10s SentenceTransformer cold-start now, during app
        # startup, so the first real query doesn't block on it.
        self.kb.warmup()

        self.export_dir = Path(export_dir) if export_dir else DEFAULT_EXPORT_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

        self.current_job_id: Optional[str] = None
        self.safety_state: bool = False  # True = STOP mode

    def _ensure_job(self) -> str:
        """Ensure a job exists for the current session."""
        if self.current_job_id is None:
            self.current_job_id = self.db.create_job()
        return self.current_job_id

    def start_job(self, job_id: Optional[str] = None) -> str:
        """Explicitly start a new job."""
        self.current_job_id = self.db.create_job(job_id)
        self.safety_state = False
        return self.current_job_id

    # ══════════════════════════════════════════════════════════
    # Tool Dispatcher
    # ══════════════════════════════════════════════════════════

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name. Returns JSON string."""
        handlers = {
            "query_kb": self._handle_query_kb,
            "log_finding": self._handle_log_finding,
            "flag_safety": self._handle_flag_safety,
            "flag_scope_change": self._handle_flag_scope_change,
            "close_job": self._handle_close_job,
        }

        handler = handlers.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown HVAC tool: {tool_name}"})

        try:
            logger.info(f"🔧 HVAC tool: {tool_name}({json.dumps(arguments, default=str)[:200]})")
            result = handler(**arguments)
            logger.info(f"🔧 Result: {result[:200]}...")
            return result
        except Exception as e:
            logger.error(f"❌ Tool error in {tool_name}: {e}", exc_info=True)
            return json.dumps({"error": str(e)})

    # ══════════════════════════════════════════════════════════
    # Tool Implementations
    # ══════════════════════════════════════════════════════════

    def _handle_query_kb(
        self,
        query: str,
        equipment_model: Optional[str] = None,
        top_k: int = 3,
        **kwargs,
    ) -> str:
        """Search the HVAC knowledge base."""
        results = self.kb.search(
            query=query,
            equipment_model=equipment_model,
            top_k=top_k,
        )

        if not results:
            return json.dumps({
                "status": "no_results",
                "message": f"No KB entries matched '{query}'. Try broadening the query.",
                "query": query,
            })

        # Return results without embeddings (too large for tool output)
        clean_results = []
        for r in results:
            clean = {k: v for k, v in r.items() if k != "embedding"}
            clean_results.append(clean)

        return json.dumps({
            "status": "ok",
            "count": len(clean_results),
            "results": clean_results,
        }, indent=2)

    def _handle_log_finding(
        self,
        location: str,
        issue: str,
        severity: str,
        part_number: Optional[str] = None,
        notes: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Record a diagnosed issue to the inspection log (SQLite)."""
        job_id = self._ensure_job()

        row_id = self.db.insert_finding(
            job_id=job_id,
            location=location,
            issue=issue,
            severity=severity,
            part_number=part_number,
            notes=notes,
        )

        return json.dumps({
            "status": "logged",
            "finding_id": row_id,
            "job_id": job_id,
            "severity": severity,
            "issue": issue,
            "message": f"Finding logged: [{severity}] {issue} at {location}",
        })

    def _handle_flag_safety(
        self,
        hazard: str,
        immediate_action: str,
        level: str,
        **kwargs,
    ) -> str:
        """Raise a safety alert. Sets STOP mode if level is 'stop'."""
        job_id = self._ensure_job()

        row_id = self.db.insert_safety_flag(
            job_id=job_id,
            hazard=hazard,
            immediate_action=immediate_action,
            level=level,
        )

        # Also log as a critical finding
        self.db.insert_finding(
            job_id=job_id,
            location="SAFETY",
            issue=f"⚠️ {hazard}",
            severity="critical",
            notes=f"Immediate action: {immediate_action}",
        )

        if level == "stop":
            self.safety_state = True

        return json.dumps({
            "status": "safety_alert",
            "safety_flag_id": row_id,
            "job_id": job_id,
            "level": level,
            "hazard": hazard,
            "immediate_action": immediate_action,
            "stop_mode": self.safety_state,
            "message": (
                f"🛑 STOP — {hazard}. {immediate_action}"
                if level == "stop"
                else f"⚠️ CAUTION — {hazard}. {immediate_action}"
            ),
        })

    def _handle_flag_scope_change(
        self,
        original_scope: str,
        new_scope: str,
        reason: str,
        estimated_extra_time_minutes: Optional[int] = None,
        **kwargs,
    ) -> str:
        """Notify that repair scope has expanded."""
        job_id = self._ensure_job()

        row_id = self.db.insert_scope_change(
            job_id=job_id,
            original_scope=original_scope,
            new_scope=new_scope,
            reason=reason,
            estimated_extra_time_minutes=estimated_extra_time_minutes,
        )

        return json.dumps({
            "status": "scope_changed",
            "scope_change_id": row_id,
            "job_id": job_id,
            "original_scope": original_scope,
            "new_scope": new_scope,
            "reason": reason,
            "estimated_extra_time_minutes": estimated_extra_time_minutes,
            "message": (
                f"🔄 Scope change: '{original_scope}' → '{new_scope}'. "
                f"Reason: {reason}. "
                + (f"Extra time: ~{estimated_extra_time_minutes} min." if estimated_extra_time_minutes else "")
            ),
        })

    def _handle_close_job(
        self,
        summary: str,
        parts_used: Optional[list[str]] = None,
        follow_up_required: bool = False,
        follow_up_notes: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Finalize the visit. Aggregates all findings, generates a structured
        JSON report, and exports to ~/Downloads.
        """
        job_id = self._ensure_job()

        # Close the job in the database
        self.db.close_job(job_id, summary)

        # Aggregate all data
        findings = self.db.get_findings_for_job(job_id)
        safety_flags = self.db.get_safety_flags_for_job(job_id)
        scope_changes = self.db.get_scope_changes_for_job(job_id)

        # Build the export document
        export = {
            "job_id": job_id,
            "closed_at": datetime.now().isoformat(),
            "summary": summary,
            "parts_used": parts_used or [],
            "follow_up_required": follow_up_required,
            "follow_up_notes": follow_up_notes,
            "findings": findings,
            "safety_flags": safety_flags,
            "scope_changes": scope_changes,
            "stats": {
                "total_findings": len(findings),
                "critical_findings": sum(1 for f in findings if f.get("severity") == "critical"),
                "safety_stops": sum(1 for s in safety_flags if s.get("level") == "stop"),
                "scope_changes_count": len(scope_changes),
            },
        }

        # Export to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"hvac_job_{job_id}_{timestamp}.json"
        export_path = self.export_dir / export_filename

        with open(export_path, "w") as f:
            json.dump(export, f, indent=2, default=str)
            f.write("\n")

        logger.info(f"📄 Job report exported to: {export_path}")

        # Reset for next job
        self.current_job_id = None
        self.safety_state = False

        return json.dumps({
            "status": "closed",
            "job_id": job_id,
            "export_path": str(export_path),
            "summary": summary,
            "parts_used": parts_used or [],
            "follow_up_required": follow_up_required,
            "stats": export["stats"],
            "message": (
                f"✅ Job {job_id} closed. Report exported to {export_filename}. "
                f"{len(findings)} findings, {len(safety_flags)} safety flags."
            ),
        })

    def get_schemas(self) -> list[dict]:
        """Return the tool schemas for model integration (loads from hvac_tools.json)."""
        schema_path = Path("shared/hvac_tools.json")
        if schema_path.exists():
            with open(schema_path) as f:
                return json.load(f).get("tools", [])
        return []

    def close(self) -> None:
        """Clean up resources."""
        self.db.close()
