import os
import sys
from PyInstaller.__main__ import run

# --- Archivos adicionales ---

# Recursos adicionales (imágenes e íconos)
additional_files = [
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\shell.ico', 'Distribuidora'),  # Icono principal
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\Logo Mana SRL.jpg', 'Distribuidora'),  # Logo
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\calendario.png',"Distribuidora"),
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\IIBB.png',"Distribuidora"),
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\echeq.png',"Distribuidora"),
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\informe.png',"Distribuidora"),
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\gotas.png',"Distribuidora"),
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\compras.png',"Distribuidora"),
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\margen.png',"Distribuidora"),
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\pedidos.png',"Distribuidora"),
    ('D:\Trabajo\SoftInformes\App PyQt5 y Pandas\src\Distribuidora\precio.png',"Distribuidora"),
]

# Crear la lista de argumentos para PyInstaller
args = [
    '--name=ManaInformes',  # Nombre del ejecutable
    '--windowed',  # No mostrar la consola (solo para GUI)
    '--icon=Distribuidora/shell.ico',  # Icono principal
    'main.py'  # Archivo principal
]

# Incluir archivos adicionales
for src, dest in additional_files:
    if sys.platform == "win32":
        args.append(f'--add-data={src};{dest}')  # Windows
    else:
        args.append(f'--add-data={src}:{dest}')  # macOS y Linux

# Ejecutar PyInstaller
if __name__ == '__main__':
    run(args)