"""Extract textual content from uploaded bytes (bounded for performance)."""

from __future__ import annotations

import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)

# Hard caps — tune via env
MAX_BYTES_READ = int(os.environ.get("UPLOAD_SENSITIVITY_MAX_BYTES", str(15 * 1024 * 1024)))
MAX_CHARS_OUTPUT = int(os.environ.get("UPLOAD_SENSITIVITY_MAX_CHARS", "400000"))


def extract_pdf_text(data: bytes) -> Tuple[str, Optional[str]]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        parts: list[str] = []
        n = 0
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            parts.append(t)
            n += len(t)
            if n >= MAX_CHARS_OUTPUT:
                break
        text = "".join(parts)[:MAX_CHARS_OUTPUT]
        return text, None
    except Exception as e:
        log.debug("PDF text extract failed: %s", e)
        return "", str(e)


def extract_with_tempfile(suffix: str, data: bytes, fn) -> Tuple[str, Optional[str]]:
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            chunk = data[:MAX_BYTES_READ]
            tf.write(chunk)
            tf.flush()
            path = tf.name
        text = fn(path)
        if len(text) > MAX_CHARS_OUTPUT:
            text = text[:MAX_CHARS_OUTPUT]
        return text, None
    except Exception as e:
        log.debug("Tempfile extract failed (%s): %s", suffix, e)
        return "", str(e)
    finally:
        if path and os.path.isfile(path):
            try:
                os.unlink(path)
            except OSError:
                pass


def extract_docx_text(data: bytes) -> Tuple[str, Optional[str]]:
    def load_docx(path: str) -> str:
        import docx2txt

        return docx2txt.process(path) or ""

    return extract_with_tempfile(".docx", data, load_docx)


def extract_plain_text(data: bytes) -> Tuple[str, Optional[str]]:
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            t = data[:MAX_BYTES_READ].decode(enc)
            return t[:MAX_CHARS_OUTPUT], None
        except UnicodeDecodeError:
            continue
    return "", "decode_error"


def extract_document_text(filename: str, content_type: Optional[str], data: bytes) -> Tuple[str, Optional[str]]:
    """
    Best-effort text extraction. Returns (text, error_message_or_none).
    Unsupported types return empty text with no error (caller may skip content scan).
    """
    ext = Path(filename).suffix.lower()
    ct = (content_type or "").lower()

    if len(data) > MAX_BYTES_READ:
        data = data[:MAX_BYTES_READ]

    if ext == ".pdf" or "pdf" in ct:
        return extract_pdf_text(data)

    if ext == ".docx" or "wordprocessingml.document" in ct:
        return extract_docx_text(data)

    textlike = (
        ext
        in (
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".xml",
            ".html",
            ".htm",
            ".rst",
            ".log",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".env",
            ".sql",
            ".ts",
            ".js",
            ".py",
            ".go",
            ".java",
            ".c",
            ".h",
            ".cpp",
            ".rs",
            ".rb",
            ".php",
            ".sh",
            ".bat",
        )
        or (ct.startswith("text/"))
    )

    if textlike:
        return extract_plain_text(data)

    if ext in (".xlsx", ".xls") or "spreadsheet" in ct:
        return _extract_xlsx_lite(data, ext)

    if ext == ".pptx" or "presentationml" in ct:
        return _extract_pptx_lite(data)

    log.debug("No specific extractor for %s (%s); skipping content body scan", filename, ct)
    return "", None


def _extract_xlsx_lite(data: bytes, ext: str) -> Tuple[str, Optional[str]]:
    """Lightweight shared strings scan without loading full workbook when possible."""
    if ext == ".xlsx":
        try:
            import zipfile

            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "xl/sharedStrings.xml" not in zf.namelist():
                    return "", None
                raw = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="ignore")
                if len(raw) > MAX_CHARS_OUTPUT:
                    raw = raw[:MAX_CHARS_OUTPUT]
                return raw, None
        except Exception as e:
            log.debug("xlsx lite extract failed: %s", e)
            return "", str(e)
    return "", None


def _extract_pptx_lite(data: bytes) -> Tuple[str, Optional[str]]:
    try:
        import zipfile
        import re

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            chunks = []
            for name in zf.namelist():
                if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                    chunks.append(zf.read(name).decode("utf-8", errors="ignore"))
                    combined = "".join(chunks)
                    if len(combined) >= MAX_CHARS_OUTPUT:
                        break
            text = re.sub(r"<[^>]+>", " ", "".join(chunks))
            text = " ".join(text.split())
            return text[:MAX_CHARS_OUTPUT], None
    except Exception as e:
        log.debug("pptx lite extract failed: %s", e)
        return "", str(e)
