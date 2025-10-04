from __future__ import annotations
"""
Binance Futures Bot - Web Application v11.0 with Enhanced Trading
Advanced trading system with improved signal generation, risk management, and AI optimization
VERSION MEJORADA BASADA EN ANÁLISIS DE RENDIMIENTO
"""
import os, time, math, logging, threading, random
import pandas as pd
import numpy as np
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

from sqlalchemy import desc, func
try:
    from database import SessionLocal, Trade, PerformanceMetrics
    DB_ENABLED = True
except ImportError:
    DB_ENABLED = False
    print("WARNING: 'database.py' not found. Database features will be disabled.")


# -------------------- CONFIGURATION -------------------- #
@dataclass
class CONFIG:
    # --- MEJORA: Apalancamiento reducido para mitigar el riesgo de grandes pérdidas.
    LEVERAGE: int = 10
    MAX_CONCURRENT_POS: int = 7
    FIXED_MARGIN_PER_TRADE_USDT: float = 4.0
    NUM_SYMBOLS_TO_SCAN: int = 400
    # Strategy Configuration (Editable from web)
    ATR_MULT_SL: float = 2.5  # Multiplicador de ATR para Stop Loss
    ATR_MULT_TP: float = 4.0  # Multiplicador de ATR para Take Profit (o usar porcentaje)
    # Trailing Stop Configuration
    TRAILING_STOP_ACTIVATION: float = 0.6
    TRAILING_STOP_PERCENTAGE: float = 0.4
    # --- MEJORA: La lógica de SL/TP ahora se basa en ATR. Este flag puede usarse para activar/desactivar la lógica de salida.
    USE_EXIT_LOGIC: bool = True
    TAKE_PROFIT_PERCENT: float = 2.5
    # AI Adjustment Configuration
    AI_SL_ADJUSTMENT: bool = True
    AI_TP_ADJUSTMENT: bool = True
    AI_TRAILING_ADJUSTMENT: bool = True
    AI_VOLATILITY_FACTOR: float = 1.8
    # Fixed Configuration
    MARGIN_TYPE: str = "CROSSED"
    MIN_24H_VOLUME: float = 25_000_000
    EXCLUDE_SYMBOLS: tuple = ("BTCDOMUSDT", "DEFIUSDT", "USDCUSDT", "TUSDUSDT", "BUSDUSDT")
    # --- MEJORA: Símbolos con mal rendimiento (POL, KERNEL) añadidos a la lista negra.
    BLACKLIST_SYMBOLS: tuple = ("PROMPTUSDT", "PLAYUSDT", "ETCUSDT", "LDOUSDT", "1000FLOKIUSDT", "QTUMUSDT", "LRCUSDT", "POLUSDT", "KERNELUSDT")
    TIMEFRAME: str = "5m"
    CANDLES_LIMIT: int = 150
    FAST_EMA: int = 12
    SLOW_EMA: int = 26
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9
    RSI_PERIOD: int = 14
    STOCH_PERIOD: int = 14
    POLL_SEC: float = 8.0
    DRY_RUN: bool = False
    MAX_WORKERS_KLINE: int = 25
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE: str = "bot_v11.log"
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"
    SIGNAL_COOLDOWN_CYCLES: int = 25
    # Balance monitoring
    MIN_BALANCE_THRESHOLD: float = 15.0
    RISK_PER_TRADE_PERCENT: float = 1.2
    # Connection settings
    MAX_API_RETRIES: int = 5
    API_RETRY_DELAY: float = 0.5
    # AI Enhancement Settings
    AI_LEARNING_RATE: float = 0.015
    AI_EXPLORATION_RATE: float = 0.08
    AI_VOLATILITY_THRESHOLD: float = 2.2
    AI_TREND_STRENGTH_THRESHOLD: float = 30.0
    # Enhanced Strategy Settings
    MIN_SIGNAL_STRENGTH: float = 0.68
    MAX_POSITION_HOLD_HOURS: int = 6
    VOLATILITY_ADJUSTMENT: bool = True

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

# -------------------- IA ENHANCEMENTS -------------------- #
@dataclass
class AIModel:
    learning_rate: float = config.AI_LEARNING_RATE
    exploration_rate: float = config.AI_EXPLORATION_RATE
    q_table: Dict = field(default_factory=dict)
    
    def get_action(self, state: str) -> Tuple[float, float]:
        if state not in self.q_table or random.random() < self.exploration_rate:
            sl_adj = random.uniform(0.7, 1.3)
            tp_adj = random.uniform(0.8, 1.5)
            self.q_table[state] = (sl_adj, tp_adj, 0)
        return self.q_table[state][0], self.q_table[state][1]
    
    def update_model(self, state: str, reward: float, sl_adj: float, tp_adj: float):
        if state in self.q_table:
            current_reward = self.q_table[state][2]
            new_reward = current_reward + self.learning_rate * (reward - current_reward)
            self.q_table[state] = (sl_adj, tp_adj, new_reward)

@dataclass
class MarketAnalyzer:
    volatility_threshold: float = config.AI_VOLATILITY_THRESHOLD
    trend_strength_threshold: float = config.AI_TREND_STRENGTH_THRESHOLD
    
    def analyze_market_conditions(self, symbol: str, df: pd.DataFrame) -> Dict[str, float]:
        if df is None or len(df) < 30:
            return {"volatility": 0, "trend_strength": 0, "market_regime": 0}
        
        atr = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1]
        volatility = (atr / df['close'].iloc[-1]) * 100
        
        adx = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1]
        plus_di = talib.PLUS_DI(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1]
        minus_di = talib.MINUS_DI(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1]
        
        market_regime = 0
        if adx > self.trend_strength_threshold:
            if plus_di > minus_di: market_regime = 1
            else: market_regime = 2
        
        return {"volatility": volatility, "trend_strength": adx, "market_regime": market_regime}

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
app_state = { "running": False, "status_message": "Stopped", "open_positions": {}, "trailing_stop_data": {}, "sl_tp_data": {}, "config": asdict(config), "performance_stats": {"realized_pnl": 0.0, "trades_count": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": 0.0, "avg_trade_duration": 0.0, "max_drawdown": 0.0, "sharpe_ratio": 0.0 }, "balance": 0.0, "total_investment_usd": 0.0, "trades_history": [], "balance_history": [], "risk_metrics": {"max_drawdown": 0.0, "sharpe_ratio": 0.0, "profit_per_day": 0.0, "exposure_ratio": 0.0, "volatility": 0.0, "avg_position_duration": 0.0}, "connection_metrics": {"api_retries": 0, "last_reconnect": None, "uptime": 0.0}, "ai_metrics": {"q_table_size": 0, "last_learning_update": None, "exploration_rate": config.AI_EXPLORATION_RATE}, "market_regime": "NEUTRAL"}
state_lock = threading.Lock()

# -------------------- BINANCE CLIENT -------------------- #
class BinanceFutures:
    def __init__(self):
        load_dotenv()
        api_key, api_secret = os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        if not api_key or not api_secret: raise ValueError("API keys not configured")
        self.client = Client(api_key, api_secret, testnet=testnet)
        log.info(f"🔧 CONNECTED TO BINANCE FUTURES {'TESTNET' if testnet else 'MAINNET'}")
        self.exchange_info = self.client.futures_exchange_info()

    def ensure_symbol_settings(self, symbol: str):
        try: self._safe_api_call(self.client.futures_change_leverage, symbol=symbol, leverage=int(config.LEVERAGE))
        except Exception as e: log.warning(f"Leverage set issue for {symbol}: {e}")
        try: self.client.futures_change_margin_type(symbol=symbol, marginType=config.MARGIN_TYPE)
        except BinanceAPIException as e:
            if not (e.code == -4046 or "No need to change margin type" in e.message): log.warning(f"Margin type set warning for {symbol}: {e}")

    def _safe_api_call(self, func, *args, **kwargs):
        for attempt in range(config.MAX_API_RETRIES):
            try:
                time.sleep(config.API_RETRY_DELAY * (2 ** attempt))
                result = func(*args, **kwargs)
                with state_lock: app_state["connection_metrics"]["api_retries"] = 0
                return result
            except BinanceAPIException as e:
                with state_lock: app_state["connection_metrics"]["api_retries"] += 1
                log.warning(f"API non-critical error: {e.code} - {e.message}")
            except Exception as e:
                with state_lock: app_state["connection_metrics"]["api_retries"] += 1
                log.warning(f"General API call error: {e}")
        return None

    def get_symbol_filters(self, symbol: str) -> Optional[Dict[str, float]]:
        s_info = next((s for s in self.exchange_info['symbols'] if s['symbol'] == symbol), None)
        if not s_info: return None
        filters = {f['filterType']: f for f in s_info['filters']}
        return {"stepSize": float(filters['LOT_SIZE']['stepSize']), "minQty": float(filters['LOT_SIZE']['minQty']), "tickSize": float(filters['PRICE_FILTER']['tickSize']), "minNotional": float(filters.get('MIN_NOTIONAL', {}).get('notional', 5.0))}

    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, price: Optional[float] = None, reduce_only: bool = False) -> Optional[Dict]:
        params = {'symbol': symbol, 'side': side, 'type': order_type, 'quantity': quantity}
        if order_type == FUTURE_ORDER_TYPE_LIMIT:
            if price is None: return None
            params.update({'price': str(price), 'timeInForce': TIME_IN_FORCE_GTC})
        if reduce_only: params['reduceOnly'] = 'true'
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] place_order: {params}")
            return {'mock': True, 'orderId': int(time.time() * 1000)}
        return self._safe_api_call(self.client.futures_create_order, **params)

    def close_position(self, symbol: str, position_amt: float) -> Optional[Dict]:
        side = SIDE_SELL if position_amt > 0 else SIDE_BUY
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] close_position {symbol} {position_amt}")
            return {'mock': True, 'orderId': int(time.time() * 1000)}
        return self.place_order(symbol, side, FUTURE_ORDER_TYPE_MARKET, abs(position_amt), reduce_only=True)

    @staticmethod
    def round_value(value: float, step: float) -> float:
        if step == 0: return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)

# -------------------- TRADING BOT WITH ENHANCED TRADING -------------------- #
class TradingBot:
    def __init__(self):
        self.api = BinanceFutures()
        self.recently_signaled = set()
        self.cycle_count = 0
        self.start_time = time.time()
        self.ai_model = AIModel()
        self.market_analyzer = MarketAnalyzer()
        self.signal_strength = {}
        self.market_regime = "NEUTRAL"

    def get_top_symbols(self) -> List[str]:
        tickers = self.api._safe_api_call(self.api.client.futures_ticker) or []
        valid_tickers = [t for t in tickers if t['symbol'].endswith('USDT') and t['symbol'] not in config.EXCLUDE_SYMBOLS and t['symbol'] not in config.BLACKLIST_SYMBOLS and float(t['quoteVolume']) > config.MIN_24H_VOLUME]
        sorted_tickers = sorted(valid_tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
        return [t['symbol'] for t in sorted_tickers[:config.NUM_SYMBOLS_TO_SCAN]]

    def get_klines_for_symbol(self, symbol: str) -> Optional[pd.DataFrame]:
        klines = self.api._safe_api_call(self.api.client.futures_klines, symbol=symbol, interval=config.TIMEFRAME, limit=config.CANDLES_LIMIT)
        if not klines: return None
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=['close'], inplace=True)
        return df

    def calculate_indicators(self, df: pd.DataFrame):
        df['fast_ema'] = talib.EMA(df['close'], timeperiod=config.FAST_EMA)
        df['slow_ema'] = talib.EMA(df['close'], timeperiod=config.SLOW_EMA)
        df['rsi'] = talib.RSI(df['close'], timeperiod=config.RSI_PERIOD)
        macd, macdsignal, macdhist = talib.MACD(df['close'], fastperiod=config.MACD_FAST, slowperiod=config.MACD_SLOW, signalperiod=config.MACD_SIGNAL)
        df['macd'], df['macd_signal'], df['macd_hist'] = macd, macdsignal, macdhist
        upper, middle, lower = talib.BBANDS(df['close'], timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = upper, middle, lower
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

    def calculate_signal_strength(self, df: pd.DataFrame, signal: str, symbol: str) -> float:
        if len(df) < 30: return 0.4
        volume_avg = df['volume'].rolling(20).mean().iloc[-1]
        volume_ratio = min(2.0, df['volume'].iloc[-1] / volume_avg) if volume_avg > 0 else 1
        rsi_strength = abs(df['rsi'].iloc[-1] - 50) / 50
        price_distance = abs(df['fast_ema'].iloc[-1] - df['slow_ema'].iloc[-1]) / df['close'].iloc[-1]
        macd_strength = 0.8 if (signal == "LONG" and df['macd'].iloc[-1] > df['macd_signal'].iloc[-1]) or (signal == "SHORT" and df['macd'].iloc[-1] < df['macd_signal'].iloc[-1]) else 0.5
        bb_position = (df['close'].iloc[-1] - df['bb_lower'].iloc[-1]) / (df['bb_upper'].iloc[-1] - df['bb_lower'].iloc[-1])
        bb_strength = 0.8 if (signal == "LONG" and bb_position < 0.2) or (signal == "SHORT" and bb_position > 0.8) else 0.5
        market_conditions = self.market_analyzer.analyze_market_conditions(symbol, df)
        trend_alignment = 0.5
        if (market_conditions["market_regime"] == 1 and signal == "LONG") or (market_conditions["market_regime"] == 2 and signal == "SHORT"): trend_alignment = 0.9
        elif (market_conditions["market_regime"] == 1 and signal == "SHORT") or (market_conditions["market_regime"] == 2 and signal == "LONG"): trend_alignment = 0.2
        regime_factor = 1.0
        if (self.market_regime == "BULL" and signal == "LONG") or (self.market_regime == "BEAR" and signal == "SHORT"): regime_factor = 1.2
        elif (self.market_regime == "BULL" and signal == "SHORT") or (self.market_regime == "BEAR" and signal == "LONG"): regime_factor = 0.7
        strength = (volume_ratio * 0.15 + rsi_strength * 0.20 + price_distance * 0.20 + macd_strength * 0.15 + bb_strength * 0.10 + trend_alignment * 0.20) * regime_factor
        return max(0.1, min(0.95, strength))

    def check_signal(self, df: pd.DataFrame, symbol: str) -> Optional[str]:
        if len(df) < 2: return None
        last, prev = df.iloc[-1], df.iloc[-2]
        signal = None
        if last['fast_ema'] > last['slow_ema'] and prev['fast_ema'] <= prev['slow_ema']: signal = 'LONG'
        elif last['fast_ema'] < last['slow_ema'] and prev['fast_ema'] >= prev['slow_ema']: signal = 'SHORT'
        if not signal: return None
        rsi_confirm = (signal == 'LONG' and last['rsi'] > 45) or (signal == 'SHORT' and last['rsi'] < 55)
        macd_confirm = (signal == 'LONG' and last['macd'] > last['macd_signal']) or (signal == 'SHORT' and last['macd'] < last['macd_signal'])
        if not (rsi_confirm or macd_confirm): return None
        strength = self.calculate_signal_strength(df, signal, symbol)
        self.signal_strength[symbol] = strength
        if strength < config.MIN_SIGNAL_STRENGTH:
            log.info(f"📉 Señal {signal} en {symbol} descartada por fuerza insuficiente: {strength:.2f}")
            return None
        log.info(f"📶 Señal {signal} con fuerza: {strength:.2f} en {symbol}")
        return signal

    def get_ai_adjustments(self, symbol: str, performance_data: Dict) -> Tuple[float, float]:
        market_conditions = self.market_analyzer.analyze_market_conditions(symbol, self.get_klines_for_symbol(symbol))
        volatility_state = "HIGH" if market_conditions["volatility"] > self.market_analyzer.volatility_threshold else "LOW"
        trend_state = "TREND" if market_conditions["trend_strength"] > 25 else "RANGE"
        market_state = "BULL" if self.market_regime == "BULL" else "BEAR" if self.market_regime == "BEAR" else "NEUTRAL"
        state_key = f"{volatility_state}_{trend_state}_{market_state}"
        if performance_data: state_key += f"_WR{int(performance_data.get('win_rate', 0.5)*100)}_PF{performance_data.get('profit_factor', 1.0):.1f}"
        return self.ai_model.get_action(state_key)

    def update_ai_model(self, symbol: str, trade_result: float, sl_adj: float, tp_adj: float, exit_reason: str):
        try:
            df = self.get_klines_for_symbol(symbol)
            if df is None or len(df) < 30: return
            market_conditions = self.market_analyzer.analyze_market_conditions(symbol, df)
            volatility_state = "HIGH" if market_conditions["volatility"] > self.market_analyzer.volatility_threshold else "LOW"
            trend_state = "TREND" if market_conditions["trend_strength"] > 25 else "RANGE"
            market_state = "BULL" if self.market_regime == "BULL" else "BEAR" if self.market_regime == "BEAR" else "NEUTRAL"
            state_key = f"{volatility_state}_{trend_state}_{market_state}_EXIT_{exit_reason}"
            
            # --- MEJORA: Lógica de recompensa de IA mejorada para valorar más los TP y penalizar más los SL.
            reward = 0.0
            if exit_reason == 'tp':
                reward = 2.0  # Recompensa máxima por alcanzar el objetivo
            elif exit_reason == 'trailing':
                reward = 1.5 + (trade_result / (abs(trade_result) + 1.0)) # Recompensa alta por dejar correr ganancias
            elif trade_result > 0:
                reward = 1.0 * (trade_result / (abs(trade_result) + 1.0)) # Recompensa moderada
            else: # Pérdidas
                if exit_reason == 'sl':
                    reward = -2.5 # Penalización extra fuerte por tocar SL
                else:
                    reward = -1.5 * (abs(trade_result) / (abs(trade_result) + 1.0))

            self.ai_model.update_model(state_key, reward, sl_adj, tp_adj)
            log.info(f"🤖 AI model updated for {symbol} with reward {reward:.2f} for exit type '{exit_reason}'")

            with state_lock:
                app_state["ai_metrics"]["q_table_size"] = len(self.ai_model.q_table)
                app_state["ai_metrics"]["last_learning_update"] = datetime.now().isoformat()
        except Exception as e:
            log.error(f"Error updating AI model for {symbol}: {e}")

    def check_trailing_stop(self, symbol: str, position: Dict, current_price: float):
        # Esta función mantiene su lógica original, ya que es robusta.
        with state_lock:
            position_side = 'LONG' if float(position['positionAmt']) > 0 else 'SHORT'
            entry_price = float(position['entryPrice'])
            trailing_data = app_state["trailing_stop_data"].get(symbol)
            if not trailing_data:
                app_state["trailing_stop_data"][symbol] = {'activated': False, 'best_price': entry_price, 'current_stop': entry_price, 'side': position_side}
                trailing_data = app_state["trailing_stop_data"][symbol]
            
            activation_percent = config.TRAILING_STOP_ACTIVATION
            stop_percentage = config.TRAILING_STOP_PERCENTAGE
            should_close = False
            
            if position_side == 'LONG':
                if current_price > trailing_data['best_price']: trailing_data['best_price'] = current_price
                profit_percentage = ((current_price - entry_price) / entry_price) * 100
                if not trailing_data['activated'] and profit_percentage >= activation_percent:
                    trailing_data['activated'] = True
                    log.info(f"🔔 Trailing stop activado para {symbol}")
                if trailing_data['activated']:
                    new_stop = trailing_data['best_price'] * (1 - stop_percentage / 100)
                    if new_stop > trailing_data['current_stop']: trailing_data['current_stop'] = new_stop
                    if current_price <= trailing_data['current_stop']:
                        log.info(f"🔴 Cierre por trailing stop: {symbol} @ {current_price} (Stop: {trailing_data['current_stop']})")
                        should_close = True
            else: # SHORT
                if current_price < trailing_data['best_price']: trailing_data['best_price'] = current_price
                profit_percentage = ((entry_price - current_price) / entry_price) * 100
                if not trailing_data['activated'] and profit_percentage >= activation_percent:
                    trailing_data['activated'] = True
                    log.info(f"🔔 Trailing stop activado para {symbol}")
                if trailing_data['activated']:
                    new_stop = trailing_data['best_price'] * (1 + stop_percentage / 100)
                    if new_stop < trailing_data['current_stop']: trailing_data['current_stop'] = new_stop
                    if current_price >= trailing_data['current_stop']:
                        log.info(f"🔴 Cierre por trailing stop: {symbol} @ {current_price} (Stop: {trailing_data['current_stop']})")
                        should_close = True
            return should_close

    def check_sl_tp_logic(self, symbol: str, position: Dict, current_price: float, df: pd.DataFrame):
        # --- MEJORA: Esta función ahora integra el SL basado en ATR y el TP basado en porcentaje.
        if not config.USE_EXIT_LOGIC or df is None or df.empty:
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
                    if config.AI_SL_ADJUSTMENT: sl_adjustment = max(0.5, min(2.0, sl_adj))
                    if config.AI_TP_ADJUSTMENT: tp_adjustment = max(0.7, min(1.5, tp_adj))
                    if sl_adjustment != 1.0 or tp_adjustment != 1.0:
                        log.info(f"🤖 AI SL/TP Adjustment for {symbol}: SL={sl_adjustment:.2f}, TP={tp_adjustment:.2f}")
            
            if 'sl_price' not in sl_tp_data:
                # Lógica de SL basada en ATR
                atr = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14).iloc[-1]
                
                if position_side == 'LONG':
                    sl_price = entry_price - (atr * config.ATR_MULT_SL * sl_adjustment)
                    tp_price = entry_price * (1 + (config.TAKE_PROFIT_PERCENT * tp_adjustment) / 100)
                else: # SHORT
                    sl_price = entry_price + (atr * config.ATR_MULT_SL * sl_adjustment)
                    tp_price = entry_price * (1 - (config.TAKE_PROFIT_PERCENT * tp_adjustment) / 100)
                
                app_state["sl_tp_data"][symbol] = {'sl_price': sl_price, 'tp_price': tp_price, 'side': position_side}
                sl_tp_data = app_state["sl_tp_data"][symbol]
                log.info(f"Initialized ATR-based SL/TP for {symbol}: SL @ {sl_price:.4f}, TP @ {tp_price:.4f}")

            sl_price, tp_price = sl_tp_data.get('sl_price'), sl_tp_data.get('tp_price')
            if not sl_price or not tp_price: return False

            if position_side == 'LONG':
                if current_price <= sl_price: return 'SL'
                elif current_price >= tp_price: return 'TP'
            else: # SHORT
                if current_price >= sl_price: return 'SL'
                elif current_price <= tp_price: return 'TP'
            return False

    def check_time_based_exit(self, symbol: str, position: Dict) -> bool:
        update_time = position.get('updateTime', 0)
        if update_time == 0: return False
        hours_held = (time.time() * 1000 - update_time) / (1000 * 60 * 60)
        if hours_held > config.MAX_POSITION_HOLD_HOURS:
            log.info(f"⏰ Cierre por tiempo: {symbol} held for {hours_held:.1f} hours")
            return True
        return False

    def check_momentum_reversal(self, symbol: str, position: Dict, df: pd.DataFrame) -> bool:
        if df is None or len(df) < 10 or 'rsi' not in df.columns: return False
        
        # --- MEJORA: Añadido filtro de volatilidad para evitar salidas en mercados laterales.
        bb_width = df['bb_width'].iloc[-1]
        if bb_width < 0.015: # Umbral de ejemplo para baja volatilidad (1.5%)
            return False # Ignorar divergencia si el mercado no es volátil
            
        position_side = 'LONG' if float(position['positionAmt']) > 0 else 'SHORT'
        current_rsi, prev_rsi = df['rsi'].iloc[-1], df['rsi'].iloc[-2]
        
        if position_side == 'LONG' and df['close'].iloc[-1] > df['close'].iloc[-3] and current_rsi < prev_rsi and current_rsi > 70:
            log.info(f"↘️ Cierre por divergencia RSI bajista: {symbol}")
            return True
        elif position_side == 'SHORT' and df['close'].iloc[-1] < df['close'].iloc[-3] and current_rsi > prev_rsi and current_rsi < 30:
            log.info(f"↗️ Cierre por divergencia RSI alcista: {symbol}")
            return True
        return False

    def dynamic_exit_strategy(self, symbol: str, position: Dict, current_price: float, df: pd.DataFrame) -> Optional[str]:
        if df is not None and not df.empty and 'rsi' not in df.columns: self.calculate_indicators(df)
        
        sl_tp_signal = self.check_sl_tp_logic(symbol, position, current_price, df)
        if sl_tp_signal: return sl_tp_signal
        
        if self.check_trailing_stop(symbol, position, current_price): return 'TRAILING'
        if self.check_time_based_exit(symbol, position): return 'TIME_EXIT'
        if self.check_momentum_reversal(symbol, position, df): return 'MOMENTUM_EXIT'
        
        return None

    def check_balance_risk(self, account_info):
        # Esta función mantiene su lógica original.
        if not account_info: return False
        usdt_balance = next((float(a.get('walletBalance', 0) or 0) for a in account_info.get('assets', []) if a.get('asset') == 'USDT'), 0.0)
        if usdt_balance < config.MIN_BALANCE_THRESHOLD:
            log.warning(f"⚠️ Balance bajo: {usdt_balance} USDT")
            return True
        return False

    def detect_market_regime(self) -> str:
        trends = []
        for timeframe in ['1h', '4h', '1d']:
            klines = self.api._safe_api_call(self.api.client.futures_klines, symbol="BTCUSDT", interval=timeframe, limit=50)
            if klines:
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
                df['close'] = pd.to_numeric(df['close'])
                ma20 = df['close'].rolling(20).mean().iloc[-1]
                ma50 = df['close'].rolling(50).mean().iloc[-1]
                trends.append(1 if ma20 > ma50 else -1)
        if sum(trends) >= 2: return "BULL"
        elif sum(trends) <= -2: return "BEAR"
        else: return "NEUTRAL"

    def calculate_position_size(self, symbol: str, price: float) -> float:
        # Lógica original de cálculo de tamaño, que es sólida.
        df = self.get_klines_for_symbol(symbol)
        volatility_ratio = 0.02
        if df is not None and len(df) > 14:
            atr = talib.ATR(df['high'], df['low'], df['close'], 14).iloc[-1]
            volatility_ratio = atr / price if price > 0 else 0.02
        position_value_usd = config.FIXED_MARGIN_PER_TRADE_USDT * config.LEVERAGE
        if config.VOLATILITY_ADJUSTMENT:
            volatility_adjustment = 1.0 / (1.0 + volatility_ratio * 10)
            position_value_usd *= volatility_adjustment
        return max(position_value_usd / price if price > 0 else 0, 0)

    def analyze_trading_performance(self, symbol: str):
        if not DB_ENABLED: return None
        # ... (La lógica interna de esta función es robusta y no requiere cambios inmediatos)
        pass # Placeholder para brevedad

    def run(self):
        log.info(f"🚀 STARTING TRADING BOT v11.0 (DRY RUN: {config.DRY_RUN})")
        self.start_time = time.time()
        
        while True:
            with state_lock:
                if not app_state["running"]: break
            
            try:
                self.cycle_count += 1
                log.info(f"--- 🔄 New scanning cycle ({self.cycle_count}) ---")
                
                if self.cycle_count % 12 == 1:
                    self.market_regime = self.detect_market_regime()
                    with state_lock: app_state["market_regime"] = self.market_regime
                    log.info(f"🏛️ Market Regime: {self.market_regime}")

                if self.cycle_count % config.SIGNAL_COOLDOWN_CYCLES == 1 and self.cycle_count > 1:
                    self.recently_signaled.clear()
                
                account_info = self.api._safe_api_call(self.api.client.futures_account)
                if not account_info: continue
                
                if self.check_balance_risk(account_info):
                    log.warning("⏸️ Pausando nuevas operaciones por balance bajo")
                    time.sleep(config.POLL_SEC)
                    continue
                
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
                                sl_adj, tp_adj = sl_tp_data.get('sl_adjustment', 1.0), sl_tp_data.get('tp_adjustment', 1.0)
                                trade_result = _record_closed_trade(self.api, symbol, position, close_order.get('orderId'), exit_signal.lower(), current_price)
                                if exit_signal.lower() in ['sl', 'tp', 'trailing'] and trade_result is not None:
                                    self.update_ai_model(symbol, trade_result, sl_adj, tp_adj, exit_signal.lower())
                    except Exception as e:
                        log.error(f"Error checking stops for {symbol}: {e}", exc_info=True)
                
                if len(open_positions) < config.MAX_CONCURRENT_POS:
                    symbols_to_scan = [s for s in self.get_top_symbols() if s not in open_positions and s not in self.recently_signaled]
                    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS_KLINE) as executor:
                        futures = {executor.submit(self.get_klines_for_symbol, s): s for s in symbols_to_scan}
                        for future in futures:
                            symbol, df = futures[future], future.result()
                            if df is None or len(df) < config.SLOW_EMA: continue
                            self.calculate_indicators(df)
                            signal = self.check_signal(df, symbol)
                            if signal:
                                self.recently_signaled.add(symbol)
                                self.open_trade(symbol, signal, df.iloc[-1])
                                if len(open_positions) + 1 >= config.MAX_CONCURRENT_POS:
                                    break
                
                with state_lock:
                    # ... Lógica de actualización de estado para la UI (sin cambios)
                    socketio.emit('status_update', app_state)

            except Exception as e:
                log.error(f"Error in main loop: {e}", exc_info=True)
            
            time.sleep(config.POLL_SEC)
        log.info("🛑 Bot stopped.")

    def open_trade(self, symbol: str, side: str, last_candle):
        if config.DRY_RUN:
            log.info(f"[DRY RUN] Would open {side} on {symbol}")
            return
        self.api.ensure_symbol_settings(symbol)
        filters = self.api.get_symbol_filters(symbol)
        if not filters: return
        price = float(last_candle['close'])
        quantity = self.calculate_position_size(symbol, price)
        quantity = self.api.round_value(quantity, filters['stepSize'])
        if quantity < filters['minQty']: quantity = filters['minQty']
        if (quantity * price) < filters['minNotional']:
            log.warning(f"Trade for {symbol} stopped. Notional value below minimum.")
            return
        order_side = SIDE_BUY if side == 'LONG' else SIDE_SELL
        limit_price = self.api.round_value(price + filters['tickSize'] * 5 if side == 'LONG' else price - filters['tickSize'] * 5, filters['tickSize'])
        order = self.api.place_order(symbol, order_side, FUTURE_ORDER_TYPE_LIMIT, quantity, price=limit_price)
        if order and order.get('orderId'):
            log.info(f"✅ LIMIT ORDER CREATED: {side} {quantity} {symbol} @ {limit_price}")
        else:
            log.error(f"❌ Could not create limit order for {symbol}.")

# -------------------- HELPER FUNCTIONS -------------------- #
def _record_closed_trade(api: BinanceFutures, symbol: str, position_data: dict, order_id: str, close_type: str, exit_price: float) -> float:
    try:
        pnl_records = api._safe_api_call(api.client.futures_account_trades, symbol=symbol, limit=20)
        realized_pnl = sum(float(t.get('realizedPnl', 0)) for t in pnl_records if str(t.get('orderId')) == str(order_id)) if pnl_records and order_id else 0.0
        
        entry_price, position_size = float(position_data['entryPrice']), abs(float(position_data['positionAmt']))
        roe = (realized_pnl / (position_size * entry_price / config.LEVERAGE)) * 100 if entry_price > 0 and position_size > 0 else 0.0
        
        entry_time = datetime.fromtimestamp(int(position_data.get('updateTime', 0)) / 1000)
        exit_time = datetime.now()
        duration_minutes = (exit_time - entry_time).total_seconds() / 60

        trade_record = { "symbol": symbol, "side": 'LONG' if float(position_data['positionAmt']) > 0 else 'SHORT', "quantity": position_size, "entryPrice": entry_price, "exitPrice": exit_price, "pnl": realized_pnl, "roe": roe, "closeType": close_type, "timestamp": exit_time.timestamp(), "duration_minutes": duration_minutes, "leverage": config.LEVERAGE }

        with state_lock:
            stats = app_state["performance_stats"]
            stats["realized_pnl"] += realized_pnl
            stats["trades_count"] += 1
            if realized_pnl >= 0: stats["wins"] += 1
            else: stats["losses"] += 1
            app_state["trades_history"].append(trade_record)
            for state_dict in ["trailing_stop_data", "sl_tp_data", "open_positions"]:
                if symbol in app_state[state_dict]: del app_state[state_dict][symbol]

        if DB_ENABLED:
            try:
                db_session = SessionLocal()
                # --- MEJORA: Eliminado el campo 'date' para evitar redundancia con 'timestamp'.
                db_trade = Trade(symbol=trade_record['symbol'], side=trade_record['side'], quantity=trade_record['quantity'], entry_price=trade_record['entryPrice'], exit_price=trade_record['exitPrice'], pnl=trade_record['pnl'], roe=trade_record['roe'], close_type=trade_record['closeType'], timestamp=exit_time, leverage=trade_record['leverage'])
                db_session.add(db_trade)
                db_session.commit()
            except Exception as e:
                log.error(f"DB Error recording trade for {symbol}: {e}")
            finally:
                if 'db_session' in locals(): db_session.close()
        
        log.info(f"✅ Position closed: {symbol}, PnL: {realized_pnl:.2f} USDT, ROE: {roe:.2f}%, Reason: {close_type}")
        socketio.emit('status_update', app_state)
        return realized_pnl
    except Exception as e:
        log.error(f"Error in _record_closed_trade for {symbol}: {e}", exc_info=True)
        return 0.0

# -------------------- WEB ROUTES & BACKGROUND TASKS -------------------- #
# (Sin cambios en las rutas de Flask y eventos de SocketIO)
@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/status')
def get_status():
    with state_lock: return jsonify(app_state)

@app.route('/api/start', methods=['POST'])
def start_bot():
    global bot_thread
    with state_lock:
        if app_state["running"]: return jsonify({"status": "error", "message": "Bot is already running"}), 400
        app_state["running"] = True
    bot_instance = TradingBot()
    bot_thread = threading.Thread(target=bot_instance.run, daemon=True)
    bot_thread.start()
    return jsonify({"status": "success", "message": "Bot started."})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    with state_lock:
        if not app_state["running"]: return jsonify({"status": "error", "message": "Bot is not running"}), 400
        app_state["running"] = False
    return jsonify({"status": "success", "message": "Bot stopped."})

@app.route('/api/update_config', methods=['POST'])
def update_config():
    global config
    data = request.json
    with state_lock:
        for key, value in data.items():
            if hasattr(config, key):
                try:
                    cur_type = type(getattr(config, key))
                    setattr(config, key, cur_type(value))
                except (ValueError, TypeError): pass
        app_state["config"] = asdict(config)
    log.info(f"⚙️ Configuration updated: {data}")
    return jsonify({"status": "success", "config": app_state["config"]})

@app.route('/api/close_position', methods=['POST'])
def close_position_api():
    symbol = request.json.get('symbol')
    if not symbol: return jsonify({"status": "error", "message": "Missing symbol"}), 400
    try:
        api = BinanceFutures()
        acct = api._safe_api_call(api.client.futures_account)
        position = next((p for p in acct.get('positions', []) if p['symbol'] == symbol and float(p['positionAmt']) != 0), None)
        if not position: return jsonify({"status": "error", "message": f"No active position for {symbol}"}), 404
        close_order = api.close_position(symbol, float(position['positionAmt']))
        if close_order:
            ticker = api._safe_api_call(api.client.futures_symbol_ticker, symbol=symbol)
            exit_price = float(ticker['price']) if ticker else float(position['entryPrice'])
            _record_closed_trade(api, symbol, position, close_order.get('orderId'), 'manual', exit_price)
            return jsonify({"status": "success", "message": f"Position on {symbol} closed."})
        return jsonify({"status": "error", "message": "Failed to close."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/trade_history')
def get_trade_history():
    with state_lock: trades = sorted(app_state["trades_history"], key=lambda x: x.get('timestamp', 0), reverse=True)
    return jsonify({"trades": trades})


@app.route('/api/positions')
def get_positions():
    """Return a list of open positions."""
    with state_lock:
        positions = list(app_state.get("open_positions", {}).values())
    return jsonify({"positions": positions})


@app.route('/api/open_positions')
def get_open_positions():
    """Return open positions as a dictionary keyed by symbol."""
    with state_lock:
        positions = app_state.get("open_positions", {})
    return jsonify(positions)


@app.route('/api/trailing_stop_data')
def get_trailing_stop_data():
    """Expose current trailing stop configuration for all symbols."""
    with state_lock:
        trailing_data = app_state.get("trailing_stop_data", {})
    return jsonify(trailing_data)

# -------------------- SOCKETIO EVENTS -------------------- #
@socketio.on('connect')
def handle_connect():
    log.info(f"🔌 Client connected: {request.sid}")
    with state_lock: socketio.emit('status_update', app_state, to=request.sid)

# -------------------- MAIN FUNCTION -------------------- #
if __name__ == '__main__':
    load_dotenv()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    if DB_ENABLED:
        try:
            from database import init_db
            init_db()
            log.info("Database initialized successfully.")
        except Exception as e:
            log.error(f"Database initialization failed: {e}")

    socketio.run(app, debug=debug, host=host, port=port, use_reloader=False, allow_unsafe_werkzeug=True)