"""Probe common Multisim COM methods against a running or opened design.

This is a developer diagnostic helper, not part of the MCP server runtime.
It requires Windows, pywin32, and NI Multisim with the COM Automation API.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import win32com.client


def _configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def _connect_app() -> Any:
    try:
        print("Connecting to running Multisim...", flush=True)
        app = win32com.client.GetObject(Class="MultisimInterface.MultisimApp")
        print("Connected via GetObject", flush=True)
        return app
    except Exception:
        print("GetObject failed, trying Dispatch...", flush=True)
        app = win32com.client.Dispatch("MultisimInterface.MultisimApp")
        print("Connected via Dispatch", flush=True)
        return app


def _get_circuit(app: Any, design_path: str | None) -> Any:
    print("\nTrying to get active circuit...", flush=True)
    for attr_name in ("ActiveCircuit", "Circuit"):
        try:
            circuit = getattr(app, attr_name)
            print(f"app.{attr_name} => {circuit}", flush=True)
            if circuit is not None:
                return circuit
        except Exception as exc:
            print(f"app.{attr_name} => {exc}", flush=True)

    if not design_path:
        raise RuntimeError("No active circuit found. Pass a design path to open one.")

    path = str(Path(design_path).resolve())
    print(f"Opening design: {path}", flush=True)
    circuit = app.OpenFile(path)
    print(f"OpenFile => {circuit}", flush=True)
    return circuit


def _first_success(label: str, func: Any, arg_sets: list[tuple[Any, ...]]) -> None:
    print(f"\n[{label}]", flush=True)
    for args in arg_sets:
        try:
            result = func(*args)
            text = str(result)
            print(f"  {label}{args} => OK, len={len(text)}", flush=True)
            print(f"  Content: {repr(text)[:300]}", flush=True)
            return
        except Exception as exc:
            print(f"  {label}{args} => {exc}", flush=True)
    print(f"  {label}: no signature succeeded", flush=True)


def _probe(circuit: Any, image_path: str) -> None:
    _first_success(
        "ReportBOM",
        circuit.ReportBOM,
        [(), (0,), (1,), ("",), (0, 0), (1, 0)],
    )

    _first_success(
        "ReportNetList",
        circuit.ReportNetList,
        [(), (0,), (1,), (2,), ("SPICE",), (0, 0), (0, ""), ("", 0)],
    )

    print("\n[GetCircuitImage]", flush=True)
    for label, args in [
        ("(format)", (0,)),
        ("(format=jpg)", (1,)),
        ("(format=png)", (2,)),
        ("(path, format)", (image_path, 0)),
        ("(format, path)", (0, image_path)),
        ("(path)", (image_path,)),
        ("()", ()),
    ]:
        try:
            result = circuit.GetCircuitImage(*args)
            print(
                f"  GetCircuitImage {label} => OK, "
                f"type={type(result).__name__}, value={repr(result)[:200]}",
                flush=True,
            )
            break
        except Exception as exc:
            print(f"  GetCircuitImage {label} => {exc}", flush=True)

    print("\n[EnumOutputs]", flush=True)
    for args in [(), (0,), (1,), (2,), (3,)]:
        try:
            result = circuit.EnumOutputs(*args)
            values = list(result) if result else []
            print(f"  EnumOutputs{args} => {values}", flush=True)
        except Exception as exc:
            print(f"  EnumOutputs{args} => {exc}", flush=True)


def main() -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "design_path",
        nargs="?",
        help="Optional .ms14/.ms8+ design path to open if no active circuit exists.",
    )
    parser.add_argument(
        "--image-path",
        default="multisim_probe_image.png",
        help="Output path used when probing GetCircuitImage signatures.",
    )
    parser.add_argument(
        "--disconnect",
        action="store_true",
        help="Call app.Disconnect() at the end of the probe.",
    )
    args = parser.parse_args()

    app = _connect_app()
    circuit = _get_circuit(app, args.design_path)
    print(f"\nCircuit object: {circuit}", flush=True)
    _probe(circuit, str(Path(args.image_path).resolve()))

    if args.disconnect:
        app.Disconnect()
        print("\nDisconnected.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
