"""
Limpieza de la Base de Datos de Inclusión Financiera (BDIF) de la CNBV.

Las hojas municipales del Excel original traen:
  - 8 filas de portada antes de los datos, con una fila de totales de control (fila 2)
  - un encabezado de 4 niveles con celdas combinadas (filas 9 a 12)
  - nombres de variable con saltos de línea y la unidad pegada ("Sucursales\\nNúmero")
  - un registro artificial 99999 "No identificado" con población cero
Este módulo convierte cada hoja en una tabla plana, tipada y validada.
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

# Filas (base 0) dentro de cada hoja municipal
FILA_TOTALES = 1          # fila 2 de Excel: suma de control por columna
FILAS_ENCABEZADO = range(8, 12)   # filas 9 a 12 de Excel
PRIMERA_FILA_DATOS = 12   # fila 13 de Excel

CLAVE_NO_IDENTIFICADO = 99999

# Abreviaturas para que los nombres de columna queden cortos y legibles
ABREVIATURAS = {
    "todos_los_sectores": "total",
    "banca_multiple": "bm",
    "banca_de_desarrollo": "bd",
    "sociedades_cooperativas_de_ahorro_y_prestamo": "socap",
    "sociedades_financieras_populares": "sofipo",
    "entidades_de_ahorro_y_credito_popular_eacp": "eacp",
}


def a_snake(texto: str) -> str:
    """'Cajeros automáticos\\nNúmero' -> 'cajeros_automaticos_numero'."""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^0-9a-zA-Z]+", "_", texto.lower())
    return texto.strip("_")


def nombre_variable(celda: str) -> str:
    """Quita la unidad que viene pegada tras el salto de línea."""
    return a_snake(str(celda).split("\n")[0])


def construir_columnas(encabezado: pd.DataFrame) -> list[str]:
    """
    Aplana el encabezado de 4 niveles.

    Las celdas combinadas llegan como vacías, así que los niveles 0 a 2 se
    rellenan hacia la derecha antes de unirlos.
    """
    niveles = encabezado.astype(object).reset_index(drop=True)
    relleno = niveles.iloc[0:3].T.ffill().T
    niveles = pd.concat([relleno, niveles.iloc[[3]]])
    columnas = []
    for j in niveles.columns:
        tema, sector, grupo, variable = niveles[j].tolist()
        if pd.isna(variable):
            columnas.append(None)
            continue
        if sector == "Información general" or pd.isna(sector):
            # Aquí el salto de línea es parte del nombre ("Clave \nEstado")
            columnas.append(a_snake(variable))
            continue
        var = nombre_variable(variable)
        sector_c = ABREVIATURAS.get(a_snake(sector), a_snake(sector))
        grupo_c = ABREVIATURAS.get(a_snake(grupo), a_snake(grupo))
        partes = [sector_c]
        # El grupo solo se añade cuando distingue algo (no repite el tema)
        if grupo_c and grupo_c not in {a_snake(tema), "total"}:
            partes.append(grupo_c)
        if var != "total" or len(partes) == 1:
            partes.append(var)
        columnas.append("__".join(partes))
    return columnas


RENOMBRES_INFO = {
    "clave_municipio": "clave_mun",
    "clave_estado": "clave_edo",
    "poblacion": "poblacion_total",
    "poblacion_adulta_mujeres": "poblacion_adulta_mujeres",
}


def leer_hoja(ruta: str, hoja: str) -> tuple[pd.DataFrame, pd.Series]:
    """Devuelve (tabla limpia, totales de control de la fila 2)."""
    crudo = pd.read_excel(ruta, sheet_name=hoja, header=None, engine="openpyxl")

    columnas = construir_columnas(crudo.iloc[list(FILAS_ENCABEZADO)])
    totales = crudo.iloc[FILA_TOTALES]

    datos = crudo.iloc[PRIMERA_FILA_DATOS:].copy()
    datos.columns = columnas
    totales.index = columnas

    # Columnas sin nombre (la columna A vacía) y filas totalmente vacías
    con_nombre = [isinstance(c, str) for c in columnas]
    datos = datos.loc[:, con_nombre]
    totales = totales[con_nombre]
    datos = datos.dropna(how="all")

    datos = datos.rename(columns=RENOMBRES_INFO)
    totales = totales.rename(index=RENOMBRES_INFO)

    # Nombres duplicados tras aplanar indicarían un error de construcción
    duplicadas = datos.columns[datos.columns.duplicated()].tolist()
    if duplicadas:
        raise ValueError(f"{hoja}: columnas duplicadas tras aplanar: {duplicadas}")

    return datos.reset_index(drop=True), totales


TEXTO = ["region", "estado", "municipio", "tipo_de_poblacion", "indice_de_rezago_social"]
CLAVES = ["clave_mun", "clave_edo"]


def tipar(df: pd.DataFrame) -> pd.DataFrame:
    """Claves y conteos a enteros; texto sin espacios ni saltos sobrantes."""
    df = df.copy()
    for c in TEXTO:
        if c in df:
            df[c] = (df[c].astype("string")
                          .str.replace(r"\s+", " ", regex=True)
                          .str.strip())
    numericas = [c for c in df.columns if c not in TEXTO]
    for c in numericas:
        df[c] = pd.to_numeric(df[c], errors="raise")
        # Todos los conteos deben ser enteros: si no, se detiene
        if not np.allclose(df[c].dropna() % 1, 0):
            raise ValueError(f"La columna {c} trae valores no enteros")
        df[c] = df[c].astype("Int64")
    return df


def validar(df: pd.DataFrame, totales: pd.Series, hoja: str) -> list[str]:
    """Revisiones de consistencia. Devuelve una bitácora legible."""
    bitacora = []

    assert df["clave_mun"].is_unique, f"{hoja}: claves de municipio repetidas"
    bitacora.append(f"{len(df):,} registros, clave de municipio única")

    geo = df[df["clave_mun"] != CLAVE_NO_IDENTIFICADO]
    assert (geo["clave_mun"] // 1000 == geo["clave_edo"]).all(), \
        f"{hoja}: la clave de estado no coincide con la de municipio"
    bitacora.append("La clave de estado coincide con los primeros dígitos de la clave municipal")

    suma = geo["poblacion_adulta_mujeres"] + geo["poblacion_adulta_hombres"]
    assert (suma == geo["poblacion_adulta"]).all(), f"{hoja}: adultos ≠ mujeres + hombres"
    bitacora.append("Población adulta = mujeres + hombres en todos los municipios")

    numericas = df.select_dtypes("number").columns.difference(CLAVES)
    negativos = int((df[numericas] < 0).sum().sum())
    assert negativos == 0, f"{hoja}: hay {negativos} valores negativos"
    nulos = int(df.isna().sum().sum())
    bitacora.append(f"Sin valores negativos; {nulos} celdas vacías")

    # Contra la fila de totales de control del propio archivo
    revisadas, diferencias = 0, []
    for c in numericas:
        esperado = totales.get(c)
        if pd.notna(esperado) and isinstance(esperado, (int, float, np.integer, np.floating)):
            revisadas += 1
            if int(df[c].sum()) != int(esperado):
                diferencias.append((c, int(df[c].sum()), int(esperado)))
    if diferencias:
        raise ValueError(f"{hoja}: sumas que no cuadran con la fila de control: {diferencias[:5]}")
    bitacora.append(f"{revisadas} columnas cuadran exactamente con la fila de totales del archivo")

    # "Todos los sectores" debe ser la suma de los cuatro sectores
    # En captación, "banca" agrupa BM + BD y "eacp" agrupa SOCAP + SOFIPO
    grupos = {"banca": ["bm", "bd"], "eacp": ["socap", "sofipo"]}
    todos = ["bm", "bd", "socap", "sofipo"]
    cruzadas = 0
    for c in [c for c in df.columns if c.startswith("total__")]:
        resto = c.split("__", 1)[1]
        grupo, _, var = resto.partition("__")
        if grupo in grupos:
            partes = [f"{s}__{var}" for s in grupos[grupo]]
        elif resto == "total":
            partes = [f"{s}__total" for s in todos]
        else:
            partes = [f"{s}__{resto}" for s in todos]
        if not all(p in df for p in partes):
            continue
        diferencia = (df[c] - df[partes].sum(axis=1)).abs()
        assert (diferencia == 0).all(), f"{hoja}: {c} no es la suma de sus sectores"
        cruzadas += 1
    if cruzadas:
        bitacora.append(f"{cruzadas} columnas agregadas = suma exacta de sus sectores, municipio por municipio")

    sin_id = df[df["clave_mun"] == CLAVE_NO_IDENTIFICADO]
    if len(sin_id):
        bitacora.append("Registro 99999 'No identificado' con población 0: "
                        "se conserva en totales y se excluye de indicadores por habitante")
    return bitacora


def limpiar_hoja(ruta: str, hoja: str) -> tuple[pd.DataFrame, list[str]]:
    df, totales = leer_hoja(ruta, hoja)
    df = tipar(df)
    return df, validar(df, totales, hoja)


INFO = ["clave_mun", "clave_edo", "region", "estado", "municipio",
        "poblacion_total", "poblacion_adulta", "poblacion_adulta_mujeres",
        "poblacion_adulta_hombres", "tipo_de_poblacion", "indice_de_rezago_social"]


def unir(infra: pd.DataFrame, capt: pd.DataFrame) -> pd.DataFrame:
    """Une ambas hojas por municipio verificando que la información general coincida."""
    comunes = [c for c in INFO if c in infra and c in capt]
    a = infra.set_index("clave_mun")[comunes[1:]]
    b = capt.set_index("clave_mun")[comunes[1:]]
    assert a.index.equals(b.index), "Las hojas no traen los mismos municipios"
    assert a.equals(b), "La información general difiere entre hojas"
    solo_capt = [c for c in capt.columns if c not in comunes]
    # En captación, "<sector>__total" es el total de cuentas (sin tarjetas de débito)
    capt = capt.rename(columns={c: c.replace("__total", "__cuentas_total")
                                for c in solo_capt if c.endswith("__total")})
    solo_capt = [c for c in capt.columns if c not in comunes]
    capt = capt.rename(columns={c: f"capt__{c}" for c in solo_capt})
    solo_capt = [f"capt__{c}" for c in solo_capt]
    return infra.merge(capt[["clave_mun"] + solo_capt], on="clave_mun", validate="1:1")
