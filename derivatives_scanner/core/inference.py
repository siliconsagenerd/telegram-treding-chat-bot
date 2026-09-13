from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from stable_baselines3 import PPO

from .feature_engine import (
    build_state_features,
    calculate_technical_indicators,
    create_lagged_features,
)

ACTION_LABELS = {0: "Hold", 1: "Buy", 2: "Sell"}


def detect_breakout_status(df: pd.DataFrame) -> str:
    if df is None or len(df) < 21:
        return "Insufficient Data"

    df = df.copy().sort_values("Date").reset_index(drop=True)
    resistance = df["High"].rolling(window=20).max()
    support = df["Low"].rolling(window=20).min()

    current_close = df["Close"].iloc[-1]
    prev_resistance = resistance.iloc[-2] if len(resistance) >= 2 else resistance.iloc[-1]
    prev_support = support.iloc[-2] if len(support) >= 2 else support.iloc[-1]

    if pd.isna(prev_resistance) or pd.isna(prev_support):
        return "Neutral Range"

    if current_close >= prev_resistance:
        return "Bullish Breakout"
    if current_close <= prev_support:
        return "Bearish Breakdown"
    if current_close >= prev_resistance * 0.98:
        return "Nearing Bullish Breakout"
    if current_close <= prev_support * 1.02:
        return "Nearing Bearish Breakdown"
    return "Neutral Range"


def prepare_observation(df: pd.DataFrame, scaler, lookback_window=60) -> np.ndarray:
    df = calculate_technical_indicators(df.copy())
    df = create_lagged_features(df)
    df = df.ffill().bfill().dropna()

    state_features = build_state_features(df)
    if len(df) < lookback_window:
        raise ValueError(f"Need at least {lookback_window} rows for model input")

    recent = df.tail(lookback_window)[state_features].copy()
    scaled_window = scaler.transform(recent)
    market_state = scaled_window.reshape(-1)

    latest_price = float(recent["Close"].iloc[-1])
    balance = 10000.0
    shares_held = 0.0
    portfolio_state = np.array(
        [
            balance / 10000.0,
            (shares_held * latest_price) / 10000.0,
            balance / 10000.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ],
        dtype=np.float32,
    )

    return np.concatenate([market_state, portfolio_state]).astype(np.float32)


@dataclass
class InferenceSnapshot:
    ticker: str
    close: float
    ppo_action: str
    position_size: float
    market_structure: str
    history: pd.DataFrame


class InferenceEngine:
    def __init__(self, model_path: Path, scaler_path: Path) -> None:
        with open(scaler_path, "rb") as f:
            self.scaler = pickle.load(f)
        self.model = PPO.load(model_path)

    def _fetch_history(self, ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame | None:
        import yfinance as yf

        history = yf.Ticker(ticker).history(period=period, interval=interval)
        if history.empty:
            return None
        history = history.reset_index()
        history.columns = [col[0] if isinstance(col, tuple) else col for col in history.columns]
        if "Date" not in history.columns:
            history = history.rename_axis("Date").reset_index()
        history["Ticker"] = ticker
        return history

    def evaluate(self, ticker: str, history: pd.DataFrame | None = None) -> InferenceSnapshot | None:
        # If pre-fetched history is provided (bulk download), use it directly
        # instead of triggering a per-ticker yf.Ticker().history() network call.
        if history is None:
            history = self._fetch_history(ticker)
        if history is None or len(history) < 90:
            return None

        try:
            obs = prepare_observation(history.copy(), self.scaler)
        except Exception:
            return None

        if obs.shape[0] != self.model.observation_space.shape[0]:
            return None

        action, _ = self.model.predict(obs, deterministic=True)
        action_type = int(action[0])
        position_size = float(action[1])
        structure = detect_breakout_status(history)

        return InferenceSnapshot(
            ticker=ticker,
            close=float(history["Close"].iloc[-1]),
            ppo_action=ACTION_LABELS.get(action_type, "Unknown"),
            position_size=position_size,
            market_structure=structure,
            history=history,
        )
