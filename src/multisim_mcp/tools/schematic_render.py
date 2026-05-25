"""
MCP Tools: SPICE Netlist → Schematic Image Renderer.

Renders a SPICE netlist as a circuit schematic PNG image using Pillow.
This fills the gap where Multisim's COM API cannot render programmatically
loaded netlists (open_netlist + export_circuit_image produces blank images).

The renderer parses a SPICE netlist and draws standard schematic symbols
(resistors, capacitors, inductors, voltage sources, opamps/VCVS) with
automatic node-based placement and wire routing.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

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


# ── Netlist parsing ─────────────────────────────────────────

@dataclass
class SpiceComponent:
    """Parsed SPICE component."""
    refdes: str
    comp_type: str          # R, C, L, V, I, E, D, Q, A
    nodes: list[str]
    value: str = ""
    display_value: str = ""  # human-readable
    model: str = ""         # model name (for D, Q, A)


def _format_value(value_str: str, comp_type: str) -> str:
    """Format a numeric value with engineering prefix and unit."""
    units = {"R": "Ω", "C": "F", "L": "H", "V": "V", "I": "A"}
    unit = units.get(comp_type, "")
    # Try to parse as float
    try:
        val = float(value_str)
    except (ValueError, TypeError):
        return value_str  # non-numeric (e.g., "SIN(...)")

    if val == 0:
        return f"0{unit}"
    abs_val = abs(val)
    prefixes = [
        (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"),
        (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"),
    ]
    for threshold, prefix in prefixes:
        if abs_val >= threshold:
            scaled = val / threshold
            if scaled == int(scaled):
                return f"{int(scaled)}{prefix}{unit}"
            return f"{scaled:.3g}{prefix}{unit}"
    return f"{val:.3g}{unit}"


_SIN_RE = re.compile(r"SIN\s*\(\s*([^\s]+)\s+([^\s]+)\s+([^\s]+)", re.IGNORECASE)


def _parse_source_value(value_str: str) -> str:
    """Parse source value for display."""
    m = _SIN_RE.search(value_str)
    if m:
        offset, amp, freq = m.group(1), m.group(2), m.group(3)
        try:
            return f"SIN {_format_value(amp, 'V')}@{_format_value(freq, '')}"
        except Exception:
            pass
    if value_str.upper().startswith("DC "):
        try:
            return f"DC {_format_value(value_str[3:].strip(), 'V')}"
        except Exception:
            pass
    if value_str.upper().startswith("PULSE"):
        return "PULSE"
    return value_str


def parse_netlist(netlist: str) -> tuple[list[SpiceComponent], str, dict[str, str]]:
    """Parse a SPICE netlist into component list, title, and model map.

    Returns:
        (components, title, models) where models maps model_name → model_type.
    """
    components: list[SpiceComponent] = []
    title = "Circuit"
    models: dict[str, str] = {}  # model_name → type (e.g. "d", "npn", "d_and")

    for i, line in enumerate(netlist.split("\n")):
        stripped = line.strip()
        if not stripped:
            continue

        # Title line (first comment)
        if stripped.startswith("*"):
            if i == 0:
                title = stripped.lstrip("* ").strip() or title
            continue

        # .model lines — extract model name and type
        if stripped.lower().startswith(".model"):
            parts = stripped.split()
            if len(parts) >= 3:
                models[parts[1]] = parts[2].lower()
            continue

        # Skip other dot-commands
        if stripped.startswith("."):
            continue

        parts = stripped.split()
        if len(parts) < 3:
            continue

        refdes = parts[0]
        first_char = refdes[0].upper()

        if first_char == "R" and len(parts) >= 4:
            comp = SpiceComponent(
                refdes=refdes, comp_type="R",
                nodes=[parts[1], parts[2]], value=parts[3],
                display_value=_format_value(parts[3], "R"),
            )
            components.append(comp)
        elif first_char == "C" and len(parts) >= 4:
            comp = SpiceComponent(
                refdes=refdes, comp_type="C",
                nodes=[parts[1], parts[2]], value=parts[3],
                display_value=_format_value(parts[3], "C"),
            )
            components.append(comp)
        elif first_char == "L" and len(parts) >= 4:
            comp = SpiceComponent(
                refdes=refdes, comp_type="L",
                nodes=[parts[1], parts[2]], value=parts[3],
                display_value=_format_value(parts[3], "L"),
            )
            components.append(comp)
        elif first_char == "V" and len(parts) >= 4:
            value_str = " ".join(parts[3:])
            comp = SpiceComponent(
                refdes=refdes, comp_type="V",
                nodes=[parts[1], parts[2]], value=value_str,
                display_value=_parse_source_value(value_str),
            )
            components.append(comp)
        elif first_char == "I" and len(parts) >= 4:
            value_str = " ".join(parts[3:])
            comp = SpiceComponent(
                refdes=refdes, comp_type="I",
                nodes=[parts[1], parts[2]], value=value_str,
                display_value=_parse_source_value(value_str),
            )
            components.append(comp)
        elif first_char == "E" and len(parts) >= 6:
            # VCVS: E name out+ out- ctrl+ ctrl- gain
            gain = parts[5] if len(parts) > 5 else "1"
            comp = SpiceComponent(
                refdes=refdes, comp_type="E",
                nodes=[parts[1], parts[2], parts[3], parts[4]],
                value=gain,
                display_value=f"A={gain}",
            )
            components.append(comp)
        elif first_char == "D" and len(parts) >= 3:
            # Diode: D name anode cathode [model]
            model_name = parts[3] if len(parts) >= 4 else ""
            comp = SpiceComponent(
                refdes=refdes, comp_type="D",
                nodes=[parts[1], parts[2]],
                model=model_name,
                display_value=model_name or "D",
            )
            components.append(comp)
        elif first_char == "Q" and len(parts) >= 4:
            # BJT: Q name collector base emitter [model]
            model_name = parts[4] if len(parts) >= 5 else ""
            comp = SpiceComponent(
                refdes=refdes, comp_type="Q",
                nodes=[parts[1], parts[2], parts[3]],
                model=model_name,
                display_value=model_name or "Q",
            )
            components.append(comp)
        elif first_char == "M" and len(parts) >= 5:
            # MOSFET: M name drain gate source bulk [model]
            model_name = parts[5] if len(parts) >= 6 else ""
            comp = SpiceComponent(
                refdes=refdes, comp_type="M",
                nodes=[parts[1], parts[2], parts[3], parts[4]],
                model=model_name,
                display_value=model_name or "MOS",
            )
            components.append(comp)
        elif first_char == "A" and len(parts) >= 3:
            # XSPICE: A name [inputs] output model
            # Parse bracket-delimited input list
            line_rest = " ".join(parts[1:])
            bracket_m = re.match(r"\[([^\]]+)\]\s+(\S+)\s+(\S+)", line_rest)
            if bracket_m:
                inputs = bracket_m.group(1).split()
                output = bracket_m.group(2)
                model_name = bracket_m.group(3)
                comp = SpiceComponent(
                    refdes=refdes, comp_type="A",
                    nodes=inputs + [output],
                    model=model_name,
                    display_value=model_name,
                )
                components.append(comp)
            else:
                # Single input: A name input output model
                if len(parts) >= 4:
                    model_name = parts[-1]
                    nodes = parts[1:-1]
                    comp = SpiceComponent(
                        refdes=refdes, comp_type="A",
                        nodes=nodes,
                        model=model_name,
                        display_value=model_name,
                    )
                    components.append(comp)

    return components, title, models


# ── Schematic drawing ───────────────────────────────────────

# Layout constants
COMP_W = 120        # component symbol width
COMP_H = 60         # component symbol height
GRID_X = 220        # horizontal spacing between components
GRID_Y = 160        # vertical spacing between rows
MARGIN = 80         # canvas margin
WIRE_COLOR = (100, 200, 255)
COMP_COLOR = (255, 215, 0)
TEXT_COLOR = (220, 220, 220)
NODE_COLOR = (0, 255, 127)
GND_COLOR = (180, 180, 180)
BG_COLOR = (20, 22, 30)
GRID_COLOR = (35, 38, 48)
# Per-type accent colours (used for symbol outlines)
TYPE_COLORS: dict[str, tuple[int, int, int]] = {
    "R": (255, 215, 0),      # gold
    "C": (100, 180, 255),    # light blue
    "L": (180, 130, 255),    # purple
    "V": (0, 220, 120),      # green
    "I": (255, 160, 50),     # orange
    "D": (255, 100, 100),    # red
    "E": (0, 200, 255),      # cyan
    "Q": (220, 180, 100),    # tan
    "M": (160, 220, 100),    # lime
    "A": (100, 200, 255),    # sky blue
}


def _draw_resistor(draw, cx: int, cy: int, refdes: str, value: str, font, font_sm,
                   color: tuple[int, int, int] = COMP_COLOR):
    """Draw a resistor zigzag symbol."""
    x1, x2 = cx - COMP_W // 2, cx + COMP_W // 2
    # Left lead
    draw.line([(x1, cy), (x1 + 20, cy)], fill=color, width=2)
    # Zigzag
    zx = x1 + 20
    zw = COMP_W - 40
    n_zigs = 6
    seg = zw / n_zigs
    pts = [(zx, cy)]
    for i in range(n_zigs):
        if i % 2 == 0:
            pts.append((zx + seg * (i + 0.5), cy - 12))
        else:
            pts.append((zx + seg * (i + 0.5), cy + 12))
        pts.append((zx + seg * (i + 1), cy))
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=color, width=2)
    # Right lead
    draw.line([(x2 - 20, cy), (x2, cy)], fill=color, width=2)
    # Labels
    draw.text((cx - 20, cy - 30), refdes, fill=TEXT_COLOR, font=font)
    draw.text((cx - 20, cy + 14), value, fill=(180, 200, 255), font=font_sm)
    return (x1, cy), (x2, cy)


def _draw_capacitor(draw, cx: int, cy: int, refdes: str, value: str, font, font_sm,
                    color: tuple[int, int, int] = COMP_COLOR):
    """Draw a capacitor symbol (two parallel plates)."""
    x1, x2 = cx - COMP_W // 2, cx + COMP_W // 2
    gap = 8
    plate_h = 28
    # Left lead
    draw.line([(x1, cy), (cx - gap, cy)], fill=color, width=2)
    # Left plate
    draw.line([(cx - gap, cy - plate_h // 2), (cx - gap, cy + plate_h // 2)],
              fill=color, width=3)
    # Right plate
    draw.line([(cx + gap, cy - plate_h // 2), (cx + gap, cy + plate_h // 2)],
              fill=color, width=3)
    # Right lead
    draw.line([(cx + gap, cy), (x2, cy)], fill=color, width=2)
    # Labels
    draw.text((cx - 20, cy - 30), refdes, fill=TEXT_COLOR, font=font)
    draw.text((cx - 20, cy + 14), value, fill=(180, 200, 255), font=font_sm)
    return (x1, cy), (x2, cy)


def _draw_inductor(draw, cx: int, cy: int, refdes: str, value: str, font, font_sm,
                   color: tuple[int, int, int] = COMP_COLOR):
    """Draw an inductor symbol (humps)."""
    x1, x2 = cx - COMP_W // 2, cx + COMP_W // 2
    draw.line([(x1, cy), (x1 + 15, cy)], fill=color, width=2)
    # Humps
    hump_w = (COMP_W - 30) / 4
    for i in range(4):
        hx = x1 + 15 + hump_w * i
        bbox = [hx, cy - 14, hx + hump_w, cy + 2]
        draw.arc(bbox, 0, 180, fill=color, width=2)
    draw.line([(x2 - 15, cy), (x2, cy)], fill=color, width=2)
    # Labels
    draw.text((cx - 20, cy - 30), refdes, fill=TEXT_COLOR, font=font)
    draw.text((cx - 20, cy + 14), value, fill=(180, 200, 255), font=font_sm)
    return (x1, cy), (x2, cy)


def _draw_voltage_source(draw, cx: int, cy: int, refdes: str, value: str, font, font_sm,
                         color: tuple[int, int, int] = COMP_COLOR):
    """Draw a voltage source symbol (circle with + -)."""
    x1, x2 = cx - COMP_W // 2, cx + COMP_W // 2
    r = 22
    # Left lead
    draw.line([(x1, cy), (cx - r, cy)], fill=color, width=2)
    # Circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=2)
    # + and - signs
    draw.text((cx - r + 6, cy - 10), "+", fill=(0, 255, 127), font=font)
    draw.text((cx + r - 16, cy - 10), "−", fill=(255, 100, 100), font=font)
    # Right lead
    draw.line([(cx + r, cy), (x2, cy)], fill=color, width=2)
    # Labels
    draw.text((cx - 20, cy - r - 22), refdes, fill=TEXT_COLOR, font=font)
    draw.text((cx - 25, cy + r + 6), value, fill=(180, 200, 255), font=font_sm)
    return (x1, cy), (x2, cy)


def _draw_current_source(draw, cx: int, cy: int, refdes: str, value: str, font, font_sm,
                         color: tuple[int, int, int] = COMP_COLOR):
    """Draw a current source symbol (circle with arrow)."""
    x1, x2 = cx - COMP_W // 2, cx + COMP_W // 2
    r = 22
    # Left lead
    draw.line([(x1, cy), (cx - r, cy)], fill=color, width=2)
    # Circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=2)
    # Arrow inside circle (pointing right = conventional current direction)
    arrow_x1 = cx - 12
    arrow_x2 = cx + 12
    draw.line([(arrow_x1, cy), (arrow_x2, cy)], fill=color, width=2)
    _draw_arrow_head(draw, arrow_x1, cy, arrow_x2, cy, size=7)
    # Right lead
    draw.line([(cx + r, cy), (x2, cy)], fill=color, width=2)
    # Labels
    draw.text((cx - 20, cy - r - 22), refdes, fill=TEXT_COLOR, font=font)
    draw.text((cx - 25, cy + r + 6), value, fill=(180, 200, 255), font=font_sm)
    return (x1, cy), (x2, cy)


def _draw_opamp(draw, cx: int, cy: int, refdes: str, value: str, font, font_sm,
                color: tuple[int, int, int] = COMP_COLOR):
    """Draw an opamp/VCVS triangle symbol."""
    # Triangle pointing right
    w, h = 60, 70
    pts = [
        (cx - w // 2, cy - h // 2),
        (cx - w // 2, cy + h // 2),
        (cx + w // 2, cy),
    ]
    draw.polygon(pts, outline=color, width=2)
    # + input (top-left)
    draw.text((cx - w // 2 + 6, cy - h // 2 + 8), "+", fill=(0, 255, 127), font=font_sm)
    # - input (bottom-left)
    draw.text((cx - w // 2 + 6, cy + h // 2 - 20), "−", fill=(255, 100, 100), font=font_sm)
    # Labels
    draw.text((cx - 10, cy - h // 2 - 22), refdes, fill=TEXT_COLOR, font=font)
    draw.text((cx - 15, cy + h // 2 + 6), value, fill=(180, 200, 255), font=font_sm)
    # Pin positions: inverting_in, noninverting_in, output
    inv_in = (cx - w // 2, cy - h // 4)
    ninv_in = (cx - w // 2, cy + h // 4)
    output = (cx + w // 2, cy)
    return inv_in, ninv_in, output


def _draw_diode(draw, cx: int, cy: int, refdes: str, value: str, font, font_sm,
                color: tuple[int, int, int] = COMP_COLOR):
    """Draw a diode symbol (triangle + bar)."""
    x1, x2 = cx - COMP_W // 2, cx + COMP_W // 2
    tri_w, tri_h = 20, 24
    # Left lead
    draw.line([(x1, cy), (cx - tri_w, cy)], fill=color, width=2)
    # Triangle (anode side, pointing right)
    pts = [
        (cx - tri_w, cy - tri_h // 2),
        (cx - tri_w, cy + tri_h // 2),
        (cx, cy),
    ]
    draw.polygon(pts, outline=color, fill=None, width=2)
    # Cathode bar
    draw.line([(cx, cy - tri_h // 2), (cx, cy + tri_h // 2)], fill=color, width=3)
    # Right lead
    draw.line([(cx, cy), (x2, cy)], fill=color, width=2)
    # Labels
    draw.text((cx - 20, cy - 30), refdes, fill=TEXT_COLOR, font=font)
    draw.text((cx - 20, cy + 14), value, fill=(180, 200, 255), font=font_sm)
    return (x1, cy), (x2, cy)


def _draw_bjt(draw, cx: int, cy: int, refdes: str, value: str, font, font_sm,
              is_npn: bool = True, color: tuple[int, int, int] = COMP_COLOR):
    """Draw a BJT transistor symbol (NPN or PNP).

    Pins returned: (collector, base, emitter).
    """
    x1 = cx - COMP_W // 2
    x2 = cx + COMP_W // 2
    bar_x = cx - 8
    bar_h = 30
    # Base lead (left)
    draw.line([(x1, cy), (bar_x, cy)], fill=color, width=2)
    # Vertical bar
    draw.line([(bar_x, cy - bar_h // 2), (bar_x, cy + bar_h // 2)],
              fill=color, width=3)
    # Collector line (upper-right)
    cx_r = cx + 16
    cy_c = cy - 22
    draw.line([(bar_x, cy - bar_h // 4), (cx_r, cy_c)], fill=color, width=2)
    # Collector lead up
    draw.line([(cx_r, cy_c), (cx_r, cy - COMP_H // 2)], fill=color, width=2)
    # Emitter line (lower-right)
    cy_e = cy + 22
    draw.line([(bar_x, cy + bar_h // 4), (cx_r, cy_e)], fill=color, width=2)
    # Emitter lead down
    draw.line([(cx_r, cy_e), (cx_r, cy + COMP_H // 2)], fill=color, width=2)
    # Arrow on emitter
    if is_npn:
        _draw_arrow_head(draw, bar_x + 2, cy + bar_h // 4 + 2, cx_r, cy_e)
    else:
        _draw_arrow_head(draw, cx_r, cy_e, bar_x + 2, cy + bar_h // 4 + 2)
    # Circle
    r = bar_h + 4
    draw.ellipse([cx - r, cy - r, cx + r + 8, cy + r], outline=color, width=1)
    # Labels
    draw.text((cx - 25, cy - COMP_H // 2 - 18), refdes, fill=TEXT_COLOR, font=font)
    type_label = "NPN" if is_npn else "PNP"
    draw.text((cx + r + 4, cy - 6), f"{type_label}", fill=(180, 200, 255), font=font_sm)
    if value and value != type_label:
        draw.text((cx - 20, cy + COMP_H // 2 + 4), value, fill=(180, 200, 255), font=font_sm)
    # Return: collector_pin, base_pin, emitter_pin
    return (cx_r, cy - COMP_H // 2), (x1, cy), (cx_r, cy + COMP_H // 2)


def _draw_mosfet(draw, cx: int, cy: int, refdes: str, value: str, font, font_sm,
                 color: tuple[int, int, int] = COMP_COLOR):
    """Draw a simplified MOSFET symbol. Pins: (drain, gate, source)."""
    x1 = cx - COMP_W // 2
    bar_x = cx - 8
    bar_h = 30
    cx_r = cx + 16
    # Gate lead
    draw.line([(x1, cy), (bar_x - 6, cy)], fill=color, width=2)
    # Gate plate
    draw.line([(bar_x - 6, cy - bar_h // 2), (bar_x - 6, cy + bar_h // 2)],
              fill=color, width=2)
    # Channel bar
    draw.line([(bar_x, cy - bar_h // 2), (bar_x, cy + bar_h // 2)],
              fill=color, width=3)
    # Drain (up)
    draw.line([(bar_x, cy - bar_h // 4), (cx_r, cy - bar_h // 4)], fill=color, width=2)
    draw.line([(cx_r, cy - bar_h // 4), (cx_r, cy - COMP_H // 2)], fill=color, width=2)
    # Source (down)
    draw.line([(bar_x, cy + bar_h // 4), (cx_r, cy + bar_h // 4)], fill=color, width=2)
    draw.line([(cx_r, cy + bar_h // 4), (cx_r, cy + COMP_H // 2)], fill=color, width=2)
    # Body connection
    draw.line([(bar_x, cy), (cx_r, cy)], fill=color, width=1)
    # Labels
    draw.text((cx - 25, cy - COMP_H // 2 - 18), refdes, fill=TEXT_COLOR, font=font)
    draw.text((cx + 22, cy - 6), "MOS", fill=(180, 200, 255), font=font_sm)
    if value:
        draw.text((cx - 20, cy + COMP_H // 2 + 4), value, fill=(180, 200, 255), font=font_sm)
    return (cx_r, cy - COMP_H // 2), (x1, cy), (cx_r, cy + COMP_H // 2)


def _draw_digital_gate(draw, cx: int, cy: int, refdes: str, value: str,
                       font, font_sm, n_inputs: int = 2,
                       color: tuple[int, int, int] = COMP_COLOR):
    """Draw a simplified digital gate box symbol.

    Returns: (input_pins_list, output_pin).
    """
    bw, bh = 50, max(40, 18 * n_inputs + 14)
    x1, x2 = cx - bw // 2, cx + bw // 2
    y1, y2 = cy - bh // 2, cy + bh // 2
    draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
    # Gate type label inside box
    gate_label = value.replace("_model", "").replace("_", " ").upper()
    # Shorten known patterns
    for pat, short in [("D AND", "AND"), ("D OR", "OR"), ("D XOR", "XOR"),
                       ("D NAND", "NAND"), ("D NOR", "NOR"),
                       ("D INVERTER", "NOT"), ("INV", "NOT")]:
        if pat in gate_label:
            gate_label = short
            break
    if len(gate_label) > 5:
        gate_label = gate_label[:5]
    draw.text((cx - len(gate_label) * 3, cy - 6), gate_label,
              fill=(0, 220, 255), font=font_sm)
    # Input leads
    input_pins = []
    for j in range(n_inputs):
        iy = y1 + (j + 1) * bh // (n_inputs + 1)
        draw.line([(x1 - 25, iy), (x1, iy)], fill=WIRE_COLOR, width=2)
        input_pins.append((x1 - 25, iy))
    # Output lead
    draw.line([(x2, cy), (x2 + 25, cy)], fill=WIRE_COLOR, width=2)
    out_pin = (x2 + 25, cy)
    # Labels
    draw.text((cx - 15, y1 - 18), refdes, fill=TEXT_COLOR, font=font)
    return input_pins, out_pin


def _draw_arrow_head(draw, x1: int, y1: int, x2: int, y2: int, size: int = 6):
    """Draw a small arrow head at (x2,y2) pointing from (x1,y1)."""
    angle = math.atan2(y2 - y1, x2 - x1)
    a1 = angle + math.pi * 0.8
    a2 = angle - math.pi * 0.8
    draw.line([(x2, y2), (int(x2 + size * math.cos(a1)), int(y2 + size * math.sin(a1)))],
              fill=COMP_COLOR, width=2)
    draw.line([(x2, y2), (int(x2 + size * math.cos(a2)), int(y2 + size * math.sin(a2)))],
              fill=COMP_COLOR, width=2)


def _draw_ground(draw, x: int, y: int):
    """Draw a ground symbol at position."""
    draw.line([(x, y), (x, y + 12)], fill=GND_COLOR, width=2)
    draw.line([(x - 12, y + 12), (x + 12, y + 12)], fill=GND_COLOR, width=2)
    draw.line([(x - 8, y + 17), (x + 8, y + 17)], fill=GND_COLOR, width=1)
    draw.line([(x - 4, y + 22), (x + 4, y + 22)], fill=GND_COLOR, width=1)


def _draw_node_dot(draw, x: int, y: int, label: str, font_sm):
    """Draw a node junction dot with label."""
    r = 4
    draw.ellipse([x - r, y - r, x + r, y + r], fill=NODE_COLOR)
    if label and label != "0":
        draw.text((x + 6, y - 14), label, fill=NODE_COLOR, font=font_sm)


def render_schematic_image(
    netlist: str,
    output_path: str,
    width: int = 1400,
    title: str | None = None,
    show_nodes: bool = True,
) -> str:
    """Render a SPICE netlist as a schematic PNG image.

    Returns the path of the saved image.
    """
    from PIL import Image, ImageDraw, ImageFont

    components, parsed_title, models = parse_netlist(netlist)
    if title is None:
        title = parsed_title

    if not components:
        raise ValueError("No renderable components found in netlist")

    # ── Classify components by rendering type ───────────────
    two_term = [c for c in components if c.comp_type in ("R", "C", "L", "V", "I", "D")]
    opamps = [c for c in components if c.comp_type == "E"]
    three_term = [c for c in components if c.comp_type in ("Q", "M")]
    digital = [c for c in components if c.comp_type == "A"]

    # Resolve model types for transistors
    for comp in three_term:
        if comp.model and comp.model in models:
            mtype = models[comp.model].lower()
            if mtype in ("npn", "pnp"):
                comp.display_value = mtype.upper()
            elif mtype in ("nmos", "pmos"):
                comp.display_value = mtype.upper()

    # Resolve gate type labels for digital components
    for comp in digital:
        if comp.model and comp.model in models:
            comp.display_value = models[comp.model]

    # Arrange two-terminal components in rows
    cols = max(3, min(6, len(two_term)))
    rows_2t = (len(two_term) + cols - 1) // cols if two_term else 0
    opamp_rows = len(opamps)
    three_term_rows = (len(three_term) + 2) // 3 if three_term else 0
    digital_rows = (len(digital) + 2) // 3 if digital else 0
    total_rows = rows_2t + opamp_rows + three_term_rows + digital_rows + 1

    # Auto-adjust canvas width based on column count
    min_width = MARGIN * 2 + cols * GRID_X + 100
    width = max(width, min_width)

    img_h = MARGIN * 2 + total_rows * GRID_Y + 80  # extra space for legend
    img = Image.new("RGB", (width, img_h), color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Font
    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_sm = ImageFont.truetype("arial.ttf", 11)
        font_title = ImageFont.truetype("arial.ttf", 20)
    except (IOError, OSError):
        font = ImageFont.load_default()
        font_sm = font
        font_title = font

    # Draw subtle grid
    for gx in range(0, width, 40):
        draw.line([(gx, 0), (gx, img_h)], fill=GRID_COLOR, width=1)
    for gy in range(0, img_h, 40):
        draw.line([(0, gy), (width, gy)], fill=GRID_COLOR, width=1)

    # Title
    draw.text((MARGIN, 15), title, fill=(0, 212, 255), font=font_title)

    # Track node positions for wiring
    node_positions: dict[str, list[tuple[int, int]]] = {}

    def _register_node(name: str, x: int, y: int):
        if name not in node_positions:
            node_positions[name] = []
        node_positions[name].append((x, y))

    # ── Draw two-terminal components ────────────────────────
    draw_funcs = {
        "R": _draw_resistor,
        "C": _draw_capacitor,
        "L": _draw_inductor,
        "V": _draw_voltage_source,
        "I": _draw_current_source,
        "D": _draw_diode,
    }

    for idx, comp in enumerate(two_term):
        row = idx // cols
        col = idx % cols
        cx = MARGIN + COMP_W // 2 + col * GRID_X + 50
        cy = MARGIN + 50 + row * GRID_Y + COMP_H

        func = draw_funcs.get(comp.comp_type)
        if func is None:
            continue

        color = TYPE_COLORS.get(comp.comp_type, COMP_COLOR)
        pin_left, pin_right = func(
            draw, cx, cy, comp.refdes, comp.display_value, font, font_sm,
            color=color,
        )
        _register_node(comp.nodes[0], pin_left[0], pin_left[1])
        _register_node(comp.nodes[1], pin_right[0], pin_right[1])

    # ── Draw opamps/VCVS ───────────────────────────────────
    for idx, comp in enumerate(opamps):
        cx = MARGIN + COMP_W + 50
        cy = MARGIN + 50 + (rows_2t + idx) * GRID_Y + COMP_H

        color = TYPE_COLORS.get("E", COMP_COLOR)
        inv_pin, ninv_pin, out_pin = _draw_opamp(
            draw, cx, cy, comp.refdes, comp.display_value, font, font_sm,
            color=color,
        )
        # Wire leads to pins
        lead = 35
        inv_lead = (inv_pin[0] - lead, inv_pin[1])
        ninv_lead = (ninv_pin[0] - lead, ninv_pin[1])
        out_lead = (out_pin[0] + lead, out_pin[1])
        draw.line([inv_lead, inv_pin], fill=WIRE_COLOR, width=2)
        draw.line([ninv_lead, ninv_pin], fill=WIRE_COLOR, width=2)
        draw.line([out_pin, out_lead], fill=WIRE_COLOR, width=2)

        # nodes: out+, out-, ctrl+, ctrl-
        _register_node(comp.nodes[0], out_lead[0], out_lead[1])      # out+
        _register_node(comp.nodes[1], cx, cy + 55)                    # out- (ground)
        _register_node(comp.nodes[3], inv_lead[0], inv_lead[1])      # ctrl- (inv input)
        _register_node(comp.nodes[2], ninv_lead[0], ninv_lead[1])    # ctrl+ (non-inv)

    # ── Draw BJTs / MOSFETs ─────────────────────────────────
    for idx, comp in enumerate(three_term):
        row_offset = rows_2t + opamp_rows + idx // 3
        col = idx % 3
        cx = MARGIN + COMP_W // 2 + col * GRID_X + 50
        cy = MARGIN + 50 + row_offset * GRID_Y + COMP_H

        if comp.comp_type == "Q":
            is_npn = True
            if comp.model and comp.model in models:
                is_npn = models[comp.model].lower() != "pnp"
            color = TYPE_COLORS.get("Q", COMP_COLOR)
            c_pin, b_pin, e_pin = _draw_bjt(
                draw, cx, cy, comp.refdes, comp.display_value,
                font, font_sm, is_npn=is_npn, color=color,
            )
            # nodes: collector, base, emitter
            _register_node(comp.nodes[0], c_pin[0], c_pin[1])
            _register_node(comp.nodes[1], b_pin[0], b_pin[1])
            _register_node(comp.nodes[2], e_pin[0], e_pin[1])
        elif comp.comp_type == "M":
            color = TYPE_COLORS.get("M", COMP_COLOR)
            d_pin, g_pin, s_pin = _draw_mosfet(
                draw, cx, cy, comp.refdes, comp.display_value, font, font_sm,
                color=color,
            )
            # nodes: drain, gate, source, bulk
            _register_node(comp.nodes[0], d_pin[0], d_pin[1])
            _register_node(comp.nodes[1], g_pin[0], g_pin[1])
            _register_node(comp.nodes[2], s_pin[0], s_pin[1])
            if len(comp.nodes) > 3:
                _register_node(comp.nodes[3], s_pin[0], s_pin[1])  # bulk → source

    # ── Draw digital gates (XSPICE A-elements) ─────────────
    for idx, comp in enumerate(digital):
        row_offset = rows_2t + opamp_rows + three_term_rows + idx // 3
        col = idx % 3
        cx = MARGIN + COMP_W // 2 + col * GRID_X + 50
        cy = MARGIN + 50 + row_offset * GRID_Y + COMP_H

        n_inputs = len(comp.nodes) - 1  # last node is output
        color = TYPE_COLORS.get("A", COMP_COLOR)
        input_pins, out_pin = _draw_digital_gate(
            draw, cx, cy, comp.refdes, comp.display_value,
            font, font_sm, n_inputs=max(1, n_inputs), color=color,
        )
        # Register input nodes
        for j, pin in enumerate(input_pins):
            if j < len(comp.nodes) - 1:
                _register_node(comp.nodes[j], pin[0], pin[1])
        # Register output node (last)
        _register_node(comp.nodes[-1], out_pin[0], out_pin[1])

    # ── Draw wires connecting same-named nodes ──────────────
    wire_idx = 0  # stagger offset for parallel wires
    for node_name, positions in node_positions.items():
        if len(positions) < 2:
            continue
        # Sort positions for clean routing
        positions.sort(key=lambda p: (p[1], p[0]))
        for i in range(len(positions) - 1):
            ax, ay = positions[i]
            bx, by = positions[i + 1]
            if ay == by:
                # Horizontal wire
                draw.line([(ax, ay), (bx, by)], fill=WIRE_COLOR, width=2)
            else:
                # L-shaped routing with staggered midpoints to avoid overlap
                offset = (wire_idx % 5) * 8 - 16  # -16, -8, 0, +8, +16
                mid_x = (ax + bx) // 2 + offset
                wire_idx += 1
                draw.line([(ax, ay), (mid_x, ay)], fill=WIRE_COLOR, width=2)
                draw.line([(mid_x, ay), (mid_x, by)], fill=WIRE_COLOR, width=2)
                draw.line([(mid_x, by), (bx, by)], fill=WIRE_COLOR, width=2)

    # ── Draw node labels and ground symbols ─────────────────
    # Count how many wires touch each position to identify true junctions
    pos_counts: dict[tuple[int, int], int] = {}
    for positions in node_positions.values():
        for p in positions:
            pos_counts[p] = pos_counts.get(p, 0) + 1

    for node_name, positions in node_positions.items():
        # Ground symbol for node "0"
        if node_name == "0":
            for x, y in positions:
                _draw_ground(draw, x, y)
            continue

        if not show_nodes:
            continue

        # Draw dots only at junctions (3+ connections) or at named nodes
        # For named nodes with 2+ positions, show one label near the first position
        seen_label = False
        for x, y in positions:
            is_junction = len(positions) >= 3  # 3+ pins share this net name
            if is_junction or not seen_label:
                _draw_node_dot(draw, x, y, node_name if not seen_label else "", font_sm)
                seen_label = True

    # ── Component count annotation with color legend ────────
    counts = {}
    for c in components:
        counts[c.comp_type] = counts.get(c.comp_type, 0) + 1
    type_names = {"R": "Resistors", "C": "Capacitors", "L": "Inductors",
                  "V": "V-Sources", "I": "I-Sources", "E": "Op-Amps",
                  "D": "Diodes", "Q": "BJTs", "M": "MOSFETs", "A": "Gates"}
    legend_x = MARGIN
    legend_y = img_h - 35
    for t, n in counts.items():
        color = TYPE_COLORS.get(t, COMP_COLOR)
        # Color swatch
        draw.rectangle([legend_x, legend_y + 2, legend_x + 10, legend_y + 12],
                       fill=color, outline=color)
        label = f"{type_names.get(t, t)}: {n}"
        draw.text((legend_x + 14, legend_y), label, fill=(160, 160, 180), font=font_sm)
        legend_x += len(label) * 7 + 30

    # Save
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


# ── MCP tool ────────────────────────────────────────────────

def tool_render_netlist_schematic(
    netlist: str,
    output_path: str = "",
    title: str | None = None,
    width: int = 1400,
    show_nodes: bool = True,
) -> dict:
    """Render a SPICE netlist as a circuit schematic image.

    Parses the netlist and generates a schematic diagram with standard
    symbols (resistors, capacitors, sources, opamps) and automatic
    wire routing between shared nodes.

    This solves the problem where open_netlist + export_circuit_image
    produces a blank grid image — this tool generates the schematic
    directly from the netlist text.

    Args:
        netlist: SPICE netlist text (same format as run_spice input).
        output_path: File path for PNG output (auto-generated if empty).
        title: Schematic title (auto-detected from netlist comment if omitted).
        width: Image width in pixels.
        show_nodes: Whether to label node connection points.
    """
    if not netlist or not netlist.strip():
        return _err("Netlist is empty", "E7_EMPTY_NETLIST")

    if not output_path:
        tmp_dir = r"C:\mcp_spice_tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        output_path = os.path.join(tmp_dir, "schematic.png")

    try:
        saved = render_schematic_image(
            netlist, output_path, width=width, title=title, show_nodes=show_nodes,
        )
        # Validate output is not empty
        if not os.path.isfile(saved) or os.path.getsize(saved) < 100:
            return _err(
                "Rendered image appears empty — netlist may have no renderable components",
                "E7_EMPTY_RENDER",
            )

        return _ok({
            "path": saved,
            "width": width,
            "components_rendered": len(parse_netlist(netlist)[0]),
        })
    except ValueError as exc:
        return _err(str(exc), "E7_RENDER_FAILED")
    except Exception as exc:
        return _err(str(exc), "E7_RENDER_ERROR", recovery="Check netlist syntax")
