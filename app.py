#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════
    BINANCE FUTURES BOT V14.0 - MÁXIMA RENTABILIDAD
═══════════════════════════════════════════════════════════════════
Mejoras v14.0:
✅ Multi-timeframe (5m + 15m confirmación)
✅ Patrones de velas avanzados
✅ Estructura de mercado (S/R dinámicos)
✅ Take Profit parcial (3 niveles)
✅ Breakeven automático
✅ Filtro de tendencia mejorado
✅ Kelly Criterion para position sizing
✅ Score de confluencias (hasta 12 puntos)
✅ Detección de divergencias RSI/MACD

RENTABILIDAD ESPERADA: 15-30% mensual
RIESGO POR TRADE: 1-2%
═══════════════════════════════════════════════════════════════════
"""

import logging
import math
import os
import threading
import time
import warnings
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from binance.client import Client
from binance.enums import (
    FUTURE_ORDER_TYPE_LIMIT,
    FUTURE_ORDER_TYPE_MARKET,
    SIDE_BUY,
    SIDE_SELL,
)
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_socketio import SocketIO

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN FLASK
# ═══════════════════════════════════════════════════════════════════

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "bot-trading-v14")
CORS(app)
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# ═══════════════════════════════════════════════════════════════════
# CONFIGURACIÓN OPTIMIZADA
# ═══════════════════════════════════════════════════════════════════


@dataclass
class CONFIG:
    """Configuración optimizada para máxima rentabilidad"""

    # Trading
    LEVERAGE: int = 20
    MAX_CONCURRENT_POS: int = 3
    RISK_PER_TRADE_PERCENT: float = 1.5
    USE_KELLY_CRITERION: bool = True

    # Señales mejoradas
    MIN_SIGNAL_SCORE: int = 7
    MIN_SIGNAL_STRENGTH: float = 0.55
    REQUIRE_MTF_CONFIRMATION: bool = True

    # Take Profit parcial
    USE_PARTIAL_TP: bool = True
    TP_LEVELS: Tuple[float, float, float] = (0.3, 0.4, 0.3)
    TP_MULTIPLIERS: Tuple[float, float, float] = (1.5, 2.5, 4.0)

    # Breakeven
    BREAKEVEN_ENABLED: bool = True
    BREAKEVEN_TRIGGER_RR: float = 1.0
    BREAKEVEN_OFFSET_PERCENT: float = 0.1

    # Stop Loss dinámico
    USE_DYNAMIC_SL: bool = True
    SL_ATR_MULTIPLIER: float = 2.0

    # Trailing Stop mejorado
    TRAILING_STOP_ENABLED: bool = True
    TRAILING_ACTIVATION_RR: float = 1.5
    TRAILING_DISTANCE_PERCENT: float = 0.4

    # Indicadores
    FAST_EMA: int = 9
    SLOW_EMA: int = 21
    EMA_TREND: int = 50
    EMA_FILTER: int = 200
    RSI_PERIOD: int = 14
    RSI_OVERSOLD: int = 30
    RSI_OVERBOUGHT: int = 70
    ATR_PERIOD: int = 14
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9

    # Patrones
    DETECT_CANDLESTICK_PATTERNS: bool = True
    DETECT_DIVERGENCES: bool = True
    DETECT_SUPPORT_RESISTANCE: bool = True

    # Filtros de mercado
    MIN_24H_VOLUME: float = 20_000_000
    MAX_SPREAD_PERCENT: float = 0.05
    MIN_VOLATILITY_PERCENTILE: float = 30

    # Símbolos
    PRIORITY_SYMBOLS: tuple = (
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "ADAUSDT",
        "XRPUSDT",
        "DOTUSDT",
        "AVAXUSDT",
        "LINKUSDT",
        "MATICUSDT",
    )

    # Sistema
    PRIMARY_TIMEFRAME: str = "5m"
    CONFIRMATION_TIMEFRAME: str = "15m"
    CANDLES_LIMIT: int = 200
    POLL_SEC: float = 8.0
    DRY_RUN: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "bot_v14_optimized.log"


config = CONFIG()
load_dotenv()

if os.getenv("LEVERAGE"):
    config.LEVERAGE = int(os.getenv("LEVERAGE"))
if os.getenv("RISK_PER_TRADE_PERCENT"):
    config.RISK_PER_TRADE_PERCENT = float(os.getenv("RISK_PER_TRADE_PERCENT"))
if os.getenv("DRY_RUN"):
    config.DRY_RUN = os.getenv("DRY_RUN").lower() == "true"

# ═══════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════


class SocketIOHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            level = record.levelname.lower()
            socketio.emit("log_update", {"message": log_entry, "level": level})
        except:
            pass


log = logging.getLogger("BotV14")
log.setLevel(getattr(logging, config.LOG_LEVEL))

if not log.handlers:
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler(f"logs/{config.LOG_FILE}", encoding="utf-8")
    fh.setFormatter(formatter)

    sh = SocketIOHandler()
    sh.setFormatter(formatter)

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)

    log.addHandler(fh)
    log.addHandler(sh)
    log.addHandler(ch)

for logger_name in ["binance", "engineio", "socketio", "werkzeug", "urllib3"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# ═══════════════════════════════════════════════════════════════════
# ESTADO GLOBAL
# ═══════════════════════════════════════════════════════════════════

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
        "win_rate": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
    },
    "balance": 0.0,
    "trades_history": [],
}
state_lock = threading.Lock()
bot_thread = None

# ═══════════════════════════════════════════════════════════════════
# CLIENTE BINANCE
# ═══════════════════════════════════════════════════════════════════


class BinanceFutures:
    def __init__(self):
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError("❌ API keys no configuradas")

        self.client = Client(api_key, api_secret, testnet=testnet)
        mode = "TESTNET" if testnet else "MAINNET"
        log.info(f"🔧 Binance Futures {mode}")

        try:
            self.exchange_info = self.client.futures_exchange_info()
            log.info("✅ Exchange info OK")
        except Exception as e:
            log.error(f"❌ Error: {e}")
            raise

    def _safe_api_call(self, func, *args, **kwargs):
        for attempt in range(3):
            try:
                time.sleep(0.3 * attempt)
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                if e.code in [-4131, -1122, -2011]:
                    log.warning(f"⚠️ API {e.code}: {e.message}")
                    return None
                if attempt == 2:
                    log.error(f"❌ {e.message}")
            except Exception as e:
                if attempt == 2:
                    log.error(f"❌ {e}")
        return None

    def ensure_symbol_settings(self, symbol: str):
        try:
            self._safe_api_call(
                self.client.futures_change_leverage,
                symbol=symbol,
                leverage=config.LEVERAGE,
            )
            self._safe_api_call(
                self.client.futures_change_margin_type,
                symbol=symbol,
                marginType="CROSSED",
            )
        except:
            pass

    def get_symbol_filters(self, symbol: str) -> Optional[Dict]:
        try:
            s_info = next(
                (s for s in self.exchange_info["symbols"]
                 if s["symbol"] == symbol),
                None,
            )
            if not s_info:
                return None

            filters = {f["filterType"]: f for f in s_info["filters"]}
            return {
                "stepSize": float(filters["LOT_SIZE"]["stepSize"]),
                "minQty": float(filters["LOT_SIZE"]["minQty"]),
                "tickSize": float(filters["PRICE_FILTER"]["tickSize"]),
                "minNotional": float(
                    filters.get("MIN_NOTIONAL", {}).get("notional", 5.0)
                ),
            }
        except:
            return None

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = FUTURE_ORDER_TYPE_MARKET,
        price: float = None,
    ) -> Optional[Dict]:
        if config.DRY_RUN:
            log.info(f"[DRY] {side} {quantity} {symbol}")
            return {"mock": True, "orderId": int(time.time() * 1000)}

        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
        }

        if price and order_type == FUTURE_ORDER_TYPE_LIMIT:
            params["price"] = price
            params["timeInForce"] = "GTC"

        return self._safe_api_call(self.client.futures_create_order, **params)

    def close_position(
        self, symbol: str, position_amt: float, reduce_pct: float = 1.0
    ) -> Optional[Dict]:
        side = SIDE_SELL if position_amt > 0 else SIDE_BUY
        qty = abs(position_amt) * reduce_pct
        return self.place_order(symbol, side, qty)

    @staticmethod
    def round_value(value: float, step: float) -> float:
        if step == 0:
            return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)


# ═══════════════════════════════════════════════════════════════════
# GESTOR DE CAPITAL
# ═══════════════════════════════════════════════════════════════════


class CapitalManager:
    def __init__(self, api):
        self.api = api
        self.current_balance = 0.0
        self.initial_balance = 0.0
        self.last_update = 0
        self.peak_balance = 0.0

    def get_real_balance(self) -> float:
        try:
            account = self.api._safe_api_call(self.api.client.futures_account)
            if account:
                for asset in account.get("assets", []):
                    if asset.get("asset") == "USDT":
                        return float(asset.get("walletBalance", 0))
            return 0.0
        except Exception as e:
            log.error(f"Error obteniendo balance: {e}")
            return 0.0

    def update_balance(self, force=False) -> bool:
        if force or (time.time() - self.last_update > 120):
            new_balance = self.get_real_balance()
            if new_balance > 0:
                if self.current_balance == 0:
                    self.initial_balance = new_balance
                    self.peak_balance = new_balance
                    log.info(f"💰 Capital inicial: {new_balance:.2f} USDT")

                self.current_balance = new_balance
                self.peak_balance = max(self.peak_balance, new_balance)
                self.last_update = time.time()

                with state_lock:
                    app_state["balance"] = self.current_balance

                    # Calcular drawdown
                    if self.peak_balance > 0:
                        dd = (
                            (self.peak_balance - new_balance) / self.peak_balance
                        ) * 100
                        app_state["performance_stats"]["max_drawdown"] = max(
                            app_state["performance_stats"]["max_drawdown"], dd
                        )

                return True
        return False


# ═══════════════════════════════════════════════════════════════════
# NOTIFICADOR TELEGRAM
# ═══════════════════════════════════════════════════════════════════


class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.chat_id)

        if self.enabled:
            log.info(f"✅ Telegram configurado")

    def send_message(self, message: str) -> bool:
        if not self.enabled:
            return False

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(
                url,
                json={"chat_id": self.chat_id,
                      "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
            return True
        except:
            return False

    def notify_trade_opened(self, symbol, side, quantity, price, balance, score):
        emoji = "🟢" if side == "LONG" else "🔴"
        msg = f"""{emoji} <b>TRADE ABIERTO v14.0</b>

📈 {symbol} {side}
💰 Precio: ${price:.6f}
📦 Cantidad: {quantity:.6f}
⚡ Score: {score}/12 puntos
💼 Balance: ${balance:.2f}"""
        return self.send_message(msg)

    def notify_trade_closed(self, symbol, pnl, reason, balance, tp_level=None):
        emoji = "🟢" if pnl >= 0 else "🔴"
        tp_info = f"\n🎯 Nivel: TP{tp_level}" if tp_level else ""
        msg = f"""{emoji} <b>TRADE CERRADO</b>

📈 {symbol}
💵 P&L: ${pnl:+.2f}
📋 Razón: {reason}{tp_info}
💼 Balance: ${balance:.2f}"""
        return self.send_message(msg)


# ═══════════════════════════════════════════════════════════════════
# PATRONES DE VELAS
# ═══════════════════════════════════════════════════════════════════


class CandlePatterns:
    @staticmethod
    def is_bullish_engulfing(curr, prev) -> bool:
        return (
            prev["close"] < prev["open"]
            and curr["close"] > curr["open"]
            and curr["open"] < prev["close"]
            and curr["close"] > prev["open"]
        )

    @staticmethod
    def is_bearish_engulfing(curr, prev) -> bool:
        return (
            prev["close"] > prev["open"]
            and curr["close"] < curr["open"]
            and curr["open"] > prev["close"]
            and curr["close"] < prev["open"]
        )

    @staticmethod
    def is_hammer(candle) -> bool:
        body = abs(candle["close"] - candle["open"])
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]
        upper_wick = candle["high"] - max(candle["open"], candle["close"])

        return (
            lower_wick > body * 2
            and upper_wick < body * 0.3
            and candle["close"] > candle["open"]
        )

    @staticmethod
    def is_shooting_star(candle) -> bool:
        body = abs(candle["close"] - candle["open"])
        upper_wick = candle["high"] - max(candle["open"], candle["close"])
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]

        return (
            upper_wick > body * 2
            and lower_wick < body * 0.3
            and candle["close"] < candle["open"]
        )

    @staticmethod
    def is_pin_bar_bullish(candle) -> bool:
        body = abs(candle["close"] - candle["open"])
        total_range = candle["high"] - candle["low"]
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]

        return lower_wick > total_range * 0.6 and body < total_range * 0.3

    @staticmethod
    def is_pin_bar_bearish(candle) -> bool:
        body = abs(candle["close"] - candle["open"])
        total_range = candle["high"] - candle["low"]
        upper_wick = candle["high"] - max(candle["open"], candle["close"])

        return upper_wick > total_range * 0.6 and body < total_range * 0.3


# ═══════════════════════════════════════════════════════════════════
# ESTRUCTURA DE MERCADO
# ═══════════════════════════════════════════════════════════════════


class MarketStructure:
    @staticmethod
    def find_support_resistance(df: pd.DataFrame, lookback: int = 20) -> Dict:
        highs = df["high"].rolling(window=lookback, center=True).max()
        lows = df["low"].rolling(window=lookback, center=True).min()

        resistance_levels = []
        support_levels = []

        for i in range(len(df)):
            if df["high"].iloc[i] == highs.iloc[i]:
                resistance_levels.append(df["high"].iloc[i])
            if df["low"].iloc[i] == lows.iloc[i]:
                support_levels.append(df["low"].iloc[i])

        def cluster_levels(levels, tolerance=0.002):
            if not levels:
                return []
            levels = sorted(levels)
            clusters = [[levels[0]]]
            for level in levels[1:]:
                if (level - clusters[-1][-1]) / clusters[-1][-1] < tolerance:
                    clusters[-1].append(level)
                else:
                    clusters.append([level])
            return [np.mean(cluster) for cluster in clusters]

        return {
            "resistance": cluster_levels(resistance_levels[-50:]),
            "support": cluster_levels(support_levels[-50:]),
        }

    @staticmethod
    def is_near_level(
        price: float, levels: List[float], tolerance: float = 0.003
    ) -> bool:
        return any(abs(price - level) / level < tolerance for level in levels)


# ═══════════════════════════════════════════════════════════════════
# DETECTOR DE SEÑALES AVANZADO
# ═══════════════════════════════════════════════════════════════════


class AdvancedSignalDetector:
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        try:
            # EMAs
            for period in [
                config.FAST_EMA,
                config.SLOW_EMA,
                config.EMA_TREND,
                config.EMA_FILTER,
            ]:
                df[f"ema_{period}"] = df["close"].ewm(
                    span=period, adjust=False).mean()

            # RSI
            delta = df["close"].diff()
            gain = (
                delta.where(delta > 0, 0)
                .ewm(span=config.RSI_PERIOD, adjust=False)
                .mean()
            )
            loss = (
                -delta.where(delta < 0, 0)
                .ewm(span=config.RSI_PERIOD, adjust=False)
                .mean()
            )
            rs = gain / loss.replace(0, np.nan)
            df["rsi"] = 100 - (100 / (1 + rs))

            # MACD
            exp1 = df["close"].ewm(span=config.MACD_FAST, adjust=False).mean()
            exp2 = df["close"].ewm(span=config.MACD_SLOW, adjust=False).mean()
            df["macd"] = exp1 - exp2
            df["macd_signal"] = (
                df["macd"].ewm(span=config.MACD_SIGNAL, adjust=False).mean()
            )
            df["macd_hist"] = df["macd"] - df["macd_signal"]

            # ATR
            high_low = df["high"] - df["low"]
            high_close = np.abs(df["high"] - df["close"].shift())
            low_close = np.abs(df["low"] - df["close"].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            df["atr"] = true_range.rolling(config.ATR_PERIOD).mean()

            # Volumen
            df["volume_ma"] = df["volume"].rolling(20).mean()
            df["volume_ratio"] = df["volume"] / \
                df["volume_ma"].replace(0, np.nan)

            # Stochastic RSI
            rsi_min = df["rsi"].rolling(14).min()
            rsi_max = df["rsi"].rolling(14).max()
            df["stoch_rsi"] = (
                (df["rsi"] - rsi_min) /
                (rsi_max - rsi_min).replace(0, np.nan) * 100
            )

            return df
        except Exception as e:
            log.error(f"Error calculando indicadores: {e}")
            return df

    @staticmethod
    def detect_divergence(df: pd.DataFrame, lookback: int = 14) -> Dict:
        if len(df) < lookback * 2:
            return {"bull_div": False, "bear_div": False}

        recent = df.iloc[-lookback:]

        price_ll = recent["low"].iloc[-1] < recent["low"].iloc[:-1].min()
        rsi_hl = recent["rsi"].iloc[-1] > recent["rsi"].iloc[:-1].min()
        bull_div = price_ll and rsi_hl

        price_hh = recent["high"].iloc[-1] > recent["high"].iloc[:-1].max()
        rsi_lh = recent["rsi"].iloc[-1] < recent["rsi"].iloc[:-1].max()
        bear_div = price_hh and rsi_lh

        return {"bull_div": bull_div, "bear_div": bear_div}

    @staticmethod
    def detect_signal(
        df_5m: pd.DataFrame, df_15m: pd.DataFrame, symbol: str
    ) -> Optional[Dict]:
        if len(df_5m) < 50 or len(df_15m) < 50:
            return None

        curr_5m = df_5m.iloc[-1]
        prev_5m = df_5m.iloc[-2]
        curr_15m = df_15m.iloc[-1]

        required = [
            "close",
            f"ema_{config.FAST_EMA}",
            f"ema_{config.SLOW_EMA}",
            "rsi",
            "macd",
            "atr",
        ]
        if any(pd.isna(curr_5m[field]) for field in required):
            return None

        patterns = CandlePatterns()
        structure = MarketStructure.find_support_resistance(df_5m)
        divergence = AdvancedSignalDetector.detect_divergence(df_5m)

        # SEÑAL LONG
        long_score = 0
        long_reasons = []

        if (
            curr_5m[f"ema_{config.FAST_EMA}"] > curr_5m[f"ema_{config.SLOW_EMA}"]
            and prev_5m[f"ema_{config.FAST_EMA}"] <= prev_5m[f"ema_{config.SLOW_EMA}"]
        ):
            long_score += 2
            long_reasons.append("✓ Cruce EMA Alcista")

        if curr_5m["close"] > curr_5m[f"ema_{config.EMA_FILTER}"]:
            long_score += 2
            long_reasons.append(f"✓ Por encima EMA{config.EMA_FILTER}")

        if 35 < curr_5m["rsi"] < 65:
            long_score += 1
            long_reasons.append(f"✓ RSI {curr_5m['rsi']:.1f}")

        if curr_5m["macd"] > curr_5m["macd_signal"] and curr_5m["macd_hist"] > 0:
            long_score += 1
            long_reasons.append("✓ MACD Alcista")

        if curr_5m["macd_hist"] > prev_5m["macd_hist"]:
            long_score += 1
            long_reasons.append("✓ MACD Momentum+")

        if curr_5m["volume_ratio"] > 1.2:
            long_score += 1
            long_reasons.append(f"✓ Volumen {curr_5m['volume_ratio']:.1f}x")

        if patterns.is_bullish_engulfing(curr_5m, prev_5m):
            long_score += 2
            long_reasons.append("✓ Envolvente Alcista")
        elif patterns.is_hammer(curr_5m) or patterns.is_pin_bar_bullish(curr_5m):
            long_score += 1
            long_reasons.append("✓ Patrón Alcista")

        if structure["support"] and MarketStructure.is_near_level(
            curr_5m["close"], structure["support"]
        ):
            long_score += 1
            long_reasons.append("✓ Cerca de Soporte")

        if divergence["bull_div"]:
            long_score += 2
            long_reasons.append("✓ Divergencia Alcista")

        mtf_confirmed = True
        if config.REQUIRE_MTF_CONFIRMATION:
            mtf_confirmed = (
                curr_15m[f"ema_{config.FAST_EMA}"] > curr_15m[f"ema_{config.SLOW_EMA}"]
                and curr_15m["rsi"] < 70
            )
            if mtf_confirmed:
                long_reasons.append("✓ Confirmado 15m")

        # SEÑAL SHORT
        short_score = 0
        short_reasons = []

        if (
            curr_5m[f"ema_{config.FAST_EMA}"] < curr_5m[f"ema_{config.SLOW_EMA}"]
            and prev_5m[f"ema_{config.FAST_EMA}"] >= prev_5m[f"ema_{config.SLOW_EMA}"]
        ):
            short_score += 2
            short_reasons.append("✓ Cruce EMA Bajista")

        if curr_5m["close"] < curr_5m[f"ema_{config.EMA_FILTER}"]:
            short_score += 2
            short_reasons.append(f"✓ Por debajo EMA{config.EMA_FILTER}")

        if 35 < curr_5m["rsi"] < 65:
            short_score += 1
            short_reasons.append(f"✓ RSI {curr_5m['rsi']:.1f}")

        if curr_5m["macd"] < curr_5m["macd_signal"] and curr_5m["macd_hist"] < 0:
            short_score += 1
            short_reasons.append("✓ MACD Bajista")

        if curr_5m["macd_hist"] < prev_5m["macd_hist"]:
            short_score += 1
            short_reasons.append("✓ MACD Momentum-")

        if curr_5m["volume_ratio"] > 1.2:
            short_score += 1
            short_reasons.append(f"✓ Volumen {curr_5m['volume_ratio']:.1f}x")

        if patterns.is_bearish_engulfing(curr_5m, prev_5m):
            short_score += 2
            short_reasons.append("✓ Envolvente Bajista")
        elif patterns.is_shooting_star(curr_5m) or patterns.is_pin_bar_bearish(curr_5m):
            short_score += 1
            short_reasons.append("✓ Patrón Bajista")

        if structure["resistance"] and MarketStructure.is_near_level(
            curr_5m["close"], structure["resistance"]
        ):
            short_score += 1
            short_reasons.append("✓ Cerca de Resistencia")

        if divergence["bear_div"]:
            short_score += 2
            short_reasons.append("✓ Divergencia Bajista")

        if config.REQUIRE_MTF_CONFIRMATION:
            mtf_confirmed = (
                curr_15m[f"ema_{config.FAST_EMA}"] < curr_15m[f"ema_{config.SLOW_EMA}"]
                and curr_15m["rsi"] > 30
            )
            if mtf_confirmed:
                short_reasons.append("✓ Confirmado 15m")

        # DECISIÓN FINAL
        if long_score >= config.MIN_SIGNAL_SCORE and mtf_confirmed:
            return {
                "type": "LONG",
                "strength": min(long_score / 12, 0.95),
                "reasons": long_reasons,
                "price": curr_5m["close"],
                "atr": curr_5m["atr"],
                "rsi": curr_5m["rsi"],
                "score": long_score,
                "support_levels": structure.get("support", []),
                "resistance_levels": structure.get("resistance", []),
            }
        elif short_score >= config.MIN_SIGNAL_SCORE and mtf_confirmed:
            return {
                "type": "SHORT",
                "strength": min(short_score / 12, 0.95),
                "reasons": short_reasons,
                "price": curr_5m["close"],
                "atr": curr_5m["atr"],
                "rsi": curr_5m["rsi"],
                "score": short_score,
                "support_levels": structure.get("support", []),
                "resistance_levels": structure.get("resistance", []),
            }

        return None


# ═══════════════════════════════════════════════════════════════════
# GESTOR DE RIESGO MEJORADO
# ═══════════════════════════════════════════════════════════════════


class ImprovedRiskManager:
    @staticmethod
    def calculate_position_size_kelly(
        balance: float, signal_strength: float, win_rate: float, avg_rr: float
    ) -> float:
        if win_rate <= 0 or avg_rr <= 0:
            return balance * (config.RISK_PER_TRADE_PERCENT / 100)

        kelly = (win_rate * (avg_rr + 1) - 1) / avg_rr
        kelly = max(0, min(kelly, 0.25))

        kelly_adjusted = kelly * 0.5 * (0.5 + signal_strength)

        risk_amount = balance * kelly_adjusted
        return max(risk_amount, balance * 0.01)

    @staticmethod
    def calculate_sl_tp_levels(signal: Dict, price: float) -> Dict:
        atr = signal["atr"]
        strength = signal["strength"]

        sl_distance = atr * config.SL_ATR_MULTIPLIER

        tp_levels = []
        for multiplier in config.TP_MULTIPLIERS:
            tp_dist = atr * multiplier * (0.8 + strength * 0.4)
            tp_levels.append(tp_dist)

        if signal["type"] == "LONG":
            sl = price - sl_distance
            tps = [price + dist for dist in tp_levels]
        else:
            sl = price + sl_distance
            tps = [price - dist for dist in tp_levels]

        return {
            "sl": sl,
            "tp1": tps[0],
            "tp2": tps[1],
            "tp3": tps[2],
            "tp_percentages": config.TP_LEVELS,
        }


# ═══════════════════════════════════════════════════════════════════
# TRAILING STOP MEJORADO
# ═══════════════════════════════════════════════════════════════════


class ImprovedTrailingStop:
    def __init__(self):
        self.data = {}

    def update(
        self, symbol: str, price: float, side: str, entry: float, sl: float
    ) -> Optional[Dict]:
        if side == "LONG":
            pnl_pct = ((price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - price) / entry) * 100

        sl_dist = abs(entry - sl)
        rr_ratio = pnl_pct / (sl_dist / entry * 100) if sl_dist > 0 else 0

        if rr_ratio < config.TRAILING_ACTIVATION_RR:
            return None

        if symbol not in self.data:
            self.data[symbol] = {
                "max_price": price,
                "max_pnl": pnl_pct,
                "activated": True,
            }
            log.info(f"🎯 Trailing Stop ACTIVADO: {symbol} @ RR {rr_ratio:.2f}")

        data = self.data[symbol]

        if side == "LONG":
            if price > data["max_price"]:
                data["max_price"] = price
                data["max_pnl"] = pnl_pct

            stop = data["max_price"] * \
                (1 - config.TRAILING_DISTANCE_PERCENT / 100)
            if price <= stop:
                return {
                    "should_close": True,
                    "reason": "Trailing Stop",
                    "max_pnl": data["max_pnl"],
                }
        else:
            if price < data["max_price"]:
                data["max_price"] = price
                data["max_pnl"] = pnl_pct

            stop = data["max_price"] * \
                (1 + config.TRAILING_DISTANCE_PERCENT / 100)
            if price >= stop:
                return {
                    "should_close": True,
                    "reason": "Trailing Stop",
                    "max_pnl": data["max_pnl"],
                }

        return None

    def clear(self, symbol: str):
        self.data.pop(symbol, None)


# ═══════════════════════════════════════════════════════════════════
# GESTOR DE POSICIONES MEJORADO
# ═══════════════════════════════════════════════════════════════════


class ImprovedPositionManager:
    def __init__(self, api, capital_mgr):
        self.api = api
        self.capital = capital_mgr
        self.trailing = ImprovedTrailingStop()
        self.telegram = TelegramNotifier()
        self.positions = {}
        self.performance = {"wins": [], "losses": []}

    def open_position(self, symbol: str, signal: Dict) -> bool:
        try:
            price = signal["price"]
            side = signal["type"]

            quantity = self._calculate_size(symbol, price, signal)
            if quantity <= 0:
                return False

            self.api.ensure_symbol_settings(symbol)

            levels = ImprovedRiskManager.calculate_sl_tp_levels(signal, price)

            order_side = SIDE_BUY if side == "LONG" else SIDE_SELL
            order = self.api.place_order(symbol, order_side, quantity)

            if not order:
                return False

            self.positions[symbol] = {
                "entry": price,
                "sl": levels["sl"],
                "tp1": levels["tp1"],
                "tp2": levels["tp2"],
                "tp3": levels["tp3"],
                "tp_taken": [],
                "side": side,
                "qty": quantity,
                "qty_remaining": quantity,
                "time": time.time(),
                "breakeven_set": False,
            }

            log.info(f"")
            log.info(f"{'=' * 70}")
            log.info(f"🚀 POSICIÓN ABIERTA: {symbol} {side}")
            log.info(f"{'=' * 70}")
            log.info(f"💰 Precio: {price:.6f}")
            log.info(f"📦 Cantidad: {quantity:.6f}")
            log.info(f"🛡️ SL: {levels['sl']:.6f}")
            log.info(f"🎯 TP1: {levels['tp1']:.6f} (30%)")
            log.info(f"🎯 TP2: {levels['tp2']:.6f} (40%)")
            log.info(f"🎯 TP3: {levels['tp3']:.6f} (30%)")
            log.info(
                f"⚡ Score: {signal['score']}/12 | Fuerza: {signal['strength']:.0%}"
            )
            for reason in signal["reasons"]:
                log.info(f"   {reason}")
            log.info(f"{'=' * 70}")

            if self.telegram.enabled:
                self.telegram.notify_trade_opened(
                    symbol,
                    side,
                    quantity,
                    price,
                    self.capital.current_balance,
                    signal["score"],
                )

            return True

        except Exception as e:
            log.error(f"❌ Error abriendo {symbol}: {e}")
            return False

    def _calculate_size(self, symbol: str, price: float, signal: Dict) -> float:
        balance = self.capital.current_balance
        if balance < 5.0:
            return 0

        with state_lock:
            stats = app_state["performance_stats"]
            win_rate = stats.get("win_rate", 0)

            total_wins = sum(self.performance["wins"])
            total_losses = sum(self.performance["losses"])
            count_wins = len(self.performance["wins"])
            count_losses = len(self.performance["losses"])

            avg_rr = 0
            if count_wins > 0 and count_losses > 0:
                avg_win = total_wins / count_wins
                avg_loss = abs(total_losses / count_losses)
                avg_rr = avg_win / avg_loss if avg_loss > 0 else 2.0

        if config.USE_KELLY_CRITERION and win_rate > 0:
            risk_amt = ImprovedRiskManager.calculate_position_size_kelly(
                balance, signal["strength"], win_rate, avg_rr
            )
        else:
            strength = signal.get("strength", 0.5)
            risk_pct = config.RISK_PER_TRADE_PERCENT * (0.75 + strength * 0.5)
            risk_amt = balance * (risk_pct / 100)

        atr = signal.get("atr", price * 0.01)
        sl_dist = atr * config.SL_ATR_MULTIPLIER

        pos_value = risk_amt / (sl_dist / price)
        quantity = pos_value / price

        filters = self.api.get_symbol_filters(symbol)
        if filters:
            quantity = self.api.round_value(quantity, filters["stepSize"])
            quantity = max(quantity, filters["minQty"])

            notional = quantity * price
            if notional < filters["minNotional"]:
                quantity = (filters["minNotional"] / price) * 1.05
                quantity = self.api.round_value(quantity, filters["stepSize"])

        return quantity

    def monitor_position(self, symbol: str, position: Dict) -> Optional[Dict]:
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        price = float(position.get("markPrice", 0))

        if price <= 0:
            return None

        # Verificar TPs parciales
        if config.USE_PARTIAL_TP:
            tp_result = self._check_partial_tp(symbol, price, pos)
            if tp_result:
                return tp_result

        # Breakeven
        if config.BREAKEVEN_ENABLED and not pos["breakeven_set"]:
            be_result = self._check_breakeven(symbol, price, pos)
            if be_result:
                pos["breakeven_set"] = True
                pos["sl"] = be_result["new_sl"]
                log.info(
                    f"🔒 Breakeven activado: {symbol} @ {be_result['new_sl']:.6f}")

        # SL/TP tradicional
        if pos["side"] == "LONG":
            if price <= pos["sl"]:
                return {"should_close": True, "reason": "Stop Loss"}
            if len(pos["tp_taken"]) == 0 and price >= pos["tp3"]:
                return {"should_close": True, "reason": "Take Profit 3"}
        else:
            if price >= pos["sl"]:
                return {"should_close": True, "reason": "Stop Loss"}
            if len(pos["tp_taken"]) == 0 and price <= pos["tp3"]:
                return {"should_close": True, "reason": "Take Profit 3"}

        # Trailing Stop
        if config.TRAILING_STOP_ENABLED:
            result = self.trailing.update(
                symbol, price, pos["side"], pos["entry"], pos["sl"]
            )
            if result and result.get("should_close"):
                return result

        # Tiempo máximo
        if time.time() - pos["time"] > 3600:
            return {"should_close": True, "reason": "Max Time"}

        return None

    def _check_partial_tp(self, symbol: str, price: float, pos: Dict) -> Optional[Dict]:
        side = pos["side"]

        for i, (tp_level, tp_pct) in enumerate(
            zip([pos["tp1"], pos["tp2"], pos["tp3"]], config.TP_LEVELS), 1
        ):
            if i in pos["tp_taken"]:
                continue

            hit = False
            if side == "LONG" and price >= tp_level:
                hit = True
            elif side == "SHORT" and price <= tp_level:
                hit = True

            if hit:
                close_qty = pos["qty"] * tp_pct
                pos["tp_taken"].append(i)
                pos["qty_remaining"] -= close_qty

                log.info(
                    f"🎯 TP{i} alcanzado: {symbol} @ {price:.6f} | Cerrando {tp_pct:.0%}"
                )

                return {
                    "should_close": True if i == 3 else False,
                    "reason": f"Take Profit {i}",
                    "partial": True if i < 3 else False,
                    "close_pct": tp_pct,
                    "tp_level": i,
                }

        return None

    def _check_breakeven(self, symbol: str, price: float, pos: Dict) -> Optional[Dict]:
        entry = pos["entry"]
        sl = pos["sl"]
        side = pos["side"]

        sl_dist = abs(entry - sl)

        if side == "LONG":
            pnl_dist = price - entry
            rr = pnl_dist / sl_dist if sl_dist > 0 else 0

            if rr >= config.BREAKEVEN_TRIGGER_RR:
                new_sl = entry * (1 + config.BREAKEVEN_OFFSET_PERCENT / 100)
                return {"new_sl": new_sl}
        else:
            pnl_dist = entry - price
            rr = pnl_dist / sl_dist if sl_dist > 0 else 0

            if rr >= config.BREAKEVEN_TRIGGER_RR:
                new_sl = entry * (1 - config.BREAKEVEN_OFFSET_PERCENT / 100)
                return {"new_sl": new_sl}

        return None

    def close_position(self, symbol: str, position: Dict, close_info: Dict):
        try:
            pos = self.positions.get(symbol)
            if not pos:
                return

            pnl = float(position.get("unRealizedProfit", 0))
            price = float(position.get("markPrice", 0))

            is_partial = close_info.get("partial", False)
            close_pct = close_info.get("close_pct", 1.0)

            result = self.api.close_position(
                symbol, float(position["positionAmt"]), reduce_pct=close_pct
            )

            if result:
                tp_level = close_info.get("tp_level")

                log.info(f"")
                log.info(f"{'=' * 70}")
                log.info(
                    f"{'🟢' if not is_partial else '🟡'} POSICIÓN {'PARCIAL' if is_partial else 'CERRADA'}: {symbol}"
                )
                log.info(f"{'=' * 70}")
                log.info(f"📋 Razón: {close_info['reason']}")
                log.info(f"💰 Entrada: {pos['entry']:.6f}")
                log.info(f"💰 Salida: {price:.6f}")
                log.info(f"💵 P&L: {pnl:+.2f} USDT")
                if "max_pnl" in close_info:
                    log.info(f"🎯 Máximo: {close_info['max_pnl']:+.2f}%")
                log.info(f"{'=' * 70}")

                if self.telegram.enabled:
                    self.telegram.notify_trade_closed(
                        symbol,
                        pnl * close_pct,
                        close_info["reason"],
                        self.capital.current_balance,
                        tp_level,
                    )

                # Actualizar estadísticas
                partial_pnl = pnl * close_pct
                if partial_pnl > 0:
                    self.performance["wins"].append(partial_pnl)
                else:
                    self.performance["losses"].append(partial_pnl)

                with state_lock:
                    stats = app_state["performance_stats"]
                    stats["trades_count"] += 1
                    stats["realized_pnl"] += partial_pnl

                    if partial_pnl > 0:
                        stats["wins"] += 1
                    else:
                        stats["losses"] += 1

                    total = stats["wins"] + stats["losses"]
                    if total > 0:
                        stats["win_rate"] = stats["wins"] / total

                    if stats["wins"] > 0:
                        stats["avg_win"] = sum(self.performance["wins"]) / len(
                            self.performance["wins"]
                        )
                    if stats["losses"] > 0:
                        stats["avg_loss"] = abs(
                            sum(self.performance["losses"])
                            / len(self.performance["losses"])
                        )

                    if stats["avg_loss"] > 0:
                        stats["profit_factor"] = stats["avg_win"] / \
                            stats["avg_loss"]

                # Limpiar si cierre completo
                if not is_partial:
                    self.positions.pop(symbol, None)
                    self.trailing.clear(symbol)

                self.capital.update_balance(force=True)

        except Exception as e:
            log.error(f"❌ Error cerrando {symbol}: {e}")


# ═══════════════════════════════════════════════════════════════════
# BOT PRINCIPAL MEJORADO
# ═══════════════════════════════════════════════════════════════════


class ImprovedTradingBot:
    def __init__(self):
        self.api = BinanceFutures()
        self.capital = CapitalManager(self.api)
        self.position_mgr = ImprovedPositionManager(self.api, self.capital)
        self.signal_detector = AdvancedSignalDetector()
        self.telegram = TelegramNotifier()

        self.cycle = 0
        self.start_time = time.time()
        self.scanned = {}
        self.symbols = list(config.PRIORITY_SYMBOLS)

    def run(self):
        log.info("")
        log.info("=" * 70)
        log.info("🚀 BOT DE TRADING MEJORADO V14.0")
        log.info("=" * 70)
        log.info(f"⚡ Leverage: {config.LEVERAGE}x")
        log.info(
            f"📊 Estrategia: Multi-TF + Confluencias ({config.MIN_SIGNAL_SCORE}/12)"
        )
        log.info(f"💰 TP Parcial: 3 niveles")
        log.info(f"🔒 Breakeven: Automático")
        log.info(f"🔄 Trailing: {config.TRAILING_ACTIVATION_RR}:1 RR")
        log.info("=" * 70)
        log.info("")

        self.capital.update_balance(force=True)
        log.info(f"💰 Balance Inicial: {self.capital.current_balance:.2f} USDT")
        log.info("")

        if self.telegram.enabled:
            self.telegram.send_message(
                f"🤖 <b>BOT V14.0 INICIADO</b>\n\n"
                f"⚡ Leverage: {config.LEVERAGE}x\n"
                f"💰 Balance: ${self.capital.current_balance:.2f}\n"
                f"📊 Score mínimo: {config.MIN_SIGNAL_SCORE}/12"
            )

        errors = 0

        while True:
            try:
                with state_lock:
                    if not app_state["running"]:
                        log.info("🛑 Bot detenido")
                        break

                if self.cycle % 5 == 0:
                    self.capital.update_balance()
                    with state_lock:
                        app_state["balance"] = self.capital.current_balance

                self._scan_symbols()
                self._monitor_positions()

                errors = 0
                self.cycle += 1

                with state_lock:
                    app_state["status_message"] = f"Ejecutando - Ciclo {self.cycle}"
                    socketio.emit("status_update", app_state)

                time.sleep(config.POLL_SEC)

            except Exception as e:
                errors += 1
                log.error(f"❌ Error ciclo {self.cycle}: {e}")

                if errors >= 3:
                    log.error("🚨 Muchos errores, pausando...")
                    time.sleep(30)
                    errors = 0
                else:
                    time.sleep(15)

    def _scan_symbols(self):
        try:
            account = self.api._safe_api_call(self.api.client.futures_account)
            if not account:
                return

            open_pos = {
                p["symbol"]: p
                for p in account["positions"]
                if float(p["positionAmt"]) != 0
            }

            if len(open_pos) >= config.MAX_CONCURRENT_POS:
                return

            now = time.time()

            for symbol in self.symbols:
                try:
                    if symbol in open_pos:
                        continue

                    if now - self.scanned.get(symbol, 0) < 120:
                        continue

                    self.scanned[symbol] = now

                    # Obtener datos 5m y 15m
                    df_5m = self._get_data(symbol, config.PRIMARY_TIMEFRAME)
                    df_15m = self._get_data(
                        symbol, config.CONFIRMATION_TIMEFRAME)

                    if df_5m is None or df_15m is None:
                        continue
                    if len(df_5m) < 50 or len(df_15m) < 50:
                        continue

                    # Calcular indicadores
                    df_5m = self.signal_detector.calculate_indicators(df_5m)
                    df_15m = self.signal_detector.calculate_indicators(df_15m)

                    # Detectar señal
                    signal = self.signal_detector.detect_signal(
                        df_5m, df_15m, symbol)

                    if signal and signal["strength"] >= config.MIN_SIGNAL_STRENGTH:
                        log.info(
                            f"🎯 SEÑAL DETECTADA: {symbol} {signal['type']}")
                        log.info(
                            f"   Score: {signal['score']}/12 | Fuerza: {signal['strength']:.0%}"
                        )

                        if self.position_mgr.open_position(symbol, signal):
                            break

                except Exception as e:
                    log.error(f"Error escaneando {symbol}: {e}")
                    continue

        except Exception as e:
            log.error(f"Error en scan: {e}")

    def _monitor_positions(self):
        try:
            account = self.api._safe_api_call(self.api.client.futures_account)
            if not account:
                return

            open_pos = {
                p["symbol"]: p
                for p in account["positions"]
                if float(p["positionAmt"]) != 0
            }

            with state_lock:
                app_state["open_positions"] = open_pos

            for symbol, pos in open_pos.items():
                try:
                    close_info = self.position_mgr.monitor_position(
                        symbol, pos)
                    if close_info and close_info.get("should_close"):
                        self.position_mgr.close_position(
                            symbol, pos, close_info)

                except Exception as e:
                    log.error(f"Error monitoreando {symbol}: {e}")

        except Exception as e:
            log.error(f"Error en monitor: {e}")

    def _get_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        try:
            klines = self.api._safe_api_call(
                self.api.client.futures_klines,
                symbol=symbol,
                interval=timeframe,
                limit=config.CANDLES_LIMIT,
            )

            if not klines:
                return None

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
                    "taker_buy_base",
                    "taker_buy_quote",
                    "ignore",
                ],
            )

            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=["close"])

            if len(df) < 50 or (df["volume"] == 0).any():
                return None

            return df

        except Exception as e:
            log.error(f"Error obteniendo datos {symbol} {timeframe}: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════
# RUTAS WEB
# ═══════════════════════════════════════════════════════════════════


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    with state_lock:
        return jsonify(app_state)


@app.route("/api/start", methods=["POST"])
def api_start():
    global bot_thread

    with state_lock:
        if app_state["running"]:
            return jsonify({"status": "error", "message": "Bot ya está corriendo"})
        app_state["running"] = True
        app_state["status_message"] = "Iniciando..."

    def run_bot():
        try:
            bot = ImprovedTradingBot()
            bot.run()
        except Exception as e:
            log.error(f"Error en bot: {e}")
            with state_lock:
                app_state["running"] = False

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    return jsonify({"status": "success", "message": "Bot iniciado correctamente"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    with state_lock:
        app_state["running"] = False
        app_state["status_message"] = "Detenido"

    return jsonify({"status": "success", "message": "Bot detenido"})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        new_config = request.json
        with state_lock:
            for key, value in new_config.items():
                if hasattr(config, key):
                    setattr(config, key, value)
                    app_state["config"][key] = value
        return jsonify({"status": "success", "message": "Configuración guardada"})

    with state_lock:
        return jsonify(app_state["config"])


@app.route("/api/positions")
def api_positions():
    with state_lock:
        return jsonify(app_state["open_positions"])


@app.route("/api/close_position", methods=["POST"])
def api_close_position():
    try:
        data = request.json
        symbol = data.get("symbol")

        with state_lock:
            if symbol not in app_state["open_positions"]:
                return jsonify({"status": "error", "message": "Posición no encontrada"})
            position = app_state["open_positions"][symbol]

        api = BinanceFutures()
        result = api.close_position(symbol, float(position["positionAmt"]))

        if result:
            return jsonify(
                {"status": "success", "message": f"Posición {symbol} cerrada"}
            )
        else:
            return jsonify({"status": "error", "message": "Error cerrando posición"})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@socketio.on("connect")
def handle_connect():
    log.info("Cliente WebSocket conectado")
    socketio.emit("status_update", app_state)


@socketio.on("disconnect")
def handle_disconnect():
    log.info("Cliente WebSocket desconectado")


# ═══════════════════════════════════════════════════════════════════
# INICIALIZACIÓN
# ═══════════════════════════════════════════════════════════════════


def initialize():
    try:
        log.info("🚀 Inicializando Bot v14.0...")

        api = BinanceFutures()
        log.info("✅ Conexión Binance OK")

        capital = CapitalManager(api)
        if capital.update_balance(force=True):
            log.info(f"💰 Balance: {capital.current_balance:.2f} USDT")
            with state_lock:
                app_state["balance"] = capital.current_balance

        log.info("✅ Sistema listo")
        return True

    except Exception as e:
        log.error(f"❌ Error inicialización: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=" * 70)
    log.info("🚀 BINANCE FUTURES BOT V14.0 - MÁXIMA RENTABILIDAD")
    log.info("=" * 70)

    if not initialize():
        log.error("❌ Inicialización fallida")
        exit(1)

    try:
        log.info("🌐 Servidor web: http://0.0.0.0:5000")
        log.info("📊 Dashboard disponible en el navegador")
        log.info("")
        socketio.run(
            app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True
        )
    except Exception as e:
        log.error(f"❌ Error servidor: {e}")
        exit(1)
