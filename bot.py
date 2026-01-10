import logging
import time
import os
import random
from datetime import datetime
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, InlineQueryHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8546823235:AAFI-3t1SCB9S4PI5izbAAz1XEwHjRlL-6E"
SUPER_ADMINS = {7355737254, 8243127223, 8167127645}
admins = SUPER_ADMINS.copy()

WAITING_APPEAL, WAITING_COMPLAINT, WAITING_ADMIN_ID, WAITING_RESPONSE, WAITING_BAN_DURATION, WAITING_BAN_REASON = range(6)

appeals = {}
appeal_counter = 0
banned_users = {}
active_chats = {}
users_data = {}
active_battles = {}

JOBS = {
    'shawarma': {'name': '🌯 Шаурмист', 'pay': (50, 150), 'cooldown': 1800},
    'watermelon': {'name': '🍉 Продавец арбузов', 'pay': (30, 100), 'cooldown': 1800},
    'taxi': {'name': '🚕 Таксист', 'pay': (100, 200), 'cooldown': 3600},
    'kebab': {'name': '🥙 Шашлычник', 'pay': (70, 180), 'cooldown': 2400},
}

SHOP_ITEMS = {
    'vip': {'name': '👑 VIP статус (7 дней)', 'price': 1000, 'type': 'vip'},
    'faith_boost': {'name': '✨ Усилитель веры +20%', 'price': 500, 'type': 'boost'},
    'lucky_coin': {'name': '🍀 Счастливая монета x2 заработок', 'price': 800, 'type': 'lucky'},
    'remove_cd': {'name': '⚡ Убрать кулдауны (1 час)', 'price': 600, 'type': 'no_cd'},
}

PRAY_COOLDOWN = 1800  # 30 минут

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

def get_user_data(user_id):
    if user_id not in users_data:
        users_data[user_id] = {
            'coins': 100,
            'faith': 50,
            'last_work': {},
            'last_pray': 0,
            'wins': 0,
            'losses': 0,
            'total_earned': 0,
            'items': {},  # {'vip': timestamp, 'no_cd': timestamp}
        }
    return users_data[user_id]

def is_admin(user_id):
    return user_id in admins

def is_user_banned(user_id):
    if user_id in banned_users and time.time() < banned_users[user_id]['until']:
        return True, banned_users[user_id]['reason'], banned_users[user_id]['until']
    elif user_id in banned_users:
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

def has_item_active(user_data, item_type):
    if item_type in user_data['items']:
        if time.time() < user_data['items'][item_type]:
            return True
        else:
            del user_data['items'][item_type]
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    is_banned, reason, until = is_user_banned(user_id)
    if is_banned:
        await update.message.reply_text(f"🚫 Бан до {datetime.fromtimestamp(until).strftime('%d.%m %H:%M')}\nПричина: {reason}")
        return
    
    user_data = get_user_data(user_id)
    vip_status = "👑 VIP" if has_item_active(user_data, 'vip') else ""
    
    keyboard = [
        [InlineKeyboardButton("📋 Жалобы", callback_data="appeals_menu"), InlineKeyboardButton("🎮 Игра", callback_data="game_menu")],
        [InlineKeyboardButton("🛒 Магазин", callback_data="shop_menu"), InlineKeyboardButton("💬 Чат", callback_data="start_chat")]
    ]
    await update.message.reply_text(
        f"👋 Привет! {vip_status}\n\n💰 {user_data['coins']} | 🙏 {user_data['faith']}% | ⚔️ {user_data['wins']}/{user_data['losses']}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_coins = sorted(users_data.items(), key=lambda x: x[1]['coins'], reverse=True)[:10]
    text = "🏆 ТОП ПО ЖИРКОИНАМ:\n\n"
    for i, (uid, data) in enumerate(top_coins, 1):
        try:
            user = await context.bot.get_chat(uid)
            vip = "👑" if has_item_active(data, 'vip') else ""
            text += f"{i}. {user.first_name} {vip}: {data['coins']}💰\n"
        except:
            text += f"{i}. ID{uid}: {data['coins']}💰\n"
    await update.message.reply_text(text)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = get_user_data(update.message.from_user.id)
    await update.message.reply_text(
        f"💰 {user_data['coins']} жиркоинов\n🙏 {user_data['faith']}% веры\n⚔️ {user_data['wins']} побед"
    )

async def work_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    no_cd = is_admin(user_id) or has_item_active(user_data, 'no_cd')
    
    keyboard = []
    for job_key, job in JOBS.items():
        last = user_data['last_work'].get(job_key, 0)
        left = int(job['cooldown'] - (time.time() - last))
        
        if no_cd or left <= 0:
            keyboard.append([InlineKeyboardButton(f"{job['name']} ({job['pay'][0]}-{job['pay'][1]}💰)", callback_data=f"work_{job_key}")])
        else:
            keyboard.append([InlineKeyboardButton(f"{job['name']} ⏳{left//60}м", callback_data="work_cd")])
    
    await update.message.reply_text("💼 Работы:", reply_markup=InlineKeyboardMarkup(keyboard))

async def pray(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)
    
    # Проверка кулдауна (кроме админов)
    if not is_admin(user_id):
        last_pray = user_data.get('last_pray', 0)
        time_left = int(PRAY_COOLDOWN - (time.time() - last_pray))
        if time_left > 0:
            await update.message.reply_text(f"🙏 Молитва доступна через {time_left//60} минут")
            return
    
    faith_gain = random.randint(5, 15)
    user_data['faith'] = min(100, user_data['faith'] + faith_gain)
    coin_bonus = random.randint(0, 50) if user_data['faith'] > 70 else 0
    user_data['coins'] += coin_bonus
    user_data['last_pray'] = time.time()
    
    await update.message.reply_text(
        f"🙏 +{faith_gain}% веры (Всего: {user_data['faith']}%)" + 
        (f"\n💰 Бонус: +{coin_bonus}" if coin_bonus else "")
    )

async def battle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⚔️ 50💰", callback_data="create_battle_50")],
        [InlineKeyboardButton("⚔️ 100💰", callback_data="create_battle_100")],
        [InlineKeyboardButton("⚔️ 200💰", callback_data="create_battle_200")]
    ]
    await update.message.reply_text("⚔️ Выберите ставку:", reply_markup=InlineKeyboardMarkup(keyboard))

async def shop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = get_user_data(update.message.from_user.id)
    keyboard = []
    for item_key, item in SHOP_ITEMS.items():
        keyboard.append([InlineKeyboardButton(f"{item['name']} - {item['price']}💰", callback_data=f"buy_{item_key}")])
    
    await update.message.reply_text(
        f"🛒 МАГАЗИН\n\nВаш баланс: {user_data['coins']}💰",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = get_user_data(update.inline_query.from_user.id)
    vip = "👑" if has_item_active(user_data, 'vip') else ""
    results = [
        InlineQueryResultArticle(
            id='profile',
            title=f'👤 Профиль {vip}',
            description=f'{user_data["coins"]}💰 | {user_data["faith"]}%🙏',
            input_message_content=InputTextMessageContent(
                f"👤 Профиль {vip}\n\n💰 {user_data['coins']}\n🙏 {user_data['faith']}%\n⚔️ {user_data['wins']}/{user_data['losses']}"
            )
        )
    ]
    await update.inline_query.answer(results)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = get_user_data(user_id)
    
    if query.data == "appeals_menu":
        keyboard = [
            [InlineKeyboardButton("Обжаловать", callback_data="appeal")],
            [InlineKeyboardButton("Жалоба", callback_data="complaint")],
            [InlineKeyboardButton("◀️", callback_data="back_to_main")]
        ]
        await query.edit_message_text("📋 Жалобы:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data == "game_menu":
        keyboard = [
            [InlineKeyboardButton("💼 Работа", callback_data="work_menu"), InlineKeyboardButton("⚔️ Битва", callback_data="battle_menu")],
            [InlineKeyboardButton("🙏 Молитва", callback_data="pray"), InlineKeyboardButton("👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton("🏆 Топ", callback_data="tops"), InlineKeyboardButton("◀️", callback_data="back_to_main")]
        ]
        await query.edit_message_text(f"🎮 Игра\n\n💰 {user_data['coins']} | 🙏 {user_data['faith']}%", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data == "shop_menu":
        keyboard = []
        for item_key, item in SHOP_ITEMS.items():
            active = ""
            if has_item_active(user_data, item['type']):
                time_left = int((user_data['items'][item['type']] - time.time()) / 60)
                active = f" ✅ ({time_left}м)"
            keyboard.append([InlineKeyboardButton(f"{item['name']} - {item['price']}💰{active}", callback_data=f"buy_{item_key}")])
        keyboard.append([InlineKeyboardButton("◀️", callback_data="back_to_main")])
        
        await query.edit_message_text(
            f"🛒 МАГАЗИН\n\nВаш баланс: {user_data['coins']}💰",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data.startswith("buy_"):
        item_key = query.data.replace("buy_", "")
        item = SHOP_ITEMS[item_key]
        
        if user_data['coins'] < item['price']:
            await query.answer(f"❌ Недостаточно! Нужно {item['price']}💰", show_alert=True)
            return
        
        user_data['coins'] -= item['price']
        
        # Активация предмета
        if item['type'] == 'vip':
            user_data['items']['vip'] = time.time() + (7 * 86400)  # 7 дней
            await query.answer("👑 VIP активирован на 7 дней!", show_alert=True)
        elif item['type'] == 'boost':
            user_data['faith'] = min(100, user_data['faith'] + 20)
            await query.answer("✨ Вера увеличена на 20%!", show_alert=True)
        elif item['type'] == 'lucky':
            user_data['items']['lucky'] = time.time() + 3600  # 1 час
            await query.answer("🍀 Удвоенный заработок на 1 час!", show_alert=True)
        elif item['type'] == 'no_cd':
            user_data['items']['no_cd'] = time.time() + 3600  # 1 час
            await query.answer("⚡ Кулдауны убраны на 1 час!", show_alert=True)
        
        # Обновляем магазин
        keyboard = []
        for ik, it in SHOP_ITEMS.items():
            active = ""
            if has_item_active(user_data, it['type']):
                time_left = int((user_data['items'][it['type']] - time.time()) / 60)
                active = f" ✅ ({time_left}м)"
            keyboard.append([InlineKeyboardButton(f"{it['name']} - {it['price']}💰{active}", callback_data=f"buy_{ik}")])
        keyboard.append([InlineKeyboardButton("◀️", callback_data="back_to_main")])
        
        await query.edit_message_text(
            f"🛒 МАГАЗИН\n\nВаш баланс: {user_data['coins']}💰",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "work_menu":
        no_cd = is_admin(user_id) or has_item_active(user_data, 'no_cd')
        keyboard = []
        for job_key, job in JOBS.items():
            last = user_data['last_work'].get(job_key, 0)
            left = int(job['cooldown'] - (time.time() - last))
            
            if no_cd or left <= 0:
                keyboard.append([InlineKeyboardButton(f"{job['name']} ({job['pay'][0]}-{job['pay'][1]}💰)", callback_data=f"work_{job_key}")])
            else:
                keyboard.append([InlineKeyboardButton(f"{job['name']} ⏳{left//60}м", callback_data="work_cd")])
        keyboard.append([InlineKeyboardButton("◀️", callback_data="game_menu")])
        await query.edit_message_text("💼 Работы:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data.startswith("work_") and query.data != "work_cd" and query.data != "work_menu":
        job_key = query.data.replace("work_", "")
        job = JOBS[job_key]
        
        # Проверка кулдауна (кроме админов и владельцев no_cd)
        no_cd = is_admin(user_id) or has_item_active(user_data, 'no_cd')
        if not no_cd:
            last = user_data['last_work'].get(job_key, 0)
            if time.time() - last < job['cooldown']:
                await query.answer("⏳ Слишком рано!", show_alert=True)
                return
        
        earnings = random.randint(job['pay'][0], job['pay'][1])
        bonus = int(earnings * (user_data['faith'] / 100))
        
        # Удвоение от lucky coin
        if has_item_active(user_data, 'lucky'):
            earnings *= 2
            bonus *= 2
        
        total = earnings + bonus
        user_data['coins'] += total
        user_data['total_earned'] += total
        user_data['last_work'][job_key] = time.time()
        user_data['faith'] = min(100, user_data['faith'] + random.randint(1, 3))
        
        await query.answer(f"💰 +{total}!", show_alert=True)
        keyboard = [[InlineKeyboardButton("◀️ К работам", callback_data="work_menu")]]
        lucky_text = " 🍀x2" if has_item_active(user_data, 'lucky') else ""
        await query.edit_message_text(
            f"{job['name']}{lucky_text}\n\n💵 {earnings}\n🙏 Бонус: +{bonus}\n💰 Итого: {total}\n\nБаланс: {user_data['coins']}💰",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "pray":
        # Проверка кулдауна (кроме админов)
        if not is_admin(user_id):
            last_pray = user_data.get('last_pray', 0)
            time_left = int(PRAY_COOLDOWN - (time.time() - last_pray))
            if time_left > 0:
                await query.answer(f"🙏 Доступно через {time_left//60} минут", show_alert=True)
                return
        
        faith_gain = random.randint(5, 15)
        coin_bonus = random.randint(0, 50) if user_data['faith'] > 70 else 0
        user_data['faith'] = min(100, user_data['faith'] + faith_gain)
        user_data['coins'] += coin_bonus
        user_data['last_pray'] = time.time()
        
        keyboard = [[InlineKeyboardButton("◀️", callback_data="game_menu")]]
        await query.edit_message_text(
            f"🙏 Молитва принята!\n\n+{faith_gain}% веры (Всего: {user_data['faith']}%)" + 
            (f"\n💰 Бонус: +{coin_bonus}" if coin_bonus else ""),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "profile":
        winrate = (user_data['wins'] / (user_data['wins'] + user_data['losses']) * 100) if (user_data['wins'] + user_data['losses']) > 0 else 0
        vip_status = "👑 VIP" if has_item_active(user_data, 'vip') else ""
        admin_status = "⭐ ADMIN" if is_admin(user_id) else ""
        
        keyboard = [[InlineKeyboardButton("◀️", callback_data="game_menu")]]
        await query.edit_message_text(
            f"👤 Профиль {vip_status} {admin_status}\n\n"
            f"💰 {user_data['coins']}\n"
            f"💵 Заработано: {user_data['total_earned']}\n"
            f"🙏 Вера: {user_data['faith']}%\n\n"
            f"⚔️ Побед: {user_data['wins']}\n"
            f"💀 Поражений: {user_data['losses']}\n"
            f"📊 Винрейт: {winrate:.1f}%",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    elif query.data == "tops":
        top_coins = sorted(users_data.items(), key=lambda x: x[1]['coins'], reverse=True)[:5]
        text = "🏆 ТОП 5:\n\n"
        for i, (uid, data) in enumerate(top_coins, 1):
            try:
                user = await context.bot.get_chat(uid)
                vip = "👑" if has_item_active(data, 'vip') else ""
                text += f"{i}. {user.first_name} {vip}: {data['coins']}💰\n"
            except:
                text += f"{i}. ID{uid}: {data['coins']}💰\n"
        keyboard = [[InlineKeyboardButton("◀️", callback_data="game_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data == "battle_menu":
        # Показать доступные битвы
        available_battles = []
        for battle_id, battle in active_battles.items():
            if battle['player2'] is None and battle['player1'] != user_id:
                available_battles.append((battle_id, battle))
        
        keyboard = []
        if available_battles:
            for battle_id, battle in available_battles[:3]:  # Показываем до 3 битв
                keyboard.append([InlineKeyboardButton(
                    f"⚔️ {battle['player1_name']} - {battle['bet']}💰",
                    callback_data=f"join_battle_{battle_id}"
                )])
        
        keyboard.append([InlineKeyboardButton("➕ Создать битву", callback_data="create_battle_menu")])
        keyboard.append([InlineKeyboardButton("◀️", callback_data="game_menu")])
        
        await query.edit_message_text("⚔️ Битвы:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data == "create_battle_menu":
        keyboard = [
            [InlineKeyboardButton("⚔️ 50💰", callback_data="create_battle_50")],
            [InlineKeyboardButton("⚔️ 100💰", callback_data="create_battle_100")],
            [InlineKeyboardButton("⚔️ 200💰", callback_data="create_battle_200")],
            [InlineKeyboardButton("◀️", callback_data="battle_menu")]
        ]
        await query.edit_message_text("⚔️ Выберите ставку:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    elif query.data.startswith("create_battle_"):
        bet = int(query.data.split("_")[2])
        if user_data['coins'] < bet:
            await query.answer(f"❌ Нужно {bet}💰", show_alert=True)
            return
        
        battle_id = f"{user_id}_{int(time.time())}"
        active_battles[battle_id] = {
            'player1': user_id,
            'player1_name': query.from_user.first_name,
            'player2': None,
            'bet': bet
        }
        user_data['coins'] -= bet
        
        await query.edit_message_text(
            f"⚔️ Битва создана!\n\n💰 Ставка: {bet}\n👤 {query.from_user.first_name}\n\nОжидание соперника..."
        )
        
        # Уведомляем других игроков
        for uid in list(users_data.keys())[:10]:  # Уведомляем первых 10
            if uid != user_id:
                try:
                    keyboard_notif = [[InlineKeyboardButton("⚔️ Принять бой!", callback_data=f"join_battle_{battle_id}")]]
                    await context.bot.send_message(
                        uid,
                        f"⚔️ Новая битва!\n\n👤 {query.from_user.first_name}\n💰 {bet}",
                        reply_markup=InlineKeyboardMarkup(keyboard_notif)
                    )
                except:
                    pass
        return
    
    elif query.data.startswith("join_battle_"):
        battle_id = query.data.replace("join_battle_", "")
        if battle_id not in active_battles:
            await query.answer("❌ Битва уже завершена", show_alert=True)
            return
        
        battle = active_battles[battle_id]
        bet = battle['bet']
        
        if user_data['coins'] < bet:
            await query.answer(f"❌ Нужно {bet}💰", show_alert=True)
            return
        
        if battle['player1'] == user_id:
            await query.answer("❌ Это ваша битва!", show_alert=True)
            return
        
        user_data['coins'] -= bet
        player1_data = get_user_data(battle['player1'])
        
        # Бой!
        p1_power = random.randint(1, 100) + player1_data['faith']
        p2_power = random.randint(1, 100) + user_data['faith']
        
        winner_id = battle['player1'] if p1_power > p2_power else user_id
        loser_id = user_id if winner_id == battle['player1'] else battle['player1']
        
        winner_data = get_user_data(winner_id)
        loser_data = get_user_data(loser_id)
        
        prize = bet * 2
        winner_data['coins'] += prize
        winner_data['wins'] += 1
        loser_data['losses'] += 1
        
        winner_name = battle['player1_name'] if winner_id == battle['player1'] else query.from_user.first_name
        loser_name = query.from_user.first_name if winner_id == battle['player1'] else battle['player1_name']
        
        result = (
            f"⚔️ БИТВА ЗАВЕРШЕНА!\n\n"
            f"{battle['player1_name']} (💪{p1_power}) VS {query.from_user.first_name} (💪{p2_power})\n\n"
            f"🏆 Победитель: {winner_name}\n"
            f"💰 Приз: {prize}\n\n"
            f"💸 Проигравший: {loser_name}"
        )
        
        try:
            await context.bot.send_message(battle['player1'], result)
        except:
            pass
        
        try:
            await query.edit_message_text(result)
        except:
            await context.bot.send_message(user_id, result)
        
        del active_battles[battle_id]
        return
    
    elif query.data == "back_to_main":
        vip_status = "👑 VIP" if has_item_active(user_data, 'vip') else ""
        keyboard = [
            [InlineKeyboardButton("📋 Жалобы", callback_data="appeals_menu"), InlineKeyboardButton("🎮 Игра", callback_data="game_menu")],
            [InlineKeyboardButton("🛒 Магазин", callback_data="shop_menu"), InlineKeyboardButton("💬 Чат", callback_data="start_chat")]
        ]
        await query.edit_message_text(
            f"💰 {user_data['coins']} | 🙏 {user_data['faith']}% {vip_status}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Остальные handlers для жалоб и чатов (как раньше)
    if query.data == "appeal":
        await query.edit_message_text("📝 Опишите наказание:")
        return WAITING_APPEAL
    elif query.data == "complaint":
        await query.edit_message_text("📝 Опишите жалобу:")
        return WAITING_COMPLAINT
    elif query.data == "start_chat":
        if user_id in active_chats:
            await query.edit_message_text("💬 У вас уже есть чат")
            return
        for admin_id in admins:
            try:
                await context.bot.send_message(admin_id, f"💬 @{query.from_user.username or query.from_user.first_name} (ID: {user_id}) запросил чат", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Начать", callback_data=f"accept_chat_{user_id}")]]))
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
    seconds, readable = parse_duration(update.message.text)
    if not seconds:
        await update.message.reply_text("❌ Формат: 1m, 1h, 1d")
        return WAITING_BAN_DURATION
    context.user_data['ban_duration'] = seconds
    context.user_data['ban_duration_readable'] = readable
    await update.message.reply_text(f"✅ {readable}\n\n📝 Причина:")
    return WAITING_BAN_REASON

async def receive_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    appeal_id = context.user_data.get('banning_appeal')
    if not appeal_id or appeal_id not in appeals:
        return ConversationHandler.END
    user_id = appeals[appeal_id]['user_id']
    duration = context.user_data.get('ban_duration')
    readable = context.user_data.get('ban_duration_readable')
    ban_until = time.time() + duration
    banned_users[user_id] = {'until': ban_until, 'reason': update.message.text}
    try:
        await context.bot.send_message(user_id, f"🚫 Бан на {readable}\nДо: {datetime.fromtimestamp(ban_until).strftime('%d.%m %H:%M')}\n\nПричина: {update.message.text}")
    except:
        pass
    await update.message.reply_text(f"✅ Забанен на {readable}")
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
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("top", top))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("work", work_cmd))
    application.add_handler(CommandHandler("battle", battle_cmd))
    application.add_handler(CommandHandler("pray", pray))
    application.add_handler(CommandHandler("shop", shop_cmd))
    
    application.add_handler(InlineQueryHandler(inline_query))
    
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
    
    application.add_handler(appeal_handler)
    application.add_handler(response_handler)
    application.add_handler(ban_handler)
    application.add_handler(addadmin_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🚀 Бот запущен с магазином!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
