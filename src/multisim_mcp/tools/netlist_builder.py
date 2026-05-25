"""
Netlist Builder Engine - programmatic circuit construction.

Provides a CircuitBuilder class that generates SPICE netlists from
component-level descriptions, handling node naming, subcircuit
instantiation, and test stimulus generation automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import ToolResponse


def _ok(data: dict | None = None) -> dict:
    return ToolResponse(ok=True, data=data or {}).model_dump()


def _err(msg: str, code: str = "ERROR", recovery: str = "") -> dict:
    return ToolResponse(
        ok=False, error_code=code, error_message=msg, suggested_recovery=recovery,
    ).model_dump()


# ────────────────────────────────────────────────────────────
# Data classes
# ────────────────────────────────────────────────────────────

@dataclass
class Pin:
    """A component pin connection."""
    name: str
    node: str  # circuit node this pin connects to


@dataclass
class Component:
    """A circuit component instance."""
    refdes: str          # Reference designator (R1, U1, A1, ...)
    comp_type: str       # resistor, capacitor, inductor, voltage_source, vcvs, xspice, subcircuit
    value: str | float | None = None
    pins: list[Pin] = field(default_factory=list)
    model: str = ""      # SPICE model name
    params: dict = field(default_factory=dict)

    def to_spice(self) -> str:
        nodes = " ".join(p.node for p in self.pins)
        if self.comp_type == "xspice":
            # XSPICE A-device syntax: A1 [in1 in2] out model
            return f"{self.refdes} {self.value}"
        elif self.comp_type == "subcircuit":
            return f"X{self.refdes} {nodes} {self.model}"
        elif self.comp_type == "vcvs":
            gain = self.value if self.value else 200000
            return f"{self.refdes} {nodes} {gain}"
        elif self.comp_type in ("voltage_source", "current_source"):
            return f"{self.refdes} {nodes} {self.value}"
        else:
            val = self.value if self.value is not None else ""
            return f"{self.refdes} {nodes} {val}"


@dataclass
class SubCircuit:
    """A .subckt definition."""
    name: str
    ports: list[str]
    body: str  # SPICE lines inside the subckt


@dataclass
class Model:
    """A .model definition."""
    name: str
    model_type: str  # d_and, d_or, npn, etc.
    params: dict = field(default_factory=dict)

    def to_spice(self) -> str:
        param_str = " ".join(f"{k}={v}" for k, v in self.params.items())
        return f".model {self.name} {self.model_type}({param_str})"


# ────────────────────────────────────────────────────────────
# Circuit Builder
# ────────────────────────────────────────────────────────────

class CircuitBuilder:
    """Programmatic SPICE netlist construction engine.

    Usage::

        cb = CircuitBuilder("My Circuit")
        cb.add_resistor("R1", "in", "out", 10000)
        cb.add_voltage_source("V1", "in", "0", "DC 5")
        netlist = cb.build()
    """

    def __init__(self, title: str = "Circuit"):
        self.title = title
        self.components: list[Component] = []
        self.subcircuits: list[SubCircuit] = []
        self.models: list[Model] = []
        self._comment_lines: list[str] = []
        self._counters: dict[str, int] = {}
        self._nodes: set[str] = {"0"}

    # ── Auto RefDes ─────────────────────────────────────────

    def _next_refdes(self, prefix: str) -> str:
        """Generate next auto-incremented RefDes."""
        cnt = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = cnt
        return f"{prefix}{cnt}"

    def _track_node(self, node: str) -> str:
        self._nodes.add(node)
        return node

    # ── Passive Components ──────────────────────────────────

    def add_resistor(self, refdes: str | None, n1: str, n2: str, value: float) -> str:
        rd = refdes or self._next_refdes("R")
        self._track_node(n1)
        self._track_node(n2)
        self.components.append(Component(
            refdes=rd, comp_type="resistor", value=value,
            pins=[Pin("1", n1), Pin("2", n2)],
        ))
        return rd

    def add_capacitor(self, refdes: str | None, n1: str, n2: str, value: float) -> str:
        rd = refdes or self._next_refdes("C")
        self._track_node(n1)
        self._track_node(n2)
        self.components.append(Component(
            refdes=rd, comp_type="capacitor", value=value,
            pins=[Pin("1", n1), Pin("2", n2)],
        ))
        return rd

    def add_inductor(self, refdes: str | None, n1: str, n2: str, value: float) -> str:
        rd = refdes or self._next_refdes("L")
        self._track_node(n1)
        self._track_node(n2)
        self.components.append(Component(
            refdes=rd, comp_type="inductor", value=value,
            pins=[Pin("1", n1), Pin("2", n2)],
        ))
        return rd

    # ── Sources ─────────────────────────────────────────────

    def add_voltage_source(
        self, refdes: str | None, nplus: str, nminus: str, value: str,
    ) -> str:
        rd = refdes or self._next_refdes("V")
        self._track_node(nplus)
        self._track_node(nminus)
        self.components.append(Component(
            refdes=rd, comp_type="voltage_source", value=value,
            pins=[Pin("+", nplus), Pin("-", nminus)],
        ))
        return rd

    def add_current_source(
        self, refdes: str | None, nplus: str, nminus: str, value: str,
    ) -> str:
        rd = refdes or self._next_refdes("I")
        self._track_node(nplus)
        self._track_node(nminus)
        self.components.append(Component(
            refdes=rd, comp_type="current_source", value=value,
            pins=[Pin("+", nplus), Pin("-", nminus)],
        ))
        return rd

    # ── Controlled Sources ──────────────────────────────────

    def add_vcvs(
        self, refdes: str | None,
        out_plus: str, out_minus: str,
        ctrl_plus: str, ctrl_minus: str,
        gain: float = 200000,
    ) -> str:
        """Add Voltage-Controlled Voltage Source (ideal opamp model)."""
        rd = refdes or self._next_refdes("E")
        for n in (out_plus, out_minus, ctrl_plus, ctrl_minus):
            self._track_node(n)
        self.components.append(Component(
            refdes=rd, comp_type="vcvs", value=gain,
            pins=[Pin("out+", out_plus), Pin("out-", out_minus),
                  Pin("ctrl+", ctrl_plus), Pin("ctrl-", ctrl_minus)],
        ))
        return rd

    # ── XSPICE Digital ──────────────────────────────────────

    def add_xspice(self, refdes: str | None, spice_line: str) -> str:
        """Add raw XSPICE A-device line."""
        rd = refdes or self._next_refdes("A")
        self.components.append(Component(
            refdes=rd, comp_type="xspice", value=spice_line,
        ))
        return rd

    def add_digital_gate(
        self, gate_type: str,
        inputs: list[str], output: str,
        refdes: str | None = None,
        model_name: str | None = None,
        rise_delay: float = 10e-9,
        fall_delay: float = 10e-9,
    ) -> str:
        """Add a digital logic gate (AND, OR, NAND, NOR, XOR, XNOR, inverter).

        Automatically creates the XSPICE A-device line and model definition.
        """
        gate_upper = gate_type.upper()
        gate_map = {
            "AND": "d_and", "OR": "d_or", "NAND": "d_nand",
            "NOR": "d_nor", "XOR": "d_xor", "XNOR": "d_xnor",
            "NOT": "d_inverter", "INV": "d_inverter", "INVERTER": "d_inverter",
            "BUF": "d_buffer", "BUFFER": "d_buffer",
        }
        d_type = gate_map.get(gate_upper)
        if not d_type:
            raise ValueError(f"Unknown gate type: {gate_type}. Use: {', '.join(gate_map.keys())}")

        # Validate input count
        single_input_gates = {"NOT", "INV", "INVERTER", "BUF", "BUFFER"}
        if gate_upper in single_input_gates and len(inputs) != 1:
            raise ValueError(f"{gate_type} gate requires exactly 1 input, got {len(inputs)}")
        if gate_upper not in single_input_gates and len(inputs) < 2:
            raise ValueError(f"{gate_type} gate requires at least 2 inputs, got {len(inputs)}")

        rd = refdes or self._next_refdes("A")
        mdl = model_name or f"{d_type}_{rd.lower()}"

        # Build A-device line
        if gate_upper in ("NOT", "INV", "INVERTER", "BUF", "BUFFER"):
            line = f"{rd} {inputs[0]} {output} {mdl}"
        else:
            in_list = " ".join(inputs)
            line = f"{rd} [{in_list}] {output} {mdl}"

        for n in inputs + [output]:
            self._track_node(n)

        self.components.append(Component(refdes=rd, comp_type="xspice", value=line))
        self.models.append(Model(
            name=mdl, model_type=d_type,
            params={"rise_delay": rise_delay, "fall_delay": fall_delay, "input_load": "1e-12"},
        ))

        # Add pull-down resistor on output for simulation stability
        self.add_resistor(None, output, "0", 100000)

        return rd

    def add_dff(
        self, data: str, clk: str, preset: str, clear: str,
        q: str, qbar: str,
        refdes: str | None = None,
        model_name: str | None = None,
        clk_delay: float = 10e-9,
    ) -> str:
        """Add D flip-flop."""
        rd = refdes or self._next_refdes("A")
        mdl = model_name or f"dff_{rd.lower()}"
        line = f"{rd} {data} {clk} {preset} {clear} {q} {qbar} {mdl}"
        for n in (data, clk, preset, clear, q, qbar):
            self._track_node(n)
        self.components.append(Component(refdes=rd, comp_type="xspice", value=line))
        self.models.append(Model(
            name=mdl, model_type="d_dff",
            params={"clk_delay": clk_delay, "ic": 0},
        ))
        self.add_resistor(None, q, "0", 100000)
        self.add_resistor(None, qbar, "0", 100000)
        return rd

    # ── Subcircuits ─────────────────────────────────────────

    def add_subcircuit_def(self, name: str, ports: list[str], body: str) -> None:
        """Define a .subckt block."""
        self.subcircuits.append(SubCircuit(name=name, ports=ports, body=body))

    def add_subcircuit_instance(
        self, refdes: str | None, subckt_name: str, connections: dict[str, str],
    ) -> str:
        """Instantiate a subcircuit."""
        rd = refdes or self._next_refdes("X")
        for n in connections.values():
            self._track_node(n)
        self.components.append(Component(
            refdes=f"X{rd}" if not rd.startswith("X") else rd,
            comp_type="subcircuit",
            model=subckt_name,
            pins=[Pin(port, node) for port, node in connections.items()],
        ))
        return rd

    # ── Model ───────────────────────────────────────────────

    def add_model(self, name: str, model_type: str, **params) -> None:
        self.models.append(Model(name=name, model_type=model_type, params=params))

    # ── Comments ────────────────────────────────────────────

    def add_comment(self, text: str) -> None:
        self._comment_lines.append(f"* {text}")

    # ── Build ───────────────────────────────────────────────

    def build(self) -> str:
        """Generate the complete SPICE netlist string.

        Automatically adds voltage sources for standard supply nodes
        (vcc, vdd) if referenced but not driven by any source.
        """
        lines: list[str] = []

        # Title
        # Sanitize to ASCII
        safe_title = self.title.encode("ascii", errors="replace").decode("ascii")
        lines.append(f"* {safe_title}")

        # Comments
        lines.extend(self._comment_lines)

        # Auto-VCC/VDD: check if supply nodes are referenced but not driven
        driven_nodes = set()
        for comp in self.components:
            if comp.comp_type in ("voltage_source", "current_source"):
                if comp.pins:
                    driven_nodes.add(comp.pins[0].node)
            elif comp.comp_type == "vcvs":
                if comp.pins:
                    driven_nodes.add(comp.pins[0].node)

        supply_map = {"vcc": 5, "vdd": 5, "vss": -5, "vee": -15}
        for node in self._nodes:
            if node.lower() in supply_map and node not in driven_nodes:
                voltage = supply_map[node.lower()]
                rd = self._next_refdes("V")
                self.components.append(Component(
                    refdes=rd, comp_type="voltage_source",
                    value=f"DC {voltage}",
                    pins=[Pin("+", node), Pin("-", "0")],
                ))
                driven_nodes.add(node)

        # Subcircuit definitions
        for sc in self.subcircuits:
            ports_str = " ".join(sc.ports)
            lines.append(f".subckt {sc.name} {ports_str}")
            lines.append(sc.body)
            lines.append(".ends")
            lines.append("")

        # Components
        for comp in self.components:
            lines.append(comp.to_spice())

        # Models
        for mdl in self.models:
            lines.append(mdl.to_spice())

        lines.append(".end")
        return "\n".join(lines) + "\n"

    def get_nodes(self) -> list[str]:
        """Return all circuit nodes (excluding ground '0')."""
        return sorted(n for n in self._nodes if n != "0")

    def validate(self) -> list[str]:
        """Check circuit connectivity, return list of warning strings.

        Detects:
        - Nodes connected to only one component pin (floating)
        - Missing ground reference (node '0' not referenced)
        """
        warnings: list[str] = []
        # Build node-to-refdes map
        node_refs: dict[str, list[str]] = {}
        for comp in self.components:
            if comp.comp_type == "xspice":
                continue  # Skip raw XSPICE — pins not tracked properly
            for pin in comp.pins:
                node_refs.setdefault(pin.node, []).append(comp.refdes)

        # Check for single-connection nodes (floating)
        for node, refs in node_refs.items():
            if node in ("0", "gnd", "ground"):
                continue
            if len(refs) == 1:
                warnings.append(
                    f"Node '{node}' is connected to only {refs[0]} — may be floating"
                )

        # Check ground reference
        if "0" not in self._nodes and "gnd" not in self._nodes:
            warnings.append("No ground node (0) found — circuit needs a ground reference")

        return warnings

    def get_print_command(self, nodes: list[str] | None = None) -> str:
        """Generate a 'print' command for all or specified nodes."""
        target = nodes or self.get_nodes()
        return "print " + " ".join(f"${n}" for n in target)

    def summary(self) -> dict:
        """Return a summary of the circuit."""
        return {
            "title": self.title,
            "num_components": len(self.components),
            "num_subcircuits": len(self.subcircuits),
            "num_models": len(self.models),
            "nodes": self.get_nodes(),
        }


# ────────────────────────────────────────────────────────────
# MCP Tool functions
# ────────────────────────────────────────────────────────────

def tool_build_netlist(
    title: str,
    components: list[dict],
    analysis: str = "op",
    output_nodes: list[str] | None = None,
) -> dict:
    """Build a SPICE netlist programmatically from component descriptions.

    Each component dict has ``type`` and type-specific fields:

    - ``{type: "R", refdes: "R1", n1: "in", n2: "out", value: 10000}``
    - ``{type: "C", refdes: "C1", n1: "out", n2: "0", value: 1e-6}``
    - ``{type: "L", refdes: "L1", n1: "in", n2: "out", value: 0.01}``
    - ``{type: "V", refdes: "V1", nplus: "in", nminus: "0", value: "DC 5"}``
    - ``{type: "V", refdes: "V1", nplus: "in", nminus: "0", value: "SIN(0 1 1000)"}``
    - ``{type: "V", refdes: "V1", nplus: "in", nminus: "0", value: "PULSE(0 5 0 1n 1n 500n 1u)"}``
    - ``{type: "I", refdes: "I1", nplus: "in", nminus: "0", value: "DC 0.001"}``
    - ``{type: "E", refdes: "E1", out_plus: "out", out_minus: "0", ctrl_plus: "inp", ctrl_minus: "inv", gain: 200000}``
    - ``{type: "gate", gate_type: "AND", inputs: ["a", "b"], output: "y"}``
    - ``{type: "gate", gate_type: "NOT", inputs: ["a"], output: "y"}``
    - ``{type: "dff", data: "d", clk: "clk", preset: "vcc", clear: "vcc", q: "q", qbar: "qn"}``
    - ``{type: "raw", line: "A1 [in1 in2] out model1"}`` — raw SPICE line

    Returns the complete netlist and suggested commands.
    """
    if not components:
        return _err("components list is empty", "E3_EMPTY")

    cb = CircuitBuilder(title)

    for comp in components:
        ctype = comp.get("type", "").upper()
        rd = comp.get("refdes")

        if ctype == "R":
            cb.add_resistor(rd, comp["n1"], comp["n2"], comp["value"])
        elif ctype == "C":
            cb.add_capacitor(rd, comp["n1"], comp["n2"], comp["value"])
        elif ctype == "L":
            cb.add_inductor(rd, comp["n1"], comp["n2"], comp["value"])
        elif ctype == "V":
            cb.add_voltage_source(rd, comp["nplus"], comp["nminus"], comp["value"])
        elif ctype == "I":
            cb.add_current_source(rd, comp["nplus"], comp["nminus"], comp["value"])
        elif ctype == "E":
            cb.add_vcvs(
                rd, comp["out_plus"], comp["out_minus"],
                comp["ctrl_plus"], comp["ctrl_minus"],
                comp.get("gain", 200000),
            )
        elif ctype == "GATE":
            cb.add_digital_gate(
                comp["gate_type"], comp["inputs"], comp["output"],
                refdes=rd,
                rise_delay=comp.get("rise_delay", 10e-9),
                fall_delay=comp.get("fall_delay", 10e-9),
            )
        elif ctype == "DFF":
            cb.add_dff(
                comp["data"], comp["clk"],
                comp.get("preset", "vcc"), comp.get("clear", "vcc"),
                comp["q"], comp.get("qbar", f"{comp['q']}n"),
                refdes=rd,
                clk_delay=comp.get("clk_delay", 10e-9),
            )
        elif ctype == "MODEL":
            cb.add_model(comp["name"], comp["model_type"], **comp.get("params", {}))
        elif ctype == "RAW":
            cb.components.append(Component(
                refdes=rd or cb._next_refdes("X"),
                comp_type="xspice",
                value=comp["line"],
            ))
        elif ctype == "COMMENT":
            cb.add_comment(comp.get("text", ""))
        else:
            return _err(f"Unknown component type: {ctype}", "E3_BAD_TYPE",
                        "Use: R, C, L, V, I, E, GATE, DFF, MODEL, RAW, COMMENT")

    netlist = cb.build()
    nodes = cb.get_nodes()
    warnings = cb.validate()

    # Build suggested commands
    measure_nodes = output_nodes or [n for n in nodes if n not in ("0", "vcc", "vdd")]
    if len(measure_nodes) > 8:
        measure_nodes = measure_nodes[:8]
    print_cmd = "print " + " ".join(f"${n}" for n in measure_nodes)

    if analysis.startswith("tran"):
        commands = [analysis, print_cmd]
    elif analysis.startswith("ac"):
        commands = [analysis, print_cmd]
    else:
        commands = ["op", print_cmd]

    return _ok({
        "netlist": netlist,
        "commands": commands,
        "summary": cb.summary(),
        "output_nodes": measure_nodes,
        "warnings": warnings or None,
    })
