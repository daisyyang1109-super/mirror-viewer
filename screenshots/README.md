# Screenshots

放 4 张图(.png 或 .jpg),让公开 README 看起来更有说服力:

| 文件名 | 推荐截哪个页面 | 重点突出 |
|---|---|---|
| `index.png` | `~/.claude/mirror/index.html` | session 列表 + 项目 chip + tag chip + 全局搜索框 + 状态徽章 |
| `session.png` | 单 session HTML(选个内容丰富的) | metadata card + 详细摘要 outline + msg 渲染 + Mermaid |
| `workflows.png` | `~/.claude/mirror/workflows.html` | 7 个 pattern 分组 + subagent / skill 统计 |
| `md-annotate.png` | 任意 .md 渲染版(`md README.md`) | TOC 浮动 + 选段批注 toolbar + 批注侧边面板 |

## 截图小贴士

- macOS: `Cmd+Shift+4` 拖选区域截,自动存桌面
- 暗色模式截会更好看(系统设置切暗)
- 1280×800 左右,避免太大
- 截好后:
  ```bash
  mv ~/Desktop/<screenshot>.png ~/projects/mirror-viewer/screenshots/<name>.png
  cd ~/projects/mirror-viewer && git add screenshots/ && git commit -m "docs: add screenshots" && git push
  ```
