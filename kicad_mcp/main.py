import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - exercised when the runtime lacks the optional MCP SDK
    class FastMCP:  # type: ignore[override]
        """Fallback implementation used when the MCP SDK is unavailable in the environment."""

        def __init__(self, name: str, instructions: str = "") -> None:
            self.name = name
            self.instructions = instructions

        def tool(self):
            def decorator(func):
                return func

            return decorator

        def run(self, transport: str = "stdio") -> None:
            return None


mcp = FastMCP("kicad-erc-server", instructions="Run KiCad schematic ERC checks and schematic exports through kicad-cli and return structured results.")

SUPPORTED_SCHEMATIC_EXTENSIONS = {".kicad_sch", ".sch"}
SUPPORTED_BOARD_EXTENSIONS = {".kicad_pcb"}


def _write_text_file(path: Path, content: str) -> None:
    # Write a text file to disk while creating parent directories as needed.
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"File already exists: {path}")
    path.write_text(content, encoding="utf-8")


def validate_schematic_path(path: str) -> str:
    # Validate that the supplied path points to a KiCad schematic file.
    """Validate that the provided path points to an existing KiCad schematic file."""
    candidate = Path(path).expanduser().resolve()

    if not candidate.exists():
        raise ValueError(f"Schematic file does not exist: {path}")
    if not candidate.is_file():
        raise ValueError(f"Path is not a file: {path}")
    if candidate.suffix.lower() not in SUPPORTED_SCHEMATIC_EXTENSIONS:
        raise ValueError(
            "Unsupported schematic format. Expected a .kicad_sch or .sch file."
        )

    try:
        contents = candidate.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"Unable to read schematic file: {exc}") from exc

    lowered = contents.lower()
    if "kicad_sch" not in lowered and "eeschema" not in lowered:
        raise ValueError(
            "Unsupported schematic format. File contents do not appear to be a KiCad schematic."
        )

    return str(candidate)


def validate_board_path(path: str) -> str:
    # Validate that the supplied path points to a KiCad PCB file.
    candidate = Path(path).expanduser().resolve()

    if not candidate.exists():
        raise ValueError(f"PCB file does not exist: {path}")
    if not candidate.is_file():
        raise ValueError(f"Path is not a file: {path}")
    if candidate.suffix.lower() not in SUPPORTED_BOARD_EXTENSIONS:
        raise ValueError(
            "Unsupported board format. Expected a .kicad_pcb file."
        )

    try:
        contents = candidate.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"Unable to read PCB file: {exc}") from exc

    lowered = contents.lower()
    if "kicad_pcb" not in lowered:
        raise ValueError(
            "Unsupported board format. File contents do not appear to be a KiCad PCB."
        )

    return str(candidate)


def _resolve_kicad_cli_executable() -> str:
    # Resolve the KiCad CLI executable from PATH or the default macOS install path.
    executable = shutil.which("kicad-cli") or shutil.which("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    if not executable:
        raise RuntimeError("kicad-cli was not found on PATH or the default macOS installation path")
    return executable


def _coerce_violation_list(payload: Any, key: str) -> List[Dict[str, Any]]:
    # Coerce a violation list into a normalized dictionary structure.
    if isinstance(payload, dict):
        items = payload.get(key, [])
    else:
        items = []

    if not isinstance(items, list):
        items = [items] if items else []

    normalized: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(dict(item))
        else:
            normalized.append({"message": str(item)})
    return normalized


def normalize_erc_report(report: Union[str, bytes, Dict[str, Any], List[Any]]) -> Dict[str, Any]:
    # Normalize KiCad ERC output into a consistent structured response.
    """Normalize ERC output from kicad-cli into structured JSON for the model."""
    if isinstance(report, bytes):
        report_text = report.decode("utf-8", errors="replace")
        report_data: Any = report_text
    elif isinstance(report, str):
        report_data = report
    elif isinstance(report, (list, dict)):
        report_data = report
    else:
        report_data = str(report)

    if isinstance(report_data, dict):
        if "sheets" in report_data and isinstance(report_data.get("sheets"), list):
            errors: List[Dict[str, Any]] = []
            warnings: List[Dict[str, Any]] = []
            for sheet in report_data.get("sheets", []):
                if not isinstance(sheet, dict):
                    continue
                for violation in sheet.get("violations", []):
                    if not isinstance(violation, dict):
                        continue
                    entry = dict(violation)
                    entry.setdefault("sheet", sheet.get("path", ""))
                    if entry.get("severity") == "error":
                        errors.append(entry)
                    else:
                        warnings.append(entry)
            extras = {k: v for k, v in report_data.items() if k != "sheets"}
            return {
                "success": True,
                "format": "json",
                "violation_count": len(errors) + len(warnings),
                "errors": errors,
                "warnings": warnings,
                "summary": {
                    "by_severity": {
                        "error": len(errors),
                        "warning": len(warnings),
                    },
                    "extra_fields": extras,
                },
            }

        errors = _coerce_violation_list(report_data, "errors")
        warnings = _coerce_violation_list(report_data, "warnings")
        extras = {k: v for k, v in report_data.items() if k not in {"errors", "warnings"}}
        return {
            "success": True,
            "format": "json",
            "violation_count": len(errors) + len(warnings),
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "by_severity": {
                    "error": len(errors),
                    "warning": len(warnings),
                },
                "extra_fields": extras,
            },
        }

    if isinstance(report_data, str):
        lines = [line.strip() for line in report_data.splitlines() if line.strip()]
        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        for line in lines:
            if line.lower().startswith("error"):
                errors.append({"message": line})
            elif line.lower().startswith("warning"):
                warnings.append({"message": line})
            else:
                warnings.append({"message": line})
        return {
            "success": True,
            "format": "text",
            "violation_count": len(errors) + len(warnings),
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "by_severity": {
                    "error": len(errors),
                    "warning": len(warnings),
                },
                "extra_fields": {},
            },
        }

    return {
        "success": True,
        "format": "unknown",
        "violation_count": 0,
        "errors": [],
        "warnings": [],
        "summary": {
            "by_severity": {
                "error": 0,
                "warning": 0,
            },
            "extra_fields": {},
        },
    }


@mcp.tool()
def create_project(project_name: str, project_dir: Optional[str] = None) -> Dict[str, Any]:
    # Create a new KiCad project skeleton with empty schematic, PCB, and library files.
    """Create a new KiCad project directory with the standard empty schematic and PCB files."""
    if not project_name or not project_name.strip():
        raise ValueError("project_name must not be empty")

    normalized_name = project_name.strip()
    invalid_chars = {"/", "\\", ":", "*", "?", '"', "<", ">", "|"}
    if any(char in invalid_chars for char in normalized_name):
        raise ValueError("project_name contains unsupported path characters")

    target_dir = Path(project_dir).expanduser().resolve() if project_dir else Path.cwd().resolve()
    if target_dir.exists() and not target_dir.is_dir():
        raise ValueError(f"project_dir must be a directory: {target_dir}")

    target_dir.mkdir(parents=True, exist_ok=True)

    created_directories: List[str] = []
    for directory in [target_dir / "libraries", target_dir / "libraries" / "footprints", target_dir / "libraries" / "3D"]:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
        created_directories.append(str(directory))

    created_files: List[str] = []
    project_file = target_dir / f"{normalized_name}.kicad_pro"
    schematic_file = target_dir / f"{normalized_name}.kicad_sch"
    pcb_file = target_dir / f"{normalized_name}.kicad_pcb"
    symbol_library_file = target_dir / "libraries" / f"{normalized_name}.kicad_sym"
    symbol_table_file = target_dir / "sym-lib-table"
    footprint_table_file = target_dir / "fp-lib-table"

    project_content = {
        "meta": {
            "filename": f"{normalized_name}.kicad_pro",
            "version": 1,
        },
        "general": {
            "name": normalized_name,
            "description": "Generated by the KiCad MCP server",
        },
        "files": [
            {"name": f"{normalized_name}.kicad_sch", "type": "schematic", "path": f"{normalized_name}.kicad_sch"},
            {"name": f"{normalized_name}.kicad_pcb", "type": "board", "path": f"{normalized_name}.kicad_pcb"},
        ],
    }

    for path, content in [
        (project_file, json.dumps(project_content, indent=2) + "\n"),
        (schematic_file, "(kicad_sch (version 20211123) (generator eeschema))\n"),
        (pcb_file, "(kicad_pcb (version 20211014) (generator pcbnew))\n"),
        (symbol_library_file, "(kicad_symbol_lib (version 20211014) (generator kicad_symbol_editor))\n"),
        (
            symbol_table_file,
            f"(sym_lib_table\n  (version 7)\n  (lib (name {normalized_name})(type \"KiCad\")(uri \"${{KIPRJMOD}}/libraries/{normalized_name}.kicad_sym\")(options \"\")(descr \"\"))\n)\n",
        ),
        (
            footprint_table_file,
            f"(fp_lib_table\n  (version 7)\n  (lib (name {normalized_name})(type \"KiCad\")(uri \"${{KIPRJMOD}}/libraries/footprints\")(options \"\")(descr \"\"))\n)\n",
        ),
    ]:
        _write_text_file(path, content)
        created_files.append(str(path))

    return {
        "success": True,
        "project_name": normalized_name,
        "project_dir": str(target_dir),
        "created_directories": created_directories,
        "created_files": created_files,
        "command": f"create_project(project_name={normalized_name!r}, project_dir={str(target_dir)!r})",
    }


def export_schematic(
    schematic_path: str,
    export_type: str,
    output_path: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    # Export a schematic artifact through the KiCad CLI.
    """Export schematic artifacts via KiCad CLI."""
    validated_path = validate_schematic_path(schematic_path)

    supported_exports = {"bom", "netlist", "pdf", "dxf", "svg"}
    if export_type not in supported_exports:
        raise ValueError(f"export_type must be one of: {', '.join(sorted(supported_exports))}")

    executable = _resolve_kicad_cli_executable()

    output_target = Path(output_path).expanduser().resolve() if output_path else None
    if output_target is not None:
        output_target.parent.mkdir(parents=True, exist_ok=True)

    command = [executable, "sch", "export", export_type, validated_path]
    if output_target is not None:
        command.extend(["--output", str(output_target)])

    for key, value in kwargs.items():
        if value is None or value is False:
            continue
        if isinstance(value, bool):
            if value:
                command.append(f"--{key}")
        else:
            command.extend([f"--{key}", str(value)])

    try:
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode not in {0, 5}:
            stderr_output = completed.stderr.strip()
            raise RuntimeError(f"kicad-cli failed: {stderr_output or completed.stdout.strip()}")

        return {
            "success": True,
            "export_type": export_type,
            "schematic_path": validated_path,
            "output_path": str(output_target) if output_target is not None else None,
            "command": " ".join(command),
            "exit_code": completed.returncode,
        }
    except Exception as exc:
        raise RuntimeError(f"Failed to export schematic {export_type}: {exc}") from exc


def export_board(
    board_path: str,
    export_type: str,
    output_path: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    # Export a board artifact through the KiCad CLI.
    validated_path = validate_board_path(board_path)

    supported_exports = {"pdf", "gerber", "drill", "3d-pdf", "3d_pdf"}
    if export_type not in supported_exports:
        raise ValueError(f"export_type must be one of: {', '.join(sorted(supported_exports))}")

    executable = _resolve_kicad_cli_executable()

    board_export_type = "3d-pdf" if export_type == "3d_pdf" else export_type
    output_target = Path(output_path).expanduser().resolve() if output_path else None
    if output_target is not None:
        output_target.parent.mkdir(parents=True, exist_ok=True)

    command = [executable, "pcb", "export", board_export_type, validated_path]
    if output_target is not None:
        command.extend(["--output", str(output_target)])

    for key, value in kwargs.items():
        if value is None or value is False:
            continue
        if isinstance(value, bool):
            if value:
                command.append(f"--{key}")
        else:
            command.extend([f"--{key}", str(value)])

    try:
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            stderr_output = completed.stderr.strip()
            raise RuntimeError(f"kicad-cli failed: {stderr_output or completed.stdout.strip()}")

        return {
            "success": True,
            "export_type": export_type,
            "board_path": validated_path,
            "output_path": str(output_target) if output_target is not None else None,
            "command": " ".join(command),
            "exit_code": completed.returncode,
        }
    except Exception as exc:
        raise RuntimeError(f"Failed to export board {export_type}: {exc}") from exc


@mcp.tool()
def run_erc(
    schematic_path: str,
    format: str = "json",
    severity_all: bool = False,
    severity_error: bool = False,
    severity_warning: bool = False,
    severity_exclusions: bool = False,
) -> Dict[str, Any]:
    # Run an ERC check and return normalized findings.
    """Run KiCad ERC on a schematic and return normalized structured results."""
    validated_path = validate_schematic_path(schematic_path)

    if format not in {"json", "report"}:
        raise ValueError("format must be either 'json' or 'report'")

    executable = _resolve_kicad_cli_executable()

    with tempfile.NamedTemporaryFile(suffix=".json" if format == "json" else ".rpt", delete=False) as handle:
        report_path = handle.name

    command = [executable, "sch", "erc", "--format", format, "--output", report_path, validated_path]
    if severity_all:
        command.append("--severity-all")
    if severity_error:
        command.append("--severity-error")
    if severity_warning:
        command.append("--severity-warning")
    if severity_exclusions:
        command.append("--severity-exclusions")

    try:
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode not in {0, 5}:
            stderr_output = completed.stderr.strip()
            raise RuntimeError(f"kicad-cli failed: {stderr_output or completed.stdout.strip()}")

        if Path(report_path).exists():
            report_content = Path(report_path).read_text(encoding="utf-8", errors="replace")
            if format == "json" and report_content:
                try:
                    payload = json.loads(report_content)
                except json.JSONDecodeError:
                    payload = report_content
            else:
                payload = report_content
        else:
            payload = completed.stdout.strip()

        normalized = normalize_erc_report(payload)
        normalized.update(
            {
                "schematic_path": validated_path,
                "command": " ".join(command),
                "exit_code": completed.returncode,
                "report_path": report_path,
            }
        )
        return normalized
    finally:
        if os.path.exists(report_path):
            os.remove(report_path)


@mcp.tool()
def export_bom(
    schematic_path: str,
    output_path: Optional[str] = None,
    variant: Optional[str] = None,
    preset: Optional[str] = None,
    format_preset: Optional[str] = None,
    fields: Optional[str] = None,
    labels: Optional[str] = None,
    group_by: Optional[str] = None,
    sort_field: Optional[str] = None,
    sort_asc: bool = False,
    filter: Optional[str] = None,
    exclude_dnp: bool = False,
    field_delimiter: Optional[str] = None,
    string_delimiter: Optional[str] = None,
    ref_delimiter: Optional[str] = None,
    ref_range_delimiter: Optional[str] = None,
    keep_tabs: bool = False,
    keep_line_breaks: bool = False,
) -> Dict[str, Any]:
    # Export a BOM from a schematic with optional formatting controls.
    """Export a bill of materials from a schematic using kicad-cli."""
    return export_schematic(
        schematic_path,
        export_type="bom",
        output_path=output_path,
        variant=variant,
        preset=preset,
        format_preset=format_preset,
        fields=fields,
        labels=labels,
        group_by=group_by,
        sort_field=sort_field,
        sort_asc=sort_asc,
        filter=filter,
        exclude_dnp=exclude_dnp,
        field_delimiter=field_delimiter,
        string_delimiter=string_delimiter,
        ref_delimiter=ref_delimiter,
        ref_range_delimiter=ref_range_delimiter,
        keep_tabs=keep_tabs,
        keep_line_breaks=keep_line_breaks,
    )


@mcp.tool()
def export_netlist(
    schematic_path: str,
    output_path: Optional[str] = None,
    format: Optional[str] = None,
    variant: Optional[str] = None,
) -> Dict[str, Any]:
    # Export a netlist from a schematic in the requested format.
    """Export a netlist from a schematic using kicad-cli."""
    return export_schematic(
        schematic_path,
        export_type="netlist",
        output_path=output_path,
        format=format,
        variant=variant,
    )


@mcp.tool()
def export_pdf(
    schematic_path: str,
    output_path: Optional[str] = None,
    drawing_sheet: Optional[str] = None,
    variant: Optional[str] = None,
    theme: Optional[str] = None,
    black_and_white: bool = False,
    exclude_drawing_sheet: bool = False,
    default_font: Optional[str] = None,
    draw_hop_over: bool = False,
    exclude_pdf_property_popups: bool = False,
    exclude_pdf_hierarchical_links: bool = False,
    exclude_pdf_metadata: bool = False,
    no_background_color: bool = False,
    pages: Optional[str] = None,
) -> Dict[str, Any]:
    # Export a schematic as a PDF document.
    """Export a schematic to PDF using kicad-cli."""
    return export_schematic(
        schematic_path,
        export_type="pdf",
        output_path=output_path,
        drawing_sheet=drawing_sheet,
        variant=variant,
        theme=theme,
        black_and_white=black_and_white,
        exclude_drawing_sheet=exclude_drawing_sheet,
        default_font=default_font,
        draw_hop_over=draw_hop_over,
        exclude_pdf_property_popups=exclude_pdf_property_popups,
        exclude_pdf_hierarchical_links=exclude_pdf_hierarchical_links,
        exclude_pdf_metadata=exclude_pdf_metadata,
        no_background_color=no_background_color,
        pages=pages,
    )


@mcp.tool()
def export_svg(
    schematic_path: str,
    output_path: Optional[str] = None,
    drawing_sheet: Optional[str] = None,
    variant: Optional[str] = None,
    theme: Optional[str] = None,
    black_and_white: bool = False,
    exclude_drawing_sheet: bool = False,
    default_font: Optional[str] = None,
    draw_hop_over: bool = False,
    no_background_color: bool = False,
    pages: Optional[str] = None,
) -> Dict[str, Any]:
    # Export a schematic as an SVG image.
    """Export a schematic to SVG using kicad-cli."""
    return export_schematic(
        schematic_path,
        export_type="svg",
        output_path=output_path,
        drawing_sheet=drawing_sheet,
        variant=variant,
        theme=theme,
        black_and_white=black_and_white,
        exclude_drawing_sheet=exclude_drawing_sheet,
        default_font=default_font,
        draw_hop_over=draw_hop_over,
        no_background_color=no_background_color,
        pages=pages,
    )


@mcp.tool()
def export_dxf(
    schematic_path: str,
    output_path: Optional[str] = None,
    drawing_sheet: Optional[str] = None,
    variant: Optional[str] = None,
    theme: Optional[str] = None,
    black_and_white: bool = False,
    exclude_drawing_sheet: bool = False,
    default_font: Optional[str] = None,
    draw_hop_over: bool = False,
    pages: Optional[str] = None,
) -> Dict[str, Any]:
    # Export a schematic as a DXF drawing.
    """Export a schematic to DXF using kicad-cli."""
    return export_schematic(
        schematic_path,
        export_type="dxf",
        output_path=output_path,
        drawing_sheet=drawing_sheet,
        variant=variant,
        theme=theme,
        black_and_white=black_and_white,
        exclude_drawing_sheet=exclude_drawing_sheet,
        default_font=default_font,
        draw_hop_over=draw_hop_over,
        pages=pages,
    )


@mcp.tool()
def export_pcb_pdf(
    pcb_path: str,
    output_path: Optional[str] = None,
    layers: str = "F.Cu",
    **kwargs: Any,
) -> Dict[str, Any]:
    # Export a PCB board as a PDF document.
    """Export a PCB board to PDF using kicad-cli.

    Args:
        pcb_path: Path to the KiCad PCB file.
        output_path: Destination PDF file path (optional).
        layers: Comma‑separated list of layer names to export. At least one layer is required.
                Canonical names like ``F.Cu`` or custom layer names may be used.
                User‑defined layer names are matched first.
    """
    # Ensure a non‑empty layer list is provided
    if not layers or not layers.strip():
        raise ValueError("layers argument must be a non‑empty comma‑separated list of layer names.")

    # Guidance for agents: if unsure which layers to export, ask the user or default to exporting the front copper layer.
    # (Agents can inspect this docstring for instructions.)
    return export_board(
        pcb_path,
        export_type="pdf",
        output_path=output_path,
        layers=layers,
        **kwargs,
    )


@mcp.tool()
def export_pcb_gerber(
    pcb_path: str,
    output_path: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    # Export Gerber files from a PCB board.
    """Export PCB Gerber files using kicad-cli."""
    return export_board(
        pcb_path,
        export_type="gerber",
        output_path=output_path,
        **kwargs,
    )


@mcp.tool()
def export_pcb_drill(
    pcb_path: str,
    output_path: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    # Export Excellon drill files from a PCB board.
    """Export PCB drill files using kicad-cli."""
    return export_board(
        pcb_path,
        export_type="drill",
        output_path=output_path,
        **kwargs,
    )


@mcp.tool()
def export_pcb_3d_pdf(
    pcb_path: str,
    output_path: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    # Export a PCB board as a 3D PDF document.
    """Export a PCB board to 3D PDF using kicad-cli."""
    return export_board(
        pcb_path,
        export_type="3d-pdf",
        output_path=output_path,
        **kwargs,
    )


if __name__ == "__main__":
    mcp.run("stdio")
