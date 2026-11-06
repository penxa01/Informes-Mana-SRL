"""Verifica la lógica pura del panel de control (formatos, filtro de productos, litros por proveedor,
deltas, cobranzas). Sin Qt y sin base de datos.

    python tests/verificar_panel_vista.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers import panel_vista as pv

fallas = []


def check(nombre, cond):
    print(("OK   " if cond else "FALLA"), nombre)
    if not cond:
        fallas.append(nombre)


def igual(nombre, obtenido, esperado):
    ok = obtenido == esperado
    check(nombre if ok else f"{nombre}: obtuvo {obtenido!r}, esperaba {esperado!r}", ok)


# ── formatos (igual que panel-comun.js) ──────────────────────────────────────
igual("numero miles", pv.numero(1234567), "1.234.567")
igual("numero decimales", pv.numero(1234.5, 1), "1.234,5")
igual("numero redondea .5 hacia arriba (como JS)", pv.numero(2.5), "3")
igual("numero 0,125 -> 0,13", pv.numero(0.125, 2), "0,13")
igual("numero negativo", pv.numero(-1500), "-1.500")
igual("dinero millones", pv.dinero(89_800_000), "$ 89,8 M")
igual("dinero miles", pv.dinero(850_000), "$ 850 mil")
igual("dinero chico", pv.dinero(1200), "$ 1.200")
igual("dinero negativo", pv.dinero(-2_000_000), "$ -2,0 M")

igual("porcentaje cero", pv.texto_porcentaje(0, 100), "0 %")
igual("porcentaje menor a 1", pv.texto_porcentaje(0.5, 100), "<1 %")
igual("porcentaje normal", pv.texto_porcentaje(25, 100), "25 %")
igual("porcentaje sin total", pv.texto_porcentaje(5, 0), "0 %")

# ── chip de variación ────────────────────────────────────────────────────────
igual("delta sin dato anterior", pv.chip_delta(10, 0, "vs x"), ("neutro", "sin dato anterior"))
igual("delta sube", pv.chip_delta(110, 100, "vs x"), ("sube", "▲ 10,0 % vs x"))
igual("delta baja", pv.chip_delta(90, 100, "vs x"), ("baja", "▼ 10,0 % vs x"))
igual("delta igual", pv.chip_delta(100, 100, "vs x"), ("neutro", "= igual vs x"))
igual("delta en puntos", pv.chip_delta(30, 28, "vs x", puntos=True), ("sube", "▲ 2,0 pts vs x"))

# ── filtro de productos ──────────────────────────────────────────────────────
f = pv.FiltroProveedores()
check("filtro arranca con todos", f.estan_todos() and not f.activo("SHELL"))
f.alternar("SHELL")
igual("primer toque aísla", f.seleccion, {"SHELL"})
check("con uno elegido, SHELL está activo", f.activo("SHELL") and not f.activo("OTROS"))
f.alternar("OTROS")
igual("segundo toque suma", f.seleccion, {"SHELL", "OTROS"})
f.alternar("SHELL")
f.alternar("OTROS")
check("sin ninguno vuelve a todos", f.estan_todos())
f.alternar("VALVOLINE")
f.todos()
check("todos() restablece", f.estan_todos())
a = pv.FiltroProveedores()
firma0 = a.firma()
a.alternar("SHELL")
check("la firma cambia con la selección", a.firma() != firma0)

# ── litros (vista_litros) ────────────────────────────────────────────────────
DATOS = {
    "litros": {
        "mes": {
            "litros": 100.0, "premium": 30.0, "pct_premium": 30.0,
            "por_dia": [
                {"fecha": "2026-11-02", "litros": 60.0, "premium": 20.0,
                 "proveedores": {"SHELL": {"litros": 40.0, "premium": 20.0}, "VALVOLINE": {"litros": 15.0, "premium": 0.0},
                                 "OTROS": {"litros": 5.0, "premium": 0.0}}},
                {"fecha": "2026-11-03", "litros": 40.0, "premium": 10.0,
                 "proveedores": {"SHELL": {"litros": 20.0, "premium": 10.0}, "VALVOLINE": {"litros": 10.0, "premium": 0.0},
                                 "OTROS": {"litros": 10.0, "premium": 0.0}}},
            ],
            "por_proveedor": {"SHELL": {"litros": 60.0, "premium": 30.0}, "VALVOLINE": {"litros": 25.0, "premium": 0.0},
                              "OTROS": {"litros": 15.0, "premium": 0.0}},
        },
        "mes_anterior": {
            "litros": 80.0, "premium": 16.0, "pct_premium": 20.0,
            "por_proveedor": {"SHELL": {"litros": 40.0, "premium": 16.0}, "VALVOLINE": {"litros": 30.0, "premium": 0.0},
                              "OTROS": {"litros": 10.0, "premium": 0.0}},
        },
    }
}
todos = pv.vista_litros(DATOS, pv.FiltroProveedores())
check("con todos: hay desglose y no hay etiqueta", todos["con_desglose"] and todos["etiqueta"] is None)
igual("con todos: litros", todos["litros"], 100.0)
igual("con todos: % premium", todos["pct"], 30.0)

solo = pv.FiltroProveedores()
solo.alternar("SHELL")
shell = pv.vista_litros(DATOS, solo)
igual("Shell: litros", shell["litros"], 60.0)
igual("Shell: premium", shell["premium"], 30.0)
igual("Shell: % premium", shell["pct"], 50.0)
igual("Shell: etiqueta", shell["etiqueta"], "Shell")
igual("Shell: litros del mes anterior", shell["litros_ant"], 40.0)
igual("Shell: % anterior", shell["pct_ant"], 40.0)
check("Shell incluye Shell", shell["incluye_shell"])
igual("Shell: por día", [d["litros"] for d in shell["por_dia"]], [40.0, 20.0])

otros = pv.FiltroProveedores()
otros.alternar("VALVOLINE")
otros.alternar("OTROS")
vo = pv.vista_litros(DATOS, otros)
check("sin Shell no incluye Shell", not vo["incluye_shell"])
igual("Valvoline + Otros: etiqueta", vo["etiqueta"], "Valvoline + Otros")
igual("Valvoline + Otros: litros", vo["litros"], 40.0)

viejo = {"litros": {"mes": {"litros": 5.0, "premium": 1.0, "pct_premium": 20.0, "por_dia": []},
                    "mes_anterior": {"litros": 4.0, "premium": 1.0, "pct_premium": 25.0}}}
v = pv.vista_litros(viejo, pv.FiltroProveedores())
check("formato anterior (sin desglose): no hay filtro", not v["con_desglose"] and v["incluye_shell"])
igual("formato anterior: litros", v["litros"], 5.0)

# ── cómo se cobró ────────────────────────────────────────────────────────────
desglose = {"total": 1000.0, "efectivo": 500.0, "transferencia": 300.0, "cheques": 200.0,
            "retenciones": 0.0, "otros": 0.0, "diferencia": 0.0}
medios = pv.medios_de_cobro(desglose)
igual("medios: solo los que siempre se muestran si no hay más", [m["clave"] for m in medios], ["efectivo", "transferencia", "cheques"])
igual("medios: porcentaje de efectivo", medios[0]["porcentaje"], "50 %")
con_otros = pv.medios_de_cobro({**desglose, "otros": 40.0, "retenciones": 10.0})
igual("medios: retenciones y otros aparecen si hay algo",
      [m["clave"] for m in con_otros], ["efectivo", "transferencia", "cheques", "retenciones", "otros"])
check("sin diferencia no hay aviso", pv.aviso_diferencia(desglose) is None)
check("con diferencia hay aviso", "diferencia $ 12" in (pv.aviso_diferencia({**desglose, "diferencia": 12.0}) or ""))

# ── cobranzas ────────────────────────────────────────────────────────────────
igual("factura vencida", pv.estado_factura("2026-11-03", "2026-11-06"), ("vencida", "Vencida hace 3 días"))
igual("factura vencida hace 1 día", pv.estado_factura("2026-11-05", "2026-11-06"), ("vencida", "Vencida hace 1 día"))
igual("factura vence hoy", pv.estado_factura("2026-11-06", "2026-11-06"), ("por-vencer", "Vence hoy"))
igual("factura vence mañana", pv.estado_factura("2026-11-07", "2026-11-06"), ("por-vencer", "Vence mañana"))
igual("factura vence en 5 días", pv.estado_factura("2026-11-11", "2026-11-06"), ("por-vencer", "Vence en 5 días"))
igual("factura al día", pv.estado_factura("2026-11-14", "2026-11-06"), ("al-dia", "Al día"))

CLIENTES = {
    "cartera": {"clientes_con_deuda": 1},
    "clientes": [
        {"cuenta": 101, "nombre": "Pérez Hnos", "saldo": 500.0, "vencido": 100.0, "facturas": [{"comprobante": "A1"}]},
        {"cuenta": 102, "nombre": "Gómez", "saldo": -50.0, "vencido": 0.0, "facturas": []},
        {"cuenta": 103, "nombre": "Sin deuda SA", "saldo": 0.0, "vencido": 0.0, "facturas": []},
    ],
}
sin_busqueda, resumen = pv.filtrar_clientes(CLIENTES, "", todos=True)
igual("sin búsqueda: solo con deuda o a favor", [c["cuenta"] for c in sin_busqueda], [101, 102])
check("sin búsqueda: el resumen cuenta clientes con deuda", "1 cliente con deuda" in resumen)
res, resumen = pv.filtrar_clientes(CLIENTES, "perez", todos=True)
igual("búsqueda ignora acentos", [c["cuenta"] for c in res], [101])
res, _ = pv.filtrar_clientes(CLIENTES, "103", todos=True)
igual("búsqueda por número de cuenta", [c["cuenta"] for c in res], [103])
res, resumen = pv.filtrar_clientes(CLIENTES, "zzz", todos=True)
check("búsqueda sin resultados lo dice", res == [] and "No hay clientes" in resumen)
muchos = {"cartera": {"clientes_con_deuda": 0},
          "clientes": [{"cuenta": i, "nombre": f"Cliente {i}", "saldo": 1.0, "vencido": 0.0, "facturas": []} for i in range(100)]}
res, resumen = pv.filtrar_clientes(muchos, "cliente", todos=True)
check("la búsqueda corta en 40 resultados", len(res) == 40 and "Mostrando 40 de 100" in resumen)

igual("texto de saldo con vencido", pv.texto_de_saldo(CLIENTES["clientes"][0]), "1 factura · $ 100 vencido")
igual("texto de saldo a favor", pv.texto_de_saldo(CLIENTES["clientes"][1]), "Saldo a favor del cliente")
igual("texto de saldo sin deuda", pv.texto_de_saldo(CLIENTES["clientes"][2]), "Sin deuda")

igual("nombre de mes", pv.nombre_mes("2026-03"), "marzo 2026")
igual("día corto", pv.dia_corto(pv.fecha_corta("2026-11-02")), "lun 2")
from datetime import datetime as _dt
igual("actualizado hoy", pv.texto_actualizado(_dt(2026, 11, 6, 0, 3), ahora=_dt(2026, 11, 6, 9, 0)), "Datos de las 00:03")
igual("actualizado otro día", pv.texto_actualizado(_dt(2026, 11, 5, 23, 50), ahora=_dt(2026, 11, 6, 9, 0)), "Datos de las 23:50 del 5/11")

# ── estado del panel ─────────────────────────────────────────────────────────
igual("sin avisos si todo está bien", pv.avisos({"desactualizado": False, "error": None, "verificado_hace_seg": 10}, False), [])
check("aviso por falta de latido", len(pv.avisos({"desactualizado": True, "error": None, "verificado_hace_seg": 1200}, False)) == 1)
check("aviso por error de cálculo", len(pv.avisos({"desactualizado": False, "error": "x", "verificado_hace_seg": 10}, False)) == 1)
check("aviso por falta de conexión", len(pv.avisos({"desactualizado": False, "error": None, "verificado_hace_seg": 10}, True)) == 1)

print()
if fallas:
    print(f"{len(fallas)} FALLA(S)")
    sys.exit(1)
print("TODO OK")
