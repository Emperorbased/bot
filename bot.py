import logging
import time
import os
import json
from datetime import datetime
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8555720790:AAF1hpcvwmmFjdr9EuOE16V7M_k0nEuASE0"
SUPER_ADMINS = {7355737254, 8243127223, 8167127645}

DATA_FILE = "bot_data.json"

def load_data():
    global admins, trainee_admins, banned_users, all_users, admin_ratings
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                admins = set(data.get('admins', list(SUPER_ADMINS)))
                trainee_admins = set(data.get('trainee_admins', []))
                banned_users = {int(k): v for k, v in data.get('banned_users', {}).items()}
                all_users = set(data.get('all_users', []))
                admin_ratings = {int(k): v for k, v in data.get('admin_ratings', {}).items()}
                logger.info(f"✅ Загружено: {len(admins)} админов, {len(trainee_admins)} стажёров")
        else:
            admins = SUPER_ADMINS.copy()
            trainee_admins = set()
            banned_users = {}
            all_users = set()
            admin_ratings = {}
    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")
        admins = SUPER_ADMINS.copy()
        trainee_admins = set()
        banned_users = {}
        all_users = set()
        admin_ratings = {}

def save_data():
    try:
        data = {
            'admins': list(admins),
            'trainee_admins': list(trainee_admins),
            'banned_users': banned_users,
            'all_users': list(all_users),
            'admin_ratings': admin_ratings
        }
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f)
        logger.info("💾 Данные сохранены")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

admins = set()
trainee_admins = set()
banned_users = {}
all_users = set()
admin_ratings = {}
load_data()

WAITING_APPEAL, WAITING_COMPLAINT, WAITING_ADMIN_ID, WAITING_TRAINEE_ID, WAITING_RESPONSE, WAITING_BAN_DURATION, WAITING_BAN_REASON, WAITING_BROADCAST, WAITING_BN_ID, WAITING_BN_DURATION, WAITING_BN_REASON = range(11)

appeals = {}
appeal_counter = 0
active_chats = {}

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

def is_admin(user_id):
    return user_id in admins

def is_trainee(user_id):
    return user_id in trainee_admins

def can_ban(user_id):
    return user_id in admins

def is_user_banned(user_id):
    if user_id in banned_users:
        if time.time() < banned_users[user_id]['until']:
            return True, banned_users[user_id]['reason'], banned_users[user_id]['until']
        else:
            del banned_users[user_id]
            save_data()
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

def update_admin_rating(admin_id, rating):
    if admin_id not in admin_ratings:
        admin_ratings[admin_id] = {'total': 0, 'count': 0, 'avg': 0}
    admin_ratings[admin_id]['total'] += rating
    admin_ratings[admin_id]['count'] += 1
    admin_ratings[admin_id]['avg'] = admin_ratings[admin_id]['total'] / admin_ratings[admin_id]['count']
    save_data()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    all_users.add(user_id)
    save_data()
    
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(f"🚫 Вы заблокированы до {ban_end}\n\nПричина: {reason}")
        return
    
    keyboard = [
        [InlineKeyboardButton("Обжаловать наказание", callback_data="appeal")],
        [InlineKeyboardButton("Жалоба на персонал", callback_data="complaint")],
        [InlineKeyboardButton("💬 Чат с админом", callback_data="start_chat")]
    ]
    await update.message.reply_text("Привет! Здесь можно обжаловать наказание.\n\nВыберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))

async def rating_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_ratings:
        await update.message.reply_text("📊 Рейтинг пуст")
        return
    sorted_admins = sorted(admin_ratings.items(), key=lambda x: x[1]['avg'], reverse=True)
    text = "📊 РЕЙТИНГ АДМИНОВ:\n\n"
    for i, (admin_id, rating) in enumerate(sorted_admins, 1):
        stars = "⭐" * int(round(rating['avg']))
        try:
            admin_user = await context.bot.get_chat(admin_id)
            admin_name = admin_user.first_name
        except:
            admin_name = f"ID {admin_id}"
        text += f"{i}. {admin_name}\n   {stars} {rating['avg']:.2f}/5 ({rating['count']} оценок)\n\n"
    await update.message.reply_text(text)

async def gov(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id) and not is_trainee(update.message.from_user.id):
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END
    await update.message.reply_text(f"📢 Рассылка\n\nТекст:\n(Всего: {len(all_users)})")
    return WAITING_BROADCAST

async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id) and not is_trainee(update.message.from_user.id):
        return ConversationHandler.END
    text = update.message.text
    await update.message.reply_text("📤 Отправка...")
    success = 0
    failed = 0
    for uid in all_users:
        try:
            await context.bot.send_message(uid, f"📢 Объявление:\n\n{text}")
            success += 1
        except:
            failed += 1
    await update.message.reply_text(f"✅ {success}\n❌ {failed}")
    return ConversationHandler.END

async def bn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not can_ban(user_id):
        await update.message.reply_text("❌ Стажёры не могут банить")
        return ConversationHandler.END
    await update.message.reply_text("👤 ID для бана:")
    return WAITING_BN_ID

async def receive_bn_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(update.message.text)
        context.user_data['bn_target'] = target_id
        await update.message.reply_text(f"⏱ Время для ID {target_id}:\n(1m, 1h, 1d)")
        return WAITING_BN_DURATION
    except ValueError:
        await update.message.reply_text("❌ Неверный ID:")
        return WAITING_BN_ID

async def receive_bn_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    duration_str = update.message.text
    seconds, readable = parse_duration(duration_str)
    if seconds is None:
        await update.message.reply_text("❌ Формат: 1m, 1h, 1d")
        return WAITING_BN_DURATION
    context.user_data['bn_duration'] = seconds
    context.user_data['bn_duration_readable'] = readable
    await update.message.reply_text(f"✅ {readable}\n\n📝 Причина:")
    return WAITING_BN_REASON

async def receive_bn_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    target_id = context.user_data.get('bn_target')
    duration = context.user_data.get('bn_duration')
    duration_readable = context.user_data.get('bn_duration_readable')
    ban_until = time.time() + duration
    banned_users[target_id] = {'until': ban_until, 'reason': reason}
    save_data()
    ban_end = datetime.fromtimestamp(ban_until).strftime('%d.%m.%Y %H:%M')
    try:
        await context.bot.send_message(target_id, f"🚫 Бан на {duration_readable}\nДо: {ban_end}\n\nПричина: {reason}")
    except:
        pass
    await update.message.reply_text(f"✅ ID {target_id} забанен на {duration_readable}")
    context.user_data.clear()
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
        await query.edit_message_text("📝 Опишите наказание:")
        return WAITING_APPEAL
    
    elif query.data == "complaint":
        is_banned, reason, until = is_user_banned(user_id)
        if is_banned:
            ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
            await query.edit_message_text(f"🚫 Бан до {ban_end}\n\nПричина: {reason}")
            return ConversationHandler.END
        await query.edit_message_text("📝 Опишите жалобу:")
        return WAITING_COMPLAINT
    
    elif query.data == "start_chat":
        if user_id in active_chats:
            await query.edit_message_text("💬 Чат уже активен")
            return
        keyboard = [[InlineKeyboardButton("Начать", callback_data=f"accept_chat_{user_id}")]]
        for admin_id in list(admins) + list(trainee_admins):
            try:
                await context.bot.send_message(admin_id, f"💬 @{query.from_user.username or query.from_user.first_name} (ID: {user_id})", reply_markup=InlineKeyboardMarkup(keyboard))
            except:
                pass
        await query.edit_message_text("✅ Запрос отправлен")
        return
    
    elif query.data.startswith("accept_chat_"):
        chat_user_id = int(query.data.split("_")[2])
        if chat_user_id in active_chats:
            await query.answer("⚠️ Занято!", show_alert=True)
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
            keyboard = [
                [InlineKeyboardButton("⭐", callback_data=f"rate_{admin_id}_1"), InlineKeyboardButton("⭐⭐", callback_data=f"rate_{admin_id}_2"), InlineKeyboardButton("⭐⭐⭐", callback_data=f"rate_{admin_id}_3")],
                [InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"rate_{admin_id}_4"), InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"rate_{admin_id}_5")],
                [InlineKeyboardButton("Пропустить", callback_data="rate_skip")]
            ]
            del active_chats[user_id]
            try:
                await context.bot.send_message(admin_id, "💬 Пользователь завершил")
            except:
                pass
            await query.edit_message_text("✅ Завершено.\n\n📊 Оцените админа:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data.startswith("rate_"):
        if query.data == "rate_skip":
            await query.edit_message_text("Спасибо!")
            return
        parts = query.data.split("_")
        admin_id = int(parts[1])
        rating = int(parts[2])
        update_admin_rating(admin_id, rating)
        try:
            await context.bot.send_message(admin_id, f"⭐ Оценка: {'⭐' * rating}")
        except:
            pass
        await query.edit_message_text(f"✅ Спасибо! {'⭐' * rating}")
        return
    
    elif query.data.startswith("end_chat_admin_"):
        chat_user_id = int(query.data.split("_")[3])
        if chat_user_id in active_chats:
            del active_chats[chat_user_id]
            try:
                await context.bot.send_message(chat_user_id, "💬 Админ завершил")
            except:
                pass
            await query.edit_message_text("✅ Завершено")
        return
    
    elif query.data.startswith("respond_"):
        appeal_id = int(query.data.split("_")[1])
        context.user_data['responding_to'] = appeal_id
        context.user_data['responding_admin'] = user_id
        await query.edit_message_text(f"{query.message.text}\n\n✍️ Ответ:")
        return WAITING_RESPONSE
    
    elif query.data.startswith("ban_"):
        appeal_id = int(query.data.split("_")[1])
        if not can_ban(user_id):
            await query.answer("❌ Стажёры не могут банить", show_alert=True)
            return
        if appeal_id in appeals:
            context.user_data['banning_appeal'] = appeal_id
            await query.edit_message_text(f"{query.message.text}\n\n⏱ Время:")
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
    save_data()
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
    save_data()
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(f"🚫 Бан до {ban_end}\n\nПричина: {reason}")
        return ConversationHandler.END
    appeal_counter += 1
    user = update.message.from_user
    appeals[appeal_counter] = {'user_id': user.id, 'username': user.username or user.first_name, 'text': update.message.text, 'type': 'appeal'}
    await update.message.reply_text(f"✅ Обжалование #{appeal_counter} отправлено!")
    keyboard = [
        [InlineKeyboardButton("Ответить", callback_data=f"respond_{appeal_counter}")],
        [InlineKeyboardButton("Бан", callback_data=f"ban_{appeal_counter}")],
        [InlineKeyboardButton("Закрыть", callback_data=f"close_{appeal_counter}")]
    ]
    for admin_id in list(admins) + list(trainee_admins):
        try:
            mark = "🔰" if admin_id in trainee_admins else ""
            await context.bot.send_message(admin_id, f"🔔 Обжалование #{appeal_counter} {mark}\n\n👤 @{user.username or user.first_name} (ID: {user.id})\n📝 {update.message.text}", reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            pass
    return ConversationHandler.END

async def receive_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global appeal_counter
    user_id = update.message.from_user.id
    all_users.add(user_id)
    save_data()
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(f"🚫 Бан до {ban_end}\n\nПричина: {reason}")
        return ConversationHandler.END
    appeal_counter += 1
    user = update.message.from_user
    appeals[appeal_counter] = {'user_id': user.id, 'username': user.username or user.first_name, 'text': update.message.text, 'type': 'complaint'}
    await update.message.reply_text(f"✅ Жалоба #{appeal_counter} отправлена!")
    keyboard = [
        [InlineKeyboardButton("Ответить", callback_data=f"respond_{appeal_counter}")],
        [InlineKeyboardButton("Бан", callback_data=f"ban_{appeal_counter}")],
        [InlineKeyboardButton("Закрыть", callback_data=f"close_{appeal_counter}")]
    ]
    for admin_id in list(admins) + list(trainee_admins):
        try:
            mark = "🔰" if admin_id in trainee_admins else ""
            await context.bot.send_message(admin_id, f"🔔 Жалоба #{appeal_counter} {mark}\n\n👤 @{user.username or user.first_name} (ID: {user.id})\n📝 {update.message.text}", reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            pass
    return ConversationHandler.END

async def receive_ban_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    appeal_id = context.user_data.get('banning_appeal')
    if not appeal_id or appeal_id not in appeals:
        await update.message.reply_text("❌ Ошибка")
        return ConversationHandler.END
    seconds, readable = parse_duration(update.message.text)
    if seconds is None:
        await update.message.reply_text("❌ Формат: 1m, 1h, 1d")
        return WAITING_BAN_DURATION
    context.user_data['ban_duration'] = seconds
    context.user_data['ban_duration_readable'] = readable
    await update.message.reply_text(f"✅ {readable}\n\n📝 Причина:")
    return WAITING_BAN_REASON

async def receive_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    appeal_id = context.user_data.get('banning_appeal')
    duration = context.user_data.get('ban_duration')
    duration_readable = context.user_data.get('ban_duration_readable')
    if not appeal_id or appeal_id not in appeals:
        return ConversationHandler.END
    user_id = appeals[appeal_id]['user_id']
    username = appeals[appeal_id]['username']
    ban_until = time.time() + duration
    banned_users[user_id] = {'until': ban_until, 'reason': update.message.text}
    save_data()
    ban_end = datetime.fromtimestamp(ban_until).strftime('%d.%m.%Y %H:%M')
    try:
        await context.bot.send_message(user_id, f"🚫 Бан на {duration_readable}\nДо: {ban_end}\n\nПричина: {update.message.text}")
    except:
        pass
    await update.message.reply_text(f"✅ @{username} (ID: {user_id}) забанен")
    del appeals[appeal_id]
    context.user_data.clear()
    return ConversationHandler.END

async def receive_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    appeal_id = context.user_data.get('responding_to')
    admin_id = context.user_data.get('responding_admin')
    if appeal_id and appeal_id in appeals:
        user_id = appeals[appeal_id]['user_id']
        keyboard = [
            [InlineKeyboardButton("⭐", callback_data=f"rate_{admin_id}_1"), InlineKeyboardButton("⭐⭐", callback_data=f"rate_{admin_id}_2"), InlineKeyboardButton("⭐⭐⭐", callback_data=f"rate_{admin_id}_3")],
            [InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"rate_{admin_id}_4"), InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"rate_{admin_id}_5")],
            [InlineKeyboardButton("Пропустить", callback_data="rate_skip")]
        ]
        try:
            await context.bot.send_message(user_id, f"💬 Ответ на #{appeal_id}:\n\n{update.message.text}\n\n📊 Оцените:", reply_markup=InlineKeyboardMarkup(keyboard))
            await update.message.reply_text("✅ Отправлено!")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    context.user_data.clear()
    return ConversationHandler.END

async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in SUPER_ADMINS:
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END
    await update.message.reply_text("👤 ID админа:")
    return WAITING_ADMIN_ID

async def receive_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_admin_id = int(update.message.text)
        if new_admin_id in admins:
            await update.message.reply_text("⚠️ Уже админ")
        else:
            admins.add(new_admin_id)
            save_data()
            await update.message.reply_text(f"✅ {new_admin_id} - полный админ!")
            try:
                await context.bot.send_message(new_admin_id, "🎉 Вы полный админ!")
            except:
                pass
    except:
        await update.message.reply_text("❌ Неверный ID")
    return ConversationHandler.END

async def addadm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in SUPER_ADMINS:
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END
    await update.message.reply_text("👤 ID стажёра:")
    return WAITING_TRAINEE_ID

async def receive_trainee_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_trainee_id = int(update.message.text)
        if new_trainee_id in trainee_admins:
            await update.message.reply_text("⚠️ Уже стажёр")
        else:
            trainee_admins.add(new_trainee_id)
            save_data()
            await update.message.reply_text(f"✅ {new_trainee_id} - стажёр (без прав на бан)!")
            try:
                await context.bot.send_message(new_trainee_id, "🔰 Вы стажёр-админ! (без прав на бан)")
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
    addadm_handler = ConversationHandler(entry_points=[CommandHandler("addadm", addadm)], states={WAITING_TRAINEE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_trainee_id)]}, fallbacks=[CommandHandler("cancel", cancel)])
    broadcast_handler = ConversationHandler(entry_points=[CommandHandler("gov", gov)], states={WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast)]}, fallbacks=[CommandHandler("cancel", cancel)])
    bn_handler = ConversationHandler(entry_points=[CommandHandler("bn", bn)], states={WAITING_BN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_bn_id)], WAITING_BN_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_bn_duration)], WAITING_BN_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_bn_reason)]}, fallbacks=[CommandHandler("cancel", cancel)])
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rating", rating_cmd))
    application.add_handler(appeal_handler)
    application.add_handler(response_handler)
    application.add_handler(ban_handler)
    application.add_handler(addadmin_handler)
    application.add_handler(addadm_handler)
    application.add_handler(broadcast_handler)
    application.add_handler(bn_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🚀 Бот запущен! Нет рекламы, новый токен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
