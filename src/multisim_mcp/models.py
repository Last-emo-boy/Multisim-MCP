"""
Pydantic data models for Multisim MCP tool inputs and outputs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Common Response ─────────────────────────────────────────

class ToolResponse(BaseModel):
    ok: bool = True
    error_code: str = ""
    error_message: str = ""
    multisim_last_error: str = ""
    suggested_recovery: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


# ── File & Session ──────────────────────────────────────────

class OpenDesignInput(BaseModel):
    path: str = Field(..., description="Absolute path to .ms14/.ms8+ design file")

class OpenNetlistInput(BaseModel):
    path: str = Field(..., description="Absolute path to .cir/.txt netlist file")

class SaveDesignAsInput(BaseModel):
    path: str = Field(..., description="Destination file path for SaveAs")

class ExportCircuitImageInput(BaseModel):
    path: str = Field(..., description="Output image file path")
    format: str = Field("png", description="Image format: bmp, jpg, png")


# ── Enumeration ─────────────────────────────────────────────

class ListComponentsInput(BaseModel):
    filter: str = Field("all", description="Filter: all, active, passive")

class ListSectionsInput(BaseModel):
    component_refdes: str = Field(..., description="Component RefDes, e.g. U1")

class ListIOInput(BaseModel):
    io_type: str = Field("all", description="Filter: all, voltage, current, digital")


# ── Component Modification ──────────────────────────────────

class SetRLCValueInput(BaseModel):
    refdes: str = Field(..., description="Component RefDes, e.g. R1, C2, L1")
    value: float = Field(
        ...,
        description="Value in base SI units (ohms/farads/henrys). E.g. 1000 for 1kΩ, 1e-9 for 1nF",
    )

class ReplaceComponentInput(BaseModel):
    refdes: str = Field(..., description="RefDes of component to replace, e.g. D1")
    section: str = Field("", description="Section name for multi-section parts, or empty")
    database: str = Field("master", description="Database: master, user, corporate")
    group: str = Field(..., description="Database group, e.g. Diodes, Analog, Sources")
    family: str = Field(..., description="Database family, e.g. DIODE, OPAMP")
    name: str = Field(..., description="Component name, e.g. 1N5712, MC1458SU")
    model: str = Field("", description="Model name (empty for default)")


# ── Input Data ──────────────────────────────────────────────

class SetInputDataRawInput(BaseModel):
    input_name: str = Field(..., description="Input source name from list_inputs")
    time_values: list[float] = Field(..., description="Array of time points (seconds)")
    data_values: list[float] = Field(..., description="Array of corresponding data values")
    repeat: bool = Field(False, description="Whether to repeat the waveform")

class SetInputDataSampledInput(BaseModel):
    input_name: str = Field(..., description="Input source name from list_inputs")
    sample_rate: float = Field(..., description="Sampling rate in samples/second")
    data_values: list[float] = Field(..., description="Array of evenly-sampled data values")
    repeat: bool = Field(False, description="Whether to repeat the waveform")

class ClearInputInput(BaseModel):
    input_name: str = Field(..., description="Input source name to clear")


# ── Output Request ──────────────────────────────────────────

class SetOutputRequestInput(BaseModel):
    output_name: str = Field(..., description="Probe name from list_outputs")
    interpolation: str = Field(
        "raw",
        description="Interpolation: raw, force_step, linear, spline, coerce",
    )
    sample_rate: float = Field(1000.0, description="Sample rate (samples/sec)")
    num_samples: int = Field(1000, description="Number of data points")
    repeat: bool = Field(False, description="Repeat output collection")

class GetOutputDataInput(BaseModel):
    output_name: str = Field(..., description="Probe name to retrieve data from")

class IsOutputReadyInput(BaseModel):
    output_name: str = Field(..., description="Probe name to check readiness")


# ── Simulation ──────────────────────────────────────────────

class ACSweepConfigInput(BaseModel):
    sweep_type: str = Field("decade", description="Sweep type: decade, octave, linear")
    num_points: int = Field(100, description="Points (per decade/octave, or total for linear)")
    start_frequency: float = Field(1.0, description="Start frequency in Hz")
    stop_frequency: float = Field(1e6, description="Stop frequency in Hz")
    output_names: list[str] = Field(
        ..., description="List of output probe names to collect"
    )

class DCOperatingPointInput(BaseModel):
    output_names: list[str] = Field(
        ..., description="List of output probe names to collect"
    )

class TransientConfigInput(BaseModel):
    stop_time: float = Field(..., description="Simulation stop time in seconds")
    output_names: list[str] = Field(
        ..., description="List of output probe names to collect"
    )
    sample_rate: float = Field(10000.0, description="Output sample rate")
    num_samples: int = Field(0, description="Number of samples (0 = auto from stop_time * sample_rate)")
    interpolation: str = Field("raw", description="Interpolation method")

class CommandLineInput(BaseModel):
    command_file: str = Field(..., description="Path to SPICE netlist command file")
    log_file: str = Field(..., description="Path for simulation log output")


# ── Export ──────────────────────────────────────────────────

class ExportNetlistInput(BaseModel):
    path: str = Field("", description="File path to save netlist (empty returns inline)")
    format: str = Field("spice", description="Format: spice, expanded_spice")

class ExportBOMInput(BaseModel):
    path: str = Field("", description="File path to save BOM (empty returns inline)")
