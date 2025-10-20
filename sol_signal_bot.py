import ccxt
import pandas as pd
import time
import requests
import ta
import os
import threading
from flask import Flask
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime, timedelta

# === Telegram ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
BOT_URL = os.environ.get("https://sol-signal-bot-wpme.onrender.com/") 

def keep_alive():
    while True:
        try:
            if BOT_URL:
                requests.get(BOT_URL)
        except:
            pass
        time.sleep(300)  # пинг каждые 5 минут

threading.Thread(target=keep_alive, daemon=True).start()

def send_telegram(msg, img=None):
    if img is None:
        data = {'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
        requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage', data=data)
    else:
        files = {'photo': img.getvalue()}
        data = {'chat_id': CHAT_ID, 'caption': msg, 'parse_mode': 'Markdown'}
        requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto', data=data, files=files)

# === Flask keep-alive ===
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot is running!"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000)).start()

# === Биржа ===
exchange = ccxt.okx({'enableRateLimit': True})

symbols = ['BTC/USDT','BNB/USDT','SOL/USDT']
timeframes = ['5m','15m']

# === Параметры риск-менеджмента ===
BALANCE = 100.0  # стартовый депозит
RISK_PER_TRADE = 0.01  # 1% от депозита
MAX_LEVERAGE = 5  # максимальное плечо для позиции/grid

# === Статистика сигналов ===
stats = {s:{tf:{'LONG':0,'SHORT':0,'Total':0,'Success':0} for tf in timeframes} for s in symbols}
last_summary_time = datetime.now()
last_daily_report = datetime.now()

# === Безопасный fetch OHLCV ===
def safe_fetch_ohlcv(symbol, timeframe, retries=5):
    delay = 5
    for i in range(retries):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        except ccxt.NetworkError:
            time.sleep(delay)
            delay *= 2
        except ccxt.ExchangeError:
            time.sleep(delay)
    raise Exception(f"Failed to fetch OHLCV for {symbol}")

# === Расчет индикаторов ===
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

# === Построение графика с сигналами ===
def plot_signal(df, signal_type, symbol, timeframe):
    fig, ax = plt.subplots(figsize=(10,4))
    ax.plot(df['timestamp'], df['close'], label='Close')
    last = df.iloc[-1]
    if signal_type:
        ax.scatter(last['timestamp'], last['close'], color='green' if signal_type=='LONG' else 'red', s=100, label=signal_type)
    ax.set_title(f"{symbol} {timeframe}")
    ax.legend()
    img = BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plt.close(fig)
    return img

# === Проверка сигналов и расчет позиции с плечом ===
# === Проверка сигналов и расчет позиции с плечом + прибыль/убыток ===
def check_signal(df, symbol, timeframe):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    adx, plus_di, minus_di = last['ADX'], last['+DI'], last['-DI']
    macd, macd_sig = last['MACD'], last['MACD_Signal']
    prev_macd, prev_macd_sig = prev['MACD'], prev['MACD_Signal']
    rsi, wr = last['RSI'], last['WR']

    # Тренд
    trend = 'up' if plus_di > minus_di else 'down'

    # MACD кросс
    macd_cross = None
    if prev_macd < prev_macd_sig and macd > macd_sig:
        macd_cross = 'bullish'
    elif prev_macd > prev_macd_sig and macd < macd_sig:
        macd_cross = 'bearish'

    # Осцилляторы
    osc = None
    if rsi < 30 and wr < -80:
        osc = 'oversold'
    elif rsi > 70 and wr > -20:
        osc = 'overbought'

    signal_type = None
    if adx >= 25:
        if trend=='up' and macd_cross=='bullish' and osc=='oversold':
            signal_type='LONG'
        elif trend=='down' and macd_cross=='bearish' and osc=='overbought':
            signal_type='SHORT'

    # Риск-менеджмент и маржинальная позиция
    entry_price = last['close']
    stop_loss = entry_price * 0.99 if signal_type=='LONG' else entry_price * 1.01
    take_profit = entry_price * 1.02 if signal_type=='LONG' else entry_price * 0.98
    position_size = BALANCE * RISK_PER_TRADE / abs(entry_price - stop_loss)
    leverage_used = min(MAX_LEVERAGE, position_size / BALANCE)
    position_size *= leverage_used

    # Потенциальная прибыль / убыток в USD
    if signal_type == 'LONG':
        potential_profit = (take_profit - entry_price) * position_size
        potential_loss = (entry_price - stop_loss) * position_size
    elif signal_type == 'SHORT':
        potential_profit = (entry_price - take_profit) * position_size
        potential_loss = (stop_loss - entry_price) * position_size
    else:
        potential_profit = potential_loss = 0

    # Обновление статистики
    stats[symbol][timeframe]['Total'] += 1
    if signal_type:
        stats[symbol][timeframe][signal_type] += 1
        stats[symbol][timeframe]['Success'] += 1

    # Отправка сигнала с графиком и таблицей
    if signal_type:
        msg = (f"⚡ *{signal_type} сигнал* по {symbol} ({timeframe})\n"
               f"Цена входа: {entry_price:.2f}\nStop-Loss: {stop_loss:.2f} | Take-Profit: {take_profit:.2f}\n"
               f"Размер позиции: {position_size:.2f} USD\nПотенциальное плечо: {leverage_used:.1f}x\n"
               f"Потенциальная прибыль: {potential_profit:.2f} USD | Потенциальный убыток: {potential_loss:.2f} USD\n"
               f"Риск на сделку: {RISK_PER_TRADE*100:.1f}%\n"
               f"✅ Можно запускать grid-бот при подтвержденном сигнале")
        img = plot_signal(df, signal_type, symbol, timeframe)
        send_telegram(msg, img)

    return signal_type

# === Сводка каждые 15 минут ===
def send_summary():
    msg = f"📊 *Сводка по индикаторам* {datetime.now()}\n"
    for s in symbols:
        for tf in timeframes:
            st = stats[s][tf]
            msg += f"{s} {tf}: Total={st['Total']} LONG={st['LONG']} SHORT={st['SHORT']}\n"
    send_telegram(msg)

# === Ежедневная сводка стратегии ===
def send_daily_report():
    msg = f"📈 *Ежедневная сводка стратегии* {datetime.now().strftime('%Y-%m-%d')}\n"
    for s in symbols:
        for tf in timeframes:
            st = stats[s][tf]
            total = st['Total'] if st['Total']>0 else 1
            success_rate = st['Success'] / total * 100
            msg += (f"{s} {tf}: Total={st['Total']} LONG={st['LONG']} SHORT={st['SHORT']} "
                    f"Процент успешных сигналов: {success_rate:.1f}%\n")
    send_telegram(msg)

# === Основной цикл ===
def main_loop():
    global last_summary_time, last_daily_report
    while True:
        try:
            now = datetime.now()
            for symbol in symbols:
                for tf in timeframes:
                    ohlcv = safe_fetch_ohlcv(symbol, tf)
                    df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df = calc_indicators(df)
                    check_signal(df, symbol, tf)

            # Сводка каждые 15 минут
            if (now - last_summary_time) > timedelta(minutes=15):
                send_summary()
                last_summary_time = now

            # Ежедневная сводка в 23:00
            if now.hour == 23 and (now - last_daily_report).days >= 1:
                send_daily_report()
                last_daily_report = now

            time.sleep(60)

        except Exception as e:
            send_telegram(f"Ошибка: {e}")
            time.sleep(10)

# === Запуск ===
main_loop()
