"""Sensitivity checks against normalized text and metadata blobs."""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from open_webui.upload_validation.rules import DetectionRules

log = logging.getLogger(__name__)


def scan_metadata_blob(blob: str, rules: DetectionRules) -> Optional[str]:
    """Return first blocked substring matched (case-insensitive), or None."""
    if not blob:
        return None
    low = blob.lower()
    for s in rules.metadata_blocked_substrings:
        if s.lower() in low:
            return s
    return None


def scan_filename(filename: str, rules: DetectionRules) -> Optional[str]:
    if not filename:
        return None
    low = filename.lower()
    for s in rules.filename_blocked_substrings:
        if s.lower() in low:
            return s
    return None


def scan_content_normalized(normalized_text: str, rules: DetectionRules) -> Tuple[Optional[str], Optional[str]]:
    """
    Keyword scan first (cheap substring), then regex patterns.
    Returns (hit_kind, hit_detail) where kind is 'keyword' or 'pattern'.
    """
    if not normalized_text:
        return (None, None)

    for kw in rules.content_keywords:
        if kw.lower() in normalized_text:
            return ("keyword", kw)

    for cp in rules.patterns:
        if cp.pattern.search(normalized_text):
            return ("pattern", cp.name)

    return (None, None)
