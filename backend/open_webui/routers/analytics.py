from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from open_webui.models.chats import Chats
from open_webui.models.models import Models as ModelsStore
from open_webui.models.users import Users
from open_webui.utils.analytics import (
    aggregate_model_usage,
    aggregate_user_activity,
    count_ui_messages,
    daily_instance_activity_for_year,
    filter_non_shared_chats,
    total_assistant_tokens,
    usage_over_time_points,
)
from open_webui.models.sensitive_upload_event import get_sensitive_upload_block_counts
from open_webui.utils.auth import get_admin_user


router = APIRouter()


def _model_display_name(model_id: str, fallback: str) -> str:
    row = ModelsStore.get_model_by_id(model_id)
    if row and row.name:
        return row.name
    return fallback


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format; use YYYY-MM-DD",
        ) from e


class AnalyticsSummaryResponse(BaseModel):
    messages: int
    tokens: int
    chats: int
    users: int
    estimated_cost: float
    sensitive_upload_blocks_total: int = 0
    sensitive_upload_blocks_metadata: int = 0
    sensitive_upload_blocks_content: int = 0


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    request: Request,
    user=Depends(get_admin_user),
):
    chats_all = filter_non_shared_chats(Chats.get_chats())
    messages_n = count_ui_messages(chats_all)
    tokens_n = total_assistant_tokens(chats_all)
    chats_n = len(chats_all)
    users_n = Users.get_num_users() or 0
    rate = float(request.app.state.config.ANALYTICS_ESTIMATED_COST_PER_TOKEN_USD or 0)
    cost = round(tokens_n * rate, 6)
    su = get_sensitive_upload_block_counts()

    return AnalyticsSummaryResponse(
        messages=messages_n,
        tokens=tokens_n,
        chats=chats_n,
        users=users_n,
        estimated_cost=cost,
        sensitive_upload_blocks_total=su["total"],
        sensitive_upload_blocks_metadata=su["metadata_sensitive"],
        sensitive_upload_blocks_content=su["content_sensitive"],
    )


class LineChartFilterOption(BaseModel):
    id: str
    name: str


class LineChartFilterOptionsResponse(BaseModel):
    users: list[LineChartFilterOption]
    models: list[LineChartFilterOption]


@router.get(
    "/line-chart-filter-options",
    response_model=LineChartFilterOptionsResponse,
)
async def get_line_chart_filter_options(user=Depends(get_admin_user)):
    """User filter: everyone in the Users table. Models: from persisted chat usage."""
    del user
    all_users = Users.get_all_users()
    users_out: list[LineChartFilterOption] = []
    for u in all_users:
        label = (u.name or u.email or "").strip() or str(u.id)
        users_out.append(LineChartFilterOption(id=str(u.id), name=label))
    users_out.sort(key=lambda x: x.name.lower())

    chats_all = filter_non_shared_chats(Chats.get_chats())
    ma = aggregate_model_usage(chats_all)

    models_out: list[LineChartFilterOption] = []
    for mid, data in ma.items():
        disp = _model_display_name(mid, data["display"])
        models_out.append(LineChartFilterOption(id=str(mid), name=str(disp)))
    models_out.sort(key=lambda x: x.name.lower())

    return LineChartFilterOptionsResponse(users=users_out, models=models_out)


@router.get("/usage-over-time")
async def get_usage_over_time(
    metric: str = Query("messages", pattern="^(messages|tokens)$"),
    start_date: str = Query(...),
    end_date: str = Query(...),
    user_id: Optional[str] = None,
    model_id: Optional[str] = None,
    user=Depends(get_admin_user),
):
    start_d = _parse_date(start_date)
    end_d = _parse_date(end_date)
    if end_d < start_d:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be on or after start_date",
        )

    chats_all = filter_non_shared_chats(Chats.get_chats())
    return usage_over_time_points(
        chats_all,
        user_id=user_id,
        model_id=model_id,
        metric=metric,
        start_d=start_d,
        end_d=end_d,
    )


class ModelUsageRow(BaseModel):
    model_id: Optional[str] = None
    model: str
    messages: int
    tokens: int
    share_percent: float


@router.get("/model-usage", response_model=list[ModelUsageRow])
async def get_model_usage(user=Depends(get_admin_user)):
    del user
    chats_all = filter_non_shared_chats(Chats.get_chats())
    acc = aggregate_model_usage(chats_all)
    total_msgs = sum(v["messages"] for v in acc.values())
    if total_msgs == 0:
        return []

    rows = []
    for mid, data in acc.items():
        disp = _model_display_name(mid, data["display"])
        rows.append(
            {
                "mid": mid,
                "model": disp,
                "messages": data["messages"],
                "tokens": data["tokens"],
                "share_percent": round(100.0 * data["messages"] / total_msgs, 2),
            }
        )
    rows.sort(key=lambda r: r["messages"], reverse=True)

    top = rows[:8]
    rest = rows[8:]
    top_clean = [
        ModelUsageRow(
            model_id=r["mid"],
            model=r["model"],
            messages=r["messages"],
            tokens=r["tokens"],
            share_percent=r["share_percent"],
        )
        for r in top
    ]
    if not rest:
        return top_clean

    others_msgs = sum(r["messages"] for r in rest)
    others_toks = sum(r["tokens"] for r in rest)
    others_share = round(100.0 * others_msgs / total_msgs, 2)

    return top_clean + [
        ModelUsageRow(
            model_id=None,
            model="Others",
            messages=others_msgs,
            tokens=others_toks,
            share_percent=others_share,
        )
    ]


class UserActivityRow(BaseModel):
    rank: int
    user: str
    role: str
    messages: int
    tokens: int


@router.get("/user-activity", response_model=list[UserActivityRow])
async def get_user_activity(user=Depends(get_admin_user)):
    del user
    chats_all = filter_non_shared_chats(Chats.get_chats())
    acc = aggregate_user_activity(chats_all)

    enriched = []
    for u in Users.get_all_users():
        uid = str(u.id)
        stats = acc.get(uid) or {"messages": 0, "tokens": 0}
        label = (u.name or u.email or "").strip() or uid
        enriched.append(
            {
                "user_id": uid,
                "label": label,
                "role": u.role or "user",
                "messages": stats["messages"],
                "tokens": stats["tokens"],
            }
        )
    enriched.sort(key=lambda x: x["messages"], reverse=True)

    out: list[UserActivityRow] = []
    for i, row in enumerate(enriched, start=1):
        out.append(
            UserActivityRow(
                rank=i,
                user=row["label"],
                role=row["role"],
                messages=row["messages"],
                tokens=row["tokens"],
            )
        )
    return out


class HeatmapDayRow(BaseModel):
    date: str
    messages: int
    tokens: int


@router.get("/user-activity-heatmap", response_model=list[HeatmapDayRow])
async def get_user_activity_heatmap(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    user=Depends(get_admin_user),
):
    del user
    y = year if year is not None else datetime.utcnow().year
    chats_all = filter_non_shared_chats(Chats.get_chats())
    rows = daily_instance_activity_for_year(chats_all, y)
    return [HeatmapDayRow(**r) for r in rows]
