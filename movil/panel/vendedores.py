"""Lo que ve cada vendedor en su panel: sus litros, su cartera, lo cobrado por mes y sus clientes.

Un vendedor es el código que figura en `ctaclien.VENDEDOR` del cliente (el mismo que `fachist.VENDNUMERO`,
`plan_caj.VENDEDOR` y `usuario.vendedor_id`). El "cobrador" de un recibo es ese mismo vendedor: el sistema no
registra quién cobró físicamente (`plan_caj.USUARIO` es siempre el mismo y `CAJERO` viene vacío).

Funciones puras sobre DataFrames, sin leer archivos ni la base. Todo lo que devuelven es JSON (claves de texto,
números de Python), listo para guardarse. Cada vendedor trae solo lo suyo: la API nunca arma datos de uno a
partir de los de otro (ver `guideline/Movil.md`, Plan A). Aparte se calcula lo de TODA la empresa (todos los clientes y
todo lo cobrado), que ven el admin y el superadmin.
"""
import calendar
import datetime as dt

import pandas as pd

from . import litros, recaudado

TC_FACTURAS = ("FA", "FC", "FE")
# Copia de cuentas_corrientes_io.TC_CONTABLES (el .exe no incluye movil/ ni al revés; lo compara tests/verificar_panel_paridad.py).
TC_CONTABLES = ("FA", "CH", "FC", "ND", "FE", "BE", "SI", "RC", "NC", "CR", "CC")
UMBRAL_SALDO = 0.01
DIAS_POR_VENCER = 7          # una factura que vence dentro de los próximos 7 días (hoy incluido) está "por vencer"
DIAS_PLAZO_SUPUESTO = 30     # si una factura no trae vencimiento: 30 días desde la emisión (hoy no pasa: vienen todas)
MESES_COBRADO = 12           # el mes en curso y los 11 anteriores


def _num(serie):
    return pd.to_numeric(serie, errors="coerce")


def _numero(valor):
    """float del valor, o NaN si no es un número (None, texto vacío...)."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float("nan")


def _importe(valor):
    n = _numero(valor)
    return 0.0 if n != n else n


def _entero(valor):
    return int(_importe(valor))


def _texto(valor):
    return "" if valor is None or pd.isna(valor) else str(valor).strip()


def _redondeo(x):
    return round(float(x), 2) + 0.0   # + 0.0: que un resto nulo sea 0.0 y no -0.0


def vendedor_de_cada_cuenta(clientes):
    """Series cuenta -> código de vendedor del cliente (`ctaclien.VENDEDOR`); sin vendedor = NaN."""
    c = pd.DataFrame({"cuenta": _num(clientes["CNUMERO"]), "vendedor": _num(clientes["VENDEDOR"])}).dropna(subset=["cuenta"])
    return c.drop_duplicates("cuenta").set_index("cuenta")["vendedor"]


def meses(hoy, cantidad=MESES_COBRADO):
    """[(clave 'AAAA-MM', desde, hasta)] del mes en curso hacia atrás; el mes en curso llega hasta `hoy`."""
    anio, mes = hoy.year, hoy.month
    resultado = []
    for i in range(cantidad):
        hasta = hoy if i == 0 else dt.date(anio, mes, calendar.monthrange(anio, mes)[1])
        resultado.append((f"{anio:04d}-{mes:02d}", dt.date(anio, mes, 1), hasta))
        mes -= 1
        if mes == 0:
            anio, mes = anio - 1, 12
    return resultado


def _cartera_vacia():
    return {"en_calle": 0.0, "vencido": 0.0, "pct_vencido": 0.0, "por_vencer": 0.0, "al_dia": 0.0,
            "a_favor": 0.0, "facturas": 0, "clientes_con_deuda": 0}


def _factura(fila, hoy):
    clase = _texto(fila["CLASE"]).upper()
    comprobante = f"{fila['TC']} {clase} {_entero(fila['NROEST']):04d}-{_entero(fila['NC']):08d}"
    atraso = max(0, (pd.Timestamp(hoy) - fila["vto"]).days)
    return {
        "comprobante": " ".join(comprobante.split()),
        "emision": fila["emision"].date().isoformat(),
        "vencimiento": fila["vto"].date().isoformat(),
        "total": _redondeo(_importe(fila["TOTALL"])),
        "saldo": _redondeo(fila["SALDO"]),
        "dias_vencida": int(atraso),
    }


def _cliente(cuenta, nombre, facturas, favor, hoy):
    """Un cliente con su saldo y sus facturas pendientes (`facturas` es lo de ese cliente en `f`, o None si no debe nada);
    `favor` es lo que tiene a favor (positivo) si no debe ninguna factura."""
    if facturas is not None:
        facturas = facturas.sort_values(["emision", "NC"], kind="stable")
        lista = [_factura(r, hoy) for _, r in facturas.iterrows()]
        monto, vencido = _redondeo(facturas["SALDO"].sum()), _redondeo(facturas["vencido"].sum())
    else:
        lista, monto, vencido = [], _redondeo(-favor), 0.0
    return {"cuenta": cuenta, "nombre": nombre, "saldo": monto, "vencido": vencido, "facturas": lista}


def _numeros_de_cartera(mias, a_favor):
    """Los números de la cartera de unas facturas (`mias`, con `SALDO`, `vencido`, `por_vencer`, `al_dia` y `CUENTA`)."""
    en_calle = float(mias["SALDO"].sum())
    vencido = float(mias["vencido"].sum())
    return {
        "en_calle": _redondeo(en_calle),
        "vencido": _redondeo(vencido),
        "pct_vencido": round(vencido / en_calle * 100, 1) if en_calle else 0.0,
        "por_vencer": _redondeo(mias["por_vencer"].sum()),
        "al_dia": _redondeo(mias["al_dia"].sum()),
        "a_favor": _redondeo(a_favor),
        "facturas": int(len(mias)),
        "clientes_con_deuda": int(mias["CUENTA"].nunique()),
    }


def _orden_de_clientes(c):
    """Con deuda primero (la mayor arriba), después los que tienen saldo a favor, después los que no deben nada."""
    return (0 if c["facturas"] else (1 if c["saldo"] < 0 else 2), -c["saldo"] if c["facturas"] else c["saldo"], c["nombre"].lower())


def cartera(ctacorr, clientes, hoy):
    """Deuda de cada vendedor y de toda la empresa: `({código: {"cartera": {...}, "clientes": [...]}}, {"cartera":
    {...}, "clientes": [...]})`. El segundo es el total de TODOS los clientes (también los que no tienen vendedor): lo ve
    el admin.

    Mismas reglas que Cuentas Corrientes del escritorio (`cuentas_corrientes_io.py`): saldo = `SALDO` nativo de las
    facturas FA/FC/FE con saldo > 0,01 (todas, sin filtrar por fecha de emisión) y a favor = cuentas con saldo
    contable negativo que no tienen factura pendiente. Lo nuevo es el vencimiento, que sí viene en los datos
    (`FECHAVTO`): vencido = venció antes de hoy; por vencer = vence en los próximos 7 días; al día = el resto.
    En calle = vencido + por vencer + al día. El a favor va aparte (no se resta).

    `clientes` lista, por vendedor, a sus clientes (todos los que no están inactivos, más cualquiera con saldo)
    para poder consultarlos; los que no deben nada traen saldo 0 y sin facturas.
    """
    hoy_ts = pd.Timestamp(hoy)
    vendedor_de = vendedor_de_cada_cuenta(clientes)

    tc = ctacorr["TC"].astype(str).str.strip().str.upper()
    saldo = _num(ctacorr["SALDO"])
    f = ctacorr.loc[tc.isin(TC_FACTURAS) & (saldo > UMBRAL_SALDO)].copy()
    f["TC"] = tc[f.index]
    f["SALDO"] = saldo[f.index]
    f["CUENTA"] = _num(f["CUENTA"])
    f["emision"] = pd.to_datetime(f["FECHA"], errors="coerce")
    f["vto"] = pd.to_datetime(f["FECHAVTO"], errors="coerce").fillna(f["emision"] + pd.Timedelta(days=DIAS_PLAZO_SUPUESTO))
    f["vendedor"] = f["CUENTA"].map(vendedor_de)
    f["vencido"] = f["SALDO"].where(f["vto"] < hoy_ts, 0.0)
    f["por_vencer"] = f["SALDO"].where((f["vto"] >= hoy_ts) & (f["vto"] <= hoy_ts + pd.Timedelta(days=DIAS_POR_VENCER)), 0.0)
    f["al_dia"] = f["SALDO"] - f["vencido"] - f["por_vencer"]

    movimientos = ctacorr.loc[tc.isin(TC_CONTABLES)]
    contable = _num(movimientos["TOTALL"]).groupby(_num(movimientos["CUENTA"])).sum()
    a_favor = (-contable[contable < -UMBRAL_SALDO])
    a_favor = a_favor[~a_favor.index.isin(f["CUENTA"])]

    por_cuenta = {cuenta: g for cuenta, g in f.groupby("CUENTA")}
    resultado = {}
    todos_los_clientes = []
    vistas = set()
    for _, cliente in clientes.drop_duplicates("CNUMERO").iterrows():
        cuenta, codigo = _numero(cliente["CNUMERO"]), _numero(cliente["VENDEDOR"])
        if cuenta != cuenta:
            continue
        cuenta = int(cuenta)
        vistas.add(cuenta)
        facturas = por_cuenta.get(cuenta)
        favor = float(a_favor.get(cuenta, 0.0))
        inactivo = _texto(cliente["INACTIVO"]).lower() in ("true", "1", "s", "si", "sí")
        if facturas is None and not favor and inactivo:
            continue
        entrada = _cliente(cuenta, _texto(cliente["CNOMBRE"]) or "SIN NOMBRE", facturas, favor, hoy)
        todos_los_clientes.append(entrada)
        if codigo == codigo:   # un cliente sin vendedor no es de ninguno, pero sí cuenta en el total de la empresa
            resultado.setdefault(int(codigo), {"cartera": _cartera_vacia(), "clientes": []})["clientes"].append(entrada)
    # Una cuenta con facturas pendientes que ya no está en ctaclien: no se pierde, se lista aparte.
    for cuenta, facturas in por_cuenta.items():
        if int(cuenta) not in vistas:
            todos_los_clientes.append(_cliente(int(cuenta), "CLIENTE DESCONOCIDO", facturas, 0.0, hoy))

    for codigo, datos in resultado.items():
        mias = f.loc[f["vendedor"] == codigo]
        cuentas_mias = {c["cuenta"] for c in datos["clientes"]}
        datos["cartera"] = _numeros_de_cartera(mias, a_favor[a_favor.index.isin(cuentas_mias)].sum())
        datos["clientes"].sort(key=_orden_de_clientes)
    # Toda la empresa: lo mismo sumado sobre todas las facturas y todos los clientes (para el admin y el superadmin).
    empresa = {"cartera": _numeros_de_cartera(f, a_favor.sum()), "clientes": sorted(todos_los_clientes, key=_orden_de_clientes)}
    return resultado, empresa


def _por_mes(recibos, caja, periodos_mes):
    """El desglose de lo cobrado en cada mes de `periodos_mes` para los `recibos` que se pasan (los de un vendedor o los de
    todos); `caja` ya viene recortada a la ventana. {"AAAA-MM": {desde, hasta, total, recibos, efectivo, ...}}."""
    return {
        clave: {"desde": desde.isoformat(), "hasta": hasta.isoformat(), **recaudado.desglose(recibos, caja, desde, hasta)}
        for clave, desde, hasta in periodos_mes
    }


def cobrado(recibos, caja, codigos, hoy):
    """Cobrado por mes (los últimos 12 meses) de cada vendedor y de toda la empresa: `({código: {"AAAA-MM": {desde,
    hasta, total, recibos, efectivo, transferencia, cheques, retenciones, otros}}}, {"AAAA-MM": {...}})`. Mismas reglas
    del recaudado del panel (`recaudado.desglose`), aplicadas a los recibos (`plan_caj`) del vendedor del cliente (el
    segundo, a todos los recibos)."""
    periodos_mes = meses(hoy)
    inicio, fin = pd.Timestamp(periodos_mes[-1][1]), pd.Timestamp(hoy)
    fr = pd.to_datetime(recibos["FECHA"], errors="coerce")
    recibos_en_ventana = recibos.loc[(fr >= inicio) & (fr <= fin)]
    fc = pd.to_datetime(caja["FECHA"], errors="coerce")
    caja_en_ventana = caja.loc[(fc >= inicio) & (fc <= fin)]
    codigo_recibo = _num(recibos_en_ventana["VENDEDOR"])
    por_vendedor = {codigo: _por_mes(recibos_en_ventana.loc[codigo_recibo == codigo], caja_en_ventana, periodos_mes)
                    for codigo in codigos}
    return por_vendedor, _por_mes(recibos_en_ventana, caja_en_ventana, periodos_mes)


def litros_de_cada_uno(ventas, abmartic, clasificacion, periodos, codigos):
    """Litros del mes y del mes anterior (hasta el mismo día) de cada vendedor, con la misma forma que el panel
    general: `litros.periodo` sobre las ventas del vendedor (`fachist.VENDNUMERO`)."""
    fechas = pd.to_datetime(ventas["FECHA"], errors="coerce")
    desde, hasta = periodos["mes_anterior"][0], periodos["mes"][1]
    en_ventana = ventas.loc[(fechas >= pd.Timestamp(desde)) & (fechas <= pd.Timestamp(hasta))]
    codigo_venta = _num(en_ventana["VENDNUMERO"])
    resultado = {}
    for codigo in codigos:
        mias = en_ventana.loc[codigo_venta == codigo]
        mes = litros.periodo(mias, abmartic, clasificacion, *periodos["mes"])
        anterior = litros.periodo(mias, abmartic, clasificacion, *periodos["mes_anterior"])
        resultado[codigo] = {
            "mes": mes,
            "mes_anterior": {k: anterior[k] for k in ("litros", "premium", "pct_premium", "por_proveedor")},
        }
    return resultado


def calcular(ventas, abmartic, clasificacion, ctacorr, clientes, recibos, caja, hoy, periodos):
    """El panel de todos los vendedores y el de la empresa entera: {"hoy", "periodos", "vendedores": {"<código>":
    {litros, cartera, cobrado, clientes}}, "empresa": {cartera, cobrado, clientes}}. La empresa es la suma de todos los
    clientes y de todo lo cobrado (para el admin y el superadmin); no trae litros porque el panel general ya los tiene.
    `periodos` son los rangos del panel general (`calculo.periodos(hoy)`)."""
    deuda, deuda_empresa = cartera(ctacorr, clientes, hoy)
    # Vendedores = los que tienen clientes asignados, más los que vendieron o cobraron en lo que se muestra
    # (códigos viejos de hace años no aparecen).
    fecha_venta = pd.to_datetime(ventas["FECHA"], errors="coerce")
    fecha_recibo = pd.to_datetime(recibos["FECHA"], errors="coerce")
    codigos = {int(c) for c in vendedor_de_cada_cuenta(clientes).dropna()}
    codigos |= {int(c) for c in _num(ventas.loc[fecha_venta >= pd.Timestamp(periodos["mes_anterior"][0]), "VENDNUMERO"]).dropna()}
    codigos |= {int(c) for c in _num(recibos.loc[fecha_recibo >= pd.Timestamp(meses(hoy)[-1][1]), "VENDEDOR"]).dropna()}
    codigos = sorted(codigos)

    sus_litros = litros_de_cada_uno(ventas, abmartic, clasificacion, periodos, codigos)
    lo_cobrado, cobrado_empresa = cobrado(recibos, caja, codigos, hoy)
    vendedores = {}
    for codigo in codigos:
        d = deuda.get(codigo, {"cartera": _cartera_vacia(), "clientes": []})
        vendedores[str(codigo)] = {
            "litros": sus_litros[codigo],
            "cartera": d["cartera"],
            "cobrado": lo_cobrado[codigo],
            "clientes": d["clientes"],
        }
    # Los períodos que muestran los litros, con la misma forma que en el panel general (así el celular dibuja las
    # mismas tarjetas): cada fila de `panel_vendedor` lleva `hoy` y `periodos` junto a los datos del vendedor.
    rangos = {nombre: {"desde": periodos[nombre][0].isoformat(), "hasta": periodos[nombre][1].isoformat()}
              for nombre in ("mes", "mes_anterior")}
    empresa = {"cartera": deuda_empresa["cartera"], "cobrado": cobrado_empresa, "clientes": deuda_empresa["clientes"]}
    return {"hoy": hoy.isoformat(), "periodos": rangos, "vendedores": vendedores, "empresa": empresa}
