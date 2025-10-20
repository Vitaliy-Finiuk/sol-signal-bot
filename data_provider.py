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
        if timeframe == '4h':
            return '4h'
        elif timeframe == '12h':
            return '12h'
        elif timeframe == '1d':
            return '1d'
        else:
            return '1h'  # по умолчанию
    
    def _get_yfinance_period(self, timeframe: str, limit: int) -> str:
        """Определяет период для загрузки данных"""
        if timeframe == '1d':
            return f"{limit*2}d"  # Берем в 2 раза больше дней
        else:
            return f"{limit*2}d"  # Для внутридневных таймфреймов тоже берем дни
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> List[list]:
        """Получает OHLCV данные с использованием yfinance"""
        cache_key = f"{symbol}_{timeframe}"
        
        # Проверяем кэш
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration.get(timeframe, 300):
                logger.info(f"Используем кэшированные данные для {symbol} {timeframe}")
                return cached_data
        
        try:
            # Уважаем rate limit
            time_since_last = time.time() - self.last_request_time
            if time_since_last < 1:  # Не более 1 запроса в секунду
                time.sleep(1 - time_since_last)
            
            # Конвертируем символ в формат Yahoo Finance
            yf_symbol = symbol.replace('/', '-')
            if yf_symbol.endswith('USDT'):
                yf_symbol = yf_symbol.replace('USDT', '-USD')
            
            # Получаем данные
            interval = self._get_yfinance_interval(timeframe)
            period = self._get_yfinance_period(timeframe, limit)
            
            logger.info(f"Запрашиваем {limit} свечей {symbol} {timeframe} с yfinance...")
            
            data = yf.download(
                tickers=yf_symbol,
                period=period,
                interval=interval,
                progress=False,
                show_errors=False
            )
            
            if data.empty:
                logger.error(f"Не удалось получить данные для {symbol}")
                return []
            
            # Конвертируем в формат OHLCV
            data = data.reset_index()
            ohlcv = []
            for _, row in data.iterrows():
                timestamp = int(row['Date'].timestamp() * 1000)  # в мс
                ohlcv.append([
                    timestamp,              # timestamp
                    row['Open'],            # open
                    row['High'],            # high
                    row['Low'],             # low
                    row['Close'],           # close
                    row['Volume']           # volume
                ])
            
            # Обновляем кэш
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
