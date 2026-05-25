"""
MCP Tools: Simulation & Analysis.

Covers: run/pause/resume/stop simulation, run_until_next_output,
        ac_sweep, dc_operating_point, transient analysis, command_line.
"""

from __future__ import annotations

from ..com_adapter import (
    MultisimCOMError,
    SWEEP_TYPE_MAP,
    INTERPOLATION_MAP,
    SIM_STATE_STOPPED,
    SIM_STATE_RUNNING,
    SIM_STATE_PAUSED,
)
from ..session import SessionManager, SIM_STATE_TO_STR
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


def _sim_state_str(session: SessionManager) -> str:
    try:
        raw = session.adapter.get_simulation_state()
        return SIM_STATE_TO_STR.get(raw, f"unknown({raw})")
    except Exception:
        return "unknown"


def tool_run_simulation(session: SessionManager) -> dict:
    """Start or resume the simulation."""
    try:
        session.adapter.run_simulation()
        session.on_simulation_started()
        state = _sim_state_str(session)
        session.log_action("run_simulation", {}, result_summary=state)
        return _ok({"simulation_state": state})
    except MultisimCOMError as exc:
        session.log_action("run_simulation", {}, error=str(exc))
        return _err(str(exc), "E4_SIM_RUN_FAILED", exc.last_error)


def tool_pause_simulation(session: SessionManager) -> dict:
    """Pause the running simulation."""
    try:
        session.adapter.pause_simulation()
        session.on_simulation_paused()
        state = _sim_state_str(session)
        session.log_action("pause_simulation", {}, result_summary=state)
        return _ok({"simulation_state": state})
    except MultisimCOMError as exc:
        session.log_action("pause_simulation", {}, error=str(exc))
        return _err(str(exc), "E4_SIM_PAUSE_FAILED", exc.last_error)


def tool_resume_simulation(session: SessionManager) -> dict:
    """Resume a paused simulation."""
    try:
        session.adapter.resume_simulation()
        session.on_simulation_started()
        state = _sim_state_str(session)
        session.log_action("resume_simulation", {}, result_summary=state)
        return _ok({"simulation_state": state})
    except MultisimCOMError as exc:
        session.log_action("resume_simulation", {}, error=str(exc))
        return _err(str(exc), "E4_SIM_RESUME_FAILED", exc.last_error)


def tool_stop_simulation(session: SessionManager) -> dict:
    """Immediately stop the simulation."""
    try:
        session.adapter.stop_simulation()
        session.on_simulation_stopped()
        state = _sim_state_str(session)
        session.log_action("stop_simulation", {}, result_summary=state)
        return _ok({"simulation_state": state})
    except MultisimCOMError as exc:
        session.log_action("stop_simulation", {}, error=str(exc))
        return _err(str(exc), "E4_SIM_STOP_FAILED", exc.last_error)


def tool_run_until_next_output(session: SessionManager) -> dict:
    """Run simulation until the next output block is ready."""
    try:
        session.adapter.run_simulation_until_next_output()
        state = _sim_state_str(session)
        session.log_action("run_until_next_output", {}, result_summary=state)
        return _ok({"simulation_state": state})
    except MultisimCOMError as exc:
        session.log_action("run_until_next_output", {}, error=str(exc))
        return _err(str(exc), "E4_SIM_NEXT_OUTPUT_FAILED", exc.last_error)


def tool_run_ac_sweep(
    session: SessionManager,
    sweep_type: str = "decade",
    num_points: int = 100,
    start_frequency: float = 1.0,
    stop_frequency: float = 1e6,
    output_names: list[str] | None = None,
) -> dict:
    """
    Run AC Sweep analysis.
    This is asynchronous - use wait_for_output / get_output_data to retrieve results.
    """
    if not output_names:
        return _err("output_names is required", "E4_MISSING_OUTPUTS")

    st = SWEEP_TYPE_MAP.get(sweep_type.lower())
    if st is None:
        return _err(
            f"Invalid sweep_type: {sweep_type}. Use decade/octave/linear.",
            "E4_BAD_SWEEP_TYPE",
        )

    try:
        session.adapter.do_ac_sweep(
            st, num_points, start_frequency, stop_frequency, output_names
        )
        session.on_simulation_started()
        session.log_action(
            "run_ac_sweep",
            {
                "sweep_type": sweep_type,
                "points": num_points,
                "start": start_frequency,
                "stop": stop_frequency,
                "outputs": output_names,
            },
            result_summary="started",
        )
        return _ok({
            "analysis": "ac_sweep",
            "sweep_type": sweep_type,
            "num_points": num_points,
            "start_frequency": start_frequency,
            "stop_frequency": stop_frequency,
            "output_names": output_names,
            "status": "running",
            "hint": "Use wait_for_output then get_output_data to retrieve results",
        })
    except MultisimCOMError as exc:
        session.log_action("run_ac_sweep", {"outputs": output_names}, error=str(exc))
        return _err(str(exc), "E4_AC_SWEEP_FAILED", exc.last_error)


def tool_run_dc_operating_point(
    session: SessionManager, output_names: list[str] | None = None
) -> dict:
    """Run DC Operating Point analysis."""
    if not output_names:
        return _err("output_names is required", "E4_MISSING_OUTPUTS")
    try:
        session.adapter.do_dc_operating_point(output_names)
        session.log_action(
            "run_dc_operating_point",
            {"outputs": output_names},
            result_summary="completed",
        )
        return _ok({
            "analysis": "dc_operating_point",
            "output_names": output_names,
            "status": "completed",
            "hint": "Use get_output_data to retrieve results",
        })
    except MultisimCOMError as exc:
        session.log_action(
            "run_dc_operating_point", {"outputs": output_names}, error=str(exc)
        )
        return _err(str(exc), "E4_DC_OP_FAILED", exc.last_error)


def tool_run_transient(
    session: SessionManager,
    stop_time: float = 0.01,
    output_names: list[str] | None = None,
    sample_rate: float = 10000.0,
    num_samples: int = 0,
    interpolation: str = "raw",
) -> dict:
    """
    Run Transient analysis by setting output requests then running simulation.
    """
    if not output_names:
        return _err("output_names is required", "E4_MISSING_OUTPUTS")

    interp = INTERPOLATION_MAP.get(interpolation.lower())
    if interp is None:
        return _err(f"Invalid interpolation: {interpolation}", "E4_BAD_INTERP")

    if num_samples <= 0:
        num_samples = int(stop_time * sample_rate)
    if num_samples <= 0:
        num_samples = 1000

    try:
        # Set output requests for each probe
        for out_name in output_names:
            session.adapter.set_output_request(
                out_name, interp, sample_rate, num_samples, False
            )

        # Run simulation
        session.adapter.run_simulation()
        session.on_simulation_started()

        # Wait for output
        wait_result = session.adapter.wait_for_next_output()

        state = _sim_state_str(session)
        session.log_action(
            "run_transient",
            {
                "stop_time": stop_time,
                "outputs": output_names,
                "sample_rate": sample_rate,
            },
            result_summary=f"done, state={state}",
        )
        return _ok({
            "analysis": "transient",
            "stop_time": stop_time,
            "output_names": output_names,
            "sample_rate": sample_rate,
            "num_samples": num_samples,
            "status": "completed",
            "timed_out": wait_result.get("timed_out", False),
            "hint": "Use get_output_data to retrieve results",
        })
    except MultisimCOMError as exc:
        session.log_action(
            "run_transient", {"stop_time": stop_time, "outputs": output_names}, error=str(exc)
        )
        return _err(str(exc), "E4_TRANSIENT_FAILED", exc.last_error)


def tool_run_command_line(
    session: SessionManager, command_file: str, log_file: str
) -> dict:
    """
    Directly simulate a SPICE netlist file.
    Expert-level: requires proper Nutmeg commands in the command file.
    """
    try:
        session.adapter.do_command_line(command_file, log_file)
        session.on_simulation_started()
        session.log_action(
            "run_command_line",
            {"command_file": command_file, "log_file": log_file},
            result_summary="started",
        )
        return _ok({
            "command_file": command_file,
            "log_file": log_file,
            "status": "running",
        })
    except MultisimCOMError as exc:
        session.log_action(
            "run_command_line", {"command_file": command_file}, error=str(exc)
        )
        return _err(str(exc), "E4_CMDLINE_FAILED", exc.last_error)


def tool_run_ac_single_frequency(
    session: SessionManager,
    frequency: float,
    output_names: list[str] | None = None,
) -> dict:
    """
    Run AC analysis at a single frequency.
    Asynchronous — use get_output_data to retrieve results.
    """
    if not output_names:
        return _err("output_names is required", "E4_MISSING_OUTPUTS")
    if frequency <= 0:
        return _err("frequency must be positive", "E4_BAD_FREQUENCY")
    try:
        session.adapter.do_ac_single_frequency(frequency, output_names)
        session.on_simulation_started()
        session.log_action(
            "run_ac_single_frequency",
            {"frequency": frequency, "outputs": output_names},
            result_summary="started",
        )
        return _ok({
            "analysis": "ac_single_frequency",
            "frequency": frequency,
            "output_names": output_names,
            "status": "running",
            "hint": "Use get_output_data to retrieve results",
        })
    except MultisimCOMError as exc:
        session.log_action(
            "run_ac_single_frequency",
            {"frequency": frequency, "outputs": output_names},
            error=str(exc),
        )
        return _err(str(exc), "E4_AC_SINGLE_FREQ_FAILED", exc.last_error)
