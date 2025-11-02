#!/bin/bash
source venv/bin/activate
export FLASK_APP=app/main.py
export FLASK_ENV=production
export BINANCE_API_KEY="TU_API_KEY"
export BINANCE_SECRET_KEY="TU_SECRET_KEY"
gunicorn -k eventlet -w 1 -b 0.0.0.0:5000 wsgi:app
