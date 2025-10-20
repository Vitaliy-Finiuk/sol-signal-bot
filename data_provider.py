import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class DataProvider:
    def __init__(self):
        self.cache = {}
        self.cache_duration = {
            '4h': 900,    # 15 минут
            '12h': 1800,  # 30 минут  
            '1d': 3600    # 1 час
        }
        self.last_request_time = 0
        
    def _get_yfinance_interval(self, timeframe: str) -> str:
        """Конвертирует наш формат таймфрейма в формат yfinance"""
        # yfinance не поддерживает 12h, используем 1d и ресемплируем
        if timeframe == '4h':
            return '4h'
        elif timeframe == '12h':
            return '1d'  # Будем использовать дневные данные для 12h
        elif timeframe == '1d':
            return '1d'
        else:
            return '1h'  # по умолчанию
    
    def _get_yfinance_period(self, timeframe: str, limit: int) -> str:
        """Определяет период для загрузки данных"""
        if timeframe == '12h':
            return f"{limit}d"  # Для 12h берем дневные данные
        elif timeframe == '1d':
            return f"{limit*2}d"  # Берем в 2 раза больше дней
        else:
            return f"{limit*2}d"  # Для внутридневных таймфреймов тоже берем дни
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> List[list]:
        cache_key = f"{symbol}_{timeframe}"
    
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration.get(timeframe, 300):
                logger.info(f"Используем кэшированные данные для {symbol} {timeframe}")
            return cached_data
    
        try:
            time_since_last = time.time() - self.last_request_time
            if time_since_last < 1:
                time.sleep(1 - time_since_last)
        
            if '/' in symbol:
                base, quote = symbol.split('/')
                yf_symbol = f"{base}-USD"
            else:
                yf_symbol = symbol
        
            interval = self._get_yfinance_interval(timeframe)
            period = self._get_yfinance_period(timeframe, limit)
        
            logger.info(f"Запрашиваем {limit} свечей {symbol} {timeframe} с yfinance...")
            data = yf.download(
                tickers=yf_symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False
        )
        
            if data.empty:
                logger.error(f"Не удалось получить данные для {symbol}")
                return []
        
            data = data.reset_index()
            if 'Date' in data.columns:
                date_col = 'Date'
            elif 'Datetime' in data.columns:
                date_col = 'Datetime'
            else:
                raise ValueError("Не найден столбец с датой в данных yfinance")
        
            # Для 12h таймфрейма используем дневные данные (yfinance не поддерживает 12h)
            if timeframe == '12h':
                logger.info(f"Используем дневные данные вместо 12h (yfinance не поддерживает 12h)")
            
            ohlcv = []
            for _, row in data.iterrows():
                # Если значение Series, берём первый элемент
                ts_value = row[date_col]
                if isinstance(ts_value, pd.Series) or isinstance(ts_value, pd.Index):
                    ts_value = ts_value.iloc[0]
                timestamp = int(pd.Timestamp(ts_value).timestamp() * 1000)
                
                # Безопасное извлечение значений (если Series, берём первый элемент)
                def safe_float(val):
                    if isinstance(val, pd.Series):
                        return float(val.iloc[0])
                    return float(val)
            
                ohlcv.append([
                    timestamp,
                    safe_float(row['Open']),
                    safe_float(row['High']),
                    safe_float(row['Low']),
                    safe_float(row['Close']),
                    safe_float(row['Volume'])
                ])
        
            self.cache[cache_key] = (ohlcv, time.time())
            self.last_request_time = time.time()
        
            return ohlcv
    
        except Exception as e:
            logger.error(f"Ошибка при получении данных с yfinance: {e}")
        return []

# Глобальный экземпляр провайдера данных
data_provider = DataProvider()

def safe_fetch_ohlcv(symbol: str, timeframe: str, limit: int = 100, retries: int = 3) -> List[list]:
    """Безопасное получение OHLCV данных с повторными попытками"""
    for attempt in range(retries):
        try:
            data = data_provider.fetch_ohlcv(symbol, timeframe, limit)
            if data:
                return data[-limit:]  # Возвращаем только запрошенное количество свечей
        except Exception as e:
            logger.warning(f"Попытка {attempt + 1}/{retries} не удалась: {str(e)}")
            time.sleep(1)  # Задержка перед повторной попыткой
    
    logger.error(f"Не удалось получить данные для {symbol} {timeframe} после {retries} попыток")
    return []
