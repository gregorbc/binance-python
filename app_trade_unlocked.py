from __future__ import annotations

import json
import logging
import math
import os
import random
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import psutil
import requests
from dotenv import load_dotenv

"""
Binance Futures Bot - Aplicación Web v12.0 con Gestión de Capital Real
Sistema de trading avanzado con seguimiento de capital real y reinversión de ganancias
Por gregorbc@gmail.com
"""
import eventlet

eventlet.monkey_patch()

# Cargar variables de entorno primero
load_dotenv()

# Configurar encoding para Windows
if sys.platform == "win32":
    # Forzar UTF-8 en Windows
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Configurar logging básico temporalmente SIN EMOJIS
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot_startup.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("BinanceFuturesBot")

# Crear directorio de logs
os.makedirs("logs", exist_ok=True)

# Manejar importación de TA-Lib
try:
    import talib

    TALIB_ENABLED = True
    log.info("TA-Lib encontrado y habilitado")
except ImportError:
    TALIB_ENABLED = False
    log.warning(
        "ADVERTENCIA: TA-Lib no encontrado. Algunos indicadores estaran deshabilitados."
    )

# Importaciones de Binance
try:
    from binance.client import Client
    from binance.enums import (
        FUTURE_ORDER_TYPE_LIMIT,
        FUTURE_ORDER_TYPE_MARKET,
        SIDE_BUY,
        SIDE_SELL,
        TIME_IN_FORCE_GTC,
    )
    from binance.exceptions import BinanceAPIException
except ImportError as e:
    log.error(f"Error importando Binance: {e}")
    exit(1)

# Importaciones de Flask
try:
    from functools import wraps

    from flask import (
        Flask,
        jsonify,
        render_template,
        request,
        send_file,
        send_from_directory,
    )
    from flask_cors import CORS
    from flask_socketio import SocketIO
except ImportError as e:
    log.error(f"Error importando Flask: {e}")
    exit(1)


# === CONFIGURACIÓN PRINCIPAL ===
@dataclass
class CONFIG:
    # Configuración Global - Valores más seguros para 20x
    LEVERAGE: int = 20
    MAX_CONCURRENT_POS: int = 3
    NUM_SYMBOLS_TO_SCAN: int = 50

    # Gestión de Riesgo Mejorada
    STOP_LOSS_PERCENT: float = 0.4
    TAKE_PROFIT_PERCENT: float = 0.8
    RISK_PER_TRADE_PERCENT: float = 0.5

    # Nuevos parámetros de seguridad
    MAX_DAILY_LOSS_PERCENT: float = 3.0
    MAX_DRAWDOWN_PERCENT: float = 6.0
    MIN_BALANCE_THRESHOLD: float = 10.0

    # Configuración de símbolos más estricta
    MIN_24H_VOLUME: float = 25_000_000

    # Exclusión de símbolos de alto riesgo
    EXCLUDE_SYMBOLS: tuple = field(
        default_factory=lambda: (
            "BTCDOMUSDT",
            "DEFIUSDT",
            "USDCUSDT",
            "1000BONKUSDT",
            "1000FLOKIUSDT",
            "1000LUNCUSDT",
            "1000PEPEUSDT",
            "1000SHIBUSDT",
            "1000XECUSDT",
        )
    )

    # Timeframes y polling optimizados
    TIMEFRAME: str = "5m"
    CANDLES_LIMIT: int = 100
    POLL_SEC: float = 15.0

    # Indicadores técnicos
    FAST_EMA: int = 8
    SLOW_EMA: int = 21
    RSI_PERIOD: int = 14

    # Activación de características de seguridad
    DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"

    # Configuración de logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "bot_v12_20x_usdt.log"

    # Configuración de estrategia
    USE_FIXED_SL_TP: bool = True
    MIN_SIGNAL_STRENGTH: float = 0.35
    MAX_POSITION_HOLD_HOURS: int = 2

    def __post_init__(self):
        """Validaciones adicionales de configuración"""
        if self.LEVERAGE > 20:
            raise ValueError("El apalancamiento no puede exceder 20x")
        if self.RISK_PER_TRADE_PERCENT > 2.0:
            raise ValueError("El riesgo por trade no puede exceder el 2%")


config = CONFIG()

# === INICIALIZACIÓN DE FLASK ===
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "your-secret-key-here")
CORS(app)
socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins="*")


# === SISTEMA DE LOGGING MEJORADO PARA WINDOWS ===
class RealTimeLogHandler(logging.Handler):
    """Manejador de logs que emite en tiempo real via Socket.IO"""

    def __init__(self, socketio):
        super().__init__()
        self.socketio = socketio
        self.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )

    def emit(self, record):
        try:
            log_entry = self.format(record)
            level = record.levelname.lower()

            # Emitir via Socket.IO
            self.socketio.emit(
                "log_update",
                {
                    "message": log_entry,
                    "level": level,
                    "timestamp": datetime.now().isoformat(),
                },
            )
        except Exception as e:
            print(f"Error en RealTimeLogHandler: {e}")


class WindowsSafeStreamHandler(logging.StreamHandler):
    """Handler seguro para Windows que maneja caracteres Unicode"""

    def __init__(self):
        super().__init__()
        # Forzar encoding UTF-8 en el stream
        if hasattr(self.stream, "reconfigure"):
            self.stream.reconfigure(encoding="utf-8")

    def emit(self, record):
        try:
            msg = self.format(record)
            # Reemplazar caracteres problemáticos en Windows
            safe_msg = msg.encode("utf-8", errors="replace").decode("utf-8")
            stream = self.stream
            stream.write(safe_msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def setup_logging():
    """Configuración robusta del sistema de logging para Windows"""
    # Limpiar handlers existentes
    for handler in log.handlers[:]:
        log.removeHandler(handler)

    # Configurar formatter SIN EMOJIS para Windows
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler para archivo con UTF-8
    file_handler = logging.FileHandler(f"logs/{config.LOG_FILE}", encoding="utf-8")
    file_handler.setFormatter(formatter)

    # Handler seguro para consola en Windows
    console_handler = WindowsSafeStreamHandler()
    console_handler.setFormatter(formatter)

    # Handler para tiempo real
    realtime_handler = RealTimeLogHandler(socketio)
    realtime_handler.setFormatter(formatter)

    # Configurar nivel
    log_level = getattr(logging, config.LOG_LEVEL)
    log.setLevel(log_level)
    file_handler.setLevel(log_level)
    console_handler.setLevel(log_level)
    realtime_handler.setLevel(log_level)

    # Agregar handlers
    log.addHandler(file_handler)
    log.addHandler(console_handler)
    log.addHandler(realtime_handler)

    # Reducir verbosidad de librerías externas
    for logger_name in ["binance", "urllib3", "engineio", "socketio"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    return log


# Configurar logging
log = setup_logging()

# === SISTEMA DE AUTENTICACIÓN API ===
API_TOKEN = os.getenv("API_TOKEN")


def require_api_token(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not API_TOKEN:
            return jsonify({"error": "API_TOKEN not set"}), 500
        token = request.headers.get("X-API-Token")
        if token != API_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return fn(*args, **kwargs)

    return wrapper


# === CLASE BINANCE FUTURES MEJORADA ===
class BinanceFutures:
    def __init__(self):
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError(
                "API keys no configuradas. Establezca las variables de entorno BINANCE_API_KEY and BINANCE_API_SECRET"
            )

        self.client = Client(api_key, api_secret, testnet=testnet)

        # Mostrar información de conexión SIN EMOJIS
        mode = "TESTNET" if testnet else "MAINNET REAL"
        log.info(f"CONECTADO A BINANCE FUTURES {mode} - 20x LEVERAGE")

        if testnet:
            log.info("MODO TESTNET - No se realizaran operaciones reales")
        else:
            log.info("MODO REAL - Se realizaran operaciones con dinero real")

        try:
            self.exchange_info = self.client.futures_exchange_info()
            log.info("Informacion de exchange cargada exitosamente")
        except Exception as e:
            log.error(f"Error conectando a Binance: {e}")
            raise

    def is_symbol_tradable(self, symbol: str) -> bool:
        """Verifica si un símbolo está disponible para trading"""
        try:
            # Para símbolos principales, asumir que son tradables
            major_symbols = [
                "BTCUSDT",
                "ETHUSDT",
                "BNBUSDT",
                "ADAUSDT",
                "XRPUSDT",
                "SOLUSDT",
            ]
            if symbol in major_symbols:
                return True

            s_info = next(
                (s for s in self.exchange_info["symbols"] if s["symbol"] == symbol),
                None,
            )
            if not s_info:
                log.warning(f"Simbolo {symbol} no encontrado en exchange info")
                return False

            status = s_info.get("status")
            if status != "TRADING":
                log.info(f"Simbolo {symbol} no disponible. Estado: {status}")
                return False

            return True

        except Exception as e:
            log.error(f"Error verificando simbolo {symbol}: {e}")
            return symbol in ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

    def _safe_api_call(self, func, *args, **kwargs):
        """Llamada segura a API con reintentos"""
        for attempt in range(3):
            try:
                result = func(*args, **kwargs)
                return result
            except BinanceAPIException as e:
                if e.code == -4131:
                    log.warning(
                        "Error PERCENT_PRICE (-4131) en orden. Mercado volatil o iliquido. Omitiendo."
                    )
                    return None
                elif e.code == -1122:
                    log.warning(f"Simbolo no disponible (error -1122): {e.message}")
                    return None
                else:
                    log.warning(f"Error de API ({e.code}): {e.message}")
                    if attempt == 2:
                        log.error(
                            f"Error final de API despues de reintentos: {e.code} - {e.message}"
                        )
            except Exception as e:
                log.warning(f"Error general en llamada a API: {e}")
                if attempt == 2:
                    log.error(f"Error general final despues de reintentos: {e}")

            time.sleep(1 * (attempt + 1))

        return None

    def get_symbol_filters(self, symbol: str) -> Optional[Dict[str, float]]:
        try:
            s_info = next(
                (s for s in self.exchange_info["symbols"] if s["symbol"] == symbol),
                None,
            )
            if not s_info:
                return None

            filters = {f["filterType"]: f for f in s_info["filters"]}

            result = {
                "stepSize": float(filters["LOT_SIZE"]["stepSize"]),
                "minQty": float(filters["LOT_SIZE"]["minQty"]),
                "tickSize": float(filters["PRICE_FILTER"]["tickSize"]),
            }

            if "MIN_NOTIONAL" in filters:
                result["minNotional"] = float(
                    filters["MIN_NOTIONAL"].get("notional", 5.0)
                )
            else:
                result["minNotional"] = 5.0

            return result

        except Exception as e:
            log.error(f"Error obteniendo filters para {symbol}: {e}")
            return None

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Optional[Dict]:
        if not self.is_symbol_tradable(symbol):
            log.error(f"No se puede colocar orden para simbolo no tradable: {symbol}")
            return None

        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
        }

        if order_type == FUTURE_ORDER_TYPE_LIMIT:
            if price is None:
                log.error("Precio requerido para ordenes LIMIT.")
                return None
            params.update({"price": str(price), "timeInForce": TIME_IN_FORCE_GTC})

        if reduce_only:
            params["reduceOnly"] = "true"

        if config.DRY_RUN:
            log.info(f"[DRY_RUN] place_order: {params}")
            return {"mock": True, "orderId": int(time.time() * 1000)}

        return self._safe_api_call(self.client.futures_create_order, **params)

    @staticmethod
    def round_value(value: float, step: float) -> float:
        if step == 0:
            return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)


# === GESTOR DE CAPITAL MEJORADO ===
class CapitalManager:
    def __init__(self, api):
        self.api = api
        self.current_balance = 0.0
        self.initial_balance = 0.0
        self.last_balance_update = 0
        self.total_profit = 0.0
        self.reinvested_profit = 0.0
        self.daily_pnl = 0.0
        self.daily_starting_balance = 0.0

    def validate_balance(self, balance: float) -> bool:
        """Validar que el balance sea realista"""
        if balance <= 0:
            log.error(f"Balance invalido: {balance}")
            return False
        if balance > 1000000:
            log.error(f"Balance sospechosamente alto: {balance}")
            return False
        return True

    def get_real_balance(self) -> float:
        """Obtener el balance real de la cuenta"""
        try:
            account_info = self.api._safe_api_call(self.api.client.futures_account)
            if account_info:
                usdt_balance = next(
                    (
                        float(a.get("walletBalance", 0))
                        for a in account_info.get("assets", [])
                        if a.get("asset") == "USDT"
                    ),
                    0.0,
                )
                return usdt_balance
        except Exception as e:
            log.error(f"Error obteniendo balance real: {e}")
        return 0.0

    def update_balance(self, force: bool = False) -> bool:
        """Actualizar balance con mejores validaciones"""
        current_time = time.time()

        if force or (current_time - self.last_balance_update > 300):
            try:
                new_balance = self.get_real_balance()

                if not self.validate_balance(new_balance):
                    return False

                # Actualizar métricas
                if self.current_balance == 0:
                    self.initial_balance = new_balance
                    self.daily_starting_balance = new_balance
                    log.info(f"Capital inicial: {new_balance:.2f} USDT")

                previous_balance = self.current_balance
                self.current_balance = new_balance
                self.last_balance_update = current_time

                # Calcular P&L
                self.total_profit = self.current_balance - self.initial_balance
                daily_pnl_change = self.current_balance - self.daily_starting_balance

                # Solo registrar cambios significativos
                if abs(self.current_balance - previous_balance) > 0.1:
                    log.info(
                        f"Balance actualizado: {self.current_balance:.2f} USDT | P&L Diario: {daily_pnl_change:+.2f} USDT"
                    )

                return True

            except Exception as e:
                log.error(f"Error critico actualizando balance: {e}")
                return False
        return False

    def get_performance_stats(self) -> Dict:
        """Obtener estadísticas de rendimiento"""
        return {
            "current_balance": self.current_balance,
            "initial_balance": self.initial_balance,
            "total_profit": self.total_profit,
            "reinvested_profit": self.reinvested_profit,
            "profit_percentage": (
                (self.total_profit / self.initial_balance * 100)
                if self.initial_balance > 0
                else 0
            ),
            "daily_pnl": self.daily_pnl,
        }


# === NOTIFICADOR DE TELEGRAM SIMPLIFICADO ===
class TelegramNotifier:
    def __init__(self):
        self.enabled = False
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if self.token and self.chat_id:
            self.enabled = True
            log.info("Telegram notifier habilitado")
        else:
            log.info(
                "Telegram disabled (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)."
            )

    def send_message(self, message: str):
        if not self.enabled:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            log.error(f"Error enviando mensaje de Telegram: {e}")
            return False


# === GESTOR DE RIESGO MEJORADO ===
class RiskManager:
    def __init__(self, trading_bot):
        self.bot = trading_bot

    def calculate_symbol_risk(self, symbol: str, df: pd.DataFrame) -> float:
        """Calcular score de riesgo para un símbolo (0-1, donde 1 es máximo riesgo)"""
        if df is None or len(df) < 20:
            return 1.0

        try:
            risk_factors = []

            # 1. Volatilidad (40% peso)
            volatility = self._calculate_volatility(df)
            vol_score = min(1.0, volatility / 5.0)
            risk_factors.append(vol_score * 0.4)

            # 2. Volumen (30% peso)
            volume_score = self._calculate_volume_risk(df)
            risk_factors.append(volume_score * 0.3)

            # 3. Spread (30% peso)
            spread_score = self._calculate_spread_risk(symbol)
            risk_factors.append(spread_score * 0.3)

            total_risk = sum(risk_factors)
            return min(1.0, total_risk)

        except Exception as e:
            log.error(f"Error calculando riesgo para {symbol}: {e}")
            return 1.0

    def _calculate_volatility(self, df: pd.DataFrame) -> float:
        """Calcular volatilidad porcentual"""
        returns = np.log(df["close"] / df["close"].shift(1))
        return returns.std() * np.sqrt(365) * 100

    def _calculate_volume_risk(self, df: pd.DataFrame) -> float:
        """Calcular riesgo basado en volumen"""
        current_volume = df["volume"].iloc[-1]
        avg_volume = df["volume"].tail(20).mean()

        if avg_volume == 0:
            return 1.0

        volume_ratio = current_volume / avg_volume
        return max(0.0, 1.0 - min(volume_ratio, 2.0) / 2.0)

    def _calculate_spread_risk(self, symbol: str) -> float:
        """Calcular riesgo basado en spread"""
        try:
            ticker = self.bot.api._safe_api_call(
                self.bot.api.client.futures_symbol_ticker, symbol=symbol
            )
            if ticker:
                bid = float(ticker["bidPrice"])
                ask = float(ticker["askPrice"])
                spread = (ask - bid) / bid * 100
                return min(1.0, spread / 0.5)
        except:
            pass
        return 1.0

    def should_trade_symbol(self, symbol: str, df: pd.DataFrame) -> bool:
        """Decidir si es seguro operar un símbolo"""
        risk_score = self.calculate_symbol_risk(symbol, df)
        max_risk_threshold = float(os.getenv("MAX_RISK_THRESHOLD", "0.85"))
        if risk_score > max_risk_threshold:
            log.info(f"{symbol} excluido por alto riesgo: {risk_score:.2f}")
            return False

        return True


# === BOT DE TRADING PRINCIPAL ===
class TradingBot:
    def __init__(self):
        self.api = BinanceFutures()
        self.capital_manager = CapitalManager(self.api)
        self.risk_manager = RiskManager(self)
        self.telegram_notifier = TelegramNotifier()

        self.recently_signaled = set()
        self.cycle_count = 0
        self.start_time = time.time()
        self.signal_strength = {}
        self.market_regime = "NEUTRAL"

    def test_api_connection(self) -> bool:
        """Verificar conexión a la API"""
        try:
            account_info = self.api._safe_api_call(self.api.client.futures_account)
            return account_info is not None
        except Exception as e:
            log.error(f"Error conectando a API: {e}")
            return False

    def get_top_symbols(self) -> List[str]:
        """Obtener los mejores símbolos para trading"""
        try:
            tickers = self.api._safe_api_call(self.api.client.futures_ticker)
            if not tickers:
                return []

            # Filtrar símbolos USDT con buen volumen
            valid_symbols = []
            for t in tickers:
                symbol = t["symbol"]
                if (
                    symbol.endswith("USDT")
                    and symbol not in config.EXCLUDE_SYMBOLS
                    and float(t.get("quoteVolume", 0)) > config.MIN_24H_VOLUME
                ):
                    valid_symbols.append(symbol)

            # Ordenar por volumen y limitar
            valid_symbols.sort(
                key=lambda x: float(
                    next(t["quoteVolume"] for t in tickers if t["symbol"] == x)
                ),
                reverse=True,
            )
            return valid_symbols[: config.NUM_SYMBOLS_TO_SCAN]

        except Exception as e:
            log.error(f"Error obteniendo simbolos: {e}")
            return []

    def get_klines_for_symbol(
        self, symbol: str, interval: str = None, limit: int = None
    ) -> Optional[pd.DataFrame]:
        """Obtener datos de klines para un símbolo"""
        klines = self.api._safe_api_call(
            self.api.client.futures_klines,
            symbol=symbol,
            interval=interval or config.TIMEFRAME,
            limit=limit or config.CANDLES_LIMIT,
        )
        if not klines:
            return None

        try:
            df = pd.DataFrame(
                klines,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_asset_volume",
                    "number_of_trades",
                    "taker_buy_base_asset_volume",
                    "taker_buy_quote_asset_volume",
                    "ignore",
                ],
            )
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"])
            return df
        except Exception as e:
            log.error(f"Error procesando klines para {symbol}: {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame):
        """Calcular indicadores técnicos"""
        if df is None or len(df) < 5:
            return
        try:
            # Calcular EMAs
            df["fast_ema"] = df["close"].ewm(span=config.FAST_EMA, adjust=False).mean()
            df["slow_ema"] = df["close"].ewm(span=config.SLOW_EMA, adjust=False).mean()

            # Calcular RSI
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=config.RSI_PERIOD).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=config.RSI_PERIOD).mean()
            rs = gain / loss
            df["rsi"] = 100 - (100 / (1 + rs))

        except Exception as e:
            log.error(f"Error calculando indicadores: {e}")

    def check_signal(self, df: pd.DataFrame, symbol: str) -> Optional[str]:
        """Verificar señal de trading con gestión de riesgo"""
        if df is None or len(df) < 50:
            return None

        # Verificación de riesgo primero
        if not self.risk_manager.should_trade_symbol(symbol, df):
            return None

        last, prev = df.iloc[-1], df.iloc[-2]

        # Verificar datos válidos
        if any(pd.isna([last["close"], last["volume"]])):
            return None

        # Señal basada en cruce de EMAs
        ema_cross = False
        if last["fast_ema"] > last["slow_ema"] and prev["fast_ema"] <= prev["slow_ema"]:
            signal = "LONG"
            ema_cross = True
        elif (
            last["fast_ema"] < last["slow_ema"] and prev["fast_ema"] >= prev["slow_ema"]
        ):
            signal = "SHORT"
            ema_cross = True

        if not ema_cross:
            return None

        # Confirmación RSI
        rsi_confirm = (signal == "LONG" and last["rsi"] > 40 and last["rsi"] < 70) or (
            signal == "SHORT" and last["rsi"] < 60 and last["rsi"] > 30
        )

        if not rsi_confirm:
            return None

        log.info(f"Senal {signal} detectada para {symbol}")
        return signal

    def calculate_position_size(self, symbol: str, price: float) -> float:
        """Calcular tamaño de posición basado en riesgo"""
        current_balance = self.capital_manager.current_balance

        if current_balance <= 0:
            return 0

        # Calcular riesgo por trade
        risk_amount = current_balance * (config.RISK_PER_TRADE_PERCENT / 100)

        # Ajuste: eliminar mínimo fijo de 5 USDT; usar minNotional/leverage
        filters = (
            self.api.get_symbol_filters(symbol)
            if hasattr(self.api, "get_symbol_filters")
            else None
        )
        min_notional = 5.0
        min_qty = None
        if filters:
            try:
                min_notional = float(filters.get("minNotional", min_notional))
            except Exception:
                pass
            if "minQty" in filters:
                try:
                    min_qty = float(filters["minQty"])
                except Exception:
                    pass
        leverage = float(getattr(config, "LEVERAGE", 20) or 20)
        min_risk_needed = max(0.0, min_notional / leverage)
        if risk_amount < min_risk_needed:
            log.debug(
                f"Ajustando riesgo de {risk_amount:.4f} -> {min_risk_needed:.4f} (minNotional={min_notional}, L={leverage})"
            )
            risk_amount = min_risk_needed

        # Calcular tamaño basado en stop loss
        sl_distance = price * (config.STOP_LOSS_PERCENT / 100)
        if sl_distance <= 0:
            return 0

        position_size = risk_amount / sl_distance
        position_size = position_size * config.LEVERAGE

        # Aplicar filtros del exchange
        filters = self.api.get_symbol_filters(symbol)
        if filters:
            min_qty = filters["minQty"]
            min_notional = filters.get("minNotional", 5.0)

            if position_size < min_qty:
                position_size = min_qty

            notional_value = position_size * price
            if notional_value < min_notional:
                min_position_size = min_notional / price
                if min_position_size < min_qty:
                    return 0
                position_size = min_position_size

        return max(position_size, 0)

    def open_trade(self, symbol: str, side: str, last_candle):
        """Abrir una nueva posición"""
        if not self.api.is_symbol_tradable(symbol):
            return

        price = float(last_candle["close"])
        filters = self.api.get_symbol_filters(symbol)

        if not filters:
            return

        quantity = self.calculate_position_size(symbol, price)
        if quantity <= 0:
            return

        quantity = self.api.round_value(quantity, filters["stepSize"])
        min_qty = filters["minQty"]

        if quantity < min_qty:
            return

        order_side = SIDE_BUY if side == "LONG" else SIDE_SELL

        log.info(f"Intentando abrir {side} {symbol} (Qty: {quantity:.6f})")

        if config.DRY_RUN:
            log.info(f"[DRY_RUN] Orden {side} para {symbol}")
            return

        order = self.api.place_order(
            symbol, order_side, FUTURE_ORDER_TYPE_MARKET, quantity
        )

        if order and order.get("orderId"):
            log.info(f"ORDEN CREADA: {side} {quantity:.6f} {symbol}")

            if self.telegram_notifier.enabled:
                self.telegram_notifier.send_message(
                    f"NUEVA POSICION\n"
                    f"Simbolo: {symbol}\n"
                    f"Direccion: {side}\n"
                    f"Cantidad: {quantity:.6f}\n"
                    f"Precio: ${price:.4f}\n"
                    f"Balance: ${self.capital_manager.current_balance:.2f}"
                )

    def get_open_positions(self):
        """Obtener posiciones abiertas"""
        try:
            account_info = self.api._safe_api_call(self.api.client.futures_account)
            if account_info:
                return {
                    p["symbol"]: p
                    for p in account_info["positions"]
                    if float(p["positionAmt"]) != 0
                }
            return {}
        except Exception as e:
            log.error(f"Error obteniendo posiciones: {e}")
            return {}

    def run(self):
        """Método principal del bot"""
        log.info("Iniciando Bot de Trading - Modo 20x")

        # Verificar conexión
        if not self.test_api_connection():
            log.error("No se pudo conectar a Binance. Deteniendo bot.")
            return

        # Actualizar balance inicial
        if not self.capital_manager.update_balance(force=True):
            log.error("No se pudo obtener balance inicial. Deteniendo bot.")
            return

        log.info(f"Balance inicial: {self.capital_manager.current_balance:.2f} USDT")

        try:
            self._main_loop()
        except KeyboardInterrupt:
            log.info("Bot detenido por el usuario")
        except Exception as e:
            log.error(f"Error critico en el bot: {e}")

    def _main_loop(self):
        """Loop principal del bot"""
        while True:
            try:
                with state_lock:
                    if not app_state["running"]:
                        break

                self.cycle_count += 1

                # Actualizar balance periódicamente
                if self.cycle_count % 10 == 0:
                    self.capital_manager.update_balance()

                # Obtener símbolos y procesar
                symbols = self.get_top_symbols()
                if not symbols:
                    log.warning("No se encontraron simbolos validos")
                    time.sleep(config.POLL_SEC)
                    continue

                # Procesar cada símbolo
                for symbol in symbols[:10]:  # Limitar a 10 símbolos por ciclo
                    try:
                        df = self.get_klines_for_symbol(symbol)
                        if df is not None and len(df) > 50:
                            self.calculate_indicators(df)
                            signal = self.check_signal(df, symbol)

                            if signal and symbol not in self.get_open_positions():
                                self.open_trade(symbol, signal, df.iloc[-1])

                    except Exception as e:
                        log.error(f"Error procesando {symbol}: {e}")

                # Actualizar estado de la aplicación
                with state_lock:
                    app_state["balance"] = self.capital_manager.current_balance
                    app_state["open_positions"] = self.get_open_positions()
                    app_state["cycle_count"] = self.cycle_count

                time.sleep(config.POLL_SEC)

            except Exception as e:
                log.error(f"ERROR en ciclo principal: {e}")
                time.sleep(30)  # Esperar 30 segundos antes de reintentar


# === ESTADO DE LA APLICACIÓN ===
state_lock = threading.RLock()
app_state = {
    "running": False,
    "status_message": "Listo para iniciar",
    "balance": 0.0,
    "open_positions": {},
    "performance_stats": {
        "trades_count": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "realized_pnl": 0.0,
    },
    "cycle_count": 0,
    "start_time": time.time(),
    "market_regime": "NEUTRAL",
}


# === RUTAS FLASK ===
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def api_health():
    """Endpoint de salud del sistema"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime": time.time() - app_state.get("start_time", time.time()),
        "memory_usage": f"{psutil.Process().memory_percent():.1f}%",
        "cpu_usage": f"{psutil.cpu_percent():.1f}%",
        "running": app_state["running"],
    }
    return jsonify(health_status)


@app.route("/api/status")
def api_status():
    with state_lock:
        return jsonify(app_state)


@app.route("/api/start", methods=["POST"])
@require_api_token
def api_start():
    global bot_thread
    with state_lock:
        if app_state["running"]:
            return jsonify({"status": "already_running"})

        app_state["running"] = True
        app_state["status_message"] = "Ejecutandose"

    def run_bot():
        try:
            bot = TradingBot()
            bot.run()
        except Exception as e:
            log.error(f"Error en el bot: {e}")
            with state_lock:
                app_state["running"] = False
                app_state["status_message"] = f"Error: {str(e)}"

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    return jsonify({"status": "started"})


@app.route("/api/stop", methods=["POST"])
@require_api_token
def api_stop():
    with state_lock:
        app_state["running"] = False
        app_state["status_message"] = "Detenido"
    return jsonify({"status": "stopped"})


@app.route("/api/config")
@require_api_token
def api_config():
    with state_lock:
        return jsonify(asdict(config))


@app.route("/api/positions")
@require_api_token
def api_positions():
    """Obtener posiciones actuales"""
    with state_lock:
        return jsonify(app_state["open_positions"])


@app.route("/api/performance")
@require_api_token
def api_performance():
    """Obtener métricas de performance"""
    with state_lock:
        return jsonify(app_state["performance_stats"])


@app.route("/api/logs")
@require_api_token
def api_logs():
    """Obtener logs históricos"""
    try:
        log_file_path = f"logs/{config.LOG_FILE}"
        if os.path.exists(log_file_path):
            with open(log_file_path, "r", encoding="utf-8") as f:
                logs = f.readlines()[-100:]
            return jsonify({"logs": logs})
        return jsonify({"logs": []})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# === EMISIÓN PERIÓDICA DE ESTADO ===
def emit_periodic_updates():
    """Emitir actualizaciones periódicas del estado"""
    while True:
        try:
            with state_lock:
                socketio.emit("status_update", app_state)
            time.sleep(3)
        except Exception as e:
            log.error(f"Error emitiendo actualizaciones: {e}")
            time.sleep(5)


# === INICIO AUTOMÁTICO DEL BOT ===
def auto_start_bot():
    """Iniciar el bot automáticamente al inicio de la aplicación"""
    global bot_thread

    auto_start = os.getenv("AUTO_START_BOT", "false").lower() == "true"

    if auto_start:
        log.info("INICIO AUTOMATICO CONFIGURADO - Iniciando bot...")
        time.sleep(2)

        with state_lock:
            if not app_state["running"]:
                app_state["running"] = True
                app_state["status_message"] = "Ejecutandose (Inicio Automatico)"

        def run_bot():
            try:
                log.info("CREANDO INSTANCIA DEL BOT DE TRADING...")
                bot = TradingBot()
                log.info("INICIANDO CICLO PRINCIPAL DEL BOT...")
                bot.run()
            except Exception as e:
                log.error(f"Error en el bot (inicio automatico): {e}")
                with state_lock:
                    app_state["running"] = False
                    app_state["status_message"] = f"Error: {str(e)}"

        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        log.info("Bot iniciado automaticamente")
    else:
        log.info(
            "Inicio automatico desactivado - Use la interfaz web para iniciar el bot"
        )


# === EJECUCIÓN PRINCIPAL ===
if __name__ == "__main__":
    log.info("Iniciando aplicacion Flask con Socket.IO...")

    # Verificar variables de entorno críticas
    required_env_vars = ["BINANCE_API_KEY", "BINANCE_API_SECRET"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        log.error(f"Variables de entorno faltantes: {', '.join(missing_vars)}")
        log.error(
            "Asegurate de crear un archivo .env con BINANCE_API_KEY y BINANCE_API_SECRET"
        )
        exit(1)

    # Iniciar hilo de actualizaciones
    update_thread = threading.Thread(target=emit_periodic_updates, daemon=True)
    update_thread.start()

    # Iniciar bot automáticamente si está configurado
    auto_start_bot()

    log.info("Sistema inicializado correctamente")
    log.info(f"Servidor web iniciando en http://0.0.0.0:5000")

    # Iniciar servidor
    try:
        socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    except Exception as e:
        log.error(f"Error al iniciar el servidor: {e}")
