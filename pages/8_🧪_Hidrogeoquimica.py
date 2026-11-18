# -*- coding: utf-8 -*-
"""
pages/8_🧪_Hidrogeoquimica.py
===============================================================================
MÓDULO DE HIDROGEOQUÍMICA Y AUDITORÍA DE CALIDAD DEL AGUA SUBTERRÁNEA
Comisión Nacional del Agua (CONAGUA) - Subdirección General Técnica
Gerencia de Aguas Subterráneas / Gerencia de Calidad del Agua

Características Periciales:
  1. Ingesta universal: Excel (.xlsx, .xls), CSV y Muestras de Demostración oficiales.
  2. Descarga de Plantilla Oficial de Laboratorio (openpyxl) en un clic (Cero-Rerun).
  3. Diagrama Trilineal de Piper con rombo equilátero real y diamante de facies interactivo (OMM/UNESCO).
  4. Diagramas de Huella Iónica de Stiff multiescala y perfil semilogarítmico de Schöeller-Berkaloff.
  5. Auditoría de Balance Iónico (% CBE - Charge Balance Error).
  6. Evaluación de aptitud para riego: RAS (SAR), %Na, CSR, Wilcox y Riverside (USSL).
  7. Génesis hidrogeoquímica: Diagrama de Gibbs y Relaciones Iónicas Molares (Índice de Revelle).
  8. Semáforo pericial de cumplimiento de la NOM-127-SSA1-2021 (Agua para Consumo Humano).
  9. Geovisor SIG interactivo MapLibre GL 3.6.2 con polígono oficial CONAGUA, Workbench Dock y HUD.
 10. Centro de exportación pericial: Paquete KMZ (Google Earth), Shapefile ESRI (.zip), Excel Multidisciplinario y GeoJSON.
===============================================================================
"""

import time
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import base64
import json
import math
import html
import io
import streamlit.components.v1 as components
from shapely.geometry import Point, Polygon, mapping
import geopandas as gpd


from utils.styles import inyectar_css_oficial, banner_institucional
from core.data_loader import (
    cargar_catalogo, cargar_datos_maestros, normalizar_clave
)
from core.pmtiles_server import obtener_url_pmtiles
from core.hidrogeoquimica import (
    parse_concatenated_csv,
    generar_plantilla_excel_hidroquimica, mapear_dataframe_hidroquimico,
    procesar_muestras_hidroquimicas, auditar_norma_127,
    generar_kmz_hidrogeoquimico, generar_shapefile_hidrogeoquimico,
    generar_reporte_excel_hidrogeoquimico,
    LIMITES_NOM_127_2021
)
from core.hidro_d3_diagrams import (
    generar_diagrama_piper_d3,
    generar_diagrama_stiff_d3,
    generar_diagrama_schoeller_d3,
    generar_diagrama_wilcox_d3,
    generar_diagrama_riverside_d3,
    generar_diagrama_gibbs_d3,
    obtener_color_facies
)

# =============================================================================
# 🎨 1. CONFIGURACIÓN Y ESTILOS
# =============================================================================
st.set_page_config(layout="wide", page_title="Hidrogeoquímica y Calidad", page_icon="🧪")
inyectar_css_oficial()
banner_institucional()

# Inyección de estilos específicos para el módulo hidrogeoquímico
st.markdown("""
<style>
/* Botones de Exportación Pericial Oficial */
.card-export-pericial {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 18px 20px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    height: 100%;
    transition: transform 0.2s, box-shadow 0.2s;
}
.card-export-pericial:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(105, 28, 50, 0.12);
    border-color: #DDC9A3;
}
a.btn-export-pericial, 
a.btn-export-pericial:link, 
a.btn-export-pericial:visited, 
a.btn-export-pericial:hover, 
a.btn-export-pericial:active {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    width: 100% !important;
    box-sizing: border-box !important;
    padding: 11px 16px !important;
    background: linear-gradient(135deg, #691C32 0%, #88102B 100%) !important;
    color: #ffffff !important;
    text-decoration: none !important;
    border-radius: 7px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    text-align: center !important;
    box-shadow: 0 3px 6px rgba(105, 28, 50, 0.25) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    cursor: pointer !important;
}
a.btn-export-pericial:hover {
    background: linear-gradient(135deg, #88102B 0%, #9f2241 100%) !important;
    color: #ffffff !important;
    box-shadow: 0 6px 14px rgba(105, 28, 50, 0.35) !important;
    transform: translateY(-1px) !important;
}
</style>
""", unsafe_allow_html=True)

def generar_enlace_descarga(data, filename, mime, label, icon="📥"):
    """Genera un botón de descarga en Base64 estilizado con Cero-Rerun."""
    b64 = base64.b64encode(data).decode()
    return f"""
    <a href="data:{mime};base64,{b64}" download="{filename}" class="btn-export-pericial">
       <span>{icon}</span> <span>{label}</span>
    </a>
    """

# =============================================================================
# 📂 2. MUESTRAS DE DEMOSTRACIÓN GENÉRICAS
# =============================================================================
def obtener_muestras_demostracion():
    """Genera un set sintético de muestras de demostración para pruebas hidrogeoquímicas."""
    return pd.DataFrame([
        {
            'Muestra': 'MANANTIAL-01',
            'Tipo_Fuente': 'Manantial',
            'Fecha': '2026-10-07',
            'Latitud': 19.7485,
            'Longitud': -97.2452,
            'Elevacion': 1720.0,
            'pH': 7.42,
            'CE_uS_cm': 365.0,
            'SDT_mg_L': 235.0,
            'Dureza_mg_L': 185.0,
            'Ca_mg_L': 52.4,
            'Mg_mg_L': 13.2,
            'Na_mg_L': 14.8,
            'K_mg_L': 2.1,
            'HCO3_mg_L': 210.0,
            'CO3_mg_L': 0.0,
            'Cl_mg_L': 11.5,
            'SO4_mg_L': 18.0,
            'NO3_mg_L': 2.7,
            'F_mg_L': 0.35,
            'As_mg_L': 0.003,
            'Pb_mg_L': 0.002,
            'Fe_mg_L': 0.045,
            'Mn_mg_L': 0.012,
            'Zn_mg_L': 0.080,
            'E_Coli': 0.0
        },
        {
            'Muestra': 'MANANTIAL-02',
            'Tipo_Fuente': 'Manantial',
            'Fecha': '2026-10-07',
            'Latitud': 19.7550,
            'Longitud': -97.2510,
            'Elevacion': 1705.0,
            'pH': 7.55,
            'CE_uS_cm': 295.0,
            'SDT_mg_L': 190.0,
            'Dureza_mg_L': 145.0,
            'Ca_mg_L': 41.0,
            'Mg_mg_L': 10.4,
            'Na_mg_L': 11.5,
            'K_mg_L': 1.8,
            'HCO3_mg_L': 168.0,
            'CO3_mg_L': 0.0,
            'Cl_mg_L': 9.2,
            'SO4_mg_L': 14.0,
            'NO3_mg_L': 2.1,
            'F_mg_L': 0.28,
            'As_mg_L': 0.002,
            'Pb_mg_L': 0.001,
            'Fe_mg_L': 0.030,
            'Mn_mg_L': 0.008,
            'Zn_mg_L': 0.050,
            'E_Coli': 0.0
        },
        {
            'Muestra': 'MANANTIAL-03',
            'Tipo_Fuente': 'Manantial',
            'Fecha': '2026-10-07',
            'Latitud': 19.7610,
            'Longitud': -97.2618,
            'Elevacion': 1680.0,
            'pH': 7.65,
            'CE_uS_cm': 240.0,
            'SDT_mg_L': 156.0,
            'Dureza_mg_L': 120.0,
            'Ca_mg_L': 34.0,
            'Mg_mg_L': 8.5,
            'Na_mg_L': 9.2,
            'K_mg_L': 1.5,
            'HCO3_mg_L': 142.0,
            'CO3_mg_L': 0.0,
            'Cl_mg_L': 7.8,
            'SO4_mg_L': 12.0,
            'NO3_mg_L': 1.9,
            'F_mg_L': 0.20,
            'As_mg_L': 0.002,
            'Pb_mg_L': 0.001,
            'Fe_mg_L': 0.020,
            'Mn_mg_L': 0.005,
            'Zn_mg_L': 0.040,
            'E_Coli': 0.0
        },
        {
            'Muestra': 'MANANTIAL-04',
            'Tipo_Fuente': 'Manantial',
            'Fecha': '2026-10-07',
            'Latitud': 19.7712,
            'Longitud': -97.2750,
            'Elevacion': 1650.0,
            'pH': 7.30,
            'CE_uS_cm': 310.0,
            'SDT_mg_L': 202.0,
            'Dureza_mg_L': 160.0,
            'Ca_mg_L': 45.2,
            'Mg_mg_L': 11.5,
            'Na_mg_L': 12.8,
            'K_mg_L': 1.9,
            'HCO3_mg_L': 185.0,
            'CO3_mg_L': 0.0,
            'Cl_mg_L': 10.1,
            'SO4_mg_L': 16.5,
            'NO3_mg_L': 3.2,
            'F_mg_L': 0.30,
            'As_mg_L': 0.003,
            'Pb_mg_L': 0.002,
            'Fe_mg_L': 0.060,
            'Mn_mg_L': 0.015,
            'Zn_mg_L': 0.070,
            'E_Coli': 17.0  # Alerta biológica
        },
        {
            'Muestra': 'POZO-01',
            'Tipo_Fuente': 'Pozo Profundo',
            'Fecha': '2026-10-07',
            'Latitud': 19.7820,
            'Longitud': -97.2890,
            'Elevacion': 1610.0,
            'pH': 7.85,
            'CE_uS_cm': 720.0,
            'SDT_mg_L': 468.0,
            'Dureza_mg_L': 310.0,
            'Ca_mg_L': 84.0,
            'Mg_mg_L': 24.5,
            'Na_mg_L': 42.0,
            'K_mg_L': 5.2,
            'HCO3_mg_L': 295.0,
            'CO3_mg_L': 0.0,
            'Cl_mg_L': 38.0,
            'SO4_mg_L': 76.0,
            'NO3_mg_L': 8.4,
            'F_mg_L': 0.82,
            'As_mg_L': 0.012,  # Excede NOM-127 (LMP 0.010)
            'Pb_mg_L': 0.004,
            'Fe_mg_L': 0.285,
            'Mn_mg_L': 0.040,
            'Zn_mg_L': 0.105,
            'E_Coli': 3.0  # Excede NOM-127 (LMP 0)
        },
        {
            'Muestra': 'POZO-02',
            'Tipo_Fuente': 'Pozo Profundo',
            'Fecha': '2026-10-08',
            'Latitud': 19.7315,
            'Longitud': -97.2105,
            'Elevacion': 1750.0,
            'pH': 7.20,
            'CE_uS_cm': 1250.0,
            'SDT_mg_L': 812.0,
            'Dureza_mg_L': 520.0,  # Excede dureza NOM-127
            'Ca_mg_L': 142.0,
            'Mg_mg_L': 40.5,
            'Na_mg_L': 88.0,
            'K_mg_L': 7.8,
            'HCO3_mg_L': 340.0,
            'CO3_mg_L': 0.0,
            'Cl_mg_L': 125.0,
            'SO4_mg_L': 220.0,
            'NO3_mg_L': 14.2,  # Excede nitratos
            'F_mg_L': 1.65,   # Excede fluoruros
            'As_mg_L': 0.015,  # Excede arsénico
            'Pb_mg_L': 0.008,
            'Fe_mg_L': 0.420,  # Excede hierro
            'Mn_mg_L': 0.180,  # Excede manganeso
            'Zn_mg_L': 0.350,
            'E_Coli': 0.0
        }
    ])

# =============================================================================
# 📌 3. GESTIÓN DE SESIÓN, AUTODETECCIÓN ESPACIAL Y LIMPIEZA INTEGRAL
# =============================================================================
if "df_hidro_raw" not in st.session_state:
    st.session_state["df_hidro_raw"] = pd.DataFrame()
    st.session_state["es_demostracion_hidro"] = False
if "hidro_uploader_key" not in st.session_state:
    st.session_state["hidro_uploader_key"] = 0
if "hidro_sel_ac_ver" not in st.session_state:
    st.session_state["hidro_sel_ac_ver"] = 0
if "hidro_ultimo_archivo_sig" not in st.session_state:
    st.session_state["hidro_ultimo_archivo_sig"] = None
if "hidro_acuifero_auto_msg" not in st.session_state:
    st.session_state["hidro_acuifero_auto_msg"] = None

# Aplicar selección/limpieza pendiente de Estado y Acuífero ANTES de instanciar selectboxes
_ac_ver_cur = st.session_state.get("hidro_sel_ac_ver", 0)
_pending_ac_hidro = st.session_state.pop("_hidro_pending_edo_ac", "__UNSET__")
if _pending_ac_hidro != "__UNSET__":
    _edo_p, _ac_p = _pending_ac_hidro
    if _edo_p is not None or _ac_p is not None:
        st.session_state[f"sel_edo_hidro_{_ac_ver_cur}"] = _edo_p
        st.session_state[f"sel_ac_hidro_{_ac_ver_cur}"] = _ac_p

_HIDRO_TAB_FILTER_KEYS = [
    "piper_familias_dataset_cache",
    "piper_familias_activas",
    "sel_piper_muestra_aislada",
    "sel_stiff_focus",
    "radio_filtro_nom127",
    "radio_geo_criterio",
]

def _limpiar_filtros_tabs_hidro():
    for _k in _HIDRO_TAB_FILTER_KEYS:
        st.session_state.pop(_k, None)

def _cb_limpiar_todo_hidro():
    _old_ac_ver = st.session_state.get("hidro_sel_ac_ver", 0)
    st.session_state["df_hidro_raw"] = pd.DataFrame()
    st.session_state["es_demostracion_hidro"] = False
    st.session_state["hidro_ultimo_archivo_sig"] = None
    st.session_state["hidro_acuifero_auto_msg"] = None
    st.session_state["hidro_uploader_key"] = st.session_state.get("hidro_uploader_key", 0) + 1
    st.session_state["hidro_sel_ac_ver"] = _old_ac_ver + 1
    st.session_state.pop(f"sel_edo_hidro_{_old_ac_ver}", None)
    st.session_state.pop(f"sel_ac_hidro_{_old_ac_ver}", None)
    st.session_state.pop("_hidro_pending_edo_ac", None)
    _limpiar_filtros_tabs_hidro()

def auto_identificar_acuifero_hidro(df_mapeado, df_cat):
    """Identifica el acuífero oficial mayoritario a partir de coordenadas decimales WGS84."""
    if df_mapeado is None or df_mapeado.empty:
        return None
    if 'Latitud' not in df_mapeado.columns or 'Longitud' not in df_mapeado.columns:
        return None

    lats = pd.to_numeric(df_mapeado['Latitud'], errors='coerce')
    lons = pd.to_numeric(df_mapeado['Longitud'], errors='coerce')
    mask_val = lats.between(-90.0, 90.0) & lons.between(-180.0, 180.0) & (lats.abs() > 0.0) & (lons.abs() > 0.0)
    if not mask_val.any():
        return None

    try:
        gdf_maestro = cargar_datos_maestros()
        if gdf_maestro is None or gdf_maestro.empty:
            return None
        if gdf_maestro.crs is None:
            gdf_maestro = gdf_maestro.set_crs(epsg=4326)

        conteos = {}
        meta_gdf = {}
        for la, lo in zip(lats[mask_val], lons[mask_val]):
            pt_geom = Point(float(lo), float(la))
            idx_pos = list(gdf_maestro.sindex.intersection(pt_geom.bounds))
            if not idx_pos:
                idx_pos = list(gdf_maestro.sindex.intersection(pt_geom.buffer(0.005).bounds))
            if not idx_pos:
                continue
            cand = gdf_maestro.iloc[idx_pos]
            hits = cand[cand.geometry.contains(pt_geom)]
            if hits.empty:
                hits = cand[cand.geometry.intersects(pt_geom.buffer(0.001))]
            if hits.empty:
                continue
            fila = hits.iloc[0]
            cve = normalizar_clave(fila.get('CLV_ACUI', fila.get('CLAVE_SIGM', '')))
            if not cve:
                continue
            conteos[cve] = conteos.get(cve, 0) + 1
            if cve not in meta_gdf:
                meta_gdf[cve] = {
                    "estado": str(fila.get('NOM_EDO', fila.get('ESTADO', ''))).strip(),
                    "nombre": str(fila.get('NOM_ACUI', fila.get('ACUÍFERO', ''))).strip(),
                }

        if not conteos:
            return None

        cve_ganadora = max(conteos.keys(), key=lambda c: conteos[c])
        edo_final = meta_gdf[cve_ganadora]["estado"]
        nom_final = meta_gdf[cve_ganadora]["nombre"]

        # Emparejar con las etiquetas exactas del catálogo usado por los selectbox
        if df_cat is not None and not df_cat.empty:
            col_nom = next((c for c in ['NOM_ACUI', 'ACUÍFERO', 'ACUIFERO', 'NOMBRE_ACUIFERO'] if c in df_cat.columns), df_cat.columns[0])
            col_cve = next((c for c in ['CLV_ACUI', 'CLAVE_SIGM', 'cve_num', 'CLAVE'] if c in df_cat.columns), df_cat.columns[1])
            match_cat = df_cat[df_cat[col_cve].apply(normalizar_clave) == cve_ganadora]
            if not match_cat.empty:
                r_cat = match_cat.iloc[0]
                edo_final = str(r_cat.get('ESTADO', edo_final)).strip()
                nom_final = str(r_cat.get(col_nom, nom_final)).strip()

        return {"clave": cve_ganadora, "nombre": nom_final, "estado": edo_final, "conteo": conteos[cve_ganadora]}
    except Exception:
        return None

def _registrar_dataset_hidro(df_nuevo, es_demo, df_cat, archivo_sig=None, bump_uploader=False):
    """Carga un dataset nuevo, limpia filtros/acuífero previos y autodetecta acuífero si hay coordenadas."""
    _limpiar_filtros_tabs_hidro()
    _old_ac_ver = st.session_state.get("hidro_sel_ac_ver", 0)
    st.session_state.pop(f"sel_edo_hidro_{_old_ac_ver}", None)
    st.session_state.pop(f"sel_ac_hidro_{_old_ac_ver}", None)
    st.session_state["hidro_sel_ac_ver"] = _old_ac_ver + 1

    st.session_state["df_hidro_raw"] = df_nuevo
    st.session_state["es_demostracion_hidro"] = bool(es_demo)
    st.session_state["hidro_ultimo_archivo_sig"] = archivo_sig
    if bump_uploader:
        st.session_state["hidro_uploader_key"] = st.session_state.get("hidro_uploader_key", 0) + 1

    df_norm_tmp = mapear_dataframe_hidroquimico(df_nuevo) if df_nuevo is not None and not df_nuevo.empty else pd.DataFrame()
    det = auto_identificar_acuifero_hidro(df_norm_tmp, df_cat)
    if det:
        st.session_state["_hidro_pending_edo_ac"] = (det["estado"], det["nombre"])
        st.session_state["hidro_acuifero_auto_msg"] = f"📍 Acuífero autodetectado: **{det['clave']} - {det['nombre']}** ({det['estado']})."
    else:
        st.session_state.pop("_hidro_pending_edo_ac", None)
        st.session_state["hidro_acuifero_auto_msg"] = None

def _cb_cargar_demo_hidro():
    _df_cat = cargar_catalogo()
    _registrar_dataset_hidro(obtener_muestras_demostracion(), es_demo=True, df_cat=_df_cat, archivo_sig=None, bump_uploader=True)

# =============================================================================
# 🎛️ 4. BARRA LATERAL (INGESTA Y CONTROL DE MUESTRAS)
# =============================================================================
with st.sidebar:
    st.markdown("<h3 style='color:#691C32; margin-top:0;'>🧪 Módulo Hidrogeoquímico</h3>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:12px; color:#475569;'>Análisis de calidad del agua, clasificación de facies y evaluación agronómica / normativa.</p>", unsafe_allow_html=True)
    st.markdown("---")

    # 1. Selector de Acuífero Oficial (sin selección por defecto fantasma)
    df_cat = cargar_catalogo()
    clave_sel = None
    nombre_sel = None
    _ac_ver = st.session_state.get("hidro_sel_ac_ver", 0)

    if df_cat is not None and not df_cat.empty:
        estados = sorted([str(e) for e in df_cat['ESTADO'].dropna().unique()])
        edo_sel = st.selectbox(
            "1. Selecciona el Estado:",
            estados,
            index=None,
            placeholder="Elige un estado...",
            key=f"sel_edo_hidro_{_ac_ver}"
        )

        acuiferos = []
        df_sub = pd.DataFrame()
        col_nom = next((c for c in ['NOM_ACUI', 'ACUÍFERO', 'ACUIFERO', 'NOMBRE_ACUIFERO'] if c in df_cat.columns), df_cat.columns[0])
        col_cve = next((c for c in ['CLV_ACUI', 'CLAVE_SIGM', 'cve_num', 'CLAVE'] if c in df_cat.columns), df_cat.columns[1])
        if edo_sel:
            df_sub = df_cat[df_cat['ESTADO'] == edo_sel]
            acuiferos = sorted(df_sub[col_nom].dropna().astype(str).unique().tolist())

        ac_sel = st.selectbox(
            "2. Acuífero Evaluado:",
            acuiferos,
            index=None,
            placeholder="Elige un acuífero...",
            key=f"sel_ac_hidro_{_ac_ver}"
        )

        if edo_sel and ac_sel and not df_sub.empty:
            match_ac = df_sub[df_sub[col_nom] == ac_sel]
            if not match_ac.empty:
                clave_sel = normalizar_clave(match_ac.iloc[0][col_cve])
                nombre_sel = ac_sel

        if st.session_state.get("hidro_acuifero_auto_msg"):
            st.caption(st.session_state["hidro_acuifero_auto_msg"])

    st.markdown("---")

    # 2. Panel de Ingesta y Plantilla Excel
    st.markdown("<p style='font-weight:700; color:#691C32; font-size:13px; margin-bottom:4px;'>📥 CARGA DE DATOS DE LABORATORIO</p>", unsafe_allow_html=True)
    _up_ver = st.session_state.get("hidro_uploader_key", 0)
    archivo_subido = st.file_uploader(
        "Subir análisis (Excel .xlsx / CSV):",
        type=['xlsx', 'xls', 'csv'],
        key=f"file_uploader_hidro_{_up_ver}",
        help="Mapea automáticamente iones y parámetros (Ca, Mg, Na, K, HCO3, Cl, SO4, As, Pb, etc.). Si incluye georreferenciación, ingresa 'Latitud' y 'Longitud' en grados decimales WGS84 (ej. 19.7485, -97.2452) para ubicar en mapa y autodetectar el acuífero."
    )

    if archivo_subido is not None:
        sig_subido = (getattr(archivo_subido, "file_id", None), archivo_subido.name, getattr(archivo_subido, "size", None))
        if sig_subido != st.session_state.get("hidro_ultimo_archivo_sig"):
            try:
                if archivo_subido.name.lower().endswith(('.xlsx', '.xls')):
                    df_cargado = pd.read_excel(archivo_subido)
                else:
                    try:
                        contenido_raw = archivo_subido.getvalue().decode('utf-8-sig')
                    except Exception:
                        contenido_raw = archivo_subido.getvalue().decode('latin1', errors='replace')
                    df_cargado = parse_concatenated_csv(contenido_raw)

                if not df_cargado.empty:
                    _registrar_dataset_hidro(df_cargado, es_demo=False, df_cat=df_cat, archivo_sig=sig_subido, bump_uploader=False)
                    st.rerun()
            except Exception as e_carga:
                st.error(f"Error al leer el archivo: {e_carga}")
        elif not st.session_state.get("df_hidro_raw", pd.DataFrame()).empty:
            st.success(f"✅ Archivo cargado con éxito ({len(st.session_state['df_hidro_raw'])} muestras identificadas).")

    # Descarga de Plantilla Oficial
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    bytes_plantilla = generar_plantilla_excel_hidroquimica()
    btn_plantilla = generar_enlace_descarga(
        bytes_plantilla, "Plantilla_Oficial_Laboratorio_Hidroquimica.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Descargar Plantilla Excel (.xlsx)",
        icon="📋"
    )
    st.markdown(btn_plantilla, unsafe_allow_html=True)

    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        st.button("🧪 Cargar Demo", key="btn_demo_hidro", use_container_width=True, on_click=_cb_cargar_demo_hidro, help="Carga datos de demostración oficiales")
    with col_btn2:
        st.button("🗑️ Limpiar", key="btn_clean_hidro", use_container_width=True, on_click=_cb_limpiar_todo_hidro, help="Limpia toda el área de trabajo (muestras, archivo subido, filtros y acuífero)")

    st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:11.5px; font-weight:700; color:#691C32; margin-bottom:2px;'>⚙️ CONFIGURACIÓN ANALÍTICA</p>", unsafe_allow_html=True)
    unidad_ui = st.selectbox(
        "Unidades de entrada:",
        ["Automático", "mg/L (ppm)", "meq/L"],
        index=0,
        key="sel_unidad_entrada_hidro",
        help="En modo Automático, el sistema detecta si las concentraciones vienen en mg/L o meq/L por encabezado y contraste de balance iónico (CBE)."
    )
    mapa_unidad = {"Automático": None, "mg/L (ppm)": "mg_L", "meq/L": "meq_L"}
    unidad_forzada_sel = mapa_unidad.get(unidad_ui, None)

    estimar_ce_sdt = st.toggle(
        "📐 Estimar CE y SDT si faltan",
        value=True,
        key="toggle_estimar_ce_sdt",
        help="Si el archivo no contiene mediciones de laboratorio de Conductividad Eléctrica (CE) o Sólidos Disueltos Totales (SDT), calcula sus aproximaciones teóricas por balance iónico canónico según USGS (Hem, 1985) y Standard Methods 1030 E para permitir proyectar Wilcox, Riverside y Gibbs."
    )

# =============================================================================
# 🚀 5. MOTOR DE PROCESAMIENTO
# =============================================================================
df_crudo = st.session_state.get("df_hidro_raw", pd.DataFrame())
df_normalizado = mapear_dataframe_hidroquimico(df_crudo) if not df_crudo.empty else pd.DataFrame()
df_procesado = procesar_muestras_hidroquimicas(df_normalizado, unidad_forzada=unidad_forzada_sel, estimar_ce_sdt=estimar_ce_sdt) if not df_normalizado.empty else pd.DataFrame()
resumen_nom127, df_auditoria = auditar_norma_127(df_procesado) if not df_procesado.empty else ({}, pd.DataFrame())

# Obtener polígono oficial del acuífero (robusto, serialización limpia vía mapping sin Timestamp)
poligono_geojson = None
bounds_poligono = None
try:
    if clave_sel:
        gdf_ac = cargar_datos_maestros()
        if gdf_ac is not None and not gdf_ac.empty:
            cve_str = str(clave_sel).strip().zfill(4)
            col_cve = next((c for c in ['CLV_ACUI', 'CLAVE_SIGM', 'CLAVE'] if c in gdf_ac.columns), gdf_ac.columns[0])
            sub_geom = gdf_ac[gdf_ac[col_cve].astype(str).str.zfill(4) == cve_str]
            if not sub_geom.empty:
                geom_dict = mapping(sub_geom.iloc[0].geometry)
                nom_ac_pol = str(sub_geom.iloc[0].get('NOM_ACUI', nombre_sel or 'Acuífero Oficial'))
                poligono_geojson = {
                    "type": "Feature",
                    "geometry": geom_dict,
                    "properties": {"nombre": nom_ac_pol, "clave": cve_str}
                }
                bounds_poligono = sub_geom.total_bounds.tolist()
except Exception:
    poligono_geojson = None
    bounds_poligono = None

# =============================================================================
# 🏢 6. ENCABEZADO Y TARJETAS KPI
# =============================================================================
st.markdown(f"""
    <div style="background: linear-gradient(135deg, #f8fafc 0%, #edf2f7 100%); border-left: 5px solid #691C32; padding: 14px 20px; border-radius: 8px; margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <div>
                <h3 style="color: #691C32; margin: 0; font-size: 20px; font-weight: 700;">
                    🧪 Plataforma Integral de Hidrogeoquímica y Calidad del Agua Subterránea
                </h3>
            </div>
            <div>
                <span style="background: {'#166534' if not st.session_state.get('es_demostracion_hidro') else '#0369a1'}; color: white; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600;">
                    {'📂 Datos Locales del Usuario' if not st.session_state.get('es_demostracion_hidro') else '🔬 Set Demostrativo Oficial (CONAGUA)'}
                </span>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)

if df_procesado.empty:
    st.markdown("""
    <div style="background: linear-gradient(135deg, #f8fafc 0%, #edf2f7 100%); border: 2px dashed #691C32; border-radius: 12px; padding: 42px 30px; text-align: center; margin: 20px 0;">
        <div style="font-size: 44px; margin-bottom: 10px;">📊</div>
        <h3 style="color: #691C32; margin: 0 0 8px 0; font-size: 21px; font-weight: 700;">
            Cargar Archivo de Laboratorio Hidroquímico
        </h3>
        <p style="color: #475569; font-size: 13.5px; max-width: 650px; margin: 0 auto 18px auto; line-height: 1.55;">
            Arrastra o selecciona tu archivo en formato <b>Excel (.xlsx / .xls)</b> o <b>CSV</b> con tus análisis fisicoquímicos (iones mayores Ca²⁺, Mg²⁺, Na⁺, K⁺, HCO₃⁻, Cl⁻, SO₄²⁻, etc.).
            Si incluyes coordenadas (<b>Latitud</b> y <b>Longitud</b>), deben proporcionarse en <b>grados decimales WGS84</b> (ej. <code>19.7485</code>, <code>-97.2452</code>) para ubicar las muestras y detectar el acuífero automáticamente.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col_up_main, _ = st.columns([3, 1])
    with col_up_main:
        archivo_main = st.file_uploader(
            "Seleccionar o arrastrar archivo Excel (.xlsx / .xls) o CSV:",
            type=['xlsx', 'xls', 'csv'],
            key=f"file_uploader_main_hero_{_up_ver}"
        )
        if archivo_main is not None:
            sig_hero = (getattr(archivo_main, "file_id", None), archivo_main.name, getattr(archivo_main, "size", None))
            if sig_hero != st.session_state.get("hidro_ultimo_archivo_sig"):
                try:
                    if archivo_main.name.lower().endswith(('.xlsx', '.xls')):
                        df_cargado_hero = pd.read_excel(archivo_main)
                    else:
                        try:
                            raw_c = archivo_main.getvalue().decode('utf-8-sig')
                        except Exception:
                            raw_c = archivo_main.getvalue().decode('latin1', errors='replace')
                        df_cargado_hero = parse_concatenated_csv(raw_c)
                    if not df_cargado_hero.empty:
                        _registrar_dataset_hidro(df_cargado_hero, es_demo=False, df_cat=df_cat, archivo_sig=sig_hero, bump_uploader=False)
                        st.rerun()
                except Exception as e_hero:
                    st.error(f"Error al leer archivo: {e_hero}")

    col_h_b1, col_h_b2 = st.columns([1, 1])
    with col_h_b1:
        st.markdown(btn_plantilla, unsafe_allow_html=True)
    with col_h_b2:
        st.button("🧪 Cargar Muestras Demo Oficiales", key="btn_hero_demo", use_container_width=True, on_click=_cb_cargar_demo_hidro)

    st.stop()

# Tarjetas KPI Superiores
with st.container(border=True):
    k1, k2, k3, k4 = st.columns(4)

    n_tot = len(df_procesado)
    cbe_med = df_procesado['CBE_pct'].abs().mean() if 'CBE_pct' in df_procesado.columns else np.nan
    cbe_txt = f"± {cbe_med:.2f}%" if pd.notna(cbe_med) else "N/D"

    facies_counts = df_procesado['Facies_Piper'].value_counts() if 'Facies_Piper' in df_procesado.columns else pd.Series()
    facies_dom = facies_counts.index[0] if not facies_counts.empty else "N/D"
    pct_facies = (facies_counts.iloc[0] / n_tot * 100.0) if not facies_counts.empty else 0.0

    n_conf = resumen_nom127.get('conformes', 0)
    pct_conf = (n_conf / n_tot * 100.0) if n_tot > 0 else 0.0

    k1.metric("Muestras Evaluadas", f"{n_tot} fuentes", f"{df_procesado['Tipo_Fuente'].nunique() if 'Tipo_Fuente' in df_procesado.columns else 1} tipos de captación")
    k2.metric("Balance Iónico Promedio", cbe_txt, "Calidad Conforme" if cbe_med <= 5.0 else ("Aceptable" if cbe_med <= 10.0 else "Revisar Análisis"), delta_color="normal" if cbe_med <= 5.0 else "inverse")
    k3.metric("Facies Dominante", facies_dom, f"{pct_facies:.0f}% del total")
    k4.metric("Conformidad NOM-127", f"{pct_conf:.1f}%", f"{n_conf} de {n_tot} muestras conformes", delta_color="normal" if pct_conf >= 70.0 else "inverse")

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

# =============================================================================
# 🛠️ 7. INTERFAZ DE TABS ESPECIALIZADAS
# =============================================================================
tab_piper, tab_stiff, tab_riego, tab_gibbs, tab_nom, tab_geo, tab_export = st.tabs([
    "📊 Facies y Piper",
    "📉 Huella Iónica (Stiff / Schöeller)",
    "🌾 Aptitud para Riego",
    "🌍 Génesis Geoquímica (Gibbs)",
    "🚨 Evaluación NOM-127-SSA1-2021",
    "🗺️ Geovisor Espacial",
    "💾 Exportación Pericial"
])

# -----------------------------------------------------------------------------
# TAB 1: FACIES Y PIPER
# -----------------------------------------------------------------------------
with tab_piper:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 8px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">DIAGRAMA TRILINEAL DE PIPER - CLASIFICACIÓN DE FAMILIAS HIDROGEOQUÍMICAS</span>
        </div>
    """, unsafe_allow_html=True)

    n_incomp = int((~df_procesado['Apta_Piper']).sum()) if 'Apta_Piper' in df_procesado.columns else 0
    if n_incomp > 0:
        st.warning(f"⚠️ **{n_incomp} muestra(s) no fueron proyectadas en el diagrama trilineal** por carecer de la serie analítica completa de iones mayores (Ca²⁺, Mg²⁺, Na⁺/K⁺, HCO₃⁻, SO₄²⁻, Cl⁻). Los valores ausentes no se estimaron para preservar el rigor analítico oficial.")

    col_p_plot, col_p_info = st.columns([7.5, 4.5], gap="large")

    with col_p_info:
        with st.container(border=True):
            st.markdown("<h4 style='color:#691C32; margin:0 0 10px 0; font-size:13.5px; font-weight:700;'>🔬 Interpretación de Facies y Control</h4>", unsafe_allow_html=True)

            # Selector para aislar muestra individual
            muestras_aptas_list = sorted(df_procesado[df_procesado['Apta_Piper'] == True]['Muestra'].astype(str).tolist()) if 'Apta_Piper' in df_procesado.columns else sorted(df_procesado['Muestra'].astype(str).tolist())
            opciones_muestra = ["🔍 Todas las fuentes ({})".format(len(muestras_aptas_list))] + muestras_aptas_list
            muestra_enfocada = st.selectbox(
                "Enfocar o Aislar Fuente Individual:",
                options=opciones_muestra,
                index=0,
                key="sel_piper_muestra_aislada",
                help="Seleccione una captación específica para proyectar sus rayos analíticos hacia el diamante central."
            )

            # Ficha técnica si seleccionó una muestra individual
            if muestra_enfocada != opciones_muestra[0]:
                sub_sel = df_procesado[df_procesado['Muestra'].astype(str) == muestra_enfocada]
                if not sub_sel.empty:
                    r_sel = sub_sel.iloc[0]
                    cbe_v = r_sel.get('CBE_pct', 0.0)
                    cbe_str = f"{cbe_v:+.2f}%" if pd.notna(cbe_v) else "N/D"
                    st.markdown(f"""
                    <div style='background:#f1f5f9; border-left:3.5px solid #691C32; padding:7px 10px; border-radius:4px; margin:8px 0; font-size:11px; line-height:1.5;'>
                        <span style='font-weight:700; color:#691C32;'>📍 Fuente Enfocada: {r_sel['Muestra']}</span><br>
                        <span style='color:#334155;'><b>Facies:</b> {r_sel.get('Facies_Piper', 'N/D')}</span><br>
                        <span style='color:#475569;'><b>Cuadrante:</b> {r_sel.get('Cuadrante_Piper', 'N/D')} | <b>CBE:</b> {cbe_str}</span>
                    </div>
                    """, unsafe_allow_html=True)

            # Gestión interactiva de Familias mediante Botones de Leyenda
            todas_familias = list(facies_counts.index)
            familias_cache_key = tuple(sorted(todas_familias))

            if ('piper_familias_dataset_cache' not in st.session_state 
                or st.session_state.get('piper_familias_dataset_cache') != familias_cache_key
                or 'piper_familias_activas' not in st.session_state):
                st.session_state['piper_familias_dataset_cache'] = familias_cache_key
                st.session_state['piper_familias_activas'] = set(todas_familias)
            else:
                # Mantener solo las que pertenezcan al dataset actual sin forzar rellenado si el usuario ocultó todas
                st.session_state['piper_familias_activas'] = st.session_state['piper_familias_activas'].intersection(set(todas_familias))

            familias_activas = st.session_state['piper_familias_activas']

            def _toggle_fam(f_nombre):
                if f_nombre in st.session_state['piper_familias_activas']:
                    st.session_state['piper_familias_activas'].discard(f_nombre)
                else:
                    st.session_state['piper_familias_activas'].add(f_nombre)

            def _activar_todas():
                st.session_state['piper_familias_activas'] = set(todas_familias)

            def _limpiar_todas():
                st.session_state['piper_familias_activas'] = set()

            st.markdown("<p style='font-size:11.5px; font-weight:700; color:#334155; margin:10px 0 4px 0;'>💧 Familias Hidroquímicas (Clic en leyenda para alternar):</p>", unsafe_allow_html=True)

            col_btn_all, col_btn_none = st.columns(2)
            with col_btn_all:
                st.button("👁️ Mostrar Todas", key="btn_act_todas_fac", use_container_width=True, on_click=_activar_todas, help="Activar todas las familias hidrogeoquímicas")
            with col_btn_none:
                st.button("🚫 Ocultar Todas", key="btn_des_todas_fac", use_container_width=True, on_click=_limpiar_todas, help="Desactivar todas las familias para aislar una")

            # Inyectar estilos CSS maestros de alineación y tarjetas periciales
            css_buttons = """
            <style>
            /* 1. Botones de acción rápida compactos */
            .st-key-btn_act_todas_fac button, .st-key-btn_des_todas_fac button {
                border: 1px solid #cbd5e1 !important;
                background-color: #f8fafc !important;
                color: #334155 !important;
                font-size: 11px !important;
                font-weight: 600 !important;
                padding: 4px 6px !important;
                min-height: 29px !important;
                border-radius: 5px !important;
                justify-content: center !important;
                text-align: center !important;
            }
            .st-key-btn_act_todas_fac button:hover, .st-key-btn_des_todas_fac button:hover {
                background-color: #f1f5f9 !important;
                border-color: #94a3b8 !important;
                color: #0f172a !important;
            }

            /* 2. Alineación milimétrica, reducción de separación y retícula compacta */
            div.st-key-lista_familias_piper {
                gap: 3px !important;
                row-gap: 3px !important;
            }
            .st-key-lista_familias_piper div[data-testid="stVerticalBlock"] {
                gap: 3px !important;
                row-gap: 3px !important;
            }
            .st-key-lista_familias_piper div.stElementContainer {
                margin: 0 !important;
                padding: 0 !important;
            }
            div[class*="st-key-btn_fac_"] {
                width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            div[class*="st-key-btn_fac_"] div[data-testid="stButton"] {
                height: auto !important;
                min-height: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
            }
            div[class*="st-key-btn_fac_"] span.stTooltipHoverTarget {
                height: auto !important;
                min-height: 0 !important;
                margin: 0 !important;
                padding: 0 !important;
                justify-content: flex-start !important;
                width: 100% !important;
            }
            div[class*="st-key-btn_fac_"] span,
            div[class*="st-key-btn_fac_"] div {
                margin: 0 !important;
            }
            div[class*="st-key-btn_fac_"] button {
                display: flex !important;
                flex-direction: row !important;
                justify-content: flex-start !important;
                align-items: center !important;
                text-align: left !important;
                width: 100% !important;
                padding: 3px 8px !important;
                margin: 0 !important;
                min-height: 28px !important;
                height: 29px !important;
                border-radius: 5px !important;
                border: 1px solid #e2e8f0 !important;
                transition: all 0.12s ease-in-out !important;
            }
            div[class*="st-key-btn_fac_"] button > div,
            div[class*="st-key-btn_fac_"] button span,
            div[class*="st-key-btn_fac_"] button div[data-testid="stMarkdownContainer"] {
                display: flex !important;
                justify-content: flex-start !important;
                align-items: center !important;
                width: 100% !important;
                margin: 0 !important;
            }
            div[class*="st-key-btn_fac_"] button p {
                display: flex !important;
                align-items: center !important;
                justify-content: flex-start !important;
                text-align: left !important;
                width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
                font-size: 11px !important;
                line-height: 1.15 !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
            }
            """
            for i, fac_nom in enumerate(todas_familias):
                col_hex = obtener_color_facies(fac_nom)
                is_active = (fac_nom in familias_activas)

                if is_active:
                    css_buttons += f"""
                    .st-key-btn_fac_{i} button {{
                        border-left: 4.5px solid {col_hex} !important;
                        background-color: #ffffff !important;
                        opacity: 1.0 !important;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
                    }}
                    .st-key-btn_fac_{i} button:hover {{
                        border-color: #cbd5e1 !important;
                        border-left: 4.5px solid {col_hex} !important;
                        background-color: #f8fafc !important;
                        box-shadow: 0 2px 6px rgba(0,0,0,0.08) !important;
                    }}
                    .st-key-btn_fac_{i} button p {{
                        color: #1e293b !important;
                        font-weight: 500 !important;
                    }}
                    .st-key-btn_fac_{i} button p::before {{
                        content: "" !important;
                        display: inline-block !important;
                        width: 9px !important;
                        height: 9px !important;
                        min-width: 9px !important;
                        min-height: 9px !important;
                        border-radius: 50% !important;
                        background-color: {col_hex} !important;
                        margin-right: 8px !important;
                        box-shadow: 0 0 0 1.5px rgba(0,0,0,0.12) !important;
                        flex-shrink: 0 !important;
                    }}
                    """
                else:
                    css_buttons += f"""
                    .st-key-btn_fac_{i} button {{
                        border-left: 4.5px solid #cbd5e1 !important;
                        background-color: #f8fafc !important;
                        opacity: 0.55 !important;
                        box-shadow: none !important;
                    }}
                    .st-key-btn_fac_{i} button:hover {{
                        opacity: 0.85 !important;
                        background-color: #f1f5f9 !important;
                    }}
                    .st-key-btn_fac_{i} button p {{
                        color: #94a3b8 !important;
                        font-weight: 400 !important;
                    }}
                    .st-key-btn_fac_{i} button p::before {{
                        content: "" !important;
                        display: inline-block !important;
                        width: 9px !important;
                        height: 9px !important;
                        min-width: 9px !important;
                        min-height: 9px !important;
                        border-radius: 50% !important;
                        background-color: transparent !important;
                        border: 2px solid #94a3b8 !important;
                        margin-right: 8px !important;
                        box-shadow: none !important;
                        flex-shrink: 0 !important;
                    }}
                    """

            css_buttons += "</style>"
            st.markdown(css_buttons, unsafe_allow_html=True)

            with st.container(key="lista_familias_piper", gap="xxsmall"):
                for i, (fac_nom, c_cnt) in enumerate(facies_counts.items()):
                    pct_val = (c_cnt / n_tot) * 100.0
                    is_active = (fac_nom in familias_activas)
                    label_txt = f"{fac_nom} · {c_cnt} fuentes ({pct_val:.0f}%)"

                    st.button(
                        label_txt,
                        key=f"btn_fac_{i}",
                        use_container_width=True,
                        on_click=_toggle_fam,
                        args=(fac_nom,),
                        help=f"Clic para {'ocultar de' if is_active else 'mostrar en'} el diagrama y tabla: {fac_nom}"
                    )

            id_aislado = muestra_enfocada if muestra_enfocada != opciones_muestra[0] else None
            if len(familias_activas) == 0 and not id_aislado:
                st.info("ℹ️ Sin familias seleccionadas. Activa una familia o pulsa 'Mostrar Todas'.")

    with col_p_plot:
        mask_piper = df_procesado['Facies_Piper'].isin(familias_activas)
        if id_aislado:
            mask_piper = mask_piper | (df_procesado['Muestra'].astype(str) == str(id_aislado))
        df_piper_render = df_procesado[mask_piper].copy()
        html_piper_d3 = generar_diagrama_piper_d3(df_piper_render, muestra_aislada=id_aislado)
        st.iframe(html_piper_d3, height=800)

    with st.expander("📋 Tabla Detallada de Parámetros Trilineales, Balance Iónico e Índice de Revelle", expanded=False):
        cols_piper_tab = [
            'Muestra', 'Tipo_Fuente', 'Apta_Piper', 'Iones_Faltantes', 'Facies_Piper', 'Cuadrante_Piper', 'CBE_pct', 'CBE_Calidad',
            'Suma_Cationes_meq', 'Suma_Aniones_meq', 'pct_Ca', 'pct_Mg', 'pct_Na_K',
            'pct_HCO3_CO3', 'pct_SO4', 'pct_Cl', 'Indice_Revelle', 'Clasif_Revelle'
        ]
        cols_presentes = [c for c in cols_piper_tab if c in df_procesado.columns]
        df_tab_p = df_procesado[mask_piper][cols_presentes].copy()        
        fmt_dict = {
            'CBE_pct': '{:+.2f}%',
            'Suma_Cationes_meq': '{:.2f}',
            'Suma_Aniones_meq': '{:.2f}',
            'pct_Ca': '{:.1f}%',
            'pct_Mg': '{:.1f}%',
            'pct_Na_K': '{:.1f}%',
            'pct_HCO3_CO3': '{:.1f}%',
            'pct_SO4': '{:.1f}%',
            'pct_Cl': '{:.1f}%',
            'Indice_Revelle': '{:.3f}'
        }
        for col_f, f_pat in fmt_dict.items():
            if col_f in df_tab_p.columns:
                df_tab_p[col_f] = df_tab_p[col_f].apply(lambda x: f_pat.format(x) if pd.notna(x) and isinstance(x, (int, float, np.floating, np.integer)) else ("" if pd.isna(x) else str(x)))
        st.dataframe(df_tab_p, width="stretch", hide_index=True)

# -----------------------------------------------------------------------------
# TAB 2: HUELLA IÓNICA (STIFF / SCHÖELLER)
# -----------------------------------------------------------------------------
with tab_stiff:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 8px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">DIAGRAMAS POLIGONALES DE STIFF Y PERFILES DE SCHÖELLER-BERKALOFF</span>
        </div>
    """, unsafe_allow_html=True)

    opciones_muestras = ["Todas las Muestras"] + df_procesado['Muestra'].astype(str).tolist()
    sel_stiff_m = st.selectbox("Seleccionar Muestra para Vista Focalizada:", opciones_muestras, index=0, key="sel_stiff_focus")

    col_st1, col_st2 = st.columns([1.25, 1.0], gap="large")
    with col_st1:
        st.markdown("<p style='font-weight:700; color:#691C32; font-size:12.5px; margin-bottom:4px;'>1. Polígonos de Huella Iónica de Stiff (meq/L) - Vectorial D3.js / SVG</p>", unsafe_allow_html=True)
        html_stiff = generar_diagrama_stiff_d3(df_procesado, sel_stiff_m)
        n_m = 1 if (sel_stiff_m and sel_stiff_m != "Todas las Muestras") else len(df_procesado)
        n_filas = math.ceil(n_m / 2.0)
        h_stiff = max(360, n_filas * 270 + 80)
        st.iframe(html_stiff, height=h_stiff)

    with col_st2:
        st.markdown("<p style='font-weight:700; color:#691C32; font-size:12.5px; margin-bottom:4px;'>2. Perfil Semilogarítmico de Schöeller-Berkaloff - Vectorial D3.js / SVG</p>", unsafe_allow_html=True)
        html_schoeller = generar_diagrama_schoeller_d3(df_procesado)
        st.iframe(html_schoeller, height=540)

# -----------------------------------------------------------------------------
# TAB 3: APTITUD PARA RIEGO AGRÍCOLA
# -----------------------------------------------------------------------------
with tab_riego:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 8px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">EVALUACIÓN AGROCLIMÁTICA Y APTITUD DEL AGUA PARA RIEGO</span>
        </div>
    """, unsafe_allow_html=True)

    r_col1, r_col2 = st.columns(2, gap="large")
    with r_col1:
        html_wilcox = generar_diagrama_wilcox_d3(df_procesado)
        st.iframe(html_wilcox, height=520)

    with r_col2:
        html_riverside = generar_diagrama_riverside_d3(df_procesado)
        st.iframe(html_riverside, height=520)

    with st.container(border=True):
        st.markdown("<p style='font-weight:700; color:#691C32; font-size:12.5px; margin-bottom:6px;'>📋 Tabla de Diagnóstico Agronómico por Pozo / Fuente</p>", unsafe_allow_html=True)
        cols_riego_tab = ['Muestra', 'Tipo_Fuente', 'CE_uS_cm', 'SDT_mg_L', 'RAS', 'Clasif_RAS', 'Pct_Na_Riego', 'CSR', 'Clasif_CSR']
        cols_r_pres = [c for c in cols_riego_tab if c in df_procesado.columns]
        df_riego_v = df_procesado[cols_r_pres].copy()
        fmt_riego = {
            'CE_uS_cm': '{:.0f}',
            'SDT_mg_L': '{:.1f}',
            'RAS': '{:.2f}',
            'Pct_Na_Riego': '{:.1f}%',
            'CSR': '{:+.2f}'
        }
        for col_f, f_pat in fmt_riego.items():
            if col_f in df_riego_v.columns:
                df_riego_v[col_f] = df_riego_v[col_f].apply(lambda x: f_pat.format(x) if pd.notna(x) and isinstance(x, (int, float, np.floating, np.integer)) else ("" if pd.isna(x) else str(x)))

        rename_riego = {}
        if df_procesado.get('CE_Estimada', pd.Series([False])).any():
            rename_riego['CE_uS_cm'] = 'CE (µS/cm)*'
        if df_procesado.get('SDT_Estimado', pd.Series([False])).any():
            rename_riego['SDT_mg_L'] = 'SDT (mg/L)*'
        if rename_riego:
            df_riego_v = df_riego_v.rename(columns=rename_riego)

        st.dataframe(df_riego_v, width="stretch", hide_index=True)

# -----------------------------------------------------------------------------
# TAB 4: GÉNESIS GEOQUÍMICA (GIBBS)
# -----------------------------------------------------------------------------
with tab_gibbs:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 8px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">DIAGRAMA DE GIBBS Y RELACIONES MOLARES GEOQUÍMICAS</span>
        </div>
    """, unsafe_allow_html=True)

    html_gibbs = generar_diagrama_gibbs_d3(df_procesado)
    st.iframe(html_gibbs, height=540)

    with st.expander("🔍 Relaciones Iónicas Molares e Índice de Revelle", expanded=True):
        cols_geoq = ['Muestra', 'Tipo_Fuente', 'rNa_rCl', 'rCa_rSO4', 'rCaMg_rHCO3', 'rMg_rCa', 'Indice_Revelle', 'Clasif_Revelle']
        c_g_pres = [c for c in cols_geoq if c in df_procesado.columns]
        df_geo_v = df_procesado[c_g_pres].copy()
        fmt_geo = {
            'rNa_rCl': '{:.2f}',
            'rCa_rSO4': '{:.2f}',
            'rCaMg_rHCO3': '{:.2f}',
            'rMg_rCa': '{:.2f}',
            'Indice_Revelle': '{:.3f}'
        }
        for col_f, f_pat in fmt_geo.items():
            if col_f in df_geo_v.columns:
                df_geo_v[col_f] = df_geo_v[col_f].apply(lambda x: f_pat.format(x) if pd.notna(x) and isinstance(x, (int, float, np.floating, np.integer)) else ("" if pd.isna(x) else str(x)))
        st.dataframe(df_geo_v, width="stretch", hide_index=True)

# -----------------------------------------------------------------------------
# TAB 5: AUDITORÍA NORMATIVA NOM-127-SSA1-2021
# -----------------------------------------------------------------------------
with tab_nom:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 8px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">EVALUACIÓN NOM-127-SSA1-2021 (AGUA PARA USO Y CONSUMO HUMANO)</span>
        </div>
    """, unsafe_allow_html=True)

    n1, n2, n3 = st.columns(3)
    n1.metric("Muestras Conformes", f"{resumen_nom127.get('conformes', 0)}", "Dentro de Límites Máximos Permisibles", delta_color="normal")
    n2.metric("En Alerta Preventiva", f"{resumen_nom127.get('alertas', 0)}", "Valores entre 80% y 100% del LMP", delta_color="off")
    n3.metric("No Conformes (Rebasan Norma)", f"{resumen_nom127.get('no_conformes', 0)}", "Riesgo Sanitario Detectado", delta_color="inverse")

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    filtro_nom = st.radio(
        "Filtrar Tabla por Dictamen Normativo:",
        ["Todas las Muestras", "🚨 Solo No Conformes", "⚠️ Solo Alertas Preventivas", "✅ Solo Conformes"],
        horizontal=True,
        key="radio_filtro_nom127"
    )

    df_aud_filtrado = df_auditoria.copy()
    if filtro_nom == "🚨 Solo No Conformes":
        df_aud_filtrado = df_aud_filtrado[df_aud_filtrado['Estatus_NOM127'].str.contains("No Conforme")]
    elif filtro_nom == "⚠️ Solo Alertas Preventivas":
        df_aud_filtrado = df_aud_filtrado[df_aud_filtrado['Estatus_NOM127'].str.contains("Alerta")]
    elif filtro_nom == "✅ Solo Conformes":
        df_aud_filtrado = df_aud_filtrado[df_aud_filtrado['Estatus_NOM127'].str.contains(r"Conforme \(Dentro")]

    def color_estatus_nom(val):
        if "No Conforme" in str(val): return "color: #9f2241; font-weight: bold; background-color: #fce7eb;"
        elif "Alerta" in str(val): return "color: #b45309; font-weight: bold; background-color: #fef3c7;"
        elif "Conforme" in str(val): return "color: #166534; font-weight: bold; background-color: #dcfce7;"
        return ""

    cols_nom_show = ['Muestra', 'Tipo_Fuente', 'Estatus_NOM127', 'Total_Evaluados', 'Conformes', 'Alertas', 'No_Conformes', 'Parametros_Excedidos', 'Parametros_Alerta']
    cols_nom_pres = [c for c in cols_nom_show if c in df_aud_filtrado.columns]
    st.dataframe(df_aud_filtrado[cols_nom_pres], width="stretch", hide_index=True)

    with st.expander("📚 Catálogo Oficial de Límites Máximos Permisibles (NOM-127-SSA1-2021)", expanded=False):
        guia_norma = [
            {'Parámetro': v['nombre'], 'Categoría': v['categoria'], 'LMP': f"{v['lmp']} {v['unidad']}", 'Tipo': 'Máximo' if v['tipo'] == 'max' else 'Mínimo'}
            for v in LIMITES_NOM_127_2021.values()
        ]
        st.dataframe(pd.DataFrame(guia_norma), width="stretch", hide_index=True)

# -----------------------------------------------------------------------------
# TAB 6: GEOVISOR ESPACIAL DE CALIDAD DEL AGUA
# -----------------------------------------------------------------------------
with tab_geo:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 8px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">DISTRIBUCIÓN ESPACIAL DE FUENTES DE MONITOREO Y CALIDAD DEL AGUA</span>
        </div>
    """, unsafe_allow_html=True)

    if 'Latitud' in df_procesado.columns and 'Longitud' in df_procesado.columns:
        _df_g_tmp = df_procesado.copy()
        _df_g_tmp['Latitud'] = pd.to_numeric(_df_g_tmp['Latitud'], errors='coerce')
        _df_g_tmp['Longitud'] = pd.to_numeric(_df_g_tmp['Longitud'], errors='coerce')
        _df_g_tmp = _df_g_tmp.dropna(subset=['Latitud', 'Longitud'])
        df_geo_pts = _df_g_tmp[
            _df_g_tmp['Latitud'].between(-90.0, 90.0) & _df_g_tmp['Longitud'].between(-180.0, 180.0)
        ].copy()
    else:
        df_geo_pts = pd.DataFrame()

    tiene_muestras_geo = not df_geo_pts.empty
    if not tiene_muestras_geo:
        if poligono_geojson is not None:
            st.info("ℹ️ El archivo cargado no incluye coordenadas en grados decimales ('Latitud' y 'Longitud'); se despliega el polígono del acuífero seleccionado y las capas de contexto.")
        else:
            st.info("ℹ️ El archivo cargado no incluye coordenadas en grados decimales ('Latitud' y 'Longitud') y no hay acuífero seleccionado. Se muestra la vista nacional; selecciona un Estado y Acuífero en la barra lateral o ubica coordenadas decimales en el panel SIG.")

    if tiene_muestras_geo:
        if 'Estatus_NOM127' not in df_geo_pts.columns and not df_auditoria.empty:
            df_geo_pts = df_geo_pts.merge(df_auditoria[['Muestra', 'Estatus_NOM127', 'Parametros_Excedidos']], on='Muestra', how='left')

        col_criterio = st.radio(
            "Simbología de Fuentes en Geovisor:",
            ["Por Facies Hidrogeoquímica (Piper)", "Por Cumplimiento NOM-127-SSA1-2021"],
            horizontal=True,
            key="radio_geo_criterio"
        )
    else:
        col_criterio = "Por Facies Hidrogeoquímica (Piper)"

    # Centro y encuadre inicial garantizados con o sin coordenadas de muestras
    if tiene_muestras_geo:
        c_lat_cen = float(df_geo_pts['Latitud'].mean())
        c_lon_cen = float(df_geo_pts['Longitud'].mean())
        min_lon = float(df_geo_pts['Longitud'].min())
        max_lon = float(df_geo_pts['Longitud'].max())
        min_lat = float(df_geo_pts['Latitud'].min())
        max_lat = float(df_geo_pts['Latitud'].max())
        if (max_lon - min_lon) < 0.015:
            min_lon, max_lon = c_lon_cen - 0.015, c_lon_cen + 0.015
        if (max_lat - min_lat) < 0.015:
            min_lat, max_lat = c_lat_cen - 0.015, c_lat_cen + 0.015
        bounds_encuadre = [min_lon, min_lat, max_lon, max_lat]
    elif bounds_poligono and len(bounds_poligono) == 4:
        c_lon_cen = float((bounds_poligono[0] + bounds_poligono[2]) / 2.0)
        c_lat_cen = float((bounds_poligono[1] + bounds_poligono[3]) / 2.0)
        bounds_encuadre = bounds_poligono
    else:
        c_lat_cen = 23.6345
        c_lon_cen = -102.5528
        bounds_encuadre = [-117.5, 14.5, -86.5, 32.8]

    # Construir GeoJSON de puntos (seguro ante nulos/NaN)
    features_pts = []
    if tiene_muestras_geo:
        for _, r in df_geo_pts.iterrows():
            id_m = html.escape(str(r.get('Muestra', 'Muestra')))
            tipo_f = html.escape(str(r.get('Tipo_Fuente', 'Fuente') if pd.notna(r.get('Tipo_Fuente')) else 'Fuente'))
            facies_raw = str(r.get('Facies_Piper', 'N/D') if pd.notna(r.get('Facies_Piper')) else 'N/D')
            facies = html.escape(facies_raw)
            estatus_raw = str(r.get('Estatus_NOM127', 'Conforme') if pd.notna(r.get('Estatus_NOM127')) else 'Conforme')
            estatus = html.escape(estatus_raw)
            exc = html.escape(str(r.get('Parametros_Excedidos', 'Ninguno') if pd.notna(r.get('Parametros_Excedidos')) else 'Ninguno'))

            sdt_v = r.get('SDT_mg_L', np.nan)
            ce_v = r.get('CE_uS_cm', np.nan)
            cbe_v = r.get('CBE_pct', np.nan)
            rev_v = r.get('Indice_Revelle', np.nan)
            sdt_txt = f"{float(sdt_v):,.1f} mg/L" if pd.notna(sdt_v) else "S/D"
            ce_txt = f"{float(ce_v):,.0f} µS/cm" if pd.notna(ce_v) else "S/D"
            cbe_txt = f"{float(cbe_v):+.2f}%" if pd.notna(cbe_v) else "S/D"
            rev_txt = f"{float(rev_v):.2f}" if pd.notna(rev_v) else "S/D"

            if "Piper" in col_criterio:
                color_pt = obtener_color_facies(facies_raw)
            else:
                if "No Conforme" in estatus_raw:
                    color_pt = "#dc2626"
                elif "Alerta" in estatus_raw:
                    color_pt = "#d97706"
                else:
                    color_pt = "#16a34a"

            popup_html = f"""
            <div style='font-family: Segoe UI, Arial, sans-serif; font-size: 11.5px; line-height: 1.45; color: #1e293b; min-width: 245px;'>
              <div style='background: #691C32; color: white; padding: 6px 10px; font-weight: 700; border-radius: 4px 4px 0 0; margin: -6px -10px 6px -10px;'>
                🧪 {id_m} ({tipo_f})
              </div>
              <div><b>Facies:</b> {facies}</div>
              <div><b>Dictamen NOM-127:</b> {estatus}</div>
              <div><b>SDT:</b> {sdt_txt} | <b>CE:</b> {ce_txt}</div>
              <div><b>Balance CBE:</b> {cbe_txt} | <b>Revelle:</b> {rev_txt}</div>
              <hr style='margin: 5px 0; border: 0; border-top: 1px solid #e2e8f0;'>
              <div><b>Fuera de Norma:</b> <span style='color:#dc2626; font-weight:600;'>{exc}</span></div>
            </div>
            """

            features_pts.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r['Longitud']), float(r['Latitud'])]
                },
                "properties": {
                    "id": id_m,
                    "tipo": tipo_f,
                    "color": color_pt,
                    "facies": facies,
                    "estatus": estatus,
                    "popup": popup_html
                }
            })

    geojson_muestras_str = json.dumps({"type": "FeatureCollection", "features": features_pts})
    geojson_poly_str = json.dumps(poligono_geojson) if poligono_geojson else "null"
    bounds_encuadre_str = json.dumps(bounds_encuadre)
    url_pmtiles_srv_geo = obtener_url_pmtiles()
    tiene_poligono_geo = poligono_geojson is not None
    n_muestras_geo = len(features_pts)

    # Bloques de leyenda sincronizados con los checkboxes del Dock
    if tiene_muestras_geo:
        if "Piper" in col_criterio:
            leg_muestras_items = """
            <div id='leg-muestras'>
                <div style='font-weight:700; color:#691C32; margin-bottom:3px; font-size:11px;'>Facies Hidrogeoquímicas:</div>
                <div><i style='background:#0284c7;'></i> Bicarbonatada Cálcica</div>
                <div><i style='background:#7c3aed;'></i> Bicarbonatada Sódica</div>
                <div><i style='background:#dc2626;'></i> Clorurada Sódica</div>
                <div><i style='background:#d97706;'></i> Sulfatada Cálcica</div>
                <div><i style='background:#059669;'></i> Mixta / Otra</div>
            </div>
            """
        else:
            leg_muestras_items = """
            <div id='leg-muestras'>
                <div style='font-weight:700; color:#691C32; margin-bottom:3px; font-size:11px;'>Dictamen NOM-127:</div>
                <div><i style='background:#16a34a;'></i> Conforme (Apta)</div>
                <div><i style='background:#d97706;'></i> Alerta Preventiva</div>
                <div><i style='background:#dc2626;'></i> No Conforme (Rebasa)</div>
            </div>
            """
    else:
        leg_muestras_items = ""

    leg_acuifero_html = (
        "<div id='leg-acuifero' style='margin-top:4px;'><i class='square' style='background:rgba(105,28,50,0.20); border:1.5px solid #691C32;'></i> Polígono del Acuífero</div>"
        if tiene_poligono_geo else ""
    )

    chk_muestras_html = (
        f"<label><input type='checkbox' id='chk-muestras' checked> 🧪 Fuentes de Monitoreo ({n_muestras_geo})</label>"
        if tiene_muestras_geo else ""
    )
    chk_acuifero_html = (
        "<label><input type='checkbox' id='chk-acuifero' checked> 🛡️ Delimitación Acuífero</label>"
        if tiene_poligono_geo else ""
    )
    opac_poly_html = """
        <div class="dock-section" id="sec-opac-poly">
            <label style="font-weight:700; color:#691C32; margin-bottom:2px;">🎨 Opacidad Acuífero: <span id="val-opac-poly">20%</span></label>
            <input type="range" class="slider-ctrl" id="slider-opac-poly" min="0" max="100" step="5" value="20" oninput="ajustarOpacidadPoligono(this.value)">
        </div>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;">
    """ if tiene_poligono_geo else ""

    html_maplibre = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="utf-8" />
        <title>Geovisor Hidrogeoquímico</title>
        <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
        <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
        <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
        <script src="https://unpkg.com/pmtiles@2.11.0/dist/index.js"></script>
        <link rel="stylesheet" href="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.css" type="text/css" />
        <script src="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/@turf/turf@6.5.0/turf.min.js"></script>
        <style>
            html, body {{ margin: 0; padding: 0; width: 100%; height: 100%; font-family: 'Segoe UI', Arial, sans-serif; overflow: hidden; }}
            #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; background: #f8fafc; border-radius: 8px; }}

            .btn-open-dock-circle {{
                position: absolute; top: 12px; left: 12px; z-index: 1000;
                background: #691C32; color: #ffffff; width: 38px; height: 38px;
                border-radius: 50%; border: 1.5px solid #DDC9A3;
                box-shadow: 0 3px 12px rgba(105, 28, 50, 0.35);
                font-size: 19px; font-weight: bold; cursor: pointer;
                display: flex; align-items: center; justify-content: center;
                transition: all 0.2s ease;
            }}
            .btn-open-dock-circle:hover {{ background: #88102B; transform: scale(1.08); }}

            .workbench-dock {{
                position: absolute; top: 12px; left: 12px; z-index: 2000;
                background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                width: 285px; border-radius: 10px; overflow: hidden;
                box-shadow: 0 6px 22px rgba(0,0,0,0.25); border-top: 4px solid #691C32;
                border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0;
                font-size: 11.5px; color: #1E293B;
            }}
            .dock-header {{
                background: #691C32; color: white; padding: 9px 12px;
                font-weight: 700; display: flex; justify-content: space-between; align-items: center;
            }}
            .dock-body {{ padding: 12px 14px; max-height: 72vh; overflow-y: auto; }}
            .dock-section {{ margin-bottom: 10px; }}
            .dock-section label {{ display: flex; align-items: center; gap: 6px; cursor: pointer; margin-bottom: 5px; font-weight: 500; }}
            .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; margin-top: 4px; }}
            .coord-row {{ display: flex; gap: 6px; margin-bottom: 6px; }}
            .coord-row input {{
                width: 50%; padding: 5px 7px; font-size: 11px; border: 1px solid #cbd5e1;
                border-radius: 4px; background: #ffffff; color: #1e293b; box-sizing: border-box;
            }}
            .coord-row input:focus {{ outline: none; border-color: #691C32; }}
            .btn-dock-primary {{
                flex: 1; padding: 6px 10px; background: #691C32; color: #ffffff;
                border: 1px solid #BC955C; border-radius: 4px; cursor: pointer;
                font-size: 11px; font-weight: 600; transition: background 0.15s ease;
            }}
            .btn-dock-primary:hover {{ background: #4A1424; }}
            .btn-dock-clear {{
                width: 32px; padding: 6px 0; background: #64748b; color: #ffffff;
                border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600;
            }}
            .btn-dock-clear:hover {{ background: #475569; }}
            .btn-reset-view {{
                width: 100%; padding: 7px 10px; background: #475569; color: #ffffff;
                border: none; border-radius: 5px; cursor: pointer; font-weight: 600;
                font-size: 11.5px; margin-top: 4px; transition: background 0.15s ease;
            }}
            .btn-reset-view:hover {{ background: #334155; }}

            .hud-elevation {{
                position: absolute; top: 12px; right: 55px; z-index: 1000;
                background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
                color: #1e293b; padding: 7px 14px; border-radius: 8px;
                border: 1.5px solid #691C32; box-shadow: 0 4px 15px rgba(0,0,0,0.15);
                font-size: 11.5px; display: flex; gap: 14px; align-items: center; pointer-events: none;
            }}
            .hud-elevation b {{ color: #691C32; margin-right: 4px; }}

            .legend-panel {{
                position: absolute; bottom: 25px; left: 12px; z-index: 1000;
                background: rgba(255,255,255,0.95); backdrop-filter: blur(8px);
                padding: 9px 13px; border-radius: 8px;
                box-shadow: 0 4px 14px rgba(0,0,0,0.16); font-size: 11px; line-height: 1.6;
                border: 1px solid #E2E8F0; border-top: 3px solid #691C32; max-width: 280px; pointer-events: auto;
            }}
            .legend-header {{
                display: flex; justify-content: space-between; align-items: center;
                cursor: pointer; font-size: 12px; font-weight: 700; color: #691C32; gap: 12px;
            }}
            .legend-header:hover {{ color: #88102B; }}
            .legend-body {{ overflow: hidden; transition: max-height 0.25s ease; margin-top: 6px; }}
            .legend-body.collapsed {{ max-height: 0 !important; margin-top: 0 !important; }}
            .legend-panel i {{
                width: 12px; height: 12px; display: inline-block; border-radius: 50%;
                margin-right: 6px; vertical-align: middle; border: 1px solid #fff;
                box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            }}
            .legend-panel i.square {{ border-radius: 2px; box-shadow: none; }}

            .gis-badge-popup .maplibregl-popup-content {{
                background: rgba(255, 255, 255, 0.96) !important;
                backdrop-filter: blur(8px) !important;
                border: 1px solid #CBD5E1 !important;
                border-top: 3px solid #691C32 !important;
                border-radius: 6px !important;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.20) !important;
                padding: 6px 10px !important;
                font-family: 'Segoe UI', Arial, sans-serif !important;
                line-height: 1.4 !important;
                pointer-events: auto !important;
            }}
            .gis-badge-popup .maplibregl-popup-tip {{
                border-top-color: rgba(255, 255, 255, 0.96) !important;
            }}
            .gis-badge-popup .maplibregl-popup-close-button {{
                color: #ffffff !important; font-size: 15px !important;
                top: 3px !important; right: 5px !important; padding: 2px 5px !important; cursor: pointer !important;
            }}

            .minimal-popup .maplibregl-popup-content {{
                background: rgba(26, 26, 26, 0.92) !important; color: #ffffff !important;
                border: 1px solid #BC955C !important; border-left: 3px solid #BC955C !important;
                border-radius: 4px !important; font-size: 11px !important; padding: 5px 9px !important;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important; pointer-events: none !important;
            }}
            .minimal-popup .maplibregl-popup-tip {{ display: none !important; }}

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

        <div class="hud-elevation" id="hud-coord">
            <div><b>Lon:</b> <span id="hud-lon">{c_lon_cen:.4f}</span>°</div>
            <div><b>Lat:</b> <span id="hud-lat">{c_lat_cen:.4f}</span>°</div>
            <div><b>Zoom:</b> <span id="hud-zoom">11.0</span></div>
        </div>

        <div id="btn-open-dock" class="btn-open-dock-circle" onclick="toggleDock()" title="Capas y Control SIG">☰</div>

        <div id="workbench-dock" class="workbench-dock" style="display: none;">
            <div class="dock-header">
                <span>🛠️ Capas y Control SIG</span>
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
                {opac_poly_html}
                <div class="dock-section">
                    <span style="font-weight:700; color:#691C32; display:block; margin-bottom:6px; font-size:11px;">📊 CAPAS ANALÍTICAS</span>
                    {chk_muestras_html}
                    {chk_acuifero_html}
                    <label><input type="checkbox" id="chk-repda-nac"> 🇲🇽 REPDA Nacional MVT (461,914)</label>
                </div>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;">
                <div class="dock-section">
                    <span style="font-weight:700; color:#691C32; display:block; margin-bottom:6px; font-size:11px;">📍 IR A COORDENADAS (GRADOS DECIMALES)</span>
                    <div class="coord-row">
                        <input type="text" id="coord-lat" inputmode="decimal" placeholder="Lat (ej. 19.7485)">
                        <input type="text" id="coord-lon" inputmode="decimal" placeholder="Lon (ej. -97.2452)">
                    </div>
                    <div style="display:flex; gap:6px;">
                        <button id="btn-coords" class="btn-dock-primary" type="button">Ubicar</button>
                        <button id="btn-clear-coord" class="btn-dock-clear" type="button" title="Borrar marcador">🗑️</button>
                    </div>
                    <div id="coord-error" style="display:none; color:#dc2626; font-size:10.5px; margin-top:4px; font-weight:600;">
                        ⚠️ Ingresa Latitud (-90 a 90) y Longitud (-180 a 180) en grados decimales (ej. 19.7485, -97.2452).
                    </div>
                </div>
                <button id="btn-reset-view" class="btn-reset-view" type="button" onclick="encuadrarVistaInicial()">↺ Restablecer Vista</button>
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
                    <span>Gabinete Hidrogeoquímico</span>
                </div>
                <span class="docked-draw-close" onclick="toggleDrawPanel()" title="Ocultar">&times;</span>
            </div>
            <div class="docked-draw-body">
                <div class="draw-grid">
                    <button id="btn-tool-point" class="btn-tool" onclick="activarModoDibujo('point')" title="Sondeo de ubicación y distancia a fuente cercana">
                        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/></svg>
                        Punto
                    </button>
                    <button id="btn-tool-line" class="btn-tool" onclick="activarModoDibujo('line_string')" title="Trazar transecto A-A' y medir distancia geodésica">
                        <svg viewBox="0 0 24 24"><path d="M4 20L20 4"/><circle cx="4" cy="20" r="2.5"/><circle cx="20" cy="4" r="2.5"/></svg>
                        Corte A-A'
                    </button>
                    <button id="btn-tool-poly" class="btn-tool" onclick="activarModoDibujo('polygon')" title="Calcular superficie del polígono trazado">
                        <svg viewBox="0 0 24 24"><polygon points="12 2 22 8.5 18 20 6 20 2 8.5"/></svg>
                        Polígono
                    </button>
                </div>

                <div style="margin: 8px 0; border-top: 1px solid #f1f5f9; padding-top: 8px;">
                    <div style="font-weight: 700; color: #1e293b; font-size: 10.5px; margin-bottom: 5px;">
                        <span>🎯 Radio de Influencia / Buffer</span>
                    </div>
                    <div style="display:flex; gap: 4px; align-items: center; margin-bottom: 5px;">
                        <input type="number" id="input-buffer-radio" value="1000" min="100" max="50000" step="100"
                               style="width: 70px; padding: 4px 6px; font-size: 11px; border: 1px solid #cbd5e1; border-radius: 4px;" title="Radio en metros">
                        <span style="font-size: 11px; color: #64748b;">m</span>
                        <button id="btn-tool-buffer" class="btn-tool" style="flex:1; padding: 4px 6px; font-size: 10.5px; justify-content: center;" onclick="activarModoBuffer()" title="Clic en mapa para fijar radio de influencia">
                            Fijar Radio
                        </button>
                    </div>
                    <div style="display: flex; gap: 4px;">
                        <button class="btn-preset" onclick="setBufferRadio(500)">500m</button>
                        <button class="btn-preset" onclick="setBufferRadio(1000)">1km</button>
                        <button class="btn-preset" onclick="setBufferRadio(2500)">2.5km</button>
                        <button class="btn-preset" onclick="setBufferRadio(5000)">5km</button>
                    </div>
                </div>

                <div style="display:flex; justify-content:space-between; align-items:center; margin: 6px 0; background:#f8fafc; padding: 4px 6px; border-radius:4px; border:1px solid #e2e8f0;">
                    <label style="font-size:10px; color:#475569; display:flex; align-items:center; gap:5px; cursor:pointer;" title="Mostrar u ocultar etiqueta flotante de medición">
                        <input type="checkbox" id="chk-show-badge" checked onchange="toggleMostrarBadges(this.checked)">
                        <span>Etiqueta en mapa</span>
                    </label>
                    <button class="btn-preset" onclick="deseleccionarTodo()" title="Ocultar nodos de edición para capturas limpias" style="padding:2px 6px; font-size:9.5px;">
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
                    <button class="btn-action-sm" onclick="document.getElementById('input-import-geojson-geo').click()" title="Cargar archivo GeoJSON al visor">
                        <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                        Importar
                    </button>
                    <input type="file" id="input-import-geojson-geo" accept=".geojson,.json" style="display:none;" onchange="importarDibujosGeoJSON(event)">
                </div>
            </div>
        </div>

        <div class="legend-panel" id="legend-panel">
            <div class="legend-header" id="legend-toggle">
                <span>Simbología</span>
                <span id="legend-icon" style="font-size:11px;">▼</span>
            </div>
            <div class="legend-body" id="legend-body" style="max-height: 360px;">
                {leg_muestras_items}
                {leg_acuifero_html}
                <div id="leg-repda-nac" style="display: none; margin-top:5px; border-top: 1px solid #eee; padding-top:4px;">
                    <b style="color:#166534; font-size:11px;">🇲🇽 REPDA Nacional (461,914)</b><br>
                    <div style="font-size:9.5px; color:#64748B; margin-bottom:2px;">Uso Oficial Registrado</div>
                    <div><i style="background:#16a34a;"></i> Agrícola</div>
                    <div><i style="background:#2563eb;"></i> Público Urbano</div>
                    <div><i style="background:#ca8a04;"></i> Pecuario</div>
                    <div><i style="background:#dc2626;"></i> Industrial</div>
                    <div><i style="background:#9333ea;"></i> Servicios</div>
                    <div><i style="background:#0284c7;"></i> Doméstico</div>
                    <div><i style="background:#0d9488;"></i> Diferentes Usos</div>
                </div>
            </div>
        </div>

        <script>
            let protocol = new pmtiles.Protocol();
            maplibregl.addProtocol("pmtiles", protocol.tile);

            const geojsonMuestras = {geojson_muestras_str};
            const geojsonPoligono = {geojson_poly_str};
            const boundsEncuadre = {bounds_encuadre_str};

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
                        {{ 'id': 'base-light-layer', 'type': 'raster', 'source': 'base-light', 'layout': {{ 'visibility': 'visible' }} }},
                        {{ 'id': 'base-sat-layer', 'type': 'raster', 'source': 'base-sat', 'layout': {{ 'visibility': 'none' }} }},
                        {{ 'id': 'base-topo-layer', 'type': 'raster', 'source': 'base-topo', 'layout': {{ 'visibility': 'none' }} }},
                        {{ 'id': 'base-osm-layer', 'type': 'raster', 'source': 'base-osm', 'layout': {{ 'visibility': 'none' }} }},
                        {{ 'id': 'base-street-layer', 'type': 'raster', 'source': 'base-street', 'layout': {{ 'visibility': 'none' }} }},
                        {{ 'id': 'base-terrain-layer', 'type': 'raster', 'source': 'base-terrain', 'layout': {{ 'visibility': 'none' }} }},
                        {{ 'id': 'base-ocean-layer', 'type': 'raster', 'source': 'base-ocean', 'layout': {{ 'visibility': 'none' }} }},
                        {{ 'id': 'base-dark-layer', 'type': 'raster', 'source': 'base-dark', 'layout': {{ 'visibility': 'none' }} }},
                        {{ 'id': 'base-google-layer', 'type': 'raster', 'source': 'base-google', 'layout': {{ 'visibility': 'none' }}, 'paint': {{ 'raster-opacity': 0.35, 'raster-saturation': -1.0 }} }}
                    ]
                }},
                center: [{c_lon_cen}, {c_lat_cen}],
                zoom: 10.5,
                attributionControl: false,
                preserveDrawingBuffer: true
            }});

            const iconExpandSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
            const iconCompressSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;

            class FullscreenCustomControl {{
                onAdd(mapInstance) {{
                    this._map = mapInstance;
                    this._cssFsActive = false;
                    this._savedFrameCss = null;
                    this._savedBodyCss = null;
                    this._container = document.createElement('div');
                    this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group';

                    const btn = document.createElement('button');
                    btn.id = 'btn-fs-visor';
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

                    const getFrameEl = () => {{ try {{ return window.frameElement || null; }} catch (e) {{ return null; }} }};
                    const updateBtnUI = (active) => {{
                        btn.innerHTML = active ? iconCompressSVG : iconExpandSVG;
                        btn.title = active ? 'Salir de Pantalla Completa (Esc)' : 'Pantalla Completa';
                        setTimeout(() => {{ mapInstance.resize(); }}, 160);
                    }};
                    const setCssFs = (enable) => {{
                        const frameEl = getFrameEl();
                        if (enable) {{
                            if (frameEl) {{
                                if (this._savedFrameCss === null) this._savedFrameCss = frameEl.style.cssText || '';
                                frameEl.style.cssText = (this._savedFrameCss ? this._savedFrameCss + ';' : '') +
                                    'position:fixed !important; inset:0px !important; width:100vw !important; height:100vh !important; max-width:100vw !important; z-index:999999 !important; background:#ffffff !important; border:none !important; border-radius:0 !important;';
                            }} else {{
                                if (this._savedBodyCss === null) this._savedBodyCss = document.body.style.cssText || '';
                                document.body.style.cssText = (this._savedBodyCss ? this._savedBodyCss + ';' : '') +
                                    'position:fixed !important; inset:0px !important; width:100vw !important; height:100vh !important; z-index:999999 !important; border-radius:0 !important;';
                            }}
                            this._cssFsActive = true;
                            updateBtnUI(true);
                        }} else {{
                            if (frameEl && this._savedFrameCss !== null) {{
                                frameEl.style.cssText = this._savedFrameCss;
                                this._savedFrameCss = null;
                            }}
                            if (this._savedBodyCss !== null) {{
                                document.body.style.cssText = this._savedBodyCss;
                                this._savedBodyCss = null;
                            }}
                            this._cssFsActive = false;
                            updateBtnUI(false);
                        }}
                    }};

                    btn.onclick = () => {{
                        const isFull = !!(document.fullscreenElement || document.webkitFullscreenElement || this._cssFsActive);
                        if (isFull) {{
                            if (this._cssFsActive) setCssFs(false);
                            if (document.fullscreenElement && document.exitFullscreen) {{
                                document.exitFullscreen().catch(() => {{}});
                            }} else if (document.webkitFullscreenElement && document.webkitExitFullscreen) {{
                                document.webkitExitFullscreen();
                            }}
                            return;
                        }}
                        const frameEl = getFrameEl();
                        if (frameEl) {{
                            try {{
                                frameEl.setAttribute('allowfullscreen', 'true');
                                const cur = frameEl.getAttribute('allow') || '';
                                if (!cur.includes('fullscreen')) frameEl.setAttribute('allow', (cur ? cur + '; ' : '') + 'fullscreen');
                            }} catch (e) {{}}
                        }}
                        const target = document.documentElement;
                        const req = target.requestFullscreen || target.webkitRequestFullscreen;
                        if (req) {{
                            try {{
                                Promise.resolve(req.call(target))
                                    .then(() => updateBtnUI(true))
                                    .catch(() => setCssFs(true));
                            }} catch (e) {{
                                setCssFs(true);
                            }}
                        }} else {{
                            setCssFs(true);
                        }}
                    }};

                    const onNativeFsChange = () => {{
                        const nativeActive = !!(document.fullscreenElement || document.webkitFullscreenElement);
                        if (!nativeActive && !this._cssFsActive) updateBtnUI(false);
                        else if (nativeActive) updateBtnUI(true);
                    }};
                    document.addEventListener('fullscreenchange', onNativeFsChange);
                    document.addEventListener('webkitfullscreenchange', onNativeFsChange);
                    window.addEventListener('keydown', (ev) => {{
                        if (ev.key === 'Escape' && this._cssFsActive) setCssFs(false);
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
            map.addControl(new maplibregl.NavigationControl({{ showCompass: true, showZoom: true }}), 'top-right');
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

            function isDrawingMode() {{
                const mode = draw && typeof draw.getMode === 'function' ? draw.getMode() : 'simple_select';
                return (mode && mode.startsWith('draw_')) || modoBufferActivo;
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
            let radioBufferMetros = 1000;

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
                radioBufferMetros = parseFloat(inputRadio.value) || 1000;
                document.getElementById('btn-tool-buffer').classList.add('active');
                map.getCanvas().style.cursor = 'crosshair';
                const box = document.getElementById('draw-measure-box');
                box.style.display = 'block';
                box.innerHTML = `<b>🎯 Radio de Influencia (${{(radioBufferMetros/1000).toFixed(2)}} km):</b> Clic en el mapa para fijar el área circular.`;
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
                a.download = 'mediciones_hidrogeoquimica.geojson';
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
            let popupActivo = null;
            let tempCoordMarker = null;
            const hoverTooltip = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, offset: 12, className: 'minimal-popup' }});

            function actualizarRotulosLinea(feat) {{
                limpiarRotulosLinea();
                if (!feat || !feat.geometry || feat.geometry.type !== 'LineString') return;
                const coords = feat.geometry.coordinates;
                if (!coords || coords.length < 2) return;
                const elA = document.createElement('div');
                elA.className = 'label-marker-corte label-a';
                elA.innerText = 'A';
                const elB = document.createElement('div');
                elB.className = 'label-marker-corte label-b';
                elB.innerText = "A'";
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

            function obtenerInfoMedicion(feat) {{
                if (!feat || !feat.geometry) return null;
                const tipo = feat.geometry.type;
                const props = feat.properties || {{}};

                if (tipo === 'Point') {{
                    const c = feat.geometry.coordinates;
                    let estadoAcuifero = "<span style='color:#64748B;'>Sin polígono activo</span>";
                    if (geojsonPoligono && geojsonPoligono.geometry) {{
                        const dentro = turf.booleanPointInPolygon(c, geojsonPoligono);
                        estadoAcuifero = dentro
                            ? "<span style='color:#059669; font-weight:700;'>🟢 Dentro del Acuífero Evaluado</span>"
                            : "<span style='color:#d97706; font-weight:700;'>🟠 Fuera del Polígono del Acuífero</span>";
                    }}

                    let distFuenteTxt = "--";
                    let nombreCercana = "";
                    if (geojsonMuestras && geojsonMuestras.features && geojsonMuestras.features.length > 0) {{
                        let minD = Infinity;
                        geojsonMuestras.features.forEach(ft => {{
                            const d = turf.distance(c, ft.geometry.coordinates, {{ units: 'kilometers' }});
                            if (d < minD) {{
                                minD = d;
                                nombreCercana = (ft.properties && ft.properties.id) ? ` (${{ft.properties.id}})` : '';
                            }}
                        }});
                        distFuenteTxt = (minD < 1.0 ? `${{(minD * 1000).toFixed(0)}} m` : `${{minD.toFixed(2)}} km`) + nombreCercana;
                    }}

                    return {{
                        coords: c,
                        badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">📍 Sondeo Puntual</div>` +
                               `<div style="font-size:10.5px; color:#334155;">` +
                               `<b>Acuífero:</b> ${{estadoAcuifero}}<br>` +
                               `<b>Fuente cercana:</b> <b>${{distFuenteTxt}}</b><br>` +
                               `<span style="color:#64748B; font-size:9.5px;">${{c[1].toFixed(5)}}° N, ${{c[0].toFixed(5)}}° W</span>` +
                               `</div>`,
                        panel: `<b>📍 Sondeo de Ubicación</b><br>` +
                               `<b>Acuífero:</b> ${{estadoAcuifero}}<br>` +
                               `<b>Fuente más cercana:</b> ${{distFuenteTxt}}<br>` +
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
                               `<b>Azimut:</b> ${{azimut.toFixed(1)}}°<br>` +
                               `<b>A:</b> ${{cA[1].toFixed(4)}}° N, ${{cA[0].toFixed(4)}}° W<br>` +
                               `<b>A':</b> ${{cB[1].toFixed(4)}}° N, ${{cB[0].toFixed(4)}}° W`
                    }};
                }}

                if (props.esCirculo || props.radioM) {{
                    const radioM = props.radioM || 1000;
                    const areaHa = props.areaHa || (turf.area(feat) / 10000).toFixed(2);
                    const radioTxt = radioM >= 1000 ? `${{(radioM / 1000).toFixed(2)}} km` : `${{radioM}} m`;
                    const areaKm2 = (turf.area(feat) / 1e6).toFixed(2);
                    return {{
                        coords: turf.centroid(feat).geometry.coordinates,
                        badge: `<div style="font-weight:700; color:#691C32; margin-bottom:2px; font-size:11px;">🎯 Área de Influencia</div>` +
                               `<div style="font-size:10.5px; color:#334155;">` +
                               `<b>Radio:</b> ${{radioTxt}}<br>` +
                               `<b>Superficie:</b> ${{areaKm2}} km² (${{areaHa}} ha)` +
                               `</div>`,
                        panel: `<b>🎯 Radio de Influencia (Buffer)</b><br>` +
                               `<b>Radio:</b> ${{radioTxt}}<br>` +
                               `<b>Superficie:</b> ${{areaKm2}} km² (${{areaHa}} ha)<br>` +
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

                if (feat.geometry.type === 'LineString') actualizarRotulosLinea(feat);
                else limpiarRotulosLinea();

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

            window.addEventListener('keydown', (e) => {{
                if (e.key === 'Escape') {{
                    const m = draw.getMode();
                    if ((m && m.startsWith('draw_')) || modoBufferActivo) {{
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

            const basemapLayerIds = [
                'base-light-layer', 'base-sat-layer', 'base-topo-layer',
                'base-osm-layer', 'base-street-layer', 'base-terrain-layer',
                'base-ocean-layer', 'base-dark-layer', 'base-google-layer'
            ];
            function cambiarMapaBase(selected) {{
                basemapLayerIds.forEach(id => {{
                    if (map.getLayer(id)) {{
                        map.setLayoutProperty(id, 'visibility', (id === selected) ? 'visible' : 'none');
                    }}
                }});
            }}
            const selBasemapEl = document.getElementById('sel-basemap');
            if (selBasemapEl) {{
                selBasemapEl.addEventListener('change', (e) => cambiarMapaBase(e.target.value));
            }}

            function ajustarOpacidadPoligono(val) {{
                const pct = parseFloat(val);
                const lbl = document.getElementById('val-opac-poly');
                if (lbl) lbl.innerText = Math.round(pct) + '%';
                if (map.getLayer('layer-poligono-fill')) {{
                    map.setPaintProperty('layer-poligono-fill', 'fill-opacity', pct / 100.0);
                }}
            }}

            function encuadrarVistaInicial() {{
                if (boundsEncuadre && boundsEncuadre.length === 4) {{
                    map.fitBounds([
                        [boundsEncuadre[0], boundsEncuadre[1]],
                        [boundsEncuadre[2], boundsEncuadre[3]]
                    ], {{ padding: 48, maxZoom: 13.5, duration: 750 }});
                }}
            }}

            const toggleLayerSync = (chkId, layerIds, legId = null) => {{
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

            // Leyenda colapsable
            document.getElementById('legend-toggle').onclick = function() {{
                const body = document.getElementById('legend-body');
                const icon = document.getElementById('legend-icon');
                if (body.classList.contains('collapsed')) {{
                    body.classList.remove('collapsed');
                    icon.innerText = '▼';
                }} else {{
                    body.classList.add('collapsed');
                    icon.innerText = '▲';
                }}
            }};

            // Buscador rápido Ir a Coordenadas (validación estricta en grados decimales)
            document.getElementById('btn-coords').onclick = () => {{
                const latRaw = (document.getElementById('coord-lat').value || '').trim().replace(',', '.');
                const lonRaw = (document.getElementById('coord-lon').value || '').trim().replace(',', '.');
                const reDecimal = /^-?\\d+(?:\\.\\d+)?$/;
                const err = document.getElementById('coord-error');
                if (!reDecimal.test(latRaw) || !reDecimal.test(lonRaw)) {{
                    err.style.display = 'block';
                    setTimeout(() => {{ err.style.display = 'none'; }}, 3500);
                    return;
                }}
                const lat = parseFloat(latRaw);
                const lon = parseFloat(lonRaw);
                if (isNaN(lat) || isNaN(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {{
                    err.style.display = 'block';
                    setTimeout(() => {{ err.style.display = 'none'; }}, 3500);
                    return;
                }}
                err.style.display = 'none';
                if (tempCoordMarker) tempCoordMarker.remove();
                const pop = new maplibregl.Popup({{ offset: 28, className: 'gis-badge-popup', closeButton: true }})
                    .setHTML(`<div style="font-size:11px;"><b>📍 Punto Buscado (Decimal)</b><br>Lat: ${{lat.toFixed(5)}}°<br>Lon: ${{lon.toFixed(5)}}°</div>`);
                tempCoordMarker = new maplibregl.Marker({{ color: '#691C32' }})
                    .setLngLat([lon, lat])
                    .setPopup(pop)
                    .addTo(map);
                tempCoordMarker.togglePopup();
                map.flyTo({{ center: [lon, lat], zoom: 12.5 }});
            }};

            document.getElementById('btn-clear-coord').onclick = () => {{
                if (tempCoordMarker) {{ tempCoordMarker.remove(); tempCoordMarker = null; }}
                document.getElementById('coord-lat').value = '';
                document.getElementById('coord-lon').value = '';
                document.getElementById('coord-error').style.display = 'none';
            }};

            map.on('mousemove', (e) => {{
                document.getElementById('hud-lon').innerText = e.lngLat.lng.toFixed(4);
                document.getElementById('hud-lat').innerText = e.lngLat.lat.toFixed(4);
                document.getElementById('hud-zoom').innerText = map.getZoom().toFixed(1);
            }});
            map.on('zoomend', () => {{
                document.getElementById('hud-zoom').innerText = map.getZoom().toFixed(1);
            }});

            map.on('load', () => {{
                // 1. Polígono Oficial del Acuífero
                if (geojsonPoligono && geojsonPoligono.geometry) {{
                    map.addSource('src-poligono', {{ type: 'geojson', data: geojsonPoligono }});
                    map.addLayer({{
                        id: 'layer-poligono-fill',
                        type: 'fill',
                        source: 'src-poligono',
                        paint: {{ 'fill-color': '#691C32', 'fill-opacity': 0.20 }}
                    }});
                    map.addLayer({{
                        id: 'layer-poligono-line',
                        type: 'line',
                        source: 'src-poligono',
                        paint: {{ 'line-color': '#691C32', 'line-width': 2.4 }}
                    }});
                }}

                // 2. REPDA Nacional Completo (Vector Tiles PMTiles)
                let pmtilesUrlGeo = '{url_pmtiles_srv_geo}';
                if (!pmtilesUrlGeo.startsWith('http://') && !pmtilesUrlGeo.startsWith('https://')) {{
                    let baseOrigin = (window.location && window.location.origin && window.location.origin !== 'null') ? window.location.origin : '';
                    if (!baseOrigin && document.referrer) {{
                        try {{ baseOrigin = new URL(document.referrer).origin; }} catch (err) {{}}
                    }}
                    pmtilesUrlGeo = (baseOrigin || '') + pmtilesUrlGeo;
                }}
                map.addSource('repda-nacional-src', {{
                    type: 'vector',
                    url: 'pmtiles://' + pmtilesUrlGeo,
                    minzoom: 4,
                    maxzoom: 8
                }});
                map.addLayer({{
                    id: 'repda-nacional-layer',
                    type: 'circle',
                    source: 'repda-nacional-src',
                    'source-layer': 'repda',
                    layout: {{ 'visibility': 'none' }},
                    paint: {{
                        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 1.2, 7, 2.5, 10, 4.5, 14, 7.5],
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
                            '#475569'
                        ],
                        'circle-opacity': 0.85,
                        'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 4, 0, 8, 0.4, 11, 1.0],
                        'circle-stroke-color': '#ffffff'
                    }}
                }});

                // 3. Fuentes de Muestreo Hidrogeoquímico (encima del contexto)
                map.addSource('src-muestras', {{ type: 'geojson', data: geojsonMuestras }});
                map.addLayer({{
                    id: 'layer-muestras-circle',
                    type: 'circle',
                    source: 'src-muestras',
                    paint: {{
                        'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 5.5, 10, 8.5, 14, 10.5],
                        'circle-color': ['get', 'color'],
                        'circle-stroke-width': 2.0,
                        'circle-stroke-color': '#ffffff'
                    }}
                }});

                // Sincronizar checkboxes y leyenda
                toggleLayerSync('chk-muestras', ['layer-muestras-circle'], 'leg-muestras');
                toggleLayerSync('chk-acuifero', ['layer-poligono-fill', 'layer-poligono-line'], 'leg-acuifero');
                toggleLayerSync('chk-repda-nac', ['repda-nacional-layer'], 'leg-repda-nac');

                // Hover tooltip ligero en muestras
                map.on('mousemove', 'layer-muestras-circle', (e) => {{
                    if (isDrawingMode()) {{
                        hoverTooltip.remove();
                        return;
                    }}
                    map.getCanvas().style.cursor = 'pointer';
                    const p = e.features[0].properties;
                    hoverTooltip
                        .setLngLat(e.features[0].geometry.coordinates)
                        .setHTML(`<b>🧪 ${{p.id}}</b><br><span style="color:#E2E8F0;">${{p.facies}} | ${{p.estatus}}</span>`)
                        .addTo(map);
                }});
                map.on('mouseleave', 'layer-muestras-circle', () => {{
                    if (!isDrawingMode()) map.getCanvas().style.cursor = '';
                    hoverTooltip.remove();
                }});

                // Popup completo al hacer clic en muestras
                map.on('click', 'layer-muestras-circle', (e) => {{
                    if (isDrawingMode()) return;
                    hoverTooltip.remove();
                    if (popupActivo) popupActivo.remove();
                    const f = e.features[0];
                    popupActivo = new maplibregl.Popup({{ className: 'gis-badge-popup', closeButton: true }})
                        .setLngLat(f.geometry.coordinates)
                        .setHTML(f.properties.popup)
                        .addTo(map);
                }});

                // Click en concesiones REPDA Nacional
                map.on('click', 'repda-nacional-layer', (e) => {{
                    if (isDrawingMode()) return;
                    const muestrasHit = map.queryRenderedFeatures(e.point, {{ layers: ['layer-muestras-circle'] }});
                    if (muestrasHit && muestrasHit.length > 0) return;
                    if (popupActivo) popupActivo.remove();
                    const p = e.features[0].properties;
                    const volM3 = p.v ? Number(p.v).toLocaleString('es-MX') : '--';
                    const volHm3 = p.v ? (Number(p.v) / 1e6).toFixed(3) : '--';
                    const latFmt = p.la !== undefined ? Number(p.la).toFixed(5) : e.lngLat.lat.toFixed(5);
                    const lonFmt = p.lo !== undefined ? Number(p.lo).toFixed(5) : e.lngLat.lng.toFixed(5);
                    popupActivo = new maplibregl.Popup({{ className: 'gis-badge-popup', closeButton: true }})
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
                map.on('mouseenter', 'repda-nacional-layer', () => {{ if (!isDrawingMode()) map.getCanvas().style.cursor = 'pointer'; }});
                map.on('mouseleave', 'repda-nacional-layer', () => {{ if (!isDrawingMode()) map.getCanvas().style.cursor = ''; }});

                // Encuadre automático inicial
                encuadrarVistaInicial();
            }});

            map.on('draw.create', (e) => {{
                if (e.features && e.features[0]) actualizarMedicionCompleta(e.features[0], true);
                limpiarHerramientasActivas();
            }});
            map.on('draw.update', (e) => {{
                if (e.features && e.features[0]) actualizarMedicionCompleta(e.features[0], false);
            }});
            map.on('draw.selectionchange', (e) => {{
                if (e.features && e.features.length > 0) actualizarMedicionCompleta(e.features[0], true);
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
    components.html(html_maplibre, height=680)

# -----------------------------------------------------------------------------
# TAB 7: EXPORTACIÓN PERICIAL
# -----------------------------------------------------------------------------
with tab_export:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 8px 14px; border-radius: 4px; margin-bottom: 14px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">CENTRO DE EXPORTACIÓN Y REPORTES PERICIALES (CERO-RERUN)</span>
        </div>
    """, unsafe_allow_html=True)

    c_exp1, c_exp2 = st.columns(2, gap="medium")
    c_exp3, c_exp4 = st.columns(2, gap="medium")

    if not df_procesado.empty and 'Latitud' in df_procesado.columns and 'Longitud' in df_procesado.columns:
        _df_v_tmp = df_procesado.dropna(subset=['Latitud', 'Longitud']).copy()
        df_valid_geo = _df_v_tmp[_df_v_tmp['Latitud'].between(-90.0, 90.0) & _df_v_tmp['Longitud'].between(-180.0, 180.0)].copy()
        tiene_coords = not df_valid_geo.empty
    else:
        df_valid_geo = pd.DataFrame()
        tiene_coords = False

    # 1. Google Earth KMZ
    with c_exp1:
        st.markdown("""
        <div class="card-export-pericial">
            <div>
                <h4 style="color:#691C32; margin:0 0 6px 0; font-size:15px;">🌐 Paquete KMZ (Google Earth)</h4>
                <p style="font-size:12px; color:#475569; margin-bottom:14px; line-height:1.45;">
                    Incluye puntos 3D fijados al terreno, polígono perimetral del acuífero oficial y carpetas jerárquicas organizadas por Facies y por Dictamen NOM-127 con fichas completas de laboratorio. Totalmente compatible con la app móvil de Google Earth.
                </p>
            </div>
        """, unsafe_allow_html=True)
        if tiene_coords:
            bytes_kmz = generar_kmz_hidrogeoquimico(df_valid_geo, df_auditoria, clave_sel or "Acuifero", nombre_sel or "Oficial", poligono_geojson)
            btn_kmz = generar_enlace_descarga(
                bytes_kmz, f"hidroquimica_{clave_sel or 'acuifero'}.kmz",
                "application/vnd.google-earth.kmz", "Descargar Paquete KMZ (.kmz)", icon="🌐"
            )
            st.markdown(btn_kmz, unsafe_allow_html=True)
        else:
            st.markdown("<div style='background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 12px; font-size: 11.5px; color: #64748b; text-align: center;'>⚠️ Requiere columnas de 'Latitud' y 'Longitud' georreferenciadas.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # 2. Shapefile ESRI (.zip)
    with c_exp2:
        st.markdown("""
        <div class="card-export-pericial">
            <div>
                <h4 style="color:#691C32; margin:0 0 6px 0; font-size:15px;">🗺️ Shapefile ESRI (.zip)</h4>
                <p style="font-size:12px; color:#475569; margin-bottom:14px; line-height:1.45;">
                    Capa vectorial geográfica completa con sus cuatro archivos obligatorios (.shp, .shx, .dbf, .prj) en proyección WGS84 (EPSG:4326), lista para su integración directa en QGIS, ArcGIS Pro y análisis geoespacial.
                </p>
            </div>
        """, unsafe_allow_html=True)
        if tiene_coords:
            bytes_shp = generar_shapefile_hidrogeoquimico(df_valid_geo, df_auditoria, f"hidroquimica_{clave_sel or 'acuifero'}")
            btn_shp = generar_enlace_descarga(
                bytes_shp, f"shapefile_hidroquimica_{clave_sel or 'acuifero'}.zip",
                "application/zip", "Descargar Shapefile ZIP (.zip)", icon="🗺️"
            )
            st.markdown(btn_shp, unsafe_allow_html=True)
        else:
            st.markdown("<div style='background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 12px; font-size: 11.5px; color: #64748b; text-align: center;'>⚠️ Requiere columnas de 'Latitud' y 'Longitud' georreferenciadas.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

    # 3. Libro Pericial Excel (.xlsx)
    with c_exp3:
        st.markdown("""
        <div class="card-export-pericial">
            <div>
                <h4 style="color:#691C32; margin:0 0 6px 0; font-size:15px;">📊 Libro Técnico Excel (.xlsx)</h4>
                <p style="font-size:12px; color:#475569; margin-bottom:14px; line-height:1.45;">
                    Cuaderno estructurado en 5 hojas técnicas especializadas: Concentraciones en mg/L, Miliequivalentes y Porcentajes, Evaluación de Riego Agrícola, Relaciones Geoquímicas y Dictamen Oficial de la NOM-127-SSA1-2021.
                </p>
            </div>
        """, unsafe_allow_html=True)
        bytes_excel_res = generar_reporte_excel_hidrogeoquimico(df_procesado, df_auditoria, clave_sel or "Acuifero", nombre_sel or "Oficial")
        btn_excel = generar_enlace_descarga(
            bytes_excel_res, f"Informe_Hidroquimico_{clave_sel or 'Acuifero'}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Descargar Libro Excel (.xlsx)", icon="📊"
        )
        st.markdown(btn_excel, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # 4. Capa GeoJSON
    with c_exp4:
        st.markdown("""
        <div class="card-export-pericial">
            <div>
                <h4 style="color:#691C32; margin:0 0 6px 0; font-size:15px;">🌐 Capa GeoJSON (.geojson)</h4>
                <p style="font-size:12px; color:#475569; margin-bottom:14px; line-height:1.45;">
                    Estándar web abierto compatible con MapLibre GL, Leaflet, Mapbox y GeoPandas. Incluye geometrías georreferenciadas y el diccionario completo de propiedades fisicoquímicas y diagnósticos para APIs y tableros.
                </p>
            </div>
        """, unsafe_allow_html=True)
        if tiene_coords:
            pts_geom = [Point(xy) for xy in zip(df_valid_geo['Longitud'], df_valid_geo['Latitud'])]
            gdf_pts = gpd.GeoDataFrame(df_valid_geo, geometry=pts_geom, crs="EPSG:4326")
            bytes_geojson = gdf_pts.to_json().encode('utf-8')
            btn_geojson = generar_enlace_descarga(
                bytes_geojson, f"capa_hidroquimica_{clave_sel or 'acuifero'}.geojson",
                "application/geo+json", "Descargar GeoJSON (.geojson)", icon="🌐"
            )
            st.markdown(btn_geojson, unsafe_allow_html=True)
        else:
            st.markdown("<div style='background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 6px; padding: 12px; font-size: 11.5px; color: #64748b; text-align: center;'>⚠️ Requiere columnas de 'Latitud' y 'Longitud' georreferenciadas.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
