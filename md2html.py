#!/usr/bin/env python3
"""Markdown → HTML 渲染器,含 TOC 浮动 sidebar + 阅读优化样式。

Usage:
  python3 md2html.py <input.md> [title] [output.html]
"""
import sys, html

src_path = sys.argv[1]
title = sys.argv[2] if len(sys.argv) > 2 else "Document"
out_path = sys.argv[3] if len(sys.argv) > 3 else src_path.replace('.md', '.html')

src = open(src_path, encoding="utf-8").read()

tpl = """<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/turndown@7.1.3/dist/turndown.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@joplin/turndown-plugin-gfm@1.0.59/dist/turndown-plugin-gfm.min.js"></script>
<style>
:root{color-scheme:light dark; --bg:#fafaf8; --fg:#1d1d1f; --muted:#6e6e73; --accent:#36c; --border:#0001; --code-bg:#f3f3f0; --pre-bg:#f6f6f3; --table-stripe:#fafafa; --table-hover:#f0f4ff; --bq-bg:#f0f4ff}
@media(prefers-color-scheme:dark){:root{--bg:#1a1a1a; --fg:#ececec; --muted:#9a9a9a; --accent:#69b1ff; --border:#fff2; --code-bg:#252525; --pre-bg:#1f1f1f; --table-stripe:#222; --table-hover:#1a2540; --bq-bg:#1a2540}}

*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.75 -apple-system,BlinkMacSystemFont,'SF Pro Text','Helvetica Neue',sans-serif;font-feature-settings:'liga' 1,'kern' 1;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}

.layout{display:flex;max-width:1280px;margin:0 auto;padding:32px 40px 80px;gap:48px}
.content{flex:1;min-width:0;max-width:780px}

/* TOC sidebar */
.toc{position:sticky;top:32px;width:240px;max-height:calc(100vh - 64px);overflow-y:auto;flex-shrink:0;align-self:flex-start;font-size:13px;padding:16px 18px;border:1px solid var(--border);border-radius:10px;background:color-mix(in srgb, var(--bg) 90%, transparent);backdrop-filter:blur(8px)}
.toc-title{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:10px;font-weight:600}
.toc ul{list-style:none;padding:0;margin:0}
.toc li{margin:0}
.toc a{display:block;color:var(--muted);text-decoration:none;line-height:1.45;padding:5px 10px 5px 12px;border-left:2px solid transparent;border-radius:0 4px 4px 0;transition:all 0.15s}
.toc a:hover{color:var(--accent);border-left-color:var(--accent)}
.toc a.active{color:var(--accent);border-left-color:var(--accent);font-weight:600;background:color-mix(in srgb, var(--accent) 8%, transparent)}
.toc-h2>a{font-weight:500;font-size:13px}
.toc-h3>a{font-size:12px;padding-left:28px;opacity:0.8}
.toc-h3>a::before{content:"·";margin-right:6px;color:var(--muted);opacity:0.6}
.toc-h3>a.active{opacity:1}

@media(max-width:1024px){.toc{width:200px;font-size:12px}.layout{padding:24px 28px;gap:32px}}
@media(max-width:768px){.toc{display:none}.layout{padding:20px;max-width:780px}.content{max-width:none}}

/* 标题层级 */
h1,h2,h3,h4,h5,h6{line-height:1.3;letter-spacing:-0.01em;color:var(--fg)}
h1{font-size:32px;font-weight:700;margin:0.5em 0 0.6em;padding-bottom:0.4em;border-bottom:2px solid var(--border)}
h2{font-size:24px;font-weight:650;margin:2.2em 0 0.6em;padding-bottom:0.3em;border-bottom:1px solid var(--border)}
h3{font-size:18px;font-weight:600;margin:1.8em 0 0.5em;color:color-mix(in srgb, var(--fg) 90%, var(--accent))}
h4{font-size:15px;font-weight:600;margin:1.4em 0 0.4em}
h2::before{content:"";display:inline-block;width:4px;height:0.85em;background:var(--accent);margin-right:10px;vertical-align:middle;border-radius:2px}

p{margin:0.9em 0}
strong{font-weight:650;color:color-mix(in srgb, var(--fg) 95%, var(--accent))}

code{background:var(--code-bg);padding:2px 7px;border-radius:4px;font-size:0.88em;font-family:ui-monospace,'SF Mono','Cascadia Code','JetBrains Mono',monospace;color:color-mix(in srgb, var(--fg) 80%, var(--accent))}
pre{background:var(--pre-bg);padding:16px 18px;border-radius:10px;overflow-x:auto;font-size:13.5px;line-height:1.6;border:1px solid var(--border);box-shadow:0 1px 3px rgba(0,0,0,0.04);margin:1.2em 0}
pre code{background:transparent;padding:0;font-size:inherit;color:var(--fg)}

table{border-collapse:separate;border-spacing:0;width:100%;margin:1.4em 0;font-size:14px;border:1px solid var(--border);border-radius:8px;overflow:hidden}
th{background:var(--code-bg);font-weight:600;text-align:left;padding:10px 14px;font-size:13px;color:var(--fg);border-bottom:1px solid var(--border)}
td{padding:10px 14px;border-bottom:1px solid var(--border);vertical-align:top;font-size:14px;line-height:1.6}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--table-hover)}
tbody tr:nth-child(even) td{background:var(--table-stripe)}
tbody tr:nth-child(even):hover td{background:var(--table-hover)}
td code,th code{font-size:0.86em}

ul,ol{padding-left:1.7em;margin:0.6em 0}
li{margin:0.4em 0;line-height:1.7}
li>p:first-child{margin-top:0}
li>p:last-child{margin-bottom:0}
ul ul,ol ol,ul ol,ol ul{margin:0.2em 0}
li input[type=checkbox]{margin-right:8px;transform:scale(1.1);accent-color:var(--accent)}

blockquote{margin:1.4em 0;padding:12px 18px;border-left:4px solid var(--accent);background:var(--bq-bg);border-radius:0 6px 6px 0;color:color-mix(in srgb, var(--fg) 92%, transparent)}
blockquote p:first-child{margin-top:0}
blockquote p:last-child{margin-bottom:0}

a{color:var(--accent);text-decoration:none;border-bottom:1px solid transparent;transition:border-color 0.15s}
a:hover{border-bottom-color:var(--accent)}

hr{border:0;border-top:1px solid var(--border);margin:2.5em 0}
img{max-width:100%;border-radius:8px;margin:1em 0}

:target{animation:flash 1.5s ease-out}
@keyframes flash{0%{background:color-mix(in srgb, var(--accent) 25%, transparent)}100%{background:transparent}}

.toc::-webkit-scrollbar{width:6px}
.toc::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.toc::-webkit-scrollbar-thumb:hover{background:var(--muted)}

/* 批注 toolbar 浮动条 */
.ann-toolbar{position:fixed;display:none;background:#222;border-radius:8px;padding:6px;box-shadow:0 4px 16px rgba(0,0,0,0.3);z-index:1000;gap:4px;align-items:center}
.ann-toolbar.show{display:inline-flex}
.ann-toolbar button{background:transparent;border:none;color:#fff;cursor:pointer;font-size:18px;padding:6px 10px;border-radius:4px;transition:background 0.15s;line-height:1}
.ann-toolbar button:hover{background:rgba(255,255,255,0.15)}
.ann-toolbar button.good:hover{background:#2a7}
.ann-toolbar button.bad:hover{background:#c44}
.ann-toolbar button.suggest:hover{background:#c80}
.ann-toolbar button.question:hover{background:#69b}
.ann-toolbar .sep{width:1px;background:#fff3;height:20px;margin:0 2px}

/* 批注高亮 */
.ann-mark{padding:0 2px;border-radius:3px;cursor:pointer;position:relative;border-bottom:2px solid;transition:filter 0.15s}
.ann-mark:hover{filter:brightness(1.15)}
.ann-mark[data-type=good]{background:rgba(42,170,80,0.18);border-bottom-color:#2a7}
.ann-mark[data-type=bad]{background:rgba(204,68,68,0.18);border-bottom-color:#c44}
.ann-mark[data-type=suggest]{background:rgba(204,136,0,0.18);border-bottom-color:#c80}
.ann-mark[data-type=question]{background:rgba(102,153,187,0.18);border-bottom-color:#69b}

/* 批注侧边面板 */
.ann-panel{position:fixed;right:20px;bottom:80px;width:300px;max-height:60vh;overflow-y:auto;background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px;box-shadow:0 4px 20px rgba(0,0,0,0.15);z-index:100;font-size:13px;display:none}
.ann-panel.open{display:block}
.ann-panel-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.ann-panel-title{font-weight:600;font-size:13px}
.ann-panel-close{cursor:pointer;background:none;border:none;color:var(--muted);font-size:18px;line-height:1}
.ann-list-item{margin:8px 0;padding:8px 10px;background:color-mix(in srgb, var(--fg) 4%, transparent);border-radius:6px;border-left:3px solid;font-size:12px}
.ann-list-item[data-type=good]{border-left-color:#2a7}
.ann-list-item[data-type=bad]{border-left-color:#c44}
.ann-list-item[data-type=suggest]{border-left-color:#c80}
.ann-list-item[data-type=question]{border-left-color:#69b}
.ann-list-text{color:var(--muted);font-size:11px;line-height:1.4;margin-bottom:4px;font-style:italic;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.ann-list-comment{font-size:12px;line-height:1.5}
.ann-list-actions{margin-top:6px;display:flex;gap:8px}
.ann-list-actions button{font-size:10px;background:none;border:1px solid var(--border);padding:2px 6px;border-radius:3px;cursor:pointer;color:var(--muted)}
.ann-list-actions button:hover{color:var(--accent);border-color:var(--accent)}

/* 批注控制按钮(fab) */
.ann-fab{position:fixed;right:20px;bottom:20px;background:var(--accent);color:#fff;border:none;border-radius:24px;padding:10px 16px;font-size:13px;font-weight:500;cursor:pointer;box-shadow:0 2px 12px rgba(0,0,0,0.2);z-index:99;display:flex;align-items:center;gap:8px}
.ann-fab:hover{filter:brightness(1.1)}
.ann-fab-count{background:rgba(255,255,255,0.25);padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}

/* 批注添加 dialog */
.ann-dialog{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:20px;box-shadow:0 8px 32px rgba(0,0,0,0.25);z-index:1001;min-width:380px;max-width:520px;display:none}
.ann-dialog.show{display:block}
.ann-dialog-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:1000;display:none}
.ann-dialog-overlay.show{display:block}
.ann-dialog h3{margin:0 0 8px;font-size:15px}
.ann-dialog .ann-selected{background:var(--code-bg);padding:8px 10px;border-radius:6px;font-size:12px;color:var(--muted);max-height:80px;overflow-y:auto;margin-bottom:12px;border-left:3px solid var(--accent);font-style:italic;line-height:1.5}
.ann-dialog textarea{width:100%;min-height:80px;padding:8px 10px;font:13px/1.5 inherit;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);resize:vertical;box-sizing:border-box}
.ann-dialog .ann-dialog-actions{margin-top:12px;display:flex;gap:8px;justify-content:flex-end}
.ann-dialog button{padding:7px 14px;font-size:13px;border-radius:6px;cursor:pointer;border:1px solid var(--border);background:transparent;color:var(--fg)}
.ann-dialog button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.ann-dialog button:hover{filter:brightness(0.95)}

/* 编辑模式 */
#root[contenteditable=true]{outline:2px dashed var(--accent);outline-offset:8px;border-radius:8px;padding:8px;background:color-mix(in srgb, var(--accent) 3%, transparent);min-height:200px}
#root[contenteditable=true]:focus{outline-color:#3a7;outline-style:solid}
.edit-mode-banner{position:fixed;top:0;left:0;right:0;background:#3a7;color:#fff;padding:6px 14px;font-size:12px;text-align:center;z-index:1100;display:none;font-weight:500}
.edit-mode-banner.show{display:block}
.edit-mode-banner button{background:rgba(255,255,255,0.2);color:#fff;border:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:11px;margin-left:10px}
.edit-fab{position:fixed;right:20px;bottom:70px;background:#3a7;color:#fff;border:none;border-radius:24px;padding:10px 16px;font-size:13px;font-weight:500;cursor:pointer;box-shadow:0 2px 12px rgba(0,0,0,0.2);z-index:99;display:flex;align-items:center;gap:6px}
.edit-fab:hover{filter:brightness(1.1)}
.edit-fab.active{background:#c44}
.export-md-btn{position:fixed;right:160px;bottom:20px;background:transparent;color:var(--accent);border:1px solid var(--accent);border-radius:24px;padding:10px 16px;font-size:13px;font-weight:500;cursor:pointer;z-index:99;display:none}
.export-md-btn.show{display:block}
.export-md-btn:hover{background:var(--accent);color:#fff}
</style></head><body>
<div class="layout">
<aside class="toc"><div class="toc-title">目录</div><ul id="toc-list"></ul></aside>
<main class="content"><div id="root"></div></main>
</div>

<div class="ann-toolbar" id="ann-toolbar">
<button class="good" data-type="good" title="标好">👍</button>
<button class="bad" data-type="bad" title="标不好">👎</button>
<button class="suggest" data-type="suggest" title="改建议">💡</button>
<button class="question" data-type="question" title="有疑问">❓</button>
</div>

<div class="ann-panel" id="ann-panel">
<div class="ann-panel-head">
<span class="ann-panel-title">批注 <span id="ann-panel-count">0</span></span>
<button class="ann-panel-close" id="ann-panel-close">×</button>
</div>
<div id="ann-list"></div>
<div style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap">
<button id="ann-export-json" style="flex:1;min-width:0;padding:6px 8px;font-size:11px;background:var(--accent);color:#fff;border:none;border-radius:5px;cursor:pointer">下载 JSON</button>
<button id="ann-copy-md" style="flex:1;min-width:0;padding:6px 8px;font-size:11px;background:transparent;color:var(--accent);border:1px solid var(--accent);border-radius:5px;cursor:pointer">复制 Markdown</button>
<button id="ann-clear" style="padding:6px 8px;font-size:11px;background:transparent;color:#c44;border:1px solid #c44;border-radius:5px;cursor:pointer">清空</button>
</div>
</div>

<button class="ann-fab" id="ann-fab">📝 批注 <span class="ann-fab-count" id="ann-fab-count">0</span></button>
<button class="edit-fab" id="edit-fab" title="切换编辑模式 · 像 Word 一样改文档">✏ 编辑</button>
<button class="export-md-btn" id="export-md-btn" title="导出当前修改回 .md 文件">💾 导出 MD</button>

<div class="edit-mode-banner" id="edit-mode-banner">
✏ 编辑模式 · 点文本直接改 · 改完点右下角「导出 MD」下载新文件
<button id="exit-edit-mode">退出编辑</button>
</div>

<div class="ann-dialog-overlay" id="ann-dialog-overlay"></div>
<div class="ann-dialog" id="ann-dialog">
<h3 id="ann-dialog-title">添加批注</h3>
<div class="ann-selected" id="ann-dialog-selected"></div>
<textarea id="ann-dialog-comment" placeholder="补充说明(可选)...例如:这段逻辑不对/改成 X 会更好/为什么这样写?"></textarea>
<div class="ann-dialog-actions">
<button id="ann-dialog-cancel">取消</button>
<button id="ann-dialog-confirm" class="primary">保存批注</button>
</div>
</div>

<script id="md-src" type="text/plain">__MD_SRC__</script>
<script>
const raw = document.getElementById('md-src').textContent;
const root = document.getElementById('root');
root.innerHTML = marked.parse(raw);

const headings = root.querySelectorAll('h2, h3');
const tocList = document.getElementById('toc-list');
const tocMap = {};
headings.forEach((h, i) => {
  const id = 'h-' + i;
  h.id = id;
  const li = document.createElement('li');
  li.className = 'toc-' + h.tagName.toLowerCase();
  const a = document.createElement('a');
  a.href = '#' + id;
  a.textContent = h.textContent;
  li.appendChild(a);
  tocList.appendChild(li);
  tocMap[id] = a;
});

if (headings.length > 0) {
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      const a = tocMap[entry.target.id];
      if (!a) return;
      if (entry.isIntersecting) {
        Object.values(tocMap).forEach(x => x.classList.remove('active'));
        a.classList.add('active');
        const tocEl = a.closest('.toc');
        if (tocEl) {
          const aRect = a.getBoundingClientRect();
          const tocRect = tocEl.getBoundingClientRect();
          if (aRect.top < tocRect.top || aRect.bottom > tocRect.bottom) {
            a.scrollIntoView({block: 'nearest'});
          }
        }
      }
    });
  }, { rootMargin: '-80px 0px -70% 0px', threshold: 0 });
  headings.forEach(h => observer.observe(h));
}

if (location.hash) {
  setTimeout(() => {
    const target = document.getElementById(location.hash.slice(1));
    if (target) target.scrollIntoView({block: 'start'});
  }, 50);
}

// ========== 批注系统 ==========
const FILE_KEY = '__FILE_KEY__';
const STORAGE_KEY = 'annotations:' + FILE_KEY;
const TYPE_META = {
  good:     { icon: '👍', name: '好',   color: '#2a7' },
  bad:      { icon: '👎', name: '不好', color: '#c44' },
  suggest:  { icon: '💡', name: '建议', color: '#c80' },
  question: { icon: '❓', name: '疑问', color: '#69b' },
};

let annotations = [];
try { annotations = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch {}

function saveAnnotations() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(annotations));
  updateCounts();
}

function updateCounts() {
  document.getElementById('ann-fab-count').textContent = annotations.length;
  document.getElementById('ann-panel-count').textContent = annotations.length;
}

// 工具栏:选段触发
const toolbar = document.getElementById('ann-toolbar');
let lastRange = null;
let lastText = '';

document.addEventListener('mouseup', (e) => {
  if (e.target.closest('.ann-toolbar, .ann-dialog, .ann-panel, .ann-fab')) return;
  setTimeout(() => {
    const sel = window.getSelection();
    const text = sel.toString().trim();
    if (!text || text.length < 3) {
      toolbar.classList.remove('show');
      return;
    }
    if (!root.contains(sel.anchorNode)) {
      toolbar.classList.remove('show');
      return;
    }
    lastRange = sel.getRangeAt(0).cloneRange();
    lastText = text;
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    toolbar.style.left = Math.min(rect.right + 8, window.innerWidth - 200) + 'px';
    toolbar.style.top = Math.max(rect.top - 50, 10) + 'px';
    toolbar.classList.add('show');
  }, 10);
});

document.addEventListener('mousedown', (e) => {
  if (!e.target.closest('.ann-toolbar')) {
    toolbar.classList.remove('show');
  }
});

// 工具栏按钮 → 打开 dialog
toolbar.querySelectorAll('button').forEach(btn => {
  btn.addEventListener('click', () => {
    const type = btn.dataset.type;
    openDialog(type, lastText);
    toolbar.classList.remove('show');
  });
});

// Dialog
const dialog = document.getElementById('ann-dialog');
const overlay = document.getElementById('ann-dialog-overlay');
const dlgTitle = document.getElementById('ann-dialog-title');
const dlgSelected = document.getElementById('ann-dialog-selected');
const dlgComment = document.getElementById('ann-dialog-comment');
let dlgType = '';
let dlgText = '';
let dlgEditId = null;

function openDialog(type, text, editId) {
  dlgType = type;
  dlgText = text;
  dlgEditId = editId || null;
  const meta = TYPE_META[type];
  dlgTitle.textContent = (editId ? '编辑' : '添加') + ' ' + meta.icon + ' ' + meta.name + ' 批注';
  dlgSelected.textContent = text;
  if (editId) {
    const existing = annotations.find(a => a.id === editId);
    dlgComment.value = existing ? existing.comment : '';
  } else {
    dlgComment.value = '';
  }
  dialog.classList.add('show');
  overlay.classList.add('show');
  setTimeout(() => dlgComment.focus(), 50);
}

function closeDialog() {
  dialog.classList.remove('show');
  overlay.classList.remove('show');
}

document.getElementById('ann-dialog-cancel').addEventListener('click', closeDialog);
overlay.addEventListener('click', closeDialog);
document.getElementById('ann-dialog-confirm').addEventListener('click', () => {
  const comment = dlgComment.value.trim();
  if (dlgEditId) {
    const a = annotations.find(x => x.id === dlgEditId);
    if (a) { a.comment = comment; a.timestamp = new Date().toISOString(); }
  } else {
    // 存上下文锚定 — 用 TreeWalker 视角数 nth(B5,跟 highlightText 对齐)
    // 在 lastRange.startContainer 之前的 textNodes 里数 dlgText 出现次数
    let nth = 0;
    if (lastRange && lastRange.startContainer) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
      let n;
      while ((n = walker.nextNode())) {
        if (n === lastRange.startContainer) {
          // 同节点内,数到 startOffset 之前的出现
          const before = n.nodeValue.slice(0, lastRange.startOffset);
          let pos = 0;
          while ((pos = before.indexOf(dlgText, pos)) !== -1) { nth++; pos += dlgText.length; }
          break;
        }
        let pos = 0;
        while ((pos = n.nodeValue.indexOf(dlgText, pos)) !== -1) { nth++; pos += dlgText.length; }
      }
    }
    const fullText = root.textContent;
    const firstIdx = fullText.indexOf(dlgText);
    const startIdx = (() => {
      let pos = 0; let i = 0;
      while ((pos = fullText.indexOf(dlgText, pos)) !== -1) {
        if (i === nth) return pos;
        i++; pos += dlgText.length;
      }
      return firstIdx;
    })();
    annotations.push({
      id: 'ann-' + Date.now() + '-' + Math.random().toString(36).slice(2,7),
      type: dlgType,
      selected_text: dlgText,
      comment: comment,
      timestamp: new Date().toISOString(),
      anchor: {
        before: startIdx > 0 ? fullText.slice(Math.max(0, startIdx - 30), startIdx) : '',
        after: fullText.slice(startIdx + dlgText.length, startIdx + dlgText.length + 30),
        nth: nth,
      },
    });
  }
  saveAnnotations();
  renderAnnotationList();
  highlightAllAnnotations();
  closeDialog();
  window.getSelection().removeAllRanges();
});

// 高亮原文里所有批注
function highlightAllAnnotations() {
  // 先清掉所有现有 mark
  root.querySelectorAll('.ann-mark').forEach(m => {
    const txt = document.createTextNode(m.textContent);
    m.replaceWith(txt);
  });
  root.normalize();
  // 按 selected_text 在原文里找,加 mark;找不到打 _orphan flag(原文被改过)
  let orphanCount = 0;
  annotations.forEach(a => {
    const ok = highlightText(a.selected_text, a.type, a.id, a.anchor);
    a._orphan = !ok;
    if (!ok) orphanCount++;
  });
  // 更新 fab count 显示 (含 orphan 提示)
  const fcEl = document.getElementById('ann-fab-count');
  if (fcEl && orphanCount > 0) {
    fcEl.textContent = annotations.length + ' (' + orphanCount + ' 失定位)';
    fcEl.style.background = 'rgba(255,200,0,0.4)';
  } else if (fcEl) {
    fcEl.style.background = '';
  }
}

function highlightText(text, type, id, anchorContext) {
  // 上下文锚定:anchorContext = {before:前 30 字, after:后 30 字, nth:第几次匹配}
  // 在原文里找所有匹配,选最接近上下文的那个,避免短词("P0"/"DeepSeek")误标
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  const matches = [];
  let n;
  while ((n = walker.nextNode())) {
    let pos = 0;
    while ((pos = n.nodeValue.indexOf(text, pos)) !== -1) {
      matches.push({node: n, offset: pos});
      pos += text.length;
    }
  }
  if (!matches.length) return false;
  // 选最接近 anchor 的匹配
  let best = matches[0];
  if (anchorContext && matches.length > 1) {
    // 算每个匹配点的上下文跟存的 anchor 距离,取最近
    let bestScore = -1;
    for (const m of matches) {
      const fullText = root.textContent;
      const globalIdx = fullText.indexOf(text, m.offset);  // 近似
      const before = fullText.slice(Math.max(0, globalIdx - 30), globalIdx);
      const after = fullText.slice(globalIdx + text.length, globalIdx + text.length + 30);
      let score = 0;
      if (anchorContext.before && before.includes(anchorContext.before.slice(-15))) score += 2;
      if (anchorContext.after && after.includes(anchorContext.after.slice(0, 15))) score += 2;
      if (anchorContext.nth !== undefined && matches.indexOf(m) === anchorContext.nth) score += 1;
      if (score > bestScore) { bestScore = score; best = m; }
    }
  }
  const node = best.node;
  const idx = best.offset;
  const before = node.nodeValue.slice(0, idx);
  const after = node.nodeValue.slice(idx + text.length);
  const parent = node.parentNode;
  const mark = document.createElement('span');
  mark.className = 'ann-mark';
  mark.dataset.type = type;
  mark.dataset.id = id;
  mark.textContent = text;
  mark.title = (TYPE_META[type] || {}).name + ' · 点击查看/编辑';
  mark.addEventListener('click', () => scrollToAnnotation(id));
  if (before) parent.insertBefore(document.createTextNode(before), node);
  parent.insertBefore(mark, node);
  if (after) parent.insertBefore(document.createTextNode(after), node);
  parent.removeChild(node);
  return true;
}

// 批注列表面板
const panel = document.getElementById('ann-panel');
const annList = document.getElementById('ann-list');
const fab = document.getElementById('ann-fab');

fab.addEventListener('click', () => {
  panel.classList.toggle('open');
});
document.getElementById('ann-panel-close').addEventListener('click', () => panel.classList.remove('open'));

function renderAnnotationList() {
  annList.innerHTML = '';
  if (!annotations.length) {
    annList.innerHTML = '<div style="color:var(--muted);font-size:12px;text-align:center;padding:16px">还没有批注</div>';
    return;
  }
  // 按 type 分组
  const groups = { good: [], bad: [], suggest: [], question: [] };
  annotations.forEach(a => groups[a.type]?.push(a));
  ['bad', 'suggest', 'question', 'good'].forEach(type => {
    const items = groups[type] || [];
    if (!items.length) return;
    const meta = TYPE_META[type];
    const head = document.createElement('div');
    head.style.cssText = 'font-size:11px;color:var(--muted);margin:8px 0 4px;text-transform:uppercase;letter-spacing:0.5px;font-weight:600';
    head.textContent = meta.icon + ' ' + meta.name + ' (' + items.length + ')';
    annList.appendChild(head);
    items.forEach(a => {
      const div = document.createElement('div');
      div.className = 'ann-list-item';
      div.dataset.type = a.type;
      const orphanHint = a._orphan ? '<div style="font-size:10px;color:#c80;margin-top:3px">⚠ 原文已改,无法定位高亮(批注内容仍保留)</div>' : '';
      div.innerHTML = `
        <div class="ann-list-text">"${escapeHTML(a.selected_text.slice(0,80))}${a.selected_text.length>80?'…':''}"</div>
        ${a.comment ? '<div class="ann-list-comment">'+escapeHTML(a.comment)+'</div>' : ''}
        ${orphanHint}
        <div class="ann-list-actions">
          <button data-action="goto" ${a._orphan ? 'disabled' : ''}>定位</button>
          <button data-action="edit">编辑</button>
          <button data-action="delete">删除</button>
        </div>
      `;
      div.querySelector('[data-action=goto]').onclick = () => scrollToAnnotation(a.id);
      div.querySelector('[data-action=edit]').onclick = () => openDialog(a.type, a.selected_text, a.id);
      div.querySelector('[data-action=delete]').onclick = () => {
        if (confirm('删除这条批注?')) {
          annotations = annotations.filter(x => x.id !== a.id);
          saveAnnotations();
          renderAnnotationList();
          highlightAllAnnotations();
        }
      };
      annList.appendChild(div);
    });
  });
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function scrollToAnnotation(id) {
  const mark = root.querySelector('.ann-mark[data-id="'+id+'"]');
  if (mark) {
    mark.scrollIntoView({block: 'center', behavior: 'smooth'});
    mark.style.outline = '3px solid var(--accent)';
    setTimeout(() => { mark.style.outline = ''; }, 1500);
  }
}

// 导出
document.getElementById('ann-export-json').addEventListener('click', () => {
  const data = {
    file: FILE_KEY,
    exported_at: new Date().toISOString(),
    count: annotations.length,
    annotations: annotations,
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = FILE_KEY.replace(/\\.md$/,'') + '.annotations.json';
  a.click();
  URL.revokeObjectURL(url);
});

document.getElementById('ann-copy-md').addEventListener('click', () => {
  if (!annotations.length) { alert('还没有批注'); return; }
  const lines = ['# 批注 · ' + FILE_KEY, '生成于 ' + new Date().toLocaleString(), '共 ' + annotations.length + ' 条', ''];
  const groups = { bad: [], suggest: [], question: [], good: [] };
  annotations.forEach(a => groups[a.type]?.push(a));
  ['bad', 'suggest', 'question', 'good'].forEach(type => {
    const items = groups[type] || [];
    if (!items.length) return;
    const meta = TYPE_META[type];
    lines.push('## ' + meta.icon + ' ' + meta.name + ' (' + items.length + ')\\n');
    items.forEach(a => {
      lines.push('- 选段: "' + a.selected_text.replace(/\\n/g, ' ').slice(0,200) + '"');
      if (a.comment) lines.push('  评语: ' + a.comment);
      lines.push('');
    });
  });
  const text = lines.join('\\n');
  navigator.clipboard.writeText(text).then(() => {
    alert('已复制到剪贴板,粘贴给 Claude 就能让它读批注改 md');
  }, () => {
    prompt('手动复制:', text);
  });
});

document.getElementById('ann-clear').addEventListener('click', () => {
  if (annotations.length === 0) return;
  if (confirm('清空所有批注?不可撤销')) {
    annotations = [];
    saveAnnotations();
    renderAnnotationList();
    highlightAllAnnotations();
  }
});

// 初始化
renderAnnotationList();
highlightAllAnnotations();
updateCounts();

// ========== 编辑模式 ==========
const editFab = document.getElementById('edit-fab');
const editBanner = document.getElementById('edit-mode-banner');
const exitEditBtn = document.getElementById('exit-edit-mode');
const exportMdBtn = document.getElementById('export-md-btn');
// C4: key 含路径 hash 避免重名文件草稿冲突
function _hashStr(s) { let h=5381; for (let i=0;i<s.length;i++) h=((h<<5)+h+s.charCodeAt(i))|0; return Math.abs(h).toString(36); }
const FILE_KEY_HASHED = FILE_KEY + ':' + _hashStr(location.pathname + FILE_KEY);
const EDIT_STORAGE_KEY = 'edit-draft:' + FILE_KEY_HASHED;

// 自动保存草稿到 localStorage(防丢失)
let editAutoSaveTimer;
let draftSaveWarned = false;
let lastSelfSaveTime = 0;  // 本 tab 自己最近写入的 ts
let crossTabConflictWarned = false;
// B7 fix R5: 区分"本 tab 自己写" vs "其他 tab 写",storage event 只在 cross-tab 时触发
window.addEventListener('storage', (e) => {
  if (e.key === EDIT_STORAGE_KEY + ':time' && e.newValue) {
    // 检测到另一 tab 在改同文档(storage event 本 tab 不会触发自己)
    if (!crossTabConflictWarned && root.getAttribute('contenteditable') === 'true') {
      crossTabConflictWarned = true;
      console.warn('另一 tab 正在编辑同一文档,本 tab 的改动可能跟它们冲突');
    }
  }
});
function autoSaveDraft() {
  try {
    const otherTime = localStorage.getItem(EDIT_STORAGE_KEY + ':time');
    if (otherTime) {
      const otherTs = new Date(otherTime).getTime();
      // 关键:跟"本 tab 自己最近写入"比。若 storage 里 ts 比自己最新写入新 → 另一 tab 写过 → 跳过
      // (用 > 严格小于,避免把自己锁死;另一 tab 写的 ts 必然 > 自己 lastSelfSaveTime)
      if (otherTs > lastSelfSaveTime && (Date.now() - otherTs) < 1000) {
        return;
      }
    }
  } catch (e) {}
  try {
    localStorage.setItem(EDIT_STORAGE_KEY, root.innerHTML);
    const now = new Date().toISOString();
    localStorage.setItem(EDIT_STORAGE_KEY + ':time', now);
    lastSelfSaveTime = new Date(now).getTime();  // 只更新本 tab 自己的 ts
  } catch (e) {
    console.warn('editor draft save failed:', e);
    // A5: localStorage 满了清旧 draft 重试一次
    if (e.name === 'QuotaExceededError' || /quota/i.test(e.message || '')) {
      // 清掉所有其他 edit-draft 旧条目
      const oldKeys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith('edit-draft:') && !k.startsWith(EDIT_STORAGE_KEY)) oldKeys.push(k);
      }
      oldKeys.forEach(k => localStorage.removeItem(k));
      try {
        localStorage.setItem(EDIT_STORAGE_KEY, root.innerHTML);
        localStorage.setItem(EDIT_STORAGE_KEY + ':time', new Date().toISOString());
      } catch (e2) {
        if (!draftSaveWarned) {
          alert('编辑草稿无法保存(localStorage 已满)。建议立刻点「💾 导出 MD」下载,避免改动丢失。');
          draftSaveWarned = true;
        }
      }
    }
  }
}

function enterEditMode() {
  // 编辑前先清除 highlight(避免 turndown 把 <span class="ann-mark"> 转回去时混乱)
  root.querySelectorAll('.ann-mark').forEach(m => {
    const txt = document.createTextNode(m.textContent);
    m.replaceWith(txt);
  });
  root.normalize();
  // 收起批注 toolbar
  toolbar.classList.remove('show');
  // 启用编辑
  root.setAttribute('contenteditable', 'true');
  root.focus();
  editBanner.classList.add('show');
  exportMdBtn.classList.add('show');
  editFab.classList.add('active');
  editFab.innerHTML = '✕ 关闭编辑';
  // 监听改动自动存草稿(500ms 节流)
  root.addEventListener('input', scheduleAutoSave);
}

function exitEditMode() {
  root.removeAttribute('contenteditable');
  editBanner.classList.remove('show');
  exportMdBtn.classList.remove('show');
  editFab.classList.remove('active');
  editFab.innerHTML = '✏ 编辑';
  root.removeEventListener('input', scheduleAutoSave);
  // 重新应用批注高亮(原文可能变了,部分会失败,但仍试)
  highlightAllAnnotations();
}

function scheduleAutoSave() {
  clearTimeout(editAutoSaveTimer);
  editAutoSaveTimer = setTimeout(autoSaveDraft, 500);
}

if (editFab) {
  editFab.addEventListener('click', () => {
    if (root.getAttribute('contenteditable') === 'true') {
      exitEditMode();
    } else {
      enterEditMode();
    }
  });
}
if (exitEditBtn) exitEditBtn.addEventListener('click', exitEditMode);

// 导出 MD
if (exportMdBtn) {
  exportMdBtn.addEventListener('click', () => {
    if (typeof TurndownService === 'undefined') {
      alert('turndown.js 未加载,无法导出。检查网络。');
      return;
    }
    const td = new TurndownService({
      headingStyle: 'atx',          // # 标题 (而不是 ===)
      codeBlockStyle: 'fenced',     // ``` 代码块 (而不是缩进)
      bulletListMarker: '-',
      emDelimiter: '*',
      strongDelimiter: '**',
      linkStyle: 'inlined',
    });
    // C5: 用 GFM 插件生成 markdown 表格(| col | col |),Claude 读着自然
    if (typeof turndownPluginGfm !== 'undefined') {
      td.use(turndownPluginGfm.gfm);
    } else {
      td.keep(['table', 'thead', 'tbody', 'tr', 'th', 'td']);  // fallback
    }
    // 注:之前有个 mermaid rule 是 dead code(永远不触发),且会吞内容,已删除
    const md = td.turndown(root.innerHTML);
    const filename = FILE_KEY.replace(/\\.md$/, '') + '.edited.md';
    const blob = new Blob([md], {type: 'text/markdown'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    setTimeout(() => alert('已下载: ' + filename + '\\n\\n你可以把这个文件覆盖原 .md,或者发给 Claude 让它 diff 改动。'), 100);
  });
}

// 启动时检查是否有未保存的草稿
const draftHtml = localStorage.getItem(EDIT_STORAGE_KEY);
const draftTime = localStorage.getItem(EDIT_STORAGE_KEY + ':time');
if (draftHtml && draftTime) {
  const ageMin = (Date.now() - new Date(draftTime).getTime()) / 60000;
  if (ageMin < 60 * 24) {  // 24h 内的草稿才提示恢复
    setTimeout(() => {
      if (confirm('检测到 ' + Math.round(ageMin) + ' 分钟前的未保存编辑草稿,要恢复吗?\\n(选取消则丢弃草稿用最新原文)')) {
        root.innerHTML = draftHtml;
        highlightAllAnnotations();
        // B6: 恢复后自动进入编辑模式,避免"看到改动但不能改"的困惑
        setTimeout(() => enterEditMode(), 100);
      } else {
        localStorage.removeItem(EDIT_STORAGE_KEY);
        localStorage.removeItem(EDIT_STORAGE_KEY + ':time');
      }
    }, 200);
  }
}
</script>
</body></html>"""

import os as _os
file_key = _os.path.basename(src_path)
out = (tpl
    .replace("__TITLE__", html.escape(title))
    .replace("__MD_SRC__", html.escape(src))
    .replace("__FILE_KEY__", html.escape(file_key))
)
open(out_path, "w", encoding="utf-8").write(out)
print(f"wrote {out_path}")
