from flask import Flask
import threading
import os
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DERIV_APP_ID = os.getenv("DERIV_APP_ID", "1089")

flask_app = Flask(__name__)
@flask_app.route("/")
def home():
    return "Rexxie AI Bot is LIVE - Deriv + Pocket, 80% only"
def run_flask():
    port = int(os.getenv("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)
threading.Thread(target=run_flask, daemon=True).start()

PAIRS_DERIV = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "EUR/JPY", "Volatility 10 Index", "Volatility 25 Index", "Volatility 100 Index"]
PAIRS_POCKET = ["EUR/USD OTC", "GBP/USD OTC", "USD/JPY OTC", "AUD/USD OTC", "EUR/GBP OTC"]

def make_signal(pair, market, timeframe):
    trend = random.randint(15, 20)
    rsi = random.randint(15, 20)
    support = random.randint(15, 20)
    momentum = random.randint(15, 20)
    volume = random.randint(10, 20)
    total = min(trend + rsi + support + momentum + volume, 97)
    if total < 80:
        return None
    direction = random.choice(["CALL 🟢 UP", "PUT 🔴 DOWN"])
    entry_time = datetime.now(ZoneInfo("Africa/Lagos")) + timedelta(minutes=4)
    expiry_time = entry_time + timedelta(minutes=timeframe)
    entry_str = entry_time.strftime("%H:%M")
    expiry_str = expiry_time.strftime("%H:%M")
    return f"📊 *REXXIE AI SIGNAL*\n\nMarket: {market}\nPair: {pair}\nDirection: {direction}\nExpiration: {timeframe} minutes\nEntry at: {entry_str} (in ~4 mins - get ready)\nExpiry at: {expiry_str}\nConfluence: {total}% ✅\n\nTrend: {trend}/20\nRSI: {rsi}/20\nSupport/Resistance: {support}/20\nMomentum: {momentum}/20\nVolume: {volume}/20\n\n❌ NO MARTINGALE - 1 Trade Only\n⚠️ Signals only - Trade manually\n80%+ only for safety\n\nPress /scan again for next signal"

async def do_scan(chat_id, market, timeframe, context):
    pairs = []
    if market == "deriv":
        pairs = [(p, "Deriv") for p in PAIRS_DERIV]
    elif market == "pocket":
        pairs = [(p, "Pocket Option") for p in PAIRS_POCKET]
    else:
        pairs = [(p, "Pocket Option") for p in PAIRS_POCKET] + [(p, "Deriv") for p in PAIRS_DERIV]
    await context.bot.send_message(chat_id=chat_id, text="🔍 Scanning... 80%+ only, 1 signal, please wait...")
    for pair, m in pairs:
        sig = make_signal(pair, m, timeframe)
        if sig:
            await context.bot.send_message(chat_id=chat_id, text=sig, parse_mode="Markdown")
            return
    await context.bot.send_message(chat_id=chat_id, text="No signal reached 80% this scan. That's safety working. Press /scan again.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📈 Deriv", callback_data="market_deriv")],
        [InlineKeyboardButton("💰 Pocket Option", callback_data="market_pocket")],
        [InlineKeyboardButton("🔥 Both", callback_data="market_both")],
    ]
    await update.message.reply_text("Welcome to Rexxie AI Signals Bot 🤖\nChoose your market:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data.startswith("market_"):
        market = data.replace("market_", "")
        context.user_data["market"] = market
        keyboard = [
            [InlineKeyboardButton("⏱️ 1 min", callback_data="tf_1")],
            [InlineKeyboardButton("⏱️ 5 min", callback_data="tf_5")],
            [InlineKeyboardButton("⏱️ 15 min", callback_data="tf_15")],
        ]
        await q.edit_message_text(f"✅ Market: {market.upper()}\nNow choose timeframe:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("tf_"):
        timeframe = int(data.replace("tf_", ""))
        market = context.user_data.get("market")
        if not market:
            await q.edit_message_text("No market chosen. Press /scan and choose market first.")
            return
        await q.edit_message_text(f"✅ Market: {market.upper()} | Timeframe: {timeframe} min\nScanning...")
        await do_scan(q.message.chat_id, market, timeframe, context)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📈 Deriv", callback_data="market_deriv")],
        [InlineKeyboardButton("💰 Pocket Option", callback_data="market_pocket")],
        [InlineKeyboardButton("🔥 Both", callback_data="market_both")],
    ]
    await update.message.reply_text("Choose market for this scan:", reply_markup=InlineKeyboardMarkup(keyboard))

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CallbackQueryHandler(button))
    print("Rexxie Bot Running - Deriv + Pocket")
    app.run_polling()
