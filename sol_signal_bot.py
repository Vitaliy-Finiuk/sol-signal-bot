import ccxt
import pandas as pd
import time
import requests
import ta
import os
import json
from datetime import datetime

# === Telegram ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram(msg):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    requests.post(url, data=data)

# === Биржа (OKX Spot) ===
exchange = ccxt.okx({
    'enableRateLimit': True,
})
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
    if adx < 25:
        return None  # слабый тренд

    trend = 'up' if plus_di > minus_di else 'down'

    # MACD кросс
    macd_cross = None
    if prev_macd < prev_macd_sig and macd > macd_sig:
        macd_cross = 'bullish'
    elif prev_macd > prev_macd_sig and macd < macd_sig:
        macd_cross = 'bearish'

    # Перекупленность/перепроданность
    osc = None
    if rsi < 30 and wr < -80:
        osc = 'oversold'
    elif rsi > 70 and wr > -20:
        osc = 'overbought'

    signal_type = None
    if trend == 'up' and macd_cross == 'bullish' and osc == 'oversold':
        signal_type = 'LONG'
    elif trend == 'down' and macd_cross == 'bearish' and osc == 'overbought':
        signal_type = 'SHORT'

    if signal_type:
        msg = f"⚡ *{signal_type} сигнал* по {symbol}\n"
        msg += f"ADX={adx:.1f} RSI={rsi:.1f} WR={wr:.1f}\n"
        msg += f"Время: {last['timestamp']}"
        send_telegram(msg)
        log_signal(signal_type, df, success=True if paper else False)
        return signal_type

    return None

# === Backtesting / Replay / Paper Trading ===
def replay_backtest(df):
    print("=== Replay / Paper Trading Mode ===")
    for i in range(15, len(df)):
        sub_df = df.iloc[i-15:i]
        check_signal(sub_df, paper=True)

# === Main Loop ===
def main_loop():
    while True:
        try:
            df = fetch_data()
            df = calc_indicators(df)
            check_signal(df)
            time.sleep(60)
        except Exception as e:
            send_telegram(f'Ошибка: {e}')
            time.sleep(60)

# === Запуск ===
mode = "live"  # "live" для реального времени, "replay" для теста
if mode == "replay":
    df_hist = fetch_data()
    df_hist = calc_indicators(df_hist)
    replay_backtest(df_hist)
else:
    main_loop()
