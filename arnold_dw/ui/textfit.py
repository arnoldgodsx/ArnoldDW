"""Single-line text that doesn't fit is cut with an ellipsis (Tk labels only wrap)."""

from functools import lru_cache

import customtkinter as ctk

ELLIPSIS = "…"


@lru_cache(maxsize=16)
def _font(family, size, weight):
    return ctk.CTkFont(family=family, size=size, weight=weight)


def fit_text(text, max_width, family, size, weight="normal"):
    """Longest prefix of `text` (plus "…") no wider than `max_width` (unscaled px)."""
    text = " ".join((text or "").split())
    font = _font(family, size, weight)
    if font.measure(text) <= max_width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid].rstrip() + ELLIPSIS) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + ELLIPSIS
