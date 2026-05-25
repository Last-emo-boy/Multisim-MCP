# Multisim MCP Server — Copilot Instructions

This project is an MCP (Model Context Protocol) server that wraps the NI Multisim COM Automation API, enabling AI agents to control circuit simulation via tools.

## Architecture

- **COM Adapter** (`src/multisim_mcp/com_adapter.py`): Low-level Python wrapper around `MultisimInterface.MultisimApp` COM object via `win32com.client.Dispatch` (late binding). All COM interactions are here.
- **Session Manager** (`src/multisim_mcp/session.py`): State machine tracking session lifecycle (idle → design_opened → modified → simulation_running → etc.), snapshots, and audit log.
- **Tool Modules** (`src/multisim_mcp/tools/`): Each file groups related MCP tool implementations. Functions are prefixed `tool_*` and return `dict` via `ToolResponse.model_dump()`.
  - `file_tools.py`: Session & file management (connect, open, save)
  - `enum_tools.py`: Enumeration & export (list_components, export_netlist, etc.)
  - `modify_tools.py`: Circuit modification (set_rlc_value, replace_component, etc.)
  - `simulation_tools.py`: Simulation control & analysis (run_transient, run_ac_sweep, etc.)
  - `output_tools.py`: Output data retrieval (get_output_data, summarize_output, etc.)
  - `spice_tools.py`: High-level SPICE analysis via DoCommandLine (run_spice, parameter_sweep). Includes `.end` pre-flight validation, error categorization (CONVERGENCE/SINGULAR_MATRIX/TIMESTEP/GENERIC), and per-point error tracking in parameter_sweep
  - `instrument_tools.py`: Virtual instruments — function_generator (waveform generation + injection), oscilloscope (transient capture + plotting), and plot_waveform (standalone plot generation)
  - `report_tools.py`: Visual HTML report generation (simulation_report)
  - `circuit_templates.py`: Pre-built SPICE netlists for common circuits (list_circuit_templates, get_circuit_template, materialize_design_template)
  - `netlist_builder.py`: Programmatic netlist construction engine (build_netlist)
  - `component_catalog.py`: Searchable component database catalog (search_component_catalog, list_component_categories)
  - `design_checks.py`: Pre-simulation design rule checking (check_design_rules)
  - `block_sim.py`: Block-level simulation pipeline + .ms14 design templates (simulate_block, simulate_pipeline, list_design_templates, get_design_template_details)
  - `schematic_render.py`: Pure-Pillow netlist → schematic image renderer (render_netlist_schematic)
  - `transient_sweep.py`: Transient parameter sweep with full waveforms + auto measurements (transient_sweep)
  - `signal_measure.py`: Structured measurement extraction engine — Vpp, RMS, gain, rise_time, THD, slew_rate, settling_time, phase_shift, etc. (measure_signals)
  - `markdown_report.py`: Markdown lab report generator with zh/en support (generate_markdown_report)
- **Server** (`src/multisim_mcp/server.py`): Registers `@mcp.tool()` and `@mcp.prompt()` with FastMCP. Each tool is a thin wrapper that delegates to the tool module and serializes via `json.dumps`.
- **Models** (`src/multisim_mcp/models.py`): Pydantic models for typed responses.

## Key COM Patterns

- **Parameterized property PUT** (RLCValue, CircuitParameterValue): `win32com` late-binding can't do `Property Let` with index params. Use `_oleobj_.Invoke(dispid, 0, pythoncom.DISPATCH_PROPERTYPUT, 0, key, value)`.
- **ByRef out-params** (GetOutputData, WaitForNextOutput): COM ByRef parameters come back as extra tuple elements in the return value.
- **Late binding**: We use `Dispatch()` (not `EnsureDispatch/gencache`) so there's no generated type library. All method calls are by name.
- **DoCommandLine = NUTMEG**: The commandFile is a nutmeg script, not raw SPICE. Use `source path/to.cir` to load a netlist, then explicit analysis commands (`op`, `dc`, `tran`, `ac`). Node voltages require `$` prefix: `print $out $vcc`.

## SPICE Analysis via run_spice

`run_spice` wraps DoCommandLine into a single high-level tool:
1. Writes inline netlist to temp `.cir` file (auto-sanitized to ASCII)
2. Builds a nutmeg script: `source` + user commands
3. Calls `NewFile()` → `DoCommandLine()` → `WaitForNextOutput()`
4. Parses log output — extracts values from `print` commands
5. Returns structured results:
   - **Scalar** (after `op`): `{results: [{"$out": -10.0, "$in": 1.0}]}`
   - **Time-series** (after `tran`): `{results: [{"_type": "transient", "time": [...], "$out": [...], "$in": [...]}]}`

The XSPICE log duplicates every value/row; the parser de-duplicates automatically.

### Transient Data Capture

After `tran` analysis, `print $out $in` produces full time-series data in the log:
```
Index   time            $out            $in
0       0.000000e+00    0.000000e+00    0.000000e+00
1       5.000000e-08    -3.141420e-04   3.141593e-05
...
```
The parser detects this tabular format and returns arrays. Feed directly into `plot_waveform`:
```python
result = run_spice(netlist, ["tran 5e-06 0.002", "print $out $in"])
tran_data = result["data"]["results"][0]  # _type: "transient"
plot_waveform(channels=[
    {"label": "Input", "time": tran_data["time"], "values": tran_data["$in"]},
    {"label": "Output", "time": tran_data["time"], "values": tran_data["$out"]},
])
```

## Parameter Sweep via parameter_sweep

`parameter_sweep` builds on `run_spice` to run multi-point sweeps in a single SPICE call:
1. Sets the first value in the netlist
2. Builds `alter` commands for subsequent values
3. Runs `analysis` + `print` for each configuration
4. Maps parsed results back to parameter values
5. Returns `{sweep_results: [{component: value, measurements: {...}, error: null}, ...]}` — one row per sweep point

Supports 2-D sweeps with `component_2` + `values_2` (outer × inner loop).

Per-point error tracking: each sweep point includes an `error` field (null on success, string on failure). The log message reports `{num_ok}/{total} sweep points succeeded`.

## Standalone Plotting via plot_waveform

`plot_waveform` generates multi-channel waveform plots without simulation:
- Accepts computed waveforms (sine, square, triangle, etc.) or raw data arrays
- Renders with Pillow (no matplotlib dependency)
- Supports overlay mode for comparing multiple signals
- Returns PNG file path + base64 preview

## Circuit Templates via circuit_templates.py

Pre-built SPICE netlists for common circuits — no `.ms14` file required:
- **Opamp**: inverting_amp, noninverting_amp, voltage_follower, summing_amp, differential_amp, integrator, differentiator
- **Filter**: rc_lowpass, rc_highpass, active_lowpass (Sallen-Key)
- **Basic**: voltage_divider, rl_circuit, rc_circuit
- **Digital**: and_gate, or_gate, not_gate, nand_gate, xor_gate, d_flipflop, jk_flipflop, sr_latch, half_adder, full_adder, mux_2to1
- **Mixed**: comparator

Each template provides:
- DC and/or transient netlist variants with parameterizable values
- Suggested nutmeg commands for analysis (RC time-constant aware: auto-computes tstep/tstop from R×C for filter templates)
- Metadata: gain formula, node descriptions, Chinese name

Usage: `list_circuit_templates()` → `get_circuit_template(id, analysis, overrides)` → `run_spice(netlist, commands)`

`materialize_design_template(template_id, analysis, overrides, output_dir, render_schematic)` writes a `.cir` file to disk and optionally renders a schematic PNG. Returns file paths + netlist + commands ready for `run_spice`.

**Important**: SPICE netlists must be ASCII-only. `run_spice` automatically sanitizes non-ASCII characters.

## Netlist Builder via netlist_builder.py

Programmatic circuit construction engine:
- `CircuitBuilder` class with methods: `add_resistor`, `add_capacitor`, `add_inductor`, `add_voltage_source`, `add_current_source`, `add_vcvs`, `add_xspice`, `add_digital_gate`, `add_dff`
- Automatic RefDes generation and pull-down resistors on digital outputs
- Digital gate input validation: NOT/INV/BUF require exactly 1 input, multi-input gates require ≥2
- Auto-VCC/VDD source generation: if supply nodes (vcc, vdd, vss, vee) are referenced but not driven, auto-creates voltage sources
- `validate()` method: checks for floating nodes (single-connection) and missing ground reference, returns warnings
- MCP tool: `build_netlist(title, components, analysis, output_nodes)` → netlist + commands + warnings for `run_spice`
- Component types: R, C, L, V, I, E, GATE, DFF, MODEL, RAW, COMMENT

Usage: `build_netlist(title="...", components=[...])` → `run_spice(netlist, commands)`

## Component Catalog via component_catalog.py

Searchable index of Multisim Master Database components:
- Categories: opamp, comparator, regulator, diode, transistor, timer, ttl, cmos, source, indicator
- Each entry has Multisim database coordinates (group/family/name) for `replace_component`
- Optional SPICE model snippets for `run_spice`
- Tools: `search_component_catalog(query, category)`, `list_component_categories()`

## Design Rule Checking via design_checks.py

Pre-simulation netlist verification:
- Checks: GROUND_REF, FLOATING_NODE, VSOURCE_PARALLEL, R_NEGATIVE/R_VERY_LOW/R_VERY_HIGH, POWER_BUDGET, DIGITAL_PULLDOWN (pull-down AND pull-up), SUPPLY_UNDRIVEN, AC_BIAS, MISSING_END, SUBCKT_UNDEFINED
- AC_BIAS: warns when AC sources are present but no DC bias point is detected
- MISSING_END: error if netlist lacks `.end` directive
- SUBCKT_UNDEFINED: error if X-instances reference undefined subcircuits
- Tool: `check_design_rules(netlist, max_power_watts, skip_rules)` → issues list with severity/rule/message/suggestion

## Block Simulation Pipeline via block_sim.py

Block-level simulation with automatic verification:
- `simulate_block(block_name, netlist, commands, expected_outputs, tolerance_percent)` — run + verify a single block
- `simulate_pipeline(blocks)` — run multiple blocks with per-block and overall pass/fail
- `.ms14 Design Templates`: `list_design_templates()`, `get_design_template_details(id)` — pre-built schematic templates with workflow guides

## Schematic Rendering via schematic_render.py

Pure-Pillow netlist → schematic image renderer (no Multisim GUI required):
- Parses SPICE netlists into component lists, draws standard circuit symbols (resistor zigzag, capacitor plates, inductor humps, voltage source circle, current source with arrow, opamp/VCVS triangle, diode triangle+bar, BJT NPN/PNP with arrow, MOSFET, digital gate boxes)
- Per-component-type color coding (gold resistors, blue capacitors, green voltage sources, etc.) with color legend
- Automatic grid-based layout with staggered L-shaped wire routing to avoid overlaps
- Smart junction dots (only at true junctions, single label per net)
- Auto-sizing canvas width based on component count
- Solves the critical gap where `open_netlist + export_circuit_image` produces a blank grid image
- Tool: `render_netlist_schematic(netlist, output_path, title, width, show_nodes)` → PNG file path

Usage: `build_netlist(...)` → `render_netlist_schematic(netlist)` → use image in reports

## Transient Sweep via transient_sweep.py

Full-waveform parameter sweep — unlike `parameter_sweep` (scalar OP only):
- Runs transient analysis for each parameter variant with full time-series data
- Auto-labels each result: `variant: "Rf=10k"`, `component`, `value`, `value_display`
- Auto-computes measurements (Vpp, RMS, gain, etc.) via signal_measure engine
- Generates overlay or panel plots (matplotlib preferred, Pillow fallback)
- Y-axis normalization in overlay mode: consistent axis limits across all variant traces for visual comparison
- Returns: `variants` (full waveform data per variant), `summary_table` (flat summary), `plot_images` (PNG paths)

Usage: `build_netlist(...)` → `transient_sweep(netlist, component="Rf", values=[10k, 20k, 47k], outputs=["$out", "$in"])` → labeled results + plots

## Signal Measurement via signal_measure.py

Structured measurement extraction from time-domain waveforms:
- Core engine: `compute_measurements(time, values, metrics)` → dict with vpp, peak, valley, rms, mean, frequency, period, rise_time, fall_time, overshoot, duty_cycle, steady_state_mean, steady_state_rms, thd, slew_rate, settling_time
- THD (Total Harmonic Distortion): DFT-based, sums harmonics 2-5 vs fundamental, returns percentage
- Slew rate: max |dV/dt| across all sample pairs, returns V/s
- Settling time: walks backward from signal end to find last point outside 2% Vpp band, returns seconds
- Phase shift: `compute_phase_shift(time, signal_a, signal_b)` via zero-crossing timing, wraps to [-180°, 180°]
- Gain computation: `compute_gain(input_values, output_values, time=None)` → voltage_gain, gain_db, phase_inverted, input_vpp, output_vpp, phase_shift_deg (when time provided)
- Tool: `measure_signals(signals, metrics, gain_pairs)` — standalone MCP tool for post-simulation analysis
- Zero-crossing detection for frequency, threshold crossing for rise/fall time

Usage: After `run_spice` or `transient_sweep`, feed waveform arrays into `measure_signals` for structured metrics.

## Markdown Report via markdown_report.py

Complete Markdown lab report generator:
- Combines schematic images, waveform plots, measurement tables, SPICE netlist, and analysis text into a publication-ready .md document
- Supports Chinese (zh) and English (en) section headings and numbering
- Auto-formats sweep_summary tables with engineering notation (kΩ, µF, etc.)
- Can embed images as base64 data URIs for standalone .md files
- Sections: purpose, conditions, schematic, netlist, waveforms, measurements, analysis, conclusion, appendix

End-to-end workflow:
1. `build_netlist` → circuit netlist
2. `render_netlist_schematic` → schematic PNG
3. `transient_sweep` → waveform images + sweep_summary
4. `generate_markdown_report(...)` → complete .md lab report

## Conventions

- All tool functions return `ToolResponse` as a `dict` (via `.model_dump()`), with `ok: bool` and `data: {}`.
- Error codes follow pattern: `E{severity}_{CATEGORY}` (e.g., `E3_RLC_FAILED`, `E4_SIM_RUN_FAILED`).
- SI units only for component values (Ohms, Farads, Henrys).
- Enum constants are defined at module level in `com_adapter.py` with `UPPER_SNAKE_CASE`.

## Build & Run

```bash
pip install -e .          # Install in editable mode
multisim-mcp              # Run the MCP server (stdio transport)
```

## Test Quick Check

```python
python -c "import asyncio; from multisim_mcp.server import mcp; tools = asyncio.run(mcp.list_tools()); print(f'{len(tools)} tools')"
```
