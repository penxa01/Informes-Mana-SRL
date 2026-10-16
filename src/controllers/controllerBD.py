import os

import psycopg2
from dbfread import DBF

from src.controllers import config


def _dbf(nombre):
    """Ruta de un DBF del sistema de gestión en el entorno detectado (D:/tiempo o Z:)."""
    return os.path.join(config.DBF_BASE_PATH, nombre)


def obtener_conexion():
    return psycopg2.connect(
        host="localhost",
        database="pedidosMana",
        user="postgres",
        password="011201"
    )

def importar_clientes_desde_dbf():
    tabla = DBF(_dbf('ctaclien.dbf'), encoding='latin-1')  # Usa el encoding correcto según tu archivo

    conn = obtener_conexion()
    cursor = conn.cursor()

    for registro in tabla:
        id_cliente = str(registro.get('CNUMERO'))
        nombre = str(registro.get('CNOMBRE')).strip()
        direccion = str(registro.get('CDIREC')).strip()
        telefono = str(registro.get('TELEFONO')).strip()
        print(f"Importando cliente: {id_cliente}, {nombre}, {direccion}, {telefono}")

        # Asegurate que la tabla cliente tenga columnas: id_cliente (TEXT o VARCHAR), nombre
        cursor.execute("""
            INSERT INTO cliente (id_cliente,nombre,direccion,telefono)
            VALUES (%s, %s, %s, %s)
        """, (id_cliente, nombre, direccion, telefono))

    conn.commit()
    cursor.close()
    conn.close()
    print("Importación completa.")

def busca_stock(id_producto):
    tabla_stock = DBF(_dbf('stock.dbf'), encoding='latin-1')  # Usa el encoding correcto según tu archivo
    for registro in tabla_stock:
        if str(registro.get('ARTICULO')) == id_producto:
            stock = registro.get('STOCK')
            return stock

def importar_productos_desde_dbf():
    tabla = DBF(_dbf('abmartic.dbf'), encoding='latin-1')  # Usa el encoding correcto según tu archivo

    conn = obtener_conexion()
    cursor = conn.cursor()

    for registro in tabla:
        id_producto = str(registro.get('CODART'))
        nombre = str(registro.get('DESC')).strip()
        stock = busca_stock(id_producto)
        print(f"Importando producto: {id_producto}, {nombre}, {stock}")

        # Asegurate que la tabla producto tenga columnas: id_producto (TEXT o VARCHAR), nombre, precio
        cursor.execute("""
            INSERT INTO producto (id_producto,nombre,stock_disponible)
            VALUES (%s, %s, %s)
        """, (id_producto, nombre, stock))

    conn.commit()
    cursor.close()
    conn.close()
    print("Importación completa.")

if __name__ == "__main__":
    opcion = input("¿Desea importar clientes o productos? (c/p): ").strip().lower()
    if opcion == 'c':
        importar_clientes_desde_dbf()
    elif opcion == 'p':
        importar_productos_desde_dbf()
    else:
        print("Opción no válida. Por favor, elija 'c' para clientes o 'p' para productos.")