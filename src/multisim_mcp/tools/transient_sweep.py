"""
MCP Tools: Transient Parameter Sweep.

Runs transient analysis across multiple parameter variants in a single
workflow, returning labeled waveforms, structured measurements, and
optional multi-variant overlay plots.

Fills the gap where parameter_sweep only supports OP/single-point
measurements, but users need complete waveforms for each variant.
"""

from __future__ import annotations

import os
import re
from typing import Any

import math

from ..models import ToolResponse
from ..session import SessionManager
from .spice_tools import tool_run_spice, _set_value_in_netlist
from .signal_measure import compute_measurements


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


def tool_transient_sweep(
    session: SessionManager,
    netlist: str,
    component: str,
    values: list[float],
    outputs: list[str],
    stop_time: float = 0.005,
    time_step: float = 1e-6,
    measurements: list[str] | None = None,
    plot: bool = True,
    overlay: bool = True,
    output_dir: str = "",
    title: str = "Transient Sweep",
    timeout_ms: int = 60000,
) -> dict:
    """Run transient analysis across multiple parameter variants.

    For each value of the swept component, runs a full transient simulation
    and collects complete waveforms. Returns labeled results with automatic
    measurements and optional overlay plots.

    Unlike ``parameter_sweep`` (which only returns scalar OP results),
    this tool returns full time-series data for each variant.

    Example — sweep feedback resistor in inverting amp:
        netlist: "Vi in 0 SIN(0 0.1 1000)\\nR1 in inv 10000\\nRf inv out 10000\\nE1 out 0 0 inv 200000\\n.end"
        component: "Rf"
        values: [10000, 20000, 47000, 100000]
        outputs: ["$out"]
        stop_time: 0.005
        → For each Rf value: waveform data, Vpp, gain, peak/valley, etc.

    Args:
        netlist: SPICE netlist (must end with .end)
        component: Component name to sweep (e.g., "Rf", "R1")
        values: List of values in SI units
        outputs: Node voltages to capture (e.g., ["$out", "$in"])
        stop_time: Simulation stop time in seconds
        time_step: Simulation time step in seconds
        measurements: Metrics to compute — vpp, peak, valley, rms, mean, gain,
                      frequency, rise_time, fall_time, overshoot, settling_time.
                      None = compute all available.
        plot: Whether to generate waveform plot images
        overlay: If True, overlay all variants per output on one plot
        output_dir: Directory for plots (default: temp dir)
        title: Plot/report title
        timeout_ms: Per-variant timeout in ms
    """
    if not values:
        return _err("values list is empty", "E8_BAD_SWEEP")
    if not outputs:
        return _err("outputs list is empty", "E8_BAD_SWEEP")
    if not netlist or not netlist.strip():
        return _err("netlist is empty", "E8_BAD_SWEEP")

    if not output_dir:
        output_dir = r"C:\mcp_spice_tmp"
    os.makedirs(output_dir, exist_ok=True)

    tran_cmd = f"tran {time_step} {stop_time}"
    print_cmd = "print " + " ".join(outputs)

    variants: list[dict] = []
    all_waveforms: dict[str, list[dict]] = {out: [] for out in outputs}
    # also capture input if $in is in outputs
    reference_input: dict | None = None

    for val_idx, val in enumerate(values):
        variant_label = f"{component}={_format_eng(val)}"

        # Modify netlist for this variant
        mod_netlist = _set_value_in_netlist(netlist, component, val)

        # Run transient
        result = tool_run_spice(session, mod_netlist, [tran_cmd, print_cmd], timeout_ms)

        variant_entry: dict[str, Any] = {
            "variant": variant_label,
            "component": component,
            "value": val,
            "value_display": _format_eng(val),
            "index": val_idx,
        }

        if not result["ok"]:
            variant_entry["error"] = result.get("error_message", "Simulation failed")
            variant_entry["waveforms"] = {}
            variant_entry["measurements"] = {}
            variants.append(variant_entry)
            continue

        parsed = result["data"].get("results", [])
        if not parsed:
            variant_entry["error"] = "No results from simulation"
            variant_entry["waveforms"] = {}
            variant_entry["measurements"] = {}
            variants.append(variant_entry)
            continue

        # Take the first transient result
        tran_data = parsed[0]
        time_arr = tran_data.get("time", [])

        waveform_data: dict[str, dict] = {}
        measurement_data: dict[str, dict] = {}

        for out_name in outputs:
            signal = tran_data.get(out_name, [])
            if not signal:
                continue

            waveform_data[out_name] = {
                "time": time_arr,
                "values": signal,
                "num_points": len(signal),
            }

            # Compute measurements
            meas = compute_measurements(
                time_arr, signal,
                metrics=measurements,
            )
            measurement_data[out_name] = meas

            # Collect for overlay plot
            all_waveforms[out_name].append({
                "label": variant_label,
                "time": time_arr,
                "values": signal,
                "measurements": meas,
            })

        # Compute inter-signal gain if both $in and $out present
        if "$in" in measurement_data and "$out" in measurement_data:
            in_vpp = measurement_data["$in"].get("vpp", 0)
            out_vpp = measurement_data["$out"].get("vpp", 0)
            if in_vpp and abs(in_vpp) > 1e-15:
                gain = out_vpp / in_vpp
                measurement_data["_gain"] = {
                    "voltage_gain": gain,
                    "gain_db": 20 * math.log10(abs(gain)) if gain != 0 else float("-inf"),
                }

        variant_entry["waveforms"] = waveform_data
        variant_entry["measurements"] = measurement_data
        variants.append(variant_entry)

    # ── Generate overlay plots ──────────────────────────────
    plot_paths: list[str] = []
    if plot and any(all_waveforms[o] for o in outputs):
        try:
            plot_paths = _generate_sweep_plots(
                all_waveforms, outputs, title, output_dir, overlay,
            )
        except Exception:
            pass  # Non-fatal

    # ── Build summary table ─────────────────────────────────
    summary_table: list[dict] = []
    for v in variants:
        row: dict[str, Any] = {
            "variant": v["variant"],
            "value": v["value"],
        }
        if "error" in v:
            row["error"] = v["error"]
        else:
            for out_name in outputs:
                meas = v.get("measurements", {}).get(out_name, {})
                for key in ["vpp", "peak", "valley", "rms", "mean", "frequency"]:
                    if key in meas:
                        row[f"{out_name}_{key}"] = meas[key]
            if "_gain" in v.get("measurements", {}):
                row["voltage_gain"] = v["measurements"]["_gain"]["voltage_gain"]
                row["gain_db"] = v["measurements"]["_gain"]["gain_db"]
        summary_table.append(row)

    session.log_action(
        "transient_sweep",
        {"component": component, "num_variants": len(values)},
        result_summary=f"{len(variants)} variants, {len(plot_paths)} plots",
    )

    return _ok({
        "variants": variants,
        "summary_table": summary_table,
        "plot_images": plot_paths,
        "component_swept": component,
        "values_swept": values,
        "outputs_measured": outputs,
        "analysis": f"tran {time_step} {stop_time}",
    })


def _generate_sweep_plots(
    all_waveforms: dict[str, list[dict]],
    outputs: list[str],
    title: str,
    output_dir: str,
    overlay: bool,
) -> list[str]:
    """Generate waveform plot images for sweep results."""
    paths: list[str] = []

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        has_mpl = True
    except ImportError:
        has_mpl = False

    if has_mpl:
        return _plot_sweep_matplotlib(all_waveforms, outputs, title, output_dir, overlay)
    else:
        return _plot_sweep_pillow(all_waveforms, outputs, title, output_dir, overlay)


def _plot_sweep_matplotlib(
    all_waveforms: dict[str, list[dict]],
    outputs: list[str],
    title: str,
    output_dir: str,
    overlay: bool,
) -> list[str]:
    """Plot sweep results using matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths: list[str] = []
    colors = ["#FFD700", "#00FF7F", "#00BFFF", "#FF69B4", "#FF6347", "#7B68EE", "#00CED1", "#FF8C00"]

    if overlay:
        # One plot per output with all variants overlaid
        for out_name in outputs:
            waveforms = all_waveforms.get(out_name, [])
            if not waveforms:
                continue

            fig, ax = plt.subplots(figsize=(12, 5))
            ax.set_title(f"{title} — {out_name}", fontsize=14, fontweight="bold")

            # Compute global Y range across all variants for normalized comparison
            global_min = min(min(wf["values"]) for wf in waveforms if wf["values"])
            global_max = max(max(wf["values"]) for wf in waveforms if wf["values"])
            y_margin = (global_max - global_min) * 0.05 if global_max > global_min else 0.1

            for i, wf in enumerate(waveforms):
                time_ms = [t * 1000 for t in wf["time"]]
                color = colors[i % len(colors)]
                label = wf["label"]
                meas = wf.get("measurements", {})
                vpp = meas.get("vpp")
                if vpp is not None:
                    label += f" (Vpp={_format_eng(vpp)}V)"
                ax.plot(time_ms, wf["values"], linewidth=1.2, color=color, label=label)

            ax.set_ylim(global_min - y_margin, global_max + y_margin)
            ax.set_xlabel("Time (ms)", fontsize=11)
            ax.set_ylabel("Voltage (V)", fontsize=11)
            ax.legend(loc="upper right", fontsize=9)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()

            safe_name = out_name.replace("$", "").replace("/", "_")
            path = os.path.join(output_dir, f"sweep_{safe_name}_overlay.png")
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            paths.append(path)
    else:
        # Separate subplot per variant
        for out_name in outputs:
            waveforms = all_waveforms.get(out_name, [])
            if not waveforms:
                continue

            n = len(waveforms)
            fig, axes = plt.subplots(n, 1, figsize=(12, 3 * n), sharex=True, squeeze=False)
            fig.suptitle(f"{title} — {out_name}", fontsize=14, fontweight="bold")

            for i, wf in enumerate(waveforms):
                ax = axes[i][0]
                time_ms = [t * 1000 for t in wf["time"]]
                color = colors[i % len(colors)]
                ax.plot(time_ms, wf["values"], linewidth=1.0, color=color)
                ax.set_ylabel(wf["label"], fontsize=10)
                ax.grid(True, alpha=0.3)
                meas = wf.get("measurements", {})
                info = []
                for k in ["vpp", "peak", "valley", "rms"]:
                    if k in meas:
                        info.append(f"{k}={_format_eng(meas[k])}V")
                if info:
                    ax.text(0.02, 0.95, "  ".join(info), transform=ax.transAxes,
                            fontsize=8, va="top",
                            bbox=dict(boxstyle="round,pad=0.3", facecolor="wheat", alpha=0.7))

            axes[-1][0].set_xlabel("Time (ms)")
            plt.tight_layout()

            safe_name = out_name.replace("$", "").replace("/", "_")
            path = os.path.join(output_dir, f"sweep_{safe_name}_panels.png")
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            paths.append(path)

    return paths


def _plot_sweep_pillow(
    all_waveforms: dict[str, list[dict]],
    outputs: list[str],
    title: str,
    output_dir: str,
    overlay: bool,
) -> list[str]:
    """Fallback sweep plotter using Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    paths: list[str] = []
    W = 1200
    colors = [(255, 215, 0), (0, 255, 127), (0, 191, 255), (255, 105, 180),
              (255, 99, 71), (123, 104, 238), (0, 206, 209), (255, 140, 0)]

    try:
        font = ImageFont.truetype("arial.ttf", 12)
        font_title = ImageFont.truetype("arial.ttf", 16)
    except (IOError, OSError):
        font = ImageFont.load_default()
        font_title = font

    for out_name in outputs:
        waveforms = all_waveforms.get(out_name, [])
        if not waveforms:
            continue

        n_ch = len(waveforms) if not overlay else 1
        H_PER = 250
        MARGIN_T, MARGIN_B, MARGIN_L, MARGIN_R = 50, 40, 80, 40
        total_h = MARGIN_T + n_ch * H_PER + MARGIN_B
        img = Image.new("RGB", (W, total_h), color=(20, 22, 30))
        draw = ImageDraw.Draw(img)

        draw.text((W // 2 - 100, 12), f"{title} — {out_name}",
                  fill=(0, 212, 255), font=font_title)

        if overlay:
            # All waveforms on one panel
            y_top = MARGIN_T + 10
            y_bot = y_top + H_PER - 30
            x_left, x_right = MARGIN_L, W - MARGIN_R
            plot_w, plot_h = x_right - x_left, y_bot - y_top

            draw.rectangle([x_left, y_top, x_right, y_bot], fill=(13, 17, 23), outline=(60, 60, 80))

            # Find global min/max
            all_vals = []
            for wf in waveforms:
                all_vals.extend(wf["values"])
            v_min, v_max = min(all_vals), max(all_vals)
            v_range = v_max - v_min
            if v_range < 1e-15:
                v_range = 1.0

            for wi, wf in enumerate(waveforms):
                color = colors[wi % len(colors)]
                vals = wf["values"]
                n = len(vals)
                step = max(1, n // plot_w)
                pts = []
                for i in range(0, n, step):
                    px = x_left + int(plot_w * i / max(n - 1, 1))
                    py = y_bot - int(plot_h * (vals[i] - v_min) / v_range)
                    pts.append((px, py))
                for i in range(len(pts) - 1):
                    draw.line([pts[i], pts[i + 1]], fill=color, width=2)

                # Legend entry
                ly = y_top + 5 + wi * 16
                draw.rectangle([x_left + 5, ly, x_left + 15, ly + 10], fill=color)
                draw.text((x_left + 20, ly - 2), wf["label"], fill=(200, 200, 200), font=font)
        else:
            # Separate panels per variant
            for wi, wf in enumerate(waveforms):
                y_top = MARGIN_T + wi * H_PER + 10
                y_bot = y_top + H_PER - 30
                x_left, x_right = MARGIN_L, W - MARGIN_R
                plot_w, plot_h = x_right - x_left, y_bot - y_top

                draw.rectangle([x_left, y_top, x_right, y_bot], fill=(13, 17, 23), outline=(60, 60, 80))

                vals = wf["values"]
                n = len(vals)
                v_min, v_max = min(vals), max(vals)
                v_range = v_max - v_min
                if v_range < 1e-15:
                    v_range = 1.0

                color = colors[wi % len(colors)]
                step = max(1, n // plot_w)
                pts = []
                for i in range(0, n, step):
                    px = x_left + int(plot_w * i / max(n - 1, 1))
                    py = y_bot - int(plot_h * (vals[i] - v_min) / v_range)
                    pts.append((px, py))
                for i in range(len(pts) - 1):
                    draw.line([pts[i], pts[i + 1]], fill=color, width=2)

                draw.text((8, y_top + 4), wf["label"], fill=color, font=font)

        safe_name = out_name.replace("$", "").replace("/", "_")
        mode = "overlay" if overlay else "panels"
        path = os.path.join(output_dir, f"sweep_{safe_name}_{mode}.png")
        img.save(path, "PNG")
        paths.append(path)

    return paths
