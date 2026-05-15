#!/bin/bash
# mirror-viewer 一键安装脚本
# 把 viewer 主体 + skills 都放到 ~/.claude/ 标准位置
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
MIRROR_DIR="$HOME/.claude/mirror"
SKILLS_DIR="$HOME/.claude/skills"

echo "==> mirror-viewer 一键安装"
echo "    源:$REPO_DIR"
echo ""

# 1. mirror 主体到 ~/.claude/mirror
echo "[1/3] 装 viewer 主体到 $MIRROR_DIR"
mkdir -p "$MIRROR_DIR"
cp "$REPO_DIR/jsonl2html.py" "$MIRROR_DIR/"
cp "$REPO_DIR/md2html.py" "$MIRROR_DIR/"
echo "      ✓ jsonl2html.py / md2html.py"

# 2. skills 到 ~/.claude/skills
echo "[2/3] 装 skills 到 $SKILLS_DIR"
mkdir -p "$SKILLS_DIR"
if [ -d "$REPO_DIR/skills/summarize-sessions" ]; then
  cp -r "$REPO_DIR/skills/summarize-sessions" "$SKILLS_DIR/"
  echo "      ✓ summarize-sessions"
fi
if [ -d "$REPO_DIR/skills/weekly-report" ]; then
  cp -r "$REPO_DIR/skills/weekly-report" "$SKILLS_DIR/"
  echo "      ✓ weekly-report"
fi

# 3. hooks 路径提示
echo "[3/3] hooks 配置(手动)"
echo "      把以下加到 ~/.claude/settings.json 的 hooks 字段:"
echo ""
echo '      "Stop": [{ "hooks": [{ "type": "command", "command": "python3 '$MIRROR_DIR'/jsonl2html.py --all '$MIRROR_DIR' 2>/dev/null &" }] }]'
echo '      "SessionEnd": [{ "hooks": [{ "type": "command", "command": "python3 '$REPO_DIR'/hooks/mark-session-closed.py" }] }]'
echo ""

echo "==> 完成"
echo ""
echo "下一步:"
echo ""
echo "  # 1. 配 DeepSeek API key(skills 用,可选)"
echo "  echo 'sk-xxx' > ~/.deepseek"
echo ""
echo "  # 2. 一次性渲染历史 session"
echo "  python3 $MIRROR_DIR/jsonl2html.py --all $MIRROR_DIR"
echo ""
echo "  # 3. 打开主页"
echo "  open $MIRROR_DIR/index.html"
echo ""
echo "  # 4. (可选)跑摘要"
echo "  python3 $SKILLS_DIR/summarize-sessions/summarize.py"
echo ""
echo "  # 5. (可选)跑周报"
echo "  python3 $SKILLS_DIR/weekly-report/report.py"
