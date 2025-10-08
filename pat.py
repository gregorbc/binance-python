import os
import re


def apply_patch():
    """Aplicar parche a app.py para agregar rutas faltantes"""

    patch_code = '''
# -------------------- RUTAS API ADICIONALES -------------------- #
@app.route('/api/history')
def api_history():
    """Obtener historial de trades"""
    with state_lock:
        return jsonify({
            "trades": app_state["trades_history"],
            "balance_history": app_state["balance_history"]
        })

@app.route('/api/update_config', methods=['POST'])
def api_update_config():
    """Actualizar configuración del bot"""
    try:
        new_config = request.json
        with state_lock:
            for key, value in new_config.items():
                if hasattr(config, key):
                    # Convertir a tipo correcto
                    current_value = getattr(config, key)
                    if isinstance(current_value, bool):
                        setattr(config, key, bool(value))
                    elif isinstance(current_value, int):
                        setattr(config, key, int(value))
                    elif isinstance(current_value, float):
                        setattr(config, key, float(value))
                    else:
                        setattr(config, key, value)
            
            app_state["config"] = asdict(config)
        
        socketio.emit('config_updated')
        return jsonify({"status": "config_updated", "message": "Configuración actualizada"})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/close_position', methods=['POST'])
def api_close_position():
    """Cerrar posición manualmente"""
    try:
        data = request.json
        symbol = data.get('symbol')
        
        if not symbol:
            return jsonify({"status": "error", "message": "Símbolo requerido"}), 400
        
        # Mock de cierre de posición
        log.info(f"🔄 Cerrando posición manualmente: {symbol}")
        
        socketio.emit('log_update', {
            'message': f'Posición cerrada manualmente: {symbol}',
            'level': 'INFO'
        })
        
        return jsonify({"status": "success", "message": f"Posición {symbol} cerrada"})
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/manual_trade', methods=['POST'])
def api_manual_trade():
    """Ejecutar trade manual"""
    try:
        data = request.json
        symbol = data.get('symbol')
        side = data.get('side')
        margin = data.get('margin')
        leverage = data.get('leverage')
        
        if not all([symbol, side, margin]):
            return jsonify({"status": "error", "message": "Datos incompletos"}), 400
        
        # Mock de trade manual
        log.info(f"🔄 Trade manual: {side} {symbol} con {margin} USDT ({leverage}x)")
        
        socketio.emit('log_update', {
            'message': f'Trade manual ejecutado: {side} {symbol}',
            'level': 'INFO'
        })
        
        return jsonify({
            "status": "success", 
            "message": f"Trade manual {side} {symbol} ejecutado"
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# Emitir actualizaciones periódicas
def emit_updates():
    """Emitir actualizaciones de estado periódicamente"""
    while True:
        try:
            with state_lock:
                # Emitir estado completo
                socketio.emit('status_update', app_state)
                
                # Emitir P&L actualizado de posiciones abiertas
                pnl_data = {}
                for symbol, position in app_state["open_positions"].items():
                    unrealized_pnl = float(position.get('unrealizedProfit', 0))
                    pnl_data[symbol] = unrealized_pnl
                
                if pnl_data:
                    socketio.emit('pnl_update', pnl_data)
            
            time.sleep(2)  # Emitir cada 2 segundos
            
        except Exception as e:
            log.error(f"Error emitiendo actualizaciones: {e}")
            time.sleep(5)

# Iniciar hilo de emisión de actualizaciones
update_thread = threading.Thread(target=emit_updates, daemon=True)
update_thread.start()
'''

    # Leer el archivo actual
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Buscar donde insertar el parche (antes del if __name__)
    insertion_point = content.find("if __name__ == '__main__':")

    if insertion_point == -1:
        print("❌ No se encontró el punto de inserción")
        return False

    # Insertar el parche
    new_content = (
        content[:insertion_point] + patch_code + "\n\n" + content[insertion_point:]
    )

    # Crear backup
    with open("app.py.backup", "w", encoding="utf-8") as f:
        f.write(content)

    # Escribir nuevo contenido
    with open("app.py", "w", encoding="utf-8") as f:
        f.write(new_content)

    print("✅ Parche aplicado exitosamente")
    print("✅ Se creó backup: app.py.backup")
    return True


if __name__ == "__main__":
    apply_patch()
