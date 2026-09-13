from __future__ import annotations

import unittest

from telegram.error import BadRequest

from derivatives_scanner.core import bot_listener
from derivatives_scanner.core.risk_engine import Suppression


class _DummyMessage:
    async def edit_text(self, **_kwargs):
        raise BadRequest("Message is not modified")


class _DummyCallbackQuery:
    def __init__(self) -> None:
        self.message = _DummyMessage()


class _DummyUpdate:
    def __init__(self) -> None:
        self.callback_query = _DummyCallbackQuery()
        self.effective_message = None


class BotListenerTest(unittest.IsolatedAsyncioTestCase):
    def test_format_earnings_watch_groups_reasons(self) -> None:
        payload = bot_listener._format_earnings_watch(
            [
                Suppression(ticker="AAA", reason="Earnings within 3d (Binary Event)"),
                Suppression(ticker="BBB", reason="Earnings within 3d (Binary Event)"),
                Suppression(ticker="CCC", reason="ATR unavailable"),
            ]
        )

        self.assertIn("📅 EARNINGS CALENDAR WATCH", payload)
        self.assertIn("• Earnings within 3d (Binary Event): AAA, BBB", payload)
        self.assertNotIn("ATR unavailable", payload)

    async def test_edit_or_reply_ignores_not_modified_bad_request(self) -> None:
        result = await bot_listener._edit_or_reply(_DummyUpdate(), "unchanged")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
