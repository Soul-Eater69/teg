"""Shared node helper: auto-sizes a box to its text and vertically centers the block."""
from __future__ import annotations
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

TITLE_H = 3.0
GAP = 1.0
LINE_H = 1.62
PAD = 2.4


def text_height(body: str, *, has_title: bool = True) -> float:
    lines = body.count("\n") + 1 if body else 0
    h = (TITLE_H if has_title else 0) + (GAP if (has_title and lines) else 0) + lines * LINE_H
    return h + 2 * PAD


def node(ax, cx, cy, w, title, body, colors, *, ts=10.0, bs=8.4, h=None, rs=2.0, italic=False):
    """Draw a rounded box auto-sized (or fixed h) with title + centered body. Returns height."""
    fill, edge, txt = colors
    lines = body.count("\n") + 1 if body else 0
    block = (TITLE_H if title else 0) + (GAP if (title and lines) else 0) + lines * LINE_H
    if h is None:
        h = block + 2 * PAD
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                 boxstyle=f"round,pad=0.3,rounding_size={rs}", fc=fill, ec=edge, lw=1.5))
    top = cy + block / 2  # top of the centered text block
    if title:
        ax.text(cx, top, title, ha="center", va="top", fontsize=ts, weight="bold", color=txt)
        if lines:
            ax.text(cx, top - TITLE_H - GAP, body, ha="center", va="top", fontsize=bs,
                    color=txt, linespacing=1.34, style="italic" if italic else "normal")
    elif lines:
        ax.text(cx, top, body, ha="center", va="top", fontsize=bs, color=txt,
                linespacing=1.34, style="italic" if italic else "normal")
    return h


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                 mutation_scale=17, lw=1.7, color="#2E6DA4"))


def band(ax, x, y, w, h, label):
    ax.add_patch(Rectangle((x, y), w, h, fill=False, ec="#2E6DA4", lw=1.4, ls=(0, (6, 4))))
    ax.text(x + w / 2, y + h - 1.6, label, ha="center", va="top", fontsize=10,
            weight="bold", color="#1F4E79")


def legend(ax, items, y, *, x0=6, dx=19, bw=3.0, bh=2.6, fs=8.4):
    x = x0
    for label, (fill, edge, _) in items:
        ax.add_patch(FancyBboxPatch((x, y), bw, bh, boxstyle="round,pad=0.1,rounding_size=0.5",
                     fc=fill, ec=edge, lw=1.3))
        ax.text(x + bw + 0.8, y + bh / 2, label, ha="left", va="center", fontsize=fs)
        x += dx


C_IO   = ("#2E6DA4", "#1F4E79", "white")
C_DATA = ("#E4F1E4", "#4C9A4C", "#1c1c1c")
C_LLM  = ("#FBE9CC", "#E0922F", "#1c1c1c")
C_GEN  = ("#E4F1E4", "#4C9A4C", "#1c1c1c")
C_DET  = ("#EFEFEF", "#9A9A9A", "#1c1c1c")
C_GATE = ("#FCE3C8", "#E0922F", "#1c1c1c")
C_NOTE = ("#EFE3F6", "#9B6FB5", "#3a2a45")
