"""Per-model visibility flags for normal users (personal vs group/shared chats)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import Boolean, Column, Integer, Text

from open_webui.internal.db import Base, get_db
from open_webui.env import SRC_LOG_LEVELS

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

_table_ready = False


class ModelPermission(Base):
    __tablename__ = "model_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Text, nullable=False, unique=True)
    provider = Column(Text, nullable=False)
    model_name = Column(Text, nullable=False)
    users_enabled = Column(Boolean, nullable=False, default=True)
    groups_enabled = Column(Boolean, nullable=False, default=True)


def ensure_model_permissions_table() -> None:
    global _table_ready
    if _table_ready:
        return
    try:
        from open_webui.internal.db import engine

        ModelPermission.__table__.create(bind=engine, checkfirst=True)
        _table_ready = True
    except Exception as e:
        log.warning("Could not ensure model_permissions table: %s", e)


def _provider_label(model_dict: dict) -> str:
    ob = str(model_dict.get("owned_by") or "").lower()
    if ob == "openai":
        return "OpenAI"
    if ob == "ollama":
        return "Ollama"
    if ob == "arena":
        return "Arena"
    return ob.title() if ob else "Other"


def sync_rows_from_api_models(models_list: list[dict]) -> None:
    """Ensure each discovered model has a DB row (defaults: both enabled). Remove rows for models no longer present."""
    ensure_model_permissions_table()
    try:
        allowed_ids = {str(m.get("id") or "") for m in models_list if m.get("id")}
        with get_db() as db:
            for m in models_list:
                mid = str(m.get("id") or "")
                if not mid:
                    continue
                name = str(m.get("name") or mid)
                provider = _provider_label(m)
                row = db.query(ModelPermission).filter_by(model_id=mid).first()
                if row is None:
                    db.add(
                        ModelPermission(
                            model_id=mid,
                            provider=provider,
                            model_name=name,
                            users_enabled=True,
                            groups_enabled=True,
                        )
                    )
                else:
                    row.provider = provider
                    row.model_name = name

            for row in db.query(ModelPermission).all():
                if row.model_id not in allowed_ids:
                    db.delete(row)

            db.commit()
    except Exception as e:
        log.warning("sync_rows_from_api_models failed: %s", e)


def get_permission_map() -> dict[str, dict[str, Any]]:
    ensure_model_permissions_table()
    out: dict[str, dict[str, Any]] = {}
    try:
        with get_db() as db:
            for r in db.query(ModelPermission).all():
                out[r.model_id] = {
                    "model_id": r.model_id,
                    "provider": r.provider,
                    "model_name": r.model_name,
                    "users_enabled": bool(r.users_enabled),
                    "groups_enabled": bool(r.groups_enabled),
                }
    except Exception as e:
        log.warning("get_permission_map failed: %s", e)
    return out


def list_all_rows() -> list[dict[str, Any]]:
    ensure_model_permissions_table()
    try:
        with get_db() as db:
            rows = db.query(ModelPermission).order_by(ModelPermission.provider, ModelPermission.model_name).all()
            return [
                {
                    "model_id": r.model_id,
                    "provider": r.provider,
                    "model_name": r.model_name,
                    "users_enabled": bool(r.users_enabled),
                    "groups_enabled": bool(r.groups_enabled),
                }
                for r in rows
            ]
    except Exception as e:
        log.warning("list_all_rows failed: %s", e)
        return []


def update_permission(
    model_id: str,
    *,
    users_enabled: Optional[bool] = None,
    groups_enabled: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    ensure_model_permissions_table()
    try:
        with get_db() as db:
            row = db.query(ModelPermission).filter_by(model_id=model_id).first()
            if row is None:
                return None
            if users_enabled is not None:
                row.users_enabled = bool(users_enabled)
            if groups_enabled is not None:
                row.groups_enabled = bool(groups_enabled)
            db.commit()
            db.refresh(row)
            return {
                "model_id": row.model_id,
                "provider": row.provider,
                "model_name": row.model_name,
                "users_enabled": bool(row.users_enabled),
                "groups_enabled": bool(row.groups_enabled),
            }
    except Exception as e:
        log.warning("update_permission failed: %s", e)
        return None


def is_model_allowed_for_context(model_id: str, context: str) -> bool:
    """
    context: 'user' | 'group'
    Missing row => allowed (backward compatible).
    """
    ensure_model_permissions_table()
    try:
        with get_db() as db:
            row = db.query(ModelPermission).filter_by(model_id=model_id).first()
            if row is None:
                return True
            if context == "group":
                return bool(row.groups_enabled)
            return bool(row.users_enabled)
    except Exception:
        return True


def filter_models_by_context(models: list[dict], context: str) -> list[dict]:
    if context not in ("user", "group"):
        return models
    return [m for m in models if is_model_allowed_for_context(str(m.get("id")), context)]
