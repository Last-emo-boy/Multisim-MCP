"""
Circuit Template Library - pre-built SPICE netlists for common circuits.

Each template provides a parameterizable netlist, metadata, typical values,
and ready-to-use nutmeg commands for analysis.
"""

from __future__ import annotations

from ..models import ToolResponse


def _ok(data: dict | None = None) -> dict:
    return ToolResponse(ok=True, data=data or {}).model_dump()


def _err(msg: str, code: str = "ERROR") -> dict:
    return ToolResponse(ok=False, error_code=code, error_message=msg).model_dump()


# ────────────────────────────────────────────────────────────
# Template definitions
# ────────────────────────────────────────────────────────────

TEMPLATES: dict[str, dict] = {
    # ── Opamp Circuits ──────────────────────────────────────
    "inverting_amp": {
        "name": "Inverting Amplifier",
        "name_zh": "反相比例运算放大器",
        "category": "opamp",
        "description": "Op-amp inverting amplifier. Gain = -Rf/R1.",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Input resistor"},
            "Rf": {"default": 100000, "unit": "Ω", "description": "Feedback resistor"},
            "Vin_dc": {"default": 0.1, "unit": "V", "description": "DC input voltage (for op analysis)"},
            "Vin_ac": {"default": 0.1, "unit": "V", "description": "AC amplitude (for tran analysis)"},
            "freq": {"default": 1000, "unit": "Hz", "description": "Signal frequency (for tran analysis)"},
        },
        "nodes": {"in": "Input node", "inv": "Inverting input (virtual ground)", "out": "Output node"},
        "gain_formula": "-Rf / R1",
        "netlist_dc": (
            "* Inverting Amplifier - DC analysis\n"
            "V1 in 0 DC {Vin_dc}\n"
            "R1 in inv {R1}\n"
            "Rf inv out {Rf}\n"
            "E1 out 0 0 inv 200000\n"
            ".end\n"
        ),
        "netlist_tran": (
            "* Inverting Amplifier - Transient analysis\n"
            "V1 in 0 SIN(0 {Vin_ac} {freq})\n"
            "R1 in inv {R1}\n"
            "Rf inv out {Rf}\n"
            "E1 out 0 0 inv 200000\n"
            ".end\n"
        ),
        "suggested_commands_dc": ["op", "print $out $in"],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in"],
    },

    "noninverting_amp": {
        "name": "Non-Inverting Amplifier",
        "name_zh": "同相比例运算放大器",
        "category": "opamp",
        "description": "Op-amp non-inverting amplifier. Gain = 1 + Rf/R1.",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Ground resistor"},
            "Rf": {"default": 90000, "unit": "Ω", "description": "Feedback resistor"},
            "Vin_dc": {"default": 0.1, "unit": "V", "description": "DC input voltage"},
            "Vin_ac": {"default": 0.1, "unit": "V", "description": "AC amplitude"},
            "freq": {"default": 1000, "unit": "Hz", "description": "Signal frequency"},
        },
        "nodes": {"inp": "Non-inverting input", "inv": "Inverting input", "out": "Output node"},
        "gain_formula": "1 + Rf / R1",
        "netlist_dc": (
            "* Non-Inverting Amplifier - DC analysis\n"
            "V1 inp 0 DC {Vin_dc}\n"
            "R1 inv 0 {R1}\n"
            "Rf inv out {Rf}\n"
            "E1 out 0 inp inv 200000\n"
            ".end\n"
        ),
        "netlist_tran": (
            "* Non-Inverting Amplifier - Transient analysis\n"
            "V1 inp 0 SIN(0 {Vin_ac} {freq})\n"
            "R1 inv 0 {R1}\n"
            "Rf inv out {Rf}\n"
            "E1 out 0 inp inv 200000\n"
            ".end\n"
        ),
        "suggested_commands_dc": ["op", "print $out $inp"],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $inp"],
    },

    "voltage_follower": {
        "name": "Voltage Follower (Unity Gain Buffer)",
        "name_zh": "电压跟随器",
        "category": "opamp",
        "description": "Op-amp voltage follower. Gain = 1. Output follows input exactly.",
        "parameters": {
            "Vin_dc": {"default": 1.0, "unit": "V", "description": "DC input voltage"},
            "Vin_ac": {"default": 1.0, "unit": "V", "description": "AC amplitude"},
            "freq": {"default": 1000, "unit": "Hz", "description": "Signal frequency"},
        },
        "nodes": {"inp": "Input node", "out": "Output node"},
        "gain_formula": "1",
        "netlist_dc": (
            "* Voltage Follower - DC analysis\n"
            "V1 inp 0 DC {Vin_dc}\n"
            "E1 out 0 inp out 200000\n"
            ".end\n"
        ),
        "netlist_tran": (
            "* Voltage Follower - Transient analysis\n"
            "V1 inp 0 SIN(0 {Vin_ac} {freq})\n"
            "E1 out 0 inp out 200000\n"
            ".end\n"
        ),
        "suggested_commands_dc": ["op", "print $out $inp"],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $inp"],
    },

    "summing_amp": {
        "name": "Summing Amplifier",
        "name_zh": "加法运算放大器",
        "category": "opamp",
        "description": "Inverting summing amplifier with two inputs. Vout = -Rf(V1/R1 + V2/R2).",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Input 1 resistor"},
            "R2": {"default": 10000, "unit": "Ω", "description": "Input 2 resistor"},
            "Rf": {"default": 10000, "unit": "Ω", "description": "Feedback resistor"},
            "V1_dc": {"default": 1.0, "unit": "V", "description": "Input 1 DC voltage"},
            "V2_dc": {"default": 2.0, "unit": "V", "description": "Input 2 DC voltage"},
        },
        "nodes": {"in1": "Input 1", "in2": "Input 2", "inv": "Summing junction", "out": "Output"},
        "gain_formula": "Vout = -Rf * (V1/R1 + V2/R2)",
        "netlist_dc": (
            "* Summing Amplifier - DC analysis\n"
            "V1 in1 0 DC {V1_dc}\n"
            "V2 in2 0 DC {V2_dc}\n"
            "R1 in1 inv {R1}\n"
            "R2 in2 inv {R2}\n"
            "Rf inv out {Rf}\n"
            "E1 out 0 0 inv 200000\n"
            ".end\n"
        ),
        "netlist_tran": None,
        "suggested_commands_dc": ["op", "print $out $in1 $in2"],
        "suggested_commands_tran": [],
    },

    "differential_amp": {
        "name": "Differential Amplifier",
        "name_zh": "差分运算放大器",
        "category": "opamp",
        "description": "Single op-amp differential amplifier. When R1=R2 and Rf=Rg: Vout = (Rf/R1)(V2-V1).",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Inverting input resistor"},
            "Rf": {"default": 100000, "unit": "Ω", "description": "Feedback resistor"},
            "R2": {"default": 10000, "unit": "Ω", "description": "Non-inverting input resistor"},
            "Rg": {"default": 100000, "unit": "Ω", "description": "Non-inverting ground resistor"},
            "V1_dc": {"default": 1.0, "unit": "V", "description": "Inverting input voltage"},
            "V2_dc": {"default": 2.0, "unit": "V", "description": "Non-inverting input voltage"},
        },
        "nodes": {"in1": "Inverting side input", "in2": "Non-inverting side input", "inv": "Inverting node", "inp": "Non-inverting node", "out": "Output"},
        "gain_formula": "(Rf/R1) * (V2 - V1)  [when R1=R2 and Rf=Rg]",
        "netlist_dc": (
            "* Differential Amplifier - DC analysis\n"
            "VA in1 0 DC {V1_dc}\n"
            "VB in2 0 DC {V2_dc}\n"
            "R1 in1 inv {R1}\n"
            "Rf inv out {Rf}\n"
            "R2 in2 inp {R2}\n"
            "Rg inp 0 {Rg}\n"
            "E1 out 0 inp inv 200000\n"
            ".end\n"
        ),
        "netlist_tran": None,
        "suggested_commands_dc": ["op", "print $out $in1 $in2"],
        "suggested_commands_tran": [],
    },

    "integrator": {
        "name": "Integrator",
        "name_zh": "积分运算放大器",
        "category": "opamp",
        "description": "Op-amp integrator. Vout = -(1/RC) ∫ Vin dt. Square wave in → triangle wave out.",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Input resistor"},
            "C1": {"default": 1e-7, "unit": "F", "description": "Feedback capacitor (100nF)"},
            "Vin_ac": {"default": 1.0, "unit": "V", "description": "AC amplitude"},
            "freq": {"default": 1000, "unit": "Hz", "description": "Signal frequency"},
        },
        "nodes": {"in": "Input node", "inv": "Inverting input", "out": "Output node"},
        "gain_formula": "-1 / (2π f R1 C1)  at frequency f",
        "netlist_tran": (
            "* Integrator - Transient analysis\n"
            "V1 in 0 PULSE(-{Vin_ac} {Vin_ac} 0 1e-9 1e-9 {half_period} {period})\n"
            "R1 in inv {R1}\n"
            "C1 inv out {C1}\n"
            "E1 out 0 0 inv 200000\n"
            ".end\n"
        ),
        "netlist_dc": None,
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in"],
    },

    "differentiator": {
        "name": "Differentiator",
        "name_zh": "微分运算放大器",
        "category": "opamp",
        "description": "Op-amp differentiator. Vout = -RC dVin/dt. Triangle wave in → square wave out.",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Feedback resistor"},
            "C1": {"default": 1e-8, "unit": "F", "description": "Input capacitor (10nF)"},
            "Vin_ac": {"default": 0.1, "unit": "V", "description": "AC amplitude"},
            "freq": {"default": 1000, "unit": "Hz", "description": "Signal frequency"},
        },
        "nodes": {"in": "Input node", "inv": "Inverting input", "out": "Output node"},
        "gain_formula": "-2π f R1 C1  at frequency f",
        "netlist_tran": (
            "* Differentiator - Transient analysis\n"
            "V1 in 0 SIN(0 {Vin_ac} {freq})\n"
            "C1 in inv {C1}\n"
            "R1 inv out {R1}\n"
            "E1 out 0 0 inv 200000\n"
            ".end\n"
        ),
        "netlist_dc": None,
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in"],
    },

    # ── Passive Filters ────────────────────────────────────
    "rc_lowpass": {
        "name": "RC Low-Pass Filter",
        "name_zh": "RC低通滤波器",
        "category": "filter",
        "description": "First-order RC low-pass filter. Cutoff = 1/(2πRC).",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Series resistance"},
            "C1": {"default": 1e-8, "unit": "F", "description": "Shunt capacitance (10nF)"},
            "Vin_ac": {"default": 1.0, "unit": "V", "description": "AC amplitude"},
            "freq": {"default": 1000, "unit": "Hz", "description": "Signal frequency"},
        },
        "nodes": {"in": "Input", "out": "Output (across C)"},
        "gain_formula": "1 / sqrt(1 + (2πfRC)²)",
        "netlist_tran": (
            "* RC Low-Pass Filter - Transient\n"
            "V1 in 0 SIN(0 {Vin_ac} {freq})\n"
            "R1 in out {R1}\n"
            "C1 out 0 {C1}\n"
            ".end\n"
        ),
        "netlist_dc": (
            "* RC Low-Pass Filter - DC\n"
            "V1 in 0 DC {Vin_ac}\n"
            "R1 in out {R1}\n"
            "C1 out 0 {C1}\n"
            ".end\n"
        ),
        "suggested_commands_dc": ["op", "print $out $in"],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in"],
    },

    "rc_highpass": {
        "name": "RC High-Pass Filter",
        "name_zh": "RC高通滤波器",
        "category": "filter",
        "description": "First-order RC high-pass filter. Cutoff = 1/(2πRC).",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Shunt resistance"},
            "C1": {"default": 1e-8, "unit": "F", "description": "Series capacitance (10nF)"},
            "Vin_ac": {"default": 1.0, "unit": "V", "description": "AC amplitude"},
            "freq": {"default": 1000, "unit": "Hz", "description": "Signal frequency"},
        },
        "nodes": {"in": "Input", "out": "Output (across R)"},
        "gain_formula": "2πfRC / sqrt(1 + (2πfRC)²)",
        "netlist_tran": (
            "* RC High-Pass Filter - Transient\n"
            "V1 in 0 SIN(0 {Vin_ac} {freq})\n"
            "C1 in out {C1}\n"
            "R1 out 0 {R1}\n"
            ".end\n"
        ),
        "netlist_dc": None,
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in"],
    },

    # ── Active Filter ──────────────────────────────────────
    "active_lowpass": {
        "name": "Active Low-Pass Filter (Sallen-Key)",
        "name_zh": "有源低通滤波器 (Sallen-Key)",
        "category": "filter",
        "description": "Second-order Sallen-Key low-pass filter with unity-gain buffer.",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "First series resistor"},
            "R2": {"default": 10000, "unit": "Ω", "description": "Second series resistor"},
            "C1": {"default": 1e-8, "unit": "F", "description": "Shunt capacitor (10nF)"},
            "C2": {"default": 1e-8, "unit": "F", "description": "Feedback capacitor (10nF)"},
            "Vin_ac": {"default": 1.0, "unit": "V", "description": "AC amplitude"},
            "freq": {"default": 1000, "unit": "Hz", "description": "Signal frequency"},
        },
        "nodes": {"in": "Input", "mid": "Between R1 and R2", "inp": "Buffer input", "out": "Output"},
        "gain_formula": "fc = 1 / (2π √(R1 R2 C1 C2))",
        "netlist_tran": (
            "* Sallen-Key Low-Pass Filter - Transient\n"
            "V1 in 0 SIN(0 {Vin_ac} {freq})\n"
            "R1 in mid {R1}\n"
            "R2 mid inp {R2}\n"
            "C1 mid 0 {C1}\n"
            "C2 inp out {C2}\n"
            "E1 out 0 inp out 200000\n"
            ".end\n"
        ),
        "netlist_dc": None,
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in"],
    },

    # ── Basic Components ───────────────────────────────────
    "voltage_divider": {
        "name": "Resistive Voltage Divider",
        "name_zh": "电阻分压器",
        "category": "basic",
        "description": "Simple voltage divider. Vout = Vin × R2/(R1+R2).",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Top resistor"},
            "R2": {"default": 10000, "unit": "Ω", "description": "Bottom resistor"},
            "Vin_dc": {"default": 5.0, "unit": "V", "description": "Input voltage"},
        },
        "nodes": {"in": "Input", "out": "Divider output (R1-R2 junction)"},
        "gain_formula": "R2 / (R1 + R2)",
        "netlist_dc": (
            "* Voltage Divider - DC analysis\n"
            "V1 in 0 DC {Vin_dc}\n"
            "R1 in out {R1}\n"
            "R2 out 0 {R2}\n"
            ".end\n"
        ),
        "netlist_tran": None,
        "suggested_commands_dc": ["op", "print $out $in"],
        "suggested_commands_tran": [],
    },

    "rl_circuit": {
        "name": "RL Series Circuit",
        "name_zh": "RL串联电路",
        "category": "basic",
        "description": "Series RL circuit. Time constant τ = L/R.",
        "parameters": {
            "R1": {"default": 1000, "unit": "Ω", "description": "Series resistance"},
            "L1": {"default": 0.01, "unit": "H", "description": "Series inductance (10mH)"},
            "Vin_dc": {"default": 5.0, "unit": "V", "description": "Step voltage"},
        },
        "nodes": {"in": "Input", "mid": "R-L junction", "out": "Output (across L)"},
        "gain_formula": "τ = L/R, Vout(t) = Vin × exp(-Rt/L)",
        "netlist_tran": (
            "* RL Series Circuit - Step response\n"
            "V1 in 0 PULSE(0 {Vin_dc} 0 1e-9 1e-9 0.1 0.2)\n"
            "R1 in mid {R1}\n"
            "L1 mid 0 {L1}\n"
            ".end\n"
        ),
        "netlist_dc": (
            "* RL Series Circuit - DC\n"
            "V1 in 0 DC {Vin_dc}\n"
            "R1 in mid {R1}\n"
            "L1 mid 0 {L1}\n"
            ".end\n"
        ),
        "suggested_commands_dc": ["op", "print $in $mid"],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $in $mid"],
    },

    "rc_circuit": {
        "name": "RC Series Circuit",
        "name_zh": "RC串联电路",
        "category": "basic",
        "description": "Series RC circuit. Time constant τ = RC.",
        "parameters": {
            "R1": {"default": 10000, "unit": "Ω", "description": "Series resistance"},
            "C1": {"default": 1e-6, "unit": "F", "description": "Series capacitance (1µF)"},
            "Vin_dc": {"default": 5.0, "unit": "V", "description": "Step voltage"},
        },
        "nodes": {"in": "Input", "out": "Output (across C)"},
        "gain_formula": "τ = RC, Vout(t) = Vin × (1 - exp(-t/RC))",
        "netlist_tran": (
            "* RC Series Circuit - Step response\n"
            "V1 in 0 PULSE(0 {Vin_dc} 0 1e-9 1e-9 0.1 0.2)\n"
            "R1 in out {R1}\n"
            "C1 out 0 {C1}\n"
            ".end\n"
        ),
        "netlist_dc": (
            "* RC Series Circuit - DC\n"
            "V1 in 0 DC {Vin_dc}\n"
            "R1 in out {R1}\n"
            "C1 out 0 {C1}\n"
            ".end\n"
        ),
        "suggested_commands_dc": ["op", "print $in $out"],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $in $out"],
    },

    # ── XSPICE Digital Circuits ─────────────────────────────
    "and_gate": {
        "name": "2-Input AND Gate",
        "name_zh": "二输入与门",
        "category": "digital",
        "description": "XSPICE behavioral AND gate. Output HIGH when both inputs HIGH.",
        "parameters": {
            "rise_delay": {"default": 10e-9, "unit": "s", "description": "Rise delay"},
            "fall_delay": {"default": 10e-9, "unit": "s", "description": "Fall delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Test clock frequency"},
        },
        "nodes": {"in1": "Input A", "in2": "Input B", "out": "Output"},
        "gain_formula": "out = in1 AND in2",
        "netlist_dc": None,
        "netlist_tran": (
            "* 2-Input AND Gate - XSPICE Digital\n"
            "V1 in1 0 PULSE(0 5 0 1e-9 1e-9 {half_period} {period})\n"
            "V2 in2 0 PULSE(0 5 0 1e-9 1e-9 {half_period_2} {period_2})\n"
            "R1 in1 in1d 100\n"
            "R2 in2 in2d 100\n"
            "A1 [in1d in2d] out and_model\n"
            ".model and_model d_and(rise_delay={rise_delay} fall_delay={fall_delay} input_load=1e-12)\n"
            "R3 out 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in1 $in2"],
    },

    "or_gate": {
        "name": "2-Input OR Gate",
        "name_zh": "二输入或门",
        "category": "digital",
        "description": "XSPICE behavioral OR gate. Output HIGH when any input HIGH.",
        "parameters": {
            "rise_delay": {"default": 10e-9, "unit": "s", "description": "Rise delay"},
            "fall_delay": {"default": 10e-9, "unit": "s", "description": "Fall delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Test clock frequency"},
        },
        "nodes": {"in1": "Input A", "in2": "Input B", "out": "Output"},
        "gain_formula": "out = in1 OR in2",
        "netlist_dc": None,
        "netlist_tran": (
            "* 2-Input OR Gate - XSPICE Digital\n"
            "V1 in1 0 PULSE(0 5 0 1e-9 1e-9 {half_period} {period})\n"
            "V2 in2 0 PULSE(0 5 0 1e-9 1e-9 {half_period_2} {period_2})\n"
            "R1 in1 in1d 100\n"
            "R2 in2 in2d 100\n"
            "A1 [in1d in2d] out or_model\n"
            ".model or_model d_or(rise_delay={rise_delay} fall_delay={fall_delay} input_load=1e-12)\n"
            "R3 out 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in1 $in2"],
    },

    "not_gate": {
        "name": "Inverter (NOT Gate)",
        "name_zh": "非门 (反相器)",
        "category": "digital",
        "description": "XSPICE behavioral NOT gate (inverter).",
        "parameters": {
            "rise_delay": {"default": 10e-9, "unit": "s", "description": "Rise delay"},
            "fall_delay": {"default": 10e-9, "unit": "s", "description": "Fall delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Test clock frequency"},
        },
        "nodes": {"in": "Input", "out": "Output (inverted)"},
        "gain_formula": "out = NOT in",
        "netlist_dc": None,
        "netlist_tran": (
            "* NOT Gate (Inverter) - XSPICE Digital\n"
            "V1 in 0 PULSE(0 5 0 1e-9 1e-9 {half_period} {period})\n"
            "R1 in ind 100\n"
            "A1 ind out inv_model\n"
            ".model inv_model d_inverter(rise_delay={rise_delay} fall_delay={fall_delay} input_load=1e-12)\n"
            "R2 out 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in"],
    },

    "nand_gate": {
        "name": "2-Input NAND Gate",
        "name_zh": "二输入与非门",
        "category": "digital",
        "description": "XSPICE behavioral NAND gate. Universal gate.",
        "parameters": {
            "rise_delay": {"default": 10e-9, "unit": "s", "description": "Rise delay"},
            "fall_delay": {"default": 10e-9, "unit": "s", "description": "Fall delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Test clock frequency"},
        },
        "nodes": {"in1": "Input A", "in2": "Input B", "out": "Output"},
        "gain_formula": "out = NOT(in1 AND in2)",
        "netlist_dc": None,
        "netlist_tran": (
            "* 2-Input NAND Gate - XSPICE Digital\n"
            "V1 in1 0 PULSE(0 5 0 1e-9 1e-9 {half_period} {period})\n"
            "V2 in2 0 PULSE(0 5 0 1e-9 1e-9 {half_period_2} {period_2})\n"
            "R1 in1 in1d 100\n"
            "R2 in2 in2d 100\n"
            "A1 [in1d in2d] out nand_model\n"
            ".model nand_model d_nand(rise_delay={rise_delay} fall_delay={fall_delay} input_load=1e-12)\n"
            "R3 out 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in1 $in2"],
    },

    "xor_gate": {
        "name": "2-Input XOR Gate",
        "name_zh": "二输入异或门",
        "category": "digital",
        "description": "XSPICE behavioral XOR gate. Essential for adders.",
        "parameters": {
            "rise_delay": {"default": 10e-9, "unit": "s", "description": "Rise delay"},
            "fall_delay": {"default": 10e-9, "unit": "s", "description": "Fall delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Test clock frequency"},
        },
        "nodes": {"in1": "Input A", "in2": "Input B", "out": "Output"},
        "gain_formula": "out = in1 XOR in2",
        "netlist_dc": None,
        "netlist_tran": (
            "* 2-Input XOR Gate - XSPICE Digital\n"
            "V1 in1 0 PULSE(0 5 0 1e-9 1e-9 {half_period} {period})\n"
            "V2 in2 0 PULSE(0 5 0 1e-9 1e-9 {half_period_2} {period_2})\n"
            "R1 in1 in1d 100\n"
            "R2 in2 in2d 100\n"
            "A1 [in1d in2d] out xor_model\n"
            ".model xor_model d_xor(rise_delay={rise_delay} fall_delay={fall_delay} input_load=1e-12)\n"
            "R3 out 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $in1 $in2"],
    },

    "d_flipflop": {
        "name": "D Flip-Flop",
        "name_zh": "D触发器",
        "category": "digital",
        "description": "XSPICE D flip-flop. Captures data on clock rising edge.",
        "parameters": {
            "clk_delay": {"default": 10e-9, "unit": "s", "description": "Clock-to-Q delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Clock frequency"},
            "data_freq": {"default": 2.5e5, "unit": "Hz", "description": "Data input frequency"},
        },
        "nodes": {"data": "D input", "clk": "Clock", "q": "Q output", "qn": "Q-bar output"},
        "gain_formula": "Q follows D on rising clock edge",
        "netlist_dc": None,
        "netlist_tran": (
            "* D Flip-Flop - XSPICE Digital\n"
            "Vclk clk 0 PULSE(0 5 0 1e-9 1e-9 {clk_half} {clk_period})\n"
            "Vdata data 0 PULSE(0 5 0 1e-9 1e-9 {data_half} {data_period})\n"
            "Rclk clk clkd 100\n"
            "Rdata data datad 100\n"
            "A1 datad clkd vcc 0 q qn dff_model\n"
            ".model dff_model d_dff(clk_delay={clk_delay} ic=0)\n"
            "Vvcc vcc 0 DC 5\n"
            "Rq q 0 100k\n"
            "Rqn qn 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $q $data $clk"],
    },

    "jk_flipflop": {
        "name": "JK Flip-Flop",
        "name_zh": "JK触发器",
        "category": "digital",
        "description": "XSPICE JK flip-flop. Most versatile sequential element.",
        "parameters": {
            "clk_delay": {"default": 10e-9, "unit": "s", "description": "Clock-to-Q delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Clock frequency"},
        },
        "nodes": {"j": "J input", "k": "K input", "clk": "Clock", "q": "Q output", "qn": "Q-bar"},
        "gain_formula": "J=K=1: toggle; J=1,K=0: set; J=0,K=1: reset",
        "netlist_dc": None,
        "netlist_tran": (
            "* JK Flip-Flop (Toggle mode J=K=1) - XSPICE Digital\n"
            "Vclk clk 0 PULSE(0 5 0 1e-9 1e-9 {clk_half} {clk_period})\n"
            "Vj j 0 DC 5\n"
            "Vk k 0 DC 5\n"
            "Rclk clk clkd 100\n"
            "Rj j jd 100\n"
            "Rk k kd 100\n"
            "A1 jd clkd kd vcc 0 q qn jkff_model\n"
            ".model jkff_model d_jkff(clk_delay={clk_delay} ic=0)\n"
            "Vvcc vcc 0 DC 5\n"
            "Rq q 0 100k\n"
            "Rqn qn 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $q $qn $clk"],
    },

    "sr_latch": {
        "name": "SR Latch (NAND-based)",
        "name_zh": "SR锁存器",
        "category": "digital",
        "description": "Set-Reset latch built from cross-coupled NAND gates.",
        "parameters": {
            "rise_delay": {"default": 10e-9, "unit": "s", "description": "Gate delay"},
            "fall_delay": {"default": 10e-9, "unit": "s", "description": "Gate delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Test frequency"},
        },
        "nodes": {"s": "Set (active low)", "r": "Reset (active low)", "q": "Q output", "qn": "Q-bar"},
        "gain_formula": "S=0: Q=1; R=0: Q=0; S=R=1: hold",
        "netlist_dc": None,
        "netlist_tran": (
            "* SR Latch (NAND) - XSPICE Digital\n"
            "Vs s 0 PULSE(5 0 1e-6 1e-9 1e-9 0.5e-6 4e-6)\n"
            "Vr r 0 PULSE(5 0 3e-6 1e-9 1e-9 0.5e-6 4e-6)\n"
            "Rs s sd 100\n"
            "Rr r rd 100\n"
            "A1 [sd qn] q nand1\n"
            "A2 [rd q] qn nand2\n"
            ".model nand1 d_nand(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            ".model nand2 d_nand(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            "Rq q 0 100k\n"
            "Rqn qn 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran 1e-8 8e-6", "print $q $qn $s $r"],
    },

    "half_adder": {
        "name": "Half Adder",
        "name_zh": "半加器",
        "category": "digital",
        "description": "Half adder: Sum = A XOR B, Carry = A AND B.",
        "parameters": {
            "rise_delay": {"default": 10e-9, "unit": "s", "description": "Gate delay"},
            "fall_delay": {"default": 10e-9, "unit": "s", "description": "Gate delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Test frequency"},
        },
        "nodes": {"a": "Input A", "b": "Input B", "sum": "Sum output", "carry": "Carry output"},
        "gain_formula": "Sum = A XOR B, Carry = A AND B",
        "netlist_dc": None,
        "netlist_tran": (
            "* Half Adder - XSPICE Digital\n"
            "Va a 0 PULSE(0 5 0 1e-9 1e-9 {half_period} {period})\n"
            "Vb b 0 PULSE(0 5 0 1e-9 1e-9 {half_period_2} {period_2})\n"
            "Ra a ad 100\n"
            "Rb b bd 100\n"
            "A1 [ad bd] sum xor1\n"
            "A2 [ad bd] carry and1\n"
            ".model xor1 d_xor(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            ".model and1 d_and(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            "Rsum sum 0 100k\n"
            "Rcarry carry 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $sum $carry $a $b"],
    },

    "full_adder": {
        "name": "Full Adder",
        "name_zh": "全加器",
        "category": "digital",
        "description": "Full adder: A + B + Cin = {Cout, Sum}. Building block for multi-bit arithmetic.",
        "parameters": {
            "rise_delay": {"default": 10e-9, "unit": "s", "description": "Gate delay"},
            "fall_delay": {"default": 10e-9, "unit": "s", "description": "Gate delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Test frequency"},
        },
        "nodes": {"a": "Input A", "b": "Input B", "cin": "Carry in", "sum": "Sum output", "cout": "Carry out"},
        "gain_formula": "Sum = A XOR B XOR Cin, Cout = (A AND B) OR (Cin AND (A XOR B))",
        "netlist_dc": None,
        "netlist_tran": (
            "* Full Adder - XSPICE Digital\n"
            "Va a 0 PULSE(0 5 0 1e-9 1e-9 {half_period} {period})\n"
            "Vb b 0 PULSE(0 5 0 1e-9 1e-9 {half_period_2} {period_2})\n"
            "Vcin cin 0 PULSE(0 5 0 1e-9 1e-9 {half_period_4} {period_4})\n"
            "Ra a ad 100\n"
            "Rb b bd 100\n"
            "Rcin cin cind 100\n"
            "* XOR chain for sum\n"
            "A1 [ad bd] axb xor1\n"
            "A2 [axb cind] sum xor2\n"
            "* Carry logic\n"
            "A3 [ad bd] ab and1\n"
            "A4 [axb cind] axbc and2\n"
            "A5 [ab axbc] cout or1\n"
            ".model xor1 d_xor(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            ".model xor2 d_xor(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            ".model and1 d_and(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            ".model and2 d_and(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            ".model or1 d_or(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            "Raxb axb 0 100k\n"
            "Rsum sum 0 100k\n"
            "Rab ab 0 100k\n"
            "Raxbc axbc 0 100k\n"
            "Rcout cout 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $sum $cout $a $b $cin"],
    },

    "mux_2to1": {
        "name": "2-to-1 Multiplexer",
        "name_zh": "二选一多路复用器",
        "category": "digital",
        "description": "2-to-1 MUX: Out = Sel ? B : A. Built from gates.",
        "parameters": {
            "rise_delay": {"default": 10e-9, "unit": "s", "description": "Gate delay"},
            "fall_delay": {"default": 10e-9, "unit": "s", "description": "Gate delay"},
            "clk_freq": {"default": 1e6, "unit": "Hz", "description": "Test frequency"},
        },
        "nodes": {"a": "Input A (sel=0)", "b": "Input B (sel=1)", "sel": "Select", "out": "Output"},
        "gain_formula": "Out = (NOT sel AND A) OR (sel AND B)",
        "netlist_dc": None,
        "netlist_tran": (
            "* 2-to-1 MUX - XSPICE Digital\n"
            "Va a 0 PULSE(0 5 0 1e-9 1e-9 {half_period} {period})\n"
            "Vb b 0 PULSE(0 5 0 1e-9 1e-9 {half_period_2} {period_2})\n"
            "Vsel sel 0 PULSE(0 5 0 1e-9 1e-9 {half_period_4} {period_4})\n"
            "Ra a ad 100\n"
            "Rb b bd 100\n"
            "Rsel sel seld 100\n"
            "* NOT sel\n"
            "A1 seld nseld inv1\n"
            "* nseld AND ad\n"
            "A2 [nseld ad] sa and1\n"
            "* seld AND bd\n"
            "A3 [seld bd] sb and2\n"
            "* OR\n"
            "A4 [sa sb] out or1\n"
            ".model inv1 d_inverter(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            ".model and1 d_and(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            ".model and2 d_and(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            ".model or1 d_or(rise_delay={rise_delay} fall_delay={fall_delay})\n"
            "Rnseld nseld 0 100k\n"
            "Rsa sa 0 100k\n"
            "Rsb sb 0 100k\n"
            "Rout out 0 100k\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $a $b $sel"],
    },

    # ── Mixed Signal ────────────────────────────────────────
    "comparator": {
        "name": "Voltage Comparator",
        "name_zh": "电压比较器",
        "category": "mixed",
        "description": "Analog comparator using high-gain VCVS. Output saturates to +/-Vsat.",
        "parameters": {
            "Vref": {"default": 2.5, "unit": "V", "description": "Reference voltage"},
            "Vin_ac": {"default": 5.0, "unit": "V", "description": "Input amplitude"},
            "freq": {"default": 1000, "unit": "Hz", "description": "Input frequency"},
            "R_limit": {"default": 1000, "unit": "Ohm", "description": "Output limiting resistor"},
        },
        "nodes": {"inp": "Non-inverting input (signal)", "ref": "Reference voltage", "out": "Comparator output"},
        "gain_formula": "Vout = Vsat if Vin > Vref else -Vsat",
        "netlist_dc": None,
        "netlist_tran": (
            "* Voltage Comparator - high gain VCVS\n"
            "Vin inp 0 SIN(2.5 {Vin_ac} {freq})\n"
            "Vref ref 0 DC {Vref}\n"
            "E1 raw 0 inp ref 100000\n"
            "D1 raw out_pos dmod\n"
            "D2 out_neg raw dmod\n"
            "Vclamp_pos out_pos 0 DC 5.1\n"
            "Vclamp_neg out_neg 0 DC -0.1\n"
            "R1 raw out {R_limit}\n"
            ".model dmod d(is=1e-14)\n"
            ".end\n"
        ),
        "suggested_commands_dc": [],
        "suggested_commands_tran": ["tran {tstep} {tstop}", "print $out $inp"],
    },
}


# ────────────────────────────────────────────────────────────
# Tool functions
# ────────────────────────────────────────────────────────────

def tool_list_circuit_templates(category: str = "all") -> dict:
    """List available circuit templates.

    Returns name, description, category, gain formula, and available
    parameters for each template.
    """
    templates = []
    for key, tpl in TEMPLATES.items():
        if category != "all" and tpl.get("category") != category:
            continue
        templates.append({
            "id": key,
            "name": tpl["name"],
            "name_zh": tpl.get("name_zh", ""),
            "category": tpl["category"],
            "description": tpl["description"],
            "gain_formula": tpl.get("gain_formula", ""),
            "parameters": {
                k: {"default": v["default"], "unit": v["unit"], "description": v["description"]}
                for k, v in tpl.get("parameters", {}).items()
            },
            "has_dc": tpl.get("netlist_dc") is not None,
            "has_tran": tpl.get("netlist_tran") is not None,
        })
    return _ok({"templates": templates, "count": len(templates)})


def tool_get_circuit_template(
    template_id: str,
    analysis: str = "dc",
    overrides: dict | None = None,
) -> dict:
    """Get a ready-to-use SPICE netlist from a circuit template.

    Fills in parameter values (using defaults or overrides) and returns
    the netlist string plus suggested nutmeg commands.

    The returned ``netlist`` can be passed directly to ``run_spice`` or
    ``parameter_sweep``.

    Args:
        template_id: Template identifier (from list_circuit_templates).
        analysis: ``"dc"`` or ``"tran"`` - selects which netlist variant.
        overrides: Dict of parameter overrides, e.g. ``{"R1": 5000, "Rf": 50000}``.
    """
    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        available = ", ".join(TEMPLATES.keys())
        return _err(
            f"Unknown template '{template_id}'. Available: {available}",
            "E3_BAD_TEMPLATE",
        )

    # Select netlist variant
    if analysis == "tran":
        netlist_template = tpl.get("netlist_tran")
        commands_key = "suggested_commands_tran"
    else:
        netlist_template = tpl.get("netlist_dc")
        commands_key = "suggested_commands_dc"

    if netlist_template is None:
        other = "tran" if analysis == "dc" else "dc"
        return _err(
            f"Template '{template_id}' has no {analysis} netlist. Try analysis='{other}'.",
            "E3_NO_NETLIST",
        )

    # Build parameter values: defaults + overrides
    params: dict = {}
    for k, v in tpl.get("parameters", {}).items():
        params[k] = v["default"]
    if overrides:
        for k, v in overrides.items():
            if k in params:
                params[k] = v
            else:
                # Allow arbitrary overrides for flexibility
                params[k] = v

    # Compute derived values for transient analysis
    freq = params.get("freq", params.get("clk_freq", params.get("frequency", 1000)))
    period = 1.0 / freq if freq > 0 else 0.001
    half_period = period / 2.0
    # Reasonable defaults: tstep = period/200, tstop covers slowest signal
    tstep = period / 200.0

    # Derived: second input at half the frequency (for truth table coverage)
    params["period_2"] = period * 2
    params["half_period_2"] = period
    # Fourth: for 3-input circuits (carry-in, select)
    params["period_4"] = period * 4
    params["half_period_4"] = period * 2

    # Clock and data periods for flip-flops
    clk_freq = params.get("clk_freq", 1e6)
    params["clk_period"] = 1.0 / clk_freq if clk_freq > 0 else 1e-6
    params["clk_half"] = params["clk_period"] / 2.0
    data_freq = params.get("data_freq", clk_freq / 4)
    params["data_period"] = 1.0 / data_freq if data_freq > 0 else 4e-6
    params["data_half"] = params["data_period"] / 2.0

    # tstop should cover the slowest signal — at least 2 full cycles
    is_digital = tpl.get("category") in ("digital",)
    if is_digital:
        all_periods = [period, params["period_2"], params["period_4"],
                       params["clk_period"], params["data_period"]]
        widest = max(all_periods)
        tstop = max(2.0 * widest, 4.0 * period)
        # tstep based on the fastest signal
        tstep = min(period, params["clk_period"]) / 200.0
    else:
        tstop = 2.0 * period
        tstep = period / 200.0
        # For filter templates, ensure enough time for RC settling (5τ)
        if tpl.get("category") == "filter":
            r_val = params.get("R1", 10000)
            c_val = params.get("C1", 1e-8)
            try:
                tau = float(r_val) * float(c_val)
                settling_time = 5.0 * tau
                if settling_time > tstop:
                    tstop = max(settling_time, 2.0 * period)
                # Ensure tstep captures the RC dynamics
                tstep = min(tstep, tau / 20.0)
            except (ValueError, TypeError):
                pass

    params["period"] = period
    params["half_period"] = half_period
    params["tstep"] = tstep
    params["tstop"] = tstop

    # Fill template
    netlist = netlist_template
    for k, v in params.items():
        netlist = netlist.replace("{" + k + "}", str(v))

    # Build suggested commands
    raw_cmds = tpl.get(commands_key, [])
    commands = []
    for cmd in raw_cmds:
        filled = cmd
        for k, v in params.items():
            filled = filled.replace("{" + k + "}", str(v))
        commands.append(filled)

    return _ok({
        "template_id": template_id,
        "name": tpl["name"],
        "name_zh": tpl.get("name_zh", ""),
        "analysis": analysis,
        "netlist": netlist,
        "commands": commands,
        "parameters_used": {k: v for k, v in params.items()
                           if k in tpl.get("parameters", {})},
        "nodes": tpl.get("nodes", {}),
        "gain_formula": tpl.get("gain_formula", ""),
    })


def tool_materialize_design_template(
    template_id: str,
    analysis: str = "tran",
    overrides: dict | None = None,
    output_dir: str = "",
    render_schematic: bool = True,
) -> dict:
    """Materialize a circuit template into files ready for simulation.

    Creates a ``.cir`` netlist file and optionally renders a schematic image.
    Returns everything needed to proceed: file paths, netlist, commands.

    This bridges the gap between ``get_circuit_template`` (returns text) and
    actual simulation — the caller gets files on disk plus a schematic image
    without needing to manually write files.

    Typical workflow:
        materialize_design_template("inverting_amp", analysis="tran")
        → {cir_path, schematic_path, netlist, commands}
        → run_spice(netlist, commands)

    Args:
        template_id: Template identifier (from list_circuit_templates).
        analysis: "dc" or "tran".
        overrides: Parameter overrides, e.g. {"R1": 5000, "Rf": 50000}.
        output_dir: Directory for output files (default: C:/mcp_spice_tmp).
        render_schematic: Whether to also render a schematic PNG.
    """
    import os

    # Get the template
    result = tool_get_circuit_template(template_id, analysis, overrides)
    if not result.get("ok"):
        return result

    data = result["data"]
    netlist = data["netlist"]
    commands = data["commands"]
    name = data["name"]

    # Output directory
    if not output_dir:
        output_dir = r"C:\mcp_spice_tmp"
    os.makedirs(output_dir, exist_ok=True)

    # Write .cir file
    safe_id = template_id.replace(" ", "_")
    cir_path = os.path.join(output_dir, f"{safe_id}.cir")
    safe_netlist = netlist.encode("ascii", errors="replace").decode("ascii")
    with open(cir_path, "w", encoding="ascii") as f:
        f.write(safe_netlist if safe_netlist.endswith("\n") else safe_netlist + "\n")

    response: dict = {
        "template_id": template_id,
        "name": name,
        "name_zh": data.get("name_zh", ""),
        "analysis": analysis,
        "cir_path": cir_path,
        "netlist": netlist,
        "commands": commands,
        "parameters_used": data.get("parameters_used", {}),
        "nodes": data.get("nodes", {}),
        "gain_formula": data.get("gain_formula", ""),
    }

    # Render schematic
    if render_schematic:
        try:
            from . import schematic_render
            sch_path = os.path.join(output_dir, f"{safe_id}_schematic.png")
            sch_result = schematic_render.tool_render_netlist_schematic(
                netlist, sch_path, title=name,
            )
            if sch_result.get("ok"):
                response["schematic_path"] = sch_result["data"]["path"]
            else:
                response["schematic_error"] = sch_result.get("error_message", "render failed")
        except Exception as exc:
            response["schematic_error"] = str(exc)

    return _ok(response)
