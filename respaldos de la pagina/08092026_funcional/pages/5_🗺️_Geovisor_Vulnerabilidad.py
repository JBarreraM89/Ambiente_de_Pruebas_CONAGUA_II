# -*- coding: utf-8 -*-
"""
Geovisor de Vulnerabilidad e Hidráulica (Arquitectura Híbrida Python + JS)
- Mapa a pantalla completa (Full Width & Full Height).
- Mallado perfecto: Etiquetas desplazadas para no superponerse con las líneas.
- Diseño de Leyenda y Controles ajustados al pixel.
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
            height: 79vh !important; /* 85% de la pantalla para dejar espacio al header */
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

    # Truncar coordenadas a 5 decimales (1 metro de precisión)
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
        /* Ajuste para que el mapa ocupe el 100% de la ventana del Iframe */
        html, body {{ margin: 0; padding: 0; height: 100%; width: 100%; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        #map {{ width: 100%; height: 100%; background-color: #e5e5e5; }}
        
        /* Jerarquía Z-Index */
        .leaflet-top {{ z-index: 1000 !important; }}
        .leaflet-bottom {{ z-index: 900 !important; }}
        
        /* Panel de Controles Principal */
        .leaflet-custom-controls {{
            background: white; padding: 15px; border-radius: 8px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2); width: 320px;
            max-height: 85vh; overflow-y: auto; transition: all 0.3s ease;
            z-index: 9999 !important; position: relative; margin-bottom: 10px !important;
        }}
        
        .panel-close-button {{
            float: right; cursor: pointer; font-size: 22px; font-weight: bold; color: #999; margin-top: -5px;
        }}
        .panel-close-button:hover {{ color: #333; }}
        
        .leaflet-open-button {{
            background: white; padding: 8px 12px; border-radius: 5px; cursor: pointer;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2); font-size: 18px; font-weight: bold;
            border: none; color: #333; display: none;
            margin-bottom: 10px !important; z-index: 9999 !important; position: relative;
        }}
        .leaflet-open-button:hover {{ background: #f4f4f4; }}

        .control-section {{ margin-bottom: 15px; position: relative; }}
        .control-section label {{ font-weight: bold; font-size: 13px; color: #333; display: block; margin-bottom: 5px; }}
        .theme-switch {{ display: flex; border: 1px solid #ccc; border-radius: 5px; overflow: hidden; }}
        .theme-btn {{ flex: 1; padding: 8px; border: none; background: #f0f0f0; cursor: pointer; font-size: 12px; }}
        .theme-btn.active {{ background: #691C32; color: white; font-weight: bold; }}
        
        input[type="text"], input[type="number"] {{ width: 100%; padding: 6px; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; font-size: 12px; margin-bottom: 5px; }}
        input[type="range"] {{ width: 100%; box-sizing: border-box; margin: 0; padding: 0; cursor: pointer; }}
        
        /* Buscador Custom */
        .custom-dropdown {{ position: relative; width: 100%; }}
        .custom-dropdown-list {{
            position: absolute; top: 100%; left: 0; right: 0; background: white;
            border: 1px solid #ccc; border-top: none; border-radius: 0 0 4px 4px;
            max-height: 150px; overflow-y: auto; z-index: 10000; display: none;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .custom-dropdown-item {{ padding: 8px; font-size: 12px; cursor: pointer; border-bottom: 1px solid #eee; }}
        .custom-dropdown-item:hover {{ background-color: #f0f0f0; color: #691C32; font-weight: bold; }}
        
        .flex-row {{ display: flex; gap: 5px; }}
        .flex-row input {{ width: 50%; }}
        
        .action-button {{ width: 100%; padding: 8px; background: #244062; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }}
        .action-button:hover {{ background: #1a2e47; }}
        
        .radio-group {{ display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; margin-top: 5px; }}
        .radio-group label {{ font-weight: normal !important; display: inline-flex; align-items: center; cursor: pointer; margin-bottom: 0 !important; }}
        .radio-group input[type="radio"] {{ width: auto; margin-right: 4px; cursor: pointer; }}
        
        .info-panel-row {{ margin-bottom: 5px; font-size: 13px; border-bottom: 1px solid #eee; padding-bottom: 3px; }}
        .info-panel-row strong {{ color: #691C32; }}
        
        /* Botón de impresión minimalista */
        .print-btn {{ 
            background: white; border: none; border-radius: 4px; 
            cursor: pointer; padding: 5px; font-size: 16px; color: #333; 
            display: flex; align-items: center; justify-content: center;
            width: 30px; height: 30px; box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            margin-bottom: 15px !important; /* Separación de la escala */
        }}
        .print-btn:hover {{ background: #f4f4f4; }}
        
        /* Simbología en bottomleft */
        .legend {{ 
            background: white; padding: 12px; border: none; 
            border-radius: 6px; font-size: 12px; line-height: 18px; color: #333; 
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            margin-bottom: 20px !important; margin-left: 20px !important;
            z-index: 800 !important; position: relative;
        }}
        .legend b {{ font-size: 13px; display: block; margin-bottom: 8px; }}
        .legend i {{ width: 14px; height: 14px; float: left; margin-right: 8px; opacity: 0.9; }}
        
        /* Controles Inferior Derecho (Escala y Logo) */
        .leaflet-control-scale {{ margin-bottom: 5px !important; margin-right: 10px !important; }}
        .leaflet-logo-control {{ margin-bottom: 5px !important; margin-right: 10px !important; text-align: right; }}
        .leaflet-logo-control img {{ width: 90px; opacity: 0.9; }}
    </style>
</head>
<body>

    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js"></script>
    
    <!-- INYECCIÓN DEL CÓDIGO FUENTE DEL PLUGIN DE MALLADO (GRATICULE) -->
    <script>
        L.LatLngGraticule = L.Layer.extend({{
            options: {{
                showLabel: true, opacity: 1, weight: 0.8, color: '#666', font: 'bold 12px Arial, sans-serif', fontColor: '#333',
                zoomInterval: [
                    {{start: 2, end: 2, interval: 40}}, {{start: 3, end: 3, interval: 20}},
                    {{start: 4, end: 4, interval: 10}}, {{start: 5, end: 5, interval: 5}},
                    {{start: 6, end: 7, interval: 2}}, {{start: 8, end: 9, interval: 1}},
                    {{start: 10, end: 20, interval: 0.5}}
                ]
            }},
            initialize: function (options) {{ L.setOptions(this, options); }},
            onAdd: function (map) {{
                this._map = map;
                this._canvas = L.DomUtil.create('canvas', 'leaflet-zoom-animated');
                this._ctx = this._canvas.getContext('2d');
                map._panes.overlayPane.appendChild(this._canvas);
                map.on('viewreset', this._reset, this);
                map.on('move', this._reset, this);
                map.on('moveend', this._reset, this);
                this._reset();
            }},
            onRemove: function (map) {{
                L.DomUtil.remove(this._canvas);
                map.off('viewreset', this._reset, this);
                map.off('move', this._reset, this);
                map.off('moveend', this._reset, this);
            }},
            _reset: function () {{
                var size = this._map.getSize();
                var lt = this._map.containerPointToLayerPoint([0, 0]);
                L.DomUtil.setPosition(this._canvas, lt);
                this._canvas.width = size.x; this._canvas.height = size.y;
                this._draw();
            }},
            _draw: function() {{
                var map = this._map; var bounds = map.getBounds();
                var zoom = map.getZoom(); var interval = 10;
                for (var i = 0; i < this.options.zoomInterval.length; i++) {{
                    if (zoom >= this.options.zoomInterval[i].start && zoom <= this.options.zoomInterval[i].end) {{
                        interval = this.options.zoomInterval[i].interval; break;
                    }}
                }}
                var ctx = this._ctx; ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
                
                var latStart = Math.ceil(bounds.getSouth() / interval) * interval;
                var latEnd = Math.floor(bounds.getNorth() / interval) * interval;
                var lngStart = Math.ceil(bounds.getWest() / interval) * interval;
                var lngEnd = Math.floor(bounds.getEast() / interval) * interval;

                // 1. Dibujar líneas
                ctx.beginPath();
                for (var lat = latStart; lat <= latEnd; lat += interval) {{
                    var p1 = map.latLngToContainerPoint([lat, bounds.getWest()]);
                    var p2 = map.latLngToContainerPoint([lat, bounds.getEast()]);
                    ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y);
                }}
                for (var lng = lngStart; lng <= lngEnd; lng += interval) {{
                    var p1 = map.latLngToContainerPoint([bounds.getNorth(), lng]);
                    var p2 = map.latLngToContainerPoint([bounds.getSouth(), lng]);
                    ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y);
                }}
                ctx.lineWidth = this.options.weight; 
                ctx.strokeStyle = this.options.color;
                ctx.stroke();

                // 2. Dibujar Textos con Sombra Blanca Gruesa (Desplazados de la línea)
                if (this.options.showLabel) {{
                    ctx.font = this.options.font;
                    ctx.textAlign = "center";
                    ctx.textBaseline = "middle";
                    
                    // Latitudes (Verticales, desplazadas hacia abajo)
                    for (var lat = latStart; lat <= latEnd; lat += interval) {{
                        var p1 = map.latLngToContainerPoint([lat, bounds.getWest()]);
                        let text = lat.toFixed(0) + '°';
                        
                        ctx.save();
                        // Posición: 20px desde la izquierda, 25px por debajo de la línea
                        ctx.translate(20, p1.y + 25);
                        ctx.rotate(-Math.PI / 2);
                        
                        ctx.strokeStyle = "white"; ctx.lineWidth = 4; ctx.strokeText(text, 0, 0);
                        ctx.fillStyle = this.options.fontColor; ctx.fillText(text, 0, 0);
                        
                        ctx.restore();
                    }}
                    
                    // Longitudes (Horizontales, desplazadas a la derecha)
                    for (var lng = lngStart; lng <= lngEnd; lng += interval) {{
                        var p1 = map.latLngToContainerPoint([bounds.getNorth(), lng]);
                        let text = lng.toFixed(0) + '°';
                        
                        ctx.save();
                        // Posición: 25px a la derecha de la línea, 20px desde arriba
                        ctx.translate(p1.x + 25, 20);
                        
                        ctx.strokeStyle = "white"; ctx.lineWidth = 4; ctx.strokeText(text, 0, 0);
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

        const map = L.map('map', {{ preferCanvas: true }}).setView([23.6345, -102.5528], 5);
        
        const basemaps = {{
            "Neutral (defecto)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}').addTo(map),
            "OpenStreetMap": L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png'),
            "Estándar (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'),
            "Satélite (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}'),
            "Topográfico (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}'),
            "Terreno (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'),
            "Océanos (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'),
            "Gris Oscuro (ESRI)": L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}')
        }};
        L.control.layers(basemaps, null, {{position: 'topright'}}).addTo(map);

        // ==========================================
        // ORDEN ESTRICTO DE CONTROLES EN BOTTOM-RIGHT
        // ==========================================
        
        // 1. Logo SSIG
        const LogoControl = L.Control.extend({{
            onAdd: function() {{
                const c = L.DomUtil.create('div', 'leaflet-logo-control');
                c.innerHTML = `<img src="https://raw.githubusercontent.com/Dchable16/geovisor_vulnerabilidad/main/logos/Logo_SSIG.png" alt="Logo SSIG">`;
                return c;
            }}
        }});
        new LogoControl({{ position: 'bottomright' }}).addTo(map);

        // 2. Escala
        L.control.scale({{ position: 'bottomright', imperial: false }}).addTo(map);

        // 3. Botón de Impresión (Sin wrapper para que se oculte completo)
        const printControl = L.control({{position: 'bottomright'}});
        printControl.onAdd = function() {{
            const btn = L.DomUtil.create('button', 'print-btn');
            btn.innerHTML = '🖨️';
            btn.title = 'Descargar mapa como imagen PNG';
            
            L.DomEvent.on(btn, 'click', function() {{
                btn.innerHTML = '⏳';
                
                // Filtro: Oculta controles interactivos, pero DEJA la leyenda, escala y logo
                htmlToImage.toPng(document.getElementById('map'), {{
                    quality: 1.0,
                    pixelRatio: 2,
                    filter: function(node) {{
                        if (!node.classList) return true;
                        const exclude = ['leaflet-control-zoom', 'leaflet-control-layers', 'print-btn', 'leaflet-custom-controls', 'leaflet-open-button'];
                        for (let i=0; i<exclude.length; i++) {{
                            if (node.classList.contains(exclude[i])) return false;
                        }}
                        return true;
                    }}
                }}).then(function (dataUrl) {{
                    let link = document.createElement('a');
                    link.download = 'Mapa_Geovisor.png';
                    link.href = dataUrl;
                    link.click();
                    btn.innerHTML = '🖨️';
                }}).catch(function(error) {{
                    console.error("Error al exportar:", error);
                    btn.innerHTML = '🖨️';
                }});
            }});
            return btn;
        }};
        printControl.addTo(map);

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

        function createPopupContent(props, theme) {{
            let html = '';
            if(theme === 'vuln') {{
                html += `<div class="info-panel-row"><strong>Acuífero:</strong> ${{props.NOM_ACUIF || 'S/D'}}</div>`;
                html += `<div class="info-panel-row"><strong>Clave:</strong> ${{props.CLAVE_ACUI || 'S/D'}}</div>`;
                html += `<div class="info-panel-row"><strong>Vulnerabilidad:</strong> Nivel ${{props.VULNERABIL || 'S/D'}}</div>`;
            }} else if(theme === 'hydro') {{
                html += `<div class="info-panel-row"><strong>Acuífero:</strong> ${{props.NOM_ACUIF || 'S/D'}}</div>`;
                html += `<div class="info-panel-row"><strong>Transmisividad:</strong> ${{props.transmisividad_media || 'S/D'}} m²/d</div>`;
                html += `<div class="info-panel-row"><strong>Conductividad:</strong> ${{props.conductividad_media || 'S/D'}} m/d</div>`;
                html += `<div class="info-panel-row"><strong>Coef. Almacenamiento:</strong> ${{props.coef_almacenamiento_medio || 'S/D'}}</div>`;
                html += `<div class="info-panel-row"><strong>Pozos Registrados:</strong> ${{props.pozos_registrados || 'S/D'}}</div>`;
            }} else if(theme === 'pozo') {{
                html += `<div class="info-panel-row"><strong>Pozo:</strong> ${{props.NOMBRE_POZO || 'S/D'}}</div>`;
                html += `<div class="info-panel-row"><strong>Acuífero:</strong> ${{props.ACUIFERO || 'S/D'}}</div>`;
                html += `<div class="info-panel-row"><strong>Transmisividad:</strong> ${{props.T_m2d || 'S/D'}}</div>`;
                html += `<div class="info-panel-row"><strong>Profundidad:</strong> ${{props.PROFUNDIDAD || 'S/D'}} m</div>`;
            }}
            return html;
        }}

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

        // CREACIÓN DE CAPAS
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
                    layer.bindPopup(createPopupContent(feature.properties, 'vuln'));
                    
                    layer.on('mouseover', function() {{ 
                        let searchKey = feature.properties.CLAVE_ACUI.padStart(4, '0') + " - " + feature.properties.NOM_ACUIF;
                        if (searchKey !== currentSelectedAquifer) {{
                            this.setStyle({{weight: 3, color: '#007BFF'}}); 
                        }}
                    }});
                    layer.on('mouseout', function() {{ 
                        let searchKey = feature.properties.CLAVE_ACUI.padStart(4, '0') + " - " + feature.properties.NOM_ACUIF;
                        if (searchKey !== currentSelectedAquifer) {{
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
                    layer.bindPopup(createPopupContent(feature.properties, 'hydro'));
                    
                    layer.on('mouseover', function() {{ 
                        let searchKey = feature.properties.CLAVE_ACUI.padStart(4, '0') + " - " + feature.properties.NOM_ACUIF;
                        if (searchKey !== currentSelectedAquifer) {{
                            this.setStyle({{weight: 3, color: '#000'}}); 
                        }}
                    }});
                    layer.on('mouseout', function() {{ 
                        let searchKey = feature.properties.CLAVE_ACUI.padStart(4, '0') + " - " + feature.properties.NOM_ACUIF;
                        if (searchKey !== currentSelectedAquifer) {{
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
                    layer.bindPopup(createPopupContent(feature.properties, 'pozo'));
                }}
            }});
        }}

        if(dataCosta10.features) layerCosta10 = L.geoJSON(dataCosta10, {{ style: function() {{ return {{color: '#007BFF', weight: 3, opacity: 0.8, fill: false}}; }} }});
        if(dataCosta1.features) layerCosta1 = L.geoJSON(dataCosta1, {{ style: function() {{ return {{color: '#FF0000', weight: 3, opacity: 0.8, fill: false}}; }} }});

        // PANEL DE CONTROLES COLAPSABLE (topleft)
        const uiControl = L.control({{position: 'topleft'}});
        uiControl.onAdd = function() {{
            const wrapper = L.DomUtil.create('div');
            L.DomEvent.disableClickPropagation(wrapper);
            L.DomEvent.disableScrollPropagation(wrapper);
            
            wrapper.innerHTML = `
                <div id="btn-open-panel" class="leaflet-open-button" title="Mostrar controles">☰ Controles</div>
                
                <div id="panel-container" class="leaflet-custom-controls">
                    <span id="btn-close-panel" class="panel-close-button" title="Ocultar controles">&times;</span>
                    <h3 style="margin-top:0; color:#691C32;">Controles</h3>
                    
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
                    
                    <button id="btn-reset" class="action-button" style="background:#e74c3c; margin-top:10px;">Restablecer Vista</button>
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
                <i style="background:#CCCCCC; border: 1px solid #666;"></i> Sin Datos
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

        // Lógica del Buscador Custom (Dropdown)
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

            if(activeTheme === 'vulnerability') updateVulnStyles();
            if(activeTheme === 'hydro' && layerHydro) layerHydro.eachLayer(l => layerHydro.resetStyle(l));
            
            let layers = activeTheme === 'vulnerability' ? indexVuln[selected] : indexHydro[selected];
            
            if(layers && layers.length > 0) {{
                let group = L.featureGroup(layers);
                map.flyToBounds(group.getBounds(), {{duration: 0.8, padding: [20, 20]}});
                layers.forEach(l => l.setStyle({{weight: 4, color: '#691C32', opacity: 1}})); 
                setTimeout(() => layers[0].openPopup(), 800);
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
            this.classList.add('active'); document.getElementById('btn-hydro').classList.remove('active');
            if(map.hasLayer(layerHydro)) map.removeLayer(layerHydro);
            if(!map.hasLayer(layerVuln)) map.addLayer(layerVuln);
            document.querySelector('.legend').style.display = 'block';
            document.getElementById('vuln-filter-section').style.display = 'block';
        }};
        document.getElementById('btn-hydro').onclick = function() {{
            activeTheme = 'hydro';
            this.classList.add('active'); document.getElementById('btn-vuln').classList.remove('active');
            if(map.hasLayer(layerVuln)) map.removeLayer(layerVuln);
            if(!map.hasLayer(layerHydro)) map.addLayer(layerHydro);
            document.querySelector('.legend').style.display = 'none';
            document.getElementById('vuln-filter-section').style.display = 'none';
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
                        color: '#333',
                        weight: 0.8,
                        opacity: 0.5,
                        fontColor: '#333',
                        zoomInterval: [
                            {{start: 2, end: 3, interval: 30}},
                            {{start: 4, end: 4, interval: 10}},
                            {{start: 5, end: 7, interval: 5}},
                            {{start: 8, end: 10, interval: 1}},
                            {{start: 11, end: 20, interval: 0.5}}
                        ]
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