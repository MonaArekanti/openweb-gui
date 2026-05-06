"""Admin token usage stats: aggregates, daily deltas, model breakdown."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from open_webui.models.chats import Chats
from open_webui.models.models import Models as ModelsStore
from open_webui.models.models import ModelModel
from open_webui.utils.analytics import (
    aggregate_model_tokens_in_window,
    count_ui_messages,
    filter_non_shared_chats,
    sum_tokens_in_window,
    total_assistant_tokens,
)
from open_webui.utils.auth import get_admin_user

router = APIRouter()


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


def _params_as_dict(params) -> dict:
    if isinstance(params, dict):
        return params
    if hasattr(params, "model_dump"):
        try:
            return params.model_dump()
        except Exception:
            pass
    return {}


def model_price_per_1k_usd(m: ModelModel, rate_per_token_usd: float) -> float:
    """Prefer explicit per-model USD per 1K tokens in params; else global estimate × 1000."""
    d = _params_as_dict(m.params)
    for key in ("price_per_1k_tokens_usd", "price_per_1k", "per_1k_token_price_usd"):
        v = d.get(key)
        if v is not None:
            try:
                return max(0.0, float(v))
            except (TypeError, ValueError):
                continue
    return max(0.0, float(rate_per_token_usd or 0.0)) * 1000.0


class TokensSummaryResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    total_tokens: int
    total_estimated_cost_usd: float
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
    total_tokens: int
    price_per_1k_usd: float
    total_cost_usd: float


class TokenBreakdownResponse(BaseModel):
    rows: list[BreakdownRow]


@router.get("/summary", response_model=TokensSummaryResponse)
async def get_tokens_summary(request: Request, user=Depends(get_admin_user)):
    del user
    chats_all = filter_non_shared_chats(Chats.get_chats())
    tokens_n = total_assistant_tokens(chats_all)
    messages_n = count_ui_messages(chats_all)
    rate = float(request.app.state.config.ANALYTICS_ESTIMATED_COST_PER_TOKEN_USD or 0)
    cost = round(tokens_n * rate, 6)
    avg = round(tokens_n / messages_n, 1) if messages_n else 0.0

    return TokensSummaryResponse(
        total_tokens=tokens_n,
        total_estimated_cost_usd=cost,
        avg_tokens_per_message=avg,
        rate_per_token_usd=rate,
    )


@router.get("/daily", response_model=TokensDailyResponse)
async def get_tokens_daily(request: Request, user=Depends(get_admin_user)):
    del user
    chats_all = filter_non_shared_chats(Chats.get_chats())
    rate = float(request.app.state.config.ANALYTICS_ESTIMATED_COST_PER_TOKEN_USD or 0)

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

    today_cost = round(today_tokens * rate, 6)
    yesterday_cost = round(yesterday_tokens * rate, 6)

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
        val = float(tok) if metric == "tokens" else round(tok * rate, 6)
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
    rate = float(request.app.state.config.ANALYTICS_ESTIMATED_COST_PER_TOKEN_USD or 0)

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
        if mm:
            p1k = model_price_per_1k_usd(mm, rate)
        else:
            p1k = rate * 1000.0
        cost = round((tok / 1000.0) * p1k, 6)
        rows.append(
            BreakdownRow(
                model_id=mid,
                model_name=disp,
                total_tokens=tok,
                price_per_1k_usd=round(p1k, 6),
                total_cost_usd=cost,
            )
        )

    rows.sort(key=lambda r: r.total_tokens, reverse=True)
    return TokenBreakdownResponse(rows=rows)
