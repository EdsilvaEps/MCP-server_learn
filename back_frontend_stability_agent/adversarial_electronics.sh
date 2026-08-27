#!/usr/bin/env bash
set -euo pipefail

# call cleanup.sh to remove the worktrees and reset the branch
echo "🧹  Cleaning up worktrees and resetting branch..."
bash cleanup.sh

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
    # define a boolean argument to control whether to run in design mode or not
    # this will force hermes to use the kicad_mcp_workflow skill when design_mode is true
    local design_mode="$2"
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
        export HERMES_PID=$$   # fake PID – just to keep the variable set
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

#---------------------------------------------------------
# 5a️⃣  Helper to read the REVIEW.md file (if it exists)
#---------------------------------------------------------
read_review() {
    # $PROJECT_ROOT is always set to the work‑tree’s project folder
    local review_path="$PROJECT_ROOT/REVIEW.md"
    if [[ -f "$review_path" ]]; then
        cat "$review_path"
    else
        # Return an empty string if the file is missing – the refiner
        # will simply receive nothing and can handle it gracefully.
        echo ""
    fi
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
# Absolute path to the folder where the output of the current agent will live
PROJECT_ROOT="$(pwd)/$PROJECT_NAME"
mkdir -p "$PROJECT_ROOT"

# -----------------------------------------------------------------
# 6b️⃣  Build the generator prompt – we tell Hermes the exact paths
# -----------------------------------------------------------------
GEN_PROMPT=$(cat <<EOF
You are a KiCad‑MCP assistant. Using the internal MCP tools, **create the entire KiCad project inside the following absolute folder**:

    $PROJECT_ROOT

**Guidelines**
1. create the KiCad project only at the path above.
2. All generated files (schematic, board, netlist, etc.) must be stored inside `$PROJECT_ROOT`.

**User design request**
"$USER_DESIGN"

**What you should return**
1. A short, human‑readable summary of what you built (project name, key components, etc.).
2. One line that starts with **Schematic:** followed by the **absolute** path to the generated `*.kicad_sch` file (which will live somewhere under `$PROJECT_ROOT`).
3. An SVG or PDF exported file of the schematic (if possible).

Do **not** embed any large dumps or extra explanatory text – the script will parse the lines that start with *Schematic:*.
EOF
)

start_hermes "$GEN_PROMPT" "true"
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
find_schematic() {
    SCHEMATIC_REL=$(find "$PROJECT_ROOT" -type f -name "*.kicad_sch" -print -quit)
    if [ -z "$SCHEMATIC_REL" ]; then
        echo "❌  No KiCad schematic (*.kicad_sch) found under $PROJECT_ROOT."
        exit 1
    fi
    SCHEMATIC_PATH="$(realpath "$SCHEMATIC_REL")"
    echo "🔎  Discovered schematic: $SCHEMATIC_PATH"
    
}

find_board() {
    BOARD_REL=$(find "$PROJECT_ROOT" -type f -name "*.kicad_pcb" -print -quit)
    if [ -z "$BOARD_REL" ]; then
        echo "⚠️  No KiCad board (*.kicad_pcb) found yet – ERC will still run on the schematic alone."
    else
        BOARD_PATH="$(realpath "$BOARD_REL")"
        echo "🔎  Discovered board: $BOARD_PATH"
    fi
}

find_schematic
find_board


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

    start_hermes \
        "Run KiCad’s Electrical Rules Check (ERC) using the mcp__kicad_general__run_erc tool on the schematic at \`$SCHEMATIC_PATH\`.

        Generate a markdown file **REVIEW.md** *inside the same project folder* (\`$PROJECT_ROOT\`) that lists each ERC violation (ignore warnings, consider only errors), explains why it occurs, and proposes a concrete fix (e.g. “add net label VCC to pin 1 of V1”, “connect pin 2 of R2 to GND”, etc.).
        If the \`violations\` array is empty, *write to REVIEW.md only the exact line**:

        <<ERC-PASS>>

        and nothing else.
        If there are violations, just produce the normal markdown review." \
        "false" # design mode is false for the critic, since we are not generating new design files, just reviewing

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

    # change project root to the critic worktree so that ERC runs in the correct context
    PROJECT_ROOT="$(pwd)/$PROJECT_NAME"
    find_schematic
    find_board

    # Remove any existing REVIEW.md so that the critic will always generate a fresh one
    rm -f "$PROJECT_ROOT/REVIEW.md" || true

    CRITIC_OUT=$(run_critic)
    echo "📝  ERC review output:"
    echo "$CRITIC_OUT"

    REVIEW_CONTENT=$(read_review) # puting this in a variable so that it can be passed to the refiner

    # Check if the ERC passed (i.e., REVIEW.md contains the special line)
    # Look for the first occurrence of <<ERC-PASS>> anywhere in the review content
    if grep -m1 -F "<<ERC-PASS>>" <<<"$REVIEW_CONTENT" > /dev/null; then
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

    # change project root to the refiner worktree so that edits are applied in the correct context
    PROJECT_ROOT="$(pwd)/$PROJECT_NAME"
    find_schematic
    find_board

    REFINER_OUT=$(run_refiner "$REVIEW_CONTENT")
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
    show HEAD:"$PROJECT_NAME" | cat || true

# ---------------------------------------------------------
# 1️⃣2️⃣  List the project files that now exist under the generator WT
# ---------------------------------------------------------
echo "📁  Project folder contents (still inside $PROJECT_ROOT):"
find "$PROJECT_ROOT" -type f -or -type d | sed "s|^$PROJECT_ROOT/||"

# ---------------------------------------------------------
# 12️⃣  Final merge & commit (repo root)
# ---------------------------------------------------------
# Return to the repository root
cd "$REPO_ROOT" || exit 1

# Ensure we are on the adversarial-loop branch
git checkout "$BRANCH"

# Merge the three work‑trees back into the branch
git merge --no-ff "../adversarial-loop-generator" -m "Merge generated KiCad project"   || echo "⚠️  Merge generator failed"
git merge --no-ff "../adversarial-loop-critic"    -m "Merge ERC review"              || echo "⚠️  Merge critic failed"
git merge --no-ff "../adversarial-loop-refine"    -m "Merge refined KiCad design"     || echo "⚠️  Merge refiner failed"

# Commit any outstanding changes (e.g. REVIEW.md updates)
git add .
git commit -m "Final adversarial-loop design – ERC passed" || echo "⚠️  Nothing new to commit"


#  To clean after a successful run:
# ./cleanup.sh