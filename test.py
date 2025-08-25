"""
Binance Futures Bot – Versión 7.3 - Panel Web Avanzado (Configuración Inteligente)
------------------------------------------------------------------------------------
Descripción:
Versión mejorada con sistema inteligente de configuración que evita llamadas API
innecesarias y elimina mensajes de error spam.
"""
from __future__ import annotations
import os, time, math, logging
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import random

from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, FUTURE_ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_STOP_MARKET, FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET
from binance.exceptions import BinanceAPIException

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS

# -------------------- CONFIGURACIÓN -------------------- #
@dataclass
class CONFIG:
    LEVERAGE: int = 20
    MARGIN_TYPE: str = "CROSSED"
    FIXED_MARGIN_PER_TRADE_USDT: float = 2.0
    MAX_CONCURRENT_POS: int = 10
    NUM_SYMBOLS_TO_SCAN: int = 300
    MIN_24H_VOLUME: float = 1_000_000
    EXCLUDE_SYMBOLS: tuple = ("BTCDOMUSDT", "DEFIUSDT")
    TIMEFRAME: str = "5m"
    CANDLES_LIMIT: int = 100
    FAST_EMA: int = 9
    SLOW_EMA: int = 21
    RSI_PERIOD: int = 14
    RSI_OVERBOUGHT: int = 70
    RSI_OVERSOLD: int = 30
    ATR_PERIOD: int = 14
    BOLLINGER_PERIOD: int = 20
    BOLLINGER_STD: float = 2.0
    VOLUME_AVG_PERIOD: int = 20
    VOLUME_SPIKE_FACTOR: float = 1.5
    ATR_MULT_SL: float = 2.0
    ATR_MULT_TP: float = 3.0
    POLL_SEC: float = 60.0
    DRY_RUN: bool = True
    MAX_WORKERS_KLINE: int = 20
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE: str = "bot_web_v7.3.log"
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"

config = CONFIG()

# -------------------- SERVIDOR WEB Y LOGGING -------------------- #
app = Flask(__name__, template_folder='.')
CORS(app)
app.config['SECRET_KEY'] = 'binance_futures_bot_secret_key_2024'
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

class SocketIOHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            level = record.levelname
            socketio.emit('log_update', {'message': log_entry, 'level': level})
        except:
            pass

log = logging.getLogger("BinanceFuturesBot")
log.setLevel(getattr(logging, config.LOG_LEVEL))

for handler in log.handlers[:]:
    log.removeHandler(handler)

formatter = logging.Formatter(config.LOG_FORMAT)

file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8', mode='a')
file_handler.setFormatter(formatter)
file_handler.setLevel(getattr(logging, config.LOG_LEVEL))

socket_handler = SocketIOHandler()
socket_handler.setFormatter(formatter)
socket_handler.setLevel(getattr(logging, config.LOG_LEVEL))

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(getattr(logging, config.LOG_LEVEL))

log.addHandler(file_handler)
log.addHandler(socket_handler)
log.addHandler(console_handler)

logging.getLogger('binance').setLevel(logging.WARNING)
logging.getLogger('engineio').setLevel(logging.WARNING)
logging.getLogger('socketio').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# -------------------- ESTADO GLOBAL -------------------- #
bot_thread = None
app_state = {
    "running": False,
    "status_message": "Detenido",
    "cycle_count": 0,
    "signals_found_this_cycle": 0,
    "open_positions": {},
    "last_signals": [],
    "config": asdict(config),
    "top_coins": [],
    "performance_stats": {"profit": 0, "win_rate": 0, "trades_count": 0},
    "balance": 0.0,
    "account_info": {}
}
state_lock = threading.Lock()

# -------------------- CLIENTE BINANCE -------------------- #
class BinanceFutures:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError("API keys no configuradas. Crea un archivo .env con BINANCE_API_KEY y BINANCE_API_SECRET")

        self.client = Client(api_key, api_secret, testnet=True)

        self.symbol_config_cache = set()
        self.symbol_info_cache = {}
        self.cache_expiry = {}
        self.cache_ttl = 3600

        log.info("🔧 CONECTADO A BINANCE FUTURES TESTNET")

        try:
            self.exchange_info = self.client.futures_exchange_info()
            self.client.futures_account()
            log.info(f"✅ Conexión establecida correctamente")
        except Exception as e:
            log.error(f"❌ Error conectando a Binance: {e}")
            raise RuntimeError(f"No se pudo conectar a Binance: {e}")

    def _is_cache_valid(self, symbol: str) -> bool:
        return (symbol in self.cache_expiry and
                time.time() < self.cache_expiry[symbol])

    def _safe_api_call(self, func, *args, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(0.1)
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                non_critical_codes = {
                    -4046: "No need to change margin type",
                    -4048: "Margin type cannot be changed if there is open order",
                    -4051: "Margin type cannot be changed if there is position",
                    -4028: "Leverage not modified",
                    -4161: "Max leverage",
                    -1111: "Precision is over the maximum defined for this asset",
                    -2019: "Margin is insufficient",
                    # Agregado para manejar el error del filtro de precio
                    -4131: "The counterparty's best price does not meet the PERCENT_PRICE filter limit."
                }
                
                if e.code in non_critical_codes:
                    symbol_name = kwargs.get('symbol', args[0] if args else 'N/A')
                    log.debug(f"API {func.__name__} para {symbol_name}: {non_critical_codes.get(e.code, e.message)}")

                    if e.code == -4131:
                         # Reinicia el ciclo para obtener un precio actualizado
                         raise Exception("Market price changed. Re-evaluating order.")

                    return None
                else:
                    if attempt == max_retries - 1:
                        log.error(f"Error API Binance en {func.__name__}: {e.code} - {e.message}")
                        return None
                    time.sleep(1 * (attempt + 1))
            except Exception as e:
                if attempt == max_retries - 1:
                    log.error(f"Error general en {func.__name__}: {e}")
                    return None
                time.sleep(1 * (attempt + 1))
        return None

    def get_symbol_configuration(self, symbol: str) -> Dict:
        try:
            if self._is_cache_valid(symbol) and symbol in self.symbol_info_cache:
                return self.symbol_info_cache[symbol]

            position_info = self._safe_api_call(self.client.futures_position_information, symbol=symbol)

            if position_info and len(position_info) > 0:
                pos_data = position_info[0]
                config_info = {
                    'leverage': int(pos_data.get('leverage', 1)),
                    'marginType': pos_data.get('marginType', 'cross').upper()
                }
            else:
                config_info = {'leverage': 1, 'marginType': 'ISOLATED'}

            self.symbol_info_cache[symbol] = config_info
            self.cache_expiry[symbol] = time.time() + self.cache_ttl

            return config_info

        except Exception as e:
            log.debug(f"No se pudo obtener configuración de {symbol}: {e}")
            return {'leverage': 1, 'marginType': 'ISOLATED'}

    def set_leverage_and_margin(self, symbol: str) -> bool:
        try:
            if (symbol in self.symbol_config_cache and
                self._is_cache_valid(symbol)):
                return True

            current_config = self.get_symbol_configuration(symbol)
            needs_leverage_change = current_config['leverage'] != config.LEVERAGE
            needs_margin_change = current_config['marginType'] != config.MARGIN_TYPE

            changes_made = []

            if needs_leverage_change:
                result = self._safe_api_call(
                    self.client.futures_change_leverage,
                    symbol=symbol,
                    leverage=config.LEVERAGE
                )
                if result is not None:
                    log.info(f"⚡ Leverage configurado para {symbol}: {config.LEVERAGE}x")
                    changes_made.append("leverage")
                    if symbol in self.symbol_info_cache:
                        self.symbol_info_cache[symbol]['leverage'] = config.LEVERAGE

            if needs_margin_change:
                result = self._safe_api_call(
                    self.client.futures_change_margin_type,
                    symbol=symbol,
                    marginType=config.MARGIN_TYPE
                )
                if result is not None:
                    log.info(f"📊 Tipo de margen configurado para {symbol}: {config.MARGIN_TYPE}")
                    changes_made.append("margin")
                    if symbol in self.symbol_info_cache:
                        self.symbol_info_cache[symbol]['marginType'] = config.MARGIN_TYPE
                else:
                    if symbol in self.symbol_info_cache:
                        self.symbol_info_cache[symbol]['marginType'] = config.MARGIN_TYPE

            if not needs_leverage_change and not needs_margin_change:
                log.debug(f"✅ {symbol} ya configurado correctamente")
            elif changes_made:
                log.info(f"✅ {symbol} configurado: {', '.join(changes_made)}")

            self.symbol_config_cache.add(symbol)
            self.cache_expiry[symbol] = time.time() + self.cache_ttl

            return True

        except Exception as e:
            log.error(f"Error configurando {symbol}: {e}")
            return False

    def clear_configuration_cache(self, symbol: str = None):
        if symbol:
            self.symbol_config_cache.discard(symbol)
            self.symbol_info_cache.pop(symbol, None)
            self.cache_expiry.pop(symbol, None)
        else:
            self.symbol_config_cache.clear()
            self.symbol_info_cache.clear()
            self.cache_expiry.clear()
            log.info("🧹 Cache de configuración limpiado")

    def get_balance(self) -> float:
        try:
            balance_info = self._safe_api_call(self.client.futures_account_balance)
            if not balance_info:
                return 0.0

            for asset in balance_info:
                if asset['asset'] == 'USDT':
                    return float(asset['balance'])
            return 0.0
        except Exception as e:
            log.error(f"Error obteniendo balance: {e}")
            return 0.0

    def get_account_info(self) -> Dict:
        account = self._safe_api_call(self.client.futures_account)
        return account if account else {}

    def get_symbol_filters(self, symbol: str) -> Optional[Dict[str, float]]:
        try:
            for s in self.exchange_info['symbols']:
                if s['symbol'] == symbol:
                    filters = {f['filterType']: f for f in s['filters']}

                    result = {}

                    if 'LOT_SIZE' in filters:
                        result["stepSize"] = float(filters['LOT_SIZE']['stepSize'])
                        result["minQty"] = float(filters['LOT_SIZE']['minQty'])

                    if 'PRICE_FILTER' in filters:
                        result["tickSize"] = float(filters['PRICE_FILTER']['tickSize'])

                    if 'MIN_NOTIONAL' in filters:
                        result["minNotional"] = float(filters['MIN_NOTIONAL']['notional'])
                    elif 'NOTIONAL' in filters:
                        result["minNotional"] = float(filters['NOTIONAL']['minNotional'])
                    else:
                        result["minNotional"] = 5.0

                    return result
            return None
        except Exception as e:
            log.error(f"Error obteniendo filtros para {symbol}: {e}")
            return None

    @staticmethod
    def round_value(value: float, step: float) -> float:
        if step == 0:
            return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)

    def get_top_symbols_by_volume(self, limit: int = 200) -> List[str]:
        try:
            tickers = self._safe_api_call(self.client.futures_ticker)
            if not tickers:
                return []

            usdt_pairs = []
            for ticker in tickers:
                symbol = ticker['symbol']
                if (symbol.endswith('USDT') and
                    symbol not in config.EXCLUDE_SYMBOLS and
                    float(ticker['quoteVolume']) > config.MIN_24H_VOLUME):
                    usdt_pairs.append({
                        'symbol': symbol,
                        'volume': float(ticker['quoteVolume'])
                    })

            usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
            return [pair['symbol'] for pair in usdt_pairs[:limit]]

        except Exception as e:
            log.error(f"Error obteniendo símbolos por volumen: {e}")
            return []

    def get_klines_batch(self, symbols: List[str], timeframe: str, limit: int) -> Dict[str, pd.DataFrame]:
        results = {}

        def fetch_klines(symbol):
            try:
                klines = self._safe_api_call(
                    self.client.futures_klines,
                    symbol=symbol,
                    interval=timeframe,
                    limit=limit
                )

                if not klines or len(klines) < 50:
                    return None

                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_av', 'trades', 'tb_base_av', 'tb_quote_av', 'ignore'
                ])

                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

                return symbol, df

            except Exception as e:
                log.error(f"Error obteniendo klines para {symbol}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=config.MAX_WORKERS_KLINE) as executor:
            future_to_symbol = {executor.submit(fetch_klines, symbol): symbol for symbol in symbols}

            for future in as_completed(future_to_symbol):
                result = future.result()
                if result:
                    symbol, df = result
                    results[symbol] = df

        return results

    def get_positions(self) -> Dict[str, Dict]:
        try:
            positions = self._safe_api_call(self.client.futures_position_information)
            if not positions:
                return {}

            open_positions = {}
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0.0:
                    open_positions[pos['symbol']] = pos

            return open_positions

        except Exception as e:
            log.error(f"Error obteniendo posiciones: {e}")
            return {}

    def place_market_order(self, symbol: str, side: str, quantity: float) -> Optional[Dict]:
        try:
            order = self._safe_api_call(
                self.client.futures_create_order,
                symbol=symbol,
                side=side,
                type=FUTURE_ORDER_TYPE_MARKET,
                quantity=quantity
            )

            if order:
                log.info(f"✅ Orden ejecutada: {side} {quantity} {symbol}")
                if symbol in self.symbol_config_cache:
                    self.clear_configuration_cache(symbol)
                return order
            else:
                log.error(f"❌ Error ejecutando orden: {side} {quantity} {symbol}")
                return None

        except Exception as e:
            log.error(f"Error colocando orden de mercado: {e}")
            return None

    def place_stop_orders(self, symbol: str, side: str, sl_price: float, tp_price: float):
        try:
            close_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY

            filters = self.get_symbol_filters(symbol)
            if not filters:
                log.error(f"No se pudieron obtener filtros para {symbol}")
                return

            sl_price = self.round_value(sl_price, filters['tickSize'])
            tp_price = self.round_value(tp_price, filters['tickSize'])

            try:
                self._safe_api_call(self.client.futures_cancel_all_open_orders, symbol=symbol)
            except:
                pass

            try:
                self._safe_api_call(
                    self.client.futures_create_order,
                    symbol=symbol,
                    side=close_side,
                    type=FUTURE_ORDER_TYPE_STOP_MARKET,
                    stopPrice=sl_price,
                    closePosition=True
                )
                log.info(f"🛡️ Stop Loss colocado en {sl_price} para {symbol}")
            except Exception as e:
                log.error(f"Error colocando Stop Loss: {e}")

            try:
                self._safe_api_call(
                    self.client.futures_create_order,
                    symbol=symbol,
                    side=close_side,
                    type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET,
                    stopPrice=tp_price,
                    closePosition=True
                )
                log.info(f"🎯 Take Profit colocado en {tp_price} para {symbol}")
            except Exception as e:
                log.error(f"Error colocando Take Profit: {e}")

        except Exception as e:
            log.error(f"Error colocando órdenes de protección: {e}")

# -------------------- ESTRATEGIA DE TRADING -------------------- #
class TradingStrategy:
    @staticmethod
    def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Añade indicadores técnicos al DataFrame"""
        try:
            df['ema_fast'] = df['close'].ewm(span=config.FAST_EMA, adjust=False).mean()
            df['ema_slow'] = df['close'].ewm(span=config.SLOW_EMA, adjust=False).mean()

            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=config.RSI_PERIOD).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=config.RSI_PERIOD).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))

            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()

            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            df['atr'] = true_range.rolling(config.ATR_PERIOD).mean()

            sma = df['close'].rolling(window=config.BOLLINGER_PERIOD).mean()
            std = df['close'].rolling(window=config.BOLLINGER_PERIOD).std()
            df['bb_upper'] = sma + (std * config.BOLLINGER_STD)
            df['bb_lower'] = sma - (std * config.BOLLINGER_STD)
            df['bb_middle'] = sma

            df['volume_ma'] = df['volume'].rolling(window=config.VOLUME_AVG_PERIOD).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']

            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']

            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.ffill().bfill()

            return df

        except Exception as e:
            log.error(f"Error calculando indicadores: {e}")
            return df

    @staticmethod
    def detect_signal(df: pd.DataFrame, symbol: str) -> Optional[str]:
        try:
            if len(df) < 50:
                return None

            current = df.iloc[-1]
            previous = df.iloc[-2]

            volume_spike = current['volume_ratio'] > config.VOLUME_SPIKE_FACTOR

            long_conditions = [
                (previous['ema_fast'] <= previous['ema_slow'] and
                 current['ema_fast'] > current['ema_slow']),

                (previous['close'] <= previous['bb_upper'] and
                 current['close'] > current['bb_upper']),

                (current['rsi'] > 30 and previous['rsi'] <= 30),

                (previous['macd'] <= previous['macd_signal'] and
                 current['macd'] > current['macd_signal'])
            ]

            short_conditions = [
                (previous['ema_fast'] >= previous['ema_slow'] and
                 current['ema_fast'] < current['ema_slow']),

                (previous['close'] >= previous['bb_lower'] and
                 current['close'] < current['bb_lower']),

                (current['rsi'] < 70 and previous['rsi'] >= 70),

                (previous['macd'] >= previous['macd_signal'] and
                 current['macd'] < current['macd_signal'])
            ]

            rsi_ok_long = current['rsi'] < config.RSI_OVERBOUGHT
            rsi_ok_short = current['rsi'] > config.RSI_OVERSOLD

            if any(long_conditions) and volume_spike and rsi_ok_long:
                return 'LONG'
            elif any(short_conditions) and volume_spike and rsi_ok_short:
                return 'SHORT'

            return None

        except Exception as e:
            log.error(f"Error detectando señal para {symbol}: {e}")
            return None

    @staticmethod
    def calculate_signal_strength(df: pd.DataFrame, signal: str) -> float:
        try:
            current = df.iloc[-1]

            volume_strength = min(5.0, current['volume_ratio'])

            if signal == 'LONG':
                rsi_strength = (config.RSI_OVERBOUGHT - current['rsi']) / 20
                momentum = (current['close'] - current['bb_lower']) / current['atr']
            else:
                rsi_strength = (current['rsi'] - config.RSI_OVERSOLD) / 20
                momentum = (current['bb_upper'] - current['close']) / current['atr']

            macd_strength = abs(current['macd_histogram']) * 100

            strength = (volume_strength * 0.4 +
                       rsi_strength * 0.3 +
                       momentum * 0.2 +
                       macd_strength * 0.1)

            return max(0, min(10, strength))

        except Exception as e:
            log.error(f"Error calculando fuerza de señal: {e}")
            return 0.0

# -------------------- GESTIÓN DE POSICIONES -------------------- #
class PositionManager:
    @staticmethod
    def calculate_position_size(api: BinanceFutures, symbol: str, price: float) -> float:
        try:
            if price <= 0:
                return 0.0

            notional_value = config.FIXED_MARGIN_PER_TRADE_USDT * config.LEVERAGE
            quantity = notional_value / price

            filters = api.get_symbol_filters(symbol)
            if not filters:
                log.error(f"No se pudieron obtener filtros para {symbol}")
                return 0.0

            min_qty = filters.get('minQty', 0)
            step_size = filters.get('stepSize', 0.001)

            quantity = api.round_value(quantity, step_size)

            if quantity < min_qty:
                log.warning(f"Cantidad {quantity} menor que mínimo {min_qty} para {symbol}")
                return 0.0

            notional = quantity * price
            min_notional = filters.get('minNotional', 5.0)

            if notional < min_notional:
                log.warning(f"Valor nocional {notional:.2f} menor que mínimo {min_notional} para {symbol}")
                return 0.0

            return quantity

        except Exception as e:
            log.error(f"Error calculando tamaño de posición: {e}")
            return 0.0

# -------------------- BOT PRINCIPAL -------------------- #
class TradingBot:
    def __init__(self):
        self.api = BinanceFutures()
        self.cycle_count = 0
        self.configured_symbols: Set[str] = set()
        self.last_signal_time = {}
        self.performance_tracker = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_profit': 0.0,
            'start_balance': 0.0
        }

    def run(self):
        global app_state
        log.info("🚀 INICIANDO BOT DE TRADING BINANCE FUTURES v7.3")

        initial_balance = self.api.get_balance()
        self.performance_tracker['start_balance'] = initial_balance

        while app_state["running"]:
            cycle_start_time = time.time()
            self.cycle_count += 1

            try:
                with state_lock:
                    app_state["status_message"] = "Actualizando datos de cuenta..."
                    app_state["cycle_count"] = self.cycle_count
                    app_state["balance"] = self.api.get_balance()
                    app_state["account_info"] = self.api.get_account_info()

                log.info(f"📊 Ciclo {self.cycle_count} - Balance: {app_state['balance']:.2f} USDT")

                open_positions = self.api.get_positions()
                with state_lock:
                    app_state["open_positions"] = open_positions

                self._update_performance_stats(open_positions)

                if len(open_positions) >= config.MAX_CONCURRENT_POS:
                    log.info(f"🔒 Límite de posiciones alcanzado ({len(open_positions)}/{config.MAX_CONCURRENT_POS})")
                    with state_lock:
                        app_state["status_message"] = f"Límite de posiciones alcanzado ({len(open_positions)}/{config.MAX_CONCURRENT_POS})"
                    time.sleep(config.POLL_SEC)
                    continue

                with state_lock:
                    app_state["status_message"] = "Obteniendo símbolos para escanear..."

                symbols_to_scan = self.api.get_top_symbols_by_volume(config.NUM_SYMBOLS_TO_SCAN)
                if not symbols_to_scan:
                    log.warning("⚠️ No se pudieron obtener símbolos para escanear")
                    time.sleep(config.POLL_SEC)
                    continue

                log.info(f"📈 Escaneando {len(symbols_to_scan)} símbolos")

                self._configure_symbols_intelligently(symbols_to_scan, open_positions)

                with state_lock:
                    app_state["status_message"] = "Buscando señales de trading..."

                signals = self._scan_for_signals(symbols_to_scan, open_positions)

                with state_lock:
                    app_state["signals_found_this_cycle"] = len(signals)

                    # CORREGIDO: Eliminar el 'data' DataFrame y solo enviar datos serializables
                    app_state["last_signals"] = [{
                        'symbol': s['symbol'],
                        'signal': s['signal'],
                        'strength': s['strength'],
                        'price': s['price'],
                        'timestamp': s['timestamp']
                    } for s in signals[:10]]

                if signals:
                    log.info(f"🎯 Encontradas {len(signals)} señales")
                    self._execute_best_signals(signals, open_positions)
                else:
                    log.info("🔍 No se encontraron señales en este ciclo")

                self._update_top_coins_data(symbols_to_scan)

                cycle_duration = time.time() - cycle_start_time
                sleep_time = max(5, config.POLL_SEC - cycle_duration)

                with state_lock:
                    app_state["status_message"] = f"Esperando {sleep_time:.0f}s para próximo ciclo..."

                log.info(f"⏱️ Ciclo completado en {cycle_duration:.2f}s. Esperando {sleep_time:.0f}s...")
                socketio.emit('status_update', app_state)

                time.sleep(sleep_time)

            except Exception as e:
                log.error(f"❌ Error en ciclo principal: {e}", exc_info=True)
                with state_lock:
                    app_state["status_message"] = f"Error: {str(e)}"
                socketio.emit('status_update', app_state)
                time.sleep(30)

        log.info("🛑 Bot detenido")

    def _configure_symbols_intelligently(self, symbols: List[str], open_positions: Dict):
        try:
            symbols_to_configure = []

            for symbol in symbols[:20]:
                if (symbol not in open_positions and
                    symbol not in self.api.symbol_config_cache):
                    symbols_to_configure.append(symbol)

            if symbols_to_configure:
                log.info(f"🔧 Configurando {len(symbols_to_configure)} símbolos nuevos...")
                configured_count = 0
                for symbol in symbols_to_configure:
                    if self.api.set_leverage_and_margin(symbol):
                        configured_count += 1
                    time.sleep(0.1)
                    if configured_count >= 10:
                        break
                if configured_count > 0:
                    log.info(f"✅ {configured_count} símbolos configurados correctamente")
            else:
                log.debug("🔧 Todos los símbolos relevantes ya están configurados")

        except Exception as e:
            log.error(f"Error configurando símbolos: {e}")

    def _update_performance_stats(self, open_positions: Dict):
        try:
            current_balance = app_state.get("balance", 0.0)
            start_balance = self.performance_tracker['start_balance']

            if start_balance > 0:
                total_profit = current_balance - start_balance
                self.performance_tracker['total_profit'] = total_profit

                total_trades = self.performance_tracker['total_trades']
                win_rate = 0
                if total_trades > 0:
                    win_rate = (self.performance_tracker['winning_trades'] / total_trades) * 100

                with state_lock:
                    app_state["performance_stats"] = {
                        "profit": total_profit,
                        "win_rate": win_rate,
                        "trades_count": total_trades
                    }
        except Exception as e:
            log.error(f"Error actualizando estadísticas: {e}")

    def _scan_for_signals(self, symbols: List[str], open_positions: Dict) -> List[Dict]:
        try:
            symbols_to_check = [s for s in symbols if s not in open_positions]

            if not symbols_to_check:
                return []

            klines_data = self.api.get_klines_batch(symbols_to_check, config.TIMEFRAME, config.CANDLES_LIMIT)

            if not klines_data:
                log.warning("⚠️ No se pudieron obtener datos de klines")
                return []

            signals = []

            for symbol, df in klines_data.items():
                try:
                    df_with_indicators = TradingStrategy.add_technical_indicators(df)

                    if df_with_indicators.isnull().any().any():
                        continue

                    signal_type = TradingStrategy.detect_signal(df_with_indicators, symbol)

                    if signal_type:
                        current_time = time.time()
                        last_signal_key = f"{symbol}_{signal_type}"

                        if (last_signal_key in self.last_signal_time and
                            current_time - self.last_signal_time[last_signal_key] < 300):
                            continue

                        self.last_signal_time[last_signal_key] = current_time

                        strength = TradingStrategy.calculate_signal_strength(df_with_indicators, signal_type)
                        current_price = float(df_with_indicators.iloc[-1]['close'])
                        atr = float(df_with_indicators.iloc[-1]['atr'])

                        # AÑADIR SÓLO DATOS SERIALIZABLES AQUÍ
                        signals.append({
                            'symbol': symbol,
                            'signal': signal_type,
                            'strength': strength,
                            'price': current_price,
                            'atr': atr,
                            'timestamp': current_time
                        })

                        log.info(f"🎯 Señal {signal_type} detectada en {symbol} (fuerza: {strength:.2f})")

                except Exception as e:
                    log.error(f"Error procesando {symbol}: {e}")
                    continue

            signals.sort(key=lambda x: x['strength'], reverse=True)
            return signals

        except Exception as e:
            log.error(f"Error escaneando señales: {e}")
            return []

    def _execute_best_signals(self, signals: List[Dict], open_positions: Dict):
        try:
            max_new_positions = config.MAX_CONCURRENT_POS - len(open_positions)
            executed_count = 0

            for signal in signals:
                if executed_count >= max_new_positions:
                    break

                symbol = signal['symbol']
                signal_type = signal['signal']
                price = signal['price']
                atr = signal['atr']

                quantity = PositionManager.calculate_position_size(self.api, symbol, price)

                if quantity <= 0:
                    log.warning(f"⚠️ No se pudo calcular cantidad para {symbol}")
                    continue

                side = SIDE_BUY if signal_type == 'LONG' else SIDE_SELL

                if signal_type == 'LONG':
                    sl_price = price - (config.ATR_MULT_SL * atr)
                    tp_price = price + (config.ATR_MULT_TP * atr)
                else:
                    sl_price = price + (config.ATR_MULT_SL * atr)
                    tp_price = price - (config.ATR_MULT_TP * atr)

                log.info(f"🚀 Ejecutando {signal_type} en {symbol}: {quantity} @ {price:.4f}")

                order = self.api.place_market_order(symbol, side, quantity)

                if order and order.get('status') == 'FILLED':
                    executed_count += 1
                    self.performance_tracker['total_trades'] += 1

                    self.api.place_stop_orders(symbol, side, sl_price, tp_price)

                    log.info(f"✅ Posición abierta en {symbol}: {signal_type} {quantity} @ {price:.4f}")
                    log.info(f"🛡️ SL: {sl_price:.4f} | 🎯 TP: {tp_price:.4f}")

                    time.sleep(1)
                else:
                    log.error(f"❌ Error ejecutando orden para {symbol}")

            if executed_count > 0:
                log.info(f"✅ Se ejecutaron {executed_count} nuevas posiciones")

        except Exception as e:
            log.error(f"Error ejecutando señales: {e}")

    def _update_top_coins_data(self, symbols: List[str]):
        try:
            top_coins = []

            for symbol in symbols[:5]:
                try:
                    ticker = self.api._safe_api_call(self.api.client.futures_ticker, symbol=symbol)
                    if ticker:
                        top_coins.append({
                            'symbol': symbol,
                            'price': float(ticker['lastPrice']),
                            'change': float(ticker['priceChangePercent']),
                            'volume': float(ticker['quoteVolume'])
                        })
                except Exception as e:
                    log.error(f"Error obteniendo ticker para {symbol}: {e}")
                    continue

            with state_lock:
                app_state["top_coins"] = top_coins

        except Exception as e:
            log.error(f"Error actualizando top coins: {e}")

# -------------------- API WEB ENDPOINTS -------------------- #

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    with state_lock:
        return jsonify(app_state)

@app.route('/api/start', methods=['POST'])
def start_bot():
    global bot_thread

    with state_lock:
        if app_state["running"]:
            return jsonify({"status": "error", "message": "El bot ya está ejecutándose"})

        app_state["running"] = True
        app_state["status_message"] = "Iniciando bot..."
        app_state["cycle_count"] = 0

    try:
        bot_instance = TradingBot()
        bot_thread = threading.Thread(target=bot_instance.run, daemon=True)
        bot_thread.start()

        log.info("🚀 Bot iniciado desde panel web")
        return jsonify({"status": "success", "message": "Bot iniciado correctamente"})

    except Exception as e:
        with state_lock:
            app_state["running"] = False
            app_state["status_message"] = f"Error al iniciar: {str(e)}"

        log.error(f"Error iniciando bot: {e}")
        return jsonify({"status": "error", "message": f"Error al iniciar: {str(e)}"})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    with state_lock:
        if not app_state["running"]:
            return jsonify({"status": "error", "message": "El bot no está ejecutándose"})

        app_state["running"] = False
        app_state["status_message"] = "Deteniendo bot..."

    log.info("🛑 Bot detenido desde panel web")
    return jsonify({"status": "success", "message": "Señal de detención enviada"})

@app.route('/api/update_config', methods=['POST'])
def update_config():
    try:
        new_config = request.json

        for key, value in new_config.items():
            key_upper = key.upper()
            if hasattr(config, key_upper):
                current_value = getattr(config, key_upper)
                if isinstance(current_value, bool):
                    value = bool(value) if isinstance(value, bool) else str(value).lower() == 'true'
                elif isinstance(current_value, int):
                    value = int(float(value))
                elif isinstance(current_value, float):
                    value = float(value)

                setattr(config, key_upper, value)

        with state_lock:
            app_state["config"] = asdict(config)

        log.info(f"📝 Configuración actualizada: {list(new_config.keys())}")
        socketio.emit('config_updated', app_state["config"])

        return jsonify({"status": "success", "message": "Configuración actualizada"})

    except Exception as e:
        log.error(f"Error actualizando configuración: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/manual_trade', methods=['POST'])
def manual_trade():
    try:
        data = request.json
        symbol = data.get('symbol', '').upper()
        side = data.get('side', 'LONG')
        margin_usdt = float(data.get('quantity', 10))
        leverage = int(data.get('leverage', config.LEVERAGE))

        if not symbol.endswith('USDT'):
            symbol += 'USDT'

        api = BinanceFutures()
        ticker = api._safe_api_call(api.client.futures_ticker, symbol=symbol)
        if not ticker:
            return jsonify({"status": "error", "message": f"Símbolo {symbol} no válido"})

        price = float(ticker['lastPrice'])

        api.set_leverage_and_margin(symbol)

        notional = margin_usdt * leverage
        quantity = notional / price

        filters = api.get_symbol_filters(symbol)
        if filters:
            quantity = api.round_value(quantity, filters['stepSize'])
            if quantity < filters['minQty']:
                return jsonify({"status": "error", "message": "Cantidad muy pequeña"})

        order_side = SIDE_BUY if side == 'LONG' else SIDE_SELL
        order = api.place_market_order(symbol, order_side, quantity)

        if order and order.get('status') == 'FILLED':
            atr_estimate = price * 0.02

            if side == 'LONG':
                sl_price = price - (config.ATR_MULT_SL * atr_estimate)
                tp_price = price + (config.ATR_MULT_TP * atr_estimate)
            else:
                sl_price = price + (config.ATR_MULT_SL * atr_estimate)
                tp_price = price - (config.ATR_MULT_TP * atr_estimate)

            api.place_stop_orders(symbol, order_side, sl_price, tp_price)

            log.info(f"📱 Trade manual ejecutado: {side} {quantity} {symbol} @ {price:.4f}")
            return jsonify({"status": "success", "message": f"Trade ejecutado: {side} {quantity} {symbol}"})
        else:
            return jsonify({"status": "error", "message": "Error ejecutando la orden"})

    except Exception as e:
        log.error(f"Error en trade manual: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/close_position', methods=['POST'])
def close_position():
    try:
        data = request.json
        symbol = data.get('symbol')

        if not symbol:
            return jsonify({"status": "error", "message": "Símbolo requerido"})

        api = BinanceFutures()
        positions = api.get_positions()

        if symbol not in positions:
            return jsonify({"status": "error", "message": f"No hay posición abierta para {symbol}"})

        position = positions[symbol]
        position_amt = float(position['positionAmt'])

        if position_amt == 0:
            return jsonify({"status": "error", "message": f"Posición ya cerrada para {symbol}"})

        close_side = SIDE_SELL if position_amt > 0 else SIDE_BUY
        close_qty = abs(position_amt)

        order = api.place_market_order(symbol, close_side, close_qty)

        if order and order.get('status') == 'FILLED':
            try:
                api._safe_api_call(api.client.futures_cancel_all_open_orders, symbol=symbol)
            except:
                pass

            api.clear_configuration_cache(symbol)

            log.info(f"🔒 Posición cerrada manualmente: {symbol}")
            return jsonify({"status": "success", "message": f"Posición cerrada: {symbol}"})
        else:
            return jsonify({"status": "error", "message": "Error cerrando la posición"})

    except Exception as e:
        log.error(f"Error cerrando posición: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/balance')
def get_balance():
    try:
        api = BinanceFutures()
        balance = api.get_balance()
        account_info = api.get_account_info()

        with state_lock:
            app_state["balance"] = balance
            app_state["account_info"] = account_info

        return jsonify({
            "status": "success",
            "balance": balance,
            "account_info": account_info
        })

    except Exception as e:
        log.error(f"Error obteniendo balance: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/clear_cache', methods=['POST'])
def clear_cache():
    try:
        api = BinanceFutures()
        api.clear_configuration_cache()

        log.info("🧹 Cache de configuración limpiado manualmente")
        return jsonify({"status": "success", "message": "Cache limpiado correctamente"})

    except Exception as e:
        log.error(f"Error limpiando cache: {e}")
        return jsonify({"status": "error", "message": str(e)})

# -------------------- SOCKETIO EVENTS -------------------- #

@socketio.on('connect')
def handle_connect():
    log.info('🌐 Cliente web conectado')
    with state_lock:
        socketio.emit('status_update', app_state)

@socketio.on('disconnect')
def handle_disconnect():
    log.info('🌐 Cliente web desconectado')

# -------------------- FUNCIÓN PRINCIPAL -------------------- #

def main():
    """Función principal"""
    try:
        log.info("🚀 Iniciando servidor web del Bot de Binance Futures v7.3 (Configuración Inteligente)")

        try:
            api = BinanceFutures()
            initial_balance = api.get_balance()
            log.info(f"💰 Balance inicial: {initial_balance:.2f} USDT")
            log.info(f"🧠 Sistema de configuración inteligente activado")

            with state_lock:
                app_state["balance"] = initial_balance
                app_state["account_info"] = api.get_account_info()

        except Exception as e:
            log.error(f"❌ Error en conexión inicial: {e}")

        log.info("🌐 Servidor disponible en http://127.0.0.1:5000")
        socketio.run(
            app,
            debug=False,
            host='0.0.0.0',
            port=5000,
            use_reloader=False,
            log_output=False
        )

    except Exception as e:
        log.error(f"❌ Error crítico: {e}", exc_info=True)

if __name__ == '__main__':
    main()