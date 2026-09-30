# -*- coding: utf-8 -*-
"""
Módulo de Modelo Geológico y Conceptual 3D (Estación de Trabajo Geocientífica)
- Lectura y recorte espacial instantáneo desde Estructuras_Nacional_SGM.parquet.
- Selector de modo dual:
    1) 🧊 Solo Acuífero (Bloque 3D Aislado) -> Rotación orbital 360° en todos los ejes (Three.js).
    2) 🌍 Con Entorno Geográfico (Mapa Mundial) -> Contexto regional continuo (MapLibre 3D).
- Simbología oficial SGM (3,024 reglas QGIS) con drapeado vectorial continuo 2K.
- Pozos 3D anclados a nivel de terreno y penetrando hacia el subsuelo según su profundidad.
- Dock lateral a la izquierda colapsable a ícono de hamburguesa (☰) con memoria de estado.
- Puntos de referencia/pozos idénticos al SIG con autodetección de acuífero.
- Botones secundarios para descargas GeoTIFF, Shapefile y CSV.
"""

import streamlit as st
import streamlit.components.v1 as components
import geopandas as gpd
import pandas as pd
import numpy as np
import rasterio
import rasterio.mask
from rasterio.transform import from_bounds
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
from concurrent.futures import ThreadPoolExecutor
from shapely.geometry import Point
import requests
import tempfile
import zipfile
import math
import os
import io
import re
import json
import time
from pathlib import Path

# Importaciones del Core
from utils.styles import inyectar_css_oficial, banner_institucional
from core.data_loader import cargar_catalogo, cargar_datos_maestros, DIRECTORIO_RAIZ

# =======================================================
# 🎨 1. CONFIGURACIÓN Y ESTILOS
# =======================================================
st.set_page_config(layout="wide", page_title="Modelo Conceptual 3D", page_icon="🧊")
inyectar_css_oficial()
banner_institucional()

st.subheader("🧊 Estación de Trabajo: Modelo Conceptual 3D")
st.caption("Modelación geológica y física 3D: Bloque aislado 360°, estructuras 1:50k SGM y pozos con profundidad real.")

if "lista_marcadores" not in st.session_state:
    st.session_state["lista_marcadores"] = []
if "csv_uploader_key_mc" not in st.session_state:
    st.session_state["csv_uploader_key_mc"] = 0

# =======================================================
# 🏛️ 2. CARGA DE ESTILOS OFICIALES SGM
# =======================================================
@st.cache_data(show_spinner=False)
def cargar_estilos_sgm_oficiales():
    carpeta_geo = DIRECTORIO_RAIZ / "data" / "geologia"
    ruta_json = carpeta_geo / "estilos_oficiales_sgm.json"
    if ruta_json.exists():
        try:
            with open(ruta_json, 'r', encoding='utf-8') as f:
                return json.load(f), "Catálogo Oficial SGM (3,024 reglas QGIS)"
        except Exception: pass
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
            if txt in DICCIONARIO_SGM_GLOBAL: return DICCIONARIO_SGM_GLOBAL[txt]
            for k_estilo, hex_col in DICCIONARIO_SGM_GLOBAL.items():
                if len(k_estilo) >= 3 and (k_estilo == txt or k_estilo in txt):
                    return hex_col
            if txt in TABLA_CROMATICA_RESPALDO: return TABLA_CROMATICA_RESPALDO[txt]

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
# 🛰️ 3. MOTOR DE AUTODETECCIÓN ESPACIAL DE ACUÍFEROS
# =======================================================
gdf_m = cargar_datos_maestros()

def auto_identificar_acuifero_por_coordenadas(lat, lon, gdf_consulta):
    try:
        val_lat = float(lat)
        val_lon = -abs(float(lon))
        pt_geom = Point(val_lon, val_lat)
        
        if gdf_consulta is None or gdf_consulta.empty: return None
        if gdf_consulta.crs is None: gdf_consulta = gdf_consulta.set_crs(epsg=4326)
        
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
# 📍 4. GESTOR DE PUNTOS CON PROFUNDIDAD REAL (IDÉNTICO AL SIG)
# =======================================================
def agregar_punto_manual():
    lat = st.session_state.get("mc_lat_punto", 0.0)
    lon = st.session_state.get("mc_lon_punto", 0.0)
    nom = st.session_state.get("mc_nombre_punto", "").strip()
    tipo = st.session_state.get("mc_tipo_punto", "Pozo existente")
    prof = st.session_state.get("mc_prof_punto", 150.0)
    
    if lat != 0.0 and lon != 0.0:
        lon_final = -abs(float(lon))
        nuevo_pto = {
            "lat": float(lat), "lon": lon_final,
            "nombre": nom if nom else f"Punto {len(st.session_state['lista_marcadores'])+1}",
            "tipo": tipo,
            "profundidad": float(prof),
            "nivel_estatico": 30.0
        }
        st.session_state["lista_marcadores"].append(nuevo_pto)
        
        acuif = auto_identificar_acuifero_por_coordenadas(lat, lon_final, gdf_m)
        if acuif:
            st.session_state["clave_global"] = acuif["clave"]
            st.session_state["nombre_global"] = acuif["nombre"]
            st.session_state["area_total_global"] = acuif["area"]
            st.session_state["mc_sel_edo"] = acuif["estado"]
            
        st.session_state["mc_lat_punto"] = 0.0
        st.session_state["mc_lon_punto"] = 0.0
        st.session_state["mc_nombre_punto"] = ""

def limpiar_puntos():
    st.session_state["lista_marcadores"] = []
    st.session_state["mc_lat_punto"] = 0.0
    st.session_state["mc_lon_punto"] = 0.0
    st.session_state["mc_nombre_punto"] = ""
    st.session_state["csv_uploader_key_mc"] += 1

@st.fragment
def renderizar_controles_puntos():
    tab_manual, tab_csv = st.tabs(["✍️ Manual", "📁 Carga CSV"])

    with tab_manual:
        st.text_input("Identificador:", key="mc_nombre_punto", placeholder="Ej. Pozo San Bernardo")
        st.selectbox(
            "Tipo de Infraestructura:", 
            ["Pozo existente", "Pozo requerido", "PTAR existente", "PTAR requerido", "Tanque existente", "Tanque requerido"], 
            key="mc_tipo_punto"
        )
        c_lat, c_lon = st.columns(2)
        c_lat.number_input("Latitud (N):", value=0.0, format="%.5f", key="mc_lat_punto")
        c_lon.number_input("Longitud (W):", value=0.0, format="%.5f", key="mc_lon_punto")
        st.number_input("Profundidad de Perforación (m):", value=150.0, min_value=1.0, max_value=2000.0, step=10.0, key="mc_prof_punto")
        
        btn_c1, btn_c2 = st.columns(2)
        btn_c1.button("➕ Agregar", on_click=agregar_punto_manual, use_container_width=True, type="primary")
        btn_c2.button("🧹 Limpiar", on_click=limpiar_puntos, use_container_width=True, type="secondary", key="btn_limp_manual_mc")

    with tab_csv:
        st.markdown("""<div style="background-color: #f8f9fa; border: 1px dashed #ced4da; border-radius: 4px; padding: 6px 10px; font-size: 10px; color: #495057; margin-bottom: 8px;">Requisitos: columnas <b>Lat</b>, <b>Long</b> y opcional <b>Profundidad</b>.</div>""", unsafe_allow_html=True)
        
        up_key = f"csv_up_mc_{st.session_state.get('csv_uploader_key_mc', 0)}"
        archivo_csv = st.file_uploader("Seleccionar archivo CSV", type=['csv'], label_visibility="collapsed", key=up_key)
        
        c_csv1, c_csv2 = st.columns(2)
        c_csv2.button("🧹 Limpiar", on_click=limpiar_puntos, use_container_width=True, type="secondary", key="btn_limp_csv_mc")

        if archivo_csv is not None:
            if c_csv1.button("🚀 Cargar", use_container_width=True, type="primary", key="btn_cargar_csv_mc"):
                try:
                    archivo_csv.seek(0)
                    try: df_p = pd.read_csv(archivo_csv, sep=None, engine='python', encoding='utf-8-sig')
                    except Exception: 
                        archivo_csv.seek(0)
                        df_p = pd.read_csv(archivo_csv, sep=';', encoding='latin1')

                    df_p.columns = df_p.columns.astype(str).str.strip().str.upper()
                    
                    col_lat = next((c for c in df_p.columns if any(k in c for k in ['LATITUD', 'LAT', 'Y', 'NORTE'])), None)
                    col_lon = next((c for c in df_p.columns if any(k in c for k in ['LONGITUD', 'LON', 'LONG', 'X', 'OESTE'])), None)
                    col_tipo = next((c for c in df_p.columns if any(k in c for k in ['INFRAESTRUCTURA', 'INFRA', 'TIPO', 'CATEGORIA'])), None)
                    col_nom = next((c for c in df_p.columns if any(k in c for k in ['NOMBRE/SITIO', 'NOMBRE', 'SITIO', 'NOM', 'ID', 'POZO'])), None)
                    col_color = next((c for c in df_p.columns if any(k in c for k in ['COLOR', 'HEX'])), None)
                    col_prof = next((c for c in df_p.columns if any(k in c for k in ['PROFUNDIDAD', 'PROF', 'PERF', 'DEPTH'])), None)
                    col_ne = next((c for c in df_p.columns if any(k in c for k in ['NIVEL', 'NE', 'ESTATICO'])), None)

                    if col_lat and col_lon:
                        nuevos_puntos = []
                        acuifero_detectado = None
                        
                        for _, row in df_p.iterrows():
                            lat_val = pd.to_numeric(str(row[col_lat]).replace(',', '.').strip(), errors='coerce')
                            lon_val = pd.to_numeric(str(row[col_lon]).replace(',', '.').strip(), errors='coerce')
                            
                            if pd.notna(lat_val) and pd.notna(lon_val):
                                tipo_v = str(row[col_tipo]).strip() if col_tipo and pd.notna(row[col_tipo]) else "Pozo existente"
                                nom_v = str(row[col_nom]).strip() if col_nom and pd.notna(row[col_nom]) else tipo_v
                                col_v = str(row[col_color]).strip() if col_color and pd.notna(row[col_color]) else None
                                
                                prof_v = 150.0
                                if col_prof and pd.notna(row[col_prof]):
                                    try: prof_v = float(str(row[col_prof]).replace(',', '.').strip())
                                    except: pass
                                    
                                ne_v = 30.0
                                if col_ne and pd.notna(row[col_ne]):
                                    try: ne_v = float(str(row[col_ne]).replace(',', '.').strip())
                                    except: pass

                                lon_final = -abs(float(lon_val))
                                nuevos_puntos.append({
                                    "lat": float(lat_val), "lon": lon_final, "nombre": nom_v, "tipo": tipo_v, "color_hex": col_v,
                                    "profundidad": prof_v, "nivel_estatico": ne_v
                                })
                                
                                if not acuifero_detectado:
                                    acuifero_detectado = auto_identificar_acuifero_por_coordenadas(lat_val, lon_final, gdf_m)

                        if nuevos_puntos:
                            st.session_state["lista_marcadores"].extend(nuevos_puntos)
                            if acuifero_detectado:
                                st.session_state["clave_global"] = acuifero_detectado["clave"]
                                st.session_state["nombre_global"] = acuifero_detectado["nombre"]
                                st.session_state["area_total_global"] = acuifero_detectado["area"]
                                st.session_state["mc_sel_edo"] = acuifero_detectado["estado"]
                                st.success(f"📍 Acuífero autodetectado: **{acuifero_detectado['clave']} - {acuifero_detectado['nombre']}**")
                            else:
                                st.success(f"✅ {len(nuevos_puntos)} pozos con profundidad procesados.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ No se encontraron coordenadas válidas.")
                    else:
                        st.error("❌ Faltan columnas de Latitud y Longitud en el CSV.")
                except Exception as e:
                    st.error(f"Error procesando CSV: {e}")
        else:
            c_csv1.button("🚀 Cargar", use_container_width=True, type="primary", disabled=True, key="btn_cargar_csv_dis_mc")

    if len(st.session_state["lista_marcadores"]) > 0:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        df_descarga = pd.DataFrame(st.session_state["lista_marcadores"]).rename(columns={
            "tipo": "Infraestructura", "nombre": "Nombre", "lat": "Lat", "lon": "Long", "profundidad": "Profundidad_m"
        })
        cols_c = [c for c in ["Infraestructura", "Nombre", "Lat", "Long", "Profundidad_m"] if c in df_descarga.columns]
        csv_data = df_descarga[cols_c].to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="⬇️ Descargar Puntos (CSV)", data=csv_data, file_name="puntos_modelo_3d.csv", mime="text/csv", type="secondary", use_container_width=True)

st.sidebar.markdown("""
    <style>
        section[data-testid="stSidebar"] button[kind="secondary"],
        section[data-testid="stSidebar"] button[data-baseweb="button"]:not([kind="primary"]),
        section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button,
        section[data-testid="stSidebar"] div[data-testid="stLinkButton"] a {
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
        section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button:hover,
        section[data-testid="stSidebar"] div[data-testid="stLinkButton"] a:hover {
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
    </style>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.subheader("📍 Puntos de Referencia / Pozos")
st.sidebar.markdown("""
    <div style="font-size: 11px; color: #666; margin-top: -14px; margin-bottom: 8px;">
        Ingresa coordenadas manuales o carga masiva vía CSV
    </div>
""", unsafe_allow_html=True)

with st.sidebar:
    renderizar_controles_puntos()

# =======================================================
# 🔍 5. SINCRONIZACIÓN Y SELECCIÓN MANUAL DE ACUÍFERO
# =======================================================
clave_actual = st.session_state.get("clave_global")
nombre_actual = st.session_state.get("nombre_global")
area_actual = st.session_state.get("area_total_global", 0)

with st.expander("📍 Búsqueda Manual de Acuífero en Catálogo", expanded=not clave_actual):
    df_cat = cargar_catalogo("Acuiferos_2026.csv")
    if not df_cat.empty:
        c_est, c_clav = st.columns(2)
        estados = sorted(df_cat["ESTADO"].dropna().unique().tolist())
        idx_edo = estados.index(st.session_state["mc_sel_edo"]) if st.session_state.get("mc_sel_edo") in estados else None
        estado_sel = c_est.selectbox("1. Estado:", estados, index=idx_edo, key="mc_sel_edo", placeholder="Elige un estado...")

        opciones_acuiferos = []
        if estado_sel:
            df_est = df_cat[df_cat["ESTADO"] == estado_sel].copy()
            df_est["ETIQUETA"] = df_est["CLAVE_SIGM"].astype(str) + " - " + df_est["ACUÍFERO"].astype(str)
            opciones_acuiferos = sorted(df_est["ETIQUETA"].unique().tolist())

        seleccion = c_clav.selectbox("2. Clave o Nombre del Acuífero:", opciones_acuiferos, key="mc_sel_clv", index=None, placeholder="Elige un acuífero...")
        if seleccion:
            clave_sel = seleccion.split(" - ")[0]
            if clave_sel != st.session_state.get("clave_global"):
                datos_acu = df_est[df_est["CLAVE_SIGM"] == clave_sel].iloc[0]
                st.session_state["clave_global"] = str(datos_acu["CLAVE_SIGM"])
                st.session_state["nombre_global"] = str(datos_acu["ACUÍFERO"])
                st.session_state["area_total_global"] = round(float(datos_acu["AREA_KM2"]), 1)
                st.rerun()

if not clave_actual or not nombre_actual:
    st.info("👆 Selecciona un Acuífero arriba o sube un archivo CSV en la barra lateral para comenzar.")
    st.stop()

with st.container(border=True):
    col_b1, col_b2, col_b3 = st.columns([1, 2, 1])
    col_b1.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>CLAVE OFICIAL</p><h4 style='color:#691C32; margin:0;'>{clave_actual}</h4>", unsafe_allow_html=True)
    col_b2.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>ACUÍFERO</p><h4 style='color:#691C32; margin:0;'>{nombre_actual}</h4>", unsafe_allow_html=True)
    col_b3.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>SUPERFICIE</p><h4 style='color:#691C32; margin:0;'>{float(area_actual):,.1f} km²</h4>", unsafe_allow_html=True)

def normalizar_cve(v):
    try: return str(int(float(v))).zfill(4)
    except: return str(v).strip().zfill(4)

coincidencias = gdf_m[gdf_m['CLV_ACUI'].apply(normalizar_cve) == normalizar_cve(clave_actual)] if gdf_m is not None else None
if coincidencias is None or coincidencias.empty:
    st.error(f"No se localizó la geometría espacial del acuífero {clave_actual}.")
    st.stop()

datos_ac = coincidencias.iloc[0]

# =======================================================
# 🛰️ 6. PIPELINE TOPOGRÁFICO DE ALTA PRECISIÓN (DEM)
# =======================================================
zoom_elegido = 12
sel_pix = "Alta (~35 m / SRTM NASA)"

def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile

def num2deg(xtile, ytile, zoom):
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * ytile / n)))
    return math.degrees(lat_rad), lon_deg

def descargar_tesela_elevacion(args):
    x, y, zoom_level = args
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom_level}/{x}/{y}.png"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            img = Image.open(io.BytesIO(r.content)).convert('RGB')
            arr = np.array(img, dtype=np.float32)
            elev = (arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0) - 32768.0
            return (x, y, elev)
    except Exception: pass
    return (x, y, None)

def obtener_o_generar_dem_acuifero(datos_ac, clave_ac, zoom_level=12):
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_dem"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_tif = carpeta_cache / f"DEM_{clave_ac}_z{zoom_level}.tif"
    if ruta_tif.exists(): return ruta_tif

    minx, miny, maxx, maxy = datos_ac.geometry.bounds
    x_start, y_start = deg2num(maxy, minx, zoom_level)
    x_end, y_end = deg2num(miny, maxx, zoom_level)
    
    num_x = (x_end - x_start) + 1
    num_y = (y_end - y_start) + 1
    malla_elevacion = np.zeros((num_y * 256, num_x * 256), dtype=np.float32)
    
    tareas = [(x, y, zoom_level) for y in range(y_start, y_end + 1) for x in range(x_start, x_end + 1)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        for x, y, elev in executor.map(descargar_tesela_elevacion, tareas):
            if elev is not None:
                malla_elevacion[(y - y_start)*256:(y - y_start + 1)*256, (x - x_start)*256:(x - x_start + 1)*256] = elev
                
    lat_top, lon_left = num2deg(x_start, y_start, zoom_level)
    lat_bottom, lon_right = num2deg(x_end + 1, y_end + 1, zoom_level)
    transform_base = from_bounds(lon_left, lat_bottom, lon_right, lat_top, malla_elevacion.shape[1], malla_elevacion.shape[0])
    
    with rasterio.MemoryFile() as memfile:
        with memfile.open(driver='GTiff', height=malla_elevacion.shape[0], width=malla_elevacion.shape[1], count=1, dtype='float32', crs='EPSG:4326', transform=transform_base, nodata=-9999.0) as ds:
            ds.write(malla_elevacion, 1)
            out_img, out_trans = rasterio.mask.mask(ds, [datos_ac.geometry.__geo_interface__], crop=True, nodata=-9999.0)
            meta = ds.meta.copy()

    meta.update({"height": out_img.shape[1], "width": out_img.shape[2], "transform": out_trans, "nodata": -9999.0})
    with rasterio.open(ruta_tif, 'w', **meta) as dst: dst.write(out_img)
    return ruta_tif

with st.spinner("Sincronizando topografía de alta resolución (SRTM NASA)..."):
    try:
        ruta_dem_local = obtener_o_generar_dem_acuifero(datos_ac, clave_actual, zoom_level=12)
    except Exception as e:
        st.error(f"Error cargando DEM: {e}")
        ruta_dem_local = None

@st.cache_data(show_spinner=False)
def generar_curvas_nivel_base_geojson(ruta_tif, intervalo_base=25):
    try:
        with rasterio.open(ruta_tif) as src:
            z = src.read(1)
            mask = (z != src.nodata) & (~np.isnan(z))
            if not np.any(mask): return "{}"
            
            vmin = float(np.min(z[mask]))
            vmax = float(np.max(z[mask]))
            niveles = np.arange(np.floor(vmin / intervalo_base) * intervalo_base, np.ceil(vmax / intervalo_base) * intervalo_base + intervalo_base, intervalo_base)
            if len(niveles) == 0: return "{}"

            paso = max(1, int(max(z.shape) / 400))
            z_sub = z[::paso, ::paso]
            H, W = z_sub.shape
            x_lin = np.linspace(src.bounds.left, src.bounds.right, W)
            y_lin = np.linspace(src.bounds.top, src.bounds.bottom, H)

            fig, ax = plt.subplots()
            cs = ax.contour(x_lin, y_lin, z_sub, levels=niveles)
            plt.close(fig)

            features = []
            for level, segs in zip(cs.levels, cs.allsegs):
                cota_val = int(round(level))
                for seg in segs:
                    if len(seg) >= 3:
                        coords = [[round(float(pt[0]), 5), round(float(pt[1]), 5)] for pt in seg]
                        features.append({
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": coords},
                            "properties": {"cota": cota_val}
                        })
            return json.dumps({"type": "FeatureCollection", "features": features})
    except Exception:
        return "{}"

geojson_curvas_cota = "{}"
if ruta_dem_local and ruta_dem_local.exists():
    geojson_curvas_cota = generar_curvas_nivel_base_geojson(str(ruta_dem_local), intervalo_base=25)

# =======================================================
# 📂 7. CAPA VECTORIAL SGM RECORTE COMPLETO
# =======================================================
@st.cache_data(show_spinner=False)
def preparar_geologia_vectorial(clave_ac):
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_geologia"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_cache_parquet = carpeta_cache / f"GEO_SHP_{clave_ac}.parquet"

    geom_4326 = datos_ac.geometry
    gdf_sgm = None

    # Si hay caché previo de solo 3 columnas, eliminarlo para forzar la recarga completa
    if ruta_cache_parquet.exists() and ruta_cache_parquet.stat().st_size > 2000:
        try:
            gdf_cached = gpd.read_parquet(ruta_cache_parquet)
            if len(gdf_cached.columns) > 3:
                gdf_sgm = gdf_cached
            else:
                ruta_cache_parquet.unlink()
        except Exception:
            pass

    # Búsqueda y recorte en archivos locales
    if gdf_sgm is None or gdf_sgm.empty:
        rutas_busqueda = [DIRECTORIO_RAIZ / "data" / "geologia", Path.home() / "Downloads"]
        for r_dir in rutas_busqueda:
            if not r_dir.exists(): continue
            for pq_p in r_dir.glob("*.parquet"):
                if any(k in pq_p.name.lower() for k in ["lito", "geo", "cnal"]) and "estructura" not in pq_p.name.lower():
                    try:
                        gdf_temp = gpd.read_parquet(pq_p)
                        if gdf_temp.crs is None: gdf_temp = gdf_temp.set_crs(epsg=4326)
                        else: gdf_temp = gdf_temp.to_crs(epsg=4326)
                        recorte = gdf_temp.clip(geom_4326)
                        if not recorte.empty:
                            gdf_sgm = recorte
                            break
                    except Exception: pass
            if gdf_sgm is not None: break

            for shp_p in r_dir.glob("*.shp"):
                if any(k in shp_p.name.lower() for k in ["lito", "geo", "cnal"]) and "estructura" not in shp_p.name.lower():
                    try:
                        gdf_temp = gpd.read_file(shp_p, encoding='latin1')
                        if gdf_temp.crs is None: gdf_temp = gdf_temp.set_crs(epsg=4326)
                        else: gdf_temp = gdf_temp.to_crs(epsg=4326)
                        recorte = gdf_temp.clip(geom_4326)
                        if not recorte.empty:
                            gdf_sgm = recorte
                            break
                    except Exception: pass
            if gdf_sgm is not None: break

    if gdf_sgm is not None and not gdf_sgm.empty:
        # -------------------------------------------------------------
        # 🛠️ CORRECCIÓN DE MOJIBAKE EN PYTHON (UTF-8 / LATIN-1)
        # -------------------------------------------------------------
        def reparar_texto_mojibake(val):
            if val is None or pd.isna(val):
                return ""
            s = str(val).strip()
            try:
                s = s.encode('latin1').decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            return s

        # Limpiar todas las columnas de texto
        for col in gdf_sgm.select_dtypes(include=['object', 'string']).columns:
            if col != 'geometry':
                gdf_sgm[col] = gdf_sgm[col].apply(reparar_texto_mojibake)
        # -------------------------------------------------------------

        cols_upper = [c.upper() for c in gdf_sgm.columns]
        if "CLAVE_SGM" in cols_upper: col_sel = gdf_sgm.columns[cols_upper.index("CLAVE_SGM")]
        elif "CLAVE" in cols_upper: col_sel = gdf_sgm.columns[cols_upper.index("CLAVE")]
        elif "LITOLOGIA" in cols_upper: col_sel = gdf_sgm.columns[cols_upper.index("LITOLOGIA")]
        else: col_sel = gdf_sgm.columns[0]

        colores_asignados = []
        dic_leyenda = {}
        for _, row in gdf_sgm.iterrows():
            c_val = str(row.get(col_sel, "")).strip()
            l_val = str(row.get("LITOLOGIA", "")).strip() if "LITOLOGIA" in gdf_sgm.columns else ""
            r_val = str(row.get("ROCA", "")).strip() if "ROCA" in gdf_sgm.columns else ""
            hex_c = resolver_color_oficial(c_val, l_val, r_val)
            colores_asignados.append(hex_c)
            dic_leyenda[c_val] = hex_c

        gdf_sgm["COLOR_HEX"] = colores_asignados
        gdf_sgm["ETIQUETA_LITO"] = gdf_sgm[col_sel].astype(str)
        gdf_sgm["geometry"] = gdf_sgm.geometry.simplify(tolerance=0.0001, preserve_topology=True)

        try:
            gdf_sgm.to_parquet(ruta_cache_parquet)
        except Exception:
            pass

        return gdf_sgm, dic_leyenda, col_sel

    return None, {}, "Ninguna"

gdf_geologia_recortada, dic_leyenda_rocas, col_litologica = preparar_geologia_vectorial(clave_actual)

gdf_borde = gpd.GeoDataFrame(geometry=[datos_ac.geometry], crs="EPSG:4326")
geojson_borde = gdf_borde.to_json()

minx, miny, maxx, maxy = datos_ac.geometry.bounds
centro_lon = (minx + maxx) / 2.0
centro_lat = (miny + maxy) / 2.0
geojson_geologia = gdf_geologia_recortada.to_json() if gdf_geologia_recortada is not None else "{}"

# Serializar puntos sincronizados de la sesión con profundidad
pozos_3d_json = json.dumps(st.session_state.get("lista_marcadores", []))

# =======================================================
# ⚡ 8. RECORTE INSTANTÁNEO DESDE EL PARQUET NACIONAL SGM
# =======================================================
@st.cache_data(show_spinner=False)
def obtener_estructuras_50k(datos_ac, clave_ac):
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_geologia"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_cache_acuifero = carpeta_cache / f"ESTRUCTURAS_50K_{clave_ac}.parquet"

    # 1. Validar si el caché existente contiene la columna AZIMUTH (si es viejo, se elimina)
    if ruta_cache_acuifero.exists():
        try:
            gdf_cached = gpd.read_parquet(ruta_cache_acuifero)
            if any("AZIMUTH" in c.upper() for c in gdf_cached.columns):
                return gdf_cached
            else:
                ruta_cache_acuifero.unlink()  # 👈 Borra el caché viejo incompleto
        except Exception:
            pass

    # 2. Recorte instantáneo desde el Parquet Nacional Maestro con todas sus columnas
    ruta_nacional = DIRECTORIO_RAIZ / "data" / "geologia" / "Estructuras_Nacional_SGM.parquet"
    if ruta_nacional.exists():
        try:
            gdf_nac = gpd.read_parquet(ruta_nacional)
            geom = datos_ac.geometry
            idx_posibles = list(gdf_nac.sindex.intersection(geom.bounds))
            if idx_posibles:
                candidatos = gdf_nac.iloc[idx_posibles]
                recorte = candidatos.clip(geom)
                if not recorte.empty:
                    recorte.to_parquet(ruta_cache_acuifero)
                    return recorte
        except Exception as e:
            print(f"Error recortando estructuras nacionales: {e}")

    return None

gdf_estructuras_50k = obtener_estructuras_50k(datos_ac, clave_actual)
geojson_estructuras = gdf_estructuras_50k.to_json() if gdf_estructuras_50k is not None and not gdf_estructuras_50k.empty else "{}"

# Exportaciones SIG oficiales con botones secundarios
def exportar_shapefile_zip(gdf, base_name):
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, f"{base_name}.shp")
        if gdf.crs is None: gdf = gdf.set_crs(epsg=4326)
        else: gdf = gdf.to_crs(epsg=4326)
        gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(tmpdir): zf.write(os.path.join(tmpdir, f), arcname=f)
        buf.seek(0)
        return buf.getvalue()

if ruta_dem_local and ruta_dem_local.exists():
    st.sidebar.markdown("---")
    st.sidebar.subheader("💾 Exportación SIG Oficial")
    with open(ruta_dem_local, "rb") as f_dem:
        st.sidebar.download_button(
            label="💾 Descargar GeoTIFF (35 m - SRTM)",
            data=f_dem,
            file_name=f"DEM_Acuifero_{clave_actual}_z12.tif",
            mime="image/tiff",
            type="secondary",
            use_container_width=True
        )
    if gdf_geologia_recortada is not None and not gdf_geologia_recortada.empty:
        zip_shp_bytes = exportar_shapefile_zip(gdf_geologia_recortada, f"Geologia_{clave_actual}")
        st.sidebar.download_button(
            label="📦 Descargar Geología Shapefile (.zip)",
            data=zip_shp_bytes,
            file_name=f"Geologia_Shapefile_{clave_actual}.zip",
            mime="application/zip",
            type="secondary",
            use_container_width=True
        )
        
        # Descarga de la tabla de atributos completa en CSV
        df_atributos_geo = gdf_geologia_recortada.drop(columns=["geometry"], errors="ignore")
        csv_geo_bytes = df_atributos_geo.to_csv(index=False).encode('utf-8-sig')
        st.sidebar.download_button(
            label="📄 Descargar Atributos Geología (CSV)",
            data=csv_geo_bytes,
            file_name=f"Atributos_Geologia_{clave_actual}.csv",
            mime="text/csv",
            type="secondary",
            use_container_width=True
        )
        
    if gdf_estructuras_50k is not None and not gdf_estructuras_50k.empty:
        zip_fallas_bytes = exportar_shapefile_zip(gdf_estructuras_50k, f"Estructuras_50k_{clave_actual}")
        st.sidebar.download_button(
            label="📦 Descargar Fallas Shapefile (.zip)",
            data=zip_fallas_bytes,
            file_name=f"Estructuras_50k_{clave_actual}.zip",
            mime="application/zip",
            type="secondary",
            use_container_width=True
        )

# =======================================================
# 🌐 9. PREPARACIÓN DE LA MALLA THREE.JS (MODO AISLADO 360°)
# =======================================================
@st.cache_data(show_spinner=False)
def preparar_malla_terreno_threejs(ruta_tif):
    with rasterio.open(ruta_tif) as src:
        z = src.read(1)
        nodata = src.nodata
        mask_valida = (z != nodata) & (~np.isnan(z))
        
        h, w = z.shape
        paso = max(1, int(max(h, w) / 220))
        z_sub = z[::paso, ::paso]
        mask_sub = mask_valida[::paso, ::paso]
        
        vmin = float(np.min(z_sub[mask_sub])) if np.any(mask_sub) else 0.0
        vmax = float(np.max(z_sub[mask_sub])) if np.any(mask_sub) else 100.0
        z_norm = np.where(mask_sub, z_sub - vmin, -9999.0)
        
        return {
            "z_grid": z_norm.tolist(),
            "rows": int(z_norm.shape[0]),
            "cols": int(z_norm.shape[1]),
            "vmin": vmin,
            "vmax": vmax,
            "bounds": [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top]
        }

datos_malla_3d = preparar_malla_terreno_threejs(str(ruta_dem_local))
malla_json = json.dumps(datos_malla_3d)

# =======================================================
# 🧊 10A. MOTOR THREE.JS: SOLO ACUÍFERO (BLOQUE AISLADO 360°)
# =======================================================
html_threejs_isolated = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Bloque Geológico 3D Oficial</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <style>
        body {{ margin: 0; padding: 0; overflow: hidden; background: #f8fafc; font-family: 'Segoe UI', Arial, sans-serif; }}
        #container3d {{ width: 100vw; height: 100vh; position: absolute; top: 0; left: 0; }}

        .hud-top {{
            position: absolute; top: 12px; right: 55px; z-index: 1000;
            background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
            padding: 7px 14px; border-radius: 8px; border: 1.5px solid #691C32;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15); font-size: 11px; color: #1e293b;
            display: flex; gap: 14px; align-items: center; pointer-events: none;
        }}
        .hud-top b {{ color: #691C32; margin-right: 3px; }}

        #popup3d {{
            position: absolute; z-index: 2000; display: none;
            background: rgba(255, 255, 255, 0.98); backdrop-filter: blur(10px);
            border-radius: 8px; padding: 10px 14px; border-top: 3.5px solid #691C32;
            box-shadow: 0 8px 24px rgba(0,0,0,0.25); border-left: 1px solid #E2E8F0;
            border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0;
            font-size: 11.5px; color: #1E293B; pointer-events: auto; max-width: 270px;
        }}
        .popup-close {{
            float: right; cursor: pointer; color: #888; font-weight: bold; font-size: 14px; margin-left: 10px;
        }}
        .popup-close:hover {{ color: #691C32; }}

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
            position: absolute; top: 12px; left: 12px; z-index: 1000;
            background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
            width: 295px; border-radius: 10px; overflow: hidden;
            box-shadow: 0 6px 20px rgba(0,0,0,0.25); border-top: 4px solid #691C32;
            border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0;
            font-size: 11.5px; color: #1E293B;
        }}
        .dock-header {{
            background: #691C32; color: white; padding: 9px 12px;
            font-weight: 700; display: flex; justify-content: space-between; align-items: center;
        }}
        .dock-body {{ padding: 12px 14px; max-height: 82vh; overflow-y: auto; }}
        .dock-section {{ margin-bottom: 11px; }}
        .dock-section label {{ font-weight: 700; color: #475569; display: block; margin-bottom: 5px; font-size: 11px; }}
        
        .btn-cam-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }}
        .btn-cam {{
            background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px;
            padding: 5px 8px; font-size: 11px; font-weight: 600; color: #334155;
            cursor: pointer; transition: all 0.2s;
        }}
        .btn-cam:hover {{ background: #DDC9A3; color: #691C32; border-color: #691C32; }}

        .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; }}

        .btn-fullscreen-top {{
            position: absolute; top: 12px; right: 12px; z-index: 1000;
            background: #ffffff; width: 32px; height: 32px; border-radius: 4px;
            border: 1px solid #cbd5e1; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; transition: background 0.2s;
        }}
        .btn-fullscreen-top:hover {{ background: #f1f5f9; }}

        .btn-screenshot {{
            width: 100%; background: #691C32; color: white; border: none;
            border-radius: 6px; padding: 8px; font-weight: 700; font-size: 11.5px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            gap: 6px; transition: background 0.2s; box-shadow: 0 2px 6px rgba(105,28,50,0.3);
        }}
        .btn-screenshot:hover {{ background: #88102B; }}
    </style>
</head>
<body>
<div id="container3d"></div>

<div class="hud-top">
    <div><b>LON:</b> <span id="hud-lon">--</span></div>
    <div><b>LAT:</b> <span id="hud-lat">--</span></div>
    <div style="color:#008a3b;"><b>COTA:</b> <span id="hud-ele">-- msnm</span></div>
</div>

<div id="popup3d">
    <span class="popup-close" onclick="cerrarPopup3D()">✕</span>
    <div id="popup-content"></div>
</div>

<button class="btn-fullscreen-top" onclick="toggleFullscreen()" title="Pantalla Completa" id="btn-fs">
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" id="fs-svg">
        <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
    </svg>
</button>

<div id="btn-open-dock" class="btn-open-dock-circle" onclick="toggleDock()" title="Abrir Instrumentación 3D" style="display: none;">
    ☰
</div>

<div id="dock-panel" class="workbench-dock">
    <div class="dock-header">
        <div style="display:flex; align-items:center; gap:6px;">
            <span>🛠️ Instrumentación 3D</span>
            <span style="font-size: 10px; opacity: 0.85;">CONAGUA</span>
        </div>
        <button onclick="toggleDock()" style="background:transparent; border:none; color:white; font-size:16px; font-weight:bold; cursor:pointer; line-height:1; padding:2px 5px;" title="Contraer panel">✕</button>
    </div>
    <div class="dock-body">
        
        <div class="dock-section">
            <label>🧭 Proyección y Vistas Cardinales (360°):</label>
            <div class="btn-cam-grid">
                <button class="btn-cam" onclick="setCameraView('top')">⬆️ Planta (2D)</button>
                <button class="btn-cam" onclick="setCameraView('iso')">🧊 Isométrica</button>
                <button class="btn-cam" onclick="setCameraView('south')">⬇️ Frente Sur</button>
                <button class="btn-cam" onclick="setCameraView('east')">➡️ Perfil Este</button>
                <button class="btn-cam" onclick="setCameraView('west')">⬅️ Perfil Oeste</button>
                <button class="btn-cam" onclick="setCameraView('under')">🔄 Desde Abajo</button>
            </div>
            <div style="font-size:10px; color:#64748B; margin-top:4px;">
                🖱️ <b>Arrastrar Clic Derecho:</b> Mover Este-Oeste y Norte-Sur.
            </div>
        </div>

        <div class="dock-section">
            <label>📐 Remuestreo del Terreno:</label>
            <select id="sel-remuestreo" style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:5px; padding:6px 8px; font-size:11px; font-weight:600; color:#334155; width:100%; cursor:pointer;" onchange="cambiarRemuestreoThree(this.value)">
                <option value="bilineal" selected>Bilineal (Suavizado continuo)</option>
                <option value="cubico">Cúbico (Spline alta curvatura)</option>
                <option value="vecino">Vecino más próximo (Escalonado)</option>
            </select>
        </div>

        <div class="dock-section">
            <label>📡 Resolución Ráster DEM:</label>
            <select id="sel-resolucion-dem" style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:5px; padding:6px 8px; font-size:11px; font-weight:600; color:#334155; width:100%; cursor:pointer;" onchange="cambiarResolucionThree(this.value)">
                <option value="1" selected>Alta (~35 m / SRTM NASA - Zoom 12)</option>
                <option value="2">Media (~70 m - Zoom 11)</option>
                <option value="4">Regional (~140 m - Zoom 10)</option>
            </select>
        </div>

        <div class="dock-section" style="background:#f8fafc; padding:8px; border-radius:6px; border:1px solid #e2e8f0;">
            <label style="color:#691C32;">☀️ Simulación Solar (Luz y Sombras):</label>
            <div style="font-size:10.5px; margin-bottom:4px;">Azimut del Sol: <b id="val-sol">315° (Noroeste)</b></div>
            <input type="range" class="slider-ctrl" id="slider-sol" min="0" max="360" step="5" value="315" oninput="cambiarLuzSolar(this.value)">
            
            <div style="font-size:10.5px; margin-top:6px; margin-bottom:4px;">Intensidad de Sombreado: <b id="val-shade">80%</b></div>
            <input type="range" class="slider-ctrl" id="slider-shade" min="0.2" max="1.5" step="0.05" value="0.8" oninput="cambiarIntensidadSombra(this.value)">
        </div>

        <div class="dock-section" style="background:#f8fafc; padding:8px 10px; border-radius:6px; border:1px solid #e2e8f0;">
            <label style="color:#691C32; margin-bottom:3px;">📏 Curvas de Nivel (Cotas):</label>
            <div style="font-size:11px; margin-bottom:5px;">Equidistancia: <b id="val-cotas" style="color:#691C32;">Cada 50 m</b></div>
            <input type="range" class="slider-ctrl" id="slider-cotas" min="0" max="250" step="25" value="50" oninput="cambiarEquidistanciaCotasThree(this.value)">
            <div style="display:flex; justify-content:space-between; font-size:9.5px; color:#64748B; margin-top:3px;">
                <span>Off (0m)</span>
                <span>25m</span>
                <span>50m</span>
                <span>100m</span>
                <span>250m</span>
            </div>
        </div>

        <div class="dock-section">
            <label>⛰️ Exageración de Relieve: <b id="val-exag" style="color:#691C32;">1.0x</b></label>
            <input type="range" class="slider-ctrl" id="slider-exag" min="0.5" max="6.0" step="0.1" value="1.0" oninput="cambiarExageracionRelieve(this.value)">
        </div>

        <div class="dock-section">
            <label>🎨 Transparencia Litología SGM: <b id="val-opac">100%</b></label>
            <input type="range" class="slider-ctrl" id="slider-opac" min="0.1" max="1.0" step="0.05" value="1.0" oninput="cambiarOpacidadThree(this.value)">
            
            <div style="margin-top: 8px; display: flex; flex-direction: column; gap: 5px;">
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-lines" checked onchange="toggleContactos()"> Contactos Geológicos SGM
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-estructuras" checked onchange="toggleEstructuras()"> ⚡ Fallas y Fracturas 1:50k (SGM)
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-border" checked onchange="toggleBorde()"> Límite Oficial Acuífero
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-pozos" checked onchange="togglePozos(this.checked)"> 📍 Pozos Subterráneos 3D
                </label>
            </div>
        </div>

        <button class="btn-screenshot" onclick="capturarPantalla3D()">
            📸 Capturar Bloque 3D (PNG)
        </button>
    </div>
</div>

<script>
    const dataGeologia = {geojson_geologia};
    const dataEstructuras = {geojson_estructuras};
    const dataBorde = {geojson_borde};
    const dataCurvas = {geojson_curvas_cota};
    const dataPozos = {pozos_3d_json};
    const mallaInfo = {malla_json};

    const minX = mallaInfo.bounds[0];
    const minY = mallaInfo.bounds[1];
    const maxX = mallaInfo.bounds[2];
    const maxY = mallaInfo.bounds[3];

    // ===================================================
    // 🎨 1. TEXTURA VECTORIAL 2K CONTINUA
    // ===================================================
    const canvasTex = document.createElement('canvas');
    canvasTex.width = 2048;
    canvasTex.height = 2048;
    const ctx = canvasTex.getContext('2d');

    function geoToCanvas(x, y) {{
        const cx = ((x - minX) / (maxX - minX)) * 2048;
        const cy = ((maxY - y) / (maxY - minY)) * 2048;
        return [cx, cy];
    }}

    function dibujarPoligono(coords, fillColor, strokeColor, lineWidth) {{
        ctx.beginPath();
        for (let i = 0; i < coords.length; i++) {{
            const [cx, cy] = geoToCanvas(coords[i][0], coords[i][1]);
            if (i === 0) ctx.moveTo(cx, cy);
            else ctx.lineTo(cx, cy);
        }}
        ctx.closePath();
        if (fillColor) {{
            ctx.fillStyle = fillColor;
            ctx.fill();
        }}
        if (strokeColor && lineWidth > 0) {{
            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = lineWidth;
            ctx.stroke();
        }}
    }}

    let pasoCotasActual = 50;

    function redibujarTexturaCompleta() {{
        ctx.clearRect(0, 0, 2048, 2048);

        // 1. Polígonos de Litología SGM
        const verContactos = document.getElementById('chk-lines').checked;
        if (dataGeologia && dataGeologia.features) {{
            dataGeologia.features.forEach(f => {{
                const color = f.properties.COLOR_HEX || '#B0BEC5';
                const geom = f.geometry;
                const stroke = verContactos ? '#334155' : null;
                const w = verContactos ? 1.5 : 0;
                if (geom.type === 'Polygon') {{
                    dibujarPoligono(geom.coordinates[0], color, stroke, w);
                }} else if (geom.type === 'MultiPolygon') {{
                    geom.coordinates.forEach(poly => {{
                        dibujarPoligono(poly[0], color, stroke, w);
                    }});
                }}
            }});
        }}

        // 2. Fallas y Fracturas 1:50,000 del SGM
        const verFallas = document.getElementById('chk-estructuras')?.checked;
        if (verFallas && dataEstructuras && dataEstructuras.features) {{
            ctx.strokeStyle = '#dc2626';
            ctx.lineWidth = 3.5;
            ctx.setLineDash([8, 4]);
            dataEstructuras.features.forEach(f => {{
                const geom = f.geometry;
                const coordsArr = geom.type === 'LineString' ? [geom.coordinates] : geom.coordinates;
                coordsArr.forEach(coords => {{
                    ctx.beginPath();
                    for (let i = 0; i < coords.length; i++) {{
                        const [cx, cy] = geoToCanvas(coords[i][0], coords[i][1]);
                        if (i === 0) ctx.moveTo(cx, cy);
                        else ctx.lineTo(cx, cy);
                    }}
                    ctx.stroke();
                }});
            }});
            ctx.setLineDash([]);
        }}

        // 3. Curvas de Nivel drapeadas en 2K
        if (pasoCotasActual > 0 && dataCurvas && dataCurvas.features) {{
            ctx.strokeStyle = '#475569';
            ctx.lineWidth = 1.0;
            ctx.setLineDash([4, 2]);
            dataCurvas.features.forEach(f => {{
                const cota = f.properties.cota;
                if (cota % pasoCotasActual === 0) {{
                    const coords = f.geometry.coordinates;
                    ctx.beginPath();
                    for (let i = 0; i < coords.length; i++) {{
                        const [cx, cy] = geoToCanvas(coords[i][0], coords[i][1]);
                        if (i === 0) ctx.moveTo(cx, cy);
                        else ctx.lineTo(cx, cy);
                    }}
                    ctx.stroke();
                }}
            }});
            ctx.setLineDash([]);
        }}

        // 4. Límite Oficial Acuífero CONAGUA
        if (document.getElementById('chk-border').checked && dataBorde && dataBorde.features) {{
            dataBorde.features.forEach(f => {{
                const geom = f.geometry;
                if (geom.type === 'Polygon') dibujarPoligono(geom.coordinates[0], null, '#691C32', 4.5);
                else if (geom.type === 'MultiPolygon') geom.coordinates.forEach(poly => dibujarPoligono(poly[0], null, '#691C32', 4.5));
            }});
        }}

        if (textureVectorial) textureVectorial.needsUpdate = true;
    }}

    let textureVectorial = new THREE.CanvasTexture(canvasTex);
    textureVectorial.anisotropy = 16;
    redibujarTexturaCompleta();

    // ===================================================
    // 🧊 2. ESCENA THREE.JS
    // ===================================================
    const container = document.getElementById('container3d');
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8fafc);

    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 1, 5000);
    camera.position.set(0, -320, 240);

    const renderer = new THREE.WebGLRenderer({{ antialias: true, preserveDrawingBuffer: true }});
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxDistance = 1600;
    controls.minDistance = 20;

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.70);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xfff7ed, 0.85);
    dirLight.position.set(-200, 200, 300);
    dirLight.castShadow = true;
    scene.add(dirLight);

    // ===================================================
    // ⛰️ 3. MALLA TRIDIMENSIONAL AISLADA
    // ===================================================
    const rows = mallaInfo.rows;
    const cols = mallaInfo.cols;
    const grid = mallaInfo.z_grid;
    const geomWidth = 350;
    const geomHeight = (geomWidth * (rows / cols));
    let baseExag = 1.0;
    let escalaActualRelieve = 1.0;
    const maxDesnivel = (mallaInfo.vmax - mallaInfo.vmin) || 100;
    const alturaNormalizada = 40.0;

    let meshAcuifero = null;

    function construirMallaTerreno(stepResolution) {{
        if (meshAcuifero) scene.remove(meshAcuifero);

        const geom = new THREE.BufferGeometry();
        const vertices = [];
        const uvs = [];
        const indices = [];

        const vMap = new Int32Array(rows * cols).fill(-1);
        let vIdx = 0;

        for (let r = 0; r < rows; r += stepResolution) {{
            for (let c = 0; c < cols; c += stepResolution) {{
                const zVal = grid[r][c];
                if (zVal > -9000) {{
                    const x = (c / (cols - 1) - 0.5) * geomWidth;
                    const y = (0.5 - r / (rows - 1)) * geomHeight;
                    const z = (zVal / maxDesnivel) * alturaNormalizada * baseExag;

                    vertices.push(x, y, z);
                    uvs.push(c / (cols - 1), 1.0 - (r / (rows - 1)));
                    vMap[r * cols + c] = vIdx++;
                }}
            }}
        }}

        for (let r = 0; r < rows - stepResolution; r += stepResolution) {{
            for (let c = 0; c < cols - stepResolution; c += stepResolution) {{
                const v00 = vMap[r * cols + c];
                const v10 = vMap[(r + stepResolution) * cols + c];
                const v01 = vMap[r * cols + (c + stepResolution)];
                const v11 = vMap[(r + stepResolution) * cols + (c + stepResolution)];

                if (v00 !== -1 && v10 !== -1 && v01 !== -1) indices.push(v00, v10, v01);
                if (v10 !== -1 && v11 !== -1 && v01 !== -1) indices.push(v10, v11, v01);
            }}
        }}

        geom.setIndex(indices);
        geom.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
        geom.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
        geom.computeVertexNormals();

        const mat = new THREE.MeshStandardMaterial({{
            map: textureVectorial,
            roughness: 0.55,
            metalness: 0.05,
            side: THREE.DoubleSide
        }});

        meshAcuifero = new THREE.Mesh(geom, mat);
        meshAcuifero.castShadow = true;
        meshAcuifero.receiveShadow = true;
        meshAcuifero.scale.set(1, 1, escalaActualRelieve);
        scene.add(meshAcuifero);
    }}

    construirMallaTerreno(1);

    // ===================================================
    // 🎯 4. MOTOR DE POZOS SUBTERRÁNEOS ANCLADOS AL TERRENO
    // ===================================================
    const grupoPozos = new THREE.Group();

    function obtenerCotaEnCoordenadas(lon, lat) {{
        const cFloat = ((lon - minX) / (maxX - minX)) * (cols - 1);
        const rFloat = ((maxY - lat) / (maxY - minY)) * (rows - 1);
        const r0 = Math.max(0, Math.min(rows - 1, Math.round(rFloat)));
        const c0 = Math.max(0, Math.min(cols - 1, Math.round(cFloat)));
        const zVal = grid[r0][c0];
        if (zVal > -9000) {{
            return (zVal / maxDesnivel) * alturaNormalizada * baseExag;
        }}
        return 0.0;
    }}

    function construirPozosSubterraneos() {{
        while (grupoPozos.children.length > 0) {{
            const obj = grupoPozos.children[0];
            grupoPozos.remove(obj);
        }}

        if (dataPozos && dataPozos.length > 0) {{
            dataPozos.forEach(p => {{
                const px = ((p.lon - minX) / (maxX - minX) - 0.5) * geomWidth;
                const py = (0.5 - (maxY - p.lat) / (maxY - minY)) * geomHeight;
                
                const zSuperficieBase = obtenerCotaEnCoordenadas(p.lon, p.lat);
                const zSuperficieActual = zSuperficieBase * escalaActualRelieve;
                const cotaMsnmReal = Math.round(mallaInfo.vmin + (zSuperficieBase / (alturaNormalizada * baseExag)) * maxDesnivel);

                const profMetros = p.profundidad && p.profundidad > 0 ? parseFloat(p.profundidad) : 150.0;
                const longitudCilindro = (profMetros / maxDesnivel) * alturaNormalizada * baseExag * escalaActualRelieve;

                let tipo = (p.tipo || '').toLowerCase();
                let colHex = p.color_hex ? parseInt(p.color_hex.replace('#',''), 16) : ((tipo.includes('requerid') || tipo.includes('nuevo')) ? 0x9F2241 : 0x008a3b);

                // Brocal a nivel de terreno
                const geomCabeza = new THREE.CylinderGeometry(2.4, 2.4, 2.5, 16);
                const matCabeza = new THREE.MeshStandardMaterial({{ color: colHex, roughness: 0.3 }});
                const cabeza = new THREE.Mesh(geomCabeza, matCabeza);
                cabeza.rotation.x = Math.PI / 2;
                cabeza.position.set(px, py, zSuperficieActual + 1.2);
                cabeza.userData = {{ ...p, cota_msnm: cotaMsnmReal, esPozo: true }};
                grupoPozos.add(cabeza);

                // Ademe penetrando hacia el subsuelo
                const geomAdeme = new THREE.CylinderGeometry(1.3, 1.3, Math.max(4.0, longitudCilindro), 16);
                const matAdeme = new THREE.MeshStandardMaterial({{ color: colHex, metalness: 0.3, roughness: 0.4 }});
                const ademe = new THREE.Mesh(geomAdeme, matAdeme);
                ademe.rotation.x = Math.PI / 2;
                ademe.position.set(px, py, zSuperficieActual - longitudCilindro / 2.0);
                ademe.userData = {{ ...p, cota_msnm: cotaMsnmReal, esPozo: true }};
                grupoPozos.add(ademe);
            }});
        }}
    }}

    construirPozosSubterraneos();
    scene.add(grupoPozos);

    // ===================================================
    // 🎛️ 5. CONTROLES Y PERSISTENCIA (LOCALSTORAGE)
    // ===================================================
    let estadoGuardado = localStorage.getItem('dock_3d_abierto');
    let dockAbierto = estadoGuardado !== null ? (estadoGuardado === 'true') : true;

    function aplicarEstadoVisualDock() {{
        const dock = document.getElementById('dock-panel');
        const btnOpen = document.getElementById('btn-open-dock');
        if (dock && btnOpen) {{
            dock.style.display = dockAbierto ? 'block' : 'none';
            btnOpen.style.display = dockAbierto ? 'none' : 'flex';
        }}
    }}
    aplicarEstadoVisualDock();

    function toggleDock() {{
        dockAbierto = !dockAbierto;
        localStorage.setItem('dock_3d_abierto', dockAbierto ? 'true' : 'false');
        aplicarEstadoVisualDock();
    }}

    function setCameraView(view) {{
        controls.reset();
        if (view === 'top') camera.position.set(0, 0, 420);
        else if (view === 'iso') camera.position.set(-180, -260, 220);
        else if (view === 'south') camera.position.set(0, -360, 60);
        else if (view === 'east') camera.position.set(380, 0, 80);
        else if (view === 'west') camera.position.set(-380, 0, 80);
        else if (view === 'under') camera.position.set(0, -200, -280);
        controls.update();
    }}

    function cambiarExageracionRelieve(val) {{
        escalaActualRelieve = parseFloat(val) / baseExag;
        if (meshAcuifero) meshAcuifero.scale.set(1, 1, escalaActualRelieve);
        construirPozosSubterraneos();
        document.getElementById('val-exag').innerText = parseFloat(val).toFixed(1) + 'x';
    }}

    function cambiarRemuestreoThree(modo) {{
        if (!meshAcuifero) return;
        if (modo === 'vecino') meshAcuifero.material.flatShading = true;
        else if (modo === 'cubico') {{ meshAcuifero.material.flatShading = false; meshAcuifero.material.roughness = 0.4; }}
        else {{ meshAcuifero.material.flatShading = false; meshAcuifero.material.roughness = 0.55; }}
        meshAcuifero.material.needsUpdate = true;
    }}

    function cambiarResolucionThree(stepVal) {{
        construirMallaTerreno(parseInt(stepVal));
        construirPozosSubterraneos();
    }}

    function cambiarEquidistanciaCotasThree(val) {{
        pasoCotasActual = parseInt(val);
        const lbl = document.getElementById('val-cotas');
        lbl.innerText = pasoCotasActual === 0 ? "Desactivadas" : "Cada " + pasoCotasActual + " m";
        redibujarTexturaCompleta();
    }}

    function cambiarOpacidadThree(val) {{
        document.getElementById('val-opac').innerText = Math.round(val * 100) + '%';
        if (meshAcuifero) {{
            meshAcuifero.material.transparent = true;
            meshAcuifero.material.opacity = parseFloat(val);
            meshAcuifero.material.needsUpdate = true;
        }}
    }}

    function cambiarLuzSolar(val) {{
        const deg = parseInt(val);
        const rad = (deg - 90) * (Math.PI / 180);
        dirLight.position.set(Math.cos(rad) * 300, Math.sin(rad) * 300, 250);
        let card = deg < 45 ? "Norte" : deg < 135 ? "Este" : deg < 225 ? "Sur" : deg < 315 ? "Oeste" : "Norte";
        document.getElementById('val-sol').innerText = deg + '° (' + card + ')';
    }}

    function cambiarIntensidadSombra(val) {{
        const shade = parseFloat(val);
        document.getElementById('val-shade').innerText = Math.round(shade * 100) + '%';
        dirLight.intensity = shade;
        ambientLight.intensity = Math.max(0.3, 1.2 - shade * 0.5);
    }}

    function toggleContactos() {{ redibujarTexturaCompleta(); }}
    function toggleEstructuras() {{ redibujarTexturaCompleta(); }}
    function toggleBorde() {{ redibujarTexturaCompleta(); }}
    function togglePozos(visible) {{ grupoPozos.visible = visible; }}

    // Pantalla Completa Oficial SVG
    const iconExp = `<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>`;
    const iconCmp = `<path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>`;

    function toggleFullscreen() {{
        if (!document.fullscreenElement) {{
            document.documentElement.requestFullscreen().catch(err => {{}});
        }} else {{
            if (document.exitFullscreen) document.exitFullscreen();
        }}
    }}

    document.addEventListener('fullscreenchange', () => {{
        const svgPath = document.querySelector('#fs-svg path');
        if (svgPath) {{
            svgPath.setAttribute('d', document.fullscreenElement ? iconCmp : iconExp);
        }}
        setTimeout(() => {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }}, 200);
    }});

    // ===================================================
    // 🎯 6. INSPECCIÓN AL CLIC EN POZOS Y GEOLOGÍA
    // ===================================================
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    const popupEl = document.getElementById('popup3d');
    const popupContent = document.getElementById('popup-content');

    function cerrarPopup3D() {{
        popupEl.style.display = 'none';
    }}

    function puntoEnPoligono(pt, coords) {{
        let x = pt[0], y = pt[1];
        let dentro = false;
        for (let i = 0, j = coords.length - 1; i < coords.length; j = i++) {{
            let xi = coords[i][0], yi = coords[i][1];
            let xj = coords[j][0], yj = coords[j][1];
            let intersecta = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
            if (intersecta) dentro = !dentro;
        }}
        return dentro;
    }}

    function identificarFormacionGeologica(lon, lat) {{
        if (!dataGeologia || !dataGeologia.features) return null;
        for (let f of dataGeologia.features) {{
            let geom = f.geometry;
            if (geom.type === 'Polygon') {{
                if (puntoEnPoligono([lon, lat], geom.coordinates[0])) return f.properties;
            }} else if (geom.type === 'MultiPolygon') {{
                for (let poly of geom.coordinates) {{
                    if (puntoEnPoligono([lon, lat], poly[0])) return f.properties;
                }}
            }}
        }}
        return null;
    }}

    window.addEventListener('click', (event) => {{
        if (event.target.closest('#dock-panel') || event.target.closest('#popup3d') || event.target.closest('.hud-top') || event.target.closest('#btn-fs') || event.target.closest('#btn-open-dock')) {{
            return;
        }}

        mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
        raycaster.setFromCamera(mouse, camera);

        // 1. Clic en Pozo
        if (grupoPozos.visible && grupoPozos.children.length > 0) {{
            const hitsPozos = raycaster.intersectObjects(grupoPozos.children);
            if (hitsPozos.length > 0) {{
                const d = hitsPozos[0].object.userData;
                popupContent.innerHTML = `
                    <h4 style="margin:0 0 6px 0; color:#691C32; border-bottom:1px solid #ddd; padding-bottom:3px;">📍 ${{d.nombre || 'Pozo'}}</h4>
                    <div style="line-height:1.5;">
                        <b>Tipo:</b> ${{d.tipo || 'Infraestructura'}}<br>
                        <b>Profundidad Real:</b> <span style="color:#691C32; font-weight:bold;">${{d.profundidad || 150}} m</span><br>
                        <b>Cota Terreno:</b> ${{d.cota_msnm || '--'}} msnm<br>
                        <b>Lat:</b> ${{d.lat.toFixed(5)}} | <b>Lon:</b> ${{d.lon.toFixed(5)}}
                    </div>
                `;
                popupEl.style.left = Math.min(window.innerWidth - 270, event.clientX + 14) + 'px';
                popupEl.style.top = Math.max(20, event.clientY - 40) + 'px';
                popupEl.style.display = 'block';
                return;
            }}
        }}

        // 2. Clic en Geología
        if (meshAcuifero) {{
            const hitsTerreno = raycaster.intersectObject(meshAcuifero);
            if (hitsTerreno.length > 0) {{
                const p = hitsTerreno[0].point;
                const lon = minX + (p.x / geomWidth + 0.5) * (maxX - minX);
                const lat = maxY - (0.5 - p.y / geomHeight) * (maxY - minY);
                const cotaNorm = (p.z / (alturaNormalizada * baseExag * escalaActualRelieve)) * maxDesnivel;
                const cotaMsnm = Math.round(mallaInfo.vmin + cotaNorm);

                // A) Buscar si diste clic sobre una Falla Geológica 1:50k
                let fallaEncontrada = null;
                if (dataEstructuras && dataEstructuras.features) {{
                    for (let f of dataEstructuras.features) {{
                        const coordsArr = f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.coordinates;
                        for (let coords of coordsArr) {{
                            for (let pt of coords) {{
                                // Tolerancia de clic (~300 metros)
                                const dist = Math.hypot(pt[0] - lon, pt[1] - lat);
                                if (dist < 0.003) {{
                                    fallaEncontrada = f.properties;
                                    break;
                                }}
                            }}
                            if (fallaEncontrada) break;
                        }}
                        if (fallaEncontrada) break;
                    }}
                }}

                // -------------------------------------------------------------
                // CASO 1: SE TOCÓ UNA FALLA O FRACTURA (SGM 1:50k)
                // -------------------------------------------------------------
                if (fallaEncontrada) {{
                    let azVal = fallaEncontrada.AZIMUTH !== undefined && fallaEncontrada.AZIMUTH !== null ? fallaEncontrada.AZIMUTH : (fallaEncontrada.Azimuth || fallaEncontrada.azimuth || fallaEncontrada.AZIMUT);
                    let azTxt = (azVal !== undefined && azVal !== null && String(azVal).trim() !== '' && String(azVal) !== 'null') ? parseFloat(azVal).toFixed(2) + '°' : 'S/D';

                    let incVal = fallaEncontrada.INCLINACION !== undefined && fallaEncontrada.INCLINACION !== null ? fallaEncontrada.INCLINACION : (fallaEncontrada.Inclinacion || fallaEncontrada.inclinacion);
                    let incTxt = (incVal !== undefined && incVal !== null && String(incVal).trim() !== '' && String(incVal) !== 'null') ? parseFloat(incVal).toFixed(0) + '°' : '0°';

                    // Si no tiene NOMBRE o es nulo, asigna el tipo de estructura al título
                    let tipoEstr = fallaEncontrada.ESTRUCTURAS || fallaEncontrada.TIPO_ESTR || 'Estructura Geológica';
                    let rawNom = fallaEncontrada.NOMBRE || fallaEncontrada.NOM_ESTR;
                    let tieneNom = rawNom && String(rawNom).trim() !== '' && String(rawNom).toUpperCase() !== 'NULL' && String(rawNom).toUpperCase() !== 'NONE';
                    let tituloMostrar = tieneNom ? String(rawNom).trim() : tipoEstr;

                    popupContent.innerHTML = `
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px; border-bottom:1px solid #ddd; padding-bottom:4px;">
                            <span style="color:#dc2626; font-size:16px;">⚡</span>
                            <h4 style="margin:0; color:#dc2626; font-size:13px;">${{tituloMostrar}}</h4>
                        </div>
                        <div style="line-height:1.5; font-size:11px; color:#1E293B;">
                            <b>Tipo:</b> ${{tipoEstr}}<br>
                            <b>Azimut de Rumbo:</b> <span style="color:#0f172a; font-weight:bold;">${{azTxt}}</span><br>
                            <b>Inclinación / Echado:</b> ${{incTxt}}<br>
                            <b>Cota Terreno:</b> <span style="color:#008A3B; font-weight:bold;">${{cotaMsnm}} msnm</span><br>
                            <span style="color:#64748B; font-size:10px;">Coords: ${{lat.toFixed(4)}}°, ${{lon.toFixed(4)}}°</span>
                        </div>
                    `;
                
                // -------------------------------------------------------------
                // CASO 2: SE TOCÓ LA ROCA (FICHA LITOLÓGICA ENRIQUECIDA)
                // -------------------------------------------------------------
                }} else {{
                    const infoLito = identificarFormacionGeologica(lon, lat);

                    if (infoLito) {{
                        const claveSgm = infoLito.CLAVE_SGM || infoLito.ETIQUETA_LITO || 'S/C';
                        const formacion = (infoLito.FORMACION && String(infoLito.FORMACION).trim() !== '' && String(infoLito.FORMACION).toUpperCase() !== 'NINGUNO' && String(infoLito.FORMACION).toUpperCase() !== 'NULL') ? String(infoLito.FORMACION).trim() : 'Formación No Asignada';
                        const litologia = infoLito.LITOLOGIA || 'Indiferenciada';
                        const roca = infoLito.ROCA || 'Sedimentaria';
                        const colorHex = infoLito.COLOR_HEX || '#B0BEC5';

                        // Construcción de la edad geológica: Periodo (Ed. Inicio - Ed. Final)
                        let edadGeo = infoLito.PERIODO || '';
                        if (infoLito.EDINICIO || infoLito.EDFINAL) {{
                            const ini = infoLito.EDINICIO || '';
                            const fin = infoLito.EDFINAL || '';
                            edadGeo += (ini === fin || !fin) ? ` (${{ini}})` : ` (${{ini}} - ${{fin}})`;
                        }}
                        if (!edadGeo.trim()) edadGeo = infoLito.ERA || 'S/D';

                        popupContent.innerHTML = `
                            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; border-bottom:1.5px solid #E2E8F0; padding-bottom:5px;">
                                <div style="display:flex; align-items:center; gap:7px;">
                                    <span style="width:14px; height:14px; background:${{colorHex}}; border-radius:3px; border:1px solid #475569; display:inline-block; flex-shrink:0;"></span>
                                    <h4 style="margin:0; color:#691C32; font-size:13px; font-weight:700;">${{formacion}}</h4>
                                </div>
                                <span style="background:#F1F5F9; border:1px solid #CBD5E1; color:#334155; font-size:10px; font-weight:700; padding:1px 5px; border-radius:4px;">${{claveSgm}}</span>
                            </div>
                            <div style="line-height:1.5; font-size:11px; color:#1E293B;">
                                <b>Litología:</b> ${{litologia}}<br>
                                <b>Tipo de Roca:</b> ${{roca}}<br>
                                <b>Edad Geológica:</b> ${{edadGeo}}<br>
                                <b>Cota Terreno:</b> <span style="color:#008A3B; font-weight:bold;">${{cotaMsnm}} msnm</span><br>
                                <span style="color:#64748B; font-size:10px;">Coords: ${{lat.toFixed(4)}}°, ${{lon.toFixed(4)}}°</span>
                            </div>
                        `;
                    }} else {{
                        popupContent.innerHTML = `
                            <h4 style="margin:0 0 4px 0; color:#691C32; font-size:13px;">Terreno Sin Clasificar</h4>
                            <div style="font-size:11px; line-height:1.4;">
                                <b>Cota:</b> <span style="color:#008A3B; font-weight:bold;">${{cotaMsnm}} msnm</span><br>
                                <span style="color:#64748B; font-size:10px;">Coords: ${{lat.toFixed(4)}}°, ${{lon.toFixed(4)}}°</span>
                            </div>
                        `;
                    }}
                }}

                popupEl.style.left = Math.min(window.innerWidth - 270, event.clientX + 14) + 'px';
                popupEl.style.top = Math.max(20, event.clientY - 40) + 'px';
                popupEl.style.display = 'block';
                return;
            }}
        }}

        cerrarPopup3D();
    }});

    window.addEventListener('mousemove', (event) => {{
        mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

        if (meshAcuifero) {{
            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObject(meshAcuifero);
            if (intersects.length > 0) {{
                const p = intersects[0].point;
                const lon = minX + (p.x / geomWidth + 0.5) * (maxX - minX);
                const lat = maxY - (0.5 - p.y / geomHeight) * (maxY - minY);
                const cotaNorm = (p.z / (alturaNormalizada * baseExag * escalaActualRelieve)) * maxDesnivel;
                const cotaMsnm = Math.round(mallaInfo.vmin + cotaNorm);

                document.getElementById('hud-lon').innerText = lon.toFixed(4) + '°';
                document.getElementById('hud-lat').innerText = lat.toFixed(4) + '°';
                document.getElementById('hud-ele').innerText = Math.round(cotaMsnm) + ' msnm';
            }} else {{
                document.getElementById('hud-lon').innerText = '--';
                document.getElementById('hud-lat').innerText = '--';
                document.getElementById('hud-ele').innerText = '-- msnm';
            }}
        }}
    }});

    function capturarPantalla3D() {{
        renderer.render(scene, camera);
        const dataURL = renderer.domElement.toDataURL('image/png');
        const link = document.createElement('a');
        link.download = 'Bloque_Geologico_3D_{clave_actual}.png';
        link.href = dataURL;
        link.click();
    }}

    window.addEventListener('resize', () => {{
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    }});

    function animate() {{
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    }}
    animate();
</script>
</body>
</html>
"""

# =======================================================
# 🌐 10B. MOTOR MAPLIBRE: CON ENTORNO GEOGRÁFICO (MAPA MUNDIAL)
# =======================================================
html_maplibre_world = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Modelo Conceptual 3D SGM</title>
    <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
    <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
    <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; background: #e2e8f0; }}

        .hud-elevation {{
            position: absolute; top: 12px; right: 85px; z-index: 1000;
            background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
            color: #1e293b; padding: 7px 12px; border-radius: 8px;
            border: 1.5px solid #691C32;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15); font-size: 11px;
            display: flex; gap: 12px; align-items: center; pointer-events: none;
        }}
        .hud-item b {{ color: #691C32; margin-right: 4px; }}

        .btn-open-dock-circle {{
            position: absolute; top: 12px; left: 12px; z-index: 1000;
            background: #691C32; color: #ffffff; width: 38px; height: 38px;
            border-radius: 50%; border: 1.5px solid #DDC9A3;
            box-shadow: 0 3px 12px rgba(105, 28, 50, 0.35);
            font-size: 19px; font-weight: bold; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            transition: all 0.2s ease;
        }}
        .btn-open-dock-circle:hover {{
            background: #88102B;
            transform: scale(1.1);
        }}

        .workbench-dock {{
            position: absolute; top: 12px; left: 12px; z-index: 1000;
            background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
            width: 295px; border-radius: 10px; overflow: hidden;
            box-shadow: 0 6px 20px rgba(0,0,0,0.25); border-top: 4px solid #691C32;
            border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0;
            font-size: 11.5px; color: #1E293B;
        }}
        .dock-header {{
            background: #691C32; color: white; padding: 9px 12px;
            font-weight: 700; display: flex; justify-content: space-between; align-items: center;
        }}
        .dock-body {{ padding: 12px 14px; max-height: 82vh; overflow-y: auto; }}
        .dock-section {{ margin-bottom: 11px; }}
        .dock-section label {{ font-weight: 700; color: #475569; display: block; margin-bottom: 5px; font-size: 11px; }}
        
        .btn-cam-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }}
        .btn-cam {{
            background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px;
            padding: 5px 8px; font-size: 11px; font-weight: 600; color: #334155;
            cursor: pointer; transition: all 0.2s;
        }}
        .btn-cam:hover {{ background: #DDC9A3; color: #691C32; border-color: #691C32; }}

        .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; }}

        .btn-screenshot {{
            width: 100%; background: #691C32; color: white; border: none;
            border-radius: 6px; padding: 8px; font-weight: 700; font-size: 11.5px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            gap: 6px; transition: background 0.2s; box-shadow: 0 2px 6px rgba(105,28,50,0.3);
        }}
        .btn-screenshot:hover {{ background: #88102B; }}
    </style>
</head>
<body>
<div id="map"></div>

<div class="hud-elevation">
    <div class="hud-item"><b>LON:</b><span id="hud-lon">--</span></div>
    <div class="hud-item"><b>LAT:</b><span id="hud-lat">--</span></div>
    <div style="color: #15803d;"><b>COTA:</b><span id="hud-ele">-- msnm</span></div>
</div>

<div id="btn-open-dock" class="btn-open-dock-circle" onclick="toggleDock()" title="Abrir Instrumentación 3D" style="display: none;">
    ☰
</div>

<div id="dock-panel" class="workbench-dock">
    <div class="dock-header">
        <div style="display:flex; align-items:center; gap:6px;">
            <span>🛠️ Instrumentación 3D</span>
            <span style="font-size: 10px; opacity: 0.85;">CONAGUA</span>
        </div>
        <button onclick="toggleDock()" style="background:transparent; border:none; color:white; font-size:16px; font-weight:bold; cursor:pointer; line-height:1; padding:2px 5px;" title="Contraer panel">✕</button>
    </div>
    <div class="dock-body">
        <div class="dock-section">
            <label>🧭 Proyección y Vistas:</label>
            <div class="btn-cam-grid">
                <button class="btn-cam" onclick="setCamera('top')">⬆️ Planta (2D)</button>
                <button class="btn-cam" onclick="setCamera('3d')">🧊 Perspectiva 3D</button>
                <button class="btn-cam" onclick="setCamera('south')">⬇️ Vista Sur</button>
                <button class="btn-cam" onclick="setCamera('east')">➡️ Perfil Este</button>
                <button class="btn-cam" onclick="setCamera('west')">⬅️ Perfil Oeste</button>
            </div>
        </div>
        
        <div class="dock-section">
            <label>📐 Remuestreo del Terreno:</label>
            <select id="sel-remuestreo" style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:5px; padding:6px 8px; font-size:11px; font-weight:600; color:#334155; width:100%; cursor:pointer;" onchange="cambiarRemuestreoTerreno(this.value)">
                <option value="bilineal" selected>Bilineal (Suavizado continuo)</option>
                <option value="cubico">Cúbico (Spline alta curvatura)</option>
                <option value="vecino">Vecino más próximo (Escalonado)</option>
            </select>
        </div>
        
        <div class="dock-section">
            <label>📡 Resolución Ráster DEM:</label>
            <select id="sel-resolucion-dem" style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:5px; padding:6px 8px; font-size:11px; font-weight:600; color:#334155; width:100%; cursor:pointer;" onchange="cambiarResolucionDEM(this.value)">
                <option value="12" selected>Alta (~35 m / SRTM NASA - Zoom 12)</option>
                <option value="11">Media (~70 m - Zoom 11)</option>
                <option value="10">Regional (~140 m - Zoom 10)</option>
            </select>
        </div>
        
        <div class="dock-section" style="background:#f8fafc; padding:8px; border-radius:6px; border:1px solid #e2e8f0; margin-top:8px;">
            <label style="color:#691C32;">☀️ Simulación Solar (Luz y Sombras):</label>
            <div style="font-size:10.5px; margin-bottom:4px;">Azimut del Sol: <b id="val-azimut" style="color:#691C32;">315° (Noroeste)</b></div>
            <input type="range" class="slider-ctrl" id="slider-azimut" min="0" max="360" step="5" value="315" oninput="cambiarAzimutSolar(this.value)">
            
            <div style="font-size:10.5px; margin-top:6px; margin-bottom:4px;">Sombreado de Laderas (Hillshade): <b id="val-shade">45%</b></div>
            <input type="range" class="slider-ctrl" id="slider-shade" min="0" max="1" step="0.05" value="0.45" oninput="cambiarIntensidadHillshade(this.value)">
        </div>
        
        <div class="dock-section" style="background:#f8fafc; padding:8px 10px; border-radius:6px; border:1px solid #e2e8f0;">
            <label style="color:#691C32; margin-bottom:3px;">📏 Curvas de Nivel (Cotas):</label>
            <div style="font-size:11px; margin-bottom:5px;">Equidistancia: <b id="val-cotas" style="color:#691C32;">Cada 50 m</b></div>
            <input type="range" class="slider-ctrl" id="slider-cotas" min="0" max="250" step="25" value="50" oninput="cambiarEquidistanciaCotas(this.value)">
            <div style="display:flex; justify-content:space-between; font-size:9.5px; color:#64748B; margin-top:3px;">
                <span>Off (0m)</span>
                <span>25m</span>
                <span>50m</span>
                <span>100m</span>
                <span>250m</span>
            </div>
        </div>

        <div class="dock-section">
            <label>⛰️ Relieve Vertical: <span id="val-exag" style="color:#691C32;">1.5x</span></label>
            <input type="range" class="slider-ctrl" id="slider-exag" min="0.5" max="5.0" step="0.1" value="1.5" oninput="cambiarExageracion(this.value)">
        </div>

        <div class="dock-section">
            <label>🎨 Transparencia Litología SGM: <span id="val-opac">85%</span></label>
            <input type="range" class="slider-ctrl" id="slider-opac" min="0" max="1" step="0.05" value="0.85" oninput="cambiarOpacidad(this.value)">
            
            <div style="margin-top: 8px; display: flex; flex-direction: column; gap: 5px;">
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-lines" checked onchange="toggleCapa('geologia-lines', this.checked)"> Contactos Geológicos SGM
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-border" checked onchange="toggleCapa('borde-line', this.checked)"> Límite Acuífero CONAGUA
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-estructuras-w" checked onchange="toggleCapa('estructuras-layer', this.checked)"> ⚡ Fallas y Fracturas 1:50k
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-pozos" checked onchange="toggleVisibilidadPozos(this.checked)"> 📍 Pozos Subterráneos 3D
                </label>
            </div>
        </div>

        <button class="btn-screenshot" onclick="capturarPantalla()">
            📸 Capturar Imagen 3D (PNG)
        </button>
    </div>
</div>

<script>
    const dataGeologia = {geojson_geologia};
    const dataEstructuras = {geojson_estructuras};
    const dataBorde = {geojson_borde};
    const dataCurvas = {geojson_curvas_cota};
    const dataPozos = {pozos_3d_json};

    const bboxAcuifero = [[{minx}, {miny}], [{maxx}, {maxy}]];

    const iconExpandSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
    const iconCompressSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;

    const map = new maplibregl.Map({{
        container: 'map',
        preserveDrawingBuffer: true,
        style: {{
            version: 8,
            sources: {{
                'basemap-source': {{
                    'type': 'raster',
                    'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'],
                    'tileSize': 256,
                    'attribution': '© Esri'
                }},
                'terrainSource': {{
                    'type': 'raster-dem',
                    'encoding': 'terrarium',
                    'tiles': ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{{z}}/{{x}}/{{y}}.png'],
                    'tileSize': 256,
                    'maxzoom': 12
                }}
            }},
            layers: [
                {{
                    'id': 'basemap-layer',
                    'type': 'raster',
                    'source': 'basemap-source',
                    'minzoom': 0,
                    'maxzoom': 19
                }},
                {{
                    'id': 'hillshade-layer',
                    'type': 'hillshade',
                    'source': 'terrainSource',
                    'paint': {{
                        'hillshade-shadow-color': 'rgba(15, 23, 42, 0.45)',
                        'hillshade-highlight-color': 'rgba(255, 255, 255, 0.85)',
                        'hillshade-accent-color': 'rgba(71, 85, 105, 0.3)',
                        'hillshade-illumination-direction': 315,
                        'hillshade-exaggeration': 0.45
                    }}
                }}
            ],
            sky: {{
                'sky-color': '#bae6fd',
                'sky-horizon-blend': 0.5,
                'horizon-color': '#f8fafc'
            }}
        }},
        center: [{centro_lon}, {centro_lat}],
        zoom: 10.5,
        pitch: 52,
        bearing: -12,
        maxPitch: 85
    }});

    let estadoGuardado = localStorage.getItem('dock_3d_abierto');
    let dockAbierto = estadoGuardado !== null ? (estadoGuardado === 'true') : true;

    function aplicarEstadoVisualDock() {{
        const dock = document.getElementById('dock-panel');
        const btnOpen = document.getElementById('btn-open-dock');
        if (dock && btnOpen) {{
            if (dockAbierto) {{
                dock.style.display = 'block';
                btnOpen.style.display = 'none';
            }} else {{
                dock.style.display = 'none';
                btnOpen.style.display = 'flex';
            }}
        }}
    }}

    let marcadoresDOM = [];

    map.on('load', () => {{
        map.setTerrain({{
            'source': 'terrainSource',
            'exaggeration': 1.5
        }});

        aplicarEstadoVisualDock();

        let padLeftInicial = dockAbierto ? 320 : 40;
        map.fitBounds(bboxAcuifero, {{
            padding: {{ top: 60, bottom: 40, left: padLeftInicial, right: 40 }},
            pitch: 52,
            bearing: -12,
            duration: 0
        }});

        // Variable global para que solo exista UN popup abierto en todo el mapa
        let popupActivo = null;
        let clickConsumido = false;

        // -------------------------------------------------------------
        // 1. CAPA DE GEOLOGÍA (POLÍGONOS LITOLÓGICOS SGM)
        // -------------------------------------------------------------
        if (dataGeologia.features && dataGeologia.features.length > 0) {{
            map.addSource('geologia-sgm', {{ 'type': 'geojson', 'data': dataGeologia }});

            map.addLayer({{
                'id': 'geologia-fill',
                'type': 'fill',
                'source': 'geologia-sgm',
                'paint': {{
                    'fill-color': ['get', 'COLOR_HEX'],
                    'fill-opacity': 0.85
                }}
            }});

            map.addLayer({{
                'id': 'geologia-lines',
                'type': 'line',
                'source': 'geologia-sgm',
                'paint': {{
                    'line-color': '#334155',
                    'line-width': 1.2,
                    'line-opacity': 0.75
                }}
            }});

            map.on('mouseenter', 'geologia-fill', () => {{ map.getCanvas().style.cursor = 'pointer'; }});
            map.on('mouseleave', 'geologia-fill', () => {{ map.getCanvas().style.cursor = ''; }});

            map.on('click', 'geologia-fill', (e) => {{
                // 🛑 SI SE TOCÓ UNA FALLA O UN POZO, NO ABRIR LA GEOLOGÍA
                if (clickConsumido) return;
                if (e.originalEvent && e.originalEvent.target && e.originalEvent.target.closest('.maplibregl-marker')) return;

                if (popupActivo) {{
                    popupActivo.remove();
                    popupActivo = null;
                }}

                const p = e.features[0].properties;
                const formacion = (p.FORMACION && String(p.FORMACION).trim() !== '' && String(p.FORMACION).toUpperCase() !== 'NINGUNO' && String(p.FORMACION).toUpperCase() !== 'NULL') ? String(p.FORMACION).trim() : 'Formación No Asignada';
                const claveSgm = p.CLAVE_SGM || p.ETIQUETA_LITO || 'S/C';
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

                const elevTerreno = map.queryTerrainElevation(e.lngLat);
                const elevTxt = elevTerreno !== null ? Math.round(elevTerreno) + ' msnm' : '--';

                popupActivo = new maplibregl.Popup({{ maxWidth: '320px', closeOnClick: true }})
                    .setLngLat(e.lngLat)
                    .setHTML(`
                        <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; line-height:1.5;">
                            <div style="display:flex; align-items:center; justify-content:space-between; border-bottom:1.5px solid #E2E8F0; padding-bottom:4px; margin-bottom:6px;">
                                <div style="display:flex; align-items:center; gap:6px;">
                                    <span style="width:13px; height:13px; background:${{colorHex}}; border-radius:3px; border:1px solid #475569; display:inline-block; flex-shrink:0;"></span>
                                    <h4 style="margin:0; color:#691C32; font-size:13px; font-weight:700;">${{formacion}}</h4>
                                </div>
                                <span style="background:#F1F5F9; border:1px solid #CBD5E1; color:#334155; font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:3px;">${{claveSgm}}</span>
                            </div>
                            <b>Litología:</b> <span style="color:#0f172a; font-weight:600;">${{litologia}}</span><br>
                            <b>Tipo de Roca:</b> ${{roca}}<br>
                            <b>Edad Geológica:</b> ${{edadGeo}}<br>
                            <b>Cota Terreno:</b> <span style="color:#008A3B; font-weight:bold;">${{elevTxt}}</span><br>
                            <span style="color:#64748B; font-size:10px;">Coords: ${{e.lngLat.lat.toFixed(4)}}°, ${{e.lngLat.lng.toFixed(4)}}°</span>
                        </div>
                    `)
                    .addTo(map);
            }});
        }}

        // -------------------------------------------------------------
        // 2. CAPA DE FALLAS Y FRACTURAS 1:50k (LÍNEAS SGM)
        // -------------------------------------------------------------
        if (dataEstructuras.features && dataEstructuras.features.length > 0) {{
            map.addSource('estructuras-sgm-src', {{ 'type': 'geojson', 'data': dataEstructuras }});
            map.addLayer({{
                'id': 'estructuras-layer',
                'type': 'line',
                'source': 'estructuras-sgm-src',
                'paint': {{
                    'line-color': '#dc2626',
                    'line-width': 2.8,
                    'line-dasharray': [3, 2]
                }}
            }});

            map.on('mouseenter', 'estructuras-layer', () => {{ map.getCanvas().style.cursor = 'pointer'; }});
            map.on('mouseleave', 'estructuras-layer', () => {{ map.getCanvas().style.cursor = ''; }});

            map.on('click', 'estructuras-layer', (e) => {{
                // 🛑 SI SE TOCÓ UN POZO QUE PASA CERCA DE LA LÍNEA, NO ABRIR LA FALLA
                if (e.originalEvent && e.originalEvent.target && e.originalEvent.target.closest('.maplibregl-marker')) return;

                clickConsumido = true;
                setTimeout(() => {{ clickConsumido = false; }}, 200);

                if (popupActivo) {{
                    popupActivo.remove();
                    popupActivo = null;
                }}

                const p = e.features[0].properties;

                let azVal = p.AZIMUTH !== undefined && p.AZIMUTH !== null ? p.AZIMUTH : (p.Azimuth || p.azimuth || p.AZIMUT);
                let azTxt = (azVal !== undefined && azVal !== null && String(azVal).trim() !== '' && String(azVal) !== 'null') ? parseFloat(azVal).toFixed(2) + '°' : 'S/D';

                let incVal = p.INCLINACION !== undefined && p.INCLINACION !== null ? p.INCLINACION : (p.Inclinacion || p.inclinacion);
                let incTxt = (incVal !== undefined && incVal !== null && String(incVal).trim() !== '' && String(incVal) !== 'null') ? parseFloat(incVal).toFixed(0) + '°' : '0°';

                let tipoEstr = p.ESTRUCTURAS || p.TIPO_ESTR || 'Estructura Geológica';
                let rawNom = p.NOMBRE || p.NOM_ESTR;
                let tieneNom = rawNom && String(rawNom).trim() !== '' && String(rawNom).toUpperCase() !== 'NULL' && String(rawNom).toUpperCase() !== 'NONE';
                let tituloMostrar = tieneNom ? String(rawNom).trim() : tipoEstr;

                const elevTerreno = map.queryTerrainElevation(e.lngLat);
                const elevTxt = elevTerreno !== null ? Math.round(elevTerreno) + ' msnm' : '--';

                popupActivo = new maplibregl.Popup({{ maxWidth: '320px', closeOnClick: true }})
                    .setLngLat(e.lngLat)
                    .setHTML(`
                        <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; line-height:1.5;">
                            <div style="display:flex; align-items:center; gap:6px; border-bottom:1.5px solid #E2E8F0; padding-bottom:4px; margin-bottom:6px;">
                                <span style="color:#dc2626; font-size:15px;">⚡</span>
                                <h4 style="margin:0; color:#dc2626; font-size:13px; font-weight:700;">${{tituloMostrar}}</h4>
                            </div>
                            <b>Tipo de Estructura:</b> ${{tipoEstr}}<br>
                            <b>Azimut de Rumbo:</b> <span style="color:#0f172a; font-weight:bold;">${{azTxt}}</span><br>
                            <b>Inclinación / Echado:</b> ${{incTxt}}<br>
                            <b>Cota Terreno:</b> <span style="color:#008A3B; font-weight:bold;">${{elevTxt}}</span><br>
                            <span style="color:#64748B; font-size:10px;">Coords: ${{e.lngLat.lat.toFixed(4)}}°, ${{e.lngLat.lng.toFixed(4)}}°</span>
                        </div>
                    `)
                    .addTo(map);
            }});
        }}

        // -------------------------------------------------------------
        // 3. CURVAS DE NIVEL (COTAS)
        // -------------------------------------------------------------
        if (dataCurvas.features && dataCurvas.features.length > 0) {{
            map.addSource('curvas-cota-src', {{ 'type': 'geojson', 'data': dataCurvas }});

            map.addLayer({{
                'id': 'curvas-cota-layer',
                'type': 'line',
                'source': 'curvas-cota-src',
                'filter': ['==', ['%', ['get', 'cota'], 50], 0],
                'paint': {{
                    'line-color': '#475569',
                    'line-width': 1.1,
                    'line-opacity': 0.7,
                    'line-dasharray': [2, 1]
                }}
            }});
        }}

        // -------------------------------------------------------------
        // 4. LÍMITE OFICIAL DEL ACUÍFERO
        // -------------------------------------------------------------
        map.addSource('borde-acuifero', {{ 'type': 'geojson', 'data': dataBorde }});
        map.addLayer({{
            'id': 'borde-line',
            'type': 'line',
            'source': 'borde-acuifero',
            'paint': {{
                'line-color': '#691C32',
                'line-width': 3.5,
                'line-dasharray': [3, 2]
            }}
        }});

        // -------------------------------------------------------------
        // 5. POZOS SUBTERRÁNEOS 3D (MÉTODO NATIVO FUNCIONAL DE MAPLIBRE)
        // -------------------------------------------------------------
        if (dataPozos && dataPozos.length > 0) {{
            dataPozos.forEach(p => {{
                const el = document.createElement('div');
                let tipo = (p.tipo || '').toLowerCase();
                let color = p.color_hex;
                
                if (!color) {{
                    if (tipo.includes('requerid') || tipo.includes('nuevo') || tipo.includes('propuest')) {{
                        color = '#9F2241';
                    }} else {{
                        color = '#008a3b';
                    }}
                }}

                el.style.width = '14px';
                el.style.height = '14px';
                el.style.borderRadius = tipo.includes('tanque') ? '3px' : '50%';
                el.style.backgroundColor = color;
                el.style.border = '2px solid #ffffff';
                el.style.boxShadow = '0 2px 6px rgba(0,0,0,0.5)';
                el.style.cursor = 'pointer';

                const latNum = typeof p.lat === 'number' ? p.lat : parseFloat(p.lat);
                const lonNum = typeof p.lon === 'number' ? p.lon : parseFloat(p.lon);
                const profVal = p.profundidad && p.profundidad > 0 ? p.profundidad : 150;

                // Popup nativo asociado directamente al marcador
                const popupPozo = new maplibregl.Popup({{ offset: 12, maxWidth: '300px' }})
                    .setHTML(`
                        <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; line-height:1.5; min-width:140px;">
                            <div style="display:flex; align-items:center; gap:6px; border-bottom:1.5px solid #E2E8F0; padding-bottom:4px; margin-bottom:6px;">
                                <span style="color:#691C32; font-size:15px;">📍</span>
                                <h4 style="margin:0; color:#691C32; font-size:13px; font-weight:700;">${{p.nombre || 'Pozo'}}</h4>
                            </div>
                            <b>Tipo:</b> ${{p.tipo || 'Infraestructura'}}<br>
                            <b>Profundidad Real:</b> <span style="color:#691C32; font-weight:bold;">${{profVal}} m</span><br>
                            <span style="color:#64748B; font-size:10px;">Coords: ${{latNum.toFixed(4)}}°, ${{lonNum.toFixed(4)}}°</span>
                        </div>
                    `);

                // Al abrir este popup, cerramos cualquier otro de geología o falla que estuviera abierto
                popupPozo.on('open', () => {{
                    if (popupActivo && popupActivo !== popupPozo) {{
                        popupActivo.remove();
                    }}
                    popupActivo = popupPozo;
                }});

                new maplibregl.Marker({{ element: el }})
                    .setLngLat([p.lon, p.lat])
                    .setPopup(popupPozo)
                    .addTo(map);

                marcadoresDOM.push(el);
            }});
        }}
    }});

    map.on('mousemove', (e) => {{
        document.getElementById('hud-lon').innerText = e.lngLat.lng.toFixed(4) + '°';
        document.getElementById('hud-lat').innerText = e.lngLat.lat.toFixed(4) + '°';
        const elevation = map.queryTerrainElevation(e.lngLat);
        document.getElementById('hud-ele').innerText = elevation !== null ? Math.round(elevation) + ' msnm' : '--';
    }});

    function setCamera(mode) {{
        let padLeft = dockAbierto ? 320 : 40;
        if (mode === 'top') map.fitBounds(bboxAcuifero, {{ padding: {{ top: 60, bottom: 40, left: padLeft, right: 40 }}, pitch: 0, bearing: 0, duration: 800 }});
        else if (mode === '3d') map.fitBounds(bboxAcuifero, {{ padding: {{ top: 60, bottom: 40, left: padLeft, right: 40 }}, pitch: 55, bearing: -15, duration: 800 }});
        else if (mode === 'south') map.fitBounds(bboxAcuifero, {{ padding: {{ top: 60, bottom: 40, left: padLeft, right: 40 }}, pitch: 60, bearing: 180, duration: 800 }});
        else if (mode === 'east') map.fitBounds(bboxAcuifero, {{ padding: {{ top: 60, bottom: 40, left: padLeft, right: 40 }}, pitch: 60, bearing: 90, duration: 800 }});
        else if (mode === 'west') map.fitBounds(bboxAcuifero, {{ padding: {{ top: 60, bottom: 40, left: padLeft, right: 40 }}, pitch: 60, bearing: 270, duration: 800 }});
    }}

    function toggleDock() {{
        dockAbierto = !dockAbierto;
        localStorage.setItem('dock_3d_abierto', dockAbierto ? 'true' : 'false');
        aplicarEstadoVisualDock();

        let padLeft = dockAbierto ? 320 : 40;
        map.fitBounds(bboxAcuifero, {{
            padding: {{ top: 60, bottom: 40, left: padLeft, right: 40 }},
            pitch: map.getPitch(),
            bearing: map.getBearing(),
            duration: 500
        }});
    }}

    function toggleVisibilidadPozos(visible) {{
        marcadoresDOM.forEach(el => {{ el.style.display = visible ? 'block' : 'none'; }});
    }}

    function cambiarEquidistanciaCotas(val) {{
        let step = parseInt(val);
        const lbl = document.getElementById('val-cotas');
        if (!map.getLayer('curvas-cota-layer')) return;

        if (step === 0) {{
            lbl.innerText = "Desactivadas";
            lbl.style.color = "#64748B";
            map.setLayoutProperty('curvas-cota-layer', 'visibility', 'none');
        }} else {{
            lbl.innerText = "Cada " + step + " m";
            lbl.style.color = "#691C32";
            map.setLayoutProperty('curvas-cota-layer', 'visibility', 'visible');
            map.setFilter('curvas-cota-layer', ['==', ['%', ['get', 'cota'], step], 0]);
        }}
        map.triggerRepaint();
    }}

    function cambiarRemuestreoTerreno(modo) {{
        if (!map.getLayer('hillshade-layer')) return;
        
        if (modo === 'cubico') {{
            map.setPaintProperty('hillshade-layer', 'hillshade-exaggeration', 0.85);
            map.setPaintProperty('hillshade-layer', 'hillshade-shadow-color', 'rgba(15, 23, 42, 0.7)');
            map.setPaintProperty('hillshade-layer', 'hillshade-accent-color', 'rgba(30, 41, 59, 0.5)');
        }} else if (modo === 'vecino') {{
            map.setPaintProperty('hillshade-layer', 'hillshade-exaggeration', 0.2);
            map.setPaintProperty('hillshade-layer', 'hillshade-shadow-color', 'rgba(15, 23, 42, 0.2)');
            map.setPaintProperty('hillshade-layer', 'hillshade-accent-color', 'rgba(71, 85, 105, 0.1)');
        }} else {{
            map.setPaintProperty('hillshade-layer', 'hillshade-exaggeration', 0.45);
            map.setPaintProperty('hillshade-layer', 'hillshade-shadow-color', 'rgba(15, 23, 42, 0.45)');
            map.setPaintProperty('hillshade-layer', 'hillshade-accent-color', 'rgba(71, 85, 105, 0.3)');
        }}
        map.triggerRepaint();
    }}
            
    let idFuenteTerrenoActual = 'terrainSource';

    function cambiarResolucionDEM(zoomVal) {{
        let z = parseInt(zoomVal);
        let exag = parseFloat(document.getElementById('slider-exag').value) || 1.5;
        let azimut = parseInt(document.getElementById('slider-azimut').value) || 315;
        let shade = parseFloat(document.getElementById('slider-shade').value) || 0.45;
        
        let fuenteVieja = idFuenteTerrenoActual;
        let fuenteNueva = 'terrainSource-z' + z + '-' + Date.now();

        map.addSource(fuenteNueva, {{
            'type': 'raster-dem',
            'encoding': 'terrarium',
            'tiles': ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{{z}}/{{x}}/{{y}}.png'],
            'tileSize': 256,
            'maxzoom': z
        }});

        map.setTerrain({{
            'source': fuenteNueva,
            'exaggeration': exag
        }});
        idFuenteTerrenoActual = fuenteNueva;

        if (map.getLayer('hillshade-layer')) {{
            map.removeLayer('hillshade-layer');
        }}
        map.addLayer({{
            'id': 'hillshade-layer',
            'type': 'hillshade',
            'source': fuenteNueva,
            'paint': {{
                'hillshade-shadow-color': 'rgba(15, 23, 42, 0.45)',
                'hillshade-highlight-color': 'rgba(255, 255, 255, 0.85)',
                'hillshade-accent-color': 'rgba(71, 85, 105, 0.3)',
                'hillshade-illumination-direction': azimut,
                'hillshade-exaggeration': shade
            }}
        }}, map.getLayer('geologia-fill') ? 'geologia-fill' : undefined);

        setTimeout(() => {{
            if (map.getSource(fuenteVieja)) {{
                try {{ map.removeSource(fuenteVieja); }} catch(e) {{}}
            }}
        }}, 600);
        
        map.triggerRepaint();
    }}

    function cambiarExageracion(val) {{
        document.getElementById('val-exag').innerText = parseFloat(val).toFixed(1) + 'x';
        map.setTerrain({{ 'source': idFuenteTerrenoActual, 'exaggeration': parseFloat(val) }});
        map.triggerRepaint();
    }}

    function cambiarAzimutSolar(val) {{
        let deg = parseInt(val);
        let cardinal = deg < 45 ? "Norte" : deg < 135 ? "Este" : deg < 225 ? "Sur" : deg < 315 ? "Oeste" : "Norte";
        document.getElementById('val-azimut').innerText = deg + '° (' + cardinal + ')';
        if (map.getLayer('hillshade-layer')) {{
            map.setPaintProperty('hillshade-layer', 'hillshade-illumination-direction', deg);
        }}
        map.triggerRepaint();
    }}

    function cambiarIntensidadHillshade(val) {{
        document.getElementById('val-shade').innerText = Math.round(val * 100) + '%';
        if (map.getLayer('hillshade-layer')) {{
            map.setPaintProperty('hillshade-layer', 'hillshade-exaggeration', parseFloat(val));
        }}
        map.triggerRepaint();
    }}

    function cambiarOpacidad(val) {{
        document.getElementById('val-opac').innerText = Math.round(val * 100) + '%';
        if (map.getLayer('geologia-fill')) {{
            map.setPaintProperty('geologia-fill', 'fill-opacity', parseFloat(val));
        }}
        map.triggerRepaint();
    }}

    function toggleCapa(id, checked) {{
        if (map.getLayer(id)) {{
            map.setLayoutProperty(id, 'visibility', checked ? 'visible' : 'none');
        }}
        map.triggerRepaint();
    }}

    function capturarPantalla() {{
        const canvas = map.getCanvas();
        const link = document.createElement('a');
        link.download = 'Modelo_Conceptual_3D_{clave_actual}.png';
        link.href = canvas.toDataURL('image/png');
        link.click();
    }}

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
            btn.style.outline = 'none';
            
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

    map.addControl(new maplibregl.NavigationControl({{
        showCompass: true,
        showZoom: true,
        visualizePitch: true
    }}), 'top-right');

    map.addControl(new maplibregl.ScaleControl({{
        maxWidth: 120,
        unit: 'metric'
    }}), 'bottom-left');
</script>
</body>
</html>
"""

# =======================================================
# 🎛️ 11. SELECTOR DUAL DE MODO DE VISUALIZACIÓN
# =======================================================
with st.container(border=True):
    col_m1, col_m2 = st.columns([0.65, 0.35], vertical_alignment="center")
    modo_visualizacion = col_m1.radio(
        "Modo de Visualización Tridimensional:",
        ["🧊 Solo Acuífero (Bloque 3D Aislado)", "🌍 Con Entorno Geográfico (Mapa Mundial)"],
        index=0,
        horizontal=True,
        key="radio_modo_3d"
    )
    if "Aislado" in modo_visualizacion:
        col_m2.info("💡 **Inspección 360° Total:** Clic sobre pozos o geología para ver atributos. Rota en cualquier dirección.")
    else:
        col_m2.info("💡 **Mapa Continuo:** Incluye elevación regional, sombreado solar y coordenadas en vivo.")

# =======================================================
# 🖥️ 12. RENDERIZADO DEL MOTOR SELECCIONADO
# =======================================================
if "Aislado" in modo_visualizacion:
    components.html(html_threejs_isolated, height=760)
else:
    components.html(html_maplibre_world, height=760)

# =======================================================
# 🏷️ 13. LEYENDA CARTOGRÁFICA OFICIAL SGM
# =======================================================
if dic_leyenda_rocas:
    st.markdown(f"""
        <div style='background-color:#F8FAFC; border-left:4px solid #691C32; padding:10px 14px; border-radius:4px; margin-top:10px; margin-bottom:8px;'>
            <span style='font-size:12.5px; font-weight:bold; color:#691C32;'>SIMBOLOGÍA LITOLÓGICA OFICIAL (SGM - INEGI)</span>
            <span style='font-size:11px; color:#64748B; margin-left:14px;'><b>Origen de Reglas:</b> {ORIGEN_SGM_GLOBAL} | <b>Campo:</b> <code>{col_litologica}</code></span>
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

# Inspección de atributos de la litología y estructuras
if gdf_geologia_recortada is not None and not gdf_geologia_recortada.empty:
    with st.expander("🔬 Inspeccionar Tabla de Atributos Vectoriales de la Capa SGM", expanded=False):
        st.dataframe(gdf_geologia_recortada.drop(columns=["geometry"], errors="ignore").head(20), use_container_width=True)

if gdf_estructuras_50k is not None and not gdf_estructuras_50k.empty:
    with st.expander(f"🔬 Inspeccionar Fallas y Estructuras SGM ({len(gdf_estructuras_50k)} registradas)", expanded=False):
        cols_est = [c for c in gdf_estructuras_50k.columns if c != 'geometry']
        st.dataframe(gdf_estructuras_50k[cols_est], use_container_width=True)