"""
Grid Bot Strategy - Запуск по сигналам Range Trading

Автоматически создает сетку ордеров в определенном диапазоне
когда Range Trading стратегия определяет боковик.
"""

import pandas as pd
import numpy as np
import ta
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class GridBotStrategy:
    """
    Grid Bot для торговли в диапазоне.
    Создает сетку ордеров между поддержкой и сопротивлением.
    """
    
    def __init__(
        self,
        grid_levels: int = 10,
        profit_per_grid: float = 0.005,  # 0.5% прибыль на уровень
        capital_per_grid: float = 0.1,   # 10% капитала на уровень
        min_range_pct: float = 2.0,      # Минимальный диапазон 2%
        max_range_pct: float = 10.0      # Максимальный диапазон 10%
    ):
        self.grid_levels = grid_levels
        self.profit_per_grid = profit_per_grid
        self.capital_per_grid = capital_per_grid
        self.min_range_pct = min_range_pct
        self.max_range_pct = max_range_pct
        
    def detect_range(self, df: pd.DataFrame, lookback: int = 50) -> Optional[Dict]:
        """
        Определяет диапазон для Grid Bot
        
        Returns:
            Dict с параметрами диапазона или None
        """
        try:
            if len(df) < lookback:
                return None
            
            # Рассчитываем индикаторы
            df['ADX'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
            df['Support'] = df['low'].rolling(window=lookback).min()
            df['Resistance'] = df['high'].rolling(window=lookback).max()
            
            last = df.iloc[-1]
            
            if pd.isna(last['ADX']):
                return None
            
            support = float(last['Support'])
            resistance = float(last['Resistance'])
            current_price = float(last['close'])
            adx = float(last['ADX'])
            
            # Рассчитываем диапазон
            range_height = resistance - support
            range_pct = (range_height / support) * 100
            
            # Проверяем условия для Grid Bot
            is_ranging = (
                adx < 30 and  # Слабый тренд
                self.min_range_pct < range_pct < self.max_range_pct and  # Оптимальный диапазон
                support < current_price < resistance  # Цена внутри диапазона
            )
            
            if not is_ranging:
                return None
            
            return {
                'support': support,
                'resistance': resistance,
                'current_price': current_price,
                'range_pct': range_pct,
                'range_height': range_height,
                'adx': adx
            }
            
        except Exception as e:
            logger.error(f"Error detecting range: {e}")
            return None
    
    def create_grid(self, range_info: Dict, balance: float) -> Dict:
        """
        Создает сетку ордеров
        
        Args:
            range_info: Информация о диапазоне
            balance: Доступный баланс
            
        Returns:
            Dict с параметрами сетки
        """
        support = range_info['support']
        resistance = range_info['resistance']
        current_price = range_info['current_price']
        
        # Рассчитываем уровни сетки
        grid_step = (resistance - support) / (self.grid_levels - 1)
        
        buy_levels = []
        sell_levels = []
        
        for i in range(self.grid_levels):
            level_price = support + (grid_step * i)
            
            # Ордера на покупку ниже текущей цены
            if level_price < current_price:
                buy_levels.append({
                    'price': level_price,
                    'amount': (balance * self.capital_per_grid) / level_price,
                    'sell_price': level_price * (1 + self.profit_per_grid)
                })
            
            # Ордера на продажу выше текущей цены
            elif level_price > current_price:
                sell_levels.append({
                    'price': level_price,
                    'amount': (balance * self.capital_per_grid) / level_price,
                    'buy_price': level_price * (1 - self.profit_per_grid)
                })
        
        return {
            'support': support,
            'resistance': resistance,
            'current_price': current_price,
            'grid_step': grid_step,
            'buy_levels': buy_levels,
            'sell_levels': sell_levels,
            'total_buy_orders': len(buy_levels),
            'total_sell_orders': len(sell_levels),
            'capital_allocated': balance * self.capital_per_grid * len(buy_levels)
        }
    
    def calculate_profit_potential(self, grid_config: Dict, range_info: Dict) -> Dict:
        """
        Рассчитывает потенциальную прибыль от Grid Bot
        
        Returns:
            Dict с прогнозом прибыли
        """
        # Прибыль от одного полного цикла (покупка -> продажа)
        profit_per_cycle = grid_config['capital_allocated'] * self.profit_per_grid
        
        # Оценка количества циклов в день (зависит от волатильности)
        range_pct = range_info['range_pct']
        estimated_cycles_per_day = range_pct / 2  # Грубая оценка
        
        # Прогноз прибыли
        daily_profit = profit_per_cycle * estimated_cycles_per_day
        monthly_profit = daily_profit * 30
        
        return {
            'profit_per_cycle': profit_per_cycle,
            'estimated_cycles_per_day': estimated_cycles_per_day,
            'daily_profit_estimate': daily_profit,
            'monthly_profit_estimate': monthly_profit,
            'monthly_roi_estimate': (monthly_profit / grid_config['capital_allocated']) * 100
        }


def strategy_grid_bot(df: pd.DataFrame, balance: float = 1000) -> Tuple[Optional[str], Dict]:
    """
    Grid Bot стратегия для запуска по сигналам
    
    Args:
        df: DataFrame с OHLCV данными
        balance: Доступный баланс
        
    Returns:
        Tuple (signal, params)
        signal: 'GRID_START' или None
        params: Параметры Grid Bot
    """
    try:
        grid_bot = GridBotStrategy(
            grid_levels=10,
            profit_per_grid=0.005,  # 0.5% на уровень
            capital_per_grid=0.1     # 10% капитала на уровень
        )
        
        # Определяем диапазон
        range_info = grid_bot.detect_range(df)
        
        if not range_info:
            return None, {}
        
        # Создаем сетку
        grid_config = grid_bot.create_grid(range_info, balance)
        
        # Рассчитываем потенциал
        profit_potential = grid_bot.calculate_profit_potential(grid_config, range_info)
        
        # Формируем параметры
        params = {
            'signal_type': 'GRID_START',
            'range_info': range_info,
            'grid_config': grid_config,
            'profit_potential': profit_potential,
            'strategy': 'Grid Bot',
            'timeframe': '4h'
        }
        
        logger.info(
            f"Grid Bot signal: Range {range_info['support']:.2f}-{range_info['resistance']:.2f} "
            f"({range_info['range_pct']:.1f}%), {grid_config['total_buy_orders']} buy orders, "
            f"Est. monthly ROI: {profit_potential['monthly_roi_estimate']:.1f}%"
        )
        
        return 'GRID_START', params
        
    except Exception as e:
        logger.error(f"Grid Bot strategy error: {e}")
        return None, {}


def format_grid_signal(params: Dict) -> str:
    """
    Форматирует сигнал Grid Bot для отправки в Telegram
    
    Args:
        params: Параметры Grid Bot
        
    Returns:
        Отформатированное сообщение
    """
    range_info = params['range_info']
    grid_config = params['grid_config']
    profit = params['profit_potential']
    
    msg = f"""
🤖 **GRID BOT SIGNAL**

📊 **Диапазон:**
• Поддержка: {range_info['support']:.2f}
• Сопротивление: {range_info['resistance']:.2f}
• Диапазон: {range_info['range_pct']:.1f}%
• Текущая цена: {range_info['current_price']:.2f}
• ADX: {range_info['adx']:.1f} (боковик)

🎯 **Параметры сетки:**
• Уровней: {grid_config['total_buy_orders'] + grid_config['total_sell_orders']}
• Шаг сетки: {grid_config['grid_step']:.2f}
• Ордеров на покупку: {grid_config['total_buy_orders']}
• Ордеров на продажу: {grid_config['total_sell_orders']}
• Капитал: {grid_config['capital_allocated']:.2f} USDT

💰 **Прогноз прибыли:**
• За цикл: {profit['profit_per_cycle']:.2f} USDT
• Циклов/день: ~{profit['estimated_cycles_per_day']:.1f}
• В день: ~{profit['daily_profit_estimate']:.2f} USDT
• В месяц: ~{profit['monthly_profit_estimate']:.2f} USDT
• ROI месяц: ~{profit['monthly_roi_estimate']:.1f}%

📝 **Рекомендации:**
1. Запустите Grid Bot в диапазоне {range_info['support']:.0f}-{range_info['resistance']:.0f}
2. Используйте {grid_config['total_buy_orders'] + grid_config['total_sell_orders']} уровней
3. Прибыль на уровень: 0.5%
4. Следите за пробоем диапазона (стоп при ADX > 30)

⚠️ **Риски:**
• Пробой диапазона вверх/вниз
• Застревание капитала в ордерах
• Комиссии биржи

🚀 **Готово к запуску!**
"""
    
    return msg


# Пример использования
if __name__ == "__main__":
    import ccxt
    
    # Загрузка данных для примера
    exchange = ccxt.okx({'enableRateLimit': True})
    ohlcv = exchange.fetch_ohlcv('SOL/USDT', '4h', limit=100)
    
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Тест стратегии
    signal, params = strategy_grid_bot(df, balance=1000)
    
    if signal:
        print(format_grid_signal(params))
    else:
        print("Нет сигнала для Grid Bot")
