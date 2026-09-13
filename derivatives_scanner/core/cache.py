from __future__ import annotations

from typing import Any


scanner_cache: dict[str, Any] = {
    "suppressions": [],
    "earnings": {},
    "earnings_region": "all",
}


def normalize_region(region: str | None) -> str:
    normalized = (region or "all").strip().lower()
    if normalized in {"india", "in"}:
        return "india"
    if normalized in {"europe", "eu"}:
        return "eu"
    if normalized == "us":
        return "us"
    return "all"


def store_scan_cache(
    region: str | None,
    *,
    suppressions: list[object] | None = None,
    earnings: list[object] | None = None,
) -> None:
    normalized = normalize_region(region)
    if suppressions is not None:
        scanner_cache["suppressions"] = list(suppressions)
    if earnings is not None:
        earnings_cache = scanner_cache.get("earnings")
        if not isinstance(earnings_cache, dict):
            earnings_cache = {}
        earnings_cache[normalized] = list(earnings)
        scanner_cache["earnings"] = earnings_cache
        scanner_cache["earnings_region"] = normalized


def get_latest_suppressions() -> list[object]:
    return list(scanner_cache.get("suppressions", []))


def get_cached_earnings(region: str | None = None) -> list[object]:
    earnings_cache = scanner_cache.get("earnings")
    if not isinstance(earnings_cache, dict) or not earnings_cache:
        return []

    normalized = normalize_region(region)
    if normalized in earnings_cache:
        return list(earnings_cache.get(normalized, []))

    latest_region = normalize_region(scanner_cache.get("earnings_region"))
    if latest_region in earnings_cache:
        return list(earnings_cache.get(latest_region, []))

    return list(next(iter(earnings_cache.values())))
