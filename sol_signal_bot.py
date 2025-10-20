import ccxt
import pandas as pd
import time
import requests
import ta
import os
import threading
from flask import Flask
import matplotlib
matplotlib.use('Agg')  # Для работы без GUI
import matplotlib.pyplot as plt
from io import BytesIO
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

def send_telegram(msg, img=None):
    try:
        if not TELEGRAM_TOKEN or not CHAT_ID:
            print("⚠️ Telegram credentials not set")
            return
            
        if img is None:
            data = {'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
            resp = requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage', 
                               data=data, timeout=10)
            if resp.status_code != 200:
                print(f"Telegram send error: {resp.text}")
        else:
            files = {'photo': img.getvalue()}
            data = {'chat_id': CHAT_ID, 'caption': msg, 'parse_mode': 'Markdown'}
            resp = requests.post(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto', 
                               data=data, files=files, timeout=15)
            if resp.status_code != 200:
                print(f"Telegram photo error: {resp.text}")
    except Exception as e:
        print(f"Telegram error: {e}")

# === Flask keep-alive ===
app = Flask(__name__)
@app.route("/")
def home():
    return "🚀 Signal Bot Active | Strategies: 4h Turtle, 12h Momentum, 1d Trend"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000), daemon=True).start()

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
stats = {s: {tf: {'LONG': 0, 'SHORT': 0, 'Total': 0, 'Signals': []} for tf in timeframes} for s in symbols}
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

# === СТРАТЕГИЯ 1: 4h Turtle ===
def strategy_4h_turtle(df):
    try:
        if len(df) < 55:
            return None, {}
        
        df['High_15'] = df['high'].rolling(window=15).max()
        df['Low_15'] = df['low'].rolling(window=15).min()
        df['EMA_21'] = ta.trend.ema_indicator(df['close'], window=21)
        df['EMA_55'] = ta.trend.ema_indicator(df['close'], window=55)
        df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
        df['Volume_SMA'] = df['volume'].rolling(window=20).mean()
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        if pd.isna(last['ATR']) or pd.isna(last['ADX']) or pd.isna(last['RSI']):
            return None, {}
        
        close = last['close']
        high_15 = prev['High_15']
        low_15 = prev['Low_15']
        ema21 = last['EMA_21']
        ema55 = last['EMA_55']
        atr = last['ATR']
        adx = last['ADX']
        volume = last['volume']
        volume_sma = last['Volume_SMA']
        rsi = last['RSI']
        
        signal = None
        params = {}
        
        if (close > high_15 and ema21 > ema55 and adx > 18 and 
            volume > volume_sma * 1.1 and rsi < 75):
            signal = 'LONG'
            params = {'entry': close, 'sl_distance': atr * 1.8, 'tp_distance': atr * 5.5, 'atr': atr}
        
        elif (close < low_15 and ema21 < ema55 and adx > 18 and 
              volume > volume_sma * 1.1 and rsi > 25):
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
        
        df['EMA_9'] = ta.trend.ema_indicator(df['close'], window=9)
        df['EMA_21'] = ta.trend.ema_indicator(df['close'], window=21)
        df['EMA_50'] = ta.trend.ema_indicator(df['close'], window=50)
        
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['BB_Upper'] = bb.bollinger_hband()
        df['BB_Lower'] = bb.bollinger_lband()
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['close']
        
        macd = ta.trend.MACD(df['close'])
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        df['MACD_Hist'] = macd.macd_diff()
        
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        df['Volume_SMA'] = df['volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['volume'] / df['Volume_SMA']
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        if pd.isna(last['ATR']) or pd.isna(last['RSI']) or pd.isna(last['MACD']):
            return None, {}
        
        close = last['close']
        ema9 = last['EMA_9']
        ema21 = last['EMA_21']
        ema50 = last['EMA_50']
        bb_upper = last['BB_Upper']
        bb_lower = last['BB_Lower']
        bb_width = last['BB_Width']
        macd_val = last['MACD']
        macd_sig = last['MACD_Signal']
        macd_hist = last['MACD_Hist']
        macd_hist_prev = prev['MACD_Hist']
        rsi = last['RSI']
        atr = last['ATR']
        volume_ratio = last['Volume_Ratio']
        
        signal = None
        params = {}
        
        if (close > bb_upper and ema9 > ema21 > ema50 and
            macd_hist > macd_hist_prev and macd_val > macd_sig and
            volume_ratio > 1.5 and 30 < rsi < 70 and bb_width > 0.02):
            signal = 'LONG'
            params = {'entry': close, 'sl_distance': atr * 2.2, 'tp_distance': atr * 6.5, 'atr': atr}
        
        elif (close < bb_lower and ema9 < ema21 < ema50 and
              macd_hist < macd_hist_prev and macd_val < macd_sig and
              volume_ratio > 1.5 and 30 < rsi < 70 and bb_width > 0.02):
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
        
        df['EMA_20'] = ta.trend.ema_indicator(df['close'], window=20)
        df['EMA_50'] = ta.trend.ema_indicator(df['close'], window=50)
        df['EMA_100'] = ta.trend.ema_indicator(df['close'], window=100)
        df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
        df['+DI'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=14)
        df['-DI'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=14)
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
        
        macd = ta.trend.MACD(df['close'])
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        
        last = df.iloc[-1]
        
        if pd.isna(last['ATR']) or pd.isna(last['ADX']) or pd.isna(last['RSI']):
            return None, {}
        
        close = last['close']
        ema20 = last['EMA_20']
        ema50 = last['EMA_50']
        ema100 = last['EMA_100']
        adx = last['ADX']
        plus_di = last['+DI']
        minus_di = last['-DI']
        rsi = last['RSI']
        macd_val = last['MACD']
        macd_sig = last['MACD_Signal']
        atr = last['ATR']
        
        uptrend = ema20 > ema50 > ema100
        downtrend = ema20 < ema50 < ema100
        
        signal = None
        params = {}
        
        if (uptrend and close <= ema20 * 1.02 and close >= ema20 * 0.97 and
            adx > 22 and plus_di > minus_di and 40 < rsi < 60 and macd_val > macd_sig):
            signal = 'LONG'
            params = {'entry': close, 'sl_distance': atr * 3.0, 'tp_distance': atr * 8.0, 'atr': atr}
        
        elif (downtrend and close >= ema20 * 0.98 and close <= ema20 * 1.03 and
              adx > 22 and minus_di > plus_di and 40 < rsi < 60 and macd_val < macd_sig):
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

# === График ===
def plot_signal(df, signal_type, symbol, timeframe, params):
    try:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
        
        ax1.plot(df['timestamp'], df['close'], label='Close', linewidth=1.5)
        
        last = df.iloc[-1]
        color = 'lime' if signal_type == 'LONG' else 'red'
        marker = '^' if signal_type == 'LONG' else 'v'
        
        ax1.scatter(last['timestamp'], last['close'], color=color, s=200, marker=marker, 
                   label=f'{signal_type} Signal', zorder=5, edgecolors='black', linewidths=2)
        
        if signal_type == 'LONG':
            sl_price = params['entry'] - params['sl_distance']
            tp_price = params['entry'] + params['tp_distance']
        else:
            sl_price = params['entry'] + params['sl_distance']
            tp_price = params['entry'] - params['tp_distance']
        
        ax1.axhline(sl_price, color='red', linestyle='--', alpha=0.7, label=f'SL: {sl_price:.2f}')
        ax1.axhline(tp_price, color='green', linestyle='--', alpha=0.7, label=f'TP: {tp_price:.2f}')
        ax1.axhline(params['entry'], color='yellow', linestyle=':', alpha=0.8, label=f'Entry: {params["entry"]:.2f}')
        
        ax1.set_title(f'{symbol} | {timeframe} | {signal_type} Signal', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Price (USDT)', fontsize=11)
        ax1.legend(loc='upper left', fontsize=9)
        ax1.grid(alpha=0.3)
        
        colors = ['green' if df.iloc[i]['close'] >= df.iloc[i]['open'] else 'red' 
                 for i in range(len(df))]
        ax2.bar(df['timestamp'], df['volume'], color=colors, alpha=0.6, width=0.8)
        ax2.set_ylabel('Volume', fontsize=11)
        ax2.set_xlabel('Time', fontsize=11)
        ax2.grid(alpha=0.3)
        
        plt.tight_layout()
        
        img = BytesIO()
        plt.savefig(img, format='png', dpi=100, bbox_inches='tight')
        img.seek(0)
        plt.close(fig)
        return img
    except Exception as e:
        print(f"Plot error: {e}")
        return None

# === Проверка сигналов ===
def check_signal(df, symbol, timeframe):
    try:
        if len(df) < 20:  # Минимальное количество свечей для расчета индикаторов
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
        stats[symbol][timeframe]['Signals'].append({
            'time': now,
            'type': signal,
            'entry': entry,
            'sl': stop_loss,
            'tp': take_profit
        })
        
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
        
        img = plot_signal(df, signal, symbol, timeframe, params)
        send_telegram(msg, img)
        
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

# === Ежедневная сводка ===
def send_daily_report():
    msg = f"📈 *Ежедневный отчёт*\n`{datetime.now().strftime('%Y-%m-%d')}`\n{'='*30}\n\n"
    
    for s in symbols:
        symbol_total = sum(stats[s][tf]['Total'] for tf in timeframes)
        if symbol_total > 0:
            msg += f"*{s}*\n"
            for tf in timeframes:
                st = stats[s][tf]
                if st['Total'] > 0:
                    long_pct = (st['LONG'] / st['Total'] * 100) if st['Total'] > 0 else 0
                    short_pct = (st['SHORT'] / st['Total'] * 100) if st['Total'] > 0 else 0
                    msg += f"  {tf}: 📈{long_pct:.0f}% 📉{short_pct:.0f}% ({st['Total']})\n"
            msg += "\n"
    
    if all(sum(stats[s][tf]['Total'] for tf in timeframes) == 0 for s in symbols):
        msg += "_Пока нет сигналов за сегодня_\n"
    
    total_today = sum(stats[s][tf]['Total'] for s in symbols for tf in timeframes)
    msg += f"{'='*30}\n🎯 Итого за день: *{total_today}* сигналов"
    
    send_telegram(msg)

# === Основной цикл ===
def main():
    global last_summary_time, last_daily_report
    
    print("🚀 Starting Signal Bot...")
    send_telegram("🤖 *Signal Bot Started!*\nMonitoring: SOL, BTC, ETH, BNB\nTimeframes: 4h, 12h, 1d")
    
    while True:
        try:
            now = datetime.now()
            
            # Ежедневный отчет в 08:00
            if now.hour == 8 and now.minute == 0 and (now - last_daily_report).total_seconds() > 3600:
                send_daily_report()
                last_daily_report = now
            
            # Сводка каждые 6 часов
            if (now - last_summary_time).total_seconds() > 21600:  # 6 часов
                send_summary()
                last_summary_time = now
            
            # Проверка сигналов для каждого символа и таймфрейма
            for symbol in symbols:
                for timeframe in timeframes:
                    try:
                        # Запрашиваем только последние 100 свечей (для расчета индикаторов)
                        ohlcv = safe_fetch_ohlcv(symbol, timeframe, limit=100)
                        if ohlcv:
                            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                            
                            check_signal(df, symbol, timeframe)
                        else:
                            print(f"⚠️ No data for {symbol} {timeframe}")
                            
                    except Exception as e:
                        print(f"Error processing {symbol} {timeframe}: {e}")
            
            # Очистка старых сигналов (старше 7 дней)
            week_ago = now - timedelta(days=7)
            for s in symbols:
                for tf in timeframes:
                    stats[s][tf]['Signals'] = [sig for sig in stats[s][tf]['Signals'] 
                                             if sig['time'] > week_ago]
            
            print(f"✅ Cycle completed at {now.strftime('%H:%M')}")
            time.sleep(60)  # Пауза 1 минута между циклами
            
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(300)  # Пауза 5 минут при ошибке

if __name__ == "__main__":
    main()