#!/usr/bin/env bash
set -euo pipefail

# adversarial_electronics.sh – simplified version without Git worktrees.
# All generated files are placed under a single "generated" directory.

# ---------------------------------------------------------
# 0️⃣  Parse options (debug / help) and capture the design prompt
# ---------------------------------------------------------
DEBUG=0 # 0 = quiet (default), 1 = foreground + full trace
while (( "$#" )); do
    case "$1" in
        -d|--debug) DEBUG=1; shift ;;
        -h|--help)  echo "Usage: $0 [--debug|-d] <design-prompt>"; exit 0 ;;
        *) break ;;
    esac
done

# Remaining arguments constitute the user's design description.
if [ "$#" -gt 0 ]; then
    USER_DESIGN="$*"
else
    read -rp "🖊️  Describe the circuit you want (e.g. \"voltage divider\", \"low-pass filter\", …): " USER_DESIGN
fi

# ---------------------------------------------------------
# 1️⃣  Define the single output directory
# ---------------------------------------------------------
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GENERATED_ROOT="${SCRIPT_DIR}/generated"
mkdir -p "${GENERATED_ROOT}"

# Clean previous run (optional – remove previous project folder)
if [ -d "${GENERATED_ROOT}/custom_generated_design" ]; then
    rm -rf "${GENERATED_ROOT}/custom_generated_design"
fi

# ---------------------------------------------------------
# 2️⃣  Helper: start Hermes (quiet vs. foreground)
# ---------------------------------------------------------
start_hermes() {
    local prompt="$1"
    local design_mode="$2" # "true" for project generation, "false" for review/fix
    local log_file
    log_file=$(mktemp "/tmp/hermes-out-$(date +%s)-XXXX.txt")
    if (( DEBUG )); then
        if [[ "$design_mode" == "true" ]]; then
            echo "🚀  Starting Hermes (foreground, design mode)…"
            hermes -s kicad_mcp_workflow chat -q "$prompt" | tee "$log_file"
        else
            echo "🚀  Starting Hermes (foreground)…"
            hermes chat -q "$prompt" | tee "$log_file"
        fi
        export HERMES_PID=$$   # dummy pid for debug mode
    else
        if [[ "$design_mode" == "true" ]]; then
            printf "🚀  Starting Hermes (background, design mode)…\n" >&2
            hermes -s kicad_mcp_workflow chat -q "$prompt" >"$log_file" 2>&1 &
        else
            printf "🚀  Starting Hermes (background)…\n" >&2
            hermes chat -q "$prompt" >"$log_file" 2>&1 &
        fi
        local pid=$!
        export HERMES_PID=$pid
    fi
    export HERMES_LOG="$log_file"
    printf "%s:%s" "$HERMES_PID" "$log_file"
}

# ---------------------------------------------------------
# 3️⃣  Helper to read REVIEW.md (if it exists)
# ---------------------------------------------------------
read_review() {
    local review_path="$PROJECT_ROOT/REVIEW.md"
    if [[ -f "$review_path" ]]; then
        cat "$review_path"
    else
        echo ""
    fi
}

# ---------------------------------------------------------
# 4️⃣  Generator – create KiCad project inside the generated folder
# ---------------------------------------------------------
PROJECT_NAME="custom_generated_design"
PROJECT_ROOT="${GENERATED_ROOT}/${PROJECT_NAME}"
mkdir -p "$PROJECT_ROOT"

GEN_PROMPT=$(cat <<EOF
You are a KiCad‑MCP assistant. Using the internal MCP tools, **create the entire KiCad project inside the following absolute folder**:

    $PROJECT_ROOT

**Guidelines**
1. create the KiCad project only at the path above.
2. All generated files (schematic, board, netlist, etc.) must be stored inside `$PROJECT_ROOT`.

**User design request**
"$USER_DESIGN"

**What you should return**
1. A short, human‑readable summary of what you built.
2. One line that starts with **Schematic:** followed by the **absolute** path to the generated `*.kicad_sch` file.
3. An SVG or PDF exported file of the schematic (if possible).
EOF
)

start_hermes "$GEN_PROMPT" "true"
GEN_PID=$HERMES_PID
GEN_LOG=$HERMES_LOG
if (( ! DEBUG )); then
    wait "$GEN_PID"
fi

tail -n 30 "$GEN_LOG"
echo "🟢  Generator finished."

# ---------------------------------------------------------
# 5️⃣  Locate generated files
# ---------------------------------------------------------
find_schematic() {
    SCHEMATIC_PATH=$(find "$PROJECT_ROOT" -type f -name "*.kicad_sch" -print -quit)
    if [ -z "$SCHEMATIC_PATH" ]; then
        echo "❌  No KiCad schematic (*.kicad_sch) found under $PROJECT_ROOT."
        exit 1
    fi
    echo "🔎  Discovered schematic: $SCHEMATIC_PATH"
}

find_board() {
    BOARD_PATH=$(find "$PROJECT_ROOT" -type f -name "*.kicad_pcb" -print -quit || true)
    if [ -n "$BOARD_PATH" ]; then
        echo "🔎  Discovered board: $BOARD_PATH"
    else
        echo "⚠️  No KiCad board (*.kicad_pcb) found yet – ERC will run on schematic only."
    fi
}

find_schematic
find_board

# ---------------------------------------------------------
# 6️⃣  Critic – run KiCad ERC and produce REVIEW.md
# ---------------------------------------------------------
run_critic() {
    echo "🔍  Running KiCad ERC on $SCHEMATIC_PATH"
    start_hermes \
        "Run KiCad’s Electrical Rules Check (ERC) using the mcp__kicad_general__run_erc tool on the schematic at \`$SCHEMATIC_PATH\`.

        Generate a markdown file **REVIEW.md** inside the same project folder (\`$PROJECT_ROOT\`) that lists each ERC violation (ignore warnings, consider only errors), explains why it occurs, and proposes a concrete fix.
        If the \`violations\` array is empty, write to REVIEW.md only the exact line:

        <<ERC-PASS>>

        and nothing else.
        If there are violations, produce the normal markdown review." \
        "false"
    local pid=$HERMES_PID
    local log=$HERMES_LOG
    wait "$pid"
    tail -n 40 "$log"
}

# ---------------------------------------------------------
# 7️⃣  Refiner – apply fixes reported in REVIEW.md
# ---------------------------------------------------------
run_refiner() {
    local report="$1"
    echo "🛠️  Refiner – applying fixes to $SCHEMATIC_PATH (project stays in $PROJECT_ROOT)"
    start_hermes \
"Using the KiCad MCP toolset, fix the ERC issues reported below **inside the existing project folder** \`$PROJECT_ROOT\`.
Do **not** change the intended topology; only apply the concrete edits listed in the report (add net‑labels, connect missing pins, delete orphan wires, etc.).
At the end of the process, generate an SVG or PDF exported file of the updated schematic and save it in the same project folder.

---Report---
$report
---End of report---" "true"
    local pid=$HERMES_PID
    local log=$HERMES_LOG
    wait "$pid"
    tail -n 30 "$log"
}

# ---------------------------------------------------------
# 8️⃣  Iterative refinement loop (max 3 passes)
# ---------------------------------------------------------
MAX_ITER=3
for ((i=1; i<=MAX_ITER; i++)); do
    echo "─────────────────────────────────────────────"
    echo "🔎  Critic pass #$i"
    echo "─────────────────────────────────────────────"

    CRITIC_OUT=$(run_critic)
    echo "📝  ERC review output:"
    echo "$CRITIC_OUT"

    REVIEW_CONTENT=$(read_review)

    if grep -m1 -F "<<ERC-PASS>>" <<<"$REVIEW_CONTENT" > /dev/null; then
        echo "✅  ERC passed on iteration $i"
        break
    fi

    REFINER_OUT=$(run_refiner "$REVIEW_CONTENT")
    echo "$REFINER_OUT"

    # Re‑discover files after possible changes
    find_schematic
    find_board

done

# ---------------------------------------------------------
# 9️⃣  Final inspection (optional)
# ---------------------------------------------------------
echo "📂  Final schematic content:"
cat "$SCHEMATIC_PATH"

# ---------------------------------------------------------
# 🔟  List generated project files
# ---------------------------------------------------------
echo "📁  Project folder contents (under $PROJECT_ROOT):"
find "$PROJECT_ROOT" -type f -or -type d | sed "s|^$PROJECT_ROOT/||"

# ---------------------------------------------------------
# Cleanup (optional)
# ---------------------------------------------------------
# Uncomment the following line to remove the generated directory after a run
# rm -rf "${GENERATED_ROOT}"