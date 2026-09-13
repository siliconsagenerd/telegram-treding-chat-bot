from __future__ import annotations

import atexit
import fcntl
import asyncio
import os
import re
import sys
import tempfile
import traceback
from time import perf_counter
from pathlib import Path

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from derivatives_scanner.core.cache import get_latest_suppressions, scanner_cache
from derivatives_scanner.config.settings import get_settings
from derivatives_scanner.main import run_scanner
from derivatives_scanner.notifications.formatter import (
    format_bearish_section,
    format_bullish_section,
    format_momentum_section,
    format_bullish_breakouts_section,
    format_bearish_breakouts_section,
    format_suppressions_section,
    format_turbo_section,
)

LOCK_FILE = Path(tempfile.gettempdir()) / "vp_deriv_scanner_bot_listener.lock"
SCAN_CACHE_TTL_SECONDS = 300
SCAN_LOADING_TEXT = "Scanning regional markets..."
SCAN_REGION_PATTERN = re.compile(r"REGION:\s*([A-Z]+)")
SCAN_SECTION_PATTERNS = (
    ("momentum", re.compile(r"BREAKOUTS", re.IGNORECASE)),
    ("bearish", re.compile(r"BEARISH SETUPS", re.IGNORECASE)),
    ("bullish", re.compile(r"BULLISH SETUPS", re.IGNORECASE)),
    ("turbos", re.compile(r"TURBO BARRIER", re.IGNORECASE)),
    ("suppressions", re.compile(r"FILTER SUPPRESSIONS", re.IGNORECASE)),
)

SCAN_CACHE: dict[str, tuple[float, object]] = {}
VIEW_REGION_KEY = "scanner_view_region"
VIEW_SECTION_KEY = "scanner_view_section"
VIEW_PREVIOUS_SECTION_KEY = "scanner_prev_section"
LATENCY_WARN_SECONDS = 8.0

_lock_fd: int | None = None

def _acquire_process_lock() -> None:
    global _lock_fd

    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise RuntimeError(
            "Bot listener is already running (lock held by another process)."
        ) from None

    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, str(os.getpid()).encode("utf-8"))
    os.fsync(fd)

    _lock_fd = fd
    atexit.register(_release_process_lock)


def _release_process_lock() -> None:
    global _lock_fd

    fd = _lock_fd
    if fd is None:
        return
    _lock_fd = None

    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🇺🇸 US Market", callback_data="scan_us"),
                InlineKeyboardButton("🇮🇳 India NSE", callback_data="scan_india"),
                InlineKeyboardButton("🇪🇺 Europe", callback_data="scan_eu"),
            ],
            [
                InlineKeyboardButton("🔥 Bearish", callback_data="bearish"),
                InlineKeyboardButton("🚀 Bullish", callback_data="bullish"),
                InlineKeyboardButton("⚡ Turbos", callback_data="turbos"),
            ],
            [
                InlineKeyboardButton("⚠️ Suppressions", callback_data="suppressions"),
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
            ],
        ]
    )


def _normalize_region(region: str | None) -> str:
    normalized = (region or "all").strip().lower()
    if normalized in {"india", "in"}:
        return "india"
    if normalized in {"europe", "eu"}:
        return "eu"
    if normalized == "us":
        return "us"
    return "all"


def _cache_key(region: str) -> str:
    return _normalize_region(region)


def _get_cached_scan(region: str) -> object | None:
    cached = SCAN_CACHE.get(_cache_key(region))
    if cached is None:
        return None
    timestamp, result = cached
    if (asyncio.get_event_loop().time() - timestamp) > SCAN_CACHE_TTL_SECONDS:
        SCAN_CACHE.pop(_cache_key(region), None)
        return None
    return result


def _store_cached_scan(region: str, result: object) -> None:
    SCAN_CACHE[_cache_key(region)] = (asyncio.get_event_loop().time(), result)
    scanner_cache["suppressions"] = list(getattr(result, "suppressions", []) or [])


def _infer_region_from_text(text: str | None) -> str:
    if not text:
        return "all"
    match = SCAN_REGION_PATTERN.search(text)
    if not match:
        return "all"
    return _normalize_region(match.group(1))


def _infer_section_from_text(text: str | None) -> str:
    if not text:
        return "scan"
    for section, pattern in SCAN_SECTION_PATTERNS:
        if pattern.search(text):
            return section
    return "scan"


def _remember_view(context: ContextTypes.DEFAULT_TYPE | None, region: str, section: str) -> None:
    if context is None:
        return

    chat_data = getattr(context, "chat_data", None)
    if chat_data is None:
        return

    chat_data[VIEW_REGION_KEY] = _normalize_region(region)
    chat_data[VIEW_SECTION_KEY] = section


def _remember_previous_section(context: ContextTypes.DEFAULT_TYPE | None, section: str) -> None:
    if context is None:
        return

    chat_data = getattr(context, "chat_data", None)
    if chat_data is None:
        return

    chat_data[VIEW_PREVIOUS_SECTION_KEY] = section


def _pop_previous_section(context: ContextTypes.DEFAULT_TYPE | None) -> str:
    chat_data = getattr(context, "chat_data", None)
    if chat_data is None:
        return "scan"
    return str(chat_data.pop(VIEW_PREVIOUS_SECTION_KEY, "scan") or "scan")


def _resolve_view_state(
    context: ContextTypes.DEFAULT_TYPE | None,
    message_text: str | None,
) -> tuple[str, str]:
    chat_data = getattr(context, "chat_data", None)
    if chat_data is not None:
        stored_region = chat_data.get(VIEW_REGION_KEY)
        stored_section = chat_data.get(VIEW_SECTION_KEY)
        if stored_region is not None or stored_section is not None:
            return _normalize_region(stored_region), str(stored_section or "scan")

    return _infer_region_from_text(message_text), _infer_section_from_text(message_text)


def _render_from_result(result, command: str) -> str:
    if command == "momentum":
        return format_momentum_section(result.momentum)
    if command == "bull_breakout":
        return format_bullish_breakouts_section(result.momentum)
    if command == "bear_breakout":
        return format_bearish_breakouts_section(result.momentum)
    if command == "bearish":
        return format_bearish_section(result.bearish)
    if command == "bullish":
        return format_bullish_section(result.bullish)
    if command == "turbos":
        return format_turbo_section(result.turbo, region="all")
    if command == "suppressions":
        return format_suppressions_section(result.suppressions)
    return result.report


async def _send_with_retry(coro_factory, attempts: int = 4):
    delay = 1.0
    for attempt in range(attempts):
        try:
            return await coro_factory()
        except RetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.5)
        except (NetworkError, TimedOut):
            if attempt >= attempts - 1:
                raise
            await asyncio.sleep(delay)
            delay *= 2
    return None


def _sanitize_text(text: str) -> str:
    clean_text = re.sub(r"\[Bot Listener PID: \d+\]", "", text).strip()
    if clean_text.startswith("```") and clean_text.endswith("```"):
        clean_text = clean_text[3:-3].strip()
    return clean_text[:3900]


async def _reply(
    update: Update,
    text: str,
    with_menu: bool = False,
    reply_markup: InlineKeyboardMarkup | None = None,
):
    if update.effective_message is None:
        return

    clean_text = _sanitize_text(text)
    markup = reply_markup if reply_markup is not None else (_keyboard() if with_menu else None)

    await _send_with_retry(
        lambda: update.effective_message.reply_text(
            text=clean_text,
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    )


async def _edit_or_reply(
    update: Update,
    text: str,
    with_menu: bool = False,
    reply_markup: InlineKeyboardMarkup | None = None,
):
    if update.callback_query and update.callback_query.message is not None:
        clean_text = _sanitize_text(text)
        markup = reply_markup if reply_markup is not None else (_keyboard() if with_menu else None)

        try:
            return await _send_with_retry(
                lambda: update.callback_query.message.edit_text(
                    text=clean_text,
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
            )
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return None
            return await _reply(update, clean_text, reply_markup=markup)
    return await _reply(update, text, with_menu=with_menu, reply_markup=reply_markup)


async def _respond(
    update: Update,
    command: str,
    region: str = "all",
    context: ContextTypes.DEFAULT_TYPE | None = None,
) -> None:
    region = _normalize_region(region)
    _remember_view(context, region, command)

    cached = _get_cached_scan(region)
    if cached is not None:
        await _edit_or_reply(update, _render_from_result(cached, command), with_menu=True)
        return

    await _edit_or_reply(update, f"\u23f3 {SCAN_LOADING_TEXT}", with_menu=True)

    try:
        settings = get_settings()
        started = perf_counter()
        result, _, emitted = await asyncio.to_thread(
            run_scanner, "manual", settings, False, region
        )
        elapsed = perf_counter() - started
        if elapsed >= LATENCY_WARN_SECONDS:
            print(
                f"[bot_listener] scan latency region={region} command={command} took {elapsed:.2f}s",
                file=sys.stderr,
            )
    except Exception as exc:
        traceback.print_exc()
        await _edit_or_reply(
            update,
            f"\u274c Scanner failed ({region.upper()}): {type(exc).__name__}: {exc}",
            with_menu=True,
        )
        return

    if emitted:
        _store_cached_scan(region, result)

    try:
        final_text = _render_from_result(result, command)
    except Exception as exc:
        traceback.print_exc()
        await _edit_or_reply(
            update,
            f"\u274c Formatting failed: {type(exc).__name__}: {exc}",
            with_menu=True,
        )
        return

    await _edit_or_reply(update, final_text, with_menu=True)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    _remember_view(context, "all", "scan")
    await _reply(
        update,
        "Derivative Radar initialized. Choose a region or a scan from the menu below.",
        with_menu=True,
    )


async def handle_breakout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    region, _ = _resolve_view_state(context, update.effective_message.text if update.effective_message else None)
    await _respond(update, "momentum", region=region, context=context)


async def handle_bull_breakout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    region, _ = _resolve_view_state(context, update.effective_message.text if update.effective_message else None)
    await _respond(update, "bull_breakout", region=region, context=context)


async def handle_bear_breakout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    region, _ = _resolve_view_state(context, update.effective_message.text if update.effective_message else None)
    await _respond(update, "bear_breakout", region=region, context=context)


async def handle_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    region, _ = _resolve_view_state(context, update.effective_message.text if update.effective_message else None)
    await _respond(update, "scan", region=region, context=context)


async def handle_scan_us(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    await _respond(update, "scan", region="us", context=context)


async def handle_scan_india(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    await _respond(update, "scan", region="india", context=context)


async def handle_scan_eu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    await _respond(update, "scan", region="eu", context=context)


async def handle_us(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    await handle_scan_us(update, context)


async def handle_india(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    await handle_scan_india(update, context)


async def handle_eu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    await handle_scan_eu(update, context)


async def handle_bearish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    region, _ = _resolve_view_state(context, update.effective_message.text if update.effective_message else None)
    await _respond(update, "bearish", region=region, context=context)


async def handle_bullish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    region, _ = _resolve_view_state(context, update.effective_message.text if update.effective_message else None)
    await _respond(update, "bullish", region=region, context=context)


async def handle_turbos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    region, _ = _resolve_view_state(context, update.effective_message.text if update.effective_message else None)
    await _respond(update, "turbos", region=region, context=context)


async def handle_suppressions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    region, _ = _resolve_view_state(context, update.effective_message.text if update.effective_message else None)
    await _respond(update, "suppressions", region=region, context=context)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    query = update.callback_query
    if query is None:
        return

    try:
        await query.answer()
    except Exception:
        pass

    raw = (update.callback_query.data or "").strip().lower()
    message_text = update.callback_query.message.text if update.callback_query.message else None
    region, section = _resolve_view_state(context, message_text)

    if raw == "scan_us":
        region = "us"
        section = "scan"
    elif raw == "scan_india":
        region = "india"
        section = "scan"
    elif raw == "scan_eu":
        region = "eu"
        section = "scan"
    elif raw in {"bearish", "bullish", "turbos", "suppressions"}:
        section = raw
    elif raw == "back_to_scan":
        await _respond(update, _pop_previous_section(context), region=region, context=context)
        return
    elif raw == "refresh":
        SCAN_CACHE.pop(_cache_key(region), None)
        await _respond(update, section, region=region, context=context)
        return
    else:
        section = "scan"

    await _respond(update, section, region=region, context=context)


async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ = context
    if update.effective_message is None or update.effective_message.text is None:
        return

    text = update.effective_message.text.strip()
    cmd_map = {
        "🇺🇸 US Market": handle_us,
        "🇮🇳 India NSE": handle_india,
        "🇪🇺 Europe": handle_eu,
        "🔥 Bearish": handle_bearish,
        "🚀 Bullish": handle_bullish,
        "⚡ Turbos": handle_turbos,
        "⚠️ Suppressions": handle_suppressions,
    }
    if text in cmd_map:
        await cmd_map[text](update, context)
        return

    if not text.startswith("/"):
        await _reply(
            update,
            "Unknown command. Use /start, /breakout, /bull_breakout, /bear_breakout, /us, /india, /eu, /bearish, /bullish, /turbos, /suppressions.",
            with_menu=True,
        )


async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "Open interactive navigation menu"),
        BotCommand("breakout", "Scan intraday high-velocity breakouts"),
        BotCommand("bull_breakout", "Show bullish breakouts (Stoploss, LTP, Target)"),
        BotCommand("bear_breakout", "Show bearish breakouts (Stoploss, LTP, Target)"),
        BotCommand("us", "Scan US High-Beta & Growth (Options)"),
        BotCommand("india", "Scan Indian NSE F&O Setups"),
        BotCommand("eu", "Scan EU Turbos & Warrants"),
        BotCommand("bearish", "Show top bearish setups"),
        BotCommand("bullish", "Show top bullish setups"),
        BotCommand("turbos", "KO barrier safety monitor"),
        BotCommand("suppressions", "View rejected tickers & reasons"),
    ]
    await application.bot.set_my_commands(commands)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    print(f"[bot_listener] handler error: {type(err).__name__}: {err}", file=sys.stderr)
    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await _send_with_retry(
                lambda: update.effective_message.reply_text(
                    f"⚠️ Temporary error: {type(err).__name__}: {str(err)[:200]}\nPlease try again."
                )
            )
        except Exception:
            pass


def build_application(token: str) -> Application:
    app = Application.builder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("breakout", handle_breakout))
    app.add_handler(CommandHandler("bull_breakout", handle_bull_breakout))
    app.add_handler(CommandHandler("bear_breakout", handle_bear_breakout))
    app.add_handler(CommandHandler("us", handle_scan_us))
    app.add_handler(CommandHandler("india", handle_scan_india))
    app.add_handler(CommandHandler("eu", handle_scan_eu))
    app.add_handler(CommandHandler("bearish", handle_bearish))
    app.add_handler(CommandHandler("bullish", handle_bullish))
    app.add_handler(CommandHandler("turbos", handle_turbos))
    app.add_handler(CommandHandler("suppressions", handle_suppressions))
    app.add_handler(CallbackQueryHandler(handle_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown_command))
    app.add_error_handler(_on_error)

    return app


def main() -> None:
    _acquire_process_lock()

    settings = get_settings()
    if not settings.telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start bot listener")

    app = build_application(settings.telegram_token)
    app.run_polling(drop_pending_updates=False, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()