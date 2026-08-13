#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------
# 0️⃣  Sanity checks
# ---------------------------------------------------------
REPO_ROOT="$(pwd)"
BRANCH="adversarial-loop"
git rev-parse --is-inside-work-tree >/dev/null || {
    echo "❌ Not inside a git repo"
    exit 1
}
git checkout -b "$BRANCH"               # creates a fresh branch
#git status --short | grep . && {
#    echo "⚠️  Working tree not clean – commit or stash first"
#    exit 1
#}

# ---------------------------------------------------------
# 1️⃣  Create the folder the generator will write into
# ---------------------------------------------------------
#echo "📂  Creating test/ folder for generated code"
#mkdir -p test

# ---------------------------------------------------------
# 2️⃣  Helper: start hermes silently, capture output
# ---------------------------------------------------------
# Usage:
#   pid_and_file=$(start_hermes "your prompt")
#   # → "12345:/tmp/hermes-out-1689172345.txt"
#   IFS=: read -r HERMES_PID HERMES_LOG <<<"$pid_and_file"
#   wait "$HERMES_PID"            # blocks until the process ends
#   GEN_OUT=$(cat "$HERMES_LOG")  # everything the process printed
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
    hermes --worktree chat --continue -q "$prompt" \
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
# 3️⃣  First iteration – generate the file
# ---------------------------------------------------------
# ---- launch -------------------------------------------------
#GEN_INFO=$(start_hermes \
#    "Generate a new Python module \`test/feature.py\` that defines a class \`Feature\` with a \`run()\` method. Do not import anything external.")
#IFS=: read -r GEN_PID GEN_LOG <<<"$GEN_INFO"
start_hermes \
    "Generate a new Python module \`test/feature.py\` that defines a class \`Feature\` with a \`run()\` method. Do not import anything external."
GEN_PID="$HERMES_PID"
GEN_LOG="$HERMES_LOG"

# ---- wait & capture -----------------------------------------
wait "$GEN_PID"                     # block until hermes finishes
GEN_OUT=$(cat "$GEN_LOG")          # full stdout+stderr of the run
echo "🟢  Generator output:"
printf "%s\n" "$GEN_OUT"

# ---------------------------------------------------------
# 4️⃣  Function: run the critic on the generated file
# ---------------------------------------------------------
run_critic() {
    start_hermes \
        "Read \`test/feature.py\`. List any PEP‑8 style problems, missing doc‑strings, or failing unit‑tests. Output a plain‑text report. If everything passes, just output the word \`OK\`."
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
    CRITIC_OUT=$(run_critic)

    echo "$CRITIC_OUT"
    if [[ "$CRITIC_OUT" == *"OK"* ]]; then
        echo "✅  All checks passed on iteration $i"
        break
    fi

    echo "🛠️  Refiner pass #$i"
    REFINER_OUT=$(run_refiner "$CRITIC_OUT")
    echo "$REFINER_OUT"
done

# ---------------------------------------------------------
# 7️⃣  Inspect the final work‑tree (optional)
# ---------------------------------------------------------
echo "📂  Final file content (in worktree \`adversarial-loop-refine\`):"
git --work-tree="./.git/worktrees/adversarial-loop-refine" show HEAD:test/feature.py | cat

# ---------------------------------------------------------
# 8️⃣  Clean‑up helper (run manually if you want to discard)
# ---------------------------------------------------------
cleanup() {
    git worktree remove "./.git/worktrees/adversarial-loop-generator" --force
    git worktree remove "./.git/worktrees/adversarial-loop-critic"    --force
    git worktree remove "./.git/worktrees/adversarial-loop-refine"   --force
    git checkout main
    git branch -D "$BRANCH"
}
# Uncomment to auto‑remove the temporary work‑trees:
# cleanup