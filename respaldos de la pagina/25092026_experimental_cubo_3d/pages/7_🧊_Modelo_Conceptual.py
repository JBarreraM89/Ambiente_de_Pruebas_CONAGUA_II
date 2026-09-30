# -*- coding: utf-8 -*-
"""
Módulo de Modelo Geológico y Conceptual 3D Subterráneo
Integra:
- Selector de Cobertura: [Bloque 3D del Acuífero (Subterráneo) | Entorno Regional Continuo]
- Cámara Orbital Esférica 360° (rotación en todas direcciones, incluso desde abajo del subsuelo)
- Cargador CSV de pozos con modelado de cilindros 3D de perforación en profundidad
- Simulación de zona no saturada y zona saturada (nivel estático)
- Transparencia superficial tipo Rayos X
- Exportación en GeoTIFF (.tif) y Shapefile (.zip)
"""

import streamlit as st
import streamlit.components.v1 as components
import geopandas as gpd
import pandas as pd
import numpy as np
import rasterio
import rasterio.mask
import rasterio.features
from rasterio.transform import from_bounds
from PIL import Image
from scipy.ndimage import zoom as nd_zoom
from concurrent.futures import ThreadPoolExecutor
import requests
import tempfile
import zipfile
import math
import os
import io
import re
import json
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

st.subheader("🧊 Estación de Trabajo: Modelo Conceptual y Geológico 3D")
st.caption("Caracterización tridimensional superficial y subterránea: Litología oficial SGM, pozos con profundidad y cámara orbital 360°.")

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
# 🔍 3. SINCRONIZACIÓN Y SELECCIÓN DE ACUÍFERO
# =======================================================
clave_actual = st.session_state.get("clave_global")
nombre_actual = st.session_state.get("nombre_global")
area_actual = st.session_state.get("area_total_global", 0)

with st.expander("📍 Búsqueda y Selección de Acuífero", expanded=not clave_actual):
    df_cat = cargar_catalogo("Acuiferos_2026.csv")
    if not df_cat.empty:
        c_est, c_clav = st.columns(2)
        estados = sorted(df_cat["ESTADO"].dropna().unique().tolist())
        estado_sel = c_est.selectbox("1. Estado:", estados, key="mc_sel_edo", index=None, placeholder="Elige un estado...")

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
    st.info("👆 Selecciona un Acuífero para generar el modelo conceptual tridimensional.")
    st.stop()

with st.container(border=True):
    col_b1, col_b2, col_b3 = st.columns([1, 2, 1])
    col_b1.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>CLAVE OFICIAL</p><h4 style='color:#691C32; margin:0;'>{clave_actual}</h4>", unsafe_allow_html=True)
    col_b2.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>ACUÍFERO</p><h4 style='color:#691C32; margin:0;'>{nombre_actual}</h4>", unsafe_allow_html=True)
    col_b3.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>SUPERFICIE</p><h4 style='color:#691C32; margin:0;'>{float(area_actual):,.1f} km²</h4>", unsafe_allow_html=True)

gdf_m = cargar_datos_maestros()
def normalizar_cve(v):
    try: return str(int(float(v))).zfill(4)
    except: return str(v).strip().zfill(4)

coincidencias = gdf_m[gdf_m['CLV_ACUI'].apply(normalizar_cve) == normalizar_cve(clave_actual)] if gdf_m is not None else None
if coincidencias is None or coincidencias.empty:
    st.error(f"No se localizó la geometría espacial del acuífero {clave_actual}.")
    st.stop()

datos_ac = coincidencias.iloc[0]

# =======================================================
# 🎛️ 4. CONTROLES: COBERTURA, SUBTERRÁNEO Y RESOLUCIÓN
# =======================================================
with st.container(border=True):
    st.markdown("<p style='font-size: 13px; font-weight: 700; color: #691C32; margin: 0 0 8px 0;'>🎛️ CONTROLES DEL MODELO CONCEPTUAL</p>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([0.28, 0.24, 0.24, 0.24])
    
    opciones_cobertura = ["📦 Bloque del Acuífero (Subterráneo 360°)", "🌐 Entorno Regional Continuo"]
    modo_cobertura = c1.radio("🌍 Modo de Cobertura:", opciones_cobertura, index=0)
    es_modo_bloque = "Bloque" in modo_cobertura

    opciones_pix = {
        "Alta (~35 m / SRTM NASA)": 12,
        "Media (~70 m)": 11,
        "Regional (~140 m)": 10
    }
    sel_pix = c2.selectbox("📡 Resolución DEM (Píxel):", list(opciones_pix.keys()), index=0)
    zoom_elegido = opciones_pix[sel_pix]

    exag_terr = c3.slider("⛰️ Exageración Relieve", min_value=0.5, max_value=4.0, value=1.8, step=0.1)
    opacidad_terreno = c4.slider("🔍 Opacidad Terreno (Rayos X)", min_value=0.1, max_value=1.0, value=0.75, step=0.05)

# =======================================================
# 📁 5. GESTOR DE POZOS CON PROFUNDIDAD (CSV SUBTERRÁNEO)
# =======================================================
with st.expander("💧 Carga de Pozos con Profundidad de Perforación (CSV Subterráneo)", expanded=False):
    col_csv1, col_csv2 = st.columns([0.7, 0.3])
    archivo_csv_pozos = col_csv1.file_uploader("Subir CSV con columnas: LATITUD, LONGITUD, PROFUNDIDAD_M (opcional: ID_POZO, NIVEL_ESTATICO_M, USO):", type=["csv"])
    
    usar_pozos_demo = False
    with col_csv2:
        st.markdown("<div style='margin-top:25px;'></div>", unsafe_allow_html=True)
        if st.button("🎲 Cargar Pozos de Demostración", help="Genera perforaciones 3D de prueba en el acuífero para evaluar la vista subterránea"):
            usar_pozos_demo = True

pozos_3d_data = []

if archivo_csv_pozos is not None:
    try:
        try: df_pozos_in = pd.read_csv(archivo_csv_pozos, encoding='utf-8')
        except: df_pozos_in = pd.read_csv(archivo_csv_pozos, encoding='latin1')
        df_pozos_in.columns = df_pozos_in.columns.str.strip().str.upper()

        c_lat = next((c for c in df_pozos_in.columns if any(k in c for k in ['LAT', 'Y', 'NORTE'])), None)
        c_lon = next((c for c in df_pozos_in.columns if any(k in c for k in ['LON', 'X', 'OESTE'])), None)
        c_prof = next((c for c in df_pozos_in.columns if any(k in c for k in ['PROF', 'DEPTH', 'PERFORA'])), None)
        c_ne = next((c for c in df_pozos_in.columns if any(k in c for k in ['NIVEL', 'ESTATICO', 'NE'])), None)
        c_nom = next((c for c in df_pozos_in.columns if any(k in c for k in ['ID', 'POZO', 'NOMBRE', 'SITIO'])), None)

        if c_lat and c_lon:
            for i, r in df_pozos_in.iterrows():
                try:
                    lat_v = float(r[c_lat])
                    lon_v = -abs(float(r[c_lon]))
                    prof_v = float(r[c_prof]) if c_prof and pd.notna(r[c_prof]) else 200.0
                    ne_v = float(r[c_ne]) if c_ne and pd.notna(r[c_ne]) else 45.0
                    nom_v = str(r[c_nom]) if c_nom and pd.notna(r[c_nom]) else f"Pozo {i+1}"
                    pozos_3d_data.append({
                        "id": nom_v, "lat": lat_v, "lon": lon_v, 
                        "prof": prof_v, "ne": ne_v
                    })
                except Exception: pass
            st.success(f"✅ Se cargaron exitosamente {len(pozos_3d_data)} pozos con perforación subterránea 3D.")
    except Exception as e:
        st.error(f"Error procesando CSV: {e}")

if (usar_pozos_demo or not pozos_3d_data) and usar_pozos_demo:
    minx, miny, maxx, maxy = datos_ac.geometry.bounds
    np.random.seed(42)
    lons_rnd = np.random.uniform(minx + 0.1, maxx - 0.1, 12)
    lats_rnd = np.random.uniform(miny + 0.1, maxy - 0.1, 12)
    profs_rnd = np.random.uniform(150.0, 420.0, 12)
    nes_rnd = np.random.uniform(30.0, 85.0, 12)
    for i in range(12):
        pozos_3d_data.append({
            "id": f"PZ-DEMO-{i+1:02d}", "lat": float(lats_rnd[i]), "lon": float(lons_rnd[i]),
            "prof": float(round(profs_rnd[i], 1)), "ne": float(round(nes_rnd[i], 1))
        })
    st.info(f"ℹ️ Mostrando 12 perforaciones subterráneas 3D de demostración (Profundidades de 150 m a 420 m).")

# =======================================================
# 🛰️ 6. PIPELINE TOPOGRÁFICO Y GEOLÓGICO
# =======================================================
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

# 📦 FUNCIÓN AGREGADA: Exportación de Shapefile en archivo .ZIP
def exportar_shapefile_zip(gdf, base_name):
    """Empaqueta un GeoDataFrame en un archivo Shapefile (.zip) en memoria."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, f"{base_name}.shp")
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)
        else:
            gdf = gdf.to_crs(epsg=4326)
        gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")
        
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(tmpdir):
                zf.write(os.path.join(tmpdir, f), arcname=f)
        buf.seek(0)
        return buf.getvalue()

@st.cache_data(show_spinner=False)
def preparar_geologia_vectorial(clave_ac):
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_geologia"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_cache_parquet = carpeta_cache / f"GEO_SHP_{clave_ac}.parquet"
    geom_4326 = datos_ac.geometry
    gdf_sgm = None

    if ruta_cache_parquet.exists() and ruta_cache_parquet.stat().st_size > 2000:
        try: gdf_sgm = gpd.read_parquet(ruta_cache_parquet)
        except Exception: pass

    if gdf_sgm is None or gdf_sgm.empty:
        rutas_busqueda = [DIRECTORIO_RAIZ / "data" / "geologia", Path.home() / "Downloads"]
        for r_dir in rutas_busqueda:
            if not r_dir.exists(): continue
            for shp_p in r_dir.glob("*.shp"):
                if any(k in shp_p.name.lower() for k in ["lito", "geo", "cnal"]):
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

            for z in r_dir.glob("*.zip"):
                try:
                    with zipfile.ZipFile(z, 'r') as z_ref:
                        shps = [a for a in z_ref.namelist() if a.endswith(".shp") and ("lito" in a.lower() or "geo" in a.lower() or "cnal" in a.lower())]
                        if shps:
                            with tempfile.TemporaryDirectory() as tmp_z:
                                z_ref.extractall(tmp_z)
                                for s in Path(tmp_z).rglob("*.shp"):
                                    gdf_temp = gpd.read_file(s, encoding='latin1')
                                    if gdf_temp.crs is None: gdf_temp = gdf_temp.set_crs(epsg=4326)
                                    else: gdf_temp = gdf_temp.to_crs(epsg=4326)
                                    recorte = gdf_temp.clip(geom_4326)
                                    if not recorte.empty:
                                        gdf_sgm = recorte
                                        break
                    if gdf_sgm is not None: break
                except Exception: pass
            if gdf_sgm is not None: break

    if gdf_sgm is not None and not gdf_sgm.empty:
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
        gdf_sgm["ETIQUETA_LITO"] = gdf_sgm[col_sel].astype(str)
        gdf_sgm["geometry"] = gdf_sgm.geometry.simplify(tolerance=0.00015, preserve_topology=True)
        return gdf_sgm[["ETIQUETA_LITO", "COLOR_HEX", "geometry"]], dic_leyenda, col_sel

    return None, {}, "Ninguna"

gdf_geologia_recortada, dic_leyenda_rocas, col_litologica = preparar_geologia_vectorial(clave_actual)

with st.spinner(f"Sincronizando topografía a {sel_pix}..."):
    try: ruta_dem_local = obtener_o_generar_dem_acuifero(datos_ac, clave_actual, zoom_level=zoom_elegido)
    except Exception as e:
        st.error(f"Error cargando DEM: {e}")
        ruta_dem_local = None

# Preparación de GeoJSONs
gdf_borde = gpd.GeoDataFrame(geometry=[datos_ac.geometry], crs="EPSG:4326")
geojson_borde = gdf_borde.to_json()
minx, miny, maxx, maxy = datos_ac.geometry.bounds
centro_lon = (minx + maxx) / 2.0
centro_lat = (miny + maxy) / 2.0

geojson_geologia = gdf_geologia_recortada.to_json() if gdf_geologia_recortada is not None else "{}"
json_pozos_subterraneos = json.dumps(pozos_3d_data)

# =======================================================
# 🌐 7. ESTACIÓN 3D COMPLETA (BLOQUE 360° SUBTERRÁNEO VS REGIONAL)
# =======================================================
if es_modo_bloque:
    html_3d = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Bloque Subterráneo 3D</title>
        <style>
            body {{ margin: 0; overflow: hidden; background-color: #0b0f19; font-family: 'Segoe UI', Arial, sans-serif; }}
            #canvas-container {{ width: 100vw; height: 100vh; }}
            .hud-3d {{
                position: absolute; top: 12px; left: 12px; z-index: 100;
                background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(8px);
                color: #f8fafc; padding: 10px 16px; border-radius: 8px;
                border: 1px solid rgba(221, 201, 163, 0.4); font-size: 11.5px;
            }}
            .hud-3d b {{ color: #DDC9A3; }}
            .tooltip-pozo {{
                position: absolute; display: none; background: white; color: #1E293B;
                padding: 8px 12px; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                font-size: 11.5px; border-left: 4px solid #008a3b; pointer-events: none; z-index: 200;
            }}
        </style>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    </head>
    <body>
        <div class="hud-3d">
            <b>📦 BLOQUE ACUÍFERO SUBTERRÁNEO 360°</b><br>
            🖱️ <b>Rotación Libre:</b> Arrastra con clic izquierdo para girar arriba, a los lados o <b>por debajo del acuífero</b>.<br>
            🔍 <b>Zoom:</b> Rueda del ratón | ↔️ <b>Desplazar:</b> Clic derecho.
        </div>
        <div id="tooltip" class="tooltip-pozo"></div>
        <div id="canvas-container"></div>

        <script>
            const pozos = {json_pozos_subterraneos};
            const bbox = [{minx}, {miny}, {maxx}, {maxy}];
            const exag = {exag_terr};
            const opac = {opacidad_terreno};

            const container = document.getElementById('canvas-container');
            const scene = new THREE.Scene();
            scene.background = new THREE.Color(0x0b0f19);

            const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 2000);
            camera.position.set(0, -180, 140);

            const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true, preserveDrawingBuffer: true }});
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(window.devicePixelRatio);
            container.appendChild(renderer.domElement);

            const controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            controls.minPolarAngle = 0; 
            controls.maxPolarAngle = Math.PI; // Permite mirar totalmente desde abajo

            const ambLight = new THREE.AmbientLight(0xffffff, 0.7);
            scene.add(ambLight);
            const dirLight = new THREE.DirectionalLight(0xfff5e6, 0.8);
            dirLight.position.set(100, -100, 200);
            scene.add(dirLight);
            const bottomLight = new THREE.DirectionalLight(0x90caf9, 0.4);
            bottomLight.position.set(0, 0, -200);
            scene.add(bottomLight);

            function toX(lon) {{ return ((lon - bbox[0]) / (bbox[2] - bbox[0]) - 0.5) * 160; }}
            function toY(lat) {{ return ((lat - bbox[1]) / (bbox[3] - bbox[1]) - 0.5) * 160; }}

            const gridW = 120, gridH = 120;
            const geomSurf = new THREE.PlaneGeometry(160, 160, gridW - 1, gridH - 1);
            const matSurf = new THREE.MeshStandardMaterial({{
                color: 0xD7CBB5, roughness: 0.8, transparent: true, opacity: opac, side: THREE.DoubleSide
            }});
            const meshSurf = new THREE.Mesh(geomSurf, matSurf);
            scene.add(meshSurf);

            const grupoPozos = new THREE.Group();
            const cilindrosRaycast = [];

            pozos.forEach(p => {{
                const px = toX(p.lon);
                const py = toY(p.lat);
                const profEscalada = (p.prof / 15.0) * exag;
                const neEscalado = (p.ne / 15.0) * exag;

                const hSeca = Math.max(0.5, neEscalado);
                const geomSeca = new THREE.CylinderGeometry(0.7, 0.7, hSeca, 12);
                geomSeca.rotateX(Math.PI / 2);
                const matSeca = new THREE.MeshStandardMaterial({{ color: 0x94a3b8, metalness: 0.5, roughness: 0.3 }});
                const meshSeca = new THREE.Mesh(geomSeca, matSeca);
                meshSeca.position.set(px, py, -hSeca / 2);
                grupoPozos.add(meshSeca);

                const hAgua = Math.max(1.0, profEscalada - neEscalado);
                const geomAgua = new THREE.CylinderGeometry(0.7, 0.7, hAgua, 12);
                geomAgua.rotateX(Math.PI / 2);
                const matAgua = new THREE.MeshStandardMaterial({{ color: 0x0284c7, metalness: 0.2, roughness: 0.2 }});
                const meshAgua = new THREE.Mesh(geomAgua, matAgua);
                meshAgua.position.set(px, py, -neEscalado - (hAgua / 2));
                meshAgua.userData = p;
                grupoPozos.add(meshAgua);
                cilindrosRaycast.push(meshAgua);

                const geomBrocal = new THREE.SphereGeometry(1.2, 16, 16);
                const matBrocal = new THREE.MeshBasicMaterial({{ color: 0x008a3b }});
                const meshBrocal = new THREE.Mesh(geomBrocal, matBrocal);
                meshBrocal.position.set(px, py, 0.5);
                grupoPozos.add(meshBrocal);
            }});
            scene.add(grupoPozos);

            const gridHelper = new THREE.GridHelper(180, 18, 0x334155, 0x1e293b);
            gridHelper.position.z = -50;
            gridHelper.rotateX(Math.PI / 2);
            scene.add(gridHelper);

            const raycaster = new THREE.Raycaster();
            const mouse = new THREE.Vector2();
            const tooltip = document.getElementById('tooltip');

            window.addEventListener('mousemove', (e) => {{
                mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
                mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
                raycaster.setFromCamera(mouse, camera);
                const intersects = raycaster.intersectObjects(cilindrosRaycast);

                if (intersects.length > 0) {{
                    const d = intersects[0].object.userData;
                    tooltip.style.display = 'block';
                    tooltip.style.left = (e.clientX + 14) + 'px';
                    tooltip.style.top = (e.clientY + 14) + 'px';
                    tooltip.innerHTML = `<b>${{d.id}}</b><br>⛏️ Profundidad Total: <b>${{d.prof}} m</b><br>💧 Nivel Estático: <b>${{d.ne}} m</b>`;
                }} else {{
                    tooltip.style.display = 'none';
                }}
            }});

            function animate() {{
                requestAnimationFrame(animate);
                controls.update();
                renderer.render(scene, camera);
            }}
            animate();

            window.addEventListener('resize', () => {{
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            }});
        </script>
    </body>
    </html>
    """
    components.html(html_3d, height=760)

else:
    html_regional = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Entorno Regional Continuo</title>
        <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
        <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
        <style>
            body {{ margin: 0; padding: 0; }}
            #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; }}
            .hud-reg {{
                position: absolute; top: 12px; left: 12px; background: rgba(15, 23, 42, 0.9);
                color: white; padding: 8px 14px; border-radius: 6px; font-size: 11px;
                border-left: 3px solid #691C32; font-family: 'Segoe UI', Arial, sans-serif;
            }}
        </style>
    </head>
    <body>
    <div id="map"></div>
    <div class="hud-reg">
        <b>🌐 ENTORNO REGIONAL CONTINUO</b><br>
        Relieve infinito de cuenca y zonas de recarga montañosa circundantes.
    </div>

    <script>
        const dataGeologia = {geojson_geologia};
        const dataBorde = {geojson_borde};
        const pozos = {json_pozos_subterraneos};

        const map = new maplibregl.Map({{
            container: 'map',
            style: {{
                version: 8,
                sources: {{
                    'esri-imagery': {{
                        'type': 'raster',
                        'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'],
                        'tileSize': 256
                    }},
                    'terrainSource': {{
                        'type': 'raster-dem',
                        'encoding': 'terrarium',
                        'tiles': ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{{z}}/{{x}}/{{y}}.png'],
                        'tileSize': 256
                    }}
                }},
                layers: [
                    {{ 'id': 'satelite', 'type': 'raster', 'source': 'esri-imagery' }},
                    {{
                        'id': 'hillshade', 'type': 'hillshade', 'source': 'terrainSource',
                        'paint': {{ 'hillshade-exaggeration': 0.6, 'hillshade-illumination-direction': 315 }}
                    }}
                ]
            }},
            center: [{centro_lon}, {centro_lat}],
            zoom: 9.5, pitch: 60, bearing: -15, maxPitch: 85
        }});

        map.on('load', () => {{
            map.setTerrain({{ 'source': 'terrainSource', 'exaggeration': {exag_terr} }});

            if (dataGeologia.features && dataGeologia.features.length > 0) {{
                map.addSource('geo-src', {{ 'type': 'geojson', 'data': dataGeologia }});
                map.addLayer({{
                    'id': 'geo-fill', 'type': 'fill', 'source': 'geo-src',
                    'paint': {{ 'fill-color': ['get', 'COLOR_HEX'], 'fill-opacity': {opacidad_terreno} }}
                }});
                map.addLayer({{
                    'id': 'geo-lines', 'type': 'line', 'source': 'geo-src',
                    'paint': {{ 'line-color': '#333333', 'line-width': 1.0 }}
                }});
            }}

            map.addSource('borde-src', {{ 'type': 'geojson', 'data': dataBorde }});
            map.addLayer({{
                'id': 'borde-layer', 'type': 'line', 'source': 'borde-src',
                'paint': {{ 'line-color': '#691C32', 'line-width': 3.5, 'line-dasharray': [3, 2] }}
            }});

            pozos.forEach(p => {{
                const el = document.createElement('div');
                el.style.width = '14px'; el.style.height = '14px'; el.style.borderRadius = '50%';
                el.style.backgroundColor = '#008a3b'; el.style.border = '2px solid white';
                el.style.boxShadow = '0 2px 6px rgba(0,0,0,0.5)';
                new maplibregl.Marker({{ element: el }})
                    .setLngLat([p.lon, p.lat])
                    .setPopup(new maplibregl.Popup().setHTML(`<b>${{p.id}}</b><br>Profundidad: ${{p.prof}} m<br>Nivel Estático: ${{p.ne}} m`))
                    .addTo(map);
            }});
        }});
        map.addControl(new maplibregl.NavigationControl(), 'top-right');
    </script>
    </body>
    </html>
    """
    components.html(html_regional, height=760)

# =======================================================
# 📊 8. AUDITORÍA Y DESCARGAS CARTOGRÁFICAS
# =======================================================
if ruta_dem_local and ruta_dem_local.exists():
    with rasterio.open(ruta_dem_local) as src_meta:
        w_px, h_px = src_meta.width, src_meta.height
        peso_mb = os.path.getsize(ruta_dem_local) / (1024 * 1024)
        res_x_deg = src_meta.res[0]
        lat_media = (src_meta.bounds.bottom + src_meta.bounds.top) / 2.0
        tam_pixel_m = res_x_deg * (111320.0 * math.cos(math.radians(lat_media)))

    with st.container(border=True):
        st.markdown("<p style='font-size: 12px; font-weight: 700; color: #1E293B; margin: 0 0 6px 0;'>📋 AUDITORÍA CARTOGRÁFICA DEL MODELO FÍSICO</p>", unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Resolución Ráster", f"{tam_pixel_m:.1f} m / píxel", f"Zoom {zoom_elegido}")
        m2.metric("Dimensiones", f"{w_px:,} × {h_px:,} px")
        m3.metric("Peso GeoTIFF", f"{peso_mb:.2f} MB")
        m4.metric("Pozos Subterráneos 3D", f"{len(pozos_3d_data)} perforaciones")

    cd1, cd2 = st.columns(2)
    with cd1:
        with open(ruta_dem_local, "rb") as f_dem:
            st.download_button(
                label=f"💾 Descargar GeoTIFF Recortado [{sel_pix.split(' ')[0]} - {tam_pixel_m:.1f}m - .tif]",
                data=f_dem,
                file_name=f"DEM_Acuifero_{clave_actual}_z{zoom_elegido}.tif",
                mime="image/tiff",
                use_container_width=True
            )
    with cd2:
        if gdf_geologia_recortada is not None and not gdf_geologia_recortada.empty:
            zip_shp_bytes = exportar_shapefile_zip(gdf_geologia_recortada, f"Geologia_{clave_actual}")
            st.download_button(
                label="📦 Descargar Geología Shapefile (.zip)",
                data=zip_shp_bytes,
                file_name=f"Geologia_Shapefile_{clave_actual}.zip",
                mime="application/zip",
                use_container_width=True
            )

# =======================================================
# 🏷️ 9. LEYENDA CARTOGRÁFICA OFICIAL SGM
# =======================================================
if dic_leyenda_rocas:
    st.markdown(f"""
        <div style='background-color:#F8FAFC; border-left:4px solid #691C32; padding:10px 14px; border-radius:4px; margin-top:10px; margin-bottom:8px;'>
            <span style='font-size:12.5px; font-weight:bold; color:#691C32;'>SIMBOLOGÍA LITOLÓGICA OFICIAL (SGM - INEGI)</span>
            <span style='font-size:11px; color:#64748B; margin-left:14px;'><b>Origen:</b> {ORIGEN_SGM_GLOBAL} | <b>Campo:</b> <code>{col_litologica}</code></span>
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