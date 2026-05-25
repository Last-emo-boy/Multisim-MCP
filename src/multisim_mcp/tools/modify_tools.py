"""
MCP Tools: Circuit Modification.

Covers: set_rlc_value, replace_component, set_input_data_raw,
        set_input_data_sampled, clear_input.
"""

from __future__ import annotations

from ..com_adapter import (
    MultisimCOMError,
    MULTISIM_MASTER_DB,
    MULTISIM_USER_DB,
    MULTISIM_CORPORATE_DB,
)
from ..session import SessionManager
from ..models import ToolResponse

DB_MAP = {
    "master": MULTISIM_MASTER_DB,
    "user": MULTISIM_USER_DB,
    "corporate": MULTISIM_CORPORATE_DB,
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


def tool_set_rlc_value(
    session: SessionManager, refdes: str, value: float
) -> dict:
    """
    Set the value of a basic R/L/C component.
    Value must be in base SI: Ohms, Farads, Henrys.
    """
    try:
        # Read old value for audit
        old_value = session.adapter.get_rlc_value(refdes)

        # Create snapshot before modification
        snapshot = session.create_snapshot(f"set_rlc_{refdes}")

        session.adapter.set_rlc_value(refdes, value)
        session.on_modified()

        # Verify
        new_value = session.adapter.get_rlc_value(refdes)

        session.log_action(
            "set_rlc_value",
            {"refdes": refdes, "value": value},
            result_summary=f"{refdes}: {old_value} -> {new_value}",
        )
        return _ok({
            "refdes": refdes,
            "old_value": old_value,
            "new_value": new_value,
            "snapshot": snapshot,
        })
    except MultisimCOMError as exc:
        session.log_action(
            "set_rlc_value", {"refdes": refdes, "value": value}, error=str(exc)
        )
        return _err(
            str(exc),
            "E3_RLC_FAILED",
            exc.last_error,
            "Ensure component is basic RLC and simulation is stopped",
        )


def tool_replace_component(
    session: SessionManager,
    refdes: str,
    section: str = "",
    database: str = "master",
    group: str = "",
    family: str = "",
    name: str = "",
    model: str = "",
) -> dict:
    """
    Replace a component with another from the database.
    After replacement, inputs and outputs should be re-enumerated.
    """
    db = DB_MAP.get(database.lower(), MULTISIM_MASTER_DB)
    try:
        snapshot = session.create_snapshot(f"replace_{refdes}")

        new_refdes = session.adapter.replace_component(
            component_name=refdes,
            section_name=section,
            source_database=db,
            source_group=group,
            source_family=family,
            source_name=name,
            model_name=model,
        )
        session.on_modified()

        session.log_action(
            "replace_component",
            {
                "refdes": refdes,
                "section": section,
                "group": group,
                "family": family,
                "name": name,
            },
            result_summary=f"{refdes} -> {new_refdes}",
        )
        return _ok({
            "old_refdes": refdes,
            "new_refdes": new_refdes,
            "snapshot": snapshot,
            "warning": "Re-enumerate inputs/outputs after replacement",
        })
    except MultisimCOMError as exc:
        session.log_action(
            "replace_component", {"refdes": refdes, "name": name}, error=str(exc)
        )
        return _err(
            str(exc),
            "E3_REPLACE_FAILED",
            exc.last_error,
            "Ensure target exists in DB, simulation is stopped, and component types are compatible",
        )


def tool_set_input_data_raw(
    session: SessionManager,
    input_name: str,
    time_values: list[float],
    data_values: list[float],
    repeat: bool = False,
) -> dict:
    """Send arbitrary (time, value) pair data to a circuit input source."""
    if len(time_values) != len(data_values):
        return _err(
            "time_values and data_values must have same length",
            "E3_INPUT_MISMATCH",
        )
    try:
        session.adapter.reserve_input(input_name)
        session.adapter.set_input_data_raw(input_name, time_values, data_values, repeat)
        session.log_action(
            "set_input_data_raw",
            {"input": input_name, "points": len(time_values), "repeat": repeat},
            result_summary="ok",
        )
        return _ok({
            "input_name": input_name,
            "points": len(time_values),
            "repeat": repeat,
        })
    except MultisimCOMError as exc:
        session.log_action(
            "set_input_data_raw", {"input": input_name}, error=str(exc)
        )
        return _err(str(exc), "E3_INPUT_RAW_FAILED", exc.last_error)


def tool_set_input_data_sampled(
    session: SessionManager,
    input_name: str,
    sample_rate: float,
    data_values: list[float],
    repeat: bool = False,
) -> dict:
    """Send evenly-sampled data to a circuit input source."""
    try:
        session.adapter.reserve_input(input_name)
        session.adapter.set_input_data_sampled(
            input_name, sample_rate, data_values, repeat
        )
        session.log_action(
            "set_input_data_sampled",
            {"input": input_name, "rate": sample_rate, "points": len(data_values)},
            result_summary="ok",
        )
        return _ok({
            "input_name": input_name,
            "sample_rate": sample_rate,
            "points": len(data_values),
            "repeat": repeat,
        })
    except MultisimCOMError as exc:
        session.log_action(
            "set_input_data_sampled", {"input": input_name}, error=str(exc)
        )
        return _err(str(exc), "E3_INPUT_SAMPLED_FAILED", exc.last_error)


def tool_clear_input(session: SessionManager, input_name: str) -> dict:
    """Clear/cancel a previously set input."""
    try:
        session.adapter.clear_input_data(input_name)
        session.log_action("clear_input", {"input": input_name}, result_summary="ok")
        return _ok({"input_name": input_name, "cleared": True})
    except MultisimCOMError as exc:
        session.log_action("clear_input", {"input": input_name}, error=str(exc))
        return _err(str(exc), "E3_CLEAR_INPUT_FAILED", exc.last_error)


def tool_get_circuit_parameter_value(
    session: SessionManager, param_name: str
) -> dict:
    """Get a circuit parameter value. Supports sub-sheet syntax like 'SC1.Vin'."""
    try:
        value = session.adapter.get_circuit_parameter_value(param_name)
        session.log_action(
            "get_circuit_parameter_value",
            {"param": param_name},
            result_summary=f"{param_name}={value}",
        )
        return _ok({"param_name": param_name, "value": value})
    except MultisimCOMError as exc:
        session.log_action(
            "get_circuit_parameter_value", {"param": param_name}, error=str(exc)
        )
        return _err(str(exc), "E3_PARAM_GET_FAILED", exc.last_error)


def tool_set_circuit_parameter_value(
    session: SessionManager, param_name: str, value: float
) -> dict:
    """Set a circuit parameter value. Simulation must be stopped.
    Supports sub-sheet syntax like 'SC1.Vin'.
    """
    try:
        old_value = session.adapter.get_circuit_parameter_value(param_name)
        snapshot = session.create_snapshot(f"set_param_{param_name}")
        session.adapter.set_circuit_parameter_value(param_name, value)
        session.on_modified()
        new_value = session.adapter.get_circuit_parameter_value(param_name)
        session.log_action(
            "set_circuit_parameter_value",
            {"param": param_name, "value": value},
            result_summary=f"{param_name}: {old_value} -> {new_value}",
        )
        return _ok({
            "param_name": param_name,
            "old_value": old_value,
            "new_value": new_value,
            "snapshot": snapshot,
        })
    except MultisimCOMError as exc:
        session.log_action(
            "set_circuit_parameter_value",
            {"param": param_name, "value": value},
            error=str(exc),
        )
        return _err(
            str(exc),
            "E3_PARAM_SET_FAILED",
            exc.last_error,
            "Ensure simulation is stopped and parameter name is valid",
        )
