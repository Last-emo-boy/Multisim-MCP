"""
MCP Tools: File & Session management.

Covers: connect, open_design, open_netlist, save, save_as,
        export_circuit_image, get_session_state.
"""

from __future__ import annotations

import os

from ..com_adapter import MultisimCOMAdapter, MultisimCOMError, IMAGE_FORMAT_MAP
from ..session import SessionManager
from ..models import ToolResponse


def _ok(data: dict | None = None) -> dict:
    return ToolResponse(ok=True, data=data or {}).model_dump()


def _err(msg: str, code: str = "ERROR", last: str = "", recovery: str = "") -> dict:
    return ToolResponse(
        ok=False,
        error_code=code,
        error_message=msg,
        multisim_last_error=last,
        suggested_recovery=recovery,
    ).model_dump()


def tool_connect(
    session: SessionManager,
    path: str | None = None,
    log_file: str | None = None,
) -> dict:
    """Connect to a local Multisim instance."""
    try:
        session.adapter.connect(path=path, log_file=log_file)
        version = session.adapter.get_version_info()
        session.log_action("connect", {"path": path}, result_summary=version)
        return _ok({"version": version, "connected": True})
    except MultisimCOMError as exc:
        session.on_error()
        session.log_action("connect", {"path": path}, error=str(exc))
        return _err(str(exc), "E2_CONNECT_FAILED", exc.last_error, "Check Multisim installation")


def tool_disconnect(session: SessionManager) -> dict:
    """Disconnect from Multisim."""
    try:
        session.adapter.disconnect()
        session.on_disconnected()
        session.log_action("disconnect", {}, result_summary="ok")
        return _ok({"connected": False})
    except MultisimCOMError as exc:
        session.log_action("disconnect", {}, error=str(exc))
        return _err(str(exc), "E2_DISCONNECT_FAILED", exc.last_error)


def tool_open_design(session: SessionManager, path: str) -> dict:
    """Open an existing .ms14/.ms8+ design file."""
    abs_path = os.path.abspath(path)
    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in (".ms8", ".ms9", ".ms10", ".ms11", ".ms12", ".ms13", ".ms14"):
        return _err(
            f"Unsupported file extension: {ext}",
            "E1_BAD_EXTENSION",
            recovery="Use .ms8 or higher Multisim file",
        )
    try:
        session.adapter.open_file(abs_path)
        session.on_file_opened(abs_path)
        name = session.adapter.get_circuit_name()
        session.log_action("open_design", {"path": abs_path}, result_summary=name)
        return _ok({
            "file": abs_path,
            "circuit_name": name,
            "session_state": session.state.value,
        })
    except MultisimCOMError as exc:
        session.on_error()
        session.log_action("open_design", {"path": abs_path}, error=str(exc))
        return _err(str(exc), "E1_OPEN_FAILED", exc.last_error)


def tool_open_netlist(session: SessionManager, path: str) -> dict:
    """
    Open a .cir/.txt netlist via DoCommandLine approach.
    Creates a blank circuit, builds a nutmeg 'source' script, and runs it.
    """
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        return _err(f"File not found: {abs_path}", "E1_NOT_FOUND")
    try:
        session.adapter.new_file()

        # DoCommandLine expects nutmeg commands, not raw SPICE.
        # Build a one-line script that sources the netlist.
        cmd_path = os.path.join(session.workspace_dir, "netlist_source.cmd")
        with open(cmd_path, "w", encoding="utf-8") as f:
            f.write(f"source {abs_path.replace(os.sep, '/')}\n")

        log_path = os.path.join(session.workspace_dir, "netlist_sim.log")
        if os.path.exists(log_path):
            os.remove(log_path)

        session.adapter.do_command_line(cmd_path, log_path)
        session.on_file_opened(abs_path)
        session.log_action("open_netlist", {"path": abs_path}, result_summary="ok")
        return _ok({
            "file": abs_path,
            "session_state": session.state.value,
            "log_file": log_path,
        })
    except MultisimCOMError as exc:
        session.on_error()
        session.log_action("open_netlist", {"path": abs_path}, error=str(exc))
        return _err(str(exc), "E1_NETLIST_FAILED", exc.last_error)


def tool_save_design(session: SessionManager) -> dict:
    """Save the current circuit."""
    try:
        session.adapter.save()
        session.log_action("save_design", {}, result_summary="ok")
        return _ok({"saved": True})
    except MultisimCOMError as exc:
        session.log_action("save_design", {}, error=str(exc))
        return _err(str(exc), "E1_SAVE_FAILED", exc.last_error)


def tool_save_design_as(session: SessionManager, path: str) -> dict:
    """Save current circuit to a new file path."""
    abs_path = os.path.abspath(path)
    try:
        session.adapter.save_as(abs_path)
        session.log_action("save_design_as", {"path": abs_path}, result_summary="ok")
        return _ok({"saved": True, "path": abs_path})
    except MultisimCOMError as exc:
        session.log_action("save_design_as", {"path": abs_path}, error=str(exc))
        return _err(str(exc), "E1_SAVEAS_FAILED", exc.last_error)


def _is_blank_image(path: str) -> bool:
    """Check if an exported image is blank (uniform color / empty grid).

    Returns True if the image has very low variance (all pixels near-identical),
    which indicates Multisim exported an empty schematic grid.
    """
    try:
        from PIL import Image
        img = Image.open(path)
        # Sample pixels (don't load full image for large files)
        img_small = img.resize((100, 100))
        pixels = list(img_small.getdata())
        if not pixels:
            return True
        # Check if all pixels are within a narrow band (blank grid)
        if isinstance(pixels[0], tuple):
            # RGB or RGBA
            r_vals = [p[0] for p in pixels]
            g_vals = [p[1] for p in pixels]
            b_vals = [p[2] for p in pixels]
            r_range = max(r_vals) - min(r_vals)
            g_range = max(g_vals) - min(g_vals)
            b_range = max(b_vals) - min(b_vals)
            # If all channels have range < 30, it's basically blank
            return r_range < 30 and g_range < 30 and b_range < 30
        else:
            # Grayscale
            val_range = max(pixels) - min(pixels)
            return val_range < 30
    except Exception:
        return False


def tool_export_circuit_image(
    session: SessionManager, path: str, fmt: str = "png"
) -> dict:
    """Export circuit schematic as image."""
    abs_path = os.path.abspath(path)
    image_format = IMAGE_FORMAT_MAP.get(fmt.lower())
    if image_format is None:
        return _err(f"Unsupported image format: {fmt}", "E1_BAD_FORMAT")
    try:
        session.adapter.get_circuit_image(abs_path, image_format)

        # Validate the exported image is not blank
        if os.path.isfile(abs_path) and _is_blank_image(abs_path):
            session.log_action(
                "export_circuit_image", {"path": abs_path, "format": fmt},
                error="Exported image is blank (empty grid)",
            )
            return _err(
                "Exported image is blank — Multisim cannot render a schematic for "
                "netlist-sourced circuits. Use render_netlist_schematic instead to "
                "generate a schematic image from SPICE netlist text.",
                "E1_IMAGE_BLANK",
                recovery="Call render_netlist_schematic(netlist=...) to generate "
                         "a schematic from the SPICE netlist.",
            )

        session.log_action("export_circuit_image", {"path": abs_path, "format": fmt}, result_summary="ok")
        return _ok({"path": abs_path, "format": fmt})
    except MultisimCOMError as exc:
        session.log_action("export_circuit_image", {"path": abs_path}, error=str(exc))
        return _err(str(exc), "E1_IMAGE_FAILED", exc.last_error)


def tool_get_session_state(session: SessionManager) -> dict:
    """Get current session info."""
    info = session.get_session_info()
    return _ok(info)


def tool_create_snippet(
    session: SessionManager, path: str, zoom_factor: float = 1.0
) -> dict:
    """Create a PNG snippet of the current circuit sheet."""
    try:
        saved_path = session.adapter.create_snippet(path, False, zoom_factor)
        session.log_action(
            "create_snippet",
            {"path": path, "zoom": zoom_factor},
            result_summary=saved_path,
        )
        return _ok({"path": saved_path, "zoom_factor": zoom_factor})
    except MultisimCOMError as exc:
        session.log_action("create_snippet", {"path": path}, error=str(exc))
        return _err(str(exc), "E1_SNIPPET_FAILED", exc.last_error)


def tool_save_design_as_snippet(
    session: SessionManager, path: str, zoom_factor: float = 1.0
) -> dict:
    """Save entire design (excluding hierarchical blocks) as a PNG snippet."""
    try:
        saved_path = session.adapter.save_design_as_snippet(path, zoom_factor)
        session.log_action(
            "save_design_as_snippet",
            {"path": path, "zoom": zoom_factor},
            result_summary=saved_path,
        )
        return _ok({"path": saved_path, "zoom_factor": zoom_factor})
    except MultisimCOMError as exc:
        session.log_action(
            "save_design_as_snippet", {"path": path}, error=str(exc)
        )
        return _err(str(exc), "E1_DESIGN_SNIPPET_FAILED", exc.last_error)
