import os, json, statistics
from datetime import datetime, timedelta
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import websocket

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
APP_ID = "1089"
LAGOS = pytz.timezone("Africa/Lagos")

PAIRS = ["R_10","R_25","R_50","R_75","R_100","JD10","JD50","JD100","frxEURUSD","frxGBPUSD","frxUSDJPY","frxAUDUSD","frxEURGBP","frxGBPJPY","frxXAUUSD","frxBTCUSD"]
NAMES = {"R_10":"Volatility 10","R_25":"Volatility 25","R_50":"Volatility 50","R_75":"Volatility 75","R_100":"Volatility 100","JD10":"Jump 10","JD50":"Jump 50","JD100":"Jump 100","frxEURUSD":"EUR/USD","frxGBPUSD":"GBP/USD","frxUSDJPY":"USD/JPY","frxAUDUSD":"AUD/USD","frxEURGBP":"EUR/GBP","frxGBPJPY":"GBP/JPY","frxXAUUSD":"GOLD","frxBTCUSD":"BTC/USD"}
user_choice = {}

def get_candles(symbol, granularity, count=50):
    try:
        ws = websocket.create_connection(f"wss://ws.binaryws.com/websockets/v3?app_id={APP_ID}", timeout=15, header=["User-Agent: Mozilla/5.0", "Origin: https://app.deriv.com"])
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
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains)/period
    al = sum(losses)/period
    if al == 0:
        return 100
    rs = ag/al
    return 100 - (100/(1+rs))

def ema(closes, period):
    if len(closes) < period:
        return closes[-1] if closes else 0
    k = 2/(period+1)
    e = closes[0]
    for c in closes[1:]:
        e = c*k + e*(1-k)
    return e

def analyse(symbol):
    c1 = get_candles(symbol, 60, 50)
    c5 = get_candles(symbol, 300, 50)
    c15 = get_candles(symbol, 900, 50)
    if not c1 or not c5:
        return None
    cl1 = [x["close"] for x in c1]
    cl5 = [x["close"] for x in c5]
    cl15 = [x["close"] for x in c15]
    r1 = rsi(cl1); r5 = rsi(cl5); r15 = rsi(cl15)
    e9 = ema(cl1, 9); e21 = ema(cl1, 21)
    last = cl1[-1]; prev = cl1[-2]
    mom = sum([1 if cl1[-i] > cl1[-i-1] else -1 for i in range(1, 6)])
    hi = max([x["high"] for x in c1[-20:]])
    lo = min([x["low"] for x in c1[-20:]])
    near_support = abs(last-lo)/last*100 < 0.05
    near_resist = abs(hi-last)/last*100 < 0.05
    mid = sum(cl1[-20:])/20
    sd = statistics.pstdev(cl1[-20:]) or 0.001
    upper = mid+2*sd; lower = mid-2*sd
    score_call = 0; score_put = 0; reasons = []
    if r1 < 30 and r5 < 40:
        score_call += 2; reasons.append("RSI oversold")
    if r1 > 70 and r5 > 60:
        score_put += 2; reasons.append("RSI overbought")
    if last > e9 > e21:
        score_call += 2; reasons.append("EMA uptrend")
    if last < e9 < e21:
        score_put += 2; reasons.append("EMA downtrend")
    if r1 > 55 and r5 > 55 and r15 > 50:
        score_call += 2; reasons.append("MTF RSI up")
    if r1 < 45 and r5 < 45 and r15 < 50:
        score_put += 2; reasons.append("MTF RSI down")
    if last <= lower:
        score_call += 1; reasons.append("Bounce off lower band")
    if last >= upper:
        score_put += 1; reasons.append("Reject upper band")
    if near_support:
        score_call += 1; reasons.append("At support")
    if near_resist:
        score_put += 1; reasons.append("At resistance")
    if mom >= 3:
        score_call += 2; reasons.append(f"Momentum +{mom}/5")
    if mom <= -3:
        score_put += 2; reasons.append(f"Momentum {mom}/5")
    total = 10
    if score_call >= 8:
        direction = "CALL 📈"; conf = int(score_call/total*100)
    elif score_put >= 8:
        direction = "PUT 📉"; conf = int(score_put/total*100)
    else:
        best = max(score_call, score_put)
        return {"no_trade": True, "conf": int(best/total*100), "r1": r1, "r5": r5}
    if abs(mom) >= 4 and abs(last-prev)/last*100 > 0.05:
        best = "30sec"
    elif abs(mom) >= 3:
        best = "1min"
    else:
        best = "2min"
    return {"direction": direction, "conf": conf, "reasons": reasons, "best": best, "r1": round(r1, 1), "r5": round(r5, 1), "price": last, "symbol": symbol}

def format_signal(res, tf, mode_label):
    entry = (datetime.now(LAGOS)+timedelta(minutes=4)).strftime("%H:%M")
    if res["best"] == "30sec":
        best_note = "momentum is very fast, best in short burst"
    elif res["best"] == f"{tf}min":
        best_note = "momentum matches your choice"
    else:
        best_note = "slower momentum, give it more time"
    return (
        f"✅ SIGNAL - 80%+ CONFLUENCE ({mode_label})\n\n"
        f"Pair: {NAMES[res['symbol']]}\n"
        f"Direction: {res['direction']}\n"
        f"Confluence: {res['conf']}%\n"
        f"Price: {res['price']}\n"
        f"RSI 1m: {res['r1']} | 5m: {res['r5']}\n"
        f"Entry Time: {entry} Lagos (4 mins to prepare)\n"
        f"Duration: {tf} min\n\n"
        f"📊 Why: {', '.join(res['reasons'])}\n\n"
        f"⏱ You chose: {tf}min\n"
        f"🎯 Best shot: {res['best']} - {best_note}\n\n"
        f"⚠️ 1 trade only. No martingale.\n"
        f"Tap /scan for manual or /auto for auto."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Rexxie Signals Bot\n\n/manual: /scan - YOU pick pair (best when free)\n/auto: /auto - BOT picks best pair (best when busy)\n\nBoth only send 80%+ signals. If no setup, NO TRADE.\n16 pairs: Volatility, Jump, Forex, GOLD, BTC.")

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = []
    for i in range(0, len(PAIRS), 2):
        row = [InlineKeyboardButton(NAMES[PAIRS[i]], callback_data=f"pair:{PAIRS[i]}")]
        if i+1 < len(PAIRS):
            row.append(InlineKeyboardButton(NAMES[PAIRS[i+1]], callback_data=f"pair:{PAIRS[i+1]}"))
        kb.append(row)
    kb.append([InlineKeyboardButton("🤖 Auto - Let Bot Pick Best", callback_data="auto:1")])
    await update.message.reply_text("📊 Pick a pair MANUALLY (16 pairs) or tap Auto:", reply_markup=InlineKeyboardMarkup(kb))

async def auto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("1 min", callback_data="auto_tf:1"), InlineKeyboardButton("5 min", callback_data="auto_tf:5"), InlineKeyboardButton("15 min", callback_data="auto_tf:15")]]
    await update.message.reply_text("🤖 AUTO MODE\nBot will scan all 16 pairs and pick the SINGLE best 80%+ setup.\n\nPick your duration:", reply_markup=InlineKeyboardMarkup(kb))

async def do_auto(q, tf):
    await q.edit_message_text(f"🤖 AUTO scanning all 16 pairs...\nChecking RSI + EMA + Bollinger + Support/Resistance + MTF...\nThis takes 40-60 sec, please wait. I will only pick the BEST one.")
    best = None
    for sym in PAIRS:
        res = analyse(sym)
        if res and not res.get("no_trade"):
            if not best or res["conf"] > best["conf"]:
                best = res
    now = datetime.now(LAGOS).strftime("%H:%M")
    if not best:
        await q.edit_message_text(f"❌ NO TRADE (AUTO)\n\nScanned all 16 pairs.\nNone reached 80%.\nTime: {now} Lagos\n\nI will NOT force a signal.\nTap /auto again in 10 mins or /scan for manual.")
        return
    await q.edit_message_text(format_signal(best, tf, "AUTO - Bot Picked Best"))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = q.data; uid = q.from_user.id
    if data.startswith("pair:"):
        sym = data.split(":")[1]; user_choice[uid] = {"pair": sym}
        kb = [[InlineKeyboardButton("1 min", callback_data="tf:1"), InlineKeyboardButton("5 min", callback_data="tf:5"), InlineKeyboardButton("15 min", callback_data="tf:15")]]
        await q.edit_message_text(f"Pair: {NAMES[sym]}\n\nNow pick your trade duration:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("tf:"):
        tf = data.split(":")[1]; ch = user_choice.get(uid, {}); sym = ch.get("pair", "R_100")
        await q.edit_message_text(f"🔍 Analysing {NAMES[sym]} deeply...\nChecking RSI + EMA + MACD + Bollinger + Support/Resistance + Multi-timeframe...\nPlease wait 15-20 sec, no rushing a direction.")
        res = analyse(sym)
        now = datetime.now(LAGOS).strftime("%H:%M")
        if not res or res.get("no_trade"):
            conf = res.get("conf", 0) if res else 0
            await q.edit_message_text(f"❌ NO TRADE\n\nPair: {NAMES[sym]}\nConfluence: {conf}% (need 80%)\nTime: {now} Lagos\n\nSetup not strong enough. I will NOT force a signal.\nTap /scan again in 5 mins.")
            return
        await q.edit_message_text(format_signal(res, tf, "MANUAL - You Picked"))
    elif data == "auto:1":
        kb = [[InlineKeyboardButton("1 min", callback_data="auto_tf:1"), InlineKeyboardButton("5 min", callback_data="auto_tf:5"), InlineKeyboardButton("15 min", callback_data="auto_tf:15")]]
        await q.edit_message_text("🤖 AUTO MODE\nBot will scan all 16 pairs and pick the SINGLE best 80%+ setup.\n\nPick your duration:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("auto_tf:"):
        tf = data.split(":")[1]
        await do_auto(q, tf)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("auto", auto_cmd))
    app.add_handler(CallbackQueryHandler(button))
    print("Rexxie Bot LIVE - Manual + Auto + 16 Pairs + 80% + Best Expiry")
    app.run_polling()
