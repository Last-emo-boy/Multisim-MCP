"""
Block-level Simulation Pipeline & .ms14 Design Template Guide.

Provides tools for:
1. Simulating individual circuit blocks and verifying outputs (P2)
2. Listing available .ms14 design templates and scaffold workflows (P1)
"""

from __future__ import annotations

import json
import os

from ..models import ToolResponse


def _ok(data: dict | None = None) -> dict:
    return ToolResponse(ok=True, data=data or {}).model_dump()


def _err(msg: str, code: str = "ERROR", recovery: str = "") -> dict:
    return ToolResponse(
        ok=False, error_code=code, error_message=msg, suggested_recovery=recovery,
    ).model_dump()


# ────────────────────────────────────────────────────────────
# .ms14 Design Template Catalog (P1)
# ────────────────────────────────────────────────────────────
# Pre-built .ms14 designs with known component topology.
# User must create these in Multisim GUI; we provide metadata
# that enables open → replace_component → set_rlc_value workflows.

DESIGN_TEMPLATES: list[dict] = [
    {
        "id": "inverting_amp_1",
        "name": "Inverting Amplifier (1-stage)",
        "description": "Single op-amp inverting amplifier with Ri, Rf, and voltage probes on input and output. Ready for replace_component to swap op-amp model.",
        "category": "opamp",
        "filename": "inverting_amp.ms14",
        "components": {
            "U1": {"type": "OPAMP", "description": "Op-amp (replaceable)", "default": "uA741"},
            "R1": {"type": "RESISTOR", "description": "Input resistor Ri", "default_value": 10000},
            "R2": {"type": "RESISTOR", "description": "Feedback resistor Rf", "default_value": 100000},
        },
        "probes": ["Probe_out", "Probe_in"],
        "workflow": [
            "1. open_design(path='inverting_amp.ms14')",
            "2. set_rlc_value('R1', new_value) to change input resistor",
            "3. set_rlc_value('R2', new_value) to change feedback resistor",
            "4. replace_component('U1', ...) to swap op-amp model",
            "5. run_transient or run_dc_operating_point for analysis",
        ],
    },
    {
        "id": "voltage_divider_1",
        "name": "Voltage Divider (2-resistor)",
        "description": "Simple voltage divider with DC source, R1, R2, and output probe.",
        "category": "basic",
        "filename": "voltage_divider.ms14",
        "components": {
            "V1": {"type": "DC_POWER", "description": "Supply voltage"},
            "R1": {"type": "RESISTOR", "description": "Top resistor", "default_value": 10000},
            "R2": {"type": "RESISTOR", "description": "Bottom resistor", "default_value": 10000},
        },
        "probes": ["Probe_out"],
        "workflow": [
            "1. open_design(path='voltage_divider.ms14')",
            "2. set_rlc_value('R1', value) and set_rlc_value('R2', value)",
            "3. run_dc_operating_point(['Probe_out'])",
        ],
    },
    {
        "id": "rc_filter_1",
        "name": "RC Low-Pass Filter",
        "description": "First-order RC low-pass filter with AC source and output probe. Ready for AC sweep analysis.",
        "category": "filter",
        "filename": "rc_lowpass.ms14",
        "components": {
            "V1": {"type": "AC_POWER", "description": "AC signal source"},
            "R1": {"type": "RESISTOR", "description": "Series resistor", "default_value": 1000},
            "C1": {"type": "CAPACITOR", "description": "Shunt capacitor", "default_value": 1e-7},
        },
        "probes": ["Probe_out", "Probe_in"],
        "workflow": [
            "1. open_design(path='rc_lowpass.ms14')",
            "2. set_rlc_value('R1', value) and set_rlc_value('C1', value)",
            "3. run_ac_sweep(['Probe_out'], start_frequency=1, stop_frequency=1e6)",
        ],
    },
    {
        "id": "digital_logic_4bit_adder",
        "name": "4-bit Binary Adder (74LS283)",
        "description": "4-bit full adder using 74LS283. Has DIP switches for inputs and LED indicators for outputs.",
        "category": "digital",
        "filename": "4bit_adder.ms14",
        "components": {
            "U1": {"type": "74LS283", "description": "4-bit binary full adder"},
        },
        "probes": [],
        "workflow": [
            "1. open_design(path='4bit_adder.ms14')",
            "2. Use SPICE analysis via run_spice for programmatic testing",
            "3. Or use interactive simulation with Multisim's virtual instruments",
        ],
    },
    {
        "id": "counter_7seg",
        "name": "BCD Counter with 7-Segment Display",
        "description": "74LS190 decade counter → 74LS47 decoder → 7-segment display with clock source.",
        "category": "digital",
        "filename": "counter_7seg.ms14",
        "components": {
            "U1": {"type": "74LS190", "description": "BCD decade counter"},
            "U2": {"type": "74LS47", "description": "BCD to 7-segment decoder"},
        },
        "probes": [],
        "workflow": [
            "1. open_design(path='counter_7seg.ms14')",
            "2. run_simulation() to see the counter in action",
            "3. Use oscilloscope tool to capture output waveforms",
        ],
    },
]


def tool_list_design_templates(category: str = "all") -> dict:
    """List available pre-built .ms14 design templates.

    These are Multisim schematic files with known component topology,
    enabling open → set_rlc_value/replace_component → simulate workflows.

    Note: The .ms14 files must exist on disk. This catalog describes
    their structure so the agent can work with them programmatically.

    Categories: opamp, filter, basic, digital, or 'all'.
    """
    if category == "all":
        templates = DESIGN_TEMPLATES
    else:
        templates = [t for t in DESIGN_TEMPLATES if t.get("category") == category]

    return _ok({
        "templates": [
            {
                "id": t["id"],
                "name": t["name"],
                "description": t["description"],
                "category": t["category"],
                "filename": t["filename"],
                "component_count": len(t.get("components", {})),
                "probe_count": len(t.get("probes", [])),
            }
            for t in templates
        ],
        "count": len(templates),
        "note": "Use get_design_template_details(id) for full component/workflow info.",
    })


def tool_get_design_template_details(template_id: str) -> dict:
    """Get detailed information about a .ms14 design template.

    Returns component topology, probe names, adjustable parameters,
    and a step-by-step workflow guide for using the template with
    MCP tools (open_design, set_rlc_value, replace_component, etc.).
    """
    tmpl = None
    for t in DESIGN_TEMPLATES:
        if t["id"] == template_id:
            tmpl = t
            break

    if not tmpl:
        return _err(
            f"Template '{template_id}' not found",
            "E3_NOT_FOUND",
            "Use list_design_templates() to see available templates.",
        )

    return _ok({
        "id": tmpl["id"],
        "name": tmpl["name"],
        "description": tmpl["description"],
        "category": tmpl["category"],
        "filename": tmpl["filename"],
        "components": tmpl["components"],
        "probes": tmpl["probes"],
        "workflow": tmpl["workflow"],
    })


# ────────────────────────────────────────────────────────────
# Block-Level Simulation Pipeline (P2)
# ────────────────────────────────────────────────────────────

def tool_simulate_block(
    block_name: str,
    netlist: str,
    commands: list[str],
    expected_outputs: dict[str, dict] | None = None,
    tolerance_percent: float = 5.0,
) -> dict:
    """Simulate a circuit block and verify outputs against expected values.

    This wraps ``run_spice`` with automatic verification. Use it to test
    individual functional blocks before combining them into larger systems.

    Args:
        block_name: Human-readable block identifier (e.g., "input_stage")
        netlist: SPICE netlist for the block
        commands: Nutmeg commands (same as run_spice)
        expected_outputs: Expected measurement values for verification.
            Format: ``{"$out": {"expected": -10.0, "unit": "V"},
                       "$gain": {"expected": 10.0, "check": "abs"}}``
            Optional — if not provided, just runs and returns results.
        tolerance_percent: Tolerance for pass/fail comparison (default 5%)

    Returns block simulation results with pass/fail verification.

    Typical workflow:
      1. simulate_block("input_stage", netlist1, commands1, expected1)
      2. simulate_block("gain_stage", netlist2, commands2, expected2)
      3. simulate_block("full_circuit", combined_netlist, commands, expected_full)
    """
    # Import spice_tools at call time to avoid circular import
    from . import spice_tools

    # Run simulation
    result = spice_tools.tool_run_spice(netlist, commands)

    if not result.get("ok"):
        return _err(
            f"Block '{block_name}' simulation failed: {result.get('error_message', 'unknown')}",
            "E4_BLOCK_SIM_FAILED",
            result.get("suggested_recovery", "Check netlist and commands."),
        )

    sim_data = result.get("data", {})
    results_list = sim_data.get("results", [])

    # If no expected outputs, just return results
    if not expected_outputs:
        return _ok({
            "block_name": block_name,
            "status": "simulated",
            "results": results_list,
            "verification": None,
            "message": f"Block '{block_name}' simulated successfully. No verification targets set.",
        })

    # Verify outputs
    verifications = []
    all_pass = True

    # Flatten results into a single dict (take last result set)
    measured_flat = {}
    for r in results_list:
        if isinstance(r, dict):
            for k, v in r.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, (int, float)):
                    measured_flat[k] = v

    for node, spec in expected_outputs.items():
        expected_val = spec.get("expected")
        check_mode = spec.get("check", "value")  # "value", "abs", "sign"
        unit = spec.get("unit", "")
        measured_val = measured_flat.get(node)

        v_entry = {
            "node": node,
            "expected": expected_val,
            "measured": measured_val,
            "unit": unit,
        }

        if measured_val is None:
            v_entry["pass"] = False
            v_entry["error"] = f"Node {node} not found in results"
            all_pass = False
        elif expected_val is not None:
            if check_mode == "abs":
                actual_check = abs(measured_val)
                expected_check = abs(expected_val)
            elif check_mode == "sign":
                actual_check = 1 if measured_val > 0 else (-1 if measured_val < 0 else 0)
                expected_check = 1 if expected_val > 0 else (-1 if expected_val < 0 else 0)
                v_entry["pass"] = actual_check == expected_check
                verifications.append(v_entry)
                if not v_entry["pass"]:
                    all_pass = False
                continue
            else:
                actual_check = measured_val
                expected_check = expected_val

            if expected_check == 0:
                v_entry["pass"] = abs(actual_check) < 0.001
            else:
                error_pct = abs((actual_check - expected_check) / expected_check) * 100
                v_entry["error_percent"] = round(error_pct, 2)
                v_entry["pass"] = error_pct <= tolerance_percent

            if not v_entry["pass"]:
                all_pass = False

        verifications.append(v_entry)

    return _ok({
        "block_name": block_name,
        "status": "pass" if all_pass else "fail",
        "results": results_list,
        "verification": {
            "checks": verifications,
            "all_pass": all_pass,
            "tolerance_percent": tolerance_percent,
        },
        "message": (
            f"Block '{block_name}': ALL CHECKS PASSED"
            if all_pass
            else f"Block '{block_name}': {sum(1 for v in verifications if not v.get('pass'))} check(s) FAILED"
        ),
    })


def tool_simulate_pipeline(
    blocks: list[dict],
    tolerance_percent: float = 5.0,
) -> dict:
    """Run a sequence of block simulations as a pipeline.

    Each block is simulated independently. Results include per-block
    pass/fail status and an overall pipeline status.

    Args:
        blocks: List of block specifications, each with:
            - name: block identifier
            - netlist: SPICE netlist
            - commands: nutmeg commands
            - expected_outputs: optional verification targets (same as simulate_block)
        tolerance_percent: Tolerance for pass/fail comparison

    Example:
        simulate_pipeline(blocks=[
            {"name": "bias_stage", "netlist": "...", "commands": ["op", "print $vout"],
             "expected_outputs": {"$vout": {"expected": 2.5, "unit": "V"}}},
            {"name": "gain_stage", "netlist": "...", "commands": ["op", "print $out"],
             "expected_outputs": {"$out": {"expected": -10.0, "unit": "V"}}},
        ])
    """
    if not blocks:
        return _err("Empty blocks list", "E3_EMPTY")

    block_results = []
    all_pass = True

    for block_spec in blocks:
        name = block_spec.get("name", f"block_{len(block_results) + 1}")
        netlist = block_spec.get("netlist", "")
        commands = block_spec.get("commands", ["op"])
        expected = block_spec.get("expected_outputs")

        if not netlist:
            block_results.append({
                "block_name": name,
                "status": "skipped",
                "message": "Empty netlist — skipped",
            })
            continue

        result = tool_simulate_block(
            block_name=name,
            netlist=netlist,
            commands=commands,
            expected_outputs=expected,
            tolerance_percent=tolerance_percent,
        )

        status = "error"
        if result.get("ok"):
            data = result.get("data", {})
            status = data.get("status", "unknown")
            block_results.append(data)
        else:
            block_results.append({
                "block_name": name,
                "status": "error",
                "message": result.get("error_message", "Unknown error"),
            })

        if status not in ("pass", "simulated"):
            all_pass = False

    passed = sum(1 for b in block_results if b.get("status") in ("pass", "simulated"))
    failed = sum(1 for b in block_results if b.get("status") == "fail")
    errors = sum(1 for b in block_results if b.get("status") == "error")

    return _ok({
        "pipeline_status": "pass" if all_pass else "fail",
        "blocks": block_results,
        "summary": {
            "total": len(block_results),
            "passed": passed,
            "failed": failed,
            "errors": errors,
        },
        "message": (
            f"Pipeline: {passed}/{len(block_results)} blocks passed"
            + ("" if all_pass else f", {failed} failed, {errors} errors")
        ),
    })
