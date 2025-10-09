from __future__ import annotations

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO

# === AJUSTES PRINCIPALES REALIZADOS ===

# 1. CORRECCIÓN DE IMPORTACIONES Y CONFIGURACIÓN INICIAL
"""
Binance Futures Bot - Aplicación Web v12.0 con Gestión de Capital Real
Sistema de trading avanzado con seguimiento de capital real y reinversión de ganancias
Por gregorbc@gmail.com
"""

import json
import logging
import math
import os
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

# Configuración inicial mejorada
load_dotenv()


# 2. MEJORA EN LA CONFIGURACIÓN DE LOGGING
def setup_logging():
    """Configuración robusta del sistema de logging"""
    log = logging.getLogger("BinanceFuturesBot")

    # Limpiar handlers existentes
    for handler in log.handlers[:]:
        log.removeHandler(handler)

    # Crear directorio de logs si no existe
    os.makedirs("logs", exist_ok=True)

    # Configurar formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler para archivo
    file_handler = logging.FileHandler(
        f"logs/{getattr(config, 'LOG_FILE', 'bot.log')}", encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Configurar nivel
    log_level = getattr(logging, getattr(config, "LOG_LEVEL", "INFO"))
    log.setLevel(log_level)
    file_handler.setLevel(log_level)
    console_handler.setLevel(log_level)

    # Agregar handlers
    log.addHandler(file_handler)
    log.addHandler(console_handler)

    # Reducir verbosidad de librerías externas
    for logger_name in ["binance", "urllib3", "engineio", "socketio"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    return log


# 3. CONFIGURACIÓN MEJORADA CON VALORES MÁS CONSERVADORES
@dataclass
class CONFIG:
    # Configuración Global - Valores más seguros para 20x
    LEVERAGE: int = 20
    MAX_CONCURRENT_POS: int = 3  # Reducido para mejor gestión de riesgo
    NUM_SYMBOLS_TO_SCAN: int = 50  # Reducido para mejor rendimiento

    # Gestión de Riesgo Mejorada
    STOP_LOSS_PERCENT: float = 0.4  # Más conservador para 20x
    TAKE_PROFIT_PERCENT: float = 0.8  # Ratio riesgo/beneficio 1:2
    RISK_PER_TRADE_PERCENT: float = 0.5  # Reducido a 0.5% por trade

    # Nuevos parámetros de seguridad
    MAX_DAILY_LOSS_PERCENT: float = 3.0  # Límite diario más conservador
    MAX_DRAWDOWN_PERCENT: float = 6.0  # Drawdown máximo reducido

    # Configuración de símbolos más estricta
    MIN_24H_VOLUME: float = 25_000_000  # Mayor volumen mínimo

    # Exclusión de símbolos de alto riesgo (ampliada)
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
    POLL_SEC: float = 15.0  # Aumentado para reducir llamadas a API

    # Activación de características de seguridad
    DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"
    ENABLE_TELEGRAM: bool = bool(os.getenv("TELEGRAM_BOT_TOKEN"))

    def __post_init__(self):
        """Validaciones adicionales de configuración"""
        if self.LEVERAGE > 20:
            raise ValueError("❌ El apalancamiento no puede exceder 20x")
        if self.RISK_PER_TRADE_PERCENT > 2.0:
            raise ValueError("❌ El riesgo por trade no puede exceder el 2%")


# 4. MEJORA EN LA CLASE CapitalManager
class CapitalManager:
    """Gestor de capital mejorado con mejores validaciones"""

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
            log.error(f"❌ Balance inválido: {balance}")
            return False
        if balance > 1000000:  # Límite superior realista
            log.error(f"❌ Balance sospechosamente alto: {balance}")
            return False
        return True

    def update_balance(self, force: bool = False) -> bool:
        """Actualizar balance con mejores validaciones"""
        current_time = time.time()

        if force or (current_time - self.last_balance_update > 300):  # 5 minutos
            try:
                new_balance = self.get_real_balance()

                if not self.validate_balance(new_balance):
                    return False

                # Actualizar métricas
                if self.current_balance == 0:
                    self.initial_balance = new_balance
                    self.daily_starting_balance = new_balance
                    log.info(f"💰 Capital inicial: {new_balance:.2f} USDT")

                previous_balance = self.current_balance
                self.current_balance = new_balance
                self.last_balance_update = current_time

                # Calcular P&L
                self.total_profit = self.current_balance - self.initial_balance
                daily_pnl_change = self.current_balance - self.daily_starting_balance

                # Solo registrar cambios significativos
                if abs(self.current_balance - previous_balance) > 0.1:
                    log.info(
                        f"📊 Balance actualizado: {self.current_balance:.2f} USDT | "
                        f"P&L Diario: {daily_pnl_change:+.2f} USDT"
                    )

                self._save_balance_to_db()
                return True

            except Exception as e:
                log.error(f"❌ Error crítico actualizando balance: {e}")
                return False
        return False


# 5. SISTEMA DE RECUPERACIÓN DE ERRORES MEJORADO
class ErrorRecoverySystem:
    """Sistema mejorado para manejo y recuperación de errores"""

    def __init__(self, trading_bot):
        self.bot = trading_bot
        self.error_count = 0
        self.last_error_time = 0
        self.max_errors_per_hour = 10

    def handle_error(self, error: Exception, context: str = ""):
        """Manejar error y decidir acción de recuperación"""
        self.error_count += 1
        current_time = time.time()

        log.error(f"🚨 Error en {context}: {error}")

        # Reiniciar contador si ha pasado más de 1 hora
        if current_time - self.last_error_time > 3600:
            self.error_count = 1

        self.last_error_time = current_time

        # Decidir acción basada en la frecuencia de errores
        if self.error_count >= self.max_errors_per_hour:
            log.warning(
                "🛑 Muchos errores recientes, pausando operaciones por 10 minutos"
            )
            time.sleep(600)  # Pausa de 10 minutos
            self.error_count = 0
            return "PAUSE"

        # Pausa corta para errores normales
        time.sleep(30)
        return "RETRY"


# 6. MEJORAS EN LA CLASE TradingBot
class TradingBot:
    def __init__(self):
        self.api = BinanceFutures()
        self.capital_manager = CapitalManager(self.api)
        self.error_recovery = ErrorRecoverySystem(self)
        self.recently_signaled = set()
        self.cycle_count = 0
        self.start_time = time.time()

        # Inicialización más segura
        self._initialize_safely()

    def _initialize_safely(self):
        """Inicialización segura con manejo de errores"""
        try:
            # Verificar conexión a API primero
            if not self.test_api_connection():
                raise ConnectionError("No se pudo conectar a la API de Binance")

            # Inicializar componentes opcionales
            self._initialize_optional_components()

            log.info("✅ Bot inicializado correctamente")

        except Exception as e:
            log.error(f"❌ Error en inicialización: {e}")
            raise

    def test_api_connection(self) -> bool:
        """Verificar conexión a la API"""
        try:
            # Intentar obtener información de cuenta
            account_info = self.api._safe_api_call(self.api.client.futures_account)
            if account_info:
                log.info("✅ Conexión a API verificada")
                return True
            return False
        except Exception as e:
            log.error(f"❌ Error conectando a API: {e}")
            return False

    def _initialize_optional_components(self):
        """Inicializar componentes opcionales con manejo de errores"""
        # Telegram
        try:
            self.telegram_notifier = TelegramNotifier()
            if self.telegram_notifier.enabled:
                log.info("✅ Telegram notifier inicializado")
        except Exception as e:
            log.warning(f"⚠️ Telegram notifier no disponible: {e}")

        # Base de datos
        try:
            if DB_ENABLED:
                self.performance_analyzer = PerformanceAnalyzer(SessionLocal())
                log.info("✅ Performance analyzer inicializado")
        except Exception as e:
            log.warning(f"⚠️ Performance analyzer no disponible: {e}")

    def run(self):
        """Método principal mejorado con mejor manejo de errores"""
        log.info("🚀 Iniciando Bot de Trading - Modo 20x")

        try:
            self._main_loop()
        except KeyboardInterrupt:
            log.info("⏹️ Bot detenido por el usuario")
        except Exception as e:
            log.error(f"❌ Error crítico en el bot: {e}")
            # Intentar reinicio seguro
            self._safe_restart()

    def _main_loop(self):
        """Loop principal con mejor gestión de errores"""
        while True:
            try:
                with state_lock:
                    if not app_state["running"]:
                        break

                self.cycle_count += 1

                # Ejecutar ciclo de trading
                self._execute_trading_cycle()

                # Gestión de recursos
                self._resource_management()

                time.sleep(config.POLL_SEC)

            except Exception as e:
                recovery_action = self.error_recovery.handle_error(e, "ciclo principal")
                if recovery_action == "PAUSE":
                    continue

    def _execute_trading_cycle(self):
        """Ejecutar un ciclo completo de trading"""
        # Actualizar balance
        if not self.capital_manager.update_balance():
            log.warning("⚠️ No se pudo actualizar el balance, omitiendo ciclo")
            return

        # Verificar condiciones de mercado
        if not self._check_market_conditions():
            return

        # Obtener y procesar símbolos
        symbols = self.get_top_symbols()
        if not symbols:
            log.warning("⚠️ No se encontraron símbolos válidos")
            return

        # Procesar posiciones abiertas
        self._process_open_positions(symbols)

        # Buscar nuevas oportunidades
        if len(self.get_open_positions()) < config.MAX_CONCURRENT_POS:
            self._scan_new_opportunities(symbols)

    def _check_market_conditions(self) -> bool:
        """Verificar condiciones generales del mercado"""
        # Verificar balance mínimo
        if self.capital_manager.current_balance < config.MIN_BALANCE_THRESHOLD:
            log.warning("⏸️ Balance insuficiente para operar")
            return False

        # Verificar límite de pérdidas diarias
        daily_pnl = (
            self.capital_manager.current_balance
            - self.capital_manager.daily_starting_balance
        )
        daily_loss_limit = (
            self.capital_manager.daily_starting_balance
            * config.MAX_DAILY_LOSS_PERCENT
            / 100
        )

        if daily_pnl < -daily_loss_limit:
            log.warning(f"⛔ Límite de pérdida diaria alcanzado: {daily_pnl:.2f}")
            return False

        return True

    def _resource_management(self):
        """Gestión de recursos y mantenimiento"""
        if self.cycle_count % 20 == 0:  # Cada 20 ciclos
            # Limpiar memoria
            self._cleanup_memory()

        if self.cycle_count % 100 == 0:  # Cada 100 ciclos
            # Verificar salud del sistema
            self._system_health_check()

    def _cleanup_memory(self):
        """Limpiar memoria y recursos"""
        import gc

        gc.collect()

        # Limpiar símbolos señalizados antiguos
        current_time = time.time()
        self.recently_signaled = {
            sym
            for sym, timestamp in self.recently_signaled.items()
            if current_time - timestamp < 3600  # Mantener por 1 hora
        }

    def _system_health_check(self):
        """Verificar salud del sistema"""
        log.info("🔍 Verificando salud del sistema...")

        # Verificar conexión API
        if not self.test_api_connection():
            log.error("❌ Problema de conexión API detectado")

        # Verificar memoria
        import psutil

        memory_usage = psutil.Process().memory_percent()
        if memory_usage > 80:
            log.warning(f"⚠️ Uso de memoria alto: {memory_usage:.1f}%")

    def _safe_restart(self):
        """Reinicio seguro del bot"""
        log.info("🔄 Intentando reinicio seguro...")
        time.sleep(60)  # Esperar 1 minuto

        try:
            # Limpiar estado
            with state_lock:
                app_state["open_positions"] = {}
                app_state["trailing_stop_data"] = {}
                app_state["sl_tp_data"] = {}

            # Reconectar API
            self.api = BinanceFutures()
            self.capital_manager = CapitalManager(self.api)

            log.info("✅ Reinicio seguro completado")
            self.run()  # Continuar ejecución

        except Exception as e:
            log.error(f"❌ Error en reinicio seguro: {e}")
            log.info("🛑 Bot detenido por errores críticos")


# 7. MEJORAS EN LA GESTIÓN DE RIESGO
class RiskManager:
    """Gestor de riesgo mejorado para 20x leverage"""

    def __init__(self, trading_bot):
        self.bot = trading_bot
        self.symbol_risk_scores = {}

    def calculate_symbol_risk(self, symbol: str, df: pd.DataFrame) -> float:
        """Calcular score de riesgo para un símbolo (0-1, donde 1 es máximo riesgo)"""
        if df is None or len(df) < 20:
            return 1.0  # Máximo riesgo si no hay datos

        try:
            risk_factors = []

            # 1. Volatilidad (40% peso)
            volatility = self._calculate_volatility(df)
            vol_score = min(1.0, volatility / 5.0)  # Normalizar
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
        return returns.std() * np.sqrt(365) * 100  # Volatilidad anualizada

    def _calculate_volume_risk(self, df: pd.DataFrame) -> float:
        """Calcular riesgo basado en volumen"""
        current_volume = df["volume"].iloc[-1]
        avg_volume = df["volume"].tail(20).mean()

        if avg_volume == 0:
            return 1.0

        volume_ratio = current_volume / avg_volume
        # Menor volumen = mayor riesgo
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
                return min(1.0, spread / 0.5)  # Normalizar
        except:
            pass
        return 1.0

    def should_trade_symbol(self, symbol: str, df: pd.DataFrame) -> bool:
        """Decidir si es seguro operar un símbolo"""
        risk_score = self.calculate_symbol_risk(symbol, df)

        # Umbral de riesgo ajustado para 20x
        max_risk_threshold = 0.6

        if risk_score > max_risk_threshold:
            log.info(f"⏭️ {symbol} excluido por alto riesgo: {risk_score:.2f}")
            return False

        return True


# 8. INTEGRACIÓN DEL RISK MANAGER EN EL BOT
class TradingBot:
    def __init__(self):
        # ... inicialización existente ...
        self.risk_manager = RiskManager(self)

    def check_signal(self, df: pd.DataFrame, symbol: str) -> Optional[str]:
        """Verificar señal con gestión de riesgo integrada"""
        # Verificación de riesgo primero
        if not self.risk_manager.should_trade_symbol(symbol, df):
            return None

        # ... lógica existente de señales ...

        return signal


# 9. MEJORAS EN LA INTERFAZ WEB

# === BOOTSTRAP Windows-friendly (no eventlet) ===
try:
    app
except NameError:
    app = Flask(__name__)
try:
    CORS(app, resources={r"/*": {"origins": "*"}})
except Exception:
    pass
try:
    socketio
except NameError:
    socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")
try:
    state_lock
except NameError:
    import threading as _th

    state_lock = _th.RLock()
try:
    app_state
except NameError:
    app_state = {
        "running": False,
        "open_positions": {},
        "trailing_stop_data": {},
        "sl_tp_data": {},
    }


# === END BOOTSTRAP ===
@app.route("/api/health")
def api_health():
    """Endpoint de salud del sistema"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime": time.time() - app_state.get("start_time", time.time()),
        "memory_usage": f"{psutil.Process().memory_percent():.1f}%",
        "cpu_usage": f"{psutil.cpu_percent():.1f}%",
    }

    try:
        # Verificar conexión a API
        bot = TradingBot()
        if bot.test_api_connection():
            health_status["api_connection"] = "healthy"
        else:
            health_status["api_connection"] = "unhealthy"
            health_status["status"] = "degraded"
    except:
        health_status["api_connection"] = "unhealthy"
        health_status["status"] = "degraded"

    return jsonify(health_status)


@app.route("/api/risk/metrics")
@require_api_token
def api_risk_metrics():
    """Métricas de riesgo en tiempo real"""
    with state_lock:
        return jsonify(
            {
                "current_balance": app_state.get("balance", 0),
                "open_positions": len(app_state.get("open_positions", {})),
                "exposure_ratio": app_state.get("risk_metrics", {}).get(
                    "exposure_ratio", 0
                ),
                "max_drawdown": app_state.get("risk_metrics", {}).get(
                    "max_drawdown", 0
                ),
                "daily_pnl": app_state.get("daily_pnl", 0),
            }
        )


# 10. CONFIGURACIÓN FINAL MEJORADA
if __name__ == "__main__":
    # Configurar logging primero
    log = setup_logging()

    # Verificar variables de entorno críticas
    required_env_vars = ["BINANCE_API_KEY", "BINANCE_API_SECRET"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        log.error(f"❌ Variables de entorno faltantes: {', '.join(missing_vars)}")
        exit(1)

    # Inicializar estado de la aplicación
    with state_lock:
        app_state.update(
            {
                "start_time": time.time(),
                "running": False,
                "status_message": "Inicializando...",
                "balance": 0.0,
                "open_positions": {},
                "performance_stats": {
                    "trades_count": 0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "realized_pnl": 0.0,
                },
            }
        )

    log.info("✅ Sistema inicializado correctamente")

    # Iniciar servidor
    try:
        socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    except Exception as e:
        log.error(f"❌ Error iniciando servidor: {e}")
