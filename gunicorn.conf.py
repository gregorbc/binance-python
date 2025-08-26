# Gunicorn Configuration for Binance Futures Bot
import os

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
backlog = 2048

# Worker processes
workers = 1
worker_class = "eventlet"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests
max_requests = 1000
max_requests_jitter = 50

# Process naming
proc_name = "binance_futures_bot"

# Environment
raw_env = [
    f"FLASK_ENV={os.environ.get('FLASK_ENV', 'production')}",
]

# --- Corrected Logging Configuration ---
logconfig_dict = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'generic': {
            'format': '%(asctime)s [%(process)d] [%(levelname)s] %(message)s',
            'datefmt': '[%Y-%m-%d %H:%M:%S %z]',
            'class': 'logging.Formatter',
        },
        'access': {
            'format': '%(message)s',
            'class': 'logging.Formatter',
        },
    },
    'handlers': {
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'generic',
            'filename': '/opt/binance-python/logs/error.log',
            'maxBytes': 1024 * 1024 * 5,
            'backupCount': 5,
        },
        'access_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'access',
            'filename': '/opt/binance-python/logs/access.log',
            'maxBytes': 1024 * 1024 * 5,
            'backupCount': 5,
        },
    },
    'loggers': {
        'gunicorn.error': {
            'handlers': ['error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'gunicorn.access': {
            'handlers': ['access_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    # --- THIS IS THE NEW, REQUIRED SECTION ---
    'root': {
        'handlers': ['error_file'],
        'level': 'INFO',
    },
}
