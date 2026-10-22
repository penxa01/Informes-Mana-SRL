import os
import openpyxl
import pandas as pd

import PyQt5.QtWidgets as widget
from dbfread import DBF

from src.controllers import config

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.utils import get_column_letter

def generar_archivo_excel(df, ruta_salida):
    """
    Genera un archivo Excel con el formato específico definido.

    :param df: DataFrame con los datos a guardar.
    :param ruta_salida: Ruta donde se guardará el archivo generado.
    """

    # Crear un nuevo libro y hoja de trabajo
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Informe Mensual"

    # Fila 1: Título DISTRIBUIDOR
    ws.append(["DISTRIBUIDOR"])
    ws.merge_cells('A1:D1')
    titulo = ws['A1']
    titulo.font = Font(bold=True, size=14)
    titulo.alignment = Alignment(horizontal="center", vertical="center")

    # Fila 2: Encabezados
    encabezados = ["Dia / Periodo", "SKU", "Familia", "Litros"]
    ws.append(encabezados)

    estilo_encabezado = Font(bold=True, color="ED1C24", name="Arial")  # Fuente Arial como alternativa
    relleno_encabezado = PatternFill(start_color="FFD500", end_color="FFD500", fill_type="solid")
    alineacion_centrada = Alignment(horizontal="center", vertical="center")

    for col_num, encabezado in enumerate(encabezados, start=1):
        celda = ws.cell(row=2, column=col_num)
        celda.font = estilo_encabezado
        celda.fill = relleno_encabezado
        celda.alignment = alineacion_centrada

    # Fila 3 en adelante: Datos del DataFrame
    for row in dataframe_to_rows(df, index=False, header=False):
        # Ajustar formato de fecha si la columna corresponde
        if isinstance(row[0], (str, pd.Timestamp)):
            try:
                row[0] = pd.to_datetime(row[0]).strftime('%Y/%m/%d')
            except Exception:
                pass
        ws.append(row)

    # Ajustar el ancho de las columnas
    columnas_anchos = [20, 25, 15, 10]
    for col_num, ancho in enumerate(columnas_anchos, start=1):
        ws.column_dimensions[get_column_letter(col_num)].width = ancho

    ws.delete_rows(3)
    ws.delete_rows(3)
    # Guardar el archivo

    try:
        wb.save(ruta_salida)
        # Mostrar mensaje de éxito
        msg_box = widget.QMessageBox()
        msg_box.setIcon(widget.QMessageBox.Information)
        msg_box.setWindowTitle("Informe Generado")
        msg_box.setText(f"El informe se guardó correctamente en:\n{ruta_salida}")
        msg_box.setStandardButtons(widget.QMessageBox.Ok)
        msg_box.exec_()
    except PermissionError:
        # Manejar el error de archivo abierto
        msg_box = widget.QMessageBox()
        msg_box.setIcon(widget.QMessageBox.Critical)
        msg_box.setWindowTitle("Error al Guardar")
        msg_box.setText(f"No se pudo guardar el archivo. Asegúrate de que no esté abierto:\n{ruta_salida}")
        msg_box.setStandardButtons(widget.QMessageBox.Ok)
        msg_box.exec_()

def format_CLIENTE(df,ruta_salida,cant):
    """
    Formatea un archivo Excel estableciendo anchos de columna específicos.
    
    Parámetros:
        datagrama (str): Ruta del archivo Excel de entrada.
        ruta_salida (str): Ruta donde se guardará el archivo formateado.
    """
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

    df.to_excel(ruta_salida,index = False)
    # Cargar el archivo Excel
    workbook = openpyxl.load_workbook(ruta_salida)
    hoja = workbook.active
    
    # Definir los anchos de las columnas
    anchos_columnas = {"A":13.0,"B":12.0,"C":54.14,"D":54.14,"E":17.29,"F":26.43,"G":51.86,"H":18.86,"I":23.14,"J":14.57,"K":6.0,"L":9.43,"M":16.14,"N":13.57,"O":24.43,"P":5.14,"Q":17.57}
    
    # Aplicar los anchos de columna
    for columna, ancho in anchos_columnas.items():
        hoja.column_dimensions[columna].width = ancho
    
    # Guardar el archivo formateado
    try:
        workbook.save(ruta_salida)
        # Mostrar mensaje de éxito
        msg_box = widget.QMessageBox()
        msg_box.setIcon(widget.QMessageBox.Information)
        msg_box.setWindowTitle("Informe Generado")
        msg_box.setText(f"Se agregaron {cant} clientes. \n El informe se guardó correctamente en:\n{ruta_salida}")
        msg_box.setStandardButtons(widget.QMessageBox.Ok)
        msg_box.exec_()
    except PermissionError:
        # Manejar el error de archivo abierto
        msg_box = widget.QMessageBox()
        msg_box.setIcon(widget.QMessageBox.Critical)
        msg_box.setWindowTitle("Error al Guardar")
        msg_box.setText(f"No se pudo guardar el archivo. Asegúrate de que no esté abierto:\n{ruta_salida}")
        msg_box.setStandardButtons(widget.QMessageBox.Ok)
        msg_box.exec_()

def buscaArtic(df):
    ruta = os.path.join(config.DBF_BASE_PATH, "ABMARTIC.DBF")
    abmartic = pd.DataFrame(iter(DBF(ruta, load=True, encoding=config.DBF_ENCODING)))
    
    abmartic = abmartic[abmartic['CODART'].isin(df['MODELO'])]

    return abmartic
