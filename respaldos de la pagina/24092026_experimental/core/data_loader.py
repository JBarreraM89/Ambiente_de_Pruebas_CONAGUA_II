# -*- coding: utf-8 -*-
"""
Created on Mon Aug  3 11:53:53 2026
@author: dchable

Core Data Loader con Aceleración R-Tree (STRtree en RAM)
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
from pathlib import Path
from shapely.strtree import STRtree

# Configuración de rutas seguras
DIRECTORIO_RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = DIRECTORIO_RAIZ / "data"

def normalizar_clave(val):
    try: return str(int(float(val))).zfill(4)
    except: return str(val).strip().zfill(4)

# =======================================================
# 🚀 REPOSITORIO ESPACIAL CON ÍNDICE R-TREE (STRtree)
# =======================================================
class SpatialLayerRepository:
    """
    Repositorio espacial en memoria RAM.
    Utiliza el árbol binario STRtree de GEOS/Shapely para resolver
    intersecciones espaciales en O(log N) en lugar de O(N).
    """
    def __init__(self, gdf: gpd.GeoDataFrame):
        self.gdf = gdf.copy() if gdf is not None and not gdf.empty else gpd.GeoDataFrame()
        if not self.gdf.empty and 'geometry' in self.gdf.columns:
            valid_mask = self.gdf.geometry.notna() & ~self.gdf.geometry.is_empty
            self.clean_gdf = self.gdf[valid_mask].reset_index(drop=True)
            self.tree = STRtree(self.clean_gdf.geometry.values)
        else:
            self.clean_gdf = gpd.GeoDataFrame()
            self.tree = None

    def query_intersects(self, geom_objetivo) -> gpd.GeoDataFrame:
        """Retorna instantáneamente las entidades que intersectan usando el índice R-Tree."""
        if self.tree is None or geom_objetivo is None or geom_objetivo.is_empty:
            return self.clean_gdf.iloc[0:0]
            
        candidate_indices = self.tree.query(geom_objetivo, predicate="intersects")
        if len(candidate_indices) == 0:
            return self.clean_gdf.iloc[0:0]
        return self.clean_gdf.iloc[candidate_indices].copy()

    def query_clave(self, clave_ac: str) -> gpd.GeoDataFrame:
        """Búsqueda directa por clave de acuífero si la columna existe."""
        if self.clean_gdf.empty:
            return self.clean_gdf.iloc[0:0]
            
        col_cve = next((c for c in ['CLV_ACUI', 'CLAVE_SIGM', 'CLAVE', 'CLVE_ACUIF'] if c in self.clean_gdf.columns), None)
        if col_cve:
            cve_norm = normalizar_clave(clave_ac)
            return self.clean_gdf[self.clean_gdf[col_cve].apply(normalizar_clave) == cve_norm].copy()
        return self.clean_gdf.iloc[0:0]

# =======================================================
# 💾 FUNCIONES DE CARGA MAESTRAS (RETROCOMPATIBLES)
# =======================================================
@st.cache_resource(show_spinner=False)
def cargar_datos_maestros():
    ruta = CARPETA_DATOS / "Acuiferos_Dashboard_V4.geojson"
    if not ruta.exists(): 
        ruta_alt = CARPETA_DATOS / "limites_acuiferos_mx.geojson"
        if ruta_alt.exists(): ruta = ruta_alt
        else: return None
    try:
        gdf = gpd.read_file(ruta, encoding="utf-8")
        if gdf.crs is None: gdf = gdf.set_crs(epsg=4326)
        else: gdf = gdf.to_crs(epsg=4326)
        return gdf
    except Exception:
        return None

@st.cache_data(show_spinner=False)
def cargar_fraccion(nombre_capa):
    """Carga estándar que respeta exactamente los nombres de tus archivos."""
    ruta_parquet = CARPETA_DATOS / f"Fracciones_{nombre_capa}.parquet"
    if ruta_parquet.exists(): return gpd.read_parquet(ruta_parquet)
    ruta_geojson = CARPETA_DATOS / f"Fracciones_{nombre_capa}.geojson"
    if ruta_geojson.exists(): return gpd.read_file(ruta_geojson, encoding="utf-8")
    return None

@st.cache_resource(show_spinner=False)
def obtener_repositorio_fraccion(nombre_capa: str) -> SpatialLayerRepository:
    """Crea y almacena el índice R-Tree en memoria de la fracción solicitada."""
    gdf = cargar_fraccion(nombre_capa)
    return SpatialLayerRepository(gdf if gdf is not None else gpd.GeoDataFrame())

def consultar_fraccion_optimizada(nombre_capa: str, clave_ac: str, geom_acuifero=None) -> gpd.GeoDataFrame:
    """Consulta inteligente: busca por clave primero, y si no existe usa el STRtree."""
    repo = obtener_repositorio_fraccion(nombre_capa)
    res_clave = repo.query_clave(clave_ac)
    if not res_clave.empty:
        return res_clave
    if geom_acuifero is not None:
        return repo.query_intersects(geom_acuifero)
    return repo.clean_gdf.iloc[0:0]

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
            col_encontrada = next((c for c in [col_cve, 'CLAVE', 'Clave'] if c in df.columns), None)
            if col_encontrada:
                df[col_encontrada] = df[col_encontrada].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(padding)
            return df
        except: 
            return None
    return None

@st.cache_data(show_spinner="Cargando catálogo oficial...")
def cargar_catalogo(nombre_archivo: str = "Acuiferos_2026.csv") -> pd.DataFrame:
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