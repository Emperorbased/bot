import logging
import time
import os
import random
from datetime import datetime, timedelta
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "8546823235:AAFI-3t1SCB9S4PI5izbAAz1XEwHjRlL-6E"

# Главные администраторы
SUPER_ADMINS = {7355737254, 8243127223, 8167127645}
admins = SUPER_ADMINS.copy()

# Состояния
WAITING_APPEAL, WAITING_COMPLAINT, WAITING_ADMIN_ID, WAITING_RESPONSE, WAITING_BAN_DURATION, WAITING_BAN_REASON = range(6)

# Хранилище
appeals = {}
appeal_counter = 0
banned_users = {}
active_chats = {}
users_data = {}  # {user_id: {'coins': int, 'faith': int, 'last_work': timestamp, 'wins': int, 'losses': int}}
active_battles = {}  # {battle_id: {'player1': id, 'player2': id, 'bet': int}}

# Работы и их параметры
JOBS = {
    'shawarma': {'name': '🌯 Шаурмист', 'pay': (50, 150), 'cooldown': 1800, 'emoji': '🌯'},
    'watermelon': {'name': '🍉 Продавец арбузов', 'pay': (30, 100), 'cooldown': 1800, 'emoji': '🍉'},
    'taxi': {'name': '🚕 Таксист', 'pay': (100, 200), 'cooldown': 3600, 'emoji': '🚕'},
    'kebab': {'name': '🥙 Шашлычник', 'pay': (70, 180), 'cooldown': 2400, 'emoji': '🥙'},
}

# Flask для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK"

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

def get_user_data(user_id):
    """Получить данные пользователя"""
    if user_id not in users_data:
        users_data[user_id] = {
            'coins': 100,  # Стартовые жиркоины
            'faith': 50,  # Вера в Аллаха (0-100)
            'last_work': {},  # {job_name: timestamp}
            'wins': 0,
            'losses': 0,
            'total_earned': 0
        }
    return users_data[user_id]

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
        return int(duration_str[:-1]) * 60, f"{duration_str[:-1]} минут(ы)"
    elif duration_str[-1] == 'h':
        return int(duration_str[:-1]) * 3600, f"{duration_str[:-1]} час(ов)"
    elif duration_str[-1] == 'd':
        return int(duration_str[:-1]) * 86400, f"{duration_str[:-1]} дней"
    else:
        return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        ban_end = datetime.fromtimestamp(until).strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(f"🚫 Вы заблокированы до {ban_end}\n\nПричина: {reason}")
        return
    
    user_data = get_user_data(user_id)
    
    keyboard = [
        [InlineKeyboardButton("📋 Жалобы", callback_data="appeals_menu")],
        [InlineKeyboardButton("🎮 Игра", callback_data="game_menu")],
        [InlineKeyboardButton("💬 Чат с админом", callback_data="start_chat")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Привет, {update.message.from_user.first_name}! 👋\n\n"
        f"💰 Жиркоины: {user_data['coins']}\n"
        f"🙏 Вера в Аллаха: {user_data['faith']}%\n"
        f"⚔️ Побед/Поражений: {user_data['wins']}/{user_data['losses']}\n\n"
        f"Выберите раздел:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    
    # Меню жалоб
    if query.data == "appeals_menu":
        keyboard = [
            [InlineKeyboardButton("Обжаловать наказание", callback_data="appeal")],
            [InlineKeyboardButton("Жалоба на персонал", callback_data="complaint")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📋 Раздел жалоб:", reply_markup=reply_markup)
        return
    
    # Игровое меню
    elif query.data == "game_menu":
        keyboard = [
            [InlineKeyboardButton("💼 Работа", callback_data="work_menu")],
            [InlineKeyboardButton("⚔️ Битва", callback_data="battle_menu")],
            [InlineKeyboardButton("🙏 Молитва", callback_data="pray")],
            [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🎮 Игровое меню\n\n"
            f"💰 Жиркоины: {user_data['coins']}\n"
            f"🙏 Вера: {user_data['faith']}%",
            reply_markup=reply_markup
        )
        return
    
    # Меню работы
    elif query.data == "work_menu":
        keyboard = []
        for job_key, job in JOBS.items():
            last_work = user_data['last_work'].get(job_key, 0)
            cooldown = job['cooldown']
            time_left = int(cooldown - (time.time() - last_work))
            
            if time_left > 0:
                minutes = time_left // 60
                button_text = f"{job['emoji']} {job['name']} (⏳ {minutes}м)"
                callback = f"work_cooldown_{job_key}"
            else:
                button_text = f"{job['emoji']} {job['name']} ({job['pay'][0]}-{job['pay'][1]}💰)"
                callback = f"work_{job_key}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback)])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="game_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "💼 Выберите работу:\n\n"
            "Каждая работа имеет откат (cooldown)",
            reply_markup=reply_markup
        )
        return
    
    # Работа
    elif query.data.startswith("work_"):
        if query.data.startswith("work_cooldown_"):
            await query.answer("⏳ Эта работа ещё недоступна!", show_alert=True)
            return
        
        job_key = query.data.replace("work_", "")
        job = JOBS[job_key]
        
        # Проверка кулдауна
        last_work = user_data['last_work'].get(job_key, 0)
        if time.time() - last_work < job['cooldown']:
            await query.answer("⏳ Слишком рано!", show_alert=True)
            return
        
        # Работа
        earnings = random.randint(job['pay'][0], job['pay'][1])
        faith_bonus = int(earnings * (user_data['faith'] / 100))
        total = earnings + faith_bonus
        
        user_data['coins'] += total
        user_data['total_earned'] += total
        user_data['last_work'][job_key] = time.time()
        user_data['faith'] = min(100, user_data['faith'] + random.randint(1, 3))
        
        await query.answer(f"💰 Заработано: {total} жиркоинов!", show_alert=True)
        
        keyboard = [[InlineKeyboardButton("◀️ К работам", callback_data="work_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{job['emoji']} {job['name']}\n\n"
            f"💵 Базовая зарплата: {earnings}\n"
            f"🙏 Бонус веры: +{faith_bonus}\n"
            f"💰 Итого: {total} жиркоинов\n\n"
            f"Ваш баланс: {user_data['coins']} 💰",
            reply_markup=reply_markup
        )
        return
    
    # Молитва
    elif query.data == "pray":
        faith_gain = random.randint(5, 15)
        coin_bonus = random.randint(0, 50) if user_data['faith'] > 70 else 0
        
        user_data['faith'] = min(100, user_data['faith'] + faith_gain)
        user_data['coins'] += coin_bonus
        
        messages = [
            "🙏 Аллах принял вашу молитву!",
            "☪️ Вера укрепляется!",
            "🕌 Благословение получено!",
            "✨ Аллах доволен вами!"
        ]
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="game_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bonus_text = f"\n💰 Бонус: +{coin_bonus} жиркоинов!" if coin_bonus > 0 else ""
        
        await query.edit_message_text(
            f"{random.choice(messages)}\n\n"
            f"🙏 Вера: +{faith_gain}% (Всего: {user_data['faith']}%){bonus_text}",
            reply_markup=reply_markup
        )
        return
    
    # Профиль
    elif query.data == "profile":
        winrate = (user_data['wins'] / (user_data['wins'] + user_data['losses']) * 100) if (user_data['wins'] + user_data['losses']) > 0 else 0
        
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="game_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"👤 Профиль {query.from_user.first_name}\n\n"
            f"💰 Жиркоины: {user_data['coins']}\n"
            f"💵 Всего заработано: {user_data['total_earned']}\n"
            f"🙏 Вера в Аллаха: {user_data['faith']}%\n\n"
            f"⚔️ Статистика боёв:\n"
            f"✅ Побед: {user_data['wins']}\n"
            f"❌ Поражений: {user_data['losses']}\n"
            f"📊 Винрейт: {winrate:.1f}%",
            reply_markup=reply_markup
        )
        return
    
    # Меню битвы
    elif query.data == "battle_menu":
        keyboard = [
            [InlineKeyboardButton("⚔️ Создать битву (50💰)", callback_data="create_battle_50")],
            [InlineKeyboardButton("⚔️ Создать битву (100💰)", callback_data="create_battle_100")],
            [InlineKeyboardButton("⚔️ Создать битву (200💰)", callback_data="create_battle_200")],
            [InlineKeyboardButton("🎲 Случайная битва", callback_data="random_battle")],
            [InlineKeyboardButton("◀️ Назад", callback_data="game_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⚔️ Битва игроков\n\n"
            "Выберите ставку или создайте случайную битву!",
            reply_markup=reply_markup
        )
        return
    
    # Создание битвы
    elif query.data.startswith("create_battle_"):
        bet = int(query.data.split("_")[2])
        
        if user_data['coins'] < bet:
            await query.answer(f"❌ Недостаточно жиркоинов! Нужно: {bet}", show_alert=True)
            return
        
        battle_id = f"{user_id}_{int(time.time())}"
        active_battles[battle_id] = {
            'player1': user_id,
            'player1_name': query.from_user.first_name,
            'player2': None,
            'bet': bet,
            'timestamp': time.time()
        }
        
        user_data['coins'] -= bet
        
        keyboard = [[InlineKeyboardButton("❌ Отменить битву", callback_data=f"cancel_battle_{battle_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚔️ Битва создана!\n\n"
            f"💰 Ставка: {bet} жиркоинов\n"
            f"👤 Создатель: {query.from_user.first_name}\n\n"
            f"Ожидание соперника...\n"
            f"ID битвы: {battle_id}",
            reply_markup=reply_markup
        )
        
        # Уведомляем других игроков
        for uid in users_data.keys():
            if uid != user_id and uid not in banned_users:
                try:
                    keyboard = [[InlineKeyboardButton("⚔️ Принять бой!", callback_data=f"join_battle_{battle_id}")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"⚔️ Новая битва!\n\n"
                             f"👤 Соперник: {query.from_user.first_name}\n"
                             f"💰 Ставка: {bet} жиркоинов",
                        reply_markup=reply_markup
                    )
                except:
                    pass
        return
    
    # Присоединиться к битве
    elif query.data.startswith("join_battle_"):
        battle_id = query.data.replace("join_battle_", "")
        
        if battle_id not in active_battles:
            await query.answer("❌ Битва уже завершена!", show_alert=True)
            return
        
        battle = active_battles[battle_id]
        bet = battle['bet']
        
        if user_data['coins'] < bet:
            await query.answer(f"❌ Недостаточно жиркоинов! Нужно: {bet}", show_alert=True)
            return
        
        if battle['player1'] == user_id:
            await query.answer("❌ Это ваша битва!", show_alert=True)
            return
        
        user_data['coins'] -= bet
        
        player1_id = battle['player1']
        player1_data = get_user_data(player1_id)
        
        # Бой!
        player1_power = random.randint(1, 100) + player1_data['faith']
        player2_power = random.randint(1, 100) + user_data['faith']
        
        winner_id = player1_id if player1_power > player2_power else user_id
        loser_id = user_id if winner_id == player1_id else player1_id
        
        winner_data = get_user_data(winner_id)
        loser_data = get_user_data(loser_id)
        
        prize = bet * 2
        winner_data['coins'] += prize
        winner_data['wins'] += 1
        loser_data['losses'] += 1
        
        winner_name = battle['player1_name'] if winner_id == player1_id else query.from_user.first_name
        loser_name = query.from_user.first_name if winner_id == player1_id else battle['player1_name']
        
        result_text = (
            f"⚔️ БИТВА ЗАВЕРШЕНА!\n\n"
            f"👤 {battle['player1_name']} (💪 {player1_power})\n"
            f"     VS\n"
            f"👤 {query.from_user.first_name} (💪 {player2_power})\n\n"
            f"🏆 Победитель: {winner_name}\n"
            f"💰 Приз: {prize} жиркоинов\n\n"
            f"💸 Проигравший: {loser_name}"
        )
        
        # Уведомляем обоих
        try:
            await context.bot.send_message(chat_id=player1_id, text=result_text)
        except:
            pass
        
        try:
            await query.edit_message_text(result_text)
        except:
            await context.bot.send_message(chat_id=user_id, text=result_text)
        
        del active_battles[battle_id]
        return
    
    # Отмена битвы
    elif query.data.startswith("cancel_battle_"):
        battle_id = query.data.replace("cancel_battle_", "")
        
        if battle_id in active_battles:
            battle = active_battles[battle_id]
            if battle['player1'] == user_id:
                user_data['coins'] += battle['bet']
                del active_battles[battle_id]
                await query.edit_message_text("❌ Битва отменена. Ставка возвращена.")
        return
    
    # Назад в главное меню
    elif query.data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("📋 Жалобы", callback_data="appeals_menu")],
            [InlineKeyboardButton("🎮 Игра", callback_data="game_menu")],
            [InlineKeyboardButton("💬 Чат с админом", callback_data="start_chat")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💰 Жиркоины: {user_data['coins']}\n"
            f"🙏 Вера: {user_data['faith']}%\n\n"
            f"Выберите раздел:",
            reply_markup=reply_markup
        )
        return
    
    # Жалобы
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
        
        await query.edit_message_text("✅ Запрос на чат отправлен.\nОжидайте подключения...")
        return ConversationHandler.END
    
    elif query.data.startswith("accept_chat_"):
        chat_user_id = int(query.data.split("_")[2])
        admin_id = query.from_user.id
        
        if chat_user_id in active_chats:
            await query.answer("⚠️ Этот чат уже занят!", show_alert=True)
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
                text=f"💬 Администратор @{query.from_user.username or query.from_user.first_name} подключился к чату!\n\nВсе ваши сообщения теперь будут переслаты администратору.",
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
        
        logger.info(f"Создан чат: пользователь {chat_user_id} (@{username}) <-> админ {admin_id}")
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
            logger.info(f"Чат завершен админом для пользователя {chat_user_id}")
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
                f"{query.message.text}\n\n⏱ Введите время бана:\nПримеры: 1m, 5m, 1h, 12h, 1d, 7d"
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
                    text=f"✅ Ваша {'жалоба' if appeal_type == 'complaint' else 'апелляция'} #{appeal_id} закрыта."
                )
            except:
                pass
            
            del appeals[appeal_id]
            await query.edit_message_text(f"{query.message.text}\n\n🔒 Жалоба закрыта")
        return ConversationHandler.END

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ГЛАВНЫЙ обработчик ВСЕХ текстовых сообщений"""
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    text = update.message.text
    username = update.message.from_user.username or update.message.from_user.first_name
    
    # Чат пользователя
    if user_id in active_chats:
        chat_info = active_chats[user_id]
        admin_id = chat_info['admin_id']
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"💬 Сообщение от @{username}:\n\n{text}"
            )
            logger.info(f"✅ Пользователь {username} ({user_id}) -> Админ {admin_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки админу: {e}")
        return
    
    # Чат админа
    for chat_user_id, chat_info in list(active_chats.items()):
        if chat_info['admin_id'] == user_id:
            try:
                user_username = chat_info['username']
                admin_username = chat_info['admin_username']
                await context.bot.send_message(
                    chat_id=chat_user_id,
                    text=f"💬 Администратор @{admin_username}:\n\n{text}"
                )
                logger.info(f"✅ Админ {username} ({user_id}) -> Пользователь @{user_username} ({chat_user_id})")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки пользователю: {e}")
            return

async def receive_appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global appeal_counter
    user_id = update.message.from_user.id
    
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
    
    await update.message.reply_text(f"✅ Обжалование #{appeal_counter} отправлено!")
    
    keyboard = [
        [InlineKeyboardButton("Ответить", callback_data=f"respond_{appeal_counter}")],
        [InlineKeyboardButton("Временный бан", callback_data=f"ban_{appeal_counter}")],
        [InlineKeyboardButton("Закрыть", callback_data=f"close_{appeal_counter}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    for admin_id in admins:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🔔 Новое обжалование #{appeal_counter}\n\n"
                     f"👤 От: @{user.username or user.first_name} (ID: {user.id})\n"
                     f"📝 {appeal_text}",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка: {e}")
    
    return ConversationHandler.END

async def receive_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global appeal_counter
    user_id = update.message.from_user.id
    
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
    
    await update.message.reply_text(f"✅ Жалоба #{appeal_counter} отправлена!")
    
    keyboard = [
        [InlineKeyboardButton("Ответить", callback_data=f"respond_{appeal_counter}")],
        [InlineKeyboardButton("Временный бан", callback_data=f"ban_{appeal_counter}")],
        [InlineKeyboardButton("Закрыть", callback_data=f"close_{appeal_counter}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    for admin_id in admins:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🔔 Жалоба на персонал #{appeal_counter}\n\n"
                     f"👤 От: @{user.username or user.first_name} (ID: {user.id})\n"
                     f"📝 {complaint_text}",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка: {e}")
    
    return ConversationHandler.END

async def receive_ban_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    duration_str = update.message.text
    appeal_id = context.user_data.get('banning_appeal')
    
    if not appeal_id or appeal_id not in appeals:
        await update.message.reply_text("❌ Ошибка")
        return ConversationHandler.END
    
    seconds, readable = parse_duration(duration_str)
    
    if seconds is None:
        await update.message.reply_text("❌ Неверный формат!\nИспользуйте: 1m, 1h, 1d")
        return WAITING_BAN_DURATION
    
    context.user_data['ban_duration'] = seconds
    context.user_data['ban_duration_readable'] = readable
    
    await update.message.reply_text(f"✅ Время: {readable}\n\n📝 Введите причину:")
    return WAITING_BAN_REASON

async def receive_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    appeal_id = context.user_data.get('banning_appeal')
    duration = context.user_data.get('ban_duration')
    duration_readable = context.user_data.get('ban_duration_readable')
    
    if not appeal_id or appeal_id not in appeals:
        await update.message.reply_text("❌ Ошибка")
        return ConversationHandler.END
    
    user_id = appeals[appeal_id]['user_id']
    username = appeals[appeal_id]['username']
    
    ban_until = time.time() + duration
    banned_users[user_id] = {'until': ban_until, 'reason': reason}
    
    ban_end = datetime.fromtimestamp(ban_until).strftime('%d.%m.%Y %H:%M')
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🚫 Вы забанены на {duration_readable}\nДо: {ban_end}\n\nПричина: {reason}"
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ @{username} (ID: {user_id}) забанен!\nВремя: {duration_readable}\nДо: {ban_end}"
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
                text=f"💬 Ответ на жалобу #{appeal_id}:\n\n{response_text}"
            )
            await update.message.reply_text("✅ Ответ отправлен!")
            
            keyboard = [[InlineKeyboardButton("Закрыть", callback_data=f"close_{appeal_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Закрыть жалобу?", reply_markup=reply_markup)
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    context.user_data.pop('responding_to', None)
    return ConversationHandler.END

async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in SUPER_ADMINS:
        await update.message.reply_text("❌ Нет прав")
        return ConversationHandler.END
    
    await update.message.reply_text("👤 Отправьте ID:")
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
                await context.bot.send_message(chat_id=new_admin_id, text="🎉 Вы теперь админ!")
            except:
                pass
    except ValueError:
        await update.message.reply_text("❌ Неверный ID")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено")
    return ConversationHandler.END

def main():
    # Запуск Flask
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    application = Application.builder().token(TOKEN).build()
    
    # Обработчик чатов ПЕРВЫМ
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
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(appeal_handler)
    application.add_handler(response_handler)
    application.add_handler(ban_handler)
    application.add_handler(addadmin_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🚀 Бот запущен с игровой системой!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
