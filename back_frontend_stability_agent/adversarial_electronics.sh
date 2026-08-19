#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------
# Hermes‑driven micro‑electronics design loop (user‑defined design)
# -----------------------------------------------------------------
# Docs for Git work‑trees:
#   https://hermes-agent.nousresearch.com/docs/user-guide/git-worktrees/

# ---------------------------------------------------------
# 0️⃣  Parse options (debug / verbose) and grab the design prompt
# ---------------------------------------------------------
DEBUG=0               # 0 = quiet (default), 1 = foreground + full trace
while (( "$#" )); do
    case "$1" in
        -d|--debug)   DEBUG=1; shift ;;
        -h|--help)    echo "Usage: $0 [--debug|-d] <design‑prompt>"; exit 0 ;;
        *) break ;;
    esac
done

# Anything left on the command line is the user’s design description.
# If nothing was supplied, ask interactively.
if [ "$#" -gt 0 ]; then
    USER_DESIGN="$*"
else
    read -rp "🖊️  Describe the circuit you want (e.g. “voltage divider”, “low‑pass filter”, …): " USER_DESIGN
fi

# ---------------------------------------------------------
# 1️⃣  Repository sanity checks
# ---------------------------------------------------------
REPO_ROOT="$(pwd)"                # must be run from the repo root (contains .git)
BRANCH="adversarial-loop"

git rev-parse --is-inside-work-tree >/dev/null || {
    echo "❌ Not inside a git repo"
    exit 1
}
# Create (or reset) the experiment branch
git checkout -b "$BRANCH" || true

# ---------------------------------------------------------
# 2️⃣  Detect an *empty* repository (no commits yet)
# ---------------------------------------------------------
if git rev-parse --verify HEAD >/dev/null 2>&1; then
    echo "✅ Repository already has commits – proceeding."
else
    echo "⚠️  Repository is empty – creating an initial empty commit."
    git checkout --orphan "$BRANCH"
    git commit --allow-empty -m "Initial empty commit for $BRANCH"
fi

# ---------------------------------------------------------
# 3️⃣  Create auxiliary work‑trees (generator / critic / refiner)
# ---------------------------------------------------------
git worktree add -b generator "../adversarial-loop-generator" || true
git worktree add -b critic    "../adversarial-loop-critic"    || true
git worktree add -b refiner   "../adversarial-loop-refine"   || true

# -----------------------------------------------------------------
# 4️⃣  Helper: start Hermes (quiet vs. foreground)
# -----------------------------------------------------------------
start_hermes() {
    local prompt="$1"
    local log_file
    log_file=$(mktemp "/tmp/hermes-out-$(date +%s)-XXXX.txt")

    if (( DEBUG )); then
        echo "📝  Hermes (foreground) – Prompt:"
        echo "---------------------------------------------------"
        echo "$prompt"
        echo "---------------------------------------------------"
        hermes chat -q "$prompt" | tee "$log_file"
        export HERMES_PID=$$   # fake PID – just to keep the variable set
    else
        printf "🚀  Starting Hermes (background)…\n" >&2
        hermes chat -q "$prompt" >"$log_file" 2>&1 &
        local pid=$!
        export HERMES_PID=$pid
    fi

    export HERMES_LOG="$log_file"
    printf "%s:%s" "$HERMES_PID" "$log_file"
}

# -----------------------------------------------------------------
# 5️⃣  Small wrapper around hermes tool_call that prints the call
# -----------------------------------------------------------------
run_tool() {
    local name="$1"
    local args_json="$2"

    if (( DEBUG )); then
        echo "🔧  TOOL CALL → $name"
        echo "     arguments: $args_json"
    fi

    hermes tool_call \
        name="$name" \
        arguments="$args_json" \
        --quiet 2>/dev/null || true
}

# ---------------------------------------------------------
# 6️⃣  Generator – create project, schematic, and keep everything
#          inside the generator work‑tree
# ---------------------------------------------------------
cd "../adversarial-loop-generator" || exit 1

# -----------------------------------------------------------------
# 6a️⃣  Fixed project name (you can customise it if you wish)
# -----------------------------------------------------------------
PROJECT_NAME="custom_generated_design"
# Absolute path to the folder where the whole KiCad project will live
PROJECT_ROOT="$(pwd)/$PROJECT_NAME"
mkdir -p "$PROJECT_ROOT"

# -----------------------------------------------------------------
# 6b️⃣  Build the generator prompt – we tell Hermes the exact paths
# -----------------------------------------------------------------
GEN_PROMPT=$(cat <<EOF
You are a KiCad‑MCP assistant. Using the internal MCP tools, **create the entire KiCad project inside the following absolute folder**:

    $PROJECT_ROOT

**Tools you must call (in this order)**
1. `mcp__kicad_general__create_project` – create a KiCad project at the path above.
2. Either `mcp__kicad_general__add_schematic_component` **or** `mcp__kicad_general__batch_add_components` – place the components that satisfy the user’s request.
   *All generated files (schematic, board, netlist, etc.) must be stored inside `$PROJECT_ROOT`.*
3. (Optional) any additional KiCad tool you think is needed, but **never write outside `$PROJECT_ROOT`**.

**User design request**
"$USER_DESIGN"

**What you should return**
1. A short, human‑readable summary of what you built (project name, key components, etc.).
2. One line that starts with **Schematic:** followed by the **absolute** path to the generated `*.kicad_sch` file (which will live somewhere under `$PROJECT_ROOT`).

Do **not** embed any large dumps or extra explanatory text – the script will parse the lines that start with *Schematic:*.
EOF
)

start_hermes "$GEN_PROMPT"
GEN_PID=$HERMES_PID
GEN_LOG=$HERMES_LOG

# ---- WAIT ONLY WHEN NOT IN DEBUG ---------------------------------
if (( ! DEBUG )); then
    wait "$GEN_PID"
fi

# Show a short tail of the generator output (just for the user)
tail -n 30 "$GEN_LOG"
echo "🟢  Generator finished."

# ---------------------------------------------------------
# 6c️⃣  Locate generated files (no log parsing)
# ---------------------------------------------------------
# 1) Schematic
SCHEMATIC_REL=$(find "$PROJECT_ROOT" -type f -name "*.kicad_sch" -print -quit)
if [ -z "$SCHEMATIC_REL" ]; then
    echo "❌  No KiCad schematic (*.kicad_sch) found under $PROJECT_ROOT."
    exit 1
fi
SCHEMATIC_PATH="$(realpath "$SCHEMATIC_REL")"
echo "🔎  Discovered schematic: $SCHEMATIC_PATH"

# 2) Board file (needed for ERC)
BOARD_REL=$(find "$PROJECT_ROOT" -type f -name "*.kicad_pcb" -print -quit)
if [ -z "$BOARD_REL" ]; then
    echo "⚠️  No KiCad board (*.kicad_pcb) found yet – ERC will still run on the schematic alone."
else
    BOARD_PATH="$(realpath "$BOARD_REL")"
    echo "🔎  Discovered board: $BOARD_PATH"
fi

# ---------------------------------------------------------
# 7️⃣  Commit the freshly created project (still inside generator WT)
# ---------------------------------------------------------
git add "$PROJECT_NAME"
git commit -m "Initial generation of KiCad project $PROJECT_NAME" || echo "⚠️  Nothing to commit"

# ---------------------------------------------------------
# 8️⃣  Critic – run KiCad ERC on the schematic and ask Hermes to review it
# ---------------------------------------------------------
run_critic() {
    echo "🔍  Running KiCad ERC on $SCHEMATIC_PATH"
    ERC_JSON=$(run_tool "mcp__kicad_general__run_erc" '{"path":"'"$SCHEMATIC_PATH"'"}')

    start_hermes \
"We have run KiCad’s Electrical Rules Check (ERC) on the schematic at \`$SCHEMATIC_PATH\`.
Below is the raw JSON result from the tool:

\`\`\`json
$ERC_JSON
\`\`\`

Create a markdown file **REVIEW.md** *inside the same project folder* (\`$PROJECT_ROOT\`) that lists each ERC violation, explains why it occurs, and proposes a concrete fix (e.g. “add net label VCC to pin 1 of V1”, “connect pin 2 of R2 to GND”, etc.).
If the \`violations\` array is empty, simply output the word **OK**."
    local pid=$HERMES_PID
    local log=$HERMES_LOG
    wait "$pid"
    tail -n 40 "$log"
}

# ---------------------------------------------------------
# 9️⃣  Refiner – ask Hermes to apply the fixes it suggested
# ---------------------------------------------------------
run_refiner() {
    local report="$1"
    echo "🛠️  Refiner – applying fixes to $SCHEMATIC_PATH (all files stay in $PROJECT_ROOT)"
    start_hermes \
"Using the KiCad MCP toolset, fix the ERC issues reported below **inside the existing project folder** \`$PROJECT_ROOT\`.
Do **not** change the intended topology; only apply the concrete edits listed in the report (add net‑labels, connect missing pins, delete orphan wires, etc.).

---Report---
$report
---End of report---"
    local pid=$HERMES_PID
    local log=$HERMES_LOG
    wait "$pid"
    tail -n 30 "$log"
}

# ---------------------------------------------------------
# 🔟  Iterative refinement loop (max 3 passes)
# ---------------------------------------------------------
MAX_ITER=3
for ((i=1; i<=MAX_ITER; i++)); do
    echo "─────────────────────────────────────────────"
    echo "🔎  Critic pass #$i"
    echo "─────────────────────────────────────────────"

    cd "../adversarial-loop-critic" || exit 1
    git fetch
    git merge generator --allow-unrelated-histories \
        -m "Merge generated KiCad project for ERC review" || \
        echo "⚠️  Merge failed, continuing anyway"

    CRITIC_OUT=$(run_critic)
    echo "$CRITIC_OUT"

    if [[ "$CRITIC_OUT" == *"OK"* ]]; then
        echo "✅  ERC passed on iteration $i"
        break
    fi

    git add .
    git commit -m "Sync ERC review for design" || \
        echo "⚠️  Nothing to commit"

    cd "../adversarial-loop-refine" || exit 1
    git fetch
    git merge generator --allow-unrelated-histories \
        -m "Merge generated KiCad project for refinement" || \
        echo "⚠️  Merge failed, continuing anyway"

    echo "─────────────────────────────────────────────"
    echo "🛠️  Refiner pass #$i"
    echo "─────────────────────────────────────────────"
    REFINER_OUT=$(run_refiner "$CRITIC_OUT")
    echo "$REFINER_OUT"

    git add "$PROJECT_NAME"
    git commit -m "Refined KiCad project based on ERC feedback" || \
        echo "⚠️  Nothing to commit"
done

# ---------------------------------------------------------
# 1️⃣1️⃣  Inspect the final schematic (optional)
# ---------------------------------------------------------
echo "📂  Final schematic content (in worktree \`adversarial-loop-refine\`):"
git --work-tree="../adversarial-loop-refine" \
    show HEAD:"$PROJECT_NAME/design/voltage_divider.kicad_sch" | cat || true

# ---------------------------------------------------------
# 1️⃣2️⃣  List the project files that now exist under the generator WT
# ---------------------------------------------------------
echo "📁  Project folder contents (still inside $PROJECT_ROOT):"
find "$PROJECT_ROOT" -type f -or -type d | sed "s|^$PROJECT_ROOT/||"

# ---------------------------------------------------------
# 1️⃣3️⃣  Clean‑up helper (run manually or uncomment)
# ---------------------------------------------------------
cleanup() {
    echo "🧹 Cleaning up work‑trees and temporary branches…"
    git worktree remove "../adversarial-loop-generator" --force
    git worktree remove "../adversarial-loop-critic"    --force
    git worktree remove "../adversarial-loop-refine"   --force

    for br in generator critic refiner; do
        git branch -D "$br" 2>/dev/null || true
    done

    git checkout main
    git branch -D "$BRANCH" 2>/dev/null || true
}
# Uncomment to auto‑clean after a successful run:
# cleanup