#!/bin/bash

# Exit immediately if a command fails
set -e

# --- Virtual Environment Setup ---
if [ -d "venv" ]; then
    echo "Activating existing virtual environment..."
    source venv/bin/activate
else
    echo "Creating new virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Upgrading pip and installing requirements..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# --- Check for TA-Lib ---
if ! python -c "import talib" 2>/dev/null; then
    echo "WARNING: TA-Lib not found. Some indicators will be disabled."
fi

# --- Flask Environment Configuration ---
export FLASK_ENV=production
export DEBUG=false

# --- Database Initialization ---
echo "Initializing the database..."
# First install required packages, then initialize
python3 -c "
import sys
try:
    from database import init_db
    from app import app
    with app.app_context():
        init_db()
    print('Database initialization complete.')
except Exception as e:
    print(f'Database initialization failed: {e}')
    sys.exit(1)
"

# --- Start Gunicorn Server ---
echo "Starting Gunicorn server with eventlet workers..."
exec gunicorn -c gunicorn.conf.py wsgi:app
