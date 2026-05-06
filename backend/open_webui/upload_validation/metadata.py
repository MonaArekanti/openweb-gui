"""Extract document metadata for sensitivity label detection."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


def extract_pdf_metadata(data: bytes) -> dict[str, Any]:
    meta: dict[str, Any] = {"format": "pdf"}
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        parts: list[str] = []
        if reader.metadata:
            md = reader.metadata
            try:
                if hasattr(md, "items"):
                    for _, v in md.items():
                        if v:
                            parts.append(str(v))
                else:
                    parts.append(str(md))
            except Exception:
                parts.append(str(reader.metadata))
        meta["text_blob"] = " ".join(parts)
    except Exception as e:
        log.debug("PDF metadata extract failed: %s", e)
        meta["parse_error"] = str(e)
    return meta


def extract_docx_core_xml_strings(data: bytes) -> dict[str, Any]:
    meta: dict[str, Any] = {"format": "docx"}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            parts = []
            for name in ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"):
                if name in zf.namelist():
                    parts.append(zf.read(name).decode("utf-8", errors="ignore"))
            meta["text_blob"] = " ".join(parts)
    except Exception as e:
        log.debug("DOCX metadata extract failed: %s", e)
        meta["parse_error"] = str(e)
    return meta


def extract_pptx_core_strings(data: bytes) -> dict[str, Any]:
    meta: dict[str, Any] = {"format": "pptx"}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            parts = []
            for name in zf.namelist():
                if name.startswith("docProps/") and name.endswith(".xml"):
                    parts.append(zf.read(name).decode("utf-8", errors="ignore"))
            meta["text_blob"] = " ".join(parts[:20])
    except Exception as e:
        log.debug("PPTX metadata extract failed: %s", e)
        meta["parse_error"] = str(e)
    return meta


def extract_metadata(filename: str, content_type: Optional[str], data: bytes) -> dict[str, Any]:
    """Return a dict including ``text_blob`` (concat metadata strings) for scanning."""
    ext = Path(filename).suffix.lower()
    ct = (content_type or "").lower()

    combined: dict[str, Any] = {"filename": filename, "extension": ext, "fragments": []}

    if ext == ".pdf" or "pdf" in ct:
        combined["fragments"].append(extract_pdf_metadata(data))
    elif ext == ".docx" or "wordprocessingml.document" in ct:
        combined["fragments"].append(extract_docx_core_xml_strings(data))
    elif ext == ".pptx" or "presentationml.presentation" in ct:
        combined["fragments"].append(extract_pptx_core_strings(data))

    blobs = []
    for frag in combined["fragments"]:
        if isinstance(frag, dict) and frag.get("text_blob"):
            blobs.append(frag["text_blob"])
    combined["text_blob"] = " ".join(blobs)
    return combined
