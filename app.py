from __future__ import annotations
"""
Binance Futures Bot v10.9 - Producción completa
Auto-trading con TP/SL dinámico y gestión de posiciones.
"""
import os, time, logging, threading
from dataclasses import dataclass, asdict
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import numpy as np

from flask import Flask, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, FUTURE_ORDER_TYPE_MARKET, FUTURE_ORDER_TYPE_LIMIT, TIME_IN_FORCE_GTC
from binance.exceptions import BinanceAPIException

# ---------------- CONFIG ---------------- #
@dataclass
class CONFIG:
    LEVERAGE: int = 50
    MAX_CONCURRENT_POS: int = 5
    FIXED_MARGIN_PER_TRADE_USDT: float = 1.0
    NUM_SYMBOLS_TO_SCAN: int = 50
    ATR_MULT_SL: float = 2.0
    ATR_MULT_TP: float = 3.0
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
    LOG_LEVEL: str = "DEBUG"
    LOG_FILE: str = "bot_v10.log"
    MYSQL_HOST: str = "localhost"
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "g273f123"
    MYSQL_DATABASE: str = "binance"
    MYSQL_PORT: int = 3306

config = CONFIG()

# ---------------- DATABASE ---------------- #
Base = declarative_base()

class TradeRecord(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    leverage = Column(Integer, nullable=False)
    close_type = Column(String(20), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    date = Column(String(10), nullable=False)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    strategy = Column(String(50), nullable=True)
    duration = Column(Float, nullable=True)

# ---------------- FLASK APP ---------------- #
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key')
CORS(app)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# ---------------- LOGGING ---------------- #
class SocketIOHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            socketio.emit('log_update', {'message': log_entry, 'level': record.levelname.lower()})
        except Exception:
            pass

log = logging.getLogger("BinanceFuturesBot")
log.setLevel(getattr(logging, config.LOG_LEVEL))
if not log.handlers:
    os.makedirs('logs', exist_ok=True)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler = logging.FileHandler(f'logs/{config.LOG_FILE}', encoding='utf-8')
    file_handler.setFormatter(formatter)
    socket_handler = SocketIOHandler()
    socket_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    log.addHandler(socket_handler)
    log.addHandler(console_handler)

# ---------------- MYSQL ---------------- #
def init_mysql():
    try:
        conn_str = f"mysql+mysqlconnector://{config.MYSQL_USER}:{config.MYSQL_PASSWORD}@{config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DATABASE}"
        engine = create_engine(conn_str, pool_pre_ping=True, pool_recycle=3600)
        Base.metadata.create_all(engine)
        Session = scoped_session(sessionmaker(bind=engine))
        log.info("✅ MySQL connected")
        return Session
    except Exception as e:
        log.error(f"MySQL connection error: {e}")
        return None

mysql_session = init_mysql()

# ---------------- GLOBAL STATE ---------------- #
bot_thread = None
state_lock = threading.Lock()
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

# ---------------- BINANCE CLIENT ---------------- #
class BinanceFutures:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        if not api_key or not api_secret:
            raise ValueError("Missing API keys")
        self.client = Client(api_key, api_secret, testnet=testnet)
        log.info(f"🔧 Connected to Binance Futures {'Testnet' if testnet else 'Mainnet'}")
        self.exchange_info = self.client.futures_exchange_info()

    def _safe_api_call(self, func, *args, **kwargs):
        for attempt in range(3):
            try:
                time.sleep(0.1)
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                log.warning(f"API Error {e.code}: {e.message}")
                time.sleep(1 * (attempt + 1))
            except Exception as e:
                log.warning(f"General API error: {e}")
                time.sleep(1 * (attempt + 1))
        return None

    def place_order(self, symbol, side, order_type, quantity, price=None, reduce_only=False):
        params = {'symbol': symbol, 'side': side, 'type': order_type, 'quantity': quantity}
        if order_type == FUTURE_ORDER_TYPE_LIMIT:
            if price is None:
                log.error("LIMIT order requires price")
                return None
            params.update({'price': str(price), 'timeInForce': TIME_IN_FORCE_GTC})
        if reduce_only:
            params['reduceOnly'] = 'true'
        return self._safe_api_call(self.client.futures_create_order, **params)

# ---------------- INDICADORES ---------------- #
def calculate_indicators(df):
    df['EMA_FAST'] = df['close'].ewm(span=config.FAST_EMA, adjust=False).mean()
    df['EMA_SLOW'] = df['close'].ewm(span=config.SLOW_EMA, adjust=False).mean()
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(config.RSI_PERIOD).mean()
    avg_loss = loss.rolling(config.RSI_PERIOD).mean()
    rs = avg_gain / (avg_loss + 1e-8)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['ATR'] = df['high'] - df['low']
    df['ATR'] = df['ATR'].rolling(14).mean()
    return df

def generate_signal(df):
    last = df.iloc[-1]
    if last['EMA_FAST'] > last['EMA_SLOW'] and last['RSI'] < 70:
        return SIDE_BUY
    elif last['EMA_FAST'] < last['EMA_SLOW'] and last['RSI'] > 30:
        return SIDE_SELL
    return None

# ---------------- AUTO-TRADING ---------------- #
def scan_and_trade():
    bf = BinanceFutures()
    session = mysql_session()
    while True:
        try:
            symbols = [s['symbol'] for s in bf.exchange_info['symbols']
                       if s['quoteAsset'] == 'USDT' and s['symbol'] not in config.EXCLUDE_SYMBOLS]
            symbols = symbols[:config.NUM_SYMBOLS_TO_SCAN]

            for symbol in symbols:
                klines = bf._safe_api_call(bf.client.futures_klines, symbol=symbol, interval=config.TIMEFRAME, limit=config.CANDLES_LIMIT)
                if not klines:
                    continue
                df = pd.DataFrame(klines, columns=['open_time','open','high','low','close','volume','close_time',
                                                   'quote_asset_volume','num_trades','taker_buy_base','taker_buy_quote','ignore'])
                df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)
                df = calculate_indicators(df)
                signal = generate_signal(df)

                with state_lock:
                    open_count = len(app_state['open_positions'])
                if open_count >= config.MAX_CONCURRENT_POS:
                    continue

                if signal:
                    qty = config.FIXED_MARGIN_PER_TRADE_USDT
                    last_atr = df['ATR'].iloc[-1]
                    last_close = df['close'].iloc[-1]

                    sl = last_close - config.ATR_MULT_SL*last_atr if signal==SIDE_BUY else last_close + config.ATR_MULT_SL*last_atr
                    tp = last_close + config.ATR_MULT_TP*last_atr if signal==SIDE_BUY else last_close - config.ATR_MULT_TP*last_atr

                    order = bf.place_order(symbol, signal, FUTURE_ORDER_TYPE_MARKET, qty)
                    if order:
                        trade = TradeRecord(
                            symbol=symbol,
                            side=signal,
                            quantity=qty,
                            entry_price=float(order.get('avgFillPrice', last_close)),
                            exit_price=None,
                            pnl=None,
                            roe=None,
                            leverage=config.LEVERAGE,
                            close_type="OPEN",
                            timestamp=datetime.now(),
                            date=datetime.now().strftime("%Y-%m-%d"),
                            stop_loss=sl,
                            take_profit=tp
                        )
                        session.add(trade)
                        session.commit()
                        with state_lock:
                            app_state['open_positions'][symbol] = asdict(trade)
                        log.info(f"✅ Trade abierto: {symbol} {signal} | SL={sl:.2f} TP={tp:.2f}")

        except Exception as e:
            log.error(f"Error scan_and_trade: {e}")
        time.sleep(config.POLL_SEC)

def start_bot():
    global bot_thread
    if bot_thread is None or not bot_thread.is_alive():
        bot_thread = threading.Thread(target=scan_and_trade, daemon=True)
        bot_thread.start()
        with state_lock:
            app_state['running'] = True
            app_state['status_message'] = "Running"
        log.info("🤖 Bot auto-trading iniciado")

# ---------------- ROUTES ---------------- #
@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route('/api/status')
def get_status():
    with state_lock:
        return jsonify(app_state)

@app.route('/api/start', methods=['POST'])
def api_start_bot():
    start_bot()
    return jsonify({"message": "Bot iniciado"}), 200

# ---------------- MAIN ---------------- #
if __name__ == '__main__':
    load_dotenv()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    os.makedirs('logs', exist_ok=True)
    socketio.run(app, debug=debug, host=host, port=port, use_reloader=False, allow_unsafe_werkzeug=True)
