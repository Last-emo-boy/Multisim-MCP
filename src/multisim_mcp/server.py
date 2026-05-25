"""
Multisim MCP Server - main entry point.

Registers all MCP tools and runs the server over stdio transport.
"""

from __future__ import annotations

import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from .com_adapter import MultisimCOMAdapter
from .session import SessionManager
from .tools import file_tools, enum_tools, modify_tools, simulation_tools, output_tools, spice_tools, instrument_tools, report_tools, circuit_templates, netlist_builder, component_catalog, design_checks, block_sim, schematic_render, transient_sweep as transient_sweep_mod, signal_measure, markdown_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("multisim_mcp")

# ── Global instances (one COM adapter + session per server process) ──
_adapter = MultisimCOMAdapter()
_session = SessionManager(adapter=_adapter)

mcp = FastMCP(
    "Multisim MCP",
    instructions="""You are an expert NI Multisim circuit simulation assistant. You control Multisim via its COM Automation API through the tools below.

## CRITICAL WORKFLOW RULES

1. **Always connect first**: Call `connect` before any other tool. This launches Multisim.
2. **Open before operate**: Call `open_design` (for .ms14/.ms8+) or `open_netlist` (for .cir) before any circuit operation.
3. **Stop before modify**: `set_rlc_value`, `set_circuit_parameter_value`, and `replace_component` all REQUIRE simulation to be stopped. Call `stop_simulation` first if needed.
4. **Enumerate before reference**: Call `list_outputs`/`list_inputs`/`list_components` to discover valid probe names and RefDes identifiers before using them. Never guess probe or component names.
5. **SI units only**: RLC values must be in base SI — Ohms (R), Farads (C), Henrys (L). Convert from human units first: 1kΩ = 1000, 10nF = 1e-8, 4.7µH = 4.7e-6.

## ANALYSIS WORKFLOW PATTERNS

### SPICE Analysis (Recommended for programmatic circuits)
```
connect → run_spice(netlist="...", commands=["op", "print $out $ui"])
```
`run_spice` is the **most powerful and flexible** tool. It accepts an inline SPICE netlist and
nutmeg commands, runs everything in one call, and returns parsed numeric results. Use it when:
- The circuit has no probes (list_outputs returns empty)
- Components use RESISTOR_RATED or other non-editable types
- You want full control over the circuit topology
- You need parameter sweeps with `alter` commands

### Quick DC Analysis (Schematic-based)
```
connect → open_design → list_outputs → run_dc_operating_point(output_names) → get_output_data
```

### Transient (Time-Domain) Analysis
```
connect → open_design → list_outputs → run_transient(output_names, stop_time, sample_rate) → get_output_data
```
`run_transient` is synchronous — it sets output requests, runs, and waits automatically.

### AC Sweep (Frequency Response)
```
connect → open_design → list_outputs → run_ac_sweep(output_names, ...) → is_output_ready → get_output_data
```
`run_ac_sweep` and `run_ac_single_frequency` are ASYNCHRONOUS — poll `is_output_ready` before calling `get_output_data`.

### Modify-Then-Simulate
```
connect → open_design → stop_simulation (if running)
→ list_components (discover RefDes)
→ set_rlc_value / set_circuit_parameter_value (modify)
→ list_outputs → run_transient / run_ac_sweep → get_output_data
→ save_design (persist changes)
```

### Parameter Study (Manual Sweep)
Repeat the modify-then-simulate pattern in a loop, changing one parameter at a time and collecting results for comparison.

### One-Call Parameter Sweep (SPICE)
```
connect → parameter_sweep(netlist, component="R1", values=[10000, 20000, 50000], outputs=["$out", "$in"])
```
`parameter_sweep` runs the entire sweep in a SINGLE SPICE call using `alter` commands internally.
Returns a structured results table with one row per parameter value — no loops needed.

### Standalone Waveform Plotting
```
plot_waveform(channels=[{label, waveform, frequency, amplitude, phase}, ...])
```
`plot_waveform` generates waveform plot images from mathematical parameters or raw data arrays.
No simulation needed — useful for visualizing computed/expected waveforms alongside measurements.

### SPICE Transient with Real Waveform Data
```
connect → run_spice(netlist, commands=["tran 10u 2m", "print $out $in"])
```
After `tran` analysis, `print` returns FULL time-series data (not just scalars).
The result includes `_type: "transient"`, `time: [...]`, and vector arrays like `$out: [...]`.
Feed this data directly into `plot_waveform` using raw data channels:
```
plot_waveform(channels=[{label: "Output", time: result["time"], values: result["$out"]}])
```
This produces plots from REAL Multisim simulation data — not computed approximations.

### Circuit Templates (No .ms14 Required)
```
list_circuit_templates(category="opamp") → see available templates
get_circuit_template("inverting_amp", analysis="tran", overrides={"R1": 5000})
  → returns ready-to-use netlist + suggested commands
run_spice(netlist=template_netlist, commands=template_commands) → simulate
```
Use templates when no .ms14 file is available. Templates provide parameterizable
SPICE netlists for common circuits (opamp, filter, basic RLC).

### Programmatic Netlist Construction
```
build_netlist(title, components=[{type: "R", n1: "in", n2: "out", value: 10000}, ...])
  → returns netlist text + suggested commands
run_spice(netlist, commands) → simulate
```
Use `build_netlist` to construct circuits programmatically from component specs.
Supports R, C, L, V, I, E (VCVS), GATE (digital), DFF, RAW, and MODEL types.

### Component Catalog Search
```
search_component_catalog("741 op-amp") → find Multisim database coordinates
search_component_catalog("counter", category="ttl") → filter by category
```
Returns group/family/name for use with `replace_component` on .ms14 designs.

### Design Rule Checking
```
build_netlist → check_design_rules(netlist) → fix issues → run_spice
```
Pre-simulation verification: floating nodes, missing ground, power budget, etc.

### Block Simulation Pipeline
```
simulate_block("input_stage", netlist1, commands1, expected_outputs)
simulate_block("output_stage", netlist2, commands2, expected_outputs)
simulate_pipeline(blocks=[...]) → run all blocks with verification
```
Test individual circuit blocks before combining them.

### Export & Report
```
export_netlist → returns circuit netlist text
export_bom → returns Bill of Materials
export_circuit_image / create_snippet → saves schematic PNG
simulation_report → generates HTML report with embedded images, measurements, BOM, netlist
```

### Virtual Instruments (Function Generator + Oscilloscope)
```
connect → open_design → list_inputs → function_generator(input_name, waveform, frequency, ...)
→ list_outputs → oscilloscope(output_names, duration, ...) → returns plot image + measurements
→ simulation_report(schematic_image, waveform_images, channel_data) → HTML report
```
`function_generator` generates waveforms (sine/square/triangle/sawtooth/pulse/dc) and injects them via SetInputDataSampled.
`oscilloscope` runs a transient sim, captures probe data, generates matplotlib plots, and returns measurements.

## TOOL CATEGORIES

| Category | Tools | When to use |
|----------|-------|-------------|
| Category | Tools | When to use |
|----------|-------|-------------|
| Session | `connect`, `disconnect`, `get_session_state` | Start/end session, check status |
| File | `open_design`, `open_netlist`, `save_design`, `save_design_as` | File I/O |
| Enumerate | `list_components`, `list_inputs`, `list_outputs`, `list_sections`, `list_variants`, `list_circuit_parameters` | Discover circuit structure — always call BEFORE referencing names |
| Modify | `set_rlc_value`, `set_circuit_parameter_value`, `replace_component`, `set_input_data_raw`, `set_input_data_sampled`, `clear_input` | Change circuit — simulation must be STOPPED |
| Simulate | `run_simulation`, `pause_simulation`, `resume_simulation`, `stop_simulation`, `run_until_next_output` | Low-level simulation control |
| **SPICE** | **`run_spice`**, **`parameter_sweep`** | **One-call SPICE analysis — inline netlist + nutmeg → structured results (scalar + time-series)** |
| Analysis | `run_transient`, `run_ac_sweep`, `run_ac_single_frequency`, `run_dc_operating_point`, `run_command_line` | Schematic-based analysis (requires probes) |
| Output | `set_output_request`, `clear_output_request`, `is_output_ready`, `get_output_data`, `summarize_output` | Data retrieval; `summarize_output` for quick metrics |
| **Instruments** | **`function_generator`**, **`oscilloscope`**, **`plot_waveform`** | **Virtual instruments — waveform injection + capture + standalone plotting** |
| Image | `export_circuit_image`, `create_snippet`, `save_design_as_snippet_image` | Schematic capture |
| Report | `export_netlist`, `export_bom`, **`simulation_report`** | Text reports & HTML visual reports |
| **Templates** | **`list_circuit_templates`**, **`get_circuit_template`** | **Pre-built SPICE netlists for common circuits — no .ms14 needed** |
| **Builder** | **`build_netlist`** | **Programmatic netlist construction from component specs** |
| **Catalog** | **`search_component_catalog`**, **`list_component_categories`** | **Find Multisim database components for replace_component** |
| **DRC** | **`check_design_rules`** | **Pre-simulation netlist verification (floating nodes, power budget, etc.)** |
| **Pipeline** | **`simulate_block`**, **`simulate_pipeline`** | **Block-level simulation with automatic output verification** |
| **Designs** | **`list_design_templates`**, **`get_design_template_details`** | **Pre-built .ms14 schematic templates with workflow guides** |

## COMMON MISTAKES TO AVOID

- Do NOT call `get_output_data` without first confirming the simulation has completed or `is_output_ready` returns true.
- Do NOT call `get_output_data` twice for the same probe — it consumes the data block.
- Do NOT modify components while simulation is running — always `stop_simulation` first.
- Do NOT pass output probe names as guesses — always use `list_outputs` to discover them.
- `run_transient` is self-contained (handles output requests internally). Don't call `set_output_request` before it.
- `run_ac_sweep` / `run_ac_single_frequency` / `run_dc_operating_point` are NOT self-contained — for AC sweep, you may still need to poll `is_output_ready`.
- When using `run_spice`, node voltages use `$` prefix in vector names: `print $out $vcc`, NOT `print v(out)`.
- The `alter` nutmeg command modifies component values inline: `alter R1 = 20000` (SI units).
- The XSPICE engine does NOT support `wrdata` — use `print` to output values (they appear in results).

## CHOOSING BETWEEN run_spice AND SCHEMATIC-BASED ANALYSIS

**Use `run_spice`** when:
- Circuit uses RESISTOR_RATED or other non-basic components (set_rlc_value won't work)
- No probes are placed on the schematic (list_outputs returns empty)
- You want to define a circuit from scratch without a .ms14 file
- You need flexible parameter sweeps with inline `alter` commands

**Use schematic-based tools** (run_transient, run_dc_operating_point, etc.) when:
- The .ms14 design already has probes placed
- Components are basic type (editable via set_rlc_value)
- You want to work with the GUI-visible schematic

## RESPONSE FORMAT

All tools return JSON with `{ok: bool, data: {...}, error_code, error_message, suggested_recovery}`. Always check `ok` before proceeding. On failure, read `error_message` and `suggested_recovery` for guidance.
""",
)


# ═══════════════════════════════════════════════════════════════
# Session & File Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def connect(
    path: str | None = None,
    log_file: str | None = None,
) -> str:
    """Connect to a local NI Multisim instance. MUST be called first before any other tool.
    
    Starts Multisim if not already running. Returns version info on success.
    
    Args:
        path: Optional path to Multisim executable (auto-detected if omitted)
        log_file: Optional path for Multisim log file
    """
    return json.dumps(file_tools.tool_connect(_session, path, log_file))


@mcp.tool()
def disconnect() -> str:
    """Disconnect from Multisim and terminate the instance."""
    return json.dumps(file_tools.tool_disconnect(_session))


@mcp.tool()
def open_design(path: str) -> str:
    """Open an existing Multisim design file (.ms14, .ms8+).
    
    Args:
        path: Absolute path to the design file
    """
    return json.dumps(file_tools.tool_open_design(_session, path))


@mcp.tool()
def open_netlist(path: str) -> str:
    """Open a SPICE netlist file (.cir, .txt) for simulation.
    
    Args:
        path: Absolute path to the netlist file
    """
    return json.dumps(file_tools.tool_open_netlist(_session, path))


@mcp.tool()
def save_design() -> str:
    """Save the current circuit design."""
    return json.dumps(file_tools.tool_save_design(_session))


@mcp.tool()
def save_design_as(path: str) -> str:
    """Save the current circuit to a new file path.
    
    Args:
        path: Destination file path
    """
    return json.dumps(file_tools.tool_save_design_as(_session, path))


@mcp.tool()
def export_circuit_image(path: str, format: str = "png") -> str:
    """Export circuit schematic as an image file.
    
    Args:
        path: Output image file path
        format: Image format - bmp, jpg, or png
    """
    return json.dumps(file_tools.tool_export_circuit_image(_session, path, format))


@mcp.tool()
def create_snippet(path: str, zoom_factor: float = 1.0) -> str:
    """Create a PNG snippet of the current circuit sheet.
    
    File extension is always forced to .png regardless of input.
    
    Args:
        path: Output file path for the snippet image
        zoom_factor: Zoom level for the snippet (default 1.0)
    """
    return json.dumps(file_tools.tool_create_snippet(_session, path, zoom_factor))


@mcp.tool()
def save_design_as_snippet_image(path: str, zoom_factor: float = 1.0) -> str:
    """Save entire design (excluding hierarchical blocks) as a PNG snippet.
    
    File extension is always forced to .png.
    
    Args:
        path: Output file path for the snippet image
        zoom_factor: Zoom level for the snippet (default 1.0)
    """
    return json.dumps(file_tools.tool_save_design_as_snippet(_session, path, zoom_factor))


@mcp.tool()
def get_session_state() -> str:
    """Get current session state including connection status, open file, and simulation state."""
    return json.dumps(file_tools.tool_get_session_state(_session))


# ═══════════════════════════════════════════════════════════════
# Enumeration & Report Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def list_components(filter: str = "all") -> str:
    """List all components with their RefDes, RLC values, editability, and sections.
    
    Call this before `set_rlc_value` or `replace_component` to discover valid RefDes names.
    Components with `editable: true` can be modified with `set_rlc_value`.
    
    Args:
        filter: Component filter - all, active, or passive
    """
    return json.dumps(enum_tools.tool_list_components(_session, filter))


@mcp.tool()
def list_inputs(io_type: str = "all") -> str:
    """List all available input sources in the circuit.
    
    Args:
        io_type: Filter type - all, voltage, current, or digital
    """
    return json.dumps(enum_tools.tool_list_inputs(_session, io_type))


@mcp.tool()
def list_outputs(io_type: str = "all") -> str:
    """List all available output probes in the circuit.
    
    ALWAYS call this before any simulation to discover valid probe names.
    The returned names are the exact strings to pass to run_transient, run_ac_sweep, etc.
    
    Args:
        io_type: Filter type - all, voltage, current, or digital
    """
    return json.dumps(enum_tools.tool_list_outputs(_session, io_type))


@mcp.tool()
def list_sections(component_refdes: str) -> str:
    """List sections of a multi-section component (e.g., U1 → U1A, U1B).
    
    Args:
        component_refdes: RefDes of the component, e.g. U1
    """
    return json.dumps(enum_tools.tool_list_sections(_session, component_refdes))


@mcp.tool()
def list_variants() -> str:
    """List all circuit design variants and the currently active one."""
    return json.dumps(enum_tools.tool_list_variants(_session))


@mcp.tool()
def export_netlist(path: str = "", format: str = "text", include_probes: bool = False) -> str:
    """Export the circuit netlist. Returns inline if path is empty.
    
    Args:
        path: File path to save (empty for inline return)
        format: Export format - 'text' or 'csv'
        include_probes: Whether to include probe info in the netlist
    """
    return json.dumps(enum_tools.tool_export_netlist(_session, path, format, include_probes))


@mcp.tool()
def export_bom(path: str = "", format: str = "text", real_only: bool = False) -> str:
    """Export the Bill of Materials. Returns inline if path is empty.
    
    Args:
        path: File path to save (empty for inline return)
        format: Export format - 'text' or 'csv'
        real_only: If true, only include real (non-virtual) components
    """
    return json.dumps(enum_tools.tool_export_bom(_session, path, format, real_only))


@mcp.tool()
def list_circuit_parameters(level: str = "all") -> str:
    """List all circuit parameter names.
    
    Args:
        level: Parameter level - 'all' for all parameters, 'top_level' for top-level only
    """
    return json.dumps(enum_tools.tool_list_circuit_parameters(_session, level))


# ═══════════════════════════════════════════════════════════════
# Modification Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def set_rlc_value(refdes: str, value: float) -> str:
    """Set the value of a basic R/L/C component.
    
    Simulation must be stopped. Creates a snapshot before modification.
    
    Args:
        refdes: Component reference designator (e.g., R1, C2, L1)
        value: Value in base SI units - Ohms for R, Farads for C, Henrys for L.
               Example: 1000 for 1kΩ, 1e-9 for 1nF, 1e-3 for 1mH
    """
    return json.dumps(modify_tools.tool_set_rlc_value(_session, refdes, value))


@mcp.tool()
def replace_component(
    refdes: str,
    group: str,
    family: str,
    name: str,
    section: str = "",
    database: str = "master",
    model: str = "",
) -> str:
    """Replace a component with another from the Multisim database.
    
    Simulation must be stopped. Re-enumerate inputs/outputs after replacement.
    Cannot replace basic RLC components (use set_rlc_value instead).
    
    Args:
        refdes: RefDes of component to replace (e.g., D1, U1)
        group: Database group (e.g., Diodes, Analog, Sources)
        family: Database family (e.g., DIODE, OPAMP, ZENER)
        name: Component name (e.g., 1N5712, MC1458SU)
        section: Section name for multi-section parts (empty for single)
        database: Database source - master, user, or corporate
        model: Model name (empty for default)
    """
    return json.dumps(
        modify_tools.tool_replace_component(
            _session, refdes, section, database, group, family, name, model
        )
    )


@mcp.tool()
def set_input_data_raw(
    input_name: str,
    time_values: list[float],
    data_values: list[float],
    repeat: bool = False,
) -> str:
    """Send arbitrary waveform data (time, value pairs) to a circuit input source.
    
    Args:
        input_name: Input source name (from list_inputs)
        time_values: Array of time points in seconds
        data_values: Array of corresponding voltage/current values
        repeat: Whether to loop the waveform
    """
    return json.dumps(
        modify_tools.tool_set_input_data_raw(
            _session, input_name, time_values, data_values, repeat
        )
    )


@mcp.tool()
def set_input_data_sampled(
    input_name: str,
    sample_rate: float,
    data_values: list[float],
    repeat: bool = False,
) -> str:
    """Send evenly-sampled waveform data to a circuit input source.
    
    Args:
        input_name: Input source name (from list_inputs)
        sample_rate: Sampling rate in samples per second
        data_values: Array of evenly-spaced data values
        repeat: Whether to loop the waveform
    """
    return json.dumps(
        modify_tools.tool_set_input_data_sampled(
            _session, input_name, sample_rate, data_values, repeat
        )
    )


@mcp.tool()
def clear_input(input_name: str) -> str:
    """Clear/cancel a previously set input waveform.
    
    Args:
        input_name: Input source name to clear
    """
    return json.dumps(modify_tools.tool_clear_input(_session, input_name))


@mcp.tool()
def get_circuit_parameter_value(param_name: str) -> str:
    """Get the value of a circuit parameter.
    
    Supports sub-sheet syntax like 'SC1.Vin'. Expressions are evaluated and result returned.
    Use list_circuit_parameters to discover available parameter names.
    
    Args:
        param_name: Circuit parameter name
    """
    return json.dumps(modify_tools.tool_get_circuit_parameter_value(_session, param_name))


@mcp.tool()
def set_circuit_parameter_value(param_name: str, value: float) -> str:
    """Set a circuit parameter value. Simulation must be stopped.
    
    Creates a snapshot before modification. Supports sub-sheet syntax like 'SC1.Vin'.
    
    Args:
        param_name: Circuit parameter name
        value: New numeric value for the parameter
    """
    return json.dumps(modify_tools.tool_set_circuit_parameter_value(_session, param_name, value))


# ═══════════════════════════════════════════════════════════════
# Simulation & Analysis Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def run_simulation() -> str:
    """Start or resume the simulation (low-level).
    
    Prefer `run_transient` or `run_ac_sweep` for most analyses.
    Only use this if you need manual control with `set_output_request` → `run_simulation` → `wait` → `get_output_data`.
    """
    return json.dumps(simulation_tools.tool_run_simulation(_session))


@mcp.tool()
def pause_simulation() -> str:
    """Pause a running simulation."""
    return json.dumps(simulation_tools.tool_pause_simulation(_session))


@mcp.tool()
def resume_simulation() -> str:
    """Resume a paused simulation."""
    return json.dumps(simulation_tools.tool_resume_simulation(_session))


@mcp.tool()
def stop_simulation() -> str:
    """Immediately stop the simulation."""
    return json.dumps(simulation_tools.tool_stop_simulation(_session))


@mcp.tool()
def run_until_next_output() -> str:
    """Run simulation until the next output data block is ready."""
    return json.dumps(simulation_tools.tool_run_until_next_output(_session))


@mcp.tool()
def run_ac_sweep(
    output_names: list[str],
    sweep_type: str = "decade",
    num_points: int = 100,
    start_frequency: float = 1.0,
    stop_frequency: float = 1e6,
) -> str:
    """Run AC Sweep (frequency response) analysis.
    
    ASYNCHRONOUS — must poll `is_output_ready` before calling `get_output_data`.
    Workflow: run_ac_sweep → is_output_ready (poll) → get_output_data
    
    Args:
        output_names: List of output probe names (from list_outputs). Required.
        sweep_type: Sweep type - decade, octave, or linear
        num_points: Points per decade/octave, or total for linear
        start_frequency: Start frequency in Hz
        stop_frequency: Stop frequency in Hz
    """
    return json.dumps(
        simulation_tools.tool_run_ac_sweep(
            _session, sweep_type, num_points, start_frequency, stop_frequency, output_names
        )
    )


@mcp.tool()
def run_dc_operating_point(output_names: list[str]) -> str:
    """Run DC Operating Point analysis.
    
    Args:
        output_names: List of output probe names to collect data from
    """
    return json.dumps(
        simulation_tools.tool_run_dc_operating_point(_session, output_names)
    )


@mcp.tool()
def run_transient(
    output_names: list[str],
    stop_time: float = 0.01,
    sample_rate: float = 10000.0,
    num_samples: int = 0,
    interpolation: str = "raw",
) -> str:
    """Run Transient (time-domain) analysis. PREFERRED for most time-domain tasks.
    
    SYNCHRONOUS — handles set_output_request → run → wait automatically.
    After this returns, call `get_output_data` directly (no polling needed).
    Do NOT call `set_output_request` before this — it's handled internally.
    
    Args:
        output_names: List of output probe names (from list_outputs). Required.
        stop_time: Simulation stop time in seconds (e.g., 0.01 for 10ms)
        sample_rate: Output data sample rate in samples/second
        num_samples: Number of samples (0 = auto from stop_time × sample_rate)
        interpolation: Method - raw, force_step, linear, spline, or coerce
    """
    return json.dumps(
        simulation_tools.tool_run_transient(
            _session, stop_time, output_names, sample_rate, num_samples, interpolation
        )
    )


@mcp.tool()
def run_command_line(command_file: str, log_file: str) -> str:
    """Directly simulate a SPICE netlist file (expert/low-level mode).
    
    Prefer `run_spice` instead — it handles file I/O and log parsing automatically.
    
    The command file should contain Nutmeg commands (source, plot, etc.).
    
    Args:
        command_file: Path to nutmeg command file
        log_file: Path for simulation log output
    """
    return json.dumps(
        simulation_tools.tool_run_command_line(_session, command_file, log_file)
    )


@mcp.tool()
def run_spice(
    netlist: str,
    commands: list[str],
    timeout_ms: int = 30000,
) -> str:
    """Run a complete SPICE simulation in one call. Returns parsed numeric results.
    
    This is the most flexible analysis tool. It accepts an inline SPICE netlist
    and a sequence of nutmeg commands, handles all file management internally,
    and returns structured output from `print` commands.
    
    Use this when:
    - The circuit has no probes (list_outputs is empty)
    - Components use RESISTOR_RATED (set_rlc_value unsupported)
    - You want to define a circuit from scratch
    - You need parameter sweeps with alter commands
    
    SPICE netlist rules:
    - Must end with `.end`
    - Analysis commands (.dc, .tran, .ac) in the netlist are IGNORED
      — use the `commands` parameter to run analyses instead
    
    Nutmeg command reference:
    - `op`                   — DC operating point
    - `dc Vi -1 1 0.01`     — DC sweep
    - `tran 1u 10m`         — Transient analysis
    - `ac dec 100 1 1meg`   — AC sweep
    - `alter R1 = 20000`    — Change component value (SI units)
    - `print $out $ui`      — Print node voltages ($ prefix required!)
    - `display`             — List available vectors
    
    Example — inverting amplifier gain measurement:
        netlist: "V1 in 0 DC 1\\nR1 in inv 10k\\nRF inv out 100k\\n.end"
        commands: ["op", "print $out $in"]
        → results: [{"$out": -10.0, "$in": 1.0}]
    
    Example — parameter sweep:
        commands: [
            "op", "print $out",
            "alter R1 = 20000", "op", "print $out",
            "alter R1 = 50000", "op", "print $out",
        ]
        → results: [{"$out": -10.0}, {"$out": -5.0}, {"$out": -2.0}]
    
    Args:
        netlist: SPICE netlist content (inline string, must end with .end)
        commands: Nutmeg commands to execute after loading the netlist
        timeout_ms: Max wait time in ms (default 30s)
    """
    return json.dumps(
        spice_tools.tool_run_spice(_session, netlist, commands, timeout_ms)
    )


@mcp.tool()
def parameter_sweep(
    netlist: str,
    component: str,
    values: list[float],
    outputs: list[str],
    analysis: str = "op",
    component_2: str | None = None,
    values_2: list[float] | None = None,
) -> str:
    """Sweep a component value and measure outputs in a SINGLE SPICE call.

    Uses `alter` commands internally — runs the entire sweep in one session.
    For 2-D sweeps, provide component_2 + values_2 (outer × inner loop).

    Example — measure gain for 5 different feedback resistors:
        netlist: "V1 in 0 DC 0.1\\nR1 in inv 10000\\nRF inv out 100000\\n...\\n.end"
        component: "RF"
        values: [10000, 20000, 50000, 100000, 200000]
        outputs: ["$out", "$in"]
        → sweep_results: [{RF: 10000, measurements: {$out: -0.1, $in: 0.1}}, ...]

    Example — 2-D sweep (R1 × RF):
        component: "R1", values: [10000, 20000]
        component_2: "RF", values_2: [50000, 100000]
        → 4 rows: R1×RF combinations

    Args:
        netlist: SPICE netlist (inline, must end with .end)
        component: Component name to sweep (e.g. "R1", "RF")
        values: List of values in SI units (Ohms, Farads, Henrys)
        outputs: Node voltages to measure (e.g. ["$out", "$in"])
        analysis: Nutmeg analysis command (default "op")
        component_2: Optional second component for 2-D sweep
        values_2: Values for the second component
    """
    return json.dumps(
        spice_tools.tool_parameter_sweep(
            _session, netlist, component, values, outputs,
            analysis, component_2, values_2,
        )
    )


@mcp.tool()
def run_ac_single_frequency(
    output_names: list[str], frequency: float
) -> str:
    """Run AC analysis at a single frequency.
    
    Asynchronous — use get_output_data to retrieve results after completion.
    
    Args:
        output_names: List of output probe names to collect data from
        frequency: Analysis frequency in Hz
    """
    return json.dumps(
        simulation_tools.tool_run_ac_single_frequency(
            _session, frequency, output_names
        )
    )


# ═══════════════════════════════════════════════════════════════
# Output Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def set_output_request(
    output_name: str,
    interpolation: str = "raw",
    sample_rate: float = 1000.0,
    num_samples: int = 1000,
    repeat: bool = False,
) -> str:
    """Configure an output data collection request. Must be called before simulation.
    
    Args:
        output_name: Probe name (from list_outputs)
        interpolation: Method - raw, force_step, linear, spline, or coerce
        sample_rate: Sample rate in samples/second
        num_samples: Number of data points to acquire
        repeat: Continue collecting data in repeating blocks
    """
    return json.dumps(
        output_tools.tool_set_output_request(
            _session, output_name, interpolation, sample_rate, num_samples, repeat
        )
    )


@mcp.tool()
def clear_output_request(output_name: str) -> str:
    """Clear a previously set output data request.
    
    Args:
        output_name: Probe name to clear
    """
    return json.dumps(output_tools.tool_clear_output_request(_session, output_name))


@mcp.tool()
def is_output_ready(output_name: str) -> str:
    """Check if output data is ready for retrieval.
    
    Args:
        output_name: Probe name to check
    """
    return json.dumps(output_tools.tool_is_output_ready(_session, output_name))


@mcp.tool()
def get_output_data(output_name: str) -> str:
    """Retrieve simulation output data for a probe.
    
    Returns time/frequency values and real/imaginary data arrays.
    IMPORTANT: Calling this CONSUMES the data block — you cannot call it twice for the same probe.
    For async analyses (ac_sweep, ac_single_frequency), check `is_output_ready` first.
    
    Args:
        output_name: Probe name to retrieve data from (must match exactly from list_outputs)
    """
    return json.dumps(output_tools.tool_get_output_data(_session, output_name))


@mcp.tool()
def summarize_output(
    output_name: str,
    metrics: list[str] | None = None,
) -> str:
    """Retrieve output data and compute summary metrics.
    
    Available metrics: peak, min, mean, rms, steady_state, overshoot,
                       cutoff_frequency_3db, gain_db.
    
    Args:
        output_name: Probe name to analyze
        metrics: List of metrics to compute (None = all)
    """
    return json.dumps(output_tools.tool_summarize_output(_session, output_name, metrics))


# ═══════════════════════════════════════════════════════════════
# Virtual Instrument Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def function_generator(
    input_name: str,
    waveform: str = "sine",
    frequency: float = 1000.0,
    amplitude: float = 1.0,
    offset: float = 0.0,
    duty_cycle: float = 0.5,
    phase: float = 0.0,
    sample_rate: float = 100000.0,
    duration: float = 0.01,
    repeat: bool = True,
) -> str:
    """Generate a waveform and inject it into a circuit input source — like a lab function generator.

    Computes the waveform in Python, then sends it via SetInputDataSampled.
    Call `list_inputs` first to discover valid input_name values.

    Supported waveforms: sine, square, triangle, sawtooth, pulse, dc.

    Workflow: list_inputs → function_generator(input_name, ...) → run simulation

    Args:
        input_name: Input source name (from list_inputs)
        waveform: Waveform shape — sine, square, triangle, sawtooth, pulse, or dc
        frequency: Waveform frequency in Hz (ignored for dc)
        amplitude: Peak amplitude in V or A (depends on source type)
        offset: DC offset added to the waveform
        duty_cycle: Duty cycle for square/pulse waves (0.0 to 1.0)
        phase: Phase offset in degrees
        sample_rate: Samples per second (higher = smoother waveform)
        duration: Waveform duration in seconds
        repeat: Whether to loop the waveform continuously
    """
    return json.dumps(
        instrument_tools.tool_function_generator(
            _session, input_name, waveform, frequency, amplitude, offset,
            duty_cycle, phase, sample_rate, duration, repeat,
        )
    )


@mcp.tool()
def oscilloscope(
    output_names: list[str],
    duration: float = 0.01,
    sample_rate: float = 100000.0,
    interpolation: str = "linear",
    plot: bool = True,
    output_dir: str = "",
    title: str = "Oscilloscope Capture",
) -> str:
    """Capture time-domain waveforms from probes — like a lab oscilloscope.

    Configures output requests, runs a transient simulation, collects data
    from all probes, computes measurements (Vpp, RMS, frequency, etc.),
    and generates a matplotlib waveform plot.

    Call `list_outputs` first to discover valid probe names.

    Workflow: list_outputs → oscilloscope(output_names, duration) → returns data + plot image

    Args:
        output_names: List of probe names (from list_outputs). Required.
        duration: Capture duration in seconds (e.g., 0.01 for 10ms)
        sample_rate: Data sample rate in samples/sec
        interpolation: Method — raw, force_step, linear, spline, or coerce
        plot: Whether to generate a PNG waveform plot (requires matplotlib)
        output_dir: Directory for plot image (default: workspace dir)
        title: Title shown on the plot
    """
    return json.dumps(
        instrument_tools.tool_oscilloscope(
            _session, output_names, duration, sample_rate, interpolation,
            plot, output_dir, title,
        )
    )


@mcp.tool()
def plot_waveform(
    channels: list[dict],
    duration: float = 0.002,
    sample_rate: float = 200000.0,
    title: str = "Waveform",
    output_path: str = "",
    width: int = 1200,
    height_per_channel: int = 280,
    overlay: bool = False,
) -> str:
    """Generate a waveform plot image — no simulation or probes needed.

    Each channel can be defined by mathematical parameters OR raw data:

    Computed waveform channel:
        {label: "Input", waveform: "sine", frequency: 1000, amplitude: 0.1, phase: 0, offset: 0}

    Raw data channel:
        {label: "Output", time: [0, 0.001, ...], values: [-1.0, -0.5, ...]}

    Supported waveforms: sine, square, triangle, sawtooth, pulse, dc.

    Set overlay=True to plot all channels on the same axes (useful for
    comparing multiple outputs at different gains).

    Example — input + inverted output at gain=-10:
        channels: [
            {label: "CH1 Input", waveform: "sine", frequency: 1000, amplitude: 0.1},
            {label: "CH2 Output", waveform: "sine", frequency: 1000, amplitude: 1.0, phase: 180}
        ]

    Args:
        channels: List of channel definitions (see above)
        duration: Time window in seconds (for computed waveforms)
        sample_rate: Samples per second (for computed waveforms)
        title: Plot title
        output_path: File path for PNG output (auto-generated if empty)
        width: Image width in pixels
        height_per_channel: Image height per channel panel in pixels
        overlay: If true, draw all channels on the same axes
    """
    return json.dumps(
        instrument_tools.tool_plot_waveform(
            _session, channels, duration, sample_rate, title,
            output_path, width, height_per_channel, overlay,
        )
    )


# ═══════════════════════════════════════════════════════════════
# Report Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def simulation_report(
    output_path: str,
    title: str = "Multisim Simulation Report",
    description: str = "",
    schematic_image: str = "",
    waveform_images: list[str] | None = None,
    channel_data: list[dict] | None = None,
    include_bom: bool = True,
    include_netlist: bool = True,
) -> str:
    """Generate a self-contained HTML visual report with all simulation results.

    Combines schematic images, oscilloscope waveform plots, measurement tables,
    BOM, and netlist into a single HTML file with dark-themed styling and
    embedded base64 images (no external dependencies).

    Typical workflow:
    1. export_circuit_image → schematic.png
    2. oscilloscope → waveform plot + channel_data
    3. simulation_report(schematic_image, waveform_images, channel_data) → report.html

    Args:
        output_path: Where to save the HTML report file
        title: Report title
        description: Optional analysis description
        schematic_image: Path to schematic image (from export_circuit_image)
        waveform_images: List of waveform plot image paths (from oscilloscope)
        channel_data: Channel measurement data (from oscilloscope response 'channels')
        include_bom: Include Bill of Materials section
        include_netlist: Include circuit netlist section
    """
    return json.dumps(
        report_tools.tool_simulation_report(
            _session, output_path, title, description, schematic_image,
            waveform_images, channel_data, include_bom, include_netlist,
        )
    )


# ═══════════════════════════════════════════════════════════════
# Circuit Template Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def list_circuit_templates(category: str = "all") -> str:
    """List available pre-built circuit templates.

    Templates provide ready-to-use SPICE netlists for common circuits — no .ms14 file needed.

    Use `get_circuit_template` to retrieve a specific template with parameter overrides.

    Args:
        category: Filter by category — all, opamp, filter, or basic
    """
    return json.dumps(circuit_templates.tool_list_circuit_templates(category))


@mcp.tool()
def get_circuit_template(
    template_id: str,
    analysis: str = "dc",
    overrides: dict | None = None,
) -> str:
    """Get a ready-to-use SPICE netlist from a circuit template.

    Returns a complete netlist with parameter values filled in, plus suggested
    nutmeg commands. Pass the netlist directly to `run_spice` or `parameter_sweep`.

    Workflow: list_circuit_templates → get_circuit_template → run_spice

    Example:
        get_circuit_template("inverting_amp", analysis="tran", overrides={"R1": 5000, "Rf": 50000})
        → netlist ready for run_spice with suggested commands

    Args:
        template_id: Template identifier (from list_circuit_templates)
        analysis: "dc" for DC operating point or "tran" for transient analysis
        overrides: Parameter overrides, e.g. {"R1": 5000, "Rf": 50000}
    """
    return json.dumps(
        circuit_templates.tool_get_circuit_template(template_id, analysis, overrides)
    )


@mcp.tool()
def materialize_design_template(
    template_id: str,
    analysis: str = "tran",
    overrides: dict | None = None,
    output_dir: str = "",
    render_schematic: bool = True,
) -> str:
    """Materialize a circuit template into files ready for simulation.

    Creates a .cir netlist file on disk and optionally renders a schematic PNG.
    Returns file paths, netlist text, and suggested commands — everything needed
    to proceed with run_spice or open_netlist.

    Workflow: list_circuit_templates → materialize_design_template → run_spice

    Example:
        materialize_design_template("inverting_amp", analysis="tran")
        → {cir_path, schematic_path, netlist, commands}

    Args:
        template_id: Template identifier (from list_circuit_templates)
        analysis: "dc" for DC operating point or "tran" for transient analysis
        overrides: Parameter overrides, e.g. {"R1": 5000, "Rf": 50000}
        output_dir: Directory for output files (default: C:/mcp_spice_tmp)
        render_schematic: Whether to also render a schematic PNG image
    """
    return json.dumps(
        circuit_templates.tool_materialize_design_template(
            template_id, analysis, overrides, output_dir, render_schematic,
        )
    )


# ═══════════════════════════════════════════════════════════════
# Netlist Builder Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def build_netlist(
    title: str,
    components: list[dict],
    analysis: str = "op",
    output_nodes: list[str] | None = None,
) -> str:
    """Build a SPICE netlist programmatically from component descriptions.

    Constructs a complete SPICE netlist from a list of component specifications.
    Returns the netlist text and suggested nutmeg commands for use with ``run_spice``.

    Component types:
    - R: Resistor — {type, refdes?, n1, n2, value}
    - C: Capacitor — {type, refdes?, n1, n2, value}
    - L: Inductor — {type, refdes?, n1, n2, value}
    - V: Voltage source — {type, refdes?, nplus, nminus, value} (value: "DC 5", "SIN(0 1 1000)", "PULSE(...)")
    - I: Current source — {type, refdes?, nplus, nminus, value}
    - E: VCVS (ideal opamp) — {type, refdes?, out_plus, out_minus, ctrl_plus, ctrl_minus, gain?}
    - GATE: Digital gate — {type, gate_type, inputs, output} (gate_type: AND/OR/NAND/NOR/XOR/NOT)
    - DFF: D flip-flop — {type, data, clk, q, preset?, clear?, qbar?}
    - MODEL: SPICE model — {type, name, model_type, params}
    - RAW: Raw SPICE line — {type, line}
    - COMMENT: Comment — {type, text}

    Workflow: build_netlist → run_spice(netlist, commands)

    Args:
        title: Circuit title
        components: List of component dicts (see types above)
        analysis: Analysis type hint — "op", "tran 1u 10m", "ac dec 10 1 1e6"
        output_nodes: Specific nodes to measure (auto-detected if omitted)
    """
    return json.dumps(
        netlist_builder.tool_build_netlist(title, components, analysis, output_nodes)
    )


# ═══════════════════════════════════════════════════════════════
# Component Catalog Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def search_component_catalog(
    query: str,
    category: str = "all",
    limit: int = 10,
) -> str:
    """Search the Multisim component catalog by keyword or description.

    Returns matching components with their database coordinates
    (group/family/name) for use with ``replace_component``, plus SPICE
    model snippets for use with ``run_spice``.

    Categories: opamp, comparator, regulator, diode, transistor, timer,
    ttl, cmos, source, indicator — or 'all' for no filter.

    Examples:
    - search_component_catalog("741 op-amp")
    - search_component_catalog("nand gate", category="ttl")
    - search_component_catalog("counter", category="ttl")

    Args:
        query: Search keywords (name, function, part number)
        category: Filter by component category
        limit: Maximum results to return
    """
    return json.dumps(
        component_catalog.tool_search_component_catalog(query, category, limit)
    )


@mcp.tool()
def list_component_categories() -> str:
    """List all component categories in the catalog with item counts."""
    return json.dumps(component_catalog.tool_list_component_categories())


# ═══════════════════════════════════════════════════════════════
# Design Rule Checking Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def check_design_rules(
    netlist: str,
    max_power_watts: float = 10.0,
    skip_rules: list[str] | None = None,
) -> str:
    """Run design rule checks on a SPICE netlist before simulation.

    Analyzes the netlist for common issues that would cause simulation
    failure or unexpected results:

    - GROUND_REF: Missing ground reference
    - FLOATING_NODE: Nodes with only one connection
    - VSOURCE_PARALLEL: Voltage sources in parallel (short circuit)
    - R_NEGATIVE / R_VERY_LOW / R_VERY_HIGH: Suspicious resistor values
    - POWER_BUDGET: Estimated power exceeds limit
    - DIGITAL_PULLDOWN: XSPICE outputs without pull-down/pull-up resistors
    - SUPPLY_UNDRIVEN: Power rail nodes without sources
    - AC_BIAS: AC sources present but no DC bias point detected
    - MISSING_END: Netlist missing required .end directive
    - SUBCKT_UNDEFINED: X-instance references undefined subcircuit

    Workflow: build_netlist → check_design_rules → run_spice

    Args:
        netlist: SPICE netlist text to check
        max_power_watts: Maximum acceptable power (default 10W)
        skip_rules: Rules to skip, e.g. ["FLOATING_NODE"]
    """
    return json.dumps(
        design_checks.tool_check_design_rules(netlist, max_power_watts, skip_rules)
    )


# ═══════════════════════════════════════════════════════════════
# Block Simulation Pipeline Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def simulate_block(
    block_name: str,
    netlist: str,
    commands: list[str],
    expected_outputs: dict[str, dict] | None = None,
    tolerance_percent: float = 5.0,
) -> str:
    """Simulate a circuit block and verify outputs against expected values.

    Wraps ``run_spice`` with automatic verification. Use to test individual
    functional blocks before combining them into larger systems.

    Args:
        block_name: Block identifier (e.g., "input_stage", "gain_stage")
        netlist: SPICE netlist for the block
        commands: Nutmeg commands (same as run_spice)
        expected_outputs: Verification targets, e.g.:
            {"$out": {"expected": -10.0, "unit": "V"},
             "$gain": {"expected": 10, "check": "abs"}}
            check modes: "value" (default), "abs" (absolute value), "sign"
        tolerance_percent: Pass/fail tolerance (default 5%)
    """
    return json.dumps(
        block_sim.tool_simulate_block(
            block_name, netlist, commands, expected_outputs, tolerance_percent,
        )
    )


@mcp.tool()
def simulate_pipeline(
    blocks: list[dict],
    tolerance_percent: float = 5.0,
) -> str:
    """Run a sequence of block simulations as a verification pipeline.

    Each block is simulated independently with optional verification.
    Returns per-block and overall pass/fail status.

    Args:
        blocks: List of block specs, each with:
            - name: block identifier
            - netlist: SPICE netlist text
            - commands: nutmeg commands list
            - expected_outputs: optional verification targets
        tolerance_percent: Pass/fail tolerance (default 5%)
    """
    return json.dumps(
        block_sim.tool_simulate_pipeline(blocks, tolerance_percent)
    )


@mcp.tool()
def list_design_templates(category: str = "all") -> str:
    """List available pre-built .ms14 design templates.

    Shows Multisim schematic files with known component topology,
    enabling open → set_rlc_value → replace_component → simulate workflows.

    Categories: opamp, filter, basic, digital, or 'all'.
    """
    return json.dumps(block_sim.tool_list_design_templates(category))


@mcp.tool()
def get_design_template_details(template_id: str) -> str:
    """Get detailed info about a .ms14 design template.

    Returns component topology, probe names, adjustable parameters,
    and a step-by-step workflow for using the template with MCP tools.

    Args:
        template_id: Template ID from list_design_templates
    """
    return json.dumps(block_sim.tool_get_design_template_details(template_id))


# ═══════════════════════════════════════════════════════════════
# Schematic Rendering Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def render_netlist_schematic(
    netlist: str,
    output_path: str = "",
    title: str | None = None,
    width: int = 1400,
    show_nodes: bool = True,
) -> str:
    """Render a SPICE netlist as a circuit schematic image.

    Generates a schematic diagram with standard symbols (resistors, capacitors,
    inductors, voltage sources, opamp/VCVS) and automatic wire routing.

    This solves the critical gap where open_netlist + export_circuit_image
    produces a blank grid image. Use this tool instead to generate schematics
    from SPICE netlist text.

    Workflow:
        build_netlist → render_netlist_schematic → (use in reports)

    Args:
        netlist: SPICE netlist text (same format as run_spice input)
        output_path: File path for PNG output (auto-generated if empty)
        title: Schematic title (auto-detected from netlist comment if omitted)
        width: Image width in pixels
        show_nodes: Whether to label node connection points
    """
    return json.dumps(
        schematic_render.tool_render_netlist_schematic(
            netlist, output_path, title, width, show_nodes,
        )
    )


# ═══════════════════════════════════════════════════════════════
# Transient Sweep Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def transient_sweep(
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
) -> str:
    """Run transient analysis across multiple parameter variants with full waveforms.

    Unlike ``parameter_sweep`` (scalar OP results only), this tool returns
    complete time-series data for each variant along with auto-computed
    measurements and labeled overlay plots.

    Each result includes the variant label (e.g. "Rf=10k"), component value,
    full waveform data, and structured measurements (Vpp, RMS, gain, etc.).

    Example — sweep feedback resistor in inverting amplifier:
        netlist: "Vi in 0 SIN(0 0.1 1000)\\nR1 in inv 10000\\nRf inv out 10000\\nE1 out 0 0 inv 200000\\n.end"
        component: "Rf"
        values: [10000, 20000, 47000, 100000]
        outputs: ["$out", "$in"]
        stop_time: 0.005
        → variants: [{variant: "Rf=10k", measurements: {$out: {vpp: 0.2, ...}}, waveforms: ...}, ...]
        → summary_table: [{variant: "Rf=10k", $out_vpp: 0.2, voltage_gain: -1.0}, ...]
        → plot_images: ["sweep_out_overlay.png"]

    Args:
        netlist: SPICE netlist (must end with .end)
        component: Component name to sweep (e.g., "Rf", "R1")
        values: List of values in SI units
        outputs: Node voltages to capture (e.g., ["$out", "$in"])
        stop_time: Simulation stop time in seconds
        time_step: Simulation time step in seconds
        measurements: Metrics list — vpp, peak, valley, rms, mean, frequency,
                      rise_time, fall_time, overshoot, steady_state_mean, etc.
                      None = compute all available.
        plot: Whether to generate waveform plot images
        overlay: If True, overlay all variants per output on one plot
        output_dir: Directory for plot images (default: C:/mcp_spice_tmp)
        title: Plot and report title
        timeout_ms: Per-variant simulation timeout in ms
    """
    return json.dumps(
        transient_sweep_mod.tool_transient_sweep(
            _session, netlist, component, values, outputs,
            stop_time, time_step, measurements, plot, overlay,
            output_dir, title, timeout_ms,
        )
    )


# ═══════════════════════════════════════════════════════════════
# Signal Measurement Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def measure_signals(
    signals: list[dict],
    metrics: list[str] | None = None,
    steady_state_fraction: float = 0.5,
    cycle_index: int | None = None,
    gain_pairs: list[dict] | None = None,
) -> str:
    """Extract structured measurements from time-domain waveform data.

    Computes standard signal metrics without requiring a new simulation.
    Feed it waveform data from ``run_spice``, ``transient_sweep``, or
    ``oscilloscope`` and get back structured measurements.

    Available metrics: vpp, peak, valley, rms, mean, frequency, period,
    rise_time, fall_time, overshoot, duty_cycle,
    steady_state_mean, steady_state_rms, thd, slew_rate, settling_time.

    Can also compute inter-signal gain and phase shift via ``gain_pairs``.

    Each signal dict must contain:
        - ``label``: Signal name (e.g., "$out", "CH1")
        - ``time``: Time array [t0, t1, ...]
        - ``values``: Amplitude array [v0, v1, ...]

    Each gain_pair dict:
        - ``input``: Label of input signal
        - ``output``: Label of output signal

    Example:
        signals: [{label: "$out", time: [...], values: [...]},
                  {label: "$in", time: [...], values: [...]}]
        gain_pairs: [{input: "$in", output: "$out"}]
        → results: [{label: "$out", vpp: 1.98, rms: 0.707, frequency: 1000, ...}]
        → gain_results: [{input: "$in", output: "$out", voltage_gain: -10.0, gain_db: 20.0}]

    Args:
        signals: List of signal dicts with label, time, and values fields
        metrics: Metrics to compute (None = all available)
        steady_state_fraction: Last N% of signal for steady-state metrics (0.0-1.0)
        cycle_index: Measure only this cycle number (0-indexed, None = full signal)
        gain_pairs: List of {input, output} dicts for gain calculations
    """
    return json.dumps(
        signal_measure.tool_measure_signals(
            signals, metrics, steady_state_fraction, cycle_index, gain_pairs,
        )
    )


# ═══════════════════════════════════════════════════════════════
# Markdown Report Tools
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
def generate_markdown_report(
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
) -> str:
    """Generate a complete Markdown lab report from structured inputs.

    Combines all simulation artifacts — schematic images, waveform plots,
    measurement tables, SPICE netlist — into a publication-ready Markdown
    document. Supports Chinese (zh) and English (en) section headings.

    Typical workflow:
    1. ``build_netlist`` → get circuit netlist
    2. ``render_netlist_schematic`` → get schematic image
    3. ``transient_sweep`` → get waveform images + sweep_summary
    4. ``generate_markdown_report(...)`` → complete .md report file

    Args:
        output_path: File path for the generated .md file
        title: Report title (e.g., "反相放大器实验报告")
        experiment_purpose: Purpose / objective description
        experiment_conditions: List of {name, value} condition entries
        netlist: SPICE netlist text to include
        schematic_image: Path to schematic image (from render_netlist_schematic)
        waveform_images: List of waveform plot image paths
        measurement_table: Generic data table — list of row dicts
        sweep_summary: Summary table from transient_sweep results
        analysis_text: Free-form analysis / discussion text
        conclusion: Experiment conclusion text
        extra_sections: Additional sections as [{title, content}]
        embed_images: Embed images as base64 (for standalone .md files)
        language: "zh" for Chinese headings, "en" for English
    """
    return json.dumps(
        markdown_report.tool_generate_markdown_report(
            output_path, title, experiment_purpose, experiment_conditions,
            netlist, schematic_image, waveform_images, measurement_table,
            sweep_summary, analysis_text, conclusion, extra_sections,
            embed_images, language,
        )
    )


# ═══════════════════════════════════════════════════════════════
# MCP Prompt Templates (Workflow Guides)
# ═══════════════════════════════════════════════════════════════


@mcp.prompt()
def analyze_circuit(design_path: str, analysis_type: str = "transient") -> str:
    """Guided workflow to open a circuit and run an analysis."""
    analysis_help = {
        "transient": (
            "For transient analysis:\n"
            "1. Call `list_outputs` to find probe names\n"
            "2. Call `run_transient(output_names=[...], stop_time=0.01)` — this is synchronous\n"
            "3. Call `get_output_data(output_name)` for each probe\n"
            "4. Optionally use `summarize_output` for quick metrics"
        ),
        "ac_sweep": (
            "For AC sweep analysis:\n"
            "1. Call `list_outputs` to find probe names\n"
            "2. Call `run_ac_sweep(output_names=[...], start_frequency=1, stop_frequency=1e6)`\n"
            "3. Poll `is_output_ready(output_name)` until true\n"
            "4. Call `get_output_data(output_name)` for each probe"
        ),
        "dc": (
            "For DC operating point:\n"
            "1. Call `list_outputs` to find probe names\n"
            "2. Call `run_dc_operating_point(output_names=[...])`\n"
            "3. Call `get_output_data(output_name)` for each probe"
        ),
    }
    guide = analysis_help.get(analysis_type, analysis_help["transient"])

    return (
        f"Open the Multisim design at `{design_path}` and run a {analysis_type} analysis.\n\n"
        f"Steps:\n"
        f"1. Call `connect()` to start Multisim\n"
        f"2. Call `open_design(path='{design_path}')`\n"
        f"{guide}\n\n"
        f"Present the results clearly with units and a summary of key observations."
    )


@mcp.prompt()
def spice_analysis(circuit_description: str, analysis_goal: str = "measure gain") -> str:
    """Guided workflow to build a SPICE netlist and simulate via run_spice."""
    return (
        f"Analyze the following circuit using `run_spice`:\n\n"
        f"**Circuit:** {circuit_description}\n"
        f"**Goal:** {analysis_goal}\n\n"
        f"Steps:\n"
        f"1. Call `connect()` to start Multisim\n"
        f"2. Build a SPICE netlist string for the circuit:\n"
        f"   - Define all components (R, C, L, V, I, subcircuits)\n"
        f"   - Use node names that describe function (inv, out, vcc, etc.)\n"
        f"   - End with `.end`\n"
        f"3. Choose nutmeg commands based on goal:\n"
        f"   - DC bias: `[\"op\", \"print $out $in\"]`\n"
        f"   - Gain: `[\"alter Vi = 0.1\", \"op\", \"print $out $in\"]`\n"
        f"   - Sweep: repeat `alter`/`op`/`print` blocks with different values\n"
        f"   - Transient: `[\"tran 1u 10m\", \"print $out\"]`\n"
        f"4. Call `run_spice(netlist=..., commands=[...])` — ONE call does everything\n"
        f"5. Present results in a clear table with calculated metrics\n\n"
        f"Remember:\n"
        f"- Node voltages use `$` prefix in print: `print $out` not `print v(out)`\n"
        f"- `alter R1 = 20000` changes R1 to 20kΩ (SI units)\n"
        f"- XSPICE does not support `wrdata` — use `print` only\n"
        f"- Each `print` command produces one result dict in the output"
    )


@mcp.prompt()
def parameter_sweep(
    design_path: str,
    component_refdes: str,
    start_value: str,
    end_value: str,
    steps: str,
) -> str:
    """Guided workflow to sweep a component value and compare results."""
    return (
        f"Perform a parameter sweep on component `{component_refdes}` "
        f"from {start_value} to {end_value} in {steps} steps.\n\n"
        f"Workflow:\n"
        f"1. `connect()` → `open_design('{design_path}')`\n"
        f"2. `list_outputs()` to discover probes\n"
        f"3. For each step value:\n"
        f"   a. `stop_simulation()` (if running)\n"
        f"   b. `set_rlc_value(refdes='{component_refdes}', value=<SI_value>)`\n"
        f"   c. Run analysis (`run_transient` or `run_dc_operating_point`)\n"
        f"   d. `get_output_data(...)` and record results\n"
        f"4. Compare across all steps and present a table or chart description\n\n"
        f"Remember: all values must be in base SI units (Ohms, Farads, Henrys).\n"
        f"Convert: 1kΩ=1000, 10nF=1e-8, 4.7µH=4.7e-6"
    )


@mcp.prompt()
def troubleshoot_circuit(design_path: str, symptom: str = "") -> str:
    """Guided workflow to diagnose a circuit issue."""
    return (
        f"Troubleshoot the Multisim circuit at `{design_path}`.\n"
        f"{'Reported symptom: ' + symptom + chr(10) if symptom else ''}\n"
        f"Diagnostic plan:\n"
        f"1. `connect()` → `open_design('{design_path}')`\n"
        f"2. `list_components()` — review all components and their values\n"
        f"3. `list_outputs()` — identify measurement probes\n"
        f"4. `run_dc_operating_point(output_names=[...])` — check bias points\n"
        f"5. `get_output_data(...)` — analyze DC results for anomalies\n"
        f"6. If needed, `run_transient(...)` to check time-domain behavior\n"
        f"7. `export_netlist()` — review circuit topology\n\n"
        f"For each step, report findings and flag any out-of-range values.\n"
        f"Suggest corrections using `set_rlc_value` or `replace_component`."
    )


@mcp.prompt()
def export_report(design_path: str, output_dir: str = ".") -> str:
    """Guided workflow to generate a complete circuit report."""
    return (
        f"Generate a full report for the Multisim circuit at `{design_path}`.\n\n"
        f"Steps:\n"
        f"1. `connect()` → `open_design('{design_path}')`\n"
        f"2. `export_circuit_image(path='{output_dir}/schematic.png')` — capture schematic\n"
        f"3. `export_bom()` — get Bill of Materials\n"
        f"4. `export_netlist()` — get circuit netlist\n"
        f"5. `list_components()` — enumerate all components with values\n"
        f"6. `run_dc_operating_point(...)` → `get_output_data(...)` — DC analysis\n"
        f"7. If applicable, run transient or AC analysis\n\n"
        f"Compile everything into a structured report with:\n"
        f"- Circuit description and schematic reference\n"
        f"- BOM table\n"
        f"- Simulation results with key metrics\n"
        f"- Design observations and recommendations"
    )


@mcp.prompt()
def lab_report(
    circuit_type: str,
    signal_params: str = "1kHz sine, 100mV amplitude, 0V offset",
    sweep_description: str = "",
    design_path: str = "",
    output_dir: str = "report_output",
) -> str:
    """End-to-end workflow to generate a lab report with data, plots, and analysis.

    Handles both cases:
    - WITH .ms14 file: opens design, exports schematic, builds netlist from export
    - WITHOUT .ms14 file: AI builds SPICE netlist from circuit_type description

    Uses only MCP tools — no custom scripts needed.
    """
    has_file = bool(design_path.strip())

    if has_file:
        circuit_steps = (
            f"1. `connect()` → `open_design('{design_path}')`\n"
            f"2. `export_circuit_image(path='{output_dir}/schematic.png')` — capture schematic\n"
            f"3. `export_netlist()` — get SPICE netlist for run_spice/parameter_sweep\n"
            f"4. `list_components()` — discover component RefDes and values\n"
        )
    else:
        circuit_steps = (
            f"1. `connect()`\n"
            f"2. Try `list_circuit_templates()` to find a matching template for **{circuit_type}**\n"
            f"3. If template found: `get_circuit_template(id, analysis='tran', overrides={{...}})`\n"
            f"4. If no template: build SPICE netlist from first principles:\n"
            f"   - Use VCVS (`E1 out 0 inp inv 200000`) as ideal opamp if needed\n"
            f"   - End with `.end`\n"
            f"   - No schematic image — describe the circuit in text and formulas\n"
        )

    sweep_guidance = sweep_description or (
        "Sweep key component values to show the circuit's behavior. "
        "For amplifiers: sweep R1 and/or RF across 3-5 values. "
        "For filters: sweep frequency or R/C values."
    )

    return (
        f"# Lab Report Generation Workflow\n\n"
        f"**Circuit type:** {circuit_type}\n"
        f"**Signal:** {signal_params}\n"
        f"**Sweep plan:** {sweep_guidance}\n"
        f"{'**Design file:** ' + design_path if has_file else '**No .ms14 file — build netlist from description**'}\n\n"
        f"## Step 1: Circuit Setup\n\n"
        f"{circuit_steps}\n\n"
        f"## Step 2: Parameter Sweep (ONE tool call)\n\n"
        f"Use `parameter_sweep` to run all configurations at once:\n"
        f"```\n"
        f"parameter_sweep(\n"
        f"    netlist=<netlist_string>,\n"
        f"    component=\"RF\",          # component to sweep\n"
        f"    values=[10000, 20000, 50000, 100000],  # SI units\n"
        f"    outputs=[\"$out\", \"$in\"],  # nodes to measure\n"
        f")\n"
        f"```\n"
        f"For 2-D sweeps, add `component_2` and `values_2`.\n\n"
        f"## Step 3: Waveform Plots from REAL Simulation Data\n\n"
        f"Use `run_spice` with transient analysis to get real waveform data:\n"
        f"```\n"
        f"run_spice(netlist=<tran_netlist>, commands=[\"tran 5e-06 0.002\", \"print $out $in\"])\n"
        f"→ results: [{{\"_type\": \"transient\", \"time\": [...], \"$out\": [...], \"$in\": [...]}}]\n"
        f"```\n"
        f"Then feed the real data directly into `plot_waveform`:\n"
        f"```\n"
        f"plot_waveform(\n"
        f"    channels=[\n"
        f"        {{label: \"Input\", time: result[\"time\"], values: result[\"$in\"]}},\n"
        f"        {{label: \"Output\", time: result[\"time\"], values: result[\"$out\"]}},\n"
        f"    ],\n"
        f"    title=\"Av=-10, R1=10kΩ RF=100kΩ\",\n"
        f"    output_path=\"{output_dir}/wave_gain10.png\",\n"
        f")\n"
        f"```\n"
        f"Run one `run_spice` + `plot_waveform` pair per configuration you want to plot.\n"
        f"For comparison overlays, set `overlay=True` with multiple output channels.\n\n"
        f"## Step 4: Write Markdown Report\n\n"
        f"Write a markdown file with:\n"
        f"1. 实验目的 — objectives\n"
        f"2. 实验原理 — theory with LaTeX formulas\n"
        f"3. 实验电路 — schematic image (if available) + component table\n"
        f"4. 实验内容与数据 — sweep results tables + waveform images\n"
        f"5. 实验结果分析 — error analysis, observations\n"
        f"6. 实验结论 — conclusions\n\n"
        f"Use relative image paths: `![](schematic.png)`, `![](wave_gain10.png)`\n\n"
        f"## Important Notes\n\n"
        f"- `parameter_sweep` replaces multiple `run_spice` calls for DC data\n"
        f"- `run_spice` with `tran` + `print` returns real time-series data arrays\n"
        f"- `plot_waveform` can plot either raw data or computed waveforms\n"
        f"- Prefer real simulation data over computed approximations\n"
        f"- `get_circuit_template` provides ready-to-use netlists (no .ms14 needed)\n"
        f"- For SPICE netlists: node voltages use `$` prefix (`$out`, `$in`)\n"
        f"- All values in SI units (Ohms, Farads, Henrys)\n"
        f"- Gains can be computed from sweep results: gain = $out / $in"
    )


@mcp.prompt()
def instrument_workflow(
    design_path: str,
    input_source: str = "",
    waveform: str = "sine",
    frequency: str = "1000",
    output_probes: str = "",
) -> str:
    """Guided workflow to use virtual instruments (Function Generator + Oscilloscope)."""
    return (
        f"Use virtual instruments to test the Multisim circuit at `{design_path}`.\n\n"
        f"Steps:\n"
        f"1. `connect()` → `open_design('{design_path}')`\n"
        f"2. `list_inputs()` — discover valid input source names\n"
        f"3. `list_outputs()` — discover valid output probe names\n"
        f"4. `function_generator(input_name='{input_source}', waveform='{waveform}', "
        f"frequency={frequency})` — inject test signal\n"
        f"5. `oscilloscope(output_names=['{output_probes}'], duration=0.01)` "
        f"— capture response waveforms\n"
        f"6. `export_circuit_image(path='schematic.png')` — capture schematic\n"
        f"7. `simulation_report(output_path='report.html', "
        f"schematic_image='schematic.png', "
        f"waveform_images=[oscilloscope_plot_path], "
        f"channel_data=oscilloscope_channels)` — generate visual HTML report\n\n"
        f"Present the measurements and describe what the output waveforms reveal about circuit behavior."
    )


# ═══════════════════════════════════════════════════════════════
# Server Entry Point
# ═══════════════════════════════════════════════════════════════


def main() -> None:
    """Run the Multisim MCP server."""
    logger.info("Starting Multisim MCP Server v0.1.0")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
