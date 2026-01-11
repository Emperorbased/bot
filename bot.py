import logging
import time
import os
from datetime import datetime
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8546823235:AAFI-3t1SCB9S4PI5izbAAz1XEwHjRlL-6E"
SUPER_ADMINS = {7355737254, 8243127223, 8167127645}
admins = SUPER_ADMINS.copy()

WAITING_APPEAL, WAITING_COMPLAINT, WAITING_ADMIN_ID, WAITING_RESPONSE, WAITING_BAN_DURATION, WAITING_BAN_REASON, WAITING_BROADCAST = range(7)

appeals = {}
appeal_counter = 0
banned_users = {}
active_chats = {}
all_users = set()

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

def is_user_banned(user_id):
    if user_id in banned_users:
        if time.time() < banned_users[user_id]['until']:
            return True, banned_users[user_id]['reason'], banned_users[user_id]['until']
        else:
            del banned_users[user_id]
    return False, None, None

def parse_duration(duration_str):
    duration_str = duration_str.strip().lower()
    if duration_str[-1] == 'm':
        return int(duration_str[:-1]) * 60, f"{duration_str[:-1]} мин"
    elif duration_str[-1] == 'h':
        return int(duration_str[:-1]) * 3600, f"{duration_str[:-1]} ч"
    elif duration_str[-1] == 'd':
        return int(duration_str[:-1]) * 86400, f"{duration_str[:-1]} д"
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    all_users.add(user_id)
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(f"🚫 Бан до {ban_end}\n\nПричина: {reason}")
        return
    keyboard = [
        [InlineKeyboardButton("Обжаловать наказание", callback_data="appeal")],
        [InlineKeyboardButton("Жалоба на персонал", callback_data="complaint")],
        [InlineKeyboardButton("💬 Чат с админом", callback_data="start_chat")]
    ]
    await update.message.reply_text("Привет! Здесь можно обжаловать наказание.\n\nВыберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))

async def gov(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END
    await update.message.reply_text(f"📢 Рассылка\n\nНапишите текст:\n(Всего: {len(all_users)})")
    return WAITING_BROADCAST

async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if update.message.from_user.id not in admins:
        return ConversationHandler.END
    await update.message.reply_text("📤 Отправка...")
    success = 0
    failed = 0
    for uid in all_users:
        try:
            await context.bot.send_message(uid, f"📢 Объявление:\n\n{text}")
            success += 1
        except:
            failed += 1
    await update.message.reply_text(f"✅ Отправлено: {success}\n❌ Ошибок: {failed}")
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "appeal":
        is_banned, reason, until = is_user_banned(user_id)
        if is_banned:
            ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
            await query.edit_message_text(f"🚫 Бан до {ban_end}\n\nПричина: {reason}")
            return ConversationHandler.END
        await query.edit_message_text("📝 Опишите какое наказание вам дали и почему его нужно обжаловать:")
        return WAITING_APPEAL
    
    elif query.data == "complaint":
        is_banned, reason, until = is_user_banned(user_id)
        if is_banned:
            ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
            await query.edit_message_text(f"🚫 Бан до {ban_end}\n\nПричина: {reason}")
            return ConversationHandler.END
        await query.edit_message_text("📝 Опишите вашу жалобу на персонал:")
        return WAITING_COMPLAINT
    
    elif query.data == "start_chat":
        if user_id in active_chats:
            await query.edit_message_text("💬 У вас уже есть активный чат")
            return
        keyboard = [[InlineKeyboardButton("Начать диалог", callback_data=f"accept_chat_{user_id}")]]
        for admin_id in admins:
            try:
                await context.bot.send_message(admin_id, f"💬 @{query.from_user.username or query.from_user.first_name} (ID: {user_id}) запросил чат", reply_markup=InlineKeyboardMarkup(keyboard))
            except:
                pass
        await query.edit_message_text("✅ Запрос отправлен")
        return
    
    elif query.data.startswith("accept_chat_"):
        chat_user_id = int(query.data.split("_")[2])
        if chat_user_id in active_chats:
            await query.answer("⚠️ Чат занят!", show_alert=True)
            return
        try:
            user_info = await context.bot.get_chat(chat_user_id)
            username = user_info.username or user_info.first_name
        except:
            username = "Unknown"
        active_chats[chat_user_id] = {'admin_id': user_id, 'username': username, 'admin_username': query.from_user.username or query.from_user.first_name}
        try:
            await context.bot.send_message(chat_user_id, f"💬 @{query.from_user.username or query.from_user.first_name} подключился!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Завершить", callback_data="end_chat_user")]]))
        except:
            pass
        await query.edit_message_text(f"✅ Чат с @{username}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Завершить", callback_data=f"end_chat_admin_{chat_user_id}")]]))
        return
    
    elif query.data == "end_chat_user":
        if user_id in active_chats:
            admin_id = active_chats[user_id]['admin_id']
            del active_chats[user_id]
            try:
                await context.bot.send_message(admin_id, "💬 Пользователь завершил чат")
            except:
                pass
            await query.edit_message_text("✅ Чат завершен")
        return
    
    elif query.data.startswith("end_chat_admin_"):
        chat_user_id = int(query.data.split("_")[3])
        if chat_user_id in active_chats:
            del active_chats[chat_user_id]
            try:
                await context.bot.send_message(chat_user_id, "💬 Админ завершил чат")
            except:
                pass
            await query.edit_message_text("✅ Чат завершен")
        return
    
    elif query.data.startswith("respond_"):
        appeal_id = int(query.data.split("_")[1])
        context.user_data['responding_to'] = appeal_id
        await query.edit_message_text(f"{query.message.text}\n\n✍️ Ответ:")
        return WAITING_RESPONSE
    
    elif query.data.startswith("ban_"):
        appeal_id = int(query.data.split("_")[1])
        if appeal_id in appeals:
            context.user_data['banning_appeal'] = appeal_id
            await query.edit_message_text(f"{query.message.text}\n\n⏱ Время (1m, 1h, 1d):")
            return WAITING_BAN_DURATION
    
    elif query.data.startswith("close_"):
        appeal_id = int(query.data.split("_")[1])
        if appeal_id in appeals:
            try:
                await context.bot.send_message(appeals[appeal_id]['user_id'], f"✅ Жалоба #{appeal_id} закрыта")
            except:
                pass
            del appeals[appeal_id]
            await query.edit_message_text(f"{query.message.text}\n\n🔒 Закрыта")
        return ConversationHandler.END

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_id = update.message.from_user.id
    text = update.message.text
    username = update.message.from_user.username or update.message.from_user.first_name
    all_users.add(user_id)
    if user_id in active_chats:
        try:
            await context.bot.send_message(active_chats[user_id]['admin_id'], f"💬 @{username}:\n\n{text}")
        except:
            pass
        return
    for chat_user_id, chat_info in list(active_chats.items()):
        if chat_info['admin_id'] == user_id:
            try:
                await context.bot.send_message(chat_user_id, f"💬 @{chat_info['admin_username']}:\n\n{text}")
            except:
                pass
            return

async def receive_appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global appeal_counter
    user_id = update.message.from_user.id
    all_users.add(user_id)
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(f"🚫 Бан до {ban_end}\n\nПричина: {reason}")
        return ConversationHandler.END
    appeal_counter += 1
    user = update.message.from_user
    appeals[appeal_counter] = {'user_id': user.id, 'username': user.username or user.first_name, 'text': update.message.text, 'type': 'appeal'}
    await update.message.reply_text(f"✅ Обжалование #{appeal_counter} отправлено!")
    keyboard = [[InlineKeyboardButton("Ответить", callback_data=f"respond_{appeal_counter}")], [InlineKeyboardButton("Бан", callback_data=f"ban_{appeal_counter}")], [InlineKeyboardButton("Закрыть", callback_data=f"close_{appeal_counter}")]]
    for admin_id in admins:
        try:
            await context.bot.send_message(admin_id, f"🔔 Обжалование #{appeal_counter}\n\n👤 @{user.username or user.first_name} (ID: {user.id})\n📝 {update.message.text}", reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            pass
    return ConversationHandler.END

async def receive_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global appeal_counter
    user_id = update.message.from_user.id
    all_users.add(user_id)
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(f"🚫 Бан до {ban_end}\n\nПричина: {reason}")
        return ConversationHandler.END
    appeal_counter += 1
    user = update.message.from_user
    appeals[appeal_counter] = {'user_id': user.id, 'username': user.username or user.first_name, 'text': update.message.text, 'type': 'complaint'}
    await update.message.reply_text(f"✅ Жалоба #{appeal_counter} отправлена!")
    keyboard = [[InlineKeyboardButton("Ответить", callback_data=f"respond_{appeal_counter}")], [InlineKeyboardButton("Бан", callback_data=f"ban_{appeal_counter}")], [InlineKeyboardButton("Закрыть", callback_data=f"close_{appeal_counter}")]]
    for admin_id in admins:
        try:
            await context.bot.send_message(admin_id, f"🔔 Жалоба #{appeal_counter}\n\n👤 @{user.username or user.first_name} (ID: {user.id})\n📝 {update.message.text}", reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            pass
    return ConversationHandler.END

async def receive_ban_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    duration_str = update.message.text
    appeal_id = context.user_data.get('banning_appeal')
    if not appeal_id or appeal_id not in appeals:
        await update.message.reply_text("❌ Ошибка")
        return ConversationHandler.END
    seconds, readable = parse_duration(duration_str)
    if seconds is None:
        await update.message.reply_text("❌ Формат: 1m, 1h, 1d")
        return WAITING_BAN_DURATION
    context.user_data['ban_duration'] = seconds
    context.user_data['ban_duration_readable'] = readable
    await update.message.reply_text(f"✅ {readable}\n\n📝 Причина:")
    return WAITING_BAN_REASON

async def receive_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    appeal_id = context.user_data.get('banning_appeal')
    duration = context.user_data.get('ban_duration')
    duration_readable = context.user_data.get('ban_duration_readable')
    if not appeal_id or appeal_id not in appeals:
        return ConversationHandler.END
    user_id = appeals[appeal_id]['user_id']
    username = appeals[appeal_id]['username']
    ban_until = time.time() + duration
    banned_users[user_id] = {'until': ban_until, 'reason': reason}
    ban_end = datetime.fromtimestamp(ban_until).strftime('%d.%m.%Y %H:%M')
    try:
        await context.bot.send_message(user_id, f"🚫 Бан на {duration_readable}\nДо: {ban_end}\n\nПричина: {reason}")
    except:
        pass
    await update.message.reply_text(f"✅ @{username} (ID: {user_id}) забанен на {duration_readable}")
    del appeals[appeal_id]
    return ConversationHandler.END

async def receive_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    appeal_id = context.user_data.get('responding_to')
    if appeal_id and appeal_id in appeals:
        try:
            await context.bot.send_message(appeals[appeal_id]['user_id'], f"💬 Ответ на жалобу #{appeal_id}:\n\n{update.message.text}")
            await update.message.reply_text("✅ Ответ отправлен!")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    context.user_data.pop('responding_to', None)
    return ConversationHandler.END

async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in SUPER_ADMINS:
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END
    await update.message.reply_text("👤 ID:")
    return WAITING_ADMIN_ID

async def receive_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_admin_id = int(update.message.text)
        if new_admin_id in admins:
            await update.message.reply_text("⚠️ Уже админ")
        else:
            admins.add(new_admin_id)
            await update.message.reply_text(f"✅ {new_admin_id} добавлен!")
            try:
                await context.bot.send_message(new_admin_id, "🎉 Вы админ!")
            except:
                pass
    except:
        await update.message.reply_text("❌ Неверный ID")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено")
    return ConversationHandler.END

def main():
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    application = Application.builder().token(TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages), group=-1)
    appeal_handler = ConversationHandler(entry_points=[CallbackQueryHandler(button_handler, pattern="^(appeal|complaint)$")], states={WAITING_APPEAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_appeal)], WAITING_COMPLAINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_complaint)]}, fallbacks=[CommandHandler("cancel", cancel)], per_message=False)
    response_handler = ConversationHandler(entry_points=[CallbackQueryHandler(button_handler, pattern="^respond_")], states={WAITING_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_response)]}, fallbacks=[CommandHandler("cancel", cancel)], per_message=False)
    ban_handler = ConversationHandler(entry_points=[CallbackQueryHandler(button_handler, pattern="^ban_")], states={WAITING_BAN_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_duration)], WAITING_BAN_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_reason)]}, fallbacks=[CommandHandler("cancel", cancel)], per_message=False)
    addadmin_handler = ConversationHandler(entry_points=[CommandHandler("addadmin", addadmin)], states={WAITING_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_id)]}, fallbacks=[CommandHandler("cancel", cancel)])
    broadcast_handler = ConversationHandler(entry_points=[CommandHandler("gov", gov)], states={WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast)]}, fallbacks=[CommandHandler("cancel", cancel)])
    application.add_handler(CommandHandler("start", start))
    application.add_handler(appeal_handler)
    application.add_handler(response_handler)
    application.add_handler(ban_handler)
    application.add_handler(addadmin_handler)
    application.add_handler(broadcast_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    logger.info("🚀 Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
