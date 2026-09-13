from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Iterable
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf
import yfinance.cache as _yfc

_yfc._TzCacheManager._tz_cache = _yfc._TzCacheDummy()
_yfc._CookieCacheManager._Cookie_cache = _yfc._CookieCacheDummy()
_yfc._ISINCacheManager._isin_cache = _yfc._ISINCacheDummy()

from derivatives_scanner.core.feature_engine import compute_atr14
from derivatives_scanner.models.expected_move import (
    ExpectedMoveResult,
    calculate_expected_move,
    score_news_catalyst,
    score_news_sentiment,
)

CATALYST_TOKENS = {
    "fda",
    "phase 3",
    "trial",
    "earnings",
    "investigation",
    "guidance",
    "merger",
    "acquisition",
}

_DATA_CACHE = {}
_CACHE_TTL = 300


@dataclass
class OptionMetrics:
    implied_move_pct: float | None
    nearest_expiry: str | None
    dte: int | None
    expected_move_abs: float | None
    expected_move_pct: float | None
    iv: float | None
    source: str


@dataclass
class EarningsMetrics:
    earnings_date: datetime | None
    days_to_earnings: int | None
    source: str


@dataclass
class EarningsEvent:
    ticker: str
    earnings_date: datetime | None
    earnings_time: str | None
    session: str | None
    source: str


@dataclass
class NewsMetrics:
    catalyst_tokens: list[str]
    headline_count: int
    top_headlines: list[str]
    catalyst_score: float
    sentiment_score: float


def _validate_ticker_history(df: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if not required_cols.issubset(df.columns):
        return None
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if len(df) < 20:
        return None
    for col in required_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=list(required_cols))
    if len(df) < 20:
        return None
    if "Ticker" not in df.columns:
        df["Ticker"] = ticker
    return df


def _fetch_single_ticker_history(ticker: str, period: str, interval: str) -> pd.DataFrame | None:
    try:
        hist = yf.Ticker(ticker).history(period=period, interval=interval)
    except Exception:
        return None
    if hist is None or hist.empty:
        return None

    df = hist.reset_index()
    clean = _validate_ticker_history(df, ticker)
    if clean is not None:
        return clean
    return None


def fetch_bulk_history(
    tickers: list[str],
    period: str = "1y",
    interval: str = "1d",
) -> dict[str, pd.DataFrame]:
    if not tickers:
        return {}

    cache_key = (tuple(sorted(tickers)), period, interval)
    now = time.time()
    if cache_key in _DATA_CACHE:
        cached_time, cached_data = _DATA_CACHE[cache_key]
        if now - cached_time < _CACHE_TTL:
            return cached_data

    ticker_str = " ".join(tickers)
    raw = None
    try:
        raw = yf.download(
            ticker_str,
            period=period,
            interval=interval,
            group_by="ticker",
            threads=True,
            progress=False,
        )
    except Exception:
        raw = None

    if raw is None or raw.empty:
        result: dict[str, pd.DataFrame] = {}
        max_workers = min(6, max(1, len(tickers)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_single_ticker_history, t, period, interval): t for t in tickers}
            for future in as_completed(futures):
                try:
                    clean = future.result()
                except Exception:
                    continue
                if clean is not None:
                    result[futures[future]] = clean
        _DATA_CACHE[cache_key] = (now, result)
        return result

    result: dict[str, pd.DataFrame] = {}

    if isinstance(raw.columns, pd.MultiIndex):
        level_values = [set(raw.columns.get_level_values(i)) for i in range(raw.columns.nlevels)]
        ticker_level = 0 if all(t in level_values[0] for t in tickers if t in level_values[0]) else 1

        available = set(raw.columns.get_level_values(ticker_level))
        for t in tickers:
            if t not in available:
                continue
            try:
                if ticker_level == 0:
                    df = raw[t].copy()
                else:
                    df = raw.xs(t, level=1, axis=1).copy()
            except Exception:
                continue
            df = df.reset_index()
            clean = _validate_ticker_history(df, t)
            if clean is not None:
                result[t] = clean
    else:
        df = raw.reset_index()
        clean = _validate_ticker_history(df, tickers[0])
        if clean is not None:
            result[tickers[0]] = clean

    if result:
        _DATA_CACHE[cache_key] = (now, result)
        return result

    fallback: dict[str, pd.DataFrame] = {}
    max_workers = min(6, max(1, len(tickers)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_single_ticker_history, t, period, interval): t for t in tickers}
        for future in as_completed(futures):
            try:
                clean = future.result()
            except Exception:
                continue
            if clean is not None:
                fallback[futures[future]] = clean

    _DATA_CACHE[cache_key] = (now, fallback)
    return fallback


def fetch_option_metrics(
    ticker: str,
    spot: float,
    history: pd.DataFrame | None = None,
    target_days: int = 35,
) -> OptionMetrics:
    """Instantaneous ATR-derived option metrics calculation.
    Bypasses slow network option chain lookups to eliminate scan latency.
    """
    atr14 = compute_atr14(history) if history is not None else None
    expected = calculate_expected_move(spot=spot, atr=atr14, target_days=target_days)
    return OptionMetrics(
        implied_move_pct=expected.expected_move_pct,
        nearest_expiry=None,
        dte=target_days,
        expected_move_abs=expected.expected_move_abs,
        expected_move_pct=expected.expected_move_pct,
        iv=None,
        source="atr_synthetic",
    )


def fetch_earnings_metrics(ticker: str, finnhub_api_key: str | None = None) -> EarningsMetrics:
    return EarningsMetrics(earnings_date=None, days_to_earnings=None, source="none")


def fetch_earnings_events(tickers: list[str], finnhub_api_key: str | None = None) -> list[EarningsEvent]:
    return []


def fetch_news_metrics(ticker: str) -> NewsMetrics:
    return NewsMetrics(
        catalyst_tokens=[],
        headline_count=0,
        top_headlines=[],
        catalyst_score=0.0,
        sentiment_score=0.0,
    )