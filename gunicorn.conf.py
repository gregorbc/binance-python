# Gunicorn Configuration for Binance Futures Bot
import os

# Server socket
# Bind to 0.0.0.0 to allow external connections
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
backlog = 2048

# Worker processes
# Use 'eventlet' for SocketIO compatibility.
# It's recommended to start with 1 worker and scale if needed.
workers = 1
worker_class = "eventlet"
worker_connections = 1000
timeout = 120
keepalive = 5

# Process naming for easier identification
proc_name = "binance_futures_bot"

# Logging
# Ensure the 'logs' directory exists before starting
logs_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(logs_dir, exist_ok=True)

# Define log file paths
accesslog = os.path.join(logs_dir, "gunicorn_access.log")
errorlog = os.path.join(logs_dir, "gunicorn_error.log")
loglevel = "info"

# Preload the application to save memory and improve startup time
preload_app = True
