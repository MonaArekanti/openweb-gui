"""Admin-only chat listing, messages, and stats."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
import logging

from pydantic import BaseModel, ConfigDict, ValidationError

from open_webui.config import ENABLE_ADMIN_CHAT_ACCESS

log = logging.getLogger(__name__)
from open_webui.constants import ERROR_MESSAGES
from open_webui.internal.db import get_db
from open_webui.models.chats import Chat, Chats, ChatModel
from open_webui.models.files import File
from open_webui.models.sensitive_upload_event import (
    SensitiveUploadEvent,
    ensure_sensitive_upload_table,
)
from open_webui.models.users import Users
from open_webui.utils.admin_chats import (
    chat_matches_any_tag_filter,
    chat_uses_model,
    classify_title_tags,
    count_list_messages,
    linearize_history_messages,
    merged_titles,
    normalize_msg_timestamp,
    primary_model_for_chat,
)
from open_webui.utils.auth import get_admin_user

from sqlalchemy import not_
router = APIRouter()


def _require_admin_chat_access():
    if not ENABLE_ADMIN_CHAT_ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )


def _parse_day_start_utc(s: str) -> int:
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d").date()
        return int(
            datetime.combine(d, datetime.min.time())
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid start_date; use YYYY-MM-DD",
        ) from e


def _parse_day_end_utc(s: str) -> int:
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d").date()
        return int(
            datetime.combine(d, datetime.max.time())
            .replace(tzinfo=timezone.utc)
            .timestamp()
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid end_date; use YYYY-MM-DD",
        ) from e


class AdminChatUser(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    name: str
    email: str


class AdminChatRow(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    title: str
    titles_display: str
    user: AdminChatUser
    model: str
    model_name: str
    message_count: int
    created_at: int
    updated_at: int
    tags: list[str]


class AdminChatStats(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    total_documents: int
    flagged_documents: int


class AdminMessageRow(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    role: str
    content: str
    timestamp: Optional[int] = None
    model: Optional[str] = None
    model_name: Optional[str] = None
    name: Optional[str] = None


def _filtered_chat_models(
    db,
    user_id: Optional[str],
    model_id: Optional[str],
    tag_list: list[str],
    start_ts: Optional[int],
    end_ts: Optional[int],
) -> list[ChatModel]:
    """Same filter semantics as the admin chat list (date/user in SQL; model/tags in Python)."""
    q = db.query(Chat).filter(not_(Chat.user_id.like("shared%")))
    if user_id:
        q = q.filter(Chat.user_id == user_id)
    if start_ts is not None:
        q = q.filter(Chat.updated_at >= start_ts)
    if end_ts is not None:
        q = q.filter(Chat.updated_at <= end_ts)
    q = q.order_by(Chat.updated_at.desc())
    rows = q.all()
    candidates: list[ChatModel] = []
    for r in rows:
        try:
            candidates.append(ChatModel.model_validate(r))
        except (ValidationError, TypeError, ValueError) as e:
            log.warning("Skipping invalid chat row in admin list: %s", e)

    filtered: list[ChatModel] = []
    for cm in candidates:
        if model_id and not chat_uses_model(cm, model_id):
            continue
        if tag_list and not chat_matches_any_tag_filter(cm, tag_list):
            continue
        filtered.append(cm)
    return filtered


def _count_uploaded_documents_filtered(
    db,
    user_id: Optional[str],
    start_ts: Optional[int],
    end_ts: Optional[int],
) -> int:
    """Uploaded files (file table); optional user + created_at range."""
    q = db.query(File)
    if user_id:
        q = q.filter(File.user_id == user_id)
    if start_ts is not None:
        q = q.filter(File.created_at >= start_ts)
    if end_ts is not None:
        q = q.filter(File.created_at <= end_ts)
    return int(q.count())


def _count_sensitive_flagged_documents_filtered(
    db,
    user_id: Optional[str],
    start_ts: Optional[int],
    end_ts: Optional[int],
) -> int:
    """
    Sensitive / flagged documents from upload validation only:
    blocked uploads (sensitive_upload_event) plus stored files flagged with
    sensitivity_content_warning in meta. Not tied to chat moderation.
    """
    ensure_sensitive_upload_table()
    q_ev = db.query(SensitiveUploadEvent).filter(
        SensitiveUploadEvent.status == "rejected"
    )
    if user_id:
        q_ev = q_ev.filter(SensitiveUploadEvent.user_id == user_id)
    if start_ts is not None:
        q_ev = q_ev.filter(SensitiveUploadEvent.created_at >= start_ts)
    if end_ts is not None:
        q_ev = q_ev.filter(SensitiveUploadEvent.created_at <= end_ts)
    rejected_n = int(q_ev.count())

    qf = db.query(File)
    if user_id:
        qf = qf.filter(File.user_id == user_id)
    if start_ts is not None:
        qf = qf.filter(File.created_at >= start_ts)
    if end_ts is not None:
        qf = qf.filter(File.created_at <= end_ts)
    warning_n = 0
    for row in qf.all():
        meta = row.meta
        if isinstance(meta, dict) and meta.get("sensitivity_content_warning") is True:
            warning_n += 1
    return rejected_n + warning_n


def _chat_to_row(cm: ChatModel, user_lookup: dict[str, Any]) -> AdminChatRow:
    uid = cm.user_id
    u = user_lookup.get(uid)
    if u:
        user_obj = AdminChatUser(
            id=str(u.id),
            name=str(u.name or "") or str(u.id),
            email=str(u.email or ""),
        )
    else:
        user_obj = AdminChatUser(id=str(uid), name=str(uid), email="")

    mid, mname = primary_model_for_chat(cm)
    title = cm.title or (cm.chat or {}).get("title") or "New Chat"
    title = str(title) if title is not None else "New Chat"
    tags = classify_title_tags(title)
    return AdminChatRow(
        id=str(cm.id),
        title=title,
        titles_display=merged_titles(cm),
        user=user_obj,
        model=mid,
        model_name=mname or mid,
        message_count=count_list_messages(cm.chat or {}),
        created_at=int(cm.created_at or 0),
        updated_at=int(cm.updated_at or 0),
        tags=tags,
    )


@router.get("/stats", response_model=AdminChatStats)
async def admin_chat_stats(
    user_id: Optional[str] = Query(None),
    model_id: Optional[str] = Query(
        None,
        description="Ignored for document stats (chat filters only affect the list).",
    ),
    tag: Optional[str] = Query(
        None,
        description="Ignored for document stats (chat filters only affect the list).",
    ),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user=Depends(get_admin_user),
):
    _require_admin_chat_access()

    start_ts: Optional[int] = None
    end_ts: Optional[int] = None
    if start_date:
        start_ts = _parse_day_start_utc(start_date)
    if end_date:
        end_ts = _parse_day_end_utc(end_date)

    with get_db() as db:
        total_documents = _count_uploaded_documents_filtered(
            db, user_id, start_ts, end_ts
        )
        flagged_documents = _count_sensitive_flagged_documents_filtered(
            db, user_id, start_ts, end_ts
        )
    return AdminChatStats(
        total_documents=total_documents,
        flagged_documents=flagged_documents,
    )


@router.get("/{chat_id}/messages", response_model=list[AdminMessageRow])
async def admin_chat_messages(chat_id: str, user=Depends(get_admin_user)):
    _require_admin_chat_access()
    cm = Chats.get_chat_by_id(chat_id)
    if cm is None or str(cm.user_id).startswith("shared-"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    history = (cm.chat or {}).get("history") or {}
    chain = linearize_history_messages(history)
    out: list[AdminMessageRow] = []
    for msg in chain:
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if isinstance(content, list):
            content = str(content)
        elif content is None:
            content = ""
        else:
            content = str(content)
        ts = normalize_msg_timestamp(msg)
        out.append(
            AdminMessageRow(
                role=role,
                content=content,
                timestamp=ts,
                model=str(msg.get("model") or "") or None,
                model_name=str(msg.get("modelName") or "") or None,
                name=str(msg.get("name") or msg.get("role") or "") or None,
            )
        )
    return out


@router.get("/", response_model=list[AdminChatRow])
async def admin_chat_list(
    user_id: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    tag: Optional[str] = Query(
        None,
        description="Comma-separated domain tags (e.g. TECH,FINANCE)",
    ),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(get_admin_user),
):
    _require_admin_chat_access()

    tag_list = [t.strip().upper() for t in (tag or "").split(",") if t.strip()]

    start_ts: Optional[int] = None
    end_ts: Optional[int] = None
    if start_date:
        start_ts = _parse_day_start_utc(start_date)
    if end_date:
        end_ts = _parse_day_end_utc(end_date)

    with get_db() as db:
        filtered = _filtered_chat_models(
            db, user_id, model_id, tag_list, start_ts, end_ts
        )

    skip = (page - 1) * limit
    page_rows = filtered[skip : skip + limit]

    uids = list({cm.user_id for cm in page_rows})
    users_batch = Users.get_users_by_user_ids(uids) if uids else []
    user_lookup = {u.id: u for u in users_batch}

    out: list[AdminChatRow] = []
    for cm in page_rows:
        try:
            out.append(_chat_to_row(cm, user_lookup))
        except (ValidationError, TypeError, ValueError) as e:
            log.warning("Could not serialize chat %s for admin list: %s", getattr(cm, "id", "?"), e)
    return out
