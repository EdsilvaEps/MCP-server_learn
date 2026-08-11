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
# 2️⃣  Helper: start a Hermes process in background and
#    remember its session id (used by `process` later)
# ---------------------------------------------------------
start_hermes() {
    echo "🚀  Starting Hermes for worktree with prompt: $2"
    # $1 = worktree name, $2 = prompt (quoted)
    local wt="$1" prompt="$2"
    # `--continue` tells the new process to inherit the current session’s
    # chat history (so we can keep feeding it new prompts later).
    # `--worktree "$wt"` creates a dedicated git work‑tree.
    # We ask Hermes to run *chat* with a *single* query and then exit
    # (the `-q` shortcut).  The process will terminate when the answer
    # is printed.
    hermes \
    #    -w "$wt" \
        --worktree \
        chat -q \
        --continue \
        "$prompt" &
    echo "$!"   # PID of the background hermes process
}

# ---------------------------------------------------------
# 3️⃣  First iteration – generate the file
# ---------------------------------------------------------
echo "📝  Generating test/feature.py"
GEN_PID=$(start_hermes \
    "adversarial-loop-generator" \
    "Generate a new Python module \`test/feature.py\` that defines a class \`Feature\` with a \`run()\` method. Do not import anything external." )
# Wait for it to finish and capture its output
GEN_OUT=$(process action=wait session_id="$GEN_PID" timeout=30 | jq -r '.output')
echo "🟢 Generator output:"
echo "$GEN_OUT"

# ---------------------------------------------------------
# 4️⃣  Function: run the critic on the generated file
# ---------------------------------------------------------
run_critic() {
    local crit_pid
    crit_pid=$(start_hermes \
        "adversarial-loop-critic" \
        "Read \`test/feature.py\`. List any PEP‑8 style problems, missing doc‑strings, or failing unit‑tests. Output a plain‑text report. If everything passes, just output the word \`OK\`.")
    process action=wait session_id="$crit_pid" timeout=30 | jq -r '.output'
}

# ---------------------------------------------------------
# 5️⃣  Function: run the refiner with a given report
# ---------------------------------------------------------
run_refiner() {
    local report="$1"
    local ref_pid
    ref_pid=$(start_hermes \
        "adversarial-loop-refine" \
        "Fix the issues reported below in \`test/feature.py\`. Do not change the public API, only address style, doc‑strings, or bugs.\n\n---\n$report")
    process action=wait session_id="$ref_pid" timeout=30 | jq -r '.output'
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