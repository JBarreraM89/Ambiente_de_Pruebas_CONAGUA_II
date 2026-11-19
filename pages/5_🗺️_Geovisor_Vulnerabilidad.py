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

repda_pmtiles_url = obtener_url_pmtiles(nombre_archivo="repda_nacional.pmtiles")

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
        #custom-measure-container { order: 4; }

        .measure-toggle-btn {
            width: 32px; height: 32px; background: #ffffff; border-radius: 4px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            box-shadow: 0 1px 5px rgba(0,0,0,0.45); border: 1px solid rgba(0,0,0,0.12);
            box-sizing: border-box; font-size: 16px; transition: all 0.15s ease;
        }
        .measure-toggle-btn:hover { background: #f4f4f4; }
        .measure-toggle-btn.active {
            background: #691C32 !important; color: #ffffff !important;
            border-color: #BC955C !important; box-shadow: 0 2px 10px rgba(105, 28, 50, 0.45);
        }

        /* Barra flotante de medición geodésica (centrada abajo para no chocar con Controles ni la ficha) */
        .measure-bar {
            position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
            z-index: 9600; display: none; align-items: center; gap: 6px;
            background: rgba(255, 255, 255, 0.96); padding: 6px 10px; border-radius: 999px;
            border: 1.5px solid #BC955C; box-shadow: 0 4px 16px rgba(0,0,0,0.22);
            font-size: 12px; color: #1E293B; white-space: nowrap;
        }
        .measure-mode-btn {
            border: 1px solid #D1D5DB; background: #FAF8F5; color: #334155;
            border-radius: 999px; padding: 4px 10px; font-size: 11.5px; font-weight: 600; cursor: pointer;
        }
        .measure-mode-btn.active { background: #691C32; color: #ffffff; border-color: #691C32; }
        .measure-readout {
            font-weight: 700; color: #691C32; padding: 0 6px; min-width: 92px; text-align: center;
        }
        .measure-icon-btn {
            border: none; background: #F1ECE4; color: #334155; border-radius: 50%;
            width: 24px; height: 24px; cursor: pointer; font-size: 12px; font-weight: 700;
            display: inline-flex; align-items: center; justify-content: center;
        }
        .measure-icon-btn:hover { background: #E2D9C8; color: #691C32; }

        .docked-actions { display: flex; gap: 6px; margin-top: 9px; }
        .docked-actions button { margin-top: 0 !important; flex: 1; }
        .btn-export-csv {
            padding: 6px 8px; border-radius: 5px; background: #691C32 !important; color: #ffffff !important;
            border: 1px solid #BC955C !important; font-size: 11.5px; font-weight: 600; cursor: pointer;
        }
        .btn-export-csv:hover { background: #4A1424 !important; }
        .label-row-flex { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; }
        .label-row-flex label { margin-bottom: 0 !important; }
        .btn-mini-csv {
            display: inline-flex; align-items: center; gap: 4px;
            background: #FAF6F0; color: #691C32; border: 1px solid #BC955C; border-radius: 4px;
            padding: 2px 7px; font-size: 10.5px; font-weight: 700; cursor: pointer;
        }
        .btn-mini-csv:hover { background: #691C32; color: #ffffff; }
        .ui-ico { display: inline-block; vertical-align: -2px; flex-shrink: 0; }
        .btn-ico-flex { display: inline-flex !important; align-items: center; justify-content: center; gap: 5px; }
        @keyframes spinSvg { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .spin-ico { animation: spinSvg 0.9s linear infinite; }
        .coord-dictamen-box {
            margin-top: 7px; padding-top: 7px; border-top: 1px solid #EAE4DA; text-align: center;
        }
        .coord-dictamen-badge {
            display: inline-block; padding: 3px 9px; border-radius: 10px; color: #ffffff;
            font-size: 11px; font-weight: 700; text-shadow: 0 1px 1px rgba(0,0,0,0.3); margin-bottom: 4px;
        }
        .coord-dictamen-aq { font-size: 11px; font-weight: 600; color: #1E293B; display: block; margin-bottom: 5px; }
        .coord-dictamen-btn {
            background: #FAF6F0; color: #691C32; border: 1px solid #BC955C; border-radius: 4px;
            padding: 3px 8px; font-size: 11px; font-weight: 600; cursor: pointer;
        }
        .coord-dictamen-btn:hover { background: #691C32; color: #ffffff; }
        .repda-popup-card { min-width: 220px; font-size: 11.5px; color: #1E293B; }
        .repda-popup-card b.rp-title { color: #691C32; font-size: 12.5px; display: block; margin-bottom: 4px; }
        .repda-popup-table { width: 100%; border-collapse: collapse; margin-top: 4px; }
        .repda-popup-table td { padding: 2px 0; border-bottom: 1px solid #F1ECE4; }
        .repda-popup-table td.rk { color: #64748B; padding-right: 8px; }
        .repda-popup-table td.rv { font-weight: 600; text-align: right; }

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
        .docked-reopen-btn {
            position: absolute; top: 10px; right: 58px; z-index: 8900;
            display: none; align-items: center; gap: 6px;
            background: #691C32 !important; color: #ffffff !important;
            border: 1.5px solid #BC955C !important; border-radius: 999px;
            padding: 6px 13px; font-size: 12px; font-weight: 600; cursor: pointer;
            box-shadow: 0 3px 12px rgba(105, 28, 50, 0.35);
            transition: background 0.15s ease, transform 0.15s ease;
        }
        .docked-reopen-btn:hover { background: #4A1424 !important; transform: translateY(-1px); }
        .search-wrap { position: relative; width: 100%; }
        .search-wrap input { padding-right: 26px !important; }
        .btn-clear-search {
            position: absolute; right: 6px; top: 50%; transform: translateY(-56%);
            width: 18px; height: 18px; border: none; border-radius: 50%;
            background: #E2D9C8 !important; color: #691C32 !important;
            font-size: 13px; font-weight: 700; line-height: 16px; text-align: center;
            cursor: pointer; display: none; padding: 0;
        }
        .btn-clear-search:hover { background: #BC955C !important; color: #ffffff !important; }

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
        const REPDA_PMTILES_URL = __REPDA_PMTILES_URL__;
        const AQUIFER_INDEX = INDICE_META.acuiferos || {};

        const repdaUseColors = {
            'AGRICOLA': '#16a34a',
            'PUBLICO URBANO': '#2563eb',
            'DOMESTICO': '#0284c7',
            'INDUSTRIAL': '#dc2626',
            'SERVICIOS': '#9333ea',
            'PECUARIO': '#ca8a04',
            'DIFERENTES USOS': '#0d9488',
            'ACUACULTURA': '#06b6d4',
            'AGROINDUSTRIAL': '#65a30d',
            'COMERCIO': '#ea580c',
            'ENERGIA ELECTRICA': '#eab308',
            'OTROS': '#64748b'
        };

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
        let activeCoordPoint = null;
        let coordEvalToken = 0;
        let latestGraticuleData = { type: 'FeatureCollection', features: [] };

        const hoverPopup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'minimal-popup' });

        // ==========================================
        // 2. CONTROLES PERSONALIZADOS (UI + SVGs MONOCROMÁTICOS)
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

        const iconExpand = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
        const iconCompress = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;
        const iconRuler = `<svg class="ui-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.3 8.7 8.7 21.3a1 1 0 0 1-1.4 0l-4.6-4.6a1 1 0 0 1 0-1.4L15.3 2.7a1 1 0 0 1 1.4 0l4.6 4.6a1 1 0 0 1 0 1.4Z"/><path d="m7.5 10.5 2 2"/><path d="m10.5 7.5 2 2"/><path d="m13.5 4.5 2 2"/><path d="m4.5 13.5 2 2"/></svg>`;
        const iconRulerSm = `<svg class="ui-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.3 8.7 8.7 21.3a1 1 0 0 1-1.4 0l-4.6-4.6a1 1 0 0 1 0-1.4L15.3 2.7a1 1 0 0 1 1.4 0l4.6 4.6a1 1 0 0 1 0 1.4Z"/><path d="m7.5 10.5 2 2"/><path d="m10.5 7.5 2 2"/><path d="m13.5 4.5 2 2"/></svg>`;
        const iconPolygonSm = `<svg class="ui-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 3 21 9 17.5 20 6.5 20 3 9 12 3"/></svg>`;
        const iconPrint = `<svg class="ui-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>`;
        const iconSpinner = `<svg class="ui-ico spin-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#691C32" stroke-width="2.6" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.2-8.56"/></svg>`;
        const iconDownloadSm = `<svg class="ui-ico" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`;
        const iconInfoSm = `<svg class="ui-ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
        const iconFocusSm = `<svg class="ui-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/></svg>`;
        const iconTrashSm = `<svg class="ui-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>`;
        const iconUndoSm = `<svg class="ui-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/></svg>`;
        const iconCloseSm = `<svg class="ui-ico" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
        const iconSlidersSm = `<svg class="ui-ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>`;
        const iconResetSm = `<svg class="ui-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>`;
        const iconDropSm = `<svg class="ui-ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#691C32" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>`;

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
        map.addControl(new CustomControl('custom-measure-container', `<button type="button" id="btn-measure" class="measure-toggle-btn" title="Medir distancias o áreas en el mapa">${iconRuler}</button>`), 'top-right');
        document.getElementById('map').insertAdjacentHTML(
            'beforeend',
            '<div id="docked-panel" class="docked-panel"></div>' +
            `<button type="button" id="btn-reopen-dock" class="docked-reopen-btn" title="Mostrar ficha del acuífero seleccionado">${iconInfoSm} Ver ficha</button>` +
            '<div id="measure-bar" class="measure-bar">' +
                `<button type="button" id="btn-m-dist" class="measure-mode-btn btn-ico-flex active">${iconRulerSm} Distancia</button>` +
                `<button type="button" id="btn-m-area" class="measure-mode-btn btn-ico-flex">${iconPolygonSm} Área</button>` +
                '<span id="measure-readout" class="measure-readout">Haz clic en el mapa</span>' +
                `<button type="button" id="btn-m-undo" class="measure-icon-btn" title="Deshacer último vértice">${iconUndoSm}</button>` +
                `<button type="button" id="btn-m-clear" class="measure-icon-btn" title="Limpiar medición">${iconTrashSm}</button>` +
                `<button type="button" id="btn-m-exit" class="measure-icon-btn" title="Salir de medición (Esc)">${iconCloseSm}</button>` +
            '</div>'
        );

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
                <h3 style="margin:0 0 10px 0; color:#691C32; font-size:15px; display:flex; align-items:center; gap:6px;">${iconSlidersSm}<span>Controles</span></h3>
                ${selectorMapasHtml}
                <div class="control-section custom-dropdown">
                    <div class="label-row-flex">
                        <label>Buscar Acuífero (${totalAq}):</label>
                        <button type="button" id="btn-export-all-csv" class="btn-mini-csv" title="Descargar resumen nacional de los ${totalAq} acuíferos en CSV">${iconDownloadSm} CSV</button>
                    </div>
                    <div class="search-wrap">
                        <input type="text" id="search-input" placeholder="-- Escribe clave o nombre --" autocomplete="off">
                        <button type="button" id="btn-clear-search" class="btn-clear-search" title="Quitar acuífero seleccionado">&times;</button>
                    </div>
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
                        <button id="btn-clear-coord" class="btn-clear-point btn-ico-flex" title="Borrar punto">${iconTrashSm}</button>
                    </div>
                    <div id="coord-error" style="display:none; color:#D90404; font-size:11px; margin-top:5px; font-weight:600; text-align:center;"></div>
                </div>
                <div class="control-section">
                    <label>Capas Adicionales:</label>
                    <label id="lbl-repda" class="chk-row"><input type="checkbox" id="chk-repda"> Aprovechamientos REPDA</label>
                    <label id="lbl-c10" class="chk-row"><input type="checkbox" id="chk-c10"> Línea Costa (10 km)</label>
                    <label id="lbl-c1" class="chk-row"><input type="checkbox" id="chk-c1"> Línea Costa (1 km)</label>
                    <label class="chk-row"><input type="checkbox" id="chk-malla"> Mallado (Lat/Lon)</label>
                </div>
                <button id="btn-reset" class="btn-reset-view btn-ico-flex">${iconResetSm} Restablecer Vista</button>
            </div>
        `;
        map.addControl(new CustomControl('main-menu-container', menuHtml), 'top-left');

        map.addControl(new CustomControl('print-ctrl-container', `<button id="btn-print" class="print-btn" title="Descargar lámina HD en PNG">${iconPrint}</button>`), 'bottom-right');
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
                    <div class="docked-actions">
                        <button id="btn-focus-aq" class="btn-focus-aq btn-ico-flex">${iconFocusSm} Enfocar</button>
                        <button id="btn-export-aq-csv" class="btn-export-csv btn-ico-flex" title="Descargar tabla oficial en CSV (Excel)">${iconDownloadSm} CSV</button>
                    </div>
                </div>
            `;
            panel.style.display = 'flex';
            const reopenBtn = document.getElementById('btn-reopen-dock');
            if (reopenBtn) reopenBtn.style.display = 'none';
            panel.querySelector('.docked-close').onclick = hideDockedPanel;
            panel.querySelector('#btn-focus-aq').onclick = () => triggerSearch(aquiferKey);
            panel.querySelector('#btn-export-aq-csv').onclick = () => exportAquiferCsv(aquiferKey);
        }

        function _downloadCsvText(filename, rows) {
            const esc = (v) => {
                const s = v == null ? '' : String(v);
                return /[",\\n\\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
            };
            const csv = '\\uFEFF' + rows.map(r => r.map(esc).join(',')).join('\\r\\n');
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        }

        function exportAquiferCsv(aquiferKey) {
            const meta = AQUIFER_INDEX[aquiferKey];
            if (!meta) return;
            const rows = [
                ['Clave_Acuifero', 'Nombre_Acuifero', 'Metodologia', 'Clase', 'Categoria', 'Poligonos', 'Superficie_km2', 'Porcentaje_%']
            ];
            ['5', '4', '3', '2', '1'].forEach(c => {
                const info = meta.clases ? meta.clases[c] : null;
                if (!info || !info.count) return;
                rows.push([
                    meta.clave, meta.nombre, activeMapCfg.metodologia, c,
                    vulnLabels[c], info.count, info.area_km2.toFixed(3), info.pct.toFixed(2)
                ]);
            });
            rows.push([meta.clave, meta.nombre, activeMapCfg.metodologia, 'TOTAL', 'Superficie Total', meta.poligonos, meta.area_km2.toFixed(2), '100.00']);
            const safeNom = meta.nombre.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 35);
            _downloadCsvText(`Vulnerabilidad_${meta.clave}_${safeNom}.csv`, rows);
        }

        function exportAllAquifersCsv() {
            const rows = [[
                'Clave_Acuifero', 'Nombre_Acuifero', 'Poligonos', 'Superficie_Total_km2', 'Clase_Predominante',
                'Pct_5_Muy_Alta', 'km2_5_Muy_Alta',
                'Pct_4_Alta', 'km2_4_Alta',
                'Pct_3_Media', 'km2_3_Media',
                'Pct_2_Baja', 'km2_2_Baja',
                'Pct_1_Muy_Baja', 'km2_1_Muy_Baja'
            ]];
            Object.keys(AQUIFER_INDEX).sort().forEach(k => {
                const m = AQUIFER_INDEX[k];
                const g = (c, f) => (m.clases && m.clases[c] ? m.clases[c][f] : 0);
                rows.push([
                    m.clave, m.nombre, m.poligonos, m.area_km2.toFixed(2),
                    vulnLabels[String(m.clase_predominante || '')] || 'S/D',
                    g('5', 'pct').toFixed(2), g('5', 'area_km2').toFixed(3),
                    g('4', 'pct').toFixed(2), g('4', 'area_km2').toFixed(3),
                    g('3', 'pct').toFixed(2), g('3', 'area_km2').toFixed(3),
                    g('2', 'pct').toFixed(2), g('2', 'area_km2').toFixed(3),
                    g('1', 'pct').toFixed(2), g('1', 'area_km2').toFixed(3)
                ]);
            });
            _downloadCsvText(`Resumen_Vulnerabilidad_Nacional_${Object.keys(AQUIFER_INDEX).length}_Acuiferos.csv`, rows);
        }

        function hideDockedPanel() {
            document.getElementById('docked-panel').style.display = 'none';
            setClickedFeature(null);
            const reopenBtn = document.getElementById('btn-reopen-dock');
            if (reopenBtn) reopenBtn.style.display = searchedName ? 'inline-flex' : 'none';
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

        function syncClearSearchBtn() {
            const inp = document.getElementById('search-input');
            const btn = document.getElementById('btn-clear-search');
            if (!inp || !btn) return;
            btn.style.display = (inp.value.trim().length > 0 || searchedName) ? 'block' : 'none';
        }

        function clearSelection(clearSearchBox = true) {
            setClickedFeature(null);
            searchedClave = null;
            searchedName = null;
            if (map.getLayer('vuln-search-fill')) {
                map.setFilter('vuln-search-fill', ['==', ['get', 'c'], '__NONE__']);
                map.setFilter('vuln-search-line', ['==', ['get', 'c'], '__NONE__']);
            }
            document.getElementById('docked-panel').style.display = 'none';
            const reopenBtn = document.getElementById('btn-reopen-dock');
            if (reopenBtn) reopenBtn.style.display = 'none';
            if (clearSearchBox) {
                const inp = document.getElementById('search-input');
                if (inp) inp.value = '';
            }
            syncClearSearchBtn();
        }

        function triggerSearch(aqKey) {
            const meta = AQUIFER_INDEX[aqKey];
            if (!meta) return;

            clearSelection(false);
            searchedClave = meta.clave;
            searchedName = aqKey;
            const inp = document.getElementById('search-input');
            if (inp) inp.value = aqKey;
            syncClearSearchBtn();

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

            // Capas de Medición Geodésica (Distancias y Áreas)
            map.addSource('measure-src', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
            map.addLayer({
                id: 'measure-fill', type: 'fill', source: 'measure-src',
                filter: ['==', ['geometry-type'], 'Polygon'],
                paint: { 'fill-color': '#691C32', 'fill-opacity': 0.18 }
            });
            map.addLayer({
                id: 'measure-line', type: 'line', source: 'measure-src',
                filter: ['==', ['geometry-type'], 'LineString'],
                paint: { 'line-color': '#691C32', 'line-width': 2.8, 'line-dasharray': [2.5, 1.5] }
            });
            map.addLayer({
                id: 'measure-pts', type: 'circle', source: 'measure-src',
                filter: ['==', ['geometry-type'], 'Point'],
                paint: { 'circle-radius': 5, 'circle-color': '#FFFFFF', 'circle-stroke-width': 2.5, 'circle-stroke-color': '#691C32' }
            });

            let measureActive = false;
            let measureMode = 'distance'; // 'distance' | 'area'
            let measureCoords = [];
            let latestMeasureGeoJSON = { type: 'FeatureCollection', features: [] };
            let latestMeasureText = '';

            function haversineMeters(c1, c2) {
                const R = 6371008.8;
                const dLat = (c2[1] - c1[1]) * Math.PI / 180;
                const dLon = (c2[0] - c1[0]) * Math.PI / 180;
                const lat1 = c1[1] * Math.PI / 180;
                const lat2 = c2[1] * Math.PI / 180;
                const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
                return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
            }

            function geodesicAreaM2(ring) {
                if (ring.length < 3) return 0;
                const R = 6378137.0;
                let total = 0;
                const n = ring.length;
                for (let i = 0; i < n; i++) {
                    const p1 = ring[i];
                    const p2 = ring[(i + 1) % n];
                    const lon1 = p1[0] * Math.PI / 180;
                    const lon2 = p2[0] * Math.PI / 180;
                    const lat1 = p1[1] * Math.PI / 180;
                    const lat2 = p2[1] * Math.PI / 180;
                    total += (lon2 - lon1) * (2 + Math.sin(lat1) + Math.sin(lat2));
                }
                return Math.abs(total * R * R / 2.0);
            }

            function formatDist(m) {
                return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
            }

            function updateMeasureRender() {
                const feats = [];
                measureCoords.forEach(c => feats.push({ type: 'Feature', geometry: { type: 'Point', coordinates: c }, properties: {} }));
                let readout = 'Haz clic en el mapa';
                if (measureCoords.length >= 2) {
                    const lineCoords = (measureMode === 'area' && measureCoords.length >= 3)
                        ? [...measureCoords, measureCoords[0]]
                        : measureCoords;
                    feats.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: lineCoords }, properties: {} });
                    let totalM = 0;
                    for (let i = 1; i < lineCoords.length; i++) totalM += haversineMeters(lineCoords[i - 1], lineCoords[i]);
                    if (measureMode === 'distance') {
                        readout = `Distancia: ${formatDist(totalM)}`;
                    } else if (measureCoords.length >= 3) {
                        feats.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [lineCoords] }, properties: {} });
                        const areaM2 = geodesicAreaM2(measureCoords);
                        const areaKm2 = areaM2 / 1e6;
                        const areaHa = areaM2 / 1e4;
                        readout = areaKm2 >= 1
                            ? `Área: ${areaKm2.toLocaleString('es-MX', { maximumFractionDigits: 2 })} km² (${Math.round(areaHa).toLocaleString('es-MX')} ha)`
                            : `Área: ${areaHa.toFixed(2)} ha (${formatDist(totalM)})`;
                    } else {
                        readout = `Perímetro: ${formatDist(totalM)} (+1 vértice)`;
                    }
                } else if (measureCoords.length === 1) {
                    readout = '1 punto · agrega siguiente';
                }
                latestMeasureText = measureCoords.length >= 2 ? readout : '';
                latestMeasureGeoJSON = { type: 'FeatureCollection', features: feats };
                if (map.getSource('measure-src')) map.getSource('measure-src').setData(latestMeasureGeoJSON);
                const ro = document.getElementById('measure-readout');
                if (ro) ro.innerText = readout;
            }

            function setMeasureActive(flag) {
                measureActive = Boolean(flag);
                const btn = document.getElementById('btn-measure');
                const bar = document.getElementById('measure-bar');
                if (btn) btn.classList.toggle('active', measureActive);
                if (bar) bar.style.display = measureActive ? 'flex' : 'none';
                map.getCanvas().style.cursor = measureActive ? 'crosshair' : '';
                if (measureActive) {
                    map.doubleClickZoom.disable();
                    setHoverFeature(null);
                    hoverPopup.remove();
                    if (repdaPopup) repdaPopup.remove();
                    updateMeasureRender();
                } else {
                    map.doubleClickZoom.enable();
                }
            }

            document.getElementById('btn-measure').onclick = () => setMeasureActive(!measureActive);
            document.getElementById('btn-m-dist').onclick = function() {
                measureMode = 'distance';
                this.classList.add('active');
                document.getElementById('btn-m-area').classList.remove('active');
                updateMeasureRender();
            };
            document.getElementById('btn-m-area').onclick = function() {
                measureMode = 'area';
                this.classList.add('active');
                document.getElementById('btn-m-dist').classList.remove('active');
                updateMeasureRender();
            };
            document.getElementById('btn-m-undo').onclick = () => { measureCoords.pop(); updateMeasureRender(); };
            document.getElementById('btn-m-clear').onclick = () => { measureCoords = []; updateMeasureRender(); };
            document.getElementById('btn-m-exit').onclick = () => { measureCoords = []; updateMeasureRender(); setMeasureActive(false); };
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && measureActive) {
                    measureCoords = [];
                    updateMeasureRender();
                    setMeasureActive(false);
                }
            });

            // Capa opcional REPDA Nacional (carga perezosa 0 bytes hasta activar checkbox)
            let repdaInitialized = false;
            let repdaHovered = false;
            const repdaPopup = new maplibregl.Popup({ offset: 12, className: 'marker-popup', closeButton: true });

            function ensureRepdaLayer() {
                if (repdaInitialized || !REPDA_PMTILES_URL) return;
                repdaInitialized = true;
                map.addSource('repda-src', {
                    type: 'vector',
                    url: 'pmtiles://' + REPDA_PMTILES_URL,
                    minzoom: 4,
                    maxzoom: 8
                });
                const colorMatch = ['match', ['get', 'u']];
                Object.entries(repdaUseColors).forEach(([uso, col]) => colorMatch.push(uso, col));
                colorMatch.push('#64748b');

                map.addLayer({
                    id: 'repda-points',
                    type: 'circle',
                    source: 'repda-src',
                    'source-layer': 'repda',
                    layout: { visibility: 'visible' },
                    paint: {
                        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 1.4, 7, 2.8, 10, 4.8, 14, 7.2],
                        'circle-color': colorMatch,
                        'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 4, 0.3, 9, 1.1],
                        'circle-stroke-color': '#FFFFFF',
                        'circle-opacity': 0.9
                    }
                }, 'measure-fill');

                let lastRepdaFolio = null;
                map.on('mousemove', 'repda-points', (e) => {
                    if (measureActive || !e.features || !e.features.length) return;
                    repdaHovered = true;
                    map.getCanvas().style.cursor = 'pointer';
                    const p = e.features[0].properties;
                    const folioKey = `${p.f || ''}|${p.u || ''}|${p.v || ''}`;
                    if (lastRepdaFolio !== folioKey) {
                        lastRepdaFolio = folioKey;
                        const vol = Number(p.v || 0).toLocaleString('es-MX');
                        hoverPopup.setLngLat(e.lngLat).setHTML(
                            `<b>REPDA · ${escapeHtml(p.u || 'OTROS')}</b><br>` +
                            `<span style="color:#D4C19C;">Folio: ${escapeHtml(p.f || 'S/D')} · ${vol} m³/año</span>`
                        );
                        if (!hoverPopup.isOpen()) hoverPopup.addTo(map);
                    } else {
                        hoverPopup.setLngLat(e.lngLat);
                        if (!hoverPopup.isOpen()) hoverPopup.addTo(map);
                    }
                });
                map.on('mouseleave', 'repda-points', () => {
                    repdaHovered = false;
                    lastRepdaFolio = null;
                    map.getCanvas().style.cursor = measureActive ? 'crosshair' : '';
                    hoverPopup.remove();
                });
                map.on('click', 'repda-points', (e) => {
                    if (measureActive || !e.features || !e.features.length) return;
                    const p = e.features[0].properties;
                    const vol = Number(p.v || 0).toLocaleString('es-MX');
                    const usoCol = repdaUseColors[p.u] || '#64748b';
                    // Cruce espacial directo con la vulnerabilidad subyacente
                    const vulnUnder = map.queryRenderedFeatures(e.point, { layers: ['vuln-fill'] });
                    let vulnBadgeHtml = '<span style="color:#64748B;font-size:11px;">Fuera de polígonos de vulnerabilidad</span>';
                    if (vulnUnder && vulnUnder.length) {
                        const vp = vulnUnder[0].properties;
                        const vc = String(vp.v || '');
                        const vCol = vulnColors[vc] || vulnColors.default;
                        const vLbl = vulnLabels[vc] || 'Sin Datos';
                        vulnBadgeHtml = `<span class="coord-dictamen-badge" style="background:${vCol};">${escapeHtml(vLbl)}</span>` +
                            `<div style="font-size:10.5px;color:#475569;">Acuífero ${escapeHtml(String(vp.c || '').padStart(4, '0'))} - ${escapeHtml(vp.n || '')}</div>`;
                    }
                    const html = `
                        <div class="repda-popup-card">
                            <b class="rp-title">${iconDropSm} Aprovechamiento REPDA</b>
                            <span class="coord-dictamen-badge" style="background:${usoCol};">${escapeHtml(p.u || 'OTROS')}</span>
                            <table class="repda-popup-table">
                                <tr><td class="rk">Folio:</td><td class="rv">${escapeHtml(p.f || 'S/D')}</td></tr>
                                <tr><td class="rk">Expediente:</td><td class="rv">${escapeHtml(p.e || 'S/D')}</td></tr>
                                <tr><td class="rk">Titular:</td><td class="rv">${escapeHtml(p.t || 'S/D')}</td></tr>
                                <tr><td class="rk">Volumen:</td><td class="rv">${vol} m³/año</td></tr>
                            </table>
                            <div class="coord-dictamen-box">
                                <div style="font-size:10.5px;font-weight:700;color:#691C32;margin-bottom:3px;">VULNERABILIDAD EN SITIO</div>
                                ${vulnBadgeHtml}
                            </div>
                        </div>
                    `;
                    repdaPopup.setLngLat(e.lngLat).setHTML(html).addTo(map);
                });
            }

            map.once('idle', () => loadingPill.classList.add('hidden'));
            map.on('error', (ev) => {
                if (ev && ev.error) console.warn('MapLibre aviso:', ev.error.message || ev.error);
            });

            // Hover & Click sobre polígonos MVT (setFeatureState instantáneo solo en vuln-line)
            map.on('mousemove', 'vuln-fill', (e) => {
                if (measureActive || repdaHovered || !e.features || !e.features.length) return;
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
                if (!repdaHovered) map.getCanvas().style.cursor = measureActive ? 'crosshair' : '';
                setHoverFeature(null);
                if (!repdaHovered) hoverPopup.remove();
            });

            map.on('click', 'vuln-fill', (e) => {
                if (measureActive || !e.features || !e.features.length) return;
                if (repdaInitialized && map.getLayoutProperty('repda-points', 'visibility') === 'visible') {
                    const repdaHits = map.queryRenderedFeatures(e.point, { layers: ['repda-points'] });
                    if (repdaHits.length) return;
                }
                const f = e.features[0];
                const fid = f.properties.fid != null ? f.properties.fid : f.id;
                setClickedFeature(fid);
                const aqKey = findAquiferKeyByClave(f.properties.c);
                if (aqKey) showDockedInfo(aqKey, f.properties.v);
            });

            // Clic general: modo medición o clic fuera de polígonos
            map.on('click', (e) => {
                if (measureActive) {
                    measureCoords.push([e.lngLat.lng, e.lngLat.lat]);
                    updateMeasureRender();
                    return;
                }
                if (repdaInitialized && map.getLayoutProperty('repda-points', 'visibility') === 'visible') {
                    if (map.queryRenderedFeatures(e.point, { layers: ['repda-points'] }).length) return;
                }
                const feats = map.queryRenderedFeatures(e.point, { layers: ['vuln-fill'] });
                if (!feats.length) {
                    setClickedFeature(null);
                    const panelVisible = document.getElementById('docked-panel').style.display !== 'none';
                    if (searchedName && panelVisible) {
                        showDockedInfo(searchedName, null);
                    } else if (!searchedName) {
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

            document.getElementById('chk-repda').onchange = e => {
                if (e.target.checked) {
                    ensureRepdaLayer();
                    if (map.getLayer('repda-points')) map.setLayoutProperty('repda-points', 'visibility', 'visible');
                } else {
                    if (map.getLayer('repda-points')) map.setLayoutProperty('repda-points', 'visibility', 'none');
                    repdaPopup.remove();
                }
            };
            document.getElementById('chk-c10').onchange = e => {
                if (map.getLayer('c10-line')) map.setLayoutProperty('c10-line', 'visibility', e.target.checked ? 'visible' : 'none');
            };
            document.getElementById('chk-c1').onchange = e => {
                if (map.getLayer('c1-line')) map.setLayoutProperty('c1-line', 'visibility', e.target.checked ? 'visible' : 'none');
            };
            document.getElementById('btn-export-all-csv').onclick = exportAllAquifersCsv;

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
            searchInput.oninput = (e) => {
                syncClearSearchBtn();
                renderDropdown(e.target.value);
            };
            document.getElementById('btn-clear-search').onclick = () => {
                clearSelection(true);
                searchList.style.display = 'none';
                searchInput.focus();
            };
            document.getElementById('btn-reopen-dock').onclick = () => {
                if (searchedName) showDockedInfo(searchedName, null);
            };
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
                box.style.cssText = 'color:#333;text-align:center;min-width:170px;';
                const titleEl = document.createElement('b');
                titleEl.style.cssText = 'color:#691C32;font-size:13px;display:block;margin-bottom:4px;';
                titleEl.textContent = rawName;
                const latEl = document.createElement('span');
                latEl.style.cssText = 'font-size:11px;color:#555;display:block;';
                latEl.textContent = `Lat: ${lat.toFixed(5)}°`;
                const lonEl = document.createElement('span');
                lonEl.style.cssText = 'font-size:11px;color:#555;display:block;';
                lonEl.textContent = `Lon: ${lon.toFixed(5)}°`;
                const dictBox = document.createElement('div');
                dictBox.className = 'coord-dictamen-box';
                dictBox.textContent = 'Evaluando vulnerabilidad...';
                box.appendChild(titleEl);
                box.appendChild(latEl);
                box.appendChild(lonEl);
                box.appendChild(dictBox);

                const markerPopup = new maplibregl.Popup({ offset: 32, className: 'marker-popup', closeButton: true }).setDOMContent(box);
                tempMarker = new maplibregl.Marker({ color: '#691C32' })
                    .setLngLat([lon, lat])
                    .setPopup(markerPopup)
                    .addTo(map);
                activeCoordPoint = { lat, lon, name: rawName, dictamen: '' };
                tempMarker.togglePopup();

                const myEvalToken = ++coordEvalToken;
                let dictamenResuelto = false;
                const consultarDictamenPunto = (esFinal = false) => {
                    if (dictamenResuelto || myEvalToken !== coordEvalToken) return;
                    const pt = map.project([lon, lat]);
                    const hits = map.queryRenderedFeatures(pt, { layers: ['vuln-fill'] });
                    if (hits && hits.length) {
                        dictamenResuelto = true;
                        dictBox.innerHTML = '';
                        const hp = hits[0].properties;
                        const vc = String(hp.v || '');
                        const vCol = vulnColors[vc] || vulnColors.default;
                        const vLbl = vulnLabels[vc] || 'Sin Datos';
                        const cl = String(hp.c || '').padStart(4, '0');
                        const nom = hp.n || 'Sin Nombre';
                        activeCoordPoint.dictamen = `${vLbl} (${cl})`;

                        const badge = document.createElement('span');
                        badge.className = 'coord-dictamen-badge';
                        badge.style.background = vCol;
                        badge.textContent = vLbl;

                        const aqSpan = document.createElement('span');
                        aqSpan.className = 'coord-dictamen-aq';
                        aqSpan.textContent = `${cl} - ${nom}`;

                        dictBox.appendChild(badge);
                        dictBox.appendChild(aqSpan);

                        const aqKey = findAquiferKeyByClave(cl);
                        if (aqKey) {
                            const fBtn = document.createElement('button');
                            fBtn.type = 'button';
                            fBtn.className = 'coord-dictamen-btn btn-ico-flex';
                            fBtn.innerHTML = `${iconFocusSm}<span>Ver ficha del acuífero</span>`;
                            fBtn.onclick = () => triggerSearch(aqKey);
                            dictBox.appendChild(fBtn);
                        }
                    } else if (esFinal) {
                        dictamenResuelto = true;
                        dictBox.innerHTML = '';
                        activeCoordPoint.dictamen = 'Sin cobertura';
                        const noneEl = document.createElement('span');
                        noneEl.style.cssText = 'font-size:11px;color:#64748B;';
                        noneEl.textContent = 'Sin cobertura de polígonos en este punto';
                        dictBox.appendChild(noneEl);
                    }
                };

                const curCenter = map.getCenter();
                const yaEnDestino = Math.abs(curCenter.lat - lat) < 0.002 && Math.abs(curCenter.lng - lon) < 0.002 && map.getZoom() >= 11.0;
                if (yaEnDestino) {
                    consultarDictamenPunto(false);
                    if (!dictamenResuelto) {
                        map.once('idle', () => consultarDictamenPunto(true));
                        setTimeout(() => consultarDictamenPunto(true), 1200);
                    }
                } else {
                    map.flyTo({ center: [lon, lat], zoom: 11.5, duration: 850 });
                    map.once('moveend', () => {
                        consultarDictamenPunto(false);
                        if (!dictamenResuelto && myEvalToken === coordEvalToken) {
                            map.once('idle', () => consultarDictamenPunto(true));
                            setTimeout(() => consultarDictamenPunto(true), 2200);
                        }
                    });
                }
            };

            document.getElementById('btn-clear-coord').onclick = () => {
                coordEvalToken++;
                if (tempMarker) tempMarker.remove();
                tempMarker = null;
                activeCoordPoint = null;
                document.getElementById('coord-lat').value = '';
                document.getElementById('coord-lon').value = '';
                document.getElementById('coord-name').value = '';
                document.getElementById('coord-error').style.display = 'none';
            };

            document.getElementById('btn-reset').onclick = () => {
                coordEvalToken++;
                clearSelection();
                currentVulnFilter = 'all';
                document.querySelector('input[name="vuln-filter"][value="all"]').checked = true;
                updateFilterStyles();
                if (tempMarker) { tempMarker.remove(); tempMarker = null; }
                activeCoordPoint = null;
                measureCoords = [];
                updateMeasureRender();
                setMeasureActive(false);
                repdaPopup.remove();
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
                const repdaVisible = document.getElementById('chk-repda') && document.getElementById('chk-repda').checked;
                const boxW = 350;
                const boxH = repdaVisible ? 260 : 225;
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
                if (repdaVisible) {
                    const ry = by + 224;
                    ctx.beginPath();
                    ctx.arc(bx + 31, ry + 7, 8, 0, Math.PI * 2);
                    ctx.fillStyle = '#2563eb';
                    ctx.fill();
                    ctx.strokeStyle = '#FFFFFF';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                    ctx.fillStyle = '#1E293B';
                    ctx.font = 'bold 17px "Segoe UI", Arial, sans-serif';
                    ctx.fillText('Puntos: Aprovechamientos REPDA', bx + 54, ry + 13);
                }

                // 3b. Cuadro resumen del acuífero seleccionado (arriba de la barra de escala)
                if (aqMeta && aqMeta.clases) {
                    const activeCls = ['5', '4', '3', '2', '1'].filter(c => aqMeta.clases[c] && aqMeta.clases[c].count > 0);
                    const sumW = 470;
                    const sumH = 112 + activeCls.length * 30;
                    const sumX = wCanvas - sumW - 28;
                    const sumY = hHeader + hMap - 96 - sumH;

                    ctx.fillStyle = 'rgba(255,255,255,0.95)';
                    ctx.strokeStyle = '#BC955C';
                    ctx.lineWidth = 3;
                    ctx.fillRect(sumX, sumY, sumW, sumH);
                    ctx.strokeRect(sumX, sumY, sumW, sumH);

                    ctx.fillStyle = '#691C32';
                    ctx.fillRect(sumX, sumY, sumW, 42);
                    ctx.fillStyle = '#FFFFFF';
                    ctx.font = 'bold 20px "Segoe UI", Arial, sans-serif';
                    ctx.fillText(`Distribución: ${aqMeta.clave} - ${aqMeta.nombre.slice(0, 26)}`, sumX + 16, sumY + 28);

                    // Barra apilada porcentual
                    let curX = sumX + 16;
                    const barW = sumW - 32;
                    const barY = sumY + 54;
                    activeCls.forEach(c => {
                        const segW = (aqMeta.clases[c].pct / 100) * barW;
                        ctx.fillStyle = vulnColors[c];
                        ctx.fillRect(curX, barY, segW, 14);
                        curX += segW;
                    });
                    ctx.strokeStyle = '#CBD5E1';
                    ctx.lineWidth = 1.5;
                    ctx.strokeRect(sumX + 16, barY, barW, 14);

                    // Filas por clase
                    activeCls.forEach((c, idx) => {
                        const info = aqMeta.clases[c];
                        const ry = sumY + 94 + idx * 30;
                        ctx.fillStyle = vulnColors[c];
                        ctx.fillRect(sumX + 16, ry - 14, 16, 16);
                        ctx.strokeStyle = '#334155';
                        ctx.lineWidth = 1;
                        ctx.strokeRect(sumX + 16, ry - 14, 16, 16);
                        ctx.fillStyle = '#1E293B';
                        ctx.font = '18px "Segoe UI", Arial, sans-serif';
                        ctx.fillText(vulnLabels[c], sumX + 42, ry);
                        ctx.textAlign = 'right';
                        ctx.font = 'bold 18px "Segoe UI", Arial, sans-serif';
                        ctx.fillText(`${info.pct.toFixed(1)}%  ·  ${info.area_km2.toLocaleString('es-MX', { maximumFractionDigits: 1 })} km²`, sumX + sumW - 16, ry);
                        ctx.textAlign = 'left';
                    });

                    const totY = sumY + sumH - 14;
                    ctx.fillStyle = '#691C32';
                    ctx.font = 'bold 18px "Segoe UI", Arial, sans-serif';
                    ctx.fillText('Superficie total', sumX + 16, totY);
                    ctx.textAlign = 'right';
                    ctx.fillText(`${aqMeta.area_km2.toLocaleString('es-MX', { maximumFractionDigits: 1 })} km² (${aqMeta.poligonos} pol.)`, sumX + sumW - 16, totY);
                    ctx.textAlign = 'left';
                }

                // 3c. Etiqueta de medición activa si existe (texto limpio institucional sin emojis)
                if (latestMeasureText) {
                    const txtMed = `Medición · ${latestMeasureText}`;
                    ctx.font = 'bold 20px "Segoe UI", Arial, sans-serif';
                    const mW = Math.max(360, Math.ceil(ctx.measureText(txtMed).width) + 54);
                    const mx = (wCanvas - mW) / 2;
                    const my = hHeader + 18;
                    ctx.fillStyle = 'rgba(105,28,50,0.94)';
                    ctx.fillRect(mx, my, mW, 42);
                    ctx.strokeStyle = '#BC955C';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(mx, my, mW, 42);
                    ctx.fillStyle = '#FFFFFF';
                    ctx.textAlign = 'center';
                    ctx.fillText(txtMed, wCanvas / 2, my + 28);
                    ctx.textAlign = 'left';
                }

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
                btn.innerHTML = iconSpinner;
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
                    btn.innerHTML = iconPrint;
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
                        if (document.getElementById('chk-repda').checked && REPDA_PMTILES_URL) {
                            offMap.addSource('repda-src', {
                                type: 'vector',
                                url: 'pmtiles://' + REPDA_PMTILES_URL,
                                minzoom: 4,
                                maxzoom: 8
                            });
                            const rMatch = ['match', ['get', 'u']];
                            Object.entries(repdaUseColors).forEach(([u, c]) => rMatch.push(u, c));
                            rMatch.push('#64748b');
                            offMap.addLayer({
                                id: 'repda-points', type: 'circle', source: 'repda-src', 'source-layer': 'repda',
                                paint: {
                                    'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 1.6, 7, 3.0, 10, 5.0, 14, 7.5],
                                    'circle-color': rMatch,
                                    'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 4, 0.4, 9, 1.2],
                                    'circle-stroke-color': '#FFFFFF',
                                    'circle-opacity': 0.92
                                }
                            });
                        }
                        if (latestMeasureGeoJSON.features.length) {
                            offMap.addSource('measure-src', { type: 'geojson', data: latestMeasureGeoJSON });
                            offMap.addLayer({ id: 'measure-fill', type: 'fill', source: 'measure-src', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#691C32', 'fill-opacity': 0.18 } });
                            offMap.addLayer({ id: 'measure-line', type: 'line', source: 'measure-src', filter: ['==', ['geometry-type'], 'LineString'], paint: { 'line-color': '#691C32', 'line-width': 2.8, 'line-dasharray': [2.5, 1.5] } });
                            offMap.addLayer({ id: 'measure-pts', type: 'circle', source: 'measure-src', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': 5, 'circle-color': '#FFFFFF', 'circle-stroke-width': 2.5, 'circle-stroke-color': '#691C32' } });
                        }
                        if (activeCoordPoint) {
                            const lblTxt = activeCoordPoint.dictamen
                                ? `${activeCoordPoint.name} · ${activeCoordPoint.dictamen}`
                                : activeCoordPoint.name;
                            offMap.addSource('coord-pt-src', {
                                type: 'geojson',
                                data: { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [activeCoordPoint.lon, activeCoordPoint.lat] }, properties: { lbl: lblTxt } }] }
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

            let graticuleRaf = null;
            let lastGraticuleTs = 0;
            function scheduleGraticuleUpdate() {
                if (!map.getLayer('graticule-line') || map.getLayoutProperty('graticule-line', 'visibility') === 'none') return;
                const now = performance.now();
                if (now - lastGraticuleTs < 60) {
                    if (!graticuleRaf) {
                        graticuleRaf = requestAnimationFrame(() => {
                            graticuleRaf = null;
                            lastGraticuleTs = performance.now();
                            updateGraticule();
                        });
                    }
                    return;
                }
                lastGraticuleTs = now;
                updateGraticule();
            }

            map.on('move', scheduleGraticuleUpdate);
            map.on('moveend', updateGraticule);
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
    .replace("__REPDA_PMTILES_URL__", _json_seguro_html(repda_pmtiles_url))
)

if hasattr(st, "iframe"):
    st.iframe(html_code, height=760)
else:
    components.html(html_code, height=760)
