#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════
    BINANCE FUTURES BOT V13.0 - OPTIMIZADO Y MEJORADO
═══════════════════════════════════════════════════════════════════
Bot de trading automatizado con:
- Sistema de señales multi-confirmación (4/8 puntos)
- SL/TP dinámicos basados en ATR
- Trailing stop automático (0.5% activación)
- Gestión de capital optimizada (2% por trade)
- Dashboard web en tiempo real
- Notificaciones Telegram
- Logs profesionales detallados
- Sistema de health check
- Backtesting integrado
- Pyramiding inteligente
- Analytics avanzados

Autor: gregorbc@gmail.com
Versión: 13.0 (Mejorada)
Fecha: 2024
═══════════════════════════════════════════════════════════════════
"""

import os
import time
import math
import logging
import threading
import requests
import pandas as pd
import numpy as np
import psutil
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import warnings

# Suprimir warnings
warnings.filterwarnings("ignore")

# Importaciones de terceros
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, FUTURE_ORDER_TYPE_MARKET
from binance.exceptions import BinanceAPIException
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS

# ═══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE FLASK
# ═══════════════════════════════════════════════════════════════════

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bot-trading-2024')
CORS(app)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# ═══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN PRINCIPAL MEJORADA
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CONFIG:
    """Configuración optimizada del bot"""
    
    # Trading básico
    LEVERAGE: int = 20
    MAX_CONCURRENT_POS: int = 5
    RISK_PER_TRADE_PERCENT: float = 2.0
    
    # Señales
    MIN_SIGNAL_SCORE: int = 4
    MIN_SIGNAL_STRENGTH: float = 0.10
    
    # Stop Loss y Take Profit
    USE_DYNAMIC_SL_TP: bool = True
    
    # Trailing Stop
    TRAILING_STOP_ENABLED: bool = True
    TRAILING_STOP_ACTIVATION: float = 0.5
    TRAILING_STOP_DISTANCE: float = 0.3
    
    # Indicadores
    FAST_EMA: int = 8
    SLOW_EMA: int = 21
    EMA_TREND: int = 50
    RSI_PERIOD: int = 14
    ATR_PERIOD: int = 14
    
    # Filtros
    MIN_24H_VOLUME: float = 10_000_000
    MIN_BALANCE_THRESHOLD: float = 5.0
    
    # Símbolos prioritarios
    PRIORITY_SYMBOLS: tuple = (
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT',
        'XRPUSDT', 'DOTUSDT', 'MATICUSDT', 'AVAXUSDT', 'LINKUSDT'
    )
    
    # Sistema
    TIMEFRAME: str = "5m"
    CANDLES_LIMIT: int = 100
    POLL_SEC: float = 10.0
    DRY_RUN: bool = False
    
    # Nuevas configuraciones avanzadas
    TRADING_HOURS: str = "00-24"  # 24/7
    MAX_DRAWDOWN_PCT: float = 10.0
    AUTO_RISK_ADJUSTMENT: bool = True
    ENABLE_PYRAMIDING: bool = True
    MAX_PYRAMID_LEVELS: int = 2
    
    # Logging
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE: str = "bot_v13_improved.log"

config = CONFIG()

# Cargar variables de entorno
load_dotenv()
if os.getenv("LEVERAGE"):
    config.LEVERAGE = int(os.getenv("LEVERAGE"))
if os.getenv("RISK_PER_TRADE_PERCENT"):
    config.RISK_PER_TRADE_PERCENT = float(os.getenv("RISK_PER_TRADE_PERCENT"))
if os.getenv("DRY_RUN"):
    config.DRY_RUN = os.getenv("DRY_RUN").lower() == "true"

# ═══════════════════════════════════════════════════════════════════
# LOGGING MEJORADO
# ═══════════════════════════════════════════════════════════════════

class SocketIOHandler(logging.Handler):
    """Handler para emitir logs via Socket.IO"""
    def emit(self, record):
        try:
            log_entry = self.format(record)
            level = record.levelname.lower()
            socketio.emit('log_update', {'message': log_entry, 'level': level})
        except:
            pass

# Configurar logger
log = logging.getLogger("BinanceFuturesBot")
log.setLevel(getattr(logging, config.LOG_LEVEL))

if not log.handlers:
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    os.makedirs('logs', exist_ok=True)
    file_handler = logging.FileHandler(f'logs/{config.LOG_FILE}', encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    socket_handler = SocketIOHandler()
    socket_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    log.addHandler(file_handler)
    log.addHandler(socket_handler)
    log.addHandler(console_handler)

# Silenciar otros loggers
for logger_name in ['binance', 'engineio', 'socketio', 'werkzeug', 'urllib3']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# ═══════════════════════════════════════════════════════════════════
# MANEJADOR AVANZADO DE ERRORES
# ═══════════════════════════════════════════════════════════════════

class AdvancedErrorHandler:
    """Manejo avanzado de errores con circuit breaker"""
    
    def __init__(self):
        self.error_count = 0
        self.last_error_time = 0
        self.circuit_open = False
        
    def should_retry(self, error):
        """Decidir si reintentar basado en el tipo de error"""
        if isinstance(error, BinanceAPIException):
            if error.code in [-1001, -1003, -1006, -1007]:  # Timeouts, conexión
                return True
            if error.code in [-1013, -2010, -2011]:  # Filtros, fondos insuficientes
                return False
        return True
    
    def record_error(self):
        """Registrar error y posiblemente abrir circuito"""
        self.error_count += 1
        self.last_error_time = time.time()
        
        if self.error_count > 5:
            self.circuit_open = True
            log.warning("🚨 Circuit breaker activado - pausando operaciones")
    
    def record_success(self):
        """Resetear contadores en éxito"""
        self.error_count = 0
        self.circuit_open = False

# ═══════════════════════════════════════════════════════════════════
# MONITOR DE SALUD (CORREGIDO)
# ═══════════════════════════════════════════════════════════════════

class HealthMonitor:
    """Monitor de salud del sistema"""
    
    def __init__(self):
        self.metrics = {
            'api_calls': 0,
            'errors': 0,
            'positions_opened': 0,
            'positions_closed': 0,
            'signals_detected': 0,
            'trades_won': 0,
            'trades_lost': 0
        }
        self.start_time = time.time()
    
    def record_metric(self, metric_name, value=1):
        """Registrar métrica"""
        if metric_name in self.metrics:
            self.metrics[metric_name] += value
    
    def get_uptime(self):
        """Obtener tiempo de actividad"""
        return time.time() - self.start_time
    
    def get_health_status(self):
        """Obtener estado de salud (MEJORADO)"""
        try:
            uptime = self.get_uptime()
            
            # Métricas con protección completa
            api_calls = max(self.metrics['api_calls'], 1)
            errors = self.metrics['errors']
            error_rate = min(errors / api_calls, 1.0)  # Máximo 100%
            
            total_trades = self.metrics['trades_won'] + self.metrics['trades_lost']
            win_rate = self.metrics['trades_won'] / max(total_trades, 1)
            
            signals_per_hour = self.metrics['signals_detected'] / max(uptime / 3600, 0.001)
            
            return {
                'uptime': uptime,
                'error_rate': error_rate,
                'win_rate': win_rate,
                'signals_per_hour': signals_per_hour,
                'metrics': self.metrics.copy()
            }
        except Exception as e:
            log.error(f"Error calculando health status: {e}")
            return {
                'uptime': 0,
                'error_rate': 1.0,
                'win_rate': 0.0,
                'signals_per_hour': 0.0,
                'metrics': self.metrics.copy()
            }

# ═══════════════════════════════════════════════════════════════════
# SISTEMA DE BACKTESTING (CORREGIDO)
# ═══════════════════════════════════════════════════════════════════

class Backtester:
    """Sistema de backtesting para optimizar parámetros"""
    
    def __init__(self, api):
        self.api = api
    
    def run_backtest(self, symbol, days=30, params=None):
        """Ejecutar backtest con parámetros específicos"""
        try:
            # Obtener datos históricos
            end_time = int(time.time() * 1000)
            start_time = end_time - (days * 24 * 60 * 60 * 1000)
            
            klines = self.api._safe_api_call(
                self.api.client.futures_klines,
                symbol=symbol,
                interval=config.TIMEFRAME,
                startTime=start_time,
                endTime=end_time,
                limit=1000
            )
            
            if not klines:
                return {"error": "No se pudieron obtener datos históricos"}
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy', 'taker_quote', 'ignore'
            ])
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Simular trading
            results = self._simulate_trading(df, params or {})
            return results
            
        except Exception as e:
            log.error(f"Error en backtest: {e}")
            return {"error": str(e)}
    
    def _simulate_trading(self, df, params):
        """Simular estrategia de trading (CORREGIDO)"""
        try:
            detector = SignalDetector()
            df_indicators = detector.calculate_indicators(df.copy())
            
            if df_indicators is None or len(df_indicators) < 50:
                return {"error": "Datos insuficientes para backtesting"}
            
            # Simulación simple
            balance = 1000  # Balance inicial simulado
            positions = []
            trades = []
            
            for i in range(50, len(df_indicators)):
                current_data = df_indicators.iloc[:i+1]
                signal = detector.detect_signal(current_data, "SIMULATION")
                
                if signal:
                    # Lógica de trading simulada
                    price = df_indicators.iloc[i]['close']
                    if signal['type'] == 'LONG' and not positions:
                        entry_price = price
                        positions.append({'side': 'LONG', 'entry': entry_price})
                        trades.append({'action': 'BUY', 'price': entry_price, 'timestamp': df_indicators.iloc[i]['timestamp']})
                    elif signal['type'] == 'SHORT' and not positions:
                        entry_price = price
                        positions.append({'side': 'SHORT', 'entry': entry_price})
                        trades.append({'action': 'SELL', 'price': entry_price, 'timestamp': df_indicators.iloc[i]['timestamp']})
                    
                    # Cerrar posiciones (lógica simple)
                    if positions:
                        pos = positions[0]
                        if pos['side'] == 'LONG' and price > pos['entry'] * 1.02:
                            pnl = (price - pos['entry']) / pos['entry'] * 100
                            trades.append({'action': 'SELL', 'price': price, 'pnl': pnl})
                            positions = []
                        elif pos['side'] == 'SHORT' and price < pos['entry'] * 0.98:
                            pnl = (pos['entry'] - price) / pos['entry'] * 100
                            trades.append({'action': 'BUY', 'price': price, 'pnl': pnl})
                            positions = []
            
            # Calcular métricas (CON PROTECCIÓN CONTRA DIVISIÓN POR CERO)
            closed_trades = [t for t in trades if 'pnl' in t]
            winning_trades = [t for t in closed_trades if t['pnl'] > 0]
            losing_trades = [t for t in closed_trades if t['pnl'] <= 0]
            
            total_trades = len(closed_trades)
            win_rate = len(winning_trades) / max(total_trades, 1) * 100
            
            avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
            avg_loss = np.mean([t['pnl'] for t in losing_trades]) if losing_trades else 0
            
            total_pnl = sum(t.get('pnl', 0) for t in closed_trades)
            
            # Calcular profit factor con protección
            total_wins = sum(t['pnl'] for t in winning_trades) if winning_trades else 0
            total_losses = abs(sum(t['pnl'] for t in losing_trades)) if losing_trades else 0
            profit_factor = total_wins / max(total_losses, 1)
            
            return {
                'total_trades': total_trades,
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_loss': total_pnl,
                'profit_factor': profit_factor,
                'max_drawdown': self._calculate_max_drawdown([t.get('pnl', 0) for t in closed_trades]),
                'sharpe_ratio': self._calculate_sharpe_ratio([t.get('pnl', 0) for t in closed_trades])
            }
        
        except Exception as e:
            log.error(f"Error en simulación de trading: {e}")
            return {"error": f"Error en simulación: {str(e)}"}
    
    def _calculate_max_drawdown(self, pnl_series):
        """Calcular máxima pérdida acumulada (CORREGIDO)"""
        if not pnl_series or len(pnl_series) == 0:
            return 0
        
        try:
            cumulative = np.cumsum(pnl_series)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / np.maximum(running_max, 1) * 100
            return np.min(drawdown) if len(drawdown) > 0 else 0
        except:
            return 0
    
    def _calculate_sharpe_ratio(self, pnl_series):
        """Calcular ratio Sharpe (CORREGIDO)"""
        if not pnl_series or len(pnl_series) < 2:
            return 0
        
        try:
            returns = np.array(pnl_series)
            if np.std(returns) == 0:
                return 0
            return (np.mean(returns) / np.std(returns)) * np.sqrt(365)  # Anualizado
        except:
            return 0

# ═══════════════════════════════════════════════════════════════════
# ANALYTICS AVANZADOS (CORREGIDO)
# ═══════════════════════════════════════════════════════════════════

class AnalyticsEngine:
    """Motor de analytics avanzado"""
    
    def __init__(self):
        self.trade_history = []
        self.performance_metrics = {}
    
    def record_trade(self, trade_data):
        """Registrar trade para analytics"""
        self.trade_history.append({
            **trade_data,
            'timestamp': datetime.now().isoformat()
        })
        
        # Mantener sólo últimos 1000 trades
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-1000:]
    
    def calculate_metrics(self):
        """Calcular métricas de performance (MEJORADO)"""
        try:
            if not self.trade_history:
                return {}
            
            df = pd.DataFrame(self.trade_history)
            if df.empty or 'pnl' not in df.columns:
                return {}
                
            # Convertir y limpiar datos
            df['pnl'] = pd.to_numeric(df['pnl'], errors='coerce')
            df = df.dropna(subset=['pnl'])
            
            if df.empty:
                return {}
                
            # Cálculos seguros
            wins = df[df['pnl'] > 0]
            losses = df[df['pnl'] < 0]
            
            total_trades = len(df)
            win_rate = len(wins) / max(total_trades, 1) * 100
            
            avg_win = wins['pnl'].mean() if not wins.empty else 0
            avg_loss = losses['pnl'].mean() if not losses.empty else 0
            
            total_wins = wins['pnl'].sum() if not wins.empty else 0
            total_losses = abs(losses['pnl'].sum()) if not losses.empty else 0
            
            profit_factor = total_wins / max(total_losses, 0.001)  # Evitar división por cero
            
            return {
                'total_trades': total_trades,
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'profit_factor': profit_factor,
                'max_drawdown': self._calculate_max_drawdown(df['pnl']),
                'sharpe_ratio': self._calculate_sharpe_ratio(df['pnl']),
                'total_pnl': df['pnl'].sum()
            }
        
        except Exception as e:
            log.error(f"Error calculando métricas: {e}")
            return {}
    
    def _calculate_max_drawdown(self, pnl_series):
        """Calcular máxima pérdida acumulada (CORREGIDO)"""
        try:
            if pnl_series.empty:
                return 0
                
            cumulative = pnl_series.cumsum()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max)
            return drawdown.min() if not drawdown.empty else 0
        except:
            return 0
    
    def _calculate_sharpe_ratio(self, pnl_series):
        """Calcular ratio Sharpe (CORREGIDO)"""
        try:
            if pnl_series.empty or len(pnl_series) < 2:
                return 0
                
            if pnl_series.std() == 0:
                return 0
                
            return (pnl_series.mean() / pnl_series.std()) * np.sqrt(365)
        except:
            return 0

# ═══════════════════════════════════════════════════════════════════
# ESTADO GLOBAL MEJORADO (CORREGIDO)
# ═══════════════════════════════════════════════════════════════════

health_monitor = HealthMonitor()

app_state = {
    "running": False,
    "status_message": "Detenido",
    "open_positions": {},
    "config": asdict(config),
    "performance_stats": {
        "realized_pnl": 0.0,
        "trades_count": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0
    },
    "balance": 0.0,
    "trades_history": [],
    "health_metrics": {
        'uptime': 0,
        'error_rate': 0,
        'win_rate': 0,
        'signals_per_hour': 0,
        'metrics': health_monitor.metrics.copy()
    },  # Estado inicial seguro
    "market_condition": "NORMAL",
    "advanced_features": True
}
state_lock = threading.Lock()
bot_thread = None

# ═══════════════════════════════════════════════════════════════════
# CLIENTE BINANCE (MEJORADO)
# ═══════════════════════════════════════════════════════════════════

class BinanceFutures:
    """Cliente para Binance Futures API con mejoras"""
    
    def __init__(self):
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError("❌ API keys no configuradas en .env")

        self.client = Client(api_key, api_secret, testnet=testnet)
        mode = "TESTNET" if testnet else "MAINNET"
        log.info(f"🔧 Conectado a Binance Futures {mode}")
        
        try:
            self.exchange_info = self.client.futures_exchange_info()
            log.info("✅ Exchange info cargada")
        except Exception as e:
            log.error(f"❌ Error conectando: {e}")
            raise

    def _safe_api_call(self, func, *args, **kwargs):
        """Llamada segura con reintentos"""
        health_monitor.record_metric('api_calls')
        for attempt in range(3):
            try:
                time.sleep(0.5 * attempt)
                result = func(*args, **kwargs)
                return result
            except BinanceAPIException as e:
                health_monitor.record_metric('errors')
                if e.code in [-4131, -1122, -2011, -1013]:
                    log.warning(f"⚠️ Error API {e.code}: {e.message}")
                    return None
                if attempt == 2:
                    log.error(f"❌ Error final: {e.message}")
            except Exception as e:
                health_monitor.record_metric('errors')
                if attempt == 2:
                    log.error(f"❌ Error: {e}")
        return None

    def ensure_symbol_settings(self, symbol: str):
        """Configurar leverage y margen"""
        try:
            self._safe_api_call(
                self.client.futures_change_leverage,
                symbol=symbol,
                leverage=config.LEVERAGE
            )
            log.info(f"✅ Leverage {config.LEVERAGE}x para {symbol}")
        except Exception as e:
            log.warning(f"⚠️ Error config {symbol}: {e}")

    def get_symbol_filters(self, symbol: str) -> Optional[Dict]:
        """Obtener filtros del símbolo"""
        try:
            s_info = next((s for s in self.exchange_info['symbols'] 
                          if s['symbol'] == symbol), None)
            if not s_info:
                return None
                
            filters = {f['filterType']: f for f in s_info['filters']}
            return {
                "stepSize": float(filters['LOT_SIZE']['stepSize']),
                "minQty": float(filters['LOT_SIZE']['minQty']),
                "tickSize": float(filters['PRICE_FILTER']['tickSize']),
                "minNotional": float(filters.get('MIN_NOTIONAL', {}).get('notional', 5.0))
            }
        except Exception as e:
            log.error(f"Error obteniendo filtros {symbol}: {e}")
            return None

    def place_order(self, symbol: str, side: str, quantity: float) -> Optional[Dict]:
        """Colocar orden de mercado"""
        if config.DRY_RUN:
            log.info(f"[DRY_RUN] Orden: {side} {quantity} {symbol}")
            return {'mock': True, 'orderId': int(time.time() * 1000)}

        return self._safe_api_call(
            self.client.futures_create_order,
            symbol=symbol,
            side=side,
            type=FUTURE_ORDER_TYPE_MARKET,
            quantity=quantity
        )

    def close_position(self, symbol: str, position_amt: float) -> Optional[Dict]:
        """Cerrar posición"""
        side = SIDE_SELL if position_amt > 0 else SIDE_BUY
        return self.place_order(symbol, side, abs(position_amt))

    @staticmethod
    def round_value(value: float, step: float) -> float:
        """Redondear según step size"""
        if step == 0:
            return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)

# ═══════════════════════════════════════════════════════════════════
# GESTOR DE CAPITAL MEJORADO
# ═══════════════════════════════════════════════════════════════════

class CapitalManager:
    """Gestor de capital mejorado"""
    
    def __init__(self, api):
        self.api = api
        self.current_balance = 0.0
        self.initial_balance = 0.0
        self.last_update = 0
        self.daily_pnl = 0.0
        self.last_reset = time.time()

    def get_real_balance(self) -> float:
        """Obtener balance real"""
        try:
            account = self.api._safe_api_call(self.api.client.futures_account)
            if account:
                for asset in account.get('assets', []):
                    if asset.get('asset') == 'USDT':
                        return float(asset.get('walletBalance', 0))
            return 0.0
        except Exception as e:
            log.error(f"Error obteniendo balance: {e}")
            return 0.0

    def update_balance(self, force=False) -> bool:
        """Actualizar balance"""
        if force or (time.time() - self.last_update > 120):
            new_balance = self.get_real_balance()
            if new_balance > 0:
                if self.current_balance == 0:
                    self.initial_balance = new_balance
                    log.info(f"💰 Capital inicial: {new_balance:.2f} USDT")
                
                # Reset diario de PnL
                if time.time() - self.last_reset > 86400:  # 24 horas
                    self.daily_pnl = 0
                    self.last_reset = time.time()
                
                self.current_balance = new_balance
                self.last_update = time.time()
                
                with state_lock:
                    app_state["balance"] = self.current_balance
                
                return True
        return False

    def get_drawdown(self) -> float:
        """Calcular drawdown actual"""
        if self.initial_balance == 0:
            return 0.0
        return ((self.initial_balance - self.current_balance) / self.initial_balance) * 100

# ═══════════════════════════════════════════════════════════════════
# NOTIFICADOR TELEGRAM MEJORADO
# ═══════════════════════════════════════════════════════════════════

class TelegramNotifier:
    """Notificaciones Telegram mejoradas"""
    
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)
        
        if self.enabled:
            log.info(f"✅ Telegram configurado")

    def send_message(self, message: str) -> bool:
        """Enviar mensaje"""
        if not self.enabled:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }, timeout=10)
            return True
        except:
            return False

    def notify_trade_opened(self, symbol, side, quantity, price, balance, score):
        """Notificar apertura mejorada"""
        emoji = "🟢" if side == "LONG" else "🔴"
        msg = f"""{emoji} <b>TRADE ABIERTO</b>

📈 {symbol} {side}
💰 Precio: ${price:.6f}
📦 Cantidad: {quantity:.6f}
⭐ Score: {score}/8
🦐 Balance: ${balance:.2f}"""
        return self.send_message(msg)

    def notify_trade_closed(self, symbol, pnl, reason, balance, max_pnl=None):
        """Notificar cierre mejorado"""
        emoji = "🟢" if pnl >= 0 else "🔴"
        max_info = f"🎯 Máximo: {max_pnl:+.2f}%\n" if max_pnl else ""
        msg = f"""{emoji} <b>TRADE CERRADO</b>

📈 {symbol}
💵 P&L: ${pnl:+.2f}
{max_info}📋 Razón: {reason}
🦐 Balance: ${balance:.2f}"""
        return self.send_message(msg)

    def notify_system_alert(self, message):
        """Notificar alerta del sistema"""
        msg = f"🚨 <b>ALERTA DEL SISTEMA</b>\n\n{message}"
        return self.send_message(msg)

# ═══════════════════════════════════════════════════════════════════
# DETECTOR DE SEÑALES
# ═══════════════════════════════════════════════════════════════════

class SignalDetector:
    """Detector de señales con multi-confirmación"""
    
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Calcular indicadores"""
        try:
            # EMAs
            df['ema_8'] = df['close'].ewm(span=8, adjust=False).mean()
            df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
            df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
            
            # RSI
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).ewm(span=14, adjust=False).mean()
            loss = -delta.where(delta < 0, 0).ewm(span=14, adjust=False).mean()
            rs = gain / loss.replace(0, np.nan)
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # MACD
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']
            
            # ATR
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            df['atr'] = true_range.rolling(14).mean()
            
            # Volumen
            df['volume_ma'] = df['volume'].rolling(20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma'].replace(0, np.nan)
            
            # Momentum
            df['momentum'] = df['close'] - df['close'].shift(10)
            
            return df
        except Exception as e:
            log.error(f"Error calculando indicadores: {e}")
            return df
    
    @staticmethod
    def detect_signal(df: pd.DataFrame, symbol: str) -> Optional[Dict]:
        """Detectar señal de trading"""
        
        if len(df) < 50:
            return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Verificar datos válidos
        required = ['close', 'ema_8', 'ema_21', 'rsi', 'macd', 'atr']
        if any(pd.isna(last[field]) for field in required):
            return None
        
        # LONG
        long_score = 0
        long_reasons = []
        
        if last['ema_8'] > last['ema_21'] and prev['ema_8'] <= prev['ema_21']:
            long_score += 2
            long_reasons.append("✓ Cruce EMA Alcista")
        if last['close'] > last['ema_50']:
            long_score += 1
            long_reasons.append("✓ Tendencia Alcista")
        if 30 < last['rsi'] < 68:
            long_score += 1
            long_reasons.append(f"✓ RSI {last['rsi']:.1f}")
        if last['macd'] > last['macd_signal']:
            long_score += 1
            long_reasons.append("✓ MACD Alcista")
        if last['macd_hist'] > prev['macd_hist']:
            long_score += 1
            long_reasons.append("✓ MACD Momentum")
        if last['volume_ratio'] > 1.1:
            long_score += 1
            long_reasons.append("✓ Volumen Alto")
        if last['momentum'] > 0:
            long_score += 1
            long_reasons.append("✓ Momentum+")
        
        # SHORT
        short_score = 0
        short_reasons = []
        
        if last['ema_8'] < last['ema_21'] and prev['ema_8'] >= prev['ema_21']:
            short_score += 2
            short_reasons.append("✓ Cruce EMA Bajista")
        if last['close'] < last['ema_50']:
            short_score += 1
            short_reasons.append("✓ Tendencia Bajista")
        if 32 < last['rsi'] < 70:
            short_score += 1
            short_reasons.append(f"✓ RSI {last['rsi']:.1f}")
        if last['macd'] < last['macd_signal']:
            short_score += 1
            short_reasons.append("✓ MACD Bajista")
        if last['macd_hist'] < prev['macd_hist']:
            short_score += 1
            short_reasons.append("✓ MACD Momentum")
        if last['volume_ratio'] > 1.1:
            short_score += 1
            short_reasons.append("✓ Volumen Alto")
        if last['momentum'] < 0:
            short_score += 1
            short_reasons.append("✓ Momentum-")
        
        # Decidir
        if long_score >= config.MIN_SIGNAL_SCORE:
            health_monitor.record_metric('signals_detected')
            return {
                'type': 'LONG',
                'strength': min(long_score / 8, 0.95),
                'reasons': long_reasons,
                'price': last['close'],
                'atr': last['atr'],
                'rsi': last['rsi'],
                'score': long_score
            }
        elif short_score >= config.MIN_SIGNAL_SCORE:
            health_monitor.record_metric('signals_detected')
            return {
                'type': 'SHORT',
                'strength': min(short_score / 8, 0.95),
                'reasons': short_reasons,
                'price': last['close'],
                'atr': last['atr'],
                'rsi': last['rsi'],
                'score': short_score
            }
        
        return None

# ═══════════════════════════════════════════════════════════════════
# GESTOR DE RIESGO MEJORADO
# ═══════════════════════════════════════════════════════════════════

class RiskManager:
    """Gestor de riesgo dinámico mejorado"""
    
    @staticmethod
    def calculate_sl_tp(signal: Dict, price: float) -> Tuple[float, float]:
        """Calcular SL y TP dinámicos"""
        atr = signal.get('atr', price * 0.01)
        strength = signal.get('strength', 0.5)
        
        # Ajustar según condiciones de mercado
        market_condition = app_state.get("market_condition", "NORMAL")
        if market_condition == "HIGH_VOLATILITY":
            sl_mult = 2.0 - (strength * 0.8)
            tp_mult = 2.5 + (strength * 1.5)
        elif market_condition == "LOW_VOLATILITY":
            sl_mult = 1.5 - (strength * 0.4)
            tp_mult = 1.8 + (strength * 1.0)
        else:
            sl_mult = 1.8 - (strength * 0.6)
            tp_mult = 2.2 + (strength * 1.3)
        
        sl_dist = atr * sl_mult
        tp_dist = atr * tp_mult
        
        if signal['type'] == "LONG":
            return price - sl_dist, price + tp_dist
        else:
            return price + sl_dist, price - tp_dist

# ═══════════════════════════════════════════════════════════════════
# TRAILING STOP MEJORADO
# ═══════════════════════════════════════════════════════════════════

class TrailingStop:
    """Trailing stop automático mejorado"""
    
    def __init__(self):
        self.data = {}
    
    def update(self, symbol: str, price: float, side: str, entry: float) -> Optional[Dict]:
        """Actualizar trailing stop mejorado"""
        
        # Calcular PnL%
        if side == "LONG":
            pnl_pct = ((price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - price) / entry) * 100
        
        # Activar solo con ganancia
        if pnl_pct < config.TRAILING_STOP_ACTIVATION:
            return None
        
        # Inicializar
        if symbol not in self.data:
            self.data[symbol] = {'max_price': price, 'max_pnl': pnl_pct}
            log.info(f"🎯 Trailing Stop ACTIVADO: {symbol} @ {pnl_pct:.2f}%")
        
        data = self.data[symbol]
        
        # Actualizar máximo
        if side == "LONG":
            if price > data['max_price']:
                data['max_price'] = price
                data['max_pnl'] = pnl_pct
            
            # Trailing stop adaptativo
            current_trailing = config.TRAILING_STOP_DISTANCE
            if pnl_pct > 2.0:  # Reducir trailing en ganancias altas
                current_trailing = max(0.1, config.TRAILING_STOP_DISTANCE * 0.7)
                
            stop = data['max_price'] * (1 - current_trailing / 100)
            if price <= stop:
                return {'should_close': True, 'reason': 'Trailing Stop', 
                       'max_pnl': data['max_pnl']}
        else:
            if price < data['max_price']:
                data['max_price'] = price
                data['max_pnl'] = pnl_pct
            
            current_trailing = config.TRAILING_STOP_DISTANCE
            if pnl_pct > 2.0:
                current_trailing = max(0.1, config.TRAILING_STOP_DISTANCE * 0.7)
                
            stop = data['max_price'] * (1 + current_trailing / 100)
            if price >= stop:
                return {'should_close': True, 'reason': 'Trailing Stop',
                       'max_pnl': data['max_pnl']}
        
        return None
    
    def clear(self, symbol: str):
        """Limpiar datos"""
        self.data.pop(symbol, None)

# ═══════════════════════════════════════════════════════════════════
# GESTOR DE POSICIONES AVANZADO
# ═══════════════════════════════════════════════════════════════════

class AdvancedPositionManager:
    """Gestor de posiciones avanzado con pyramiding"""
    
    def __init__(self, api, capital_mgr):
        self.api = api
        self.capital = capital_mgr
        self.trailing = TrailingStop()
        self.telegram = TelegramNotifier()
        self.positions = {}
        self.entry_levels = {}  # Para pyramiding
        self.analytics = AnalyticsEngine()

    def can_add_to_position(self, symbol, signal):
        """Verificar si se puede añadir a posición existente"""
        if symbol not in self.positions:
            return False
        
        pos = self.positions[symbol]
        current_price = signal['price']
        
        # Verificar dirección y condiciones para añadir
        if pos['side'] != signal['type']:
            return False
        
        # Verificar niveles de pyramiding
        current_levels = self.entry_levels.get(symbol, 0)
        if current_levels >= config.MAX_PYRAMID_LEVELS:
            return False
        
        # Lógica de pyramiding (añadir en retrocesos)
        if pos['side'] == 'LONG' and current_price < pos['entry'] * 0.99:
            return True
        elif pos['side'] == 'SHORT' and current_price > pos['entry'] * 1.01:
            return True
        
        return False

    def add_to_position(self, symbol, signal):
        """Añadir a posición existente"""
        try:
            if not config.ENABLE_PYRAMIDING:
                return False
                
            current_pos = self.positions[symbol]
            new_quantity = self._calculate_size(symbol, signal['price'], signal) * 0.5  # 50% tamaño inicial
            
            if new_quantity <= 0:
                return False
            
            # Ejecutar orden adicional
            order_side = SIDE_BUY if current_pos['side'] == "LONG" else SIDE_SELL
            order = self.api.place_order(symbol, order_side, new_quantity)
            
            if order:
                # Actualizar posición promedio
                total_qty = current_pos['qty'] + new_quantity
                current_pos['entry'] = (
                    (current_pos['entry'] * current_pos['qty'] + signal['price'] * new_quantity) / total_qty
                )
                current_pos['qty'] = total_qty
                
                # Actualizar niveles de pyramiding
                self.entry_levels[symbol] = self.entry_levels.get(symbol, 0) + 1
                
                log.info(f"📈 Pyramiding: Añadido a {symbol} - Nuevo promedio: {current_pos['entry']:.6f}")
                return True
                
        except Exception as e:
            log.error(f"Error en pyramiding {symbol}: {e}")
        
        return False

    def open_position(self, symbol: str, signal: Dict) -> bool:
        """Abrir posición"""
        try:
            price = signal['price']
            side = signal['type']
            
            # Verificar pyramiding primero
            if self.can_add_to_position(symbol, signal):
                return self.add_to_position(symbol, signal)
            
            # Calcular tamaño
            quantity = self._calculate_size(symbol, price, signal)
            if quantity <= 0:
                return False
            
            # Configurar símbolo
            self.api.ensure_symbol_settings(symbol)
            
            # Calcular SL/TP
            sl, tp = RiskManager.calculate_sl_tp(signal, price)
            
            # Abrir
            order_side = SIDE_BUY if side == "LONG" else SIDE_SELL
            order = self.api.place_order(symbol, order_side, quantity)
            
            if not order:
                return False
            
            # Guardar datos
            self.positions[symbol] = {
                'entry': price,
                'sl': sl,
                'tp': tp,
                'side': side,
                'qty': quantity,
                'time': time.time()
            }
            
            # Inicializar pyramiding
            self.entry_levels[symbol] = 0
            
            # Registrar métricas
            health_monitor.record_metric('positions_opened')
            
            # Log
            log.info(f"")
            log.info(f"{'='*60}")
            log.info(f"🚀 POSICIÓN ABIERTA: {symbol} {side}")
            log.info(f"{'='*60}")
            log.info(f"💰 Precio: {price:.6f}")
            log.info(f"📦 Cantidad: {quantity:.6f}")
            log.info(f"🛡️ SL: {sl:.6f} | 🎯 TP: {tp:.6f}")
            log.info(f"⚡ Fuerza: {signal['strength']:.0%} ({signal['score']}/8)")
            for reason in signal['reasons']:
                log.info(f"   {reason}")
            log.info(f"{'='*60}")
            
            # Notificar
            if self.telegram.enabled:
                self.telegram.notify_trade_opened(
                    symbol, side, quantity, price, self.capital.current_balance, signal['score']
                )
            
            return True
            
        except Exception as e:
            log.error(f"❌ Error abriendo {symbol}: {e}")
            return False
    
    def _calculate_size(self, symbol: str, price: float, signal: Dict) -> float:
        """Calcular tamaño de posición con ajuste dinámico"""
        balance = self.capital.current_balance
        if balance < config.MIN_BALANCE_THRESHOLD:
            return 0
        
        # Ajuste de riesgo según condiciones
        base_risk = config.RISK_PER_TRADE_PERCENT
        if config.AUTO_RISK_ADJUSTMENT:
            market_condition = app_state.get("market_condition", "NORMAL")
            if market_condition == "HIGH_VOLATILITY":
                base_risk *= 0.7  # Reducir riesgo en alta volatilidad
            elif market_condition == "LOW_VOLATILITY":
                base_risk = min(3.0, base_risk * 1.1)  # Aumentar ligeramente
        
        strength = signal.get('strength', 0.5)
        risk_pct = base_risk * (0.75 + strength * 0.5)
        risk_amt = balance * (risk_pct / 100)
        
        atr = signal.get('atr', price * 0.01)
        sl_dist = atr * 1.8
        
        pos_value = risk_amt / (sl_dist / price)
        quantity = pos_value / price
        
        # Aplicar filtros
        filters = self.api.get_symbol_filters(symbol)
        if filters:
            quantity = self.api.round_value(quantity, filters['stepSize'])
            quantity = max(quantity, filters['minQty'])
            
            notional = quantity * price
            if notional < filters['minNotional']:
                quantity = (filters['minNotional'] / price) * 1.05
                quantity = self.api.round_value(quantity, filters['stepSize'])
        
        return quantity
    
    def monitor_position(self, symbol: str, position: Dict) -> Optional[Dict]:
        """Monitorear posición"""
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        price = float(position.get('markPrice', 0))
        
        if price <= 0:
            return None
        
        # SL/TP
        if pos['side'] == "LONG":
            if price <= pos['sl']:
                return {'should_close': True, 'reason': 'Stop Loss'}
            if price >= pos['tp']:
                return {'should_close': True, 'reason': 'Take Profit'}
        else:
            if price >= pos['sl']:
                return {'should_close': True, 'reason': 'Stop Loss'}
            if price <= pos['tp']:
                return {'should_close': True, 'reason': 'Take Profit'}
        
        # Trailing Stop
        if config.TRAILING_STOP_ENABLED:
            result = self.trailing.update(symbol, price, pos['side'], pos['entry'])
            if result and result.get('should_close'):
                return result
        
        # Tiempo máximo (30 min)
        if time.time() - pos['time'] > 1800:
            return {'should_close': True, 'reason': 'Max Time'}
        
        return None
    
    def close_position(self, symbol: str, position: Dict, close_info: Dict):
        """Cerrar posición"""
        try:
            pos = self.positions.get(symbol)
            if not pos:
                return
            
            pnl = float(position.get('unRealizedProfit', 0))
            price = float(position.get('markPrice', 0))
            
            # Cerrar
            result = self.api.close_position(symbol, float(position['positionAmt']))
            
            if result:
                # Registrar métricas
                health_monitor.record_metric('positions_closed')
                if pnl > 0:
                    health_monitor.record_metric('trades_won')
                else:
                    health_monitor.record_metric('trades_lost')
                
                # Registrar en analytics
                self.analytics.record_trade({
                    'symbol': symbol,
                    'side': pos['side'],
                    'entry_price': pos['entry'],
                    'exit_price': price,
                    'quantity': pos['qty'],
                    'pnl': pnl,
                    'reason': close_info.get('reason', 'Unknown'),
                    'duration': time.time() - pos['time']
                })
                
                log.info(f"")
                log.info(f"{'='*60}")
                log.info(f"🔴 POSICIÓN CERRADA: {symbol}")
                log.info(f"{'='*60}")
                log.info(f"📋 Razón: {close_info['reason']}")
                log.info(f"💰 Entrada: {pos['entry']:.6f}")
                log.info(f"💰 Salida: {price:.6f}")
                log.info(f"💵 P&L: {pnl:+.2f} USDT")
                if 'max_pnl' in close_info:
                    log.info(f"🎯 Máximo: {close_info['max_pnl']:+.2f}%")
                log.info(f"{'='*60}")
                
                # Notificar
                if self.telegram.enabled:
                    self.telegram.notify_trade_closed(
                        symbol, pnl, close_info['reason'], 
                        self.capital.current_balance,
                        close_info.get('max_pnl')
                    )
                
                # Actualizar estado global
                with state_lock:
                    app_state["performance_stats"]["realized_pnl"] += pnl
                    app_state["performance_stats"]["trades_count"] += 1
                    if pnl > 0:
                        app_state["performance_stats"]["wins"] += 1
                    else:
                        app_state["performance_stats"]["losses"] += 1
                    
                    total_trades = app_state["performance_stats"]["trades_count"]
                    if total_trades > 0:
                        app_state["performance_stats"]["win_rate"] = (
                            app_state["performance_stats"]["wins"] / total_trades * 100
                        )
                
                # Limpiar
                self.positions.pop(symbol, None)
                self.entry_levels.pop(symbol, None)
                self.trailing.clear(symbol)
                self.capital.update_balance(force=True)
        
        except Exception as e:
            log.error(f"❌ Error cerrando {symbol}: {e}")

# ═══════════════════════════════════════════════════════════════════
# BOT PRINCIPAL MEJORADO
# ═══════════════════════════════════════════════════════════════════

class EnhancedTradingBot:
    """Bot de trading principal mejorado"""
    
    def __init__(self):
        self.api = BinanceFutures()
        self.capital = CapitalManager(self.api)
        self.position_mgr = AdvancedPositionManager(self.api, self.capital)
        self.signal_detector = SignalDetector()
        self.telegram = TelegramNotifier()
        self.error_handler = AdvancedErrorHandler()
        self.backtester = Backtester(self.api)
        
        self.cycle = 0
        self.start_time = time.time()
        self.scanned = {}
        self.symbols = list(config.PRIORITY_SYMBOLS)
        
        # Estado de mercado
        self.market_volatility = 0
        self.trend_direction = 0
    
    def run(self):
        """Bucle principal mejorado"""
        
        log.info("")
        log.info("="*70)
        log.info("🚀 BOT DE TRADING MEJORADO V13.0 - SISTEMA AVANZADO")
        log.info("="*70)
        log.info(f"⚡ Leverage: {config.LEVERAGE}x")
        log.info(f"📊 Estrategia: Multi-Confirmación ({config.MIN_SIGNAL_SCORE}/8)")
        log.info(f"🔄 Trailing Stop: {config.TRAILING_STOP_ACTIVATION}%")
        log.info(f"📈 Pyramiding: {'Activado' if config.ENABLE_PYRAMIDING else 'Desactivado'}")
        log.info("="*70)
        log.info("")
        
        # Inicializar
        self.capital.update_balance(force=True)
        log.info(f"💰 Balance Inicial: {self.capital.current_balance:.2f} USDT")
        log.info("")
        
        # Notificar
        if self.telegram.enabled:
            self.telegram.send_message(
                f"🤖 <b>BOT MEJORADO INICIADO</b>\n\n"
                f"⚡ Leverage: {config.LEVERAGE}x\n"
                f"💰 Balance: ${self.capital.current_balance:.2f}\n"
                f"📈 Pyramiding: {'✅' if config.ENABLE_PYRAMIDING else '❌'}"
            )
        
        errors = 0
        
        while True:
            try:
                with state_lock:
                    if not app_state["running"]:
                        log.info("🛑 Bot detenido")
                        break
                
                # Health check del sistema
                if self.error_handler.circuit_open:
                    log.warning("⏸️ Circuit breaker activado - pausando operaciones")
                    time.sleep(60)
                    continue
                
                # Actualizar balance
                if self.cycle % 5 == 0:
                    self.capital.update_balance()
                    with state_lock:
                        app_state["balance"] = self.capital.current_balance
                
                # Análisis de condiciones de mercado
                self._analyze_market_conditions()
                
                # Trading adaptativo
                self._adaptive_trading()
                
                # Escanear símbolos
                self._scan_symbols()
                
                # Monitorear posiciones
                self._monitor_positions()
                
                # Actualizar métricas
                self._update_metrics()
                
                errors = 0
                self.error_handler.record_success()
                self.cycle += 1
                time.sleep(config.POLL_SEC)
            
            except Exception as e:
                errors += 1
                self.error_handler.record_error()
                log.error(f"❌ Error ciclo {self.cycle}: {e}")
                
                if errors >= 3:
                    log.error("🚨 Muchos errores, pausando...")
                    time.sleep(30)
                    errors = 0
                else:
                    time.sleep(15)
    
    def _analyze_market_conditions(self):
        """Analizar condiciones de mercado"""
        try:
            # Calcular volatilidad del mercado
            tickers = self.api.client.futures_ticker()
            price_changes = [float(t['priceChangePercent']) for t in tickers[:20] 
                           if float(t['priceChangePercent']) != 0]
            
            if price_changes:
                self.market_volatility = np.std(price_changes)
                
                # Determinar condición del mercado
                if self.market_volatility > 2.0:
                    app_state["market_condition"] = "HIGH_VOLATILITY"
                elif self.market_volatility < 0.5:
                    app_state["market_condition"] = "LOW_VOLATILITY"
                else:
                    app_state["market_condition"] = "NORMAL"
                    
                # Log cada 50 ciclos
                if self.cycle % 50 == 0:
                    log.info(f"📊 Condición mercado: {app_state['market_condition']} "
                            f"(Volatilidad: {self.market_volatility:.2f}%)")
                    
        except Exception as e:
            log.warning(f"⚠️ Error análisis mercado: {e}")
    
    def _adaptive_trading(self):
        """Trading adaptativo a condiciones del mercado"""
        market_condition = app_state.get("market_condition", "NORMAL")
        
        # Ajustar estrategia según condiciones
        if market_condition == "HIGH_VOLATILITY":
            # Reducir tamaño de posición en alta volatilidad
            original_risk = config.RISK_PER_TRADE_PERCENT
            config.RISK_PER_TRADE_PERCENT = original_risk * 0.7
            if self.cycle % 50 == 0:
                log.info("📉 Alta volatilidad - Reduciendo riesgo 30%")
        elif market_condition == "LOW_VOLATILITY":
            # Estrategias para mercados tranquilos
            config.RISK_PER_TRADE_PERCENT = min(3.0, config.RISK_PER_TRADE_PERCENT * 1.1)
    
    def _scan_symbols(self):
        """Escanear símbolos mejorado"""
        try:
            account = self.api._safe_api_call(self.api.client.futures_account)
            if not account:
                return
            
            open_pos = {p['symbol']: p for p in account['positions'] 
                       if float(p['positionAmt']) != 0}
            
            if len(open_pos) >= config.MAX_CONCURRENT_POS:
                return
            
            now = time.time()
            
            for symbol in self.symbols:
                try:
                    if symbol in open_pos:
                        continue
                    
                    # Cooldown
                    if now - self.scanned.get(symbol, 0) < 120:
                        continue
                    
                    self.scanned[symbol] = now
                    
                    # Obtener datos
                    df = self._get_data(symbol)
                    if df is None or len(df) < 50:
                        continue
                    
                    # Indicadores
                    df = self.signal_detector.calculate_indicators(df)
                    
                    # Detectar señal
                    signal = self.signal_detector.detect_signal(df, symbol)
                    
                    if signal and signal['strength'] > config.MIN_SIGNAL_STRENGTH:
                        log.info(f"🎯 SEÑAL: {symbol} {signal['type']} "
                                f"(Fuerza: {signal['strength']:.0%}, Score: {signal['score']}/8)")
                        
                        # Verificar drawdown antes de abrir
                        drawdown = self.capital.get_drawdown()
                        if drawdown > config.MAX_DRAWDOWN_PCT:
                            log.warning(f"⚠️ Drawdown alto ({drawdown:.1f}%), omitiendo señal")
                            continue
                        
                        # Abrir posición
                        if self.position_mgr.open_position(symbol, signal):
                            break
                
                except Exception as e:
                    log.error(f"Error escaneando {symbol}: {e}")
                    continue
        
        except Exception as e:
            log.error(f"Error en scan: {e}")
    
    def _monitor_positions(self):
        """Monitorear posiciones mejorado"""
        try:
            account = self.api._safe_api_call(self.api.client.futures_account)
            if not account:
                return
            
            open_pos = {p['symbol']: p for p in account['positions'] 
                       if float(p['positionAmt']) != 0}
            
            with state_lock:
                app_state["open_positions"] = open_pos
            
            for symbol, pos in open_pos.items():
                try:
                    close_info = self.position_mgr.monitor_position(symbol, pos)
                    if close_info and close_info.get('should_close'):
                        self.position_mgr.close_position(symbol, pos, close_info)
                
                except Exception as e:
                    log.error(f"Error monitoreando {symbol}: {e}")
        
        except Exception as e:
            log.error(f"Error en monitor: {e}")
    
    def _update_metrics(self):
        """Actualizar métricas del sistema"""
        # Actualizar health metrics cada 10 ciclos
        if self.cycle % 10 == 0:
            with state_lock:
                app_state["health_metrics"] = health_monitor.get_health_status()
                app_state["performance_stats"].update(
                    self.position_mgr.analytics.calculate_metrics()
                )
    
    def _get_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Obtener datos de klines"""
        try:
            klines = self.api._safe_api_call(
                self.api.client.futures_klines,
                symbol=symbol,
                interval=config.TIMEFRAME,
                limit=config.CANDLES_LIMIT
            )
            
            if not klines:
                return None
            
            df = pd.DataFrame(
                klines,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_asset_volume', 'number_of_trades',
                        'taker_buy_base', 'taker_buy_quote', 'ignore']
            )
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna(subset=['close'])
            
            if len(df) < 50 or (df['volume'] == 0).any():
                return None
            
            return df
        
        except Exception as e:
            log.error(f"Error obteniendo datos {symbol}: {e}")
            return None

# ═══════════════════════════════════════════════════════════════════
# RUTAS WEB MEJORADAS
# ═══════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    """Estado del bot mejorado"""
    with state_lock:
        # Actualizar métricas en tiempo real
        app_state["health_metrics"] = health_monitor.get_health_status()
        return jsonify(app_state)

@app.route('/api/start', methods=['POST'])
def api_start():
    """Iniciar bot"""
    global bot_thread
    
    with state_lock:
        if app_state["running"]:
            return jsonify({"status": "error", "message": "Bot ya está corriendo"})
        app_state["running"] = True
        app_state["status_message"] = "Iniciado"
    
    def run_bot():
        try:
            bot = EnhancedTradingBot()
            bot.run()
        except Exception as e:
            log.error(f"Error en bot: {e}")
            with state_lock:
                app_state["running"] = False
                app_state["status_message"] = f"Error: {str(e)}"
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    log.info("✅ Bot mejorado iniciado")
    return jsonify({"status": "success", "message": "Bot mejorado iniciado"})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Detener bot"""
    with state_lock:
        app_state["running"] = False
        app_state["status_message"] = "Detenido"
    
    log.info("🛑 Bot detenido")
    return jsonify({"status": "success", "message": "Bot detenido"})

@app.route('/api/emergency_stop', methods=['POST'])
def api_emergency_stop():
    """Parada de emergencia - Cierra todas las posiciones"""
    try:
        api = BinanceFutures()
        account = api.client.futures_account()
        
        closed_positions = []
        for position in account['positions']:
            position_amt = float(position['positionAmt'])
            if position_amt != 0:
                result = api.close_position(position['symbol'], position_amt)
                if result:
                    closed_positions.append(position['symbol'])
                    log.info(f"🆘 Cierre emergencia: {position['symbol']}")
        
        # Detener bot
        with state_lock:
            app_state["running"] = False
            app_state["status_message"] = "EMERGENCY STOP"
        
        # Notificar
        telegram = TelegramNotifier()
        if telegram.enabled:
            telegram.notify_system_alert(
                f"PARADA DE EMERGENCIA\n\n"
                f"Posiciones cerradas: {len(closed_positions)}\n"
                f"Símbolos: {', '.join(closed_positions) if closed_positions else 'Ninguna'}"
            )
        
        return jsonify({
            "status": "success", 
            "closed_positions": closed_positions,
            "message": "Parada de emergencia ejecutada"
        })
    
    except Exception as e:
        log.error(f"❌ Error en parada de emergencia: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """Configuración mejorada"""
    if request.method == 'POST':
        new_config = request.json
        with state_lock:
            for key, value in new_config.items():
                if hasattr(config, key):
                    # Conversión de tipos
                    current_value = getattr(config, key)
                    if isinstance(current_value, bool):
                        value = bool(value)
                    elif isinstance(current_value, int):
                        value = int(value)
                    elif isinstance(current_value, float):
                        value = float(value)
                    
                    setattr(config, key, value)
                    app_state["config"][key] = value
            
            # Log de cambios importantes
            if 'RISK_PER_TRADE_PERCENT' in new_config:
                log.info(f"⚙️ Riesgo actualizado: {config.RISK_PER_TRADE_PERCENT}%")
            if 'LEVERAGE' in new_config:
                log.info(f"⚙️ Leverage actualizado: {config.LEVERAGE}x")
        
        return jsonify({"status": "success", "message": "Configuración actualizada"})
    
    with state_lock:
        return jsonify(app_state["config"])

@app.route('/api/advanced_config', methods=['POST'])
def api_advanced_config():
    """Configuración avanzada en tiempo real"""
    try:
        new_config = request.json
        
        # Validar configuración
        valid_keys = ['TRADING_HOURS', 'MAX_DRAWDOWN_PCT', 'AUTO_RISK_ADJUSTMENT', 
                     'ENABLE_PYRAMIDING', 'MAX_PYRAMID_LEVELS']
        config_updates = {k: v for k, v in new_config.items() if k in valid_keys}
        
        with state_lock:
            # Actualizar configuración global
            for key, value in config_updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
                    app_state["config"][key] = value
            
            # Aplicar cambios en caliente
            if 'TRADING_HOURS' in config_updates:
                log.info(f"🕒 Horario de trading actualizado: {config.TRADING_HOURS}")
            if 'ENABLE_PYRAMIDING' in config_updates:
                status = "activado" if config.ENABLE_PYRAMIDING else "desactivado"
                log.info(f"📈 Pyramiding {status}")
        
        return jsonify({"status": "success", "applied": config_updates})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/positions')
def api_positions():
    """Posiciones abiertas"""
    with state_lock:
        return jsonify(app_state["open_positions"])

@app.route('/api/history')
def api_history():
    """Historial de trades"""
    with state_lock:
        return jsonify({"trades": app_state.get("trades_history", [])})

@app.route('/api/performance')
def api_performance():
    """Métricas de performance detalladas (CORREGIDO)"""
    try:
        analytics = AnalyticsEngine()
        metrics = analytics.calculate_metrics()
        
        health_status = health_monitor.get_health_status()
        
        return jsonify({
            "metrics": metrics,
            "health": health_status,
            "current_strategy": {
                "active_symbols": list(app_state.get("open_positions", {}).keys()),
                "market_condition": app_state.get("market_condition", "NORMAL"),
                "volatility": 0  # Placeholder para futuras implementaciones
            }
        })
    
    except Exception as e:
        log.error(f"Error en endpoint de performance: {e}")
        return jsonify({
            "metrics": {},
            "health": {"error": str(e)},
            "current_strategy": {}
        })

@app.route('/api/health')
def api_health():
    """Endpoint de salud del sistema"""
    try:
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime": health_monitor.get_uptime(),
            "memory_usage": f"{memory_usage:.2f} MB",
            "active_threads": threading.active_count(),
            "cpu_percent": psutil.cpu_percent(),
            "bot_cycles": getattr(health_monitor, 'cycle', 0)
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        })

@app.route('/api/optimize', methods=['POST'])
def api_optimize():
    """Optimizar parámetros del bot"""
    data = request.json
    symbol = data.get('symbol', 'BTCUSDT')
    days = data.get('days', 30)
    
    try:
        backtester = Backtester(BinanceFutures())
        results = backtester.run_backtest(symbol, days)
        
        if results:
            return jsonify({
                "status": "success", 
                "optimization": results,
                "symbol": symbol,
                "period_days": days
            })
        else:
            return jsonify({"status": "error", "message": "Error en backtesting"})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/close_position', methods=['POST'])
def api_close_position():
    """Cerrar posición manualmente"""
    try:
        data = request.json
        symbol = data.get('symbol')
        
        with state_lock:
            if symbol not in app_state["open_positions"]:
                return jsonify({"status": "error", "message": "Posición no encontrada"})
            position = app_state["open_positions"][symbol]
        
        api = BinanceFutures()
        result = api.close_position(symbol, float(position['positionAmt']))
        
        if result:
            log.info(f"✅ Posición {symbol} cerrada manualmente")
            return jsonify({"status": "success", "message": f"Posición {symbol} cerrada"})
        else:
            return jsonify({"status": "error", "message": "Error cerrando posición"})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@socketio.on('connect')
def handle_connect():
    """Cliente conectado"""
    log.info('📱 Cliente WebSocket conectado')
    socketio.emit('status_update', app_state)

@socketio.on('disconnect')
def handle_disconnect():
    """Cliente desconectado"""
    log.info('📱 Cliente WebSocket desconectado')

@socketio.on('get_health')
def handle_health():
    """Solicitud de salud"""
    socketio.emit('health_update', health_monitor.get_health_status())

# ═══════════════════════════════════════════════════════════════════
# INICIALIZACIÓN MEJORADA (CORREGIDO)
# ═══════════════════════════════════════════════════════════════════

def enhanced_initialize():
    """Inicialización mejorada"""
    try:
        log.info("🚀 INICIALIZACIÓN AVANZADA DEL SISTEMA")
        
        # Verificar dependencias
        try:
            import psutil
            log.info("✅ Dependencias avanzadas cargadas")
        except ImportError as e:
            log.warning(f"⚠️ Dependencia faltante: {e}")
        
        # Inicializar API
        api = BinanceFutures()
        log.info("✅ Conexión Binance OK")
        
        # Inicializar capital
        capital = CapitalManager(api)
        if capital.update_balance(force=True):
            log.info(f"💰 Balance: {capital.current_balance:.2f} USDT")
            with state_lock:
                app_state["balance"] = capital.current_balance
        
        # Actualizar health metrics inicial
        with state_lock:
            app_state["health_metrics"] = health_monitor.get_health_status()
        
        log.info("✅ Sistema avanzado inicializado correctamente")
        return True
        
    except Exception as e:
        log.error(f"❌ Error inicialización avanzada: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("="*70)
    log.info("🚀 BINANCE FUTURES BOT V13.0 - SISTEMA MEJORADO")
    log.info("="*70)
    
    if not enhanced_initialize():
        log.error("❌ Inicialización fallida")
        exit(1)
    
    try:
        log.info("🌐 Servidor: http://0.0.0.0:5000")
        log.info("📊 Dashboard: http://localhost:5000")
        log.info("🔧 Características avanzadas: ✅ ACTIVADAS")
        socketio.run(
            app, 
            host='0.0.0.0', 
            port=5000, 
            debug=False,
            allow_unsafe_werkzeug=True
        )
    except Exception as e:
        log.error(f"❌ Error servidor: {e}")
        exit(1)