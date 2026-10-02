#!/usr/bin/env bash
# Install the skill into an agent skills directory.
#   ./install.sh                      -> auto-detected skills dir (see below)
#   ./install.sh <skills-dir>         -> <skills-dir>/youtube-interview-digest
#   ./install.sh <skills-dir> --link  -> symlink instead of copy (for development)
#
# 未显式指定目录时的解析顺序：
#   1) 环境变量 $SKILLS_DIR
#   2) 自动探测 $HOME 下一级隐藏目录里的 skills/（如 ~/.claude/skills、~/.codex/skills…）
#      探测到多个时取排序后的第一个，并打印全部候选
#   3) 都没探测到 -> ~/.agent-skills
set -euo pipefail
NAME=youtube-interview-digest
SRC="$(cd "$(dirname "$0")" && pwd)/skills/$NAME"
DEST_ROOT="${1:-${SKILLS_DIR:-}}"
MODE="${2:-copy}"

if [ -z "$DEST_ROOT" ]; then
  found=()
  for d in "$HOME"/.*/skills; do
    if [ -d "$d" ]; then found+=("$d"); fi
  done
  if [ "${#found[@]}" -gt 0 ]; then
    DEST_ROOT="${found[0]}"
    if [ "${#found[@]}" -gt 1 ]; then
      echo "• detected ${#found[@]} skills dirs: ${found[*]}"
      echo "• using $DEST_ROOT (pass an explicit dir to override)"
    fi
  else
    DEST_ROOT="$HOME/.agent-skills"
  fi
fi

echo "• target: $DEST_ROOT"
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
