from __future__ import annotations
"""
Binance Futures Bot - Aplicación Web v12.0 con Gestión de Capital Real
Sistema de trading avanzado con seguimiento de capital real y reinversión de ganancias
Por gregorbc@gmail.com
"""
import os
import time
import math
import logging
import threading
import random
import requests
import pandas as pd
import numpy as np
from collections import deque
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from sqlalchemy import func, case, desc

# Manejar importación de TA-Lib
try:
    import talib
    TALIB_ENABLED = True
    print("✅ TA-Lib encontrado y habilitado")
except ImportError:
    TALIB_ENABLED = False
    print("ADVERTENCIA: TA-Lib no encontrado. Algunos indicadores estarán deshabilitados.")

from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, FUTURE_ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
from binance.exceptions import BinanceAPIException

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS

# Importaciones para el modelo de aprendizaje profundo Por gregorbc@gmail.com
try:
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Dense
    from tensorflow.keras.optimizers import Adam
    DRL_ENABLED = True
except ImportError:
    DRL_ENABLED = False
    print("ADVERTENCIA: TensorFlow no encontrado. Las características de Deep Learning estarán deshabilitadas. Por gregorbc@gmail.com")

# Importación de base de datos con manejo de errores
DB_ENABLED = False
try:
    from database import SessionLocal, Trade, PerformanceMetrics, AccountBalance, get_db_session_with_retry, execute_with_retry, check_db_connection
    DB_ENABLED = True
    print("✅ Base de datos habilitada")
except ImportError as e:
    DB_ENABLED = False
    print(f"ADVERTENCIA: 'database.py' no encontrado. Las características de base de datos estarán deshabilitadas. Error: {e}")
except Exception as e:
    DB_ENABLED = False
    print(f"ADVERTENCIA: Error al inicializar base de datos: {e}")

# -------------------- CONFIGURACIÓN -------------------- #
@dataclass
class CONFIG:
    # Configuración Global Por gregorbc@gmail.com
    LEVERAGE: int = 20  # Cambiado de 10 a 20x
    MAX_CONCURRENT_POS: int = 3
    NUM_SYMBOLS_TO_SCAN: int = 400  # Reducido para mejor rendimiento
    # Configuración de Estrategia Por gregorbc@gmail.com
    ATR_MULT_SL: float = 2.2
    ATR_MULT_TP: float = 3.5
    # Configuración de Trailing Stop Por gregorbc@gmail.com
    TRAILING_STOP_ACTIVATION: float = 0.8
    TRAILING_STOP_PERCENTAGE: float = 0.35
    # Configuración de SL/TP Fijo Por gregorbc@gmail.com
    USE_FIXED_SL_TP: bool = True
    STOP_LOSS_PERCENT: float = 1.0  # **Mejora:** Reducido a 1.0 para 20x leverage para una gestión de riesgo más estricta.
    TAKE_PROFIT_PERCENT: float = 2.5  # **Mejora:** Reducido para 20x leverage.
    # Configuración de Ajuste de IA Por gregorbc@gmail.com
    AI_SL_ADJUSTMENT: bool = True
    AI_TP_ADJUSTMENT: bool = True
    AI_TRAILING_ADJUSTMENT: bool = True
    AI_VOLATILITY_FACTOR: float = 1.5
    # Configuración Fija Por gregorbc@gmail.com
    MARGIN_TYPE: str = "CROSSED"
    MIN_24H_VOLUME: float = 5_000_000  # Aumentado para mayor liquidez
    EXCLUDE_SYMBOLS: tuple = ("BTCDOMUSDT", "DEFIUSDT", "USDCUSDT", "TUSDUSDT", "BUSDUSDT", "USTUSDT")
    # **Mejora:** Nueva lista negra con símbolos de alto riesgo.
    BLACKLIST_SYMBOLS: tuple = ("PROMPTUSDT", "PLAYUSDT", "LDOUSDT", "1000FLOKIUSDT",
                               "QTUMUSDT", "LRCUSDT", "GALAUSDT", "SKLUSDT", "HBARUSDT", "CUSDT",
                               "SOLUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "SHIBUSDT",
                               "TAUSDT", "NEWTUSDT", "KERNELUSDT", "LPTUSDT", "DOTUSDT", "LINKUSDT",
                               "AAVEUSDT", "UNIUSDT", "TIAUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
                               "SEIUSDT", "INJUSDT", "NEARUSDT", "FTMUSDT")  # **Mejora:** Añadidos más pares para reducir el riesgo.
    TIMEFRAME: str = "5m"
    CANDLES_LIMIT: int = 100
    FAST_EMA: int = 8   # Ajustado para 20x
    SLOW_EMA: int = 21  # Ajustado para 20x
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9
    RSI_PERIOD: int = 14
    STOCH_PERIOD: int = 14
    POLL_SEC: float = 8.0  # Reducido para mayor reactividad
    DRY_RUN: bool = False
    MAX_WORKERS_KLINE: int = 8  # Reducido para 20x
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE: str = "bot_v12_20x_usdt.log"
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"
    SIGNAL_COOLDOWN_CYCLES: int = 25  # Reducido para 20x
    # Monitoreo de balance - Gestión de capital real Por gregorbc@gmail.com
    MIN_BALANCE_THRESHOLD: float = 10.0  # Reducido para 20x
    RISK_PER_TRADE_PERCENT: float = 1.5  # **Mejora:** Reducido a 1.5% para una gestión de riesgo más estricta.
    # Configuración de conexión Por gregorbc@gmail.com
    MAX_API_RETRIES: int = 3
    API_RETRY_DELAY: float = 1.0
    # Configuración de Mejora de IA Por gregorbc@gmail.com
    AI_LEARNING_RATE: float = 0.02
    AI_EXPLORATION_RATE: float = 0.06
    AI_VOLATILITY_THRESHOLD: float = 2.5
    AI_TREND_STRENGTH_THRESHOLD: float = 25.0
    # Configuración de Estrategia Mejorada Por gregorbc@gmail.com
    MIN_SIGNAL_STRENGTH: float = 0.40  # **Mejora:** Aumentado para 20x
    MAX_POSITION_HOLD_HOURS: int = 2    # **Mejora:** Reducido para 20x para evitar posiciones estancadas.
    VOLATILITY_ADJUSTMENT: bool = True
    # Gestión de Riesgo Mejorada Por gregorbc@gmail.com
    MAX_DAILY_LOSS_PERCENT: float = 6.0  # **Mejora:** Reducido para 20x.
    MAX_DRAWDOWN_PERCENT: float = 10.0   # **Mejora:** Reducido para 20x.
    # Configuración de símbolos optimizada Por gregorbc@gmail.com
    SYMBOL_SPECIFIC_SETTINGS: Dict = field(default_factory=lambda: {
        "BTCUSDT": {"risk_multiplier": 0.4, "max_leverage": 20, "enabled": True},
        "ETHUSDT": {"risk_multiplier": 0.5, "max_leverage": 20, "enabled": True},
        "XRPUSDT": {"risk_multiplier": 1.0, "max_leverage": 20},
        "DOGEUSDT": {"risk_multiplier": 0.8, "max_leverage": 20},
        "MATICUSDT": {"risk_multiplier": 1.0, "max_leverage": 20},
        "SHIBUSDT": {"risk_multiplier": 0.7, "max_leverage": 20},
        "LTCUSDT": {"risk_multiplier": 0.9, "max_leverage": 20},
        "TRXUSDT": {"risk_multiplier": 1.0, "max_leverage": 20},
        "DOTUSDT": {"risk_multiplier": 0.8, "max_leverage": 20},
        "LINKUSDT": {"risk_multiplier": 0.8, "max_leverage": 20},
        "BCHUSDT": {"risk_multiplier": 0.6, "max_leverage": 20, "enabled": True},
        "AVAXUSDT": {"risk_multiplier": 0.8, "max_leverage": 20},
        "XLMUSDT": {"risk_multiplier": 1.0, "max_leverage": 20},
        "ATOMUSDT": {"risk_multiplier": 0.8, "max_leverage": 20},
        "ETCUSDT": {"risk_multiplier": 0.9, "max_leverage": 20},
        "ADAUSDT": {"risk_multiplier": 0.6, "max_leverage": 20, "enabled": True},
        "ALGOUSDT": {"risk_multiplier": 1.0, "max_leverage": 20},
        "VETUSDT": {"risk_multiplier": 1.0, "max_leverage": 20},
        "THETAUSDT": {"risk_multiplier": 0.9, "max_leverage": 20},
        "FILUSDT": {"risk_multiplier": 0.8, "max_leverage": 20},
        "XTZUSDT": {"risk_multiplier": 0.9, "max_leverage": 20},
        "EOSUSDT": {"risk_multiplier": 0.9, "max_leverage": 20},
        "AAVEUSDT": {"risk_multiplier": 0.5, "max_leverage": 20, "enabled": True},
        "UNIUSDT": {"risk_multiplier": 0.7, "max_leverage": 20},
        # Nuevos símbolos populares con USDT
        "SOLUSDT": {"risk_multiplier": 0.6, "max_leverage": 20, "enabled": True},
        "BNBUSDT": {"risk_multiplier": 0.5, "max_leverage": 20, "enabled": True},
        "APTUSDT": {"risk_multiplier": 1.2, "max_leverage": 20},
        "ARBUSDT": {"risk_multiplier": 1.1, "max_leverage": 20},
        "OPUSDT": {"risk_multiplier": 1.0, "max_leverage": 20},
        "SUIUSDT": {"risk_multiplier": 1.2, "max_leverage": 20},
        "SEIUSDT": {"risk_multiplier": 1.3, "max_leverage": 20},
        "INJUSDT": {"risk_multiplier": 0.9, "max_leverage": 20},
        "NEARUSDT": {"risk_multiplier": 0.8, "max_leverage": 20},
        "FTMUSDT": {"risk_multiplier": 1.1, "max_leverage": 20},
    })
    ENABLE_DYNAMIC_LEVERAGE: bool = True
    VOLUME_WEIGHTED_SIGNALS: bool = True
    MIN_VOLUME_CONFIRMATION: float = 0.35  # Ajustado para 20x
    # Configuración para timeframe múltiple Por gregorbc@gmail.com
    HIGHER_TIMEFRAME_CONFIRMATION: bool = True
    HIGHER_TIMEFRAME: str = "15m"  # Cambiado a 15m para 20x
    BTC_CORRELATION_FILTER: bool = True
    # Configuración de capital real y reinversión Por gregorbc@gmail.com
    MIN_NOTIONAL_OVERRIDE: float = 5.0
    REINVESTMENT_ENABLED: bool = True
    REINVESTMENT_THRESHOLD: float = 0.4  # Reducido para 20x
    CAPITAL_GROWTH_TARGET: float = 0.8   # Reducido para 20x
    INITIAL_CAPITAL: float = 20.0
    CAPITAL_UPDATE_INTERVAL: int = 25    # Reducido para 20x
    # Nuevos parámetros para 20x leverage
    MIN_ADX_FOR_TREND: float = 13.0      # Aumentado para 20x
    RSI_OVERBOUGHT: float = 68.0         # Ajustado para 20x
    RSI_OVERSOLD: float = 32.0           # Ajustado para 20x
    MAX_VOLATILITY_PERCENT: float = 30.0  # Límite de volatilidad para 20x
    # Nuevos parámetros para gestión de riesgo mejorada
    MAX_CONSECUTIVE_LOSSES: int = 3      # Máximas pérdidas consecutivas antes de pausar
    LOW_VOLUME_THRESHOLD: float = 0.3    # Umbral de volumen bajo (30% del promedio)
    MAX_SPREAD_PERCENT: float = 0.1      # Spread máximo permitido (0.1%)
    
    def __post_init__(self):
        """Validar configuraciones requeridas"""
        required_configs = [
            'STOCH_PERIOD', 'RSI_PERIOD', 'MACD_FAST', 'MACD_SLOW', 'MACD_SIGNAL',
            'FAST_EMA', 'SLOW_EMA', 'LEVERAGE', 'MAX_CONCURRENT_POS'
        ]
        
        for config_name in required_configs:
            if not hasattr(self, config_name):
                raise ValueError(f"❌ Configuración requerida faltante: {config_name}")

config = CONFIG()

# -------------------- CONFIGURACIÓN DEL OPTIMIZADOR DE ESTRATEGIA -------------------- #
@dataclass
class STRATEGY_OPTIMIZER:
    OPTIMIZATION_INTERVAL: int = 15      # Reducido para 20x
    MIN_TRADES_FOR_ANALYSIS: int = 5     # Reducido para 20x
    LEVERAGE_ADJUSTMENT_STEP: int = 5
    MAX_LEVERAGE: int = 20               # Máximo 20x
    MIN_LEVERAGE: int = 10               # Mínimo 10x
    VOLATILITY_THRESHOLD: float = 2.8    # Aumentado para 20x

strategy_optimizer = STRATEGY_OPTIMIZER()

# -------------------- GESTOR DE CAPITAL -------------------- #
class CapitalManager:
    """Gestor de capital real con reinversión de ganancias Por gregorbc@gmail.com"""

    def __init__(self, api):
        self.api = api
        self.current_balance = 0.0
        self.initial_balance = 0.0
        self.last_balance_update = 0
        self.total_profit = 0.0
        self.reinvested_profit = 0.0

    def get_real_balance(self) -> float:
        """Obtener el balance real de la cuenta Por gregorbc@gmail.com"""
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
            log.error(f"Error obteniendo balance real: {e} Por gregorbc@gmail.com")
        return 0.0

    def update_balance(self, force: bool = False) -> bool:
        """Actualizar el balance real Por gregorbc@gmail.com"""
        current_time = time.time()
        if force or (current_time - self.last_balance_update > 240):  # Reducido a 4 min para 20x
            new_balance = self.get_real_balance()
            if new_balance > 0:
                if self.current_balance == 0:
                    self.initial_balance = new_balance
                    log.info(f"💰 Capital inicial: {new_balance:.2f} USDT (20x leverage) Por gregorbc@gmail.com")

                self.current_balance = new_balance
                self.last_balance_update = current_time

                # Calcular profit total
                self.total_profit = self.current_balance - self.initial_balance

                # Guardar en base de datos con manejo de errores mejorado
                self._save_balance_to_db()
                return True
        return False

    def _save_balance_to_db(self):
        """Guardar balance en base de datos con reintentos Por gregorbc@gmail.com"""
        if not DB_ENABLED:
            return

        def save_operation():
            db = get_db_session_with_retry(max_retries=2)
            if db:
                try:
                    balance_record = AccountBalance(
                        balance=self.current_balance,
                        total_profit=self.total_profit,
                        reinvested_profit=self.reinvested_profit
                    )
                    db.add(balance_record)
                    db.commit()
                    log.info(f"💾 Balance guardado en DB: {self.current_balance:.2f} USDT")
                except Exception as e:
                    log.error(f"Error guardando balance en DB: {e} Por gregorbc@gmail.com")
                    db.rollback()
                finally:
                    db.close()

        # Ejecutar con reintentos
        execute_with_retry(save_operation, max_retries=2, retry_delay=1)

    def should_reinvest(self, profit: float) -> bool:
        """Decidir si reinvertir las ganancias Por gregorbc@gmail.com"""
        if not config.REINVESTMENT_ENABLED:
            return False

        # Reinvertir si la ganancia supera el threshold
        return profit >= config.REINVESTMENT_THRESHOLD

    def reinvest_profit(self, profit: float):
        """Reinvertir las ganancias en el capital Por gregorbc@gmail.com"""
        if profit > 0 and self.should_reinvest(profit):
            self.reinvested_profit += profit
            log.info(f"🔄 Reinvirtiendo {profit:.2f} USDT en el capital (20x) Por gregorbc@gmail.com")
            # El balance se actualizará automáticamente en el próximo ciclo

    def get_performance_stats(self) -> Dict:
        """Obtener estadísticas de rendimiento Por gregorbc@gmail.com"""
        return {
            "current_balance": self.current_balance,
            "initial_balance": self.initial_balance,
            "total_profit": self.total_profit,
            "reinvested_profit": self.reinvested_profit,
            "profit_percentage": (self.total_profit / self.initial_balance * 100) if self.initial_balance > 0 else 0,
            "daily_target": config.CAPITAL_GROWTH_TARGET,
            "leverage": config.LEVERAGE
        }

# -------------------- MEJORAS DE IA -------------------- #
@dataclass
class AIModel:
    """Modelo de IA para optimización de parámetros de trading Por gregorbc@gmail.com"""
    learning_rate: float = config.AI_LEARNING_RATE
    exploration_rate: float = config.AI_EXPLORATION_RATE
    q_table: Dict = field(default_factory=dict)

    def get_action(self, state: str) -> Tuple[float, float]:
        """Obtiene la mejor acción (sl_adj, tp_adj) para un estado dado Por gregorbc@gmail.com"""
        if state not in self.q_table or random.random() < self.exploration_rate:
            sl_adj = random.uniform(0.7, 1.3)
            tp_adj = random.uniform(0.8, 1.5)
            self.q_table[state] = (sl_adj, tp_adj, 0)
        return self.q_table[state][0], self.q_table[state][1]

    def update_model(self, state: str, reward: float, sl_adj: float, tp_adj: float):
        """Actualiza el modelo Q-learning con la recompensa obtenida Por gregorbc@gmail.com"""
        if state in self.q_table:
            current_reward = self.q_table[state][2]
            new_reward = current_reward + self.learning_rate * (reward - current_reward)
            self.q_table[state] = (sl_adj, tp_adj, new_reward)

@dataclass
class MarketAnalyzer:
    """Analizador de condiciones del mercado Por gregorbc@gmail.com"""
    volatility_threshold: float = config.AI_VOLATILITY_THRESHOLD
    trend_strength_threshold: float = config.AI_TREND_STRENGTH_THRESHOLD

    def analyze_market_conditions(self, symbol: str, df: pd.DataFrame) -> Dict[str, float]:
        """Analiza las condiciones del mercado para un símbolo Por gregorbc@gmail.com"""
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

# -------------------- ANALIZADOR DE RENDIMIENTO -------------------- #
@dataclass
class PerformanceAnalyzer:
    """Analizador de rendimiento basado en datos históricos Por gregorbc@gmail.com"""

    def __init__(self, db_session=None):
        self.db_session = db_session
        self.symbol_performance = {}
        self._load_performance_data()

    def _load_performance_data(self):
        """Cargar datos de rendimiento históricos con manejo de errores Por gregorbc@gmail.com"""
        if not DB_ENABLED:
            return

        def load_operation():
            db = get_db_session_with_retry(max_retries=2)
            if not db:
                return
                
            try:
                trades = db.query(Trade).all()
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
                log.error(f"Error cargando datos de rendimiento: {e} Por gregorbc@gmail.com")
            finally:
                db.close()

        execute_with_retry(load_operation, max_retries=2, retry_delay=1)

    def get_symbol_risk_factor(self, symbol: str) -> float:
        """Calcular factor de riesgo para un símbolo basado en historial Por gregorbc@gmail.com"""
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

# -------------------- NOTIFICADOR DE TELEGRAM MEJORADO -------------------- #
class TelegramNotifier:
    """Sistema avanzado de notificaciones por Telegram Por gregorbc@gmail.com"""
    
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)
        
        if self.enabled:
            log.info(f"✅ Bot de Telegram configurado: Chat ID {self.chat_id}")
        else:
            log.warning("⚠️ Bot de Telegram no configurado. Agrega TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env")

    def send_message(self, message: str, parse_mode: str = "HTML"):
        """Envía mensaje a Telegram con manejo de errores"""
        if not self.enabled:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            return True
            
        except requests.exceptions.RequestException as e:
            log.error(f"❌ Error enviando mensaje por Telegram: {e}")
            return False
        except Exception as e:
            log.error(f"❌ Error inesperado en Telegram: {e}")
            return False

    def notify_trade_opened(self, symbol: str, side: str, quantity: float, 
                          price: float, balance: float, leverage: int = 20):
        """Notifica apertura de trade"""
        emoji = "🟢" if side == "LONG" else "🔴"
        message = f"""
{emoji} <b>TRADE ABIERTO ({leverage}x)</b>

📈 <b>Símbolo:</b> {symbol}
🎯 <b>Dirección:</b> {side}
📊 <b>Cantidad:</b> {quantity:.4f}
💰 <b>Precio Entrada:</b> ${price:.6f}
💵 <b>Valor:</b> ${quantity * price:.2f}
⚡ <b>Apalancamiento:</b> {leverage}x
🏦 <b>Capital:</b> ${balance:.2f} USDT

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

    def notify_trade_closed(self, symbol: str, pnl: float, reason: str, 
                          balance: float, entry_price: float, exit_price: float,
                          quantity: float, leverage: int = 20):
        """Notifica cierre de trade con detalles completos"""
        emoji = "🟢" if pnl >= 0 else "🔴"
        roe = (pnl / (quantity * entry_price / leverage)) * 100 if entry_price > 0 else 0
        
        message = f"""
{emoji} <b>TRADE CERRADO ({leverage}x)</b>

📈 <b>Símbolo:</b> {symbol}
🎯 <b>Resultado:</b> {'GANANCIA' if pnl >= 0 else 'PÉRDIDA'}
💰 <b>P&L:</b> ${pnl:+.2f} USDT
📊 <b>ROE:</b> {roe:+.2f}%
🔍 <b>Razón:</b> {reason}

📥 <b>Precio Entrada:</b> ${entry_price:.6f}
📤 <b>Precio Salida:</b> ${exit_price:.6f}
📦 <b>Cantidad:</b> {quantity:.4f}

🏦 <b>Capital Actual:</b> ${balance:.2f} USDT
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

    def notify_balance_update(self, balance: float, profit: float, 
                            profit_percentage: float, leverage: int = 20):
        """Notifica actualización de balance"""
        message = f"""
💰 <b>ACTUALIZACIÓN DE CAPITAL ({leverage}x)</b>

🏦 <b>Balance Actual:</b> ${balance:.2f} USDT
📈 <b>Profit Total:</b> ${profit:+.2f} USDT
📊 <b>Rentabilidad:</b> {profit_percentage:+.2f}%

⚡ <b>Apalancamiento:</b> {leverage}x
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

    def notify_reinvestment(self, amount: float, new_balance: float, leverage: int = 20):
        """Notifica reinversión de ganancias"""
        message = f"""
🔄 <b>REINVERSIÓN DE GANANCIAS ({leverage}x)</b>

💵 <b>Monto Reinvertido:</b> ${amount:.2f} USDT
🏦 <b>Nuevo Capital:</b> ${new_balance:.2f} USDT
⚡ <b>Apalancamiento:</b> {leverage}x

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

    def notify_error(self, error_message: str, context: str = ""):
        """Notifica errores críticos"""
        message = f"""
🚨 <b>ERROR CRÍTICO</b>

❌ <b>Error:</b> {error_message}
🔧 <b>Contexto:</b> {context}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

    def notify_warning(self, warning_message: str, context: str = ""):
        """Notifica advertencias"""
        message = f"""
⚠️ <b>ADVERTENCIA</b>

📢 <b>Mensaje:</b> {warning_message}
🔧 <b>Contexto:</b> {context}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

    def notify_market_regime(self, regime: str, description: str = ""):
        """Notifica cambio de régimen de mercado"""
        emoji = "🐂" if regime == "BULL" else "🐻" if regime == "BEAR" else "➡️"
        message = f"""
{emoji} <b>CAMBIO DE RÉGIMEN DE MERCADO</b>

📊 <b>Régimen:</b> {regime}
📝 <b>Descripción:</b> {description}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

    def notify_bot_started(self, leverage: int = 20):
        """Notifica que el bot ha iniciado"""
        message = f"""
🤖 <b>BOT DE TRADING INICIADO</b>

✅ <b>Sistema activado</b>
⚡ <b>Apalancamiento:</b> {leverage}x
🏦 <b>Modo:</b> {'SIMULACIÓN' if config.DRY_RUN else 'REAL'}
⏰ <b>Hora:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📊 <b>Estrategia configurada para 20x leverage</b>
        """
        return self.send_message(message)

# -------------------- MANEJADOR DE COMANDOS DE TELEGRAM -------------------- #
class TelegramCommandHandler:
    """Maneja los comandos recibidos por Telegram Por gregorbc@gmail.com"""
    
    def __init__(self, trading_bot):
        self.bot = trading_bot
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.set_webhook()
        
    def set_webhook(self):
        """Configurar webhook para recibir mensajes"""
        if not self.token:
            return
            
        try:
            # Para desarrollo, usamos polling en lugar de webhook
            log.info("📱 Modo desarrollo: Usando polling para comandos de Telegram")
                
        except Exception as e:
            log.warning(f"⚠️ Error configurando webhook: {e}")

    def handle_command(self, message: dict):
        """Procesar comandos recibidos Por gregorbc@gmail.com"""
        if 'text' not in message or 'chat' not in message:
            return
            
        chat_id = message['chat']['id']
        text = message['text'].strip()
        
        # Comandos básicos
        if text.startswith('/'):
            command = text.split(' ')[0].lower()
            
            if command == '/start':
                self.send_welcome(chat_id)
            elif command == '/status':
                self.send_status(chat_id)
            elif command == '/balance':
                self.send_balance(chat_id)
            elif command == '/positions':
                self.send_positions(chat_id)
            elif command == '/stats':
                self.send_stats(chat_id)
            elif command == '/performance':
                self.send_performance(chat_id)
            elif command == '/stop':
                self.stop_bot(chat_id)
            elif command == '/restart':
                self.restart_bot(chat_id)
            elif command == '/help':
                self.send_help(chat_id)
            else:
                self.send_message(chat_id, "❌ Comando no reconocido. Usa /help para ver comandos disponibles.")

    def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML"):
        """Enviar mensaje a Telegram Por gregorbc@gmail.com"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            log.error(f"Error enviando mensaje: {e}")
            return False

    def send_welcome(self, chat_id: int):
        """Mensaje de bienvenida Por gregorbc@gmail.com"""
        with state_lock:
            status = app_state
            
        message = f"""
🤖 <b>BOT DE TRADING BINANCE FUTURES</b>

✅ <b>Estado:</b> {'🟢 ACTIVO' if status['running'] else '🔴 INACTIVO'}
⚡ <b>Apalancamiento:</b> 20x
🏦 <b>Modo:</b> {'REAL' if not config.DRY_RUN else 'SIMULACIÓN'}
💰 <b>Balance:</b> ${status['balance']:.2f} USDT

<b>📊 Comandos disponibles:</b>
/start - Iniciar bot
/status - Estado del trading  
/balance - Balance y ganancias
/positions - Posiciones abiertas
/stats - Estadísticas
/performance - Rendimiento
/stop - Detener bot
/restart - Reiniciar bot
/help - Ayuda

⏰ <b>Hora:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        self.send_message(chat_id, message)

    def send_status(self, chat_id: int):
        """Enviar estado actual Por gregorbc@gmail.com"""
        with state_lock:
            status = app_state
            
        message = f"""
📊 <b>ESTADO DEL TRADING</b>

✅ <b>Bot:</b> {'🟢 ACTIVO' if status['running'] else '🔴 INACTIVO'}
💰 <b>Balance:</b> ${status['balance']:.2f} USDT
📈 <b>Posiciones abiertas:</b> {len(status['open_positions'])}
🎯 <b>Trades hoy:</b> {status['performance_stats']['trades_count']}

<b>📈 Rendimiento:</b>
🏆 <b>Win Rate:</b> {status['performance_stats']['win_rate']:.1f}%
📊 <b>Profit Factor:</b> {status['performance_stats']['profit_factor']:.2f}
💰 <b>P&L Realizado:</b> ${status['performance_stats']['realized_pnl']:.2f}

⚡ <b>Apalancamiento:</b> 20x
🏛️ <b>Régimen mercado:</b> {status['market_regime']}
        """
        self.send_message(chat_id, message)

    def send_balance(self, chat_id: int):
        """Enviar información de balance Por gregorbc@gmail.com"""
        with state_lock:
            capital_stats = app_state['capital_stats']
            
        message = f"""
💰 <b>INFORMACIÓN DE CAPITAL</b>

🏦 <b>Balance actual:</b> ${capital_stats['current_balance']:.2f} USDT
📈 <b>Profit total:</b> ${capital_stats['total_profit']:+.2f} USDT
📊 <b>Rentabilidad:</b> {capital_stats['profit_percentage']:+.2f}%
🔄 <b>Reinvertido:</b> ${capital_stats['reinvested_profit']:.2f} USDT

⚡ <b>Apalancamiento:</b> 20x
🎯 <b>Objetivo diario:</b> {capital_stats['daily_target']:.1f}%

⏰ <b>Actualizado:</b> {datetime.now().strftime('%H:%M:%S')}
        """
        self.send_message(chat_id, message)

    def send_positions(self, chat_id: int):
        """Enviar posiciones abiertas Por gregorbc@gmail.com"""
        with state_lock:
            positions = app_state['open_positions']
            
        if not positions:
            self.send_message(chat_id, "📭 <b>No hay posiciones abiertas</b>")
            return
            
        message = "📊 <b>POSICIONES ABIERTAS</b>\n\n"
        
        for symbol, position in positions.items():
            side = 'LONG' if float(position['positionAmt']) > 0 else 'SHORT'
            entry_price = float(position['entryPrice'])
            unrealized_pnl = float(position.get('unrealizedProfit', 0))
            
            message += f"""
📈 <b>{symbol}</b>
🎯 <b>Dirección:</b> {side}
💰 <b>Precio entrada:</b> ${entry_price:.6f}
📊 <b>P&L No realizado:</b> ${unrealized_pnl:+.2f}
⚡ <b>Apalancamiento:</b> {position.get('leverage', 20)}x
            """
            
        self.send_message(chat_id, message)

    def send_stats(self, chat_id: int):
        """Enviar estadísticas Por gregorbc@gmail.com"""
        with state_lock:
            stats = app_state['performance_stats']
            
        message = f"""
📈 <b>ESTADÍSTICAS DE TRADING</b>

🎯 <b>Total trades:</b> {stats['trades_count']}
🏆 <b>Win Rate:</b> {stats['win_rate']:.1f}%
✅ <b>Ganadores:</b> {stats['wins']}
❌ <b>Perdedores:</b> {stats['losses']}

💰 <b>P&L Total:</b> ${stats['realized_pnl']:+.2f}
📊 <b>Profit Factor:</b> {stats['profit_factor']:.2f}
⏱️ <b>Duración promedio:</b> {stats['avg_trade_duration']:.1f}m

📈 <b>Avg Win:</b> ${stats['avg_win']:.2f}
📉 <b>Avg Loss:</b> ${stats['avg_loss']:.2f}
        """
        self.send_message(chat_id, message)

    def send_performance(self, chat_id: int):
        """Enviar rendimiento por símbolo Por gregorbc@gmail.com"""
        if not DB_ENABLED:
            self.send_message(chat_id, "❌ Base de datos no habilitada")
            return
            
        try:
            db = get_db_session_with_retry(max_retries=2)
            if not db:
                self.send_message(chat_id, "❌ Error de conexión a base de datos")
                return
                
            symbol_stats = db.query(
                Trade.symbol,
                func.count(Trade.id).label('total_trades'),
                func.sum(case((Trade.pnl > 0, 1), else_=0)).label('winning_trades'),
                func.sum(Trade.pnl).label('total_pnl'),
                func.avg(Trade.pnl).label('avg_pnl')
            ).group_by(Trade.symbol).all()
            
            message = "📊 <b>RENDIMIENTO POR SÍMBOLO</b>\n\n"
            
            for stat in symbol_stats:
                win_rate = (stat.winning_trades / stat.total_trades * 100) if stat.total_trades > 0 else 0
                message += f"""
📈 <b>{stat.symbol}</b>
🎯 <b>Trades:</b> {stat.total_trades}
🏆 <b>Win Rate:</b> {win_rate:.1f}%
💰 <b>P&L Total:</b> ${stat.total_pnl:+.2f}
📊 <b>Avg P&L:</b> ${stat.avg_pnl:+.2f}
                """
                
            self.send_message(chat_id, message)
            
        except Exception as e:
            self.send_message(chat_id, f"❌ Error obteniendo estadísticas: {str(e)}")
        finally:
            if 'db' in locals():
                db.close()

    def stop_bot(self, chat_id: int):
        """Detener el bot Por gregorbc@gmail.com"""
        with state_lock:
            app_state["running"] = False
            
        self.send_message(chat_id, "🛑 <b>Bot detenido</b>\n\nEl bot ha sido detenido exitosamente.")
        log.info("Bot detenido por comando de Telegram")

    def restart_bot(self, chat_id: int):
        """Reiniciar el bot Por gregorbc@gmail.com"""
        self.send_message(chat_id, "🔄 <b>Reiniciando bot...</b>")
        
        # Aquí iría la lógica para reiniciar el bot
        # Esto es más complejo y requiere gestión de hilos
        
        self.send_message(chat_id, "✅ <b>Bot reiniciado</b>")

    def send_help(self, chat_id: int):
        """Enviar ayuda Por gregorbc@gmail.com"""
        message = """
🤖 <b>AYUDA - COMANDOS DISPONIBLES</b>

/start - Iniciar el bot de trading
/status - Estado actual del trading
/balance - Ver balance y ganancias
/positions - Posiciones abiertas actuales
/stats - Estadísticas de performance
/performance - Rendimiento por símbolo
/stop - Detener el bot
/restart - Reiniciar bot
/help - Mostrar esta ayuda

<b>📊 Información adicional:</b>
• El bot opera con 20x leverage
• Modo: {'REAL' if not config.DRY_RUN else 'SIMULACIÓN'}
• Monitorea USDT pairs con alta liquidez

⏰ <b>Soporte:</b> gregorbc@gmail.com
        """
        self.send_message(chat_id, message)

# -------------------- POLLING PARA TELEGRAM -------------------- #
class TelegramPoller:
    """Polling para recibir mensajes en desarrollo Por gregorbc@gmail.com"""
    
    def __init__(self, command_handler: TelegramCommandHandler):
        self.handler = command_handler
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.last_update_id = 0
        self.running = False
        
    def start_polling(self):
        """Iniciar polling en un hijo separado Por gregorbc@gmail.com"""
        if not self.token:
            log.warning("❌ No se puede iniciar polling - Token de Telegram no configurado")
            return
            
        self.running = True
        threading.Thread(target=self._poll_messages, daemon=True).start()
        log.info("✅ Polling de Telegram iniciado")
        
    def stop_polling(self):
        """Detener polling Por gregorbc@gmail.com"""
        self.running = False
        log.info("✅ Polling de Telegram detenido")
        
    def _poll_messages(self):
        """Polling para mensajes nuevos Por gregorbc@gmail.com"""
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.token}/getUpdates"
                params = {'offset': self.last_update_id + 1, 'timeout': 30}
                
                response = requests.get(url, params=params, timeout=35)
                if response.status_code == 200:
                    data = response.json()
                    
                    if data['ok'] and data['result']:
                        for update in data['result']:
                            self.last_update_id = update['update_id']
                            if 'message' in update:
                                self.handler.handle_command(update['message'])
                                
            except requests.exceptions.Timeout:
                # Timeout es normal en polling, continuar
                continue
            except Exception as e:
                log.error(f"Error en polling de Telegram: {e}")
                time.sleep(5)

# -------------------- CONFIGURACIÓN DE APLICACIÓN FLASK -------------------- #
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
CORS(app)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# -------------------- CONFIGURACIÓN DE LOGGING -------------------- #
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

# -------------------- ESTADO GLOBAL -------------------- #
bot_thread = None
_trailing_monitor_thread = None
app_state = {
    "running": False,
    "status_message": "Detenido",
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
        "daily_target": config.CAPITAL_GROWTH_TARGET,
        "leverage": config.LEVERAGE
    }
}
state_lock = threading.Lock()

# -------------------- CLIENTE BINANCE -------------------- #
class BinanceFutures:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError("API keys no configuradas. Establezca las variables de entorno BINANCE_API_KEY and BINANCE_API_SECRET Por gregorbc@gmail.com")

        self.client = Client(api_key, api_secret, testnet=testnet)
        log.info(f"🔧 CONECTADO A BINANCE FUTURES {'TESTNET' if testnet else 'MAINNET'} - 20x LEVERAGE Por gregorbc@gmail.com")

        try:
            self.exchange_info = self.client.futures_exchange_info()
            log.info("✅ Información de exchange cargada exitosamente Por gregorbc@gmail.com")
        except Exception as e:
            log.error(f"❌ Error conectando a Binance: {e} Por gregorbc@gmail.com")
            raise

    def ensure_symbol_settings(self, symbol: str):
        try:
            _ = self._safe_api_call(self.client.futures_change_leverage, symbol=symbol, leverage=int(config.LEVERAGE))
            log.info(f"✅ Apalancamiento configurado a {config.LEVERAGE}x para {symbol} Por gregorbc@gmail.com")
        except Exception as e:
            log.warning(f"Problema al establecer leverage para {symbol}: {e} Por gregorbc@gmail.com")

        try:
            self.client.futures_change_margin_type(symbol=symbol, marginType=config.MARGIN_TYPE)
        except BinanceAPIException as e:
            if e.code == -4046 or "No need to change margin type" in e.message:
                pass
            else:
                log.warning(f"Advertencia al establecer tipo de margen para {symbol}: {e} Por gregorbc@gmail.com")
        except Exception as e:
            log.error(f"Error inesperado al establecer tipo de margen para {symbol}: {e} Por gregorbc@gmail.com")

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
                    log.warning("Error PERCENT_PRICE (-4131) en orden. Mercado volátil or ilíquido. Omitiendo. Por gregorbc@gmail.com")
                    return None
                elif e.code in [-2011, -2021]:
                    log.warning(f"Error de API en orden ({e.code}): {e.message} Por gregorbc@gmail.com")
                else:
                    log.warning(f"Error no crítico de API: {e.code} - {e.message} Por gregorbc@gmail.com")
                    if attempt == config.MAX_API_RETRIES - 1:
                        log.error(f"Error final de API después de todos los reintentos: {e.code} - {e.message} Por gregorbc@gmail.com")
            except Exception as e:
                with state_lock:
                    app_state["connection_metrics"]["api_retries"] += 1
                log.warning(f"Error general en llamada a API: {e} Por gregorbc@gmail.com")
                if attempt == config.MAX_API_RETRIES - 1:
                    log.error(f"Error general final después de todos los reintentos: {e} Por gregorbc@gmail.com")

        return None

    def smart_retry_api_call(self, func, *args, **kwargs):
        """Llamada a API con reintentos inteligentes basados en el tipo de error Por gregorbc@gmail.com"""
        retry_delays = [1, 2, 4, 8, 16]
        last_exception = None

        for attempt, delay in enumerate(retry_delays):
            try:
                result = func(*args, **kwargs)

                if attempt > 0:
                    log.info(f"✅ Reintento exitoso después de {attempt} intentos Por gregorbc@gmail.com")

                return result
            except BinanceAPIException as e:
                last_exception = e

                if e.code in [-1013, -2010, -2011]:
                    log.error(f"Error no recuperable: {e.message} (código: {e.code}) Por gregorbc@gmail.com")
                    break

                log.warning(f"Reintentando en {delay}s (intento {attempt + 1}/{len(retry_delays)}) Por gregorbc@gmail.com")
                time.sleep(delay)

            except Exception as e:
                last_exception = e
                log.warning(f"Error general, reintentando en {delay}s (intento {attempt + 1}/{len(retry_delays)}) Por gregorbc@gmail.com")
                time.sleep(delay)

        log.error(f"❌ Todos los reintentos fallados: {last_exception} Por gregorbc@gmail.com")
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
                log.error("Precio requerido para órdenes LIMIT. Por gregorbc@gmail.com")
                return None
            params.update({
                'price': str(price),
                'timeInForce': TIME_IN_FORCE_GTC
            })

        if reduce_only:
            params['reduceOnly'] = 'true'

        if config.DRY_RUN:
            log.info(f"[DRY_RUN] place_order: {params} Por gregorbc@gmail.com")
            return {'mock': True, 'orderId': int(time.time() * 1000)}

        return self.smart_retry_api_call(self.client.futures_create_order, **params)

    def close_position(self, symbol: str, position_amt: float) -> Optional[Dict]:
        side = SIDE_SELL if position_amt > 0 else SIDE_BUY
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] close_position {symbol} {position_amt} Por gregorbc@gmail.com")
            return {'mock': True, 'orderId': int(time.time() * 1000)}
        return self.place_order(symbol, side, FUTURE_ORDER_TYPE_MARKET, abs(position_amt), reduce_only=True)

    def cancel_order(self, symbol: str, orderId: int) -> Optional[Dict]:
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] cancel_order: {orderId} para {symbol} Por gregorbc@gmail.com")
            return {'mock': True}

        try:
            return self.smart_retry_api_call(self.client.futures_cancel_order, symbol=symbol, orderId=orderId)
        except Exception as e:
            log.warning(f"No se pudo cancelar la orden {orderId} para {symbol}: {e} Por gregorbc@gmail.com")
            return None

    @staticmethod
    def round_value(value: float, step: float) -> float:
        if step == 0:
            return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)

# -------------------- BOT DE TRADING CON GESTIÓN DE CAPITAL REAL -------------------- #
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
        self.telegram_handler = TelegramCommandHandler(self)
        self.telegram_poller = TelegramPoller(self.telegram_handler)

        # Notificar inicio del bot por Telegram
        if self.telegram_notifier.enabled:
            self.telegram_notifier.notify_bot_started(config.LEVERAGE)

        # Iniciar polling de Telegram
        self.telegram_poller.start_polling()

        try:
            self.performance_analyzer = PerformanceAnalyzer(SessionLocal() if DB_ENABLED else None)
        except Exception as e:
            log.error(f"Error inicializando PerformanceAnalyzer: {e}")
            self.performance_analyzer = None
            
        self.daily_pnl = 0.0
        self.daily_starting_balance = 0.0
        self.today = datetime.now().date()

    def get_top_symbols(self) -> List[str]:
        tickers = self.api._safe_api_call(self.api.client.futures_ticker)
        if not tickers:
            return []

        # Filtrar solo pares USDT
        valid_tickers = [
            t for t in tickers
            if t['symbol'].endswith('USDT')
            and t['symbol'] not in config.EXCLUDE_SYMBOLS
            and t['symbol'] not in config.BLACKLIST_SYMBOLS
            and float(t['quoteVolume']) > config.MIN_24H_VOLUME
        ]

        # Para cuentas con 20x leverage, priorizar símbolos con buena liquidez
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

            # Ajustar para 20x leverage
            if min_order_value <= (self.capital_manager.current_balance * 0.8):
                suitable_symbols.append(t)

        # Ordenar por volumen y precio adecuado para 20x
        suitable_symbols.sort(key=lambda x: (float(x['quoteVolume']), 1/float(x['lastPrice'])), reverse=True)

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
        df = df.dropna(subset=['close'])
        df['symbol'] = symbol
        return df

    def calculate_indicators(self, df: pd.DataFrame):
        # EMAs ajustadas para 20x
        df['fast_ema'] = df['close'].ewm(span=config.FAST_EMA, adjust=False).mean()
        df['slow_ema'] = df['close'].ewm(span=config.SLOW_EMA, adjust=False).mean()

        # RSI Por gregorbc@gmail.com
        delta = df['close'].diff()
        up, down = delta.copy(), delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0
        roll_up = up.ewm(span=config.RSI_PERIOD, adjust=False).mean()
        roll_down = down.abs().ewm(span=config.RSI_PERIOD, adjust=False).mean()
        rs = roll_up / roll_down.replace(0, np.nan)
        df['rsi'] = 100.0 - (100.0 / (1.0 + rs)).fillna(50)

        # MACD Por gregorbc@gmail.com
        exp1 = df['close'].ewm(span=config.MACD_FAST, adjust=False).mean()
        exp2 = df['close'].ewm(span=config.MACD_SLOW, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=config.MACD_SIGNAL, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # Stochastic RSI Por gregorbc@gmail.com
        stoch_rsi = (df['rsi'] - df['rsi'].rolling(config.STOCH_PERIOD).min()) / (df['rsi'].rolling(config.STOCH_PERIOD).max() - df['rsi'].rolling(config.STOCH_PERIOD).min())
        df['stoch_rsi'] = stoch_rsi * 100

        # Bollinger Bands Por gregorbc@gmail.com
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

        # Volatilidad para 20x
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(20).std() * np.sqrt(365) * 100

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        Calcula el ADX (Average Directional Index) usando TA-Lib or implementación alternativa.
        Por gregorbc@gmail.com
        """
        if len(df) < period * 2 + 1:
            return 0.0
        
        try:
            if TALIB_ENABLED:
                # Asegurarse de que los datos son del tipo correcto
                high = df['high'].astype(float).values
                low = df['low'].astype(float).values
                close = df['close'].astype(float).values
                
                # Calcular ADX con TA-Lib
                adx_values = talib.ADX(high, low, close, timeperiod=period)
                
                # Tomar los últimos valores válidos (no NaN)
                valid_adx = adx_values[~np.isnan(adx_values)]
                if len(valid_adx) > 0:
                    result = float(valid_adx[-1])
                    return result
                return 0.0
            else:
                return self._calculate_adx_manual(df, period)
                
        except Exception as e:
            symbol = df['symbol'].iloc[-1] if 'symbol' in df.columns else 'UNKNOWN'
            log.error(f"Error calculando ADX para {symbol}: {e} Por gregorbc@gmail.com")
            return 0.0

    def _calculate_adx_manual(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        Implementación manual del ADX cuando TA-Lib no está disponible.
        Por gregorbc@gmail.com
        """
        try:
            # Calcular +DM and -DM
            high, low, close = df['high'], df['low'], df['close']
            
            up_move = high.diff()
            down_move = low.diff().abs() * -1
            
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move.abs(), 0)
            
            # Calcular True Range
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # Suavizar con media móvil
            atr = true_range.rolling(period).mean()
            
            # Calcular DI+ y DI-
            plus_di = 100 * (pd.Series(plus_dm).rolling(period).mean() / atr)
            minus_di = 100 * (pd.Series(minus_dm).rolling(period).mean() / atr)
            
            # Calcular DX y ADX
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
            adx = dx.rolling(period).mean()
            
            result = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
            return result
            
        except Exception as e:
            log.error(f"Error en cálculo manual de ADX: {e} Por gregorbc@gmail.com")
            return 0.0

    def calculate_signal_strength(self, df: pd.DataFrame, signal: str, symbol: str) -> float:
        """Calcula la fuerza de la señal basada en múltiples factores Por gregorbc@gmail.com"""
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
        if len(df) < 50:
            return None
            
        last, prev = df.iloc[-1], df.iloc[-2]

        # Verificar ADX para 20x - mayor exigencia
        if len(df) >= 28:
            adx = self.calculate_adx(df)
            if adx < config.MIN_ADX_FOR_TREND:
                log.info(f"↔️ Mercado lateral para {symbol} (ADX: {adx:.1f} < {config.MIN_ADX_FOR_TREND}), omitiendo Por gregorbc@gmail.com")
                return None

        # Verificar volatilidad para 20x
        if 'volatility' in df.columns and not pd.isna(df['volatility'].iloc[-1]):
            volatility = df['volatility'].iloc[-1]
            if volatility > config.MAX_VOLATILITY_PERCENT:
                log.info(f"⚡ Alta volatilidad en {symbol}: {volatility:.1f}%, omitiendo Por gregorbc@gmail.com")
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

        # Condiciones RSI ajustadas para 20x
        rsi_confirm = (signal == 'LONG' and last['rsi'] > 45 and last['rsi'] < config.RSI_OVERBOUGHT) or \
                     (signal == 'SHORT' and last['rsi'] < 55 and last['rsi'] > config.RSI_OVERSOLD)

        macd_confirm = (signal == 'LONG' and last['macd'] > last['macd_signal']) or \
                      (signal == 'SHORT' and last['macd'] < last['macd_signal'])

        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        trend_confirm = (signal == 'LONG' and last['close'] > ema50) or \
                       (signal == 'SHORT' and last['close'] < ema50)

        confirmations = sum([rsi_confirm, macd_confirm, trend_confirm])
        if confirmations < 2:  # Mayor exigencia para 20x
            return None

        if config.VOLUME_WEIGHTED_SIGNALS:
            volume_avg = df['volume'].rolling(20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / volume_avg if volume_avg > 0 else 1

            if volume_ratio < config.MIN_VOLUME_CONFIRMATION:
                log.info(f"📉 Señal {signal} descartada por volumen insuficiente: {volume_ratio:.2f} Por gregorbc@gmail.com")
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
                        log.info(f"⏭️ Señal {signal} en {symbol} descartada por falta de alineación con TF superior ({higher_tf_signal}) Por gregorbc@gmail.com")
                        return None
            except Exception as e:
                log.error(f"Error verificando TF superior para {symbol}: {e} Por gregorbc@gmail.com")

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
                    log.info(f"⚠️ Señal {signal} en {symbol} con señal contraria en BTC, fuerza reducida a {strength:.2f} Por gregorbc@gmail.com")

        strength = self.calculate_signal_strength(df, signal, symbol)
        self.signal_strength[symbol] = strength

        if strength < config.MIN_SIGNAL_STRENGTH:
            log.info(f"📉 Señal {signal} descartada por fuerza insuficiente: {strength:.2f} Por gregorbc@gmail.com")
            return None

        log.info(f"📶 Señal {signal} con fuerza: {strength:.2f}, confirmaciones: {confirmations}/3 Por gregorbc@gmail.com")
        return signal

    def get_ai_adjustments(self, symbol: str, performance_data: Dict) -> Tuple[float, float]:
        """Obtiene ajustes de SL/TP de la IA Por gregorbc@gmail.com"""
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
        """Actualiza el modelo de IA con el resultado de la operación Por gregorbc@gmail.com"""
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
            log.error(f"Error actualizando modelo de IA para {symbol}: {e} Por gregorbc@gmail.com")

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
                        log.info(f"🤖 Ajuste de Trailing por IA para {symbol}: {trailing_adjustment:.2f} (Volatilidad: {performance_data.get('market_volatility', 0):.2f}%) Por gregorbc@gmail.com")

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
                    log.info(f"🔔 Trailing stop activado para {symbol} (adj: {trailing_data['trailing_adjustment']:.2f}) Por gregorbc@gmail.com")
                if trailing_data['activated']:
                    new_stop = trailing_data['best_price'] * (1 - stop_percentage / 100)
                    if new_stop > trailing_data['current_stop']:
                        trailing_data['current_stop'] = new_stop
                    if current_price <= trailing_data['current_stop']:
                        log.info(f"🔴 Cierre por trailing stop: {symbol} @ {current_price} (Stop: {trailing_data['current_stop']}) Por gregorbc@gmail.com")
                        should_close = True
            else:
                if current_price < trailing_data['best_price']:
                    trailing_data['best_price'] = current_price
                profit_percentage = ((entry_price - current_price) / entry_price) * 100
                if not trailing_data['activated'] and profit_percentage >= activation_percent:
                    trailing_data['activated'] = True
                    log.info(f"🔔 Trailing stop activado para {symbol} (adj: {trailing_data['trailing_adjustment']:.2f}) Por gregorbc@gmail.com")
                if trailing_data['activated']:
                    new_stop = trailing_data['best_price'] * (1 + stop_percentage / 100)
                    if new_stop < trailing_data['current_stop']:
                        trailing_data['current_stop'] = new_stop
                    if current_price >= trailing_data['current_stop']:
                        log.info(f"🔴 Cierre por trailing stop: {symbol} @ {current_price} (Stop: {trailing_data['current_stop']}) Por gregorbc@gmail.com")
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
                        log.info(f"🤖 Ajuste SL/TP por IA para {symbol}: SL={sl_adjustment:.2f}, TP={tp_adjustment:.2f} Por gregorbc@gmail.com")

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
                log.info(f"SL/TP inicializado para {symbol}: SL @ {sl_price:.4f} (adj: {sl_adjustment:.2f}), TP @ {tp_price:.4f} (adj: {tp_adjustment:.2f}) Por gregorbc@gmail.com")

            sl_price = sl_tp_data.get('sl_price')
            tp_price = sl_tp_data.get('tp_price')

            if not sl_price or not tp_price:
                return False

            if position_side == 'LONG':
                if current_price <= sl_price:
                    log.info(f"🔴 Cierre por STOP LOSS: {symbol} @ {current_price} (SL: {sl_price}) Por gregorbc@gmail.com")
                    return 'SL'
                elif current_price >= tp_price:
                    log.info(f"🟢 Cierre por TAKE PROFIT: {symbol} @ {current_price} (TP: {tp_price}) Por gregorbc@gmail.com")
                    return 'TP'
            else:
                if current_price >= sl_price:
                    log.info(f"🔴 Cierre por STOP LOSS: {symbol} @ {current_price} (SL: {sl_price}) Por gregorbc@gmail.com")
                    return 'SL'
                elif current_price <= tp_price:
                    log.info(f"🟢 Cierre por TAKE PROFIT: {symbol} @ {current_price} (TP: {tp_price}) Por gregorbc@gmail.com")
                    return 'TP'
            return False

    def check_time_based_exit(self, symbol: str, position: Dict) -> bool:
        """Check if position should be closed based on holding time Por gregorbc@gmail.com"""
        update_time = position.get('updateTime', 0)
        if update_time == 0:
            return False

        hours_held = (time.time() * 1000 - update_time) / (1000 * 60 * 60)
        if hours_held > config.MAX_POSITION_HOLD_HOURS:
            log.info(f"⏰ Cierre por tiempo: {symbol} held for {hours_held:.1f} hours Por gregorbc@gmail.com")
            return True
        return False

    def check_momentum_reversal(self, symbol: str, position: Dict, df: pd.DataFrame) -> bool:
        """Check if momentum has reversed against the position Por gregorbc@gmail.com"""
        if df is None or len(df) < 10 or 'rsi' not in df.columns:
            return False

        position_side = 'LONG' if float(position['positionAmt']) > 0 else 'SHORT'
        current_rsi = df['rsi'].iloc[-1]
        prev_rsi = df['rsi'].iloc[-2]

        if position_side == 'LONG':
            price_trend = df['close'].iloc[-1] > df['close'].iloc[-3]
            rsi_trend = current_rsi < prev_rsi
            if price_trend and rsi_trend and current_rsi > 70:
                log.info(f"↘️ Cierre por divergencia RSI bajista: {symbol} Por gregorbc@gmail.com")
                return True
        else:
            price_trend = df['close'].iloc[-1] < df['close'].iloc[-3]
            rsi_trend = current_rsi > prev_rsi
            if price_trend and rsi_trend and current_rsi < 30:
                log.info(f"↗️ Cierre por divergencia RSI alcista: {symbol} Por gregorbc@gmail.com")
                return True

        return False

    def dynamic_exit_strategy(self, symbol: str, position: Dict, current_price: float, df: pd.DataFrame) -> Optional[str]:
        """Combine multiple exit strategies for better performance Por gregorbc@gmail.com"""
        # Verificar volumen anormalmente bajo (posible manipulación)
        if df is not None and len(df) > 20:
            volume_avg = df['volume'].rolling(20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            
            if current_volume < volume_avg * config.LOW_VOLUME_THRESHOLD:
                log.info(f"⚠️ Volumen anormalmente bajo en {symbol}, cerrando posición Por gregorbc@gmail.com")
                return 'LOW_VOLUME_EXIT'
        
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
            log.warning(f"⚠️ Balance bajo: {current_balance:.2f} USDT (mínimo: {config.MIN_BALANCE_THRESHOLD} USDT) Por gregorbc@gmail.com")
            return True

        open_positions = {p['symbol']: p for p in account_info['positions'] if float(p['positionAmt']) != 0}
        total_investment = sum(float(p.get('initialMargin', 0) or 0) for p in open_positions.values())
        exposure_ratio = total_investment / current_balance if current_balance > 0 else 0

        if exposure_ratio > 0.8:
            log.warning(f"⚠️ Exposición demasiado alta: {exposure_ratio:.2%} Por gregorbc@gmail.com")
        
        with state_lock:
            app_state["risk_metrics"]["exposure_ratio"] = exposure_ratio
            if app_state["balance_history"]:
                peak = max(app_state["balance_history"])
                drawdown = (peak - current_balance) / peak * 100 if peak > 0 else 0
                app_state["risk_metrics"]["max_drawdown"] = max(app_state["risk_metrics"]["max_drawdown"], drawdown)

                if drawdown > config.MAX_DRAWDOWN_PERCENT:
                    log.warning(f"⛔ Drawdown máximo excedido: {drawdown:.2f}% Por gregorbc@gmail.com")
                    return True

            app_state["balance_history"].append(current_balance)
            if len(app_state["balance_history"]) > 100:
                app_state["balance_history"].pop(0)

        return False

    def detect_market_regime(self) -> str:
        """Detect overall market regime to adjust trading strategy Por gregorbc@gmail.com"""
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
        Calculate position size based on real capital for 20x leverage
        Por gregorbc@gmail.com
        """
        # Usar balance real del capital manager
        current_balance = self.capital_manager.current_balance

        if current_balance <= 0:
            return 0

        risk_amount = current_balance * (config.RISK_PER_TRADE_PERCENT / 100)

        risk_factor = 1.0
        if self.performance_analyzer:
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
        
        # Aplicar leverage 20x
        position_size = position_size * leverage

        # Verificar volatilidad
        df = self.get_klines_for_symbol(symbol)
        if df is not None and not df.empty and len(df) > 20:
            returns = np.log(df['close'] / df['close'].shift(1))
            volatility = returns.std() * np.sqrt(365)

            # Reducir tamaño de posición en mercados volátiles para 20x
            volatility_factor = 1.0 / (1.0 + volatility * 10)
            position_size *= volatility_factor

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

            # Verificar máximo por balance con 20x
            max_position_size = (current_balance * leverage) / price
            position_size = min(position_size, max_position_size * 0.8)  # Margen de seguridad

        return max(position_size, 0)

    def analyze_trading_performance(self, symbol: str):
        if not DB_ENABLED: return None
        
        def analyze_operation():
            db = get_db_session_with_retry(max_retries=2)
            if not db:
                return None
                
            try:
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

                metrics = PerformanceMetrics(
                    symbol=symbol, 
                    win_rate=win_rate, 
                    profit_factor=profit_factor, 
                    avg_win=avg_win, 
                    avg_loss=avg_loss, 
                    recommended_leverage=recommended_leverage, 
                    strategy_effectiveness=strategy_effectiveness, 
                    market_volatility=atr, 
                    avg_trade_duration=avg_trade_duration
                )
                db.add(metrics)
                db.commit()

                log.info(f"📊 Análisis de rendimiento para {symbol}: WR: {win_rate:.2%}, PF: {profit_factor:.2f}, Lev. Rec: {recommended_leverage}x, Vol: {atr:.2f}%, Dur: {avg_trade_duration:.1f}m Por gregorbc@gmail.com")
                return asdict(metrics)
                
            except Exception as e:
                log.error(f"Error analizando rendimiento para {symbol}: {e} Por gregorbc@gmail.com")
                db.rollback()
                return None
            finally:
                db.close()

        return execute_with_retry(analyze_operation, max_retries=2, retry_delay=1)

    def optimize_strategy_based_on_losses(self):
        if not DB_ENABLED: 
            return
            
        def optimize_operation():
            db = get_db_session_with_retry(max_retries=2)
            if not db:
                return
                
            try:
                recent_losing_trades = db.query(Trade.symbol, func.count(Trade.id)).filter(
                    Trade.pnl < 0,
                    Trade.timestamp >= datetime.now() - timedelta(hours=strategy_optimizer.OPTIMIZATION_INTERVAL)
                ).group_by(Trade.symbol).all()

                if not recent_losing_trades: 
                    return

                for symbol, loss_count in recent_losing_trades:
                    total_trades = db.query(Trade).filter(Trade.symbol == symbol).count()
                    if total_trades > strategy_optimizer.MIN_TRADES_FOR_ANALYSIS:
                        loss_ratio = loss_count / total_trades
                        if loss_ratio > 0.7:
                            log.warning(f"⚠️ Símbolo problemático detectado: {symbol} con {loss_ratio:.2%} de trades perdedores Por gregorbc@gmail.com")
            except Exception as e:
                log.error(f"Error optimizando estrategia basada en pérdidas: {e} Por gregorbc@gmail.com")
            finally:
                db.close()

        execute_with_retry(optimize_operation, max_retries=2, retry_delay=1)

    def analyze_problematic_symbols(self):
        """Analizar símbolos con peor performance y ajustar estrategia Por gregorbc@gmail.com"""
        if not DB_ENABLED:
            return
            
        try:
            db = get_db_session_with_retry(max_retries=2)
            if not db:
                return
                
            # Obtener símbolos con al menos 5 trades
            symbol_stats = db.query(
                Trade.symbol,
                func.count(Trade.id).label('total_trades'),
                func.sum(case((Trade.pnl > 0, 1), else_=0)).label('winning_trades'),
                func.sum(Trade.pnl).label('total_pnl'),
                func.avg(Trade.pnl).label('avg_pnl')
            ).group_by(Trade.symbol).having(func.count(Trade.id) >= 5).all()
            
            problematic_symbols = []
            for stat in symbol_stats:
                win_rate = stat.winning_trades / stat.total_trades if stat.total_trades > 0 else 0
                if win_rate < 0.4 or stat.total_pnl < 0:
                    problematic_symbols.append({
                        'symbol': stat.symbol,
                        'win_rate': win_rate,
                        'total_pnl': float(stat.total_pnl),
                        'avg_pnl': float(stat.avg_pnl) if stat.avg_pnl else 0
                    })
            
            # Ajustar estrategia para símbolos problemáticos
            for symbol_data in problematic_symbols:
                symbol = symbol_data['symbol']
                log.warning(f"⚠️ Símbolo problemático: {symbol}, Win Rate: {symbol_data['win_rate']:.2%}, PnL Total: {symbol_data['total_pnl']:.2f}")
                
                # Reducir leverage o evitar trading para este símbolo
                if symbol_data['win_rate'] < 0.3:
                    # Deshabilitar completamente
                    config.SYMBOL_SPECIFIC_SETTINGS[symbol] = {
                        'risk_multiplier': 0.3,
                        'max_leverage': 10,
                        'enabled': False
                    }
                    log.info(f"🔒 Deshabilitando trading para {symbol} debido a mal performance Por gregorbc@gmail.com")
                else:
                    # Reducir riesgo
                    config.SYMBOL_SPECIFIC_SETTINGS[symbol] = {
                        'risk_multiplier': 0.5,
                        'max_leverage': 15,
                        'enabled': True
                    }
                    log.info(f"⚠️ Reduciendo riesgo para {symbol} debido a performance mediocre Por gregorbc@gmail.com")
                    
        except Exception as e:
            log.error(f"Error analizando símbolos problemáticos: {e} Por gregorbc@gmail.com")
        finally:
            if 'db' in locals():
                db.close()

    def generate_daily_report(self):
        """Generar reporte diario de performance Por gregorbc@gmail.com"""
        if not DB_ENABLED:
            return

        def report_operation():
            db = get_db_session_with_retry(max_retries=2)
            if not db:
                return
                
            try:
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

                message = f"""<b>📊 Reporte Diario de Trading (20x)</b>

💰 Capital Actual: {capital_stats['current_balance']:.2f} USDT
📈 Profit Total: {capital_stats['total_profit']:+.2f} USDT
📊 Rentabilidad: {capital_stats['profit_percentage']:+.2f}%
⚡ Apalancamiento: 20x

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

                log.info(f"📊 Reporte diario generado: {total_trades} trades, P&L Diario: {total_pnl:+.2f} USDT (20x) Por gregorbc@gmail.com")

            except Exception as e:
                log.error(f"Error generando reporte diario: {e} Por gregorbc@gmail.com")
            finally:
                db.close()

    def open_trade(self, symbol: str, side: str, last_candle):
        # Verificar spread excesivo
        ticker = self.api._safe_api_call(self.api.client.futures_symbol_ticker, symbol=symbol)
        if ticker:
            bid_price = float(ticker.get('bidPrice', 0))
            ask_price = float(ticker.get('askPrice', 0))
            if bid_price > 0 and ask_price > 0:
                spread = (ask_price - bid_price) / bid_price * 100
                if spread > config.MAX_SPREAD_PERCENT:
                    log.warning(f"⏭️ Spread demasiado alto ({spread:.2f}%) en {symbol}, omitiendo trade Por gregorbc@gmail.com")
                    return

        symbol_settings = config.SYMBOL_SPECIFIC_SETTINGS.get(symbol, {})
        if not symbol_settings.get('enabled', True):
            log.info(f"⏭️ Símbolo {symbol} deshabilitado en configuración Por gregorbc@gmail.com")
            return

        price = float(last_candle['close'])
        filters = self.api.get_symbol_filters(symbol)

        if not filters:
            log.error(f"No filters for {symbol} Por gregorbc@gmail.com")
            return

        min_notional = max(filters.get('minNotional', 5.0), config.MIN_NOTIONAL_OVERRIDE)
        min_qty = filters['minQty']

        min_position_size = min_notional / price
        if min_position_size < min_qty:
            min_position_size = min_qty

        if min_position_size * price > self.capital_manager.current_balance:
            log.info(f"⏭️ {symbol} requiere mínimo {min_position_size * price:.2f} USDT, capital insuficiente Por gregorbc@gmail.com")
            return

        max_leverage = symbol_settings.get('max_leverage', config.LEVERAGE)
        current_leverage = min(config.LEVERAGE, max_leverage)

        if config.DRY_RUN:
            log.info(f"[DRY RUN] Would open {side} on {symbol} Por gregorbc@gmail.com")
            return

        self.api.ensure_symbol_settings(symbol)

        quantity = self.calculate_position_size(symbol, price)

        if quantity <= 0:
            log.info(f"⏭️ Tamaño de posición inválido para {symbol} Por gregorbc@gmail.com")
            return

        quantity = self.api.round_value(quantity, filters['stepSize'])

        if quantity < min_qty:
            log.info(f"⏭️ Cantidad {quantity} para {symbol} es menor que el mínimo {min_qty} Por gregorbc@gmail.com")
            return

        notional_value = quantity * price
        if notional_value < min_notional:
            log.info(f"⏭️ Valor nocional {notional_value:.2f} para {symbol} es menor que el mínimo {min_notional:.2f} Por gregorbc@gmail.com")
            return

        order_side = SIDE_BUY if side == 'LONG' else SIDE_SELL

        log.info(f"Attempting to place MARKET order for {side} {symbol} (Qty: {quantity}, Value: {notional_value:.2f} USDT, 20x) Por gregorbc@gmail.com")

        order = self.api.place_order(symbol, order_side, FUTURE_ORDER_TYPE_MARKET, quantity)

        if order and order.get('orderId'):
            log.info(f"✅ MARKET ORDER CREATED: {side} {quantity} {symbol} (20x) Por gregorbc@gmail.com")

            if self.telegram_notifier.enabled:
                self.telegram_notifier.notify_trade_opened(
                    symbol, side, quantity, price, 
                    self.capital_manager.current_balance, config.LEVERAGE
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
            log.error(f"❌ Could not create market order for {symbol}. Response: {order} Por gregorbc@gmail.com")

    def run(self):
        log.info(f"🚀 STARTING TRADING BOT v12.0 WITH 20x LEVERAGE - USDT PAIRS Por gregorbc@gmail.com")
        log.info(f"⚡ Configuración 20x: SL={config.STOP_LOSS_PERCENT}%, TP={config.TAKE_PROFIT_PERCENT}%")
        log.info(f"⚡ Risk per trade: {config.RISK_PER_TRADE_PERCENT}%, Max positions: {config.MAX_CONCURRENT_POS}")
        
        # Verificar conexión y configuración
        log.info(f"🔑 API Key presente: {bool(os.getenv('BINANCE_API_KEY'))}")
        log.info(f"🔑 API Secret presente: {bool(os.getenv('BINANCE_API_SECRET'))}")
        log.info(f"🌐 Modo Testnet: {os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'}")
        log.info(f"🔧 Dry Run: {config.DRY_RUN}")
        
        # Verificar conexión a base de datos
        if DB_ENABLED:
            db_healthy = check_db_connection()
            log.info(f"🗄️ Conexión a base de datos: {'✅ SALUDABLE' if db_healthy else '❌ PROBLEMAS'}")
        
        self.start_time = time.time()

        # Inicializar con capital real
        self.capital_manager.update_balance(force=True)
        self.daily_starting_balance = self.capital_manager.current_balance
        self.daily_pnl = 0.0
        self.today = datetime.now().date()

        # Verificar si el balance supera el mínimo requerido
        if self.capital_manager.current_balance < config.MIN_BALANCE_THRESHOLD:
            log.warning(f"⚠️ Balance insuficiente: {self.capital_manager.current_balance:.2f} USDT < {config.MIN_BALANCE_THRESHOLD} USDT")
            if self.telegram_notifier.enabled:
                self.telegram_notifier.notify_warning(
                    f"Balance insuficiente: {self.capital_manager.current_balance:.2f} USDT",
                    "El bot no realizará operaciones hasta que se depositen más fondos"
                )

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
                log.info(f"--- 🔄 Cycle {self.cycle_count} - Capital: {self.capital_manager.current_balance:.2f} USDT (20x) ---")

                # Actualizar capital más frecuentemente para 20x
                if self.cycle_count % config.CAPITAL_UPDATE_INTERVAL == 0:
                    if self.capital_manager.update_balance():
                        current_balance = self.capital_manager.current_balance
                        profit = self.capital_manager.total_profit
                        profit_percentage = (self.capital_manager.total_profit / self.capital_manager.initial_balance * 100) if self.capital_manager.initial_balance > 0 else 0

                        if self.telegram_notifier.enabled:
                            self.telegram_notifier.notify_balance_update(
                                current_balance, profit, profit_percentage, config.LEVERAGE
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
                    log.info("🔄 Nuevo día - Reiniciando métricas diarias (20x) Por gregorbc@gmail.com")

                with state_lock:
                    app_state["connection_metrics"]["uptime"] = time.time() - self.start_time

                if self.cycle_count % 12 == 0:
                    self.market_regime = self.detect_market_regime()
                    with state_lock:
                        app_state["market_regime"] = self.market_regime
                    log.info(f"🏛️ Market Regime: {self.market_regime} (20x) Por gregorbc@gmail.com")
                    
                    if self.telegram_notifier.enabled:
                        self.telegram_notifier.notify_market_regime(
                            self.market_regime,
                            "El bot ajustará su estrategia según el régimen de mercado detectado"
                        )

                account_info = self.api._safe_api_call(self.api.client.futures_account)
                if not account_info:
                    time.sleep(config.POLL_SEC)
                    continue

                # Verificar pérdidas consecutivas
                with state_lock:
                    recent_trades = app_state["trades_history"][-config.MAX_CONSECUTIVE_LOSSES:]
                    consecutive_losses = sum(1 for trade in recent_trades if trade.get('pnl', 0) < 0)
                    
                    if consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
                        log.warning(f"⛔ {consecutive_losses} pérdidas consecutivas, pausando trading por 1 hora Por gregorbc@gmail.com")
                        time.sleep(3600)
                        continue

                if self.daily_pnl < - (self.daily_starting_balance * config.MAX_DAILY_LOSS_PERCENT / 100):
                    log.warning(f"⛔ Límite de pérdida diaria alcanzado: {self.daily_pnl:.2f} USDT (20x) Por gregorbc@gmail.com")
                    if self.telegram_notifier.enabled:
                        self.telegram_notifier.notify_warning(
                            f"Límite de pérdida diaria alcanzado: {self.daily_pnl:.2f} USDT",
                            "El bot se pausará hasta el próximo día de trading"
                        )
                    time.sleep(config.POLL_SEC)
                    continue

                low_balance = self.check_balance_risk(account_info)
                if low_balance: 
                    log.warning("⏸️ Pausando nuevas operaciones por balance bajo (20x) Por gregorbc@gmail.com")
                    if self.telegram_notifier.enabled:
                        self.telegram_notifier.notify_warning(
                            "Balance bajo detectado",
                            "No se abrirán nuevas posiciones hasta que el balance mejore"
                        )

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
                                            symbol, trade_result, exit_signal.lower(),
                                            self.capital_manager.current_balance,
                                            float(position['entryPrice']), current_price,
                                            abs(float(position['positionAmt'])), config.LEVERAGE
                                        )

                                if exit_signal.lower() in ['sl', 'tp', 'trailing'] and trade_result is not None:
                                    self.update_ai_model(symbol, trade_result, sl_adj, tp_adj, exit_signal.lower())

                    except Exception as e:
                        log.error(f"Error checking stops for {symbol}: {e} Por gregorbc@gmail.com", exc_info=True)
                        if self.telegram_notifier.enabled:
                            self.telegram_notifier.notify_error(
                                f"Error verificando stops para {symbol}",
                                str(e)
                            )

                if open_positions:
                    socketio.emit('pnl_update', {p['symbol']: float(p.get('unrealizedProfit', 0) or 0) for p in open_positions.values()})

                if self.cycle_count % 6 == 0 and DB_ENABLED:
                    try:
                        self.optimize_strategy_based_on_losses()
                        for symbol in open_positions.keys(): 
                            self.analyze_trading_performance(symbol)
                    except Exception as e:
                        log.error(f"Error en análisis de rendimiento: {e} Por gregorbc@gmail.com")

                # Análisis de símbolos problemáticos cada 24 ciclos
                if self.cycle_count % 24 == 0 and DB_ENABLED:
                    self.analyze_problematic_symbols()

                num_open_pos = len(open_positions)
                if num_open_pos < config.MAX_CONCURRENT_POS and not low_balance:
                    symbols_to_scan = [s for s in self.get_top_symbols() if s not in open_positions and s not in self.recently_signaled]
                    log.info(f"🔍 Scanning {len(symbols_to_scan)} symbols for new signals (20x). Por gregorbc@gmail.com")

                    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS_KLINE) as executor:
                        futures = {executor.submit(self.get_klines_for_symbol, s): s for s in symbols_to_scan}
                        for future in futures:
                            symbol, df = futures[future], future.result()
                            if df is None or len(df) < config.SLOW_EMA: continue
                            self.calculate_indicators(df)
                            signal = self.check_signal(df, symbol)
                            if signal:
                                log.info(f"🔥 Signal found! {signal} on {symbol} (20x) Por gregorbc@gmail.com")
                                self.recently_signaled.add(symbol)
                                self.open_trade(symbol, signal, df.iloc[-1])
                                if len(open_positions) + 1 >= config.MAX_CONCURRENT_POS:
                                    log.info("🚫 Concurrent positions limit reached (20x). Por gregorbc@gmail.com")
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
                log.error(f"Error in main loop: {e} Por gregorbc@gmail.com", exc_info=True)
                if self.telegram_notifier.enabled:
                    self.telegram_notifier.notify_error(
                        "Error en el loop principal del bot",
                        str(e)
                    )

            time.sleep(config.POLL_SEC)

        log.info("🛑 Bot stopped (20x). Por gregorbc@gmail.com")
        if self.telegram_notifier.enabled:
            self.telegram_notifier.send_message("🛑 <b>Bot de Trading Detenido</b>\n\nEl bot ha sido detenido manualmente.")

# -------------------- FUNCIONES AUXILIARES -------------------- #
def _record_closed_trade(api: BinanceFutures, symbol: str, position_data: dict, order_id: str, close_type: str, exit_price: float) -> Optional[float]:
    """
    Helper function to centralize the logic for recording a closed trade.
    Fetches PnL, calculates stats, and updates the global state and database.
    Returns the realized PnL for AI learning.
    Por gregorbc@gmail.com
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
            def save_trade_operation():
                db = get_db_session_with_retry(max_retries=2)
                if not db:
                    return
                    
                try:
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
                    db.add(db_trade)
                    db.commit()
                    log.info(f"💾 Trade guardado en DB: {symbol}, PnL: {realized_pnl:.2f}")
                except Exception as e:
                    log.error(f"DB Error recording trade for {symbol}: {e} Por gregorbc@gmail.com")
                    db.rollback()
                finally:
                    db.close()

            execute_with_retry(save_trade_operation, max_retries=2, retry_delay=1)

        log.info(f"✅ Position closed: {symbol}, PnL: {realized_pnl:.2f} USDT, ROE: {roe:.2f}%, Reason: {close_type} (20x) Por gregorbc@gmail.com")
        socketio.emit('status_update', app_state)
        
        return realized_pnl

    except Exception as e:
        log.error(f"❌ Critical error in _record_closed_trade for {symbol}: {e}", exc_info=True)
        return None

# -------------------- RUTAS WEB Y TAREAS EN SEGUNDO PLANO -------------------- #

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
    global bot_thread
    with state_lock:
        if app_state["running"]: 
            return jsonify({"status": "error", "message": "Bot is already running"}), 400
        app_state["running"] = True
        app_state["status_message"] = "Starting..."  # CORREGIDO: usar = en lugar de :
    
    bot_instance = TradingBot()
    bot_thread = threading.Thread(target=bot_instance.run, daemon=True)
    bot_thread.start()
    log.info("▶️ Bot started from web interface (20x). Por gregorbc@gmail.com")
    return jsonify({"status": "success", "message": "Bot started successfully."})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    with state_lock:
        if not app_state["running"]: 
            return jsonify({"status": "error", "message": "Bot is not running"}), 400
        app_state["running"] = False
        app_state["status_message"] = "Stopping..."
    
    log.info("⏹️ Bot stopped from web interface (20x). Por gregorbc@gmail.com")
    return jsonify({"status": "success", "message": "Bot stopped."})

@app.route('/api/update_config', methods=['POST'])
def update_config():
    data = request.json

    def cast_value(current, value):
        if isinstance(current, bool): 
            return str(value).lower() in ['true', '1', 'yes', 'on']
        if isinstance(current, int): 
            return int(value)
        if isinstance(current, float): 
            return float(value)
        if isinstance(current, tuple):
            if isinstance(value, str): 
                return tuple(p.strip().upper() for p in value.split(',') if p.strip())
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
                    log.warning(f"Failed to set config field {key} with value {value}: {e} Por gregorbc@gmail.com")
                    return jsonify({"status": "error", "message": f"Invalid value for {key}: {value}"}), 400
        app_state["config"] = asdict(config)

    log.info(f"⚙️ Configuration updated: {updated_fields} (20x) Por gregorbc@gmail.com")
    socketio.emit('config_updated', app_state["config"])
    return jsonify({"status": "success", "message": "Configuration saved.", "config": app_state["config"]})

@app.route('/api/close_position', methods=['POST'])
def close_position_api():
    symbol = request.json.get('symbol')
    if not symbol: 
        return jsonify({"status": "error", "message": "Missing symbol"}), 400

    try:
        api = BinanceFutures()
        acct = api._safe_api_call(api.client.futures_account)
        position = next((p for p in acct.get('positions', []) if p['symbol'] == symbol and float(p['positionAmt']) != 0), None)
        if not position: 
            return jsonify({"status": "error", "message": f"No active position found for {symbol}"}), 404

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
        log.error(f"Error closing position {symbol}: {e} Por gregorbc@gmail.com")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/manual_trade', methods=['POST'])
def manual_trade():
    data = request.json
    symbol, side, margin = data.get('symbol', '').upper(), data.get('side'), float(data.get('margin', 10))
    if not all([symbol, side]): 
        return jsonify({"status": "error", "message": "Missing parameters."}), 400
    
    try:
        api = BinanceFutures()
        api.ensure_symbol_settings(symbol)
        mark = api._safe_api_call(api.client.futures_mark_price, symbol=symbol)
        if not mark: 
            return jsonify({"status": "error", "message": "Unable to fetch mark price."}), 500
        
        price = float(mark['markPrice'])
        filters = api.get_symbol_filters(symbol)
        if not filters: 
            return jsonify({"status": "error", "message": f"Could not get filters for {symbol}"}), 500
        
        leverage_param = float(data.get('leverage', config.LEVERAGE) or config.LEVERAGE)
        quantity = api.round_value((margin * leverage_param) / price, filters['stepSize'])
        
        if quantity < filters['minQty'] or (quantity * price) < filters['minNotional']: 
            return jsonify({"status": "error", "message": f"Quantity ({quantity}) below minimum allowed."}), 400
        
        order_side = SIDE_BUY if side == 'LONG' else SIDE_SELL
        order = api.place_order(symbol, order_side, FUTURE_ORDER_TYPE_MARKET, quantity)
        
        if order and (order.get('orderId') or order.get('mock')):
            log.info(f"MANUAL TRADE CREATED: {side} {quantity} {symbol} (20x) Por gregorbc@gmail.com")
            return jsonify({"status": "success", "message": f"Manual market order for {symbol} created."})
        else:
            return jsonify({"status": "error", "message": f"Manual order failed: {order}"}), 500
            
    except Exception as e:
        log.error(f"Error in manual trade: {e} Por gregorbc@gmail.com")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/trade_history')
def get_trade_history():
    with state_lock:
        trades = app_state["trades_history"]
    
    sorted_trades = sorted(trades, key=lambda x: x.get('timestamp', 0), reverse=True)
    page, per_page = int(request.args.get('page', 1)), int(request.args.get('per_page', 20))
    start_idx, end_idx = (page - 1) * per_page, page * per_page
    paginated_trades = sorted_trades[start_idx:end_idx]
    
    return jsonify({
        "trades": paginated_trades, 
        "total": len(sorted_trades), 
        "page": page, 
        "per_page": per_page, 
        "total_pages": math.ceil(len(sorted_trades) / per_page)
    })

@app.route('/api/performance_metrics')
def get_performance_metrics():
    if not DB_ENABLED: 
        return jsonify({"error": "Database is not enabled."}), 503
    
    try:
        db = get_db_session_with_retry(max_retries=2)
        if not db:
            return jsonify({"error": "No se pudo conectar a la base de datos"}), 503
            
        query = db.query(PerformanceMetrics).order_by(desc(PerformanceMetrics.timestamp)).limit(100)
        metrics = query.all()
        return jsonify([asdict(m) for m in metrics])
        
    except Exception as e:
        log.error(f"Error fetching performance metrics: {e} Por gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'db' in locals(): 
            db.close()

@app.route('/api/performance_stats')
def get_performance_stats():
    """Obtener estadísticas de rendimiento detalladas Por gregorbc@gmail.com"""
    if not DB_ENABLED: 
        return jsonify({"error": "Database is not enabled."}), 503
    
    try:
        db = get_db_session_with_retry(max_retries=2)
        if not db:
            return jsonify({"error": "No se pudo conectar a la base de datos"}), 503

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
        log.error(f"Error fetching performance stats: {e} Por gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'db' in locals(): 
            db.close()

@app.route('/api/ai_metrics')
def get_ai_metrics():
    with state_lock:
        return jsonify(app_state["ai_metrics"])

@app.route('/api/detailed_metrics')
def get_detailed_metrics():
    """Obtener métricas detalladas para el panel de control Por gregorbc@gmail.com"""
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
        log.error(f"Error calculando métricas detalladas: {e} Por gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500

@app.route('/api/capital_stats')
def get_capital_stats():
    """Obtener estadísticas de capital Por gregorbc@gmail.com"""
    with state_lock:
        return jsonify(app_state["capital_stats"])

@app.route('/api/update_balance', methods=['POST'])
def update_balance():
    """Forzar actualización del balance Por gregorbc@gmail.com"""
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
        log.error(f"Error updating balance: {e} Por gregorbc@gmail.com")
        return jsonify({"status": "error", "message": str(e)}), 500

# -------------------- NUEVAS RUTAS DE BASE DE DATOS -------------------- #
@app.route('/api/db/trade_history')
def get_db_trade_history():
    """Obtener historial completo de trades desde la base de datos Por gregorbc@gmail.com"""
    if not DB_ENABLED:
        return jsonify({"error": "Database no está habilitada"}), 503

    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))

        db = get_db_session_with_retry(max_retries=2)
        if not db:
            return jsonify({"error": "No se pudo conectar a la base de datos"}), 503
            
        # Query for trades with pagination
        trades = db.query(Trade).order_by(desc(Trade.timestamp)).offset((page-1)*per_page).limit(per_page).all()
        total = db.query(func.count(Trade.id)).scalar()
        
        return jsonify({
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
                "duration": t.duration
            } for t in trades],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page
        })
            
    except Exception as e:
        log.error(f"Error fetching trade history from DB: {e} Por gregorbc@gmail.com")
        return jsonify({"error": str(e)}), 500
    finally:
        if 'db' in locals(): 
            db.close()

# -------------------- EVENTOS SOCKETIO -------------------- #
@socketio.on('connect')
def handle_connect():
    log.info(f"🔌 Client connected: {request.sid} Por gregorbc@gmail.com")
    with state_lock:
        socketio.emit('status_update', app_state, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    log.info(f"🔌 Client disconnected: {request.sid} Por gregorbc@gmail.com")

# -------------------- FUNCIÓN PRINCIPAL -------------------- #
if __name__ == '__main__':
    load_dotenv()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'

    log.info("🚀 Starting Binance Futures Bot Web Application v12.0 with 20x Leverage")
    log.info(f"⚡ Trading USDT pairs with {config.LEVERAGE}x leverage")
    log.info(f"🌐 Server will run on {host}:{port}")

    os.makedirs('logs', exist_ok=True)

    if DB_ENABLED:
        try:
            from database import init_db
            init_db()
            log.info("Database initialized successfully.")
        except Exception as e:
            log.error(f"Database initialization failed: {e}")

    socketio.run(app, debug=debug, host=host, port=port, use_reloader=False, allow_unsafe_werkzeug=True)
