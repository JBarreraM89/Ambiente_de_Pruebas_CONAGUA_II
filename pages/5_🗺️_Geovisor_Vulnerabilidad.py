# -*- coding: utf-8 -*-
"""
Geovisor Nacional de Vulnerabilidad de Acuíferos (Arquitectura Vector Tiles PMTiles + MapLibre GL JS)
- Carga progresiva sin simplificación destructiva desde static/vulnerabilidad_nacional.pmtiles.
- Catálogo extensible de capas de vulnerabilidad preparado para nuevos mapas temáticos.
- Ficha lateral acoplada (Docked Inspector) con desglose oficial multi-clase (km² y %) por acuífero.
- Exportación PNG por composición WebGL/Canvas sin errores CORS, pantalla completa estable y mallado limpio.
"""

import json
import logging
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from core.data_loader import CARPETA_DATOS
from core.pmtiles_server import obtener_url_pmtiles
from utils.styles import banner_institucional, inyectar_css_oficial

logger = logging.getLogger(__name__)

# ==========================================
# 1. CONFIGURACIÓN GLOBAL DE PÁGINA
# ==========================================
st.set_page_config(layout="wide")
inyectar_css_oficial()
banner_institucional()

st.markdown("""
    <style>
        .block-container {
            padding-top: 0.9rem;
            padding-bottom: 0rem;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
            max-width: 100%;
        }
        iframe {
            width: 100%;
            height: 78vh !important;
            min-height: 540px;
            border: none;
            border-radius: 8px;
        }
    </style>
""", unsafe_allow_html=True)

st.subheader("🌍 Geovisor Nacional de Vulnerabilidad de Acuíferos")


# ==========================================
# 2. CATÁLOGO DE MAPAS Y CARGA LIGERA (< 100 KB)
# ==========================================
CATALOGO_MAPAS = [
    {
        "id": "vulnerabilidad",
        "nombre": "Vulnerabilidad (SEAG-INDEX)",
        "pmtiles": "vulnerabilidad_nacional.pmtiles",
        "source_layer": "vulnerabilidad",
        "metodologia": "SEAG-INDEX",
        "campo_clase": "v",
    },
    # Futuros mapas de vulnerabilidad (p. ej. DRASTIC, GOD, AVI) se registran aquí
    # con su archivo .pmtiles en static/ sin duplicar código HTML/JS.
]


def _json_seguro_html(obj):
    texto = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return texto.replace("</", "<\\/").replace("<!--", "<\\!--")


@st.cache_data(show_spinner="Cargando catálogo de acuíferos...")
def cargar_indice_vulnerabilidad(ruta_str: str):
    ruta = Path(ruta_str)
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


RUTA_INDICE = CARPETA_DATOS / "web" / "vulnerabilidad_index.json"
indice_vuln = cargar_indice_vulnerabilidad(str(RUTA_INDICE))

if indice_vuln is None:
    st.error(
        "No se encontró el catálogo espacial `data/web/vulnerabilidad_index.json`. "
        "Ejecuta `python data/convertidor_vulnerabilidad_pmtiles.py` para generar las teselas vectoriales."
    )
    st.stop()

# Asegura el servicio HTTP Range local (127.0.0.1:8515) o URL CDN en Cloud para cada capa del catálogo
catalogo_runtime = []
for capa in CATALOGO_MAPAS:
    pmtiles_url = obtener_url_pmtiles(nombre_archivo=capa["pmtiles"])
    catalogo_runtime.append({**capa, "url": pmtiles_url})

# ==========================================
# 3. PLANTILLA FRONTEND (MAPLIBRE GL JS + PMTILES)
# ==========================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
    <style>
        html, body {
            margin: 0; padding: 0; height: 100%; width: 100%; overflow: hidden;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #e9ecef;
        }
        #map { width: 100%; height: 100%; background-color: #e5e5e5; position: relative; }

        /* Badge de carga progresiva */
        .loading-pill {
            position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
            background: rgba(105, 28, 50, 0.92); color: #ffffff;
            border: 1px solid #BC955C; border-radius: 999px;
            padding: 5px 14px; font-size: 12px; font-weight: 600;
            box-shadow: 0 3px 12px rgba(0, 0, 0, 0.25);
            z-index: 12000; display: flex; align-items: center; gap: 8px;
            pointer-events: none; transition: opacity 0.3s ease;
        }
        .loading-pill.hidden { opacity: 0; }
        .spinner-dot {
            width: 8px; height: 8px; border-radius: 50%; background: #D4C19C;
            animation: pulseDot 0.9s infinite alternate;
        }
        @keyframes pulseDot {
            from { opacity: 0.35; transform: scale(0.85); }
            to { opacity: 1; transform: scale(1.2); }
        }

        /* Overrides MapLibre */
        .maplibregl-control-container { pointer-events: none; }
        .maplibregl-ctrl-top-right, .maplibregl-ctrl-top-left,
        .maplibregl-ctrl-bottom-right, .maplibregl-ctrl-bottom-left {
            display: flex !important; pointer-events: none !important; padding: 0 !important;
        }
        .maplibregl-ctrl { pointer-events: auto !important; float: none !important; clear: none !important; margin: 0 !important; }

        /* TOP-LEFT */
        .maplibregl-ctrl-top-left {
            flex-direction: column !important; align-items: flex-start !important;
            z-index: 9999 !important; max-height: calc(100vh - 16px);
        }
        .maplibregl-ctrl-top-left .maplibregl-ctrl { margin: 10px 0 0 10px !important; }

        /* TOP-RIGHT (Barra de botones fija al borde derecho) */
        .maplibregl-ctrl-top-right {
            flex-direction: column !important; align-items: flex-end !important;
            z-index: 9000 !important;
        }
        .maplibregl-ctrl-top-right .maplibregl-ctrl { margin: 10px 10px 0 0 !important; }
        #custom-fs-container { order: 1; }
        #custom-layer-container { order: 2; }
        .maplibregl-ctrl-top-right .maplibregl-ctrl-group { order: 3 !important; box-shadow: 0 1px 5px rgba(0,0,0,0.45) !important; }

        /* BOTTOM-RIGHT */
        .maplibregl-ctrl-bottom-right {
            flex-direction: column !important; align-items: flex-end !important;
            justify-content: flex-end !important; z-index: 8000 !important;
        }
        .maplibregl-ctrl-bottom-right .maplibregl-ctrl { margin: 0 10px 0 0 !important; }
        #print-ctrl-container { order: 1; margin-bottom: 6px !important; }
        .maplibregl-ctrl-scale { order: 2; margin-bottom: 4px !important; margin-right: 10px !important; }
        #logo-ctrl-container { order: 3; margin-bottom: 4px !important; }
        .maplibregl-ctrl-attrib {
            order: 4; margin: 0 !important; background: rgba(255,255,255,0.88) !important;
            font-size: 11px !important; padding: 2px 6px !important; border-radius: 4px 0 0 0;
        }

        /* BOTTOM-LEFT (Fija siempre en esquina inferior izquierda, sin moverse) */
        .maplibregl-ctrl-bottom-left {
            flex-direction: column !important; align-items: flex-start !important;
            justify-content: flex-end !important; z-index: 5000 !important;
        }
        .maplibregl-ctrl-bottom-left .maplibregl-ctrl {
            margin: 0 0 10px 10px !important;
        }

        /* Botón Pantalla Completa */
        .custom-fullscreen-btn {
            width: 32px; height: 32px; background: #ffffff; border-radius: 4px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            box-shadow: 0 1px 5px rgba(0,0,0,0.45); border: 1px solid rgba(0,0,0,0.12);
            box-sizing: border-box;
        }
        .custom-fullscreen-btn:hover { background: #f4f4f4; }

        /* Selector Capas Base */
        .leaflet-control-layers {
            box-shadow: 0 1px 5px rgba(0,0,0,0.4); background: #fff;
            border-radius: 5px; transition: padding 0.1s;
        }
        .leaflet-control-layers:hover { padding: 6px 10px 6px 6px; }
        .leaflet-control-layers-toggle {
            width: 34px; height: 34px; display: block;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23333' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolygon points='12 2 2 7 12 12 22 7 12 2'/%3E%3Cpolyline points='2 12 12 17 22 12'/%3E%3Cpolyline points='2 17 12 22 22 17'/%3E%3C/svg%3E");
            background-size: 20px 20px; background-position: center; background-repeat: no-repeat;
        }
        .leaflet-control-layers:hover .leaflet-control-layers-toggle { display: none; }
        .leaflet-control-layers-list {
            display: none; font-size: 12px; color: #333; margin: 0; min-width: 155px;
        }
        .leaflet-control-layers:hover .leaflet-control-layers-list { display: block; }
        .leaflet-control-layers-base label { display: block; margin: 0; padding: 0; cursor: pointer; font-weight: normal !important; }
        .leaflet-control-layers-base label div { display: flex; align-items: center; margin-bottom: 4px; }
        .leaflet-control-layers-base input[type="radio"] { margin: 0 6px 0 0; cursor: pointer; accent-color: #691C32; }
        .leaflet-control-layers-base span { font-size: 12px; white-space: nowrap; }

        /* Docked Inspector (flotante a la izquierda de la barra derecha para no chocar con Imprimir/Escala/Logo) */
        .docked-panel {
            position: absolute; top: 10px; right: 58px; z-index: 8900;
            background: #ffffff !important; width: 295px !important; border-radius: 8px !important;
            overflow: hidden !important; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25) !important;
            border-top: 4px solid #691C32 !important; border-left: 1px solid #E2D9C8 !important;
            border-right: 1px solid #E2D9C8 !important; border-bottom: 1px solid #E2D9C8 !important;
            display: none; max-height: calc(100vh - 115px); flex-direction: column;
        }
        .docked-header { background: #691C32 !important; color: #ffffff !important; padding: 10px 14px !important; position: relative !important; }
        .docked-title { font-size: 13.5px !important; font-weight: 700 !important; display: block !important; padding-right: 22px !important; line-height: 1.25 !important; color: #ffffff !important; }
        .docked-sub { font-size: 11px !important; color: #D4C19C !important; display: block !important; margin-top: 3px !important; letter-spacing: 0.4px !important; }
        .docked-close {
            position: absolute !important; top: 8px !important; right: 10px !important; color: #ffffff !important;
            cursor: pointer !important; font-size: 20px !important; font-weight: bold !important; line-height: 1 !important;
        }
        .docked-close:hover { color: #BC955C !important; }
        .docked-body { padding: 12px 14px !important; background: #ffffff !important; overflow-y: auto !important; }
        .card-badge {
            display: inline-block !important; padding: 4px 10px !important; border-radius: 12px !important;
            color: #ffffff !important; font-size: 11px !important; font-weight: 700 !important;
            margin-bottom: 8px !important; text-shadow: 0 1px 2px rgba(0,0,0,0.35) !important;
        }
        .section-mini-title {
            font-size: 11px; font-weight: 700; color: #691C32; text-transform: uppercase;
            letter-spacing: 0.4px; margin: 8px 0 5px 0;
        }
        .stacked-bar {
            display: flex; width: 100%; height: 10px; border-radius: 5px; overflow: hidden;
            background: #ECEAE6; margin-bottom: 8px; border: 1px solid #DDD6C8;
        }
        .card-table { width: 100% !important; border-collapse: collapse !important; font-size: 11.5px !important; }
        .card-table td { padding: 4px 0 !important; border-bottom: 1px solid #F0ECE6 !important; color: #333333 !important; }
        .card-table td.label { color: #5F6368 !important; font-weight: 500 !important; }
        .card-table td.val { font-weight: 600 !important; text-align: right !important; color: #1A1A1A !important; white-space: nowrap; }
        .swatch-dot {
            display: inline-block; width: 9px; height: 9px; border-radius: 2px;
            margin-right: 5px; vertical-align: middle; border: 1px solid rgba(0,0,0,0.25);
        }
        .btn-focus-aq {
            width: 100%; margin-top: 9px; padding: 6px 10px; border-radius: 5px;
            background: #FAF6F0 !important; color: #691C32 !important;
            border: 1px solid #BC955C !important; font-size: 11.5px; font-weight: 600;
            cursor: pointer; transition: background 0.15s ease;
        }
        .btn-focus-aq:hover { background: #F1E8D9 !important; }

        /* Tooltip Minimalista (siempre por encima de la ficha lateral) */
        .maplibregl-popup { z-index: 9500 !important; }
        .minimal-popup .maplibregl-popup-content {
            background: rgba(26, 26, 26, 0.92) !important; color: #ffffff !important;
            border: 1px solid #BC955C !important; border-left: 3px solid #BC955C !important;
            border-radius: 4px !important; font-size: 11px !important; padding: 5px 9px !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important; pointer-events: none !important;
        }
        .minimal-popup .maplibregl-popup-tip { display: none !important; }
        .marker-popup .maplibregl-popup-content {
            padding: 12px 16px !important; border-radius: 6px !important;
            border-top: 4px solid #691C32 !important; box-shadow: 0 4px 15px rgba(0,0,0,0.2) !important;
        }

        /* Panel Controles (compacto para dejar libre la leyenda fija abajo) */
        .leaflet-custom-controls {
            background: #ffffff; padding: 11px 13px; border-radius: 8px; box-sizing: border-box;
            box-shadow: 0 4px 18px rgba(0,0,0,0.18); width: 310px; max-height: calc(100vh - 178px);
            overflow-y: auto; overflow-x: hidden; z-index: 9999 !important; position: relative;
            border-top: 4px solid #691C32; border-left: 1px solid #E2D9C8;
            border-right: 1px solid #E2D9C8; border-bottom: 1px solid #E2D9C8;
        }
        .leaflet-custom-controls::-webkit-scrollbar { width: 6px; }
        .leaflet-custom-controls::-webkit-scrollbar-track { background: transparent; margin: 8px 0; }
        .leaflet-custom-controls::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 8px; }
        .leaflet-custom-controls::-webkit-scrollbar-thumb:hover { background: #BC955C; }
        .panel-close-button {
            float: right; cursor: pointer; font-size: 20px; font-weight: bold;
            color: #888888; margin-top: -3px; line-height: 1;
        }
        .panel-close-button:hover { color: #691C32; }
        .leaflet-open-button {
            background: #691C32 !important; color: #ffffff !important; width: 38px; height: 38px;
            border-radius: 50% !important; line-height: 36px; text-align: center; cursor: pointer;
            box-shadow: 0 3px 10px rgba(105, 28, 50, 0.35); font-size: 18px; font-weight: bold;
            border: 1.5px solid #BC955C !important; display: none; z-index: 9999 !important;
        }
        .leaflet-open-button:hover { background: #4A1424 !important; transform: scale(1.06); }

        .control-section { margin-bottom: 9px; position: relative; }
        .control-section label { font-weight: 600; font-size: 11.5px; color: #333333; display: block; margin-bottom: 3px; }
        .theme-switch { display: flex; flex-wrap: wrap; border: 1px solid #BC955C; border-radius: 6px; overflow: hidden; background: #FAF8F5; }
        .theme-btn {
            flex: 1; padding: 6px 8px; border: none; background: transparent !important;
            cursor: pointer; font-size: 11.5px; color: #555555 !important; font-weight: 500;
        }
        .theme-btn.active { background: #691C32 !important; color: #ffffff !important; font-weight: 700; }

        input[type="text"], input[type="number"] {
            width: 100%; padding: 5px 8px; box-sizing: border-box; border: 1px solid #D1D5DB;
            border-radius: 5px; font-size: 11.5px; margin-bottom: 4px; background: #FAFAFA;
        }
        input[type="text"]:focus, input[type="number"]:focus {
            outline: none; border-color: #691C32; background: #ffffff;
            box-shadow: 0 0 0 2px rgba(105, 28, 50, 0.15);
        }
        input[type="range"] { width: 100%; accent-color: #691C32; cursor: pointer; }
        .radio-group { display: flex; flex-wrap: wrap; gap: 6px 9px; font-size: 11.5px; margin-top: 2px; }
        .radio-group label { font-weight: normal !important; display: inline-flex; align-items: center; cursor: pointer; margin-bottom: 0 !important; }
        .radio-group input[type="radio"], input[type="checkbox"] { accent-color: #691C32; cursor: pointer; margin-right: 4px; }
        .chk-row { font-weight: normal !important; display: flex !important; align-items: center; margin-bottom: 3px !important; cursor: pointer; font-size: 11.5px !important; }

        .custom-dropdown { position: relative; width: 100%; }
        .custom-dropdown-list {
            position: absolute; top: 100%; left: 0; right: 0; background: white;
            border: 1px solid #BC955C; border-top: none; border-radius: 0 0 6px 6px;
            max-height: 170px; overflow-y: auto; z-index: 10000; display: none;
            box-shadow: 0 4px 10px rgba(0,0,0,0.12);
        }
        .custom-dropdown-item { padding: 7px 10px; font-size: 11.5px; cursor: pointer; border-bottom: 1px solid #F3EFEA; }
        .custom-dropdown-item:hover { background-color: #FAF5EE; color: #691C32; font-weight: 600; }

        .flex-row { display: flex; gap: 6px; }
        .flex-row input { width: 50%; }
        .action-button {
            width: 100%; padding: 6px 10px; background: #691C32 !important; color: #ffffff !important;
            border: 1px solid #BC955C !important; border-radius: 5px; cursor: pointer;
            font-weight: 600; font-size: 11.5px;
        }
        .action-button:hover { background: #4A1424 !important; }
        .btn-clear-point {
            width: 34px; padding: 6px 0; background: #6F7271 !important; color: #ffffff !important;
            border: none; border-radius: 5px; cursor: pointer; font-size: 13px; text-align: center;
        }
        .btn-clear-point:hover { background: #4A4D4E !important; }
        .btn-reset-view {
            width: 100%; padding: 6px 10px; background: #6F7271 !important; color: #ffffff !important;
            border: none; border-radius: 5px; cursor: pointer; font-weight: 600; font-size: 11.5px; margin-top: 3px;
        }
        .btn-reset-view:hover { background: #4A4D4E !important; }

        /* Inferior Derecho */
        .print-btn {
            background: white; border: 1px solid rgba(0,0,0,0.2); border-radius: 4px;
            cursor: pointer; padding: 0; font-size: 16px; color: #333;
            display: flex; align-items: center; justify-content: center;
            width: 32px; height: 32px; box-shadow: 0 1px 5px rgba(0,0,0,0.35);
        }
        .print-btn:hover { background: #f4f4f4; }
        .custom-logo { display: block; height: 36px; opacity: 0.95; max-width: 110px; object-fit: contain; }

        /* Leyenda Inferior Izquierda */
        .legend {
            background: white; padding: 10px 12px; border-radius: 6px; font-size: 12px; line-height: 18px;
            color: #333; box-shadow: 0 2px 8px rgba(0,0,0,0.22); width: 155px; box-sizing: border-box;
            border: 1px solid #E2D9C8;
        }
        .legend-header { display: flex; justify-content: space-between; align-items: center; cursor: pointer; font-size: 12.5px; font-weight: 700; color: #691C32; }
        .legend-body { overflow: hidden; transition: max-height 0.25s ease; margin-top: 7px; }
        .legend-body.collapsed { max-height: 0 !important; margin-top: 0 !important; }
        .legend-item { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; font-size: 11.5px; }
        .legend-swatch { width: 13px; height: 13px; flex-shrink: 0; border: 1px solid #444444; border-radius: 2px; }
    </style>
</head>
<body>
    <div id="map">
        <div id="tile-loading-pill" class="loading-pill">
            <span class="spinner-dot"></span>
            <span id="loading-text">Cargando teselas vectoriales...</span>
        </div>
    </div>

    <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <script src="https://unpkg.com/pmtiles@2.11.0/dist/index.js"></script>

    <script>
        // ==========================================
        // 1. CATÁLOGO DE CAPAS E ÍNDICE LIGERO
        // ==========================================
        const CATALOGO_MAPAS = __CATALOGO_MAPAS__;
        const INDICE_META = __INDICE_META__;
        const AQUIFER_INDEX = INDICE_META.acuiferos || {};

        const vulnColors = {
            '5': '#D90404', '4': '#F25C05', '3': '#F2B705',
            '2': '#99C140', '1': '#2DC937', 'default': '#94A3B8'
        };
        const vulnLabels = {
            '5': '5 - Muy Alta', '4': '4 - Alta', '3': '3 - Media',
            '2': '2 - Baja', '1': '1 - Muy Baja'
        };

        // Registrar protocolo PMTiles
        const pmtilesProtocol = new pmtiles.Protocol();
        maplibregl.addProtocol("pmtiles", pmtilesProtocol.tile);

        const viewBounds = [[-124.4, 13.5], [-80.5, 33.5]];
        const limitBounds = [[-130.0, 8.0], [-72.0, 39.0]];

        const map = new maplibregl.Map({
            container: 'map',
            style: {
                version: 8,
                glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
                sources: {
                    'basemap': {
                        type: 'raster',
                        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
                        tileSize: 256,
                        attribution: '<b>© Esri</b>'
                    }
                },
                layers: [{ id: 'basemap-layer', type: 'raster', source: 'basemap', minzoom: 0, maxzoom: 22 }]
            },
            bounds: viewBounds,
            fitBoundsOptions: { padding: 12 },
            maxBounds: limitBounds,
            minZoom: 3.5,
            renderWorldCopies: false,
            fadeDuration: 0,
            preserveDrawingBuffer: true,
            attributionControl: false
        });

        map.addControl(new maplibregl.AttributionControl({ compact: false }), 'bottom-right');

        let activeMapCfg = CATALOGO_MAPAS[0];
        let activeBasemapName = "Neutral (defecto)";
        let currentOpacity = 0.75;
        let currentVulnFilter = 'all';
        let hoveredFeatureId = null;
        let clickedFeatureId = null;
        let searchedClave = null;
        let searchedName = null;
        let selectedPolygonProps = null;
        let activeCoordPoint = null;
        let latestGraticuleData = { type: 'FeatureCollection', features: [] };

        const hoverPopup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'minimal-popup' });

        // ==========================================
        // 2. CONTROLES PERSONALIZADOS (UI)
        // ==========================================
        class CustomControl {
            constructor(id, html) { this.id = id; this.html = html; }
            onAdd() {
                this._container = document.createElement('div');
                this._container.id = this.id;
                this._container.className = 'maplibregl-ctrl';
                this._container.innerHTML = this.html;
                return this._container;
            }
            onRemove() { if (this._container.parentNode) this._container.parentNode.removeChild(this._container); }
        }

        const iconExpand = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
        const iconCompress = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;
        map.addControl(new CustomControl('custom-fs-container', `<div id="fs-btn" class="custom-fullscreen-btn" title="Pantalla completa">${iconExpand}</div>`), 'top-right');

        const basemapsUrls = {
            "Neutral (defecto)": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
            "OpenStreetMap": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "Estándar (ESRI)": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
            "Satélite (ESRI)": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            "Topográfico (ESRI)": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
            "Gris Oscuro (ESRI)": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        };
        const radiosHtml = Object.keys(basemapsUrls).map((k, i) => `
            <label><div><input type="radio" name="basemap_radio" value="${k}" ${i === 0 ? 'checked' : ''}><span>${k}</span></div></label>
        `).join('');

        map.addControl(new CustomControl('custom-layer-container', `
            <div class="leaflet-control-layers custom-leaflet-layers">
                <a class="leaflet-control-layers-toggle" href="#" title="Mapas base"></a>
                <div class="leaflet-control-layers-list"><div class="leaflet-control-layers-base">${radiosHtml}</div></div>
            </div>
        `), 'top-right');

        map.addControl(new maplibregl.NavigationControl({ showCompass: true, showZoom: true }), 'top-right');
        document.getElementById('map').insertAdjacentHTML('beforeend', '<div id="docked-panel" class="docked-panel"></div>');

        const selectorMapasHtml = CATALOGO_MAPAS.length > 1
            ? `<div class="control-section"><label>Capa Temática:</label><div class="theme-switch" id="catalog-switch">${
                CATALOGO_MAPAS.map((m, idx) => `<button class="theme-btn ${idx === 0 ? 'active' : ''}" data-map-id="${m.id}">${m.nombre}</button>`).join('')
              }</div></div>`
            : '';

        const totalAq = Object.keys(AQUIFER_INDEX).length;
        const menuHtml = `
            <div id="btn-open-panel" class="leaflet-open-button" title="Mostrar controles">☰</div>
            <div id="panel-container" class="leaflet-custom-controls">
                <span id="btn-close-panel" class="panel-close-button" title="Ocultar controles">&times;</span>
                <h3 style="margin:0 0 10px 0; color:#691C32; font-size:15px;">⚙️ Controles</h3>
                ${selectorMapasHtml}
                <div class="control-section custom-dropdown">
                    <label>Buscar Acuífero (${totalAq}):</label>
                    <input type="text" id="search-input" placeholder="-- Escribe clave o nombre --" autocomplete="off">
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
                    <input type="text" id="coord-name" placeholder="Etiqueta (Ej. Pozo 1)" maxlength="60">
                    <div class="flex-row">
                        <input type="number" id="coord-lat" placeholder="Lat. (-90 a 90)" step="any">
                        <input type="number" id="coord-lon" placeholder="Lon. (-180 a 180)" step="any">
                    </div>
                    <div class="flex-row" style="margin-top: 4px;">
                        <button id="btn-coords" class="action-button" style="flex: 1;">Ubicar en Mapa</button>
                        <button id="btn-clear-coord" class="btn-clear-point" title="Borrar punto">🗑️</button>
                    </div>
                    <div id="coord-error" style="display:none; color:#D90404; font-size:11px; margin-top:5px; font-weight:600; text-align:center;"></div>
                </div>
                <div class="control-section">
                    <label>Capas Adicionales:</label>
                    <label id="lbl-c10" class="chk-row"><input type="checkbox" id="chk-c10"> Línea Costa (10 km)</label>
                    <label id="lbl-c1" class="chk-row"><input type="checkbox" id="chk-c1"> Línea Costa (1 km)</label>
                    <label class="chk-row"><input type="checkbox" id="chk-malla"> Mallado (Lat/Lon)</label>
                </div>
                <button id="btn-reset" class="btn-reset-view">↺ Restablecer Vista</button>
            </div>
        `;
        map.addControl(new CustomControl('main-menu-container', menuHtml), 'top-left');

        map.addControl(new CustomControl('print-ctrl-container', `<button id="btn-print" class="print-btn" title="Descargar mapa en PNG">🖨️</button>`), 'bottom-right');
        map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }), 'bottom-right');
        map.addControl(new CustomControl('logo-ctrl-container', `<img class="custom-logo" src="https://raw.githubusercontent.com/Dchable16/geovisor_vulnerabilidad/main/logos/Logo_SSIG.png" crossorigin="anonymous">`), 'bottom-right');

        const legendHtml = `
            <div class="legend" id="legend-container">
                <div class="legend-header" id="legend-toggle">
                    <span>Simbología</span>
                    <span id="legend-icon" style="font-size:11px;">▼</span>
                </div>
                <div class="legend-body" id="legend-body" style="max-height: 200px;">
                    <div class="legend-item"><span class="legend-swatch" style="background:#D90404;"></span><span>5 - Muy Alta</span></div>
                    <div class="legend-item"><span class="legend-swatch" style="background:#F25C05;"></span><span>4 - Alta</span></div>
                    <div class="legend-item"><span class="legend-swatch" style="background:#F2B705;"></span><span>3 - Media</span></div>
                    <div class="legend-item"><span class="legend-swatch" style="background:#99C140;"></span><span>2 - Baja</span></div>
                    <div class="legend-item"><span class="legend-swatch" style="background:#2DC937;"></span><span>1 - Muy Baja</span></div>
                </div>
            </div>
        `;
        map.addControl(new CustomControl('legend-wrapper', legendHtml), 'bottom-left');

        document.getElementById('legend-toggle').onclick = function() {
            const body = document.getElementById('legend-body');
            const icon = document.getElementById('legend-icon');
            const collapsed = body.classList.toggle('collapsed');
            icon.innerText = collapsed ? '▲' : '▼';
        };

        // Ocultar checkboxes de costa si el paquete PMTiles no incluyó esas capas
        if (!INDICE_META.has_costa_10km) document.getElementById('lbl-c10').style.display = 'none';
        if (!INDICE_META.has_costa_1km) document.getElementById('lbl-c1').style.display = 'none';

        // ==========================================
        // 3. HELPERS DE RENDER Y FICHA LATERAL
        // ==========================================
        function findAquiferKeyByClave(clave) {
            const cNorm = String(clave || '').trim().padStart(4, '0');
            for (const [key, meta] of Object.entries(AQUIFER_INDEX)) {
                if (meta.clave === cNorm) return key;
            }
            return null;
        }

        function escapeHtml(txt) {
            const div = document.createElement('div');
            div.textContent = txt == null ? '' : String(txt);
            return div.innerHTML;
        }

        function showDockedInfo(aquiferKey, clickedPolyClass) {
            const panel = document.getElementById('docked-panel');
            const meta = AQUIFER_INDEX[aquiferKey];
            if (!meta) return;

            const predom = String(meta.clase_predominante || '');
            const badgeClass = clickedPolyClass != null ? String(clickedPolyClass) : predom;
            const badgePrefix = clickedPolyClass != null ? 'Zona seleccionada: ' : 'Clase predominante: ';
            const badgeColor = vulnColors[badgeClass] || vulnColors.default;
            const badgeLabel = vulnLabels[badgeClass] || 'Sin Datos';

            const ordenClases = ['5', '4', '3', '2', '1'];
            let barHtml = '';
            let rowsHtml = '';
            ordenClases.forEach(c => {
                const info = meta.clases ? meta.clases[c] : null;
                if (!info || !info.count) return;
                barHtml += `<div title="${vulnLabels[c]}: ${info.pct}% (${info.area_km2.toLocaleString('es-MX')} km²)" style="width:${info.pct}%; background:${vulnColors[c]};"></div>`;
                rowsHtml += `
                    <tr>
                        <td class="label"><span class="swatch-dot" style="background:${vulnColors[c]};"></span>${vulnLabels[c]}</td>
                        <td class="val">${info.pct.toFixed(1)}% · ${info.area_km2.toLocaleString('es-MX', { maximumFractionDigits: 1 })} km²</td>
                    </tr>
                `;
            });

            panel.innerHTML = `
                <div class="docked-header">
                    <span class="docked-close" title="Cerrar ficha">&times;</span>
                    <span class="docked-title">${escapeHtml(meta.nombre)}</span>
                    <span class="docked-sub">CLAVE: ${escapeHtml(meta.clave)} · ${escapeHtml(activeMapCfg.metodologia)}</span>
                </div>
                <div class="docked-body">
                    <div class="card-badge" style="background:${badgeColor};">${badgePrefix}${badgeLabel}</div>
                    <div class="section-mini-title">Distribución en el Acuífero</div>
                    <div class="stacked-bar">${barHtml}</div>
                    <table class="card-table">
                        ${rowsHtml}
                        <tr>
                            <td class="label" style="font-weight:700;color:#691C32 !important;">Superficie total</td>
                            <td class="val" style="color:#691C32 !important;">${meta.area_km2.toLocaleString('es-MX', { maximumFractionDigits: 1 })} km² (${meta.poligonos} pol.)</td>
                        </tr>
                    </table>
                    <button id="btn-focus-aq" class="btn-focus-aq">🔎 Enfocar Acuífero completo</button>
                </div>
            `;
            panel.style.display = 'flex';
            panel.querySelector('.docked-close').onclick = clearSelection;
            panel.querySelector('#btn-focus-aq').onclick = () => triggerSearch(aquiferKey);
        }

        function getVulnFillOpacityExpr() {
            const fVal = currentVulnFilter === 'all' ? -1 : parseInt(currentVulnFilter, 10);
            if (fVal === -1) return currentOpacity;
            return ['case', ['==', ['get', 'v'], fVal], currentOpacity, 0.08];
        }

        function getVulnLineColorExpr() {
            const fVal = currentVulnFilter === 'all' ? -1 : parseInt(currentVulnFilter, 10);
            if (fVal === -1) {
                return [
                    'case',
                    ['boolean', ['feature-state', 'selected'], false], '#691C32',
                    ['boolean', ['feature-state', 'hover'], false], '#007BFF',
                    '#475569'
                ];
            }
            return [
                'case',
                ['boolean', ['feature-state', 'selected'], false], '#691C32',
                ['boolean', ['feature-state', 'hover'], false], '#007BFF',
                ['!=', ['get', 'v'], fVal], '#CBD5E1',
                '#334155'
            ];
        }

        function getVulnLineWidthExpr() {
            const fVal = currentVulnFilter === 'all' ? -1 : parseInt(currentVulnFilter, 10);
            if (fVal === -1) {
                return [
                    'case',
                    ['boolean', ['feature-state', 'selected'], false], 3.0,
                    ['boolean', ['feature-state', 'hover'], false], 2.5,
                    0.75
                ];
            }
            return [
                'case',
                ['boolean', ['feature-state', 'selected'], false], 3.0,
                ['boolean', ['feature-state', 'hover'], false], 2.5,
                ['!=', ['get', 'v'], fVal], 0.35,
                1.0
            ];
        }

        function _setLineStateSafe(fid, stateObj) {
            if (fid == null || !map.getSource('vuln-src')) return;
            try {
                map.setFeatureState({ source: 'vuln-src', sourceLayer: activeMapCfg.source_layer, id: fid }, stateObj);
            } catch (e) {}
        }

        function setHoverFeature(fid) {
            const nextId = fid != null ? fid : null;
            if (hoveredFeatureId === nextId) return;
            if (hoveredFeatureId !== null) _setLineStateSafe(hoveredFeatureId, { hover: false });
            hoveredFeatureId = nextId;
            if (hoveredFeatureId !== null) _setLineStateSafe(hoveredFeatureId, { hover: true });
        }

        function setClickedFeature(fid) {
            const nextId = fid != null ? fid : null;
            if (clickedFeatureId === nextId) return;
            if (clickedFeatureId !== null) _setLineStateSafe(clickedFeatureId, { selected: false });
            clickedFeatureId = nextId;
            if (clickedFeatureId !== null) _setLineStateSafe(clickedFeatureId, { selected: true });
        }

        function clearSelection() {
            setClickedFeature(null);
            searchedClave = null;
            searchedName = null;
            selectedPolygonProps = null;
            if (map.getLayer('vuln-search-fill')) {
                map.setFilter('vuln-search-fill', ['==', ['get', 'c'], '__NONE__']);
                map.setFilter('vuln-search-line', ['==', ['get', 'c'], '__NONE__']);
            }
            document.getElementById('docked-panel').style.display = 'none';
        }

        function triggerSearch(aqKey) {
            const meta = AQUIFER_INDEX[aqKey];
            if (!meta) return;

            clearSelection();
            searchedClave = meta.clave;
            searchedName = aqKey;

            if (map.getLayer('vuln-search-fill')) {
                map.setFilter('vuln-search-fill', ['==', ['get', 'c'], searchedClave]);
                map.setFilter('vuln-search-line', ['==', ['get', 'c'], searchedClave]);
            }
            map.fitBounds([[meta.bounds[0], meta.bounds[1]], [meta.bounds[2], meta.bounds[3]]], { padding: 50, duration: 850 });
            showDockedInfo(aqKey, null);
        }

        // ==========================================
        // 4. INICIALIZACIÓN DE CAPAS PMTILES
        // ==========================================
        map.on('load', () => {
            const loadingPill = document.getElementById('tile-loading-pill');

            map.addSource('vuln-src', {
                type: 'vector',
                url: 'pmtiles://' + activeMapCfg.url,
                minzoom: 3,
                maxzoom: 11,
                promoteId: { [activeMapCfg.source_layer]: 'fid' }
            });

            map.addSource('graticule-src', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });

            map.addLayer({
                id: 'vuln-fill',
                type: 'fill',
                source: 'vuln-src',
                'source-layer': activeMapCfg.source_layer,
                paint: {
                    'fill-color': [
                        'match', ['get', 'v'],
                        5, vulnColors['5'],
                        4, vulnColors['4'],
                        3, vulnColors['3'],
                        2, vulnColors['2'],
                        1, vulnColors['1'],
                        vulnColors.default
                    ],
                    'fill-opacity': getVulnFillOpacityExpr()
                }
            });

            // Resaltado completo de acuífero buscado (debajo de vuln-line para no tapar el contorno azul de hover)
            map.addLayer({
                id: 'vuln-search-fill',
                type: 'fill',
                source: 'vuln-src',
                'source-layer': activeMapCfg.source_layer,
                filter: ['==', ['get', 'c'], '__NONE__'],
                paint: { 'fill-color': '#691C32', 'fill-opacity': 0.12 }
            });
            map.addLayer({
                id: 'vuln-search-line',
                type: 'line',
                source: 'vuln-src',
                'source-layer': activeMapCfg.source_layer,
                filter: ['==', ['get', 'c'], '__NONE__'],
                paint: { 'line-color': '#691C32', 'line-width': 2.2 }
            });

            map.addLayer({
                id: 'vuln-line',
                type: 'line',
                source: 'vuln-src',
                'source-layer': activeMapCfg.source_layer,
                paint: {
                    'line-color': getVulnLineColorExpr(),
                    'line-width': getVulnLineWidthExpr()
                }
            });

            if (INDICE_META.has_costa_10km) {
                map.addLayer({
                    id: 'c10-line', type: 'line', source: 'vuln-src', 'source-layer': 'costa_10km',
                    layout: { visibility: 'none' },
                    paint: { 'line-color': '#007BFF', 'line-width': 2.5, 'line-opacity': 0.85 }
                });
            }
            if (INDICE_META.has_costa_1km) {
                map.addLayer({
                    id: 'c1-line', type: 'line', source: 'vuln-src', 'source-layer': 'costa_1km',
                    layout: { visibility: 'none' },
                    paint: { 'line-color': '#FF0000', 'line-width': 2.5, 'line-opacity': 0.85 }
                });
            }

            map.addLayer({
                id: 'graticule-line', type: 'line', source: 'graticule-src',
                filter: ['==', ['geometry-type'], 'LineString'],
                layout: { visibility: 'none' },
                paint: { 'line-color': '#475569', 'line-width': 0.75, 'line-opacity': 0.55 }
            });
            map.addLayer({
                id: 'graticule-label-lat', type: 'symbol', source: 'graticule-src',
                filter: ['==', ['get', 'axis'], 'lat'],
                layout: {
                    visibility: 'none',
                    'text-field': ['get', 'label'],
                    'text-font': ['Open Sans Regular'],
                    'text-size': 11,
                    'symbol-placement': 'point',
                    'text-anchor': 'left',
                    'text-offset': [0.25, 0],
                    'text-allow-overlap': true,
                    'text-ignore-placement': true
                },
                paint: { 'text-color': '#1E293B', 'text-halo-color': '#FFFFFF', 'text-halo-width': 2 }
            });
            map.addLayer({
                id: 'graticule-label-lon', type: 'symbol', source: 'graticule-src',
                filter: ['==', ['get', 'axis'], 'lon'],
                layout: {
                    visibility: 'none',
                    'text-field': ['get', 'label'],
                    'text-font': ['Open Sans Regular'],
                    'text-size': 11,
                    'symbol-placement': 'point',
                    'text-anchor': 'top',
                    'text-offset': [0, 0.2],
                    'text-allow-overlap': true,
                    'text-ignore-placement': true
                },
                paint: { 'text-color': '#1E293B', 'text-halo-color': '#FFFFFF', 'text-halo-width': 2 }
            });

            map.once('idle', () => loadingPill.classList.add('hidden'));
            map.on('error', (ev) => {
                if (ev && ev.error) console.warn('MapLibre aviso:', ev.error.message || ev.error);
            });

            // Hover & Click sobre polígonos MVT (setFeatureState instantáneo solo en vuln-line)
            map.on('mousemove', 'vuln-fill', (e) => {
                if (!e.features || !e.features.length) return;
                map.getCanvas().style.cursor = 'pointer';
                const f = e.features[0];
                const fid = f.properties.fid != null ? f.properties.fid : f.id;
                const cambioPoligono = hoveredFeatureId !== fid;
                if (cambioPoligono) {
                    setHoverFeature(fid);
                    const clave = String(f.properties.c || '').padStart(4, '0');
                    const nom = f.properties.n || 'Sin Nombre';
                    const cls = String(f.properties.v || '');
                    const clsLbl = vulnLabels[cls] || 'S/D';
                    hoverPopup.setLngLat(e.lngLat).setHTML(`<b>${escapeHtml(clave)}</b> - ${escapeHtml(nom)}<br><span style="color:#D4C19C;">${escapeHtml(clsLbl)}</span>`);
                    if (!hoverPopup.isOpen()) hoverPopup.addTo(map);
                } else {
                    hoverPopup.setLngLat(e.lngLat);
                    if (!hoverPopup.isOpen()) hoverPopup.addTo(map);
                }
            });

            map.on('mouseleave', 'vuln-fill', () => {
                map.getCanvas().style.cursor = '';
                setHoverFeature(null);
                hoverPopup.remove();
            });

            map.on('click', 'vuln-fill', (e) => {
                if (!e.features || !e.features.length) return;
                const f = e.features[0];
                const fid = f.properties.fid != null ? f.properties.fid : f.id;
                setClickedFeature(fid);
                selectedPolygonProps = f.properties;
                const aqKey = findAquiferKeyByClave(f.properties.c);
                if (aqKey) showDockedInfo(aqKey, f.properties.v);
            });

            // Clic fuera de polígonos
            map.on('click', (e) => {
                const feats = map.queryRenderedFeatures(e.point, { layers: ['vuln-fill'] });
                if (!feats.length) {
                    setClickedFeature(null);
                    if (searchedName) {
                        showDockedInfo(searchedName, null);
                    } else {
                        document.getElementById('docked-panel').style.display = 'none';
                    }
                }
            });

            function updateOpacityFast() {
                if (map.getLayer('vuln-fill')) {
                    map.setPaintProperty('vuln-fill', 'fill-opacity', getVulnFillOpacityExpr());
                }
            }

            function updateFilterStyles() {
                if (map.getLayer('vuln-fill')) {
                    map.setPaintProperty('vuln-fill', 'fill-opacity', getVulnFillOpacityExpr());
                    map.setPaintProperty('vuln-line', 'line-color', getVulnLineColorExpr());
                    map.setPaintProperty('vuln-line', 'line-width', getVulnLineWidthExpr());
                }
            }

            // Eventos Controles
            document.querySelectorAll('input[name="basemap_radio"]').forEach(r => {
                r.addEventListener('change', (e) => {
                    activeBasemapName = e.target.value;
                    map.getSource('basemap').setTiles([basemapsUrls[activeBasemapName]]);
                });
            });

            document.getElementById('btn-close-panel').onclick = () => {
                document.getElementById('panel-container').style.display = 'none';
                document.getElementById('btn-open-panel').style.display = 'block';
            };
            document.getElementById('btn-open-panel').onclick = () => {
                document.getElementById('panel-container').style.display = 'block';
                document.getElementById('btn-open-panel').style.display = 'none';
            };

            let opacityRaf = null;
            document.getElementById('op-slider').oninput = (e) => {
                currentOpacity = parseFloat(e.target.value);
                document.getElementById('op-val').innerText = Math.round(currentOpacity * 100) + '%';
                if (!opacityRaf) {
                    opacityRaf = requestAnimationFrame(() => {
                        opacityRaf = null;
                        updateOpacityFast();
                    });
                }
            };

            document.querySelectorAll('input[name="vuln-filter"]').forEach(r => {
                r.onchange = function() {
                    currentVulnFilter = this.value;
                    updateFilterStyles();
                };
            });

            document.getElementById('chk-c10').onchange = e => {
                if (map.getLayer('c10-line')) map.setLayoutProperty('c10-line', 'visibility', e.target.checked ? 'visible' : 'none');
            };
            document.getElementById('chk-c1').onchange = e => {
                if (map.getLayer('c1-line')) map.setLayoutProperty('c1-line', 'visibility', e.target.checked ? 'visible' : 'none');
            };

            // Buscador predictivo de acuíferos
            const searchInput = document.getElementById('search-input');
            const searchList = document.getElementById('search-list');
            const allAquiferNames = Object.keys(AQUIFER_INDEX).sort();

            function renderDropdown(text = "") {
                searchList.innerHTML = "";
                const q = text.trim().toLowerCase();
                let count = 0;
                for (const name of allAquiferNames) {
                    if (!q || name.toLowerCase().includes(q)) {
                        const d = document.createElement('div');
                        d.className = 'custom-dropdown-item';
                        d.innerText = name;
                        d.onclick = () => {
                            searchInput.value = name;
                            searchList.style.display = 'none';
                            triggerSearch(name);
                        };
                        searchList.appendChild(d);
                        count++;
                    }
                }
                searchList.style.display = count > 0 ? 'block' : 'none';
            }
            searchInput.onfocus = () => renderDropdown(searchInput.value);
            searchInput.oninput = (e) => renderDropdown(e.target.value);
            document.addEventListener('click', (e) => {
                if (!searchInput.contains(e.target) && !searchList.contains(e.target)) {
                    searchList.style.display = 'none';
                }
            });

            // Coordenadas con validación estricta [-90..90] / [-180..180] y sin XSS
            let tempMarker = null;
            function showCoordError(msg) {
                const err = document.getElementById('coord-error');
                err.innerText = msg;
                err.style.display = 'block';
                setTimeout(() => { err.style.display = 'none'; }, 3500);
            }

            document.getElementById('btn-coords').onclick = () => {
                const lat = parseFloat(document.getElementById('coord-lat').value);
                const lon = parseFloat(document.getElementById('coord-lon').value);
                const rawName = (document.getElementById('coord-name').value || '').trim() || 'Punto Buscado';

                if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
                    showCoordError('⚠️ Ingresa Latitud y Longitud numéricas.');
                    return;
                }
                if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
                    showCoordError('⚠️ Rango válido: Latitud [-90, 90] y Longitud [-180, 180].');
                    return;
                }

                document.getElementById('coord-error').style.display = 'none';
                if (tempMarker) tempMarker.remove();

                const box = document.createElement('div');
                box.style.cssText = 'color:#333;text-align:center;min-width:120px;';
                const titleEl = document.createElement('b');
                titleEl.style.cssText = 'color:#691C32;font-size:13px;display:block;margin-bottom:4px;';
                titleEl.textContent = rawName;
                const latEl = document.createElement('span');
                latEl.style.cssText = 'font-size:11px;color:#555;display:block;';
                latEl.textContent = `Lat: ${lat.toFixed(5)}°`;
                const lonEl = document.createElement('span');
                lonEl.style.cssText = 'font-size:11px;color:#555;display:block;';
                lonEl.textContent = `Lon: ${lon.toFixed(5)}°`;
                box.appendChild(titleEl);
                box.appendChild(latEl);
                box.appendChild(lonEl);

                const markerPopup = new maplibregl.Popup({ offset: 32, className: 'marker-popup', closeButton: true }).setDOMContent(box);
                tempMarker = new maplibregl.Marker({ color: '#691C32' })
                    .setLngLat([lon, lat])
                    .setPopup(markerPopup)
                    .addTo(map);
                activeCoordPoint = { lat, lon, name: rawName };
                tempMarker.togglePopup();
                map.flyTo({ center: [lon, lat], zoom: 11.5 });
            };

            document.getElementById('btn-clear-coord').onclick = () => {
                if (tempMarker) tempMarker.remove();
                tempMarker = null;
                activeCoordPoint = null;
                document.getElementById('coord-lat').value = '';
                document.getElementById('coord-lon').value = '';
                document.getElementById('coord-name').value = '';
                document.getElementById('coord-error').style.display = 'none';
            };

            document.getElementById('btn-reset').onclick = () => {
                clearSelection();
                currentVulnFilter = 'all';
                document.querySelector('input[name="vuln-filter"][value="all"]').checked = true;
                updateFilterStyles();
                searchInput.value = '';
                if (tempMarker) { tempMarker.remove(); tempMarker = null; }
                activeCoordPoint = null;
                document.getElementById('coord-lat').value = '';
                document.getElementById('coord-lon').value = '';
                document.getElementById('coord-name').value = '';
                document.getElementById('coord-error').style.display = 'none';
                map.fitBounds(viewBounds, { padding: 12, duration: 850 });
            };

            // Exportación Cartográfica Offscreen en Alta Resolución (2560x1680 px)
            function dibujarEscalaYCartografia(ctx, wCanvas, hHeader, hMap, hFooter, centerLat, currentZoom, aqMeta) {
                // 1. Encabezado institucional
                ctx.fillStyle = '#691C32';
                ctx.fillRect(0, 0, wCanvas, hHeader);
                ctx.fillStyle = '#BC955C';
                ctx.fillRect(0, hHeader - 5, wCanvas, 5);

                ctx.fillStyle = '#FFFFFF';
                ctx.font = 'bold 34px "Segoe UI", Arial, sans-serif';
                ctx.fillText('MAPA DE VULNERABILIDAD INTRÍNSECA DE ACUÍFEROS', 40, 48);

                ctx.fillStyle = '#EBDDC3';
                ctx.font = '20px "Segoe UI", Arial, sans-serif';
                const subtitulo = aqMeta
                    ? `Acuífero: ${aqMeta.clave} - ${aqMeta.nombre}  |  Superficie: ${aqMeta.area_km2.toLocaleString('es-MX', { maximumFractionDigits: 1 })} km²  |  Metodología: ${activeMapCfg.metodologia}`
                    : `Cobertura Nacional (${Object.keys(AQUIFER_INDEX).length} acuíferos)  |  Metodología: ${activeMapCfg.metodologia}`;
                ctx.fillText(subtitulo, 40, 82);

                const fechaStr = new Date().toLocaleDateString('es-MX', { year: 'numeric', month: '2-digit', day: '2-digit' });
                ctx.textAlign = 'right';
                ctx.font = 'bold 20px "Segoe UI", Arial, sans-serif';
                ctx.fillStyle = '#FFFFFF';
                ctx.fillText('CONAGUA · SSIG', wCanvas - 40, 46);
                ctx.font = '18px "Segoe UI", Arial, sans-serif';
                ctx.fillStyle = '#D4C19C';
                ctx.fillText(`Fecha: ${fechaStr}`, wCanvas - 40, 78);
                ctx.textAlign = 'left';

                // 2. Rosa de los vientos (Norte) arriba-derecha del mapa
                const nx = wCanvas - 72;
                const ny = hHeader + 64;
                ctx.save();
                ctx.fillStyle = 'rgba(255,255,255,0.92)';
                ctx.strokeStyle = '#691C32';
                ctx.lineWidth = 2.5;
                ctx.beginPath();
                ctx.arc(nx, ny, 34, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();

                ctx.fillStyle = '#691C32';
                ctx.font = 'bold 20px "Segoe UI", sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText('N', nx, ny - 10);
                ctx.beginPath();
                ctx.moveTo(nx, ny - 4);
                ctx.lineTo(nx + 10, ny + 18);
                ctx.lineTo(nx, ny + 12);
                ctx.lineTo(nx - 10, ny + 18);
                ctx.closePath();
                ctx.fill();
                ctx.restore();
                ctx.textAlign = 'left';

                // 3. Simbología vectorial HD abajo-izquierda del mapa
                const boxW = 330;
                const boxH = 225;
                const bx = 28;
                const by = hHeader + hMap - boxH - 24;
                ctx.fillStyle = 'rgba(255,255,255,0.95)';
                ctx.strokeStyle = '#BC955C';
                ctx.lineWidth = 3;
                ctx.fillRect(bx, by, boxW, boxH);
                ctx.strokeRect(bx, by, boxW, boxH);

                ctx.fillStyle = '#691C32';
                ctx.font = 'bold 22px "Segoe UI", Arial, sans-serif';
                ctx.fillText('Simbología (SEAG-INDEX)', bx + 20, by + 34);

                const items = [
                    ['#D90404', '5 - Muy Alta'],
                    ['#F25C05', '4 - Alta'],
                    ['#F2B705', '3 - Media'],
                    ['#99C140', '2 - Baja'],
                    ['#2DC937', '1 - Muy Baja']
                ];
                ctx.font = '19px "Segoe UI", Arial, sans-serif';
                items.forEach(([col, txt], i) => {
                    const iy = by + 56 + i * 32;
                    ctx.fillStyle = col;
                    ctx.fillRect(bx + 20, iy, 22, 22);
                    ctx.strokeStyle = '#333333';
                    ctx.lineWidth = 1.5;
                    ctx.strokeRect(bx + 20, iy, 22, 22);
                    ctx.fillStyle = '#1E293B';
                    ctx.fillText(txt, bx + 54, iy + 18);
                });

                // 4. Barra de escala métrica precisa (considerando pixelRatio = 2 sobre ancho 1280px)
                const metersPerPx = (156543.03392 * Math.cos(centerLat * Math.PI / 180)) / Math.pow(2, currentZoom) / 2;
                const rawMeters = metersPerPx * 260;
                const pasos = [500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000, 1000000];
                let niceM = pasos[0];
                for (const p of pasos) { if (p <= rawMeters) niceM = p; }
                const barPx = Math.round(niceM / metersPerPx);
                const scaleLabel = niceM >= 1000 ? `${niceM / 1000} km` : `${niceM} m`;

                const sx = wCanvas - barPx - 34;
                const sy = hHeader + hMap - 52;
                ctx.fillStyle = 'rgba(255,255,255,0.92)';
                ctx.fillRect(sx - 14, sy - 28, barPx + 28, 48);
                ctx.strokeStyle = '#334155';
                ctx.lineWidth = 2;
                ctx.strokeRect(sx - 14, sy - 28, barPx + 28, 48);
                ctx.fillStyle = '#111827';
                ctx.fillRect(sx, sy, barPx / 2, 10);
                ctx.fillStyle = '#FFFFFF';
                ctx.fillRect(sx + barPx / 2, sy, barPx / 2, 10);
                ctx.strokeRect(sx, sy, barPx, 10);
                ctx.fillStyle = '#111827';
                ctx.font = 'bold 18px "Segoe UI", Arial, sans-serif';
                ctx.fillText('0', sx - 4, sy - 8);
                ctx.textAlign = 'right';
                ctx.fillText(scaleLabel, sx + barPx + 4, sy - 8);
                ctx.textAlign = 'left';

                // 5. Pie de página cartográfico
                const fy = hHeader + hMap;
                ctx.fillStyle = '#FAF8F5';
                ctx.fillRect(0, fy, wCanvas, hFooter);
                ctx.fillStyle = '#BC955C';
                ctx.fillRect(0, fy, wCanvas, 3);
                ctx.fillStyle = '#475569';
                ctx.font = '18px "Segoe UI", Arial, sans-serif';
                const c = map.getCenter();
                ctx.fillText(
                    `Centro: ${c.lat.toFixed(4)}° N, ${c.lng.toFixed(4)}° E  |  Zoom: ${currentZoom.toFixed(2)}  |  Mapa base: ${activeBasemapName}  |  Proyección: Web Mercator (EPSG:3857)`,
                    36, fy + 38
                );
                ctx.textAlign = 'right';
                ctx.fillText('Subgerencia de Sistemas de Información Geohidrológica · CONAGUA', wCanvas - 36, fy + 38);
                ctx.textAlign = 'left';
            }

            document.getElementById('btn-print').onclick = function() {
                const btn = this;
                btn.innerHTML = '⏳';
                btn.style.cursor = 'wait';
                btn.disabled = true;

                const offDiv = document.createElement('div');
                offDiv.style.cssText = 'position:fixed; left:-10000px; top:0; width:1280px; height:760px; pointer-events:none; opacity:0.01;';
                document.body.appendChild(offDiv);

                let offMap = null;
                let finalizado = false;
                const limpiar = () => {
                    if (offMap) { try { offMap.remove(); } catch (e) {} offMap = null; }
                    if (offDiv.parentNode) offDiv.parentNode.removeChild(offDiv);
                    btn.innerHTML = '🖨️';
                    btn.style.cursor = 'pointer';
                    btn.disabled = false;
                };

                try {
                    const center = map.getCenter();
                    const zoom = map.getZoom();
                    const bearing = map.getBearing();
                    const pitch = map.getPitch();

                    offMap = new maplibregl.Map({
                        container: offDiv,
                        style: {
                            version: 8,
                            glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
                            sources: {
                                'basemap': {
                                    type: 'raster',
                                    tiles: [basemapsUrls[activeBasemapName]],
                                    tileSize: 256
                                }
                            },
                            layers: [{ id: 'basemap-layer', type: 'raster', source: 'basemap', minzoom: 0, maxzoom: 22 }]
                        },
                        center: [center.lng, center.lat],
                        zoom: zoom,
                        bearing: bearing,
                        pitch: pitch,
                        interactive: false,
                        preserveDrawingBuffer: true,
                        pixelRatio: 2,
                        attributionControl: false
                    });

                    const capturar = () => {
                        if (finalizado) return;
                        finalizado = true;
                        try {
                            const glCanvas = offMap.getCanvas();
                            const wCanvas = glCanvas.width;
                            const hMap = glCanvas.height;
                            const hHeader = 104;
                            const hFooter = 58;
                            const outCanvas = document.createElement('canvas');
                            outCanvas.width = wCanvas;
                            outCanvas.height = hHeader + hMap + hFooter;
                            const ctx = outCanvas.getContext('2d');

                            ctx.drawImage(glCanvas, 0, hHeader);
                            const aqMeta = searchedName ? AQUIFER_INDEX[searchedName] : null;
                            dibujarEscalaYCartografia(ctx, wCanvas, hHeader, hMap, hFooter, center.lat, zoom, aqMeta);

                            const dataUrl = outCanvas.toDataURL('image/png');
                            const a = document.createElement('a');
                            a.download = searchedClave ? `Mapa_Vulnerabilidad_${searchedClave}_HD.png` : 'Mapa_Vulnerabilidad_Nacional_HD.png';
                            a.href = dataUrl;
                            a.click();
                        } catch (err) {
                            console.warn('Error generando captura HD:', err);
                        } finally {
                            limpiar();
                        }
                    };

                    offMap.on('load', () => {
                        offMap.addSource('vuln-src', {
                            type: 'vector',
                            url: 'pmtiles://' + activeMapCfg.url,
                            minzoom: 3,
                            maxzoom: 11
                        });
                        offMap.addLayer({
                            id: 'vuln-fill', type: 'fill', source: 'vuln-src',
                            'source-layer': activeMapCfg.source_layer,
                            paint: {
                                'fill-color': [
                                    'match', ['get', 'v'],
                                    5, vulnColors['5'], 4, vulnColors['4'], 3, vulnColors['3'],
                                    2, vulnColors['2'], 1, vulnColors['1'], vulnColors.default
                                ],
                                'fill-opacity': getVulnFillOpacityExpr()
                            }
                        });
                        offMap.addLayer({
                            id: 'vuln-line', type: 'line', source: 'vuln-src',
                            'source-layer': activeMapCfg.source_layer,
                            paint: { 'line-color': getVulnLineColorExpr(), 'line-width': getVulnLineWidthExpr() }
                        });
                        if (searchedClave) {
                            offMap.addLayer({
                                id: 'vuln-search-fill', type: 'fill', source: 'vuln-src',
                                'source-layer': activeMapCfg.source_layer,
                                filter: ['==', ['get', 'c'], searchedClave],
                                paint: { 'fill-color': '#691C32', 'fill-opacity': 0.14 }
                            });
                            offMap.addLayer({
                                id: 'vuln-search-line', type: 'line', source: 'vuln-src',
                                'source-layer': activeMapCfg.source_layer,
                                filter: ['==', ['get', 'c'], searchedClave],
                                paint: { 'line-color': '#691C32', 'line-width': 2.5 }
                            });
                        }
                        if (clickedFeatureId !== null) {
                            offMap.addLayer({
                                id: 'vuln-clicked-line', type: 'line', source: 'vuln-src',
                                'source-layer': activeMapCfg.source_layer,
                                filter: ['==', ['get', 'fid'], clickedFeatureId],
                                paint: { 'line-color': '#691C32', 'line-width': 3.0 }
                            });
                        }
                        if (INDICE_META.has_costa_10km && document.getElementById('chk-c10').checked) {
                            offMap.addLayer({ id: 'c10-line', type: 'line', source: 'vuln-src', 'source-layer': 'costa_10km', paint: { 'line-color': '#007BFF', 'line-width': 2.5, 'line-opacity': 0.85 } });
                        }
                        if (INDICE_META.has_costa_1km && document.getElementById('chk-c1').checked) {
                            offMap.addLayer({ id: 'c1-line', type: 'line', source: 'vuln-src', 'source-layer': 'costa_1km', paint: { 'line-color': '#FF0000', 'line-width': 2.5, 'line-opacity': 0.85 } });
                        }
                        if (document.getElementById('chk-malla').checked && latestGraticuleData.features.length) {
                            offMap.addSource('graticule-src', { type: 'geojson', data: latestGraticuleData });
                            offMap.addLayer({ id: 'graticule-line', type: 'line', source: 'graticule-src', filter: ['==', ['geometry-type'], 'LineString'], paint: { 'line-color': '#475569', 'line-width': 0.75, 'line-opacity': 0.55 } });
                            offMap.addLayer({
                                id: 'graticule-label-lat', type: 'symbol', source: 'graticule-src', filter: ['==', ['get', 'axis'], 'lat'],
                                layout: { 'text-field': ['get', 'label'], 'text-font': ['Open Sans Regular'], 'text-size': 11, 'symbol-placement': 'point', 'text-anchor': 'left', 'text-offset': [0.25, 0], 'text-allow-overlap': true, 'text-ignore-placement': true },
                                paint: { 'text-color': '#1E293B', 'text-halo-color': '#FFFFFF', 'text-halo-width': 2 }
                            });
                            offMap.addLayer({
                                id: 'graticule-label-lon', type: 'symbol', source: 'graticule-src', filter: ['==', ['get', 'axis'], 'lon'],
                                layout: { 'text-field': ['get', 'label'], 'text-font': ['Open Sans Regular'], 'text-size': 11, 'symbol-placement': 'point', 'text-anchor': 'top', 'text-offset': [0, 0.2], 'text-allow-overlap': true, 'text-ignore-placement': true },
                                paint: { 'text-color': '#1E293B', 'text-halo-color': '#FFFFFF', 'text-halo-width': 2 }
                            });
                        }
                        if (activeCoordPoint) {
                            offMap.addSource('coord-pt-src', {
                                type: 'geojson',
                                data: { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [activeCoordPoint.lon, activeCoordPoint.lat] }, properties: { lbl: activeCoordPoint.name } }] }
                            });
                            offMap.addLayer({
                                id: 'coord-pt-circle', type: 'circle', source: 'coord-pt-src',
                                paint: { 'circle-radius': 8, 'circle-color': '#691C32', 'circle-stroke-width': 2.5, 'circle-stroke-color': '#FFFFFF' }
                            });
                            offMap.addLayer({
                                id: 'coord-pt-label', type: 'symbol', source: 'coord-pt-src',
                                layout: { 'text-field': ['get', 'lbl'], 'text-font': ['Open Sans Regular'], 'text-size': 13, 'text-offset': [0, -1.6], 'text-anchor': 'bottom', 'text-allow-overlap': true },
                                paint: { 'text-color': '#691C32', 'text-halo-color': '#FFFFFF', 'text-halo-width': 2.5 }
                            });
                        }

                        offMap.once('idle', () => setTimeout(capturar, 120));
                    });

                    // Salvavidas si algún servidor externo de mapa base tarda demasiado
                    setTimeout(() => { if (!finalizado && offMap) capturar(); }, 10000);
                } catch (err) {
                    console.warn('Error iniciando captura HD:', err);
                    limpiar();
                }
            };

            // Pantalla completa sin resetear la vista actual
            document.getElementById('fs-btn').onclick = function() {
                if (!document.fullscreenElement) {
                    const req = document.documentElement.requestFullscreen();
                    if (req && typeof req.catch === 'function') req.catch(() => {});
                } else {
                    const ex = document.exitFullscreen();
                    if (ex && typeof ex.catch === 'function') ex.catch(() => {});
                }
            };
            document.addEventListener('fullscreenchange', () => {
                document.getElementById('fs-btn').innerHTML = document.fullscreenElement ? iconCompress : iconExpand;
                setTimeout(() => map.resize(), 180);
            });

            // Mallado adaptativo sin recorte en bordes
            function updateGraticule() {
                if (!map.getLayer('graticule-line') || map.getLayoutProperty('graticule-line', 'visibility') === 'none') return;
                const bounds = map.getBounds();
                const latSpan = bounds.getNorth() - bounds.getSouth();
                const lngSpan = bounds.getEast() - bounds.getWest();
                const target = latSpan / 6;
                const intervals = [20, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01];
                let interval = 0.01;
                for (let i = 0; i < intervals.length; i++) {
                    if (target >= intervals[i]) { interval = intervals[i]; break; }
                }

                const features = [];
                const s = Math.floor(bounds.getSouth() / interval) * interval;
                const n = Math.ceil(bounds.getNorth() / interval) * interval;
                const w = Math.floor(bounds.getWest() / interval) * interval;
                const e = Math.ceil(bounds.getEast() / interval) * interval;

                const latInset = bounds.getNorth() - latSpan * 0.012;
                const lonInset = bounds.getWest() + lngSpan * 0.008;

                for (let lat = s; lat <= n; lat += interval) {
                    features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[w, lat], [e, lat]] }, properties: {} });
                    if (lat > bounds.getSouth() + latSpan * 0.04 && lat < bounds.getNorth() - latSpan * 0.04) {
                        features.push({
                            type: 'Feature',
                            geometry: { type: 'Point', coordinates: [lonInset, lat] },
                            properties: { label: Number(lat.toFixed(4)) + '°', axis: 'lat' }
                        });
                    }
                }
                for (let lng = w; lng <= e; lng += interval) {
                    features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: [[lng, s], [lng, n]] }, properties: {} });
                    if (lng > bounds.getWest() + lngSpan * 0.06 && lng < bounds.getEast() - lngSpan * 0.04) {
                        features.push({
                            type: 'Feature',
                            geometry: { type: 'Point', coordinates: [lng, latInset] },
                            properties: { label: Number(lng.toFixed(4)) + '°', axis: 'lon' }
                        });
                    }
                }
                latestGraticuleData = { type: 'FeatureCollection', features: features };
                map.getSource('graticule-src').setData(latestGraticuleData);
            }

            map.on('move', updateGraticule);
            document.getElementById('chk-malla').onchange = (e) => {
                const vis = e.target.checked ? 'visible' : 'none';
                map.setLayoutProperty('graticule-line', 'visibility', vis);
                map.setLayoutProperty('graticule-label-lat', 'visibility', vis);
                map.setLayoutProperty('graticule-label-lon', 'visibility', vis);
                if (e.target.checked) updateGraticule();
            };
        });
    </script>
</body>
</html>
"""

html_code = (
    HTML_TEMPLATE
    .replace("__CATALOGO_MAPAS__", _json_seguro_html(catalogo_runtime))
    .replace("__INDICE_META__", _json_seguro_html(indice_vuln))
)

components.html(html_code, height=760)
