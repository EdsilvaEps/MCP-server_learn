#!/usr/bin/env bash
set -euo pipefail

# hermes with branches and worktrees: https://hermes-agent.nousresearch.com/docs/user-guide/git-worktrees/ 

# ---------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------
REPO_ROOT="$(pwd)"
BRANCH="adversarial-loop"
git rev-parse --is-inside-work-tree >/dev/null || {
    echo "❌ Not inside a git repo"
    exit 1
}
git checkout -b "$BRANCH" || true               # creates a fresh branch

# -----------------------------------------------------------------
# Is the repo empty (no commits yet)?
# -----------------------------------------------------------------
if git rev-parse --verify HEAD >/dev/null 2>&1; then
    echo "✅ Repository already has commits – proceeding."
else
    echo "⚠️  Repository is empty – creating an initial empty commit."
    # Create an orphan branch (no parent) and add a dummy commit.
    # `--allow-empty` lets us commit without any files.
    git checkout --orphan "$BRANCH"
    git commit --allow-empty -m "Initial empty commit for $BRANCH"
fi


#---------------------------------------------------------
# Create worktrees for generator, critic, and refiner
#---------------------------------------------------------

git worktree add -b generator ../adversarial-loop-generator || true
git worktree add -b critic    ../adversarial-loop-critic    || true
git worktree add -b refiner     ../adversarial-loop-refine    || true


# ---------------------------------------------------------
# Helper: start hermes silently, capture output
# ---------------------------------------------------------
start_hermes() {
    # $1 = prompt string (quoted by the caller)
    local prompt="$1"

    # Create a unique log file for this run.
    #   -%s gives seconds since epoch → almost‑guaranteed unique.
    #   mktemp is safer than manually concatenating strings.
    local log_file
    log_file=$(mktemp "/tmp/hermes-out-$(date +%s)-XXXX.txt")

    printf "🚀 Starting Hermes (PID will appear after launch)…\n" >&2
    # Run hermes in the background, redirecting **both** streams to $log_file.
    # The trailing '&' puts it in background; $! captures its PID.
    #hermes --worktree chat --continue -q "$prompt" \ 

    hermes chat -q "$prompt" \
        >"$log_file" 2>&1 &
    local pid=$!

    export HERMES_PID="$pid"  # for debugging if you want to attach to it
    export HERMES_LOG="$log_file"  # for debugging if you want to inspect output

    # Disown so the shell won’t send SIGHUP if you later exit.
    #disown %${pid}

    # Return both pieces of info in a single “PID:logfile” string.
    printf "%s:%s" "$pid" "$log_file"
}

# ---------------------------------------------------------
# First iteration – generate the file
# ---------------------------------------------------------

cd "../adversarial-loop-generator" || exit 1
# ---- launch -------------------------------------------------
start_hermes \
    "Generate a new Python module \`test/feature.py\` that defines a class \`Feature\` with a \`run()\` method. Do not import anything external."
GEN_PID="$HERMES_PID"
GEN_LOG="$HERMES_LOG"

# ---- wait & capture -----------------------------------------
wait "$GEN_PID"                     # block until hermes finishes
GEN_OUT=$(cat "$GEN_LOG")          # full stdout+stderr of the run
echo "🟢  Generator output:"
printf "%s\n" "$GEN_OUT"

#-----Commit-----------------------------------------------------
git add test/feature.py
git commit -m "Initial generation of test/feature.py" || echo "⚠️  Nothing to commit"

# ---------------------------------------------------------
# Function: run the critic on the generated file
# ---------------------------------------------------------

run_critic() {
    start_hermes \
        "Read \`test/feature.py\`. List any PEP‑8 style problems, missing doc‑strings, or failing unit‑tests. Generate a markdown file REVIEW.md. If there aren't issues, just output the word \`OK\`."
    local pid="$HERMES_PID"
    local log="$HERMES_LOG"
    wait "$pid"    
    cat "$log"
}

# ---------------------------------------------------------
# 5️⃣  Function: run the refiner with a given report
# ---------------------------------------------------------
run_refiner() {
    local report="$1"
    start_hermes \
        "Fix the issues reported below in \`test/feature.py\`. Do not change the public API, only address style, doc‑strings, or bugs.\n\n---\n$report"
    local pid="$HERMES_PID"
    local log="$HERMES_LOG"
    wait "$pid"
    cat "$log"
}


# ---------------------------------------------------------
# 6️⃣  Iterative refinement loop (max 3 passes)
# ---------------------------------------------------------
MAX_ITER=3
for ((i=1; i<=MAX_ITER; i++)); do
    echo "🔎  Critic pass #$i"

    cd "../adversarial-loop-critic" || exit 1

    #-----sync the generated code into the critic worktree----------
    git fetch
    git merge generator --allow-unrelated-histories -m "Merge generated code for review" || echo "⚠️  Merge failed, continuing anyway"

    CRITIC_OUT=$(run_critic)
    echo "$CRITIC_OUT"

    if [[ "$CRITIC_OUT" == *"OK"* ]]; then
        echo "✅  All checks passed on iteration $i"
        break
    fi

    #-----Commit the critic's review--------------------------------
    git add .
    git commit -m "Sync generated code for review" || echo "⚠️  Nothing to commit"

    cd "../adversarial-loop-refine" || exit 1
    #-----sync the generated code into the refiner worktree----------
    git fetch
    git merge generator --allow-unrelated-histories -m "Merge generated code for refinement" || echo "⚠️  Merge failed, continuing anyway"

    echo "🛠️  Refiner pass #$i"
    REFINER_OUT=$(run_refiner "$CRITIC_OUT")
    echo "$REFINER_OUT"

    #-----Commit the refiner's changes--------------------------------
    git add test/feature.py
    git commit -m "Refined test/feature.py based on critic feedback" || echo "⚠️  Nothing to commit"
done

# ---------------------------------------------------------
# 7️⃣  Inspect the final work‑tree (optional)
# ---------------------------------------------------------

echo "📂  Final file content (in worktree \`adversarial-loop-refine\`):"
git --work-tree="../adversarial-loop-refine" show HEAD:test/feature.py | cat || true

# call the cleanup script afterwards
#bash cleanup.sh