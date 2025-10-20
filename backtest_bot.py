import ccxt
import pandas as pd
import numpy as np
import ta
from datetime import datetime, timedelta
import time

# === АГРЕССИВНАЯ КОНФИГУРАЦИЯ для малого депозита ===
INITIAL_BALANCE = 100.0
RISK_PER_TRADE = 0.03  # 3% риска (агрессивнее)
MAX_LEVERAGE = 7  # Увеличили до 7x для малого депозита
COMMISSION = 0.0006
MIN_RISK_REWARD = 2.0

exchange = ccxt.okx({'enableRateLimit': True})

def fetch_historical_data(symbol, timeframe, days=90):
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

# === ОБНОВЛЕННАЯ СТРАТЕГИЯ 1: 4h - Агрессивный Turtle ===
def strategy_4h_aggressive_turtle(df):
    """
    Turtle Trading с более частыми входами
    - Снижен период с 20 до 15 (больше сигналов)
    - Добавлен фильтр по Volume
    - Увеличено плечо для максимизации прибыли
    """
    # Donchian Channels (15 вместо 20)
    df['High_15'] = df['high'].rolling(window=15).max()
    df['Low_15'] = df['low'].rolling(window=15).min()
    
    # EMA
    df['EMA_21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['EMA_55'] = ta.trend.ema_indicator(df['close'], window=55)
    
    # ATR
    df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    
    # ADX
    df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
    
    # Volume
    df['Volume_SMA'] = df['volume'].rolling(window=20).mean()
    
    # RSI для дополнительного фильтра
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
        
        # LONG: пробой + тренд вверх + объем + RSI не перегрет
        if (close > high_15 and 
            ema21 > ema55 and 
            adx > 18 and  # снизили порог
            volume > volume_sma * 1.1 and  # смягчили требование
            rsi < 75):  # не входим в явном перекупе
            df.loc[df.index[i], 'signal'] = 1
            df.loc[df.index[i], 'sl_distance'] = atr * 1.8  # чуть уже стоп
            df.loc[df.index[i], 'tp_distance'] = atr * 5.5  # R:R ~ 3:1
        
        # SHORT: пробой + тренд вниз + объем + RSI не перепродан
        elif (close < low_15 and 
              ema21 < ema55 and 
              adx > 18 and 
              volume > volume_sma * 1.1 and
              rsi > 25):
            df.loc[df.index[i], 'signal'] = -1
            df.loc[df.index[i], 'sl_distance'] = atr * 1.8
            df.loc[df.index[i], 'tp_distance'] = atr * 5.5
    
    return df

# === УЛУЧШЕННАЯ СТРАТЕГИЯ 2: 12h - Momentum Breakout ===
def strategy_12h_momentum(df):
    """
    Агрессивная momentum стратегия
    - Вход на импульсных пробоях с подтверждением
    - Высокий R:R для компенсации меньшего Win Rate
    """
    # EMA лента
    df['EMA_9'] = ta.trend.ema_indicator(df['close'], window=9)
    df['EMA_21'] = ta.trend.ema_indicator(df['close'], window=21)
    df['EMA_50'] = ta.trend.ema_indicator(df['close'], window=50)
    
    # Bollinger Bands
    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['BB_Upper'] = bb.bollinger_hband()
    df['BB_Lower'] = bb.bollinger_lband()
    df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['close']  # ширина в %
    
    # MACD
    macd = ta.trend.MACD(df['close'])
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()
    df['MACD_Hist'] = macd.macd_diff()
    
    # RSI
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    
    # ATR
    df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    
    # Volume
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
        
        # LONG: цена пробивает BB верх + EMA выстроены + MACD растет + всплеск объема
        if (close > bb_upper and 
            ema9 > ema21 > ema50 and
            macd_hist > macd_hist_prev and macd_val > macd_sig and
            volume_ratio > 1.5 and  # всплеск объема
            30 < rsi < 70 and
            bb_width > 0.02):  # достаточная волатильность
            df.loc[df.index[i], 'signal'] = 1
            df.loc[df.index[i], 'sl_distance'] = atr * 2.2
            df.loc[df.index[i], 'tp_distance'] = atr * 6.5  # R:R ~ 3:1
        
        # SHORT: цена пробивает BB низ + EMA выстроены вниз + MACD падает + всплеск объема
        elif (close < bb_lower and 
              ema9 < ema21 < ema50 and
              macd_hist < macd_hist_prev and macd_val < macd_sig and
              volume_ratio > 1.5 and
              30 < rsi < 70 and
              bb_width > 0.02):
            df.loc[df.index[i], 'signal'] = -1
            df.loc[df.index[i], 'sl_distance'] = atr * 2.2
            df.loc[df.index[i], 'tp_distance'] = atr * 6.5
    
    return df

# === НОВАЯ СТРАТЕГИЯ 3: 1d - Strong Trend Following ===
def strategy_1d_strong_trend(df):
    """
    Упрощенная трендовая стратегия для дневок
    - Следование за сильными трендами
    - Вход на откатах к EMA
    - Меньше фильтров = больше сигналов
    """
    # EMA
    df['EMA_20'] = ta.trend.ema_indicator(df['close'], window=20)
    df['EMA_50'] = ta.trend.ema_indicator(df['close'], window=50)
    df['EMA_100'] = ta.trend.ema_indicator(df['close'], window=100)
    
    # ADX и DI
    df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
    df['+DI'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=14)
    df['-DI'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=14)
    
    # RSI
    df['RSI'] = ta.momentum.rsi(df['close'], window=14)
    
    # ATR
    df['ATR'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'], window=14)
    
    # MACD для подтверждения
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
        
        # Определяем тренд
        uptrend = ema20 > ema50 > ema100
        downtrend = ema20 < ema50 < ema100
        
        # LONG: восходящий тренд + откат к EMA20 + ADX сильный + DI подтверждает
        if (uptrend and 
            close <= ema20 * 1.02 and close >= ema20 * 0.97 and  # около EMA20
            adx > 22 and plus_di > minus_di and
            40 < rsi < 60 and
            macd_val > macd_sig):
            df.loc[df.index[i], 'signal'] = 1
            df.loc[df.index[i], 'sl_distance'] = atr * 3
            df.loc[df.index[i], 'tp_distance'] = atr * 8  # R:R ~ 2.7:1
        
        # SHORT: нисходящий тренд + откат к EMA20 + ADX сильный + DI подтверждает
        elif (downtrend and 
              close >= ema20 * 0.98 and close <= ema20 * 1.03 and
              adx > 22 and minus_di > plus_di and
              40 < rsi < 60 and
              macd_val < macd_sig):
            df.loc[df.index[i], 'signal'] = -1
            df.loc[df.index[i], 'sl_distance'] = atr * 3
            df.loc[df.index[i], 'tp_distance'] = atr * 8
    
    return df

# === Агрессивный бэктест с высоким плечом ===
def backtest_aggressive(df, strategy_name, symbol, timeframe):
    print(f"\n{'='*90}")
    print(f"🎯 {strategy_name}")
    print(f"📊 {symbol} | {timeframe}")
    print(f"📅 {df['timestamp'].min().strftime('%Y-%m-%d')} → {df['timestamp'].max().strftime('%Y-%m-%d')}")
    print(f"⚡ АГРЕССИВНЫЙ РЕЖИМ: Плечо до {MAX_LEVERAGE}x | Риск {RISK_PER_TRADE*100}%")
    print(f"{'='*90}\n")
    
    balance = INITIAL_BALANCE
    trades = []
    position = None
    peak_balance = INITIAL_BALANCE
    
    for i in range(len(df)):
        row = df.iloc[i]
        signal = row['signal']
        
        if position is not None:
            current_price = row['close']
            
            # Агрессивный trailing stop
            if position['type'] == 'LONG':
                profit_pct = (current_price - position['entry']) / position['entry']
                
                # При 5% прибыли - безубыток
                if profit_pct > 0.05:
                    position['stop_loss'] = max(position['stop_loss'], position['entry'] * 1.015)
                
                # При 10% прибыли - фиксируем 70% прибыли
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
                        'hold_days': (row['timestamp'] - position['entry_time']).total_seconds() / 86400,
                        'return_pct': profit_pct * 100
                    })
                    
                    result = "✅ TP" if current_price >= position['take_profit'] else "⚠️ SL"
                    print(f"{result} LONG | {position['entry']:.4f} → {current_price:.4f} | "
                          f"PnL: {pnl:+.2f} USD ({profit_pct*100:+.1f}%) | "
                          f"Плечо: {position['leverage']:.1f}x | Баланс: {balance:.2f} USD")
                    
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
                        'hold_days': (row['timestamp'] - position['entry_time']).total_seconds() / 86400,
                        'return_pct': profit_pct * 100
                    })
                    
                    result = "✅ TP" if current_price <= position['take_profit'] else "⚠️ SL"
                    print(f"{result} SHORT | {position['entry']:.4f} → {current_price:.4f} | "
                          f"PnL: {pnl:+.2f} USD ({profit_pct*100:+.1f}%) | "
                          f"Плечо: {position['leverage']:.1f}x | Баланс: {balance:.2f} USD")
                    
                    position = None
        
        # Открытие позиции с высоким плечом
        if position is None and signal != 0:
            entry_price = row['close']
            sl_distance = row['sl_distance']
            tp_distance = row['tp_distance']
            
            if tp_distance / sl_distance < MIN_RISK_REWARD:
                continue
            
            if signal == 1:  # LONG
                stop_loss = entry_price - sl_distance
                take_profit = entry_price + tp_distance
                
                # Агрессивный расчет позиции
                risk_amount = balance * RISK_PER_TRADE
                position_size_base = risk_amount / sl_distance
                
                # Используем максимальное плечо
                leverage_used = MAX_LEVERAGE
                position_size = min(position_size_base * leverage_used, 
                                   balance * MAX_LEVERAGE / entry_price)
                
                # Эффективное плечо
                effective_leverage = (position_size * entry_price) / balance
                
                position = {
                    'type': 'LONG',
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'size': position_size,
                    'leverage': effective_leverage,
                    'entry_time': row['timestamp']
                }
                
                rr = tp_distance / sl_distance
                potential_profit = tp_distance * position_size
                print(f"🟢 LONG | {entry_price:.4f} | SL: {stop_loss:.4f} | TP: {take_profit:.4f} | "
                      f"R:R {rr:.1f}:1 | Плечо: {effective_leverage:.1f}x | "
                      f"Потенциал: +{potential_profit:.2f} USD")
            
            elif signal == -1:  # SHORT
                stop_loss = entry_price + sl_distance
                take_profit = entry_price - tp_distance
                
                risk_amount = balance * RISK_PER_TRADE
                position_size_base = risk_amount / sl_distance
                
                leverage_used = MAX_LEVERAGE
                position_size = min(position_size_base * leverage_used,
                                   balance * MAX_LEVERAGE / entry_price)
                
                effective_leverage = (position_size * entry_price) / balance
                
                position = {
                    'type': 'SHORT',
                    'entry': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'size': position_size,
                    'leverage': effective_leverage,
                    'entry_time': row['timestamp']
                }
                
                rr = tp_distance / sl_distance
                potential_profit = tp_distance * position_size
                print(f"🔴 SHORT | {entry_price:.4f} | SL: {stop_loss:.4f} | TP: {take_profit:.4f} | "
                      f"R:R {rr:.1f}:1 | Плечо: {effective_leverage:.1f}x | "
                      f"Потенциал: +{potential_profit:.2f} USD")
        
        if balance > peak_balance:
            peak_balance = balance
    
    # Статистика
    print(f"\n{'='*90}")
    print(f"📊 РЕЗУЛЬТАТЫ")
    print(f"{'='*90}\n")
    
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
        
        avg_hold = trades_df['hold_days'].mean()
        avg_leverage = trades_df['leverage'].mean()
        avg_return = trades_df[trades_df['return_pct'] > 0]['return_pct'].mean() if wins > 0 else 0
        
        # Просадка
        trades_df['cum'] = trades_df['balance']
        trades_df['peak'] = trades_df['cum'].cummax()
        trades_df['dd'] = (trades_df['cum'] - trades_df['peak']) / trades_df['peak'] * 100
        max_dd = trades_df['dd'].min()
        
        print(f"💰 Баланс: {INITIAL_BALANCE:.2f} → {final:.2f} USD")
        print(f"📈 PnL: {total_pnl:+.2f} USD ({roi:+.1f}%)")
        print(f"⚡ Среднее плечо: {avg_leverage:.1f}x")
        print(f"\n📊 Сделок: {total} | ✅ {wins} ({wr:.1f}%) | ❌ {losses}")
        print(f"💵 Ср. прибыль: +{avg_win:.2f} USD | Ср. убыток: {avg_loss:.2f} USD")
        print(f"🎯 Лучшая: +{best:.2f} USD | Худшая: {worst:.2f} USD")
        print(f"📊 Profit Factor: {pf:.2f}")
        print(f"⏱️ Среднее удержание: {avg_hold:.1f} дней")
        print(f"📈 Средний возврат: {avg_return:.1f}%")
        print(f"📉 Макс. просадка: {max_dd:.2f}%")
        
        # Оценка риска ликвидации
        max_leverage_used = trades_df['leverage'].max()
        print(f"⚠️ Макс. использованное плечо: {max_leverage_used:.1f}x")
        
    else:
        print("⚠️ Нет сделок")
        total_pnl = 0
        wr = 0
        roi = 0
        pf = 0
        avg_hold = 0
        avg_leverage = 0
    
    print(f"\n{'='*90}\n")
    
    return trades, {'pnl': total_pnl, 'wr': wr, 'roi': roi, 'pf': pf, 'avg_hold': avg_hold, 'avg_leverage': avg_leverage}

# === Главная функция ===
def main():
    # Добавили волатильные альткоины для большей прибыли
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'AVAX/USDT']
    
    strategies = {
        '4h': ('4h Aggressive Turtle (15-period)', strategy_4h_aggressive_turtle, 90),
        '12h': ('12h Momentum Breakout (BB + Volume)', strategy_12h_momentum, 120),
        '1d': ('1d Strong Trend Following', strategy_1d_strong_trend, 180)
    }
    
    print("=" * 90)
    print("🚀 АГРЕССИВНАЯ СВИНГ-ТРЕЙДИНГ СИСТЕМА")
    print("💰 Оптимизирована для малого депозита с плечом до 7x")
    print("⚡ Риск: 3% на сделку | Минимальный R:R: 2:1")
    print("=" * 90)
    print(f"⏰ Старт: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    all_results = []
    
    for symbol in symbols:
        for timeframe, (strategy_name, strategy_func, days) in strategies.items():
            try:
                df = fetch_historical_data(symbol, timeframe, days)
                df = strategy_func(df)
                trades, stats = backtest_aggressive(df, strategy_name, symbol, timeframe)
                
                all_results.append({
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'strategy': strategy_name,
                    'trades': trades,
                    'stats': stats
                })
                
                time.sleep(2)
                
            except Exception as e:
                print(f"❌ Ошибка {symbol} {timeframe}: {e}\n")
                continue
    
    # ИТОГОВЫЙ ОТЧЕТ
    print("\n" + "=" * 120)
    print("📊 ИТОГОВЫЙ ОТЧЕТ - АГРЕССИВНАЯ СИСТЕМА")
    print("=" * 120)
    print(f"{'Инструмент':<12} | {'TF':<4} | {'Стратегия':<45} | {'Сделок':<7} | {'WR%':<6} | {'PnL':<10} | {'ROI%':<8} | {'PF':<6} | {'Плечо':<6}")
    print("-" * 120)
    
    best_strategy = None
    best_roi = -float('inf')
    
    for result in all_results:
        if result['trades']:
            stats = result['stats']
            print(f"{result['symbol']:<12} | {result['timeframe']:<4} | {result['strategy']:<45} | "
                  f"{len(result['trades']):<7} | {stats['wr']:>5.1f}% | {stats['pnl']:>+9.2f} | "
                  f"{stats['roi']:>+7.1f}% | {stats['pf']:>5.2f} | {stats['avg_leverage']:>5.1f}x")
            
            if stats['roi'] > best_roi:
                best_roi = stats['roi']
                best_strategy = result
        else:
            print(f"{result['symbol']:<12} | {result['timeframe']:<4} | {result['strategy']:<45} | {'0':<7} | {'-':<6} | {'-':<10} | {'-':<8} | {'-':<6} | {'-':<6}")
    
    print("-" * 120)
    
    # ЛУЧШАЯ СТРАТЕГИЯ
    if best_strategy:
        print("\n" + "=" * 120)
        print("🏆 ЛУЧШАЯ СТРАТЕГИЯ")
        print("=" * 120)
        print(f"📊 {best_strategy['symbol']} | {best_strategy['timeframe']} | {best_strategy['strategy']}")
        print(f"💰 ROI: {best_strategy['stats']['roi']:+.1f}%")
        print(f"📈 PnL: {best_strategy['stats']['pnl']:+.2f} USD")
        print(f"✅ Win Rate: {best_strategy['stats']['wr']:.1f}%")
        print(f"📊 Profit Factor: {best_strategy['stats']['pf']:.2f}")
        print(f"⚡ Среднее плечо: {best_strategy['stats']['avg_leverage']:.1f}x")
        print(f"⏱️ Среднее удержание: {best_strategy['stats']['avg_hold']:.1f} дней")
        print("=" * 120)
        
        # ТОП-5 СДЕЛОК
        if best_strategy['trades']:
            trades_df = pd.DataFrame(best_strategy['trades'])
            top_trades = trades_df.nlargest(5, 'pnl')
            
            print("\n🌟 ТОП-5 ПРИБЫЛЬНЫХ СДЕЛОК:")
            print("-" * 120)
            for idx, trade in top_trades.iterrows():
                print(f"  {trade['type']:<6} | {trade['entry_time'].strftime('%Y-%m-%d %H:%M')} | "
                      f"{trade['entry']:.4f} → {trade['exit']:.4f} | "
                      f"PnL: {trade['pnl']:+.2f} USD ({trade['return_pct']:+.1f}%) | "
                      f"Плечо: {trade['leverage']:.1f}x | "
                      f"Удержание: {trade['hold_days']:.1f} дней")
            print("-" * 120)
    
    # ОБЩАЯ СТАТИСТИКА
    print("\n" + "=" * 120)
    print("📊 ОБЩАЯ СТАТИСТИКА ПО ВСЕМ СТРАТЕГИЯМ")
    print("=" * 120)
    
    total_trades = sum(len(r['trades']) for r in all_results if r['trades'])
    total_pnl = sum(r['stats']['pnl'] for r in all_results if r['trades'])
    
    profitable_strategies = [r for r in all_results if r['trades'] and r['stats']['pnl'] > 0]
    losing_strategies = [r for r in all_results if r['trades'] and r['stats']['pnl'] <= 0]
    
    print(f"🎯 Всего стратегий протестировано: {len(all_results)}")
    print(f"📊 Общее количество сделок: {total_trades}")
    print(f"💰 Общий PnL: {total_pnl:+.2f} USD")
    print(f"✅ Прибыльных стратегий: {len(profitable_strategies)}")
    print(f"❌ Убыточных стратегий: {len(losing_strategies)}")
    
    if profitable_strategies:
        avg_roi_profitable = np.mean([r['stats']['roi'] for r in profitable_strategies])
        avg_wr_profitable = np.mean([r['stats']['wr'] for r in profitable_strategies])
        avg_pf_profitable = np.mean([r['stats']['pf'] for r in profitable_strategies if r['stats']['pf'] != float('inf')])
        
        print(f"\n💎 Средние показатели прибыльных стратегий:")
        print(f"   ROI: {avg_roi_profitable:+.1f}%")
        print(f"   Win Rate: {avg_wr_profitable:.1f}%")
        print(f"   Profit Factor: {avg_pf_profitable:.2f}")
    
    print("=" * 120)
    
    # РЕКОМЕНДАЦИИ
    print("\n" + "=" * 120)
    print("💡 РЕКОМЕНДАЦИИ ДЛЯ РЕАЛЬНОЙ ТОРГОВЛИ")
    print("=" * 120)
    print("⚠️ ВАЖНО:")
    print("  1. Начните с минимального депозита и протестируйте систему на реальном рынке")
    print("  2. Используйте плечо 3-5x для начала, не сразу 7x")
    print("  3. Строго соблюдайте риск-менеджмент: не более 3% на сделку")
    print("  4. Установите защиту от ликвидации: стоп-лосс обязателен")
    print("  5. Следите за волатильностью рынка - в штиль снизьте плечо")
    print("  6. Диверсифицируйте: не торгуйте все депо в одной сделке")
    print("  7. Ведите журнал сделок и анализируйте ошибки")
    print("  8. При просадке 20%+ - остановитесь и пересмотрите стратегию")
    print("\n🎯 Лучшая стратегия из теста:")
    if best_strategy:
        print(f"   {best_strategy['symbol']} на {best_strategy['timeframe']} таймфрейме")
        print(f"   Стратегия: {best_strategy['strategy']}")
        print(f"   Показала ROI: {best_strategy['stats']['roi']:+.1f}%")
    print("\n⚡ Помните: прошлые результаты не гарантируют будущую прибыль!")
    print("=" * 120)
    
    print(f"\n⏰ Завершено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 120)

if __name__ == '__main__':
    main()