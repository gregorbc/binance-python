from __future__ import annotations
"""
Binance Futures Bot - Web Application v10.4
Production-ready Flask web application for server deployment
"""
import os, time, math, logging, threading
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, FUTURE_ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
from binance.exceptions import BinanceAPIException

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS

# -------------------- CONFIGURATION -------------------- #
@dataclass
class CONFIG:
    # Global Configuration (Editable from web)
    LEVERAGE: int = 20
    MAX_CONCURRENT_POS: int = 10
    FIXED_MARGIN_PER_TRADE_USDT: float = 2.0
    NUM_SYMBOLS_TO_SCAN: int = 150
    # Strategy Configuration (Editable from web)
    ATR_MULT_SL: float = 2.0
    ATR_MULT_TP: float = 3.0
    # Fixed Configuration
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

# -------------------- FLASK APP SETUP -------------------- #
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
CORS(app)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

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
    
    # File handler
    os.makedirs('logs', exist_ok=True)
    file_handler = logging.FileHandler(f'logs/{config.LOG_FILE}', encoding='utf-8', mode='a')
    file_handler.setFormatter(formatter)
    
    # Socket handler for real-time updates
    socket_handler = SocketIOHandler()
    socket_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    log.addHandler(file_handler)
    log.addHandler(socket_handler)
    log.addHandler(console_handler)

# Suppress verbose logging from external libraries
for logger_name in ['binance', 'engineio', 'socketio', 'werkzeug', 'urllib3']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# -------------------- GLOBAL STATE -------------------- #
bot_thread = None
app_state = {
    "running": False,
    "status_message": "Stopped",
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
        "profit_factor": 0.0
    },
    "balance": 0.0,
    "total_investment_usd": 0.0,
    "trades_history": []
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
            raise ValueError("API keys not configured. Set BINANCE_API_KEY and BINANCE_API_SECRET environment variables")
        
        self.client = Client(api_key, api_secret, testnet=testnet)
        log.info(f"🔧 CONNECTED TO BINANCE FUTURES {'TESTNET' if testnet else 'MAINNET'}")
        
        try:
            self.exchange_info = self.client.futures_exchange_info()
            log.info("✅ Exchange information loaded successfully")
        except Exception as e:
            log.error(f"❌ Error connecting to Binance: {e}")
            raise

    def _safe_api_call(self, func, *args, **kwargs):
        for attempt in range(3):
            try:
                time.sleep(0.1)
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                if e.code == -4131:
                    log.warning(f"PERCENT_PRICE error (-4131) in order. Volatile or illiquid market. Skipping.")
                    return None
                log.warning(f"API non-critical error: {e.message}")
                if attempt == 2:
                    log.error(f"Final API error: {e.code} - {e.message}")
                time.sleep(1 * (attempt + 1))
            except Exception as e:
                log.warning(f"General API call error: {e}")
                if attempt == 2:
                    log.error(f"Final general error: {e}")
                time.sleep(1 * (attempt + 1))
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
                log.error("Price required for LIMIT orders.")
                return None
            params.update({
                'price': str(price),
                'timeInForce': TIME_IN_FORCE_GTC
            })
        
        if reduce_only:
            params['reduceOnly'] = 'true'
        
        return self._safe_api_call(self.client.futures_create_order, **params)

    def close_position(self, symbol: str, position_amt: float) -> Optional[Dict]:
        side = SIDE_SELL if position_amt > 0 else SIDE_BUY
        return self.place_order(symbol, side, FUTURE_ORDER_TYPE_MARKET, abs(position_amt), reduce_only=True)

    @staticmethod
    def round_value(value: float, step: float) -> float:
        if step == 0:
            return value
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)

# -------------------- TRADING BOT -------------------- #
class TradingBot:
    def __init__(self):
        self.api = BinanceFutures()
        self.recently_signaled = set()
        self.cycle_count = 0

    def get_top_symbols(self) -> List[str]:
        tickers = self.api._safe_api_call(self.api.client.futures_ticker)
        if not tickers:
            return []
        
        valid_tickers = [
            t for t in tickers
            if t['symbol'].endswith('USDT')
            and t['symbol'] not in config.EXCLUDE_SYMBOLS
            and float(t['quoteVolume']) > config.MIN_24H_VOLUME
        ]
        
        sorted_tickers = sorted(valid_tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
        return [t['symbol'] for t in sorted_tickers[:config.NUM_SYMBOLS_TO_SCAN]]

    def get_klines_for_symbol(self, symbol: str) -> Optional[pd.DataFrame]:
        klines = self.api._safe_api_call(
            self.api.client.futures_klines,
            symbol=symbol,
            interval=config.TIMEFRAME,
            limit=config.CANDLES_LIMIT
        )
        
        if not klines:
            return None
        
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        return df

    def calculate_indicators(self, df: pd.DataFrame):
        df['fast_ema'] = df['close'].ewm(span=config.FAST_EMA, adjust=False).mean()
        df['slow_ema'] = df['close'].ewm(span=config.SLOW_EMA, adjust=False).mean()
        
        # RSI calculation
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=config.RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=config.RSI_PERIOD).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss)))

    def check_signal(self, df: pd.DataFrame) -> Optional[str]:
        if len(df) < 2:
            return None
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Long signal: EMA crossover up and RSI > 50
        if (last['fast_ema'] > last['slow_ema'] and 
            prev['fast_ema'] <= prev['slow_ema'] and 
            last['rsi'] > 50):
            return 'LONG'
        
        # Short signal: EMA crossover down and RSI < 50
        if (last['fast_ema'] < last['slow_ema'] and 
            prev['fast_ema'] >= prev['slow_ema'] and 
            last['rsi'] < 50):
            return 'SHORT'
        
        return None

    def run(self):
        log.info(f"🚀 STARTING TRADING BOT v10.4 (DRY RUN: {config.DRY_RUN})")
        
        while True:
            with state_lock:
                if not app_state["running"]:
                    break
            
            try:
                self.cycle_count += 1
                log.info(f"--- 🔄 New scanning cycle ({self.cycle_count}) ---")

                # Clean signal memory periodically
                if self.cycle_count % config.SIGNAL_COOLDOWN_CYCLES == 1 and self.cycle_count > 1:
                    log.info("🧹 Cleaning recent signals memory (cooldown).")
                    self.recently_signaled.clear()
                
                # Get account info
                account_info = self.api._safe_api_call(self.api.client.futures_account)
                if not account_info:
                    continue
                
                # Process open positions
                open_positions = {
                    p['symbol']: p for p in account_info['positions']
                    if float(p['positionAmt']) != 0
                }
                
                # Emit real-time PnL updates
                if open_positions:
                    socketio.emit('pnl_update', {
                        p['symbol']: float(p['unrealizedProfit'])
                        for p in open_positions.values()
                    })

                # Scan for new signals if we have room for more positions
                num_open_pos = len(open_positions)
                if num_open_pos < config.MAX_CONCURRENT_POS:
                    symbols_to_scan = [
                        s for s in self.get_top_symbols()
                        if s not in open_positions and s not in self.recently_signaled
                    ]
                    
                    log.info(f"🔍 Scanning {len(symbols_to_scan)} symbols for new signals.")
                    
                    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS_KLINE) as executor:
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
                            signal = self.check_signal(df)
                            
                            if signal:
                                log.info(f"🔥 Signal found! {signal} on {symbol}")
                                self.recently_signaled.add(symbol)
                                self.open_trade(symbol, signal, df.iloc[-1])
                                
                                # Check if we've reached the position limit
                                if len(open_positions) + 1 >= config.MAX_CONCURRENT_POS:
                                    log.info("🚫 Concurrent positions limit reached.")
                                    break
                
                # Update application state
                with state_lock:
                    stats = app_state["performance_stats"]
                    
                    # Calculate performance metrics
                    if stats["trades_count"] > 0:
                        stats["win_rate"] = (stats["wins"] / stats["trades_count"]) * 100
                        stats["avg_win"] = (stats["realized_pnl"] / stats["wins"]) if stats["wins"] > 0 else 0
                        
                        # Calculate average loss (this would need trade history in real implementation)
                        total_loss = abs(sum(t.get('pnl', 0) for t in app_state["trades_history"] if t.get('pnl', 0) < 0))
                        stats["avg_loss"] = total_loss / stats["losses"] if stats["losses"] > 0 else 0
                        
                        # Calculate profit factor
                        total_win = sum(t.get('pnl', 0) for t in app_state["trades_history"] if t.get('pnl', 0) > 0)
                        stats["profit_factor"] = total_win / total_loss if total_loss > 0 else float('inf')

                    app_state.update({
                        "status_message": "Running",
                        "balance": next((float(a['walletBalance']) for a in account_info['assets'] if a['asset'] == 'USDT'), 0.0),
                        "open_positions": open_positions,
                        "total_investment_usd": sum(float(p['initialMargin']) for p in open_positions.values()),
                        "performance_stats": stats
                    })
                    
                    # Emit state update to all connected clients
                    socketio.emit('status_update', app_state)

            except Exception as e:
                log.error(f"Error in main loop: {e}", exc_info=True)
            
            time.sleep(config.POLL_SEC)
        
        log.info("🛑 Bot stopped.")

    def open_trade(self, symbol: str, side: str, last_candle):
        if config.DRY_RUN:
            log.info(f"[DRY RUN] Would open {side} on {symbol}")
            return

        filters = self.api.get_symbol_filters(symbol)
        if not filters:
            return

        price = last_candle['close']
        quantity = (config.FIXED_MARGIN_PER_TRADE_USDT * config.LEVERAGE) / price
        quantity = self.api.round_value(quantity, filters['stepSize'])

        if quantity < filters['minQty'] or (quantity * price) < filters['minNotional']:
            log.warning(f"Quantity {quantity} for {symbol} is below minimum allowed.")
            return

        order_side = SIDE_BUY if side == 'LONG' else SIDE_SELL
        tick_size = filters['tickSize']
        
        # Place slightly off-market limit order
        limit_price = price + tick_size * 5 if side == 'LONG' else price - tick_size * 5
        limit_price = self.api.round_value(limit_price, tick_size)
        
        log.info(f"Attempting to place LIMIT order for {side} {symbol} @ {limit_price}")
        order = self.api.place_order(symbol, order_side, FUTURE_ORDER_TYPE_LIMIT, quantity, price=limit_price)

        if order and order.get('orderId'):
            log.info(f"✅ LIMIT ORDER CREATED: {side} {quantity} {symbol} @ {limit_price}")
        else:
            log.error(f"❌ Could not create limit order for {symbol}. Response: {order}")

# -------------------- WEB ROUTES -------------------- #
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
        app_state["status_message"] = "Starting..."
    
    bot_instance = TradingBot()
    bot_thread = threading.Thread(target=bot_instance.run, daemon=True)
    bot_thread.start()
    
    log.info("▶️ Bot started from web interface.")
    return jsonify({"status": "success", "message": "Bot started successfully."})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    with state_lock:
        if not app_state["running"]:
            return jsonify({"status": "error", "message": "Bot is not running"}), 400
        
        app_state["running"] = False
        app_state["status_message"] = "Stopping..."
    
    log.info("⏹️ Bot stopped from web interface.")
    return jsonify({"status": "success", "message": "Bot stopped."})

@app.route('/api/update_config', methods=['POST'])
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
                    # Handle boolean conversion
                    setattr(config, key, str(value).lower() in ['true', '1'])
        
        app_state["config"] = asdict(config)
    
    log.info(f"⚙️ Configuration updated: {data}")
    socketio.emit('config_updated')
    return jsonify({
        "status": "success",
        "message": "Configuration saved.",
        "config": app_state["config"]
    })

@app.route('/api/close_position', methods=['POST'])
def close_position_api():
    symbol = request.json.get('symbol')
    if not symbol:
        return jsonify({"status": "error", "message": "Missing symbol"}), 400
    
    with state_lock:
        position = app_state["open_positions"].get(symbol)
    
    if not position:
        return jsonify({"status": "error", "message": f"No position found for {symbol}"}), 404
    
    try:
        api = BinanceFutures()
        result = api.close_position(symbol, float(position['positionAmt']))
        
        if result:
            # Get realized PnL from trade history
            pnl_records = api._safe_api_call(api.client.futures_user_trades, symbol=symbol, limit=10)
            realized_pnl = sum(float(trade['realizedPnl']) for trade in pnl_records if trade['orderId'] == result['orderId'])
            
            with state_lock:
                stats = app_state["performance_stats"]
                stats["realized_pnl"] += realized_pnl
                stats["trades_count"] += 1
                
                # Record the trade
                trade_record = {
                    "symbol": symbol,
                    "pnl": realized_pnl,
                    "timestamp": time.time()
                }
                app_state["trades_history"].append(trade_record)
                
                if realized_pnl >= 0:
                    stats["wins"] += 1
                else:
                    stats["losses"] += 1
            
            log.info(f"✅ Position on {symbol} closed. Realized PNL: {realized_pnl:.2f} USDT")
            return jsonify({"status": "success", "message": f"Position on {symbol} closed."})
        else:
            return jsonify({"status": "error", "message": "Failed to send close order."}), 500
            
    except Exception as e:
        log.error(f"Error closing position {symbol}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/manual_trade', methods=['POST'])
def manual_trade():
    data = request.json
    symbol = data.get('symbol', '').upper()
    side = data.get('side')
    margin = float(data.get('margin', 10))
    
    if not all([symbol, side]):
        return jsonify({"status": "error", "message": "Missing parameters."}), 400
    
    try:
        api = BinanceFutures()
        price = float(api._safe_api_call(api.client.futures_mark_price, symbol=symbol)['markPrice'])
        filters = api.get_symbol_filters(symbol)
        
        if not filters:
            return jsonify({"status": "error", "message": f"Could not get filters for {symbol}"}), 500
        
        quantity = (margin * config.LEVERAGE) / price
        quantity = api.round_value(quantity, filters['stepSize'])
        
        if quantity < filters['minQty'] or (quantity * price) < filters['minNotional']:
            return jsonify({"status": "error", "message": f"Quantity ({quantity}) below minimum allowed."}), 400
        
        order_side = SIDE_BUY if side == 'LONG' else SIDE_SELL
        tick_size = filters['tickSize']
        limit_price = api.round_value(
            price + tick_size * 5 if side == 'LONG' else price - tick_size * 5,
            tick_size
        )
        
        order = api.place_order(symbol, order_side, FUTURE_ORDER_TYPE_LIMIT, quantity, price=limit_price)
        
        if order and order.get('orderId'):
            log.info(f"MANUAL TRADE CREATED: {side} {quantity} {symbol} @ {limit_price}")
            return jsonify({"status": "success", "message": f"Manual limit order for {symbol} created."})
        else:
            return jsonify({"status": "error", "message": f"Manual order failed: {order}"}), 500
            
    except Exception as e:
        log.error(f"Error in manual trade: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/history')
def get_history():
    """Return trading history"""
    with state_lock:
        trades = app_state["trades_history"]
    
    log.info("ℹ️ Trading history request received.")
    return jsonify({"trades": trades})

# -------------------- SOCKETIO EVENTS -------------------- #
@socketio.on('connect')
def handle_connect():
    log.info(f"🔌 Client connected: {request.sid}")
    # Send initial state to new client
    with state_lock:
        socketio.emit('status_update', app_state)

@socketio.on('disconnect')
def handle_disconnect():
    log.info(f"🔌 Client disconnected: {request.sid}")

# -------------------- MAIN FUNCTION -------------------- #
def create_app():
    """Application factory function"""
    return app

if __name__ == '__main__':
    # Load environment variables
    load_dotenv()
    
    # Get configuration from environment
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    log.info("🚀 Starting Binance Futures Bot Web Application v10.4")
    log.info(f"🌐 Server will run on {host}:{port}")
    
    # Create required directories
    os.makedirs('logs', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Run the application
    socketio.run(
        app,
        debug=debug,
        host=host,
        port=port,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )