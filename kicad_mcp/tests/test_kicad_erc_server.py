import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import normalize_erc_report, validate_schematic_path


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
