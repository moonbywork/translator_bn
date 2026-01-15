import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEST_CHAT_ID = int(os.getenv("DEST_CHAT_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN")
if not DEST_CHAT_ID:
    raise RuntimeError("Missing DEST_CHAT_ID")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send .srt here (DM). I will submit anonymously.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message

    # keep anonymous: only accept via DM
    if msg.chat.type != "private":
        await msg.reply_text("Please DM me the file for anonymous submission.")
        return

    doc = msg.document
    filename = (doc.file_name or "").lower()
    if not filename.endswith(".srt"):
        await msg.reply_text("Please send a .srt file only.")
        return

    caption = f"📥 New SRT Submission\n🗂 File: {doc.file_name}\n👤 Sender: Anonymous"
    await context.bot.send_document(chat_id=DEST_CHAT_ID, document=doc.file_id, caption=caption)
    await msg.reply_text("✅ Submitted (anonymous).")

def build_app() -> Application:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    return application

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", "10000"))  # Render sets PORT
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")  # we will set this in Render env
    if not RENDER_EXTERNAL_URL:
        raise RuntimeError("Missing RENDER_EXTERNAL_URL env var")

    WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
    WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

    app = build_app()
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH.strip("/"),
        webhook_url=WEBHOOK_URL,
    )
