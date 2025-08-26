from __future__ import annotations

"""
Binance Futures Bot – Versión 10.1 - Edición Profesional
------------------------------------------------------------------------------------
Descripción:
Versión refactorizada con una interfaz web profesional, correcciones de errores críticos
y nuevas funcionalidades para una gestión avanzada.
- REPARADO: KeyError por 'unRealizedProfit' vs 'unrealizedProfit'.
- REPARADO: AttributeError por 'MAX_CONCURRENT_POS' faltante.
- REPARADO: Cálculo de cantidad para evitar órdenes de tamaño 0.0.
- MEJORADO: Interfaz web completamente rediseñada (HTML/CSS/JS).
- AÑADIDO: Panel de configuración global en la web (Leverage, Margin, etc.).
- AÑADIDO: Seguimiento de P&L Realizado de trades cerrados.
- AÑADIDO: Modales de confirmación y notificaciones 'toast' en el frontend.
"""
import logging
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import pandas as pd
from binance.client import Client
from binance.enums import (
    FUTURE_ORDER_TYPE_LIMIT,
    FUTURE_ORDER_TYPE_MARKET,
    SIDE_BUY,
    SIDE_SELL,
    TIME_IN_FORCE_GTC,
)
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_socketio import SocketIO


# -------------------- CONFIGURACIÓN -------------------- #
@dataclass
class CONFIG:
    # --- Configuración Global (Editable desde la web) ---
    LEVERAGE: int = 20
    MAX_CONCURRENT_POS: int = 10
    FIXED_MARGIN_PER_TRADE_USDT: float = (
        2.0  # Aumentado para evitar errores de cantidad mínima
    )
    NUM_SYMBOLS_TO_SCAN: int = 150
    # --- Configuración de Estrategia (Editable desde la web) ---
    ATR_MULT_SL: float = 2.0
    ATR_MULT_TP: float = 3.0
    # --- Configuración Fija ---
    MARGIN_TYPE: str = "CROSSED"
    MIN_24H_VOLUME: float = 20_000_000
    EXCLUDE_SYMBOLS: tuple = ("BTCDOMUSDT", "DEFIUSDT", "USDCUSDT", "TUSDUSDT")
    TIMEFRAME: str = "5m"
    CANDLES_LIMIT: int = 100
    FAST_EMA: int = 9
    SLOW_EMA: int = 21
    RSI_PERIOD: int = 14
    POLL_SEC: float = 10.0
    DRY_RUN: bool = False
    MAX_WORKERS_KLINE: int = 20
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "bot_v10.log"
    LOG_FORMAT: str = "%(asctime)s - %(levelname)s - %(message)s"
    SIGNAL_COOLDOWN_CYCLES: int = 30


config = CONFIG()

# -------------------- SERVIDOR WEB Y LOGGING -------------------- #
app = Flask(__name__, template_folder=".")
CORS(app)
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")


class SocketIOHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            level = record.levelname.lower()
            socketio.emit("log_update", {"message": log_entry, "level": level})
        except Exception:
            pass


log = logging.getLogger("BinanceFuturesBot")
log.setLevel(getattr(logging, config.LOG_LEVEL))
if not log.handlers:
    formatter = logging.Formatter(config.LOG_FORMAT)
    file_handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8", mode="a")
    file_handler.setFormatter(formatter)
    socket_handler = SocketIOHandler()
    socket_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    log.addHandler(socket_handler)
    log.addHandler(console_handler)

for logger_name in ["binance", "engineio", "socketio", "werkzeug", "urllib3"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# -------------------- ESTADO GLOBAL -------------------- #
bot_thread = None
app_state = {
    "running": False,
    "status_message": "Detenido",
    "open_positions": {},
    "config": asdict(config),
    "performance_stats": {"realized_pnl": 0.0, "trades_count": 0},
    "balance": 0.0,
    "total_investment_usd": 0.0,
}
state_lock = threading.Lock()


# -------------------- CLIENTE BINANCE -------------------- #
class BinanceFutures:
    def __init__(self):
        load_dotenv()
        api_key, api_secret = (
            os.getenv("BINANCE_API_KEY"),
            os.getenv("BINANCE_API_SECRET"),
        )
        if not api_key or not api_secret:
            raise ValueError("API keys no configuradas en .env")
        self.client = Client(api_key, api_secret, testnet=True)
        log.info("🔧 CONECTADO A BINANCE FUTURES TESTNET")
        try:
            self.exchange_info = self.client.futures_exchange_info()
            log.info("✅ Información de intercambio cargada correctamente")
        except Exception as e:
            log.error(f"❌ Error conectando a Binance: {e}")
            raise

    def _safe_api_call(self, func, *args, **kwargs):
        for attempt in range(3):
            try:
                time.sleep(0.1)
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                if e.code == -4131:
                    log.warning(
                        f"Error PERCENT_PRICE (-4131) en orden. Mercado volátil o ilíquido. Omitiendo."
                    )
                    return None
                log.warning(f"API non-critical error: {e.message}")
                if attempt == 2:
                    log.error(f"Error final de API: {e.code} - {e.message}")
                time.sleep(1 * (attempt + 1))
            except Exception as e:
                log.warning(f"Error general en llamada API: {e}")
                if attempt == 2:
                    log.error(f"Error general final: {e}")
                time.sleep(1 * (attempt + 1))
        return None

    def get_symbol_filters(self, symbol: str) -> Optional[Dict[str, float]]:
        s_info = next(
            (s for s in self.exchange_info["symbols"] if s["symbol"] == symbol), None
        )
        if not s_info:
            return None
        filters = {f["filterType"]: f for f in s_info["filters"]}
        return {
            "stepSize": float(filters["LOT_SIZE"]["stepSize"]),
            "minQty": float(filters["LOT_SIZE"]["minQty"]),
            "tickSize": float(filters["PRICE_FILTER"]["tickSize"]),
            "minNotional": float(filters.get("MIN_NOTIONAL", {}).get("notional", 5.0)),
        }

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Optional[Dict]:
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
        }
        if order_type == FUTURE_ORDER_TYPE_LIMIT:
            if price is None:
                log.error("Precio requerido para órdenes LIMIT.")
                return None
            params.update({"price": str(price), "timeInForce": TIME_IN_FORCE_GTC})
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._safe_api_call(self.client.futures_create_order, **params)

    def close_position(self, symbol: str, position_amt: float) -> Optional[Dict]:
        side = SIDE_SELL if position_amt > 0 else SIDE_BUY
        return self.place_order(
            symbol, side, FUTURE_ORDER_TYPE_MARKET, abs(position_amt), reduce_only=True
        )

    @staticmethod
    def round_value(value: float, step: float) -> float:
        if step == 0:
            return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)


# -------------------- BOT PRINCIPAL Y ESTRATEGIA -------------------- #
class TradingBot:
    def __init__(self):
        self.api = BinanceFutures()
        self.recently_signaled = set()
        self.cycle_count = 0

    def get_top_symbols(self) -> List[str]:
        tickers = self.api._safe_api_call(self.api.client.futures_ticker)
        if not tickers:
            return []
        valid = [
            t
            for t in tickers
            if t["symbol"].endswith("USDT")
            and t["symbol"] not in config.EXCLUDE_SYMBOLS
            and float(t["quoteVolume"]) > config.MIN_24H_VOLUME
        ]
        return [
            t["symbol"]
            for t in sorted(valid, key=lambda x: float(x["quoteVolume"]), reverse=True)[
                : config.NUM_SYMBOLS_TO_SCAN
            ]
        ]

    def get_klines_for_symbol(self, symbol: str) -> Optional[pd.DataFrame]:
        klines = self.api._safe_api_call(
            self.api.client.futures_klines,
            symbol=symbol,
            interval=config.TIMEFRAME,
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
                "taker_buy_base_asset_volume",
                "taker_buy_quote_asset_volume",
                "ignore",
            ],
        )
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])
        return df

    def calculate_indicators(self, df: pd.DataFrame):
        df["fast_ema"] = df["close"].ewm(span=config.FAST_EMA, adjust=False).mean()
        df["slow_ema"] = df["close"].ewm(span=config.SLOW_EMA, adjust=False).mean()
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=config.RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=config.RSI_PERIOD).mean()
        df["rsi"] = 100 - (100 / (1 + (gain / loss)))

    def check_signal(self, df: pd.DataFrame) -> Optional[str]:
        last, prev = df.iloc[-1], df.iloc[-2]
        if (
            last["fast_ema"] > last["slow_ema"]
            and prev["fast_ema"] <= prev["slow_ema"]
            and last["rsi"] > 50
        ):
            return "LONG"
        if (
            last["fast_ema"] < last["slow_ema"]
            and prev["fast_ema"] >= prev["slow_ema"]
            and last["rsi"] < 50
        ):
            return "SHORT"
        return None

    def run(self):
        log.info(f"🚀 INICIANDO BOT DE TRADING v10 (DRY RUN: {config.DRY_RUN})")
        while True:
            with state_lock:
                if not app_state["running"]:
                    break
            try:
                self.cycle_count += 1
                log.info(f"--- 🔄 Nuevo ciclo de escaneo ({self.cycle_count}) ---")

                if (
                    self.cycle_count % config.SIGNAL_COOLDOWN_CYCLES == 1
                    and self.cycle_count > 1
                ):
                    log.info("🧹 Limpiando memoria de señales recientes (cooldown).")
                    self.recently_signaled.clear()

                account_info = self.api._safe_api_call(self.api.client.futures_account)
                if not account_info:
                    continue

                open_positions = {
                    p["symbol"]: p
                    for p in account_info["positions"]
                    if float(p["positionAmt"]) != 0
                }

                if open_positions:
                    # REPARADO: Se utiliza la clave correcta 'unrealizedProfit' en lugar de 'unRealizedProfit'.
                    socketio.emit(
                        "pnl_update",
                        {
                            p["symbol"]: float(p["unrealizedProfit"])
                            for p in open_positions.values()
                        },
                    )

                num_open_pos = len(open_positions)
                if num_open_pos < config.MAX_CONCURRENT_POS:
                    symbols_to_scan = [
                        s
                        for s in self.get_top_symbols()
                        if s not in open_positions and s not in self.recently_signaled
                    ]
                    log.info(
                        f"🔍 Escaneando {len(symbols_to_scan)} símbolos para nuevas señales."
                    )

                    with ThreadPoolExecutor(
                        max_workers=config.MAX_WORKERS_KLINE
                    ) as executor:
                        futures = {
                            executor.submit(self.get_klines_for_symbol, s): s
                            for s in symbols_to_scan
                        }
                        for future in futures:
                            symbol = futures[future]
                            df = future.result()
                            if df is None or len(df) < config.SLOW_EMA:
                                continue

                            self.calculate_indicators(df)
                            if signal := self.check_signal(df):
                                log.info(f"🔥 ¡Señal encontrada! {signal} en {symbol}")
                                self.recently_signaled.add(symbol)
                                self.open_trade(symbol, signal, df.iloc[-1])
                                if len(open_positions) + 1 >= config.MAX_CONCURRENT_POS:
                                    log.info(
                                        " Límite de posiciones concurrentes alcanzado."
                                    )
                                    break

                with state_lock:
                    app_state.update(
                        {
                            "status_message": "En ejecución",
                            "balance": next(
                                (
                                    float(a["walletBalance"])
                                    for a in account_info["assets"]
                                    if a["asset"] == "USDT"
                                ),
                                0.0,
                            ),
                            "open_positions": open_positions,
                            "total_investment_usd": sum(
                                float(p["initialMargin"])
                                for p in open_positions.values()
                            ),
                        }
                    )
                    socketio.emit("status_update", app_state)

            except Exception as e:
                log.error(f"Error en ciclo principal: {e}", exc_info=True)
            time.sleep(config.POLL_SEC)
        log.info("🛑 Bot detenido.")

    def open_trade(self, symbol: str, side: str, last_candle):
        if config.DRY_RUN:
            log.info(f"[DRY RUN] Abriría {side} en {symbol}")
            return

        filters = self.api.get_symbol_filters(symbol)
        if not filters:
            return

        price = last_candle["close"]
        quantity = (config.FIXED_MARGIN_PER_TRADE_USDT * config.LEVERAGE) / price
        quantity = self.api.round_value(quantity, filters["stepSize"])

        if quantity < filters["minQty"] or (quantity * price) < filters["minNotional"]:
            log.warning(
                f"Cantidad {quantity} para {symbol} es menor al mínimo permitido."
            )
            return

        order_side = SIDE_BUY if side == "LONG" else SIDE_SELL
        tick_size = filters["tickSize"]
        limit_price = price + tick_size * 5 if side == "LONG" else price - tick_size * 5
        limit_price = self.api.round_value(limit_price, tick_size)

        log.info(f"Intentando abrir orden LIMIT para {side} {symbol} @ {limit_price}")
        order = self.api.place_order(
            symbol, order_side, FUTURE_ORDER_TYPE_LIMIT, quantity, price=limit_price
        )

        if order and order.get("orderId"):
            log.info(
                f"✅ ORDEN LÍMITE CREADA: {side} {quantity} {symbol} @ {limit_price}"
            )
        else:
            log.error(
                f"❌ No se pudo crear la orden límite para {symbol}. Respuesta: {order}"
            )


# -------------------- API WEB ENDPOINTS Y FUNCIÓN PRINCIPAL -------------------- #
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def get_status():
    with state_lock:
        return jsonify(app_state)


@app.route("/api/start", methods=["POST"])
def start_bot():
    global bot_thread
    with state_lock:
        if app_state["running"]:
            return (
                jsonify({"status": "error", "message": "El bot ya está en ejecución"}),
                400,
            )
        app_state["running"] = True
        app_state["status_message"] = "Iniciando..."
    bot_instance = TradingBot()
    bot_thread = threading.Thread(target=bot_instance.run, daemon=True)
    bot_thread.start()
    log.info("▶️ Bot iniciado desde la web.")
    return jsonify({"status": "success", "message": "Bot iniciado correctamente."})


@app.route("/api/stop", methods=["POST"])
def stop_bot():
    with state_lock:
        if not app_state["running"]:
            return (
                jsonify({"status": "error", "message": "El bot no está en ejecución"}),
                400,
            )
        app_state["running"] = False
        app_state["status_message"] = "Deteniendo..."
    log.info("⏹️ Bot detenido desde la web.")
    return jsonify({"status": "success", "message": "Bot detenido."})


@app.route("/api/update_config", methods=["POST"])
def update_config():
    global config
    data = request.json
    with state_lock:
        for key, value in data.items():
            if hasattr(config, key):
                field_type = type(getattr(config, key))
                try:
                    setattr(config, key, field_type(value))
                except (ValueError, TypeError):
                    setattr(config, key, str(value).lower() in ["true", "1"])
        app_state["config"] = asdict(config)
    log.info(f"⚙️ Configuración actualizada: {data}")
    socketio.emit("config_updated")
    return jsonify(
        {
            "status": "success",
            "message": "Configuración guardada.",
            "config": app_state["config"],
        }
    )


@app.route("/api/close_position", methods=["POST"])
def close_position_api():
    symbol = request.json.get("symbol")
    if not symbol:
        return jsonify({"status": "error", "message": "Falta el símbolo"}), 400

    with state_lock:
        position = app_state["open_positions"].get(symbol)

    if not position:
        return (
            jsonify(
                {"status": "error", "message": f"No se encontró posición para {symbol}"}
            ),
            404,
        )

    try:
        api = BinanceFutures()
        result = api.close_position(symbol, float(position["positionAmt"]))
        if result:
            # Obtener PNL del trade cerrado
            pnl_records = api._safe_api_call(
                api.client.futures_user_trades, symbol=symbol, limit=10
            )
            realized_pnl = sum(
                float(trade["realizedPnl"])
                for trade in pnl_records
                if trade["orderId"] == result["orderId"]
            )

            with state_lock:
                app_state["performance_stats"]["realized_pnl"] += realized_pnl
                app_state["performance_stats"]["trades_count"] += 1
            log.info(
                f"✅ Posición en {symbol} cerrada. PNL Realizado: {realized_pnl:.2f} USDT"
            )
            return jsonify(
                {"status": "success", "message": f"Posición en {symbol} cerrada."}
            )
        else:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Falló el envío de la orden de cierre.",
                    }
                ),
                500,
            )
    except Exception as e:
        log.error(f"Error al cerrar posición {symbol}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/manual_trade", methods=["POST"])
def manual_trade():
    data = request.json
    symbol, side, margin = (
        data.get("symbol", "").upper(),
        data.get("side"),
        float(data.get("margin", 10)),
    )
    if not all([symbol, side]):
        return jsonify({"status": "error", "message": "Faltan parámetros."}), 400

    try:
        api = BinanceFutures()
        price = float(
            api._safe_api_call(api.client.futures_mark_price, symbol=symbol)[
                "markPrice"
            ]
        )
        filters = api.get_symbol_filters(symbol)
        if not filters:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"No se obtuvieron filtros para {symbol}",
                    }
                ),
                500,
            )

        quantity = (margin * config.LEVERAGE) / price
        quantity = api.round_value(quantity, filters["stepSize"])
        if quantity < filters["minQty"] or (quantity * price) < filters["minNotional"]:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Cantidad ({quantity}) menor al mínimo permitido.",
                    }
                ),
                400,
            )

        order_side = SIDE_BUY if side == "LONG" else SIDE_SELL
        tick_size = filters["tickSize"]
        limit_price = api.round_value(
            price + tick_size * 5 if side == "LONG" else price - tick_size * 5,
            tick_size,
        )
        order = api.place_order(
            symbol, order_side, FUTURE_ORDER_TYPE_LIMIT, quantity, price=limit_price
        )

        if order and order.get("orderId"):
            log.info(f"TRADE MANUAL CREADO: {side} {quantity} {symbol} @ {limit_price}")
            return jsonify(
                {
                    "status": "success",
                    "message": f"Orden límite manual para {symbol} creada.",
                }
            )
        else:
            return (
                jsonify(
                    {"status": "error", "message": f"La orden manual falló: {order}"}
                ),
                500,
            )
    except Exception as e:
        log.error(f"Error en trade manual: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def main():
    log.info("🚀 Iniciando servidor web del Bot de Binance Futures v10")
    socketio.run(
        app,
        debug=False,
        host="0.0.0.0",
        port=5000,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()
