# mirror-viewer

> Claude Code session 的可视化 + 元数据管理 + 智能后处理工具。实时镜像 CLI 对话到 HTML(不替代 CLI),提供跨 session 全局搜索 / 项目分组 / 工作流 pattern 识别 / 短/详细摘要 / Markdown 批注等能力。

**关键特征**:

- **静态 HTML + 本地 Python**:没有 daemon,没有 server,没有 npm 依赖。一个脚本搞定
- **零 token**:viewer 主体不调任何 LLM。智能层(摘要 / 标签 / outline)走可选 skill,DeepSeek 单 session 约 ¥0.02
- **跟 CLI 共生不替代**:Stop hook 触发,你在终端继续干活,浏览器副屏看
- **跨 session 搜索**:全局搜索 / 文件反向 / 命令反向 / workflow pattern 识别
- **Markdown 批注**:任意 .md 文件 → 渲染 HTML + TOC + 选段批注(好/不好/建议/疑问)→ 导出给 AI 改文档

---

## 截图

(占位,补 screenshots/index.png + session.png + workflows.png)

---

## 它解决什么问题

你跑 Claude Code CLI 时常见的痛:

1. **终端滚屏丢失** —— 长对话 / 工具调用细节 / 表格 / diff 在终端里又长又看不清
2. **多 session 没法回看** —— 历史 jsonl 在 `~/.claude/projects/`,但裸 jsonl 无法浏览
3. **跨 session 找不回** —— "上次我和 AI 聊白素微 v5 是哪个 session?" 没工具能答
4. **重复工作** —— 不知道自己经常做什么 pattern,哪些可以自动化
5. **不知道 token 烧在哪** —— 哪个 session 最贵,哪些应该 `/clear`

mirror viewer 把这些一次性解决。

---

## 快速开始

### 1. 安装(2 分钟)

```bash
# clone
git clone https://github.com/daisyyang1109-super/mirror-viewer.git ~/mirror-viewer

# 跑一次全量渲染(扫所有 ~/.claude/projects/*/*.jsonl)
mkdir -p ~/.claude/mirror
python3 ~/mirror-viewer/jsonl2html.py --all ~/.claude/mirror

# 打开看
open ~/.claude/mirror/index.html
```

第一次跑会渲染所有历史 session,看到一个**多 session 列表**。

### 2. 实时镜像(加 Stop hook)

要让 mirror 跟你的 CLI 对话实时同步,加 Stop hook 到 `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/mirror-viewer/jsonl2html.py --latest ~/.claude/mirror 2>/dev/null || true",
            "async": true
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/mirror-viewer/hooks/mark-session-closed.py 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

之后每次 Claude Code 回复完,mirror viewer 自动渲染最新 session HTML。浏览器右下角点 **↻ 刷新** 看更新。

### 3. (可选)智能摘要 skill

如果想给每个 session 加一句话摘要 + 5 个标签 + 详细 outline:

```bash
# cp skill 到 ~/.claude/skills/
mkdir -p ~/.claude/skills/summarize-sessions
cp -r ~/mirror-viewer/skills/summarize-sessions/* ~/.claude/skills/summarize-sessions/

# 配置 DeepSeek API key(任一方式)
export DEEPSEEK_API_KEY=sk-xxx
# 或者
echo 'sk-xxx' > ~/.deepseek

# 跑短摘要(增量,只处理还没摘要的)
python3 ~/.claude/skills/summarize-sessions/summarize.py
# 或在 Claude Code 里输 /summarize-sessions

# 跑某 session 的详细 outline(多段主题 + 跳转锚点)
python3 ~/.claude/skills/summarize-sessions/detail-summary.py --sid <full-sid>
```

成本:DeepSeek 单 session 约 ¥0.02-0.05。

### 4. Markdown 批注(零 token)

```bash
# 把 md2html.py 加 alias 到 ~/.zshrc
md() {
  python3 ~/mirror-viewer/md2html.py "$1" "${2:-$(basename "$1" .md)}" "/tmp/md-render/$(basename "$1" .md).html"
  open "/tmp/md-render/$(basename "$1" .md).html"
}

# 用法
md ~/some-doc.md           # 渲染 + 打开浏览器
md ~/some-doc.md "标题"     # 自定义标题
```

特性:
- 左侧 TOC 浮动 sidebar,自动滚动高亮当前章节
- 选段批注(👍 好 / 👎 不好 / 💡 建议 / ❓ 疑问)
- localStorage 持久化(刷新不丢)
- 导出 JSON 或复制 Markdown 摘要给 AI 改

---

## 主要功能

### `jsonl2html.py` · 主脚本

| 功能 | 说明 |
|---|---|
| **多 session 列表**(`index.html`) | 时间倒序,项目自动分组,3 档状态(活跃/不活跃/已关),超长 session 标记 |
| **跨 session 全局搜索** | excerpt 高亮 + 跳转 + URL hash 持久化 |
| **session 内搜索** | 多关键词 AND + 高亮 |
| **session metadata card** | 项目 / cwd / 工具调用次数 / token 细分 / 时长 / 文件 / 命令 |
| **文件反向索引**(`files.html`) | 每个文件被哪些 session 改过 |
| **命令反向索引**(`commands.html`) | 每条 Bash 命令在哪些 session 跑过 |
| **工作流 pattern**(`workflows.html`) | 7 个通用 pattern 自动识别 + subagent / skill 调用统计 |
| **Mermaid 流程图渲染** | 对话里的 ` ```mermaid ` block 自动渲染为 SVG |
| **分页 + 锚点** | 超 500 msg 自动隐藏老 msg,"加载更早"按钮,锚点跳转自动展开 |
| **暗色模式 + 手动刷新** | 跟系统模式 + 右下角刷新按钮 |

### `md2html.py` · Markdown 渲染 + 批注

| 功能 | 说明 |
|---|---|
| **TOC 左侧浮动 sidebar** | 自动扫 h2/h3,smooth scroll,active 高亮 |
| **阅读优化样式** | 字体 / 行高 / 标题层级 / 表格斑马 / 代码块 / 引用块 / 链接 |
| **选段批注 4 类** | 👍 好 / 👎 不好 / 💡 建议 / ❓ 疑问 |
| **批注侧边面板** | 按类型分组,问题优先,可定位/编辑/删除 |
| **导出给 AI** | 下载 JSON 或剪贴板 Markdown 摘要 |
| **跨刷新持久化** | localStorage 按文件名 key |

### `summarize-sessions/` · LLM 智能层(可选)

| 功能 | 成本(DeepSeek) |
|---|---|
| **短摘要 + 5 个标签** (`summarize.py`) | ~¥0.015/session |
| **详细摘要 outline** (`detail-summary.py`) | ~¥0.05/session,smart sampling 长 session 也能处理 |

---

## 跟其他工具的对比

| 工具 | 我的定位 | 跟 mirror-viewer 的区别 |
|---|---|---|
| `claude-code-viewer` (d-kimuson) | web-based viewer + 内嵌 chat | 它默认是 chat 客户端,watch live 是附加功能;mirror-viewer 是**纯镜像**,完全不替代 CLI |
| `cclogviewer` (Brads3290) | 单文件 jsonl → HTML | 单 session,没多 session 列表 / 搜索 / pattern |
| `claude-code-history-viewer` (jhlee0409) | desktop app,跨多 CLI | 历史 viewer,没实时同步,没批注,没 skill |
| `sugyan/claude-code-webui` | web chat 替代品 | 是 chat 客户端,不是 mirror |

mirror-viewer 的窄缝:**实时 mirror + 跨 session 元数据分析 + 零依赖 + 静态 HTML**。

---

## 设计原则

1. **零 token 优先** —— viewer 不调 LLM,所有 metadata 程序化抽取
2. **静态 HTML** —— file:// 打开,无 daemon 无 server,重启即恢复
3. **mirror 是 viewer,不长 agent 能力** —— LLM 调用全走 skill,主进程或人手动 invoke
4. **通用化优先** —— 不绑特定项目,pattern 关键词跨语言/跨技术栈
5. **单文件可移植** —— `jsonl2html.py` 1500+ 行,故意不分模块,方便维护和移植
6. **不长 daemon** —— 任何要 daemon 的功能(批注同步、resume 命令等)必须充分论证再做

---

## 系统要求

- macOS / Linux(Windows 部分功能受限,见 `ISSUES.md` 的 Windows 跨平台清单)
- Python 3.8+(macOS 自带)
- Claude Code v2.1+
- (可选)DeepSeek API key 给 skill 用

---

## 已知问题

详见 `ISSUES.md`。当前 23 个已识别问题,5 个最致命的已修,18 个按优先级排进 TODO。

---

## License

MIT

---

## 一些 trivia

- 开发周期:**一晚上 30 行 Python 跑通初版,几天加齐所有功能**
- 总代码量:**~2200 行 Python + JS + CSS**(主要在 `jsonl2html.py` 一个文件)
- 灵感:Claude Code 用 CLI 时受不了终端滚屏丢失
- 不解决的问题:不解决 chat 替代品的事(已有 sugyan/claude-code-webui 等),不解决跨 CLI 适配(已有 jhlee0409 等),不解决 IDE 集成(已有 Cursor 等)
