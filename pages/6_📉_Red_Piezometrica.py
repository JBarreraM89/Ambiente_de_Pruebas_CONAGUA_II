# -*- coding: utf-8 -*-
"""
Módulo de Evaluación y Monitoreo Geohidrológico (Nivel Enterprise)
Diagnóstico físico con Kriging Ordinario, Variogramas, Isopiezas, Vectores de Flujo y Forecasting.
Desacoplamiento de modelo matemático vs renderizado para interactividad instantánea (<40 ms).
"""

import os
import io
import re
import html
import math
import json
import base64
import zipfile
import tempfile
import unicodedata
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from scipy.spatial import ConvexHull
from matplotlib.path import Path as MplPath

try:
    import geopandas as gpd
    from shapely.geometry import LineString, Point, Polygon, MultiPolygon, mapping
    GEOPANDAS_INSTALADO = True
except ImportError:
    GEOPANDAS_INSTALADO = False

# Importaciones del Core
from utils.styles import inyectar_css_oficial, banner_institucional
from core.data_loader import CARPETA_DATOS, cargar_catalogo, cargar_datos_maestros, DIRECTORIO_RAIZ
from core.pmtiles_server import asegurar_servidor_pmtiles, obtener_url_pmtiles

try:
    import datetime
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from core.word_utils import activar_ortografia_y_gramatica_es_mx, configurar_encabezado_repetible_y_paginacion
    DOCX_DISPONIBLE = True
except ImportError:
    DOCX_DISPONIBLE = False

# =======================================================
# ⚡ FUNCIÓN MÁGICA: Descargas Cero-Rerun (Scope Global)
# =======================================================
def generar_enlace_descarga(data, filename, mime, label):
    """Genera un enlace de descarga en Base64 que opera 100% en el cliente sin causar rerun en Streamlit."""
    b64 = base64.b64encode(data).decode()
    return f'<a href="data:{mime};base64,{b64}" download="{filename}" class="btn-descarga-html">{label}</a>'

# =======================================================
# 🎨 1. CONFIGURACIÓN E INYECCIÓN DE ESTILOS
# =======================================================
st.set_page_config(layout="wide", page_title="Red Piezométrica", page_icon="📉")
inyectar_css_oficial()
banner_institucional()

# ⚡ CSS AISLADO Y NEUTRALIZACIÓN DE CONFLICTOS CON styles.py
st.markdown("""
    <style>
        /* ========================================================= */
        /* 📏 0. ESTABILIZADOR DE PESTAÑAS (ELIMINA BRINCOS DE SCROLL)*/
        /* ========================================================= */
        div[data-testid="stTabs"] div[role="tabpanel"],
        div[data-testid="stTabs"] [data-baseweb="tab-panel"] {
            min-height: 880px !important;
        }

        /* Sub-pestañas del panel izquierdo conservan su tamaño natural */
        div[data-testid="stColumn"] div[data-testid="stTabs"] div[role="tabpanel"],
        div[data-testid="stColumn"] div[data-testid="stTabs"] [data-baseweb="tab-panel"] {
            min-height: auto !important;
        }

        /* ========================================================= */
        /* 🚨 1. ANULAR MARGEN DE 1.8rem DE styles.py EN BOTONES     */
        /* ========================================================= */
        [data-testid="stExpanderDetails"] button [data-testid="stMarkdownContainer"] p,
        [data-testid="stExpanderDetails"] button p,
        [data-testid="stExpanderDetails"] [data-testid="stFileUploader"] p {
            margin: 0 !important;
            margin-bottom: 0 !important;
            padding: 0 !important;
            line-height: 1 !important;
        }

        /* ========================================================= */
        /* 📍 2. BOTONES DE BARRA LATERAL                            */
        /* ========================================================= */
        section[data-testid="stSidebar"] button[kind="secondary"],
        section[data-testid="stSidebar"] button[data-baseweb="button"]:not([kind="primary"]),
        section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button {
            background-color: #e9ecef !important;
            border: 1px solid #ced4da !important;
            border-radius: 6px !important;
            color: #333333 !important;
            font-weight: 600 !important;
            width: 100% !important;
            min-height: 38px !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-decoration: none !important;
            transition: all 0.2s ease !important;
            margin-top: 4px !important;
        }
        section[data-testid="stSidebar"] button[kind="secondary"]:hover,
        section[data-testid="stSidebar"] button[data-baseweb="button"]:not([kind="primary"]):hover,
        section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button:hover {
            background-color: #dde2e6 !important;
            border-color: #adb5bd !important;
            color: #000000 !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        }
        section[data-testid="stSidebar"] button[kind="primary"] {
            border-radius: 6px !important;
            min-height: 38px !important;
            font-weight: 600 !important;
            margin-top: 4px !important;
        }

        /* ========================================================= */
        /* 🚀 3. BOTONES DE FRONTERAS DEL MODELO (CARGAR / LIMPIAR)  */
        /* ========================================================= */
        [data-testid="stExpanderDetails"] div[data-testid="stButton"] > button {
            height: 38px !important;
            min-height: 38px !important;
            max-height: 38px !important;
            border-radius: 6px !important;
            font-weight: 600 !important;
            font-size: 14px !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 14px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
            transition: all 0.2s ease !important;
        }
        [data-testid="stExpanderDetails"] div[data-testid="stButton"] > button div {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            height: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        /* Botón Limpiar (Gris) */
        [data-testid="stExpanderDetails"] div[data-testid="stButton"] > button[kind="secondary"] {
            background-color: #e9ecef !important;
            border: 1px solid #ced4da !important;
            color: #333333 !important;
        }
        [data-testid="stExpanderDetails"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
            background-color: #dde2e6 !important;
            border-color: #adb5bd !important;
            color: #000000 !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        }

        /* Botón Cargar (Guinda) */
        [data-testid="stExpanderDetails"] div[data-testid="stButton"] > button[kind="primary"] {
            background-color: #9F2241 !important;
            border: 1px solid #9F2241 !important;
            color: #ffffff !important;
        }
        [data-testid="stExpanderDetails"] div[data-testid="stButton"] > button[kind="primary"]:hover {
            background-color: #691C32 !important;
            border-color: #691C32 !important;
        }

        /* ========================================================= */
        /* 📦 4. CONTENEDOR DEL UPLOADER BLANCO + BOTÓN UPLOAD       */
        /* ========================================================= */
        [data-testid="stFileUploaderDropzone"],
        [data-testid="stFileUploader"] section {
            background-color: #ffffff !important;
            border: 1px solid #ced4da !important;
            border-radius: 8px !important;
        }

        [data-testid="stFileUploader"] button {
            background-color: #e9ecef !important;
            border: 1px solid #ced4da !important;
            border-radius: 6px !important;
            color: #333333 !important;
            font-size: 14px !important;
            font-weight: 600 !important;
            width: 100% !important;
            height: 38px !important;
            min-height: 38px !important;
            padding: 0 14px !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
            margin: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            transition: all 0.2s ease !important;
        }
        [data-testid="stFileUploader"] button:hover {
            background-color: #dde2e6 !important;
            border-color: #adb5bd !important;
            color: #000000 !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        }
        [data-testid="stFileUploader"] button div {
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            height: 100% !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        /* ========================================================= */
        /* 📥 5. ENLACES DE DESCARGAS SIG                            */
        /* ========================================================= */
        .btn-descarga-html {
            display: inline-flex !important; 
            align-items: center !important; 
            justify-content: center !important;
            background-color: #e9ecef !important; 
            border: 1px solid #ced4da !important; 
            border-radius: 6px !important;
            color: #333333 !important; 
            font-weight: 600 !important; 
            font-size: 12.5px !important; 
            padding: 0 6px !important;
            text-decoration: none !important; 
            width: 100% !important; 
            min-height: 38px !important;
            height: 38px !important;
            box-sizing: border-box !important; 
            transition: all 0.2s ease !important; 
            margin-top: 4px !important;
            margin-bottom: 4px !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
        }
        .btn-descarga-html:hover {
            background-color: #dde2e6 !important;
            border-color: #adb5bd !important;
            color: #000000 !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        }
    </style>
""", unsafe_allow_html=True)

st.subheader("📉 Red de Monitoreo Geohidrológico")
st.caption("Validación Física: Evaluación espacial, temporal, modelación geostadística de flujo y proyectiva.")

# =======================================================
# 🏛️ 1.5 CARGA DE ESTILOS OFICIALES SGM
# =======================================================
@st.cache_data(show_spinner=False)
def cargar_estilos_sgm_oficiales():
    carpeta_geo = DIRECTORIO_RAIZ / "data" / "geologia"
    ruta_json = carpeta_geo / "estilos_oficiales_sgm.json"
    if ruta_json.exists():
        try:
            with open(ruta_json, 'r', encoding='utf-8') as f:
                return json.load(f), "Catálogo Oficial SGM (3,024 reglas QGIS)"
        except Exception:
            pass
    return {}, "Norma Cartográfica General SGM"

DICCIONARIO_SGM_GLOBAL, ORIGEN_SGM_GLOBAL = cargar_estilos_sgm_oficiales()

TABLA_CROMATICA_RESPALDO = {
    "Q(AL)": "#FFF5AF", "ALUVION": "#FFF5AF", "ALUVIÓN": "#FFF5AF",
    "Q(AR)": "#FFE696", "ARENA": "#FFE696", "Q(CO)": "#E6CDA0", "CONGLOMERADO": "#E6CDA0",
    "Q(LA)": "#EBEBBE", "LACUSTRE": "#EBEBBE", "QPT(B)": "#800080", "BASALTO": "#800080",
    "QPT(A)": "#C33278", "ANDESITA": "#B43264", "TPA(A)": "#B43264",
    "TPA(R)": "#ED5F7D", "RIOLITA": "#ED5F7D", "TPA(D)": "#F07D3C", "DACITA": "#F07D3C",
    "TPA(TR)": "#F7AFAF", "TOBA RIOLITICA": "#F7AFAF", "TPA(TA)": "#B98CC3",
    "K(CZ)": "#2887CD", "CALIZA": "#2887CD", "KI(CZ)": "#0F5FAF", "KS(CZ)": "#5FAFE6",
    "K(LU)": "#9BB95A", "LUTITA": "#9BB95A", "K(AR)": "#BED273", "ARENISCA": "#BED273",
    "GR": "#EB3732", "GRANITO": "#EB3732", "GD": "#D74B46", "GRANODIORITA": "#D74B46",
    "AGUA": "#A6CAE8"
}

def resolver_color_oficial(clave_sgm, litologia, roca):
    for val in [clave_sgm, litologia, roca]:
        if val is not None and pd.notna(val):
            txt = str(val).strip().upper()
            if txt in DICCIONARIO_SGM_GLOBAL:
                return DICCIONARIO_SGM_GLOBAL[txt]
            for k_estilo, hex_col in DICCIONARIO_SGM_GLOBAL.items():
                if len(k_estilo) >= 3 and (k_estilo == txt or k_estilo in txt):
                    return hex_col
            if txt in TABLA_CROMATICA_RESPALDO:
                return TABLA_CROMATICA_RESPALDO[txt]

    texto_eval = f"{clave_sgm} {litologia} {roca}".upper()
    if any(k in texto_eval for k in ["ALUV", "ALUVION", "ALUVIÓN", "SUELO"]): return "#FFF5AF"
    if any(k in texto_eval for k in ["BASALT", "BASÁLT"]): return "#800080"
    if any(k in texto_eval for k in ["ANDESIT", "ANDESÍT"]): return "#B43264"
    if any(k in texto_eval for k in ["RIOLIT", "RIOLÍT"]): return "#ED5F7D"
    if any(k in texto_eval for k in ["CALIZ", "CALÍZ"]): return "#2887CD"
    if any(k in texto_eval for k in ["LUTIT", "LUTÍT"]): return "#9BB95A"
    if any(k in texto_eval for k in ["ARENISC", "ARENA"]): return "#BED273"
    if any(k in texto_eval for k in ["GRANIT", "GRANOD"]): return "#EB3732"
    if "AGUA" in texto_eval: return "#A6CAE8"
    return "#B0BEC5"

# =======================================================
# 🛰️ 2.15 MOTOR DE AUTODETECCIÓN ESPACIAL DE ACUÍFEROS
# =======================================================
gdf_m = cargar_datos_maestros()

def auto_identificar_acuifero_por_coordenadas(lat, lon, gdf_consulta):
    try:
        val_lat = float(lat)
        val_lon = -abs(float(lon))
        pt_geom = Point(val_lon, val_lat)
        
        if gdf_consulta is None or gdf_consulta.empty:
            return None
        if gdf_consulta.crs is None:
            gdf_consulta = gdf_consulta.set_crs(epsg=4326)
        
        idx_posibles = list(gdf_consulta.sindex.intersection(pt_geom.bounds))
        if not idx_posibles:
            idx_posibles = list(gdf_consulta.sindex.intersection(pt_geom.buffer(0.005).bounds))
            
        if idx_posibles:
            candidatos = gdf_consulta.iloc[idx_posibles]
            coincidencias = candidatos[candidatos.geometry.contains(pt_geom)]
            if coincidencias.empty:
                coincidencias = candidatos[candidatos.geometry.intersects(pt_geom.buffer(0.001))]
                
            if not coincidencias.empty:
                fila = coincidencias.iloc[0]
                cve = str(fila.get('CLV_ACUI', fila.get('CLAVE_SIGM', ''))).strip().zfill(4)
                nom = str(fila.get('NOM_ACUI', fila.get('ACUÍFERO', ''))).strip()
                area = float(fila.get('AREA_KM2', 0.0))
                edo = str(fila.get('NOM_EDO', fila.get('ESTADO', ''))).strip()
                return {"clave": cve, "nombre": nom, "area": area, "estado": edo}
    except Exception:
        pass
    return None

# =======================================================
# 🏢 2.1.B CARGA E INTEGRACIÓN DE CONCESIONES REPDA (INCISO D)
# =======================================================
@st.cache_data(show_spinner=False)
def cargar_resumen_repda(clave_acuifero):
    """
    Carga el balance de derechos de extracción de aguas subterráneas (REPDA oficial CONAGUA)
    y el conteo oficial de aprovechamientos de data/REPDA.xlsx y data/coordenadas_repda_sep25.
    """
    if not clave_acuifero:
        return None
    try:
        cve_str = str(clave_acuifero).strip()
        cve_str4 = cve_str.zfill(4)
        cve_int = int(cve_str)
    except Exception:
        return None

    resumen = {
        "clave": cve_str4,
        "nombre": "",
        "volumen_total_hm3": 0.0,
        "volumen_total_m3": 0.0,
        "total_aprovechamientos": 0,
        "df_usos": pd.DataFrame(),
        "uso_predominante": "No especificado",
        "pct_predominante": 0.0,
        "conteo_usos": {}
    }

    ruta_repda = os.path.join("data", "REPDA.xlsx")
    if os.path.exists(ruta_repda):
        try:
            df_repda = pd.read_excel(ruta_repda)
            col_cve = df_repda.columns[0]
            match = df_repda[df_repda[col_cve].astype(str).str.strip().str.zfill(4) == cve_str4]
            if match.empty:
                match = df_repda[df_repda[col_cve].astype(str).str.strip() == str(cve_int)]
            
            if not match.empty:
                r = match.iloc[0]
                resumen["nombre"] = str(r.get('Acuífero', r.get('Acu\u00edfero', ''))).strip()
                vol_tot = float(r.get('Volumen total (hm3/año)', r.get('Volumen total (hm3/a\u00f1o)', 0.0)) or 0.0)
                resumen["volumen_total_hm3"] = vol_tot
                resumen["volumen_total_m3"] = vol_tot * 1e6

                usos_cols = [c for c in df_repda.columns if '(hm3/' in c and 'total' not in c.lower() and 'porcentaje' not in c.lower()]
                desglose = []
                for c in usos_cols:
                    val = float(r.get(c, 0.0) or 0.0)
                    if val > 0:
                        nombre_uso = c.split('(')[0].strip()
                        desglose.append({
                            'Uso': nombre_uso,
                            'Volumen_hm3': round(val, 4),
                            'Volumen_m3': round(val * 1e6, 2)
                        })
                df_u = pd.DataFrame(desglose)
                if not df_u.empty:
                    df_u['Pct_Volumen'] = (df_u['Volumen_hm3'] / vol_tot * 100.0) if vol_tot > 0 else 0.0
                    df_u = df_u.sort_values(by='Volumen_hm3', ascending=False)
                    resumen["df_usos"] = df_u
                    resumen["uso_predominante"] = df_u.iloc[0]['Uso']
                    resumen["pct_predominante"] = float(df_u.iloc[0]['Pct_Volumen'])
        except Exception:
            pass

    # Conteo de aprovechamientos (prioriza coordenadas_repda_sep25.parquet, fallback a Aprovechamientos.parquet)
    ruta_sep25_pq = os.path.join("data", "coordenadas_repda_sep25.parquet")
    ruta_sep25_xlsx = os.path.join("data", "coordenadas_repda_sep25.xlsx")
    if os.path.exists(ruta_sep25_xlsx) and (not os.path.exists(ruta_sep25_pq) or os.path.getmtime(ruta_sep25_xlsx) > os.path.getmtime(ruta_sep25_pq)):
        try:
            df_all = pd.read_excel(ruta_sep25_xlsx)
            df_all.to_parquet(ruta_sep25_pq, index=False, engine="pyarrow", compression="snappy")
        except Exception:
            pass

    aprov_cargados = False
    if os.path.exists(ruta_sep25_pq) and cve_int > 0:
        try:
            sub_ap = pd.read_parquet(ruta_sep25_pq, filters=[('AC_HOM', '==', cve_int)])
            if not sub_ap.empty:
                resumen["total_aprovechamientos"] = len(sub_ap)
                col_u = next((c for c in sub_ap.columns if c.strip().upper() in ['D_USO_TIT', 'USOAGUA', 'USO']), None)
                if col_u:
                    resumen["conteo_usos"] = sub_ap[col_u].value_counts().to_dict()
                aprov_cargados = True
        except Exception:
            pass

    if not aprov_cargados:
        ruta_aprov = os.path.join("data", "Aprovechamientos.parquet")
        if os.path.exists(ruta_aprov):
            try:
                df_aprov = pd.read_parquet(ruta_aprov)
                sub_ap = df_aprov[df_aprov['Cve_Acuif'].astype(str).str.strip().str.zfill(4) == cve_str4]
                if sub_ap.empty:
                    sub_ap = df_aprov[df_aprov['Cve_Acuif'].astype(str).str.strip() == str(cve_int)]
                resumen["total_aprovechamientos"] = len(sub_ap)
                if not sub_ap.empty and 'Uso' in sub_ap.columns:
                    resumen["conteo_usos"] = sub_ap['Uso'].value_counts().to_dict()
            except Exception:
                pass

    return resumen


def get_repda_uso_color(uso_str):
    u = str(uso_str).upper()
    if 'AGR' in u: return '#16a34a'
    if 'URB' in u or 'PUBL' in u: return '#2563eb'
    if 'IND' in u: return '#d97706'
    if 'SERV' in u or 'COMER' in u: return '#9333ea'
    if 'DOM' in u: return '#06b6d4'
    if 'DIF' in u or 'MULT' in u: return '#ec4899'
    if 'PEC' in u: return '#84cc16'
    return '#64748b'


def cargar_concesiones_repda_puntos(clave_acuifero, custom_df=None):
    """
    Carga pozos y aprovechamientos georreferenciados con volumen concesionado.
    Prioriza archivo cargado por el usuario (custom_df); de lo contrario consulta data/coordenadas_repda_sep25.
    Retorna: (df_puntos, geojson_str, tiene_puntos)
    """
    df_raw = None
    if custom_df is not None and not custom_df.empty:
        df_raw = custom_df.copy()
    else:
        try:
            cve_int = int(str(clave_acuifero).strip()) if clave_acuifero else 0
        except Exception:
            cve_int = 0

        ruta_pq = os.path.join("data", "coordenadas_repda_sep25.parquet")
        ruta_xlsx = os.path.join("data", "coordenadas_repda_sep25.xlsx")

        # Caching automático de coordenadas_repda_sep25.xlsx a parquet para lectura en milisegundos
        if os.path.exists(ruta_xlsx):
            if not os.path.exists(ruta_pq) or os.path.getmtime(ruta_xlsx) > os.path.getmtime(ruta_pq):
                try:
                    df_all = pd.read_excel(ruta_xlsx)
                    df_all.to_parquet(ruta_pq, index=False, engine="pyarrow", compression="snappy")
                except Exception:
                    pass

        if os.path.exists(ruta_pq) and cve_int > 0:
            try:
                df_raw = pd.read_parquet(ruta_pq, filters=[("AC_HOM", "==", cve_int)])
            except Exception:
                df_raw = None

        if df_raw is None or df_raw.empty:
            ruta_core = os.path.join("core", "pozos_consolidados.xlsx")
            if os.path.exists(ruta_core):
                try:
                    df_pc = pd.read_excel(ruta_core, sheet_name="REPDA_CONAGUA")
                    if "CVE_ACU" in df_pc.columns:
                        sub = df_pc[df_pc["CVE_ACU"] == cve_int]
                        df_raw = sub if not sub.empty else df_pc
                    else:
                        df_raw = df_pc
                except Exception:
                    df_raw = None

    if df_raw is None or df_raw.empty:
        return pd.DataFrame(), '{"type": "FeatureCollection", "features": []}', False

    col_lon = next((c for c in df_raw.columns if c.strip().upper() in ["LONDEC", "LONGITUD", "LON", "LONG"]), None)
    col_lat = next((c for c in df_raw.columns if c.strip().upper() in ["LATDEC", "LATITUD", "LAT"]), None)
    if not col_lon or not col_lat:
        return pd.DataFrame(), '{"type": "FeatureCollection", "features": []}', False

    col_vol = next((c for c in df_raw.columns if c.strip().upper() in ["VOLEXTANUA", "VOLUMEN", "VOL_EXT_M3", "VOLUMEN_M3", "VOL_M3", "VOL_EXT_HM3"]), None)
    col_uso = next((c for c in df_raw.columns if c.strip().upper() in ["D_USO_TIT", "USOAGUA", "USO", "USO_AGUA", "USO_SUB", "USO_TIT"]), None)
    col_titular = next((c for c in df_raw.columns if c.strip().upper() in ["TITULAR", "NOMBRE", "RAZON_SOCIAL", "PROPIETARIO"]), None)
    col_folio = next((c for c in df_raw.columns if c.strip().upper() in ["FOLIOREG", "FOLIO", "TITULO", "EXPEDIENTE"]), None)
    col_exp = next((c for c in df_raw.columns if c.strip().upper() in ["NO_EXPE", "EXPEDIENTE", "NUM_EXPEDIENTE", "NO_EXP"]), None)
    col_fecha = next((c for c in df_raw.columns if c.strip().upper() in ["FECHAREGI2", "FECHA", "FECHA_REGISTRO", "FECHAREG"]), None)
    col_prof = next((c for c in df_raw.columns if c.strip().upper() in ["PROFUND", "PROFUNDIDAD", "PROF"]), None)

    vol_series = pd.to_numeric(df_raw[col_vol], errors="coerce").fillna(0.0) if col_vol else pd.Series(0.0, index=df_raw.index)
    max_raw_vol = float(vol_series.max()) if not vol_series.empty else 1.0
    if max_raw_vol > 0 and max_raw_vol <= 500 and "HM3" in (col_vol.upper() if col_vol else ""):
        vol_series = vol_series * 1e6
        max_raw_vol = float(vol_series.max())
    if max_raw_vol <= 0:
        max_raw_vol = 1.0

    features = []
    recs = []
    for idx, row in df_raw.iterrows():
        try:
            lat = float(row[col_lat])
            lon = float(row[col_lon])
        except Exception:
            continue
        if np.isnan(lat) or np.isnan(lon) or lat == 0.0 or lon == 0.0:
            continue
        if abs(lon) > 80:
            lon = -abs(lon)

        vol_m3 = float(vol_series.loc[idx])
        vol_hm3 = round(vol_m3 / 1e6, 4)
        uso = str(row[col_uso]).strip() if col_uso and pd.notna(row.get(col_uso)) else "No Especificado"
        titular = str(row[col_titular]).strip() if col_titular and pd.notna(row.get(col_titular)) else "Sin Titular Registrado"
        folio = str(row[col_folio]).strip() if col_folio and pd.notna(row.get(col_folio)) else f"REPDA-{idx+1}"
        expediente = str(row[col_exp]).strip() if col_exp and pd.notna(row.get(col_exp)) else ""
        fecha_str = str(row[col_fecha])[:10] if col_fecha and pd.notna(row.get(col_fecha)) else ""
        prof = float(pd.to_numeric(row[col_prof], errors="coerce")) if col_prof and not pd.isna(row.get(col_prof)) else 0.0

        color = get_repda_uso_color(uso)
        radio_px = round(float(5.0 + 11.0 * np.sqrt(max(0.0, vol_m3) / max_raw_vol)), 1)

        prop = {
            "folio": folio,
            "expediente": expediente,
            "fecha": fecha_str,
            "titular": titular,
            "uso": uso,
            "volumen_m3": round(vol_m3, 1),
            "volumen_hm3": vol_hm3,
            "profundidad_m": round(prof, 1),
            "radio_px": radio_px,
            "color": color,
            "lat": round(lat, 5),
            "lon": round(lon, 5)
        }
        recs.append(prop)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": prop
        })

    df_puntos = pd.DataFrame(recs)
    geojson_str = json.dumps({"type": "FeatureCollection", "features": features})
    tiene_puntos = len(features) > 0
    return df_puntos, geojson_str, tiene_puntos

# =======================================================
# 📍 2.2 CONTROL Y CARGA DE PUNTOS ADICIONALES (MANUAL Y CSV)
# =======================================================
if "marcadores_piezo" not in st.session_state:
    st.session_state["marcadores_piezo"] = []
if "csv_uploader_key_piezo" not in st.session_state:
    st.session_state["csv_uploader_key_piezo"] = 0

@st.fragment
def renderizar_controles_puntos_piezo():
    tab_m, tab_c = st.tabs(["✍️ Manual", "📁 Carga CSV"])
    
    with tab_m:
        with st.form(key="form_manual_piezo", clear_on_submit=True):
            nom = st.text_input("Identificador:", placeholder="Ej. Pozo San Bernardo")
            tipo = st.selectbox("Tipo de Infraestructura:", ["Pozo existente", "Pozo requerido", "PTAR existente", "PTAR requerido", "Tanque existente", "Tanque requerido"])
            c1, c2 = st.columns(2)
            lat = c1.number_input("Latitud (N):", value=0.0, format="%.5f")
            lon = c2.number_input("Longitud (W):", value=0.0, format="%.5f")
            
            submit_manual = st.form_submit_button("➕ Agregar", type="primary", use_container_width=True)
            
            if submit_manual:
                if lat != 0.0 and lon != 0.0:
                    lon_final = -abs(float(lon))
                    st.session_state["marcadores_piezo"].append({
                        "lat": float(lat), "lon": lon_final,
                        "nombre": nom.strip() if nom.strip() else f"Punto Manual {len(st.session_state['marcadores_piezo'])+1}",
                        "tipo": tipo,
                        "atributos": {},
                        "fuente": "manual"
                    })
                    
                    acuifero_detectado = auto_identificar_acuifero_por_coordenadas(lat, lon_final, gdf_m)
                    if acuifero_detectado:
                        st.session_state["clave_piezo"] = acuifero_detectado["clave"]
                        st.session_state["nombre_piezo"] = acuifero_detectado["nombre"]
                        st.session_state["area_total_piezo"] = acuifero_detectado["area"]
                        st.session_state["piezo_sel_edo"] = acuifero_detectado["estado"]
                        st.session_state["piezo_sel_clv"] = f"{acuifero_detectado['clave']} - {acuifero_detectado['nombre']}"
                        st.session_state["puntos_recien_cargados"] = True

                    try:
                        st.rerun(scope="app")
                    except TypeError:
                        st.rerun()
                else:
                    st.warning("Ingresa coordenadas válidas distintas de 0.00000.")

        if st.button("🧹 Limpiar Todos los Puntos", use_container_width=True, type="secondary", key="btn_limpiar_manual_piezo"):
            st.session_state["marcadores_piezo"] = []
            st.session_state["csv_uploader_key_piezo"] = st.session_state.get("csv_uploader_key_piezo", 0) + 1
            try:
                st.rerun(scope="app")
            except TypeError:
                st.rerun()
        
    with tab_c:
        st.markdown("""<div style="background-color: #ffffff; border: 1px dashed #ced4da; border-radius: 4px; padding: 6px 10px; font-size: 10px; color: #495057; margin-bottom: 8px;">Sube tu archivo y mapea las columnas. El mapa se actualizará al dar clic en "Cargar Puntos CSV".</div>""", unsafe_allow_html=True)
        
        up_key = f"csv_up_piezo_{st.session_state['csv_uploader_key_piezo']}"
        archivo_csv = st.file_uploader("Subir CSV", type=['csv'], key=up_key, label_visibility="collapsed")
        
        c_csv1, c_csv2 = st.columns(2)
        if c_csv2.button("🧹 Limpiar", use_container_width=True, type="secondary", key="btn_limpiar_csv_piezo"):
            st.session_state["marcadores_piezo"] = []
            st.session_state["csv_uploader_key_piezo"] = st.session_state.get("csv_uploader_key_piezo", 0) + 1
            try:
                st.rerun(scope="app")
            except TypeError:
                st.rerun()
        
        if archivo_csv is not None:
            try:
                archivo_csv.seek(0)
                try:
                    df_pts = pd.read_csv(archivo_csv, sep=None, engine='python', encoding='utf-8-sig')
                except Exception:
                    archivo_csv.seek(0)
                    df_pts = pd.read_csv(archivo_csv, sep=None, engine='python', encoding='latin1')
                    
                df_pts.columns = df_pts.columns.astype(str).str.strip()
                cols = df_pts.columns.tolist()
                cols_upper = [c.upper() for c in cols]
                
                idx_lat = next((i for i, c in enumerate(cols_upper) if any(k in c for k in ['LATITUD', 'LAT', 'Y', 'NORTE'])), 0)
                idx_lon = next((i for i, c in enumerate(cols_upper) if any(k in c for k in ['LONGITUD', 'LON', 'LONG', 'X', 'OESTE'])), 0)
                idx_infra = next((i for i, c in enumerate(cols_upper) if any(k in c for k in ['INFRAESTRUCTURA', 'INFRA', 'TIPO', 'CATEGORIA'])), None)
                idx_nom = next((i for i, c in enumerate(cols_upper) if any(k in c for k in ['NOMBRE/SITIO', 'NOMBRE', 'SITIO', 'NOM', 'ID', 'ESTACION'])), None)
                idx_color = next((i for i, c in enumerate(cols_upper) if any(k in c for k in ['COLOR', 'HEX'])), None)
                
                with st.form(key="form_csv_piezo"):
                    col_lat = st.selectbox("Columna Latitud:", cols, index=idx_lat)
                    col_lon = st.selectbox("Columna Longitud:", cols, index=idx_lon)
                    
                    opciones_opt = ["(Ninguna)"] + cols
                    col_nom = st.selectbox("Columna Nombre (Opcional):", opciones_opt, index=(idx_nom + 1) if idx_nom is not None else 0)
                    col_infra = st.selectbox("Columna Tipo Infraestructura (Opcional):", opciones_opt, index=(idx_infra + 1) if idx_infra is not None else 0)
                    col_color = st.selectbox("Columna Color HEX (Opcional):", opciones_opt, index=(idx_color + 1) if idx_color is not None else 0)
                    
                    cols_popup = st.multiselect("Columnas para el Popup:", cols)
                    
                    submit_csv = st.form_submit_button("🚀 Cargar Puntos CSV", type="primary", use_container_width=True)
                    
                    if submit_csv:
                        nuevos = []
                        acuifero_detectado = None
                        
                        for _, row in df_pts.iterrows():
                            try:
                                lat_v = pd.to_numeric(str(row[col_lat]).replace(',', '.').strip(), errors='coerce')
                                lon_v = pd.to_numeric(str(row[col_lon]).replace(',', '.').strip(), errors='coerce')
                                if pd.notna(lat_v) and pd.notna(lon_v):
                                    infra_val = str(row[col_infra]).strip() if col_infra != "(Ninguna)" and pd.notna(row[col_infra]) else "Pozo existente"
                                    nom_v = str(row[col_nom]).strip() if col_nom != "(Ninguna)" and pd.notna(row[col_nom]) else infra_val
                                    color_val = str(row[col_color]).strip() if col_color != "(Ninguna)" and pd.notna(row[col_color]) else None
                                    
                                    attrs = {c: str(row[c]) for c in cols_popup}
                                    lon_final = -abs(float(lon_v))
                                    
                                    nuevos.append({
                                        "lat": float(lat_v), "lon": lon_final,
                                        "nombre": nom_v, "tipo": infra_val, "color_hex": color_val,
                                        "atributos": attrs, "fuente": "csv"
                                    })
                                    
                                    if not acuifero_detectado:
                                        acuifero_detectado = auto_identificar_acuifero_por_coordenadas(lat_v, lon_final, gdf_m)
                                        
                            except Exception:
                                pass
                            
                        if nuevos:
                            st.session_state["puntos_recien_cargados"] = True
                            st.session_state["marcadores_piezo"].extend(nuevos)
                            if acuifero_detectado:
                                st.session_state["clave_piezo"] = acuifero_detectado["clave"]
                                st.session_state["nombre_piezo"] = acuifero_detectado["nombre"]
                                st.session_state["area_total_piezo"] = acuifero_detectado["area"]
                                st.session_state["piezo_sel_edo"] = acuifero_detectado["estado"]
                                st.session_state["piezo_sel_clv"] = f"{acuifero_detectado['clave']} - {acuifero_detectado['nombre']}"
                                st.success(f"📍 Acuífero autodetectado: **{acuifero_detectado['clave']} - {acuifero_detectado['nombre']}**")
                            else:
                                st.success(f"✅ {len(nuevos)} puntos cargados correctamente.")
                            try:
                                st.rerun(scope="app")
                            except TypeError:
                                st.rerun()
                        else:
                            st.error("❌ No se encontraron coordenadas válidas.")
            except Exception as e:
                st.error(f"Error procesando CSV: {e}")
        else:
            c_csv1.button("🚀 Cargar", use_container_width=True, type="primary", disabled=True, key="btn_cargar_csv_dis_piezo")

st.sidebar.markdown("---")
st.sidebar.subheader("📍 Puntos de Referencia / Pozos")
st.sidebar.markdown("""<div style="font-size: 11px; color: #666; margin-top: -14px; margin-bottom: 8px;">Ingresa coordenadas manuales o carga masiva vía CSV</div>""", unsafe_allow_html=True)

with st.sidebar:
    renderizar_controles_puntos_piezo()
    if len(st.session_state["marcadores_piezo"]) > 0:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        df_descarga = pd.DataFrame(st.session_state["marcadores_piezo"])
        if not df_descarga.empty:
            if 'atributos' in df_descarga.columns:
                df_attrs = pd.json_normalize(df_descarga['atributos'])
                df_descarga = pd.concat([df_descarga.drop(columns=['atributos']), df_attrs], axis=1)
            df_descarga = df_descarga.rename(columns={"tipo": "Infraestructura", "nombre": "Nombre", "lat": "Latitud", "lon": "Longitud"})
            cols_to_keep = ["Infraestructura", "Nombre", "Latitud", "Longitud"] + [c for c in df_descarga.columns if c not in ["Infraestructura", "Nombre", "Latitud", "Longitud", "fuente", "color_hex"]]
            csv_data = df_descarga[cols_to_keep].to_csv(index=False).encode('utf-8-sig')
            
            st.markdown(generar_enlace_descarga(csv_data, "puntos_piezometria.csv", "text/csv", "⬇️ Descargar Puntos (CSV)"), unsafe_allow_html=True)

    with st.sidebar.expander("🏢 Concesiones REPDA (Extracciones)", expanded=False):
        st.markdown("""<div style="font-size: 11px; color: #475569; margin-bottom: 6px;">Superposición oficial de derechos de extracción de aguas subterráneas (Causa vs Efecto).<br><b style="color:#166534;">Fuente base:</b> coordenadas_repda_sep25.xlsx</div>""", unsafe_allow_html=True)
        subir_repda = st.file_uploader("Cargar concesiones locales (CSV/Excel):", type=["csv", "xlsx", "xls"], key="uploader_repda_side")
        if subir_repda is not None:
            try:
                if subir_repda.name.endswith(".csv"):
                    df_sub_rep = pd.read_csv(subir_repda, encoding="latin1")
                else:
                    df_sub_rep = pd.read_excel(subir_repda)
                st.session_state["repda_custom_df"] = df_sub_rep
                st.success(f"✅ Cargadas {len(df_sub_rep)} captaciones")
            except Exception as e:
                st.error(f"Error procesando archivo: {e}")
        elif "repda_custom_df" in st.session_state:
            st.info(f"📂 Archivo activo: {len(st.session_state['repda_custom_df'])} registros")
            if st.button("🗑️ Restablecer a oficial CONAGUA", use_container_width=True, key="btn_reset_repda"):
                del st.session_state["repda_custom_df"]
                st.rerun()

# =======================================================
# 🔍 3. SELECTOR Y SINCRONIZACIÓN DE SESIÓN GLOBAL
# =======================================================
clave_actual = st.session_state.get("clave_piezo")
nombre_actual = st.session_state.get("nombre_piezo")
area_actual = st.session_state.get("area_total_piezo", 0)

abrir_buscador = True if not clave_actual else False

with st.expander("📍 Búsqueda de Acuífero en Catálogo Oficial", expanded=abrir_buscador):
    df_cat = cargar_catalogo("Acuiferos_2026.csv")
    if not df_cat.empty:
        try:
            c_est, c_clav = st.columns(2)
            estados = sorted(df_cat["ESTADO"].dropna().unique().tolist())
            estado_sel = c_est.selectbox("1. Selecciona el Estado:", estados, key="piezo_sel_edo", index=None, placeholder="Elige un estado...")

            opciones_acuiferos = []
            if estado_sel:
                df_est = df_cat[df_cat["ESTADO"] == estado_sel].copy()
                df_est["ETIQUETA"] = df_est["CLAVE_SIGM"].astype(str) + " - " + df_est["ACUÍFERO"].astype(str)
                opciones_acuiferos = sorted(df_est["ETIQUETA"].unique().tolist())

            seleccion = c_clav.selectbox("2. Escribe o selecciona el Acuífero:", opciones_acuiferos, key="piezo_sel_clv", index=None, placeholder="Elige un acuífero...")

            if seleccion:
                clave_sel = seleccion.split(" - ")[0]
                if clave_sel != st.session_state.get("clave_piezo"):
                    datos_acu = df_est[df_est["CLAVE_SIGM"] == clave_sel].iloc[0]
                    st.session_state["clave_piezo"] = str(datos_acu["CLAVE_SIGM"])
                    st.session_state["nombre_piezo"] = str(datos_acu["ACUÍFERO"])
                    st.session_state["area_total_piezo"] = round(float(datos_acu["AREA_KM2"]), 1)
                    
                    # 🛡️ PROTECCIÓN: Solo limpiar si el cambio vino de selección manual en el buscador
                    if not st.session_state.get("puntos_recien_cargados", False):
                        st.session_state["marcadores_piezo"] = []
                        st.session_state["csv_uploader_key_piezo"] = st.session_state.get("csv_uploader_key_piezo", 0) + 1
                    st.session_state["puntos_recien_cargados"] = False
                    
                    clave_actual = st.session_state["clave_piezo"]
                    nombre_actual = st.session_state["nombre_piezo"]
                    area_actual = st.session_state["area_total_piezo"]
        except Exception as e:
            st.error(f"Error cargando catálogo: {e}")

if not clave_actual or not nombre_actual:
    st.info("👆 **Bienvenido.** Por favor, selecciona un Estado y un Acuífero en el buscador de arriba para iniciar la evaluación geohidrológica.")
    st.stop()

# Banner Ejecutivo del Acuífero
with st.container(border=True):
    col_b1, col_b2, col_b3 = st.columns([1, 2, 1])
    col_b1.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>CLAVE OFICIAL</p><h4 style='color:#691C32; margin:0;'>{clave_actual}</h4>", unsafe_allow_html=True)
    col_b2.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>ACUÍFERO EVALUADO</p><h4 style='color:#691C32; margin:0;'>{nombre_actual}</h4>", unsafe_allow_html=True)
    col_b3.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>SUPERFICIE</p><h4 style='color:#691C32; margin:0;'>{float(area_actual):,.1f} km²</h4>", unsafe_allow_html=True)

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

# =======================================================
# 💾 4. CARGA Y TRANSFORMACIÓN DE BASE DE DATOS
# =======================================================
@st.cache_data(show_spinner="Procesando serie de tiempo piezométrica nacional...")
def cargar_piezometria():
    archivos_candidatos = list(CARPETA_DATOS.glob("Mediciones*.csv"))
    if not archivos_candidatos:
        return None, None, None
        
    archivos_candidatos.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    ruta_csv = archivos_candidatos[0] 
    
    try:
        df = pd.read_csv(ruta_csv, sep=None, engine='python', encoding='utf-8-sig')
    except Exception:
        df = pd.read_csv(ruta_csv, sep=None, engine='python', encoding='latin1')
        
    df.columns = df.columns.str.strip()
    cols_upper = [str(c).upper() for c in df.columns]
    
    col_cve = next((c for c, u in zip(df.columns, cols_upper) if 'CVE_ACUI' in u or 'CLAVE' in u), None)
    col_pozo = next((c for c, u in zip(df.columns, cols_upper) if 'NOM_POZ' in u), next((c for c, u in zip(df.columns, cols_upper) if 'POZO' in u), 'Pozo'))
    col_edo = next((c for c, u in zip(df.columns, cols_upper) if 'NOM_EDO' in u or 'ESTADO' in u), 'Estado')
    col_ac = next((c for c, u in zip(df.columns, cols_upper) if 'NOM_ACU' in u or 'ACUIFERO' in u or 'ACUÍFERO' in u), 'Acuifero')
    col_elev = next((c for c, u in zip(df.columns, cols_upper) if 'ELEV' in u), 'Elev.Terr')
    col_lat = next((c for c, u in zip(df.columns, cols_upper) if 'LAT' in u), 'Latitud')
    col_lon = next((c for c, u in zip(df.columns, cols_upper) if 'LON' in u), 'Longitud')
    
    lista_acuiferos_crudos = df[col_ac].dropna().unique().tolist() if col_ac in df.columns else []
    
    renombre_anios = {}
    for col in df.columns:
        match = re.search(r'(19\d{2}|20\d{2})', str(col))
        if match:
            renombre_anios[col] = match.group(1)
            
    df = df.rename(columns=renombre_anios)
    columnas_anios_limpias = list(renombre_anios.values())
    
    id_vars_seguras = [c for c in [col_cve, col_pozo, col_edo, col_ac, col_elev, col_lat, col_lon] if c is not None and c in df.columns]
    val_vars_seguras = [c for c in columnas_anios_limpias if c in df.columns]
    
    df_largo = df.melt(id_vars=id_vars_seguras, value_vars=val_vars_seguras, var_name='Año', value_name='Profundidad_NE')
    
    rename_dict = {
        col_pozo: 'Pozo', col_edo: 'Estado', col_ac: 'Acuifero',
        col_elev: 'Elev.Terr', col_lat: 'Latitud', col_lon: 'Longitud'
    }
    if col_cve:
        rename_dict[col_cve] = 'Clave'
        
    df_largo = df_largo.rename(columns=rename_dict)
    
    if 'Clave' in df_largo.columns:
        df_largo['Clave'] = df_largo['Clave'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(4)
    
    df_largo['Profundidad_NE'] = pd.to_numeric(df_largo['Profundidad_NE'], errors='coerce')
    df_largo['Año'] = pd.to_numeric(df_largo['Año'], errors='coerce')
    df_largo['Elev.Terr'] = pd.to_numeric(df_largo['Elev.Terr'], errors='coerce')
    df_largo['Carga_Hidraulica'] = df_largo['Elev.Terr'] - df_largo['Profundidad_NE']
    
    return df, df_largo, lista_acuiferos_crudos

df_crudo, df_largo, lista_nombres_crudos = cargar_piezometria()

if df_crudo is None or df_largo is None:
    st.error("⚠️ No se encontró ningún archivo de piezometría en la carpeta de datos.")
    st.stop()

# =======================================================
# 🔍 4.1 FILTRADO ESTRICTO POR CLAVE DEL ACUÍFERO
# =======================================================
clave_limpia_global = str(clave_actual).strip().zfill(4)

if 'Clave' in df_largo.columns:
    df_ac_completo = df_largo[df_largo['Clave'] == clave_limpia_global].copy()
else:
    def normalizar(texto):
        if pd.isna(texto) or not texto: return ""
        t = str(texto).upper().strip()
        t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
        t = re.sub(r'[^A-Z0-9\s]', '', t)
        return re.sub(r'\s+', ' ', t)

    nombre_limpio_global = normalizar(nombre_actual)
    df_largo['Ac_Norm'] = df_largo['Acuifero'].apply(normalizar)
    df_ac_completo = df_largo[df_largo['Ac_Norm'] == nombre_limpio_global].copy()

if df_ac_completo.empty:
    st.error(f"❌ El acuífero **{clave_actual} - {nombre_actual}** no cuenta con registros en la base de monitoreo.")
    st.stop()

df_ac = df_ac_completo.dropna(subset=['Profundidad_NE', 'Año']).copy()
if df_ac.empty:
    st.warning(f"⚠️ El acuífero **{nombre_actual}** existe en la base, pero todas sus mediciones de profundidad están en blanco.")
    st.stop()

pozos_disponibles = sorted(df_ac['Pozo'].astype(str).unique().tolist())

# =======================================================
# ⏱️ 4.2 MOTOR DE SINCRONIZACIÓN TEMPORAL E INTERPOLACIÓN
# =======================================================
def obtener_red_sincronizada(df_ac_completo, anio_objetivo, var_nombre='Carga_Hidraulica', modo="interpolado", ventana_tolerancia=3):
    """
    Sincroniza temporalmente la red de pozos para un año objetivo.
    - modo 'interpolado': Si el pozo tiene dato en el año, lo usa. Si no, interpola o proyecta por tendencia si el dato más reciente está a <= ventana_tolerancia años.
    - modo 'estricto': Solo pozos con medición en el año exacto.
    """
    filas_sincronizadas = []
    pozos_unicos = df_ac_completo['Pozo'].unique()
    
    for pz in pozos_unicos:
        df_pz = df_ac_completo[df_ac_completo['Pozo'] == pz].sort_values(by='Año').dropna(subset=['Año', 'Latitud', 'Longitud'])
        if df_pz.empty:
            continue
        
        lat = float(df_pz.iloc[0]['Latitud'])
        lon = float(df_pz.iloc[0]['Longitud'])
        elev = float(df_pz.iloc[0]['Elev.Terr']) if ('Elev.Terr' in df_pz.columns and pd.notna(df_pz.iloc[0]['Elev.Terr'])) else np.nan
        
        # 1. Comprobar si existe medición exacta en anio_objetivo
        df_exacto = df_pz[df_pz['Año'] == anio_objetivo].dropna(subset=[var_nombre])
        if not df_exacto.empty:
            val = float(df_exacto.iloc[0][var_nombre])
            pne = float(df_exacto.iloc[0]['Profundidad_NE']) if ('Profundidad_NE' in df_exacto.columns and pd.notna(df_exacto.iloc[0]['Profundidad_NE'])) else np.nan
            ch = float(df_exacto.iloc[0]['Carga_Hidraulica']) if ('Carga_Hidraulica' in df_exacto.columns and pd.notna(df_exacto.iloc[0]['Carga_Hidraulica'])) else np.nan
            filas_sincronizadas.append({
                'Pozo': pz,
                'Latitud': lat,
                'Longitud': lon,
                'Elev.Terr': elev,
                'Año': int(anio_objetivo),
                'Año_Medido': int(anio_objetivo),
                'Profundidad_NE': pne,
                'Carga_Hidraulica': ch,
                var_nombre: val,
                'Tipo_Dato': 'Medición Real'
            })
            continue
            
        # Si el modo es estricto, no se interpola
        if modo == "estricto":
            continue
            
        # 2. Si el modo es interpolado, verificar si se puede interpolar o proyectar
        df_validos = df_pz.dropna(subset=['Año', var_nombre])
        if len(df_validos) < 1:
            continue
            
        anios = df_validos['Año'].values
        vals = df_validos[var_nombre].values
        min_a, max_a = int(anios.min()), int(anios.max())
        
        # A. Interpolación entre dos años existentes
        if min_a <= anio_objetivo <= max_a:
            val_interp = float(np.interp(anio_objetivo, anios, vals))
            pne_interp = (elev - val_interp) if (pd.notna(elev) and var_nombre == 'Carga_Hidraulica') else (val_interp if var_nombre == 'Profundidad_NE' else np.nan)
            ch_interp = val_interp if var_nombre == 'Carga_Hidraulica' else ((elev - val_interp) if pd.notna(elev) else np.nan)
            filas_sincronizadas.append({
                'Pozo': pz,
                'Latitud': lat,
                'Longitud': lon,
                'Elev.Terr': elev,
                'Año': int(anio_objetivo),
                'Año_Medido': int(anios[np.abs(anios - anio_objetivo).argmin()]),
                'Profundidad_NE': pne_interp,
                'Carga_Hidraulica': ch_interp,
                var_nombre: val_interp,
                'Tipo_Dato': 'Interpolación Temporal'
            })
        # B. Proyección temporal hacia adelante o hacia atrás si está dentro de la ventana de tolerancia
        elif abs(anio_objetivo - max_a) <= ventana_tolerancia or abs(anio_objetivo - min_a) <= ventana_tolerancia:
            if len(df_validos) >= 2:
                z_coef = np.polyfit(anios, vals, 1)
                val_proy = float(np.polyval(z_coef, anio_objetivo))
            else:
                val_proy = float(vals[-1] if anio_objetivo > max_a else vals[0])
                
            pne_proy = (elev - val_proy) if (pd.notna(elev) and var_nombre == 'Carga_Hidraulica') else (val_proy if var_nombre == 'Profundidad_NE' else np.nan)
            ch_proy = val_proy if var_nombre == 'Carga_Hidraulica' else ((elev - val_proy) if pd.notna(elev) else np.nan)
            filas_sincronizadas.append({
                'Pozo': pz,
                'Latitud': lat,
                'Longitud': lon,
                'Elev.Terr': elev,
                'Año': int(anio_objetivo),
                'Año_Medido': int(max_a if anio_objetivo > max_a else min_a),
                'Profundidad_NE': pne_proy,
                'Carga_Hidraulica': ch_proy,
                var_nombre: val_proy,
                'Tipo_Dato': 'Proyección por Tendencia'
            })
            
    df_sync = pd.DataFrame(filas_sincronizadas)
    if not df_sync.empty:
        df_sync = df_sync.dropna(subset=[var_nombre, 'Latitud', 'Longitud'])
    return df_sync

# =======================================================
# 🗺️ 5. POLÍGONO OFICIAL Y GEOLOGÍA
# =======================================================
@st.cache_resource(show_spinner=False)
def obtener_poligono_oficial(clave):
    try:
        gdf = cargar_datos_maestros()
        if gdf is not None and not gdf.empty:
            cve_str = str(clave).strip().zfill(4)
            col_cve = next((c for c in ['CLV_ACUI', 'CLAVE_SIGM', 'CLAVE'] if c in gdf.columns), gdf.columns[0])
            coincidencias = gdf[gdf[col_cve].astype(str).str.zfill(4) == cve_str]
            if not coincidencias.empty:
                return coincidencias.iloc[0].geometry
    except Exception:
        pass
    return None

poligono_oficial_geom = obtener_poligono_oficial(clave_actual)

@st.cache_data(show_spinner=False)
def preparar_geologia_vectorial(clave_ac, _geom_acuifero):
    if _geom_acuifero is None:
        return None, "Ninguna", {}
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_geologia"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_cache_parquet = carpeta_cache / f"GEO_SHP_{clave_ac}.parquet"

    gdf_sgm = None
    if ruta_cache_parquet.exists() and ruta_cache_parquet.stat().st_size > 2000:
        try:
            gdf_cached = gpd.read_parquet(ruta_cache_parquet)
            if len(gdf_cached.columns) > 3:
                gdf_sgm = gdf_cached
            else:
                ruta_cache_parquet.unlink()
        except Exception:
            pass

    if gdf_sgm is None or gdf_sgm.empty:
        rutas_busqueda = [DIRECTORIO_RAIZ / "data" / "geologia"]
        for r_dir in rutas_busqueda:
            if not r_dir.exists(): continue
            for pq_p in r_dir.glob("*.parquet"):
                if any(k in pq_p.name.lower() for k in ["lito", "geo", "cnal"]) and "estructura" not in pq_p.name.lower():
                    try:
                        gdf_temp = gpd.read_parquet(pq_p)
                        if gdf_temp.crs is None:
                            gdf_temp = gdf_temp.set_crs(epsg=4326)
                        else:
                            gdf_temp = gdf_temp.to_crs(epsg=4326)
                        recorte = gdf_temp.clip(_geom_acuifero)
                        if not recorte.empty:
                            gdf_sgm = recorte
                            break
                    except Exception:
                        pass
            if gdf_sgm is not None:
                break

    if gdf_sgm is not None and not gdf_sgm.empty:
        def reparar_texto_mojibake(val):
            if val is None or pd.isna(val): return ""
            s = str(val).strip()
            try:
                s = s.encode('latin1').decode('utf-8')
            except Exception:
                pass
            return s

        for col in gdf_sgm.select_dtypes(include=['object', 'string']).columns:
            if col != 'geometry':
                gdf_sgm[col] = gdf_sgm[col].apply(reparar_texto_mojibake)

        cols_upper = [c.upper() for c in gdf_sgm.columns]
        if "CLAVE_SGM" in cols_upper: col_sel = gdf_sgm.columns[cols_upper.index("CLAVE_SGM")]
        elif "CLAVE" in cols_upper: col_sel = gdf_sgm.columns[cols_upper.index("CLAVE")]
        elif "LITOLOGIA" in cols_upper: col_sel = gdf_sgm.columns[cols_upper.index("LITOLOGIA")]
        else: col_sel = gdf_sgm.columns[0]

        colores = []
        dic_leyenda = {}
        for _, row in gdf_sgm.iterrows():
            c_val = str(row.get(col_sel, "")).strip()
            l_val = str(row.get("LITOLOGIA", "")).strip() if "LITOLOGIA" in gdf_sgm.columns else ""
            r_val = str(row.get("ROCA", "")).strip() if "ROCA" in gdf_sgm.columns else ""
            hex_c = resolver_color_oficial(c_val, l_val, r_val)
            colores.append(hex_c)
            dic_leyenda[c_val] = hex_c
            
        gdf_sgm["COLOR_HEX"] = colores
        gdf_sgm["geometry"] = gdf_sgm.geometry.simplify(tolerance=0.0001, preserve_topology=True)

        try:
            gdf_sgm.to_parquet(ruta_cache_parquet)
        except Exception:
            pass
        return gdf_sgm, col_sel, dic_leyenda
        
    return None, "Ninguna", {}

# =======================================================
# ⚙️ 6. MOTOR GEOSTADÍSTICO MATEMÁTICO (DESACOPLADO)
# =======================================================
def resolver_malla_kriging(df_puntos, variable, modelo_param, bounds_limite=None, resolucion=150):
    try:
        from pykrige.ok import OrdinaryKriging
        PYKRIGE_INSTALADO = True
    except ImportError:
        PYKRIGE_INSTALADO = False
    if not PYKRIGE_INSTALADO:
        return None, "Falta instalar 'pykrige' (pip install pykrige)", None, None, None, None, None, None, None, None, None
        
    x = np.asarray(df_puntos['Longitud'].values, dtype=np.float64)
    y = np.asarray(df_puntos['Latitud'].values, dtype=np.float64)
    z = np.asarray(df_puntos[variable].values, dtype=np.float64)
    
    if bounds_limite is not None:
        min_x, min_y, max_x, max_y = bounds_limite
        margen_x = (max_x - min_x) * 0.03
        margen_y = (max_y - min_y) * 0.03
        min_x, max_x = min_x - margen_x, max_x + margen_x
        min_y, max_y = min_y - margen_y, max_y + margen_y
    else:
        margen_x = (x.max() - x.min()) * 0.15
        margen_y = (y.max() - y.min()) * 0.15
        min_x, max_x = x.min() - margen_x, x.max() + margen_x
        min_y, max_y = y.min() - margen_y, y.max() + margen_y
    
    grid_x = np.linspace(min_x, max_x, resolucion, dtype=np.float64)
    grid_y = np.linspace(min_y, max_y, resolucion, dtype=np.float64)
    X, Y = np.meshgrid(grid_x, grid_y)
    
    props_kriging = {}
    try:
        v_model = 'linear'
        v_kwargs = {}
        var_z = float(np.var(z)) if np.var(z) > 0 else 1.0
        rango_geom = max(0.01, float(np.hypot(x.max()-x.min(), y.max()-y.min())))

        if 'Lineal' in modelo_param: 
            v_model = 'linear'
        elif 'Esférico' in modelo_param: 
            v_model = 'spherical'
        elif 'Exponencial' in modelo_param: 
            v_model = 'exponential'
        elif 'Gaussiano' in modelo_param: 
            v_model = 'gaussian'
        elif 'Square root' in modelo_param or 'Raíz Cuadrada' in modelo_param: 
            v_model = 'power'
            v_kwargs['variogram_parameters'] = {'scale': var_z, 'exponent': 0.5, 'nugget': 0.0}
        elif 'Stable' in modelo_param: 
            v_model = 'power'
            v_kwargs['variogram_parameters'] = {'scale': var_z, 'exponent': 1.5, 'nugget': 0.0}
        elif 'Logarítmico' in modelo_param:
            v_model = 'custom'
            v_kwargs['variogram_function'] = lambda p, d: p[0] * np.log1p(d) + p[1]
            v_kwargs['variogram_parameters'] = [var_z, 0.0]
        elif 'Cúbico' in modelo_param:
            v_model = 'custom'
            p0 = var_z / (rango_geom**3)
            v_kwargs['variogram_function'] = lambda p, d: p[0] * (d**3) + p[1]
            v_kwargs['variogram_parameters'] = [p0, 0.0]

        ok = OrdinaryKriging(x, y, z, variogram_model=v_model, verbose=False, enable_plotting=False, **v_kwargs)
        Z, ss = ok.execute('grid', grid_x, grid_y)
        
        exp_lags = ok.lags
        exp_semi = ok.semivariance
        smooth_lags = np.linspace(0, np.max(exp_lags) * 1.1, 100)
        if v_model == 'custom': 
            theo_semi_smooth = v_kwargs['variogram_function'](ok.variogram_model_parameters, smooth_lags)
            theo_semi = v_kwargs['variogram_function'](ok.variogram_model_parameters, exp_lags)
        else: 
            theo_semi_smooth = ok.variogram_function(ok.variogram_model_parameters, smooth_lags)
            theo_semi = ok.variogram_function(ok.variogram_model_parameters, exp_lags)
            
        ss_res = np.sum((exp_semi - theo_semi)**2)
        ss_tot = np.sum((exp_semi - np.mean(exp_semi))**2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        fit_range = "N/A"
        if v_model not in ['linear', 'power', 'custom'] and hasattr(ok, 'variogram_model_parameters'):
            try:
                fit_range = ok.variogram_model_parameters[1]
            except Exception:
                fit_range = "N/A"
        
        props_kriging = {
            "Determination (R²)": f"{r_squared:.4f}",
            "Fitting Range": f"{fit_range:.2f}" if isinstance(fit_range, (int, float)) else "N/A",
            "Samples": str(len(x)),
            "Lag Distance": f"{np.mean(np.diff(exp_lags)):.4f}",
            "Max Distance": f"{np.max(exp_lags):.4f}"
        }
    except Exception as e:
        return None, f"Error ajustando variograma {modelo_param}: {e}.", None, None, None, None, None, None, None, None, None

    bounds = [[min_y, min_x], [max_y, max_x]]
    return X, Y, Z, grid_x, grid_y, bounds, props_kriging, exp_lags, exp_semi, smooth_lags, theo_semi_smooth

@st.cache_data(show_spinner=False)
def evaluar_validacion_cruzada_loocv(df_puntos, var_nombre):
    """
    Realiza Validación Cruzada Leave-One-Out (LOOCV) para los 8 modelos de semivariograma.
    Calcula RMSE (m), MAE (m), ME/Sesgo (m) y R² para cada modelo.
    Retorna un DataFrame con el ranking y un diccionario de detalles por pozo.
    """
    try:
        from pykrige.ok import OrdinaryKriging
    except ImportError:
        return None, None, None
        
    if df_puntos is None or len(df_puntos) < 4:
        return None, None, None
        
    df_valid = df_puntos.dropna(subset=['Longitud', 'Latitud', var_nombre]).drop_duplicates(subset=['Longitud', 'Latitud']).copy()
    if len(df_valid) < 4:
        return None, None, None
        
    x = np.asarray(df_valid['Longitud'].values, dtype=np.float64)
    y = np.asarray(df_valid['Latitud'].values, dtype=np.float64)
    z = np.asarray(df_valid[var_nombre].values, dtype=np.float64)
    pozos = df_valid['Pozo'].values
    n = len(x)
    
    modelos_disponibles = [
        "Esférico (spherical)", 
        "Exponencial (exponential)", 
        "Gaussiano (gaussian)", 
        "Lineal (no nugget)", 
        "Raíz Cuadrada (square root)", 
        "Logarítmico", 
        "Stable (0 < k < 2)", 
        "Cúbico"
    ]
    
    resultados_lista = []
    detalles_dict = {}
    
    for m_label in modelos_disponibles:
        y_obs_list, y_pred_list, pozos_list = [], [], []
        
        for i in range(n):
            train_mask = np.ones(n, dtype=bool)
            train_mask[i] = False
            
            sub_x = x[train_mask]
            sub_y = y[train_mask]
            sub_z = z[train_mask]
            
            var_z = float(np.var(sub_z)) if np.var(sub_z) > 0 else 1.0
            rango_geom = max(0.01, float(np.hypot(sub_x.max() - sub_x.min(), sub_y.max() - sub_y.min())))
            
            v_model = 'linear'
            v_kwargs = {}
            
            if 'Lineal' in m_label:
                v_model = 'linear'
            elif 'Esférico' in m_label:
                v_model = 'spherical'
            elif 'Exponencial' in m_label:
                v_model = 'exponential'
            elif 'Gaussiano' in m_label:
                v_model = 'gaussian'
            elif 'Square root' in m_label or 'Raíz Cuadrada' in m_label:
                v_model = 'power'
                v_kwargs['variogram_parameters'] = {'scale': var_z, 'exponent': 0.5, 'nugget': 0.0}
            elif 'Stable' in m_label:
                v_model = 'power'
                v_kwargs['variogram_parameters'] = {'scale': var_z, 'exponent': 1.5, 'nugget': 0.0}
            elif 'Logarítmico' in m_label:
                v_model = 'custom'
                v_kwargs['variogram_function'] = lambda p, d: p[0] * np.log1p(d) + p[1]
                v_kwargs['variogram_parameters'] = [var_z, 0.0]
            elif 'Cúbico' in m_label:
                v_model = 'custom'
                p0 = var_z / (rango_geom**3)
                v_kwargs['variogram_function'] = lambda p, d: p[0] * (d**3) + p[1]
                v_kwargs['variogram_parameters'] = [p0, 0.0]
                
            try:
                ok = OrdinaryKriging(sub_x, sub_y, sub_z, variogram_model=v_model, verbose=False, enable_plotting=False, **v_kwargs)
                pred, _ = ok.execute('points', [x[i]], [y[i]])
                val_pred = float(pred[0])
                if not np.isnan(val_pred):
                    y_obs_list.append(float(z[i]))
                    y_pred_list.append(val_pred)
                    pozos_list.append(pozos[i])
            except Exception:
                pass
                
        if len(y_pred_list) >= max(3, int(n * 0.7)):
            arr_obs = np.array(y_obs_list)
            arr_pred = np.array(y_pred_list)
            residuos = arr_obs - arr_pred
            
            rmse = float(np.sqrt(np.mean(residuos**2)))
            mae = float(np.mean(np.abs(residuos)))
            me_sesgo = float(np.mean(residuos))
            
            ss_res = np.sum(residuos**2)
            ss_tot = np.sum((arr_obs - np.mean(arr_obs))**2)
            r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
            
            df_det = pd.DataFrame({
                'Pozo': pozos_list,
                'Observado': np.round(arr_obs, 2),
                'Predicho_LOOCV': np.round(arr_pred, 2),
                'Residual_m': np.round(residuos, 2),
                'Abs_Residual_m': np.round(np.abs(residuos), 2)
            }).sort_values(by='Abs_Residual_m', ascending=False)
            
            detalles_dict[m_label] = df_det
            
            resultados_lista.append({
                'Modelo': m_label,
                'RMSE (m)': round(rmse, 3),
                'MAE (m)': round(mae, 3),
                'Sesgo ME (m)': round(me_sesgo, 3),
                'R²': round(r2, 4),
                'Muestras': len(y_pred_list)
            })
            
    if not resultados_lista:
        return None, None, None
        
    df_ranking = pd.DataFrame(resultados_lista).sort_values(by='RMSE (m)', ascending=True).reset_index(drop=True)
    df_ranking.insert(0, 'Rank', [f"{'🥇' if i==0 else ('🥈' if i==1 else ('🥉' if i==2 else f'{i+1}º'))}" for i in range(len(df_ranking))])
    
    modelo_optimo = df_ranking.iloc[0]['Modelo']
    
    return df_ranking, modelo_optimo, detalles_dict

def empaquetar_shapefile_zip(gdf, base_name):
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, f"{base_name}.shp")
        if gdf.crs is None: gdf = gdf.set_crs(epsg=4326)
        else: gdf = gdf.to_crs(epsg=4326)
            
        gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")
        
        prj_path = os.path.join(tmpdir, f"{base_name}.prj")
        if not os.path.exists(prj_path):
            with open(prj_path, "w") as f_prj:
                f_prj.write('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')
                
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(tmpdir):
                zf.write(os.path.join(tmpdir, f), arcname=f)
        zip_buf.seek(0)
        return zip_buf.getvalue()

def generar_geotiff_bytes(Z_masked, bounds):
    import matplotlib.pyplot as plt
    try:
        import rasterio
        from rasterio.transform import from_bounds
        from rasterio.io import MemoryFile
        RASTERIO_INSTALADO = True
    except ImportError:
        RASTERIO_INSTALADO = False
    
    min_y, min_x = bounds[0]
    max_y, max_x = bounds[1]
    height, width = Z_masked.shape
    Z_flipped = np.flipud(Z_masked).astype(np.float32)
    data_write = np.nan_to_num(Z_flipped, nan=-9999.0)

    if RASTERIO_INSTALADO:
        transform = from_bounds(min_x, min_y, max_x, max_y, width, height)
        with MemoryFile() as memfile:
            with memfile.open(
                driver='GTiff', height=height, width=width, count=1,
                dtype='float32', crs='EPSG:4326', transform=transform, nodata=-9999.0
            ) as dst:
                dst.write(data_write, 1)
            return memfile.read()
    else:
        buf = io.BytesIO()
        plt.imsave(buf, Z_flipped, cmap='Blues', format='tiff')
        return buf.getvalue()

# =======================================================
# 🌐 6.5 EXPORTACIÓN GEOGRÁFICA KMZ (GOOGLE EARTH)
# =======================================================
def _hex_a_kml_color(hex_str, alpha="ff"):
    """Convierte un color hexadecimal '#RRGGBB' a formato KML 'aabbggrr'."""
    if not hex_str:
        return f"{alpha}ffffff"
    h = str(hex_str).lstrip('#').strip()
    if len(h) == 6:
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"{alpha}{b}{g}{r}".lower()
    elif len(h) == 8:
        return h.lower()
    return f"{alpha}ffffff"

def _geom_a_kml(geom):
    """Convierte geometrías Shapely o diccionarios GeoJSON a KML válido."""
    if geom is None:
        return ""
    if isinstance(geom, dict):
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        if gtype == "Point":
            return f"<Point><coordinates>{coords[0]},{coords[1]},0</coordinates></Point>"
        elif gtype == "LineString":
            c_str = " ".join([f"{pt[0]},{pt[1]},0" for pt in coords if len(pt) >= 2])
            return f"<LineString><tessellate>1</tessellate><coordinates>{c_str}</coordinates></LineString>"
        elif gtype == "MultiLineString":
            res = ["<MultiGeometry>"]
            for line in coords:
                c_str = " ".join([f"{pt[0]},{pt[1]},0" for pt in line if len(pt) >= 2])
                res.append(f"<LineString><tessellate>1</tessellate><coordinates>{c_str}</coordinates></LineString>")
            res.append("</MultiGeometry>")
            return "".join(res)
        elif gtype == "Polygon":
            if not coords:
                return ""
            ext = " ".join([f"{pt[0]},{pt[1]},0" for pt in coords[0] if len(pt) >= 2])
            res = [f"<Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{ext}</coordinates></LinearRing></outerBoundaryIs>"]
            for ring in coords[1:]:
                inte = " ".join([f"{pt[0]},{pt[1]},0" for pt in ring if len(pt) >= 2])
                res.append(f"<innerBoundaryIs><LinearRing><coordinates>{inte}</coordinates></LinearRing></innerBoundaryIs>")
            res.append("</Polygon>")
            return "".join(res)
        elif gtype == "MultiPolygon":
            res = ["<MultiGeometry>"]
            for poly in coords:
                if not poly:
                    continue
                ext = " ".join([f"{pt[0]},{pt[1]},0" for pt in poly[0] if len(pt) >= 2])
                res.append(f"<Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{ext}</coordinates></LinearRing></outerBoundaryIs>")
                for ring in poly[1:]:
                    inte = " ".join([f"{pt[0]},{pt[1]},0" for pt in ring if len(pt) >= 2])
                    res.append(f"<innerBoundaryIs><LinearRing><coordinates>{inte}</coordinates></LinearRing></innerBoundaryIs>")
                res.append("</Polygon>")
            res.append("</MultiGeometry>")
            return "".join(res)
        return ""
    if hasattr(geom, "is_empty") and geom.is_empty:
        return ""
    gt = getattr(geom, "geom_type", "")
    if gt == 'Point':
        return f"<Point><coordinates>{geom.x},{geom.y},0</coordinates></Point>"
    elif gt == 'LineString':
        coords = " ".join([f"{x},{y},0" for x, y in geom.coords])
        return f"<LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString>"
    elif gt == 'MultiLineString':
        res = ["<MultiGeometry>"]
        for line in geom.geoms:
            coords = " ".join([f"{x},{y},0" for x, y in line.coords])
            res.append(f"<LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString>")
        res.append("</MultiGeometry>")
        return "".join(res)
    elif gt == 'Polygon':
        ext = " ".join([f"{x},{y},0" for x, y in geom.exterior.coords])
        res = [f"<Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{ext}</coordinates></LinearRing></outerBoundaryIs>"]
        for interior in geom.interiors:
            inte = " ".join([f"{x},{y},0" for x, y in interior.coords])
            res.append(f"<innerBoundaryIs><LinearRing><coordinates>{inte}</coordinates></LinearRing></innerBoundaryIs>")
        res.append("</Polygon>")
        return "".join(res)
    elif gt == 'MultiPolygon':
        res = ["<MultiGeometry>"]
        for p in geom.geoms:
            res.append(_geom_a_kml(p))
        res.append("</MultiGeometry>")
        return "".join(res)
    return ""

def _extraer_punto_medio(geom):
    """Extrae las coordenadas [lon, lat] del punto medio de una línea para rotular cotas en KML."""
    if geom is None:
        return None
    try:
        if isinstance(geom, dict):
            gtype = geom.get("type", "")
            coords = geom.get("coordinates", [])
            if gtype == "LineString" and coords:
                return coords[len(coords) // 2]
            elif gtype == "MultiLineString" and coords:
                longest = max(coords, key=lambda l: len(l)) if coords else []
                return longest[len(longest) // 2] if longest else None
        elif hasattr(geom, "geom_type"):
            if geom.geom_type == "LineString" and not geom.is_empty:
                pt = geom.interpolate(0.5, normalized=True)
                return [pt.x, pt.y]
            elif geom.geom_type == "MultiLineString" and not geom.is_empty:
                longest = max(geom.geoms, key=lambda g: g.length) if geom.geoms else None
                if longest:
                    pt = longest.interpolate(0.5, normalized=True)
                    return [pt.x, pt.y]
    except Exception:
        pass
    return None

def _parse_geojson_features(geojson_input):
    if not geojson_input:
        return []
    if isinstance(geojson_input, (bytes, bytearray)):
        geojson_input = geojson_input.decode('utf-8', errors='ignore')
    if isinstance(geojson_input, str):
        try:
            data = json.loads(geojson_input)
        except Exception:
            return []
    elif isinstance(geojson_input, dict):
        data = geojson_input
    elif hasattr(geojson_input, "iterfeatures"):
        try:
            return list(geojson_input.iterfeatures())
        except Exception:
            return []
    elif hasattr(geojson_input, "__geo_interface__"):
        gi = geojson_input.__geo_interface__
        return gi.get("features", [gi]) if gi.get("type") == "FeatureCollection" else [gi]
    else:
        return []
    
    if data.get("type") == "FeatureCollection":
        return data.get("features", [])
    elif data.get("type") == "Feature":
        return [data]
    return []

def _construir_kml_geologia(geojson_geo):
    """Genera las etiquetas KML para la capa de Geología Oficial SGM con colores litológicos oficiales."""
    feat_geo = _parse_geojson_features(geojson_geo)
    if not feat_geo:
        return []
    lines = [f'  <Folder><name>Geología SGM ({len(feat_geo)} unidades litológicas)</name><open>0</open>']
    for idx, feat in enumerate(feat_geo):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        col_hex = props.get("COLOR_HEX", "#B0BEC5")
        kml_color = _hex_a_kml_color(col_hex, alpha="99")  # ~60% opacidad
        kml_borde = _hex_a_kml_color("#444444", alpha="cc")

        clave_sgm = html.escape(str(props.get("CLAVE_SGM", props.get("CLAVE", props.get("LITOLOGIA", f"Geo-{idx+1}")))))
        roca = html.escape(str(props.get("ROCA", props.get("LITOLOGIA", "N/D"))))
        formacion = html.escape(str(props.get("FORMACION", "N/D")))
        era = html.escape(str(props.get("ERA", "N/D")))

        geom_kml = _geom_a_kml(geom)
        if geom_kml:
            lines.append('    <Placemark>')
            lines.append(f'      <name>{clave_sgm} ({roca})</name>')
            lines.append('      <Style>')
            lines.append(f'        <LineStyle><color>{kml_borde}</color><width>1.0</width></LineStyle>')
            lines.append(f'        <PolyStyle><color>{kml_color}</color><fill>1</fill><outline>1</outline></PolyStyle>')
            lines.append('        <LabelStyle><scale>0</scale></LabelStyle>')
            lines.append('      </Style>')
            lines.append('      <description><![CDATA[')
            lines.append('        <div style="font-family:Arial,sans-serif;font-size:11.5px;min-width:200px;">')
            lines.append(f'          <div style="font-weight:700;color:#691C32;font-size:12px;margin-bottom:4px;border-bottom:1px solid #CBD5E1;padding-bottom:2px;">🏛️ Geología SGM: {clave_sgm}</div>')
            lines.append('          <table style="width:100%;border-collapse:collapse;font-size:10.5px;">')
            lines.append(f'            <tr><td style="color:#64748b;">Roca / Litología:</td><td><b>{roca}</b></td></tr>')
            if formacion != "N/D":
                lines.append(f'            <tr><td style="color:#64748b;">Formación:</td><td>{formacion}</td></tr>')
            if era != "N/D":
                lines.append(f'            <tr><td style="color:#64748b;">Era / Periodo:</td><td>{era}</td></tr>')
            lines.append(f'            <tr><td style="color:#64748b;">Color Oficial:</td><td><span style="display:inline-block;width:12px;height:12px;background-color:{col_hex};border:1px solid #999;border-radius:2px;vertical-align:middle;"></span> {col_hex}</td></tr>')
            lines.append('          </table>')
            lines.append('        </div>')
            lines.append('      ]]></description>')
            lines.append(f'      {geom_kml}')
            lines.append('    </Placemark>')
    lines.append('  </Folder>')
    return lines

def _construir_kml_repda(geojson_repda):
    """Genera las etiquetas KML para las Concesiones y Captaciones REPDA del acuífero con colores de uso y sin saturación visual."""
    feat_repda = _parse_geojson_features(geojson_repda)
    if not feat_repda:
        return []
    lines = [f'  <Folder><name>Concesiones REPDA ({len(feat_repda)} captaciones)</name><open>0</open>']
    for idx, feat in enumerate(feat_repda):
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        folio = html.escape(str(props.get("folio", props.get("TITULO", props.get("titulo", f"REPDA-{idx+1}")))))
        titular = html.escape(str(props.get("titular", props.get("TITULAR", "Sin Titular"))))
        uso = html.escape(str(props.get("uso", props.get("USO", "No Especificado"))))
        vol_m3 = float(props.get("volumen_m3", props.get("VOL_TOTAL", props.get("volumen", 0.0))))
        vol_hm3 = float(props.get("volumen_hm3", vol_m3 / 1e6))
        prof = float(props.get("profundidad_m", 0.0))
        color_uso = props.get("color") or get_repda_uso_color(uso)
        kml_color = _hex_a_kml_color(color_uso, alpha="ff")

        prof_row = f'            <tr><td style="color:#64748b;">Profundidad de Perforación:</td><td>{prof:.1f} m</td></tr>' if prof > 0 else ''

        lines.append('    <Placemark>')
        lines.append(f'      <name>{folio} ({uso})</name>')
        lines.append('      <Style>')
        lines.append(f'        <IconStyle><scale>0.6</scale><color>{kml_color}</color><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle>')
        lines.append('        <LabelStyle><scale>0</scale></LabelStyle>')
        lines.append('      </Style>')
        lines.append('      <description><![CDATA[')
        lines.append('        <div style="font-family:Arial,sans-serif;font-size:11.5px;min-width:220px;">')
        lines.append(f'          <div style="font-weight:700;color:#166534;font-size:12px;margin-bottom:4px;border-bottom:1px solid #CBD5E1;padding-bottom:2px;">💧 Concesión REPDA: {folio}</div>')
        lines.append('          <table style="width:100%;border-collapse:collapse;font-size:10.5px;">')
        lines.append(f'            <tr><td style="color:#64748b;">Titular:</td><td><b>{titular}</b></td></tr>')
        lines.append(f'            <tr><td style="color:#64748b;">Uso Concesionado:</td><td><b>{uso}</b></td></tr>')
        lines.append(f'            <tr><td style="color:#64748b;">Volumen Anual:</td><td><b>{vol_m3:,.1f} m³/año</b> ({vol_hm3:.4f} hm³)</td></tr>')
        if prof_row:
            lines.append(prof_row)
        lines.append(f'            <tr><td style="color:#64748b;">Coordenadas:</td><td>{coords[1]:.5f}, {coords[0]:.5f}</td></tr>')
        lines.append('          </table>')
        lines.append('        </div>')
        lines.append('      ]]></description>')
        lines.append(f'      <Point><coordinates>{coords[0]},{coords[1]},0</coordinates></Point>')
        lines.append('    </Placemark>')
    lines.append('  </Folder>')
    return lines

def _generar_png_flecha_flujo():
    """Genera una imagen PNG estilizada de flecha hidrológica con antialiasing para vectores KMZ."""
    try:
        from PIL import Image, ImageDraw
        size = 128
        scale = 4
        S = size * scale  # 512
        img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        cx = S / 2.0
        top_y = 35.0 * scale
        bot_y = 100.0 * scale
        stem_w = 8.5 * scale
        head_w = 32.0 * scale
        head_h = 48.0 * scale
        
        p_tip = (cx, top_y)
        p_head_r = (cx + head_w, top_y + head_h)
        p_in_r = (cx + stem_w, top_y + head_h - 8.0 * scale)
        p_stem_br = (cx + stem_w, bot_y)
        p_stem_bl = (cx - stem_w, bot_y)
        p_in_l = (cx - stem_w, top_y + head_h - 8.0 * scale)
        p_head_l = (cx - head_w, top_y + head_h)
        
        poly = [p_tip, p_head_r, p_in_r, p_stem_br, p_stem_bl, p_in_l, p_head_l]
        
        # Borde blanco exterior para alto contraste sobre satélite, ráster o geología
        draw.polygon(poly, fill=(2, 132, 199, 255), outline=(255, 255, 255, 255), width=int(5.5 * scale))
        draw.polygon(poly, fill=(2, 132, 199, 255))
        
        img_res = img.resize((size, size), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img_res.save(buf, format='PNG')
        return buf.getvalue()
    except Exception:
        return None

def generar_kmz_dinamica_flujo(
    clave_actual, nombre_acuifero, anio_sel, var_real,
    bounds, img_kriging_png, geojson_iso, geojson_flujo,
    df_pozos, delim_geom=None, props_kriging=None, marcadores_adicionales=None,
    geojson_geo=None, geojson_repda=None
):
    nombre_acuifero_safe = html.escape(str(nombre_acuifero))
    var_label = "Elevación Piezométrica" if "elev" in str(var_real).lower() or "carga" in str(var_real).lower() else "Profundidad al Nivel Estático"
    unidad = "msnm" if "elev" in str(var_real).lower() or "carga" in str(var_real).lower() else "m"

    min_y, min_x = float(bounds[0][0]), float(bounds[0][1])
    max_y, max_x = float(bounds[1][0]), float(bounds[1][1])

    kml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        f'  <name>Piezometría y Dinámica de Flujo ({anio_sel}) - {clave_actual} {nombre_acuifero_safe}</name>',
        '  <open>1</open>',
        '  <description><![CDATA[',
        '    <div style="font-family:Arial,sans-serif;font-size:12px;color:#1e293b;max-width:320px;">',
        f'      <h3 style="color:#691C32;margin:0 0 6px 0;border-bottom:2px solid #691C32;padding-bottom:4px;">Acuífero {clave_actual} - {nombre_acuifero_safe}</h3>',
        f'      <p style="margin:4px 0;"><b>Variable Modelada:</b> {var_label} ({unidad})</p>',
        f'      <p style="margin:4px 0;"><b>Año de Análisis:</b> {anio_sel}</p>',
        f'      <p style="margin:4px 0;"><b>Pozos Activos:</b> {len(df_pozos) if df_pozos is not None else 0}</p>',
        '      <p style="font-size:10.5px;color:#64748b;margin-top:6px;">Generado por la Plataforma Oficial de Geohidrología y Balances de Aguas Subterráneas.</p>',
        '    </div>',
        '  ]]></description>',
        '  <Style id="style-limite">',
        '    <LineStyle><color>ff321c69</color><width>2.5</width></LineStyle>',
        '    <PolyStyle><color>15321c69</color><fill>1</fill><outline>1</outline></PolyStyle>',
        '  </Style>',
        '  <Style id="style-iso">',
        '    <LineStyle><color>ffe0d000</color><width>2.2</width></LineStyle>',
        '    <IconStyle><scale>0</scale></IconStyle>',
        '    <LabelStyle><scale>0.85</scale><color>ffffffff</color></LabelStyle>',
        '  </Style>',
        '  <Style id="style-flujo-line">',
        '    <LineStyle><color>ffd07000</color><width>2.6</width></LineStyle>',
        '    <LabelStyle><scale>0</scale></LabelStyle>',
        '  </Style>',
        '  <Style id="style-pozo-extra-manual">',
        '    <IconStyle><scale>0.85</scale><color>ff0054d3</color><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle>',
        '    <LabelStyle><scale>0.8</scale><color>ffffffff</color></LabelStyle>',
        '  </Style>',
        '  <Style id="style-pozo-extra-csv">',
        '    <IconStyle><scale>0.85</scale><color>ffb98029</color><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle>',
        '    <LabelStyle><scale>0.8</scale><color>ffffffff</color></LabelStyle>',
        '  </Style>'
    ]

    if delim_geom is not None:
        geom_kml = _geom_a_kml(delim_geom)
        if geom_kml:
            kml.append('  <Folder><name>1. Límite del Acuífero</name>')
            kml.append('    <Placemark>')
            kml.append(f'      <name>Polígono Oficial ({clave_actual})</name>')
            kml.append('      <styleUrl>#style-limite</styleUrl>')
            kml.append(f'      {geom_kml}')
            kml.append('    </Placemark>')
            kml.append('  </Folder>')

    if img_kriging_png:
        r2_txt = f"{props_kriging.get('Determination (R²)', 'N/D')}" if props_kriging else "N/D"
        rango_txt = f"{props_kriging.get('Fitting Range', 'N/D')}" if props_kriging else "N/D"
        kml.append('  <Folder><name>2. Superficie Piezométrica (Ráster Kriging)</name>')
        kml.append('    <GroundOverlay>')
        kml.append(f'      <name>Malla Kriging {var_label} ({anio_sel})</name>')
        kml.append('      <description><![CDATA[')
        kml.append(f'        <b>Modelo Geostadístico:</b> Kriging Ordinario<br><b>R²:</b> {r2_txt}<br><b>Rango de Ajuste:</b> {rango_txt}')
        kml.append('      ]]></description>')
        kml.append('      <Icon><href>kriging_overlay.png</href></Icon>')
        kml.append('      <LatLonBox>')
        kml.append(f'        <north>{max_y:.6f}</north><south>{min_y:.6f}</south><east>{max_x:.6f}</east><west>{min_x:.6f}</west><rotation>0</rotation>')
        kml.append('      </LatLonBox>')
        kml.append('    </GroundOverlay>')
        kml.append('  </Folder>')

    feat_iso = _parse_geojson_features(geojson_iso)
    if feat_iso:
        kml.append(f'  <Folder><name>3. Isopiezas Piezométricas ({len(feat_iso)} curvas)</name>')
        for idx, feat in enumerate(feat_iso):
            geom = feat.get("geometry", {})
            props = feat.get("properties", {})
            cota = props.get("COTA_M", "N/D")
            geom_kml = _geom_a_kml(geom)
            mid_pt = _extraer_punto_medio(geom)
            if geom_kml:
                if mid_pt:
                    geom_final = f"<MultiGeometry>{geom_kml}<Point><coordinates>{mid_pt[0]},{mid_pt[1]},0</coordinates></Point></MultiGeometry>"
                else:
                    geom_final = geom_kml

                kml.append('    <Placemark>')
                kml.append(f'      <name>{cota} {unidad}</name>')
                kml.append('      <styleUrl>#style-iso</styleUrl>')
                kml.append('      <description><![CDATA[')
                kml.append(f'        <div style="font-family:Arial,sans-serif;font-size:11px;">')
                kml.append(f'          <b>Isopieza Piezométrica</b><br>')
                kml.append(f'          Cota: <b>{cota} {unidad}</b><br>')
                kml.append(f'          Variable: {var_label}')
                kml.append('        </div>')
                kml.append('      ]]></description>')
                kml.append(f'      {geom_final}')
                kml.append('    </Placemark>')
        kml.append('  </Folder>')

    feat_flujo = _parse_geojson_features(geojson_flujo)
    if feat_flujo:
        kml.append(f'  <Folder><name>4. Vectores de Flujo Subterráneo ({len(feat_flujo)} vectores)</name>')
        
        # Graduación suave de escala por gradiente hidráulico
        todos_grad = [float(f.get("properties", {}).get("GRAD_M_KM", 0.0)) for f in feat_flujo if f.get("properties")]
        max_grad = max(todos_grad) if todos_grad else 1.0

        for idx, feat in enumerate(feat_flujo):
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2:
                continue
            lo, la = float(coords[0]), float(coords[1])
            grad_m_km = float(props.get("GRAD_M_KM", 0.0))
            az = float(props.get("AZIMUT_DEG", 0.0))
            trans = props.get("TRANSMISIVIDAD_M2_DIA", None)
            caudal = props.get("CAUDAL_UNIT_M2_DIA", None)

            # Escala suave proporcional al gradiente hidráulico (entre 0.72 y 1.15)
            if max_grad > 0:
                scale_v = round(0.72 + 0.38 * min(1.0, math.sqrt(max(0.0, grad_m_km) / max(max_grad, 1e-4))), 2)
            else:
                scale_v = 0.85

            desc_flujo = f"""
            <div style="font-family:Arial,sans-serif;font-size:11px;min-width:215px;">
              <div style="font-weight:700;color:#0284c7;font-size:12px;margin-bottom:4px;border-bottom:1px solid #CBD5E1;padding-bottom:2px;">🧭 Vector Hidrodinámico #{idx+1}</div>
              <table style="width:100%;border-collapse:collapse;margin-top:4px;font-size:10.5px;">
                <tr><td style="color:#64748b;">Dirección (Azimut):</td><td><b>{az:.1f}°</b></td></tr>
                <tr><td style="color:#64748b;">Gradiente (i):</td><td><b>{grad_m_km:.2f} m/km</b></td></tr>
                {"<tr><td style='color:#64748b;'>Transmisividad (T):</td><td><b>" + f"{trans:.2f} m²/d</b></td></tr>" if trans is not None else ""}
                {"<tr><td style='color:#64748b;'>Caudal Unitario (q):</td><td><b>" + f"{caudal:.3f} m²/d</b></td></tr>" if caudal is not None else ""}
                <tr><td style="color:#64748b;">Coordenadas:</td><td>{la:.5f}, {lo:.5f}</td></tr>
              </table>
            </div>
            """
            kml.append('    <Placemark>')
            kml.append(f'      <name>Flujo #{idx+1} ({az:.0f}° | {grad_m_km:.1f} m/km)</name>')
            kml.append('      <Style>')
            kml.append('        <IconStyle>')
            kml.append(f'          <scale>{scale_v}</scale>')
            kml.append(f'          <heading>{az:.1f}</heading>')
            kml.append('          <Icon><href>arrow_flow.png</href></Icon>')
            kml.append('          <hotSpot x="0.5" y="0.5" xunits="fraction" yunits="fraction"/>')
            kml.append('        </IconStyle>')
            kml.append('        <LabelStyle><scale>0</scale></LabelStyle>')
            kml.append('      </Style>')
            kml.append(f'      <description><![CDATA[{desc_flujo}]]></description>')
            kml.append(f'      <Point><coordinates>{lo:.6f},{la:.6f},0</coordinates></Point>')
            kml.append('    </Placemark>')
        kml.append('  </Folder>')

    if df_pozos is not None and not df_pozos.empty:
        kml.append(f'  <Folder><name>5. Red de Monitoreo Piezométrico ({len(df_pozos)} pozos)</name>')
        for _, r in df_pozos.iterrows():
            pz_nom = html.escape(str(r.get("Pozo", "Sin Nombre")))
            lat = float(r.get("Latitud", 0.0))
            lon = float(r.get("Longitud", 0.0))
            val = float(r.get(var_real, 0.0))
            t_dato = str(r.get("Tipo_Dato", "Medición Real"))
            anio_m = int(r.get("Año_Medido", r.get("Año", anio_sel)))
            col_p = r.get("Color")
            if not col_p or pd.isna(col_p):
                col_p = "#285c4d"
            tend_p = str(r.get("Tendencia", "Monitoreo Oficial"))
            kml_col = _hex_a_kml_color(col_p, alpha="ff")

            desc_pz = f"""
            <div style="font-family:Arial,sans-serif;font-size:11px;min-width:215px;">
              <h4 style="color:#691C32;margin:0 0 4px 0;border-bottom:1px solid #CBD5E1;padding-bottom:2px;">📍 Pozo: {pz_nom}</h4>
              <table style="width:100%;border-collapse:collapse;font-size:10.5px;">
                <tr><td style="color:#64748b;">Nivel ({unidad}):</td><td><b>{val:.2f} {unidad}</b></td></tr>
                <tr><td style="color:#64748b;">Tendencia Piezométrica:</td><td><b>{tend_p}</b></td></tr>
                <tr><td style="color:#64748b;">Año Sincronizado:</td><td>{anio_sel} (Medido: {anio_m})</td></tr>
                <tr><td style="color:#64748b;">Tipo de Registro:</td><td>{t_dato}</td></tr>
                <tr><td style="color:#64748b;">Coordenadas:</td><td>{lat:.5f}, {lon:.5f}</td></tr>
              </table>
            </div>
            """
            kml.append('    <Placemark>')
            kml.append(f'      <name>{pz_nom} ({val:.1f} {unidad})</name>')
            kml.append('      <Style>')
            kml.append(f'        <IconStyle><scale>0.85</scale><color>{kml_col}</color><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle>')
            kml.append('        <LabelStyle><scale>0.75</scale><color>ffffffff</color></LabelStyle>')
            kml.append('      </Style>')
            kml.append(f'      <description><![CDATA[{desc_pz}]]></description>')
            kml.append(f'      <Point><coordinates>{lon},{lat},0</coordinates></Point>')
            kml.append('    </Placemark>')
        kml.append('  </Folder>')

    if marcadores_adicionales:
        kml.append(f'  <Folder><name>6. Puntos Adicionales ({len(marcadores_adicionales)} puntos)</name>')
        for idx, pt in enumerate(marcadores_adicionales):
            nom_pt = html.escape(str(pt.get("nombre", f"Punto {idx+1}")))
            lat_pt = float(pt.get("lat", 0.0))
            lon_pt = float(pt.get("lon", 0.0))
            fuente_pt = pt.get("fuente", "manual")
            tipo_pt = pt.get("tipo", "Marcador")
            style_pt = "#style-pozo-extra-csv" if fuente_pt == "csv" else "#style-pozo-extra-manual"
            kml.append('    <Placemark>')
            kml.append(f'      <name>{nom_pt}</name>')
            kml.append(f'      <styleUrl>{style_pt}</styleUrl>')
            kml.append('      <description><![CDATA[')
            kml.append(f'        <b>{nom_pt}</b><br>Fuente: {fuente_pt}<br>Tipo: {tipo_pt}<br>Coord: {lat_pt:.5f}, {lon_pt:.5f}')
            kml.append('      ]]></description>')
            kml.append(f'      <Point><coordinates>{lon_pt},{lat_pt},0</coordinates></Point>')
            kml.append('    </Placemark>')
        kml.append('  </Folder>')

    # 7. Geología SGM (Litología)
    if geojson_geo:
        kml.extend(_construir_kml_geologia(geojson_geo))

    # 8. Concesiones REPDA del Acuífero
    if geojson_repda:
        kml.extend(_construir_kml_repda(geojson_repda))

    kml.append('</Document>')
    kml.append('</kml>')
    kml_str = chr(10).join(kml)

    buf_kmz = io.BytesIO()
    with zipfile.ZipFile(buf_kmz, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('doc.kml', kml_str.encode('utf-8'))
        if img_kriging_png:
            zf.writestr('kriging_overlay.png', img_kriging_png)
        img_arrow_png = _generar_png_flecha_flujo()
        if img_arrow_png:
            zf.writestr('arrow_flow.png', img_arrow_png)
    buf_kmz.seek(0)
    return buf_kmz.getvalue()

def generar_kmz_evolucion(
    clave_actual, nombre_acuifero, anio_t1, anio_t2,
    bounds, img_evo_png, geojson_iso_bytes,
    df_pz_evo, delim_geom=None, resumen_repda=None, geojson_repda_str=None,
    geojson_geo=None
):
    nombre_acuifero_safe = html.escape(str(nombre_acuifero))
    min_y, min_x = float(bounds[0][0]), float(bounds[0][1])
    max_y, max_x = float(bounds[1][0]), float(bounds[1][1])

    kml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        f'  <name>Evolución Piezométrica Δh ({anio_t1} - {anio_t2}) - {clave_actual} {nombre_acuifero_safe}</name>',
        '  <open>1</open>',
        '  <description><![CDATA[',
        '    <div style="font-family:Arial,sans-serif;font-size:12px;color:#1e293b;max-width:320px;">',
        f'      <h3 style="color:#691C32;margin:0 0 6px 0;border-bottom:2px solid #691C32;padding-bottom:4px;">Acuífero {clave_actual} - {nombre_acuifero_safe}</h3>',
        f'      <p style="margin:4px 0;"><b>Periodo Multianual:</b> {anio_t1} → {anio_t2}</p>',
        f'      <p style="margin:4px 0;"><b>Pozos con Diagnóstico:</b> {len(df_pz_evo) if df_pz_evo is not None else 0}</p>',
        '      <p style="font-size:10.5px;color:#64748b;margin-top:6px;">Generado por la Plataforma Oficial de Geohidrología y Balances de Aguas Subterráneas.</p>',
        '    </div>',
        '  ]]></description>',
        '  <Style id="style-limite">',
        '    <LineStyle><color>ff321c69</color><width>2.5</width></LineStyle>',
        '    <PolyStyle><color>15321c69</color><fill>1</fill><outline>1</outline></PolyStyle>',
        '  </Style>',
        '  <Style id="style-iso-abat">',
        '    <LineStyle><color>ff0000b3</color><width>2.2</width></LineStyle>',
        '    <IconStyle><scale>0</scale></IconStyle>',
        '    <LabelStyle><scale>0.85</scale><color>ff8888ff</color></LabelStyle>',
        '  </Style>',
        '  <Style id="style-iso-recup">',
        '    <LineStyle><color>ffcc5500</color><width>2.2</width></LineStyle>',
        '    <IconStyle><scale>0</scale></IconStyle>',
        '    <LabelStyle><scale>0.85</scale><color>ffffff88</color></LabelStyle>',
        '  </Style>',
        '  <Style id="style-iso-equil">',
        '    <LineStyle><color>ff503e2c</color><width>2.2</width></LineStyle>',
        '    <IconStyle><scale>0</scale></IconStyle>',
        '    <LabelStyle><scale>0.85</scale><color>ffffffff</color></LabelStyle>',
        '  </Style>'
    ]

    if delim_geom is not None:
        geom_kml = _geom_a_kml(delim_geom)
        if geom_kml:
            kml.append('  <Folder><name>1. Límite del Acuífero</name>')
            kml.append('    <Placemark>')
            kml.append(f'      <name>Polígono Oficial ({clave_actual})</name>')
            kml.append('      <styleUrl>#style-limite</styleUrl>')
            kml.append(f'      {geom_kml}')
            kml.append('    </Placemark>')
            kml.append('  </Folder>')

    if img_evo_png:
        kml.append('  <Folder><name>2. Superficie de Abatimiento Δh (Ráster Divergente)</name>')
        kml.append('    <GroundOverlay>')
        kml.append(f'      <name>Variación Piezométrica Δh ({anio_t1} - {anio_t2})</name>')
        kml.append('      <description><![CDATA[')
        kml.append(f'        <b>Cálculo Diferencial:</b> Δh = Carga({anio_t2}) - Carga({anio_t1})<br>Ráster con escala cromática divergente (Rojo: Abatimiento | Azul: Recuperación)')
        kml.append('      ]]></description>')
        kml.append('      <Icon><href>evolucion_overlay.png</href></Icon>')
        kml.append('      <LatLonBox>')
        kml.append(f'        <north>{max_y:.6f}</north><south>{min_y:.6f}</south><east>{max_x:.6f}</east><west>{min_x:.6f}</west><rotation>0</rotation>')
        kml.append('      </LatLonBox>')
        kml.append('    </GroundOverlay>')
        kml.append('  </Folder>')

    feat_iso = _parse_geojson_features(geojson_iso_bytes)
    if feat_iso:
        kml.append(f'  <Folder><name>3. Isolíneas de Variación Δh ({len(feat_iso)} isolíneas)</name>')
        for idx, feat in enumerate(feat_iso):
            geom = feat.get("geometry", {})
            props = feat.get("properties", {})
            dh_val = float(props.get("DELTA_H_M", 0.0))
            tipo_iso = props.get("TIPO", "Abatimiento" if dh_val < 0 else "Recuperación")

            if dh_val < -1e-4:
                style_iso = "#style-iso-abat"
            elif dh_val > 1e-4:
                style_iso = "#style-iso-recup"
            else:
                style_iso = "#style-iso-equil"

            geom_kml = _geom_a_kml(geom)
            mid_pt = _extraer_punto_medio(geom)
            if geom_kml:
                if mid_pt:
                    geom_final = f"<MultiGeometry>{geom_kml}<Point><coordinates>{mid_pt[0]},{mid_pt[1]},0</coordinates></Point></MultiGeometry>"
                else:
                    geom_final = geom_kml

                kml.append('    <Placemark>')
                kml.append(f'      <name>Δh = {dh_val:+.1f} m</name>')
                kml.append(f'      <styleUrl>{style_iso}</styleUrl>')
                kml.append('      <description><![CDATA[')
                kml.append(f'        <b>Isolínea Diferencial Δh:</b> {dh_val:+.2f} m<br><b>Comportamiento:</b> {tipo_iso}')
                kml.append('      ]]></description>')
                kml.append(f'      {geom_final}')
                kml.append('    </Placemark>')
        kml.append('  </Folder>')

    df_pz_df = df_pz_evo if isinstance(df_pz_evo, pd.DataFrame) else pd.DataFrame(df_pz_evo if df_pz_evo else [])
    if df_pz_df is not None and not df_pz_df.empty:
        kml.append(f'  <Folder><name>4. Diagnóstico de Pozos ({len(df_pz_df)} pozos)</name>')
        for _, r in df_pz_df.iterrows():
            pz_nom = html.escape(str(r.get("Pozo", "Sin Nombre")))
            lat = float(r.get("Latitud", 0.0))
            lon = float(r.get("Longitud", 0.0))
            dh = float(r.get("Delta_h_m", 0.0))
            tasa = float(r.get("Tasa_m_anio", 0.0))
            cond = str(r.get("Condicion", "N/D"))

            col_p = r.get("Color")
            if not col_p or pd.isna(col_p):
                if "crítico" in cond.lower() or "severo" in cond.lower(): col_p = "#9f2241"
                elif "moderado" in cond.lower(): col_p = "#ea580c"
                elif "leve" in cond.lower(): col_p = "#f59e0b"
                elif "recuper" in cond.lower(): col_p = "#16a34a"
                else: col_p = "#64748b"
            kml_col = _hex_a_kml_color(col_p, alpha="ff")

            c1 = r.get(f"Carga_{anio_t1}_msnm", "N/D")
            c2 = r.get(f"Carga_{anio_t2}_msnm", "N/D")

            desc_pz = f"""
            <div style="font-family:Arial,sans-serif;font-size:11px;min-width:220px;">
              <h4 style="color:#691C32;margin:0 0 4px 0;border-bottom:1px solid #CBD5E1;padding-bottom:2px;">📍 Pozo: {pz_nom}</h4>
              <table style="width:100%;border-collapse:collapse;font-size:10.5px;">
                <tr><td style="color:#64748b;">Condición:</td><td><b>{cond}</b></td></tr>
                <tr><td style="color:#64748b;">Variación Neta (Δh):</td><td><b>{dh:+.2f} m</b></td></tr>
                <tr><td style="color:#64748b;">Tasa Promedio Anual:</td><td><b>{tasa:+.2f} m/año</b></td></tr>
                <tr><td style="color:#64748b;">Nivel en {anio_t1}:</td><td>{c1} msnm</td></tr>
                <tr><td style="color:#64748b;">Nivel en {anio_t2}:</td><td>{c2} msnm</td></tr>
                <tr><td style="color:#64748b;">Coordenadas:</td><td>{lat:.5f}, {lon:.5f}</td></tr>
              </table>
            </div>
            """
            kml.append('    <Placemark>')
            kml.append(f'      <name>{pz_nom} ({dh:+.1f} m | {tasa:+.2f} m/a)</name>')
            kml.append('      <Style>')
            kml.append(f'        <IconStyle><scale>0.85</scale><color>{kml_col}</color><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle>')
            kml.append('        <LabelStyle><scale>0.75</scale><color>ffffffff</color></LabelStyle>')
            kml.append('      </Style>')
            kml.append(f'      <description><![CDATA[{desc_pz}]]></description>')
            kml.append(f'      <Point><coordinates>{lon},{lat},0</coordinates></Point>')
            kml.append('    </Placemark>')
        kml.append('  </Folder>')

    # 5. Concesiones REPDA del Acuífero
    if geojson_repda_str:
        kml.extend(_construir_kml_repda(geojson_repda_str))

    # 6. Geología SGM (Litología)
    if geojson_geo:
        kml.extend(_construir_kml_geologia(geojson_geo))

    kml.append('</Document>')
    kml.append('</kml>')
    kml_str = chr(10).join(kml)

    buf_kmz = io.BytesIO()
    with zipfile.ZipFile(buf_kmz, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('doc.kml', kml_str.encode('utf-8'))
        if img_evo_png:
            zf.writestr('evolucion_overlay.png', img_evo_png)
    buf_kmz.seek(0)
    return buf_kmz.getvalue()

def generar_kmz_cobertura(
    clave_actual, nombre_acuifero, radio_km,
    geojson_ciega, geojson_cubierta,
    df_pozos, df_propuestas, delim_geom=None, res_metricas=None,
    geojson_geo=None, geojson_repda=None
):
    nombre_acuifero_safe = html.escape(str(nombre_acuifero))
    metricas = res_metricas or {}
    area_tot = metricas.get('area_total_km2', 0.0)
    area_cie = metricas.get('area_ciega_km2', 0.0)
    pct_cie = metricas.get('pct_ciega', 0.0)
    pct_cub = metricas.get('pct_cubierta', 0.0)
    km2_pz = metricas.get('km2_por_pozo', 0.0)

    kml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        f'  <name>Cobertura y Zonas Ciegas (R={radio_km:.1f} km) - {clave_actual} {nombre_acuifero_safe}</name>',
        '  <open>1</open>',
        '  <description><![CDATA[',
        '    <div style="font-family:Arial,sans-serif;font-size:12px;color:#1e293b;max-width:320px;">',
        f'      <h3 style="color:#691C32;margin:0 0 6px 0;border-bottom:2px solid #691C32;padding-bottom:4px;">Acuífero {clave_actual} - {nombre_acuifero_safe}</h3>',
        f'      <p style="margin:4px 0;"><b>Superficie Total:</b> {area_tot:,.1f} km²</p>',
        f'      <p style="margin:4px 0;"><b>Radio de Representatividad:</b> {radio_km:.1f} km</p>',
        f'      <p style="margin:4px 0;"><b>Cobertura de Monitoreo:</b> <span style="color:#16a34a;font-weight:700;">{pct_cub:.1f}%</span></p>',
        f'      <p style="margin:4px 0;"><b>Zonas Ciegas (Sin Datos):</b> <span style="color:#dc2626;font-weight:700;">{pct_cie:.1f}% ({area_cie:,.1f} km²)</span></p>',
        f'      <p style="margin:4px 0;"><b>Densidad Media:</b> 1 pozo c/{km2_pz:.1f} km²</p>',
        '      <p style="font-size:10.5px;color:#64748b;margin-top:6px;">Generado por la Plataforma Oficial de Geohidrología y Balances de Aguas Subterráneas.</p>',
        '    </div>',
        '  ]]></description>',
        '  <Style id="style-limite">',
        '    <LineStyle><color>ff321c69</color><width>2.5</width></LineStyle>',
        '    <PolyStyle><color>10321c69</color><fill>1</fill><outline>1</outline></PolyStyle>',
        '  </Style>',
        '  <Style id="style-ciega">',
        '    <LineStyle><color>ff1111cc</color><width>2.0</width></LineStyle>',
        '    <PolyStyle><color>731111cc</color><fill>1</fill><outline>1</outline></PolyStyle>',
        '  </Style>',
        '  <Style id="style-cubierta">',
        '    <LineStyle><color>ff228822</color><width>1.5</width></LineStyle>',
        '    <PolyStyle><color>4d22aa22</color><fill>1</fill><outline>1</outline></PolyStyle>',
        '  </Style>',
        '  <Style id="style-pozo-exist">',
        '    <IconStyle><scale>0.85</scale><color>ffd07000</color><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle>',
        '    <LabelStyle><scale>0.75</scale><color>ffffffff</color></LabelStyle>',
        '  </Style>',
        '  <Style id="style-pozo-prop">',
        '    <IconStyle><scale>1.0</scale><color>ff0099ff</color><Icon><href>http://maps.google.com/mapfiles/kml/shapes/target.png</href></Icon></IconStyle>',
        '    <LabelStyle><scale>0.8</scale><color>ffffffff</color></LabelStyle>',
        '  </Style>'
    ]

    if delim_geom is not None:
        geom_kml = _geom_a_kml(delim_geom)
        if geom_kml:
            kml.append('  <Folder><name>1. Límite del Acuífero</name>')
            kml.append('    <Placemark>')
            kml.append(f'      <name>Polígono Oficial ({area_tot:,.1f} km²)</name>')
            kml.append('      <styleUrl>#style-limite</styleUrl>')
            kml.append(f'      {geom_kml}')
            kml.append('    </Placemark>')
            kml.append('  </Folder>')

    feat_cie = _parse_geojson_features(geojson_ciega)
    if feat_cie:
        kml.append(f'  <Folder><name>2. Zonas Ciegas de Monitoreo (Sin Cobertura: {pct_cie:.1f}%)</name>')
        for idx, feat in enumerate(feat_cie):
            geom = feat.get("geometry", {})
            geom_kml = _geom_a_kml(geom)
            if geom_kml:
                kml.append('    <Placemark>')
                kml.append(f'      <name>Zona Ciega #{idx+1}</name>')
                kml.append('      <styleUrl>#style-ciega</styleUrl>')
                kml.append('      <description><![CDATA[')
                kml.append('        <div style="font-family:Arial,sans-serif;font-size:11px;">')
                kml.append('          <b style="color:#b91c1c;">⚠️ Vacío de Información Geohidrológica</b><br>')
                kml.append('          Esta región carece de pozos de observación activos en el radio especificado.<br>')
                kml.append('          Cualquier interpolación espacial en este sector incurre en alta incertidumbre.')
                kml.append('        </div>')
                kml.append('      ]]></description>')
                kml.append(f'      {geom_kml}')
                kml.append('    </Placemark>')
        kml.append('  </Folder>')

    feat_cub = _parse_geojson_features(geojson_cubierta)
    if feat_cub:
        kml.append(f'  <Folder><name>3. Cobertura Activa de Pozos (Radio R={radio_km:.1f} km: {pct_cub:.1f}%)</name>')
        for idx, feat in enumerate(feat_cub):
            geom = feat.get("geometry", {})
            geom_kml = _geom_a_kml(geom)
            if geom_kml:
                kml.append('    <Placemark>')
                kml.append(f'      <name>Polígono Cobertura #{idx+1}</name>')
                kml.append('      <styleUrl>#style-cubierta</styleUrl>')
                kml.append('      <description><![CDATA[')
                kml.append('        <div style="font-family:Arial,sans-serif;font-size:11px;">')
                kml.append(f'          <b>Superficie Monitoreada</b><br>Radio de Influencia: <b>{radio_km:.1f} km</b>')
                kml.append('        </div>')
                kml.append('      ]]></description>')
                kml.append(f'      {geom_kml}')
                kml.append('    </Placemark>')
        kml.append('  </Folder>')

    df_pz_ex = df_pozos if isinstance(df_pozos, pd.DataFrame) else pd.DataFrame(df_pozos if df_pozos else [])
    if df_pz_ex is not None and not df_pz_ex.empty:
        kml.append(f'  <Folder><name>4. Pozos de Monitoreo Existentes ({len(df_pz_ex)} pozos)</name>')
        for _, r in df_pz_ex.iterrows():
            pz_nom = html.escape(str(r.get("Pozo", "Sin Nombre")))
            lat = float(r.get("Latitud", 0.0))
            lon = float(r.get("Longitud", 0.0))
            kml.append('    <Placemark>')
            kml.append(f'      <name>{pz_nom}</name>')
            kml.append('      <styleUrl>#style-pozo-exist</styleUrl>')
            kml.append('      <description><![CDATA[')
            kml.append(f'        <b>Pozo de Monitoreo:</b> {pz_nom}<br>Radio de Cobertura: {radio_km:.1f} km<br>Coord: {lat:.5f}, {lon:.5f}')
            kml.append('      ]]></description>')
            kml.append(f'      <Point><coordinates>{lon},{lat},0</coordinates></Point>')
            kml.append('    </Placemark>')
        kml.append('  </Folder>')

    df_pr = df_propuestas if isinstance(df_propuestas, pd.DataFrame) else pd.DataFrame(df_propuestas if df_propuestas else [])
    if df_pr is not None and not df_pr.empty:
        kml.append(f'  <Folder><name>5. Propuestas de Nuevos Pozos ({len(df_pr)} sitios prioritarios)</name>')
        for _, r in df_pr.iterrows():
            p_id = html.escape(str(r.get("ID", "Sitio")))
            lat = float(r.get("Latitud", 0.0))
            lon = float(r.get("Longitud", 0.0))
            area_v = float(r.get("Area_Vacio_km2", 0.0))
            dist_p = float(r.get("Dist_Pozo_km", 0.0))
            prio = str(r.get("Prioridad", "Media"))

            desc_prop = f"""
            <div style="font-family:Arial,sans-serif;font-size:11px;min-width:210px;">
              <h4 style="color:#ea580c;margin:0 0 4px 0;border-bottom:1px solid #CBD5E1;padding-bottom:2px;">🎯 Nuevo Sitio Propuesto: {p_id}</h4>
              <table style="width:100%;border-collapse:collapse;font-size:10.5px;">
                <tr><td style="color:#64748b;">Prioridad de Instalación:</td><td><b>{prio}</b></td></tr>
                <tr><td style="color:#64748b;">Área de Vacío a Capturar:</td><td><b>{area_v:,.1f} km²</b></td></tr>
                <tr><td style="color:#64748b;">Distancia a Pozo Cercano:</td><td><b>{dist_p:.1f} km</b></td></tr>
                <tr><td style="color:#64748b;">Coordenadas:</td><td>{lat:.5f}, {lon:.5f}</td></tr>
              </table>
            </div>
            """
            kml.append('    <Placemark>')
            kml.append(f'      <name>Sitio Sugerido {p_id}</name>')
            kml.append('      <styleUrl>#style-pozo-prop</styleUrl>')
            kml.append(f'      <description><![CDATA[{desc_prop}]]></description>')
            kml.append(f'      <Point><coordinates>{lon},{lat},0</coordinates></Point>')
            kml.append('    </Placemark>')
        kml.append('  </Folder>')

    # 6. Geología SGM (Litología)
    if geojson_geo:
        kml.extend(_construir_kml_geologia(geojson_geo))

    # 7. Concesiones REPDA del Acuífero
    if geojson_repda:
        kml.extend(_construir_kml_repda(geojson_repda))

    kml.append('</Document>')
    kml.append('</kml>')
    kml_str = chr(10).join(kml)

    buf_kmz = io.BytesIO()
    with zipfile.ZipFile(buf_kmz, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('doc.kml', kml_str.encode('utf-8'))
    buf_kmz.seek(0)
    return buf_kmz.getvalue()

# =======================================================
# 🎨 7. RENDERIZADO VISUAL REACTIVO (<30 ms)
# =======================================================
def render_imagen_kriging(X, Y, Z_masked, bounds):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    fig = plt.figure(figsize=(10, 10), frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_xlim(bounds[0][1], bounds[1][1])
    ax.set_ylim(bounds[0][0], bounds[1][0])
    
    ax.contourf(X, Y, Z_masked, levels=40, cmap='Blues')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, pad_inches=0)
    plt.close(fig)
    
    vmin = float(np.nanmin(Z_masked)) if not np.isnan(np.nanmin(Z_masked)) else 0.0
    vmax = float(np.nanmax(Z_masked)) if not np.isnan(np.nanmax(Z_masked)) else 100.0
    return buf.getvalue(), vmin, vmax

def render_imagen_isolineas(X, Y, Z_masked, bounds, intervalo_iso, var_nombre):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    fig = plt.figure(figsize=(10, 10), frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_xlim(bounds[0][1], bounds[1][1])
    ax.set_ylim(bounds[0][0], bounds[1][0])
    
    vmin = float(np.nanmin(Z_masked)) if not np.isnan(np.nanmin(Z_masked)) else 0.0
    vmax = float(np.nanmax(Z_masked)) if not np.isnan(np.nanmax(Z_masked)) else 100.0
    if intervalo_iso <= 0: intervalo_iso = 5.0
    
    niveles = np.arange(np.floor(vmin / intervalo_iso) * intervalo_iso, 
                        np.ceil(vmax / intervalo_iso) * intervalo_iso + intervalo_iso, 
                        intervalo_iso)
    if len(niveles) < 2: niveles = np.linspace(vmin, vmax, 5)
        
    contours = ax.contour(X, Y, Z_masked, levels=niveles, colors='white', linestyles='dashed', linewidths=1.6, alpha=0.95)
    ax.clabel(contours, inline=True, fontsize=10.5, fmt='%1.1f', colors='#002B49')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, pad_inches=0)
    plt.close(fig)
    
    features, line_geoms, cotas = [], [], []
    try:
        for level_val, segs in zip(contours.levels, contours.allsegs):
            for seg in segs:
                if len(seg) >= 2:
                    coords = [[round(float(pt[0]), 6), round(float(pt[1]), 6)] for pt in seg]
                    features.append({
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": {"COTA_M": round(float(level_val), 2), "VARIABLE": var_nombre}
                    })
                    if GEOPANDAS_INSTALADO:
                        line_geoms.append(LineString(coords))
                        cotas.append(round(float(level_val), 2))
    except Exception:
        pass

    geojson_bytes = json.dumps({"type": "FeatureCollection", "features": features}, indent=2).encode('utf-8')
    shp_zip_bytes = None
    if GEOPANDAS_INSTALADO and line_geoms:
        df_iso = pd.DataFrame({"COTA_M": cotas, "VARIABLE": [var_nombre]*len(cotas)})
        gdf_iso = gpd.GeoDataFrame(df_iso, geometry=line_geoms, crs="EPSG:4326")
        shp_zip_bytes = empaquetar_shapefile_zip(gdf_iso, f"isopiezas_{clave_actual}")
        
    return buf.getvalue(), geojson_bytes, shp_zip_bytes

def render_imagen_vectores(X, Y, Z, grid_x, grid_y, bounds, variable, densidad_flujo, inside_mask, transmisividad=0.0):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    # Conversión geométrica métrica (WGS84) para gradiente físico real en m/m
    lat_media = float(np.mean(grid_y))
    m_por_deg_lat = 111132.954
    m_por_deg_lon = 111412.84 * np.cos(np.radians(lat_media))
    
    step_x_m = float(abs(grid_x[1] - grid_x[0])) * m_por_deg_lon if len(grid_x) > 1 else 100.0
    step_y_m = float(abs(grid_y[1] - grid_y[0])) * m_por_deg_lat if len(grid_y) > 1 else 100.0
    
    dy, dx = np.gradient(Z, step_y_m, step_x_m)
    # Ley de Darcy: flujo va en sentido contrario al gradiente de carga hidráulica (-gradiente)
    Vx, Vy = (-dx, -dy) if variable == 'Carga_Hidraulica' else (dx, dy)
        
    magnitude = np.sqrt(Vx**2 + Vy**2)
    magnitude = np.where(magnitude == 0, 1e-10, magnitude)
    Vx_norm, Vy_norm = (Vx / magnitude), (Vy / magnitude)
    
    resolucion = len(grid_x)
    paso = max(1, int(resolucion / max(4, densidad_flujo)))
    
    X_sub = X[::paso, ::paso]
    Y_sub = Y[::paso, ::paso]
    Vx_sub = Vx_norm[::paso, ::paso]
    Vy_sub = Vy_norm[::paso, ::paso]
    Mag_sub = magnitude[::paso, ::paso]
    inside_sub = inside_mask[::paso, ::paso]
    
    fig = plt.figure(figsize=(10, 10), frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_xlim(bounds[0][1], bounds[1][1])
    ax.set_ylim(bounds[0][0], bounds[1][0])
    
    validos = inside_sub & (~np.isnan(Mag_sub))
    if np.any(validos):
        ax.quiver(
            X_sub[validos], Y_sub[validos], 
            Vx_sub[validos], Vy_sub[validos], 
            Mag_sub[validos], 
            cmap='Blues_r', alpha=0.85, scale=densidad_flujo * 1.8, width=0.0035, headwidth=3.5, headlength=4.5
        )
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, pad_inches=0)
    plt.close(fig)

    lons = X_sub[validos]
    lats = Y_sub[validos]
    v_x = Vx_sub[validos]
    v_y = Vy_sub[validos]
    mags = Mag_sub[validos]
    azimut = (np.degrees(np.arctan2(v_x, v_y)) + 360) % 360

    features_vec, points_geom, data_records = [], [], []
    for lo, la, vx, vy, mg, az in zip(lons, lats, v_x, v_y, mags, azimut):
        rec = {
            "LONGITUD": round(float(lo), 6), "LATITUD": round(float(la), 6),
            "GRADIENTE": round(float(mg), 6), "GRAD_M_KM": round(float(mg) * 1000.0, 3),
            "AZIMUT_DEG": round(float(az), 1),
            "VX": round(float(vx), 5), "VY": round(float(vy), 5)
        }
        if transmisividad > 0:
            rec["TRANSMISIVIDAD_M2_DIA"] = round(float(transmisividad), 2)
            rec["CAUDAL_UNIT_M2_DIA"] = round(float(transmisividad * float(mg)), 3)
        data_records.append(rec)
        features_vec.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [rec["LONGITUD"], rec["LATITUD"]]},
            "properties": rec
        })
        if GEOPANDAS_INSTALADO:
            points_geom.append(Point(rec["LONGITUD"], rec["LATITUD"]))

    geojson_bytes = json.dumps({"type": "FeatureCollection", "features": features_vec}, indent=2).encode('utf-8')
    shp_zip_bytes = None
    if GEOPANDAS_INSTALADO and points_geom:
        gdf_vec = gpd.GeoDataFrame(pd.DataFrame(data_records), geometry=points_geom, crs="EPSG:4326")
        shp_zip_bytes = empaquetar_shapefile_zip(gdf_vec, f"vectores_flujo_{clave_actual}")
        
    return buf.getvalue(), geojson_bytes, shp_zip_bytes

def render_imagen_evolucion_divergente(X, Y, delta_Z_masked, bounds):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    
    fig = plt.figure(figsize=(10, 10), frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_xlim(bounds[0][1], bounds[1][1])
    ax.set_ylim(bounds[0][0], bounds[1][0])
    
    val_valid = delta_Z_masked[~np.isnan(delta_Z_masked)]
    if len(val_valid) == 0:
        vmin, vmax = -5.0, 5.0
    else:
        vmin = float(np.min(val_valid))
        vmax = float(np.max(val_valid))
        
    if vmin >= 0:
        vmin = -0.05
    if vmax <= 0:
        vmax = 0.05
        
    try:
        norm = TwoSlopeNorm(vcenter=0.0, vmin=vmin, vmax=vmax)
        ax.contourf(X, Y, delta_Z_masked, levels=50, cmap='RdBu', norm=norm, extend='both')
    except Exception:
        ax.contourf(X, Y, delta_Z_masked, levels=50, cmap='RdBu', extend='both')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, pad_inches=0)
    plt.close(fig)
    
    return buf.getvalue(), vmin, vmax

def render_imagen_isolineas_evolucion(X, Y, delta_Z_masked, bounds, intervalo_iso, clave_actual):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    fig = plt.figure(figsize=(10, 10), frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_xlim(bounds[0][1], bounds[1][1])
    ax.set_ylim(bounds[0][0], bounds[1][0])
    
    val_valid = delta_Z_masked[~np.isnan(delta_Z_masked)]
    if len(val_valid) == 0:
        vmin, vmax = -5.0, 5.0
    else:
        vmin = float(np.min(val_valid))
        vmax = float(np.max(val_valid))
        
    if intervalo_iso <= 0:
        intervalo_iso = 2.0
        
    min_cota = np.floor(vmin / intervalo_iso) * intervalo_iso
    max_cota = np.ceil(vmax / intervalo_iso) * intervalo_iso
    niveles = np.arange(min_cota, max_cota + intervalo_iso * 0.5, intervalo_iso)
    if len(niveles) < 2:
        niveles = np.linspace(vmin, vmax, 5)
        
    niveles_neg = [round(float(n), 2) for n in niveles if n < -1e-4]
    niveles_cero = [round(float(n), 2) for n in niveles if abs(n) <= 1e-4]
    niveles_pos = [round(float(n), 2) for n in niveles if n > 1e-4]
    
    contours_all = []
    if niveles_neg:
        c_neg = ax.contour(X, Y, delta_Z_masked, levels=niveles_neg, colors='#990000', linestyles='solid', linewidths=1.8, alpha=0.95)
        ax.clabel(c_neg, inline=True, fontsize=10, fmt='%.1f m', colors='#660000')
        contours_all.append(c_neg)
    if niveles_cero:
        c_cero = ax.contour(X, Y, delta_Z_masked, levels=niveles_cero, colors='#2C3E50', linestyles='solid', linewidths=2.2, alpha=0.95)
        ax.clabel(c_cero, inline=True, fontsize=10.5, fmt='0.0 m (Equilibrio)', colors='#1A252F')
        contours_all.append(c_cero)
    if niveles_pos:
        c_pos = ax.contour(X, Y, delta_Z_masked, levels=niveles_pos, colors='#0055AA', linestyles='dashed', linewidths=1.8, alpha=0.95)
        ax.clabel(c_pos, inline=True, fontsize=10, fmt='+%.1f m', colors='#003366')
        contours_all.append(c_pos)
        
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, pad_inches=0)
    plt.close(fig)
    
    features, line_geoms, cotas = [], [], []
    for cnt in contours_all:
        try:
            for level_val, segs in zip(cnt.levels, cnt.allsegs):
                for seg in segs:
                    if len(seg) >= 2:
                        coords = [[round(float(pt[0]), 6), round(float(pt[1]), 6)] for pt in seg]
                        tipo_cota = "Abatimiento" if level_val < -1e-4 else ("Equilibrio" if abs(level_val) <= 1e-4 else "Recuperación")
                        features.append({
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": coords},
                            "properties": {"DELTA_H_M": round(float(level_val), 2), "TIPO": tipo_cota}
                        })
                        if GEOPANDAS_INSTALADO:
                            line_geoms.append(LineString(coords))
                            cotas.append(round(float(level_val), 2))
        except Exception:
            pass
            
    geojson_bytes = json.dumps({"type": "FeatureCollection", "features": features}, indent=2).encode('utf-8')
    shp_zip_bytes = None
    if GEOPANDAS_INSTALADO and line_geoms:
        df_iso = pd.DataFrame({"DELTA_H_M": cotas, "TIPO": ["Abatimiento" if c < -1e-4 else ("Equilibrio" if abs(c) <= 1e-4 else "Recuperación") for c in cotas]})
        gdf_iso = gpd.GeoDataFrame(df_iso, geometry=line_geoms, crs="EPSG:4326")
        shp_zip_bytes = empaquetar_shapefile_zip(gdf_iso, f"isolineas_delta_h_{clave_actual}")
        
    return buf.getvalue(), geojson_bytes, shp_zip_bytes

# =======================================================
# 📄 GENERADOR DE DICTAMEN GEOHIDROLÓGICO OFICIAL (.DOCX)
# =======================================================
def _formatear_celda_dictamen(celda, texto, fondo_hex=None, negrita=False, tamano_pt=9, alineacion=WD_ALIGN_PARAGRAPH.LEFT, color_hex="1E293B", cursiva=False):
    tcPr = celda._tc.get_or_add_tcPr()
    tcVAlign = tcPr.find(qn('w:vAlign'))
    if tcVAlign is None:
        tcVAlign = OxmlElement('w:vAlign')
        tcPr.append(tcVAlign)
    tcVAlign.set(qn('w:val'), "center")
    
    if fondo_hex:
        shd = tcPr.find(qn('w:shd'))
        if shd is not None:
            tcPr.remove(shd)
        tcShd = OxmlElement('w:shd')
        tcShd.set(qn('w:val'), 'clear')
        tcShd.set(qn('w:color'), 'auto')
        tcShd.set(qn('w:fill'), fondo_hex)
        tcPr.append(tcShd)
        
    celda.text = ""
    p = celda.paragraphs[0]
    p.alignment = alineacion
    p.paragraph_format.space_before = Pt(2.5)
    p.paragraph_format.space_after = Pt(2.5)
    
    run = p.add_run(str(texto))
    run.font.name = 'Calibri'
    run.font.size = Pt(tamano_pt)
    run.font.bold = negrita
    run.font.italic = cursiva
    if color_hex:
        run.font.color.rgb = RGBColor.from_string(color_hex)

def _estilizar_tabla_dictamen(tabla, color_borde="CBD5E1"):
    tabla.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblPr = tabla._tbl.tblPr
    tblBorders = tblPr.find(qn('w:tblBorders'))
    if tblBorders is not None:
        tblPr.remove(tblBorders)
    tblBorders = OxmlElement('w:tblBorders')
    for borde in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        el = OxmlElement(f'w:{borde}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), '4')
        el.set(qn('w:color'), color_borde)
        tblBorders.append(el)
    tblPr.append(tblBorders)

def _agregar_seccion_dictamen(doc, num, titulo):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(f"{num}. {titulo.upper()}")
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x69, 0x1C, 0x32)

def generar_docx_dictamen_piezometrico(
    clave_acuifero,
    nombre_acuifero,
    estado_acuifero,
    area_km2,
    df_piezo,
    poligono_geom=None,
    t_darcy=0.0,
    resumen_repda=None,
    resumen_cobertura=None,
    resumen_delta_v=None
):
    if not DOCX_DISPONIBLE:
        return b""
    
    doc = Document()
    for s in doc.sections:
        s.top_margin = Cm(2.0)
        s.bottom_margin = Cm(2.0)
        s.left_margin = Cm(2.5)
        s.right_margin = Cm(2.5)

    # Membrete Oficial CONAGUA
    p_header = doc.add_paragraph()
    p_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_header.paragraph_format.space_after = Pt(2)
    
    r1 = p_header.add_run("COMISIÓN NACIONAL DEL AGUA\n")
    r1.bold = True
    r1.font.size = Pt(13)
    r1.font.color.rgb = RGBColor(0x69, 0x1C, 0x32)
    
    r2 = p_header.add_run("SUBDIRECCIÓN GENERAL TÉCNICA | GERENCIA DE AGUAS SUBTERRÁNEAS\n")
    r2.bold = True
    r2.font.size = Pt(9.5)
    r2.font.color.rgb = RGBColor(0x24, 0x40, 0x62)
    
    r3 = p_header.add_run("DICTAMEN GEOHIDROLÓGICO Y AUDITORÍA DE LA RED PIEZOMÉTRICA\n")
    r3.bold = True
    r3.font.size = Pt(12)
    r3.font.color.rgb = RGBColor(0x11, 0x18, 0x27)
    
    p_meta = doc.add_paragraph()
    p_meta.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_meta.paragraph_format.space_after = Pt(8)
    fecha_hoy = datetime.date.today().strftime('%d/%m/%Y')
    r_meta = p_meta.add_run(f"Fecha de emisión: {fecha_hoy} | Folio Oficial: SGT-GAS-PIEZO-{clave_acuifero}-{datetime.date.today().year}")
    r_meta.font.size = Pt(8.5)
    r_meta.font.italic = True
    r_meta.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    # 1. Identificación
    _agregar_seccion_dictamen(doc, "1", "Identificación Oficial del Acuífero")
    t1 = doc.add_table(rows=3, cols=4)
    _estilizar_tabla_dictamen(t1)
    filas_t1 = [
        [("Clave Oficial:", True, "C0D7EE", "244062"), (str(clave_acuifero), False, None, "111827"), ("Nombre Oficial:", True, "C0D7EE", "244062"), (str(nombre_acuifero), True, None, "111827")],
        [("Entidad Federativa:", True, "C0D7EE", "244062"), (str(estado_acuifero or "N/D"), False, None, "111827"), ("Superficie Oficial:", True, "C0D7EE", "244062"), (f"{float(area_km2):,.2f} km²", False, None, "111827")],
        [("Estatus Operativo:", True, "C0D7EE", "244062"), ("Red Piezométrica Activa", False, None, "059669"), ("Marco Normativo:", True, "C0D7EE", "244062"), ("NOM-011-CONAGUA-2015", False, None, "111827")]
    ]
    for r_i, fila in enumerate(filas_t1):
        for c_i, (txt, neg, bg, col) in enumerate(fila):
            _formatear_celda_dictamen(t1.cell(r_i, c_i), txt, fondo_hex=bg, negrita=neg, tamano_pt=9, color_hex=col)

    # 2. Salud de la Red Piezométrica
    _agregar_seccion_dictamen(doc, "2", "Diagnóstico de Salud y Operatividad de la Red Piezométrica")
    total_pozos = 0
    pozos_activos = 0
    pct_activos = 0.0
    densidad_str = "N/D"
    media_prof_str = "N/D"
    media_elev_str = "N/D"
    periodo_str = "N/D"

    if df_piezo is not None and not df_piezo.empty:
        total_pozos = df_piezo['Pozo'].nunique() if 'Pozo' in df_piezo.columns else len(df_piezo)
        if 'Año' in df_piezo.columns:
            a_min = int(df_piezo['Año'].min())
            a_max = int(df_piezo['Año'].max())
            periodo_str = f"{a_min} – {a_max}"
            pozos_activos = df_piezo[df_piezo['Año'] >= (a_max - 3)]['Pozo'].nunique() if 'Pozo' in df_piezo.columns else 0
            pct_activos = (pozos_activos / total_pozos * 100.0) if total_pozos > 0 else 0.0
        if area_km2 > 0 and pozos_activos > 0:
            densidad_val = area_km2 / pozos_activos
            densidad_str = f"1 pozo / {densidad_val:.1f} km²"
        if 'Prof_NE_m' in df_piezo.columns:
            m_p = df_piezo['Prof_NE_m'].dropna().mean()
            if pd.notna(m_p): media_prof_str = f"{float(m_p):.2f} m.b.n.s."
        if 'Elev_NE_msnm' in df_piezo.columns:
            m_e = df_piezo['Elev_NE_msnm'].dropna().mean()
            if pd.notna(m_e): media_elev_str = f"{float(m_e):.2f} m.s.n.m."

    t2 = doc.add_table(rows=4, cols=4)
    _estilizar_tabla_dictamen(t2)
    filas_t2 = [
        [("Pozos Registrados (Censo):", True, "C0D7EE", "244062"), (f"{total_pozos} aprovechamientos", False, None, "111827"), ("Pozos Activos (≤ 3 años):", True, "C0D7EE", "244062"), (f"{pozos_activos} ({pct_activos:.0f}% operatividad)", True, None, "059669" if pct_activos >= 70 else "B91C1C")],
        [("Pozos Desatendidos:", True, "C0D7EE", "244062"), (f"{total_pozos - pozos_activos} pozos", False, None, "B91C1C" if (total_pozos - pozos_activos) > 0 else "111827"), ("Densidad de Observación:", True, "C0D7EE", "244062"), (densidad_str, False, None, "111827")],
        [("Nivel Estático Promedio:", True, "C0D7EE", "244062"), (media_prof_str, False, None, "111827"), ("Elevación Piezométrica Media:", True, "C0D7EE", "244062"), (media_elev_str, False, None, "111827")],
        [("Período de Registro:", True, "C0D7EE", "244062"), (periodo_str, False, None, "111827"), ("Estándar Normativo Requerido:", True, "C0D7EE", "244062"), ("1 pozo / 50–100 km²", False, None, "64748B")]
    ]
    for r_i, fila in enumerate(filas_t2):
        for c_i, (txt, neg, bg, col) in enumerate(fila):
            _formatear_celda_dictamen(t2.cell(r_i, c_i), txt, fondo_hex=bg, negrita=neg, tamano_pt=9, color_hex=col)

    # 3. REPDA
    _agregar_seccion_dictamen(doc, "3", "Derechos de Extracción de Aguas Subterráneas (REPDA Oficial)")
    if resumen_repda and resumen_repda.get("volumen_total_hm3", 0.0) > 0:
        vol_tot = resumen_repda.get("volumen_total_hm3", 0.0)
        vol_m3 = resumen_repda.get("volumen_total_m3", vol_tot * 1e6)
        total_aprov = resumen_repda.get("total_aprovechamientos", 0)
        uso_pred = resumen_repda.get("uso_predominante", "N/D")
        pct_pred = resumen_repda.get("pct_predominante", 0.0)

        t3_res = doc.add_table(rows=2, cols=4)
        _estilizar_tabla_dictamen(t3_res)
        filas_t3_res = [
            [("Volumen Total Concesionado:", True, "C0D7EE", "244062"), (f"{vol_tot:,.3f} hm³/año", True, None, "111827"), ("Equivalente en m³/año:", True, "C0D7EE", "244062"), (f"{vol_m3:,.0f} m³/año", False, None, "111827")],
            [("Aprovechamientos Georreferenciados:", True, "C0D7EE", "244062"), (f"{total_aprov:,} pozos", False, None, "111827"), ("Uso Predominante:", True, "C0D7EE", "244062"), (f"{uso_pred} ({pct_pred:.1f}%)", True, None, "2563EB")]
        ]
        for r_i, fila in enumerate(filas_t3_res):
            for c_i, (txt, neg, bg, col) in enumerate(fila):
                _formatear_celda_dictamen(t3_res.cell(r_i, c_i), txt, fondo_hex=bg, negrita=neg, tamano_pt=9, color_hex=col)

        df_usos = resumen_repda.get("df_usos", pd.DataFrame())
        if not df_usos.empty:
            p_sub = doc.add_paragraph()
            p_sub.paragraph_format.space_before = Pt(6)
            p_sub.paragraph_format.space_after = Pt(2)
            r_sub = p_sub.add_run("Distribución de la Extracción por Tipo de Uso Consuntivo:")
            r_sub.font.size = Pt(9.5)
            r_sub.font.bold = True
            r_sub.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

            t3_tab = doc.add_table(rows=len(df_usos) + 2, cols=4)
            _estilizar_tabla_dictamen(t3_tab)
            headers = ["Uso Consuntivo", "Volumen (hm³/año)", "Volumen (m³/año)", "Participación (%)"]
            for c_i, h in enumerate(headers):
                _formatear_celda_dictamen(t3_tab.cell(0, c_i), h, fondo_hex="244062", negrita=True, tamano_pt=9, color_hex="FFFFFF", alineacion=WD_ALIGN_PARAGRAPH.CENTER)

            for r_idx, (_, row_u) in enumerate(df_usos.iterrows(), start=1):
                u_nom = str(row_u['Uso'])
                v_h = float(row_u['Volumen_hm3'])
                v_m = float(row_u['Volumen_m3'])
                p_v = float(row_u['Pct_Volumen'])
                bg_row = "F8FAFC" if (r_idx % 2 == 1) else None
                _formatear_celda_dictamen(t3_tab.cell(r_idx, 0), u_nom, fondo_hex=bg_row, negrita=False, tamano_pt=9, color_hex="1E293B")
                _formatear_celda_dictamen(t3_tab.cell(r_idx, 1), f"{v_h:,.3f}", fondo_hex=bg_row, negrita=False, tamano_pt=9, color_hex="1E293B", alineacion=WD_ALIGN_PARAGRAPH.RIGHT)
                _formatear_celda_dictamen(t3_tab.cell(r_idx, 2), f"{v_m:,.0f}", fondo_hex=bg_row, negrita=False, tamano_pt=9, color_hex="1E293B", alineacion=WD_ALIGN_PARAGRAPH.RIGHT)
                _formatear_celda_dictamen(t3_tab.cell(r_idx, 3), f"{p_v:.1f}%", fondo_hex=bg_row, negrita=False, tamano_pt=9, color_hex="1E293B", alineacion=WD_ALIGN_PARAGRAPH.RIGHT)

            tot_idx = len(df_usos) + 1
            _formatear_celda_dictamen(t3_tab.cell(tot_idx, 0), "TOTAL ACUÍFERO", fondo_hex="C0D7EE", negrita=True, tamano_pt=9, color_hex="244062")
            _formatear_celda_dictamen(t3_tab.cell(tot_idx, 1), f"{vol_tot:,.3f}", fondo_hex="C0D7EE", negrita=True, tamano_pt=9, color_hex="244062", alineacion=WD_ALIGN_PARAGRAPH.RIGHT)
            _formatear_celda_dictamen(t3_tab.cell(tot_idx, 2), f"{vol_m3:,.0f}", fondo_hex="C0D7EE", negrita=True, tamano_pt=9, color_hex="244062", alineacion=WD_ALIGN_PARAGRAPH.RIGHT)
            _formatear_celda_dictamen(t3_tab.cell(tot_idx, 3), "100.0%", fondo_hex="C0D7EE", negrita=True, tamano_pt=9, color_hex="244062", alineacion=WD_ALIGN_PARAGRAPH.RIGHT)
    else:
        p_no_repda = doc.add_paragraph()
        p_no_repda.paragraph_format.space_before = Pt(4)
        p_no_repda.add_run("No se localizaron títulos de concesión en el Registro Público de Derechos de Agua (REPDA) para esta demarcación geohidrológica.").italic = True

    # 4. Auditoría Territorial y Zonas Ciegas
    _agregar_seccion_dictamen(doc, "4", "Auditoría Territorial y Detección de Zonas Ciegas")
    if resumen_cobertura:
        t4 = doc.add_table(rows=3, cols=4)
        _estilizar_tabla_dictamen(t4)
        a_cub = resumen_cobertura.get('area_cubierta_km2', 0.0)
        p_cub = resumen_cobertura.get('pct_cubierta', 0.0)
        a_cie = resumen_cobertura.get('area_ciega_km2', 0.0)
        p_cie = resumen_cobertura.get('pct_ciega', 0.0)
        n_prop = len(resumen_cobertura.get('df_propuestas', [])) if isinstance(resumen_cobertura.get('df_propuestas'), pd.DataFrame) else resumen_cobertura.get('n_propuestos', 0)
        calif = resumen_cobertura.get('diagnostico', resumen_cobertura.get('calificacion', 'En Evaluación'))

        filas_t4 = [
            [("Radio de Cobertura Representativo:", True, "C0D7EE", "244062"), ("5.0 km", False, None, "111827"), ("Calificación Territorial:", True, "C0D7EE", "244062"), (str(calif), True, None, "059669" if p_cub >= 70 else "B91C1C")],
            [("Superficie con Cobertura Activa:", True, "C0D7EE", "244062"), (f"{a_cub:,.1f} km² ({p_cub:.1f}%)", True, None, "059669"), ("Superficie en Zona Ciega (Sin Monitoreo):", True, "C0D7EE", "244062"), (f"{a_cie:,.1f} km² ({p_cie:.1f}%)", True, None, "B91C1C")],
            [("Pozos Estratégicos Propuestos:", True, "C0D7EE", "244062"), (f"{n_prop} piezómetros sugeridos", True, None, "2563EB"), ("Impacto Geostadístico:", True, "C0D7EE", "244062"), ("Alta incertidumbre en zonas ciegas", False, None, "64748B")]
        ]
        for r_i, fila in enumerate(filas_t4):
            for c_i, (txt, neg, bg, col) in enumerate(fila):
                _formatear_celda_dictamen(t4.cell(r_i, c_i), txt, fondo_hex=bg, negrita=neg, tamano_pt=9, color_hex=col)
    else:
        p_cob_nd = doc.add_paragraph()
        p_cob_nd.paragraph_format.space_before = Pt(4)
        p_cob_nd.add_run("Auditoría territorial ejecutada a partir de los puntos piezométricos georreferenciados disponibles en el modelo geostadístico.").italic = True

    # 5. Dinámica de Flujo y Cambio de Almacenamiento
    _agregar_seccion_dictamen(doc, "5", "Dinámica Hidráulica y Balance de Almacenamiento (NOM-011-CONAGUA-2015)")
    if resumen_delta_v:
        dV_hm3 = resumen_delta_v.get("delta_V_hm3", 0.0)
        tasa_hm3 = resumen_delta_v.get("tasa_V_anual_hm3", 0.0)
        sy_val = resumen_delta_v.get("sy", 0.10)
        per_str = resumen_delta_v.get("periodo", "Período Evaluado")

        t5 = doc.add_table(rows=2, cols=4)
        _estilizar_tabla_dictamen(t5)
        color_v = "059669" if dV_hm3 >= 0 else "B91C1C"
        filas_t5 = [
            [("Cambio de Almacenamiento (ΔV):", True, "C0D7EE", "244062"), (f"{dV_hm3:+,.2f} hm³", True, None, color_v), ("Tasa Anual de Variación:", True, "C0D7EE", "244062"), (f"{tasa_hm3:+,.2f} hm³/año", True, None, color_v)],
            [("Coeficiente de Almacenamiento (Sy):", True, "C0D7EE", "244062"), (f"{sy_val:.3f}", False, None, "111827"), ("Período de Análisis:", True, "C0D7EE", "244062"), (str(per_str), False, None, "111827")]
        ]
        for r_i, fila in enumerate(filas_t5):
            for c_i, (txt, neg, bg, col) in enumerate(fila):
                _formatear_celda_dictamen(t5.cell(r_i, c_i), txt, fondo_hex=bg, negrita=neg, tamano_pt=9, color_hex=col)

    # Evaluación de Darcy
    p_darcy = doc.add_paragraph()
    p_darcy.paragraph_format.space_before = Pt(6)
    p_darcy.paragraph_format.space_after = Pt(2)
    if t_darcy > 0:
        r_d = p_darcy.add_run(f"• Hidráulica de Darcy Parametrizada: Se incorporó una Transmisividad representativa de T = {t_darcy:,.1f} m²/día. El caudal unitario subterráneo estimado (q = T · i) se calcula a lo largo de las trayectorias preferenciales y transectos de flujo.")
        r_d.font.size = Pt(9)
        r_d.font.italic = True
    else:
        r_d = p_darcy.add_run("• Criterio Hidráulico en Ausencia de Transmisividad (T): Al no disponerse de pruebas de bombeo calibradas en toda la malla, el análisis físico se fundó en el tensor de gradientes hidráulicos equipotenciales (i = -∇h). Este método identifica de forma rigurosa la dirección ortogonal de las líneas de corriente, las divisorias piezométricas y los conos de abatimiento inducidos por concentración de bombeo.")
        r_d.font.size = Pt(9)
        r_d.font.italic = True

    # 6. Conclusiones y Recomendaciones
    _agregar_seccion_dictamen(doc, "6", "Conclusiones y Recomendaciones Geohidrológicas")
    recs = [
        "1. Priorizar la perforación e instrumentación de pozos de observación en las zonas ciegas territoriales identificadas, a fin de mitigar la incertidumbre en la interpolación geostadística por Kriging Ordinario.",
        "2. Reactivar el programa de medición piezométrica en los pozos desatendidos con más de 3 años de inactividad, restaurando la representatividad histórica de la serie de tiempo.",
        "3. Establecer monitoreo telemétrico continuo automatizado con transductores piezoresistivos en los sectores con mayor abatimiento piezométrico y mayor densidad de concesiones REPDA.",
        "4. Realizar pruebas de bombeo escalonadas y de gasto constante para calibrar localmente la transmisividad y el coeficiente de almacenamiento (Sy).",
        "5. Integrar los resultados del presente dictamen a los estudios técnicos oficiales de actualización de disponibilidad media anual bajo la NOM-011-CONAGUA-2015."
    ]
    for rec in recs:
        p_item = doc.add_paragraph()
        p_item.paragraph_format.space_before = Pt(2)
        p_item.paragraph_format.space_after = Pt(2)
        r_item = p_item.add_run(rec)
        r_item.font.size = Pt(9)
        r_item.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

    # Pie de página / Certificación
    p_cert = doc.add_paragraph()
    p_cert.paragraph_format.space_before = Pt(16)
    p_cert.paragraph_format.space_after = Pt(2)
    p_cert.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_cert = p_cert.add_run("_____________________________________________________\nDIRECCIÓN DE EVALUACIÓN Y MONITOREO GEOHIDROLÓGICO\nCOMISIÓN NACIONAL DEL AGUA")
    r_cert.font.size = Pt(8.5)
    r_cert.font.bold = True
    r_cert.font.color.rgb = RGBColor(0x69, 0x1C, 0x32)

    try:
        activar_ortografia_y_gramatica_es_mx(doc)
    except Exception:
        pass

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

# =======================================================
# 📊 8. EJE 1: SALUD E INVENTARIO DE LA RED
# =======================================================
with st.container(border=True):
    st.markdown("<p style='color:#691C32; font-weight:700; margin:0 0 8px 0; font-size:14px;'>📡 SALUD Y OPERATIVIDAD DE LA RED PIEZOMÉTRICA</p>", unsafe_allow_html=True)
    col_i1, col_i2, col_i3, col_i4 = st.columns(4)

    total_pozos = len(pozos_disponibles)
    anio_reciente = df_ac['Año'].max()
    pozos_activos = df_ac[df_ac['Año'] >= (anio_reciente - 3)]['Pozo'].nunique()
    porcentaje_activos = (pozos_activos / total_pozos) * 100 if total_pozos > 0 else 0

    col_i1.metric("Pozos Registrados", total_pozos)
    col_i2.metric("Pozos Activos (≤ 3 años)", pozos_activos, f"{porcentaje_activos:.0f}% Operatividad", delta_color="normal" if porcentaje_activos > 70 else "inverse")

    if area_actual > 0 and pozos_activos > 0:
        densidad = area_actual / pozos_activos
        col_i3.metric("Densidad Espacial", f"1 pozo / {densidad:.1f} km²")
    else:
        col_i3.metric("Densidad Espacial", "N/D", "Sin pozos activos")

    col_i4.metric("Sin Datos Recientes", total_pozos - pozos_activos, "Pozos Desatendidos", delta_color="inverse")

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

# =======================================================
# 📋 8.1 GENERADOR DE DICTAMEN TÉCNICO OFICIAL (.DOCX)
# =======================================================
with st.expander("📋 Dictamen Geohidrológico y Ficha Técnica Oficial (.docx)", expanded=False):
    col_d1, col_d2 = st.columns([3, 1])
    with col_d1:
        st.markdown(f"""
        <div style="font-size:12.5px; color:#334155; line-height:1.5;">
            <b>Emisión Institucional CONAGUA / Gerencia de Aguas Subterráneas</b><br>
            Genera un informe pericial y dictamen técnico en formato <b>Microsoft Word (.docx)</b> conforme a los lineamientos
            oficiales de la <b>NOM-011-CONAGUA-2015</b>. Incluye identificación del acuífero, diagnóstico de salud de la red piezométrica,
            análisis de derechos de extracción REPDA por tipo de uso consuntivo, auditoría territorial de cobertura (zonas ciegas),
            cálculo de desalmacenamiento (ΔV) y evaluación hidráulica (Darcy / equipotenciales).
        </div>
        """, unsafe_allow_html=True)
    with col_d2:
        try:
            res_repda_doc = cargar_resumen_repda(clave_actual)
            res_cob_doc = st.session_state.get(f"res_cob_{clave_actual}")
            if not res_cob_doc and poligono_oficial_geom is not None and df_ac is not None and not df_ac.empty:
                try:
                    res_cob_doc = calcular_cobertura_y_zonas_ciegas(df_ac, radio_km=5.0, geom_acuifero=poligono_oficial_geom)
                except Exception:
                    res_cob_doc = None
            
            res_dv_doc = st.session_state.get(f"res_dv_{clave_actual}")
            t_darcy_doc = float(st.session_state.get("input_transmisividad_darcy", 0.0) or 0.0)

            fecha_doc_str = datetime.date.today().strftime('%Y%m%d')
            bytes_dictamen = generar_docx_dictamen_piezometrico(
                clave_acuifero=clave_actual,
                nombre_acuifero=nombre_actual,
                estado_acuifero=st.session_state.get("piezo_sel_edo", "N/D"),
                area_km2=float(area_actual),
                df_piezo=df_ac,
                poligono_geom=poligono_oficial_geom,
                t_darcy=t_darcy_doc,
                resumen_repda=res_repda_doc,
                resumen_cobertura=res_cob_doc,
                resumen_delta_v=res_dv_doc
            )

            st.download_button(
                label="📥 Descargar Dictamen Word (.docx)",
                data=bytes_dictamen,
                file_name=f"Dictamen_Geohidrologico_{clave_actual}_{fecha_doc_str}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
        except Exception as e_doc:
            st.warning(f"Dictamen en preparación ({e_doc})")

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

# =======================================================
# 🛠️ 9. INTERFAZ DE TABS
# =======================================================
tab_mapa, tab_evolucion, tab_cobertura, tab_hidrograma, tab_alertas = st.tabs([
    "🗺️ Dinámica de Flujo y Variogramas", 
    "📉 Evolución y Conos de Abatimiento (Δh)", 
    "🎯 Cobertura y Zonas Ciegas",
    "📈 Hidrogramas Inteligentes", 
    "🚨 Forecasting y Alertas"
])

# --- EJE 3: DINÁMICA ESPACIAL AVANZADA ---
with tab_mapa:
    @st.fragment
    def renderizar_pestaña_mapa():
        
        if "poly_uploader_key" not in st.session_state:
            st.session_state["poly_uploader_key"] = 0
        if "poligono_personalizado" not in st.session_state:
            st.session_state["poligono_personalizado"] = None
            
        def limpiar_poly():
            st.session_state["poly_uploader_key"] = st.session_state.get("poly_uploader_key", 0) + 1
            st.session_state["poligono_personalizado"] = None

        anios_disp = sorted([int(a) for a in df_ac['Año'].dropna().unique().tolist()])
        anios_con_pozos = df_ac.groupby('Año')['Pozo'].nunique()
        anios_validos = [int(a) for a in anios_con_pozos[anios_con_pozos >= 4].index.tolist()]
        anio_default = max(anios_validos) if anios_validos else (max(anios_disp) if anios_disp else 2024)
        idx_anio = anios_disp.index(anio_default) if anio_default in anios_disp else len(anios_disp)-1

        geom_oficial = st.session_state.get("poligono_personalizado", None)
        if geom_oficial is None:
            geom_oficial = poligono_oficial_geom

        opciones_delimitacion = ["Pozos de Monitoreo (Envolvente Convexa)"]
        if geom_oficial is not None:
            opciones_delimitacion.insert(0, "Polígono Oficial del Acuífero")

        with st.container(border=True):
            c_f1, c_f2, c_f3, c_f4 = st.columns([1.1, 1.4, 1.8, 1.4])
            anio_sel = c_f1.selectbox("Año Objetivo:", anios_disp, index=idx_anio, key="sel_krig_anio_objetivo")
            modo_sync = c_f2.selectbox(
                "Sincronización Temporal:",
                ["Interpolación Dinámica", "Corte Estricto (Sin interpolar)"],
                key="sel_krig_modo_sync"
            )
            var_interp = c_f3.selectbox(
                "Variable a Modelar:",
                ["Carga Hidráulica (msnm) [Recomendado para flujo]", "Profundidad del Nivel (m)"],
                key="sel_krig_var_interp"
            )
            modo_delimitacion = c_f4.selectbox(
                "Delimitar Kriging por:", 
                opciones_delimitacion, 
                index=0,
                key="sel_krig_delimitacion"
            )

        var_real = 'Carga_Hidraulica' if "Carga" in var_interp else 'Profundidad_NE'
        modo_sync_cod = "interpolado" if "Interpolación" in modo_sync else "estricto"
        df_ultimo = obtener_red_sincronizada(df_ac, anio_sel, var_nombre=var_real, modo=modo_sync_cod, ventana_tolerancia=3)

        df_ranking_loocv, modelo_optimo_sugerido, detalles_loocv = None, None, None
        if not df_ultimo.empty and len(df_ultimo) >= 4:
            df_ranking_loocv, modelo_optimo_sugerido, detalles_loocv = evaluar_validacion_cruzada_loocv(df_ultimo, var_real)

        if not df_ultimo.empty:
            media_val = float(df_ultimo[var_real].mean())
            min_val = float(df_ultimo[var_real].min())
            max_val = float(df_ultimo[var_real].max())
            rango_val = max_val - min_val
            unidad_var = "msnm" if var_real == 'Carga_Hidraulica' else "m"

            n_reales = len(df_ultimo[df_ultimo['Tipo_Dato'] == 'Medición Real'])
            n_interp = len(df_ultimo) - n_reales

            n_abat = 0
            n_recup = 0
            for _, r_p in df_ultimo.iterrows():
                df_hist_p = df_ac[df_ac['Pozo'].astype(str) == str(r_p['Pozo'])]
                if len(df_hist_p) >= 2:
                    slope = np.polyfit(df_hist_p['Año'], df_hist_p['Profundidad_NE'], 1)[0]
                    if slope > 0.1: n_abat += 1
                    elif slope < -0.1: n_recup += 1

            rmse_card = f"{df_ranking_loocv.iloc[0]['RMSE (m)']:.2f} m" if df_ranking_loocv is not None and not df_ranking_loocv.empty else "N/A"
            r2_card = f"R²: {df_ranking_loocv.iloc[0]['R²']:.3f}" if df_ranking_loocv is not None and not df_ranking_loocv.empty else "N/A"

            with st.container(border=True):
                m1, m2, m3, m4 = st.columns(4)
                m1.metric(
                    f"{'Carga Hidráulica' if var_real == 'Carga_Hidraulica' else 'Profundidad'} Media",
                    f"{media_val:.2f} {unidad_var}",
                    f"Rango: {rango_val:.1f} {unidad_var} [{min_val:.1f} a {max_val:.1f}]",
                    help="Promedio aritmético de los niveles en los pozos monitoreados para este año."
                )
                m2.metric(
                    "Pozos de Monitoreo",
                    f"{len(df_ultimo)} pozos",
                    f"{n_reales} medidos | {n_interp} interp.",
                    help="Pozos sincronizados para el año objetivo (medición directa vs sincronización temporal)."
                )
                m3.metric(
                    "Tendencia Histórica",
                    f"{n_abat} en descenso",
                    f"{n_recup} en recuperación",
                    delta_color="inverse" if n_abat > n_recup else "normal",
                    help="Número de pozos con tendencia de descenso (abatimiento) vs ascenso (recuperación) en su serie de tiempo."
                )
                m4.metric(
                    "Ajuste LOOCV Óptimo",
                    rmse_card,
                    f"Modelo: {modelo_optimo_sugerido.split(' ')[0] if modelo_optimo_sugerido else 'N/A'} ({r2_card})",
                    help="Precisión del modelo con menor error cuadrático medio tras validación cruzada iterativa Leave-One-Out."
                )

        st.markdown("<div style='margin-top: 6px;'></div>", unsafe_allow_html=True)
        col_izq, col_der = st.columns([1.15, 2.85], gap="large")
        
        with col_izq:
            st.markdown("<h4 style='color:#691C32; margin-top:0; font-size:15px; margin-bottom:8px;'>⚙️ Panel Geostadístico</h4>", unsafe_allow_html=True)
            tab_params, tab_vario, tab_valida = st.tabs(["🔧 Configuración", "📈 Variograma", "🎯 Validación LOOCV"])
            
            with tab_params:
                lista_modelos = [
                    "Esférico (spherical)", "Exponencial (exponential)", "Gaussiano (gaussian)", "Lineal (no nugget)", 
                    "Raíz Cuadrada (square root)", "Logarítmico", "Stable (0 < k < 2)", "Cúbico"
                ]
                
                idx_param = 0
                if "sel_krig_modelo" in st.session_state and st.session_state["sel_krig_modelo"] in lista_modelos:
                    idx_param = lista_modelos.index(st.session_state["sel_krig_modelo"])
                
                st.markdown("<b style='font-size:12px; color:#1e293b;'>Modelo de Semivariograma:</b>", unsafe_allow_html=True)
                c_mod1, c_mod2 = st.columns([2.0, 1.0])
                param = c_mod1.selectbox("Modelo de Variograma:", lista_modelos, index=idx_param, key="sel_krig_param_box", label_visibility="collapsed")
                
                with c_mod2:
                    if df_ranking_loocv is not None and not df_ranking_loocv.empty:
                        if st.button("✨ Óptimo", key="btn_usar_optimo_krig", help=f"Aplicar automáticamente el semivariograma con menor RMSE ({modelo_optimo_sugerido})"):
                            st.session_state["sel_krig_modelo"] = modelo_optimo_sugerido
                            st.rerun()

                if df_ranking_loocv is not None and not df_ranking_loocv.empty:
                    rmse_val = df_ranking_loocv.iloc[0]['RMSE (m)']
                    st.markdown(
                        f"<div style='background:#f0fdf4; border:1px solid #bbf7d0; border-radius:4px; padding:4px 8px; font-size:10.5px; color:#166534; margin-top:-2px; margin-bottom:10px; line-height:1.3;'>"
                        f"🏆 <b>Sugerencia Óptima (LOOCV):</b> {modelo_optimo_sugerido} (RMSE: <b>{rmse_val:.2f} m</b>)"
                        f"</div>", 
                        unsafe_allow_html=True
                    )

                if len(df_ultimo) >= 4:
                    rango_estimado = max(1.0, float(df_ultimo[var_real].max() - df_ultimo[var_real].min()))
                    def_equidistancia = max(0.5, round(rango_estimado / 10.0, 1))
                    if def_equidistancia >= 5: def_equidistancia = round(def_equidistancia / 5.0) * 5.0
                else:
                    rango_estimado = 50.0
                    def_equidistancia = 5.0

                st.markdown("<b style='font-size:12px; color:#1e293b; margin-top:6px;'>Ajustes Cartográficos:</b>", unsafe_allow_html=True)
                intervalo_iso = st.slider(
                    "Equidistancia de Isolíneas (m):", 
                    min_value=max(0.5, round(rango_estimado / 40.0, 1)), 
                    max_value=max(2.0, round(rango_estimado / 2.0, 1)), 
                    value=float(min(max(2.0, round(rango_estimado / 2.0, 1)), def_equidistancia)), 
                    step=0.5 if rango_estimado < 20 else 1.0,
                    key="slider_equidistancia_iso"
                )
                densidad_flujo = st.slider("Densidad de Vectores de Flujo:", 8, 36, 20, 2, key="slider_densidad_flujo")

                with st.expander("💧 Hidráulica de Flujo Subterráneo (Darcy)", expanded=False):
                    st.caption(r"Ingresa la Transmisividad representativa ($T$) para estimar el caudal unitario de flujo ($q = T \cdot i$). Si es 0, opera exclusivamente en modo de gradiente hidráulico.")
                    t_darcy = st.number_input(
                        "Transmisividad de Referencia (T, m²/día):", 
                        min_value=0.0, max_value=25000.0, value=0.0, step=50.0, format="%.1f", 
                        key="input_transmisividad_darcy",
                        help="Transmisividad del acuífero (T = K · b). Permite calcular q = T · i en m³/día por metro de ancho."
                    )
                    if t_darcy > 0:
                        st.info(f"Modo Darcy Activo: T = {t_darcy:,.1f} m²/día. Se calculará q = T · i en vectores y transecto.")

                with st.expander("📁 Subir Polígono Personalizado", expanded=False):
                    st.caption("Carga un archivo (.geojson o .zip con shapefile) para delimitar el área de estudio.")
                    up_key = f"up_poly_piezo_{st.session_state.get('poly_uploader_key', 0)}"
                    up_geom = st.file_uploader("Cargar Polígono", type=['geojson', 'json', 'zip'], key=up_key, label_visibility="collapsed")
                    
                    c_poly1, c_poly2 = st.columns(2)
                    with c_poly1:
                        if up_geom is not None:
                            if st.button("🚀 Cargar", use_container_width=True, type="primary", key="btn_cargar_poly"):
                                try:
                                    if up_geom.name.endswith(".zip"):
                                        with tempfile.TemporaryDirectory() as tmpdir:
                                            zip_path = os.path.join(tmpdir, "poly.zip")
                                            with open(zip_path, "wb") as f_up: f_up.write(up_geom.read())
                                            gdf_up = gpd.read_file(f"zip://{zip_path}")
                                    else:
                                        gdf_up = gpd.read_file(up_geom)

                                    if gdf_up.crs != "EPSG:4326":
                                        gdf_up = gdf_up.to_crs(epsg=4326)
                                    st.session_state["poligono_personalizado"] = gdf_up.unary_union
                                    st.success("✅ Polígono cargado.")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"Error procesando archivo: {err}")
                        else:
                            st.button("🚀 Cargar", use_container_width=True, type="primary", disabled=True, key="btn_cargar_poly_dis")
                    
                    with c_poly2:
                        st.button("🧹 Limpiar", use_container_width=True, type="secondary", key="btn_limpiar_poly", on_click=limpiar_poly)

            with tab_vario:
                ph_variograma = st.empty()

            with tab_valida:
                ph_validacion = st.empty()

        # 2. MAPA Y RESULTADOS (COLUMNA DERECHA)
        with col_der:
            geom_activa = st.session_state.get("poligono_personalizado", None)
            if geom_activa is None:
                geom_activa = poligono_oficial_geom

            if len(df_ultimo) >= 4:
                with st.spinner("Modelando superficie geostadística y delimitando fronteras..."):
                    geom_para_kriging = geom_activa if modo_delimitacion == "Polígono Oficial del Acuífero" else None
                    bounds_limite_hashable = geom_para_kriging.bounds if geom_para_kriging is not None else None
                    
                    resultado_kriging = resolver_malla_kriging(
                        df_ultimo, var_real, param, bounds_limite=bounds_limite_hashable
                    )
                    
                    if resultado_kriging[0] is None:
                        st.error(resultado_kriging[1])
                    else:
                        X, Y, Z, grid_x, grid_y, bounds, props_kriging, exp_lags, exp_semi, smooth_lags, theo_semi = resultado_kriging
                        
                        pts_grid = np.column_stack((X.ravel(), Y.ravel()))
                        hull_pts = None
                        inside_mask = None
                        
                        if modo_delimitacion == "Polígono Oficial del Acuífero" and geom_activa is not None:
                            try:
                                if geom_activa.geom_type == 'Polygon':
                                    path_poly = MplPath(np.array(geom_activa.exterior.coords))
                                    inside_mask = path_poly.contains_points(pts_grid).reshape(X.shape)
                                elif geom_activa.geom_type == 'MultiPolygon':
                                    mask_accum = np.zeros(len(pts_grid), dtype=bool)
                                    for poly_sub in geom_activa.geoms:
                                        p_sub = MplPath(np.array(poly_sub.exterior.coords))
                                        mask_accum |= p_sub.contains_points(pts_grid)
                                    inside_mask = mask_accum.reshape(X.shape)
                            except Exception:
                                inside_mask = None

                        if inside_mask is None:
                            x_pozos = df_ultimo['Longitud'].values
                            y_pozos = df_ultimo['Latitud'].values
                            try:
                                hull = ConvexHull(np.column_stack((x_pozos, y_pozos)))
                                hull_pts = np.column_stack((x_pozos[hull.vertices], y_pozos[hull.vertices]))
                                hull_path = MplPath(hull_pts)
                                inside_mask = hull_path.contains_points(pts_grid).reshape(X.shape)
                            except Exception:
                                inside_mask = np.ones(X.shape, dtype=bool)

                        Z_masked = np.where(inside_mask, Z, np.nan)

                        img_kriging, vmin, vmax = render_imagen_kriging(X, Y, Z_masked, bounds)
                        img_isolineas, geojson_iso, shp_iso_zip = render_imagen_isolineas(X, Y, Z_masked, bounds, intervalo_iso, var_real)
                        img_flujo, geojson_flujo, shp_flujo_zip = render_imagen_vectores(X, Y, Z, grid_x, grid_y, bounds, var_real, densidad_flujo, inside_mask, transmisividad=t_darcy)

                        geotiff_bytes = generar_geotiff_bytes(Z_masked, bounds)
                        mask_val = ~np.isnan(Z_masked)
                        lons_k = np.round(X[mask_val], 6)
                        lats_k = np.round(Y[mask_val], 6)
                        vals_k = np.round(Z_masked[mask_val], 3)
                        df_grid = pd.DataFrame({"LONGITUD": lons_k, "LATITUD": lats_k, "VALOR": vals_k})
                        features_krig = [
                            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(lo), float(la)]}, "properties": {"VALOR": float(vl), "VARIABLE": var_real}}
                            for lo, la, vl in zip(lons_k, lats_k, vals_k)
                        ]
                        geojson_krig = json.dumps({"type": "FeatureCollection", "features": features_krig}).encode('utf-8')
                        shp_krig_zip = empaquetar_shapefile_zip(gpd.GeoDataFrame(df_grid, geometry=[Point(xy) for xy in zip(lons_k, lats_k)], crs="EPSG:4326"), f"kriging_{clave_actual}") if (GEOPANDAS_INSTALADO and not df_grid.empty) else None

                        z_list = []
                        for row in Z_masked:
                            z_list.append([None if math.isnan(v) else round(float(v), 2) for v in row])
                        z_data_json = json.dumps(z_list)
                        bounds_json = json.dumps(bounds)

                        with ph_variograma.container():
                            fig_var = go.Figure()
                            fig_var.add_trace(go.Scatter(x=exp_lags, y=exp_semi, mode='markers', name='Exp.', marker=dict(color='#9f2241', size=6)))
                            fig_var.add_trace(go.Scatter(x=smooth_lags, y=theo_semi, mode='lines', name='Teórico', line=dict(color='#285c4d', width=2)))
                            fig_var.update_layout(
                                xaxis_title="Lag", yaxis_title="Semivarianza",
                                height=250, margin=dict(t=10, b=10, l=10, r=10), plot_bgcolor='rgba(0,0,0,0)',
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
                            )
                            fig_var.update_xaxes(showgrid=True, gridcolor='rgba(200,200,200,0.2)')
                            fig_var.update_yaxes(showgrid=True, gridcolor='rgba(200,200,200,0.2)')
                            st.plotly_chart(fig_var, use_container_width=True)

                            tabla_props = f"""
                            <div style="background-color:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; padding:10px; margin-top:10px;">
                                <p style="margin:0 0 5px 0; font-size:12px; font-weight:bold; color:#691C32; border-bottom:1px solid #CBD5E1; padding-bottom:4px;">Métricas del Ajuste</p>
                                <table style="width:100%; font-size:11px; border-collapse: collapse; font-family: 'Segoe UI', sans-serif;">
                                    <tr style="border-bottom: 1px solid #E2E8F0;"><td style="color:#64748B; padding:3px 0;">R²:</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Determination (R²)']}</td></tr>
                                    <tr style="border-bottom: 1px solid #E2E8F0;"><td style="color:#64748B; padding:3px 0;">Rango:</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Fitting Range']}</td></tr>
                                    <tr style="border-bottom: 1px solid #E2E8F0;"><td style="color:#64748B; padding:3px 0;">Muestras:</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Samples']}</td></tr>
                                    <tr style="border-bottom: 1px solid #E2E8F0;"><td style="color:#64748B; padding:3px 0;">Lag Dist:</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Lag Distance']}</td></tr>
                                    <tr><td style="color:#64748B; padding:3px 0;">Dist. Max:</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Max Distance']}</td></tr>
                                </table>
                            </div>
                            """
                            st.markdown(tabla_props, unsafe_allow_html=True)

                        with ph_validacion.container():
                            if df_ranking_loocv is not None and not df_ranking_loocv.empty:
                                st.markdown("<p style='font-weight:700; color:#691C32; margin-bottom:2px; font-size:12.5px;'>🎯 VALIDACIÓN CRUZADA LOOCV</p>", unsafe_allow_html=True)
                                st.markdown("<p style='font-size:10.5px; color:#64748B; margin-bottom:8px;'>Evaluación Leave-One-Out (LOOCV) iterativa sobre los 8 modelos de semivariograma para identificar el menor error de interpolación.</p>", unsafe_allow_html=True)

                                rmse_top = df_ranking_loocv.iloc[0]['RMSE (m)']
                                mae_top = df_ranking_loocv.iloc[0]['MAE (m)']
                                r2_top = df_ranking_loocv.iloc[0]['R²']
                                
                                st.markdown(f"""
                                <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px; padding:7px 10px; margin-bottom:8px;">
                                    <span style="color:#166534; font-weight:700; font-size:11.5px;">🏆 Modelo Óptimo: {modelo_optimo_sugerido}</span><br>
                                    <span style="color:#15803d; font-size:10.5px;">RMSE Mínimo: <b>{rmse_top:.3f} m</b> | MAE: <b>{mae_top:.3f} m</b> | R²: <b>{r2_top:.4f}</b></span>
                                </div>
                                """, unsafe_allow_html=True)

                                st.markdown("<b style='font-size:11px; color:#1e293b;'>Ranking General de Precisión:</b>", unsafe_allow_html=True)
                                st.dataframe(df_ranking_loocv, use_container_width=True, hide_index=True)

                                df_det_act = detalles_loocv.get(param, detalles_loocv.get(modelo_optimo_sugerido, None))
                                if df_det_act is not None and not df_det_act.empty:
                                    st.markdown(f"<b style='font-size:11px; color:#1e293b; margin-top:6px;'>Dispersión Medido vs Predicho ({param.split(' ')[0]}):</b>", unsafe_allow_html=True)
                                    min_val = min(df_det_act['Observado'].min(), df_det_act['Predicho_LOOCV'].min())
                                    max_val = max(df_det_act['Observado'].max(), df_det_act['Predicho_LOOCV'].max())

                                    fig_loocv = go.Figure()
                                    fig_loocv.add_trace(go.Scatter(
                                        x=[min_val, max_val], y=[min_val, max_val],
                                        mode='lines', name='1:1 Ideal',
                                        line=dict(color='#64748B', dash='dash', width=1.5)
                                    ))
                                    fig_loocv.add_trace(go.Scatter(
                                        x=df_det_act['Observado'], y=df_det_act['Predicho_LOOCV'],
                                        mode='markers', name='Pozos',
                                        text=df_det_act['Pozo'] + '<br>Residuo: ' + df_det_act['Residual_m'].astype(str) + ' m',
                                        marker=dict(
                                            color=df_det_act['Abs_Residual_m'],
                                            colorscale='Reds',
                                            size=7,
                                            showscale=True,
                                            colorbar=dict(title=dict(text="|e| m", font=dict(size=9)), thickness=8, len=0.7)
                                        )
                                    ))
                                    fig_loocv.update_layout(
                                        xaxis_title="Medido (msnm)", yaxis_title="Predicho LOOCV (msnm)",
                                        height=240, margin=dict(t=10, b=10, l=10, r=10),
                                        plot_bgcolor='rgba(0,0,0,0)',
                                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=9))
                                    )
                                    fig_loocv.update_xaxes(showgrid=True, gridcolor='rgba(200,200,200,0.2)')
                                    fig_loocv.update_yaxes(showgrid=True, gridcolor='rgba(200,200,200,0.2)')
                                    st.plotly_chart(fig_loocv, use_container_width=True)

                                    with st.expander("🔬 Residuales por Pozo (Detección de Outliers)", expanded=False):
                                        fila_m = df_ranking_loocv[df_ranking_loocv['Modelo'] == param]
                                        v_rmse = fila_m['RMSE (m)'].values[0] if not fila_m.empty else rmse_top
                                        df_exp = df_det_act.copy()
                                        df_exp['Diagnóstico'] = df_exp['Abs_Residual_m'].apply(lambda e: '⚠️ Discrepancia (>2 RMSE)' if e > 2*v_rmse else 'Normal')
                                        st.dataframe(df_exp[['Pozo', 'Observado', 'Predicho_LOOCV', 'Residual_m', 'Diagnóstico']], use_container_width=True, hide_index=True)
                            else:
                                st.info("ℹ️ Se requieren al menos 4 pozos para calcular la validación cruzada geoestadística.")
                        
                        # 1. Preparar GeoJSON de Pozos Oficiales
                        features_pozos = []
                        colores_tab1 = []
                        tendencias_tab1 = []
                        for _, row in df_ultimo.iterrows():
                            df_hist = df_ac[df_ac['Pozo'].astype(str) == str(row['Pozo'])]
                            if len(df_hist) >= 2:
                                z_trend = np.polyfit(df_hist['Año'], df_hist['Profundidad_NE'], 1)[0]
                                color_punto = "#9f2241" if z_trend > 0.1 else ("#285c4d" if z_trend < -0.1 else "#b38e5d")
                                tend_txt = f"Abatimiento ({z_trend:+.2f} m/año)" if z_trend > 0.1 else (f"Recuperación ({z_trend:+.2f} m/año)" if z_trend < -0.1 else f"Estable ({z_trend:+.2f} m/año)")
                            else:
                                color_punto = "#9e9d9e"
                                tend_txt = "Sin Historial Suficiente"
                            
                            colores_tab1.append(color_punto)
                            tendencias_tab1.append(tend_txt)
                            tipo_dato_txt = str(row.get('Tipo_Dato', 'Medición Real'))
                            anio_medido_txt = int(row.get('Año_Medido', row['Año']))
                            features_pozos.append({
                                "type": "Feature",
                                "geometry": {"type": "Point", "coordinates": [row['Longitud'], row['Latitud']]},
                                "properties": {
                                    "Pozo": row['Pozo'],
                                    "Valor": round(row[var_real], 2),
                                    "Año": int(row['Año']),
                                    "Año_Medido": anio_medido_txt,
                                    "Tipo": tipo_dato_txt,
                                    "Color": color_punto,
                                    "Tendencia": tend_txt,
                                    "Variable": var_real
                                }
                            })
                        df_ultimo['Color'] = colores_tab1
                        df_ultimo['Tendencia'] = tendencias_tab1
                        geojson_pozos_str = json.dumps({"type": "FeatureCollection", "features": features_pozos})

                        # 2. Preparar GeoJSON de Puntos Adicionales (Manual/CSV)
                        features_add = []
                        for pt in st.session_state.get("marcadores_piezo", []):
                            fuente = pt.get("fuente", "manual")
                            color = "#2980b9" if fuente == "csv" else "#d35400"
                            features_add.append({
                                "type": "Feature",
                                "geometry": {"type": "Point", "coordinates": [pt['lon'], pt['lat']]},
                                "properties": {
                                    "nombre": pt['nombre'],
                                    "tipo": pt.get('tipo', 'Desconocido'),
                                    "color": color,
                                    "fuente": fuente,
                                    "atributos": pt.get('atributos', {})
                                }
                            })
                        geojson_add_str = json.dumps({"type": "FeatureCollection", "features": features_add})

                        # 3. Preparar GeoJSON de Geología
                        geojson_geo_str = "{}"
                        col_sel_geo = "LITOLOGIA"
                        dic_leyenda_rocas = {}
                        if geom_activa is not None:
                            gdf_geo, col_sel_geo, dic_leyenda_rocas = preparar_geologia_vectorial(clave_actual, geom_activa)
                            if gdf_geo is not None and not gdf_geo.empty:
                                geojson_geo_str = gdf_geo.to_json()

                        # 4. Coordenadas de la imagen para MapLibre
                        min_y, min_x = bounds[0]
                        max_y, max_x = bounds[1]

                        if geom_activa is not None:
                            try:
                                centro_lon = float(geom_activa.centroid.x)
                                centro_lat = float(geom_activa.centroid.y)
                            except Exception:
                                centro_lon = float((min_x + max_x) / 2.0)
                                centro_lat = float((min_y + max_y) / 2.0)
                        else:
                            centro_lon = float((min_x + max_x) / 2.0)
                            centro_lat = float((min_y + max_y) / 2.0)

                        img_coords_json = json.dumps([
                            [min_x, max_y], [max_x, max_y], [max_x, min_y], [min_x, min_y]
                        ])

                        if vmin == vmax:
                            vmax = vmin + 1.0

                        vmid = (vmin + vmax) / 2.0
                        var_titulo_limpio = "Carga Hidráulica (msnm)" if "Carga" in var_interp else "Profundidad del Nivel (m)"
                        
                        poly_bounds_str = json.dumps(list(geom_activa.bounds)) if geom_activa is not None else "null"
                        poly_tab1_geojson_str = json.dumps(mapping(geom_activa)) if (geom_activa is not None and GEOPANDAS_INSTALADO) else "null"
                        
                        img_krig_b64 = base64.b64encode(img_kriging).decode('utf-8')
                        img_iso_b64 = base64.b64encode(img_isolineas).decode('utf-8')
                        img_flujo_b64 = base64.b64encode(img_flujo).decode('utf-8')

                        # Carga de concesiones REPDA para visualización de extracciones vs dinámica de flujo
                        df_repda_pts_tab1, geojson_repda_tab1_str, tiene_repda_tab1 = cargar_concesiones_repda_puntos(clave_actual, st.session_state.get("repda_custom_df"))
                        n_repda_tab1 = len(df_repda_pts_tab1)
                        
                        # 5. Construcción dinámica de la leyenda editable (Estilo Visor y Descargas)
                        hay_manual = any(pt.get("fuente") == "manual" for pt in st.session_state.get("marcadores_piezo", []))
                        hay_csv = any(pt.get("fuente") == "csv" for pt in st.session_state.get("marcadores_piezo", []))
                        
                        span_edit = 'contenteditable="true" spellcheck="false" title="Haz clic para editar este texto" class="txt-leyenda-editable"'

                        leyenda_html = f"""
                        <b style="color:#691C32; font-size: 12px;"><span {span_edit}>Simbología</span></b><br>
                        <div id="leg-pozos" style="margin-top:4px;">
                            <i style="background:#9f2241;"></i> <span {span_edit}>Pozo Abatiéndose</span><br>
                            <i style="background:#285c4d;"></i> <span {span_edit}>Pozo Recuperando</span><br>
                            <i style="background:#b38e5d;"></i> <span {span_edit}>Pozo Estable</span><br>
                        </div>
                        """
                        
                        leyenda_html += f'<div id="leg-manual" style="display: {"block" if hay_manual else "none"}; margin-top:4px; border-top: 1px solid #eee; padding-top:4px;">'
                        leyenda_html += f'<i style="background:#d35400;"></i> <span {span_edit}>Puntos Manuales</span><br></div>'
                            
                        leyenda_html += f'<div id="leg-csv" style="display: {"block" if hay_csv else "none"}; margin-top:4px;">'
                        leyenda_html += f'<i class="circle" style="background:#2980b9;"></i> <span {span_edit}>Puntos CSV</span><br></div>'

                        if tiene_repda_tab1:
                            leyenda_html += f'<div id="leg-repda" style="display: none; margin-top:4px; border-top: 1px solid #eee; padding-top:4px;">'
                            leyenda_html += f'<b style="color:#691C32; font-size:11px;"><span {span_edit}>Concesiones REPDA ({n_repda_tab1})</span></b><br>'
                            leyenda_html += f'<div style="font-size:9.5px; color:#64748B; margin-bottom:2px;"><span {span_edit}>Radio proporcional a √Volumen</span></div>'
                            leyenda_html += f'<i class="circle" style="background:#16a34a;"></i> <span {span_edit}>Agrícola</span><br>'
                            leyenda_html += f'<i class="circle" style="background:#2563eb;"></i> <span {span_edit}>Público Urbano</span><br>'
                            leyenda_html += f'<i class="circle" style="background:#d97706;"></i> <span {span_edit}>Industrial</span><br>'
                            leyenda_html += f'<i class="circle" style="background:#9333ea;"></i> <span {span_edit}>Servicios / Comercial</span><br>'
                            leyenda_html += f'<i class="circle" style="background:#06b6d4;"></i> <span {span_edit}>Doméstico</span><br>'
                            leyenda_html += f'<i class="circle" style="background:#ec4899;"></i> <span {span_edit}>Diferentes Usos</span><br></div>'

                        leyenda_html += f"""
                        <div id="leg-repda-nac" style="display: none; margin-top:5px; border-top: 1px solid #eee; padding-top:4px;">
                            <b style="color:#166534; font-size:11px;"><span {span_edit}>🇲🇽 REPDA Nacional (461,914)</span></b><br>
                            <div style="font-size:9.5px; color:#64748B; margin-bottom:3px;"><span {span_edit}>Uso Oficial Registrado</span></div>
                            <i class="circle" style="background:#16a34a;"></i> <span {span_edit}>Agrícola</span><br>
                            <i class="circle" style="background:#2563eb;"></i> <span {span_edit}>Público Urbano</span><br>
                            <i class="circle" style="background:#ca8a04;"></i> <span {span_edit}>Pecuario</span><br>
                            <i class="circle" style="background:#dc2626;"></i> <span {span_edit}>Industrial</span><br>
                            <i class="circle" style="background:#9333ea;"></i> <span {span_edit}>Servicios</span><br>
                            <i class="circle" style="background:#0284c7;"></i> <span {span_edit}>Doméstico</span><br>
                            <i class="circle" style="background:#0d9488;"></i> <span {span_edit}>Diferentes Usos</span><br>
                        </div>
                        """
                            
                        if dic_leyenda_rocas:
                            leyenda_html += f'<div id="leg-geo" style="display: {"block" if False else "none"}; margin-top:4px; border-top: 1px solid #eee; padding-top:4px;">'
                            leyenda_html += f'<b style="color:#691C32; font-size:11px;"><span {span_edit}>Geología SGM ({col_sel_geo})</span></b><div style="max-height: 150px; overflow-y: auto; margin-top:4px;">'
                            for roca, color in dic_leyenda_rocas.items():
                                leyenda_html += f'<i class="square" style="background:{color};"></i> <span {span_edit} style="font-size:9.5px;">{roca}</span><br>'
                            leyenda_html += '</div></div>'

                        url_pmtiles_srv_tab1 = obtener_url_pmtiles()

                        # 6. HTML de MapLibre (Motor WebGL)
                        html_maplibre = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="utf-8" />
                            <title>Red Piezométrica MapLibre</title>
                            <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
                            <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
                            <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
                            <script src="https://unpkg.com/pmtiles@2.11.0/dist/index.js"></script>
                            
                            <!-- Librerías Vectoriales para Dibujo y Cálculo Geodésico -->
                            <link rel="stylesheet" href="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.css" type="text/css" />
                            <script src="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.js"></script>
                            <script src="https://cdn.jsdelivr.net/npm/@turf/turf@6.5.0/turf.min.js"></script>

                            <style>
                                body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; overflow: hidden; }}
                                #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; background: #ffffff; border-radius: 8px; }}
                                
                                .txt-leyenda-editable {{ 
                                    cursor: text; padding: 1px 4px; border-radius: 3px; outline: none; 
                                    border-bottom: 1px dashed transparent; transition: background-color 0.2s; 
                                }}
                                .txt-leyenda-editable:hover {{ 
                                    background-color: rgba(0,0,0,0.05); border-bottom: 1px dashed #888; 
                                }}
                                .txt-leyenda-editable:focus {{ 
                                    background-color: #ffffff; border-bottom: 1.5px solid #2980b9; 
                                    box-shadow: 0 1px 3px rgba(0,0,0,0.15); 
                                }}

                                .gis-badge-popup .maplibregl-popup-content {{
                                    background: rgba(255, 255, 255, 0.95) !important;
                                    backdrop-filter: blur(8px) !important;
                                    border: 1px solid #CBD5E1 !important;
                                    border-top: 3px solid #691C32 !important;
                                    border-radius: 6px !important;
                                    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16) !important;
                                    padding: 6px 10px !important;
                                    font-family: 'Segoe UI', Arial, sans-serif !important;
                                    line-height: 1.4 !important;
                                    pointer-events: auto !important;
                                }}
                                .gis-badge-popup .maplibregl-popup-tip {{
                                    border-top-color: rgba(255, 255, 255, 0.95) !important;
                                }}
                                .gis-badge-popup .maplibregl-popup-close-button {{
                                    font-size: 14px !important;
                                    color: #64748B !important;
                                    padding: 2px 5px !important;
                                    right: 2px !important;
                                    top: 2px !important;
                                    cursor: pointer !important;
                                }}
                                .gis-badge-popup .maplibregl-popup-close-button:hover {{
                                    color: #DC2626 !important;
                                    background: transparent !important;
                                }}

                                .hud-elevation {{
                                    position: absolute; top: 12px; right: 55px; z-index: 1000;
                                    background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
                                    color: #1e293b; padding: 7px 14px; border-radius: 8px;
                                    border: 1.5px solid #691C32; box-shadow: 0 4px 15px rgba(0,0,0,0.15);
                                    font-size: 11.5px; display: flex; gap: 14px; align-items: center; pointer-events: none;
                                }}
                                .hud-elevation b {{ color: #691C32; margin-right: 4px; }}
                                
                                .btn-open-dock-circle {{
                                    position: absolute; top: 12px; left: 12px; z-index: 1000;
                                    background: #691C32; color: #ffffff; width: 38px; height: 38px;
                                    border-radius: 50%; border: 1.5px solid #DDC9A3;
                                    box-shadow: 0 3px 12px rgba(105, 28, 50, 0.35);
                                    font-size: 19px; font-weight: bold; cursor: pointer;
                                    display: flex; align-items: center; justify-content: center;
                                    transition: all 0.2s ease;
                                }}
                                .btn-open-dock-circle:hover {{ background: #88102B; transform: scale(1.1); }}
                                
                                .workbench-dock {{
                                    position: absolute; top: 12px; left: 12px; z-index: 2000;
                                    background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                                    width: 280px; border-radius: 10px; overflow: hidden;
                                    box-shadow: 0 6px 20px rgba(0,0,0,0.25); border-top: 4px solid #691C32;
                                    border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0;
                                    font-size: 11.5px; color: #1E293B;
                                }}
                                .dock-header {{ 
                                    background: #691C32; color: white; padding: 9px 12px; 
                                    font-weight: 700; display: flex; justify-content: space-between; align-items: center; 
                                }}
                                .dock-body {{ padding: 12px 14px; max-height: 70vh; overflow-y: auto; }}
                                .dock-section {{ margin-bottom: 12px; }}
                                .dock-section label {{ display: flex; align-items: center; gap: 6px; cursor: pointer; margin-bottom: 6px; font-weight: 500; }}
                                .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; margin-top: 4px; }}
                                
                                .legend-panel {{
                                    position: absolute; bottom: 35px; left: 12px; z-index: 1000;
                                    background: rgba(255,255,255,0.95); padding: 10px 14px; border-radius: 8px;
                                    box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-size: 11px; line-height: 1.6;
                                    border: 1px solid #E2E8F0; max-width: 280px; pointer-events: auto;
                                }}
                                .legend-panel i {{ width: 12px; height: 12px; display: inline-block; border-radius: 50%; margin-right: 6px; vertical-align: middle; border: 1px solid #ccc; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }}
                                .legend-panel .square {{ border-radius: 2px; }}
                                
                                .leaflet-open-gradient-btn {{
                                    position: absolute; top: 160px; right: 10px; z-index: 1000;
                                    background: #691C32 !important; color: #ffffff; width: 29px; height: 29px;
                                    border-radius: 4px; border: 2px solid rgba(0,0,0,0.2);
                                    cursor: pointer; display: flex; align-items: center; justify-content: center;
                                    transition: background 0.2s ease;
                                }}
                                .leaflet-open-gradient-btn:hover {{ background: #88102B !important; }}

                                .gradient-docked-panel {{
                                    position: absolute; top: 160px; right: 50px; z-index: 2000;
                                    background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                                    width: 220px; border-radius: 8px; overflow: hidden;
                                    box-shadow: 0 4px 15px rgba(0,0,0,0.2); border-top: 3px solid #691C32;
                                    border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0;
                                    font-size: 11px; color: #1E293B;
                                }}
                                .docked-gradient-header {{
                                    background: #f8fafc; color: #1e293b; padding: 6px 10px;
                                    font-weight: 700; display: flex; justify-content: space-between; align-items: center;
                                    border-bottom: 1px solid #e2e8f0;
                                }}
                                .docked-gradient-close {{ cursor: pointer; font-size: 16px; color: #64748b; line-height: 1; }}
                                .docked-gradient-close:hover {{ color: #dc2626; }}
                                .docked-gradient-body {{ padding: 10px; }}
                                .gradient-bar {{ height: 10px; border-radius: 4px; background: linear-gradient(to right, #eff3ff, #bdd7e7, #6baed6, #3182bd, #08519c); margin: 6px 0; border: 1px solid #ccc; }}
                                .gradient-labels {{ display: flex; justify-content: space-between; font-weight: bold; color: #333; }}

                                .leaflet-open-draw-btn {{
                                    position: absolute; top: 196px; right: 10px; z-index: 1000;
                                    background: #ffffff; color: #691C32; width: 29px; height: 29px;
                                    border-radius: 4px; border: 2px solid rgba(0,0,0,0.2);
                                    cursor: pointer; display: flex; align-items: center; justify-content: center;
                                    transition: background 0.2s ease;
                                }}
                                .leaflet-open-draw-btn:hover {{ background: #f4f4f4; }}

                                .draw-docked-panel {{
                                    position: absolute; top: 196px; right: 50px; z-index: 2000;
                                    background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                                    width: 270px; border-radius: 8px; overflow: hidden;
                                    box-shadow: 0 4px 15px rgba(0,0,0,0.2); border-top: 3px solid #691C32;
                                    border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0;
                                    font-size: 11px; color: #1E293B;
                                }}
                                .docked-draw-header {{
                                    background: #f8fafc; color: #1e293b; padding: 6px 10px;
                                    font-weight: 700; display: flex; justify-content: space-between; align-items: center;
                                    border-bottom: 1px solid #e2e8f0; font-size: 11.5px;
                                }}
                                .docked-draw-close {{ cursor: pointer; font-size: 16px; color: #64748b; line-height: 1; font-weight: bold; }}
                                .docked-draw-close:hover {{ color: #dc2626; }}
                                .docked-draw-body {{ padding: 10px; }}

                                .draw-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 8px; }}
                                .btn-tool {{
                                    background: #ffffff; border: 1px solid #CBD5E1; border-radius: 5px;
                                    padding: 6px 8px; font-size: 11px; font-weight: 600; color: #334155;
                                    display: flex; align-items: center; gap: 6px; cursor: pointer; transition: all 0.15s ease;
                                }}
                                .btn-tool svg {{ width: 14px; height: 14px; stroke: #691C32; fill: none; stroke-width: 2; flex-shrink: 0; }}
                                .btn-tool:hover {{ background: #f1f5f9; border-color: #691C32; color: #691C32; }}
                                .btn-tool.active {{ background: #691C32; border-color: #691C32; color: #ffffff; }}
                                .btn-tool.active svg {{ stroke: #ffffff; }}

                                .btn-preset {{
                                    flex: 1; padding: 3px 4px; font-size: 10px; font-weight: 600;
                                    border: 1px solid #cbd5e1; border-radius: 3px; background: #f8fafc;
                                    color: #475569; cursor: pointer; transition: all 0.15s ease; text-align: center;
                                }}
                                .btn-preset:hover {{ background: #e2e8f0; color: #1e293b; border-color: #691C32; }}

                                .draw-measure-box {{
                                    background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 5px;
                                    padding: 8px 10px; font-size: 11px; line-height: 1.45; color: #14532D;
                                    margin-bottom: 8px; display: none;
                                }}
                                .draw-measure-box b {{ color: #166534; }}

                                .draw-actions {{ display: flex; gap: 6px; border-top: 1px solid #f1f5f9; padding-top: 8px; }}
                                .btn-action-sm {{
                                    flex: 1; padding: 5px 8px; font-size: 10.5px; font-weight: 600;
                                    border-radius: 4px; border: 1px solid #cbd5e1; background: #ffffff;
                                    cursor: pointer; display: flex; align-items: center; justify-content: center;
                                    gap: 5px; transition: all 0.15s ease; color: #334155;
                                }}
                                .btn-action-sm svg {{ width: 13px; height: 13px; stroke: currentColor; fill: none; stroke-width: 2; }}
                                .btn-action-sm:hover {{ background: #f8fafc; border-color: #94A3B8; }}
                                .btn-action-sm.danger {{ color: #dc2626; border-color: #fecaca; }}
                                .btn-action-sm.danger:hover {{ background: #fef2f2; border-color: #dc2626; }}

                                .label-marker-corte {{
                                    width: 22px; height: 22px; border-radius: 50%;
                                    color: #ffffff; font-weight: 800; font-size: 11px;
                                    display: flex; align-items: center; justify-content: center;
                                    box-shadow: 0 2px 6px rgba(0,0,0,0.35); border: 2px solid #ffffff;
                                    pointer-events: none; font-family: 'Segoe UI', Arial, sans-serif;
                                }}
                                .label-marker-corte.label-a {{ background: #691C32; }}
                                .label-marker-corte.label-b {{ background: #166534; }}

                                .perfil-docked-panel {{
                                    position: absolute; bottom: 10px; left: 10px; right: 55px; height: 215px;
                                    background: rgba(255, 255, 255, 0.98); backdrop-filter: blur(10px);
                                    border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,0.25);
                                    border: 1.5px solid #cbd5e1; border-top: 3.5px solid #691C32;
                                    z-index: 2500; display: none; flex-direction: column; overflow: hidden;
                                    font-size: 11px; color: #1e293b;
                                }}
                                .docked-perfil-header {{
                                    background: #f8fafc; color: #1e293b; padding: 6px 12px;
                                    font-weight: 700; display: flex; justify-content: space-between; align-items: center;
                                    border-bottom: 1px solid #e2e8f0; font-size: 11.5px;
                                }}
                                .docked-perfil-body {{
                                    flex: 1; display: flex; padding: 8px 12px; gap: 12px; overflow: hidden;
                                }}
                                .perfil-stats-col {{
                                    width: 230px; display: flex; flex-direction: column; justify-content: space-between;
                                    border-right: 1px solid #e2e8f0; padding-right: 10px; font-size: 11px; flex-shrink: 0;
                                }}
                                .perfil-stat-row {{ display: flex; justify-content: space-between; margin-bottom: 2px; }}
                                .perfil-stat-row b {{ color: #691C32; }}
                                .perfil-svg-container {{
                                    flex: 1; position: relative; display: flex; flex-direction: column; min-width: 0;
                                }}
                                .perfil-tooltip {{
                                    position: absolute; top: 4px; right: 8px; background: rgba(30, 41, 59, 0.92);
                                    color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 10.5px;
                                    pointer-events: none; display: none; z-index: 10;
                                }}

                                .maplibregl-ctrl-attrib {{
                                    background-color: rgba(255, 255, 255, 0.85) !important;
                                    padding: 2px 6px !important; border-radius: 3px !important;
                                    font-size: 10.5px !important; color: #333 !important;
                                    box-shadow: 0 1px 3px rgba(0,0,0,0.15) !important;
                                }}
                            </style>
                        </head>
                        <body>
                            <div id="map"></div>
                            
                            <div class="hud-elevation">
                                <div><b>LON:</b> <span id="hud-lon">--</span></div>
                                <div><b>LAT:</b> <span id="hud-lat">--</span></div>
                                <div style="color:#008a3b;"><b>VALOR:</b> <span id="hud-ele">--</span></div>
                            </div>

                            <div id="btn-open-dock" class="btn-open-dock-circle" onclick="toggleDock()" title="Abrir Herramientas Visuales">
                                ☰
                            </div>
                            
                            <div id="dock-panel" class="workbench-dock" style="display: none;">
                                <div class="dock-header">
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <span>🛠️ Capas Visuales</span>
                                    </div>
                                    <button onclick="toggleDock()" style="background:transparent; border:none; color:white; font-size:16px; font-weight:bold; cursor:pointer; line-height:1; padding:2px 5px;" title="Contraer panel">✕</button>
                                </div>
                                <div class="dock-body">
                                    <div class="dock-section">
                                        <label style="font-weight:700; color:#691C32; margin-bottom:2px;">🌍 Mapa Base:</label>
                                        <select id="sel-basemap" class="slider-ctrl" style="padding: 4px; border-radius: 4px; border: 1px solid #ccc; width: 100%; background: #f8fafc;">
                                            <option value="base-light-layer">Gris Claro (Esri)</option>
                                            <option value="base-sat-layer">Satélite (Esri)</option>
                                            <option value="base-topo-layer">Topográfico (Esri)</option>
                                            <option value="base-osm-layer">OpenStreetMap</option>
                                            <option value="base-street-layer">Estándar (Esri)</option>
                                            <option value="base-terrain-layer">Terreno (Esri)</option>
                                            <option value="base-ocean-layer">Océanos (Esri)</option>
                                            <option value="base-dark-layer">Gris Oscuro (Esri)</option>
                                            <option value="base-google-layer">Google Satelital gris 35%</option>
                                        </select>
                                    </div>
                                    <hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;">
                                    <div class="dock-section">
                                        <label style="font-weight:700; color:#691C32; margin-bottom:2px;">🎨 Transparencia Kriging: <span id="val-opac">65%</span></label>
                                        <input type="range" class="slider-ctrl" id="slider-opac" min="0" max="1" step="0.05" value="0.65" oninput="cambiarOpacidadKriging(this.value)">
                                    </div>
                                    <div class="dock-section" id="sec-opac-geo" style="display: none;">
                                        <label style="font-weight:700; color:#691C32; margin-bottom:2px;">🎨 Transparencia Geología: <span id="val-opac-geo">50%</span></label>
                                        <input type="range" class="slider-ctrl" id="slider-opac-geo" min="0" max="1" step="0.05" value="0.50" oninput="cambiarOpacidadGeologia(this.value)">
                                    </div>
                                    <hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;">
                                    <div class="dock-section">
                                        <label><input type="checkbox" id="chk-kriging" checked> 🌊 Superficie Kriging</label>
                                        <label><input type="checkbox" id="chk-iso" checked> 📏 Isolíneas / Isopiezas</label>
                                        <label><input type="checkbox" id="chk-vec" checked> 🧭 Vectores de Flujo</label>
                                        <label><input type="checkbox" id="chk-heat"> 🔥 Mapa de Calor</label>
                                        <label><input type="checkbox" id="chk-pozos" checked> 📍 Red Piezométrica</label>
                                        <label style="display: {'flex' if geom_activa is not None else 'none'};"><input type="checkbox" id="chk-poly" checked> 🛡️ Límite del Acuífero</label>
                                        <label style="display: {'flex' if tiene_repda_tab1 else 'none'};"><input type="checkbox" id="chk-repda"> 🏢 Concesiones REPDA ({n_repda_tab1})</label>
                                        <label style="display: flex;"><input type="checkbox" id="chk-repda-nac"> 🇲🇽 REPDA Nacional MVT (461,914)</label>
                                        <label style="display: {'flex' if hay_manual else 'none'};"><input type="checkbox" id="chk-manual" checked> 🟠 Puntos Manuales</label>
                                        <label style="display: {'flex' if hay_csv else 'none'};"><input type="checkbox" id="chk-csv" checked> 🔵 Puntos CSV</label>
                                        <label style="display: {'flex' if dic_leyenda_rocas else 'none'};"><input type="checkbox" id="chk-geo"> ⛰️ Geología SGM</label>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="legend-panel">
                                {leyenda_html}
                            </div>
                            
                            <div id="btn-open-gradient" class="leaflet-open-gradient-btn" onclick="toggleGradient()" title="Mostrar Gradiente">
                                <div style="width: 14px; height: 14px; background: linear-gradient(to bottom, #eff3ff, #08519c); border: 1px solid #fff; border-radius: 2px;"></div>
                            </div>

                            <div id="gradient-panel-container" class="gradient-docked-panel" style="display: none;">
                                <div class="docked-gradient-header">
                                    <span>Gradiente Piezométrico</span>
                                    <span class="docked-gradient-close" onclick="toggleGradient()" title="Ocultar">&times;</span>
                                </div>
                                <div class="docked-gradient-body">
                                    <b style="color:#691C32; font-size:11px;">{var_titulo_limpio}</b>
                                    <div class="gradient-bar"></div>
                                    <div class="gradient-labels">
                                        <span>{vmin:.1f}</span>
                                        <span>{vmid:.1f}</span>
                                        <span>{vmax:.1f}</span>
                                    </div>
                                </div>
                            </div>

                            <div id="btn-open-draw" class="leaflet-open-draw-btn" onclick="toggleDraw()" title="Herramientas de Dibujo y Medición">
                                <svg viewBox="0 0 24 24" style="width:16px; height:16px; stroke:#691C32; fill:none; stroke-width:2;">
                                    <path d="M12 19l7-7 3 3-7 7-3-3z"/>
                                    <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/>
                                    <circle cx="12" cy="12" r="2"/>
                                </svg>
                            </div>

                            <div id="draw-panel-container" class="draw-docked-panel" style="display: none;">
                                <div class="docked-draw-header">
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <svg viewBox="0 0 24 24" style="width:14px; height:14px; stroke:#691C32; fill:none; stroke-width:2;">
                                            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                                            <polyline points="2 17 12 22 22 17"/>
                                            <polyline points="2 12 12 17 22 12"/>
                                        </svg>
                                        <span>Gabinete Hidrogeológico</span>
                                    </div>
                                    <span class="docked-draw-close" onclick="toggleDraw()" title="Ocultar">&times;</span>
                                </div>
                                <div class="docked-draw-body">
                                    <div class="draw-grid">
                                        <button id="btn-tool-point" class="btn-tool" onclick="activarModoDibujo('point')" title="Sondear cota/profundidad puntual">
                                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/></svg>
                                            Punto
                                        </button>
                                        <button id="btn-tool-line" class="btn-tool" onclick="activarModoDibujo('line_string')" title="Trazar línea o corte transversal A-A'">
                                            <svg viewBox="0 0 24 24"><path d="M4 20L20 4"/><circle cx="4" cy="20" r="2.5"/><circle cx="20" cy="4" r="2.5"/></svg>
                                            Corte A-A'
                                        </button>
                                        <button id="btn-tool-poly" class="btn-tool" onclick="activarModoDibujo('polygon')" title="Calcular superficie geodésica">
                                            <svg viewBox="0 0 24 24"><polygon points="12 2 22 8.5 18 20 6 20 2 8.5"/></svg>
                                            Polígono
                                        </button>
                                        <button id="btn-tool-circle" class="btn-tool" onclick="iniciarDibujoCirculo()" title="Círculo a mano alzada">
                                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><line x1="12" y1="12" x2="18.36" y2="5.64"/></svg>
                                            Círculo Libre
                                        </button>
                                    </div>

                                    <!-- Sección de Buffer Analítico Fijo -->
                                    <div style="margin: 8px 0; border-top: 1px solid #f1f5f9; padding-top: 8px;">
                                        <div style="font-weight: 700; color: #1e293b; font-size: 10.5px; margin-bottom: 5px; display:flex; justify-content:space-between; align-items:center;">
                                            <span>🎯 Radio de Influencia / Buffer</span>
                                        </div>
                                        <div style="display:flex; gap: 4px; align-items: center; margin-bottom: 5px;">
                                            <input type="number" id="input-buffer-radio" value="500" min="20" max="50000" step="50" 
                                                   style="width: 70px; padding: 4px 6px; font-size: 11px; border: 1px solid #cbd5e1; border-radius: 4px;" title="Radio en metros">
                                            <span style="font-size: 11px; color: #64748b;">m</span>
                                            <button id="btn-tool-buffer" class="btn-tool" style="flex:1; padding: 4px 6px; font-size: 10.5px; justify-content: center;" onclick="activarModoBuffer()" title="Clic en mapa o pozo para colocar buffer">
                                                Fijar Buffer
                                            </button>
                                        </div>
                                        <div style="display: flex; gap: 4px;">
                                            <button class="btn-preset" onclick="setBufferRadio(250)">250m</button>
                                            <button class="btn-preset" onclick="setBufferRadio(500)">500m</button>
                                            <button class="btn-preset" onclick="setBufferRadio(1000)">1km</button>
                                            <button class="btn-preset" onclick="setBufferRadio(2000)">2km</button>
                                        </div>
                                    </div>

                                    <!-- Controles de Modo Captura Limpia y Bloqueo -->
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin: 6px 0; background:#f8fafc; padding: 4px 6px; border-radius:4px; border:1px solid #e2e8f0;">
                                        <label style="font-size:10px; color:#475569; display:flex; align-items:center; gap:5px; cursor:pointer;" title="Ocultar popups flotantes para capturas de pantalla 100% limpias">
                                            <input type="checkbox" id="chk-show-badge" checked onchange="toggleMostrarBadges(this.checked)">
                                            <span>Etiqueta en mapa</span>
                                        </label>
                                        <button class="btn-preset" onclick="deseleccionarTodo()" title="Ocultar nodos de edición para fotos de reporte" style="padding:2px 6px; font-size:9.5px;">
                                            👁️ Ocultar Nodos
                                        </button>
                                    </div>

                                    <div id="draw-measure-box" class="draw-measure-box"></div>

                                    <div class="draw-actions">
                                        <button class="btn-action-sm danger" onclick="eliminarDibujoSeleccionado()" title="Borrar selección o todos los trazos">
                                            <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                                            Limpiar
                                        </button>
                                        <button class="btn-action-sm" onclick="descargarDibujosGeoJSON()" title="Descargar trazos en GeoJSON para QGIS/ArcGIS">
                                            <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                                            Exportar
                                        </button>
                                        <button class="btn-action-sm" onclick="document.getElementById('input-import-geojson').click()" title="Cargar archivo GeoJSON al visor">
                                            <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                                            Importar
                                        </button>
                                        <input type="file" id="input-import-geojson" accept=".geojson,.json" style="display:none;" onchange="importarDibujosGeoJSON(event)">
                                    </div>
                                </div>
                            </div>

                            <!-- Panel Inferior de Perfil Geohidrológico de Corte A - A' -->
                            <div id="panel-perfil-corte" class="perfil-docked-panel" style="display: none;">
                                <div class="docked-perfil-header">
                                    <div style="display:flex; align-items:center; gap:8px;">
                                        <svg viewBox="0 0 24 24" style="width:15px; height:15px; stroke:#691C32; fill:none; stroke-width:2.2;">
                                            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                                        </svg>
                                        <span style="font-weight:700; color:#691C32;">Perfil Hidrogeológico de Corte Transversal A - A'</span>
                                        <span id="perfil-header-resumen" style="font-weight:500; color:#64748b; font-size:10.5px; margin-left:6px;"></span>
                                    </div>
                                    <div style="display:flex; align-items:center; gap:8px;">
                                        <button class="btn-action-sm" onclick="descargarCsvPerfil()" title="Exportar datos del transecto a CSV" style="padding:3px 8px; font-size:10.5px;">
                                            <svg viewBox="0 0 24 24" style="width:12px; height:12px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                                            Descargar CSV
                                        </button>
                                        <span class="docked-draw-close" onclick="cerrarPerfilCorte()" title="Cerrar">&times;</span>
                                    </div>
                                </div>
                                <div class="docked-perfil-body">
                                    <div class="perfil-stats-col" id="perfil-stats-box">
                                        <!-- Métricas del Corte -->
                                    </div>
                                    <div class="perfil-svg-container" id="perfil-svg-box">
                                        <div id="perfil-tooltip" class="perfil-tooltip"></div>
                                        <svg id="perfil-svg-chart" style="width:100%; height:100%; overflow:visible;"></svg>
                                    </div>
                                </div>
                            </div>

                            <script>
                                function cambiarOpacidadKriging(valor) {{
                                    if (map.getLayer('kriging-layer')) {{
                                        map.setPaintProperty('kriging-layer', 'raster-opacity', parseFloat(valor));
                                        document.getElementById('val-opac').innerText = Math.round(valor * 100) + '%';
                                    }}
                                }}

                                function cambiarOpacidadGeologia(valor) {{
                                    if (map.getLayer('geo-fill')) {{
                                        map.setPaintProperty('geo-fill', 'fill-opacity', parseFloat(valor));
                                        document.getElementById('val-opac-geo').innerText = Math.round(valor * 100) + '%';
                                    }}
                                }}

                                const iconExpandSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
                                const iconCompressSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;

                                let protocol = new pmtiles.Protocol();
                                maplibregl.addProtocol("pmtiles", protocol.tile);

                                const map = new maplibregl.Map({{
                                    container: 'map',
                                    style: {{
                                        'version': 8,
                                        'sources': {{
                                            'base-light': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri' }},
                                            'base-sat': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, Maxar' }},
                                            'base-topo': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, USGS' }},
                                            'base-osm': {{ 'type': 'raster', 'tiles': ['https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png'], 'tileSize': 256, 'attribution': '© OpenStreetMap' }},
                                            'base-street': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri' }},
                                            'base-terrain': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, USGS' }},
                                            'base-ocean': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, GEBCO' }},
                                            'base-dark': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri' }},
                                            'base-google': {{ 'type': 'raster', 'tiles': ['https://mt1.google.com/vt/lyrs=s&x={{x}}&y={{y}}&z={{z}}'], 'tileSize': 256, 'attribution': 'Google Satellite' }}
                                        }},
                                        'layers': [
                                            {{ 'id': 'base-light-layer', 'type': 'raster', 'source': 'base-light', 'layout': {{'visibility': 'visible'}} }},
                                            {{ 'id': 'base-sat-layer', 'type': 'raster', 'source': 'base-sat', 'layout': {{'visibility': 'none'}} }},
                                            {{ 'id': 'base-topo-layer', 'type': 'raster', 'source': 'base-topo', 'layout': {{'visibility': 'none'}} }},
                                            {{ 'id': 'base-osm-layer', 'type': 'raster', 'source': 'base-osm', 'layout': {{'visibility': 'none'}} }},
                                            {{ 'id': 'base-street-layer', 'type': 'raster', 'source': 'base-street', 'layout': {{'visibility': 'none'}} }},
                                            {{ 'id': 'base-terrain-layer', 'type': 'raster', 'source': 'base-terrain', 'layout': {{'visibility': 'none'}} }},
                                            {{ 'id': 'base-ocean-layer', 'type': 'raster', 'source': 'base-ocean', 'layout': {{'visibility': 'none'}} }},
                                            {{ 'id': 'base-dark-layer', 'type': 'raster', 'source': 'base-dark', 'layout': {{'visibility': 'none'}} }},
                                            {{ 'id': 'base-google-layer', 'type': 'raster', 'source': 'base-google', 'layout': {{'visibility': 'none'}}, 'paint': {{'raster-opacity': 0.35, 'raster-saturation': -1.0}} }}
                                        ]
                                    }},
                                    center: [{centro_lon}, {centro_lat}],
                                    zoom: 9.5,
                                    attributionControl: false,
                                    preserveDrawingBuffer: true
                                }});
                                
                                class FullscreenCustomControl {{
                                    onAdd(mapInstance) {{
                                        this._map = mapInstance;
                                        this._container = document.createElement('div');
                                        this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group';
                                        
                                        const btn = document.createElement('button');
                                        btn.type = 'button';
                                        btn.innerHTML = iconExpandSVG;
                                        btn.title = 'Pantalla Completa';
                                        btn.style.width = '30px';
                                        btn.style.height = '30px';
                                        btn.style.display = 'flex';
                                        btn.style.alignItems = 'center';
                                        btn.style.justifyContent = 'center';
                                        btn.style.background = '#ffffff';
                                        btn.style.cursor = 'pointer';
                                        btn.style.border = 'none';
                                        
                                        btn.onclick = () => {{
                                            if (!document.fullscreenElement) {{
                                                document.documentElement.requestFullscreen().catch(err => {{}});
                                            }} else {{
                                                if (document.exitFullscreen) document.exitFullscreen();
                                            }}
                                        }};
                                        
                                        document.addEventListener('fullscreenchange', () => {{
                                            btn.innerHTML = document.fullscreenElement ? iconCompressSVG : iconExpandSVG;
                                            btn.title = document.fullscreenElement ? 'Salir de Pantalla Completa' : 'Pantalla Completa';
                                            setTimeout(() => {{ mapInstance.resize(); }}, 200);
                                        }});
                                        
                                        this._container.appendChild(btn);
                                        return this._container;
                                    }}
                                    onRemove() {{
                                        this._container.parentNode.removeChild(this._container);
                                        this._map = undefined;
                                    }}
                                }}
                                map.addControl(new FullscreenCustomControl(), 'top-right');
                                map.addControl(new maplibregl.NavigationControl(), 'top-right');
                                map.addControl(new maplibregl.AttributionControl({{ compact: false }}), 'bottom-right');
                                map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-right');

                                const draw = new MapboxDraw({{
                                    displayControlsDefault: false,
                                    controls: {{}},
                                    userProperties: true,
                                    styles: [
                                        {{
                                            'id': 'gl-draw-line', 'type': 'line',
                                            'filter': ['all', ['==', '$type', 'LineString'], ['!=', 'mode', 'static']],
                                            'layout': {{ 'line-cap': 'round', 'line-join': 'round' }},
                                            'paint': {{ 'line-color': '#9f2241', 'line-width': 3, 'line-dasharray': [0.2, 2] }}
                                        }},
                                        {{
                                            'id': 'gl-draw-polygon-fill', 'type': 'fill',
                                            'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                                            'paint': {{ 'fill-color': '#285c4d', 'fill-opacity': 0.25 }}
                                        }},
                                        {{
                                            'id': 'gl-draw-polygon-stroke', 'type': 'line',
                                            'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                                            'layout': {{ 'line-cap': 'round', 'line-join': 'round' }},
                                            'paint': {{ 'line-color': '#285c4d', 'line-width': 2.5 }}
                                        }},
                                        {{
                                            'id': 'gl-draw-point', 'type': 'circle',
                                            'filter': ['all', ['==', '$type', 'Point'], ['!=', 'meta', 'vertex'], ['!=', 'meta', 'midpoint'], ['!=', 'mode', 'static']],
                                            'paint': {{ 'circle-radius': 5, 'circle-color': '#ffffff', 'circle-stroke-width': 2, 'circle-stroke-color': '#691C32' }}
                                        }},
                                        {{
                                            'id': 'gl-draw-vertex-inactive', 'type': 'circle',
                                            'filter': ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                                            'paint': {{ 'circle-radius': 5, 'circle-color': '#ffffff', 'circle-stroke-width': 2, 'circle-stroke-color': '#691C32' }}
                                        }},
                                        {{
                                            'id': 'gl-draw-vertex-active', 'type': 'circle',
                                            'filter': ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                                            'paint': {{ 'circle-radius': 7, 'circle-color': '#691C32', 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' }}
                                        }},
                                        {{
                                            'id': 'gl-draw-midpoint', 'type': 'circle',
                                            'filter': ['all', ['==', 'meta', 'midpoint'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                                            'paint': {{ 'circle-radius': 4.5, 'circle-color': '#DDC9A3', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#691C32' }}
                                        }}
                                    ]
                                }});
                                map.addControl(draw);

                                let dockAbierto = true;
                                function aplicarEstadoVisualDock() {{
                                    const dock = document.getElementById('dock-panel');
                                    const btnOpen = document.getElementById('btn-open-dock');
                                    if (dock && btnOpen) {{
                                        dock.style.display = dockAbierto ? 'block' : 'none';
                                        btnOpen.style.display = dockAbierto ? 'none' : 'flex';
                                    }}
                                }}
                                function toggleDock() {{
                                    dockAbierto = !dockAbierto;
                                    aplicarEstadoVisualDock();
                                }}
                                aplicarEstadoVisualDock();
                                
                                let gradientAbierto = false;
                                function toggleGradient() {{
                                    gradientAbierto = !gradientAbierto;
                                    const panel = document.getElementById('gradient-panel-container');
                                    const btn = document.getElementById('btn-open-gradient');
                                    if (gradientAbierto) {{
                                        panel.style.display = 'block';
                                        btn.style.display = 'none';
                                        if (drawAbierto) toggleDraw();
                                    }} else {{
                                        panel.style.display = 'none';
                                        btn.style.display = 'flex';
                                    }}
                                }}

                                let drawAbierto = false;
                                function toggleDraw() {{
                                    drawAbierto = !drawAbierto;
                                    const panel = document.getElementById('draw-panel-container');
                                    const btn = document.getElementById('btn-open-draw');
                                    if (drawAbierto) {{
                                        panel.style.display = 'block';
                                        btn.style.display = 'none';
                                        if (gradientAbierto) toggleGradient();
                                    }} else {{
                                        panel.style.display = 'none';
                                        btn.style.display = 'flex';
                                        detenerModoCirculo();
                                        detenerModoBuffer();
                                        limpiarHerramientasActivas();
                                    }}
                                }}

                                function activarModoDibujo(mode) {{
                                    detenerModoCirculo();
                                    detenerModoBuffer();
                                    limpiarHerramientasActivas();
                                    map.getCanvas().style.cursor = 'crosshair'; 
                                    if (mode === 'point') {{
                                        document.getElementById('btn-tool-point').classList.add('active');
                                        draw.changeMode('draw_point');
                                    }} else if (mode === 'line_string') {{
                                        document.getElementById('btn-tool-line').classList.add('active');
                                        draw.changeMode('draw_line_string');
                                    }} else if (mode === 'polygon') {{
                                        document.getElementById('btn-tool-poly').classList.add('active');
                                        draw.changeMode('draw_polygon');
                                    }}
                                }}

                                function limpiarHerramientasActivas() {{
                                    ['btn-tool-point', 'btn-tool-line', 'btn-tool-poly', 'btn-tool-circle', 'btn-tool-buffer'].forEach(id => {{
                                        const el = document.getElementById(id);
                                        if (el) el.classList.remove('active');
                                    }});
                                    map.getCanvas().style.cursor = ''; 
                                }}

                                function eliminarDibujoSeleccionado() {{
                                    const sel = draw.getSelectedIds();
                                    if (sel && sel.length > 0) {{
                                        draw.delete(sel);
                                    }} else {{
                                        draw.deleteAll();
                                    }}
                                    document.getElementById('draw-measure-box').style.display = 'none';
                                    limpiarRotulosLinea();
                                    if (popupActivo) popupActivo.remove();
                                    if (perfilAbierto) cerrarPerfilCorte();
                                }}

                                function descargarDibujosGeoJSON() {{
                                    const data = draw.getAll();
                                    if (!data || !data.features || data.features.length === 0) {{
                                        alert("No hay geometrías trazadas en el mapa para exportar.");
                                        return;
                                    }}
                                    const blob = new Blob([JSON.stringify(data, null, 2)], {{ type: 'application/geo+json' }});
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = 'mediciones_piezometria.geojson';
                                    a.click();
                                    URL.revokeObjectURL(url);
                                }}

                                function importarDibujosGeoJSON(e) {{
                                    const file = e.target.files[0];
                                    if (!file) return;
                                    const reader = new FileReader();
                                    reader.onload = function(evt) {{
                                        try {{
                                            const data = JSON.parse(evt.target.result);
                                            if (data.type === "FeatureCollection" && data.features) {{
                                                data.features.forEach(f => draw.add(f));
                                                const bbox = turf.bbox(data);
                                                map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], {{ padding: 40 }});
                                                alert(`Se importaron ${{data.features.length}} geometrías exitosamente al mapa.`);
                                            }} else if (data.type === "Feature") {{
                                                draw.add(data);
                                                const bbox = turf.bbox(data);
                                                map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], {{ padding: 40 }});
                                                alert("Se importó 1 geometría exitosamente.");
                                            }} else {{
                                                alert("El archivo no contiene un formato GeoJSON válido.");
                                            }}
                                        }} catch(err) {{
                                            alert("Error al parsear el archivo GeoJSON: " + err.message);
                                        }}
                                    }};
                                    reader.readAsText(file);
                                    e.target.value = "";
                                }}

                                let modoCirculoActivo = false;
                                let centroCirculo = null;

                                function iniciarDibujoCirculo() {{
                                    detenerModoBuffer();
                                    limpiarHerramientasActivas();
                                    draw.changeMode('simple_select');
                                    modoCirculoActivo = true;
                                    centroCirculo = null;
                                    document.getElementById('btn-tool-circle').classList.add('active');
                                    map.getCanvas().style.cursor = 'crosshair';
                                    const box = document.getElementById('draw-measure-box');
                                    box.style.display = 'block';
                                    box.innerHTML = '<b>Paso 1:</b> Clic en el mapa para fijar el <b>CENTRO</b>.';
                                }}

                                function detenerModoCirculo() {{
                                    modoCirculoActivo = false;
                                    centroCirculo = null;
                                    map.getCanvas().style.cursor = '';
                                    const btn = document.getElementById('btn-tool-circle');
                                    if (btn) btn.classList.remove('active');
                                    if (map.getSource('temp-circle-src')) {{
                                        map.getSource('temp-circle-src').setData({{ "type": "FeatureCollection", "features": [] }});
                                    }}
                                }}

                                let modoBufferActivo = false;
                                let radioBufferMetros = 500;

                                function setBufferRadio(m) {{
                                    document.getElementById('input-buffer-radio').value = m;
                                    radioBufferMetros = m;
                                    activarModoBuffer();
                                }}

                                function activarModoBuffer() {{
                                    detenerModoCirculo();
                                    limpiarHerramientasActivas();
                                    draw.changeMode('simple_select');
                                    modoBufferActivo = true;
                                    const inputRadio = document.getElementById('input-buffer-radio');
                                    radioBufferMetros = parseFloat(inputRadio.value) || 500;
                                    document.getElementById('btn-tool-buffer').classList.add('active');
                                    map.getCanvas().style.cursor = 'crosshair';
                                    const box = document.getElementById('draw-measure-box');
                                    box.style.display = 'block';
                                    box.innerHTML = `<b>🎯 Buffer Fijo (${{radioBufferMetros}} m):</b> Clic en el mapa o sobre un pozo para fijar el radio de influencia.`;
                                }}

                                function detenerModoBuffer() {{
                                    modoBufferActivo = false;
                                    map.getCanvas().style.cursor = '';
                                    const btn = document.getElementById('btn-tool-buffer');
                                    if (btn) btn.classList.remove('active');
                                }}

                                const selBasemap = document.getElementById('sel-basemap');
                                if (selBasemap) {{
                                    selBasemap.addEventListener('change', (e) => {{
                                        const selected = e.target.value;
                                        const basemaps = ['base-light-layer', 'base-sat-layer', 'base-topo-layer', 'base-osm-layer', 'base-street-layer', 'base-terrain-layer', 'base-ocean-layer', 'base-dark-layer', 'base-google-layer'];
                                        
                                        basemaps.forEach(id => {{
                                            if (map.getLayer(id)) {{
                                                map.setLayoutProperty(id, 'visibility', id === selected ? 'visible' : 'none');
                                            }}
                                        }});
                                    }});
                                }}

                                const z_data = {z_data_json};
                                const bounds = {bounds_json};
                                const min_y = bounds[0][0], min_x = bounds[0][1];
                                const max_y = bounds[1][0], max_x = bounds[1][1];
                                const rows = z_data.length, cols = z_data[0].length;
                                
                                let popupActivo = null;

                                map.on('load', () => {{
                                    map.addSource('temp-circle-src', {{
                                        type: 'geojson',
                                        data: {{ "type": "FeatureCollection", "features": [] }}
                                    }});
                                    map.addLayer({{
                                        id: 'temp-circle-fill', type: 'fill', source: 'temp-circle-src',
                                        paint: {{ 'fill-color': '#008a3b', 'fill-opacity': 0.2 }}
                                    }});
                                    map.addLayer({{
                                        id: 'temp-circle-line', type: 'line', source: 'temp-circle-src',
                                        paint: {{ 'line-color': '#008a3b', 'line-width': 2, 'line-dasharray': [2, 2] }}
                                    }});

                                    const polyTab1Data = {poly_tab1_geojson_str};
                                    if (polyTab1Data) {{
                                        map.addSource('poly-tab1-src', {{ type: 'geojson', data: polyTab1Data }});
                                        map.addLayer({{
                                            id: 'poly-tab1-fill', type: 'fill', source: 'poly-tab1-src',
                                            paint: {{ 'fill-color': '#000000', 'fill-opacity': 0.02 }}
                                        }});
                                        map.addLayer({{
                                            id: 'poly-tab1-line', type: 'line', source: 'poly-tab1-src',
                                            paint: {{ 'line-color': '#691C32', 'line-width': 2.0, 'line-dasharray': [3, 1.5] }}
                                        }});
                                    }}

                                    const geoData = {geojson_geo_str};
                                    if (geoData.features) {{
                                        map.addSource('geo-src', {{ type: 'geojson', data: geoData }});
                                        map.addLayer({{
                                            id: 'geo-fill', type: 'fill', source: 'geo-src',
                                            paint: {{ 'fill-color': ['get', 'COLOR_HEX'], 'fill-opacity': 0.5 }},
                                            layout: {{ 'visibility': 'none' }}
                                        }});
                                        map.addLayer({{
                                            id: 'geo-line', type: 'line', source: 'geo-src',
                                            paint: {{ 'line-color': '#555', 'line-width': 0.5, 'line-opacity': 0.6 }},
                                            layout: {{ 'visibility': 'none' }}
                                        }});
                                    }}

                                    map.addSource('kriging-src', {{
                                        type: 'image', url: 'data:image/png;base64,{img_krig_b64}', coordinates: {img_coords_json}
                                    }});
                                    map.addLayer({{
                                        id: 'kriging-layer', type: 'raster', source: 'kriging-src',
                                        paint: {{ 'raster-opacity': 0.65, 'raster-resampling': 'linear' }}
                                    }});

                                    map.addSource('iso-src', {{
                                        type: 'image', url: 'data:image/png;base64,{img_iso_b64}', coordinates: {img_coords_json}
                                    }});
                                    map.addLayer({{ id: 'iso-layer', type: 'raster', source: 'iso-src', paint: {{ 'raster-opacity': 0.95 }} }});

                                    map.addSource('vec-src', {{
                                        type: 'image', url: 'data:image/png;base64,{img_flujo_b64}', coordinates: {img_coords_json}
                                    }});
                                    map.addLayer({{ id: 'vec-layer', type: 'raster', source: 'vec-src', paint: {{ 'raster-opacity': 0.9 }} }});

                                    map.addSource('pozos-src', {{ type: 'geojson', data: {geojson_pozos_str} }});
                                    map.addLayer({{
                                        id: 'heat-layer', type: 'heatmap', source: 'pozos-src',
                                        paint: {{
                                            'heatmap-weight': ['interpolate', ['linear'], ['get', 'Valor'], {vmin}, 0, {vmax}, 1],
                                            'heatmap-intensity': 1.5,
                                            'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(40,92,77,0)', 0.2, '#285c4d', 0.6, '#b38e5d', 1.0, '#9f2241'],
                                            'heatmap-radius': 30, 'heatmap-opacity': 0.6
                                        }},
                                        layout: {{ 'visibility': 'none' }}
                                    }});

                                    map.addLayer({{
                                        id: 'pozos-layer', type: 'circle', source: 'pozos-src',
                                        paint: {{
                                            'circle-radius': 5,
                                            'circle-color': ['get', 'Color'],
                                            'circle-stroke-width': 1,
                                            'circle-stroke-color': '#ffffff'
                                        }}
                                    }});

                                    map.addSource('add-src', {{ type: 'geojson', data: {geojson_add_str} }});
                                    map.addLayer({{
                                        id: 'add-layer-manual', type: 'circle', source: 'add-src',
                                        filter: ['==', ['get', 'fuente'], 'manual'],
                                        paint: {{ 'circle-radius': 6, 'circle-color': '#d35400', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#ffffff' }}
                                    }});
                                    map.addLayer({{
                                        id: 'add-layer-csv', type: 'circle', source: 'add-src',
                                        filter: ['==', ['get', 'fuente'], 'csv'],
                                        paint: {{ 'circle-radius': 6, 'circle-color': '#2980b9', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#ffffff' }}
                                    }});

                                    if ({ 'true' if tiene_repda_tab1 else 'false' }) {{
                                        map.addSource('repda-src', {{ type: 'geojson', data: {geojson_repda_tab1_str} }});
                                        map.addLayer({{
                                            id: 'repda-halo-layer', type: 'circle', source: 'repda-src',
                                            paint: {{ 'circle-radius': ['+', ['get', 'radio_px'], 1.5], 'circle-color': '#ffffff', 'circle-opacity': 0.95 }},
                                            layout: {{ 'visibility': 'none' }}
                                        }});
                                        map.addLayer({{
                                            id: 'repda-layer', type: 'circle', source: 'repda-src',
                                            paint: {{
                                                'circle-radius': ['get', 'radio_px'],
                                                'circle-color': ['get', 'color'],
                                                'circle-opacity': 0.88,
                                                'circle-stroke-width': 1.2,
                                                'circle-stroke-color': '#0f172a'
                                            }},
                                            layout: {{ 'visibility': 'none' }}
                                        }});

                                        map.on('click', 'repda-layer', (e) => {{
                                            if (isDrawingMode()) return;
                                            if (popupActivo) popupActivo.remove();
                                            const p = e.features[0].properties;
                                            const volFmt = p.volumen_m3 !== undefined ? Number(p.volumen_m3).toLocaleString('es-MX') : '--';
                                            const volHm3 = p.volumen_hm3 !== undefined ? Number(p.volumen_hm3).toFixed(3) : '--';
                                            const html = `
                                                <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; min-width:210px; line-height:1.45;">
                                                    <div style="font-weight:700; color:#691C32; font-size:12px; margin-bottom:4px; border-bottom:1.5px solid #691C32; padding-bottom:3px; display:flex; justify-content:space-between; align-items:center;">
                                                        <span>🏢 Concesión REPDA</span>
                                                        <span style="font-size:9.5px; background:${{p.color}}; color:#fff; padding:1px 5px; border-radius:3px; font-weight:600;">${{p.uso}}</span>
                                                    </div>
                                                    <div><b>Titular:</b> ${{p.titular}}</div>
                                                    <div><b>Folio Oficial:</b> <span style="font-family:monospace; color:#334155;">${{p.folio}}</span></div>
                                                    ${{p.expediente ? `<div><b>Expediente:</b> <span style="font-family:monospace; color:#475569;">${{p.expediente}}</span></div>` : ''}}
                                                    ${{p.fecha ? `<div><b>Fecha Registro:</b> ${{p.fecha}}</div>` : ''}}
                                                    <div><b>Volumen:</b> <b style="color:#1e293b;">${{volFmt}} m³/año</b> (${{volHm3}} hm³/año)</div>
                                                    ${{p.profundidad_m > 0 ? `<div><b>Profundidad Obra:</b> ${{p.profundidad_m}} m</div>` : ''}}
                                                    <div style="font-size:9.5px; color:#64748b; margin-top:4px; text-align:right;">
                                                        Coordenadas: ${{Number(p.lat).toFixed(5)}}° N, ${{Number(p.lon).toFixed(5)}}° W
                                                    </div>
                                                </div>
                                            `;
                                            popupActivo = new maplibregl.Popup().setLngLat(e.lngLat).setHTML(html).addTo(map);
                                        }});
                                    }}

                                    // REPDA Nacional Completo MVT (PMTiles 461,914 concesiones)
                                    let pmtilesUrlTab1 = '{url_pmtiles_srv_tab1}';
                                    if (!pmtilesUrlTab1.startsWith('http://') && !pmtilesUrlTab1.startsWith('https://')) {{
                                        let baseOrigin = (window.location && window.location.origin && window.location.origin !== 'null') ? window.location.origin : '';
                                        if (!baseOrigin && document.referrer) {{
                                            try {{ baseOrigin = new URL(document.referrer).origin; }} catch (err) {{}}
                                        }}
                                        pmtilesUrlTab1 = (baseOrigin || '') + pmtilesUrlTab1;
                                    }}
                                    map.addSource('repda-nacional-src', {{
                                        type: 'vector',
                                        url: 'pmtiles://' + pmtilesUrlTab1,
                                        minzoom: 4,
                                        maxzoom: 8
                                    }});
                                    map.addLayer({{
                                        id: 'repda-nacional-layer',
                                        type: 'circle',
                                        source: 'repda-nacional-src',
                                        'source-layer': 'repda',
                                        maxzoom: { '11' if tiene_repda_tab1 else '24' },
                                        layout: {{ 'visibility': 'none' }},
                                        paint: {{
                                            'circle-radius': [
                                                'interpolate', ['linear'], ['zoom'],
                                                4, 1.2,
                                                7, 2.5,
                                                10, 4.5,
                                                14, 7.5
                                            ],
                                            'circle-color': [
                                                'match', ['get', 'u'],
                                                'AGRICOLA', '#16a34a',
                                                'PUBLICO URBANO', '#2563eb',
                                                'DOMESTICO', '#0284c7',
                                                'INDUSTRIAL', '#dc2626',
                                                'SERVICIOS', '#9333ea',
                                                'PECUARIO', '#ca8a04',
                                                'DIFERENTES USOS', '#0d9488',
                                                'ACUACULTURA', '#06b6d4',
                                                'AGROINDUSTRIAL', '#65a30d',
                                                'COMERCIO', '#ea580c',
                                                'ENERGIA ELECTRICA', '#eab308',
                                                /* default */ '#475569'
                                            ],
                                            'circle-opacity': 0.85,
                                            'circle-stroke-width': [
                                                'interpolate', ['linear'], ['zoom'],
                                                4, 0,
                                                8, 0.4,
                                                11, 1.0
                                            ],
                                            'circle-stroke-color': '#ffffff'
                                        }}
                                    }});

                                    map.on('click', 'repda-nacional-layer', (e) => {{
                                        if (isDrawingMode()) return;
                                        if (popupActivo) popupActivo.remove();
                                        const p = e.features[0].properties;
                                        const volM3 = p.v ? Number(p.v).toLocaleString('es-MX') : '--';
                                        const volHm3 = p.v ? (Number(p.v) / 1e6).toFixed(3) : '--';
                                        const latFmt = p.la !== undefined ? Number(p.la).toFixed(5) : e.lngLat.lat.toFixed(5);
                                        const lonFmt = p.lo !== undefined ? Number(p.lo).toFixed(5) : e.lngLat.lng.toFixed(5);
                                        const html = `
                                            <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; min-width:220px; line-height:1.45;">
                                                <div style="font-weight:700; color:#166534; font-size:12px; margin-bottom:4px; border-bottom:1.5px solid #166534; padding-bottom:3px; display:flex; justify-content:space-between; align-items:center;">
                                                    <span>🇲🇽 Concesión REPDA Nacional</span>
                                                    <span style="font-size:10px; background:#f1f5f9; color:#475569; padding:1px 5px; border-radius:4px;">${{p.f || '--'}}</span>
                                                </div>
                                                <div style="margin-bottom:3px;"><b>Titular:</b> <span style="color:#0f172a; font-weight:600;">${{p.t || '--'}}</span></div>
                                                ${{p.e ? `<div style="margin-bottom:2px;"><b>Expediente:</b> ${{p.e}}</div>` : ''}}
                                                <div style="margin-bottom:2px;"><b>Uso:</b> <span style="background:#f0fdf4; color:#166534; font-weight:700; padding:1px 5px; border-radius:3px; border:1px solid #bbf7d0;">${{p.u || '--'}}</span></div>
                                                <div style="margin-bottom:2px;"><b>Volumen Anual:</b> <b>${{volM3}}</b> m³/año (${{volHm3}} hm³/año)</div>
                                                <div style="font-size:9.5px; color:#64748b; margin-top:4px;">Coordenadas: ${{latFmt}}° N, ${{lonFmt}}° W</div>
                                            </div>
                                        `;
                                        popupActivo = new maplibregl.Popup({{ className: 'gis-badge-popup' }}).setLngLat(e.lngLat).setHTML(html).addTo(map);
                                    }});

                                    map.on('mouseenter', 'repda-nacional-layer', () => {{ if (!isDrawingMode()) map.getCanvas().style.cursor = 'pointer'; }});
                                    map.on('mouseleave', 'repda-nacional-layer', () => {{ if (!isDrawingMode()) map.getCanvas().style.cursor = ''; }});

                                    const polyBounds = {poly_bounds_str};
                                    if (polyBounds) {{
                                        map.fitBounds([[polyBounds[0], polyBounds[1]], [polyBounds[2], polyBounds[3]]], {{ padding: 40 }});
                                    }}
                                }});

                                const legContenedor = document.querySelector('.legend-panel');
                                if (legContenedor) {{
                                    legContenedor.addEventListener('keydown', function(e) {{ e.stopPropagation(); }});
                                    legContenedor.addEventListener('keyup', function(e) {{ e.stopPropagation(); }});
                                    legContenedor.addEventListener('keypress', function(e) {{ e.stopPropagation(); }});
                                }}

                                map.on('mousemove', (e) => {{
                                    document.getElementById('hud-lon').innerText = e.lngLat.lng.toFixed(5) + '°';
                                    document.getElementById('hud-lat').innerText = e.lngLat.lat.toFixed(5) + '°';
                                    
                                    const lat = e.lngLat.lat, lng = e.lngLat.lng;
                                    if (lat >= min_y && lat <= max_y && lng >= min_x && lng <= max_x) {{
                                        let r = Math.floor(((lat - min_y) / (max_y - min_y)) * (rows - 1));
                                        let c = Math.floor(((lng - min_x) / (max_x - min_x)) * (cols - 1));
                                        r = Math.max(0, Math.min(rows - 1, r));
                                        c = Math.max(0, Math.min(cols - 1, c));
                                        const val = z_data[r][c];
                                        if (val !== null) {{
                                            document.getElementById('hud-ele').innerText = val.toFixed(2);
                                        }} else {{
                                            document.getElementById('hud-ele').innerText = '--';
                                        }}
                                    }} else {{
                                        document.getElementById('hud-ele').innerText = '--';
                                    }}

                                    if (!modoCirculoActivo || !centroCirculo) return;
                                    const actual = [e.lngLat.lng, e.lngLat.lat];
                                    const radioKm = turf.distance(centroCirculo, actual, {{ units: 'kilometers' }});
                                    if (radioKm > 0.0005) {{
                                        const tempCircle = turf.circle(centroCirculo, radioKm, {{ steps: 48, units: 'kilometers' }});
                                        if (map.getSource('temp-circle-src')) {{
                                            map.getSource('temp-circle-src').setData(tempCircle);
                                        }}
                                        const radioM = (radioKm * 1000).toFixed(1);
                                        const areaHa = (turf.area(tempCircle) / 10000).toFixed(2);
                                        document.getElementById('draw-measure-box').innerHTML = 
                                            `<b>Radio:</b> ${{radioM}} m (${{radioKm.toFixed(3)}} km)<br>` +
                                            `<b>Área de Influencia:</b> ${{areaHa}} ha<br>` +
                                            `<span style="color:#64748B; font-size:10px;">Clic para confirmar circunferencia</span>`;
                                    }}
                                }});

                                map.on('click', (e) => {{
                                    if (modoBufferActivo) {{
                                        const coords = [e.lngLat.lng, e.lngLat.lat];
                                        const radioKm = radioBufferMetros / 1000.0;
                                        const circlePoly = turf.circle(coords, radioKm, {{ steps: 64, units: 'kilometers' }});
                                        const areaHa = (turf.area(circlePoly) / 10000).toFixed(2);
                                        circlePoly.properties = {{
                                            esCirculo: true,
                                            radioM: radioBufferMetros,
                                            areaHa: areaHa
                                        }};
                                        draw.add(circlePoly);
                                        detenerModoBuffer();
                                        actualizarMedicionCompleta(circlePoly, true);
                                        return;
                                    }}

                                    if (!modoCirculoActivo) return;
                                    const coords = [e.lngLat.lng, e.lngLat.lat];
                                    if (!centroCirculo) {{
                                        centroCirculo = coords;
                                        const box = document.getElementById('draw-measure-box');
                                        box.innerHTML = '<b>Paso 2:</b> Mueve el cursor y haz un <b>segundo clic</b> para consolidar el radio.';
                                    }} else {{
                                        const radioKm = turf.distance(centroCirculo, coords, {{ units: 'kilometers' }});
                                        if (radioKm > 0.001) {{
                                            const circlePoly = turf.circle(centroCirculo, radioKm, {{ steps: 64, units: 'kilometers' }});
                                            const radioM = Math.round(radioKm * 1000);
                                            const areaHa = (turf.area(circlePoly) / 10000).toFixed(2);
                                            circlePoly.properties = {{
                                                esCirculo: true,
                                                radioM: radioM,
                                                areaHa: areaHa
                                            }};
                                            draw.add(circlePoly);
                                            actualizarMedicionCompleta(circlePoly, true);
                                        }}
                                        detenerModoCirculo();
                                    }}
                                }});

                                let lineaActualFeat = null;
                                let perfilAbierto = false;
                                let perfilActualData = null;

                                function calcularPerfilLinea(feat) {{
                                    if (!feat || !feat.geometry || feat.geometry.type !== 'LineString') return null;
                                    const coords = feat.geometry.coordinates;
                                    if (!coords || coords.length < 2) return null;
                                    
                                    const kmTotal = turf.length(feat, {{ units: 'kilometers' }});
                                    if (kmTotal <= 0) return null;

                                    const numPuntos = Math.min(100, Math.max(30, Math.round(kmTotal * 15)));
                                    const stepKm = kmTotal / (numPuntos - 1);
                                    const puntos = [];
                                    let hMin = Infinity, hMax = -Infinity;
                                    let hInicio = null, hFin = null;

                                    for (let i = 0; i < numPuntos; i++) {{
                                        const dKm = i * stepKm;
                                        const pt = turf.along(feat, dKm, {{ units: 'kilometers' }});
                                        const lng = pt.geometry.coordinates[0];
                                        const lat = pt.geometry.coordinates[1];

                                        let valZ = null;
                                        if (lat >= min_y && lat <= max_y && lng >= min_x && lng <= max_x) {{
                                            let r = Math.floor(((lat - min_y) / (max_y - min_y)) * (rows - 1));
                                            let c = Math.floor(((lng - min_x) / (max_x - min_x)) * (cols - 1));
                                            r = Math.max(0, Math.min(rows - 1, r));
                                            c = Math.max(0, Math.min(cols - 1, c));
                                            valZ = z_data[r][c];
                                        }}

                                        if (valZ !== null && !isNaN(valZ)) {{
                                            if (valZ < hMin) hMin = valZ;
                                            if (valZ > hMax) hMax = valZ;
                                            if (hInicio === null) hInicio = valZ;
                                            hFin = valZ;
                                        }}

                                        puntos.push({{
                                            dist_m: dKm * 1000,
                                            dist_km: dKm,
                                            lng: lng,
                                            lat: lat,
                                            z: valZ
                                        }});
                                    }}

                                    const coordInicio = coords[0];
                                    const coordFin = coords[coords.length - 1];
                                    const rumbo = turf.bearing(coordInicio, coordFin);
                                    const azimut = (rumbo + 360) % 360;

                                    let cuadrante = "N";
                                    if (azimut >= 337.5 || azimut < 22.5) cuadrante = "Norte (N)";
                                    else if (azimut >= 22.5 && azimut < 67.5) cuadrante = "Noreste (NE)";
                                    else if (azimut >= 67.5 && azimut < 112.5) cuadrante = "Este (E)";
                                    else if (azimut >= 112.5 && azimut < 157.5) cuadrante = "Sureste (SE)";
                                    else if (azimut >= 157.5 && azimut < 202.5) cuadrante = "Sur (S)";
                                    else if (azimut >= 202.5 && azimut < 247.5) cuadrante = "Suroeste (SW)";
                                    else if (azimut >= 247.5 && azimut < 292.5) cuadrante = "Oeste (W)";
                                    else cuadrante = "Noroeste (NW)";

                                    const deltaH = (hInicio !== null && hFin !== null) ? (hFin - hInicio) : 0;
                                    const gradienteM_Km = (kmTotal > 0 && hInicio !== null && hFin !== null) ? Math.abs(deltaH) / kmTotal : 0;

                                    let direccionFlujo = "Indeterminada";
                                    if (hInicio !== null && hFin !== null) {{
                                        if (hInicio > hFin + 0.05) direccionFlujo = "De A hacia A'";
                                        else if (hFin > hInicio + 0.05) direccionFlujo = "De A' hacia A";
                                        else direccionFlujo = "Gradiente uniforme / flujo laminar nulo";
                                    }}

                                    return {{
                                        kmTotal: kmTotal,
                                        mTotal: kmTotal * 1000,
                                        azimut: azimut,
                                        cuadrante: cuadrante,
                                        hInicio: hInicio,
                                        hFin: hFin,
                                        deltaH: deltaH,
                                        gradienteM_Km: gradienteM_Km,
                                        direccionFlujo: direccionFlujo,
                                        hMin: (hMin === Infinity) ? null : hMin,
                                        hMax: (hMax === -Infinity) ? null : hMax,
                                        puntos: puntos
                                    }};
                                }}

                                function renderizarPerfilSvg(p) {{
                                    const svg = document.getElementById('perfil-svg-chart');
                                    if (!svg || !p || !p.puntos || p.puntos.length < 2) return;
                                    
                                    perfilActualData = p;
                                    const box = svg.getBoundingClientRect();
                                    const w = box.width || 560;
                                    const h = box.height || 140;

                                    const padL = 50, padR = 25, padT = 15, padB = 25;
                                    const plotW = Math.max(10, w - padL - padR);
                                    const plotH = Math.max(10, h - padT - padB);

                                    let minZ = p.hMin !== null ? p.hMin : 0;
                                    let maxZ = p.hMax !== null ? p.hMax : 100;
                                    let spanZ = maxZ - minZ;
                                    if (spanZ <= 0.01) spanZ = 1.0;
                                    
                                    minZ -= spanZ * 0.08;
                                    maxZ += spanZ * 0.08;
                                    spanZ = maxZ - minZ;

                                    let dLine = "";
                                    let primerX = null, primerY = null, ultimoX = null;

                                    p.puntos.forEach((pt, idx) => {{
                                        const x = padL + (pt.dist_m / p.mTotal) * plotW;
                                        let y = padT + plotH / 2;
                                        if (pt.z !== null && !isNaN(pt.z)) {{
                                            y = padT + (1 - (pt.z - minZ) / spanZ) * plotH;
                                        }}
                                        if (idx === 0) {{
                                            dLine += `M ${{x.toFixed(1)}} ${{y.toFixed(1)}}`;
                                            primerX = x;
                                            primerY = y;
                                        }} else {{
                                            dLine += ` L ${{x.toFixed(1)}} ${{y.toFixed(1)}}`;
                                        }}
                                        ultimoX = x;
                                    }});

                                    const yBase = padT + plotH;
                                    const dArea = `${{dLine}} L ${{ultimoX.toFixed(1)}} ${{yBase}} L ${{primerX.toFixed(1)}} ${{yBase}} Z`;

                                    const midZ = (p.hMin !== null && p.hMax !== null) ? ((p.hMin + p.hMax) / 2) : (minZ + spanZ/2);
                                    const yMid = padT + (1 - (midZ - minZ) / spanZ) * plotH;
                                    const yMinLine = padT + (1 - (p.hMin - minZ) / spanZ) * plotH;
                                    const yMaxLine = padT + (1 - (p.hMax - minZ) / spanZ) * plotH;

                                    let svgHtml = `
                                        <defs>
                                            <linearGradient id="perfilGrad" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="0%" stop-color="#285c4d" stop-opacity="0.4" />
                                                <stop offset="100%" stop-color="#285c4d" stop-opacity="0.05" />
                                            </linearGradient>
                                        </defs>
                                        <line x1="${{padL}}" y1="${{yMaxLine.toFixed(1)}}" x2="${{padL + plotW}}" y2="${{yMaxLine.toFixed(1)}}" stroke="#cbd5e1" stroke-dasharray="2,2"/>
                                        <text x="${{padL - 6}}" y="${{(yMaxLine + 3).toFixed(1)}}" font-size="9" fill="#64748b" text-anchor="end">${{p.hMax !== null ? p.hMax.toFixed(1) : ''}}</text>
                                        
                                        <line x1="${{padL}}" y1="${{yMid.toFixed(1)}}" x2="${{padL + plotW}}" y2="${{yMid.toFixed(1)}}" stroke="#e2e8f0" stroke-dasharray="2,2"/>
                                        <text x="${{padL - 6}}" y="${{(yMid + 3).toFixed(1)}}" font-size="9" fill="#64748b" text-anchor="end">${{midZ.toFixed(1)}}</text>
                                        
                                        <line x1="${{padL}}" y1="${{yMinLine.toFixed(1)}}" x2="${{padL + plotW}}" y2="${{yMinLine.toFixed(1)}}" stroke="#cbd5e1" stroke-dasharray="2,2"/>
                                        <text x="${{padL - 6}}" y="${{(yMinLine + 3).toFixed(1)}}" font-size="9" fill="#64748b" text-anchor="end">${{p.hMin !== null ? p.hMin.toFixed(1) : ''}}</text>
                                        
                                        <line x1="${{padL}}" y1="${{yBase}}" x2="${{padL + plotW}}" y2="${{yBase}}" stroke="#94a3b8" stroke-width="1.5"/>
                                        <text x="${{padL}}" y="${{yBase + 13}}" font-size="9" fill="#475569" text-anchor="start">0 m (A)</text>
                                        <text x="${{padL + plotW/2}}" y="${{yBase + 13}}" font-size="9" fill="#475569" text-anchor="middle">${{(p.mTotal/2).toFixed(0)}} m</text>
                                        <text x="${{padL + plotW}}" y="${{yBase + 13}}" font-size="9" fill="#475569" text-anchor="end">${{p.mTotal.toFixed(0)}} m (A')</text>

                                        <path d="${{dArea}}" fill="url(#perfilGrad)" />
                                        <path d="${{dLine}}" fill="none" stroke="#691C32" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>

                                        <circle cx="${{primerX.toFixed(1)}}" cy="${{primerY.toFixed(1)}}" r="4.5" fill="#9f2241" stroke="#fff" stroke-width="1.5"/>
                                        <circle cx="${{ultimoX.toFixed(1)}}" cy="${{(padT + (1 - (p.hFin - minZ) / spanZ) * plotH).toFixed(1)}}" r="4.5" fill="#285c4d" stroke="#fff" stroke-width="1.5"/>

                                        <line id="svg-hover-line" x1="0" y1="${{padT}}" x2="0" y2="${{yBase}}" stroke="#691C32" stroke-width="1.2" stroke-dasharray="3,2" style="display:none;"/>
                                        <circle id="svg-hover-circle" cx="0" cy="0" r="5" fill="#691C32" stroke="#fff" stroke-width="2" style="display:none;"/>
                                    `;

                                    svg.innerHTML = svgHtml;
                                    
                                    svg.onmousemove = (e) => {{
                                        const rect = svg.getBoundingClientRect();
                                        const mouseX = e.clientX - rect.left;
                                        if (mouseX < padL || mouseX > padL + plotW) {{
                                            document.getElementById('svg-hover-line').style.display = 'none';
                                            document.getElementById('svg-hover-circle').style.display = 'none';
                                            document.getElementById('perfil-tooltip').style.display = 'none';
                                            return;
                                        }}
                                        const ratio = (mouseX - padL) / plotW;
                                        const targetDist = ratio * p.mTotal;
                                        
                                        let ptCercano = p.puntos[0];
                                        let diffMin = Math.abs(p.puntos[0].dist_m - targetDist);
                                        for (let i = 1; i < p.puntos.length; i++) {{
                                            const diff = Math.abs(p.puntos[i].dist_m - targetDist);
                                            if (diff < diffMin) {{
                                                diffMin = diff;
                                                ptCercano = p.puntos[i];
                                            }}
                                        }}

                                        const hoverX = padL + (ptCercano.dist_m / p.mTotal) * plotW;
                                        const hoverY = ptCercano.z !== null ? (padT + (1 - (ptCercano.z - minZ) / spanZ) * plotH) : (padT + plotH/2);

                                        const hLine = document.getElementById('svg-hover-line');
                                        const hCirc = document.getElementById('svg-hover-circle');
                                        const tip = document.getElementById('perfil-tooltip');

                                        hLine.setAttribute('x1', hoverX);
                                        hLine.setAttribute('x2', hoverX);
                                        hLine.style.display = 'block';

                                        hCirc.setAttribute('cx', hoverX);
                                        hCirc.setAttribute('cy', hoverY);
                                        hCirc.style.display = 'block';

                                        tip.style.display = 'block';
                                        tip.innerHTML = `<b>Distancia:</b> ${{ptCercano.dist_m.toFixed(0)}} m | <b>{var_titulo_limpio}:</b> ${{ptCercano.z !== null ? ptCercano.z.toFixed(2) : '--'}}`;
                                    }};

                                    svg.onmouseleave = () => {{
                                        const hLine = document.getElementById('svg-hover-line');
                                        const hCirc = document.getElementById('svg-hover-circle');
                                        const tip = document.getElementById('perfil-tooltip');
                                        if (hLine) hLine.style.display = 'none';
                                        if (hCirc) hCirc.style.display = 'none';
                                        if (tip) tip.style.display = 'none';
                                    }};
                                }}

                                function abrirPerfilCorte(feat) {{
                                    const targetFeat = feat || lineaActualFeat;
                                    if (!targetFeat) {{
                                        alert("Trazar o seleccionar primero una línea en el mapa.");
                                        return;
                                    }}
                                    const p = calcularPerfilLinea(targetFeat);
                                    if (!p) return;

                                    perfilAbierto = true;
                                    const panel = document.getElementById('panel-perfil-corte');
                                    panel.style.display = 'flex';

                                    document.getElementById('perfil-header-resumen').innerText = 
                                        `Longitud: ${{p.mTotal.toFixed(0)}} m | Azimut: ${{p.azimut.toFixed(1)}}° (${{p.cuadrante}}) | Gradiente: ${{p.gradienteM_Km.toFixed(3)}} m/km`;

                                    const statsBox = document.getElementById('perfil-stats-box');
                                    const tDarcyVal = {t_darcy};
                                    let qDarcyHtml = '';
                                    if (tDarcyVal > 0) {{
                                        const qUnit = (tDarcyVal * Math.abs(p.gradienteM_M)).toFixed(3);
                                        qDarcyHtml = `<div class="perfil-stat-row" style="color:#0284c7;"><span>Caudal Darcy (q):</span> <b>${{qUnit}} m³/día/m</b></div>`;
                                    }}
                                    statsBox.innerHTML = `
                                        <div class="perfil-stat-row"><span>Longitud A-A':</span> <b>${{p.mTotal.toFixed(0)}} m (${{p.kmTotal.toFixed(2)}} km)</b></div>
                                        <div class="perfil-stat-row"><span>Azimut Geográfico:</span> <b>${{p.azimut.toFixed(1)}}° (${{p.cuadrante}})</b></div>
                                        <div class="perfil-stat-row"><span>Cota en A:</span> <b>${{p.hInicio !== null ? p.hInicio.toFixed(2) + ' m' : '--'}}</b></div>
                                        <div class="perfil-stat-row"><span>Cota en A':</span> <b>${{p.hFin !== null ? p.hFin.toFixed(2) + ' m' : '--'}}</b></div>
                                        <div class="perfil-stat-row"><span>Desnivel (Δh):</span> <b>${{p.deltaH !== null ? p.deltaH.toFixed(2) + ' m' : '--'}}</b></div>
                                        <div class="perfil-stat-row"><span>Gradiente Hidráulico:</span> <b>${{p.gradienteM_Km.toFixed(3)}} m/km</b></div>
                                        <div class="perfil-stat-row" style="border-top:1px solid #e2e8f0; padding-top:4px;">
                                            <span>Flujo Subterráneo:</span> <b style="color:#166534;">${{p.direccionFlujo}}</b>
                                        </div>
                                        ${{qDarcyHtml}}
                                    `;

                                    setTimeout(() => {{
                                        renderizarPerfilSvg(p);
                                    }}, 60);
                                }}

                                function cerrarPerfilCorte() {{
                                    perfilAbierto = false;
                                    document.getElementById('panel-perfil-corte').style.display = 'none';
                                }}

                                function descargarCsvPerfil() {{
                                    if (!perfilActualData || !perfilActualData.puntos) {{
                                        alert("No hay datos de perfil para exportar.");
                                        return;
                                    }}
                                    let csv = "distancia_m,distancia_km,latitud,longitud,{var_titulo_limpio}\\n";
                                    perfilActualData.puntos.forEach(p => {{
                                        csv += `${{p.dist_m.toFixed(1)}},${{p.dist_km.toFixed(3)}},${{p.lat.toFixed(6)}},${{p.lng.toFixed(6)}},${{p.z !== null ? p.z.toFixed(2) : ""}}\\n`;
                                    }});
                                    const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
                                    const url = URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = 'perfil_hidrogeologico_A_A.csv';
                                    a.click();
                                    URL.revokeObjectURL(url);
                                }}

                                window.addEventListener('resize', () => {{
                                    if (perfilAbierto && perfilActualData) {{
                                        renderizarPerfilSvg(perfilActualData);
                                    }}
                                }});

                                function obtenerInfoMedicion(feat) {{
                                    if (!feat || !feat.geometry) return null;
                                    const tipo = feat.geometry.type;
                                    const props = feat.properties || {{}};

                                    if (tipo === 'Point') {{
                                        const c = feat.geometry.coordinates;
                                        const lng = c[0], lat = c[1];
                                        let valZ = null;
                                        if (lat >= min_y && lat <= max_y && lng >= min_x && lng <= max_x) {{
                                            let r = Math.floor(((lat - min_y) / (max_y - min_y)) * (rows - 1));
                                            let col = Math.floor(((lng - min_x) / (max_x - min_x)) * (cols - 1));
                                            r = Math.max(0, Math.min(rows - 1, r));
                                            col = Math.max(0, Math.min(cols - 1, col));
                                            valZ = z_data[r][col];
                                        }}
                                        const cotaTxt = (valZ !== null && !isNaN(valZ)) ? `${{valZ.toFixed(2)}}` : 'S/D';
                                        
                                        return {{
                                            coords: c,
                                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📍 Punto de Sondeo</div>` +
                                                   `<div style="font-size:10.5px; color:#334155;">` +
                                                   `<b>{var_titulo_limpio}:</b> <span style="color:#691C32; font-weight:700;">${{cotaTxt}}</span><br>` +
                                                   `<span style="color:#64748B; font-size:9.5px;">${{lat.toFixed(4)}}° N, ${{lng.toFixed(4)}}° W</span>` +
                                                   `</div>`,
                                            panel: `<b>📍 Sondeo Piezométrico</b><br>` +
                                                   `<b>Coordenadas:</b> ${{lat.toFixed(5)}}° N, ${{lng.toFixed(5)}}° W<br>` +
                                                   `<b>{var_titulo_limpio}:</b> <span style="color:#691C32; font-weight:700;">${{cotaTxt}}</span>`
                                        }};
                                    }}

                                    if (tipo === 'LineString') {{
                                        lineaActualFeat = feat;
                                        const km = turf.length(feat, {{ units: 'kilometers' }});
                                        const p = calcularPerfilLinea(feat);
                                        const distFormato = km < 1.0 ? `${{(km * 1000).toFixed(0)}} m` : `${{km.toFixed(2)}} km (${{(km * 1000).toFixed(0)}} m)`;
                                        const azimutTxt = p ? `${{p.azimut.toFixed(0)}}° ${{p.cuadrante}}` : '--';
                                        const gradTxt = p ? `${{p.gradienteM_Km.toFixed(2)}} m/km` : '--';
                                        
                                        const coordsPts = feat.geometry.coordinates;
                                        const midCoord = coordsPts[Math.floor(coordsPts.length / 2)];

                                        return {{
                                            coords: midCoord,
                                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📏 Transecto A - A'</div>` +
                                                   `<div style="font-size:10.5px; color:#334155;">` +
                                                   `<b>Distancia:</b> ${{distFormato}}<br>` +
                                                   `<b>Rumbo:</b> ${{azimutTxt}} · <b>Grad:</b> ${{gradTxt}}` +
                                                   `</div>`,
                                            panel: `<b>📏 Transecto de Corte A - A'</b><br>` +
                                                   `<b>Longitud Total:</b> ${{distFormato}}<br>` +
                                                   `<b>Azimut Geográfico:</b> ${{p ? p.azimut.toFixed(1) + '° (' + p.cuadrante + ')' : '--'}}<br>` +
                                                   `<b>Cota en A:</b> ${{p && p.hInicio !== null ? p.hInicio.toFixed(2) + ' m' : '--'}}<br>` +
                                                   `<b>Cota en A':</b> ${{p && p.hFin !== null ? p.hFin.toFixed(2) + ' m' : '--'}}<br>` +
                                                   `<b>Gradiente Hidráulico:</b> ${{p ? p.gradienteM_Km.toFixed(3) + ' m/km' : '--'}}<br>` +
                                                   `<b>Sentido del Flujo:</b> <span style="color:#166534; font-weight:600;">${{p ? p.direccionFlujo : '--'}}</span>` +
                                                   `<button class="btn-tool" style="width:100%; margin-top:8px; background:#691C32; color:#fff; justify-content:center; border:none; padding:6px 8px; cursor:pointer;" onclick="abrirPerfilCorte()">📐 Ver Perfil de Corte A - A'</button>`
                                        }};
                                    }}

                                    if (props.esCirculo || props.radioM) {{
                                        const radioM = props.radioM || 500;
                                        const areaHa = props.areaHa || (turf.area(feat) / 10000).toFixed(2);
                                        const radioTxt = radioM >= 1000 ? `${{(radioM / 1000).toFixed(2)}} km` : `${{radioM}} m`;
                                        return {{
                                            coords: turf.centroid(feat).geometry.coordinates,
                                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">🎯 Radio de Influencia</div>` +
                                                   `<div style="font-size:10.5px; color:#334155;">` +
                                                   `<b>Radio:</b> ${{radioTxt}}<br>` +
                                                   `<b>Superficie:</b> ${{areaHa}} ha` +
                                                   `</div>`,
                                            panel: `<b>🎯 Radio de Influencia / Buffer</b><br>` +
                                                   `<b>Radio Fijo:</b> ${{radioTxt}}<br>` +
                                                   `<b>Área de Influencia:</b> ${{areaHa}} ha<br>` +
                                                   `<b>Perímetro:</b> ${{(2 * Math.PI * radioM / 1000).toFixed(2)}} km`
                                        }};
                                    }}

                                    if (tipo === 'Polygon') {{
                                        const m2 = turf.area(feat);
                                        const ha = (m2 / 10000).toFixed(2);
                                        const kmPerim = turf.length(turf.polygonToLine(feat), {{ units: 'kilometers' }}).toFixed(2);
                                        return {{
                                            coords: turf.centroid(feat).geometry.coordinates,
                                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📐 Área Delimitada</div>` +
                                                   `<div style="font-size:10.5px; color:#334155;">` +
                                                   `<b>Superficie:</b> ${{ha}} ha<br>` +
                                                   `<b>Perímetro:</b> ${{kmPerim}} km` +
                                                   `</div>`,
                                            panel: `<b>📐 Polígono de Medición</b><br>` +
                                                   `<b>Superficie:</b> ${{ha}} ha (${{Math.round(m2).toLocaleString()}} m²)<br>` +
                                                   `<b>Perímetro:</b> ${{kmPerim}} km`
                                        }};
                                    }}
                                    return null;
                                }}

                                let markerA = null;
                                let markerB = null;

                                function actualizarRotulosLinea(feat) {{
                                    limpiarRotulosLinea();
                                    if (!feat || !feat.geometry || feat.geometry.type !== 'LineString') return;
                                    const coords = feat.geometry.coordinates;
                                    if (!coords || coords.length < 2) return;
                                    
                                    const elA = document.createElement('div');
                                    elA.className = 'label-marker-corte label-a';
                                    elA.innerText = 'A';
                                    elA.title = 'Extremo Inicial A del corte';
                                    
                                    const elB = document.createElement('div');
                                    elB.className = 'label-marker-corte label-b';
                                    elB.innerText = "A'";
                                    elB.title = "Extremo Final A' del corte";
                                    
                                    markerA = new maplibregl.Marker({{ element: elA }}).setLngLat(coords[0]).addTo(map);
                                    markerB = new maplibregl.Marker({{ element: elB }}).setLngLat(coords[coords.length - 1]).addTo(map);
                                }}

                                function limpiarRotulosLinea() {{
                                    if (markerA) {{ markerA.remove(); markerA = null; }}
                                    if (markerB) {{ markerB.remove(); markerB = null; }}
                                }}

                                function toggleMostrarBadges(mostrar) {{
                                    if (!mostrar && popupActivo) {{
                                        popupActivo.remove();
                                    }} else if (mostrar) {{
                                        const feats = draw.getAll().features;
                                        if (feats && feats.length > 0) {{
                                            actualizarMedicionCompleta(feats[feats.length - 1], true);
                                        }}
                                    }}
                                }}

                                function deseleccionarTodo() {{
                                    draw.changeMode('simple_select', {{ featureIds: [] }});
                                    if (popupActivo) popupActivo.remove();
                                }}

                                window.addEventListener('keydown', (e) => {{
                                    if (e.key === 'Escape') {{
                                        const m = draw.getMode();
                                        if (m.startsWith('draw_') || modoCirculoActivo || modoBufferActivo) {{
                                            draw.trash();
                                            draw.changeMode('simple_select');
                                            detenerModoCirculo();
                                            detenerModoBuffer();
                                            limpiarHerramientasActivas();
                                            const b = document.getElementById('draw-measure-box');
                                            if (b) b.style.display = 'none';
                                            limpiarRotulosLinea();
                                        }}
                                    }}
                                }});

                                function actualizarMedicionCompleta(feat, mostrarBadge) {{
                                    if (!feat) return;
                                    const info = obtenerInfoMedicion(feat);
                                    if (!info) return;

                                    const box = document.getElementById('draw-measure-box');
                                    if (box) {{
                                        box.style.display = 'block';
                                        box.innerHTML = info.panel;
                                    }}

                                    if (feat.geometry.type === 'LineString') {{
                                        actualizarRotulosLinea(feat);
                                    }} else {{
                                        limpiarRotulosLinea();
                                    }}

                                    const chkBadge = document.getElementById('chk-show-badge');
                                    const permitirBadge = chkBadge ? chkBadge.checked : true;

                                    if (mostrarBadge && permitirBadge) {{
                                        if (popupActivo) popupActivo.remove();
                                        popupActivo = new maplibregl.Popup({{ closeOnClick: true, offset: 12, className: 'gis-badge-popup' }})
                                            .setLngLat(info.coords)
                                            .setHTML(info.badge)
                                            .addTo(map);
                                    }} else if (!permitirBadge && popupActivo) {{
                                        popupActivo.remove();
                                    }}
                                }}

                                map.on('draw.render', () => {{
                                    const mode = draw.getMode();
                                    const box = document.getElementById('draw-measure-box');
                                    if (mode === 'draw_line_string' && box) {{
                                        box.style.display = 'block';
                                        box.innerHTML = `<b>📏 Trazando línea...</b><br><span style="color:#64748B; font-size:10px;">Clic para fijar puntos. <b>Doble clic</b> para finalizar.</span>`;
                                    }} else if (mode === 'draw_polygon' && box) {{
                                        box.style.display = 'block';
                                        box.innerHTML = `<b>📐 Trazando polígono...</b><br><span style="color:#64748B; font-size:10px;">Clic para fijar esquinas. <b>Doble clic</b> para cerrar.</span>`;
                                    }}
                                }});

                                map.on('draw.create', (e) => {{
                                    if (e.features && e.features.length > 0) {{
                                        const feat = e.features[0];
                                        actualizarMedicionCompleta(feat, true);
                                    }}
                                    limpiarHerramientasActivas();
                                }});

                                map.on('draw.update', (e) => {{
                                    if (e.features && e.features.length > 0) {{
                                        const feat = e.features[0];
                                        if (feat.geometry.type === 'LineString' && perfilAbierto) {{
                                            abrirPerfilCorte(feat);
                                        }}
                                        actualizarMedicionCompleta(feat, true);
                                    }}
                                }});

                                map.on('draw.selectionchange', (e) => {{
                                    if (e.features && e.features.length > 0) {{
                                        const feat = e.features[0];
                                        actualizarMedicionCompleta(feat, true);
                                    }} else {{
                                        if (popupActivo) {{
                                            popupActivo.remove();
                                            popupActivo = null;
                                        }}
                                    }}
                                }});

                                function isDrawingMode() {{
                                    try {{
                                        return draw.getMode() !== 'simple_select' || modoCirculoActivo || modoBufferActivo;
                                    }} catch(e) {{ return false; }}
                                }}

                                map.on('click', 'pozos-layer', (e) => {{
                                    if (isDrawingMode()) return;
                                    if (popupActivo) popupActivo.remove();
                                    const p = e.features[0].properties;
                                    popupActivo = new maplibregl.Popup().setLngLat(e.lngLat)
                                        .setHTML(`<div style="font-family:'Segoe UI',sans-serif; font-size:12px; min-width:160px;">
                                                    <h4 style="margin:0 0 5px 0; color:#691C32; border-bottom:1px solid #ddd; padding-bottom:3px;">📍 Pozo: ${{p.Pozo}}</h4>
                                                    <b>${{p.Variable}}:</b> ${{p.Valor}}<br>
                                                    <b>Año Objetivo:</b> ${{p.Año}}<br>
                                                    <b>Origen:</b> ${{p.Tipo || 'Medición Real'}}<br>
                                                    <b>Año Medido:</b> ${{p.Año_Medido || p.Año}}
                                                  </div>`)
                                        .addTo(map);
                                }});

                                map.on('click', 'add-layer-manual', (e) => showAddPopup(e));
                                map.on('click', 'add-layer-csv', (e) => showAddPopup(e));

                                function showAddPopup(e) {{
                                    if (isDrawingMode()) return;
                                    if (popupActivo) popupActivo.remove();
                                    const p = e.features[0].properties;
                                    let html = `<div style="font-family:'Segoe UI',sans-serif; font-size:12px; min-width:150px;"><h4 style="margin:0 0 5px 0; color:#691C32; border-bottom:1px solid #ddd; padding-bottom:3px;">${{p.nombre}}</h4><b>Tipo:</b> ${{p.tipo}}<br>`;
                                    let attrs = p.atributos;
                                    if (typeof attrs === 'string') {{
                                        try {{ attrs = JSON.parse(attrs); }} catch(err) {{ attrs = {{}}; }}
                                    }}
                                    for (const [k, v] of Object.entries(attrs || {{}})) {{ html += `<b>${{k}}:</b> ${{v}}<br>`; }}
                                    html += `</div>`;
                                    popupActivo = new maplibregl.Popup().setLngLat(e.lngLat).setHTML(html).addTo(map);
                                }}
                                
                                map.on('click', 'geo-fill', (e) => {{
                                    if (isDrawingMode()) return;
                                    const puntosClickeados = map.queryRenderedFeatures(e.point, {{
                                        layers: ['pozos-layer', 'add-layer-manual', 'add-layer-csv']
                                    }});
                                    if (puntosClickeados.length > 0) return;

                                    if (popupActivo) popupActivo.remove();
                                    const p = e.features[0].properties;
                                    const formacion = (p.FORMACION && p.FORMACION !== 'null' && p.FORMACION !== 'NINGUNO') ? p.FORMACION : 'Formación No Asignada';
                                    const claveSgm = p["{col_sel_geo}"] || p.ETIQUETA_LITO || 'S/C';
                                    const litologia = p.LITOLOGIA || 'Indiferenciada';
                                    const roca = p.ROCA || 'Sedimentaria';
                                    const colorHex = p.COLOR_HEX || '#B0BEC5';
                                    
                                    let edadGeo = p.PERIODO || '';
                                    if (p.EDINICIO || p.EDFINAL) {{
                                        const ini = p.EDINICIO || '';
                                        const fin = p.EDFINAL || '';
                                        edadGeo += (ini === fin || !fin) ? ` (${{ini}})` : ` (${{ini}} - ${{fin}})`;
                                    }}
                                    if (!edadGeo.trim()) edadGeo = p.ERA || 'S/D';

                                    let html = `
                                        <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; line-height:1.5; min-width:200px;">
                                            <div style="display:flex; align-items:center; justify-content:space-between; border-bottom:1.5px solid #E2E8F0; padding-bottom:4px; margin-bottom:6px;">
                                                <div style="display:flex; align-items:center; gap:6px;">
                                                    <span style="width:13px; height:13px; background:${{colorHex}}; border-radius:3px; border:1px solid #475569; display:inline-block;"></span>
                                                    <h4 style="margin:0; color:#691C32; font-size:13px; font-weight:700;">${{formacion}}</h4>
                                                </div>
                                                <span style="background:#F1F5F9; border:1px solid #CBD5E1; color:#334155; font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:3px;">${{claveSgm}}</span>
                                            </div>
                                            <b>Litología:</b> <span style="color:#0f172a; font-weight:600;">${{litologia}}</span><br>
                                            <b>Tipo de Roca:</b> ${{roca}}<br>
                                            <b>Edad Geológica:</b> ${{edadGeo}}<br>
                                            <span style="color:#64748B; font-size:10px;">Coords: ${{e.lngLat.lat.toFixed(4)}}°, ${{e.lngLat.lng.toFixed(4)}}°</span>
                                        </div>
                                    `;
                                    popupActivo = new maplibregl.Popup().setLngLat(e.lngLat).setHTML(html).addTo(map);
                                }});

                                const capasInteractivas = ['pozos-layer', 'add-layer-manual', 'add-layer-csv', 'geo-fill', 'repda-layer'];
                                capasInteractivas.forEach(capa => {{
                                    map.on('mouseenter', capa, () => {{
                                        if (!isDrawingMode()) map.getCanvas().style.cursor = 'pointer';
                                    }});
                                    map.on('mouseleave', capa, () => {{
                                        if (!isDrawingMode()) map.getCanvas().style.cursor = '';
                                    }});
                                }});

                                const toggleLayer = (chkId, layerIds, legId = null) => {{
                                    const chk = document.getElementById(chkId);
                                    if (chk) {{
                                        chk.addEventListener('change', (e) => {{
                                            const vis = e.target.checked ? 'visible' : 'none';
                                            layerIds.forEach(id => {{ if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis); }});
                                            if (legId) {{
                                                const leg = document.getElementById(legId);
                                                if (leg) leg.style.display = e.target.checked ? 'block' : 'none';
                                            }}
                                        }});
                                    }}
                                }};

                                toggleLayer('chk-kriging', ['kriging-layer']);
                                toggleLayer('chk-iso', ['iso-layer']);
                                toggleLayer('chk-vec', ['vec-layer']);
                                toggleLayer('chk-heat', ['heat-layer']);
                                toggleLayer('chk-pozos', ['pozos-layer'], 'leg-pozos');
                                toggleLayer('chk-poly', ['poly-tab1-fill', 'poly-tab1-line']);
                                toggleLayer('chk-repda', ['repda-halo-layer', 'repda-layer'], 'leg-repda');
                                toggleLayer('chk-repda-nac', ['repda-nacional-layer'], 'leg-repda-nac');
                                toggleLayer('chk-manual', ['add-layer-manual'], 'leg-manual');
                                toggleLayer('chk-csv', ['add-layer-csv'], 'leg-csv');
                                toggleLayer('chk-geo', ['geo-fill', 'geo-line'], 'leg-geo');

                                const chkGeo = document.getElementById('chk-geo');
                                if (chkGeo) {{
                                    chkGeo.addEventListener('change', (e) => {{
                                        const secOpacGeo = document.getElementById('sec-opac-geo');
                                        if (secOpacGeo) {{
                                            secOpacGeo.style.display = e.target.checked ? 'block' : 'none';
                                        }}
                                    }});
                                }}

                                let isDraggingPopup = false;
                                window.addEventListener('mousemove', (e) => {{
                                    if (!isDraggingPopup || !popupActivo) return;
                                    const rect = map.getCanvasContainer().getBoundingClientRect();
                                    const point = [e.clientX - rect.left, e.clientY - rect.top];
                                    popupActivo.setLngLat(map.unproject(point));
                                }});

                                window.addEventListener('mouseup', () => {{
                                    if (isDraggingPopup) {{
                                        isDraggingPopup = false;
                                        map.dragPan.enable();
                                    }}
                                }});

                                const observerPopups = new MutationObserver((mutations) => {{
                                    mutations.forEach((mutation) => {{
                                        mutation.addedNodes.forEach((node) => {{
                                            if (node.classList && node.classList.contains('maplibregl-popup') && node.classList.contains('transparent-popup')) {{
                                                if (popupActivo && !node.dataset.draggable) {{
                                                    node.dataset.draggable = "true";
                                                    node.style.cursor = 'move';
                                                    node.addEventListener('mousedown', (e) => {{
                                                        isDraggingPopup = true;
                                                        map.dragPan.disable();
                                                        e.stopPropagation();
                                                    }});
                                                }}
                                            }}
                                        }});
                                    }});
                                }});
                                observerPopups.observe(document.body, {{ childList: true, subtree: true }});

                            </script>
                        </body>
                        </html>
                        """
                        components.html(html_maplibre, height=720)

                        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                        with st.container(border=True):
                            st.markdown("<p style='font-weight:700; color:#691C32; margin-bottom:8px; font-size:13px;'>💾 EXPORTACIÓN DE RESULTADOS SIG Y MODELACIÓN (CERO-RERUN)</p>", unsafe_allow_html=True)
                            c_d1, c_d2, c_d3, c_d4, c_d5 = st.columns(5)

                            btn_tif = generar_enlace_descarga(
                                geotiff_bytes, f"kriging_{clave_actual}_{var_real}_{anio_sel}.tif", 
                                "image/tiff", "🗺️ GeoTIFF Ráster (.tif)"
                            )
                            c_d1.markdown(btn_tif, unsafe_allow_html=True)

                            if shp_krig_zip:
                                btn_shp_malla = generar_enlace_descarga(
                                    shp_krig_zip, f"kriging_malla_{clave_actual}_{anio_sel}.zip", 
                                    "application/zip", "📦 Shapefile Malla (.zip)"
                                )
                                c_d2.markdown(btn_shp_malla, unsafe_allow_html=True)
                            else:
                                btn_json_malla = generar_enlace_descarga(
                                    geojson_krig, f"kriging_malla_{clave_actual}_{anio_sel}.geojson",
                                    "application/geo+json", "📄 GeoJSON Malla"
                                )
                                c_d2.markdown(btn_json_malla, unsafe_allow_html=True)

                            if shp_iso_zip:
                                btn_shp_iso = generar_enlace_descarga(
                                    shp_iso_zip, f"isopiezas_{clave_actual}_{anio_sel}.zip", 
                                    "application/zip", "📏 Shapefile Isopiezas (.zip)"
                                )
                                c_d3.markdown(btn_shp_iso, unsafe_allow_html=True)
                            else:
                                btn_json_iso = generar_enlace_descarga(
                                    geojson_iso, f"isopiezas_{clave_actual}_{anio_sel}.geojson", 
                                    "application/geo+json", "📄 GeoJSON Isopiezas"
                                )
                                c_d3.markdown(btn_json_iso, unsafe_allow_html=True)

                            if shp_flujo_zip:
                                btn_shp_flujo = generar_enlace_descarga(
                                    shp_flujo_zip, f"vectores_flujo_{clave_actual}_{anio_sel}.zip", 
                                    "application/zip", "🧭 Shapefile Vectores (.zip)"
                                )
                                c_d4.markdown(btn_shp_flujo, unsafe_allow_html=True)
                            else:
                                btn_json_flujo = generar_enlace_descarga(
                                    geojson_flujo, f"vectores_flujo_{clave_actual}_{anio_sel}.geojson", 
                                    "application/geo+json", "📄 GeoJSON Vectores"
                                )
                                c_d4.markdown(btn_json_flujo, unsafe_allow_html=True)

                            kmz_flujo_bytes = generar_kmz_dinamica_flujo(
                                clave_actual, nombre_actual, anio_sel, var_real,
                                bounds, img_kriging, geojson_iso, geojson_flujo,
                                df_ultimo, delim_geom=geom_activa, props_kriging=props_kriging,
                                marcadores_adicionales=st.session_state.get("marcadores_piezo", []),
                                geojson_geo=geojson_geo_str,
                                geojson_repda=geojson_repda_tab1_str if tiene_repda_tab1 else None
                            )
                            btn_kmz_flujo = generar_enlace_descarga(
                                kmz_flujo_bytes, f"dinamica_flujo_{clave_actual}_{anio_sel}.kmz",
                                "application/vnd.google-earth.kmz", "🌐 Paquete KMZ (Google Earth)"
                            )
                            c_d5.markdown(btn_kmz_flujo, unsafe_allow_html=True)
                        
                        if dic_leyenda_rocas:
                            st.markdown(f"""
                                <div style='background-color:#F8FAFC; border-left:4px solid #691C32; padding:10px 14px; border-radius:4px; margin-top:10px; margin-bottom:8px;'>
                                    <span style='font-size:12.5px; font-weight:bold; color:#691C32;'>SIMBOLOGÍA LITOLÓGICA OFICIAL (SGM - INEGI)</span>
                                    <span style='font-size:11px; color:#64748B; margin-left:14px;'><b>Origen de Reglas:</b> {ORIGEN_SGM_GLOBAL} | <b>Campo:</b> <code>{col_sel_geo}</code></span>
                                </div>
                            """, unsafe_allow_html=True)

                            items_html = [
                                f"<div style='display:inline-flex; align-items:center; margin-right:18px; margin-bottom:6px;'>"
                                f"<span style='width:16px; height:16px; background-color:{color}; border-radius:3px; display:inline-block; margin-right:7px; border:1px solid rgba(0,0,0,0.3);'></span>"
                                f"<span style='font-size:11.5px; font-weight:700; color:#1E293B;'>{roca}</span>"
                                f"</div>"
                                for roca, color in dic_leyenda_rocas.items()
                            ]
                            st.markdown(f"<div style='background-color:#ffffff; padding:12px; border-radius:6px; border:1px solid #E2E8F0; line-height:1.6;'>{''.join(items_html)}</div>", unsafe_allow_html=True)

                        try:
                            if gdf_geo is not None and not gdf_geo.empty:
                                with st.expander("🔬 Inspeccionar Tabla de Atributos Vectoriales de la Capa SGM", expanded=False):
                                    st.dataframe(gdf_geo.drop(columns=["geometry"], errors="ignore").head(20), use_container_width=True)
                        except NameError:
                            pass

            else:
                st.warning("⚠️ Se requieren al menos 4 pozos con coordenadas y elevación de terreno válidas para resolver la matriz matemática de interpolación.")
    renderizar_pestaña_mapa()
    
# =======================================================
# 📉 INCISO A: EVOLUCIÓN DEL NIVEL ESTÁTICO (Δh) Y CONOS DE ABATIMIENTO
# =======================================================
with tab_evolucion:
    @st.fragment
    def renderizar_pestaña_evolucion():
        st.markdown("""
            <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
                <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">📉 DIAGNÓSTICO DE EVOLUCIÓN PIEZOMÉTRICA Y CONOS DE ABATIMIENTO (Δh = ht₂ - ht₁)</span><br>
                <span style="font-size: 11.5px; color: #475569;">
                    Evaluación espacio-temporal del potencial hidráulico conforme al procedimiento de balance geohidrológico (NOM-011-CONAGUA-2015).
                    Identifica núcleos concéntricos de sobreexplotación (conos de abatimiento) y cuantifica el cambio en el volumen de almacenamiento (ΔV = ∬ Δh · Sy dA).
                </span>
            </div>
        """, unsafe_allow_html=True)
        
        anios_disp_evo = sorted([int(a) for a in df_ac['Año'].dropna().unique().tolist()])
        if len(anios_disp_evo) < 2:
            st.warning("⚠️ Se requieren datos de al menos 2 años distintos en este acuífero para evaluar la evolución temporal.")
            return

        idx_def_t1 = 0
        idx_def_t2 = len(anios_disp_evo) - 1
        if idx_def_t2 > 5:
            idx_def_t1 = max(0, idx_def_t2 - 10)

        with st.container(border=True):
            c_e1, c_e2, c_e3, c_e4 = st.columns([1.1, 1.1, 1.3, 1.1])
            anio_t1 = c_e1.selectbox("Año Base (t₁):", anios_disp_evo, index=idx_def_t1, key="sel_evo_t1")
            anio_t2 = c_e2.selectbox("Año Comparativo (t₂):", anios_disp_evo, index=idx_def_t2, key="sel_evo_t2")
            modo_sync_evo = c_e3.selectbox("Sincronización de Pozos:", ["Interpolación Temporal", "Corte Estricto"], index=0, key="sel_evo_sync")
            sy_param = c_e4.number_input("Coef. Almacenamiento (Sy):", min_value=0.001, max_value=0.35, value=0.08, step=0.01, format="%.3f", key="sel_evo_sy", help="Rendimiento específico Sy conforme a la NOM-011. Típicos: Granular 0.05-0.15, Rocas fracturadas 0.01-0.05.")

            c_e5, c_e6, c_e7 = st.columns([1.2, 1.6, 1.2])
            modelo_krig_evo = c_e5.selectbox("Semivariograma Kriging:", ["Esférico", "Lineal", "Gaussiano", "Exponencial"], index=0, key="sel_evo_vario")

            geom_oficial = st.session_state.get("poligono_personalizado", None)
            if geom_oficial is None:
                geom_oficial = poligono_oficial_geom

            opciones_delimitacion_evo = ["Pozos de Monitoreo (Envolvente Convexa)"]
            if geom_oficial is not None:
                opciones_delimitacion_evo.insert(0, "Polígono Oficial del Acuífero")

            modo_delimitacion_evo = c_e6.selectbox(
                "Delimitar interpolación por:", 
                opciones_delimitacion_evo, 
                index=0, 
                key="sel_evo_delim"
            )

            intervalo_iso_evo = c_e7.selectbox(
                "Intervalo Isolíneas (Δh):",
                [1.0, 2.0, 5.0, 10.0],
                index=1,
                format_func=lambda x: f"Cada {x:.1f} m",
                key="sel_evo_iso_step"
            )

        if anio_t1 >= anio_t2:
            st.error("⚠️ El Año Base (t₁) debe ser estrictamente anterior al Año Comparativo (t₂). Por favor ajuste los selectores de fecha.")
            return

        modo_p = "interpolado" if modo_sync_evo == "Interpolación Temporal" else "estricto"
        df_sync_t1 = obtener_red_sincronizada(df_ac, anio_t1, var_nombre='Carga_Hidraulica', modo=modo_p)
        df_sync_t2 = obtener_red_sincronizada(df_ac, anio_t2, var_nombre='Carga_Hidraulica', modo=modo_p)

        if len(df_sync_t1) < 4 or len(df_sync_t2) < 4:
            st.warning(f"⚠️ Se requieren al menos 4 pozos válidos por año para interpolar. Pozos t₁ ({anio_t1}): {len(df_sync_t1)} | Pozos t₂ ({anio_t2}): {len(df_sync_t2)}.")
            return

        if modo_delimitacion_evo == "Polígono Oficial del Acuífero" and geom_oficial is not None:
            delim_geom = geom_oficial
            bounds_lim = geom_oficial.bounds
            label_delimitacion = "Polígono Oficial del Acuífero"
        else:
            x_pozos = np.concatenate([df_sync_t1['Longitud'].values, df_sync_t2['Longitud'].values])
            y_pozos = np.concatenate([df_sync_t1['Latitud'].values, df_sync_t2['Latitud'].values])
            try:
                hull = ConvexHull(np.column_stack((x_pozos, y_pozos)))
                hull_pts = np.column_stack((x_pozos[hull.vertices], y_pozos[hull.vertices]))
                hull_loop = np.vstack([hull_pts, hull_pts[0]])
                delim_geom = Polygon(hull_loop)
                bounds_lim = delim_geom.bounds
            except Exception:
                delim_geom = None
                bounds_lim = None
            label_delimitacion = "Envolvente Convexa de Pozos"

        with st.spinner("Modelando superficies piezométricas t₁ y t₂ mediante Kriging Ordinario..."):
            res_k1 = resolver_malla_kriging(df_sync_t1, 'Carga_Hidraulica', modelo_krig_evo, bounds_limite=bounds_lim, resolucion=120)
            res_k2 = resolver_malla_kriging(df_sync_t2, 'Carga_Hidraulica', modelo_krig_evo, bounds_limite=bounds_lim, resolucion=120)

            if res_k1[0] is None:
                st.error(f"Error resolviendo Kriging para {anio_t1}: {res_k1[1]}")
                return
            if res_k2[0] is None:
                st.error(f"Error resolviendo Kriging para {anio_t2}: {res_k2[1]}")
                return

            X, Y, Z1, grid_x, grid_y, bounds = res_k1[0], res_k1[1], res_k1[2], res_k1[3], res_k1[4], res_k1[5]
            Z2 = res_k2[2]
            delta_Z = Z2 - Z1

        pts_grid = np.column_stack((X.ravel(), Y.ravel()))
        inside_mask = None
        if delim_geom is not None:
            try:
                if delim_geom.geom_type == 'Polygon':
                    path_poly = MplPath(np.array(delim_geom.exterior.coords))
                    inside_mask = path_poly.contains_points(pts_grid).reshape(X.shape)
                elif delim_geom.geom_type == 'MultiPolygon':
                    mask_accum = np.zeros(len(pts_grid), dtype=bool)
                    for poly_sub in delim_geom.geoms:
                        p_sub = MplPath(np.array(poly_sub.exterior.coords))
                        mask_accum |= p_sub.contains_points(pts_grid)
                    inside_mask = mask_accum.reshape(X.shape)
            except Exception:
                inside_mask = None
        if inside_mask is None:
            inside_mask = np.ones(X.shape, dtype=bool)

        delta_Z_masked = np.where(inside_mask, delta_Z, np.nan)

        z_list = []
        for row in delta_Z_masked:
            r_vals = []
            for val in row:
                if np.isnan(val):
                    r_vals.append(None)
                else:
                    r_vals.append(round(float(val), 2))
            z_list.append(r_vals)
        z_data_json = json.dumps(z_list)
        bounds_json = json.dumps(bounds)

        lat_media = float(np.mean([bounds[0][0], bounds[1][0]]))
        dx_m = abs(grid_x[1] - grid_x[0]) * 111320.0 * math.cos(math.radians(lat_media))
        dy_m = abs(grid_y[1] - grid_y[0]) * 111320.0
        dA_m2 = dx_m * dy_m
        dA_km2 = dA_m2 / 1e6

        dt_anios = max(1, anio_t2 - anio_t1)
        valid_mask = inside_mask & (~np.isnan(delta_Z))
        delta_vals = delta_Z[valid_mask]

        if len(delta_vals) > 0:
            delta_V_m3 = float(np.sum(delta_vals * sy_param * dA_m2))
            delta_V_hm3 = delta_V_m3 / 1e6
            tasa_V_anual_hm3 = delta_V_hm3 / dt_anios
            st.session_state[f"res_dv_{clave_actual}"] = {
                "delta_V_hm3": delta_V_hm3,
                "tasa_V_anual_hm3": tasa_V_anual_hm3,
                "sy": sy_param,
                "periodo": f"{anio_t1} – {anio_t2}"
            }

            min_dh = float(np.min(delta_vals))
            max_dh = float(np.max(delta_vals))
            mean_dh = float(np.mean(delta_vals))

            caida_max_m = abs(min_dh) if min_dh < 0 else 0.0
            tasa_caida_max = caida_max_m / dt_anios

            n_total = len(delta_vals)
            n_abat = np.sum(delta_vals < -0.1)
            n_recup = np.sum(delta_vals > 0.1)

            area_total_km2 = n_total * dA_km2
            area_abat_km2 = n_abat * dA_km2
            area_recup_km2 = n_recup * dA_km2
            pct_abat = (area_abat_km2 / area_total_km2 * 100.0) if area_total_km2 > 0 else 0.0
            pct_recup = (area_recup_km2 / area_total_km2 * 100.0) if area_total_km2 > 0 else 0.0
        else:
            delta_V_hm3, tasa_V_anual_hm3 = 0.0, 0.0
            caida_max_m, tasa_caida_max, mean_dh = 0.0, 0.0, 0.0
            area_total_km2, area_abat_km2, pct_abat = 0.0, 0.0, 0.0

        with st.container(border=True):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric(
                "Cambio Almacenamiento (ΔV)",
                f"{delta_V_hm3:,.2f} hm³",
                f"{tasa_V_anual_hm3:+,.2f} hm³/año (NOM-011)",
                delta_color="normal" if delta_V_hm3 >= 0 else "inverse",
                help="Volumen total de agua subterránea acumulado (+) o perdido (-) por desalmacenamiento en el periodo analizado."
            )
            m2.metric(
                "Descenso Máximo Puntual",
                f"{caida_max_m:.2f} m",
                f"-{tasa_caida_max:.2f} m/año",
                delta_color="inverse" if caida_max_m > 0 else "off",
                help="Máxima caída puntual de carga hidráulica detectada en la superficie piezométrica."
            )
            m3.metric(
                "Evolución Media Ponderada",
                f"{mean_dh:+.2f} m",
                f"{mean_dh / dt_anios:+.2f} m/año",
                delta_color="normal" if mean_dh >= 0 else "inverse",
                help="Variación promedio ponderada de la carga hidráulica en toda la superficie del acuífero."
            )
            m4.metric(
                "Superficie en Abatimiento",
                f"{area_abat_km2:,.1f} km²",
                f"{pct_abat:.1f}% del área acuífera",
                delta_color="inverse" if pct_abat > 30 else "normal",
                help="Área del acuífero donde el nivel estático descendió más de 0.1 m."
            )

        df_pz_evo = []
        m_t1 = df_sync_t1.set_index('Pozo')
        m_t2 = df_sync_t2.set_index('Pozo')
        pozos_comunes = sorted(list(set(m_t1.index).intersection(set(m_t2.index))))

        features_pozos_evo = []
        for pz in pozos_comunes:
            r1 = m_t1.loc[pz]
            r2 = m_t2.loc[pz]
            if isinstance(r1, pd.DataFrame): r1 = r1.iloc[0]
            if isinstance(r2, pd.DataFrame): r2 = r2.iloc[0]

            ch1 = float(r1['Carga_Hidraulica'])
            ch2 = float(r2['Carga_Hidraulica'])
            dh = ch2 - ch1
            tasa = dh / dt_anios

            if tasa <= -1.5:
                cond = "Abatimiento Crítico"
                col_p = "#990000"
            elif tasa <= -0.5:
                cond = "Abatimiento Moderado"
                col_p = "#d9534f"
            elif tasa < 0.0:
                cond = "Abatimiento Leve"
                col_p = "#f0ad4e"
            elif tasa == 0.0:
                cond = "Equilibrio"
                col_p = "#6c757d"
            else:
                cond = "Recuperación"
                col_p = "#0275d8"

            lat_p = float(r1['Latitud'])
            lon_p = float(r1['Longitud'])
            elev_p = float(r1.get('Elev.Terr', np.nan))

            rec_pz = {
                'Pozo': str(pz),
                'Latitud': lat_p,
                'Longitud': lon_p,
                'Elev_Terr': elev_p,
                f'Carga_{anio_t1}_msnm': round(ch1, 2),
                f'Carga_{anio_t2}_msnm': round(ch2, 2),
                'Delta_h_m': round(dh, 2),
                'Tasa_m_anio': round(tasa, 2),
                'Condicion': cond,
                'Color': col_p
            }
            df_pz_evo.append(rec_pz)
            features_pozos_evo.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon_p, lat_p]},
                "properties": rec_pz
            })
        df_pz_evo = pd.DataFrame(df_pz_evo)
        geojson_pozos_evo_str = json.dumps({"type": "FeatureCollection", "features": features_pozos_evo})

        # Carga e integración espacial de Concesiones REPDA (Inciso D: Causa vs Efecto)
        resumen_repda = cargar_resumen_repda(clave_actual)
        df_repda_pts, geojson_repda_str, tiene_repda_pts = cargar_concesiones_repda_puntos(clave_actual, st.session_state.get("repda_custom_df"))

        vol_en_abatimiento_m3 = 0.0
        vol_total_muestra_m3 = 0.0
        n_repda_en_abat = 0
        n_repda_total = len(df_repda_pts)

        interp_dh = None
        try:
            interp_dh = RegularGridInterpolator((grid_y, grid_x), delta_Z_masked, bounds_error=False, fill_value=np.nan)
        except Exception:
            interp_dh = None

        features_repda_enriquecidas = []
        if tiene_repda_pts:
            try:
                repda_fc = json.loads(geojson_repda_str)
                for feat in repda_fc.get("features", []):
                    props = feat.get("properties", {})
                    lon_pt = feat["geometry"]["coordinates"][0]
                    lat_pt = feat["geometry"]["coordinates"][1]

                    dh_val = float(interp_dh((lat_pt, lon_pt))) if interp_dh is not None else np.nan
                    v_m3 = float(props.get("volumen_m3", 0.0))
                    vol_total_muestra_m3 += v_m3

                    if not np.isnan(dh_val):
                        dh_val_round = round(dh_val, 2)
                        if dh_val <= -1.5:
                            diag_rep = "🚨 Núcleo de Abatimiento Crítico"
                            col_diag = "#990000"
                            es_abat = True
                        elif dh_val <= -0.5:
                            diag_rep = "⚠️ Cono de Abatimiento Moderado"
                            col_diag = "#d9534f"
                            es_abat = True
                        elif dh_val < -0.1:
                            diag_rep = "📉 Cono de Abatimiento Leve"
                            col_diag = "#f0ad4e"
                            es_abat = True
                        elif dh_val <= 0.1:
                            diag_rep = "⚖️ Balance Neutro / Equilibrio"
                            col_diag = "#64748b"
                            es_abat = False
                        else:
                            diag_rep = "💧 Área de Recuperación Freática"
                            col_diag = "#0275d8"
                            es_abat = False
                    else:
                        dh_val_round = None
                        diag_rep = "⚪ Fuera de Envolvente Interpolada"
                        col_diag = "#94a3b8"
                        es_abat = False

                    if es_abat:
                        vol_en_abatimiento_m3 += v_m3
                        n_repda_en_abat += 1

                    props["dh_local"] = dh_val_round
                    props["diagnostico_evo"] = diag_rep
                    props["color_diagnostico"] = col_diag
                    feat["properties"] = props
                    features_repda_enriquecidas.append(feat)

                geojson_repda_str = json.dumps({"type": "FeatureCollection", "features": features_repda_enriquecidas})
            except Exception:
                pass

        pct_vol_en_abat = (vol_en_abatimiento_m3 / vol_total_muestra_m3 * 100.0) if vol_total_muestra_m3 > 0 else 0.0
        pct_pozos_en_abat = (n_repda_en_abat / n_repda_total * 100.0) if n_repda_total > 0 else 0.0

        img_evo_png, vmin_evo, vmax_evo = render_imagen_evolucion_divergente(X, Y, delta_Z_masked, bounds)
        img_iso_png, geojson_iso_bytes, shp_iso_zip = render_imagen_isolineas_evolucion(X, Y, delta_Z_masked, bounds, intervalo_iso_evo, clave_actual)
        geotiff_evo_bytes = generar_geotiff_bytes(delta_Z_masked, bounds)

        img_evo_b64 = base64.b64encode(img_evo_png).decode('utf-8')
        img_iso_b64 = base64.b64encode(img_iso_png).decode('utf-8')

        if delim_geom is not None:
            poly_geojson_obj = {"type": "Feature", "geometry": mapping(delim_geom), "properties": {"nombre": label_delimitacion}}
            poly_geojson_str = json.dumps(poly_geojson_obj)
            poly_bounds_json = json.dumps(list(delim_geom.bounds))
            centro_lon = float(delim_geom.centroid.x)
            centro_lat = float(delim_geom.centroid.y)
        else:
            poly_geojson_str = "null"
            poly_bounds_json = json.dumps([[bounds[0][1], bounds[0][0]], [bounds[1][1], bounds[1][0]]])
            centro_lon = float((bounds[0][1] + bounds[1][1]) / 2.0)
            centro_lat = float((bounds[0][0] + bounds[1][0]) / 2.0)

        min_y, min_x = bounds[0]
        max_y, max_x = bounds[1]
        img_coords_json = json.dumps([
            [min_x, max_y], [max_x, max_y], [max_x, min_y], [min_x, min_y]
        ])

        span_edit = 'contenteditable="true" spellcheck="false" title="Haz clic para editar este texto" class="txt-leyenda-editable"'

        # Preparar GeoJSON de Geología para Tab 2
        geojson_geo_evo_str = "{}"
        col_sel_geo_evo = "LITOLOGIA"
        dic_leyenda_rocas_evo = {}
        geom_geo_evo = delim_geom if delim_geom is not None else poligono_oficial_geom
        if geom_geo_evo is not None:
            gdf_geo_evo, col_sel_geo_evo, dic_leyenda_rocas_evo = preparar_geologia_vectorial(clave_actual, geom_geo_evo)
            if gdf_geo_evo is not None and not gdf_geo_evo.empty:
                geojson_geo_evo_str = gdf_geo_evo.to_json()

        leyenda_repda_html = ""
        if tiene_repda_pts:
            leyenda_repda_html = f"""
            <div id="leg-repda" style="margin-top:5px; border-top: 1px solid #eee; padding-top:4px;">
                <b style="color:#691C32; font-size:11px;"><span {span_edit}>Concesiones REPDA ({n_repda_total})</span></b><br>
                <div style="font-size:9.5px; color:#64748B; margin-bottom:3px;"><span {span_edit}>Radio proporcional a √Volumen</span></div>
                <i class="circle" style="background:#16a34a;"></i> <span {span_edit}>Agrícola</span><br>
                <i class="circle" style="background:#2563eb;"></i> <span {span_edit}>Público Urbano</span><br>
                <i class="circle" style="background:#d97706;"></i> <span {span_edit}>Industrial</span><br>
                <i class="circle" style="background:#9333ea;"></i> <span {span_edit}>Servicios / Comercial</span><br>
                <i class="circle" style="background:#06b6d4;"></i> <span {span_edit}>Doméstico</span><br>
                <i class="circle" style="background:#ec4899;"></i> <span {span_edit}>Diferentes Usos</span><br>
            </div>
            """

        leyenda_html_evo = f"""
        <b style="color:#691C32; font-size: 12px;"><span {span_edit}>Simbología Evolución</span></b><br>
        <div id="leg-pozos" style="margin-top:4px;">
            <i style="background:#990000;"></i> <span {span_edit}>Abatimiento Crítico (&lt; -1.5 m/año)</span><br>
            <i style="background:#d9534f;"></i> <span {span_edit}>Abatimiento Moderado (-1.5 a -0.5)</span><br>
            <i style="background:#f0ad4e;"></i> <span {span_edit}>Abatimiento Leve (-0.5 a 0.0)</span><br>
            <i style="background:#0275d8;"></i> <span {span_edit}>Recuperación Freática (&gt; 0.0 m/año)</span><br>
        </div>
        <div id="leg-poly" style="margin-top:4px; border-top: 1px solid #eee; padding-top:4px;">
            <i class="square" style="background:rgba(105,28,50,0.08); border: 1.5px dashed #691C32;"></i> <span {span_edit}>{label_delimitacion}</span><br>
        </div>
        {leyenda_repda_html}
        <div id="leg-repda-nac" style="display: none; margin-top:5px; border-top: 1px solid #eee; padding-top:4px;">
            <b style="color:#166534; font-size:11px;"><span {span_edit}>🇲🇽 REPDA Nacional (461,914)</span></b><br>
            <div style="font-size:9.5px; color:#64748B; margin-bottom:3px;"><span {span_edit}>Uso Oficial Registrado</span></div>
            <i class="circle" style="background:#16a34a;"></i> <span {span_edit}>Agrícola</span><br>
            <i class="circle" style="background:#2563eb;"></i> <span {span_edit}>Público Urbano</span><br>
            <i class="circle" style="background:#ca8a04;"></i> <span {span_edit}>Pecuario</span><br>
            <i class="circle" style="background:#dc2626;"></i> <span {span_edit}>Industrial</span><br>
            <i class="circle" style="background:#9333ea;"></i> <span {span_edit}>Servicios</span><br>
            <i class="circle" style="background:#0284c7;"></i> <span {span_edit}>Doméstico</span><br>
            <i class="circle" style="background:#0d9488;"></i> <span {span_edit}>Diferentes Usos</span><br>
        </div>
        """

        if dic_leyenda_rocas_evo:
            leyenda_html_evo += f'<div id="leg-geo" style="display: none; margin-top:4px; border-top: 1px solid #eee; padding-top:4px;">'
            leyenda_html_evo += f'<b style="color:#691C32; font-size:11px;"><span {span_edit}>Geología SGM ({col_sel_geo_evo})</span></b><div style="max-height: 140px; overflow-y: auto; margin-top:4px;">'
            for roca, color in dic_leyenda_rocas_evo.items():
                leyenda_html_evo += f'<i class="square" style="background:{color};"></i> <span {span_edit} style="font-size:9.5px;">{roca}</span><br>'
            leyenda_html_evo += '</div></div>'

        url_pmtiles_srv_tab2 = obtener_url_pmtiles()

        html_maplibre_evo = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <title>Evolución Piezométrica MapLibre</title>
            <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
            <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
            <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
            <script src="https://unpkg.com/pmtiles@2.11.0/dist/index.js"></script>
            
            <!-- Librerías Vectoriales para Dibujo y Cálculo Geodésico -->
            <link rel="stylesheet" href="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.css" type="text/css" />
            <script src="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/@turf/turf@6.5.0/turf.min.js"></script>
            <style>
                body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; overflow: hidden; }}
                #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; background: #ffffff; border-radius: 8px; }}
                
                .txt-leyenda-editable {{ 
                    cursor: text; padding: 1px 4px; border-radius: 3px; outline: none; 
                    border-bottom: 1px dashed transparent; transition: background-color 0.2s; 
                }}
                .txt-leyenda-editable:hover {{ 
                    background-color: rgba(0,0,0,0.05); border-bottom: 1px dashed #888; 
                }}
                .txt-leyenda-editable:focus {{ 
                    background-color: #ffffff; border-bottom: 1.5px solid #2980b9; 
                    box-shadow: 0 1px 3px rgba(0,0,0,0.15); 
                }}

                .gis-badge-popup .maplibregl-popup-content {{
                    background: rgba(255, 255, 255, 0.95) !important;
                    backdrop-filter: blur(8px) !important;
                    border: 1px solid #CBD5E1 !important;
                    border-top: 3px solid #691C32 !important;
                    border-radius: 6px !important;
                    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16) !important;
                    padding: 8px 12px !important;
                    font-family: 'Segoe UI', Arial, sans-serif !important;
                    line-height: 1.4 !important;
                    pointer-events: auto !important;
                }}
                .gis-badge-popup .maplibregl-popup-tip {{
                    border-top-color: rgba(255, 255, 255, 0.95) !important;
                }}
                .gis-badge-popup .maplibregl-popup-close-button {{
                    font-size: 14px !important;
                    color: #64748B !important;
                    padding: 2px 5px !important;
                    right: 2px !important;
                    top: 2px !important;
                    cursor: pointer !important;
                }}
                .gis-badge-popup .maplibregl-popup-close-button:hover {{
                    color: #DC2626 !important;
                    background: transparent !important;
                }}

                .hud-elevation {{
                    position: absolute; top: 12px; right: 55px; z-index: 1000;
                    background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
                    color: #1e293b; padding: 7px 14px; border-radius: 8px;
                    border: 1.5px solid #691C32; box-shadow: 0 4px 15px rgba(0,0,0,0.15);
                    font-size: 11.5px; display: flex; gap: 14px; align-items: center; pointer-events: none;
                }}
                .hud-elevation b {{ color: #691C32; margin-right: 4px; }}
                
                .btn-open-dock-circle {{
                    position: absolute; top: 12px; left: 12px; z-index: 1000;
                    background: #691C32; color: #ffffff; width: 38px; height: 38px;
                    border-radius: 50%; border: 1.5px solid #DDC9A3;
                    box-shadow: 0 3px 12px rgba(105, 28, 50, 0.35);
                    font-size: 19px; font-weight: bold; cursor: pointer;
                    display: flex; align-items: center; justify-content: center;
                    transition: all 0.2s ease;
                }}
                .btn-open-dock-circle:hover {{ background: #88102B; transform: scale(1.1); }}
                
                .workbench-dock {{
                    position: absolute; top: 12px; left: 12px; z-index: 2000;
                    background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                    width: 280px; border-radius: 10px; overflow: hidden;
                    box-shadow: 0 6px 20px rgba(0,0,0,0.25); border-top: 4px solid #691C32;
                    border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0;
                    font-size: 11.5px; color: #1E293B;
                }}
                .dock-header {{ 
                    background: #691C32; color: white; padding: 9px 12px; 
                    font-weight: 700; display: flex; justify-content: space-between; align-items: center; 
                }}
                .dock-body {{ padding: 12px 14px; max-height: 70vh; overflow-y: auto; }}
                .dock-section {{ margin-bottom: 12px; }}
                .dock-section label {{ display: flex; align-items: center; gap: 6px; cursor: pointer; margin-bottom: 6px; font-weight: 500; }}
                .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; margin-top: 4px; }}
                
                .legend-panel {{
                    position: absolute; bottom: 35px; left: 12px; z-index: 1000;
                    background: rgba(255,255,255,0.95); padding: 10px 14px; border-radius: 8px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-size: 11px; line-height: 1.6;
                    border: 1px solid #E2E8F0; max-width: 280px; pointer-events: auto;
                }}
                .legend-panel i {{ width: 12px; height: 12px; display: inline-block; border-radius: 50%; margin-right: 6px; vertical-align: middle; border: 1px solid #ccc; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }}
                .legend-panel .square {{ border-radius: 2px; }}
                
                .leaflet-open-gradient-btn {{
                    position: absolute; top: 160px; right: 10px; z-index: 1000;
                    background: #691C32 !important; color: #ffffff; width: 29px; height: 29px;
                    border-radius: 4px; border: 2px solid rgba(0,0,0,0.2);
                    cursor: pointer; display: flex; align-items: center; justify-content: center;
                    transition: background 0.2s ease;
                }}
                .leaflet-open-gradient-btn:hover {{ background: #88102B !important; }}

                .gradient-docked-panel {{
                    position: absolute; top: 160px; right: 50px; z-index: 2000;
                    background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                    width: 230px; border-radius: 8px; overflow: hidden;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.2); border-top: 3px solid #691C32;
                    border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0;
                    font-size: 11px; color: #1E293B;
                }}
                .docked-gradient-header {{
                    background: #f8fafc; color: #1e293b; padding: 6px 10px;
                    font-weight: 700; display: flex; justify-content: space-between; align-items: center;
                    border-bottom: 1px solid #e2e8f0;
                }}
                .docked-gradient-close {{ cursor: pointer; font-size: 16px; color: #64748b; line-height: 1; }}
                .docked-gradient-close:hover {{ color: #dc2626; }}
                .docked-gradient-body {{ padding: 10px; }}
                .gradient-bar {{ height: 10px; border-radius: 4px; background: linear-gradient(to right, #b2182b, #ef8a62, #fddbc7, #f7f7f7, #d1e5f0, #67a9cf, #2166ac); margin: 6px 0; border: 1px solid #ccc; }}
                .gradient-labels {{ display: flex; justify-content: space-between; font-weight: bold; color: #333; }}

                .leaflet-open-draw-btn {{
                    position: absolute; top: 200px; right: 10px; z-index: 1000;
                    background: #691C32 !important; color: #ffffff; width: 29px; height: 29px;
                    border-radius: 4px; border: 2px solid rgba(0,0,0,0.2);
                    cursor: pointer; display: flex; align-items: center; justify-content: center;
                    transition: background 0.2s ease;
                }}
                .leaflet-open-draw-btn:hover {{ background: #88102B !important; }}

                .draw-docked-panel {{
                    position: absolute; top: 160px; right: 50px; z-index: 2000;
                    background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                    width: 275px; border-radius: 8px; overflow: hidden;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.2); border-top: 3px solid #691C32;
                    border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0;
                    font-size: 11px; color: #1E293B;
                }}
                .docked-draw-header {{
                    background: #f8fafc; color: #1e293b; padding: 6px 10px;
                    font-weight: 700; display: flex; justify-content: space-between; align-items: center;
                    border-bottom: 1px solid #e2e8f0; font-size: 11.5px;
                }}
                .docked-draw-close {{ cursor: pointer; font-size: 16px; color: #64748b; line-height: 1; font-weight: bold; }}
                .docked-draw-close:hover {{ color: #dc2626; }}
                .docked-draw-body {{ padding: 10px; }}

                .draw-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px; margin-bottom: 8px; }}
                .btn-tool {{
                    background: #ffffff; border: 1px solid #CBD5E1; border-radius: 5px;
                    padding: 5px 6px; font-size: 10.5px; font-weight: 600; color: #334155;
                    display: flex; align-items: center; justify-content: center; gap: 5px; cursor: pointer; transition: all 0.15s ease;
                }}
                .btn-tool svg {{ width: 13px; height: 13px; stroke: #691C32; fill: none; stroke-width: 2; flex-shrink: 0; }}
                .btn-tool:hover {{ background: #f1f5f9; border-color: #691C32; color: #691C32; }}
                .btn-tool.active {{ background: #691C32; border-color: #691C32; color: #ffffff; }}
                .btn-tool.active svg {{ stroke: #ffffff; }}

                .btn-preset {{
                    flex: 1; padding: 3px 4px; font-size: 10px; font-weight: 600;
                    border: 1px solid #cbd5e1; border-radius: 3px; background: #f8fafc;
                    color: #475569; cursor: pointer; transition: all 0.15s ease; text-align: center;
                }}
                .btn-preset:hover {{ background: #e2e8f0; color: #1e293b; border-color: #691C32; }}

                .draw-measure-box {{
                    background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 5px;
                    padding: 8px 10px; font-size: 11px; line-height: 1.45; color: #14532D;
                    margin-bottom: 8px; display: none;
                }}
                .draw-measure-box b {{ color: #166534; }}

                .draw-actions {{ display: flex; gap: 6px; border-top: 1px solid #f1f5f9; padding-top: 8px; }}
                .btn-action-sm {{
                    flex: 1; padding: 5px 8px; font-size: 10.5px; font-weight: 600;
                    border-radius: 4px; border: 1px solid #cbd5e1; background: #ffffff;
                    cursor: pointer; display: flex; align-items: center; justify-content: center;
                    gap: 5px; transition: all 0.15s ease; color: #334155;
                }}
                .btn-action-sm svg {{ width: 13px; height: 13px; stroke: currentColor; fill: none; stroke-width: 2; }}
                .btn-action-sm:hover {{ background: #f8fafc; border-color: #94A3B8; }}
                .btn-action-sm.danger {{ color: #dc2626; border-color: #fecaca; }}
                .btn-action-sm.danger:hover {{ background: #fef2f2; border-color: #dc2626; }}

                .label-marker-corte {{
                    width: 22px; height: 22px; border-radius: 50%;
                    color: #ffffff; font-weight: 800; font-size: 11px;
                    display: flex; align-items: center; justify-content: center;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.35); border: 2px solid #ffffff;
                    pointer-events: none; font-family: 'Segoe UI', Arial, sans-serif;
                }}
                .label-marker-corte.label-a {{ background: #691C32; }}
                .label-marker-corte.label-b {{ background: #166534; }}
            </style>
        </head>
        <body>
            <div id="map"></div>

            <div class="hud-elevation">
                <div><b>LON:</b> <span id="hud-lon">--</span></div>
                <div><b>LAT:</b> <span id="hud-lat">--</span></div>
                <div style="color:#008a3b;"><b>Δh:</b> <span id="hud-ele">--</span></div>
            </div>

            <div id="btn-open-dock" class="btn-open-dock-circle" onclick="toggleDock()" title="Abrir Herramientas Visuales">
                ☰
            </div>

            <div id="dock-panel" class="workbench-dock" style="display: none;">
                <div class="dock-header">
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span>🛠️ Capas Visuales</span>
                    </div>
                    <button onclick="toggleDock()" style="background:transparent; border:none; color:white; font-size:16px; font-weight:bold; cursor:pointer; line-height:1; padding:2px 5px;" title="Contraer panel">✕</button>
                </div>
                <div class="dock-body">
                    <div class="dock-section">
                        <label style="font-weight:700; color:#691C32; margin-bottom:2px;">🌍 Mapa Base:</label>
                        <select id="sel-basemap" class="slider-ctrl" style="padding: 4px; border-radius: 4px; border: 1px solid #ccc; width: 100%; background: #f8fafc;">
                            <option value="base-light-layer">Gris Claro (Esri)</option>
                            <option value="base-sat-layer">Satélite (Esri)</option>
                            <option value="base-topo-layer">Topográfico (Esri)</option>
                            <option value="base-osm-layer">OpenStreetMap</option>
                            <option value="base-street-layer">Estándar (Esri)</option>
                            <option value="base-terrain-layer">Terreno (Esri)</option>
                            <option value="base-ocean-layer">Océanos (Esri)</option>
                            <option value="base-dark-layer">Gris Oscuro (Esri)</option>
                            <option value="base-google-layer">Google Satelital gris 35%</option>
                        </select>
                    </div>
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;">
                    <div class="dock-section">
                        <label style="font-weight:700; color:#691C32; margin-bottom:2px;">🎨 Transparencia Malla Δh: <span id="val-opac">70%</span></label>
                        <input type="range" class="slider-ctrl" id="slider-opac" min="0" max="1" step="0.05" value="0.70" oninput="cambiarOpacidadEvo(this.value)">
                    </div>
                    <div class="dock-section" id="sec-opac-geo" style="display: none;">
                        <label style="font-weight:700; color:#691C32; margin-bottom:2px;">🎨 Transparencia Geología: <span id="val-opac-geo">50%</span></label>
                        <input type="range" class="slider-ctrl" id="slider-opac-geo" min="0" max="1" step="0.05" value="0.50" oninput="cambiarOpacidadGeologia(this.value)">
                    </div>
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;">
                    <div class="dock-section">
                        <label><input type="checkbox" id="chk-kriging" checked> 🌊 Malla Divergente Δh</label>
                        <label><input type="checkbox" id="chk-iso" checked> 📏 Isolíneas de Descenso</label>
                        <label><input type="checkbox" id="chk-pozos" checked> 📍 Red Piezométrica</label>
                        <label><input type="checkbox" id="chk-poly" checked> 🗺️ {label_delimitacion}</label>
                        <label style="display: {'flex' if tiene_repda_pts else 'none'};"><input type="checkbox" id="chk-repda" checked> 🏢 Concesiones REPDA ({n_repda_total})</label>
                        <label style="display: flex;"><input type="checkbox" id="chk-repda-nac"> 🇲🇽 REPDA Nacional MVT (461,914)</label>
                        <label style="display: {'flex' if dic_leyenda_rocas_evo else 'none'};"><input type="checkbox" id="chk-geo"> ⛰️ Geología SGM</label>
                    </div>
                </div>
            </div>

            <div class="legend-panel">
                {leyenda_html_evo}
            </div>

            <div id="btn-open-gradient" class="leaflet-open-gradient-btn" onclick="toggleGradient()" title="Mostrar Gradiente">
                <div style="width: 14px; height: 14px; background: linear-gradient(to bottom, #b2182b, #2166ac); border: 1px solid #fff; border-radius: 2px;"></div>
            </div>

            <div id="gradient-panel-container" class="gradient-docked-panel" style="display: none;">
                <div class="docked-gradient-header">
                    <span>Gradiente Piezométrico (Δh)</span>
                    <span class="docked-gradient-close" onclick="toggleGradient()" title="Ocultar">&times;</span>
                </div>
                <div class="docked-gradient-body">
                    <b style="color:#691C32; font-size:11px;">Evolución del Nivel ({anio_t2} - {anio_t1})</b>
                    <div class="gradient-bar"></div>
                    <div class="gradient-labels">
                        <span style="color:#990000;">{vmin_evo:.1f} m</span>
                        <span style="color:#2C3E50;">0.0 m</span>
                        <span style="color:#0055AA;">+{vmax_evo:.1f} m</span>
                    </div>
                    <div style="font-size:9.5px; color:#64748B; margin-top:5px; text-align:center;">Rojo: Abatimiento | Azul: Recuperación</div>
                </div>
            </div>

            <div id="btn-open-draw" class="leaflet-open-draw-btn" onclick="toggleDraw()" title="Herramientas de Dibujo y Medición">
                <svg viewBox="0 0 24 24" style="width:16px; height:16px; stroke:#ffffff; fill:none; stroke-width:2;">
                    <path d="M12 19l7-7 3 3-7 7-3-3z"/>
                    <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/>
                    <circle cx="12" cy="12" r="2"/>
                </svg>
            </div>

            <div id="draw-panel-container" class="draw-docked-panel" style="display: none;">
                <div class="docked-draw-header">
                    <div style="display:flex; align-items:center; gap:6px;">
                        <svg viewBox="0 0 24 24" style="width:14px; height:14px; stroke:#691C32; fill:none; stroke-width:2;">
                            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                            <polyline points="2 17 12 22 22 17"/>
                            <polyline points="2 12 12 17 22 12"/>
                        </svg>
                        <span>Gabinete de Evolución (Δh)</span>
                    </div>
                    <span class="docked-draw-close" onclick="toggleDraw()" title="Ocultar">&times;</span>
                </div>
                <div class="docked-draw-body">
                    <div class="draw-grid">
                        <button id="btn-tool-point" class="btn-tool" onclick="activarModoDibujo('point')" title="Sondear variación de nivel Δh puntual">
                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/></svg>
                            Punto
                        </button>
                        <button id="btn-tool-line" class="btn-tool" onclick="activarModoDibujo('line_string')" title="Trazar transecto A-A' de variación de nivel">
                            <svg viewBox="0 0 24 24"><path d="M4 20L20 4"/><circle cx="4" cy="20" r="2.5"/><circle cx="20" cy="4" r="2.5"/></svg>
                            Corte A-A'
                        </button>
                        <button id="btn-tool-poly" class="btn-tool" onclick="activarModoDibujo('polygon')" title="Calcular superficie del área delimitada">
                            <svg viewBox="0 0 24 24"><polygon points="12 2 22 8.5 18 20 6 20 2 8.5"/></svg>
                            Polígono
                        </button>
                    </div>

                    <!-- Sección de Buffer / Cono de Influencia Fijo -->
                    <div style="margin: 8px 0; border-top: 1px solid #f1f5f9; padding-top: 8px;">
                        <div style="font-weight: 700; color: #1e293b; font-size: 10.5px; margin-bottom: 5px;">
                            <span>🎯 Radio de Influencia / Cono</span>
                        </div>
                        <div style="display:flex; gap: 4px; align-items: center; margin-bottom: 5px;">
                            <input type="number" id="input-buffer-radio" value="500" min="20" max="50000" step="50" 
                                   style="width: 70px; padding: 4px 6px; font-size: 11px; border: 1px solid #cbd5e1; border-radius: 4px;" title="Radio en metros">
                            <span style="font-size: 11px; color: #64748b;">m</span>
                            <button id="btn-tool-buffer" class="btn-tool" style="flex:1; padding: 4px 6px; font-size: 10.5px; justify-content: center;" onclick="activarModoBuffer()" title="Clic en mapa o pozo para fijar radio">
                                Fijar Radio
                            </button>
                        </div>
                        <div style="display: flex; gap: 4px;">
                            <button class="btn-preset" onclick="setBufferRadio(250)">250m</button>
                            <button class="btn-preset" onclick="setBufferRadio(500)">500m</button>
                            <button class="btn-preset" onclick="setBufferRadio(1000)">1km</button>
                            <button class="btn-preset" onclick="setBufferRadio(2000)">2km</button>
                        </div>
                    </div>

                    <!-- Controles de Modo Captura Limpia y Bloqueo -->
                    <div style="display:flex; justify-content:space-between; align-items:center; margin: 6px 0; background:#f8fafc; padding: 4px 6px; border-radius:4px; border:1px solid #e2e8f0;">
                        <label style="font-size:10px; color:#475569; display:flex; align-items:center; gap:5px; cursor:pointer;" title="Ocultar popups flotantes para capturas de pantalla 100% limpias">
                            <input type="checkbox" id="chk-show-badge" checked onchange="toggleMostrarBadges(this.checked)">
                            <span>Etiqueta en mapa</span>
                        </label>
                        <button class="btn-preset" onclick="deseleccionarTodo()" title="Ocultar nodos de edición para fotos de reporte" style="padding:2px 6px; font-size:9.5px;">
                            👁️ Ocultar Nodos
                        </button>
                    </div>

                    <div id="draw-measure-box" class="draw-measure-box"></div>

                    <div class="draw-actions">
                        <button class="btn-action-sm danger" onclick="eliminarDibujoSeleccionado()" title="Borrar selección o todos los trazos">
                            <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                            Limpiar
                        </button>
                        <button class="btn-action-sm" onclick="descargarDibujosGeoJSON()" title="Descargar trazos en GeoJSON para QGIS/ArcGIS">
                            <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                            Exportar
                        </button>
                        <button class="btn-action-sm" onclick="document.getElementById('input-import-geojson').click()" title="Cargar archivo GeoJSON al visor">
                            <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                            Importar
                        </button>
                        <input type="file" id="input-import-geojson" accept=".geojson,.json" style="display:none;" onchange="importarDibujosGeoJSON(event)">
                    </div>
                </div>
            </div>

            <script>
                const z_data = {z_data_json};
                const bounds = {bounds_json};
                const min_y = bounds[0][0], min_x = bounds[0][1];
                const max_y = bounds[1][0], max_x = bounds[1][1];
                const rows = z_data.length;
                const cols = z_data[0].length;

                const polyGeojson = {poly_geojson_str};
                const polyBounds = {poly_bounds_json};

                let dockAbierto = false;
                function aplicarEstadoVisualDock() {{
                    const panel = document.getElementById('dock-panel');
                    const btnOpen = document.getElementById('btn-open-dock');
                    if (panel && btnOpen) {{
                        panel.style.display = dockAbierto ? 'block' : 'none';
                        btnOpen.style.display = dockAbierto ? 'none' : 'flex';
                    }}
                }}
                function toggleDock() {{
                    dockAbierto = !dockAbierto;
                    aplicarEstadoVisualDock();
                }}
                aplicarEstadoVisualDock();

                let gradientAbierto = false;
                function toggleGradient() {{
                    gradientAbierto = !gradientAbierto;
                    const panel = document.getElementById('gradient-panel-container');
                    const btn = document.getElementById('btn-open-gradient');
                    if (gradientAbierto) {{
                        panel.style.display = 'block';
                        btn.style.display = 'none';
                        if (drawAbierto) toggleDraw();
                    }} else {{
                        panel.style.display = 'none';
                        btn.style.display = 'flex';
                    }}
                }}

                const iconExpandSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
                const iconCompressSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;

                let protocol = new pmtiles.Protocol();
                maplibregl.addProtocol("pmtiles", protocol.tile);

                const map = new maplibregl.Map({{
                    container: 'map',
                    style: {{
                        'version': 8,
                        'sources': {{
                            'base-light': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri' }},
                            'base-sat': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, Maxar' }},
                            'base-topo': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, USGS' }},
                            'base-osm': {{ 'type': 'raster', 'tiles': ['https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png'], 'tileSize': 256, 'attribution': '© OpenStreetMap' }},
                            'base-street': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri' }},
                            'base-terrain': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, USGS' }},
                            'base-ocean': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, GEBCO' }},
                            'base-dark': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri' }},
                            'base-google': {{ 'type': 'raster', 'tiles': ['https://mt1.google.com/vt/lyrs=s&x={{x}}&y={{y}}&z={{z}}'], 'tileSize': 256, 'attribution': 'Google Satellite' }}
                        }},
                        'layers': [
                            {{ 'id': 'base-light-layer', 'type': 'raster', 'source': 'base-light', 'layout': {{'visibility': 'visible'}} }},
                            {{ 'id': 'base-sat-layer', 'type': 'raster', 'source': 'base-sat', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-topo-layer', 'type': 'raster', 'source': 'base-topo', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-osm-layer', 'type': 'raster', 'source': 'base-osm', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-street-layer', 'type': 'raster', 'source': 'base-street', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-terrain-layer', 'type': 'raster', 'source': 'base-terrain', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-ocean-layer', 'type': 'raster', 'source': 'base-ocean', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-dark-layer', 'type': 'raster', 'source': 'base-dark', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-google-layer', 'type': 'raster', 'source': 'base-google', 'layout': {{'visibility': 'none'}}, 'paint': {{'raster-opacity': 0.35, 'raster-saturation': -1.0}} }}
                        ]
                    }},
                    center: [{centro_lon}, {centro_lat}],
                    zoom: 9.5,
                    attributionControl: false,
                    preserveDrawingBuffer: true
                }});

                class CustomFullscreenControl {{
                    onAdd(mapInstance) {{
                        this._map = mapInstance;
                        this._container = document.createElement('div');
                        this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group';
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.innerHTML = iconExpandSVG;
                        btn.title = 'Pantalla Completa';
                        btn.style.width = '30px';
                        btn.style.height = '30px';
                        btn.style.display = 'flex';
                        btn.style.alignItems = 'center';
                        btn.style.justifyContent = 'center';
                        btn.style.cursor = 'pointer';

                        btn.addEventListener('click', () => {{
                            if (!document.fullscreenElement) {{
                                document.documentElement.requestFullscreen().catch(err => alert(err.message));
                            }} else {{
                                if (document.exitFullscreen) document.exitFullscreen();
                            }}
                        }});

                        document.addEventListener('fullscreenchange', () => {{
                            btn.innerHTML = document.fullscreenElement ? iconCompressSVG : iconExpandSVG;
                            btn.title = document.fullscreenElement ? 'Salir de Pantalla Completa' : 'Pantalla Completa';
                            setTimeout(() => {{ mapInstance.resize(); }}, 200);
                        }});

                        this._container.appendChild(btn);
                        return this._container;
                    }}
                    onRemove() {{
                        this._container.parentNode.removeChild(this._container);
                        this._map = undefined;
                    }}
                }}

                map.addControl(new CustomFullscreenControl(), 'top-right');
                map.addControl(new maplibregl.NavigationControl(), 'top-right');
                map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-right');

                const draw = new MapboxDraw({{
                    displayControlsDefault: false,
                    controls: {{}},
                    userProperties: true,
                    styles: [
                        {{
                            'id': 'gl-draw-line', 'type': 'line',
                            'filter': ['all', ['==', '$type', 'LineString'], ['!=', 'mode', 'static']],
                            'layout': {{ 'line-cap': 'round', 'line-join': 'round' }},
                            'paint': {{ 'line-color': '#9f2241', 'line-width': 3, 'line-dasharray': [0.2, 2] }}
                        }},
                        {{
                            'id': 'gl-draw-polygon-fill', 'type': 'fill',
                            'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                            'paint': {{ 'fill-color': '#285c4d', 'fill-opacity': 0.25 }}
                        }},
                        {{
                            'id': 'gl-draw-polygon-stroke', 'type': 'line',
                            'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                            'layout': {{ 'line-cap': 'round', 'line-join': 'round' }},
                            'paint': {{ 'line-color': '#285c4d', 'line-width': 2.5 }}
                        }},
                        {{
                            'id': 'gl-draw-point', 'type': 'circle',
                            'filter': ['all', ['==', '$type', 'Point'], ['!=', 'meta', 'vertex'], ['!=', 'meta', 'midpoint'], ['!=', 'mode', 'static']],
                            'paint': {{ 'circle-radius': 5, 'circle-color': '#ffffff', 'circle-stroke-width': 2, 'circle-stroke-color': '#691C32' }}
                        }},
                        {{
                            'id': 'gl-draw-vertex-inactive', 'type': 'circle',
                            'filter': ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                            'paint': {{ 'circle-radius': 5, 'circle-color': '#ffffff', 'circle-stroke-width': 2, 'circle-stroke-color': '#691C32' }}
                        }},
                        {{
                            'id': 'gl-draw-vertex-active', 'type': 'circle',
                            'filter': ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                            'paint': {{ 'circle-radius': 7, 'circle-color': '#691C32', 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' }}
                        }},
                        {{
                            'id': 'gl-draw-midpoint', 'type': 'circle',
                            'filter': ['all', ['==', 'meta', 'midpoint'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                            'paint': {{ 'circle-radius': 4.5, 'circle-color': '#DDC9A3', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#691C32' }}
                        }}
                    ]
                }});
                map.addControl(draw);

                let drawAbierto = false;
                function toggleDraw() {{
                    drawAbierto = !drawAbierto;
                    const panel = document.getElementById('draw-panel-container');
                    const btn = document.getElementById('btn-open-draw');
                    if (drawAbierto) {{
                        panel.style.display = 'block';
                        btn.style.display = 'none';
                        if (gradientAbierto) toggleGradient();
                    }} else {{
                        panel.style.display = 'none';
                        btn.style.display = 'flex';
                        detenerModoBuffer();
                        limpiarHerramientasActivas();
                    }}
                }}

                function activarModoDibujo(mode) {{
                    detenerModoBuffer();
                    limpiarHerramientasActivas();
                    map.getCanvas().style.cursor = 'crosshair'; 
                    if (mode === 'point') {{
                        document.getElementById('btn-tool-point').classList.add('active');
                        draw.changeMode('draw_point');
                    }} else if (mode === 'line_string') {{
                        document.getElementById('btn-tool-line').classList.add('active');
                        draw.changeMode('draw_line_string');
                    }} else if (mode === 'polygon') {{
                        document.getElementById('btn-tool-poly').classList.add('active');
                        draw.changeMode('draw_polygon');
                    }}
                }}

                function limpiarHerramientasActivas() {{
                    ['btn-tool-point', 'btn-tool-line', 'btn-tool-poly', 'btn-tool-buffer'].forEach(id => {{
                        const el = document.getElementById(id);
                        if (el) el.classList.remove('active');
                    }});
                    map.getCanvas().style.cursor = ''; 
                }}

                let modoBufferActivo = false;
                let radioBufferMetros = 500;

                function setBufferRadio(m) {{
                    document.getElementById('input-buffer-radio').value = m;
                    radioBufferMetros = m;
                    activarModoBuffer();
                }}

                function activarModoBuffer() {{
                    limpiarHerramientasActivas();
                    draw.changeMode('simple_select');
                    modoBufferActivo = true;
                    const inputRadio = document.getElementById('input-buffer-radio');
                    radioBufferMetros = parseFloat(inputRadio.value) || 500;
                    document.getElementById('btn-tool-buffer').classList.add('active');
                    map.getCanvas().style.cursor = 'crosshair';
                    const box = document.getElementById('draw-measure-box');
                    box.style.display = 'block';
                    box.innerHTML = `<b>🎯 Buffer Fijo (${{radioBufferMetros}} m):</b> Clic en el mapa para situar radio de influencia.`;
                }}

                function detenerModoBuffer() {{
                    modoBufferActivo = false;
                    map.getCanvas().style.cursor = '';
                    const btn = document.getElementById('btn-tool-buffer');
                    if (btn) btn.classList.remove('active');
                }}

                function eliminarDibujoSeleccionado() {{
                    const sel = draw.getSelectedIds();
                    if (sel && sel.length > 0) {{
                        draw.delete(sel);
                    }} else {{
                        draw.deleteAll();
                    }}
                    document.getElementById('draw-measure-box').style.display = 'none';
                    limpiarRotulosLinea();
                    if (popupDibujoActivo) popupDibujoActivo.remove();
                }}

                function descargarDibujosGeoJSON() {{
                    const data = draw.getAll();
                    if (!data || !data.features || data.features.length === 0) {{
                        alert("No hay geometrías trazadas en el mapa para exportar.");
                        return;
                    }}
                    const blob = new Blob([JSON.stringify(data, null, 2)], {{ type: 'application/geo+json' }});
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'mediciones_evolucion_dh.geojson';
                    a.click();
                    URL.revokeObjectURL(url);
                }}

                function importarDibujosGeoJSON(e) {{
                    const file = e.target.files[0];
                    if (!file) return;
                    const reader = new FileReader();
                    reader.onload = function(evt) {{
                        try {{
                            const data = JSON.parse(evt.target.result);
                            if (data.type === "FeatureCollection" && data.features) {{
                                data.features.forEach(f => draw.add(f));
                                const bbox = turf.bbox(data);
                                map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], {{ padding: 40 }});
                                alert(`Se importaron ${{data.features.length}} geometrías exitosamente.`);
                            }} else if (data.type === "Feature") {{
                                draw.add(data);
                                const bbox = turf.bbox(data);
                                map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], {{ padding: 40 }});
                                alert("Se importó 1 geometría exitosamente.");
                            }} else {{
                                alert("Formato GeoJSON no válido.");
                            }}
                        }} catch(err) {{
                            alert("Error al leer archivo: " + err.message);
                        }}
                    }};
                    reader.readAsText(file);
                    e.target.value = "";
                }}

                let markerA = null;
                let markerB = null;
                let popupDibujoActivo = null;

                function actualizarRotulosLinea(feat) {{
                    limpiarRotulosLinea();
                    if (!feat || !feat.geometry || feat.geometry.type !== 'LineString') return;
                    const coords = feat.geometry.coordinates;
                    if (!coords || coords.length < 2) return;
                    
                    const elA = document.createElement('div');
                    elA.className = 'label-marker-corte label-a';
                    elA.innerText = 'A';
                    elA.title = 'Extremo Inicial A del corte';
                    
                    const elB = document.createElement('div');
                    elB.className = 'label-marker-corte label-b';
                    elB.innerText = "A'";
                    elB.title = "Extremo Final A' del corte";
                    
                    markerA = new maplibregl.Marker({{ element: elA }}).setLngLat(coords[0]).addTo(map);
                    markerB = new maplibregl.Marker({{ element: elB }}).setLngLat(coords[coords.length - 1]).addTo(map);
                }}

                function limpiarRotulosLinea() {{
                    if (markerA) {{ markerA.remove(); markerA = null; }}
                    if (markerB) {{ markerB.remove(); markerB = null; }}
                }}

                function toggleMostrarBadges(mostrar) {{
                    if (!mostrar && popupDibujoActivo) {{
                        popupDibujoActivo.remove();
                    }} else if (mostrar) {{
                        const feats = draw.getAll().features;
                        if (feats && feats.length > 0) {{
                            actualizarMedicionCompleta(feats[feats.length - 1], true);
                        }}
                    }}
                }}

                function deseleccionarTodo() {{
                    draw.changeMode('simple_select', {{ featureIds: [] }});
                    if (popupDibujoActivo) popupDibujoActivo.remove();
                }}

                window.addEventListener('keydown', (e) => {{
                    if (e.key === 'Escape') {{
                        const m = draw.getMode();
                        if (m.startsWith('draw_') || modoBufferActivo) {{
                            draw.trash();
                            draw.changeMode('simple_select');
                            detenerModoBuffer();
                            limpiarHerramientasActivas();
                            const b = document.getElementById('draw-measure-box');
                            if (b) b.style.display = 'none';
                            limpiarRotulosLinea();
                        }}
                    }}
                }});

                function obtenerInfoMedicion(feat) {{
                    if (!feat || !feat.geometry) return null;
                    const tipo = feat.geometry.type;
                    const props = feat.properties || {{}};

                    if (tipo === 'Point') {{
                        const c = feat.geometry.coordinates;
                        const lng = c[0], lat = c[1];
                        let valZ = null;
                        if (lat >= min_y && lat <= max_y && lng >= min_x && lng <= max_x) {{
                            let r = Math.floor(((lat - min_y) / (max_y - min_y)) * (rows - 1));
                            let col = Math.floor(((lng - min_x) / (max_x - min_x)) * (cols - 1));
                            r = Math.max(0, Math.min(rows - 1, r));
                            col = Math.max(0, Math.min(cols - 1, col));
                            valZ = z_data[r][col];
                        }}
                        const valTxt = (valZ !== null && !isNaN(valZ)) ? (valZ > 0 ? '+' : '') + valZ.toFixed(2) + ' m' : 'S/D';
                        const diagTxt = valZ !== null ? (valZ < -0.1 ? '🚨 Abatimiento Freático' : (valZ > 0.1 ? '🟢 Recuperación de Nivel' : 'Estabilidad')) : '';
                        
                        return {{
                            coords: c,
                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📍 Sondeo de Variación (Δh)</div>` +
                                   `<div style="font-size:10.5px; color:#334155;">` +
                                   `<b>Evolución:</b> <span style="color:${{valZ < 0 ? '#990000' : '#0055aa'}}; font-weight:700;">${{valTxt}}</span><br>` +
                                   `<span style="color:#64748B; font-size:9.5px;">${{lat.toFixed(4)}}° N, ${{lng.toFixed(4)}}° W</span>` +
                                   `</div>`,
                            panel: `<b>📍 Sondeo de Evolución Δh</b><br>` +
                                   `<b>Coordenadas:</b> ${{lat.toFixed(5)}}° N, ${{lng.toFixed(5)}}° W<br>` +
                                   `<b>Variación Estimada:</b> <span style="color:${{valZ < 0 ? '#990000' : '#0055aa'}}; font-weight:700;">${{valTxt}}</span><br>` +
                                   `<b>Diagnóstico:</b> ${{diagTxt}}`
                        }};
                    }}

                    if (tipo === 'LineString') {{
                        const coordsPts = feat.geometry.coordinates;
                        const km = turf.length(feat, {{ units: 'kilometers' }});
                        const distFormato = km < 1.0 ? `${{(km * 1000).toFixed(0)}} m` : `${{km.toFixed(2)}} km`;
                        
                        const cA = coordsPts[0];
                        const cB = coordsPts[coordsPts.length - 1];
                        const rumbo = turf.bearing(cA, cB);
                        const azimut = (rumbo + 360) % 360;

                        let zA = null, zB = null;
                        if (cA[1] >= min_y && cA[1] <= max_y && cA[0] >= min_x && cA[0] <= max_x) {{
                            let r = Math.max(0, Math.min(rows - 1, Math.floor(((cA[1] - min_y) / (max_y - min_y)) * (rows - 1))));
                            let c = Math.max(0, Math.min(cols - 1, Math.floor(((cA[0] - min_x) / (max_x - min_x)) * (cols - 1))));
                            zA = z_data[r][c];
                        }}
                        if (cB[1] >= min_y && cB[1] <= max_y && cB[0] >= min_x && cB[0] <= max_x) {{
                            let r = Math.max(0, Math.min(rows - 1, Math.floor(((cB[1] - min_y) / (max_y - min_y)) * (rows - 1))));
                            let c = Math.max(0, Math.min(cols - 1, Math.floor(((cB[0] - min_x) / (max_x - min_x)) * (cols - 1))));
                            zB = z_data[r][c];
                        }}

                        const zATxt = zA !== null ? (zA > 0 ? '+' : '') + zA.toFixed(2) + ' m' : '--';
                        const zBTxt = zB !== null ? (zB > 0 ? '+' : '') + zB.toFixed(2) + ' m' : '--';
                        const deltaZ = (zA !== null && zB !== null) ? (zB - zA) : null;
                        const deltaZTxt = deltaZ !== null ? (deltaZ > 0 ? '+' : '') + deltaZ.toFixed(2) + ' m' : '--';
                        const midCoord = coordsPts[Math.floor(coordsPts.length / 2)];

                        return {{
                            coords: midCoord,
                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📏 Transecto A - A' (Δh)</div>` +
                                   `<div style="font-size:10.5px; color:#334155;">` +
                                   `<b>Longitud:</b> ${{distFormato}} · <b>Azimut:</b> ${{azimut.toFixed(0)}}°<br>` +
                                   `<b>Δh en A:</b> ${{zATxt}} | <b>Δh en A':</b> ${{zBTxt}}` +
                                   `</div>`,
                            panel: `<b>📏 Transecto de Variación A - A'</b><br>` +
                                   `<b>Longitud Total:</b> ${{distFormato}}<br>` +
                                   `<b>Azimut Geográfico:</b> ${{azimut.toFixed(1)}}°<br>` +
                                   `<b>Δh en Extremo A:</b> ${{zATxt}}<br>` +
                                   `<b>Δh en Extremo A':</b> ${{zBTxt}}<br>` +
                                   `<b>Diferencial (A' - A):</b> <b style="color:#691C32;">${{deltaZTxt}}</b>`
                        }};
                    }}

                    if (props.esCirculo || props.radioM) {{
                        const radioM = props.radioM || 500;
                        const areaHa = props.areaHa || (turf.area(feat) / 10000).toFixed(2);
                        const radioTxt = radioM >= 1000 ? `${{(radioM / 1000).toFixed(2)}} km` : `${{radioM}} m`;
                        return {{
                            coords: turf.centroid(feat).geometry.coordinates,
                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">🎯 Radio de Influencia</div>` +
                                   `<div style="font-size:10.5px; color:#334155;">` +
                                   `<b>Radio:</b> ${{radioTxt}}<br>` +
                                   `<b>Superficie:</b> ${{areaHa}} ha` +
                                   `</div>`,
                            panel: `<b>🎯 Radio de Influencia / Cono</b><br>` +
                                   `<b>Radio:</b> ${{radioTxt}}<br>` +
                                   `<b>Área Cubierta:</b> ${{areaHa}} ha<br>` +
                                   `<b>Perímetro:</b> ${{(2 * Math.PI * radioM / 1000).toFixed(2)}} km`
                        }};
                    }}

                    if (tipo === 'Polygon') {{
                        const m2 = turf.area(feat);
                        const ha = (m2 / 10000).toFixed(2);
                        const km2 = (m2 / 1e6).toFixed(2);
                        const kmPerim = turf.length(turf.polygonToLine(feat), {{ units: 'kilometers' }}).toFixed(2);
                        return {{
                            coords: turf.centroid(feat).geometry.coordinates,
                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📐 Área Delimitada</div>` +
                                   `<div style="font-size:10.5px; color:#334155;">` +
                                   `<b>Superficie:</b> ${{ha}} ha (${{km2}} km²)<br>` +
                                   `<b>Perímetro:</b> ${{kmPerim}} km` +
                                   `</div>`,
                            panel: `<b>📐 Polígono de Medición</b><br>` +
                                   `<b>Superficie:</b> ${{ha}} ha (${{km2}} km²)<br>` +
                                   `<b>Perímetro:</b> ${{kmPerim}} km`
                        }};
                    }}
                    return null;
                }}

                function actualizarMedicionCompleta(feat, mostrarBadge) {{
                    if (!feat) return;
                    const info = obtenerInfoMedicion(feat);
                    if (!info) return;

                    const box = document.getElementById('draw-measure-box');
                    if (box) {{
                        box.style.display = 'block';
                        box.innerHTML = info.panel;
                    }}

                    if (feat.geometry.type === 'LineString') {{
                        actualizarRotulosLinea(feat);
                    }} else {{
                        limpiarRotulosLinea();
                    }}

                    const chkBadge = document.getElementById('chk-show-badge');
                    const permitirBadge = chkBadge ? chkBadge.checked : true;

                    if (mostrarBadge && permitirBadge) {{
                        if (popupDibujoActivo) popupDibujoActivo.remove();
                        popupDibujoActivo = new maplibregl.Popup({{ closeOnClick: true, offset: 12, className: 'gis-badge-popup' }})
                            .setLngLat(info.coords)
                            .setHTML(info.badge)
                            .addTo(map);
                    }}
                }}

                map.on('draw.create', (e) => {{
                    if (e.features && e.features[0]) actualizarMedicionCompleta(e.features[0], true);
                    limpiarHerramientasActivas();
                }});
                map.on('draw.update', (e) => {{
                    if (e.features && e.features[0]) actualizarMedicionCompleta(e.features[0], false);
                }});
                map.on('draw.selectionchange', (e) => {{
                    if (e.features && e.features.length > 0) {{
                        actualizarMedicionCompleta(e.features[0], true);
                    }}
                }});
                map.on('draw.delete', () => {{
                    document.getElementById('draw-measure-box').style.display = 'none';
                    limpiarRotulosLinea();
                    if (popupDibujoActivo) popupDibujoActivo.remove();
                }});

                map.on('click', (e) => {{
                    if (modoBufferActivo) {{
                        const coords = [e.lngLat.lng, e.lngLat.lat];
                        const radioKm = radioBufferMetros / 1000.0;
                        const circlePoly = turf.circle(coords, radioKm, {{ steps: 64, units: 'kilometers' }});
                        const areaHa = (turf.area(circlePoly) / 10000).toFixed(2);
                        circlePoly.properties = {{
                            esCirculo: true,
                            radioM: radioBufferMetros,
                            areaHa: areaHa
                        }};
                        draw.add(circlePoly);
                        detenerModoBuffer();
                        actualizarMedicionCompleta(circlePoly, true);
                    }}
                }});

                map.on('load', function() {{
                    if (polyGeojson) {{
                        map.addSource('poly-src', {{ type: 'geojson', data: polyGeojson }});
                        map.addLayer({{
                            id: 'poly-layer-fill', type: 'fill', source: 'poly-src',
                            paint: {{ 'fill-color': '#000000', 'fill-opacity': 0.02 }}
                        }});
                        map.addLayer({{
                            id: 'poly-layer-line', type: 'line', source: 'poly-src',
                            paint: {{ 'line-color': '#691C32', 'line-width': 2.2, 'line-dasharray': [3, 1.5] }}
                        }});
                    }}

                    const geoData = {geojson_geo_evo_str};
                    if (geoData.features) {{
                        map.addSource('geo-src', {{ type: 'geojson', data: geoData }});
                        map.addLayer({{
                            id: 'geo-fill', type: 'fill', source: 'geo-src',
                            paint: {{ 'fill-color': ['get', 'COLOR_HEX'], 'fill-opacity': 0.5 }},
                            layout: {{ 'visibility': 'none' }}
                        }});
                        map.addLayer({{
                            id: 'geo-line', type: 'line', source: 'geo-src',
                            paint: {{ 'line-color': '#555', 'line-width': 0.5, 'line-opacity': 0.6 }},
                            layout: {{ 'visibility': 'none' }}
                        }});
                    }}

                    map.addSource('kriging-src', {{
                        type: 'image', url: 'data:image/png;base64,{img_evo_b64}', coordinates: {img_coords_json}
                    }});
                    map.addLayer({{
                        id: 'kriging-layer', type: 'raster', source: 'kriging-src',
                        paint: {{ 'raster-opacity': 0.70, 'raster-resampling': 'linear' }}
                    }});

                    map.addSource('iso-src', {{
                        type: 'image', url: 'data:image/png;base64,{img_iso_b64}', coordinates: {img_coords_json}
                    }});
                    map.addLayer({{
                        id: 'iso-layer', type: 'raster', source: 'iso-src',
                        paint: {{ 'raster-opacity': 0.95 }}
                    }});

                    map.addSource('pozos-src', {{ type: 'geojson', data: {geojson_pozos_evo_str} }});
                    map.addLayer({{
                        id: 'pozos-layer', type: 'circle', source: 'pozos-src',
                        paint: {{
                            'circle-radius': 6.5,
                            'circle-color': ['get', 'Color'],
                            'circle-stroke-width': 1.5,
                            'circle-stroke-color': '#ffffff'
                        }}
                    }});

                    if ({ 'true' if tiene_repda_pts else 'false' }) {{
                        map.addSource('repda-src', {{
                            type: 'geojson',
                            data: {geojson_repda_str}
                        }});
                        map.addLayer({{
                            id: 'repda-halo-layer', type: 'circle', source: 'repda-src',
                            paint: {{
                                'circle-radius': ['+', ['get', 'radio_px'], 1.5],
                                'circle-color': '#ffffff',
                                'circle-opacity': 0.95
                            }}
                        }});
                        map.addLayer({{
                            id: 'repda-layer', type: 'circle', source: 'repda-src',
                            paint: {{
                                'circle-radius': ['get', 'radio_px'],
                                'circle-color': ['get', 'color'],
                                'circle-opacity': 0.88,
                                'circle-stroke-width': 1.2,
                                'circle-stroke-color': '#0f172a'
                            }}
                        }});

                        map.on('click', 'repda-layer', function(e) {{
                            const p = e.features[0].properties;
                            const volFmt = p.volumen_m3 !== undefined ? Number(p.volumen_m3).toLocaleString('es-MX') : '--';
                            const volHm3 = p.volumen_hm3 !== undefined ? Number(p.volumen_hm3).toFixed(3) : '--';
                            const dhTxt = (p.dh_local !== undefined && p.dh_local !== null) ? ((p.dh_local > 0 ? '+' : '') + Number(p.dh_local).toFixed(2) + ' m') : 'Sin datos';
                            const colDiag = p.color_diagnostico || '#64748b';
                            const diagTxt = p.diagnostico_evo || 'Sin diagnóstico';

                            const html = `
                                <div style="font-family:Segoe UI, sans-serif; font-size:11.5px; min-width:215px; line-height:1.45;">
                                    <div style="font-weight:700; color:#691C32; font-size:12px; margin-bottom:4px; border-bottom:1.5px solid #691C32; padding-bottom:3px; display:flex; justify-content:space-between; align-items:center;">
                                        <span>🏢 Concesión REPDA</span>
                                        <span style="font-size:9.5px; background:${{p.color}}; color:#fff; padding:1px 5px; border-radius:3px; font-weight:600;">${{p.uso}}</span>
                                    </div>
                                    <div><b>Titular:</b> ${{p.titular}}</div>
                                    <div><b>Folio Oficial:</b> <span style="font-family:monospace; color:#334155;">${{p.folio}}</span></div>
                                    ${{p.expediente ? `<div><b>Expediente:</b> <span style="font-family:monospace; color:#475569;">${{p.expediente}}</span></div>` : ''}}
                                    ${{p.fecha ? `<div><b>Fecha Registro:</b> ${{p.fecha}}</div>` : ''}}
                                    <div><b>Volumen Concesionado:</b> <b style="color:#1e293b;">${{volFmt}} m³/año</b> (${{volHm3}} hm³/año)</div>
                                    ${{p.profundidad_m > 0 ? `<div><b>Profundidad Obra:</b> ${{p.profundidad_m}} m</div>` : ''}}
                                    <div style="margin-top:6px; padding:5px 8px; border-radius:4px; font-size:10.5px; background:#f8fafc; border-left:3px solid ${{colDiag}};">
                                        <b>Evolución Local (Δh):</b> <span style="font-weight:700; color:${{colDiag}};">${{dhTxt}}</span><br>
                                        <b>Diagnóstico Causa/Efecto:</b> <span style="font-weight:600; color:${{colDiag}};">${{diagTxt}}</span>
                                    </div>
                                    <div style="font-size:9.5px; color:#64748b; margin-top:4px; text-align:right;">
                                        Coordenadas: ${{Number(p.lat).toFixed(5)}}° N, ${{Number(p.lon).toFixed(5)}}° W
                                    </div>
                                </div>
                            `;
                            new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                                .setLngLat(e.lngLat)
                                .setHTML(html)
                                .addTo(map);
                        }});
                        map.on('mouseenter', 'repda-layer', function() {{ map.getCanvas().style.cursor = 'pointer'; }});
                        map.on('mouseleave', 'repda-layer', function() {{ map.getCanvas().style.cursor = ''; }});
                    }}

                    // REPDA Nacional Completo MVT (PMTiles 461,914 concesiones)
                    let pmtilesUrlTab2 = '{url_pmtiles_srv_tab2}';
                    if (!pmtilesUrlTab2.startsWith('http://') && !pmtilesUrlTab2.startsWith('https://')) {{
                        let baseOrigin = (window.location && window.location.origin && window.location.origin !== 'null') ? window.location.origin : '';
                        if (!baseOrigin && document.referrer) {{
                            try {{ baseOrigin = new URL(document.referrer).origin; }} catch (err) {{}}
                        }}
                        pmtilesUrlTab2 = (baseOrigin || '') + pmtilesUrlTab2;
                    }}
                    map.addSource('repda-nacional-src', {{
                        type: 'vector',
                        url: 'pmtiles://' + pmtilesUrlTab2,
                        minzoom: 4,
                        maxzoom: 8
                    }});
                    map.addLayer({{
                        id: 'repda-nacional-layer',
                        type: 'circle',
                        source: 'repda-nacional-src',
                        'source-layer': 'repda',
                        maxzoom: { '11' if tiene_repda_pts else '24' },
                        layout: {{ 'visibility': 'none' }},
                        paint: {{
                            'circle-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                4, 1.2,
                                7, 2.5,
                                10, 4.5,
                                14, 7.5
                            ],
                            'circle-color': [
                                'match', ['get', 'u'],
                                'AGRICOLA', '#16a34a',
                                'PUBLICO URBANO', '#2563eb',
                                'DOMESTICO', '#0284c7',
                                'INDUSTRIAL', '#dc2626',
                                'SERVICIOS', '#9333ea',
                                'PECUARIO', '#ca8a04',
                                'DIFERENTES USOS', '#0d9488',
                                'ACUACULTURA', '#06b6d4',
                                'AGROINDUSTRIAL', '#65a30d',
                                'COMERCIO', '#ea580c',
                                'ENERGIA ELECTRICA', '#eab308',
                                /* default */ '#475569'
                            ],
                            'circle-opacity': 0.85,
                            'circle-stroke-width': [
                                'interpolate', ['linear'], ['zoom'],
                                4, 0,
                                8, 0.4,
                                11, 1.0
                            ],
                            'circle-stroke-color': '#ffffff'
                        }}
                    }});

                    map.on('click', 'repda-nacional-layer', function(e) {{
                        const p = e.features[0].properties;
                        const volM3 = p.v ? Number(p.v).toLocaleString('es-MX') : '--';
                        const volHm3 = p.v ? (Number(p.v) / 1e6).toFixed(3) : '--';
                        const latFmt = p.la !== undefined ? Number(p.la).toFixed(5) : e.lngLat.lat.toFixed(5);
                        const lonFmt = p.lo !== undefined ? Number(p.lo).toFixed(5) : e.lngLat.lng.toFixed(5);
                        new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                            .setLngLat(e.lngLat)
                            .setHTML(`
                                <div style="font-family:Segoe UI,sans-serif; font-size:11.5px; min-width:220px; line-height:1.45;">
                                    <div style="font-weight:700; color:#166534; font-size:12px; margin-bottom:4px; border-bottom:1.5px solid #166534; padding-bottom:3px; display:flex; justify-content:space-between; align-items:center;">
                                        <span>🇲🇽 Concesión REPDA Nacional</span>
                                        <span style="font-size:10px; background:#f1f5f9; color:#475569; padding:1px 5px; border-radius:4px;">${{p.f || '--'}}</span>
                                    </div>
                                    <div style="margin-bottom:3px;"><b>Titular:</b> <span style="color:#0f172a; font-weight:600;">${{p.t || '--'}}</span></div>
                                    ${{p.e ? `<div style="margin-bottom:2px;"><b>Expediente:</b> ${{p.e}}</div>` : ''}}
                                    <div style="margin-bottom:2px;"><b>Uso:</b> <span style="background:#f0fdf4; color:#166534; font-weight:700; padding:1px 5px; border-radius:3px; border:1px solid #bbf7d0;">${{p.u || '--'}}</span></div>
                                    <div style="margin-bottom:2px;"><b>Volumen Anual:</b> <b>${{volM3}}</b> m³/año (${{volHm3}} hm³/año)</div>
                                    <div style="font-size:9.5px; color:#64748b; margin-top:4px;">Coordenadas: ${{latFmt}}° N, ${{lonFmt}}° W</div>
                                </div>
                            `)
                            .addTo(map);
                    }});
                    map.on('mouseenter', 'repda-nacional-layer', function() {{ map.getCanvas().style.cursor = 'pointer'; }});
                    map.on('mouseleave', 'repda-nacional-layer', function() {{ map.getCanvas().style.cursor = ''; }});

                    if (polyBounds) {{
                        map.fitBounds([[polyBounds[0], polyBounds[1]], [polyBounds[2], polyBounds[3]]], {{ padding: 35 }});
                    }}
                }});

                const selBasemap = document.getElementById('sel-basemap');
                if (selBasemap) {{
                    selBasemap.addEventListener('change', (e) => {{
                        const selected = e.target.value;
                        const basemaps = ['base-light-layer', 'base-sat-layer', 'base-topo-layer', 'base-osm-layer', 'base-street-layer', 'base-terrain-layer', 'base-ocean-layer', 'base-dark-layer', 'base-google-layer'];
                        basemaps.forEach(id => {{
                            if (map.getLayer(id)) {{
                                map.setLayoutProperty(id, 'visibility', id === selected ? 'visible' : 'none');
                            }}
                        }});
                    }});
                }}

                function cambiarOpacidadEvo(val) {{
                    const el = document.getElementById('val-opac');
                    if (el) el.innerText = Math.round(val * 100) + '%';
                    if (map.getLayer('kriging-layer')) {{
                        map.setPaintProperty('kriging-layer', 'raster-opacity', parseFloat(val));
                    }}
                }}

                function cambiarOpacidadGeologia(val) {{
                    const elVal = document.getElementById('val-opac-geo');
                    if (elVal) elVal.innerText = Math.round(val * 100) + '%';
                    if (map.getLayer('geo-fill')) {{
                        map.setPaintProperty('geo-fill', 'fill-opacity', parseFloat(val));
                    }}
                }}

                const toggleLayerEvo = (chkId, layerIds, legId = null) => {{
                    const chk = document.getElementById(chkId);
                    if (chk) {{
                        chk.addEventListener('change', (e) => {{
                            const vis = e.target.checked ? 'visible' : 'none';
                            layerIds.forEach(id => {{
                                if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
                            }});
                            if (legId) {{
                                const leg = document.getElementById(legId);
                                if (leg) leg.style.display = e.target.checked ? 'block' : 'none';
                            }}
                        }});
                    }}
                }};

                toggleLayerEvo('chk-kriging', ['kriging-layer']);
                toggleLayerEvo('chk-iso', ['iso-layer']);
                toggleLayerEvo('chk-pozos', ['pozos-layer'], 'leg-pozos');
                toggleLayerEvo('chk-poly', ['poly-layer-line', 'poly-layer-fill'], 'leg-poly');
                toggleLayerEvo('chk-repda', ['repda-halo-layer', 'repda-layer'], 'leg-repda');
                toggleLayerEvo('chk-repda-nac', ['repda-nacional-layer'], 'leg-repda-nac');
                toggleLayerEvo('chk-geo', ['geo-fill', 'geo-line'], 'leg-geo');

                const chkGeo = document.getElementById('chk-geo');
                if (chkGeo) {{
                    chkGeo.addEventListener('change', (e) => {{
                        const secOpacGeo = document.getElementById('sec-opac-geo');
                        if (secOpacGeo) secOpacGeo.style.display = e.target.checked ? 'block' : 'none';
                    }});
                }}

                map.on('click', 'geo-fill', (e) => {{
                    const puntosClickeados = map.queryRenderedFeatures(e.point, {{
                        layers: ['pozos-layer', 'repda-layer', 'repda-nacional-layer'].filter(id => map.getLayer(id))
                    }});
                    if (puntosClickeados.length > 0) return;

                    const p = e.features[0].properties;
                    const formacion = (p.FORMACION && p.FORMACION !== 'null' && p.FORMACION !== 'NINGUNO') ? p.FORMACION : 'Formación No Asignada';
                    const claveSgm = p["{col_sel_geo_evo}"] || p.ETIQUETA_LITO || 'S/C';
                    const litologia = p.LITOLOGIA || 'Indiferenciada';
                    const roca = p.ROCA || 'Sedimentaria';
                    const colorHex = p.COLOR_HEX || '#B0BEC5';
                    
                    let edadGeo = p.PERIODO || '';
                    if (p.EDINICIO || p.EDFINAL) {{
                        const ini = p.EDINICIO || '';
                        const fin = p.EDFINAL || '';
                        edadGeo += (ini === fin || !fin) ? ` (${{ini}})` : ` (${{ini}} - ${{fin}})`;
                    }}
                    if (!edadGeo.trim()) edadGeo = p.ERA || 'S/D';

                    let html = `
                        <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; line-height:1.5; min-width:200px;">
                            <div style="display:flex; align-items:center; justify-content:space-between; border-bottom:1.5px solid #E2E8F0; padding-bottom:4px; margin-bottom:6px;">
                                <div style="display:flex; align-items:center; gap:6px;">
                                    <span style="width:13px; height:13px; background:${{colorHex}}; border-radius:3px; border:1px solid #475569; display:inline-block;"></span>
                                    <h4 style="margin:0; color:#691C32; font-size:13px; font-weight:700;">${{formacion}}</h4>
                                </div>
                                <span style="background:#F1F5F9; border:1px solid #CBD5E1; color:#334155; font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:3px;">${{claveSgm}}</span>
                            </div>
                            <b>Litología:</b> <span style="color:#0f172a; font-weight:600;">${{litologia}}</span><br>
                            <b>Tipo de Roca:</b> ${{roca}}<br>
                            <b>Edad Geológica:</b> ${{edadGeo}}<br>
                            <span style="color:#64748B; font-size:10px;">Coords: ${{e.lngLat.lat.toFixed(4)}}°, ${{e.lngLat.lng.toFixed(4)}}°</span>
                        </div>
                    `;
                    new maplibregl.Popup({{ className: 'gis-badge-popup' }}).setLngLat(e.lngLat).setHTML(html).addTo(map);
                }});
                map.on('mouseenter', 'geo-fill', () => {{ map.getCanvas().style.cursor = 'pointer'; }});
                map.on('mouseleave', 'geo-fill', () => {{ map.getCanvas().style.cursor = ''; }});

                map.on('mousemove', (e) => {{
                    document.getElementById('hud-lon').innerText = e.lngLat.lng.toFixed(5) + '°';
                    document.getElementById('hud-lat').innerText = e.lngLat.lat.toFixed(5) + '°';
                    const lat = e.lngLat.lat, lng = e.lngLat.lng;
                    if (lat >= min_y && lat <= max_y && lng >= min_x && lng <= max_x) {{
                        let r = Math.floor(((lat - min_y) / (max_y - min_y)) * (rows - 1));
                        let c = Math.floor(((lng - min_x) / (max_x - min_x)) * (cols - 1));
                        r = Math.max(0, Math.min(rows - 1, r));
                        c = Math.max(0, Math.min(cols - 1, c));
                        const val = z_data[r][c];
                        if (val !== null) {{
                            document.getElementById('hud-ele').innerText = (val > 0 ? '+' : '') + val.toFixed(2) + ' m';
                            document.getElementById('hud-ele').style.color = val < 0 ? '#990000' : (val > 0 ? '#0055AA' : '#2C3E50');
                        }} else {{
                            document.getElementById('hud-ele').innerText = '--';
                        }}
                    }} else {{
                        document.getElementById('hud-ele').innerText = '--';
                    }}
                }});

                map.on('click', 'pozos-layer', function(e) {{
                    const p = e.features[0].properties;
                    const html = `
                        <div style="font-family:Segoe UI, sans-serif; font-size:11.5px; min-width:190px;">
                            <div style="font-weight:700; color:#691C32; font-size:12px; margin-bottom:4px; border-bottom:1px solid #e2e8f0; padding-bottom:2px;">
                                📍 Pozo: ${{p.Pozo}}
                            </div>
                            <div><b>Carga ${{p.Carga_{anio_t1}_msnm !== undefined ? '{anio_t1}' : ''}}:</b> ${{p.Carga_{anio_t1}_msnm}} msnm</div>
                            <div><b>Carga ${{p.Carga_{anio_t2}_msnm !== undefined ? '{anio_t2}' : ''}}:</b> ${{p.Carga_{anio_t2}_msnm}} msnm</div>
                            <div style="margin-top:5px; padding-top:4px; border-top:1px dashed #cbd5e1;">
                                <b>Evolución Total (Δh):</b> <span style="font-weight:700; color:${{p.Delta_h_m < 0 ? '#990000' : '#0055aa'}};">${{p.Delta_h_m}} m</span><br>
                                <b>Tasa Anual:</b> ${{p.Tasa_m_anio}} m/año<br>
                                <b>Condición:</b> <span style="font-weight:600;">${{p.Condicion}}</span>
                            </div>
                        </div>
                    `;
                    new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                        .setLngLat(e.lngLat)
                        .setHTML(html)
                        .addTo(map);
                }});

                map.on('mouseenter', 'pozos-layer', function() {{ map.getCanvas().style.cursor = 'pointer'; }});
                map.on('mouseleave', 'pozos-layer', function() {{ map.getCanvas().style.cursor = ''; }});

                const legContenedor = document.querySelector('.legend-panel');
                if (legContenedor) {{
                    legContenedor.addEventListener('keydown', function(e) {{ e.stopPropagation(); }});
                    legContenedor.addEventListener('keyup', function(e) {{ e.stopPropagation(); }});
                    legContenedor.addEventListener('keypress', function(e) {{ e.stopPropagation(); }});
                }}
            </script>
        </body>
        </html>
        """
        components.html(html_maplibre_evo, height=650)

        st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)
        col_an1, col_an2 = st.columns([1.15, 1.85], gap="large")

        with col_an1:
            st.markdown("<p style='font-weight:700; color:#691C32; margin-bottom:6px; font-size:13px;'>🚨 NÚCLEOS Y CONOS DE ABATIMIENTO ACTIVO</p>", unsafe_allow_html=True)
            if not df_pz_evo.empty:
                df_conos = df_pz_evo[df_pz_evo['Delta_h_m'] < 0].sort_values(by='Delta_h_m', ascending=True)
                if not df_conos.empty:
                    df_tabla_conos = df_conos[['Pozo', f'Carga_{anio_t1}_msnm', f'Carga_{anio_t2}_msnm', 'Delta_h_m', 'Tasa_m_anio', 'Condicion']].copy()
                    df_tabla_conos.columns = ['Pozo', f'Carga {anio_t1}', f'Carga {anio_t2}', 'Δh (m)', 'Tasa (m/año)', 'Severidad']
                    st.dataframe(df_tabla_conos, use_container_width=True, hide_index=True, height=260)
                else:
                    st.success("🎉 No se registraron conos de abatimiento ni descensos piezométricos en los pozos evaluados.")
            else:
                st.info("Sin pozos coincidentes entre ambos años seleccionados.")

        with col_an2:
            st.markdown("<p style='font-weight:700; color:#691C32; margin-bottom:6px; font-size:13px;'>📊 DISTRIBUCIÓN SUPERFICIAL POR RANGO DE EVOLUCIÓN</p>", unsafe_allow_html=True)
            if len(delta_vals) > 0:
                categorias = [
                    ("Crítico (< -15 m)", np.sum(delta_vals < -15.0) * dA_km2, "#780016"),
                    ("Severo (-15 a -10 m)", np.sum((delta_vals >= -15.0) & (delta_vals < -10.0)) * dA_km2, "#a8112c"),
                    ("Moderado (-10 a -5 m)", np.sum((delta_vals >= -10.0) & (delta_vals < -5.0)) * dA_km2, "#d9534f"),
                    ("Leve (-5 a -1 m)", np.sum((delta_vals >= -5.0) & (delta_vals < -1.0)) * dA_km2, "#f0ad4e"),
                    ("Equilibrio (-1 a +1 m)", np.sum((delta_vals >= -1.0) & (delta_vals <= 1.0)) * dA_km2, "#94a3b8"),
                    ("Recuperación (> +1 m)", np.sum(delta_vals > 1.0) * dA_km2, "#0275d8")
                ]
                df_dist = pd.DataFrame([{
                    "Rango": c[0],
                    "Área (km²)": round(c[1], 1),
                    "Porcentaje (%)": round((c[1] / area_total_km2 * 100.0) if area_total_km2 > 0 else 0, 1),
                    "Color": c[2]
                } for c in categorias])

                fig_dist = px.bar(
                    df_dist, x="Área (km²)", y="Rango", orientation="h",
                    text="Área (km²)", color="Rango",
                    color_discrete_map={row["Rango"]: row["Color"] for _, row in df_dist.iterrows()}
                )
                fig_dist.update_layout(
                    height=260, margin=dict(l=10, r=20, t=10, b=10),
                    showlegend=False, yaxis=dict(autorange="reversed"),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
                )
                fig_dist.update_traces(texttemplate='%{text:,.1f} km²', textposition='outside')
                st.plotly_chart(fig_dist, use_container_width=True)

        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<p style='font-weight:700; color:#691C32; margin-bottom:8px; font-size:13px;'>💾 EXPORTACIÓN DE RESULTADOS SIG Y TABULARES (CERO-RERUN)</p>", unsafe_allow_html=True)
            c_d1, c_d2, c_d3, c_d4, c_d5 = st.columns(5)

            btn_tif = generar_enlace_descarga(
                geotiff_evo_bytes, f"geotiff_delta_h_{clave_actual}_{anio_t1}_{anio_t2}.tif",
                "image/tiff", "🗺️ GeoTIFF Δh (Ráster 32-bit)"
            )
            c_d1.markdown(btn_tif, unsafe_allow_html=True)

            if shp_iso_zip:
                btn_shp = generar_enlace_descarga(
                    shp_iso_zip, f"isolineas_delta_h_{clave_actual}_{anio_t1}_{anio_t2}.zip",
                    "application/zip", "📦 Shapefile ZIP Isolíneas"
                )
                c_d2.markdown(btn_shp, unsafe_allow_html=True)
            else:
                c_d2.info("SHP no disponible")

            btn_json = generar_enlace_descarga(
                geojson_iso_bytes, f"isolineas_delta_h_{clave_actual}_{anio_t1}_{anio_t2}.geojson",
                "application/json", "🌐 GeoJSON Isolíneas"
            )
            c_d3.markdown(btn_json, unsafe_allow_html=True)

            if not df_pz_evo.empty:
                csv_bytes = df_pz_evo.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                btn_csv = generar_enlace_descarga(
                    csv_bytes, f"diagnostico_pozos_delta_h_{clave_actual}_{anio_t1}_{anio_t2}.csv",
                    "text/csv", "📊 CSV Diagnóstico Pozos"
                )
                c_d4.markdown(btn_csv, unsafe_allow_html=True)
            else:
                c_d4.info("Sin pozos a exportar")

            kmz_evo_bytes = generar_kmz_evolucion(
                clave_actual, nombre_actual, anio_t1, anio_t2,
                bounds, img_evo_png, geojson_iso_bytes,
                df_pz_evo, delim_geom=delim_geom, resumen_repda=resumen_repda,
                geojson_repda_str=geojson_repda_str if tiene_repda_pts else None,
                geojson_geo=geojson_geo_evo_str
            )
            btn_kmz_evo = generar_enlace_descarga(
                kmz_evo_bytes, f"evolucion_delta_h_{clave_actual}_{anio_t1}_{anio_t2}.kmz",
                "application/vnd.google-earth.kmz", "🌐 Paquete KMZ (Google Earth)"
            )
            c_d5.markdown(btn_kmz_evo, unsafe_allow_html=True)

        # =======================================================
        # 🏢 INCISO D: CORRELACIÓN ESPACIAL CAUSA VS EFECTO (REPDA)
        # =======================================================
        st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)
        st.markdown("""
            <div style="background-color: #f8fafc; border-left: 4px solid #166534; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
                <span style="font-weight: 700; color: #166534; font-size: 13.5px;">🏢 CORRELACIÓN ESPACIAL CAUSA VS EFECTO (EXTRACCIONES REPDA VS ABATIMIENTOS)</span><br>
                <span style="font-size: 11.5px; color: #475569;">
                    Contraste geohidrológico entre los volúmenes de extracción concesionados (Causa: bombeo registrado en el REPDA)
                    y el abatimiento piezométrico observado en el acuífero (Efecto: conos de depresión y descenso de carga Δh).
                </span>
            </div>
        """, unsafe_allow_html=True)

        with st.container(border=True):
            r_c1, r_c2, r_c3, r_c4 = st.columns(4)
            
            vol_oficial_hm3 = resumen_repda.get("volumen_total_hm3", 0.0) if resumen_repda else 0.0
            tot_aprov = resumen_repda.get("total_aprovechamientos", 0) if resumen_repda else 0
            uso_max = resumen_repda.get("uso_predominante", "N/D") if resumen_repda else "N/D"
            pct_max = resumen_repda.get("pct_predominante", 0.0) if resumen_repda else 0.0

            r_c1.metric(
                "Volumen Concesionado Oficial",
                f"{vol_oficial_hm3:,.2f} hm³/año",
                f"{tot_aprov} captaciones censadas (CONAGUA)",
                delta_color="off",
                help="Volumen total de derechos de extracción de aguas subterráneas inscritos en el REPDA para este acuífero."
            )

            vol_abat_hm3 = vol_en_abatimiento_m3 / 1e6
            r_c2.metric(
                "Extracción en Conos Activos",
                f"{vol_abat_hm3:,.2f} hm³/año",
                f"{pct_vol_en_abat:.1f}% del volumen muestreado",
                delta_color="inverse" if pct_vol_en_abat > 50 else "normal",
                help="Volumen concesionado cuyos pozos caen en sectores con descenso piezométrico activo (Δh < -0.1 m)."
            )

            r_c3.metric(
                "Aprovechamientos en Abatimiento",
                f"{n_repda_en_abat} de {n_repda_total} pozos",
                f"{pct_pozos_en_abat:.1f}% de las captaciones",
                delta_color="inverse" if pct_pozos_en_abat > 50 else "normal",
                help="Número de captaciones georreferenciadas que coinciden espacialmente con conos de depresión."
            )

            r_c4.metric(
                "Uso Predominante",
                f"{uso_max}",
                f"{pct_max:.1f}% del volumen concesionado",
                delta_color="off",
                help="Uso consuntivo con mayor asignación volumétrica de aguas subterráneas en el acuífero."
            )

        if tiene_repda_pts:
            if pct_vol_en_abat >= 60.0:
                diag_box_bg = "#fef2f2"
                diag_box_border = "#dc2626"
                diag_box_txt = "#991b1b"
                icono_diag = "🚨"
                dictamen = f"<b>ALTA CONCENTRACIÓN CAUSAL:</b> El <b>{pct_vol_en_abat:.1f}%</b> del volumen concesionado muestreado ({vol_abat_hm3:,.2f} hm³/año) se concentra en zonas con abatimiento piezométrico activo (Δh &lt; -0.1 m). Los centros de bombeo del uso <b>{uso_max}</b> actúan como inductores geométricos directos de los conos de depresión identificados."
            elif pct_vol_en_abat >= 30.0:
                diag_box_bg = "#fffbeb"
                diag_box_border = "#d97706"
                diag_box_txt = "#92400e"
                icono_diag = "⚠️"
                dictamen = f"<b>CORRELACIÓN MODERADA:</b> El <b>{pct_vol_en_abat:.1f}%</b> del volumen concesionado ({vol_abat_hm3:,.2f} hm³/año) opera en sectores con descensos piezométricos. Existe correspondencia espacial entre los núcleos de extracción y la formación de gradientes convergentes."
            else:
                diag_box_bg = "#f0fdf4"
                diag_box_border = "#16a34a"
                diag_box_txt = "#166534"
                icono_diag = "⚖️"
                dictamen = f"<b>CORRELACIÓN DISPERSA O EN EQUILIBRIO:</b> Solo el <b>{pct_vol_en_abat:.1f}%</b> del volumen concesionado evaluado coincide con áreas de descenso piezométrico. El acuífero presenta áreas de extracción con amortiguamiento hidrogeológico o recarga localizada."

            st.markdown(f"""
                <div style="background-color: {diag_box_bg}; border-left: 4px solid {diag_box_border}; padding: 10px 14px; border-radius: 6px; margin: 10px 0; color: {diag_box_txt}; font-size: 12px; line-height: 1.5;">
                    <span style="font-size: 14px; margin-right: 6px;">{icono_diag}</span>{dictamen}
                </div>
            """, unsafe_allow_html=True)

        col_rep1, col_rep2 = st.columns([1.15, 1.85], gap="large")
        with col_rep1:
            st.markdown("<p style='font-weight:700; color:#166534; margin-bottom:6px; font-size:13px;'>📋 DISTRIBUCIÓN OFICIAL POR TIPO DE USO (CONAGUA)</p>", unsafe_allow_html=True)
            if resumen_repda and not resumen_repda["df_usos"].empty:
                df_u_show = resumen_repda["df_usos"][["Uso", "Volumen_hm3", "Pct_Volumen"]].copy()
                df_u_show.columns = ["Uso", "Volumen (hm³/año)", "% Total"]
                df_u_show["Volumen (hm³/año)"] = df_u_show["Volumen (hm³/año)"].apply(lambda x: f"{x:,.2f}")
                df_u_show["% Total"] = df_u_show["% Total"].apply(lambda x: f"{x:.1f}%")
                st.dataframe(df_u_show, use_container_width=True, hide_index=True, height=240)
            else:
                st.info("No se encontró desglose volumétrico por uso en el registro REPDA para este acuífero.")

        with col_rep2:
            st.markdown("<p style='font-weight:700; color:#166534; margin-bottom:6px; font-size:13px;'>📊 ESTRUCTURA VOLUMÉTRICA DE LA EXTRACCIÓN SUBTERRÁNEA</p>", unsafe_allow_html=True)
            if resumen_repda and not resumen_repda["df_usos"].empty:
                df_plot_u = resumen_repda["df_usos"].copy()
                fig_rep_u = px.bar(
                    df_plot_u, x="Volumen_hm3", y="Uso", orientation="h",
                    text="Volumen_hm3", color="Uso",
                    color_discrete_map={
                        row["Uso"]: get_repda_uso_color(row["Uso"]) for _, row in df_plot_u.iterrows()
                    }
                )
                fig_rep_u.update_layout(
                    height=240, margin=dict(l=10, r=20, t=10, b=10),
                    showlegend=False, yaxis=dict(autorange="reversed"),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)"
                )
                fig_rep_u.update_traces(texttemplate='%{text:,.2f} hm³', textposition='outside')
                st.plotly_chart(fig_rep_u, use_container_width=True)
            else:
                st.info("Sin datos para graficar la distribución de usos.")

        if tiene_repda_pts:
            st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
            geojson_repda_bytes = geojson_repda_str.encode('utf-8')
            btn_repda_json = generar_enlace_descarga(
                geojson_repda_bytes, f"concesiones_repda_{clave_actual}.geojson",
                "application/json", "🏢 Descargar Concesiones REPDA con Diagnóstico Δh (GeoJSON)"
            )
            st.markdown(btn_repda_json, unsafe_allow_html=True)

    renderizar_pestaña_evolucion()

# =======================================================
# 🎯 INCISO C: DIAGNÓSTICO DE ZONAS CIEGAS Y COBERTURA DE LA RED
# =======================================================
def calcular_cobertura_y_zonas_ciegas(df_pozos, radio_km, geom_acuifero, min_area_vacio_km2=25.0):
    import pyproj
    from shapely.geometry import Point, Polygon, MultiPolygon
    from shapely.ops import unary_union, transform

    if df_pozos is None or df_pozos.empty or geom_acuifero is None:
        return None

    centro_lon = float(geom_acuifero.centroid.x)
    centro_lat = float(geom_acuifero.centroid.y)

    utm_zone = int((centro_lon + 180) / 6) + 1
    epsg_utm = 32600 + utm_zone if centro_lat >= 0 else 32700 + utm_zone

    to_utm = pyproj.Transformer.from_crs('EPSG:4326', f'EPSG:{epsg_utm}', always_xy=True).transform
    to_wgs = pyproj.Transformer.from_crs(f'EPSG:{epsg_utm}', 'EPSG:4326', always_xy=True).transform

    try:
        poly_acuifero_utm = transform(to_utm, geom_acuifero)
    except Exception:
        return None

    area_total_km2 = float(poly_acuifero_utm.area / 1e6)
    if area_total_km2 <= 0:
        return None

    radio_m = float(radio_km) * 1000.0
    bufs_utm_list = []

    df_unicos = df_pozos.dropna(subset=['Longitud', 'Latitud']).drop_duplicates(subset=['Longitud', 'Latitud'])
    if df_unicos.empty:
        return None

    for _, r in df_unicos.iterrows():
        try:
            p_utm = transform(to_utm, Point(float(r['Longitud']), float(r['Latitud'])))
            bufs_utm_list.append(p_utm.buffer(radio_m, quad_segs=16))
        except Exception:
            continue

    if not bufs_utm_list:
        return None

    union_bufs_utm = unary_union(bufs_utm_list)

    try:
        cubierta_utm = poly_acuifero_utm.intersection(union_bufs_utm)
    except Exception:
        cubierta_utm = Polygon()

    try:
        ciega_utm = poly_acuifero_utm.difference(union_bufs_utm)
    except Exception:
        ciega_utm = Polygon()

    area_cubierta_km2 = float(cubierta_utm.area / 1e6) if (cubierta_utm and not cubierta_utm.is_empty) else 0.0
    area_ciega_km2 = float(ciega_utm.area / 1e6) if (ciega_utm and not ciega_utm.is_empty) else 0.0

    pct_cubierta = (area_cubierta_km2 / area_total_km2 * 100.0) if area_total_km2 > 0 else 0.0
    pct_ciega = (area_ciega_km2 / area_total_km2 * 100.0) if area_total_km2 > 0 else 0.0

    cubierta_wgs = transform(to_wgs, cubierta_utm) if (cubierta_utm and not cubierta_utm.is_empty) else None
    ciega_wgs = transform(to_wgs, ciega_utm) if (ciega_utm and not ciega_utm.is_empty) else None

    propuestas = []
    if ciega_utm and not ciega_utm.is_empty:
        geoms_ciegas = [ciega_utm] if ciega_utm.geom_type == 'Polygon' else [g for g in ciega_utm.geoms if g.geom_type in ['Polygon', 'MultiPolygon']]
        geoms_ordenadas = sorted(geoms_ciegas, key=lambda g: g.area, reverse=True)

        pts_pozos_utm = [transform(to_utm, Point(float(r['Longitud']), float(r['Latitud']))) for _, r in df_unicos.iterrows()]

        idx_p = 1
        for g_vacio in geoms_ordenadas:
            a_vacio_km2 = float(g_vacio.area / 1e6)
            if a_vacio_km2 >= float(min_area_vacio_km2):
                p_rep_utm = g_vacio.representative_point()
                p_rep_wgs = transform(to_wgs, p_rep_utm)

                d_min_m = min([p_rep_utm.distance(p_exist) for p_exist in pts_pozos_utm]) if pts_pozos_utm else 0.0
                d_min_km = d_min_m / 1000.0

                if a_vacio_km2 >= 150.0 or d_min_km >= radio_km * 2.5:
                    prioridad = "Muy Alta"
                elif a_vacio_km2 >= 75.0 or d_min_km >= radio_km * 1.8:
                    prioridad = "Alta"
                elif a_vacio_km2 >= 35.0:
                    prioridad = "Media"
                else:
                    prioridad = "Moderada"

                propuestas.append({
                    'ID': f"PROP-{idx_p:02d}",
                    'Longitud': round(float(p_rep_wgs.x), 5),
                    'Latitud': round(float(p_rep_wgs.y), 5),
                    'Area_Vacio_km2': round(a_vacio_km2, 1),
                    'Dist_Pozo_km': round(d_min_km, 1),
                    'Prioridad': prioridad
                })
                idx_p += 1

    df_propuestas = pd.DataFrame(propuestas)

    n_pozos = len(df_unicos)
    densidad_pozos_1000km2 = (n_pozos / area_total_km2 * 1000.0) if area_total_km2 > 0 else 0.0
    km2_por_pozo = (area_total_km2 / n_pozos) if n_pozos > 0 else 0.0

    if pct_cubierta >= 70.0:
        diagnostico_txt = "Cobertura Alta (Suficiente)"
        color_diag = "#166534"
    elif pct_cubierta >= 45.0:
        diagnostico_txt = "Cobertura Moderada (Aceptable)"
        color_diag = "#b45309"
    else:
        diagnostico_txt = "Cobertura Deficiente (Crítica)"
        color_diag = "#991b1b"

    return {
        'area_total_km2': area_total_km2,
        'area_cubierta_km2': area_cubierta_km2,
        'area_ciega_km2': area_ciega_km2,
        'pct_cubierta': pct_cubierta,
        'pct_ciega': pct_ciega,
        'n_pozos': n_pozos,
        'densidad_1000km2': densidad_pozos_1000km2,
        'km2_por_pozo': km2_por_pozo,
        'diagnostico': diagnostico_txt,
        'color_diagnostico': color_diag,
        'cubierta_wgs': cubierta_wgs,
        'ciega_wgs': ciega_wgs,
        'df_propuestas': df_propuestas,
        'epsg_utm': epsg_utm
    }

with tab_cobertura:
    @st.fragment
    def renderizar_pestaña_cobertura():
        st.markdown("""
            <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
                <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">🎯 DIAGNÓSTICO DE COBERTURA Y DETECCIÓN DE ZONAS CIEGAS DE LA RED PIEZOMÉTRICA</span><br>
                <span style="font-size: 11.5px; color: #475569;">
                    Evaluación geoespacial de la representatividad espacial de los pozos de observación conforme a las directrices de la CONAGUA y la Guía de Prácticas Hidrológicas de la OMM (Nº 168).
                    Identifica vacíos de monitoreo (zonas ciegas) e infiere ubicaciones óptimas para la densificación o expansión de la red de monitoreo.
                </span>
            </div>
        """, unsafe_allow_html=True)

        anios_disp_cob = sorted([int(a) for a in df_ac['Año'].dropna().unique().tolist()])
        opciones_anios = ["Todos los Pozos Históricos"] + [str(a) for a in anios_disp_cob[::-1]]

        geom_oficial = st.session_state.get("poligono_personalizado", None)
        if geom_oficial is None:
            geom_oficial = poligono_oficial_geom

        opciones_delimitacion = ["Pozos de Monitoreo (Envolvente Convexa)"]
        if geom_oficial is not None:
            opciones_delimitacion.insert(0, "Polígono Oficial del Acuífero")

        with st.container(border=True):
            c_c1, c_c2, c_c3, c_c4 = st.columns([1.2, 1.4, 1.4, 1.1])
            sel_conjunto = c_c1.selectbox("Conjunto de Pozos:", opciones_anios, index=0, key="sel_cob_conjunto")
            radio_km = c_c2.selectbox(
                "Radio de Representatividad (R):",
                [2.5, 5.0, 7.5, 10.0, 15.0, 20.0],
                index=1,
                format_func=lambda x: f"{x:.1f} km (Diámetro: {x*2:.0f} km)",
                key="sel_cob_radio",
                help="Radio de representatividad piezométrica. CONAGUA/OMM recomiendan 3-5 km en acuíferos sobreexplotados y 5-10 km en monitoreo regional."
            )
            modo_delim = c_c3.selectbox(
                "Delimitar Acuífero por:",
                opciones_delimitacion,
                index=0,
                key="sel_cob_delim"
            )
            min_vacio = c_c4.selectbox(
                "Umbral Vacío Crítico:",
                [10, 25, 50, 100],
                index=1,
                format_func=lambda x: f"> {x} km²",
                key="sel_cob_umbral_vacio",
                help="Superficie mínima contigua de zona ciega para clasificarla como candidato prioritario a nuevo pozo."
            )

        if sel_conjunto == "Todos los Pozos Históricos":
            df_pozos_cob = df_ac.sort_values(by='Año').groupby('Pozo').last().reset_index()
        else:
            anio_target = int(sel_conjunto)
            df_pozos_cob = obtener_red_sincronizada(df_ac, anio_target, var_nombre='Carga_Hidraulica', modo='interpolado')

        if df_pozos_cob.empty:
            st.warning("⚠️ No se encontraron pozos válidos para el conjunto seleccionado.")
            return

        df_unicos = df_pozos_cob.dropna(subset=['Longitud', 'Latitud']).drop_duplicates(subset=['Longitud', 'Latitud'])

        if modo_delim == "Polígono Oficial del Acuífero" and geom_oficial is not None:
            geom_activa = geom_oficial
        else:
            x_pozos = df_unicos['Longitud'].values
            y_pozos = df_unicos['Latitud'].values
            try:
                hull = ConvexHull(np.column_stack((x_pozos, y_pozos)))
                hull_pts = np.column_stack((x_pozos[hull.vertices], y_pozos[hull.vertices]))
                hull_loop = np.vstack([hull_pts, hull_pts[0]])
                geom_activa = Polygon(hull_loop)
            except Exception:
                geom_activa = None

        if geom_activa is None:
            st.warning("⚠️ No se pudo determinar el polígono del acuífero para la delimitación.")
            return

        with st.spinner("Analizando representatividad espacial y calculando zonas ciegas..."):
            res = calcular_cobertura_y_zonas_ciegas(df_unicos, radio_km, geom_activa, min_vacio)

        if res is None:
            st.error("No se pudo calcular la cobertura espacial con la geometría proporcionada.")
            return

        st.session_state[f"res_cob_{clave_actual}"] = res

        with st.container(border=True):
            m1, m2, m3, m4 = st.columns(4)
            m1.metric(
                "Superficie Monitoreada",
                f"{res['area_cubierta_km2']:,.1f} km²",
                f"{res['pct_cubierta']:.1f}% de cobertura",
                delta_color="normal" if res['pct_cubierta'] >= 60 else "inverse",
                help="Área del acuífero ubicada dentro del radio de influencia hidrogeológica de al menos un pozo de monitoreo."
            )
            m2.metric(
                "Superficie en Zona Ciega",
                f"{res['area_ciega_km2']:,.1f} km²",
                f"{res['pct_ciega']:.1f}% desatendido",
                delta_color="inverse" if res['pct_ciega'] > 40 else "normal",
                help="Superficie del acuífero desprovista de pozos de observación activos. La interpolación en estas áreas extrapola con alta incertidumbre."
            )
            m3.metric(
                "Densidad de la Red",
                f"{res['densidad_1000km2']:.2f} pozos / 1000 km²",
                f"1 pozo cada {res['km2_por_pozo']:.1f} km²",
                help="Densidad media de pozos de monitoreo en relación con la superficie acuífera."
            )
            m4.metric(
                "Diagnóstico OMM y Vacíos",
                f"{len(res['df_propuestas'])} vacíos críticos",
                res['diagnostico'],
                delta_color="normal" if res['pct_cubierta'] >= 60 else "inverse",
                help="Número de núcleos o vacíos territoriales prioritarios detectados donde se sugiere densificar la red."
            )

        # Preparación GeoJSON
        gdf_ac_poly = gpd.GeoDataFrame([{'NOMBRE': 'Acuífero'}], geometry=[geom_activa], crs="EPSG:4326")
        geojson_acuifero_str = gdf_ac_poly.to_json()

        gdf_cub = None
        if res['cubierta_wgs'] is not None and not res['cubierta_wgs'].is_empty:
            geoms_c = [res['cubierta_wgs']] if res['cubierta_wgs'].geom_type == 'Polygon' else list(res['cubierta_wgs'].geoms)
            gdf_cub = gpd.GeoDataFrame([{'ID': i, 'TIPO': 'Cobertura Activa'} for i in range(len(geoms_c))], geometry=geoms_c, crs="EPSG:4326")
            geojson_cubierta_str = gdf_cub.to_json()
        else:
            geojson_cubierta_str = '{"type":"FeatureCollection","features":[]}'

        gdf_cie = None
        if res['ciega_wgs'] is not None and not res['ciega_wgs'].is_empty:
            geoms_ci = [res['ciega_wgs']] if res['ciega_wgs'].geom_type == 'Polygon' else [g for g in res['ciega_wgs'].geoms if g.geom_type in ['Polygon', 'MultiPolygon']]
            gdf_cie = gpd.GeoDataFrame([{'ID': i, 'TIPO': 'Zona Ciega'} for i, g in enumerate(geoms_ci)], geometry=geoms_ci, crs="EPSG:4326")
            geojson_ciega_str = gdf_cie.to_json()
        else:
            geojson_ciega_str = '{"type":"FeatureCollection","features":[]}'

        features_pz = []
        for _, r in df_unicos.iterrows():
            features_pz.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(r['Longitud']), float(r['Latitud'])]},
                "properties": {
                    "Pozo": str(r['Pozo']),
                    "Radio_km": float(radio_km),
                    "Lat": round(float(r['Latitud']), 5),
                    "Lon": round(float(r['Longitud']), 5)
                }
            })
        geojson_pozos_str = json.dumps({"type": "FeatureCollection", "features": features_pz})

        features_prop = []
        for _, r in res['df_propuestas'].iterrows():
            features_prop.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(r['Longitud']), float(r['Latitud'])]},
                "properties": {
                    "ID": str(r['ID']),
                    "Area_Vacio_km2": float(r['Area_Vacio_km2']),
                    "Dist_Pozo_km": float(r['Dist_Pozo_km']),
                    "Prioridad": str(r['Prioridad'])
                }
            })
        geojson_propuestas_str = json.dumps({"type": "FeatureCollection", "features": features_prop})

        features_add = []
        for pt in st.session_state.get("marcadores_piezo", []):
            fuente = pt.get("fuente", "manual")
            color = "#2980b9" if fuente == "csv" else "#d35400"
            features_add.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [pt['lon'], pt['lat']]},
                "properties": {"nombre": pt['nombre'], "tipo": pt.get('tipo', 'Desconocido'), "color": color}
            })
        geojson_add_str = json.dumps({"type": "FeatureCollection", "features": features_add})

        bounds_lim = list(geom_activa.bounds)
        poly_bounds_str = json.dumps(bounds_lim)
        centro_lon = float(geom_activa.centroid.x)
        centro_lat = float(geom_activa.centroid.y)

        shp_ciegas_zip = empaquetar_shapefile_zip(gdf_cie, f"zonas_ciegas_{clave_actual}") if (gdf_cie is not None and not gdf_cie.empty) else None
        shp_cubierta_zip = empaquetar_shapefile_zip(gdf_cub, f"cobertura_buffers_{clave_actual}") if (gdf_cub is not None and not gdf_cub.empty) else None
        
        gdf_prop = None
        if not res['df_propuestas'].empty:
            pts_geom_prop = [Point(xy) for xy in zip(res['df_propuestas']['Longitud'], res['df_propuestas']['Latitud'])]
            gdf_prop = gpd.GeoDataFrame(res['df_propuestas'], geometry=pts_geom_prop, crs="EPSG:4326")
            shp_propuestas_zip = empaquetar_shapefile_zip(gdf_prop, f"propuesta_nuevos_pozos_{clave_actual}")
        else:
            shp_propuestas_zip = None

        # Integración Concesiones REPDA y Puntos de Referencia para Tab 3
        df_repda_pts_tab3, geojson_repda_tab3_str, tiene_repda_tab3 = cargar_concesiones_repda_puntos(
            clave_actual, st.session_state.get("repda_custom_df")
        )
        n_repda_tab3 = len(df_repda_pts_tab3) if tiene_repda_tab3 else 0

        # Preparación Geología Vectorial para Tab 3
        geojson_geo_cob_str = "{}"
        col_sel_geo_cob = "LITOLOGIA"
        dic_leyenda_rocas_cob = {}
        if geom_activa is not None:
            gdf_geo_cob, col_sel_geo_cob, dic_leyenda_rocas_cob = preparar_geologia_vectorial(clave_actual, geom_activa)
            if gdf_geo_cob is not None and not gdf_geo_cob.empty:
                geojson_geo_cob_str = gdf_geo_cob.to_json()

        hay_manual_cob = any(pt.get("fuente") != "csv" for pt in st.session_state.get("marcadores_piezo", []))
        hay_csv_cob = any(pt.get("fuente") == "csv" for pt in st.session_state.get("marcadores_piezo", []))

        span_edit = 'contenteditable="true" spellcheck="false" class="txt-leyenda-editable"'
        leyenda_repda_cob_html = f'''<div id="leg-repda" style="margin-top:2px; display:none;"><i style="background:#2563EB; border:1px solid #1D4ED8;"></i> <span {span_edit}>Captaciones REPDA ({n_repda_tab3:,})</span></div>''' if tiene_repda_tab3 else ""
        leyenda_manual_cob_html = f'''<div id="leg-manual" style="margin-top:2px;"><i style="background:#d35400;"></i> <span {span_edit}>Punto de Referencia Manual</span></div>''' if hay_manual_cob else ""
        leyenda_csv_cob_html = f'''<div id="leg-csv" style="margin-top:2px;"><i style="background:#2980b9;"></i> <span {span_edit}>Punto Cargado por CSV</span></div>''' if hay_csv_cob else ""

        leyenda_geo_cob_html = ""
        if dic_leyenda_rocas_cob:
            leyenda_geo_cob_html = f'''<div id="leg-geo" style="display: none; margin-top:4px; border-top: 1px solid #eee; padding-top:4px;">
                <b style="color:#691C32; font-size:11px;"><span {span_edit}>Geología SGM ({col_sel_geo_cob})</span></b><div style="max-height: 140px; overflow-y: auto; margin-top:4px;">'''
            for roca, color in dic_leyenda_rocas_cob.items():
                leyenda_geo_cob_html += f'<i class="square" style="background:{color};"></i> <span {span_edit} style="font-size:9.5px;">{roca}</span><br>'
            leyenda_geo_cob_html += '</div></div>'

        chk_repda_html = f'<label id="lbl-repda" style="display:flex;"><input type="checkbox" id="chk-repda"> 🏢 Concesiones REPDA ({n_repda_tab3:,})</label>' if tiene_repda_tab3 else ''
        chk_manual_html = '<label id="lbl-manual" style="display:flex;"><input type="checkbox" id="chk-manual" checked> 📍 Referencias Manuales</label>' if hay_manual_cob else ''
        chk_csv_html = '<label id="lbl-csv" style="display:flex;"><input type="checkbox" id="chk-csv" checked> 📄 Pozos Adicionales CSV</label>' if hay_csv_cob else ''
        chk_geo_cob_html = f'<label id="lbl-geo" style="display:{"flex" if dic_leyenda_rocas_cob else "none"};"><input type="checkbox" id="chk-geo"> ⛰️ Geología SGM</label>'
        url_pmtiles_srv = obtener_url_pmtiles()
        html_maplibre_cob = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <title>Diagnóstico de Zonas Ciegas MapLibre</title>
            <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
            <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
            <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
            <script src="https://unpkg.com/pmtiles@2.11.0/dist/index.js"></script>
            
            <!-- Librerías Vectoriales para Dibujo y Cálculo Geodésico -->
            <link rel="stylesheet" href="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.css" type="text/css" />
            <script src="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/@turf/turf@6.5.0/turf.min.js"></script>
            <style>
                body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; overflow: hidden; }}
                #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; background: #ffffff; border-radius: 8px; }}

                .txt-leyenda-editable {{ 
                    cursor: text; padding: 1px 4px; border-radius: 3px; outline: none; 
                    border-bottom: 1px dashed transparent; transition: background-color 0.2s; 
                }}
                .txt-leyenda-editable:hover {{ 
                    background-color: rgba(0,0,0,0.05); border-bottom: 1px dashed #888; 
                }}
                .txt-leyenda-editable:focus {{ 
                    background-color: #ffffff; border-bottom: 1.5px solid #2980b9; 
                    box-shadow: 0 1px 3px rgba(0,0,0,0.15); 
                }}

                .gis-badge-popup .maplibregl-popup-content {{
                    background: rgba(255, 255, 255, 0.96) !important;
                    backdrop-filter: blur(8px) !important;
                    border: 1px solid #CBD5E1 !important;
                    border-top: 3px solid #691C32 !important;
                    border-radius: 6px !important;
                    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16) !important;
                    padding: 8px 12px !important;
                    font-family: 'Segoe UI', Arial, sans-serif !important;
                    line-height: 1.4 !important;
                }}
                .gis-badge-popup .maplibregl-popup-tip {{ border-top-color: rgba(255, 255, 255, 0.96) !important; }}

                .hud-elevation {{
                    position: absolute; top: 12px; right: 55px; z-index: 1000;
                    background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
                    color: #1e293b; padding: 7px 14px; border-radius: 8px;
                    border: 1.5px solid #691C32; box-shadow: 0 4px 15px rgba(0,0,0,0.15);
                    font-size: 11.5px; display: flex; gap: 14px; align-items: center; pointer-events: none;
                }}
                .hud-elevation b {{ color: #691C32; margin-right: 4px; }}

                .btn-open-dock-circle {{
                    position: absolute; top: 12px; left: 12px; z-index: 1000;
                    background: #691C32; color: #ffffff; width: 38px; height: 38px;
                    border-radius: 50%; border: 1.5px solid #DDC9A3;
                    box-shadow: 0 3px 12px rgba(105, 28, 50, 0.35);
                    font-size: 19px; font-weight: bold; cursor: pointer;
                    display: flex; align-items: center; justify-content: center;
                    transition: all 0.2s ease;
                }}
                .btn-open-dock-circle:hover {{ background: #88102B; transform: scale(1.1); }}

                .workbench-dock {{
                    position: absolute; top: 12px; left: 12px; z-index: 2000;
                    background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                    width: 280px; border-radius: 10px; overflow: hidden;
                    box-shadow: 0 6px 20px rgba(0,0,0,0.25); border-top: 4px solid #691C32;
                    border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0;
                    font-size: 11.5px; color: #1E293B;
                }}
                .dock-header {{ 
                    background: #691C32; color: white; padding: 9px 12px; 
                    font-weight: 700; display: flex; justify-content: space-between; align-items: center; 
                }}
                .dock-body {{ padding: 12px 14px; max-height: 70vh; overflow-y: auto; }}
                .dock-section {{ margin-bottom: 12px; }}
                .dock-section label {{ display: flex; align-items: center; gap: 6px; cursor: pointer; margin-bottom: 6px; font-weight: 500; }}
                .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; margin-top: 4px; }}

                .legend-panel {{
                    position: absolute; bottom: 25px; left: 12px; z-index: 1000;
                    background: rgba(255,255,255,0.95); padding: 10px 14px; border-radius: 8px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-size: 11px; line-height: 1.6;
                    border: 1px solid #E2E8F0; max-width: 290px; pointer-events: auto;
                }}
                .legend-panel i {{ width: 12px; height: 12px; display: inline-block; border-radius: 50%; margin-right: 6px; vertical-align: middle; border: 1px solid #ccc; }}
                .legend-panel .square {{ border-radius: 2px; }}

                .leaflet-open-draw-btn {{
                    position: absolute; top: 160px; right: 10px; z-index: 1000;
                    background: #691C32 !important; color: #ffffff; width: 29px; height: 29px;
                    border-radius: 4px; border: 2px solid rgba(0,0,0,0.2);
                    cursor: pointer; display: flex; align-items: center; justify-content: center;
                    transition: background 0.2s ease;
                }}
                .leaflet-open-draw-btn:hover {{ background: #88102B !important; }}

                .draw-docked-panel {{
                    position: absolute; top: 160px; right: 50px; z-index: 2000;
                    background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                    width: 275px; border-radius: 8px; overflow: hidden;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.2); border-top: 3px solid #691C32;
                    border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0;
                    font-size: 11px; color: #1E293B;
                }}
                .docked-draw-header {{
                    background: #f8fafc; color: #1e293b; padding: 6px 10px;
                    font-weight: 700; display: flex; justify-content: space-between; align-items: center;
                    border-bottom: 1px solid #e2e8f0; font-size: 11.5px;
                }}
                .docked-draw-close {{ cursor: pointer; font-size: 16px; color: #64748b; line-height: 1; font-weight: bold; }}
                .docked-draw-close:hover {{ color: #dc2626; }}
                .docked-draw-body {{ padding: 10px; }}

                .draw-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px; margin-bottom: 8px; }}
                .btn-tool {{
                    background: #ffffff; border: 1px solid #CBD5E1; border-radius: 5px;
                    padding: 5px 6px; font-size: 10.5px; font-weight: 600; color: #334155;
                    display: flex; align-items: center; justify-content: center; gap: 5px; cursor: pointer; transition: all 0.15s ease;
                }}
                .btn-tool svg {{ width: 13px; height: 13px; stroke: #691C32; fill: none; stroke-width: 2; flex-shrink: 0; }}
                .btn-tool:hover {{ background: #f1f5f9; border-color: #691C32; color: #691C32; }}
                .btn-tool.active {{ background: #691C32; border-color: #691C32; color: #ffffff; }}
                .btn-tool.active svg {{ stroke: #ffffff; }}

                .btn-preset {{
                    flex: 1; padding: 3px 4px; font-size: 10px; font-weight: 600;
                    border: 1px solid #cbd5e1; border-radius: 3px; background: #f8fafc;
                    color: #475569; cursor: pointer; transition: all 0.15s ease; text-align: center;
                }}
                .btn-preset:hover {{ background: #e2e8f0; color: #1e293b; border-color: #691C32; }}

                .draw-measure-box {{
                    background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 5px;
                    padding: 8px 10px; font-size: 11px; line-height: 1.45; color: #14532D;
                    margin-bottom: 8px; display: none;
                }}
                .draw-measure-box b {{ color: #166534; }}

                .draw-actions {{ display: flex; gap: 6px; border-top: 1px solid #f1f5f9; padding-top: 8px; }}
                .btn-action-sm {{
                    flex: 1; padding: 5px 8px; font-size: 10.5px; font-weight: 600;
                    border-radius: 4px; border: 1px solid #cbd5e1; background: #ffffff;
                    cursor: pointer; display: flex; align-items: center; justify-content: center;
                    gap: 5px; transition: all 0.15s ease; color: #334155;
                }}
                .btn-action-sm svg {{ width: 13px; height: 13px; stroke: currentColor; fill: none; stroke-width: 2; }}
                .btn-action-sm:hover {{ background: #f8fafc; border-color: #94A3B8; }}
                .btn-action-sm.danger {{ color: #dc2626; border-color: #fecaca; }}
                .btn-action-sm.danger:hover {{ background: #fef2f2; border-color: #dc2626; }}

                .label-marker-corte {{
                    width: 22px; height: 22px; border-radius: 50%;
                    color: #ffffff; font-weight: 800; font-size: 11px;
                    display: flex; align-items: center; justify-content: center;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.35); border: 2px solid #ffffff;
                    pointer-events: none; font-family: 'Segoe UI', Arial, sans-serif;
                }}
                .label-marker-corte.label-a {{ background: #691C32; }}
                .label-marker-corte.label-b {{ background: #166534; }}
            </style>
        </head>
        <body>
            <div id="map"></div>

            <div class="hud-elevation" id="hud-cob">
                <div><b>Diagnóstico:</b> <span id="hud-status" style="font-weight:600; color:{res['color_diagnostico']};">{res['diagnostico']}</span></div>
                <div style="border-left:1px solid #cbd5e1; padding-left:10px;"><b>Coord:</b> <span id="hud-coord">--</span></div>
            </div>

            <div id="btn-open-dock" class="btn-open-dock-circle" onclick="toggleDock()" title="Capas y Mapas Base">☰</div>

            <div class="workbench-dock" id="workbench-dock" style="display: none;">
                <div class="dock-header">
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span>🛠️ Capas de Diagnóstico</span>
                    </div>
                    <button onclick="toggleDock()" style="background:transparent; border:none; color:white; font-size:16px; font-weight:bold; cursor:pointer; line-height:1; padding:2px 5px;" title="Cerrar panel">✕</button>
                </div>
                <div class="dock-body">
                    <div class="dock-section">
                        <label style="font-weight:700; color:#691C32; margin-bottom:2px;">🌍 Mapa Base:</label>
                        <select id="sel-basemap" class="slider-ctrl" style="padding: 4px; border-radius: 4px; border: 1px solid #ccc; width: 100%; background: #f8fafc;" onchange="cambiarMapaBase(this.value)">
                            <option value="base-light-layer">Gris Claro (Esri)</option>
                            <option value="base-sat-layer">Satélite (Esri)</option>
                            <option value="base-topo-layer">Topográfico (Esri)</option>
                            <option value="base-osm-layer">OpenStreetMap</option>
                            <option value="base-street-layer">Estándar (Esri)</option>
                            <option value="base-terrain-layer">Terreno (Esri)</option>
                            <option value="base-ocean-layer">Océanos (Esri)</option>
                            <option value="base-dark-layer">Gris Oscuro (Esri)</option>
                            <option value="base-google-layer">Google Satelital gris 35%</option>
                        </select>
                    </div>

                    <div class="dock-section">
                        <span style="font-weight:700; color:#691C32; display:block; margin-bottom:6px; font-size:11px;">🎨 OPACIDAD ZONAS CIEGAS</span>
                        <input type="range" class="slider-ctrl" id="slider-opac-zonas" min="0.1" max="0.8" step="0.05" value="0.4" oninput="cambiarOpacidadZonas(this.value)">
                        <div style="display:flex; justify-content:space-between; font-size:9.5px; color:#64748b; margin-top:2px;">
                            <span>Tenue</span><span id="val-opac-zonas">40%</span><span>Opaco</span>
                        </div>
                    </div>
                    <div class="dock-section" id="sec-opac-geo" style="display: none;">
                        <span style="font-weight:700; color:#691C32; display:block; margin-bottom:6px; font-size:11px;">🎨 OPACIDAD GEOLOGÍA SGM</span>
                        <input type="range" class="slider-ctrl" id="slider-opac-geo" min="0" max="1" step="0.05" value="0.50" oninput="cambiarOpacidadGeologia(this.value)">
                        <div style="display:flex; justify-content:space-between; font-size:9.5px; color:#64748b; margin-top:2px;">
                            <span>Tenue</span><span id="val-opac-geo">50%</span><span>Opaco</span>
                        </div>
                    </div>

                    <div class="dock-section">
                        <span style="font-weight:700; color:#691C32; display:block; margin-bottom:6px; font-size:11px;">📊 CAPAS ANALÍTICAS</span>
                        <label><input type="checkbox" id="chk-ciega" checked> 🔴 Zonas Ciegas (Vacíos)</label>
                        <label><input type="checkbox" id="chk-cubierta" checked> 🟢 Cobertura de Pozos ({radio_km:.1f} km)</label>
                        <label><input type="checkbox" id="chk-acuifero" checked> 🛡️ Delimitación Acuífero</label>
                        <label><input type="checkbox" id="chk-pozos" checked> 📍 Pozos de Monitoreo</label>
                        <label><input type="checkbox" id="chk-propuestas" checked> 🎯 Puntos Sugeridos</label>
                        {chk_repda_html}
                        <label id="lbl-repda-nac" style="display:flex;"><input type="checkbox" id="chk-repda-nac"> 🇲🇽 REPDA Nacional MVT (461,914)</label>
                        {chk_manual_html}
                        {chk_csv_html}
                        {chk_geo_cob_html}
                    </div>
                </div>
            </div>

            <div id="btn-open-draw" class="leaflet-open-draw-btn" onclick="toggleDrawPanel()" title="Herramientas de Medición y Diagnóstico Turf.js">
                <svg viewBox="0 0 24 24" style="width:16px; height:16px; stroke:#ffffff; fill:none; stroke-width:2;">
                    <path d="M12 19l7-7 3 3-7 7-3-3z"/>
                    <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/>
                    <circle cx="12" cy="12" r="2"/>
                </svg>
            </div>

            <div class="draw-docked-panel" id="draw-docked-panel" style="display: none;">
                <div class="docked-draw-header">
                    <div style="display:flex; align-items:center; gap:6px;">
                        <svg viewBox="0 0 24 24" style="width:14px; height:14px; stroke:#691C32; fill:none; stroke-width:2;">
                            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                            <polyline points="2 17 12 22 22 17"/>
                            <polyline points="2 12 12 17 22 12"/>
                        </svg>
                        <span>Gabinete de Cobertura y Vacíos</span>
                    </div>
                    <span class="docked-draw-close" onclick="toggleDrawPanel()" title="Ocultar">&times;</span>
                </div>
                <div class="docked-draw-body">
                    <div class="draw-grid">
                        <button id="btn-tool-point" class="btn-tool" onclick="activarModoDibujo('point')" title="Sondeo diagnóstico puntual de cobertura">
                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/></svg>
                            Punto
                        </button>
                        <button id="btn-tool-line" class="btn-tool" onclick="activarModoDibujo('line_string')" title="Trazar transecto A-A' y medir distancias a pozos">
                            <svg viewBox="0 0 24 24"><path d="M4 20L20 4"/><circle cx="4" cy="20" r="2.5"/><circle cx="20" cy="4" r="2.5"/></svg>
                            Corte A-A'
                        </button>
                        <button id="btn-tool-poly" class="btn-tool" onclick="activarModoDibujo('polygon')" title="Calcular superficie de zonas de interés">
                            <svg viewBox="0 0 24 24"><polygon points="12 2 22 8.5 18 20 6 20 2 8.5"/></svg>
                            Polígono
                        </button>
                    </div>

                    <!-- Sección de Buffer de Inspección / Radio de Prueba -->
                    <div style="margin: 8px 0; border-top: 1px solid #f1f5f9; padding-top: 8px;">
                        <div style="font-weight: 700; color: #1e293b; font-size: 10.5px; margin-bottom: 5px;">
                            <span>🎯 Radio de Inspección / Densificación</span>
                        </div>
                        <div style="display:flex; gap: 4px; align-items: center; margin-bottom: 5px;">
                            <input type="number" id="input-buffer-radio" value="2500" min="100" max="50000" step="250" 
                                   style="width: 70px; padding: 4px 6px; font-size: 11px; border: 1px solid #cbd5e1; border-radius: 4px;" title="Radio en metros">
                            <span style="font-size: 11px; color: #64748b;">m</span>
                            <button id="btn-tool-buffer" class="btn-tool" style="flex:1; padding: 4px 6px; font-size: 10.5px; justify-content: center;" onclick="activarModoBuffer()" title="Clic en zona ciega para simular cobertura">
                                Fijar Radio
                            </button>
                        </div>
                        <div style="display: flex; gap: 4px;">
                            <button class="btn-preset" onclick="setBufferRadio(1000)">1km</button>
                            <button class="btn-preset" onclick="setBufferRadio(2500)">2.5km</button>
                            <button class="btn-preset" onclick="setBufferRadio(5000)">5km</button>
                            <button class="btn-preset" onclick="setBufferRadio(10000)">10km</button>
                        </div>
                    </div>

                    <!-- Controles de Modo Captura Limpia y Bloqueo -->
                    <div style="display:flex; justify-content:space-between; align-items:center; margin: 6px 0; background:#f8fafc; padding: 4px 6px; border-radius:4px; border:1px solid #e2e8f0;">
                        <label style="font-size:10px; color:#475569; display:flex; align-items:center; gap:5px; cursor:pointer;" title="Ocultar popups flotantes para capturas de pantalla 100% limpias">
                            <input type="checkbox" id="chk-show-badge" checked onchange="toggleMostrarBadges(this.checked)">
                            <span>Etiqueta en mapa</span>
                        </label>
                        <button class="btn-preset" onclick="deseleccionarTodo()" title="Ocultar nodos de edición para fotos de reporte" style="padding:2px 6px; font-size:9.5px;">
                            👁️ Ocultar Nodos
                        </button>
                    </div>

                    <div id="draw-measure-box" class="draw-measure-box"></div>

                    <div class="draw-actions">
                        <button class="btn-action-sm danger" onclick="eliminarDibujoSeleccionado()" title="Borrar selección o todos los trazos">
                            <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                            Limpiar
                        </button>
                        <button class="btn-action-sm" onclick="descargarDibujosGeoJSON()" title="Descargar trazos en GeoJSON para QGIS/ArcGIS">
                            <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                            Exportar
                        </button>
                        <button class="btn-action-sm" onclick="document.getElementById('input-import-geojson-cob').click()" title="Cargar archivo GeoJSON al visor">
                            <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                            Importar
                        </button>
                        <input type="file" id="input-import-geojson-cob" accept=".geojson,.json" style="display:none;" onchange="importarDibujosGeoJSON(event)">
                    </div>
                </div>
            </div>

            <div class="legend-panel">
                <b style="color:#691C32; font-size:12px;"><span {span_edit}>Simbología de Cobertura</span></b><br>
                <div style="margin-top:4px;">
                    <div id="leg-cubierta"><i style="background:#10B981; opacity:0.85;"></i> <span {span_edit}>Área Monitoreada (R: {radio_km:.1f} km)</span></div>
                    <div id="leg-ciega" style="margin-top:2px;"><i style="background:#E11D48; opacity:0.85;"></i> <span {span_edit}>Zona Ciega (Sin Medición)</span></div>
                    <div id="leg-pozos" style="margin-top:2px;"><i style="background:#1E293B;"></i> <span {span_edit}>Pozo de Monitoreo Activo</span></div>
                    <div id="leg-propuestas" style="margin-top:2px;"><i style="background:#F59E0B; border: 1.5px solid #78350F;"></i> <span {span_edit}>Punto Sugerido (Nuevo Pozo)</span></div>
                    <div id="leg-acuifero" style="margin-top:2px;"><i class="square" style="background:transparent; border:1.5px dashed #691C32;"></i> <span {span_edit}>Delimitación del Acuífero</span></div>
                    {leyenda_repda_cob_html}
                    <div id="leg-repda-nac" style="display: none; margin-top:5px; border-top: 1px solid #eee; padding-top:4px;">
                        <b style="color:#166534; font-size:11px;"><span {span_edit}>🇲🇽 REPDA Nacional (461,914)</span></b><br>
                        <div style="font-size:9.5px; color:#64748B; margin-bottom:3px;"><span {span_edit}>Uso Oficial Registrado</span></div>
                        <i class="circle" style="background:#16a34a;"></i> <span {span_edit}>Agrícola</span><br>
                        <i class="circle" style="background:#2563eb;"></i> <span {span_edit}>Público Urbano</span><br>
                        <i class="circle" style="background:#ca8a04;"></i> <span {span_edit}>Pecuario</span><br>
                        <i class="circle" style="background:#dc2626;"></i> <span {span_edit}>Industrial</span><br>
                        <i class="circle" style="background:#9333ea;"></i> <span {span_edit}>Servicios</span><br>
                        <i class="circle" style="background:#0284c7;"></i> <span {span_edit}>Doméstico</span><br>
                        <i class="circle" style="background:#0d9488;"></i> <span {span_edit}>Diferentes Usos</span><br>
                    </div>
                    {leyenda_manual_cob_html}
                    {leyenda_csv_cob_html}
                    {leyenda_geo_cob_html}
                </div>
            </div>

            <script>
                // Registrar protocolo PMTiles para teselas vectoriales de alto rendimiento
                let protocol = new pmtiles.Protocol();
                maplibregl.addProtocol("pmtiles", protocol.tile);

                const boundsAcuifero = {poly_bounds_str};
                const geoAcuifero = {geojson_acuifero_str};
                const geoCubierta = {geojson_cubierta_str};
                const geoCiega = {geojson_ciega_str};
                const geoPozos = {geojson_pozos_str};
                const geoPropuestas = {geojson_propuestas_str};
                const geoAdd = {geojson_add_str};
                const geoRepda = {geojson_repda_tab3_str};

                const map = new maplibregl.Map({{
                    container: 'map',
                    style: {{
                        'version': 8,
                        'sources': {{
                            'base-light': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri' }},
                            'base-sat': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, Maxar' }},
                            'base-topo': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, USGS' }},
                            'base-osm': {{ 'type': 'raster', 'tiles': ['https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png'], 'tileSize': 256, 'attribution': '© OpenStreetMap' }},
                            'base-street': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri' }},
                            'base-terrain': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, USGS' }},
                            'base-ocean': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri, GEBCO' }},
                            'base-dark': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256, 'attribution': 'Esri' }},
                            'base-google': {{ 'type': 'raster', 'tiles': ['https://mt1.google.com/vt/lyrs=s&x={{x}}&y={{y}}&z={{z}}'], 'tileSize': 256, 'attribution': 'Google Satellite' }}
                        }},
                        'layers': [
                            {{ 'id': 'base-light-layer', 'type': 'raster', 'source': 'base-light', 'layout': {{'visibility': 'visible'}} }},
                            {{ 'id': 'base-sat-layer', 'type': 'raster', 'source': 'base-sat', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-topo-layer', 'type': 'raster', 'source': 'base-topo', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-osm-layer', 'type': 'raster', 'source': 'base-osm', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-street-layer', 'type': 'raster', 'source': 'base-street', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-terrain-layer', 'type': 'raster', 'source': 'base-terrain', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-ocean-layer', 'type': 'raster', 'source': 'base-ocean', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-dark-layer', 'type': 'raster', 'source': 'base-dark', 'layout': {{'visibility': 'none'}} }},
                            {{ 'id': 'base-google-layer', 'type': 'raster', 'source': 'base-google', 'layout': {{'visibility': 'none'}}, 'paint': {{'raster-opacity': 0.35, 'raster-saturation': -1.0}} }}
                        ]
                    }},
                    center: [{centro_lon}, {centro_lat}],
                    zoom: 9
                }});

                const iconExpandSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
                const iconCompressSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;

                class FullscreenCustomControl {{
                    onAdd(mapInstance) {{
                        this._map = mapInstance;
                        this._container = document.createElement('div');
                        this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group';
                        
                        const btn = document.createElement('button');
                        btn.type = 'button';
                        btn.innerHTML = iconExpandSVG;
                        btn.title = 'Pantalla Completa';
                        btn.style.width = '30px';
                        btn.style.height = '30px';
                        btn.style.display = 'flex';
                        btn.style.alignItems = 'center';
                        btn.style.justifyContent = 'center';
                        btn.style.background = '#ffffff';
                        btn.style.cursor = 'pointer';
                        btn.style.border = 'none';
                        
                        btn.onclick = () => {{
                            const target = document.documentElement;
                            if (!document.fullscreenElement && !document.webkitFullscreenElement) {{
                                if (target.requestFullscreen) {{
                                    target.requestFullscreen().catch(err => {{}});
                                }} else if (target.webkitRequestFullscreen) {{
                                    target.webkitRequestFullscreen();
                                }}
                            }} else {{
                                if (document.exitFullscreen) {{
                                    document.exitFullscreen();
                                }} else if (document.webkitExitFullscreen) {{
                                    document.webkitExitFullscreen();
                                }}
                            }}
                        }};
                        
                        const updateBtn = () => {{
                            const isFull = !!(document.fullscreenElement || document.webkitFullscreenElement);
                            btn.innerHTML = isFull ? iconCompressSVG : iconExpandSVG;
                            btn.title = isFull ? 'Salir de Pantalla Completa (Esc)' : 'Pantalla Completa';
                            setTimeout(() => {{ mapInstance.resize(); }}, 150);
                        }};

                        document.addEventListener('fullscreenchange', updateBtn);
                        document.addEventListener('webkitfullscreenchange', updateBtn);
                        
                        this._container.appendChild(btn);
                        return this._container;
                    }}
                    onRemove() {{
                        this._container.parentNode.removeChild(this._container);
                        this._map = undefined;
                    }}
                }}
                map.addControl(new FullscreenCustomControl(), 'top-right');
                map.addControl(new maplibregl.NavigationControl(), 'top-right');
                map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-right');

                const draw = new MapboxDraw({{
                    displayControlsDefault: false,
                    controls: {{}},
                    userProperties: true,
                    styles: [
                        {{
                            'id': 'gl-draw-line', 'type': 'line',
                            'filter': ['all', ['==', '$type', 'LineString'], ['!=', 'mode', 'static']],
                            'layout': {{ 'line-cap': 'round', 'line-join': 'round' }},
                            'paint': {{ 'line-color': '#9f2241', 'line-width': 3, 'line-dasharray': [0.2, 2] }}
                        }},
                        {{
                            'id': 'gl-draw-polygon-fill', 'type': 'fill',
                            'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                            'paint': {{ 'fill-color': '#285c4d', 'fill-opacity': 0.25 }}
                        }},
                        {{
                            'id': 'gl-draw-polygon-stroke', 'type': 'line',
                            'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                            'layout': {{ 'line-cap': 'round', 'line-join': 'round' }},
                            'paint': {{ 'line-color': '#285c4d', 'line-width': 2.5 }}
                        }},
                        {{
                            'id': 'gl-draw-point', 'type': 'circle',
                            'filter': ['all', ['==', '$type', 'Point'], ['!=', 'meta', 'vertex'], ['!=', 'meta', 'midpoint'], ['!=', 'mode', 'static']],
                            'paint': {{ 'circle-radius': 5, 'circle-color': '#ffffff', 'circle-stroke-width': 2, 'circle-stroke-color': '#691C32' }}
                        }},
                        {{
                            'id': 'gl-draw-vertex-inactive', 'type': 'circle',
                            'filter': ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                            'paint': {{ 'circle-radius': 5, 'circle-color': '#ffffff', 'circle-stroke-width': 2, 'circle-stroke-color': '#691C32' }}
                        }},
                        {{
                            'id': 'gl-draw-vertex-active', 'type': 'circle',
                            'filter': ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                            'paint': {{ 'circle-radius': 7, 'circle-color': '#691C32', 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' }}
                        }},
                        {{
                            'id': 'gl-draw-midpoint', 'type': 'circle',
                            'filter': ['all', ['==', 'meta', 'midpoint'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                            'paint': {{ 'circle-radius': 4.5, 'circle-color': '#DDC9A3', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#691C32' }}
                        }}
                    ]
                }});
                map.addControl(draw);

                if (boundsAcuifero && boundsAcuifero.length === 4) {{
                    map.fitBounds([
                        [boundsAcuifero[0], boundsAcuifero[1]],
                        [boundsAcuifero[2], boundsAcuifero[3]]
                    ], {{ padding: 35, duration: 800 }});
                }}

                map.on('load', () => {{
                    // 1. Acuífero
                    map.addSource('source-acuifero', {{ type: 'geojson', data: geoAcuifero }});
                    map.addLayer({{
                        id: 'acuifero-fill', type: 'fill', source: 'source-acuifero',
                        paint: {{ 'fill-color': '#691C32', 'fill-opacity': 0.04 }}
                    }});
                    map.addLayer({{
                        id: 'acuifero-line', type: 'line', source: 'source-acuifero',
                        paint: {{ 'line-color': '#691C32', 'line-width': 2.2, 'line-dasharray': [3, 2] }}
                    }});

                    // 1.1 Geología SGM
                    const geoData = {geojson_geo_cob_str};
                    if (geoData.features) {{
                        map.addSource('geo-src', {{ type: 'geojson', data: geoData }});
                        map.addLayer({{
                            id: 'geo-fill', type: 'fill', source: 'geo-src',
                            paint: {{ 'fill-color': ['get', 'COLOR_HEX'], 'fill-opacity': 0.45 }},
                            layout: {{ 'visibility': 'none' }}
                        }});
                        map.addLayer({{
                            id: 'geo-line', type: 'line', source: 'geo-src',
                            paint: {{ 'line-color': '#555', 'line-width': 0.5, 'line-opacity': 0.6 }},
                            layout: {{ 'visibility': 'none' }}
                        }});
                    }}

                    // 2. Cobertura Activa
                    map.addSource('source-cubierta', {{ type: 'geojson', data: geoCubierta }});
                    map.addLayer({{
                        id: 'cubierta-fill', type: 'fill', source: 'source-cubierta',
                        paint: {{ 'fill-color': '#10B981', 'fill-opacity': 0.32 }}
                    }});
                    map.addLayer({{
                        id: 'cubierta-line', type: 'line', source: 'source-cubierta',
                        paint: {{ 'line-color': '#059669', 'line-width': 1.2 }}
                    }});

                    // 3. Zonas Ciegas
                    map.addSource('source-ciega', {{ type: 'geojson', data: geoCiega }});
                    map.addLayer({{
                        id: 'ciega-fill', type: 'fill', source: 'source-ciega',
                        paint: {{ 'fill-color': '#E11D48', 'fill-opacity': 0.40 }}
                    }});
                    map.addLayer({{
                        id: 'ciega-line', type: 'line', source: 'source-ciega',
                        paint: {{ 'line-color': '#BE123C', 'line-width': 1.6 }}
                    }});

                    // 4. Pozos Existentes
                    map.addSource('source-pozos', {{ type: 'geojson', data: geoPozos }});
                    map.addLayer({{
                        id: 'pozos-circle', type: 'circle', source: 'source-pozos',
                        paint: {{
                            'circle-radius': 5.5,
                            'circle-color': '#1E293B',
                            'circle-stroke-width': 1.8,
                            'circle-stroke-color': '#FFFFFF'
                        }}
                    }});

                    // 5. Puntos Propuestos
                    map.addSource('source-propuestas', {{ type: 'geojson', data: geoPropuestas }});
                    map.addLayer({{
                        id: 'propuestas-glow', type: 'circle', source: 'source-propuestas',
                        paint: {{
                            'circle-radius': 13,
                            'circle-color': '#F59E0B',
                            'circle-opacity': 0.35
                        }}
                    }});
                    map.addLayer({{
                        id: 'propuestas-circle', type: 'circle', source: 'source-propuestas',
                        paint: {{
                            'circle-radius': 7.5,
                            'circle-color': '#D97706',
                            'circle-stroke-width': 2.2,
                            'circle-stroke-color': '#FFFFFF'
                        }}
                    }});

                    // Click en Pozos
                    map.on('click', 'pozos-circle', (e) => {{
                        const p = e.features[0].properties;
                        new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                            .setLngLat(e.lngLat)
                            .setHTML(`
                                <div style="font-weight:700; color:#691C32; font-size:12px; margin-bottom:4px; border-bottom:1px solid #e2e8f0; padding-bottom:2px;">
                                    📍 Pozo: ${{p.Pozo}}
                                </div>
                                <div style="font-size:11px; color:#334155;">
                                    <b>Coordenadas:</b> ${{p.Lat}}° N, ${{p.Lon}}° W<br>
                                    <b>Radio Representatividad:</b> ${{p.Radio_km}} km<br>
                                    <span style="color:#166534; font-weight:600; font-size:10.5px;">🟢 Monitoreo Piezométrico Activo</span>
                                </div>
                            `)
                            .addTo(map);
                    }});

                    // Click en Propuestas
                    map.on('click', 'propuestas-circle', (e) => {{
                        const p = e.features[0].properties;
                        new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                            .setLngLat(e.lngLat)
                            .setHTML(`
                                <div style="font-weight:700; color:#B45309; font-size:12px; margin-bottom:4px; border-bottom:1px solid #fef3c7; padding-bottom:2px;">
                                    🎯 Propuesta de Nuevo Pozo: ${{p.ID}}
                                </div>
                                <div style="font-size:11px; color:#334155;">
                                    <b>Coordenadas Sugeridas:</b> ${{e.lngLat.lat.toFixed(5)}}° N, ${{e.lngLat.lng.toFixed(5)}}° W<br>
                                    <b>Superficie de Vacío Contiguo:</b> ${{p.Area_Vacio_km2}} km²<br>
                                    <b>Distancia a Pozo Existente:</b> ${{p.Dist_Pozo_km}} km<br>
                                    <div style="margin-top:4px;"><b>Prioridad:</b> <span style="font-weight:700; color:#B45309;">${{p.Prioridad}}</span></div>
                                </div>
                            `)
                            .addTo(map);
                    }});

                    // Click en Zona Ciega
                    map.on('click', 'ciega-fill', (e) => {{
                        if (map.getLayer('geo-fill') && map.getLayoutProperty('geo-fill', 'visibility') === 'visible') {{
                            return; // Permite que geo-fill procese el clic litológico
                        }}
                        new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                            .setLngLat(e.lngLat)
                            .setHTML(`
                                <div style="font-weight:700; color:#BE123C; font-size:12px; margin-bottom:3px;">
                                    🔴 Zona Ciega de Monitoreo
                                </div>
                                <div style="font-size:11px; color:#475569;">
                                    Área desprovista de medición piezométrica directa para el radio de ${{radio_km}} km.<br>
                                    <span style="color:#991B1B; font-weight:600; font-size:10.5px;">⚠️ Alta incertidumbre en interpolación geohidrológica.</span>
                                </div>
                            `)
                            .addTo(map);
                    }});

                    // Click en Geología SGM
                    map.on('click', 'geo-fill', (e) => {{
                        if (typeof modoDibujoActivo !== 'undefined' && modoDibujoActivo) return;
                        const puntosClickeados = map.queryRenderedFeatures(e.point, {{
                            layers: ['pozos-circle', 'propuestas-circle', 'add-layer-manual', 'add-layer-csv', 'repda-layer', 'repda-nacional-layer'].filter(id => map.getLayer(id))
                        }});
                        if (puntosClickeados.length > 0) return;

                        const p = e.features[0].properties;
                        const formacion = (p.FORMACION && p.FORMACION !== 'null' && p.FORMACION !== 'NINGUNO') ? p.FORMACION : 'Formación No Asignada';
                        const claveSgm = p["{col_sel_geo_cob}"] || p.ETIQUETA_LITO || 'S/C';
                        const litologia = p.LITOLOGIA || 'Indiferenciada';
                        const roca = p.ROCA || 'Sedimentaria';
                        const colorHex = p.COLOR_HEX || '#B0BEC5';
                        
                        let edadGeo = p.PERIODO || '';
                        if (p.EDINICIO || p.EDFINAL) {{
                            const ini = p.EDINICIO || '';
                            const fin = p.EDFINAL || '';
                            edadGeo += (ini === fin || !fin) ? ` (${{ini}})` : ` (${{ini}} - ${{fin}})`;
                        }}
                        if (!edadGeo.trim()) edadGeo = p.ERA || 'S/D';

                        const ptGeo = [e.lngLat.lng, e.lngLat.lat];
                        let condCob = "";
                        if (typeof turf !== 'undefined') {{
                            let esCiega = false;
                            if (geoCiega && geoCiega.features) {{
                                for (let f of geoCiega.features) {{
                                    if (turf.booleanPointInPolygon(ptGeo, f)) {{ esCiega = true; break; }}
                                }}
                            }}
                            if (esCiega) {{
                                condCob = '<div style="margin-top:4px; padding-top:3px; border-top:1px dashed #e2e8f0; color:#BE123C; font-size:10px; font-weight:700;">🔴 En Zona Ciega de Monitoreo</div>';
                            }} else {{
                                condCob = '<div style="margin-top:4px; padding-top:3px; border-top:1px dashed #e2e8f0; color:#059669; font-size:10px; font-weight:700;">🟢 En Cobertura Activa</div>';
                            }}
                        }}

                        let html = `
                            <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; line-height:1.5; min-width:200px;">
                                <div style="display:flex; align-items:center; justify-content:space-between; border-bottom:1.5px solid #E2E8F0; padding-bottom:4px; margin-bottom:6px;">
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <span style="width:13px; height:13px; background:${{colorHex}}; border-radius:3px; border:1px solid #475569; display:inline-block;"></span>
                                        <h4 style="margin:0; color:#691C32; font-size:13px; font-weight:700;">${{formacion}}</h4>
                                    </div>
                                    <span style="background:#F1F5F9; border:1px solid #CBD5E1; color:#334155; font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:3px;">${{claveSgm}}</span>
                                </div>
                                <b>Litología:</b> <span style="color:#0f172a; font-weight:600;">${{litologia}}</span><br>
                                <b>Tipo de Roca:</b> ${{roca}}<br>
                                <b>Edad Geológica:</b> ${{edadGeo}}<br>
                                ${{condCob}}
                                <span style="color:#64748B; font-size:10px;">Coords: ${{e.lngLat.lat.toFixed(4)}}°, ${{e.lngLat.lng.toFixed(4)}}°</span>
                            </div>
                        `;
                        new maplibregl.Popup({{ className: 'gis-badge-popup' }}).setLngLat(e.lngLat).setHTML(html).addTo(map);
                    }});
                    map.on('mouseenter', 'geo-fill', () => {{ if (typeof modoDibujoActivo !== 'undefined' && !modoDibujoActivo) map.getCanvas().style.cursor = 'pointer'; }});
                    map.on('mouseleave', 'geo-fill', () => {{ if (typeof modoDibujoActivo !== 'undefined' && !modoDibujoActivo) map.getCanvas().style.cursor = ''; }});

                    // 6. Puntos de Referencia Adicionales (Manuales y CSV)
                    map.addSource('add-src', {{ type: 'geojson', data: geoAdd }});
                    map.addLayer({{
                        id: 'add-layer-manual', type: 'circle', source: 'add-src',
                        filter: ['!=', ['get', 'tipo'], 'csv'],
                        paint: {{
                            'circle-radius': 6.5,
                            'circle-color': '#d35400',
                            'circle-stroke-width': 1.8,
                            'circle-stroke-color': '#FFFFFF'
                        }}
                    }});
                    map.addLayer({{
                        id: 'add-layer-csv', type: 'circle', source: 'add-src',
                        filter: ['==', ['get', 'tipo'], 'csv'],
                        paint: {{
                            'circle-radius': 6,
                            'circle-color': '#2980b9',
                            'circle-stroke-width': 1.8,
                            'circle-stroke-color': '#FFFFFF'
                        }}
                    }});

                    // Click en Puntos Adicionales
                    ['add-layer-manual', 'add-layer-csv'].forEach(lyr => {{
                        map.on('click', lyr, (e) => {{
                            const p = e.features[0].properties;
                            new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                                .setLngLat(e.lngLat)
                                .setHTML(`
                                    <div style="font-weight:700; color:#691C32; font-size:12px; margin-bottom:4px; border-bottom:1px solid #e2e8f0; padding-bottom:2px;">
                                        📌 ${{p.nombre || 'Punto Adicional'}}
                                    </div>
                                    <div style="font-size:11px; color:#334155;">
                                        <b>Tipo / Fuente:</b> ${{p.tipo || '--'}}<br>
                                        <b>Coordenadas:</b> ${{e.lngLat.lat.toFixed(5)}}° N, ${{e.lngLat.lng.toFixed(5)}}° W
                                    </div>
                                `)
                                .addTo(map);
                        }});
                    }});

                    // 7. Concesiones REPDA
                    map.addSource('repda-src', {{ type: 'geojson', data: geoRepda }});
                    map.addLayer({{
                        id: 'repda-halo-layer', type: 'circle', source: 'repda-src',
                        paint: {{
                            'circle-radius': ['+', ['get', 'radio_px'], 2.5],
                            'circle-color': ['get', 'color'],
                            'circle-opacity': 0.28
                        }},
                        layout: {{ 'visibility': 'none' }}
                    }});
                    map.addLayer({{
                        id: 'repda-layer', type: 'circle', source: 'repda-src',
                        paint: {{
                            'circle-radius': ['get', 'radio_px'],
                            'circle-color': ['get', 'color'],
                            'circle-opacity': 0.88,
                            'circle-stroke-width': 1.2,
                            'circle-stroke-color': '#0f172a'
                        }},
                        layout: {{ 'visibility': 'none' }}
                    }});

                    // Click en REPDA con Diagnóstico Territorial Turf.js
                    map.on('click', 'repda-layer', (e) => {{
                        const p = e.features[0].properties;
                        const c = e.lngLat;
                        const ptGeo = [c.lng, c.lat];

                        let condCob = "<span style='color:#64748B;'>Fuera del Acuífero</span>";
                        let esCiega = false;
                        let esCubierta = false;

                        if (geoCiega && geoCiega.features && geoCiega.features.length > 0) {{
                            for (let f of geoCiega.features) {{
                                if (turf.booleanPointInPolygon(ptGeo, f)) {{
                                    esCiega = true;
                                    break;
                                }}
                            }}
                        }}
                        if (geoCubierta && geoCubierta.features && geoCubierta.features.length > 0) {{
                            for (let f of geoCubierta.features) {{
                                if (turf.booleanPointInPolygon(ptGeo, f)) {{
                                    esCubierta = true;
                                    break;
                                }}
                            }}
                        }}

                        if (esCiega) {{
                            condCob = "<span style='color:#BE123C; font-weight:700;'>🔴 Ubicado en Zona Ciega (Sin Monitoreo)</span>";
                        }} else if (esCubierta) {{
                            condCob = `<span style='color:#059669; font-weight:700;'>🟢 Ubicado en Cobertura Activa ({radio_km:.1f} km)</span>`;
                        }}

                        const volFmt = p.volumen_m3 !== undefined ? Number(p.volumen_m3).toLocaleString('es-MX') : '--';
                        const volHm3 = p.volumen_hm3 !== undefined ? Number(p.volumen_hm3).toFixed(3) : '--';

                        new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                            .setLngLat(c)
                            .setHTML(`
                                <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; min-width:220px; line-height:1.45;">
                                    <div style="font-weight:700; color:#691C32; font-size:12px; margin-bottom:4px; border-bottom:1.5px solid #691C32; padding-bottom:3px; display:flex; justify-content:space-between; align-items:center;">
                                        <span>🏢 Concesión REPDA</span>
                                        <span style="font-size:10px; background:#f1f5f9; color:#475569; padding:1px 5px; border-radius:4px;">${{p.folio || '--'}}</span>
                                    </div>
                                    <div style="margin-bottom:3px;"><b>Titular:</b> <span style="color:#0f172a; font-weight:600;">${{p.titular || '--'}}</span></div>
                                    ${{p.expediente ? `<div style="margin-bottom:2px;"><b>Expediente:</b> ${{p.expediente}}</div>` : ''}}
                                    ${{p.fecha ? `<div style="margin-bottom:2px;"><b>Fecha Registro:</b> ${{p.fecha}}</div>` : ''}}
                                    <div style="margin-bottom:2px;"><b>Uso:</b> <span style="background:${{p.color || '#3b82f6'}}22; color:${{p.color || '#1d4ed8'}}; font-weight:700; padding:1px 5px; border-radius:3px; border:1px solid ${{p.color || '#3b82f6'}}55;">${{p.uso || '--'}}</span></div>
                                    <div style="margin-bottom:2px;"><b>Volumen Anual:</b> <b>${{volFmt}}</b> m³/año (${{volHm3}} hm³/año)</div>
                                    ${{p.profundidad_m > 0 ? `<div style="margin-bottom:2px;"><b>Profundidad:</b> ${{p.profundidad_m}} m</div>` : ''}}
                                    <div style="margin-top:5px; padding-top:4px; border-top:1px dashed #cbd5e1; font-size:11px;">
                                        <b>Diagnóstico Territorial:</b><br>${{condCob}}
                                    </div>
                                    <div style="font-size:9.5px; color:#64748b; margin-top:4px; text-align:right;">
                                        Coordenadas: ${{Number(p.lat).toFixed(5)}}° N, ${{Number(p.lon).toFixed(5)}}° W
                                    </div>
                                </div>
                            `)
                            .addTo(map);
                    }});

                    // 8. REPDA Nacional Completo (Vector Tiles PMTiles)
                    let pmtilesUrlTab3 = '{url_pmtiles_srv}';
                    if (!pmtilesUrlTab3.startsWith('http://') && !pmtilesUrlTab3.startsWith('https://')) {{
                        let baseOrigin = (window.location && window.location.origin && window.location.origin !== 'null') ? window.location.origin : '';
                        if (!baseOrigin && document.referrer) {{
                            try {{ baseOrigin = new URL(document.referrer).origin; }} catch (err) {{}}
                        }}
                        pmtilesUrlTab3 = (baseOrigin || '') + pmtilesUrlTab3;
                    }}
                    map.addSource('repda-nacional-src', {{
                        type: 'vector',
                        url: 'pmtiles://' + pmtilesUrlTab3,
                        minzoom: 4,
                        maxzoom: 8
                    }});
                    map.addLayer({{
                        id: 'repda-nacional-layer',
                        type: 'circle',
                        source: 'repda-nacional-src',
                        'source-layer': 'repda',
                        maxzoom: { '11' if tiene_repda_tab3 else '24' },
                        layout: {{ 'visibility': 'none' }},
                        paint: {{
                            'circle-radius': [
                                'interpolate', ['linear'], ['zoom'],
                                4, 1.2,
                                7, 2.5,
                                10, 4.5,
                                14, 7.5
                            ],
                            'circle-color': [
                                'match', ['get', 'u'],
                                'AGRICOLA', '#16a34a',
                                'PUBLICO URBANO', '#2563eb',
                                'DOMESTICO', '#0284c7',
                                'INDUSTRIAL', '#dc2626',
                                'SERVICIOS', '#9333ea',
                                'PECUARIO', '#ca8a04',
                                'DIFERENTES USOS', '#0d9488',
                                'ACUACULTURA', '#06b6d4',
                                'AGROINDUSTRIAL', '#65a30d',
                                'COMERCIO', '#ea580c',
                                'ENERGIA ELECTRICA', '#eab308',
                                /* default */ '#475569'
                            ],
                            'circle-opacity': 0.85,
                            'circle-stroke-width': [
                                'interpolate', ['linear'], ['zoom'],
                                4, 0,
                                8, 0.4,
                                11, 1.0
                            ],
                            'circle-stroke-color': '#ffffff'
                        }}
                    }});

                    // Click en pozo REPDA Nacional
                    map.on('click', 'repda-nacional-layer', (e) => {{
                        const p = e.features[0].properties;
                        const volM3 = p.v ? Number(p.v).toLocaleString('es-MX') : '--';
                        const volHm3 = p.v ? (Number(p.v) / 1e6).toFixed(3) : '--';
                        const latFmt = p.la !== undefined ? Number(p.la).toFixed(5) : e.lngLat.lat.toFixed(5);
                        const lonFmt = p.lo !== undefined ? Number(p.lo).toFixed(5) : e.lngLat.lng.toFixed(5);
                        new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                            .setLngLat(e.lngLat)
                            .setHTML(`
                                <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; min-width:220px; line-height:1.45;">
                                    <div style="font-weight:700; color:#166534; font-size:12px; margin-bottom:4px; border-bottom:1.5px solid #166534; padding-bottom:3px; display:flex; justify-content:space-between; align-items:center;">
                                        <span>🇲🇽 Concesión REPDA Nacional</span>
                                        <span style="font-size:10px; background:#f1f5f9; color:#475569; padding:1px 5px; border-radius:4px;">${{p.f || '--'}}</span>
                                    </div>
                                    <div style="margin-bottom:3px;"><b>Titular:</b> <span style="color:#0f172a; font-weight:600;">${{p.t || '--'}}</span></div>
                                    ${{p.e ? `<div style="margin-bottom:2px;"><b>Expediente:</b> ${{p.e}}</div>` : ''}}
                                    <div style="margin-bottom:2px;"><b>Uso:</b> <span style="background:#f0fdf4; color:#166534; font-weight:700; padding:1px 5px; border-radius:3px; border:1px solid #bbf7d0;">${{p.u || '--'}}</span></div>
                                    <div style="margin-bottom:2px;"><b>Volumen Anual:</b> <b>${{volM3}}</b> m³/año (${{volHm3}} hm³/año)</div>
                                    <div style="font-size:9.5px; color:#64748b; margin-top:4px;">Coordenadas: ${{latFmt}}° N, ${{lonFmt}}° W</div>
                                </div>
                            `)
                            .addTo(map);
                    }});

                    // Eventos de Cursor para capas interactivas
                    ['pozos-circle', 'propuestas-circle', 'repda-layer', 'repda-nacional-layer', 'add-layer-manual', 'add-layer-csv'].forEach(lyr => {{
                        map.on('mouseenter', lyr, () => {{ map.getCanvas().style.cursor = 'pointer'; }});
                        map.on('mouseleave', lyr, () => {{ map.getCanvas().style.cursor = ''; }});
                    }});
                }});

                // HUD Reactivo de Coordenadas y Diagnóstico
                map.on('mousemove', (e) => {{
                    document.getElementById('hud-coord').innerText = `${{e.lngLat.lat.toFixed(5)}}° N, ${{e.lngLat.lng.toFixed(5)}}° W`;
                }});

                // Gestión de Mapas Base (idéntica a Dinámica de Flujo y Evolución)
                const basemapsCob = [
                    'base-light-layer', 'base-sat-layer', 'base-topo-layer',
                    'base-osm-layer', 'base-street-layer', 'base-terrain-layer',
                    'base-ocean-layer', 'base-dark-layer', 'base-google-layer'
                ];
                function cambiarMapaBase(selected) {{
                    basemapsCob.forEach(id => {{
                        if (map.getLayer(id)) {{
                            map.setLayoutProperty(id, 'visibility', (id === selected) ? 'visible' : 'none');
                        }}
                    }});
                }}

                const selBasemapEl = document.getElementById('sel-basemap');
                if (selBasemapEl) {{
                    selBasemapEl.addEventListener('change', (e) => {{
                        cambiarMapaBase(e.target.value);
                    }});
                }}

                // Control de Opacidad de Zonas Ciegas
                function cambiarOpacidadZonas(val) {{
                    const numVal = parseFloat(val);
                    const pctEl = document.getElementById('val-opac-zonas');
                    if (pctEl) pctEl.innerText = Math.round(numVal * 100) + '%';
                    if (map.getLayer('ciega-fill')) {{
                        map.setPaintProperty('ciega-fill', 'fill-opacity', numVal);
                    }}
                }}

                function cambiarOpacidadGeologia(val) {{
                    const numVal = parseFloat(val);
                    const pctEl = document.getElementById('val-opac-geo');
                    if (pctEl) pctEl.innerText = Math.round(numVal * 100) + '%';
                    if (map.getLayer('geo-fill')) {{
                        map.setPaintProperty('geo-fill', 'fill-opacity', numVal);
                    }}
                }}

                // Conmutación Reactiva de Capas y Sincronización con Leyenda
                const toggleLayerCob = (chkId, layerIds, legId = null) => {{
                    const chk = document.getElementById(chkId);
                    if (chk) {{
                        chk.addEventListener('change', (e) => {{
                            const vis = e.target.checked ? 'visible' : 'none';
                            layerIds.forEach(id => {{
                                if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', vis);
                            }});
                            if (legId) {{
                                const leg = document.getElementById(legId);
                                if (leg) leg.style.display = e.target.checked ? 'block' : 'none';
                            }}
                        }});
                    }}
                }};

                toggleLayerCob('chk-ciega', ['ciega-fill', 'ciega-line'], 'leg-ciega');
                toggleLayerCob('chk-cubierta', ['cubierta-fill', 'cubierta-line'], 'leg-cubierta');
                toggleLayerCob('chk-acuifero', ['acuifero-fill', 'acuifero-line'], 'leg-acuifero');
                toggleLayerCob('chk-pozos', ['pozos-circle'], 'leg-pozos');
                toggleLayerCob('chk-propuestas', ['propuestas-glow', 'propuestas-circle'], 'leg-propuestas');
                toggleLayerCob('chk-repda', ['repda-halo-layer', 'repda-layer'], 'leg-repda');
                toggleLayerCob('chk-repda-nac', ['repda-nacional-layer'], 'leg-repda-nac');
                toggleLayerCob('chk-manual', ['add-layer-manual'], 'leg-manual');
                toggleLayerCob('chk-csv', ['add-layer-csv'], 'leg-csv');
                toggleLayerCob('chk-geo', ['geo-fill', 'geo-line'], 'leg-geo');
                const chkGeoCob = document.getElementById('chk-geo');
                if (chkGeoCob) {{
                    chkGeoCob.addEventListener('change', (e) => {{
                        const secOpacGeo = document.getElementById('sec-opac-geo');
                        if (secOpacGeo) secOpacGeo.style.display = e.target.checked ? 'block' : 'none';
                    }});
                }}

                // Control de Dock Homologado
                let dockAbierto = false;
                function aplicarEstadoVisualDock() {{
                    const dock = document.getElementById('workbench-dock');
                    const btnOpen = document.getElementById('btn-open-dock');
                    if (dock && btnOpen) {{
                        dock.style.display = dockAbierto ? 'block' : 'none';
                        btnOpen.style.display = dockAbierto ? 'none' : 'flex';
                    }}
                }}

                function toggleDock() {{
                    dockAbierto = !dockAbierto;
                    aplicarEstadoVisualDock();
                    if (dockAbierto && drawAbierto) {{
                        toggleDrawPanel();
                    }}
                }}
                aplicarEstadoVisualDock();

                let drawAbierto = false;
                function toggleDrawPanel() {{
                    drawAbierto = !drawAbierto;
                    const p = document.getElementById('draw-docked-panel');
                    const btn = document.getElementById('btn-open-draw');
                    if (drawAbierto) {{
                        p.style.display = 'block';
                        btn.style.display = 'none';
                        if (dockAbierto) toggleDock();
                    }} else {{
                        p.style.display = 'none';
                        btn.style.display = 'flex';
                        detenerModoBuffer();
                        limpiarHerramientasActivas();
                    }}
                }}

                function activarModoDibujo(mode) {{
                    detenerModoBuffer();
                    limpiarHerramientasActivas();
                    map.getCanvas().style.cursor = 'crosshair'; 
                    if (mode === 'point') {{
                        document.getElementById('btn-tool-point').classList.add('active');
                        draw.changeMode('draw_point');
                    }} else if (mode === 'line_string') {{
                        document.getElementById('btn-tool-line').classList.add('active');
                        draw.changeMode('draw_line_string');
                    }} else if (mode === 'polygon') {{
                        document.getElementById('btn-tool-poly').classList.add('active');
                        draw.changeMode('draw_polygon');
                    }}
                }}

                function limpiarHerramientasActivas() {{
                    ['btn-tool-point', 'btn-tool-line', 'btn-tool-poly', 'btn-tool-buffer'].forEach(id => {{
                        const el = document.getElementById(id);
                        if (el) el.classList.remove('active');
                    }});
                    map.getCanvas().style.cursor = ''; 
                }}

                let modoBufferActivo = false;
                let radioBufferMetros = 2500;

                function setBufferRadio(m) {{
                    document.getElementById('input-buffer-radio').value = m;
                    radioBufferMetros = m;
                    activarModoBuffer();
                }}

                function activarModoBuffer() {{
                    limpiarHerramientasActivas();
                    draw.changeMode('simple_select');
                    modoBufferActivo = true;
                    const inputRadio = document.getElementById('input-buffer-radio');
                    radioBufferMetros = parseFloat(inputRadio.value) || 2500;
                    document.getElementById('btn-tool-buffer').classList.add('active');
                    map.getCanvas().style.cursor = 'crosshair';
                    const box = document.getElementById('draw-measure-box');
                    box.style.display = 'block';
                    box.innerHTML = `<b>🎯 Buffer de Densificación (${{(radioBufferMetros/1000).toFixed(1)}} km):</b> Clic en el mapa sobre una zona ciega para simular área de cobertura.`;
                }}

                function detenerModoBuffer() {{
                    modoBufferActivo = false;
                    map.getCanvas().style.cursor = '';
                    const btn = document.getElementById('btn-tool-buffer');
                    if (btn) btn.classList.remove('active');
                }}

                function eliminarDibujoSeleccionado() {{
                    const sel = draw.getSelectedIds();
                    if (sel && sel.length > 0) {{
                        draw.delete(sel);
                    }} else {{
                        draw.deleteAll();
                    }}
                    document.getElementById('draw-measure-box').style.display = 'none';
                    limpiarRotulosLinea();
                    if (popupDibujoActivo) popupDibujoActivo.remove();
                }}

                function descargarDibujosGeoJSON() {{
                    const data = draw.getAll();
                    if (!data || !data.features || data.features.length === 0) {{
                        alert("No hay geometrías trazadas en el mapa para exportar.");
                        return;
                    }}
                    const blob = new Blob([JSON.stringify(data, null, 2)], {{ type: 'application/geo+json' }});
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'analisis_cobertura_zonas_ciegas.geojson';
                    a.click();
                    URL.revokeObjectURL(url);
                }}

                function importarDibujosGeoJSON(e) {{
                    const file = e.target.files[0];
                    if (!file) return;
                    const reader = new FileReader();
                    reader.onload = function(evt) {{
                        try {{
                            const data = JSON.parse(evt.target.result);
                            if (data.type === "FeatureCollection" && data.features) {{
                                data.features.forEach(f => draw.add(f));
                                const bbox = turf.bbox(data);
                                map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], {{ padding: 40 }});
                                alert(`Se importaron ${{data.features.length}} geometrías exitosamente.`);
                            }} else if (data.type === "Feature") {{
                                draw.add(data);
                                const bbox = turf.bbox(data);
                                map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], {{ padding: 40 }});
                                alert("Se importó 1 geometría exitosamente.");
                            }} else {{
                                alert("Formato GeoJSON no válido.");
                            }}
                        }} catch(err) {{
                            alert("Error al leer archivo: " + err.message);
                        }}
                    }};
                    reader.readAsText(file);
                    e.target.value = "";
                }}

                let markerA = null;
                let markerB = null;
                let popupDibujoActivo = null;

                function actualizarRotulosLinea(feat) {{
                    limpiarRotulosLinea();
                    if (!feat || !feat.geometry || feat.geometry.type !== 'LineString') return;
                    const coords = feat.geometry.coordinates;
                    if (!coords || coords.length < 2) return;
                    
                    const elA = document.createElement('div');
                    elA.className = 'label-marker-corte label-a';
                    elA.innerText = 'A';
                    elA.title = 'Extremo Inicial A';
                    
                    const elB = document.createElement('div');
                    elB.className = 'label-marker-corte label-b';
                    elB.innerText = "A'";
                    elB.title = "Extremo Final A'";
                    
                    markerA = new maplibregl.Marker({{ element: elA }}).setLngLat(coords[0]).addTo(map);
                    markerB = new maplibregl.Marker({{ element: elB }}).setLngLat(coords[coords.length - 1]).addTo(map);
                }}

                function limpiarRotulosLinea() {{
                    if (markerA) {{ markerA.remove(); markerA = null; }}
                    if (markerB) {{ markerB.remove(); markerB = null; }}
                }}

                function toggleMostrarBadges(mostrar) {{
                    if (!mostrar && popupDibujoActivo) {{
                        popupDibujoActivo.remove();
                    }} else if (mostrar) {{
                        const feats = draw.getAll().features;
                        if (feats && feats.length > 0) {{
                            actualizarMedicionCompleta(feats[feats.length - 1], true);
                        }}
                    }}
                }}

                function deseleccionarTodo() {{
                    draw.changeMode('simple_select', {{ featureIds: [] }});
                    if (popupDibujoActivo) popupDibujoActivo.remove();
                }}

                window.addEventListener('keydown', (e) => {{
                    if (e.key === 'Escape') {{
                        const m = draw.getMode();
                        if (m.startsWith('draw_') || modoBufferActivo) {{
                            draw.trash();
                            draw.changeMode('simple_select');
                            detenerModoBuffer();
                            limpiarHerramientasActivas();
                            const b = document.getElementById('draw-measure-box');
                            if (b) b.style.display = 'none';
                            limpiarRotulosLinea();
                        }}
                    }}
                }});

                function obtenerInfoMedicion(feat) {{
                    if (!feat || !feat.geometry) return null;
                    const tipo = feat.geometry.type;
                    const props = feat.properties || {{}};

                    if (tipo === 'Point') {{
                        const c = feat.geometry.coordinates;
                        
                        let estadoTxt = "<span style='color:#64748B;'>Fuera del Acuífero</span>";
                        if (geoAcuifero && geoAcuifero.features && geoAcuifero.features.length > 0) {{
                            for (let f of geoAcuifero.features) {{
                                if (turf.booleanPointInPolygon(c, f)) {{
                                    estadoTxt = "<span style='color:#1E293B;'>Dentro del Polígono del Acuífero</span>";
                                    break;
                                }}
                            }}
                        }}

                        let esCiega = false;
                        if (geoCiega && geoCiega.features && geoCiega.features.length > 0) {{
                            for (let f of geoCiega.features) {{
                                if (turf.booleanPointInPolygon(c, f)) {{
                                    esCiega = true;
                                    break;
                                }}
                            }}
                        }}

                        let esCubierta = false;
                        if (geoCubierta && geoCubierta.features && geoCubierta.features.length > 0) {{
                            for (let f of geoCubierta.features) {{
                                if (turf.booleanPointInPolygon(c, f)) {{
                                    esCubierta = true;
                                    break;
                                }}
                            }}
                        }}

                        let diagnosticoHtml = "";
                        if (esCiega) {{
                            diagnosticoHtml = "<span style='color:#BE123C; font-weight:700;'>🔴 Ubicación en Zona Ciega (Sin Monitoreo)</span>";
                        }} else if (esCubierta) {{
                            diagnosticoHtml = `<span style='color:#059669; font-weight:700;'>🟢 Ubicación con Cobertura Activa ({radio_km} km)</span>`;
                        }} else {{
                            diagnosticoHtml = estadoTxt;
                        }}

                        let distPozoTxt = "--";
                        if (geoPozos && geoPozos.features && geoPozos.features.length > 0) {{
                            let minD = Infinity;
                            geoPozos.features.forEach(pz => {{
                                const d = turf.distance(c, pz.geometry.coordinates, {{ units: 'kilometers' }});
                                if (d < minD) minD = d;
                            }});
                            distPozoTxt = minD < 1.0 ? `${{(minD * 1000).toFixed(0)}} m` : `${{minD.toFixed(2)}} km`;
                        }}

                        return {{
                            coords: c,
                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📍 Diagnóstico de Ubicación</div>` +
                                   `<div style="font-size:10.5px; color:#334155;">` +
                                   `<b>Estado:</b> ${{diagnosticoHtml}}<br>` +
                                   `<b>Dist. Pozo más cercano:</b> <span style="font-weight:700;">${{distPozoTxt}}</span><br>` +
                                   `<span style="color:#64748B; font-size:9.5px;">${{c[1].toFixed(4)}}° N, ${{c[0].toFixed(4)}}° W</span>` +
                                   `</div>`,
                            panel: `<b>📍 Diagnóstico Puntual de Cobertura</b><br>` +
                                   `<b>Condición:</b> ${{diagnosticoHtml}}<br>` +
                                   `<b>Distancia a Pozo Cercano:</b> ${{distPozoTxt}}<br>` +
                                   `<b>Coordenadas:</b> ${{c[1].toFixed(5)}}° N, ${{c[0].toFixed(5)}}° W`
                        }};
                    }}

                    if (tipo === 'LineString') {{
                        const coordsPts = feat.geometry.coordinates;
                        const km = turf.length(feat, {{ units: 'kilometers' }});
                        const distFormato = km < 1.0 ? `${{(km * 1000).toFixed(0)}} m` : `${{km.toFixed(2)}} km`;
                        
                        const cA = coordsPts[0];
                        const cB = coordsPts[coordsPts.length - 1];
                        const rumbo = turf.bearing(cA, cB);
                        const azimut = (rumbo + 360) % 360;
                        const midCoord = coordsPts[Math.floor(coordsPts.length / 2)];

                        return {{
                            coords: midCoord,
                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📏 Transecto A - A'</div>` +
                                   `<div style="font-size:10.5px; color:#334155;">` +
                                   `<b>Distancia:</b> ${{distFormato}}<br>` +
                                   `<b>Azimut:</b> ${{azimut.toFixed(1)}}°` +
                                   `</div>`,
                            panel: `<b>📏 Transecto Geodésico A - A'</b><br>` +
                                   `<b>Longitud Total:</b> ${{distFormato}}<br>` +
                                   `<b>Azimut Geográfico:</b> ${{azimut.toFixed(1)}}°<br>` +
                                   `<b>Extremo A:</b> ${{cA[1].toFixed(4)}}° N, ${{cA[0].toFixed(4)}}° W<br>` +
                                   `<b>Extremo A':</b> ${{cB[1].toFixed(4)}}° N, ${{cB[0].toFixed(4)}}° W`
                        }};
                    }}

                    if (props.esCirculo || props.radioM) {{
                        const radioM = props.radioM || 2500;
                        const areaHa = props.areaHa || (turf.area(feat) / 10000).toFixed(2);
                        const radioTxt = radioM >= 1000 ? `${{(radioM / 1000).toFixed(2)}} km` : `${{radioM}} m`;
                        const areaKm2 = (turf.area(feat) / 1e6).toFixed(2);
                        return {{
                            coords: turf.centroid(feat).geometry.coordinates,
                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">🎯 Simulación de Densificación</div>` +
                                   `<div style="font-size:10.5px; color:#334155;">` +
                                   `<b>Radio de Prueba:</b> ${{radioTxt}}<br>` +
                                   `<b>Cobertura Aportada:</b> ${{areaKm2}} km² (${{areaHa}} ha)` +
                                   `</div>`,
                            panel: `<b>🎯 Simulación de Pozo Propuesto</b><br>` +
                                   `<b>Radio de Influencia:</b> ${{radioTxt}}<br>` +
                                   `<b>Superficie que Cubriría:</b> ${{areaKm2}} km² (${{areaHa}} ha)<br>` +
                                   `<b>Perímetro:</b> ${{(2 * Math.PI * radioM / 1000).toFixed(2)}} km`
                        }};
                    }}

                    if (tipo === 'Polygon') {{
                        const m2 = turf.area(feat);
                        const ha = (m2 / 10000).toFixed(2);
                        const km2 = (m2 / 1e6).toFixed(2);
                        const kmPerim = turf.length(turf.polygonToLine(feat), {{ units: 'kilometers' }}).toFixed(2);
                        return {{
                            coords: turf.centroid(feat).geometry.coordinates,
                            badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📐 Área Delimitada</div>` +
                                   `<div style="font-size:10.5px; color:#334155;">` +
                                   `<b>Superficie:</b> ${{km2}} km² (${{ha}} ha)<br>` +
                                   `<b>Perímetro:</b> ${{kmPerim}} km` +
                                   `</div>`,
                            panel: `<b>📐 Polígono de Medición</b><br>` +
                                   `<b>Superficie:</b> ${{km2}} km² (${{ha}} ha)<br>` +
                                   `<b>Perímetro:</b> ${{kmPerim}} km`
                        }};
                    }}
                    return null;
                }}

                function actualizarMedicionCompleta(feat, mostrarBadge) {{
                    if (!feat) return;
                    const info = obtenerInfoMedicion(feat);
                    if (!info) return;

                    const box = document.getElementById('draw-measure-box');
                    if (box) {{
                        box.style.display = 'block';
                        box.innerHTML = info.panel;
                    }}

                    if (feat.geometry.type === 'LineString') {{
                        actualizarRotulosLinea(feat);
                    }} else {{
                        limpiarRotulosLinea();
                    }}

                    const chkBadge = document.getElementById('chk-show-badge');
                    const permitirBadge = chkBadge ? chkBadge.checked : true;

                    if (mostrarBadge && permitirBadge) {{
                        if (popupDibujoActivo) popupDibujoActivo.remove();
                        popupDibujoActivo = new maplibregl.Popup({{ closeOnClick: true, offset: 12, className: 'gis-badge-popup' }})
                            .setLngLat(info.coords)
                            .setHTML(info.badge)
                            .addTo(map);
                    }}
                }}

                map.on('draw.create', (e) => {{
                    if (e.features && e.features[0]) actualizarMedicionCompleta(e.features[0], true);
                    limpiarHerramientasActivas();
                }});
                map.on('draw.update', (e) => {{
                    if (e.features && e.features[0]) actualizarMedicionCompleta(e.features[0], false);
                }});
                map.on('draw.selectionchange', (e) => {{
                    if (e.features && e.features.length > 0) {{
                        actualizarMedicionCompleta(e.features[0], true);
                    }}
                }});
                map.on('draw.delete', () => {{
                    document.getElementById('draw-measure-box').style.display = 'none';
                    limpiarRotulosLinea();
                    if (popupDibujoActivo) popupDibujoActivo.remove();
                }});

                map.on('click', (e) => {{
                    if (modoBufferActivo) {{
                        const coords = [e.lngLat.lng, e.lngLat.lat];
                        const radioKm = radioBufferMetros / 1000.0;
                        const circlePoly = turf.circle(coords, radioKm, {{ steps: 64, units: 'kilometers' }});
                        const areaHa = (turf.area(circlePoly) / 10000).toFixed(2);
                        circlePoly.properties = {{
                            esCirculo: true,
                            radioM: radioBufferMetros,
                            areaHa: areaHa
                        }};
                        draw.add(circlePoly);
                        detenerModoBuffer();
                        actualizarMedicionCompleta(circlePoly, true);
                    }}
                }});
            </script>
        </body>
        </html>
        """
        components.html(html_maplibre_cob, height=680)

        st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)
        col_diag1, col_diag2 = st.columns([1.35, 1.65], gap="large")

        with col_diag1:
            st.markdown("<p style='font-weight:700; color:#691C32; margin-bottom:6px; font-size:13px;'>🎯 INVENTARIO DE VACÍOS CRÍTICOS Y PUNTOS PROPUESTOS</p>", unsafe_allow_html=True)
            if not res['df_propuestas'].empty:
                df_mostrar_prop = res['df_propuestas'].copy()
                df_mostrar_prop.columns = ['ID', 'Longitud (°W)', 'Latitud (°N)', 'Vacío (km²)', 'Dist. Pozo (km)', 'Prioridad']
                st.dataframe(df_mostrar_prop, use_container_width=True, hide_index=True, height=270)
            else:
                st.success("🎉 No se identificaron vacíos que superen el umbral crítico seleccionado. La red cuenta con una cobertura homogénea para este radio.")

        with col_diag2:
            st.markdown("<p style='font-weight:700; color:#691C32; margin-bottom:6px; font-size:13px;'>📋 EVALUACIÓN NORMATIVA DE DENSIDAD DE RED (CONAGUA / OMM)</p>", unsafe_allow_html=True)

            df_omm = pd.DataFrame([
                {
                    "Régimen Hidrogeológico": "Acuífero en Sobreexplotación / Urbano-Industrial",
                    "Densidad OMM Sugerida": "1 pozo cada 25 – 50 km²",
                    "Radio Típico": "3.0 – 4.0 km",
                    "Cumplimiento Actual": "✅ Conforme" if res['km2_por_pozo'] <= 50 else "⚠️ Densidad Baja"
                },
                {
                    "Régimen Hidrogeológico": "Acuífero Agrícola Intensivo",
                    "Densidad OMM Sugerida": "1 pozo cada 50 – 100 km²",
                    "Radio Típico": "4.0 – 5.5 km",
                    "Cumplimiento Actual": "✅ Conforme" if res['km2_por_pozo'] <= 100 else "⚠️ Densidad Baja"
                },
                {
                    "Régimen Hidrogeológico": "Acuífero Regional / Explotación Baja",
                    "Densidad OMM Sugerida": "1 pozo cada 100 – 250 km²",
                    "Radio Típico": "5.5 – 9.0 km",
                    "Cumplimiento Actual": "✅ Conforme" if res['km2_por_pozo'] <= 250 else "❌ Deficiente"
                }
            ])
            st.dataframe(df_omm, use_container_width=True, hide_index=True, height=140)

            st.markdown(f"""
                <div style="background-color:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; padding:10px 14px; font-size:11.5px; color:#334155; line-height:1.5;">
                    <b>Diagnóstico de Representatividad:</b> La red evaluada cuenta con <b>{res['n_pozos']} pozos de observación</b> para una superficie acuífera de <b>{res['area_total_km2']:,.1f} km²</b>, 
                    lo que arroja un promedio de <b>1 pozo cada {res['km2_por_pozo']:.1f} km²</b> ({res['densidad_1000km2']:.2f} pozos por cada 1,000 km²).<br>
                    Con un radio de representatividad piezométrica de <b>{radio_km:.1f} km</b>, se cubre el <b style="color:{res['color_diagnostico']};">{res['pct_cubierta']:.1f}%</b> del acuífero, 
                    mientras que <b>{res['area_ciega_km2']:,.1f} km² ({res['pct_ciega']:.1f}%)</b> corresponden a zonas ciegas donde cualquier interpolación geostadística extrapola con elevada incertidumbre.
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<p style='font-weight:700; color:#691C32; margin-bottom:8px; font-size:13px;'>💾 EXPORTACIÓN DE RESULTADOS SIG Y DIAGNÓSTICO (CERO-RERUN)</p>", unsafe_allow_html=True)
            c_d1, c_d2, c_d3, c_d4, c_d5 = st.columns(5)

            if shp_ciegas_zip:
                btn_shp_ciegas = generar_enlace_descarga(
                    shp_ciegas_zip, f"zonas_ciegas_{clave_actual}_{radio_km:.1f}km.zip",
                    "application/zip", "📦 Shapefile Zonas Ciegas (.zip)"
                )
                c_d1.markdown(btn_shp_ciegas, unsafe_allow_html=True)
            else:
                btn_json_ciegas = generar_enlace_descarga(
                    geojson_ciega_str.encode('utf-8'), f"zonas_ciegas_{clave_actual}_{radio_km:.1f}km.geojson",
                    "application/geo+json", "📄 GeoJSON Zonas Ciegas"
                )
                c_d1.markdown(btn_json_ciegas, unsafe_allow_html=True)

            if shp_cubierta_zip:
                btn_shp_cubierta = generar_enlace_descarga(
                    shp_cubierta_zip, f"cobertura_buffers_{clave_actual}_{radio_km:.1f}km.zip",
                    "application/zip", "📦 Shapefile Cobertura (.zip)"
                )
                c_d2.markdown(btn_shp_cubierta, unsafe_allow_html=True)
            else:
                btn_json_cubierta = generar_enlace_descarga(
                    geojson_cubierta_str.encode('utf-8'), f"cobertura_buffers_{clave_actual}_{radio_km:.1f}km.geojson",
                    "application/geo+json", "📄 GeoJSON Cobertura"
                )
                c_d2.markdown(btn_json_cubierta, unsafe_allow_html=True)

            if shp_propuestas_zip:
                btn_shp_prop = generar_enlace_descarga(
                    shp_propuestas_zip, f"propuesta_pozos_{clave_actual}.zip",
                    "application/zip", "🎯 Shapefile Nuevos Pozos (.zip)"
                )
                c_d3.markdown(btn_shp_prop, unsafe_allow_html=True)
            else:
                btn_json_prop = generar_enlace_descarga(
                    geojson_propuestas_str.encode('utf-8'), f"propuesta_pozos_{clave_actual}.geojson",
                    "application/geo+json", "🎯 GeoJSON Nuevos Pozos"
                )
                c_d3.markdown(btn_json_prop, unsafe_allow_html=True)

            if not res['df_propuestas'].empty:
                csv_prop = res['df_propuestas'].to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                btn_csv = generar_enlace_descarga(
                    csv_prop, f"propuesta_pozos_{clave_actual}.csv",
                    "text/csv", "📊 CSV Inventario de Vacíos"
                )
                c_d4.markdown(btn_csv, unsafe_allow_html=True)
            else:
                c_d4.info("Sin vacíos para exportar")

            kmz_cob_bytes = generar_kmz_cobertura(
                clave_actual, nombre_actual, radio_km,
                geojson_ciega_str, geojson_cubierta_str,
                df_unicos, res.get('df_propuestas'), delim_geom=geom_activa,
                res_metricas=res,
                geojson_geo=geojson_geo_cob_str,
                geojson_repda=geojson_repda_tab3_str if tiene_repda_tab3 else None
            )
            btn_kmz_cob = generar_enlace_descarga(
                kmz_cob_bytes, f"cobertura_zonas_ciegas_{clave_actual}_{radio_km:.1f}km.kmz",
                "application/vnd.google-earth.kmz", "🌐 Paquete KMZ (Google Earth)"
            )
            c_d5.markdown(btn_kmz_cob, unsafe_allow_html=True)

    renderizar_pestaña_cobertura()

# --- EJE 2: HIDROGRAMAS INTELIGENTES ---
with tab_hidrograma:
    @st.fragment
    def renderizar_pestaña_hidrograma():
        st.write("Selecciona un pozo de la red de monitoreo para analizar su comportamiento temporal y su tasa de abatimiento matemática.")
        
        c_h1, c_h2 = st.columns([1.5, 1])
        pozo_sel = c_h1.selectbox("🎯 Filtrar por Pozo de Monitoreo:", pozos_disponibles)
        var_hidro = c_h2.radio("Variable a Graficar:", ["Profundidad del Nivel (m)", "Carga Hidráulica (msnm)"], horizontal=True)
        col_y_hidro = 'Profundidad_NE' if "Profundidad" in var_hidro else 'Carga_Hidraulica'
        
        df_pozo_raw = df_ac[df_ac['Pozo'].astype(str) == str(pozo_sel)].dropna(subset=['Año', col_y_hidro])
        # Promediar si existen mediciones estacionales en el mismo año
        df_pozo = df_pozo_raw.groupby('Año')[col_y_hidro].mean().reset_index().sort_values(by='Año')
        
        if len(df_pozo) >= 2:
            x = df_pozo['Año'].values
            y = df_pozo[col_y_hidro].values
            coeficientes = np.polyfit(x, y, 1)
            pendiente = coeficientes[0] 
            tendencia_y = np.polyval(coeficientes, x)
            
            col_m1, col_m2, col_m3 = st.columns(3)
            unidad_txt = "m" if col_y_hidro == 'Profundidad_NE' else "msnm"
            col_m1.metric("Último Valor Registrado", f"{y[-1]:.2f} {unidad_txt}")
            
            # En Profundidad_NE: pendiente > 0 significa nivel bajando (abatimiento)
            # En Carga_Hidraulica: pendiente < 0 significa carga bajando (abatimiento)
            es_abatimiento = (pendiente > 0.1) if col_y_hidro == 'Profundidad_NE' else (pendiente < -0.1)
            es_recuperacion = (pendiente < -0.1) if col_y_hidro == 'Profundidad_NE' else (pendiente > 0.1)
            
            if es_abatimiento:
                estado, color_linea = "🔴 Abatiéndose", "#9f2241"
                delta_txt = f"-{abs(pendiente):.2f} m/año"
                col_m2.metric("Ritmo de Abatimiento", delta_txt, "Pérdida de Nivel", delta_color="inverse")
            elif es_recuperacion:
                estado, color_linea = "🟢 Recuperándose", "#285c4d"
                delta_txt = f"+{abs(pendiente):.2f} m/año"
                col_m2.metric("Ritmo de Recuperación", delta_txt, "Aumento de Nivel", delta_color="normal")
            else:
                estado, color_linea = "🟡 Estable", "#b38e5d"
                delta_txt = f"{pendiente:.2f} m/año"
                col_m2.metric("Tasa de Cambio Promedio", delta_txt, "Estable", delta_color="off")
                
            col_m3.metric("Diagnóstico Físico", estado)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_pozo['Año'], y=df_pozo[col_y_hidro], mode='lines+markers', name='Medición de Campo', line=dict(color='#244062', width=2.5), marker=dict(size=8, color='#b38e5d')))
            ecuacion_txt = f"y = {pendiente:.2f}x {'+' if coeficientes[1]>0 else '-'} {abs(coeficientes[1]):.2f}"
            fig.add_trace(go.Scatter(x=df_pozo['Año'], y=tendencia_y, mode='lines', name=f'Tendencia Histórica ({ecuacion_txt})', line=dict(color=color_linea, width=2, dash='dash')))

            mitad_idx = len(x) // 2
            fig.add_annotation(x=x[mitad_idx], y=tendencia_y[mitad_idx], text=f"<b>Pendiente:<br>{pendiente:.2f} m/año</b>", showarrow=True, arrowhead=2, arrowsize=1, ax=40, ay=-40, font=dict(color=color_linea, size=11), arrowcolor=color_linea, bgcolor="rgba(255,255,255,0.9)", bordercolor=color_linea)

            layout_yaxis = dict(autorange="reversed") if col_y_hidro == 'Profundidad_NE' else dict(title="Carga Hidráulica (msnm)")
            titulo_hidro = f"Evolución Piezométrica ({var_hidro}) - Pozo: {pozo_sel}"
            fig.update_layout(title=titulo_hidro, yaxis=layout_yaxis, xaxis=dict(title="Año"), height=500, margin=dict(t=60, b=40), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No hay suficientes datos históricos para este pozo.")
    renderizar_pestaña_hidrograma()

# --- EJE 4: FORECASTING Y ALERTAS ---
with tab_alertas:
    @st.fragment
    def renderizar_pestaña_alertas():
        st.write("### 🔮 Proyección al Año 2035 (Reloj de Agotamiento)")
        resultados_alertas = []
        
        for pozo in pozos_disponibles:
            df_hist_raw = df_ac[df_ac['Pozo'].astype(str) == str(pozo)].dropna(subset=['Año', 'Profundidad_NE'])
            df_hist = df_hist_raw.groupby('Año')['Profundidad_NE'].mean().reset_index().sort_values(by='Año')
            if len(df_hist) >= 3: 
                x, y = df_hist['Año'].values, df_hist['Profundidad_NE'].values
                z = np.polyfit(x, y, 1)
                tasa = float(z[0])
                prof_actual = float(y[-1])
                anio_actual = int(x[-1])
                prof_2035 = max(0.0, float(np.polyval(z, 2035)))
                anios_dif = max(1, 2035 - anio_actual)
                caida_estimada = round(tasa * anios_dif, 2) if tasa > 0 else 0.0
                
                alerta = "🚨 Crítico" if tasa > 0.5 else ("⚠️ Precaución" if tasa > 0 else "✅ Estable / Sano")
                resultados_alertas.append({
                    "ID Pozo": str(pozo), 
                    "Tasa (m/año)": round(tasa, 2), 
                    "Último Año Medido": anio_actual, 
                    "Prof. Actual (m)": round(prof_actual, 2), 
                    "Prof. Proyectada 2035 (m)": round(prof_2035, 2), 
                    "Caída Estimada (m)": caida_estimada, 
                    "Estatus de Estrés": alerta
                })
                
        if resultados_alertas:
            df_alertas = pd.DataFrame(resultados_alertas).sort_values(by="Tasa (m/año)", ascending=False)
            def color_estatus(val):
                if "Crítico" in str(val): return "color: #9f2241; font-weight: bold; background-color: #f5e6e8;"
                if "Precaución" in str(val): return "color: #b38e5d; font-weight: bold; background-color: #fcf5eb;"
                if "Estable" in str(val): return "color: #285c4d; font-weight: bold; background-color: #e8f0ec;"
                return ""
            st.dataframe(df_alertas.style.map(color_estatus, subset=['Estatus de Estrés']).format({"Tasa (m/año)": "{:.2f}", "Prof. Actual (m)": "{:.2f}", "Prof. Proyectada 2035 (m)": "{:.2f}", "Caída Estimada (m)": "{:.2f}"}), use_container_width=True, hide_index=True)
            
            pozos_criticos = len(df_alertas[df_alertas["Estatus de Estrés"] == "🚨 Crítico"])
            if pozos_criticos > 0:
                st.error(f"**Justificación Técnica:** Se detectaron {pozos_criticos} pozos con abatimiento crítico (tasa > 0.50 m/año).")
            else:
                st.success("La red refleja estabilidad física general.")
            
            col_g1, col_g2 = st.columns([1, 1.3])
            with col_g1:
                st.write("**1. Panorama Global**")
                fig_bar = px.bar(df_alertas, x="ID Pozo", y="Tasa (m/año)", color="Estatus de Estrés", color_discrete_map={"🚨 Crítico": "#9f2241", "⚠️ Precaución": "#b38e5d", "✅ Estable / Sano": "#285c4d"})
                fig_bar.add_hline(y=0.5, line_dash="dot", annotation_text="Límite Crítico (0.5 m/año)", line_color="#9f2241")
                fig_bar.update_layout(height=450, showlegend=False)
                st.plotly_chart(fig_bar, use_container_width=True)
            with col_g2:
                st.write("**2. Proyección y Cálculo**")
                pozo_demo = st.selectbox("Selecciona un pozo:", df_alertas["ID Pozo"].tolist())
                df_pozo_demo_raw = df_ac[df_ac['Pozo'].astype(str) == pozo_demo].dropna(subset=['Año', 'Profundidad_NE'])
                df_pozo_demo = df_pozo_demo_raw.groupby('Año')['Profundidad_NE'].mean().reset_index().sort_values(by='Año')
                x, y = df_pozo_demo['Año'].values, df_pozo_demo['Profundidad_NE'].values
                z = np.polyfit(x, y, 1)
                x_proy = np.arange(x[0], 2036)
                y_proy = np.polyval(z, x_proy)
                prof_proy_2035 = max(0.0, float(np.polyval(z, 2035)))
                
                fig_demo = go.Figure()
                fig_demo.add_trace(go.Scatter(x=x_proy, y=y_proy, mode='lines', name='Regresión Lineal', line=dict(color='#888', width=1.5, dash='dot')))
                fig_demo.add_trace(go.Scatter(x=x, y=y, mode='markers', name='Datos Reales', marker=dict(color='#244062', size=8)))
                fig_demo.add_trace(go.Scatter(x=[x[-1]], y=[y[-1]], mode='markers', name='Última Medida', marker=dict(color='#b38e5d', size=12, symbol='square')))
                fig_demo.add_trace(go.Scatter(x=[2035], y=[prof_proy_2035], mode='markers', name='Proyección 2035', marker=dict(color='#9f2241', size=14, symbol='star')))
                
                if z[0] > 0:
                    fig_demo.add_shape(type="line", x0=x[-1], y0=y[-1], x1=2035, y1=y[-1], line=dict(color="gray", width=1, dash="dash"))
                    fig_demo.add_annotation(x=2035, y=(y[-1] + prof_proy_2035)/2, ax=2035, ay=y[-1], text=f"<b>Caída:<br>{prof_proy_2035 - y[-1]:.1f} m</b>", showarrow=True, arrowhead=2)
                else:
                    fig_demo.add_shape(type="line", x0=x[-1], y0=y[-1], x1=2035, y1=y[-1], line=dict(color="gray", width=1, dash="dash"))
                    fig_demo.add_annotation(x=2035, y=(y[-1] + prof_proy_2035)/2, ax=2035, ay=y[-1], text=f"<b>Recuperación:<br>{y[-1] - prof_proy_2035:.1f} m</b>", showarrow=True, arrowhead=2)
                    
                fig_demo.update_layout(yaxis=dict(autorange="reversed"), height=450)
                st.plotly_chart(fig_demo, use_container_width=True)
        else:
            st.info("ℹ️ No se identificaron pozos de monitoreo con al menos 3 años de registros históricos para generar proyecciones estadísticas al año 2035 en este acuífero.")
    renderizar_pestaña_alertas()