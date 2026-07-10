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
