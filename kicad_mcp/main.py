import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("kicad-erc-server", instructions="Run KiCad schematic ERC checks through kicad-cli and return normalized structured results.")

SUPPORTED_SCHEMATIC_EXTENSIONS = {".kicad_sch", ".sch"}

def validate_schematic_path(path: str) -> str:
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


def _coerce_violation_list(payload: Any, key: str) -> List[Dict[str, Any]]:
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
def run_erc(
    schematic_path: str,
    format: str = "json",
    severity_all: bool = False,
    severity_error: bool = False,
    severity_warning: bool = False,
    severity_exclusions: bool = False,
) -> Dict[str, Any]:
    """Run KiCad ERC on a schematic and return normalized structured results."""
    validated_path = validate_schematic_path(schematic_path)

    if format not in {"json", "report"}:
        raise ValueError("format must be either 'json' or 'report'")

    executable = shutil.which("kicad-cli") or shutil.which("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    if not executable:
        raise RuntimeError("kicad-cli was not found on PATH or the default macOS installation path")

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


if __name__ == "__main__":
    mcp.run("stdio")
