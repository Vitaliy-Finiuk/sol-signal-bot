import ccxt
import pandas as pd
import time
import requests
import os
import threading
from flask import Flask
from datetime import datetime, timedelta

# === Telegram ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
BOT_URL = os.environ.get("BOT_URL", "https://sol-signal-bot-wpme.onrender.com/")

def keep_alive():
    while True:
        try:
            if BOT_URL:
                requests.get(BOT_URL, timeout=5)
        except:
            pass
        time.sleep(300)

threading.Thread(target=keep_alive, daemon=True).start()

def send_telegram(msg):
    try:
        if not TELEGRAM_TOKEN or not CHAT_ID:
            print("⚠️ Telegram credentials not set")
            return
            
        data = {'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
        resp = requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage', 
                           data=data, timeout=10)
        if resp.status_code != 200:
            print(f"Telegram send error: {resp.text}")
    except Exception as e:
        print(f"Telegram error: {e}")

# === Flask keep-alive ===
app = Flask(__name__)
@app.route("/")
def home():
    return "🚀 Signal Bot Active | Strategies: RSI + EMA"

def run_flask():
    app.run(host="0.0.0.0", port=10000, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# === Биржа ===
exchange = ccxt.okx({'enableRateLimit': True})

# Параметры
symbols = ['SOL/USDT', 'BTC/USDT', 'ETH/USDT', 'BNB/USDT']
timeframes = ['4h', '12h', '1d']

BALANCE = 100.0
RISK_PER_TRADE = 0.03
MAX_LEVERAGE = 7
MIN_RISK_REWARD = 2.0
COMMISSION = 0.0006

# Статистика
stats = {s: {tf: {'LONG': 0, 'SHORT': 0, 'Total': 0} for tf in timeframes} for s in symbols}
last_summary_time = datetime.now()
last_daily_report = datetime.now()
last_signal_time = {}

# === Безопасный fetch ===
def safe_fetch_ohlcv(symbol, timeframe, limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return ohlcv if ohlcv else None
    except Exception as e:
        print(f"Fetch error {symbol} {timeframe}: {e}")
        return None

# === Простые индикаторы без ta ===
def calculate_ema(series, window):
    return series.ewm(span=window, adjust=False).mean()

def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_atr(high, low, close, window=14):
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=window).mean()
    return atr

# === СТРАТЕГИЯ 1: 4h Turtle ===
def strategy_4h_turtle(df):
    try:
        if len(df) < 55:
            return None, {}
        
        df['High_15'] = df['high'].rolling(window=15).max()
        df['Low_15'] = df['low'].rolling(window=15).min()
        df['EMA_21'] = calculate_ema(df['close'], 21)
        df['EMA_55'] = calculate_ema(df['close'], 55)
        df['ATR'] = calculate_atr(df['high'], df['low'], df['close'])
        df['RSI'] = calculate_rsi(df['close'])
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        if pd.isna(last['ATR']) or pd.isna(last['RSI']):
            return None, {}
        
        close = last['close']
        high_15 = prev['High_15']
        low_15 = prev['Low_15']
        ema21 = last['EMA_21']
        ema55 = last['EMA_55']
        atr = last['ATR']
        rsi = last['RSI']
        
        signal = None
        params = {}
        
        if (close > high_15 and ema21 > ema55 and rsi < 75):
            signal = 'LONG'
            params = {'entry': close, 'sl_distance': atr * 1.8, 'tp_distance': atr * 5.5, 'atr': atr}
        
        elif (close < low_15 and ema21 < ema55 and rsi > 25):
            signal = 'SHORT'
            params = {'entry': close, 'sl_distance': atr * 1.8, 'tp_distance': atr * 5.5, 'atr': atr}
        
        return signal, params
    except Exception as e:
        print(f"Strategy 4h error: {e}")
        return None, {}

# === СТРАТЕГИЯ 2: 12h Momentum ===
def strategy_12h_momentum(df):
    try:
        if len(df) < 50:
            return None, {}
        
        df['EMA_9'] = calculate_ema(df['close'], 9)
        df['EMA_21'] = calculate_ema(df['close'], 21)
        df['EMA_50'] = calculate_ema(df['close'], 50)
        
        # Bollinger Bands
        df['BB_Middle'] = df['close'].rolling(window=20).mean()
        df['BB_Std'] = df['close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (df['BB_Std'] * 2)
        df['BB_Lower'] = df['BB_Middle'] - (df['BB_Std'] * 2)
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['close']
        
        df['RSI'] = calculate_rsi(df['close'])
        df['ATR'] = calculate_atr(df['high'], df['low'], df['close'])
        
        last = df.iloc[-1]
        
        if pd.isna(last['ATR']) or pd.isna(last['RSI']):
            return None, {}
        
        close = last['close']
        ema9 = last['EMA_9']
        ema21 = last['EMA_21']
        ema50 = last['EMA_50']
        bb_upper = last['BB_Upper']
        bb_lower = last['BB_Lower']
        bb_width = last['BB_Width']
        rsi = last['RSI']
        atr = last['ATR']
        
        signal = None
        params = {}
        
        if (close > bb_upper and ema9 > ema21 > ema50 and
            30 < rsi < 70 and bb_width > 0.02):
            signal = 'LONG'
            params = {'entry': close, 'sl_distance': atr * 2.2, 'tp_distance': atr * 6.5, 'atr': atr}
        
        elif (close < bb_lower and ema9 < ema21 < ema50 and
              30 < rsi < 70 and bb_width > 0.02):
            signal = 'SHORT'
            params = {'entry': close, 'sl_distance': atr * 2.2, 'tp_distance': atr * 6.5, 'atr': atr}
        
        return signal, params
    except Exception as e:
        print(f"Strategy 12h error: {e}")
        return None, {}

# === СТРАТЕГИЯ 3: 1d Trend ===
def strategy_1d_trend(df):
    try:
        if len(df) < 100:
            return None, {}
        
        df['EMA_20'] = calculate_ema(df['close'], 20)
        df['EMA_50'] = calculate_ema(df['close'], 50)
        df['EMA_100'] = calculate_ema(df['close'], 100)
        df['RSI'] = calculate_rsi(df['close'])
        df['ATR'] = calculate_atr(df['high'], df['low'], df['close'])
        
        last = df.iloc[-1]
        
        if pd.isna(last['ATR']) or pd.isna(last['RSI']):
            return None, {}
        
        close = last['close']
        ema20 = last['EMA_20']
        ema50 = last['EMA_50']
        ema100 = last['EMA_100']
        rsi = last['RSI']
        atr = last['ATR']
        
        uptrend = ema20 > ema50 > ema100
        downtrend = ema20 < ema50 < ema100
        
        signal = None
        params = {}
        
        if (uptrend and close <= ema20 * 1.02 and close >= ema20 * 0.97 and 40 < rsi < 60):
            signal = 'LONG'
            params = {'entry': close, 'sl_distance': atr * 3.0, 'tp_distance': atr * 8.0, 'atr': atr}
        
        elif (downtrend and close >= ema20 * 0.98 and close <= ema20 * 1.03 and 40 < rsi < 60):
            signal = 'SHORT'
            params = {'entry': close, 'sl_distance': atr * 3.0, 'tp_distance': atr * 8.0, 'atr': atr}
        
        return signal, params
    except Exception as e:
        print(f"Strategy 1d error: {e}")
        return None, {}

# === Выбор стратегии ===
def get_strategy(timeframe):
    strategies = {
        '4h': ('4h Aggressive Turtle', strategy_4h_turtle),
        '12h': ('12h Momentum Breakout', strategy_12h_momentum),
        '1d': ('1d Strong Trend Following', strategy_1d_trend)
    }
    return strategies.get(timeframe, (None, None))

# === Проверка сигналов ===
def check_signal(df, symbol, timeframe):
    try:
        if len(df) < 20:
            return
        
        strategy_name, strategy_func = get_strategy(timeframe)
        if not strategy_func:
            return
        
        signal, params = strategy_func(df)
        
        if not signal or not params:
            return
        
        signal_key = f"{symbol}_{timeframe}_{signal}"
        now = datetime.now()
        if signal_key in last_signal_time:
            if (now - last_signal_time[signal_key]).total_seconds() < 3600:
                return
        last_signal_time[signal_key] = now
        
        rr = params['tp_distance'] / params['sl_distance']
        if rr < MIN_RISK_REWARD:
            return
        
        entry = params['entry']
        sl_distance = params['sl_distance']
        tp_distance = params['tp_distance']
        
        if signal == 'LONG':
            stop_loss = entry - sl_distance
            take_profit = entry + tp_distance
        else:
            stop_loss = entry + sl_distance
            take_profit = entry - tp_distance
        
        risk_amount = BALANCE * RISK_PER_TRADE
        position_size_base = risk_amount / sl_distance
        
        if entry <= 0:
            return
        
        leverage_ratio = (position_size_base * entry) / BALANCE
        leverage_used = min(MAX_LEVERAGE, leverage_ratio)
        position_size = (risk_amount * leverage_used) / sl_distance
        
        if signal == 'LONG':
            potential_profit = tp_distance * position_size
            potential_loss = sl_distance * position_size
        else:
            potential_profit = tp_distance * position_size
            potential_loss = sl_distance * position_size
        
        commission_cost = position_size * entry * COMMISSION * 2
        net_profit = potential_profit - commission_cost
        net_loss = potential_loss + commission_cost
        
        stats[symbol][timeframe]['Total'] += 1
        stats[symbol][timeframe][signal] += 1
        
        msg = (
            f"🚨 *{signal} СИГНАЛ*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Пара:* `{symbol}`\n"
            f"⏰ *Таймфрейм:* `{timeframe}`\n"
            f"🎯 *Стратегия:* `{strategy_name}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 *ПАРАМЕТРЫ ВХОДА:*\n"
            f"├ Цена входа: `{entry:.4f}` USDT\n"
            f"├ Stop-Loss: `{stop_loss:.4f}` USDT\n"
            f"└ Take-Profit: `{take_profit:.4f}` USDT\n\n"
            f"📊 *ПОЗИЦИЯ:*\n"
            f"├ Размер: `{position_size:.2f}` USD\n"
            f"├ Плечо: `{leverage_used:.1f}x`\n"
            f"└ R:R: `{rr:.2f}:1`\n\n"
            f"💵 *ПРОГНОЗ:*\n"
            f"├ ✅ Прибыль: `+{net_profit:.2f}` USD (`+{(net_profit/BALANCE)*100:.1f}%`)\n"
            f"├ ❌ Убыток: `-{net_loss:.2f}` USD (`-{(net_loss/BALANCE)*100:.1f}%`)\n"
            f"└ Риск: `{RISK_PER_TRADE*100:.0f}%` от депозита\n\n"
            f"📈 *ATR:* `{params['atr']:.4f}`\n"
            f"⚡ *Комиссии:* `{commission_cost:.2f}` USD\n\n"
            f"⚠️ *Рекомендации:*\n"
            f"• Строго соблюдай Stop-Loss!\n"
            f"• Используй trailing stop при +5%\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        
        send_telegram(msg)
        print(f"✅ {signal} signal sent: {symbol} {timeframe}")
        
    except Exception as e:
        print(f"Check signal error: {e}")

# === Сводка ===
def send_summary():
    msg = f"📊 *Статистика сигналов*\n`{datetime.now().strftime('%Y-%m-%d %H:%M')}`\n━━━━━━━━━━━━━━━━━━━━\n"
    
    total_signals = 0
    for s in symbols:
        for tf in timeframes:
            st = stats[s][tf]
            if st['Total'] > 0:
                msg += f"`{s:<10}` {tf:>3}: 📈{st['LONG']} 📉{st['SHORT']} (всего: {st['Total']})\n"
                total_signals += st['Total']
    
    if total_signals == 0:
        msg += "\n_Пока нет сигналов_"
    
    msg += f"\n━━━━━━━━━━━━━━━━━━━━\n🎯 Всего: *{total_signals}*"
    send_telegram(msg)

# === Основной цикл ===
def main():
    global last_summary_time, last_daily_report
    
    print("🚀 Starting Signal Bot...")
    send_telegram("🤖 *Signal Bot Started!*\nMonitoring: SOL, BTC, ETH, BNB\nTimeframes: 4h, 12h, 1d")
    
    while True:
        try:
            now = datetime.now()
            
            # Сводка каждые 6 часов
            if (now - last_summary_time).total_seconds() > 21600:
                send_summary()
                last_summary_time = now
            
            # Проверка сигналов
            for symbol in symbols:
                for timeframe in timeframes:
                    try:
                        ohlcv = safe_fetch_ohlcv(symbol, timeframe, limit=100)
                        if ohlcv:
                            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                            
                            check_signal(df, symbol, timeframe)
                        else:
                            print(f"⚠️ No data for {symbol} {timeframe}")
                            
                    except Exception as e:
                        print(f"Error processing {symbol} {timeframe}: {e}")
            
            print(f"✅ Cycle completed at {now.strftime('%H:%M')}")
            time.sleep(60)
            
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(300)

if __name__ == "__main__":
    main()