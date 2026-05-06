"""Orchestrates metadata → filename → content sensitivity validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from open_webui.upload_validation.content import extract_document_text
from open_webui.upload_validation.detection import (
    scan_content_normalized,
    scan_filename,
    scan_metadata_blob,
)
from open_webui.upload_validation.metadata import extract_metadata
from open_webui.upload_validation.normalization import normalize_text
from open_webui.upload_validation.rules import DetectionRules, load_rules

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    allowed: bool
    stage: Optional[str] = None  # metadata | filename | content
    detail: Optional[str] = None
    content_sensitivity_warning: bool = False


def _rules_for_request(request: Request) -> DetectionRules:
    path = getattr(request.app.state.config, "UPLOAD_SENSITIVITY_RULES_PATH", "") or ""
    path = str(path).strip()
    return load_rules(path if path else None)


def validate_upload_buffer(
    request: Request,
    data: bytes,
    filename: str,
    content_type: Optional[str],
) -> ValidationResult:
    """
    Run validation pipeline when enabled via config / env.

    Strict order (metadata before content — content scan never runs if step 1 rejects):
      1. Filename substrings (immediate; no document parsing).
      2. Embedded document metadata blob (PDF/DOCX/PPTX tags only — no body extract).
      3. Document body text extraction + scan (only if steps 1–2 passed).
    """
    enabled = bool(getattr(request.app.state.config, "UPLOAD_SENSITIVITY_VALIDATION_ENABLED", False))
    if not enabled:
        return ValidationResult(True)

    content_action = str(
        getattr(request.app.state.config, "UPLOAD_SENSITIVE_CONTENT_ACTION", "block") or "block"
    ).lower()
    if content_action not in ("block", "warn"):
        content_action = "block"

    rules = _rules_for_request(request)

    try:
        fn_hit = scan_filename(filename, rules)
        if fn_hit:
            log.warning("Upload rejected (filename): %s", fn_hit)
            return ValidationResult(False, "filename", fn_hit)
    except Exception as e:
        log.debug("Filename scan error: %s", e)

    try:
        meta_pkg = extract_metadata(filename, content_type, data)
        blob = meta_pkg.get("text_blob") or ""
        hit = scan_metadata_blob(blob, rules)
        if hit:
            log.warning("Upload rejected (metadata sensitivity): %s", hit)
            return ValidationResult(False, "metadata", hit)
    except Exception as e:
        log.debug("Metadata extraction skipped/failed: %s", e)

    try:
        text, extract_err = extract_document_text(filename, content_type, data)
        if extract_err:
            log.debug("Content extraction note for %s: %s", filename, extract_err)
        if not text or not text.strip():
            return ValidationResult(True)

        normalized = normalize_text(text)
        kind, detail = scan_content_normalized(normalized, rules)
        if kind:
            if content_action == "warn":
                log.warning(
                    "Upload allowed with content sensitivity warning (%s): %s", kind, detail
                )
                return ValidationResult(
                    True,
                    "content",
                    f"{kind}:{detail}",
                    content_sensitivity_warning=True,
                )
            log.warning("Upload rejected (content %s): %s", kind, detail)
            return ValidationResult(False, "content", f"{kind}:{detail}")
    except Exception as e:
        log.warning("Content sensitivity scan failed (allowing upload): %s", e)

    return ValidationResult(True)
