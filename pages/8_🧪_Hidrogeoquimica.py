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
import importlib
import core.hidrogeoquimica
import core.hidro_d3_diagrams
importlib.reload(core.hidro_d3_diagrams)
importlib.reload(core.hidrogeoquimica)
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
    generar_diagrama_gibbs_d3
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
# 📂 2. MUESTRAS DE DEMOSTRACIÓN OFICIALES (MEMO CONAGUA JALACINGO / ALTOTONGA)
# =============================================================================
def obtener_muestras_demostracion():
    """Genera el dataset de demostración basado en el informe de laboratorio F-PRR1 CONAGUA."""
    return pd.DataFrame([
        {
            'Muestra': 'MAN-01_Pancho_Poza',
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
            'Muestra': 'MAN-02_Nixcamalonoa',
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
            'Muestra': 'MAN-03_Techocoapa',
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
            'Muestra': 'MAN-04_Calpulalpan',
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
            'Muestra': 'PZ-01_Jesus_Orozco',
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
            'Muestra': 'PZ-02_Agricola_Sur',
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
# 📌 3. GESTIÓN DE SESIÓN Y CARGA DE DATOS
# =============================================================================
if "df_hidro_raw" not in st.session_state:
    st.session_state["df_hidro_raw"] = pd.DataFrame()
    st.session_state["es_demostracion_hidro"] = False

# =============================================================================
# 🎛️ 4. BARRA LATERAL (INGESTA Y CONTROL DE MUESTRAS)
# =============================================================================
with st.sidebar:
    st.markdown("<h3 style='color:#691C32; margin-top:0;'>🧪 Módulo Hidrogeoquímico</h3>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:12px; color:#475569;'>Auditoría de calidad del agua, clasificación de facies y evaluación agronómica / normativa.</p>", unsafe_allow_html=True)
    st.markdown("---")

    # 1. Selector de Acuífero Oficial con Auto-detección Inteligente
    df_cat = cargar_catalogo()
    clave_sel = None
    nombre_sel = None

    if df_cat is not None and not df_cat.empty:
        estados = sorted([str(e) for e in df_cat['ESTADO'].dropna().unique()])
        idx_edo = estados.index('VERACRUZ') if 'VERACRUZ' in estados else 0
        edo_sel = st.selectbox("1. Selecciona el Estado:", estados, index=idx_edo, key="sel_edo_hidro")

        df_sub = df_cat[df_cat['ESTADO'] == edo_sel]
        col_nom = next((c for c in ['NOM_ACUI', 'ACUÍFERO', 'ACUIFERO', 'NOMBRE_ACUIFERO'] if c in df_sub.columns), df_sub.columns[0])
        col_cve = next((c for c in ['CLV_ACUI', 'CLAVE_SIGM', 'cve_num', 'CLAVE'] if c in df_sub.columns), df_sub.columns[1])
        acuiferos = sorted(df_sub[col_nom].dropna().astype(str).unique().tolist())

        # Seleccionar por defecto PEROTE-ZALAYETA si está disponible (coincide con Jalacingo / Altotonga)
        idx_ac = 0
        for i_ac, nom_ac_i in enumerate(acuiferos):
            if "PEROTE" in nom_ac_i.upper():
                idx_ac = i_ac
                break

        ac_sel = st.selectbox("2. Acuífero Evaluado:", acuiferos, index=idx_ac, key="sel_ac_hidro")

        match_ac = df_sub[df_sub[col_nom] == ac_sel]
        if not match_ac.empty:
            clave_sel = normalizar_clave(match_ac.iloc[0][col_cve])
            nombre_sel = ac_sel

    st.markdown("---")

    # 2. Panel de Ingesta y Plantilla Excel
    st.markdown("<p style='font-weight:700; color:#691C32; font-size:13px; margin-bottom:4px;'>📥 CARGA DE DATOS DE LABORATORIO</p>", unsafe_allow_html=True)
    archivo_subido = st.file_uploader(
        "Subir análisis (Excel .xlsx / CSV):",
        type=['xlsx', 'xls', 'csv'],
        key="file_uploader_hidro",
        help="El sistema mapea automáticamente los nombres de columnas de cualquier laboratorio (Ca, Mg, Na, K, HCO3, Cl, SO4, As, Pb, etc.)."
    )

    if archivo_subido is not None:
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
                st.session_state["df_hidro_raw"] = df_cargado
                st.session_state["es_demostracion_hidro"] = False
                st.success(f"✅ Archivo cargado con éxito ({len(df_cargado)} muestras identificadas).")
        except Exception as e_carga:
            st.error(f"Error al leer el archivo: {e_carga}")

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
        if st.button("🧪 Cargar Demo", key="btn_demo_hidro", use_container_width=True, help="Carga datos de demostración oficiales"):
            st.session_state["df_hidro_raw"] = obtener_muestras_demostracion()
            st.session_state["es_demostracion_hidro"] = True
            st.rerun()
    with col_btn2:
        if st.button("🗑️ Limpiar", key="btn_clean_hidro", use_container_width=True, help="Limpia los datos cargados"):
            st.session_state["df_hidro_raw"] = pd.DataFrame()
            st.session_state["es_demostracion_hidro"] = False
            st.rerun()

# =============================================================================
# 🚀 5. MOTOR DE PROCESAMIENTO
# =============================================================================
df_crudo = st.session_state.get("df_hidro_raw", pd.DataFrame())
df_normalizado = mapear_dataframe_hidroquimico(df_crudo) if not df_crudo.empty else pd.DataFrame()
df_procesado = procesar_muestras_hidroquimicas(df_normalizado) if not df_normalizado.empty else pd.DataFrame()
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
                <h3 style="color: #691C32; margin: 0 0 4px 0; font-size: 20px; font-weight: 700;">
                    🧪 Plataforma Integral de Hidrogeoquímica y Calidad del Agua Subterránea
                </h3>
                <p style="margin: 0; color: #475569; font-size: 13px;">
                    Acuífero Oficial: <b>{clave_sel or 'N/D'} - {nombre_sel or 'General'}</b> | Marco Normativo: <b>NOM-127-SSA1-2021</b> y Estándares OMM / UNESCO
                </p>
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
            El sistema mapeará automáticamente los nombres de columnas de laboratorio y generará todos los diagramas hidrogeoquímicos vectoriales interactivos.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col_up_main, _ = st.columns([3, 1])
    with col_up_main:
        archivo_main = st.file_uploader(
            "Seleccionar o arrastrar archivo Excel (.xlsx / .xls) o CSV:",
            type=['xlsx', 'xls', 'csv'],
            key="file_uploader_main_hero"
        )
        if archivo_main is not None:
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
                    st.session_state["df_hidro_raw"] = df_cargado_hero
                    st.session_state["es_demostracion_hidro"] = False
                    st.success(f"✅ Archivo cargado con éxito ({len(df_cargado_hero)} muestras identificadas).")
                    st.rerun()
            except Exception as e_hero:
                st.error(f"Error al leer archivo: {e_hero}")

    col_h_b1, col_h_b2 = st.columns([1, 1])
    with col_h_b1:
        st.markdown(btn_plantilla, unsafe_allow_html=True)
    with col_h_b2:
        if st.button("🧪 Cargar Muestras Demo Oficiales", key="btn_hero_demo", use_container_width=True):
            st.session_state["df_hidro_raw"] = obtener_muestras_demostracion()
            st.session_state["es_demostracion_hidro"] = True
            st.rerun()

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
    "🚨 Auditoría NOM-127-SSA1-2021",
    "🗺️ Geovisor Espacial",
    "💾 Exportación Pericial"
])

# -----------------------------------------------------------------------------
# TAB 1: FACIES Y PIPER
# -----------------------------------------------------------------------------
with tab_piper:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 10px 14px; border-radius: 4px; margin-bottom: 14px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">DIAGRAMA TRILINEAL DE PIPER - CLASIFICACIÓN DE FAMILIAS HIDROGEOQUÍMICAS</span><br>
            <span style="font-size: 11.5px; color: #475569;">
                Representación simultánea de cationes (Ca²⁺, Mg²⁺, Na⁺+K⁺) y aniones (HCO₃⁻+CO₃²⁻, SO₄²⁻, Cl⁻) en porcentaje de miliequivalentes por litro (meq/L).
                El diamante central equilátero proyecta la evolución natural del agua subterránea desde facies bicarbonatadas cálcicas hasta cloruradas sódicas.
            </span>
        </div>
    """, unsafe_allow_html=True)

    n_incomp = int((~df_procesado['Apta_Piper']).sum()) if 'Apta_Piper' in df_procesado.columns else 0
    if n_incomp > 0:
        st.warning(f"⚠️ **{n_incomp} muestra(s) no fueron proyectadas en el diagrama trilineal** por carecer de la serie analítica completa de iones mayores (Ca²⁺, Mg²⁺, Na⁺/K⁺, HCO₃⁻, SO₄²⁻, Cl⁻). Los valores ausentes no se estimaron para preservar el rigor analítico oficial.")

    col_p_plot, col_p_info = st.columns([7.5, 4.5], gap="large")

    facies_paleta_ui = {
        "Bicarbonatada Magnésica-Sódica": "#0891b2",
        "Bicarbonatada Sódica": "#7c3aed",
        "Bicarbonatada Sódica-Magnésica": "#9333ea",
        "Bicarbonatada Magnésica": "#16a34a",
        "Bicarbonatada Magnésica-Cálcica": "#059669",
        "Bicarbonatada Cálcica-Magnésica": "#0284c7",
        "Bicarbonatada Sódica-Cálcica": "#c026d3",
        "Bicarbonatada Cálcica": "#0369a1",
        "Bicarbonatada Mixta Catiónica": "#64748b",
        "Bicarbonatada Cálcica-Sódica": "#0ea5e9",
        "Sulfatada Magnésica-Sódica": "#d97706",
        "Clorurada Sódica": "#dc2626",
        "Sulfatada Cálcica": "#b45309"
    }

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

            # Filtro interactivo de Familias
            todas_familias = list(facies_counts.index)
            familias_seleccionadas = st.multiselect(
                "Filtrar Familias Activas:",
                options=todas_familias,
                default=todas_familias,
                key="ms_piper_familias_activas",
                help="Desmarque familias para ocultarlas del diagrama y de la tabla."
            )

            if not familias_seleccionadas:
                familias_seleccionadas = todas_familias

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

            st.markdown("<p style='font-size:11.5px; font-weight:700; color:#334155; margin:10px 0 6px 0;'>Familias Identificadas en el Muestreo:</p>", unsafe_allow_html=True)
            for fac_nom, c_cnt in facies_counts.items():
                pct_val = (c_cnt / n_tot) * 100.0
                is_active = (fac_nom in familias_seleccionadas)
                badge_col = facies_paleta_ui.get(fac_nom, "#0284c7")
                opacity_style = "opacity:1.0;" if is_active else "opacity:0.40; text-decoration:line-through;"
                border_style = f"border-left:3px solid {badge_col};" if is_active else "border-left:3px solid #cbd5e1;"

                st.markdown(f"""
                <div style='display:flex; justify-content:space-between; align-items:center; padding:5px 8px; background:#f8fafc; {border_style} border-radius:4px; margin-bottom:5px; font-size:11px; {opacity_style}'>
                    <span><b>{fac_nom}</b></span>
                    <span style='background:{badge_col if is_active else "#94a3b8"}; color:white; padding:2px 7px; border-radius:10px; font-size:10px; font-weight:bold;'>{c_cnt} fuentes ({pct_val:.0f}%)</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("<p style='font-size:11.5px; font-weight:700; color:#334155; margin-bottom:6px;'>Guía de Cuadrantes del Diamante Central:</p>", unsafe_allow_html=True)
            st.markdown("""
            <div style='font-size:11px; color:#475569; line-height:1.5;'>
                • <b style='color:#166534;'>Oeste (Bicarbonatada Cálcica/Magnésica):</b> Aguas jóvenes de recarga reciente en zonas de infiltración. Predominio de disolución carbonatada.<br>
                • <b style='color:#6b21a8;'>Sur (Bicarbonatada Sódica):</b> Aguas sujetas a intercambio catiónico natural (ablandamiento natural en medios arcillosos).<br>
                • <b style='color:#92400e;'>Norte (Sulfatada/Clorurada Cálcica):</b> Disolución de evaporitas (yeso, anhidrita) o dureza permanente no carbónica.<br>
                • <b style='color:#991b1b;'>Este (Clorurada/Sulfatada Sódica):</b> Aguas altamente evolucionadas, largo tiempo de residencia, salinas o intrusión marina.
            </div>
            """, unsafe_allow_html=True)

    with col_p_plot:
        id_aislado = muestra_enfocada if muestra_enfocada != opciones_muestra[0] else None
        df_piper_render = df_procesado[df_procesado['Facies_Piper'].isin(familias_seleccionadas)].copy()
        html_piper_d3 = generar_diagrama_piper_d3(df_piper_render, muestra_aislada=id_aislado)
        st.iframe(html_piper_d3, height=800)

    with st.expander("📋 Tabla Detallada de Parámetros Trilineales, Balance Iónico e Índice de Revelle", expanded=False):
        cols_piper_tab = [
            'Muestra', 'Tipo_Fuente', 'Apta_Piper', 'Iones_Faltantes', 'Facies_Piper', 'Cuadrante_Piper', 'CBE_pct', 'CBE_Calidad',
            'Suma_Cationes_meq', 'Suma_Aniones_meq', 'pct_Ca', 'pct_Mg', 'pct_Na_K',
            'pct_HCO3_CO3', 'pct_SO4', 'pct_Cl', 'Indice_Revelle', 'Clasif_Revelle'
        ]
        cols_presentes = [c for c in cols_piper_tab if c in df_procesado.columns]
        df_tab_p = df_procesado[cols_presentes].copy()
        
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
        st.dataframe(df_tab_p.style.format({k: v for k, v in fmt_dict.items() if k in df_tab_p.columns}), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# TAB 2: HUELLA IÓNICA (STIFF / SCHÖELLER)
# -----------------------------------------------------------------------------
with tab_stiff:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">DIAGRAMAS POLIGONALES DE STIFF Y PERFILES DE SCHÖELLER-BERKALOFF</span><br>
            <span style="font-size: 11.5px; color: #475569;">
                Los polígonos de Stiff configuran la huella digital iónica en meq/L para cada captación. El perfil semilogarítmico de Schöeller permite trazar la secuencia de evolución geoquímica hidrogeológica.
            </span>
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
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">EVALUACIÓN AGROCLIMÁTICA Y APTITUD DEL AGUA PARA RIEGO</span><br>
            <span style="font-size: 11.5px; color: #475569;">
                Análisis del riesgo de salinización y sodificación del suelo. Integra la <b>Relación de Adsorción de Sodio (RAS / SAR)</b>, el <b>Carbonato de Sodio Residual (CSR)</b>, el diagrama de <b>Wilcox</b> y la clasificación de <b>Riverside (USSL)</b>.
            </span>
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
        st.dataframe(df_riego_v.style.format({
            'CE_uS_cm': '{:.0f}',
            'SDT_mg_L': '{:.1f}',
            'RAS': '{:.2f}',
            'Pct_Na_Riego': '{:.1f}%',
            'CSR': '{:+.2f}'
        }), use_container_width=True, hide_index=True)

        st.caption("ℹ️ **Nota Técnica sobre el Carbonato de Sodio Residual (CSR):** Valores negativos reflejan un exceso benéfico de calcio y magnesio sobre los aniones carbonatados ((Ca+Mg) > (HCO3+CO3)), garantizando nulo riesgo de sodificación alcalina y excelente estabilidad para la estructura del suelo.")

# -----------------------------------------------------------------------------
# TAB 4: GÉNESIS GEOQUÍMICA (GIBBS)
# -----------------------------------------------------------------------------
with tab_gibbs:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">DIAGRAMA DE GIBBS Y RELACIONES MOLARES GEOQUÍMICAS</span><br>
            <span style="font-size: 11.5px; color: #475569;">
                Identificación del proceso rector de adquisición de solutos: <b>Precipitación / Lluvia</b>, <b>Interacción Agua-Roca (Meteorización de Silicatos y Carbonatos)</b> o <b>Evaporación / Salinidad</b>.
            </span>
        </div>
    """, unsafe_allow_html=True)

    html_gibbs = generar_diagrama_gibbs_d3(df_procesado)
    st.iframe(html_gibbs, height=540)

    with st.expander("🔍 Auditoría de Relaciones Iónicas Molares e Índice de Revelle", expanded=True):
        st.markdown("""
            <div style="font-size:12px; color:#334155; line-height:1.5; margin-bottom:10px;">
                • <b>Relación Na⁺ / Cl⁻:</b> Valores ≈ 1.0 evidencian disolución de halita (NaCl). Valores > 1.0 denotan meteorización de silicatos de sodio (albita) o intercambio catiónico natural.<br>
                • <b>Relación Ca²⁺ / SO₄²⁻:</b> Valores ≈ 1.0 evidencian disolución de yeso (CaSO₄·2H₂O) o anhidrita.<br>
                • <b>Relación (Ca²⁺ + Mg²⁺) / HCO₃⁻:</b> Evalúa la disolución de carbonatos (calcita y dolomita).<br>
                • <b>Índice de Revelle (Cl⁻ / HCO₃⁻):</b> Trazador oficial de salinización e intrusión marina (< 1.0 continental no afectada; 1.0 a 2.8 ligera; > 6.6 intrusión crítica).
            </div>
        """, unsafe_allow_html=True)

        cols_geoq = ['Muestra', 'Tipo_Fuente', 'rNa_rCl', 'rCa_rSO4', 'rCaMg_rHCO3', 'rMg_rCa', 'Indice_Revelle', 'Clasif_Revelle']
        c_g_pres = [c for c in cols_geoq if c in df_procesado.columns]
        df_geo_v = df_procesado[c_g_pres].copy()
        st.dataframe(df_geo_v.style.format({
            'rNa_rCl': '{:.2f}',
            'rCa_rSO4': '{:.2f}',
            'rCaMg_rHCO3': '{:.2f}',
            'rMg_rCa': '{:.2f}',
            'Indice_Revelle': '{:.3f}'
        }), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# TAB 5: AUDITORÍA NORMATIVA NOM-127-SSA1-2021
# -----------------------------------------------------------------------------
with tab_nom:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">AUDITORÍA PERICIAL NOM-127-SSA1-2021 (AGUA PARA USO Y CONSUMO HUMANO)</span><br>
            <span style="font-size: 11.5px; color: #475569;">
                Evaluación automatizada frente a los Límites Máximos Permisibles (LMP) de la Norma Oficial Mexicana vigente.
                Incluye metales tóxicos (Arsénico ≤ 0.010 mg/L, Plomo ≤ 0.010 mg/L, Fluoruros ≤ 1.5 mg/L), parámetros estéticos (SDT, Dureza, Hierro, Manganeso) y microbiológicos (E. coli).
            </span>
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

    st.dataframe(
        df_aud_filtrado[['Muestra', 'Tipo_Fuente', 'Estatus_NOM127', 'Total_Evaluados', 'Conformes', 'Alertas', 'No_Conformes', 'Parametros_Excedidos', 'Parametros_Alerta']]
        .style.map(color_estatus_nom, subset=['Estatus_NOM127']),
        use_container_width=True, hide_index=True
    )

    with st.expander("📚 Catálogo Oficial de Límites Máximos Permisibles (NOM-127-SSA1-2021)", expanded=False):
        guia_norma = [
            {'Parámetro': v['nombre'], 'Categoría': v['categoria'], 'LMP': f"{v['lmp']} {v['unidad']}", 'Tipo': 'Máximo' if v['tipo'] == 'max' else 'Mínimo'}
            for v in LIMITES_NOM_127_2021.values()
        ]
        st.dataframe(pd.DataFrame(guia_norma), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# TAB 6: GEOVISOR ESPACIAL DE CALIDAD DEL AGUA
# -----------------------------------------------------------------------------
with tab_geo:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">DISTRIBUCIÓN ESPACIAL DE FUENTES DE MONITOREO Y CALIDAD DEL AGUA</span><br>
            <span style="font-size: 11.5px; color: #475569;">
                Georreferenciación de pozos y manantiales sobre el acuífero oficial. Plataforma MapLibre GL 3.6.2 WebGL sin marcas de agua de terceros, con soporte de capas base y análisis hidrogeoquímico.
            </span>
        </div>
    """, unsafe_allow_html=True)

    df_geo_pts = df_procesado.dropna(subset=['Latitud', 'Longitud']).copy() if ('Latitud' in df_procesado.columns and 'Longitud' in df_procesado.columns) else pd.DataFrame()

    if df_geo_pts.empty:
        st.warning("⚠️ Las muestras cargadas no cuentan con coordenadas 'Latitud' y 'Longitud' para su representación cartográfica.")
    else:
        # Unir estatus NOM-127 a los puntos si no está
        if 'Estatus_NOM127' not in df_geo_pts.columns and not df_auditoria.empty:
            df_geo_pts = df_geo_pts.merge(df_auditoria[['Muestra', 'Estatus_NOM127', 'Parametros_Excedidos']], on='Muestra', how='left')

        col_criterio = st.radio(
            "Simbología de Fuentes en Geovisor:",
            ["Por Facies Hidrogeoquímica (Piper)", "Por Cumplimiento NOM-127-SSA1-2021"],
            horizontal=True,
            key="radio_geo_criterio"
        )

        c_lat_cen = float(df_geo_pts['Latitud'].mean())
        c_lon_cen = float(df_geo_pts['Longitud'].mean())

        # Construir GeoJSON de puntos
        features_pts = []
        for _, r in df_geo_pts.iterrows():
            id_m = html.escape(str(r.get('Muestra', 'Muestra')))
            facies = str(r.get('Facies_Piper', 'N/D'))
            estatus = str(r.get('Estatus_NOM127', 'Conforme'))
            exc = str(r.get('Parametros_Excedidos', 'Ninguno'))
            
            # Asignar color según criterio
            if "Piper" in col_criterio:
                if "Bicarbonatada Cálcica" in facies: color_pt = "#0284c7"
                elif "Bicarbonatada Sódica" in facies: color_pt = "#7c3aed"
                elif "Clorurada Sódica" in facies: color_pt = "#dc2626"
                elif "Sulfatada" in facies: color_pt = "#d97706"
                else: color_pt = "#059669"
            else:
                if "No Conforme" in estatus: color_pt = "#dc2626"
                elif "Alerta" in estatus: color_pt = "#d97706"
                else: color_pt = "#16a34a"

            popup_html = f"""
            <div style='font-family: Arial, sans-serif; font-size: 11.5px; line-height: 1.4; color: #1e293b; min-width: 250px;'>
              <div style='background: #691C32; color: white; padding: 6px 10px; font-weight: bold; border-radius: 4px 4px 0 0;'>
                🧪 {id_m} ({r.get('Tipo_Fuente', 'Fuente')})
              </div>
              <div style='padding: 8px 10px; border: 1px solid #cbd5e1; border-top: none; background: white; border-radius: 0 0 4px 4px;'>
                <b>Facies:</b> {facies}<br>
                <b>Dictamen NOM-127:</b> {estatus}<br>
                <b>SDT:</b> {r.get('SDT_mg_L', 0):,.1f} mg/L | <b>CE:</b> {r.get('CE_uS_cm', 0):,.0f} µS/cm<br>
                <b>Balance CBE:</b> {r.get('CBE_pct', 0):+.2f}%<br>
                <b>Índice Revelle:</b> {r.get('Indice_Revelle', 0):.2f}<br>
                <hr style='margin: 4px 0;'>
                <b>Fuera de Norma:</b> <span style='color:#dc2626; font-weight:600;'>{exc}</span>
              </div>
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
                    "color": color_pt,
                    "facies": facies,
                    "estatus": estatus,
                    "popup": popup_html
                }
            })

        geojson_muestras_str = json.dumps({"type": "FeatureCollection", "features": features_pts})
        geojson_poly_str = json.dumps(poligono_geojson) if poligono_geojson else "null"
        bounds_poly_str = json.dumps(bounds_poligono) if bounds_poligono else "null"

        # Construir items de la leyenda según criterio
        if "Piper" in col_criterio:
            legend_items = """
            <div style='font-weight:700; color:#691C32; margin-bottom:4px; font-size:11px;'>Facies Hidrogeoquímicas:</div>
            <div><i style='background:#0284c7;'></i> Bicarbonatada Cálcica</div>
            <div><i style='background:#7c3aed;'></i> Bicarbonatada Sódica</div>
            <div><i style='background:#dc2626;'></i> Clorurada Sódica</div>
            <div><i style='background:#d97706;'></i> Sulfatada Cálcica</div>
            <div><i style='background:#059669;'></i> Mixta / Otra</div>
            """
        else:
            legend_items = """
            <div style='font-weight:700; color:#691C32; margin-bottom:4px; font-size:11px;'>Dictamen NOM-127:</div>
            <div><i style='background:#16a34a;'></i> Conforme (Apta)</div>
            <div><i style='background:#d97706;'></i> Alerta Preventiva</div>
            <div><i style='background:#dc2626;'></i> No Conforme (Rebasa)</div>
            """

        html_maplibre = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <title>Geovisor Hidrogeoquímico</title>
            <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
            <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
            <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
            <style>
                body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; overflow: hidden; }}
                #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; border-radius: 8px; }}

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
                .dock-body {{ padding: 12px 14px; max-height: 70vh; overflow-y: auto; }}
                .dock-section {{ margin-bottom: 12px; }}
                .dock-section label {{ display: flex; align-items: center; gap: 6px; cursor: pointer; margin-bottom: 6px; font-weight: 500; }}
                .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; margin-top: 4px; }}

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
                    padding: 10px 14px; border-radius: 8px;
                    box-shadow: 0 4px 14px rgba(0,0,0,0.16); font-size: 11px; line-height: 1.6;
                    border: 1px solid #E2E8F0; border-top: 3px solid #691C32; max-width: 280px;
                }}
                .legend-panel i {{
                    width: 12px; height: 12px; display: inline-block; border-radius: 50%;
                    margin-right: 6px; vertical-align: middle; border: 1px solid #fff;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
                }}

                .gis-badge-popup .maplibregl-popup-content {{
                    background: rgba(255, 255, 255, 0.96) !important;
                    backdrop-filter: blur(8px) !important;
                    border: 1px solid #CBD5E1 !important;
                    border-top: 3px solid #691C32 !important;
                    border-radius: 6px !important;
                    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.20) !important;
                    padding: 0 !important;
                    overflow: hidden !important;
                }}
                .gis-badge-popup .maplibregl-popup-tip {{
                    border-top-color: rgba(255, 255, 255, 0.96) !important;
                }}
                .gis-badge-popup .maplibregl-popup-close-button {{
                    color: #ffffff !important;
                    font-size: 15px !important;
                    top: 4px !important; right: 6px !important;
                    padding: 2px 4px !important;
                }}
            </style>
        </head>
        <body>
            <div id="map"></div>

            <div class="btn-open-dock-circle" onclick="toggleDock()" title="Capas y Controles SIG">☰</div>

            <div id="dock-panel" class="workbench-dock" style="display: none;">
                <div class="dock-header">
                    <span>🛠️ Capas y Control SIG</span>
                    <span style="cursor:pointer; font-size:16px;" onclick="toggleDock()">✕</span>
                </div>
                <div class="dock-body">
                    <div class="dock-section">
                        <div style="font-weight:700; color:#691C32; margin-bottom:6px; font-size:11px; text-transform:uppercase;">1. Capa Base Cartográfica</div>
                        <label><input type="radio" name="basemap" value="esri" checked onchange="cambiarBasemap(this.value)"> 🛰️ Satelital ESRI Maxar</label>
                        <label><input type="radio" name="basemap" value="carto" onchange="cambiarBasemap(this.value)"> 🗺️ Carto Claro (Vector)</label>
                        <label><input type="radio" name="basemap" value="topo" onchange="cambiarBasemap(this.value)"> ⛰️ Topografía y Relieve</label>
                        <label><input type="radio" name="basemap" value="osm" onchange="cambiarBasemap(this.value)"> 🌐 OpenStreetMap</label>
                    </div>
                    <div class="dock-section" style="border-top: 1px solid #e2e8f0; padding-top:8px;">
                        <div style="font-weight:700; color:#691C32; margin-bottom:6px; font-size:11px; text-transform:uppercase;">2. Capas Temáticas</div>
                        <label><input type="checkbox" id="chk-poligono" checked onchange="toggleLayer('layer-poligono-fill'); toggleLayer('layer-poligono-line');"> 🏛️ Polígono Oficial Acuífero</label>
                        <label><input type="checkbox" id="chk-muestras" checked onchange="toggleLayer('layer-muestras-circle');"> 🧪 Fuentes de Monitoreo</label>
                    </div>
                    <div class="dock-section" style="border-top: 1px solid #e2e8f0; padding-top:8px;">
                        <div style="font-weight:700; color:#691C32; margin-bottom:4px; font-size:11px; text-transform:uppercase;">3. Opacidad del Polígono</div>
                        <input type="range" class="slider-ctrl" min="0" max="100" value="20" oninput="ajustarOpacidadPoligono(this.value)">
                    </div>
                </div>
            </div>

            <div class="hud-elevation" id="hud-coord">
                <div><b>Lon:</b> <span id="hud-lon">{c_lon_cen:.4f}</span>°</div>
                <div><b>Lat:</b> <span id="hud-lat">{c_lat_cen:.4f}</span>°</div>
                <div><b>Zoom:</b> <span id="hud-zoom">11.0</span></div>
            </div>

            <div class="legend-panel">
                {legend_items}
            </div>

            <script>
                const basemaps = {{
                    esri: {{
                        version: 8,
                        sources: {{
                            'esri-sat': {{
                                type: 'raster',
                                tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'],
                                tileSize: 256,
                                attribution: '© Esri, Maxar, Earthstar Geographics'
                            }}
                        }},
                        layers: [{{ id: 'base-layer', type: 'raster', source: 'esri-sat', minzoom: 0, maxzoom: 19 }}]
                    }},
                    carto: {{
                        version: 8,
                        sources: {{
                            'carto-light': {{
                                type: 'raster',
                                tiles: ['https://basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}.png'],
                                tileSize: 256,
                                attribution: '© CARTO, OpenStreetMap'
                            }}
                        }},
                        layers: [{{ id: 'base-layer', type: 'raster', source: 'carto-light', minzoom: 0, maxzoom: 19 }}]
                    }},
                    topo: {{
                        version: 8,
                        sources: {{
                            'topo-layer': {{
                                type: 'raster',
                                tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'],
                                tileSize: 256,
                                attribution: '© Esri Topo'
                            }}
                        }},
                        layers: [{{ id: 'base-layer', type: 'raster', source: 'topo-layer', minzoom: 0, maxzoom: 19 }}]
                    }},
                    osm: {{
                        version: 8,
                        sources: {{
                            'osm-tiles': {{
                                type: 'raster',
                                tiles: ['https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png'],
                                tileSize: 256,
                                attribution: '© OpenStreetMap contributors'
                            }}
                        }},
                        layers: [{{ id: 'base-layer', type: 'raster', source: 'osm-tiles', minzoom: 0, maxzoom: 19 }}]
                    }}
                }};

                const map = new maplibregl.Map({{
                    container: 'map',
                    style: basemaps.esri,
                    center: [{c_lon_cen}, {c_lat_cen}],
                    zoom: 11
                }});

                map.addControl(new maplibregl.NavigationControl(), 'top-right');
                map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-right');

                const geojsonMuestras = {geojson_muestras_str};
                const geojsonPoligono = {geojson_poly_str};
                const boundsPoligono = {bounds_poly_str};

                function toggleDock() {{
                    const dock = document.getElementById('dock-panel');
                    dock.style.display = (dock.style.display === 'none' || dock.style.display === '') ? 'block' : 'none';
                }}

                function toggleLayer(layerId) {{
                    if (map.getLayer(layerId)) {{
                        const vis = map.getLayoutProperty(layerId, 'visibility');
                        map.setLayoutProperty(layerId, 'visibility', vis === 'none' ? 'visible' : 'none');
                    }}
                }}

                function ajustarOpacidadPoligono(val) {{
                    const op = parseFloat(val) / 100.0;
                    if (map.getLayer('layer-poligono-fill')) {{
                        map.setPaintProperty('layer-poligono-fill', 'fill-opacity', op);
                    }}
                }}

                map.on('mousemove', (e) => {{
                    document.getElementById('hud-lon').innerText = e.lngLat.lng.toFixed(4);
                    document.getElementById('hud-lat').innerText = e.lngLat.lat.toFixed(4);
                    document.getElementById('hud-zoom').innerText = map.getZoom().toFixed(1);
                }});

                function cargarCapasDatos() {{
                    // 1. Polígono Oficial del Acuífero
                    if (geojsonPoligono && geojsonPoligono.geometry) {{
                        if (!map.getSource('src-poligono')) {{
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
                                paint: {{ 'line-color': '#691C32', 'line-width': 2.8 }}
                            }});
                        }}
                    }}

                    // 2. Fuentes de Muestreo Hidrogeoquímico
                    if (!map.getSource('src-muestras')) {{
                        map.addSource('src-muestras', {{ type: 'geojson', data: geojsonMuestras }});
                        map.addLayer({{
                            id: 'layer-muestras-circle',
                            type: 'circle',
                            source: 'src-muestras',
                            paint: {{
                                'circle-radius': 9,
                                'circle-color': ['get', 'color'],
                                'circle-stroke-width': 2.2,
                                'circle-stroke-color': '#ffffff'
                            }}
                        }});
                    }}

                    // Encuadre automático (fitBounds)
                    if (boundsPoligono && boundsPoligono.length === 4) {{
                        map.fitBounds([
                            [boundsPoligono[0], boundsPoligono[1]],
                            [boundsPoligono[2], boundsPoligono[3]]
                        ], {{ padding: 45, maxZoom: 13.5 }});
                    }}
                }}

                map.on('load', cargarCapasDatos);

                map.on('click', 'layer-muestras-circle', (e) => {{
                    const f = e.features[0];
                    new maplibregl.Popup({{ className: 'gis-badge-popup' }})
                        .setLngLat(f.geometry.coordinates)
                        .setHTML(f.properties.popup)
                        .addTo(map);
                }});

                map.on('mouseenter', 'layer-muestras-circle', () => {{ map.getCanvas().style.cursor = 'pointer'; }});
                map.on('mouseleave', 'layer-muestras-circle', () => {{ map.getCanvas().style.cursor = ''; }});

                function cambiarBasemap(tipo) {{
                    map.setStyle(basemaps[tipo]);
                    map.once('style.load', cargarCapasDatos);
                }}
            </script>
        </body>
        </html>
        """
        st.iframe(html_maplibre, height=680)

# -----------------------------------------------------------------------------
# TAB 7: EXPORTACIÓN PERICIAL
# -----------------------------------------------------------------------------
with tab_export:
    st.markdown("""
        <div style="background-color: #f8fafc; border-left: 4px solid #691C32; padding: 10px 14px; border-radius: 4px; margin-bottom: 14px;">
            <span style="font-weight: 700; color: #691C32; font-size: 13.5px;">CENTRO DE EXPORTACIÓN Y REPORTES PERICIALES (CERO-RERUN)</span><br>
            <span style="font-size: 11.5px; color: #475569;">
                Descarga de bases de datos completas procesadas con balances iónicos, clasificaciones agronómicas y dictamen de calidad para Google Earth (Móvil/Desktop) y SIG.
            </span>
        </div>
    """, unsafe_allow_html=True)

    c_exp1, c_exp2 = st.columns(2, gap="medium")
    c_exp3, c_exp4 = st.columns(2, gap="medium")

    tiene_coords = ('Latitud' in df_procesado.columns and 'Longitud' in df_procesado.columns and not df_procesado.dropna(subset=['Latitud', 'Longitud']).empty) if not df_procesado.empty else False

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
            bytes_kmz = generar_kmz_hidrogeoquimico(df_procesado, df_auditoria, clave_sel or "Acuifero", nombre_sel or "Oficial", poligono_geojson)
            btn_kmz = generar_enlace_descarga(
                bytes_kmz, f"auditoria_hidroquimica_{clave_sel or 'acuifero'}.kmz",
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
            bytes_shp = generar_shapefile_hidrogeoquimico(df_procesado, df_auditoria, f"hidroquimica_{clave_sel or 'acuifero'}")
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
            bytes_excel_res, f"Informe_Pericial_Hidroquimico_{clave_sel or 'Acuifero'}.xlsx",
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
            df_valid_geo = df_procesado.dropna(subset=['Latitud', 'Longitud']).copy()
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
