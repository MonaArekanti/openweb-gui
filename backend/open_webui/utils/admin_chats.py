"""Admin Chats page helpers: tag classification, message flattening, filters."""

from __future__ import annotations

from typing import Any, Optional

from open_webui.models.chats import ChatModel

TITLE_TAG_KEYWORDS: dict[str, list[str]] = {
    "TECH": [
        "ai",
        "artificial intelligence",
        "grok",
        "code",
        "software",
        "tech",
        "bot",
        "gpt",
        "model",
        "llm",
    ],
    "HEALTH": [
        "health",
        "medical",
        "doctor",
        "fitness",
        "diet",
        "wellness",
        "medicine",
        "symptom",
    ],
    "FINANCE": [
        "finance",
        "money",
        "budget",
        "invest",
        "stock",
        "cost",
        "revenue",
        "tax",
        "payment",
    ],
    "RETAIL": [
        "shop",
        "store",
        "product",
        "cart",
        "order",
        "customer",
        "sale",
        "ecommerce",
    ],
    "LOGISTICS": [
        "delivery",
        "shipping",
        "supply",
        "logistics",
        "transport",
        "warehouse",
        "fleet",
        "cargo",
    ],
    "AUTOMOTIVE": [
        "car",
        "vehicle",
        "auto",
        "drive",
        "motor",
        "electric vehicle",
        "ev",
        "truck",
    ],
    "MANUFACTURING": [
        "factory",
        "production",
        "manufacture",
        "assembly",
        "plant",
        "industrial",
        "machinery",
    ],
    "ENVIRONMENT": [
        "climate",
        "green",
        "carbon",
        "environment",
        "eco",
        "sustainability",
        "renewable",
        "energy",
    ],
    "GOVERNMENT": [
        "policy",
        "law",
        "government",
        "regulation",
        "compliance",
        "public",
        "federal",
        "legal",
    ],
}


def classify_title_tags(title: str) -> list[str]:
    if not title:
        return []
    low = title.lower()
    out: list[str] = []
    for tag, kws in TITLE_TAG_KEYWORDS.items():
        for kw in kws:
            if kw in low:
                if tag not in out:
                    out.append(tag)
                break
    return out


def chat_uses_model(chat: ChatModel, model_id: str) -> bool:
    if not model_id:
        return True
    messages = (chat.chat or {}).get("history", {}).get("messages") or {}
    for msg in messages.values():
        if msg.get("role") == "assistant" and str(msg.get("model") or "") == model_id:
            return True
    return False


def chat_matches_any_tag_filter(chat: ChatModel, selected: list[str]) -> bool:
    if not selected:
        return True
    title = chat.title or (chat.chat or {}).get("title") or ""
    tags = classify_title_tags(str(title))
    return bool(set(tags) & set(selected))


def count_list_messages(chat: dict) -> int:
    messages = (chat or {}).get("history", {}).get("messages") or {}
    n = 0
    for msg in messages.values():
        if msg.get("role") in ("user", "assistant", "system"):
            n += 1
    return n


def primary_model_for_chat(chat: ChatModel) -> tuple[str, str]:
    """Return (model_id, display_name) from the latest assistant message with a model."""
    messages = (chat.chat or {}).get("history", {}).get("messages") or {}
    last_mid = None
    last_ts = -1.0
    for mid, msg in messages.items():
        if msg.get("role") != "assistant":
            continue
        mid_val = msg.get("model")
        if not mid_val:
            continue
        ts = msg.get("timestamp")
        if isinstance(ts, (int, float)):
            t = float(ts)
            if t > 1e12:
                t /= 1000.0
        else:
            t = 0.0
        if t >= last_ts:
            last_ts = t
            last_mid = msg
    if last_mid:
        mid = str(last_mid.get("model"))
        name = str(last_mid.get("modelName") or mid)
        return (mid, name)
    return ("", "")


def linearize_history_messages(history: dict[str, Any]) -> list[dict[str, Any]]:
    """Active branch from root to currentId (same idea as frontend createMessagesList)."""
    if not history or not history.get("messages"):
        return []
    messages = history["messages"]
    current_id = history.get("currentId")
    if not current_id or current_id not in messages:
        # fallback: arbitrary order of user/assistant
        out = []
        for m in messages.values():
            if m.get("role") in ("user", "assistant", "system"):
                out.append(m)
        return out

    chain: list[dict[str, Any]] = []
    mid: Optional[str] = current_id
    while mid:
        m = messages.get(mid)
        if not m:
            break
        chain.append(m)
        mid = m.get("parentId")
    chain.reverse()
    return chain


def normalize_msg_timestamp(msg: dict) -> Optional[int]:
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


def merged_titles(chat: ChatModel) -> str:
    meta = chat.meta or {}
    extra = meta.get("merged_titles") or meta.get("titles")
    if isinstance(extra, list) and extra:
        return " ".join(str(x) for x in extra if x)
    return chat.title or (chat.chat or {}).get("title") or "New Chat"


def is_flagged_meta(meta: Optional[dict]) -> bool:
    if not meta or not isinstance(meta, dict):
        return False
    return bool(meta.get("is_flagged"))
