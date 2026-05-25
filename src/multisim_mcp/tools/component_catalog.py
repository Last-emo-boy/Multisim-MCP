"""
Component Database Catalog - searchable index of Multisim Master Database components.

Provides a structured catalog of commonly-used components with their
Multisim database coordinates (group/family/name) for use with
``replace_component``, plus SPICE model equivalents for ``run_spice``.
"""

from __future__ import annotations

import re

from ..models import ToolResponse


def _ok(data: dict | None = None) -> dict:
    return ToolResponse(ok=True, data=data or {}).model_dump()


def _err(msg: str, code: str = "ERROR") -> dict:
    return ToolResponse(ok=False, error_code=code, error_message=msg).model_dump()


# ────────────────────────────────────────────────────────────
# Component Catalog Database
# ────────────────────────────────────────────────────────────
# Each entry: {
#   "name": display name,
#   "description": what it does,
#   "category": search category,
#   "tags": search keywords,
#   "multisim": {"database", "group", "family", "name"} for replace_component,
#   "spice_model": SPICE netlist snippet for run_spice (optional),
# }

CATALOG: list[dict] = [
    # ── Op-Amps ─────────────────────────────────────────────
    {
        "name": "LM741",
        "description": "General purpose operational amplifier, unity gain bandwidth 1MHz",
        "category": "opamp",
        "tags": ["op-amp", "operational amplifier", "741", "general purpose", "analog"],
        "multisim": {"database": "master", "group": "Analog", "family": "OPAMP", "name": "LM741CH/NOPB"},
        "spice_model": "* Ideal opamp model: E1 out 0 inp inv 200000",
        "specs": {"gbw": "1MHz", "slew_rate": "0.5V/us", "vos": "1mV", "supply": "+/-15V"},
    },
    {
        "name": "UA741",
        "description": "Industry standard operational amplifier",
        "category": "opamp",
        "tags": ["op-amp", "741", "standard", "analog"],
        "multisim": {"database": "master", "group": "Analog", "family": "OPAMP", "name": "uA741"},
        "spice_model": "* Ideal opamp model: E1 out 0 inp inv 200000",
        "specs": {"gbw": "1MHz", "slew_rate": "0.5V/us", "supply": "+/-15V"},
    },
    {
        "name": "LM324",
        "description": "Quad op-amp, single supply, low power",
        "category": "opamp",
        "tags": ["op-amp", "quad", "single supply", "low power", "analog"],
        "multisim": {"database": "master", "group": "Analog", "family": "OPAMP", "name": "LM324AN/NOPB"},
        "spice_model": "* Ideal opamp: E1 out 0 inp inv 200000",
        "specs": {"gbw": "1.2MHz", "supply": "3-32V single, +/-1.5 to +/-16V dual"},
    },
    {
        "name": "TL072",
        "description": "Dual JFET-input op-amp, low noise",
        "category": "opamp",
        "tags": ["op-amp", "jfet", "low noise", "audio", "dual"],
        "multisim": {"database": "master", "group": "Analog", "family": "OPAMP", "name": "TL072ACP"},
        "specs": {"gbw": "3MHz", "slew_rate": "13V/us", "supply": "+/-18V"},
    },
    {
        "name": "LM358",
        "description": "Dual op-amp, single supply compatible",
        "category": "opamp",
        "tags": ["op-amp", "dual", "single supply", "analog"],
        "multisim": {"database": "master", "group": "Analog", "family": "OPAMP", "name": "LM358AN/NOPB"},
        "specs": {"gbw": "1MHz", "supply": "3-32V single"},
    },

    # ── Comparators ─────────────────────────────────────────
    {
        "name": "LM311",
        "description": "Voltage comparator, open collector output",
        "category": "comparator",
        "tags": ["comparator", "voltage", "open collector", "analog"],
        "multisim": {"database": "master", "group": "Analog", "family": "COMPARATOR", "name": "LM311N/NOPB"},
        "specs": {"response_time": "200ns", "supply": "+/-15V"},
    },
    {
        "name": "LM339",
        "description": "Quad comparator, open collector output",
        "category": "comparator",
        "tags": ["comparator", "quad", "open collector"],
        "multisim": {"database": "master", "group": "Analog", "family": "COMPARATOR", "name": "LM339AN/NOPB"},
    },

    # ── Voltage Regulators ──────────────────────────────────
    {
        "name": "7805",
        "description": "5V positive voltage regulator, 1A",
        "category": "regulator",
        "tags": ["regulator", "voltage", "5v", "linear", "7805", "power"],
        "multisim": {"database": "master", "group": "Power", "family": "VOLTAGE_REGULATOR", "name": "LM7805CT/NOPB"},
        "specs": {"vout": "5V", "vin_max": "35V", "iout_max": "1A"},
    },
    {
        "name": "7812",
        "description": "12V positive voltage regulator, 1A",
        "category": "regulator",
        "tags": ["regulator", "voltage", "12v", "linear", "7812"],
        "multisim": {"database": "master", "group": "Power", "family": "VOLTAGE_REGULATOR", "name": "LM7812CT/NOPB"},
    },
    {
        "name": "LM317",
        "description": "Adjustable positive voltage regulator, 1.2V-37V",
        "category": "regulator",
        "tags": ["regulator", "adjustable", "linear", "lm317"],
        "multisim": {"database": "master", "group": "Power", "family": "VOLTAGE_REGULATOR", "name": "LM317AT/NOPB"},
    },

    # ── Diodes ──────────────────────────────────────────────
    {
        "name": "1N4148",
        "description": "Small signal fast switching diode",
        "category": "diode",
        "tags": ["diode", "signal", "switching", "small signal"],
        "multisim": {"database": "master", "group": "Diodes", "family": "DIODE", "name": "1N4148"},
        "spice_model": ".model D1N4148 D(Is=2.52e-9 Rs=0.568)",
    },
    {
        "name": "1N4007",
        "description": "General purpose rectifier diode, 1A 1000V",
        "category": "diode",
        "tags": ["diode", "rectifier", "power", "1n4007"],
        "multisim": {"database": "master", "group": "Diodes", "family": "DIODE", "name": "1N4007"},
    },
    {
        "name": "1N5819",
        "description": "Schottky barrier rectifier, 1A 40V",
        "category": "diode",
        "tags": ["diode", "schottky", "rectifier", "fast"],
        "multisim": {"database": "master", "group": "Diodes", "family": "SCHOTTKY_DIODE", "name": "1N5819"},
    },
    {
        "name": "LED_red",
        "description": "Red LED, Vf=1.8V typical",
        "category": "diode",
        "tags": ["led", "red", "indicator", "light"],
        "multisim": {"database": "master", "group": "Diodes", "family": "LED", "name": "LED_red"},
        "spice_model": ".model LED_RED D(Is=1e-20 N=1.8 Rs=5)",
    },

    # ── Zener Diodes ────────────────────────────────────────
    {
        "name": "1N4733A",
        "description": "5.1V Zener diode, 1W",
        "category": "diode",
        "tags": ["zener", "5.1v", "voltage reference", "diode"],
        "multisim": {"database": "master", "group": "Diodes", "family": "ZENER", "name": "1N4733A"},
    },
    {
        "name": "1N4742A",
        "description": "12V Zener diode, 1W",
        "category": "diode",
        "tags": ["zener", "12v", "voltage reference", "diode"],
        "multisim": {"database": "master", "group": "Diodes", "family": "ZENER", "name": "1N4742A"},
    },

    # ── Transistors (BJT) ───────────────────────────────────
    {
        "name": "2N2222",
        "description": "NPN general purpose transistor",
        "category": "transistor",
        "tags": ["bjt", "npn", "transistor", "switching", "general purpose", "2n2222"],
        "multisim": {"database": "master", "group": "Transistors", "family": "BJT_NPN", "name": "2N2222A"},
        "spice_model": ".model Q2N2222 NPN(Is=14.34f Bf=255.9 Vaf=74.03)",
        "specs": {"vceo": "40V", "ic_max": "800mA", "hfe": "100-300"},
    },
    {
        "name": "2N3904",
        "description": "NPN small signal transistor",
        "category": "transistor",
        "tags": ["bjt", "npn", "small signal", "2n3904"],
        "multisim": {"database": "master", "group": "Transistors", "family": "BJT_NPN", "name": "2N3904"},
        "specs": {"vceo": "40V", "ic_max": "200mA", "hfe": "100-300"},
    },
    {
        "name": "2N3906",
        "description": "PNP small signal transistor (complement of 2N3904)",
        "category": "transistor",
        "tags": ["bjt", "pnp", "small signal", "2n3906"],
        "multisim": {"database": "master", "group": "Transistors", "family": "BJT_PNP", "name": "2N3906"},
    },
    {
        "name": "TIP31C",
        "description": "NPN power transistor, 3A 100V",
        "category": "transistor",
        "tags": ["bjt", "npn", "power", "tip31"],
        "multisim": {"database": "master", "group": "Transistors", "family": "BJT_NPN", "name": "TIP31C"},
    },

    # ── MOSFETs ─────────────────────────────────────────────
    {
        "name": "IRF540N",
        "description": "N-channel power MOSFET, 33A 100V",
        "category": "transistor",
        "tags": ["mosfet", "nmos", "power", "switching", "irf540"],
        "multisim": {"database": "master", "group": "Transistors", "family": "MOSFET_N", "name": "IRF540N"},
    },
    {
        "name": "2N7000",
        "description": "N-channel enhancement MOSFET, small signal",
        "category": "transistor",
        "tags": ["mosfet", "nmos", "small signal", "2n7000"],
        "multisim": {"database": "master", "group": "Transistors", "family": "MOSFET_N", "name": "2N7000"},
    },

    # ── 555 Timer ───────────────────────────────────────────
    {
        "name": "NE555",
        "description": "555 Timer IC - astable, monostable, bistable modes",
        "category": "timer",
        "tags": ["555", "timer", "oscillator", "pulse", "ne555", "mixed"],
        "multisim": {"database": "master", "group": "Mixed", "family": "TIMER", "name": "LM555CN/NOPB"},
        "specs": {"supply": "4.5-16V", "output_current": "200mA"},
    },

    # ── TTL Logic ICs ───────────────────────────────────────
    {
        "name": "74LS00",
        "description": "Quad 2-input NAND gate",
        "category": "ttl",
        "tags": ["logic", "nand", "gate", "ttl", "74ls", "quad", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS00D"},
    },
    {
        "name": "74LS02",
        "description": "Quad 2-input NOR gate",
        "category": "ttl",
        "tags": ["logic", "nor", "gate", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS02D"},
    },
    {
        "name": "74LS04",
        "description": "Hex inverter (NOT gate)",
        "category": "ttl",
        "tags": ["logic", "inverter", "not", "gate", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS04D"},
    },
    {
        "name": "74LS08",
        "description": "Quad 2-input AND gate",
        "category": "ttl",
        "tags": ["logic", "and", "gate", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS08D"},
    },
    {
        "name": "74LS32",
        "description": "Quad 2-input OR gate",
        "category": "ttl",
        "tags": ["logic", "or", "gate", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS32D"},
    },
    {
        "name": "74LS86",
        "description": "Quad 2-input XOR gate",
        "category": "ttl",
        "tags": ["logic", "xor", "gate", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS86D"},
    },
    {
        "name": "74LS74",
        "description": "Dual D flip-flop with preset and clear",
        "category": "ttl",
        "tags": ["flip-flop", "d", "register", "ttl", "74ls", "digital", "sequential"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS74D"},
    },
    {
        "name": "74LS76",
        "description": "Dual JK flip-flop with preset and clear",
        "category": "ttl",
        "tags": ["flip-flop", "jk", "register", "ttl", "74ls", "digital", "sequential"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS76AN"},
    },
    {
        "name": "74LS138",
        "description": "3-to-8 line decoder/demultiplexer",
        "category": "ttl",
        "tags": ["decoder", "demux", "3-to-8", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS138D"},
    },
    {
        "name": "74LS151",
        "description": "8-to-1 multiplexer",
        "category": "ttl",
        "tags": ["mux", "multiplexer", "8-to-1", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS151D"},
    },
    {
        "name": "74LS161",
        "description": "4-bit synchronous binary counter",
        "category": "ttl",
        "tags": ["counter", "binary", "4-bit", "synchronous", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS161D"},
    },
    {
        "name": "74LS163",
        "description": "4-bit synchronous binary counter (synchronous clear)",
        "category": "ttl",
        "tags": ["counter", "binary", "synchronous", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS163D"},
    },
    {
        "name": "74LS190",
        "description": "BCD decade up/down counter",
        "category": "ttl",
        "tags": ["counter", "bcd", "decade", "up/down", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS190D"},
    },
    {
        "name": "74LS47",
        "description": "BCD to 7-segment decoder (active low output)",
        "category": "ttl",
        "tags": ["decoder", "7-segment", "bcd", "display", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS47D"},
    },
    {
        "name": "74LS283",
        "description": "4-bit binary full adder",
        "category": "ttl",
        "tags": ["adder", "4-bit", "arithmetic", "ttl", "74ls", "digital", "calculator"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS283D"},
    },
    {
        "name": "74LS181",
        "description": "4-bit ALU (Arithmetic Logic Unit)",
        "category": "ttl",
        "tags": ["alu", "arithmetic", "logic", "4-bit", "ttl", "74ls", "digital", "calculator"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS181D"},
    },
    {
        "name": "74LS245",
        "description": "Octal bus transceiver (tristate)",
        "category": "ttl",
        "tags": ["bus", "buffer", "transceiver", "tristate", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS245D"},
    },
    {
        "name": "74LS373",
        "description": "Octal D-type transparent latch",
        "category": "ttl",
        "tags": ["latch", "register", "8-bit", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS373D"},
    },
    {
        "name": "74LS374",
        "description": "Octal D-type edge-triggered flip-flop",
        "category": "ttl",
        "tags": ["flip-flop", "register", "8-bit", "edge-triggered", "ttl", "74ls", "digital"],
        "multisim": {"database": "master", "group": "TTL", "family": "74LS", "name": "74LS374D"},
    },

    # ── CMOS Logic ──────────────────────────────────────────
    {
        "name": "CD4017",
        "description": "Decade counter/divider with 10 decoded outputs",
        "category": "cmos",
        "tags": ["counter", "decade", "decoded", "cmos", "cd4000", "digital"],
        "multisim": {"database": "master", "group": "CMOS", "family": "CD4000", "name": "CD4017BD"},
    },
    {
        "name": "CD4060",
        "description": "14-stage ripple binary counter with oscillator",
        "category": "cmos",
        "tags": ["counter", "binary", "oscillator", "cmos", "divider", "digital"],
        "multisim": {"database": "master", "group": "CMOS", "family": "CD4000", "name": "CD4060BD"},
    },

    # ── Sources ─────────────────────────────────────────────
    {
        "name": "DC_POWER",
        "description": "DC voltage source / power supply",
        "category": "source",
        "tags": ["source", "dc", "power", "supply", "voltage"],
        "multisim": {"database": "master", "group": "Sources", "family": "POWER_SOURCES", "name": "DC_POWER"},
        "spice_model": "V1 node 0 DC {value}",
    },
    {
        "name": "AC_POWER",
        "description": "AC voltage source / signal generator",
        "category": "source",
        "tags": ["source", "ac", "signal", "generator", "sine"],
        "multisim": {"database": "master", "group": "Sources", "family": "SIGNAL_VOLTAGE_SOURCES", "name": "AC_POWER"},
        "spice_model": "V1 node 0 SIN(0 {amplitude} {frequency})",
    },
    {
        "name": "CLOCK_VOLTAGE",
        "description": "Digital clock source (square wave)",
        "category": "source",
        "tags": ["source", "clock", "digital", "square", "pulse"],
        "multisim": {"database": "master", "group": "Sources", "family": "SIGNAL_VOLTAGE_SOURCES", "name": "CLOCK_VOLTAGE"},
        "spice_model": "V1 node 0 PULSE(0 5 0 1n 1n {half_period} {period})",
    },

    # ── Indicators ──────────────────────────────────────────
    {
        "name": "PROBE",
        "description": "Voltage probe for measurements",
        "category": "indicator",
        "tags": ["probe", "voltage", "measurement", "indicator"],
        "multisim": {"database": "master", "group": "Indicators", "family": "PROBE", "name": "PROBE"},
    },
    {
        "name": "7SEG_DISPLAY",
        "description": "7-segment LED display",
        "category": "indicator",
        "tags": ["display", "7-segment", "led", "indicator", "digit"],
        "multisim": {"database": "master", "group": "Indicators", "family": "HEX_DISPLAY", "name": "DCD_HEX"},
    },
]


# ────────────────────────────────────────────────────────────
# Tool functions
# ────────────────────────────────────────────────────────────

def tool_search_component_catalog(
    query: str,
    category: str = "all",
    limit: int = 10,
) -> dict:
    """Search the component catalog by keyword, description, or tags.

    Returns matching components with their Multisim database coordinates
    (group/family/name) for use with ``replace_component``.

    Categories: opamp, comparator, regulator, diode, transistor, timer,
    ttl, cmos, source, indicator, or 'all' for no filter.
    """
    query_lower = query.lower()
    keywords = query_lower.split()

    results = []
    for comp in CATALOG:
        if category != "all" and comp.get("category") != category:
            continue

        # Score: how many keywords match name, description, or tags
        score = 0
        searchable = (
            comp["name"].lower() + " "
            + comp["description"].lower() + " "
            + " ".join(comp.get("tags", []))
        )
        for kw in keywords:
            if kw in searchable:
                score += 1
            # Bonus for exact name match
            if kw == comp["name"].lower():
                score += 5

        if score > 0:
            results.append((score, comp))

    # Sort by score descending
    results.sort(key=lambda x: x[0], reverse=True)

    matches = []
    for score, comp in results[:limit]:
        entry = {
            "name": comp["name"],
            "description": comp["description"],
            "category": comp["category"],
            "tags": comp.get("tags", []),
        }
        if "multisim" in comp:
            entry["multisim"] = comp["multisim"]
        if "spice_model" in comp:
            entry["spice_model"] = comp["spice_model"]
        if "specs" in comp:
            entry["specs"] = comp["specs"]
        matches.append(entry)

    return _ok({
        "matches": matches,
        "count": len(matches),
        "total_catalog_size": len(CATALOG),
        "query": query,
        "category_filter": category,
    })


def tool_list_component_categories() -> dict:
    """List all component categories with counts."""
    cats: dict[str, int] = {}
    for comp in CATALOG:
        cat = comp.get("category", "other")
        cats[cat] = cats.get(cat, 0) + 1

    return _ok({
        "categories": [
            {"category": k, "count": v, "description": _cat_descriptions.get(k, "")}
            for k, v in sorted(cats.items())
        ],
        "total": len(CATALOG),
    })


_cat_descriptions = {
    "opamp": "Operational amplifiers",
    "comparator": "Voltage comparators",
    "regulator": "Voltage regulators",
    "diode": "Diodes, LEDs, Zeners",
    "transistor": "BJTs and MOSFETs",
    "timer": "Timer ICs (555, etc.)",
    "ttl": "TTL 74LS/74HC series logic",
    "cmos": "CMOS CD4000 series logic",
    "source": "Voltage and current sources",
    "indicator": "Probes, displays, LEDs",
    "mixed": "Mixed signal components",
}
