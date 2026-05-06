"""Map model IDs to OpenAI/Ollama connection URLs and per-connection price_per_1k."""

from __future__ import annotations

from typing import Optional, Tuple

from fastapi import Request

from open_webui.models.models import Models as ModelsStore

_MAX_BASE_CHAIN = 12


def _price_from_cfg(cfg: dict) -> Optional[float]:
    if not cfg or "price_per_1k" not in cfg:
        return None
    try:
        v = float(cfg["price_per_1k"])
        return max(0.0, v)
    except (TypeError, ValueError):
        return None


def _price_for_model(cfg: dict, model_id: str) -> Optional[float]:
    """
    Resolve USD per 1K tokens for this model on this connection.

    Optional dict on connection config:
      price_per_1k_by_model (alias: model_prices): { "<model_id>": number, ... }
    Overrides the single price_per_1k when the message model id matches a key.
    """
    if not cfg:
        return None
    bym = cfg.get("price_per_1k_by_model") or cfg.get("model_prices")
    if isinstance(bym, dict) and model_id in bym:
        raw = bym.get(model_id)
        if raw is not None and raw != "":
            try:
                return max(0.0, float(raw))
            except (TypeError, ValueError):
                pass
    return _price_from_cfg(cfg)


def _resolve_direct(
    mid: str, request: Request
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Match model id to connection without workspace/base-model fallbacks."""
    cfg_state = request.app.state.config

    openai_urls = list(cfg_state.OPENAI_API_BASE_URLS or [])
    openai_configs = dict(cfg_state.OPENAI_API_CONFIGS or {})

    def try_openai() -> Optional[Tuple[str, Optional[float]]]:
        singles: list[Tuple[str, dict]] = []
        for url in openai_urls:
            cfg = openai_configs.get(url) or {}
            prefix = (cfg.get("prefix_id") or "").strip()
            mids = cfg.get("model_ids") or []

            if prefix:
                if mid == prefix or mid.startswith(prefix + "."):
                    return (url, _price_for_model(cfg, mid))
                continue

            if mids:
                if mid in mids:
                    return (url, _price_for_model(cfg, mid))
                continue

            singles.append((url, cfg))

        if len(singles) == 1:
            u, c = singles[0]
            return (u, _price_for_model(c, mid))
        return None

    hit = try_openai()
    if hit:
        return hit[0], hit[1], "openai"

    ollama_urls = list(cfg_state.OLLAMA_BASE_URLS or [])
    ollama_configs = dict(cfg_state.OLLAMA_API_CONFIGS or {})

    def try_ollama() -> Optional[Tuple[str, Optional[float]]]:
        singles_o: list[Tuple[str, dict]] = []
        for url in ollama_urls:
            cfg = ollama_configs.get(url) or {}
            prefix = (cfg.get("prefix_id") or "").strip()
            mids = cfg.get("model_ids") or []

            if prefix:
                if mid == prefix or mid.startswith(prefix + "."):
                    return (url, _price_for_model(cfg, mid))
                continue

            if mids:
                if mid in mids:
                    return (url, _price_for_model(cfg, mid))
                continue

            singles_o.append((url, cfg))

        if len(singles_o) == 1:
            u, c = singles_o[0]
            return (u, _price_for_model(c, mid))
        return None

    hit_o = try_ollama()
    if hit_o:
        return hit_o[0], hit_o[1], "ollama"

    return None, None, None


def resolve_model_connection(
    model_id: str,
    request: Request,
    _depth: int = 0,
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Returns (connection_base_url, price_per_1k_usd or None if unset, provider 'openai'|'ollama').

    If chats use a workspace model id that does not appear on any connection, pricing is
    resolved via Models.base_model_id when set (same id users pick when creating a custom model).

    Connection configs may set price_per_1k_by_model (or model_prices) for per-model prices
    on a single connection.
    """
    mid = (model_id or "").strip()
    if not mid:
        return None, None, None
    if _depth > _MAX_BASE_CHAIN:
        return None, None, None

    url, price, provider = _resolve_direct(mid, request)

    if url is None and price is None:
        row = ModelsStore.get_model_by_id(mid)
        if row and row.base_model_id:
            bid = (row.base_model_id or "").strip()
            if bid and bid != mid:
                return resolve_model_connection(bid, request, _depth + 1)
        return None, None, None

    if price is None:
        row = ModelsStore.get_model_by_id(mid)
        if row and row.base_model_id:
            bid = (row.base_model_id or "").strip()
            if bid and bid != mid:
                _, p2, _ = resolve_model_connection(bid, request, _depth + 1)
                if p2 is not None:
                    return url, p2, provider

    return url, price, provider
