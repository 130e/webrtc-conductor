#!/usr/bin/env bash
set -euo pipefail

REMOTE_DUMP="$1"
DST_OUTPUT="$2"

matches=("$REMOTE_DUMP"/webrtc_receive_stream_*.ivf)

# No match
if [ ${#matches[@]} -eq 0 ] || [ ! -e "${matches[0]}" ]; then
    echo "Error: No .ivf files found in $REMOTE_DUMP" >&2
    exit 1
fi

# Multiple matches
if [ ${#matches[@]} -gt 1 ]; then
    echo "Error: Multiple .ivf files found in $REMOTE_DUMP: ${matches[*]}" >&2
    echo "Deleting all for clean rerun..." >&2
    rm -f "${matches[@]}"
    exit 2
fi

# Exactly one match
src="${matches[0]}"
dst="$DST_OUTPUT"
mv "$src" "$dst"
echo "Renamed $src -> $dst"
