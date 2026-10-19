"""公开 USGS GeoJSON 适配器；区分观测发生时间与记录更新时间。"""

from datetime import datetime, timedelta, timezone
from src.ingestion.source_schema import RssSource, RssFetchResult, ParsedNewsItem


def parse_usgs(data: dict, source: RssSource, now: datetime) -> RssFetchResult:
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("Invalid USGS schema")
    result = RssFetchResult(
        source_name=source.name, success=True, fetched_at=now, fetched_count=len(data["features"])
    )
    for feature in data["features"]:
        try:
            p = feature["properties"]
            occurred = datetime.fromtimestamp(p["time"] / 1000, timezone.utc)
            updated = datetime.fromtimestamp(p["updated"] / 1000, timezone.utc)
            if updated > now + timedelta(hours=1) or not str(p["url"]).startswith(
                "https://earthquake.usgs.gov/"
            ):
                raise ValueError("Invalid observation timestamp or URL")
            title = str(p["title"])[:500]
            content = f"USGS reports {title}. Observation time: {occurred.isoformat()}. Magnitude: {p['mag']}. This is an instrument report; estimates may be revised."
            result.items.append(
                ParsedNewsItem(
                    source_name=source.name,
                    source_url=p["url"],
                    title=title,
                    content=content,
                    language=source.language,
                    published_at=updated,
                    time_quality="verified",
                    raw_published_at=str(p["updated"]),
                    metadata={
                        **source.provenance(),
                        "official_event_id": feature["id"],
                        "occurred_at": occurred.isoformat(),
                        "timestamp_semantics": "record_updated_at",
                        "magnitude": p["mag"],
                    },
                )
            )
        except (KeyError, ValueError, TypeError, OverflowError):
            result.skipped_count += 1
    result.items.sort(key=lambda n: n.published_at, reverse=True)
    result.items = result.items[: source.max_items]
    result.latest_published_at = max((n.published_at for n in result.items), default=None)
    return result
