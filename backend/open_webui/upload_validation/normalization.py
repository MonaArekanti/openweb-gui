"""Text normalization for sensitivity scanning."""

from __future__ import annotations

import re
import unicodedata


_WS_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Lowercase, NFKC normalize, collapse whitespace for keyword scans."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.lower()
    t = _WS_RE.sub(" ", t).strip()
    return t
