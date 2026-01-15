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

# ======================
# LOAD ENV
# ======================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEST_CHAT_ID = int(os.getenv("DEST_CHAT_ID", "0"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise RuntimeError("❌ Missing BOT_TOKEN")
if not RENDER_EXTERNAL_URL:
    raise RuntimeError("❌ Missing RENDER_EXTERNAL_URL")

# ======================
# COMMANDS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📤 Anonymous Subtitle Submission Bot\n\n"
        "Send your .srt file here (DM only).\n"
        "Your name will NOT be shown.\n"
    )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(
        f"chat_id: {chat.id}\n"
        f"type: {chat.type}\n"
        f"title: {chat.title}"
    )

# ======================
# DOCUMENT HANDLER
# ======================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    # DM only (for anonymity)
    if msg.chat.type != "private":
        await msg.reply_text("❌ Please DM me the file for anonymous submission.")
        return

    doc = msg.document
    if not doc or not doc.file_name:
        await msg.reply_text("❌ Invalid file.")
        return

    if not doc.file_name.lower().endswith(".srt"):
        await msg.reply_text("❌ Only .srt files are allowed.")
        return

    if DEST_CHAT_ID == 0:
        await msg.reply_text("⚠️ Destination group not configured yet.")
        return

    caption = (
        "📥 New Subtitle Submission\n"
        f"🗂 File: {doc.file_name}\n"
        "👤 Sender: Anonymous"
    )

    try:
        await context.bot.send_document(
            chat_id=DEST_CHAT_ID,
            document=doc.file_id,
            caption=caption,
        )
        await msg.reply_text("✅ Submitted successfully (anonymous).")
    except Exception as e:
        await msg.reply_text(f"❌ Failed to submit.\n{e}")

# ======================
# APP BUILDER
# ======================
def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    return app

# ======================
# MAIN (WEBHOOK FOR RENDER)
# ======================
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
