# -*- coding: utf-8 -*-
"""
Geovisor de Vulnerabilidad e Hidráulica (Arquitectura Híbrida Python + MapLibre GL JS)
- Mapa a pantalla completa (Full Width & Full Height ajustado).
- Mallado adaptativo nativo con estilo clásico (Coordenadas pegadas a los bordes).
- Selector de capas estilo Leaflet clásico (Hover expansible).
- Botón de Pantalla Completa y brújula ordenados a la derecha.
- Panel principal (Top-Left) con z-index supremo sobre la leyenda.
- Panel lateral acoplado (Docked Inspector) con colores institucionales oficiales.
"""

import streamlit as st
import streamlit.components.v1 as components
import geopandas as gpd
import pandas as pd
from shapely import wkt
import json
import logging

# Importaciones de tu core
from utils.styles import inyectar_css_oficial, banner_institucional
from core.data_loader import CARPETA_DATOS
from core.geo_web import asegurar_vulnerabilidad_web

logger = logging.getLogger(__name__)

# ==========================================
# 1. CONFIGURACIÓN GLOBALES
# ==========================================
st.set_page_config(layout="wide")
inyectar_css_oficial()
banner_institucional()

# CSS para forzar a Streamlit a usar todo el espacio disponible (Ajustado a 74vh)
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            padding-left: 0rem;
            padding-right: 0rem;
            max-width: 100%;
        }
        iframe {
            width: 100%;
            height: 74vh !important;
            border: none;
        }
    </style>
""", unsafe_allow_html=True)

st.subheader("🌍 Geovisor de Vulnerabilidad e Hidráulica")

# ==========================================
# 2. PREPARACIÓN DE DATOS EN PYTHON (BACKEND)
# ==========================================
def _json_seguro(texto):
    return texto.replace("</", "<\\/").replace("<!--", "<\\!--")

@st.cache_resource(show_spinner="Optimizando y consolidando datos espaciales...")
def preparar_datos_para_js():
    json_vuln = None
    try:
        json_vuln = asegurar_vulnerabilidad_web(CARPETA_DATOS).read_text(encoding="utf-8")
        gdf_vuln = gpd.GeoDataFrame()
    except Exception:
        logger.exception("No se pudo generar el GeoJSON liviano de vulnerabilidad; se usa la ruta lenta")
        ruta_vuln = CARPETA_DATOS / "Vulnerabilidad_Nacional.parquet"
        gdf_vuln = gpd.read_parquet(ruta_vuln) if ruta_vuln.exists() else gpd.GeoDataFrame()
    
    ruta_limites = CARPETA_DATOS / "limites_acuiferos_mx.geojson"
    ruta_hydro = CARPETA_DATOS / "propiedades_hidraulicas.json"
    gdf_hydro = gpd.read_file(ruta_limites) if ruta_limites.exists() else gpd.GeoDataFrame()
    
    if not gdf_hydro.empty and ruta_hydro.exists():
        with open(ruta_hydro, 'r', encoding='utf-8') as f:
            hydro_json = json.load(f).get('data', {})
        df_props = pd.DataFrame.from_dict(hydro_json, orient='index')
        df_props.index.name = 'CLAVE_NORMALIZADA'
        gdf_hydro['CLAVE_NORMALIZADA'] = gdf_hydro['CLAVE_ACUI'].astype(str).str.zfill(4)
        gdf_hydro = gdf_hydro.merge(df_props, on='CLAVE_NORMALIZADA', how='left')

    ruta_pozos = CARPETA_DATOS / "pozos.geojson"
    gdf_pozos = gpd.read_file(ruta_pozos) if ruta_pozos.exists() else gpd.GeoDataFrame()

    ruta_costa1 = CARPETA_DATOS / "Linea_Costa_1km.parquet"
    ruta_costa10 = CARPETA_DATOS / "Linea_Costa_10km.parquet"
    gdf_costa1 = gpd.read_parquet(ruta_costa1) if ruta_costa1.exists() else gpd.GeoDataFrame()
    gdf_costa10 = gpd.read_parquet(ruta_costa10) if ruta_costa10.exists() else gpd.GeoDataFrame()

    def truncar_coordenadas(geom):
        if geom is None: return None
        return wkt.loads(wkt.dumps(geom, rounding_precision=5))

    if not gdf_vuln.empty:
        gdf_vuln['geometry'] = gdf_vuln['geometry'].apply(truncar_coordenadas)
        cols = [c for c in ['CLAVE_ACUI', 'NOM_ACUIF', 'VULNERABIL', 'geometry'] if c in gdf_vuln.columns]
        json_vuln = gdf_vuln[cols].to_json()
    elif json_vuln is None: json_vuln = "{}"

    if not gdf_hydro.empty:
        gdf_hydro['geometry'] = gdf_hydro['geometry'].apply(truncar_coordenadas)
        cols = [c for c in ['CLAVE_ACUI', 'NOM_ACUIF', 'transmisividad_media', 'conductividad_media', 'coef_almacenamiento_medio', 'profundidad_media', 'pozos_registrados', 'geometry'] if c in gdf_hydro.columns]
        json_hydro = gdf_hydro[cols].to_json()
    else: json_hydro = "{}"

    if not gdf_costa1.empty:
        gdf_costa1['geometry'] = gdf_costa1['geometry'].apply(truncar_coordenadas)
        json_costa1 = gdf_costa1[['geometry']].to_json()
    else: json_costa1 = "{}"
        
    if not gdf_costa10.empty:
        gdf_costa10['geometry'] = gdf_costa10['geometry'].apply(truncar_coordenadas)
        json_costa10 = gdf_costa10[['geometry']].to_json()
    else: json_costa10 = "{}"

    json_pozos = gdf_pozos.to_json() if not gdf_pozos.empty else "{}"

    return tuple(_json_seguro(t) for t in (json_vuln, json_hydro, json_pozos, json_costa1, json_costa10))

json_vuln, json_hydro, json_pozos, json_costa1, json_costa10 = preparar_datos_para_js()

# ==========================================
# 3. INYECCIÓN DEL FRONTEND (MAPLIBRE JS)
# ==========================================
html_code = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
    <style>
        html, body {{ margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        #map {{ width: 100%; height: 100%; background-color: #e5e5e5; }}
        
        /* =========================================================================
           OVERRIDES MAPLIBRE (POSICIONAMIENTO Y Z-INDEX)
           ========================================================================= */
        .maplibregl-control-container {{ pointer-events: none; }}
        .maplibregl-ctrl-top-right, .maplibregl-ctrl-top-left, 
        .maplibregl-ctrl-bottom-right, .maplibregl-ctrl-bottom-left {{
            display: flex !important; pointer-events: none !important; padding: 0 !important;
        }}
        .maplibregl-ctrl {{ pointer-events: auto !important; float: none !important; clear: none !important; margin: 0 !important; }}

        /* TOP-LEFT (Panel Principal -> Supremo Z-Index para que cubra la leyenda) */
        .maplibregl-ctrl-top-left {{
            flex-direction: column !important; align-items: flex-start !important;
            z-index: 9999 !important;
        }}
        .maplibregl-ctrl-top-left .maplibregl-ctrl {{ margin: 10px 0 0 10px !important; }}

        /* TOP-RIGHT (Pantalla completa -> Capas -> Brújula -> Panel Lateral) */
        .maplibregl-ctrl-top-right {{
            flex-direction: column !important; align-items: flex-end !important;
            z-index: 9000 !important;
        }}
        .maplibregl-ctrl-top-right .maplibregl-ctrl {{ margin: 10px 10px 0 0 !important; }}
        #custom-fs-container {{ order: 1; }}
        #custom-layer-container {{ order: 2; }}
        .maplibregl-ctrl-top-right .maplibregl-ctrl-group {{ order: 3 !important; box-shadow: 0 1px 5px rgba(0,0,0,0.65) !important; }}
        #docked-panel-container {{ order: 4; }}

        /* BOTTOM-RIGHT (Imprimir -> Escala -> Logo -> Atribución visible) */
        .maplibregl-ctrl-bottom-right {{ flex-direction: column !important; align-items: flex-end !important; justify-content: flex-end !important; z-index: 8000 !important; }}
        .maplibregl-ctrl-bottom-right .maplibregl-ctrl {{ margin: 0 10px 0 0 !important; }}
        #print-ctrl-container {{ order: 1; margin-bottom: 8px !important; }}
        .maplibregl-ctrl-scale {{ order: 2; margin-bottom: 4px !important; margin-right: 6px !important; }}
        #logo-ctrl-container {{ order: 3; margin-bottom: 4px !important; }}
        .maplibregl-ctrl-attrib {{ order: 4; margin: 0 !important; background: rgba(255,255,255,0.85) !important; font-size: 12px !important; padding: 2px 6px !important; border-radius: 4px 0 0 0; }}

        /* BOTTOM-LEFT (Leyenda debajo del panel) */
        .maplibregl-ctrl-bottom-left {{ flex-direction: column !important; align-items: flex-start !important; justify-content: flex-end !important; z-index: 5000 !important; }}
        .maplibregl-ctrl-bottom-left .maplibregl-ctrl {{ margin: 0 0 12px 12px !important; }}

        /* =========================================================================
           ESTILOS COMPONENTES VISUALES
           ========================================================================= */

        /* 1. Botón Pantalla Completa */
        .custom-fullscreen-btn {{
            width: 32px; height: 32px; background: #ffffff; border-radius: 4px; cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 5px rgba(0,0,0,0.65);
        }}
        .custom-fullscreen-btn:hover {{ background: #f4f4f4; }}

        /* 2. Selector de Capas Base (Estilo Nativo Leaflet) */
        .leaflet-control-layers {{
            box-shadow: 0 1px 5px rgba(0,0,0,0.4);
            background: #fff;
            border-radius: 5px;
            transition: padding 0.1s;
        }}
        .leaflet-control-layers:hover {{ padding: 6px 10px 6px 6px; }}
        
        .leaflet-control-layers-toggle {{
            width: 36px; height: 36px; display: block;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23333' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='12 2 2 7 12 12 22 7 12 2'/%3E%3Cpolyline points='2 12 12 17 22 12'/%3E%3Cpolyline points='2 17 12 22 22 17'/%3E%3C/svg%3E");
            background-size: 20px 20px; background-position: center; background-repeat: no-repeat;
        }}
        .leaflet-control-layers:hover .leaflet-control-layers-toggle {{ display: none; }}
        
        .leaflet-control-layers-list {{ display: none; font-size: 12px; font-family: "Helvetica Neue", Arial, Helvetica, sans-serif; color: #333; margin: 0; min-width: 150px; }}
        .leaflet-control-layers:hover .leaflet-control-layers-list {{ display: block; }}
        
        .leaflet-control-layers-base label {{ display: block; margin: 0; padding: 0; cursor: pointer; font-weight: normal !important; }}
        .leaflet-control-layers-base label div {{ display: flex; align-items: center; margin-bottom: 3px; }}
        .leaflet-control-layers-base input[type="radio"] {{ margin: 0 5px 0 0; cursor: pointer; }}
        .leaflet-control-layers-base span {{ font-size: 12px; white-space: nowrap; }}

        /* 3. Panel Lateral de Datos (Docked) */
        .docked-panel {{
            background: #ffffff !important; width: 290px !important; border-radius: 8px !important;
            overflow: hidden !important; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25) !important;
            border-top: 4px solid #691C32 !important; border-left: 1px solid #E2D9C8 !important;
            border-right: 1px solid #E2D9C8 !important; border-bottom: 1px solid #E2D9C8 !important; display: none;
        }}
        
        .docked-header {{ background: #691C32 !important; color: #ffffff !important; padding: 10px 14px !important; position: relative !important; }}
        .docked-title {{ font-size: 14px !important; font-weight: 700 !important; display: block !important; padding-right: 22px !important; line-height: 1.2 !important; color: #ffffff !important; }}
        .docked-sub {{ font-size: 11px !important; color: #D4C19C !important; display: block !important; margin-top: 4px !important; letter-spacing: 0.5px !important; }}
        .docked-close {{ position: absolute !important; top: 8px !important; right: 10px !important; color: #ffffff !important; cursor: pointer !important; font-size: 20px !important; font-weight: bold !important; transition: color 0.2s ease !important; line-height: 1 !important; }}
        .docked-close:hover {{ color: #BC955C !important; }}
        .docked-body {{ padding: 14px !important; background: #ffffff !important; max-height: 380px !important; overflow-y: auto !important; }}
        .card-badge {{ display: inline-block !important; padding: 4px 10px !important; border-radius: 12px !important; color: #ffffff !important; font-size: 11px !important; font-weight: bold !important; margin-bottom: 10px !important; text-shadow: 0 1px 2px rgba(0,0,0,0.3) !important; }}
        .card-table {{ width: 100% !important; border-collapse: collapse !important; font-size: 12px !important; }}
        .card-table td {{ padding: 5px 0 !important; border-bottom: 1px solid #F0ECE6 !important; color: #333333 !important; }}
        .card-table td.label {{ color: #6F7271 !important; font-weight: 500 !important; width: 55% !important; }}
        .card-table td.val {{ font-weight: 600 !important; text-align: right !important; color: #1A1A1A !important; }}

        /* Tooltip Minimalista (Hover) */
        .minimal-popup .maplibregl-popup-content {{
            background: rgba(26, 26, 26, 0.92) !important; color: #ffffff !important;
            border: 1px solid #BC955C !important; border-left: 3px solid #BC955C !important;
            border-radius: 4px !important; font-size: 11px !important; padding: 4px 8px !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important; pointer-events: none !important; margin-top: -10px !important;
        }}
        .minimal-popup .maplibregl-popup-tip {{ display: none !important; }}
        
        /* Popup de Marcador (Ir a Coordenadas) */
        .marker-popup .maplibregl-popup-content {{
            padding: 12px 16px !important; border-radius: 6px !important;
            border-top: 4px solid #691C32 !important; box-shadow: 0 4px 15px rgba(0,0,0,0.2) !important;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}

        /* =========================================================================
           PANEL DE CONTROLES PRINCIPAL
           ========================================================================= */
        .leaflet-custom-controls {{
            background: #ffffff;
            padding: 16px;
            border-radius: 8px;
            box-sizing: border-box;
            box-shadow: 0 4px 18px rgba(0,0,0,0.18);
            width: 320px;
            max-height: 85vh;
            overflow-y: auto;
            overflow-x: hidden;
            transition: all 0.3s ease;
            z-index: 9999 !important;
            position: relative;
            margin-bottom: 10px !important;
            border-top: 4px solid #691C32;
            border-left: 1px solid #E2D9C8;
            border-right: 1px solid #E2D9C8;
            border-bottom: 1px solid #E2D9C8;
        }}

        /* ESTILO PARA QUE EL SCROLL NO TAPE LAS ESQUINAS REDONDEADAS */
        .leaflet-custom-controls::-webkit-scrollbar {{
            width: 6px;
        }}
        .leaflet-custom-controls::-webkit-scrollbar-track {{
            background: transparent;
            border-radius: 8px;
            margin: 8px 0; /* Aleja la barra de las esquinas superior e inferior */
        }}
        .leaflet-custom-controls::-webkit-scrollbar-thumb {{
            background: #D1D5DB;
            border-radius: 8px;
        }}
        .leaflet-custom-controls::-webkit-scrollbar-thumb:hover {{
            background: #BC955C;
        }}
        
        .panel-close-button {{
            float: right;
            cursor: pointer;
            font-size: 20px;
            font-weight: bold;
            color: #888888;
            margin-top: -3px;
            transition: color 0.2s ease;
        }}
        .panel-close-button:hover {{ color: #691C32; }}
        
        .leaflet-open-button {{
            background: #691C32 !important;
            color: #ffffff !important;
            width: 38px;
            height: 38px;
            border-radius: 50% !important;
            padding: 0 !important;
            line-height: 36px;
            text-align: center;
            cursor: pointer;
            box-shadow: 0 3px 10px rgba(105, 28, 50, 0.35);
            font-size: 18px;
            font-weight: bold;
            border: 1.5px solid #BC955C !important;
            display: none;
            margin-bottom: 10px !important;
            z-index: 9999 !important;
            position: relative;
            transition: all 0.2s ease;
        }}
        .leaflet-open-button:hover {{
            background: #4A1424 !important;
            transform: scale(1.08);
        }}

        .control-section {{ margin-bottom: 14px; position: relative; }}
        .control-section label {{
            font-weight: 600;
            font-size: 12.5px;
            color: #333333;
            display: block;
            margin-bottom: 5px;
        }}

        .theme-switch {{
            display: flex;
            border: 1px solid #BC955C;
            border-radius: 6px;
            overflow: hidden;
            background: #FAF8F5;
        }}
        
        /* BOTONES DEL MENÚ (!important para evitar que MapLibre los blanquee) */
        .theme-btn {{
            flex: 1;
            padding: 7px 10px;
            border: none;
            background: transparent !important;
            cursor: pointer;
            font-size: 12px;
            color: #555555 !important;
            font-weight: 500;
            transition: all 0.2s ease;
        }}
        .theme-btn:hover {{ background: rgba(105, 28, 50, 0.08) !important; color: #691C32 !important; }}
        .theme-btn.active {{ background: #691C32 !important; color: #ffffff !important; font-weight: bold; }}
        .theme-btn.active:hover {{ background: #4A1424 !important; color: #ffffff !important; }}
        
        input[type="text"], input[type="number"] {{
            width: 100%;
            padding: 7px 9px;
            box-sizing: border-box;
            border: 1px solid #D1D5DB;
            border-radius: 5px;
            font-size: 12px;
            margin-bottom: 6px;
            background: #FAFAFA;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }}
        input[type="text"]:focus, input[type="number"]:focus {{
            outline: none;
            border-color: #691C32;
            background: #ffffff;
            box-shadow: 0 0 0 2px rgba(105, 28, 50, 0.15);
        }}
        
        input[type="range"] {{ width: 100%; accent-color: #691C32; cursor: pointer; }}
        .radio-group {{ display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; margin-top: 5px; }}
        .radio-group label {{ font-weight: normal !important; display: inline-flex; align-items: center; cursor: pointer; margin-bottom: 0 !important; }}
        .radio-group input[type="radio"], input[type="checkbox"] {{ accent-color: #691C32; cursor: pointer; margin-right: 5px; }}
        
        .custom-dropdown {{ position: relative; width: 100%; }}
        .custom-dropdown-list {{
            position: absolute; top: 100%; left: 0; right: 0; background: white;
            border: 1px solid #BC955C; border-top: none; border-radius: 0 0 6px 6px;
            max-height: 150px; overflow-y: auto; z-index: 10000; display: none;
            box-shadow: 0 4px 10px rgba(0,0,0,0.12);
        }}
        .custom-dropdown-item {{
            padding: 8px 10px;
            font-size: 12px;
            cursor: pointer;
            border-bottom: 1px solid #F3EFEA;
            transition: background 0.15s ease, color 0.15s ease;
        }}
        .custom-dropdown-item:hover {{ background-color: #FAF5EE; color: #691C32; font-weight: 600; }}
        
        .flex-row {{ display: flex; gap: 6px; }}
        .flex-row input {{ width: 50%; }}
        
        /* BOTONES DE ACCIÓN (!important para evitar que MapLibre los blanquee) */
        .action-button {{
            width: 100%;
            padding: 8px 12px;
            background: #691C32 !important;
            color: #ffffff !important;
            border: 1px solid #BC955C !important;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            font-size: 12px;
            transition: background 0.2s ease;
        }}
        .action-button:hover {{ background: #4A1424 !important; color: #ffffff !important; }}

        .btn-clear-point {{
            width: 35px;
            padding: 8px 0;
            background: #6F7271 !important;
            color: #ffffff !important;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
            transition: background 0.2s ease;
            text-align: center;
        }}
        .btn-clear-point:hover {{ background: #4A4D4E !important; color: #ffffff !important; }}

        .btn-reset-view {{
            width: 100%;
            padding: 8px 12px;
            background: #6F7271 !important;
            color: #ffffff !important;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            font-size: 12px;
            margin-top: 12px;
            transition: background 0.2s ease;
        }}
        .btn-reset-view:hover {{ background: #4A4D4E !important; color: #ffffff !important; }}

        /* Controles Inferior Derecho */
        .print-btn {{ 
            background: white; border: 2px solid rgba(0,0,0,0.2); border-radius: 4px; 
            cursor: pointer; padding: 0; font-size: 16px; color: #333; 
            display: flex; align-items: center; justify-content: center;
            width: 32px; height: 32px; box-shadow: 0 1px 5px rgba(0,0,0,0.4);
            transition: background 0.2s;
        }}
        .print-btn:hover {{ background: #f4f4f4; }}
        
        .custom-logo {{ display: block; height: 38px; opacity: 0.95; max-width: 110px; object-fit: contain; }}
        
        /* Leyenda Inferior Izquierda */
        .legend {{ 
            background: white; padding: 12px; border-radius: 6px; font-size: 12px; line-height: 18px; color: #333; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.2); pointer-events: auto; width: 140px; transition: all 0.3s ease;
        }}
        .legend-header {{ display: flex; justify-content: space-between; align-items: center; cursor: pointer; font-size: 13px; font-weight: bold; border-bottom: 1px solid transparent; padding-bottom: 0px; }}
        .legend-header:hover {{ color: #691C32; }}
        .legend-body {{ overflow: hidden; transition: max-height 0.3s ease; margin-top: 8px; }}
        .legend-body.collapsed {{ max-height: 0 !important; margin-top: 0 !important; }}
        .legend i {{ width: 14px; height: 14px; float: left; margin-right: 8px; opacity: 0.95; border: 1px solid #444444; border-radius: 2px; box-sizing: border-box; }}
    </style>
</head>
<body>

    <div id="map"></div>

    <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js"></script>

    <script>
        // ==========================================
        // 1. DATOS Y PREPARACIÓN
        // ==========================================
        const dataVuln = {json_vuln};
        const dataHydro = {json_hydro};
        const dataPozos = {json_pozos};
        const dataCosta1 = {json_costa1};
        const dataCosta10 = {json_costa10};

        function assignIDs(geojson, prefix) {{
            if (!geojson.features) return;
            geojson.features.forEach((f, i) => f.id = i + 1);
        }}
        assignIDs(dataVuln);
        assignIDs(dataHydro);
        assignIDs(dataPozos);

        function getBBox(geom) {{
            let bounds = [Infinity, Infinity, -Infinity, -Infinity];
            let coords = geom.type.includes("Multi") ? geom.coordinates.flat(2) : geom.coordinates.flat(1);
            if (geom.type === "Polygon") coords = geom.coordinates.flat(1);
            if (geom.type === "MultiPolygon") coords = geom.coordinates.flat(2);
            coords.forEach(c => {{
                if (c[0] < bounds[0]) bounds[0] = c[0];
                if (c[1] < bounds[1]) bounds[1] = c[1];
                if (c[0] > bounds[2]) bounds[2] = c[0];
                if (c[1] > bounds[3]) bounds[3] = c[1];
            }});
            return bounds;
        }}

        const searchIndex = {{}};
        const searchNames = new Set();
        
        function extendBBox(b1, b2) {{
            return [
                Math.min(b1[0], b2[0]), Math.min(b1[1], b2[1]),
                Math.max(b1[2], b2[2]), Math.max(b1[3], b2[3])
            ];
        }}

        function buildIndex(features, theme) {{
            if (!features) return;
            features.forEach(f => {{
                let name = f.properties.NOM_ACUIF;
                let clave = f.properties.CLAVE_ACUI;
                if (name && clave) {{
                    let key = clave.padStart(4, '0') + " - " + name;
                    f.properties.__sk = key; 
                    searchNames.add(key);
                    
                    if (!searchIndex[key]) searchIndex[key] = {{}};
                    if (!searchIndex[key][theme]) {{
                        searchIndex[key][theme] = {{ ids: [], bounds: [Infinity, Infinity, -Infinity, -Infinity], props: f.properties }};
                    }}
                    
                    searchIndex[key][theme].ids.push(f.id);
                    searchIndex[key][theme].bounds = extendBBox(searchIndex[key][theme].bounds, getBBox(f.geometry));
                }}
            }});
        }}
        buildIndex(dataVuln.features, 'vuln');
        buildIndex(dataHydro.features, 'hydro');

        const vulnColors = {{ '5': '#D90404', '4': '#F25C05', '3': '#F2B705', '2': '#99C140', '1': '#2DC937', 'default': '#CCCCCC' }};

        // ==========================================
        // 2. INICIALIZACIÓN DEL MAPA
        // ==========================================
        
        const viewBounds = [
            [-124.4, 13.5], 
            [-80.5, 33.5]   
        ];
        
        const limitBounds = [
            [-130.0, 8.0], 
            [-72.0, 39.0]   
        ];

        const map = new maplibregl.Map({{
            container: 'map',
            style: {{
                version: 8,
                glyphs: "https://fonts.openmaptiles.org/{{fontstack}}/{{range}}.pbf",
                sources: {{
                    'basemap': {{ type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'], tileSize: 256, attribution: '<b>© Esri</b>' }}
                }},
                layers: [{{ id: 'basemap-layer', type: 'raster', source: 'basemap', minzoom: 0, maxzoom: 22 }}]
            }},
            bounds: viewBounds,           
            fitBoundsOptions: {{ padding: 10 }}, 
            maxBounds: limitBounds,       
            minZoom: 3.5,                 
            preserveDrawingBuffer: true,
            attributionControl: false
        }});

        map.addControl(new maplibregl.AttributionControl({{ compact: false }}), 'bottom-right');

        let activeTheme = 'vulnerability';
        let currentOpacity = 0.75;
        let currentVulnFilter = 'all';
        let hoveredStateId = null;
        
        // VARIABLES DE SELECCIÓN INDEPENDIENTES
        let searchedStateIds = []; 
        let searchedProps = null; 
        let clickedStateId = null;

        const popup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, className: 'minimal-popup' }});

        // ==========================================
        // 3. CONTROLES PERSONALIZADOS (UI)
        // ==========================================
        class CustomControl {{
            constructor(id, html) {{ this.id = id; this.html = html; }}
            onAdd(map) {{
                this._container = document.createElement('div');
                this._container.id = this.id;
                this._container.className = 'maplibregl-ctrl';
                this._container.innerHTML = this.html;
                return this._container;
            }}
            onRemove() {{ this._container.parentNode.removeChild(this._container); }}
        }}

        const iconExpand = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
        map.addControl(new CustomControl('custom-fs-container', `<div id="fs-btn" class="custom-fullscreen-btn" title="Pantalla completa">${{iconExpand}}</div>`), 'top-right');
        
        const basemapsUrls = {{
            "Neutral (defecto)": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}",
            "OpenStreetMap": "https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png",
            "Estándar (ESRI)": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}",
            "Satélite (ESRI)": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}",
            "Topográfico (ESRI)": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}",
            "Gris Oscuro (ESRI)": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}"
        }};
        let radiosHtml = Object.keys(basemapsUrls).map((k, i) => `
            <label>
                <div><input type="radio" name="basemap_radio" value="${{k}}" ${{i===0 ? 'checked' : ''}}><span> ${{k}}</span></div>
            </label>
        `).join('');
        
        const layerControlHtml = `
            <div class="leaflet-control-layers custom-leaflet-layers">
                <a class="leaflet-control-layers-toggle" href="#" title="Capas"></a>
                <div class="leaflet-control-layers-list">
                    <div class="leaflet-control-layers-base">
                        ${{radiosHtml}}
                    </div>
                </div>
            </div>
        `;
        map.addControl(new CustomControl('custom-layer-container', layerControlHtml), 'top-right');
        map.addControl(new maplibregl.NavigationControl({{ showCompass: true, showZoom: true }}), 'top-right');
        map.addControl(new CustomControl('docked-panel-container', '<div id="docked-panel" class="docked-panel"></div>'), 'top-right');

        const menuHtml = `
            <div id="btn-open-panel" class="leaflet-open-button" title="Mostrar controles">☰</div>
            <div id="panel-container" class="leaflet-custom-controls">
                <span id="btn-close-panel" class="panel-close-button" title="Ocultar controles">&times;</span>
                <h3 style="margin-top:0; color:#691C32;">⚙️ Controles</h3>
                
                <div class="control-section">
                    <label>Modo de Visualización:</label>
                    <div class="theme-switch">
                        <button id="btn-vuln" class="theme-btn active">Vulnerabilidad</button>
                        <button id="btn-hydro" class="theme-btn">Hidrodinámicos</button>
                    </div>
                </div>

                <div class="control-section custom-dropdown">
                    <label>Buscar Acuífero:</label>
                    <input type="text" id="search-input" placeholder="-- Escribe o selecciona --" autocomplete="off">
                    <div id="search-list" class="custom-dropdown-list"></div>
                </div>

                <div class="control-section">
                    <label>Opacidad: <span id="op-val">75%</span></label>
                    <input type="range" id="op-slider" min="0" max="1" step="0.05" value="0.75">
                </div>
                
                <div class="control-section" id="vuln-filter-section">
                    <label>Iluminar por vulnerabilidad:</label>
                    <div class="radio-group" id="vuln-radios">
                        <label><input type="radio" name="vuln-filter" value="all" checked> Todos</label>
                        <label><input type="radio" name="vuln-filter" value="5"> 5</label>
                        <label><input type="radio" name="vuln-filter" value="4"> 4</label>
                        <label><input type="radio" name="vuln-filter" value="3"> 3</label>
                        <label><input type="radio" name="vuln-filter" value="2"> 2</label>
                        <label><input type="radio" name="vuln-filter" value="1"> 1</label>
                    </div>
                </div>

                <div class="control-section">
                    <label>Ir a Coordenadas:</label>
                    <input type="text" id="coord-name" placeholder="Punto (Ej. Pozo 1)">
                    <div class="flex-row">
                        <input type="number" id="coord-lat" placeholder="Latitud">
                        <input type="number" id="coord-lon" placeholder="Longitud">
                    </div>
                    <div class="flex-row" style="margin-top: 5px;">
                        <button id="btn-coords" class="action-button" style="flex: 1;">Ubicar en Mapa</button>
                        <button id="btn-clear-coord" class="btn-clear-point" title="Borrar punto">🗑️</button>
                    </div>
                    <!-- MENSAJE DE ERROR OCULTO -->
                    <div id="coord-error" style="display: none; color: #D90404; font-size: 11px; margin-top: 6px; font-weight: 600; text-align: center;">
                        ⚠️ Ingresa Latitud y Longitud.
                    </div>
                </div>

                <div class="control-section">
                    <label>Capas Adicionales:</label>
                    <label id="lbl-pozos"><input type="checkbox" id="chk-pozos"> Mostrar Pozos</label><br>
                    <label id="lbl-c10"><input type="checkbox" id="chk-c10"> Línea Costa (10km)</label><br>
                    <label id="lbl-c1"><input type="checkbox" id="chk-c1"> Línea Costa (1km)</label><br>
                    <label><input type="checkbox" id="chk-malla"> Mallado (Lat/Lon)</label>
                </div>
                
                <button id="btn-reset" class="btn-reset-view">↺ Restablecer Vista</button>
            </div>
        `;
        map.addControl(new CustomControl('main-menu-container', menuHtml), 'top-left');

        map.addControl(new CustomControl('print-ctrl-container', `<button id="btn-print" class="print-btn" title="Descargar imagen">🖨️</button>`), 'bottom-right');
        map.addControl(new maplibregl.ScaleControl({{ maxWidth: 100, unit: 'metric' }}), 'bottom-right');
        map.addControl(new CustomControl('logo-ctrl-container', `<img class="custom-logo" src="https://raw.githubusercontent.com/Dchable16/geovisor_vulnerabilidad/main/logos/Logo_SSIG.png">`), 'bottom-right');
        
        const legendHtml = `
            <div class="legend" id="legend-container">
                <div class="legend-header" id="legend-toggle">
                    <span>Simbología</span>
                    <span id="legend-icon" style="font-size:11px;">▼</span>
                </div>
                <div class="legend-body" id="legend-body" style="max-height: 200px;">
                    <i style="background:#D90404;"></i> 5 - Muy Alta<br>
                    <i style="background:#F25C05;"></i> 4 - Alta<br>
                    <i style="background:#F2B705;"></i> 3 - Media<br>
                    <i style="background:#99C140;"></i> 2 - Baja<br>
                    <i style="background:#2DC937;"></i> 1 - Muy Baja<br>
                    <i style="background:#CCCCCC;"></i> Sin Datos
                </div>
            </div>
        `;
        map.addControl(new CustomControl('legend-wrapper', legendHtml), 'bottom-left');

        document.getElementById('legend-toggle').onclick = function() {{
            const body = document.getElementById('legend-body');
            const icon = document.getElementById('legend-icon');
            if (body.classList.contains('collapsed')) {{
                body.classList.remove('collapsed');
                icon.innerText = '▼';
                this.style.borderBottom = '1px solid transparent';
            }} else {{
                body.classList.add('collapsed');
                icon.innerText = '▲';
                this.style.borderBottom = 'none';
            }}
        }};

        // ==========================================
        // 4. LÓGICA DE CAPAS Y MAPA
        // ==========================================
        map.on('load', () => {{
            
            if(dataVuln.features) map.addSource('vuln-src', {{ type: 'geojson', data: dataVuln }});
            if(dataHydro.features) map.addSource('hydro-src', {{ type: 'geojson', data: dataHydro }});
            if(dataCosta10.features) map.addSource('c10-src', {{ type: 'geojson', data: dataCosta10 }});
            if(dataCosta1.features) map.addSource('c1-src', {{ type: 'geojson', data: dataCosta1 }});
            if(dataPozos.features) map.addSource('pozos-src', {{ type: 'geojson', data: dataPozos }});
            map.addSource('graticule-src', {{ type: 'geojson', data: {{type: 'FeatureCollection', features: []}} }});

            function getVulnFillExpression() {{
                return [
                    'case',
                    ['all', ['!=', currentVulnFilter, 'all'], ['!=', ['to-string', ['get', 'VULNERABIL']], currentVulnFilter]], 0.1,
                    ['boolean', ['feature-state', 'selected'], false], 0.85,
                    currentOpacity
                ];
            }}

            function getVulnLineColorExpression() {{
                return [
                    'case',
                    ['boolean', ['feature-state', 'selected'], false], '#691C32',
                    ['boolean', ['feature-state', 'hover'], false], '#007BFF',
                    ['all', ['!=', currentVulnFilter, 'all'], ['!=', ['to-string', ['get', 'VULNERABIL']], currentVulnFilter]], '#dddddd',
                    '#555555'
                ];
            }}

            function getVulnLineWidthExpression() {{
                return [
                    'case',
                    ['boolean', ['feature-state', 'selected'], false], 4,
                    ['boolean', ['feature-state', 'hover'], false], 3,
                    ['all', ['!=', currentVulnFilter, 'all'], ['!=', ['to-string', ['get', 'VULNERABIL']], currentVulnFilter]], 0.5,
                    1
                ];
            }}

            function getHydroFillExpression() {{
                return ['case', ['boolean', ['feature-state', 'selected'], false], 0.85, currentOpacity];
            }}

            if(dataVuln.features) {{
                map.addLayer({{
                    id: 'vuln-fill', type: 'fill', source: 'vuln-src',
                    paint: {{
                        'fill-color': ['match', ['to-string', ['get', 'VULNERABIL']], 
                            '5', vulnColors['5'], '4', vulnColors['4'], '3', vulnColors['3'], 
                            '2', vulnColors['2'], '1', vulnColors['1'], vulnColors['default']],
                        'fill-opacity': getVulnFillExpression()
                    }}
                }});
                map.addLayer({{
                    id: 'vuln-line', type: 'line', source: 'vuln-src',
                    paint: {{
                        'line-color': getVulnLineColorExpression(),
                        'line-width': getVulnLineWidthExpression()
                    }}
                }});
            }}

            if(dataHydro.features) {{
                map.addLayer({{
                    id: 'hydro-fill', type: 'fill', source: 'hydro-src',
                    layout: {{ visibility: 'none' }},
                    paint: {{
                        'fill-color': ['case', ['has', 'transmisividad_media'], '#AAD3DF', '#E0E0E0'],
                        'fill-opacity': getHydroFillExpression()
                    }}
                }});
                map.addLayer({{
                    id: 'hydro-line', type: 'line', source: 'hydro-src',
                    layout: {{ visibility: 'none' }},
                    paint: {{
                        'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#691C32',
                                      ['boolean', ['feature-state', 'hover'], false], '#000000', '#666666'],
                        'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 4,
                                      ['boolean', ['feature-state', 'hover'], false], 3, 1]
                    }}
                }});
            }}

            if(dataCosta10.features) map.addLayer({{ id: 'c10-line', type: 'line', source: 'c10-src', layout: {{visibility: 'none'}}, paint: {{'line-color': '#007BFF', 'line-width': 3, 'line-opacity': 0.8}} }});
            if(dataCosta1.features) map.addLayer({{ id: 'c1-line', type: 'line', source: 'c1-src', layout: {{visibility: 'none'}}, paint: {{'line-color': '#FF0000', 'line-width': 3, 'line-opacity': 0.8}} }});
            if(dataPozos.features) map.addLayer({{ id: 'pozos-point', type: 'circle', source: 'pozos-src', layout: {{visibility: 'none'}}, paint: {{'circle-radius': 4, 'circle-color': '#007BFF', 'circle-stroke-width': 1, 'circle-stroke-color': '#fff'}} }});
            
            map.addLayer({{ 
                id: 'graticule-line', type: 'line', source: 'graticule-src', 
                filter: ['==', ['geometry-type'], 'LineString'],
                layout: {{visibility: 'none'}}, 
                paint: {{'line-color': '#444', 'line-width': 0.8, 'line-opacity': 0.6}} 
            }});

            map.addLayer({{ 
                id: 'graticule-label', type: 'symbol', source: 'graticule-src', 
                filter: ['==', ['geometry-type'], 'Point'],
                layout: {{
                    visibility: 'none', 
                    'text-field': ['get', 'label'],
                    'text-font': ['Open Sans Regular'],
                    'text-size': 12, 
                    'symbol-placement': 'point',
                    'text-anchor': 'top-left',
                    'text-offset': [0.3, 0.3],
                    'text-allow-overlap': true,
                    'text-ignore-placement': true
                }}, 
                paint: {{'text-color': '#222', 'text-halo-color': '#fff', 'text-halo-width': 2.5}} 
            }});

            function setFeatureSelected(id, isSelected) {{
                if (map.getSource('vuln-src')) map.setFeatureState({{ source: 'vuln-src', id: id }}, {{ selected: isSelected }});
                if (map.getSource('hydro-src')) map.setFeatureState({{ source: 'hydro-src', id: id }}, {{ selected: isSelected }});
            }}

            function handleHover(layerPrefix) {{
                const fillLayer = layerPrefix + '-fill';
                map.on('mousemove', fillLayer, (e) => {{
                    if (e.features.length > 0) {{
                        map.getCanvas().style.cursor = 'pointer';
                        const f = e.features[0];
                        if (hoveredStateId !== null) map.setFeatureState({{ source: layerPrefix + '-src', id: hoveredStateId }}, {{ hover: false }});
                        hoveredStateId = f.id;
                        map.setFeatureState({{ source: layerPrefix + '-src', id: hoveredStateId }}, {{ hover: true }});
                        
                        let name = f.properties.NOM_ACUIF || 'Sin Nombre';
                        let clave = f.properties.CLAVE_ACUI ? f.properties.CLAVE_ACUI.padStart(4, '0') : 'S/D';
                        popup.setLngLat(e.lngLat).setHTML(`<b>${{clave}}</b> - ${{name}}`).addTo(map);
                    }}
                }});
                map.on('mouseleave', fillLayer, () => {{
                    map.getCanvas().style.cursor = '';
                    if (hoveredStateId !== null) map.setFeatureState({{ source: layerPrefix + '-src', id: hoveredStateId }}, {{ hover: false }});
                    hoveredStateId = null;
                    popup.remove();
                }});

                map.on('click', fillLayer, (e) => {{
                    if (e.features.length > 0) {{
                        const f = e.features[0];
                        
                        if (clickedStateId !== null && !searchedStateIds.includes(clickedStateId)) {{
                            setFeatureSelected(clickedStateId, false);
                        }}
                        
                        clickedStateId = f.id;
                        setFeatureSelected(clickedStateId, true);
                        
                        showDockedInfo(f.properties, layerPrefix);
                    }}
                }});
            }}
            if(dataVuln.features) handleHover('vuln');
            if(dataHydro.features) handleHover('hydro');

            if(dataPozos.features) {{
                map.on('mouseenter', 'pozos-point', (e) => {{
                    map.getCanvas().style.cursor = 'pointer';
                    let name = e.features[0].properties.NOMBRE_POZO || 'Pozo';
                    popup.setLngLat(e.lngLat).setHTML(`📍 <b>${{name}}</b>`).addTo(map);
                }});
                map.on('mouseleave', 'pozos-point', () => {{ map.getCanvas().style.cursor = ''; popup.remove(); }});
                map.on('click', 'pozos-point', (e) => showDockedInfo(e.features[0].properties, 'pozo'));
            }}

            // CLIC EN EL FONDO DEL MAPA
            map.on('click', (e) => {{
                const layers = [];
                if(activeTheme==='vulnerability') layers.push('vuln-fill');
                if(activeTheme==='hydro') layers.push('hydro-fill');
                const features = map.queryRenderedFeatures(e.point, {{ layers: layers }});
                
                if (!features.length && !map.queryRenderedFeatures(e.point, {{layers: ['pozos-point']}}).length) {{
                    
                    if (clickedStateId !== null) {{
                        if (!searchedStateIds.includes(clickedStateId)) {{
                            setFeatureSelected(clickedStateId, false);
                        }}
                        clickedStateId = null;
                    }}
                    
                    if (searchedStateIds.length > 0 && searchedProps) {{
                        showDockedInfo(searchedProps, activeTheme === 'vulnerability' ? 'vuln' : 'hydro');
                    }} else {{
                        document.getElementById('docked-panel').style.display = 'none';
                    }}
                }}
            }});

            function clearSelection() {{
                searchedStateIds.forEach(id => setFeatureSelected(id, false));
                searchedStateIds = [];
                searchedProps = null;
                
                if (clickedStateId !== null) {{
                    setFeatureSelected(clickedStateId, false);
                    clickedStateId = null;
                }}
                document.getElementById('docked-panel').style.display = 'none';
            }}

            function updateStyles() {{
                if(map.getLayer('vuln-fill')) {{
                    map.setPaintProperty('vuln-fill', 'fill-opacity', getVulnFillExpression());
                    map.setPaintProperty('vuln-line', 'line-color', getVulnLineColorExpression());
                    map.setPaintProperty('vuln-line', 'line-width', getVulnLineWidthExpression());
                }}
                if(map.getLayer('hydro-fill')) {{
                    map.setPaintProperty('hydro-fill', 'fill-opacity', getHydroFillExpression());
                }}
            }}

            function showDockedInfo(props, theme) {{
                const panel = document.getElementById('docked-panel');
                let vulnLabels = {{'5':'5 - Muy Alta', '4':'4 - Alta', '3':'3 - Media', '2':'2 - Baja', '1':'1 - Muy Baja'}};
                let v = String(props.VULNERABIL || '');
                let vColor = vulnColors[v] || '#888888';
                let vText = vulnLabels[v] || 'Sin Datos';

                // CORRECCIÓN: Se quitó el onclick="..." del span. 
                // La acción de cerrar se asigna correctamente al final de esta función.
                let html = `<div class="docked-header"><span class="docked-close">&times;</span><span class="docked-title">${{props.NOM_ACUIF || props.ACUIFERO || props.NOMBRE_POZO || 'Sin Nombre'}}</span><span class="docked-sub">CLAVE OFICIAL: ${{props.CLAVE_ACUI || 'S/D'}}</span></div><div class="docked-body">`;

                if(theme === 'vuln') html += `<div class="card-badge" style="background:${{vColor}};">${{vText}}</div><table class="card-table"><tr><td class="label">Metodología:</td><td class="val">SEAG-INDEX</td></tr></table>`;
                else if(theme === 'hydro') html += `<table class="card-table"><tr><td class="label">Transmisividad:</td><td class="val">${{props.transmisividad_media || 'S/D'}} m²/d</td></tr><tr><td class="label">Conductividad:</td><td class="val">${{props.conductividad_media || 'S/D'}} m/d</td></tr><tr><td class="label">Almacenamiento:</td><td class="val">${{props.coef_almacenamiento_medio || 'S/D'}}</td></tr><tr><td class="label">Pozos Oficiales:</td><td class="val">${{props.pozos_registrados || '0'}}</td></tr></table>`;
                else if(theme === 'pozo') html += `<table class="card-table"><tr><td class="label">Acuífero:</td><td class="val">${{props.ACUIFERO || 'S/D'}}</td></tr><tr><td class="label">Transmisividad:</td><td class="val">${{props.T_m2d || 'S/D'}} m²/d</td></tr><tr><td class="label">Profundidad:</td><td class="val">${{props.PROFUNDIDAD || 'S/D'}} m</td></tr></table>`;
                
                html += `</div>`;
                panel.innerHTML = html;
                panel.style.display = 'block';
                panel.querySelector('.docked-close').onclick = clearSelection;
            }}

            document.querySelectorAll('input[name="basemap_radio"]').forEach(radio => {{
                radio.addEventListener('change', (e) => {{
                    map.getSource('basemap').setTiles([basemapsUrls[e.target.value]]);
                }});
            }});
            
            document.getElementById('btn-close-panel').onclick = () => {{ document.getElementById('panel-container').style.display='none'; document.getElementById('btn-open-panel').style.display='block'; }};
            document.getElementById('btn-open-panel').onclick = () => {{ document.getElementById('panel-container').style.display='block'; document.getElementById('btn-open-panel').style.display='none'; }};

            document.getElementById('btn-vuln').onclick = function() {{
                activeTheme = 'vulnerability';
                this.classList.add('active'); document.getElementById('btn-hydro').classList.remove('active');
                map.setLayoutProperty('vuln-fill', 'visibility', 'visible'); map.setLayoutProperty('vuln-line', 'visibility', 'visible');
                if(map.getLayer('hydro-fill')) {{ map.setLayoutProperty('hydro-fill', 'visibility', 'none'); map.setLayoutProperty('hydro-line', 'visibility', 'none'); }}
                document.getElementById('legend-wrapper').style.display = 'block'; document.getElementById('vuln-filter-section').style.display = 'block';
            }};

            document.getElementById('btn-hydro').onclick = function() {{
                if(!dataHydro.features) return;
                activeTheme = 'hydro';
                this.classList.add('active'); document.getElementById('btn-vuln').classList.remove('active');
                map.setLayoutProperty('vuln-fill', 'visibility', 'none'); map.setLayoutProperty('vuln-line', 'visibility', 'none');
                map.setLayoutProperty('hydro-fill', 'visibility', 'visible'); map.setLayoutProperty('hydro-line', 'visibility', 'visible');
                document.getElementById('legend-wrapper').style.display = 'none'; document.getElementById('vuln-filter-section').style.display = 'none';
            }};

            document.getElementById('op-slider').oninput = (e) => {{
                currentOpacity = parseFloat(e.target.value);
                document.getElementById('op-val').innerText = Math.round(currentOpacity*100)+'%';
                updateStyles();
            }};

            document.querySelectorAll('input[name="vuln-filter"]').forEach(r => r.onchange = function() {{
                currentVulnFilter = this.value; updateStyles();
            }});

            document.getElementById('chk-pozos').onchange = e => map.setLayoutProperty('pozos-point', 'visibility', e.target.checked ? 'visible' : 'none');
            document.getElementById('chk-c10').onchange = e => map.setLayoutProperty('c10-line', 'visibility', e.target.checked ? 'visible' : 'none');
            document.getElementById('chk-c1').onchange = e => map.setLayoutProperty('c1-line', 'visibility', e.target.checked ? 'visible' : 'none');

            const searchInput = document.getElementById('search-input');
            const searchList = document.getElementById('search-list');
            const allNames = Array.from(searchNames).sort();

            function renderDropdown(text="") {{
                searchList.innerHTML = ""; let c = 0;
                allNames.forEach(n => {{
                    if (n.toLowerCase().includes(text.toLowerCase())) {{
                        let d = document.createElement('div'); d.className = 'custom-dropdown-item'; d.innerText = n;
                        d.onclick = () => {{ searchInput.value = n; searchList.style.display = 'none'; triggerSearch(n); }};
                        searchList.appendChild(d); c++;
                    }}
                }});
                searchList.style.display = c > 0 ? 'block' : 'none';
            }}
            searchInput.onfocus = () => renderDropdown(searchInput.value);
            searchInput.oninput = (e) => renderDropdown(e.target.value);
            document.onclick = (e) => {{ if(!searchInput.contains(e.target) && !searchList.contains(e.target)) searchList.style.display='none'; }};

            function triggerSearch(name) {{
                let data = searchIndex[name][activeTheme === 'vulnerability' ? 'vuln' : 'hydro'];
                if(!data) return;
                
                clearSelection();
                
                searchedStateIds = data.ids;
                searchedProps = data.props;
                searchedStateIds.forEach(id => setFeatureSelected(id, true));
                
                map.fitBounds(data.bounds, {{padding: 50, duration: 1000}});
                setTimeout(() => showDockedInfo(data.props, activeTheme === 'vulnerability' ? 'vuln' : 'hydro'), 1000);
            }}

            let tempMarker = null;
            document.getElementById('btn-coords').onclick = () => {{
                let lat = parseFloat(document.getElementById('coord-lat').value);
                let lon = parseFloat(document.getElementById('coord-lon').value);
                let name = document.getElementById('coord-name').value || 'Punto Buscado';
                let errorMsg = document.getElementById('coord-error');
                
                // Muestra el error en el panel sin salir de pantalla completa
                if(isNaN(lat) || isNaN(lon)) {{
                    errorMsg.style.display = 'block';
                    setTimeout(() => {{ errorMsg.style.display = 'none'; }}, 3000); // Se oculta a los 3 segundos
                    return;
                }}
                
                errorMsg.style.display = 'none'; // Oculta el error si todo está bien
                if(tempMarker) tempMarker.remove();
                
                const popupHtml = `
                    <div style="color: #333; text-align: center; min-width: 120px;">
                        <b style="color: #691C32; font-size: 13px; display:block; margin-bottom:4px;">${{name}}</b>
                        <span style="font-size: 11px; color: #555;">Lat: ${{lat}}</span><br>
                        <span style="font-size: 11px; color: #555;">Lon: ${{lon}}</span>
                    </div>
                `;
                
                const markerPopup = new maplibregl.Popup({{ offset: 35, className: 'marker-popup', closeButton: true }})
                    .setHTML(popupHtml);
                
                tempMarker = new maplibregl.Marker({{color: '#691C32'}})
                    .setLngLat([lon, lat])
                    .setPopup(markerPopup)
                    .addTo(map);
                    
                tempMarker.togglePopup();
                map.flyTo({{center: [lon, lat], zoom: 12}});
            }};

            // NUEVA FUNCIÓN: Limpiar solo el punto
            document.getElementById('btn-clear-coord').onclick = () => {{
                if(tempMarker) tempMarker.remove();
                document.getElementById('coord-lat').value = '';
                document.getElementById('coord-lon').value = '';
                document.getElementById('coord-name').value = '';
            }};

            document.getElementById('btn-reset').onclick = () => {{
                clearSelection();
                currentVulnFilter = 'all'; document.querySelector('input[value="all"]').checked = true; updateStyles();
                searchInput.value = ''; 
                
                // Limpiar el marcador al restablecer también
                if(tempMarker) tempMarker.remove();
                document.getElementById('coord-lat').value = '';
                document.getElementById('coord-lon').value = '';
                document.getElementById('coord-name').value = '';
                
                map.fitBounds(viewBounds, {{ padding: 10, duration: 1000 }});
            }};

            document.getElementById('btn-print').onclick = function() {{
                const btn = this; btn.innerHTML = '⏳'; btn.style.cursor = 'wait';
                htmlToImage.toPng(document.getElementById('map'), {{
                    pixelRatio: 2, quality: 1.0,
                    filter: (node) => {{
                        if (!node.classList) return true;
                        // Ocultamos todos los controles EXCEPTO la leyenda si está abierta
                        if (node.classList.contains('maplibregl-ctrl')) {{
                            if (node.id === 'legend-wrapper') {{
                                const body = document.getElementById('legend-body');
                                return !body.classList.contains('collapsed');
                            }}
                            return false; 
                        }}
                        return true;
                    }}
                }}).then(url => {{
                    let a = document.createElement('a'); a.download = 'Mapa_Geovisor.png'; a.href = url; a.click();
                }}).finally(() => {{ btn.innerHTML = '🖨️'; btn.style.cursor = 'pointer'; }});
            }};

            document.getElementById('fs-btn').onclick = function() {{
                if (!document.fullscreenElement) document.documentElement.requestFullscreen();
                else document.exitFullscreen();
            }};
            document.addEventListener('fullscreenchange', () => {{
                document.getElementById('fs-btn').innerHTML = document.fullscreenElement ? 
                    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>` : iconExpand;
                
                setTimeout(() => {{
                    map.resize();
                    map.fitBounds(viewBounds, {{ padding: 10, duration: 800 }}); 
                }}, 200);
            }});

            if(!dataHydro.features) document.getElementById('btn-hydro').style.display = 'none';
            if(!dataPozos.features) document.getElementById('lbl-pozos').style.display = 'none';
            if(!dataCosta10.features) document.getElementById('lbl-c10').style.display = 'none';
            if(!dataCosta1.features) document.getElementById('lbl-c1').style.display = 'none';

            function updateGraticule() {{
                if(map.getLayoutProperty('graticule-line', 'visibility') === 'none') return;
                
                const bounds = map.getBounds();
                const latSpan = bounds.getNorth() - bounds.getSouth();
                const target = latSpan / 6;
                const intervals = [20, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01];
                let interval = 0.01;
                for(let i=0; i<intervals.length; i++) {{ if(target >= intervals[i]) {{ interval = intervals[i]; break; }} }}
                
                const features = [];
                const s = Math.floor(bounds.getSouth() / interval) * interval;
                const n = Math.ceil(bounds.getNorth() / interval) * interval;
                const w = Math.floor(bounds.getWest() / interval) * interval;
                const e = Math.ceil(bounds.getEast() / interval) * interval;

                const topEdge = bounds.getNorth();
                const leftEdge = bounds.getWest();

                for(let lat=s; lat<=n; lat+=interval) {{
                    features.push({{ type: 'Feature', geometry: {{ type: 'LineString', coordinates: [[w, lat], [e, lat]] }}, properties: {{}} }});
                    features.push({{ type: 'Feature', geometry: {{ type: 'Point', coordinates: [leftEdge, lat] }}, properties: {{ label: Number(lat.toFixed(5)) + '°' }} }});
                }}
                for(let lng=w; lng<=e; lng+=interval) {{
                    features.push({{ type: 'Feature', geometry: {{ type: 'LineString', coordinates: [[lng, s], [lng, n]] }}, properties: {{}} }});
                    features.push({{ type: 'Feature', geometry: {{ type: 'Point', coordinates: [lng, topEdge] }}, properties: {{ label: Number(lng.toFixed(5)) + '°' }} }});
                }}
                map.getSource('graticule-src').setData({{type: 'FeatureCollection', features: features}});
            }}
            
            map.on('move', updateGraticule);
            
            document.getElementById('chk-malla').onchange = (e) => {{
                map.setLayoutProperty('graticule-line', 'visibility', e.target.checked ? 'visible' : 'none');
                map.setLayoutProperty('graticule-label', 'visibility', e.target.checked ? 'visible' : 'none');
                if(e.target.checked) updateGraticule();
            }};
        }});
    </script>
</body>
</html>
"""

# Renderizar el HTML en Streamlit
components.html(html_code, height=720)
