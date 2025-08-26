sudo bash -c 'cat > /opt/binance-python/wsgi.py <<EOF
#!/usr/bin/env python3
"""
WSGI Configuration for Binance Futures Bot
Production-ready WSGI entry point
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project directory to Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# Import the Flask application and the SocketIO instance
from app import app, socketio

# For production servers, the socketio object is the WSGI application
application = socketio

if __name__ == "__main__":
    socketio.run(app, debug=False, host="0.0.0.0", port=5000)
EOF'
