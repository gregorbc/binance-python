# patch_nuclear.py
# Solución nuclear - comenta todos los endpoints problemáticos

def nuclear_fix():
    print("☢️  Aplicando solución nuclear...")
    
    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Encontrar las secciones problemáticas y comentarlas
        problematic_patterns = [
            "@app.route('/api/update_config', methods=['POST'])",
            "@app.route('/api/close_position', methods=['POST'])", 
            "@app.route('/api/manual_trade', methods=['POST'])"
        ]
        
        fixed = False
        in_problematic_block = False
        new_lines = []
        
        for line in lines:
            # Verificar si estamos en un bloque problemático
            if any(pattern in line for pattern in problematic_patterns):
                in_problematic_block = True
                new_lines.append(f"# COMENTADO POR DUPLICADO: {line}")
                fixed = True
            elif in_problematic_block and line.strip() and not line.startswith(' ') and not line.startswith('@'):
                # Salir del bloque cuando encontramos una línea no indentada que no es decorador
                in_problematic_block = False
                new_lines.append(line)
            elif in_problematic_block:
                new_lines.append(f"# {line}")
            else:
                new_lines.append(line)
        
        if fixed:
            with open('app.py', 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print("✅ Solución nuclear aplicada - endpoints duplicados comentados")
        else:
            print("⚠️  No se encontraron endpoints duplicados para comentar")
            
    except Exception as e:
        print(f"❌ Error en solución nuclear: {e}")

if __name__ == '__main__':
    nuclear_fix()