"""人物关系图渲染 — 把 Mermaid 代码封装为可双击打开的 HTML 文件."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

# 项目根目录 (src/character_builder/../.. = 项目根)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output" / "character_relations"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; padding: 20px; background: #fafafa; }}
  h1 {{ font-size: 20px; color: #333; margin-bottom: 16px; }}
  .graph-box {{ background: #fff; border: 1px solid #e2e2e2; border-radius: 8px;
                padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  .mermaid {{ display: flex; justify-content: center; }}
  #legend {{ margin-top: 16px; color: #666; font-size: 12px; line-height: 1.6; }}
</style>
</head>
<body>
  <h1>📊 人物关系图 — {title}</h1>
  <div class="graph-box">
    <pre class="mermaid">
{mermaid}
    </pre>
  </div>
  <div id="legend">Tip: 支持滚轮缩放、拖动画布。双击节点可查看标签。</div>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{ startOnLoad: true, theme: 'default',
      flowchart: {{ curve: 'basis' }}, securityLevel: 'loose' }});
  </script>
</body>
</html>
"""


def _extract_mermaid_block(text: str) -> str:
    """从文本中提取 ```mermaid ... ``` 代码块; 无围栏时尝试识别 graph/flowchart 开头."""
    m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```(?:txt)?\s*\n(graph|flowchart|sequenceDiagram)[\s\S]*?```", text, re.DOTALL)
    if m:
        return m.group(0).strip()
    # 无围栏: 找以 graph 或 flowchart 开头的块
    lines = text.strip().splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^(graph|flowchart)\s+(TD|TB|LR|RL|BT)", line.strip()):
            return "\n".join(lines[i:]).strip()
    return text.strip()


def render_relationship_html(mermaid_code: str, title: str = "人物关系图") -> str:
    """把 Mermaid 代码渲染为 HTML 文件, 返回文件绝对路径.

    Args:
        mermaid_code: Mermaid 关系图代码
        title: 标题 (如书名或作品名)

    Returns:
        生成的 HTML 文件绝对路径; 失败时返回空字符串。
    """
    block = _extract_mermaid_block(mermaid_code)
    if not block or not block.startswith(("graph", "flowchart")):
        return ""

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r"[^\w一-鿿-]", "_", title)
        ts = time.strftime("%Y%m%d_%H%M%S")
        filepath = OUTPUT_DIR / f"{safe_title}_{ts}.html"

        html = _HTML_TEMPLATE.format(title=title, mermaid=block)
        filepath.write_text(html, encoding="utf-8")
        return str(filepath)
    except Exception:
        return ""
