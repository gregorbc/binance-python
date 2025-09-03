from __future__ import annotations
"""
Binance Futures Bot - Web Application v12.0 with Real Capital Management
Advanced trading system with real capital tracking and profit reinvestment
By gregorbc@gmail.com
"""
import os, time, math, logging, threading, random, requests
import pandas as pd
import numpy as np
from collections import deque
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import talib

from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, FUTURE_ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
from binance.exceptions import BinanceAPIException

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS

# Importaciones para el modelo de aprendizaje profundo By gregorbc@gmail.com
try:
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Dense
    from tensorflow.keras.optimizers import Adam
    DRL_ENABLED = True
except ImportError:
    DRL_ENABLED = False
    print("WARNING: TensorFlow not found. Deep Learning features will be disabled. By gregorbc@gmail.com")

from sqlalchemy import desc, func, case
try:
    from database import SessionLocal, Trade, PerformanceMetrics, AccountBalance
    DB_ENABLED = True
except ImportError:
    DB_ENABLED = False
    print("WARNING: 'database.py' not found. Database features will be disabled. By gregorbc@gmail.com")


# -------------------- CONFIGURATION -------------------- #
@dataclass
class CONFIG:
    # Global Configuration By gregorbc@gmail.com
    LEVERAGE: int = 10
    MAX_CONCURRENT_POS: int = 3
    NUM_SYMBOLS_TO_SCAN: int = 50
    # Strategy Configuration By gregorbc@gmail.com
    ATR_MULT_SL: float = 2.2
    ATR_MULT_TP: float = 3.5
    # Trailing Stop Configuration By gregorbc@gmail.com
    TRAILING_STOP_ACTIVATION: float = 0.8
    TRAILING_STOP_PERCENTAGE: float = 0.35
    # Fixed SL/TP Configuration By gregorbc@gmail.com
    USE_FIXED_SL_TP: bool = True
    STOP_LOSS_PERCENT: float = 1.5
    TAKE_PROFIT_PERCENT: float = 3.5  # Changed from 3.0 to 3.5 By gregorbc@gmail.com
    # AI Adjustment Configuration By gregorbc@gmail.com
    AI_SL_ADJUSTMENT: bool = True
    AI_TP_ADJUSTMENT: bool = True
    AI_TRAILING_ADJUSTMENT: bool = True
    AI_VOLATILITY_FACTOR: float = 1.5
    # Fixed Configuration By gregorbc@gmail.com
    MARGIN_TYPE: str = "CROSSED"
    MIN_24H_VOLUME: float = 30_000_000
    EXCLUDE_SYMBOLS: tuple = ("BTCDOMUSDT", "DEFIUSDT", "USDCUSDT", "TUSDUSDT", "BUSDUSDT", "USTUSDT")
    BLACKLIST_SYMBOLS: tuple = ("PROMPTUSDT", "PLAYUSDT", "LDOUSDT", "1000FLOKIUSDT",
                               "QTUMUSDT", "LRCUSDT", "GALAUSDT", "SKLUSDT", "HBARUSDT", "CUSDT",
                               "SOLUSDT", "BNBUSDT", "ADAUSDT")
    TIMEFRAME: str = "5m"
    CANDLES_LIMIT: int = 100
    FAST_EMA: int = 10
    SLOW_EMA: int = 21
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9
    RSI_PERIOD: int = 14
    STOCH_PERIOD: int = 14
    POLL_SEC: float = 10.0
    DRY_RUN: bool = False
    MAX_WORKERS_KLINE: int = 10
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "bot_v12_real_capital.log"
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"
    SIGNAL_COOLDOWN_CYCLES: int = 30
    # Balance monitoring - Gestión de capital real By gregorbc@gmail.com
    MIN_BALANCE_THRESHOLD: float = 15.0
    RISK_PER_TRADE_PERCENT: float = 3.5  # Changed from 2.0 to 3.5 By gregorbc@gmail.com
    # Connection settings By gregorbc@gmail.com
    MAX_API_RETRIES: int = 3
    API_RETRY_DELAY: float = 1.0
    # AI Enhancement Settings By gregorbc@gmail.com
    AI_LEARNING_RATE: float = 0.02
    AI_EXPLORATION_RATE: float = 0.06
    AI_VOLATILITY_THRESHOLD: float = 2.5
    AI_TREND_STRENGTH_THRESHOLD: float = 25.0
    # Enhanced Strategy Settings By gregorbc@gmail.com
    MIN_SIGNAL_STRENGTH: float = 0.65
    MAX_POSITION_HOLD_HOURS: int = 4
    VOLATILITY_ADJUSTMENT: bool = True
    # Enhanced Risk Management By gregorbc@gmail.com
    MAX_DAILY_LOSS_PERCENT: float = 10.0
    MAX_DRAWDOWN_PERCENT: float = 15.0
    # Symbol settings optimizados By gregorbc@gmail.com
    SYMBOL_SPECIFIC_SETTINGS: Dict = field(default_factory=lambda: {
        "BTCUSDT": {"risk_multiplier": 0.5, "max_leverage": 5, "enabled": False},
        "ETHUSDT": {"risk_multiplier": 0.5, "max_leverage": 5, "enabled": False},
        "XRPUSDT": {"risk_multiplier": 1.2, "max_leverage": 10},
        "DOGEUSDT": {"risk_multiplier": 1.2, "max_leverage": 10},
        "MATICUSDT": {"risk_multiplier": 1.1, "max_leverage": 10},
        "SHIBUSDT": {"risk_multiplier": 1.3, "max_leverage": 15},
        "LTCUSDT": {"risk_multiplier": 1.0, "max_leverage": 8},
        "TRXUSDT": {"risk_multiplier": 1.2, "max_leverage": 10},
        "DOTUSDT": {"risk_multiplier": 0.8, "max_leverage": 8},
        "LINKUSDT": {"risk_multiplier": 0.8, "max_leverage": 8},
        "BCHUSDT": {"risk_multiplier": 0.7, "max_leverage": 5, "enabled": False},
        "AVAXUSDT": {"risk_multiplier": 0.8, "max_leverage": 8},
        "XLMUSDT": {"risk_multiplier": 1.2, "max_leverage": 10},
        "ATOMUSDT": {"risk_multiplier": 0.8, "max_leverage": 8},
        "ETCUSDT": {"risk_multiplier": 0.9, "max_leverage": 8},
        "ADAUSDT": {"risk_multiplier": 0.6, "max_leverage": 5, "enabled": False},
        "ALGOUSDT": {"risk_multiplier": 1.1, "max_leverage": 10},
        "VETUSDT": {"risk_multiplier": 1.2, "max_leverage": 10},
        "THETAUSDT": {"risk_multiplier": 1.0, "max_leverage": 8},
        "FILUSDT": {"risk_multiplier": 0.8, "max_leverage": 8},
        "XTZUSDT": {"risk_multiplier": 1.0, "max_leverage": 8},
        "EOSUSDT": {"risk_multiplier": 1.0, "max_leverage": 8},
        "AAVEUSDT": {"risk_multiplier": 0.5, "max_leverage": 5, "enabled": False},
        "UNIUSDT": {"risk_multiplier": 0.7, "max_leverage": 6},
    })
    ENABLE_DYNAMIC_LEVERAGE: bool = True
    VOLUME_WEIGHTED_SIGNALS: bool = True
    MIN_VOLUME_CONFIRMATION: float = 1.2  # Changed from 1.8 to 1.2 By gregorbc@gmail.com
    # Configuración para timeframe múltiple By gregorbc@gmail.com
    HIGHER_TIMEFRAME_CONFIRMATION: bool = True
    HIGHER_TIMEFRAME: str = "30m"  # Changed from "15m" to "30m" By gregorbc@gmail.com
    BTC_CORRELATION_FILTER: bool = True
    # Configuración de capital real y reinversión By gregorbc@gmail.com
    MIN_NOTIONAL_OVERRIDE: float = 5.0
    REINVESTMENT_ENABLED: bool = True  # Habilitar reinversión de ganancias
    REINVESTMENT_THRESHOLD: float = 0.5  # Changed from 1.0 to 0.5 By gregorbc@gmail.com
    CAPITAL_GROWTH_TARGET: float = 1.0  # Changed from 0.5 to 1.0 By gregorbc@gmail.com
    INITIAL_CAPITAL: float = 20.0  # Capital inicial (se actualizará con el real)
    CAPITAL_UPDATE_INTERVAL: int = 30  # Actualizar capital cada 30 ciclos

config = CONFIG()

# -------------------- STRATEGY OPTIMIZER CONFIG -------------------- #
@dataclass
class STRATEGY_OPTIMIZER:
    OPTIMIZATION_INTERVAL: int = 20
    MIN_TRADES_FOR_ANALYSIS: int = 6
    LEVERAGE_ADJUSTMENT_STEP: int = 5
    MAX_LEVERAGE: int = 100
    MIN_LEVERAGE: int = 5
    VOLATILITY_THRESHOLD: float = 2.2

strategy_optimizer = STRATEGY_OPTIMIZER()

# -------------------- CAPITAL MANAGER -------------------- #
class CapitalManager:
    """Gestor de capital real con reinversión de ganancias By gregorbc@gmail.com"""

    def __init__(self, api):
        self.api = api
        self.current_balance = 0.0
        self.initial_balance = 0.0
        self.last_balance_update = 0
        self.total_profit = 0.0
        self.reinvested_profit = 0.0

    def get_real_balance(self) -> float:
        """Obtener el balance real de la cuenta By gregorbc@gmail.com"""
        try:
            account_info = self.api._safe_api_call(self.api.client.futures_account)
            if account_info:
                # Buscar el balance de USDT
                usdt_balance = next(
                    (float(a.get('walletBalance', 0))
                     for a in account_info.get('assets', [])
                     if a.get('asset') == 'USDT'),
                    0.0
                )
                return usdt_balance
        except Exception as e:
            log.error(f"Error obteniendo balance real: {e} By gregorbc@gmail.com")
        return 0.0

    def update_balance(self, force: bool = False) -> bool:
        """Actualizar el balance real By gregorbc@gmail.com"""
        current_time = time.time()
        if force or (current_time - self.last_balance_update > 300):  # Actualizar cada 5 min
            new_balance = self.get_real_balance()
            if new_balance > 0:
                if self.current_balance == 0:
                    self.initial_balance = new_balance
                    log.info(f"💰 Capital inicial: {new_balance:.2f} USDT By gregorbc@gmail.com")

                self.current_balance = new_balance
                self.last_balance_update = current_time

                # Calcular profit total
                self.total_profit = self.current_balance - self.initial_balance

                # Guardar en base de datos
                self._save_balance_to_db()
                return True
        return False

    def _save_balance_to_db(self):
        """Guardar balance en base de datos By gregorbc@gmail.com"""
        if not DB_ENABLED:
            return

        try:
            db = SessionLocal()
            balance_record = AccountBalance(
                balance=self.current_balance,
                total_profit=self.total_profit,
                reinvested_profit=self.reinvested_profit
            )
            db.add(balance_record)
            db.commit()
        except Exception as e:
            log.error(f"Error guardando balance en DB: {e} By gregorbc@gmail.com")
        finally:
            if 'db' in locals():
                db.close()

    def should_reinvest(self, profit: float) -> bool:
        """Decidir si reinvertir las ganancias By gregorbc@gmail.com"""
        if not config.REINVESTMENT_ENABLED:
            return False

        # Reinvertir si la ganancia supera el threshold
        return profit >= config.REINVESTMENT_THRESHOLD

    def reinvest_profit(self, profit: float):
        """Reinvertir las ganancias en el capital By gregorbc@gmail.com"""
        if profit > 0 and self.should_reinvest(profit):
            self.reinvested_profit += profit
            log.info(f"🔄 Reinvirtiendo {profit:.2f} USDT en el capital By gregorbc@gmail.com")
            # El balance se actualizará automáticamente en el próximo ciclo

    def get_performance_stats(self) -> Dict:
        """Obtener estadísticas de rendimiento By gregorbc@gmail.com"""
        return {
            "current_balance": self.current_balance,
            "initial_balance": self.initial_balance,
            "total_profit": self.total_profit,
            "reinvested_profit": self.reinvested_profit,
            "profit_percentage": (self.total_profit / self.initial_balance * 100) if self.initial_balance > 0 else 0,
            "daily_target": config.CAPITAL_GROWTH_TARGET
        }

# -------------------- IA ENHANCEMENTS -------------------- #
@dataclass
class AIModel:
    """Modelo de IA para optimización de parámetros de trading By gregorbc@gmail.com"""
    learning_rate: float = config.AI_LEARNING_RATE
    exploration_rate: float = config.AI_EXPLORATION_RATE
    q_table: Dict = field(default_factory=dict)

    def get_action(self, state: str) -> Tuple[float, float]:
        """Obtiene la mejor acción (sl_adj, tp_adj) para un estado dado By gregorbc@gmail.com"""
        if state not in self.q_table or random.random() < self.exploration_rate:
            sl_adj = random.uniform(0.7, 1.3)
            tp_adj = random.uniform(0.8, 1.5)
            self.q_table[state] = (sl_adj, tp_adj, 0)
        return self.q_table[state][0], self.q_table[state][1]

    def update_model(self, state: str, reward: float, sl_adj: float, tp_adj: float):
        """Actualiza el modelo Q-learning con la recompensa obtenida By gregorbc@gmail.com"""
        if state in self.q_table:
            current_reward = self.q_table[state][2]
            new_reward = current_reward + self.learning_rate * (reward - current_reward)
            self.q_table[state] = (sl_adj, tp_adj, new_reward)

@dataclass
class MarketAnalyzer:
    """Analizador de condiciones del mercado By gregorbc@gmail.com"""
    volatility_threshold: float = config.AI_VOLATILITY_THRESHOLD
    trend_strength_threshold: float = config.AI_TREND_STRENGTH_THRESHOLD

    def analyze_market_conditions(self, symbol: str, df: pd.DataFrame) -> Dict[str, float]:
        """Analiza las condiciones del mercado para un símbolo By gregorbc@gmail.com"""
        if df is None or len(df) < 30:
            return {"volatility": 0, "trend_strength": 0, "market_regime": 0}

        # Calcular volatilidad (ATR porcentual)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]
        volatility = (atr / df['close'].iloc[-1]) * 100

        # Calcular fuerza de tendencia (ADX)
        positive_dm = df['high'].diff()
        negative_dm = df['low'].diff()
        positive_dm[positive_dm < 0] = 0
        negative_dm[negative_dm > 0] = 0

        tr14 = true_range.rolling(14).mean()
        plus_di14 = (positive_dm.rolling(14).mean() / tr14) * 100
        minus_di14 = (negative_dm.rolling(14).mean() / tr14) * 100
        dx = (np.abs(plus_di14 - minus_di14) / (plus_di14 + minus_di14)) * 100
        adx = dx.rolling(14).mean().iloc[-1]

        # Determinar régimen de mercado
        market_regime = 0
        if adx > self.trend_strength_threshold:
            if plus_di14.iloc[-1] > minus_di14.iloc[-1]:
                market_regime = 1
            else:
                market_regime = 2

        return {
            "volatility": volatility,
            "trend_strength": adx,
            "market_regime": market_regime
        }

# -------------------- PERFORMANCE ANALYZER -------------------- #
@dataclass
class PerformanceAnalyzer:
    """Analizador de rendimiento basado en datos históricos By gregorbc@gmail.com"""

    def __init__(self, db_session=None):
        self.db_session = db_session
        self.symbol_performance = {}
        self._load_performance_data()

    def _load_performance_data(self):
        """Cargar datos de rendimiento históricos By gregorbc@gmail.com"""
        try:
            if self.db_session:
                trades = self.db_session.query(Trade).all()
                for trade in trades:
                    symbol = trade.symbol
                    if symbol not in self.symbol_performance:
                        self.symbol_performance[symbol] = {
                            'total_trades': 0,
                            'winning_trades': 0,
                            'total_pnl': 0,
                            'avg_win': 0,
                            'avg_loss': 0
                        }

                    self.symbol_performance[symbol]['total_trades'] += 1
                    self.symbol_performance[symbol]['total_pnl'] += trade.pnl

                    if trade.pnl > 0:
                        self.symbol_performance[symbol]['winning_trades'] += 1
        except Exception as e:
            log.error(f"Error loading performance data: {e} By gregorbc@gmail.com")

    def get_symbol_risk_factor(self, symbol: str) -> float:
        """Calcular factor de riesgo para un símbolo basado en historial By gregorbc@gmail.com"""
        if symbol not in self.symbol_performance:
            return 1.0

        stats = self.symbol_performance[symbol]
        if stats['total_trades'] < 5:
            return 1.0

        win_rate = stats['winning_trades'] / stats['total_trades']
        avg_profit = stats['total_pnl'] / stats['total_trades']

        if win_rate < 0.4 or avg_profit < 0:
            return 0.5
        elif win_rate > 0.6 and avg_profit > 0:
            return 1.3

        return 1.0

# -------------------- TELEGRAM NOTIFIER -------------------- #
class TelegramNotifier:
    """Enviar notificaciones importantes por Telegram By gregorbc@gmail.com"""
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)

    def send_message(self, message: str):
        if not self.enabled:
            return

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            log.error(f"Error enviando mensaje por Telegram: {e} By gregorbc@gmail.com")

    def notify_trade_opened(self, symbol: str, side: str, quantity: float, price: float, balance: float):
        message = f"<b>🟢 Trade Abierto</b>\n\nSímbolo: {symbol}\nDirección: {side}\nCantidad: {quantity}\nPrecio: {price:.6f}\nCapital: {balance:.2f} USDT By gregorbc@gmail.com"
        self.send_message(message)

    def notify_trade_closed(self, symbol: str, pnl: float, reason: str, balance: float):
        emoji = "🟢" if pnl >= 0 else "🔴"
        message = f"<b>{emoji} Trade Cerrado</b>\n\nSímbolo: {symbol}\nP&L: {pnl:.2f} USDT\nRazón: {reason}\nCapital: {balance:.2f} USDT By gregorbc@gmail.com"
        self.send_message(message)

    def notify_balance_update(self, balance: float, profit: float, profit_percentage: float):
        message = f"<b>💰 Actualización de Capital</b>\n\nBalance: {balance:.2f} USDT\nProfit: {profit:+.2f} USDT\nRentabilidad: {profit_percentage:+.2f}% By gregorbc@gmail.com"
        self.send_message(message)

    def notify_reinvestment(self, amount: float, new_balance: float):
        message = f"<b>🔄 Reinversión de Ganancias</b>\n\nMonto: {amount:.2f} USDT\nNuevo Capital: {new_balance:.2f} USDT By gregorbc@gmail.com"
        self.send_message(message)

# -------------------- FLASK APP SETUP -------------------- #
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
CORS(app)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# -------------------- LOGGING SETUP -------------------- #
class SocketIOHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            level = record.levelname.lower()
            socketio.emit('log_update', {'message': log_entry, 'level': level})
        except Exception:
            pass

log = logging.getLogger("BinanceFuturesBot")
log.setLevel(getattr(logging, config.LOG_LEVEL))
if not log.handlers:
    formatter = logging.Formatter(config.LOG_FORMAT)

    os.makedirs('logs', exist_ok=True)
    file_handler = logging.FileHandler(f'logs/{config.LOG_FILE}', encoding='utf-8', mode='a')
    file_handler.setFormatter(formatter)

    socket_handler = SocketIOHandler()
    socket_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    log.addHandler(file_handler)
    log.addHandler(socket_handler)
    log.addHandler(console_handler)

for logger_name in ['binance', 'engineio', 'socketio', 'werkzeug', 'urllib3']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# -------------------- GLOBAL STATE -------------------- #
bot_thread = None
_trailing_monitor_thread = None
app_state = {
    "running": False,
    "status_message": "Stopped",
    "open_positions": {},
    "trailing_stop_data": {},
    "sl_tp_data": {},
    "config": asdict(config),
    "performance_stats": {
        "realized_pnl": 0.0,
        "trades_count": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "profit_factor": 0.0,
        "avg_trade_duration": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0
    },
    "balance": 0.0,
    "total_investment_usd": 0.0,
    "trades_history": [],
    "balance_history": [],
    "risk_metrics": {
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
        "profit_per_day": 0.0,
        "exposure_ratio": 0.0,
        "volatility": 0.0,
        "avg_position_duration": 0.0
    },
    "connection_metrics": {
        "api_retries": 0,
        "last_reconnect": None,
        "uptime": 0.0
    },
    "ai_metrics": {
        "q_table_size": 0,
        "last_learning_update": None,
        "exploration_rate": config.AI_EXPLORATION_RATE
    },
    "market_regime": "NEUTRAL",
    "daily_pnl": 0.0,
    "daily_starting_balance": 0.0,
    "capital_stats": {
        "current_balance": 0.0,
        "initial_balance": 0.0,
        "total_profit": 0.0,
        "reinvested_profit": 0.0,
        "profit_percentage": 0.0,
        "daily_target": config.CAPITAL_GROWTH_TARGET
    }
}
state_lock = threading.Lock()

# -------------------- BINANCE CLIENT -------------------- #
class BinanceFutures:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError("API keys not configured. Set BINANCE_API_KEY and BINANCE_API_SECRET environment variables By gregorbc@gmail.com")

        self.client = Client(api_key, api_secret, testnet=testnet)
        log.info(f"🔧 CONNECTED TO BINANCE FUTURES {'TESTNET' if testnet else 'MAINNET'} By gregorbc@gmail.com")

        try:
            self.exchange_info = self.client.futures_exchange_info()
            log.info("✅ Exchange information loaded successfully By gregorbc@gmail.com")
        except Exception as e:
            log.error(f"❌ Error connecting to Binance: {e} By gregorbc@gmail.com")
            raise

    def ensure_symbol_settings(self, symbol: str):
        try:
            _ = self._safe_api_call(self.client.futures_change_leverage, symbol=symbol, leverage=int(config.LEVERAGE))
        except Exception as e:
            log.warning(f"Leverage set issue for {symbol}: {e} By gregorbc@gmail.com")

        try:
            self.client.futures_change_margin_type(symbol=symbol, marginType=config.MARGIN_TYPE)
        except BinanceAPIException as e:
            if e.code == -4046 or "No need to change margin type" in e.message:
                pass
            else:
                log.warning(f"Margin type set warning for {symbol}: {e} By gregorbc@gmail.com")
        except Exception as e:
            log.error(f"An unexpected error occurred setting margin type for {symbol}: {e} By gregorbc@gmail.com")

    def _safe_api_call(self, func, *args, **kwargs):
        for attempt in range(config.MAX_API_RETRIES):
            try:
                time.sleep(config.API_RETRY_DELAY * (2 ** attempt))
                result = func(*args, **kwargs)

                with state_lock:
                    app_state["connection_metrics"]["api_retries"] = 0

                return result
            except BinanceAPIException as e:
                with state_lock:
                    app_state["connection_metrics"]["api_retries"] += 1

                if e.code == -4131:
                    log.warning("PERCENT_PRICE error (-4131) in order. Volatile or illiquid market. Skipping. By gregorbc@gmail.com")
                    return None
                elif e.code in [-2011, -2021]:
                    log.warning(f"API order error ({e.code}): {e.message} By gregorbc@gmail.com")
                else:
                    log.warning(f"API non-critical error: {e.code} - {e.message} By gregorbc@gmail.com")
                    if attempt == config.MAX_API_RETRIES - 1:
                        log.error(f"Final API error after all retries: {e.code} - {e.message} By gregorbc@gmail.com")
            except Exception as e:
                with state_lock:
                    app_state["connection_metrics"]["api_retries"] += 1
                log.warning(f"General API call error: {e} By gregorbc@gmail.com")
                if attempt == config.MAX_API_RETRIES - 1:
                    log.error(f"Final general error after all retries: {e} By gregorbc@gmail.com")

        return None

    def smart_retry_api_call(self, func, *args, **kwargs):
        """Llamada a API con reintentos inteligentes basados en el tipo de error By gregorbc@gmail.com"""
        retry_delays = [1, 2, 4, 8, 16]
        last_exception = None

        for attempt, delay in enumerate(retry_delays):
            try:
                result = func(*args, **kwargs)

                if attempt > 0:
                    log.info(f"✅ Reintento exitoso después de {attempt} intentos By gregorbc@gmail.com")

                return result
            except BinanceAPIException as e:
                last_exception = e

                if e.code in [-1013, -2010, -2011]:
                    log.error(f"Error no recuperable: {e.message} (código: {e.code}) By gregorbc@gmail.com")
                    break

                log.warning(f"Reintentando en {delay}s (intento {attempt + 1}/{len(retry_delays)}) By gregorbc@gmail.com")
                time.sleep(delay)

            except Exception as e:
                last_exception = e
                log.warning(f"Error general, reintentando en {delay}s (intento {attempt + 1}/{len(retry_delays)}) By gregorbc@gmail.com")
                time.sleep(delay)

        log.error(f"❌ Todos los reintentos fallaron: {last_exception} By gregorbc@gmail.com")
        return None

    def get_symbol_filters(self, symbol: str) -> Optional[Dict[str, float]]:
        s_info = next((s for s in self.exchange_info['symbols'] if s['symbol'] == symbol), None)
        if not s_info:
            return None

        filters = {f['filterType']: f for f in s_info['filters']}
        return {
            "stepSize": float(filters['LOT_SIZE']['stepSize']),
            "minQty": float(filters['LOT_SIZE']['minQty']),
            "tickSize": float(filters['PRICE_FILTER']['tickSize']),
            "minNotional": float(filters.get('MIN_NOTIONAL', {}).get('notional', 5.0))
        }

    def place_order(self, symbol: str, side: str, order_type: str, quantity: float,
                   price: Optional[float] = None, reduce_only: bool = False) -> Optional[Dict]:
        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'quantity': quantity
        }

        if order_type == FUTURE_ORDER_TYPE_LIMIT:
            if price is None:
                log.error("Price required for LIMIT orders. By gregorbc@gmail.com")
                return None
            params.update({
                'price': str(price),
                'timeInForce': TIME_IN_FORCE_GTC
            })

        if reduce_only:
            params['reduceOnly'] = 'true'

        if config.DRY_RUN:
            log.info(f"[DRY_RUN] place_order: {params} By gregorbc@gmail.com")
            return {'mock': True, 'orderId': int(time.time() * 1000)}

        return self.smart_retry_api_call(self.client.futures_create_order, **params)

    def close_position(self, symbol: str, position_amt: float) -> Optional[Dict]:
        side = SIDE_SELL if position_amt > 0 else SIDE_BUY
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] close_position {symbol} {position_amt} By gregorbc@gmail.com")
            return {'mock': True, 'orderId': int(time.time() * 1000)}
        return self.place_order(symbol, side, FUTURE_ORDER_TYPE_MARKET, abs(position_amt), reduce_only=True)

    def cancel_order(self, symbol: str, orderId: int) -> Optional[Dict]:
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] cancel_order: {orderId} for {symbol} By gregorbc@gmail.com")
            return {'mock': True}

        try:
            return self.smart_retry_api_call(self.client.futures_cancel_order, symbol=symbol, orderId=orderId)
        except Exception as e:
            log.warning(f"Could not cancel order {orderId} for {symbol}: {e} By gregorbc@gmail.com")
            return None

    @staticmethod
    def round_value(value: float, step: float) -> float:
        if step == 0:
            return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)

# -------------------- TRADING BOT WITH REAL CAPITAL MANAGEMENT -------------------- #
class TradingBot:
    def __init__(self):
        self.api = BinanceFutures()
        self.capital_manager = CapitalManager(self.api)
        self.recently_signaled = set()
        self.cycle_count = 0
        self.start_time = time.time()
        self.ai_model = AIModel()
        self.market_analyzer = MarketAnalyzer()
        self.signal_strength = {}
        self.market_regime = "NEUTRAL"
        self.telegram_notifier = TelegramNotifier()

        self.performance_analyzer = PerformanceAnalyzer(SessionLocal() if DB_ENABLED else None)
        self.daily_pnl = 0.0
        self.daily_starting_balance = 0.0
        self.today = datetime.now().date()

    def get_top_symbols(self) -> List[str]:
        tickers = self.api._safe_api_call(self.api.client.futures_ticker)
        if not tickers:
            return []

        valid_tickers = [
            t for t in tickers
            if t['symbol'].endswith('USDT')
            and t['symbol'] not in config.EXCLUDE_SYMBOLS
            and t['symbol'] not in config.BLACKLIST_SYMBOLS
            and float(t['quoteVolume']) > config.MIN_24H_VOLUME
        ]

        # Para cuentas pequeñas, priorizar símbolos con precios bajos
        suitable_symbols = []
        for t in valid_tickers:
            symbol = t['symbol']
            price = float(t['lastPrice'])

            filters = self.api.get_symbol_filters(symbol)
            if not filters:
                continue

            min_notional = max(filters.get('minNotional', 5.0), config.MIN_NOTIONAL_OVERRIDE)
            min_qty = filters['minQty']

            min_order_value = min_qty * price
            if min_order_value < min_notional:
                min_order_value = min_notional

            if min_order_value <= self.capital_manager.current_balance:
                suitable_symbols.append(t)

        suitable_symbols.sort(key=lambda x: (float(x['quoteVolume']), float(x['lastPrice'])), reverse=True)

        return [t['symbol'] for t in suitable_symbols[:config.NUM_SYMBOLS_TO_SCAN]]

    def get_klines_for_symbol(self, symbol: str, interval: str = None, limit: int = None) -> Optional[pd.DataFrame]:
        klines = self.api._safe_api_call(
            self.api.client.futures_klines,
            symbol=symbol,
            interval=interval or config.TIMEFRAME,
            limit=limit or config.CANDLES_LIMIT
        )
        if not klines: return None
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=['close'], inplace=True)
        df['symbol'] = symbol
        return df

    def calculate_indicators(self, df: pd.DataFrame):
        # EMAs By gregorbc@gmail.com
        df['fast_ema'] = df['close'].ewm(span=config.FAST_EMA, adjust=False).mean()
        df['slow_ema'] = df['close'].ewm(span=config.SLOW_EMA, adjust=False).mean()

        # RSI By gregorbc@gmail.com
        delta = df['close'].diff()
        up, down = delta.copy(), delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0
        roll_up = up.ewm(span=config.RSI_PERIOD, adjust=False).mean()
        roll_down = down.abs().ewm(span=config.RSI_PERIOD, adjust=False).mean()
        rs = roll_up / roll_down.replace(0, np.nan)
        df['rsi'] = 100.0 - (100.0 / (1.0 + rs)).fillna(50)

        # MACD By gregorbc@gmail.com
        exp1 = df['close'].ewm(span=config.MACD_FAST, adjust=False).mean()
        exp2 = df['close'].ewm(span=config.MACD_SLOW, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=config.MACD_SIGNAL, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # Stochastic RSI By gregorbc@gmail.com
        stoch_rsi = (df['rsi'] - df['rsi'].rolling(config.STOCH_PERIOD).min()) / (df['rsi'].rolling(config.STOCH_PERIOD).max() - df['rsi'].rolling(config.STOCH_PERIOD).min())
        df['stoch_rsi'] = stoch_rsi * 100

        # Bollinger Bands By gregorbc@gmail.com
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        Calcula el ADX (Average Directional Index) usando la librería TA-Lib para mayor precisión.
        By gregorbc@gmail.com
        """
        if len(df) < period * 2:
            return 0.0 # Devuelve 0 si no hay suficientes datos

        try:
            # Asegurarse de que los datos son del tipo correcto (numpy arrays de tipo float)
            high = df['high'].astype(float).to_numpy()
            low = df['low'].astype(float).to_numpy()
            close = df['close'].astype(float).to_numpy()

            # Llamar a la función ADX de TA-Lib
            adx_values = talib.ADX(high, low, close, timeperiod=period)

            # El último valor puede be NaN (Not a Number), así que lo manejamos
            last_adx = adx_values[-1]
            return last_adx if not np.isnan(last_adx) else 0.0

        except Exception as e:
            # Captura cualquier error durante el cálculo y lo registra
            symbol = df['symbol'].iloc[-1] if 'symbol' in df.columns else 'UNKNOWN'
            log.error(f"Error calculando ADX para {symbol} con talib: {e} By gregorbc@gmail.com")
            return 0.0 # Devuelve 0 en caso de error para evitar tomar decisiones incorrectas

    def calculate_signal_strength(self, df: pd.DataFrame, signal: str, symbol: str) -> float:
        """Calcula la fuerza de la señal basada en múltiples factores By gregorbc@gmail.com"""
        if len(df) < 30:
            return 0.4

        volume_avg = df['volume'].rolling(20).mean().iloc[-1]
        volume_ratio = min(2.0, df['volume'].iloc[-1] / volume_avg) if volume_avg > 0 else 1

        rsi_strength = abs(df['rsi'].iloc[-1] - 50) / 50

        ema_distance = abs(df['fast_ema'].iloc[-1] - df['slow_ema'].iloc[-1])
        price_distance = ema_distance / df['close'].iloc[-1] if df['close'].iloc[-1] > 0 else 0

        macd_strength = 0.5
        if signal == "LONG" and df['macd'].iloc[-1] > df['macd_signal'].iloc[-1]:
            macd_strength = 0.8
        elif signal == "SHORT" and df['macd'].iloc[-1] < df['macd_signal'].iloc[-1]:
            macd_strength = 0.8

        bb_position = (df['close'].iloc[-1] - df['bb_lower'].iloc[-1]) / (df['bb_upper'].iloc[-1] - df['bb_lower'].iloc[-1])
        bb_strength = 0.5
        if signal == "LONG" and bb_position < 0.2:
            bb_strength = 0.8
        elif signal == "SHORT" and bb_position > 0.8:
            bb_strength = 0.8

        market_conditions = self.market_analyzer.analyze_market_conditions(symbol, df)
        trend_alignment = 0.5
        if market_conditions["market_regime"] == 1 and signal == "LONG":
            trend_alignment = 0.9
        elif market_conditions["market_regime"] == 2 and signal == "SHORT":
            trend_alignment = 0.9
        elif (market_conditions["market_regime"] == 1 and signal == "SHORT") or \
             (market_conditions["market_regime"] == 2 and signal == "LONG"):
            trend_alignment = 0.2

        regime_factor = 1.0
        if self.market_regime == "BULL" and signal == "LONG":
            regime_factor = 1.2
        elif self.market_regime == "BEAR" and signal == "SHORT":
            regime_factor = 1.2
        elif (self.market_regime == "BULL" and signal == "SHORT") or \
             (self.market_regime == "BEAR" and signal == "LONG"):
            regime_factor = 0.7

        strength = (volume_ratio * 0.15 +
                   rsi_strength * 0.20 +
                   price_distance * 0.20 +
                   macd_strength * 0.15 +
                   bb_strength * 0.10 +
                   trend_alignment * 0.20) * regime_factor

        return max(0.1, min(0.95, strength))

    def check_signal(self, df: pd.DataFrame, symbol: str) -> Optional[str]:
        if len(df) < 2: return None
        last, prev = df.iloc[-1], df.iloc[-2]

        adx = self.calculate_adx(df)
        # Changed ADX threshold from 20 to 15 By gregorbc@gmail.com
        if adx < 15:  # Changed from 20 to 15
            log.info(f"↔️ Mercado lateral detectado para {symbol} (ADX: {adx:.1f}), evitando señales By gregorbc@gmail.com")
            return None

        ema_cross = False
        if last['fast_ema'] > last['slow_ema'] and prev['fast_ema'] <= prev['slow_ema']:
            signal = 'LONG'
            ema_cross = True
        elif last['fast_ema'] < last['slow_ema'] and prev['fast_ema'] >= prev['slow_ema']:
            signal = 'SHORT'
            ema_cross = True

        if not ema_cross:
            return None

        rsi_confirm = (signal == 'LONG' and last['rsi'] > 48 and last['rsi'] < 70) or \
                     (signal == 'SHORT' and last['rsi'] < 52 and last['rsi'] > 30)

        macd_confirm = (signal == 'LONG' and last['macd'] > last['macd_signal']) or \
                      (signal == 'SHORT' and last['macd'] < last['macd_signal'])

        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        trend_confirm = (signal == 'LONG' and last['close'] > ema50) or \
                       (signal == 'SHORT' and last['close'] < ema50)

        confirmations = sum([rsi_confirm, macd_confirm, trend_confirm])
        if confirmations < 2:
            return None

        if config.VOLUME_WEIGHTED_SIGNALS:
            volume_avg = df['volume'].rolling(20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / volume_avg if volume_avg > 0 else 1

            if volume_ratio < config.MIN_VOLUME_CONFIRMATION:
                log.info(f"📉 Señal {signal} descartada por volumen insuficiente: {volume_ratio:.2f} By gregorbc@gmail.com")
                return None

        if config.HIGHER_TIMEFRAME_CONFIRMATION:
            try:
                df_higher = self.get_klines_for_symbol(symbol, interval=config.HIGHER_TIMEFRAME, limit=50)
                if df_higher is not None and len(df_higher) > 20:
                    self.calculate_indicators(df_higher)
                    higher_tf_signal = None
                    last_higher = df_higher.iloc[-1]
                    prev_higher = df_higher.iloc[-2]

                    if last_higher['fast_ema'] > last_higher['slow_ema'] and prev_higher['fast_ema'] <= prev_higher['slow_ema']:
                        higher_tf_signal = 'LONG'
                    elif last_higher['fast_ema'] < last_higher['slow_ema'] and prev_higher['fast_ema'] >= prev_higher['slow_ema']:
                        higher_tf_signal = 'SHORT'

                    if higher_tf_signal != signal:
                        log.info(f"⏭️ Señal {signal} en {symbol} descartada por falta de alineación con TF superior ({higher_tf_signal}) By gregorbc@gmail.com")
                        return None
            except Exception as e:
                log.error(f"Error verificando TF superior para {symbol}: {e} By gregorbc@gmail.com")

        if config.BTC_CORRELATION_FILTER and symbol != "BTCUSDT":
            btc_df = self.get_klines_for_symbol("BTCUSDT", interval=config.TIMEFRAME, limit=50)
            if btc_df is not None and len(btc_df) > 20:
                self.calculate_indicators(btc_df)
                btc_signal = None
                last_btc = btc_df.iloc[-1]
                prev_btc = btc_df.iloc[-2]

                if last_btc['fast_ema'] > last_btc['slow_ema'] and prev_btc['fast_ema'] <= prev_btc['slow_ema']:
                    btc_signal = 'LONG'
                elif last_btc['fast_ema'] < last_btc['slow_ema'] and prev_btc['fast_ema'] >= prev_btc['slow_ema']:
                    btc_signal = 'SHORT'

                if btc_signal and btc_signal != signal:
                    strength = self.calculate_signal_strength(df, signal, symbol) # Recalculate strength before reducing
                    strength *= 0.6
                    log.info(f"⚠️ Señal {signal} en {symbol} con señal contraria en BTC, fuerza reducida a {strength:.2f} By gregorbc@gmail.com")

        strength = self.calculate_signal_strength(df, signal, symbol)
        self.signal_strength[symbol] = strength

        if strength < config.MIN_SIGNAL_STRENGTH:
            log.info(f"📉 Señal {signal} descartada por fuerza insuficiente: {strength:.2f} By gregorbc@gmail.com")
            return None

        log.info(f"📶 Señal {signal} con fuerza: {strength:.2f}, confirmaciones: {confirmations}/3 By gregorbc@gmail.com")
        return signal

    def get_ai_adjustments(self, symbol: str, performance_data: Dict) -> Tuple[float, float]:
        """Obtiene ajustes de SL/TP de la IA By gregorbc@gmail.com"""
        market_conditions = self.market_analyzer.analyze_market_conditions(symbol, self.get_klines_for_symbol(symbol))

        volatility_state = "HIGH" if market_conditions["volatility"] > self.market_analyzer.volatility_threshold else "LOW"
        trend_state = "TREND" if market_conditions["trend_strength"] > 25 else "RANGE"
        market_state = "BULL" if self.market_regime == "BULL" else "BEAR" if self.market_regime == "BEAR" else "NEUTRAL"

        state_key = f"{volatility_state}_{trend_state}_{market_state}"

        if performance_data:
            win_rate = performance_data.get('win_rate', 0.5)
            profit_factor = performance_data.get('profit_factor', 1.0)
            state_key += f"_WR{int(win_rate*100)}_PF{profit_factor:.1f}"

        sl_adj, tp_adj = self.ai_model.get_action(state_key)
        return sl_adj, tp_adj

    def update_ai_model(self, symbol: str, trade_result: float, sl_adj: float, tp_adj: float, exit_reason: str):
        """Actualiza el modelo de IA con el resultado de la operación By gregorbc@gmail.com"""
        try:
            df = self.get_klines_for_symbol(symbol)
            if df is None or len(df) < 30:
                return

            market_conditions = self.market_analyzer.analyze_market_conditions(symbol, df)
            volatility_state = "HIGH" if market_conditions["volatility"] > self.market_analyzer.volatility_threshold else "LOW"
            trend_state = "TREND" if market_conditions["trend_strength"] > 25 else "RANGE"
            market_state = "BULL" if self.market_regime == "BULL" else "BEAR" if self.market_regime == "BEAR" else "NEUTRAL"

            state_key = f"{volatility_state}_{trend_state}_{market_state}_EXIT_{exit_reason}"

            if trade_result > 0:
                reward = min(2.0, trade_result / (abs(trade_result) + 1.0))
            else:
                reward = max(-1.5, trade_result / (abs(trade_result) + 1.0))

            self.ai_model.update_model(state_key, reward, sl_adj, tp_adj)

            with state_lock:
                app_state["ai_metrics"]["q_table_size"] = len(self.ai_model.q_table)
                app_state["ai_metrics"]["last_learning_update"] = datetime.now().isoformat()
                app_state["ai_metrics"]["exploration_rate"] = self.ai_model.exploration_rate
        except Exception as e:
            log.error(f"Error updating AI model for {symbol}: {e} By gregorbc@gmail.com")

    def check_trailing_stop(self, symbol: str, position: Dict, current_price: float):
        with state_lock:
            position_side = 'LONG' if float(position['positionAmt']) > 0 else 'SHORT'
            entry_price = float(position['entryPrice'])

            trailing_adjustment = 1.0
            if config.AI_TRAILING_ADJUSTMENT and DB_ENABLED:
                performance_data = self.analyze_trading_performance(symbol)
                if performance_data:
                    volatility_factor = performance_data.get('market_volatility', 1.0) * config.AI_VOLATILITY_FACTOR
                    trailing_adjustment = max(0.7, min(1.5, volatility_factor))
                    if trailing_adjustment != 1.0:
                        log.info(f"🤖 AI Trailing Adjustment for {symbol}: {trailing_adjustment:.2f} (Volatility: {performance_data.get('market_volatility', 0):.2f}%) By gregorbc@gmail.com")

            trailing_data = app_state["trailing_stop_data"].get(symbol)

            if not trailing_data:
                app_state["trailing_stop_data"][symbol] = {
                    'activated': False,
                    'best_price': entry_price,
                    'current_stop': entry_price,
                    'side': position_side,
                    'last_stop_price': 0.0,
                    'stop_order_id': None,
                    'trailing_adjustment': trailing_adjustment
                }
                trailing_data = app_state["trailing_stop_data"][symbol]
            else:
                trailing_data['trailing_adjustment'] = trailing_adjustment

            activation_percent = config.TRAILING_STOP_ACTIVATION * trailing_data['trailing_adjustment']
            stop_percentage = config.TRAILING_STOP_PERCENTAGE * trailing_data['trailing_adjustment']

            should_close = False

            if position_side == 'LONG':
                if current_price > trailing_data['best_price']:
                    trailing_data['best_price'] = current_price
                profit_percentage = ((current_price - entry_price) / entry_price) * 100
                if not trailing_data['activated'] and profit_percentage >= activation_percent:
                    trailing_data['activated'] = True
                    log.info(f"🔔 Trailing stop activado para {symbol} (adj: {trailing_data['trailing_adjustment']:.2f}) By gregorbc@gmail.com")
                if trailing_data['activated']:
                    new_stop = trailing_data['best_price'] * (1 - stop_percentage / 100)
                    if new_stop > trailing_data['current_stop']:
                        trailing_data['current_stop'] = new_stop
                    if current_price <= trailing_data['current_stop']:
                        log.info(f"🔴 Cierre por trailing stop: {symbol} @ {current_price} (Stop: {trailing_data['current_stop']}) By gregorbc@gmail.com")
                        should_close = True
            else:
                if current_price < trailing_data['best_price']:
                    trailing_data['best_price'] = current_price
                profit_percentage = ((entry_price - current_price) / entry_price) * 100
                if not trailing_data['activated'] and profit_percentage >= activation_percent:
                    trailing_data['activated'] = True
                    log.info(f"🔔 Trailing stop activado para {symbol} (adj: {trailing_data['trailing_adjustment']:.2f}) By gregorbc@gmail.com")
                if trailing_data['activated']:
                    new_stop = trailing_data['best_price'] * (1 + stop_percentage / 100)
                    if new_stop < trailing_data['current_stop']:
                        trailing_data['current_stop'] = new_stop
                    if current_price >= trailing_data['current_stop']:
                        log.info(f"🔴 Cierre por trailing stop: {symbol} @ {current_price} (Stop: {trailing_data['current_stop']}) By gregorbc@gmail.com")
                        should_close = True

            return should_close

    def check_fixed_sl_tp(self, symbol: str, position: Dict, current_price: float):
        if not config.USE_FIXED_SL_TP:
            return False

        with state_lock:
            sl_tp_data = app_state["sl_tp_data"].get(symbol, {})
            position_side = 'LONG' if float(position['positionAmt']) > 0 else 'SHORT'
            entry_price = float(position['entryPrice'])

            sl_adjustment, tp_adjustment = 1.0, 1.0

            if (config.AI_SL_ADJUSTMENT or config.AI_TP_ADJUSTMENT) and DB_ENABLED:
                performance_data = self.analyze_trading_performance(symbol)
                if performance_data:
                    sl_adj, tp_adj = self.get_ai_adjustments(symbol, performance_data)

                    if config.AI_SL_ADJUSTMENT:
                        sl_adjustment = max(0.5, min(2.0, sl_adj))
                    if config.AI_TP_ADJUSTMENT:
                        tp_adjustment = max(0.7, min(1.5, tp_adj))

                    if sl_adjustment != 1.0 or tp_adjustment != 1.0:
                        log.info(f"🤖 AI SL/TP Adjustment for {symbol}: SL={sl_adjustment:.2f}, TP={tp_adjustment:.2f} By gregorbc@gmail.com")

            if 'sl_price' not in sl_tp_data:
                if position_side == 'LONG':
                    sl_price = entry_price * (1 - (config.STOP_LOSS_PERCENT * sl_adjustment) / 100)
                    tp_price = entry_price * (1 + (config.TAKE_PROFIT_PERCENT * tp_adjustment) / 100)
                else:
                    sl_price = entry_price * (1 + (config.STOP_LOSS_PERCENT * sl_adjustment) / 100)
                    tp_price = entry_price * (1 - (config.TAKE_PROFIT_PERCENT * tp_adjustment) / 100)

                app_state["sl_tp_data"][symbol] = {
                    'sl_price': sl_price, 'tp_price': tp_price, 'side': position_side,
                    'entry_price': entry_price, 'sl_adjustment': sl_adjustment, 'tp_adjustment': tp_adjustment
                }
                sl_tp_data = app_state["sl_tp_data"][symbol]
                log.info(f"Initialized SL/TP for {symbol}: SL @ {sl_price:.4f} (adj: {sl_adjustment:.2f}), TP @ {tp_price:.4f} (adj: {tp_adjustment:.2f}) By gregorbc@gmail.com")

            sl_price = sl_tp_data.get('sl_price')
            tp_price = sl_tp_data.get('tp_price')

            if not sl_price or not tp_price:
                return False

            if position_side == 'LONG':
                if current_price <= sl_price:
                    log.info(f"🔴 Cierre por STOP LOSS: {symbol} @ {current_price} (SL: {sl_price}) By gregorbc@gmail.com")
                    return 'SL'
                elif current_price >= tp_price:
                    log.info(f"🟢 Cierre por TAKE PROFIT: {symbol} @ {current_price} (TP: {tp_price}) By gregorbc@gmail.com")
                    return 'TP'
            else:
                if current_price >= sl_price:
                    log.info(f"🔴 Cierre por STOP LOSS: {symbol} @ {current_price} (SL: {sl_price}) By gregorbc@gmail.com")
                    return 'SL'
                elif current_price <= tp_price:
                    log.info(f"🟢 Cierre por TAKE PROFIT: {symbol} @ {current_price} (TP: {tp_price}) By gregorbc@gmail.com")
                    return 'TP'
            return False

    def check_time_based_exit(self, symbol: str, position: Dict) -> bool:
        """Check if position should be closed based on holding time By gregorbc@gmail.com"""
        update_time = position.get('updateTime', 0)
        if update_time == 0:
            return False

        hours_held = (time.time() * 1000 - update_time) / (1000 * 60 * 60)
        if hours_held > config.MAX_POSITION_HOLD_HOURS:
            log.info(f"⏰ Cierre por tiempo: {symbol} held for {hours_held:.1f} hours By gregorbc@gmail.com")
            return True
        return False

    def check_momentum_reversal(self, symbol: str, position: Dict, df: pd.DataFrame) -> bool:
        """Check if momentum has reversed against the position By gregorbc@gmail.com"""
        if df is None or len(df) < 10 or 'rsi' not in df.columns:
            return False

        position_side = 'LONG' if float(position['positionAmt']) > 0 else 'SHORT'
        current_rsi = df['rsi'].iloc[-1]
        prev_rsi = df['rsi'].iloc[-2]

        if position_side == 'LONG':
            price_trend = df['close'].iloc[-1] > df['close'].iloc[-3]
            rsi_trend = current_rsi < prev_rsi
            if price_trend and rsi_trend and current_rsi > 70:
                log.info(f"↘️ Cierre por divergencia RSI bajista: {symbol} By gregorbc@gmail.com")
                return True
        else:
            price_trend = df['close'].iloc[-1] < df['close'].iloc[-3]
            rsi_trend = current_rsi > prev_rsi
            if price_trend and rsi_trend and current_rsi < 30:
                log.info(f"↗️ Cierre por divergencia RSI alcista: {symbol} By gregorbc@gmail.com")
                return True

        return False

    def dynamic_exit_strategy(self, symbol: str, position: Dict, current_price: float, df: pd.DataFrame) -> Optional[str]:
        """Combine multiple exit strategies for better performance By gregorbc@gmail.com"""
        if df is not None and not df.empty and 'rsi' not in df.columns:
            self.calculate_indicators(df)

        sl_tp_signal = self.check_fixed_sl_tp(symbol, position, current_price)
        if sl_tp_signal:
            return sl_tp_signal

        trailing_stop_signal = self.check_trailing_stop(symbol, position, current_price)
        if trailing_stop_signal:
            return 'TRAILING'

        time_exit = self.check_time_based_exit(symbol, position)
        if time_exit:
            return 'TIME_EXIT'

        momentum_exit = self.check_momentum_reversal(symbol, position, df)
        if momentum_exit:
            return 'MOMENTUM_EXIT'

        return None

    def check_balance_risk(self, account_info):
        if not account_info: return False

        # Usar balance real del capital manager
        current_balance = self.capital_manager.current_balance

        if current_balance < config.MIN_BALANCE_THRESHOLD:
            log.warning(f"⚠️ Balance bajo: {current_balance:.2f} USDT (mínimo: {config.MIN_BALANCE_THRESHOLD} USDT) By gregorbc@gmail.com")
            return True

        open_positions = {p['symbol']: p for p in account_info['positions'] if float(p['positionAmt']) != 0}
        total_investment = sum(float(p.get('initialMargin', 0) or 0) for p in open_positions.values())
        exposure_ratio = total_investment / current_balance if current_balance > 0 else 0

        if exposure_ratio > 0.8:
            log.warning(f"⚠️ Exposición demasiado alta: {exposure_ratio:.2%} By gregorbc@gmail.com")
        
        with state_lock:
            app_state["risk_metrics"]["exposure_ratio"] = exposure_ratio
            if app_state["balance_history"]:
                peak = max(app_state["balance_history"])
                drawdown = (peak - current_balance) / peak * 100 if peak > 0 else 0
                app_state["risk_metrics"]["max_drawdown"] = max(app_state["risk_metrics"]["max_drawdown"], drawdown)

                if drawdown > config.MAX_DRAWDOWN_PERCENT:
                    log.warning(f"⛔ Drawdown máximo excedido: {drawdown:.2f}% By gregorbc@gmail.com")
                    return True

            app_state["balance_history"].append(current_balance)
            if len(app_state["balance_history"]) > 100:
                app_state["balance_history"].pop(0)

        return False

    def detect_market_regime(self) -> str:
        """Detect overall market regime to adjust trading strategy By gregorbc@gmail.com"""
        btc_df = self.get_klines_for_symbol("BTCUSDT")
        if btc_df is None or len(btc_df) < 100:
            return "NEUTRAL"

        trends = []
        for timeframe in ['1h', '4h', '1d']:
            df = self.api._safe_api_call(
                self.api.client.futures_klines,
                symbol="BTCUSDT",
                interval=timeframe,
                limit=50
            )
            if df:
                df = pd.DataFrame(df, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
                for col in ['open', 'high', 'low', 'close']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

                ma20 = df['close'].rolling(20).mean().iloc[-1]
                ma50 = df['close'].rolling(50).mean().iloc[-1]
                trends.append(1 if ma20 > ma50 else -1)

        if sum(trends) >= 2:
            return "BULL"
        elif sum(trends) <= -2:
            return "BEAR"
        else:
            return "NEUTRAL"

    def calculate_position_size(self, symbol: str, price: float) -> float:
        """
        Calculate position size based on real capital
        By gregorbc@gmail.com
        """
        # Usar balance real del capital manager
        current_balance = self.capital_manager.current_balance

        if current_balance <= 0:
            return 0

        risk_amount = current_balance * (config.RISK_PER_TRADE_PERCENT / 100)

        risk_factor = self.performance_analyzer.get_symbol_risk_factor(symbol)

        symbol_settings = config.SYMBOL_SPECIFIC_SETTINGS.get(symbol, {})
        symbol_risk_multiplier = symbol_settings.get('risk_multiplier', 1.0)

        adjusted_risk_amount = risk_amount * risk_factor * symbol_risk_multiplier

        sl_distance = price * (config.STOP_LOSS_PERCENT / 100)
        if sl_distance <= 0:
            return 0

        position_size = adjusted_risk_amount / sl_distance

        max_leverage = symbol_settings.get('max_leverage', config.LEVERAGE)
        leverage = min(config.LEVERAGE, max_leverage)
        position_size = position_size * leverage / config.LEVERAGE

        df = self.get_klines_for_symbol(symbol)

        if df is not None and not df.empty and len(df) > 20:
            returns = np.log(df['close'] / df['close'].shift(1))
            volatility = returns.std() * np.sqrt(365)

            volatility_factor = 1.0 / (1.0 + volatility * 8)
            position_size *= volatility_factor

            log.info(f"📊 Volatilidad {symbol}: {volatility:.4f}, Factor: {volatility_factor:.2f} By gregorbc@gmail.com")

        filters = self.api.get_symbol_filters(symbol)
        if filters:
            min_qty = filters['minQty']
            min_notional = max(filters.get('minNotional', 5.0), config.MIN_NOTIONAL_OVERRIDE)

            if position_size < min_qty:
                position_size = min_qty

            notional_value = position_size * price
            if notional_value < min_notional:
                min_position_size = min_notional / price
                if min_position_size < min_qty:
                    return 0
                position_size = min_position_size

            max_position_size = (current_balance * leverage) / price
            position_size = min(position_size, max_position_size)

        return max(position_size, 0)

    def analyze_trading_performance(self, symbol: str):
        if not DB_ENABLED: return None
        try:
            db = SessionLocal()
            recent_trades = db.query(Trade).filter(
                Trade.symbol == symbol,
                Trade.timestamp >= datetime.now() - timedelta(hours=strategy_optimizer.OPTIMIZATION_INTERVAL)
            ).all()

            if len(recent_trades) < strategy_optimizer.MIN_TRADES_FOR_ANALYSIS:
                return None

            winning_trades = [t for t in recent_trades if t.pnl > 0]
            losing_trades = [t for t in recent_trades if t.pnl < 0]
            win_rate = len(winning_trades) / len(recent_trades) if recent_trades else 0
            avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = abs(sum(t.pnl for t in losing_trades) / len(losing_trades)) if losing_trades else 0

            total_win_pnl = avg_win * len(winning_trades)
            total_loss_pnl = abs(avg_loss * len(losing_trades))
            profit_factor = total_win_pnl / total_loss_pnl if total_loss_pnl > 0 else total_win_pnl

            trade_durations = [t.duration for t in recent_trades if t.duration is not None]
            avg_trade_duration = sum(trade_durations) / len(trade_durations) if trade_durations else 0

            klines = self.get_klines_for_symbol(symbol)
            atr = 0
            if klines is not None:
                high_low = klines['high'] - klines['low']
                high_close = abs(klines['high'] - klines['close'].shift())
                low_close = abs(klines['low'] - klines['close'].shift())
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.rolling(14).mean().iloc[-1] / klines['close'].iloc[-1] * 100

            recommended_leverage = config.LEVERAGE
            if win_rate > 0.7 and profit_factor > 2.0:
                recommended_leverage = min(config.LEVERAGE + strategy_optimizer.LEVERAGE_ADJUSTMENT_STEP, strategy_optimizer.MAX_LEVERAGE)
            elif win_rate < 0.3 or profit_factor < 1.0:
                recommended_leverage = max(config.LEVERAGE - strategy_optimizer.LEVERAGE_ADJUSTMENT_STEP, strategy_optimizer.MIN_LEVERAGE)

            if atr > strategy_optimizer.VOLATILITY_THRESHOLD:
                recommended_leverage = max(recommended_leverage - strategy_optimizer.LEVERAGE_ADJUSTMENT_STEP, strategy_optimizer.MIN_LEVERAGE)

            strategy_effectiveness = win_rate * profit_factor if profit_factor != float('inf') else win_rate * 10

            metrics = PerformanceMetrics(symbol=symbol, win_rate=win_rate, profit_factor=profit_factor, avg_win=avg_win, avg_loss=avg_loss, recommended_leverage=recommended_leverage, strategy_effectiveness=strategy_effectiveness, market_volatility=atr, avg_trade_duration=avg_trade_duration)
            db.add(metrics)
            db.commit()

            log.info(f"📊 Análisis de rendimiento para {symbol}: WR: {win_rate:.2%}, PF: {profit_factor:.2f}, Lev. Rec: {recommended_leverage}x, Vol: {atr:.2f}%, Dur: {avg_trade_duration:.1f}m By gregorbc@gmail.com")
            return asdict(metrics)

        except Exception as e:
            log.error(f"Error analizando rendimiento para {symbol}: {e} By gregorbc@gmail.com")
            return None
        finally:
            if 'db' in locals(): db.close()

    def optimize_strategy_based_on_losses(self):
        if not DB_ENABLED: return
        try:
            db = SessionLocal()
            recent_losing_trades = db.query(Trade.symbol, func.count(Trade.id)).filter(
                Trade.pnl < 0,
                Trade.timestamp >= datetime.now() - timedelta(hours=strategy_optimizer.OPTIMIZATION_INTERVAL)
            ).group_by(Trade.symbol).all()

            if not recent_losing_trades: return

            for symbol, loss_count in recent_losing_trades:
                total_trades = db.query(Trade).filter(Trade.symbol == symbol).count()
                if total_trades > strategy_optimizer.MIN_TRADES_FOR_ANALYSIS:
                    loss_ratio = loss_count / total_trades
                    if loss_ratio > 0.7:
                        log.warning(f"⚠️ Símbolo problemático detectado: {symbol} con {loss_ratio:.2%} de trades perdedores By gregorbc@gmail.com")

        except Exception as e:
            log.error(f"Error optimizando estrategia basada en pérdidas: {e} By gregorbc@gmail.com")
        finally:
            if 'db' in locals(): db.close()

    def generate_daily_report(self):
        """Generar reporte diario de performance By gregorbc@gmail.com"""
        if not DB_ENABLED:
            return

        try:
            db = SessionLocal()
            today = datetime.now().date()
            start_of_day = datetime.combine(today, datetime.min.time())

            daily_trades = db.query(Trade).filter(
                Trade.timestamp >= start_of_day
            ).all()

            if not daily_trades:
                return

            total_trades = len(daily_trades)
            winning_trades = [t for t in daily_trades if t.pnl > 0]
            losing_trades = [t for t in daily_trades if t.pnl < 0]
            win_rate = len(winning_trades) / total_trades * 100
            total_pnl = sum(t.pnl for t in daily_trades)

            capital_stats = self.capital_manager.get_performance_stats()

            message = f"""<b>📊 Reporte Diario de Trading</b>

💰 Capital Actual: {capital_stats['current_balance']:.2f} USDT
📈 Profit Total: {capital_stats['total_profit']:+.2f} USDT
📊 Rentabilidad: {capital_stats['profit_percentage']:+.2f}%

📈 Total Trades: {total_trades}
✅ Trades Ganadores: {len(winning_trades)} ({win_rate:.1f}%)
❌ Trades Perdedores: {len(losing_trades)}
💰 P&L Diario: {total_pnl:+.2f} USDT

<b>📋 Resumen por Símbolo:</b>
"""

            by_symbol = {}
            for trade in daily_trades:
                if trade.symbol not in by_symbol:
                    by_symbol[trade.symbol] = []
                by_symbol[trade.symbol].append(trade)

            for symbol, trades in by_symbol.items():
                symbol_pnl = sum(t.pnl for t in trades)
                symbol_win_rate = len([t for t in trades if t.pnl > 0]) / len(trades) * 100
                message += f"\n{symbol}: {len(trades)} trades, P&L: {symbol_pnl:+.2f} USDT, Win Rate: {symbol_win_rate:.1f}%"

            self.telegram_notifier.send_message(message)

            log.info(f"📊 Reporte diario generado: {total_trades} trades, P&L Diario: {total_pnl:+.2f} USDT By gregorbc@gmail.com")

        except Exception as e:
            log.error(f"Error generando reporte diario: {e} By gregorbc@gmail.com")
        finally:
            if 'db' in locals():
                db.close()

    def open_trade(self, symbol: str, side: str, last_candle):
        symbol_settings = config.SYMBOL_SPECIFIC_SETTINGS.get(symbol, {})
        if not symbol_settings.get('enabled', True):
            log.info(f"⏭️ Símbolo {symbol} deshabilitado en configuración By gregorbc@gmail.com")
            return

        price = float(last_candle['close'])
        filters = self.api.get_symbol_filters(symbol)

        if not filters:
            log.error(f"No filters for {symbol} By gregorbc@gmail.com")
            return

        min_notional = max(filters.get('minNotional', 5.0), config.MIN_NOTIONAL_OVERRIDE)
        min_qty = filters['minQty']

        min_position_size = min_notional / price
        if min_position_size < min_qty:
            min_position_size = min_qty

        if min_position_size * price > self.capital_manager.current_balance:
            log.info(f"⏭️ {symbol} requiere mínimo {min_position_size * price:.2f} USDT, capital insuficiente By gregorbc@gmail.com")
            return

        max_leverage = symbol_settings.get('max_leverage', config.LEVERAGE)
        current_leverage = min(config.LEVERAGE, max_leverage)

        if config.DRY_RUN:
            log.info(f"[DRY RUN] Would open {side} on {symbol} By gregorbc@gmail.com")
            return

        self.api.ensure_symbol_settings(symbol)

        quantity = self.calculate_position_size(symbol, price)

        if quantity <= 0:
            log.info(f"⏭️ Tamaño de posición inválido para {symbol} By gregorbc@gmail.com")
            return

        quantity = self.api.round_value(quantity, filters['stepSize'])

        if quantity < min_qty:
            log.info(f"⏭️ Cantidad {quantity} para {symbol} es menor que el mínimo {min_qty} By gregorbc@gmail.com")
            return

        notional_value = quantity * price
        if notional_value < min_notional:
            log.info(f"⏭️ Valor nocional {notional_value:.2f} para {symbol} es menor que el mínimo {min_notional:.2f} By gregorbc@gmail.com")
            return

        order_side = SIDE_BUY if side == 'LONG' else SIDE_SELL

        log.info(f"Attempting to place MARKET order for {side} {symbol} (Qty: {quantity}, Value: {notional_value:.2f} USDT) By gregorbc@gmail.com")

        order = self.api.place_order(symbol, order_side, FUTURE_ORDER_TYPE_MARKET, quantity)

        if order and order.get('orderId'):
            log.info(f"✅ MARKET ORDER CREATED: {side} {quantity} {symbol} By gregorbc@gmail.com")

            if self.telegram_notifier.enabled:
                self.telegram_notifier.notify_trade_opened(
                    symbol, side, quantity, price, self.capital_manager.current_balance
                )

            if side == 'LONG':
                sl_price = price * (1 - (config.STOP_LOSS_PERCENT / 100))
                tp_price = price * (1 + (config.TAKE_PROFIT_PERCENT / 100))
            else:
                sl_price = price * (1 + (config.STOP_LOSS_PERCENT / 100))
                tp_price = price * (1 - (config.TAKE_PROFIT_PERCENT / 100))

            with state_lock:
                app_state["sl_tp_data"][symbol] = {
                    'sl_price': sl_price,
                    'tp_price': tp_price,
                    'side': side,
                    'entry_price': price
                }
        else:
            log.error(f"❌ Could not create market order for {symbol}. Response: {order} By gregorbc@gmail.com")

    def run(self):
        log.info(f"🚀 STARTING TRADING BOT v12.0 WITH REAL CAPITAL MANAGEMENT By gregorbc@gmail.com")
        self.start_time = time.time()

        # Inicializar con capital real
        self.capital_manager.update_balance(force=True)
        self.daily_starting_balance = self.capital_manager.current_balance
        self.daily_pnl = 0.0
        self.today = datetime.now().date()

        with state_lock:
            app_state["daily_starting_balance"] = self.capital_manager.current_balance
            app_state["daily_pnl"] = 0.0
            app_state["balance"] = self.capital_manager.current_balance
            app_state["capital_stats"] = self.capital_manager.get_performance_stats()

        while True:
            with state_lock:
                if not app_state["running"]: break

            try:
                self.cycle_count += 1
                log.info(f"--- 🔄 New scanning cycle ({self.cycle_count}) - Capital: {self.capital_manager.current_balance:.2f} USDT --- By gregorbc@gmail.com")

                # Actualizar capital real periódicamente
                if self.cycle_count % config.CAPITAL_UPDATE_INTERVAL == 0:
                    if self.capital_manager.update_balance():
                        current_balance = self.capital_manager.current_balance
                        profit = self.capital_manager.total_profit
                        profit_percentage = (self.capital_manager.total_profit / self.capital_manager.initial_balance * 100) if self.capital_manager.initial_balance > 0 else 0

                        if self.telegram_notifier.enabled:
                            self.telegram_notifier.notify_balance_update(
                                current_balance, profit, profit_percentage
                            )

                        with state_lock:
                            app_state["balance"] = current_balance
                            app_state["capital_stats"] = self.capital_manager.get_performance_stats()

                current_date = datetime.now().date()
                if current_date != self.today:
                    self.today = current_date
                    self.daily_starting_balance = self.capital_manager.current_balance
                    self.daily_pnl = 0.0
                    with state_lock:
                        app_state["daily_starting_balance"] = self.capital_manager.current_balance
                        app_state["daily_pnl"] = 0.0

                    self.generate_daily_report()
                    log.info("🔄 Nuevo día - Reiniciando métricas diarias By gregorbc@gmail.com")

                with state_lock:
                    app_state["connection_metrics"]["uptime"] = time.time() - self.start_time

                if self.cycle_count % 12 == 0:
                    self.market_regime = self.detect_market_regime()
                    with state_lock:
                        app_state["market_regime"] = self.market_regime
                    log.info(f"🏛️ Market Regime: {self.market_regime} By gregorbc@gmail.com")

                if self.cycle_count % config.SIGNAL_COOLDOWN_CYCLES == 1 and self.cycle_count > 1:
                    log.info("🧹 Cleaning recent signals memory (cooldown). By gregorbc@gmail.com")
                    self.recently_signaled.clear()

                account_info = self.api._safe_api_call(self.api.client.futures_account)
                if not account_info:
                    time.sleep(config.POLL_SEC)
                    continue

                if self.daily_pnl < - (self.daily_starting_balance * config.MAX_DAILY_LOSS_PERCENT / 100):
                    log.warning(f"⛔ Límite de pérdida diaria alcanzado: {self.daily_pnl:.2f} USDT By gregorbc@gmail.com")
                    time.sleep(config.POLL_SEC)
                    continue

                low_balance = self.check_balance_risk(account_info)
                if low_balance: log.warning("⏸️ Pausando nuevas operaciones por balance bajo By gregorbc@gmail.com")

                open_positions = {p['symbol']: p for p in account_info['positions'] if float(p['positionAmt']) != 0}

                for symbol, position in open_positions.items():
                    try:
                        ticker = self.api._safe_api_call(self.api.client.futures_symbol_ticker, symbol=symbol)
                        if not ticker: continue

                        current_price = float(ticker['price'])
                        df = self.get_klines_for_symbol(symbol)

                        exit_signal = self.dynamic_exit_strategy(symbol, position, current_price, df)

                        if exit_signal:
                            close_order = self.api.close_position(symbol, float(position['positionAmt']))
                            if close_order:
                                sl_tp_data = app_state["sl_tp_data"].get(symbol, {})
                                sl_adj = sl_tp_data.get('sl_adjustment', 1.0)
                                tp_adj = sl_tp_data.get('tp_adjustment', 1.0)

                                trade_result = _record_closed_trade(self.api, symbol, position, close_order.get('orderId'), exit_signal.lower(), current_price)

                                if trade_result is not None:
                                    # Reinvertir ganancias si corresponde
                                    self.capital_manager.reinvest_profit(trade_result)

                                    self.daily_pnl += trade_result
                                    with state_lock:
                                        app_state["daily_pnl"] = self.daily_pnl

                                    if self.telegram_notifier.enabled:
                                        self.telegram_notifier.notify_trade_closed(
                                            symbol, trade_result, exit_signal.lower(), self.capital_manager.current_balance
                                        )

                                if exit_signal.lower() in ['sl', 'tp', 'trailing'] and trade_result is not None:
                                    self.update_ai_model(symbol, trade_result, sl_adj, tp_adj, exit_signal.lower())

                    except Exception as e:
                        log.error(f"Error checking stops for {symbol}: {e} By gregorbc@gmail.com", exc_info=True)

                if open_positions:
                    socketio.emit('pnl_update', {p['symbol']: float(p.get('unrealizedProfit', 0) or 0) for p in open_positions.values()})

                if self.cycle_count % 6 == 0 and DB_ENABLED:
                    try:
                        self.optimize_strategy_based_on_losses()
                        for symbol in open_positions.keys(): self.analyze_trading_performance(symbol)
                    except Exception as e:
                        log.error(f"Error en análisis de rendimiento: {e} By gregorbc@gmail.com")

                num_open_pos = len(open_positions)
                if num_open_pos < config.MAX_CONCURRENT_POS and not low_balance:
                    symbols_to_scan = [s for s in self.get_top_symbols() if s not in open_positions and s not in self.recently_signaled]
                    log.info(f"🔍 Scanning {len(symbols_to_scan)} symbols for new signals. By gregorbc@gmail.com")

                    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS_KLINE) as executor:
                        futures = {executor.submit(self.get_klines_for_symbol, s): s for s in symbols_to_scan}
                        for future in futures:
                            symbol, df = futures[future], future.result()
                            if df is None or len(df) < config.SLOW_EMA: continue
                            self.calculate_indicators(df)
                            signal = self.check_signal(df, symbol)
                            if signal:
                                log.info(f"🔥 Signal found! {signal} on {symbol} By gregorbc@gmail.com")
                                self.recently_signaled.add(symbol)
                                self.open_trade(symbol, signal, df.iloc[-1])
                                if len(open_positions) + 1 >= config.MAX_CONCURRENT_POS:
                                    log.info("🚫 Concurrent positions limit reached. By gregorbc@gmail.com")
                                    break

                with state_lock:
                    stats = app_state["performance_stats"]
                    trades = app_state["trades_history"]
                    if trades:
                        stats["win_rate"] = (stats["wins"] / stats["trades_count"]) * 100 if stats["trades_count"] > 0 else 0
                        winning_trades_pnl = [t['pnl'] for t in trades if t['pnl'] > 0]
                        losing_trades_pnl = [t['pnl'] for t in trades if t['pnl'] < 0]
                        stats["avg_win"] = sum(winning_trades_pnl) / len(winning_trades_pnl) if winning_trades_pnl else 0
                        stats["avg_loss"] = abs(sum(losing_trades_pnl) / len(losing_trades_pnl)) if losing_trades_pnl else 0
                        total_win = sum(winning_trades_pnl)
                        total_loss = abs(sum(losing_trades_pnl))

                        stats["profit_factor"] = total_win / total_loss if total_loss > 0 else total_win

                        durations = [t['duration_minutes'] for t in trades if 'duration_minutes' in t]
                        if durations:
                            stats["avg_trade_duration"] = sum(durations) / len(durations)

                    current_balance = self.capital_manager.current_balance

                    app_state.update({
                        "status_message": "Running",
                        "balance": current_balance,
                        "open_positions": open_positions,
                        "total_investment_usd": sum(float(p.get('initialMargin', 0) or 0) for p in open_positions.values()),
                        "performance_stats": stats,
                        "capital_stats": self.capital_manager.get_performance_stats()
                    })
                    socketio.emit('status_update', app_state)

            except Exception as e:
                log.error(f"Error in main loop: {e} By gregorbc@gmail.com", exc_info=True)

            time.sleep(config.POLL_SEC)

        log.info("🛑 Bot stopped. By gregorbc@gmail.com")

# -------------------- HELPER FUNCTIONS -------------------- #
def _record_closed_trade(api: BinanceFutures, symbol: str, position_data: dict, order_id: str, close_type: str, exit_price: float) -> Optional[float]:
    """
    Helper function to centralize the logic for recording a closed trade.
    Fetches PnL, calculates stats, and updates the global state and database.
    Returns the realized PnL for AI learning.
    By gregorbc@gmail.com
    """
    try:
        pnl_records = api._safe_api_call(api.client.futures_account_trades, symbol=symbol, limit=20)
        realized_pnl = 0.0
        if pnl_records and order_id:
            # Suma el PnL de todas las transacciones que coincidan con el ID de la orden de cierre
            realized_pnl = sum(float(trade.get('realizedPnl', 0)) for trade in pnl_records if str(trade.get('orderId')) == str(order_id))

        entry_price = float(position_data['entryPrice'])
        position_size = abs(float(position_data['positionAmt']))
        current_leverage = int(position_data.get('leverage', config.LEVERAGE))

        roe = (realized_pnl / (position_size * entry_price / current_leverage)) * 100 if entry_price > 0 and position_size > 0 and current_leverage > 0 else 0.0

        entry_timestamp = int(position_data.get('updateTime', 0))
        entry_time = datetime.fromtimestamp(entry_timestamp / 1000) if entry_timestamp > 0 else datetime.now()
        exit_time = datetime.now()
        duration_minutes = (exit_time - entry_time).total_seconds() / 60

        trade_record = {
            "symbol": symbol,
            "side": 'LONG' if float(position_data['positionAmt']) > 0 else 'SHORT',
            "quantity": position_size,
            "entryPrice": entry_price,
            "exitPrice": exit_price,
            "pnl": realized_pnl,
            "roe": roe,
            "closeType": close_type,
            "timestamp": exit_time.timestamp(),
            "date": exit_time.strftime('%Y-%m-%d %H:%M:%S'),
            "duration_minutes": duration_minutes,
            "leverage": current_leverage
        }

        with state_lock:
            stats = app_state["performance_stats"]
            stats["realized_pnl"] += realized_pnl
            stats["trades_count"] += 1
            if realized_pnl >= 0:
                stats["wins"] += 1
            else:
                stats["losses"] += 1

            app_state["trades_history"].append(trade_record)

            for state_dict in ["trailing_stop_data", "sl_tp_data", "open_positions"]:
                if symbol in app_state[state_dict]:
                    del app_state[state_dict][symbol]

        if DB_ENABLED:
            try:
                db_session = SessionLocal()
                db_trade = Trade(
                    symbol=trade_record['symbol'],
                    side=trade_record['side'],
                    quantity=trade_record['quantity'],
                    entry_price=trade_record['entryPrice'],
                    exit_price=trade_record['exitPrice'],
                    pnl=trade_record['pnl'],
                    roe=trade_record['roe'],
                    close_type=trade_record['closeType'],
                    timestamp=exit_time,
                    leverage=trade_record['leverage'],
                    date=trade_record['date'],
                    duration=trade_record['duration_minutes']
                )
                db_session.add(db_trade)
                db_session.commit()
            except Exception as e:
                log.error(f"DB Error recording trade for {symbol}: {e} By gregorbc@gmail.com")
            finally:
                if 'db_session' in locals(): db_session.close()

        log.info(f"✅ Position closed: {symbol}, PnL: {realized_pnl:.2f} USDT, ROE: {roe:.2f}%, Reason: {close_type} By gregorbc@gmail.com")
        socketio.emit('status_update', app_state)
        
        return realized_pnl

    except Exception as e:
        log.error(f"❌ Critical error in _record_closed_trade for {symbol}: {e}", exc_info=True)
        return None

# -------------------- WEB ROUTES & BACKGROUND TASKS -------------------- #

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route('/api/status')
def get_status():
    with state_lock:
        return jsonify(app_state)

@app.route('/api/start', methods=['POST'])
def start_bot():
    global bot_thread, _trailing_monitor_thread
    with state_lock:
        if app_state["running"]: return jsonify({"status": "error", "message": "Bot is already running"}), 400
        app_state["running"] = True
        app_state["status_message"] = "Starting..."
    bot_instance = TradingBot()
    bot_thread = threading.Thread(target=bot_instance.run, daemon=True)
    bot_thread.start()
    log.info("▶️ Bot started from web interface. By gregorbc@gmail.com")
    return jsonify({"status": "success", "message": "Bot started successfully."})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    with state_lock:
        if not app_state["running"]: return jsonify({"status": "error", "message": "Bot is not running"}), 400
        app_state["running"] = False
        app_state["status_message"] = "Stopping..."
    log.info("⏹️ Bot stopped from web interface. By gregorbc@gmail.com")
    return jsonify({"status": "success", "message": "Bot stopped."})

@app.route('/api/update_config', methods=['POST'])
def update_config():
    global config
    data = request.json

    def cast_value(current, value):
        if isinstance(current, bool): return str(value).lower() in ['true', '1', 'yes', 'on']
        if isinstance(current, int): return int(value)
        if isinstance(current, float): return float(value)
        if isinstance(current, tuple):
            if isinstance(value, str): return tuple(p.strip().upper() for p in value.split(',') if p.strip())
            return tuple(str(x).upper() for x in value)
        return str(value)

    updated_fields = {}
    with state_lock:
        for key, value in data.items():
            if hasattr(config, key):
                try:
                    cur = getattr(config, key)
                    new_value = cast_value(cur, value)
                    setattr(config, key, new_value)
                    updated_fields[key] = new_value
                except (ValueError, TypeError) as e:
                    log.warning(f"Failed to set config field {key} with value {value}: {e} By gregorbc@gmail.com")
                    return jsonify({"status": "error", "message": f"Invalid value for {key}: {value}"}), 400
        app_state["config"] = asdict(config)

    log.info(f"⚙️ Configuration updated: {updated_fields} By gregorbc@gmail.com")
    socketio.emit('config_updated', app_state["config"])
    return jsonify({"status": "success", "message": "Configuration saved.", "config": app_state["config"]})

@app.route('/api/close_position', methods=['POST'])
def close_position_api():
    symbol = request.json.get('symbol')
    if not symbol: return jsonify({"status": "error", "message": "Missing symbol"}), 400

    try:
        api = BinanceFutures()
        acct = api._safe_api_call(api.client.futures_account)
        position = next((p for p in acct.get('positions', []) if p['symbol'] == symbol and float(p['positionAmt']) != 0), None)
        if not position: return jsonify({"status": "error", "message": f"No active position found for {symbol}"}), 404

        position_amt = float(position['positionAmt'])
        close_order = api.close_position(symbol, position_amt)

        if close_order:
            ticker = api._safe_api_call(api.client.futures_symbol_ticker, symbol=symbol)
            exit_price = float(ticker['price']) if ticker else float(position['entryPrice'])
            pnl = _record_closed_trade(api, symbol, position, close_order.get('orderId'), 'manual', exit_price)

            if pnl is not None:
                with state_lock:
                    app_state["daily_pnl"] += pnl

            return jsonify({"status": "success", "message": f"Position on {symbol} closed."})
        else:
            return jsonify({"status": "error", "message": "Failed to send close order."}), 500

    except Exception as e:
        log.error(f"Error closing position {symbol}: {e} By gregorbc@gmail.com")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/manual_trade', methods=['POST'])
def manual_trade():
    data = request.json
    symbol, side, margin = data.get('symbol', '').upper(), data.get('side'), float(data.get('margin', 10))
    if not all([symbol, side]): return jsonify({"status": "error", "message": "Missing parameters."}), 400
    try:
        api = BinanceFutures()
        api.ensure_symbol_settings(symbol)
        mark = api._safe_api_call(api.client.futures_mark_price, symbol=symbol)
        if not mark: return jsonify({"status": "error", "message": "Unable to fetch mark price."}), 500
        price = float(mark['markPrice'])
        filters = api.get_symbol_filters(symbol)
        if not filters: return jsonify({"status": "error", "message": f"Could not get filters for {symbol}"}), 500
        leverage_param = float(data.get('leverage', config.LEVERAGE) or config.LEVERAGE)
        quantity = api.round_value((margin * leverage_param) / price, filters['stepSize'])
        if quantity < filters['minQty'] or (quantity * price) < filters['minNotional']: return jsonify({"status": "error", "message": f"Quantity ({quantity}) below minimum allowed."}), 400
        order_side = SIDE_BUY if side == 'LONG' else SIDE_SELL
        order = api.place_order(symbol, order_side, FUTURE_ORDER_TYPE_MARKET, quantity)
        if order and (order.get('orderId') or order.get('mock')):
            log.info(f"MANUAL TRADE CREATED: {side} {quantity} {symbol} By gregorbc@gmail.com")
            return jsonify({"status": "success", "message": f"Manual market order for {symbol} created."})
        else:
            return jsonify({"status": "error", "message": f"Manual order failed: {order}"}), 500
    except Exception as e:
        log.error(f"Error in manual trade: {e} By gregorbc@gmail.com")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/trade_history')
def get_trade_history():
    with state_lock:
        trades = app_state["trades_history"]
    sorted_trades = sorted(trades, key=lambda x: x.get('timestamp', 0), reverse=True)
    page, per_page = int(request.args.get('page', 1)), int(request.args.get('per_page', 20))
    start_idx, end_idx = (page - 1) * per_page, page * per_page
    paginated_trades = sorted_trades[start_idx:end_idx]
    return jsonify({"trades": paginated_trades, "total": len(sorted_trades), "page": page, "per_page": per_page, "total_pages": math.ceil(len(sorted_trades) / per_page)})

@app.route('/api/performance_metrics')
def get_performance_metrics():
    if not DB_ENABLED: return jsonify({"error": "Database is not enabled."}), 503
    try:
        db = SessionLocal()
        query = db.query(PerformanceMetrics).order_by(desc(PerformanceMetrics.timestamp)).limit(100)
        metrics = query.all()
        return jsonify([asdict(m) for m in metrics])
    except Exception as e:
        log.error(f"Error fetching performance metrics: {e} By gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'db' in locals(): db.close()

@app.route('/api/performance_stats')
def get_performance_stats():
    """Obtener estadísticas de rendimiento detalladas By gregorbc@gmail.com"""
    if not DB_ENABLED: return jsonify({"error": "Database is not enabled."}), 503
    try:
        db = SessionLocal()

        symbol_stats = db.query(
            Trade.symbol,
            func.count(Trade.id).label('total_trades'),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label('winning_trades'),
            func.avg(case((Trade.pnl > 0, Trade.pnl), else_=None)).label('avg_win'),
            func.avg(case((Trade.pnl < 0, Trade.pnl), else_=None)).label('avg_loss'),
            func.sum(Trade.pnl).label('total_pnl')
        ).group_by(Trade.symbol).all()

        overall_stats = db.query(
            func.count(Trade.id).label('total_trades'),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label('winning_trades'),
            func.avg(Trade.pnl).label('avg_pnl'),
            func.sum(Trade.pnl).label('total_pnl')
        ).first()

        return jsonify({
            'symbol_stats': [dict(s) for s in symbol_stats],
            'overall_stats': dict(overall_stats._mapping) if overall_stats else {}
        })
    except Exception as e:
        log.error(f"Error fetching performance stats: {e} By gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'db' in locals(): db.close()

@app.route('/api/ai_metrics')
def get_ai_metrics():
    with state_lock:
        return jsonify(app_state["ai_metrics"])

@app.route('/api/detailed_metrics')
def get_detailed_metrics():
    """Obtener métricas detalladas para el panel de control By gregorbc@gmail.com"""
    try:
        with state_lock:
            balance_history = app_state.get("balance_history", [])
            trades = app_state.get("trades_history", [])

            if not balance_history or not trades:
                return jsonify({"error": "Datos insuficientes"})

            initial_balance = balance_history[0] if balance_history else 0
            current_balance = balance_history[-1] if balance_history else 0
            total_return = ((current_balance - initial_balance) / initial_balance * 100) if initial_balance > 0 else 0

            returns = []
            for i in range(1, len(balance_history)):
                ret = (balance_history[i] - balance_history[i-1]) / balance_history[i-1] if balance_history[i-1] > 0 else 0
                returns.append(ret)

            sharpe_ratio = (np.mean(returns) / np.std(returns) * np.sqrt(365)) if returns and np.std(returns) > 0 else 0

            winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('pnl', 0) < 0]

            metrics = {
                "total_return_percent": total_return,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": app_state["risk_metrics"].get("max_drawdown", 0),
                "win_rate": (len(winning_trades) / len(trades)) * 100 if trades else 0,
                "profit_factor": (sum(t.get('pnl', 0) for t in winning_trades) /
                                  abs(sum(t.get('pnl', 0) for t in losing_trades))) if losing_trades and sum(t.get('pnl', 0) for t in losing_trades) != 0 else float('inf'),
                "avg_trade_duration": app_state["performance_stats"].get("avg_trade_duration", 0),
                "exposure_ratio": app_state["risk_metrics"].get("exposure_ratio", 0),
            }

            return jsonify(metrics)

    except Exception as e:
        log.error(f"Error calculando métricas detalladas: {e} By gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500

@app.route('/api/capital_stats')
def get_capital_stats():
    """Obtener estadísticas de capital By gregorbc@gmail.com"""
    with state_lock:
        return jsonify(app_state["capital_stats"])

@app.route('/api/update_balance', methods=['POST'])
def update_balance():
    """Forzar actualización del balance By gregorbc@gmail.com"""
    try:
        bot_instance = TradingBot()
        if bot_instance.capital_manager.update_balance(force=True):
            with state_lock:
                app_state["balance"] = bot_instance.capital_manager.current_balance
                app_state["capital_stats"] = bot_instance.capital_manager.get_performance_stats()
            return jsonify({"status": "success", "message": "Balance updated successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to update balance"}), 500
    except Exception as e:
        log.error(f"Error updating balance: {e} By gregorbc@gmail.com")
        return jsonify({"status": "error", "message": str(e)}), 500

# -------------------- NEW DATABASE ROUTES -------------------- #
@app.route('/api/db/trade_history')
def get_db_trade_history():
    """Obtener historial completo de trades desde la base de datos By gregorbc@gmail.com"""
    if not DB_ENABLED:
        return jsonify({"error": "Database no está habilitada"}), 503

    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))

        db = SessionLocal()

        # Obtener trades con paginación
        trades = db.query(Trade).order_by(desc(Trade.timestamp)).offset((page-1)*per_page).limit(per_page).all()

        # Contar total de trades
        total_trades = db.query(func.count(Trade.id)).scalar()

        # Calcular métricas generales
        overall_stats = db.query(
            func.count(Trade.id).label('total_trades'),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label('winning_trades'),
            func.sum(Trade.pnl).label('total_pnl'),
            func.avg(case((Trade.pnl > 0, Trade.pnl), else_=None)).label('avg_win'),
            func.avg(case((Trade.pnl < 0, Trade.pnl), else_=None)).label('avg_loss')
        ).first()

        # Calcular profit factor
        total_wins = db.query(func.sum(Trade.pnl)).filter(Trade.pnl > 0).scalar() or 0
        total_losses = abs(db.query(func.sum(Trade.pnl)).filter(Trade.pnl < 0).scalar() or 0)
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

        # Calcular drawdown máximo
        trades_chronological = db.query(Trade).order_by(Trade.timestamp).all()
        balance = 0
        peak = 0
        max_drawdown = 0
        equity_curve = []

        for trade in trades_chronological:
            balance += trade.pnl
            equity_curve.append(balance)
            if balance > peak:
                peak = balance
            drawdown = (peak - balance) / peak * 100 if peak > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Calcular Sharpe ratio (aproximado)
        daily_returns = []
        current_date = None
        daily_pnl = 0

        for trade in trades_chronological:
            trade_date = trade.timestamp.date()
            if current_date is None:
                current_date = trade_date

            if trade_date == current_date:
                daily_pnl += trade.pnl
            else:
                if len(equity_curve) > 1:
                    prev_balance = equity_curve[-2]
                    daily_return = daily_pnl / prev_balance if prev_balance > 0 else 0
                    daily_returns.append(daily_return)
                daily_pnl = trade.pnl
                current_date = trade_date

        if daily_pnl != 0 and len(equity_curve) > 1:
            prev_balance = equity_curve[-2]
            daily_return = daily_pnl / prev_balance if prev_balance > 0 else 0
            daily_returns.append(daily_return)

        sharpe_ratio = 0
        if daily_returns:
            avg_daily_return = np.mean(daily_returns)
            std_daily_return = np.std(daily_returns)
            sharpe_ratio = (avg_daily_return / std_daily_return) * np.sqrt(365) if std_daily_return > 0 else 0

        result = {
            "trades": [{
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "quantity": float(t.quantity),
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price),
                "pnl": float(t.pnl),
                "roe": float(t.roe),
                "close_type": t.close_type,
                "timestamp": t.timestamp.isoformat(),
                "leverage": t.leverage,
                "duration": float(t.duration) if t.duration else 0
            } for t in trades],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_trades,
                "pages": (total_trades + per_page - 1) // per_page
            },
            "performance_metrics": {
                "total_trades": overall_stats.total_trades,
                "winning_trades": overall_stats.winning_trades,
                "win_rate": (overall_stats.winning_trades / overall_stats.total_trades * 100) if overall_stats.total_trades > 0 else 0,
                "total_pnl": float(overall_stats.total_pnl) if overall_stats.total_pnl else 0,
                "avg_win": float(overall_stats.avg_win) if overall_stats.avg_win else 0,
                "avg_loss": float(overall_stats.avg_loss) if overall_stats.avg_loss else 0,
                "profit_factor": profit_factor,
                "max_drawdown": max_drawdown,
                "sharpe_ratio": sharpe_ratio
            }
        }

        return jsonify(result)

    except Exception as e:
        log.error(f"Error obteniendo historial de trades: {e} By gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'db' in locals():
            db.close()

@app.route('/api/db/performance_by_symbol')
def get_performance_by_symbol():
    """Obtener métricas de rendimiento agrupadas por símbolo By gregorbc@gmail.com"""
    if not DB_ENABLED:
        return jsonify({"error": "Database no está habilitada"}), 503

    try:
        db = SessionLocal()

        symbol_stats = db.query(
            Trade.symbol,
            func.count(Trade.id).label('total_trades'),
            func.sum(case((Trade.pnl > 0, 1), else_=0)).label('winning_trades'),
            func.sum(Trade.pnl).label('total_pnl'),
            func.avg(case((Trade.pnl > 0, Trade.pnl), else_=None)).label('avg_win'),
            func.avg(case((Trade.pnl < 0, Trade.pnl), else_=None)).label('avg_loss'),
            func.avg(Trade.leverage).label('avg_leverage'),
            func.avg(Trade.duration).label('avg_duration')
        ).group_by(Trade.symbol).all()

        result = [{
            "symbol": stat.symbol,
            "total_trades": stat.total_trades,
            "winning_trades": stat.winning_trades,
            "win_rate": (stat.winning_trades / stat.total_trades * 100) if stat.total_trades > 0 else 0,
            "total_pnl": float(stat.total_pnl) if stat.total_pnl else 0,
            "avg_win": float(stat.avg_win) if stat.avg_win else 0,
            "avg_loss": float(stat.avg_loss) if stat.avg_loss else 0,
            "profit_factor": (float(stat.avg_win) / abs(float(stat.avg_loss))) if stat.avg_loss and stat.avg_loss != 0 and stat.avg_win else 0,
            "avg_leverage": float(stat.avg_leverage) if stat.avg_leverage else 0,
            "avg_duration": float(stat.avg_duration) if stat.avg_duration else 0
        } for stat in symbol_stats]

        return jsonify(result)

    except Exception as e:
        log.error(f"Error obteniendo rendimiento por símbolo: {e} By gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'db' in locals():
            db.close()

@app.route('/api/db/equity_curve')
def get_equity_curve():
    """Obtener la curva de equity (evolución del balance) By gregorbc@gmail.com"""
    if not DB_ENABLED:
        return jsonify({"error": "Database no está habilitada"}), 503

    try:
        db = SessionLocal()

        # Obtener todos los trades ordenados por fecha
        trades = db.query(Trade).order_by(Trade.timestamp).all()

        equity_curve = []
        current_balance = 0
        peak_balance = 0

        for trade in trades:
            current_balance += trade.pnl
            if current_balance > peak_balance:
                peak_balance = current_balance

            drawdown = ((peak_balance - current_balance) / peak_balance * 100) if peak_balance > 0 else 0

            equity_curve.append({
                "timestamp": trade.timestamp.isoformat(),
                "balance": current_balance,
                "drawdown": drawdown,
                "trade_id": trade.id,
                "symbol": trade.symbol,
                "pnl": trade.pnl
            })

        return jsonify(equity_curve)

    except Exception as e:
        log.error(f"Error obteniendo curva de equity: {e} By gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'db' in locals():
            db.close()

@app.route('/api/positions')
def get_positions():
    with state_lock:
        return jsonify({"positions": list(app_state.get("open_positions", {}).values())})

@app.route('/api/open_positions')
def get_open_positions():
    with state_lock:
        return jsonify(app_state.get("open_positions", {}))

@app.route('/api/trailing_stop_data')
def get_trailing_stop_data():
    with state_lock:
        return jsonify(app_state.get("trailing_stop_data", {}))

# -------------------- SOCKETIO EVENTS -------------------- #
@socketio.on('connect')
def handle_connect():
    log.info(f"🔌 Client connected: {request.sid} By gregorbc@gmail.com")
    with state_lock:
        socketio.emit('status_update', app_state, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    log.info(f"🔌 Client disconnected: {request.sid} By gregorbc@gmail.com")

# -------------------- MAIN FUNCTION -------------------- #
if __name__ == '__main__':
    load_dotenv()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'

    log.info("🚀 Starting Binance Futures Bot Web Application v12.0 with Real Capital Management By gregorbc@gmail.com")
    log.info(f"🌐 Server will run on {host}:{port} By gregorbc@gmail.com")

    os.makedirs('logs', exist_ok=True)

    if DB_ENABLED:
        try:
            from database import init_db
            init_db()
            log.info("Database initialized successfully. By gregorbc@gmail.com")
        except Exception as e:
            log.error(f"Database initialization failed: {e} By gregorbc@gmail.com")

    socketio.run(app, debug=debug, host=host, port=port, use_reloader=False, allow_unsafe_werkzeug=True)
