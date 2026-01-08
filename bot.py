import logging
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "8546823235:AAFI-3t1SCB9S4PI5izbAAz1XEwHjRlL-6E"

# Главные администраторы (могут добавлять других админов)
SUPER_ADMINS = {7355737254, 8243127223, 8167127645}

# Все администраторы (включая добавленных)
admins = SUPER_ADMINS.copy()

# Состояния для ConversationHandler
WAITING_APPEAL, WAITING_COMPLAINT, WAITING_ADMIN_ID, WAITING_RESPONSE, WAITING_BAN_DURATION, WAITING_BAN_REASON = range(6)

# Хранилище жалоб и банов
appeals = {}
appeal_counter = 0
banned_users = {}  # {user_id: {'until': timestamp, 'reason': str}}

def is_user_banned(user_id):
    """Проверка, забанен ли пользователь"""
    if user_id in banned_users:
        if time.time() < banned_users[user_id]['until']:
            return True, banned_users[user_id]['reason'], banned_users[user_id]['until']
        else:
            # Бан истек
            del banned_users[user_id]
    return False, None, None

def parse_duration(duration_str):
    """Парсинг строки времени (1m, 1h, 1d) в секунды"""
    duration_str = duration_str.strip().lower()
    
    if duration_str[-1] == 'm':
        return int(duration_str[:-1]) * 60, f"{duration_str[:-1]} минут(ы)"
    elif duration_str[-1] == 'h':
        return int(duration_str[:-1]) * 3600, f"{duration_str[:-1]} час(ов)"
    elif duration_str[-1] == 'd':
        return int(duration_str[:-1]) * 86400, f"{duration_str[:-1]} дней"
    else:
        return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.message.from_user.id
    
    # Проверка бана
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(
            f"🚫 Вы заблокированы в боте до {ban_end}\n\n"
            f"Причина: {reason}"
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("Обжаловать наказание", callback_data="appeal")],
        [InlineKeyboardButton("Жалоба на персонал", callback_data="complaint")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Привет! Здесь можно обжаловать наказание.\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "appeal":
        # Проверка бана
        is_banned, reason, until = is_user_banned(user_id)
        if is_banned:
            ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
            await query.edit_message_text(
                f"🚫 Вы заблокированы в боте до {ban_end}\n\n"
                f"Причина: {reason}"
            )
            return ConversationHandler.END
            
        await query.edit_message_text(
            "📝 Опишите какое наказание вам дали и почему его нужно обжаловать:"
        )
        return WAITING_APPEAL
    
    elif query.data == "complaint":
        # Проверка бана
        is_banned, reason, until = is_user_banned(user_id)
        if is_banned:
            ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
            await query.edit_message_text(
                f"🚫 Вы заблокированы в боте до {ban_end}\n\n"
                f"Причина: {reason}"
            )
            return ConversationHandler.END
            
        await query.edit_message_text(
            "📝 Опишите вашу жалобу на персонал:"
        )
        return WAITING_COMPLAINT
    
    elif query.data.startswith("respond_"):
        # Админ хочет ответить на жалобу
        appeal_id = int(query.data.split("_")[1])
        context.user_data['responding_to'] = appeal_id
        await query.edit_message_text(
            f"{query.message.text}\n\n"
            "✍️ Напишите ваш ответ:"
        )
        return WAITING_RESPONSE
    
    elif query.data.startswith("ban_"):
        # Админ хочет забанить пользователя
        appeal_id = int(query.data.split("_")[1])
        if appeal_id in appeals:
            context.user_data['banning_appeal'] = appeal_id
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                "⏱ Введите время бана:\n"
                "Примеры: 1m (1 минута), 5m (5 минут), 1h (1 час), 12h (12 часов), 1d (1 день), 7d (7 дней)"
            )
            return WAITING_BAN_DURATION
    
    elif query.data.startswith("close_"):
        # Админ закрывает жалобу
        appeal_id = int(query.data.split("_")[1])
        if appeal_id in appeals:
            user_id = appeals[appeal_id]['user_id']
            appeal_type = appeals[appeal_id]['type']
            
            # Уведомляем пользователя
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Ваша {'жалоба' if appeal_type == 'complaint' else 'апелляция'} #{appeal_id} была закрыта администратором."
                )
            except:
                pass
            
            # Удаляем жалобу из системы
            del appeals[appeal_id]
            
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                f"🔒 Жалоба закрыта администратором @{query.from_user.username or query.from_user.first_name}"
            )
        return ConversationHandler.END

async def receive_appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение текста обжалования"""
    global appeal_counter
    
    user_id = update.message.from_user.id
    
    # Проверка бана
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(
            f"🚫 Вы заблокированы в боте до {ban_end}\n\n"
            f"Причина: {reason}"
        )
        return ConversationHandler.END
    
    appeal_counter += 1
    
    user = update.message.from_user
    appeal_text = update.message.text
    
    # Сохраняем жалобу
    appeals[appeal_counter] = {
        'user_id': user.id,
        'username': user.username or user.first_name,
        'text': appeal_text,
        'type': 'appeal'
    }
    
    await update.message.reply_text(
        f"✅ Ваше обжалование #{appeal_counter} отправлено администрации!\n"
        "Ожидайте ответа."
    )
    
    # Отправляем всем админам
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
            logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
    
    return ConversationHandler.END

async def receive_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение текста жалобы на персонал"""
    global appeal_counter
    
    user_id = update.message.from_user.id
    
    # Проверка бана
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(
            f"🚫 Вы заблокированы в боте до {ban_end}\n\n"
            f"Причина: {reason}"
        )
        return ConversationHandler.END
    
    appeal_counter += 1
    
    user = update.message.from_user
    complaint_text = update.message.text
    
    # Сохраняем жалобу
    appeals[appeal_counter] = {
        'user_id': user.id,
        'username': user.username or user.first_name,
        'text': complaint_text,
        'type': 'complaint'
    }
    
    await update.message.reply_text(
        f"✅ Ваша жалоба #{appeal_counter} отправлена администрации!\n"
        "Ожидайте ответа."
    )
    
    # Отправляем всем админам
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
            logger.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")
    
    return ConversationHandler.END

async def receive_ban_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение времени бана"""
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
    
    await update.message.reply_text(
        f"✅ Время бана: {readable}\n\n"
        "📝 Теперь введите причину бана:"
    )
    return WAITING_BAN_REASON

async def receive_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение причины бана и применение"""
    reason = update.message.text
    appeal_id = context.user_data.get('banning_appeal')
    duration = context.user_data.get('ban_duration')
    duration_readable = context.user_data.get('ban_duration_readable')
    
    if not appeal_id or appeal_id not in appeals:
        await update.message.reply_text("❌ Ошибка: жалоба не найдена")
        return ConversationHandler.END
    
    user_id = appeals[appeal_id]['user_id']
    username = appeals[appeal_id]['username']
    
    # Применяем бан
    ban_until = time.time() + duration
    banned_users[user_id] = {
        'until': ban_until,
        'reason': reason
    }
    
    ban_end = datetime.fromtimestamp(ban_until).strftime('%d.%m.%Y %H:%M')
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🚫 Вы были заблокированы в боте на {duration_readable}\n"
                 f"До: {ban_end}\n\n"
                 f"Причина: {reason}"
        )
    except:
        pass
    
    # Уведомляем админа
    await update.message.reply_text(
        f"✅ Пользователь @{username} (ID: {user_id}) забанен!\n"
        f"Время: {duration_readable}\n"
        f"До: {ban_end}\n"
        f"Причина: {reason}"
    )
    
    # Закрываем жалобу
    del appeals[appeal_id]
    
    # Очищаем данные
    context.user_data.pop('banning_appeal', None)
    context.user_data.pop('ban_duration', None)
    context.user_data.pop('ban_duration_readable', None)
    
    return ConversationHandler.END

async def receive_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ответа от админа"""
    appeal_id = context.user_data.get('responding_to')
    
    if appeal_id and appeal_id in appeals:
        user_id = appeals[appeal_id]['user_id']
        response_text = update.message.text
        
        # Отправляем ответ пользователю
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"💬 Ответ администратора на вашу жалобу #{appeal_id}:\n\n"
                     f"{response_text}"
            )
            await update.message.reply_text("✅ Ответ отправлен пользователю!")
            
            # Предлагаем закрыть жалобу
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
    """Команда для добавления нового админа (только для супер-админов)"""
    user_id = update.message.from_user.id
    
    if user_id not in SUPER_ADMINS:
        await update.message.reply_text("❌ У вас нет прав для добавления администраторов.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "👤 Отправьте ID пользователя, которого хотите добавить в администраторы:"
    )
    return WAITING_ADMIN_ID

async def receive_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ID нового админа"""
    try:
        new_admin_id = int(update.message.text)
        
        if new_admin_id in admins:
            await update.message.reply_text("⚠️ Этот пользователь уже является администратором.")
        else:
            admins.add(new_admin_id)
            await update.message.reply_text(
                f"✅ Пользователь {new_admin_id} добавлен в администраторы!"
            )
            
            # Уведомляем нового админа
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
    """Отмена текущего действия"""
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    # ConversationHandler для обжалований
    appeal_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^(appeal|complaint)$")],
        states={
            WAITING_APPEAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_appeal)],
            WAITING_COMPLAINT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_complaint)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    
    # ConversationHandler для ответов админов
    response_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^respond_")],
        states={
            WAITING_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_response)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    
    # ConversationHandler для банов
    ban_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^ban_")],
        states={
            WAITING_BAN_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_duration)],
            WAITING_BAN_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_reason)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False
    )
    
    # ConversationHandler для добавления админов
    addadmin_handler = ConversationHandler(
        entry_points=[CommandHandler("addadmin", addadmin)],
        states={
            WAITING_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(appeal_handler)
    application.add_handler(response_handler)
    application.add_handler(ban_handler)
    application.add_handler(addadmin_handler)
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^close_"))
    
    # Запуск бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
