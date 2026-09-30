# -*- coding: utf-8 -*-
"""
Geovisor de Vulnerabilidad e Hidráulica (Arquitectura Híbrida Python + JS)
- Mapa a pantalla completa (Full Width & Full Height).
- Mallado adaptativo sin errores de zoom.
- Botón de Pantalla Completa oficial (4 esquinas en negritas) arriba del selector de capas.
- Panel lateral acoplado (Docked Inspector) con colores institucionales oficiales.
- Tooltips al vuelo (Hover) + Ficha técnica al clic.
"""

import streamlit as st
import streamlit.components.v1 as components
import geopandas as gpd
import pandas as pd
from shapely import wkt
import json

# Importaciones de tu core
from utils.styles import inyectar_css_oficial, banner_institucional
from core.data_loader import CARPETA_DATOS

# ==========================================
# 1. CONFIGURACIÓN GLOBALES
# ==========================================
st.set_page_config(layout="wide")
inyectar_css_oficial()
banner_institucional()

# CSS para forzar a Streamlit a usar todo el espacio disponible
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
            height: 79vh !important;
            border: none;
        }
    </style>
""", unsafe_allow_html=True)

st.subheader("🌍 Geovisor de Vulnerabilidad e Hidráulica")

# ==========================================
# 2. PREPARACIÓN DE DATOS EN PYTHON (BACKEND)
# ==========================================
@st.cache_data(show_spinner="Optimizando y consolidando datos espaciales...")
def preparar_datos_para_js():
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
    else: json_vuln = "{}"

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

    return json_vuln, json_hydro, json_pozos, json_costa1, json_costa10

json_vuln, json_hydro, json_pozos, json_costa1, json_costa10 = preparar_datos_para_js()

# ==========================================
# 3. INYECCIÓN DEL FRONTEND (JS OPTIMIZADO)
# ==========================================
html_code = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        html, body {{ margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        #map {{ width: 100%; height: 100%; background-color: #e5e5e5; }}
        
        /* Jerarquía Z-Index */
        .leaflet-top {{ z-index: 1000 !important; }}
        .leaflet-bottom {{ z-index: 900 !important; }}

        /* =========================================================================
           ORDEN Y POSICIÓN EN LA ESQUINA SUPERIOR DERECHA (TOP-RIGHT)
           ========================================================================= */
        .leaflet-top.leaflet-right {{
            display: flex !important;
            flex-direction: column !important;
            align-items: flex-end !important;
        }}

        /* 1. Botón Pantalla Completa: Siempre primero arriba */
        .leaflet-fullscreen-control {{
            order: 1 !important;
            margin-top: 10px !important;
            margin-right: 10px !important;
            margin-bottom: 0 !important;
        }}

        /* 2. Selector de Capas Base: Debajo de pantalla completa */
        .leaflet-control-layers {{
            order: 2 !important;
            margin-top: 10px !important;
            margin-right: 10px !important;
        }}

        /* 3. Panel Lateral de Datos: Debajo de las capas */
        .leaflet-docked-panel {{
            order: 3 !important;
            margin-top: 10px !important;
            margin-right: 10px !important;
            background: #ffffff !important;
            width: 290px !important;
            border-radius: 8px !important;
            overflow: hidden !important;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25) !important;
            border-top: 4px solid #691C32 !important;
            border-left: 1px solid #E2D9C8 !important;
            border-right: 1px solid #E2D9C8 !important;
            border-bottom: 1px solid #E2D9C8 !important;
            z-index: 1000 !important;
            font-family: 'Segoe UI', Arial, sans-serif !important;
            display: none;
        }}
        
        .docked-header {{
            background: #691C32 !important;
            color: #ffffff !important;
            padding: 10px 14px !important;
            position: relative !important;
        }}
        
        .docked-title {{
            font-size: 14px !important;
            font-weight: 700 !important;
            display: block !important;
            padding-right: 22px !important;
            line-height: 1.2 !important;
            color: #ffffff !important;
        }}
        
        .docked-sub {{
            font-size: 11px !important;
            color: #D4C19C !important;
            display: block !important;
            margin-top: 4px !important;
            letter-spacing: 0.5px !important;
        }}
        
        .docked-close {{
            position: absolute !important;
            top: 8px !important;
            right: 10px !important;
            color: #ffffff !important;
            cursor: pointer !important;
            font-size: 20px !important;
            font-weight: bold !important;
            transition: color 0.2s ease !important;
            line-height: 1 !important;
        }}
        .docked-close:hover {{ color: #BC955C !important; }}
        
        .docked-body {{
            padding: 14px !important;
            background: #ffffff !important;
            max-height: 380px !important;
            overflow-y: auto !important;
        }}

        .card-badge {{
            display: inline-block !important;
            padding: 4px 10px !important;
            border-radius: 12px !important;
            color: #ffffff !important;
            font-size: 11px !important;
            font-weight: bold !important;
            margin-bottom: 10px !important;
            text-shadow: 0 1px 2px rgba(0,0,0,0.3) !important;
        }}

        .card-table {{
            width: 100% !important;
            border-collapse: collapse !important;
            font-size: 12px !important;
        }}
        .card-table td {{
            padding: 5px 0 !important;
            border-bottom: 1px solid #F0ECE6 !important;
            color: #333333 !important;
        }}
        .card-table td.label {{
            color: #6F7271 !important;
            font-weight: 500 !important;
            width: 55% !important;
        }}
        .card-table td.val {{
            font-weight: 600 !important;
            text-align: right !important;
            color: #1A1A1A !important;
        }}

        /* Tooltip Minimalista (Hover) */
        .institutional-tooltip {{
            background: rgba(26, 26, 26, 0.92) !important;
            color: #ffffff !important;
            border: 1px solid #BC955C !important;
            border-left: 3px solid #BC955C !important;
            border-radius: 4px !important;
            font-size: 11px !important;
            font-family: 'Segoe UI', Arial, sans-serif !important;
            padding: 4px 8px !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
            pointer-events: none !important;
        }}
        .institutional-tooltip:before {{ display: none !important; }}
        
        /* Panel de Controles Principal */
        .leaflet-custom-controls {{
            background: #ffffff;
            padding: 16px;
            border-radius: 8px;
            box-shadow: 0 4px 18px rgba(0,0,0,0.18);
            width: 320px;
            max-height: 85vh;
            overflow-y: auto;
            transition: all 0.3s ease;
            z-index: 9999 !important;
            position: relative;
            margin-bottom: 10px !important;
            border-top: 4px solid #691C32;
            border-left: 1px solid #E2D9C8;
            border-right: 1px solid #E2D9C8;
            border-bottom: 1px solid #E2D9C8;
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
            background: #691C32;
            color: #ffffff;
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
            border: 1.5px solid #BC955C;
            display: none;
            margin-bottom: 10px !important;
            z-index: 9999 !important;
            position: relative;
            transition: all 0.2s ease;
        }}
        .leaflet-open-button:hover {{
            background: #4A1424;
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
        .theme-btn {{
            flex: 1;
            padding: 7px 10px;
            border: none;
            background: transparent;
            cursor: pointer;
            font-size: 12px;
            color: #555555;
            font-weight: 500;
            transition: all 0.2s ease;
        }}
        .theme-btn:hover {{ background: rgba(105, 28, 50, 0.08); color: #691C32; }}
        .theme-btn.active {{ background: #691C32; color: #ffffff; font-weight: bold; }}
        
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
        
        .action-button {{
            width: 100%;
            padding: 8px 12px;
            background: #691C32;
            color: #ffffff;
            border: 1px solid #BC955C;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            font-size: 12px;
            transition: background 0.2s ease;
        }}
        .action-button:hover {{ background: #4A1424; }}

        .btn-reset-view {{
            width: 100%;
            padding: 8px 12px;
            background: #6F7271;
            color: #ffffff;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: 600;
            font-size: 12px;
            margin-top: 12px;
            transition: background 0.2s ease;
        }}
        .btn-reset-view:hover {{ background: #4A4D4E; }}
        
        /* Controles Inferior Derecho */
        .leaflet-bottom.leaflet-right {{
            display: flex !important;
            flex-direction: column !important;
            align-items: flex-end !important;
            justify-content: flex-end !important;
            right: 0 !important;
            bottom: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            pointer-events: none !important;
        }}

        .leaflet-print-control {{
            order: 1 !important;
            margin: 0 10px 8px 0 !important;
            background: transparent !important;
            border: none !important;
            pointer-events: auto !important;
        }}
        .print-btn {{ 
            background: white; border: 2px solid rgba(0,0,0,0.2); border-radius: 4px; 
            cursor: pointer; padding: 0; font-size: 16px; color: #333; 
            display: flex; align-items: center; justify-content: center;
            width: 32px; height: 32px; box-shadow: 0 1px 5px rgba(0,0,0,0.4);
            transition: background 0.2s;
        }}
        .print-btn:hover {{ background: #f4f4f4; }}
        
        .leaflet-control-scale {{ 
            order: 2 !important;
            margin: 0 6px 1px 0 !important;
            pointer-events: auto !important;
        }}
        .leaflet-control-scale-line {{ margin: 0 !important; }}
        
        .leaflet-logo-control {{ 
            order: 3 !important;
            margin: 0 10px 2px 0 !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            display: flex !important;
            align-items: center !important;
            justify-content: flex-end !important;
            gap: 12px !important;
            pointer-events: auto !important;
        }}
        .leaflet-logo-control img {{ 
            height: 38px;
            width: auto;
            max-width: 110px;
            opacity: 0.95; 
            display: block; 
            object-fit: contain;
        }}

        .leaflet-control-attribution {{
            order: 4 !important;
            margin: 0 !important;
            font-size: 14px !important;
            pointer-events: auto !important;
        }}
        
        .legend {{ 
            background: white; padding: 12px; border: none; 
            border-radius: 6px; font-size: 12px; line-height: 18px; color: #333; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            margin-bottom: 12px !important; margin-left: 12px !important;
            z-index: 800 !important; position: relative;
        }}
        .legend b {{ font-size: 13px; display: block; margin-bottom: 8px; }}
        .legend i {{ 
            width: 14px; 
            height: 14px; 
            float: left; 
            margin-right: 8px; 
            opacity: 0.95; 
            border: 1px solid #444444;
            border-radius: 2px;
            box-sizing: border-box;
        }}
    </style>
</head>
<body>

    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js"></script>
    
    <!-- PLUGIN MALLADO (GRATICULE ADAPTATIVO EXACTO) -->
    <script>
        L.LatLngGraticule = L.Layer.extend({{
            options: {{
                showLabel: true, 
                opacity: 0.6, 
                weight: 0.8, 
                color: '#444', 
                font: 'bold 11px Arial, sans-serif', 
                fontColor: '#222'
            }},
            initialize: function (options) {{ L.setOptions(this, options); }},
            onAdd: function (map) {{
                this._map = map;
                this._canvas = L.DomUtil.create('canvas', 'leaflet-zoom-animated');
                this._ctx = this._canvas.getContext('2d');
                map._panes.overlayPane.appendChild(this._canvas);
                map.on('viewreset zoomend moveend', this._reset, this);
                this._reset();
            }},
            onRemove: function (map) {{
                L.DomUtil.remove(this._canvas);
                map.off('viewreset zoomend moveend', this._reset, this);
            }},
            _reset: function () {{
                var size = this._map.getSize();
                var lt = this._map.containerPointToLayerPoint([0, 0]);
                L.DomUtil.setPosition(this._canvas, lt);
                this._canvas.width = size.x; this._canvas.height = size.y;
                this._draw();
            }},

            _getInterval: function(bounds) {{
                var latSpan = bounds.getNorth() - bounds.getSouth();
                var target = latSpan / 6;
                
                var intervals = [
                    20, 10, 5, 2, 1,
                    0.5, 0.2, 0.1,
                    0.05, 0.02, 0.01,
                    0.005, 0.002, 0.001,
                    0.0005, 0.0002, 0.0001
                ];
                
                for (var i = 0; i < intervals.length; i++) {{
                    if (target >= intervals[i]) {{
                        return intervals[i];
                    }}
                }}
                return 0.0001;
            }},

            _draw: function() {{
                var map = this._map; 
                var bounds = map.getBounds();
                var interval = this._getInterval(bounds);
                var ctx = this._ctx; 
                ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
                
                var latIndexStart = Math.ceil(bounds.getSouth() / interval);
                var latIndexEnd = Math.floor(bounds.getNorth() / interval);
                var lngIndexStart = Math.ceil(bounds.getWest() / interval);
                var lngIndexEnd = Math.floor(bounds.getEast() / interval);

                ctx.beginPath();
                for (var i = latIndexStart; i <= latIndexEnd; i++) {{
                    var lat = i * interval;
                    var p1 = map.latLngToContainerPoint([lat, bounds.getWest()]);
                    var p2 = map.latLngToContainerPoint([lat, bounds.getEast()]);
                    ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y);
                }}
                for (var j = lngIndexStart; j <= lngIndexEnd; j++) {{
                    var lng = j * interval;
                    var p1 = map.latLngToContainerPoint([bounds.getNorth(), lng]);
                    var p2 = map.latLngToContainerPoint([bounds.getSouth(), lng]);
                    ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y);
                }}
                ctx.lineWidth = this.options.weight; 
                ctx.strokeStyle = this.options.color;
                ctx.stroke();

                if (this.options.showLabel) {{
                    ctx.font = this.options.font;
                    ctx.textAlign = "center";
                    ctx.textBaseline = "middle";
                    
                    for (var i = latIndexStart; i <= latIndexEnd; i++) {{
                        var lat = i * interval;
                        var p1 = map.latLngToContainerPoint([lat, bounds.getWest()]);
                        var text = Number(lat.toFixed(5)) + '°';
                        ctx.save();
                        ctx.translate(22, p1.y + 15);
                        ctx.rotate(-Math.PI / 2);
                        ctx.strokeStyle = "white"; ctx.lineWidth = 3; ctx.strokeText(text, 0, 0);
                        ctx.fillStyle = this.options.fontColor; ctx.fillText(text, 0, 0);
                        ctx.restore();
                    }}
                    
                    for (var j = lngIndexStart; j <= lngIndexEnd; j++) {{
                        var lng = j * interval;
                        var p1 = map.latLngToContainerPoint([bounds.getNorth(), lng]);
                        var text = Number(lng.toFixed(5)) + '°';
                        ctx.save();
                        ctx.translate(p1.x + 20, 18);
                        ctx.strokeStyle = "white"; ctx.lineWidth = 3; ctx.strokeText(text, 0, 0);
                        ctx.fillStyle = this.options.fontColor; ctx.fillText(text, 0, 0);
                        ctx.restore();
                    }}
                }}
            }}
        }});
        L.latlngGraticule = function(options) {{ return new L.LatLngGraticule(options); }};
    </script>

    <script>
        const dataVuln = {json_vuln};
        const dataHydro = {json_hydro};
        const dataPozos = {json_pozos};
        const dataCosta1 = {json_costa1};
        const dataCosta10 = {json_costa10};

        const map = L.map('map', {{ 
            preferCanvas: true, 
            attributionControl: true 
        }}).setView([23.6345, -102.5528], 5);
        
        // =========================================================================
        // 1. BOTÓN PANTALLA COMPLETA (ICONO EXACTO A FOLIUM - 4 ESQUINAS NEGRAS)
        // =========================================================================
        const iconExpandSVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
        const iconCompressSVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;

        const fsControl = L.control({{ position: 'topright' }});
        fsControl.onAdd = function(map) {{
            const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-fullscreen-control');
            const btn = L.DomUtil.create('a', 'leaflet-fullscreen-btn', container);
            btn.innerHTML = iconExpandSVG;
            btn.href = '#';
            btn.title = 'Pantalla completa';
            btn.style.width = '32px';
            btn.style.height = '32px';
            btn.style.display = 'flex';
            btn.style.alignItems = 'center';
            btn.style.justifyContent = 'center';
            btn.style.background = '#ffffff';
            btn.style.cursor = 'pointer';
            btn.style.textDecoration = 'none';

            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);

            L.DomEvent.on(btn, 'click', function(e) {{
                L.DomEvent.stop(e);
                if (!document.fullscreenElement) {{
                    document.documentElement.requestFullscreen().catch(err => {{
                        alert(`No se pudo activar pantalla completa: ${{err.message}}`);
                    }});
                }} else {{
                    if (document.exitFullscreen) {{
                        document.exitFullscreen();
                    }}
                }}
            }});

            // Asegura que siempre quede en primer lugar arriba del selector de capas
            setTimeout(function() {{
                const corner = map._controlCorners['topright'];
                if (corner && corner.firstChild !== container) {{
                    corner.insertBefore(container, corner.firstChild);
                }}
            }}, 0);

            return container;
        }};
        fsControl.addTo(map);

        document.addEventListener('fullscreenchange', function() {{
            const btn = document.querySelector('.leaflet-fullscreen-btn');
            if (document.fullscreenElement) {{
                if (btn) {{
                    btn.innerHTML = iconCompressSVG;
                    btn.title = 'Salir de pantalla completa';
                }}
            }} else {{
                if (btn) {{
                    btn.innerHTML = iconExpandSVG;
                    btn.title = 'Pantalla completa';
                }}
            }}
            setTimeout(function() {{
                map.invalidateSize();
            }}, 200);
        }});

        // =========================================================================
        // 2. SELECTOR DE CAPAS BASE
        // =========================================================================
        const basemaps = {{
            "Neutral (defecto)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ attribution: '© Esri' }}).addTo(map),
            "OpenStreetMap": L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ attribution: '© OpenStreetMap' }}),
            "Estándar (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ attribution: '© Esri' }}),
            "Satélite (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ attribution: '© Esri' }}),
            "Topográfico (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ attribution: '© Esri' }}),
            "Terreno (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ attribution: '© Esri' }}),
            "Océanos (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ attribution: '© Esri' }}),
            "Gris Oscuro (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ attribution: '© Esri' }})
        }};
        
        L.control.layers(basemaps, null, {{position: 'topright'}}).addTo(map);

        // =========================================================================
        // 3. CONTROLES EN BOTTOM-RIGHT: 1. Botón -> 2. Escala -> 3. Logo SSIG -> 4. Leaflet
        // =========================================================================
        const printControl = L.control({{position: 'bottomright'}});
        printControl.onAdd = function() {{
            const container = L.DomUtil.create('div', 'leaflet-print-control');
            const btn = L.DomUtil.create('button', 'print-btn', container);
            btn.innerHTML = '🖨️';
            btn.title = 'Descargar mapa como imagen PNG';
            
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);

            L.DomEvent.on(btn, 'click', function() {{
                btn.innerHTML = '⏳';
                btn.style.cursor = 'wait';
                btn.disabled = true;

                const mapElement = document.getElementById('map');

                htmlToImage.toPng(mapElement, {{
                    pixelRatio: 2,
                    quality: 1.0,
                    filter: function(node) {{
                        if (!node.classList) return true;
                        const exclude = [
                            'leaflet-control-zoom', 
                            'leaflet-control-layers', 
                            'leaflet-print-control', 
                            'print-btn', 
                            'leaflet-custom-controls', 
                            'leaflet-open-button',
                            'leaflet-fullscreen-control',
                            'leaflet-fullscreen-btn'
                        ];
                        for (let i = 0; i < exclude.length; i++) {{
                            if (node.classList.contains(exclude[i])) return false;
                        }}
                        return true;
                    }}
                }}).then(function (dataUrl) {{
                    let link = document.createElement('a');
                    link.download = 'Mapa_Geovisor.png';
                    link.href = dataUrl;
                    link.click();
                }}).catch(function(error) {{
                    console.error("Error al exportar:", error);
                }}).finally(function() {{
                    btn.innerHTML = '🖨️';
                    btn.style.cursor = 'pointer';
                    btn.disabled = false;
                }});
            }});
            return container;
        }};
        printControl.addTo(map);

        L.control.scale({{ position: 'bottomright', imperial: false }}).addTo(map);

        const LogoControl = L.Control.extend({{
            onAdd: function() {{
                const c = L.DomUtil.create('div', 'leaflet-logo-control');
                c.innerHTML = `
                    <img src="https://raw.githubusercontent.com/Dchable16/geovisor_vulnerabilidad/main/logos/Logo_SSIG.png" alt="Logo SSIG">
                `;
                return c;
            }}
        }});
        new LogoControl({{ position: 'bottomright' }}).addTo(map);

        // ==========================================
        // VARIABLES GLOBALES Y LÓGICA DE CAPAS
        // ==========================================
        let activeTheme = 'vulnerability';
        let currentOpacity = 0.75;
        let currentSelectedAquifer = ""; 
        let currentVulnFilter = "all"; 
        
        let layerVuln, layerHydro, layerPozos, layerCosta1, layerCosta10, graticuleLayer;
        
        let indexVuln = {{}};
        let indexHydro = {{}};
        let searchNames = new Set();

        const vulnColors = {{
            '5': '#D90404', '4': '#F25C05', '3': '#F2B705', '2': '#99C140', '1': '#2DC937', 'default': '#CCCCCC'
        }};

        // =========================================================================
        // CONTROL Y FUNCIONES DEL PANEL LATERAL ACOPLADO (TOP-RIGHT)
        // =========================================================================
        const dockControl = L.control({{ position: 'topright' }});
        dockControl.onAdd = function() {{
            const div = L.DomUtil.create('div', 'leaflet-docked-panel');
            div.id = 'docked-panel';
            L.DomEvent.disableClickPropagation(div);
            L.DomEvent.disableScrollPropagation(div);
            return div;
        }};
        dockControl.addTo(map);

        let selectedLayerHighlight = null;

        function showDockedInfo(props, theme, layer) {{
            const panel = document.getElementById('docked-panel');
            if(!panel) return;

            // Restaurar estilo del acuífero previamente seleccionado
            if(selectedLayerHighlight && selectedLayerHighlight !== layer) {{
                if(activeTheme === 'vulnerability' && typeof updateVulnStyles === 'function') {{
                    updateVulnStyles();
                }}
                if(activeTheme === 'hydro' && typeof layerHydro !== 'undefined' && layerHydro) {{
                    layerHydro.eachLayer(l => layerHydro.resetStyle(l));
                }}
            }}

            // Resaltar en el mapa el polígono actual en guinda
            selectedLayerHighlight = layer;
            if(layer && layer.setStyle) {{
                layer.setStyle({{ weight: 4, color: '#691C32', fillOpacity: 0.85 }});
            }}

            let vulnLabels = {{
                '5': '5 - Muy Alta',
                '4': '4 - Alta',
                '3': '3 - Media',
                '2': '2 - Baja',
                '1': '1 - Muy Baja'
            }};
            let v = String(props.VULNERABIL || '');
            let vColor = (typeof vulnColors !== 'undefined' && vulnColors[v]) ? vulnColors[v] : '#888888';
            let vText = vulnLabels[v] || 'Sin Datos';

            let html = `
                <div class="docked-header">
                    <span class="docked-close" onclick="closeDockedInfo()">&times;</span>
                    <span class="docked-title">${{props.NOM_ACUIF || props.ACUIFERO || props.NOMBRE_POZO || 'Sin Nombre'}}</span>
                    <span class="docked-sub">CLAVE OFICIAL: ${{props.CLAVE_ACUI || 'S/D'}}</span>
                </div>
                <div class="docked-body">
            `;

            if(theme === 'vuln') {{
                html += `
                    <div class="card-badge" style="background:${{vColor}};">${{vText}}</div>
                    <table class="card-table">
                        <tr><td class="label">Metodología:</td><td class="val">SEAG-INDEX</td></tr>
                    </table>
                `;
            }} else if(theme === 'hydro') {{
                html += `
                    <table class="card-table">
                        <tr><td class="label">Transmisividad:</td><td class="val">${{props.transmisividad_media || 'S/D'}} m²/d</td></tr>
                        <tr><td class="label">Conductividad:</td><td class="val">${{props.conductividad_media || 'S/D'}} m/d</td></tr>
                        <tr><td class="label">Almacenamiento:</td><td class="val">${{props.coef_almacenamiento_medio || 'S/D'}}</td></tr>
                        <tr><td class="label">Pozos Oficiales:</td><td class="val">${{props.pozos_registrados || '0'}}</td></tr>
                    </table>
                `;
            }} else if(theme === 'pozo') {{
                html += `
                    <table class="card-table">
                        <tr><td class="label">Acuífero:</td><td class="val">${{props.ACUIFERO || 'S/D'}}</td></tr>
                        <tr><td class="label">Transmisividad:</td><td class="val">${{props.T_m2d || 'S/D'}} m²/d</td></tr>
                        <tr><td class="label">Profundidad:</td><td class="val">${{props.PROFUNDIDAD || 'S/D'}} m</td></tr>
                    </table>
                `;
            }}

            html += `</div>`;
            panel.innerHTML = html;
            panel.style.display = 'block';
        }}

        function closeDockedInfo() {{
            const panel = document.getElementById('docked-panel');
            if(panel) panel.style.display = 'none';
            if(selectedLayerHighlight) {{
                if(activeTheme === 'vulnerability' && typeof updateVulnStyles === 'function') {{
                    updateVulnStyles();
                }}
                if(activeTheme === 'hydro' && typeof layerHydro !== 'undefined' && layerHydro) {{
                    layerHydro.eachLayer(l => layerHydro.resetStyle(l));
                }}
                selectedLayerHighlight = null;
            }}
        }}

        // Cerrar panel al hacer clic en el mapa vacío
        map.on('click', function() {{
            closeDockedInfo();
        }});

        function updateVulnStyles() {{
            if (!layerVuln) return;
            layerVuln.eachLayer(function(layer) {{
                let val = layer.feature.properties.VULNERABIL;
                let searchKey = layer.feature.properties.CLAVE_ACUI.padStart(4, '0') + " - " + layer.feature.properties.NOM_ACUIF;
                let isSelected = searchKey === currentSelectedAquifer;
                
                let opacity = currentOpacity;
                if (currentVulnFilter !== "all" && String(val) !== currentVulnFilter) {{
                    opacity = 0.1; 
                }}

                layer.setStyle({{
                    fillColor: vulnColors[val] || vulnColors['default'], 
                    color: isSelected ? '#691C32' : (opacity === 0.1 ? '#ddd' : '#555'), 
                    weight: isSelected ? 4 : (opacity === 0.1 ? 0.5 : 1), 
                    fillOpacity: opacity 
                }});
            }});
        }}

        // ==========================================
        // CREACIÓN DE CAPAS (CONECTADAS AL PANEL LATERAL)
        // ==========================================
        if(dataVuln.features) {{
            layerVuln = L.geoJSON(dataVuln, {{
                style: function(feature) {{
                    let val = feature.properties.VULNERABIL;
                    return {{ fillColor: vulnColors[val] || vulnColors['default'], color: '#555', weight: 1, fillOpacity: currentOpacity }};
                }},
                onEachFeature: function(feature, layer) {{
                    let name = feature.properties.NOM_ACUIF;
                    let clave = feature.properties.CLAVE_ACUI;
                    if(name && clave) {{
                        let searchKey = clave.padStart(4, '0') + " - " + name;
                        searchNames.add(searchKey);
                        if (!indexVuln[searchKey]) indexVuln[searchKey] = [];
                        indexVuln[searchKey].push(layer); 
                    }}

                    // 1. Tooltip al pasar el cursor (Hover)
                    let claveNorm = clave ? clave.padStart(4, '0') : 'S/D';
                    layer.bindTooltip(`<b>${{claveNorm}}</b> - ${{name || 'Sin Nombre'}}`, {{
                        sticky: true,
                        direction: 'top',
                        className: 'institutional-tooltip',
                        offset: [0, -10]
                    }});

                    // 2. Clic: Abre el panel lateral
                    layer.on('click', function(e) {{
                        L.DomEvent.stopPropagation(e);
                        showDockedInfo(feature.properties, 'vuln', layer);
                    }});
                    
                    layer.on('mouseover', function() {{ 
                        let searchKey = feature.properties.CLAVE_ACUI.padStart(4, '0') + " - " + feature.properties.NOM_ACUIF;
                        if (searchKey !== currentSelectedAquifer && layer !== selectedLayerHighlight) {{
                            this.setStyle({{weight: 3, color: '#007BFF'}}); 
                        }}
                    }});
                    layer.on('mouseout', function() {{ 
                        let searchKey = feature.properties.CLAVE_ACUI.padStart(4, '0') + " - " + feature.properties.NOM_ACUIF;
                        if (searchKey !== currentSelectedAquifer && layer !== selectedLayerHighlight) {{
                            updateVulnStyles(); 
                        }}
                    }});
                }}
            }}).addTo(map);
        }}

        if(dataHydro.features) {{
            layerHydro = L.geoJSON(dataHydro, {{
                style: function(feature) {{
                    let hasData = feature.properties.transmisividad_media ? true : false;
                    return {{ fillColor: hasData ? '#AAD3DF' : '#E0E0E0', color: '#666', weight: 1, fillOpacity: currentOpacity }};
                }},
                onEachFeature: function(feature, layer) {{
                    let name = feature.properties.NOM_ACUIF;
                    let clave = feature.properties.CLAVE_ACUI;
                    if(name && clave) {{
                        let searchKey = clave.padStart(4, '0') + " - " + name;
                        if (!indexHydro[searchKey]) indexHydro[searchKey] = [];
                        indexHydro[searchKey].push(layer);
                    }}

                    let claveNorm = clave ? clave.padStart(4, '0') : 'S/D';
                    layer.bindTooltip(`<b>${{claveNorm}}</b> - ${{name || 'Sin Nombre'}}`, {{
                        sticky: true,
                        direction: 'top',
                        className: 'institutional-tooltip',
                        offset: [0, -10]
                    }});

                    layer.on('click', function(e) {{
                        L.DomEvent.stopPropagation(e);
                        showDockedInfo(feature.properties, 'hydro', layer);
                    }});
                    
                    layer.on('mouseover', function() {{ 
                        let searchKey = feature.properties.CLAVE_ACUI.padStart(4, '0') + " - " + feature.properties.NOM_ACUIF;
                        if (searchKey !== currentSelectedAquifer && layer !== selectedLayerHighlight) {{
                            this.setStyle({{weight: 3, color: '#000'}}); 
                        }}
                    }});
                    layer.on('mouseout', function() {{ 
                        let searchKey = feature.properties.CLAVE_ACUI.padStart(4, '0') + " - " + feature.properties.NOM_ACUIF;
                        if (searchKey !== currentSelectedAquifer && layer !== selectedLayerHighlight) {{
                            layerHydro.resetStyle(this); 
                        }}
                    }});
                }}
            }});
        }}

        if(dataPozos.features) {{
            layerPozos = L.geoJSON(dataPozos, {{
                pointToLayer: function(feature, latlng) {{
                    return L.circleMarker(latlng, {{ radius: 4, fillColor: '#007BFF', color: '#fff', weight: 1, fillOpacity: 0.8 }});
                }},
                onEachFeature: function(feature, layer) {{
                    let nombrePozo = feature.properties.NOMBRE_POZO || 'Pozo';
                    layer.bindTooltip(`📍 <b>${{nombrePozo}}</b>`, {{
                        sticky: true,
                        direction: 'top',
                        className: 'institutional-tooltip',
                        offset: [0, -8]
                    }});

                    layer.on('click', function(e) {{
                        L.DomEvent.stopPropagation(e);
                        showDockedInfo(feature.properties, 'pozo', layer);
                    }});
                }}
            }});
        }}

        if(dataCosta10.features) layerCosta10 = L.geoJSON(dataCosta10, {{ style: function() {{ return {{color: '#007BFF', weight: 3, opacity: 0.8, fill: false}}; }} }});
        if(dataCosta1) layerCosta1 = L.geoJSON(dataCosta1, {{ style: function() {{ return {{color: '#FF0000', weight: 3, opacity: 0.8, fill: false}}; }} }});

        // PANEL DE CONTROLES COLAPSABLE (topleft)
        const uiControl = L.control({{position: 'topleft'}});
        uiControl.onAdd = function() {{
            const wrapper = L.DomUtil.create('div');
            L.DomEvent.disableClickPropagation(wrapper);
            L.DomEvent.disableScrollPropagation(wrapper);
            
            wrapper.innerHTML = `
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
                        <label>Buscar Acuífero (Clave o Nombre):</label>
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
                        <input type="text" id="coord-name" placeholder="Nombre del punto (Ej. Pozo 1)">
                        <div class="flex-row">
                            <input type="number" id="coord-lat" placeholder="Latitud">
                            <input type="number" id="coord-lon" placeholder="Longitud">
                        </div>
                        <button id="btn-coords" class="action-button" style="margin-top: 5px;">Ubicar en Mapa</button>
                    </div>

                    <div class="control-section">
                        <label>Capas Adicionales:</label>
                        <label><input type="checkbox" id="chk-pozos"> Mostrar Pozos</label><br>
                        <label><input type="checkbox" id="chk-c10"> Línea Costa (10km)</label><br>
                        <label><input type="checkbox" id="chk-c1"> Línea Costa (1km)</label><br>
                        <label><input type="checkbox" id="chk-malla"> Mallado (Lat/Lon)</label>
                    </div>
                    
                    <button id="btn-reset" class="btn-reset-view">↺ Restablecer Vista</button>
                </div>
            `;
            return wrapper;
        }};
        uiControl.addTo(map);

        // LEYENDA (Colocada en bottomleft)
        const legend = L.control({{position: 'bottomleft'}});
        legend.onAdd = function () {{
            const div = L.DomUtil.create('div', 'legend');
            div.innerHTML = `
                <b>Vulnerabilidad</b>
                <i style="background:#D90404;"></i> 5 - Muy Alta<br>
                <i style="background:#F25C05;"></i> 4 - Alta<br>
                <i style="background:#F2B705;"></i> 3 - Media<br>
                <i style="background:#99C140;"></i> 2 - Baja<br>
                <i style="background:#2DC937;"></i> 1 - Muy Baja<br>
                <i style="background:#CCCCCC;"></i> Sin Datos
            `;
            return div;
        }};
        legend.addTo(map);

        // ==========================================
        // EVENTOS Y LÓGICA
        // ==========================================
        document.getElementById('btn-close-panel').onclick = function() {{
            document.getElementById('panel-container').style.display = 'none';
            document.getElementById('btn-open-panel').style.display = 'block';
        }};
        document.getElementById('btn-open-panel').onclick = function() {{
            document.getElementById('panel-container').style.display = 'block';
            document.getElementById('btn-open-panel').style.display = 'none';
        }};

        // Buscador Custom
        const searchInput = document.getElementById('search-input');
        const searchList = document.getElementById('search-list');
        const allNames = Array.from(searchNames).sort();

        function renderDropdown(filterText = "") {{
            searchList.innerHTML = "";
            let count = 0;
            allNames.forEach(name => {{
                if (name.toLowerCase().includes(filterText.toLowerCase())) {{
                    let div = document.createElement('div');
                    div.className = 'custom-dropdown-item';
                    div.innerText = name;
                    div.onclick = function() {{
                        searchInput.value = name;
                        searchList.style.display = 'none';
                        triggerSearch(name);
                    }};
                    searchList.appendChild(div);
                    count++;
                }}
            }});
            searchList.style.display = count > 0 ? 'block' : 'none';
        }}

        searchInput.addEventListener('focus', () => renderDropdown(searchInput.value));
        searchInput.addEventListener('input', (e) => renderDropdown(e.target.value));
        
        document.addEventListener('click', function(e) {{
            if (!searchInput.contains(e.target) && !searchList.contains(e.target)) {{
                searchList.style.display = 'none';
            }}
        }});

        function triggerSearch(selected) {{
            currentSelectedAquifer = selected; 

            if(activeTheme === 'vulnerability' && typeof updateVulnStyles === 'function') {{
                updateVulnStyles();
            }}
            if(activeTheme === 'hydro' && typeof layerHydro !== 'undefined' && layerHydro) {{
                layerHydro.eachLayer(l => layerHydro.resetStyle(l));
            }}
            
            let layers = activeTheme === 'vulnerability' ? indexVuln[selected] : indexHydro[selected];
            
            if(layers && layers.length > 0) {{
                let group = L.featureGroup(layers);
                map.flyToBounds(group.getBounds(), {{duration: 0.8, padding: [20, 20]}});
                layers.forEach(l => l.setStyle({{weight: 4, color: '#691C32', opacity: 1}})); 

                setTimeout(() => {{
                    let currentTheme = activeTheme === 'vulnerability' ? 'vuln' : 'hydro';
                    showDockedInfo(layers[0].feature.properties, currentTheme, layers[0]);
                }}, 800);
            }}
        }}

        const radioButtons = document.querySelectorAll('input[name="vuln-filter"]');
        radioButtons.forEach(radio => {{
            radio.addEventListener('change', function() {{
                currentVulnFilter = this.value;
                updateVulnStyles();
            }});
        }});

        document.getElementById('btn-vuln').onclick = function() {{
            activeTheme = 'vulnerability';
            this.classList.add('active'); 
            document.getElementById('btn-hydro').classList.remove('active');
            
            if(typeof layerHydro !== 'undefined' && layerHydro && map.hasLayer(layerHydro)) {{
                map.removeLayer(layerHydro);
            }}
            if(typeof layerVuln !== 'undefined' && layerVuln && !map.hasLayer(layerVuln)) {{
                map.addLayer(layerVuln);
            }}
            
            const legendEl = document.querySelector('.legend');
            if(legendEl) legendEl.style.display = 'block';
            const filterEl = document.getElementById('vuln-filter-section');
            if(filterEl) filterEl.style.display = 'block';
        }};

        document.getElementById('btn-hydro').onclick = function() {{
            activeTheme = 'hydro';
            this.classList.add('active'); 
            document.getElementById('btn-vuln').classList.remove('active');
            
            if(typeof layerVuln !== 'undefined' && layerVuln && map.hasLayer(layerVuln)) {{
                map.removeLayer(layerVuln);
            }}
            if(typeof layerHydro !== 'undefined' && layerHydro && !map.hasLayer(layerHydro)) {{
                map.addLayer(layerHydro);
            }}
            
            const legendEl = document.querySelector('.legend');
            if(legendEl) legendEl.style.display = 'none';
            const filterEl = document.getElementById('vuln-filter-section');
            if(filterEl) filterEl.style.display = 'none';
        }};

        document.getElementById('op-slider').oninput = function(e) {{
            currentOpacity = parseFloat(e.target.value);
            document.getElementById('op-val').innerText = Math.round(currentOpacity * 100) + '%';
            if(activeTheme === 'vulnerability') updateVulnStyles();
            if(activeTheme === 'hydro' && layerHydro) layerHydro.setStyle({{fillOpacity: currentOpacity}});
        }};

        let tempMarker;
        document.getElementById('btn-coords').onclick = function() {{
            let lat = parseFloat(document.getElementById('coord-lat').value);
            let lon = parseFloat(document.getElementById('coord-lon').value);
            let name = document.getElementById('coord-name').value || 'Punto Buscado';
            
            if(isNaN(lat) || isNaN(lon)) return alert("Ingresa coordenadas válidas");
            
            if(tempMarker) map.removeLayer(tempMarker);
            tempMarker = L.marker([lat, lon]).addTo(map)
                .bindPopup(`<b>${{name}}</b><br>Lat: ${{lat}}<br>Lon: ${{lon}}`).openPopup();
            map.flyTo([lat, lon], 12, {{duration: 1}});
        }};

        document.getElementById('btn-reset').onclick = function() {{
            currentSelectedAquifer = "";
            currentVulnFilter = "all";
            document.querySelector('input[name="vuln-filter"][value="all"]').checked = true;
            document.getElementById('search-input').value = ""; 
            
            if(activeTheme === 'vulnerability') updateVulnStyles();
            if(activeTheme === 'hydro' && layerHydro) layerHydro.eachLayer(l => layerHydro.resetStyle(l));
            
            closeDockedInfo();
            map.flyTo([23.6345, -102.5528], 5, {{duration: 1}});
            if(tempMarker) map.removeLayer(tempMarker);
            map.closePopup();
        }};

        document.getElementById('chk-pozos').onchange = function(e) {{
            if(e.target.checked && layerPozos) map.addLayer(layerPozos);
            else if(layerPozos) map.removeLayer(layerPozos);
        }};
        document.getElementById('chk-c10').onchange = function(e) {{
            if(e.target.checked && layerCosta10) map.addLayer(layerCosta10);
            else if(layerCosta10) map.removeLayer(layerCosta10);
        }};
        document.getElementById('chk-c1').onchange = function(e) {{
            if(e.target.checked && layerCosta1) map.addLayer(layerCosta1);
            else if(layerCosta1) map.removeLayer(layerCosta1);
        }};
        
        document.getElementById('chk-malla').onchange = function(e) {{
            if(e.target.checked) {{
                if(!graticuleLayer && typeof L.latlngGraticule !== 'undefined') {{
                    graticuleLayer = L.latlngGraticule({{
                        showLabel: true,
                        color: '#444',
                        weight: 0.8,
                        opacity: 0.6,
                        fontColor: '#222'
                    }});
                }}
                if(graticuleLayer) graticuleLayer.addTo(map);
            }} else if(graticuleLayer) {{
                map.removeLayer(graticuleLayer);
            }}
        }};

    </script>
</body>
</html>
"""

# Renderizar el HTML en Streamlit
components.html(html_code, height=800)