import ccxt
import logging
from typing import Optional, List, Dict, Any

# Настройка логирования
logger = logging.getLogger(__name__)

class ExchangeManager:
    def __init__(self):
        self.exchanges: List[ccxt.Exchange] = []
        self.current_exchange: Optional[ccxt.Exchange] = None
        self.fallback_exchange: Optional[ccxt.Exchange] = None
        self._init_exchanges()

    def _get_exchange_config(self, exchange_id: str) -> Dict[str, Any]:
        """Возвращает конфигурацию для указанной биржи"""
        configs = {
            'bybit': {
                'enableRateLimit': True,
                'rateLimit': 3500,  # 3.5 секунды между запросами
                'timeout': 120000,  # 2 минуты таймаут
                'options': {
                    'defaultType': 'swap',
                    'adjustForTimeDifference': True,
                    'recvWindow': 120000,
                    'brokerId': 'CCXT',
                    'createMarketBuyOrderRequiresPrice': False,
                    'defaultTimeInForce': 'GTC',
                    'defaultReduceOnly': False,
                },
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept-Encoding': 'gzip, deflate, br',
                },
                'verbose': False
            },
            'okx': {
                'enableRateLimit': True,
                'rateLimit': 2000,  # 2 секунды между запросами
                'timeout': 60000,   # 1 минута таймаут
                'options': {
                    'defaultType': 'swap',
                    'adjustForTimeDifference': True,
                    'recvWindow': 60000,
                },
                'verbose': False
            },
            'binance': {
                'enableRateLimit': True,
                'rateLimit': 1000,  # 1 секунда между запросами
                'timeout': 30000,   # 30 секунд таймаут
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                    'recvWindow': 60000,
                },
                'verbose': False
            },
            'kucoin': {
                'enableRateLimit': True,
                'rateLimit': 1500,  # 1.5 секунды между запросами
                'timeout': 60000,   # 1 минута таймаут
                'options': {
                    'defaultType': 'swap',
                    'adjustForTimeDifference': True,
                },
                'verbose': False
            }
        }
        return configs.get(exchange_id, {})

    def _create_exchange(self, exchange_id: str) -> Optional[ccxt.Exchange]:
        """Создает и возвращает экземпляр биржи"""
        try:
            config = self._get_exchange_config(exchange_id)
            if not config:
                logger.warning(f"Конфигурация для биржи {exchange_id} не найдена")
                return None
                
            exchange_class = getattr(ccxt, exchange_id)
            exchange = exchange_class(config)
            exchange.load_markets()
            exchange.fetch_time()  # Проверяем соединение
            logger.info(f"✅ Успешное подключение к {exchange_id.upper()}")
            return exchange
            
        except Exception as e:
            logger.warning(f"⚠️ Не удалось подключиться к {exchange_id.upper()}: {str(e)}")
            return None

    def _init_exchanges(self):
        """Инициализирует биржи в порядке приоритета"""
        exchange_priority = ['kucoin' ,'bybit', 'okx', 'binance']
        
        for exchange_id in exchange_priority:
            if len(self.exchanges) >= 2:  # Берем максимум 2 биржи
                break
                
            exchange = self._create_exchange(exchange_id)
            if exchange:
                self.exchanges.append(exchange)
        
        if not self.exchanges:
            logger.error("❌ Не удалось подключиться ни к одной бирже")
            raise Exception("Не удалось инициализировать ни одну биржу")
        
        self.current_exchange = self.exchanges[0]
        self.fallback_exchange = self.exchanges[1] if len(self.exchanges) > 1 else self.exchanges[0]
        
        logger.info(f"Основная биржа: {self.current_exchange.id.upper()}")
        if len(self.exchanges) > 1:
            logger.info(f"Резервная биржа: {self.fallback_exchange.id.upper()}")
    
    def get_exchange(self) -> ccxt.Exchange:
        """Возвращает текущую активную биржу"""
        return self.current_exchange or self.fallback_exchange
    
    def switch_to_fallback(self) -> bool:
        """Переключается на резервную биржу"""
        if self.fallback_exchange and self.current_exchange != self.fallback_exchange:
            logger.warning(f"Переключаемся на резервную биржу: {self.fallback_exchange.id.upper()}")
            self.current_exchange = self.fallback_exchange
            return True
        return False

# Глобальный экземпляр менеджера бирж
exchange_manager = ExchangeManager()
