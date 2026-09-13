from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root: Path
    model_path: Path
    scaler_path: Path
    env_file: Path
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_pass: str | None
    email_from: str | None
    email_to: list[str]
    telegram_token: str | None
    telegram_chat_id: str | None
    finnhub_api_key: str | None
    atr_percent_min: float
    volume_sma20_min: float
    vol_rank_overheated: float
    max_turbo_leverage: float


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for lineno, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid env line {lineno} in {env_path}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if not key:
            raise ValueError(f"Invalid env line {lineno} in {env_path}: empty key")
        if key not in os.environ:
            os.environ[key] = value


def _as_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a float, got {raw!r}") from exc


def _as_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def get_settings(root: Path | None = None) -> Settings:
    project_root = root or Path(__file__).resolve().parents[2]
    env_file = Path(os.environ.get("MARKET_ALERT_ENV_FILE", project_root / ".market_alert.env"))
    load_env_file(env_file)

    smtp_user = os.environ.get("SMTP_USER")
    return Settings(
        root=project_root,
        model_path=project_root / "best_model.zip",
        scaler_path=project_root / "scaler.pkl",
        env_file=env_file,
        smtp_host=os.environ.get("SMTP_HOST"),
        smtp_port=_as_int("SMTP_PORT", 465),
        smtp_user=smtp_user,
        smtp_pass=os.environ.get("SMTP_PASS"),
        email_from=os.environ.get("EMAIL_FROM", smtp_user),
        email_to=[x.strip() for x in os.environ.get("EMAIL_TO", "").split(",") if x.strip()],
        telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID"),
        finnhub_api_key=os.environ.get("FINNHUB_API_KEY"),
        atr_percent_min=_as_float("ATR_PERCENT_MIN", 1.5),
        volume_sma20_min=_as_float("VOLUME_SMA20_MIN", 1_000_000),
        vol_rank_overheated=_as_float("VOL_RANK_OVERHEATED", 90.0),
        max_turbo_leverage=_as_float("MAX_TURBO_LEVERAGE", 4.5),
    )