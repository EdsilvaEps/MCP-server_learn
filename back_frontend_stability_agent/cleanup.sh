#!/usr/bin/env bash
# cleanup.sh
# ---------------------------------------------------------
# Purpose:  Remove all work‑trees and temporary branches that
#           `adversarial_looper.sh` may have left behind.
# ---------------------------------------------------------

set -euo pipefail

# -----------------------------------------------------------------
# 1️⃣  Sanity check – must be inside a git repository
# -----------------------------------------------------------------
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "❌  Not inside a git repository – aborting."
    exit 1
fi

# -----------------------------------------------------------------
# 2️⃣  Define the names/paths that need removal
# -----------------------------------------------------------------
BRANCH="adversarial-loop"
WORKTREE_ROOT="$(pwd)"                # repository root

# Relative paths used by the original script
WT_GEN="${WORKTREE_ROOT}/../adversarial-loop-generator"
WT_CRITIC="${WORKTREE_ROOT}/../adversarial-loop-critic"
WT_REFINER="${WORKTREE_ROOT}/../adversarial-loop-refine"

# -----------------------------------------------------------------
# 3️⃣  Helper: safely remove a work‑tree (ignore errors if it does not exist)
# -----------------------------------------------------------------
remove_worktree() {
    local path="$1"
    if [ -d "$path" ]; then
        echo "🧹  Removing work‑tree at $path"
        git worktree remove "$path" --force || true
        # The directory may still be left behind on disk; clean it up
        rm -rf "$path"
    else
        echo "⚠️  Work‑tree $path not found – skipping."
    fi
}

# -----------------------------------------------------------------
# 4️⃣  Remove the three auxiliary work‑trees
# -----------------------------------------------------------------
remove_worktree "$WT_GEN"
remove_worktree "$WT_CRITIC"
remove_worktree "$WT_REFINER"

# -----------------------------------------------------------------
# 5️⃣  Delete the temporary branches (generator, critic, refiner, main loop)
# -----------------------------------------------------------------
for br in generator critic refiner "$BRANCH"; do
    if git show-ref --verify --quiet "refs/heads/$br"; then
        echo "🗑️  Deleting branch $br"
        git branch -D "$br" || true
    else
        echo "⚠️  Branch $br does not exist – skipping."
    fi
done

# -----------------------------------------------------------------
# 6️⃣  Return to the main branch (if it still exists)
# -----------------------------------------------------------------
if git show-ref --verify --quiet "refs/heads/main"; then
    echo "🔀  Switching back to main"
    git checkout main
else
    # Fallback: pick the first local branch that isn’t a temp one
    fallback="$(git branch --format='%(refname:short)' | grep -v -E 'generator|critic|refiner|adversarial-loop' | head -n1 || true)"
    if [ -n "$fallback" ]; then
        echo "🔀  Switching to $fallback (main not found)"
        git checkout "$fallback"
    else
        echo "⚠️  No non‑temporary branch left to checkout."
    fi
fi

# -----------------------------------------------------------------
# 7️⃣  Final tidy‑up – remove any stray empty directories created by the loops
# -----------------------------------------------------------------
for dir in "$WT_GEN" "$WT_CRITIC" "$WT_REFINER"; do
    if [ -d "$dir" ]; then
        echo "🧽  Removing leftover directory $dir"
        rm -rf "$dir"
    fi
done

echo "✅  Clean‑up complete."