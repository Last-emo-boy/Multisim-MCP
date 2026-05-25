"""
Design Rule Checking - pre-simulation verification of circuits.

Provides tools that analyze SPICE netlists and/or live designs for
common design issues: floating nodes, missing ground, power budget
violations, fan-out problems, and component value sanity checks.
"""

from __future__ import annotations

import re

from ..models import ToolResponse


def _ok(data: dict | None = None) -> dict:
    return ToolResponse(ok=True, data=data or {}).model_dump()


def _err(msg: str, code: str = "ERROR") -> dict:
    return ToolResponse(ok=False, error_code=code, error_message=msg).model_dump()


# ────────────────────────────────────────────────────────────
# Severity levels
# ────────────────────────────────────────────────────────────
SEV_ERROR = "error"      # Must fix before simulation
SEV_WARNING = "warning"  # May cause unexpected results
SEV_INFO = "info"        # Best-practice suggestion


# ────────────────────────────────────────────────────────────
# Netlist-based checks
# ────────────────────────────────────────────────────────────

def _parse_netlist_nodes(netlist: str) -> dict:
    """Extract node connectivity from a SPICE netlist.

    Returns: {
        "components": [{"refdes": str, "nodes": [str], "line": str}],
        "node_connections": {node: [refdes_list]},
        "has_ground": bool,
        "voltage_sources": [{"refdes": str, "nodes": [str], "value": str}],
        "resistors": [{"refdes": str, "nodes": [str], "value": float|None}],
    }
    """
    components = []
    node_connections: dict[str, list[str]] = {}
    voltage_sources = []
    resistors = []
    has_ground = False

    for raw_line in netlist.strip().splitlines():
        line = raw_line.strip()
        # Skip comments, directives, empty lines
        if not line or line.startswith("*") or line.startswith("."):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        refdes = parts[0]
        prefix = refdes[0].upper()

        # Extract nodes based on component type
        nodes = []
        value_str = None

        if prefix in ("R", "C", "L"):
            if len(parts) >= 4:
                nodes = [parts[1], parts[2]]
                value_str = parts[3]
            elif len(parts) >= 3:
                nodes = [parts[1], parts[2]]
        elif prefix == "V" or prefix == "I":
            if len(parts) >= 3:
                nodes = [parts[1], parts[2]]
                value_str = " ".join(parts[3:]) if len(parts) > 3 else None
        elif prefix == "E":  # VCVS
            if len(parts) >= 5:
                nodes = [parts[1], parts[2], parts[3], parts[4]]
        elif prefix == "A":
            # XSPICE: parse bracketed inputs
            bracket_match = re.search(r'\[([^\]]+)\]', line)
            if bracket_match:
                in_nodes = bracket_match.group(1).split()
                rest_after = line[bracket_match.end():].split()
                out_node = rest_after[0] if rest_after else None
                nodes = in_nodes + ([out_node] if out_node else [])
            else:
                # Simple: A1 in out model
                if len(parts) >= 3:
                    nodes = [parts[1], parts[2]]
        elif prefix == "X":
            # Subcircuit instance: X1 n1 n2 ... subckt_name
            if len(parts) >= 3:
                nodes = parts[1:-1]  # last part is subcircuit name
        elif prefix == "Q":
            # BJT: Q1 collector base emitter model
            if len(parts) >= 4:
                nodes = [parts[1], parts[2], parts[3]]
        elif prefix == "M":
            # MOSFET: M1 drain gate source bulk model
            if len(parts) >= 5:
                nodes = [parts[1], parts[2], parts[3], parts[4]]
        elif prefix == "D":
            # Diode: D1 anode cathode model
            if len(parts) >= 3:
                nodes = [parts[1], parts[2]]

        if nodes:
            comp_entry = {"refdes": refdes, "nodes": nodes, "line": line}
            components.append(comp_entry)

            for n in nodes:
                if n == "0" or n.lower() in ("gnd", "ground"):
                    has_ground = True
                node_connections.setdefault(n, []).append(refdes)

            if prefix == "V":
                voltage_sources.append({"refdes": refdes, "nodes": nodes, "value": value_str or ""})
            if prefix == "R":
                try:
                    val = float(value_str) if value_str else None
                except ValueError:
                    val = None
                resistors.append({"refdes": refdes, "nodes": nodes, "value": val})

    return {
        "components": components,
        "node_connections": node_connections,
        "has_ground": has_ground,
        "voltage_sources": voltage_sources,
        "resistors": resistors,
    }


def _check_ground(parsed: dict) -> list[dict]:
    """Check for ground reference."""
    issues = []
    if not parsed["has_ground"]:
        issues.append({
            "severity": SEV_ERROR,
            "rule": "GROUND_REF",
            "message": "No ground (node 0) reference found. Every circuit needs a ground node.",
            "suggestion": "Connect at least one node to ground (0).",
        })
    return issues


def _check_floating_nodes(parsed: dict) -> list[dict]:
    """Check for nodes with only one connection (floating)."""
    issues = []
    for node, refs in parsed["node_connections"].items():
        if node in ("0", "gnd", "ground"):
            continue
        if len(refs) == 1:
            issues.append({
                "severity": SEV_WARNING,
                "rule": "FLOATING_NODE",
                "message": f"Node '{node}' is connected to only one component ({refs[0]}). It may be floating.",
                "suggestion": f"Verify node '{node}' is properly connected, or it might be intentionally unused.",
            })
    return issues


def _check_voltage_source_loops(parsed: dict) -> list[dict]:
    """Check for voltage sources connected in parallel (short circuit risk)."""
    issues = []
    vs = parsed["voltage_sources"]
    for i in range(len(vs)):
        for j in range(i + 1, len(vs)):
            n1 = set(vs[i]["nodes"])
            n2 = set(vs[j]["nodes"])
            if n1 == n2:
                issues.append({
                    "severity": SEV_ERROR,
                    "rule": "VSOURCE_PARALLEL",
                    "message": (
                        f"Voltage sources {vs[i]['refdes']} and {vs[j]['refdes']} "
                        f"share the same nodes {n1}. Parallel voltage sources cause convergence failure."
                    ),
                    "suggestion": "Remove one source or add a small series resistance.",
                })
    return issues


def _check_resistor_values(parsed: dict) -> list[dict]:
    """Check for extreme or suspicious resistor values."""
    issues = []
    for r in parsed["resistors"]:
        val = r.get("value")
        if val is None:
            continue
        if val <= 0:
            issues.append({
                "severity": SEV_ERROR,
                "rule": "R_NEGATIVE",
                "message": f"{r['refdes']} has non-positive value ({val}Ω). Must be > 0.",
                "suggestion": "Use a positive resistance value.",
            })
        elif val < 0.001:
            issues.append({
                "severity": SEV_WARNING,
                "rule": "R_VERY_LOW",
                "message": f"{r['refdes']} = {val}Ω is extremely low (< 1mΩ). May cause convergence issues.",
                "suggestion": "Use minimum ~1Ω unless this is intentional.",
            })
        elif val > 1e12:
            issues.append({
                "severity": SEV_WARNING,
                "rule": "R_VERY_HIGH",
                "message": f"{r['refdes']} = {val:.0e}Ω is extremely high (> 1TΩ). May cause precision issues.",
                "suggestion": "Values above 100MΩ often cause numerical problems.",
            })
    return issues


def _check_power_budget(parsed: dict, max_power: float) -> list[dict]:
    """Estimate max power budget from voltage sources and load resistors.

    Very rough: P ≈ V²/R for each source-to-ground resistive path.
    """
    issues = []
    # Find max supply voltage
    max_v = 0.0
    for vs in parsed["voltage_sources"]:
        val = vs.get("value", "")
        # Try to extract DC value
        m = re.search(r'DC\s+([0-9.eE+-]+)', val, re.IGNORECASE)
        if m:
            try:
                max_v = max(max_v, abs(float(m.group(1))))
            except ValueError:
                pass
        else:
            # Try plain number
            try:
                max_v = max(max_v, abs(float(val)))
            except ValueError:
                pass

    if max_v == 0:
        return issues

    # Find smallest load resistance
    min_r = None
    for r in parsed["resistors"]:
        val = r.get("value")
        if val and val > 0:
            if min_r is None or val < min_r:
                min_r = val

    if min_r and min_r > 0:
        peak_power = (max_v ** 2) / min_r
        if peak_power > max_power:
            issues.append({
                "severity": SEV_WARNING,
                "rule": "POWER_BUDGET",
                "message": (
                    f"Estimated peak power {peak_power:.2f}W "
                    f"(V={max_v}V, R_min={min_r}Ω) exceeds limit {max_power}W."
                ),
                "suggestion": "Check load resistance values to avoid excessive power dissipation.",
            })

    return issues


def _check_digital_outputs(parsed: dict) -> list[dict]:
    """Check that XSPICE digital outputs have pull-down or pull-up resistors."""
    issues = []
    # Find XSPICE A-devices
    a_devices = [c for c in parsed["components"] if c["refdes"].startswith("A")]
    for ad in a_devices:
        # Get output node (typically last node before model name)
        nodes = ad["nodes"]
        if not nodes:
            continue
        out_node = nodes[-1]  # Rough heuristic
        # Check if there's a resistor from out_node to ground or supply
        has_pull = False
        for r in parsed["resistors"]:
            if out_node in r["nodes"]:
                other = [n for n in r["nodes"] if n != out_node]
                if other and other[0] in ("0", "gnd", "ground", "vcc", "vdd"):
                    has_pull = True
                    break
        if not has_pull:
            issues.append({
                "severity": SEV_INFO,
                "rule": "DIGITAL_PULLDOWN",
                "message": (
                    f"XSPICE device {ad['refdes']}: output node '{out_node}' has no pull-down/pull-up resistor. "
                    f"Consider adding a ~100kΩ resistor to ground or VCC for simulation stability."
                ),
                "suggestion": f"Add: R_pd {out_node} 0 100000",
            })
    return issues


def _check_undriven_inputs(parsed: dict) -> list[dict]:
    """Check for nodes that are only read (no source driving them)."""
    issues = []
    # Nodes driven by a source: voltage sources or controlled sources
    driven = set()
    for vs in parsed["voltage_sources"]:
        if vs["nodes"]:
            driven.add(vs["nodes"][0])  # positive terminal
    for c in parsed["components"]:
        if c["refdes"].startswith("E"):
            # VCVS output
            if len(c["nodes"]) >= 2:
                driven.add(c["nodes"][0])

    # All other nodes need at least one driving component or might be floating
    # This is a very rough check
    for node, refs in parsed["node_connections"].items():
        if node in ("0", "gnd", "ground"):
            continue
        if node.lower() in ("vcc", "vdd", "vss", "vee"):
            if node not in driven:
                issues.append({
                    "severity": SEV_WARNING,
                    "rule": "SUPPLY_UNDRIVEN",
                    "message": (
                        f"Power rail node '{node}' referenced but no voltage source found. "
                        f"It needs a voltage source like V_{node} {node} 0 DC value."
                    ),
                    "suggestion": f"Add: V_{node} {node} 0 DC 5  (or appropriate value)",
                })
    return issues


# ────────────────────────────────────────────────────────────
# Additional checks
# ────────────────────────────────────────────────────────────

def _check_missing_end(netlist: str) -> list[dict]:
    """Check that netlist ends with .end directive."""
    issues = []
    stripped = netlist.strip()
    if not stripped.lower().endswith(".end"):
        issues.append({
            "severity": SEV_ERROR,
            "rule": "MISSING_END",
            "message": "Netlist does not end with .end directive. SPICE requires .end as the last line.",
            "suggestion": "Add '.end' as the last line of the netlist.",
        })
    return issues


def _check_subcircuit_refs(netlist: str, parsed: dict) -> list[dict]:
    """Check that all subcircuit instantiations reference defined subcircuits."""
    issues = []
    # Collect .subckt definitions
    defined_subckts: set[str] = set()
    for raw_line in netlist.strip().splitlines():
        line = raw_line.strip().lower()
        if line.startswith(".subckt"):
            parts = line.split()
            if len(parts) >= 2:
                defined_subckts.add(parts[1])

    # Find X instances
    for comp in parsed["components"]:
        refdes = comp["refdes"]
        if refdes.upper().startswith("X"):
            # Last token on the line is the subcircuit name
            parts = comp["line"].split()
            if len(parts) >= 3:
                subckt_name = parts[-1].lower()
                if subckt_name not in defined_subckts:
                    issues.append({
                        "severity": SEV_ERROR,
                        "rule": "SUBCKT_UNDEFINED",
                        "message": (
                            f"{refdes} references subcircuit '{parts[-1]}' which is not defined "
                            f"in this netlist."
                        ),
                        "suggestion": f"Add a .subckt {parts[-1]} definition, or check the name spelling.",
                    })
    return issues


def _check_ac_bias(parsed: dict) -> list[dict]:
    """Check for circuits that have AC sources but may lack DC bias."""
    issues = []
    has_ac_source = False
    has_dc_source = False

    for vs in parsed["voltage_sources"]:
        val = vs.get("value", "").strip().upper()
        if "SIN" in val or "AC" in val:
            has_ac_source = True
        if val.startswith("DC") or re.match(r'^[+-]?\d', val):
            has_dc_source = True

    # If there are AC sources but no separate DC bias, warn
    if has_ac_source and not has_dc_source:
        # Check if any AC source has a DC offset (e.g., SIN(2.5 1 1000))
        has_offset = False
        for vs in parsed["voltage_sources"]:
            val = vs.get("value", "")
            m = re.search(r'SIN\(([^)]+)\)', val, re.IGNORECASE)
            if m:
                params = m.group(1).split()
                if len(params) >= 1:
                    try:
                        offset = float(params[0])
                        if abs(offset) > 1e-12:
                            has_offset = True
                    except ValueError:
                        pass
        if not has_offset:
            issues.append({
                "severity": SEV_INFO,
                "rule": "AC_BIAS",
                "message": (
                    "Circuit has AC source(s) but no DC bias voltage found. "
                    "Active circuits (opamps, transistors) typically need DC biasing."
                ),
                "suggestion": "If using active components, add DC bias sources or use SIN(offset ...) form.",
            })
    return issues


# ────────────────────────────────────────────────────────────
# MCP Tool functions
# ────────────────────────────────────────────────────────────

def tool_check_design_rules(
    netlist: str,
    max_power_watts: float = 10.0,
    skip_rules: list[str] | None = None,
) -> dict:
    """Run design rule checks on a SPICE netlist.

    Checks applied:
    - GROUND_REF: circuit has a ground (node 0) reference
    - FLOATING_NODE: nodes with only one connection
    - VSOURCE_PARALLEL: voltage sources connected in parallel
    - R_NEGATIVE / R_VERY_LOW / R_VERY_HIGH: suspicious resistor values
    - POWER_BUDGET: estimated power exceeds limit
    - DIGITAL_PULLDOWN: XSPICE outputs without pull-down/pull-up resistors
    - SUPPLY_UNDRIVEN: power rail nodes without voltage sources
    - MISSING_END: netlist doesn't end with .end
    - SUBCKT_UNDEFINED: subcircuit instantiations referencing undefined .subckt
    - AC_BIAS: AC sources present but no DC bias found

    Args:
        netlist: SPICE netlist text to check
        max_power_watts: Maximum acceptable power budget (default 10W)
        skip_rules: List of rule names to skip (e.g. ["FLOATING_NODE"])

    Returns issues list with severity, rule, message, and suggestion.
    """
    if not netlist or not netlist.strip():
        return _err("Empty netlist", "E3_EMPTY")

    skip = set(skip_rules or [])
    parsed = _parse_netlist_nodes(netlist)

    all_issues = []

    checks = [
        _check_ground,
        _check_floating_nodes,
        _check_voltage_source_loops,
        _check_resistor_values,
        lambda p: _check_power_budget(p, max_power_watts),
        _check_digital_outputs,
        _check_undriven_inputs,
        lambda p: _check_ac_bias(p),
    ]

    for check_fn in checks:
        issues = check_fn(parsed)
        all_issues.extend(issues)

    # Netlist-level checks (not in parsed dict)
    all_issues.extend(_check_missing_end(netlist))
    all_issues.extend(_check_subcircuit_refs(netlist, parsed))

    # Filter out skipped rules
    if skip:
        all_issues = [i for i in all_issues if i["rule"] not in skip]

    # Categorize
    errors = [i for i in all_issues if i["severity"] == SEV_ERROR]
    warnings = [i for i in all_issues if i["severity"] == SEV_WARNING]
    infos = [i for i in all_issues if i["severity"] == SEV_INFO]

    return _ok({
        "issues": all_issues,
        "summary": {
            "total": len(all_issues),
            "errors": len(errors),
            "warnings": len(warnings),
            "info": len(infos),
            "pass": len(errors) == 0,
        },
        "circuit_stats": {
            "num_components": len(parsed["components"]),
            "num_nodes": len(parsed["node_connections"]),
            "num_voltage_sources": len(parsed["voltage_sources"]),
            "num_resistors": len(parsed["resistors"]),
            "has_ground": parsed["has_ground"],
        },
    })
