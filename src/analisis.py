"""Indicadores por 10,000 adultos y gráficas del proyecto."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

from limpieza import CLAVE_NO_IDENTIFICADO

# ---------------------------------------------------------------- columnas clave
SUC = "total__infraestructura__sucursales"
CAJ = "total__infraestructura__cajeros_automaticos"
COR = "total__infraestructura__corresponsales_unicos"
CTA = "capt__total__cuentas_total"
PUNTOS = {SUC: "Sucursales", CAJ: "Cajeros", COR: "Corresponsales"}
SECTORES_SUC = {
    "bm__infraestructura__sucursales": "Banca múltiple",
    "bd__infraestructura__sucursales": "Banca de desarrollo",
    "socap__infraestructura__sucursales": "Cooperativas (SOCAP)",
    "sofipo__infraestructura__sucursales": "Financieras populares (SOFIPO)",
}
ORDEN_REZAGO = ["Muy bajo", "Bajo", "Medio", "Alto", "Muy alto"]
ORDEN_TIPO = ["Metrópoli", "Semi-metrópoli", "Urbano", "Semi-urbano", "En transición", "Rural"]


def marcar(df: pd.DataFrame) -> pd.DataFrame:
    """Banderas que deciden qué entra a los indicadores por habitante."""
    df = df.copy()
    df["es_no_identificado"] = df["clave_mun"] == CLAVE_NO_IDENTIFICADO
    df["sin_poblacion"] = (df["poblacion_adulta"] == 0) & ~df["es_no_identificado"]
    df["usar_en_tasas"] = ~df["es_no_identificado"] & ~df["sin_poblacion"]
    df["sin_punto_de_acceso"] = (df[SUC] == 0) & (df[CAJ] == 0) & (df[COR] == 0)
    for col, nombre in PUNTOS.items():
        tasa = (df[col] / df["poblacion_adulta"] * 1e4).where(df["usar_en_tasas"])
        df[f"{nombre.lower()}_por_10k_adultos"] = tasa.astype("Float64").round(2)
    df["cuentas_por_adulto"] = (df[CTA] / df["poblacion_adulta"]).where(df["usar_en_tasas"]).astype("Float64").round(2)
    return df


def tasas(df: pd.DataFrame, por: str) -> pd.DataFrame:
    """Suma numeradores y denominadores antes de dividir (no promedia tasas)."""
    base = df[df["usar_en_tasas"]]
    g = base.groupby(por).agg(
        municipios=("clave_mun", "size"),
        municipios_sin_acceso=("sin_punto_de_acceso", "sum"),
        poblacion_adulta=("poblacion_adulta", "sum"),
        **{n: (c, "sum") for c, n in PUNTOS.items()},
        cuentas=(CTA, "sum"),
    )
    for n in PUNTOS.values():
        g[f"{n.lower()}_por_10k"] = (g[n] / g["poblacion_adulta"] * 1e4).round(2)
    g["cuentas_por_adulto"] = (g["cuentas"] / g["poblacion_adulta"]).round(2)
    g["pct_municipios_sin_acceso"] = (g["municipios_sin_acceso"] / g["municipios"] * 100).round(1)
    return g


def nacional(df: pd.DataFrame) -> pd.Series:
    base = df[df["usar_en_tasas"]]
    s = base[list(PUNTOS) + [CTA, "poblacion_adulta"]].sum()
    return pd.Series({f"{n.lower()}_por_10k": round(s[c] / s["poblacion_adulta"] * 1e4, 2)
                      for c, n in PUNTOS.items()})


# ---------------------------------------------------------------- estilo
TINTA, TINTA2, TENUE = "#0b0b0b", "#52514e", "#898781"
REJILLA, BASE, FONDO = "#e1e0d9", "#c3c2b7", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
FUENTE = "Fuente: CNBV, Base de Datos de Inclusión Financiera, marzo 2026. Elaboración: Leonardo Chapa Gallardo."


def estilo():
    plt.rcParams.update({
        "font.family": ["Inter", "DejaVu Sans"],
        "font.size": 10, "axes.titlesize": 13, "axes.titleweight": "semibold",
        "axes.edgecolor": BASE, "axes.labelcolor": TINTA2, "text.color": TINTA,
        "xtick.color": TENUE, "ytick.color": TINTA2,
        "axes.spines.top": False, "axes.spines.right": False,
        "figure.facecolor": FONDO, "axes.facecolor": FONDO,
        "savefig.facecolor": FONDO, "savefig.dpi": 200,
    })


def _cerrar(fig, ax, titulo, subtitulo, ruta, y_fuente=-0.03):
    ax.set_title(titulo, loc="left", pad=26)
    ax.text(0, 1.02, subtitulo, transform=ax.transAxes, color=TINTA2, fontsize=9.5)
    fig.text(0.01, y_fuente, FUENTE, color=TENUE, fontsize=7.5)
    fig.savefig(ruta, bbox_inches="tight")
    plt.close(fig)


def grafica_estados(por_estado: pd.DataFrame, valor_nacional: float, ruta: str):
    d = por_estado["cajeros_por_10k"].sort_values()
    fig, ax = plt.subplots(figsize=(8, 9))
    ax.barh(d.index, d.values, color=SERIES[0], height=0.72)
    ax.axvline(valor_nacional, color=TINTA2, lw=1, ls=(0, (3, 3)))
    ax.text(valor_nacional, len(d) - 0.3, f"  Nacional: {valor_nacional:.1f}", color=TINTA2, fontsize=8.5, va="bottom")
    for y, v in enumerate(d.values):
        ax.text(v + 0.15, y, f"{v:.1f}", va="center", fontsize=8, color=TINTA2, zorder=3,
                bbox=dict(boxstyle="square,pad=0.1", fc=FONDO, ec="none"))
    ax.xaxis.grid(True, color=REJILLA, lw=0.6); ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0); ax.set_ylim(-0.6, len(d) - 0.1)
    ax.set_xlabel("Cajeros automáticos por cada 10,000 adultos")
    _cerrar(fig, ax, "Cajeros automáticos por estado",
            "Todos los sectores. La línea punteada marca el promedio nacional.", ruta)


def grafica_rezago(por_rezago: pd.DataFrame, ruta: str):
    d = por_rezago.loc[ORDEN_REZAGO]
    cols = [("sucursales_por_10k", "Sucursales"), ("cajeros_por_10k", "Cajeros"),
            ("corresponsales_por_10k", "Corresponsales")]
    fig, ax = plt.subplots(figsize=(9, 5))
    ancho, x = 0.26, range(len(d))
    for k, (c, n) in enumerate(cols):
        pos = [i + (k - 1) * (ancho + 0.01) for i in x]
        ax.bar(pos, d[c], width=ancho, color=SERIES[k], label=n)
        for p, v in zip(pos, d[c]):
            ax.text(p, v + 0.12, f"{v:.1f}", ha="center", fontsize=8, color=TINTA2)
    ax.set_xticks(list(x), d.index); ax.tick_params(axis="x", length=0, colors=TINTA2)
    ax.yaxis.grid(True, color=REJILLA, lw=0.6); ax.set_axisbelow(True)
    ax.set_ylabel("Puntos por cada 10,000 adultos"); ax.set_xlabel("Índice de rezago social del municipio")
    ax.legend(frameon=False, ncol=3, loc="upper right")
    _cerrar(fig, ax, "A más rezago social, menos infraestructura financiera",
            "Municipios agrupados por índice de rezago social (CONEVAL).", ruta)


def grafica_sectores(df: pd.DataFrame, ruta: str):
    base = df[df["usar_en_tasas"]]
    d = base.groupby("tipo_de_poblacion")[list(SECTORES_SUC)].sum().loc[ORDEN_TIPO[::-1]]
    pct = d.div(d.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(9, 4.8))
    izquierda = pd.Series(0.0, index=pct.index)
    for k, (c, n) in enumerate(SECTORES_SUC.items()):
        ax.barh(pct.index, pct[c], left=izquierda, color=SERIES[k], label=n,
                height=0.66, edgecolor=FONDO, linewidth=1.5)
        for y, (l, v) in enumerate(zip(izquierda, pct[c])):
            if v >= 9:
                ax.text(l + v / 2, y, f"{v:.0f}%", ha="center", va="center", fontsize=8,
                        color="#0b0b0b" if SERIES[k] == "#eda100" else "white")
        izquierda += pct[c]
    for y, total in enumerate(d.sum(axis=1)):
        ax.text(101, y, f"{int(total):,} suc.", va="center", fontsize=8, color=TINTA2)
    ax.set_xlim(0, 100); ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    ax.tick_params(axis="y", length=0)
    ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.1), fontsize=8.5)
    _cerrar(fig, ax, "¿Quién tiene sucursales en el México rural?",
            "Distribución de sucursales por sector, según tipo de población del municipio.", ruta, y_fuente=-0.1)


def grafica_sin_acceso(por_tipo: pd.DataFrame, ruta: str):
    d = por_tipo.loc[ORDEN_TIPO[::-1]]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.barh(d.index, d["pct_municipios_sin_acceso"], color=SERIES[0], height=0.62)
    for y, (p, n, m) in enumerate(zip(d["pct_municipios_sin_acceso"], d["municipios_sin_acceso"], d["municipios"])):
        ax.text(p + 0.8, y, f"{p:.1f}%  ({int(n)} de {int(m)})", va="center", fontsize=8.5, color=TINTA2)
    ax.set_xlim(0, 55); ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    ax.xaxis.grid(True, color=REJILLA, lw=0.6); ax.set_axisbelow(True); ax.tick_params(axis="y", length=0)
    _cerrar(fig, ax, "Municipios sin ningún punto de acceso financiero",
            "Sin sucursal, cajero automático ni corresponsal, por tipo de población.", ruta)
