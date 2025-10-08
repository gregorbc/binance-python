#!/bin/bash

echo "🤖 Instalación del Bot de Trading Binance Futures"
echo "=================================================="

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no está instalado. Por favor instálalo primero."
    exit 1
fi

echo "✅ Python 3 encontrado"

# Crear entorno virtual
echo "🔧 Creando entorno virtual..."
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
echo "📦 Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt

# Configurar archivo .env
echo "⚙️ Configurando variables de entorno..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "📝 Por favor configura el archivo .env con tus claves API"
fi

# Crear directorios necesarios
echo "📁 Creando directorios..."
mkdir -p logs
mkdir -p static
mkdir -p templates

# Verificar instalación
echo "🔍 Verificando instalación..."
python -c "import binance, flask, pandas, numpy" && echo "✅ Todas las dependencias instaladas correctamente" || echo "❌ Error en la instalación de dependencias"

echo ""
echo "🎉 Instalación completada!"
echo ""
echo "📝 Próximos pasos:"
echo "1. Configura tus claves API en el archivo .env"
echo "2. Ejecuta: source venv/bin/activate"
echo "3. Ejecuta: python app.py"
echo "4. Abre http://localhost:5000 en tu navegador"
echo ""
echo "💡 Para soporte: gregorbc@gmail.com"