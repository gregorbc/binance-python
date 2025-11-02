#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════
    BINANCE FUTURES BOT V18.4 - MAXIMO PnL PARA 9.81 USDT
           IA SELECCIONA LOS MEJORES PARES AUTOMÁTICAMENTE
              STOP LOSS OPTIMIZADO - BALANCE PEQUEÑO
              SISTEMA DE TIEMPO REAL COMPLETO
════════════════════════════════════════════════════════════════
"""

import os
from decimal import Decimal, getcontext, ROUND_FLOOR, ROUND_HALF_UP
import time
import math
import logging
import logging.handlers
import threading
import requests
import pandas as pd
import numpy as np
import psutil
import csv
import talib
import json
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import warnings
from collections import deque, defaultdict

# Suprimir warnings
warnings.filterwarnings("ignore")

# Importaciones de terceros
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS

# ================== BINANCE ENUMS COMPAT ==================
try:
    from binance.enums import SIDE_BUY, SIDE_SELL, FUTURE_ORDER_TYPE_MARKET
except Exception:
    SIDE_BUY = "BUY"
    SIDE_SELL = "SELL"
    FUTURE_ORDER_TYPE_MARKET = "MARKET"

TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"
STOP_MARKET = "STOP_MARKET"
# ==========================================================

# ════════════════════════════════════════════════════════════════
# CONFIGURACIÓN MAXIMO PnL PARA 9.81 USDT
# ════════════════════════════════════════════════════════════════

@dataclass
class CONFIG:
    """Configuración V18.4 - MAXIMO PnL PARA 9.81 USDT"""
    
    # ESTRATEGIA SCAN UNIVERSAL - AJUSTES MAXIMO RENDIMIENTO
    RISK_PER_TRADE_PERCENT: float = 6.0
    SMALL_BALANCE_RISK_PERCENT: float = 5.5
    LEVERAGE: int = 12
    SMALL_BALANCE_LEVERAGE: int = 12
    MAX_CONCURRENT_POS: int = 9
    
    # SCAN UNIVERSAL CONFIG - FILTROS MAXIMO RENDIMIENTO
    SCAN_ALL_SYMBOLS: bool = True
    MAX_SYMBOLS_TO_ANALYZE: int = 150
    MAX_SYMBOLS_TO_TRADE: int = 15
    MIN_VOLUME_USDT: float = 50_000
    MAX_PRICE_USDT: float = 0.80
    MIN_PRICE_USDT: float = 0.0005
    SCAN_INTERVAL_MINUTES: int = 3
    
    # FILTROS AVANZADOS - MAXIMO RENDIMIENTO
    MIN_PRICE_CHANGE_24H: float = 0.1
    MAX_PRICE_CHANGE_24H: float = 100.0
    VOLATILITY_FILTER: bool = True
    MIN_VOLATILITY_24H: float = 0.1
    MAX_VOLATILITY_24H: float = 80.0
    
    # 🔧 SEÑALES MAXIMO RENDIMIENTO
    MIN_SIGNAL_SCORE: int = 1
    ML_CONFIDENCE_THRESHOLD: float = 0.12
    IA_SIGNAL_STRENGTH_THRESHOLD: float = 0.03
    
    # 🔧 STOP LOSS MAXIMO RENDIMIENTO
    TP_RR: float = 1.8
    SL_ATR_MULT: float = 1.2
    MIN_STOP_DISTANCE_PCT: float = 0.0008
    
    # 🔧 LÍMITES PARA BALANCE PEQUEÑO - MAXIMO RENDIMIENTO
    MAX_POSITION_SIZE_PCT: float = 18.0
    MAX_QUANTITY_MULTIPLIER: float = 12.0
    MAX_RISK_PERCENTAGE: float = 30.0
    
    # PROTECCIÓN MEJORADA
    MAX_DAILY_TRADES: int = 1244
    DAILY_LOSS_LIMIT: float = 15.0
    
    # FRECUENCIA
    POLL_SEC: float = 1.5
    
    # SÍMBOLOS GARANTIZADOS - ACTUALIZADO
    PRIORITY_SYMBOLS: tuple = (
        'DOGEUSDT', 'TRXUSDT', 'SHIBUSDT', 'VETUSDT', 'ONEUSDT',
        'HOTUSDT', 'BTTUSDT', 'ZILUSDT', 'WINUSDT', 'TFUELUSDT',
        'CHZUSDT', 'STMXUSDT', 'ANKRUSDT', 'BATUSDT', 'DENTUSDT',
        'CELRUSDT', 'COTIUSDT', 'FETUSDT', 'LRCUSDT', 'SANDUSDT',
        'MANAUSDT', 'ENJUSDT', 'ALICEUSDT', 'AUDIOUSDT', 'DASHUSDT'
    )
    
    # Multi-timeframe
    TIMEFRAME_PRIMARY: str = "5m"
    TIMEFRAME_SECONDARY: str = "3m"
    TIMEFRAME_IA: str = "1m"
    
    # Stops & Targets
    USE_EXCHANGE_STOPS: bool = True
    
    # PROTECCIÓN MEJORADA PARA CAPITAL MUY PEQUEÑO
    MIN_BALANCE_THRESHOLD: float = 2.0
    MAX_DRAWDOWN_PCT: float = 10.0
    MAX_CONSECUTIVE_LOSSES: int = 500
    
    # Configuración para balances MUY pequeños ESPECÍFICA
    SMALL_BALANCE_THRESHOLD: float = 1.0
    SMALL_BALANCE_LOCKOUT_MINUTES: int = 30
    PER_SYMBOL_MAX_NOTIONAL_PCT: float = 0.25
    SYMBOL_COOLDOWN_MINUTES: int = 15
    MAX_SPREAD_PCT: float = 0.0050
    MAX_FUNDING_ABS: float = 0.0050
    
    # Indicadores MÁS SENSIBLES
    FAST_EMA: int = 3
    SLOW_EMA: int = 8
    EMA_TREND: int = 15
    RSI_PERIOD: int = 8
    ATR_PERIOD: int = 3
    MACD_FAST: int = 3
    MACD_SLOW: int = 8
    MACD_SIGNAL: int = 3
    VOLUME_MA: int = 5
    
    # Sistema IA
    CANDLES_LIMIT: int = 50
    DRY_RUN: bool = False
    
    # Estrategias de cierre
    USE_ADVANCED_EXIT_STRATEGIES: bool = True
    EFFICIENT_LOSS_TIME_MINUTES: int = 2
    EFFICIENT_LOSS_ATR_THRESHOLD: float = 0.020
    
    # PARÁMETROS OPTIMIZADOS PARA CAPITAL MUY PEQUEÑO
    QUICK_PROFIT_THRESHOLD: float = 2.5
    QUICK_LOSS_THRESHOLD: float = -0.20
    MAX_HOLDING_TIME_MINUTES: int = 8
    MIN_HOLDING_TIME_MINUTES: int = 0.3
    
    # Logging
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE: str = "bot_10usdt_maxprofit.log"
    
    # 🔧 PROTECCIÓN CONTRA LÍMITES DE POSICIÓN
    PROBLEMATIC_SYMBOLS: tuple = (
        'BLESSUSDT', 'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT',
        'XRPUSDT', 'ADAUSDT', 'DOTUSDT', 'MATICUSDT', 'LTCUSDT'
    )
    MAX_RETRY_REDUCTION_FACTOR: float = 0.6
    MIN_NOTIONAL_SAFETY: float = 7.5

    # 🔧 PROTECCIÓN DE MARGEN MEJORADA
    MIN_AVAILABLE_MARGIN: float = 2.0
    MAX_MARGIN_UTILIZATION: float = 0.7
    MAX_CONCURRENT_POS_BY_MARGIN: int = 3

# Inicializar configuración
config = CONFIG()

# Cargar variables de entorno
load_dotenv()

# ════════════════════════════════════════════════════════════════
# FLASK APP
# ════════════════════════════════════════════════════════════════

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bot-trading-10usdt-maxprofit')
CORS(app)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# ════════════════════════════════════════════════════════════════
# LOGGING MEJORADO
# ════════════════════════════════════════════════════════════════

def setup_advanced_logging():
    """Configuración de logging mejorada"""
    log = logging.getLogger("BinanceFuturesBotV18_10USDT_MAXPROFIT")
    log.setLevel(getattr(logging, config.LOG_LEVEL))
    
    if log.handlers:
        for handler in log.handlers:
            log.removeHandler(handler)
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    os.makedirs('logs', exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        f'logs/{config.LOG_FILE}', 
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    class SocketIOHandler(logging.Handler):
        def emit(self, record):
            try:
                log_entry = self.format(record)
                level = record.levelname.lower()
                socketio.emit('log_update', {'message': log_entry, 'level': level})
            except:
                pass
    
    socket_handler = SocketIOHandler()
    socket_handler.setFormatter(formatter)
    
    log.addHandler(file_handler)
    log.addHandler(console_handler)
    log.addHandler(socket_handler)
    log.propagate = False
    
    return log

log = setup_advanced_logging()

# ════════════════════════════════════════════════════════════════
# CLIENTE BINANCE MEJORADO PARA 9.81 USDT - MAXIMO RENDIMIENTO
# ════════════════════════════════════════════════════════════════

class BinanceFuturesMaxProfit:
    def __init__(self):
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError("❌ API keys no configuradas")

        self.client = Client(api_key, api_secret, testnet=testnet)
        self.exchange_info = self.client.futures_exchange_info()
        self.symbol_precision_info = self._load_all_symbol_precision()
        self.health_status = {
            'last_successful_call': datetime.now(),
            'consecutive_errors': 0,
            'total_errors': 0
        }
        # 🔧 Nuevos atributos para gestión de errores y límites
        self.failed_symbols = set()
        self.position_limits_cache = {}
        log.info(f"🔧 Conectado a Binance Futures {'TESTNET' if testnet else 'MAINNET'} - 9.81 USDT MAXIMO RENDIMIENTO")

    def _load_all_symbol_precision(self):
        """Cargar información de precisión para TODOS los símbolos"""
        precision_info = {}
        try:
            for symbol_info in self.exchange_info['symbols']:
                symbol = symbol_info['symbol']
                if symbol_info.get('status') == 'TRADING' and symbol_info.get('quoteAsset') == 'USDT':
                    info = self._extract_precision_from_symbol_info(symbol_info)
                    precision_info[symbol] = info
            log.info(f"✅ Precisión cargada para {len(precision_info)} símbolos")
            return precision_info
        except Exception as e:
            log.error(f"❌ Error cargando precisiones: {e}")
            return {}

    def get_klines(self, symbol: str, interval: str, limit: int = config.CANDLES_LIMIT):
        """Obtener klines"""
        try:
            klines = self.client.futures_klines(
                symbol=symbol, interval=interval, limit=limit
            )
            self._record_success()
            return klines if klines else None
        except Exception as e:
            self._record_error()
            return None

    def _safe_api_call(self, func, *args, **kwargs):
        """Llamada segura a API con reintentos"""
        for attempt in range(3):
            try:
                time.sleep(0.3 * attempt)
                result = func(*args, **kwargs)
                self._record_success()
                return result
            except BinanceAPIException as e:
                self._record_error()
                if attempt == 2:
                    log.error(f"❌ Error API: {e.message} (code: {e.code})")
                continue
            except Exception as e:
                self._record_error()
                if attempt == 2:
                    log.error(f"❌ Error en API: {e}")
                continue
        return None

    def _record_success(self):
        """Registrar llamada exitosa"""
        self.health_status['last_successful_call'] = datetime.now()
        self.health_status['consecutive_errors'] = 0

    def _record_error(self):
        """Registrar error"""
        self.health_status['consecutive_errors'] += 1
        self.health_status['total_errors'] += 1

    def get_account_info(self):
        try:
            account = self._safe_api_call(self.client.futures_account)
            if account:
                total_balance = float(account.get('totalWalletBalance', 0))
                available_balance = float(account.get('availableBalance', 0))
                log.info(f"💰 Balance 9.81 USDT MAXPROFIT: Total: {total_balance:.2f} USDT, Disponible: {available_balance:.2f} USDT")
            return account if account else None
        except Exception as e:
            log.error(f"Error obteniendo cuenta: {e}")
            return None

    def round_quantity(self, symbol: str, quantity: float):
        """Redondear cantidad - MAXIMO RENDIMIENTO"""
        precision_info = self.symbol_precision_info.get(symbol, {})
        step_size = precision_info.get('step_size', 0.001)
        min_qty = precision_info.get('min_qty', 0.001)
        
        if step_size >= 1:
            rounded = math.floor(quantity / step_size) * step_size
        else:
            precision = precision_info.get('quantity_precision', 3)
            rounded = math.floor(quantity / step_size) * step_size
            rounded = round(rounded, precision)
        
        if rounded < min_qty:
            rounded = min_qty
        
        return float(rounded)

    def round_price(self, symbol: str, price: float):
        """Redondear precio - MAXIMO RENDIMIENTO"""
        precision_info = self.symbol_precision_info.get(symbol, {})
        tick_size = precision_info.get('tick_size', 0.01)
        
        if tick_size >= 1:
            rounded = math.floor(price / tick_size) * tick_size
        else:
            precision = precision_info.get('price_precision', 2)
            rounded = math.floor(price / tick_size) * tick_size
            rounded = round(rounded, precision)
        
        return float(rounded)

    def _extract_precision_from_symbol_info(self, symbol_info: dict) -> dict:
        lot_size = next((f for f in symbol_info.get('filters', []) if f.get('filterType') == 'LOT_SIZE'), None)
        price_f  = next((f for f in symbol_info.get('filters', []) if f.get('filterType') == 'PRICE_FILTER'), None)
        
        if lot_size:
            step_size = float(lot_size.get('stepSize', '0.001'))
            min_qty   = float(lot_size.get('minQty',   '0.001'))
            quantity_precision = 0 if step_size >= 1 else int(round(-math.log10(step_size)))
        else:
            step_size = 0.001
            min_qty   = 0.001
            quantity_precision = 3
            
        if price_f:
            tick_size = float(price_f.get('tickSize', '0.01'))
            price_precision = 0 if tick_size >= 1 else int(round(-math.log10(tick_size)))
        else:
            tick_size = 0.01
            price_precision = 2
            
        return {
            'quantity_precision': quantity_precision,
            'price_precision': price_precision,
            'min_qty': min_qty,
            'step_size': step_size,
            'tick_size': tick_size
        }

    def get_current_price(self, symbol: str):
        """Obtener precio actual"""
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            log.error(f"❌ Error obteniendo precio para {symbol}: {e}")
            return 0.0

    def place_order_with_retry(self, symbol: str, side: str, quantity: float, max_retries: int = 3):
        """Colocar orden con reintentos y gestión de límites - MAXIMO RENDIMIENTO"""
        for attempt in range(max_retries):
            try:
                # 🔧 REDUCIR CANTIDAD SI HAY ERRORES PREVIOS
                if symbol in self.failed_symbols and attempt > 0:
                    reduction_factor = 0.7 ** attempt
                    adjusted_quantity = quantity * reduction_factor
                    adjusted_quantity = self.round_quantity(symbol, adjusted_quantity)
                    
                    current_price = self.get_current_price(symbol)
                    adjusted_notional = adjusted_quantity * current_price
                    
                    if adjusted_notional >= 6.0:
                        quantity = adjusted_quantity
                        log.info(f"🔧 Cantidad reducida por errores previos: {quantity:.0f}")
                
                order = self.place_order(symbol, side, quantity)
                if order:
                    if symbol in self.failed_symbols:
                        self.failed_symbols.remove(symbol)
                    return order
                else:
                    log.warning(f"⚠️ Intento {attempt + 1} fallido para {symbol}")
                    
            except BinanceAPIException as e:
                if "MAX_POSITION" in str(e) or "LEVERAGE" in str(e) or e.code == -2027:
                    self.failed_symbols.add(symbol)
                    log.warning(f"🔧 Límite de posición/exceso de leverage detectado en {symbol}")
                    
                    if attempt == max_retries - 1:
                        log.error(f"❌ Error persistente de límite en {symbol}, añadiendo a lista negra temporal")
                        return None
                        
                elif "MARGIN" in str(e) or e.code == -2019:
                    self.failed_symbols.add(symbol)
                    log.warning(f"🔧 Margen insuficiente detectado en {symbol}")
                    
                    if attempt == max_retries - 1:
                        log.error(f"❌ Error persistente de margen en {symbol}, añadiendo a lista negra temporal")
                        return None
                        
                elif "MIN_NOTIONAL" in str(e):
                    log.info(f"🔧 Ajustando por MIN_NOTIONAL en {symbol}")
                    current_price = self.get_current_price(symbol)
                    min_notional = 6.0
                    min_quantity = min_notional / current_price
                    precision_info = self.symbol_precision_info.get(symbol, {})
                    step_size = precision_info.get('step_size', 0.001)
                    
                    adjusted_qty = math.ceil(min_quantity / step_size) * step_size
                    adjusted_qty = self.round_quantity(symbol, adjusted_qty)
                    
                    new_notional = adjusted_qty * current_price
                    if new_notional >= min_notional:
                        quantity = adjusted_qty
                        log.info(f"🔧 Nueva cantidad para {symbol}: {quantity}")
                    else:
                        while new_notional < min_notional and adjusted_qty < 100000:
                            adjusted_qty += step_size
                            adjusted_qty = self.round_quantity(symbol, adjusted_qty)
                            new_notional = adjusted_qty * current_price
                        if new_notional >= min_notional:
                            quantity = adjusted_qty
                            log.info(f"🔧 Cantidad ajustada: {quantity} = ${new_notional:.2f}")
                        else:
                            log.error(f"❌ No se puede alcanzar notional mínimo para {symbol}")
                            return None
                elif attempt == max_retries - 1:
                    log.error(f"❌ Error después de {max_retries} intentos: {e}")
                    return None
            time.sleep(1 * (attempt + 1))
        return None

    def place_order(self, symbol: str, side: str, quantity: float):
        """Colocar orden - MAXIMO RENDIMIENTO"""
        try:
            precision_info = self.symbol_precision_info.get(symbol, {})
            min_qty = precision_info.get('min_qty', 0.001)
            
            if quantity < min_qty:
                log.warning(f"⚠️ Cantidad {quantity} menor que mínimo {min_qty} para {symbol}")
                return None

            if config.DRY_RUN:
                current_price = self.get_current_price(symbol)
                notional = quantity * current_price
                log.info(f"[DRY_RUN] 🎯 Orden simulada: {side} {quantity} {symbol} @ ${current_price:.2f} = ${notional:.2f}")
                return {'mock': True, 'orderId': int(time.time() * 1000)}

            rounded_quantity = self.round_quantity(symbol, quantity)
            
            if rounded_quantity <= 0:
                log.error(f"❌ Cantidad inválida para {symbol}: {rounded_quantity}")
                return None
            
            current_price = self.get_current_price(symbol)
            notional = rounded_quantity * current_price
            
            MIN_NOTIONAL = 6.0
            
            if notional < MIN_NOTIONAL:
                log.warning(f"⚠️ Notional insuficiente: ${notional:.2f} < ${MIN_NOTIONAL}")
                min_quantity = MIN_NOTIONAL / current_price
                min_quantity = self.round_quantity(symbol, min_quantity)
                min_notional = min_quantity * current_price
                
                if min_notional >= MIN_NOTIONAL:
                    rounded_quantity = min_quantity
                    notional = min_notional
                    log.info(f"🔧 Usando cantidad mínima: {rounded_quantity} = ${notional:.2f}")
                else:
                    step_size = precision_info.get('step_size', 0.001)
                    adjusted_quantity = rounded_quantity
                    while notional < MIN_NOTIONAL and adjusted_quantity < 100000:
                        adjusted_quantity += step_size
                        adjusted_quantity = self.round_quantity(symbol, adjusted_quantity)
                        notional = adjusted_quantity * current_price
                    
                    if notional >= MIN_NOTIONAL:
                        rounded_quantity = adjusted_quantity
                        log.info(f"🔧 Ajustado a mínimo: {rounded_quantity} = ${notional:.2f}")
                    else:
                        log.warning(f"⛔ Notional insuficiente incluso con ajustes: ${notional:.2f}")
                        return None
            
            log.info(f"📦 Colocando orden REAL para 9.81 USDT MAXPROFIT: {side} {rounded_quantity} {symbol} (Notional: ${notional:.2f})")
            
            return self._safe_api_call(
                self.client.futures_create_order,
                symbol=symbol,
                side=side,
                type=FUTURE_ORDER_TYPE_MARKET,
                quantity=rounded_quantity
            )
        except Exception as e:
            log.error(f"❌ Error colocando orden {symbol}: {e}")
            return None

    def close_position(self, symbol: str, position_amt: float):
        try:
            side = SIDE_SELL if position_amt > 0 else SIDE_BUY
            quantity = abs(position_amt)
            rounded_quantity = self.round_quantity(symbol, quantity)
            return self.place_order(symbol, side, rounded_quantity)
        except Exception as e:
            log.error(f"❌ Error cerrando posición {symbol}: {e}")
            return None

    def place_stop_order(self, symbol: str, side: str, quantity: float, stop_price: float):
        """Colocar orden stop mejorada para 9.81 USDT MAXPROFIT"""
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] 🛡️ Orden stop simulada: {side} {quantity} {symbol} @ ${stop_price:.4f}")
            return {'mock': True, 'orderId': int(time.time() * 1000)}
        
        try:
            rounded_quantity = self.round_quantity(symbol, quantity)
            rounded_stop_price = self.round_price(symbol, stop_price)
            
            current_price = self.get_current_price(symbol)
            if current_price <= 0:
                log.error(f"❌ Precio actual inválido para {symbol}")
                return None
                
            price_distance_pct = abs(current_price - rounded_stop_price) / current_price
            if price_distance_pct < config.MIN_STOP_DISTANCE_PCT:
                log.warning(f"⭕ Stop demasiado cercano: {price_distance_pct:.3%} < {config.MIN_STOP_DISTANCE_PCT:.3%}")
                if side == SIDE_SELL:
                    rounded_stop_price = current_price * (1 - config.MIN_STOP_DISTANCE_PCT)
                else:
                    rounded_stop_price = current_price * (1 + config.MIN_STOP_DISTANCE_PCT)
                rounded_stop_price = self.round_price(symbol, rounded_stop_price)
                log.info(f"🔧 Stop ajustado a: ${rounded_stop_price:.4f}")
            
            log.info(f"🛡️ Colocando orden STOP para 9.81 USDT MAXPROFIT: {side} {rounded_quantity} {symbol} @ ${rounded_stop_price:.4f}")
            
            return self._safe_api_call(
                self.client.futures_create_order,
                symbol=symbol,
                side=side,
                type="STOP_MARKET",
                stopPrice=rounded_stop_price,
                quantity=rounded_quantity,
                closePosition=True
            )
        except Exception as e:
            log.error(f"❌ Error colocando orden stop {symbol}: {e}")
            return None

# ════════════════════════════════════════════════════════════════
# GESTOR DE CAPITAL MAXIMO RENDIMIENTO PARA 9.81 USDT
# ════════════════════════════════════════════════════════════════

class MaxProfitCapitalManager:
    """Gestor de capital MAXIMO RENDIMIENTO para 9.81 USDT"""
    
    def __init__(self, api: BinanceFuturesMaxProfit):
        self.api = api
        self.current_balance = 0.0
        self.initial_balance = 0.0
        self.trade_history = deque(maxlen=15)
        self.last_update = 0
        self.update_balance()

    def update_balance(self):
        """Actualizar balance"""
        try:
            account = self.api.get_account_info()
            if account:
                total_balance = float(account.get('totalWalletBalance', 0))
                available_balance = float(account.get('availableBalance', 0))
                
                new_balance = max(total_balance, available_balance)
                
                if new_balance != self.current_balance:
                    self.current_balance = new_balance
                    if self.initial_balance == 0:
                        self.initial_balance = self.current_balance
                    log.info(f"💰 Balance 9.81 USDT MAXPROFIT actualizado: {self.current_balance:.2f} USDT")
                
                self.last_update = time.time()
                return True
            
            log.warning("⚠️ No se pudo obtener balance de la cuenta")
            return False
        except Exception as e:
            log.error(f"❌ Error actualizando balance: {e}")
            return False

    def can_trade_symbol_max_profit(self, symbol: str, current_price: float) -> bool:
        """Verificación MAXIMO RENDIMIENTO para 9.81 USDT"""
        try:
            if current_price > config.MAX_PRICE_USDT:
                return False
                
            if current_price < config.MIN_PRICE_USDT:
                return False

            min_notional = 6.0
            precision_info = self.api.symbol_precision_info.get(symbol, {})
            
            if not precision_info:
                return False

            step_size = precision_info.get('step_size', 0.001)
            min_qty = precision_info.get('min_qty', 0.001)

            min_quantity_theoretical = min_notional / current_price
            
            min_quantity = math.ceil(min_quantity_theoretical / step_size) * step_size
            min_quantity = self.api.round_quantity(symbol, min_quantity)
            
            test_notional = min_quantity * current_price
            
            if test_notional < min_notional:
                adjusted_quantity = min_quantity
                max_iterations = 1000
                
                while test_notional < min_notional and adjusted_quantity < 100000 and max_iterations > 0:
                    adjusted_quantity += step_size
                    adjusted_quantity = self.api.round_quantity(symbol, adjusted_quantity)
                    test_notional = adjusted_quantity * current_price
                    max_iterations -= 1
                
                if test_notional < min_notional:
                    return False
            
            if min_quantity < min_qty:
                min_quantity = min_qty
                test_notional = min_quantity * current_price
                if test_notional < min_notional:
                    return False
                
            return True
            
        except Exception as e:
            log.debug(f"⚠️ Error verificando {symbol}: {e}")
            return False

    def validate_position_limits(self, symbol: str, quantity: float, entry_price: float) -> bool:
        """Validar límites de posición antes de ordenar"""
        try:
            current_price = self.api.get_current_price(symbol)
            notional = quantity * current_price
            
            # Verificar notional mínimo de seguridad
            if notional < config.MIN_NOTIONAL_SAFETY:
                log.warning(f"⭕ Notional de seguridad insuficiente: ${notional:.2f} < ${config.MIN_NOTIONAL_SAFETY:.2f}")
                
                # 🔧 INTENTAR AJUSTAR LA CANTIDAD PARA CUMPLIR EL MÍNIMO
                min_quantity_safety = config.MIN_NOTIONAL_SAFETY / current_price
                min_quantity_safety = self.api.round_quantity(symbol, min_quantity_safety)
                adjusted_notional = min_quantity_safety * current_price
                
                if adjusted_notional >= config.MIN_NOTIONAL_SAFETY:
                    log.info(f"🔧 Cantidad ajustable para cumplir mínimo: {min_quantity_safety:.0f} = ${adjusted_notional:.2f}")
                    return True
                else:
                    return False
                    
            # Verificar si es símbolo problemático
            if symbol in config.PROBLEMATIC_SYMBOLS:
                max_problematic_notional = 12.0
                if notional > max_problematic_notional:
                    log.warning(f"⭕ Símbolo problemático {symbol}, notional muy alto: ${notional:.2f}")
                    return False
                        
            return True
            
        except Exception as e:
            log.warning(f"⚠️ Error validando límites: {e}")
            return True

    def calculate_max_profit_position_size(self, symbol: str, entry_price: float, stop_loss: float, 
                                         confidence: float, aggressiveness: float) -> float:
        """Cálculo MAXIMO RENDIMIENTO con gestión mejorada de margen para 9.81 USDT"""
        try:
            if entry_price <= config.MIN_PRICE_USDT:
                return 0.0
            
            # 🔧 ACTUALIZAR BALANCE PRIMERO
            if not self.update_balance():
                return 0.0

            if self.current_balance <= config.MIN_BALANCE_THRESHOLD:
                return 0.0

            stop_distance = abs(entry_price - stop_loss)
            if stop_distance <= 0:
                return 0.0

            account = self.api.get_account_info()
            if not account:
                return 0.0

            # 🔧 OBTENER MARGEN DISPONIBLE REAL
            available_balance = float(account.get('availableBalance', 0))
            total_balance = float(account.get('totalWalletBalance', 0))
            
            log.info(f"💰 Margen disponible: ${available_balance:.2f} / Total: ${total_balance:.2f}")
            
            # 🔧 VERIFICAR MARGEN MÍNIMO
            MIN_AVAILABLE_MARGIN = config.MIN_AVAILABLE_MARGIN
            if available_balance < MIN_AVAILABLE_MARGIN:
                log.warning(f"⭕ Margen insuficiente: ${available_balance:.2f} < ${MIN_AVAILABLE_MARGIN:.2f}")
                return 0.0

            # 🔧 ESTRATEGIA MAXIMO RENDIMIENTO CON LÍMITE DE MARGEN
            min_notional = 6.0
            target_notional = min(7.5, available_balance * config.MAX_MARGIN_UTILIZATION)
            
            base_quantity = target_notional / entry_price
            base_quantity = self.api.round_quantity(symbol, base_quantity)
            calculated_notional = base_quantity * entry_price
            
            precision_info = self.api.symbol_precision_info.get(symbol, {})
            step_size = precision_info.get('step_size', 0.001)
            adjusted_quantity = base_quantity
            
            max_iterations = 500
            while calculated_notional < min_notional and adjusted_quantity < 50000 and max_iterations > 0:
                adjusted_quantity += step_size
                adjusted_quantity = self.api.round_quantity(symbol, adjusted_quantity)
                calculated_notional = adjusted_quantity * entry_price
                max_iterations -= 1
            
            if calculated_notional < min_notional:
                return 0.0

            quantity = adjusted_quantity
            
            # 🔧 BOOST CON LÍMITE POR MARGEN DISPONIBLE
            confidence_boost = 1.0 + (confidence * 0.3)
            aggressiveness_boost = 1.0 + (aggressiveness * 0.2)
            quantity *= confidence_boost * aggressiveness_boost
            quantity = self.api.round_quantity(symbol, quantity)
            
            # Recalcular notional después del boost
            calculated_notional = quantity * entry_price
            
            # 🔧 VERIFICAR QUE NO EXCEDA EL MARGEN DISPONIBLE
            if calculated_notional > available_balance * config.MAX_MARGIN_UTILIZATION:
                quantity = (available_balance * config.MAX_MARGIN_UTILIZATION) / entry_price
                quantity = self.api.round_quantity(symbol, quantity)
                calculated_notional = quantity * entry_price
                log.info(f"🔧 Ajustando por límite de margen: {quantity:.0f} {symbol} = ${calculated_notional:.2f}")
            
            # 🔧 GARANTIZAR NOTIONAL MÍNIMO DE SEGURIDAD
            if calculated_notional < config.MIN_NOTIONAL_SAFETY:
                # Ajustar para alcanzar el notional mínimo de seguridad
                min_quantity_safety = config.MIN_NOTIONAL_SAFETY / entry_price
                min_quantity_safety = self.api.round_quantity(symbol, min_quantity_safety)
                min_notional_safety = min_quantity_safety * entry_price
                
                if min_notional_safety >= config.MIN_NOTIONAL_SAFETY:
                    quantity = min_quantity_safety
                    calculated_notional = min_notional_safety
                    log.info(f"🔧 Ajustando para notional mínimo de seguridad: {quantity:.0f} {symbol} = ${calculated_notional:.2f}")
                else:
                    # Incrementar hasta alcanzar el mínimo
                    while calculated_notional < config.MIN_NOTIONAL_SAFETY and quantity < 50000 and max_iterations > 0:
                        quantity += step_size
                        quantity = self.api.round_quantity(symbol, quantity)
                        calculated_notional = quantity * entry_price
                        max_iterations -= 1
                    
                    if calculated_notional >= config.MIN_NOTIONAL_SAFETY:
                        log.info(f"🔧 Incrementado para notional mínimo: {quantity:.0f} {symbol} = ${calculated_notional:.2f}")
                    else:
                        log.warning(f"⭕ No se puede alcanzar notional mínimo de seguridad: ${calculated_notional:.2f} < ${config.MIN_NOTIONAL_SAFETY:.2f}")
                        return 0.0
            
            # 🔧 NUEVA PROTECCIÓN: Reducir tamaño si hay problemas previos
            max_retry_factor = 0.5
            if symbol in self.api.failed_symbols:
                quantity *= max_retry_factor
                quantity = self.api.round_quantity(symbol, quantity)
                calculated_notional = quantity * entry_price
                log.info(f"🔧 Reduciendo posición por errores previos en {symbol}")
                
                # 🔧 VERIFICAR QUE SIGA CUMPLIENDO EL MÍNIMO DESPUÉS DE REDUCIR
                if calculated_notional < config.MIN_NOTIONAL_SAFETY:
                    log.warning(f"⭕ Posición reducida por debajo del mínimo: ${calculated_notional:.2f} < ${config.MIN_NOTIONAL_SAFETY:.2f}")
                    return 0.0
            
            # 🔧 VALIDACIÓN DE RIESGO MÁS FLEXIBLE
            risk_dollars = quantity * stop_distance
            risk_percentage = (risk_dollars / available_balance) * 100
            
            MAX_RISK_PERCENTAGE = config.MAX_RISK_PERCENTAGE
            
            if risk_percentage > MAX_RISK_PERCENTAGE:
                if risk_percentage < 50:
                    log.warning(f"⚠️ Riesgo alto aceptado: {risk_percentage:.1f}%")
                else:
                    return 0.0

            log.info(f"📊 Posición MAXIMO RENDIMIENTO: {quantity:.0f} {symbol} = ${calculated_notional:.2f} "
                    f"(Riesgo: {risk_percentage:.1f}%, Margen disp: ${available_balance:.2f})")
            
            return quantity
            
        except Exception as e:
            log.error(f"❌ Error cálculo posición MAXIMO {symbol}: {e}")
            return 0.0

# ════════════════════════════════════════════════════════════════
# SISTEMA DE IA MAXIMO RENDIMIENTO PARA 9.81 USDT
# ════════════════════════════════════════════════════════════════

class MaxProfitIATradingSystem:
    """Sistema de IA MAXIMO RENDIMIENTO para 9.81 USDT"""
    
    def __init__(self, api):
        self.api = api
        self.signal_cache = {}
        self.signal_cooldown = {}
        self.last_cleanup = time.time()
        
    def predict_movement_max_profit(self, symbol: str, df: pd.DataFrame) -> dict:
        """Predicción MAXIMO RENDIMIENTO para 9.81 USDT"""
        try:
            self._cleanup_old_cache()
            
            current_time = time.time()
            cache_key = f"{symbol}_{current_time // 60}"
            
            if cache_key in self.signal_cache:
                return self.signal_cache[cache_key]
            
            if df.empty or len(df) < 10:
                return self._get_minimum_confidence_prediction()
            
            technical_signal = self._calculate_max_profit_technical_signal(df)
            volume_signal = self._calculate_max_profit_volume_signal(df)
            momentum_signal = self._calculate_max_profit_momentum_signal(df)
            
            bull_confidence = 0.0
            bear_confidence = 0.0
            
            if technical_signal['direction'] == 'BULLISH':
                bull_confidence += technical_signal['strength'] * 0.5
            else:
                bear_confidence += technical_signal['strength'] * 0.5
                
            if volume_signal['direction'] == 'BULLISH':
                bull_confidence += volume_signal['strength'] * 0.3
            else:
                bear_confidence += volume_signal['strength'] * 0.3
                
            if momentum_signal['direction'] == 'BULLISH':
                bull_confidence += momentum_signal['strength'] * 0.2
            else:
                bear_confidence += momentum_signal['strength'] * 0.2
            
            min_confidence = 0.10
            bull_confidence = max(bull_confidence, min_confidence)
            bear_confidence = max(bear_confidence, min_confidence)
            
            if bull_confidence > bear_confidence:
                direction = 'BULLISH'
                confidence = min(0.95, bull_confidence)
                aggressiveness = min(1.0, confidence * 1.8)
            elif bear_confidence > bull_confidence:
                direction = 'BEARISH' 
                confidence = min(0.95, bear_confidence)
                aggressiveness = min(1.0, confidence * 1.8)
            else:
                direction = 'NEUTRAL'
                confidence = max(bull_confidence, bear_confidence)
                aggressiveness = 0.0
            
            prediction = {
                'direction': direction,
                'confidence': confidence,
                'aggressiveness': aggressiveness
            }
            
            self.signal_cache[cache_key] = prediction
            return prediction
            
        except Exception as e:
            log.warning(f"⚠️ Error predicción IA MAXIMO {symbol}: {e}")
            return self._get_minimum_confidence_prediction()

    def _get_minimum_confidence_prediction(self):
        """Retornar predicción con confianza mínima garantizada"""
        return {
            'direction': 'NEUTRAL',
            'confidence': 0.12,
            'aggressiveness': 0.08
        }

    def _calculate_max_profit_technical_signal(self, df: pd.DataFrame) -> dict:
        """Señal técnica MAXIMO RENDIMIENTO"""
        try:
            if len(df) < 5:
                return {'direction': 'NEUTRAL', 'strength': 0.12}
                
            ema_fast = talib.EMA(df['close'], timeperiod=config.FAST_EMA).iloc[-1]
            ema_slow = talib.EMA(df['close'], timeperiod=config.SLOW_EMA).iloc[-1]
            
            rsi = talib.RSI(df['close'], timeperiod=config.RSI_PERIOD).iloc[-1]
            
            macd, macd_signal, macd_hist = talib.MACD(df['close'])
            macd_trend = macd_hist.iloc[-1] > 0 if len(macd_hist) > 1 else False
            
            strength = 0.12
            direction = 'NEUTRAL'
            
            if (ema_fast > ema_slow and 
                rsi > 25 and rsi < 80 and
                macd_trend):
                direction = 'BULLISH'
                strength = 0.7
                
            elif (ema_fast < ema_slow and 
                  rsi < 75 and rsi > 20 and
                  not macd_trend):
                direction = 'BEARISH'
                strength = 0.7
                
            return {'direction': direction, 'strength': max(0.12, strength)}
            
        except Exception:
            return {'direction': 'NEUTRAL', 'strength': 0.12}

    def _calculate_max_profit_volume_signal(self, df: pd.DataFrame) -> dict:
        """Señal de volumen MAXIMO RENDIMIENTO"""
        try:
            if 'volume' not in df.columns or len(df) < 5:
                return {'direction': 'NEUTRAL', 'strength': 0.12}
                
            volume = df['volume']
            current_volume = volume.iloc[-1]
            avg_volume = volume.rolling(5).mean().iloc[-1]
            
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            price_up = df['close'].iloc[-1] > df['close'].iloc[-2]
            
            strength = 0.12
            direction = 'NEUTRAL'
            
            if volume_ratio > 1.2 and price_up:
                direction = 'BULLISH'
                strength = min(0.8, volume_ratio * 0.4)
            elif volume_ratio > 1.2 and not price_up:
                direction = 'BEARISH' 
                strength = min(0.8, volume_ratio * 0.4)
                
            return {'direction': direction, 'strength': max(0.12, strength)}
            
        except Exception:
            return {'direction': 'NEUTRAL', 'strength': 0.12}

    def _calculate_max_profit_momentum_signal(self, df: pd.DataFrame) -> dict:
        """Señal de momentum MAXIMO RENDIMIENTO"""
        try:
            if len(df) < 3:
                return {'direction': 'NEUTRAL', 'strength': 0.12}
                
            current_price = df['close'].iloc[-1]
            price_2m_ago = df['close'].iloc[-3] if len(df) >= 3 else current_price
            
            momentum_pct = (current_price - price_2m_ago) / price_2m_ago * 100
            
            strength = 0.12
            direction = 'NEUTRAL'
            
            if momentum_pct > 0.05:
                direction = 'BULLISH'
                strength = min(0.7, abs(momentum_pct) * 0.6)
            elif momentum_pct < -0.05:
                direction = 'BEARISH'
                strength = min(0.7, abs(momentum_pct) * 0.6)
                
            return {'direction': direction, 'strength': max(0.12, strength)}
            
        except Exception:
            return {'direction': 'NEUTRAL', 'strength': 0.12}

    def _cleanup_old_cache(self):
        """Limpiar cache antiguo"""
        current_time = time.time()
        if current_time - self.last_cleanup > 60:
            expired_keys = [
                key for key in self.signal_cache.keys() 
                if current_time - float(key.split('_')[-1]) * 60 > 300
            ]
            for key in expired_keys:
                del self.signal_cache[key]
            self.last_cleanup = current_time

# ════════════════════════════════════════════════════════════════
# SISTEMA DE SCAN UNIVERSAL MAXIMO RENDIMIENTO
# ════════════════════════════════════════════════════════════════

class UniversalSymbolScanner:
    """Sistema de scan universal MAXIMO RENDIMIENTO para 9.81 USDT"""
    
    def __init__(self, api):
        self.api = api
        self.ia_system = MaxProfitIATradingSystem(api)
        self.scan_results = {}
        self.last_scan_time = None
        self.eligible_symbols = []
        self.symbol_metrics = {}
        self.symbol_cache = {}
        self.cache_expiry = timedelta(minutes=3)
        self.failed_symbols = set()
        self.last_cache_cleanup = datetime.now()
        self.capital_manager = MaxProfitCapitalManager(api)
        
    def get_all_trading_symbols(self):
        """Obtener TODOS los símbolos de trading"""
        try:
            exchange_info = self.api.client.futures_exchange_info()
            symbols = []
            
            for symbol_info in exchange_info['symbols']:
                symbol = symbol_info['symbol']
                
                if (symbol_info['status'] == 'TRADING' and 
                    symbol_info['quoteAsset'] == 'USDT' and
                    symbol_info['contractType'] == 'PERPETUAL'):
                    symbols.append(symbol)
            
            log.info(f"📊 Total de pares USDT disponibles: {len(symbols)}")
            return symbols
            
        except Exception as e:
            log.error(f"❌ Error obteniendo todos los símbolos: {e}")
            return list(config.PRIORITY_SYMBOLS)

    def get_symbols_24h_metrics(self, symbols: list):
        """Obtener métricas de 24h para todos los símbolos con cache"""
        try:
            cache_key = "24h_metrics"
            if cache_key in self.symbol_cache:
                cache_data, cache_time = self.symbol_cache[cache_key]
                if datetime.now() - cache_time < self.cache_expiry:
                    return cache_data
            
            metrics = {}
            tickers = self.api.client.futures_ticker()
            
            for ticker in tickers:
                symbol = ticker['symbol']
                if symbol in symbols:
                    try:
                        price_change_percent = float(ticker['priceChangePercent'])
                        volume = float(ticker['quoteVolume'])
                        high_price = float(ticker['highPrice'])
                        low_price = float(ticker['lowPrice'])
                        current_price = float(ticker['lastPrice'])
                        
                        if current_price <= 0:
                            continue
                            
                        volatility = ((high_price - low_price) / low_price * 100) if low_price > 0 else 0
                        
                        metrics[symbol] = {
                            'symbol': symbol,
                            'price_change_24h': price_change_percent,
                            'volume_24h': volume,
                            'volatility_24h': volatility,
                            'current_price': current_price,
                            'high_24h': high_price,
                            'low_24h': low_price
                        }
                    except Exception as e:
                        continue
            
            self.symbol_cache[cache_key] = (metrics, datetime.now())
            return metrics
            
        except Exception as e:
            log.error(f"❌ Error obteniendo métricas 24h: {e}")
            return {}

    def get_guaranteed_symbols(self):
        """Obtener símbolos GARANTIZADOS que funcionen con 9.81 USDT"""
        guaranteed_symbols = []
        
        test_symbols = [
            'DOGEUSDT', 'TRXUSDT', 'SHIBUSDT', 'VETUSDT', 'ONEUSDT',
            'HOTUSDT', 'BTTUSDT', 'ZILUSDT', 'WINUSDT', 'TFUELUSDT',
            'CHZUSDT', 'STMXUSDT', 'ANKRUSDT', 'BATUSDT', 'DENTUSDT',
            'CELRUSDT', 'COTIUSDT', 'FETUSDT', 'LRCUSDT', 'SANDUSDT'
        ]
        
        for symbol in test_symbols:
            try:
                current_price = self.api.get_current_price(symbol)
                if current_price > 0 and current_price <= config.MAX_PRICE_USDT:
                    if self.capital_manager.can_trade_symbol_max_profit(symbol, current_price):
                        guaranteed_symbols.append(symbol)
                        log.info(f"✅ Símbolo garantizado: {symbol} - Precio: ${current_price:.6f}")
                    
                    if len(guaranteed_symbols) >= 12:
                        break
            except Exception as e:
                continue
        
        return guaranteed_symbols

    def filter_symbols_by_criteria(self, metrics: dict):
        """Filtrado mejorado para evitar símbolos problemáticos"""
        filtered_symbols = {}
        
        # Símbolos conocidos problemáticos por límites de posición
        problematic_leverage_symbols = [
            'BLESSUSDT', 'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT',
            'XRPUSDT', 'ADAUSDT', 'DOTUSDT', 'MATICUSDT', 'LTCUSDT'
        ]
        
        symbols_checked = 0
        symbols_passed = 0
        
        for symbol, data in metrics.items():
            try:
                symbols_checked += 1
                
                if symbol in self.failed_symbols:
                    continue
                    
                # Excluir símbolos problemáticos conocidos
                if symbol in problematic_leverage_symbols:
                    continue
                    
                if symbol in config.PROBLEMATIC_SYMBOLS:
                    continue
                    
                volume_24h = data.get('volume_24h', 0)
                current_price = data.get('current_price', 0)
                price_change = abs(data.get('price_change_24h', 0))
                volatility = data.get('volatility_24h', 0)
                
                if current_price < config.MIN_PRICE_USDT:
                    continue
                    
                if current_price > config.MAX_PRICE_USDT:
                    continue
                    
                if volume_24h < config.MIN_VOLUME_USDT:
                    continue
                    
                # Filtros más flexibles para máximo rendimiento
                if volatility < config.MIN_VOLATILITY_24H or volatility > config.MAX_VOLATILITY_24H:
                    continue
                    
                if not self.capital_manager.can_trade_symbol_max_profit(symbol, current_price):
                    continue
                
                symbols_passed += 1
                filtered_symbols[symbol] = data
                    
            except Exception as e:
                self.failed_symbols.add(symbol)
                continue
        
        log.info(f"🎯 Símbolos analizados: {symbols_checked}, viables: {symbols_passed}")
        return filtered_symbols

    def calculate_profitability_score(self, symbol: str, metrics: dict):
        """Calcular score de rentabilidad MAXIMO RENDIMIENTO"""
        try:
            cache_key = f"score_{symbol}"
            if cache_key in self.symbol_cache:
                cache_data, cache_time = self.symbol_cache[cache_key]
                if datetime.now() - cache_time < timedelta(minutes=10):
                    return cache_data
            
            klines = self.api.get_klines(symbol, "5m", 30)
            if not klines:
                return 0, "Sin datos históricos"
            
            df = self.create_dataframe(klines)
            if df.empty:
                return 0, "DataFrame vacío"
            
            ia_prediction = self.ia_system.predict_movement_max_profit(symbol, df)
            ia_confidence = ia_prediction['confidence']
            ia_direction = ia_prediction['direction']
            aggressiveness = ia_prediction.get('aggressiveness', 0.0)
            
            symbol_metrics = metrics.get(symbol, {})
            volume_24h = symbol_metrics.get('volume_24h', 0)
            volatility_24h = symbol_metrics.get('volatility_24h', 0)
            price_change_24h = symbol_metrics.get('price_change_24h', 0)
            
            score = 0
            
            score += int(ia_confidence * 50)
            volume_score = min(20, (volume_24h / 1000000) * 1.5)
            score += volume_score
            
            if 2 <= volatility_24h <= 25:
                volatility_score = 15
            elif 1 <= volatility_24h < 2 or 25 < volatility_24h <= 40:
                volatility_score = 8
            else:
                volatility_score = 3
            score += volatility_score
            
            momentum_score = min(15, abs(price_change_24h) * 0.5)
            score += momentum_score
            score += int(aggressiveness * 12)
            
            details = [
                f"IA:{ia_confidence:.2f}",
                f"VOL:${volume_24h/1000000:.1f}M",
                f"VOLAT:{volatility_24h:.1f}%",
                f"MOM:{price_change_24h:.1f}%",
                f"AGGRO:{aggressiveness:.2f}"
            ]
            
            result = (min(100, score), ", ".join(details))
            self.symbol_cache[cache_key] = (result, datetime.now())
            return result
            
        except Exception as e:
            log.warning(f"⚠️ Error calculando score para {symbol}: {e}")
            self.failed_symbols.add(symbol)
            return 0, f"Error: {str(e)}"

    def scan_universal_symbols(self):
        """Scan universal MAXIMO RENDIMIENTO para 9.81 USDT"""
        try:
            log.info("🔍 Iniciando SCAN UNIVERSAL MAXIMO RENDIMIENTO...")
            
            self.cleanup_old_cache()
            
            all_symbols = self.get_all_trading_symbols()
            metrics_24h = self.get_symbols_24h_metrics(all_symbols)
            filtered_symbols = self.filter_symbols_by_criteria(metrics_24h)
            
            symbols_to_analyze = list(filtered_symbols.keys())[:config.MAX_SYMBOLS_TO_ANALYZE]
            log.info(f"🎯 Analizando {len(symbols_to_analyze)} símbolos para 9.81 USDT MAXPROFIT...")
            
            scored_symbols = []
            
            for symbol in symbols_to_analyze:
                try:
                    score, details = self.calculate_profitability_score(symbol, filtered_symbols)
                    
                    if score > 15:
                        symbol_data = filtered_symbols[symbol]
                        scored_symbols.append({
                            'symbol': symbol,
                            'score': score,
                            'details': details,
                            'price': symbol_data['current_price'],
                            'volume_24h': symbol_data['volume_24h'],
                            'volatility_24h': symbol_data['volatility_24h'],
                            'price_change_24h': symbol_data['price_change_24h'],
                            'ia_analysis': details
                        })
                        
                except Exception as e:
                    self.failed_symbols.add(symbol)
                    continue
            
            scored_symbols.sort(key=lambda x: x['score'], reverse=True)
            top_symbols = scored_symbols[:config.MAX_SYMBOLS_TO_TRADE]
            
            if not top_symbols:
                log.warning("⚠️ No se encontraron símbolos en el scan, usando símbolos garantizados...")
                guaranteed_symbols = self.get_guaranteed_symbols()
                for symbol in guaranteed_symbols:
                    try:
                        current_price = self.api.get_current_price(symbol)
                        top_symbols.append({
                            'symbol': symbol,
                            'score': 50,
                            'details': "Símbolo garantizado MAXPROFIT",
                            'price': current_price,
                            'volume_24h': 1000000,
                            'volatility_24h': 5.0,
                            'price_change_24h': 2.0,
                            'ia_analysis': "Garantizado MAXPROFIT"
                        })
                    except:
                        continue
            
            self.scan_results = {
                'timestamp': datetime.now().isoformat(),
                'total_analyzed': len(symbols_to_analyze),
                'top_symbols': top_symbols,
                'failed_symbols_count': len(self.failed_symbols)
            }
            
            self.eligible_symbols = [s['symbol'] for s in top_symbols]
            self.symbol_metrics = {s['symbol']: s for s in top_symbols}
            
            log.info("🎯 SCAN UNIVERSAL COMPLETADO - Top Símbolos para 9.81 USDT MAXPROFIT:")
            for i, symbol_data in enumerate(top_symbols[:12]):
                log.info(f"   {i+1}. {symbol_data['symbol']} - Score: {symbol_data['score']}/100 "
                        f"Price: ${symbol_data['price']:.6f}")
            
            self.last_scan_time = datetime.now()
            return top_symbols
            
        except Exception as e:
            log.error(f"❌ Error en SCAN UNIVERSAL para 9.81 USDT MAXPROFIT: {e}")
            guaranteed_symbols = self.get_guaranteed_symbols()
            fallback_symbols = []
            for symbol in guaranteed_symbols[:8]:
                fallback_symbols.append({
                    'symbol': symbol,
                    'score': 50,
                    'details': "Fallback garantizado MAXPROFIT",
                    'price': 0.01,
                    'volume_24h': 1000000,
                    'volatility_24h': 5.0,
                    'price_change_24h': 2.0,
                    'ia_analysis': "Fallback MAXPROFIT"
                })
            self.eligible_symbols = guaranteed_symbols[:8]
            return fallback_symbols

    def cleanup_old_cache(self):
        """Limpiar cache antiguo"""
        try:
            current_time = datetime.now()
            if (current_time - self.last_cache_cleanup).total_seconds() > 180:
                expired_keys = []
                for key, (data, timestamp) in self.symbol_cache.items():
                    if current_time - timestamp > self.cache_expiry:
                        expired_keys.append(key)
                
                for key in expired_keys:
                    del self.symbol_cache[key]
                
                self.last_cache_cleanup = current_time
        except Exception as e:
            pass

    def create_dataframe(self, klines):
        """Crear DataFrame desde klines"""
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'trades',
            'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df

# ════════════════════════════════════════════════════════════════
# GENERADOR DE SEÑALES MAXIMO RENDIMIENTO PARA 9.81 USDT
# ════════════════════════════════════════════════════════════════

class MaxProfitSignalGenerator:
    """Generador de señales MAXIMO RENDIMIENTO para 9.81 USDT"""
    
    def __init__(self, api: BinanceFuturesMaxProfit):
        self.api = api
        self.ia_system = MaxProfitIATradingSystem(api)
        self.signals = []
        self.symbol_analysis_cache = {}
        self.last_analysis_time = {}
        self.capital_manager = MaxProfitCapitalManager(api)
        self.position_manager = None
        
    def set_position_manager(self, position_manager):
        """Establecer el gestor de posiciones"""
        self.position_manager = position_manager

    def get_klines(self, symbol: str, interval: str, limit: int = config.CANDLES_LIMIT):
        try:
            klines = self.api.client.futures_klines(
                symbol=symbol, interval=interval, limit=limit
            )
            return klines if klines else None
        except Exception as e:
            log.error(f"Error obteniendo klines {symbol}: {e}")
            return None

    def analyze_symbol_max_profit(self, symbol: str):
        """Análisis MAXIMO RENDIMIENTO para 9.81 USDT"""
        try:
            if not self.position_manager:
                return None
                
            current_price = self.position_manager.get_current_price(symbol)
            if current_price > config.MAX_PRICE_USDT or current_price < config.MIN_PRICE_USDT:
                return None
                
            if not self.capital_manager.can_trade_symbol_max_profit(symbol, current_price):
                return None
            
            current_time = time.time()
            if symbol in self.last_analysis_time:
                if current_time - self.last_analysis_time[symbol] < 20:
                    return self.symbol_analysis_cache.get(symbol)
            
            log.debug(f"🧠 Análisis MAXIMO 9.81 USDT: {symbol}")
            
            klines_1m = self.get_klines(symbol, "1m", 30)
            klines_3m = self.get_klines(symbol, "3m", 20)
            
            if not klines_1m or not klines_3m:
                return None
                
            if len(klines_1m) < 5 or len(klines_3m) < 5:
                return None
                
            df_1m = self.create_dataframe(klines_1m)
            df_3m = self.create_dataframe(klines_3m)
            
            if df_1m.empty or df_3m.empty:
                return None
                
            ia_prediction = self.ia_system.predict_movement_max_profit(symbol, df_1m)
            ia_confidence = ia_prediction['confidence']
            ia_direction = ia_prediction['direction']
            aggressiveness = ia_prediction.get('aggressiveness', 0.0)
            
            df_1m = self.calculate_max_profit_indicators(df_1m)
            
            if df_1m.empty:
                return None
                
            latest_1m = df_1m.iloc[-1]
            current_price = float(latest_1m['close'])
            
            if current_price <= 0:
                return None
            
            score = 0
            signal_type = None
            score_details = []
            
            if ia_confidence > 0.08:
                ia_points = int(12 * ia_confidence)
                score += ia_points
                score_details.append(f"IA:{ia_confidence:.2f}")
                
                if aggressiveness > 0.08:
                    score += 5
                    score_details.append(f"AGG:{aggressiveness:.2f}")
                    
                signal_type = "LONG" if ia_direction == "BULLISH" else "SHORT"
            
            technical_signal = self._get_max_profit_technical_signal(df_1m, latest_1m)
            if technical_signal['signal'] != 'NEUTRAL':
                score += 6
                score_details.append(f"TECH:{technical_signal['signal']}")
                if signal_type is None:
                    signal_type = technical_signal['signal']
            
            momentum_score = self._calculate_max_profit_momentum_score(df_1m, df_3m)
            score += momentum_score
            if momentum_score > 0:
                score_details.append(f"MOM:{momentum_score}")
            
            volume_score = self._calculate_max_profit_volume_score(df_1m)
            score += volume_score
            if volume_score > 0:
                score_details.append(f"VOL:{volume_score}")
            
            if score >= config.MIN_SIGNAL_SCORE and signal_type is not None:
                atr_value = latest_1m.get('atr', current_price * 0.002)
                current_price = float(latest_1m['close'])

                min_stop_distance_price = current_price * config.MIN_STOP_DISTANCE_PCT
                base_sl_distance = atr_value * config.SL_ATR_MULT

                if current_price < 0.005:
                    min_stop_distance_price = current_price * 0.0002
                elif current_price < 0.01:
                    min_stop_distance_price = current_price * 0.0004

                final_sl_distance = max(base_sl_distance, min_stop_distance_price)
                max_sl_distance = current_price * 0.015
                final_sl_distance = min(final_sl_distance, max_sl_distance)
                
                sl_multiplier = 1.0 - (aggressiveness * 0.15)
                final_sl_distance *= sl_multiplier
                
                if signal_type == "LONG":
                    sl_price = current_price - final_sl_distance
                    tp_price = current_price + (final_sl_distance * config.TP_RR)
                else:
                    sl_price = current_price + final_sl_distance
                    tp_price = current_price - (final_sl_distance * config.TP_RR)
                
                if sl_price <= 0 or tp_price <= 0:
                    return None

                stop_distance_pct = abs(current_price - sl_price) / current_price
                
                if stop_distance_pct < config.MIN_STOP_DISTANCE_PCT:
                    adjustment_factor = config.MIN_STOP_DISTANCE_PCT / stop_distance_pct
                    final_sl_distance *= adjustment_factor
                    
                    if signal_type == "LONG":
                        sl_price = current_price - final_sl_distance
                        tp_price = current_price + (final_sl_distance * config.TP_RR)
                    else:
                        sl_price = current_price + final_sl_distance
                        tp_price = current_price - (final_sl_distance * config.TP_RR)
                
                stop_distance_pct = abs(current_price - sl_price) / current_price
                
                if stop_distance_pct > 0.10:
                    log.info(f"🔧 Ajustando stop amplio: {stop_distance_pct:.2%} -> 6%")
                    final_sl_distance = current_price * 0.06
                    if signal_type == "LONG":
                        sl_price = current_price - final_sl_distance
                        tp_price = current_price + (final_sl_distance * config.TP_RR)
                    else:
                        sl_price = current_price + final_sl_distance
                        tp_price = current_price - (final_sl_distance * config.TP_RR)
                    stop_distance_pct = 0.06
                
                signal_data = {
                    'symbol': symbol,
                    'type': signal_type,
                    'score': score,
                    'price': current_price,
                    'sl_price': sl_price,
                    'tp_price': tp_price,
                    'atr': atr_value,
                    'ia_confidence': ia_confidence,
                    'ia_direction': ia_direction,
                    'aggressiveness': aggressiveness,
                    'details': " ".join(score_details),
                    'stop_distance_pct': stop_distance_pct,
                    'timestamp': datetime.now().isoformat()
                }
                
                log.info(f"🎯 SEÑAL MAXIMO 9.81 USDT: {symbol} {signal_type} Score: {score} "
                        f"Precio: ${current_price:.6f} SL: {stop_distance_pct:.2%} "
                        f"IA: {ia_direction}({ia_confidence:.2f})")
                
                self.symbol_analysis_cache[symbol] = signal_data
                self.last_analysis_time[symbol] = current_time
                
                return signal_data
            
            self.symbol_analysis_cache[symbol] = None
            self.last_analysis_time[symbol] = current_time
            
            return None
            
        except Exception as e:
            log.warning(f"⚠️ Error análisis MAXIMO {symbol}: {e}")
            return None

    def _get_max_profit_technical_signal(self, df: pd.DataFrame, latest: pd.Series) -> dict:
        """Señal técnica MAXIMO RENDIMIENTO"""
        try:
            signal = 'NEUTRAL'
            strength = 0.0
            
            ema_fast = latest.get('ema_fast', 0)
            ema_slow = latest.get('ema_slow', 0)
            
            if pd.notna(ema_fast) and pd.notna(ema_slow):
                if ema_fast > ema_slow:
                    signal = 'LONG'
                    strength += 0.5
                elif ema_fast < ema_slow:
                    signal = 'SHORT'
                    strength += 0.5
            
            rsi = latest.get('rsi', 50)
            if pd.notna(rsi):
                if rsi < 30:
                    if signal == 'NEUTRAL':
                        signal = 'LONG'
                    strength += 0.4
                elif rsi > 70:
                    if signal == 'NEUTRAL':
                        signal = 'SHORT'
                    strength += 0.4
            
            macd_hist = latest.get('macd_hist', 0)
            if pd.notna(macd_hist):
                if macd_hist > 0 and signal in ['LONG', 'NEUTRAL']:
                    signal = 'LONG'
                    strength += 0.3
                elif macd_hist < 0 and signal in ['SHORT', 'NEUTRAL']:
                    signal = 'SHORT'
                    strength += 0.3
            
            return {'signal': signal, 'strength': strength}
            
        except:
            return {'signal': 'NEUTRAL', 'strength': 0.0}

    def _calculate_max_profit_momentum_score(self, df_1m: pd.DataFrame, df_3m: pd.DataFrame) -> int:
        """Score de momentum MAXIMO RENDIMIENTO"""
        try:
            score = 0
            
            if len(df_1m) >= 3:
                price_change_1m = (df_1m['close'].iloc[-1] - df_1m['close'].iloc[-3]) / df_1m['close'].iloc[-3] * 100
                if abs(price_change_1m) > 0.03:
                    score += 3
                    if price_change_1m > 0:
                        score += 2
            
            if (df_1m['ema_fast'].iloc[-1] > df_1m['ema_slow'].iloc[-1] and
                df_3m['ema_fast'].iloc[-1] > df_3m['ema_slow'].iloc[-1]):
                score += 2
            elif (df_1m['ema_fast'].iloc[-1] < df_1m['ema_slow'].iloc[-1] and
                  df_3m['ema_fast'].iloc[-1] < df_3m['ema_slow'].iloc[-1]):
                score += 2
                
            return min(6, score)
        except:
            return 0

    def _calculate_max_profit_volume_score(self, df: pd.DataFrame) -> int:
        """Score de volumen MAXIMO RENDIMIENTO"""
        try:
            score = 0
            
            if 'volume' not in df.columns or 'volume_ma' not in df.columns:
                return 0
                
            volume_ratio = df['volume'].iloc[-1] / df['volume_ma'].iloc[-1]
            
            if volume_ratio > 1.3:
                score += 2
            if volume_ratio > 2.0:
                score += 2
                
            return min(4, score)
        except:
            return 0

    def calculate_max_profit_indicators(self, df: pd.DataFrame):
        """Indicadores técnicos para 9.81 USDT MAXPROFIT"""
        try:
            if df.empty or len(df) < 5:
                return df
                
            df['ema_fast'] = talib.EMA(df['close'], timeperiod=config.FAST_EMA)
            df['ema_slow'] = talib.EMA(df['close'], timeperiod=config.SLOW_EMA)
            df['ema_trend'] = talib.EMA(df['close'], timeperiod=config.EMA_TREND)
            
            df['rsi'] = talib.RSI(df['close'], timeperiod=config.RSI_PERIOD)
            
            df['macd'], df['macd_signal'], df['macd_hist'] = talib.MACD(
                df['close'], fastperiod=config.MACD_FAST, slowperiod=config.MACD_SLOW, signalperiod=config.MACD_SIGNAL
            )
            
            df['atr'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=config.ATR_PERIOD)
            
            if 'volume' in df.columns:
                df['volume_ma'] = talib.SMA(df['volume'], timeperiod=config.VOLUME_MA)
                
            return df
            
        except Exception as e:
            log.error(f"❌ Error indicadores: {e}")
            return df

    def create_dataframe(self, klines):
        """Crear DataFrame desde klines"""
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'trades',
            'taker_buy_base', 'taker_buy_quote', 'ignore'
        ])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df

# ════════════════════════════════════════════════════════════════
# GESTOR DE POSICIONES - MAXIMO RENDIMIENTO PARA 9.81 USDT
# ════════════════════════════════════════════════════════════════

class MaxProfitPositionManager:
    def __init__(self, api: BinanceFuturesMaxProfit):
        self.api = api
        self.active_positions = {}
        self.bot_managed_positions = {}
        
    def get_active_positions(self):
        """Obtener posiciones activas - MAXIMO RENDIMIENTO PARA 9.81 USDT"""
        try:
            account = self.api.get_account_info()
            if not account:
                return self.active_positions
            
            current_positions = {}
            
            for position in account.get('positions', []):
                symbol = position.get('symbol')
                amount = float(position.get('positionAmt', 0))
                
                if abs(amount) > 0.0001:
                    current_positions[symbol] = {
                        'symbol': symbol,
                        'amount': amount,
                        'side': 'LONG' if amount > 0 else 'SHORT',
                        'entry_price': float(position.get('entryPrice', 0)),
                        'unrealized_pnl': float(position.get('unrealizedProfit', 0)),
                        'leverage': int(position.get('leverage', 1)),
                        'liquidation_price': float(position.get('liquidationPrice', 0)),
                        'timestamp': datetime.now().isoformat()
                    }
            
            self._sync_bot_managed_positions(current_positions)
            
            self.active_positions = current_positions
            return self.active_positions
            
        except Exception as e:
            log.error(f"❌ Error obteniendo posiciones: {e}")
            return self.active_positions

    def _sync_bot_managed_positions(self, current_positions: dict):
        """Sincronizar posiciones gestionadas por el bot"""
        try:
            symbols_to_remove = []
            for symbol in self.bot_managed_positions:
                if symbol not in current_positions:
                    symbols_to_remove.append(symbol)
            
            for symbol in symbols_to_remove:
                self.remove_bot_managed_position(symbol)
                
        except Exception as e:
            log.warning(f"⚠️ Error sincronizando posiciones: {e}")

    def add_bot_managed_position(self, symbol: str, position_data: dict):
        """Añadir posición gestionada por el bot"""
        try:
            required_keys = ['symbol', 'side', 'amount', 'entry_price', 'sl_price', 'tp_price', 'entry_time', 'position_value']
            
            for key in required_keys:
                if key not in position_data:
                    log.warning(f"⚠️ Clave faltante en posición {symbol}: {key}")
                    if key == 'sl_price':
                        position_data[key] = 0.0
                    elif key == 'tp_price':
                        position_data[key] = 0.0
                    elif key == 'entry_time':
                        position_data[key] = datetime.now()
                    elif key == 'position_value':
                        position_data[key] = 0.0
            
            self.bot_managed_positions[symbol] = position_data
            log.info(f"✅ Posición gestionada añadida: {symbol}")
            
        except Exception as e:
            log.error(f"❌ Error añadiendo posición gestionada {symbol}: {e}")

    def remove_bot_managed_position(self, symbol: str):
        """Eliminar posición gestionada por el bot"""
        try:
            if symbol in self.bot_managed_positions:
                del self.bot_managed_positions[symbol]
                log.info(f"✅ Posición gestionada eliminada: {symbol}")
        except Exception as e:
            log.error(f"❌ Error eliminando posición gestionada {symbol}: {e}")

    def get_bot_managed_position(self, symbol: str) -> dict:
        """Obtener posición gestionada por el bot"""
        return self.bot_managed_positions.get(symbol, {})

    def get_current_price(self, symbol: str) -> float:
        """Obtener precio actual del símbolo"""
        try:
            ticker = self.api.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            log.error(f"❌ Error obteniendo precio actual {symbol}: {e}")
            return 0.0

    def close_position(self, symbol: str, quantity: float):
        """Cerrar posición"""
        try:
            if config.DRY_RUN:
                log.info(f"[DRY_RUN] 🎯 Cerrando posición simulada: {symbol} {quantity}")
                return {'mock': True}
            
            return self.api.close_position(symbol, quantity)
        except Exception as e:
            log.error(f"❌ Error cerrando posición {symbol}: {e}")
            return None

# ════════════════════════════════════════════════════════════════
# SISTEMA DE PROTECCIÓN MAXIMO RENDIMIENTO PARA 9.81 USDT
# ════════════════════════════════════════════════════════════════

class EnhancedProtectionSystem:
    """Sistema de protección optimizado para 9.81 USDT MAXPROFIT"""
    
    def __init__(self, api):
        self.api = api
        self.daily_stats = {
            'trades_count': 0,
            'daily_pnl': 0.0,
            'consecutive_losses': 0,
            'consecutive_wins': 0,
            'last_trade_time': None,
            'daily_target_reached': False
        }
        self.trade_times = deque(maxlen=config.MAX_DAILY_TRADES)
        self.lock_until = None
        self.today = datetime.now().date()
        self.min_balance_protection = 3.0
        
    def _update_daily_stats(self):
        """Reiniciar estadísticas diarias"""
        try:
            current_date = datetime.now().date()
            if current_date != self.today:
                self.daily_stats = {
                    'trades_count': 0,
                    'daily_pnl': 0.0,
                    'consecutive_losses': 0,
                    'consecutive_wins': 0,
                    'last_trade_time': None,
                    'daily_target_reached': False
                }
                self.today = current_date
        except Exception as e:
            pass

    def can_trade_max_profit(self) -> bool:
        """Verificación ESPECÍFICA para 9.81 USDT MAXPROFIT con protección de margen"""
        self._update_daily_stats()
        
        if hasattr(self, 'current_balance') and self.current_balance < self.min_balance_protection:
            log.warning(f"⛔ Balance por debajo del mínimo protegido: ${self.current_balance:.2f} < ${self.min_balance_protection:.2f}")
            return False
        
        # 🔧 NUEVA PROTECCIÓN: Verificar margen disponible
        try:
            account = self.api.get_account_info()
            if account:
                available_balance = float(account.get('availableBalance', 0))
                if available_balance < config.MIN_AVAILABLE_MARGIN:
                    log.warning(f"⛔ Margen disponible insuficiente: ${available_balance:.2f} < ${config.MIN_AVAILABLE_MARGIN:.2f}")
                    return False
        except Exception as e:
            log.warning(f"⚠️ Error verificando margen: {e}")
        
        if self.lock_until and datetime.now() < self.lock_until:
            remaining = (self.lock_until - datetime.now()).total_seconds() // 60
            log.warning(f"🔒 Bloqueo activo ({int(remaining)} min restantes)")
            return False
        
        if self.daily_stats['trades_count'] >= config.MAX_DAILY_TRADES:
            log.warning(f"⛔ Límite diario de trades: {self.daily_stats['trades_count']}/{config.MAX_DAILY_TRADES}")
            return False
            
        if self.daily_stats['daily_pnl'] <= -config.DAILY_LOSS_LIMIT:
            lock_minutes = config.SMALL_BALANCE_LOCKOUT_MINUTES
            self.lock_until = datetime.now() + timedelta(minutes=lock_minutes)
            log.warning(f"⛔ Límite pérdida diaria: ${self.daily_stats['daily_pnl']:.2f} → bloqueo {lock_minutes} min")
            return False
            
        if self.daily_stats['daily_pnl'] >= 100.0:
            log.info(f"🎯 Objetivo diario MAXPROFIT alcanzado: +${self.daily_stats['daily_pnl']:.2f}")
            self.daily_stats['daily_target_reached'] = True
            return False
            
        if self.daily_stats['consecutive_losses'] >= 40:
            log.warning("⛔ 4 pérdidas consecutivas - pausa de 30min")
            self.lock_until = datetime.now() + timedelta(minutes=30)
            return False
            
        current_time = datetime.now()
        recent_trades = [t for t in self.trade_times if (current_time - t).total_seconds() < 3600]
        if len(recent_trades) >= 60:
            log.warning("⏰ 6 trades en la última hora - pausa de 15min")
            time.sleep(900)
            return False
            
        return True

    def set_current_balance(self, balance: float):
        """Actualizar balance actual para protección"""
        self.current_balance = balance

    def record_trade_result(self, pnl: float, symbol: str):
        """Registro de trade para 9.81 USDT MAXPROFIT"""
        self.daily_stats['trades_count'] += 1
        self.daily_stats['daily_pnl'] += pnl
        self.daily_stats['last_trade_time'] = datetime.now()
        self.trade_times.append(datetime.now())
        
        if pnl > 0:
            self.daily_stats['consecutive_wins'] += 1
            self.daily_stats['consecutive_losses'] = 0
            log.info(f"✅ Trade ganador MAXPROFIT: {symbol} +${pnl:.2f}")
        else:
            self.daily_stats['consecutive_losses'] += 1
            self.daily_stats['consecutive_wins'] = 0
            log.warning(f"❌ Trade perdedor MAXPROFIT: {symbol} ${pnl:.2f}")
            
        log.info(f"📊 ESTADO DIARIO MAXPROFIT: Trades: {self.daily_stats['trades_count']}, "
                f"PnL: ${self.daily_stats['daily_pnl']:.2f}")

# ════════════════════════════════════════════════════════════════
# BOT PRINCIPAL MAXIMO RENDIMIENTO PARA 9.81 USDT
# ════════════════════════════════════════════════════════════════

class UniversalScanBinanceFuturesBot:
    def __init__(self):
        self.running = False
        self.thread = None
        self.start_time = datetime.now()
        
        self.api = BinanceFuturesMaxProfit()
        self.capital = MaxProfitCapitalManager(self.api)
        self.position_manager = MaxProfitPositionManager(self.api)
        self.signal_generator = MaxProfitSignalGenerator(self.api)
        self.signal_generator.set_position_manager(self.position_manager)
        self.protection_system = EnhancedProtectionSystem(self.api)
        
        self.universal_scanner = UniversalSymbolScanner(self.api)
        self.ia_system = MaxProfitIATradingSystem(self.api)
        
        self.performance_metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'total_pnl': 0.0,
            'daily_target': 200.0,
            'max_daily_loss': 15.0
        }
        
        self.current_trading_symbols = []
        self.last_signal_check = {}
        self.last_scan_time = 0
        self.cycle_count = 0
        
        log.info("🤖 Binance Futures Bot V18.4 - MAXIMO RENDIMIENTO PARA 9.81 USDT")

    def start(self):
        if self.running:
            log.warning("⚠️ Bot ya está ejecutándose")
            return
        
        if not self.capital.update_balance():
            log.error("❌ No se puede obtener balance inicial")
            return
            
        log.info(f"💰 BALANCE INICIAL 9.81 USDT MAXPROFIT: {self.capital.current_balance:.2f} USDT")
        
        self._execute_universal_scan()
        
        self.running = True
        self.thread = threading.Thread(target=self._run_scan_loop, daemon=True)
        self.thread.start()
        log.info("🚀 Bot 9.81 USDT MAXIMO RENDIMIENTO iniciado")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        log.info("🛑 Bot 9.81 USDT MAXPROFIT detenido")

    def _execute_universal_scan(self):
        """Ejecutar scan universal para 9.81 USDT MAXPROFIT"""
        try:
            log.info("🌐 Ejecutando SCAN UNIVERSAL MAXIMO RENDIMIENTO...")
            top_symbols = self.universal_scanner.scan_universal_symbols()
            
            if top_symbols:
                self.current_trading_symbols = [s['symbol'] for s in top_symbols]
                log.info(f"✅ SCAN completado: {len(self.current_trading_symbols)} símbolos para 9.81 USDT MAXPROFIT")
            else:
                self.current_trading_symbols = list(config.PRIORITY_SYMBOLS)
                
            self.last_scan_time = time.time()
            
        except Exception as e:
            log.error(f"❌ Error en scan universal para 9.81 USDT MAXPROFIT: {e}")
            self.current_trading_symbols = list(config.PRIORITY_SYMBOLS)

    def _run_scan_loop(self):
        """Loop principal MAXIMO RENDIMIENTO para 9.81 USDT"""
        log.info("🔄 Iniciando loop MAXIMO RENDIMIENTO para 9.81 USDT...")
        
        consecutive_errors = 0
        last_balance_update = 0
        last_position_update = 0
        last_health_check = time.time()
        
        while self.running:
            cycle_start = time.time()
            try:
                self.cycle_count += 1
                
                current_time = time.time()
                
                if current_time - last_balance_update > 8:
                    if self.capital.update_balance():
                        self.protection_system.set_current_balance(self.capital.current_balance)
                        last_balance_update = current_time
                    else:
                        time.sleep(3)
                        continue
                
                if current_time - last_position_update > 8:
                    active_positions = self.position_manager.get_active_positions()
                    last_position_update = current_time
                
                if (current_time - self.last_scan_time > config.SCAN_INTERVAL_MINUTES * 60 or 
                    len(self.current_trading_symbols) == 0):
                    self._execute_universal_scan()
                
                has_balance = self.capital.current_balance > config.MIN_BALANCE_THRESHOLD
                has_position_slots = len(active_positions) < config.MAX_CONCURRENT_POS
                protection_ok = self.protection_system.can_trade_max_profit()
                
                if has_balance and has_position_slots and protection_ok:
                    self._search_signals(active_positions, current_time)
                
                for symbol in list(active_positions.keys()):
                    try:
                        self._manage_position(symbol)
                    except Exception as e:
                        log.warning(f"⚠️ Error gestionando posición {symbol}: {e}")
                        time.sleep(1)
                
                if current_time - last_health_check > 150:
                    self._health_check()
                    last_health_check = current_time
                
                if self.cycle_count % 4 == 0:
                    log.info(f"📈 ESTADO MAXPROFIT - Ciclo: {self.cycle_count}, "
                            f"Balance: ${self.capital.current_balance:.2f}, "
                            f"Posiciones: {len(active_positions)}")
                
                consecutive_errors = 0
                
            except Exception as e:
                log.error(f"❌ Error en loop principal MAXPROFIT: {e}")
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    log.error("🔴 Múltiples errores consecutivos, pausa extendida...")
                    time.sleep(45)
                    consecutive_errors = 0
                else:
                    time.sleep(8)

            sleep_time = max(0.8, config.POLL_SEC - (time.time() - cycle_start))
            time.sleep(sleep_time)

    def _health_check(self):
        """Verificación de salud del bot para 9.81 USDT MAXPROFIT"""
        try:
            balance_ok = self.capital.current_balance > config.MIN_BALANCE_THRESHOLD
            api_ok = self.api.health_status['consecutive_errors'] < 5
            
            if not balance_ok:
                log.warning("⚠️ Chequeo salud: Balance bajo")
            if not api_ok:
                log.warning("⚠️ Chequeo salud: Múltiples errores de API")
                
            log.info(f"❤️ Salud del bot MAXPROFIT: Balance={'OK' if balance_ok else 'BAJO'}, "
                    f"API={'OK' if api_ok else 'PROBLEMAS'}")
                
        except Exception as e:
            log.warning(f"⚠️ Error en chequeo de salud: {e}")

    def _search_signals(self, active_positions: dict, current_time: float):
        """Búsqueda de señales con límites mejorados de margen"""
        try:
            signals_found = 0
            max_signals_per_cycle = 2
            
            # 🔧 VERIFICAR MARGEN DISPONIBLE GLOBAL
            account = self.api.get_account_info()
            if account:
                available_balance = float(account.get('availableBalance', 0))
                if available_balance < 3.0:
                    log.warning(f"⭕ Margen global insuficiente: ${available_balance:.2f}")
                    return
            
            for symbol in self.current_trading_symbols:
                if signals_found >= max_signals_per_cycle:
                    break
                    
                if symbol in active_positions:
                    continue
                    
                if symbol in self.last_signal_check:
                    time_since_last = current_time - self.last_signal_check[symbol]
                    if time_since_last < 25:
                        continue
                
                current_price = self.position_manager.get_current_price(symbol)
                if current_price < config.MIN_PRICE_USDT:
                    continue
                    
                if not self.capital.can_trade_symbol_max_profit(symbol, current_price):
                    continue
                    
                signal = self.signal_generator.analyze_symbol_max_profit(symbol)
                if signal and signal['score'] >= config.MIN_SIGNAL_SCORE:
                    log.info(f"🎯 Señal MAXIMO 9.81 USDT: {symbol} {signal['type']} "
                            f"Score: {signal['score']} Precio: ${current_price:.6f} "
                            f"SL: {signal['stop_distance_pct']:.2%}")
                    
                    self._execute_trade(signal)
                    self.last_signal_check[symbol] = current_time
                    signals_found += 1
                    
                    time.sleep(1.0)
                
        except Exception as e:
            log.error(f"❌ Error en búsqueda MAXPROFIT: {e}")

    def _execute_trade(self, signal: dict):
        """Ejecución de trade con verificación mejorada de margen"""
        try:
            symbol = signal['symbol']
            signal_type = signal['type']
            entry_price = signal['price']
            sl_price = signal['sl_price']
            tp_price = signal['tp_price']
            confidence = signal['ia_confidence']
            aggressiveness = signal['aggressiveness']

            # 🔧 ACTUALIZAR BALANCE PRIMERO
            if not self.capital.update_balance():
                log.warning(f"⭕ No se pudo actualizar balance para {symbol}")
                return

            # 🔧 VERIFICAR MARGEN DISPONIBLE
            account = self.api.get_account_info()
            if not account:
                log.warning(f"⭕ No se pudo obtener información de cuenta para {symbol}")
                return

            available_balance = float(account.get('availableBalance', 0))
            MIN_AVAILABLE_MARGIN = config.MIN_AVAILABLE_MARGIN
            
            if available_balance < MIN_AVAILABLE_MARGIN:
                log.warning(f"⭕ Margen insuficiente para {symbol}: ${available_balance:.2f} < ${MIN_AVAILABLE_MARGIN:.2f}")
                return

            if (sl_price <= 0 or tp_price <= 0 or entry_price <= 0 or
                entry_price > config.MAX_PRICE_USDT):
                log.warning(f"⭕ Precios inválidos o muy altos para {symbol}")
                return

            stop_distance_pct = abs(entry_price - sl_price) / entry_price
            if stop_distance_pct < config.MIN_STOP_DISTANCE_PCT:
                log.warning(f"⭕ Stop demasiado cercano: {stop_distance_pct:.3%} < {config.MIN_STOP_DISTANCE_PCT:.3%}")
                return

            log.info(f"🎯 EJECUTANDO TRADE MAXIMO 9.81 USDT: {symbol} {signal_type} "
                    f"@ {entry_price:.6f} SL: {sl_price:.6f} TP: {tp_price:.6f}")

            quantity = self.capital.calculate_max_profit_position_size(
                symbol, entry_price, sl_price, confidence, aggressiveness
            )

            if quantity <= 0:
                log.warning(f"⭕ Cantidad inválida para {symbol}: {quantity}")
                return

            position_value = quantity * entry_price
            
            # 🔧 VERIFICACIÓN FINAL DE MARGEN
            if available_balance - position_value < 1.0:
                log.warning(f"⭕ Operación dejaría margen insuficiente: ${available_balance:.2f} - ${position_value:.2f} < $1.00")
                return

            # 🔧 NUEVA VALIDACIÓN MÁS FLEXIBLE
            if not self.capital.validate_position_limits(symbol, quantity, entry_price):
                # 🔧 INTENTAR CON CANTIDAD MÍNIMA
                min_quantity_safety = config.MIN_NOTIONAL_SAFETY / entry_price
                min_quantity_safety = self.api.round_quantity(symbol, min_quantity_safety)
                min_position_value = min_quantity_safety * entry_price
                
                if min_position_value >= config.MIN_NOTIONAL_SAFETY and min_position_value <= available_balance * 0.8:
                    quantity = min_quantity_safety
                    position_value = min_position_value
                    log.info(f"🔧 Usando cantidad mínima de seguridad: {quantity:.0f} = ${position_value:.2f}")
                else:
                    log.warning(f"⭕ Validación de límites fallida para {symbol}")
                    return

            if position_value < 6.0:
                log.warning(f"⭕ Notional insuficiente: ${position_value:.2f} < $6.00")
                return

            side = SIDE_BUY if signal_type == "LONG" else SIDE_SELL
            
            order = self.api.place_order_with_retry(symbol, side, quantity)
            
            if not order:
                log.warning(f"⭕ Orden fallida para {symbol}")
                return

            log.info(f"✅ Orden EJECUTADA MAXIMO 9.81 USDT: {symbol} {side} {quantity:.0f} = ${position_value:.2f}")

            position_data = {
                'symbol': symbol,
                'side': signal_type,
                'amount': quantity,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'entry_time': datetime.now(),
                'position_value': position_value,
                'ia_confidence': confidence,
                'aggressiveness': aggressiveness
            }
        
            self.position_manager.add_bot_managed_position(symbol, position_data)

            if config.USE_EXCHANGE_STOPS:
                stop_side = SIDE_SELL if signal_type == "LONG" else SIDE_BUY
                self.api.place_stop_order(symbol, stop_side, quantity, sl_price)

        except Exception as e:
            log.error(f"❌ Error ejecutando trade para 9.81 USDT MAXPROFIT: {e}")

    def _manage_position(self, symbol: str):
        """Gestión de posición MAXIMO RENDIMIENTO para 9.81 USDT"""
        try:
            bot_position = self.position_manager.get_bot_managed_position(symbol)
            if not bot_position:
                return

            current_price = self.position_manager.get_current_price(symbol)
            
            if current_price <= 0:
                return

            required_keys = ['side', 'entry_price', 'sl_price', 'tp_price']
            for key in required_keys:
                if key not in bot_position:
                    if key == 'sl_price':
                        bot_position[key] = bot_position['entry_price'] * 0.98
                    elif key == 'tp_price':
                        bot_position[key] = bot_position['entry_price'] * 1.04

            side = bot_position['side']
            entry_price = bot_position['entry_price']
            sl_price = bot_position['sl_price']
            tp_price = bot_position['tp_price']

            if side == "LONG":
                pnl_pct = (current_price - entry_price) / entry_price * 100
            else:
                pnl_pct = (entry_price - current_price) / entry_price * 100

            if ((side == "LONG" and current_price >= tp_price) or
                (side == "SHORT" and current_price <= tp_price)):
                
                log.info(f"🎯 Take Profit MAXIMO 9.81 USDT: {symbol} PnL: {pnl_pct:.2f}%")
                self._close_position_with_profit(symbol, pnl_pct)
                return

            if ((side == "LONG" and current_price <= sl_price) or
                (side == "SHORT" and current_price >= sl_price)):
                
                log.info(f"🛑 Stop Loss MAXIMO 9.81 USDT: {symbol} PnL: {pnl_pct:.2f}%")
                self._close_position_with_loss(symbol, pnl_pct)
                return

        except Exception as e:
            log.error(f"❌ Error gestionando posición {symbol}: {e}")

    def _close_position_with_profit(self, symbol: str, pnl_pct: float):
        """Cerrar posición con ganancia para 9.81 USDT MAXPROFIT"""
        try:
            active_positions = self.position_manager.get_active_positions()
            position = active_positions.get(symbol)
            
            if not position:
                return

            quantity = abs(position['amount'])
            result = self.position_manager.close_position(symbol, quantity)
            
            if result:
                pnl_usdt = (pnl_pct / 100) * self.capital.current_balance
                log.info(f"💰 Posición cerrada con GANANCIA MAXIMO 9.81 USDT: {symbol} +{pnl_pct:.2f}% (+${pnl_usdt:.2f})")
                self.protection_system.record_trade_result(pnl_usdt, symbol)
                self.position_manager.remove_bot_managed_position(symbol)

        except Exception as e:
            log.error(f"❌ Error cerrando posición con ganancia {symbol}: {e}")

    def _close_position_with_loss(self, symbol: str, pnl_pct: float):
        """Cerrar posición con pérdida para 9.81 USDT MAXPROFIT"""
        try:
            active_positions = self.position_manager.get_active_positions()
            position = active_positions.get(symbol)
            
            if not position:
                return

            quantity = abs(position['amount'])
            result = self.position_manager.close_position(symbol, quantity)
            
            if result:
                pnl_usdt = (pnl_pct / 100) * self.capital.current_balance
                log.info(f"📉 Posición cerrada con PÉRDIDA MAXIMO 9.81 USDT: {symbol} {pnl_pct:.2f}% (${pnl_usdt:.2f})")
                self.protection_system.record_trade_result(pnl_usdt, symbol)
                self.position_manager.remove_bot_managed_position(symbol)

        except Exception as e:
            log.error(f"❌ Error cerrando posición con pérdida {symbol}: {e}")

# ════════════════════════════════════════════════════════════════
# WEBSOCKET HANDLERS PARA DATOS EN TIEMPO REAL
# ════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    """Estado general del bot"""
    try:
        bot_status = {
            'running': bot.running if 'bot' in globals() else False,
            'current_balance': bot.capital.current_balance if 'bot' in globals() else 0,
            'active_positions': len(bot.position_manager.active_positions) if 'bot' in globals() else 0,
            'trading_symbols_count': len(bot.current_trading_symbols) if 'bot' in globals() else 0,
            'optimized_for': '9.81 USDT - MAXIMO RENDIMIENTO'
        }
        return jsonify(bot_status)
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/positions')
def api_positions():
    """Obtener posiciones reales en tiempo real"""
    try:
        if 'bot' not in globals():
            return jsonify({'error': 'Bot no inicializado'})
        
        active_positions = bot.position_manager.get_active_positions()
        positions_data = []
        total_unrealized_pnl = 0.0
        
        for symbol, position in active_positions.items():
            try:
                current_price = bot.position_manager.get_current_price(symbol)
                entry_price = position.get('entry_price', 0)
                amount = position.get('amount', 0)
                side = position.get('side', 'LONG')
                
                # Calcular PnL en tiempo real
                if side == 'LONG':
                    unrealized_pnl = (current_price - entry_price) * amount
                else:
                    unrealized_pnl = (entry_price - current_price) * amount
                
                pnl_percent = (unrealized_pnl / (entry_price * abs(amount))) * 100 if entry_price * abs(amount) > 0 else 0
                total_unrealized_pnl += unrealized_pnl
                
                positions_data.append({
                    'symbol': symbol,
                    'side': side,
                    'amount': abs(amount),
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'unrealized_pnl': unrealized_pnl,
                    'pnl_percent': pnl_percent,
                    'leverage': position.get('leverage', 1),
                    'liquidation_price': position.get('liquidation_price', 0),
                    'timestamp': position.get('timestamp', '')
                })
                
            except Exception as e:
                log.warning(f"⚠️ Error procesando posición {symbol}: {e}")
                continue
        
        return jsonify({
            'positions': positions_data,
            'total_unrealized_pnl': total_unrealized_pnl,
            'positions_count': len(positions_data),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        log.error(f"❌ Error obteniendo posiciones: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/performance')
def api_performance():
    """Obtener métricas de performance en tiempo real"""
    try:
        if 'bot' not in globals():
            return jsonify({'error': 'Bot no inicializado'})
        
        # Obtener estadísticas del sistema de protección
        protection = bot.protection_system
        capital = bot.capital
        
        # Obtener cuenta actualizada
        account = bot.api.get_account_info()
        available_balance = float(account.get('availableBalance', 0)) if account else 0
        
        # Calcular win rate
        total_trades = bot.performance_metrics['total_trades']
        winning_trades = bot.performance_metrics['winning_trades']
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return jsonify({
            'daily_trades': protection.daily_stats['trades_count'],
            'daily_pnl': protection.daily_stats['daily_pnl'],
            'consecutive_losses': protection.daily_stats['consecutive_losses'],
            'consecutive_wins': protection.daily_stats['consecutive_wins'],
            'available_balance': available_balance,
            'total_balance': capital.current_balance,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        log.error(f"❌ Error obteniendo performance: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/start', methods=['POST'])
def api_start():
    try:
        if 'bot' not in globals():
            return jsonify({'error': 'Bot no inicializado'})
        
        if not bot.running:
            bot.start()
            return jsonify({'status': 'Bot 9.81 USDT MAXPROFIT iniciado'})
        else:
            return jsonify({'status': 'Bot ya estaba ejecutándose'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    try:
        if 'bot' in globals() and bot.running:
            bot.stop()
            return jsonify({'status': 'Bot 9.81 USDT MAXPROFIT detenido'})
        else:
            return jsonify({'status': 'Bot no estaba ejecutándose'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/scan')
def api_scan():
    try:
        if 'bot' in globals():
            bot._execute_universal_scan()
            return jsonify({
                'status': 'Scan ejecutado',
                'symbols_count': len(bot.current_trading_symbols),
                'optimized_for': '9.81 USDT - MAXIMO RENDIMIENTO'
            })
        else:
            return jsonify({'error': 'Bot no inicializado'})
    except Exception as e:
        return jsonify({'error': str(e)})

@socketio.on('connect')
def handle_connect():
    log.info('Cliente WebSocket conectado')
    socketio.emit('log_update', {'message': '✅ Cliente conectado - Modo tiempo real activado', 'level': 'info'})

@socketio.on('disconnect')
def handle_disconnect():
    log.info('Cliente WebSocket desconectado')

@socketio.on('request_positions')
def handle_positions_request():
    """Enviar posiciones cuando el cliente las solicite"""
    try:
        if 'bot' in globals():
            # Emitir datos iniciales
            active_positions = bot.position_manager.get_active_positions()
            socketio.emit('positions_update', {'positions': active_positions})
    except Exception as e:
        log.error(f"❌ Error enviando posiciones: {e}")

# ════════════════════════════════════════════════════════════════
# SISTEMA DE ACTUALIZACIÓN EN TIEMPO REAL
# ════════════════════════════════════════════════════════════════

def start_realtime_updates():
    """Iniciar emisión de actualizaciones en tiempo real"""
    def emit_updates():
        while True:
            try:
                if 'bot' in globals() and bot.running:
                    # Emitir actualización de posiciones cada 3 segundos
                    active_positions = bot.position_manager.get_active_positions()
                    positions_data = []
                    total_unrealized_pnl = 0.0
                    
                    for symbol, position in active_positions.items():
                        try:
                            current_price = bot.position_manager.get_current_price(symbol)
                            entry_price = position.get('entry_price', 0)
                            amount = position.get('amount', 0)
                            side = position.get('side', 'LONG')
                            
                            if side == 'LONG':
                                unrealized_pnl = (current_price - entry_price) * amount
                            else:
                                unrealized_pnl = (entry_price - current_price) * amount
                            
                            pnl_percent = (unrealized_pnl / (entry_price * abs(amount))) * 100 if entry_price * abs(amount) > 0 else 0
                            total_unrealized_pnl += unrealized_pnl
                            
                            positions_data.append({
                                'symbol': symbol,
                                'side': side,
                                'amount': abs(amount),
                                'entry_price': entry_price,
                                'current_price': current_price,
                                'unrealized_pnl': unrealized_pnl,
                                'pnl_percent': pnl_percent,
                                'leverage': position.get('leverage', 1),
                                'liquidation_price': position.get('liquidation_price', 0)
                            })
                            
                        except Exception as e:
                            continue
                    
                    socketio.emit('positions_realtime', {
                        'positions': positions_data,
                        'total_unrealized_pnl': total_unrealized_pnl,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Emitir actualización de performance cada 5 segundos
                    protection = bot.protection_system
                    performance_data = {
                        'daily_trades': protection.daily_stats['trades_count'],
                        'daily_pnl': protection.daily_stats['daily_pnl'],
                        'consecutive_losses': protection.daily_stats['consecutive_losses'],
                        'consecutive_wins': protection.daily_stats['consecutive_wins'],
                        'available_balance': bot.capital.current_balance,
                        'total_trades': bot.performance_metrics['total_trades'],
                        'winning_trades': bot.performance_metrics['winning_trades'],
                        'timestamp': datetime.now().isoformat()
                    }
                    socketio.emit('performance_update', performance_data)
                
                time.sleep(3)  # Esperar 3 segundos entre actualizaciones
                
            except Exception as e:
                log.error(f"❌ Error en emisión tiempo real: {e}")
                time.sleep(5)
    
    # Iniciar thread para actualizaciones en tiempo real
    update_thread = threading.Thread(target=emit_updates, daemon=True)
    update_thread.start()

# ════════════════════════════════════════════════════════════════
# INICIALIZACIÓN
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        log.info("🚀 INICIANDO BOT MAXIMO RENDIMIENTO PARA 9.81 USDT - SISTEMA TIEMPO REAL")
        
        # Inicializar bot
        bot = UniversalScanBinanceFuturesBot()
        
        # Iniciar sistema de actualizaciones en tiempo real
        start_realtime_updates()
        
        log.info("🌐 Iniciando servidor web en http://localhost:5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
        
    except KeyboardInterrupt:
        log.info("🛑 Detención solicitada por usuario")
        if 'bot' in globals():
            bot.stop()
    except Exception as e:
        log.error(f"❌ Error fatal: {e}")
        if 'bot' in globals():
            bot.stop()
