#!/usr/bin/env python3
"""Generate detailed multi-section summary for a single Claude Code session.

Usage:
  python3 detail-summary.py --sid <session-id>   生成详细摘要,cache 到 /tmp/mirror/detailed-summaries/<sid>.json
  python3 detail-summary.py --sid <id> --force   强制重新生成(覆盖 cache)
"""
import json, os, sys, time, urllib.request, urllib.error

MIRROR_DIR = os.path.expanduser("~/.claude/mirror")
DETAILED_DIR = os.path.join(MIRROR_DIR, "detailed-summaries")
SEARCH_INDEX = os.path.join(MIRROR_DIR, "search-index.json")
PROJECTS_BASE = os.path.expanduser("~/.claude/projects")  # 通用化:扫所有 user namespace 子目录
JSONL2HTML = os.path.expanduser("~/.claude/mirror/jsonl2html.py")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
MAX_MSGS = 200
MAX_CHARS_PER_MSG = 600
TIMEOUT = 90


def get_deepseek_key():
    """fallback:env DEEPSEEK_API_KEY → ~/.deepseek 文件。"""
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


def load_session_with_weights(jsonl_path):
    """直接读原始 jsonl,每条 msg 计算 weight:
    - has_tool_use → +1.5(具体工作发生)
    - len(text) bonus → +len/500 封顶 3
    - role=user → +1.0(用户输入往往开新话题或拍板)
    - 紧随 user 的 assistant(idx - last_user <= 2) → +0.5(密集讨论上下文)
    """
    items = []
    idx = -1
    last_user_idx = -100
    with open(jsonl_path) as f:
        for line in f:
            try: d = json.loads(line)
            except: continue
            if d.get("type") not in ("user", "assistant"): continue
            idx += 1
            msg = d.get("message", {})
            content = msg.get("content", "")
            role = d.get("type")
            text = ""
            has_tool = False
            if isinstance(content, str):
                stripped = content.strip()
                if stripped.startswith("<system-reminder>") or stripped.startswith("<command-"):
                    continue
                text = stripped
            elif isinstance(content, list):
                parts = []
                for b in content:
                    if not isinstance(b, dict): continue
                    if b.get("type") == "text": parts.append(b.get("text", ""))
                    if b.get("type") == "tool_use": has_tool = True
                text = "\n".join(parts).strip()
            if not text and not has_tool:
                continue
            weight = 1.0
            if has_tool: weight += 1.5
            weight += min(len(text) / 500.0, 3.0)
            if role == "user":
                last_user_idx = idx
                weight += 1.0
            elif idx - last_user_idx <= 2:
                weight += 0.5
            items.append({
                "idx": idx,
                "role": role,
                "text": text[:MAX_CHARS_PER_MSG],
                "has_tool": has_tool,
                "weight": weight,
            })
    return items


def smart_sample(items, max_n=MAX_MSGS):
    """智能采样:必保首 head_n + 尾 tail_n,中间按 weight 取 top。"""
    n = len(items)
    if n <= max_n:
        return items
    head_n = min(30, max_n // 5)
    tail_n = min(30, max_n // 5)
    mid_budget = max_n - head_n - tail_n
    head = items[:head_n]
    tail = items[-tail_n:]
    mid_pool = items[head_n:n - tail_n]
    mid_top = sorted(mid_pool, key=lambda x: -x["weight"])[:mid_budget]
    mid_top.sort(key=lambda x: x["idx"])
    return head + mid_top + tail


def build_prompt(items):
    """带 idx 的 conversation。"""
    lines = []
    for m in items:
        marker = "+" if m.get("has_tool") else " "
        text = (m.get("text") or "").replace("\n", " ")[:MAX_CHARS_PER_MSG]
        lines.append(f"[{m['idx']}]{marker}[{m['role']}] {text}")
    return "\n".join(lines)


SYSTEM_PROMPT = """你是 Claude Code session 历史的详细摘要助手。读完整段对话后,把内容按主题边界分成 4-10 个段落 outline。

每个段落输出:
- topic: 这段的主题(< 25 字, 名词性短语, 避免动词大词)
- start_msg_idx: 这段开始的消息索引(整数, 必须是输入里出现过的 idx)
- summary: 这段的详细摘要(80-200 字), 必须包含:
  * 用户问/想做什么
  * AI 做了什么/给了什么建议
  * 最终落到什么(决策/产出/结论/数字)
- key_points: 2-5 条要点(每条 10-40 字, 短句, 信息密度高)

输入对话每条消息格式: `[idx]<marker>[role] text`。
`<marker>` = `+` 表示该消息含 tool_use(AI 调用工具,具体工作发生),`空格` 表示纯文本。优先把 `+` 标记的消息作为段落边界依据。

注意:
- 必须输出合法 JSON, 不要 markdown 代码块, 不要解释
- start_msg_idx 必须是输入里出现过的 idx, 不能瞎填
- topic 边界要清晰, 避免段落跨主题
- 如果某段没有明确结论, 也要说"未结案/搁置/暂缓"

格式: {"outline": [{"topic": "xxx", "start_msg_idx": N, "summary": "xxx", "key_points": ["a", "b"]}, ...]}"""


def call_deepseek(prompt, key):
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 4000,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read())
    text = data["choices"][0]["message"]["content"]
    return json.loads(text), data.get("usage", {})


def main():
    args = sys.argv[1:]
    sid = None
    force = False
    if "--sid" in args:
        i = args.index("--sid")
        if i + 1 < len(args): sid = args[i + 1]
    if "--force" in args: force = True

    if not sid:
        print("ERR: --sid <session-id> 必填", file=sys.stderr)
        sys.exit(1)

    os.makedirs(DETAILED_DIR, exist_ok=True)
    out_path = os.path.join(DETAILED_DIR, f"{sid}.json")

    if os.path.exists(out_path) and not force:
        print(f"cache 已存在: {out_path}, 加 --force 强制重跑")
        return

    # 通用化:扫所有 ~/.claude/projects/*/ 找该 sid 的 jsonl
    import glob as _glob
    candidates = _glob.glob(os.path.join(PROJECTS_BASE, "*", f"{sid}.jsonl"))
    candidates += _glob.glob(os.path.join(PROJECTS_BASE, f"{sid}.jsonl"))
    if not candidates:
        print(f"ERR: 在 {PROJECTS_BASE}/*/ 下找不到 {sid}.jsonl", file=sys.stderr)
        sys.exit(1)
    jsonl_path = candidates[0]

    key = get_deepseek_key()
    if not key:
        print("ERR: DEEPSEEK_API_KEY 找不到", file=sys.stderr)
        sys.exit(1)

    items = load_session_with_weights(jsonl_path)
    if not items:
        print("ERR: session 没有有效 msgs", file=sys.stderr)
        sys.exit(1)

    sampled = smart_sample(items)
    tool_count = sum(1 for m in sampled if m.get("has_tool"))
    prompt = build_prompt(sampled)
    print(f"调 DeepSeek: smart sample {len(sampled)} / total {len(items)} 条 msg (其中 {tool_count} 条有 tool_use)...")

    t0 = time.time()
    try:
        result, usage = call_deepseek(prompt, key)
    except Exception as e:
        print(f"ERR: DeepSeek 调用失败: {e}", file=sys.stderr)
        sys.exit(1)

    detail = {
        "sid": sid,
        "model": MODEL,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "outline": result.get("outline", []),
        "total_msgs": len(items),
        "sampled_msgs": len(sampled),
        "sampling": "smart_weighted",
    }
    with open(out_path, "w") as f:
        json.dump(detail, f, ensure_ascii=False, indent=2)

    dt = time.time() - t0
    tok_in = usage.get("prompt_tokens", 0)
    tok_out = usage.get("completion_tokens", 0)
    cost = tok_in * 0.0027 / 1000 + tok_out * 0.0011 / 1000
    print(f"完成。{len(detail['outline'])} 段 outline · {dt:.1f}s · tok in={tok_in} out={tok_out} · ¥{cost:.3f}")
    print(f"cache: {out_path}")

    print("重新渲染 mirror viewer...")
    os.system(f"python3 {JSONL2HTML} --all {MIRROR_DIR}")
    sess_html = os.path.join(MIRROR_DIR, f"{sid}.html")
    if os.path.exists(sess_html):
        os.system(f"open {sess_html}")
        print(f"已打开 {sess_html}")


if __name__ == "__main__":
    main()
