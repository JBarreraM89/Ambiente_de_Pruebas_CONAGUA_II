# -*- coding: utf-8 -*-
"""
Core Data Loader Optimizado para Streamlit Cloud
Usa Predicate Pushdown con GeoParquet para ahorrar RAM.
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
from pathlib import Path

# Configuración de rutas seguras
DIRECTORIO_RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = DIRECTORIO_RAIZ / "data"

def normalizar_clave(val):
    try: return str(int(float(val))).zfill(4)
    except: return str(val).strip().zfill(4)

# =======================================================
# 1. CARGA DE DATOS MAESTROS (CON LÍMITE DE CACHÉ)
# =======================================================
@st.cache_data(show_spinner=False, max_entries=1, ttl=3600)
def cargar_datos_maestros():
    """Carga el polígono nacional. Solo mantiene 1 en memoria."""
    ruta = CARPETA_DATOS / "Acuiferos_Dashboard_V4.parquet"
    if ruta.exists():
        return gpd.read_parquet(ruta)
    return None

# =======================================================
# 2. LECTURA INTELIGENTE (PREDICATE PUSHDOWN) PARA GEOPARQUET
# =======================================================
@st.cache_data(show_spinner=False, max_entries=20, ttl=3600)
def cargar_fraccion(nombre_capa, clave_ac=None):
    """
    Si se pasa clave_ac, lee SOLO la información de ese acuífero desde el disco.
    Si no se pasa, lee todo (usar con precaución).
    """
    ruta_parquet = CARPETA_DATOS / f"Fracciones_{nombre_capa}.parquet"
    if not ruta_parquet.exists(): 
        return None

    if clave_ac:
        clave_norm = normalizar_clave(clave_ac)
        try:
            # MAGIA: PyArrow filtra a nivel de disco antes de subir a la RAM
            gdf = gpd.read_parquet(ruta_parquet, filters=[('CLV_ACUI', '==', clave_norm)])
            if not gdf.empty: 
                return gdf
        except Exception:
            pass # Si falla (ej. la columna no se llama CLV_ACUI), pasa al fallback
        
        # Fallback: Cargar todo y filtrar en memoria
        gdf = gpd.read_parquet(ruta_parquet)
        col_cve = next((c for c in ['CLV_ACUI', 'CLAVE_SIGM', 'CLAVE', 'CLVE_ACUIF'] if c in gdf.columns), None)
        if col_cve:
            gdf['TEMP_CVE'] = gdf[col_cve].apply(normalizar_clave)
            return gdf[gdf['TEMP_CVE'] == clave_norm].drop(columns=['TEMP_CVE']).copy()
        return gpd.GeoDataFrame()
    else:
        # Si no se pasa clave, carga el archivo completo
        return gpd.read_parquet(ruta_parquet)

# =======================================================
# 3. LECTURA DE TABLAS (EXCEL, CSV, PARQUET) CON LÍMITES
# =======================================================
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
        except: 
            return None
    return None

@st.cache_data(show_spinner="Cargando catálogo oficial...", max_entries=1, ttl=7200)
def cargar_catalogo(nombre_archivo: str = "Acuiferos_2026.csv") -> pd.DataFrame:
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        return pd.DataFrame()
    df = pd.read_csv(ruta, encoding="utf-8")
    if 'CLAVE_SIGM' in df.columns:
        df["CLAVE_SIGM"] = df["CLAVE_SIGM"].astype(str).str.zfill(4)
    return df

@st.cache_data(show_spinner=False, max_entries=2, ttl=3600)
def cargar_historico_excel(nombre_archivo: str, anio: int) -> dict:
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        return {}
        
    df = pd.read_excel(ruta)
    df.columns = df.columns.str.upper().str.strip() 
    
    col_clave = 'CLAVE' if 'CLAVE' in df.columns else ('CLAVE_SIGM' if 'CLAVE_SIGM' in df.columns else None)
    if not col_clave:
        return {}
        
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
