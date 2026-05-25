"""
MCP Tools: Virtual Instruments — Function Generator & Oscilloscope.

These are high-level tools that emulate lab instruments by combining
waveform generation (input injection) and data capture (output collection)
with matplotlib visualization.

Function Generator: Generate standard waveforms → inject via SetInputDataSampled
Oscilloscope:       Configure probes → run transient → capture → plot → return image
"""

from __future__ import annotations

import math
import os
from typing import Any

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


# ── Waveform Generation Helpers ─────────────────────────────


def _generate_waveform(
    waveform: str,
    frequency: float,
    amplitude: float,
    offset: float,
    duty_cycle: float,
    phase_deg: float,
    sample_rate: float,
    duration: float,
) -> list[float]:
    """Generate a standard waveform as a list of samples."""
    n_samples = int(sample_rate * duration)
    if n_samples <= 0:
        raise ValueError("duration * sample_rate must yield at least 1 sample")

    dt = 1.0 / sample_rate
    phase_rad = math.radians(phase_deg)
    samples: list[float] = []

    for i in range(n_samples):
        t = i * dt
        theta = 2.0 * math.pi * frequency * t + phase_rad

        if waveform == "sine":
            val = amplitude * math.sin(theta)
        elif waveform == "square":
            # duty_cycle: fraction of period that is HIGH
            frac = (theta / (2.0 * math.pi)) % 1.0
            val = amplitude if frac < duty_cycle else -amplitude
        elif waveform == "triangle":
            frac = (theta / (2.0 * math.pi)) % 1.0
            if frac < 0.25:
                val = amplitude * (4.0 * frac)
            elif frac < 0.75:
                val = amplitude * (2.0 - 4.0 * frac)
            else:
                val = amplitude * (4.0 * frac - 4.0)
        elif waveform == "sawtooth":
            frac = (theta / (2.0 * math.pi)) % 1.0
            val = amplitude * (2.0 * frac - 1.0)
        elif waveform == "pulse":
            frac = (theta / (2.0 * math.pi)) % 1.0
            val = amplitude if frac < duty_cycle else 0.0
        elif waveform == "dc":
            val = amplitude
        else:
            raise ValueError(f"Unknown waveform type: {waveform}")

        samples.append(val + offset)

    return samples


# ── Function Generator Tool ─────────────────────────────────


def tool_function_generator(
    session: SessionManager,
    input_name: str,
    waveform: str = "sine",
    frequency: float = 1000.0,
    amplitude: float = 1.0,
    offset: float = 0.0,
    duty_cycle: float = 0.5,
    phase: float = 0.0,
    sample_rate: float = 100000.0,
    duration: float = 0.01,
    repeat: bool = True,
) -> dict:
    """Generate a standard waveform and inject it into a circuit input source.

    Emulates a function generator by computing waveform samples in Python
    and sending them to Multisim via SetInputDataSampled.

    Supported waveforms: sine, square, triangle, sawtooth, pulse, dc.
    """
    waveform = waveform.lower().strip()
    valid = {"sine", "square", "triangle", "sawtooth", "pulse", "dc"}
    if waveform not in valid:
        return _err(
            f"Invalid waveform '{waveform}'. Use: {', '.join(sorted(valid))}",
            "E3_BAD_WAVEFORM",
        )
    if frequency <= 0 and waveform != "dc":
        return _err("frequency must be positive", "E3_BAD_FREQUENCY")
    if sample_rate <= 0:
        return _err("sample_rate must be positive", "E3_BAD_SAMPLE_RATE")
    if duration <= 0:
        return _err("duration must be positive", "E3_BAD_DURATION")
    if not 0.0 <= duty_cycle <= 1.0:
        return _err("duty_cycle must be between 0 and 1", "E3_BAD_DUTY")

    try:
        samples = _generate_waveform(
            waveform, frequency, amplitude, offset, duty_cycle, phase,
            sample_rate, duration,
        )
    except ValueError as exc:
        return _err(str(exc), "E3_WAVEFORM_GEN_FAILED")

    try:
        session.adapter.reserve_input(input_name)
        session.adapter.set_input_data_sampled(
            input_name, sample_rate, samples, repeat
        )

        # Compute preview: first few samples + stats
        n = len(samples)
        preview = samples[:min(20, n)]
        peak = max(samples)
        valley = min(samples)

        session.log_action(
            "function_generator",
            {
                "input": input_name,
                "waveform": waveform,
                "frequency": frequency,
                "amplitude": amplitude,
            },
            result_summary=f"{waveform} {frequency}Hz {n} samples",
        )
        return _ok({
            "input_name": input_name,
            "waveform": waveform,
            "frequency": frequency,
            "amplitude": amplitude,
            "offset": offset,
            "duty_cycle": duty_cycle,
            "phase": phase,
            "sample_rate": sample_rate,
            "duration": duration,
            "num_samples": n,
            "repeat": repeat,
            "peak": peak,
            "valley": valley,
            "preview": preview,
        })
    except MultisimCOMError as exc:
        session.log_action(
            "function_generator", {"input": input_name}, error=str(exc)
        )
        return _err(
            str(exc), "E3_FUNCGEN_FAILED", exc.last_error,
            "Ensure input_name is valid (from list_inputs) and simulation is stopped",
        )


# ── Oscilloscope Tool ───────────────────────────────────────


def tool_oscilloscope(
    session: SessionManager,
    output_names: list[str],
    duration: float = 0.01,
    sample_rate: float = 100000.0,
    interpolation: str = "linear",
    plot: bool = True,
    output_dir: str = "",
    title: str = "Oscilloscope Capture",
) -> dict:
    """Capture time-domain waveforms and optionally generate a plot image.

    Emulates an oscilloscope: configures probes, runs a transient simulation,
    collects data from all specified probes, and plots the results using matplotlib.

    Returns captured data + measurement summary + path to plot image (if plot=True).
    """
    if not output_names:
        return _err("output_names is required", "E5_MISSING_OUTPUTS")

    interp_code = INTERPOLATION_MAP.get(interpolation.lower())
    if interp_code is None:
        return _err(
            f"Invalid interpolation: {interpolation}", "E5_BAD_INTERP",
        )
    if duration <= 0:
        return _err("duration must be positive", "E5_BAD_DURATION")
    if sample_rate <= 0:
        return _err("sample_rate must be positive", "E5_BAD_SAMPLE_RATE")

    num_samples = int(duration * sample_rate)
    if num_samples <= 0:
        num_samples = 1000

    # ── Configure & Run ─────────────────────────────────────
    try:
        for name in output_names:
            session.adapter.set_output_request(
                name, interp_code, sample_rate, num_samples, False
            )

        session.adapter.run_simulation()
        session.on_simulation_started()
        wait_result = session.adapter.wait_for_next_output()
        timed_out = wait_result.get("timed_out", False)

    except MultisimCOMError as exc:
        session.log_action(
            "oscilloscope", {"outputs": output_names}, error=str(exc)
        )
        return _err(
            str(exc), "E5_SIM_FAILED", exc.last_error,
            "Ensure probes are valid (from list_outputs) and circuit is ready",
        )

    # ── Collect Data ────────────────────────────────────────
    channels: list[dict[str, Any]] = []
    for name in output_names:
        try:
            raw = session.adapter.get_output_data(name)
            time_data = raw["time_or_freq"]
            real_data = raw["real"]
            n = len(real_data)

            # Compute measurements
            measurements: dict[str, Any] = {"num_points": n}
            if n > 0:
                measurements["peak"] = max(real_data)
                measurements["valley"] = min(real_data)
                measurements["vpp"] = measurements["peak"] - measurements["valley"]
                measurements["mean"] = sum(real_data) / n
                measurements["rms"] = math.sqrt(sum(v ** 2 for v in real_data) / n)

                # DC offset estimate (mean)
                measurements["dc_offset"] = measurements["mean"]

                # Frequency estimate: count zero crossings
                if n > 2:
                    mean_val = measurements["mean"]
                    crossings = 0
                    for i in range(1, n):
                        if (real_data[i - 1] - mean_val) * (real_data[i] - mean_val) < 0:
                            crossings += 1
                    if crossings > 1 and len(time_data) > 1:
                        total_time = time_data[-1] - time_data[0]
                        if total_time > 0:
                            measurements["estimated_frequency"] = crossings / (2.0 * total_time)

            channels.append({
                "name": name,
                "time": time_data,
                "values": real_data,
                "measurements": measurements,
            })
        except MultisimCOMError as exc:
            channels.append({
                "name": name,
                "error": str(exc),
                "time": [],
                "values": [],
                "measurements": {},
            })

    # ── Plot ────────────────────────────────────────────────
    plot_path: str | None = None
    if plot and any(ch["values"] for ch in channels):
        try:
            plot_path = _plot_oscilloscope(
                channels, title, output_dir or session.workspace_dir,
            )
        except Exception as exc:
            # Non-fatal: plotting failure shouldn't block data return
            plot_path = None
            session.log_action(
                "oscilloscope_plot", {}, error=f"Plot failed: {exc}"
            )

    # ── Build response ──────────────────────────────────────
    response_channels = []
    for ch in channels:
        entry: dict[str, Any] = {
            "name": ch["name"],
            "measurements": ch.get("measurements", {}),
        }
        if ch.get("error"):
            entry["error"] = ch["error"]
        # Include raw data (truncated to keep response manageable)
        n = len(ch.get("values", []))
        if n > 2000:
            # Downsample for response
            step = n // 1000
            entry["time"] = ch["time"][::step]
            entry["values"] = ch["values"][::step]
            entry["downsampled"] = True
            entry["original_points"] = n
        else:
            entry["time"] = ch.get("time", [])
            entry["values"] = ch.get("values", [])
        response_channels.append(entry)

    session.log_action(
        "oscilloscope",
        {"outputs": output_names, "duration": duration},
        result_summary=f"{len(channels)} ch, plot={'yes' if plot_path else 'no'}",
    )

    return _ok({
        "channels": response_channels,
        "duration": duration,
        "sample_rate": sample_rate,
        "timed_out": timed_out,
        "plot_image": plot_path,
    })


def _plot_oscilloscope(
    channels: list[dict],
    title: str,
    output_dir: str,
) -> str:
    """Generate a multi-channel oscilloscope plot and save as PNG.

    Tries matplotlib first; falls back to Pillow-based rendering if unavailable.
    """
    try:
        return _plot_with_matplotlib(channels, title, output_dir)
    except ImportError:
        return _plot_with_pillow(channels, title, output_dir)


def _plot_with_matplotlib(
    channels: list[dict],
    title: str,
    output_dir: str,
) -> str:
    """Generate plot using matplotlib (preferred)."""
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt

    n_channels = sum(1 for ch in channels if ch.get("values"))
    if n_channels == 0:
        raise ValueError("No data to plot")

    fig, axes = plt.subplots(
        n_channels, 1,
        figsize=(12, 3 * n_channels),
        sharex=True,
        squeeze=False,
    )
    fig.suptitle(title, fontsize=14, fontweight="bold")

    plot_idx = 0
    for ch in channels:
        values = ch.get("values", [])
        if not values:
            continue
        time_data = ch.get("time", [])
        name = ch["name"]
        measurements = ch.get("measurements", {})

        ax = axes[plot_idx][0]

        # Auto-scale time axis for readability
        time_arr, time_unit = _auto_scale_time(time_data)
        ax.plot(time_arr, values, linewidth=0.8, color=_channel_color(plot_idx))
        ax.set_ylabel(name, fontsize=10)
        ax.grid(True, alpha=0.3)

        # Annotation: key measurements
        info_parts = []
        if "vpp" in measurements:
            info_parts.append(f"Vpp={_format_eng(measurements['vpp'])}V")
        if "rms" in measurements:
            info_parts.append(f"RMS={_format_eng(measurements['rms'])}V")
        if "estimated_frequency" in measurements:
            info_parts.append(f"f≈{_format_eng(measurements['estimated_frequency'])}Hz")
        if "mean" in measurements:
            info_parts.append(f"DC={_format_eng(measurements['mean'])}V")
        if info_parts:
            ax.text(
                0.02, 0.95, "  ".join(info_parts),
                transform=ax.transAxes, fontsize=8,
                verticalalignment="top",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="wheat", alpha=0.7),
            )

        plot_idx += 1

    axes[-1][0].set_xlabel(f"Time ({time_unit})")
    plt.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, "oscilloscope_capture.png")
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return plot_path


def _plot_with_pillow(
    channels: list[dict],
    title: str,
    output_dir: str,
) -> str:
    """Generate a simple oscilloscope-style plot using only Pillow.

    Used as fallback when matplotlib is not available (no 32-bit wheel).
    Draws waveforms on a dark background with grid, labels, and measurements.
    """
    from PIL import Image, ImageDraw, ImageFont

    W, H_PER_CH = 1200, 280
    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 80, 40, 50, 40
    active = [ch for ch in channels if ch.get("values")]
    if not active:
        raise ValueError("No data to plot")

    n_ch = len(active)
    total_h = MARGIN_T + n_ch * H_PER_CH + MARGIN_B
    img = Image.new("RGB", (W, total_h), color=(26, 26, 46))
    draw = ImageDraw.Draw(img)

    # Try to use a better font; fallback to default
    try:
        font_label = ImageFont.truetype("arial.ttf", 13)
        font_title = ImageFont.truetype("arial.ttf", 18)
        font_small = ImageFont.truetype("arial.ttf", 11)
    except (IOError, OSError):
        font_label = ImageFont.load_default()
        font_title = font_label
        font_small = font_label

    # Title
    draw.text((W // 2 - len(title) * 5, 12), title, fill=(0, 212, 255), font=font_title)

    colors = [(255, 215, 0), (0, 255, 127), (0, 191, 255), (255, 105, 180)]

    for ch_idx, ch in enumerate(active):
        values = ch["values"]
        time_data = ch.get("time", [])
        name = ch["name"]
        measurements = ch.get("measurements", {})
        color = colors[ch_idx % len(colors)]

        # Plot area for this channel
        y_top = MARGIN_T + ch_idx * H_PER_CH + 10
        y_bot = y_top + H_PER_CH - 30
        x_left = MARGIN_L
        x_right = W - MARGIN_R
        plot_w = x_right - x_left
        plot_h = y_bot - y_top

        # Background for plot area
        draw.rectangle([x_left, y_top, x_right, y_bot], fill=(13, 17, 23))

        # Grid lines
        for gi in range(1, 10):
            gx = x_left + int(plot_w * gi / 10)
            draw.line([(gx, y_top), (gx, y_bot)], fill=(50, 50, 70), width=1)
        for gi in range(1, 8):
            gy = y_top + int(plot_h * gi / 8)
            draw.line([(x_left, gy), (x_right, gy)], fill=(50, 50, 70), width=1)

        # Border
        draw.rectangle([x_left, y_top, x_right, y_bot], outline=(60, 60, 80))

        # Channel label
        draw.text((8, y_top + 4), name, fill=color, font=font_label)

        # Scale values to pixel coords
        n = len(values)
        if n < 2:
            continue
        v_min = min(values)
        v_max = max(values)
        v_range = v_max - v_min
        if v_range < 1e-15:
            v_range = 1.0
            v_min = values[0] - 0.5

        points = []
        for i in range(n):
            px = x_left + int(plot_w * i / (n - 1))
            py = y_bot - int(plot_h * (values[i] - v_min) / v_range)
            points.append((px, py))

        # Draw waveform (using line segments)
        if len(points) > 1:
            # Downsample if too many points for Pillow performance
            step = max(1, len(points) // plot_w)
            downsampled = points[::step]
            for i in range(len(downsampled) - 1):
                draw.line([downsampled[i], downsampled[i + 1]], fill=color, width=2)

        # Y-axis labels
        draw.text((x_left - 70, y_top), f"{_format_eng(v_max)}V", fill=(180, 180, 180), font=font_small)
        draw.text((x_left - 70, y_bot - 12), f"{_format_eng(v_min)}V", fill=(180, 180, 180), font=font_small)

        # Measurements annotation
        info_parts = []
        if "vpp" in measurements:
            info_parts.append(f"Vpp={_format_eng(measurements['vpp'])}V")
        if "rms" in measurements:
            info_parts.append(f"RMS={_format_eng(measurements['rms'])}V")
        if "estimated_frequency" in measurements:
            info_parts.append(f"f≈{_format_eng(measurements['estimated_frequency'])}Hz")
        if info_parts:
            info_text = "  ".join(info_parts)
            draw.text((x_left + 8, y_top + 4), info_text, fill=(200, 200, 160), font=font_small)

    # Time axis label
    if active and active[0].get("time"):
        t = active[0]["time"]
        _, time_unit = _auto_scale_time(t)
        draw.text(
            (W // 2 - 30, total_h - 30),
            f"Time ({time_unit})",
            fill=(180, 180, 180), font=font_label,
        )

    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, "oscilloscope_capture.png")
    img.save(plot_path, "PNG")
    return plot_path


# ── Standalone Plot Waveform Tool ───────────────────────────


def tool_plot_waveform(
    session: SessionManager,
    channels: list[dict],
    duration: float = 0.002,
    sample_rate: float = 200000.0,
    title: str = "Waveform",
    output_path: str = "",
    width: int = 1200,
    height_per_channel: int = 280,
    overlay: bool = False,
) -> dict:
    """Generate a multi-channel waveform plot from parameters or raw data.

    Each channel dict can specify EITHER:
      - Computed waveform:  ``{label, waveform, frequency, amplitude, phase, offset}``
      - Raw data:           ``{label, time, values}``

    Set ``overlay=True`` to plot all channels on the same axes.

    The plot is rendered with Pillow (no matplotlib needed) and saved as PNG.
    Returns the file path and a base64-encoded preview of the image.
    """
    from PIL import Image, ImageDraw, ImageFont
    import base64
    from io import BytesIO

    if not channels:
        return _err("channels list is empty", "E3_BAD_CHANNELS")

    # ── Generate data for computed channels ─────────────────
    for ch in channels:
        if "values" in ch and ch["values"]:
            # Raw data provided — validate
            if "time" not in ch or not ch["time"]:
                n = len(ch["values"])
                ch["time"] = [i / sample_rate for i in range(n)]
            continue

        # Computed waveform
        wf = ch.get("waveform", "sine").lower()
        freq = ch.get("frequency", 1000.0)
        amp = ch.get("amplitude", 1.0)
        phase_deg = ch.get("phase", 0.0)
        offset = ch.get("offset", 0.0)
        duty = ch.get("duty_cycle", 0.5)

        samples = _generate_waveform(
            wf, freq, amp, offset, duty, phase_deg, sample_rate, duration,
        )
        ch["values"] = samples
        ch["time"] = [i / sample_rate for i in range(len(samples))]

    # ── Compute measurements per channel ────────────────────
    for ch in channels:
        vals = ch.get("values", [])
        n = len(vals)
        if n == 0:
            ch["measurements"] = {}
            continue
        peak = max(vals)
        valley = min(vals)
        mean = sum(vals) / n
        rms = math.sqrt(sum(v ** 2 for v in vals) / n)
        meas: dict[str, Any] = {
            "peak": peak,
            "valley": valley,
            "vpp": peak - valley,
            "mean": mean,
            "rms": rms,
        }
        # Frequency estimate
        if n > 2:
            crossings = 0
            t = ch["time"]
            for i in range(1, n):
                if (vals[i - 1] - mean) * (vals[i] - mean) < 0:
                    crossings += 1
            if crossings > 1 and len(t) > 1:
                total_time = t[-1] - t[0]
                if total_time > 0:
                    meas["estimated_frequency"] = crossings / (2.0 * total_time)
        ch["measurements"] = meas

    # ── Render with Pillow ──────────────────────────────────
    active = [ch for ch in channels if ch.get("values")]
    if not active:
        return _err("All channels are empty", "E3_NO_DATA")

    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 80, 40, 50, 40
    W = width

    if overlay:
        n_panels = 1
    else:
        n_panels = len(active)
    total_h = MARGIN_T + n_panels * height_per_channel + MARGIN_B
    img = Image.new("RGB", (W, total_h), color=(26, 26, 46))
    draw = ImageDraw.Draw(img)

    try:
        font_label = ImageFont.truetype("arial.ttf", 13)
        font_title = ImageFont.truetype("arial.ttf", 18)
        font_small = ImageFont.truetype("arial.ttf", 11)
    except (IOError, OSError):
        font_label = ImageFont.load_default()
        font_title = font_label
        font_small = font_label

    # Title
    draw.text((W // 2 - len(title) * 5, 12), title, fill=(0, 212, 255), font=font_title)

    colors = [
        (255, 215, 0), (0, 255, 127), (0, 191, 255), (255, 105, 180),
        (255, 99, 71), (147, 112, 219), (50, 205, 50), (255, 165, 0),
    ]

    def _draw_channel(ch_data, panel_idx, color, y_top, y_bot, v_min_override=None, v_max_override=None):
        values = ch_data["values"]
        label = ch_data.get("label", ch_data.get("name", f"CH{panel_idx+1}"))
        measurements = ch_data.get("measurements", {})

        x_left, x_right = MARGIN_L, W - MARGIN_R
        plot_w = x_right - x_left
        plot_h = y_bot - y_top

        if not overlay or panel_idx == 0:
            draw.rectangle([x_left, y_top, x_right, y_bot], fill=(13, 17, 23))
            for gi in range(1, 10):
                gx = x_left + int(plot_w * gi / 10)
                draw.line([(gx, y_top), (gx, y_bot)], fill=(50, 50, 70))
            for gi in range(1, 8):
                gy = y_top + int(plot_h * gi / 8)
                draw.line([(x_left, gy), (x_right, gy)], fill=(50, 50, 70))
            draw.rectangle([x_left, y_top, x_right, y_bot], outline=(60, 60, 80))

        # Label
        label_y = y_top + 4 + panel_idx * 16 if overlay else y_top + 4
        draw.text((8, label_y), label, fill=color, font=font_label)

        n = len(values)
        if n < 2:
            return

        v_min = v_min_override if v_min_override is not None else min(values)
        v_max = v_max_override if v_max_override is not None else max(values)
        v_range = v_max - v_min
        if v_range < 1e-15:
            v_range = 1.0; v_min = values[0] - 0.5

        points = []
        for i in range(n):
            px = x_left + int(plot_w * i / (n - 1))
            py = y_bot - int(plot_h * (values[i] - v_min) / v_range)
            points.append((px, py))

        step = max(1, len(points) // plot_w)
        ds = points[::step]
        for i in range(len(ds) - 1):
            draw.line([ds[i], ds[i + 1]], fill=color, width=2)

        if not overlay or panel_idx == 0:
            draw.text((x_left - 70, y_top), f"{_format_eng(v_max)}V", fill=(180, 180, 180), font=font_small)
            draw.text((x_left - 70, y_bot - 12), f"{_format_eng(v_min)}V", fill=(180, 180, 180), font=font_small)

        info_parts = []
        if "vpp" in measurements:
            info_parts.append(f"Vpp={_format_eng(measurements['vpp'])}V")
        if "estimated_frequency" in measurements:
            info_parts.append(f"f≈{_format_eng(measurements['estimated_frequency'])}Hz")
        if info_parts:
            info_y = y_top + 4 + (panel_idx * 16 if overlay else 0)
            info_x = x_left + 8 + len(label) * 8 + 20
            draw.text((info_x, info_y), "  ".join(info_parts), fill=(200, 200, 160), font=font_small)

    if overlay:
        # All channels share one panel
        y_top = MARGIN_T + 10
        y_bot = y_top + height_per_channel - 30
        all_vals = [v for ch in active for v in ch["values"]]
        v_min_all = min(all_vals)
        v_max_all = max(all_vals)
        for ci, ch in enumerate(active):
            _draw_channel(ch, ci, colors[ci % len(colors)], y_top, y_bot, v_min_all, v_max_all)
    else:
        for ci, ch in enumerate(active):
            y_top = MARGIN_T + ci * height_per_channel + 10
            y_bot = y_top + height_per_channel - 30
            _draw_channel(ch, ci, colors[ci % len(colors)], y_top, y_bot)

    # Time axis
    if active and active[0].get("time"):
        _, time_unit = _auto_scale_time(active[0]["time"])
        draw.text((W // 2 - 30, total_h - 30), f"Time ({time_unit})", fill=(180, 180, 180), font=font_label)

    # ── Save ────────────────────────────────────────────────
    if not output_path:
        out_dir = session.workspace_dir
        os.makedirs(out_dir, exist_ok=True)
        output_path = os.path.join(out_dir, "waveform_plot.png")
    else:
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    img.save(output_path, "PNG")

    # Base64 preview
    buf = BytesIO()
    img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    session.log_action(
        "plot_waveform",
        {"channels": len(active), "overlay": overlay},
        result_summary=f"{len(active)} ch → {output_path}",
    )

    # Build channel summaries for response
    ch_summaries = []
    for ch in active:
        ch_summaries.append({
            "label": ch.get("label", ch.get("name", "?")),
            "measurements": ch.get("measurements", {}),
        })

    return _ok({
        "plot_image": output_path,
        "image_base64": b64[:200] + "..." if len(b64) > 200 else b64,
        "channels": ch_summaries,
        "width": W,
        "height": total_h,
    })


def _auto_scale_time(time_data: list[float]) -> tuple[list[float], str]:
    """Scale time values to appropriate unit for display."""
    if not time_data:
        return time_data, "s"
    max_t = max(abs(t) for t in time_data) if time_data else 0
    if max_t == 0:
        return time_data, "s"
    if max_t < 1e-6:
        return [t * 1e9 for t in time_data], "ns"
    if max_t < 1e-3:
        return [t * 1e6 for t in time_data], "µs"
    if max_t < 1.0:
        return [t * 1e3 for t in time_data], "ms"
    return time_data, "s"


def _channel_color(index: int) -> str:
    """Return oscilloscope-style channel colors."""
    colors = ["#FFD700", "#00FF7F", "#00BFFF", "#FF69B4", "#FF6347", "#9370DB"]
    return colors[index % len(colors)]


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
            return f"{scaled:.3g}{prefix}"
    return f"{value:.3g}"
