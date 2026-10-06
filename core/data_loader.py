# -*- coding: utf-8 -*-
"""
Core Data Loader optimizado para Streamlit Cloud.
Usa predicate pushdown con inspección de esquema (PyArrow).

Cambios respecto a la versión anterior:
- `cargar_fraccion`: UNA sola lectura filtrada según el tipo real de la columna de
  clave. Un resultado vacío es un resultado válido (ya no dispara la lectura
  completa del parquet, que en unidades_riego/municipios pesa 60-80 MB). La
  lectura completa solo ocurre si el filtro lanza una excepción.
- Normalización de claves unificada (`normalizar_clave` / `normalizar_serie_clave`):
  sin el `.replace('.0', '')` literal y sin '0nan' para valores nulos.
- Sin `except:` desnudos: los errores se registran con `logging`.
- CSV con respaldo de codificación (utf-8-sig -> cp1252).
- `cargar_datos_maestros` avisa con st.error si falta el archivo.

Contratos que se conservan (para no romper las páginas):
- `cargar_excel/csv/parquet` devuelven None si fallan.
- `cargar_fraccion` devuelve None si no existe la capa y un GeoDataFrame vacío si la
  capa no tiene columna de clave.
- `cargar_historico_excel` sigue devolviendo {"error_columnas": True, ...} cuando
  faltan columnas.
"""

import logging
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import streamlit as st

logger = logging.getLogger(__name__)

DIRECTORIO_RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = DIRECTORIO_RAIZ / "data"

COLUMNAS_CLAVE = ("CLV_ACUI", "CLAVE_SIGM", "CLAVE", "CLVE_ACUIF")
_VALORES_NULOS = ["", "nan", "none", "<na>", "nat"]


# ==========================================
# NORMALIZACIÓN DE CLAVES
# ==========================================
def normalizar_clave(val, padding: int = 4) -> str:
    """Normaliza una clave de acuífero a texto con ceros a la izquierda ('101.0' -> '0101').

    Devuelve '' si el valor es nulo, de modo que nunca coincide con una clave válida.
    """
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    texto = str(val).strip()
    if texto.lower() in _VALORES_NULOS:
        return ""
    try:
        return str(int(float(texto))).zfill(padding)
    except (ValueError, OverflowError):
        return texto.zfill(padding)


def normalizar_serie_clave(serie: pd.Series, padding: int = 4) -> pd.Series:
    """Versión vectorizada de `normalizar_clave`. Los nulos quedan como ''."""
    s = serie.astype("string").str.strip().fillna("")
    s = s.str.replace(r"\.0+$", "", regex=True)
    s = s.mask(s.str.lower().isin(_VALORES_NULOS), "")
    s = s.mask(s != "", s.str.zfill(padding))
    return s.astype(object)


# ==========================================
# DATOS MAESTROS
# ==========================================
def _leer_gdf_maestro() -> Optional[gpd.GeoDataFrame]:
    """Lectura cruda (sin caché) del GeoDataFrame maestro: GeoParquet y, si no, GeoJSON."""
    ruta = CARPETA_DATOS / "Acuiferos_Dashboard_V4.parquet"
    if ruta.exists():
        return gpd.read_parquet(ruta)
    ruta_alt = CARPETA_DATOS / "Acuiferos_Dashboard_V4.geojson"
    if ruta_alt.exists():
        logger.warning("Usando GeoJSON como respaldo; convertir a GeoParquet mejora la velocidad.")
        return gpd.read_file(ruta_alt)
    return None


@st.cache_data(show_spinner=False, max_entries=1, ttl=3600)
def _leer_datos_maestros() -> Optional[gpd.GeoDataFrame]:
    return _leer_gdf_maestro()


def cargar_datos_maestros() -> Optional[gpd.GeoDataFrame]:
    """GeoDataFrame maestro de acuíferos (copia segura por llamada). None si no hay archivo."""
    gdf = _leer_datos_maestros()
    if gdf is None:
        st.error("❌ No se encontró 'Acuiferos_Dashboard_V4.parquet' (ni .geojson) en la carpeta data/.")
    return gdf


cargar_datos_maestros.clear = _leer_datos_maestros.clear  # compatibilidad con .clear()


@st.cache_resource(show_spinner=False, max_entries=1, ttl=3600)
def _leer_datos_maestros_compartido() -> Optional[gpd.GeoDataFrame]:
    return _leer_gdf_maestro()


def obtener_datos_maestros_compartidos() -> Optional[gpd.GeoDataFrame]:
    """Igual que `cargar_datos_maestros`, pero SIN copiar el GeoDataFrame en cada llamada.

    Es mucho más rápido y ahorra memoria, pero el objeto es compartido entre sesiones:
    NO debe modificarse (usar `.copy()` si se necesita cambiar algo). Adoptarlo página
    por página, después de verificar que ninguna modifica el GeoDataFrame en sitio.
    """
    gdf = _leer_datos_maestros_compartido()
    if gdf is None:
        st.error("❌ No se encontró 'Acuiferos_Dashboard_V4.parquet' (ni .geojson) en la carpeta data/.")
    return gdf


# ==========================================
# FRACCIONES (CAPAS GRANDES, FILTRADAS POR ACUÍFERO)
# ==========================================
def _valores_filtro(tipo: pa.DataType, clave: str) -> list:
    """Valores equivalentes de la clave según el tipo de la columna en el parquet."""
    if pa.types.is_integer(tipo):
        return [int(clave)]
    if pa.types.is_floating(tipo):
        return [float(clave)]
    sin_ceros = clave.lstrip("0") or "0"
    return [clave] if sin_ceros == clave else [clave, sin_ceros]


@st.cache_data(show_spinner=False, max_entries=20, ttl=3600)
def _cargar_fraccion_cache(nombre_capa: str, clave_norm: Optional[str]):
    ruta = CARPETA_DATOS / f"Fracciones_{nombre_capa}.parquet"
    if not ruta.exists():
        return None

    # Sin clave: capa completa (puede pesar decenas de MB; usar solo si es necesario).
    if not clave_norm:
        return gpd.read_parquet(ruta)

    col_cve = None
    try:
        esquema = pq.read_schema(ruta)
        col_cve = next((c for c in COLUMNAS_CLAVE if c in esquema.names), None)
        if col_cve is None:
            return gpd.GeoDataFrame()  # la capa no trae clave de acuífero
        valores = _valores_filtro(esquema.field(col_cve).type, clave_norm)
        # Un resultado vacío es válido: el acuífero simplemente no tiene elementos en la capa.
        return gpd.read_parquet(ruta, filters=[(col_cve, "in", valores)])
    except Exception:
        logger.exception("Filtro por parquet falló en '%s'; se usa lectura completa.", nombre_capa)

    # Respaldo (solo si el filtro lanzó una excepción): lectura completa + filtro en memoria.
    gdf = gpd.read_parquet(ruta)
    col = col_cve or next((c for c in COLUMNAS_CLAVE if c in gdf.columns), None)
    if col is None:
        return gpd.GeoDataFrame()
    return gdf[normalizar_serie_clave(gdf[col]) == clave_norm].copy()


def cargar_fraccion(nombre_capa: str, clave_ac=None):
    """Capa 'Fracciones_<nombre_capa>.parquet' filtrada por acuífero.

    Normaliza la clave ANTES de entrar al caché, para que '101' y '0101' compartan entrada.
    """
    clave_norm = normalizar_clave(clave_ac) if clave_ac is not None else None
    return _cargar_fraccion_cache(nombre_capa, clave_norm)


cargar_fraccion.clear = _cargar_fraccion_cache.clear  # compatibilidad con .clear()


# ==========================================
# TABLAS (EXCEL / CSV / PARQUET)
# ==========================================
@st.cache_data(show_spinner=False, max_entries=5, ttl=3600)
def cargar_excel(nombre_archivo: str, col_cve: Optional[str] = None, padding: int = 4):
    """Lee un Excel de data/. Normaliza `col_cve` si existe. None si falla."""
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        logger.warning("No existe %s", ruta)
        return None
    try:
        df = pd.read_excel(ruta)
        if col_cve and col_cve in df.columns:
            df[col_cve] = normalizar_serie_clave(df[col_cve], padding)
        return df
    except Exception:
        logger.exception("No se pudo leer el Excel %s", nombre_archivo)
        return None


def _leer_csv_robusto(ruta: Path) -> pd.DataFrame:
    """Lee un CSV probando utf-8-sig y luego cp1252 (exportaciones de Excel)."""
    try:
        return pd.read_csv(ruta, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(ruta, encoding="cp1252")


@st.cache_data(show_spinner=False, max_entries=5, ttl=3600)
def cargar_csv(nombre_archivo: str, col_cve: Optional[str] = None, padding: int = 4):
    """Lee un CSV de data/. Normaliza `col_cve` si existe. None si falla."""
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        logger.warning("No existe %s", ruta)
        return None
    try:
        df = _leer_csv_robusto(ruta)
        if col_cve and col_cve in df.columns:
            df[col_cve] = normalizar_serie_clave(df[col_cve], padding)
        return df
    except Exception:
        logger.exception("No se pudo leer el CSV %s", nombre_archivo)
        return None


@st.cache_data(show_spinner=False, max_entries=10, ttl=3600)
def cargar_parquet(nombre_archivo: str, col_cve: str = "CLV_ACUI", padding: int = 4):
    """Lee un parquet tabular de data/. Normaliza la columna de clave. None si falla."""
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        logger.warning("No existe %s", ruta)
        return None
    try:
        df = pd.read_parquet(ruta)
        col = next((c for c in (col_cve, "CLAVE", "Clave") if c in df.columns), None)
        if col:
            df[col] = normalizar_serie_clave(df[col], padding)
        return df
    except Exception:
        logger.exception("No se pudo leer el parquet %s", nombre_archivo)
        return None


@st.cache_data(show_spinner="Cargando catálogo oficial...", max_entries=1, ttl=7200)
def cargar_catalogo(nombre_archivo: str = "Acuiferos_2026.csv") -> pd.DataFrame:
    """Catálogo oficial de acuíferos. DataFrame vacío si el archivo no existe."""
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        logger.warning("No existe el catálogo %s", ruta)
        return pd.DataFrame()
    df = _leer_csv_robusto(ruta)
    if "CLAVE_SIGM" in df.columns:
        df["CLAVE_SIGM"] = normalizar_serie_clave(df["CLAVE_SIGM"])
    return df


@st.cache_data(show_spinner=False, max_entries=2, ttl=3600)
def cargar_historico_excel(nombre_archivo: str, anio: int) -> dict:
    """{clave: {'DMA': x, 'VEAS': y}} para el año dado ('N/D' si no hay dato).

    Si faltan las columnas del año devuelve {"error_columnas": True, "dma": ..., "veas": ...}
    (contrato heredado: las páginas ya lo consultan).
    """
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        return {}
    df = pd.read_excel(ruta)
    df.columns = df.columns.str.upper().str.strip()
    col_clave = next((c for c in ("CLAVE", "CLAVE_SIGM") if c in df.columns), None)
    if not col_clave:
        return {}
    col_dma, col_veas = f"DMA_{anio}", f"VEAS_{anio}"
    if col_dma not in df.columns or col_veas not in df.columns:
        return {"error_columnas": True, "dma": col_dma, "veas": col_veas}

    claves = normalizar_serie_clave(df[col_clave])
    dma = pd.to_numeric(df[col_dma], errors="coerce")
    veas = pd.to_numeric(df[col_veas], errors="coerce")
    return {
        clave: {
            "DMA": float(d) if pd.notna(d) else "N/D",
            "VEAS": float(v) if pd.notna(v) else "N/D",
        }
        for clave, d, v in zip(claves, dma, veas)
        if clave
    }
