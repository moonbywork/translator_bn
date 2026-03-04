import os
import asyncio
import logging
import random
import string
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import RetryAfter, TimedOut, NetworkError, TelegramError

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEST_CHAT_ID = int(os.getenv("DEST_CHAT_ID", "0"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise RuntimeError("❌ Missing BOT_TOKEN")
if not RENDER_EXTERNAL_URL:
    raise RuntimeError("❌ Missing RENDER_EXTERNAL_URL")

# ----------------------
# Settings
# ----------------------
LABEL = "Translator:"
TZ_MY = ZoneInfo("Asia/Kuala_Lumpur")  # Malaysia
TZ_BD = ZoneInfo("Asia/Dhaka")         # Bangladesh
TZ_RU = ZoneInfo("Europe/Moscow")      # Russia (Moscow time)
LOG_FILE = os.getenv("LOG_FILE", "log.txt")

# If you truly want NO caption in group at all, set SEND_CAPTION=0 in env.
SEND_CAPTION = os.getenv("SEND_CAPTION", "1").strip() not in {"0", "false", "False", "no", "NO"}

# Nickname mapping (EXACT match, no dot/space removal)
# Key must match Telegram full_name exactly as the bot sees it.
NICKNAME_MAP = {
    "Uttarayan Sengupta": "Ryan",
    "Sumiparna Roy": "Sumi",
    "Md. Shafaytul Islam Shanto": "Shafaytul",
    "Suman G.": "Suman",
    "Ezaz Ahmed": "Ezaz",
    "Adeeb": "Adeeb",
    "Samael": "Samael",
    "Nuva": "Ananna",
    "Monira": "Monira",
    "Lamia Jahan": "Lamia",
}

# Optional (BEST): map user_id -> nickname, survives Telegram name changes.
# Fill later if you want.
USER_ID_NICKNAME_MAP = {
    # 123456789: "Ryan",
}


# ----------------------
# Logging (to console + log.txt)
# ----------------------
logger = logging.getLogger("vo_bot")
logger.setLevel(logging.INFO)

_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

# Console
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
logger.addHandler(_sh)

# File
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setFormatter(_fmt)
logger.addHandler(_fh)


def _t_str(tz: ZoneInfo) -> str:
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")


def multi_time_str() -> str:
    """
    Returns: 'MYT=... | BDT=... | MSK=...'
    """
    return f"MYT={_t_str(TZ_MY)} | BDT={_t_str(TZ_BD)} | MSK={_t_str(TZ_RU)}"


def make_ref(prefix: str = "TX") -> str:
    ts = datetime.now(TZ_MY).strftime("%Y%m%d-%H%M%S")
    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{prefix}-{ts}-{rand}"


def movie_from_filename(filename: str) -> str:
    # "full movie name" = filename without extension (no trimming)
    return filename.rsplit(".", 1)[0]


def translator_display_name(msg) -> str:
    """
    Uses:
    1) user_id mapping (if exists)
    2) exact full_name mapping
    3) Telegram full_name
    4) @username
    """
    u = msg.from_user
    if u:
        if u.id in USER_ID_NICKNAME_MAP:
            return USER_ID_NICKNAME_MAP[u.id]
        if u.full_name and u.full_name in NICKNAME_MAP:
            return NICKNAME_MAP[u.full_name]
        if u.full_name:
            return u.full_name
        if u.username:
            return f"@{u.username}"
    return "Unknown"


async def send_with_retry(send_coro_factory, max_attempts: int = 4):
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await send_coro_factory()
        except RetryAfter as e:
            last_err = e
            wait_s = int(getattr(e, "retry_after", 2)) + 1
            logger.warning("RetryAfter: wait %ss (attempt %s/%s)", wait_s, attempt, max_attempts)
            await asyncio.sleep(wait_s)
        except (TimedOut, NetworkError) as e:
            last_err = e
            wait_s = 2 * attempt
            logger.warning("Network/Timeout: wait %ss (attempt %s/%s): %s", wait_s, attempt, max_attempts, e)
            await asyncio.sleep(wait_s)
        except TelegramError as e:
            last_err = e
            logger.error("TelegramError (no retry): %s", e)
            raise
    raise last_err if last_err else RuntimeError("Unknown send failure")


def log_event(event: str, **fields):
    """
    Write one structured line into log.txt (and console).
    Includes 3 timezones.
    """
    t = multi_time_str()
    parts = [f"{t}", event]
    for k, v in fields.items():
        parts.append(f'{k}="{v}"')
    logger.info(" | ".join(parts))


# ----------------------
# Commands
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send your .srt file here (DM only).\n"
        "No caption needed.\n\n"
        "Group caption will be:\n"
        f"{LABEL} <Nickname>\n\n"
        "Bot will reply RECEIVED / FORWARDED with 3 timezones.\n"
        "Log saved in log.txt inside the bot folder."
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"✅ Alive\n{multi_time_str()}")


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u:
        return
    await update.message.reply_text(
        "Your Telegram info (what bot sees):\n"
        f"user_id: {u.id}\n"
        f"full_name: {u.full_name}\n"
        f"username: @{u.username}" if u.username else f"user_id: {u.id}\nfull_name: {u.full_name}\nusername: (none)"
    )


async def lastlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /lastlog [N] - send last N lines of log.txt (DM only)
    """
    msg = update.message
    if msg.chat.type != "private":
        return

    try:
        n = int(context.args[0]) if context.args else 30
        n = max(5, min(n, 120))
    except Exception:
        n = 30

    try:
        path = LOG_FILE
        if not os.path.exists(path):
            await msg.reply_text("log.txt not found yet.")
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-n:]
        text = "".join(lines)
        # Telegram message limit safety
        if len(text) > 3500:
            text = text[-3500:]
        await msg.reply_text("Last log lines:\n\n" + text)
    except Exception as e:
        await msg.reply_text(f"Failed reading log.txt: {e}")


async def sendlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /sendlog - send log.txt as a file (DM only)
    """
    msg = update.message
    if msg.chat.type != "private":
        return
    if not os.path.exists(LOG_FILE):
        await msg.reply_text("log.txt not found yet.")
        return
    try:
        await context.bot.send_document(chat_id=msg.chat_id, document=open(LOG_FILE, "rb"))
    except Exception as e:
        await msg.reply_text(f"Failed sending log.txt: {e}")


async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(
        f"chat_id: {chat.id}\n"
        f"type: {chat.type}\n"
        f"title: {chat.title}"
    )


# ----------------------
# Handlers
# ----------------------
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    # Must be DM
    if msg.chat.type != "private":
        try:
            await msg.reply_text("⚠️ Please send your .srt in DM (private chat) with this bot.")
        except Exception:
            pass
        return

    if DEST_CHAT_ID == 0:
        await msg.reply_text("⚠️ Destination group not configured yet (DEST_CHAT_ID).")
        return

    doc = msg.document
    if not doc or not doc.file_name:
        await msg.reply_text("⚠️ Please send the .srt as a FILE (Document), not as text.")
        return

    if not doc.file_name.lower().endswith(".srt"):
        await msg.reply_text("⚠️ Only .srt files are accepted.")
        return

    translator = translator_display_name(msg)
    movie = movie_from_filename(doc.file_name)
    # ✅ Ref = full movie name
    ref = movie

    t_str = multi_time_str()

    log_event(
        "RECEIVED_SRT",
        ref=ref,
        translator=translator,
        user_id=(msg.from_user.id if msg.from_user else ""),
        file_name=doc.file_name,
        file_size=(doc.file_size or ""),
        msg_id=msg.message_id,
    )

    # Receipt to translator (counter proof)
    await msg.reply_text(
        "📥 RECEIVED\n"
        f"Ref(Movie): {ref}\n"
        f"{t_str}\n"
        "Forwarding now..."
    )

    # ✅ Caption in group: ONLY Translator name (no time, no ref)
    caption = f"{LABEL} {translator}" if SEND_CAPTION else None

    try:
        async def _send():
            return await context.bot.send_document(
                chat_id=DEST_CHAT_ID,
                document=doc.file_id,
                caption=caption,
            )

        await send_with_retry(_send, max_attempts=4)

        log_event("FORWARDED_SRT", ref=ref, translator=translator, to_chat=DEST_CHAT_ID)
        await msg.reply_text(
            "✅ FORWARDED\n"
            f"Ref(Movie): {ref}\n"
            f"{t_str}"
        )

    except Exception as e:
        log_event("FAILED_FORWARD_SRT", ref=ref, translator=translator, error=str(e))
        await msg.reply_text(
            "❌ FAILED to forward\n"
            f"Ref(Movie): {ref}\n"
            f"{t_str}\n"
            f"Error: {e}"
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.chat.type != "private":
        return

    if DEST_CHAT_ID == 0:
        return

    text = (msg.text or "").strip()
    if not text:
        return

    translator = translator_display_name(msg)
    ref = make_ref("MSG")
    t_str = multi_time_str()

    log_event(
        "RECEIVED_TEXT",
        ref=ref,
        translator=translator,
        user_id=(msg.from_user.id if msg.from_user else ""),
        msg_id=msg.message_id,
    )

    out = f"{text}\n\n{LABEL} {translator}"

    try:
        async def _send():
            return await context.bot.send_message(chat_id=DEST_CHAT_ID, text=out)

        await send_with_retry(_send, max_attempts=4)

        log_event("FORWARDED_TEXT", ref=ref, translator=translator, to_chat=DEST_CHAT_ID)
        await msg.reply_text(f"✅ SENT\nRef: {ref}\n{t_str}")
    except Exception as e:
        log_event("FAILED_TEXT_FORWARD", ref=ref, translator=translator, error=str(e))
        await msg.reply_text(f"❌ FAILED\nRef: {ref}\n{t_str}\nError: {e}")


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("lastlog", lastlog))
    app.add_handler(CommandHandler("sendlog", sendlog))
    app.add_handler(CommandHandler("id", get_id))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app


# ----------------------
# Main (Webhook for Render)
# ----------------------
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", "10000"))

    WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
    WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

    application = build_app()

    print("🚀 Bot starting with webhook:")
    print("Webhook URL:", WEBHOOK_URL)
    print("Logging to:", LOG_FILE)

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH.strip("/"),
        webhook_url=WEBHOOK_URL,
    )
