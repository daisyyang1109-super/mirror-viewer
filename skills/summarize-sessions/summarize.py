#!/usr/bin/env python3
"""Summarize Claude Code sessions via DeepSeek.

Usage:
  python3 summarize.py            # 增量(默认):只跑还没摘要的 session
  python3 summarize.py --all      # 全量:重跑所有 session
  python3 summarize.py --sid <id> # 只跑指定 session
"""
import json, os, sys, time, urllib.request, urllib.error

MIRROR_DIR = os.path.expanduser("~/.claude/mirror")
SEARCH_INDEX = os.path.join(MIRROR_DIR, "search-index.json")
SUMMARIES = os.path.join(MIRROR_DIR, "summaries.json")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
MAX_MSGS = 100   # 单 session 最多采样 100 条 msg(防超 context)
MAX_CHARS_PER_MSG = 500
TIMEOUT = 60


def get_deepseek_key():
    """fallback:env DEEPSEEK_API_KEY → ~/.deepseek 文件。key 不进 commit。"""
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


def sample_msgs(msgs):
    """从 session msgs 里采样:首 30 + 尾 50 + 中间随机 20(总 <= MAX_MSGS)。"""
    if len(msgs) <= MAX_MSGS:
        return msgs
    head = msgs[:30]
    tail = msgs[-50:]
    mid_start = 30
    mid_end = len(msgs) - 50
    if mid_end > mid_start:
        # 等距采样 20 条中间
        step = max(1, (mid_end - mid_start) // 20)
        mid = msgs[mid_start:mid_end:step][:20]
    else:
        mid = []
    return head + mid + tail


def build_prompt(msgs):
    """拼接 session msgs 成 prompt。每条加 role 前缀 + 截 MAX_CHARS_PER_MSG。"""
    lines = []
    for m in msgs:
        role = m.get("role", "?")
        text = (m.get("text") or "").replace("\n", " ")[:MAX_CHARS_PER_MSG]
        lines.append(f"[{role}] {text}")
    return "\n".join(lines)


SYSTEM_PROMPT = """你是 Claude Code session 历史的总结助手。读完一段 user/assistant conversation 后输出 JSON:

- summary: 一句话(中文, 60-100 字)说明 session 的**具体落点**:
  * 必须包含: 具体决策(决定/放弃/选择 X) 或 具体产出(实现/写了/删掉 X) 或 具体结论(验证/得出 X)
  * 强烈避免: "分析了X" / "讨论了X" / "评估了X" / "对话" / "聊了" 这种动词大词
  * 如果是评估/分析类 session, 必须写出**得出了什么具体判断/选择**, 不要停在"分析"
  * 如果同主题多次评估, 突出**本次 session 关注的具体子模块或新角度**(如 "本次聚焦付费抽卡设计" / "本次新增创作者经济视角")

- tags: 3-5 个关键词标签(中文短词):
  * 优先具体名词: 文件名 / 工具名 / 概念名 / 决策结果 / 模块名
  * 避免: "讨论" / "分析" / "对话" / "评估" 这种动词
  * 好例子: "付费抽卡" / "creator-economy" / "mirror-viewer" / "封版" / "P0"
  * 坏例子: "分析" / "评估" / "讨论" / "项目分析"

注意:
- 必须输出合法 JSON, 不要 markdown 代码块, 不要解释
- 格式: {"summary": "xxx", "tags": ["a", "b", "c"]}"""


def call_deepseek(prompt, key, retries=2):
    """调 DeepSeek API。失败重试 retries 次,仍失败抛 RuntimeError。"""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 400,
        "temperature": 0.3,
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                DEEPSEEK_URL,
                data=json.dumps(body).encode(),
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read())
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return json.loads(text), usage
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(1 + attempt)
    raise RuntimeError(f"DeepSeek call failed after {retries+1} tries: {last_err}")


def load_summaries():
    if not os.path.exists(SUMMARIES):
        return {}
    try:
        with open(SUMMARIES) as f:
            return json.load(f)
    except Exception:
        return {}


def save_summaries(summaries):
    with open(SUMMARIES, "w") as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)


def main():
    args = sys.argv[1:]
    mode_all = "--all" in args
    sid_filter = None
    if "--sid" in args:
        i = args.index("--sid")
        if i + 1 < len(args):
            sid_filter = args[i + 1]

    if not os.path.exists(SEARCH_INDEX):
        print(f"ERR: {SEARCH_INDEX} 不存在。先跑 python3 ~/.claude/mirror/jsonl2html.py --all ~/.claude/mirror 生成。", file=sys.stderr)
        sys.exit(1)

    key = get_deepseek_key()
    if not key:
        print("ERR: DeepSeek API key 找不到。手动 export DEEPSEEK_API_KEY=xxx 再跑。", file=sys.stderr)
        sys.exit(1)

    with open(SEARCH_INDEX) as f:
        index = json.load(f)

    summaries = load_summaries()
    todo = []
    for e in index:
        sid = e["sid"]
        if sid_filter and sid != sid_filter:
            continue
        if not mode_all and sid in summaries:
            continue
        if not e.get("msgs"):
            continue  # 空 session 跳过
        todo.append(e)

    if not todo:
        print(f"没有待处理 session(已有 {len(summaries)} 个摘要)。传 --all 强制重跑。")
        return

    print(f"待处理 {len(todo)} 个 session,跳过 {len(index)-len(todo)} 个已有摘要的。")
    total_in = total_out = 0
    failed = []
    t0 = time.time()

    for i, e in enumerate(todo, 1):
        sid = e["sid"]
        msgs = sample_msgs(e["msgs"])
        prompt = build_prompt(msgs)
        try:
            result, usage = call_deepseek(prompt, key)
            summaries[sid] = {
                "summary": result.get("summary", "").strip()[:200],
                "tags": [t.strip()[:20] for t in result.get("tags", [])[:6] if t and isinstance(t, str)],
                "model": MODEL,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            total_in += usage.get("prompt_tokens", 0)
            total_out += usage.get("completion_tokens", 0)
            print(f"  [{i}/{len(todo)}] {sid[:8]} · {summaries[sid]['summary'][:30]}…")
            # 每条单独写盘,失败不影响已成功的
            save_summaries(summaries)
        except Exception as ex:
            failed.append((sid, str(ex)))
            print(f"  [{i}/{len(todo)}] {sid[:8]} FAILED: {ex}", file=sys.stderr)

    dt = time.time() - t0
    # DeepSeek 价格:cache miss input ¥0.0027/1K, cache hit ¥0.0007/1K, output ¥0.0011/1K(2026 价)
    # 粗算用 cache miss 价
    cost = total_in * 0.0027 / 1000 + total_out * 0.0011 / 1000
    print()
    print(f"完成。耗时 {dt:.1f}s · 处理 {len(todo)-len(failed)}/{len(todo)} 成功")
    print(f"Token: in={total_in} out={total_out} · 估计花费 ¥{cost:.3f}")
    if failed:
        print(f"失败 {len(failed)} 个:")
        for sid, err in failed[:10]:
            print(f"  {sid[:8]}: {err}")

    # 触发 mirror 重新渲染(summaries 才会显示)
    print()
    print("重新渲染 mirror viewer…")
    rc = os.system("python3 ~/.claude/mirror/jsonl2html.py --all ~/.claude/mirror")
    if rc == 0:
        print("done. 打开 ~/.claude/mirror/index.html 看摘要。")


if __name__ == "__main__":
    main()
