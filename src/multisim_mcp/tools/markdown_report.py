"""
MCP Tools: Markdown Lab Report Generator.

Generates a complete Markdown lab report from structured inputs: title,
experiment conditions, circuit netlist, schematic/waveform images,
measurement tables, and analysis conclusions.

Designed for the workflow:
    build_netlist → render_netlist_schematic → transient_sweep → measure_signals
    → generate_markdown_report
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
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


def _img_reference(path: str, embed: bool, alt: str = "Image") -> str:
    """Generate markdown image reference, optionally embedding as base64."""
    if embed and os.path.isfile(path):
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
        return f"![{alt}](data:{mime};base64,{data})"
    else:
        return f"![{alt}]({path})"


def tool_generate_markdown_report(
    output_path: str,
    title: str = "实验报告",
    experiment_purpose: str = "",
    experiment_conditions: list[dict] | None = None,
    netlist: str = "",
    schematic_image: str = "",
    waveform_images: list[str] | None = None,
    measurement_table: list[dict] | None = None,
    sweep_summary: list[dict] | None = None,
    analysis_text: str = "",
    conclusion: str = "",
    extra_sections: list[dict] | None = None,
    embed_images: bool = False,
    language: str = "zh",
) -> dict:
    """Generate a complete Markdown lab report from structured inputs.

    Combines all simulation artifacts — schematic images, waveform plots,
    measurement data, netlists — into a publication-ready Markdown document.

    Workflow:
    1. ``build_netlist`` → get netlist
    2. ``render_netlist_schematic`` → get schematic image
    3. ``transient_sweep`` → get waveform images + measurements
    4. ``generate_markdown_report(...)`` → complete .md report

    Example — inverting amplifier lab report:
        generate_markdown_report(
            output_path="report.md",
            title="反相放大器实验报告",
            experiment_purpose="验证反相放大器增益与反馈电阻的关系",
            experiment_conditions=[
                {name: "输入信号", value: "正弦波 1kHz, 100mV"},
                {name: "R1", value: "10kΩ"},
                {name: "Rf扫描值", value: "10k/20k/47k/100kΩ"},
            ],
            netlist: "Vi in 0 SIN(...)\\n...",
            schematic_image: "schematic.png",
            waveform_images: ["sweep_out_overlay.png"],
            sweep_summary: [
                {variant: "Rf=10k", "$out_vpp": 0.2, voltage_gain: -1.0},
                {variant: "Rf=20k", "$out_vpp": 0.4, voltage_gain: -2.0},
            ],
            conclusion: "实测增益与理论值 -Rf/R1 一致",
        )

    Args:
        output_path: File path for the generated .md file.
        title: Report title.
        experiment_purpose: Purpose / objective of the experiment.
        experiment_conditions: List of {name, value} dicts for experiment parameters.
        netlist: SPICE netlist text to include in the report.
        schematic_image: Path to circuit schematic image.
        waveform_images: List of waveform plot image paths.
        measurement_table: List of dicts — each dict is a row with arbitrary columns.
        sweep_summary: Summary table from transient_sweep (auto-formatted).
        analysis_text: Free-form analysis / discussion text.
        conclusion: Experiment conclusion text.
        extra_sections: Additional sections [{title, content}].
        embed_images: If True, embed images as base64 data URIs.
        language: Report language — "zh" (Chinese) or "en" (English).
    """
    if not output_path:
        return _err("output_path is required", "E10_MISSING_PATH")

    # Language labels
    if language == "zh":
        labels = {
            "toc": "目录",
            "purpose": "一、实验目的",
            "conditions": "二、实验条件",
            "schematic": "三、电路原理图",
            "netlist": "四、SPICE 网表",
            "waveforms": "五、仿真波形",
            "measurements": "六、测量数据",
            "analysis": "七、数据分析",
            "conclusion": "八、实验结论",
            "appendix": "附录",
            "name_col": "参数",
            "value_col": "值",
            "generated": "本报告由 Multisim MCP 自动生成",
            "date": "日期",
        }
    else:
        labels = {
            "toc": "Table of Contents",
            "purpose": "1. Experiment Purpose",
            "conditions": "2. Experiment Conditions",
            "schematic": "3. Circuit Schematic",
            "netlist": "4. SPICE Netlist",
            "waveforms": "5. Simulation Waveforms",
            "measurements": "6. Measurement Data",
            "analysis": "7. Analysis",
            "conclusion": "8. Conclusion",
            "appendix": "Appendix",
            "name_col": "Parameter",
            "value_col": "Value",
            "generated": "Generated by Multisim MCP",
            "date": "Date",
        }

    sections: list[str] = []
    section_number = 0

    # ── Title & header ──────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections.append(f"# {title}\n")
    sections.append(f"> {labels['generated']}  ")
    sections.append(f"> {labels['date']}: {timestamp}\n")

    # ── Experiment purpose ──────────────────────────────────
    if experiment_purpose:
        sections.append(f"## {labels['purpose']}\n")
        sections.append(f"{experiment_purpose}\n")

    # ── Experiment conditions ───────────────────────────────
    if experiment_conditions:
        sections.append(f"## {labels['conditions']}\n")
        sections.append(f"| {labels['name_col']} | {labels['value_col']} |")
        sections.append("|:---|:---|")
        for cond in experiment_conditions:
            name = cond.get("name", "")
            value = cond.get("value", "")
            sections.append(f"| {name} | {value} |")
        sections.append("")

    # ── Circuit schematic ───────────────────────────────────
    if schematic_image:
        sections.append(f"## {labels['schematic']}\n")
        sections.append(_img_reference(schematic_image, embed_images, "Circuit Schematic"))
        sections.append("")

    # ── SPICE netlist ───────────────────────────────────────
    if netlist:
        sections.append(f"## {labels['netlist']}\n")
        sections.append("```spice")
        sections.append(netlist.strip())
        sections.append("```\n")

    # ── Waveform images ─────────────────────────────────────
    if waveform_images:
        sections.append(f"## {labels['waveforms']}\n")
        for i, img_path in enumerate(waveform_images):
            sections.append(_img_reference(img_path, embed_images, f"Waveform {i + 1}"))
            sections.append("")

    # ── Measurement table ───────────────────────────────────
    has_data = bool(measurement_table or sweep_summary)
    if has_data:
        sections.append(f"## {labels['measurements']}\n")

    if sweep_summary:
        # Auto-format sweep summary table
        if sweep_summary:
            # Collect all column keys
            all_keys: list[str] = []
            for row in sweep_summary:
                for k in row:
                    if k not in all_keys:
                        all_keys.append(k)

            # Pretty column headers
            header_map = {
                "variant": "Variant",
                "value": "Value",
                "$out_vpp": "Vout_pp",
                "$out_peak": "Vout_peak",
                "$out_valley": "Vout_valley",
                "$out_rms": "Vout_RMS",
                "$out_mean": "Vout_mean",
                "$out_frequency": "Frequency",
                "$in_vpp": "Vin_pp",
                "$in_rms": "Vin_RMS",
                "voltage_gain": "Gain (Av)",
                "gain_db": "Gain (dB)",
                "error": "Error",
            }

            display_keys = [k for k in all_keys if k != "error" or any(r.get("error") for r in sweep_summary)]
            headers = [header_map.get(k, k) for k in display_keys]

            sections.append("| " + " | ".join(headers) + " |")
            sections.append("|" + "|".join(":---" for _ in headers) + "|")

            for row in sweep_summary:
                cells: list[str] = []
                for k in display_keys:
                    v = row.get(k, "—")
                    if isinstance(v, float):
                        if "gain" in k.lower() and "db" not in k.lower():
                            cells.append(f"{v:.2f}")
                        elif "db" in k.lower():
                            cells.append(f"{v:.1f}")
                        else:
                            cells.append(f"{_format_eng(v)}")
                    else:
                        cells.append(str(v))
                sections.append("| " + " | ".join(cells) + " |")
            sections.append("")

    if measurement_table:
        # Generic measurement table
        if measurement_table:
            all_keys = []
            for row in measurement_table:
                for k in row:
                    if k not in all_keys:
                        all_keys.append(k)

            sections.append("| " + " | ".join(all_keys) + " |")
            sections.append("|" + "|".join(":---" for _ in all_keys) + "|")
            for row in measurement_table:
                cells = []
                for k in all_keys:
                    v = row.get(k, "—")
                    if isinstance(v, float):
                        cells.append(f"{_format_eng(v)}")
                    else:
                        cells.append(str(v))
                sections.append("| " + " | ".join(cells) + " |")
            sections.append("")

    # ── Analysis ────────────────────────────────────────────
    if analysis_text:
        sections.append(f"## {labels['analysis']}\n")
        sections.append(f"{analysis_text}\n")

    # ── Conclusion ──────────────────────────────────────────
    if conclusion:
        sections.append(f"## {labels['conclusion']}\n")
        sections.append(f"{conclusion}\n")

    # ── Extra sections ──────────────────────────────────────
    if extra_sections:
        for sec in extra_sections:
            sec_title = sec.get("title", labels["appendix"])
            sec_content = sec.get("content", "")
            sections.append(f"## {sec_title}\n")
            sections.append(f"{sec_content}\n")

    # ── Assemble and write ──────────────────────────────────
    md_content = "\n".join(sections)

    abs_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return _ok({
        "path": abs_path,
        "size_bytes": os.path.getsize(abs_path),
        "sections_count": len([s for s in sections if s.startswith("## ")]),
    })
