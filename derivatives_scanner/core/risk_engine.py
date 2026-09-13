from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


BULLISH_STRUCTURES = {"Bullish Breakout", "Nearing Bullish Breakout"}
BEARISH_STRUCTURES = {"Bearish Breakdown", "Nearing Bearish Breakdown"}


@dataclass
class Suppression:
    ticker: str
    reason: str


@dataclass
class KORisk:
    ticker: str
    trade_type: str
    spot_price: float
    ko_strike: float
    buffer_percent: float
    atr_buffer_ratio: float
    risk_level: str
    recommended_leverage: float
    leverage_warning: str | None
    synthetic_stop: float


def classify_signal(ppo_action: str, market_structure: str) -> str | None:
    if market_structure in BEARISH_STRUCTURES:
        return "BEAR"
    if ppo_action == "Buy" or market_structure in BULLISH_STRUCTURES:
        return "BULL"
    return None


def is_inactive_ticker(ppo_action: str, market_structure: str, position_size: float) -> bool:
    return ppo_action == "Hold" and market_structure == "Neutral Range" and position_size <= 0.0


def compute_vol_rank(hv30_series: pd.Series) -> float | None:
    valid = hv30_series.dropna()
    if len(valid) < 40:
        return None
    window = valid.tail(252)
    floor = float(window.min())
    cap = float(window.max())
    latest = float(window.iloc[-1])
    if cap <= floor:
        return None
    return ((latest - floor) / (cap - floor)) * 100.0


def classify_ko_risk(atr_buffer_ratio: float) -> str:
    if atr_buffer_ratio < 1.5:
        return "CRITICAL"
    if atr_buffer_ratio < 2.5:
        return "ELEVATED"
    return "SAFE"


def compute_synthetic_preko_stop(spot_price: float, ko_strike: float, trade_type: str) -> float:
    if trade_type == "BULL":
        intrinsic = max(spot_price - ko_strike, 0.0)
        return ko_strike + 0.65 * intrinsic
    intrinsic = max(ko_strike - spot_price, 0.0)
    return ko_strike - 0.65 * intrinsic


def evaluate_ko_risk(
    ticker: str,
    trade_type: str,
    spot_price: float,
    atr14: float,
    max_turbo_leverage: float,
    ko_strike: float | None = None,
) -> KORisk:
    if atr14 <= 0:
        atr14 = max(spot_price * 0.01, 0.01)

    if ko_strike is None:
        if trade_type == "BULL":
            ko_strike = max(spot_price - (2.8 * atr14), 0.01)
        else:
            ko_strike = spot_price + (2.8 * atr14)

    raw_distance = abs(spot_price - ko_strike)
    buffer_percent = (raw_distance / spot_price) * 100 if spot_price > 0 else 0.0
    atr_buffer_ratio = raw_distance / atr14 if atr14 > 0 else 0.0
    risk_level = classify_ko_risk(atr_buffer_ratio)

    # Keep leverage conservative around KO distance and enforce hard cap warning.
    recommended_leverage = min(max_turbo_leverage, max(1.0, spot_price / max(raw_distance, 0.01)))
    leverage_warning = None
    if recommended_leverage > 4.5:
        leverage_warning = "WARNING: leverage above 4.5x cap"

    synthetic_stop = compute_synthetic_preko_stop(spot_price, ko_strike, trade_type)
    return KORisk(
        ticker=ticker,
        trade_type=trade_type,
        spot_price=spot_price,
        ko_strike=ko_strike,
        buffer_percent=buffer_percent,
        atr_buffer_ratio=atr_buffer_ratio,
        risk_level=risk_level,
        recommended_leverage=recommended_leverage,
        leverage_warning=leverage_warning,
        synthetic_stop=synthetic_stop,
    )