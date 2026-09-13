from __future__ import annotations

import unittest

from derivatives_scanner.core.risk_engine import KORisk, Suppression
from derivatives_scanner.core.setup_generator import DerivativeSetup, MomentumSetup
from derivatives_scanner.notifications.formatter import (
    format_bearish_section,
    format_bullish_section,
    format_momentum_section,
    format_radar_report,
    format_suppressions_section,
    format_turbo_section,
)


def _momentum(ticker: str, headline: str) -> MomentumSetup:
    return MomentumSetup(
        ticker=ticker,
        close=100.0,
        atr_percent=3.0,
        volume_ratio=1.5,
        expected_move_pct=4.0,
        expected_move_abs=4.0,
        catalyst="News",
        headlines=[headline],
        trend_score=40.0,
        news_score=10.0,
        high_momentum=True,
    )


class FormatterTest(unittest.TestCase):
    def test_empty_sections_keep_their_header(self) -> None:
        self.assertEqual(format_bearish_section([]), "🔥 BEARISH SETUPS\n• None qualified\n")
        self.assertEqual(format_bullish_section([]), "🚀 BULLISH SETUPS\n• None qualified\n")
        self.assertEqual(format_turbo_section([]), "⚡ TURBO BARRIER MONITOR\n• None qualified\n")
        self.assertEqual(
            format_suppressions_section([]),
            "⚠️ FILTER SUPPRESSIONS (CAPITAL PRESERVATION)\n• None qualified\n",
        )
        self.assertEqual(
            format_momentum_section([]),
            "🚀 INTRADAY MOMENTUM & BOOM WATCH (HIGH VELOCITY + NEWS)\n• None qualified\n",
        )

    def test_suppressions_are_grouped_by_reason(self) -> None:
        text = format_suppressions_section(
            [
                Suppression(ticker="AAA", reason="ATR unavailable"),
                Suppression(ticker="BBB", reason="ATR unavailable"),
                Suppression(ticker="CCC", reason="Earnings within 3d"),
            ]
        )
        self.assertIn("• ATR unavailable: AAA, BBB", text)
        self.assertIn("• Earnings within 3d: CCC", text)

    def test_suppression_reason_keeps_raw_comparison_operators(self) -> None:
        text = format_suppressions_section(
            [Suppression(ticker="AAA", reason="Nearest option expiry < 14 DTE")]
        )
        self.assertIn("• Nearest option expiry < 14 DTE: AAA", text)
        self.assertNotIn("&lt;", text)

    def test_long_suppression_groups_are_truncated_with_hidden_count(self) -> None:
        suppressions = [
            Suppression(ticker=f"T{i:03d}.NS", reason="ATR unavailable") for i in range(135)
        ]
        text = format_suppressions_section(suppressions)
        line = text.splitlines()[1]

        self.assertIn("T000.NS", line)
        self.assertIn("T009.NS", line)
        self.assertNotIn("T010.NS", line)
        self.assertTrue(line.endswith("... (+125 more)"))

    def test_momentum_entries_are_separated_by_blank_line(self) -> None:
        text = format_momentum_section(
            [_momentum("AAA", "First headline"), _momentum("BBB", "Second headline")]
        )
        blocks = text.split("\n\n")

        self.assertEqual(len(blocks), 3)
        self.assertIn("INTRADAY MOMENTUM", blocks[0])
        self.assertIn("AAA", blocks[1])
        self.assertIn("BBB", blocks[2])

    def test_setup_and_turbo_sections_use_card_layout(self) -> None:
        bearish = DerivativeSetup(
            ticker="AAA",
            trade_type="BEAR",
            signal="Bearish Breakdown",
            close=123.45,
            structure="Bearish Breakdown",
            strategy="Standard Put / Turbo Bear",
            strike_low=118.0,
            strike_high=120.0,
            delta_target="-0.45 to -0.60",
            atr_percent=3.4,
            vol_rank=62.0,
            implied_move_pct=5.2,
            expected_move_abs=6.4,
            expected_move_pct=5.2,
            hv30=40.0,
            catalyst_summary="News: guidance cut",
            trend_score=-38.0,
            news_score=-12.0,
            high_momentum=False,
            dte=21,
        )
        turbo = KORisk(
            ticker="BBB",
            trade_type="BULL",
            spot_price=98.76,
            ko_strike=91.23,
            buffer_percent=7.6,
            atr_buffer_ratio=2.1,
            risk_level="SAFE",
            recommended_leverage=3.2,
            leverage_warning=None,
            synthetic_stop=94.12,
        )

        bearish_text = format_bearish_section([bearish], region="us")
        turbo_text = format_turbo_section([turbo], region="all")

        self.assertIn("• AAA | $123.45", bearish_text)
        self.assertIn("Setup: BEAR (Bearish Breakdown)", bearish_text)
        self.assertIn("Target: $118.00 - $120.00 | Delta: -0.45 to -0.60", bearish_text)
        self.assertIn("ATR: 3.4% | Vol Rank: Elevated IV | News: guidance cut", bearish_text)
        self.assertIn("• BBB | BULL TURBO", turbo_text)
        self.assertIn("Spot: $98.76 | KO: $91.23", turbo_text)
        self.assertIn("Buffer: 7.6% | ATR Multiplier: 2.1x 🟢", turbo_text)

    def test_report_footer_is_divided_from_scanner_data(self) -> None:
        report = format_radar_report(
            mode="manual",
            region="eu",
            bearish_setups=[],
            bullish_setups=[],
            momentum_setups=[],
            turbo_rows=[],
            suppressions=[Suppression(ticker="AAA", reason="ATR unavailable")],
        )

        self.assertIn("• ATR unavailable: AAA\n\n--------------------\nEXECUTION RULES:", report)
        self.assertFalse(report.startswith("\n"))
        self.assertFalse(report.startswith("• None qualified"))


if __name__ == "__main__":
    unittest.main()
