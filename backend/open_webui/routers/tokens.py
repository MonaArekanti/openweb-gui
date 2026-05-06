"""Admin token usage stats: aggregates, daily deltas, model breakdown."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from open_webui.models.chats import Chats
from open_webui.models.models import Models as ModelsStore
from open_webui.utils.analytics import (
    aggregate_model_tokens_in_window,
    count_ui_messages,
    filter_non_shared_chats,
    iter_assistant_events_filtered,
    sum_tokens_in_window,
    total_assistant_tokens,
)
from open_webui.utils.auth import get_admin_user
from open_webui.utils.connection_pricing import resolve_model_connection

router = APIRouter()
DEFAULT_PRICE_PER_1K_USD = 1.0


def _parse_day(value: str) -> date:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format; use YYYY-MM-DD",
        ) from e


def _utc_day_start_timestamp(d: date) -> int:
    start = datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)
    return int(start.timestamp())


def _utc_day_end_exclusive(d: date) -> int:
    return _utc_day_start_timestamp(d + timedelta(days=1))


def _effective_price_per_1k(p1k: Optional[float]) -> float:
    """Use configured price when present, otherwise fallback to a safe default."""
    try:
        if p1k is None:
            return DEFAULT_PRICE_PER_1K_USD
        return max(0.0, float(p1k))
    except (TypeError, ValueError):
        return DEFAULT_PRICE_PER_1K_USD


class TokensSummaryResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    total_tokens: int
    total_estimated_cost_usd: float
    has_missing_connection_prices: bool
    avg_tokens_per_message: float
    rate_per_token_usd: float


class TokensDailyResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    today_tokens: int
    today_cost_usd: float
    yesterday_tokens: int
    yesterday_cost_usd: float
    change_percent: Optional[float] = Field(
        None,
        description="Percent change vs yesterday; null when yesterday had zero tokens.",
    )


class ModelBarRow(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    model_name: str
    value: float


class BreakdownRow(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    model_name: str
    connection_url: Optional[str] = None
    total_tokens: int
    price_per_1k_usd: Optional[float] = None
    total_cost_usd: Optional[float] = None


class TokenBreakdownResponse(BaseModel):
    rows: list[BreakdownRow]


def _estimated_cost_from_connections(chats: list, request: Request) -> tuple[float, bool]:
    acc = aggregate_model_tokens_in_window(
        chats,
        user_id=None,
        start_ts=None,
        end_ts_exclusive=None,
    )
    total = 0.0
    for mid, data in acc.items():
        tok = int(data["tokens"])
        _, price, _ = resolve_model_connection(mid, request)
        total += (tok / 1000.0) * _effective_price_per_1k(price)
    # We now fallback to DEFAULT_PRICE_PER_1K_USD whenever a model has no explicit price.
    return round(total, 6), False


def _estimated_cost_in_window(
    chats: list, request: Request, start_ts: int, end_exc: int
) -> float:
    from collections import defaultdict

    by_model: dict[str, int] = defaultdict(int)
    for ev in iter_assistant_events_filtered(
        chats,
        start_ts=start_ts,
        end_ts_exclusive=end_exc,
    ):
        by_model[ev["model_id"]] += ev["tokens"]
    total = 0.0
    for mid, tok in by_model.items():
        _, price, _ = resolve_model_connection(mid, request)
        total += (tok / 1000.0) * _effective_price_per_1k(price)
    return round(total, 6)


@router.get("/summary", response_model=TokensSummaryResponse)
async def get_tokens_summary(request: Request, user=Depends(get_admin_user)):
    del user
    chats_all = filter_non_shared_chats(Chats.get_chats())
    tokens_n = total_assistant_tokens(chats_all)
    messages_n = count_ui_messages(chats_all)
    rate = float(request.app.state.config.ANALYTICS_ESTIMATED_COST_PER_TOKEN_USD or 0)
    cost, missing = _estimated_cost_from_connections(chats_all, request)
    avg = round(tokens_n / messages_n, 1) if messages_n else 0.0

    return TokensSummaryResponse(
        total_tokens=tokens_n,
        total_estimated_cost_usd=cost,
        has_missing_connection_prices=missing,
        avg_tokens_per_message=avg,
        rate_per_token_usd=rate,
    )


@router.get("/daily", response_model=TokensDailyResponse)
async def get_tokens_daily(request: Request, user=Depends(get_admin_user)):
    del user
    chats_all = filter_non_shared_chats(Chats.get_chats())

    today_d = datetime.now(timezone.utc).date()
    yesterday_d = today_d - timedelta(days=1)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    today_start = _utc_day_start_timestamp(today_d)
    y_start = _utc_day_start_timestamp(yesterday_d)
    y_end_exc = _utc_day_end_exclusive(yesterday_d)

    # Today: midnight UTC through now (inclusive).
    today_tokens = sum_tokens_in_window(
        chats_all,
        start_ts=today_start,
        end_ts_exclusive=now_ts + 1,
    )
    yesterday_tokens = sum_tokens_in_window(
        chats_all,
        start_ts=y_start,
        end_ts_exclusive=y_end_exc,
    )

    today_cost = _estimated_cost_in_window(
        chats_all, request, today_start, now_ts + 1
    )
    yesterday_cost = _estimated_cost_in_window(
        chats_all, request, y_start, y_end_exc
    )

    change_pct: Optional[float]
    if yesterday_tokens == 0:
        change_pct = None
    else:
        change_pct = round(
            100.0 * (today_tokens - yesterday_tokens) / yesterday_tokens,
            1,
        )

    return TokensDailyResponse(
        today_tokens=today_tokens,
        today_cost_usd=today_cost,
        yesterday_tokens=yesterday_tokens,
        yesterday_cost_usd=yesterday_cost,
        change_percent=change_pct,
    )


def _model_display_name(model_id: str, fallback: str) -> str:
    row = ModelsStore.get_model_by_id(model_id)
    if row and row.name:
        return row.name
    return fallback


@router.get("/model-bars", response_model=list[ModelBarRow])
async def get_model_token_bars(
    request: Request,
    start_date: str = Query(...),
    end_date: str = Query(...),
    metric: str = Query("tokens", pattern="^(tokens|price)$"),
    user=Depends(get_admin_user),
):
    del user
    start_d = _parse_day(start_date)
    end_d = _parse_day(end_date)
    if end_d < start_d:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be on or after start_date",
        )

    start_ts = _utc_day_start_timestamp(start_d)
    end_ts_exc = _utc_day_end_exclusive(end_d)

    chats_all = filter_non_shared_chats(Chats.get_chats())
    acc = aggregate_model_tokens_in_window(
        chats_all,
        user_id=None,
        start_ts=start_ts,
        end_ts_exclusive=end_ts_exc,
    )

    rate = float(request.app.state.config.ANALYTICS_ESTIMATED_COST_PER_TOKEN_USD or 0)
    configured = ModelsStore.get_all_models()

    by_id: dict[str, ModelBarRow] = {}
    for m in configured:
        by_id[m.id] = ModelBarRow(model_id=m.id, model_name=m.name or m.id, value=0.0)

    for mid, data in acc.items():
        tok = int(data["tokens"])
        disp = _model_display_name(mid, data["display"])
        _, p1k, _ = resolve_model_connection(mid, request)
        effective_price = _effective_price_per_1k(p1k)
        if metric == "tokens":
            val = float(tok)
        else:
            val = round((tok / 1000.0) * effective_price, 6)
        if mid in by_id:
            by_id[mid] = ModelBarRow(model_id=mid, model_name=disp, value=val)
        else:
            by_id[mid] = ModelBarRow(model_id=mid, model_name=disp, value=val)

    rows = list(by_id.values())
    rows.sort(key=lambda r: r.value, reverse=True)
    return rows


@router.get("/breakdown", response_model=TokenBreakdownResponse)
async def get_token_breakdown(
    request: Request,
    user_id: Optional[str] = Query(None),
    user=Depends(get_admin_user),
):
    del user
    chats_all = filter_non_shared_chats(Chats.get_chats())

    acc = aggregate_model_tokens_in_window(
        chats_all,
        user_id=user_id,
        start_ts=None,
        end_ts_exclusive=None,
    )

    configured = {m.id: m for m in ModelsStore.get_all_models()}
    mids = set(acc.keys()) | set(configured.keys())

    rows: list[BreakdownRow] = []
    for mid in mids:
        mm = configured.get(mid)
        tok = int(acc[mid]["tokens"]) if mid in acc else 0
        disp = (
            mm.name
            if mm and mm.name
            else _model_display_name(mid, acc[mid]["display"] if mid in acc else mid)
        )
        conn_url, p1k, _ = resolve_model_connection(mid, request)
        effective_price = _effective_price_per_1k(p1k)
        cost_val: Optional[float] = round((tok / 1000.0) * effective_price, 6)
        rows.append(
            BreakdownRow(
                model_id=mid,
                model_name=disp,
                connection_url=conn_url,
                total_tokens=tok,
                price_per_1k_usd=round(effective_price, 6),
                total_cost_usd=cost_val,
            )
        )

    rows.sort(key=lambda r: r.total_tokens, reverse=True)
    return TokenBreakdownResponse(rows=rows)
