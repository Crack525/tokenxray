#!/bin/bash
# Record tokenxray demo GIFs.
# Usage: bash demo/record.sh [cli|session|all]
# Requires: vhs (brew install vhs)

set -e
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEMO_DIR="$REPO_DIR/demo"

target="${1:-all}"

record() {
    local tape="$1"
    local name="$(basename "$tape" .tape)"
    local tmp="$(mktemp /tmp/tokenxray-$name-XXXXXX.tape)"

    echo "Recording $name..."
    sed "s|__DEMO_DIR__|$DEMO_DIR|g" "$tape" > "$tmp"
    cd "$REPO_DIR"
    vhs "$tmp"
    rm "$tmp"
    echo "  -> demo/$name.gif"
}

# Ensure mock data exists
python3 "$DEMO_DIR/setup_mock.py" --home "$DEMO_DIR/home" > /dev/null

if [ "$target" = "cli" ] || [ "$target" = "all" ]; then
    record "$DEMO_DIR/demo.tape"
fi

if [ "$target" = "session" ] || [ "$target" = "all" ]; then
    record "$DEMO_DIR/demo-session.tape"
fi

echo "Done."
