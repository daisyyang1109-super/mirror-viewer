# Changelog

## [0.2.0] - 2026-05-14 · 数据修复 + 知识图谱导出 + 周报

### 新增
- **Skill: weekly-report** (`skills/weekly-report/`)
  - 读最近 N 天 session 摘要 + tags + 文件 + 命令 + token,DeepSeek 一次汇总
  - 7 节结构(主题 / 决策 / 项目 / 产出 / token 统计 / 工作模式 / 下周建议)
  - Python 端先算 ground truth,LLM 只填表不重新加 24 个数
  - 单 session 异常自动标 `⚠ 数据可疑`
- **知识图谱导出**(knowledge-graph.html)
  - 一键导出 Markdown 大纲(纯 tag 树,community → tag,session 不进图)
  - 一键导出思维导图 PNG(D3 horizontal tree + retina 2x,自动 clamp 16384 上限防爆)

### 修复(P0)
- **token total 公式去掉 cache_read** — 之前包含缓存命中字节数,单 session 数字虚高 50-130x
  - 例:某 session 5.5B → 真实 106M
- **duration 加 idle gap 过滤** — 同一 sessionId 跨多天 resume 时不再用 last-first wall clock,改成相邻 ts gap > 5min 跳过累加
  - 例:某 session 311h(13 天日历跨度)→ 75h(真实活跃时长)
- **fmt_tokens 加 B 后缀** — 10B+ 不再显示成 10020.8M
- **超长 badge 阈值重定标** — 从 100K 改为 500 条消息或 5M 真实 token

### 改进
- files / commands 反向索引表格用 `table-layout: fixed`,fpath 列 ellipsis + hover 展开,sids 列改 chip 样式 flex wrap
- 过滤 heredoc 续行 noise(`\\` 单字符等不再进命令索引)
- workflows.html tab nav 补全(知识图谱 link)

## [0.1.0] - 2026-05-14 · Initial release

### 主要功能

- **Mirror viewer 主体**(`jsonl2html.py`)
  - 实时镜像 Claude Code session 到 HTML(Stop hook 触发)
  - 多 session 列表(index.html)+ 时间倒序 + 项目自动分组
  - 3 档状态判定(活跃 / 不活跃 / 已关)
  - 跨 session 全局搜索 + session 内搜索
  - 文件反向索引(`files.html`)+ 命令反向索引(`commands.html`)
  - 工作流 pattern 识别(`workflows.html`)— 7 个通用 pattern + subagent / skill 统计
  - Session metadata card(项目 / cwd / token / 时长 / 文件 / 命令)
  - Mermaid 流程图渲染
  - Markdown 异步分批渲染(大 session 不卡)
  - 分页渲染(超 500 msg 自动隐藏老的,"加载更早"按钮)
  - 锚点跳转(`#msg-N` 自动展开 hidden msg)
  - 暗色模式 + 手动刷新按钮

- **Markdown 渲染器**(`md2html.py`)
  - 左侧 TOC 浮动 sidebar(自动滚动高亮当前章节)
  - 阅读优化样式(字体 / 间距 / 表格 / 代码块 / 引用)
  - 选段批注 4 类(👍 好 / 👎 不好 / 💡 建议 / ❓ 疑问)
  - 批注侧边面板(按类型分组 + 定位/编辑/删除)
  - 上下文锚定 + nth-match,避免短词误匹配
  - 导出 JSON 或 Markdown 摘要给 AI 改文档
  - localStorage 持久化

- **Skill: summarize-sessions**
  - `summarize.py` — 短摘要 + 5 个 tag(DeepSeek)
  - `detail-summary.py` — 详细 outline 多段(smart sampling 长 session 也能跑)

### QA Review 修过的关键 bug

- atomic write `search-index.json` 避免 async hook 并发损坏
- 全部 `open()` 显式 `encoding="utf-8"`(20 处)防 Windows 中文崩
- `mark-session-closed.py` 加 atomic + 错误打 stderr + 显式关文件
- Markdown 批注 highlightText 加上下文锚定 + nth-match
- `tool_result` 超 8K 截断 + 字符数提示

### 已知问题

详见 `ISSUES.md` — 23 条已识别,5 个最致命的已修,剩 18 条按优先级排进 TODO。

### 设计原则

详见 `README.md` 第 "设计原则" 一节。核心:
- 零 token 主体
- 静态 HTML 无 daemon
- mirror 是 viewer 不长 agent 能力
- 单文件可移植
