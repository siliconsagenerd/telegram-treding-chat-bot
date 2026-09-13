from __future__ import annotations

import unittest
from unittest.mock import patch

from derivatives_scanner.config.tickers import get_tickers


class TickersTest(unittest.TestCase):
    @patch("derivatives_scanner.config.tickers.is_market_open", return_value=True)
    def test_region_specific_tickers(self, _mock_market_open) -> None:
        us = get_tickers("us")
        india = get_tickers("india")
        eu = get_tickers("eu")

        self.assertIn("AAPL", us)
        self.assertIn("INFY.NS", india)
        self.assertIn("SAP.DE", eu)
        self.assertNotIn("INFY.NS", us)

    @patch("derivatives_scanner.config.tickers.is_market_open", return_value=False)
    def test_manual_scans_ignore_market_open_filter(self, _mock_market_open) -> None:
        us = get_tickers("us", live_only=False)

        self.assertIn("AAPL", us)


if __name__ == "__main__":
    unittest.main()
