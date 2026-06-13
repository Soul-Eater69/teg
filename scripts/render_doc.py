"""Render a Markdown analysis doc to a self-contained HTML file.

Charts are inlined as base64 data URIs, so the output opens on any machine / online viewer
with no sibling image files - fixing the broken relative ``![](charts/x.png)`` links when the
doc is copied around. Run with the markdown lib provided ad-hoc (no project dependency):

  uv run --with markdown python scripts/render_doc.py docs/retrieval_eval_findings.md

Writes ``<doc>.html`` next to the source. Pass several docs to render them all.
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import re
from pathlib import Path

import markdown

_IMG_SRC = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.IGNORECASE)

_CSS = """
:root { color-scheme: light dark; }
body { max-width: 880px; margin: 2rem auto; padding: 0 1.2rem;
       font: 16px/1.6 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
       color: #1f2328; background: #fff; }
h1, h2, h3 { line-height: 1.25; margin-top: 1.8rem; }
h1 { border-bottom: 2px solid #d0d7de; padding-bottom: .3rem; }
h2 { border-bottom: 1px solid #d8dee4; padding-bottom: .25rem; }
img { max-width: 100%; height: auto; display: block; margin: 1rem 0;
      border: 1px solid #d0d7de; border-radius: 6px; }
table { border-collapse: collapse; margin: 1rem 0; width: 100%; }
th, td { border: 1px solid #d0d7de; padding: 6px 13px; text-align: left; }
th { background: #f6f8fa; }
tr:nth-child(2n) td { background: #f6f8fa; }
code { background: #eff1f3; padding: .15em .35em; border-radius: 4px;
       font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
pre { background: #f6f8fa; padding: 1rem; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { border-left: 4px solid #d0d7de; margin: 1rem 0; padding: .2rem 1rem; color: #57606a; }
"""


def _inline_images(html: str, base_dir: Path) -> tuple[str, int, list[str]]:
    inlined = 0
    missing: list[str] = []

    def _sub(match: re.Match) -> str:
        nonlocal inlined
        src = match.group(2)
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        path = (base_dir / src).resolve()
        if not path.exists():
            missing.append(src)
            return match.group(0)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        inlined += 1
        return f"{match.group(1)}data:{mime};base64,{data}{match.group(3)}"

    return _IMG_SRC.sub(_sub, html), inlined, missing


def render(md_path: Path) -> Path:
    text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(
        text, extensions=["tables", "fenced_code", "sane_lists", "toc", "attr_list"]
    )
    body, inlined, missing = _inline_images(body, md_path.parent)
    title = md_path.stem.replace("_", " ")
    html = (f"<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{title}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n")
    out = md_path.with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    print(f"{md_path.name} -> {out.name}  ({inlined} image(s) inlined)"
          + (f"  MISSING: {missing}" if missing else ""))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Render Markdown to self-contained HTML.")
    p.add_argument("docs", nargs="+", help="markdown file(s) to render")
    args = p.parse_args()
    for doc in args.docs:
        render(Path(doc))
