import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import (
    create_project,
    export_board,
    export_pcb_drill,
    export_pcb_gerber,
    export_pcb_pdf,
    export_pcb_3d_pdf,
    export_schematic,
    normalize_erc_report,
    validate_board_path,
    validate_schematic_path,
)


def test_validate_schematic_path_rejects_non_schematic_file(tmp_path):
    sample = tmp_path / "notes.txt"
    sample.write_text("hello")

    with pytest.raises(ValueError):
        validate_schematic_path(str(sample))


def test_validate_schematic_path_accepts_existing_kicad_sch(tmp_path):
    sample = tmp_path / "example.kicad_sch"
    sample.write_text("(kicad_sch (version 20211123) (generator eeschema))")

    result = validate_schematic_path(str(sample))

    assert result == str(sample.resolve())


def test_normalize_erc_report_handles_json_payload():
    payload = {
        "version": 1,
        "errors": [
            {
                "severity": "error",
                "message": "Net label not connected",
                "reference": "U1",
                "sheet": "/Sheet1",
            }
        ],
        "warnings": [
            {
                "severity": "warning",
                "message": "Missing footprint",
                "reference": "R1",
                "sheet": "Sheet1",
            }
        ],
    }

    normalized = normalize_erc_report(payload)

    assert normalized["violation_count"] == 2
    assert normalized["errors"][0]["reference"] == "U1"
    assert normalized["warnings"][0]["sheet"] == "Sheet1"
    assert normalized["summary"]["by_severity"]["error"] == 1
    assert normalized["summary"]["by_severity"]["warning"] == 1


def test_normalize_erc_report_handles_text_payload():
    payload = "Error: Missing power flag\nWarning: Unconnected pin"

    normalized = normalize_erc_report(payload)

    assert normalized["violation_count"] == 2
    assert normalized["errors"][0]["message"].startswith("Error")
    assert normalized["warnings"][0]["message"].startswith("Warning")


def test_normalize_erc_report_handles_kicad_json_schema():
    payload = {
        "sheets": [
            {
                "path": "/",
                "violations": [
                    {
                        "severity": "error",
                        "message": "Pin not connected",
                        "reference": "U1",
                    },
                    {
                        "severity": "warning",
                        "message": "Unconnected power pin",
                        "reference": "U2",
                    },
                ],
            }
        ]
    }

    normalized = normalize_erc_report(payload)

    assert normalized["violation_count"] == 2
    assert normalized["summary"]["by_severity"]["error"] == 1
    assert normalized["summary"]["by_severity"]["warning"] == 1
    assert normalized["errors"][0]["reference"] == "U1"


def test_create_project_creates_expected_kicad_files(tmp_path):
    project_root = tmp_path / "new-project"

    result = create_project("NewProject", project_dir=str(project_root))

    assert result["success"] is True
    assert result["project_name"] == "NewProject"
    assert (project_root / "NewProject.kicad_pro").exists()
    assert (project_root / "NewProject.kicad_sch").exists()
    assert (project_root / "NewProject.kicad_pcb").exists()
    assert (project_root / "sym-lib-table").exists()
    assert (project_root / "fp-lib-table").exists()
    assert (project_root / "libraries" / "footprints").is_dir()
    assert (project_root / "libraries" / "3D").is_dir()


def test_export_schematic_invokes_expected_kicad_cli_command(tmp_path, monkeypatch):
    sample = tmp_path / "example.kicad_sch"
    sample.write_text("(kicad_sch (version 20211123) (generator eeschema))")
    output_path = tmp_path / "exports" / "example.csv"

    recorded = {}

    def fake_run(command, capture_output, text):
        recorded["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("main.subprocess.run", fake_run)
    monkeypatch.setattr("main.shutil.which", lambda name: "/usr/bin/kicad-cli")

    result = export_schematic(str(sample), export_type="bom", output_path=str(output_path))

    assert recorded["command"][:4] == ["/usr/bin/kicad-cli", "sch", "export", "bom"]
    assert recorded["command"][-2:] == ["--output", str(output_path.resolve())]
    assert result["success"] is True
    assert result["output_path"] == str(output_path.resolve())
    assert result["export_type"] == "bom"


@pytest.mark.parametrize(
    ("export_type", "expected_subcommand", "output_path"),
    [
        ("netlist", "netlist", "example.net"),
        ("pdf", "pdf", "example.pdf"),
        ("svg", "svg", "example.svg"),
        ("dxf", "dxf", "example.dxf"),
    ],
)
def test_export_schematic_supports_multiple_schematic_exports(tmp_path, monkeypatch, export_type, expected_subcommand, output_path):
    sample = tmp_path / "example.kicad_sch"
    sample.write_text("(kicad_sch (version 20211123) (generator eeschema))")
    output_file = tmp_path / output_path

    recorded = {}

    def fake_run(command, capture_output, text):
        recorded["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("main.subprocess.run", fake_run)
    monkeypatch.setattr("main.shutil.which", lambda name: "/usr/bin/kicad-cli")

    result = export_schematic(str(sample), export_type=export_type, output_path=str(output_file))

    assert recorded["command"][0:4] == ["/usr/bin/kicad-cli", "sch", "export", expected_subcommand]
    assert result["success"] is True
    assert result["export_type"] == export_type


def test_validate_board_path_accepts_existing_kicad_pcb(tmp_path):
    sample = tmp_path / "example.kicad_pcb"
    sample.write_text("(kicad_pcb (version 20211014) (generator pcbnew))")

    result = validate_board_path(str(sample))

    assert result == str(sample.resolve())


@pytest.mark.parametrize(
    ("export_type", "expected_subcommand", "output_path"),
    [
        ("pdf", "pdf", "example.pdf"),
        ("gerber", "gerber", "example.zip"),
        ("drill", "drill", "example.drl"),
        ("3d-pdf", "3d-pdf", "example.3d.pdf"),
    ],
)
def test_export_board_supports_multiple_board_exports(tmp_path, monkeypatch, export_type, expected_subcommand, output_path):
    sample = tmp_path / "example.kicad_pcb"
    sample.write_text("(kicad_pcb (version 20211014) (generator pcbnew))")
    output_file = tmp_path / output_path

    recorded = {}

    def fake_run(command, capture_output, text):
        recorded["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("main.subprocess.run", fake_run)
    monkeypatch.setattr("main.shutil.which", lambda name: "/usr/bin/kicad-cli")

    result = export_board(str(sample), export_type=export_type, output_path=str(output_file))

    assert recorded["command"][0:4] == ["/usr/bin/kicad-cli", "pcb", "export", expected_subcommand]
    assert result["success"] is True
    assert result["export_type"] == export_type


def test_export_pcb_pdf_wrapper_invokes_board_export(tmp_path, monkeypatch):
    sample = tmp_path / "example.kicad_pcb"
    sample.write_text("(kicad_pcb (version 20211014) (generator pcbnew))")
    output_file = tmp_path / "example.pdf"

    recorded = {}

    def fake_run(command, capture_output, text):
        recorded["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("main.subprocess.run", fake_run)
    monkeypatch.setattr("main.shutil.which", lambda name: "/usr/bin/kicad-cli")

    result = export_pcb_pdf(str(sample), output_path=str(output_file), layers="F.Cu")

    assert recorded["command"][0:4] == ["/usr/bin/kicad-cli", "pcb", "export", "pdf"]
    assert result["success"] is True
    assert result["output_path"] == str(output_file.resolve())
