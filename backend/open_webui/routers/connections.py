"""Admin API for listing and patching OpenAI/Ollama connection configs (incl. price_per_1k)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from open_webui.utils.auth import get_admin_user

router = APIRouter()


class ConnectionOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    provider: str = Field(pattern="^(openai|ollama)$")
    base_url: str
    price_per_1k: Optional[float] = None
    has_api_key: bool = False


class ConnectionsListResponse(BaseModel):
    openai: list[ConnectionOut]
    ollama: list[ConnectionOut]


class ConnectionPatchBody(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    api_key: Optional[str] = None
    price_per_1k: Optional[float] = Field(None, ge=0)


def _price(cfg: dict) -> Optional[float]:
    if not cfg or "price_per_1k" not in cfg:
        return None
    try:
        return max(0.0, float(cfg["price_per_1k"]))
    except (TypeError, ValueError):
        return None


@router.get("", response_model=ConnectionsListResponse)
async def list_connections(request: Request, user=Depends(get_admin_user)):
    del user
    cfg = request.app.state.config

    openai_out: list[ConnectionOut] = []
    keys = list(cfg.OPENAI_API_KEYS or [])
    urls = list(cfg.OPENAI_API_BASE_URLS or [])
    o_cfg = dict(cfg.OPENAI_API_CONFIGS or {})
    for idx, url in enumerate(urls):
        c = o_cfg.get(url) or {}
        openai_out.append(
            ConnectionOut(
                id=f"openai-{idx}",
                provider="openai",
                base_url=url,
                price_per_1k=_price(c),
                has_api_key=bool(keys[idx] if idx < len(keys) else ""),
            )
        )

    ollama_urls = list(cfg.OLLAMA_BASE_URLS or [])
    ol_cfg = dict(cfg.OLLAMA_API_CONFIGS or {})
    ollama_out: list[ConnectionOut] = []
    for idx, url in enumerate(ollama_urls):
        c = ol_cfg.get(url) or {}
        ollama_out.append(
            ConnectionOut(
                id=f"ollama-{idx}",
                provider="ollama",
                base_url=url,
                price_per_1k=_price(c),
                has_api_key=False,
            )
        )

    return ConnectionsListResponse(openai=openai_out, ollama=ollama_out)


@router.patch("/{connection_id}", response_model=ConnectionOut)
async def patch_connection(
    connection_id: str,
    body: ConnectionPatchBody,
    request: Request,
    user=Depends(get_admin_user),
):
    del user
    parts = connection_id.split("-", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id")
    provider, idx_s = parts
    try:
        idx = int(idx_s)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid id"
        ) from e

    if provider == "openai":
        urls = list(request.app.state.config.OPENAI_API_BASE_URLS or [])
        if idx < 0 or idx >= len(urls):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        url = urls[idx]

        keys = list(request.app.state.config.OPENAI_API_KEYS or [])
        while len(keys) <= idx:
            keys.append("")
        if body.api_key is not None:
            keys[idx] = body.api_key
        request.app.state.config.OPENAI_API_KEYS = keys

        configs: dict[str, Any] = dict(request.app.state.config.OPENAI_API_CONFIGS or {})
        cfg = dict(configs.get(url, {}))
        if body.price_per_1k is not None:
            cfg["price_per_1k"] = body.price_per_1k
        configs[url] = cfg
        request.app.state.config.OPENAI_API_CONFIGS = configs

        fc = dict(request.app.state.config.OPENAI_API_CONFIGS or {}).get(url, {})
        fk = list(request.app.state.config.OPENAI_API_KEYS or [])
        return ConnectionOut(
            id=f"openai-{idx}",
            provider="openai",
            base_url=url,
            price_per_1k=_price(fc),
            has_api_key=bool(fk[idx] if idx < len(fk) else ""),
        )

    if provider == "ollama":
        urls = list(request.app.state.config.OLLAMA_BASE_URLS or [])
        if idx < 0 or idx >= len(urls):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        url = urls[idx]

        configs = dict(request.app.state.config.OLLAMA_API_CONFIGS or {})
        cfg = dict(configs.get(url, {}))
        if body.price_per_1k is not None:
            cfg["price_per_1k"] = body.price_per_1k
        configs[url] = cfg
        request.app.state.config.OLLAMA_API_CONFIGS = configs

        fc = dict(request.app.state.config.OLLAMA_API_CONFIGS or {}).get(url, {})
        return ConnectionOut(
            id=f"ollama-{idx}",
            provider="ollama",
            base_url=url,
            price_per_1k=_price(fc),
            has_api_key=False,
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid provider")
