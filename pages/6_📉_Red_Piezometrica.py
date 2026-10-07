# -*- coding: utf-8 -*-
"""
Módulo de Evaluación y Monitoreo Geohidrológico (Nivel Enterprise)
Diagnóstico físico con Kriging Ordinario, Variogramas, Isopiezas, Vectores de Flujo y Forecasting.
Desacoplamiento de modelo matemático vs renderizado para interactividad instantánea (<40 ms).
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import unicodedata
import re
import io
import os
import json
import zipfile
import tempfile
import base64
import time
import math
from pathlib import Path
import streamlit.components.v1 as components

try:
    import geopandas as gpd
    from shapely.geometry import LineString, Point, Polygon, MultiPolygon, shape
    GEOPANDAS_INSTALADO = True
except ImportError:
    GEOPANDAS_INSTALADO = False

# Importaciones del Core
from utils.styles import inyectar_css_oficial, banner_institucional
from core.data_loader import CARPETA_DATOS, cargar_catalogo, cargar_datos_maestros, DIRECTORIO_RAIZ

# =======================================================
# 🎨 1. CONFIGURACIÓN E INYECCIÓN DE ESTILOS
# =======================================================
st.set_page_config(layout="wide", page_title="Red Piezométrica", page_icon="📉")
inyectar_css_oficial()
banner_institucional()

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
# 🛰️ 2.15 MOTOR DE AUTODETECCIÓN ESPACIAL DE ACUÍFEROS
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
# 📍 2.2 CONTROL Y CARGA DE PUNTOS ADICIONALES (MANUAL Y CSV)
# =======================================================
if "marcadores_piezo" not in st.session_state:
    st.session_state["marcadores_piezo"] = []
if "csv_uploader_key_piezo" not in st.session_state:
    st.session_state["csv_uploader_key_piezo"] = 0

def limpiar_puntos_piezo():
    st.session_state["marcadores_piezo"] = []
    st.session_state["csv_uploader_key_piezo"] += 1

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
                    
                    # ⚡ AUTODETECCIÓN ESPACIAL
                    acuifero_detectado = auto_identificar_acuifero_por_coordenadas(lat, lon_final, gdf_m)
                    if acuifero_detectado:
                        st.session_state["clave_piezo"] = acuifero_detectado["clave"]
                        st.session_state["nombre_piezo"] = acuifero_detectado["nombre"]
                        st.session_state["area_total_piezo"] = acuifero_detectado["area"]
                        st.session_state["piezo_sel_edo"] = acuifero_detectado["estado"]
                        st.success(f"📍 Acuífero autodetectado: **{acuifero_detectado['clave']} - {acuifero_detectado['nombre']}**")
                        time.sleep(1)
                        
                    st.rerun()
        
        if st.button("🧹 Limpiar Todos los Puntos", use_container_width=True, key="btn_limpiar_manual_piezo"):
            limpiar_puntos_piezo()
            st.rerun()
        
    with tab_c:
        st.markdown("""<div style="background-color: #f8f9fa; border: 1px dashed #ced4da; border-radius: 4px; padding: 6px 10px; font-size: 10px; color: #495057; margin-bottom: 8px;">Sube tu archivo y mapea las columnas. El mapa no se actualizará hasta que des clic en "Cargar Puntos CSV".</div>""", unsafe_allow_html=True)
        
        up_key = f"csv_up_piezo_{st.session_state['csv_uploader_key_piezo']}"
        archivo_csv = st.file_uploader("Subir CSV", type=['csv'], key=up_key, label_visibility="collapsed")
        
        c_csv1, c_csv2 = st.columns(2)
        if c_csv2.button("🧹 Limpiar", use_container_width=True, type="secondary", key="btn_limpiar_csv_piezo"):
            limpiar_puntos_piezo()
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
                                    
                                    # ⚡ AUTODETECCIÓN ESPACIAL
                                    if not acuifero_detectado:
                                        acuifero_detectado = auto_identificar_acuifero_por_coordenadas(lat_v, lon_final, gdf_m)
                                        
                            except: pass
                            
                        if nuevos:
                            st.session_state["marcadores_piezo"].extend(nuevos)
                            
                            if acuifero_detectado:
                                st.session_state["clave_piezo"] = acuifero_detectado["clave"]
                                st.session_state["nombre_piezo"] = acuifero_detectado["nombre"]
                                st.session_state["area_total_piezo"] = acuifero_detectado["area"]
                                st.session_state["piezo_sel_edo"] = acuifero_detectado["estado"]
                                st.success(f"📍 Acuífero autodetectado: **{acuifero_detectado['clave']} - {acuifero_detectado['nombre']}**")
                            else:
                                st.success(f"✅ {len(nuevos)} puntos cargados correctamente.")
                                
                            time.sleep(1)
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
st.sidebar.markdown("""
    <style>
        section[data-testid="stSidebar"] button[kind="secondary"],
        section[data-testid="stSidebar"] button[data-baseweb="button"]:not([kind="primary"]),
        section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button {
            background-color: #e9ecef !important; border: 1px solid #ced4da !important;
            border-radius: 6px !important; color: #333333 !important; font-weight: 600 !important;
            width: 100% !important; min-height: 38px !important; transition: all 0.2s ease !important;
            margin-top: 4px !important;
        }
        section[data-testid="stSidebar"] button[kind="secondary"]:hover {
            background-color: #dde2e6 !important; border-color: #adb5bd !important; color: #000000 !important;
        }
        section[data-testid="stSidebar"] button[kind="primary"] {
            border-radius: 6px !important; min-height: 38px !important; font-weight: 600 !important; margin-top: 4px !important;
        }
    </style>
""", unsafe_allow_html=True)

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
            st.download_button(label="⬇️ Descargar Puntos (CSV)", data=csv_data, file_name="puntos_piezometria.csv", mime="text/csv", use_container_width=True)

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
                    
                    # Limpiar puntos al cambiar de acuífero
                    st.session_state["marcadores_piezo"] = []
                    st.session_state["csv_uploader_key_piezo"] = st.session_state.get("csv_uploader_key_piezo", 0) + 1
                    
                    st.rerun()
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
    if not archivos_candidatos: return None, None, None
        
    archivos_candidatos.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    ruta_csv = archivos_candidatos[0] 
    
    try: df = pd.read_csv(ruta_csv, sep=None, engine='python', encoding='utf-8-sig')
    except: df = pd.read_csv(ruta_csv, sep=None, engine='python', encoding='latin1')
        
    df.columns = df.columns.str.strip()
    cols_upper = [str(c).upper() for c in df.columns]
    
    # Buscar la columna de la Clave del Acuífero
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
        if match: renombre_anios[col] = match.group(1)
            
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
    if _geom_acuifero is None: return None, "Ninguna", {}
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_geologia"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_cache_parquet = carpeta_cache / f"GEO_SHP_{clave_ac}.parquet"

    gdf_sgm = None
    if ruta_cache_parquet.exists() and ruta_cache_parquet.stat().st_size > 2000:
        try:
            gdf_cached = gpd.read_parquet(ruta_cache_parquet)
            if len(gdf_cached.columns) > 3: gdf_sgm = gdf_cached
            else: ruta_cache_parquet.unlink()
        except Exception: pass

    if gdf_sgm is None or gdf_sgm.empty:
        rutas_busqueda = [DIRECTORIO_RAIZ / "data" / "geologia"]
        for r_dir in rutas_busqueda:
            if not r_dir.exists(): continue
            for pq_p in r_dir.glob("*.parquet"):
                if any(k in pq_p.name.lower() for k in ["lito", "geo", "cnal"]) and "estructura" not in pq_p.name.lower():
                    try:
                        gdf_temp = gpd.read_parquet(pq_p)
                        if gdf_temp.crs is None: gdf_temp = gdf_temp.set_crs(epsg=4326)
                        else: gdf_temp = gdf_temp.to_crs(epsg=4326)
                        recorte = gdf_temp.clip(_geom_acuifero)
                        if not recorte.empty:
                            gdf_sgm = recorte
                            break
                    except Exception: pass
            if gdf_sgm is not None: break

    if gdf_sgm is not None and not gdf_sgm.empty:
        def reparar_texto_mojibake(val):
            if val is None or pd.isna(val): return ""
            s = str(val).strip()
            try: s = s.encode('latin1').decode('utf-8')
            except: pass
            return s

        for col in gdf_sgm.select_dtypes(include=['object', 'string']).columns:
            if col != 'geometry': gdf_sgm[col] = gdf_sgm[col].apply(reparar_texto_mojibake)

        cols_upper = [c.upper() for c in gdf_sgm.columns]
        if "CLAVE_SGM" in cols_upper: col_sel = gdf_sgm.columns[cols_upper.index("CLAVE_SGM")]
        elif "CLAVE" in cols_upper: col_sel = gdf_sgm.columns[cols_upper.index("CLAVE")]
        elif "LITOLOGIA" in cols_upper: col_sel = gdf_sgm.columns[cols_upper.index("LITOLOGIA")]
        else: col_sel = gdf_sgm.columns[0]

        def resolver_color(c, l, r):
            texto_eval = f"{c} {l} {r}".upper()
            if any(k in texto_eval for k in ["ALUV", "ALUVION", "SUELO"]): return "#FFF5AF"
            if any(k in texto_eval for k in ["BASALT", "BASÁLT"]): return "#800080"
            if any(k in texto_eval for k in ["ANDESIT", "ANDESÍT"]): return "#B43264"
            if any(k in texto_eval for k in ["RIOLIT", "RIOLÍT"]): return "#ED5F7D"
            if any(k in texto_eval for k in ["CALIZ", "CALÍZ"]): return "#2887CD"
            if any(k in texto_eval for k in ["LUTIT", "LUTÍT"]): return "#9BB95A"
            if any(k in texto_eval for k in ["ARENISC", "ARENA"]): return "#BED273"
            if any(k in texto_eval for k in ["GRANIT", "GRANOD"]): return "#EB3732"
            if "AGUA" in texto_eval: return "#A6CAE8"
            return "#B0BEC5"

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

        try: gdf_sgm.to_parquet(ruta_cache_parquet)
        except Exception: pass
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
        
    x = df_puntos['Longitud'].values
    y = df_puntos['Latitud'].values
    z = df_puntos[variable].values
    
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
    
    grid_x = np.linspace(min_x, max_x, resolucion)
    grid_y = np.linspace(min_y, max_y, resolucion)
    X, Y = np.meshgrid(grid_x, grid_y)
    
    props_kriging = {}
    try:
        v_model = 'linear'
        v_kwargs = {}
        if 'Lineal' in modelo_param: v_model = 'linear'
        elif 'Esférico' in modelo_param: v_model = 'spherical'
        elif 'Exponencial' in modelo_param: v_model = 'exponential'
        elif 'Gaussiano' in modelo_param: v_model = 'gaussian'
        elif 'Square root' in modelo_param: 
            v_model = 'power'
            v_kwargs['variogram_parameters'] = {'degree': 0.5}
        elif 'Stable' in modelo_param: 
            v_model = 'power'
            v_kwargs['variogram_parameters'] = {'degree': 1.5}
        elif 'Logarítmico' in modelo_param:
            v_model = 'custom'
            v_kwargs['variogram_function'] = lambda p, d: p[0] * np.log1p(d) + p[1]
            v_kwargs['variogram_parameters'] = [np.var(z), 0.0]
        elif 'Cúbico' in modelo_param:
            v_model = 'custom'
            v_kwargs['variogram_function'] = lambda p, d: p[0] * (d**3) + p[1]
            v_kwargs['variogram_parameters'] = [0.0, np.var(z)]

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
        fit_range = ok.variogram_model_parameters[1] if v_model not in ['linear', 'power', 'custom'] else "N/A"
        
        props_kriging = {
            "Determination (R²)": f"{r_squared:.4f}",
            "Fitting Range": f"{fit_range:.2f}" if isinstance(fit_range, float) else "N/A",
            "Samples": str(len(x)),
            "Lag Distance": f"{np.mean(np.diff(exp_lags)):.4f}",
            "Max Distance": f"{np.max(exp_lags):.4f}"
        }
    except Exception as e:
        return None, f"Error ajustando variograma {modelo_param}: {e}.", None, None, None, None, None, None, None, None, None

    bounds = [[min_y, min_x], [max_y, max_x]]
    return X, Y, Z, grid_x, grid_y, bounds, props_kriging, exp_lags, exp_semi, smooth_lags, theo_semi_smooth

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
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.io import MemoryFile
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
# 🎨 7. RENDERIZADO VISUAL REACTIVO (<30 ms)
# =======================================================
# ⚡ OPTIMIZACIÓN: Sin decoradores @st.cache_data para evitar UnhashableParamError
def render_imagen_kriging(X, Y, Z_masked, bounds):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    fig = plt.figure(figsize=(10, 10), frameon=False)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    ax.set_xlim(bounds[0][1], bounds[1][1])
    ax.set_ylim(bounds[0][0], bounds[1][0])
    
    contourf = ax.contourf(X, Y, Z_masked, levels=40, cmap='Blues')
    
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

def render_imagen_vectores(X, Y, Z, grid_x, grid_y, bounds, variable, densidad_flujo, inside_mask):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    dy, dx = np.gradient(Z, grid_y, grid_x)
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
            "GRADIENTE": round(float(mg), 5), "AZIMUT_DEG": round(float(az), 1),
            "VX": round(float(vx), 5), "VY": round(float(vy), 5)
        }
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

    if area_actual > 0:
        densidad = area_actual / pozos_activos if pozos_activos > 0 else 0
        col_i3.metric("Densidad Espacial", f"1 pozo / {densidad:.1f} km²")
    else:
        col_i3.metric("Densidad Espacial", "N/D")

    col_i4.metric("Sin Datos Recientes", total_pozos - pozos_activos, "Pozos Desatendidos", delta_color="inverse")

st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

# =======================================================
# 🛠️ 9. INTERFAZ DE TABS
# =======================================================
tab_mapa, tab_hidrograma, tab_alertas = st.tabs([
    "🗺️ Dinámica de Flujo y Variogramas", 
    "📈 Hidrogramas Inteligentes", 
    "🚨 Forecasting y Alertas"
])

# --- EJE 3: DINÁMICA ESPACIAL AVANZADA ---
with tab_mapa:
    @st.fragment
    def renderizar_pestaña_mapa():
        
        # 1. PESTAÑA DESPLEGABLE PARA HERRAMIENTAS MATEMÁTICAS (PYTHON)
        with st.expander("⚙️ Herramientas y Configuración del Modelo Geostadístico", expanded=False):
            st.markdown("<p style='font-size:13px; color:#64748B; margin-bottom:10px;'>Ajusta los parámetros matemáticos. El modelo espacial se recalculará automáticamente.</p>", unsafe_allow_html=True)
            
            c_p1, c_p2, c_p3 = st.columns(3)
            
            with c_p1:
                var_interp = st.selectbox("1. Variable a Modelar", ["Carga Hidráulica (msnm) [Recomendado para flujo]", "Profundidad del Nivel (m)"])
                var_real = 'Carga_Hidraulica' if "Carga" in var_interp else 'Profundidad_NE'
                
                param = st.selectbox("2. Modelo de Variograma", [
                    "Lineal (no nugget)", "Raíz Cuadrada (square root)", "Logarítmico", 
                    "Stable (0 < k < 2)", "Cúbico", "Esférico (spherical)", "Exponencial (exponential)", "Gaussiano (gaussian)"
                ])
                
            df_ultimo = df_ac.loc[df_ac.groupby('Pozo')['Año'].idxmax()].dropna(subset=[var_real, 'Latitud', 'Longitud']).copy()
            
            with c_p2:
                geom_activa = poligono_oficial_geom
                opciones_delimitacion = ["Pozos de Monitoreo (Envolvente Convexa)"]
                if geom_activa is not None:
                    opciones_delimitacion.insert(0, "Polígono Oficial del Acuífero")

                modo_delimitacion = st.radio(
                    "3. Delimitar modelo por:", 
                    opciones_delimitacion, 
                    index=0
                )
                
                up_geom = st.file_uploader("Cargar Polígono Alternativo (.geojson/.zip):", type=['geojson', 'json', 'zip'], key="up_poly_piezo")
                if up_geom is not None:
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
                        geom_activa = gdf_up.unary_union
                        st.success("✅ Polígono personalizado cargado.")
                    except Exception as err:
                        st.error(f"Error procesando archivo: {err}")
                        
            if len(df_ultimo) >= 4:
                rango_estimado = max(1.0, float(df_ultimo[var_real].max() - df_ultimo[var_real].min()))
                def_equidistancia = max(0.5, round(rango_estimado / 10.0, 1))
                if def_equidistancia >= 5: def_equidistancia = round(def_equidistancia / 5.0) * 5.0
            else:
                rango_estimado = 50.0
                def_equidistancia = 5.0
                
            with c_p3:
                intervalo_iso = st.slider(
                    "Equidistancia de Isolíneas (m):", 
                    min_value=max(0.5, round(rango_estimado / 40.0, 1)), 
                    max_value=max(2.0, round(rango_estimado / 2.0, 1)), 
                    value=float(min(max(2.0, round(rango_estimado / 2.0, 1)), def_equidistancia)), 
                    step=0.5 if rango_estimado < 20 else 1.0
                )
                densidad_flujo = st.slider("Densidad de Vectores de Flujo:", 8, 36, 20, 2)

        # 2. PESTAÑA DESPLEGABLE PARA EL SEMIVARIOGRAMA
        with st.expander("📈 Análisis Geostadístico (Semivariograma Experimental vs Teórico)", expanded=False):
            ph_variograma = st.empty()

        # 3. RENDERIZADO DEL MAPA (A PANTALLA COMPLETA)
        if len(df_ultimo) >= 4:
            with st.spinner("Modelando superficie geostadística y delimitando fronteras..."):
                # Tupla hasheable (min_x, min_y, max_x, max_y)
                geom_para_kriging = geom_activa if modo_delimitacion == "Polígono Oficial del Acuífero" else None
                bounds_limite_hashable = geom_para_kriging.bounds if geom_para_kriging is not None else None
                
                resultado_kriging = resolver_malla_kriging(
                    df_ultimo, var_real, param, bounds_limite=bounds_limite_hashable
                )
                
                if resultado_kriging[0] is None:
                    st.error(resultado_kriging[1])
                else:
                    X, Y, Z, grid_x, grid_y, bounds, props_kriging, exp_lags, exp_semi, smooth_lags, theo_semi = resultado_kriging
                    
                    # 🎯 DELIMITACIÓN MATEMÁTICA
                    pts_grid = np.column_stack((X.ravel(), Y.ravel()))
                    hull_pts = None
                    inside_mask = None
                    
                    if modo_delimitacion == "Polígono Oficial del Acuífero" and geom_activa is not None:
                        try:
                            from scipy.spatial import ConvexHull
                            from matplotlib.path import Path
                            if geom_activa.geom_type == 'Polygon':
                                path_poly = Path(np.array(geom_activa.exterior.coords))
                                inside_mask = path_poly.contains_points(pts_grid).reshape(X.shape)
                            elif geom_activa.geom_type == 'MultiPolygon':
                                mask_accum = np.zeros(len(pts_grid), dtype=bool)
                                for poly_sub in geom_activa.geoms:
                                    p_sub = Path(np.array(poly_sub.exterior.coords))
                                    mask_accum |= p_sub.contains_points(pts_grid)
                                inside_mask = mask_accum.reshape(X.shape)
                        except Exception:
                            inside_mask = None

                    if inside_mask is None:
                        from scipy.spatial import ConvexHull
                        from matplotlib.path import Path
                        x_pozos = df_ultimo['Longitud'].values
                        y_pozos = df_ultimo['Latitud'].values
                        try:
                            hull = ConvexHull(np.column_stack((x_pozos, y_pozos)))
                            hull_pts = np.column_stack((x_pozos[hull.vertices], y_pozos[hull.vertices]))
                            hull_path = Path(hull_pts)
                            inside_mask = hull_path.contains_points(pts_grid).reshape(X.shape)
                        except Exception:
                            inside_mask = np.ones(X.shape, dtype=bool)

                    Z_masked = np.where(inside_mask, Z, np.nan)

                    # ⚡ Renderizado Desacoplado
                    img_kriging, vmin, vmax = render_imagen_kriging(X, Y, Z_masked, bounds)
                    img_isolineas, geojson_iso, shp_iso_zip = render_imagen_isolineas(X, Y, Z_masked, bounds, intervalo_iso, var_real)
                    img_flujo, geojson_flujo, shp_flujo_zip = render_imagen_vectores(X, Y, Z, grid_x, grid_y, bounds, var_real, densidad_flujo, inside_mask)

                    # Preparación de datos de Kriging para exportación y para JS
                    geotiff_bytes = generar_geotiff_bytes(Z_masked, bounds)
                    mask_val = ~np.isnan(Z_masked)
                    df_grid = pd.DataFrame({"LONGITUD": np.round(X[mask_val], 6), "LATITUD": np.round(Y[mask_val], 6), "VALOR": np.round(Z_masked[mask_val], 3)})
                    geojson_krig = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["LONGITUD"], r["LATITUD"]]}, "properties": {"VALOR": r["VALOR"], "VARIABLE": var_real}} for _, r in df_grid.iterrows()]}, indent=2).encode('utf-8')
                    shp_krig_zip = empaquetar_shapefile_zip(gpd.GeoDataFrame(df_grid, geometry=[Point(xy) for xy in zip(df_grid["LONGITUD"], df_grid["LATITUD"])], crs="EPSG:4326"), f"kriging_{clave_actual}") if (GEOPANDAS_INSTALADO and not df_grid.empty) else None

                    # Convertir Z_masked a JSON para el click en el mapa
                    z_list = []
                    for row in Z_masked:
                        z_list.append([None if math.isnan(v) else round(float(v), 2) for v in row])
                    z_data_json = json.dumps(z_list)
                    bounds_json = json.dumps(bounds)

                    # Semivariograma
                    with ph_variograma.container():
                        fig_var = go.Figure()
                        fig_var.add_trace(go.Scatter(x=exp_lags, y=exp_semi, mode='markers', name='Experimental (Campo)', marker=dict(color='#9f2241', size=7)))
                        fig_var.add_trace(go.Scatter(x=smooth_lags, y=theo_semi, mode='lines', name='Ajuste Teórico', line=dict(color='#285c4d', width=2)))
                        fig_var.update_layout(
                            xaxis_title="Lag (Distancia)", yaxis_title="Semivarianza",
                            height=250, margin=dict(t=10, b=10, l=10, r=10), plot_bgcolor='rgba(0,0,0,0)',
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10))
                        )
                        fig_var.update_xaxes(showgrid=True, gridcolor='rgba(200,200,200,0.2)')
                        fig_var.update_yaxes(showgrid=True, gridcolor='rgba(200,200,200,0.2)')
                        st.plotly_chart(fig_var, use_container_width=True)

                        tabla_props = f"""
                        <table style="width:100%; font-size:11.5px; border-collapse: collapse; font-family: 'Segoe UI', sans-serif;">
                            <tr style="border-bottom: 1px solid #E2E8F0;"><td style="color:#64748B; padding:3px 0;">Determinación (R²):</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Determination (R²)']}</td></tr>
                            <tr style="border-bottom: 1px solid #E2E8F0;"><td style="color:#64748B; padding:3px 0;">Fitting Range:</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Fitting Range']}</td></tr>
                            <tr style="border-bottom: 1px solid #E2E8F0;"><td style="color:#64748B; padding:3px 0;">Muestras Activas:</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Samples']} pozos</td></tr>
                            <tr style="border-bottom: 1px solid #E2E8F0;"><td style="color:#64748B; padding:3px 0;">Lag Distance:</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Lag Distance']}</td></tr>
                            <tr><td style="color:#64748B; padding:3px 0;">Distancia Máxima:</td><td style="font-weight:700; color:#1E293B; text-align:right;">{props_kriging['Max Distance']}</td></tr>
                        </table>
                        """
                        st.markdown(tabla_props, unsafe_allow_html=True)
                    
                    # =======================================================
                    # 🗺️ RENDERIZADO MAPLIBRE GL JS (WEBGL)
                    # =======================================================
                    import streamlit.components.v1 as components
                    
                    centro_lat, centro_lon = df_ultimo['Latitud'].mean(), df_ultimo['Longitud'].mean()
                    
                    # 1. Preparar GeoJSON de Pozos Oficiales
                    features_pozos = []
                    for _, row in df_ultimo.iterrows():
                        df_hist = df_ac[df_ac['Pozo'].astype(str) == str(row['Pozo'])]
                        if len(df_hist) >= 2:
                            z_trend = np.polyfit(df_hist['Año'], df_hist['Profundidad_NE'], 1)[0]
                            color_punto = "#9f2241" if z_trend > 0.1 else ("#285c4d" if z_trend < -0.1 else "#b38e5d")
                        else:
                            color_punto = "#9e9d9e"
                        features_pozos.append({
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [row['Longitud'], row['Latitud']]},
                            "properties": {
                                "Pozo": row['Pozo'],
                                "Valor": round(row[var_real], 2),
                                "Año": row['Año'],
                                "Color": color_punto,
                                "Variable": var_real
                            }
                        })
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
                    img_coords_json = json.dumps([
                        [min_x, max_y], [max_x, max_y], [max_x, min_y], [min_x, min_y]
                    ])

                    if vmin == vmax:
                        vmax = vmin + 1.0

                    vmid = (vmin + vmax) / 2.0
                    var_titulo_limpio = "Carga Hidráulica (msnm)" if "Carga" in var_interp else "Profundidad del Nivel (m)"
                    
                    poly_bounds_str = json.dumps(list(geom_activa.bounds)) if geom_activa is not None else "null"
                    
                    img_krig_b64 = base64.b64encode(img_kriging).decode('utf-8')
                    img_iso_b64 = base64.b64encode(img_isolineas).decode('utf-8')
                    img_flujo_b64 = base64.b64encode(img_flujo).decode('utf-8')
                    
                    # 5. Construcción dinámica de la leyenda
                    hay_manual = any(pt.get("fuente") == "manual" for pt in st.session_state.get("marcadores_piezo", []))
                    hay_csv = any(pt.get("fuente") == "csv" for pt in st.session_state.get("marcadores_piezo", []))
                    
                    leyenda_html = f"""
                    <b style="color:#691C32; font-size: 12px;">Simbología</b><br>
                    <div id="leg-pozos" style="margin-top:4px;">
                        <i style="background:#9f2241;"></i> Pozo Abatiéndose<br>
                        <i style="background:#285c4d;"></i> Pozo Recuperando<br>
                        <i style="background:#b38e5d;"></i> Pozo Estable<br>
                    </div>
                    """
                    
                    leyenda_html += f'<div id="leg-manual" style="display: {"block" if hay_manual else "none"}; margin-top:4px; border-top: 1px solid #eee; padding-top:4px;">'
                    leyenda_html += '<i style="background:#d35400;"></i> Puntos Manuales<br></div>'
                        
                    leyenda_html += f'<div id="leg-csv" style="display: {"block" if hay_csv else "none"}; margin-top:4px;">'
                    leyenda_html += '<i class="circle" style="background:#2980b9;"></i> Puntos CSV<br></div>'
                        
                    if dic_leyenda_rocas:
                        leyenda_html += f'<div id="leg-geo" style="display: {"block" if False else "none"}; margin-top:4px; border-top: 1px solid #eee; padding-top:4px;">'
                        leyenda_html += f'<b style="color:#691C32; font-size:11px;">Geología SGM ({col_sel_geo})</b><div style="max-height: 150px; overflow-y: auto; margin-top:4px;">'
                        for roca, color in dic_leyenda_rocas.items():
                            leyenda_html += f'<i class="square" style="background:{color};"></i> <span style="font-size:9.5px;">{roca}</span><br>'
                        leyenda_html += '</div></div>'

                    # 6. HTML de MapLibre
                    html_maplibre = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8" />
                        <title>Red Piezométrica MapLibre</title>
                        <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
                        <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
                        <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
                        
                        <!-- Librerías Vectoriales para Dibujo y Cálculo Geodésico -->
                        <link rel="stylesheet" href="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.css" type="text/css" />
                        <script src="https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.4.3/mapbox-gl-draw.js"></script>
                        <script src="https://cdn.jsdelivr.net/npm/@turf/turf@6.5.0/turf.min.js"></script>

                        <style>
                            body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; overflow: hidden; }}
                            #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; background: #e2e8f0; }}
                            
                            /* ========================================================= */
                            /* ✨ ESTILOS PARA POPUPS TRANSPARENTES (TOOLTIP)            */
                            /* ========================================================= */
                            .maplibregl-popup-content {{
                                background: none !important;
                                box-shadow: none !important;
                                border: none !important;
                                padding: 0 !important;
                            }}
                            .maplibregl-popup-tip {{ display: none !important; }}
                            .maplibregl-popup-close-button {{ display: none !important; }}
                            
                            .custom-transparent-popup {{
                                font-family: 'Segoe UI', sans-serif;
                                font-size: 12.5px;
                                color: #1E293B;
                                text-shadow: 1px 1px 0 #fff, -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 0px 2px 4px rgba(0,0,0,0.5);
                                font-weight: 600;
                                pointer-events: none;
                                line-height: 1.4;
                            }}
                            .custom-transparent-popup h4 {{
                                margin: 0 0 2px 0;
                                color: #691C32;
                                font-size: 14px;
                                font-weight: 800;
                                text-shadow: 1px 1px 0 #fff, -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 0px 2px 4px rgba(0,0,0,0.5);
                            }}

                            /* HUD Coordenadas */
                            .hud-elevation {{
                                position: absolute; top: 12px; right: 55px; z-index: 1000;
                                background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
                                color: #1e293b; padding: 7px 14px; border-radius: 8px;
                                border: 1.5px solid #691C32;
                                box-shadow: 0 4px 15px rgba(0,0,0,0.15); font-size: 11.5px;
                                display: flex; gap: 14px; align-items: center; pointer-events: none;
                            }}
                            .hud-elevation b {{ color: #691C32; margin-right: 4px; }}
                            
                            /* Botón Hamburguesa */
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
                            
                            /* Dock / Panel Lateral */
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
                            .dock-section label {{ display: flex; align-items: center; gap: 6px; cursor: pointer; margin-bottom: 6px; font-weight: 500;}}
                            .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; margin-top: 4px; }}
                            
                            /* Leyendas */
                            .legend-panel {{
                                position: absolute; bottom: 25px; left: 12px; z-index: 1000;
                                background: rgba(255,255,255,0.95); padding: 10px 14px; border-radius: 8px;
                                box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-size: 11px; line-height: 1.6;
                                border: 1px solid #E2E8F0;
                            }}
                            .legend-panel i {{ width: 12px; height: 12px; display: inline-block; border-radius: 50%; margin-right: 6px; vertical-align: middle; border: 1px solid #ccc; box-shadow: 0 1px 3px rgba(0,0,0,0.3);}}
                            .legend-panel .square {{ border-radius: 2px; }}
                            
                            /* Botón Gradiente */
                            .leaflet-open-gradient-btn {{
                                position: absolute; top: 160px; right: 10px; z-index: 1000;
                                background: #691C32 !important; color: #ffffff; width: 29px; height: 29px;
                                border-radius: 4px; border: 2px solid rgba(0,0,0,0.2);
                                box-shadow: none;
                                cursor: pointer;
                                display: flex; align-items: center; justify-content: center;
                                transition: background 0.2s ease;
                            }}
                            .leaflet-open-gradient-btn:hover {{ background: #88102B !important; }}

                            /* Panel Gradiente Desplegable */
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

                            /* ========================================================= */
                            /* 📐 PANEL Y BOTÓN PROFESIONAL DE DIBUJO Y MEDICIÓN         */
                            /* ========================================================= */
                            .leaflet-open-draw-btn {{
                                position: absolute; top: 196px; right: 10px; z-index: 1000;
                                background: #ffffff; color: #691C32; width: 29px; height: 29px;
                                border-radius: 4px; border: 2px solid rgba(0,0,0,0.2);
                                box-shadow: none; cursor: pointer;
                                display: flex; align-items: center; justify-content: center;
                                transition: background 0.2s ease;
                            }}
                            .leaflet-open-draw-btn:hover {{ background: #f4f4f4; }}

                            .draw-docked-panel {{
                                position: absolute; top: 196px; right: 50px; z-index: 2000;
                                background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
                                width: 260px; border-radius: 8px; overflow: hidden;
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

                            .draw-grid {{
                                display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 8px;
                            }}
                            .btn-tool {{
                                background: #ffffff; border: 1px solid #CBD5E1; border-radius: 5px;
                                padding: 6px 8px; font-size: 11px; font-weight: 600; color: #334155;
                                display: flex; align-items: center; gap: 6px; cursor: pointer;
                                transition: all 0.15s ease;
                            }}
                            .btn-tool svg {{ width: 14px; height: 14px; stroke: #691C32; fill: none; stroke-width: 2; flex-shrink: 0; }}
                            .btn-tool:hover {{ background: #f1f5f9; border-color: #691C32; color: #691C32; }}
                            .btn-tool.active {{ background: #691C32; border-color: #691C32; color: #ffffff; }}
                            .btn-tool.active svg {{ stroke: #ffffff; }}

                            .draw-measure-box {{
                                background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 5px;
                                padding: 8px 10px; font-size: 11px; line-height: 1.45; color: #14532D;
                                margin-bottom: 8px; display: none;
                            }}
                            .draw-measure-box b {{ color: #166534; }}

                            .draw-actions {{
                                display: flex; gap: 6px; border-top: 1px solid #f1f5f9; padding-top: 8px;
                            }}
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
                        </style>
                    </head>
                    <body>
                        <!-- Definiciones de Iconos SVG para Herramientas de Dibujo -->
                        <svg style="display:none;">
                            <symbol id="icon-poly" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 2l8 6-3 10H7l-3-10z"/>
                            </symbol>
                            <symbol id="icon-line" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="4 20 12 12 20 4"/>
                            </symbol>
                            <symbol id="icon-point" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="12" cy="12" r="3"/>
                                <path d="M12 2v2m0 16v2m10-10h-2M4 12H2"/>
                            </symbol>
                            <symbol id="icon-trash" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M3 6h18 M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                            </symbol>
                            <symbol id="icon-clear" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 4H8l-7 8 7 8h13a2 2 0 002-2V6a2 2 0 00-2-2z M18 9l-6 6 M12 9l6 6"/>
                            </symbol>
                        </svg>

                        <div id="map"></div>
                        
                        <!-- HUD COORDENADAS -->
                        <div class="hud-elevation">
                            <div><b>LON:</b> <span id="hud-lon">--</span></div>
                            <div><b>LAT:</b> <span id="hud-lat">--</span></div>
                            <div style="color:#008a3b;"><b>VALOR:</b> <span id="hud-ele">--</span></div>
                        </div>

                        <!-- BOTÓN HAMBURGUESA -->
                        <div id="btn-open-dock" class="btn-open-dock-circle" onclick="toggleDock()" title="Abrir Herramientas Visuales">
                            ☰
                        </div>
                        
                        <!-- DOCK PANEL -->
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
                                        <option value="base-google-layer">Google Satelital</option>
                                    </select>
                                </div>
                                <hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;">
                                <div class="dock-section">
                                    <label style="font-weight:700; color:#691C32; margin-bottom:2px;">🎨 Transparencia Kriging: <span id="val-opac">65%</span></label>
                                    <input type="range" class="slider-ctrl" id="slider-opac" min="0" max="1" step="0.05" value="0.65" oninput="cambiarOpacidadKriging(this.value)">
                                </div>
                                <div class="dock-section" id="sec-opac-geo" style="display: {'block' if dic_leyenda_rocas else 'none'};">
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
                                    <label style="display: {'flex' if hay_manual else 'none'};"><input type="checkbox" id="chk-manual" checked> 🟠 Puntos Manuales</label>
                                    <label style="display: {'flex' if hay_csv else 'none'};"><input type="checkbox" id="chk-csv" checked> 🔵 Puntos CSV</label>
                                    <label style="display: {'flex' if dic_leyenda_rocas else 'none'};"><input type="checkbox" id="chk-geo"> ⛰️ Geología SGM</label>
                                </div>
                            </div>
                        </div>
                        
                        <!-- LEYENDAS -->
                        <div class="legend-panel">
                            {leyenda_html}
                        </div>
                        
                        <!-- BOTÓN GRADIENTE -->
                        <div id="btn-open-gradient" class="leaflet-open-gradient-btn" onclick="toggleGradient()" title="Mostrar Gradiente">
                            <div style="width: 14px; height: 14px; background: linear-gradient(to bottom, #eff3ff, #08519c); border: 1px solid #fff; border-radius: 2px;"></div>
                        </div>

                        <!-- PANEL GRADIENTE -->
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

                        <!-- BOTÓN DIBUJO Y MEDICIÓN (SVG) -->
                        <div id="btn-open-draw" class="leaflet-open-draw-btn" onclick="toggleDraw()" title="Herramientas de Dibujo y Medición">
                            <svg viewBox="0 0 24 24" style="width:16px; height:16px; stroke:#691C32; fill:none; stroke-width:2;">
                                <path d="M12 19l7-7 3 3-7 7-3-3z"/>
                                <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/>
                                <circle cx="12" cy="12" r="2"/>
                            </svg>
                        </div>

                        <!-- PANEL DESPLEGABLE: TRAZADOS Y MEDICIONES -->
                        <div id="draw-panel-container" class="draw-docked-panel" style="display: none;">
                            <div class="docked-draw-header">
                                <div style="display:flex; align-items:center; gap:6px;">
                                    <svg viewBox="0 0 24 24" style="width:14px; height:14px; stroke:#691C32; fill:none; stroke-width:2;">
                                        <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                                        <polyline points="2 17 12 22 22 17"/>
                                        <polyline points="2 12 12 17 22 12"/>
                                    </svg>
                                    <span>Medición y Trazo</span>
                                </div>
                                <span class="docked-draw-close" onclick="toggleDraw()" title="Ocultar">&times;</span>
                            </div>
                            <div class="docked-draw-body">
                                <div class="draw-grid">
                                    <button id="btn-tool-point" class="btn-tool" onclick="activarModoDibujo('point')">
                                        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/></svg>
                                        Punto
                                    </button>
                                    <button id="btn-tool-line" class="btn-tool" onclick="activarModoDibujo('line_string')">
                                        <svg viewBox="0 0 24 24"><path d="M4 20L20 4"/><circle cx="4" cy="20" r="2.5"/><circle cx="20" cy="4" r="2.5"/></svg>
                                        Distancia
                                    </button>
                                    <button id="btn-tool-poly" class="btn-tool" onclick="activarModoDibujo('polygon')">
                                        <svg viewBox="0 0 24 24"><polygon points="12 2 22 8.5 18 20 6 20 2 8.5"/></svg>
                                        Polígono
                                    </button>
                                    <button id="btn-tool-circle" class="btn-tool" onclick="iniciarDibujoCirculo()">
                                        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><line x1="12" y1="12" x2="18.36" y2="5.64"/></svg>
                                        Círculo
                                    </button>
                                </div>

                                <!-- RESULTADOS MÉTRICOS -->
                                <div id="draw-measure-box" class="draw-measure-box"></div>

                                <!-- ACCIONES DE EDICIÓN Y EXPORTACIÓN -->
                                <div class="draw-actions">
                                    <button class="btn-action-sm danger" onclick="eliminarDibujoSeleccionado()" title="Borrar selección o todos los trazos">
                                        <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                                        Limpiar
                                    </button>
                                    <button class="btn-action-sm" onclick="descargarDibujosGeoJSON()" title="Descargar trazos en GeoJSON para QGIS/ArcGIS">
                                        <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                                        GeoJSON
                                    </button>
                                </div>
                            </div>
                        </div>

                        <script>
                            // Iconos SVG para Fullscreen
                            const iconExpandSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
                            const iconCompressSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;

                            // Inicialización del Mapa
                            const map = new maplibregl.Map({{
                                container: 'map',
                                style: {{
                                    'version': 8,
                                    'sources': {{
                                        'base-light': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256 }},
                                        'base-sat': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256 }},
                                        'base-topo': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256 }},
                                        'base-osm': {{ 'type': 'raster', 'tiles': ['https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png'], 'tileSize': 256 }},
                                        'base-street': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256 }},
                                        'base-terrain': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256 }},
                                        'base-ocean': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256 }},
                                        'base-dark': {{ 'type': 'raster', 'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], 'tileSize': 256 }},
                                        'base-google': {{ 'type': 'raster', 'tiles': ['https://mt1.google.com/vt/lyrs=s&x={{x}}&y={{y}}&z={{z}}'], 'tileSize': 256 }}
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
                                        {{ 'id': 'base-google-layer', 'type': 'raster', 'source': 'base-google', 'layout': {{'visibility': 'none'}} }}
                                    ]
                                }},
                                center: [{centro_lon}, {centro_lat}],
                                zoom: 9.5,
                                preserveDrawingBuffer: true
                            }});
                            
                            // Control Fullscreen Custom (Se añade PRIMERO para que quede arriba)
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
                            
                            // Controles Nativos (Brújula y Zoom quedan debajo del Fullscreen)
                            map.addControl(new maplibregl.NavigationControl(), 'top-right');
                            map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-right');

                            // =========================================================
                            // 📐 INICIALIZACIÓN DE MAPBOX DRAW (HERRAMIENTAS DE DIBUJO)
                            // =========================================================
                            const draw = new MapboxDraw({{
                                displayControlsDefault: false,
                                controls: {{}}, // Desactivamos la UI por defecto para usar nuestros botones SVG
                                userProperties: true,
                                styles: [
                                    {{
                                        'id': 'gl-draw-line',
                                        'type': 'line',
                                        'filter': ['all', ['==', '$type', 'LineString'], ['!=', 'mode', 'static']],
                                        'layout': {{ 'line-cap': 'round', 'line-join': 'round' }},
                                        'paint': {{ 'line-color': '#9f2241', 'line-width': 3, 'line-dasharray': [0.2, 2] }}
                                    }},
                                    {{
                                        'id': 'gl-draw-polygon-fill',
                                        'type': 'fill',
                                        'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                                        'paint': {{ 'fill-color': '#285c4d', 'fill-opacity': 0.25 }}
                                    }},
                                    {{
                                        'id': 'gl-draw-polygon-stroke',
                                        'type': 'line',
                                        'filter': ['all', ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']],
                                        'layout': {{ 'line-cap': 'round', 'line-join': 'round' }},
                                        'paint': {{ 'line-color': '#285c4d', 'line-width': 2.5 }}
                                    }},
                                    {{
                                        'id': 'gl-draw-point',
                                        'type': 'circle',
                                        'filter': ['all', ['==', '$type', 'Point'], ['!=', 'meta', 'vertex'], ['!=', 'meta', 'midpoint'], ['!=', 'mode', 'static']],
                                        'paint': {{ 'circle-radius': 5, 'circle-color': '#ffffff', 'circle-stroke-width': 2, 'circle-stroke-color': '#691C32' }}
                                    }},
                                    // ✨ OCULTAR NODOS / VÉRTICES DE EDICIÓN
                                    {{
                                        'id': 'gl-draw-vertex-inactive',
                                        'type': 'circle',
                                        'filter': ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                                        'paint': {{ 'circle-radius': 0, 'circle-opacity': 0 }}
                                    }},
                                    {{
                                        'id': 'gl-draw-vertex-active',
                                        'type': 'circle',
                                        'filter': ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                                        'paint': {{ 'circle-radius': 0, 'circle-opacity': 0 }}
                                    }},
                                    {{
                                        'id': 'gl-draw-midpoint',
                                        'type': 'circle',
                                        'filter': ['all', ['==', 'meta', 'midpoint'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
                                        'paint': {{ 'circle-radius': 0, 'circle-opacity': 0 }}
                                    }}
                                ]
                            }});
                            map.addControl(draw); // Se agrega sin posición porque usamos botones externos

                            // Lógica del Dock (Hamburguesa)
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
                            aplicarEstadoVisualDock(); // Inicializar estado
                            
                            // Lógica del Panel de Gradiente
                            let gradientAbierto = false;
                            function toggleGradient() {{
                                gradientAbierto = !gradientAbierto;
                                const panel = document.getElementById('gradient-panel-container');
                                const btn = document.getElementById('btn-open-gradient');
                                if (gradientAbierto) {{
                                    panel.style.display = 'block';
                                    btn.style.display = 'none';
                                    if (drawAbierto) toggleDraw(); // Cierra el panel de dibujo si estaba abierto
                                }} else {{
                                    panel.style.display = 'none';
                                    btn.style.display = 'flex';
                                }}
                            }}

                            // Lógica del Panel de Dibujo
                            let drawAbierto = false;
                            function toggleDraw() {{
                                drawAbierto = !drawAbierto;
                                const panel = document.getElementById('draw-panel-container');
                                const btn = document.getElementById('btn-open-draw');
                                if (drawAbierto) {{
                                    panel.style.display = 'block';
                                    btn.style.display = 'none';
                                    if (gradientAbierto) toggleGradient(); // Cierra el gradiente si estaba abierto
                                }} else {{
                                    panel.style.display = 'none';
                                    btn.style.display = 'flex';
                                    detenerModoCirculo();
                                    limpiarHerramientasActivas();
                                }}
                            }}

                            // Funciones de Botones de Dibujo
                            function activarModoDibujo(mode) {{
                                detenerModoCirculo();
                                limpiarHerramientasActivas();
                                
                                // Forzar el cursor de cruz para todas las herramientas
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
                                ['btn-tool-point', 'btn-tool-line', 'btn-tool-poly', 'btn-tool-circle'].forEach(id => {{
                                    const el = document.getElementById(id);
                                    if (el) el.classList.remove('active');
                                }});
                                
                                // Restaurar el cursor normal al terminar de dibujar
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
                                if (popupActivo) popupActivo.remove(); // Elimina la etiqueta flotante
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

                            // Modo Circunferencia / Radio Geodésico
                            let modoCirculoActivo = false;
                            let centroCirculo = null;

                            function iniciarDibujoCirculo() {{
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

                            // Selector de Mapas Base (Con Google Satelital 35%)
                            document.getElementById('sel-basemap').addEventListener('change', (e) => {{
                                const selected = e.target.value;
                                const basemaps = ['base-light-layer', 'base-sat-layer', 'base-topo-layer', 'base-osm-layer', 'base-street-layer', 'base-terrain-layer', 'base-ocean-layer', 'base-dark-layer', 'base-google-layer'];
                                
                                basemaps.forEach(id => {{
                                    if (map.getLayer(id)) {{
                                        if (selected === 'base-google-layer') {{
                                            if (id === 'base-light-layer') map.setLayoutProperty(id, 'visibility', 'visible');
                                            else if (id === 'base-google-layer') {{
                                                map.setLayoutProperty(id, 'visibility', 'visible');
                                                map.setPaintProperty(id, 'raster-opacity', 0.35);
                                            }} else {{
                                                map.setLayoutProperty(id, 'visibility', 'none');
                                            }}
                                        }} else {{
                                            map.setLayoutProperty(id, 'visibility', id === selected ? 'visible' : 'none');
                                            if (id === selected) map.setPaintProperty(id, 'raster-opacity', 1.0);
                                        }}
                                    }}
                                }});
                            }});

                            // Variables Matemáticas
                            const z_data = {z_data_json};
                            const bounds = {bounds_json};
                            const min_y = bounds[0][0], min_x = bounds[0][1];
                            const max_y = bounds[1][0], max_x = bounds[1][1];
                            const rows = z_data.length, cols = z_data[0].length;
                            
                            let popupActivo = null;

                            map.on('load', () => {{
                                // Capa auxiliar para preview elástico del círculo
                                map.addSource('temp-circle-src', {{
                                    type: 'geojson',
                                    data: {{ "type": "FeatureCollection", "features": [] }}
                                }});
                                map.addLayer({{
                                    id: 'temp-circle-fill',
                                    type: 'fill',
                                    source: 'temp-circle-src',
                                    paint: {{ 'fill-color': '#008a3b', 'fill-opacity': 0.2 }}
                                }});
                                map.addLayer({{
                                    id: 'temp-circle-line',
                                    type: 'line',
                                    source: 'temp-circle-src',
                                    paint: {{ 'line-color': '#008a3b', 'line-width': 2, 'line-dasharray': [2, 2] }}
                                }});

                                // 1. Geología SGM
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

                                // 2. Kriging Raster
                                map.addSource('kriging-src', {{
                                    type: 'image',
                                    url: 'data:image/png;base64,{img_krig_b64}',
                                    coordinates: {img_coords_json}
                                }});
                                map.addLayer({{
                                    id: 'kriging-layer', type: 'raster', source: 'kriging-src',
                                    paint: {{ 'raster-opacity': 0.65, 'raster-resampling': 'linear' }}
                                }});

                                // 3. Isolíneas
                                map.addSource('iso-src', {{
                                    type: 'image', url: 'data:image/png;base64,{img_iso_b64}', coordinates: {img_coords_json}
                                }});
                                map.addLayer({{ id: 'iso-layer', type: 'raster', source: 'iso-src', paint: {{ 'raster-opacity': 0.95 }} }});

                                // 4. Vectores
                                map.addSource('vec-src', {{
                                    type: 'image', url: 'data:image/png;base64,{img_flujo_b64}', coordinates: {img_coords_json}
                                }});
                                map.addLayer({{ id: 'vec-layer', type: 'raster', source: 'vec-src', paint: {{ 'raster-opacity': 0.9 }} }});

                                // 5. Mapa de Calor (Nativo)
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

                                // 6. Puntos Oficiales
                                map.addLayer({{
                                    id: 'pozos-layer', type: 'circle', source: 'pozos-src',
                                    paint: {{
                                        'circle-radius': 5,
                                        'circle-color': ['get', 'Color'],
                                        'circle-stroke-width': 1,
                                        'circle-stroke-color': '#ffffff'
                                    }}
                                }});

                                // 7. Puntos Adicionales
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

                                // Ajustar vista
                                const polyBounds = {poly_bounds_str};
                                if (polyBounds) {{
                                    map.fitBounds([[polyBounds[0], polyBounds[1]], [polyBounds[2], polyBounds[3]]], {{ padding: 40 }});
                                }}
                            }});

                            // HUD Coordenadas y Valor Interpolado (Mousemove)
                            map.on('mousemove', (e) => {{
                                document.getElementById('hud-lon').innerText = e.lngLat.lng.toFixed(4) + '°';
                                document.getElementById('hud-lat').innerText = e.lngLat.lat.toFixed(4) + '°';
                                
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

                                // Lógica de previsualización del Círculo
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

                            // Lógica de Clic para el Círculo
                            map.on('click', (e) => {{
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
                                        draw.add(circlePoly);
                                        
                                        // Mostrar Popup al finalizar el círculo
                                        if (popupActivo) popupActivo.remove();
                                        popupActivo = new maplibregl.Popup({{ closeOnClick: false, offset: 10 }})
                                            .setLngLat(coords)
                                            .setHTML(`<div class="custom-transparent-popup">
                                                        <b>Radio:</b> ${{(radioKm * 1000).toFixed(1)}} m<br>
                                                        <b>Área:</b> ${{(turf.area(circlePoly) / 10000).toFixed(2)}} ha
                                                      </div>`)
                                            .addTo(map);
                                    }}
                                    detenerModoCirculo();
                                }}
                            }});

                            // Actualizar resultados de medición (Líneas y Polígonos)
                            function generarTextoMedicion(feat) {{
                                const tipo = feat.geometry.type;
                                if (tipo === 'Point') {{
                                    const c = feat.geometry.coordinates;
                                    return `<b>Punto:</b> ${{c[1].toFixed(5)}}° N, ${{c[0].toFixed(5)}}° W`;
                                }} else if (tipo === 'LineString') {{
                                    const km = turf.length(feat, {{ units: 'kilometers' }});
                                    return `<b>Distancia:</b> ${{(km * 1000).toFixed(1)}} m (${{km.toFixed(3)}} km)`;
                                }} else if (tipo === 'Polygon') {{
                                    const m2 = turf.area(feat);
                                    const perim = turf.length(turf.polygonToLine(feat), {{ units: 'kilometers' }});
                                    return `<b>Superficie:</b> ${{(m2 / 10000).toFixed(2)}} ha<br><b>Perímetro:</b> ${{perim.toFixed(2)}} km`;
                                }}
                                return "";
                            }}

                            // 1. ACTUALIZACIÓN EN VIVO (Mientras se mueve el mouse dibujando)
                            map.on('draw.render', () => {{
                                const data = draw.getAll();
                                if (data.features.length > 0) {{
                                    const feat = data.features[data.features.length - 1];
                                    const box = document.getElementById('draw-measure-box');
                                    box.style.display = 'block';
                                    box.innerHTML = generarTextoMedicion(feat) + '<br><span style="color:#64748B; font-size:10px;">Doble clic para finalizar</span>';
                                }}
                            }});

                            // 2. POPUP AL FINALIZAR EL DIBUJO
                            map.on('draw.create', (e) => {{
                                const feat = e.features[0];
                                const texto = generarTextoMedicion(feat);
                                
                                // Determinar dónde anclar el popup
                                let coords;
                                if (feat.geometry.type === 'Point') coords = feat.geometry.coordinates;
                                else if (feat.geometry.type === 'LineString') coords = feat.geometry.coordinates[feat.geometry.coordinates.length - 1];
                                else coords = turf.centroid(feat).geometry.coordinates; // Centro del polígono

                                if (popupActivo) popupActivo.remove();
                                popupActivo = new maplibregl.Popup({{ closeOnClick: false, offset: 10 }})
                                    .setLngLat(coords)
                                    .setHTML(`<div class="custom-transparent-popup">
                                                <h4>📏 Medición Finalizada</h4>
                                                ${{texto}}
                                              </div>`)
                                    .addTo(map);
                                    
                                limpiarHerramientasActivas();
                            }});

                            map.on('draw.selectionchange', (e) => {{
                                if (e.features && e.features.length > 0) {{
                                    const feat = e.features[0];
                                    const texto = generarTextoMedicion(feat);
                                    
                                    // Actualizar la caja si el panel está abierto
                                    const box = document.getElementById('draw-measure-box');
                                    if (box) box.innerHTML = texto;

                                    // Determinar dónde anclar el popup
                                    let coords;
                                    if (feat.geometry.type === 'Point') coords = feat.geometry.coordinates;
                                    else if (feat.geometry.type === 'LineString') {{
                                        const pts = feat.geometry.coordinates;
                                        coords = pts[Math.floor(pts.length / 2)]; // Mitad de la línea
                                    }}
                                    else coords = turf.centroid(feat).geometry.coordinates; // Centro del polígono

                                    if (popupActivo) popupActivo.remove();
                                    popupActivo = new maplibregl.Popup({{ closeOnClick: false, offset: 10 }})
                                        .setLngLat(coords)
                                        .setHTML(`<div class="custom-transparent-popup">
                                                    <h4>📏 Medición</h4>
                                                    ${{texto}}
                                                  </div>`)
                                        .addTo(map);
                                }}
                            }});

                            // =========================================================
                            // 🛡️ PROTECCIÓN DE EVENTOS Y CURSOR DURANTE EL DIBUJO
                            // =========================================================
                            function isDrawingMode() {{
                                try {{
                                    return draw.getMode() !== 'simple_select' || modoCirculoActivo;
                                }} catch(e) {{ return false; }}
                            }}

                            // Eventos de Clic en Pozos Oficiales
                            map.on('click', 'pozos-layer', (e) => {{
                                if (isDrawingMode()) return; // Ignorar si estamos dibujando
                                if (popupActivo) popupActivo.remove();
                                const p = e.features[0].properties;
                                popupActivo = new maplibregl.Popup().setLngLat(e.lngLat)
                                    .setHTML(`<div class="custom-transparent-popup">
                                                <h4>📍 Pozo: ${{p.Pozo}}</h4>
                                                <b>${{p.Variable}}:</b> ${{p.Valor}}<br>
                                                <b>Año de Medición:</b> ${{p.Año}}
                                              </div>`)
                                    .addTo(map);
                            }});

                            // Eventos de Clic en Puntos Adicionales
                            map.on('click', 'add-layer-manual', (e) => showAddPopup(e));
                            map.on('click', 'add-layer-csv', (e) => showAddPopup(e));

                            function showAddPopup(e) {{
                                if (isDrawingMode()) return; // Ignorar si estamos dibujando
                                if (popupActivo) popupActivo.remove();
                                const p = e.features[0].properties;
                                let html = `<div class="custom-transparent-popup"><h4>${{p.nombre}}</h4><b>Tipo:</b> ${{p.tipo}}<br>`;
                                let attrs = p.atributos;
                                if (typeof attrs === 'string') {{
                                    try {{ attrs = JSON.parse(attrs); }} catch(err) {{ attrs = {{}}; }}
                                }}
                                for (const [k, v] of Object.entries(attrs || {{}})) {{ html += `<b>${{k}}:</b> ${{v}}<br>`; }}
                                html += `</div>`;
                                popupActivo = new maplibregl.Popup().setLngLat(e.lngLat).setHTML(html).addTo(map);
                            }}
                            
                            // Eventos de Clic en Geología
                            map.on('click', 'geo-fill', (e) => {{
                                if (isDrawingMode()) return; // Ignorar si estamos dibujando
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
                                    <div class="custom-transparent-popup">
                                        <h4>${{formacion}}</h4>
                                        <b>Clave:</b> ${{claveSgm}}<br>
                                        <b>Litología:</b> ${{litologia}}<br>
                                        <b>Tipo de Roca:</b> ${{roca}}<br>
                                        <b>Edad Geológica:</b> ${{edadGeo}}<br>
                                        <span style="color:#64748B; font-size:10.5px;">Coords: ${{e.lngLat.lat.toFixed(4)}}°, ${{e.lngLat.lng.toFixed(4)}}°</span>
                                    </div>
                                `;
                                popupActivo = new maplibregl.Popup().setLngLat(e.lngLat).setHTML(html).addTo(map);
                            }});

                            // Controlar el cursor (Evitar que cambie a manita si estamos dibujando)
                            const capasInteractivas = ['pozos-layer', 'add-layer-manual', 'add-layer-csv', 'geo-fill'];
                            capasInteractivas.forEach(capa => {{
                                map.on('mouseenter', capa, () => {{
                                    if (!isDrawingMode()) map.getCanvas().style.cursor = 'pointer';
                                }});
                                map.on('mouseleave', capa, () => {{
                                    if (!isDrawingMode()) map.getCanvas().style.cursor = '';
                                }});
                            }});

                            // Toggles de Capas y Sincronización con la Leyenda
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
                            toggleLayer('chk-manual', ['add-layer-manual'], 'leg-manual');
                            toggleLayer('chk-csv', ['add-layer-csv'], 'leg-csv');
                            toggleLayer('chk-geo', ['geo-fill', 'geo-line'], 'leg-geo');

                            // =========================================================
                            // 🖱️ HACER POPUPS ARRASTRABLES (DRAGGABLE) AUTOMÁTICAMENTE
                            // =========================================================
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
                                        if (node.classList && node.classList.contains('maplibregl-popup')) {{
                                            if (popupActivo && !node.dataset.draggable) {{
                                                node.dataset.draggable = "true";
                                                node.style.cursor = 'move';
                                                node.addEventListener('mousedown', (e) => {{
                                                    isDraggingPopup = true;
                                                    map.dragPan.disable(); // Evita que el mapa se mueva al arrastrar
                                                    e.stopPropagation();
                                                }});
                                            }}
                                        }}
                                    }});
                                }});
                            }});
                            // Observar cuando se inyecta un popup al DOM
                            observerPopups.observe(document.body, {{ childList: true, subtree: true }});

                        </script>
                    </body>
                    </html>
                    """
                    components.html(html_maplibre, height=720)

                    # =======================================================
                    # 📥 DESCARGA DIRECTA SIG (GEOTIFF, SHAPEFILE, GEOJSON)
                    # =======================================================
                    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                    with st.expander("📥 Descargar Capas en Formatos SIG (GeoTIFF, Shapefile, GeoJSON)", expanded=False):
                        st.caption("Archivos 100% compatibles con QGIS, ArcGIS, Google Earth y modelación numérica.")
                        col_d1, col_d2, col_d3 = st.columns(3)

                        with col_d1:
                            st.markdown("<p style='font-size:13px; font-weight:700; color:#1E293B; margin:0 0 6px 0;'>🌊 1. Superficie Kriging</p>", unsafe_allow_html=True)
                            st.download_button("🗺️ GeoTIFF Ráster (.tif)", data=geotiff_bytes, file_name=f"kriging_{clave_actual}_{var_real}.tif", mime="image/tiff", use_container_width=True)
                            if shp_krig_zip:
                                st.download_button("📦 Shapefile Malla (.zip)", data=shp_krig_zip, file_name=f"kriging_malla_{clave_actual}.zip", mime="application/zip", use_container_width=True)
                            st.download_button("📄 GeoJSON Malla (.geojson)", data=geojson_krig, file_name=f"kriging_malla_{clave_actual}.geojson", mime="application/geo+json", use_container_width=True)

                        with col_d2:
                            st.markdown("<p style='font-size:13px; font-weight:700; color:#1E293B; margin:0 0 6px 0;'>📏 2. Isolíneas / Isopiezas</p>", unsafe_allow_html=True)
                            if shp_iso_zip:
                                st.download_button("📦 Shapefile Líneas (.zip)", data=shp_iso_zip, file_name=f"isopiezas_{clave_actual}.zip", mime="application/zip", use_container_width=True)
                            st.download_button("📄 GeoJSON Líneas (.geojson)", data=geojson_iso, file_name=f"isopiezas_{clave_actual}.geojson", mime="application/geo+json", use_container_width=True)

                        with col_d3:
                            st.markdown("<p style='font-size:13px; font-weight:700; color:#1E293B; margin:0 0 6px 0;'>🧭 3. Vectores de Flujo</p>", unsafe_allow_html=True)
                            if shp_flujo_zip:
                                st.download_button("📦 Shapefile Vectores (.zip)", data=shp_flujo_zip, file_name=f"vectores_flujo_{clave_actual}.zip", mime="application/zip", use_container_width=True)
                            st.download_button("📄 GeoJSON Vectores (.geojson)", data=geojson_flujo, file_name=f"vectores_flujo_{clave_actual}.geojson", mime="application/geo+json", use_container_width=True)
        else:
            st.warning("⚠️ Se requieren al menos 4 pozos con coordenadas y elevación de terreno válidas para resolver la matriz matemática de interpolación.")
    renderizar_pestaña_mapa()

# =======================================================
# 🏷️ 3. LEYENDA CARTOGRÁFICA OFICIAL SGM (EN PYTHON)
# =======================================================
if 'dic_leyenda_rocas' in locals() and dic_leyenda_rocas:
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

# Inspección de atributos de la litología
if 'gdf_geo' in locals() and gdf_geo is not None and not gdf_geo.empty:
    with st.expander("🔬 Inspeccionar Tabla de Atributos Vectoriales de la Capa SGM", expanded=False):
        st.dataframe(gdf_geo.drop(columns=["geometry"], errors="ignore").head(20), use_container_width=True)

# --- EJE 2: HIDROGRAMAS INTELIGENTES ---
with tab_hidrograma:
    @st.fragment
    def renderizar_pestaña_hidrograma():
        st.write("Selecciona un pozo de la red de monitoreo para analizar su comportamiento temporal y su tasa de abatimiento matemática.")
        pozo_sel = st.selectbox("🎯 Filtrar por Pozo de Monitoreo:", pozos_disponibles)
        
        # ⚡ PROTECCIÓN CONTRA VALORES NULOS PARA EVITAR QUE POLYFIT COLAPSE
        df_pozo = df_ac[df_ac['Pozo'].astype(str) == str(pozo_sel)].sort_values(by='Año').dropna(subset=['Año', 'Profundidad_NE'])
        
        if len(df_pozo) >= 2:
            x = df_pozo['Año'].values
            y = df_pozo['Profundidad_NE'].values
            coeficientes = np.polyfit(x, y, 1)
            pendiente = coeficientes[0] 
            tendencia_y = np.polyval(coeficientes, x)
            
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Última Profundidad Registrada", f"{y[-1]:.2f} m")
            
            if pendiente > 0.1:
                estado, color_linea = "🔴 Abatiéndose", "#9f2241"
                col_m2.metric("Ritmo de Abatimiento", f"-{pendiente:.2f} m/año", "Caída del Nivel", delta_color="inverse")
            elif pendiente < -0.1:
                estado, color_linea = "🟢 Recuperándose", "#285c4d"
                col_m2.metric("Ritmo de Recuperación", f"+{abs(pendiente):.2f} m/año", "Aumento del Nivel", delta_color="normal")
            else:
                estado, color_linea = "🟡 Estable", "#b38e5d"
                col_m2.metric("Tasa de Cambio Promedio", f"{pendiente:.2f} m/año", "Estable", delta_color="off")
                
            col_m3.metric("Diagnóstico Físico", estado)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_pozo['Año'], y=df_pozo['Profundidad_NE'], mode='lines+markers', name='Medición de Campo', line=dict(color='#244062', width=2.5), marker=dict(size=8, color='#b38e5d')))
            ecuacion_txt = f"y = {pendiente:.2f}x {'+' if coeficientes[1]>0 else '-'} {abs(coeficientes[1]):.2f}"
            fig.add_trace(go.Scatter(x=df_pozo['Año'], y=tendencia_y, mode='lines', name=f'Tendencia Histórica ({ecuacion_txt})', line=dict(color=color_linea, width=2, dash='dash')))

            mitad_idx = len(x) // 2
            fig.add_annotation(x=x[mitad_idx], y=tendencia_y[mitad_idx], text=f"<b>Pendiente:<br>{pendiente:.2f} m/año</b>", showarrow=True, arrowhead=2, arrowsize=1, ax=40, ay=-40, font=dict(color=color_linea, size=11), arrowcolor=color_linea, bgcolor="rgba(255,255,255,0.9)", bordercolor=color_linea)

            fig.update_layout(title=f"Hidrograma Invertido - Evolución del Nivel Estático (Pozo: {pozo_sel})", yaxis=dict(autorange="reversed"), height=500, margin=dict(t=60, b=40), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)
        else: st.warning("No hay suficientes datos históricos.")
    renderizar_pestaña_hidrograma()

# --- EJE 4: FORECASTING Y ALERTAS ---
with tab_alertas:
    @st.fragment
    def renderizar_pestaña_alertas():
        st.write("### 🔮 Proyección al Año 2035 (Reloj de Agotamiento)")
        resultados_alertas = []
        
        for pozo in pozos_disponibles:
            # ⚡ PROTECCIÓN CONTRA VALORES NULOS
            df_hist = df_ac[df_ac['Pozo'].astype(str) == str(pozo)].sort_values(by='Año').dropna(subset=['Año', 'Profundidad_NE'])
            if len(df_hist) >= 3: 
                x, y = df_hist['Año'].values, df_hist['Profundidad_NE'].values
                z = np.polyfit(x, y, 1)
                tasa, prof_actual, anio_actual = z[0], y[-1], x[-1]
                prof_2035 = np.polyval(z, 2035)
                alerta = "🚨 Crítico" if tasa > 0.5 else ("⚠️ Precaución" if tasa > 0 else "✅ Estable / Sano")
                resultados_alertas.append({"ID Pozo": str(pozo), "Tasa (m/año)": tasa, "Último Año Medido": int(anio_actual), "Prof. Actual (m)": prof_actual, "Prof. Proyectada 2035 (m)": prof_2035, "Caída Estimada (m)": (prof_2035 - prof_actual) if tasa > 0 else 0.0, "Estatus de Estrés": alerta})
                
        if resultados_alertas:
            df_alertas = pd.DataFrame(resultados_alertas).sort_values(by="Tasa (m/año)", ascending=False)
            def color_estatus(val):
                if "Crítico" in str(val): return "color: #9f2241; font-weight: bold; background-color: #f5e6e8;"
                if "Precaución" in str(val): return "color: #b38e5d; font-weight: bold; background-color: #fcf5eb;"
                if "Estable" in str(val): return "color: #285c4d; font-weight: bold; background-color: #e8f0ec;"
                return ""
            st.dataframe(df_alertas.style.map(color_estatus, subset=['Estatus de Estrés']).format({"Tasa (m/año)": "{:.2f}", "Prof. Actual (m)": "{:.2f}", "Prof. Proyectada 2035 (m)": "{:.2f}", "Caída Estimada (m)": "{:.2f}"}), use_container_width=True, hide_index=True)
            
            pozos_criticos = len(df_alertas[df_alertas["Estatus de Estrés"] == "🚨 Crítico"])
            if pozos_criticos > 0: st.error(f"**Justificación Técnica:** Se detectaron {pozos_criticos} pozos con abatimiento crítico.")
            else: st.success("La red refleja estabilidad física.")
            
            col_g1, col_g2 = st.columns([1, 1.3])
            with col_g1:
                st.write("**1. Panorama Global**")
                fig_bar = px.bar(df_alertas, x="ID Pozo", y="Tasa (m/año)", color="Estatus de Estrés", color_discrete_map={"🚨 Crítico": "#9f2241", "⚠️ Precaución": "#b38e5d", "✅ Estable / Sano": "#285c4d"})
                fig_bar.add_hline(y=0.5, line_dash="dot", annotation_text="Límite Crítico", line_color="#9f2241")
                fig_bar.update_layout(height=450, showlegend=False)
                st.plotly_chart(fig_bar, use_container_width=True)
            with col_g2:
                st.write("**2. Proyección y Cálculo**")
                pozo_demo = st.selectbox("Selecciona un pozo:", df_alertas["ID Pozo"].tolist())
                # ⚡ PROTECCIÓN CONTRA VALORES NULOS
                df_pozo_demo = df_ac[df_ac['Pozo'].astype(str) == pozo_demo].sort_values(by='Año').dropna(subset=['Año', 'Profundidad_NE'])
                x, y = df_pozo_demo['Año'].values, df_pozo_demo['Profundidad_NE'].values
                z = np.polyfit(x, y, 1)
                x_proy = np.arange(x[0], 2036)
                y_proy = np.polyval(z, x_proy)
                
                fig_demo = go.Figure()
                fig_demo.add_trace(go.Scatter(x=x_proy, y=y_proy, mode='lines', name=f'Regresión Lineal', line=dict(color='#888', width=1.5, dash='dot')))
                fig_demo.add_trace(go.Scatter(x=x, y=y, mode='markers', name='Datos Reales', marker=dict(color='#244062', size=8)))
                fig_demo.add_trace(go.Scatter(x=[x[-1]], y=[y[-1]], mode='markers', name=f'Última Medida', marker=dict(color='#b38e5d', size=12, symbol='square')))
                fig_demo.add_trace(go.Scatter(x=[2035], y=[np.polyval(z, 2035)], mode='markers', name='Proyección 2035', marker=dict(color='#9f2241', size=14, symbol='star')))
                if z[0] > 0:
                    fig_demo.add_shape(type="line", x0=x[-1], y0=y[-1], x1=2035, y1=y[-1], line=dict(color="gray", width=1, dash="dash"))
                    fig_demo.add_annotation(x=2035, y=(y[-1] + np.polyval(z, 2035))/2, ax=2035, ay=y[-1], text=f"<b>Caída:<br>{np.polyval(z, 2035) - y[-1]:.1f} m</b>", showarrow=True, arrowhead=2)
                fig_demo.update_layout(yaxis=dict(autorange="reversed"), height=450)
                st.plotly_chart(fig_demo, use_container_width=True)
    renderizar_pestaña_alertas()
