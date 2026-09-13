from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from derivatives_scanner.config.settings import Settings
from derivatives_scanner.main import run_scanner


def _dummy_settings() -> Settings:
    root = Path("/tmp")
    return Settings(
        root=root,
        model_path=root / "best_model.zip",
        scaler_path=root / "scaler.pkl",
        env_file=root / ".market_alert.env",
        smtp_host=None,
        smtp_port=465,
        smtp_user=None,
        smtp_pass=None,
        email_from=None,
        email_to=[],
        telegram_token=None,
        telegram_chat_id=None,
        finnhub_api_key=None,
        atr_percent_min=2.5,
        volume_sma20_min=1_000_000,
        vol_rank_overheated=80.0,
        max_turbo_leverage=4.5,
    )


class ScannerMainTest(unittest.TestCase):
    @patch("derivatives_scanner.main.get_tickers", return_value=[])
    def test_run_scanner_skips_when_no_tickers(self, _mock_get_tickers) -> None:
        result, events, emitted = run_scanner("model_sync", _dummy_settings(), region=None)

        self.assertFalse(emitted)
        self.assertEqual(events, [])
        self.assertEqual(result.report, "")
        self.assertEqual(result.bearish, [])
        self.assertEqual(result.bullish, [])
        self.assertEqual(result.momentum, [])
        self.assertEqual(result.turbo, [])
        self.assertEqual(result.suppressions, [])


if __name__ == "__main__":
    unittest.main()
