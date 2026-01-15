import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEST_CHAT_ID = int(os.getenv("DEST_CHAT_ID", "0"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise RuntimeError("❌ Missing BOT_TOKEN")
if not RENDER_EXTERNAL_URL:
    raise RuntimeError("❌ Missing RENDER_EXTERNAL_URL")


# ----------------------
# Commands
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send your .srt file here (DM only).\n"
        "No caption needed.\n\n"
        "Format sent to group:\n"
        "MovieName\n"
        "Your Name"
    )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(
        f"chat_id: {chat.id}\n"
        f"type: {chat.type}\n"
        f"title: {chat.title}"
    )


# ----------------------
# Helpers
# ----------------------
def sender_name(msg) -> str:
    u = msg.from_user
    if u and u.full_name:
        return u.full_name
    if u and u.username:
        return f"@{u.username}"
    return "Unknown"


def movie_name_from_filename(filename: str) -> str:
    # Remove extension only
    return filename.rsplit(".", 1)[0]


# ----------------------
# Handlers
# ----------------------
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    # DM only
    if msg.chat.type != "private":
        return

    if DEST_CHAT_ID == 0:
        await msg.reply_text("⚠️ Destination group not configured yet.")
        return

    doc = msg.document
    if not doc or not doc.file_name:
        return

    # Enforce .srt only
    if not doc.file_name.lower().endswith(".srt"):
        return

    movie_name = movie_name_from_filename(doc.file_name)
    sender = sender_name(msg)

    # ✅ EXACT FORMAT (2 lines ONLY)
    caption = f"{movie_name}\n{sender}"

    try:
        await context.bot.send_document(
            chat_id=DEST_CHAT_ID,
            document=doc.file_id,
            caption=caption,
        )
        await msg.reply_text("✅ Submitted.")
    except Exception as e:
        await msg.reply_text(f"❌ Failed to submit.\n{e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    if msg.chat.type != "private":
        return

    if DEST_CHAT_ID == 0:
        return

    text = (msg.text or "").strip()
    if not text:
        return

    sender = sender_name(msg)

    # Text forwarded with sender only
    out = f"{text}\n{sender}"

    try:
        await context.bot.send_message(
            chat_id=DEST_CHAT_ID,
            text=out
        )
        await msg.reply_text("✅ Message sent.")
    except Exception:
        pass


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
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

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH.strip("/"),
        webhook_url=WEBHOOK_URL,
    )
