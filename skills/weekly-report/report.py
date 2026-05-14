#!/usr/bin/env python3
"""Weekly report: 读最近 N 天 session,1 次 LLM 汇总 markdown。

Usage:
  python3 report.py             # 默认 7 天
  python3 report.py --days 14   # 最近 14 天
"""
import json, os, sys, time, datetime, urllib.request, glob

MIRROR_DIR = os.path.expanduser("~/.claude/mirror")
SEARCH_INDEX = os.path.join(MIRROR_DIR, "search-index.json")
SUMMARIES = os.path.join(MIRROR_DIR, "summaries.json")
REPORTS_DIR = os.path.join(MIRROR_DIR, "reports")
PROJECTS_BASE = os.path.expanduser("~/.claude/projects")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
TIMEOUT = 90


def get_deepseek_key():
    """fallback chain:env DEEPSEEK_API_KEY → ~/.deepseek。key 不进 commit。"""
    if k := os.environ.get("DEEPSEEK_API_KEY"):
        return k
    p = os.path.expanduser("~/.deepseek")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
        except Exception:
            pass
    return None


def collect_sessions(days):
    if not os.path.exists(SEARCH_INDEX):
        return None, f"{SEARCH_INDEX} 不存在,先跑 python3 ~/.claude/mirror/jsonl2html.py --all ~/.claude/mirror"
    with open(SEARCH_INDEX, encoding="utf-8") as f:
        index = json.load(f)
    summaries = {}
    if os.path.exists(SUMMARIES):
        try:
            with open(SUMMARIES, encoding="utf-8") as f:
                summaries = json.load(f)
        except Exception:
            pass
    # 扫所有 jsonl 拿 mtime
    jsonl_paths = {}
    for p in glob.glob(os.path.join(PROJECTS_BASE, "*", "*.jsonl")) + glob.glob(os.path.join(PROJECTS_BASE, "*.jsonl")):
        sid = os.path.basename(p).replace(".jsonl", "")
        jsonl_paths[sid] = p
    now = time.time()
    cutoff = now - days * 86400
    sessions = []
    for e in index:
        sid = e["sid"]
        jp = jsonl_paths.get(sid)
        if not jp:
            continue
        mt = os.path.getmtime(jp)
        if mt < cutoff:
            continue
        sm = summaries.get(sid, {})
        sessions.append({
            "sid": sid,
            "short": sid[:8],
            "mtime": datetime.datetime.fromtimestamp(mt).strftime("%m-%d %H:%M"),
            "mtime_ts": mt,
            "project": e.get("project", "—"),
            "tokens_total": (e.get("tokens") or {}).get("total", 0),
            "duration_min": e.get("duration_min", 0),
            "files": [f["path"] for f in (e.get("files") or [])[:5]],
            "commands": [c["cmd"] for c in (e.get("commands") or [])[:5]],
            "summary": (sm.get("summary") or "").strip(),
            "tags": sm.get("tags", []),
        })
    sessions.sort(key=lambda x: -x["mtime_ts"])
    return sessions, None


def fmt_tok(n):
    if n >= 1_000_000_000:
        return f"{n/1e9:.2f}B"
    if n >= 1_000_000:
        return f"{n/1e6:.1f}M"
    if n >= 1000:
        return f"{n/1e3:.1f}K"
    return str(n)


def fmt_dur(m):
    if m >= 60:
        h = m // 60
        rem = m % 60
        return f"{h}h{rem}m" if rem else f"{h}h"
    return f"{m}m"


def build_prompt(sessions, days):
    # Python 端先算好 ground truth, LLM 不要重新加
    total_tok = sum(s["tokens_total"] for s in sessions)
    total_min = sum(s["duration_min"] for s in sessions)
    n = max(len(sessions), 1)
    avg_tok = total_tok // n
    avg_min = total_min // n
    top3 = sorted(sessions, key=lambda s: -s["tokens_total"])[:3]
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days - 1)).strftime("%Y-%m-%d")

    head = [
        f"日期范围(请严格用这个,不要改年份):{start_date} ~ {today}",
        f"最近 {days} 天 {len(sessions)} 个 Claude Code session 元数据。",
        "",
        "## 统计数据(已 Python 端算好,LLM 请直接填表,不要重新计算)",
        f"- 总 token:{fmt_tok(total_tok)} (raw {total_tok:,})",
        f"- 总时长:{fmt_dur(total_min)} (raw {total_min}m)",
        f"- 单 session 平均:{fmt_tok(avg_tok)} tok / {fmt_dur(avg_min)}",
        "- 最贵 3 个:",
    ]
    for s in top3:
        head.append(f"  - {s['short']} ({s['mtime']}): {fmt_tok(s['tokens_total'])} tok / {fmt_dur(s['duration_min'])}")
    head.append("")
    head.append("## 各 session 详情")

    lines = head
    for s in sessions:
        warn = ""
        if s["tokens_total"] > 500_000_000 or s["duration_min"] > 1000:
            warn = " ⚠数据可疑"
        lines.append(f"\n## [{s['mtime']}] {s['short']} · {s['project']} · {fmt_tok(s['tokens_total'])} tok / {fmt_dur(s['duration_min'])}{warn}")
        if s["tags"]:
            lines.append(f"tags: {', '.join(s['tags'])}")
        if s["summary"]:
            lines.append(f"摘要: {s['summary']}")
        if s["files"]:
            lines.append(f"触及文件: {', '.join(os.path.basename(f) for f in s['files'])}")
        if s["commands"]:
            lines.append(f"命令: {' | '.join(c[:40] for c in s['commands'][:3])}")
    return "\n".join(lines)


SYSTEM_PROMPT = """你是 Daisy 的工作周报生成助手。基于多个 Claude Code session 元数据生成 markdown 周报。

重要:
- 日期范围严格用 user prompt 头部给的"日期范围",不要自己改年份(今年是 2026)
- 统计数据(总 token / 总时长 / 平均 / top3)已 Python 端算好,**直接填表,不要重新加 24 个数**
- session 行有 ⚠ 标记的代表数据可疑,不要把它当 top 推

输出结构(严格按下面 7 节):

# Daisy 工作周报 · YYYY-MM-DD ~ YYYY-MM-DD

## 1. 主要主题(3-6 大主题, 按 tag/项目聚类)
每个主题:**主题名** + 1 句话说明 + 涉及 session 数

## 2. 关键决策
3-8 条本周做出的具体决策(必须有"决策"性质, 不是"分析了 X"那种)。每条格式:
- **[mm-dd 短sid]** 决策内容(<= 30 字)

## 3. 触及项目
按项目分组:
- **项目名** (N session, X token):本周在该项目做了什么(1 句话)

## 4. 主要产出物
- 写过/改过的关键文件 top 5
- 跑过的关键命令 top 3
- 任何已上线/已交付的东西

## 5. Token / 时长统计
- 总 token / 总时长
- 单 session 平均
- 最贵的 3 个 session

## 6. 工作模式观察(主观点评 2-3 条)
- 本周主要节奏(冲刺?探索?重构?)
- 哪些事卡住(从摘要里识别"暂缓 / 待定 / 没收尾")
- 工作分布特征

## 7. 下周建议(2-3 条具体动作)
基于本周节奏给具体建议。

风格:
- plain modern 中文, 不要 emoji
- 时间戳 mm-dd HH:MM 纯数字
- 不写 "## 综上所述"
- 直接落点, 避免"讨论了 X / 分析了 Y"这种废话
- token 数字用 K/M/B 后缀, 不要 raw"""


def call_deepseek(prompt, key):
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 3500,
        "temperature": 0.4,
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"], data.get("usage", {})


def main():
    args = sys.argv[1:]
    days = 7
    if "--days" in args:
        i = args.index("--days")
        if i + 1 < len(args):
            try:
                days = int(args[i + 1])
            except Exception:
                pass

    sessions, err = collect_sessions(days)
    if err:
        print(f"ERR: {err}", file=sys.stderr)
        sys.exit(1)
    if not sessions:
        print(f"最近 {days} 天没有 session。")
        return

    key = get_deepseek_key()
    if not key:
        print("ERR: DEEPSEEK_API_KEY 找不到。export 或 echo sk-xxx > ~/.deepseek", file=sys.stderr)
        sys.exit(1)

    print(f"收集到最近 {days} 天 {len(sessions)} 个 session, 调 DeepSeek 生成周报...")
    prompt = build_prompt(sessions, days)

    t0 = time.time()
    try:
        report, usage = call_deepseek(prompt, key)
    except Exception as e:
        print(f"ERR: {e}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(REPORTS_DIR, exist_ok=True)
    fname = f"{datetime.datetime.now().strftime('%Y-%m-%d')}-{days}d-report.md"
    out_path = os.path.join(REPORTS_DIR, fname)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    dt = time.time() - t0
    tin = usage.get("prompt_tokens", 0)
    tout = usage.get("completion_tokens", 0)
    cost = tin * 0.0027 / 1000 + tout * 0.0011 / 1000
    print(f"\n完成。{dt:.1f}s · tok in={tin} out={tout} · ¥{cost:.3f}")
    print(f"报告: {out_path}")
    # 顺手用 md2html 渲染 + open
    md2html = os.path.expanduser("~/.claude/mirror/md2html.py")
    if os.path.exists(md2html):
        html_path = out_path.replace(".md", ".html")
        os.system(f'python3 "{md2html}" "{out_path}" "周报 {fname}" "{html_path}"')
        os.system(f'open "{html_path}"')
    else:
        os.system(f'open "{out_path}"')


if __name__ == "__main__":
    main()
