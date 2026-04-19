"""
FindingsStore — in-process session state for HVAC Copilot.

Mirrors the Swift FindingsStore contract: holds the running list of findings,
scope changes, safety state, and the final close-job record for one session.
Each WebSocket connection gets its own instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Finding:
    location: str
    issue: str
    severity: str
    part_number: str | None = None
    notes: str | None = None
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class SafetyAlert:
    hazard: str
    immediate_action: str
    level: str
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ScopeChange:
    original_scope: str
    new_scope: str
    reason: str
    estimated_extra_time_minutes: int | None = None
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class JobClosure:
    summary: str
    parts_used: list[str]
    follow_up_required: bool
    follow_up_notes: str | None = None
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        if self.follow_up_notes is None:
            d.pop("follow_up_notes")
        return d


class FindingsStore:
    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.safety_alerts: list[SafetyAlert] = []
        self.scope_changes: list[ScopeChange] = []
        self.closure: JobClosure | None = None
        self.started_at: str = _now_iso()

    def add_finding(self, **kwargs: Any) -> Finding:
        f = Finding(**kwargs)
        self.findings.append(f)
        return f

    def add_safety(self, **kwargs: Any) -> SafetyAlert:
        s = SafetyAlert(**kwargs)
        self.safety_alerts.append(s)
        return s

    def add_scope_change(self, **kwargs: Any) -> ScopeChange:
        c = ScopeChange(**kwargs)
        self.scope_changes.append(c)
        return c

    def close_job(self, **kwargs: Any) -> JobClosure:
        self.closure = JobClosure(**kwargs)
        return self.closure

    @property
    def is_stopped(self) -> bool:
        return any(s.level == "stop" for s in self.safety_alerts)

    def snapshot(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "findings": [f.to_dict() for f in self.findings],
            "safety_alerts": [s.to_dict() for s in self.safety_alerts],
            "scope_changes": [c.to_dict() for c in self.scope_changes],
            "closure": self.closure.to_dict() if self.closure else None,
            "is_stopped": self.is_stopped,
        }
