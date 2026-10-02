# -*- coding: utf-8 -*-
"""
Módulo de Evaluación y Monitoreo Geohidrológico (Nivel Enterprise)
Diagnóstico físico con Kriging Ordinario, Variogramas, Isopiezas, Vectores de Flujo y Forecasting.
Desacoplamiento de modelo matemático vs renderizado para interactividad instantánea (<40 ms).
Exportación exclusiva en formatos SIG: GeoTIFF (.tif), Shapefile (.zip) y GeoJSON (.geojson).
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import folium
from folium.plugins import HeatMap, Fullscreen
from streamlit_folium import st_folium
import unicodedata
import re
import io
import os
import json
import zipfile
import tempfile
import base64
import branca.colormap as cm
from branca.element import MacroElement
from jinja2 import Template

# --- MODO SERGURO PARA MATPLOTLIB EN LA NUBE ---
import matplotlib
matplotlib.use('Agg')

try:
    import geopandas as gpd
    from shapely.geometry import LineString, Point, Polygon, MultiPolygon, shape
    GEOPANDAS_INSTALADO = True
except ImportError:
    GEOPANDAS_INSTALADO = False

# Importaciones del Core
from utils.styles import inyectar_css_oficial, banner_institucional
from core.data_loader import CARPETA_DATOS, cargar_catalogo, cargar_datos_maestros

# =======================================================
# 🎨 0. CONFIGURACIÓN E INYECCIÓN DE ESTILOS
# =======================================================
st.set_page_config(layout="wide")
inyectar_css_oficial()
banner_institucional()

st.subheader("📉 Red de Monitoreo Geohidrológico")
st.caption("Validación Física: Evaluación espacial, temporal, modelación geostadística de flujo y proyectiva.")

# =======================================================
# 🔍 1. SELECTOR Y SINCRONIZACIÓN DE SESIÓN GLOBAL
# =======================================================
clave_actual = st.session_state.get("clave_global")
nombre_actual = st.session_state.get("nombre_global")
area_actual = st.session_state.get("area_total_global", 0)

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
                if clave_sel != st.session_state.get("clave_global"):
                    datos_acu = df_est[df_est["CLAVE_SIGM"] == clave_sel].iloc[0]
                    st.session_state["clave_global"] = str(datos_acu["CLAVE_SIGM"])
                    st.session_state["nombre_global"] = str(datos_acu["ACUÍFERO"])
                    st.session_state["area_total_global"] = round(float(datos_acu["AREA_KM2"]), 1)
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
# 💾 2. CARGA Y TRANSFORMACIÓN DE BASE DE DATOS
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
    id_vars_seguras = [c for c in [col_pozo, col_edo, col_ac, col_elev, col_lat, col_lon] if c in df.columns]
    val_vars_seguras = [c for c in columnas_anios_limpias if c in df.columns]
    
    df_largo = df.melt(id_vars=id_vars_seguras, value_vars=val_vars_seguras, var_name='Año', value_name='Profundidad_NE')
    
    df_largo = df_largo.rename(columns={
        col_pozo: 'Pozo', col_edo: 'Estado', col_ac: 'Acuifero',
        col_elev: 'Elev.Terr', col_lat: 'Latitud', col_lon: 'Longitud'
    })
    
    df_largo['Profundidad_NE'] = pd.to_numeric(df_largo['Profundidad_NE'], errors='coerce')
    df_largo['Año'] = pd.to_numeric(df_largo['Año'], errors='coerce')
    df_largo['Elev.Terr'] = pd.to_numeric(df_largo['Elev.Terr'], errors='coerce')
    df_largo['Carga_Hidraulica'] = df_largo['Elev.Terr'] - df_largo['Profundidad_NE']
    
    return df, df_largo, lista_acuiferos_crudos

df_crudo, df_largo, lista_nombres_crudos = cargar_piezometria()

if df_crudo is None or df_largo is None:
    st.error("⚠️ No se encontró ningún archivo de piezometría en la carpeta de datos.")
    st.stop()

def normalizar(texto):
    if pd.isna(texto) or not texto: return ""
    t = str(texto).upper().strip()
    t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    t = re.sub(r'[^A-Z0-9\s]', '', t)
    return re.sub(r'\s+', ' ', t)

nombre_limpio_global = normalizar(nombre_actual)
df_largo['Ac_Norm'] = df_largo['Acuifero'].apply(normalizar)
df_ac_completo = df_largo[df_largo['Ac_Norm'].apply(lambda x: x in nombre_limpio_global or nombre_limpio_global in x)].copy()

if df_ac_completo.empty:
    st.error(f"❌ El acuífero **{nombre_actual}** no cuenta con registros en la base de monitoreo.")
    st.stop()

df_ac = df_ac_completo.dropna(subset=['Profundidad_NE', 'Año']).copy()
if df_ac.empty:
    st.warning(f"⚠️ El acuífero **{nombre_actual}** existe en la base, pero todas sus mediciones de profundidad están en blanco.")
    st.stop()

pozos_disponibles = sorted(df_ac['Pozo'].astype(str).unique().tolist())

# =======================================================
# 🗺️ 2.1 POLÍGONO OFICIAL (DESDE Acuiferos_Dashboard_V4)
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

# =======================================================
# ⚙️ 3. MOTOR GEOSTADÍSTICO MATEMÁTICO (DESACOPLADO)
# =======================================================
@st.cache_data(show_spinner=False)
def resolver_malla_kriging(df_puntos, variable, modelo_param, bounds_limite=None, resolucion=150):
    try:
        from pykrige.ok import OrdinaryKriging
    except ImportError:
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
    import matplotlib.pyplot as plt
    min_y, min_x = bounds[0]
    max_y, max_x = bounds[1]
    height, width = Z_masked.shape
    Z_flipped = np.flipud(Z_masked).astype(np.float32)
    data_write = np.nan_to_num(Z_flipped, nan=-9999.0)

    try:
        import rasterio
        from rasterio.transform import from_bounds
        from rasterio.io import MemoryFile
        
        transform = from_bounds(min_x, min_y, max_x, max_y, width, height)
        with MemoryFile() as memfile:
            with memfile.open(
                driver='GTiff', height=height, width=width, count=1,
                dtype='float32', crs='EPSG:4326', transform=transform, nodata=-9999.0
            ) as dst:
                dst.write(data_write, 1)
            return memfile.read()
    except ImportError:
        buf = io.BytesIO()
        plt.imsave(buf, Z_flipped, cmap='Blues', format='tiff')
        return buf.getvalue()

# =======================================================
# 🎨 3.1 RENDERIZADO VISUAL REACTIVO (<30 ms)
# =======================================================
def render_imagen_kriging(X, Y, Z_masked, bounds):
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
# 📊 4. EJE 1: SALUD E INVENTARIO DE LA RED
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
# 🛠️ 5. INTERFAZ DE TABS
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
        c_ctrl, c_map = st.columns([0.34, 0.66])
        
        with c_ctrl:
            with st.container(border=True):
                st.markdown("<h4 style='color:#691C32; margin:0 0 10px 0; font-size:15px;'>⚙️ Configuración Geostadística</h4>", unsafe_allow_html=True)
                var_interp = st.selectbox("1. Variable a Modelar", ["Carga Hidráulica (msnm) [Recomendado para flujo]", "Profundidad del Nivel (m)"])
                var_real = 'Carga_Hidraulica' if "Carga" in var_interp else 'Profundidad_NE'
                
                param = st.selectbox("2. Modelo de Variograma", [
                    "Lineal (no nugget)", "Raíz Cuadrada (square root)", "Logarítmico", 
                    "Stable (0 < k < 2)", "Cúbico", "Esférico (spherical)", "Exponencial (exponential)", "Gaussiano (gaussian)"
                ])
                
            df_ultimo = df_ac.loc[df_ac.groupby('Pozo')['Año'].idxmax()].dropna(subset=[var_real, 'Latitud', 'Longitud']).copy()

            # 🗺️ Gestión del Polígono Oficial y Delimitación Espacial
            geom_activa = poligono_oficial_geom
            with st.container(border=True):
                st.markdown("<h4 style='color:#691C32; margin:0 0 10px 0; font-size:15px;'>📍 Delimitación Geográfica</h4>", unsafe_allow_html=True)
                
                if geom_activa is not None:
                    st.success(f"✅ Polígono oficial de **{nombre_actual}** cargado automáticamente desde el Geovisor.")
                else:
                    st.info("ℹ️ No se detectó polígono oficial en el catálogo maestro.")

                with st.expander("📁 Cargar Polígono Alternativo (Shapefile o GeoJSON)", expanded=False):
                    up_geom = st.file_uploader("Subir archivo (.geojson o .zip con Shapefile):", type=['geojson', 'json', 'zip'], key="up_poly_piezo")
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
                            st.success("✅ Polígono personalizado cargado correctamente.")
                        except Exception as err:
                            st.error(f"Error procesando archivo: {err}")

                opciones_delimitacion = ["Pozos de Monitoreo (Envolvente Convexa)"]
                if geom_activa is not None:
                    opciones_delimitacion.insert(0, "Polígono Oficial del Acuífero")

                modo_delimitacion = st.radio(
                    "3. Delimitar modelo geohidrológico por:", 
                    opciones_delimitacion, 
                    index=0,
                    help="Si eliges el polígono oficial, el modelo espacial abarcará y recortará exactamente en la frontera del acuífero."
                )

            # Cálculo de rango preliminar para sliders
            if len(df_ultimo) >= 4:
                rango_estimado = max(1.0, float(df_ultimo[var_real].max() - df_ultimo[var_real].min()))
                def_equidistancia = max(0.5, round(rango_estimado / 10.0, 1))
                if def_equidistancia >= 5: def_equidistancia = round(def_equidistancia / 5.0) * 5.0
            else:
                rango_estimado = 50.0
                def_equidistancia = 5.0

            # 🎛️ Controladores de visualización reactivos (<30 ms)
            with st.container(border=True):
                st.markdown("<h4 style='color:#691C32; margin:0 0 10px 0; font-size:15px;'>🎛️ Ajustes de Visualización</h4>", unsafe_allow_html=True)
                
                opacidad_kriging = st.slider("Transparencia Capa Kriging (Opacidad):", 0.0, 1.0, 0.55, 0.05)
                intervalo_iso = st.slider(
                    "Equidistancia de Isolíneas (m):", 
                    min_value=max(0.5, round(rango_estimado / 40.0, 1)), 
                    max_value=max(2.0, round(rango_estimado / 2.0, 1)), 
                    value=float(min(max(2.0, round(rango_estimado / 2.0, 1)), def_equidistancia)), 
                    step=0.5 if rango_estimado < 20 else 1.0
                )
                densidad_flujo = st.slider("Densidad de Vectores de Flujo:", 8, 36, 20, 2)
            
            ph_variograma = st.empty()

        with c_map:
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

                        # ⚡ Renderizado Desacoplado (Ultrarrápido)
                        img_kriging, vmin, vmax = render_imagen_kriging(X, Y, Z_masked, bounds)
                        img_isolineas, geojson_iso, shp_iso_zip = render_imagen_isolineas(X, Y, Z_masked, bounds, intervalo_iso, var_real)
                        img_flujo, geojson_flujo, shp_flujo_zip = render_imagen_vectores(X, Y, Z, grid_x, grid_y, bounds, var_real, densidad_flujo, inside_mask)

                        # Preparación de datos de Kriging para exportación
                        geotiff_bytes = generar_geotiff_bytes(Z_masked, bounds)
                        mask_val = ~np.isnan(Z_masked)
                        df_grid = pd.DataFrame({"LONGITUD": np.round(X[mask_val], 6), "LATITUD": np.round(Y[mask_val], 6), "VALOR": np.round(Z_masked[mask_val], 3)})
                        geojson_krig = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["LONGITUD"], r["LATITUD"]]}, "properties": {"VALOR": r["VALOR"], "VARIABLE": var_real}} for _, r in df_grid.iterrows()]}, indent=2).encode('utf-8')
                        shp_krig_zip = empaquetar_shapefile_zip(gpd.GeoDataFrame(df_grid, geometry=[Point(xy) for xy in zip(df_grid["LONGITUD"], df_grid["LATITUD"])], crs="EPSG:4326"), f"kriging_{clave_actual}") if (GEOPANDAS_INSTALADO and not df_grid.empty) else None

                        # Semivariograma
                        with ph_variograma.container():
                            with st.container(border=True):
                                st.markdown("<h5 style='color:#691C32; margin:0 0 8px 0;'>📈 Semivariograma Experimental vs Teórico</h5>", unsafe_allow_html=True)
                                fig_var = go.Figure()
                                fig_var.add_trace(go.Scatter(x=exp_lags, y=exp_semi, mode='markers', name='Experimental (Campo)', marker=dict(color='#9f2241', size=7)))
                                fig_var.add_trace(go.Scatter(x=smooth_lags, y=theo_semi, mode='lines', name='Ajuste Teórico', line=dict(color='#285c4d', width=2)))
                                fig_var.update_layout(
                                    xaxis_title="Lag (Distancia)", yaxis_title="Semivarianza",
                                    height=220, margin=dict(t=10, b=10, l=10, r=10), plot_bgcolor='rgba(0,0,0,0)',
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
                        
                        centro_lat, centro_lon = df_ultimo['Latitud'].mean(), df_ultimo['Longitud'].mean()
                        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=10, tiles=None, control_scale=False, zoom_control=True)
                        m.fit_bounds(bounds)

                        # Estilos Leaflet
                        css_controles = """
                        <style>
                            .leaflet-top.leaflet-left { left: 0 !important; top: 0 !important; }
                            .leaflet-control-zoom { margin-top: 12px !important; margin-left: 12px !important; }
                            .leaflet-control-layers { margin-top: 10px !important; margin-right: 10px !important; z-index: 2000 !important; }
                            .leaflet-control-layers-expanded { z-index: 2500 !important; box-shadow: 0 4px 18px rgba(0,0,0,0.25) !important; }
                            .gradient-widget-control { position: absolute !important; top: 125px !important; right: 10px !important; z-index: 1000 !important; pointer-events: auto !important; }
                            .leaflet-open-gradient-btn { background: #691C32 !important; color: #ffffff !important; width: 38px !important; height: 38px !important; border-radius: 50% !important; line-height: 36px !important; text-align: center !important; cursor: pointer !important; box-shadow: 0 3px 10px rgba(105, 28, 50, 0.35) !important; font-size: 17px !important; border: 1.5px solid #BC955C !important; display: flex; align-items: center !important; justify-content: center !important; transition: all 0.2s ease !important; }
                            .leaflet-open-gradient-btn:hover { background: #4A1424 !important; transform: scale(1.08) !important; }
                            .gradient-docked-panel { background: #ffffff !important; width: 280px !important; border-radius: 8px !important; overflow: hidden !important; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25) !important; border-top: 4px solid #691C32 !important; border: 1px solid #E2D9C8 !important; font-family: 'Segoe UI', Arial, sans-serif !important; display: none; }
                            .docked-gradient-header { background: #691C32 !important; color: #ffffff !important; padding: 9px 12px !important; position: relative !important; }
                            .docked-gradient-title { font-size: 13px !important; font-weight: 700 !important; color: #ffffff !important; padding-right: 22px !important; }
                            .docked-gradient-sub { font-size: 10px !important; color: #D4C19C !important; margin-top: 3px !important; text-transform: uppercase !important; }
                            .docked-gradient-close { position: absolute !important; top: 6px !important; right: 10px !important; color: #ffffff !important; cursor: pointer !important; font-size: 20px !important; }
                            .docked-gradient-close:hover { color: #BC955C !important; }
                            .docked-gradient-body { padding: 12px 14px !important; background: #ffffff !important; }
                            .info.legend-piezo { background: white; padding: 12px; border: 1px solid #dcdde1; border-radius: 6px; font-size: 12px; line-height: 18px; color: #333; box-shadow: 0 4px 10px rgba(0,0,0,0.15); margin-bottom: 15px !important; margin-left: 15px !important; font-family: 'Segoe UI', sans-serif; }
                            .info.legend-piezo b { font-size: 13.5px; display: block; margin-bottom: 8px; color: #691C32; border-bottom: 1px solid #eee; padding-bottom: 4px;}
                            .info.legend-piezo i.circulo { width: 12px; height: 12px; float: left; margin-right: 8px; margin-top: 2px; border: 1px solid #fff; border-radius: 50%; }
                            .info.legend-piezo i.flecha { color:#004085; font-weight:bold; font-size:16px; float:left; margin-right:8px; line-height: 14px; font-style: normal; }
                        </style>
                        """
                        m.get_root().html.add_child(folium.Element(css_controles))

                        # Mapas Base
                        folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Neutral (defecto)').add_to(m)
                        folium.TileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', attr='OpenStreetMap', name='OpenStreetMap', show=False).add_to(m)
                        folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Estándar (ESRI)', show=False).add_to(m)
                        folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satélite (ESRI)', show=False).add_to(m)
                        folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Topográfico (ESRI)', show=False).add_to(m)
                        folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Terreno (ESRI)', show=False).add_to(m)
                        folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Océanos (ESRI)', show=False).add_to(m)
                        folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Gris Oscuro (ESRI)', show=False).add_to(m)
                        folium.TileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google', name='Google Satelital (Transparencia)', show=False).add_to(m)

                        # Polígono Oficial
                        if geom_activa is not None:
                            capa_poligono = folium.FeatureGroup(name="🗺️ Polígono Oficial del Acuífero", show=True)
                            folium.GeoJson(
                                geom_activa.__geo_interface__,
                                style_function=lambda x: {
                                    'fillColor': '#BC955C', 'color': '#691C32',
                                    'weight': 2.5, 'fillOpacity': 0.10, 'dashArray': '4, 4'
                                },
                                tooltip=f"<b>Acuífero:</b> {nombre_actual} ({clave_actual})"
                            ).add_to(capa_poligono)
                            capa_poligono.add_to(m)

                        # Capa Calor
                        capa_calor = folium.FeatureGroup(name="🔥 Mapa de Calor (Zonas Críticas)", show=False)
                        heat_data = [[row['Latitud'], row['Longitud'], row['Profundidad_NE']] for _, row in df_ultimo.iterrows()]
                        HeatMap(heat_data, radius=35, blur=25, min_opacity=0.4, gradient={0.2: '#285c4d', 0.6: '#b38e5d', 1.0: '#9f2241'}).add_to(capa_calor)
                        capa_calor.add_to(m)
                        
                        # Capa Kriging con opacidad directa en Leaflet
                        capa_kriging = folium.FeatureGroup(name="🌊 Superficie Piezométrica (Kriging)", show=True)
                        img_krig_b64 = base64.b64encode(img_kriging).decode('utf-8')
                        folium.raster_layers.ImageOverlay(
                            image=f"data:image/png;base64,{img_krig_b64}", 
                            bounds=bounds, 
                            opacity=opacidad_kriging
                        ).add_to(capa_kriging)
                        capa_kriging.add_to(m)

                        # Capa Isolíneas
                        capa_isolineas = folium.FeatureGroup(name="📏 Isolíneas / Isopiezas (Cotas)", show=True)
                        img_iso_b64 = base64.b64encode(img_isolineas).decode('utf-8')
                        folium.raster_layers.ImageOverlay(
                            image=f"data:image/png;base64,{img_iso_b64}", 
                            bounds=bounds, 
                            opacity=0.95
                        ).add_to(capa_isolineas)
                        capa_isolineas.add_to(m)

                        # Capa Flujo
                        capa_flujo = folium.FeatureGroup(name="🧭 Vectores de Dirección de Flujo", show=True)
                        img_flujo_b64 = base64.b64encode(img_flujo).decode('utf-8')
                        folium.raster_layers.ImageOverlay(
                            image=f"data:image/png;base64,{img_flujo_b64}", 
                            bounds=bounds, 
                            opacity=0.90
                        ).add_to(capa_flujo)
                        capa_flujo.add_to(m)
                        
                        # Capa Pozos
                        capa_pozos = folium.FeatureGroup(name="📍 Red Piezométrica (Pozos)", show=True)
                        if hull_pts is not None and modo_delimitacion != "Polígono Oficial del Acuífero":
                            hull_folium = [[float(pt[1]), float(pt[0])] for pt in hull_pts]
                            hull_folium.append(hull_folium[0])
                            folium.PolyLine(
                                locations=hull_folium, color='#691C32', weight=2, dash_array='6, 6',
                                tooltip=f"Envolvente Convexa ({len(df_ultimo)} pozos)"
                            ).add_to(capa_pozos)

                        for _, row in df_ultimo.iterrows():
                            df_hist = df_ac[df_ac['Pozo'].astype(str) == str(row['Pozo'])]
                            if len(df_hist) >= 2:
                                z = np.polyfit(df_hist['Año'], df_hist['Profundidad_NE'], 1)
                                color_punto = "#9f2241" if z[0] > 0.1 else ("#285c4d" if z[0] < -0.1 else "#b38e5d")
                            else: color_punto = "#9e9d9e"
                                
                            folium.CircleMarker(
                                location=[row['Latitud'], row['Longitud']],
                                radius=6, color='#111', weight=1, fill=True, fill_color=color_punto, fill_opacity=1,
                                tooltip=f"<b>Pozo {row['Pozo']}</b><br>Valor Modelo: {row[var_real]:.2f}<br>Año Medición: {row['Año']}"
                            ).add_to(capa_pozos)
                        capa_pozos.add_to(m)
                        
                        # Gradiente Piezométrico
                        vmid = (vmin + vmax) / 2.0
                        vmin_fmt, vmid_fmt, vmax_fmt = f"{vmin:.1f}", f"{vmid:.1f}", f"{vmax:.1f}"
                        var_titulo_limpio = "Carga Hidráulica (msnm)" if "Carga" in var_interp else "Profundidad del Nivel (m)"

                        class ControlesVisualesMapa(MacroElement):
                            def __init__(self):
                                super().__init__()
                                self._template = Template(f"""
                                {{% macro script(this, kwargs) %}}
                                L.control.scale({{position: 'bottomright', metric: true, imperial: true}}).addTo({{{{this._parent.get_name()}}}});

                                var legend = L.control({{position: 'bottomleft'}});
                                legend.onAdd = function (map) {{
                                    var div = L.DomUtil.create('div', 'info legend-piezo');
                                    div.innerHTML = `
                                    <b>Simbología</b>
                                    <i class="circulo" style="background:#9f2241;"></i> Pozo Abatiéndose<br>
                                    <i class="circulo" style="background:#285c4d;"></i> Pozo Recuperando<br>
                                    <i class="circulo" style="background:#b38e5d;"></i> Pozo Estable<br>
                                    <hr style="margin: 8px 0; border: 0; border-top: 1px solid #eee;">
                                    <div style="display:flex; align-items:center; margin-top:2px;">
                                        <i class="flecha">&rarr;</i> <span>Vectores de Flujo</span>
                                    </div>
                                    `;
                                    return div;
                                }};
                                legend.addTo({{{{this._parent.get_name()}}}});

                                var gradControl = L.control({{position: 'topright'}});
                                gradControl.onAdd = function (map) {{
                                    var div = L.DomUtil.create('div', 'gradient-widget-control');
                                    L.DomEvent.disableClickPropagation(div);
                                    L.DomEvent.disableScrollPropagation(div);
                                    
                                    div.innerHTML = `
                                    <div id="btn-open-gradient" class="leaflet-open-gradient-btn" title="Mostrar Gradiente Piezométrico" onclick="
                                        document.getElementById('gradient-panel-container').style.display = 'block';
                                        document.getElementById('btn-open-gradient').style.display = 'none';
                                    ">
                                        ☰
                                    </div>

                                    <div id="gradient-panel-container" class="gradient-docked-panel">
                                        <div class="docked-gradient-header">
                                            <span class="docked-gradient-close" onclick="
                                                document.getElementById('gradient-panel-container').style.display = 'none';
                                                document.getElementById('btn-open-gradient').style.display = 'flex';
                                            " title="Ocultar">&times;</span>
                                            <span class="docked-gradient-title">Gradiente Piezométrico</span>
                                            <span class="docked-gradient-sub">{var_titulo_limpio}</span>
                                        </div>
                                        <div class="docked-gradient-body">
                                            <div style="height: 10px; border-radius: 4px; background: linear-gradient(to right, #eff3ff, #bdd7e7, #6baed6, #3182bd, #08519c); border: 1px solid rgba(0,0,0,0.18); margin-bottom: 6px;"></div>
                                            <div style="display: flex; justify-content: space-between; font-size: 10px; color: #333333; font-weight: 600;">
                                                <span>{vmin_fmt}</span>
                                                <span>{vmid_fmt}</span>
                                                <span>{vmax_fmt}</span>
                                            </div>
                                        </div>
                                    </div>
                                    `;
                                    return div;
                                }};
                                gradControl.addTo({{{{this._parent.get_name()}}}});
                                {{% endmacro %}}
                                """)
                        m.add_child(ControlesVisualesMapa())
                        
                        Fullscreen(position='topright', title='Pantalla completa', title_cancel='Salir de pantalla completa', force_separate_button=True).add_to(m)
                        folium.LayerControl(position='topright', collapsed=True).add_to(m)
                        
                        st_folium(m, height=720, use_container_width=True, returned_objects=[])

                        # =======================================================
                        # 📥 DESCARGA DIRECTA SIG (GEOTIFF, SHAPEFILE, GEOJSON)
                        # =======================================================
                        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                        with st.expander("📥 Descargar Capas en Formatos SIG (GeoTIFF, Shapefile, GeoJSON)", expanded=True):
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

# --- EJE 2: HIDROGRAMAS INTELIGENTES ---
with tab_hidrograma:
    @st.fragment
    def renderizar_pestaña_hidrograma():
        st.write("Selecciona un pozo de la red de monitoreo para analizar su comportamiento temporal y su tasa de abatimiento matemática.")
        pozo_sel = st.selectbox("🎯 Filtrar por Pozo de Monitoreo:", pozos_disponibles)
        df_pozo = df_ac[df_ac['Pozo'].astype(str) == str(pozo_sel)].sort_values(by='Año')
        
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
            df_hist = df_ac[df_ac['Pozo'].astype(str) == str(pozo)].sort_values(by='Año')
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
                df_pozo_demo = df_ac[df_ac['Pozo'].astype(str) == pozo_demo].sort_values(by='Año')
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
