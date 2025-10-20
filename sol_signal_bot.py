import ccxt
import pandas as pd
import time
import requests
import ta  # библиотека для индикаторов

# === Telegram ===
TELEGRAM_TOKEN = '8282840722:AAGk0J2k5qQBIZUNhgxZZtxvl2O5zweRrWE'
CHAT_ID = '632424066'

def send_telegram(msg):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {'chat_id': CHAT_ID, 'text': msg}
    requests.post(url, data=data)

# === Биржа ===
exchange = ccxt.binance({'enableRateLimit': True})
symbol = 'SOL/USDT'
timeframe = '5m'

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

def check_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    adx, plus_di, minus_di = last['ADX'], last['+DI'], last['-DI']
    macd, macd_sig = last['MACD'], last['MACD_Signal']
    prev_macd, prev_macd_sig = prev['MACD'], prev['MACD_Signal']
    rsi, wr = last['RSI'], last['WR']

    msg = f"\n[{last['timestamp']}]\n"
    msg += f"ADX={adx:.2f}, +DI={plus_di:.2f}, -DI={minus_di:.2f}\n"
    msg += f"MACD={macd:.5f}, Signal={macd_sig:.5f}\n"
    msg += f"RSI={rsi:.2f}, WR={wr:.2f}\n"

    if adx < 25:
        msg += "❌ Слабый тренд (ADX < 25)\n"
        send_telegram(msg)
        return None

    trend = 'up' if plus_di > minus_di else 'down'
    msg += f"📈 Тренд: {trend.upper()}\n"

    macd_cross = None
    if prev_macd < prev_macd_sig and macd > macd_sig:
        macd_cross = 'bullish'
        msg += "✅ MACD пересёк сигнал снизу вверх (bullish)\n"
    elif prev_macd > prev_macd_sig and macd < macd_sig:
        macd_cross = 'bearish'
        msg += "✅ MACD пересёк сигнал сверху вниз (bearish)\n"
    else:
        msg += "❌ Пересечения MACD нет\n"

    osc = None
    if rsi < 30 and wr < -80:
        osc = 'oversold'
        msg += "✅ Рынок перепродан (oversold)\n"
    elif rsi > 70 and wr > -20:
        osc = 'overbought'
        msg += "✅ Рынок перекуплен (overbought)\n"
    else:
        msg += "❌ Нет перекупленности/перепроданности\n"

    if trend == 'up' and macd_cross == 'bullish' and osc == 'oversold':
        signal = f'⚡ LONG сигнал по {symbol}\nADX={adx:.1f} RSI={rsi:.1f} WR={wr:.1f}'
        send_telegram(msg + signal)
        return signal
    if trend == 'down' and macd_cross == 'bearish' and osc == 'overbought':
        signal = f'⚡ SHORT сигнал по {symbol}\nADX={adx:.1f} RSI={rsi:.1f} WR={wr:.1f}'
        send_telegram(msg + signal)
        return signal

    msg += "⚠️ Условия не совпали — сигнал не сформирован."
    send_telegram(msg)
    return None

while True:
    try:
        df = fetch_data()
        df = calc_indicators(df)
        check_signal(df)
        time.sleep(60)
    except Exception as e:
        send_telegram(f'Ошибка: {e}')
        time.sleep(60)
