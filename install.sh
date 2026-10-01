#!/usr/bin/env bash
# Install the skill into an agent skills directory.
#   ./install.sh                      -> ~/.workbuddy/skills/youtube-interview-digest
#   ./install.sh <skills-dir>         -> <skills-dir>/youtube-interview-digest
#   ./install.sh <skills-dir> --link  -> symlink instead of copy (for development)
set -euo pipefail
NAME=youtube-interview-digest
SRC="$(cd "$(dirname "$0")" && pwd)/skills/$NAME"
DEST_ROOT="${1:-$HOME/.workbuddy/skills}"
MODE="${2:-copy}"
mkdir -p "$DEST_ROOT"
DEST="$DEST_ROOT/$NAME"
if [ -e "$DEST" ] || [ -L "$DEST" ]; then
  BACKUP="$DEST.bak.$(date +%Y%m%d%H%M%S)"
  echo "• existing install found, moving it to $BACKUP"
  mv "$DEST" "$BACKUP"
fi
if [ "$MODE" = "--link" ]; then
  ln -s "$SRC" "$DEST"
else
  cp -R "$SRC" "$DEST"
  find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} +
fi
echo "✓ installed to $DEST"
PY="${PY:-python3}"
if "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
  "$PY" -c 'import yt_dlp, youtube_transcript_api' 2>/dev/null \
    && echo "✓ python deps already available ($("$PY" --version))" \
    || echo "→ install deps:  $PY -m pip install -r \"$DEST/requirements.txt\"   (a venv is recommended)"
else
  echo "! Python >= 3.10 required (found: $("$PY" --version 2>&1)). Set PY=/path/to/python3.x and re-run."
fi
