from flask import Flask, jsonify, send_from_directory
from flask_socketio import SocketIO
from app.binance_client import BinanceFuturesMaxProfit
import eventlet

app = Flask(__name__, static_folder="../static")
socketio = SocketIO(app, cors_allowed_origins="*")

bot = BinanceFuturesMaxProfit(socketio)

@app.route("/api/status")
def status():
    return jsonify(bot.get_status())

@app.route("/api/start", methods=["POST"])
def start():
    return jsonify(bot.start())

@app.route("/api/stop", methods=["POST"])
def stop():
    return jsonify(bot.stop())

@app.route("/api/positions")
def positions():
    return jsonify(bot.get_positions())

@app.route("/api/scan")
def scan():
    return jsonify(bot.run_scan())

@app.route("/api/performance")
def performance():
    return jsonify(bot.get_performance())

@app.route("/")
def index():
    return send_from_directory("../static", "index.html")

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
