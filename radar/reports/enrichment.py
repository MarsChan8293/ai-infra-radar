from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def _empty_entry_summary() -> dict[str, str | None]:
    return {"title_zh": None, "reason_text_zh": None, "reason_text_en": None}


def _empty_daily_briefing() -> dict[str, str | None]:
    return {"briefing_zh": None, "briefing_en": None}


def _fallback_reason_text(event: dict[str, Any]) -> str:
    return str(event.get("reason") or "")


def build_filter_tags(event: dict[str, Any]) -> dict[str, Any]:
    score = float(event["score"])
    if score >= 0.8:
        score_band = "high"
    elif score >= 0.4:
        score_band = "medium"
    else:
        score_band = "low"

    return {
        "source": event["source"],
        "alert_type": event["alert_type"],
        "score_band": score_band,
        "topic_tags": [event["source"]],
    }


def build_search_text(event: dict[str, Any]) -> str:
    filter_tags = event["filter_tags"]
    parts: list[str] = [
        str(event["display_name"]),
        str(event["source"]),
        str(event["alert_type"]),
        str(event.get("reason", "")),
        str(event.get("title_zh") or ""),
        str(event.get("reason_text_zh") or ""),
        str(event.get("reason_text_en") or ""),
    ]
    parts.extend(str(tag) for tag in filter_tags.get("topic_tags", []))
    return " ".join(part for part in parts if part).strip()


def enrich_report_events(
    events: list[dict[str, Any]],
    *,
    summarizer: Any,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for event in events:
        summary_fields = summarizer.summarize_entry(event)

        enriched_event = {
            **event,
            "filter_tags": build_filter_tags(event),
            "title_zh": summary_fields.get("title_zh"),
            "reason_text_zh": summary_fields.get("reason_text_zh"),
            "reason_text_en": summary_fields.get("reason_text_en")
            or _fallback_reason_text(event),
        }
        enriched_event["search_text"] = build_search_text(enriched_event)
        enriched.append(enriched_event)
    return enriched


def build_filter_summary(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    source_counts = Counter(event["filter_tags"]["source"] for event in events)
    alert_type_counts = Counter(event["filter_tags"]["alert_type"] for event in events)
    score_band_counts = Counter(event["filter_tags"]["score_band"] for event in events)
    topic_counts = Counter(
        tag for event in events for tag in event["filter_tags"]["topic_tags"]
    )
    return {
        "sources": [
            {"value": value, "count": count}
            for value, count in source_counts.most_common()
        ],
        "alert_types": [
            {"value": value, "count": count}
            for value, count in alert_type_counts.most_common()
        ],
        "score_bands": [
            {"value": value, "count": count}
            for value, count in score_band_counts.most_common()
        ],
        "topic_tags": [
            {"value": value, "count": count}
            for value, count in topic_counts.most_common()
        ],
    }


def build_enriched_daily_report(
    *,
    date: str,
    events: list[dict[str, Any]],
    summarizer: Any,
    include_daily_briefing: bool = True,
) -> dict[str, Any]:
    enriched = enrich_report_events(events, summarizer=summarizer)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in enriched:
        grouped[event["source"]].append(event)

    briefing = _empty_daily_briefing()
    if include_daily_briefing:
        briefing = summarizer.summarize_daily_briefing(date=date, entries=enriched)

    top_sources = Counter(event["source"] for event in enriched).most_common()
    return {
        "date": date,
        "summary": {
            "total_alerts": len(enriched),
            "top_sources": [
                {"source": source, "count": count} for source, count in top_sources
            ],
            "max_score": max((float(event["score"]) for event in enriched), default=0.0),
            "briefing_zh": briefing.get("briefing_zh"),
            "briefing_en": briefing.get("briefing_en"),
        },
        "filters": build_filter_summary(enriched),
        "topics": [
            {"topic": topic, "count": len(items), "events": items}
            for topic, items in sorted(grouped.items())
        ],
    }
