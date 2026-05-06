"""Admin API: model visibility for users vs group/shared chats."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from open_webui.models.model_permissions import (
    list_all_rows,
    sync_rows_from_api_models,
    update_permission,
)
from open_webui.utils.auth import get_admin_user
from open_webui.utils.models import collect_models_for_permission_sync

router = APIRouter()


class ModelPermissionPatch(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    users_enabled: Optional[bool] = None
    groups_enabled: Optional[bool] = None


class ModelPermissionRow(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    provider: str
    model_name: str
    users_enabled: bool
    groups_enabled: bool


@router.get("/", response_model=list[ModelPermissionRow])
async def list_permissions(request: Request, user=Depends(get_admin_user)):
    del user
    models_list = await collect_models_for_permission_sync(request)
    sync_rows_from_api_models(models_list)
    rows = list_all_rows()
    return [ModelPermissionRow(**r) for r in rows]


@router.patch("/{model_id:path}", response_model=ModelPermissionRow)
async def patch_permission(
    model_id: str,
    body: ModelPermissionPatch,
    user=Depends(get_admin_user),
):
    del user
    if body.users_enabled is None and body.groups_enabled is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide users_enabled and/or groups_enabled",
        )
    updated = update_permission(
        model_id,
        users_enabled=body.users_enabled,
        groups_enabled=body.groups_enabled,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown model_id; open Permissions once after configuring connections.",
        )
    return ModelPermissionRow(**updated)
