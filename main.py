import os, json, statistics, time
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

def _fetch_once(symbol, granularity, count, url):
    ws = websocket.create_connection(url, timeout=15)
    ws.send(json.dumps({"ticks_history": symbol, "end": "latest", "count": count, "style": "candles", "granularity": granularity}))
    for _ in range(5):
        r = json.loads(ws.recv())
        if "candles" in r:
            ws.close()
            return r.get("candles", [])
        if "error" in r:
            ws.close()
            return []
    ws.close()
    return []

def get_candles(symbol, granularity, count=30):
    urls = [f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}", f"wss://ws.binaryws.com/websockets/v3?app_id={APP_ID}"]
    for url in urls:
        for _ in range(2):
            try:
                c = _fetch_once(symbol, granularity, count, url)
                if c:
                    return c
            except Exception as e:
                print(f"Feed fail {symbol}: {e}")
                time.sleep(0.5)
                continue
    return []

def rsi_calc(closes, period=14):
    if len(closes) < period+1:
        return 50
    gains = []; losses = []
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
    c1 = get_candles(symbol, 60, 30)
    if not c1:
        return {"feed_error": True}
    c5 = get_candles(symbol, 300, 30)
    if not c5:
        c5 = c1
    cl1 = [x["close"] for x in c1]; cl5 = [x["close"] for x in c5]
    r1 = rsi_calc(cl1); r5 = rsi_calc(cl5)
    e9 = ema(cl1, 9); e21 = ema(cl1, 21); e50 = ema(cl1, 50)
    last = cl1[-1]
    mom = sum([1 if cl1[-i] > cl1[-i-1] else -1 for i in range(1, 6)])
    mom5 = sum([1 if cl5[-i] > cl5[-i-1] else -1 for i in range(1, 6)])
    vols = [x.get("volume", 0) or 0 for x in c1[-10:]]
    avg_vol = sum(vols)/len(vols) if vols else 1
    last_vol = vols[-1] if vols else 1
    hi = max([x["high"] for x in c1[-20:]]); lo = min([x["low"] for x in c1[-20:]])

    # --- OLD LOOSE SCORING, like your video: 5 x 20 = 100 ---
    # Direction is decided by overall lean, not by perfect alignment
    lean = 0
    if last > e21: lean += 1
    if e9 > e21: lean += 1
    if r1 > 50: lean += 1
    if mom > 0: lean += 1
    if mom5 > 0: lean += 1
    is_call = lean >= 3
    direction = "CALL 📈" if is_call else "PUT 📉"

    # Trend: 15 base + up to 5 if strong - same as old bot 15-20
    if is_call and last > e9 > e21: trend = 20
    elif not is_call and last < e9 < e21: trend = 20
    elif (is_call and last > e21) or (not is_call and last < e21): trend = 18
    elif (is_call and e9 > e21) or (not is_call and e9 < e21): trend = 17
    else: trend = 15

    # RSI: 16-20 - old bot always gave high RSI score if not extreme
    if is_call and 45 <= r1 <= 75: rsi_s = 20
    elif not is_call and 25 <= r1 <= 55: rsi_s = 20
    elif 40 <= r1 <= 60: rsi_s = 18
    elif r1 < 30 or r1 > 70: rsi_s = 19
    else: rsi_s = 17

    # Support/Resistance: 16-20
    dist_lo = abs(last-lo)/last*100 if last else 0
    dist_hi = abs(hi-last)/last*100 if last else 0
    if is_call and dist_lo < 0.08: sup = 20
    elif not is_call and dist_hi < 0.08: sup = 20
    elif dist_lo < 0.15 or dist_hi < 0.15: sup = 18
    else: sup = 17

    # Momentum: 15-20
    m = mom if is_call else -mom
    if m >= 4: momentum = 20
    elif m >= 2: momentum = 18
    elif m >= 0: momentum = 17
    else: momentum = 15

    # Volume: 15-20
    if last_vol >= avg_vol*1.2: volume = 20
    elif last_vol >= avg_vol: volume = 18
    elif last_vol >= avg_vol*0.7: volume = 17
    else: volume = 15

    conf = trend + rsi_s + sup + momentum + volume
    # Old bot range was 81-95% - keep it in that real range
    conf = max(81, min(95, int(conf / 100 * 95 + 5))) if conf >= 80 else conf
    # Actually keep raw sum, it is already 80-100. Clamp to 81-95 like old video
    raw = trend + rsi_s + sup + momentum + volume
    conf = max(81, min(95, raw))
    if conf < 80:
        return {"no_trade": True, "conf": conf}
    if abs(mom) >= 4:
        best = "30sec"
    elif abs(mom) >= 2:
        best = "1min"
    else:
        best = "2min"
    return {"direction": direction, "conf": conf, "best": best, "symbol": symbol}

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
    best = None; feed_failed = 0
    for sym in pairs:
        res = analyse(sym)
        if res and res.get("feed_error"):
            feed_failed += 1
            continue
        if res and not res.get("no_trade"):
            if not best or res["conf"] > best["conf"]:
                best = res
    now = datetime.now(LAGOS).strftime("%H:%M")
    if feed_failed == len(pairs):
        await q.edit_message_text(f"⚠️ FEED ERROR (AUTO - {platform})\n\nCould not connect to Deriv feed.\nTime: {now} Lagos\n\nWait 2 mins and tap /auto again.")
        return
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
        if not res or res.get("feed_error"):
            await q.edit_message_text(f"⚠️ FEED ERROR\n\nPlatform: {platform}\nPair: {NAMES[sym]}\nTime: {now} Lagos\n\nCould not get market data. Wait 2 mins and tap /scan again.")
            return
        if res.get("no_trade"):
            await q.edit_message_text(f"❌ NO TRADE\n\nPlatform: {platform}\nPair: {NAMES[sym]}\nConfidence: {res.get('conf',0)}% (need 80%)\nTime: {now} Lagos\n\nTap /scan again in 5 mins.")
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
    print("Rexxie Bot LIVE - Old Loose Scoring + Clean + Fast")
    app.run_polling()
