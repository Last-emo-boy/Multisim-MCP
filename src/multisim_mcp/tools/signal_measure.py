"""
MCP Tools: Signal Measurement Engine.

Provides structured measurement extraction from time-domain waveform data.
Supports: vpp, peak, valley, rms, mean, gain, frequency, rise_time, fall_time,
overshoot, settling_time, duty_cycle, period, phase, steady_state_mean,
thd, slew_rate, settling_time.

Can be used standalone via ``measure_signals`` tool, or called internally
by other tools (transient_sweep, oscilloscope, etc.).
"""

from __future__ import annotations

import math
import os
from typing import Any

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


def _format_eng(value: float) -> str:
    """Format a number in engineering notation."""
    if value == 0:
        return "0"
    abs_val = abs(value)
    prefixes = [
        (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"),
        (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"),
    ]
    for threshold, prefix in prefixes:
        if abs_val >= threshold:
            scaled = value / threshold
            if scaled == int(scaled):
                return f"{int(scaled)}{prefix}"
            return f"{scaled:.4g}{prefix}"
    return f"{value:.4g}"


# ── Core measurement engine ────────────────────────────────

ALL_METRICS = [
    "vpp", "peak", "valley", "rms", "mean", "frequency", "period",
    "rise_time", "fall_time", "overshoot", "duty_cycle",
    "steady_state_mean", "steady_state_rms",
    "ripple_vpp", "dc_level", "dominant_frequency",
    "thd", "slew_rate", "settling_time",
]


def _find_zero_crossings(values: list[float], time: list[float], rising: bool = True) -> list[float]:
    """Find zero-crossing times via linear interpolation."""
    crossings: list[float] = []
    mean = sum(values) / len(values)
    centered = [v - mean for v in values]

    for i in range(len(centered) - 1):
        if rising and centered[i] <= 0 < centered[i + 1]:
            # Rising crossing — interpolate
            frac = -centered[i] / (centered[i + 1] - centered[i]) if (centered[i + 1] - centered[i]) != 0 else 0
            t_cross = time[i] + frac * (time[i + 1] - time[i])
            crossings.append(t_cross)
        elif not rising and centered[i] >= 0 > centered[i + 1]:
            # Falling crossing
            frac = centered[i] / (centered[i] - centered[i + 1]) if (centered[i] - centered[i + 1]) != 0 else 0
            t_cross = time[i] + frac * (time[i + 1] - time[i])
            crossings.append(t_cross)
    return crossings


def _find_threshold_crossing(values: list[float], time: list[float],
                              threshold: float, rising: bool) -> float | None:
    """Find first time a signal crosses a threshold."""
    for i in range(len(values) - 1):
        if rising and values[i] <= threshold < values[i + 1]:
            frac = (threshold - values[i]) / (values[i + 1] - values[i]) if values[i + 1] != values[i] else 0
            return time[i] + frac * (time[i + 1] - time[i])
        elif not rising and values[i] >= threshold > values[i + 1]:
            frac = (values[i] - threshold) / (values[i] - values[i + 1]) if values[i] != values[i + 1] else 0
            return time[i] + frac * (time[i + 1] - time[i])
    return None


def compute_measurements(
    time: list[float],
    values: list[float],
    metrics: list[str] | None = None,
    steady_state_fraction: float = 0.5,
    cycle_index: int | None = None,
) -> dict[str, Any]:
    """Compute structured measurements from a time-domain signal.

    Args:
        time: Time array.
        values: Signal amplitude array (same length as time).
        metrics: List of metrics to compute (None = all).
        steady_state_fraction: Fraction of signal to use for steady-state
                               measurements (taken from the end).
        cycle_index: If set, measure only this cycle (0-indexed).

    Returns:
        Dict of measurement results with both raw values and formatted strings.
    """
    if not values or not time:
        return {}

    n = len(values)
    requested = set(metrics or ALL_METRICS)
    result: dict[str, Any] = {}

    # ── Extract a specific cycle if requested ───────────────
    if cycle_index is not None:
        rising_crossings = _find_zero_crossings(values, time, rising=True)
        if cycle_index + 1 < len(rising_crossings):
            t_start = rising_crossings[cycle_index]
            t_end = rising_crossings[cycle_index + 1]
            # Find indices for this cycle
            i_start = next((i for i, t in enumerate(time) if t >= t_start), 0)
            i_end = next((i for i, t in enumerate(time) if t >= t_end), n)
            time = time[i_start:i_end]
            values = values[i_start:i_end]
            n = len(values)
            result["cycle_index"] = cycle_index
            result["cycle_start_time"] = t_start
            result["cycle_end_time"] = t_end

    if n == 0:
        return result

    # ── Basic statistics ────────────────────────────────────
    peak = max(values)
    valley = min(values)
    vpp = peak - valley
    mean = sum(values) / n
    rms = math.sqrt(sum(v * v for v in values) / n)

    if "peak" in requested:
        result["peak"] = peak
    if "valley" in requested:
        result["valley"] = valley
    if "vpp" in requested:
        result["vpp"] = vpp
    if "mean" in requested:
        result["mean"] = mean
    if "rms" in requested:
        result["rms"] = rms

    # ── Frequency / period from zero crossings ──────────────
    if "frequency" in requested or "period" in requested:
        rising_crossings = _find_zero_crossings(values, time, rising=True)
        if len(rising_crossings) >= 2:
            periods = [rising_crossings[i + 1] - rising_crossings[i]
                       for i in range(len(rising_crossings) - 1)]
            avg_period = sum(periods) / len(periods)
            if "period" in requested:
                result["period"] = avg_period
            if "frequency" in requested:
                result["frequency"] = 1.0 / avg_period if avg_period > 0 else 0

    # ── Duty cycle ──────────────────────────────────────────
    if "duty_cycle" in requested:
        above_mean = sum(1 for v in values if v > mean)
        result["duty_cycle"] = above_mean / n if n > 0 else 0

    # ── Rise time (10% → 90%) ──────────────────────────────
    if "rise_time" in requested:
        v_10 = valley + 0.1 * vpp
        v_90 = valley + 0.9 * vpp
        t_10 = _find_threshold_crossing(values, time, v_10, rising=True)
        t_90 = _find_threshold_crossing(values, time, v_90, rising=True)
        if t_10 is not None and t_90 is not None and t_90 > t_10:
            result["rise_time"] = t_90 - t_10
        else:
            result["rise_time"] = None

    # ── Fall time (90% → 10%) ──────────────────────────────
    if "fall_time" in requested:
        v_90 = valley + 0.9 * vpp
        v_10 = valley + 0.1 * vpp
        t_90f = _find_threshold_crossing(values, time, v_90, rising=False)
        t_10f = _find_threshold_crossing(values, time, v_10, rising=False)
        if t_90f is not None and t_10f is not None and t_10f > t_90f:
            result["fall_time"] = t_10f - t_90f
        else:
            result["fall_time"] = None

    # ── Overshoot ───────────────────────────────────────────
    if "overshoot" in requested:
        # Steady-state from last portion of signal
        ss_start = int(n * (1 - steady_state_fraction))
        ss_values = values[ss_start:]
        if ss_values:
            ss_mean = sum(ss_values) / len(ss_values)
            if abs(ss_mean) > 1e-15:
                result["overshoot"] = (peak - ss_mean) / abs(ss_mean) * 100  # percent
            else:
                result["overshoot"] = 0

    # ── Steady-state measurements ───────────────────────────
    if "steady_state_mean" in requested or "steady_state_rms" in requested:
        ss_start = int(n * (1 - steady_state_fraction))
        ss_values = values[ss_start:]
        if ss_values:
            if "steady_state_mean" in requested:
                result["steady_state_mean"] = sum(ss_values) / len(ss_values)
            if "steady_state_rms" in requested:
                result["steady_state_rms"] = math.sqrt(
                    sum(v * v for v in ss_values) / len(ss_values)
                )

    # ── Dominant frequency via FFT (better for filtered/distorted waveforms) ──
    if "dominant_frequency" in requested and n >= 8:
        try:
            dt = (time[-1] - time[0]) / (n - 1) if n > 1 else 1.0
            fs = 1.0 / dt if dt > 0 else 1.0
            # Remove DC offset
            centered = [v - mean for v in values]
            # Simple DFT — limit to min(n/2, 2000) bins for performance
            n_fft = n
            max_k = min(n_fft // 2, 2000)
            max_mag = 0.0
            dom_freq = 0.0
            for k in range(1, max_k):
                re_part = sum(centered[j] * math.cos(2 * math.pi * k * j / n_fft)
                              for j in range(n_fft))
                im_part = sum(centered[j] * math.sin(2 * math.pi * k * j / n_fft)
                              for j in range(n_fft))
                mag = re_part * re_part + im_part * im_part  # skip sqrt for comparison
                if mag > max_mag:
                    max_mag = mag
                    dom_freq = k * fs / n_fft
            result["dominant_frequency"] = dom_freq
        except Exception:
            result["dominant_frequency"] = None

    # ── Frequency fallback: if zero-crossing failed but FFT succeeded ──
    if ("frequency" in requested and "frequency" not in result
            and "dominant_frequency" in result
            and result.get("dominant_frequency")):
        result["frequency"] = result["dominant_frequency"]
        if "period" in requested:
            result["period"] = 1.0 / result["frequency"]

    # ── THD (Total Harmonic Distortion) via DFT ─────────────
    if "thd" in requested and n >= 16:
        try:
            dt = (time[-1] - time[0]) / (n - 1) if n > 1 else 1.0
            fs = 1.0 / dt if dt > 0 else 1.0
            centered = [v - mean for v in values]
            n_fft = n
            max_k = min(n_fft // 2, 2000)
            # Compute magnitude spectrum
            magnitudes: list[float] = []
            for k in range(1, max_k):
                re_part = sum(centered[j] * math.cos(2 * math.pi * k * j / n_fft)
                              for j in range(n_fft))
                im_part = sum(centered[j] * math.sin(2 * math.pi * k * j / n_fft)
                              for j in range(n_fft))
                magnitudes.append(math.sqrt(re_part * re_part + im_part * im_part))
            if magnitudes:
                fund_idx = magnitudes.index(max(magnitudes))
                fund_mag = magnitudes[fund_idx]
                if fund_mag > 1e-15:
                    # Sum harmonics 2nd through 5th
                    harmonic_sum_sq = 0.0
                    for h in range(2, 6):
                        h_idx = fund_idx * h
                        if h_idx < len(magnitudes):
                            harmonic_sum_sq += magnitudes[h_idx] ** 2
                    result["thd"] = math.sqrt(harmonic_sum_sq) / fund_mag * 100  # percent
                else:
                    result["thd"] = 0.0
        except Exception:
            result["thd"] = None

    # ── Slew rate (max dV/dt) ───────────────────────────────
    if "slew_rate" in requested and n >= 4:
        try:
            max_dvdt = 0.0
            for i in range(1, n):
                dt_i = time[i] - time[i - 1]
                if dt_i > 0:
                    dvdt = abs(values[i] - values[i - 1]) / dt_i
                    if dvdt > max_dvdt:
                        max_dvdt = dvdt
            result["slew_rate"] = max_dvdt  # V/s
        except Exception:
            result["slew_rate"] = None

    # ── Settling time (time to stay within ±band of final value) ──
    if "settling_time" in requested and n >= 8:
        try:
            ss_start = int(n * (1 - steady_state_fraction))
            ss_values = values[ss_start:]
            final_val = sum(ss_values) / len(ss_values) if ss_values else values[-1]
            band = vpp * 0.02 if vpp > 1e-15 else 1e-6  # 2% of Vpp
            # Walk backward from end to find last time signal was outside band
            settle_idx = 0
            for i in range(n - 1, -1, -1):
                if abs(values[i] - final_val) > band:
                    settle_idx = i + 1
                    break
            if settle_idx < n:
                result["settling_time"] = time[settle_idx] - time[0]
            else:
                result["settling_time"] = time[-1] - time[0]
        except Exception:
            result["settling_time"] = None

    # ── Ripple & DC level (for rectified / filtered waveforms) ──
    if "ripple_vpp" in requested or "dc_level" in requested:
        ss_start = int(n * (1 - steady_state_fraction))
        ss_values = values[ss_start:]
        if ss_values:
            ss_peak = max(ss_values)
            ss_valley = min(ss_values)
            ss_mean_val = sum(ss_values) / len(ss_values)
            if "ripple_vpp" in requested:
                result["ripple_vpp"] = ss_peak - ss_valley
            if "dc_level" in requested:
                result["dc_level"] = ss_mean_val

    return result


def compute_gain(
    input_values: list[float],
    output_values: list[float],
    time: list[float] | None = None,
) -> dict[str, float]:
    """Compute voltage gain between two signals.

    Returns gain (linear), gain_db, input_vpp, output_vpp.
    If time is provided, also computes phase_shift_deg.
    """
    if not input_values or not output_values:
        return {}

    in_peak, in_valley = max(input_values), min(input_values)
    out_peak, out_valley = max(output_values), min(output_values)
    in_vpp = in_peak - in_valley
    out_vpp = out_peak - out_valley

    result: dict[str, float] = {
        "input_vpp": in_vpp,
        "output_vpp": out_vpp,
    }

    if abs(in_vpp) < 1e-15:
        result["error"] = "Input amplitude too small for gain calculation"
        return result

    gain = out_vpp / in_vpp
    result["voltage_gain"] = gain
    result["gain_db"] = 20 * math.log10(abs(gain)) if gain != 0 else float("-inf")

    # Detect phase inversion
    in_mean = sum(input_values) / len(input_values)
    out_mean = sum(output_values) / len(output_values)
    in_peak_idx = input_values.index(max(input_values))
    out_at_in_peak = output_values[min(in_peak_idx, len(output_values) - 1)]
    result["phase_inverted"] = (out_at_in_peak - out_mean) < 0 < (in_peak - in_mean)

    # Compute phase shift if time array available
    if time and len(time) == len(input_values) == len(output_values):
        phase = compute_phase_shift(time, input_values, output_values)
        if phase is not None:
            result["phase_shift_deg"] = phase

    return result


def compute_phase_shift(
    time: list[float],
    signal_a: list[float],
    signal_b: list[float],
) -> float | None:
    """Compute phase shift between two signals in degrees.

    Uses zero-crossing timing on both signals to measure the time delay,
    then converts to degrees based on the signal period.
    Returns positive if signal_b leads signal_a.
    """
    if len(time) < 4 or len(signal_a) != len(time) or len(signal_b) != len(time):
        return None

    crossings_a = _find_zero_crossings(signal_a, time, rising=True)
    crossings_b = _find_zero_crossings(signal_b, time, rising=True)

    if len(crossings_a) < 2 or len(crossings_b) < 1:
        return None

    period = crossings_a[1] - crossings_a[0]
    if period <= 0:
        return None

    # Find the closest crossing of B to the first crossing of A
    t_a = crossings_a[0]
    best_dt = None
    for t_b in crossings_b:
        dt = t_b - t_a
        # Wrap to [-period/2, period/2]
        while dt > period / 2:
            dt -= period
        while dt < -period / 2:
            dt += period
        if best_dt is None or abs(dt) < abs(best_dt):
            best_dt = dt

    if best_dt is None:
        return None

    return (best_dt / period) * 360.0


# ── MCP tool ────────────────────────────────────────────────

def tool_measure_signals(
    signals: list[dict],
    metrics: list[str] | None = None,
    steady_state_fraction: float = 0.5,
    cycle_index: int | None = None,
    gain_pairs: list[dict] | None = None,
) -> dict:
    """Extract structured measurements from time-domain waveform data.

    Supports: vpp, peak, valley, rms, mean, frequency, period,
    rise_time, fall_time, overshoot, duty_cycle,
    steady_state_mean, steady_state_rms,
    thd, slew_rate, settling_time.

    Can also compute inter-signal gain and phase shift when ``gain_pairs``
    is provided.

    Each signal dict must contain:
        - ``label``: Signal name (e.g., "$out", "CH1")
        - ``time``: Time array [t0, t1, ...]
        - ``values``: Amplitude array [v0, v1, ...]

    Each gain_pair dict:
        - ``input``: Label of input signal
        - ``output``: Label of output signal

    Example — measure transient output:
        signals: [{label: "$out", time: [...], values: [...]}]
        metrics: ["vpp", "rms", "frequency", "gain"]
        → {results: [{label: "$out", vpp: 1.98, rms: 0.707, ...}]}

    Args:
        signals: List of signal dicts with label, time, and values fields.
        metrics: Metrics to compute (None = all available).
        steady_state_fraction: Last N% of signal for steady-state metrics (0.0-1.0).
        cycle_index: Measure only this cycle number (0-indexed, None = full signal).
        gain_pairs: List of {input: label, output: label} for gain calculations.
    """
    if not signals:
        return _err("signals list is empty", "E9_BAD_INPUT")

    results: list[dict] = []
    signal_map: dict[str, dict] = {}

    for sig in signals:
        label = sig.get("label", "unnamed")
        time_arr = sig.get("time", [])
        val_arr = sig.get("values", [])

        if not time_arr or not val_arr:
            results.append({"label": label, "error": "Empty time or values array"})
            continue

        if len(time_arr) != len(val_arr):
            results.append({"label": label, "error": f"Length mismatch: time={len(time_arr)}, values={len(val_arr)}"})
            continue

        meas = compute_measurements(
            time_arr, val_arr,
            metrics=metrics,
            steady_state_fraction=steady_state_fraction,
            cycle_index=cycle_index,
        )

        entry: dict[str, Any] = {"label": label}
        entry.update(meas)

        # Add formatted values
        formatted: dict[str, str] = {}
        unit_map = {
            "vpp": "V", "peak": "V", "valley": "V", "rms": "V", "mean": "V",
            "frequency": "Hz", "period": "s", "rise_time": "s", "fall_time": "s",
            "steady_state_mean": "V", "steady_state_rms": "V",
            "dominant_frequency": "Hz", "ripple_vpp": "V", "dc_level": "V",
            "slew_rate": "V/s", "settling_time": "s",
        }
        for key, unit in unit_map.items():
            if key in meas and meas[key] is not None:
                formatted[key] = f"{_format_eng(meas[key])}{unit}"
        if "overshoot" in meas and meas["overshoot"] is not None:
            formatted["overshoot"] = f"{meas['overshoot']:.1f}%"
        if "duty_cycle" in meas:
            formatted["duty_cycle"] = f"{meas['duty_cycle'] * 100:.1f}%"
        if "thd" in meas and meas["thd"] is not None:
            formatted["thd"] = f"{meas['thd']:.2f}%"
        entry["formatted"] = formatted

        results.append(entry)
        signal_map[label] = sig

    # ── Gain calculations ───────────────────────────────────
    gain_results: list[dict] = []
    if gain_pairs:
        for pair in gain_pairs:
            in_label = pair.get("input", "")
            out_label = pair.get("output", "")
            in_sig = signal_map.get(in_label)
            out_sig = signal_map.get(out_label)

            if not in_sig or not out_sig:
                gain_results.append({
                    "input": in_label, "output": out_label,
                    "error": "Signal not found",
                })
                continue

            gain = compute_gain(
                in_sig["values"], out_sig["values"],
                time=in_sig.get("time"),
            )
            gain_entry: dict[str, Any] = {"input": in_label, "output": out_label}
            gain_entry.update(gain)
            if "voltage_gain" in gain:
                gain_entry["formatted_gain"] = f"{gain['voltage_gain']:.2f}"
            if "gain_db" in gain:
                gain_entry["formatted_gain_db"] = f"{gain['gain_db']:.1f} dB"
            gain_results.append(gain_entry)

    response: dict[str, Any] = {"results": results}
    if gain_results:
        response["gain_results"] = gain_results

    return _ok(response)
