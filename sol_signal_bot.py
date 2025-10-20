import ccxt
import pandas as pd
import time
import requests
import ta
import os
import json
import threading
from flask import Flask


# === Telegram ===
TELEGRAM_TOKEN = '8282840722:AAGk0J2k5qQBIZUNhgxZZtxvl2O5zweRrWE'
CHAT_ID = '632424066'

def send_telegram(msg):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    requests.post(url, data=data)

# === Flask keep-alive для Render Free ===
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000)).start()

# === Биржа (OKX Spot) ===
exchange = ccxt.okx({'enableRateLimit': True})
symbol = 'SOL/USDT'
timeframe = '5m'

# Лог сигналов
LOG_FILE = 'signals.log'
stats = {'LONG':0, 'SHORT':0, 'Total':0, 'Success':0}

def log_signal(signal_type, df, success=False):
    stats['Total'] += 1
    if success:
        stats['Success'] += 1
    stats[signal_type] += 1
    last = df.iloc[-1]
    log = {
        'timestamp': str(last['timestamp']),
        'signal': signal_type,
        'ADX': last['ADX'],
        'RSI': last['RSI'],
        'WR': last['WR'],
        'success': success
    }
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(log) + '\n')

def fetch_data():
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
    df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calc_indicators(df):
    df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
    df['+DI'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=14)
    df['-DI'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=14)
    macd = ta.trend.MACD(df['close'])
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    df['WR'] = ta.momentum.williams_r(df['high'], df['low'], df['close'], lbp=14)
    return df

def check_signal(df, paper=True):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    adx, plus_di, minus_di = last['ADX'], last['+DI'], last['-DI']
    macd, macd_sig = last['MACD'], last['MACD_Signal']
    prev_macd, prev_macd_sig = prev['MACD'], prev['MACD_Signal']
    rsi, wr = last['RSI'], last['WR']

    # Проверка тренда
    indicators_not_ok = []
    if adx < 25:
        indicators_not_ok.append("ADX")
    
    trend = 'up' if plus_di > minus_di else 'down'

    # MACD кросс
    macd_cross = None
    if prev_macd < prev_macd_sig and macd > macd_sig:
        macd_cross = 'bullish'
    elif prev_macd > prev_macd_sig and macd < macd_sig:
        macd_cross = 'bearish'
    else:
        indicators_not_ok.append("MACD")

    # Перекупленность/перепроданность
    osc = None
    if rsi < 30 and wr < -80:
        osc = 'oversold'
    elif rsi > 70 and wr > -20:
        osc = 'overbought'
    else:
        indicators_not_ok.append("RSI/WR")

    signal_type = None
    if trend == 'up' and macd_cross == 'bullish' and osc == 'oversold':
        signal_type = 'LONG'
    elif trend == 'down' and macd_cross == 'bearish' and osc == 'overbought':
        signal_type = 'SHORT'

    # Отправка сигнала
    if signal_type:
        msg = f"⚡ *{signal_type} сигнал* по {symbol}\nADX={adx:.1f} RSI={rsi:.1f} WR={wr:.1f}\nВремя: {last['timestamp']}"
        send_telegram(msg)
        log_signal(signal_type, df, success=True if paper else False)

    # Отправка сводки каждые 5 минут
    summary = f"📊 *Сводка индикаторов* {symbol} | {last['timestamp']}\n"
    if indicators_not_ok:
        summary += "❌ Не подходят: " + ", ".join(indicators_not_ok)
    else:
        summary += "✅ Все индикаторы в норме"
    send_telegram(summary)

    return signal_type

# === Main Loop ===
def main_loop():
    while True:
        try:
            df = fetch_data()
            df = calc_indicators(df)
            check_signal(df)
            time.sleep(300)  # 5 минут
        except Exception as e:
            send_telegram(f'Ошибка: {e}')
            time.sleep(60)

# === Запуск ===
main_loop()
