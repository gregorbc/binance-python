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

from flask import Flask, render_template, jsonify, request, send_from_directory, send_file
from flask_socketio import SocketIO
from flask_cors import CORS

# Importaciones para el modelo de aprendizaje profundo
try:
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import Dense
    from tensorflow.keras.optimizers import Adam
    DRL_ENABLED = True
except ImportError:
    DRL_ENABLED = False
    print("ADVERTENCIA: TensorFlow no encontrado. Las características de Deep Learning estarán deshabilitadas.")

# Importación de base de datos con manejo de errores
DB_ENABLED = False
try:
    from database import SessionLocal, Trade, PerformanceMetrics, AccountBalance, get_db_session_with_retry, execute_with_retry, check_db_connection
    from sqlalchemy import func, case
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
    # Configuración Global
    LEVERAGE: int = 20
    MAX_CONCURRENT_POS: int = 5
    NUM_SYMBOLS_TO_SCAN: int = 80  # Reducido de 150 a 80 para mejor rendimiento
    # Configuración de Estrategia
    ATR_MULT_SL: float = 2.2
    ATR_MULT_TP: float = 3.5
    # Configuración de Trailing Stop
    TRAILING_STOP_ACTIVATION: float = 0.8
    TRAILING_STOP_PERCENTAGE: float = 0.35
    # Configuración de SL/TP Fijo
    USE_FIXED_SL_TP: bool = True
    STOP_LOSS_PERCENT: float = 0.5  # Reducido de 0.8% para 20x
    TAKE_PROFIT_PERCENT: float = 1.2  # Reducido de 1.8% para 20x
    # Configuración de Ajuste de IA
    AI_SL_ADJUSTMENT: bool = True
    AI_TP_ADJUSTMENT: bool = True
    AI_TRAILING_ADJUSTMENT: bool = True
    AI_VOLATILITY_FACTOR: float = 1.5
    # Configuración Fija
    MARGIN_TYPE: str = "CROSSED"
    MIN_24H_VOLUME: float = 10_000_000  # Aumentado para mejor calidad
    EXCLUDE_SYMBOLS: tuple = (
        "BTCDOMUSDT", "DEFIUSDT", "USDCUSDT", "TUSDUSDT", "BUSDUSDT", "USTUSDT",
        "BCCUSDT", "BCHABCUSDT", "BCHSVUSDT", "BEARUSDT", "BULLUSDT", 
        "ETHBEARUSDT", "ETHBULLUSDT", "EOSBEARUSDT", "EOSBULLUSDT",
        "XRPBEARUSDT", "XRPBULLUSDT", "BNBBEARUSDT", "BNBBULLUSDT",
        "ADABEARUSDT", "ADABULLUSDT", "LTCBEARUSDT", "LTCBULLUSDT",
        "ETCBEARUSDT", "ETCBULLUSDT", "TRXBEARUSDT", "TRXBULLUSDT",
        "XTZBEARUSDT", "XTZBULLUSDT", "LINKBEARUSDT", "LINKBULLUSDT",
        # Nuevos símbolos problemáticos identificados en logs
        "4USDT", "1000CHEEMSUSDT", "NAORISUSDT", "COAIUSDT", "AIAUSDT",
        "TOWNSUSDT", "UMAUSDT", "OMNIUSDT", "ALPHAUSDT", "QUSDT",
        "MEMEUSDT", "PEPEUSDT", "BONKUSDT"  # Nuevos memecoins de alta volatilidad
    )
    # Lista negra con símbolos de alto riesgo
    BLACKLIST_SYMBOLS: tuple = (
        "PROMPTUSDT", "PLAYUSDT", "LDOUSDT", "1000FLOKIUSDT", "QTUMUSDT",
        "LRCUSDT", "GALAUSDT", "SKLUSDT", "HBARUSDT", "CUSDT", "SOLUSDT",
        "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "SHIBUSDT", "TAUSDT",
        "NEWTUSDT", "KERNELUSDT", "LPTUSDT", "DOTUSDT", "LINKUSDT", "AAVEUSDT",
        "UNIUSDT", "TIAUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT", "SEIUSDT", "INJUSDT",
        "NEARUSDT", "FTMUSDT", "MEMEUSDT", "PEPEUSDT", "BONKUSDT", "1000BONKUSDT",
        "FRONTUSDT", "LITUSDT", "NKNUSDT", "OXTUSDT", "STGUSDT", "WAVESUSDT",
        "SNXUSDT", "ENJUSDT", "GRTUSDT", "BANDUSDT", "OCEANUSDT", "COTIUSDT",
        "KAVAUSDT", "DUSKUSDT", "RSRUSDT", "HOTUSDT", "ZILUSDT", "IOSTUSDT",
        "ONEUSDT", "STMXUSDT", "DENTUSDT", "VETUSDT", "ANKRUSDT", "CHZUSDT",
        "BTSUSDT", "FTTUSDT", "CRVUSDT", "CVXUSDT", "SUSHIUSDT", "YFIUSDT",
        "EGLDUSDT", "KSMUSDT", "JSTUSDT", "SUNUSDT", "BZRXUSDT", "RENUSDT",
        "REQUSDT", "NMRUSDT", "RLCUSDT", "UMAUSDT", "POLYUSDT", "LINAUSDT",
        "AKROUSDT", "STORJUSDT", "DIAUSDT", "BELUSDT", "WINGUSDT", "CTKUSDT",
        "TKOUSDT", "ALICEUSDT", "LTOUSDT", "CKBUSDT", "TWTUSDT", "FIROUSDT",
        "BETAUSDT", "PERLUSDT", "KEYUSDT", "DREPUSDT", "TROYUSDT", "COCOSUSDT",
        "MTLUSDT", "VITEUSDT", "DEGOUSDT", "TORNUSDT", "KEEPUSDT", "API3USDT",
        "PUNDIXUSDT", "PNTUSDT", "CLVUSDT", "ICPUSDT", "ARPAUSDT", "RADUSDT",
        "BALUSDT", "GTCUSDT", "QUICKUSDT", "REEFUSDT", "OGNUSDT", "CVPUSDT",
        "AGLDUSDT", "NUUSDT", "IDEXUSDT", "VISRUSDT", "BADGERUSDT", "EPSUSDT",
        "ALPHAUSDT", "INSURUSDT", "TRUUSDT", "LQTYUSDT", "STXUSDT", "FORTHUSDT",
        "BICOUSDT", "GODSUSDT", "IMXUSDT", "NBTUSDT", "ANTUSDT", "GASUSDT",
        "POWRUSDT", "LOOMUSDT", "QNTUSDT", "NEXOUSDT", "FUNUSDT", "HIVEUSDT",
        "CHRUSDT", "SPELLUSDT", "JASMYUSDT", "DYDXUSDT", "SLPUSDT", "ICXUSDT",
        "GLMRUSDT", "ASTRUSDT", "GALUSDT", "OPUSDT", "LEVERUSDT", "MDTUSDT",
        "XVGUSDT", "ZENUSDT", "SCUSDT", "IOTAUSDT", "FLMUSDT", "CELRUSDT",
        "DATAUSDT", "AMBUSDT", "DASHUSDT", "ZECUSDT", "XMRUSDT", "KMDUSDT",
        "BATUSDT", "MANAUSDT", "SANDUSDT", "ENJUSDT", "ATLASUSDT", "POLISUSDT",
        "AUDIOUSDT", "RAREUSDT", "NFTUSDT", "TVKUSDT", "MBOXUSDT", "WAXPUSDT",
        "GMTUSDT", "APEUSDT", "GALUSDT", "PHBUSDT", "GNSUSDT", "MCUSDT",
        "VIBUSDT", "COSUSDT", "CTSIUSDT", "FIDAUSDT", "ORBSUSDT", "QKCUSDT",
        "DOCKUSDT", "TLMUSDT", "BURGERUSDT", "ALCXUSDT", "YGGUSDT", "ILVUSDT",
        "XNOUSDT", "ERNUSDT", "KLAYUSDT", "PROMUSDT", "VOXELUSDT", "GALAXUSDT",
        "CVXUSDT", "FXSUSDT", "JOEUSDT", "MKRUSDT", "ZRXUSDT", "BNTUSDT",
        "COMPUSDT", "SNXUSDT", "UMAUSDT", "MIRUSDT", "ROSEUSDT", "AVAXUSDT",
        "NEARUSDT", "CELOUSDT", "KDAUSDT", "XECUSDT", "IOTXUSDT", "ONTUSDT",
        "RVNUSDT", "ZILUSDT", "IOSTUSDT", "STMXUSDT", "ARDRUSDT", "NANOUSDT",
        "HNTUSDT", "IOSTUSDT", "PERPUSDT", "RIFUSDT", "SXPUSDT", "SYSUSDT",
        "DGBUSDT", "UTKUSDT", "XEMUSDT", "WANUSDT", "WTCUSDT", "FETUSDT",
        "CELRUSDT", "MATICUSDT", "ETCUSDT", "BCHUSDT", "EOSUSDT", "XLMUSDT",
        "TRXUSDT", "ADAUSDT", "XRPUSDT", "LTCUSDT", "ATOMUSDT", "ALGOUSDT"
    )
    TIMEFRAME: str = "5m"
    CANDLES_LIMIT: int = 100
    FAST_EMA: int = 8
    SLOW_EMA: int = 21
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9
    RSI_PERIOD: int = 14
    STOCH_PERIOD: int = 14
    POLL_SEC: float = 10.0  # Aumentado de 8.0 para reducir carga
    DRY_RUN: bool = False
    MAX_WORKERS_KLINE: int = 4  # Reducido de 8 para mejor rendimiento
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE: str = "bot_v12_20x_usdt.log"
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"
    SIGNAL_COOLDOWN_CYCLES: int = 25
    # Monitoreo de balance - Gestión de capital real
    MIN_BALANCE_THRESHOLD: float = 10.0
    RISK_PER_TRADE_PERCENT: float = 1.0  # Reducido de 2.0% para 20x
    # Configuración de conexión
    MAX_API_RETRIES: int = 3
    API_RETRY_DELAY: float = 1.0
    # Configuración de Mejora de IA
    AI_LEARNING_RATE: float = 0.02
    AI_EXPLORATION_RATE: float = 0.06
    AI_VOLATILITY_THRESHOLD: float = 2.5
    AI_TREND_STRENGTH_THRESHOLD: float = 25.0
    # Configuración de Estrategia Mejorada
    MIN_SIGNAL_STRENGTH: float = 0.35  # Aumentado de 0.30
    MAX_POSITION_HOLD_HOURS: int = 2
    VOLATILITY_ADJUSTMENT: bool = True
    # Gestión de Riesgo Mejorada
    MAX_DAILY_LOSS_PERCENT: float = 6.0
    MAX_DRAWDOWN_PERCENT: float = 10.0
    # Configuración de símbolos optimizada
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
    MIN_VOLUME_CONFIRMATION: float = 0.35
    # Configuración para timeframe múltiple
    HIGHER_TIMEFRAME_CONFIRMATION: bool = False  # Desactivado temporalmente para debugging
    HIGHER_TIMEFRAME: str = "15m"
    BTC_CORRELATION_FILTER: bool = True
    # Configuración de capital real y reinversión
    MIN_NOTIONAL_OVERRIDE: float = 5.0
    REINVESTMENT_ENABLED: bool = True
    REINVESTMENT_THRESHOLD: float = 0.4
    CAPITAL_GROWTH_TARGET: float = 0.8
    INITIAL_CAPITAL: float = 20.0
    CAPITAL_UPDATE_INTERVAL: int = 25
    # Nuevos parámetros para 20x leverage
    MIN_ADX_FOR_TREND: float = 12.0  # Aumentado de 8.0
    RSI_OVERBOUGHT: float = 72.0
    RSI_OVERSOLD: float = 28.0
    MAX_VOLATILITY_PERCENT: float = 25.0  # Reducido de 30.0%
    # Nuevos parámetros para gestión de riesgo mejorada
    MAX_CONSECUTIVE_LOSSES: int = 3
    LOW_VOLUME_THRESHOLD: float = 0.3
    MAX_SPREAD_PERCENT: float = 0.1
    
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
    OPTIMIZATION_INTERVAL: int = 15
    MIN_TRADES_FOR_ANALYSIS: int = 5
    LEVERAGE_ADJUSTMENT_STEP: int = 5
    MAX_LEVERAGE: int = 20
    MIN_LEVERAGE: int = 10
    VOLATILITY_THRESHOLD: float = 2.8

strategy_optimizer = STRATEGY_OPTIMIZER()

# -------------------- GESTOR DE CAPITAL -------------------- #
class CapitalManager:
    """Gestor de capital real con reinversión de ganancias"""

    def __init__(self, api):
        self.api = api
        self.current_balance = 0.0
        self.initial_balance = 0.0
        self.last_balance_update = 0
        self.total_profit = 0.0
        self.reinvested_profit = 0.0

    def get_real_balance(self) -> float:
        """Obtener el balance real de la cuenta"""
        try:
            account_info = self.api._safe_api_call(self.api.client.futures_account)
            if account_info:
                usdt_balance = next(
                    (float(a.get('walletBalance', 0))
                     for a in account_info.get('assets', [])
                     if a.get('asset') == 'USDT'),
                    0.0
                )
                return usdt_balance
        except Exception as e:
            log.error(f"Error obteniendo balance real: {e}")
        return 0.0

    def update_balance(self, force: bool = False) -> bool:
        """Actualizar el balance real"""
        current_time = time.time()
        if force or (current_time - self.last_balance_update > 240):
            new_balance = self.get_real_balance()
            if new_balance > 0:
                if self.current_balance == 0:
                    self.initial_balance = new_balance
                    log.info(f"💰 Capital inicial: {new_balance:.2f} USDT (20x leverage)")

                self.current_balance = new_balance
                self.last_balance_update = current_time
                self.total_profit = self.current_balance - self.initial_balance
                self._save_balance_to_db()
                return True
        return False

    def _save_balance_to_db(self):
        """Guardar balance en base de datos con reintentos"""
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
                    log.error(f"Error guardando balance en DB: {e}")
                    db.rollback()
                finally:
                    db.close()

        execute_with_retry(save_operation, max_retries=2, retry_delay=1)

    def should_reinvest(self, profit: float) -> bool:
        """Decidir si reinvertir las ganancias"""
        if not config.REINVESTMENT_ENABLED:
            return False
        return profit >= config.REINVESTMENT_THRESHOLD

    def reinvest_profit(self, profit: float):
        """Reinvertir las ganancias en el capital"""
        if profit > 0 and self.should_reinvest(profit):
            self.reinvested_profit += profit
            log.info(f"🔄 Reinvirtiendo {profit:.2f} USDT en el capital (20x)")

    def get_performance_stats(self) -> Dict:
        """Obtener estadísticas de rendimiento"""
        return {
            "current_balance": self.current_balance,
            "initial_balance": self.initial_balance,
            "total_profit": self.total_profit,
            "reinvested_profit": self.reinvested_profit,
            "profit_percentage": (self.total_profit / self.initial_balance * 100) if self.initial_balance > 0 else 0,
            "daily_target": config.CAPITAL_GROWTH_TARGET,
            "leverage": config.LEVERAGE
        }

# -------------------- NOTIFICADOR DE TELEGRAM MEJORADO -------------------- #
class TelegramNotifier:
    """Sistema avanzado de notificaciones por Telegram"""
    
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)
        self.message_queue = deque()
        self.sending = False
        
        if self.enabled:
            log.info(f"✅ Bot de Telegram configurado: Chat ID {self.chat_id}")
        else:
            log.warning("⚠️ Bot de Telegram no configurado. Agrega TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env")

    def send_message(self, message: str, parse_mode: str = "HTML", retry_count: int = 3) -> bool:
        """Envía mensaje a Telegram con manejo robusto de errores y cola"""
        if not self.enabled:
            return False

        # Agregar a la cola si ya se está enviando un mensaje
        if self.sending:
            self.message_queue.append((message, parse_mode))
            return True

        self.sending = True
        
        for attempt in range(retry_count):
            try:
                url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                    "disable_notification": False
                }
                
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                
                # Procesar siguiente mensaje en la cola
                self.sending = False
                if self.message_queue:
                    next_msg, next_parse_mode = self.message_queue.popleft()
                    threading.Thread(target=self.send_message, args=(next_msg, next_parse_mode), daemon=True).start()
                
                return True
                
            except requests.exceptions.RequestException as e:
                log.warning(f"⚠️ Error enviando mensaje Telegram (intento {attempt + 1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    time.sleep(2 ** attempt)  # Backoff exponencial
            except Exception as e:
                log.error(f"❌ Error inesperado en Telegram: {e}")
                break

        self.sending = False
        return False

    def notify_trade_opened(self, symbol: str, side: str, quantity: float, 
                          price: float, balance: float, leverage: int = 20):
        """Notifica apertura de trade"""
        emoji = "🟢" if side == "LONG" else "🔴"
        notional_value = quantity * price
        
        message = f"""
{emoji} <b>TRADE ABIERTO ({leverage}x)</b>

📈 <b>Símbolo:</b> {symbol}
🎯 <b>Dirección:</b> {side}
📊 <b>Cantidad:</b> {quantity:.4f}
💰 <b>Precio Entrada:</b> ${price:.6f}
💵 <b>Valor Nocional:</b> ${notional_value:.2f}
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
        notional_value = quantity * entry_price
        
        message = f"""
{emoji} <b>TRADE CERRADO ({leverage}x)</b>

📈 <b>Símbolo:</b> {symbol}
🎯 <b>Resultado:</b> {'✅ GANANCIA' if pnl >= 0 else '❌ PÉRDIDA'}
💰 <b>P&L:</b> ${pnl:+.2f} USDT
📊 <b>ROE:</b> {roe:+.2f}%
🔍 <b>Razón:</b> {reason}

📥 <b>Precio Entrada:</b> ${entry_price:.6f}
📤 <b>Precio Salida:</b> ${exit_price:.6f}
📦 <b>Cantidad:</b> {quantity:.4f}
💵 <b>Valor:</b> ${notional_value:.2f}

🏦 <b>Capital Actual:</b> ${balance:.2f} USDT
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

    def notify_balance_update(self, balance: float, profit: float, 
                            profit_percentage: float, leverage: int = 20):
        """Notifica actualización de balance"""
        emoji = "📈" if profit >= 0 else "📉"
        
        message = f"""
{emoji} <b>ACTUALIZACIÓN DE CAPITAL ({leverage}x)</b>

🏦 <b>Balance Actual:</b> ${balance:.2f} USDT
💰 <b>Profit Total:</b> ${profit:+.2f} USDT
📊 <b>Rentabilidad:</b> {profit_percentage:+.2f}%

⚡ <b>Apalancamiento:</b> {leverage}x
🎯 <b>Objetivo diario:</b> {config.CAPITAL_GROWTH_TARGET:.1f}%

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
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        mode = "TESTNET" if testnet else "MAINNET REAL"
        
        message = f"""
🤖 <b>BOT DE TRADING INICIADO</b>

✅ <b>Sistema activado</b>
🌐 <b>Modo:</b> {mode}
⚡ <b>Apalancamiento:</b> {leverage}x
🏦 <b>Trading:</b> {'SIMULACIÓN' if config.DRY_RUN else 'REAL'}
📊 <b>Estrategia:</b> 20x Leverage - USDT Pairs

⏰ <b>Hora de inicio:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

<b>📈 Características activas:</b>
• Gestión de capital real
• IA para ajuste de parámetros
• Notificaciones en tiempo real
• Análisis de rendimiento
• Sistema Telegram activo
        """
        return self.send_message(message)

    def notify_bot_stopped(self, reason: str = ""):
        """Notifica que el bot se ha detenido"""
        message = f"""
🛑 <b>BOT DE TRADING DETENIDO</b>

❌ <b>Estado:</b> INACTIVO
📝 <b>Razón:</b> {reason if reason else "Detenido manualmente"}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

    def notify_daily_report(self, report_data: Dict):
        """Notifica reporte diario"""
        message = f"""
📊 <b>REPORTE DIARIO DE TRADING (20x)</b>

🏦 <b>Balance Final:</b> ${report_data.get('final_balance', 0):.2f} USDT
💰 <b>P&L Diario:</b> ${report_data.get('daily_pnl', 0):+.2f} USDT
📈 <b>Trades Totales:</b> {report_data.get('total_trades', 0)}
✅ <b>Trades Ganadores:</b> {report_data.get('winning_trades', 0)}
❌ <b>Trades Perdedores:</b> {report_data.get('losing_trades', 0)}
🎯 <b>Win Rate:</b> {report_data.get('win_rate', 0):.1f}%

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        return self.send_message(message)

# -------------------- MANEJADOR DE COMANDOS DE TELEGRAM -------------------- #
class TelegramCommandHandler:
    """Maneja los comandos recibidos por Telegram"""
    
    def __init__(self, trading_bot):
        self.bot = trading_bot
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.last_update_id = 0
        
    def poll_commands(self):
        """Sondea continuamente los comandos de Telegram"""
        if not self.token:
            return
            
        while True:
            try:
                updates = self.get_updates()
                if updates:
                    for update in updates:
                        self.process_update(update)
                time.sleep(2)  # Verificar cada 2 segundos
            except Exception as e:
                log.error(f"Error en poll_commands: {e}")
                time.sleep(10)

    def get_updates(self):
        """Obtiene actualizaciones de Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params = {
                "offset": self.last_update_id + 1,
                "timeout": 30
            }
            response = requests.get(url, params=params, timeout=35)
            response.raise_for_status()
            data = response.json()
            
            if data.get("ok") and data.get("result"):
                return data["result"]
            return []
        except Exception as e:
            log.error(f"Error obteniendo updates de Telegram: {e}")
            return []

    def process_update(self, update):
        """Procesa una actualización de Telegram"""
        update_id = update.get("update_id")
        message = update.get("message", {})
        text = message.get("text", "").strip()
        chat_id = message.get("chat", {}).get("id")
        
        if update_id > self.last_update_id:
            self.last_update_id = update_id

        if not text or not chat_id:
            return

        # Verificar que el chat_id sea el autorizado
        authorized_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if str(chat_id) != str(authorized_chat_id):
            self.send_message(chat_id, "❌ No autorizado para usar este bot.")
            return

        # Procesar comandos
        command = text.lower()
        
        if command == "/start":
            self.send_welcome(chat_id)
        elif command == "/status":
            self.send_status(chat_id)
        elif command == "/balance":
            self.send_balance(chat_id)
        elif command == "/positions":
            self.send_positions(chat_id)
        elif command == "/stats":
            self.send_stats(chat_id)
        elif command == "/performance":
            self.send_performance(chat_id)
        elif command == "/stop":
            self.stop_bot(chat_id)
        elif command == "/start_bot":
            self.start_bot(chat_id)
        elif command == "/help":
            self.send_help(chat_id)
        else:
            self.send_message(chat_id, "❌ Comando no reconocido. Usa /help para ver comandos disponibles.")

    def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML"):
        """Enviar mensaje a Telegram"""
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
        """Mensaje de bienvenida"""
        with state_lock:
            status = app_state
            
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        mode = "TESTNET" if testnet else "MAINNET REAL"
        
        message = f"""
🤖 <b>BOT DE TRADING BINANCE FUTURES</b>

✅ <b>Estado:</b> {'🟢 ACTIVO' if status['running'] else '🔴 INACTIVO'}
🌐 <b>Modo:</b> {mode}
⚡ <b>Apalancamiento:</b> 20x
🏦 <b>Trading:</b> {'SIMULACIÓN' if config.DRY_RUN else 'REAL'}
💰 <b>Balance:</b> ${status['balance']:.2f} USDT

<b>📊 Comandos disponibles:</b>
/start - Mensaje de bienvenida
/status - Estado del trading  
/balance - Balance y ganancias
/positions - Posiciones abiertas
/stats - Estadísticas
/performance - Rendimiento
/stop - Detener bot
/start_bot - Iniciar bot
/help - Ayuda

⏰ <b>Hora:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        self.send_message(chat_id, message)

    def send_status(self, chat_id: int):
        """Enviar estado actual"""
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
        """Enviar información de balance"""
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
        """Enviar posiciones abiertas"""
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
            leverage = position.get('leverage', 20)
            
            message += f"""
📈 <b>{symbol}</b>
🎯 <b>Dirección:</b> {side}
💰 <b>Precio entrada:</b> ${entry_price:.6f}
📊 <b>P&L No realizado:</b> ${unrealized_pnl:+.2f}
⚡ <b>Apalancamiento:</b> {leverage}x
            """
            
        self.send_message(chat_id, message)

    def send_stats(self, chat_id: int):
        """Enviar estadísticas"""
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
        """Enviar rendimiento por símbolo"""
        # Esta función puede expandirse para mostrar estadísticas por símbolo
        message = """
📊 <b>RENDIMIENTO POR SÍMBOLO</b>

🔍 <i>Funcionalidad en desarrollo...</i>
📈 Próximamente: Estadísticas detalladas por par de trading
        """
        self.send_message(chat_id, message)

    def stop_bot(self, chat_id: int):
        """Detener el bot"""
        with state_lock:
            app_state["running"] = False
            app_state["status_message"] = "Detenido por Telegram"
            
        # Notificar por Telegram
        if self.bot.telegram_notifier.enabled:
            self.bot.telegram_notifier.notify_bot_stopped("Comando por Telegram")
        
        self.send_message(chat_id, "🛑 <b>Bot detenido exitosamente</b>")

    def start_bot(self, chat_id: int):
        """Iniciar el bot"""
        global bot_thread
        
        with state_lock:
            if app_state["running"]:
                self.send_message(chat_id, "⚠️ <b>El bot ya está en ejecución</b>")
                return
                
            app_state["running"] = True
            app_state["status_message"] = "Iniciado por Telegram"
        
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
        
        self.send_message(chat_id, "🚀 <b>Bot iniciado exitosamente</b>")
        if self.bot.telegram_notifier.enabled:
            self.bot.telegram_notifier.notify_bot_started(config.LEVERAGE)

    def send_help(self, chat_id: int):
        """Enviar ayuda"""
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        mode = "TESTNET" if testnet else "MAINNET REAL"
        
        message = f"""
🤖 <b>AYUDA - COMANDOS DISPONIBLES</b>

/start - Mensaje de bienvenida
/status - Estado actual del trading
/balance - Ver balance y ganancias
/positions - Posiciones abiertas actuales
/stats - Estadísticas de performance
/performance - Rendimiento por símbolo
/stop - Detener el bot
/start_bot - Iniciar bot
/help - Mostrar esta ayuda

<b>📊 Información adicional:</b>
• El bot opera con 20x leverage
• Modo: {mode}
• Trading: {'SIMULACIÓN' if config.DRY_RUN else 'REAL'}
• Monitorea USDT pairs con alta liquidez
• Notificaciones automáticas de trades

⏰ <b>Soporte:</b> gregorbc@gmail.com
        """
        self.send_message(chat_id, message)

# -------------------- MEJORAS DE IA -------------------- #
@dataclass
class AIModel:
    """Modelo de IA para optimización de parámetros de trading"""
    learning_rate: float = config.AI_LEARNING_RATE
    exploration_rate: float = config.AI_EXPLORATION_RATE
    q_table: Dict = field(default_factory=dict)

    def get_action(self, state: str) -> Tuple[float, float]:
        """Obtiene la mejor acción (sl_adj, tp_adj) para un estado dado"""
        if state not in self.q_table or random.random() < self.exploration_rate:
            sl_adj = random.uniform(0.7, 1.3)
            tp_adj = random.uniform(0.8, 1.5)
            self.q_table[state] = (sl_adj, tp_adj, 0)
        return self.q_table[state][0], self.q_table[state][1]

    def update_model(self, state: str, reward: float, sl_adj: float, tp_adj: float):
        """Actualiza el modelo Q-learning con la recompensa obtenida"""
        if state in self.q_table:
            current_reward = self.q_table[state][2]
            new_reward = current_reward + self.learning_rate * (reward - current_reward)
            self.q_table[state] = (sl_adj, tp_adj, new_reward)

@dataclass
class MarketAnalyzer:
    """Analizador de condiciones del mercado"""
    volatility_threshold: float = config.AI_VOLATILITY_THRESHOLD
    trend_strength_threshold: float = config.AI_TREND_STRENGTH_THRESHOLD

    def analyze_market_conditions(self, symbol: str, df: pd.DataFrame) -> Dict[str, float]:
        """Analiza las condiciones del mercado para un símbolo"""
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
    """Analizador de rendimiento basado en datos históricos"""

    def __init__(self, db_session=None):
        self.db_session = db_session
        self.symbol_performance = {}
        self._load_performance_data()

    def _load_performance_data(self):
        """Cargar datos de rendimiento históricos con manejo de errores"""
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
                log.error(f"Error cargando datos de rendimiento: {e}")
            finally:
                db.close()

        execute_with_retry(load_operation, max_retries=2, retry_delay=1)

    def get_symbol_risk_factor(self, symbol: str) -> float:
        """Calcular factor de riesgo para un símbolo basado en historial"""
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

# -------------------- CONFIGURACIÓN DE APLICACIÓN FLASK -------------------- #
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
CORS(app)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

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

# -------------------- SISTEMA DE LOGS EN TIEMPO REAL -------------------- #

class RealTimeLogHandler(logging.Handler):
    """Manejador de logs que emite en tiempo real via Socket.IO"""
    
    def __init__(self, socketio):
        super().__init__()
        self.socketio = socketio
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    def emit(self, record):
        try:
            log_entry = self.format(record)
            level = record.levelname.lower()
            
            # Emitir via Socket.IO
            self.socketio.emit('log_update', {
                'message': log_entry,
                'level': level,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            print(f"Error en RealTimeLogHandler: {e}")

# Configurar el logger principal para logs en tiempo real
def setup_realtime_logging():
    """Configurar el sistema de logs en tiempo real"""
    # Remover handlers existentes para evitar duplicados
    log.handlers = []
    
    # Handler para archivo
    file_handler = logging.FileHandler(f'logs/{config.LOG_FILE}', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(config.LOG_FORMAT))
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(config.LOG_FORMAT))
    
    # Handler para tiempo real
    realtime_handler = RealTimeLogHandler(socketio)
    realtime_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # Agregar todos los handlers
    log.addHandler(file_handler)
    log.addHandler(console_handler)
    log.addHandler(realtime_handler)
    
    log.setLevel(getattr(logging, config.LOG_LEVEL))

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

# -------------------- CLIENTE BINANCE MEJORADO -------------------- #
class BinanceFutures:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError("API keys no configuradas. Establezca las variables de entorno BINANCE_API_KEY and BINANCE_API_SECRET")

        self.client = Client(api_key, api_secret, testnet=testnet)
        
        # Mostrar información de conexión
        mode = "TESTNET" if testnet else "MAINNET REAL"
        log.info(f"🔧 CONECTADO A BINANCE FUTURES {mode} - 20x LEVERAGE")
        
        if testnet:
            log.info("⚠️ MODO TESTNET - No se realizarán operaciones reales")
        else:
            log.info("🚀 MODO REAL - Se realizarán operaciones con dinero real")

        try:
            self.exchange_info = self.client.futures_exchange_info()
            log.info("✅ Información de exchange cargada exitosamente")
        except Exception as e:
            log.error(f"❌ Error conectando a Binance: {e}")
            raise

    def is_symbol_tradable(self, symbol: str) -> bool:
        """Verifica si un símbolo está disponible para trading"""
        try:
            # Para símbolos principales como BTCUSDT, ETHUSDT, asumir que son tradables
            # para evitar problemas con la estructura de datos del exchange
            major_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'XRPUSDT', 'SOLUSDT']
            if symbol in major_symbols:
                return True
                
            s_info = next((s for s in self.exchange_info['symbols'] if s['symbol'] == symbol), None)
            if not s_info:
                log.warning(f"Símbolo {symbol} no encontrado en exchange info")
                return False
                
            status = s_info.get('status')
            if status != 'TRADING':
                log.info(f"Símbolo {symbol} no disponible. Estado: {status}")
                return False
                
            # Verificación más flexible para contratos
            contract_type = s_info.get('contractType', '')
            if contract_type not in ['PERPETUAL', 'CURRENT_QUARTER', 'NEXT_QUARTER']:
                log.info(f"Símbolo {symbol} no es un contrato válido. Tipo: {contract_type}")
                return False

            return True
            
        except Exception as e:
            log.error(f"Error verificando símbolo {symbol}: {e}")
            # En caso de error, permitir símbolos principales
            return symbol in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']

    def ensure_symbol_settings(self, symbol: str):
        if not self.is_symbol_tradable(symbol):
            log.warning(f"⏭️ Símbolo {symbol} no está disponible para trading, omitiendo configuración")
            return

        try:
            _ = self._safe_api_call(self.client.futures_change_leverage, symbol=symbol, leverage=int(config.LEVERAGE))
            log.info(f"✅ Apalancamiento configurado a {config.LEVERAGE}x para {symbol}")
        except Exception as e:
            log.warning(f"Problema al establecer leverage para {symbol}: {e}")

        try:
            self.client.futures_change_margin_type(symbol=symbol, marginType=config.MARGIN_TYPE)
        except BinanceAPIException as e:
            if e.code == -4046 or "No need to change margin type" in e.message:
                pass
            else:
                log.warning(f"Advertencia al establecer tipo de margen para {symbol}: {e}")
        except Exception as e:
            log.error(f"Error inesperado al establecer tipo de margen para {symbol}: {e}")

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
                    log.warning("Error PERCENT_PRICE (-4131) en orden. Mercado volátil o ilíquido. Omitiendo.")
                    return None
                elif e.code == -1122:  # Invalid symbol status
                    log.warning(f"❌ Símbolo no disponible (error -1122): {e.message}")
                    return None  # No reintentar para este error
                elif e.code in [-2011, -2021]:
                    log.warning(f"Error de API en orden ({e.code}): {e.message}")
                else:
                    log.warning(f"Error no crítico de API: {e.code} - {e.message}")
                    if attempt == config.MAX_API_RETRIES - 1:
                        log.error(f"Error final de API después de todos los reintentos: {e.code} - {e.message}")
            except Exception as e:
                with state_lock:
                    app_state["connection_metrics"]["api_retries"] += 1
                log.warning(f"Error general en llamada a API: {e}")
                if attempt == config.MAX_API_RETRIES - 1:
                    log.error(f"Error general final después de todos los reintentos: {e}")

        return None

    def smart_retry_api_call(self, func, *args, **kwargs):
        """Llamada a API con reintentos inteligentes basados en el tipo de error"""
        retry_delays = [1, 2, 4, 8, 16]
        last_exception = None

        for attempt, delay in enumerate(retry_delays):
            try:
                result = func(*args, **kwargs)

                if attempt > 0:
                    log.info(f"✅ Reintento exitoso después de {attempt} intentos")

                return result
            except BinanceAPIException as e:
                last_exception = e

                if e.code in [-1013, -2010, -2011, -1122]:
                    log.error(f"Error no recuperable: {e.message} (código: {e.code})")
                    break

                log.warning(f"Reintentando en {delay}s (intento {attempt + 1}/{len(retry_delays)})")
                time.sleep(delay)

            except Exception as e:
                last_exception = e
                log.warning(f"Error general, reintentando en {delay}s (intento {attempt + 1}/{len(retry_delays)})")
                time.sleep(delay)

        log.error(f"❌ Todos los reintentos fallados: {last_exception}")
        return None

    def get_symbol_filters(self, symbol: str) -> Optional[Dict[str, float]]:
        try:
            s_info = next((s for s in self.exchange_info['symbols'] if s['symbol'] == symbol), None)
            if not s_info:
                log.warning(f"Símbolo {symbol} no encontrado en exchange info")
                return None
                
            if s_info.get('status') != 'TRADING':
                log.warning(f"Símbolo {symbol} no está disponible para trading. Estado: {s_info.get('status')}")
                return None

            filters = {f['filterType']: f for f in s_info['filters']}
            
            required_filters = ['LOT_SIZE', 'PRICE_FILTER']
            if not all(req in filters for req in required_filters):
                log.warning(f"Símbolo {symbol} no tiene todos los filtros requeridos")
                return None
                
            result = {
                "stepSize": float(filters['LOT_SIZE']['stepSize']),
                "minQty": float(filters['LOT_SIZE']['minQty']),
                "tickSize": float(filters['PRICE_FILTER']['tickSize'])
            }
            
            # MIN_NOTIONAL puede no estar presente en todos los símbolos
            if 'MIN_NOTIONAL' in filters:
                result["minNotional"] = float(filters['MIN_NOTIONAL'].get('notional', 5.0))
            else:
                result["minNotional"] = 5.0  # Valor por defecto
                
            return result
            
        except Exception as e:
            log.error(f"Error obteniendo filters para {symbol}: {e}")
            return None

    def place_order(self, symbol: str, side: str, order_type: str, quantity: float,
                   price: Optional[float] = None, reduce_only: bool = False) -> Optional[Dict]:
        if not self.is_symbol_tradable(symbol):
            log.error(f"❌ No se puede colocar orden para símbolo no tradable: {symbol}")
            return None

        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'quantity': quantity
        }

        if order_type == FUTURE_ORDER_TYPE_LIMIT:
            if price is None:
                log.error("Precio requerido para órdenes LIMIT.")
                return None
            params.update({
                'price': str(price),
                'timeInForce': TIME_IN_FORCE_GTC
            })

        if reduce_only:
            params['reduceOnly'] = 'true'

        if config.DRY_RUN:
            log.info(f"[DRY_RUN] place_order: {params}")
            return {'mock': True, 'orderId': int(time.time() * 1000)}

        return self.smart_retry_api_call(self.client.futures_create_order, **params)

    def close_position(self, symbol: str, position_amt: float) -> Optional[Dict]:
        if not self.is_symbol_tradable(symbol):
            log.error(f"❌ No se puede cerrar posición para símbolo no tradable: {symbol}")
            return None

        side = SIDE_SELL if position_amt > 0 else SIDE_BUY
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] close_position {symbol} {position_amt}")
            return {'mock': True, 'orderId': int(time.time() * 1000)}
        return self.place_order(symbol, side, FUTURE_ORDER_TYPE_MARKET, abs(position_amt), reduce_only=True)

    def cancel_order(self, symbol: str, orderId: int) -> Optional[Dict]:
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] cancel_order: {orderId} para {symbol}")
            return {'mock': True}

        try:
            return self.smart_retry_api_call(self.client.futures_cancel_order, symbol=symbol, orderId=orderId)
        except Exception as e:
            log.warning(f"No se pudo cancelar la orden {orderId} para {symbol}: {e}")
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
        
        # Sistema de Telegram
        self.telegram_notifier = TelegramNotifier()
        self.telegram_handler = TelegramCommandHandler(self)
        
        # Iniciar polling de comandos de Telegram en hilo separado
        if self.telegram_notifier.enabled:
            telegram_polling_thread = threading.Thread(
                target=self.telegram_handler.poll_commands, 
                daemon=True
            )
            telegram_polling_thread.start()
            log.info("✅ Sistema de comandos de Telegram iniciado")

        try:
            self.performance_analyzer = PerformanceAnalyzer(SessionLocal() if DB_ENABLED else None)
        except Exception as e:
            log.error(f"Error inicializando PerformanceAnalyzer: {e}")
            self.performance_analyzer = None
            
        self.daily_pnl = 0.0
        self.daily_starting_balance = 0.0
        self.today = datetime.now().date()

    def check_volatility_safety(self, symbol: str, df: pd.DataFrame) -> bool:
        """Verificar que la volatilidad esté dentro de límites seguros para 20x"""
        if df is None or len(df) < 20:
            return True
            
        try:
            # Calcular volatilidad reciente (últimas 10 velas)
            returns = df['close'].pct_change().dropna()
            if len(returns) < 10:
                return True
                
            recent_volatility = returns.tail(10).std() * np.sqrt(365) * 100
            
            if recent_volatility > config.MAX_VOLATILITY_PERCENT:
                log.warning(f"⚡ Volatilidad peligrosa en {symbol}: {recent_volatility:.1f}%")
                return False
                
            return True
        except Exception as e:
            log.error(f"Error calculando volatilidad para {symbol}: {e}")
            return True

    def safe_restart(self):
        """Reinicio seguro del bot"""
        log.info("🔄 Intentando reinicio seguro en 60 segundos...")
        time.sleep(60)
        
        # Limpiar estado
        with state_lock:
            app_state["open_positions"] = {}
            app_state["trailing_stop_data"] = {}
            app_state["sl_tp_data"] = {}
        
        # Reconectar API
        try:
            self.api = BinanceFutures()
            log.info("✅ Reconexión a API exitosa")
        except Exception as e:
            log.error(f"❌ Error en reconexión: {e}")
            return
        
        # Continuar ejecución
        self.run()

    def cleanup_problematic_symbols(self, symbols: List[str]) -> List[str]:
        """Limpia símbolos problemáticos de forma proactiva"""
        problematic_keywords = [
            '1000', '10000', 'AI', 'MEME', 'CHEEMS', 'NAORIS', 'COAI', 
            '4USDT', 'TOWNS', 'UMA', 'OMNI', 'ALPHA', 'QUSDT'
        ]
        
        clean_symbols = []
        
        for symbol in symbols:
            if not any(keyword in symbol for keyword in problematic_keywords):
                clean_symbols.append(symbol)
        
        removed_count = len(symbols) - len(clean_symbols)
        if removed_count > 0:
            log.info(f"🧹 Limpiados {removed_count} símbolos problemáticos")
        
        return clean_symbols

    def get_top_symbols(self) -> List[str]:
        tickers = self.api._safe_api_call(self.api.client.futures_ticker)
        if not tickers:
            return []

        exchange_info = self.api.exchange_info
        symbol_info_map = {s['symbol']: s for s in exchange_info['symbols']}

        # Filtros más estrictos para símbolos
        valid_tickers = []
        for t in tickers:
            symbol = t['symbol']
            
            # Verificar si el símbolo existe y es tradable
            if symbol not in symbol_info_map:
                continue
                
            symbol_info = symbol_info_map[symbol]
            
            # Verificar que el símbolo esté disponible para trading
            if symbol_info.get('status') != 'TRADING':
                continue
                
            # Excluir símbolos problemáticos (usando las listas actualizadas)
            if (symbol.endswith('USDT') and
                symbol not in config.EXCLUDE_SYMBOLS and
                symbol not in config.BLACKLIST_SYMBOLS and
                float(t['quoteVolume']) > config.MIN_24H_VOLUME and
                not any(x in symbol for x in ['1000', '10000', 'AI', 'MEME', 'CHEEMS', 'NAORIS', 'COAI', '4USDT'])):
            
                # Verificar que el símbolo tenga los filtros necesarios
                filters = self.api.get_symbol_filters(symbol)
                if not filters:
                    continue
                    
                # Verificar precio válido
                if float(t.get('lastPrice', 0)) <= 0:
                    continue
                    
                # Verificar volumen válido
                if float(t.get('volume', 0)) <= 0:
                    continue
                    
                valid_tickers.append(t)

        # Ordenar por volumen de forma descendente
        valid_tickers.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
        
        # Tomar los mejores símbolos con buena liquidez (usando el nuevo límite)
        top_symbols = []
        for t in valid_tickers[:config.NUM_SYMBOLS_TO_SCAN]:
            symbol = t['symbol']
            
            # Verificación adicional de precio y volumen
            price = float(t['lastPrice'])
            volume = float(t['quoteVolume'])
            
            if price > 0.001 and volume > 100000:  # Filtros adicionales
                top_symbols.append(symbol)
        
        # Limpiar símbolos problemáticos
        top_symbols = self.cleanup_problematic_symbols(top_symbols)
        
        log.info(f"🔍 Encontrados {len(top_symbols)} símbolos válidos de {len(valid_tickers)} posibles")
        return top_symbols

    def validate_symbol_data(self, symbol: str, df: pd.DataFrame) -> bool:
        """Valida que los datos del símbolo sean de calidad"""
        if df is None or len(df) < 50:
            return False
        
        # Verificar datos nulos
        if df[['open', 'high', 'low', 'close', 'volume']].isna().any().any():
            log.info(f"📊 {symbol} tiene datos nulos, omitiendo")
            return False
        
        # Verificar volumen cero
        if (df['volume'] == 0).any():
            log.info(f"📊 {symbol} tiene volumen cero, omitiendo")
            return False
        
        # Verificar precios válidos
        if (df[['open', 'high', 'low', 'close']] <= 0).any().any():
            log.info(f"📊 {symbol} tiene precios inválidos, omitiendo")
            return False
        
        return True

    def get_klines_for_symbol(self, symbol: str, interval: str = None, limit: int = None) -> Optional[pd.DataFrame]:
        # Obtener klines incluso para símbolos no marcados como tradables
        # para evitar perder datos de símbolos principales
        klines = self.api._safe_api_call(
            self.api.client.futures_klines,
            symbol=symbol,
            interval=interval or config.TIMEFRAME,
            limit=limit or config.CANDLES_LIMIT
        )
        if not klines: 
            return None
            
        try:
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.dropna(subset=['close'])
            df['symbol'] = symbol
            
            # Validar calidad de datos
            if not self.validate_symbol_data(symbol, df):
                return None
                
            return df
        except Exception as e:
            log.error(f"Error procesando klines para {symbol}: {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame):
        """Calcular indicadores técnicos con manejo robusto de errores"""
        if df is None or len(df) < 5:
            return          
        try:
            # Calcular EMAs
            df['fast_ema'] = df['close'].ewm(span=config.FAST_EMA, adjust=False).mean()
            df['slow_ema'] = df['close'].ewm(span=config.SLOW_EMA, adjust=False).mean()
            
            # Calcular RSI
            delta = df['close'].diff()
            up, down = delta.copy(), delta.copy()
            up[up < 0] = 0
            down[down > 0] = 0
            
            roll_up = up.ewm(span=config.RSI_PERIOD, adjust=False).mean()
            roll_down = down.abs().ewm(span=config.RSI_PERIOD, adjust=False).mean()
            rs = roll_up / roll_down.replace(0, np.nan)
            df['rsi'] = 100.0 - (100.0 / (1.0 + rs)).fillna(50)

            # Calcular MACD
            exp1 = df['close'].ewm(span=config.MACD_FAST, adjust=False).mean()
            exp2 = df['close'].ewm(span=config.MACD_SLOW, adjust=False).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=config.MACD_SIGNAL, adjust=False).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']

            # Calcular Stoch RSI
            stoch_rsi = (df['rsi'] - df['rsi'].rolling(config.STOCH_PERIOD).min()) / \
                       (df['rsi'].rolling(config.STOCH_PERIOD).max() - df['rsi'].rolling(config.STOCH_PERIOD).min())
            df['stoch_rsi'] = stoch_rsi * 100

            # Calcular Bollinger Bands
            df['bb_middle'] = df['close'].rolling(20).mean()
            bb_std = df['close'].rolling(20).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
            df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
            df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

            # Calcular volatilidad
            df['returns'] = df['close'].pct_change()
            df['volatility'] = df['returns'].rolling(20).std() * np.sqrt(365) * 100
            
        except Exception as e:
            log.error(f"Error calculando indicadores: {e}")
            # Establecer valores por defecto para evitar que falle el análisis
            df['fast_ema'] = df['close']
            df['slow_ema'] = df['close']
            df['rsi'] = 50
            df['macd'] = 0
            df['macd_signal'] = 0
            df['macd_hist'] = 0
            df['stoch_rsi'] = 50
            df['bb_middle'] = df['close']
            df['bb_upper'] = df['close']
            df['bb_lower'] = df['close']
            df['bb_width'] = 0
            df['returns'] = 0
            df['volatility'] = 0

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        if len(df) < period * 2 + 1:
            return 0.0
        
        try:
            if TALIB_ENABLED:
                high = df['high'].astype(float).values
                low = df['low'].astype(float).values
                close = df['close'].astype(float).values
                
                adx_values = talib.ADX(high, low, close, timeperiod=period)
                
                valid_adx = adx_values[~np.isnan(adx_values)]
                if len(valid_adx) > 0:
                    result = float(valid_adx[-1])
                    return result
                return 0.0
            else:
                return self._calculate_adx_manual(df, period)
                
        except Exception as e:
            symbol = df['symbol'].iloc[-1] if 'symbol' in df.columns else 'UNKNOWN'
            log.error(f"Error calculando ADX para {symbol}: {e}")
            return 0.0

    def _calculate_adx_manual(self, df: pd.DataFrame, period: int = 14) -> float:
        try:
            high, low, close = df['high'], df['low'], df['close']
            
            up_move = high.diff()
            down_move = low.diff().abs() * -1
            
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move.abs(), 0)
            
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            atr = true_range.rolling(period).mean()
            
            plus_di = 100 * (pd.Series(plus_dm).rolling(period).mean() / atr)
            minus_di = 100 * (pd.Series(minus_dm).rolling(period).mean() / atr)
            
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
            adx = dx.rolling(period).mean()
            
            result = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
            return result
            
        except Exception as e:
            log.error(f"Error en cálculo manual de ADX: {e}")
            return 0.0

    def calculate_signal_strength(self, df: pd.DataFrame, signal: str, symbol: str) -> float:
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
            
        # Verificación de volatilidad (nueva)
        if not self.check_volatility_safety(symbol, df):
            return None
            
        last, prev = df.iloc[-1], df.iloc[-2]

        # Verificar que tenemos datos válidos
        if any(pd.isna([last['close'], last['volume'], last['high'], last['low']])):
            return None

        # Verificar volumen mínimo absoluto
        min_volume_threshold = 1000  # Volumen mínimo en USDT
        current_volume_usdt = last['volume'] * last['close']
        if current_volume_usdt < min_volume_threshold:
            log.info(f"📉 {symbol} volumen muy bajo: ${current_volume_usdt:.0f}")
            return None

        # Verificar ADX para 20x - requisitos más estrictos
        if len(df) >= 28:
            adx = self.calculate_adx(df)
            if adx < config.MIN_ADX_FOR_TREND:
                log.info(f"↔️ ADX bajo para {symbol} (ADX: {adx:.1f}), omitiendo")
                return None

        # Verificar volatilidad para 20x
        if 'volatility' in df.columns and not pd.isna(df['volatility'].iloc[-1]):
            volatility = df['volatility'].iloc[-1]
            if volatility > config.MAX_VOLATILITY_PERCENT:
                log.info(f"⚡ Alta volatilidad en {symbol}: {volatility:.1f}%, omitiendo")
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
            
            # Verificar que el volumen promedio sea válido
            if volume_avg <= 0:
                log.info(f"📉 {symbol} volumen promedio inválido: {volume_avg}")
                return None
                
            volume_ratio = current_volume / volume_avg if volume_avg > 0 else 0

            if volume_ratio < config.MIN_VOLUME_CONFIRMATION:
                log.info(f"📉 Señal {signal} descartada por volumen insuficiente: {volume_ratio:.2f}")
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
                        log.info(f"⏭️ Señal {signal} en {symbol} descartada por falta de alineación con TF superior ({higher_tf_signal})")
                        return None
            except Exception as e:
                log.error(f"Error verificando TF superior para {symbol}: {e}")

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
                    strength = self.calculate_signal_strength(df, signal, symbol)
                    strength *= 0.6
                    log.info(f"⚠️ Señal {signal} en {symbol} con señal contraria en BTC, fuerza reducida a {strength:.2f}")

        strength = self.calculate_signal_strength(df, signal, symbol)
        self.signal_strength[symbol] = strength

        if strength < config.MIN_SIGNAL_STRENGTH:
            log.info(f"📉 Señal {signal} descartada por fuerza insuficiente: {strength:.2f}")
            return None

        log.info(f"📶 Señal {signal} con fuerza: {strength:.2f}, confirmaciones: {confirmations}/3")
        return signal

    def get_ai_adjustments(self, symbol: str, performance_data: Dict) -> Tuple[float, float]:
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
            log.error(f"Error actualizando modelo de IA para {symbol}: {e}")

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
                        log.info(f"🤖 Ajuste de Trailing por IA para {symbol}: {trailing_adjustment:.2f} (Volatilidad: {performance_data.get('market_volatility', 0):.2f}%)")

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
                    log.info(f"🔔 Trailing stop activado para {symbol} (adj: {trailing_data['trailing_adjustment']:.2f})")
                if trailing_data['activated']:
                    new_stop = trailing_data['best_price'] * (1 - stop_percentage / 100)
                    if new_stop > trailing_data['current_stop']:
                        trailing_data['current_stop'] = new_stop
                    if current_price <= trailing_data['current_stop']:
                        log.info(f"🔴 Cierre por trailing stop: {symbol} @ {current_price} (Stop: {trailing_data['current_stop']})")
                        should_close = True
            else:
                if current_price < trailing_data['best_price']:
                    trailing_data['best_price'] = current_price
                profit_percentage = ((entry_price - current_price) / entry_price) * 100
                if not trailing_data['activated'] and profit_percentage >= activation_percent:
                    trailing_data['activated'] = True
                    log.info(f"🔔 Trailing stop activado para {symbol} (adj: {trailing_data['trailing_adjustment']:.2f})")
                if trailing_data['activated']:
                    new_stop = trailing_data['best_price'] * (1 + stop_percentage / 100)
                    if new_stop < trailing_data['current_stop']:
                        trailing_data['current_stop'] = new_stop
                    if current_price >= trailing_data['current_stop']:
                        log.info(f"🔴 Cierre por trailing stop: {symbol} @ {current_price} (Stop: {trailing_data['current_stop']})")
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
                        log.info(f"🤖 Ajuste SL/TP por IA para {symbol}: SL={sl_adjustment:.2f}, TP={tp_adjustment:.2f}")

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
                log.info(f"SL/TP inicializado para {symbol}: SL @ {sl_price:.4f} (adj: {sl_adjustment:.2f}), TP @ {tp_price:.4f} (adj: {tp_adjustment:.2f})")

            sl_price = sl_tp_data.get('sl_price')
            tp_price = sl_tp_data.get('tp_price')

            if not sl_price or not tp_price:
                return False

            if position_side == 'LONG':
                if current_price <= sl_price:
                    log.info(f"🔴 Cierre por STOP LOSS: {symbol} @ {current_price} (SL: {sl_price})")
                    return 'SL'
                elif current_price >= tp_price:
                    log.info(f"🟢 Cierre por TAKE PROFIT: {symbol} @ {current_price} (TP: {tp_price})")
                    return 'TP'
            else:
                if current_price >= sl_price:
                    log.info(f"🔴 Cierre por STOP LOSS: {symbol} @ {current_price} (SL: {sl_price})")
                    return 'SL'
                elif current_price <= tp_price:
                    log.info(f"🟢 Cierre por TAKE PROFIT: {symbol} @ {current_price} (TP: {tp_price})")
                    return 'TP'
            return False

    def check_time_based_exit(self, symbol: str, position: Dict) -> bool:
        update_time = position.get('updateTime', 0)
        if update_time == 0:
            return False

        hours_held = (time.time() * 1000 - update_time) / (1000 * 60 * 60)
        if hours_held > config.MAX_POSITION_HOLD_HOURS:
            log.info(f"⏰ Cierre por tiempo: {symbol} held for {hours_held:.1f} hours")
            return True
        return False

    def check_momentum_reversal(self, symbol: str, position: Dict, df: pd.DataFrame) -> bool:
        if df is None or len(df) < 10 or 'rsi' not in df.columns:
            return False

        position_side = 'LONG' if float(position['positionAmt']) > 0 else 'SHORT'
        current_rsi = df['rsi'].iloc[-1]
        prev_rsi = df['rsi'].iloc[-2]

        if position_side == 'LONG':
            price_trend = df['close'].iloc[-1] > df['close'].iloc[-3]
            rsi_trend = current_rsi < prev_rsi
            if price_trend and rsi_trend and current_rsi > 70:
                log.info(f"↘️ Cierre por divergencia RSI bajista: {symbol}")
                return True
        else:
            price_trend = df['close'].iloc[-1] < df['close'].iloc[-3]
            rsi_trend = current_rsi > prev_rsi
            if price_trend and rsi_trend and current_rsi < 30:
                log.info(f"↗️ Cierre por divergencia RSI alcista: {symbol}")
                return True

        return False

    def dynamic_exit_strategy(self, symbol: str, position: Dict, current_price: float, df: pd.DataFrame) -> Optional[str]:
        if df is not None and len(df) > 20:
            volume_avg = df['volume'].rolling(20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            
            if current_volume < volume_avg * config.LOW_VOLUME_THRESHOLD:
                log.info(f"⚠️ Volumen anormalmente bajo en {symbol}, cerrando posición")
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

        current_balance = self.capital_manager.current_balance

        if current_balance < config.MIN_BALANCE_THRESHOLD:
            log.warning(f"⚠️ Balance bajo: {current_balance:.2f} USDT (mínimo: {config.MIN_BALANCE_THRESHOLD} USDT)")
            return True

        open_positions = {p['symbol']: p for p in account_info['positions'] if float(p['positionAmt']) != 0}
        total_investment = sum(float(p.get('initialMargin', 0) or 0) for p in open_positions.values())
        exposure_ratio = total_investment / current_balance if current_balance > 0 else 0

        if exposure_ratio > 0.8:
            log.warning(f"⚠️ Exposición demasiado alta: {exposure_ratio:.2%}")
        
        with state_lock:
            app_state["risk_metrics"]["exposure_ratio"] = exposure_ratio
            if app_state["balance_history"]:
                peak = max(app_state["balance_history"])
                drawdown = (peak - current_balance) / peak * 100 if peak > 0 else 0
                app_state["risk_metrics"]["max_drawdown"] = max(app_state["risk_metrics"]["max_drawdown"], drawdown)

                if drawdown > config.MAX_DRAWDOWN_PERCENT:
                    log.warning(f"⛔ Drawdown máximo excedido: {drawdown:.2f}%")
                    return True

            app_state["balance_history"].append(current_balance)
            if len(app_state["balance_history"]) > 100:
                app_state["balance_history"].pop(0)

        return False

    def detect_market_regime(self) -> str:
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
        current_balance = self.capital_manager.current_balance

        if current_balance <= 0:
            return 0

        # Riesgo más conservador para 20x
        risk_amount = current_balance * (config.RISK_PER_TRADE_PERCENT / 100)
        
        # Verificar balance mínimo realista
        if risk_amount < 5.0:  # Mínimo $5 de riesgo
            log.warning(f"💰 Balance muy bajo para operar: {current_balance:.2f} USDT")
            return 0

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
        
        position_size = position_size * leverage

        df = self.get_klines_for_symbol(symbol)
        if df is not None and not df.empty and len(df) > 20:
            returns = np.log(df['close'] / df['close'].shift(1))
            volatility = returns.std() * np.sqrt(365)

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

            max_position_size = (current_balance * leverage) / price
            position_size = min(position_size, max_position_size * 0.8)

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

                log.info(f"📊 Análisis de rendimiento para {symbol}: WR: {win_rate:.2%}, PF: {profit_factor:.2f}, Lev. Rec: {recommended_leverage}x, Vol: {atr:.2f}%, Dur: {avg_trade_duration:.1f}m")
                return asdict(metrics)
                
            except Exception as e:
                log.error(f"Error analizando rendimiento para {symbol}: {e}")
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
                            log.warning(f"⚠️ Símbolo problemático detectado: {symbol} con {loss_ratio:.2%} de trades perdedores")
            except Exception as e:
                log.error(f"Error optimizando estrategia basada en pérdidas: {e}")
            finally:
                db.close()

        execute_with_retry(optimize_operation, max_retries=2, retry_delay=1)

    def analyze_problematic_symbols(self):
        if not DB_ENABLED:
            return
            
        try:
            db = get_db_session_with_retry(max_retries=2)
            if not db:
                return
                
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
            
            for symbol_data in problematic_symbols:
                symbol = symbol_data['symbol']
                log.warning(f"⚠️ Símbolo problemático: {symbol}, Win Rate: {symbol_data['win_rate']:.2%}, PnL Total: {symbol_data['total_pnl']:.2f}")
                
                if symbol_data['win_rate'] < 0.3:
                    config.SYMBOL_SPECIFIC_SETTINGS[symbol] = {
                        'risk_multiplier': 0.3,
                        'max_leverage': 10,
                        'enabled': False
                    }
                    log.info(f"🔒 Deshabilitando trading para {symbol} debido a mal performance")
                else:
                    config.SYMBOL_SPECIFIC_SETTINGS[symbol] = {
                        'risk_multiplier': 0.5,
                        'max_leverage': 15,
                        'enabled': True
                    }
                    log.info(f"⚠️ Reduciendo riesgo para {symbol} debido a performance mediocre")
                    
        except Exception as e:
            log.error(f"Error analizando símbolos problemáticos: {e}")
        finally:
            if 'db' in locals():
                db.close()

    def generate_daily_report(self):
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

                log.info(f"📊 Reporte diario generado: {total_trades} trades, P&L Diario: {total_pnl:+.2f} USDT (20x)")

            except Exception as e:
                log.error(f"Error generando reporte diario: {e}")
            finally:
                db.close()

    def cleanup_invalid_symbols(self):
        valid_symbols = set(self.get_top_symbols())
        
        with state_lock:
            invalid_trailing = [s for s in app_state["trailing_stop_data"] if s not in valid_symbols]
            for symbol in invalid_trailing:
                del app_state["trailing_stop_data"][symbol]
                
            invalid_sltp = [s for s in app_state["sl_tp_data"] if s not in valid_symbols]
            for symbol in invalid_sltp:
                del app_state["sl_tp_data"][symbol]
                
            if invalid_trailing or invalid_sltp:
                log.info(f"🧹 Limpiados {len(invalid_trailing + invalid_sltp)} símbolos inválidos")

    def open_trade(self, symbol: str, side: str, last_candle):
        if not self.api.is_symbol_tradable(symbol):
            log.warning(f"⏭️ Símbolo {symbol} no está disponible para trading, omitiendo")
            return

        ticker = self.api._safe_api_call(self.api.client.futures_symbol_ticker, symbol=symbol)
        if ticker:
            bid_price = float(ticker.get('bidPrice', 0))
            ask_price = float(ticker.get('askPrice', 0))
            if bid_price > 0 and ask_price > 0:
                spread = (ask_price - bid_price) / bid_price * 100
                if spread > config.MAX_SPREAD_PERCENT:
                    log.warning(f"⏭️ Spread demasiado alto ({spread:.2f}%) en {symbol}, omitiendo trade")
                    return

        symbol_settings = config.SYMBOL_SPECIFIC_SETTINGS.get(symbol, {})
        if not symbol_settings.get('enabled', True):
            log.info(f"⏭️ Símbolo {symbol} deshabilitado en configuración")
            return

        price = float(last_candle['close'])
        filters = self.api.get_symbol_filters(symbol)

        if not filters:
            log.error(f"No filters for {symbol}")
            return

        min_notional = max(filters.get('minNotional', 5.0), config.MIN_NOTIONAL_OVERRIDE)
        min_qty = filters['minQty']

        min_position_size = min_notional / price
        if min_position_size < min_qty:
            min_position_size = min_qty

        if min_position_size * price > self.capital_manager.current_balance:
            log.info(f"⏭️ {symbol} requiere mínimo {min_position_size * price:.2f} USDT, capital insuficiente")
            return

        max_leverage = symbol_settings.get('max_leverage', config.LEVERAGE)
        current_leverage = min(config.LEVERAGE, max_leverage)

        if config.DRY_RUN:
            log.info(f"[DRY RUN] Would open {side} on {symbol}")
            return

        self.api.ensure_symbol_settings(symbol)

        quantity = self.calculate_position_size(symbol, price)

        if quantity <= 0:
            log.info(f"⏭️ Tamaño de posición inválido para {symbol}")
            return

        quantity = self.api.round_value(quantity, filters['stepSize'])

        if quantity < min_qty:
            log.info(f"⏭️ Cantidad {quantity} para {symbol} es menor que el mínimo {min_qty}")
            return

        notional_value = quantity * price
        if notional_value < min_notional:
            log.info(f"⏭️ Valor nocional {notional_value:.2f} para {symbol} es menor que el mínimo {min_notional:.2f}")
            return

        order_side = SIDE_BUY if side == 'LONG' else SIDE_SELL

        log.info(f"Attempting to place MARKET order for {side} {symbol} (Qty: {quantity}, Value: {notional_value:.2f} USDT, 20x)")

        order = self.api.place_order(symbol, order_side, FUTURE_ORDER_TYPE_MARKET, quantity)

        if order and order.get('orderId'):
            log.info(f"✅ MARKET ORDER CREATED: {side} {quantity} {symbol} (20x)")

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
            log.error(f"❌ Could not create market order for {symbol}. Response: {order}")

    def run(self):
        # Mostrar información de configuración
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        mode = "TESTNET" if testnet else "MAINNET REAL"
        
        log.info(f"🚀 STARTING TRADING BOT v12.0 WITH 20x LEVERAGE - {mode}")
        log.info(f"⚡ Configuración 20x: SL={config.STOP_LOSS_PERCENT}%, TP={config.TAKE_PROFIT_PERCENT}%")
        log.info(f"⚡ Risk per trade: {config.RISK_PER_TRADE_PERCENT}%, Max positions: {config.MAX_CONCURRENT_POS}")
        
        log.info(f"🔑 API Key presente: {bool(os.getenv('BINANCE_API_KEY'))}")
        log.info(f"🔑 API Secret presente: {bool(os.getenv('BINANCE_API_SECRET'))}")
        log.info(f"🌐 Modo: {mode}")
        log.info(f"🔧 Dry Run: {config.DRY_RUN}")
        log.info(f"🤖 Telegram: {'✅ CONFIGURADO' if self.telegram_notifier.enabled else '❌ NO CONFIGURADO'}")
        
        if DB_ENABLED:
            db_healthy = check_db_connection()
            log.info(f"🗄️ Conexión a base de datos: {'✅ SALUDABLE' if db_healthy else '❌ PROBLEMAS'}")
        
        # Notificar inicio por Telegram
        if self.telegram_notifier.enabled:
            self.telegram_notifier.notify_bot_started(config.LEVERAGE)
        
        self.start_time = time.time()

        self.capital_manager.update_balance(force=True)
        self.daily_starting_balance = self.capital_manager.current_balance
        self.daily_pnl = 0.0
        self.today = datetime.now().date()

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
            try:
                with state_lock:
                    if not app_state["running"]: 
                        break

                self.cycle_count += 1
                log.info(f"--- 🔄 Cycle {self.cycle_count} - Capital: {self.capital_manager.current_balance:.2f} USDT (20x) ---")

                if self.cycle_count % 50 == 0:
                    self.cleanup_invalid_symbols()

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
                    log.info("🔄 Nuevo día - Reiniciando métricas diarias (20x)")

                with state_lock:
                    app_state["connection_metrics"]["uptime"] = time.time() - self.start_time

                if self.cycle_count % 12 == 0:
                    self.market_regime = self.detect_market_regime()
                    with state_lock:
                        app_state["market_regime"] = self.market_regime
                    log.info(f"🏛️ Market Regime: {self.market_regime} (20x)")
                    
                    if self.telegram_notifier.enabled:
                        self.telegram_notifier.notify_market_regime(
                            self.market_regime,
                            "El bot ajustará su estrategia según el régimen de mercado detectado"
                        )

                account_info = self.api._safe_api_call(self.api.client.futures_account)
                if not account_info:
                    time.sleep(config.POLL_SEC)
                    continue

                with state_lock:
                    recent_trades = app_state["trades_history"][-config.MAX_CONSECUTIVE_LOSSES:]
                    consecutive_losses = sum(1 for trade in recent_trades if trade.get('pnl', 0) < 0)
                    
                    if consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
                        log.warning(f"⛔ {consecutive_losses} pérdidas consecutivas, pausando trading por 1 hora")
                        time.sleep(3600)
                        continue

                if self.daily_pnl < - (self.daily_starting_balance * config.MAX_DAILY_LOSS_PERCENT / 100):
                    log.warning(f"⛔ Límite de pérdida diaria alcanzado: {self.daily_pnl:.2f} USDT (20x)")
                    if self.telegram_notifier.enabled:
                        self.telegram_notifier.notify_warning(
                            f"Límite de pérdida diaria alcanzado: {self.daily_pnl:.2f} USDT",
                            "El bot se pausará hasta el próximo día de trading"
                        )
                    time.sleep(config.POLL_SEC)
                    continue

                low_balance = self.check_balance_risk(account_info)
                if low_balance: 
                    log.warning("⏸️ Pausando nuevas operaciones por balance bajo (20x)")
                    if self.telegram_notifier.enabled:
                        self.telegram_notifier.notify_warning(
                            "Balance bajo detectado",
                            "No se abrirán nuevas posiciones hasta que el balance mejore"
                        )

                open_positions = {p['symbol']: p for p in account_info['positions'] if float(p['positionAmt']) != 0}

                time.sleep(config.POLL_SEC)

            except Exception as e:
                log.error(f"❌ ERROR CRÍTICO en ciclo principal: {e}")
                import traceback
                log.error(f"Traceback: {traceback.format_exc()}")
                
                if self.telegram_notifier.enabled:
                    self.telegram_notifier.notify_error(
                        f"Error crítico: {str(e)}", 
                        "El bot se ha detenido por seguridad"
                    )
                
                # Intentar reinicio seguro
                self.safe_restart()
                break  # Salir del ciclo actual, safe_restart iniciará uno nuevo

# -------------------- RUTAS FLASK -------------------- #
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    with state_lock:
        return jsonify(app_state)

@app.route('/api/start', methods=['POST'])
def api_start():
    global bot_thread
    with state_lock:
        if app_state["running"]:
            return jsonify({"status": "already_running"})
        
        app_state["running"] = True
        app_state["status_message"] = "Ejecutándose"
        
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

@app.route('/api/stop', methods=['POST'])
def api_stop():
    with state_lock:
        app_state["running"] = False
        app_state["status_message"] = "Detenido"
    return jsonify({"status": "stopped"})

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        new_config = request.json
        with state_lock:
            for key, value in new_config.items():
                if hasattr(config, key):
                    # Convertir al tipo correcto
                    current_value = getattr(config, key)
                    if isinstance(current_value, bool):
                        setattr(config, key, bool(value))
                    elif isinstance(current_value, int):
                        setattr(config, key, int(value))
                    elif isinstance(current_value, float):
                        setattr(config, key, float(value))
                    else:
                        setattr(config, key, value)
            app_state["config"] = asdict(config)
        return jsonify({"status": "updated"})
    else:
        with state_lock:
            return jsonify(app_state["config"])

@app.route('/api/history')
def api_history():
    """Obtener historial de trades"""
    with state_lock:
        return jsonify({
            "trades": app_state["trades_history"],
            "balance_history": app_state["balance_history"]
        })

@app.route('/api/logs')
def api_logs():
    """Obtener logs históricos"""
    try:
        log_file_path = f'logs/{config.LOG_FILE}'
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r', encoding='utf-8') as f:
                logs = f.readlines()[-100:]  # Últimas 100 líneas
            return jsonify({'logs': logs})
        return jsonify({'logs': []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    """Limpiar archivo de logs"""
    try:
        log_file_path = f'logs/{config.LOG_FILE}'
        if os.path.exists(log_file_path):
            open(log_file_path, 'w').close()
        
        socketio.emit('log_update', {
            'message': 'Logs limpiados manualmente',
            'level': 'info',
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify({'status': 'success', 'message': 'Logs limpiados'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/export')
def api_export_logs():
    """Exportar logs como archivo"""
    try:
        log_file_path = f'logs/{config.LOG_FILE}'
        if os.path.exists(log_file_path):
            return send_file(log_file_path, as_attachment=True, download_name='trading_bot_logs.txt')
        return jsonify({'error': 'Archivo de logs no encontrado'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/positions')
def api_positions():
    """Obtener posiciones actuales"""
    with state_lock:
        return jsonify(app_state["open_positions"])

@app.route('/api/performance')
def api_performance():
    """Obtener métricas de performance"""
    with state_lock:
        return jsonify(app_state["performance_stats"])

@app.route('/api/balance/history')
def api_balance_history():
    """Obtener historial de balance"""
    with state_lock:
        return jsonify(app_state["balance_history"])

# -------------------- EMISIÓN PERIÓDICA DE ESTADO -------------------- #

def emit_periodic_updates():
    """Emitir actualizaciones periódicas del estado"""
    while True:
        try:
            with state_lock:
                # Emitir estado completo
                socketio.emit('status_update', app_state)
                
                # Emitir P&L actualizado
                pnl_data = {}
                for symbol, position in app_state["open_positions"].items():
                    unrealized_pnl = float(position.get('unrealizedProfit', 0))
                    pnl_data[symbol] = unrealized_pnl
                
                if pnl_data:
                    socketio.emit('pnl_update', pnl_data)
            
            time.sleep(3)  # Emitir cada 3 segundos
            
        except Exception as e:
            log.error(f"Error emitiendo actualizaciones: {e}")
            time.sleep(5)

# -------------------- INICIO AUTOMÁTICO DEL BOT -------------------- #
def auto_start_bot():
    """Iniciar el bot automáticamente al inicio de la aplicación"""
    global bot_thread
    
    # Verificar si el bot debe iniciarse automáticamente
    auto_start = os.getenv('AUTO_START_BOT', 'false').lower() == 'true'
    
    if auto_start:
        log.info("🚀 INICIO AUTOMÁTICO CONFIGURADO - Iniciando bot...")
        
        # Pequeña pausa para asegurar que todo esté inicializado
        time.sleep(2)
        
        with state_lock:
            if not app_state["running"]:
                app_state["running"] = True
                app_state["status_message"] = "Ejecutándose (Inicio Automático)"
        
        def run_bot():
            try:
                log.info("🤖 CREANDO INSTANCIA DEL BOT DE TRADING...")
                bot = TradingBot()
                log.info("🎯 INICIANDO CICLO PRINCIPAL DEL BOT...")
                bot.run()
            except Exception as e:
                log.error(f"❌ Error en el bot (inicio automático): {e}")
                import traceback
                log.error(f"Traceback: {traceback.format_exc()}")
                with state_lock:
                    app_state["running"] = False
                    app_state["status_message"] = f"Error: {str(e)}"
        
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        log.info("✅ Bot iniciado automáticamente")
    else:
        log.info("⏸️ Inicio automático desactivado - Use la interfaz web para iniciar el bot")

# -------------------- EJECUCIÓN PRINCIPAL -------------------- #
if __name__ == '__main__':
    # Configurar logging en tiempo real
    setup_realtime_logging()
    
    # Iniciar hilo de actualizaciones
    update_thread = threading.Thread(target=emit_periodic_updates, daemon=True)
    update_thread.start()
    
    log.info("🚀 Iniciando aplicación Flask con Socket.IO...")
    log.info("📊 Sistema de logs en tiempo real inicializado")
    
    # Iniciar bot automáticamente si está configurado
    auto_start_bot()
    
    # Mostrar estado inicial
    with state_lock:
        status = "ACTIVO" if app_state["running"] else "INACTIVO"
        log.info(f"🔧 Estado del bot: {status}")
        log.info(f"💰 Balance inicial: {app_state['balance']:.2f} USDT")
    
    # Iniciar servidor Flask
    try:
        log.info("🌐 Servidor web iniciando en http://0.0.0.0:5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    except Exception as e:
        log.error(f"❌ Error al iniciar el servidor: {e}")