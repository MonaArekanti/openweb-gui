"""Minimal analytics records for blocked sensitive uploads (no file content stored)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from sqlalchemy import BigInteger, Column, String, Text

from open_webui.internal.db import Base, get_db, engine
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

_table_ready = False


class SensitiveUploadEvent(Base):
    __tablename__ = "sensitive_upload_event"

    id = Column(String, primary_key=True)
    created_at = Column(BigInteger, nullable=False)
    user_id = Column(String, nullable=False)
    session_id = Column(String, nullable=True)
    filename = Column(Text, nullable=False)
    detection_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="rejected")
    category = Column(Text, nullable=True)
    internal_stage = Column(String, nullable=True)


def ensure_sensitive_upload_table() -> None:
    global _table_ready
    if _table_ready:
        return
    try:
        SensitiveUploadEvent.__table__.create(bind=engine, checkfirst=True)
        _table_ready = True
    except Exception as e:
        log.warning("Could not ensure sensitive_upload_event table: %s", e)


def record_sensitive_upload_rejection(
    user_id: str,
    filename: str,
    detection_type: str,
    *,
    session_id: Optional[str] = None,
    category: Optional[str] = None,
    internal_stage: Optional[str] = None,
) -> None:
    """
    Persist a minimal rejection event (never stores file bytes or full extracted text).
    Call before returning HTTP error to the client.
    """
    ensure_sensitive_upload_table()
    safe_cat = (category or "")[:200] if category else None
    row = SensitiveUploadEvent(
        id=str(uuid.uuid4()),
        created_at=int(time.time()),
        user_id=user_id,
        session_id=(session_id or None),
        filename=filename or "unknown",
        detection_type=detection_type,
        status="rejected",
        category=safe_cat,
        internal_stage=internal_stage,
    )
    try:
        with get_db() as db:
            db.add(row)
            db.commit()
    except Exception as e:
        log.warning("Failed to record sensitive upload rejection event: %s", e)


def get_sensitive_upload_block_counts() -> dict[str, Any]:
    ensure_sensitive_upload_table()
    try:
        with get_db() as db:
            total = (
                db.query(SensitiveUploadEvent)
                .filter(SensitiveUploadEvent.status == "rejected")
                .count()
            )
            meta = (
                db.query(SensitiveUploadEvent)
                .filter(
                    SensitiveUploadEvent.status == "rejected",
                    SensitiveUploadEvent.detection_type == "metadata-sensitive",
                )
                .count()
            )
            content = (
                db.query(SensitiveUploadEvent)
                .filter(
                    SensitiveUploadEvent.status == "rejected",
                    SensitiveUploadEvent.detection_type == "content-sensitive",
                )
                .count()
            )
            return {
                "total": int(total),
                "metadata_sensitive": int(meta),
                "content_sensitive": int(content),
            }
    except Exception as e:
        log.warning("Sensitive upload counts unavailable: %s", e)
        return {"total": 0, "metadata_sensitive": 0, "content_sensitive": 0}
