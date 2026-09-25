#!/usr/bin/env bash
# Safely delete fully-merged remote branches that are not:
#   - protected (main, master, develop, staging)
#   - archived namespaces (acceptance/, promotion/, release/, security/)
#   - the head of any open PR
#   - containing unmerged work (not an ancestor of origin/main)
#
# Usage:
#   bash scripts/cleanup_stale_branches.sh            # dry run
#   bash scripts/cleanup_stale_branches.sh --delete   # actually delete

set -euo pipefail

MODE="${1:-dry-run}"
REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
PROTECTED_EXACT="main master develop staging"
PROTECTED_PREFIX="acceptance/ promotion/ release/ security/"

echo "Repository: $REPO"
echo "Mode: $MODE"
echo

git fetch --prune origin >/dev/null

ALL_REMOTE=$(git branch -r --format='%(refname:short)' \
    | grep -vE '^origin(/HEAD)?$' \
    | sed 's|^origin/||' \
    | sort -u)

OPEN_PR_HEADS=$(gh pr list --state open --limit 500 \
    --json headRefName --jq '.[].headRefName' 2>/dev/null || true)

KEEP_FILE=$(mktemp)
DELETE_FILE=$(mktemp)
trap 'rm -f "$KEEP_FILE" "$DELETE_FILE"' EXIT

for b in $PROTECTED_EXACT; do echo "$b" >> "$KEEP_FILE"; done
printf '%s\n' "$OPEN_PR_HEADS" >> "$KEEP_FILE"

echo "Unmerged branches (kept):"
while IFS= read -r b; do
    [ -z "$b" ] && continue
    grep -qxF "$b" "$KEEP_FILE" && continue
    if ! git merge-base --is-ancestor "origin/$b" "origin/main" 2>/dev/null; then
        echo "$b" >> "$KEEP_FILE"
        echo "  - $b"
    fi
done <<< "$ALL_REMOTE"
echo

while IFS= read -r b; do
    [ -z "$b" ] && continue
    grep -qxF "$b" "$KEEP_FILE" && continue
    skip=0
    for p in $PROTECTED_PREFIX; do
        case "$b" in "$p"*) skip=1 ;; esac
    done
    [ "$skip" -eq 1 ] && continue
    echo "$b" >> "$DELETE_FILE"
done <<< "$ALL_REMOTE"

sort -u "$KEEP_FILE" -o "$KEEP_FILE"
sort -u "$DELETE_FILE" -o "$DELETE_FILE"

TOTAL=$(printf '%s\n' "$ALL_REMOTE" | grep -c . || true)
KEEP_COUNT=$(grep -c . "$KEEP_FILE" || true)
DELETE_COUNT=$(grep -c . "$DELETE_FILE" || true)

echo "==================================================="
echo "Summary"
echo "==================================================="
echo "Total remote branches: $TOTAL"
echo "Will keep:             $KEEP_COUNT"
echo "Will delete:           $DELETE_COUNT"
echo

if [ "$DELETE_COUNT" -eq 0 ]; then
    echo "Nothing to delete."
    exit 0
fi

echo "Branches slated for deletion:"
sed 's/^/  - /' "$DELETE_FILE"
echo

if [ "$MODE" != "--delete" ]; then
    echo "DRY RUN — nothing was deleted."
    echo "Re-run with --delete to actually delete."
    exit 0
fi

read -r -p "Delete $DELETE_COUNT remote branches? Type 'yes' to confirm: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

FAILED=""
while IFS= read -r b; do
    [ -z "$b" ] && continue
    echo "Deleting $b ..."
    if git push origin --delete "$b" 2>&1 | grep -q 'deleted'; then
        echo "  ok"
    else
        echo "  FAILED"
        FAILED="${FAILED}${b}"$'\n'
    fi
done < "$DELETE_FILE"

echo
echo "==================================================="
if [ -z "$FAILED" ]; then
    echo "All branches deleted cleanly."
else
    echo "Some branches failed to delete:"
    printf '%s\n' "$FAILED" | sed 's/^/  - /'
fi
