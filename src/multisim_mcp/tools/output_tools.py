"""
MCP Tools: Output request & data retrieval.

Covers: set_output_request, clear_output_request, is_output_ready,
        get_output_data, summarize_output.
"""

from __future__ import annotations

import math

from ..com_adapter import MultisimCOMError, INTERPOLATION_MAP
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


def tool_set_output_request(
    session: SessionManager,
    output_name: str,
    interpolation: str = "raw",
    sample_rate: float = 1000.0,
    num_samples: int = 1000,
    repeat: bool = False,
) -> dict:
    """Configure an output data request before simulation."""
    interp = INTERPOLATION_MAP.get(interpolation.lower())
    if interp is None:
        return _err(f"Invalid interpolation: {interpolation}", "E4_BAD_INTERP")
    try:
        session.adapter.set_output_request(
            output_name, interp, sample_rate, num_samples, repeat
        )
        session.log_action(
            "set_output_request",
            {"output": output_name, "interp": interpolation, "rate": sample_rate},
            result_summary="ok",
        )
        return _ok({
            "output_name": output_name,
            "interpolation": interpolation,
            "sample_rate": sample_rate,
            "num_samples": num_samples,
            "repeat": repeat,
        })
    except MultisimCOMError as exc:
        session.log_action(
            "set_output_request", {"output": output_name}, error=str(exc)
        )
        return _err(str(exc), "E4_OUTPUT_REQ_FAILED", exc.last_error)


def tool_clear_output_request(session: SessionManager, output_name: str) -> dict:
    """Clear a previously set output request."""
    try:
        session.adapter.clear_output_request(output_name)
        session.log_action(
            "clear_output_request", {"output": output_name}, result_summary="ok"
        )
        return _ok({"output_name": output_name, "cleared": True})
    except MultisimCOMError as exc:
        session.log_action(
            "clear_output_request", {"output": output_name}, error=str(exc)
        )
        return _err(str(exc), "E4_CLEAR_OUTPUT_FAILED", exc.last_error)


def tool_is_output_ready(session: SessionManager, output_name: str) -> dict:
    """Check if output data is ready for retrieval."""
    try:
        ready = session.adapter.output_ready(output_name)
        return _ok({"output_name": output_name, "ready": ready})
    except MultisimCOMError as exc:
        return _err(str(exc), "E4_OUTPUT_READY_FAILED", exc.last_error)


def tool_get_output_data(session: SessionManager, output_name: str) -> dict:
    """
    Retrieve simulation output data for a probe.
    Returns time/frequency values and corresponding real/imaginary data.
    Note: calling this consumes the data block from Multisim.
    """
    try:
        data = session.adapter.get_output_data(output_name)
        n_points = len(data.get("time_or_freq", []))
        session.log_action(
            "get_output_data",
            {"output": output_name},
            result_summary=f"{n_points} points",
        )
        return _ok({
            "output_name": output_name,
            "num_points": n_points,
            "time_or_freq": data["time_or_freq"],
            "real": data["real"],
            "imaginary": data["imaginary"],
        })
    except MultisimCOMError as exc:
        session.log_action("get_output_data", {"output": output_name}, error=str(exc))
        return _err(str(exc), "E4_GET_DATA_FAILED", exc.last_error)


def tool_summarize_output(
    session: SessionManager,
    output_name: str,
    metrics: list[str] | None = None,
) -> dict:
    """
    Retrieve output data and compute summary metrics.
    Supported metrics: peak, min, mean, rms, steady_state, overshoot,
                       cutoff_frequency_3db, gain_db.
    If metrics is None, computes all.
    """
    try:
        data = session.adapter.get_output_data(output_name)
    except MultisimCOMError as exc:
        return _err(str(exc), "E4_GET_DATA_FAILED", exc.last_error)

    x = data.get("time_or_freq", [])
    y_real = data.get("real", [])
    y_imag = data.get("imaginary", [])
    n = len(y_real)

    if n == 0:
        return _err("No data points returned", "E4_NO_DATA")

    all_metrics = metrics or [
        "peak", "min", "mean", "rms", "steady_state",
        "overshoot", "cutoff_frequency_3db", "gain_db",
    ]

    # Compute magnitude for frequency domain
    has_imag = any(abs(v) > 1e-30 for v in y_imag)
    if has_imag:
        magnitude = [math.sqrt(r**2 + im**2) for r, im in zip(y_real, y_imag)]
    else:
        magnitude = y_real

    summary: dict = {"output_name": output_name, "num_points": n}

    if "peak" in all_metrics:
        summary["peak"] = max(magnitude)

    if "min" in all_metrics:
        summary["min"] = min(magnitude)

    if "mean" in all_metrics:
        summary["mean"] = sum(magnitude) / n

    if "rms" in all_metrics:
        summary["rms"] = math.sqrt(sum(v**2 for v in magnitude) / n)

    if "steady_state" in all_metrics and n >= 10:
        # Use last 10% as steady-state estimate
        tail = magnitude[int(n * 0.9):]
        summary["steady_state"] = sum(tail) / len(tail) if tail else 0

    if "overshoot" in all_metrics and n >= 10:
        peak = max(magnitude)
        tail = magnitude[int(n * 0.9):]
        ss = sum(tail) / len(tail) if tail else 0
        if abs(ss) > 1e-15:
            summary["overshoot_percent"] = ((peak - ss) / abs(ss)) * 100
        else:
            summary["overshoot_percent"] = 0.0

    if "cutoff_frequency_3db" in all_metrics and has_imag and len(x) > 1:
        # Find -3dB point from peak magnitude
        peak_mag = max(magnitude)
        threshold = peak_mag / math.sqrt(2)  # -3dB
        fc = None
        for i in range(len(magnitude)):
            if magnitude[i] <= threshold:
                fc = x[i]
                break
        summary["cutoff_frequency_3db"] = fc

    if "gain_db" in all_metrics and has_imag and len(magnitude) > 0:
        # Low-frequency gain in dB
        lf_gain = magnitude[0] if magnitude[0] > 1e-30 else 1e-30
        summary["gain_db"] = 20 * math.log10(lf_gain)

    session.log_action(
        "summarize_output",
        {"output": output_name, "metrics": all_metrics},
        result_summary=f"{len(summary)} metrics computed",
    )
    return _ok(summary)
