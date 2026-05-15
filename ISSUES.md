# mirror viewer · 已知问题清单

**最后 QA review**:2026-05-14
**Reviewer**:general-purpose QA agent

按严重度 + 是否已修分组。

---

## 已修(2026-05-14 这轮)

- [x] `save_search_index` atomic write(tmp + rename),避免 async hook 并发损坏
- [x] 所有 `open(...)` 加 `encoding="utf-8"`(20 处),防 Windows 中文崩
- [x] `mark-session-closed.py` atomic write + 错误打 stderr + 显式关文件句柄
- [x] `md2html.py highlightText` 用 **上下文锚定 + nth-match**,避免短词("P0"/"DeepSeek")误匹配多处
- [x] `tool_result` 超 8K 截断,加 `⚠ 已截断` 标记 + 字符数提示

---

## 高优先级未修(下次开干)

### H1 · Stop hook async 并发竞写其他文件
**位置**:`jsonl2html.py` main 写 index.html / files.html / commands.html / workflows.html / 每个 `<sid>.html`
**问题**:settings.json 里 hook 是 `async: true`,两次 Stop 撞上同时写同一个 HTML 文件,可能写出半个。
**已部分修**:search-index.json 已经 atomic write。
**待修**:所有 HTML 输出也用 atomic write(tmp + rename),或加 pid lock(/tmp/jsonl2html.lock)。

### H2 · `--latest` 错配 session(假设 `rows[0]` = 当前 session)
**位置**:`jsonl2html.py` main `--latest` 分支
**问题**:Stop hook 没有把 `session_id` 传进来,脚本只能假设 mtime 最新 = 当前。如果用户在 A session 时手动后台 mv 了 B session 的 jsonl,Stop A 会错把 B 当 latest 重渲染,A 不更新。
**修法**:Stop hook command 改成 `python3 ... --latest ~/.claude/mirror --sid $SESSION_ID`,脚本读 stdin JSON 拿 `session_id`。

### H3 · 跨节点选段批注完全丢失
**位置**:`md2html.py highlightText`
**问题**:`TreeWalker SHOW_TEXT` 只在单个 textNode 里 `includes(text)`,选段一旦跨 `<p>`/`<strong>`/`<code>` 等元素边界,匹配失败,批注被悄悄吞。
**修法**:用 `root.textContent.indexOf` 全局找,再走 Range API 跨节点 wrap,或者退回"无法高亮但保留在批注列表"。

### H4 · `os.system(...)` 拼路径不安全
**位置**:`summarize.py:219`、`detail-summary.py:234`、`detail-summary.py:237`
**问题**:`os.system(f"open {sess_html}")` 若 sid / 路径含空格 / 特殊字符直接炸。
**修法**:统一改 `subprocess.run([sys.executable, ...], check=False)` 列表参数。

### H5 · `get_deepseek_key()` 两个 skill 重复实现
**位置**:`summarize.py` / `detail-summary.py` 各一份。
**修法**:提为共享模块 `_key_util.py`。当前重复但功能正确,优先级降。

---

## 中优先级未修

### M1 · build_rows + build_search_index_entries 重复扫 jsonl
**问题**:`--all` 时每个 jsonl 被 `parse_jsonl_for_metadata` + `session_meta` + `parse_jsonl_for_index` 扫 3 遍,30 session 慢 3x。
**修法**:合并到一次 pass,返回多个数据结构。

### M2 · search-index.json 5.2MB 内嵌 index.html,首屏阻塞
**问题**:浏览器 `JSON.parse` 5MB 阻塞 200-500ms。涨到 50MB 会卡死。
**修法**:拆 inverted index + lazy load,或外挂 fetch(file:// 协议限制)。

### M3 · 全局搜索 O(N×M) 每 keystroke
**位置**:`INDEX_JS doSearch`
**问题**:10W+ msg 时每输入 1 字符全量扫一遍。
**修法**:debounce 200ms + 简易 trigram 索引。

### M4 · md2html localStorage 满了静默失败
**问题**:`setItem` 超 5-10MB 配额抛异常,当前没 catch,用户感觉"批注保存了"实际丢了。
**修法**:try/catch + 提示用户导出 + 清理。

### M5 · 多 tab 改批注 race condition
**问题**:两个 tab 同时改批注 → 后写的 `setItem` 整体覆盖前一个的新增,前 tab 数据丢。
**修法**:`storage` 事件监听 + 重新载入合并。

### M6 · 触摸事件未适配(移动端批注用不了)
**位置**:`md2html.py mouseup`
**修法**:加 `touchend` + `selectionchange` 双轨。

### M7 · thinking blocks 没截断
**问题**:tool_result 已截断,但 thinking blocks 累积仍能让 HTML > 10MB(0d5a77fd 18MB 主因)。
**修法**:thinking > 4KB 截断,加展开提示。

### M8 · subagent 类型识别脆弱
**位置**:`parse_jsonl_for_metadata` `name in ("Task", "Agent")`
**问题**:`"Agent"` 是猜的 dead code;真要兜底应该看 `input.subagent_type` 字段存在。
**修法**:`if name == "Task" or inp.get("subagent_type")`。

### M9 · PII / secrets 泄漏风险
**位置**:tool_result / Bash command 原样进 HTML
**问题**:`.env` / API key 偶尔出现在 stderr / curl 调用里。19MB 的 session HTML grep `Bearer ` / `sk-` 大概率有命中。用户分享 / 备份 HTML 就是事故。
**修法**:加 redact 层,正则替换 `sk-[a-zA-Z0-9]+` / `ghp_*` / `Bearer .*` / `.dev.vars` 内容。

### M10 · closed-sessions.json 永远只增长
**问题**:几年下来上千条 dead entry。
**修法**:90 天 TTL,加载时过滤。

---

## 低优先级未修(看心情)

### L1 · CSS 内联到每个 HTML 重复
**问题**:30 个 session HTML × 16KB CSS = 重复 480KB。
**修法**:外链 `mirror.css` 一次。

### L2 · open 命令是 macOS only
**问题**:`os.system(f"open {sess_html}")` 在 Linux 用 `xdg-open` / Windows 用 `start`。
**修法**:`webbrowser.open(...)` 或按 `sys.platform` 分支。

### L3 · marked.js 安全
**问题**:`marked@12` 历史有 XSS issue。
**修法**:加 `marked.setOptions({mangle:false, headerIds:false})` + sanitize-html。

---

## Windows 跨平台改动清单

完整改完所有 H + 适配下面的:

| 位置 | 改法 |
|---|---|
| `settings.json` Stop hook command | `python3` → `sys.executable` 或写 wrapper script;`2>/dev/null \|\| true` 不兼容 cmd.exe |
| `summarize.py` / `detail-summary.py` fallback 路径 | 已通用化 |
| `os.system("open ...")` | webbrowser.open 或 platform 分支(L2) |
| `os.system(...)` 全部 | 改 subprocess.run 列表参数(H4) |
| `glob.glob("*/*.jsonl")` | win 路径分隔符,可能要 `os.path.join` |

---

## 设计割裂(以后重构)

- **md2html.py 跟 mirror viewer session HTML 不互通**:批注在 README 上,session HTML 看不到。理想:session 详情页也支持选段批注 → 直接 inject 进下轮 prompt(批注 → UserPromptSubmit hook 闭环)。但需要 daemon,跟封版冲突。

---

**总结**:本轮修了 5 个最致命的。剩 H1-H5 + M1-M10 + L1-L3 共 18 条,按优先级排进 TODO,按需修。

## 0.2.1 - 2026-05-15 · 用户上报修复

- **[H6] jsonl 文件编码容错** — 用户 chuyun 上报:某些 session 的 jsonl 含非 UTF-8 字节,`open(encoding="utf-8")` 直接 raise UnicodeDecodeError 导致渲染失败。修复:全部 jsonl 读取加 `errors="replace"`(`jsonl2html.py:190, 216, 334, 373`)。元数据 JSON 不动(那是我们自己生产的,fail-fast 更好)。
- **[L4] Python 3.12+ SyntaxWarning** — JS 嵌入 Python 字符串里的 regex `\d` / `\.` 在新版 Python 触发 SyntaxWarning(老版本只是 silent)。修复:所有此类 escape 改成 `\\d` / `\\.`(`jsonl2html.py:849, 901`)。
