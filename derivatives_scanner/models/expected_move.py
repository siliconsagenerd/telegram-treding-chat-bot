from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExpectedMoveResult:
    expected_move_abs: float | None
    expected_move_pct: float | None
    source: str
    iv: float | None = None
    dte: int | None = None


@dataclass(frozen=True)
class TrendVector:
    trend_score: float
    breakout_bias: str
    z_score: float | None
    ema_gap_pct: float | None
    slope_score: float


def calculate_expected_move(
    spot: float,
    iv: float | None = None,
    dte: int | None = None,
    atr: float | None = None,
    atm_straddle: float | None = None,
    target_days: int | None = None,
) -> ExpectedMoveResult:
    if spot <= 0:
        return ExpectedMoveResult(expected_move_abs=None, expected_move_pct=None, source="invalid")

    move_abs: float | None = None
    source = "unknown"

    if atm_straddle is not None and atm_straddle > 0:
        move_abs = 0.85 * atm_straddle
        source = "straddle"
    elif iv is not None and iv > 0 and dte is not None and dte > 0:
        move_abs = spot * iv * sqrt(dte / 365.0)
        source = "iv"
    elif atr is not None and atr > 0:
        horizon = max(target_days or dte or 1, 1)
        move_abs = atr * sqrt(horizon)
        source = "atr"

    if move_abs is None:
        return ExpectedMoveResult(expected_move_abs=None, expected_move_pct=None, source=source, iv=iv, dte=dte)

    return ExpectedMoveResult(
        expected_move_abs=float(move_abs),
        expected_move_pct=float((move_abs / spot) * 100.0),
        source=source,
        iv=iv,
        dte=dte,
    )


def score_trend_vector(history: pd.DataFrame) -> TrendVector:
    if history is None or history.empty or "Close" not in history.columns:
        return TrendVector(trend_score=0.0, breakout_bias="NEUTRAL", z_score=None, ema_gap_pct=None, slope_score=0.0)

    close = history["Close"].astype(float)
    ema20 = close.ewm(span=20, adjust=False).mean()
    sma50 = close.rolling(window=50).mean()
    std50 = close.rolling(window=50).std()

    latest_close = float(close.iloc[-1])
    latest_ema20 = float(ema20.iloc[-1])
    latest_sma50 = float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else latest_ema20
    latest_std50 = float(std50.iloc[-1]) if not pd.isna(std50.iloc[-1]) and std50.iloc[-1] > 0 else None

    ema_gap_pct = ((latest_close - latest_ema20) / latest_ema20) * 100.0 if latest_ema20 > 0 else None
    z_score = ((latest_close - latest_sma50) / latest_std50) if latest_std50 else None

    ema_slope = float(ema20.diff().tail(5).mean()) if len(ema20.dropna()) >= 5 else 0.0
    sma_slope = float(sma50.diff().tail(5).mean()) if len(sma50.dropna()) >= 5 else 0.0
    slope_score = 0.0
    if latest_close > 0:
        slope_score = np.clip(((ema_slope + sma_slope) / latest_close) * 1_000, -50.0, 50.0)

    distance_score = 0.0
    if ema_gap_pct is not None:
        distance_score = float(np.clip(ema_gap_pct * 4.0, -40.0, 40.0))

    alignment_score = 0.0
    if latest_close > latest_ema20 > latest_sma50:
        alignment_score = 25.0
        breakout_bias = "BULLISH"
    elif latest_close < latest_ema20 < latest_sma50:
        alignment_score = -25.0
        breakout_bias = "BEARISH"
    else:
        breakout_bias = "NEUTRAL"

    z_component = 0.0
    if z_score is not None:
        z_component = float(np.clip(-z_score * 6.0, -25.0, 25.0))

    trend_score = float(np.clip(distance_score + alignment_score + slope_score + z_component, -100.0, 100.0))
    if trend_score > 25 and breakout_bias == "NEUTRAL":
        breakout_bias = "BULLISH"
    elif trend_score < -25 and breakout_bias == "NEUTRAL":
        breakout_bias = "BEARISH"

    return TrendVector(
        trend_score=trend_score,
        breakout_bias=breakout_bias,
        z_score=float(z_score) if z_score is not None else None,
        ema_gap_pct=float(ema_gap_pct) if ema_gap_pct is not None else None,
        slope_score=float(slope_score),
    )


_BULLISH_WORDS = {
    "beat",
    "beats",
    "surge",
    "rally",
    "upgrade",
    "record",
    "growth",
    "approval",
    "expands",
    "wins",
    "bullish",
}

_BEARISH_WORDS = {
    "miss",
    "misses",
    "downgrade",
    "lawsuit",
    "probe",
    "investigation",
    "cuts",
    "slump",
    "warning",
    "bearish",
    "delay",
    "restructuring",
}


def score_news_catalyst(tokens: list[str], headlines: list[str]) -> float:
    score = 0.0
    for token in tokens:
        lowered = token.lower()
        if lowered in {"earnings", "trial", "fda", "guidance", "merger", "acquisition"}:
            score += 8.0
        elif lowered in {"investigation"}:
            score -= 6.0

    for headline in headlines:
        text = headline.lower()
        if any(word in text for word in _BULLISH_WORDS):
            score += 4.0
        if any(word in text for word in _BEARISH_WORDS):
            score -= 4.0

    return float(np.clip(score, -50.0, 50.0))


def score_news_sentiment(headlines: list[str]) -> float:
    score = 0.0
    for headline in headlines:
        text = headline.lower()
        if any(word in text for word in _BULLISH_WORDS):
            score += 2.5
        if any(word in text for word in _BEARISH_WORDS):
            score -= 2.5
    return float(np.clip(score, -25.0, 25.0))
