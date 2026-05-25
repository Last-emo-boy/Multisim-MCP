import math

import pytest

from multisim_mcp.tools.circuit_templates import (
    tool_get_circuit_template,
    tool_list_circuit_templates,
)
from multisim_mcp.tools.design_checks import tool_check_design_rules
from multisim_mcp.tools.netlist_builder import tool_build_netlist
from multisim_mcp.tools.signal_measure import compute_gain, compute_measurements


def test_build_netlist_returns_spice_and_commands():
    result = tool_build_netlist(
        title="Voltage divider",
        components=[
            {"type": "V", "refdes": "V1", "nplus": "in", "nminus": "0", "value": "DC 5"},
            {"type": "R", "refdes": "R1", "n1": "in", "n2": "out", "value": 10000},
            {"type": "R", "refdes": "R2", "n1": "out", "n2": "0", "value": 10000},
        ],
        output_nodes=["out"],
    )

    assert result["ok"] is True
    assert result["data"]["commands"] == ["op", "print $out"]
    assert result["data"]["summary"]["num_components"] == 3
    assert "V1 in 0 DC 5" in result["data"]["netlist"]
    assert "R1 in out 10000" in result["data"]["netlist"]
    assert result["data"]["netlist"].strip().endswith(".end")


def test_design_rules_report_missing_ground_and_end_directive():
    result = tool_check_design_rules("R1 in out 1000")

    assert result["ok"] is True
    rules = {issue["rule"] for issue in result["data"]["issues"]}
    assert "GROUND_REF" in rules
    assert "MISSING_END" in rules
    assert result["data"]["summary"]["pass"] is False


def test_circuit_template_generates_transient_netlist_with_overrides():
    listing = tool_list_circuit_templates("opamp")
    assert listing["ok"] is True
    assert any(t["id"] == "inverting_amp" for t in listing["data"]["templates"])

    result = tool_get_circuit_template(
        "inverting_amp",
        analysis="tran",
        overrides={"R1": 5000, "Rf": 50000, "freq": 2000},
    )

    assert result["ok"] is True
    assert "R1 in inv 5000" in result["data"]["netlist"]
    assert "Rf inv out 50000" in result["data"]["netlist"]
    assert result["data"]["commands"][0].startswith("tran ")
    assert result["data"]["commands"][1] == "print $out $in"


def test_signal_measurements_and_gain_for_sine_wave():
    samples = 200
    frequency = 1000.0
    duration = 3.0 / frequency
    time = [duration * i / (samples - 1) for i in range(samples)]
    input_values = [math.sin(2 * math.pi * frequency * t) for t in time]
    output_values = [-2.0 * v for v in input_values]

    measurements = compute_measurements(time, input_values, metrics=["vpp", "rms", "frequency"])
    gain = compute_gain(input_values, output_values, time)

    assert measurements["vpp"] == pytest.approx(2.0, abs=2e-3)
    assert measurements["rms"] == pytest.approx(1 / math.sqrt(2), rel=2e-2)
    assert measurements["frequency"] == pytest.approx(frequency, rel=2e-2)
    assert gain["voltage_gain"] == pytest.approx(2.0, rel=1e-9)
    assert gain["gain_db"] == pytest.approx(20 * math.log10(2), rel=1e-9)
    assert gain["phase_inverted"] is True
