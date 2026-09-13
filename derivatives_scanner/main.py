from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass, replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

from derivatives_scanner.config.settings import Settings, get_settings
from derivatives_scanner.config.tickers import get_tickers
from derivatives_scanner.core.cache import store_scan_cache
from derivatives_scanner.core.data_pipeline import (
    fetch_bulk_history,
    fetch_option_metrics,
)
from derivatives_scanner.core.feature_engine import compute_atr14, compute_hv30_series
from derivatives_scanner.core.inference import InferenceEngine
from derivatives_scanner.core.risk_engine import (
    KORisk,
    Suppression,
    classify_signal,
    compute_vol_rank,
    evaluate_ko_risk,
    is_inactive_ticker,
)
from derivatives_scanner.core.setup_generator import (
    CandidateInput,
    DerivativeSetup,
    MomentumSetup,
    build_momentum_setup,
    build_trade_setup,
)
from derivatives_scanner.models.expected_move import score_trend_vector
from derivatives_scanner.notifications.formatter import format_radar_report
from derivatives_scanner.notifications.mailer import send_email
from derivatives_scanner.notifications.telegram_bot import send_telegram_message

MODE_CHANNELS: dict[str, str] = {
    "morning": "telegram",
    "midday": "telegram",
    "model_sync": "email",
    "premarket_us": "telegram",
    "us_open": "telegram",
    "monitor": "telegram",
    "evening": "telegram",
    "manual": "telegram",
}

MONITOR_KO_BREACH_LEVELS = {"CRITICAL"}
LATENCY_WARN_SECONDS = 8.0
_INFERENCE_ENGINE_CACHE: dict[tuple[str, int, str, int], InferenceEngine] = {}

_TZ_BERLIN = ZoneInfo("Europe/Berlin")


@dataclass
class ScanResult:
    mode: str
    bearish: list[DerivativeSetup]
    bullish: list[DerivativeSetup]
    momentum: list[MomentumSetup]
    turbo: list[KORisk]
    suppressions: list[Suppression]
    report: str


def resolve_auto_mode() -> str:
    now = datetime.now(_TZ_BERLIN)

    def is_near(target_h, target_m):
        target = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
        diff = abs((now - target).total_seconds())
        return diff < 300

    if is_near(7, 45): return "morning"
    if is_near(11, 0): return "midday"
    if is_near(12, 0): return "model_sync"
    if is_near(13, 0): return "premarket_us"
    if is_near(15, 35): return "us_open"
    if is_near(20, 0): return "evening"

    return "model_sync"


def _dispatch_alert(mode: str, body: str, settings: Settings) -> list[str]:
    events: list[str] = []
    channel = MODE_CHANNELS.get(mode, "email")

    if channel == "email":
        can_email = (
                settings.smtp_host
                and settings.smtp_user
                and settings.smtp_pass
                and settings.email_from
                and settings.email_to
        )
        if can_email:
            try:
                send_email(
                    subject=f"Derivative Action Radar | {mode}",
                    body=body,
                    smtp_host=settings.smtp_host,
                    smtp_port=settings.smtp_port,
                    smtp_user=settings.smtp_user,
                    smtp_pass=settings.smtp_pass,
                    sender=settings.email_from,
                    recipients=settings.email_to,
                )
                events.append("email:sent")
            except Exception as exc:
                events.append(f"email:failed:{exc}")
        else:
            events.append("email:skipped_missing_config")
        return events

    can_telegram = settings.telegram_token and settings.telegram_chat_id
    if can_telegram:
        try:
            send_telegram_message(settings.telegram_token, settings.telegram_chat_id, body)
            events.append("telegram:sent")
        except Exception as exc:
            events.append(f"telegram:failed:{exc}")
    else:
        events.append("telegram:skipped_missing_config")

    return events


def _monitor_should_alert(mode: str, turbo_rows: list[KORisk]) -> bool:
    if mode != "monitor":
        return True
    return any(row.risk_level in MONITOR_KO_BREACH_LEVELS for row in turbo_rows)


def _get_inference_engine(model_path: Path, scaler_path: Path) -> InferenceEngine:
    model_mtime = model_path.stat().st_mtime_ns if model_path.exists() else -1
    scaler_mtime = scaler_path.stat().st_mtime_ns if scaler_path.exists() else -1
    cache_key = (str(model_path), model_mtime, str(scaler_path), scaler_mtime)

    engine = _INFERENCE_ENGINE_CACHE.get(cache_key)
    if engine is None:
        engine = InferenceEngine(model_path, scaler_path)
        _INFERENCE_ENGINE_CACHE[cache_key] = engine
    return engine


def _build_scan_lists(
        settings: Settings,
        region: str | None = None,
        live_only: bool = True,
) -> tuple[
    list[DerivativeSetup],
    list[DerivativeSetup],
    list[MomentumSetup],
    list[KORisk],
    list[Suppression],
    list[object],
    int,
]:
    tickers = get_tickers(region, live_only=live_only)
    if not tickers:
        return [], [], [], [], [], [], 0

    engine = _get_inference_engine(settings.model_path, settings.scaler_path)

    bullish: list[DerivativeSetup] = []
    bearish: list[DerivativeSetup] = []
    momentum: list[MomentumSetup] = []
    turbo: list[KORisk] = []
    suppressions: list[Suppression] = []

    fetch_started = perf_counter()
    history_map = fetch_bulk_history(tickers, period="1y", interval="1d")
    fetch_elapsed = perf_counter() - fetch_started
    if fetch_elapsed >= LATENCY_WARN_SECONDS:
        print(
            f"[scanner] bulk history fetch region={region or 'all'} tickers={len(tickers)} took {fetch_elapsed:.2f}s",
            file=sys.stderr,
        )

    def process_ticker(ticker: str):
        try:
            hist = history_map.get(ticker)
            snapshot = engine.evaluate(ticker, history=hist)
            if snapshot is None:
                return None, None, Suppression(ticker=ticker, reason="No valid model input/data")

            atr14 = compute_atr14(snapshot.history)
            if atr14 is None or atr14 <= 0:
                return None, None, Suppression(ticker=ticker, reason="ATR unavailable")

            close = float(snapshot.close)
            atr_pct = (atr14 / close) * 100 if close > 0 else 0.0
            volume_sma20 = float(snapshot.history["Volume"].rolling(20).mean().iloc[-1])
            volume_ratio = float(snapshot.history["Volume"].iloc[-1] / volume_sma20) if volume_sma20 > 0 else 0.0

            hv_series = compute_hv30_series(snapshot.history)
            hv30 = float(hv_series.dropna().iloc[-1]) if not hv_series.dropna().empty else None
            vol_rank = compute_vol_rank(hv_series)
            trend = score_trend_vector(snapshot.history)

            if is_inactive_ticker(snapshot.ppo_action, snapshot.market_structure, snapshot.position_size):
                return None, None, None

            signal = classify_signal(snapshot.ppo_action, snapshot.market_structure)
            if signal is None:
                return None, None, None

            if atr_pct < settings.atr_percent_min:
                return None, None, Suppression(ticker=ticker,
                                               reason=f"ATR% < {settings.atr_percent_min:.1f}% (Insufficient Velocity)")
            if volume_sma20 < settings.volume_sma20_min:
                return None, None, Suppression(ticker=ticker, reason="Volume SMA20 < 1,000,000")
            if signal == "BULL" and vol_rank is not None and vol_rank > settings.vol_rank_overheated:
                return None, None, Suppression(ticker=ticker,
                                               reason=f"Vol Rank > {settings.vol_rank_overheated:.0f}% (Overheated IV)")

            candidate_base = CandidateInput(
                ticker=ticker,
                close=close,
                ppo_action=snapshot.ppo_action,
                market_structure=snapshot.market_structure,
                position_size=float(snapshot.position_size),
                atr14=float(atr14),
                atr_percent=float(atr_pct),
                vol_rank=vol_rank,
                implied_move_pct=None,
                expected_move_abs=None,
                expected_move_pct=None,
                hv30=hv30,
                earnings_days=None,
                catalyst_tokens=[],
                top_headlines=[],
                volume_ratio=volume_ratio,
                trend_score=trend.trend_score,
                news_score=0.0,
                breakout_bias=trend.breakout_bias,
            )

            option_metrics = fetch_option_metrics(ticker, close, history=snapshot.history)

            candidate = replace(
                candidate_base,
                implied_move_pct=option_metrics.implied_move_pct,
                expected_move_abs=option_metrics.expected_move_abs,
                expected_move_pct=option_metrics.expected_move_pct,
                earnings_days=None,
                dte=option_metrics.dte,
            )

            m_setup = build_momentum_setup(candidate)
            setup = build_trade_setup(candidate)

            if setup is None:
                return None, m_setup, None

            ko_risk = evaluate_ko_risk(
                ticker=ticker,
                trade_type=setup.trade_type,
                spot_price=setup.close,
                atr14=atr14,
                max_turbo_leverage=settings.max_turbo_leverage,
                ko_strike=None,
            )

            return (setup, ko_risk), m_setup, None

        except Exception as e:
            err = str(e).lower()
            if "database is locked" in err or "unable to open database" in err:
                reason = "API Fetch Failure (database lock)"
            elif "no data found" in err or "delisted" in err:
                reason = "Ticker delisted/no data"
            else:
                reason = f"Processing error: {type(e).__name__}"
            return None, None, Suppression(ticker=ticker, reason=reason)

    with ThreadPoolExecutor(max_workers=max(1, min(len(tickers), 10))) as executor:
        results = list(executor.map(process_ticker, tickers))

    for item, m_setup, suppression in results:
        if item:
            setup, ko_risk = item
            if setup.trade_type == "BEAR":
                bearish.append(setup)
            else:
                bullish.append(setup)
            if ko_risk:
                turbo.append(ko_risk)
        if m_setup:
            momentum.append(m_setup)
        if suppression:
            suppressions.append(suppression)

    # Max 5 per category to adhere to 4096 char limit
    bearish = sorted(bearish, key=lambda x: x.atr_percent, reverse=True)[:5]
    bullish = sorted(bullish, key=lambda x: x.atr_percent, reverse=True)[:5]
    momentum = sorted(momentum, key=lambda x: x.expected_move_pct, reverse=True)[:5]
    turbo = sorted(turbo, key=lambda x: x.atr_buffer_ratio)[:5]

    return bearish, bullish, momentum, turbo, suppressions, [], len(tickers)


def run_scanner(
        mode: str,
        settings: Settings,
        dispatch: bool = True,
        region: str | None = None,
) -> tuple[ScanResult, list[str], bool]:
    live_only = mode != "manual"
    bearish, bullish, momentum, turbo, suppressions, earnings_events, ticker_count = _build_scan_lists(
        settings,
        region=region,
        live_only=live_only,
    )

    if ticker_count == 0:
        result = ScanResult(
            mode=mode,
            bearish=[],
            bullish=[],
            momentum=[],
            turbo=[],
            suppressions=[],
            report="",
        )
        store_scan_cache(region, suppressions=[], earnings=[])
        return result, [], False

    should_emit = _monitor_should_alert(mode, turbo)
    report = ""
    if should_emit:
        report = format_radar_report(
            mode=mode,
            region=region or "all",
            bearish_setups=bearish,
            bullish_setups=bullish,
            momentum_setups=momentum,
            turbo_rows=turbo,
            suppressions=suppressions,
        )

    result = ScanResult(
        mode=mode,
        bearish=bearish,
        bullish=bullish,
        momentum=momentum,
        turbo=turbo,
        suppressions=suppressions,
        report=report,
    )
    store_scan_cache(region, suppressions=suppressions, earnings=earnings_events)

    events: list[str] = []
    if should_emit and dispatch:
        events = _dispatch_alert(mode, report, settings)

    return result, events, should_emit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Derivative & Turbo Warrant scanner")
    parser.add_argument(
        "--mode",
        choices=["morning", "midday", "model_sync", "premarket_us", "us_open", "monitor", "auto", "evening", "manual"],
        default="model_sync",
    )
    return parser


def cli_main() -> None:
    args = build_parser().parse_args()
    mode = resolve_auto_mode() if args.mode == "auto" else args.mode
    settings = get_settings()

    lock_file = Path(tempfile.gettempdir()) / f"derivatives_scanner_{mode}.lock"
    try:
        import fcntl
        f = open(lock_file, "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            print(f"Scanner for mode '{mode}' is already running (file locked). Skipping.")
            return

        result, events, emitted = run_scanner(mode, settings, region=None)
        if emitted:
            print(f"[{datetime.now()}] Scan emitted for mode '{mode}' (PID: {os.getpid()})")
            print(result.report)
            if events:
                print("\nDispatch:", ", ".join(events))
    except Exception as e:
        print(f"Error during scanner execution: {e}")


if __name__ == "__main__":
    cli_main()