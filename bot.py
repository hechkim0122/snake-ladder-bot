import os
import random
import json
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# توکن از متغیرهای محیطی خوانده می‌شود (امنیت بالا)
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
    # --- بخش جدید: کامیت خودکار فایل امتیازها به گیت‌هاب ---
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", SCORES_FILE], check=True)
        subprocess.run(["git", "commit", "-m", "Update scores"], check=True)
        subprocess.run(["git", "push"], check=True)
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
def move_player(pos, roll):
    new_pos = pos + roll
    if new_pos > 100:
        return pos
    if new_pos in SNAKES_AND_LADDERS:
        new_pos = SNAKES_AND_LADDERS[new_pos]
    return new_pos

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("این بازی فقط در گروه قابل اجراست!")
        return
    if chat_id in games and games[chat_id]["state"] == "playing":
        await update.message.reply_text("یک بازی در جریان است!")
        return
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
    await update.message.reply_text(f"🎮 بازی شروع شد!\nنوبت اول: {first_name}\n/roll بزنید.")

async def roll_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    if chat_id not in games or games[chat_id]["state"] != "playing":
        await update.message.reply_text("بازی فعالی وجود ندارد.")
        return
    if user.id not in games[chat_id]["players"]:
        await update.message.reply_text("شما در این بازی نیستید!")
        return
    current_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
    if user.id != current_id:
        current_name = games[chat_id]["players"][current_id]["name"]
        await update.message.reply_text(f"نوبت شما نیست! نوبت {current_name} است.")
        return

    roll = random.randint(1, 6)
    player = games[chat_id]["players"][user.id]
    old_pos = player["pos"]
    new_pos = move_player(old_pos, roll)
    player["pos"] = new_pos

    msg = f"🎲 {user.first_name} تاس {roll} آورد و از {old_pos} به {new_pos} رفت."
    if new_pos in SNAKES_AND_LADDERS and old_pos + roll in SNAKES_AND_LADDERS:
        if SNAKES_AND_LADDERS[old_pos + roll] > old_pos + roll:
            msg += " 🪜 پله!"
        else:
            msg += " 🐍 مار!"

    if new_pos == 100:
        games[chat_id]["state"] = "ended"
        updated = add_win(user.id, user.first_name)
        level = get_level(updated["points"])
        await update.message.reply_text(
            msg + f"\n\n🏆 {user.first_name} برنده شد!\n"
            f"➕ ۱۰ امتیاز گرفت.\n"
            f"مجموع امتیاز: {updated['points']} | سطح: {level}"
        )
        return

    games[chat_id]["turn_index"] = (games[chat_id]["turn_index"] + 1) % len(games[chat_id]["order"])
    next_id = games[chat_id]["order"][games[chat_id]["turn_index"]]
    next_name = games[chat_id]["players"][next_id]["name"]
    await update.message.reply_text(msg + f"\n\nنوبت: {next_name}")

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
    app.add_handler(CommandHandler("roll", roll_dice))
    app.add_handler(CommandHandler("myscore", my_score))
    app.add_handler(CommandHandler("top", top_players))
    print("ربات مار و پله در حال اجراست...")
    app.run_polling()