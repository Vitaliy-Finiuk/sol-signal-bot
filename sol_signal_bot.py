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
    adx, plus_di, minus_di = last['ADX'], last['+DI'], last['-DI']
    macd, macd_sig = last['MACD'], last['MACD_Signal']
    rsi, wr = last['RSI'], last['WR']

    # Тренд
    if adx < 25:
        return None
    trend = 'up' if plus_di > minus_di else 'down'

    # MACD кросс
    prev = df.iloc[-2]
    macd_cross = 'bullish' if prev['MACD'] < prev['MACD_Signal'] and macd > macd_sig else \
                 'bearish' if prev['MACD'] > prev['MACD_Signal'] and macd < macd_sig else None

    # Перекупленность
    osc = 'oversold' if rsi < 30 and wr < -80 else \
          'overbought' if rsi > 70 and wr > -20 else None

    # Сигнал
    if trend == 'up' and macd_cross == 'bullish' and osc == 'oversold':
        return f'⚡ LONG сигнал по {symbol}\nADX={adx:.1f} RSI={rsi:.1f} WR={wr:.1f}'
    if trend == 'down' and macd_cross == 'bearish' and osc == 'overbought':
        return f'⚡ SHORT сигнал по {symbol}\nADX={adx:.1f} RSI={rsi:.1f} WR={wr:.1f}'
    return None

while True:
    try:
        df = fetch_data()
        df = calc_indicators(df)
        signal = check_signal(df)
        if signal:
            print(signal)
            send_telegram(signal)
        time.sleep(60)
    except Exception as e:
        print('Ошибка:', e)
        time.sleep(60)
