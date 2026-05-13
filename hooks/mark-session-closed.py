#!/usr/bin/env python3
"""SessionEnd hook helper. 从 stdin 读 session_id, 写到 ~/.claude/mirror/closed-sessions.json。
- atomic write(tmp + rename)避免并发损坏
- 报错打 stderr 让 hook log 可见
- 显式关文件句柄
"""
import json, sys, os, time

CLOSED_FILE = os.path.expanduser("~/.claude/mirror/closed-sessions.json")
TMP_FILE = CLOSED_FILE + ".tmp"

try:
    data = json.loads(sys.stdin.read())
    sid = data.get("session_id")
    if not sid:
        sys.exit(0)
    os.makedirs(os.path.dirname(CLOSED_FILE), exist_ok=True)
    closed = {}
    if os.path.exists(CLOSED_FILE):
        try:
            with open(CLOSED_FILE, encoding="utf-8") as f:
                closed = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[mark-session-closed] 读旧 closed-sessions 失败,重建: {e}", file=sys.stderr)
            closed = {}
    closed[sid] = int(time.time())
    # atomic: 写 tmp 再 rename(rename 是原子的)
    with open(TMP_FILE, "w", encoding="utf-8") as f:
        json.dump(closed, f, ensure_ascii=False)
    os.replace(TMP_FILE, CLOSED_FILE)
except Exception as e:
    print(f"[mark-session-closed] hook failed: {e}", file=sys.stderr)
    sys.exit(0)  # 不阻塞 SessionEnd
