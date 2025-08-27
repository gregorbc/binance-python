"""
WSGI Configuration for Binance Futures Bot
Production-ready WSGI entry point for Gunicorn.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
# This ensures that Gunicorn has access to the necessary secrets and config
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Import the Flask application instance from your main app file.
# The `socketio` instance is already attached to the `app` instance within app.py.
# Gunicorn, when run with the eventlet worker, will correctly handle both
# standard HTTP requests and WebSocket connections.
from app import app

# The variable 'application' is what Gunicorn looks for by default.
application = app
