#!/usr/bin/env bash
# Fetch the public repositories used as benchmark corpora.
#
# Every corpus is a real AI codebase of the kind `aitrace scan` is pointed at in
# production, pinned to an exact commit so a benchmark run today is comparable
# to one from six months ago. Shallow single-commit clones — history is not
# scanned, so fetching it would only cost disk.
#
# Usage: benchmarks/fetch_corpora.sh [target-dir]   (default: benchmarks/corpora)

set -euo pipefail

TARGET_DIR="${1:-$(dirname "$0")/corpora}"
mkdir -p "$TARGET_DIR"

# name|url|pinned commit
CORPORA=(
  "dify|https://github.com/langgenius/dify.git|main"
  "langchain|https://github.com/langchain-ai/langchain.git|master"
  "haystack|https://github.com/deepset-ai/haystack.git|main"
  "crewai|https://github.com/crewAIInc/crewAI.git|main"
)

for entry in "${CORPORA[@]}"; do
  IFS='|' read -r name url ref <<< "$entry"
  dest="$TARGET_DIR/$name"

  if [ -d "$dest/.git" ]; then
    echo "== $name already present, skipping"
    continue
  fi

  echo "== cloning $name from $url ($ref)"
  git clone --depth 1 --branch "$ref" --single-branch "$url" "$dest"

  # Record the resolved commit so results are attributable to exact source.
  git -C "$dest" rev-parse HEAD > "$dest/.benchmark-commit"
  echo "   pinned at $(cat "$dest/.benchmark-commit")"
done

echo
echo "Corpora ready in $TARGET_DIR"
for entry in "${CORPORA[@]}"; do
  IFS='|' read -r name _ _ <<< "$entry"
  dest="$TARGET_DIR/$name"
  [ -d "$dest" ] || continue
  count=$(find "$dest" -type f \
    \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' \
       -o -name '*.jsx' -o -name '*.mjs' -o -name '*.cjs' \) \
    -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | wc -l | tr -d ' ')
  printf '  %-12s %s source files @ %s\n' "$name" "$count" "$(cut -c1-8 < "$dest/.benchmark-commit")"
done
