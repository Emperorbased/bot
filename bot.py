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
        await update.message.reply_text(f"🚫 Вы заблокированы в боте до {ban_end}\n\nПричина: {reason}")
        return
    
    keyboard = [
        [InlineKeyboardButton("Обжаловать наказание", callback_data="appeal")],
        [InlineKeyboardButton("Жалоба на персонал", callback_data="complaint")],
        [InlineKeyboardButton("💬 Чат с администратором", callback_data="start_chat")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Привет! Здесь можно обжаловать наказание.\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def gov(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"📢 Рассылка\n\n"
        f"Напишите текст для отправки:\n"
        f"(Всего пользователей: {len(all_users)})"
    )
    return WAITING_BROADCAST

async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    
    if user_id not in admins:
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END
    
    await update.message.reply_text("📤 Отправка...")
    
    success = 0
    failed = 0
    
    for uid in all_users:
        try:
            await context.bot.send_message(uid, f"📢 Объявление:\n\n{text}")
            success += 1
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка {uid}: {e}")
    
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
            await query.edit_message_text(f"🚫 Вы заблокированы до {ban_end}\n\nПричина: {reason}")
            return ConversationHandler.END
        await query.edit_message_text("📝 Опишите какое наказание вам дали и почему его нужно обжаловать:")
        return WAITING_APPEAL
    
    elif query.data == "complaint":
        is_banned, reason, until = is_user_banned(user_id)
        if is_banned:
            ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
            await query.edit_message_text(f"🚫 Вы заблокированы до {ban_end}\n\nПричина: {reason}")
            return ConversationHandler.END
        await query.edit_message_text("📝 Опишите вашу жалобу на персонал:")
        return WAITING_COMPLAINT
    
    elif query.data == "start_chat":
        if user_id in active_chats:
            await query.edit_message_text("💬 У вас уже есть активный чат с администратором.\nПросто напишите ваше сообщение.")
            return
        
        keyboard = [[InlineKeyboardButton("Начать диалог", callback_data=f"accept_chat_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        for admin_id in admins:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"💬 Пользователь @{query.from_user.username or query.from_user.first_name} (ID: {user_id}) запросил чат",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка: {e}")
        
        await query.edit_message_text("✅ Запрос на чат отправлен администраторам.\nОжидайте подключения...")
        return ConversationHandler.END
    
    elif query.data.startswith("accept_chat_"):
        chat_user_id = int(query.data.split("_")[2])
        admin_id = query.from_user.id
        
        if chat_user_id in active_chats:
            await query.answer("⚠️ Этот чат уже занят другим администратором!", show_alert=True)
            return ConversationHandler.END
        
        try:
            user_info = await context.bot.get_chat(chat_user_id)
            username = user_info.username if user_info.username else user_info.first_name
        except:
            username = "Unknown"
        
        active_chats[chat_user_id] = {
            'admin_id': admin_id,
            'username': username,
            'admin_username': query.from_user.username or query.from_user.first_name
        }
        
        try:
            keyboard = [[InlineKeyboardButton("Завершить диалог", callback_data="end_chat_user")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=chat_user_id,
                text=f"💬 Администратор @{query.from_user.username or query.from_user.first_name} подключился к чату!\n\nВсе ваши сообщения будут переслаты администратору.",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка: {e}")
        
        keyboard = [[InlineKeyboardButton("Завершить диалог", callback_data=f"end_chat_admin_{chat_user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"✅ Вы подключились к чату с @{username} (ID: {chat_user_id})\n\nВсе ваши сообщения будут переслаты пользователю.",
            reply_markup=reply_markup
        )
        logger.info(f"Чат: {chat_user_id} (@{username}) <-> админ {admin_id}")
        return ConversationHandler.END
    
    elif query.data == "end_chat_user":
        if user_id in active_chats:
            admin_id = active_chats[user_id]['admin_id']
            del active_chats[user_id]
            try:
                await context.bot.send_message(chat_id=admin_id, text="💬 Пользователь завершил диалог.")
            except:
                pass
            await query.edit_message_text("✅ Диалог завершен.")
            logger.info(f"Чат завершен пользователем {user_id}")
        else:
            await query.answer("У вас нет активного чата", show_alert=True)
        return ConversationHandler.END
    
    elif query.data.startswith("end_chat_admin_"):
        chat_user_id = int(query.data.split("_")[3])
        if chat_user_id in active_chats:
            del active_chats[chat_user_id]
            try:
                await context.bot.send_message(chat_id=chat_user_id, text="💬 Администратор завершил диалог.")
            except:
                pass
            await query.edit_message_text("✅ Диалог завершен.")
            logger.info(f"Чат завершен админом для {chat_user_id}")
        else:
            await query.answer("Чат уже завершен", show_alert=True)
        return ConversationHandler.END
    
    elif query.data.startswith("respond_"):
        appeal_id = int(query.data.split("_")[1])
        context.user_data['responding_to'] = appeal_id
        await query.edit_message_text(f"{query.message.text}\n\n✍️ Напишите ваш ответ:")
        return WAITING_RESPONSE
    
    elif query.data.startswith("ban_"):
        appeal_id = int(query.data.split("_")[1])
        if appeal_id in appeals:
            context.user_data['banning_appeal'] = appeal_id
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                "⏱ Введите время бана:\nПримеры: 1m, 5m, 1h, 12h, 1d, 7d"
            )
            return WAITING_BAN_DURATION
    
    elif query.data.startswith("close_"):
        appeal_id = int(query.data.split("_")[1])
        if appeal_id in appeals:
            user_id = appeals[appeal_id]['user_id']
            appeal_type = appeals[appeal_id]['type']
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Ваша {'жалоба' if appeal_type == 'complaint' else 'апелляция'} #{appeal_id} была закрыта администратором."
                )
            except:
                pass
            del appeals[appeal_id]
            await query.edit_message_text(f"{query.message.text}\n\n🔒 Жалоба закрыта администратором")
        return ConversationHandler.END

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    text = update.message.text
    username = update.message.from_user.username or update.message.from_user.first_name
    
    all_users.add(user_id)
    
    if user_id in active_chats:
        chat_info = active_chats[user_id]
        admin_id = chat_info['admin_id']
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"💬 Сообщение от @{username}:\n\n{text}"
            )
            logger.info(f"✅ {username} ({user_id}) -> Админ {admin_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
        return
    
    for chat_user_id, chat_info in list(active_chats.items()):
        if chat_info['admin_id'] == user_id:
            try:
                user_username = chat_info['username']
                admin_username = chat_info['admin_username']
                await context.bot.send_message(
                    chat_id=chat_user_id,
                    text=f"💬 Администратор @{admin_username}:\n\n{text}"
                )
                logger.info(f"✅ Админ {username} ({user_id}) -> @{user_username} ({chat_user_id})")
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
            return

async def receive_appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global appeal_counter
    user_id = update.message.from_user.id
    all_users.add(user_id)
    
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(f"🚫 Вы заблокированы до {ban_end}\n\nПричина: {reason}")
        return ConversationHandler.END
    
    appeal_counter += 1
    user = update.message.from_user
    appeal_text = update.message.text
    
    appeals[appeal_counter] = {
        'user_id': user.id,
        'username': user.username or user.first_name,
        'text': appeal_text,
        'type': 'appeal'
    }
    
    await update.message.reply_text(f"✅ Ваше обжалование #{appeal_counter} отправлено администрации!\nОжидайте ответа.")
    
    keyboard = [
        [InlineKeyboardButton("Ответить", callback_data=f"respond_{appeal_counter}")],
        [InlineKeyboardButton("Временный бан", callback_data=f"ban_{appeal_counter}")],
        [InlineKeyboardButton("Закрыть жалобу", callback_data=f"close_{appeal_counter}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    for admin_id in admins:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🔔 Новое обжалование #{appeal_counter}\n\n"
                     f"👤 От: @{user.username or user.first_name} (ID: {user.id})\n"
                     f"📝 Текст:\n{appeal_text}",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка: {e}")
    
    return ConversationHandler.END

async def receive_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global appeal_counter
    user_id = update.message.from_user.id
    all_users.add(user_id)
    
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(f"🚫 Вы заблокированы до {ban_end}\n\nПричина: {reason}")
        return ConversationHandler.END
    
    appeal_counter += 1
    user = update.message.from_user
    complaint_text = update.message.text
    
    appeals[appeal_counter] = {
        'user_id': user.id,
        'username': user.username or user.first_name,
        'text': complaint_text,
        'type': 'complaint'
    }
    
    await update.message.reply_text(f"✅ Ваша жалоба #{appeal_counter} отправлена администрации!\nОжидайте ответа.")
    
    keyboard = [
        [InlineKeyboardButton("Ответить", callback_data=f"respond_{appeal_counter}")],
        [InlineKeyboardButton("Временный бан", callback_data=f"ban_{appeal_counter}")],
        [InlineKeyboardButton("Закрыть жалобу", callback_data=f"close_{appeal_counter}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    for admin_id in admins:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🔔 Новая жалоба на персонал #{appeal_counter}\n\n"
                     f"👤 От: @{user.username or user.first_name} (ID: {user.id})\n"
                     f"📝 Текст:\n{complaint_text}",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка: {e}")
    
    return ConversationHandler.END

async def receive_ban_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    duration_str = update.message.text
    appeal_id = context.user_data.get('banning_appeal')
    
    if not appeal_id or appeal_id not in appeals:
        await update.message.reply_text("❌ Ошибка: жалоба не найдена")
        return ConversationHandler.END
    
    seconds, readable = parse_duration(duration_str)
    
    if seconds is None:
        await update.message.reply_text(
            "❌ Неверный формат времени!\n"
            "Используйте: 1m (минуты), 1h (часы), 1d (дни)\n"
            "Попробуйте снова:"
        )
        return WAITING_BAN_DURATION
    
    context.user_data['ban_duration'] = seconds
    context.user_data['ban_duration_readable'] = readable
    
    await update.message.reply_text(f"✅ Время бана: {readable}\n\n📝 Теперь введите причину бана:")
    return WAITING_BAN_REASON

async def receive_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    appeal_id = context.user_data.get('banning_appeal')
    duration = context.user_data.get('ban_duration')
    duration_readable = context.user_data.get('ban_duration_readable')
    
    if not appeal_id or appeal_id not in appeals:
        await update.message.reply_text("❌ Ошибка: жалоба не найдена")
        return ConversationHandler.END
    
    user_id = appeals[appeal_id]['user_id']
    username = appeals[appeal_id]['username']
    
    ban_until = time.time() + duration
    banned_users[user_id] = {
        'until': ban_until,
        'reason': reason
    }
    
    ban_end = datetime.fromtimestamp(ban_until).strftime('%d.%m.%Y %H:%M')
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🚫 Вы были заблокированы в боте на {duration_readable}\n"
                 f"До: {ban_end}\n\n"
                 f"Причина: {reason}"
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ Пользователь @{username} (ID: {user_id}) забанен!\n"
        f"Время: {duration_readable}\n"
        f"До: {ban_end}\n"
        f"Причина: {reason}"
    )
    
    del appeals[appeal_id]
    context.user_data.pop('banning_appeal', None)
    context.user_data.pop('ban_duration', None)
    context.user_data.pop('ban_duration_readable', None)
    
    return ConversationHandler.END

async def receive_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    appeal_id = context.user_data.get('responding_to')
    
    if appeal_id and appeal_id in appeals:
        user_id = appeals[appeal_id]['user_id']
        response_text = update.message.text
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"💬 Ответ администратора на вашу жалобу #{appeal_id}:\n\n"
                     f"{response_text}"
            )
            await update.message.reply_text("✅ Ответ отправлен пользователю!")
            
            keyboard = [[InlineKeyboardButton("Закрыть жалобу", callback_data=f"close_{appeal_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Хотите закрыть эту жалобу?",
                reply_markup=reply_markup
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка отправки ответа: {e}")
    
    context.user_data.pop('responding_to', None)
    return ConversationHandler.END

async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in SUPER_ADMINS:
        await update.message.reply_text("❌ У вас нет прав для добавления администраторов.")
        return ConversationHandler.END
    
    await update.message.reply_text("👤 Отправьте ID пользователя, которого хотите добавить в администраторы:")
    return WAITING_ADMIN_ID

async def receive_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_admin_id = int(update.message.text)
        
        if new_admin_id in admins:
            await update.message.reply_text("⚠️ Этот пользователь уже является администратором.")
        else:
            admins.add(new_admin_id)
            await update.message.reply_text(f"✅ Пользователь {new_admin_id} добавлен в администраторы!")
            try:
                await context.bot.send_message(
                    chat_id=new_admin_id,
                    text="🎉 Вы были назначены администратором бота!"
                )
            except:
                pass
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID. Введите числовой ID пользователя.")
 return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

def main():
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages), group=-1)
    
    appeal_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^(appeal|complaint)$")],
        states={
            WAITING_APPEAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_appeal)],
            WAITING_COMPLAINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_complaint)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    
    response_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^respond_")],
        states={
            WAITING_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_response)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    
    ban_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^ban_")],
        states={
            WAITING_BAN_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_duration)],
            WAITING_BAN_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_reason)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    
    addadmin_handler = ConversationHandler(
        entry_points=[CommandHandler("addadmin", addadmin)],
        states={
            WAITING_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler("gov", gov)],
        states={
            WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
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
