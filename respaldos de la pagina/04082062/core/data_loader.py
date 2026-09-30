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
def cargar_parquet(nombre_archivo):
    ruta = CARPETA_DATOS / nombre_archivo
    if ruta.exists(): return pd.read_parquet(ruta)
    return None