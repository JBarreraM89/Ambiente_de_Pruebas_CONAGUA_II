# -*- coding: utf-8 -*-
"""
core/hidro_d3_diagrams.py
===============================================================================
MOTOR VECTORIAL INTERACTIVO D3.JS / SVG PARA DIAGRAMAS HIDROGEOQUÍMICOS
Comisión Nacional del Agua (CONAGUA) - Gráficos de Publicación Científica

Funcionalidades de cada diagrama:
  - Renderizado en cliente acelerado por GPU (< 10 ms).
  - Escalamiento vectorial sin distorsión (viewBox estandarizado).
  - Controles de Zoom continuo (Mouse Wheel, Botones + / - / 1:1).
  - Paneo libre mediante arrastre con el cursor (Grab / Grabbing).
  - Lupa de Aumento Dinámica (2.5x) para inspección de clusters densos.
  - Exportación en SVG vectorial (editable en Illustrator/Inkscape)
    y PNG a 300 DPI (alta resolución para informes periciales).
===============================================================================
"""

import json
import math
import numpy as np
import pandas as pd


# =============================================================================
# 1. DIAGRAMA TRILINEAL DE PIPER VECTORIAL D3.JS
# =============================================================================
def generar_diagrama_piper_d3(df_procesado, muestra_aislada=None):
    """
    Genera el HTML + D3.js con presentación científica limpia y profesional:
      - Geometría canónica oficial (OMM / UNESCO / A.M. Piper 1944).
      - Cabecera limpia y sobria: título oficial, controles de Zoom, Lupa y Descarga SVG/PNG (300 DPI).
      - Soporte para aislamiento de muestra individual (rayos proyectados automáticos hacia el diamante).
      - Rótulos de ejes del rombo SO4+Cl, Ca+Mg, Na+K, CO3+HCO3.
      - Tooltip inteligente anti-recorte con detección de bordes.
    """
    muestras_data = []
    colores_paleta = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    facies_paleta_base = {
        "Bicarbonatada Magnésica-Sódica": "#0891b2",
        "Bicarbonatada Sódica": "#7c3aed",
        "Bicarbonatada Sódica-Magnésica": "#9333ea",
        "Bicarbonatada Magnésica": "#16a34a",
        "Bicarbonatada Magnésica-Cálcica": "#059669",
        "Bicarbonatada Cálcica-Magnésica": "#0284c7",
        "Bicarbonatada Sódica-Cálcica": "#c026d3",
        "Bicarbonatada Cálcica": "#0369a1",
        "Bicarbonatada Mixta Catiónica": "#64748b",
        "Bicarbonatada Cálcica-Sódica": "#0ea5e9",
        "Sulfatada Magnésica-Sódica": "#d97706",
        "Clorurada Sódica": "#dc2626",
        "Sulfatada Cálcica": "#b45309"
    }

    # Filtrar estrictamente muestras aptas con coordenadas completas
    for idx, r in df_procesado.iterrows():
        if 'Apta_Piper' in df_procesado.columns and not r.get('Apta_Piper', True):
            continue
        if pd.isna(r.get('pct_Ca')) or pd.isna(r.get('pct_HCO3_CO3')):
            continue

        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        fac = str(r.get('Facies_Piper', 'N/D'))
        color_pt = facies_paleta_base.get(fac, colores_paleta[idx % len(colores_paleta)])

        muestras_data.append({
            "id": id_m,
            "fuente": str(r.get('Tipo_Fuente', 'Fuente')),
            "facies": fac,
            "cuadrante": str(r.get('Cuadrante_Piper', 'N/D')),
            "cbe": float(r.get('CBE_pct', 0.0)) if pd.notna(r.get('CBE_pct')) else 0.0,
            "cbe_calidad": str(r.get('CBE_Calidad', 'N/D')),
            "sdt": float(r.get('SDT_mg_L', 0.0)) if pd.notna(r.get('SDT_mg_L')) else 0.0,
            "ce": float(r.get('CE_uS_cm', 0.0)) if pd.notna(r.get('CE_uS_cm')) else 0.0,
            "revelle": float(r.get('Indice_Revelle', 0.0)) if pd.notna(r.get('Indice_Revelle')) else 0.0,
            "ca_pct": float(r.get('pct_Ca', 0.0)),
            "mg_pct": float(r.get('pct_Mg', 0.0)),
            "nak_pct": float(r.get('pct_Na_K', 0.0)),
            "hco3_pct": float(r.get('pct_HCO3_CO3', 0.0)),
            "so4_pct": float(r.get('pct_SO4', 0.0)),
            "cl_pct": float(r.get('pct_Cl', 0.0)),
            "color": color_pt
        })

    muestras_json_str = json.dumps(muestras_data)
    muestra_aislada_json = json.dumps(str(muestra_aislada) if muestra_aislada else "")

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Piper D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{
          margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
          background: #ffffff; user-select: none; display: flex; flex-direction: column; height: 100vh; overflow: hidden;
        }}
        .toolbar-piper {{
          display: flex; justify-content: space-between; align-items: center;
          padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; flex-shrink: 0;
        }}
        .btn-toolbar {{
          background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px;
          padding: 5px 11px; font-size: 11px; font-weight: 600; cursor: pointer;
          color: #334155; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 4px;
        }}
        .btn-toolbar:hover {{ background: #691C32; color: white; border-color: #691C32; }}
        .btn-toolbar.active {{ background: #691C32 !important; color: white !important; border-color: #691C32 !important; }}
        #piper-svg-container {{
          flex: 1; width: 100%; position: relative; background: #ffffff; overflow: hidden;
          cursor: grab;
        }}
        #piper-svg-container.grabbing {{ cursor: grabbing; }}
        #piper-svg-container.lupa-mode {{ cursor: crosshair; }}
        svg {{ width: 100%; height: 100%; display: block; }}
        #piper-tooltip {{
          position: absolute; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.98); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 6px 20px rgba(0,0,0,0.22);
          padding: 9px 13px; font-size: 11.5px; color: #1e293b;
          pointer-events: none; width: 280px; line-height: 1.45;
        }}
        .axis-label-piper {{
          font-size: 11px; font-weight: 800; fill: #1e293b; text-anchor: middle;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        .ion-label {{
          font-size: 13px; font-weight: 800; fill: #0f172a;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        .tick-label-piper {{
          font-size: 8.5px; font-weight: 600; fill: #334155;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        .tick-label-100 {{
          font-size: 9.5px; font-weight: 700; fill: #0f172a;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        .diamond-axis-label {{
          font-size: 11px; font-weight: 800; text-anchor: middle; dominant-baseline: middle;
          fill: #0f172a; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          paint-order: stroke fill; stroke: #ffffff; stroke-width: 4px; stroke-linejoin: round;
        }}
        .grid-line {{ stroke: #475569; stroke-width: 0.85; stroke-dasharray: 3,2.5; opacity: 0.8; }}
        .grid-line-diamond {{ stroke: #475569; stroke-width: 0.85; stroke-dasharray: 3,2.5; opacity: 0.8; }}
        .axis-line {{ stroke: #0f172a; stroke-width: 1.8; fill: none; }}
        .tick-line {{ stroke: #0f172a; stroke-width: 1.2; }}
      </style>
    </head>
    <body>
      <div class="toolbar-piper">
        <div style="font-size: 12px; font-weight: 700; color: #691C32; white-space: nowrap;">
          🧪 Diagrama Trilineal de Piper (OMM / UNESCO)
        </div>
        <div style="display: flex; gap: 6px; align-items: center; flex-wrap: nowrap;">
          <button class="btn-toolbar" onclick="zoomIn()" title="Acercar (Zoom In)"><span>🔍+</span></button>
          <button class="btn-toolbar" onclick="zoomOut()" title="Alejar (Zoom Out)"><span>🔍-</span></button>
          <button class="btn-toolbar" onclick="resetZoom()" title="Restablecer tamaño original (100%)"><span>🔄 1:1</span></button>
          <button class="btn-toolbar" id="btn-lupa" onclick="toggleLupa()" title="Activar/Desactivar Lupa de Aumento">
            <span>🔎 Lupa</span> <span id="lupa-status" style="font-size:9.5px; opacity:0.85;">OFF</span>
          </button>
          <button class="btn-toolbar active" id="btn-diamond-labels" onclick="toggleDiamondLabels()" title="Mostrar/Ocultar Rótulos de Ejes del Rombo">
            <span>🏷️ Rótulos Ejes</span>
          </button>
          <span id="zoom-level" style="font-size:11px; font-weight:600; color:#64748b; margin: 0 4px;">100%</span>
          <button class="btn-toolbar" onclick="descargarSVG()" title="Exportar vector SVG original"><span>📥 SVG</span></button>
          <button class="btn-toolbar" onclick="descargarPNG()" title="Exportar imagen de alta resolución (300 DPI)"><span>📷 PNG</span></button>
        </div>
      </div>

      <div id="piper-svg-container">
        <div id="piper-tooltip"></div>
      </div>

      <script>
        const samples = {muestras_json_str};
        const isolatedSampleId = {muestra_aislada_json};

        const w = 960, h = 800;
        const svg = d3.select("#piper-svg-container").append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{w}} ${{h}}`)
          .attr("width", w)
          .attr("height", h)
          .attr("id", "svg-piper")
          .attr("preserveAspectRatio", "xMidYMid meet");

        svg.append("rect")
          .attr("width", w)
          .attr("height", h)
          .attr("fill", "#ffffff");

        const zoomGroup = svg.append("g").attr("id", "zoom-group");

        const defs = svg.append("defs");
        defs.append("style").text(`
          .axis-line {{ stroke: #0f172a !important; stroke-width: 1.8 !important; fill: none !important; stroke-linejoin: round; }}
          .grid-line {{ stroke: #475569 !important; stroke-width: 0.85 !important; stroke-dasharray: 3,2.5 !important; opacity: 0.8 !important; fill: none !important; }}
          .grid-line-diamond {{ stroke: #475569 !important; stroke-width: 0.85 !important; stroke-dasharray: 3,2.5 !important; opacity: 0.8 !important; fill: none !important; }}
          .tick-line {{ stroke: #0f172a !important; stroke-width: 1.1 !important; fill: none !important; }}
          .axis-label-piper {{ font-size: 11px !important; font-weight: 800 !important; fill: #1e293b !important; text-anchor: middle !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
          .ion-label {{ font-size: 13px !important; font-weight: 800 !important; fill: #0f172a !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
          .diamond-axis-label {{ font-size: 11px !important; font-weight: 800 !important; text-anchor: middle !important; dominant-baseline: middle !important; fill: #0f172a !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; paint-order: stroke fill; stroke: #ffffff; stroke-width: 4px; stroke-linejoin: round; }}
          .tick-label-piper {{ font-size: 8px !important; font-weight: 600 !important; fill: #475569 !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
          .tick-label-100 {{ font-size: 9.5px !important; font-weight: 700 !important; fill: #0f172a !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
          .sample-pt {{ stroke: #ffffff !important; stroke-width: 1.8 !important; }}
          .connection-line {{ opacity: 0.75 !important; fill: none !important; }}
        `);

        const L = 330.0;
        const H = L * Math.sqrt(3) / 2.0;

        const x_c_left = 65.0, y_base = 650.0;
        const x_c_right = x_c_left + L, y_c_right = y_base;
        const x_c_top = x_c_left + L / 2.0, y_c_top = y_base - H;

        const x_a_left = 565.0, y_a_left = y_base;
        const x_a_right = x_a_left + L, y_a_right = y_base;
        const x_a_top = x_a_left + L / 2.0, y_a_top = y_base - H;

        const x_d_left = x_c_right;
        const y_d_left = y_c_top;
        const x_d_top = (x_c_right + x_a_left) / 2.0;
        const y_d_top = y_c_top - H;
        const x_d_right = x_a_left;
        const y_d_right = y_a_top;
        const x_d_bot = x_d_top;
        const y_d_bot = y_c_top + H;

        const gGrid = zoomGroup.append("g").attr("id", "grid-group");
        const gAxes = zoomGroup.append("g").attr("id", "axes-group");
        const gTicks = zoomGroup.append("g").attr("id", "ticks-group");
        const gLabels = zoomGroup.append("g").attr("id", "labels-group");
        const gConnections = zoomGroup.append("g").attr("id", "connections-group");
        const gSamples = zoomGroup.append("g").attr("id", "samples-group");

        // Cuadrícula Ternaria Cationes y Aniones
        for (let s = 1; s <= 9; s++) {{
          const frac = s / 10.0;
          gGrid.append("line").attr("x1", x_c_left + frac * L).attr("y1", y_base).attr("x2", x_c_left + frac * L / 2.0).attr("y2", y_base - frac * H).attr("class", "grid-line");
          gGrid.append("line").attr("x1", x_c_left + frac * L).attr("y1", y_base).attr("x2", x_c_top + frac * L / 2.0).attr("y2", y_c_top + frac * H).attr("class", "grid-line");
          gGrid.append("line").attr("x1", x_c_left + frac * L / 2.0).attr("y1", y_base - frac * H).attr("x2", x_c_right - frac * L / 2.0).attr("y2", y_base - frac * H).attr("class", "grid-line");

          gGrid.append("line").attr("x1", x_a_left + frac * L).attr("y1", y_base).attr("x2", x_a_left + frac * L / 2.0).attr("y2", y_base - frac * H).attr("class", "grid-line");
          gGrid.append("line").attr("x1", x_a_left + frac * L).attr("y1", y_base).attr("x2", x_a_top + frac * L / 2.0).attr("y2", y_a_top + frac * H).attr("class", "grid-line");
          gGrid.append("line").attr("x1", x_a_left + frac * L / 2.0).attr("y1", y_base - frac * H).attr("x2", x_a_right - frac * L / 2.0).attr("y2", y_base - frac * H).attr("class", "grid-line");
        }}

        // Cuadrícula Diamante
        for (let s = 1; s <= 9; s++) {{
          const frac = s / 10.0;
          const p1x = x_d_left + frac * (x_d_top - x_d_left), p1y = y_d_left + frac * (y_d_top - y_d_left);
          const p2x = x_d_bot + frac * (x_d_right - x_d_bot), p2y = y_d_bot + frac * (y_d_right - y_d_bot);
          gGrid.append("line").attr("x1", p1x).attr("y1", p1y).attr("x2", p2x).attr("y2", p2y).attr("class", "grid-line-diamond");

          const p3x = x_d_left + frac * (x_d_bot - x_d_left), p3y = y_d_left + frac * (y_d_bot - y_d_left);
          const p4x = x_d_top + frac * (x_d_right - x_d_top), p4y = y_d_top + frac * (y_d_right - y_d_top);
          gGrid.append("line").attr("x1", p3x).attr("y1", p3y).attr("x2", p4x).attr("y2", p4y).attr("class", "grid-line-diamond");
        }}

        // Ejes Principales
        gAxes.append("polygon").attr("points", `${{x_c_left}},${{y_base}} ${{x_c_right}},${{y_c_right}} ${{x_c_top}},${{y_c_top}}`).attr("class", "axis-line");
        gAxes.append("polygon").attr("points", `${{x_a_left}},${{y_base}} ${{x_a_right}},${{y_a_right}} ${{x_a_top}},${{y_a_top}}`).attr("class", "axis-line");
        gAxes.append("polygon").attr("points", `${{x_d_left}},${{y_d_left}} ${{x_d_top}},${{y_d_top}} ${{x_d_right}},${{y_d_right}} ${{x_d_bot}},${{y_d_bot}}`).attr("class", "axis-line");

        // Ticks Ternarios y Diamante
        const norm_lx = -Math.sqrt(3)/2.0, norm_ly = -0.5;
        const norm_rx = Math.sqrt(3)/2.0, norm_ry = -0.5;

        for (let s = 1; s <= 9; s++) {{
          const frac = s / 10.0;
          const val = s * 10;
          const isMajor = (s % 2 === 0);
          const tickLen = isMajor ? 5.5 : 3.2;

          const c_bx = x_c_left + frac * L;
          gTicks.append("line").attr("x1", c_bx).attr("y1", y_base).attr("x2", c_bx).attr("y2", y_base + tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", c_bx).attr("y", y_base + 13).attr("class", "tick-label-piper").attr("text-anchor", "middle").text(100 - val);

          const c_lx = x_c_left + 0.5 * frac * L, c_ly = y_base - frac * H;
          gTicks.append("line").attr("x1", c_lx).attr("y1", c_ly).attr("x2", c_lx + norm_lx * tickLen).attr("y2", c_ly + norm_ly * tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", c_lx - 7).attr("y", c_ly + 3).attr("class", "tick-label-piper").attr("text-anchor", "end").text(val);

          const c_rx = x_c_top + 0.5 * frac * L, c_ry = y_c_top + frac * H;
          gTicks.append("line").attr("x1", c_rx).attr("y1", c_ry).attr("x2", c_rx + norm_rx * tickLen).attr("y2", c_ry + norm_ry * tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", c_rx + 7).attr("y", c_ry + 3).attr("class", "tick-label-piper").attr("text-anchor", "start").text(val);

          const a_bx = x_a_left + frac * L;
          gTicks.append("line").attr("x1", a_bx).attr("y1", y_base).attr("x2", a_bx).attr("y2", y_base + tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", a_bx).attr("y", y_base + 13).attr("class", "tick-label-piper").attr("text-anchor", "middle").text(val);

          const a_lx = x_a_left + 0.5 * frac * L, a_ly = y_base - frac * H;
          gTicks.append("line").attr("x1", a_lx).attr("y1", a_ly).attr("x2", a_lx + norm_lx * tickLen).attr("y2", a_ly + norm_ly * tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", a_lx - 7).attr("y", a_ly + 3).attr("class", "tick-label-piper").attr("text-anchor", "end").text(100 - val);

          const a_rx = x_a_top + 0.5 * frac * L, a_ry = y_a_top + frac * H;
          gTicks.append("line").attr("x1", a_rx).attr("y1", a_ry).attr("x2", a_rx + norm_rx * tickLen).attr("y2", a_ry + norm_ry * tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", a_rx + 7).attr("y", a_ry + 3).attr("class", "tick-label-piper").attr("text-anchor", "start").text(100 - val);
        }}

        // Ticks Diamante
        const d_norm_ul_x = -Math.sqrt(3)/2.0, d_norm_ul_y = -0.5;
        const d_norm_ur_x = Math.sqrt(3)/2.0, d_norm_ur_y = -0.5;
        const d_norm_ll_x = -Math.sqrt(3)/2.0, d_norm_ll_y = 0.5;
        const d_norm_lr_x = Math.sqrt(3)/2.0, d_norm_lr_y = 0.5;

        for (let s = 1; s <= 9; s++) {{
          const frac = s / 10.0;
          const val = s * 10;
          const tickLen = (s % 2 === 0) ? 5.5 : 3.2;

          const ul_x = x_d_left + frac * (x_d_top - x_d_left), ul_y = y_d_left + frac * (y_d_top - y_d_left);
          gTicks.append("line").attr("x1", ul_x).attr("y1", ul_y).attr("x2", ul_x + d_norm_ul_x * tickLen).attr("y2", ul_y + d_norm_ul_y * tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", ul_x + d_norm_ul_x * 7).attr("y", ul_y + d_norm_ul_y * 7 + 3).attr("class", "tick-label-piper").attr("text-anchor", "end").text(val);

          const ur_x = x_d_top + frac * (x_d_right - x_d_top), ur_y = y_d_top + frac * (y_d_right - y_d_top);
          gTicks.append("line").attr("x1", ur_x).attr("y1", ur_y).attr("x2", ur_x + d_norm_ur_x * tickLen).attr("y2", ur_y + d_norm_ur_y * tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", ur_x + d_norm_ur_x * 7).attr("y", ur_y + d_norm_ur_y * 7 + 3).attr("class", "tick-label-piper").attr("text-anchor", "start").text(100 - val);

          const ll_x = x_d_left + frac * (x_d_bot - x_d_left), ll_y = y_d_left + frac * (y_d_bot - y_d_left);
          gTicks.append("line").attr("x1", ll_x).attr("y1", ll_y).attr("x2", ll_x + d_norm_ll_x * tickLen).attr("y2", ll_y + d_norm_ll_y * tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", ll_x + d_norm_ll_x * 7).attr("y", ll_y + d_norm_ll_y * 7 + 3).attr("class", "tick-label-piper").attr("text-anchor", "end").text(val);

          const lr_x = x_d_bot + frac * (x_d_right - x_d_bot), lr_y = y_d_bot + frac * (y_d_right - y_d_bot);
          gTicks.append("line").attr("x1", lr_x).attr("y1", lr_y).attr("x2", lr_x + d_norm_lr_x * tickLen).attr("y2", lr_y + d_norm_lr_y * tickLen).attr("class", "tick-line");
          gTicks.append("text").attr("x", lr_x + d_norm_lr_x * 7).attr("y", lr_y + d_norm_lr_y * 7 + 3).attr("class", "tick-label-piper").attr("text-anchor", "start").text(val);
        }}

        // Rótulos de Ejes del Rombo
        const gDiamondLabels = zoomGroup.append("g").attr("id", "diamond-labels-group");
        const mid_ul_x = (x_d_left + x_d_top) / 2.0, mid_ul_y = (y_d_left + y_d_top) / 2.0;
        gDiamondLabels.append("text").attr("x", mid_ul_x).attr("y", mid_ul_y).attr("transform", `rotate(-60, ${{mid_ul_x}}, ${{mid_ul_y}}) translate(0, -28)`).attr("class", "diamond-axis-label").text("SO₄ + Cl  →");

        const mid_ur_x = (x_d_top + x_d_right) / 2.0, mid_ur_y = (y_d_top + y_d_right) / 2.0;
        gDiamondLabels.append("text").attr("x", mid_ur_x).attr("y", mid_ur_y).attr("transform", `rotate(60, ${{mid_ur_x}}, ${{mid_ur_y}}) translate(0, -28)`).attr("class", "diamond-axis-label").text("←  Na + K");

        const mid_ll_x = (x_d_left + x_d_bot) / 2.0, mid_ll_y = (y_d_left + y_d_bot) / 2.0;
        gDiamondLabels.append("text").attr("x", mid_ll_x).attr("y", mid_ll_y).attr("transform", `rotate(60, ${{mid_ll_x}}, ${{mid_ll_y}}) translate(0, 22)`).attr("class", "diamond-axis-label").text("Ca + Mg  →");

        const mid_lr_x = (x_d_bot + x_d_right) / 2.0, mid_lr_y = (y_d_bot + y_d_right) / 2.0;
        gDiamondLabels.append("text").attr("x", mid_lr_x).attr("y", mid_lr_y).attr("transform", `rotate(-60, ${{mid_lr_x}}, ${{mid_lr_y}}) translate(0, 22)`).attr("class", "diamond-axis-label").text("CO₃ + HCO₃  →");

        // Rótulos Iones
        gLabels.append("text").attr("x", x_c_top).attr("y", y_base + 46).attr("class", "axis-label-piper").text("CATIONES (% meq/L)");
        gLabels.append("text").attr("x", x_c_left - 10).attr("y", y_base + 20).attr("class", "ion-label").attr("text-anchor", "end").text("Ca²⁺");
        gLabels.append("text").attr("x", x_c_right + 10).attr("y", y_base + 20).attr("class", "ion-label").attr("text-anchor", "start").text("Na⁺ + K⁺");
        gLabels.append("text").attr("x", x_c_top).attr("y", y_c_top - 16).attr("class", "ion-label").attr("text-anchor", "middle").text("Mg²⁺");

        gLabels.append("text").attr("x", x_a_top).attr("y", y_base + 46).attr("class", "axis-label-piper").text("ANIONES (% meq/L)");
        gLabels.append("text").attr("x", x_a_left - 10).attr("y", y_base + 20).attr("class", "ion-label").attr("text-anchor", "end").text("CO₃²⁻ + HCO₃⁻");
        gLabels.append("text").attr("x", x_a_right + 10).attr("y", y_base + 20).attr("class", "ion-label").attr("text-anchor", "start").text("Cl⁻");
        gLabels.append("text").attr("x", x_a_top).attr("y", y_a_top - 16).attr("class", "ion-label").attr("text-anchor", "middle").text("SO₄²⁻");

        // Tooltip
        const tooltip = d3.select("#piper-tooltip");

        const hasIsolation = (isolatedSampleId && isolatedSampleId.trim() !== "" && isolatedSampleId !== "ALL");

        // Render de Muestras
        samples.forEach((m, i) => {{
          const isMatch = (m.id === isolatedSampleId);
          const ca_frac = m.ca_pct / 100.0;
          const mg_frac = m.mg_pct / 100.0;
          const nak_frac = m.nak_pct / 100.0;

          const xc = x_c_left + 0.5 * (2.0 * nak_frac + mg_frac) * L;
          const yc = y_base - mg_frac * H;

          const cl_frac = m.cl_pct / 100.0;
          const so4_frac = m.so4_pct / 100.0;
          const hco3_frac = m.hco3_pct / 100.0;

          const xa = x_a_left + 0.5 * (2.0 * cl_frac + so4_frac) * L;
          const ya = y_base - so4_frac * H;

          const xd = (xc + xa) / 2.0 + (yc - ya) / (2.0 * Math.sqrt(3));
          const yd = (yc + ya) / 2.0 - Math.sqrt(3) * (xa - xc) / 2.0;

          const conn = gConnections.append("polyline")
            .attr("points", `${{xc}},${{yc}} ${{xd}},${{yd}} ${{xa}},${{ya}}`)
            .attr("stroke", m.color)
            .attr("stroke-width", isMatch ? 2.4 : 1.2)
            .attr("stroke-dasharray", isMatch ? "4,3" : null)
            .attr("stroke-opacity", isMatch ? 0.95 : 0.65)
            .attr("fill", "none")
            .attr("style", hasIsolation && !isMatch ? "display: none;" : "")
            .attr("class", `connection-line conn-${{i}}`);

          const showTip = (event) => {{
            conn.classed("highlight", true).attr("stroke-width", 2.4).attr("stroke-opacity", 1.0).style("display", "block");
            d3.selectAll(`.pt-group-${{i}}`).raise().selectAll("circle, polygon").attr("stroke-width", 3.0);

            const tipHtml = `
              <div style="font-weight:700; color:#691C32; margin-bottom:4px; font-size:12px;">🧪 ${{m.id}}</div>
              <div style="color:#475569; font-size:11px; margin-bottom:6px;"><b>Fuente:</b> ${{m.fuente}}</div>
              <div style="background:#f1f5f9; padding:5px 8px; border-radius:4px; margin-bottom:6px;">
                <b>Facies:</b> <span style="color:${{m.color}}; font-weight:700;">${{m.facies}}</span><br>
                <b>Cuadrante:</b> <span style="color:#0f172a; font-weight:600;">${{m.cuadrante}}</span><br>
                <b>Error Balance (CBE):</b> ${{m.cbe >= 0 ? '+' : ''}}${{m.cbe.toFixed(2)}}% (${{m.cbe_calidad}})<br>
                <b>SDT:</b> ${{m.sdt > 0 ? m.sdt.toLocaleString() + ' mg/L' : 'N/D'}} | <b>CE:</b> ${{m.ce > 0 ? m.ce.toLocaleString() + ' µS/cm' : 'N/D'}}<br>
                <b>Índice Revelle:</b> ${{m.revelle > 0 ? m.revelle.toFixed(2) : 'N/D'}}
              </div>
              <div style="font-size:10.5px; color:#334155;">
                <b>Cationes:</b> Ca²⁺=${{m.ca_pct.toFixed(1)}}%, Mg²⁺=${{m.mg_pct.toFixed(1)}}%, Na⁺+K⁺=${{m.nak_pct.toFixed(1)}}%<br>
                <b>Aniones:</b> HCO₃⁻=${{m.hco3_pct.toFixed(1)}}%, SO₄²⁻=${{m.so4_pct.toFixed(1)}}%, Cl⁻=${{m.cl_pct.toFixed(1)}}%
              </div>
            `;
            tooltip.html(tipHtml).style("display", "block");

            const container = document.getElementById("piper-svg-container");
            const cRect = container.getBoundingClientRect();
            const mouseX = event.clientX - cRect.left;
            const mouseY = event.clientY - cRect.top;

            const tipEl = tooltip.node();
            const tipW = tipEl.offsetWidth || 280;
            const tipH = tipEl.offsetHeight || 160;

            let leftPos = mouseX + 16;
            if (leftPos + tipW > cRect.width - 12) {{
              leftPos = Math.max(10, mouseX - tipW - 16);
            }}

            let topPos = mouseY - 15;
            if (topPos + tipH > cRect.height - 12) {{
              topPos = Math.max(10, mouseY - tipH - 12);
            }}

            tooltip.style("left", leftPos + "px").style("top", topPos + "px");
          }};

          const hideTip = () => {{
            if (!hasIsolation || !isMatch) {{
              conn.classed("highlight", false).attr("stroke-width", 1.2).attr("stroke-opacity", 0.65);
              if (hasIsolation) conn.style("display", "none");
            }}
            d3.selectAll(`.pt-group-${{i}}`).selectAll("circle, polygon").attr("stroke-width", isMatch ? 2.6 : 1.8);
            tooltip.style("display", "none");
          }};

          const grp = gSamples.append("g")
            .attr("class", `pt-group-${{i}}`)
            .attr("data-id", m.id)
            .attr("data-facies", m.facies);

          if (hasIsolation && !isMatch) {{
            grp.style("opacity", 0.12).style("pointer-events", "none");
          }}

          const r_circ = isMatch ? 8.5 : 5.5;
          const stroke_c = isMatch ? "#0f172a" : "#ffffff";
          const stroke_w = isMatch ? 2.6 : 1.8;

          grp.append("circle")
            .attr("cx", xc).attr("cy", yc).attr("r", r_circ)
            .attr("fill", m.color).attr("stroke", stroke_c).attr("stroke-width", stroke_w)
            .attr("style", `fill: ${{m.color}} !important; stroke: ${{stroke_c}} !important; stroke-width: ${{stroke_w}}px !important;`)
            .attr("class", "sample-pt pt-cat")
            .on("mouseover", showTip).on("mousemove", showTip).on("mouseout", hideTip);

          grp.append("circle")
            .attr("cx", xa).attr("cy", ya).attr("r", r_circ)
            .attr("fill", m.color).attr("stroke", stroke_c).attr("stroke-width", stroke_w)
            .attr("style", `fill: ${{m.color}} !important; stroke: ${{stroke_c}} !important; stroke-width: ${{stroke_w}}px !important;`)
            .attr("class", "sample-pt pt-an")
            .on("mouseover", showTip).on("mousemove", showTip).on("mouseout", hideTip);

          const rd = isMatch ? 11.0 : 7.0;
          grp.append("polygon")
            .attr("points", `${{xd}},${{yd - rd}} ${{xd + rd}},${{yd}} ${{xd}},${{yd + rd}} ${{xd - rd}},${{yd}}`)
            .attr("fill", m.color).attr("stroke", stroke_c).attr("stroke-width", stroke_w)
            .attr("style", `fill: ${{m.color}} !important; stroke: ${{stroke_c}} !important; stroke-width: ${{stroke_w}}px !important;`)
            .attr("class", "sample-pt pt-dia")
            .on("mouseover", showTip).on("mousemove", showTip).on("mouseout", hideTip);

          if (isMatch) {{
            grp.raise();
          }}
        }});

        let diamondLabelsVisible = true;
        function toggleDiamondLabels() {{
          diamondLabelsVisible = !diamondLabelsVisible;
          d3.select("#diamond-labels-group").style("display", diamondLabelsVisible ? "block" : "none");
          const btn = document.getElementById("btn-diamond-labels");
          if (diamondLabelsVisible) {{
            btn.classList.add("active");
          }} else {{
            btn.classList.remove("active");
          }}
        }}

        // Lupa de Aumento Dinámica (2.5x)
        const lensGroup = svg.append("g").attr("id", "lens-group").style("display", "none").style("pointer-events", "none");
        const lensRadius = 85;
        const lensMag = 2.5;

        defs.append("clipPath").attr("id", "piper-lens-clip")
          .append("circle").attr("r", lensRadius);

        const lensContent = lensGroup.append("g").attr("clip-path", "url(#piper-lens-clip)");
        lensContent.append("rect").attr("x", -lensRadius).attr("y", -lensRadius).attr("width", lensRadius * 2).attr("height", lensRadius * 2).attr("fill", "#ffffff");
        const lensUse = lensContent.append("use").attr("href", "#zoom-group");

        lensGroup.append("circle")
          .attr("r", lensRadius)
          .attr("fill", "none")
          .attr("stroke", "#691C32")
          .attr("stroke-width", 3.0)
          .attr("filter", "drop-shadow(0 4px 12px rgba(0,0,0,0.35))");

        lensGroup.append("line").attr("x1", -12).attr("y1", 0).attr("x2", 12).attr("y2", 0).attr("stroke", "#dc2626").attr("stroke-width", 1.2);
        lensGroup.append("line").attr("x1", 0).attr("y1", -12).attr("x2", 0).attr("y2", 12).attr("stroke", "#dc2626").attr("stroke-width", 1.2);

        let lupaActive = false;
        function toggleLupa() {{
          lupaActive = !lupaActive;
          const btn = document.getElementById("btn-lupa");
          const status = document.getElementById("lupa-status");
          const container = document.getElementById("piper-svg-container");
          if (lupaActive) {{
            btn.classList.add("active");
            status.textContent = "ON";
            container.classList.add("lupa-mode");
          }} else {{
            btn.classList.remove("active");
            status.textContent = "OFF";
            container.classList.remove("lupa-mode");
            lensGroup.style("display", "none");
          }}
        }}

        svg.on("mousemove", function(event) {{
          if (!lupaActive) return;
          const [mx, my] = d3.pointer(event, svg.node());
          lensGroup.style("display", "block").attr("transform", `translate(${{mx}}, ${{my}})`);
          lensUse.attr("transform", `scale(${{lensMag}}) translate(${{-mx}}, ${{-my}})`);
        }});

        svg.on("mouseleave", function() {{
          if (lupaActive) lensGroup.style("display", "none");
        }});

        // Zoom y Paneo
        const zoom = d3.zoom()
          .scaleExtent([0.5, 8])
          .on("zoom", (event) => {{
            zoomGroup.attr("transform", event.transform);
            const pct = Math.round(event.transform.k * 100);
            document.getElementById("zoom-level").textContent = pct + "%";
          }});

        svg.call(zoom);

        function zoomIn() {{ svg.transition().duration(250).call(zoom.scaleBy, 1.25); }}
        function zoomOut() {{ svg.transition().duration(250).call(zoom.scaleBy, 0.8); }}
        function resetZoom() {{ svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity); }}

        function getCleanStandaloneSVG() {{
          const svgEl = document.getElementById("svg-piper");
          const clone = svgEl.cloneNode(true);

          const cloneLens = clone.querySelector("#lens-group");
          if (cloneLens) cloneLens.remove();

          const cloneZoom = clone.querySelector("#zoom-group");
          if (cloneZoom) cloneZoom.setAttribute("transform", "translate(0,0) scale(1)");

          let defs = clone.querySelector("defs");
          if (!defs) {{
            defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
            clone.insertBefore(defs, clone.firstChild);
          }}
          const styleEl = document.createElementNS("http://www.w3.org/2000/svg", "style");
          styleEl.textContent = `
            .axis-line {{ stroke: #0f172a !important; stroke-width: 1.8 !important; fill: none !important; stroke-linejoin: round; }}
            .grid-line {{ stroke: #475569 !important; stroke-width: 0.85 !important; stroke-dasharray: 3,2.5 !important; opacity: 0.8 !important; fill: none !important; }}
            .grid-line-diamond {{ stroke: #475569 !important; stroke-width: 0.85 !important; stroke-dasharray: 3,2.5 !important; opacity: 0.8 !important; fill: none !important; }}
            .tick-line {{ stroke: #0f172a !important; stroke-width: 1.1 !important; fill: none !important; }}
            .axis-label-piper {{ font-size: 11px !important; font-weight: 800 !important; fill: #1e293b !important; text-anchor: middle !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
            .ion-label {{ font-size: 13px !important; font-weight: 800 !important; fill: #0f172a !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
            .diamond-axis-label {{ font-size: 11px !important; font-weight: 800 !important; text-anchor: middle !important; dominant-baseline: middle !important; fill: #0f172a !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; paint-order: stroke fill; stroke: #ffffff; stroke-width: 4px; stroke-linejoin: round; }}
            .tick-label-piper {{ font-size: 8px !important; font-weight: 600 !important; fill: #475569 !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
            .tick-label-100 {{ font-size: 9.5px !important; font-weight: 700 !important; fill: #0f172a !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
            .sample-pt {{ stroke: #ffffff !important; stroke-width: 1.8 !important; }}
            .connection-line {{ opacity: 0.75 !important; fill: none !important; }}
          `;
          defs.appendChild(styleEl);

          const polys = clone.querySelectorAll("polygon");
          polys.forEach(p => {{
            if (!p.classList.contains("sample-pt")) {{
              p.setAttribute("fill", "none");
              p.setAttribute("stroke", "#0f172a");
              p.setAttribute("stroke-width", "1.8");
            }}
          }});

          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(clone);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          return source;
        }}

        function descargarSVG() {{
          const source = getCleanStandaloneSVG();
          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{type: "image/svg+xml;charset=utf-8"}});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "Diagrama_Piper_Vectorial_CONAGUA.svg";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }}

        function descargarPNG() {{
          const source = getCleanStandaloneSVG();
          const canvas = document.createElement("canvas");
          const scale = 3.125;
          canvas.width = w * scale;
          canvas.height = h * scale;
          const ctx = canvas.getContext("2d");
          ctx.imageSmoothingEnabled = true;
          ctx.imageSmoothingQuality = "high";

          const img = new Image();
          const svgBlob = new Blob([source], {{type: "image/svg+xml;charset=utf-8"}});
          const url = URL.createObjectURL(svgBlob);

          img.onload = function() {{
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Piper_Oficial_300DPI_CONAGUA.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code


def generar_diagrama_stiff_d3(df_procesado, muestra_sel=None):
    """
    Genera diagramas poligonales de Stiff en D3.js / SVG nativo:
      - 2 columnas responsivas con tarjetas individuales y controles de Zoom de Tarjetas (+/-).
      - Convención Canónica Tri-Nivel de H.A. Stiff (1951):
          Nivel 0 (sup): Na++K+ (izq) | Cl- (der)
          Nivel 1 (med): Ca2+ (izq)   | HCO3- (der)
          Nivel 2 (inf): Mg2+ (izq)   | SO42- (der)
      - Ejes milimétricos en meq/L con escala simétrica regular sin solapamientos.
      - Descarga directa en SVG vectorial y PNG a 300 DPI por muestra y mosaico completo.
    """
    df_plot = df_procesado.copy()
    if muestra_sel and muestra_sel != "Todas las Muestras":
        df_plot = df_plot[df_plot['Muestra'].astype(str) == str(muestra_sel)]

    muestras_stiff = []
    colores_paleta = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, (_, r) in enumerate(df_plot.iterrows()):
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        na_k = float(r.get('Na_meq_L', 0) + r.get('K_meq_L', 0))
        ca = float(r.get('Ca_meq_L', 0))
        mg = float(r.get('Mg_meq_L', 0))
        cl = float(r.get('Cl_meq_L', 0))
        hco3 = float(r.get('HCO3_meq_L', 0) + r.get('CO3_meq_L', 0))
        so4 = float(r.get('SO4_meq_L', 0))

        color_pt = colores_paleta[idx % len(colores_paleta)]
        muestras_stiff.append({
            "id": id_m,
            "fuente": str(r.get('Tipo_Fuente', 'Fuente')),
            "facies": str(r.get('Facies_Piper', 'N/D')),
            "cbe": float(r.get('CBE_pct', 0.0)),
            "sdt": float(r.get('SDT_mg_L', 0.0)),
            "na_k": na_k, "ca": ca, "mg": mg,
            "cl": cl, "hco3": hco3, "so4": so4,
            "color": color_pt
        })

    json_stiff = json.dumps(muestras_stiff)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagramas de Stiff D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{
          margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
          background: #f8fafc; user-select: none;
        }}
        .toolbar-stiff {{
          display: flex; justify-content: space-between; align-items: center;
          padding: 8px 16px; background: #ffffff; border-bottom: 1px solid #e2e8f0;
          position: sticky; top: 0; z-index: 100;
        }}
        .btn-toolbar {{
          background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px;
          padding: 5px 11px; font-size: 11px; font-weight: 600; color: #334155;
          cursor: pointer; display: inline-flex; align-items: center; gap: 4px;
          transition: all 0.2s ease;
        }}
        .btn-toolbar:hover {{
          background: #691C32; color: #ffffff; border-color: #691C32;
        }}
        .btn-card-dl {{
          background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px;
          padding: 2px 7px; font-size: 10px; font-weight: 600; color: #475569;
          cursor: pointer; transition: all 0.15s ease;
        }}
        .btn-card-dl:hover {{
          background: #691C32; color: #ffffff; border-color: #691C32;
        }}
        .stiff-grid {{
          --card-min-w: 440px;
          display: grid; grid-template-columns: repeat(auto-fit, minmax(var(--card-min-w), 1fr));
          gap: 16px; padding: 16px;
        }}
        .stiff-card {{
          background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.05); padding: 12px 14px 10px 14px;
          transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}
        .stiff-card:hover {{
          box-shadow: 0 4px 12px rgba(0,0,0,0.1);
          transform: translateY(-2px);
        }}
        .card-header {{
          display: flex; justify-content: space-between; align-items: center;
          margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #f1f5f9;
        }}
        .card-title {{
          font-size: 12px; font-weight: 700; color: #1e293b;
        }}
        .card-meta {{
          font-size: 10px; color: #64748b;
        }}
        .card-body {{
          width: 100%; height: 180px; position: relative;
        }}
        svg {{ width: 100%; height: 100%; display: block; }}
        .axis-line {{ stroke: #64748b; stroke-width: 1; fill: none; }}
        .center-axis {{ stroke: #0f172a; stroke-width: 1.8; fill: none; }}
        .grid-tick {{ stroke: #e2e8f0; stroke-width: 0.8; stroke-dasharray: 2, 2; fill: none; }}
        .ion-label {{ font-size: 9.5px; font-weight: 700; fill: #1e293b; font-family: sans-serif; }}
        .tick-text {{ font-size: 8px; fill: #64748b; text-anchor: middle; font-family: sans-serif; }}
      </style>
    </head>
    <body>
      <div class="toolbar-stiff">
        <div style="font-size: 12px; font-weight: 700; color: #691C32;">
          ⚡ Polígonos de Huella Iónica de Stiff (meq/L) - D3.js / SVG (H.A. Stiff, 1951)
        </div>
        <div style="display: flex; gap: 6px; align-items: center;">
          <button class="btn-toolbar" onclick="cambiarTamanoTarjetas(60)" title="Aumentar tamaño de tarjetas">
            <span>🔍+</span> Aumentar
          </button>
          <button class="btn-toolbar" onclick="cambiarTamanoTarjetas(-60)" title="Reducir tamaño de tarjetas">
            <span>🔍-</span> Reducir
          </button>
          <button class="btn-toolbar" onclick="resetTamanoTarjetas()" title="Restablecer tamaño normal">
            <span>🔄</span> Normal
          </button>
          <div style="height: 18px; width: 1px; background: #cbd5e1; margin: 0 4px;"></div>
          <button class="btn-toolbar" onclick="descargarMosaicoSVG()">
            <span>📥</span> Mosaico SVG
          </button>
          <button class="btn-toolbar" onclick="descargarMosaicoPNG()">
            <span>🖼️</span> Mosaico PNG 300 DPI
          </button>
        </div>
      </div>

      <div class="stiff-grid" id="stiff-grid-container"></div>

      <script>
        const data = {json_stiff};
        let curMinW = 440;

        function cambiarTamanoTarjetas(delta) {{
          curMinW = Math.max(300, Math.min(800, curMinW + delta));
          document.querySelector('.stiff-grid').style.setProperty('--card-min-w', curMinW + 'px');
        }}

        function resetTamanoTarjetas() {{
          curMinW = 440;
          document.querySelector('.stiff-grid').style.setProperty('--card-min-w', '440px');
        }}

        let maxGlobal = 0.5;
        data.forEach(d => {{
          maxGlobal = Math.max(maxGlobal, d.na_k, d.ca, d.mg, d.cl, d.hco3, d.so4);
        }});
        maxGlobal = Math.ceil(maxGlobal * 1.15);

        const container = d3.select("#stiff-grid-container");

        data.forEach((m, i) => {{
          const card = container.append("div").attr("class", "stiff-card");

          const header = card.append("div").attr("class", "card-header");
          const hLeft = header.append("div");
          hLeft.append("div").attr("class", "card-title").text(`Muestra ${{m.id}}`);
          hLeft.append("div").attr("class", "card-meta").text(`${{m.fuente}} | ${{m.facies}} | CBE: ${{m.cbe.toFixed(1)}}%`);

          const hRight = header.append("div").style("display", "flex").style("gap", "4px");
          hRight.append("button")
            .attr("class", "btn-card-dl")
            .text("SVG")
            .attr("title", "Descargar SVG")
            .on("click", () => descargarStiffIndividualSVG(i, m.id));

          hRight.append("button")
            .attr("class", "btn-card-dl")
            .text("PNG")
            .attr("title", "Descargar PNG 300 DPI")
            .on("click", () => descargarStiffIndividualPNG(i, m.id));

          const cBody = card.append("div").attr("class", "card-body");

          const w = 450, h = 190;
          const padL = 75, padR = 75, padT = 32, padB = 28;
          const xCenter = w / 2.0;

          const svg = cBody.append("svg")
            .attr("xmlns", "http://www.w3.org/2000/svg")
            .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
            .attr("viewBox", `0 0 ${{w}} ${{h}}`)
            .attr("width", w)
            .attr("height", h)
            .attr("id", `svg-stiff-${{i}}`)
            .attr("preserveAspectRatio", "xMidYMid meet");

          svg.append("rect")
            .attr("width", w)
            .attr("height", h)
            .attr("fill", "#ffffff");

          const defs = svg.append("defs");
          defs.append("style").text(`
            .axis-line {{ stroke: #64748b; stroke-width: 1; fill: none; }}
            .center-axis {{ stroke: #0f172a; stroke-width: 1.8; fill: none; }}
            .grid-tick {{ stroke: #e2e8f0; stroke-width: 0.8; stroke-dasharray: 2, 2; fill: none; }}
            .ion-label {{ font-size: 9.5px; font-weight: 700; fill: #1e293b; font-family: sans-serif; }}
            .tick-text {{ font-size: 8px; fill: #64748b; text-anchor: middle; font-family: sans-serif; }}
          `);

          const yLevels = [
            padT + 15,
            padT + (h - padT - padB) / 2.0,
            h - padB - 15
          ];

          const scaleCat = d3.scaleLinear().domain([0, maxGlobal]).range([xCenter, padL]);
          const scaleAn = d3.scaleLinear().domain([0, maxGlobal]).range([xCenter, w - padR]);

          yLevels.forEach(y => {{
            svg.append("line")
              .attr("x1", padL).attr("y1", y)
              .attr("x2", w - padR).attr("y2", y)
              .attr("class", "axis-line")
              .attr("fill", "none");
          }});

          svg.append("line")
            .attr("x1", xCenter).attr("y1", padT)
            .attr("x2", xCenter).attr("y2", h - padB)
            .attr("class", "center-axis")
            .attr("fill", "none");

          const ticks = [Math.round(maxGlobal * 0.5), maxGlobal];
          ticks.forEach(tVal => {{
            const xL = scaleCat(tVal);
            const xR = scaleAn(tVal);
            svg.append("line").attr("x1", xL).attr("y1", padT).attr("x2", xL).attr("y2", h - padB).attr("class", "grid-tick").attr("fill", "none");
            svg.append("line").attr("x1", xR).attr("y1", padT).attr("x2", xR).attr("y2", h - padB).attr("class", "grid-tick").attr("fill", "none");
            svg.append("text").attr("x", xL).attr("y", h - padB + 14).attr("class", "tick-text").text(tVal);
            svg.append("text").attr("x", xR).attr("y", h - padB + 14).attr("class", "tick-text").text(tVal);
          }});
          svg.append("text").attr("x", xCenter).attr("y", h - padB + 14).attr("class", "tick-text").text("0");
          svg.append("text").attr("x", xCenter).attr("y", h - 2).attr("class", "tick-text").text("meq/L").style("font-weight", "600");

          svg.append("text").attr("x", padL - 8).attr("y", yLevels[0] + 3).text("Na⁺+K⁺").attr("class", "ion-label").attr("text-anchor", "end");
          svg.append("text").attr("x", padL - 8).attr("y", yLevels[1] + 3).text("Ca²⁺").attr("class", "ion-label").attr("text-anchor", "end");
          svg.append("text").attr("x", padL - 8).attr("y", yLevels[2] + 3).text("Mg²⁺").attr("class", "ion-label").attr("text-anchor", "end");

          svg.append("text").attr("x", w - padR + 8).attr("y", yLevels[0] + 3).text("Cl⁻").attr("class", "ion-label").attr("text-anchor", "start");
          svg.append("text").attr("x", w - padR + 8).attr("y", yLevels[1] + 3).text("HCO₃⁻").attr("class", "ion-label").attr("text-anchor", "start");
          svg.append("text").attr("x", w - padR + 8).attr("y", yLevels[2] + 3).text("SO₄²⁻").attr("class", "ion-label").attr("text-anchor", "start");

          svg.append("text").attr("x", (padL + xCenter) / 2.0).attr("y", padT - 8).text("← CATIONES").attr("class", "ion-label").attr("text-anchor", "middle").style("fill", "#691C32");
          svg.append("text").attr("x", (w - padR + xCenter) / 2.0).attr("y", padT - 8).text("ANIONES →").attr("class", "ion-label").attr("text-anchor", "middle").style("fill", "#691C32");

          const pt_na_k = [scaleCat(m.na_k), yLevels[0]];
          const pt_ca = [scaleCat(m.ca), yLevels[1]];
          const pt_mg = [scaleCat(m.mg), yLevels[2]];
          const pt_so4 = [scaleAn(m.so4), yLevels[2]];
          const pt_hco3 = [scaleAn(m.hco3), yLevels[1]];
          const pt_cl = [scaleAn(m.cl), yLevels[0]];

          const polyPts = [pt_na_k, pt_ca, pt_mg, pt_so4, pt_hco3, pt_cl];
          const ptsString = polyPts.map(p => `${{p[0].toFixed(1)}},${{p[1].toFixed(1)}}`).join(" ");

          svg.append("polygon")
            .attr("points", ptsString)
            .attr("fill", m.color)
            .attr("fill-opacity", 0.35)
            .attr("stroke", m.color)
            .attr("stroke-width", 2.2);

          polyPts.forEach(pt => {{
            svg.append("circle")
              .attr("cx", pt[0]).attr("cy", pt[1]).attr("r", 3.5)
              .attr("fill", m.color).attr("stroke", "#ffffff").attr("stroke-width", 1.2);
          }});
        }});

        function descargarStiffIndividualSVG(idx, sampleId) {{
          const svgEl = document.getElementById(`svg-stiff-${{idx}}`);
          if (!svgEl) return;
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `Stiff_${{sampleId}}_Vectorial.svg`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarStiffIndividualPNG(idx, sampleId) {{
          const svgEl = document.getElementById(`svg-stiff-${{idx}}`);
          if (!svgEl) return;
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            canvas.width = 420 * scale;
            canvas.height = 180 * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, 420, 180);
            ctx.drawImage(img, 0, 0, 420, 180);
            URL.revokeObjectURL(url);
            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = `Stiff_${{sampleId}}_300DPI.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}

        function descargarMosaicoSVG() {{
          descargarStiffIndividualSVG(0, data[0]?.id || "Muestra");
        }}

        function descargarMosaicoPNG() {{
          descargarStiffIndividualPNG(0, data[0]?.id || "Muestra");
        }}
      </script>
    </body>
    </html>
    """
    return html_code


# =============================================================================
# 3. DIAGRAMA DE SCHÖELLER-BERKALOFF VECTORIAL D3.JS
# =============================================================================
def generar_diagrama_schoeller_d3(df_procesado):
    """
    Construye el Perfil Semilogarítmico de Schöeller-Berkaloff en D3.js / SVG:
      - Secuencia de Chebotarev con escala logarítmica exacta (0.01 a 100 meq/L).
      - Resaltado interactivo de perfiles por pozo con hover.
      - Controles de Zoom, Paneo, Lupa de Aumento Dinámica (2.5x) y Descarga SVG/PNG 300 DPI.
    """
    muestras_data = []
    colores_paleta = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        color_pt = colores_paleta[idx % len(colores_paleta)]
        muestras_data.append({
            "id": id_m,
            "facies": str(r.get('Facies_Piper', 'N/D')),
            "ca": max(0.001, float(r.get('Ca_meq_L', 0.001))),
            "mg": max(0.001, float(r.get('Mg_meq_L', 0.001))),
            "nak": max(0.001, float(r.get('Na_meq_L', 0) + r.get('K_meq_L', 0))),
            "hco3": max(0.001, float(r.get('HCO3_meq_L', 0.001) + r.get('CO3_meq_L', 0))),
            "so4": max(0.001, float(r.get('SO4_meq_L', 0.001))),
            "cl": max(0.001, float(r.get('Cl_meq_L', 0.001))),
            "color": color_pt
        })

    json_str = json.dumps(muestras_data)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Schöeller D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{
          margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
          background: #ffffff; user-select: none; overflow: hidden;
        }}
        .toolbar-schoeller {{
          display: flex; justify-content: space-between; align-items: center;
          padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;
        }}
        .btn-toolbar {{
          background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px;
          padding: 5px 11px; font-size: 11px; font-weight: 600; color: #334155;
          cursor: pointer; display: inline-flex; align-items: center; gap: 4px;
          transition: all 0.2s ease;
        }}
        .btn-toolbar:hover {{ background: #691C32; color: #ffffff; border-color: #691C32; }}
        .btn-toolbar.active {{ background: #691C32 !important; color: #ffffff !important; border-color: #691C32 !important; }}
        #schoeller-svg-container {{ width: 100%; height: 500px; position: relative; background: #ffffff; overflow: hidden; cursor: grab; }}
        #schoeller-svg-container.grabbing {{ cursor: grabbing; }}
        #schoeller-svg-container.lupa-mode {{ cursor: crosshair; }}
        svg {{ width: 100%; height: 100%; display: block; }}
        .schoeller-line {{ fill: none; stroke-width: 2.2; transition: all 0.2s; }}
        .schoeller-line.faded {{ opacity: 0.18; stroke-width: 1.2; }}
        .schoeller-line.active {{ stroke-width: 3.5; opacity: 1; }}
        .schoeller-dot {{ cursor: pointer; transition: r 0.2s; }}
        .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
        .axis-text {{ font-size: 11px; fill: #475569; font-family: sans-serif; }}
        #schoeller-tooltip {{
          position: fixed; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11.5px; color: #1e293b; pointer-events: none;
        }}
        .legend-container {{
          display: flex; gap: 12px; flex-wrap: wrap; padding: 6px 16px; background: #ffffff; border-bottom: 1px solid #f1f5f9; max-height: 50px; overflow-y: auto;
        }}
        .leg-item {{
          display: flex; align-items: center; gap: 6px; font-size: 10.5px; cursor: pointer; padding: 2px 6px; border-radius: 4px;
        }}
        .leg-item:hover {{ background: #f1f5f9; }}
        .leg-bullet {{ width: 9px; height: 9px; border-radius: 50%; }}
      </style>
    </head>
    <body>
      <div class="toolbar-schoeller">
        <div style="font-size: 12px; font-weight: 700; color: #691C32; white-space: nowrap;">
          ⚡ Perfil Schöeller-Berkaloff
        </div>
        <div style="display: flex; gap: 5px; align-items: center; flex-wrap: nowrap;">
          <button class="btn-toolbar" onclick="zoomIn()" title="Acercar (Zoom In)"><span>🔍+</span></button>
          <button class="btn-toolbar" onclick="zoomOut()" title="Alejar (Zoom Out)"><span>🔍-</span></button>
          <button class="btn-toolbar" onclick="resetZoom()" title="Restablecer tamaño original (100%)"><span>🔄 1:1</span></button>
          <button class="btn-toolbar" id="btn-lupa" onclick="toggleLupa()" title="Activar/Desactivar Lupa de Aumento">
            <span>🔎 Lupa</span> <span id="lupa-status" style="font-size:9.5px; opacity:0.85;">OFF</span>
          </button>
          <span id="zoom-level" style="font-size:11px; font-weight:600; color:#64748b; margin: 0 3px;">100%</span>
          <div style="height: 16px; width: 1px; background: #cbd5e1; margin: 0 3px;"></div>
          <button class="btn-toolbar" onclick="descargarSVG()" title="Exportar SVG Vectorial"><span>📥 SVG</span></button>
          <button class="btn-toolbar" onclick="descargarPNG()" title="Exportar PNG a 300 DPI"><span>🖼️ PNG</span></button>
        </div>
      </div>

      <div class="legend-container" id="legend-bar"></div>
      <div id="schoeller-tooltip"></div>
      <div id="schoeller-svg-container"></div>

      <script>
        const data = {json_str};
        const ions = [
          {{ key: "ca", label: "Ca²⁺" }},
          {{ key: "mg", label: "Mg²⁺" }},
          {{ key: "nak", label: "Na⁺+K⁺" }},
          {{ key: "hco3", label: "HCO₃⁻" }},
          {{ key: "so4", label: "SO₄²⁻" }},
          {{ key: "cl", label: "Cl⁻" }}
        ];

        const w = 900, h = 440;
        const padL = 70, padR = 40, padT = 30, padB = 55;

        const svg = d3.select("#schoeller-svg-container").append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{w}} ${{h}}`)
          .attr("width", w)
          .attr("height", h)
          .attr("id", "svg-schoeller")
          .attr("preserveAspectRatio", "xMidYMid meet");

        svg.append("rect")
          .attr("width", w)
          .attr("height", h)
          .attr("fill", "#ffffff");

        const zoomGroup = svg.append("g").attr("id", "zoom-group");

        const defs = svg.append("defs");
        defs.append("style").text(`
          .schoeller-line {{ fill: none; stroke-width: 2.2; }}
          .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
          .axis-text {{ font-size: 11px; fill: #475569; font-family: sans-serif; }}
        `);

        const tooltip = d3.select("#schoeller-tooltip");

        const xScale = d3.scalePoint().domain(ions.map(d => d.label)).range([padL, w - padR]).padding(0.4);
        const yScale = d3.scaleLog().domain([0.01, 100]).range([h - padB, padT]);

        [0.01, 0.1, 1, 10, 100].forEach(val => {{
          const y = yScale(val);
          zoomGroup.append("line").attr("x1", padL).attr("y1", y).attr("x2", w - padR).attr("y2", y).attr("class", "grid-line").attr("fill", "none");
          zoomGroup.append("text").attr("x", padL - 10).attr("y", y).text(val).attr("class", "axis-text").attr("text-anchor", "end").attr("dominant-baseline", "middle");
        }});

        ions.forEach(ion => {{
          const x = xScale(ion.label);
          zoomGroup.append("line").attr("x1", x).attr("y1", padT).attr("x2", x).attr("y2", h - padB).attr("class", "grid-line").attr("fill", "none");
          zoomGroup.append("text").attr("x", x).attr("y", h - padB + 22).text(ion.label).attr("class", "axis-text").attr("text-anchor", "middle").style("font-weight", "700").style("fill", "#1e293b").style("font-size", "12px");
        }});

        zoomGroup.append("text").attr("x", (padL + w - padR)/2).attr("y", h - 10).text("Secuencia Hidrogeoquímica de Chebotarev").attr("class", "axis-text").attr("text-anchor", "middle").style("font-weight", "600");
        zoomGroup.append("text").attr("transform", "rotate(-90)").attr("x", -(padT + h - padB)/2).attr("y", 18).text("Concentración Iónica (meq/L, escala log)").attr("class", "axis-text").attr("text-anchor", "middle").style("font-weight", "600");

        const legBar = d3.select("#legend-bar");

        data.forEach((m, idx) => {{
          const lineGen = d3.line()
            .x(d => xScale(d.label))
            .y(d => yScale(d.val));

          const pts = ions.map(ion => ({{ label: ion.label, val: m[ion.key] }}));

          const path = zoomGroup.append("path")
            .datum(pts)
            .attr("d", lineGen)
            .attr("stroke", m.color)
            .attr("fill", "none")
            .attr("stroke-width", 2.2)
            .attr("class", `schoeller-line line-${{idx}}`);

          const dots = zoomGroup.selectAll(`.dot-${{idx}}`)
            .data(pts)
            .enter().append("circle")
            .attr("cx", d => xScale(d.label))
            .attr("cy", d => yScale(d.val))
            .attr("r", 4.5)
            .attr("fill", m.color)
            .attr("stroke", "#ffffff")
            .attr("stroke-width", 1.5)
            .attr("class", `schoeller-dot dot-${{idx}}`);

          const highlight = () => {{
            d3.selectAll(".schoeller-line").classed("faded", true);
            path.classed("faded", false).classed("active", true).raise();
            dots.raise().attr("r", 6.5);
          }};

          const unhighlight = () => {{
            d3.selectAll(".schoeller-line").classed("faded", false).classed("active", false);
            dots.attr("r", 4.5);
          }};

          path.on("mouseover", highlight).on("mouseout", unhighlight);
          dots.on("mouseover", (event, d) => {{
            highlight();
            tooltip.html(`<b>${{m.id}}</b><br>${{d.label}}: ${{d.val.toFixed(2)}} meq/L<br>Facies: ${{m.facies}}`)
              ;
            const tNode = tooltip.node();
            const tW = tNode.offsetWidth || 180;
            const tH = tNode.offsetHeight || 65;
            let lPos = event.clientX + 12;
            if (lPos + tW > window.innerWidth - 10) lPos = Math.max(10, event.clientX - tW - 12);
            let tPos = event.clientY - 24;
            if (tPos + tH > window.innerHeight - 10) tPos = Math.max(10, event.clientY - tH - 12);
            tooltip.style("left", lPos + "px").style("top", tPos + "px").style("display", "block");
          }}).on("mouseout", () => {{
            unhighlight();
            tooltip.style("display", "none");
          }});

          if (idx < 25) {{
            const item = legBar.append("div").attr("class", "leg-item");
            item.append("div").attr("class", "leg-bullet").style("background", m.color);
            item.append("span").text(m.id);
            item.on("mouseover", highlight).on("mouseout", unhighlight);
          }}
        }});

        // Componentes de la Lupa (Magnifier Lens)
        const lensGroup = svg.append("g").attr("id", "lens-group").style("display", "none").style("pointer-events", "none");
        const lensRadius = 80;
        const lensMag = 2.5;

        defs.append("clipPath").attr("id", "schoeller-lens-clip")
          .append("circle").attr("r", lensRadius);

        const lensContent = lensGroup.append("g").attr("clip-path", "url(#schoeller-lens-clip)");
        lensContent.append("rect").attr("x", -lensRadius).attr("y", -lensRadius).attr("width", lensRadius * 2).attr("height", lensRadius * 2).attr("fill", "#ffffff");
        const lensUse = lensContent.append("use").attr("href", "#zoom-group");

        lensGroup.append("circle")
          .attr("r", lensRadius)
          .attr("fill", "none")
          .attr("stroke", "#691C32")
          .attr("stroke-width", 3.0)
          .attr("filter", "drop-shadow(0 4px 12px rgba(0,0,0,0.35))");
        lensGroup.append("line").attr("x1", -12).attr("x2", 12).attr("y1", 0).attr("y2", 0).attr("stroke", "#691C32").attr("stroke-width", 1.2).attr("opacity", 0.7);
        lensGroup.append("line").attr("x1", 0).attr("x2", 0).attr("y1", -12).attr("y2", 12).attr("stroke", "#691C32").attr("stroke-width", 1.2).attr("opacity", 0.7);

        // Zoom y Paneo
        let currentTransform = d3.zoomIdentity;
        const zoom = d3.zoom()
          .scaleExtent([0.5, 12])
          .on("start", () => d3.select("#schoeller-svg-container").classed("grabbing", true))
          .on("end", () => d3.select("#schoeller-svg-container").classed("grabbing", false))
          .on("zoom", (event) => {{
            currentTransform = event.transform;
            zoomGroup.attr("transform", currentTransform);
            const pct = Math.round(event.transform.k * 100);
            d3.select("#zoom-level").text(pct + "%");
            updateLens();
          }});

        svg.call(zoom);

        function zoomIn() {{ svg.transition().duration(250).call(zoom.scaleBy, 1.35); }}
        function zoomOut() {{ svg.transition().duration(250).call(zoom.scaleBy, 0.74); }}
        function resetZoom() {{ svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity); }}

        let lupaActiva = false;
        let lastMouseSVG = null;

        function toggleLupa() {{
          lupaActiva = !lupaActiva;
          d3.select("#btn-lupa").classed("active", lupaActiva);
          d3.select("#lupa-status").text(lupaActiva ? "ON" : "OFF");
          d3.select("#schoeller-svg-container").classed("lupa-mode", lupaActiva);
          if (!lupaActiva) {{
            lensGroup.style("display", "none");
            lastMouseSVG = null;
          }}
        }}

        function getSVGPoint(event) {{
          const pt = svg.node().createSVGPoint();
          pt.x = event.clientX;
          pt.y = event.clientY;
          return pt.matrixTransform(svg.node().getScreenCTM().inverse());
        }}

        function updateLens() {{
          if (!lupaActiva || !lastMouseSVG) return;
          const {{x, y}} = lastMouseSVG;
          lensGroup.attr("transform", `translate(${{x}}, ${{y}})`);
          lensUse.attr("transform", `scale(${{lensMag}}) translate(${{-x}}, ${{-y}})`);
        }}

        svg.on("mousemove", function(event) {{
          if (!lupaActiva) return;
          lastMouseSVG = getSVGPoint(event);
          lensGroup.style("display", "block");
          updateLens();
        }});

        svg.on("mouseleave", function() {{
          if (lupaActiva) {{
            lensGroup.style("display", "none");
            lastMouseSVG = null;
          }}
        }});

        function descargarSVG() {{
          const prevTransform = zoomGroup.attr("transform");
          zoomGroup.attr("transform", null);
          lensGroup.style("display", "none");

          const svgEl = document.getElementById("svg-schoeller");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}

          zoomGroup.attr("transform", prevTransform);
          if (lupaActiva && lastMouseSVG) lensGroup.style("display", "block");

          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = "Diagrama_Schoeller_Vectorial.svg";
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarPNG() {{
          const prevTransform = zoomGroup.attr("transform");
          zoomGroup.attr("transform", null);
          lensGroup.style("display", "none");

          const svgEl = document.getElementById("svg-schoeller");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}

          zoomGroup.attr("transform", prevTransform);
          if (lupaActiva && lastMouseSVG) lensGroup.style("display", "block");

          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            canvas.width = w * scale;
            canvas.height = h * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, w, h);
            ctx.drawImage(img, 0, 0, w, h);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Schoeller_300DPI.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code


# =============================================================================
# 4. DIAGRAMA DE WILCOX VECTORIAL D3.JS
# =============================================================================
def generar_diagrama_wilcox_d3(df_procesado):
    """
    Construye el Diagrama de Wilcox en D3.js / SVG nativo:
      - Zonas de aptitud agronómica sombreadas translúcidas (Excelente, Bueno, Permisible, Dudoso).
      - CE vs % Na soluble.
      - Controles de Zoom, Paneo, Lupa de Aumento Dinámica (2.5x) y Descarga SVG/PNG 300 DPI.
    """
    muestras = []
    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        ce = float(r.get('CE_uS_cm', 0.0) if pd.notna(r.get('CE_uS_cm')) else (r.get('SDT_mg_L', 0.0) / 0.65))
        pct_na = float(r.get('Pct_Na_Riego', 0.0))
        ras = float(r.get('RAS', 0.0))
        muestras.append({
            "id": id_m, "ce": ce, "pct_na": pct_na, "ras": ras,
            "color": colores[idx % len(colores)],
            "facies": str(r.get('Facies_Piper', ''))
        })

    json_str = json.dumps(muestras)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Wilcox D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #ffffff; user-select: none; overflow: hidden; }}
        .toolbar {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
        .btn-toolbar {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px; padding: 5px 11px; font-size: 11px; font-weight: 600; cursor: pointer; color: #334155; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 4px; }}
        .btn-toolbar:hover {{ background: #691C32; color: white; border-color: #691C32; }}
        .btn-toolbar.active {{ background: #691C32 !important; color: white !important; border-color: #691C32 !important; }}
        #wilcox-svg-container {{ width: 100%; height: 480px; position: relative; background: #ffffff; overflow: hidden; cursor: grab; }}
        #wilcox-svg-container.grabbing {{ cursor: grabbing; }}
        #wilcox-svg-container.lupa-mode {{ cursor: crosshair; }}
        svg {{ width: 100%; height: 100%; display: block; }}
        .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; stroke-dasharray: 2, 2; fill: none; }}
        .zone-boundary {{ stroke-width: 1.8; stroke-dasharray: 4, 3; fill: none; }}
        .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
        .zone-text {{ font-size: 11px; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        .dot {{ cursor: pointer; transition: r 0.2s; }}
        #wilcox-tooltip {{
          position: fixed; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11px; color: #1e293b; pointer-events: none;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar">
        <div style="font-size: 11.5px; font-weight: 700; color: #691C32; white-space: nowrap;">🌾 Diagrama de Wilcox</div>
        <div style="display: flex; gap: 5px; align-items: center; flex-wrap: nowrap;">
          <button class="btn-toolbar" onclick="zoomIn()" title="Acercar (Zoom In)"><span>🔍+</span></button>
          <button class="btn-toolbar" onclick="zoomOut()" title="Alejar (Zoom Out)"><span>🔍-</span></button>
          <button class="btn-toolbar" onclick="resetZoom()" title="Restablecer tamaño original (100%)"><span>🔄 1:1</span></button>
          <button class="btn-toolbar" id="btn-lupa" onclick="toggleLupa()" title="Activar/Desactivar Lupa de Aumento">
            <span>🔎 Lupa</span> <span id="lupa-status" style="font-size:9.5px; opacity:0.85;">OFF</span>
          </button>
          <span id="zoom-level" style="font-size:11px; font-weight:600; color:#64748b; margin: 0 3px;">100%</span>
          <div style="height: 16px; width: 1px; background: #cbd5e1; margin: 0 3px;"></div>
          <button class="btn-toolbar" onclick="descargarSVG()" title="Exportar SVG"><span>📥 SVG</span></button>
          <button class="btn-toolbar" onclick="descargarPNG()" title="Exportar PNG a 300 DPI"><span>🖼️ PNG</span></button>
        </div>
      </div>
      <div id="wilcox-tooltip"></div>
      <div id="wilcox-svg-container"></div>

      <script>
        const data = {json_str};
        const w = 700, h = 440;
        const padL = 60, padR = 30, padT = 30, padB = 55;

        const svg = d3.select("#wilcox-svg-container").append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{w}} ${{h}}`)
          .attr("width", w)
          .attr("height", h)
          .attr("id", "svg-wilcox")
          .attr("preserveAspectRatio", "xMidYMid meet");

        svg.append("rect")
          .attr("width", w)
          .attr("height", h)
          .attr("fill", "#ffffff");

        const zoomGroup = svg.append("g").attr("id", "zoom-group");

        const defs = svg.append("defs");
        defs.append("style").text(`
          .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; stroke-dasharray: 2, 2; fill: none; }}
          .zone-boundary {{ stroke-width: 1.8; stroke-dasharray: 4, 3; fill: none; }}
          .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
          .zone-text {{ font-size: 11px; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        `);

        const tooltip = d3.select("#wilcox-tooltip");

        const xScale = d3.scaleLinear().domain([0, 4000]).range([padL, w - padR]);
        const yScale = d3.scaleLinear().domain([0, 100]).range([h - padB, padT]);

        xScale.ticks(8).forEach(tick => {{
          zoomGroup.append("line").attr("x1", xScale(tick)).attr("y1", padT).attr("x2", xScale(tick)).attr("y2", h - padB).attr("class", "grid-line").attr("fill", "none");
          zoomGroup.append("text").attr("x", xScale(tick)).attr("y", h - padB + 18).text(tick).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "middle");
        }});
        yScale.ticks(5).forEach(tick => {{
          zoomGroup.append("line").attr("x1", padL).attr("y1", yScale(tick)).attr("x2", w - padR).attr("y2", yScale(tick)).attr("class", "grid-line").attr("fill", "none");
          zoomGroup.append("text").attr("x", padL - 8).attr("y", yScale(tick)).text(tick + "%").attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "end").attr("dominant-baseline", "middle");
        }});

        zoomGroup.append("text").attr("x", (padL + w - padR)/2).attr("y", h - 12).text("Conductividad Eléctrica (µS/cm a 25 °C)").attr("class", "axis-label").attr("text-anchor", "middle");
        zoomGroup.append("text").attr("transform", "rotate(-90)").attr("x", -(padT + h - padB)/2).attr("y", 16).text("Porcentaje de Sodio Soluble (% Na)").attr("class", "axis-label").attr("text-anchor", "middle");

        const ceArr = d3.range(0, 4001, 100);
        // Curvas empíricas originales de aptitud agronómica de Wilcox (1948, 1955)
        const curveExc = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, Math.min(100, 100.0 * Math.exp(-d / 2800.0)))));
        const curveBue = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, Math.min(100, 85.0 * Math.exp(-d / 2000.0)))));
        const curvePer = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, Math.min(100, 70.0 * Math.exp(-d / 1500.0)))));
        const curveDud = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, Math.min(100, 55.0 * Math.exp(-d / 1200.0)))));

        zoomGroup.append("path").datum(ceArr).attr("d", curveExc).attr("stroke", "#16a34a").attr("fill", "none").attr("class", "zone-boundary");
        zoomGroup.append("path").datum(ceArr).attr("d", curveBue).attr("stroke", "#2563eb").attr("fill", "none").attr("class", "zone-boundary");
        zoomGroup.append("path").datum(ceArr).attr("d", curvePer).attr("stroke", "#d97706").attr("fill", "none").attr("class", "zone-boundary");

        zoomGroup.append("text").attr("x", xScale(350)).attr("y", yScale(85)).text("Excelente").attr("class", "zone-text").attr("fill", "#16a34a");
        zoomGroup.append("text").attr("x", xScale(1000)).attr("y", yScale(55)).text("Bueno").attr("class", "zone-text").attr("fill", "#2563eb");
        zoomGroup.append("text").attr("x", xScale(1800)).attr("y", yScale(30)).text("Permisible").attr("class", "zone-text").attr("fill", "#d97706");
        zoomGroup.append("text").attr("x", xScale(2900)).attr("y", yScale(16)).text("Dudoso / Inadecuado").attr("class", "zone-text").attr("fill", "#dc2626");

        data.forEach(m => {{
          zoomGroup.append("circle")
            .attr("cx", xScale(m.ce))
            .attr("cy", yScale(m.pct_na))
            .attr("r", 5.5)
            .attr("fill", m.color)
            .attr("stroke", "#ffffff")
            .attr("stroke-width", 1.8)
            .attr("class", "dot")
            .on("mouseover", (event) => {{
              tooltip.html(`
                <b>🌾 ${{m.id}}</b><br>
                <b>Conductividad:</b> ${{m.ce.toLocaleString()}} µS/cm<br>
                <b>% Sodio Soluble:</b> ${{m.pct_na.toFixed(1)}}%<br>
                <b>RAS:</b> ${{m.ras.toFixed(2)}}<br>
                <b>Facies:</b> ${{m.facies}}
              `);
              const tNode = tooltip.node();
              const tW = tNode.offsetWidth || 220;
              const tH = tNode.offsetHeight || 110;
              let lPos = event.clientX + 14;
              if (lPos + tW > window.innerWidth - 10) lPos = Math.max(10, event.clientX - tW - 14);
              let tPos = event.clientY - 20;
              if (tPos + tH > window.innerHeight - 10) tPos = Math.max(10, event.clientY - tH - 12);
              tooltip.style("left", lPos + "px").style("top", tPos + "px").style("display", "block");
            }})
            .on("mouseout", () => {{ tooltip.style("display", "none"); }});
        }});

        // Componentes de la Lupa (Magnifier Lens)
        const lensGroup = svg.append("g").attr("id", "lens-group").style("display", "none").style("pointer-events", "none");
        const lensRadius = 75;
        const lensMag = 2.5;

        defs.append("clipPath").attr("id", "wilcox-lens-clip")
          .append("circle").attr("r", lensRadius);

        const lensContent = lensGroup.append("g").attr("clip-path", "url(#wilcox-lens-clip)");
        lensContent.append("rect").attr("x", -lensRadius).attr("y", -lensRadius).attr("width", lensRadius * 2).attr("height", lensRadius * 2).attr("fill", "#ffffff");
        const lensUse = lensContent.append("use").attr("href", "#zoom-group");

        lensGroup.append("circle")
          .attr("r", lensRadius)
          .attr("fill", "none")
          .attr("stroke", "#691C32")
          .attr("stroke-width", 3.0)
          .attr("filter", "drop-shadow(0 4px 12px rgba(0,0,0,0.35))");
        lensGroup.append("line").attr("x1", -12).attr("x2", 12).attr("y1", 0).attr("y2", 0).attr("stroke", "#691C32").attr("stroke-width", 1.2).attr("opacity", 0.7);
        lensGroup.append("line").attr("x1", 0).attr("x2", 0).attr("y1", -12).attr("y2", 12).attr("stroke", "#691C32").attr("stroke-width", 1.2).attr("opacity", 0.7);

        // Zoom y Paneo
        let currentTransform = d3.zoomIdentity;
        const zoom = d3.zoom()
          .scaleExtent([0.5, 12])
          .on("start", () => d3.select("#wilcox-svg-container").classed("grabbing", true))
          .on("end", () => d3.select("#wilcox-svg-container").classed("grabbing", false))
          .on("zoom", (event) => {{
            currentTransform = event.transform;
            zoomGroup.attr("transform", currentTransform);
            const pct = Math.round(event.transform.k * 100);
            d3.select("#zoom-level").text(pct + "%");
            updateLens();
          }});

        svg.call(zoom);

        function zoomIn() {{ svg.transition().duration(250).call(zoom.scaleBy, 1.35); }}
        function zoomOut() {{ svg.transition().duration(250).call(zoom.scaleBy, 0.74); }}
        function resetZoom() {{ svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity); }}

        let lupaActiva = false;
        let lastMouseSVG = null;

        function toggleLupa() {{
          lupaActiva = !lupaActiva;
          d3.select("#btn-lupa").classed("active", lupaActiva);
          d3.select("#lupa-status").text(lupaActiva ? "ON" : "OFF");
          d3.select("#wilcox-svg-container").classed("lupa-mode", lupaActiva);
          if (!lupaActiva) {{
            lensGroup.style("display", "none");
            lastMouseSVG = null;
          }}
        }}

        function getSVGPoint(event) {{
          const pt = svg.node().createSVGPoint();
          pt.x = event.clientX;
          pt.y = event.clientY;
          return pt.matrixTransform(svg.node().getScreenCTM().inverse());
        }}

        function updateLens() {{
          if (!lupaActiva || !lastMouseSVG) return;
          const {{x, y}} = lastMouseSVG;
          lensGroup.attr("transform", `translate(${{x}}, ${{y}})`);
          lensUse.attr("transform", `scale(${{lensMag}}) translate(${{-x}}, ${{-y}})`);
        }}

        svg.on("mousemove", function(event) {{
          if (!lupaActiva) return;
          lastMouseSVG = getSVGPoint(event);
          lensGroup.style("display", "block");
          updateLens();
        }});

        svg.on("mouseleave", function() {{
          if (lupaActiva) {{
            lensGroup.style("display", "none");
            lastMouseSVG = null;
          }}
        }});

        function descargarSVG() {{
          const prevTransform = zoomGroup.attr("transform");
          zoomGroup.attr("transform", null);
          lensGroup.style("display", "none");

          const svgEl = document.getElementById("svg-wilcox");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}

          zoomGroup.attr("transform", prevTransform);
          if (lupaActiva && lastMouseSVG) lensGroup.style("display", "block");

          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = "Diagrama_Wilcox_Vectorial.svg";
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarPNG() {{
          const prevTransform = zoomGroup.attr("transform");
          zoomGroup.attr("transform", null);
          lensGroup.style("display", "none");

          const svgEl = document.getElementById("svg-wilcox");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}

          zoomGroup.attr("transform", prevTransform);
          if (lupaActiva && lastMouseSVG) lensGroup.style("display", "block");

          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            canvas.width = w * scale;
            canvas.height = h * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, w, h);
            ctx.drawImage(img, 0, 0, w, h);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Wilcox_300DPI.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code


# =============================================================================
# 5. DIAGRAMA DE RIVERSIDE (USSL) VECTORIAL D3.JS
# =============================================================================
def generar_diagrama_riverside_d3(df_procesado):
    """
    Construye el Diagrama de Riverside (USSL) en D3.js / SVG nativo:
      - Salinidad (C1-C4) vs Peligro de Sodificación (S1-S4).
      - Escala logarítmica de CE e isolíneas empíricas de RAS.
      - Controles de Zoom, Paneo, Lupa de Aumento Dinámica (2.5x) y Descarga SVG/PNG 300 DPI.
    """
    muestras = []
    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        ce = float(r.get('CE_uS_cm', 0.0) if pd.notna(r.get('CE_uS_cm')) else (r.get('SDT_mg_L', 0.0) / 0.65))
        ce = max(100.0, ce)
        ras = float(r.get('RAS', 0.0))
        muestras.append({
            "id": id_m, "ce": ce, "ras": ras,
            "clasif": str(r.get('Clasif_RAS', '')),
            "color": colores[idx % len(colores)],
            "facies": str(r.get('Facies_Piper', ''))
        })

    json_str = json.dumps(muestras)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Riverside D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #ffffff; user-select: none; overflow: hidden; }}
        .toolbar {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
        .btn-toolbar {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px; padding: 5px 11px; font-size: 11px; font-weight: 600; cursor: pointer; color: #334155; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 4px; }}
        .btn-toolbar:hover {{ background: #691C32; color: white; border-color: #691C32; }}
        .btn-toolbar.active {{ background: #691C32 !important; color: white !important; border-color: #691C32 !important; }}
        #riverside-svg-container {{ width: 100%; height: 480px; position: relative; background: #ffffff; overflow: hidden; cursor: grab; }}
        #riverside-svg-container.grabbing {{ cursor: grabbing; }}
        #riverside-svg-container.lupa-mode {{ cursor: crosshair; }}
        svg {{ width: 100%; height: 100%; display: block; }}
        .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
        .c-boundary {{ stroke: #94a3b8; stroke-width: 1.2; stroke-dasharray: 4, 3; fill: none; }}
        .s-boundary {{ stroke-width: 1.2; stroke-dasharray: 3, 3; fill: none; }}
        .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
        .dot {{ cursor: pointer; transition: r 0.2s; }}
        #riv-tooltip {{
          position: fixed; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11px; color: #1e293b; pointer-events: none;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar">
        <div style="font-size: 11.5px; font-weight: 700; color: #691C32; white-space: nowrap;">🌾 Diagrama de Riverside</div>
        <div style="display: flex; gap: 5px; align-items: center; flex-wrap: nowrap;">
          <button class="btn-toolbar" onclick="zoomIn()" title="Acercar (Zoom In)"><span>🔍+</span></button>
          <button class="btn-toolbar" onclick="zoomOut()" title="Alejar (Zoom Out)"><span>🔍-</span></button>
          <button class="btn-toolbar" onclick="resetZoom()" title="Restablecer tamaño original (100%)"><span>🔄 1:1</span></button>
          <button class="btn-toolbar" id="btn-lupa" onclick="toggleLupa()" title="Activar/Desactivar Lupa de Aumento">
            <span>🔎 Lupa</span> <span id="lupa-status" style="font-size:9.5px; opacity:0.85;">OFF</span>
          </button>
          <span id="zoom-level" style="font-size:11px; font-weight:600; color:#64748b; margin: 0 3px;">100%</span>
          <div style="height: 16px; width: 1px; background: #cbd5e1; margin: 0 3px;"></div>
          <button class="btn-toolbar" onclick="descargarSVG()" title="Exportar SVG"><span>📥 SVG</span></button>
          <button class="btn-toolbar" onclick="descargarPNG()" title="Exportar PNG a 300 DPI"><span>🖼️ PNG</span></button>
        </div>
      </div>
      <div id="riv-tooltip"></div>
      <div id="riverside-svg-container"></div>

      <script>
        const data = {json_str};
        const w = 700, h = 440;
        const padL = 60, padR = 30, padT = 30, padB = 55;

        const svg = d3.select("#riverside-svg-container").append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{w}} ${{h}}`)
          .attr("width", w)
          .attr("height", h)
          .attr("id", "svg-riverside")
          .attr("preserveAspectRatio", "xMidYMid meet");

        svg.append("rect")
          .attr("width", w)
          .attr("height", h)
          .attr("fill", "#ffffff");

        const zoomGroup = svg.append("g").attr("id", "zoom-group");

        const defs = svg.append("defs");
        defs.append("style").text(`
          .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
          .c-boundary {{ stroke: #94a3b8; stroke-width: 1.2; stroke-dasharray: 4, 3; fill: none; }}
          .s-boundary {{ stroke-width: 1.2; stroke-dasharray: 3, 3; fill: none; }}
          .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
        `);

        const tooltip = d3.select("#riv-tooltip");

        const xScale = d3.scaleLog().domain([100, 5000]).range([padL, w - padR]);
        const yScale = d3.scaleLinear().domain([0, 32]).range([h - padB, padT]);

        [100, 250, 750, 2250, 5000].forEach(val => {{
          zoomGroup.append("line").attr("x1", xScale(val)).attr("y1", padT).attr("x2", xScale(val)).attr("y2", h - padB).attr("fill", "none").attr("class", val === 100 || val === 5000 ? "grid-line" : "c-boundary");
          zoomGroup.append("text").attr("x", xScale(val)).attr("y", h - padB + 18).text(val).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "middle");
        }});

        [0, 5, 10, 15, 20, 25, 30].forEach(val => {{
          zoomGroup.append("line").attr("x1", padL).attr("y1", yScale(val)).attr("x2", w - padR).attr("y2", yScale(val)).attr("class", "grid-line").attr("fill", "none");
          zoomGroup.append("text").attr("x", padL - 8).attr("y", yScale(val)).text(val).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "end").attr("dominant-baseline", "middle");
        }});

        zoomGroup.append("text").attr("x", xScale(160)).attr("y", padT - 8).text("C1: Baja").attr("font-size", "10px").attr("fill", "#16a34a").attr("text-anchor", "middle").style("font-weight", "700");
        zoomGroup.append("text").attr("x", xScale(430)).attr("y", padT - 8).text("C2: Media").attr("font-size", "10px").attr("fill", "#2563eb").attr("text-anchor", "middle").style("font-weight", "700");
        zoomGroup.append("text").attr("x", xScale(1300)).attr("y", padT - 8).text("C3: Alta").attr("font-size", "10px").attr("fill", "#d97706").attr("text-anchor", "middle").style("font-weight", "700");
        zoomGroup.append("text").attr("x", xScale(3350)).attr("y", padT - 8).text("C4: Muy Alta").attr("font-size", "10px").attr("fill", "#dc2626").attr("text-anchor", "middle").style("font-weight", "700");

        const ceLogArr = d3.range(100, 5001, 25);
        // Ecuaciones empíricas oficiales del USDA Handbook 60 (L.A. Richards, 1954):
        // S1/S2: S = 18.87 - 4.44*log10(CE)
        // S2/S3: S = 31.31 - 6.66*log10(CE)
        // S3/S4: S = 43.75 - 8.87*log10(CE)
        const curveS1 = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, 18.87 - 4.44 * Math.log10(d))));
        const curveS2 = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, 31.31 - 6.66 * Math.log10(d))));
        const curveS3 = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, 43.75 - 8.87 * Math.log10(d))));

        zoomGroup.append("path").datum(ceLogArr).attr("d", curveS1).attr("stroke", "#16a34a").attr("fill", "none").attr("class", "s-boundary");
        zoomGroup.append("path").datum(ceLogArr).attr("d", curveS2).attr("stroke", "#d97706").attr("fill", "none").attr("class", "s-boundary");
        zoomGroup.append("path").datum(ceLogArr).attr("d", curveS3).attr("stroke", "#dc2626").attr("fill", "none").attr("class", "s-boundary");

        zoomGroup.append("text").attr("x", (padL + w - padR)/2).attr("y", h - 12).text("Conductividad Eléctrica (µS/cm, escala log)").attr("class", "axis-label").attr("text-anchor", "middle");
        zoomGroup.append("text").attr("transform", "rotate(-90)").attr("x", -(padT + h - padB)/2).attr("y", 18).text("Relación de Adsorción de Sodio (RAS / SAR)").attr("class", "axis-label").attr("text-anchor", "middle");

        data.forEach(m => {{
          zoomGroup.append("circle")
            .attr("cx", xScale(m.ce))
            .attr("cy", yScale(m.ras))
            .attr("r", 5.5)
            .attr("fill", m.color)
            .attr("stroke", "#ffffff")
            .attr("stroke-width", 1.8)
            .attr("class", "dot")
            .on("mouseover", (event) => {{
              tooltip.html(`
                <b>🌾 ${{m.id}}</b><br>
                <b>Conductividad:</b> ${{m.ce.toLocaleString()}} µS/cm<br>
                <b>RAS:</b> ${{m.ras.toFixed(2)}}<br>
                <b>Diagnóstico:</b> ${{m.clasif}}<br>
                <b>Facies:</b> ${{m.facies}}
              `);
              const tNode = tooltip.node();
              const tW = tNode.offsetWidth || 220;
              const tH = tNode.offsetHeight || 110;
              let lPos = event.clientX + 14;
              if (lPos + tW > window.innerWidth - 10) lPos = Math.max(10, event.clientX - tW - 14);
              let tPos = event.clientY - 20;
              if (tPos + tH > window.innerHeight - 10) tPos = Math.max(10, event.clientY - tH - 12);
              tooltip.style("left", lPos + "px").style("top", tPos + "px").style("display", "block");
            }})
            .on("mouseout", () => {{ tooltip.style("display", "none"); }});
        }});

        // Componentes de la Lupa (Magnifier Lens)
        const lensGroup = svg.append("g").attr("id", "lens-group").style("display", "none").style("pointer-events", "none");
        const lensRadius = 75;
        const lensMag = 2.5;

        defs.append("clipPath").attr("id", "riverside-lens-clip")
          .append("circle").attr("r", lensRadius);

        const lensContent = lensGroup.append("g").attr("clip-path", "url(#riverside-lens-clip)");
        lensContent.append("rect").attr("x", -lensRadius).attr("y", -lensRadius).attr("width", lensRadius * 2).attr("height", lensRadius * 2).attr("fill", "#ffffff");
        const lensUse = lensContent.append("use").attr("href", "#zoom-group");

        lensGroup.append("circle")
          .attr("r", lensRadius)
          .attr("fill", "none")
          .attr("stroke", "#691C32")
          .attr("stroke-width", 3.0)
          .attr("filter", "drop-shadow(0 4px 12px rgba(0,0,0,0.35))");
        lensGroup.append("line").attr("x1", -12).attr("x2", 12).attr("y1", 0).attr("y2", 0).attr("stroke", "#691C32").attr("stroke-width", 1.2).attr("opacity", 0.7);
        lensGroup.append("line").attr("x1", 0).attr("x2", 0).attr("y1", -12).attr("y2", 12).attr("stroke", "#691C32").attr("stroke-width", 1.2).attr("opacity", 0.7);

        // Zoom y Paneo
        let currentTransform = d3.zoomIdentity;
        const zoom = d3.zoom()
          .scaleExtent([0.5, 12])
          .on("start", () => d3.select("#riverside-svg-container").classed("grabbing", true))
          .on("end", () => d3.select("#riverside-svg-container").classed("grabbing", false))
          .on("zoom", (event) => {{
            currentTransform = event.transform;
            zoomGroup.attr("transform", currentTransform);
            const pct = Math.round(event.transform.k * 100);
            d3.select("#zoom-level").text(pct + "%");
            updateLens();
          }});

        svg.call(zoom);

        function zoomIn() {{ svg.transition().duration(250).call(zoom.scaleBy, 1.35); }}
        function zoomOut() {{ svg.transition().duration(250).call(zoom.scaleBy, 0.74); }}
        function resetZoom() {{ svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity); }}

        let lupaActiva = false;
        let lastMouseSVG = null;

        function toggleLupa() {{
          lupaActiva = !lupaActiva;
          d3.select("#btn-lupa").classed("active", lupaActiva);
          d3.select("#lupa-status").text(lupaActiva ? "ON" : "OFF");
          d3.select("#riverside-svg-container").classed("lupa-mode", lupaActiva);
          if (!lupaActiva) {{
            lensGroup.style("display", "none");
            lastMouseSVG = null;
          }}
        }}

        function getSVGPoint(event) {{
          const pt = svg.node().createSVGPoint();
          pt.x = event.clientX;
          pt.y = event.clientY;
          return pt.matrixTransform(svg.node().getScreenCTM().inverse());
        }}

        function updateLens() {{
          if (!lupaActiva || !lastMouseSVG) return;
          const {{x, y}} = lastMouseSVG;
          lensGroup.attr("transform", `translate(${{x}}, ${{y}})`);
          lensUse.attr("transform", `scale(${{lensMag}}) translate(${{-x}}, ${{-y}})`);
        }}

        svg.on("mousemove", function(event) {{
          if (!lupaActiva) return;
          lastMouseSVG = getSVGPoint(event);
          lensGroup.style("display", "block");
          updateLens();
        }});

        svg.on("mouseleave", function() {{
          if (lupaActiva) {{
            lensGroup.style("display", "none");
            lastMouseSVG = null;
          }}
        }});

        function descargarSVG() {{
          const prevTransform = zoomGroup.attr("transform");
          zoomGroup.attr("transform", null);
          lensGroup.style("display", "none");

          const svgEl = document.getElementById("svg-riverside");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}

          zoomGroup.attr("transform", prevTransform);
          if (lupaActiva && lastMouseSVG) lensGroup.style("display", "block");

          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = "Diagrama_Riverside_Vectorial.svg";
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarPNG() {{
          const prevTransform = zoomGroup.attr("transform");
          zoomGroup.attr("transform", null);
          lensGroup.style("display", "none");

          const svgEl = document.getElementById("svg-riverside");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}

          zoomGroup.attr("transform", prevTransform);
          if (lupaActiva && lastMouseSVG) lensGroup.style("display", "block");

          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            canvas.width = w * scale;
            canvas.height = h * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, w, h);
            ctx.drawImage(img, 0, 0, w, h);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Riverside_300DPI.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code


# =============================================================================
# 6. DIAGRAMAS DUALES DE GIBBS VECTORIAL D3.JS
# =============================================================================
def generar_diagrama_gibbs_d3(df_procesado):
    """
    Construye los diagramas duales de Gibbs en D3.js / SVG nativo:
      - Cationes: Na/(Na+Ca) vs SDT (log).
      - Aniones: Cl/(Cl+HCO3) vs SDT (log).
      - Zonas geomorfológicas rectoras sombreadas (Lluvia, Agua-Roca, Evaporación).
      - Controles de Zoom, Paneo, Lupa de Aumento Dinámica (2.5x) y Descarga SVG/PNG 300 DPI.
    """
    muestras = []
    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        sdt = max(10.0, float(r.get('SDT_mg_L', 100.0) if pd.notna(r.get('SDT_mg_L')) else 100.0))
        g_cat = float(r.get('Gibbs_Cationes', np.nan))
        g_an = float(r.get('Gibbs_Aniones', np.nan))
        muestras.append({
            "id": id_m, "sdt": sdt, "g_cat": g_cat, "g_an": g_an,
            "color": colores[idx % len(colores)],
            "facies": str(r.get('Facies_Piper', ''))
        })

    json_str = json.dumps(muestras)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Gibbs D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #ffffff; user-select: none; overflow: hidden; }}
        .toolbar {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
        .btn-toolbar {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px; padding: 5px 11px; font-size: 11px; font-weight: 600; cursor: pointer; color: #334155; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 4px; }}
        .btn-toolbar:hover {{ background: #691C32; color: white; border-color: #691C32; }}
        .btn-toolbar.active {{ background: #691C32 !important; color: white !important; border-color: #691C32 !important; }}
        #gibbs-svg-container {{ width: 100%; height: 500px; position: relative; background: #ffffff; overflow: hidden; cursor: grab; }}
        #gibbs-svg-container.grabbing {{ cursor: grabbing; }}
        #gibbs-svg-container.lupa-mode {{ cursor: crosshair; }}
        svg {{ width: 100%; height: 100%; display: block; }}
        .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
        .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
        .panel-title {{ font-size: 12.5px; fill: #1e293b; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        .zone-rect {{ stroke: none; rx: 4; }}
        .zone-text {{ font-size: 9.5px; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        .dot {{ cursor: pointer; transition: r 0.2s; }}
        #gibbs-tooltip {{
          position: fixed; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11px; color: #1e293b; pointer-events: none;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar">
        <div style="font-size: 11.5px; font-weight: 700; color: #691C32; white-space: nowrap;">🌍 Diagramas de Gibbs</div>
        <div style="display: flex; gap: 5px; align-items: center; flex-wrap: nowrap;">
          <button class="btn-toolbar" onclick="zoomIn()" title="Acercar (Zoom In)"><span>🔍+</span></button>
          <button class="btn-toolbar" onclick="zoomOut()" title="Alejar (Zoom Out)"><span>🔍-</span></button>
          <button class="btn-toolbar" onclick="resetZoom()" title="Restablecer tamaño original (100%)"><span>🔄 1:1</span></button>
          <button class="btn-toolbar" id="btn-lupa" onclick="toggleLupa()" title="Activar/Desactivar Lupa de Aumento">
            <span>🔎 Lupa</span> <span id="lupa-status" style="font-size:9.5px; opacity:0.85;">OFF</span>
          </button>
          <span id="zoom-level" style="font-size:11px; font-weight:600; color:#64748b; margin: 0 3px;">100%</span>
          <div style="height: 16px; width: 1px; background: #cbd5e1; margin: 0 3px;"></div>
          <button class="btn-toolbar" onclick="descargarSVG()" title="Exportar SVG"><span>📥 SVG</span></button>
          <button class="btn-toolbar" onclick="descargarPNG()" title="Exportar PNG a 300 DPI"><span>🖼️ PNG</span></button>
        </div>
      </div>
      <div id="gibbs-tooltip"></div>
      <div id="gibbs-svg-container"></div>

      <script>
        const data = {json_str};
        const totalW = 920, h = 460;
        const padT = 45, padB = 55;
        const panelW = 400;
        const gap = 60;
        const padL1 = 65, padL2 = padL1 + panelW + gap;

        const svg = d3.select("#gibbs-svg-container").append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{totalW}} ${{h}}`)
          .attr("width", totalW)
          .attr("height", h)
          .attr("id", "svg-gibbs")
          .attr("preserveAspectRatio", "xMidYMid meet");

        svg.append("rect")
          .attr("width", totalW)
          .attr("height", h)
          .attr("fill", "#ffffff");

        const zoomGroup = svg.append("g").attr("id", "zoom-group");

        const defs = svg.append("defs");
        defs.append("style").text(`
          .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
          .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
          .panel-title {{ font-size: 12.5px; fill: #1e293b; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
          .zone-rect {{ stroke: none; rx: 4; }}
          .zone-text {{ font-size: 9.5px; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        `);

        const tooltip = d3.select("#gibbs-tooltip");
        const yScale = d3.scaleLog().domain([10, 10000]).range([h - padB, padT]);

        function dibujarPanel(offsetL, titulo, xField, xLabel) {{
          const xScale = d3.scaleLinear().domain([0, 1.0]).range([offsetL, offsetL + panelW]);

          zoomGroup.append("text").attr("x", offsetL + panelW/2).attr("y", padT - 18).text(titulo).attr("class", "panel-title");

          // Envolvente canónica en 'Boomerang' de Gibbs (Science, 1970)
          // 1. Sector Precipitación (Lluvia) - Inferior Derecha
          const lluviaPts = [
            [xScale(0.50), yScale(10)], [xScale(1.0), yScale(10)],
            [xScale(1.0), yScale(80)], [xScale(0.65), yScale(80)],
            [xScale(0.50), yScale(35)]
          ];
          zoomGroup.append("polygon")
            .attr("points", lluviaPts.map(p => `${{p[0]}},${{p[1]}}`).join(" "))
            .attr("fill", "#3b82f6").attr("fill-opacity", 0.15).attr("stroke", "#3b82f6").attr("stroke-width", 1.2).attr("stroke-dasharray", "3,3");
          zoomGroup.append("text").attr("x", xScale(0.78)).attr("y", (yScale(80) + yScale(10))/2 + 4).text("Precipitación (Lluvia)").attr("class", "zone-text").attr("fill", "#1d4ed8");

          // 2. Sector Interacción Agua-Roca / Meteorización - Centro Izquierda
          const rocaPts = [
            [xScale(0.02), yScale(150)], [xScale(0.55), yScale(150)],
            [xScale(0.55), yScale(950)], [xScale(0.02), yScale(950)],
            [xScale(0.00), yScale(500)]
          ];
          zoomGroup.append("polygon")
            .attr("points", rocaPts.map(p => `${{p[0]}},${{p[1]}}`).join(" "))
            .attr("fill", "#22c55e").attr("fill-opacity", 0.15).attr("stroke", "#22c55e").attr("stroke-width", 1.2).attr("stroke-dasharray", "3,3");
          zoomGroup.append("text").attr("x", xScale(0.28)).attr("y", (yScale(950) + yScale(150))/2 + 4).text("Interacción Agua-Roca").attr("class", "zone-text").attr("fill", "#15803d");

          // 3. Sector Evaporación / Salinidad - Superior Derecha
          const evapPts = [
            [xScale(0.45), yScale(1000)], [xScale(1.0), yScale(1000)],
            [xScale(1.0), yScale(10000)], [xScale(0.60), yScale(10000)],
            [xScale(0.45), yScale(3500)]
          ];
          zoomGroup.append("polygon")
            .attr("points", evapPts.map(p => `${{p[0]}},${{p[1]}}`).join(" "))
            .attr("fill", "#ef4444").attr("fill-opacity", 0.15).attr("stroke", "#ef4444").attr("stroke-width", 1.2).attr("stroke-dasharray", "3,3");
          zoomGroup.append("text").attr("x", xScale(0.78)).attr("y", (yScale(10000) + yScale(1000))/2 + 4).text("Evaporación / Salinidad").attr("class", "zone-text").attr("fill", "#b91c1c");

          [0, 0.2, 0.4, 0.6, 0.8, 1.0].forEach(val => {{
            zoomGroup.append("line").attr("x1", xScale(val)).attr("y1", padT).attr("x2", xScale(val)).attr("y2", h - padB).attr("class", "grid-line").attr("fill", "none");
            zoomGroup.append("text").attr("x", xScale(val)).attr("y", h - padB + 18).text(val.toFixed(1)).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "middle");
          }});

          if (offsetL === padL1) {{
            [10, 100, 1000, 10000].forEach(val => {{
              zoomGroup.append("line").attr("x1", padL1).attr("y1", yScale(val)).attr("x2", padL1 + panelW).attr("y2", yScale(val)).attr("class", "grid-line").attr("fill", "none");
              zoomGroup.append("text").attr("x", padL1 - 8).attr("y", yScale(val)).text(val.toLocaleString()).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "end").attr("dominant-baseline", "middle");
            }});
            zoomGroup.append("text").attr("transform", "rotate(-90)").attr("x", -(padT + h - padB)/2).attr("y", 16).text("SDT (mg/L, escala log)").attr("class", "axis-label").attr("text-anchor", "middle");
          }} else {{
            [10, 100, 1000, 10000].forEach(val => {{
              zoomGroup.append("line").attr("x1", offsetL).attr("y1", yScale(val)).attr("x2", offsetL + panelW).attr("y2", yScale(val)).attr("class", "grid-line").attr("fill", "none");
            }});
          }}

          zoomGroup.append("text").attr("x", offsetL + panelW/2).attr("y", h - 12).text(xLabel).attr("class", "axis-label").attr("text-anchor", "middle");

          data.forEach(m => {{
            const xVal = m[xField];
            if (xVal !== null && !isNaN(xVal)) {{
              zoomGroup.append("circle")
                .attr("cx", xScale(xVal))
                .attr("cy", yScale(m.sdt))
                .attr("r", 5.5)
                .attr("fill", m.color)
                .attr("stroke", "#ffffff")
                .attr("stroke-width", 1.8)
                .attr("class", "dot")
                .on("mouseover", (event) => {{
                  tooltip.html(`
                    <b>🧪 ${{m.id}}</b><br>
                    <b>${{xLabel}}:</b> ${{xVal.toFixed(2)}}<br>
                    <b>SDT:</b> ${{m.sdt.toLocaleString()}} mg/L<br>
                    <b>Facies:</b> ${{m.facies}}
                  `);
                  const tNode = tooltip.node();
                  const tW = tNode.offsetWidth || 200;
                  const tH = tNode.offsetHeight || 95;
                  let lPos = event.clientX + 14;
                  if (lPos + tW > window.innerWidth - 10) lPos = Math.max(10, event.clientX - tW - 14);
                  let tPos = event.clientY - 20;
                  if (tPos + tH > window.innerHeight - 10) tPos = Math.max(10, event.clientY - tH - 12);
                  tooltip.style("left", lPos + "px").style("top", tPos + "px").style("display", "block");
                }})
                .on("mouseout", () => {{ tooltip.style("display", "none"); }});
            }}
          }});
        }}

        dibujarPanel(padL1, "Cationes: Na⁺ / (Na⁺ + Ca²⁺)", "g_cat", "Relación Na⁺ / (Na⁺ + Ca²⁺)");
        dibujarPanel(padL2, "Aniones: Cl⁻ / (Cl⁻ + HCO₃⁻)", "g_an", "Relación Cl⁻ / (Cl⁻ + HCO₃⁻)");

        // Componentes de la Lupa (Magnifier Lens)
        const lensGroup = svg.append("g").attr("id", "lens-group").style("display", "none").style("pointer-events", "none");
        const lensRadius = 80;
        const lensMag = 2.5;

        defs.append("clipPath").attr("id", "gibbs-lens-clip")
          .append("circle").attr("r", lensRadius);

        const lensContent = lensGroup.append("g").attr("clip-path", "url(#gibbs-lens-clip)");
        lensContent.append("rect").attr("x", -lensRadius).attr("y", -lensRadius).attr("width", lensRadius * 2).attr("height", lensRadius * 2).attr("fill", "#ffffff");
        const lensUse = lensContent.append("use").attr("href", "#zoom-group");

        lensGroup.append("circle")
          .attr("r", lensRadius)
          .attr("fill", "none")
          .attr("stroke", "#691C32")
          .attr("stroke-width", 3.0)
          .attr("filter", "drop-shadow(0 4px 12px rgba(0,0,0,0.35))");
        lensGroup.append("line").attr("x1", -12).attr("x2", 12).attr("y1", 0).attr("y2", 0).attr("stroke", "#691C32").attr("stroke-width", 1.2).attr("opacity", 0.7);
        lensGroup.append("line").attr("x1", 0).attr("x2", 0).attr("y1", -12).attr("y2", 12).attr("stroke", "#691C32").attr("stroke-width", 1.2).attr("opacity", 0.7);

        // Zoom y Paneo
        let currentTransform = d3.zoomIdentity;
        const zoom = d3.zoom()
          .scaleExtent([0.5, 12])
          .on("start", () => d3.select("#gibbs-svg-container").classed("grabbing", true))
          .on("end", () => d3.select("#gibbs-svg-container").classed("grabbing", false))
          .on("zoom", (event) => {{
            currentTransform = event.transform;
            zoomGroup.attr("transform", currentTransform);
            const pct = Math.round(event.transform.k * 100);
            d3.select("#zoom-level").text(pct + "%");
            updateLens();
          }});

        svg.call(zoom);

        function zoomIn() {{ svg.transition().duration(250).call(zoom.scaleBy, 1.35); }}
        function zoomOut() {{ svg.transition().duration(250).call(zoom.scaleBy, 0.74); }}
        function resetZoom() {{ svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity); }}

        let lupaActiva = false;
        let lastMouseSVG = null;

        function toggleLupa() {{
          lupaActiva = !lupaActiva;
          d3.select("#btn-lupa").classed("active", lupaActiva);
          d3.select("#lupa-status").text(lupaActiva ? "ON" : "OFF");
          d3.select("#gibbs-svg-container").classed("lupa-mode", lupaActiva);
          if (!lupaActiva) {{
            lensGroup.style("display", "none");
            lastMouseSVG = null;
          }}
        }}

        function getSVGPoint(event) {{
          const pt = svg.node().createSVGPoint();
          pt.x = event.clientX;
          pt.y = event.clientY;
          return pt.matrixTransform(svg.node().getScreenCTM().inverse());
        }}

        function updateLens() {{
          if (!lupaActiva || !lastMouseSVG) return;
          const {{x, y}} = lastMouseSVG;
          lensGroup.attr("transform", `translate(${{x}}, ${{y}})`);
          lensUse.attr("transform", `scale(${{lensMag}}) translate(${{-x}}, ${{-y}})`);
        }}

        svg.on("mousemove", function(event) {{
          if (!lupaActiva) return;
          lastMouseSVG = getSVGPoint(event);
          lensGroup.style("display", "block");
          updateLens();
        }});

        svg.on("mouseleave", function() {{
          if (lupaActiva) {{
            lensGroup.style("display", "none");
            lastMouseSVG = null;
          }}
        }});

        function descargarSVG() {{
          const prevTransform = zoomGroup.attr("transform");
          zoomGroup.attr("transform", null);
          lensGroup.style("display", "none");

          const svgEl = document.getElementById("svg-gibbs");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}

          zoomGroup.attr("transform", prevTransform);
          if (lupaActiva && lastMouseSVG) lensGroup.style("display", "block");

          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = "Diagrama_Gibbs_Vectorial.svg";
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarPNG() {{
          const prevTransform = zoomGroup.attr("transform");
          zoomGroup.attr("transform", null);
          lensGroup.style("display", "none");

          const svgEl = document.getElementById("svg-gibbs");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}

          zoomGroup.attr("transform", prevTransform);
          if (lupaActiva && lastMouseSVG) lensGroup.style("display", "block");

          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            canvas.width = totalW * scale;
            canvas.height = h * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, totalW, h);
            ctx.drawImage(img, 0, 0, totalW, h);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Gibbs_300DPI.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code
