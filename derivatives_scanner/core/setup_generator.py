from __future__ import annotations

from dataclasses import dataclass

from derivatives_scanner.core.risk_engine import classify_signal, is_inactive_ticker


@dataclass
class CandidateInput:
    ticker: str
    close: float
    ppo_action: str
    market_structure: str
    position_size: float
    atr14: float
    atr_percent: float
    vol_rank: float | None
    implied_move_pct: float | None
    expected_move_abs: float | None
    expected_move_pct: float | None
    hv30: float | None
    catalyst_tokens: list[str]
    top_headlines: list[str]
    volume_ratio: float
    trend_score: float
    news_score: float
    breakout_bias: str
    dte: int | None = None
    earnings_days: int | None = None


@dataclass
class DerivativeSetup:
    ticker: str
    trade_type: str
    signal: str
    close: float
    structure: str
    strategy: str
    strike_target: float
    target_price: float
    delta_target: str
    atr_percent: float
    vol_rank: float | None
    implied_move_pct: float | None
    expected_move_abs: float | None
    expected_move_pct: float | None
    hv30: float | None
    catalyst_summary: str
    trend_score: float
    news_score: float
    high_momentum: bool
    dte: int | None = None


@dataclass
class MomentumSetup:
    ticker: str
    close: float
    atr_percent: float
    volume_ratio: float
    expected_move_pct: float
    expected_move_abs: float | None
    catalyst: str
    headlines: list[str]
    trend_score: float
    news_score: float
    high_momentum: bool


def build_momentum_setup(data: CandidateInput) -> MomentumSetup | None:
    # Allow high-velocity or high-volume breakouts
    if data.atr_percent < 1.5 and data.volume_ratio < 1.1:
        return None

    move_pct = data.expected_move_pct or max(data.atr_percent * 1.5, (data.implied_move_pct or 0.0) / 5)
    high_momentum = abs(data.trend_score) >= 35

    # Catalyst description fallback to technicals if news is empty
    if data.top_headlines:
        catalyst_str = data.top_headlines[0][:80]
    elif data.catalyst_tokens:
        catalyst_str = ", ".join(data.catalyst_tokens)
    else:
        catalyst_str = f"Volume breakout ({data.volume_ratio:.1f}x) & velocity expansion"

    return MomentumSetup(
        ticker=data.ticker,
        close=data.close,
        atr_percent=data.atr_percent,
        volume_ratio=data.volume_ratio,
        expected_move_pct=move_pct,
        expected_move_abs=data.expected_move_abs,
        catalyst=catalyst_str,
        headlines=data.top_headlines,
        trend_score=data.trend_score,
        news_score=data.news_score,
        high_momentum=high_momentum,
    )


def build_trade_setup(data: CandidateInput) -> DerivativeSetup | None:
    if is_inactive_ticker(data.ppo_action, data.market_structure, data.position_size):
        return None

    signal = classify_signal(data.ppo_action, data.market_structure)
    if signal is None:
        return None

    exp_abs = data.expected_move_abs if data.expected_move_abs is not None else (data.close * (data.atr_percent / 100.0))

    if signal == "BULL":
        target_strike = round(data.close + (0.5 * data.atr14), 2)
        target_price = round(data.close + exp_abs, 2)
        delta_target = "+0.44"
        strategy = "Long Calls / Bull Warrants"
        label = "Bullish Breakout" if "Bullish" in data.market_structure else "Bullish Momentum"
    else:
        target_strike = round(max(data.close - (0.5 * data.atr14), 0.01), 2)
        target_price = round(max(data.close - exp_abs, 0.01), 2)
        delta_target = "-0.42"
        strategy = "Long Puts / Bear Warrants"
        label = "Bearish Breakdown" if "Bearish" in data.market_structure else "Bearish Momentum"

    catalysts = []
    if data.catalyst_tokens:
        catalysts.append(", ".join(data.catalyst_tokens[:3]))

    return DerivativeSetup(
        ticker=data.ticker,
        trade_type=signal,
        signal=label,
        close=data.close,
        structure=data.market_structure,
        strategy=strategy,
        strike_target=target_strike,
        target_price=target_price,
        delta_target=delta_target,
        atr_percent=data.atr_percent,
        vol_rank=data.vol_rank,
        implied_move_pct=data.implied_move_pct,
        expected_move_abs=data.expected_move_abs,
        expected_move_pct=data.expected_move_pct,
        hv30=data.hv30,
        catalyst_summary=" | ".join(catalysts) if catalysts else "Technical Momentum",
        trend_score=data.trend_score,
        news_score=data.news_score,
        high_momentum=abs(data.trend_score) >= 35,
        dte=data.dte or 35,
    )