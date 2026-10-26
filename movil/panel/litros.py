"""Litros vendidos y % Premium, con la MISMA lógica del informe de Litros del escritorio
(`src/Views/Litros/LitrosDBF.py`, ver `guideline/Views-Litros.md`), pero sin Qt: funciones puras
sobre DataFrames, para poder calcularlas en el servidor sin la aplicación de escritorio.

Ojo: el mapa de medidas y las reglas están DUPLICADOS respecto del escritorio (el `.exe` no
incluye `movil/` ni al revés). `tests/verificar_panel_paridad.py` compara las dos copias; si se
agrega un CODMEDIDA nuevo en el escritorio, ese test avisa que acá falta.
"""
import re

import pandas as pd

# Proveedores que distingue el informe de Litros (`clasificar_proveedor`). Premium solo existe en SHELL.
PROVEEDORES = ("SHELL", "VALVOLINE", "OTROS")

# Tipos de comprobante que cuentan como ventas en el informe de Litros (src/ui/paginas/litros.py).
TC_LITROS = ("FC", "NC", "ND", "FE", "CR")

# Mapa explícito de CODMEDIDA → litros por unidad (copia de LitrosDBF.py).
_CODMEDIDA_LITROS = {
    # ── Litros directos ──────────────────────────────────────────────────
    '0.5 l': 0.5,
    '1 lt': 1.0, '1 lts': 1.0,
    '4 lts': 4.0,
    '5 lts': 5.0, '5': 5.0,
    '8 lts': 8.0,
    '10l': 10.0,
    '15 lt': 15.0,
    '19 l': 19.0,
    '20 lt': 20.0,
    '100 l': 100.0,
    '200 l': 200.0,
    '204 l': 204.0,
    '205 l': 205.0, '205': 205.0,
    '208 l': 208.0,
    '209 l': 209.0,
    '240 l': 240.0,
    '250 l': 250.0,
    '1000': 1000.0,           # IBC 1000 LTS
    # ── Galones (1 gal US = 3.785411784 L) ──────────────────────────────
    '1 gl': 3.785,
    '1/4 g': 0.946,
    # ── cc / cm³ / mL  →  ÷ 1000 ────────────────────────────────────────
    '100 c': 0.1,
    '150': 0.15,
    '200': 0.2,
    '250': 0.25,
    '350 c': 0.35,
    '415': 0.415,
    '440': 0.44, '440 c': 0.44,
    '450 c': 0.45,
    '500 c': 0.5,
    # ── Onzas fluidas (1 fl oz = 0.029574 L) ────────────────────────────
    '12 oz': 0.355,
    '14 oz': 0.414,
    # ── Sin equivalencia en litros (unidades, kits, criques) ─────────────
    '1': 0.0, '1 uni': 0.0, 'kit': 0.0, 'cja10': 0.0,
    # TN = capacidad de carga en criques, no peso → 0 L
    '2 tn': 0.0, '3 tn': 0.0, '4 tn': 0.0, '5 tn': 0.0,
    '10 tn': 0.0, '15 tn': 0.0, '20 tn': 0.0, '30 tn': 0.0,
    # ── Kg → L  (1 kg = 1 L) ─────────────────────────────────────────────
    '1 kg': 1.0,
    '3.5 k': 3.5,
    '4 kg': 4.0,
    '5 kgs': 5.0,
    '16 kg': 16.0,
    '18 kg': 18.0,
    '20 kg': 20.0,
    '45 kg': 45.0,
    '170 k': 170.0,
    '180 k': 180.0,
    '190.5': 190.5,  # GADUS 190,5 KG
    '200k': 200.0,
    # ── Gramos → L  (÷ 1000) ─────────────────────────────────────────────
    '150 g': 0.15,
    '250 g': 0.25,
    '400 g': 0.4,
    '500 g': 0.5,
    '907 g': 0.907,
    # ── Libras → L  (1 lb = 0.453592 kg = 0.453592 L) ────────────────────
    '35 lb': 15.876,  # 35 × 0.453592
}

def codmedida_a_litros(codmedida: str) -> float:
    """Convierte CODMEDIDA a litros por unidad. Retorna 0.0 si no aplica."""
    key = str(codmedida).strip().lower()
    if key in _CODMEDIDA_LITROS:
        return _CODMEDIDA_LITROS[key]
    # Fallback: extraer primer número (cubre nuevos códigos en L no mapeados)
    m = re.match(r'^(\d+(?:\.\d+)?)', key)
    if m:
        return float(m.group(1))
    return 0.0


def clasificar_proveedor(sku):
    sku = str(sku).strip()
    if sku.upper().startswith("L"):
        return "SHELL"
    if re.match(r"^\d{2}[A-Za-z]{2}\d{3}$", sku):
        return "VALVOLINE"
    return "OTROS"


def litros_por_producto(ventas, abmartic, clasificacion):
    """Tabla por producto como la del informe: Codigo, Unidades, Litros, Proveedor, Premium.

    :param ventas: DataFrame con ``MODELO`` y ``U_VENDIDAS`` (ya filtrado por fecha y tipo de comprobante).
    :param abmartic: DataFrame con ``CODART`` y ``CODMEDIDA``.
    :param clasificacion: DataFrame con ``articulo``, ``Clasificacion`` y ``Artiprov`` (LITROS SHELL.xlsx).
    """
    vacio = pd.DataFrame(columns=["Codigo", "Unidades", "Litros", "Proveedor", "Premium"])
    if ventas.empty:
        return vacio
    # inner: las ventas de artículos que no están en abmartic no cuentan (igual que el escritorio)
    df = ventas[["MODELO", "U_VENDIDAS"]].merge(abmartic[["CODART", "CODMEDIDA"]], left_on="MODELO", right_on="CODART", how="inner")
    if df.empty:
        return vacio
    df["U_VENDIDAS"] = pd.to_numeric(df["U_VENDIDAS"], errors="coerce").fillna(0)
    df["litros"] = (df["U_VENDIDAS"] * df["CODMEDIDA"].apply(lambda c: codmedida_a_litros(str(c)))).round(2)
    df["Proveedor"] = df["MODELO"].apply(clasificar_proveedor)

    cls = clasificacion.set_index("articulo")["Clasificacion"].to_dict()
    cls.update(clasificacion.dropna(subset=["Artiprov"]).set_index("Artiprov")["Clasificacion"].to_dict())
    df["Premium"] = df.apply(
        lambda r: cls.get(str(r["MODELO"]).strip(), "-") if r["Proveedor"] == "SHELL" else "-", axis=1)

    agg = df.groupby("MODELO", as_index=False).agg(
        Unidades=("U_VENDIDAS", "sum"), Litros=("litros", "sum"), Proveedor=("Proveedor", "first"), Premium=("Premium", "first"))
    agg["Litros"] = agg["Litros"].round(2)
    return agg.rename(columns={"MODELO": "Codigo"})


def totales(tabla):
    """(litros totales, litros premium) de la tabla por producto, como los KPI del escritorio."""
    if tabla.empty:
        return 0.0, 0.0
    return float(tabla["Litros"].sum()), float(tabla.loc[tabla["Premium"] == "Premium", "Litros"].sum())


def por_proveedor(tabla):
    """{proveedor: {"litros", "premium"}} de la tabla por producto; siempre trae los tres proveedores
    (en cero si no vendieron). Con esto el celular recalcula totales y % premium para cualquier
    selección de proveedores sin volver a pedir nada (igual que los filtros del escritorio)."""
    resultado = {p: {"litros": 0.0, "premium": 0.0} for p in PROVEEDORES}
    if tabla.empty:
        return resultado
    for proveedor in PROVEEDORES:
        t = tabla[tabla["Proveedor"] == proveedor]
        resultado[proveedor] = {
            "litros": round(float(t["Litros"].sum()), 2),
            "premium": round(float(t.loc[t["Premium"] == "Premium", "Litros"].sum()), 2),
        }
    return resultado


def periodo(ventas, abmartic, clasificacion, desde, hasta):
    """Litros del período [desde, hasta] (inclusive, fechas `date`): total, premium, % premium,
    el desglose por proveedor y la serie por día (para un gráfico; cada día también con su
    desglose). `ventas` trae ``FECHA``, ``TC``, ``MODELO``, ``U_VENDIDAS``."""
    fechas = pd.to_datetime(ventas["FECHA"], errors="coerce")
    tc = ventas["TC"].astype(str).str.strip().str.upper()
    f = ventas.loc[(fechas >= pd.Timestamp(desde)) & (fechas <= pd.Timestamp(hasta)) & tc.isin(TC_LITROS)].copy()
    f["FECHA"] = pd.to_datetime(f["FECHA"]).dt.date

    tabla = litros_por_producto(f, abmartic, clasificacion)
    total, premium = totales(tabla)
    por_dia = []
    for dia, grupo in f.groupby("FECHA"):
        tabla_dia = litros_por_producto(grupo, abmartic, clasificacion)
        t, p = totales(tabla_dia)
        por_dia.append({"fecha": dia.isoformat(), "litros": round(t, 2), "premium": round(p, 2),
                        "proveedores": por_proveedor(tabla_dia)})
    return {
        "litros": round(total, 2),
        "premium": round(premium, 2),
        "pct_premium": round(premium / total * 100, 1) if total else 0.0,
        "por_proveedor": por_proveedor(tabla),
        "por_dia": por_dia,
    }
