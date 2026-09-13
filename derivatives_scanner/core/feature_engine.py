from __future__ import annotations

import numpy as np
import pandas as pd


def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().sort_values("Date").reset_index(drop=True)
    df["Ticker"] = df.get("Ticker", "UNKNOWN")

    df["SMA_5"] = df["Close"].rolling(window=5).mean()
    df["SMA_10"] = df["Close"].rolling(window=10).mean()
    df["SMA_20"] = df["Close"].rolling(window=20).mean()
    df["SMA_50"] = df["Close"].rolling(window=50).mean()

    df["EMA_12"] = df["Close"].ewm(span=12, adjust=False).mean()
    df["EMA_26"] = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = df["EMA_12"] - df["EMA_26"]
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Histogram"] = df["MACD"] - df["MACD_Signal"]

    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    bb_middle = df["Close"].rolling(window=20).mean()
    bb_std = df["Close"].rolling(window=20).std()
    df["BB_Upper"] = bb_middle + (bb_std * 2)
    df["BB_Lower"] = bb_middle - (bb_std * 2)
    df["BB_Width"] = df["BB_Upper"] - df["BB_Lower"]
    df["BB_Position"] = (df["Close"] - df["BB_Lower"]) / df["BB_Width"].replace(0, np.nan)
    df["Volatility"] = df["Close"].rolling(window=20).std()
    df["Price_Change"] = df["Close"].pct_change()
    df["Price_Change_5d"] = df["Close"].pct_change(periods=5)
    df["High_Low_Ratio"] = df["High"] / df["Low"]
    df["Open_Close_Ratio"] = df["Open"] / df["Close"]
    df["Volume_SMA"] = df["Volume"].rolling(window=20).mean()
    df["Volume_Ratio"] = df["Volume"] / df["Volume_SMA"].replace(0, np.nan)
    return df


def create_lagged_features(df: pd.DataFrame, lags=(1, 2, 3, 5, 10)) -> pd.DataFrame:
    df = df.copy()
    feature_columns = ["Close", "Volume", "Price_Change", "RSI", "MACD", "Volatility"]
    for col in feature_columns:
        if col in df.columns:
            for lag in lags:
                df[f"{col}_lag_{lag}"] = df[col].shift(lag)
    return df


def build_state_features(df: pd.DataFrame) -> list[str]:
    base_features = [
        "Open", "High", "Low", "Close", "Volume",
        "SMA_5", "SMA_10", "SMA_20", "SMA_50",
        "EMA_12", "EMA_26", "MACD", "MACD_Signal", "RSI",
        "BB_Position", "BB_Width", "Volatility",
        "Price_Change", "High_Low_Ratio", "Volume_Ratio",
    ]
    lag_features = [col for col in df.columns if "_lag_" in col]
    return [col for col in base_features + lag_features if col in df.columns]


def compute_atr14(df: pd.DataFrame) -> float | None:
    required = {"High", "Low", "Close"}
    if not required.issubset(df.columns) or len(df) < 15:
        return None

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr14 = tr.rolling(window=14).mean().iloc[-1]
    if pd.isna(atr14):
        return None
    return float(atr14)


def compute_hv30_series(df: pd.DataFrame) -> pd.Series:
    if "Close" not in df.columns:
        return pd.Series(dtype=float)
    close = df["Close"].astype(float)
    log_returns = np.log(close / close.shift(1))
    return log_returns.rolling(window=30).std() * np.sqrt(252) * 100
