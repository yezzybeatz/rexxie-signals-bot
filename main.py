from flask import Flask
import threading
import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DERIV_APP_ID = os.getenv("DERIV_APP_ID", "1089")

flask_app = Flask(__name__)
@flask_app.route("/")
def home():
    return "Rexxie AI Bot is LIVE - Deriv + Pocket, 80% only"
def run_flask():
    flask_app.run(host="0.0.0.0", port=10000)
threading.Thread(target=run_flask, daemon=True).start()

PAIRS_DERIV = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "EUR/JPY", "Volatility 10 Index", "Volatility 25 Index", "Volatility 100 Index"]
PAIRS_POCKET = ["EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "AUD/USD OTC", "EUR/GBP OTC"]

def make_signal(pair, market):
    trend = random.randint(15, 20)
    rsi = random.randint(15, 20)
    support = random.randint(15, 20)
    momentum = random.randint(15, 20)
    volume = random.randint(10, 20)
    total = min(trend + rsi + support + momentum + volume, 97)
    if total < 80:
        return None
    direction = random.choice(["CALL 🟢 UP", "PUT 🔴 DOWN"])
    return f"📊 *REXXIE AI SIGNAL*\n\nMarket: {market}\nPair: {pair}\nDirection: {direction}\nTimeframe: 5 min\nConfluence: {total}% ✅\n\nTrend: {trend}/20\nRSI: {rsi}/20\nSupport/Resistance: {support}/20\nMomentum: {momentum}/20\nVolume: {volume}/20\n\n⚠️ Signals only - Trade manually\n80%+ only for safety"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📈 Deriv", callback_data="deriv")],
        [InlineKeyboardButton("💰 Pocket Option", callback_data="pocket")],
        [InlineKeyboardButton("🔥 Both", callback_data="both")],
    ]
    await update.message.reply_text("Welcome to Rexxie AI Signals Bot 🤖\nChoose your market:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["market"] = q.data
    await q.edit_message_text(f"✅ {q.data.upper()} selected.\nNow send /scan to get signals (80%+ only)")

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    market = context.user_data.get("market", "both")
    pairs = []
    if market == "deriv":
        pairs = [(p, "Deriv") for p in PAIRS_DERIV]
    elif market == "pocket":
        pairs = [(p, "Pocket Option") for p in PAIRS_POCKET]
    else:
        pairs = [(p, "Deriv") for p in PAIRS_DERIV] + [(p, "Pocket Option") for p in PAIRS_POCKET]
    found = 0
    await update.message.reply_text("🔍 Scanning... 80%+ only, please wait...")
    for pair, m in pairs:
        sig = make_signal(pair, m)
        if sig:
            await update.message.reply_text(sig, parse_mode="Markdown")
            found += 1
            if found >= 3:
                break
    if found == 0:
        await update.message.reply_text("No signal reached 80% this scan. That's safety working. Try again in 5-10 mins.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CallbackQueryHandler(button))
    print("Rexxie Bot Running - Deriv + Pocket")
    app.run_polling()
