"""
MCP Tools: Enumeration & Reporting.

Covers: list_components, list_inputs, list_outputs, list_sections,
        list_variants, export_netlist, export_bom.
"""

from __future__ import annotations

import os

from ..com_adapter import (
    MultisimCOMAdapter,
    MultisimCOMError,
    COMPONENT_ALL,
    COMPONENT_ACTIVE,
    COMPONENT_PASSIVE,
    SIMULATION_IO_ALL,
    SIMULATION_IO_VOLTAGE,
    SIMULATION_IO_CURRENT,
    SIMULATION_IO_DIGITAL,
    EXPORT_FORMAT_TEXT,
    EXPORT_FORMAT_CSV,
    CIRCUIT_PARAM_ALL,
    CIRCUIT_PARAM_TOP_LEVEL,
    CIRCUIT_PARAM_LEVEL_MAP,
)
from ..session import SessionManager
from ..models import ToolResponse


COMPONENT_FILTER_MAP = {
    "all": COMPONENT_ALL,
    "active": COMPONENT_ACTIVE,
    "passive": COMPONENT_PASSIVE,
}

IO_TYPE_MAP = {
    "all": SIMULATION_IO_ALL,
    "voltage": SIMULATION_IO_VOLTAGE,
    "current": SIMULATION_IO_CURRENT,
    "digital": SIMULATION_IO_DIGITAL,
}

EXPORT_FORMAT_MAP = {
    "text": EXPORT_FORMAT_TEXT,
    "csv": EXPORT_FORMAT_CSV,
}


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


def tool_list_components(
    session: SessionManager, filter_type: str = "all"
) -> dict:
    """List all components in the current circuit."""
    filt = COMPONENT_FILTER_MAP.get(filter_type.lower(), COMPONENT_ALL)
    try:
        components = session.adapter.enum_components(filt)
        # Enrich with RLC values where possible
        enriched = []
        for refdes in components:
            entry: dict = {"refdes": refdes}
            # Try reading RLC value
            try:
                val = session.adapter.get_rlc_value(refdes)
                entry["rlc_value"] = val
                entry["editable"] = True
            except MultisimCOMError:
                entry["rlc_value"] = None
                entry["editable"] = False
            # Try getting sections
            try:
                sects = session.adapter.enum_sections(refdes)
                entry["sections"] = sects
            except MultisimCOMError:
                entry["sections"] = []
            enriched.append(entry)

        session.log_action(
            "list_components",
            {"filter": filter_type},
            result_summary=f"{len(enriched)} components",
        )
        return _ok({"components": enriched, "count": len(enriched)})
    except MultisimCOMError as exc:
        session.log_action("list_components", {"filter": filter_type}, error=str(exc))
        return _err(str(exc), "E2_ENUM_FAILED", exc.last_error)


def tool_list_inputs(session: SessionManager, io_type: str = "all") -> dict:
    """List all available input sources in the circuit."""
    filt = IO_TYPE_MAP.get(io_type.lower(), SIMULATION_IO_ALL)
    try:
        inputs = session.adapter.enum_inputs(filt)
        session.log_action(
            "list_inputs", {"io_type": io_type}, result_summary=f"{len(inputs)} inputs"
        )
        return _ok({"inputs": inputs, "count": len(inputs)})
    except MultisimCOMError as exc:
        session.log_action("list_inputs", {"io_type": io_type}, error=str(exc))
        return _err(str(exc), "E2_ENUM_FAILED", exc.last_error)


def tool_list_outputs(session: SessionManager, io_type: str = "all") -> dict:
    """List all available output probes in the circuit."""
    filt = IO_TYPE_MAP.get(io_type.lower(), SIMULATION_IO_ALL)
    try:
        outputs = session.adapter.enum_outputs(filt)
        session.log_action(
            "list_outputs", {"io_type": io_type}, result_summary=f"{len(outputs)} outputs"
        )
        return _ok({"outputs": outputs, "count": len(outputs)})
    except MultisimCOMError as exc:
        session.log_action("list_outputs", {"io_type": io_type}, error=str(exc))
        return _err(str(exc), "E2_ENUM_FAILED", exc.last_error)


def tool_list_sections(session: SessionManager, component_refdes: str) -> dict:
    """List sections of a multi-section component."""
    try:
        sections = session.adapter.enum_sections(component_refdes)
        session.log_action(
            "list_sections",
            {"refdes": component_refdes},
            result_summary=f"{len(sections)} sections",
        )
        return _ok({"refdes": component_refdes, "sections": sections})
    except MultisimCOMError as exc:
        session.log_action(
            "list_sections", {"refdes": component_refdes}, error=str(exc)
        )
        return _err(str(exc), "E3_SECTION_FAILED", exc.last_error)


def tool_list_variants(session: SessionManager) -> dict:
    """List all circuit variants."""
    try:
        variants = session.adapter.enum_variants()
        active = session.adapter.get_active_variant()
        session.log_action(
            "list_variants", {}, result_summary=f"{len(variants)} variants"
        )
        return _ok({"variants": variants, "active_variant": active})
    except MultisimCOMError as exc:
        session.log_action("list_variants", {}, error=str(exc))
        return _err(str(exc), "E2_ENUM_FAILED", exc.last_error)


def tool_export_netlist(
    session: SessionManager,
    path: str = "",
    fmt: str = "text",
    include_probes: bool = False,
) -> dict:
    """Export netlist. If path is empty, returns content inline."""
    export_fmt = EXPORT_FORMAT_MAP.get(fmt.lower(), EXPORT_FORMAT_TEXT)
    try:
        content = session.adapter.report_netlist(
            probes_flag=include_probes,
            format_type=export_fmt,
            file_name=path if path else "",
        )
        result: dict = {"format": fmt, "include_probes": include_probes, "content": content}
        if path:
            result["path"] = os.path.abspath(path)
        session.log_action("export_netlist", {"path": path, "format": fmt}, result_summary="ok")
        return _ok(result)
    except MultisimCOMError as exc:
        session.log_action("export_netlist", {"path": path}, error=str(exc))
        return _err(str(exc), "E2_NETLIST_EXPORT_FAILED", exc.last_error)


def tool_export_bom(
    session: SessionManager,
    path: str = "",
    fmt: str = "text",
    real_only: bool = False,
) -> dict:
    """Export BOM. If path is empty, returns content inline."""
    export_fmt = EXPORT_FORMAT_MAP.get(fmt.lower(), EXPORT_FORMAT_TEXT)
    try:
        content = session.adapter.report_bom(
            real_flag=real_only,
            format_type=export_fmt,
            file_name=path if path else "",
        )
        result: dict = {"format": fmt, "real_only": real_only, "content": content}
        if path:
            result["path"] = os.path.abspath(path)
        session.log_action("export_bom", {"path": path}, result_summary="ok")
        return _ok(result)
    except MultisimCOMError as exc:
        session.log_action("export_bom", {"path": path}, error=str(exc))
        return _err(str(exc), "E2_BOM_EXPORT_FAILED", exc.last_error)


def tool_list_circuit_parameters(
    session: SessionManager, level: str = "all"
) -> dict:
    """List circuit parameter names.
    
    Args:
        level: 'all' for all parameters, 'top_level' for top-level only
    """
    lvl = CIRCUIT_PARAM_LEVEL_MAP.get(level.lower(), CIRCUIT_PARAM_ALL)
    try:
        params = session.adapter.enum_circuit_parameters(lvl)
        session.log_action(
            "list_circuit_parameters",
            {"level": level},
            result_summary=f"{len(params)} parameters",
        )
        return _ok({"parameters": params, "count": len(params), "level": level})
    except MultisimCOMError as exc:
        session.log_action(
            "list_circuit_parameters", {"level": level}, error=str(exc)
        )
        return _err(str(exc), "E2_ENUM_PARAMS_FAILED", exc.last_error)
