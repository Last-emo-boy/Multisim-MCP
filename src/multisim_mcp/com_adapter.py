"""
COM Adapter for NI Multisim Automation API.

Wraps all COM interactions into a clean Python interface, handling
connection lifecycle, error translation, and type conversion.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# COM constants mapping Multisim enumerations
# enum ComponentType
COMPONENT_ALL = 0
COMPONENT_ACTIVE = 1
COMPONENT_PASSIVE = 2

# enum MultisimDB
MULTISIM_MASTER_DB = 0
MULTISIM_USER_DB = 1
MULTISIM_CORPORATE_DB = 2

# enum SweepType
SWEEP_DECADE = 0
SWEEP_OCTAVE = 1
SWEEP_LINEAR = 2

# enum SimulationInterpolation
INTERPOLATION_RAW = 0
INTERPOLATION_FORCE_STEP = 1
INTERPOLATION_LINEAR = 2
INTERPOLATION_SPLINE = 3
INTERPOLATION_COERCE = 4

# enum SimulationIOType
SIMULATION_IO_ALL = 0
SIMULATION_IO_VOLTAGE = 1
SIMULATION_IO_CURRENT = 2
SIMULATION_IO_DIGITAL = 3

# enum SimulationState
SIM_STATE_STOPPED = 0
SIM_STATE_RUNNING = 1
SIM_STATE_PAUSED = 2

# enum CircuitImageFormat
IMAGE_FORMAT_BMP = 0
IMAGE_FORMAT_JPG = 1
IMAGE_FORMAT_PNG = 2

# enum ExportFormat
EXPORT_FORMAT_TEXT = 0
EXPORT_FORMAT_CSV = 1

SWEEP_TYPE_MAP = {
    "decade": SWEEP_DECADE,
    "octave": SWEEP_OCTAVE,
    "linear": SWEEP_LINEAR,
}

INTERPOLATION_MAP = {
    "raw": INTERPOLATION_RAW,
    "force_step": INTERPOLATION_FORCE_STEP,
    "linear": INTERPOLATION_LINEAR,
    "spline": INTERPOLATION_SPLINE,
    "coerce": INTERPOLATION_COERCE,
}

IMAGE_FORMAT_MAP = {
    "bmp": IMAGE_FORMAT_BMP,
    "jpg": IMAGE_FORMAT_JPG,
    "png": IMAGE_FORMAT_PNG,
}

# enum CircuitParameterLevel
CIRCUIT_PARAM_ALL = 0
CIRCUIT_PARAM_TOP_LEVEL = 1

CIRCUIT_PARAM_LEVEL_MAP = {
    "all": CIRCUIT_PARAM_ALL,
    "top_level": CIRCUIT_PARAM_TOP_LEVEL,
}


class MultisimCOMError(Exception):
    """Raised when a COM call to Multisim fails."""

    def __init__(self, message: str, last_error: str = ""):
        self.last_error = last_error
        super().__init__(message)


class MultisimCOMAdapter:
    """
    Wraps the Multisim COM Automation API.

    Manages MultisimApp and MultisimCircuit COM objects.
    All public methods translate COM exceptions into MultisimCOMError.
    """

    def __init__(self) -> None:
        self._app: Any = None
        self._circuit: Any = None

    @property
    def is_connected(self) -> bool:
        if self._app is None:
            return False
        try:
            return bool(self._app.IsConnected)
        except Exception:
            return False

    @property
    def has_circuit(self) -> bool:
        return self._circuit is not None

    # ── Connection ──────────────────────────────────────────────

    def connect(self, path: str | None = None, log_file: str | None = None) -> None:
        """Start a new Multisim instance and connect to it."""
        try:
            import win32com.client  # type: ignore[import-untyped]

            self._app = win32com.client.Dispatch("MultisimInterface.MultisimApp")

            if path:
                self._app.Path = path
            if log_file:
                self._app.LogFile = log_file

            self._app.Connect()
            if not self._app.IsConnected:
                raise MultisimCOMError("Failed to connect to Multisim")
            logger.info("Connected to Multisim: %s", self._app.VersionInfo)
        except MultisimCOMError:
            raise
        except Exception as exc:
            raise MultisimCOMError(f"COM connect failed: {exc}") from exc

    def disconnect(self) -> None:
        """Terminate the connected Multisim instance."""
        try:
            if self._app and self._app.IsConnected:
                self._app.Disconnect()
            self._circuit = None
            self._app = None
            logger.info("Disconnected from Multisim")
        except Exception as exc:
            raise MultisimCOMError(f"COM disconnect failed: {exc}") from exc

    def get_version_info(self) -> str:
        self._require_connected()
        return str(self._app.VersionInfo)

    def get_last_error(self) -> str:
        """Get last error from app or circuit level."""
        parts = []
        try:
            if self._app:
                parts.append(f"App: {self._app.LastErrorMessage}")
        except Exception:
            pass
        try:
            if self._circuit:
                parts.append(f"Circuit: {self._circuit.LastErrorMessage}")
        except Exception:
            pass
        return " | ".join(parts) if parts else ""

    # ── File Operations ─────────────────────────────────────────

    def new_file(self) -> None:
        """Create a new blank circuit."""
        self._require_connected()
        try:
            self._circuit = self._app.NewFile()
        except Exception as exc:
            raise MultisimCOMError(
                f"NewFile failed: {exc}", self.get_last_error()
            ) from exc

    def open_file(self, filename: str) -> None:
        """Open an existing .ms8+ circuit file."""
        self._require_connected()
        abs_path = os.path.abspath(filename)
        if not os.path.isfile(abs_path):
            raise MultisimCOMError(f"File not found: {abs_path}")
        try:
            self._circuit = self._app.OpenFile(abs_path)
        except Exception as exc:
            raise MultisimCOMError(
                f"OpenFile failed: {exc}", self.get_last_error()
            ) from exc

    def save(self) -> None:
        self._require_circuit()
        try:
            self._circuit.Save()
        except Exception as exc:
            raise MultisimCOMError(
                f"Save failed: {exc}", self.get_last_error()
            ) from exc

    def save_as(self, filename: str) -> None:
        self._require_circuit()
        abs_path = os.path.abspath(filename)
        try:
            self._circuit.SaveAs(abs_path)
        except Exception as exc:
            raise MultisimCOMError(
                f"SaveAs failed: {exc}", self.get_last_error()
            ) from exc

    # ── Circuit Properties ──────────────────────────────────────

    def get_circuit_name(self) -> str:
        self._require_circuit()
        return str(self._circuit.CircuitName)

    def get_file_name(self) -> str:
        self._require_circuit()
        return str(self._circuit.FileName)

    def get_simulation_state(self) -> int:
        self._require_circuit()
        return int(self._circuit.SimulationState)

    def get_active_variant(self) -> str:
        self._require_circuit()
        return str(self._circuit.ActiveVariant)

    def set_active_variant(self, variant: str) -> None:
        self._require_circuit()
        try:
            self._circuit.ActiveVariant = variant
        except Exception as exc:
            raise MultisimCOMError(
                f"SetActiveVariant failed: {exc}", self.get_last_error()
            ) from exc

    # ── Enumeration ─────────────────────────────────────────────

    def enum_components(self, filter_type: int = COMPONENT_ALL) -> list[str]:
        self._require_circuit()
        try:
            result = self._circuit.EnumComponents(filter_type)
            return list(result) if result else []
        except Exception as exc:
            raise MultisimCOMError(
                f"EnumComponents failed: {exc}", self.get_last_error()
            ) from exc

    def enum_sections(self, component_name: str) -> list[str]:
        self._require_circuit()
        try:
            result = self._circuit.EnumSections(component_name)
            return list(result) if result else []
        except Exception as exc:
            raise MultisimCOMError(
                f"EnumSections failed: {exc}", self.get_last_error()
            ) from exc

    def enum_inputs(self, io_type: int = SIMULATION_IO_ALL) -> list[str]:
        self._require_circuit()
        try:
            result = self._circuit.EnumInputs(io_type)
            return list(result) if result else []
        except Exception as exc:
            raise MultisimCOMError(
                f"EnumInputs failed: {exc}", self.get_last_error()
            ) from exc

    def enum_outputs(self, io_type: int = SIMULATION_IO_ALL) -> list[str]:
        self._require_circuit()
        try:
            result = self._circuit.EnumOutputs(io_type)
            return list(result) if result else []
        except Exception as exc:
            raise MultisimCOMError(
                f"EnumOutputs failed: {exc}", self.get_last_error()
            ) from exc

    def enum_variants(self) -> list[str]:
        self._require_circuit()
        try:
            result = self._circuit.EnumVariants()
            return list(result) if result else []
        except Exception as exc:
            raise MultisimCOMError(
                f"EnumVariants failed: {exc}", self.get_last_error()
            ) from exc

    def enum_circuit_parameters(
        self, level: int = CIRCUIT_PARAM_ALL
    ) -> list[str]:
        """Enumerate circuit parameter names.
        
        Args:
            level: CIRCUIT_PARAM_ALL (0) or CIRCUIT_PARAM_TOP_LEVEL (1)
        """
        self._require_circuit()
        try:
            result = self._circuit.EnumCircuitParameters(level)
            return list(result) if result else []
        except Exception as exc:
            raise MultisimCOMError(
                f"EnumCircuitParameters failed: {exc}", self.get_last_error()
            ) from exc

    # ── Component Modification ──────────────────────────────────

    def get_rlc_value(self, component_name: str) -> float:
        self._require_circuit()
        try:
            return float(self._circuit.RLCValue(component_name))
        except Exception as exc:
            raise MultisimCOMError(
                f"RLCValue get failed for {component_name}: {exc}",
                self.get_last_error(),
            ) from exc

    def set_rlc_value(self, component_name: str, value: float) -> None:
        self._require_circuit()
        self._require_simulation_stopped()
        try:
            # RLCValue is a *parameterized* COM property (Property Let).
            # win32com late-binding (.Dispatch) interprets .RLCValue(name, val)
            # as DISPATCH_METHOD, which fails. We must use an explicit
            # DISPATCH_PROPERTYPUT via the low-level _oleobj_.Invoke.
            import pythoncom

            dispid = self._circuit._oleobj_.GetIDsOfNames("RLCValue")[0]
            # Args order: index param first, value-to-set last.
            # win32com's Invoke auto-assigns DISPID_PROPERTYPUT to the
            # last positional arg when wFlags includes PROPERTYPUT.
            self._circuit._oleobj_.Invoke(
                dispid,
                0,  # lcid
                pythoncom.DISPATCH_PROPERTYPUT,
                0,  # bResultWanted
                component_name,
                value,
            )
        except MultisimCOMError:
            raise
        except Exception as exc:
            raise MultisimCOMError(
                f"RLCValue set failed for {component_name}: {exc}",
                self.get_last_error(),
            ) from exc

    def get_circuit_parameter_value(self, param_name: str) -> float:
        """Get a circuit parameter value by name.
        
        Supports sub-sheet syntax like 'SC1.Vin'.
        Expressions are evaluated and the result returned.
        """
        self._require_circuit()
        try:
            return float(self._circuit.CircuitParameterValue(param_name))
        except Exception as exc:
            raise MultisimCOMError(
                f"CircuitParameterValue get failed for {param_name}: {exc}",
                self.get_last_error(),
            ) from exc

    def set_circuit_parameter_value(self, param_name: str, value: float) -> None:
        """Set a circuit parameter value. Simulation must be stopped.
        
        Supports sub-sheet syntax like 'SC1.Vin'.
        """
        self._require_circuit()
        self._require_simulation_stopped()
        try:
            import pythoncom

            dispid = self._circuit._oleobj_.GetIDsOfNames(
                "CircuitParameterValue"
            )[0]
            self._circuit._oleobj_.Invoke(
                dispid,
                0,
                pythoncom.DISPATCH_PROPERTYPUT,
                0,
                param_name,
                value,
            )
        except MultisimCOMError:
            raise
        except Exception as exc:
            raise MultisimCOMError(
                f"CircuitParameterValue set failed for {param_name}: {exc}",
                self.get_last_error(),
            ) from exc

    def replace_component(
        self,
        component_name: str,
        section_name: str,
        source_database: int,
        source_group: str,
        source_family: str,
        source_name: str,
        model_name: str = "",
    ) -> str:
        self._require_circuit()
        self._require_simulation_stopped()
        try:
            new_refdes = self._circuit.ReplaceComponent(
                component_name,
                section_name,
                source_database,
                source_group,
                source_family,
                source_name,
                model_name,
            )
            return str(new_refdes)
        except Exception as exc:
            raise MultisimCOMError(
                f"ReplaceComponent failed for {component_name}: {exc}",
                self.get_last_error(),
            ) from exc

    # ── Input Data ──────────────────────────────────────────────

    def reserve_input(self, input_name: str) -> None:
        self._require_circuit()
        try:
            self._circuit.ReserveInput(input_name)
        except Exception as exc:
            raise MultisimCOMError(
                f"ReserveInput failed: {exc}", self.get_last_error()
            ) from exc

    def set_input_data_raw(
        self,
        input_name: str,
        time_values: list[float],
        data_values: list[float],
        repeat: bool = False,
    ) -> None:
        self._require_circuit()
        try:
            self._circuit.SetInputDataRaw(
                input_name, time_values, data_values, repeat
            )
        except Exception as exc:
            raise MultisimCOMError(
                f"SetInputDataRaw failed: {exc}", self.get_last_error()
            ) from exc

    def set_input_data_sampled(
        self,
        input_name: str,
        sample_rate: float,
        data_values: list[float],
        repeat: bool = False,
    ) -> None:
        self._require_circuit()
        try:
            self._circuit.SetInputDataSampled(
                input_name, sample_rate, data_values, repeat
            )
        except Exception as exc:
            raise MultisimCOMError(
                f"SetInputDataSampled failed: {exc}", self.get_last_error()
            ) from exc

    def clear_input_data(self, input_name: str) -> None:
        self._require_circuit()
        try:
            self._circuit.ClearInputData(input_name)
        except Exception as exc:
            raise MultisimCOMError(
                f"ClearInputData failed: {exc}", self.get_last_error()
            ) from exc

    # ── Output Request & Data ───────────────────────────────────

    def set_output_request(
        self,
        output_name: str,
        method: int = INTERPOLATION_RAW,
        sample_rate: float = 1000.0,
        num_samples: int = 1000,
        repeat: bool = False,
    ) -> None:
        self._require_circuit()
        try:
            self._circuit.SetOutputRequest(
                output_name, method, sample_rate, num_samples, repeat
            )
        except Exception as exc:
            raise MultisimCOMError(
                f"SetOutputRequest failed: {exc}", self.get_last_error()
            ) from exc

    def clear_output_request(self, output_name: str) -> None:
        self._require_circuit()
        try:
            self._circuit.ClearOutputRequest(output_name)
        except Exception as exc:
            raise MultisimCOMError(
                f"ClearOutputRequest failed: {exc}", self.get_last_error()
            ) from exc

    def output_ready(self, output_name: str) -> bool:
        self._require_circuit()
        try:
            return bool(self._circuit.OutputReady(output_name))
        except Exception as exc:
            raise MultisimCOMError(
                f"OutputReady failed: {exc}", self.get_last_error()
            ) from exc

    def get_output_data(
        self, output_name: str
    ) -> dict[str, list[float]]:
        """
        Retrieve output data. Returns dict with keys:
        - time_or_freq: x-axis values
        - real: real part of y values
        - imaginary: imaginary part (frequency domain; zeros for time domain)
        - interpolation_method: int code of method used
        """
        self._require_circuit()
        try:
            # GetOutputData signature:
            #   Sub GetOutputData(ByVal outputName, ByRef dataArray, ByRef method)
            # In win32com, ByRef out-params are *returned* as a tuple.
            # We pass placeholder values for the two ByRef params;
            # win32com returns (dataArray, method) as a tuple.
            result = self._circuit.GetOutputData(output_name, None, 0)

            # Unpack ByRef return values
            if isinstance(result, tuple):
                data_array, method_out = result[0], int(result[1])
            else:
                # Fallback: some COM wrappers return only the first ByRef
                data_array = result
                method_out = INTERPOLATION_RAW

            # COM returns a 2D SAFEARRAY: (0,n)=time/freq, (1,n)=real, (2,n)=imag
            time_or_freq: list[float] = []
            real_part: list[float] = []
            imag_part: list[float] = []
            if data_array is not None:
                for i in range(len(data_array[0])):
                    time_or_freq.append(float(data_array[0][i]))
                    real_part.append(float(data_array[1][i]))
                    imag_part.append(float(data_array[2][i]))

            return {
                "time_or_freq": time_or_freq,
                "real": real_part,
                "imaginary": imag_part,
                "interpolation_method": method_out,
            }
        except MultisimCOMError:
            raise
        except Exception as exc:
            raise MultisimCOMError(
                f"GetOutputData failed: {exc}", self.get_last_error()
            ) from exc

    # ── Simulation Control ──────────────────────────────────────

    def run_simulation(self) -> None:
        self._require_circuit()
        try:
            self._circuit.RunSimulation()
        except Exception as exc:
            raise MultisimCOMError(
                f"RunSimulation failed: {exc}", self.get_last_error()
            ) from exc

    def pause_simulation(self) -> None:
        self._require_circuit()
        try:
            self._circuit.PauseSimulation()
        except Exception as exc:
            raise MultisimCOMError(
                f"PauseSimulation failed: {exc}", self.get_last_error()
            ) from exc

    def resume_simulation(self) -> None:
        self._require_circuit()
        try:
            self._circuit.ResumeSimulation()
        except Exception as exc:
            raise MultisimCOMError(
                f"ResumeSimulation failed: {exc}", self.get_last_error()
            ) from exc

    def stop_simulation(self) -> None:
        self._require_circuit()
        try:
            self._circuit.StopSimulation()
        except Exception as exc:
            raise MultisimCOMError(
                f"StopSimulation failed: {exc}", self.get_last_error()
            ) from exc

    def run_simulation_until_next_output(self) -> None:
        self._require_circuit()
        try:
            self._circuit.RunSimulationUntilNextOutput()
        except Exception as exc:
            raise MultisimCOMError(
                f"RunSimulationUntilNextOutput failed: {exc}",
                self.get_last_error(),
            ) from exc

    def wait_for_next_output(self, wait_time_ms: int = 10000) -> dict:
        """Wait until the next output request is ready or simulation ends.

        Args:
            wait_time_ms: Milliseconds to wait before timing out.

        Returns:
            dict with 'timed_out' (bool) and 'output_names' (list[str]).
        """
        self._require_circuit()
        try:
            # API: WaitForNextOutput(ByRef bTimedOut As Boolean, ByVal nWaitTime As int32) As Variant
            # ByRef bTimedOut comes back as extra tuple element
            result = self._circuit.WaitForNextOutput(wait_time_ms)
            # Late-binding: ByRef bool returned as second element
            if isinstance(result, tuple) and len(result) >= 2:
                output_names = result[0]
                timed_out = bool(result[1])
            else:
                output_names = result
                timed_out = False
            # Normalise output_names
            if output_names is None:
                names_list: list[str] = []
            elif isinstance(output_names, str):
                names_list = [output_names] if output_names else []
            else:
                names_list = [str(n) for n in output_names]
            return {"timed_out": timed_out, "output_names": names_list}
        except Exception as exc:
            raise MultisimCOMError(
                f"WaitForNextOutput failed: {exc}", self.get_last_error()
            ) from exc

    # ── Analysis ────────────────────────────────────────────────

    def do_ac_sweep(
        self,
        sweep_type: int,
        num_points: int,
        start_frequency: float,
        stop_frequency: float,
        output_names: list[str],
    ) -> None:
        self._require_circuit()
        try:
            self._circuit.DoACSweep(
                sweep_type, num_points, start_frequency, stop_frequency, output_names
            )
        except Exception as exc:
            raise MultisimCOMError(
                f"DoACSweep failed: {exc}", self.get_last_error()
            ) from exc

    def do_dc_operating_point(self, output_names: list[str]) -> None:
        self._require_circuit()
        try:
            self._circuit.DoDCOperatingPoint(output_names)
        except Exception as exc:
            raise MultisimCOMError(
                f"DoDCOperatingPoint failed: {exc}", self.get_last_error()
            ) from exc

    def do_ac_single_frequency(
        self, frequency: float, output_names: list[str]
    ) -> None:
        """Run AC analysis at a single frequency. Async — use GetOutputData."""
        self._require_circuit()
        try:
            self._circuit.DoACSingleFrequency(frequency, output_names)
        except Exception as exc:
            raise MultisimCOMError(
                f"DoACSingleFrequency failed: {exc}", self.get_last_error()
            ) from exc

    def do_command_line(self, command_file: str, log_file: str) -> None:
        self._require_circuit()
        try:
            self._circuit.DoCommandLine(command_file, log_file)
        except Exception as exc:
            raise MultisimCOMError(
                f"DoCommandLine failed: {exc}", self.get_last_error()
            ) from exc

    # ── Reports & Export ────────────────────────────────────────

    def report_netlist(
        self,
        probes_flag: bool = False,
        format_type: int = EXPORT_FORMAT_TEXT,
        file_name: str = "",
    ) -> str:
        """Create a netlist report.

        Args:
            probes_flag: If True, include probes in the report.
            format_type: EXPORT_FORMAT_TEXT (0) or EXPORT_FORMAT_CSV (1).
            file_name: If provided, save to file; otherwise return as string.
        """
        self._require_circuit()
        try:
            return str(self._circuit.ReportNetList(probes_flag, format_type, file_name))
        except Exception as exc:
            raise MultisimCOMError(
                f"ReportNetList failed: {exc}", self.get_last_error()
            ) from exc

    def report_bom(
        self,
        real_flag: bool = False,
        format_type: int = EXPORT_FORMAT_TEXT,
        file_name: str = "",
    ) -> str:
        """Create a Bill of Materials report.

        Args:
            real_flag: If True, only real components; if False, virtual components.
            format_type: EXPORT_FORMAT_TEXT (0) or EXPORT_FORMAT_CSV (1).
            file_name: If provided, save to file; otherwise return as string.
        """
        self._require_circuit()
        try:
            return str(self._circuit.ReportBOM(real_flag, format_type, file_name))
        except Exception as exc:
            raise MultisimCOMError(
                f"ReportBOM failed: {exc}", self.get_last_error()
            ) from exc

    def get_circuit_image(
        self, filename: str, image_format: int = IMAGE_FORMAT_PNG
    ) -> str:
        """Take a screen capture of the current circuit.

        Args:
            filename: Path to save the image file.
            image_format: IMAGE_FORMAT_BMP (0), IMAGE_FORMAT_JPG (1), IMAGE_FORMAT_PNG (2).

        Returns:
            Fully-qualified path of the saved image file.
        """
        self._require_circuit()
        abs_path = os.path.abspath(filename)
        try:
            # API signature: GetCircuitImage(imageFormat, FileName) -> String
            result = self._circuit.GetCircuitImage(image_format, abs_path)
            return str(result) if result else abs_path
        except Exception as exc:
            raise MultisimCOMError(
                f"GetCircuitImage failed: {exc}", self.get_last_error()
            ) from exc

    def create_snippet(
        self, filename: str, selection_only: bool = False, zoom_factor: float = 1.0
    ) -> str:
        """Create a PNG snippet of the current circuit sheet.
        
        Note: selectionOnlyFlag is ignored by the API (always captures whole sheet).
        Extension is always forced to .png.
        """
        self._require_circuit()
        abs_path = os.path.abspath(filename)
        try:
            result = self._circuit.CreateSnippet(abs_path, selection_only, zoom_factor)
            return str(result)
        except Exception as exc:
            raise MultisimCOMError(
                f"CreateSnippet failed: {exc}", self.get_last_error()
            ) from exc

    def save_design_as_snippet(
        self, filename: str, zoom_factor: float = 1.0
    ) -> str:
        """Save entire design (excluding hierarchical blocks) as a PNG snippet.
        
        Extension is always forced to .png.
        """
        self._require_circuit()
        abs_path = os.path.abspath(filename)
        try:
            result = self._circuit.SaveDesignAsSnippet(abs_path, zoom_factor)
            return str(result)
        except Exception as exc:
            raise MultisimCOMError(
                f"SaveDesignAsSnippet failed: {exc}", self.get_last_error()
            ) from exc

    # ── Internal Helpers ────────────────────────────────────────

    def _require_connected(self) -> None:
        if not self.is_connected:
            raise MultisimCOMError("Not connected to Multisim. Call connect() first.")

    def _require_circuit(self) -> None:
        self._require_connected()
        if self._circuit is None:
            raise MultisimCOMError("No circuit open. Open a file first.")

    def _require_simulation_stopped(self) -> None:
        state = self.get_simulation_state()
        if state != SIM_STATE_STOPPED:
            raise MultisimCOMError(
                f"Simulation must be stopped (current state: {state}). "
                "Call stop_simulation() first."
            )
