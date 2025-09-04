# Monkey patch debe ser lo PRIMERO que se ejecute
try:
    import eventlet
    eventlet.monkey_patch()
    print("Eventlet monkey patching applied successfully.")
except Exception as e:
    print(f"Monkey patching failed: {e}")
    # Continue without monkey patch if eventlet not available

import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Importar la aplicación Flask después del monkey patch
def create_app():
    from app import app
    return app

app = create_app()

# Asegurarse de que la aplicación sea callable
if __name__ == "__main__":
    app.run()
