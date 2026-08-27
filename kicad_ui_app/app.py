"""Gradio PoC UI for LLM‑assisted KiCad schematic generation.

This is a self‑contained demonstration application. It provides a two‑column
interface where the user can describe a circuit in natural language, select a
few options and trigger a (mock) generation workflow. The backend function
`generate_circuit` returns:

* a textual LLM explanation
* a list of PNG image paths (generated on the fly)
* a list of artifact file paths (schematic, netlist, BOM)
* a log string
* a status flag

All files are written under a temporary ``generated`` directory inside the
project root. The implementation avoids any external dependencies apart from
Gradio itself – the only additional import is ``base64`` for decoding an embed‑
ded placeholder PNG.

The UI uses Gradio components matching the specification:
- ``gr.Textbox`` for the circuit request
- ``gr.Accordion`` for advanced settings
- ``gr.Button`` to start generation
- ``gr.Markdown`` for the LLM output
- ``gr.Gallery`` for schematic previews
- ``gr.File`` for artifact download
- ``gr.Accordion`` with a ``gr.Textbox`` for logs
- ``gr.Chatbot`` (optional) could be added later for interactive refinement.

The code is deliberately simple and type‑annotated for clarity.
"""

import os
import base64
import datetime
from pathlib import Path
from typing import List, Dict

import gradio as gr

# ---------------------------------------------------------------------------
# Helper: write a tiny placeholder PNG (red square) to ``path``.
# The image data is a base64‑encoded 1×1 red pixel PNG, scaled up by the UI.
# ---------------------------------------------------------------------------
_RED_SQUARE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/5+hHgAFgwJ/"
    "Xc8XWQAAAABJRU5ErkJggg=="
)

def _write_placeholder_png(path: Path) -> None:
    """Create a tiny red‑square PNG at *path*.

    Args:
        path: Destination file path. Parent directories are created automatically.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    png_bytes = base64.b64decode(_RED_SQUARE_PNG_B64)
    path.write_bytes(png_bytes)

# ---------------------------------------------------------------------------
# Mock backend – in a real system this would call the LLM and KiCad tools.
# ---------------------------------------------------------------------------
def generate_circuit(
    prompt: str,
    model: str,
    complexity: str,
    generate_bom: bool,
    generate_pcb: bool,
) -> Dict:
    """Generate a circuit design by invoking the external script.

    The function calls the system‑wide ``adversarial_electronics.sh`` script,
    passing the user's *prompt* as a command‑line argument. The script creates
    design artifacts under ``../../adversarial-loop-generator/custom_generated_design``
    relative to this file. This implementation gathers the resulting files and
    any generated PNG images, returning them for the UI.

    Args:
        prompt: Natural‑language description of the desired circuit.
        model: Ignored – the script determines the model internally.
        complexity: Ignored – the script determines complexity internally.
        generate_bom: Ignored – BOM generation is handled by the script.
        generate_pcb: Ignored – PCB generation is handled by the script.

    Returns:
        Mapping with keys ``llm_output``, ``images``, ``files``, ``logs`` and
        ``status`` matching the UI specification.
    """
    import subprocess
    import shlex
    # Resolve the target directory where the script will place its output.
    # This matches the script's internal relative path "../adversarial-loop-generator".
    target_dir = Path(__file__).resolve().parent.parent / "adversarial-loop-generator" / "custom_generated_design"
    # Ensure the directory exists before invoking the script (the script may clean it).
    target_dir.mkdir(parents=True, exist_ok=True)

    # Resolve the script location (it is not guaranteed to be on $PATH).
    script_path = Path(__file__).resolve().parent.parent / "back_frontend_stability_agent" / "adversarial_electronics.sh"
    # Build the command – invoke via bash to ensure execution.
    cmd = ["bash", str(script_path), " -d ",prompt]
    # Run the script, capturing stdout and stderr for logs.
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent))
    logs = proc.stdout + ("\n" if proc.stdout and proc.stderr else "") + proc.stderr

    # After execution, collect all files generated in the target directory.
    # Images are any PNG files; other artifacts are returned as generic files.
    images = []
    files = []
    if target_dir.is_dir():
        for p in sorted(target_dir.rglob("*")):
            if p.is_file():
                if p.suffix.lower() == ".svg":
                    images.append(str(p))
                else:
                    files.append(str(p))

    # Simple textual output indicating success.
    llm_output = f"**Design request**: {prompt}\n\nDesign generated by ``adversarial_electronics.sh``."

    status = "complete" if proc.returncode == 0 else "failed"

    return {
        "llm_output": llm_output,
        "images": images,
        "files": files,
        "logs": logs,
        "status": status,
    }

# ---------------------------------------------------------------------------
# Gradio UI definition.
# ---------------------------------------------------------------------------
with gr.Blocks(title="KiCad Design Assistant (PoC)") as demo:
    gr.Markdown("# KiCad Design Assistant – Proof of Concept")
    with gr.Row():
        # Left column – inputs & controls
        with gr.Column(scale=1):
            circuit_input = gr.Textbox(
                lines=8,
                label="Circuit Request",
                placeholder="e.g. Design a 5V buck converter from 12V input capable of delivering 2A.",
            )
            # Advanced settings inside an accordion
            with gr.Accordion("Advanced Settings", open=False):
                model_dropdown = gr.Dropdown(
                    choices=["GPT-4", "GPT-4.1", "Local Llama", "Mock Backend"],
                    value="Mock Backend",
                    label="Model",
                )
                complexity_dropdown = gr.Dropdown(
                    choices=["Simple", "Medium", "Complex"],
                    value="Simple",
                    label="Complexity Level",
                )
                generate_bom_checkbox = gr.Checkbox(
                    label="Generate Bill of Materials",
                    value=False,
                )
                generate_pcb_checkbox = gr.Checkbox(
                    label="Generate PCB Placeholder",
                    value=False,
                )
            generate_btn = gr.Button("Generate Schematic", variant="primary")
            status_md = gr.Markdown("_Idle_")
        # Right column – results
        with gr.Column(scale=2):
            llm_output_md = gr.Markdown(label="LLM Design Output")
            gallery = gr.Gallery(label="Schematic Preview", show_label=True, columns=2)
            file_download = gr.File(label="Design Artifacts", file_count="multiple")
            with gr.Accordion("Execution Logs", open=False):
                log_box = gr.Textbox(lines=15, label="Logs")

    # -----------------------------------------------------------------------
    # Callback wiring
    # -----------------------------------------------------------------------
    def _on_generate(
        prompt: str,
        model: str,
        complexity: str,
        gen_bom: bool,
        gen_pcb: bool,
    ):
        if not prompt.strip():
            return (
                "**Error:** Please describe a circuit.",
                [],
                [],
                "No prompt supplied.",
                "failed",
            )
        result = generate_circuit(prompt, model, complexity, gen_bom, gen_pcb)
        # Gradio expects the exact ordering of output components.
        return (
            result["llm_output"],
            result["images"],
            result["files"],
            result["logs"],
            result["status"],
        )

    # Bind inputs and outputs – note the order matches the return tuple.
    generate_btn.click(
        fn=_on_generate,
        inputs=[
            circuit_input,
            model_dropdown,
            complexity_dropdown,
            generate_bom_checkbox,
            generate_pcb_checkbox,
        ],
        outputs=[
            llm_output_md,
            gallery,
            file_download,
            log_box,
            status_md,
        ],
    )

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    demo.queue().launch(share=True)
