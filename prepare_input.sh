#!/usr/bin/env bash
# Clones nats-server and copies relevant .go source files into graphrag/input/
# Each file gets a header comment so GraphRAG knows its path context.

set -e

REPO_URL="https://github.com/nats-io/nats-server"
CLONE_DIR="/tmp/nats-server"
INPUT_DIR="$(dirname "$0")/graphrag/input"

echo "Cloning NATS server (shallow)..."
if [ -d "$CLONE_DIR" ]; then
  echo "  Already cloned, skipping."
else
  git clone --depth=1 "$REPO_URL" "$CLONE_DIR"
fi

mkdir -p "$INPUT_DIR"

# Key packages for pub/sub triage: server core, client handling, JetStream,
# authentication, logging, clustering. Skip generated, vendor, and test files.
INCLUDE_DIRS=(
  "server"
  "logger"
)

echo "Copying relevant .go files to $INPUT_DIR..."
count=0

for dir in "${INCLUDE_DIRS[@]}"; do
  # maxdepth 1 - we don't look too deep. Can remove this if necessary
  find "$CLONE_DIR/$dir" -maxdepth 1 -name "*.go" \
    ! -name "*_test.go" \
    ! -name "*.pb.go" | while read -r src; do

    filename=$(basename "$src")
    dest="$INPUT_DIR/${dir}_${filename%.go}.txt"

    # Prepend file path as context for the LLM
    {
      echo "=== FILE: $dir/$filename ==="
      echo ""
      cat "$src"
    } > "$dest"

    echo "  + $dir/$filename"
    count=$((count + 1))
  done
done

# Also grab the top-level README for conceptual context
if [ -f "$CLONE_DIR/README.md" ]; then
  cp "$CLONE_DIR/README.md" "$INPUT_DIR/README.txt"
  echo "  + README.md"
fi

echo ""
echo "Done. Files written to: $INPUT_DIR"
echo "Next steps:"
echo "  cd graphrag"
echo "  graphrag prompt-tune --root . --domain \"pub/sub messaging system source code\" --language English"
