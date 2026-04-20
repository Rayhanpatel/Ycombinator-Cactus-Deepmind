"""
Tool Definitions — function calling tools for the VoiceSight Field Inspector.

Defines tools that Gemma 4 can invoke after processing camera frames and audio input.
Data is stored locally in an SQLite database.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

from src.config import cfg

# ── Database Setup ────────────────────────────────────────────
DB_PATH = cfg.PROJECT_ROOT / "inspection_data.db"

def init_db():
    """Initialize the SQLite database for storing inspection findings."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            location TEXT,
            issue TEXT,
            severity TEXT,
            dimensions TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Initialize DB on load
init_db()

# ══════════════════════════════════════════════════════════════
# Tool Registry
# ══════════════════════════════════════════════════════════════

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "log_finding",
            "description": "Log an inspection finding. Use this when the user describes damage or an issue they see.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Where the issue is located (e.g., 'north wall', 'roof', 'basement pipe')"
                    },
                    "issue": {
                        "type": "string",
                        "description": "A concise description of the issue or damage (e.g., 'water leak', 'structural crack')"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "The severity level of the finding."
                    },
                    "dimensions": {
                        "type": "string",
                        "description": "The approximate size or dimensions of the issue (e.g., '3 feet wide', 'hairline')"
                    }
                },
                "required": ["location", "issue", "severity"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_findings",
            "description": "Retrieve a summary of all findings logged so far during this inspection.",
            "parameters": {
                "type": "object",
                "properties": {},
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_inspection_report",
            "description": "Compile all findings into a final Markdown report and save it to disk. Call this when the user says they are done.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_name": {
                        "type": "string",
                        "description": "The name or address of the inspection site."
                    }
                },
                "required": ["site_name"]
            }
        }
    }
]

# ══════════════════════════════════════════════════════════════
# Tool Implementations
# ══════════════════════════════════════════════════════════════

def _log_finding(location: str, issue: str, severity: str, dimensions: str = "Not specified", **kwargs) -> str:
    """Save an inspection finding directly to the SQLite database."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO findings (timestamp, location, issue, severity, dimensions) VALUES (?, ?, ?, ?, ?)",
            (timestamp, location, issue, severity, dimensions)
        )
        conn.commit()
        finding_id = cursor.lastrowid
        conn.close()
        
        logger.info(f"✅ Logged Finding #{finding_id}: {severity.upper()} severity {issue} at {location}")
        return json.dumps({
            "status": "success", 
            "message": f"Successfully logged finding {finding_id}.",
            "finding_id": finding_id
        })
    except Exception as e:
        logger.error(f"Failed to log finding: {e}")
        return json.dumps({"status": "error", "message": str(e)})


def _get_current_findings(**kwargs) -> str:
    """Fetch all stored findings from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM findings ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        conn.close()
        
        findings = [dict(row) for row in rows]
        if not findings:
            return json.dumps({"status": "success", "message": "No findings have been logged yet.", "count": 0})
            
        return json.dumps({
            "status": "success",
            "count": len(findings),
            "findings": findings
        })
    except Exception as e:
        logger.error(f"Failed to retrieve findings: {e}")
        return json.dumps({"status": "error", "message": str(e)})


def _generate_inspection_report(site_name: str, **kwargs) -> str:
    """Generate a Markdown file summarizing the entire inspection."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM findings ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return json.dumps({"status": "error", "message": "Cannot generate report. No findings have been logged."})
            
        # Create Reports directory
        reports_dir = cfg.PROJECT_ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = reports_dir / f"Inspection_Report_{site_name.replace(' ', '_')}_{date_str}.md"
        
        # Build Markdown content
        md_content = f"# VoiceSight Inspection Report\n\n"
        md_content += f"**Site Details:** {site_name}\n"
        md_content += f"**Date:** {datetime.now().strftime('%B %d, %Y')}\n"
        md_content += f"**Total Findings:** {len(rows)}\n\n"
        md_content += "---\n\n"
        
        for row in rows:
            md_content += f"### Finding #{row['id']} - {row['location']}\n"
            md_content += f"- **Issue**: {row['issue']}\n"
            md_content += f"- **Severity**: {row['severity'].upper()}\n"
            md_content += f"- **Dimensions (approx)**: {row['dimensions']}\n"
            md_content += f"- **Time Logged**: {row['timestamp']}\n\n"
            
        # Write to file
        with open(filename, "w") as f:
            f.write(md_content)
            
        logger.info(f"📄 Report written to {filename}")
        return json.dumps({
            "status": "success", 
            "message": f"Report generated successfully.",
            "file_path": str(filename)
        })
        
    except Exception as e:
        logger.error(f"Failed to generate report: {e}")
        return json.dumps({"status": "error", "message": str(e)})


# Map tool names to their implementations
_TOOL_REGISTRY: dict[str, Callable[..., str]] = {
    "log_finding": _log_finding,
    "get_current_findings": _get_current_findings,
    "generate_inspection_report": _generate_inspection_report,
}

# ══════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════

def get_tools_json() -> str:
    """Return the tool schemas as a JSON string for Cactus."""
    return json.dumps(TOOL_SCHEMAS)

def execute_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool by name with the given arguments."""
    if tool_name not in _TOOL_REGISTRY:
        logger.error(f"Unknown tool: {tool_name}")
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        logger.info(f"🔧 Executing tool: {tool_name} with args {arguments}")
        result = _TOOL_REGISTRY[tool_name](**arguments)
        logger.info(f"🔧 Tool result: {result}")
        return result
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return json.dumps({"error": str(e)})

def handle_function_calls(function_calls: list[dict]) -> list[dict]:
    """Process a list of function calls from the LLM."""
    results = []
    for call in function_calls:
        name = call.get("name", "")
        args = call.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except:
                args = {}

        result = execute_tool(name, args)
        results.append({
            "role": "tool",
            "content": json.dumps({"name": name, "content": result}),
        })

    return results
