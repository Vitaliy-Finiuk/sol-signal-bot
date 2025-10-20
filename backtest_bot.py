
import ccxt
import pandas as pd
import numpy as np
import ta
from datetime import datetime
import time
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

# === КОНФИГУРАЦИЯ ===
INITIAL_BALANCE = 100.0
RISK_PER_TRADE = 0.03
MAX_LEVERAGE = 7
COMMISSION = 0.0006
MIN_RISK_REWARD = 2.0

exchange = ccxt.okx({'enableRateLimit': True})

def fetch_historical_data(symbol, timeframe, days=180):
    """Загрузка исторических данных"""
    print(f"📥 Загрузка {symbol} {timeframe} за {days} дней...")
    
    since = exchange.milliseconds() - days * 24 * 60 * 60 * 1000
    all_ohlcv = []
    
    while since < exchange.milliseconds():
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1
            time.sleep(exchange.rateLimit / 1000)
        except Exception as e:
            print(f"⚠️ Ошибка: {e}")
            time.sleep(5)
            continue
    
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    print(f"✅ Загружено {len(df)} свечей\n")
    return df

# === СТРАТЕГИЯ 1: 4h Aggressive Turtle ===
def strategy_4h_turtle(df):
    """Turtle Trading с периодом 15"""
    df = df.copy()
    df['High_15'] = df['high'].rolling(window=15).max()
    df['Low_15'] = df['low'].rolling(window=15).min()
    df['EMA_21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['EMA_55'] = ta.trend.ema_indicator(df['close'], window=55)
    df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
    df['Volume_SMA'] = df['volume'].rolling(window=20).mean()
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    
    df['signal'] = 0
    df['sl_distance'] = 0.0
    df['tp_distance'] = 0.0
    
    for i in range(55, len(df)):
        close = df.iloc[i]['close']
        high_15 = df.iloc[i-1]['High_15']
        low_15 = df.iloc[i-1]['Low_15']
        ema21 = df.iloc[i]['EMA_21']
        ema55 = df.iloc[i]['EMA_55']
        atr = df.iloc[i]['ATR']
        adx = df.iloc[i]['ADX']
        volume = df.iloc[i]['volume']
        volume_sma = df.iloc[i]['Volume_SMA']
        rsi = df.iloc[i]['RSI']
        
        if pd.isna(atr) or pd.isna(adx) or pd.isna(rsi):
            continue
        
        # LONG
        if (close > high_15 and ema21 > ema55 and adx > 18 and 
            volume > volume_sma * 1.1 and rsi < 75):
            df.loc[df.index[i], 'signal'] = 1
            df.loc[df.index[i], 'sl_distance'] = atr * 1.8
            df.loc[df.index[i], 'tp_distance'] = atr * 5.5
        
        # SHORT
        elif (close < low_15 and ema21 < ema55 and adx > 18 and 
              volume > volume_sma * 1.1 and rsi > 25):
            df.loc[df.index[i], 'signal'] = -1
            df.loc[df.index[i], 'sl_distance'] = atr * 1.8
            df.loc[df.index[i], 'tp_distance'] = atr * 5.5
    
    return df

# === СТРАТЕГИЯ 2: 12h Momentum Breakout ===
def strategy_12h_momentum(df):
    """Bollinger + MACD + Volume"""
    df = df.copy()
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
    
    df['signal'] = 0
    df['sl_distance'] = 0.0
    df['tp_distance'] = 0.0
    
    for i in range(50, len(df)):
        close = df.iloc[i]['close']
        ema9 = df.iloc[i]['EMA_9']
        ema21 = df.iloc[i]['EMA_21']
        ema50 = df.iloc[i]['EMA_50']
        bb_upper = df.iloc[i]['BB_Upper']
        bb_lower = df.iloc[i]['BB_Lower']
        bb_width = df.iloc[i]['BB_Width']
        macd_val = df.iloc[i]['MACD']
        macd_sig = df.iloc[i]['MACD_Signal']
        macd_hist = df.iloc[i]['MACD_Hist']
        macd_hist_prev = df.iloc[i-1]['MACD_Hist']
        rsi = df.iloc[i]['RSI']
        atr = df.iloc[i]['ATR']
        volume_ratio = df.iloc[i]['Volume_Ratio']
        
        if pd.isna(atr) or pd.isna(rsi) or pd.isna(macd_val):
            continue
        
        # LONG
        if (close > bb_upper and ema9 > ema21 > ema50 and
            macd_hist > macd_hist_prev and macd_val > macd_sig and
            volume_ratio > 1.5 and 30 < rsi < 70 and bb_width > 0.02):
            df.loc[df.index[i], 'signal'] = 1
            df.loc[df.index[i], 'sl_distance'] = atr * 2.2
            df.loc[df.index[i], 'tp_distance'] = atr * 6.5
        
        # SHORT
        elif (close < bb_lower and ema9 < ema21 < ema50 and
              macd_hist < macd_hist_prev and macd_val < macd_sig and
              volume_ratio > 1.5 and 30 < rsi < 70 and bb_width > 0.02):
            df.loc[df.index[i], 'signal'] = -1
            df.loc[df.index[i], 'sl_distance'] = atr * 2.2
            df.loc[df.index[i], 'tp_distance'] = atr * 6.5
    
    return df

# === СТРАТЕГИЯ 3: 1d Strong Trend ===
def strategy_1d_trend(df):
    """Trend Following на дневках"""
    df = df.copy()
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
    
    df['signal'] = 0
    df['sl_distance'] = 0.0
    df['tp_distance'] = 0.0
    
    for i in range(100, len(df)):
        close = df.iloc[i]['close']
        ema20 = df.iloc[i]['EMA_20']
        ema50 = df.iloc[i]['EMA_50']
        ema100 = df.iloc[i]['EMA_100']
        adx = df.iloc[i]['ADX']
        plus_di = df.iloc[i]['+DI']
        minus_di = df.iloc[i]['-DI']
        rsi = df.iloc[i]['RSI']
        macd_val = df.iloc[i]['MACD']
        macd_sig = df.iloc[i]['MACD_Signal']
        atr = df.iloc[i]['ATR']
        
        if pd.isna(atr) or pd.isna(adx) or pd.isna(rsi):
            continue
        
        uptrend = ema20 > ema50 > ema100
        downtrend = ema20 < ema50 < ema100
        
        # LONG
        if (uptrend and close <= ema20 * 1.02 and close >= ema20 * 0.97 and
            adx > 22 and plus_di > minus_di and 40 < rsi < 60 and macd_val > macd_sig):
            df.loc[df.index[i], 'signal'] = 1
            df.loc[df.index[i], 'sl_distance'] = atr * 3.0
            df.loc[df.index[i], 'tp_distance'] = atr * 8.0
        
        # SHORT
        elif (downtrend and close >= ema20 * 0.98 and close <= ema20 * 1.03 and
              adx > 22 and minus_di > plus_di and 40 < rsi < 60 and macd_val < macd_sig):
            df.loc[df.index[i], 'signal'] = -1
            df.loc[df.index[i], 'sl_distance'] = atr * 3.0
            df.loc[df.index[i], 'tp_distance'] = atr * 8.0
    
    return df

# === БЭКТЕСТ С ГРАФИКАМИ ===
def backtest_with_charts(df, strategy_name, symbol, timeframe):
    """Бэктест с визуализацией сделок"""
    print(f"\n{'='*100}")
    print(f"🎯 {strategy_name}")
    print(f"📊 {symbol} | {timeframe}")
    print(f"📅 {df['timestamp'].min().strftime('%Y-%m-%d')} → {df['timestamp'].max().strftime('%Y-%m-%d')}")
    print(f"{'='*100}\n")
    
    balance = INITIAL_BALANCE
    trades = []
    position = None
    
    for i in range(len(df)):
        row = df.iloc[i]
        signal = row['signal']
        
        # Закрытие позиции
        if position is not None:
            current_price = row['close']
            
            if position['type'] == 'LONG':
                profit_pct = (current_price - position['entry']) / position['entry']
                
                # Trailing stop
                if profit_pct > 0.05:
                    position['stop_loss'] = max(position['stop_loss'], position['entry'] * 1.015)
                if profit_pct > 0.10:
                    position['stop_loss'] = max(position['stop_loss'], 
                                               position['entry'] + (current_price - position['entry']) * 0.7)
                
                if current_price <= position['stop_loss'] or current_price >= position['take_profit']:
                    pnl = (current_price - position['entry']) * position['size']
                    pnl -= position['size'] * position['entry'] * COMMISSION
                    pnl -= position['size'] * current_price * COMMISSION
                    balance += pnl
                    
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': row['timestamp'],
                        'type': position['type'],
                        'entry': position['entry'],
                        'exit': current_price,
                        'size': position['size'],
                        'leverage': position['leverage'],
                        'pnl': pnl,
                        'balance': balance,
                        'return_pct': profit_pct * 100
                    })
                    
                    position = None
            
            elif position['type'] == 'SHORT':
                profit_pct = (position['entry'] - current_price) / position['entry']
                
                if profit_pct > 0.05:
                    position['stop_loss'] = min(position['stop_loss'], position['entry'] * 0.985)
                if profit_pct > 0.10:
                    position['stop_loss'] = min(position['stop_loss'],
                                               position['entry'] - (position['entry'] - current_price) * 0.7)
                
                if current_price >= position['stop_loss'] or current_price <= position['take_profit']:
                    pnl = (position['entry'] - current_price) * position['size']
                    pnl -= position['size'] * position['entry'] * COMMISSION
                    pnl -= position['size'] * current_price * COMMISSION
                    balance += pnl
                    
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': row['timestamp'],
                        'type': position['type'],
                        'entry': position['entry'],
                        'exit': current_price,
                        'size': position['size'],
                        'leverage': position['leverage'],
                        'pnl': pnl,
                        'balance': balance,
                        'return_pct': profit_pct * 100
                    })
                    
                    position = None
        
        # Открытие позиции
        if position is None and signal != 0:
            entry_price = row['close']
            sl_distance = row['sl_distance']
            tp_distance = row['tp_distance']
            
            if tp_distance / sl_distance < MIN_RISK_REWARD:
                continue
            
            risk_amount = balance * RISK_PER_TRADE
            position_size_base = risk_amount / sl_distance
            leverage_used = min(MAX_LEVERAGE, (position_size_base * entry_price) / balance)
            position_size = (risk_amount * leverage_used) / sl_distance
            
            if signal == 1:  # LONG
                stop_loss = entry_price - sl_distance
                take_profit = entry_price + tp_distance
                
                position = {
                    'type': 'LONG',
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'size': position_size,
                    'leverage': leverage_used,
                    'entry_time': row['timestamp']
                }
            
            elif signal == -1:  # SHORT
                stop_loss = entry_price + sl_distance
                take_profit = entry_price - tp_distance
                
                position = {
                    'type': 'SHORT',
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'size': position_size,
                    'leverage': leverage_used,
                    'entry_time': row['timestamp']
                }
    
    # === СТАТИСТИКА ===
    print(f"\n{'='*100}")
    print(f"📊 РЕЗУЛЬТАТЫ")
    print(f"{'='*100}\n")
    
    if trades:
        trades_df = pd.DataFrame(trades)
        
        total = len(trades)
        wins = len(trades_df[trades_df['pnl'] > 0])
        losses = total - wins
        wr = (wins / total * 100) if total > 0 else 0
        
        total_pnl = trades_df['pnl'].sum()
        avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if wins > 0 else 0
        avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if losses > 0 else 0
        
        best = trades_df['pnl'].max()
        worst = trades_df['pnl'].min()
        
        win_sum = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
        loss_sum = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
        pf = win_sum / loss_sum if loss_sum > 0 else float('inf')
        
        final = balance
        roi = ((final - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
        
        avg_leverage = trades_df['leverage'].mean()
        avg_return = trades_df[trades_df['return_pct'] > 0]['return_pct'].mean() if wins > 0 else 0
        
        # Просадка
        trades_df['cum_balance'] = trades_df['balance']
        trades_df['peak'] = trades_df['cum_balance'].cummax()
        trades_df['dd'] = (trades_df['cum_balance'] - trades_df['peak']) / trades_df['peak'] * 100
        max_dd = trades_df['dd'].min()
        
        # Серии
        trades_df['win'] = trades_df['pnl'] > 0
        trades_df['streak'] = (trades_df['win'] != trades_df['win'].shift()).cumsum()
        win_streaks = trades_df[trades_df['win']].groupby('streak').size()
        loss_streaks = trades_df[~trades_df['win']].groupby('streak').size()
        max_win_streak = win_streaks.max() if len(win_streaks) > 0 else 0
        max_loss_streak = loss_streaks.max() if len(loss_streaks) > 0 else 0
        
        print(f"💰 Баланс: {INITIAL_BALANCE:.2f} → {final:.2f} USD")
        print(f"📈 PnL: {total_pnl:+.2f} USD ({roi:+.1f}%)")
        print(f"⚡ Среднее плечо: {avg_leverage:.1f}x")
        print(f"\n📊 Сделок: {total} | ✅ {wins} ({wr:.1f}%) | ❌ {losses}")
        print(f"💵 Ср. прибыль: +{avg_win:.2f} USD | Ср. убыток: {avg_loss:.2f} USD")
        print(f"🎯 Лучшая: +{best:.2f} USD | Худшая: {worst:.2f} USD")
        print(f"📊 Profit Factor: {pf:.2f}")
        print(f"📈 Средний возврат: {avg_return:.1f}%")
        print(f"📉 Макс. просадка: {max_dd:.2f}%")
        print(f"🔥 Макс. серия побед: {max_win_streak} | Макс. серия поражений: {max_loss_streak}")
        
        if total < 30:
            print(f"\n⚠️  ВНИМАНИЕ: Малая выборка ({total} сделок) - результаты могут быть нерепрезентативными!")
        
        # === ГРАФИК ===
        plot_results(df, trades_df, strategy_name, symbol, timeframe)
        
        return trades_df, {
            'total': total,
            'wins': wins,
            'wr': wr,
            'pnl': total_pnl,
            'roi': roi,
            'pf': pf,
            'max_dd': max_dd,
            'avg_leverage': avg_leverage
        }
    else:
        print("⚠️ Нет сделок")
        return None, {'total': 0, 'wins': 0, 'wr': 0, 'pnl': 0, 'roi': 0, 'pf': 0, 
                      'max_dd': 0, 'avg_leverage': 0}

# === ВИЗУАЛИЗАЦИЯ ===
def plot_results(df, trades_df, strategy_name, symbol, timeframe):
    """Создание графика с сделками"""
    fig = plt.figure(figsize=(16, 10))
    gs = GridSpec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.3)
    
    # График 1: Цена + Сделки
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(df['timestamp'], df['close'], label='Цена', linewidth=1, color='gray', alpha=0.7)
    
    # Отображение сделок
    for _, trade in trades_df.iterrows():
        color = 'green' if trade['pnl'] > 0 else 'red'
        marker = '^' if trade['type'] == 'LONG' else 'v'
        
        # Вход
        ax1.scatter(trade['entry_time'], trade['entry'], color='blue', s=100, 
                   marker=marker, zorder=5, edgecolors='black', linewidths=1.5)
        
        # Выход
        ax1.scatter(trade['exit_time'], trade['exit'], color=color, s=100, 
                   marker='o', zorder=5, edgecolors='black', linewidths=1.5)
        
        # Линия сделки
        ax1.plot([trade['entry_time'], trade['exit_time']], 
                [trade['entry'], trade['exit']], 
                color=color, alpha=0.5, linewidth=2)
    
    ax1.set_title(f'{strategy_name} | {symbol} {timeframe}', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Цена (USDT)', fontsize=11)
    ax1.grid(alpha=0.3)
    ax1.legend(['Цена', 'Вход LONG', 'Вход SHORT', 'Выход (profit)', 'Выход (loss)'], 
              loc='upper left', fontsize=9)
    
    # График 2: Баланс
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(trades_df['exit_time'], trades_df['balance'], color='blue', linewidth=2)
    ax2.axhline(INITIAL_BALANCE, color='gray', linestyle='--', alpha=0.5)
    ax2.fill_between(trades_df['exit_time'], trades_df['balance'], INITIAL_BALANCE, 
                     where=(trades_df['balance'] >= INITIAL_BALANCE), 
                     color='green', alpha=0.2)
    ax2.fill_between(trades_df['exit_time'], trades_df['balance'], INITIAL_BALANCE, 
                     where=(trades_df['balance'] < INITIAL_BALANCE), 
                     color='red', alpha=0.2)
    ax2.set_ylabel('Баланс (USD)', fontsize=11)
    ax2.grid(alpha=0.3)
    
    # График 3: PnL по сделкам
    ax3 = fig.add_subplot(gs[2])
    colors = ['green' if x > 0 else 'red' for x in trades_df['pnl']]
    ax3.bar(range(len(trades_df)), trades_df['pnl'], color=colors, alpha=0.7)
    ax3.axhline(0, color='black', linestyle='-', linewidth=0.5)
    ax3.set_ylabel('PnL (USD)', fontsize=11)
    ax3.set_xlabel('Номер сделки', fontsize=11)
    ax3.grid(alpha=0.3)
    
    # График 4: Просадка
    ax4 = fig.add_subplot(gs[3])
    ax4.plot(trades_df['exit_time'], trades_df['dd'], color='red', linewidth=2)
    ax4.fill_between(trades_df['exit_time'], 0, trades_df['dd'], color='red', alpha=0.3)
    ax4.set_ylabel('Просадка (%)', fontsize=11)
    ax4.set_xlabel('Время', fontsize=11)
    ax4.grid(alpha=0.3)
    
    plt.tight_layout()
    filename = f"{strategy_name.replace(' ', '_')}_{symbol.replace('/', '_')}_{timeframe}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"\n📊 График сохранён: {filename}")
    plt.close()

# === ГЛАВНАЯ ФУНКЦИЯ ===


# === ГЛАВНАЯ ФУНКЦИЯ ===




# === ГЛАВНАЯ ФУНКЦИЯ ===
def main():
    print("=" * 100)
    print("🚀 ТЕСТИРОВАНИЕ СТРАТЕГИЙ НА ИСТОРИЧЕСКИХ ДАННЫХ")
    print("💰 Депозит: $100 | Риск: 3% | Плечо: до 7x")
    print("=" * 100)
    
    # Тестируемые пары и стратегии
    test_configs = [
        ('SOL/USDT', '4h', strategy_4h_turtle, '4h Aggressive Turtle', 180),
        ('SOL/USDT', '12h', strategy_12h_momentum, '12h Momentum Breakout', 180),
        ('SOL/USDT', '1d', strategy_1d_trend, '1d Strong Trend Following', 180),
        
        ('BTC/USDT', '4h', strategy_4h_turtle, '4h Aggressive Turtle', 180),
        ('ETH/USDT', '4h', strategy_4h_turtle, '4h Aggressive Turtle', 180),
    ]
    
    all_results = []
    
    for symbol, timeframe, strategy_func, strategy_name, days in test_configs:
        try:
            # Загрузка данных
            df = fetch_historical_data(symbol, timeframe, days)
            
            # Применение стратегии
            df = strategy_func(df)
            
            # Бэктест
            trades_df, stats = backtest_with_charts(df, strategy_name, symbol, timeframe)
            
            all_results.append({
                'symbol': symbol,
                'timeframe': timeframe,
                'strategy': strategy_name,
                'stats': stats
            })
            
            time.sleep(3)  # Пауза между запросами
            
        except Exception as e:
            print(f"❌ Ошибка {symbol} {timeframe}: {e}\n")
            continue
    
    # === ИТОГОВАЯ СВОДКА ===
    print("\n" + "=" * 100)
    print("📊 ИТОГОВАЯ СВОДКА ПО ВСЕМ ТЕСТАМ")
    print("=" * 100)
    print(f"{'Инструмент':<12} | {'TF':<4} | {'Стратегия':<30} | {'Сделок':<7} | {'WR%':<6} | {'PnL':<10} | {'ROI%':<8} | {'DD%':<7} | {'PF':<6}")
    print("-" * 100)
    
    best_result = None
    best_roi = -float('inf')
    
    for result in all_results:
        stats = result['stats']
        print(f"{result['symbol']:<12} | {result['timeframe']:<4} | {result['strategy']:<30} | "
              f"{stats['total']:<7} | {stats['wr']:>5.1f}% | {stats['pnl']:>+9.2f} | "
              f"{stats['roi']:>+7.1f}% | {stats['max_dd']:>6.1f}% | {stats['pf']:>5.2f}")
        
        if stats['roi'] > best_roi:
            best_roi = stats['roi']
            best_result = result
    
    print("-" * 100)
    
    # Лучшая стратегия
    if best_result:
        print("\n" + "=" * 100)
        print("🏆 ЛУЧШАЯ СТРАТЕГИЯ")
        print("=" * 100)
        print(f"📊 {best_result['symbol']} | {best_result['timeframe']} | {best_result['strategy']}")
        print(f"💰 ROI: {best_result['stats']['roi']:+.1f}% | PnL: {best_result['stats']['pnl']:+.2f} USD")
        print(f"📈 Win Rate: {best_result['stats']['wr']:.1f}% | Сделок: {best_result['stats']['total']}")
        print(f"🛡️  Макс. просадка: {best_result['stats']['max_dd']:.1f}%")
        print(f"🎯 Profit Factor: {best_result['stats']['pf']:.2f}")
    
    # Рекомендации
    print("\n" + "=" * 100)
    print("💡 РЕКОМЕНДАЦИИ")
    print("=" * 100)
    
    profitable_strategies = [r for r in all_results if r['stats']['roi'] > 0]
    if profitable_strategies:
        print("✅ ПРИБЫЛЬНЫЕ СТРАТЕГИИ:")
        for strategy in profitable_strategies:
            print(f"   • {strategy['symbol']} {strategy['timeframe']} - {strategy['strategy']} "
                  f"(ROI: {strategy['stats']['roi']:+.1f}%)")
    else:
        print("❌ Прибыльных стратегий не найдено. Рекомендуется:")
        print("   • Увеличить период тестирования")
        print("   • Настроить параметры стратегий")
        print("   • Протестировать другие торговые пары")
    
    # Общие рекомендации
    print("\n📝 ОБЩИЕ СОВЕТЫ:")
    print("   • Протестируйте стратегии на большем объеме данных (1+ год)")
    print("   • Добавьте фильтр волатильности для избежания шумовых сигналов")
    print("   • Рассмотрите комбинирование нескольких таймфреймов")
    print("   • Всегда используйте стоп-лосс и управление капиталом")
    
    return all_results

# === ОПТИМИЗАЦИЯ ПАРАМЕТРОВ ===
def optimize_strategy(df, strategy_func, param_grid):
    """Простая оптимизация параметров стратегии"""
    print("🔄 Запуск оптимизации параметров...")
    
    best_params = None
    best_roi = -float('inf')
    best_trades = None
    
    # Пример простого перебора параметров
    for risk_reward in [1.5, 2.0, 2.5, 3.0]:
        global MIN_RISK_REWARD
        MIN_RISK_REWARD = risk_reward
        
        optimized_df = strategy_func(df)
        trades_df, stats = backtest_with_charts(optimized_df, f"Optimized RR={risk_reward}", "OPT", "4h")
        
        if stats['roi'] > best_roi and stats['total'] > 10:
            best_roi = stats['roi']
            best_params = {'risk_reward': risk_reward}
            best_trades = trades_df
    
    print(f"🎯 Лучшие параметры: {best_params} (ROI: {best_roi:.1f}%)")
    return best_params, best_trades

# === АНАЛИЗ РЫНОЧНЫХ УСЛОВИЙ ===
def analyze_market_regimes(df):
    """Анализ рыночных режимов"""
    print("\n📊 АНАЛИЗ РЫНОЧНЫХ УСЛОВИЙ")
    
    # Волатильность
    df['volatility'] = df['high'].rolling(20).std() / df['close'].rolling(20).mean() * 100
    current_vol = df['volatility'].iloc[-1]
    vol_avg = df['volatility'].mean()
    
    # Тренд
    df['trend'] = df['close'].rolling(50).apply(lambda x: (x[-1] - x[0]) / x[0] * 100)
    current_trend = df['trend'].iloc[-1]
    
    print(f"📈 Текущая волатильность: {current_vol:.1f}% (средняя: {vol_avg:.1f}%)")
    print(f"📊 Текущий тренд (50 периодов): {current_trend:+.1f}%")
    
    if current_vol > vol_avg * 1.5:
        print("⚡ ВЫСОКАЯ ВОЛАТИЛЬНОСТЬ - будьте осторожны!")
    elif current_vol < vol_avg * 0.7:
        print("😴 НИЗКАЯ ВОЛАТИЛЬНОСТЬ - возможны ложные пробои")
    
    if abs(current_trend) > 20:
        print(f"🎯 СИЛЬНЫЙ ТРЕНД - {'бычий' if current_trend > 0 else 'медвежий'}")

# === ЗАПУСК ПРОГРАММЫ ===
if __name__ == "__main__":
    try:
        # Проверка подключения к бирже
        print("🔌 Проверка подключения к OKX...")
        exchange.load_markets()
        print("✅ Подключение успешно!")
        
        # Запуск основного тестирования
        results = main()
        
        # Дополнительный анализ
        if results:
            # Анализ для первой стратегии
            sample_symbol = 'SOL/USDT'
            sample_timeframe = '4h'
            
            print(f"\n🔍 ДЕТАЛЬНЫЙ АНАЛИЗ ДЛЯ {sample_symbol} {sample_timeframe}")
            df_sample = fetch_historical_data(sample_symbol, sample_timeframe, 365)
            analyze_market_regimes(df_sample)
            
            # Оптимизация параметров (опционально)
            if len(results) > 0:
                print("\n🔄 ЗАПУСК ОПТИМИЗАЦИИ ПАРАМЕТРОВ...")
                best_params, best_trades = optimize_strategy(df_sample, strategy_4h_turtle, {})
        
        print("\n" + "=" * 100)
        print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО!")
        print("=" * 100)
        print("💡 Помните: исторические результаты не гарантируют будущую прибыльность.")
        print("📚 Всегда тестируйте стратегии на демо-счете перед реальной торговлей.")
        
    except KeyboardInterrupt:
        print("\n⏹️  Программа остановлена пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        print("🔧 Проверьте:")
        print("   • Интернет-подключение")
        print("   • Доступность биржи OKX")
        print("   • Корректность торговой пары")