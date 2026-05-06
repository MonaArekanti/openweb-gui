"""Aggregate statistics from persisted chat JSON for admin analytics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Generator, Optional

from open_webui.models.chats import ChatModel


def normalize_timestamp(msg: dict) -> Optional[int]:
    ts = msg.get("timestamp")
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            t = float(ts)
            if t > 1e12:
                return int(t / 1000)
            return int(t)
    except (TypeError, ValueError):
        pass
    return None


def extract_tokens(msg: dict) -> int:
    usage = msg.get("usage") or {}
    if not isinstance(usage, dict):
        return 0
    tt = usage.get("total_tokens")
    if tt is not None:
        try:
            return max(0, int(tt))
        except (TypeError, ValueError):
            pass
    try:
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        return max(0, pt + ct)
    except (TypeError, ValueError):
        return 0


def iter_assistant_events(chats: list[ChatModel]) -> Generator[dict, None, None]:
    for chat in chats:
        uid = chat.user_id
        if uid.startswith("shared-"):
            continue
        messages = (chat.chat or {}).get("history", {}).get("messages") or {}
        for msg in messages.values():
            if msg.get("role") != "assistant":
                continue
            model_id = msg.get("model")
            if not model_id:
                continue
            ts = normalize_timestamp(msg)
            yield {
                "chat_user_id": uid,
                "model_id": str(model_id),
                "model_display": str(msg.get("modelName") or model_id),
                "ts": ts,
                "tokens": extract_tokens(msg),
            }


def count_ui_messages(chats: list[ChatModel]) -> int:
    n = 0
    for chat in chats:
        if chat.user_id.startswith("shared-"):
            continue
        messages = (chat.chat or {}).get("history", {}).get("messages") or {}
        for msg in messages.values():
            if msg.get("role") in ("user", "assistant"):
                n += 1
    return n


def total_assistant_tokens(chats: list[ChatModel]) -> int:
    return sum(ev["tokens"] for ev in iter_assistant_events(chats))


def aggregate_model_usage(chats: list[ChatModel]) -> dict[str, dict]:
    acc: dict[str, dict] = defaultdict(
        lambda: {"messages": 0, "tokens": 0, "display": ""}
    )
    for ev in iter_assistant_events(chats):
        mid = ev["model_id"]
        acc[mid]["messages"] += 1
        acc[mid]["tokens"] += ev["tokens"]
        if not acc[mid]["display"]:
            acc[mid]["display"] = ev["model_display"]
    return acc


def aggregate_user_activity(chats: list[ChatModel]) -> dict[str, dict]:
    acc: dict[str, dict] = defaultdict(lambda: {"messages": 0, "tokens": 0})
    for ev in iter_assistant_events(chats):
        uid = ev["chat_user_id"]
        acc[uid]["messages"] += 1
        acc[uid]["tokens"] += ev["tokens"]
    return acc


def usage_over_time_points(
    chats: list[ChatModel],
    *,
    user_id: Optional[str],
    model_id: Optional[str],
    metric: str,
    start_d: date,
    end_d: date,
) -> list[dict]:
    start_ts = int(
        datetime.combine(start_d, datetime.min.time())
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    end_exclusive = int(
        datetime.combine(end_d + timedelta(days=1), datetime.min.time())
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    tallies: dict[tuple[str, str], float] = defaultdict(float)

    for ev in iter_assistant_events(chats):
        if user_id and ev["chat_user_id"] != user_id:
            continue
        if model_id and ev["model_id"] != model_id:
            continue
        ts = ev["ts"]
        if ts is None:
            continue
        if ts < start_ts or ts >= end_exclusive:
            continue
        day = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        mid = ev["model_id"]
        if metric == "tokens":
            tallies[(day, mid)] += float(ev["tokens"])
        else:
            tallies[(day, mid)] += 1.0

    out: list[dict] = []
    for (day, mid), cnt in tallies.items():
        out.append({"date": day, "model": mid, "count": int(cnt)})
    out.sort(key=lambda x: (x["date"], x["model"]))
    return out


def filter_non_shared_chats(chats: list[ChatModel]) -> list[ChatModel]:
    return [c for c in chats if not c.user_id.startswith("shared-")]


def daily_instance_activity_for_year(chats: list[ChatModel], year: int) -> list[dict]:
    """UTC calendar days in ``year``: total assistant messages + tokens per day (instance-wide)."""
    y_start = date(year, 1, 1)
    y_end = date(year, 12, 31)
    start_ts = int(
        datetime.combine(y_start, datetime.min.time())
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    end_exc = int(
        datetime.combine(y_end + timedelta(days=1), datetime.min.time())
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )

    tallies: dict[str, dict[str, int]] = defaultdict(lambda: {"messages": 0, "tokens": 0})

    for ev in iter_assistant_events(chats):
        ts = ev["ts"]
        if ts is None:
            continue
        if ts < start_ts or ts >= end_exc:
            continue
        day = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        tallies[day]["messages"] += 1
        tallies[day]["tokens"] += ev["tokens"]

    out: list[dict] = []
    d = y_start
    while d <= y_end:
        key = d.isoformat()
        row = tallies.get(key, {"messages": 0, "tokens": 0})
        out.append(
            {
                "date": key,
                "messages": row["messages"],
                "tokens": row["tokens"],
            }
        )
        d += timedelta(days=1)
    return out
