import ccxt
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class DataProvider:
    def __init__(self, use_exchange: str = 'okx'):
        """
        Инициализация провайдера данных
        
        Args:
            use_exchange: 'okx', 'binance' или 'bybit'
        """
        self.cache = {}
        self.cache_duration = {
            '4h': 900,    # 15 минут
            '12h': 1800,  # 30 минут  
            '1d': 3600    # 1 час
        }
        self.last_request_time = 0
        
        # Инициализация биржи для реальных данных
        if use_exchange == 'okx':
            self.exchange = ccxt.okx({'enableRateLimit': True})
        elif use_exchange == 'binance':
            self.exchange = ccxt.binance({'enableRateLimit': True})
        elif use_exchange == 'bybit':
            self.exchange = ccxt.bybit({'enableRateLimit': True})
        else:
            self.exchange = ccxt.okx({'enableRateLimit': True})
        
        logger.info(f"DataProvider инициализирован с биржей: {use_exchange.upper()}")
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> List[list]:
        """
        Получает OHLCV данные с биржи в реальном времени
        
        Args:
            symbol: Торговая пара (например 'BTC/USDT')
            timeframe: Таймфрейм ('4h', '12h', '1d')
            limit: Количество свечей
            
        Returns:
            List[list]: Список свечей [timestamp, open, high, low, close, volume]
        """
        cache_key = f"{symbol}_{timeframe}"
    
        # Проверка кэша
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration.get(timeframe, 300):
                logger.info(f"📦 Кэш: {symbol} {timeframe}")
                return cached_data
    
        try:
            # Rate limiting
            time_since_last = time.time() - self.last_request_time
            if time_since_last < 1:
                time.sleep(1 - time_since_last)
        
            # Получаем данные с биржи
            logger.info(f"📥 Загрузка {symbol} {timeframe} (limit={limit}) с {self.exchange.id.upper()}...")
            
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            if not ohlcv:
                logger.error(f"❌ Пустой ответ для {symbol} {timeframe}")
                return []
            
            # Кэшируем данные
            self.cache[cache_key] = (ohlcv, time.time())
            self.last_request_time = time.time()
            
            logger.info(f"✅ Получено {len(ohlcv)} свечей {symbol} {timeframe}")
            return ohlcv
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки {symbol} {timeframe}: {e}")
            return []


# Глобальный экземпляр провайдера данных
data_provider = DataProvider(use_exchange='okx')


def safe_fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100) -> Optional[pd.DataFrame]:
    """
    Безопасное получение OHLCV данных с обработкой ошибок
    
    Returns:
        DataFrame с колонками: timestamp, open, high, low, close, volume
    """
    try:
        ohlcv = data_provider.fetch_ohlcv(symbol, timeframe, limit)
        
        if not ohlcv or len(ohlcv) == 0:
            return None
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        return df
        
    except Exception as e:
        logger.error(f"Ошибка в safe_fetch_ohlcv для {symbol} {timeframe}: {e}")
        return None
