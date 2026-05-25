"""
MCP Tools: SPICE analysis via DoCommandLine.

Provides run_spice — a single high-level tool that accepts an inline
SPICE netlist and nutmeg commands, handles all file I/O, execution,
waiting, log parsing, and returns structured numeric results.
"""

from __future__ import annotations

import os
import re

from ..com_adapter import MultisimCOMError
from ..session import SessionManager
from ..models import ToolResponse


def _get_short_path(long_path: str) -> str:
    """Get Windows 8.3 short path name (no spaces, no special chars).

    Falls back to the original path if the API call fails.
    """
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(512)
        result = ctypes.windll.kernel32.GetShortPathNameW(long_path, buf, 512)
        if result > 0:
            return buf.value
    except Exception:
        pass
    return long_path


def _ok(data: dict | None = None) -> dict:
    return ToolResponse(ok=True, data=data or {}).model_dump()


def _err(msg: str, code: str = "ERROR", last: str = "", recovery: str = "") -> dict:
    return ToolResponse(
        ok=False,
        error_code=code,
        error_message=msg,
        multisim_last_error=last,
        suggested_recovery=recovery,
    ).model_dump()


# ── Log parser ──────────────────────────────────────────────

_FLOAT_RE = re.compile(r"^[+-]?\d+\.?\d*[eE][+-]?\d+$|^[+-]?\d+\.?\d*$")
_CMD_BOUNDARY = re.compile(r"^User command performed\s+\(")
_TAB_HEADER_RE = re.compile(r"^Index\s+(time|frequency)\s+", re.IGNORECASE)
_TAB_ROW_RE = re.compile(r"^\d+\s+[+-]?\d")


def _parse_tabular_block(lines: list[str]) -> dict | None:
    """Try to parse a tabular sweep block from ``print`` output.

    After ``tran`` analysis, ``print $out $in`` produces::

        Index   time            $out            $in
        0       0.000000e+00    0.000000e+00    0.000000e+00
        ...

    After ``ac`` analysis, ``print $out`` produces::

        Index   frequency       $out
        0       1.000000e+01    9.999500e-01
        ...

    Rows are tab-separated and XSPICE duplicates each row (de-dup by Index).
    Returns ``{"_type": "transient"|"ac", "time"|"frequency": [...], ...}``
    or ``None`` if the block is not tabular.
    """
    # Find the header line
    header_idx = None
    for i, line in enumerate(lines):
        if _TAB_HEADER_RE.match(line.strip()):
            header_idx = i
            break
    if header_idx is None:
        return None

    # Parse header columns (skip "Index")
    header_parts = lines[header_idx].split()
    col_names = header_parts[1:]  # ["time", "$out", "$in", ...]

    # Parse data rows, de-duplicating by index
    rows: list[list[float]] = []
    seen_indices: set[int] = set()
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if _CMD_BOUNDARY.match(stripped) or stripped.startswith("Command:>"):
            break
        if not _TAB_ROW_RE.match(stripped):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        try:
            idx = int(parts[0])
        except ValueError:
            continue
        # De-duplicate (XSPICE echoes each row twice)
        if idx in seen_indices:
            continue
        seen_indices.add(idx)
        try:
            values = [float(x) for x in parts[1:]]
        except ValueError:
            continue
        rows.append(values)

    if not rows:
        return None

    # Build columnar result
    sweep_var = col_names[0].lower()  # "time" or "frequency"
    result_type = "ac" if sweep_var == "frequency" else "transient"
    result: dict = {"_type": result_type, "num_points": len(rows)}
    for j, col in enumerate(col_names):
        result[col] = [row[j] for row in rows if j < len(row)]
    return result


def _parse_log(log_text: str) -> list[dict]:
    """Extract structured results from Multisim XSPICE command log.

    Each ``print`` command in the log produces one result dict.

    - **Scalar** (after ``op``): maps vector names to single float values.
    - **Tabular** (after ``tran``): ``_type: "transient"``, ``time: [...]``,
      and vector arrays like ``$out: [...]``.
    - **Tabular** (after ``ac``): ``_type: "ac"``, ``frequency: [...]``,
      and vector arrays.

    The XSPICE log duplicates every value/row; the parser de-duplicates.
    """
    results: list[dict] = []
    blocks = re.split(r"Command:>print\s+", log_text)

    for block in blocks[1:]:
        lines = block.split("\n")
        # First line has vector names (rest of the 'print' command)
        header = lines[0].strip()
        vec_names = header.split()

        # Try tabular format first (time-series from tran/ac)
        tabular = _parse_tabular_block(lines[1:])
        if tabular is not None:
            results.append(tabular)
            continue

        # Scalar format (single values from op)
        floats: list[float] = []
        for line in lines[1:]:
            stripped = line.strip()
            if _CMD_BOUNDARY.match(stripped) or stripped.startswith("Command:>"):
                break
            if _FLOAT_RE.match(stripped):
                floats.append(float(stripped))

        # De-duplicate (XSPICE echoes every value twice)
        if len(floats) == 2 * len(vec_names):
            floats = floats[::2]

        if len(floats) == len(vec_names):
            results.append(dict(zip(vec_names, floats)))
        elif floats:
            results.append({"_vectors": vec_names, "_raw": floats})

    return results


def _collect_errors(log_text: str) -> list[str]:
    """Return genuine error lines (ignore comment-triggered Permission denied).

    Categorises: CONVERGENCE, SINGULAR_MATRIX, TIMESTEP, GENERIC.
    """
    errors = []
    for line in log_text.split("\n"):
        if "Error:" in line and "Permission denied" not in line:
            errors.append(line.strip())
    return errors


def _categorize_errors(errors: list[str]) -> dict:
    """Return error categories found in the error list."""
    cats: dict[str, list[str]] = {}
    for e in errors:
        low = e.lower()
        if "convergence" in low or "no convergence" in low:
            cats.setdefault("CONVERGENCE", []).append(e)
        elif "singular" in low:
            cats.setdefault("SINGULAR_MATRIX", []).append(e)
        elif "timestep" in low or "time step" in low:
            cats.setdefault("TIMESTEP", []).append(e)
        else:
            cats.setdefault("GENERIC", []).append(e)
    return cats


# ── Main tool ───────────────────────────────────────────────

def tool_run_spice(
    session: SessionManager,
    netlist: str,
    commands: list[str],
    timeout_ms: int = 30000,
) -> dict:
    """Run a complete SPICE simulation from inline netlist and nutmeg commands.

    Handles temp-file management, circuit creation, execution, waiting,
    and log parsing internally.  Returns structured numeric results.
    """
    # XSPICE nutmeg `source` command splits on whitespace and doesn't handle
    # special chars (& in usernames, spaces in paths).  Use a root-level
    # temp dir with a guaranteed-safe path for all SPICE temp files.
    tmp_dir = r"C:\mcp_spice_tmp"
    os.makedirs(tmp_dir, exist_ok=True)

    cir_path = os.path.join(tmp_dir, "circuit.cir")
    cmd_path = os.path.join(tmp_dir, "script.cmd")
    log_path = os.path.join(tmp_dir, "sim.log")

    try:
        # ── Pre-flight check: netlist must end with .end ────
        stripped_netlist = netlist.strip()
        if not stripped_netlist.lower().rstrip().endswith(".end"):
            return _err(
                "Netlist must end with .end directive",
                "E3_NETLIST_SYNTAX",
                recovery="Add '.end' as the last line of the netlist",
            )

        # ── Write temp files ────────────────────────────────
        # XSPICE can't handle multi-byte UTF-8 in netlists — strip non-ASCII
        safe_netlist = netlist.encode("ascii", errors="replace").decode("ascii")
        with open(cir_path, "w", encoding="ascii") as f:
            f.write(safe_netlist if safe_netlist.endswith("\n") else safe_netlist + "\n")

        # Use 8.3 short path for the source command — avoids spaces/& in paths
        cir_short = _get_short_path(cir_path).replace(os.sep, "/")
        script_lines = [f"source {cir_short}"]
        script_lines.extend(commands)
        with open(cmd_path, "w", encoding="utf-8") as f:
            f.write("\n".join(script_lines) + "\n")

        # ── Remove stale log ────────────────────────────────
        if os.path.exists(log_path):
            os.remove(log_path)

        # ── Ensure blank circuit for DoCommandLine ──────────
        try:
            session.adapter.new_file()
        except MultisimCOMError:
            pass  # Already have a circuit — fine

        # ── Execute ─────────────────────────────────────────
        session.adapter.do_command_line(cmd_path, log_path)
        wait_result = session.adapter.wait_for_next_output(timeout_ms)

        # ── Read & parse log ────────────────────────────────
        log_text = ""
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                log_text = f.read()

        parsed = _parse_log(log_text)
        errors = _collect_errors(log_text)
        error_cats = _categorize_errors(errors) if errors else None
        timed_out = wait_result.get("timed_out", False)

        session.log_action(
            "run_spice",
            {"num_commands": len(commands)},
            result_summary=f"{len(parsed)} result(s), timed_out={timed_out}",
        )

        return _ok({
            "results": parsed,
            "errors": errors or None,
            "error_categories": error_cats,
            "timed_out": timed_out,
        })

    except MultisimCOMError as exc:
        session.log_action("run_spice", {}, error=str(exc))
        return _err(
            str(exc), "E4_SPICE_FAILED", exc.last_error,
            "Check netlist syntax and nutmeg commands",
        )
    except Exception as exc:
        return _err(str(exc), "E4_SPICE_ERROR", recovery="Check netlist and commands")


# ── Parameter Sweep ─────────────────────────────────────────

def _set_value_in_netlist(netlist: str, component: str, value: float) -> str:
    """Replace the value of a component in a SPICE netlist string.

    Matches lines starting with the component name (case-insensitive) and
    replaces the last numeric token (the component value).
    """
    lines = netlist.split("\n")
    comp_upper = component.upper()
    val_re = re.compile(
        r"(?:^|\s)([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*$"
    )
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.upper().startswith(comp_upper + " "):
            # Replace the last numeric token
            m = val_re.search(stripped)
            if m:
                prefix = stripped[: m.start(1)]
                lines[i] = f"{prefix}{value}"
    return "\n".join(lines)


def tool_parameter_sweep(
    session: SessionManager,
    netlist: str,
    component: str,
    values: list[float],
    outputs: list[str],
    analysis: str = "op",
    component_2: str | None = None,
    values_2: list[float] | None = None,
) -> dict:
    """Sweep a component value across multiple points in a single SPICE call.

    Uses ``alter`` commands internally to change values between analysis
    runs, keeping everything in one XSPICE session for speed.

    For 2-D sweeps, supply *component_2* and *values_2*.  The outer loop
    is *component*/*values* and the inner loop is *component_2*/*values_2*.

    Returns a structured table of results — one row per configuration.
    """
    if not values:
        return _err("values list is empty", "E3_BAD_SWEEP")
    if not outputs:
        return _err("outputs list is empty (use e.g. ['$out'])", "E3_BAD_SWEEP")

    # Build the single-dimensional or 2-D sweep plan
    plan: list[dict] = []  # [{component: val, ...}, ...]
    if component_2 and values_2:
        for v1 in values:
            for v2 in values_2:
                plan.append({component: v1, component_2: v2})
    else:
        for v1 in values:
            plan.append({component: v1})

    # Build commands: first point uses the netlist value; rest use alter
    print_cmd = "print " + " ".join(outputs)
    modified_netlist = _set_value_in_netlist(netlist, component, plan[0][component])
    if component_2 and component_2 in plan[0]:
        modified_netlist = _set_value_in_netlist(
            modified_netlist, component_2, plan[0][component_2]
        )

    commands: list[str] = [analysis, print_cmd]

    for point in plan[1:]:
        for comp_name, comp_val in point.items():
            commands.append(f"alter {comp_name} = {comp_val}")
        commands.append(analysis)
        commands.append(print_cmd)

    # Single SPICE call for the entire sweep
    result = tool_run_spice(session, modified_netlist, commands)
    if not result["ok"]:
        return result

    parsed = result["data"].get("results", [])

    # Map results back to parameter values
    sweep_results: list[dict] = []
    num_ok = 0
    for i, point in enumerate(plan):
        row: dict = dict(point)  # copy parameter values
        if i < len(parsed):
            row["measurements"] = parsed[i]
            row["error"] = None
            num_ok += 1
        else:
            row["measurements"] = None
            row["error"] = f"No result returned for sweep point {i}"
        sweep_results.append(row)

    session.log_action(
        "parameter_sweep",
        {"component": component, "num_points": len(plan)},
        result_summary=f"{num_ok}/{len(plan)} sweep points succeeded",
    )

    return _ok({
        "sweep_results": sweep_results,
        "total_points": len(plan),
        "components_swept": [component] + ([component_2] if component_2 else []),
        "outputs_measured": outputs,
    })
