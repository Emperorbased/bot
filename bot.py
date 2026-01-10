import logging
import os
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8546823235:AAFI-3t1SCB9S4PI5izbAAz1XEwHjRlL-6E"

# Flask для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot running!"

@app.route('/health')
def health():
    return "OK"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отвечаем на все сообщения"""
    await update.message.reply_text("🚫 Бот временно закрыт")

def main():
    # Запуск Flask
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    application = Application.builder().token(TOKEN).build()
    
    # Обработчик всех сообщений и команд
    application.add_handler(MessageHandler(filters.ALL, handle_all))
    application.add_handler(CommandHandler("start", handle_all))
    
    logger.info("🚫 Бот закрыт")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
