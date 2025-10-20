"""
Market Regime Monitor - Определение режима рынка

Анализирует рынок и определяет:
- Бычий тренд (Bull Trend)
- Медвежий тренд (Bear Trend)
- Бычий боковик (Bullish Range)
- Медвежий боковик (Bearish Range)
- Нейтральный боковик (Neutral Range)
"""

import pandas as pd
import numpy as np
import ta
from typing import Dict, Optional, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MarketRegimeMonitor:
    """
    Мониторинг рыночных режимов
    """
    
    def __init__(
        self,
        adx_threshold: float = 25,
        trend_strength_threshold: float = 20,
        range_threshold: float = 2.0
    ):
        self.adx_threshold = adx_threshold
        self.trend_strength_threshold = trend_strength_threshold
        self.range_threshold = range_threshold
        
    def analyze_market_regime(self, df: pd.DataFrame) -> Dict:
        """
        Анализирует режим рынка
        
        Returns:
            Dict с информацией о режиме рынка
        """
        try:
            if len(df) < 100:
                return {'regime': 'UNKNOWN', 'confidence': 0}
            
            # Рассчитываем индикаторы
            df = self._calculate_indicators(df)
            
            last = df.iloc[-1]
            
            # Извлекаем значения
            adx = float(last['ADX'])
            plus_di = float(last['+DI'])
            minus_di = float(last['-DI'])
            ema20 = float(last['EMA_20'])
            ema50 = float(last['EMA_50'])
            ema100 = float(last['EMA_100'])
            close = float(last['close'])
            rsi = float(last['RSI'])
            macd = float(last['MACD'])
            macd_signal = float(last['MACD_Signal'])
            bb_width = float(last['BB_Width'])
            
            # Определяем тренд
            trend_direction = self._determine_trend(
                ema20, ema50, ema100, plus_di, minus_di, macd, macd_signal
            )
            
            # Определяем силу тренда
            trend_strength = self._calculate_trend_strength(adx, bb_width)
            
            # Определяем режим
            regime = self._classify_regime(
                trend_direction, trend_strength, adx, rsi, close, ema20, ema50
            )
            
            # Рассчитываем уверенность
            confidence = self._calculate_confidence(
                adx, trend_direction, ema20, ema50, ema100, rsi
            )
            
            # Дополнительная информация
            volatility = self._calculate_volatility(df)
            momentum = self._calculate_momentum(df)
            
            return {
                'regime': regime,
                'confidence': confidence,
                'trend_direction': trend_direction,
                'trend_strength': trend_strength,
                'adx': adx,
                'rsi': rsi,
                'volatility': volatility,
                'momentum': momentum,
                'price': close,
                'ema20': ema20,
                'ema50': ema50,
                'ema100': ema100,
                'timestamp': last['timestamp']
            }
            
        except Exception as e:
            logger.error(f"Error analyzing market regime: {e}")
            return {'regime': 'ERROR', 'confidence': 0}
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Рассчитывает технические индикаторы"""
        df = df.copy()
        
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
        
        # MACD
        macd = ta.trend.MACD(df['close'])
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
        df['BB_Upper'] = bb.bollinger_hband()
        df['BB_Lower'] = bb.bollinger_lband()
        df['BB_Middle'] = bb.bollinger_mavg()
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']
        
        return df
    
    def _determine_trend(
        self, ema20: float, ema50: float, ema100: float,
        plus_di: float, minus_di: float, macd: float, macd_signal: float
    ) -> str:
        """Определяет направление тренда"""
        
        # Бычий тренд
        if (ema20 > ema50 > ema100 and 
            plus_di > minus_di and 
            macd > macd_signal):
            return 'BULLISH'
        
        # Медвежий тренд
        elif (ema20 < ema50 < ema100 and 
              minus_di > plus_di and 
              macd < macd_signal):
            return 'BEARISH'
        
        # Слабый бычий
        elif ema20 > ema50 and plus_di > minus_di:
            return 'WEAK_BULLISH'
        
        # Слабый медвежий
        elif ema20 < ema50 and minus_di > plus_di:
            return 'WEAK_BEARISH'
        
        # Нейтральный
        else:
            return 'NEUTRAL'
    
    def _calculate_trend_strength(self, adx: float, bb_width: float) -> str:
        """Определяет силу тренда"""
        
        if adx > 40:
            return 'VERY_STRONG'
        elif adx > 30:
            return 'STRONG'
        elif adx > 25:
            return 'MODERATE'
        elif adx > 20:
            return 'WEAK'
        else:
            return 'VERY_WEAK'
    
    def _classify_regime(
        self, trend_direction: str, trend_strength: str,
        adx: float, rsi: float, close: float, ema20: float, ema50: float
    ) -> str:
        """Классифицирует режим рынка"""
        
        # Сильный бычий тренд
        if (trend_direction == 'BULLISH' and 
            adx > self.adx_threshold and 
            trend_strength in ['STRONG', 'VERY_STRONG']):
            return 'BULL_TREND'
        
        # Сильный медвежий тренд
        elif (trend_direction == 'BEARISH' and 
              adx > self.adx_threshold and 
              trend_strength in ['STRONG', 'VERY_STRONG']):
            return 'BEAR_TREND'
        
        # Бычий боковик (цена выше EMA, но слабый тренд)
        elif (adx < self.adx_threshold and 
              close > ema50 and 
              rsi > 50):
            return 'BULLISH_RANGE'
        
        # Медвежий боковик (цена ниже EMA, но слабый тренд)
        elif (adx < self.adx_threshold and 
              close < ema50 and 
              rsi < 50):
            return 'BEARISH_RANGE'
        
        # Нейтральный боковик
        elif adx < self.adx_threshold:
            return 'NEUTRAL_RANGE'
        
        # Слабый бычий тренд
        elif trend_direction in ['BULLISH', 'WEAK_BULLISH']:
            return 'WEAK_BULL_TREND'
        
        # Слабый медвежий тренд
        elif trend_direction in ['BEARISH', 'WEAK_BEARISH']:
            return 'WEAK_BEAR_TREND'
        
        # По умолчанию - неопределенный
        else:
            return 'UNDEFINED'
    
    def _calculate_confidence(
        self, adx: float, trend_direction: str,
        ema20: float, ema50: float, ema100: float, rsi: float
    ) -> float:
        """Рассчитывает уверенность в определении режима (0-100)"""
        
        confidence = 0
        
        # ADX вклад (0-30 баллов)
        if adx > 40:
            confidence += 30
        elif adx > 30:
            confidence += 25
        elif adx > 25:
            confidence += 20
        elif adx > 20:
            confidence += 15
        else:
            confidence += 10
        
        # Выравнивание EMA (0-30 баллов)
        if ema20 > ema50 > ema100 or ema20 < ema50 < ema100:
            confidence += 30
        elif ema20 > ema50 or ema20 < ema50:
            confidence += 20
        else:
            confidence += 10
        
        # RSI подтверждение (0-20 баллов)
        if trend_direction == 'BULLISH' and rsi > 50:
            confidence += 20
        elif trend_direction == 'BEARISH' and rsi < 50:
            confidence += 20
        elif 45 < rsi < 55:
            confidence += 15
        else:
            confidence += 10
        
        # Согласованность направления (0-20 баллов)
        if trend_direction in ['BULLISH', 'BEARISH']:
            confidence += 20
        elif trend_direction in ['WEAK_BULLISH', 'WEAK_BEARISH']:
            confidence += 15
        else:
            confidence += 10
        
        return min(confidence, 100)
    
    def _calculate_volatility(self, df: pd.DataFrame) -> str:
        """Определяет волатильность"""
        
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * 100
        
        if volatility > 5:
            return 'VERY_HIGH'
        elif volatility > 3:
            return 'HIGH'
        elif volatility > 2:
            return 'MODERATE'
        elif volatility > 1:
            return 'LOW'
        else:
            return 'VERY_LOW'
    
    def _calculate_momentum(self, df: pd.DataFrame) -> str:
        """Определяет моментум"""
        
        # Изменение цены за последние 20 свечей
        price_change = ((df['close'].iloc[-1] - df['close'].iloc[-20]) / 
                       df['close'].iloc[-20] * 100)
        
        if price_change > 10:
            return 'VERY_STRONG_UP'
        elif price_change > 5:
            return 'STRONG_UP'
        elif price_change > 2:
            return 'MODERATE_UP'
        elif price_change > -2:
            return 'NEUTRAL'
        elif price_change > -5:
            return 'MODERATE_DOWN'
        elif price_change > -10:
            return 'STRONG_DOWN'
        else:
            return 'VERY_STRONG_DOWN'


def format_regime_message(regime_info: Dict, symbol: str, timeframe: str) -> str:
    """
    Форматирует сообщение о режиме рынка для Telegram
    """
    
    regime = regime_info['regime']
    confidence = regime_info['confidence']
    
    # Эмодзи для режимов
    regime_emoji = {
        'BULL_TREND': '🐂📈',
        'BEAR_TREND': '🐻📉',
        'BULLISH_RANGE': '🐂↔️',
        'BEARISH_RANGE': '🐻↔️',
        'NEUTRAL_RANGE': '😴↔️',
        'WEAK_BULL_TREND': '🐂💤',
        'WEAK_BEAR_TREND': '🐻💤',
        'UNDEFINED': '❓'
    }
    
    # Названия режимов
    regime_names = {
        'BULL_TREND': 'Сильный бычий тренд',
        'BEAR_TREND': 'Сильный медвежий тренд',
        'BULLISH_RANGE': 'Бычий боковик',
        'BEARISH_RANGE': 'Медвежий боковик',
        'NEUTRAL_RANGE': 'Нейтральный боковик',
        'WEAK_BULL_TREND': 'Слабый бычий тренд',
        'WEAK_BEAR_TREND': 'Слабый медвежий тренд',
        'UNDEFINED': 'Неопределенный'
    }
    
    # Рекомендации по стратегиям
    strategy_recommendations = {
        'BULL_TREND': '✅ Turtle (4h), Momentum (12h), Trend (1d)',
        'BEAR_TREND': '✅ Turtle SHORT (4h), Momentum SHORT (12h)',
        'BULLISH_RANGE': '✅ Grid Bot, Range Trading (покупка на падениях)',
        'BEARISH_RANGE': '✅ Grid Bot, Range Trading (продажа на росте)',
        'NEUTRAL_RANGE': '✅ Grid Bot (нейтральная сетка)',
        'WEAK_BULL_TREND': '⚠️ Осторожно: Turtle (4h) с малым плечом',
        'WEAK_BEAR_TREND': '⚠️ Осторожно: Turtle SHORT (4h) с малым плечом',
        'UNDEFINED': '❌ Не торговать, ждать четкого сигнала'
    }
    
    emoji = regime_emoji.get(regime, '❓')
    name = regime_names.get(regime, 'Неизвестный')
    strategy = strategy_recommendations.get(regime, 'Нет рекомендаций')
    
    msg = f"""
📊 **РЕЖИМ РЫНКА: {emoji} {name}**

🎯 **{symbol} | {timeframe}**
• Уверенность: {confidence:.0f}%
• ADX: {regime_info['adx']:.1f}
• RSI: {regime_info['rsi']:.1f}
• Цена: {regime_info['price']:.2f}

📈 **Технический анализ:**
• EMA 20: {regime_info['ema20']:.2f}
• EMA 50: {regime_info['ema50']:.2f}
• EMA 100: {regime_info['ema100']:.2f}
• Волатильность: {regime_info['volatility']}
• Моментум: {regime_info['momentum']}

💡 **Рекомендуемые стратегии:**
{strategy}

⏰ {regime_info['timestamp'].strftime('%Y-%m-%d %H:%M')}
"""
    
    return msg


def get_regime_color(regime: str) -> str:
    """Возвращает цвет для режима (для графиков)"""
    colors = {
        'BULL_TREND': 'green',
        'BEAR_TREND': 'red',
        'BULLISH_RANGE': 'lightgreen',
        'BEARISH_RANGE': 'lightcoral',
        'NEUTRAL_RANGE': 'gray',
        'WEAK_BULL_TREND': 'yellowgreen',
        'WEAK_BEAR_TREND': 'orange',
        'UNDEFINED': 'black'
    }
    return colors.get(regime, 'black')


# Пример использования
if __name__ == "__main__":
    import ccxt
    
    # Загрузка данных
    exchange = ccxt.okx({'enableRateLimit': True})
    ohlcv = exchange.fetch_ohlcv('SOL/USDT', '4h', limit=100)
    
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Анализ режима
    monitor = MarketRegimeMonitor()
    regime_info = monitor.analyze_market_regime(df)
    
    # Вывод
    print(format_regime_message(regime_info, 'SOL/USDT', '4h'))
