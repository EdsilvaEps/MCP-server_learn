# KiCad Schematic MCP Server

This package exposes FastMCP tools that shell out to `kicad-cli` for schematic validation and export workflows, including ERC checks, schematic exports such as BOM, netlist, PDF, PNG, DXF, and HPGL, and project scaffolding for new KiCad projects.

## Features

- Validates that the input path exists and points to a supported schematic file (`.kicad_sch` or `.sch`)
- Validates the file format before invoking KiCad
- Runs ERC checks and returns normalized `errors`, `warnings`, and summary data
- Exports schematics to BOM, netlist, PDF, PNG, DXF, and HPGL formats through `kicad-cli`
- Creates a new KiCad project skeleton with empty schematic, PCB, symbol library, and footprint library files

## Usage

Install the package and run the server:

```bash
cd kicad_mcp
pip install -e .
python main.py
```

The MCP tools exposed are:

- `run_erc(schematic_path, format="json", severity_all=False, severity_error=False, severity_warning=False, severity_exclusions=False)`
- `export_bom(schematic_path, output_path=None, variant=None, preset=None, format_preset=None, fields=None, labels=None, group_by=None, sort_field=None, sort_asc=False, filter=None, exclude_dnp=False, field_delimiter=None, string_delimiter=None, ref_delimiter=None, ref_range_delimiter=None, keep_tabs=False, keep_line_breaks=False)`
- `export_netlist(schematic_path, output_path=None, format=None, variant=None)`
- `export_pdf(schematic_path, output_path=None, drawing_sheet=None, variant=None, theme=None, black_and_white=False, exclude_drawing_sheet=False, default_font=None, draw_hop_over=False, exclude_pdf_property_popups=False, exclude_pdf_hierarchical_links=False, exclude_pdf_metadata=False, no_background_color=False, pages=None)`
- `export_svg(schematic_path, output_path=None, drawing_sheet=None, variant=None, theme=None, black_and_white=False, exclude_drawing_sheet=False, default_font=None, draw_hop_over=False, no_background_color=False, pages=None)`
- `export_dxf(schematic_path, output_path=None, drawing_sheet=None, variant=None, theme=None, black_and_white=False, exclude_drawing_sheet=False, default_font=None, draw_hop_over=False, pages=None)`
- `create_project(project_name, project_dir=None)`

Example export calls:

```python
export_bom("example.kicad_sch", output_path="out/bom.csv")
export_pdf("example.kicad_sch", output_path="out/schematic.pdf")
export_svg("example.kicad_sch", output_path="out/schematic.svg")
```

Example project creation:

```python
create_project("MyBoard", project_dir="/tmp/my-board")
```

## Installing kicad-cli

The server expects `kicad-cli` to be available on your terminal `PATH`.

### macOS

Install KiCad with Homebrew:

```bash
brew install --cask kicad
```

KiCad typically installs the CLI at:

```text
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
```

If `kicad-cli` is not found in a new terminal session, add KiCad's binary directory to your shell profile:

```bash
echo 'export PATH="/Applications/KiCad/KiCad.app/Contents/MacOS:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Verify it works:

```bash
kicad-cli --help
```

### Windows

Install KiCad with Winget:

```powershell
winget install -e --id KiCad.KiCad
```

If you prefer the installer, download it from the official KiCad website.

The CLI executable is usually located in a folder such as:

```text
C:\Program Files\KiCad\bin\kicad-cli.exe
```

or under a versioned KiCad installation folder such as:

```text
C:\Program Files\KiCad\8.0\bin\kicad-cli.exe
```

Add that folder to your `PATH` so it is available in new terminal sessions:

1. Open "Environment Variables"
2. Edit the user or system `Path` variable
3. Add the KiCad `bin` directory, for example `C:\Program Files\KiCad\8.0\bin`
4. Open a new terminal and verify:

```powershell
kicad-cli --help
```

### Linux

Install KiCad from your distribution's package manager. Examples:

Debian/Ubuntu:

```bash
sudo apt update
sudo apt install kicad
```

Fedora:

```bash
sudo dnf install kicad
```

Arch Linux:

```bash
sudo pacman -S kicad
```

If the CLI is not found, add the install location to your shell profile:

```bash
echo 'export PATH="$PATH:/usr/bin"' >> ~/.bashrc
source ~/.bashrc
```

Verify it works:

```bash
kicad-cli --help
```

## Notes
