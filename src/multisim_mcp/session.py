"""
Session state manager for Multisim MCP.

Tracks the current session state, open file, snapshots, and audit log.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .com_adapter import MultisimCOMAdapter, SIM_STATE_STOPPED, SIM_STATE_RUNNING, SIM_STATE_PAUSED

logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    IDLE = "idle"
    DESIGN_OPENED = "design_opened"
    NETLIST_OPENED = "netlist_opened"
    MODIFIED = "modified"
    SIMULATION_RUNNING = "simulation_running"
    SIMULATION_PAUSED = "simulation_paused"
    ERROR = "error"


SIM_STATE_TO_STR = {
    SIM_STATE_STOPPED: "stopped",
    SIM_STATE_RUNNING: "running",
    SIM_STATE_PAUSED: "paused",
}


@dataclass
class AuditEntry:
    timestamp: str
    tool_name: str
    params_summary: dict[str, Any]
    target_file: str
    snapshot_path: str
    sim_state: str
    error: str
    result_summary: str


@dataclass
class SessionManager:
    """Manages Multisim session lifecycle, snapshots, and audit log."""

    adapter: MultisimCOMAdapter
    workspace_dir: str = ""
    _state: SessionState = SessionState.IDLE
    _open_file: str = ""
    _snapshot_dir: str = ""
    _audit_log: list[AuditEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.workspace_dir:
            self.workspace_dir = os.path.join(os.path.expanduser("~"), ".multisim_mcp")
        self._snapshot_dir = os.path.join(self.workspace_dir, "snapshots")
        os.makedirs(self._snapshot_dir, exist_ok=True)

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def open_file(self) -> str:
        return self._open_file

    def get_session_info(self) -> dict[str, Any]:
        """Return current session state summary."""
        sim_state = "unknown"
        circuit_name = ""
        if self.adapter.has_circuit:
            try:
                raw = self.adapter.get_simulation_state()
                sim_state = SIM_STATE_TO_STR.get(raw, f"unknown({raw})")
            except Exception:
                sim_state = "error"
            try:
                circuit_name = self.adapter.get_circuit_name()
            except Exception:
                pass

        return {
            "session_state": self._state.value,
            "open_file": self._open_file,
            "circuit_name": circuit_name,
            "simulation_state": sim_state,
            "connected": self.adapter.is_connected,
            "snapshot_dir": self._snapshot_dir,
        }

    # ── State Transitions ──────────────────────────────────

    def on_file_opened(self, filepath: str) -> None:
        self._open_file = filepath
        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".cir", ".txt"):
            self._state = SessionState.NETLIST_OPENED
        else:
            self._state = SessionState.DESIGN_OPENED

    def on_modified(self) -> None:
        if self._state in (SessionState.DESIGN_OPENED, SessionState.NETLIST_OPENED):
            self._state = SessionState.MODIFIED

    def on_simulation_started(self) -> None:
        self._state = SessionState.SIMULATION_RUNNING

    def on_simulation_paused(self) -> None:
        self._state = SessionState.SIMULATION_PAUSED

    def on_simulation_stopped(self) -> None:
        if self._open_file:
            self._state = SessionState.DESIGN_OPENED
        else:
            self._state = SessionState.IDLE

    def on_error(self) -> None:
        self._state = SessionState.ERROR

    def on_disconnected(self) -> None:
        self._state = SessionState.IDLE
        self._open_file = ""

    # ── Snapshots ──────────────────────────────────────────

    def create_snapshot(self, reason: str = "") -> str:
        """
        Create a snapshot of the current design file before a destructive operation.
        Returns the snapshot file path.
        """
        if not self._open_file or not os.path.isfile(self._open_file):
            return ""

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.basename(self._open_file)
        name, ext = os.path.splitext(base)
        snapshot_name = f"{name}_{ts}_{reason}{ext}"
        snapshot_path = os.path.join(self._snapshot_dir, snapshot_name)
        try:
            shutil.copy2(self._open_file, snapshot_path)
            logger.info("Snapshot created: %s", snapshot_path)
            return snapshot_path
        except Exception as exc:
            logger.warning("Failed to create snapshot: %s", exc)
            return ""

    # ── Audit Log ──────────────────────────────────────────

    def log_action(
        self,
        tool_name: str,
        params: dict[str, Any],
        error: str = "",
        result_summary: str = "",
    ) -> None:
        sim_state = "unknown"
        if self.adapter.has_circuit:
            try:
                raw = self.adapter.get_simulation_state()
                sim_state = SIM_STATE_TO_STR.get(raw, str(raw))
            except Exception:
                sim_state = "error"

        entry = AuditEntry(
            timestamp=datetime.datetime.now().isoformat(),
            tool_name=tool_name,
            params_summary=params,
            target_file=self._open_file,
            snapshot_path="",
            sim_state=sim_state,
            error=error,
            result_summary=result_summary,
        )
        self._audit_log.append(entry)
        logger.info("Audit: %s %s", tool_name, result_summary or error)

    def export_audit_log(self, filepath: str | None = None) -> str:
        """Export audit log to a JSON file."""
        if filepath is None:
            filepath = os.path.join(self.workspace_dir, "audit_log.json")
        entries = []
        for e in self._audit_log:
            entries.append({
                "timestamp": e.timestamp,
                "tool_name": e.tool_name,
                "params_summary": e.params_summary,
                "target_file": e.target_file,
                "snapshot_path": e.snapshot_path,
                "sim_state": e.sim_state,
                "error": e.error,
                "result_summary": e.result_summary,
            })
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        return filepath
