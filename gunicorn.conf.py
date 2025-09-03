# gunicorn.conf.py
import multiprocessing

# Configuración de Gunicorn
workers = 2
threads = 4
worker_class = "eventlet"
bind = "0.0.0.0:5000"
reload = False
preload_app = True
timeout = 120
max_requests = 1000
max_requests_jitter = 100
graceful_timeout = 30
worker_connections = 1000
