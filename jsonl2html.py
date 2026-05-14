#!/usr/bin/env python3
"""Claude Code session mirror viewer.

Usage:
  python3 jsonl2html.py --latest <out_dir>       Hook 用:只渲染最新 session + 重建 index
  python3 jsonl2html.py --all <out_dir>          全量:渲染所有 session + index
  python3 jsonl2html.py <input.jsonl> <out.html> Legacy:单文件渲染
"""
import json, sys, html, datetime, os, glob, argparse, re

PROJECTS_BASE = os.path.expanduser("~/.claude/projects")
PROJECTS_DIR = PROJECTS_BASE  # legacy alias

WORKFLOW_PATTERNS = [
    {
        "id": "experiment",
        "name": "实验 / 跑批",
        "desc": "lab / experiment / 验证 / benchmark / eval",
        "file_re": [r"/lab/", r"/experiments?/", r"/eval/", r"\.prompt\.ya?ml$", r"\.eval\.", r"/benchmark", r"fixtures?/"],
        "cmd_re": [r"dump-", r"aggregate-", r"run-.*lab", r"^pytest .* -k ", r"^vitest --run", r"^bun .*bench"],
        "tag_keys": ["lab", "experiment", "实验", "验证", "eval", "benchmark", "ab-test", "对照"],
        "min_signals": 2,
    },
    {
        "id": "debug-fix",
        "name": "Debug / Bug fix",
        "desc": "复现 → 定位 → 修",
        "file_re": [r"BUG", r"TRACKER", r"\.test\.", r"\.spec\.", r"/tests?/", r"/__tests__/"],
        "cmd_re": [r"^git log", r"^git blame", r"^git bisect", r"^grep ", r"^rg ", r"^ag ", r"--debug"],
        "tag_keys": ["bug", "debug", "排查", "排错", "fix", "修复", "修", "排障", "故障", "错误", "issue", "regression", "error", "失败", "卡住", "弹窗", "卡顿"],
        "min_signals": 2,
    },
    {
        "id": "documentation",
        "name": "文档 / 设计",
        "desc": "写 doc / brief / spec / plan / readme",
        "file_re": [r"\.md$", r"\.mdx$", r"\.rst$", r"\.adoc$", r"/docs?/", r"README", r"BRIEF", r"DESIGN", r"SPEC", r"PLAN", r"PRD", r"RFC"],
        "cmd_re": [],
        "tag_keys": ["文档", "设计", "docs", "brief", "spec", "plan", "策划", "writeup", "readme", "prd", "rfc", "策划稿"],
        "min_signals": 1,
    },
    {
        "id": "implementation",
        "name": "实现编码",
        "desc": "写代码 / 跑 test / commit",
        "file_re": [r"\.(ts|tsx)$", r"\.(py|mjs)$", r"\.(js|jsx)$", r"\.(go|rs|java|kt)$", r"\.(rb|cpp|c|h|hpp)$", r"\.(html|css|scss|sql)$"],
        "cmd_re": [r"^npm test", r"^vitest", r"^pnpm test", r"^pytest", r"^cargo test", r"^go test", r"^mvn test", r"^make test", r"^git commit", r"^bun ", r"^python3? ", r"^node ", r"^cargo run", r"^go run"],
        "tag_keys": ["实现", "编码", "code", "implement", "上线", "落地", "P0", "P1", "refactor", "重构", "整合", "ship", "deploy"],
        "min_signals": 2,
    },
    {
        "id": "research",
        "name": "调研 / 决策",
        "desc": "竞品 / 市场 / NO-GO / 文献 / 选型",
        "file_re": [],
        "cmd_re": [],
        "tag_keys": ["调研", "research", "市场", "竞品", "NO-GO", "go-no-go", "决策", "decision", "转向", "市场定位", "选型", "对比", "evaluate", "trade-off"],
        "min_signals": 1,
    },
    {
        "id": "system-setup",
        "name": "环境 / 配置 / 工具",
        "desc": "settings / hook / 装包 / CI / 工具",
        "file_re": [r"\.claude/", r"settings\.json$", r"\.env", r"\.envrc$", r"package\.json$", r"requirements\.txt$", r"Cargo\.toml$", r"go\.mod$", r"Gemfile$", r"pyproject\.toml$", r"\.gitignore$", r"\.github/workflows", r"Dockerfile"],
        "cmd_re": [r"^brew install", r"^npm install", r"^pip install", r"^npx ", r"^pnpm install", r"^cargo install", r"^apt install", r"^yarn add", r"^bun install"],
        "tag_keys": ["配置", "config", "安装", "install", "setup", "hook", "skill", "工具", "tooling", "ci", "环境"],
        "min_signals": 1,
    },
    {
        "id": "project-audit",
        "name": "项目审计 / 架构可视化",
        "desc": "评价项目 / 画架构图 / 技术栈分析",
        "file_re": [r"-architecture\.html", r"ARCHITECTURE", r"-eval\.html"],
        "cmd_re": [r"^tree ", r"^find .* -type d", r"^cloc", r"^scc"],
        "tag_keys": ["架构", "architecture", "评价", "review", "技术栈", "stack", "audit", "可视化", "项目结构", "目录树", "structure"],
        "min_signals": 1,
    },
]


def match_workflows(r, summaries):
    """对单个 session row 匹配所有 pattern,返回 list of (pattern, signal_count)。"""
    import re as _re
    files_str = " ".join(f["path"] for f in (r.get("files") or []))
    cmds_str = " ".join(c["cmd"] for c in (r.get("commands") or []))
    tags = [t.lower() for t in (summaries.get(r["sid"], {}).get("tags", []) or []) if isinstance(t, str)]
    summary_text = (summaries.get(r["sid"], {}).get("summary") or "").lower()
    matches = []
    for p in WORKFLOW_PATTERNS:
        score = 0
        for pat in p["file_re"]:
            if _re.search(pat, files_str, _re.I): score += 1
        for pat in p["cmd_re"]:
            if _re.search(pat, cmds_str, _re.I): score += 1
        for kw in p["tag_keys"]:
            klow = kw.lower()
            if any(klow in t for t in tags) or klow in summary_text: score += 1
        if score >= p["min_signals"]:
            matches.append((p, score))
    matches.sort(key=lambda x: -x[1])
    return matches


FILE_TOOLS = {"Edit", "Write", "Read", "NotebookEdit", "MultiEdit"}

HOME = os.path.expanduser("~")


def derive_project(cwd):
    """通用项目名推导:cwd basename, ~ 根 → 'personal',Downloads → 取最后两层。"""
    if not cwd:
        return "—"
    cwd = cwd.rstrip("/")
    if cwd == HOME:
        return "personal"
    # ~/Downloads 下面常嵌套打包目录,取最后两层
    if cwd.startswith(os.path.join(HOME, "Downloads") + "/"):
        parts = cwd.split("/")
        last2 = "/".join(parts[-2:])
        return last2[:32]
    return os.path.basename(cwd) or "—"


def esc(s):
    return html.escape(s if isinstance(s, str) else json.dumps(s, ensure_ascii=False, indent=2))


def fmt_time(ts):
    if not ts: return ""
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
    except Exception:
        return ts


def fmt_mtime(path):
    try:
        ts = os.path.getmtime(path)
        return datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
    except Exception:
        return ""


def render_block(b):
    if isinstance(b, str):
        return f'<div class="md">{esc(b)}</div>'
    t = b.get("type")
    if t == "text":
        return f'<div class="md">{esc(b.get("text", ""))}</div>'
    if t == "thinking":
        return f'<details class="thinking"><summary>thinking</summary><pre>{esc(b.get("thinking", ""))}</pre></details>'
    if t == "tool_use":
        name = b.get("name", "?")
        inp = json.dumps(b.get("input", {}), ensure_ascii=False, indent=2)
        return f'<details class="tool-use"><summary>tool: {esc(name)}</summary><pre>{esc(inp)}</pre></details>'
    if t == "tool_result":
        c = b.get("content", "")
        if isinstance(c, list):
            c = "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in c)
        # 截断超长 tool_result(避免 HTML 爆炸到 19MB)
        MAX_RESULT_CHARS = 8000
        orig_len = len(c) if isinstance(c, str) else 0
        truncated = orig_len > MAX_RESULT_CHARS
        if truncated:
            c = c[:MAX_RESULT_CHARS] + f"\n\n... [截断 {orig_len - MAX_RESULT_CHARS:,} 字符,完整看 jsonl 原文]"
        err = " err" if b.get("is_error") else ""
        size_hint = f" · {orig_len:,} 字" if orig_len > 2000 else ""
        trunc_hint = " ⚠ 已截断" if truncated else ""
        return f'<details class="tool-result{err}"><summary>result{size_hint}{trunc_hint}</summary><pre>{esc(c)}</pre></details>'
    return f'<details><summary>{esc(t)}</summary><pre>{esc(b)}</pre></details>'


def render_msg(d, idx=0):
    role = d.get("type")
    if role not in ("user", "assistant"):
        return ""
    msg = d.get("message", {})
    content = msg.get("content", "")
    blocks = content if isinstance(content, list) else [content]
    body = "\n".join(render_block(b) for b in blocks)
    ts = fmt_time(d.get("timestamp", ""))
    model = msg.get("model", "") if role == "assistant" else ""
    head = f'<div class="head"><span class="role">{role}</span><span class="meta">{esc(model)} {ts}</span></div>'
    return f'<section class="msg {role}" id="msg-{idx}" data-idx="{idx}">{head}{body}</section>'


def parse_jsonl(jsonl_path):
    cards = []
    idx = 0
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            out = render_msg(d, idx=idx)
            if out:
                cards.append(out)
                idx += 1
    return cards


def parse_jsonl_for_metadata(jsonl_path):
    """抽 cwd / 项目 / 触及文件 / Bash 命令 / token 用量 / 时长 / subagent / skill 调用。零 token。"""
    cwd = None
    file_hits = {}
    cmd_hits = {}
    subagent_hits = {}
    skill_hits = {}
    tool_call_count = 0
    tok_input = tok_cache_create = tok_cache_read = tok_output = 0
    all_ts = []
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if not cwd and d.get("cwd"):
                    cwd = d.get("cwd")
                ts = d.get("timestamp")
                if ts:
                    all_ts.append(ts)
                msg = d.get("message", {})
                # 抽 user 消息里的 <command-name>/xxx</command-name>
                if d.get("type") == "user":
                    uc = msg.get("content", "")
                    if isinstance(uc, str):
                        for m in re.finditer(r"<command-name>/?([a-zA-Z][a-zA-Z0-9_-]+)</command-name>", uc):
                            cmd = m.group(1)
                            skill_hits[cmd] = skill_hits.get(cmd, 0) + 1
                if d.get("type") != "assistant":
                    continue
                u = msg.get("usage", {}) or {}
                tok_input += u.get("input_tokens", 0) or 0
                tok_cache_create += u.get("cache_creation_input_tokens", 0) or 0
                tok_cache_read += u.get("cache_read_input_tokens", 0) or 0
                tok_output += u.get("output_tokens", 0) or 0
                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    tool_call_count += 1
                    name = b.get("name", "")
                    inp = b.get("input", {}) or {}
                    if name in FILE_TOOLS:
                        p = inp.get("file_path") or inp.get("notebook_path") or ""
                        if p:
                            rec = file_hits.setdefault(p, {"tools": set(), "count": 0})
                            rec["tools"].add(name)
                            rec["count"] += 1
                    elif name == "Bash":
                        cmd = (inp.get("command") or "").strip()
                        if cmd:
                            head = cmd.split("\n", 1)[0][:80].strip()
                            # 过滤 heredoc 续行/单符号 noise(\, |, ;, &&, EOF 等)
                            if len(head) >= 2 and re.search(r"[A-Za-z]", head):
                                cmd_hits[head] = cmd_hits.get(head, 0) + 1
                    elif name in ("Task", "Agent"):
                        sub_type = inp.get("subagent_type") or "general-purpose"
                        desc = (inp.get("description") or "").strip()[:60]
                        rec = subagent_hits.setdefault(sub_type, {"count": 0, "examples": []})
                        rec["count"] += 1
                        if desc and len(rec["examples"]) < 3:
                            rec["examples"].append(desc)
    except Exception:
        pass
    # duration:同一个 sessionId 可跨多天 resume,所以不能用 last-first wall clock
    # 改成遍历相邻 ts,gap > 5min 不累加(代表 idle / 多天暂停),只算"活跃时长"
    duration_min = 0
    wall_min = 0
    IDLE_GAP_SEC = 300
    if all_ts:
        try:
            ts_sec = sorted(
                datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
                for t in all_ts
            )
            wall_min = int((ts_sec[-1] - ts_sec[0]) / 60)
            active_sec = 0
            for i in range(1, len(ts_sec)):
                gap = ts_sec[i] - ts_sec[i - 1]
                if gap <= IDLE_GAP_SEC:
                    active_sec += gap
            duration_min = int(active_sec / 60)
        except Exception:
            pass
    files = sorted(
        [{"path": p, "tools": sorted(v["tools"]), "count": v["count"]} for p, v in file_hits.items()],
        key=lambda x: -x["count"],
    )
    commands = sorted(
        [{"cmd": c, "count": n} for c, n in cmd_hits.items()],
        key=lambda x: -x["count"],
    )
    subagents = sorted(
        [{"type": t, "count": v["count"], "examples": v["examples"]} for t, v in subagent_hits.items()],
        key=lambda x: -x["count"],
    )
    skills = sorted(
        [{"name": n, "count": c} for n, c in skill_hits.items()],
        key=lambda x: -x["count"],
    )
    # total 只算真实出账(cache_read 是缓存命中字节数,不烧钱也不算工作量)
    total_tokens = tok_input + tok_cache_create + tok_output
    return {
        "cwd": cwd or "",
        "project": derive_project(cwd),
        "files": files,
        "commands": commands,
        "subagents": subagents,
        "skills": skills,
        "tool_calls": tool_call_count,
        "tokens": {
            "input": tok_input,
            "cache_create": tok_cache_create,
            "cache_read": tok_cache_read,
            "output": tok_output,
            "total": total_tokens,
        },
        "duration_min": duration_min,
        "wall_min": wall_min,
    }


def parse_jsonl_for_index(jsonl_path, max_text=800):
    items = []
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                t = d.get("type")
                if t not in ("user", "assistant"):
                    continue
                msg = d.get("message", {})
                content = msg.get("content", "")
                text = ""
                if isinstance(content, str):
                    stripped = content.strip()
                    if stripped.startswith("<system-reminder>") or stripped.startswith("<command-"):
                        continue
                    text = stripped
                elif isinstance(content, list):
                    parts = []
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "text":
                            parts.append(b.get("text", ""))
                    text = "\n".join(parts).strip()
                if not text:
                    continue
                items.append({
                    "role": t,
                    "text": text[:max_text],
                    "ts": d.get("timestamp", ""),
                })
    except Exception:
        pass
    return items


def session_meta(jsonl_path):
    msg_count = 0
    first_user = ""
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                t = d.get("type")
                if t in ("user", "assistant"):
                    msg_count += 1
                    if t == "user" and not first_user:
                        c = d.get("message", {}).get("content")
                        if isinstance(c, str):
                            stripped = c.strip()
                            if not stripped.startswith("<system-reminder>") and not stripped.startswith("<command-"):
                                first_user = stripped[:60].replace("\n", " ")
    except Exception:
        pass
    return msg_count, first_user


CSS = """
:root{color-scheme:light dark}
body{max-width:920px;margin:24px auto;padding:0 16px 80px;font:14px/1.55 -apple-system,BlinkMacSystemFont,'SF Pro Text',sans-serif;background:#fafaf8;color:#1a1a1a}
@media(prefers-color-scheme:dark){body{background:#1a1a1a;color:#eee}}
header.top{position:sticky;top:0;background:#fafaf8;padding:12px 0;margin-bottom:16px;border-bottom:1px solid #0001;z-index:10;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
@media(prefers-color-scheme:dark){header.top{background:#1a1a1a;border-bottom-color:#fff2}}
header.top a{color:#36c;text-decoration:none;font-size:13px}
header.top .meta-info{color:#888;font-size:12px;margin-left:auto}
input#search{flex:1;min-width:200px;padding:6px 10px;border:1px solid #0002;border-radius:6px;background:transparent;color:inherit;font-size:13px}
@media(prefers-color-scheme:dark){input#search{border-color:#fff3}}
.msg{margin:16px 0;padding:14px 18px;border-radius:10px;border:1px solid #0001}
@media(prefers-color-scheme:dark){.msg{border-color:#fff2}}
.user{background:#eef4ff}
@media(prefers-color-scheme:dark){.user{background:#1a2540}}
.assistant{background:#fff}
@media(prefers-color-scheme:dark){.assistant{background:#222}}
.head{display:flex;justify-content:space-between;font-size:12px;color:#888;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px}
.role{font-weight:600;color:#555}
@media(prefers-color-scheme:dark){.role{color:#bbb}}
.md{white-space:pre-wrap;word-wrap:break-word}
.md pre{background:#0001;padding:8px;border-radius:6px;overflow-x:auto;white-space:pre}
@media(prefers-color-scheme:dark){.md pre{background:#fff1}}
.md code{background:#0001;padding:1px 4px;border-radius:3px;font-size:13px}
@media(prefers-color-scheme:dark){.md code{background:#fff1}}
.md table{border-collapse:collapse;margin:8px 0}
.md td,.md th{border:1px solid #0002;padding:4px 8px}
details{margin:6px 0;border-left:3px solid #ccc;padding:4px 10px;background:#0001;border-radius:4px}
@media(prefers-color-scheme:dark){details{background:#fff1}}
details summary{cursor:pointer;font-size:12px;color:#666;font-family:ui-monospace,monospace}
@media(prefers-color-scheme:dark){details summary{color:#aaa}}
details pre{margin-top:8px;font-size:12px;white-space:pre-wrap;max-height:400px;overflow:auto}
.tool-use{border-left-color:#5a9}
.tool-result{border-left-color:#a85}
.tool-result.err{border-left-color:#e44}
.thinking{border-left-color:#a7c;opacity:0.7}
mark{background:#ff0;color:#000;padding:0 2px;border-radius:2px}
.msg.hidden{display:none}
.msg.msg-hidden{display:none}
.load-earlier-bar{position:sticky;top:60px;text-align:center;padding:12px;margin:10px 0;background:rgba(255,255,255,0.95);backdrop-filter:blur(6px);z-index:5;border-radius:8px;border:1px solid #0001}
@media(prefers-color-scheme:dark){.load-earlier-bar{background:rgba(30,30,30,0.95);border-color:#fff2}}
.load-earlier-btn{padding:8px 16px;font-size:13px;background:#36c;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:500;margin:0 4px}
.load-earlier-btn:hover{background:#258}
.load-all-btn{padding:8px 14px;font-size:12px;background:transparent;color:#36c;border:1px solid #36c;border-radius:6px;cursor:pointer;margin:0 4px}
.load-all-btn:hover{background:#36c;color:#fff}
table.sessions{width:100%;border-collapse:collapse;margin-top:8px}
table.sessions td,table.sessions th{padding:8px 12px;border-bottom:1px solid #0001;font-size:13px;text-align:left}
@media(prefers-color-scheme:dark){table.sessions td,table.sessions th{border-bottom-color:#fff2}}
table.sessions tr.active td{background:#fff8c4}
@media(prefers-color-scheme:dark){table.sessions tr.active td{background:#3a3520}}
table.sessions a{color:#36c;text-decoration:none}
table.sessions td.preview{max-width:480px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#666}
@media(prefers-color-scheme:dark){table.sessions td.preview{color:#aaa}}
table.sessions td.count{text-align:right;color:#888;font-variant-numeric:tabular-nums}
table.sessions td.time{color:#888;font-variant-numeric:tabular-nums;white-space:nowrap}
.refresh-indicator{position:fixed;bottom:14px;right:18px;font-size:13px;color:#fff;background:#36c;padding:8px 14px;border-radius:20px;border:none;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.15);font-weight:500;transition:all 0.15s}
.refresh-indicator:hover{background:#258;transform:scale(1.05)}
.refresh-indicator:active{transform:scale(0.95)}
button.refresh-indicator{font-family:inherit}
span.refresh-indicator{background:#aaa;cursor:default;color:#fff;font-size:11px;padding:3px 8px;font-weight:normal;box-shadow:none}
@media(prefers-color-scheme:dark){span.refresh-indicator{background:#555}}
.results-meta{color:#888;font-size:12px;margin-bottom:8px}
.session-result{margin:14px 0;padding:12px 14px;border:1px solid #0001;border-radius:8px;background:rgba(0,0,0,0.02)}
@media(prefers-color-scheme:dark){.session-result{border-color:#fff2;background:rgba(255,255,255,0.02)}}
.session-result-head{display:flex;justify-content:space-between;margin-bottom:8px;font-size:13px}
.session-result-head .meta{color:#888;font-size:12px}
.result-row{display:flex;gap:10px;padding:6px 8px;font-size:13px;color:inherit;text-decoration:none;border-radius:4px;align-items:flex-start}
.result-row:hover{background:#0001}
@media(prefers-color-scheme:dark){.result-row:hover{background:#fff1}}
.result-row .role{font-size:11px;color:#888;text-transform:uppercase;flex-shrink:0;width:60px;padding-top:2px}
.role-user{color:#36c}
.role-assistant{color:#787}
.result-row .snip{flex:1;line-height:1.5;word-break:break-word}
.more{font-size:12px;color:#888;padding:4px 8px}
.empty{padding:20px;text-align:center;color:#888}
.tabs{display:flex;gap:4px;margin-bottom:12px;border-bottom:1px solid #0001}
@media(prefers-color-scheme:dark){.tabs{border-bottom-color:#fff2}}
.tabs a{padding:8px 14px;text-decoration:none;color:#666;font-size:13px;border-bottom:2px solid transparent;margin-bottom:-1px}
.tabs a.active{color:#36c;border-bottom-color:#36c;font-weight:600}
@media(prefers-color-scheme:dark){.tabs a{color:#aaa}}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px 0}
.chip{padding:4px 10px;font-size:12px;border:1px solid #0002;border-radius:14px;cursor:pointer;color:#666;background:transparent;user-select:none}
@media(prefers-color-scheme:dark){.chip{border-color:#fff3;color:#bbb}}
.chip.active{background:#36c;color:#fff;border-color:#36c}
.chip .ct{opacity:0.6;margin-left:4px;font-variant-numeric:tabular-nums}
.session-meta-card{margin:12px 0 18px;padding:12px 16px;border:1px solid #0001;border-radius:8px;background:rgba(0,0,0,0.02);font-size:13px}
@media(prefers-color-scheme:dark){.session-meta-card{border-color:#fff2;background:rgba(255,255,255,0.02)}}
.session-meta-card .row{display:flex;gap:14px;flex-wrap:wrap;margin:4px 0;align-items:baseline}
.session-meta-card .label{color:#888;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;flex-shrink:0;width:64px}
.session-meta-card code{font-size:12px;background:#0001;padding:1px 6px;border-radius:3px;font-family:ui-monospace,monospace}
@media(prefers-color-scheme:dark){.session-meta-card code{background:#fff1}}
.session-meta-card details{margin:4px 0;border:none;background:transparent;padding:0}
.session-meta-card details summary{font-size:12px;color:#36c;cursor:pointer}
.session-meta-card details ul{margin:8px 0 0;padding-left:20px;font-size:12px;line-height:1.7;color:#555}
@media(prefers-color-scheme:dark){.session-meta-card details ul{color:#bbb}}
.session-meta-card .badge{display:inline-block;padding:2px 8px;font-size:11px;background:#36c;color:#fff;border-radius:10px;margin-right:6px}
table.sessions td.project{color:#36c;font-size:12px}
table.sessions td.num{text-align:right;color:#888;font-variant-numeric:tabular-nums;font-size:12px}
table.files{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed}
table.files th:nth-child(2),table.files td:nth-child(2),
table.files th:nth-child(3),table.files td:nth-child(3){width:72px}
table.files th:nth-child(4),table.files td:nth-child(4){width:36%}
table.files td,table.files th{padding:8px 12px;border-bottom:1px solid #0001;text-align:left;vertical-align:top}
@media(prefers-color-scheme:dark){table.files td,table.files th{border-bottom-color:#fff2}}
table.files td.fpath{font-family:ui-monospace,monospace;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
table.files td.fpath:hover{white-space:normal;word-break:break-all;background:rgba(0,0,0,0.02)}
@media(prefers-color-scheme:dark){table.files td.fpath:hover{background:rgba(255,255,255,0.03)}}
table.files td.sids{font-size:11px;line-height:1.6}
.sids-wrap{display:flex;flex-wrap:wrap;gap:4px}
table.files td.sids a{padding:1px 7px;border-radius:4px;background:rgba(54,98,204,0.10);color:#36c;text-decoration:none;letter-spacing:0.2px}
table.files td.sids a:hover{background:#36c;color:#fff}
@media(prefers-color-scheme:dark){table.files td.sids a{background:rgba(54,98,204,0.20);color:#9bf}}
.warn-long td{background:rgba(228,68,68,0.06)}
@media(prefers-color-scheme:dark){.warn-long td{background:rgba(228,68,68,0.12)}}
.warn-long td.count{color:#e44;font-weight:600}
.warn-mark{color:#e44;font-weight:600;margin-left:4px}
.chip.warn-chip{border-color:#e44;color:#e44}
.chip.warn-chip.active{background:#e44;color:#fff;border-color:#e44}
.badge.warn{background:#e44;margin-left:6px}
.tok-sub{color:#888;font-size:11px;margin-left:8px;font-family:ui-monospace,monospace}
.mermaid-rendered{margin:12px 0;padding:12px;background:rgba(0,0,0,0.02);border-radius:6px;overflow-x:auto;text-align:center}
@media(prefers-color-scheme:dark){.mermaid-rendered{background:rgba(255,255,255,0.04)}}
.mermaid-rendered svg{max-width:100%;height:auto}
.tag{display:inline-block;padding:2px 8px;font-size:11px;background:#e0e8f5;color:#36c;border-radius:10px;margin-right:4px;margin-bottom:2px}
@media(prefers-color-scheme:dark){.tag{background:#1a2540;color:#9bf}}
table.sessions td.summary{color:#222;font-size:13px;max-width:380px;line-height:1.5}
@media(prefers-color-scheme:dark){table.sessions td.summary{color:#ddd}}
table.sessions td.tags{font-size:11px;max-width:240px}
.summary-card{margin:12px 0;padding:14px 16px;border-left:4px solid #36c;background:rgba(54,98,204,0.06);border-radius:6px}
@media(prefers-color-scheme:dark){.summary-card{background:rgba(54,98,204,0.12)}}
.summary-card .summary-text{font-size:14px;font-weight:500;line-height:1.5}
.summary-card .tag-row{margin-top:8px}
.status-active{display:inline-block;padding:1px 7px;font-size:10px;background:#3a3;color:#fff;border-radius:8px;margin-left:6px;font-weight:600;letter-spacing:0.5px}
.status-idle{display:inline-block;padding:1px 7px;font-size:10px;background:#c80;color:#fff;border-radius:8px;margin-left:6px;font-weight:500}
.status-closed{display:inline-block;padding:1px 7px;font-size:10px;background:#aaa;color:#fff;border-radius:8px;margin-left:6px;opacity:0.7}
@media(prefers-color-scheme:dark){.status-closed{background:#555}}
.chip.live-chip{border-color:#3a3;color:#3a3}
.chip.live-chip.active{background:#3a3;color:#fff;border-color:#3a3}
.chip.idle-chip{border-color:#c80;color:#c80}
.chip.idle-chip.active{background:#c80;color:#fff;border-color:#c80}
.detail-btn{padding:5px 12px;font-size:12px;background:#36c;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:500;margin-left:8px}
.detail-btn:hover{background:#258}
.detail-panel{margin:12px 0 20px;padding:16px;border:1px solid #36c;border-radius:8px;background:rgba(54,98,204,0.04)}
@media(prefers-color-scheme:dark){.detail-panel{background:rgba(54,98,204,0.10)}}
.outline-meta{color:#888;font-size:11px;margin-bottom:12px;border-bottom:1px solid #0001;padding-bottom:8px}
.outline-item{margin:14px 0;padding:10px 12px;border-left:3px solid #36c;background:rgba(0,0,0,0.02);border-radius:0 6px 6px 0}
@media(prefers-color-scheme:dark){.outline-item{background:rgba(255,255,255,0.04)}}
.outline-head{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.outline-head strong{font-size:14px}
.outline-jump{font-size:11px;color:#36c;text-decoration:none;padding:2px 8px;background:rgba(54,98,204,0.10);border-radius:4px;font-family:ui-monospace,monospace}
.outline-jump:hover{background:#36c;color:#fff}
.outline-summary{font-size:13px;line-height:1.6;margin-bottom:6px}
.outline-keys{margin:6px 0 0;padding-left:20px;font-size:12px;line-height:1.7;color:#666}
@media(prefers-color-scheme:dark){.outline-keys{color:#aaa}}
.msg:target{outline:3px solid #36c;outline-offset:4px;scroll-margin-top:80px}
.pattern-section{margin:24px 0;padding:16px 18px;border:1px solid #0001;border-radius:8px;background:rgba(0,0,0,0.02)}
@media(prefers-color-scheme:dark){.pattern-section{border-color:#fff2;background:rgba(255,255,255,0.02)}}
.pattern-section h3{margin:0 0 4px;font-size:15px;display:flex;align-items:center;gap:10px}
.pattern-count{font-size:12px;color:#fff;background:#36c;padding:2px 8px;border-radius:10px;font-weight:500}
.pattern-desc{font-size:12px;color:#888;margin:0 0 12px}
.more td{color:#888;font-size:12px;text-align:center;padding:8px}
.pattern-meta{margin:8px 0 12px;font-size:12px}
.pattern-meta-row{margin:4px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.pattern-meta .label{color:#888;width:64px;font-size:11px;flex-shrink:0}
.tag-chips-wrap{margin:-6px 0 14px;padding-top:0;max-height:96px;overflow-y:auto;border-bottom:1px dashed #0001;padding-bottom:8px}
@media(prefers-color-scheme:dark){.tag-chips-wrap{border-bottom-color:#fff2}}
.chip.tag-chip{padding:2px 8px;font-size:11px;border-radius:11px;background:transparent}
.chip.tag-chip.active{background:#36c;color:#fff;border-color:#36c}
.tag-clickable{cursor:pointer;user-select:none}
.tag-clickable:hover{background:#cdd9f0;color:#36c}
@media(prefers-color-scheme:dark){.tag-clickable:hover{background:#234070;color:#9bf}}
"""

INDEX_JS = """
const data = JSON.parse(document.getElementById('search-data').textContent);
const input = document.getElementById('global-search');
const resultsWrap = document.getElementById('results-wrap');
const resultsEl = document.getElementById('results');
const resultsMeta = document.getElementById('results-meta');
const tableEl = document.getElementById('session-table');

function esc(s) { return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function snippet(text, terms) {
  const lower = text.toLowerCase();
  let pos = -1;
  for (const t of terms) { const p = lower.indexOf(t); if (p >= 0 && (pos < 0 || p < pos)) pos = p; }
  if (pos < 0) pos = 0;
  const start = Math.max(0, pos - 40);
  const end = Math.min(text.length, pos + 120);
  let snip = text.slice(start, end);
  if (start > 0) snip = '…' + snip;
  if (end < text.length) snip += '…';
  const re = new RegExp('(' + terms.map(t => t.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')).join('|') + ')', 'gi');
  return esc(snip).replace(re, '<mark>$1</mark>');
}

function doSearch(q) {
  const terms = q.toLowerCase().trim().split(/\\s+/).filter(Boolean);
  if (!terms.length) {
    resultsWrap.style.display = 'none';
    tableEl.style.display = '';
    return;
  }
  tableEl.style.display = 'none';
  resultsWrap.style.display = '';
  const hits = [];
  let total = 0;
  for (const session of data) {
    const matches = [];
    for (const m of session.msgs) {
      const txt = m.text.toLowerCase();
      if (terms.every(t => txt.includes(t))) matches.push(m);
    }
    if (matches.length) { hits.push({session, matches}); total += matches.length; }
  }
  resultsMeta.textContent = hits.length + ' 个 session 命中, 共 ' + total + ' 条匹配';
  const qp = encodeURIComponent(q);
  resultsEl.innerHTML = hits.map(h => {
    const head = '<div class="session-result-head"><a href="' + esc(h.session.sid) + '.html#q=' + qp + '"><strong>' + esc(h.session.sid.slice(0,8)) + '</strong></a><span class="meta">' + esc(h.session.mtime_str) + ' · ' + h.matches.length + ' 条匹配</span></div>';
    const rows = h.matches.slice(0, 3).map(m =>
      '<a class="result-row" href="' + esc(h.session.sid) + '.html#q=' + qp + '">'
      + '<span class="role role-' + m.role + '">' + m.role + '</span>'
      + '<span class="snip">' + snippet(m.text, terms) + '</span>'
      + '</a>'
    ).join('');
    const more = h.matches.length > 3 ? '<div class="more">+ ' + (h.matches.length - 3) + ' 条更多,进入 session 查看</div>' : '';
    return '<div class="session-result">' + head + rows + more + '</div>';
  }).join('') || '<div class="empty">没有匹配</div>';
}

function readHash() { const m = location.hash.match(/q=([^&]*)/); return m ? decodeURIComponent(m[1]) : ''; }
function writeHash(q) { if (q) history.replaceState(null, '', '#q=' + encodeURIComponent(q)); else history.replaceState(null, '', location.pathname); }

const chipsWrap = document.getElementById('chips-wrap');
const tagChipsWrap = document.getElementById('tag-chips-wrap');
const sessionRows = Array.from(document.querySelectorAll('#session-table tbody tr.srow'));
let activeProject = '';
let activeTag = '';

function applyFilters() {
  for (const r of sessionRows) {
    let show = true;
    if (activeProject === '__long__') show = show && r.dataset.long === '1';
    else if (activeProject === '__active__') show = show && r.dataset.status === 'active';
    else if (activeProject === '__idle__') show = show && r.dataset.status === 'idle';
    else if (activeProject === '__closed__') show = show && r.dataset.status === 'closed';
    else if (activeProject) show = show && r.dataset.project === activeProject;
    if (activeTag) {
      const tags = (r.dataset.tags || '').split(',');
      show = show && tags.includes(activeTag);
    }
    r.style.display = show ? '' : 'none';
  }
}

function syncFilterUI() {
  if (chipsWrap) chipsWrap.querySelectorAll('.chip').forEach(c => {
    c.classList.toggle('active', (c.dataset.project || '') === activeProject);
  });
  if (tagChipsWrap) tagChipsWrap.querySelectorAll('.chip').forEach(c => {
    c.classList.toggle('active', (c.dataset.tag || '') === activeTag);
  });
}

function readFilterHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  activeProject = params.get('proj') || '';
  activeTag = (params.get('tag') || '').toLowerCase();
}
function writeFilterHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  if (activeProject) params.set('proj', activeProject); else params.delete('proj');
  if (activeTag) params.set('tag', activeTag); else params.delete('tag');
  const s = params.toString();
  history.replaceState(null, '', s ? '#' + s : location.pathname);
}

if (chipsWrap) {
  chipsWrap.addEventListener('click', e => {
    const btn = e.target.closest('.chip');
    if (!btn) return;
    activeProject = btn.dataset.project;
    syncFilterUI();
    applyFilters();
    writeFilterHash();
  });
}
if (tagChipsWrap) {
  tagChipsWrap.addEventListener('click', e => {
    const btn = e.target.closest('.chip');
    if (!btn) return;
    activeTag = btn.dataset.tag || '';
    syncFilterUI();
    applyFilters();
    writeFilterHash();
  });
}
// 点表格里的 tag chip 也触发 filter
document.querySelectorAll('#session-table .tag-clickable').forEach(el => {
  el.addEventListener('click', e => {
    e.preventDefault();
    activeTag = el.dataset.tag || '';
    syncFilterUI();
    applyFilters();
    writeFilterHash();
    window.scrollTo(0, 0);
  });
});
// 初始从 hash 读
readFilterHash();
syncFilterUI();
applyFilters();

const q0 = readHash();
if (q0) { input.value = q0; doSearch(q0); }
input.addEventListener('input', () => { doSearch(input.value); writeHash(input.value); });
"""

SEARCH_JS = """
const search = document.getElementById('search');
const msgs = Array.from(document.querySelectorAll('.msg'));
const indicator = document.getElementById('refresh-indicator');
let refreshTimer = null;
let paused = false;

function highlight(el, terms) {
  // 还原原文(去掉旧 mark),只对纯 text 节点重新匹配
  el.querySelectorAll('mark').forEach(m => {
    const tn = document.createTextNode(m.textContent);
    m.replaceWith(tn);
  });
  if (!terms.length) return;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
  const texts = [];
  let n;
  while ((n = walker.nextNode())) {
    if (n.parentElement.closest('script,style,.head')) continue;
    texts.push(n);
  }
  const re = new RegExp('(' + terms.map(t => t.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')).join('|') + ')', 'gi');
  for (const node of texts) {
    if (!re.test(node.nodeValue)) { re.lastIndex = 0; continue; }
    re.lastIndex = 0;
    const span = document.createElement('span');
    span.innerHTML = esc(node.nodeValue).replace(re, '<mark>$1</mark>');
    node.replaceWith(span);
  }
}

function esc(s) { return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function applyFilter(q) {
  const terms = q.trim().split(/\\s+/).filter(Boolean).map(t => t.toLowerCase());
  for (const m of msgs) {
    const txt = m.textContent.toLowerCase();
    const match = terms.length === 0 || terms.every(t => txt.includes(t));
    m.classList.toggle('hidden', !match);
    if (match) highlight(m, terms);
  }
}

function readHash() {
  const m = location.hash.match(/q=([^&]*)/);
  return m ? decodeURIComponent(m[1]) : '';
}

function writeHash(q) {
  if (q) history.replaceState(null, '', '#q=' + encodeURIComponent(q));
  else history.replaceState(null, '', location.pathname);
}

// 手动刷新:点 button 直接 reload。无自动定时。
function scheduleRefresh() { /* no-op, manual mode */ }
function pauseRefresh() { /* no-op */ }
function resumeRefresh() { /* no-op */ }
if (indicator && indicator.dataset.live && indicator.tagName === 'BUTTON') {
  indicator.addEventListener('click', () => location.reload());
}

if (search) {
  const q0 = readHash();
  if (q0) { search.value = q0; applyFilter(q0); pauseRefresh(); }
  search.addEventListener('input', () => {
    if (search.value) expandAllForSearch();  // 搜索时展开所有 hidden,否则搜不到
    applyFilter(search.value);
    writeHash(search.value);
    if (search.value) pauseRefresh(); else resumeRefresh();
  });
  search.addEventListener('focus', pauseRefresh);
  search.addEventListener('blur', () => { if (!search.value) resumeRefresh(); });
}

// markdown 渲染(异步分批 + 跳过 .msg-hidden 节省 CPU)
function renderMarkdown(els) {
  if (typeof marked === 'undefined' || typeof marked.parse !== 'function') {
    els.forEach(el => { if (!el.querySelector('pre,details')) el.style.whiteSpace = 'pre-wrap'; });
    return;
  }
  const BATCH = 25;
  let idx = 0;
  function renderMdBatch() {
    const end = Math.min(idx + BATCH, els.length);
    for (; idx < end; idx++) {
      const el = els[idx];
      try {
        if (!el.querySelector('pre,details')) el.innerHTML = marked.parse(el.textContent);
      } catch (e) { /* skip */ }
    }
    if (idx < els.length) requestAnimationFrame(renderMdBatch);
  }
  requestAnimationFrame(renderMdBatch);
}
// 初始只渲染可见 msg 的 .md
renderMarkdown(Array.from(document.querySelectorAll('.msg:not(.msg-hidden) .md')));

// 分页加载更早
const loadEarlierBtn = document.getElementById('load-earlier-btn');
const loadAllBtn = document.getElementById('load-all-btn');
const hiddenCountEl = document.getElementById('hidden-count');
function expandHidden(batch) {
  const hidden = Array.from(document.querySelectorAll('.msg.msg-hidden'));
  if (!hidden.length) return;
  const toShow = batch ? hidden.slice(-batch) : hidden;  // batch=null 时全展开
  const scrollAnchor = document.querySelector('.msg:not(.msg-hidden)');
  const anchorTop = scrollAnchor ? scrollAnchor.getBoundingClientRect().top : 0;
  toShow.forEach(m => m.classList.remove('msg-hidden'));
  // 渲染新展开的 md
  const newMds = [];
  toShow.forEach(m => m.querySelectorAll('.md').forEach(el => newMds.push(el)));
  renderMarkdown(newMds);
  // 更新按钮状态
  const remaining = document.querySelectorAll('.msg.msg-hidden').length;
  if (remaining === 0) {
    const bar = document.querySelector('.load-earlier-bar');
    if (bar) bar.remove();
  } else if (hiddenCountEl) {
    hiddenCountEl.textContent = remaining;
  }
  // 保持视觉锚点(scrollAnchor 仍在原 viewport 位置)
  if (scrollAnchor) {
    requestAnimationFrame(() => {
      const newTop = scrollAnchor.getBoundingClientRect().top;
      window.scrollBy(0, newTop - anchorTop);
    });
  }
}
if (loadEarlierBtn) loadEarlierBtn.addEventListener('click', () => expandHidden(500));
if (loadAllBtn) loadAllBtn.addEventListener('click', () => expandHidden(null));

// 搜索时自动展开全部(否则搜不到 hidden 内容)
function expandAllForSearch() {
  if (document.querySelector('.msg.msg-hidden')) expandHidden(null);
}

// 跳转锚点 #msg-N 时,确保该 msg 已展开
function ensureMsgVisible() {
  const m = location.hash.match(/^#msg-(\d+)$/);
  if (!m) return;
  const target = document.getElementById('msg-' + m[1]);
  if (target && target.classList.contains('msg-hidden')) {
    // 展开到该 msg
    const allMsgs = Array.from(document.querySelectorAll('.msg'));
    const tgtIdx = allMsgs.indexOf(target);
    if (tgtIdx >= 0) {
      const toExpand = allMsgs.slice(0, tgtIdx + 1).filter(x => x.classList.contains('msg-hidden'));
      toExpand.forEach(x => x.classList.remove('msg-hidden'));
      const newMds = [];
      toExpand.forEach(x => x.querySelectorAll('.md').forEach(el => newMds.push(el)));
      renderMarkdown(newMds);
      const remaining = document.querySelectorAll('.msg.msg-hidden').length;
      if (remaining === 0) {
        const bar = document.querySelector('.load-earlier-bar');
        if (bar) bar.remove();
      } else if (hiddenCountEl) hiddenCountEl.textContent = remaining;
      setTimeout(() => target.scrollIntoView({block: 'start', behavior: 'smooth'}), 50);
    }
  }
}
window.addEventListener('hashchange', ensureMsgVisible);
ensureMsgVisible();

// mermaid 渲染:扫 marked 输出的 mermaid code block,替换成 SVG
if (window.mermaid) {
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  mermaid.initialize({ startOnLoad: false, theme: isDark ? 'dark' : 'default', securityLevel: 'loose' });
  const blocks = document.querySelectorAll('pre code.language-mermaid');
  blocks.forEach(async (el, i) => {
    const src = el.textContent;
    const id = 'mm-' + Date.now() + '-' + i;
    try {
      const { svg } = await mermaid.render(id, src);
      const wrap = document.createElement('div');
      wrap.className = 'mermaid-rendered';
      wrap.innerHTML = svg;
      el.parentElement.replaceWith(wrap);
    } catch (e) {
      // 渲染失败保留原代码块
      console.warn('mermaid render failed:', e);
    }
  });
}

// 详细摘要按钮 + outline 面板
const detailBtn = document.getElementById('detail-btn');
const detailPanel = document.getElementById('detail-panel');
const detailDataEl = document.getElementById('detail-data');
let detailData = null;
try { detailData = JSON.parse(detailDataEl.textContent); } catch(e) {}
const sidMatch = location.pathname.match(/([0-9a-f]{8}-[0-9a-f-]+)\.html/);
const fullSid = sidMatch ? sidMatch[1] : '';

function renderDetailPanel(data) {
  if (!data || !data.outline) return;
  const html = data.outline.map((o, i) => `
    <div class="outline-item">
      <div class="outline-head">
        <a href="#msg-${o.start_msg_idx}" class="outline-jump">→ msg #${o.start_msg_idx}</a>
        <strong>${i+1}. ${escapeHTML(o.topic || '')}</strong>
      </div>
      <div class="outline-summary">${escapeHTML(o.summary || '')}</div>
      ${o.key_points && o.key_points.length ? '<ul class="outline-keys">' + o.key_points.map(k => '<li>' + escapeHTML(k) + '</li>').join('') + '</ul>' : ''}
    </div>
  `).join('');
  detailPanel.innerHTML = `<div class="outline-meta">${data.outline.length} 段 · 生成于 ${data.generated_at} · ${data.model}</div>` + html;
}
function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function showDetail() {
  renderDetailPanel(detailData);
  detailPanel.style.display = 'block';
  detailBtn.textContent = '收起详细摘要';
}
function hideDetail() {
  detailPanel.style.display = 'none';
  detailBtn.textContent = '展开详细摘要';
}
function updateDetailHash(open) {
  const params = new URLSearchParams(location.hash.slice(1));
  if (open) params.set('detail', '1'); else params.delete('detail');
  const s = params.toString();
  history.replaceState(null, '', s ? '#' + s : location.pathname);
}
function isDetailOpenInHash() {
  return new URLSearchParams(location.hash.slice(1)).get('detail') === '1';
}

if (detailBtn) {
  detailBtn.addEventListener('click', () => {
    if (detailData) {
      const wasHidden = detailPanel.style.display === 'none';
      if (wasHidden) { showDetail(); updateDetailHash(true); }
      else { hideDetail(); updateDetailHash(false); }
    } else {
      const cmd = `python3 ~/.claude/skills/summarize-sessions/detail-summary.py --sid ${fullSid}`;
      navigator.clipboard.writeText(cmd).then(() => {
        alert('命令已复制到剪贴板:\\n\\n' + cmd + '\\n\\n去 terminal 粘贴执行(约 30-60s),完成后会自动重新打开本页面,届时按钮变成"展开详细摘要"。');
      }, () => {
        prompt('复制下面命令到 terminal 跑(完成后会自动重新打开本页面):', cmd);
      });
    }
  });
  // 页面加载时:如有 detail data 且 hash 标记为 open,自动展开
  if (detailData && isDetailOpenInHash()) {
    showDetail();
  }
}

// scroll 位置:节流保存到 sessionStorage,刷新后恢复(只在没搜索 + 没展开 detail 时考虑滚到底)
const scrollKey = 'mirror-scroll-' + (fullSid || location.pathname);
let scrollSaveTimer;
window.addEventListener('scroll', () => {
  clearTimeout(scrollSaveTimer);
  scrollSaveTimer = setTimeout(() => {
    sessionStorage.setItem(scrollKey, window.scrollY);
  }, 300);
}, {passive: true});

const savedScroll = parseFloat(sessionStorage.getItem(scrollKey) || '0');
const wantBottom = (!search || !search.value) && !isDetailOpenInHash();
// requestAnimationFrame 等渲染完
requestAnimationFrame(() => {
  if (savedScroll > 100) {
    // 用户之前滚到的位置,优先恢复
    window.scrollTo(0, savedScroll);
  } else if (wantBottom) {
    // 首次访问 / 没保存过 scroll,默认滚到底看最新
    window.scrollTo(0, document.body.scrollHeight);
  }
});

scheduleRefresh();
"""


def fmt_tokens(n):
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)


def fmt_duration(m):
    if not m: return "—"
    if m >= 60:
        h = m // 60
        rem = m % 60
        return f"{h}h{rem}m" if rem else f"{h}h"
    return f"{m}m"


def render_session_html(jsonl_path, sid, is_latest=False, meta=None, summary=None, detail=None):
    cards = parse_jsonl(jsonl_path)
    refresh_marker = '<button id="refresh-indicator" data-live="1" class="refresh-indicator" title="点击立即从最新 jsonl 重新渲染">↻ 刷新</button>' if is_latest else '<span id="refresh-indicator" class="refresh-indicator">archived</span>'
    # 分页:超过 VISIBLE_THRESHOLD 时,前部分默认隐藏(DOM 在但 display:none),点按钮渐进展开
    VISIBLE_THRESHOLD = 500
    n_total = len(cards)
    hidden_count = max(0, n_total - VISIBLE_THRESHOLD)
    if hidden_count > 0:
        cards = [
            (c.replace('<section class="msg ', '<section class="msg msg-hidden ', 1) if i < hidden_count else c)
            for i, c in enumerate(cards)
        ]
    load_earlier_bar = (
        f'<div class="load-earlier-bar"><button id="load-earlier-btn" class="load-earlier-btn">↑ 加载更早 500 条(还有 <span id="hidden-count">{hidden_count}</span> 条隐藏)</button> '
        f'<button id="load-all-btn" class="load-all-btn">全部展开</button></div>'
    ) if hidden_count > 0 else ''
    detail_json = json.dumps(detail, ensure_ascii=False) if detail else "null"
    detail_json_safe = detail_json.replace("</", "<\\/")
    summary_html = ""
    if summary and (summary.get("summary") or summary.get("tags")):
        tag_html = " ".join(f'<span class="tag">{esc(t)}</span>' for t in summary.get("tags", []))
        summary_html = f"""<div class="summary-card">
<div class="summary-text">{esc(summary.get("summary",""))}</div>
{f'<div class="tag-row">{tag_html}</div>' if tag_html else ''}
</div>"""
    meta_card = ""
    if meta:
        tokens = meta.get("tokens", {}) or {}
        tot = tokens.get("total", 0)
        dur = meta.get("duration_min", 0)
        warn = len(cards) > 200 or tot > 100_000
        warn_html = '<span class="badge warn">⚠ 超长</span>' if warn else ''
        tok_breakdown = ""
        if tokens:
            tok_breakdown = (
                f' <span class="tok-sub">in {fmt_tokens(tokens.get("input",0))} '
                f'· cache_r {fmt_tokens(tokens.get("cache_read",0))} '
                f'· cache_w {fmt_tokens(tokens.get("cache_create",0))} '
                f'· out {fmt_tokens(tokens.get("output",0))}</span>'
            )
        files_summary = ""
        if meta["files"]:
            items = "".join(
                f'<li><code>{esc(f["path"])}</code> · {",".join(esc(t) for t in f["tools"])} ×{f["count"]}</li>'
                for f in meta["files"][:50]
            )
            more = f'<li>… 共 {len(meta["files"])} 个文件</li>' if len(meta["files"]) > 50 else ""
            files_summary = f'<details><summary>触及文件 {len(meta["files"])} 个(点开)</summary><ul>{items}{more}</ul></details>'
        cmd_summary = ""
        if meta["commands"]:
            items = "".join(
                f'<li><code>{esc(c["cmd"])}</code> ×{c["count"]}</li>'
                for c in meta["commands"][:30]
            )
            more = f'<li>… 共 {len(meta["commands"])} 条命令</li>' if len(meta["commands"]) > 30 else ""
            cmd_summary = f'<details><summary>Bash 命令 {len(meta["commands"])} 条(点开)</summary><ul>{items}{more}</ul></details>'
        meta_card = f"""<div class="session-meta-card">
<div class="row"><span class="label">项目</span><span><span class="badge">{esc(meta["project"])}</span>{warn_html}</span></div>
<div class="row"><span class="label">cwd</span><code>{esc(meta["cwd"]) or "—"}</code></div>
<div class="row"><span class="label">Token</span><span>{fmt_tokens(tot)}{tok_breakdown}</span></div>
<div class="row"><span class="label">时长</span>{fmt_duration(dur)} · 工具调用 {meta["tool_calls"]} 次</div>
{('<div class="row"><span class="label">文件</span>' + files_summary + '</div>') if files_summary else ''}
{('<div class="row"><span class="label">命令</span>' + cmd_summary + '</div>') if cmd_summary else ''}
</div>"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{esc(sid[:8])} · session</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
<style>{CSS}</style></head><body>
<header class="top">
<a href="index.html">← 所有 session</a>
<input id="search" placeholder="搜索本 session 文本(空格分隔多关键词 AND)">
<span class="meta-info">{esc(sid)} · {len(cards)} msgs</span>
<button id="detail-btn" class="detail-btn">{"展开详细摘要" if detail else "生成详细摘要"}</button>
</header>
{summary_html}
{meta_card}
<div id="detail-panel" class="detail-panel" style="display:none"></div>
<script id="detail-data" type="application/json">{detail_json_safe}</script>
{load_earlier_bar}
{chr(10).join(cards)}
{refresh_marker}
<script>{SEARCH_JS}</script>
</body></html>"""


def render_index_html(rows, latest_sid, search_index, summaries=None, closed_sids=None):
    summaries = summaries or {}
    closed_sids = closed_sids or set()
    now_ts = datetime.datetime.now().timestamp()
    ACTIVE_SEC = 600  # mtime 10 分钟内 = 活跃
    proj_counts = {}
    long_count = 0
    active_count = 0
    idle_count = 0
    for r in rows:
        p = r.get("project", "—")
        proj_counts[p] = proj_counts.get(p, 0) + 1
        tot_tok = (r.get("tokens") or {}).get("total", 0)
        # 超长阈值:消息 > 500 或真实出账 token > 5M(cache_read 已不计入)
        if r["count"] > 500 or tot_tok > 5_000_000:
            long_count += 1
        if r["sid"] in closed_sids:
            pass
        elif (now_ts - r["mtime"]) < ACTIVE_SEC:
            active_count += 1
        else:
            idle_count += 1
    chips = [f'<button class="chip active" data-project="">全部 <span class="ct">{len(rows)}</span></button>']
    if active_count:
        chips.append(f'<button class="chip live-chip" data-project="__active__">● 活跃 <span class="ct">{active_count}</span></button>')
    if idle_count:
        chips.append(f'<button class="chip idle-chip" data-project="__idle__">○ 不活跃 <span class="ct">{idle_count}</span></button>')
    if long_count:
        chips.append(f'<button class="chip warn-chip" data-project="__long__">⚠ 超长 <span class="ct">{long_count}</span></button>')
    for p, n in sorted(proj_counts.items(), key=lambda x: -x[1]):
        chips.append(f'<button class="chip" data-project="{esc(p)}">{esc(p)} <span class="ct">{n}</span></button>')
    chips_html = "\n".join(chips)
    # 聚合 tag 计数 → 顶部热门标签 chip 区
    tag_counts = {}
    for r in rows:
        sm = summaries.get(r["sid"], {})
        for t in sm.get("tags", []):
            if isinstance(t, str) and t.strip():
                tag_counts[t.strip()] = tag_counts.get(t.strip(), 0) + 1
    tag_chips_html = ""
    if tag_counts:
        top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:30]
        chips_for_tags = ['<button class="chip tag-chip active" data-tag="">全部标签</button>']
        for t, n in top_tags:
            chips_for_tags.append(f'<button class="chip tag-chip" data-tag="{esc(t.lower())}">{esc(t)} <span class="ct">{n}</span></button>')
        tag_chips_html = f'<div id="tag-chips-wrap" class="chips tag-chips-wrap">{chr(10).join(chips_for_tags)}</div>'
    body_rows = []
    for r in rows:
        active = ' active' if r["sid"] == latest_sid else ''
        tokens = r.get("tokens") or {}
        tot = tokens.get("total", 0)
        is_long = r["count"] > 500 or tot > 5_000_000
        long_cls = " warn-long" if is_long else ""
        long_attr = "1" if is_long else "0"
        warn_mark = ' <span class="warn-mark">⚠</span>' if is_long else ""
        s = summaries.get(r["sid"], {})
        sum_text = s.get("summary", "") or r.get("preview", "") or "—"
        sum_cls = "summary" if s.get("summary") else "preview"
        tag_html = " ".join(f'<span class="tag tag-clickable" data-tag="{esc(t.lower())}">{esc(t)}</span>' for t in s.get("tags", [])[:5] if isinstance(t, str))
        if r["sid"] in closed_sids:
            status_html = '<span class="status-closed">已关</span>'
            status_key = "closed"
        elif (now_ts - r["mtime"]) < ACTIVE_SEC:
            status_html = '<span class="status-active">活跃</span>'
            status_key = "active"
        else:
            status_html = '<span class="status-idle">不活跃</span>'
            status_key = "idle"
        tag_attr = ",".join(t.lower() for t in s.get("tags", []) if isinstance(t, str))
        body_rows.append(
            f'<tr class="srow{active}{long_cls}" data-sid="{esc(r["sid"])}" data-project="{esc(r.get("project","—"))}" data-long="{long_attr}" data-status="{status_key}" data-tags="{esc(tag_attr)}">'
            f'<td class="time">{esc(r["mtime_str"])}</td>'
            f'<td class="project">{esc(r.get("project","—"))}</td>'
            f'<td class="count">{r["count"]}{warn_mark}</td>'
            f'<td class="num">{fmt_tokens(tot)}</td>'
            f'<td class="num">{fmt_duration(r.get("duration_min",0))}</td>'
            f'<td class="num">{r.get("files_n",0)}</td>'
            f'<td class="num">{r.get("commands_n",0)}</td>'
            f'<td><a href="{esc(r["sid"])}.html">{esc(r["sid"][:8])}</a> {status_html}</td>'
            f'<td class="{sum_cls}">{esc(sum_text)}</td>'
            f'<td class="tags">{tag_html or "—"}</td>'
            f'</tr>'
        )
    index_json = json.dumps(search_index, ensure_ascii=False)
    index_json_safe = index_json.replace("</", "<\\/")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Claude Code sessions</title>
<style>{CSS}</style></head><body>
<header class="top">
<strong>Claude Code sessions</strong>
<input id="global-search" placeholder="全局搜索所有 session(空格分隔多关键词 AND)">
<span class="meta-info">{len(rows)} 个 session</span>
</header>
<nav class="tabs">
<a href="index.html" class="active">Sessions</a>
<a href="files.html">文件反向</a>
<a href="commands.html">命令反向</a>
<a href="workflows.html">工作流</a>
<a href="knowledge-graph.html">知识图谱</a>
</nav>
<div id="chips-wrap" class="chips">{chips_html}</div>
{tag_chips_html}
<div id="results-wrap" style="display:none">
<div class="results-meta" id="results-meta"></div>
<div id="results"></div>
</div>
<table class="sessions" id="session-table">
<thead><tr>
<th>时间</th><th>项目</th>
<th style="text-align:right">消息</th>
<th style="text-align:right">Token</th>
<th style="text-align:right">时长</th>
<th style="text-align:right">文件</th>
<th style="text-align:right">命令</th>
<th>session</th><th>摘要 / 首句</th><th>标签</th>
</tr></thead>
<tbody>
{chr(10).join(body_rows)}
</tbody>
</table>
<script id="search-data" type="application/json">{index_json_safe}</script>
<script>{INDEX_JS}</script>
</body></html>"""


def render_knowledge_graph_html(rows, summaries):
    """知识图谱页:tag + session 双节点 force-directed graph。"""
    tag_to_sessions = {}
    session_data = {}
    tag_pairs = {}  # (tag_a, tag_b) → 共现 session 数
    mtime_min = None
    mtime_max = None
    for r in rows:
        sm = summaries.get(r["sid"], {})
        tags = [t for t in (sm.get("tags") or []) if isinstance(t, str) and t.strip()]
        if not tags:
            continue
        mt = r.get("mtime", 0)
        if mtime_min is None or mt < mtime_min: mtime_min = mt
        if mtime_max is None or mt > mtime_max: mtime_max = mt
        tokens_total = (r.get("tokens") or {}).get("total", 0)
        session_data[r["sid"]] = {
            "sid": r["sid"],
            "short": r["sid"][:8],
            "summary": (sm.get("summary") or r.get("preview") or "—")[:120],
            "tags": tags,
            "project": r.get("project", "—"),
            "mtime_str": r["mtime_str"],
            "mtime_ts": mt,
            "msg_count": r.get("count", 0),
            "tokens_total": tokens_total,
        }
        for t in tags:
            tag_to_sessions.setdefault(t, []).append(r["sid"])
        # tag 共现统计
        sorted_tags = sorted(tags)
        for i in range(len(sorted_tags)):
            for j in range(i + 1, len(sorted_tags)):
                key = (sorted_tags[i], sorted_tags[j])
                tag_pairs[key] = tag_pairs.get(key, 0) + 1
    nodes = []
    links = []
    for tag, sids in tag_to_sessions.items():
        nodes.append({
            "id": "tag:" + tag,
            "type": "tag",
            "label": tag,
            "size": len(sids),
        })
    for sid, meta in session_data.items():
        nodes.append({
            "id": "sid:" + sid,
            "type": "session",
            "label": meta["short"],
            "data": meta,
        })
    # 给每个 session 算 "dominant tag" — 该 session 5 个 tag 里出现次数最多的(整图最热门的那个)
    # 用作颜色编码,让同主题 session 染同色
    for sid, meta in session_data.items():
        tag_freq = [(t, len(tag_to_sessions.get(t, []))) for t in meta["tags"]]
        if tag_freq:
            tag_freq.sort(key=lambda x: -x[1])
            meta["dominant_tag"] = tag_freq[0][0]
        else:
            meta["dominant_tag"] = "?"
    # tag-session 边
    for tag, sids in tag_to_sessions.items():
        for sid in sids:
            links.append({"source": "tag:" + tag, "target": "sid:" + sid, "type": "ts"})
    # tag-tag 共现边(≥2 次共现,避免太密)
    MIN_COOCCUR = 2
    n_tag_tag = 0
    for (a, b), count in tag_pairs.items():
        if count < MIN_COOCCUR:
            continue
        links.append({"source": "tag:" + a, "target": "tag:" + b, "type": "tt", "weight": count})
        n_tag_tag += 1
    # 时间窗口给前端用
    mtime_range = {"min": mtime_min or 0, "max": mtime_max or 0}

    data_json = json.dumps({"nodes": nodes, "links": links, "mtime_range": mtime_range}, ensure_ascii=False).replace("</", "<\\/")
    n_tags = len(tag_to_sessions)
    n_sessions = len(session_data)
    n_links = len(links)
    n_ts_links = n_links - n_tag_tag
    # 统计:出现最多的 tag top 10
    top_tags = sorted(tag_to_sessions.items(), key=lambda kv: -len(kv[1]))[:15]
    top_tags_html = "".join(
        f'<li><a href="#" data-tag="{esc(t)}" class="tag-pill">{esc(t)}<span class="ct">{len(s)}</span></a></li>'
        for t, s in top_tags
    )

    tpl = """<!doctype html><html><head><meta charset="utf-8"><title>知识图谱</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<style>__SHARED_CSS__
body{padding:0;max-width:none;margin:0}
.kg-layout{display:grid;grid-template-columns:280px 1fr;height:100vh;overflow:hidden}
.kg-sidebar{padding:16px 18px;border-right:1px solid #0001;background:#fafaf8;overflow-y:auto}
@media(prefers-color-scheme:dark){.kg-sidebar{background:#1a1a1a;border-right-color:#fff2}}
.kg-sidebar h3{margin:18px 0 8px;font-size:13px;color:#888;text-transform:uppercase;letter-spacing:0.5px}
.kg-stats{font-size:12px;color:#666;line-height:1.6}
@media(prefers-color-scheme:dark){.kg-stats{color:#aaa}}
.kg-stats strong{color:#36c}
.tag-pill-list{list-style:none;padding:0;margin:0}
.tag-pill-list li{margin:4px 0}
.tag-pill{display:flex;justify-content:space-between;align-items:center;padding:5px 10px;font-size:12px;background:rgba(0,0,0,0.04);border-radius:14px;color:#333;text-decoration:none}
@media(prefers-color-scheme:dark){.tag-pill{background:rgba(255,255,255,0.06);color:#ddd}}
.tag-pill:hover{background:#36c;color:#fff}
.tag-pill.active{background:#36c;color:#fff;font-weight:600}
.tag-pill .ct{font-size:11px;opacity:0.7;margin-left:6px}
.kg-canvas{position:relative;overflow:hidden}
.kg-canvas svg{width:100%;height:100%;cursor:grab}
.kg-canvas svg:active{cursor:grabbing}
.kg-tooltip{position:absolute;background:rgba(20,20,20,0.95);color:#fff;padding:10px 14px;border-radius:8px;font-size:12px;line-height:1.5;pointer-events:none;max-width:340px;z-index:100;display:none}
.kg-tooltip.show{display:block}
.kg-tooltip .tt-title{font-weight:600;font-size:13px;margin-bottom:4px}
.kg-tooltip .tt-meta{color:#aaa;font-size:11px;margin-bottom:6px}
.kg-tooltip .tt-tags{margin-top:6px}
.kg-tooltip .tt-tag{display:inline-block;background:rgba(54,98,204,0.4);padding:2px 7px;border-radius:9px;font-size:10px;margin-right:4px;margin-bottom:3px}
.kg-controls{position:absolute;top:14px;right:14px;background:#fff;padding:8px 10px;border-radius:8px;font-size:12px;display:flex;flex-direction:column;gap:6px;border:1px solid #0001}
@media(prefers-color-scheme:dark){.kg-controls{background:#222;border-color:#fff2}}
.kg-controls button{padding:4px 10px;font-size:11px;border:1px solid #0002;background:transparent;border-radius:4px;cursor:pointer;color:inherit}
@media(prefers-color-scheme:dark){.kg-controls button{border-color:#fff3}}
.kg-controls button:hover{background:#36c;color:#fff;border-color:#36c}
.node-tag{fill:#36c}
.node-session{fill:#888}
.node-session.highlighted{stroke:#3a7;stroke-width:3px}
.node-tag.highlighted{stroke:#c80;stroke-width:3px}
.node-session.dimmed,.node-tag.dimmed{opacity:0.15}
.link{stroke:#0002;stroke-width:1px}
.link.tt{stroke:#c80;stroke-width:1.5px;stroke-opacity:0.4;stroke-dasharray:3,3}
.link.highlighted{stroke:#36c;stroke-width:2.5px;stroke-opacity:0.9}
.link.dimmed{opacity:0.05}
@media(prefers-color-scheme:dark){.link{stroke:#fff3}}
.node-label{font-size:11px;fill:#333;pointer-events:none;font-family:-apple-system,sans-serif;text-anchor:middle}
@media(prefers-color-scheme:dark){.node-label{fill:#ddd}}
.node-label.tag-label{font-weight:600;font-size:12px}
.node-label.session-label{font-size:9px;opacity:0.7;font-family:ui-monospace,monospace}
.hull-path{pointer-events:none}
.hull-label{pointer-events:none;font-family:-apple-system,sans-serif}
</style></head><body>
<header class="top" style="padding:10px 16px">
<strong>知识图谱 · 跨 session tag 关联</strong>
<input id="kg-search" placeholder="搜 tag / session sid / 摘要..." style="flex:1;max-width:340px;margin:0 16px;padding:6px 10px;font-size:13px;border:1px solid #0002;border-radius:6px;background:transparent;color:inherit">
<span class="meta-info">__N_SESSIONS__ session · __N_TAGS__ tag · __N_TS_LINKS__ tag→session · __N_TAG_TAG__ tag↔tag</span>
</header>
<nav class="tabs" style="padding:0 16px">
<a href="index.html">Sessions</a>
<a href="files.html">文件反向</a>
<a href="commands.html">命令反向</a>
<a href="workflows.html">工作流</a>
<a href="knowledge-graph.html" class="active">知识图谱</a>
</nav>
<div class="kg-layout">
<aside class="kg-sidebar">
<div class="kg-stats">
全图共 <strong>__N_SESSIONS__</strong> session 和 <strong>__N_TAGS__</strong> tag,<strong>__N_LINKS__</strong> 条连接。<br><br>
<strong>用法:</strong>
<ul style="padding-left:18px;line-height:1.7;margin:6px 0;font-size:11px">
<li>蓝色大节点 = tag,小节点 = session</li>
<li>session 颜色 = 主题(同色同 cluster)</li>
<li>session 大小 = token 烧得多就大</li>
<li>session 越新越鲜艳</li>
<li>橙色虚线 = tag↔tag 共现</li>
<li>拖节点固定位置</li>
<li>hover 看摘要</li>
<li>单击 session 跳详情页</li>
<li>单击 tag 高亮关联</li>
<li><strong>双击</strong>聚焦子图(2 跳邻居)</li>
<li>虚线圈 = 自动识别的主题集团</li>
<li>顶部搜索 / 右上保存 PNG</li>
</ul>
</div>
<h3>热门标签 (top 15)</h3>
<ul class="tag-pill-list">__TOP_TAGS_HTML__</ul>
</aside>
<div class="kg-canvas" id="kg-canvas">
<svg id="kg-svg"></svg>
<div class="kg-tooltip" id="kg-tooltip"></div>
<div class="kg-controls">
<button id="kg-toggle-hulls">⌬ 切换主题圈</button>
<button id="kg-reset-zoom">重置缩放</button>
<button id="kg-clear-highlight">取消聚焦</button>
<button id="kg-download-png">📷 保存 PNG</button>
<button id="kg-export-md">导出 Markdown 大纲</button>
<button id="kg-export-mindmap">导出思维导图 PNG</button>
</div>
</div>
</div>
<script id="kg-data" type="application/json">__DATA_JSON__</script>
<script>
const data = JSON.parse(document.getElementById('kg-data').textContent);
const svg = d3.select('#kg-svg');
const canvas = document.getElementById('kg-canvas');
const width = canvas.clientWidth;
const height = canvas.clientHeight;
const tooltip = document.getElementById('kg-tooltip');

// zoom(filter 关掉 dblclick,避免跟自定义双击聚焦打架)
const zoomG = svg.append('g').attr('class','zoom-layer');
const zoomBehavior = d3.zoom().scaleExtent([0.2, 5])
  .filter(e => e.type !== 'dblclick')
  .on('zoom', (e) => zoomG.attr('transform', e.transform));
svg.call(zoomBehavior);

// hull layer(community 背景圈,在 link 下)
const hullG = zoomG.append('g').attr('class', 'hulls');
const hullLabelG = zoomG.append('g').attr('class', 'hull-labels');

// force simulation
const sim = d3.forceSimulation(data.nodes)
  .force('link', d3.forceLink(data.links).id(d => d.id).distance(d => d.source.type === 'tag' ? 80 : 60).strength(0.4))
  .force('charge', d3.forceManyBody().strength(d => d.type === 'tag' ? -200 : -50))
  .force('center', d3.forceCenter(width/2, height/2))
  .force('collide', d3.forceCollide().radius(d => d.type === 'tag' ? 14 + Math.min(d.size, 10) : 8));

// 项目颜色 hash:同项目同色
function hashColor(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  const hue = Math.abs(h) % 360;
  return `hsl(${hue}, 60%, 58%)`;
}

// Label Propagation community detection(简化 Louvain,零外部依赖)
function detectCommunities(nodes, links, iterations) {
  iterations = iterations || 15;
  const adj = {};
  nodes.forEach(n => { adj[n.id] = []; });
  links.forEach(l => {
    const s = typeof l.source === 'object' ? l.source.id : l.source;
    const t = typeof l.target === 'object' ? l.target.id : l.target;
    const w = l.weight || (l.type === 'tt' ? 2 : 1);  // tag-tag 权重高(主题更紧密)
    adj[s].push({neighbor: t, weight: w});
    adj[t].push({neighbor: s, weight: w});
  });
  const labels = {};
  nodes.forEach(n => { labels[n.id] = n.id; });
  // deterministic order:用 node.id hash 排序,保证每次刷新结果一致
  function _hash(s) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h; }
  const baseOrder = nodes.map(n => n.id).sort((a, b) => _hash(a) - _hash(b));
  for (let iter = 0; iter < iterations; iter++) {
    let changed = false;
    // 每次迭代用同一固定顺序(不再 random),community 稳定
    const order = baseOrder;
    for (const id of order) {
      const freq = {};
      for (const {neighbor, weight} of adj[id]) {
        const lbl = labels[neighbor];
        freq[lbl] = (freq[lbl] || 0) + weight;
      }
      let best = labels[id], maxF = -1;
      for (const [lbl, f] of Object.entries(freq)) {
        if (f > maxF || (f === maxF && lbl < best)) { maxF = f; best = lbl; }
      }
      if (best !== labels[id]) {
        labels[id] = best;
        changed = true;
      }
    }
    if (!changed) break;
  }
  return labels;
}
// 跑 community detection,给每个 node 加 community 字段
const communityLabels = detectCommunities(data.nodes, data.links);
data.nodes.forEach(n => { n.community = communityLabels[n.id]; });
// 统计每个 community 的成员 + 主题(取 community 内 tag 节点 size 最大的 label 作为 cluster name)
const communityInfo = {};
data.nodes.forEach(n => {
  const c = n.community;
  if (!communityInfo[c]) communityInfo[c] = {members: [], topTag: null, topTagId: null, tagSize: -1};
  communityInfo[c].members.push(n);
  if (n.type === 'tag' && n.size > communityInfo[c].tagSize) {
    communityInfo[c].topTag = n.label;
    communityInfo[c].topTagId = n.id;
    communityInfo[c].tagSize = n.size;
  }
});

// 时间渐变 opacity:新 session 不透明,老的浅
const mtRange = data.mtime_range || {min: 0, max: 1};
function timeOpacity(ts) {
  if (!ts || mtRange.max === mtRange.min) return 1;
  const norm = (ts - mtRange.min) / (mtRange.max - mtRange.min);
  return 0.35 + norm * 0.65;  // 老 0.35 → 新 1.0
}

const link = zoomG.append('g').attr('class','links').selectAll('line')
  .data(data.links).join('line')
  .attr('class', d => 'link ' + (d.type || 'ts'))
  .attr('stroke-width', d => d.type === 'tt' ? 1 + Math.min(d.weight || 1, 4) * 0.3 : 1);

const node = zoomG.append('g').attr('class','nodes').selectAll('g')
  .data(data.nodes).join('g')
  .attr('class', d => d.type === 'tag' ? 'node-tag-group' : 'node-session-group')
  .call(d3.drag()
    .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
    .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
    .on('end', (e, d) => {
      if (!e.active) sim.alphaTarget(0);
      // C1: 保留拖完位置但允许微调
    }));

// session 节点大小:tokens 量编码(log scale,大节点 = 烧 token 多)
// 区间设计:无 token → 6px,1K → ~8px,1M → ~13px,1B → ~18px
function sessionRadius(d) {
  const tot = (d.data && d.data.tokens_total) || 0;
  if (tot <= 0) return 6;
  return Math.max(6, Math.min(18, 5 + Math.log10(tot + 1) * 1.5));
}

node.append('circle')
  .attr('r', d => d.type === 'tag' ? Math.max(10, 8 + Math.sqrt(d.size) * 3) : sessionRadius(d))
  .attr('class', d => d.type === 'tag' ? 'node-tag' : 'node-session')
  .attr('fill', d => {
    if (d.type === 'tag') return '#36c';
    // session 颜色 = dominant tag hash (同主题 session 同色,真正 cluster 化)
    return hashColor(d.data.dominant_tag || d.data.project || 'unknown');
  })
  .attr('opacity', d => {
    if (d.type === 'tag') return 1;
    return timeOpacity(d.data.mtime_ts);
  })
  .attr('stroke', '#fff')
  .attr('stroke-width', 1.5);

node.append('text')
  .attr('class', d => d.type === 'tag' ? 'node-label tag-label' : 'node-label session-label')
  .attr('dy', d => d.type === 'tag' ? Math.max(20, 18 + Math.sqrt(d.size) * 2) : 14)
  .text(d => d.label);

// hull 渲染:每 community 一个凸包背景
let showHulls = true;
let tickCount = 0;
function updateHulls() {
  if (!showHulls) {
    hullG.selectAll('path').remove();
    hullLabelG.selectAll('text').remove();
    return;
  }
  // C3 fix: 同时记 pts + node 引用,padding 计算改对象引用 O(N) 而非浮点比较 O(N*M)
  const grouped = {};
  data.nodes.forEach(n => {
    if (n.community === undefined || n.x === undefined) return;
    if (!grouped[n.community]) grouped[n.community] = {pts: [], nodes: []};
    grouped[n.community].pts.push([n.x, n.y]);
    grouped[n.community].nodes.push(n);
  });
  const hullData = Object.entries(grouped)
    .filter(([_, g]) => g.pts.length >= 3)
    .map(([id, g]) => {
      const hull = d3.polygonHull(g.pts);
      if (!hull) return null;
      const cx = d3.mean(hull, d => d[0]);
      const cy = d3.mean(hull, d => d[1]);
      // padding = community 内最大节点半径 + 10
      const maxR = Math.max(...g.nodes.map(n =>
        n.type === 'tag' ? Math.max(10, 8 + Math.sqrt(n.size) * 3) : sessionRadius(n)
      )) + 10;
      const padded = hull.map(p => {
        const dx = p[0] - cx, dy = p[1] - cy;
        const d = Math.sqrt(dx*dx + dy*dy) || 1;
        return [p[0] + dx/d * maxR, p[1] + dy/d * maxR];
      });
      return {id, hull: padded, cx, cy, info: communityInfo[id]};
    })
    .filter(x => x);
  // 画 hull
  hullG.selectAll('path').data(hullData, d => d.id).join(
    enter => enter.append('path').attr('class', 'hull-path'),
    update => update,
    exit => exit.remove()
  ).attr('d', d => 'M' + d.hull.map(p => p.join(',')).join('L') + 'Z')
   .attr('fill', d => hashColor('com:' + d.id))
   .attr('fill-opacity', 0.08)
   .attr('stroke', d => hashColor('com:' + d.id))
   .attr('stroke-opacity', 0.4)
   .attr('stroke-width', 2)
   .attr('stroke-dasharray', '4,4');
  // 画 community 标签
  hullLabelG.selectAll('text').data(hullData.filter(d => d.info && d.info.topTag && d.info.members.length >= 3), d => d.id).join(
    enter => enter.append('text').attr('class', 'hull-label'),
    update => update,
    exit => exit.remove()
  ).attr('x', d => d.cx)
   .attr('y', d => Math.min(...d.hull.map(p => p[1])) - 8)
   .attr('text-anchor', 'middle')
   .attr('fill', d => hashColor('com:' + d.id))
   .attr('font-weight', 700)
   .attr('font-size', 13)
   .attr('opacity', 0.9)
   .text(d => '⌬ ' + d.info.topTag + ' (' + d.info.members.length + ')');
}

sim.on('tick', () => {
  link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  node.attr('transform', d => `translate(${d.x},${d.y})`);
  tickCount++;
  // A3 fix: 前期(alpha>0.1)每 10 tick 节流;收敛区(alpha<0.1)节点几乎不动,不必每帧更新
  if (tickCount % 10 === 0) updateHulls();
});
sim.on('end', () => updateHulls());  // 完全收敛后兜底更新一次

// hover tooltip
node.on('mouseenter', (e, d) => {
  let html = '';
  if (d.type === 'tag') {
    html = '<div class="tt-title">' + escapeHTML(d.label) + '</div><div class="tt-meta">tag · ' + d.size + ' 个 session 用过</div>';
  } else {
    const m = d.data;
    html = '<div class="tt-title">' + escapeHTML(m.short) + ' · ' + escapeHTML(m.project) + '</div>';
    html += '<div class="tt-meta">' + escapeHTML(m.mtime_str) + ' · ' + m.msg_count + ' msgs</div>';
    html += escapeHTML(m.summary);
    html += '<div class="tt-tags">' + m.tags.map(t => '<span class="tt-tag">'+escapeHTML(t)+'</span>').join('') + '</div>';
  }
  tooltip.innerHTML = html;
  tooltip.classList.add('show');
}).on('mousemove', (e) => {
  tooltip.style.left = Math.min(e.pageX + 14, window.innerWidth - 360) + 'px';
  tooltip.style.top = (e.pageY + 14) + 'px';
}).on('mouseleave', () => tooltip.classList.remove('show'));

// click 加 250ms 延迟,让 dblclick 有机会先触发取消跳转
const clickTimers = {};
node.on('click', (e, d) => {
  e.stopPropagation();
  if (clickTimers[d.id]) clearTimeout(clickTimers[d.id]);
  clickTimers[d.id] = setTimeout(() => {
    delete clickTimers[d.id];  // B1: 完成后从 map 删,避免膨胀
    if (d.type === 'session') {
      window.location.href = d.data.sid + '.html';
    } else if (d.type === 'tag') {
      highlightTag(d.label);
    }
  }, 250);
});

// 双击聚焦子图(只显示 root + 1 跳 + 2 跳邻居)
function focusSubgraph(rootId) {
  const keep = new Set([rootId]);
  // BFS 2 跳
  for (let depth = 0; depth < 2; depth++) {
    const expansion = new Set();
    data.links.forEach(l => {
      const sId = typeof l.source === 'object' ? l.source.id : l.source;
      const tId = typeof l.target === 'object' ? l.target.id : l.target;
      if (keep.has(sId)) expansion.add(tId);
      if (keep.has(tId)) expansion.add(sId);
    });
    expansion.forEach(x => keep.add(x));
  }
  node.selectAll('circle')
    .classed('dimmed', d => !keep.has(d.id))
    .classed('highlighted', d => d.id === rootId);
  link.classed('dimmed', l => {
    const sId = typeof l.source === 'object' ? l.source.id : l.source;
    const tId = typeof l.target === 'object' ? l.target.id : l.target;
    return !keep.has(sId) || !keep.has(tId);
  });
}
node.on('dblclick', (e, d) => {
  e.stopPropagation();
  e.preventDefault();
  // 取消同节点的延迟 click(避免双击同时触发跳页)
  if (clickTimers[d.id]) {
    clearTimeout(clickTimers[d.id]);
    delete clickTimers[d.id];  // B1: 清掉防止 map 膨胀
  }
  focusSubgraph(d.id);
});
// 双击空白(SVG 自己)恢复
svg.on('dblclick.background', function(e) {
  if (e.target === this || e.target.tagName === 'svg' || e.target.classList.contains('zoom-layer')) {
    clearHighlight();
  }
});

// 高亮某 tag 所有关联
function highlightTag(tagName) {
  const tagId = 'tag:' + tagName;
  const relatedSids = new Set();
  data.links.forEach(l => {
    const sId = typeof l.source === 'object' ? l.source.id : l.source;
    const tId = typeof l.target === 'object' ? l.target.id : l.target;
    if (sId === tagId) relatedSids.add(tId);
    if (tId === tagId) relatedSids.add(sId);
  });
  node.classed('highlighted', false);
  node.selectAll('circle').classed('highlighted', d => d.id === tagId || relatedSids.has(d.id));
  link.classed('highlighted', l => {
    const sId = typeof l.source === 'object' ? l.source.id : l.source;
    const tId = typeof l.target === 'object' ? l.target.id : l.target;
    return sId === tagId || tId === tagId;
  });
  document.querySelectorAll('.tag-pill').forEach(p => p.classList.toggle('active', p.dataset.tag === tagName));
}

function clearHighlight() {
  node.selectAll('circle').classed('highlighted', false).classed('dimmed', false);
  link.classed('highlighted', false).classed('dimmed', false);
  document.querySelectorAll('.tag-pill').forEach(p => p.classList.remove('active'));
  const si = document.getElementById('kg-search');
  if (si) si.value = '';
}

// 搜索 filter
const searchInput = document.getElementById('kg-search');
if (searchInput) {
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim().toLowerCase();
    if (!q) {
      node.selectAll('circle').classed('dimmed', false).classed('highlighted', false);
      link.classed('dimmed', false);
      return;
    }
    const matchedIds = new Set();
    data.nodes.forEach(n => {
      let hit = false;
      if (n.label && n.label.toLowerCase().includes(q)) hit = true;
      if (n.type === 'session' && n.data) {
        if ((n.data.summary || '').toLowerCase().includes(q)) hit = true;
        if ((n.data.project || '').toLowerCase().includes(q)) hit = true;
        if (n.data.sid && n.data.sid.toLowerCase().includes(q)) hit = true;
        if ((n.data.tags || []).some(t => t.toLowerCase().includes(q))) hit = true;
      }
      if (hit) matchedIds.add(n.id);
    });
    node.selectAll('circle')
      .classed('highlighted', d => matchedIds.has(d.id))
      .classed('dimmed', d => !matchedIds.has(d.id));
    link.classed('dimmed', l => {
      const sId = typeof l.source === 'object' ? l.source.id : l.source;
      const tId = typeof l.target === 'object' ? l.target.id : l.target;
      return !matchedIds.has(sId) && !matchedIds.has(tId);
    });
  });
}

document.querySelectorAll('.tag-pill').forEach(p => {
  p.addEventListener('click', (e) => {
    e.preventDefault();
    highlightTag(p.dataset.tag);
  });
});

document.getElementById('kg-clear-highlight').addEventListener('click', clearHighlight);
document.getElementById('kg-toggle-hulls').addEventListener('click', () => {
  showHulls = !showHulls;
  updateHulls();
});
document.getElementById('kg-reset-zoom').addEventListener('click', () => {
  // 用同一 zoomBehavior 实例(B3),避免状态错位
  svg.transition().duration(500).call(zoomBehavior.transform, d3.zoomIdentity);
  sim.alpha(0.5).restart();
});

// === 知识树导出 ===
// 纯 tag 结构:community(主题)→ 该社区内 tag(按热度 top N)。session 不进图。
const TAGS_PER_COMMUNITY = 10;
const MIN_TAGS_IN_COMMUNITY = 2;

function buildKnowledgeTree() {
  // 按 community 收集 tag 节点(过滤 session)
  const byCom = {};
  data.nodes.forEach(n => {
    if (n.type !== 'tag' || n.community === undefined) return;
    if (!byCom[n.community]) byCom[n.community] = [];
    byCom[n.community].push(n);
  });
  // 每个 tag 算"被多少 session 用过"(从 ts link 数,fallback tag.size)
  const tagSessionCount = {};
  data.links.forEach(l => {
    if (l.type !== 'ts') return;
    const src = typeof l.source === 'object' ? l.source.id : l.source;
    const tgt = typeof l.target === 'object' ? l.target.id : l.target;
    const tagId = src.startsWith('tag:') ? src : (tgt.startsWith('tag:') ? tgt : null);
    if (!tagId) return;
    tagSessionCount[tagId] = (tagSessionCount[tagId] || 0) + 1;
  });

  const tree = {name: '知识图 · ' + new Date().toISOString().slice(0,10), children: []};
  const comIds = Object.keys(byCom)
    .filter(c => byCom[c].length >= MIN_TAGS_IN_COMMUNITY)
    .sort((a, b) => byCom[b].length - byCom[a].length);

  for (const cid of comIds) {
    const tags = byCom[cid].slice().sort((a, b) => (b.size || 0) - (a.size || 0));
    const info = communityInfo[cid] || {};
    // L1 名 = 该 community 最热 tag(代表性主题词)
    const topTag = info.topTag || tags[0].label;
    const topTagId = info.topTagId || tags[0].id;
    const comNode = {name: topTag, children: []};
    // L2:其他 tag(用 id 过滤,避免同名 tag 误删)
    const innerTags = tags
      .filter(t => t.id !== topTagId)
      .slice(0, TAGS_PER_COMMUNITY);
    for (const t of innerTags) {
      const cnt = tagSessionCount[t.id] || t.size || 0;
      comNode.children.push({name: cnt > 1 ? `${t.label} (${cnt})` : t.label});
    }
    if (comNode.children.length > 0) tree.children.push(comNode);
  }
  return tree;
}

function treeToMarkdown(tree) {
  const lines = [`# ${tree.name}`, ''];
  function walk(node, depth) {
    const indent = '  '.repeat(depth);
    lines.push(`${indent}- ${node.name}`);
    (node.children || []).forEach(c => walk(c, depth + 1));
  }
  (tree.children || []).forEach(c => walk(c, 0));
  return lines.join(String.fromCharCode(10));
}

function xmlEsc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 用 D3 horizontal tree layout 渲染思维导图 SVG → PNG
function exportMindmapPng() {
  const tree = buildKnowledgeTree();
  const root = d3.hierarchy(tree, d => d.children);
  // 截断过长 label,留 tooltip 不影响 PNG
  root.descendants().forEach(d => {
    const t = d.data.name;
    d.data._display = t.length > 26 ? t.slice(0, 26) + '…' : t;
  });
  const leafCount = Math.max(root.leaves().length, 8);
  const nodeVGap = 32;
  const colGap = 280;
  const margin = {top: 60, right: 80, bottom: 60, left: 80};
  const innerHeight = leafCount * nodeVGap;
  const innerWidth = (root.height) * colGap;
  const width = innerWidth + margin.left + margin.right + 320;
  const height = innerHeight + margin.top + margin.bottom;
  const layout = d3.tree().size([innerHeight, innerWidth]);
  layout(root);

  const svgNs = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNs, 'svg');
  svg.setAttribute('xmlns', svgNs);
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

  const bg = document.createElementNS(svgNs, 'rect');
  bg.setAttribute('width', width); bg.setAttribute('height', height); bg.setAttribute('fill', '#fafaf8');
  svg.appendChild(bg);

  // 根节点居中,所有坐标偏移 margin
  const offsetX = margin.left;
  const offsetY = margin.top;
  // 颜色板(按 community 序号)
  const palette = ['#36c', '#0aa', '#c80', '#a85', '#a7c', '#3a7', '#c5b', '#5a9', '#d72', '#48a'];
  // 给每个 community 一级节点分配色板
  const comColor = {};
  root.children && root.children.forEach((c, i) => { comColor[c.data.name] = palette[i % palette.length]; });

  // 链接(贝塞尔曲线)
  const linkG = document.createElementNS(svgNs, 'g');
  svg.appendChild(linkG);
  root.descendants().slice(1).forEach(d => {
    let topCom = d;
    while (topCom.depth > 1) topCom = topCom.parent;
    const color = comColor[topCom.data.name] || '#888';
    const sx = d.parent.y + offsetX, sy = d.parent.x + offsetY;
    const tx = d.y + offsetX, ty = d.x + offsetY;
    const mx = (sx + tx) / 2;
    const path = document.createElementNS(svgNs, 'path');
    path.setAttribute('d', `M${sx},${sy}C${mx},${sy} ${mx},${ty} ${tx},${ty}`);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', color);
    path.setAttribute('stroke-opacity', d.depth === 1 ? 0.9 : 0.5);
    path.setAttribute('stroke-width', d.depth === 1 ? 2.2 : 1.4);
    linkG.appendChild(path);
  });

  // 节点
  const nodeG = document.createElementNS(svgNs, 'g');
  svg.appendChild(nodeG);
  root.descendants().forEach(d => {
    const x = d.y + offsetX, y = d.x + offsetY;
    const text = d.data._display;
    // 中文宽度估算
    const charW = 13;
    const padX = 14;
    const minW = 60;
    const w = Math.min(280, Math.max(minW, text.length * charW + padX * 2));
    const h = d.depth === 0 ? 38 : 28;
    let topCom = d;
    while (topCom.depth > 1) topCom = topCom.parent;
    const accent = comColor[topCom && topCom.data ? topCom.data.name : ''] || '#36c';
    const isRoot = d.depth === 0;
    const isCom = d.depth === 1;

    const rect = document.createElementNS(svgNs, 'rect');
    rect.setAttribute('x', x - w/2);
    rect.setAttribute('y', y - h/2);
    rect.setAttribute('width', w);
    rect.setAttribute('height', h);
    rect.setAttribute('rx', 8);
    rect.setAttribute('fill', isRoot ? '#1a1a1a' : (isCom ? accent : '#fff'));
    rect.setAttribute('stroke', isRoot ? '#000' : accent);
    rect.setAttribute('stroke-width', isCom ? 0 : 1.5);
    nodeG.appendChild(rect);

    const tElem = document.createElementNS(svgNs, 'text');
    tElem.setAttribute('x', x);
    tElem.setAttribute('y', y + 4);
    tElem.setAttribute('text-anchor', 'middle');
    tElem.setAttribute('font-family', '-apple-system, BlinkMacSystemFont, sans-serif');
    tElem.setAttribute('font-size', isRoot ? 16 : (isCom ? 13 : 12));
    tElem.setAttribute('font-weight', isRoot ? '700' : (isCom ? '600' : '500'));
    tElem.setAttribute('fill', isRoot ? '#fff' : (isCom ? '#fff' : '#333'));
    tElem.textContent = text;
    nodeG.appendChild(tElem);
  });

  // serialize
  const serializer = new XMLSerializer();
  const svgStr = serializer.serializeToString(svg);
  const blob = new Blob([svgStr], {type: 'image/svg+xml;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement('canvas');
    // canvas 上限 16384 (Chrome/Firefox);iOS Safari 4096。clamp 防 worst-case 静默白图
    const MAX_DIM = 16384;
    const scale = Math.min(2, MAX_DIM / Math.max(width, height));
    canvas.width = Math.floor(width * scale);
    canvas.height = Math.floor(height * scale);
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fafaf8';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);
    canvas.toBlob(b => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(b);
      a.download = `mindmap-${new Date().toISOString().slice(0,10)}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1500);
    }, 'image/png');
  };
  img.onerror = () => alert('SVG 转 PNG 失败');
  img.src = url;
}

function downloadText(filename, content, mime) {
  const blob = new Blob([content], {type: (mime || 'text/plain') + ';charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

document.getElementById('kg-export-md').addEventListener('click', () => {
  const tree = buildKnowledgeTree();
  const md = treeToMarkdown(tree);
  const ts = new Date().toISOString().slice(0,10);
  downloadText(`knowledge-tree-${ts}.md`, md, 'text/markdown');
});

document.getElementById('kg-export-mindmap').addEventListener('click', exportMindmapPng);

// 截图 PNG:svg → canvas → png download
let pngBusy = false;
document.getElementById('kg-download-png').addEventListener('click', (e) => {
  if (pngBusy) return;  // A1 fix: 防 5s 内连点并发
  pngBusy = true;
  const btn = e.currentTarget;
  btn.disabled = true;
  const origText = btn.textContent;
  btn.textContent = '⏳ 导出中...';
  // 暂停 simulation 避免导出时节点抖动
  sim.stop();
  const svgEl = document.getElementById('kg-svg');
  // inline 必要 styles 到 svg(否则 image 渲染时 css 类不生效)
  const allElems = svgEl.querySelectorAll('*');
  const tmpStyles = [];
  allElems.forEach(el => {
    const cs = window.getComputedStyle(el);
    const props = ['fill','stroke','stroke-width','stroke-dasharray','opacity','font-size','font-family','font-weight','text-anchor'];
    const inlined = {};
    props.forEach(p => {
      const v = cs.getPropertyValue(p);
      if (v) {
        inlined[p] = el.style.getPropertyValue(p);
        el.style.setProperty(p, v);
      }
    });
    tmpStyles.push({el, inlined});
  });
  const w = svgEl.clientWidth, h = svgEl.clientHeight;
  const scale = 2;  // retina
  const serializer = new XMLSerializer();
  const cloned = svgEl.cloneNode(true);
  cloned.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  cloned.setAttribute('width', w);
  cloned.setAttribute('height', h);
  const svgStr = serializer.serializeToString(cloned);
  // 恢复原 inline style
  tmpStyles.forEach(({el, inlined}) => {
    Object.entries(inlined).forEach(([k, v]) => {
      if (v) el.style.setProperty(k, v);
      else el.style.removeProperty(k);
    });
  });
  const blob = new Blob([svgStr], {type: 'image/svg+xml;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const img = new Image();
  // A1 fix: done flag 让三路径互斥,避免重复 cleanup / 重复 restart sim
  let pngDone = false;
  function finalizePng(msg) {
    if (pngDone) return;
    pngDone = true;
    URL.revokeObjectURL(url);
    sim.alpha(0.1).restart();
    // 恢复按钮
    pngBusy = false;
    btn.disabled = false;
    btn.textContent = origText;
    if (msg) alert(msg);
  }
  img.onload = () => {
    if (pngDone) return;
    const canvas = document.createElement('canvas');
    canvas.width = w * scale;
    canvas.height = h * scale;
    const ctx = canvas.getContext('2d');
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    ctx.fillStyle = isDark ? '#0f1115' : '#fafaf8';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, w, h);
    canvas.toBlob(b => {
      if (!b) { finalizePng('截图失败,浏览器可能不支持'); return; }
      const a = document.createElement('a');
      a.href = URL.createObjectURL(b);
      const ts = new Date().toISOString().slice(0,19).replace(/[:T]/g,'-');
      a.download = `knowledge-graph-${ts}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
      finalizePng();
    }, 'image/png');
  };
  img.onerror = () => finalizePng('SVG 转 PNG 失败,可能含浏览器不支持的元素');
  setTimeout(() => finalizePng(), 5000);
  img.src = url;
});

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
</script>
</body></html>"""
    return (tpl
        .replace("__SHARED_CSS__", CSS)
        .replace("__N_SESSIONS__", str(n_sessions))
        .replace("__N_TAGS__", str(n_tags))
        .replace("__N_LINKS__", str(n_links))
        .replace("__N_TS_LINKS__", str(n_ts_links))
        .replace("__N_TAG_TAG__", str(n_tag_tag))
        .replace("__TOP_TAGS_HTML__", top_tags_html)
        .replace("__DATA_JSON__", data_json)
    )


def render_workflows_html(rows, summaries):
    """工作流模式识别页:零 token,扫所有 session 匹配 6 个 pattern。"""
    pattern_buckets = {p["id"]: [] for p in WORKFLOW_PATTERNS}
    multi_match_rows = []  # 命中多个 pattern 的 session
    unmatched = []
    for r in rows:
        matches = match_workflows(r, summaries)
        if not matches:
            unmatched.append(r)
            continue
        if len(matches) > 1:
            multi_match_rows.append((r, matches))
        for p, score in matches:
            pattern_buckets[p["id"]].append({"row": r, "score": score})
    # 每个 bucket 按 score 倒序
    for pid in pattern_buckets:
        pattern_buckets[pid].sort(key=lambda x: -x["score"])

    pattern_sections = []
    for p in WORKFLOW_PATTERNS:
        bucket = pattern_buckets[p["id"]]
        if not bucket:
            pattern_sections.append(f'<div class="pattern-section"><h3>{esc(p["name"])} <span class="pattern-count">0</span></h3><p class="pattern-desc">{esc(p["desc"])}</p><p class="empty">未识别到</p></div>')
            continue
        # 聚合 subagent / skill 频次(这个 pattern 内的所有 session)
        sa_agg = {}
        sk_agg = {}
        for b in bucket:
            for s in b["row"].get("subagents", []) or []:
                k = s.get("type", "?")
                sa_agg[k] = sa_agg.get(k, 0) + s.get("count", 0)
            for s in b["row"].get("skills", []) or []:
                k = s.get("name", "?")
                sk_agg[k] = sk_agg.get(k, 0) + s.get("count", 0)
        sa_top = sorted(sa_agg.items(), key=lambda x: -x[1])[:6]
        sk_top = sorted(sk_agg.items(), key=lambda x: -x[1])[:6]
        sa_html = " ".join(f'<span class="tag">{esc(k)} ×{v}</span>' for k, v in sa_top) or "—"
        sk_html = " ".join(f'<span class="tag">/{esc(k)} ×{v}</span>' for k, v in sk_top) or "—"
        rows_html = "".join(
            f'<tr><td class="time">{esc(b["row"]["mtime_str"])}</td>'
            f'<td>{esc(b["row"].get("project","—"))}</td>'
            f'<td class="num">{b["score"]}</td>'
            f'<td><a href="{esc(b["row"]["sid"])}.html">{esc(b["row"]["sid"][:8])}</a></td>'
            f'<td class="preview">{esc(summaries.get(b["row"]["sid"], {}).get("summary") or b["row"].get("preview") or "—")}</td>'
            f'</tr>'
            for b in bucket[:30]
        )
        more = f'<tr><td colspan="5" class="more">+ {len(bucket) - 30} 个更多 session,按命中信号数排序</td></tr>' if len(bucket) > 30 else ""
        pattern_sections.append(
            f'<div class="pattern-section">'
            f'<h3>{esc(p["name"])} <span class="pattern-count">{len(bucket)}</span></h3>'
            f'<p class="pattern-desc">{esc(p["desc"])}</p>'
            f'<div class="pattern-meta"><div class="pattern-meta-row"><span class="label">subagent:</span>{sa_html}</div>'
            f'<div class="pattern-meta-row"><span class="label">skill:</span>{sk_html}</div></div>'
            f'<table class="files"><thead><tr><th>时间</th><th>项目</th><th style="text-align:right">信号数</th><th>sid</th><th>摘要/首句</th></tr></thead>'
            f'<tbody>{rows_html}{more}</tbody></table>'
            f'</div>'
        )

    # 头部统计
    coverage = len(rows) - len(unmatched)
    summary_html = (
        f'<p class="results-meta">{coverage}/{len(rows)} session 命中至少 1 个 pattern · '
        f'{len(multi_match_rows)} 个 session 跨多 pattern · '
        f'{len(unmatched)} 个未识别</p>'
    )

    return f"""<!doctype html><html><head><meta charset="utf-8"><title>工作流模式识别</title>
<style>{CSS}</style></head><body>
<header class="top">
<strong>工作流模式识别</strong>
<span class="meta-info">{len(WORKFLOW_PATTERNS)} 个 pattern · {len(rows)} 个 session 扫过</span>
</header>
<nav class="tabs">
<a href="index.html">Sessions</a>
<a href="files.html">文件反向</a>
<a href="commands.html">命令反向</a>
<a href="workflows.html" class="active">工作流</a>
<a href="knowledge-graph.html">知识图谱</a>
</nav>
{summary_html}
{chr(10).join(pattern_sections)}
</body></html>"""


def render_commands_html(rows):
    """命令反向索引:每条 Bash 命令前缀 → 哪些 session 跑过。"""
    cmd_to_sessions = {}
    for r in rows:
        for c in r.get("commands", []):
            entry = cmd_to_sessions.setdefault(c["cmd"], [])
            entry.append({
                "sid": r["sid"],
                "short": r["sid"][:8],
                "mtime_str": r["mtime_str"],
                "mtime": r["mtime"],
                "count": c["count"],
                "project": r.get("project", "—"),
            })
    sorted_cmds = sorted(cmd_to_sessions.items(), key=lambda kv: -sum(x["count"] for x in kv[1]))
    body = []
    for cmd, sessions in sorted_cmds:
        sessions.sort(key=lambda x: -x["mtime"])
        total = sum(s["count"] for s in sessions)
        sids_html = "".join(
            f'<a href="{esc(s["sid"])}.html" title="{esc(s["mtime_str"])} · {esc(s["project"])} ×{s["count"]}">{esc(s["short"])}</a>'
            for s in sessions
        )
        body.append(
            f'<tr>'
            f'<td class="fpath" title="{esc(cmd)}">{esc(cmd)}</td>'
            f'<td class="num">{len(sessions)}</td>'
            f'<td class="num">{total}</td>'
            f'<td class="sids"><div class="sids-wrap">{sids_html}</div></td>'
            f'</tr>'
        )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>命令反向索引</title>
<style>{CSS}</style></head><body>
<header class="top">
<strong>命令反向索引</strong>
<input id="filter-input" placeholder="按命令过滤(子串匹配)">
<span class="meta-info">{len(sorted_cmds)} 条不同命令</span>
</header>
<nav class="tabs">
<a href="index.html">Sessions</a>
<a href="files.html">文件反向</a>
<a href="commands.html" class="active">命令反向</a>
<a href="workflows.html">工作流</a>
<a href="knowledge-graph.html">知识图谱</a>
</nav>
<table class="files" id="files-table">
<thead><tr><th>命令</th><th style="text-align:right">session 数</th><th style="text-align:right">总次数</th><th>session 列表(按时间)</th></tr></thead>
<tbody>
{chr(10).join(body)}
</tbody>
</table>
<script>
const fi = document.getElementById('filter-input');
const rows = Array.from(document.querySelectorAll('#files-table tbody tr'));
function applyFilter(q) {{
  const ql = q.toLowerCase().trim();
  for (const r of rows) {{
    const cmd = r.querySelector('.fpath').textContent.toLowerCase();
    r.style.display = (!ql || cmd.includes(ql)) ? '' : 'none';
  }}
}}
function readHash() {{ const m = location.hash.match(/q=([^&]*)/); return m ? decodeURIComponent(m[1]) : ''; }}
function writeHash(q) {{ if (q) history.replaceState(null,'','#q='+encodeURIComponent(q)); else history.replaceState(null,'',location.pathname); }}
const q0 = readHash();
if (q0) {{ fi.value = q0; applyFilter(q0); }}
fi.addEventListener('input', () => {{ applyFilter(fi.value); writeHash(fi.value); }});
</script>
</body></html>"""


def render_files_html(rows):
    """文件反向索引:每个文件 → 哪些 session 触及。"""
    file_to_sessions = {}  # path → [{sid, short, mtime_str, tools, count}]
    for r in rows:
        for f in r.get("files", []):
            entry = file_to_sessions.setdefault(f["path"], [])
            entry.append({
                "sid": r["sid"],
                "short": r["sid"][:8],
                "mtime_str": r["mtime_str"],
                "mtime": r["mtime"],
                "tools": f["tools"],
                "count": f["count"],
                "project": r.get("project", "—"),
            })
    # 按"被触及总次数"倒序
    sorted_files = sorted(file_to_sessions.items(), key=lambda kv: -sum(x["count"] for x in kv[1]))
    body = []
    for path, sessions in sorted_files:
        sessions.sort(key=lambda x: -x["mtime"])
        total_touches = sum(s["count"] for s in sessions)
        sids_html = "".join(
            f'<a href="{esc(s["sid"])}.html" title="{esc(s["mtime_str"])} · {esc(s["project"])} · {",".join(s["tools"])} ×{s["count"]}">{esc(s["short"])}</a>'
            for s in sessions
        )
        body.append(
            f'<tr>'
            f'<td class="fpath" title="{esc(path)}">{esc(path)}</td>'
            f'<td class="num">{len(sessions)}</td>'
            f'<td class="num">{total_touches}</td>'
            f'<td class="sids"><div class="sids-wrap">{sids_html}</div></td>'
            f'</tr>'
        )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>文件反向索引</title>
<style>{CSS}</style></head><body>
<header class="top">
<strong>文件反向索引</strong>
<input id="filter-input" placeholder="按路径过滤(子串匹配)">
<span class="meta-info">{len(sorted_files)} 个文件</span>
</header>
<nav class="tabs">
<a href="index.html">Sessions</a>
<a href="files.html" class="active">文件反向</a>
<a href="commands.html">命令反向</a>
<a href="workflows.html">工作流</a>
<a href="knowledge-graph.html">知识图谱</a>
</nav>
<table class="files" id="files-table">
<thead><tr><th>文件路径</th><th style="text-align:right">session 数</th><th style="text-align:right">总操作</th><th>session 列表(按时间)</th></tr></thead>
<tbody>
{chr(10).join(body)}
</tbody>
</table>
<script>
const fi = document.getElementById('filter-input');
const rows = Array.from(document.querySelectorAll('#files-table tbody tr'));
function applyFilter(q) {{
  const ql = q.toLowerCase().trim();
  for (const r of rows) {{
    const path = r.querySelector('.fpath').textContent.toLowerCase();
    r.style.display = (!ql || path.includes(ql)) ? '' : 'none';
  }}
}}
function readHash() {{ const m = location.hash.match(/q=([^&]*)/); return m ? decodeURIComponent(m[1]) : ''; }}
function writeHash(q) {{ if (q) history.replaceState(null,'','#q='+encodeURIComponent(q)); else history.replaceState(null,'',location.pathname); }}
const q0 = readHash();
if (q0) {{ fi.value = q0; applyFilter(q0); }}
fi.addEventListener('input', () => {{ applyFilter(fi.value); writeHash(fi.value); }});
</script>
</body></html>"""


def list_sessions():
    """扫所有 ~/.claude/projects/*/ 下的 jsonl,通用化(不限定 user 目录)。"""
    files = glob.glob(os.path.join(PROJECTS_BASE, "*", "*.jsonl"))
    if not files:
        # legacy: 单层目录(没分 user namespace 的情况)
        files = glob.glob(os.path.join(PROJECTS_BASE, "*.jsonl"))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files


def build_rows(files, metadata_cache=None):
    """metadata_cache: dict sid → meta. 为复用预算好的 metadata,避免每次重读。"""
    rows = []
    for f in files:
        sid = os.path.basename(f).replace(".jsonl", "")
        count, preview = session_meta(f)
        if metadata_cache and sid in metadata_cache:
            meta = metadata_cache[sid]
        else:
            meta = parse_jsonl_for_metadata(f)
        rows.append({
            "sid": sid,
            "count": count,
            "preview": preview,
            "mtime": os.path.getmtime(f),
            "mtime_str": fmt_mtime(f),
            "path": f,
            "project": meta["project"],
            "cwd": meta["cwd"],
            "files": meta["files"],
            "files_n": len(meta["files"]),
            "commands": meta["commands"],
            "commands_n": len(meta["commands"]),
            "subagents": meta.get("subagents", []),
            "skills": meta.get("skills", []),
            "tool_calls": meta["tool_calls"],
            "tokens": meta.get("tokens", {}),
            "duration_min": meta.get("duration_min", 0),
        })
    return rows


def build_search_index_entries(rows):
    """search-index.json 内含 metadata + msgs。"""
    entries = []
    for r in rows:
        msgs = parse_jsonl_for_index(r["path"])
        entries.append({
            "sid": r["sid"],
            "mtime_str": r["mtime_str"],
            "project": r["project"],
            "cwd": r["cwd"],
            "files": r["files"],
            "commands": r["commands"],
            "subagents": r.get("subagents", []),
            "skills": r.get("skills", []),
            "tool_calls": r["tool_calls"],
            "tokens": r.get("tokens", {}),
            "duration_min": r.get("duration_min", 0),
            "msgs": msgs,
        })
    return entries


def load_search_index(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def load_summaries(out_dir):
    """读 /tmp/mirror/summaries.json。skill 生产,mirror viewer 只读。"""
    p = os.path.join(out_dir, "summaries.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_detail_summary(out_dir, sid):
    """读 /tmp/mirror/detailed-summaries/<sid>.json。脚本生产,viewer 只读。"""
    p = os.path.join(out_dir, "detailed-summaries", f"{sid}.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_closed_sids(out_dir):
    """读 /tmp/mirror/closed-sessions.json。SessionEnd hook 写,mirror 只读。"""
    p = os.path.join(out_dir, "closed-sessions.json")
    try:
        with open(p, encoding="utf-8") as f:
            return set(json.load(f).keys())
    except Exception:
        return set()


def save_search_index(entries, path):
    """atomic write:避免 async hook 并发撞坏文件。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    os.replace(tmp, path)


def meta_from_index_entry(e):
    """从 search-index.json 单条 entry 还原 metadata dict。"""
    return {
        "project": e.get("project", "—"),
        "cwd": e.get("cwd", ""),
        "files": e.get("files", []),
        "commands": e.get("commands", []),
        "subagents": e.get("subagents", []),
        "skills": e.get("skills", []),
        "tool_calls": e.get("tool_calls", 0),
        "tokens": e.get("tokens", {}),
        "duration_min": e.get("duration_min", 0),
    }


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--latest":
        out_dir = args[1]
        os.makedirs(out_dir, exist_ok=True)
        files = list_sessions()
        if not files:
            print("no session files", file=sys.stderr); return
        # 加载旧索引(含 metadata)作为 cache
        idx_path = os.path.join(out_dir, "search-index.json")
        existing = load_search_index(idx_path)
        meta_cache = {e["sid"]: meta_from_index_entry(e) for e in existing}
        rows = build_rows(files, metadata_cache=meta_cache)
        latest = rows[0]
        # 重算 latest 的 metadata + msgs(其他用 cache)
        latest_meta = parse_jsonl_for_metadata(latest["path"])
        latest["project"] = latest_meta["project"]
        latest["cwd"] = latest_meta["cwd"]
        latest["files"] = latest_meta["files"]
        latest["files_n"] = len(latest_meta["files"])
        latest["commands"] = latest_meta["commands"]
        latest["commands_n"] = len(latest_meta["commands"])
        latest["tool_calls"] = latest_meta["tool_calls"]
        latest["tokens"] = latest_meta.get("tokens", {})
        latest["duration_min"] = latest_meta.get("duration_min", 0)
        latest_summary = load_summaries(out_dir).get(latest["sid"])
        latest_detail = load_detail_summary(out_dir, latest["sid"])
        html_out = render_session_html(latest["path"], latest["sid"], is_latest=True, meta=latest_meta, summary=latest_summary, detail=latest_detail)
        with open(os.path.join(out_dir, f'{latest["sid"]}.html'), "w", encoding="utf-8") as f:
            f.write(html_out)
        # 更新 search index
        existing_by_sid = {e["sid"]: e for e in existing}
        latest_entry = {
            "sid": latest["sid"],
            "mtime_str": latest["mtime_str"],
            "project": latest["project"],
            "cwd": latest["cwd"],
            "files": latest["files"],
            "commands": latest["commands"],
            "tool_calls": latest["tool_calls"],
            "tokens": latest["tokens"],
            "duration_min": latest["duration_min"],
            "msgs": parse_jsonl_for_index(latest["path"]),
        }
        existing_by_sid[latest["sid"]] = latest_entry
        merged = []
        for r in rows:
            if r["sid"] in existing_by_sid:
                merged.append(existing_by_sid[r["sid"]])
            else:
                meta = parse_jsonl_for_metadata(r["path"])
                merged.append({
                    "sid": r["sid"],
                    "mtime_str": r["mtime_str"],
                    "project": meta["project"],
                    "cwd": meta["cwd"],
                    "files": meta["files"],
                    "commands": meta["commands"],
                    "tool_calls": meta["tool_calls"],
                    "tokens": meta.get("tokens", {}),
                    "duration_min": meta.get("duration_min", 0),
                    "msgs": parse_jsonl_for_index(r["path"]),
                })
        save_search_index(merged, idx_path)
        summaries = load_summaries(out_dir)
        closed_sids = load_closed_sids(out_dir)
        idx_out = render_index_html(rows, latest["sid"], merged, summaries=summaries, closed_sids=closed_sids)
        with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(idx_out)
        files_out = render_files_html(rows)
        with open(os.path.join(out_dir, "files.html"), "w", encoding="utf-8") as f:
            f.write(files_out)
        cmds_out = render_commands_html(rows)
        with open(os.path.join(out_dir, "commands.html"), "w", encoding="utf-8") as f:
            f.write(cmds_out)
        wf_summaries = load_summaries(out_dir)
        wf_out = render_workflows_html(rows, wf_summaries)
        with open(os.path.join(out_dir, "workflows.html"), "w", encoding="utf-8") as f:
            f.write(wf_out)
        kg_out = render_knowledge_graph_html(rows, wf_summaries)
        with open(os.path.join(out_dir, "knowledge-graph.html"), "w", encoding="utf-8") as f:
            f.write(kg_out)
        tok = (latest.get("tokens") or {}).get("total", 0)
        print(f"latest: {latest['sid'][:8]} · {latest['count']} msgs · {fmt_tokens(tok)} tok · {fmt_duration(latest.get('duration_min',0))} · proj={latest['project']}")
    elif len(args) == 2 and args[0] == "--all":
        out_dir = args[1]
        os.makedirs(out_dir, exist_ok=True)
        files = list_sessions()
        rows = build_rows(files)
        latest_sid = rows[0]["sid"] if rows else None
        summaries = load_summaries(out_dir)
        closed_sids = load_closed_sids(out_dir)
        for r in rows:
            is_latest = r["sid"] == latest_sid
            meta_for_render = {
                "project": r["project"],
                "cwd": r["cwd"],
                "files": r["files"],
                "commands": r["commands"],
                "tool_calls": r["tool_calls"],
                "tokens": r.get("tokens", {}),
                "duration_min": r.get("duration_min", 0),
            }
            detail = load_detail_summary(out_dir, r["sid"])
            html_out = render_session_html(r["path"], r["sid"], is_latest=is_latest, meta=meta_for_render, summary=summaries.get(r["sid"]), detail=detail)
            with open(os.path.join(out_dir, f'{r["sid"]}.html'), "w", encoding="utf-8") as f:
                f.write(html_out)
        index_entries = build_search_index_entries(rows)
        save_search_index(index_entries, os.path.join(out_dir, "search-index.json"))
        idx_out = render_index_html(rows, latest_sid, index_entries, summaries=summaries, closed_sids=closed_sids)
        with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(idx_out)
        files_out = render_files_html(rows)
        with open(os.path.join(out_dir, "files.html"), "w", encoding="utf-8") as f:
            f.write(files_out)
        cmds_out = render_commands_html(rows)
        with open(os.path.join(out_dir, "commands.html"), "w", encoding="utf-8") as f:
            f.write(cmds_out)
        wf_summaries = load_summaries(out_dir)
        wf_out = render_workflows_html(rows, wf_summaries)
        with open(os.path.join(out_dir, "workflows.html"), "w", encoding="utf-8") as f:
            f.write(wf_out)
        kg_out = render_knowledge_graph_html(rows, wf_summaries)
        with open(os.path.join(out_dir, "knowledge-graph.html"), "w", encoding="utf-8") as f:
            f.write(kg_out)
        print(f"rendered {len(rows)} sessions + search/files/commands indexes; index at {out_dir}/index.html")
    elif len(args) == 2:
        src, dst = args
        sid = os.path.basename(src).replace(".jsonl", "")
        meta = parse_jsonl_for_metadata(src)
        html_out = render_session_html(src, sid, is_latest=True, meta=meta)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(html_out)
        print(f"wrote {dst}")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
