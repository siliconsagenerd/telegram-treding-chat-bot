from __future__ import annotations

import unittest

from derivatives_scanner.core.setup_generator import CandidateInput, build_trade_setup


class SetupGeneratorTest(unittest.TestCase):
    def test_hold_neutral_zero_allocation_is_dropped(self) -> None:
        candidate = CandidateInput(
            ticker="TEST",
            close=100.0,
            ppo_action="Hold",
            market_structure="Neutral Range",
            position_size=0.0,
            atr14=3.0,
            atr_percent=3.0,
            vol_rank=40.0,
            implied_move_pct=5.0,
            expected_move_abs=6.0,
            expected_move_pct=6.0,
            hv30=35.0,
            earnings_days=10,
            catalyst_tokens=[],
            top_headlines=[],
            volume_ratio=1.0,
            trend_score=0.0,
            news_score=0.0,
            breakout_bias="NEUTRAL",
        )
        self.assertIsNone(build_trade_setup(candidate))


if __name__ == "__main__":
    unittest.main()
