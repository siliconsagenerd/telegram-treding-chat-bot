from __future__ import annotations

import unittest

import pandas as pd

from derivatives_scanner.models.expected_move import calculate_expected_move, score_trend_vector


class ExpectedMoveTest(unittest.TestCase):
    def test_straddle_takes_priority(self) -> None:
        result = calculate_expected_move(spot=100.0, iv=0.4, dte=10, atr=2.0, atm_straddle=8.0)
        self.assertAlmostEqual(result.expected_move_abs or 0.0, 6.8, places=2)
        self.assertAlmostEqual(result.expected_move_pct or 0.0, 6.8, places=2)
        self.assertEqual(result.source, "straddle")

    def test_atr_fallback(self) -> None:
        result = calculate_expected_move(spot=100.0, atr=2.0, target_days=9)
        self.assertAlmostEqual(result.expected_move_abs or 0.0, 6.0, places=2)
        self.assertAlmostEqual(result.expected_move_pct or 0.0, 6.0, places=2)
        self.assertEqual(result.source, "atr")

    def test_trend_vector_detects_bullish_alignment(self) -> None:
        close = list(range(1, 80))
        history = pd.DataFrame({"Close": close})
        vector = score_trend_vector(history)
        self.assertIn(vector.breakout_bias, {"BULLISH", "NEUTRAL"})


if __name__ == "__main__":
    unittest.main()
