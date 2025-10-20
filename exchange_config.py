import ccxt
import logging
from typing import Optional, List, Dict, Any

# Настройка логирования
logger = logging.getLogger(__name__)

class ExchangeManager:
    def __init__(self):
        self.exchanges: List[Dict[str, Any]] = []  # List of dicts with 'exchange' and 'status'
        self.current_exchange: Optional[ccxt.Exchange] = None
        self.fallback_exchange: Optional[ccxt.Exchange] = None
        self._init_exchanges()
        self._setup_exchange_priority()

    def _get_symbol_mapping(self, exchange_id: str, symbol: str) -> str:
        """Возвращает правильный формат символа для указанной биржи"""
        symbol_mapping = {
            'okx': {
                'SOL/USDT': 'SOL/USDT:USDT',  # Формат фьючерсов на OKX
                'default': 'SOL/USDT:USDT'
            },
            'bybit': {
                'SOL/USDT': 'SOL/USDT:USDT',  # Формат фьючерсов на Bybit
                'default': 'SOL/USDT:USDT'
            },
            'binance': {
                'SOL/USDT': 'SOL/USDT',
                'default': 'SOL/USDT'
            },
            'kucoin': {
                'SOL/USDT': 'SOL/USDT:USDT',  # Формат фьючерсов на KuCoin
                'default': 'SOL/USDT:USDT'
            }
        }
        return symbol_mapping.get(exchange_id, {}).get(symbol, symbol_mapping[exchange_id]['default'])

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
            logger.error(f"Ошибка при инициализации биржи {exchange_id}: {str(e)}")
            return None
            
    def _create_public_exchange(self) -> ccxt.Exchange:
        """Создает публичный экземпляр биржи без аутентификации"""
        try:
            # Пробуем Binance как основной публичный источник
            exchange = ccxt.binance({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # или 'spot' в зависимости от нужного рынка
                }
            })
            exchange.load_markets()
            logger.info("✅ Успешно подключение к публичному API Binance")
            return exchange
        except Exception as e:
            logger.warning(f"Не удалось подключиться к публичному API Binance: {e}")
            
            # Если не получилось с Binance, пробуем OKX
            try:
                exchange = ccxt.okx({
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'swap',
                    }
                })
                exchange.load_markets()
                logger.info("✅ Успешное подключение к публичному API OKX")
                return exchange
            except Exception as e:
                logger.error(f"Не удалось подключиться к публичным API: {e}")
                raise RuntimeError("Не удалось подключиться ни к одному публичному источнику данных")
            
    def _init_exchanges(self):
        """Инициализирует все доступные биржи"""
        exchange_ids = ['bybit', 'okx', 'kucoin']  # Пробуем Bybit первым, так как он обычно стабилен
        
        for exchange_id in exchange_ids:
            try:
                config = self._get_exchange_config(exchange_id)
                exchange_class = getattr(ccxt, exchange_id)
                exchange = exchange_class(config)
                
                # Test connection with a public endpoint
                exchange.fetch_ticker('SOL/USDT')  # Более легкий запрос, чем fetch_time()
                
                self.exchanges.append({
                    'id': exchange_id,
                    'exchange': exchange,
                    'status': 'connected',
                    'last_check': datetime.now().isoformat()
                })
                logger.info(f"✅ Успешное подключение к {exchange_id.upper()}")
                
            except ccxt.NetworkError as e:
                logger.warning(f"⚠️ Ошибка сети при подключении к {exchange_id.upper()}: {str(e)}")
            except ccxt.ExchangeError as e:
                logger.error(f"❌ Ошибка биржи {exchange_id.upper()}: {str(e)}")
            except Exception as e:
                logger.error(f"❌ Неизвестная ошибка при подключении к {exchange_id.upper()}: {str(e)}")
    
    def _setup_exchange_priority(self):
        """Устанавливает приоритетные биржи"""
        connected_exchanges = [e for e in self.exchanges if e['status'] == 'connected']
        
        if not connected_exchanges:
            raise RuntimeError("Не удалось подключиться ни к одной бирже")
            
        self.current_exchange = connected_exchanges[0]['exchange']
        logger.info(f"Основная биржа: {connected_exchanges[0]['id'].upper()}")
        
        if len(connected_exchanges) > 1:
            self.fallback_exchange = connected_exchanges[1]['exchange']
            logger.info(f"Резервная биржа: {connected_exchanges[1]['id'].upper()}")

    def get_exchange(self) -> ccxt.Exchange:
        """Возвращает текущую активную биржу, при необходимости переключаясь на запасную"""
        if self.current_exchange:
            try:
                # Проверяем соединение через публичный эндпоинт
                self.current_exchange.fetch_ticker('SOL/USDT')
                return self.current_exchange
            except Exception as e:
                logger.warning(f"Ошибка соединения с {self.current_exchange.id}: {str(e)}")
                return self.switch_to_fallback()
                
        # Если нет активной биржи, пробуем публичный API
        try:
            return self._create_public_exchange()
        except Exception as e:
            logger.error(f"Не удалось подключиться к публичному API: {e}")
            return self.switch_to_fallback()

        # Если дошли сюда, значит все биржи не работают, пробуем переинициализировать
        logger.warning("⚠️ Попытка переподключения к биржам...")
        self.exchanges = []
        self._init_exchanges()
        self._setup_exchange_priority()
        
        if not self.current_exchange:
            raise RuntimeError("Не удалось установить соединение ни с одной биржей")
            
        return self.current_exchange if len(self.exchanges) > 1 else self.exchanges[0]
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
