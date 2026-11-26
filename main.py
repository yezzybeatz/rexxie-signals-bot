import os, json, statistics
from datetime import datetime, timedelta
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import websocket
from flask import Flask
import threading

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
APP_ID = "1089"
LAGOS = pytz.timezone("Africa/Lagos")

_keep = Flask(__name__)
@_keep.route("/")
def _home():
    return "Rexxie Bot LIVE"
def _run_keep():
    _keep.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
threading.Thread(target=_run_keep, daemon=True).start()

DERIV_PAIRS = ["R_100","R_75","R_50","JD100","frxEURUSD","frxGBPJPY","frxXAUUSD","frxBTCUSD"]
POCKET_PAIRS = ["frxEURUSD","frxGBPUSD","frxGBPJPY","frxXAUUSD","frxBTCUSD","frxEURJPY","frxAUDUSD"]
NAMES = {"R_100":"Volatility 100","R_75":"Volatility 75","R_50":"Volatility 50","JD100":"Jump 100","frxEURUSD":"EUR/USD","frxGBPUSD":"GBP/USD","frxGBPJPY":"GBP/JPY","frxXAUUSD":"GOLD","frxBTCUSD":"BTC/USD","frxEURJPY":"EUR/JPY","frxAUDUSD":"AUD/USD"}
user_choice = {}

def get_candles(symbol, granularity, count=25):
    try:
        ws = websocket.create_connection(f"wss://ws.binaryws.com/websockets/v3?app_id={APP_ID}", timeout=8, header=["User-Agent: Mozilla/5.0", "Origin: https://app.deriv.com"])
        ws.send(json.dumps({"ticks_history": symbol, "end": "latest", "count": count, "style": "candles", "granularity": granularity}))
        r = json.loads(ws.recv()); ws.close()
        return r.get("candles", [])
    except Exception:
        return []

def rsi(closes, period=14):
    if len(closes) < period+1:
        return 50
    gains = []
    losses = []
    for i in range(1, period+1):
        d = closes[-i] - closes[-i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains)/period; al = sum(losses)/period
    if al == 0:
        return 100
    rs = ag/al
    return 100 - (100/(1+rs))

def ema(closes, period):
    if len(closes) < period:
        return closes[-1] if closes else 0
    k = 2/(period+1); e = closes[0]
    for c in closes[1:]:
        e = c*k + e*(1-k)
    return e

def analyse(symbol):
    c1 = get_candles(symbol, 60, 25)
    c5 = get_candles(symbol, 300, 25)
    if not c1 or not c5:
        return None
    cl1 = [x["close"] for x in c1]; cl5 = [x["close"] for x in c5]
    r1 = rsi(cl1); r5 = rsi(cl5)
    e9 = ema(cl1, 9); e21 = ema(cl1, 21)
    last = cl1[-1]; prev = cl1[-2]
    mom = sum([1 if cl1[-i] > cl1[-i-1] else -1 for i in range(1, 6)])
    hi = max([x["high"] for x in c1[-20:]]); lo = min([x["low"] for x in c1[-20:]])
    near_support = abs(last-lo)/last*100 < 0.05
    near_resist = abs(hi-last)/last*100 < 0.05
    mid = sum(cl1[-20:])/20; sd = statistics.pstdev(cl1[-20:]) or 0.001
    upper = mid+2*sd; lower = mid-2*sd
    score_call = 0; score_put = 0
    if r1 < 30 and r5 < 40: score_call += 2
    if r1 > 70 and r5 > 60: score_put += 2
    if last > e9 > e21: score_call += 2
    if last < e9 < e21: score_put += 2
    if r1 > 55 and r5 > 55: score_call += 2
    if r1 < 45 and r5 < 45: score_put += 2
    if last <= lower: score_call += 1
    if last >= upper: score_put += 1
    if near_support: score_call += 1
    if near_resist: score_put += 1
    if mom >= 3: score_call += 2
    if mom <= -3: score_put += 2
    total = 10
    if score_call >= 8:
        direction = "CALL 📈"; conf = int(score_call/total*100)
    elif score_put >= 8:
        direction = "PUT 📉"; conf = int(score_put/total*100)
    else:
        best = max(score_call, score_put)
        return {"no_trade": True, "conf": int(best/total*100)}
    if abs(mom) >= 4 and abs(last-prev)/last*100 > 0.05:
        best = "30sec"
    elif abs(mom) >= 3:
        best = "1min"
    else:
        best = "2min"
    return {"direction": direction, "conf": conf, "best": best, "price": last, "symbol": symbol}

def format_signal(res, tf, platform, mode_label):
    entry = (datetime.now(LAGOS)+timedelta(minutes=4)).strftime("%H:%M")
    if res["best"] == "30sec":
        best_note = "fast move, best in short burst"
    elif res["best"] == f"{tf}min":
        best_note = "matches your choice"
    else:
        best_note = "slower move, give it more time"
    return (
        f"✅ SIGNAL - {platform} ({mode_label})\n\n"
        f"Pair: {NAMES[res['symbol']]}\n"
        f"Direction: {res['direction']}\n"
        f"Confidence: {res['conf']}%\n"
        f"Entry: {entry} Lagos\n"
        f"Duration: {tf} min\n\n"
        f"⏱ You chose: {tf}min\n"
        f"🎯 Best shot: {res['best']} - {best_note}\n\n"
        f"❌ NO MARTINGALE - 1 Trade Only\n"
        f"⚠️ Signals only - Trade manually\n"
        f"Tap /scan for next signal."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Rexxie Signals Bot\n\n/scan - YOU pick platform + pair\n/auto - BOT picks best pair\n\nOnly 80%+ signals. If no setup, NO TRADE.\nDeriv: 8 pairs | Pocket: 7 pairs")

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("📊 Deriv", callback_data="platform:Deriv"), InlineKeyboardButton("💰 Pocket Option", callback_data="platform:Pocket")]]
    await update.message.reply_text("First, pick your platform:", reply_markup=InlineKeyboardMarkup(kb))

async def auto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("📊 Deriv", callback_data="auto_platform:Deriv"), InlineKeyboardButton("💰 Pocket Option", callback_data="auto_platform:Pocket")]]
    await update.message.reply_text("🤖 AUTO MODE - First, pick your platform:", reply_markup=InlineKeyboardMarkup(kb))

async def show_pairs(q, platform, prefix):
    pairs = DERIV_PAIRS if platform == "Deriv" else POCKET_PAIRS
    kb = []
    for i in range(0, len(pairs), 2):
        row = [InlineKeyboardButton(NAMES[pairs[i]], callback_data=f"{prefix}_pair:{platform}:{pairs[i]}")]
        if i+1 < len(pairs):
            row.append(InlineKeyboardButton(NAMES[pairs[i+1]], callback_data=f"{prefix}_pair:{platform}:{pairs[i+1]}"))
        kb.append(row)
    await q.edit_message_text(f"Platform: {platform} ({len(pairs)} pairs)\n\nPick a pair:", reply_markup=InlineKeyboardMarkup(kb))

async def do_auto(q, platform, tf):
    await q.edit_message_text(f"🤖 AUTO scanning {platform}...\nAnalysing market, please wait...")
    pairs = DERIV_PAIRS if platform == "Deriv" else POCKET_PAIRS
    best = None
    for sym in pairs:
        res = analyse(sym)
        if res and not res.get("no_trade"):
            if not best or res["conf"] > best["conf"]:
                best = res
    now = datetime.now(LAGOS).strftime("%H:%M")
    if not best:
        await q.edit_message_text(f"❌ NO TRADE (AUTO - {platform})\n\nNo pair reached 80%.\nTime: {now} Lagos\n\nTap /auto again in 10 mins or /scan for manual.")
        return
    await q.edit_message_text(format_signal(best, tf, platform, "AUTO"))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = q.data; uid = q.from_user.id
    if data.startswith("platform:"):
        platform = data.split(":")[1]; user_choice[uid] = {"platform": platform}
        await show_pairs(q, platform, "manual")
    elif data.startswith("auto_platform:"):
        platform = data.split(":")[1]; user_choice[uid] = {"platform": platform}
        kb = [[InlineKeyboardButton("1 min", callback_data=f"auto_tf:{platform}:1"), InlineKeyboardButton("5 min", callback_data=f"auto_tf:{platform}:5"), InlineKeyboardButton("15 min", callback_data=f"auto_tf:{platform}:15")]]
        await q.edit_message_text(f"Platform: {platform} (AUTO)\n\nPick your duration:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("manual_pair:"):
        _, platform, sym = data.split(":"); user_choice[uid] = {"platform": platform, "pair": sym}
        kb = [[InlineKeyboardButton("1 min", callback_data=f"tf:{platform}:1"), InlineKeyboardButton("5 min", callback_data=f"tf:{platform}:5"), InlineKeyboardButton("15 min", callback_data=f"tf:{platform}:15")]]
        await q.edit_message_text(f"Platform: {platform}\nPair: {NAMES[sym]}\n\nPick your duration:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("tf:"):
        _, platform, tf = data.split(":"); ch = user_choice.get(uid, {}); sym = ch.get("pair", "R_100")
        await q.edit_message_text(f"🔍 Analysing {NAMES[sym]}...\nPlease wait...")
        res = analyse(sym)
        now = datetime.now(LAGOS).strftime("%H:%M")
        if not res or res.get("no_trade"):
            conf = res.get("conf", 0) if res else 0
            await q.edit_message_text(f"❌ NO TRADE\n\nPlatform: {platform}\nPair: {NAMES[sym]}\nConfidence: {conf}% (need 80%)\nTime: {now} Lagos\n\nTap /scan again in 5 mins.")
            return
        await q.edit_message_text(format_signal(res, tf, platform, "MANUAL"))
    elif data.startswith("auto_tf:"):
        _, platform, tf = data.split(":")
        await do_auto(q, platform, tf)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("auto", auto_cmd))
    app.add_handler(CallbackQueryHandler(button))
    print("Rexxie Bot LIVE - Deriv 8 + Pocket 7 + Fast + Clean")
    app.run_polling()
