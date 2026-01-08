import logging
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
WAITING_APPEAL, WAITING_COMPLAINT, WAITING_ADMIN_ID, WAITING_RESPONSE = range(4)

# Хранилище жалоб
appeals = {}
appeal_counter = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
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
    
    if query.data == "appeal":
        await query.edit_message_text(
            "📝 Опишите какое наказание вам дали и почему его нужно обжаловать:"
        )
        return WAITING_APPEAL
    
    elif query.data == "complaint":
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
    application.add_handler(addadmin_handler)
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^close_"))
    
    # Запуск бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
