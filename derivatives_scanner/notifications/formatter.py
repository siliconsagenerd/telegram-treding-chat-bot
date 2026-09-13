from __future__ import annotations

from datetime import datetime
from collections import defaultdict
from zoneinfo import ZoneInfo

from derivatives_scanner.core.risk_engine import KORisk, Suppression
from derivatives_scanner.core.setup_generator import DerivativeSetup, MomentumSetup

NONE_QUALIFIED = "• None qualified"
SUPPRESSION_TICKER_LIMIT = 10

EXECUTION_RULES = (
    "EXECUTION PROTOCOL:\n\n"
    "Max allocation: 1.0% - 2.0% capital per trade.\n\n"
    "Derivatives horizon: 30–45 DTE.\n\n"
    "Avoid market orders in the first 30m of the local session."
)


def _currency_symbol(region: str) -> str:
    r = region.strip().lower()
    if r in {"india", "in"}:
        return "₹"
    elif r in {"europe", "eu"}:
        return "€"
    return "$"


def _bias_label(score: float) -> str:
    if score >= 30:
        return f"🟢 Strong Bullish (Trend +{int(score)})"
    elif score <= -30:
        return f"🔴 Heavy Bearish (Trend {int(score)})"
    elif score > 0:
        return f"🟢 Mild Bullish (Trend +{int(score)})"
    elif score < 0:
        return f"🔴 Mild Bearish (Trend {int(score)})"
    return f"⚪ Neutral (Trend {int(score)})"


def _vol_label(vol_rank: float | None) -> str:
    if vol_rank is None:
        return "n/a"
    if vol_rank < 35:
        return f"{vol_rank:.0f}% (Low IV)"
    elif vol_rank <= 55:
        return f"{vol_rank:.0f}% (Fair IV)"
    elif vol_rank <= 80:
        return f"{vol_rank:.0f}% (Elevated IV)"
    return f"{vol_rank:.0f}% (Overheated IV)"


def format_momentum_section(momentum_setups: list[MomentumSetup], region: str = "all") -> str:
    header = "🚀 INTRADAY BREAKOUTS"
    if not momentum_setups:
        return f"{header}\n{NONE_QUALIFIED}"

    currency = _currency_symbol(region)
    cards = [header]
    for s in momentum_setups:
        exp_abs = s.expected_move_abs if s.expected_move_abs is not None else (s.close * s.expected_move_pct / 100)
        is_bull = s.trend_score >= 0
        stoploss = s.close - exp_abs if is_bull else s.close + exp_abs
        target = s.close + exp_abs if is_bull else s.close - exp_abs
        pct_label = f"+{s.expected_move_pct:.1f}% Upside" if is_bull else f"-{s.expected_move_pct:.1f}% Downside"

        card = (
            f"• Ticker: {s.ticker}\n"
            f"  LTP: {currency}{s.close:,.2f}\n"
            f"  Stoploss: {currency}{stoploss:,.2f}\n"
            f"  Target: {currency}{target:,.2f}\n"
            f"  Potential: {pct_label} | Vol: {s.volume_ratio:.1f}x\n"
            f"  Catalyst: {s.catalyst}"
        )
        cards.append(card)
    return "\n\n".join(cards)


def format_bullish_breakouts_section(momentum_setups: list[MomentumSetup], region: str = "all") -> str:
    bulls = [s for s in momentum_setups if s.trend_score >= 0]
    header = "🚀 BULLISH BREAKOUTS"
    if not bulls:
        return f"{header}\n{NONE_QUALIFIED}"

    currency = _currency_symbol(region)
    cards = [header]
    for s in bulls:
        exp_abs = s.expected_move_abs if s.expected_move_abs is not None else (s.close * s.expected_move_pct / 100)
        stoploss = s.close - exp_abs
        target = s.close + exp_abs

        card = (
            f"• Ticker: {s.ticker}\n"
            f"  LTP: {currency}{s.close:,.2f}\n"
            f"  Stoploss: {currency}{stoploss:,.2f}\n"
            f"  Target: {currency}{target:,.2f}\n"
            f"  Potential Upside: +{s.expected_move_pct:.1f}%"
        )
        cards.append(card)
    return "\n\n".join(cards)


def format_bearish_breakouts_section(momentum_setups: list[MomentumSetup], region: str = "all") -> str:
    bears = [s for s in momentum_setups if s.trend_score < 0]
    header = "🔥 BEARISH BREAKOUTS"
    if not bears:
        return f"{header}\n{NONE_QUALIFIED}"

    currency = _currency_symbol(region)
    cards = [header]
    for s in bears:
        exp_abs = s.expected_move_abs if s.expected_move_abs is not None else (s.close * s.expected_move_pct / 100)
        stoploss = s.close + exp_abs
        target = s.close - exp_abs

        card = (
            f"• Ticker: {s.ticker}\n"
            f"  LTP: {currency}{s.close:,.2f}\n"
            f"  Stoploss: {currency}{stoploss:,.2f}\n"
            f"  Target: {currency}{target:,.2f}\n"
            f"  Potential Downside: -{s.expected_move_pct:.1f}%"
        )
        cards.append(card)
    return "\n\n".join(cards)


def format_bearish_section(bearish_setups: list[DerivativeSetup], region: str = "all") -> str:
    header = "🔥 BEARISH SETUPS (Long Puts / Bear Warrants)"
    if not bearish_setups:
        return f"{header}\n{NONE_QUALIFIED}"

    currency = _currency_symbol(region)
    cards = [header]
    for s in bearish_setups:
        exp_abs = s.expected_move_abs if s.expected_move_abs is not None else (s.close * (s.expected_move_pct or 0.0) / 100)
        pct = f"{s.expected_move_pct:.1f}%" if s.expected_move_pct is not None else f"{s.atr_percent:.1f}%"
        dte = s.dte or 35

        card = (
            f"• {s.ticker} | Spot: {currency}{s.close:,.2f}\n"
            f"Target Strike: {currency}{s.strike_target:,.2f} Put | Exp: {dte} DTE | Delta: {s.delta_target}\n"
            f"Exp. Move: ±{exp_abs:,.2f} ({pct}) | Downside Target: {currency}{s.target_price:,.2f}\n"
            f"ATR: {s.atr_percent:.1f}% | Vol Rank: {_vol_label(s.vol_rank)}"
        )
        cards.append(card)
    return "\n\n".join(cards)


def format_bullish_section(bullish_setups: list[DerivativeSetup], region: str = "all") -> str:
    header = "🚀 BULLISH SETUPS (Long Calls / Bull Warrants)"
    if not bullish_setups:
        return f"{header}\n{NONE_QUALIFIED}"

    currency = _currency_symbol(region)
    cards = [header]
    for s in bullish_setups:
        exp_abs = s.expected_move_abs if s.expected_move_abs is not None else (s.close * (s.expected_move_pct or 0.0) / 100)
        pct = f"{s.expected_move_pct:.1f}%" if s.expected_move_pct is not None else f"{s.atr_percent:.1f}%"
        dte = s.dte or 35

        card = (
            f"• {s.ticker} | Spot: {currency}{s.close:,.2f}\n"
            f"Target Strike: {currency}{s.strike_target:,.2f} Call | Exp: {dte} DTE | Delta: {s.delta_target}\n"
            f"Exp. Move: ±{exp_abs:,.2f} ({pct}) | Upside Target: {currency}{s.target_price:,.2f}\n"
            f"ATR: {s.atr_percent:.1f}% | Vol Rank: {_vol_label(s.vol_rank)}"
        )
        cards.append(card)
    return "\n\n".join(cards)


def format_turbo_section(turbo_rows: list[KORisk], region: str = "all") -> str:
    r_key = (region or "all").strip().lower()
    if r_key in {"us", "america"}:
        reg_label = "US Market"
    elif r_key in {"india", "in"}:
        reg_label = "India NSE"
    elif r_key in {"eu", "europe"}:
        reg_label = "Europe"
    else:
        reg_label = "Global"

    header = f"⚡ TURBO BARRIER SAFETY MONITOR ({reg_label})"
    if not turbo_rows:
        return f"{header}\n{NONE_QUALIFIED}"

    currency = _currency_symbol(region)
    cards = [header]
    for k in turbo_rows:
        trade_label = "BULL TURBO (Long)" if k.trade_type == "BULL" else "BEAR TURBO (Short)"
        card = (
            f"• {k.ticker} | {trade_label}\n"
            f"Spot: {currency}{k.spot_price:,.2f} | KO Barrier: {currency}{k.ko_strike:,.2f} | Buffer: {k.buffer_percent:.1f}%\n"
            f"Safety Margin: {k.atr_buffer_ratio:.1f}x ATR ({k.risk_level}) | Leverage: ~{k.recommended_leverage:.1f}x"
        )
        cards.append(card)
    return "\n\n".join(cards)


def format_suppressions_section(suppressions: list[Suppression]) -> str:
    header = "⚠️ FILTER SUPPRESSIONS"
    if not suppressions:
        return f"{header}\n{NONE_QUALIFIED}"

    grouped: dict[str, list[str]] = defaultdict(list)
    for item in suppressions:
        grouped[item.reason].append(item.ticker)

    out = [header]
    for reason, tickers in grouped.items():
        if len(tickers) > SUPPRESSION_TICKER_LIMIT:
            shown = ", ".join(tickers[:SUPPRESSION_TICKER_LIMIT])
            hidden = len(tickers) - SUPPRESSION_TICKER_LIMIT
            out.append(f"• {reason}: {shown} ... (+{hidden} more)")
        else:
            out.append(f"• {reason}: {', '.join(tickers)}")
    return "\n".join(out)


def format_radar_report(
    mode: str,
    region: str,
    bearish_setups: list[DerivativeSetup],
    bullish_setups: list[DerivativeSetup],
    momentum_setups: list[MomentumSetup],
    turbo_rows: list[KORisk],
    suppressions: list[Suppression],
) -> str:
    r_key = (region or "all").strip().lower()
    if r_key in {"us", "america"}:
        region_title = "US MARKET"
    elif r_key in {"india", "in"}:
        region_title = "INDIA NSE"
    elif r_key in {"eu", "europe"}:
        region_title = "EUROPE"
    else:
        region_title = "GLOBAL"

    now_berlin = datetime.now(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H:%M CEST")
    title_block = f"DERIVATIVE ACTION RADAR — {region_title}\n{now_berlin} | Regular Session"

    sections = [
        title_block,
        format_momentum_section(momentum_setups, region),
        format_bearish_section(bearish_setups, region),
        format_bullish_section(bullish_setups, region),
        format_turbo_section(turbo_rows, region),
        format_suppressions_section(suppressions),
        EXECUTION_RULES
    ]

    return "\n\n".join(s.strip() for s in sections if s.strip()).strip()