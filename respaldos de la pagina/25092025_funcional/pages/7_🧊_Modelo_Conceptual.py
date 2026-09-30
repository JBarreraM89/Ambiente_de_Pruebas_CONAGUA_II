# -*- coding: utf-8 -*-
"""
Created on Fri Sep 25 10:46:24 2026

@author: dchable
"""

# -*- coding: utf-8 -*-
"""
Módulo de Modelo Geológico y Conceptual 3D
Visualización tridimensional del relieve, litología oficial INEGI/SGM y límites de acuíferos.
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import rasterio
import rasterio.mask
import rasterio.features
from rasterio.transform import from_bounds
import plotly.graph_objects as go
from pathlib import Path
from PIL import Image
import requests
import tempfile
import zipfile
import math
import os
import io

# Importaciones del Core
from utils.styles import inyectar_css_oficial, banner_institucional
from core.data_loader import cargar_catalogo, cargar_datos_maestros, DIRECTORIO_RAIZ

# =======================================================
# 🎨 1. CONFIGURACIÓN Y ESTILOS
# =======================================================
st.set_page_config(layout="wide", page_title="Modelo Conceptual 3D", page_icon="🧊")
inyectar_css_oficial()
banner_institucional()

st.subheader("🧊 Modelo Conceptual y Geológico 3D")
st.caption("Caracterización geomorfológica tridimensional, relieve estructural y litología oficial (INEGI / SGM).")

# =======================================================
# 🔍 2. SINCRONIZACIÓN Y BUSCADOR DE ACUÍFERO
# =======================================================
clave_actual = st.session_state.get("clave_global")
nombre_actual = st.session_state.get("nombre_global")
area_actual = st.session_state.get("area_total_global", 0)

abrir_buscador = True if not clave_actual else False

with st.expander("📍 Búsqueda y Selección de Acuífero", expanded=abrir_buscador):
    df_cat = cargar_catalogo("Acuiferos_2026.csv")
    if not df_cat.empty:
        try:
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
        except Exception as e:
            st.error(f"Error cargando catálogo: {e}")

if not clave_actual or not nombre_actual:
    st.info("👆 Selecciona un Estado y Acuífero en el buscador superior para generar el modelo conceptual tridimensional.")
    st.stop()

# Banner informativo
with st.container(border=True):
    col_b1, col_b2, col_b3 = st.columns([1, 2, 1])
    col_b1.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>CLAVE OFICIAL</p><h4 style='color:#691C32; margin:0;'>{clave_actual}</h4>", unsafe_allow_html=True)
    col_b2.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>ACUÍFERO</p><h4 style='color:#691C32; margin:0;'>{nombre_actual}</h4>", unsafe_allow_html=True)
    col_b3.markdown(f"<p style='font-size:12px; color:#64748B; margin:0;'>SUPERFICIE</p><h4 style='color:#691C32; margin:0;'>{float(area_actual):,.1f} km²</h4>", unsafe_allow_html=True)

# Obtener geometría oficial del acuífero
gdf_m = cargar_datos_maestros()
def normalizar_cve(v):
    try: return str(int(float(v))).zfill(4)
    except: return str(v).strip().zfill(4)

coincidencias = gdf_m[gdf_m['CLV_ACUI'].apply(normalizar_cve) == normalizar_cve(clave_actual)] if gdf_m is not None else None
if coincidencias is None or coincidencias.empty:
    st.error(f"No se localizó la geometría espacial del acuífero {clave_actual} en la base cartográfica maestra.")
    st.stop()

datos_ac = coincidencias.iloc[0]

# =======================================================
# 🛰️ 3. FUNCIONES DE PROCESAMIENTO RÁSTER Y VECTORIAL
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
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg

def obtener_o_generar_dem_acuifero(datos_ac, clave_ac):
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_dem"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_tif = carpeta_cache / f"DEM_{clave_ac}.tif"
    
    if ruta_tif.exists():
        return ruta_tif

    minx, miny, maxx, maxy = datos_ac.geometry.bounds
    zoom = 10
    
    x_start, y_start = deg2num(maxy, minx, zoom)
    x_end, y_end = deg2num(miny, maxx, zoom)
    
    num_x = (x_end - x_start) + 1
    num_y = (y_end - y_start) + 1
    
    malla_elevacion = np.zeros((num_y * 256, num_x * 256), dtype=np.float32)
    
    for iy, y in enumerate(range(y_start, y_end + 1)):
        for ix, x in enumerate(range(x_start, x_end + 1)):
            url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{x}/{y}.png"
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    img = Image.open(io.BytesIO(r.content)).convert('RGB')
                    arr = np.array(img, dtype=np.float32)
                    elev = (arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0) - 32768.0
                    malla_elevacion[iy*256:(iy+1)*256, ix*256:(ix+1)*256] = elev
            except Exception:
                pass
                
    lat_top, lon_left = num2deg(x_start, y_start, zoom)
    lat_bottom, lon_right = num2deg(x_end + 1, y_end + 1, zoom)
    
    transform_base = from_bounds(lon_left, lat_bottom, lon_right, lat_top, malla_elevacion.shape[1], malla_elevacion.shape[0])
    
    with rasterio.MemoryFile() as memfile:
        with memfile.open(
            driver='GTiff', height=malla_elevacion.shape[0], width=malla_elevacion.shape[1],
            count=1, dtype='float32', crs='EPSG:4326', transform=transform_base, nodata=-9999.0
        ) as dataset:
            dataset.write(malla_elevacion, 1)
            geom_json = [datos_ac.geometry.__geo_interface__]
            out_img, out_trans = rasterio.mask.mask(dataset, geom_json, crop=True, nodata=-9999.0)
            meta_final = dataset.meta.copy()

    meta_final.update({
        "height": out_img.shape[1],
        "width": out_img.shape[2],
        "transform": out_trans,
        "nodata": -9999.0
    })
    
    with rasterio.open(ruta_tif, 'w', **meta_final) as dst:
        dst.write(out_img)
        
    return ruta_tif

def calcular_carta_inegi_250k(lat, lon):
    if -102.0 <= lon < -96.0: zona = 14
    elif -108.0 <= lon < -102.0: zona = 13
    elif -114.0 <= lon < -108.0: zona = 12
    elif -96.0 <= lon < -90.0: zona = 15
    else: zona = 14

    if 16.0 <= lat < 20.0: banda = "E"
    elif 14.0 <= lat < 16.0: banda = "D"
    elif 20.0 <= lat < 24.0: banda = "F"
    elif 24.0 <= lat < 28.0: banda = "G"
    else: banda = "E"

    if 19.0 <= lat <= 20.0 and -100.0 <= lon <= -98.0: return "E14-2"
    if 15.0 <= lat <= 16.5 and -98.0 <= lon <= -96.0: return "D14-3"
    return f"{banda}{zona}-2"

def exportar_shapefile_zip(gdf, base_name):
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, f"{base_name}.shp")
        if gdf.crs is None: gdf = gdf.set_crs(epsg=4326)
        else: gdf = gdf.to_crs(epsg=4326)
        gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")
        
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(tmpdir):
                zf.write(os.path.join(tmpdir, f), arcname=f)
        buf.seek(0)
        return buf.getvalue()

def obtener_o_descargar_geologia_vectorial(datos_ac, clave_ac):
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_geologia"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_cache_parquet = carpeta_cache / f"GEO_SHP_{clave_ac}.parquet"
    
    if ruta_cache_parquet.exists() and ruta_cache_parquet.stat().st_size > 2000:
        try:
            gdf_c = gpd.read_parquet(ruta_cache_parquet)
            if not gdf_c.empty: return gdf_c
        except Exception: pass

    geom_4326 = datos_ac.geometry
    cx, cy = geom_4326.centroid.x, geom_4326.centroid.y
    clave_carta = calcular_carta_inegi_250k(cy, cx)

    rutas_busqueda = [Path.home() / "Downloads", DIRECTORIO_RAIZ / "data" / "geologia"]
    gdf_inegi = None
    
    for r_dir in rutas_busqueda:
        if not r_dir.exists(): continue
        for z in r_dir.glob("*.zip"):
            try:
                with zipfile.ZipFile(z, 'r') as z_ref:
                    archivos = z_ref.namelist()
                    shps = [a for a in archivos if a.endswith(".shp") and ("lito" in a.lower() or "geo" in a.lower())]
                    if shps:
                        with tempfile.TemporaryDirectory() as tmp_z:
                            z_ref.extractall(tmp_z)
                            for f_shp in Path(tmp_z).rglob("*.shp"):
                                gdf_t = gpd.read_file(f_shp, encoding='latin1')
                                if gdf_t.crs is None: gdf_t = gdf_t.set_crs(epsg=4326)
                                else: gdf_t = gdf_t.to_crs(epsg=4326)
                                gdf_c = gdf_t.clip(geom_4326)
                                if not gdf_c.empty:
                                    gdf_inegi = gdf_c
                                    break
                if gdf_inegi is not None: break
            except Exception: pass
        if gdf_inegi is not None: break

    if gdf_inegi is not None and not gdf_inegi.empty:
        gdf_inegi.to_parquet(ruta_cache_parquet)
        return gdf_inegi
    return None

def renderizar_mapa_3d_puro(ruta_tif, datos_ac, marcadores, exag_terr, rampa_color, mostrar_curvas, mostrar_borde, prof_perforacion, tamano_brocal, mostrar_etiquetas=False, gdf_geologia=None):
    with rasterio.open(ruta_tif) as src:
        z_crudo = np.array(src.read(1), copy=True)
        nodata = src.nodata
        z_acuifero = np.where(z_crudo == nodata, np.nan, z_crudo)
        
        h, w = z_acuifero.shape
        factor = max(1, int(max(h, w) / 220))
        z_display = z_acuifero[::factor, ::factor]
        
        bounds = src.bounds
        x_coords = np.linspace(bounds.left, bounds.right, z_display.shape[1])
        y_coords = np.linspace(bounds.top, bounds.bottom, z_display.shape[0])

    def limpiar_str(txt):
        import unicodedata
        return ''.join(c for c in unicodedata.normalize('NFD', str(txt)) if unicodedata.category(c) != 'Mn').lower()

    es_geologia = "geolog" in limpiar_str(rampa_color)
    dic_leyenda_rocas = {}
    col_roca_usada = "Ninguna"
    
    if es_geologia and gdf_geologia is not None and not gdf_geologia.empty:
        cols_upper = [c.upper() for c in gdf_geologia.columns]
        candidatas = ['CLV_LITO', 'CLV_LITOL', 'TIPO_ROCA', 'LITOLOGIA', 'DESCRIP', 'ROCA', 'UNIDAD']
        col_roca = next((c for c, u in zip(gdf_geologia.columns, cols_upper) if any(k == u for k in candidatas)), None)
        if not col_roca:
            col_roca = next((c for c, u in zip(gdf_geologia.columns, cols_upper) if any(k in u for k in candidatas)), gdf_geologia.columns[0])
            
        col_roca_usada = col_roca
        unidades_unicas = sorted(gdf_geologia[col_roca].dropna().astype(str).unique().tolist())
        
        roca_to_id = {roca: i + 1 for i, roca in enumerate(unidades_unicas)}
        gdf_geologia_temp = gdf_geologia.copy()
        gdf_geologia_temp["ROCA_ID"] = gdf_geologia_temp[col_roca].astype(str).map(roca_to_id).fillna(0)
        
        transform_dem = from_bounds(bounds.left, bounds.bottom, bounds.right, bounds.top, z_display.shape[1], z_display.shape[0])
        formas = [(geom, val) for geom, val in zip(gdf_geologia_temp.geometry, gdf_geologia_temp["ROCA_ID"])]
        
        matriz_litologia = rasterio.features.rasterize(formas, out_shape=z_display.shape, transform=transform_dem, fill=0, dtype=np.float32)
        surface_color_matrix = np.where((matriz_litologia == 0) | np.isnan(z_display), np.nan, matriz_litologia)
        
        paleta_inegi = [
            "#6A1B9A", "#FFB74D", "#F06292", "#81D4FA", "#8D6E63", 
            "#BA68C8", "#4DB6AC", "#E57373", "#AED581", "#90A4AE", 
            "#FFD54F", "#4FC3F7", "#FFF176"
        ]
        
        n_c = max(1, len(unidades_unicas))
        colorscale_final = []
        for i in range(n_c):
            hex_c = paleta_inegi[i % len(paleta_inegi)]
            colorscale_final.append([i / n_c, hex_c])
            colorscale_final.append([(i + 1) / n_c, hex_c])
            dic_leyenda_rocas[unidades_unicas[i]] = hex_c
            
        cmin_val, cmax_val = 1, n_c
        mostrar_barra = False
    else:
        paletas_validas = {
            "earth": "earth", "turbo": "turbo", "viridis": "viridis",
            "spectral": "spectral", "topo": "dense", "cividis": "cividis"
        }
        colorscale_final = paletas_validas.get(str(rampa_color).strip().lower(), "earth")
        surface_color_matrix = z_display
        cmin_val, cmax_val = None, None
        mostrar_barra = True

    fig = go.Figure()
    fig.add_trace(go.Surface(
        x=x_coords, y=y_coords, z=z_display,
        surfacecolor=surface_color_matrix,
        colorscale=colorscale_final,
        cmin=cmin_val, cmax=cmax_val,
        showscale=mostrar_barra,
        colorbar=dict(title="msnm", len=0.6, thickness=15) if mostrar_barra else None,
        contours=dict(z=dict(show=mostrar_curvas, usecolormap=not es_geologia, highlightcolor="#9F2241", project_z=False)),
        lighting=dict(ambient=0.7, diffuse=0.8, roughness=0.5, specular=0.1),
        name="Modelo 3D"
    ))

    # Borde oficial
    if mostrar_borde and datos_ac is not None and hasattr(datos_ac, 'geometry'):
        geom = datos_ac.geometry
        geoms_list = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
        for poly_idx, poly in enumerate(geoms_list):
            coords = list(poly.exterior.coords)
            b_lons, b_lats, b_z = [c[0] for c in coords], [c[1] for c in coords], []
            for x_p, y_p in zip(b_lons, b_lats):
                col_idx = int((x_p - bounds.left) / (bounds.right - bounds.left) * (z_display.shape[1] - 1))
                row_idx = int((bounds.top - y_p) / (bounds.top - bounds.bottom) * (z_display.shape[0] - 1))
                if 0 <= row_idx < z_display.shape[0] and 0 <= col_idx < z_display.shape[1] and not np.isnan(z_display[row_idx, col_idx]):
                    b_z.append(z_display[row_idx, col_idx] + 12)
                else: b_z.append(np.nanmean(z_display) + 12)
            fig.add_trace(go.Scatter3d(x=b_lons, y=b_lats, z=b_z, mode='lines', line=dict(color='#9F2241', width=6), showlegend=(poly_idx == 0), name="Límite Oficial CONAGUA"))

    z_aspect = max(0.005, 0.25 * exag_terr)
    fig.update_layout(
        scene=dict(aspectratio=dict(x=1, y=1, z=z_aspect), camera=dict(eye=dict(x=1.3, y=-1.3, z=0.9))),
        margin=dict(l=0, r=0, b=0, t=10),
        height=720
    )
    st.plotly_chart(fig, use_container_width=True)

    if es_geologia and dic_leyenda_rocas:
        st.markdown(f"<p style='font-size:12px; font-weight:bold; margin-top:5px; color:#691C32;'>LITOLOGÍA INEGI (Columna: <code>{col_roca_usada}</code>):</p>", unsafe_allow_html=True)
        items_html = [f"<div style='display:inline-flex; align-items:center; margin-right:15px; margin-bottom:5px;'><span style='width:14px; height:14px; background-color:{c}; border-radius:3px; display:inline-block; margin-right:6px; border:1px solid #999;'></span><span style='font-size:11px;'>{n}</span></div>" for n, c in dic_leyenda_rocas.items()]
        st.markdown(f"<div style='background-color:#f8f9fa; padding:10px; border-radius:6px; border:1px solid #ddd;'>{''.join(items_html)}</div>", unsafe_allow_html=True)

    if gdf_geologia is not None and not gdf_geologia.empty:
        with st.expander("🔬 Inspeccionar Atributos y Polígonos de Litología", expanded=False):
            st.markdown(f"**Total polígonos recortados:** {len(gdf_geologia)} | **Columna litológica:** `{col_roca_usada}`")
            columnas_mostrar = [c for c in gdf_geologia.columns if c != 'geometry'][:8]
            st.dataframe(gdf_geologia[columnas_mostrar].head(15), use_container_width=True)

# =======================================================
# 🚀 4. EJECUCIÓN PRINCIPAL Y CONTROLES
# =======================================================
col_dem, col_geo = st.columns(2)

with col_dem:
    with st.spinner("Sincronizando topografía de alta resolución (DEM)..."):
        try:
            ruta_dem_local = obtener_o_generar_dem_acuifero(datos_ac, clave_actual)
        except Exception as e_dem:
            st.error(f"Error cargando DEM: {e_dem}")
            ruta_dem_local = None

with col_geo:
    col_g_info, col_g_btn = st.columns([0.75, 0.25])
    with col_g_btn:
        if st.button("🗑️ Limpiar Caché", help="Borra la capa en caché en caso de requerir re-descarga"):
            p_cache = DIRECTORIO_RAIZ / "data" / "cache_geologia" / f"GEO_SHP_{clave_actual}.parquet"
            if p_cache.exists(): p_cache.unlink()
            st.rerun()
    with col_g_info:
        gdf_geo_local = obtener_o_descargar_geologia_vectorial(datos_ac, clave_actual)
        if gdf_geo_local is not None and not gdf_geo_local.empty:
            st.caption(f"✅ Geología vectorial conectada ({len(gdf_geo_local)} polígonos).")
        else:
            st.caption("ℹ️ Sin cobertura geológica local disponible.")

if ruta_dem_local and ruta_dem_local.exists():
    with st.container(border=True):
        st.markdown("<p style='font-size: 13px; font-weight: 700; color: #691C32; margin: 0 0 8px 0;'>🎛️ PARÁMETROS DEL MODELO CONCEPTUAL 3D</p>", unsafe_allow_html=True)
        c_c1, c_c2, c_c3, c_c4 = st.columns(4)
        
        exag_terr = c_c1.slider("⛰️ Exageración Relieve", min_value=0.0, max_value=3.0, value=1.0, step=0.2)
        prof_perforacion = c_c2.slider("⛏️ Prof. Perforación (m)", min_value=10, max_value=500, value=150, step=5)
        tamano_brocal = c_c3.slider("🔘 Tamaño de Ademe (px)", min_value=2, max_value=20, value=7, step=1)
        
        opciones_rampas = ["Geología Oficial (SGM/INEGI)", "Earth", "Turbo", "Viridis", "Spectral", "Topo", "Cividis"]
        rampa_color = c_c4.selectbox("🎨 Mapeo Superficial / Textura", opciones_rampas, index=0)
        
        c_tog1, c_tog2, c_tog3 = st.columns(3)
        mostrar_borde = c_tog1.toggle("🛡️ Mostrar Borde Oficial", value=True)
        mostrar_curvas = c_tog2.toggle("📏 Ver Curvas de Nivel 3D", value=True)
        mostrar_etiquetas = c_tog3.toggle("🏷️ Ver Etiquetas Fijas", value=False)

    marcadores = st.session_state.get("lista_marcadores", [])

    renderizar_mapa_3d_puro(
        ruta_dem_local, datos_ac, marcadores, exag_terr, rampa_color,
        mostrar_curvas, mostrar_borde, prof_perforacion, tamano_brocal,
        mostrar_etiquetas, gdf_geologia=gdf_geo_local
    )

    # Botones de exportación SIG
    cd1, cd2 = st.columns(2)
    with cd1:
        with open(ruta_dem_local, "rb") as f_dem:
            st.download_button(
                label="💾 Descargar DEM Recortado (.tif)",
                data=f_dem,
                file_name=f"DEM_Acuifero_{clave_actual}.tif",
                mime="image/tiff",
                use_container_width=True
            )
    with cd2:
        if gdf_geo_local is not None and not gdf_geo_local.empty:
            zip_shp_bytes = exportar_shapefile_zip(gdf_geo_local, f"Geologia_{clave_actual}")
            st.download_button(
                label="📦 Descargar Geología Shapefile (.zip)",
                data=zip_shp_bytes,
                file_name=f"Geologia_Shapefile_{clave_actual}.zip",
                mime="application/zip",
                use_container_width=True
            )
else:
    st.warning("No se pudo generar el modelo digital del terreno para este acuífero.")