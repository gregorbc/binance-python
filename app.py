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
    
    _24H_VOLUME: float = 30_000_000
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

            # El último valor puede ser NaN (Not a Number), así que lo manejamos
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
                    strength = strength * 0.6
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
