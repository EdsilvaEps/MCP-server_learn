# KiCad ERC MCP Server

This package exposes a FastMCP tool that shells out to `kicad-cli sch erc`, validates the provided schematic path, and returns normalized ERC results as structured JSON.

## Features

- Validates that the input path exists and points to a supported schematic file (`.kicad_sch` or `.sch`)
- Validates the file format before invoking KiCad
- Captures the JSON/text report emitted by `kicad-cli`
- Normalizes ERC findings into structured `errors`, `warnings`, and summary data

## Usage

Install the package and run the server:

```bash
cd kicad_mcp
pip install -e .
python main.py
```

The MCP tool exposed is:

- `run_erc(schematic_path, format="json", severity_all=False, severity_error=False, severity_warning=False, severity_exclusions=False)`

## Notes

The server expects `kicad-cli` to be available on your PATH or installed at the default macOS location:

```text
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
```
