import os
import random
import json
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = os.environ.get("BOT_TOKEN")
SCORES_FILE = "scores.json"

SNAKES_AND_LADDERS = {
    3: 22, 5: 8, 11: 26, 20: 29,
    28: 51, 36: 44, 40: 62, 51: 67, 63: 81, 71: 92,
    17: 4, 24: 7, 38: 19, 48: 26, 56: 33, 64: 46,
    72: 54, 87: 66, 93: 73, 95: 75, 98: 79
}

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

# ---------- منطق بازی ----------
def get_keyboard():
    keyboard = [[InlineKeyboardButton("🎲 انداختن تاس", callback_data="roll_dice")]]
    return InlineKeyboardMarkup(keyboard)

def build_scoreboard(chat_id):
    players = games[chat_id]["players"]
    # مرتب‌سازی بر اساس موقعیت
    sorted_players = sorted(players.values(), key=lambda x: x["pos"], reverse=True)
    board = "📊 **جدول موقعیت‌ها:**\n"
    for p in sorted_players:
        board += f"👤 {p['name']}: خانه {p['pos']}\n"
    return board

async def timeout_turn(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    if chat_id not in games or games[chat_id]["state"] != "playing":
        return
    current_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
    current_name = games[chat_id]["players"][current_id]["name"]
    
    # رفتن به نفر بعدی
    games[chat_id]["turn_index"] = (games[chat_id]["turn_index"] + 1) % len(games[chat_id]["order"])
    next_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
    next_name = games[chat_id]["players"][next_id]["name"]
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏰ زمان {current_name} تمام شد! نوبت به {next_name} رسید.",
        reply_markup=get_keyboard()
    )
    # زمان‌سنج جدید برای نفر بعدی
    context.job_queue.run_once(timeout_turn, 30, chat_id=chat_id, name=str(chat_id))

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("این بازی فقط در گروه قابل اجراست!")
        return
    if chat_id in games and games[chat_id]["state"] == "playing":
        await update.message.reply_text("یک بازی در جریان است!")
        return
        
    # پاک کردن زمان‌سنج‌های قبلی
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()

    games[chat_id] = {"players": {}, "order": [], "turn_index": 0, "state": "signup"}
    await update.message.reply_text(
        "🎲 بازی مار و پله شروع شد!\n"
        "برای ورود /join را بزنید (۲ تا ۵ نفر).\n"
        "وقتی همه وارد شدند، /start_game را بزنید."
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
    games[chat_id]["players"][user.id] = {"name": user.first_name, "pos": 0}
    games[chat_id]["order"].append(user.id)
    await update.message.reply_text(f"✅ {user.first_name} وارد بازی شد.\nتعداد: {len(games[chat_id]['players'])}")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games or games[chat_id]["state"] != "signup":
        await update.message.reply_text("بازی در حال ثبت‌نام نیست.")
        return
    if len(games[chat_id]["players"]) < 2:
        await update.message.reply_text("حداقل ۲ نفر لازم است!")
        return
    games[chat_id]["state"] = "playing"
    games[chat_id]["turn_index"] = 0
    first_id = games[chat_id]["order"][0]
    first_name = games[chat_id]["players"][first_id]["name"]
    
    await update.message.reply_text(
        f"🎮 بازی شروع شد!\nنوبت اول: {first_name} (۳۰ ثانیه فرصت داری!)\n",
        reply_markup=get_keyboard()
    )
    
    # شروع زمان‌سنج
    context.job_queue.run_once(timeout_turn, 30, chat_id=chat_id, name=str(chat_id))

async def handle_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    user = query.from_user

    if chat_id not in games or games[chat_id]["state"] != "playing":
        await query.edit_message_text("بازی فعالی وجود ندارد.")
        return
    if user.id not in games[chat_id]["players"]:
        await query.answer("شما در این بازی نیستید!", show_alert=True)
        return
        
    current_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
    if user.id != current_id:
        current_name = games[chat_id]["players"][current_id]["name"]
        await query.answer(f"نوبت شما نیست! نوبت {current_name} است.", show_alert=True)
        return

    # حذف زمان‌سنج فعلی چون تاس انداخت
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()

    roll = random.randint(1, 6)
    player = games[chat_id]["players"][user.id]
    old_pos = player["pos"]
    new_pos = old_pos + roll
    
    msg = f"🎲 {user.first_name} تاس {roll} آورد.\n"
    
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
        await query.edit_message_text(
            msg + f"\n🏆 {user.first_name} برنده شد!\n"
            f"➕ ۱۰ امتیاز گرفت.\n"
            f"مجموع: {updated['points']} | سطح: {level}"
        )
        return

    # رفتن به نفر بعدی
    games[chat_id]["turn_index"] = (games[chat_id]["turn_index"] + 1) % len(games[chat_id]["order"])
    next_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
    next_name = games[chat_id]["players"][next_id]["name"]
    
    board = build_scoreboard(chat_id)
    msg += f"\n{board}\n"
    msg += f"⏳ نوبت: {next_name} (۳۰ ثانیه)"
    
    await query.edit_message_text(msg, reply_markup=get_keyboard())
    
    # شروع زمان‌سنج برای نفر بعدی
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
    
    # هندلر برای دکمه شیشه‌ای
    app.add_handler(CallbackQueryHandler(handle_roll, pattern="roll_dice"))
    
    print("ربات حرفه‌ای مار و پله در حال اجراست...")
    app.run_polling()
