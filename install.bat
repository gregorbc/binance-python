@echo off
echo Instalando Bot de Trading Binance Futures...
echo ==========================================

echo Creando entorno virtual...
python -m venv venv

echo Activando entorno virtual...
call venv\Scripts\activate.bat

echo Instalando dependencias principales...
pip install --upgrade pip
pip install python-dotenv requests pandas numpy python-binance
pip install flask flask-socketio flask-cors eventlet

echo Instalando dependencias opcionales...
pip install talib-binance tensorflow sqlalchemy

echo Creando estructura de carpetas...
mkdir