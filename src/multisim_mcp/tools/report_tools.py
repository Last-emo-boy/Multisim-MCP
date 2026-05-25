"""
MCP Tools: Visual Simulation Report.

Generates an HTML report combining schematic image, oscilloscope waveform
plots, measurement tables, BOM, and netlist into a single self-contained file.
"""

from __future__ import annotations

import base64
import html
import os
from datetime import datetime
from typing import Any

from ..com_adapter import MultisimCOMError
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


def _img_to_base64(path: str) -> str | None:
    """Read an image file and return base64-encoded data URI."""
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "bmp": "image/bmp"}.get(
        ext.lstrip("."), "image/png"
    )
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


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


def tool_simulation_report(
    session: SessionManager,
    output_path: str,
    title: str = "Multisim Simulation Report",
    description: str = "",
    schematic_image: str = "",
    waveform_images: list[str] | None = None,
    channel_data: list[dict] | None = None,
    include_bom: bool = True,
    include_netlist: bool = True,
) -> dict:
    """Generate a self-contained HTML simulation report.

    Combines schematic images, oscilloscope waveform plots, measurement
    data, BOM, and netlist into a single HTML file with embedded images.

    Args:
        output_path: Where to save the HTML report.
        title: Report title.
        description: Optional circuit/analysis description.
        schematic_image: Path to schematic image (from export_circuit_image/create_snippet).
        waveform_images: List of paths to waveform plot images (from oscilloscope tool).
        channel_data: List of channel dicts with 'name' and 'measurements' keys
                      (from oscilloscope tool response).
        include_bom: Whether to include Bill of Materials.
        include_netlist: Whether to include circuit netlist.
    """
    if not output_path:
        return _err("output_path is required", "E6_MISSING_PATH")

    sections: list[str] = []

    # ── Header ──────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Schematic ───────────────────────────────────────────
    if schematic_image:
        b64 = _img_to_base64(schematic_image)
        if b64:
            sections.append(
                f'<div class="section">'
                f'<h2>Circuit Schematic</h2>'
                f'<img src="{b64}" class="schematic" alt="Circuit Schematic">'
                f'</div>'
            )

    # ── Waveforms ───────────────────────────────────────────
    if waveform_images:
        img_tags = []
        for img_path in waveform_images:
            b64 = _img_to_base64(img_path)
            if b64:
                img_tags.append(f'<img src="{b64}" class="waveform" alt="Waveform">')
        if img_tags:
            sections.append(
                f'<div class="section">'
                f'<h2>Waveform Captures</h2>'
                + "\n".join(img_tags) +
                f'</div>'
            )

    # ── Measurements Table ──────────────────────────────────
    if channel_data:
        rows = []
        for ch in channel_data:
            name = html.escape(ch.get("name", "—"))
            m = ch.get("measurements", {})
            row_cells = [
                f"<td>{name}</td>",
                f"<td>{_format_eng(m.get('peak', 0))}V</td>",
                f"<td>{_format_eng(m.get('valley', 0))}V</td>",
                f"<td>{_format_eng(m.get('vpp', 0))}V</td>",
                f"<td>{_format_eng(m.get('rms', 0))}V</td>",
                f"<td>{_format_eng(m.get('mean', 0))}V</td>",
            ]
            freq = m.get("estimated_frequency")
            if freq is not None:
                row_cells.append(f"<td>{_format_eng(freq)}Hz</td>")
            else:
                row_cells.append("<td>—</td>")
            rows.append("<tr>" + "".join(row_cells) + "</tr>")

        sections.append(
            '<div class="section">'
            '<h2>Measurement Summary</h2>'
            '<table>'
            '<thead><tr>'
            '<th>Channel</th><th>Peak</th><th>Valley</th>'
            '<th>Vpp</th><th>RMS</th><th>DC Mean</th><th>Frequency</th>'
            '</tr></thead>'
            '<tbody>' + "\n".join(rows) + '</tbody>'
            '</table>'
            '</div>'
        )

    # ── BOM ─────────────────────────────────────────────────
    if include_bom:
        try:
            bom_text = session.adapter.report_bom(real_flag=False)
            if bom_text:
                sections.append(
                    '<div class="section">'
                    '<h2>Bill of Materials</h2>'
                    f'<pre>{html.escape(bom_text)}</pre>'
                    '</div>'
                )
        except (MultisimCOMError, Exception):
            pass  # BOM not available — skip

    # ── Netlist ─────────────────────────────────────────────
    if include_netlist:
        try:
            netlist_text = session.adapter.report_netlist(probes_flag=True)
            if netlist_text:
                sections.append(
                    '<div class="section">'
                    '<h2>Circuit Netlist</h2>'
                    f'<pre>{html.escape(netlist_text)}</pre>'
                    '</div>'
                )
        except (MultisimCOMError, Exception):
            pass  # Netlist not available — skip

    # ── Assemble HTML ───────────────────────────────────────
    desc_html = f'<p class="description">{html.escape(description)}</p>' if description else ""

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(title)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #1a1a2e; color: #e0e0e0; padding: 24px;
    max-width: 1200px; margin: 0 auto;
  }}
  h1 {{
    color: #00d4ff; font-size: 28px; margin-bottom: 4px;
    border-bottom: 2px solid #00d4ff; padding-bottom: 8px;
  }}
  .timestamp {{ color: #888; font-size: 12px; margin-bottom: 16px; }}
  .description {{ color: #b0b0b0; margin-bottom: 20px; font-style: italic; }}
  .section {{
    background: #16213e; border-radius: 8px; padding: 20px;
    margin-bottom: 20px; border: 1px solid #0f3460;
  }}
  h2 {{ color: #e94560; font-size: 20px; margin-bottom: 12px; }}
  img.schematic, img.waveform {{
    max-width: 100%; border-radius: 4px; border: 1px solid #333;
    margin-bottom: 8px; display: block;
  }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 14px;
  }}
  th {{
    background: #0f3460; color: #00d4ff; padding: 10px 12px;
    text-align: left; border: 1px solid #1a1a3e;
  }}
  td {{
    padding: 8px 12px; border: 1px solid #1a1a3e;
  }}
  tr:nth-child(even) {{ background: #1a1a3e; }}
  tr:hover {{ background: #1f2b50; }}
  pre {{
    background: #0d1117; padding: 16px; border-radius: 4px;
    overflow-x: auto; font-size: 12px; line-height: 1.5;
    color: #c9d1d9; border: 1px solid #30363d;
    max-height: 400px; overflow-y: auto;
  }}
  .footer {{
    text-align: center; color: #555; font-size: 11px;
    margin-top: 24px; padding-top: 12px; border-top: 1px solid #333;
  }}
</style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="timestamp">Generated: {timestamp}</div>
  {desc_html}
  {"".join(sections)}
  <div class="footer">Generated by Multisim MCP Server</div>
</body>
</html>"""

    # ── Write file ──────────────────────────────────────────
    try:
        abs_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(report_html)
    except Exception as exc:
        return _err(f"Failed to write report: {exc}", "E6_WRITE_FAILED")

    session.log_action(
        "simulation_report",
        {"output_path": abs_path, "sections": len(sections)},
        result_summary=f"HTML report with {len(sections)} sections",
    )

    return _ok({
        "report_path": abs_path,
        "sections_count": len(sections),
        "has_schematic": bool(schematic_image),
        "has_waveforms": bool(waveform_images),
        "has_measurements": bool(channel_data),
        "has_bom": include_bom,
        "has_netlist": include_netlist,
    })
