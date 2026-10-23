import os
import random
import json
import subprocess
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from PIL import Image, ImageDraw, ImageFont

TOKEN = os.environ.get("BOT_TOKEN")
SCORES_FILE = "scores.json"

SNAKES_AND_LADDERS = {
    3: 22, 5: 8, 11: 26, 20: 29, 28: 51, 36: 44, 40: 62, 51: 67, 63: 81, 71: 92,
    17: 4, 24: 7, 38: 19, 48: 26, 56: 33, 64: 46, 72: 54, 87: 66, 93: 73, 95: 75, 98: 79
}

EMOJIS = ["🔴", "🔵", "🟢", "🟡", "🟣"]
COLORS = ["red", "blue", "green", "gold", "purple"]

games = {}

# ---------- مدیریت امتیاز ----------
def load_scores():
    if os.path.exists(SCORES_FILE):
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_scores(scores):
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True, capture_output=True)
        subprocess.run(["git", "add", SCORES_FILE], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Update scores"], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
    except Exception as e:
        print(f"خطا در ذخیره‌سازی در گیت‌هاب: {e}")

def get_level(points):
    if points >= 150: return "🏆 افسانه"
    if points >= 70: return "🥇 استاد"
    if points >= 30: return "🥈 حرفه‌ای"
    return "🥉 تازه‌کار"

def add_win(user_id, name):
    scores = load_scores()
    uid = str(user_id)
    if uid not in scores:
        scores[uid] = {"name": name, "points": 0, "wins": 0}
    scores[uid]["points"] += 10
    scores[uid]["wins"] += 1
    scores[uid]["name"] = name
    save_scores(scores)
    return scores[uid]

# ---------- ساخت عکس صفحه بازی ----------
def generate_board_image(players):
    cell_size = 60
    board_size = cell_size * 10
    img = Image.new("RGB", (board_size, board_size), "white")
    draw = ImageDraw.Draw(img)

    for i in range(1, 101):
        row = (i - 1) // 10
        col = (i - 1) % 10
        if row % 2 == 1:
            col = 9 - col
        
        x0 = col * cell_size
        y0 = (9 - row) * cell_size
        x1 = x0 + cell_size
        y1 = y0 + cell_size
        
        fill_color = "white"
        if i in SNAKES_AND_LADDERS:
            if SNAKES_AND_LADDERS[i] > i:
                fill_color = "#d4edda"
            else:
                fill_color = "#f8d7da"
                
        draw.rectangle([x0, y0, x1, y1], outline="black", fill=fill_color)
        # شماره خانه‌ها
        draw.text((x0 + 5, y0 + 5), str(i), fill="black")

        player_index = 0
        for uid, p in players.items():
            if p["pos"] == i:
                # کشیدن مهره رنگی
                color = COLORS[player_index % len(COLORS)]
                px = x0 + cell_size / 2
                py = y0 + cell_size / 2
                r = 12
                draw.ellipse([px - r, py - r, px + r, py + r], fill=color, outline="black")
                player_index += 1

    bio = io.BytesIO()
    bio.name = 'board.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio

# ---------- منطق بازی ----------
def get_keyboard(is_creator=False):
    keyboard = [[InlineKeyboardButton("🎲 انداختن تاس", callback_data="roll_dice")]]
    if is_creator:
        keyboard.append([InlineKeyboardButton("🛑 پایان بازی", callback_data="end_game")])
    return InlineKeyboardMarkup(keyboard)

async def timeout_turn(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    if chat_id not in games or games[chat_id]["state"] != "playing":
        return
    
    current_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
    current_name = games[chat_id]["players"][current_id]["name"]
    
    games[chat_id]["turn_index"] = (games[chat_id]["turn_index"] + 1) % len(games[chat_id]["order"])
    next_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
    next_name = games[chat_id]["players"][next_id]["name"]
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ زمان {current_name} تمام شد! نوبت به {next_name} رسید.",
        reply_markup=get_keyboard(is_creator=True)
    )
    context.job_queue.run_once(timeout_turn, 30, chat_id=chat_id, name=str(chat_id))

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("این بازی فقط در گروه قابل اجراست!")
        return
    if chat_id in games and games[chat_id]["state"] == "playing":
        await update.message.reply_text("یک بازی در جریان است!")
        return
        
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()

    games[chat_id] = {
        "players": {}, 
        "order": [], 
        "turn_index": 0, 
        "state": "signup",
        "creator_id": user.id
    }
    await update.message.reply_text(
        f"🎲 بازی مار و پله توسط {user.first_name} ساخته شد!\n"
        "برای ورود /join را بزنید.\n"
        "فقط سازنده می‌تواند با /start_game بازی را شروع کند."
    )

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in games or games[chat_id]["state"] != "signup":
        await update.message.reply_text("ثبت‌نام فعالی وجود ندارد.")
        return
    if user.id in games[chat_id]["players"]:
        await update.message.reply_text("شما قبلاً وارد شده‌اید!")
        return
    if len(games[chat_id]["players"]) >= 5:
        await update.message.reply_text("ظرفیت پر است! حداکثر ۵ نفر.")
        return
    
    # اختصاص ایموجی بر اساس تعداد فعلی
    emoji = EMOJIS[len(games[chat_id]["players"])]
    games[chat_id]["players"][user.id] = {"name": user.first_name, "pos": 0, "emoji": emoji}
    games[chat_id]["order"].append(user.id)
    
    await update.message.reply_text(
        f"✅ {user.first_name} با مهره {emoji} وارد بازی شد.\n"
        f"تعداد: {len(games[chat_id]['players'])}"
    )

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in games or games[chat_id]["state"] != "signup":
        await update.message.reply_text("بازی در حال ثبت‌نام نیست.")
        return
    
    if user.id != games[chat_id]["creator_id"]:
        await update.message.reply_text("فقط سازنده بازی اجازه شروع دارد!")
        return
        
    if len(games[chat_id]["players"]) < 2:
        await update.message.reply_text("حداقل ۲ نفر لازم است!")
        return
        
    games[chat_id]["state"] = "playing"
    games[chat_id]["turn_index"] = 0
    first_id = games[chat_id]["order"][0]
    first_name = games[chat_id]["players"][first_id]["name"]
    
    board_img = generate_board_image(games[chat_id]["players"])
    await update.message.reply_photo(
        photo=board_img,
        caption=f"🎮 بازی شروع شد!\nنوبت اول: {first_name} (۳۰ ثانیه فرصت داری!)\n",
        reply_markup=get_keyboard(is_creator=True)
    )
    
    context.job_queue.run_once(timeout_turn, 30, chat_id=chat_id, name=str(chat_id))

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    user = query.from_user
    data = query.data

    if chat_id not in games:
        return

    # --- دکمه پایان بازی ---
    if data == "end_game":
        if user.id != games[chat_id]["creator_id"]:
            await query.answer("فقط سازنده بازی می‌تواند آن را تمام کند!", show_alert=True)
            return
        
        games[chat_id]["state"] = "ended"
        current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in current_jobs:
            job.schedule_removal()
        
        await query.edit_message_caption(
            caption="🛑 بازی توسط سازنده پایان یافت.",
            reply_markup=None
        )
        return

    # --- دکمه انداختن تاس ---
    if data == "roll_dice":
        if games[chat_id]["state"] != "playing":
            return
        if user.id not in games[chat_id]["players"]:
            await query.answer("شما در این بازی نیستید!", show_alert=True)
            return
            
        current_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
        if user.id != current_id:
            current_name = games[chat_id]["players"][current_id]["name"]
            await query.answer(f"نوبت شما نیست! نوبت {current_name} است.", show_alert=True)
            return

        current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in current_jobs:
            job.schedule_removal()

        roll = random.randint(1, 6)
        player = games[chat_id]["players"][user.id]
        old_pos = player["pos"]
        new_pos = old_pos + roll
        
        msg = f"🎲 {player['emoji']} {user.first_name} تاس {roll} آورد.\n"
        
        if new_pos > 100:
            msg += f"❌ نیاز به دقیقاً {100 - old_pos} بود. سر جایت ماندی.\n"
            new_pos = old_pos
        elif new_pos in SNAKES_AND_LADDERS:
            if SNAKES_AND_LADDERS[new_pos] > new_pos:
                msg += f"🪜 پله! از {new_pos} پریدی به {SNAKES_AND_LADDERS[new_pos]}.\n"
            else:
                msg += f"🐍 مار! از {new_pos} سقوط کردی به {SNAKES_AND_LADDERS[new_pos]}.\n"
            new_pos = SNAKES_AND_LADDERS[new_pos]
        else:
             msg += f"➡️ از {old_pos} به {new_pos} رفتی.\n"

        player["pos"] = new_pos

        if new_pos == 100:
            games[chat_id]["state"] = "ended"
            updated = add_win(user.id, user.first_name)
            level = get_level(updated["points"])
            
            board_img = generate_board_image(games[chat_id]["players"])
            await query.message.reply_photo(
                photo=board_img,
                caption=msg + f"\n🏆 {user.first_name} برنده شد!\n"
                f"➕ ۱۰ امتیاز گرفت.\n"
                f"مجموع: {updated['points']} | سطح: {level}"
            )
            await query.edit_message_reply_markup(reply_markup=None)
            return

        games[chat_id]["turn_index"] = (games[chat_id]["turn_index"] + 1) % len(games[chat_id]["order"])
        next_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
        next_name = games[chat_id]["players"][next_id]["name"]
        next_emoji = games[chat_id]["players"][next_id]["emoji"]
        
        board_img = generate_board_image(games[chat_id]["players"])
        msg += f"\n⏳ نوبت: {next_emoji} {next_name} (۳۰ ثانیه)"
        
        await query.message.reply_photo(
            photo=board_img,
            caption=msg,
            reply_markup=get_keyboard(is_creator=True)
        )
        # حذف دکمه‌های پیام قبلی
        await query.edit_message_reply_markup(reply_markup=None)
        
        context.job_queue.run_once(timeout_turn, 30, chat_id=chat_id, name=str(chat_id))

# ---------- دستورات امتیاز ----------
async def my_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    scores = load_scores()
    uid = str(user.id)
    if uid not in scores:
        await update.message.reply_text("هنوز امتیازی ندارید! یک بازی ببرید.")
        return
    s = scores[uid]
    await update.message.reply_text(f"👤 {user.first_name}\nامتیاز: {s['points']}\nبردها: {s['wins']}\nسطح: {get_level(s['points'])}")

async def top_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scores = load_scores()
    if not scores:
        await update.message.reply_text("هنوز کسی امتیاز ندارد!")
        return
    sorted_scores = sorted(scores.values(), key=lambda x: x["points"], reverse=True)[:10]
    lines = ["🏅 جدول برترین‌ها:"]
    for i, s in enumerate(sorted_scores, 1):
        lines.append(f"{i}. {s['name']} - {s['points']} امتیاز ({get_level(s['points'])})")
    await update.message.reply_text("\n".join(lines))

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("newgame", new_game))
    app.add_handler(CommandHandler("join", join_game))
    app.add_handler(CommandHandler("start_game", start_game))
    app.add_handler(CommandHandler("myscore", my_score))
    app.add_handler(CommandHandler("top", top_players))
    
    app.add_handler(CallbackQueryHandler(handle_buttons, pattern="^(roll_dice|end_game)$"))
    
    print("ربات تصویری مار و پله در حال اجراست...")
    app.run_polling()
