# -*- coding: utf-8 -*-
"""
Core Data Loader Optimizado para Streamlit Cloud
Usa Predicate Pushdown con inspección de esquema (PyArrow).
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path

DIRECTORIO_RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = DIRECTORIO_RAIZ / "data"

def normalizar_clave(val):
    try: return str(int(float(val))).zfill(4)
    except: return str(val).strip().zfill(4)

@st.cache_data(show_spinner=False, max_entries=1, ttl=3600)
def cargar_datos_maestros():
    ruta = CARPETA_DATOS / "Acuiferos_Dashboard_V4.parquet"
    if ruta.exists(): return gpd.read_parquet(ruta)
    # Fallback por si sigue siendo geojson
    ruta_alt = CARPETA_DATOS / "Acuiferos_Dashboard_V4.geojson"
    if ruta_alt.exists(): return gpd.read_file(ruta_alt)
    return None

@st.cache_data(show_spinner=False, max_entries=20, ttl=3600)
def cargar_fraccion(nombre_capa, clave_ac=None):
    ruta_parquet = CARPETA_DATOS / f"Fracciones_{nombre_capa}.parquet"
    if not ruta_parquet.exists(): return None

    if clave_ac:
        clave_norm = normalizar_clave(clave_ac)
        try:
            # 1. Espiar el esquema del parquet sin cargarlo a la RAM
            esquema = pq.read_schema(ruta_parquet)
            nombres_cols = esquema.names
            
            # 2. Buscar cómo se llama realmente la columna de la clave
            col_cve = next((c for c in ['CLV_ACUI', 'CLAVE_SIGM', 'CLAVE', 'CLVE_ACUIF'] if c in nombres_cols), None)
            
            if col_cve:
                # 3. Intentar filtro ultra-rápido asumiendo que es texto
                try:
                    gdf = gpd.read_parquet(ruta_parquet, filters=[(col_cve, '==', clave_norm)])
                    if not gdf.empty: return gdf
                except: pass
                
                # 4. Si falló, intentar filtro ultra-rápido asumiendo que es número (ej. 101 en vez de "0101")
                try:
                    gdf_int = gpd.read_parquet(ruta_parquet, filters=[(col_cve, '==', int(clave_norm))])
                    if not gdf_int.empty: return gdf_int
                except: pass
        except Exception:
            pass
            
        # 5. EL PARACAÍDAS (Solo llegará aquí si la capa de verdad no tiene clave)
        gdf = gpd.read_parquet(ruta_parquet)
        col_cve_fb = next((c for c in ['CLV_ACUI', 'CLAVE_SIGM', 'CLAVE', 'CLVE_ACUIF'] if c in gdf.columns), None)
        if col_cve_fb:
            gdf['TEMP_CVE'] = gdf[col_cve_fb].apply(normalizar_clave)
            return gdf[gdf['TEMP_CVE'] == clave_norm].drop(columns=['TEMP_CVE']).copy()
        return gpd.GeoDataFrame()
    else:
        return gpd.read_parquet(ruta_parquet)

@st.cache_data(show_spinner=False, max_entries=5, ttl=3600)
def cargar_excel(nombre_archivo, col_cve=None, padding=4):
    ruta = CARPETA_DATOS / nombre_archivo
    if ruta.exists():
        try:
            df = pd.read_excel(ruta)
            if col_cve and col_cve in df.columns:
                df[col_cve] = df[col_cve].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(padding)
            return df
        except: return None
    return None

@st.cache_data(show_spinner=False, max_entries=5, ttl=3600)
def cargar_csv(nombre_archivo, col_cve=None, padding=4):
    ruta = CARPETA_DATOS / nombre_archivo
    if ruta.exists():
        try:
            df = pd.read_csv(ruta)
            if col_cve and col_cve in df.columns:
                df[col_cve] = df[col_cve].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(padding)
            return df
        except: return None
    return None

@st.cache_data(show_spinner=False, max_entries=10, ttl=3600)
def cargar_parquet(nombre_archivo, col_cve="CLV_ACUI", padding=4):
    ruta = CARPETA_DATOS / nombre_archivo
    if ruta.exists():
        try:
            df = pd.read_parquet(ruta)
            col_encontrada = next((c for c in [col_cve, 'CLAVE', 'Clave'] if c in df.columns), None)
            if col_encontrada:
                df[col_encontrada] = df[col_encontrada].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(padding)
            return df
        except: return None
    return None

@st.cache_data(show_spinner="Cargando catálogo oficial...", max_entries=1, ttl=7200)
def cargar_catalogo(nombre_archivo: str = "Acuiferos_2026.csv") -> pd.DataFrame:
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists(): return pd.DataFrame()
    df = pd.read_csv(ruta, encoding="utf-8")
    if 'CLAVE_SIGM' in df.columns: df["CLAVE_SIGM"] = df["CLAVE_SIGM"].astype(str).str.zfill(4)
    return df

@st.cache_data(show_spinner=False, max_entries=2, ttl=3600)
def cargar_historico_excel(nombre_archivo: str, anio: int) -> dict:
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists(): return {}
    df = pd.read_excel(ruta)
    df.columns = df.columns.str.upper().str.strip() 
    col_clave = 'CLAVE' if 'CLAVE' in df.columns else ('CLAVE_SIGM' if 'CLAVE_SIGM' in df.columns else None)
    if not col_clave: return {}
    col_dma = f"DMA_{anio}"
    col_veas = f"VEAS_{anio}"
    if col_dma not in df.columns or col_veas not in df.columns:
        return {"error_columnas": True, "dma": col_dma, "veas": col_veas}
    df[col_clave] = df[col_clave].astype(str).str.zfill(4)
    dict_hist = {}
    for _, row in df.iterrows():
        val_dma = float(row[col_dma]) if pd.notna(row[col_dma]) else "N/D"
        val_veas = float(row[col_veas]) if pd.notna(row[col_veas]) else "N/D"
        dict_hist[row[col_clave]] = {'DMA': val_dma, 'VEAS': val_veas}
    return dict_hist
