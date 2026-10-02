#!/usr/bin/env bash
# local_fetch.sh — 在本机（正常 IP + 已登录 Chrome）一次性抓取 YouTube 访谈的全部数据 + 字幕，
# 用于绕过 agent / 沙箱的云 IP 被 YouTube 防爬（RequestBlocked / page needs to be reloaded）的问题。
#
# 用法：
#   ./local_fetch.sh "<YouTube URL>" [输出目录，默认 ~/yt_<videoId>]
#
# 它会用本机已登录 Chrome 的 cookie（--cookies-from-browser chrome，无需手动导出），
# 一次拿到 meta / heatmap / comments / transcript，输出到指定目录并打印路径。
# 跑完后把输出目录路径发回 agent，即可继续翻译 / 解构 / 渲染。
#
# 注意：只有"抓取"这一步需要访问 YouTube；翻译 / 分析信号 / 解构 / 渲染都不需要联网，
# 所以你本机只跑这一条命令即可。

set -uo pipefail

if [ "$#" -lt 1 ]; then
  echo "用法: $0 \"<YouTube URL>\" [输出目录]" >&2
  exit 2
fi

URL="$1"
OUT="${2:-}"

# 定位脚本所在目录，从而找到 fetch_youtube.py（脚本在 skill 根目录时，fetch 在 ./scripts 下）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/scripts/fetch_youtube.py" ]; then
  FETCH="$SCRIPT_DIR/scripts/fetch_youtube.py"
elif [ -f "$SCRIPT_DIR/fetch_youtube.py" ]; then
  FETCH="$SCRIPT_DIR/fetch_youtube.py"
else
  echo "找不到 fetch_youtube.py（local_fetch.sh 应位于 skill 根目录或 scripts/ 内）" >&2
  exit 3
fi

# 优先用 WorkBuddy managed venv（已含 yt-dlp），否则回退到系统 python3
PY="$HOME/.workbuddy/binaries/python/envs/default/bin/python"
if [ ! -x "$PY" ]; then PY="python3"; fi

# 校验 yt-dlp 是否可用
if ! "$PY" -c "import yt_dlp" >/dev/null 2>&1; then
  echo "⚠️  $PY 未安装 yt-dlp，请先安装： $PY -m pip install -U yt-dlp" >&2
  exit 5
fi

# 从 URL 解析 videoId，用于默认输出目录命名
VID="$(echo "$URL" | sed -E 's@.*(v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11}).*@\2@')"
if [ -z "$VID" ]; then
  echo "无法从 URL 解析 11 位 videoId: $URL" >&2
  exit 4
fi

if [ -z "$OUT" ]; then OUT="$HOME/yt_$VID"; fi

echo "▶ Python : $PY"
echo "▶ 输出   : $OUT"
echo "▶ 请保持 Chrome 已登录并运行（用于读取 cookie）"
echo

set +e
"$PY" "$FETCH" "$URL" --out "$OUT" --max-comments 300 --cookies-from-browser chrome
RC=$?
set -e

echo
echo "============================================================"
if [ "$RC" -eq 0 ]; then
  echo "✅ 抓取成功（上方 subtitle_source 非 null 即已拿到字幕）"
elif [ "$RC" -eq 4 ]; then
  echo "⚠️  抓取完成，但字幕缺失（subtitle_source 为 null）——请检查上方日志"
else
  echo "⚠️  fetch_youtube.py 退出码 $RC，请检查上方日志"
fi
echo "➡️  把输出目录发回 agent 继续（翻译 / 解构 / 渲染）："
echo "   $OUT"
echo "============================================================"
