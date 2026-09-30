# -*- coding: utf-8 -*-
"""
Created on Mon Aug  3 11:53:53 2026

@author: dchable
"""

# core/data_loader.py
import streamlit as st
import geopandas as gpd
import pandas as pd
from pathlib import Path

# Configuración de rutas seguras
DIRECTORIO_RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = DIRECTORIO_RAIZ / "data"

@st.cache_data(show_spinner=False)
def cargar_datos_maestros():
    ruta = CARPETA_DATOS / "Acuiferos_Dashboard_V4.geojson"
    if not ruta.exists(): return None
    return gpd.read_file(ruta, encoding="utf-8")

@st.cache_data(show_spinner=False)
def cargar_fraccion(nombre_capa):
    ruta_parquet = CARPETA_DATOS / f"Fracciones_{nombre_capa}.parquet"
    if ruta_parquet.exists(): return gpd.read_parquet(ruta_parquet)
    ruta_geojson = CARPETA_DATOS / f"Fracciones_{nombre_capa}.geojson"
    if ruta_geojson.exists(): return gpd.read_file(ruta_geojson, encoding="utf-8")
    return None

@st.cache_data(show_spinner=False)
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

@st.cache_data(show_spinner=False)
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

@st.cache_data(show_spinner=False)
def cargar_parquet(nombre_archivo, col_cve="CLV_ACUI", padding=4):
    ruta = CARPETA_DATOS / nombre_archivo
    if ruta.exists():
        try:
            df = pd.read_parquet(ruta)
            # Buscar dinámicamente si existe la columna de clave para normalizarla
            col_encontrada = next((c for c in [col_cve, 'CLAVE', 'Clave'] if c in df.columns), None)
            if col_encontrada:
                df[col_encontrada] = df[col_encontrada].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(padding)
            return df
        except: 
            return None
    return None

@st.cache_data(show_spinner="Cargando catálogo oficial...")
def cargar_catalogo(nombre_archivo: str) -> pd.DataFrame:
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        return pd.DataFrame()
    df = pd.read_csv(ruta, encoding="utf-8")
    if 'CLAVE_SIGM' in df.columns:
        df["CLAVE_SIGM"] = df["CLAVE_SIGM"].astype(str).str.zfill(4)
    return df

@st.cache_data(show_spinner=False)
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