import ccxt
import pandas as pd
import time
import requests
import ta
import os
import threading
import traceback
from flask import Flask
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime, timedelta
import random
import json
from collections import defaultdict
import numpy as np
import logging
from typing import Optional, Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
    return "🚀 Signal Bot Active | Exchange: Bybit | Strategies: 4h Turtle, 12h Momentum, 1d Trend"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000), daemon=True).start()

# === УЛУЧШЕННАЯ КОНФИГУРАЦИЯ БИРЖИ ===
def create_exchange(exchange_id='bybit'):
    """Создаёт экземпляр биржи с улучшенными настройками"""
    configs = {
        'bybit': {
            'enableRateLimit': True,
            'rateLimit': 3500,  # 3.5 секунды между запросами
            'timeout': 120000,  # 2 минуты таймаут
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True,
                'recvWindow': 120000,  # 2 минуты
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
                'recvWindow': 60000,  # 1 минута
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
                'recvWindow': 60000,  # 1 минута
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
    
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class(configs[exchange_id])
        exchange.load_markets()
        return exchange
    except Exception as e:
        logger.error(f"Ошибка при создании экземпляра {exchange_id}: {str(e)}")
        return None

# Инициализация бирж с приоритетом
def init_exchanges():
    """Инициализирует биржи в порядке приоритета"""
    exchange_priority = ['bybit', 'okx', 'binance', 'kucoin']
    exchanges = []
    
    for exchange_id in exchange_priority:
        try:
            ex = create_exchange(exchange_id)
            if ex:
                ex.fetch_time()  # Проверяем соединение
                logger.info(f"✅ Успешное подключение к {exchange_id.upper()}")
                exchanges.append(ex)
                if len(exchanges) >= 2:  # Берем максимум 2 биржи
                    break
        except Exception as e:
            logger.warning(f"⚠️ Не удалось подключиться к {exchange_id.upper()}: {str(e)}")
    
    if not exchanges:
        logger.error("❌ Не удалось подключиться ни к одной бирже")
        exit(1)
        
    return exchanges

# Инициализируем биржи
try:
    exchanges = init_exchanges()
    exchange = exchanges[0]  # Основная биржа
    fallback_exchange = exchanges[1] if len(exchanges) > 1 else exchanges[0]  # Резервная биржа
    current_exchange = exchange  # Текущая активная биржа
    
    logger.info(f"Основная биржа: {exchange.id.upper()}")
    if len(exchanges) > 1:
        logger.info(f"Резервная биржа: {fallback_exchange.id.upper()}")
        
except Exception as e:
    logger.error(f"❌ Критическая ошибка при инициализации бирж: {str(e)}")
    exit(1)

# === ПАРАМЕТРЫ ===
EXCHANGES = [
    # OKX - хорошая альтернатива Bybit
    {
        'id': 'okx',
        'name': 'OKX',
        'config': {
            'enableRateLimit': True,
            'rateLimit': 2000,
            'timeout': 60000,
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True,
                'recvWindow': 60000,
            }
        }
    },
    # Binance - хорошая ликвидность
    {
        'id': 'binance',
        'name': 'Binance',
        'config': {
            'enableRateLimit': True,
            'rateLimit': 1000,
            'timeout': 30000,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
                'recvWindow': 60000,
            }
        }
    },
    # KuCoin - меньше ограничений
    {
        'id': 'kucoin',
        'name': 'KuCoin',
        'config': {
            'enableRateLimit': True,
            'rateLimit': 1500,
            'timeout': 60000,
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True,
            }
        }
    }
]

def get_exchange_instance(exchange_config):
    """Создаёт экземпляр биржи с обработкой ошибок"""
    exchange_class = getattr(ccxt, exchange_config['id'])
    try:
        exchange = exchange_class(exchange_config['config'])
        # Проверяем доступность API
        exchange.fetch_time()
        logger.info(f"Successfully connected to {exchange_config['name']}")
        return exchange
    except Exception as e:
        logger.warning(f"Failed to initialize {exchange_config['name']}: {str(e)}")
        return None

# Инициализируем биржи
exchange = None
fallback_exchanges = []

# Пытаемся инициализировать основную биржу (Bybit)
try:
    exchange = create_exchange()
    exchange.fetch_time()  # Проверяем соединение
    logger.info("Successfully connected to Bybit")
except Exception as e:
    logger.error(f"Failed to connect to Bybit: {str(e)}")
    exchange = None

# Инициализируем фоллбэк биржи
for exchange_config in EXCHANGES:
    if len(fallback_exchanges) >= 2:  # Максимум 2 фоллбэк биржи
        break
    ex = get_exchange_instance(exchange_config)
    if ex:
        fallback_exchanges.append(ex)

if not exchange and not fallback_exchanges:
    logger.error("Failed to initialize any exchange. Please check your internet connection and API settings.")
    exit(1)

# Текущая активная биржа (будет переключаться при ошибках)
current_exchange = exchange or fallback_exchanges[0] if fallback_exchanges else None

# Инициализация бирж с приоритетом
def init_exchanges():
    """Инициализирует биржи в порядке приоритета"""
    exchange_priority = ['bybit', 'okx', 'binance', 'kucoin']
    exchanges = []
    
    for exchange_id in exchange_priority:
        try:
            ex = create_exchange(exchange_id)
            ex.fetch_time()  # Проверяем соединение
            logger.info(f"✅ Успешное подключение к {exchange_id.upper()}")
            exchanges.append(ex)
            if len(exchanges) >= 2:  # Берем максимум 2 биржи
                break
        except Exception as e:
            logger.warning(f"⚠️ Не удалось подключиться к {exchange_id.upper()}: {str(e)}")
    
    if not exchanges:
        logger.error("❌ Не удалось подключиться ни к одной бирже")
        exit(1)
        
    return exchanges

# Инициализируем биржи
try:
    exchanges = init_exchanges()
    exchange = exchanges[0]  # Основная биржа
    fallback_exchange = exchanges[1] if len(exchanges) > 1 else exchanges[0]  # Резервная биржа
    current_exchange = exchange  # Текущая активная биржа
    
    logger.info(f"Основная биржа: {exchange.id.upper()}")
    if len(exchanges) > 1:
        logger.info(f"Резервная биржа: {fallback_exchange.id.upper()}")
        
except Exception as e:
    logger.error(f"❌ Критическая ошибка при инициализации бирж: {str(e)}")
    exit(1)

# === ПАРАМЕТРЫ ===
symbols = ['SOL/USDT', 'BTC/USDT', 'ETH/USDT', 'BNB/USDT']
timeframes = {
    '4h': 100,   # Уменьшено для экономии запросов
    '12h': 100,
    '1d': 150
}

BALANCE = 100.0
RISK_PER_TRADE = 0.03
MAX_LEVERAGE = 7
MIN_RISK_REWARD = 2.0
COMMISSION = 0.0006

# === УЛУЧШЕННАЯ СИСТЕМА КЭШИРОВАНИЯ И ВАЛИДАЦИИ ===
class DataValidator:
    """Класс для валидации и очистки данных"""
    
    @staticmethod
    def validate_ohlcv_data(ohlcv: List) -> Tuple[bool, str]:
        """Валидация OHLCV данных"""
        if not ohlcv or len(ohlcv) < 10:
            return False, "Insufficient data points"
        
        for i, candle in enumerate(ohlcv):
            if len(candle) != 6:
                return False, f"Invalid candle format at index {i}"
            
            timestamp, open_price, high, low, close, volume = candle
            
            # Проверка на NaN или None
            if any(pd.isna(x) or x is None for x in [open_price, high, low, close, volume]):
                return False, f"NaN/None values at index {i}"
            
            # Проверка логичности цен
            if not (0 < open_price < 1000000 and 0 < close_price < 1000000):
                return False, f"Price out of range at index {i}"
            
            if not (low <= min(open_price, close_price) and high >= max(open_price, close_price)):
                return False, f"Invalid OHLC relationship at index {i}"
            
            if volume < 0:
                return False, f"Negative volume at index {i}"
        
        return True, "Valid"
    
    @staticmethod
    def clean_ohlcv_data(ohlcv: List) -> List:
        """Очистка и нормализация данных"""
        cleaned = []
        for candle in ohlcv:
            timestamp, open_price, high, low, close, volume = candle
            
            # Округление до разумной точности
            open_price = round(float(open_price), 8)
            high = round(float(high), 8)
            low = round(float(low), 8)
            close = round(float(close), 8)
            volume = round(float(volume), 2)
            
            cleaned.append([timestamp, open_price, high, low, close, volume])
        
        return cleaned

class DataCache:
    def __init__(self):
        self.cache = {}
        self.cache_duration = {
            '4h': 900,    # 15 минут
            '12h': 1800,  # 30 минут  
            '1d': 3600    # 1 час
        }
        self.request_times = defaultdict(list)
        self.last_request_time = 0
        self.validator = DataValidator()
        self.health_stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'validation_failures': 0,
            'cache_hits': 0
        }
        
    def can_make_request(self):
        """Проверяет, можно ли сделать запрос с учётом rate limits"""
        now = time.time()
        # Увеличено до 5 секунд между запросами для Bybit
        if now - self.last_request_time < 5:
            return False
        return True
    
    def get_cached_data(self, symbol, timeframe):
        """Получает данные из кэша"""
        cache_key = f"{symbol}_{timeframe}"
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration[timeframe]:
                self.health_stats['cache_hits'] += 1
                logger.info(f"Cache hit: {symbol} {timeframe}")
                return data
        return None
    
    def set_cached_data(self, symbol, timeframe, data):
        """Сохраняет данные в кэш с валидацией"""
        cache_key = f"{symbol}_{timeframe}"
        
        # Валидация данных перед кэшированием
        is_valid, message = self.validator.validate_ohlcv_data(data)
        if not is_valid:
            logger.warning(f"Data validation failed for {symbol} {timeframe}: {message}")
            self.health_stats['validation_failures'] += 1
            return False
        
        # Очистка данных
        cleaned_data = self.validator.clean_ohlcv_data(data)
        
        self.cache[cache_key] = (cleaned_data, time.time())
        self.last_request_time = time.time()
        self.health_stats['successful_requests'] += 1
        logger.info(f"Cached {len(cleaned_data)} candles for {symbol} {timeframe}")
        return True
    
    def get_health_stats(self):
        """Возвращает статистику здоровья кэша"""
        total = self.health_stats['total_requests']
        success_rate = (self.health_stats['successful_requests'] / total * 100) if total > 0 else 0
        cache_hit_rate = (self.health_stats['cache_hits'] / total * 100) if total > 0 else 0
        
        return {
            'total_requests': total,
            'success_rate': round(success_rate, 2),
            'cache_hit_rate': round(cache_hit_rate, 2),
            'validation_failures': self.health_stats['validation_failures']
        }

# === СИСТЕМА МОНИТОРИНГА ЗДОРОВЬЯ ===
class HealthMonitor:
    def __init__(self):
        self.start_time = datetime.now()
        self.errors = []
        self.performance_metrics = {
            'api_calls': 0,
            'successful_calls': 0,
            'failed_calls': 0,
            'signals_generated': 0,
            'cache_hits': 0
        }
        self.last_health_check = datetime.now()
    
    def record_error(self, error_type, message):
        """Запись ошибки"""
        self.errors.append({
            'timestamp': datetime.now(),
            'type': error_type,
            'message': str(message)[:200]
        })
        # Храним только последние 100 ошибок
        if len(self.errors) > 100:
            self.errors = self.errors[-100:]
    
    def record_api_call(self, success=True):
        """Запись API вызова"""
        self.performance_metrics['api_calls'] += 1
        if success:
            self.performance_metrics['successful_calls'] += 1
        else:
            self.performance_metrics['failed_calls'] += 1
    
    def record_signal(self):
        """Запись сгенерированного сигнала"""
        self.performance_metrics['signals_generated'] += 1
    
    def get_uptime(self):
        """Возвращает время работы"""
        return datetime.now() - self.start_time
    
    def get_success_rate(self):
        """Возвращает процент успешных вызовов"""
        total = self.performance_metrics['api_calls']
        if total == 0:
            return 100.0
        return (self.performance_metrics['successful_calls'] / total) * 100
    
    def get_health_status(self):
        """Возвращает общий статус здоровья"""
        success_rate = self.get_success_rate()
        uptime = self.get_uptime()
        
        if success_rate >= 95 and uptime.total_seconds() > 3600:
            return "HEALTHY"
        elif success_rate >= 80:
            return "DEGRADED"
        else:
            return "UNHEALTHY"
    
    def get_summary(self):
        """Возвращает сводку здоровья"""
        uptime = self.get_uptime()
        success_rate = self.get_success_rate()
        
        return {
            'status': self.get_health_status(),
            'uptime_hours': round(uptime.total_seconds() / 3600, 2),
            'success_rate': round(success_rate, 2),
            'api_calls': self.performance_metrics['api_calls'],
            'signals_generated': self.performance_metrics['signals_generated'],
            'recent_errors': len([e for e in self.errors if (datetime.now() - e['timestamp']).total_seconds() < 3600])
        }

# === СИСТЕМА СОХРАНЕНИЯ ДАННЫХ (ФАЙЛОВАЯ) ===
class DataPersistence:
    def __init__(self, data_dir='bot_data'):
        self.data_dir = data_dir
        self.signals_file = os.path.join(data_dir, 'signals.json')
        self.stats_file = os.path.join(data_dir, 'stats.json')
        self.init_storage()
    
    def init_storage(self):
        """Инициализация файлового хранилища"""
        try:
            # Создаём директорию если не существует
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
            
            # Инициализируем файлы если не существуют
            if not os.path.exists(self.signals_file):
                with open(self.signals_file, 'w') as f:
                    json.dump([], f)
            
            if not os.path.exists(self.stats_file):
                with open(self.stats_file, 'w') as f:
                    json.dump({}, f)
            
            logger.info("File storage initialized successfully")
            
        except Exception as e:
            logger.error(f"Storage initialization error: {e}")
    
    def save_signal(self, signal_data):
        """Сохранение сигнала в файл"""
        try:
            # Читаем существующие сигналы
            signals = []
            if os.path.exists(self.signals_file):
                with open(self.signals_file, 'r') as f:
                    signals = json.load(f)
            
            # Добавляем новый сигнал
            signals.append(signal_data)
            
            # Ограничиваем количество сигналов (последние 1000)
            if len(signals) > 1000:
                signals = signals[-1000:]
            
            # Сохраняем обратно
            with open(self.signals_file, 'w') as f:
                json.dump(signals, f, indent=2)
            
            logger.info(f"Signal saved: {signal_data['symbol']} {signal_data['signal_type']}")
            
        except Exception as e:
            logger.error(f"Error saving signal: {e}")
    
    def get_recent_signals(self, hours=24):
        """Получение недавних сигналов"""
        try:
            if not os.path.exists(self.signals_file):
                return []
            
            with open(self.signals_file, 'r') as f:
                signals = json.load(f)
            
            since = datetime.now() - timedelta(hours=hours)
            recent_signals = []
            
            for signal in signals:
                signal_time = datetime.fromisoformat(signal['timestamp'])
                if signal_time > since:
                    recent_signals.append(signal)
            
            return recent_signals
            
        except Exception as e:
            logger.error(f"Error getting recent signals: {e}")
            return []
    
    def save_stats(self, stats_data):
        """Сохранение статистики"""
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(stats_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving stats: {e}")
    
    def load_stats(self):
        """Загрузка статистики"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading stats: {e}")
            return {}

# === СИСТЕМА HEALTH CHECK ===
class HealthCheckSystem:
    def __init__(self):
        self.last_health_check = datetime.now()
        self.health_check_interval = 300  # 5 минут
        self.consecutive_failures = 0
        self.max_failures = 3
        
    def should_send_health_check(self):
        """Проверяет, нужно ли отправить health check"""
        now = datetime.now()
        return (now - self.last_health_check).total_seconds() >= self.health_check_interval
    
    def send_health_check(self):
        """Отправляет health check в Telegram"""
        try:
            health_summary = health_monitor.get_summary()
            cache_stats = data_cache.get_health_stats()
            
            # Определяем статус
            status_emoji = "🟢" if health_summary['status'] == "HEALTHY" else "🟡" if health_summary['status'] == "DEGRADED" else "🔴"
            
            msg = (
                f"{status_emoji} *HEALTH CHECK*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ Время: `{datetime.now().strftime('%H:%M:%S')}`\n"
                f"🏥 Статус: *{health_summary['status']}*\n"
                f"⏱️ Время работы: *{health_summary['uptime_hours']:.1f}ч*\n"
                f"✅ API успешность: *{health_summary['success_rate']:.1f}%*\n"
                f"📦 Кэш попадания: *{cache_stats['cache_hit_rate']:.1f}%*\n"
                f"🔄 API вызовов: *{health_summary['api_calls']}*\n"
                f"📊 Сигналов: *{health_summary['signals_generated']}*\n"
                f"🏦 Биржа: *{current_exchange.id.title()}*\n"
            )
            
            if health_summary['recent_errors'] > 0:
                msg += f"⚠️ Ошибок за час: *{health_summary['recent_errors']}*\n"
            
            msg += f"━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🤖 Бот работает стабильно"
            
            send_telegram(msg)
            self.last_health_check = datetime.now()
            self.consecutive_failures = 0
            
            logger.info("Health check sent successfully")
            
        except Exception as e:
            self.consecutive_failures += 1
            logger.error(f"Health check failed: {e}")
            
            # Если слишком много неудач подряд, отправляем критическое сообщение
            if self.consecutive_failures >= self.max_failures:
                try:
                    critical_msg = (
                        f"🚨 *КРИТИЧЕСКАЯ ОШИБКА*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"❌ Health check не работает!\n"
                        f"🔄 Попыток: *{self.consecutive_failures}*\n"
                        f"⏰ Время: `{datetime.now().strftime('%H:%M:%S')}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔧 Проверьте бота!"
                    )
                    send_telegram(critical_msg)
                    self.consecutive_failures = 0  # Сбрасываем счётчик
                except:
                    pass  # Если даже критическое сообщение не отправилось, просто логируем

# Глобальные переменные
data_cache = DataCache()
health_monitor = HealthMonitor()
data_persistence = DataPersistence()
health_check_system = HealthCheckSystem()
stats = {s: {tf: {'LONG': 0, 'SHORT': 0, 'Total': 0, 'Signals': []} for tf in timeframes.keys()} for s in symbols}
last_summary_time = datetime.now()
last_daily_report = datetime.now()
last_signal_time = {}
current_exchange = exchange  # Текущая активная биржа

# === УЛУЧШЕННЫЙ FETCH С АДАПТИВНЫМИ ЗАДЕРЖКАМИ ===
def safe_fetch_ohlcv(symbol, timeframe, limit=100, retries=3):
    """Безопасное получение данных с улучшенным управлением rate limits и поддержкой прокси"""
    global current_exchange
    
    # Convert symbol to exchange format if needed
    symbol = symbol.replace('/', '')
    
    data_cache.health_stats['total_requests'] += 1
    
    # Check cache first with extended TTL
    cached_data = data_cache.get_cached_data(symbol, timeframe)
    if cached_data and len(cached_data) >= 50:  # Only use cache if we have enough data
        data_cache.health_stats['cache_hits'] += 1
        logger.info(f"Using cached data for {symbol} {timeframe} ({len(cached_data)} candles)")
        return cached_data
    
    # Rate limiting parameters
    min_request_interval = 5.0  # Increased minimum interval to 5 seconds
    request_timeout = 60.0  # Increased timeout to 60 seconds
    
    # Adaptive delays with more aggressive backoff
    base_delay = 10.0  # Increased base delay to 10 seconds
    max_delay = 300.0  # Maximum delay of 5 minutes
    
    # Add initial jitter to spread out requests
    time.sleep(random.uniform(1.0, 3.0))
    
    # Enforce minimum time between requests with exponential backoff
    current_time = time.time()
    time_since_last = current_time - data_cache.last_request_time
    if time_since_last < min_request_interval:
        wait_time = (min_request_interval - time_since_last) * (1 + random.random())
        logger.info(f"Rate limit cooldown: waiting {wait_time:.2f}s...")
        time.sleep(wait_time)
    
    last_exception = None
    last_status_code = None
    
    # Prepare request parameters
    params = {
        'timeout': int(request_timeout * 1000),
        'recvWindow': 120000,  # Increased to 120 seconds
        'limit': limit,
        'price': 'mark',
        'type': 'swap'  # Force linear perpetual for Bybit
    }
    
    for attempt in range(retries):
        try:
            # Update last request time
            data_cache.last_request_time = time.time()
            
            # Calculate dynamic delay with jitter
            if attempt > 0:
                delay = min(base_delay * (3 ** attempt) * random.uniform(0.8, 1.5), max_delay)
                logger.warning(f"Attempt {attempt+1}/{retries} for {symbol} {timeframe}, waiting {delay:.1f}s...")
                time.sleep(delay)
            
            logger.info(f"Fetching {symbol} {timeframe} from {current_exchange.id} (attempt {attempt+1}/{retries})...")
            
            # Try with proxy if available
            proxy = None
            if hasattr(current_exchange, 'proxy') and current_exchange.proxy:
                proxy = current_exchange.proxy
            
            # Make the API request with enhanced parameters
            ohlcv = current_exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=None,
                limit=limit,
                params=params
            )

            # Validate response
            if not ohlcv or len(ohlcv) < 20:  # Reduced minimum candles to 20 for more flexibility
                logger.warning(f"Insufficient data: received {len(ohlcv) if ohlcv else 0} candles")
                if attempt < retries - 1:  # Only continue if we have retries left
                    continue
                return []

            # Cache the successful response
            if data_cache.set_cached_data(symbol, timeframe, ohlcv):
                logger.info(f"Successfully cached {len(ohlcv)} candles for {symbol} {timeframe}")
            
            data_cache.health_stats['successful_requests'] += 1
            return ohlcv
            
        except ccxt.RateLimitExceeded as e:
            last_exception = e
            delay = min(base_delay * (3 ** (attempt + 1)), max_delay)
            logger.warning(f"Rate limit exceeded for {symbol} {timeframe} (attempt {attempt+1}/{retries}), waiting {delay:.1f}s...")
            time.sleep(delay)
            
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, requests.exceptions.RequestException) as e:
            last_exception = e
            logger.error(f"Network/Exchange error ({current_exchange.id}): {str(e)}")
            
            # Switch to fallback exchange if available
            if current_exchange == exchange and fallback_exchange:
                logger.info(f"Switching to fallback exchange: {fallback_exchange.id}")
                current_exchange = fallback_exchange
                time.sleep(base_delay)
                continue
                
            delay = min(base_delay * (2 ** (attempt + 1)), max_delay)
            time.sleep(delay)
            
        except ccxt.ExchangeError as e:
            last_exception = e
            error_msg = str(e).lower()
            
            # Handle geoblocking specifically
            if 'cloudfront' in error_msg or '403' in error_msg or 'geoblocked' in error_msg:
                logger.error(f"Geoblocking detected for {current_exchange.id}. Consider using a proxy or VPN.")
                if current_exchange == exchange and fallback_exchange:
                    logger.info(f"Switching to fallback exchange due to geoblocking: {fallback_exchange.id}")
                    current_exchange = fallback_exchange
                    time.sleep(base_delay)
                    continue
            
            logger.error(f"Exchange error ({current_exchange.id}): {str(e)}")
            delay = min(base_delay * (4 ** (attempt + 1)), max_delay)
            time.sleep(delay)
                
        except Exception as e:
            last_exception = e
            logger.error(f"Unexpected error for {symbol} {timeframe}: {str(e)}", exc_info=True)
            time.sleep(min(base_delay * (3 ** (attempt + 1)), max_delay))
    
    # If all attempts failed, log the final error
    error_msg = f"Failed to fetch {symbol} {timeframe} after {retries} attempts"
    if last_exception:
        error_msg += f": {str(last_exception)}"
    logger.error(error_msg)
    
    # Switch back to main exchange if we're on fallback
    if current_exchange != exchange:
        logger.info(f"Switching back to main exchange: {exchange.id}")
        current_exchange = exchange
    
    # Return empty list to indicate failure
    return []
    raise Exception(f"Failed to fetch {symbol} {timeframe} after {retries} attempts from both exchanges")

# === УЛУЧШЕННЫЕ СТРАТЕГИИ С ВАЛИДАЦИЕЙ ===
def calculate_indicators_safely(df, indicators_config):
    """Безопасное вычисление индикаторов с валидацией"""
    try:
        results = {}
        
        for name, config in indicators_config.items():
            try:
                if config['type'] == 'rolling':
                    results[name] = df[config['column']].rolling(window=config['window']).agg(config['agg'])
                elif config['type'] == 'ta_indicator':
                    indicator_func = getattr(ta, config['module'])
                    if config['params']:
                        results[name] = indicator_func(df[config['column']], **config['params'])
                    else:
                        results[name] = indicator_func(df[config['column']])
                elif config['type'] == 'ta_multi':
                    indicator_func = getattr(ta, config['module'])
                    results[name] = indicator_func(df[config['columns'][0]], df[config['columns'][1]], df[config['columns'][2]], **config['params'])
            except Exception as e:
                logger.error(f"Error calculating {name}: {e}")
                return None
        
        return results
    except Exception as e:
        logger.error(f"Error in calculate_indicators_safely: {e}")
        return None

def validate_signal_conditions(conditions, values):
    """Валидация условий сигнала"""
    try:
        for condition in conditions:
            if not condition(values):
                return False
        return True
    except Exception as e:
        logger.error(f"Error validating signal conditions: {e}")
        return False

# === СТРАТЕГИЯ 1: 4h Turtle (УЛУЧШЕННАЯ) ===
def strategy_4h_turtle(df):
    try:
        if len(df) < 55:
            logger.warning("Insufficient data for 4h Turtle strategy")
            return None, {}
        
        # Конфигурация индикаторов
        indicators_config = {
            'High_15': {'type': 'rolling', 'column': 'high', 'window': 15, 'agg': 'max'},
            'Low_15': {'type': 'rolling', 'column': 'low', 'window': 15, 'agg': 'min'},
            'EMA_21': {'type': 'ta_indicator', 'module': 'trend.ema_indicator', 'column': 'close', 'params': {'window': 21}},
            'EMA_55': {'type': 'ta_indicator', 'module': 'trend.ema_indicator', 'column': 'close', 'params': {'window': 55}},
            'ATR': {'type': 'ta_multi', 'module': 'volatility.average_true_range', 'columns': ['high', 'low', 'close'], 'params': {'window': 14}},
            'ADX': {'type': 'ta_multi', 'module': 'trend.adx', 'columns': ['high', 'low', 'close'], 'params': {'window': 14}},
            'Volume_SMA': {'type': 'rolling', 'column': 'volume', 'window': 20, 'agg': 'mean'},
            'RSI': {'type': 'ta_indicator', 'module': 'momentum.rsi', 'column': 'close', 'params': {'window': 14}}
        }
        
        # Вычисление индикаторов
        indicators = calculate_indicators_safely(df, indicators_config)
        if indicators is None:
            return None, {}
        
        # Добавление индикаторов в DataFrame
        for name, values in indicators.items():
            df[name] = values
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Валидация критических значений
        critical_values = ['ATR', 'ADX', 'RSI', 'EMA_21', 'EMA_55', 'Volume_SMA']
        for val in critical_values:
            if pd.isna(last[val]) or last[val] <= 0:
                logger.warning(f"Invalid {val} value: {last[val]}")
            return None, {}
        
        close = float(last['close'])
        high_15 = float(prev['High_15'])
        low_15 = float(prev['Low_15'])
        ema21 = float(last['EMA_21'])
        ema55 = float(last['EMA_55'])
        atr = float(last['ATR'])
        adx = float(last['ADX'])
        volume = float(last['volume'])
        volume_sma = float(last['Volume_SMA'])
        rsi = float(last['RSI'])
        
        # Проверка на разумные значения
        if atr <= 0 or volume <= 0 or volume_sma <= 0:
            logger.warning("Invalid ATR or volume values")
            return None, {}
        
        signal = None
        params = {}
        
        # LONG условия
        long_conditions = [
            lambda v: v['close'] > v['high_15'],
            lambda v: v['ema21'] > v['ema55'],
            lambda v: v['adx'] > 18,
            lambda v: v['volume'] > v['volume_sma'] * 1.1,
            lambda v: v['rsi'] < 75
        ]
        
        values = {
            'close': close, 'high_15': high_15, 'ema21': ema21, 'ema55': ema55,
            'adx': adx, 'volume': volume, 'volume_sma': volume_sma, 'rsi': rsi
        }
        
        if validate_signal_conditions(long_conditions, values):
            signal = 'LONG'
            params = {
                'entry': close, 
                'sl_distance': atr * 1.8, 
                'tp_distance': atr * 5.5, 
                'atr': atr
            }
        
        # SHORT условия
        elif validate_signal_conditions([
            lambda v: v['close'] < v['low_15'],
            lambda v: v['ema21'] < v['ema55'],
            lambda v: v['adx'] > 18,
            lambda v: v['volume'] > v['volume_sma'] * 1.1,
            lambda v: v['rsi'] > 25
        ], values):
            signal = 'SHORT'
            params = {
                'entry': close, 
                'sl_distance': atr * 1.8, 
                'tp_distance': atr * 5.5, 
                'atr': atr
            }
        
        if signal:
            logger.info(f"4h Turtle signal: {signal} for entry {close:.4f}")
        
        return signal, params
        
    except Exception as e:
        logger.error(f"Strategy 4h Turtle error: {e}")
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

# === УЛУЧШЕННАЯ ПРОВЕРКА СИГНАЛОВ ===
def check_signal(df, symbol, timeframe):
    try:
        if len(df) < 100:
            logger.warning(f"Insufficient data for {symbol} {timeframe}: {len(df)} candles")
            return
        
        strategy_name, strategy_func = get_strategy(timeframe)
        if not strategy_func:
            logger.warning(f"No strategy found for timeframe {timeframe}")
            return
        
        signal, params = strategy_func(df)
        
        if not signal or not params:
            return
        
        signal_key = f"{symbol}_{timeframe}_{signal}"
        now = datetime.now()
        if signal_key in last_signal_time:
            if (now - last_signal_time[signal_key]).total_seconds() < 3600:
                logger.info(f"Signal {signal_key} already sent recently, skipping")
                return
        last_signal_time[signal_key] = now
        
        # Валидация параметров
        if not all(key in params for key in ['entry', 'sl_distance', 'tp_distance', 'atr']):
            logger.error(f"Invalid signal parameters for {symbol} {timeframe}")
            return
        
        rr = params['tp_distance'] / params['sl_distance']
        if rr < MIN_RISK_REWARD:
            logger.info(f"Risk/reward ratio too low: {rr:.2f} for {symbol} {timeframe}")
            return
        
        entry = float(params['entry'])
        sl_distance = float(params['sl_distance'])
        tp_distance = float(params['tp_distance'])
        atr = float(params['atr'])
        
        if entry <= 0 or sl_distance <= 0 or tp_distance <= 0:
            logger.error(f"Invalid price values for {symbol} {timeframe}")
            return
        
        if signal == 'LONG':
            stop_loss = entry - sl_distance
            take_profit = entry + tp_distance
        else:
            stop_loss = entry + sl_distance
            take_profit = entry - tp_distance
        
        # Проверка на разумные значения
        if stop_loss <= 0 or take_profit <= 0:
            logger.error(f"Invalid stop loss or take profit for {symbol} {timeframe}")
            return
        
        risk_amount = BALANCE * RISK_PER_TRADE
        position_size_base = risk_amount / sl_distance
        
        leverage_ratio = (position_size_base * entry) / BALANCE
        leverage_used = min(MAX_LEVERAGE, leverage_ratio)
        position_size = (risk_amount * leverage_used) / sl_distance
        
        potential_profit = tp_distance * position_size
        potential_loss = sl_distance * position_size
        
        commission_cost = position_size * entry * COMMISSION * 2
        net_profit = potential_profit - commission_cost
        net_loss = potential_loss + commission_cost
        
        # Обновление статистики
        stats[symbol][timeframe]['Total'] += 1
        stats[symbol][timeframe][signal] += 1
        stats[symbol][timeframe]['Signals'].append({
            'time': now,
            'type': signal,
            'entry': entry,
            'sl': stop_loss,
            'tp': take_profit
        })
        
        # Сохранение в базу данных
        signal_data = {
            'timestamp': now.isoformat(),
            'symbol': symbol,
            'timeframe': timeframe,
            'signal_type': signal,
            'entry_price': entry,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'atr': atr
        }
        data_persistence.save_signal(signal_data)
        
        # Запись в мониторинг
        health_monitor.record_signal()
        
        # Формирование сообщения
        msg = (
            f"🚨 *{signal} СИГНАЛ*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Пара:* `{symbol}`\n"
            f"⏰ *Таймфрейм:* `{timeframe}`\n"
            f"🎯 *Стратегия:* `{strategy_name}`\n"
            f"🏦 *Биржа:* {current_exchange.id.title()}\n"
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
            f"📈 *ATR:* `{atr:.4f}`\n"
            f"⚡ *Комиссии:* `{commission_cost:.2f}` USD\n\n"
            f"⚠️ *Рекомендации:*\n"
            f"• Строго соблюдай Stop-Loss!\n"
            f"• Используй trailing stop при +5%\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        
        img = plot_signal(df, signal, symbol, timeframe, params)
        send_telegram(msg, img)
        
        logger.info(f"✅ {signal} signal sent: {symbol} {timeframe} at {entry:.4f}")
        
    except Exception as e:
        logger.error(f"Check signal error for {symbol} {timeframe}: {e}")
        health_monitor.record_error("signal_check", str(e))

# === УЛУЧШЕННАЯ СВОДКА С МОНИТОРИНГОМ ===
def send_summary():
    health_summary = health_monitor.get_summary()
    cache_stats = data_cache.get_health_stats()
    
    msg = f"📊 *Статистика сигналов ({current_exchange.id.title()})*\n`{datetime.now().strftime('%Y-%m-%d %H:%M')}`\n━━━━━━━━━━━━━━━━━━━━\n"
    
    total_signals = 0
    for s in symbols:
        for tf in timeframes.keys():
            st = stats[s][tf]
            if st['Total'] > 0:
                msg += f"`{s:<10}` {tf:>3}: 📈{st['LONG']} 📉{st['SHORT']} (всего: {st['Total']})\n"
                total_signals += st['Total']
    
    if total_signals == 0:
        msg += "\n_Пока нет сигналов_"
    
    msg += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🎯 Всего сигналов: *{total_signals}*\n"
    msg += f"🏥 Статус: *{health_summary['status']}*\n"
    msg += f"⏱️ Время работы: *{health_summary['uptime_hours']}ч*\n"
    msg += f"✅ Успешность API: *{health_summary['success_rate']}%*\n"
    msg += f"📦 Кэш попадания: *{cache_stats['cache_hit_rate']}%*\n"
    msg += f"🔄 API вызовов: *{health_summary['api_calls']}*\n"
    
    if health_summary['recent_errors'] > 0:
        msg += f"⚠️ Ошибок за час: *{health_summary['recent_errors']}*\n"
    
    send_telegram(msg)

# === Ежедневная сводка ===
def send_daily_report():
    msg = f"📈 *Ежедневный отчёт (Bybit)*\n`{datetime.now().strftime('%Y-%m-%d')}`\n{'='*30}\n\n"
    
    for s in symbols:
        symbol_total = sum(stats[s][tf]['Total'] for tf in timeframes.keys())
        if symbol_total > 0:
            msg += f"*{s}*\n"
            for tf in timeframes.keys():
                st = stats[s][tf]
                if st['Total'] > 0:
                    long_pct = (st['LONG'] / st['Total'] * 100) if st['Total'] > 0 else 0
                    short_pct = (st['SHORT'] / st['Total'] * 100) if st['Total'] > 0 else 0
                    msg += (f"  {tf}: Всего {st['Total']} | "
                           f"LONG {st['LONG']} ({long_pct:.0f}%) | "
                           f"SHORT {st['SHORT']} ({short_pct:.0f}%)\n")
            msg += "\n"
    
    msg += f"{'='*30}\n🎯 *Лучшая стратегия:* 4h Turtle\n💡 Следи за пробоями!"
    send_telegram(msg)

# === УЛУЧШЕННЫЙ ОСНОВНОЙ ЦИКЛ ===
def send_startup_message():
    """Send the initial startup message with bot configuration"""
    try:
        message = (
            "🚀 *Enhanced Bot Started!*\n\n"
            "🏦 *Exchanges:* Bybit (Primary) + Binance (Fallback)\n"
            "🎯 *Strategies:*\n"
            "• 4h Aggressive Turtle\n"
            "• 12h Momentum Breakout\n"
            "• 1d Strong Trend\n\n"
            "✅ *Monitoring:* " + ", ".join(symbols) + "\n"
            "🛡️ *Features:*\n"
            "• Ultra-Conservative Rate Limiting\n"
            "• Data Validation & Cleaning\n"
            "• Health Monitoring\n"
            "• File-based Data Storage\n"
            "• Enhanced Error Handling\n"
            "• Smart Caching System\n"
            "• 5-minute Health Checks\n\n"
            "⏰ *Intervals:*\n"
            "• 4h: 20 min\n"
            "• 12h: 1 hour\n"
            "• 1d: 2 hours"
        )
        send_telegram(message)
        return True
    except Exception as e:
        print(f"Error sending startup message: {e}")
        return False

def main_loop():
    global last_summary_time, last_daily_report, last_status_time, last_processed_tf
    
    # Send startup message
    if not send_startup_message():
        print("⚠️ Failed to send startup message, will retry later")
    
    # Initialize last_processed_tf to track the last processed timeframe
    last_processed_tf = list(timeframes.keys())[0] if timeframes else "N/A"
    
    # Initialize last_status_time to ensure first status is sent immediately
    last_status_time = datetime.now() - timedelta(minutes=6)
    
    # Очень консервативные интервалы проверки для Bybit
    check_intervals = {
        '4h': 1200,  # 20 минут (увеличено с 10)
        '12h': 3600, # 1 час (увеличено с 30 минут)
        '1d': 7200   # 2 часа (увеличено с 1 часа)
    }
    last_check = {tf: datetime.now() - timedelta(seconds=check_intervals[tf]) for tf in timeframes.keys()}
    
    # Счётчик ошибок для адаптивного поведения
    error_count = 0
    max_errors = 10
    
    while True:
        try:
            now = datetime.now()
            
            # Проверка каждого таймфрейма по расписанию
            for tf in timeframes.keys():
                if (now - last_check[tf]).total_seconds() < check_intervals[tf]:
                    continue
                
                print(f"\n{'='*50}")
                print(f"🔍 Checking {tf} timeframe on {current_exchange.id}...")
                print(f"{'='*50}")
                
                # Обработка символов с улучшенной обработкой ошибок
                successful_symbols = 0
                for i, symbol in enumerate(symbols):
                    try:
                        limit = timeframes[tf]
                        ohlcv = safe_fetch_ohlcv(symbol, tf, limit=limit)
                        
                        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                        
                        check_signal(df, symbol, tf)
                        successful_symbols += 1
                        health_monitor.record_api_call(success=True)
                        
                        # Адаптивная задержка между символами - увеличена для Bybit
                        if i < len(symbols) - 1:  # Не ждём после последнего символа
                            delay = 15 + random.uniform(0, 10)  # 15-25 секунд
                            logger.info(f"Waiting {delay:.1f}s before next symbol...")
                            time.sleep(delay)
                        
                    except Exception as e:
                        logger.error(f"Error {symbol} {tf}: {e}")
                        health_monitor.record_api_call(success=False)
                        health_monitor.record_error("api_call", str(e))
                        error_count += 1
                        
                        # Если слишком много ошибок, увеличиваем интервалы
                        if error_count > max_errors:
                            logger.warning(f"Too many errors ({error_count}), increasing intervals...")
                            for tf_key in check_intervals:
                                check_intervals[tf_key] *= 1.5
                            error_count = 0
                        
                        # Увеличенная задержка при ошибке - ещё больше для Bybit
                        time.sleep(30 + random.uniform(0, 15))  # 30-45 секунд
                        continue
                
                    if successful_symbols > 0:
                        last_check[tf] = now
                        print(f"✅ Successfully processed {successful_symbols}/{len(symbols)} symbols for {tf}")
                    else:
                        print(f"⚠️ No successful requests for {tf}, will retry later")
                
                # Задержка между таймфреймами - увеличена для Bybit
                time.sleep(20 + random.uniform(0, 10))  # 20-30 секунд
            
            # Health check каждые 5 минут
            if health_check_system.should_send_health_check():
                health_check_system.send_health_check()
                
            # Send status update every 5 minutes
            status_interval = timedelta(minutes=5)
            time_since_last_status = now - last_status_time
            
            if time_since_last_status > status_interval:
                try:
                    print(f"\n🔔 Preparing status update (last was {time_since_last_status} ago)")
                    status_msg = (
                        f"🤖 *Bot Status Update*\n"
                        f"• Uptime: {health_monitor.get_uptime()}\n"
                        f"• API Success Rate: {health_monitor.get_success_rate():.1f}%\n"
                        f"• Last Check: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"• Active Symbols: {len(symbols)}"
                        f" ({', '.join(symbols)})\n"
                        f"• Last TF: {last_processed_tf}\n"
                        f"• Next Summary: {last_summary_time + timedelta(minutes=30) if last_summary_time else 'N/A'}"
                    )
                    print("📤 Sending status update to Telegram...")
                    send_telegram(status_msg)
                    last_status_time = now
                    print(f"✅ Status update sent at {now.strftime('%H:%M:%S')}")
                except Exception as e:
                    print(f"❌ Error sending status update: {e}")
                    print(f"Error details: {str(e)}\n{traceback.format_exc()}")
                except Exception as e:
                    print(f"Error sending status update: {e}")
            
            # Update last processed timeframe at the end of processing
            if 'tf' in locals():
                last_processed_tf = tf
            
            # Send summary every 30 minutes
            summary_interval = timedelta(minutes=30)
            time_since_last_summary = now - last_summary_time
            
            if time_since_last_summary > summary_interval:
                try:
                    print(f"\n📊 Preparing summary (last was {time_since_last_summary} ago)")
                    print("📤 Sending summary to Telegram...")
                    send_summary()
                    last_summary_time = now
                    print(f"✅ Summary sent at {now.strftime('%H:%M:%S')}")
                except Exception as e:
                    print(f"❌ Error sending summary: {e}")
                    print(f"Error details: {str(e)}\n{traceback.format_exc()}")
            
            # Send daily report once per day around 23:00
            current_hour = now.hour
            current_minute = now.minute
            if current_hour == 23 and current_minute < 5:
                if (now - last_daily_report).days >= 1:
                    try:
                        send_daily_report()
                        last_daily_report = now
                        # Also update summary time to avoid duplicate messages
                        last_summary_time = now
                    except Exception as e:
                        print(f"Error sending daily report: {e}")
            
            # Sleep with jitter to avoid rate limiting
            sleep_time = 300 + random.uniform(0, 60)  # 5-6 minutes
            print(f"😴 Sleeping {sleep_time:.1f}s before next cycle...")
            time.sleep(sleep_time)
            
        except Exception as e:
            error_msg = f"❌ *Критическая ошибка:*\n`{str(e)[:200]}`"
            send_telegram(error_msg)
            print(f"Main loop error: {e}")
            error_count += 1
            
            # Экспоненциальная задержка при критических ошибках
            sleep_time = min(300, 60 * (2 ** min(error_count, 5)))
            print(f"💤 Critical error sleep: {sleep_time}s")
            time.sleep(sleep_time)

# === Запуск ===
if __name__ == '__main__':
    print("="*70)
    print("🚀 Enhanced Signal Bot Starting...")
    print(f"🏦 Primary Exchange: Bybit")
    print(f"🔄 Fallback Exchange: Binance")
    print(f"📊 Symbols: {symbols}")
    print(f"⏰ Timeframes: {list(timeframes.keys())}")
    print(f"💰 Balance: {BALANCE} USD | Risk: {RISK_PER_TRADE*100}%")
    print(f"⚡ Max Leverage: {MAX_LEVERAGE}x")
    print(f"🛡️ Rate Limit Protection: ENABLED")
    print(f"📦 Smart Caching: ENABLED")
    print(f"🔄 Adaptive Delays: ENABLED")
    print(f"🏥 Health Monitoring: ENABLED")
    print(f"💾 File-based Storage: ENABLED")
    print(f"🔄 5-min Health Checks: ENABLED")
    print(f"✅ Data Validation: ENABLED")
    print(f"📝 Logging: ENABLED")
    print("="*70)
    
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n⛔ Бот остановлен пользователем")
        send_telegram("⛔ *Бот остановлен*")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        send_telegram(f"❌ *Бот упал:* `{str(e)[:200]}`")