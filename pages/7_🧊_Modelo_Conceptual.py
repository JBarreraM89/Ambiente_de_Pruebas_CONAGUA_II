# -*- coding: utf-8 -*-
"""
Módulo de Modelo Geológico y Conceptual 3D (Estación de Trabajo Geocientífica)
- DEM SRTM/Terrarium descargado en EPSG:3857, sin batimetría oceánica (z < -12 m -> nodata),
  reproyectado rigurosamente a EPSG:4326 y recortado exactamente al polígono oficial del acuífero.
- Recorte espacial en streaming (PyArrow iter_batches + Shapely prepared) sobre
  Litologia_Nacional_SGM.parquet y Estructuras_Nacional_SGM.parquet (bajo consumo de RAM).
- Selector de modo dual:
    1) Solo Acuífero (Bloque 3D Aislado) -> Escala real 1:1 calibrada en metros, polígonos con
       huecos (evenodd + point-in-polygon con anillos interiores), rotación orbital 360° (Three.js).
    2) Con Entorno Geográfico (Mapa Mundial) -> Contexto regional continuo (MapLibre 3D).
- Simbología oficial SGM (3,024 reglas QGIS) con resolución exacta O(1) sin falsos positivos.
- Gestor de pozos/puntos sincronizado en tiempo real (st.rerun(scope="app")), normalización de
  entidades federativas y filtrado de puntos dentro/fuera del acuífero activo.
- Exportación SIG oficial bajo demanda (callable + on_click="ignore"): GeoTIFF, Shapefile, KMZ y CSV.
"""

import html as _html
import io
import json
import logging
import math
import os
import re
import tempfile
import threading
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests
import shapely
from PIL import Image
from pyproj import Geod, Transformer
from shapely.geometry import Point
from shapely.ops import transform as shapely_transform
import streamlit as st
import streamlit.components.v1 as components

from core.data_loader import (
    DIRECTORIO_RAIZ,
    cargar_catalogo,
    normalizar_clave,
    normalizar_serie_clave,
    obtener_datos_maestros_compartidos,
)
from core.pmtiles_server import obtener_url_pmtiles
from core.puntos import detectar_columnas_puntos
from utils.styles import banner_institucional, inyectar_css_oficial

logger = logging.getLogger(__name__)

# =======================================================
# 🎨 1. CONFIGURACIÓN Y UTILIDADES DE SEGURIDAD
# =======================================================
inyectar_css_oficial()
banner_institucional()

DEM_CACHE_VERSION = "v3_3857_4326_nobathy12"
GEO_CACHE_VERSION = "v2_full_vertices"
ORIGIN_SHIFT_3857 = 20037508.342789244  # pi * R_WGS84
MIN_TERRESTRIAL_ELEV_M = -12.0  # Laguna Salada (-10 m) es el punto terrestre más bajo de México
MAX_TESELAS_DEM = 400  # tope de teselas (~105 MB de malla base) para proteger la memoria
GEOD_WGS84 = Geod(ellps="WGS84")


def _json_seguro(texto: str) -> str:
    """JSON apto para incrustar en <script>: evita rupturas con '</script>', '<!--' o separadores Unicode."""
    return (
        str(texto)
        .replace("</", "<\\/")
        .replace("<!--", "<\\!--")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _normalizar_texto_clave(texto) -> str:
    """Mayúsculas sin acentos ni espacios extra para comparar nombres de entidades federativas."""
    if texto is None:
        return ""
    try:
        if pd.isna(texto):
            return ""
    except (TypeError, ValueError):
        pass
    s = unicodedata.normalize("NFKD", str(texto).strip().upper())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)


_ALIAS_ESTADOS = {
    "DISTRITO FEDERAL": "CIUDAD DE MEXICO",
    "CDMX": "CIUDAD DE MEXICO",
    "D F": "CIUDAD DE MEXICO",
    "MEXICO": "ESTADO DE MEXICO",
    "EDOMEX": "ESTADO DE MEXICO",
    "COAHUILA": "COAHUILA DE ZARAGOZA",
    "MICHOACAN": "MICHOACAN DE OCAMPO",
    "VERACRUZ": "VERACRUZ DE IGNACIO DE LA LLAVE",
}


def _resolver_estado_en_catalogo(edo_raw, lista_estados_cat: list):
    """Mapea el nombre de estado de gdf_m (sin acentos/alias históricos) al texto exacto del catálogo."""
    if not edo_raw or not lista_estados_cat:
        return None
    objetivo = _normalizar_texto_clave(edo_raw)
    objetivo_alias = _ALIAS_ESTADOS.get(objetivo, objetivo)
    mapa = {_normalizar_texto_clave(e): e for e in lista_estados_cat}
    if objetivo in mapa:
        return mapa[objetivo]
    if objetivo_alias in mapa:
        return mapa[objetivo_alias]
    # Coincidencia por prefijo seguro (ej. COAHUILA -> COAHUILA DE ZARAGOZA o viceversa)
    for k_norm, orig in mapa.items():
        if k_norm.startswith(objetivo + " ") or objetivo.startswith(k_norm + " "):
            return orig
    return None


def _reparar_texto_mojibake(val) -> str:
    """Repara mojibake UTF-8 leído como Latin-1 (ej. 'MetamÃ³rfica' -> 'Metamórfica')."""
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    if not s:
        return ""
    if "Ã" in s or "Â" in s or "â" in s:
        try:
            s = s.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s


def _pozos_para_visor(lista: list) -> list:
    """Valida coordenadas, profundidad, nivel estático y color de cada punto para el visor JS."""
    seguros = []
    for p in lista:
        try:
            lat = float(p.get("lat"))
            lon = float(p.get("lon"))
            if not (math.isfinite(lat) and math.isfinite(lon)):
                continue
        except (TypeError, ValueError):
            continue

        q = {
            "lat": lat,
            "lon": lon,
            "nombre": str(p.get("nombre") or "Pozo").strip(),
            "tipo": str(p.get("tipo") or "Pozo existente").strip(),
            "profundidad": None,
            "nivel_estatico": None,
            "color_hex": None,
        }
        prof = p.get("profundidad")
        if prof is not None:
            try:
                pf = float(prof)
                if math.isfinite(pf) and pf > 0:
                    q["profundidad"] = round(pf, 2)
            except (TypeError, ValueError):
                pass
        ne = p.get("nivel_estatico")
        if ne is not None:
            try:
                nf = float(ne)
                if math.isfinite(nf) and nf >= 0:
                    q["nivel_estatico"] = round(nf, 2)
            except (TypeError, ValueError):
                pass
        color = p.get("color_hex")
        if color is not None and re.fullmatch(r"#[0-9A-Fa-f]{6}", str(color).strip()):
            q["color_hex"] = str(color).strip()
        seguros.append(q)
    return seguros


def _render_html_visor(html_code: str, height: int = 760):
    """Renderiza el visor HTML usando st.iframe (Streamlit 1.58+) con respaldo a components.html."""
    if hasattr(st, "iframe"):
        st.iframe(html_code, height=height)
    else:
        components.html(html_code, height=height)


def _extraer_geometrias_por_familia(gdf: gpd.GeoDataFrame, familia: str) -> gpd.GeoDataFrame:
    """Filtra y normaliza un GeoDataFrame a una familia geométrica homogénea ('polygon' o 'line').

    Evita fallos de ESRI Shapefile y KMZ cuando `.clip()` genera GeometryCollection o residuos de borde.
    """
    if gdf is None or gdf.empty:
        return gdf
    tipos_ok = ("Polygon", "MultiPolygon") if familia == "polygon" else ("LineString", "MultiLineString")
    geoms_limpias = []
    indices_ok = []

    for idx, geom in zip(gdf.index, gdf.geometry):
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in tipos_ok:
            geoms_limpias.append(geom)
            indices_ok.append(idx)
        elif geom.geom_type == "GeometryCollection":
            sub = [g for g in geom.geoms if g is not None and not g.is_empty and g.geom_type in tipos_ok]
            if not sub:
                continue
            geom_unida = shapely.unary_union(sub) if len(sub) > 1 else sub[0]
            if geom_unida is not None and not geom_unida.is_empty and geom_unida.geom_type in tipos_ok:
                geoms_limpias.append(geom_unida)
                indices_ok.append(idx)

    if not indices_ok:
        return gdf.iloc[0:0].copy()
    out = gdf.loc[indices_ok].copy()
    out["geometry"] = geoms_limpias
    return out.reset_index(drop=True)


def _rerun_app():
    """Fuerza rerun completo de la aplicación desde un @st.fragment."""
    try:
        st.rerun(scope="app")
    except TypeError:
        st.rerun()


st.subheader("🧊 Estación de Trabajo: Modelo Conceptual 3D")
st.caption("Modelación geológica y física 3D: Bloque aislado a escala real calibrada, estructuras 1:50k SGM y pozos con profundidad real.")

if "lista_marcadores" not in st.session_state:
    st.session_state["lista_marcadores"] = []
if "csv_uploader_key_mc" not in st.session_state:
    st.session_state["csv_uploader_key_mc"] = 0
if "mc_pts_ver" not in st.session_state:
    st.session_state["mc_pts_ver"] = 0

# =======================================================
# 🏛️ 2. CARGA DE ESTILOS OFICIALES SGM (O(1) SIN FALSOS POSITIVOS)
# =======================================================
@st.cache_data(show_spinner=False, max_entries=1, ttl=86400)
def cargar_estilos_sgm_oficiales():
    ruta_json = DIRECTORIO_RAIZ / "data" / "geologia" / "estilos_oficiales_sgm.json"
    if ruta_json.exists():
        try:
            with open(ruta_json, "r", encoding="utf-8") as f:
                raw = json.load(f)
            normalizado = {str(k).strip().upper(): v for k, v in raw.items() if isinstance(v, str)}
            return normalizado, f"Catálogo Oficial SGM ({len(normalizado):,} reglas QGIS)"
        except Exception:
            logger.exception("No se pudo cargar estilos_oficiales_sgm.json")
    return {}, "Norma Cartográfica General SGM"


DICCIONARIO_SGM_GLOBAL, ORIGEN_SGM_GLOBAL = cargar_estilos_sgm_oficiales()

TABLA_CROMATICA_RESPALDO = {
    "H2O": "#A6CAE8", "AGUA": "#A6CAE8",
    "Q(AL)": "#FFF5AF", "ALUVION": "#FFF5AF", "ALUVIAL": "#FFF5AF",
    "Q(AR)": "#FFE696", "ARENA": "#FFE696",
    "Q(CO)": "#E6CDA0", "CONGLOMERADO": "#E6CDA0",
    "Q(LA)": "#EBEBBE", "QPTLA": "#EBEBBE", "LACUSTRE": "#EBEBBE",
    "QPT(B)": "#800080", "BASALTO": "#800080",
    "QPT(A)": "#C33278", "ANDESITA": "#B43264", "TPA(A)": "#B43264",
    "TPA(R)": "#ED5F7D", "RIOLITA": "#ED5F7D",
    "TPA(D)": "#F07D3C", "DACITA": "#F07D3C",
    "TPA(TR)": "#F7AFAF", "TOBA RIOLITICA": "#F7AFAF", "TPA(TA)": "#B98CC3",
    "K(CZ)": "#2887CD", "CALIZA": "#2887CD", "KI(CZ)": "#0F5FAF", "KS(CZ)": "#5FAFE6",
    "K(LU)": "#9BB95A", "LUTITA": "#9BB95A",
    "K(AR)": "#BED273", "ARENISCA": "#BED273", "TPLAR": "#BED273",
    "GR": "#EB3732", "GRANITO": "#EB3732",
    "GD": "#D74B46", "GRANODIORITA": "#D74B46",
    "DIABASA": "#B71C1C",
    "PORFIDO RIOLITICO": "#E04070",
    "COMPLEJO METAMORFICO": "#7E57C2", "METASEDIMENTARIO": "#9575CD", "PIZARRA": "#7E57C2",
}


def resolver_color_oficial(clave_sgm, litologia, roca) -> str:
    """Resuelve el color SGM oficial en O(1) sin falsos positivos por subcadenas cortas."""
    clv = _reparar_texto_mojibake(clave_sgm).upper()
    lito = _reparar_texto_mojibake(litologia).upper()
    roca_t = _reparar_texto_mojibake(roca).upper()

    # 1. Coincidencia exacta por clave SGM (cubre ~98 % de las unidades nacionales)
    if clv in DICCIONARIO_SGM_GLOBAL:
        return DICCIONARIO_SGM_GLOBAL[clv]
    if clv in TABLA_CROMATICA_RESPALDO:
        return TABLA_CROMATICA_RESPALDO[clv]

    # 2. Coincidencia exacta por litología completa o término litológico dominante (antes de '-')
    lito_norm = _normalizar_texto_clave(lito)
    lito_primaria = lito_norm.split("-")[0].strip() if lito_norm else ""
    for candidato in (lito, lito_norm, lito_primaria):
        if not candidato or candidato in ("NO APLICABLE", "INDETERMINADO", "NINGUNO"):
            continue
        if candidato in DICCIONARIO_SGM_GLOBAL:
            return DICCIONARIO_SGM_GLOBAL[candidato]
        if candidato in TABLA_CROMATICA_RESPALDO:
            return TABLA_CROMATICA_RESPALDO[candidato]

    # 3. Clasificación geológica controlada por palabras clave (sin subcadenas arbitrarias de 3 letras)
    texto_eval = f"{clv} {lito_norm} {_normalizar_texto_clave(roca_t)}"
    if "H2O" in texto_eval or "AGUA" in texto_eval:
        return "#A6CAE8"
    if any(k in texto_eval for k in ("ALUV", "SUELO", "LITORAL", "EOLIC")):
        return "#FFF5AF"
    if "LACUSTR" in texto_eval:
        return "#EBEBBE"
    if "CONGLOM" in texto_eval or "BRECHA SED" in texto_eval:
        return "#E6CDA0"
    if "BASALT" in texto_eval:
        return "#800080"
    if "DACIT" in texto_eval:
        return "#F07D3C"
    if "TOBA" in texto_eval or "IGNIMBRIT" in texto_eval:
        return "#F7AFAF"
    if "RIOLIT" in texto_eval or "PORFIDO" in texto_eval:
        return "#ED5F7D"
    if "ANDESIT" in texto_eval:
        return "#B43264"
    if "CALIZ" in texto_eval or "DOLOM" in texto_eval or "COQUINA" in texto_eval or "TRAVERT" in texto_eval:
        return "#2887CD"
    if "LUTIT" in texto_eval or "LIMOLIT" in texto_eval or "MARGA" in texto_eval:
        return "#9BB95A"
    if "ARENISC" in texto_eval or "ARENA" in texto_eval:
        return "#BED273"
    if any(k in texto_eval for k in ("GRANOD", "TONALIT", "MONZONIT")):
        return "#D74B46"
    if any(k in texto_eval for k in ("GRANIT", "DIABAS", "GABRO", "DIORIT", "INTRUSIV")):
        return "#EB3732"
    if any(k in texto_eval for k in ("METAMORF", "METASED", "PIZARRA", "FILITA", "ESQUISTO", "GNEIS", "MARMOL", "CUARCITA")):
        return "#8B5CF6"
    return "#B0BEC5"


# =======================================================
# 🛰️ 3. MOTOR DE AUTODETECCIÓN ESPACIAL DE ACUÍFEROS
# =======================================================
gdf_m = obtener_datos_maestros_compartidos()
df_cat = cargar_catalogo("Acuiferos_2026.csv")
ESTADOS_CATALOGO = sorted(df_cat["ESTADO"].dropna().unique().tolist()) if df_cat is not None and not df_cat.empty else []


def auto_identificar_acuifero_por_coordenadas(lat, lon, gdf_consulta):
    """Identifica el acuífero oficial CONAGUA que contiene el punto (lat, lon)."""
    try:
        val_lat = float(lat)
        val_lon = -abs(float(lon))
        if not (math.isfinite(val_lat) and math.isfinite(val_lon)):
            return None
        pt_geom = Point(val_lon, val_lat)

        if gdf_consulta is None or gdf_consulta.empty:
            return None

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
                cve = normalizar_clave(fila.get("CLV_ACUI", fila.get("CLAVE_SIGM", "")))
                nom = str(fila.get("NOM_ACUI", fila.get("ACUÍFERO", ""))).strip()
                area = round(float(fila.get("AREA_KM2", 0.0)), 1)
                edo_raw = str(fila.get("NOM_EDO", fila.get("ESTADO", ""))).strip()
                edo_cat = _resolver_estado_en_catalogo(edo_raw, ESTADOS_CATALOGO)
                # Usar nombre oficial del catálogo si existe para mantener 100 % de paridad en los selectores
                etiqueta_cat = None
                if df_cat is not None and not df_cat.empty:
                    m_cat = df_cat[normalizar_serie_clave(df_cat["CLAVE_SIGM"]) == cve]
                    if not m_cat.empty:
                        row_c = m_cat.iloc[0]
                        edo_cat = str(row_c["ESTADO"]).strip()
                        nom = str(row_c["ACUÍFERO"]).strip()
                        area = round(float(row_c["AREA_KM2"]), 1)
                        etiqueta_cat = f"{normalizar_clave(row_c['CLAVE_SIGM'])} - {nom}"
                return {
                    "clave": cve,
                    "nombre": nom,
                    "area": area,
                    "estado": edo_cat,
                    "etiqueta": etiqueta_cat,
                }
    except Exception:
        logger.exception("Error autoidentificando acuífero para (%s, %s)", lat, lon)
    return None


def _activar_acuifero_en_sesion(acuif: dict):
    """Sincroniza el acuífero activo y programa la actualización limpia de los selectores."""
    if not acuif or not acuif.get("clave"):
        return
    st.session_state["clave_mc"] = acuif["clave"]
    st.session_state["nombre_mc"] = acuif["nombre"]
    st.session_state["area_total_mc"] = acuif["area"]
    st.session_state["_mc_sync_edo"] = acuif.get("estado")
    st.session_state["_mc_sync_clv"] = acuif.get("etiqueta")


# =======================================================
# 📍 4. GESTOR DE PUNTOS CON PROFUNDIDAD REAL (SINCRONIZADO)
# =======================================================
@st.fragment
def renderizar_controles_puntos():
    v = st.session_state.get("mc_pts_ver", 0)
    tab_manual, tab_csv = st.tabs(["✍️ Manual", "📁 Carga CSV"])

    with tab_manual:
        nom_val = st.text_input(
            "Identificador:",
            key=f"mc_nombre_punto_{v}",
            placeholder="Ej. Pozo San Bernardo",
        )
        tipo_val = st.selectbox(
            "Tipo de Infraestructura:",
            ["Pozo existente", "Pozo requerido", "PTAR existente", "PTAR requerido", "Tanque existente", "Tanque requerido"],
            key=f"mc_tipo_punto_{v}",
        )
        c_lat, c_lon = st.columns(2)
        lat_val = c_lat.number_input("Latitud (N):", value=0.0, format="%.5f", key=f"mc_lat_punto_{v}")
        lon_val = c_lon.number_input("Longitud (W):", value=0.0, format="%.5f", key=f"mc_lon_punto_{v}")
        c_pr, c_ne = st.columns(2)
        prof_val = c_pr.number_input(
            "Profundidad (m):",
            value=150.0,
            min_value=1.0,
            max_value=2000.0,
            step=10.0,
            key=f"mc_prof_punto_{v}",
        )
        ne_val = c_ne.number_input(
            "Nivel Estático (m):",
            value=0.0,
            min_value=0.0,
            max_value=1500.0,
            step=5.0,
            help="Profundidad al nivel del agua (0 = sin dato).",
            key=f"mc_ne_punto_{v}",
        )

        btn_c1, btn_c2 = st.columns(2)
        if btn_c1.button("➕ Agregar", width="stretch", type="primary", key="btn_agregar_manual_mc"):
            if lat_val == 0.0 or lon_val == 0.0:
                st.warning("⚠️ Ingresa coordenadas válidas de Latitud y Longitud distintas de 0.")
            elif not (-90.0 <= lat_val <= 90.0 and -180.0 <= lon_val <= 180.0):
                st.error("❌ Coordenadas fuera de rango geográfico válido.")
            else:
                lon_final = -abs(float(lon_val))
                nuevo_pto = {
                    "lat": float(lat_val),
                    "lon": lon_final,
                    "nombre": nom_val.strip() if nom_val.strip() else f"Punto {len(st.session_state['lista_marcadores']) + 1}",
                    "tipo": tipo_val,
                    "profundidad": float(prof_val),
                    "nivel_estatico": float(ne_val) if ne_val > 0 else None,
                }
                if ne_val > 0 and ne_val >= prof_val:
                    st.toast(
                        "⚠️ El Nivel Estático es mayor o igual a la profundidad; el pozo se dibujará sin columna saturada.",
                        icon="⚠️",
                    )
                st.session_state["lista_marcadores"].append(nuevo_pto)
                acuif = auto_identificar_acuifero_por_coordenadas(lat_val, lon_final, gdf_m)
                if acuif:
                    _activar_acuifero_en_sesion(acuif)
                    st.toast(f"📍 Acuífero detectado: {acuif['clave']} - {acuif['nombre']}", icon="📍")
                else:
                    st.toast("⚠️ Punto agregado fuera de los límites oficiales de acuíferos.", icon="⚠️")
                st.session_state["mc_pts_ver"] = v + 1
                _rerun_app()

        if btn_c2.button("🧹 Limpiar", width="stretch", type="secondary", key="btn_limp_manual_mc"):
            st.session_state["lista_marcadores"] = []
            st.session_state["mc_pts_ver"] = v + 1
            st.session_state["csv_uploader_key_mc"] = st.session_state.get("csv_uploader_key_mc", 0) + 1
            _rerun_app()

    with tab_csv:
        st.markdown(
            """<div style="background-color: #f8f9fa; border: 1px dashed #ced4da; border-radius: 4px; padding: 6px 10px; font-size: 10px; color: #495057; margin-bottom: 8px;">Requisitos: columnas <b>Lat</b>, <b>Long</b> y opcionales <b>Profundidad</b> / <b>Nivel Estático</b>.</div>""",
            unsafe_allow_html=True,
        )

        up_key = f"csv_up_mc_{st.session_state.get('csv_uploader_key_mc', 0)}"
        archivo_csv = st.file_uploader("Seleccionar archivo CSV", type=["csv"], label_visibility="collapsed", key=up_key)

        c_csv1, c_csv2 = st.columns(2)
        if c_csv2.button("🧹 Limpiar", width="stretch", type="secondary", key="btn_limp_csv_mc"):
            st.session_state["lista_marcadores"] = []
            st.session_state["mc_pts_ver"] = v + 1
            st.session_state["csv_uploader_key_mc"] = st.session_state.get("csv_uploader_key_mc", 0) + 1
            _rerun_app()

        if archivo_csv is not None:
            if c_csv1.button("🚀 Cargar", width="stretch", type="primary", key="btn_cargar_csv_mc"):
                try:
                    archivo_csv.seek(0)
                    try:
                        df_p = pd.read_csv(archivo_csv, sep=None, engine="python", encoding="utf-8-sig")
                    except Exception:
                        archivo_csv.seek(0)
                        df_p = pd.read_csv(archivo_csv, sep=";", encoding="latin1")

                    df_p.columns = df_p.columns.astype(str).str.strip().str.upper()

                    _cols = detectar_columnas_puntos(df_p.columns)
                    col_lat, col_lon, col_tipo, col_nom = _cols["lat"], _cols["lon"], _cols["tipo"], _cols["nombre"]
                    col_color, col_prof, col_ne = _cols["color"], _cols["profundidad"], _cols["nivel_estatico"]

                    if col_lat and col_lon:
                        nuevos_puntos = []
                        acuifero_detectado = None

                        for _, row in df_p.iterrows():
                            lat_v = pd.to_numeric(str(row[col_lat]).replace(",", ".").strip(), errors="coerce")
                            lon_v = pd.to_numeric(str(row[col_lon]).replace(",", ".").strip(), errors="coerce")

                            if pd.notna(lat_v) and pd.notna(lon_v) and (-90.0 <= float(lat_v) <= 90.0) and (-180.0 <= float(lon_v) <= 180.0):
                                tipo_v = str(row[col_tipo]).strip() if col_tipo and pd.notna(row[col_tipo]) else "Pozo existente"
                                nom_v = str(row[col_nom]).strip() if col_nom and pd.notna(row[col_nom]) else tipo_v
                                col_v = str(row[col_color]).strip() if col_color and pd.notna(row[col_color]) else None

                                prof_v = None
                                if col_prof and pd.notna(row[col_prof]):
                                    try:
                                        pf = float(str(row[col_prof]).replace(",", ".").strip())
                                        if math.isfinite(pf) and pf > 0:
                                            prof_v = pf
                                    except ValueError:
                                        pass

                                ne_v = None
                                if col_ne and pd.notna(row[col_ne]):
                                    try:
                                        nf = float(str(row[col_ne]).replace(",", ".").strip())
                                        if math.isfinite(nf) and nf >= 0:
                                            ne_v = nf
                                    except ValueError:
                                        pass

                                lon_final = -abs(float(lon_v))
                                nuevos_puntos.append({
                                    "lat": float(lat_v),
                                    "lon": lon_final,
                                    "nombre": nom_v,
                                    "tipo": tipo_v,
                                    "color_hex": col_v,
                                    "profundidad": prof_v,
                                    "nivel_estatico": ne_v,
                                })

                                if not acuifero_detectado:
                                    acuifero_detectado = auto_identificar_acuifero_por_coordenadas(lat_v, lon_final, gdf_m)

                        if nuevos_puntos:
                            st.session_state["lista_marcadores"].extend(nuevos_puntos)
                            if acuifero_detectado:
                                _activar_acuifero_en_sesion(acuifero_detectado)
                                st.toast(
                                    f"📍 {len(nuevos_puntos)} puntos cargados · Acuífero: {acuifero_detectado['clave']} - {acuifero_detectado['nombre']}",
                                    icon="📍",
                                )
                            else:
                                st.toast(f"✅ {len(nuevos_puntos)} puntos procesados.", icon="✅")
                            st.session_state["csv_uploader_key_mc"] = st.session_state.get("csv_uploader_key_mc", 0) + 1
                            _rerun_app()
                        else:
                            st.error("❌ No se encontraron coordenadas válidas.")
                    else:
                        st.error("❌ Faltan columnas de Latitud y Longitud en el CSV.")
                except Exception as e:
                    st.error(f"Error procesando CSV: {e}")
        else:
            c_csv1.button("🚀 Cargar", width="stretch", type="primary", disabled=True, key="btn_cargar_csv_dis_mc")

    n_marcadores = len(st.session_state["lista_marcadores"])
    if n_marcadores > 0:
        st.caption(f"📌 **{n_marcadores}** punto(s) en sesión")
        # Capturar copia por valor: st.download_button(data=callable) corre en hilo sin st.session_state
        _pts_snapshot = [dict(p) for p in st.session_state["lista_marcadores"]]

        def _csv_puntos_bytes(pts=_pts_snapshot) -> bytes:
            df_desc = pd.DataFrame(pts).rename(
                columns={
                    "tipo": "Infraestructura",
                    "nombre": "Nombre",
                    "lat": "Lat",
                    "lon": "Long",
                    "profundidad": "Profundidad_m",
                    "nivel_estatico": "Nivel_Estatico_m",
                }
            )
            cols_c = [
                c
                for c in ["Infraestructura", "Nombre", "Lat", "Long", "Profundidad_m", "Nivel_Estatico_m"]
                if c in df_desc.columns
            ]
            return df_desc[cols_c].to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            label="⬇️ Descargar Puntos (CSV)",
            data=_csv_puntos_bytes,
            file_name="puntos_modelo_3d.csv",
            mime="text/csv",
            type="secondary",
            width="stretch",
            on_click="ignore",
        )


st.sidebar.markdown(
    """
    <style>
        section[data-testid="stSidebar"] button[kind="secondary"],
        section[data-testid="stSidebar"] button[data-baseweb="button"]:not([kind="primary"]),
        section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button,
        section[data-testid="stSidebar"] div[data-testid="stLinkButton"] a {
            background-color: #e9ecef !important;
            border: 1px solid #ced4da !important;
            border-radius: 6px !important;
            color: #333333 !important;
            font-weight: 600 !important;
            width: 100% !important;
            min-height: 38px !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-decoration: none !important;
            transition: all 0.2s ease !important;
            margin-top: 4px !important;
        }
        section[data-testid="stSidebar"] button[kind="secondary"]:hover,
        section[data-testid="stSidebar"] button[data-baseweb="button"]:not([kind="primary"]):hover,
        section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button:hover,
        section[data-testid="stSidebar"] div[data-testid="stLinkButton"] a:hover {
            background-color: #dde2e6 !important;
            border-color: #adb5bd !important;
            color: #000000 !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        }
        section[data-testid="stSidebar"] button[kind="primary"] {
            border-radius: 6px !important;
            min-height: 38px !important;
            font-weight: 600 !important;
            margin-top: 4px !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("---")
st.sidebar.subheader("📍 Puntos de Referencia / Pozos")
st.sidebar.markdown(
    """
    <div style="font-size: 11px; color: #666; margin-top: -14px; margin-bottom: 8px;">
        Ingresa coordenadas manuales o carga masiva vía CSV
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    renderizar_controles_puntos()

# =======================================================
# 🔍 5. SINCRONIZACIÓN Y SELECCIÓN MANUAL DE ACUÍFERO (SIN REBOTES NI RERUN EXTRA)
# =======================================================
# Aplicar sincronización pendiente desde autodetección ANTES de instanciar los selectbox
if "_mc_sync_edo" in st.session_state:
    sync_edo = st.session_state.pop("_mc_sync_edo")
    sync_clv = st.session_state.pop("_mc_sync_clv", None)
    if sync_edo in ESTADOS_CATALOGO:
        st.session_state["mc_sel_edo"] = sync_edo
        st.session_state["mc_sel_clv"] = sync_clv
    else:
        st.session_state["mc_sel_clv"] = None

# Sanitizar por seguridad si mc_sel_edo tiene un valor no perteneciente al catálogo
if st.session_state.get("mc_sel_edo") not in ESTADOS_CATALOGO:
    st.session_state["mc_sel_edo"] = None


def _on_estado_change_mc():
    st.session_state["mc_sel_clv"] = None


def _on_acuifero_change_mc():
    sel = st.session_state.get("mc_sel_clv")
    if not sel or df_cat is None or df_cat.empty:
        return
    clave_sel = normalizar_clave(sel.split(" - ")[0])
    m = df_cat[normalizar_serie_clave(df_cat["CLAVE_SIGM"]) == clave_sel]
    if not m.empty:
        row_a = m.iloc[0]
        st.session_state["clave_mc"] = clave_sel
        st.session_state["nombre_mc"] = str(row_a["ACUÍFERO"]).strip()
        st.session_state["area_total_mc"] = round(float(row_a["AREA_KM2"]), 1)


with st.expander("📍 Búsqueda Manual de Acuífero en Catálogo", expanded=not bool(st.session_state.get("clave_mc"))):
    if df_cat is not None and not df_cat.empty:
        c_est, c_clav = st.columns(2)
        estado_sel = c_est.selectbox(
            "1. Estado:",
            ESTADOS_CATALOGO,
            index=None,
            key="mc_sel_edo",
            placeholder="Elige un estado...",
            on_change=_on_estado_change_mc,
        )

        opciones_acuiferos = []
        if estado_sel:
            df_est = df_cat[df_cat["ESTADO"] == estado_sel]
            claves_fmt = normalizar_serie_clave(df_est["CLAVE_SIGM"])
            opciones_acuiferos = sorted((claves_fmt + " - " + df_est["ACUÍFERO"].astype(str).str.strip()).unique().tolist())

        # Si el valor actual en mc_sel_clv no pertenece al estado seleccionado, limpiar antes de crear widget
        if st.session_state.get("mc_sel_clv") not in opciones_acuiferos:
            st.session_state["mc_sel_clv"] = None

        c_clav.selectbox(
            "2. Clave o Nombre del Acuífero:",
            opciones_acuiferos,
            index=None,
            key="mc_sel_clv",
            placeholder="Elige un acuífero...",
            on_change=_on_acuifero_change_mc,
        )

clave_actual = st.session_state.get("clave_mc")
nombre_actual = st.session_state.get("nombre_mc")
area_actual = st.session_state.get("area_total_mc", 0.0)

if not clave_actual or not nombre_actual:
    st.info("👆 Selecciona un Acuífero arriba o carga puntos/CSV en la barra lateral para comenzar.")
    st.stop()

coincidencias = (
    gdf_m[normalizar_serie_clave(gdf_m["CLV_ACUI"]) == normalizar_clave(clave_actual)]
    if gdf_m is not None
    else None
)
if coincidencias is None or coincidencias.empty:
    st.error(f"No se localizó la geometría espacial del acuífero {clave_actual}.")
    st.stop()

datos_ac = coincidencias.iloc[0]
geom_ac = datos_ac.geometry
minx, miny, maxx, maxy = geom_ac.bounds
centro_lon = (minx + maxx) / 2.0
centro_lat = (miny + maxy) / 2.0

# =======================================================
# 🛰️ 6. PIPELINE TOPOGRÁFICO GEORREFERENCIADO (EPSG:3857 -> EPSG:4326, SIN BATIMETRÍA)
# =======================================================
def deg2num(lat_deg: float, lon_deg: float, zoom: int):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def contar_teselas(bounds, zoom: int) -> int:
    minx_b, miny_b, maxx_b, maxy_b = bounds
    x0, y0 = deg2num(maxy_b, minx_b, zoom)
    x1, y1 = deg2num(miny_b, maxx_b, zoom)
    return (x1 - x0 + 1) * (y1 - y0 + 1)


def zoom_para_limite(bounds, zoom: int, max_teselas: int = MAX_TESELAS_DEM, zoom_min: int = 8) -> int:
    """Baja el zoom hasta que el número de teselas no supere el tope (protege la memoria)."""
    while zoom > zoom_min and contar_teselas(bounds, zoom) > max_teselas:
        zoom -= 1
    return zoom


def zoom_de_ruta(ruta) -> int:
    m = re.search(r"_z(\d+)$", Path(ruta).stem)
    return int(m.group(1)) if m else 12


def resolucion_dem_m(zoom: int, lat: float) -> float:
    """Tamaño aproximado de píxel (m) de una tesela de 256 px a esa latitud."""
    return 156543.03392 * math.cos(math.radians(lat)) / (2.0 ** zoom)


def _descargar_tesela_terrarium(session: requests.Session, x: int, y: int, zoom_level: int):
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom_level}/{x}/{y}.png"
    for intento in range(3):
        try:
            r = session.get(url, timeout=10)
            if r.status_code == 200:
                img = Image.open(io.BytesIO(r.content)).convert("RGB")
                arr = np.asarray(img, dtype=np.float32)
                elev = (arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0) - 32768.0
                return (x, y, elev)
            if r.status_code == 404:
                break
        except Exception:
            pass
        time.sleep(0.4 * (intento + 1))
    return (x, y, None)


def obtener_o_generar_dem_acuifero(geom_acuifero, clave_ac: str, zoom_level: int = 12) -> Path:
    """Descarga el DEM en EPSG:3857, filtra batimetría oceánica y reproyecta exactamente a EPSG:4326."""
    import rasterio
    import rasterio.mask
    from rasterio.transform import from_bounds
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    zoom_level = zoom_para_limite(geom_acuifero.bounds, zoom_level)
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_dem"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_tif = carpeta_cache / f"DEM_{clave_ac}_z{zoom_level}.tif"
    ruta_ok = ruta_tif.with_suffix(".ok")

    if ruta_tif.exists() and ruta_ok.exists():
        try:
            if ruta_ok.read_text(encoding="utf-8").strip() == DEM_CACHE_VERSION:
                return ruta_tif
        except OSError:
            pass

    bx0, by0, bx1, by1 = geom_acuifero.bounds
    x_start, y_start = deg2num(by1, bx0, zoom_level)
    x_end, y_end = deg2num(by0, bx1, zoom_level)

    num_x = (x_end - x_start) + 1
    num_y = (y_end - y_start) + 1
    malla_3857 = np.full((num_y * 256, num_x * 256), -9999.0, dtype=np.float32)

    tareas = [(x, y) for y in range(y_start, y_end + 1) for x in range(x_start, x_end + 1)]
    fallidas = 0
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(_descargar_tesela_terrarium, session, x, y, zoom_level) for x, y in tareas]
            for fut in futures:
                x, y, elev = fut.result()
                if elev is None:
                    fallidas += 1
                    continue
                malla_3857[
                    (y - y_start) * 256 : (y - y_start + 1) * 256,
                    (x - x_start) * 256 : (x - x_start + 1) * 256,
                ] = elev
    finally:
        session.close()

    if fallidas:
        raise RuntimeError(
            f"No se pudieron descargar {fallidas} de {len(tareas)} teselas de elevación. Intenta de nuevo en unos minutos."
        )

    # 1. Filtrar batimetría oceánica y huecos SRTM (< -12 msnm)
    malla_3857[malla_3857 < MIN_TERRESTRIAL_ELEV_M] = -9999.0

    # 2. Transformación lineal exacta en EPSG:3857 (Web Mercator)
    n_tiles = 2.0 ** zoom_level
    tile_m = (2.0 * ORIGIN_SHIFT_3857) / n_tiles
    west_3857 = -ORIGIN_SHIFT_3857 + x_start * tile_m
    east_3857 = -ORIGIN_SHIFT_3857 + (x_end + 1) * tile_m
    north_3857 = ORIGIN_SHIFT_3857 - y_start * tile_m
    south_3857 = ORIGIN_SHIFT_3857 - (y_end + 1) * tile_m
    transform_3857 = from_bounds(west_3857, south_3857, east_3857, north_3857, malla_3857.shape[1], malla_3857.shape[0])

    # 3. Recortar primero en EPSG:3857 (reduce drásticamente los píxeles a reproyectar)
    tr_to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    geom_3857 = shapely_transform(tr_to_3857.transform, geom_acuifero).buffer(tile_m * 0.05)

    with rasterio.MemoryFile() as mem_src:
        with mem_src.open(
            driver="GTiff",
            height=malla_3857.shape[0],
            width=malla_3857.shape[1],
            count=1,
            dtype="float32",
            crs="EPSG:3857",
            transform=transform_3857,
            nodata=-9999.0,
        ) as ds_3857:
            ds_3857.write(malla_3857, 1)
            crop_3857, crop_trans_3857 = rasterio.mask.mask(
                ds_3857,
                [geom_3857.__geo_interface__],
                crop=True,
                all_touched=True,
                nodata=-9999.0,
            )

    del malla_3857  # liberar RAM de inmediato

    # 4. Reproyectar el recorte EPSG:3857 -> EPSG:4326 con exactitud geodésica
    src_h, src_w = crop_3857.shape[1], crop_3857.shape[2]
    src_bounds = rasterio.transform.array_bounds(src_h, src_w, crop_trans_3857)
    dst_transform, dst_w, dst_h = calculate_default_transform(
        "EPSG:3857", "EPSG:4326", src_w, src_h, *src_bounds
    )
    arr_4326 = np.full((dst_h, dst_w), -9999.0, dtype=np.float32)
    reproject(
        source=crop_3857[0],
        destination=arr_4326,
        src_transform=crop_trans_3857,
        src_crs="EPSG:3857",
        src_nodata=-9999.0,
        dst_transform=dst_transform,
        dst_crs="EPSG:4326",
        dst_nodata=-9999.0,
        resampling=Resampling.bilinear,
    )
    arr_4326[arr_4326 < MIN_TERRESTRIAL_ELEV_M] = -9999.0

    # 5. Recorte final nítido en EPSG:4326 al límite oficial del acuífero y guardado comprimido
    with rasterio.MemoryFile() as mem_4326:
        with mem_4326.open(
            driver="GTiff",
            height=dst_h,
            width=dst_w,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=dst_transform,
            nodata=-9999.0,
        ) as ds_4326:
            ds_4326.write(arr_4326, 1)
            out_img, out_trans = rasterio.mask.mask(
                ds_4326,
                [geom_acuifero.__geo_interface__],
                crop=True,
                nodata=-9999.0,
            )
            meta = ds_4326.meta.copy()

    # Asegurar que si un acuífero costero quedó con todos los píxeles filtrados por error de costa, al menos no colapse
    valid_check = (out_img[0] != -9999.0) & (~np.isnan(out_img[0]))
    if not np.any(valid_check):
        from rasterio.features import geometry_mask

        dentro_mask = geometry_mask(
            [geom_acuifero.__geo_interface__],
            out_shape=out_img[0].shape,
            transform=out_trans,
            invert=True,
        )
        out_img[0] = np.where(dentro_mask, 0.0, -9999.0).astype(np.float32)

    meta.update({
        "height": out_img.shape[1],
        "width": out_img.shape[2],
        "transform": out_trans,
        "nodata": -9999.0,
        "compress": "deflate",
        "predictor": 3,
    })
    ruta_tmp = ruta_tif.with_suffix(f".tmp_{os.getpid()}_{threading.get_ident()}.tif")
    with rasterio.open(ruta_tmp, "w", **meta) as dst:
        dst.write(out_img)
    os.replace(ruta_tmp, ruta_tif)
    ruta_ok.write_text(DEM_CACHE_VERSION, encoding="utf-8")
    return ruta_tif


with st.spinner("Sincronizando topografía georreferenciada (AWS Terrain / SRTM · EPSG:4326)..."):
    try:
        ruta_dem_local = obtener_o_generar_dem_acuifero(geom_ac, clave_actual, zoom_level=12)
    except Exception as e:
        st.error(f"Error cargando DEM: {e}")
        ruta_dem_local = None

if ruta_dem_local is None or not ruta_dem_local.exists():
    st.warning("No se pudo construir el modelo digital de elevación; el visor 3D no está disponible por ahora.")
    st.stop()

dem_mtime = ruta_dem_local.stat().st_mtime
zoom_dem_efectivo = zoom_de_ruta(ruta_dem_local)
res_dem_efectiva_m = resolucion_dem_m(zoom_dem_efectivo, centro_lat)


@st.cache_data(show_spinner=False, max_entries=8, ttl=3600)
def analizar_dem_resumen(ruta_tif: str, mtime: float) -> dict:
    """Calcula estadísticas exactas del DEM completo (sin submuestreo) y paso óptimo de curvas."""
    import rasterio

    with rasterio.open(ruta_tif) as src:
        z = src.read(1)
        nodata = src.nodata
        mask = (z != nodata) & (~np.isnan(z)) & (z >= MIN_TERRESTRIAL_ELEV_M)
        if not np.any(mask):
            vmin, vmax = 0.0, 100.0
        else:
            vals = z[mask]
            vmin = float(np.min(vals))
            vmax = float(np.max(vals))
        desnivel = max(vmax - vmin, 1.0)
        if desnivel <= 60.0:
            intervalo_base = 5
            paso_inicial = 10
            max_slider = 50
        elif desnivel <= 250.0:
            intervalo_base = 10
            paso_inicial = 20
            max_slider = 100
        else:
            intervalo_base = 25
            paso_inicial = 50
            max_slider = 250

        lat_c = (src.bounds.top + src.bounds.bottom) / 2.0
        lon_c = (src.bounds.left + src.bounds.right) / 2.0
        _, _, width_m = GEOD_WGS84.inv(src.bounds.left, lat_c, src.bounds.right, lat_c)
        _, _, height_m = GEOD_WGS84.inv(lon_c, src.bounds.bottom, lon_c, src.bounds.top)
        px_m = width_m / max(src.width, 1)

        return {
            "vmin": vmin,
            "vmax": vmax,
            "desnivel": desnivel,
            "width": int(src.width),
            "height": int(src.height),
            "width_m": float(width_m),
            "height_m": float(height_m),
            "px_m": float(px_m),
            "bounds": [float(src.bounds.left), float(src.bounds.bottom), float(src.bounds.right), float(src.bounds.top)],
            "intervalo_base": int(intervalo_base),
            "paso_inicial": int(paso_inicial),
            "max_slider": int(max_slider),
        }


dem_stats = analizar_dem_resumen(str(ruta_dem_local), dem_mtime)


@st.cache_data(show_spinner=False, max_entries=8, ttl=3600)
def generar_curvas_nivel_base_geojson(ruta_tif: str, intervalo_base: int = 25, mtime: float = 0.0) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import rasterio

    try:
        with rasterio.open(ruta_tif) as src:
            z = src.read(1)
            mask = (z != src.nodata) & (~np.isnan(z)) & (z >= MIN_TERRESTRIAL_ELEV_M)
            if not np.any(mask):
                return "{}"

            vmin = float(np.min(z[mask]))
            vmax = float(np.max(z[mask]))
            niveles = np.arange(
                math.floor(vmin / intervalo_base) * intervalo_base,
                math.ceil(vmax / intervalo_base) * intervalo_base + intervalo_base,
                intervalo_base,
            )
            if len(niveles) == 0:
                return "{}"

            h_full, w_full = z.shape
            escala_c = min(1.0, 400.0 / max(h_full, w_full))
            target_h = min(h_full, max(2, int(round(h_full * escala_c))))
            target_w = min(w_full, max(2, int(round(w_full * escala_c))))
            row_idx = np.unique(np.round(np.linspace(0, h_full - 1, target_h)).astype(int))
            col_idx = np.unique(np.round(np.linspace(0, w_full - 1, target_w)).astype(int))
            z_sub = np.ma.masked_where(~mask[np.ix_(row_idx, col_idx)], z[np.ix_(row_idx, col_idx)])
            # Coordenadas exactas del centro de cada píxel (estándar GDAL / ArcGIS / QGIS, 0 m estiramiento)
            tr = src.transform
            x_lin = tr.c + (col_idx + 0.5) * tr.a
            y_lin = tr.f + (row_idx + 0.5) * tr.e

            fig, ax = plt.subplots()
            cs = ax.contour(x_lin, y_lin, z_sub, levels=niveles)
            plt.close(fig)

            features = []
            for level, segs in zip(cs.levels, cs.allsegs):
                cota_val = int(round(float(level)))
                for seg in segs:
                    if len(seg) >= 3:
                        coords = [[round(float(pt[0]), 5), round(float(pt[1]), 5)] for pt in seg]
                        features.append({
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": coords},
                            "properties": {"cota": cota_val},
                        })
            return _json_seguro(json.dumps({"type": "FeatureCollection", "features": features}))
    except Exception:
        logger.exception("Error generando curvas de nivel para %s", ruta_tif)
        return "{}"


geojson_curvas_cota = generar_curvas_nivel_base_geojson(
    str(ruta_dem_local),
    intervalo_base=dem_stats["intervalo_base"],
    mtime=dem_mtime,
)

# =======================================================
# 📂 7. CAPA VECTORIAL SGM (STREAMING PYARROW BAJA RAM + CACHÉ LIMPIO)
# =======================================================
def _recortar_parquet_streaming(ruta_pq: Path, geom_4326, batch_size: int = 4096) -> gpd.GeoDataFrame:
    """Recorta un GeoParquet nacional pesado por lotes sin cargar todo el archivo a RAM."""
    pf = pq.ParquetFile(ruta_pq)
    crs_pq = "EPSG:4326"
    try:
        geo_meta_raw = pf.schema_arrow.metadata.get(b"geo") if pf.schema_arrow.metadata else None
        if geo_meta_raw:
            geo_meta = json.loads(geo_meta_raw.decode("utf-8"))
            primary = geo_meta.get("primary_column", "geometry")
            crs_info = geo_meta.get("columns", {}).get(primary, {}).get("crs")
            if crs_info:
                crs_pq = crs_info
    except Exception:
        pass

    geom_consulta = geom_4326
    necesita_reproy = False
    try:
        from pyproj import CRS
        crs_obj = CRS.from_user_input(crs_pq)
        if crs_obj.to_epsg() != 4326:
            tr = Transformer.from_crs("EPSG:4326", crs_obj, always_xy=True)
            geom_consulta = shapely_transform(tr.transform, geom_4326)
            necesita_reproy = True
    except Exception:
        pass

    shapely.prepare(geom_consulta)
    partes = []
    for batch in pf.iter_batches(batch_size=batch_size):
        b_df = batch.to_pandas()
        if "geometry" not in b_df.columns or b_df.empty:
            continue
        geoms = shapely.from_wkb(b_df["geometry"].to_numpy())
        mask = shapely.intersects(geom_consulta, geoms)
        if np.any(mask):
            sub = b_df.loc[mask].copy()
            sub["geometry"] = geoms[mask]
            partes.append(sub)

    if not partes:
        return gpd.GeoDataFrame()

    gdf_cand = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), geometry="geometry", crs=crs_pq)
    recorte = gdf_cand.clip(geom_consulta)
    if necesita_reproy and not recorte.empty:
        recorte = recorte.to_crs(epsg=4326)
    return recorte


def _tiene_mojibake(gdf: gpd.GeoDataFrame) -> bool:
    for col in gdf.select_dtypes(include=["object", "string"]).columns:
        if col == "geometry":
            continue
        if gdf[col].dropna().astype(str).str.contains("Ã|Â", regex=True).any():
            return True
    return False


@st.cache_data(show_spinner=False, max_entries=8, ttl=3600)
def preparar_geologia_vectorial(clave_ac: str, _geom_4326):
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_geologia"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_cache_parquet = carpeta_cache / f"GEO_SHP_{clave_ac}.parquet"
    ruta_cache_ver = carpeta_cache / f"GEO_SHP_{clave_ac}.ver"

    # 1. Ruta rápida de caché (solo si conserva 100 % de vértices oficiales sin simplificación previa)
    cache_version_ok = (
        ruta_cache_ver.exists()
        and ruta_cache_ver.read_text(encoding="utf-8").strip() == GEO_CACHE_VERSION
    )
    if cache_version_ok and ruta_cache_parquet.exists() and ruta_cache_parquet.stat().st_size > 2000:
        try:
            gdf_cached = gpd.read_parquet(ruta_cache_parquet)
            cols_req = {"COLOR_HEX", "ETIQUETA_LITO", "geometry"}
            if len(gdf_cached.columns) > 3 and cols_req.issubset(gdf_cached.columns) and not _tiene_mojibake(gdf_cached):
                cols_u = [c.upper() for c in gdf_cached.columns]
                col_sel = (
                    gdf_cached.columns[cols_u.index("CLAVE_SGM")]
                    if "CLAVE_SGM" in cols_u
                    else gdf_cached.columns[cols_u.index("ETIQUETA_LITO")]
                )
                # Recalcular colores en memoria con la regla corregida O(1) (no modifica geometría ni disco)
                lito_col = "LITOLOGIA" if "LITOLOGIA" in gdf_cached.columns else None
                roca_col = "ROCA" if "ROCA" in gdf_cached.columns else None
                gdf_cached["COLOR_HEX"] = [
                    resolver_color_oficial(c, l, r)
                    for c, l, r in zip(
                        gdf_cached[col_sel],
                        gdf_cached[lito_col] if lito_col else [""] * len(gdf_cached),
                        gdf_cached[roca_col] if roca_col else [""] * len(gdf_cached),
                    )
                ]
                dic_leyenda = dict(
                    zip(
                        gdf_cached[col_sel].astype(str).str.strip(),
                        gdf_cached["COLOR_HEX"].astype(str),
                    )
                )
                return gdf_cached, dic_leyenda, col_sel
        except Exception:
            logger.warning("Caché de geología %s corrupto; se regenerará.", ruta_cache_parquet)

    # 2. Recorte en streaming desde data/geologia (nunca escanea Downloads)
    gdf_sgm = None
    carpeta_geo = DIRECTORIO_RAIZ / "data" / "geologia"
    if carpeta_geo.exists():
        for pq_p in sorted(carpeta_geo.glob("*.parquet")):
            nom_l = pq_p.name.lower()
            if any(k in nom_l for k in ("lito", "geo", "cnal")) and "estructura" not in nom_l:
                try:
                    recorte = _recortar_parquet_streaming(pq_p, _geom_4326, batch_size=4096)
                    if not recorte.empty:
                        gdf_sgm = recorte
                        break
                except Exception:
                    logger.exception("Error recortando %s", pq_p.name)

    if gdf_sgm is None or gdf_sgm.empty:
        return None, {}, "Ninguna"

    # 3. Limpiar geometrías, reparar mojibake y resolver colorimetría SGM (una sola vez)
    gdf_sgm = _extraer_geometrias_por_familia(gdf_sgm, "polygon")
    if gdf_sgm.empty:
        return None, {}, "Ninguna"

    for col in gdf_sgm.select_dtypes(include=["object", "string"]).columns:
        if col != "geometry":
            gdf_sgm[col] = gdf_sgm[col].apply(_reparar_texto_mojibake)

    cols_upper = [c.upper() for c in gdf_sgm.columns]
    if "CLAVE_SGM" in cols_upper:
        col_sel = gdf_sgm.columns[cols_upper.index("CLAVE_SGM")]
    elif "CLAVE" in cols_upper:
        col_sel = gdf_sgm.columns[cols_upper.index("CLAVE")]
    elif "LITOLOGIA" in cols_upper:
        col_sel = gdf_sgm.columns[cols_upper.index("LITOLOGIA")]
    else:
        col_sel = gdf_sgm.columns[0]

    lito_vals = gdf_sgm["LITOLOGIA"] if "LITOLOGIA" in gdf_sgm.columns else [""] * len(gdf_sgm)
    roca_vals = gdf_sgm["ROCA"] if "ROCA" in gdf_sgm.columns else [""] * len(gdf_sgm)
    colores_asignados = [
        resolver_color_oficial(c, l, r)
        for c, l, r in zip(gdf_sgm[col_sel], lito_vals, roca_vals)
    ]
    gdf_sgm["COLOR_HEX"] = colores_asignados
    gdf_sgm["ETIQUETA_LITO"] = gdf_sgm[col_sel].astype(str).str.strip()
    dic_leyenda = dict(zip(gdf_sgm["ETIQUETA_LITO"], gdf_sgm["COLOR_HEX"]))

    # Fidelidad geométrica 100 % sin simplificación para caché oficial y exportaciones Shapefile/KMZ
    try:
        ruta_tmp_pq = ruta_cache_parquet.with_suffix(f".tmp_{os.getpid()}_{threading.get_ident()}.parquet")
        gdf_sgm.to_parquet(ruta_tmp_pq)
        os.replace(ruta_tmp_pq, ruta_cache_parquet)
        ruta_cache_ver.write_text(GEO_CACHE_VERSION, encoding="utf-8")
    except Exception:
        logger.warning("No se pudo guardar caché de geología %s", ruta_cache_parquet)

    return gdf_sgm, dic_leyenda, col_sel


@st.cache_data(show_spinner=False, max_entries=8, ttl=3600)
def obtener_estructuras_50k(clave_ac: str, _geom_4326):
    carpeta_cache = DIRECTORIO_RAIZ / "data" / "cache_geologia"
    carpeta_cache.mkdir(parents=True, exist_ok=True)
    ruta_cache_acuifero = carpeta_cache / f"ESTRUCTURAS_50K_{clave_ac}.parquet"

    if ruta_cache_acuifero.exists():
        try:
            gdf_cached = gpd.read_parquet(ruta_cache_acuifero)
            if any("AZIMUTH" in c.upper() for c in gdf_cached.columns) and not _tiene_mojibake(gdf_cached):
                return _extraer_geometrias_por_familia(gdf_cached, "line")
            ruta_cache_acuifero.unlink()
        except Exception:
            pass

    ruta_nacional = DIRECTORIO_RAIZ / "data" / "geologia" / "Estructuras_Nacional_SGM.parquet"
    if ruta_nacional.exists():
        try:
            recorte = _recortar_parquet_streaming(ruta_nacional, _geom_4326, batch_size=16384)
            recorte = _extraer_geometrias_por_familia(recorte, "line")
            if recorte is not None and not recorte.empty:
                for col in recorte.select_dtypes(include=["object", "string"]).columns:
                    if col != "geometry":
                        recorte[col] = recorte[col].apply(_reparar_texto_mojibake)
                ruta_tmp = ruta_cache_acuifero.with_suffix(f".tmp_{os.getpid()}_{threading.get_ident()}.parquet")
                recorte.to_parquet(ruta_tmp)
                os.replace(ruta_tmp, ruta_cache_acuifero)
                return recorte
        except Exception:
            logger.exception("Error recortando estructuras nacionales para %s", clave_ac)

    return None


gdf_geologia_recortada, dic_leyenda_rocas, col_litologica = preparar_geologia_vectorial(clave_actual, geom_ac)
gdf_estructuras_50k = obtener_estructuras_50k(clave_actual, geom_ac)


@st.cache_data(show_spinner=False, max_entries=8, ttl=3600)
def _geologia_a_json(_gdf, clave: str, n_filas: int) -> str:
    cols_visor = [
        c
        for c in ["CLAVE_SGM", "ETIQUETA_LITO", "COLOR_HEX", "FORMACION", "LITOLOGIA", "ROCA", "PERIODO", "EDINICIO", "EDFINAL", "ERA", "geometry"]
        if c in _gdf.columns
    ]
    gdf_visor = _gdf[cols_visor].copy()
    # Si un acuífero muy extenso excede 60k vértices, se optimiza SOLO el GeoJSON visual web
    # sin alterar nunca el caché oficial ni las exportaciones Shapefile / KMZ.
    try:
        n_coords = int(shapely.get_num_coordinates(gdf_visor.geometry).sum())
        if n_coords > 60000:
            gdf_visor["geometry"] = gdf_visor.geometry.simplify(tolerance=0.00008, preserve_topology=True)
    except Exception:
        pass
    for col in gdf_visor.select_dtypes(include=["object", "string"]).columns:
        gdf_visor[col] = (
            gdf_visor[col]
            .fillna("")
            .astype(str)
            .str.replace("\n", " ", regex=False)
            .str.replace("\r", "", regex=False)
        )
    return _json_seguro(gdf_visor.to_json())


@st.cache_data(show_spinner=False, max_entries=8, ttl=3600)
def _gdf_a_json_cache(_gdf, clave: str, capa: str, n_filas: int) -> str:
    return _json_seguro(_gdf.to_json())


@st.cache_data(show_spinner=False, max_entries=8, ttl=3600)
def _borde_a_json(clave: str, _geom) -> str:
    gdf_borde = gpd.GeoDataFrame(geometry=[_geom], crs="EPSG:4326")
    return _json_seguro(gdf_borde.to_json())


geojson_borde = _borde_a_json(clave_actual, geom_ac)
geojson_geologia = (
    _geologia_a_json(gdf_geologia_recortada, clave_actual, len(gdf_geologia_recortada))
    if gdf_geologia_recortada is not None and not gdf_geologia_recortada.empty
    else "{}"
)
geojson_estructuras = (
    _gdf_a_json_cache(gdf_estructuras_50k, clave_actual, "estructuras", len(gdf_estructuras_50k))
    if gdf_estructuras_50k is not None and not gdf_estructuras_50k.empty
    else "{}"
)

def _enriquecer_pozos_con_cota_geotiff(lista_pozos: list, ruta_tif: Path) -> list:
    """Extrae la cota exacta (interpolación bilineal) desde el GeoTIFF completo (equivalente a Extract Values to Points)."""
    if not lista_pozos or not ruta_tif or not ruta_tif.exists():
        return lista_pozos
    import rasterio

    enriquecidos = []
    try:
        with rasterio.open(ruta_tif) as src:
            tr = src.transform
            inv_tr = ~tr
            h, w = src.height, src.width
            nodata = src.nodata
            z_band = None  # lectura perezosa solo si algún pozo cae dentro del GeoTIFF
            for p in lista_pozos:
                q = dict(p)
                q["cota_geotiff"] = None
                lon, lat = q["lon"], q["lat"]
                if src.bounds.left <= lon <= src.bounds.right and src.bounds.bottom <= lat <= src.bounds.top:
                    if z_band is None:
                        z_band = src.read(1)
                    col_f, row_f = inv_tr * (lon, lat)
                    cf = col_f - 0.5
                    rf = row_f - 0.5
                    if -0.5 <= cf <= w - 0.5 and -0.5 <= rf <= h - 0.5:
                        cf_c = max(0.0, min(float(w - 1), cf))
                        rf_c = max(0.0, min(float(h - 1), rf))
                        r0, c0 = int(math.floor(rf_c)), int(math.floor(cf_c))
                        r1, c1 = min(h - 1, r0 + 1), min(w - 1, c0 + 1)
                        fr, fc = rf_c - r0, cf_c - c0
                        vecinos = [
                            (float(z_band[r0, c0]), (1.0 - fr) * (1.0 - fc)),
                            (float(z_band[r1, c0]), fr * (1.0 - fc)),
                            (float(z_band[r0, c1]), (1.0 - fr) * fc),
                            (float(z_band[r1, c1]), fr * fc),
                        ]
                        validos = [
                            (zv, wv)
                            for zv, wv in vecinos
                            if zv != nodata and not math.isnan(zv) and zv >= MIN_TERRESTRIAL_ELEV_M
                        ]
                        if validos:
                            sw = sum(wv for _, wv in validos)
                            val_msnm = sum(zv * wv for zv, wv in validos) / sw if sw > 0 else validos[0][0]
                            q["cota_geotiff"] = round(val_msnm, 1)
                enriquecidos.append(q)
    except Exception:
        logger.exception("Error muestreando cotas de pozos sobre GeoTIFF")
        return lista_pozos
    return enriquecidos


# Filtrar pozos para el bloque 3D aislado y enriquecer con cota exacta del GeoTIFF completo
todos_pozos_validos = _enriquecer_pozos_con_cota_geotiff(
    _pozos_para_visor(st.session_state.get("lista_marcadores", [])),
    ruta_dem_local,
)
b_l, b_b, b_r, b_t = dem_stats["bounds"]
pozos_en_acuifero = [
    p for p in todos_pozos_validos if (b_l <= p["lon"] <= b_r and b_b <= p["lat"] <= b_t)
]
n_pozos_fuera = len(todos_pozos_validos) - len(pozos_en_acuifero)
pozos_aislado_json = _json_seguro(json.dumps(pozos_en_acuifero))
pozos_mapa_json = _json_seguro(json.dumps(todos_pozos_validos))
leyenda_sgm_json = _json_seguro(json.dumps(sorted(dic_leyenda_rocas.items())))
acuifero_meta_json = _json_seguro(json.dumps({
    "clave": str(clave_actual),
    "nombre": str(nombre_actual),
    "area_km2": round(float(area_actual), 1),
    "vmin": round(dem_stats["vmin"], 1),
    "vmax": round(dem_stats["vmax"], 1),
    "px_m": round(dem_stats["px_m"], 0),
    "zoom_dem": int(zoom_dem_efectivo),
}))

# =======================================================
# 💾 8. EXPORTACIONES SIG BLINDADAS Y BAJO DEMANDA (0 ms AL CARGAR)
# =======================================================
@st.cache_data(show_spinner=False, max_entries=4, ttl=1800)
def exportar_shapefile_zip(_gdf_origen, base_name: str, familia: str = "polygon") -> bytes:
    if _gdf_origen is None or _gdf_origen.empty:
        return b""
    try:
        gdf = _gdf_origen.copy()
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)
        else:
            gdf = gdf.to_crs(epsg=4326)

        gdf = _extraer_geometrias_por_familia(gdf, familia)
        if gdf.empty:
            return b""

        # Truncar nombres a 10 caracteres (límite DBF de ESRI Shapefile)
        cols_map, cols_usadas = {}, set()
        for col in gdf.columns:
            if col == "geometry":
                continue
            c_clean = re.sub(r"[^A-Za-z0-9_]", "", str(col).upper())[:10] or "COL"
            c_final, suf = c_clean, 1
            while c_final in cols_usadas:
                c_final = f"{c_clean[:8]}_{suf}"
                suf += 1
            cols_usadas.add(c_final)
            cols_map[col] = c_final

        gdf = gdf.rename(columns=cols_map)

        for col in gdf.columns:
            if col == "geometry":
                continue
            if pd.api.types.is_object_dtype(gdf[col]) or pd.api.types.is_string_dtype(gdf[col]):
                gdf[col] = gdf[col].fillna("").astype(str)
            elif pd.api.types.is_numeric_dtype(gdf[col]) and not pd.api.types.is_bool_dtype(gdf[col]):
                gdf[col] = gdf[col].fillna(0)

        with tempfile.TemporaryDirectory() as tmpdir:
            shp_path = os.path.join(tmpdir, f"{base_name}.shp")
            gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="utf-8")

            prj_path = os.path.join(tmpdir, f"{base_name}.prj")
            if not os.path.exists(prj_path):
                with open(prj_path, "w", encoding="utf-8") as f_prj:
                    f_prj.write(
                        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
                        'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
                        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
                    )

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in os.listdir(tmpdir):
                    zf.write(os.path.join(tmpdir, fname), arcname=fname)
            return buf.getvalue()
    except Exception:
        logger.exception("Error exportando Shapefile %s", base_name)
        return b""


def hex_to_kml_color(hex_str, alpha: str = "cc") -> str:
    """Convierte color HEX (#RRGGBB) a formato KML (AABBGGRR)."""
    s = str(hex_str or "").strip().lstrip("#")
    if re.fullmatch(r"[0-9A-Fa-f]{6}", s):
        return f"{alpha}{s[4:6]}{s[2:4]}{s[0:2]}".lower()
    return f"{alpha}cccccc"


def _polygon_a_kml(poly) -> str:
    partes = [
        "<Polygon>\n<tessellate>1</tessellate>\n<outerBoundaryIs><LinearRing><coordinates>",
        " ".join(f"{c[0]:.6f},{c[1]:.6f}" for c in poly.exterior.coords),
        "</coordinates></LinearRing></outerBoundaryIs>\n",
    ]
    for interior in poly.interiors:
        partes.append("<innerBoundaryIs><LinearRing><coordinates>")
        partes.append(" ".join(f"{c[0]:.6f},{c[1]:.6f}" for c in interior.coords))
        partes.append("</coordinates></LinearRing></innerBoundaryIs>\n")
    partes.append("</Polygon>\n")
    return "".join(partes)


@st.cache_data(show_spinner=False, max_entries=4, ttl=1800)
def exportar_kmz_geologia(_gdf_origen, base_name: str) -> bytes:
    if _gdf_origen is None or _gdf_origen.empty:
        return b""
    try:
        gdf = _gdf_origen.copy()
        if gdf.crs is None:
            gdf = gdf.set_crs(epsg=4326)
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        gdf = _extraer_geometrias_por_familia(gdf, "polygon")
        if gdf.empty:
            return b""

        partes_kml = [
            '<?xml version="1.0" encoding="UTF-8"?>\n',
            '<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n',
            f"<name>{_xml_escape(str(base_name))}</name>\n",
        ]

        # Estilos únicos
        colores_vistos = set()
        if "COLOR_HEX" in gdf.columns:
            for c in gdf["COLOR_HEX"].dropna().astype(str).unique():
                c_clean = c.strip() if re.fullmatch(r"#[0-9A-Fa-f]{6}", c.strip()) else "#cccccc"
                if c_clean not in colores_vistos:
                    colores_vistos.add(c_clean)
                    sid = f"style_{c_clean.lstrip('#').lower()}"
                    partes_kml.append(
                        f'<Style id="{sid}"><LineStyle><color>ff333333</color><width>1.5</width></LineStyle>'
                        f'<PolyStyle><color>{hex_to_kml_color(c_clean, "cc")}</color></PolyStyle></Style>\n'
                    )
        if "#cccccc" not in colores_vistos:
            partes_kml.append(
                '<Style id="style_cccccc"><LineStyle><color>ff333333</color><width>1.5</width></LineStyle>'
                '<PolyStyle><color>cccccccc</color></PolyStyle></Style>\n'
            )

        attr_cols = [c for c in gdf.columns if c not in ("geometry", "COLOR_HEX", "ETIQUETA_LITO")]

        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            raw_col = row.get("COLOR_HEX")
            color = str(raw_col).strip() if pd.notna(raw_col) and re.fullmatch(r"#[0-9A-Fa-f]{6}", str(raw_col).strip()) else "#cccccc"
            style_id = f"style_{color.lstrip('#').lower()}"

            raw_name = row.get("ETIQUETA_LITO") or row.get("CLAVE_SGM") or "Polígono"
            name_xml = _xml_escape(str(raw_name))

            filas_html = [
                "<table border='1' cellpadding='4' style='border-collapse:collapse; width:100%; font-family:sans-serif; font-size:12px;'>",
                f"<tr style='background-color:{color}; color:#111;'><th colspan='2'>Atributos Geológicos</th></tr>",
            ]
            for col in attr_cols:
                val = row[col]
                if pd.notna(val) and str(val).strip() != "":
                    filas_html.append(
                        f"<tr><td style='background-color:#f2f2f2; font-weight:bold;'>{_html.escape(str(col))}</td>"
                        f"<td>{_html.escape(str(val))}</td></tr>"
                    )
            filas_html.append("</table>")
            desc_html = "".join(filas_html).replace("]]>", "]]]]><![CDATA[>")

            if geom.geom_type == "Polygon":
                geom_kml = _polygon_a_kml(geom)
            elif geom.geom_type == "MultiPolygon":
                geom_kml = "<MultiGeometry>\n" + "".join(_polygon_a_kml(poly) for poly in geom.geoms) + "</MultiGeometry>\n"
            else:
                continue

            partes_kml.append(
                f"<Placemark>\n<name>{name_xml}</name>\n<styleUrl>#{style_id}</styleUrl>\n"
                f"<description><![CDATA[{desc_html}]]></description>\n{geom_kml}</Placemark>\n"
            )

        partes_kml.append("</Document>\n</kml>")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doc.kml", "".join(partes_kml).encode("utf-8"))
        return buf.getvalue()
    except Exception:
        logger.exception("Error exportando KMZ %s", base_name)
        return b""


# Botones de exportación SIG oficial bajo demanda (callable + on_click="ignore")
st.sidebar.markdown("---")
st.sidebar.subheader("💾 Exportación SIG Oficial")

st.sidebar.download_button(
    label=f"💾 Descargar GeoTIFF (~{dem_stats['px_m']:.0f} m · z{zoom_dem_efectivo})",
    data=lambda r=ruta_dem_local: r.read_bytes(),
    file_name=f"DEM_Acuifero_{clave_actual}_z{zoom_dem_efectivo}.tif",
    mime="image/tiff",
    type="secondary",
    width="stretch",
    on_click="ignore",
)

if gdf_geologia_recortada is not None and not gdf_geologia_recortada.empty:
    st.sidebar.download_button(
        label="📦 Descargar Geología Shapefile (.zip)",
        data=lambda g=gdf_geologia_recortada, c=clave_actual: exportar_shapefile_zip(g, f"Geologia_{c}", "polygon"),
        file_name=f"Geologia_Shapefile_{clave_actual}.zip",
        mime="application/zip",
        type="secondary",
        width="stretch",
        on_click="ignore",
    )
    st.sidebar.download_button(
        label="🌍 Descargar Geología Google Earth (.kmz)",
        data=lambda g=gdf_geologia_recortada, c=clave_actual: exportar_kmz_geologia(g, f"Geologia_{c}"),
        file_name=f"Geologia_GoogleEarth_{clave_actual}.kmz",
        mime="application/vnd.google-earth.kmz",
        type="secondary",
        width="stretch",
        on_click="ignore",
    )
    st.sidebar.download_button(
        label="📄 Descargar Atributos Geología (CSV)",
        data=lambda g=gdf_geologia_recortada: g.drop(columns=["geometry"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
        file_name=f"Atributos_Geologia_{clave_actual}.csv",
        mime="text/csv",
        type="secondary",
        width="stretch",
        on_click="ignore",
    )

if gdf_estructuras_50k is not None and not gdf_estructuras_50k.empty:
    st.sidebar.download_button(
        label="📦 Descargar Fallas Shapefile (.zip)",
        data=lambda g=gdf_estructuras_50k, c=clave_actual: exportar_shapefile_zip(g, f"Estructuras_50k_{c}", "line"),
        file_name=f"Estructuras_50k_{clave_actual}.zip",
        mime="application/zip",
        type="secondary",
        width="stretch",
        on_click="ignore",
    )

# =======================================================
# 📊 9. RESUMEN TÉCNICO DEL ACUÍFERO Y SELECTOR DE MODO
# =======================================================
n_unid_lito = len(dic_leyenda_rocas)
n_estructuras = len(gdf_estructuras_50k) if gdf_estructuras_50k is not None else 0

with st.container(border=True):
    col_b1, col_b2, col_b3, col_b4 = st.columns([0.9, 2.0, 1.1, 1.5])
    col_b1.markdown(
        f"<p style='font-size:11px; color:#64748B; margin:0;'>CLAVE OFICIAL</p>"
        f"<h4 style='color:#691C32; margin:0;'>{_html.escape(str(clave_actual))}</h4>",
        unsafe_allow_html=True,
    )
    col_b2.markdown(
        f"<p style='font-size:11px; color:#64748B; margin:0;'>ACUÍFERO</p>"
        f"<h4 style='color:#691C32; margin:0;'>{_html.escape(str(nombre_actual))}</h4>",
        unsafe_allow_html=True,
    )
    col_b3.markdown(
        f"<p style='font-size:11px; color:#64748B; margin:0;'>SUPERFICIE</p>"
        f"<h4 style='color:#691C32; margin:0;'>{float(area_actual):,.1f} km²</h4>",
        unsafe_allow_html=True,
    )
    col_b4.markdown(
        f"<p style='font-size:11px; color:#64748B; margin:0;'>RELIEVE DEM (~{dem_stats['px_m']:.0f} m · z{zoom_dem_efectivo})</p>"
        f"<div style='font-size:13px; font-weight:700; color:#1E293B; margin-top:2px;'>"
        f"{dem_stats['vmin']:,.0f} a {dem_stats['vmax']:,.0f} msnm "
        f"<span style='color:#64748B; font-weight:500;'>(Δ {dem_stats['desnivel']:,.0f} m)</span></div>"
        f"<div style='font-size:11px; color:#64748B;'>{n_unid_lito} unidades SGM · {n_estructuras:,} estructuras · {len(pozos_en_acuifero)} pozos</div>",
        unsafe_allow_html=True,
    )

if n_pozos_fuera > 0:
    st.caption(
        f"ℹ️ {n_pozos_fuera} de {len(todos_pozos_validos)} punto(s) cargado(s) caen fuera del acuífero activo "
        f"({clave_actual}) y se omiten en el bloque 3D aislado (visibles en el modo Mapa Mundial)."
    )

with st.container(border=True):
    col_m1, col_m2 = st.columns([0.62, 0.38], vertical_alignment="center")
    modo_visualizacion = col_m1.radio(
        "Modo de Visualización Tridimensional:",
        ["🧊 Solo Acuífero (Bloque 3D Aislado)", "🌍 Con Entorno Geográfico (Mapa Mundial)"],
        index=0,
        horizontal=True,
        key="radio_modo_3d",
    )
    if "Aislado" in modo_visualizacion:
        col_m2.info("💡 **Bloque 360° calibrado:** Escala real 1:1 en metros (exageración verdadera), pozos 3D al subsuelo e inspección litológica.")
    else:
        col_m2.info("💡 **Mapa Regional 3D:** Elevación SRTM continua, sombreado solar, fallas 1:50k y coordenadas/cota en vivo.")

# =======================================================
# 🌐 10. PREPARACIÓN CONDICIONAL DE LA MALLA THREE.JS (SOLO EN MODO AISLADO)
# =======================================================
@st.cache_data(show_spinner=False, max_entries=6, ttl=3600)
def preparar_malla_terreno_threejs(ruta_tif: str, mtime: float = 0.0) -> str:
    import rasterio

    with rasterio.open(ruta_tif) as src:
        z = src.read(1)
        nodata = src.nodata
        mask_valida = (z != nodata) & (~np.isnan(z)) & (z >= MIN_TERRESTRIAL_ELEV_M)

        h_full, w_full = z.shape
        escala_m = min(1.0, 220.0 / max(h_full, w_full))
        target_h = min(h_full, max(2, int(round(h_full * escala_m))))
        target_w = min(w_full, max(2, int(round(w_full * escala_m))))
        row_idx = np.unique(np.round(np.linspace(0, h_full - 1, target_h)).astype(int))
        col_idx = np.unique(np.round(np.linspace(0, w_full - 1, target_w)).astype(int))
        z_sub = z[np.ix_(row_idx, col_idx)]
        mask_sub = mask_valida[np.ix_(row_idx, col_idx)]

        vmin = float(np.min(z[mask_valida])) if np.any(mask_valida) else 0.0
        vmax = float(np.max(z[mask_valida])) if np.any(mask_valida) else 100.0
        z_norm = np.where(mask_sub, np.round(z_sub - vmin, 2), -9999.0)

        # Coordenadas exactas de centros de píxel extremos (estándar GDAL/ArcGIS/QGIS, 0 m desfase de ½ píxel)
        tr = src.transform
        lon_min_c = float(tr.c + (int(col_idx[0]) + 0.5) * tr.a)
        lon_max_c = float(tr.c + (int(col_idx[-1]) + 0.5) * tr.a)
        lat_max_c = float(tr.f + (int(row_idx[0]) + 0.5) * tr.e)
        lat_min_c = float(tr.f + (int(row_idx[-1]) + 0.5) * tr.e)

        lat_c = (lat_max_c + lat_min_c) / 2.0
        lon_c = (lon_min_c + lon_max_c) / 2.0
        _, _, width_m = GEOD_WGS84.inv(lon_min_c, lat_c, lon_max_c, lat_c)
        _, _, height_m = GEOD_WGS84.inv(lon_c, lat_min_c, lon_c, lat_max_c)
        px_malla_m = width_m / max(z_norm.shape[1] - 1, 1)

        # Exageración inicial real recomendada: apunta a una altura visual ~10 % del ancho del bloque
        desnivel = max(vmax - vmin, 1.0)
        exag_sugerida = (0.10 * width_m) / desnivel
        exag_inicial = round(max(1.0, min(15.0, exag_sugerida)) * 2.0) / 2.0  # pasos de 0.5x
        exag_max = max(10.0, round(exag_inicial * 3.0))

        payload = {
            "z_grid": z_norm.tolist(),
            "rows": int(z_norm.shape[0]),
            "cols": int(z_norm.shape[1]),
            "vmin": round(vmin, 2),
            "vmax": round(vmax, 2),
            "width_m": round(width_m, 1),
            "height_m": round(height_m, 1),
            "px_malla_m": round(px_malla_m, 1),
            "exag_inicial": exag_inicial,
            "exag_max": exag_max,
            "bounds": [lon_min_c, lat_min_c, lon_max_c, lat_max_c],
        }
        return _json_seguro(json.dumps(payload))


# =======================================================
# 🧊 11A. MOTOR THREE.JS: SOLO ACUÍFERO (BLOQUE AISLADO 360°)
# =======================================================
def construir_html_aislado(malla_json_str: str) -> str:
    int_base = dem_stats["intervalo_base"]
    paso_ini = dem_stats["paso_inicial"]
    max_sl = dem_stats["max_slider"]
    t1, t2, t3, t4 = max_sl // 5, (2 * max_sl) // 5, (3 * max_sl) // 5, (4 * max_sl) // 5

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Bloque Geológico 3D Oficial</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/exporters/GLTFExporter.js"></script>
    <style>
        body {{ margin: 0; padding: 0; overflow: hidden; background: #f8fafc; font-family: 'Segoe UI', Arial, sans-serif; }}
        #container3d {{ width: 100vw; height: 100vh; position: absolute; top: 0; left: 0; }}

        .hud-top {{
            position: absolute; top: 12px; right: 55px; z-index: 1000;
            background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
            padding: 7px 14px; border-radius: 8px; border: 1.5px solid #691C32;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15); font-size: 11px; color: #1e293b;
            display: flex; gap: 14px; align-items: center; pointer-events: none;
        }}
        .hud-top b {{ color: #691C32; margin-right: 3px; }}

        #popup3d {{
            position: absolute; z-index: 2000; display: none;
            background: rgba(255, 255, 255, 0.98); backdrop-filter: blur(10px);
            border-radius: 8px; padding: 10px 14px; border-top: 3.5px solid #691C32;
            box-shadow: 0 8px 24px rgba(0,0,0,0.25); border-left: 1px solid #E2E8F0;
            border-right: 1px solid #E2E8F0; border-bottom: 1px solid #E2E8F0;
            font-size: 11.5px; color: #1E293B; pointer-events: auto; max-width: 285px;
        }}
        .popup-close {{
            float: right; cursor: pointer; color: #888; font-weight: bold; font-size: 14px; margin-left: 10px;
        }}
        .popup-close:hover {{ color: #691C32; }}

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

        .workbench-dock {{
            position: absolute; top: 12px; left: 12px; z-index: 1000;
            background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
            width: 295px; border-radius: 10px; overflow: hidden;
            box-shadow: 0 6px 20px rgba(0,0,0,0.25); border-top: 4px solid #691C32;
            border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0;
            font-size: 11.5px; color: #1E293B;
        }}
        .dock-header {{
            background: #691C32; color: white; padding: 9px 12px;
            font-weight: 700; display: flex; justify-content: space-between; align-items: center;
        }}
        .dock-body {{ padding: 12px 14px; max-height: 82vh; overflow-y: auto; }}
        .dock-section {{ margin-bottom: 11px; }}
        .dock-section label {{ font-weight: 700; color: #475569; display: block; margin-bottom: 5px; font-size: 11px; }}

        .btn-cam-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }}
        .btn-cam {{
            background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px;
            padding: 5px 8px; font-size: 11px; font-weight: 600; color: #334155;
            cursor: pointer; transition: all 0.2s;
        }}
        .btn-cam:hover {{ background: #DDC9A3; color: #691C32; border-color: #691C32; }}

        .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; }}

        .btn-fullscreen-top {{
            position: absolute; top: 12px; right: 12px; z-index: 1000;
            background: #ffffff; width: 32px; height: 32px; border-radius: 4px;
            border: 1px solid #cbd5e1; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; transition: background 0.2s;
        }}
        .btn-fullscreen-top:hover {{ background: #f1f5f9; }}

        .btn-screenshot {{
            width: 100%; background: #691C32; color: white; border: none;
            border-radius: 6px; padding: 8px; font-weight: 700; font-size: 11.5px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            gap: 6px; transition: background 0.2s; box-shadow: 0 2px 6px rgba(105,28,50,0.3);
        }}
        .btn-screenshot:hover {{ background: #88102B; }}

        .btn-tool-sec {{
            width: 100%; background: #f8fafc; color: #334155; border: 1px solid #cbd5e1;
            border-radius: 6px; padding: 7px 8px; font-weight: 700; font-size: 11px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            gap: 6px; transition: all 0.2s; margin-top: 6px;
        }}
        .btn-tool-sec:hover {{ background: #f1f5f9; border-color: #691C32; color: #691C32; }}
        .btn-tool-sec.active {{ background: #691C32; color: #ffffff; border-color: #691C32; }}

        #compass-3d {{
            position: absolute; top: 54px; right: 12px; z-index: 1000;
            width: 54px; height: 54px; border-radius: 50%;
            background: rgba(255,255,255,0.96); border: 1.5px solid #cbd5e1;
            box-shadow: 0 2px 10px rgba(0,0,0,0.14); display: flex;
            align-items: center; justify-content: center; cursor: pointer;
        }}
        #compass-3d:hover {{ border-color: #691C32; }}

        #scale-3d {{
            position: absolute; bottom: 14px; right: 14px; z-index: 1000;
            background: rgba(255,255,255,0.92); padding: 4px 10px 5px 10px;
            border-radius: 6px; border: 1px solid #cbd5e1; font-size: 10px;
            font-weight: 700; color: #334155; pointer-events: none;
            box-shadow: 0 2px 8px rgba(0,0,0,0.10); text-align: center;
        }}
        #scale-bar-line {{
            height: 6px; margin-top: 2px; border-left: 2px solid #691C32;
            border-right: 2px solid #691C32; border-bottom: 2px solid #691C32;
            min-width: 40px;
        }}

        #section-hint {{
            position: absolute; top: 54px; left: 50%; transform: translateX(-50%);
            z-index: 1200; display: none; background: #691C32; color: #ffffff;
            padding: 6px 14px; border-radius: 20px; font-size: 11.5px; font-weight: 600;
            box-shadow: 0 4px 14px rgba(105,28,50,0.35); pointer-events: none;
        }}

        #section-drawer {{
            position: absolute; left: 12px; right: 12px; bottom: 12px; z-index: 1600;
            display: none; background: rgba(255,255,255,0.98); backdrop-filter: blur(10px);
            border-radius: 10px; border: 1px solid #cbd5e1; border-top: 3.5px solid #691C32;
            box-shadow: 0 10px 30px rgba(15,23,42,0.25); padding: 10px 14px;
        }}
        .sec-header {{
            display: flex; justify-content: space-between; align-items: center;
            flex-wrap: wrap; gap: 8px; margin-bottom: 6px;
        }}
        .sec-metrics {{
            display: flex; gap: 14px; flex-wrap: wrap; font-size: 11px; color: #334155;
        }}
        .sec-metrics b {{ color: #691C32; }}
        .sec-actions {{ display: flex; gap: 6px; align-items: center; }}
        .sec-btn {{
            background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px;
            padding: 4px 9px; font-size: 10.5px; font-weight: 700; color: #1e293b;
            cursor: pointer;
        }}
        .sec-btn:hover {{ background: #e2e8f0; border-color: #691C32; color: #691C32; }}
        .sec-canvas-wrap {{ position: relative; width: 100%; }}
        #section-canvas {{ width: 100%; height: 205px; display: block; border-radius: 6px; border: 1px solid #e2e8f0; background: #ffffff; cursor: crosshair; }}
        #section-tooltip {{
            position: absolute; top: 10px; left: 68px; z-index: 20; display: none;
            pointer-events: none; background: rgba(15,23,42,0.94); color: #f8fafc;
            padding: 7px 10px; border-radius: 7px; font-size: 10.5px; line-height: 1.42;
            border-left: 3.5px solid #06b6d4; box-shadow: 0 6px 18px rgba(15,23,42,0.32);
            max-width: 315px; backdrop-filter: blur(4px);
        }}
        .sec-note {{
            font-size: 9.8px; color: #64748b; margin-top: 5px;
            display: flex; justify-content: space-between; align-items: center;
            gap: 8px; flex-wrap: wrap;
        }}
    </style>
</head>
<body>
<div id="container3d"></div>

<div class="hud-top">
    <div><b>LON:</b> <span id="hud-lon">--</span></div>
    <div><b>LAT:</b> <span id="hud-lat">--</span></div>
    <div style="color:#008a3b;"><b>COTA:</b> <span id="hud-ele">-- msnm</span></div>
</div>

<div id="compass-3d" onclick="orientarAlNorte()" title="Norte geográfico (clic para orientar al Norte manteniendo inclinación 3D)">
    <svg id="compass-needle" width="46" height="46" viewBox="0 0 48 48" style="transition: transform 0.08s linear;">
        <circle cx="24" cy="24" r="21.5" fill="none" stroke="#e2e8f0" stroke-width="1.2"/>
        <line x1="43" y1="24" x2="45.5" y2="24" stroke="#94a3b8" stroke-width="1.3"/>
        <line x1="2.5" y1="24" x2="5" y2="24" stroke="#94a3b8" stroke-width="1.3"/>
        <line x1="24" y1="43" x2="24" y2="45.5" stroke="#94a3b8" stroke-width="1.3"/>
        <text x="24" y="12.5" text-anchor="middle" font-size="10.5" font-weight="900" font-family="Segoe UI, Arial, sans-serif" fill="#691C32">N</text>
        <polygon points="24,14.8 29,25.5 24,22.8 19,25.5" fill="#9F2241"/>
        <polygon points="24,38.5 29,25.5 24,28.2 19,25.5" fill="#94a3b8"/>
        <circle cx="24" cy="25.5" r="1.7" fill="#ffffff" stroke="#475569" stroke-width="0.9"/>
    </svg>
</div>

<div id="scale-3d">
    <div id="scale-bar-label">-- km</div>
    <div id="scale-bar-line" style="width: 80px;"></div>
</div>

<div id="section-hint">✂️ Sección A–A': haz clic sobre el bloque 3D para marcar el punto A</div>

<div id="section-drawer">
    <div class="sec-header">
        <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
            <span style="font-weight:800; color:#691C32; font-size:12.5px;">✂️ Perfil Topográfico–Geológico (A – A')</span>
            <div class="sec-metrics" id="sec-metrics"></div>
        </div>
        <div class="sec-actions">
            <select id="sel-sec-scale" class="sec-btn" onchange="cambiarEscalaPerfil(this.value)" title="Escala vertical del perfil">
                <option value="auto" selected>Escala: Auto</option>
                <option value="1:1">Escala: 1:1 real</option>
            </select>
            <button class="sec-btn" onclick="exportarPerfilPNG()">📷 PNG Perfil</button>
            <button class="sec-btn" onclick="exportarPerfilCSV()">📄 CSV Perfil</button>
            <button class="sec-btn" onclick="limpiarSeccion()">🧹 Limpiar</button>
            <button class="sec-btn" onclick="cerrarDrawerSeccion()" title="Ocultar perfil">✕</button>
        </div>
    </div>
    <div class="sec-canvas-wrap">
        <canvas id="section-canvas"></canvas>
        <div id="section-tooltip"></div>
    </div>
    <div class="sec-note">
        <span><b>Nota técnica:</b> Las franjas de color proyectan la cartografía litológica superficial SGM 1:50k (sin espesores ni buzamientos en subsuelo).</span>
        <span>🖱️ Pasa el cursor sobre el perfil para inspeccionar y sincronizar con el bloque 3D.</span>
    </div>
</div>

<div id="popup3d">
    <span class="popup-close" onclick="cerrarPopup3D()">✕</span>
    <div id="popup-content"></div>
</div>

<button class="btn-fullscreen-top" onclick="toggleFullscreen()" title="Pantalla Completa" id="btn-fs">
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" id="fs-svg">
        <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
    </svg>
</button>

<div id="btn-open-dock" class="btn-open-dock-circle" onclick="toggleDock()" title="Abrir Instrumentación 3D" style="display: none;">
    ☰
</div>

<div id="dock-panel" class="workbench-dock">
    <div class="dock-header">
        <div style="display:flex; align-items:center; gap:6px;">
            <span>🛠️ Instrumentación 3D</span>
            <span style="font-size: 10px; opacity: 0.85;">CONAGUA</span>
        </div>
        <button onclick="toggleDock()" style="background:transparent; border:none; color:white; font-size:16px; font-weight:bold; cursor:pointer; line-height:1; padding:2px 5px;" title="Contraer panel">✕</button>
    </div>
    <div class="dock-body">

        <div class="dock-section">
            <label>🧭 Proyección y Vistas Cardinales (360°):</label>
            <div class="btn-cam-grid">
                <button class="btn-cam" onclick="setCameraView('top')">⬆️ Planta (2D)</button>
                <button class="btn-cam" onclick="setCameraView('iso')">🧊 Isométrica</button>
                <button class="btn-cam" onclick="setCameraView('south')">⬇️ Frente Sur</button>
                <button class="btn-cam" onclick="setCameraView('east')">➡️ Perfil Este</button>
                <button class="btn-cam" onclick="setCameraView('west')">⬅️ Perfil Oeste</button>
                <button class="btn-cam" onclick="setCameraView('under')">🔄 Desde Abajo</button>
            </div>
            <div style="font-size:10px; color:#64748B; margin-top:4px;">
                🖱️ <b>Clic Izq.:</b> Rotar · <b>Clic Der.:</b> Desplazar · <b>Clic breve:</b> Inspeccionar.
            </div>
        </div>

        <div class="dock-section">
            <label>📐 Remuestreo del Terreno:</label>
            <select id="sel-remuestreo" style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:5px; padding:6px 8px; font-size:11px; font-weight:600; color:#334155; width:100%; cursor:pointer;" onchange="cambiarRemuestreoThree(this.value)">
                <option value="bilineal" selected>Bilineal (Interpolación lineal 2×2)</option>
                <option value="cubico">Cúbico (Bicúbico Catmull-Rom 4×4)</option>
                <option value="vecino">Vecino más próximo (Escalonado)</option>
            </select>
        </div>

        <div class="dock-section">
            <label>📡 Detalle de Malla 3D:</label>
            <select id="sel-resolucion-dem" style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:5px; padding:6px 8px; font-size:11px; font-weight:600; color:#334155; width:100%; cursor:pointer;" onchange="cambiarResolucionThree(this.value)">
                <option value="1" selected id="opt-res-1">Máximo (malla completa)</option>
                <option value="2" id="opt-res-2">Medio (1/2 paso)</option>
                <option value="4" id="opt-res-4">Ligero (1/4 paso)</option>
            </select>
        </div>

        <div class="dock-section" style="background:#f8fafc; padding:8px; border-radius:6px; border:1px solid #e2e8f0;">
            <label style="color:#691C32;">☀️ Simulación Solar (Luz y Sombras):</label>
            <div style="font-size:10.5px; margin-bottom:4px;">Azimut del Sol: <b id="val-sol">315° (Noroeste)</b></div>
            <input type="range" class="slider-ctrl" id="slider-sol" min="0" max="360" step="5" value="315" oninput="cambiarLuzSolar(this.value)">

            <div style="font-size:10.5px; margin-top:6px; margin-bottom:4px;">Intensidad de Sombreado: <b id="val-shade">85%</b></div>
            <input type="range" class="slider-ctrl" id="slider-shade" min="0.2" max="1.5" step="0.05" value="0.85" oninput="cambiarIntensidadSombra(this.value)">
        </div>

        <div class="dock-section" style="background:#f8fafc; padding:8px 10px; border-radius:6px; border:1px solid #e2e8f0;">
            <label style="color:#691C32; margin-bottom:3px;">📏 Curvas de Nivel (Cotas):</label>
            <div style="font-size:11px; margin-bottom:5px;">Equidistancia: <b id="val-cotas" style="color:#691C32;">Cada {paso_ini} m</b></div>
            <input type="range" class="slider-ctrl" id="slider-cotas" min="0" max="{max_sl}" step="{int_base}" value="{paso_ini}" oninput="cambiarEquidistanciaCotasThree(this.value)">
            <div style="display:flex; justify-content:space-between; font-size:9px; color:#64748B; margin-top:3px; padding:0 1px;">
                <span>Off</span>
                <span>{t1}m</span>
                <span>{t2}m</span>
                <span>{t3}m</span>
                <span>{t4}m</span>
                <span>{max_sl}m</span>
            </div>
        </div>

        <div class="dock-section">
            <label>⛰️ Exageración Vertical Real: <b id="val-exag" style="color:#691C32;">1.0x</b></label>
            <input type="range" class="slider-ctrl" id="slider-exag" min="1.0" max="15.0" step="0.5" value="1.0" oninput="cambiarExageracionRelieve(this.value)">
            <div style="font-size:9.5px; color:#64748B; margin-top:2px;">1.0x = escala 1:1 real (horizontal y vertical en metros).</div>
        </div>

        <div class="dock-section">
            <label>🎨 Opacidad Litología SGM: <b id="val-opac">100%</b></label>
            <input type="range" class="slider-ctrl" id="slider-opac" min="0.1" max="1.0" step="0.05" value="1.0" oninput="cambiarOpacidadThree(this.value)">

            <div style="margin-top: 8px; display: flex; flex-direction: column; gap: 5px;">
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-lines" checked onchange="toggleContactos()"> Contactos Geológicos SGM
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-estructuras" checked onchange="toggleEstructuras()"> ⚡ Fallas y Fracturas 1:50k (SGM)
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-border" checked onchange="toggleBorde()"> Límite Oficial Acuífero
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-pozos" checked onchange="togglePozos(this.checked)"> 📍 Pozos Subterráneos 3D
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-faldon" checked onchange="toggleFaldon(this.checked)"> 🧱 Bloque Sólido (Faldón)
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;" id="lbl-freatico">
                    <input type="checkbox" id="chk-freatico" onchange="toggleFreatico(this.checked)"> 💧 Superficie Piezométrica 3D
                </label>
            </div>
        </div>

        <button class="btn-tool-sec" id="btn-section" onclick="toggleModoSeccion()">
            ✂️ Sección Transversal (A–A')
        </button>

        <button class="btn-screenshot" style="margin-top:8px;" onclick="capturarPantalla3D()">
            📸 Capturar Lámina HD (PNG)
        </button>

        <button class="btn-tool-sec" id="btn-gltf" onclick="exportarGLTF()">
            🧊 Exportar Modelo 3D (.gltf)
        </button>
    </div>
</div>

<script>
    const dataGeologia = {geojson_geologia};
    const dataEstructuras = {geojson_estructuras};
    const dataBorde = {geojson_borde};
    const dataCurvas = {geojson_curvas_cota};
    const dataPozos = {pozos_aislado_json};
    const mallaInfo = {malla_json_str};
    const leyendaSgm = {leyenda_sgm_json};
    const acuifMeta = {acuifero_meta_json};

    const minX = mallaInfo.bounds[0];
    const minY = mallaInfo.bounds[1];
    const maxX = mallaInfo.bounds[2];
    const maxY = mallaInfo.bounds[3];

    // Etiquetas reales de malla 3D según resolución efectiva en metros
    const pxBase = Math.max(1, Math.round(mallaInfo.px_malla_m));
    document.getElementById('opt-res-1').text = `Máximo (~${{pxBase}} m/celda · ${{mallaInfo.cols}}×${{mallaInfo.rows}})`;
    document.getElementById('opt-res-2').text = `Medio (~${{pxBase * 2}} m/celda)`;
    document.getElementById('opt-res-4').text = `Ligero (~${{pxBase * 4}} m/celda)`;

    // Helper seguro contra inyección HTML en popups
    function escapeHtml(val) {{
        if (val === null || val === undefined) return '';
        return String(val)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }}

    function rumboCardinal8(deg) {{
        const rumbos = ['Norte', 'Noreste', 'Este', 'Sureste', 'Sur', 'Suroeste', 'Oeste', 'Noroeste'];
        const idx = Math.round((((deg % 360) + 360) % 360) / 45) % 8;
        return rumbos[idx];
    }}

    // ===================================================
    // 🎨 1. TEXTURA VECTORIAL 2K CONTINUA (SOPORTA HUECOS)
    // ===================================================
    const canvasTex = document.createElement('canvas');
    canvasTex.width = 2048;
    canvasTex.height = 2048;
    const ctx = canvasTex.getContext('2d');

    function geoToCanvas(x, y) {{
        const cx = ((x - minX) / (maxX - minX)) * 2048;
        const cy = ((maxY - y) / (maxY - minY)) * 2048;
        return [cx, cy];
    }}

    function dibujarPoligonoConHuecos(rings, fillColor, strokeColor, lineWidth) {{
        if (!rings || rings.length === 0) return;
        ctx.beginPath();
        for (let r = 0; r < rings.length; r++) {{
            const coords = rings[r];
            if (!coords || coords.length < 2) continue;
            for (let i = 0; i < coords.length; i++) {{
                const [cx, cy] = geoToCanvas(coords[i][0], coords[i][1]);
                if (i === 0) ctx.moveTo(cx, cy);
                else ctx.lineTo(cx, cy);
            }}
            ctx.closePath();
        }}
        if (fillColor) {{
            ctx.fillStyle = fillColor;
            ctx.fill('evenodd');
        }}
        if (strokeColor && lineWidth > 0) {{
            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = lineWidth;
            ctx.stroke();
        }}
    }}

    let pasoCotasActual = {paso_ini};
    let textureVectorial = null;
    let needsRender = true;
    function marcarRender() {{ needsRender = true; }}

    function redibujarTexturaCompleta() {{
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(0, 0, 2048, 2048);

        // 1. Polígonos de Litología SGM (con anillos interiores / huecos respetados)
        const verContactos = document.getElementById('chk-lines') ? document.getElementById('chk-lines').checked : true;
        if (dataGeologia && dataGeologia.features && dataGeologia.features.length > 0) {{
            dataGeologia.features.forEach(f => {{
                const color = (f.properties && f.properties.COLOR_HEX) ? f.properties.COLOR_HEX : '#B0BEC5';
                const geom = f.geometry;
                const stroke = verContactos ? '#334155' : null;
                const w = verContactos ? 1.5 : 0;
                if (geom && geom.type === 'Polygon') {{
                    dibujarPoligonoConHuecos(geom.coordinates, color, stroke, w);
                }} else if (geom && geom.type === 'MultiPolygon') {{
                    geom.coordinates.forEach(poly => {{
                        dibujarPoligonoConHuecos(poly, color, stroke, w);
                    }});
                }}
            }});
        }}

        // 2. Fallas y Fracturas 1:50,000 del SGM
        const verFallas = document.getElementById('chk-estructuras')?.checked;
        if (verFallas && dataEstructuras && dataEstructuras.features) {{
            ctx.strokeStyle = '#dc2626';
            ctx.lineWidth = 3.5;
            ctx.setLineDash([8, 4]);
            dataEstructuras.features.forEach(f => {{
                const geom = f.geometry;
                if (!geom) return;
                const coordsArr = geom.type === 'LineString' ? [geom.coordinates] : (geom.type === 'MultiLineString' ? geom.coordinates : []);
                coordsArr.forEach(coords => {{
                    ctx.beginPath();
                    for (let i = 0; i < coords.length; i++) {{
                        const [cx, cy] = geoToCanvas(coords[i][0], coords[i][1]);
                        if (i === 0) ctx.moveTo(cx, cy);
                        else ctx.lineTo(cx, cy);
                    }}
                    ctx.stroke();
                }});
            }});
            ctx.setLineDash([]);
        }}

        // 3. Curvas de Nivel drapeadas en 2K
        if (pasoCotasActual > 0 && dataCurvas && dataCurvas.features) {{
            ctx.strokeStyle = '#475569';
            ctx.lineWidth = 1.0;
            ctx.setLineDash([4, 2]);
            dataCurvas.features.forEach(f => {{
                const cota = f.properties.cota;
                if (cota % pasoCotasActual === 0) {{
                    const coords = f.geometry.coordinates;
                    ctx.beginPath();
                    for (let i = 0; i < coords.length; i++) {{
                        const [cx, cy] = geoToCanvas(coords[i][0], coords[i][1]);
                        if (i === 0) ctx.moveTo(cx, cy);
                        else ctx.lineTo(cx, cy);
                    }}
                    ctx.stroke();
                }}
            }});
            ctx.setLineDash([]);
        }}

        // 4. Límite Oficial Acuífero CONAGUA (incluyendo anillos interiores si existen)
        if (document.getElementById('chk-border').checked && dataBorde && dataBorde.features) {{
            dataBorde.features.forEach(f => {{
                const geom = f.geometry;
                if (geom && geom.type === 'Polygon') dibujarPoligonoConHuecos(geom.coordinates, null, '#691C32', 4.5);
                else if (geom && geom.type === 'MultiPolygon') geom.coordinates.forEach(poly => dibujarPoligonoConHuecos(poly, null, '#691C32', 4.5));
            }});
        }}

        if (textureVectorial) textureVectorial.needsUpdate = true;
        marcarRender();
    }}

    textureVectorial = new THREE.CanvasTexture(canvasTex);
    textureVectorial.anisotropy = 16;
    redibujarTexturaCompleta();

    // ===================================================
    // 🧊 2. ESCENA THREE.JS
    // ===================================================
    const container = document.getElementById('container3d');
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8fafc);

    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 1, 6000);
    camera.up.set(0, 0, 1);  // Convención GIS 3D Z-up (+X Este, +Y Norte, +Z Elevación)
    camera.position.set(0, -340, 240);

    const renderer = new THREE.WebGLRenderer({{ antialias: true, preserveDrawingBuffer: true }});
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxDistance = 1800;
    controls.minDistance = 20;
    controls.update();
    controls.addEventListener('change', marcarRender);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.72);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xfff7ed, 0.85);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    dirLight.shadow.camera.left = -280;
    dirLight.shadow.camera.right = 280;
    dirLight.shadow.camera.top = 280;
    dirLight.shadow.camera.bottom = -280;
    dirLight.shadow.camera.near = 40;
    dirLight.shadow.camera.far = 1200;
    dirLight.shadow.bias = -0.0005;
    dirLight.shadow.normalBias = 0.55;
    dirLight.shadow.camera.updateProjectionMatrix();
    scene.add(dirLight);

    // ===================================================
    // ⛰️ 3. MALLA TRIDIMENSIONAL CALIBRADA (ESCALA 1:1 REAL EN METROS)
    // ===================================================
    const rows = mallaInfo.rows;
    const cols = mallaInfo.cols;
    const grid = mallaInfo.z_grid;
    const geomWidth = 350.0;
    const geomHeight = geomWidth * (mallaInfo.height_m / Math.max(mallaInfo.width_m, 1.0));
    // 1 metro real = unitsPerMeter unidades Three.js (tanto horizontal como vertical en 1.0x)
    const unitsPerMeter = geomWidth / Math.max(mallaInfo.width_m, 1.0);

    let exagRealActual = mallaInfo.exag_inicial || 1.0;
    const sliderExag = document.getElementById('slider-exag');
    sliderExag.max = String(mallaInfo.exag_max || 15.0);
    sliderExag.value = String(exagRealActual);
    document.getElementById('val-exag').innerText = exagRealActual.toFixed(1) + 'x';

    // Estado persistente de remuestreo, resolución y material
    let remuestreoActual = 'bilineal';
    let stepResolucionActual = 1;
    let opacidadActual = 1.0;
    let meshAcuifero = null;
    let meshFaldon = null;
    let meshFreatico = null;
    let mostrarFaldon = true;
    const zBaseFaldon = -Math.max(12.0, 0.045 * geomWidth);

    function destruirMesh(m) {{
        if (!m) return null;
        scene.remove(m);
        if (m.geometry) m.geometry.dispose();
        if (m.material) m.material.dispose();
        return null;
    }}

    function construirFaldonSolido(outRows, outCols, vMap, vertices) {{
        meshFaldon = destruirMesh(meshFaldon);

        // Extrusión por aristas de borde real: cualquier arista compartida por solo 1 triángulo de la malla
        const edgeCount = new Map();
        const edgePair = new Map();
        function regEdge(a, b) {{
            const k = a < b ? (a + '_' + b) : (b + '_' + a);
            edgeCount.set(k, (edgeCount.get(k) || 0) + 1);
            if (!edgePair.has(k)) edgePair.set(k, [a, b]);
        }}

        for (let ir = 0; ir < outRows - 1; ir++) {{
            for (let ic = 0; ic < outCols - 1; ic++) {{
                const v00 = vMap[ir * outCols + ic];
                const v10 = vMap[(ir + 1) * outCols + ic];
                const v01 = vMap[ir * outCols + (ic + 1)];
                const v11 = vMap[(ir + 1) * outCols + (ic + 1)];
                if (v00 !== -1 && v10 !== -1 && v01 !== -1) {{
                    regEdge(v00, v10); regEdge(v10, v01); regEdge(v01, v00);
                }}
                if (v10 !== -1 && v11 !== -1 && v01 !== -1) {{
                    regEdge(v10, v11); regEdge(v11, v01); regEdge(v01, v10);
                }}
            }}
        }}

        const skirtPos = [];
        edgeCount.forEach((cnt, k) => {{
            if (cnt !== 1) return;
            const [a, b] = edgePair.get(k);
            const ax = vertices[a * 3], ay = vertices[a * 3 + 1], az = vertices[a * 3 + 2];
            const bx = vertices[b * 3], by = vertices[b * 3 + 1], bz = vertices[b * 3 + 2];
            const zBot = zBaseFaldon / Math.max(exagRealActual, 0.5);
            skirtPos.push(
                ax, ay, az,  bx, by, bz,  ax, ay, zBot,
                bx, by, bz,  bx, by, zBot,  ax, ay, zBot
            );
        }});

        if (skirtPos.length === 0) return;
        const gSkirt = new THREE.BufferGeometry();
        gSkirt.setAttribute('position', new THREE.Float32BufferAttribute(skirtPos, 3));
        gSkirt.computeVertexNormals();
        const mSkirt = new THREE.MeshStandardMaterial({{
            color: 0x94a3b8,
            roughness: 0.88,
            metalness: 0.02,
            transparent: true,
            opacity: 0.72,
            side: THREE.DoubleSide
        }});
        meshFaldon = new THREE.Mesh(gSkirt, mSkirt);
        meshFaldon.scale.set(1, 1, exagRealActual);
        meshFaldon.visible = mostrarFaldon;
        scene.add(meshFaldon);
    }}

    function actualizarBaseFaldon() {{
        if (!meshFaldon || !meshFaldon.geometry) return;
        const pos = meshFaldon.geometry.attributes.position;
        const zBot = zBaseFaldon / Math.max(exagRealActual, 0.5);
        for (let i = 0; i < pos.count; i += 6) {{
            pos.setZ(i + 2, zBot);
            pos.setZ(i + 4, zBot);
            pos.setZ(i + 5, zBot);
        }}
        pos.needsUpdate = true;
        meshFaldon.geometry.computeBoundingBox();
        meshFaldon.geometry.computeBoundingSphere();
    }}

    function toggleFaldon(visible) {{
        mostrarFaldon = visible;
        if (meshFaldon) meshFaldon.visible = visible;
        marcarRender();
    }}

    // Núcleos matemáticos reales de remuestreo DEM (Vecino, Bilineal 2×2, Bicúbico Keys a=-0.5 4×4)
    function pesoCubicoKeys(t) {{
        const x = Math.abs(t);
        if (x <= 1.0) return (1.5 * x - 2.5) * x * x + 1.0;
        if (x < 2.0) return ((-0.5 * x + 2.5) * x - 4.0) * x + 2.0;
        return 0.0;
    }}

    function muestrearBilinealDEM(rf, cf) {{
        const r0 = Math.floor(rf), r1 = Math.min(rows - 1, r0 + 1);
        const c0 = Math.floor(cf), c1 = Math.min(cols - 1, c0 + 1);
        const fr = rf - r0, fc = cf - c0;

        const z00 = grid[r0][c0], z10 = grid[r1][c0], z01 = grid[r0][c1], z11 = grid[r1][c1];
        let suma = 0.0, pesos = 0.0;
        if (z00 > -9000) {{ const w = (1 - fr) * (1 - fc); suma += z00 * w; pesos += w; }}
        if (z10 > -9000) {{ const w = fr * (1 - fc); suma += z10 * w; pesos += w; }}
        if (z01 > -9000) {{ const w = (1 - fr) * fc; suma += z01 * w; pesos += w; }}
        if (z11 > -9000) {{ const w = fr * fc; suma += z11 * w; pesos += w; }}
        return pesos > 0 ? (suma / pesos) : -9999.0;
    }}

    function muestrearBicubicoDEM(rf, cf) {{
        const r0 = Math.floor(rf), c0 = Math.floor(cf);
        const fr = rf - r0, fc = cf - c0;
        if (r0 < 1 || r0 >= rows - 2 || c0 < 1 || c0 >= cols - 2) {{
            return muestrearBilinealDEM(rf, cf);
        }}

        const wr0 = pesoCubicoKeys(fr + 1), wr1 = pesoCubicoKeys(fr), wr2 = pesoCubicoKeys(fr - 1), wr3 = pesoCubicoKeys(fr - 2);
        const wc0 = pesoCubicoKeys(fc + 1), wc1 = pesoCubicoKeys(fc), wc2 = pesoCubicoKeys(fc - 1), wc3 = pesoCubicoKeys(fc - 2);
        const wr = [wr0, wr1, wr2, wr3];
        const wc = [wc0, wc1, wc2, wc3];

        let val = 0.0;
        let min2x2 = Infinity, max2x2 = -Infinity;
        for (let m = -1; m <= 2; m++) {{
            const fila = grid[r0 + m];
            let filaVal = 0.0;
            for (let n = -1; n <= 2; n++) {{
                const z = fila[c0 + n];
                if (z <= -9000) return muestrearBilinealDEM(rf, cf);
                if ((m === 0 || m === 1) && (n === 0 || n === 1)) {{
                    if (z < min2x2) min2x2 = z;
                    if (z > max2x2) max2x2 = z;
                }}
                filaVal += z * wc[n + 1];
            }}
            val += filaVal * wr[m + 1];
        }}
        // Acotamiento monótono en celda 2×2 (evita sobreoscilación Gibbs en acantilados)
        return Math.max(min2x2, Math.min(max2x2, val));
    }}

    function remuestrearDEM(rf, cf, modo) {{
        const rNear = Math.max(0, Math.min(rows - 1, Math.round(rf)));
        const cNear = Math.max(0, Math.min(cols - 1, Math.round(cf)));
        if (grid[rNear][cNear] <= -9000) return -9999.0;  // preserva contorno oficial exacto
        if (modo === 'vecino') return grid[rNear][cNear];
        if (modo === 'cubico') return muestrearBicubicoDEM(rf, cf);
        return muestrearBilinealDEM(rf, cf);
    }}

    function aplicarPropiedadesMaterial() {{
        if (!meshAcuifero) return;
        const mat = meshAcuifero.material;
        mat.flatShading = (remuestreoActual === 'vecino');
        mat.roughness = 0.58;
        mat.metalness = 0.04;
        mat.opacity = opacidadActual;
        mat.transparent = (opacidadActual < 0.999);
        mat.needsUpdate = true;
        marcarRender();
    }}

    function construirMallaTerreno(stepOverride) {{
        if (stepOverride !== undefined) stepResolucionActual = stepOverride;

        if (meshAcuifero) {{
            scene.remove(meshAcuifero);
            if (meshAcuifero.geometry) meshAcuifero.geometry.dispose();
            if (meshAcuifero.material) meshAcuifero.material.dispose();
            meshAcuifero = null;
        }}

        // Factores no enteros garantizan remuestreo sub-píxel genuino entre celdas del DEM
        const factorEscala = stepResolucionActual === 1 ? 1.25 : (stepResolucionActual === 2 ? 0.55 : 0.30);
        const outRows = Math.max(2, Math.round(rows * factorEscala));
        const outCols = Math.max(2, Math.round(cols * factorEscala));

        const geom = new THREE.BufferGeometry();
        const vertices = [];
        const uvs = [];
        const indices = [];

        const vMap = new Int32Array(outRows * outCols).fill(-1);
        let vIdx = 0;

        for (let ir = 0; ir < outRows; ir++) {{
            const vFrac = ir / (outRows - 1);
            const rf = vFrac * (rows - 1);
            const y = (0.5 - vFrac) * geomHeight;
            const uvY = 1.0 - vFrac;

            for (let ic = 0; ic < outCols; ic++) {{
                const uFrac = ic / (outCols - 1);
                const cf = uFrac * (cols - 1);
                const zMetrosRel = remuestrearDEM(rf, cf, remuestreoActual);
                if (zMetrosRel > -9000) {{
                    const x = (uFrac - 0.5) * geomWidth;
                    const z = zMetrosRel * unitsPerMeter;  // escala real 1:1

                    vertices.push(x, y, z);
                    uvs.push(uFrac, uvY);
                    vMap[ir * outCols + ic] = vIdx++;
                }}
            }}
        }}

        for (let ir = 0; ir < outRows - 1; ir++) {{
            for (let ic = 0; ic < outCols - 1; ic++) {{
                const v00 = vMap[ir * outCols + ic];
                const v10 = vMap[(ir + 1) * outCols + ic];
                const v01 = vMap[ir * outCols + (ic + 1)];
                const v11 = vMap[(ir + 1) * outCols + (ic + 1)];

                if (v00 !== -1 && v10 !== -1 && v01 !== -1) indices.push(v00, v10, v01);
                if (v10 !== -1 && v11 !== -1 && v01 !== -1) indices.push(v10, v11, v01);
            }}
        }}

        geom.setIndex(indices);
        geom.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
        geom.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
        geom.computeVertexNormals();

        const mat = new THREE.MeshStandardMaterial({{
            map: textureVectorial,
            roughness: 0.58,
            metalness: 0.04,
            side: THREE.DoubleSide
        }});

        meshAcuifero = new THREE.Mesh(geom, mat);
        meshAcuifero.castShadow = true;
        meshAcuifero.receiveShadow = true;
        meshAcuifero.scale.set(1, 1, exagRealActual);
        scene.add(meshAcuifero);
        construirFaldonSolido(outRows, outCols, vMap, vertices);
        aplicarPropiedadesMaterial();
    }}

    construirMallaTerreno(1);

    // ===================================================
    // 🎯 4. POZOS SUBTERRÁNEOS 3D (INTERPOLACIÓN BILINEAL + ZERO LEAKS)
    // ===================================================
    const grupoPozos = new THREE.Group();
    const registrosPozos = [];

    function obtenerElevacionRelMetros(lon, lat) {{
        const cFloat = ((lon - minX) / (maxX - minX)) * (cols - 1);
        const rFloat = ((maxY - lat) / (maxY - minY)) * (rows - 1);
        if (cFloat < 0 || cFloat > cols - 1 || rFloat < 0 || rFloat > rows - 1) return null;

        const r0 = Math.floor(rFloat), r1 = Math.min(rows - 1, r0 + 1);
        const c0 = Math.floor(cFloat), c1 = Math.min(cols - 1, c0 + 1);
        const fr = rFloat - r0, fc = cFloat - c0;

        const z00 = grid[r0][c0], z10 = grid[r1][c0], z01 = grid[r0][c1], z11 = grid[r1][c1];
        const validos = [
            [z00, (1 - fr) * (1 - fc)],
            [z10, fr * (1 - fc)],
            [z01, (1 - fr) * fc],
            [z11, fr * fc]
        ].filter(v => v[0] > -9000);

        if (validos.length === 0) return null;
        let suma = 0, pesos = 0;
        validos.forEach(v => {{ suma += v[0] * v[1]; pesos += v[1]; }});
        return pesos > 0 ? (suma / pesos) : validos[0][0];
    }}

    function construirPozosSubterraneos() {{
        while (grupoPozos.children.length > 0) {{
            const obj = grupoPozos.children[0];
            grupoPozos.remove(obj);
            if (obj.geometry) obj.geometry.dispose();
            if (obj.material) obj.material.dispose();
        }}
        registrosPozos.length = 0;

        if (!dataPozos || dataPozos.length === 0) return;

        dataPozos.forEach(p => {{
            const zRelMetros = obtenerElevacionRelMetros(p.lon, p.lat);
            if (zRelMetros === null) return;  // fuera de píxeles válidos del acuífero

            const px = ((p.lon - minX) / (maxX - minX) - 0.5) * geomWidth;
            const py = (0.5 - (maxY - p.lat) / (maxY - minY)) * geomHeight;
            const cotaMsnmReal = (p.cota_geotiff !== null && p.cota_geotiff !== undefined)
                ? p.cota_geotiff
                : Math.round(mallaInfo.vmin + zRelMetros);
            const profMetros = (p.profundidad && p.profundidad > 0) ? parseFloat(p.profundidad) : 150.0;
            const neRaw = (p.nivel_estatico !== null && p.nivel_estatico !== undefined) ? parseFloat(p.nivel_estatico) : NaN;
            const neMetros = (!Number.isNaN(neRaw) && neRaw >= 0) ? neRaw : null;
            const elevPiez = (neMetros !== null) ? Number((cotaMsnmReal - neMetros).toFixed(1)) : null;

            const tipo = (p.tipo || '').toLowerCase();
            const colHex = p.color_hex
                ? parseInt(p.color_hex.replace('#', ''), 16)
                : ((tipo.includes('requerid') || tipo.includes('nuevo') || tipo.includes('propuest')) ? 0x9F2241 : 0x008a3b);

            const uData = {{ ...p, cota_msnm: cotaMsnmReal, elev_piez: elevPiez, esPozo: true }};

            // Brocal a nivel de terreno
            const geomCabeza = new THREE.CylinderGeometry(2.2, 2.2, 2.2, 16);
            const matCabeza = new THREE.MeshStandardMaterial({{ color: colHex, roughness: 0.35 }});
            const cabeza = new THREE.Mesh(geomCabeza, matCabeza);
            cabeza.rotation.x = Math.PI / 2;
            cabeza.userData = uData;
            grupoPozos.add(cabeza);

            // Ademe superior (zona no saturada o columna completa si no hay NE)
            const geomAdeme = new THREE.CylinderGeometry(1.15, 1.15, 1.0, 14);
            const matAdeme = new THREE.MeshStandardMaterial({{ color: colHex, metalness: 0.25, roughness: 0.45 }});
            const ademe = new THREE.Mesh(geomAdeme, matAdeme);
            ademe.rotation.x = Math.PI / 2;
            ademe.userData = uData;
            grupoPozos.add(ademe);

            // Columna saturada azul + anillo de nivel estático si existe NE < profundidad
            let ademeSat = null;
            let anilloNe = null;
            if (neMetros !== null && neMetros < profMetros) {{
                const geomSat = new THREE.CylinderGeometry(1.22, 1.22, 1.0, 14);
                const matSat = new THREE.MeshStandardMaterial({{ color: 0x0284c7, metalness: 0.15, roughness: 0.3 }});
                ademeSat = new THREE.Mesh(geomSat, matSat);
                ademeSat.rotation.x = Math.PI / 2;
                ademeSat.userData = uData;
                grupoPozos.add(ademeSat);

                const geomAn = new THREE.CylinderGeometry(2.0, 2.0, 0.9, 16);
                const matAn = new THREE.MeshStandardMaterial({{ color: 0x38bdf8, emissive: 0x0369a1, emissiveIntensity: 0.35 }});
                anilloNe = new THREE.Mesh(geomAn, matAn);
                anilloNe.rotation.x = Math.PI / 2;
                anilloNe.userData = uData;
                grupoPozos.add(anilloNe);
            }}

            registrosPozos.push({{
                px, py, zRelMetros, profMetros, neMetros, cotaMsnmReal, elevPiez,
                lon: p.lon, lat: p.lat, cabeza, ademe, ademeSat, anilloNe
            }});
        }});

        actualizarPosicionesPozos();
        actualizarEstadoFreatico();
    }}

    function actualizarPosicionesPozos() {{
        registrosPozos.forEach(reg => {{
            const zSup = reg.zRelMetros * unitsPerMeter * exagRealActual;
            const longTotal = Math.max(2.5, reg.profMetros * unitsPerMeter * exagRealActual);
            reg.cabeza.position.set(reg.px, reg.py, zSup + 1.1);

            if (reg.ademeSat && reg.neMetros !== null && reg.neMetros < reg.profMetros) {{
                const fracNe = reg.neMetros / reg.profMetros;
                if (fracNe <= 0.001) {{
                    reg.ademe.visible = false;
                    reg.ademeSat.scale.set(1, longTotal, 1);
                    reg.ademeSat.position.set(reg.px, reg.py, zSup - longTotal / 2.0);
                    if (reg.anilloNe) reg.anilloNe.position.set(reg.px, reg.py, zSup);
                }} else {{
                    reg.ademe.visible = true;
                    const longSup = Math.max(0.8, longTotal * fracNe);
                    const longSat = Math.max(1.0, longTotal - longSup);
                    reg.ademe.scale.set(1, longSup, 1);
                    reg.ademe.position.set(reg.px, reg.py, zSup - longSup / 2.0);
                    reg.ademeSat.scale.set(1, longSat, 1);
                    reg.ademeSat.position.set(reg.px, reg.py, zSup - longSup - longSat / 2.0);
                    if (reg.anilloNe) reg.anilloNe.position.set(reg.px, reg.py, zSup - longSup);
                }}
            }} else {{
                reg.ademe.visible = true;
                reg.ademe.scale.set(1, longTotal, 1);
                reg.ademe.position.set(reg.px, reg.py, zSup - longTotal / 2.0);
            }}
        }});
        marcarRender();
    }}

    // Superficie Piezométrica 3D (IDW p=2) cuando existen >= 3 pozos con Nivel Estático
    function actualizarEstadoFreatico() {{
        const pozosNe = registrosPozos.filter(r => r.elevPiez !== null);
        const chk = document.getElementById('chk-freatico');
        const lbl = document.getElementById('lbl-freatico');
        if (!chk || !lbl) return;
        if (pozosNe.length < 3) {{
            chk.checked = false;
            chk.disabled = true;
            lbl.style.opacity = '0.55';
            lbl.title = `Se requieren al menos 3 pozos con Nivel Estático (actual: ${{pozosNe.length}})`;
            meshFreatico = destruirMesh(meshFreatico);
        }} else {{
            chk.disabled = false;
            lbl.style.opacity = '1';
            lbl.title = `Interpolación IDW (p=2) con ${{pozosNe.length}} pozos piezométricos`;
            if (chk.checked) construirSuperficieFreatica();
        }}
    }}

    function construirSuperficieFreatica() {{
        meshFreatico = destruirMesh(meshFreatico);
        const pozosNe = registrosPozos.filter(r => r.elevPiez !== null);
        if (pozosNe.length < 3) return;

        const outR = Math.max(20, Math.min(80, Math.round(rows * 0.45)));
        const outC = Math.max(20, Math.min(80, Math.round(cols * 0.45)));
        const verts = [];
        const idxs = [];
        const vMap = new Int32Array(outR * outC).fill(-1);
        let vi = 0;

        const cosLatIdw = Math.cos(((minY + maxY) * 0.5) * Math.PI / 180.0);

        for (let ir = 0; ir < outR; ir++) {{
            const vf = ir / (outR - 1);
            const rf = vf * (rows - 1);
            const lat = maxY - vf * (maxY - minY);
            const y = (0.5 - vf) * geomHeight;
            for (let ic = 0; ic < outC; ic++) {{
                const uf = ic / (outC - 1);
                const cf = uf * (cols - 1);
                const zTerRel = remuestrearDEM(rf, cf, 'bilineal');
                if (zTerRel <= -9000) continue;
                const lon = minX + uf * (maxX - minX);
                const x = (uf - 0.5) * geomWidth;

                // Interpolación IDW isotrópica en espacio métrico (corrige cos(lat) en longitudes)
                let num = 0, den = 0;
                for (let k = 0; k < pozosNe.length; k++) {{
                    const pk = pozosNe[k];
                    const dLonM = (lon - pk.lon) * cosLatIdw;
                    const dLatM = lat - pk.lat;
                    const d2 = dLonM * dLonM + dLatM * dLatM;
                    if (d2 < 1e-12) {{ num = pk.elevPiez; den = 1; break; }}
                    const w = 1.0 / d2;
                    num += w * pk.elevPiez;
                    den += w;
                }}
                const elevPiezM = den > 0 ? (num / den) : (mallaInfo.vmin + zTerRel - 30);
                // Restringir a <= superficie del terreno (salvo surgencia puntual)
                const zFreaticoRel = Math.min(zTerRel - 0.5, elevPiezM - mallaInfo.vmin);
                verts.push(x, y, zFreaticoRel * unitsPerMeter);
                vMap[ir * outC + ic] = vi++;
            }}
        }}

        for (let ir = 0; ir < outR - 1; ir++) {{
            for (let ic = 0; ic < outC - 1; ic++) {{
                const a = vMap[ir * outC + ic], b = vMap[(ir + 1) * outC + ic];
                const c = vMap[ir * outC + (ic + 1)], d = vMap[(ir + 1) * outC + (ic + 1)];
                if (a !== -1 && b !== -1 && c !== -1) idxs.push(a, b, c);
                if (b !== -1 && d !== -1 && c !== -1) idxs.push(b, d, c);
            }}
        }}

        const gF = new THREE.BufferGeometry();
        gF.setIndex(idxs);
        gF.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
        gF.computeVertexNormals();
        const mF = new THREE.MeshStandardMaterial({{
            color: 0x0ea5e9,
            emissive: 0x0284c7,
            emissiveIntensity: 0.18,
            roughness: 0.25,
            metalness: 0.1,
            transparent: true,
            opacity: 0.45,
            side: THREE.DoubleSide,
            depthWrite: false
        }});
        meshFreatico = new THREE.Mesh(gF, mF);
        meshFreatico.scale.set(1, 1, exagRealActual);
        scene.add(meshFreatico);
        marcarRender();
    }}

    function toggleFreatico(visible) {{
        if (visible) construirSuperficieFreatica();
        else meshFreatico = destruirMesh(meshFreatico);
        marcarRender();
    }}

    construirPozosSubterraneos();
    scene.add(grupoPozos);

    // ===================================================
    // 🎛️ 5. CONTROLES Y PERSISTENCIA
    // ===================================================
    let estadoGuardado = localStorage.getItem('dock_3d_abierto');
    let dockAbierto = estadoGuardado !== null ? (estadoGuardado === 'true') : true;

    function aplicarEstadoVisualDock() {{
        const dock = document.getElementById('dock-panel');
        const btnOpen = document.getElementById('btn-open-dock');
        if (dock && btnOpen) {{
            dock.style.display = dockAbierto ? 'block' : 'none';
            btnOpen.style.display = dockAbierto ? 'none' : 'flex';
        }}
    }}
    aplicarEstadoVisualDock();

    function toggleDock() {{
        dockAbierto = !dockAbierto;
        localStorage.setItem('dock_3d_abierto', dockAbierto ? 'true' : 'false');
        aplicarEstadoVisualDock();
    }}

    function calcularDistanciaEncuadreTop() {{
        const vFov = THREE.MathUtils.degToRad(camera.fov);
        const tanHalf = Math.tan(vFov * 0.5);
        const fitH = (geomHeight * 0.5) / tanHalf;
        const fitW = (geomWidth * 0.5) / (tanHalf * Math.max(camera.aspect, 0.5));
        return Math.max(360, Math.max(fitH, fitW) * 1.18);
    }}

    function orientarAlNorte() {{
        // Siempre orienta el azimut exactamente al Norte (0°) conservando inclinación 3D y zoom,
        // anulando cualquier inercia residual (damping) de OrbitControls
        const offset = camera.position.clone().sub(controls.target);
        const horizDist = Math.hypot(offset.x, offset.y);
        const dySign = offset.z < 0 ? 1 : -1;
        const prevDamp = controls.enableDamping;
        controls.enableDamping = false;
        camera.position.set(
            controls.target.x,
            controls.target.y + dySign * Math.max(0.01, horizDist),
            controls.target.z + offset.z
        );
        controls.update();
        controls.enableDamping = prevDamp;
        actualizarBrujulaYEscala();
        marcarRender();
    }}

    function setCameraView(view) {{
        controls.reset();
        const zTop = calcularDistanciaEncuadreTop();
        if (view === 'top') camera.position.set(0, -0.01, zTop);
        else if (view === 'iso') camera.position.set(-190, -270, 220);
        else if (view === 'south') camera.position.set(0, -370, 70);
        else if (view === 'east') camera.position.set(390, 0, 80);
        else if (view === 'west') camera.position.set(-390, 0, 80);
        else if (view === 'under') camera.position.set(0, -210, -280);
        controls.update();
        actualizarBrujulaYEscala();
        marcarRender();
    }}

    function cambiarExageracionRelieve(val) {{
        exagRealActual = parseFloat(val);
        if (meshAcuifero) meshAcuifero.scale.set(1, 1, exagRealActual);
        if (meshFaldon) {{
            meshFaldon.scale.set(1, 1, exagRealActual);
            actualizarBaseFaldon();
        }}
        if (meshFreatico) meshFreatico.scale.set(1, 1, exagRealActual);
        if (lineaSeccion3D) {{
            lineaSeccion3D.scale.set(1, 1, exagRealActual);
            const invZ = 1.0 / Math.max(exagRealActual, 0.01);
            lineaSeccion3D.children.forEach(ch => {{
                if (ch.userData && ch.userData.esPinSeccion) ch.scale.set(1, 1, invZ);
            }});
        }}
        if (marcadorHoverSeccion3D && marcadorHoverSeccion3D.visible && ultimoHoverSeccionMuestra && ultimoHoverSeccionMuestra.zRel !== null) {{
            marcadorHoverSeccion3D.position.z = (ultimoHoverSeccionMuestra.zRel * unitsPerMeter + 2.2) * exagRealActual;
        }}
        actualizarPosicionesPozos();
        document.getElementById('val-exag').innerText = exagRealActual.toFixed(1) + 'x';
    }}

    function cambiarRemuestreoThree(modo) {{
        remuestreoActual = modo;
        construirMallaTerreno();
        if (ultimoPerfilData && document.getElementById('section-drawer')?.style.display === 'block') {{
            generarPerfilGeologico(ultimoPerfilData.pA, ultimoPerfilData.pB);
        }}
    }}

    function cambiarResolucionThree(stepVal) {{
        construirMallaTerreno(parseInt(stepVal, 10));
    }}

    function cambiarEquidistanciaCotasThree(val) {{
        pasoCotasActual = parseInt(val, 10);
        const lbl = document.getElementById('val-cotas');
        lbl.innerText = pasoCotasActual === 0 ? 'Desactivadas' : 'Cada ' + pasoCotasActual + ' m';
        redibujarTexturaCompleta();
    }}

    function cambiarOpacidadThree(val) {{
        opacidadActual = parseFloat(val);
        document.getElementById('val-opac').innerText = Math.round(opacidadActual * 100) + '%';
        aplicarPropiedadesMaterial();
    }}

    function cambiarLuzSolar(val) {{
        const deg = parseInt(val, 10);
        // Azimut geográfico horario desde el Norte (+Y): x = sin(az), y = cos(az)
        const rad = deg * (Math.PI / 180.0);
        dirLight.position.set(Math.sin(rad) * 320, Math.cos(rad) * 320, 260);
        document.getElementById('val-sol').innerText = deg + '° (' + rumboCardinal8(deg) + ')';
        marcarRender();
    }}
    cambiarLuzSolar(315);

    function cambiarIntensidadSombra(val) {{
        const shade = parseFloat(val);
        document.getElementById('val-shade').innerText = Math.round(shade * 100) + '%';
        dirLight.intensity = shade;
        ambientLight.intensity = Math.max(0.3, 1.15 - shade * 0.45);
        marcarRender();
    }}

    function toggleContactos() {{ redibujarTexturaCompleta(); }}
    function toggleEstructuras() {{ redibujarTexturaCompleta(); }}
    function toggleBorde() {{ redibujarTexturaCompleta(); }}
    function togglePozos(visible) {{ grupoPozos.visible = visible; marcarRender(); }}

    const iconExp = `<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>`;
    const iconCmp = `<path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>`;

    function toggleFullscreen() {{
        if (!document.fullscreenElement) {{
            document.documentElement.requestFullscreen().catch(() => {{}});
        }} else if (document.exitFullscreen) {{
            document.exitFullscreen();
        }}
    }}

    document.addEventListener('fullscreenchange', () => {{
        const svgPath = document.querySelector('#fs-svg path');
        if (svgPath) svgPath.setAttribute('d', document.fullscreenElement ? iconCmp : iconExp);
        setTimeout(() => {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
            marcarRender();
        }}, 200);
    }});

    // ===================================================
    // 🎯 6. INSPECCIÓN AL CLIC (SIN FALSOS CLICS AL ORBITAR + HUECOS + SEGMENTOS)
    // ===================================================
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    const popupEl = document.getElementById('popup3d');
    const popupContent = document.getElementById('popup-content');

    function cerrarPopup3D() {{ popupEl.style.display = 'none'; }}

    function puntoEnAnillo(pt, coords) {{
        const x = pt[0], y = pt[1];
        let dentro = false;
        for (let i = 0, j = coords.length - 1; i < coords.length; j = i++) {{
            const xi = coords[i][0], yi = coords[i][1];
            const xj = coords[j][0], yj = coords[j][1];
            const intersecta = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
            if (intersecta) dentro = !dentro;
        }}
        return dentro;
    }}

    function puntoEnPoligonoConHuecos(pt, rings) {{
        if (!rings || rings.length === 0) return false;
        if (!puntoEnAnillo(pt, rings[0])) return false;
        for (let r = 1; r < rings.length; r++) {{
            if (puntoEnAnillo(pt, rings[r])) return false;  // está dentro de un hueco
        }}
        return true;
    }}

    // Índice espacial ligero (bounding box por polígono) para acelerar 15x-30x identificación litológica
    let geoBboxesCache = null;
    function obtenerBboxesGeologia() {{
        if (geoBboxesCache !== null) return geoBboxesCache;
        geoBboxesCache = [];
        if (!dataGeologia || !dataGeologia.features) return geoBboxesCache;
        for (let idx = 0; idx < dataGeologia.features.length; idx++) {{
            const geom = dataGeologia.features[idx].geometry;
            let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
            if (geom) {{
                const polys = geom.type === 'Polygon' ? [geom.coordinates] : (geom.type === 'MultiPolygon' ? geom.coordinates : []);
                for (let p = 0; p < polys.length; p++) {{
                    const ext = polys[p][0];
                    if (!ext) continue;
                    for (let k = 0; k < ext.length; k++) {{
                        const lx = ext[k][0], ly = ext[k][1];
                        if (lx < bx0) bx0 = lx;
                        if (lx > bx1) bx1 = lx;
                        if (ly < by0) by0 = ly;
                        if (ly > by1) by1 = ly;
                    }}
                }}
            }}
            geoBboxesCache.push([bx0, by0, bx1, by1]);
        }}
        return geoBboxesCache;
    }}

    function identificarFormacionGeologica(lon, lat) {{
        if (!dataGeologia || !dataGeologia.features) return null;
        const bboxes = obtenerBboxesGeologia();
        const feats = dataGeologia.features;
        for (let i = 0; i < feats.length; i++) {{
            const b = bboxes[i];
            if (lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) continue;
            const geom = feats[i].geometry;
            if (!geom) continue;
            if (geom.type === 'Polygon') {{
                if (puntoEnPoligonoConHuecos([lon, lat], geom.coordinates)) return feats[i].properties;
            }} else if (geom.type === 'MultiPolygon') {{
                for (let poly of geom.coordinates) {{
                    if (puntoEnPoligonoConHuecos([lon, lat], poly)) return feats[i].properties;
                }}
            }}
        }}
        return null;
    }}

    function distPuntoASegmento(px, py, x1, y1, x2, y2) {{
        const dx = x2 - x1, dy = y2 - y1;
        const len2 = dx * dx + dy * dy;
        if (len2 === 0) return Math.hypot(px - x1, py - y1);
        let t = ((px - x1) * dx + (py - y1) * dy) / len2;
        t = Math.max(0, Math.min(1, t));
        return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
    }}

    function limpiarFormacion(rawForm, litologia) {{
        const s = rawForm ? String(rawForm).trim() : '';
        const up = s.toUpperCase();
        if (!s || up === 'NINGUNO' || up === 'NULL' || up === 'NONE' || up === 'INDETERMINADO' || up === 'NO APLICABLE') {{
            return litologia && litologia !== 'No aplicable' ? litologia : 'Formación Sin Asignar';
        }}
        return s;
    }}

    function limpiarRoca(rawRoca) {{
        const s = rawRoca ? String(rawRoca).trim() : '';
        const up = s.toUpperCase();
        if (!s || up === 'NULL' || up === 'NONE' || up === 'NO APLICABLE' || up === 'NINGUNO') return 'S/D';
        return s;
    }}

    // Diferenciar arrastre de cámara vs clic real
    let downX = 0, downY = 0, isPointerDown = false;
    window.addEventListener('pointerdown', (e) => {{
        downX = e.clientX;
        downY = e.clientY;
        isPointerDown = true;
    }});
    window.addEventListener('pointerup', () => {{ isPointerDown = false; }});

    window.addEventListener('click', (event) => {{
        if (Math.hypot(event.clientX - downX, event.clientY - downY) > 5) return;
        if (event.target.closest('#dock-panel') || event.target.closest('#popup3d') || event.target.closest('.hud-top') || event.target.closest('#btn-fs') || event.target.closest('#btn-open-dock') || event.target.closest('#compass-3d') || event.target.closest('#section-drawer')) {{
            return;
        }}

        mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
        raycaster.setFromCamera(mouse, camera);

        // 0. Modo Sección Transversal A–A'
        if (modoSeccionActivo && meshAcuifero) {{
            const hitsSec = raycaster.intersectObject(meshAcuifero);
            if (hitsSec.length > 0) {{
                const p = hitsSec[0].point;
                const lon = minX + (p.x / geomWidth + 0.5) * (maxX - minX);
                const lat = maxY - (0.5 - p.y / geomHeight) * (maxY - minY);
                agregarPuntoSeccion(lon, lat);
            }}
            return;
        }}

        // 1. Clic en Pozo
        if (grupoPozos.visible && grupoPozos.children.length > 0) {{
            const hitsPozos = raycaster.intersectObjects(grupoPozos.children);
            if (hitsPozos.length > 0) {{
                const d = hitsPozos[0].object.userData;
                const cotaTxt = (d.cota_msnm !== null && d.cota_msnm !== undefined) ? (d.cota_msnm + ' msnm') : 'S/D';
                const profTxt = (d.profundidad && d.profundidad > 0) ? (d.profundidad + ' m') : 'Sin dato (visualizado a 150 m)';
                const neRow = (d.nivel_estatico !== null && d.nivel_estatico !== undefined)
                    ? `<b>Nivel Estático:</b> <span style="color:#0284c7; font-weight:bold;">${{d.nivel_estatico}} m</span><br>`
                      + (d.elev_piez !== null && d.elev_piez !== undefined ? `<b>Elev. Piezométrica:</b> <span style="color:#0369a1; font-weight:bold;">${{d.elev_piez}} msnm</span><br>` : '')
                    : '';
                popupContent.innerHTML = `
                    <h4 style="margin:0 0 6px 0; color:#691C32; border-bottom:1px solid #ddd; padding-bottom:3px;">📍 ${{escapeHtml(d.nombre || 'Pozo')}}</h4>
                    <div style="line-height:1.5;">
                        <b>Tipo:</b> ${{escapeHtml(d.tipo || 'Infraestructura')}}<br>
                        <b>Profundidad:</b> <span style="color:#691C32; font-weight:bold;">${{profTxt}}</span><br>
                        ${{neRow}}
                        <b>Cota Terreno:</b> <span style="color:#008a3b; font-weight:bold;">${{cotaTxt}}</span><br>
                        <span style="color:#64748B; font-size:10px;">Lat: ${{d.lat.toFixed(5)}}° | Lon: ${{d.lon.toFixed(5)}}°</span>
                    </div>
                `;
                popupEl.style.left = Math.min(window.innerWidth - 295, Math.max(12, event.clientX + 14)) + 'px';
                popupEl.style.top = Math.max(20, event.clientY - 40) + 'px';
                popupEl.style.display = 'block';
                return;
            }}
        }}

        // 2. Clic en Geología o Fallas visibles
        if (meshAcuifero) {{
            const hitsTerreno = raycaster.intersectObject(meshAcuifero);
            if (hitsTerreno.length > 0) {{
                const p = hitsTerreno[0].point;
                const lon = minX + (p.x / geomWidth + 0.5) * (maxX - minX);
                const lat = maxY - (0.5 - p.y / geomHeight) * (maxY - minY);
                const cotaMsnm = Math.round(mallaInfo.vmin + (p.z / (unitsPerMeter * exagRealActual)));

                // A) Buscar falla SOLO si la capa de fallas está activa (distancia a segmento)
                let fallaEncontrada = null;
                const verFallasChk = document.getElementById('chk-estructuras')?.checked;
                if (verFallasChk && dataEstructuras && dataEstructuras.features) {{
                    const tolDeg = Math.max(maxX - minX, maxY - minY) * 0.012;
                    let mejorDist = tolDeg;
                    for (let f of dataEstructuras.features) {{
                        const geom = f.geometry;
                        if (!geom) continue;
                        const coordsArr = geom.type === 'LineString' ? [geom.coordinates] : (geom.type === 'MultiLineString' ? geom.coordinates : []);
                        for (let coords of coordsArr) {{
                            for (let i = 0; i < coords.length - 1; i++) {{
                                const dSeg = distPuntoASegmento(lon, lat, coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1]);
                                if (dSeg < mejorDist) {{
                                    mejorDist = dSeg;
                                    fallaEncontrada = f.properties;
                                }}
                            }}
                        }}
                    }}
                }}

                if (fallaEncontrada) {{
                    const azRaw = fallaEncontrada.AZIMUTH ?? fallaEncontrada.Azimuth ?? fallaEncontrada.azimuth ?? fallaEncontrada.AZIMUT;
                    const azNum = parseFloat(azRaw);
                    const azTxt = (azRaw !== undefined && azRaw !== null && !Number.isNaN(azNum) && azNum > 0) ? azNum.toFixed(1) + '°' : 'S/D';

                    const incRaw = fallaEncontrada.INCLINACION ?? fallaEncontrada.Inclinacion ?? fallaEncontrada.inclinacion;
                    const incNum = parseFloat(incRaw);
                    const incTxt = (incRaw !== undefined && incRaw !== null && !Number.isNaN(incNum) && incNum > 0) ? incNum.toFixed(0) + '°' : 'S/D';

                    const tipoEstr = fallaEncontrada.ESTRUCTURAS || fallaEncontrada.TIPO_ESTR || 'Estructura Geológica';
                    const rawNom = fallaEncontrada.NOMBRE || fallaEncontrada.NOM_ESTR;
                    const tieneNom = rawNom && !['', 'NULL', 'NONE', 'NINGUNO', 'SIN NOMBRE'].includes(String(rawNom).trim().toUpperCase());
                    const tituloMostrar = tieneNom ? String(rawNom).trim() : tipoEstr;

                    popupContent.innerHTML = `
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px; border-bottom:1px solid #ddd; padding-bottom:4px;">
                            <span style="color:#dc2626; font-size:16px;">⚡</span>
                            <h4 style="margin:0; color:#dc2626; font-size:13px;">${{escapeHtml(tituloMostrar)}}</h4>
                        </div>
                        <div style="line-height:1.5; font-size:11px; color:#1E293B;">
                            <b>Tipo:</b> ${{escapeHtml(tipoEstr)}}<br>
                            <b>Azimut de Rumbo:</b> <span style="color:#0f172a; font-weight:bold;">${{azTxt}}</span><br>
                            <b>Inclinación / Echado:</b> ${{incTxt}}<br>
                            <b>Cota Terreno:</b> <span style="color:#008A3B; font-weight:bold;">${{cotaMsnm}} msnm</span><br>
                            <span style="color:#64748B; font-size:10px;">Coords: ${{lat.toFixed(4)}}°, ${{lon.toFixed(4)}}°</span>
                        </div>
                    `;
                }} else {{
                    const infoLito = identificarFormacionGeologica(lon, lat);
                    if (infoLito) {{
                        const claveSgm = infoLito.CLAVE_SGM || infoLito.ETIQUETA_LITO || 'S/C';
                        const litologia = infoLito.LITOLOGIA || 'Indiferenciada';
                        const formacion = limpiarFormacion(infoLito.FORMACION, litologia);
                        const roca = limpiarRoca(infoLito.ROCA);
                        const colorHex = infoLito.COLOR_HEX || '#B0BEC5';

                        let edadGeo = infoLito.PERIODO || '';
                        if (infoLito.EDINICIO || infoLito.EDFINAL) {{
                            const ini = infoLito.EDINICIO || '';
                            const fin = infoLito.EDFINAL || '';
                            edadGeo += (ini === fin || !fin) ? ` (${{ini}})` : ` (${{ini}} - ${{fin}})`;
                        }}
                        if (!edadGeo.trim()) edadGeo = infoLito.ERA || 'S/D';

                        popupContent.innerHTML = `
                            <div style="display:flex; align-items:center; justify-content:space-between; gap:6px; margin-bottom:6px; border-bottom:1.5px solid #E2E8F0; padding-bottom:5px;">
                                <div style="display:flex; align-items:center; gap:7px;">
                                    <span style="width:14px; height:14px; background:${{escapeHtml(colorHex)}}; border-radius:3px; border:1px solid #475569; display:inline-block; flex-shrink:0;"></span>
                                    <h4 style="margin:0; color:#691C32; font-size:13px; font-weight:700;">${{escapeHtml(formacion)}}</h4>
                                </div>
                                <span style="background:#F1F5F9; border:1px solid #CBD5E1; color:#334155; font-size:10px; font-weight:700; padding:1px 5px; border-radius:4px; white-space:nowrap;">${{escapeHtml(claveSgm)}}</span>
                            </div>
                            <div style="line-height:1.5; font-size:11px; color:#1E293B;">
                                <b>Litología:</b> ${{escapeHtml(litologia)}}<br>
                                <b>Tipo de Roca:</b> ${{escapeHtml(roca)}}<br>
                                <b>Edad Geológica:</b> ${{escapeHtml(edadGeo)}}<br>
                                <b>Cota Terreno:</b> <span style="color:#008A3B; font-weight:bold;">${{cotaMsnm}} msnm</span><br>
                                <span style="color:#64748B; font-size:10px;">Coords: ${{lat.toFixed(4)}}°, ${{lon.toFixed(4)}}°</span>
                            </div>
                        `;
                    }} else {{
                        popupContent.innerHTML = `
                            <h4 style="margin:0 0 4px 0; color:#691C32; font-size:13px;">Terreno Sin Clasificar</h4>
                            <div style="font-size:11px; line-height:1.4;">
                                <b>Cota:</b> <span style="color:#008A3B; font-weight:bold;">${{cotaMsnm}} msnm</span><br>
                                <span style="color:#64748B; font-size:10px;">Coords: ${{lat.toFixed(4)}}°, ${{lon.toFixed(4)}}°</span>
                            </div>
                        `;
                    }}
                }}

                popupEl.style.left = Math.min(window.innerWidth - 295, Math.max(12, event.clientX + 14)) + 'px';
                popupEl.style.top = Math.max(20, event.clientY - 40) + 'px';
                popupEl.style.display = 'block';
                return;
            }}
        }}

        cerrarPopup3D();
    }});

    // Throttle de raycasting en mousemove (~60 ms) y suspensión al rotar cámara
    let ultimoHoverTs = 0;
    let hoverPendiente = null;
    window.addEventListener('mousemove', (event) => {{
        if (isPointerDown || !meshAcuifero) return;
        const ahora = performance.now();
        if (ahora - ultimoHoverTs < 60) return;
        ultimoHoverTs = ahora;
        if (hoverPendiente) cancelAnimationFrame(hoverPendiente);
        const cx = event.clientX, cy = event.clientY;
        hoverPendiente = requestAnimationFrame(() => {{
            mouse.x = (cx / window.innerWidth) * 2 - 1;
            mouse.y = -(cy / window.innerHeight) * 2 + 1;
            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObject(meshAcuifero);
            if (intersects.length > 0) {{
                const p = intersects[0].point;
                const lon = minX + (p.x / geomWidth + 0.5) * (maxX - minX);
                const lat = maxY - (0.5 - p.y / geomHeight) * (maxY - minY);
                const cotaMsnm = Math.round(mallaInfo.vmin + (p.z / (unitsPerMeter * exagRealActual)));
                document.getElementById('hud-lon').innerText = lon.toFixed(4) + '°';
                document.getElementById('hud-lat').innerText = lat.toFixed(4) + '°';
                document.getElementById('hud-ele').innerText = cotaMsnm + ' msnm';
            }} else {{
                document.getElementById('hud-lon').innerText = '--';
                document.getElementById('hud-lat').innerText = '--';
                document.getElementById('hud-ele').innerText = '-- msnm';
            }}
        }});
    }});

    // ===================================================
    // 🧭 7. BRÚJULA 3D DINÁMICA + ESCALA MÉTRICA
    // ===================================================
    let ultimoAnguloNorteDeg = 0;
    let ultimaEscalaTexto = '-- km';
    let ultimaEscalaPx = 80;
    let ultimaMetersPerPx = 100.0;

    function actualizarBrujulaYEscala() {{
        // Proyección exacta del vector Norte geográfico (+Y) sobre los ejes de pantalla de la cámara (Right, Up)
        camera.updateMatrixWorld();
        const me = camera.matrixWorld.elements;
        const nx = me[1];  // dot(Norte, cameraRight)
        let ny = me[5];    // dot(Norte, cameraUp)
        if (Math.hypot(nx, ny) < 1e-4) {{
            ny = -me[9];   // respaldo horizontal exacto: dot(Norte, cameraForward)
        }}
        ultimoAnguloNorteDeg = (Math.atan2(nx, ny) * 180.0) / Math.PI;
        if (Math.abs(ultimoAnguloNorteDeg) < 0.05) ultimoAnguloNorteDeg = 0;
        const needle = document.getElementById('compass-needle');
        if (needle) needle.style.transform = `rotate(${{ultimoAnguloNorteDeg.toFixed(1)}}deg)`;

        // Escala métrica en el plano del target de la cámara
        const distCam = camera.position.distanceTo(controls.target);
        const vFovRad = THREE.MathUtils.degToRad(camera.fov);
        const worldHeightAtTarget = 2.0 * Math.tan(vFovRad / 2.0) * distCam;
        const unitsPerPx = worldHeightAtTarget / Math.max(window.innerHeight, 1);
        const metersPerPx = unitsPerPx / unitsPerMeter;
        ultimaMetersPerPx = metersPerPx;
        const targetMeters = metersPerPx * 95.0;

        const pasosM = [100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000];
        let elegido = pasosM[0];
        for (let i = 0; i < pasosM.length; i++) {{
            if (pasosM[i] <= targetMeters * 1.35) elegido = pasosM[i];
        }}
        const barPx = Math.max(36, Math.min(140, Math.round(elegido / Math.max(metersPerPx, 1e-6))));
        const lblTxt = elegido >= 1000 ? (elegido / 1000) + ' km' : elegido + ' m';
        ultimaEscalaTexto = lblTxt;
        ultimaEscalaPx = barPx;

        const elLbl = document.getElementById('scale-bar-label');
        const elBar = document.getElementById('scale-bar-line');
        if (elLbl) elLbl.innerText = lblTxt;
        if (elBar) elBar.style.width = barPx + 'px';
    }}
    controls.addEventListener('change', actualizarBrujulaYEscala);
    actualizarBrujulaYEscala();

    // ===================================================
    // ✂️ 8. PERFIL TOPOGRÁFICO–GEOLÓGICO INTERACTIVO (A–A')
    // ===================================================
    let modoSeccionActivo = false;
    let ptsSeccion = [];
    let lineaSeccion3D = null;
    let ultimoPerfilData = null;
    let escalaPerfilActual = 'auto';
    let perfilBaseCache = null;
    let perfilLayoutMeta = null;
    let marcadorHoverSeccion3D = null;
    let ultimoHoverSeccionMuestra = null;

    function asegurarMarcadorHover3D() {{
        if (!marcadorHoverSeccion3D) {{
            marcadorHoverSeccion3D = new THREE.Group();
            const inner = new THREE.Mesh(
                new THREE.SphereGeometry(3.2, 16, 16),
                new THREE.MeshBasicMaterial({{ color: 0x06b6d4 }})
            );
            const halo = new THREE.Mesh(
                new THREE.SphereGeometry(5.2, 16, 16),
                new THREE.MeshBasicMaterial({{ color: 0x38bdf8, transparent: true, opacity: 0.32, depthWrite: false }})
            );
            marcadorHoverSeccion3D.add(inner);
            marcadorHoverSeccion3D.add(halo);
            marcadorHoverSeccion3D.visible = false;
            scene.add(marcadorHoverSeccion3D);
        }}
        return marcadorHoverSeccion3D;
    }}

    function ocultarHoverSeccion() {{
        const tip = document.getElementById('section-tooltip');
        if (tip) tip.style.display = 'none';
        if (perfilBaseCache && perfilLayoutMeta) {{
            const canvas = document.getElementById('section-canvas');
            if (canvas) {{
                const c = canvas.getContext('2d');
                c.setTransform(1, 0, 0, 1, 0, 0);
                c.clearRect(0, 0, canvas.width, canvas.height);
                c.drawImage(perfilBaseCache, 0, 0);
            }}
        }}
        if (marcadorHoverSeccion3D && marcadorHoverSeccion3D.visible) {{
            marcadorHoverSeccion3D.visible = false;
            marcarRender();
        }}
        ultimoHoverSeccionMuestra = null;
    }}

    function cambiarEscalaPerfil(val) {{
        escalaPerfilActual = (val === '1:1') ? '1:1' : 'auto';
        if (ultimoPerfilData) {{
            dibujarCanvasPerfil(ultimoPerfilData);
        }}
    }}

    // Geodesia inversa exacta sobre elipsoide WGS 84 (Vincenty, 1975 · precisión < 1 mm)
    function geodesiaWGS84(lat1, lon1, lat2, lon2) {{
        const a = 6378137.0;
        const f = 1.0 / 298.257223563;
        const b = a * (1.0 - f);
        const phi1 = lat1 * Math.PI / 180.0;
        const phi2 = lat2 * Math.PI / 180.0;
        const L = (lon2 - lon1) * Math.PI / 180.0;
        if (Math.abs(phi1 - phi2) < 1e-12 && Math.abs(L) < 1e-12) return {{ distKm: 0.0, azDeg: 0.0 }};

        const U1 = Math.atan((1.0 - f) * Math.tan(phi1));
        const U2 = Math.atan((1.0 - f) * Math.tan(phi2));
        const sinU1 = Math.sin(U1), cosU1 = Math.cos(U1);
        const sinU2 = Math.sin(U2), cosU2 = Math.cos(U2);

        let lam = L, lamPrev = 0, iter = 0;
        let sinSigma = 0, cosSigma = 0, sigma = 0, sinAlpha = 0, cos2Alpha = 0, cos2SigmaM = 0;
        do {{
            const sinLam = Math.sin(lam), cosLam = Math.cos(lam);
            const t1 = cosU2 * sinLam;
            const t2 = cosU1 * sinU2 - sinU1 * cosU2 * cosLam;
            sinSigma = Math.hypot(t1, t2);
            if (sinSigma === 0) return {{ distKm: 0.0, azDeg: 0.0 }};
            cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLam;
            sigma = Math.atan2(sinSigma, cosSigma);
            sinAlpha = (cosU1 * cosU2 * sinLam) / sinSigma;
            cos2Alpha = 1.0 - sinAlpha * sinAlpha;
            cos2SigmaM = cos2Alpha > 1e-12 ? (cosSigma - (2.0 * sinU1 * sinU2) / cos2Alpha) : 0.0;
            const C = (f / 16.0) * cos2Alpha * (4.0 + f * (4.0 - 3.0 * cos2Alpha));
            lamPrev = lam;
            lam = L + (1.0 - C) * f * sinAlpha * (sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1.0 + 2.0 * cos2SigmaM * cos2SigmaM)));
        }} while (Math.abs(lam - lamPrev) > 1e-12 && ++iter < 100);

        if (iter >= 100) {{
            // Respaldo esférico solo para pares casi antípodas
            const R = 6371.0088;
            const dLat = phi2 - phi1;
            const h = Math.sin(dLat / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(L / 2) ** 2;
            const y = Math.sin(L) * Math.cos(phi2);
            const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(L);
            return {{
                distKm: 2.0 * R * Math.atan2(Math.sqrt(h), Math.sqrt(1.0 - h)),
                azDeg: ((Math.atan2(y, x) * 180.0 / Math.PI) + 360.0) % 360.0
            }};
        }}

        const u2 = cos2Alpha * (a * a - b * b) / (b * b);
        const A = 1.0 + (u2 / 16384.0) * (4096.0 + u2 * (-768.0 + u2 * (320.0 - 175.0 * u2)));
        const B = (u2 / 1024.0) * (256.0 + u2 * (-128.0 + u2 * (74.0 - 47.0 * u2)));
        const dSigma = B * sinSigma * (
            cos2SigmaM + (B / 4.0) * (
                cosSigma * (-1.0 + 2.0 * cos2SigmaM * cos2SigmaM) -
                (B / 6.0) * cos2SigmaM * (-3.0 + 4.0 * sinSigma * sinSigma) * (-3.0 + 4.0 * cos2SigmaM * cos2SigmaM)
            )
        );
        const distM = b * A * (sigma - dSigma);
        const azRad = Math.atan2(cosU2 * Math.sin(lam), cosU1 * sinU2 - sinU1 * cosU2 * Math.cos(lam));
        return {{
            distKm: distM / 1000.0,
            azDeg: ((azRad * 180.0 / Math.PI) + 360.0) % 360.0
        }};
    }}

    function haversineKm(lat1, lon1, lat2, lon2) {{
        return geodesiaWGS84(lat1, lon1, lat2, lon2).distKm;
    }}

    function azimutAB(lat1, lon1, lat2, lon2) {{
        return geodesiaWGS84(lat1, lon1, lat2, lon2).azDeg;
    }}

    function interseccionSegmentos(ax, ay, bx, by, cx, cy, dx, dy) {{
        const rX = bx - ax, rY = by - ay;
        const sX = dx - cx, sY = dy - cy;
        const denom = rX * sY - rY * sX;
        if (Math.abs(denom) < 1e-12) return null;
        const t = ((cx - ax) * sY - (cy - ay) * sX) / denom;
        const u = ((cx - ax) * rY - (cy - ay) * rX) / denom;
        if (t >= 0 && t <= 1 && u >= 0 && u <= 1) return t;
        return null;
    }}

    function toggleModoSeccion() {{
        modoSeccionActivo = !modoSeccionActivo;
        const btn = document.getElementById('btn-section');
        const hint = document.getElementById('section-hint');
        if (btn) btn.classList.toggle('active', modoSeccionActivo);
        renderer.domElement.style.cursor = modoSeccionActivo ? 'crosshair' : '';
        if (modoSeccionActivo) {{
            cerrarPopup3D();
            ptsSeccion = [];
            if (hint) {{
                hint.innerText = "✂️ Sección A–A': haz clic sobre el bloque 3D para marcar el punto A";
                hint.style.display = 'block';
            }}
        }} else if (hint) {{
            hint.style.display = 'none';
        }}
    }}

    function cerrarDrawerSeccion() {{
        ocultarHoverSeccion();
        const dr = document.getElementById('section-drawer');
        if (dr) dr.style.display = 'none';
    }}

    function limpiarSeccion() {{
        ocultarHoverSeccion();
        ptsSeccion = [];
        ultimoPerfilData = null;
        perfilLayoutMeta = null;
        if (lineaSeccion3D) {{
            scene.remove(lineaSeccion3D);
            lineaSeccion3D.traverse(o => {{
                if (o.geometry) o.geometry.dispose();
                if (o.material) o.material.dispose();
            }});
            lineaSeccion3D = null;
        }}
        if (marcadorHoverSeccion3D) {{
            scene.remove(marcadorHoverSeccion3D);
            marcadorHoverSeccion3D.traverse(o => {{
                if (o.geometry) o.geometry.dispose();
                if (o.material) o.material.dispose();
            }});
            marcadorHoverSeccion3D = null;
        }}
        cerrarDrawerSeccion();
        if (modoSeccionActivo) {{
            const hint = document.getElementById('section-hint');
            if (hint) {{
                hint.innerText = "✂️ Sección A–A': haz clic sobre el bloque 3D para marcar el punto A";
                hint.style.display = 'block';
            }}
        }}
        marcarRender();
    }}

    function agregarPuntoSeccion(lon, lat) {{
        const hint = document.getElementById('section-hint');
        if (ptsSeccion.length >= 2) ptsSeccion = [];
        ptsSeccion.push({{ lon, lat }});
        if (ptsSeccion.length === 1) {{
            if (hint) hint.innerText = "✂️ Punto A fijado · Haz clic para marcar el punto A' (final)";
            dibujarTrazaSeccion3D();
        }} else {{
            if (hint) hint.style.display = 'none';
            modoSeccionActivo = false;
            const btn = document.getElementById('btn-section');
            if (btn) btn.classList.remove('active');
            renderer.domElement.style.cursor = '';
            generarPerfilGeologico(ptsSeccion[0], ptsSeccion[1]);
        }}
    }}

    function dibujarTrazaSeccion3D(muestras) {{
        if (lineaSeccion3D) {{
            scene.remove(lineaSeccion3D);
            lineaSeccion3D.traverse(o => {{
                if (o.geometry) o.geometry.dispose();
                if (o.material) o.material.dispose();
            }});
            lineaSeccion3D = null;
        }}
        lineaSeccion3D = new THREE.Group();
        const invZPin = 1.0 / Math.max(exagRealActual, 0.01);
        const addPin = (lon, lat, col) => {{
            const cf = ((lon - minX) / (maxX - minX)) * (cols - 1);
            const rf = ((maxY - lat) / (maxY - minY)) * (rows - 1);
            let zRel = 0;
            if (cf >= 0 && cf <= cols - 1 && rf >= 0 && rf <= rows - 1) {{
                const zr = remuestrearDEM(rf, cf, remuestreoActual);
                if (zr > -9000) zRel = zr;
            }}
            const px = ((lon - minX) / (maxX - minX) - 0.5) * geomWidth;
            const py = (0.5 - (maxY - lat) / (maxY - minY)) * geomHeight;
            const g = new THREE.SphereGeometry(2.8, 14, 14);
            const m = new THREE.MeshBasicMaterial({{ color: col }});
            const s = new THREE.Mesh(g, m);
            s.userData = {{ esPinSeccion: true }};
            s.scale.set(1, 1, invZPin);
            s.position.set(px, py, zRel * unitsPerMeter + 1.5);
            lineaSeccion3D.add(s);
        }};
        if (ptsSeccion[0]) addPin(ptsSeccion[0].lon, ptsSeccion[0].lat, 0xfacc15);
        if (ptsSeccion[1]) addPin(ptsSeccion[1].lon, ptsSeccion[1].lat, 0xef4444);

        if (muestras && muestras.length >= 2) {{
            const pts3 = [];
            muestras.forEach(s => {{
                if (s.zRel === null) return;
                const px = ((s.lon - minX) / (maxX - minX) - 0.5) * geomWidth;
                const py = (0.5 - (maxY - s.lat) / (maxY - minY)) * geomHeight;
                pts3.push(new THREE.Vector3(px, py, s.zRel * unitsPerMeter + 1.2));
            }});
            if (pts3.length >= 2) {{
                const lg = new THREE.BufferGeometry().setFromPoints(pts3);
                const lm = new THREE.LineBasicMaterial({{ color: 0xfacc15, linewidth: 2 }});
                lineaSeccion3D.add(new THREE.Line(lg, lm));
            }}
        }}
        lineaSeccion3D.scale.set(1, 1, exagRealActual);
        scene.add(lineaSeccion3D);
        marcarRender();
    }}

    function generarPerfilGeologico(pA, pB) {{
        const N = 220;
        const distTotalKm = haversineKm(pA.lat, pA.lon, pB.lat, pB.lon);
        if (distTotalKm < 0.05) return;
        const az = azimutAB(pA.lat, pA.lon, pB.lat, pB.lon);

        const muestras = [];
        let cotaMin = Infinity, cotaMax = -Infinity, sumPend = 0, cntPend = 0;
        for (let i = 0; i <= N; i++) {{
            const t = i / N;
            const lon = pA.lon + t * (pB.lon - pA.lon);
            const lat = pA.lat + t * (pB.lat - pA.lat);
            const cf = ((lon - minX) / (maxX - minX)) * (cols - 1);
            const rf = ((maxY - lat) / (maxY - minY)) * (rows - 1);
            let zRel = null, cota = null;
            if (cf >= 0 && cf <= cols - 1 && rf >= 0 && rf <= rows - 1) {{
                const zr = remuestrearDEM(rf, cf, remuestreoActual);
                if (zr > -9000) {{
                    zRel = zr;
                    cota = mallaInfo.vmin + zr;
                    if (cota < cotaMin) cotaMin = cota;
                    if (cota > cotaMax) cotaMax = cota;
                }}
            }}
            const lito = identificarFormacionGeologica(lon, lat);
            muestras.push({{
                t,
                distKm: t * distTotalKm,
                lon, lat, zRel, cota,
                clave: lito ? (lito.CLAVE_SGM || lito.ETIQUETA_LITO || 'S/C') : '',
                litologia: lito ? (lito.LITOLOGIA || '') : '',
                roca: lito ? limpiarRoca(lito.ROCA) : '',
                color: lito ? (lito.COLOR_HEX || '#B0BEC5') : '#e2e8f0'
            }});
        }}
        for (let i = 1; i < muestras.length; i++) {{
            if (muestras[i].cota !== null && muestras[i - 1].cota !== null) {{
                const dsM = (distTotalKm * 1000) / N;
                sumPend += Math.abs(muestras[i].cota - muestras[i - 1].cota) / dsM * 100;
                cntPend++;
            }}
        }}

        // Cruces con fallas SGM 1:50k
        const crucesFallas = [];
        if (dataEstructuras && dataEstructuras.features) {{
            dataEstructuras.features.forEach(f => {{
                const geom = f.geometry;
                if (!geom) return;
                const arr = geom.type === 'LineString' ? [geom.coordinates] : (geom.type === 'MultiLineString' ? geom.coordinates : []);
                arr.forEach(coords => {{
                    for (let i = 0; i < coords.length - 1; i++) {{
                        const tHit = interseccionSegmentos(pA.lon, pA.lat, pB.lon, pB.lat, coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1]);
                        if (tHit !== null) {{
                            const pr = f.properties || {{}};
                            const nom = pr.NOMBRE && !['NULL', 'NONE', ''].includes(String(pr.NOMBRE).toUpperCase()) ? pr.NOMBRE : (pr.ESTRUCTURAS || 'Falla');
                            crucesFallas.push({{ t: tHit, distKm: tHit * distTotalKm, nombre: String(nom).trim() }});
                        }}
                    }}
                }});
            }});
        }}

        // Proyección ortogonal métrica de pozos sobre A–A' (corrige factor cos(lat)) dentro de corredor (6 % de L, mín. 500 m)
        const corredorKm = Math.max(0.5, distTotalKm * 0.06);
        const pozosProy = [];
        const cosSec = Math.cos(((pA.lat + pB.lat) * 0.5) * Math.PI / 180.0);
        const dxABRaw = pB.lon - pA.lon, dyAB = pB.lat - pA.lat;
        const dxABM = dxABRaw * cosSec;
        const len2AB = dxABM * dxABM + dyAB * dyAB;
        if (len2AB > 0) {{
            registrosPozos.forEach(reg => {{
                const tP = (((reg.lon - pA.lon) * cosSec) * dxABM + (reg.lat - pA.lat) * dyAB) / len2AB;
                if (tP < 0 || tP > 1) return;
                const projLon = pA.lon + tP * dxABRaw;
                const projLat = pA.lat + tP * dyAB;
                const offKm = haversineKm(reg.lat, reg.lon, projLat, projLon);
                if (offKm <= corredorKm) {{
                    pozosProy.push({{
                        t: tP,
                        distKm: tP * distTotalKm,
                        offKm: offKm,
                        nombre: reg.cabeza.userData.nombre || 'Pozo',
                        cota: reg.cotaMsnmReal,
                        prof: reg.profMetros,
                        ne: reg.neMetros
                    }});
                }}
            }});
        }}

        ultimoPerfilData = {{
            pA, pB, distTotalKm, az,
            cotaMin: Number.isFinite(cotaMin) ? cotaMin : 0,
            cotaMax: Number.isFinite(cotaMax) ? cotaMax : 100,
            pendMedia: cntPend > 0 ? (sumPend / cntPend) : 0,
            muestras, crucesFallas, pozosProy
        }};
        dibujarTrazaSeccion3D(muestras);
        dibujarCanvasPerfil(ultimoPerfilData);
    }}

    function dibujarCanvasPerfil(data, targetCanvas) {{
        const canvas = targetCanvas || document.getElementById('section-canvas');
        if (!canvas || !data) return;
        const isExport = !!targetCanvas;
        if (!isExport) {{
            const dr = document.getElementById('section-drawer');
            if (dr && dr.style.display !== 'block') dr.style.display = 'block';
        }}
        const dpr = isExport ? 1 : (window.devicePixelRatio || 1);
        const W = isExport ? canvas.width : Math.max(600, canvas.clientWidth || 900);
        const H = isExport ? canvas.height : 205;
        if (!isExport) {{
            canvas.width = Math.round(W * dpr);
            canvas.height = Math.round(H * dpr);
        }}
        const c = canvas.getContext('2d');
        c.setTransform(dpr, 0, 0, dpr, 0, 0);

        c.fillStyle = '#ffffff';
        c.fillRect(0, 0, W, H);

        const padL = 56, padR = 24, padT = isExport ? 58 : 22, padB = isExport ? 50 : 34;
        const plotW = W - padL - padR;
        const plotH = H - padT - padB;

        // Rango vertical incluyendo fondo de pozos proyectados + soporte escala Auto / 1:1 real
        let yMinRaw = data.cotaMin;
        let yMaxRaw = data.cotaMax;
        data.pozosProy.forEach(w => {{
            if (w.cota - w.prof < yMinRaw) yMinRaw = w.cota - w.prof;
        }});
        const distM = Math.max(1.0, data.distTotalKm * 1000.0);
        const mPerPxX = distM / Math.max(plotW, 1);
        let yMin, yMax;
        if (escalaPerfilActual === '1:1') {{
            const metricSpan = Math.max(Math.max(20, yMaxRaw - yMinRaw) * 1.18, mPerPxX * plotH);
            const yMid = (yMinRaw + yMaxRaw) * 0.5;
            yMin = yMid - metricSpan * 0.5;
            yMax = yMid + metricSpan * 0.5;
        }} else {{
            const ySpan = Math.max(20, yMaxRaw - yMinRaw);
            yMin = yMinRaw - ySpan * 0.14;
            yMax = yMaxRaw + ySpan * 0.10;
        }}
        const vegFactor = (mPerPxX * plotH) / Math.max(yMax - yMin, 1e-6);

        if (isExport) {{
            c.fillStyle = '#691C32';
            c.fillRect(0, 0, W, 38);
            c.fillStyle = '#ffffff';
            c.font = 'bold 15px Segoe UI, Arial';
            c.fillText(`PERFIL TOPOGRÁFICO–GEOLÓGICO A–A' · ${{acuifMeta.clave}} - ${{acuifMeta.nombre}}`, 16, 24);
            c.font = '11px Segoe UI, Arial';
            c.textAlign = 'right';
            const lblEsc = escalaPerfilActual === '1:1' ? '1:1 real' : `Auto · EV ${{vegFactor.toFixed(1)}}x`;
            c.fillText(`L = ${{data.distTotalKm.toFixed(2)}} km | Az = ${{data.az.toFixed(0)}}° | Δ = ${{Math.round(data.cotaMax - data.cotaMin)}} m | Escala: ${{lblEsc}}`, W - 16, 24);
            c.textAlign = 'left';
        }}

        const xOf = t => padL + t * plotW;
        const yOf = z => padT + (1 - (z - yMin) / (yMax - yMin)) * plotH;

        // Cuadrícula horizontal
        c.strokeStyle = '#e2e8f0';
        c.lineWidth = 1;
        c.font = '10px Segoe UI, Arial';
        c.fillStyle = '#475569';
        for (let i = 0; i <= 4; i++) {{
            const zVal = yMin + (i / 4) * (yMax - yMin);
            const yy = yOf(zVal);
            c.beginPath(); c.moveTo(padL, yy); c.lineTo(W - padR, yy); c.stroke();
            c.textAlign = 'right';
            c.fillText(Math.round(zVal) + ' m', padL - 6, yy + 3);
        }}

        // Relleno subsuperficial coloreado por litología SGM
        const baseY = padT + plotH;
        const m = data.muestras;
        for (let i = 0; i < m.length - 1; i++) {{
            if (m[i].cota === null || m[i + 1].cota === null) continue;
            const x1 = xOf(m[i].t), x2 = xOf(m[i + 1].t);
            const y1 = yOf(m[i].cota), y2 = yOf(m[i + 1].cota);
            c.fillStyle = m[i].color || '#cbd5e1';
            c.globalAlpha = 0.72;
            c.beginPath();
            c.moveTo(x1, baseY); c.lineTo(x1, y1); c.lineTo(x2, y2); c.lineTo(x2, baseY);
            c.closePath();
            c.fill();
        }}
        c.globalAlpha = 1.0;

        // Etiquetas de unidades litológicas en tramos suficientemente anchos
        let segStart = 0;
        for (let i = 1; i <= m.length; i++) {{
            const cambio = (i === m.length) || (m[i].clave !== m[segStart].clave);
            if (cambio) {{
                const x1 = xOf(m[segStart].t), x2 = xOf(m[i - 1].t);
                const lbl = m[segStart].clave;
                if (lbl && (x2 - x1) > 42) {{
                    const midIdx = Math.floor((segStart + i - 1) / 2);
                    const yTop = m[midIdx].cota !== null ? yOf(m[midIdx].cota) : padT + plotH / 2;
                    const yLbl = Math.min(baseY - 8, (yTop + baseY) / 2 + 4);
                    c.fillStyle = 'rgba(255,255,255,0.82)';
                    const tw = c.measureText(lbl).width + 6;
                    c.fillRect((x1 + x2) / 2 - tw / 2, yLbl - 10, tw, 13);
                    c.fillStyle = '#0f172a';
                    c.font = 'bold 9.5px Segoe UI, Arial';
                    c.textAlign = 'center';
                    c.fillText(lbl, (x1 + x2) / 2, yLbl);
                }}
                segStart = i;
            }}
        }}

        // Línea topográfica principal
        c.strokeStyle = '#691C32';
        c.lineWidth = 2.2;
        c.beginPath();
        let started = false;
        for (let i = 0; i < m.length; i++) {{
            if (m[i].cota === null) {{ started = false; continue; }}
            const xx = xOf(m[i].t), yy = yOf(m[i].cota);
            if (!started) {{ c.moveTo(xx, yy); started = true; }}
            else c.lineTo(xx, yy);
        }}
        c.stroke();

        // Cruces de fallas SGM
        data.crucesFallas.forEach(fl => {{
            const xf = xOf(fl.t);
            c.strokeStyle = '#dc2626';
            c.lineWidth = 1.5;
            c.setLineDash([4, 3]);
            c.beginPath(); c.moveTo(xf, padT); c.lineTo(xf, baseY); c.stroke();
            c.setLineDash([]);
            c.fillStyle = '#dc2626';
            c.font = 'bold 9px Segoe UI, Arial';
            c.textAlign = 'center';
            c.fillText('⚡', xf, padT + 9);
        }});

        // Pozos proyectados (profundidad + nivel estático azul)
        data.pozosProy.forEach(w => {{
            const xw = xOf(w.t);
            const yTop = yOf(w.cota);
            const yBot = yOf(w.cota - w.prof);
            c.strokeStyle = '#0f172a';
            c.lineWidth = 3;
            c.beginPath(); c.moveTo(xw, yTop); c.lineTo(xw, yBot); c.stroke();
            if (w.ne !== null && w.ne < w.prof) {{
                const yNe = yOf(w.cota - w.ne);
                c.strokeStyle = '#0284c7';
                c.lineWidth = 3.5;
                c.beginPath(); c.moveTo(xw, yNe); c.lineTo(xw, yBot); c.stroke();
                c.fillStyle = '#0284c7';
                c.beginPath(); c.arc(xw, yNe, 3.5, 0, Math.PI * 2); c.fill();
            }}
            c.fillStyle = '#691C32';
            c.beginPath(); c.arc(xw, yTop, 3.5, 0, Math.PI * 2); c.fill();
            c.font = 'bold 9px Segoe UI, Arial';
            c.textAlign = 'center';
            c.fillText(w.nombre.slice(0, 14), xw, Math.max(padT + 10, yTop - 6));
        }});

        // Eje X (distancias + A / A')
        c.strokeStyle = '#64748b';
        c.lineWidth = 1;
        c.beginPath(); c.moveTo(padL, baseY); c.lineTo(W - padR, baseY); c.stroke();
        c.fillStyle = '#334155';
        c.font = '10px Segoe UI, Arial';
        for (let i = 0; i <= 5; i++) {{
            const t = i / 5;
            c.textAlign = 'center';
            c.fillText((t * data.distTotalKm).toFixed(1) + ' km', xOf(t), baseY + 14);
        }}
        c.font = 'bold 11px Segoe UI, Arial';
        c.fillStyle = '#691C32';
        c.textAlign = 'left'; c.fillText('A', padL, padT - 5);
        c.textAlign = 'right'; c.fillText("A'", W - padR, padT - 5);

        if (isExport) {{
            c.fillStyle = '#475569';
            c.font = 'italic 10.5px Segoe UI, Arial';
            c.textAlign = 'left';
            c.fillText(
                'Nota técnica: Las franjas de color proyectan la cartografía litológica superficial SGM 1:50k (sin espesores ni buzamientos en subsuelo). Remuestreo DEM: ' + remuestreoActual + '.',
                padL, H - 10
            );
        }} else {{
            perfilLayoutMeta = {{ W, H, dpr, padL, padR, padT, padB, plotW, plotH, yMin, yMax, vegFactor }};
            if (!perfilBaseCache) perfilBaseCache = document.createElement('canvas');
            perfilBaseCache.width = canvas.width;
            perfilBaseCache.height = canvas.height;
            const cacheCtx = perfilBaseCache.getContext('2d');
            cacheCtx.setTransform(1, 0, 0, 1, 0, 0);
            cacheCtx.clearRect(0, 0, perfilBaseCache.width, perfilBaseCache.height);
            cacheCtx.drawImage(canvas, 0, 0);

            const met = document.getElementById('sec-metrics');
            if (met) {{
                met.innerHTML =
                    `<span><b>Longitud:</b> ${{data.distTotalKm.toFixed(2)}} km</span>` +
                    `<span><b>Azimut:</b> ${{data.az.toFixed(0)}}° (${{rumboCardinal8(data.az)}})</span>` +
                    `<span><b>Cota:</b> ${{Math.round(data.cotaMin)}}–${{Math.round(data.cotaMax)}} msnm (Δ ${{Math.round(data.cotaMax - data.cotaMin)}} m)</span>` +
                    `<span><b>Pend. media:</b> ${{data.pendMedia.toFixed(1)}}%</span>` +
                    `<span><b>EV:</b> ${{vegFactor.toFixed(1)}}x</span>` +
                    `<span><b>Fallas:</b> ${{data.crucesFallas.length}} · <b>Pozos:</b> ${{data.pozosProy.length}}</span>`;
            }}
        }}
    }}

    // Hover interactivo 2D ↔ 3D sobre el perfil topográfico–geológico
    (function inicializarInteraccionPerfil() {{
        const canvas = document.getElementById('section-canvas');
        if (!canvas) return;
        canvas.addEventListener('mousemove', (ev) => {{
            if (!ultimoPerfilData || !perfilLayoutMeta || !perfilBaseCache) return;
            const rect = canvas.getBoundingClientRect();
            if (rect.width <= 0) return;
            const meta = perfilLayoutMeta;
            const mx = (ev.clientX - rect.left) * (meta.W / rect.width);
            if (mx < meta.padL || mx > meta.W - meta.padR) {{
                ocultarHoverSeccion();
                return;
            }}
            const tRaw = Math.max(0, Math.min(1, (mx - meta.padL) / Math.max(meta.plotW, 1)));
            const m = ultimoPerfilData.muestras;
            if (!m || m.length === 0) return;
            const idx = Math.round(tRaw * (m.length - 1));
            const s = m[idx];

            // Pendiente puntual en % (diferencia centrada)
            const i0 = Math.max(0, idx - 1);
            const i1 = Math.min(m.length - 1, idx + 1);
            const dsM = (m[i1].distKm - m[i0].distKm) * 1000.0;
            let pendLocalTxt = 'S/D';
            if (m[i0].cota !== null && m[i1].cota !== null && dsM > 0.1) {{
                const pVal = ((m[i1].cota - m[i0].cota) / dsM) * 100.0;
                pendLocalTxt = (pVal >= 0 ? '+' : '') + pVal.toFixed(1) + '%';
            }}

            // Redibujar desde caché offscreen (< 0.5 ms) + crosshair
            const c = canvas.getContext('2d');
            c.setTransform(1, 0, 0, 1, 0, 0);
            c.clearRect(0, 0, canvas.width, canvas.height);
            c.drawImage(perfilBaseCache, 0, 0);
            c.setTransform(meta.dpr, 0, 0, meta.dpr, 0, 0);

            const xCur = meta.padL + s.t * meta.plotW;
            const baseY = meta.padT + meta.plotH;
            c.strokeStyle = '#0284c7';
            c.lineWidth = 1.4;
            c.setLineDash([4, 3]);
            c.beginPath(); c.moveTo(xCur, meta.padT); c.lineTo(xCur, baseY); c.stroke();

            if (s.cota !== null) {{
                const yCur = meta.padT + (1 - (s.cota - meta.yMin) / (meta.yMax - meta.yMin)) * meta.plotH;
                c.strokeStyle = 'rgba(2,132,199,0.45)';
                c.lineWidth = 1;
                c.beginPath(); c.moveTo(meta.padL, yCur); c.lineTo(xCur, yCur); c.stroke();
                c.setLineDash([]);
                c.fillStyle = '#06b6d4';
                c.beginPath(); c.arc(xCur, yCur, 5.2, 0, Math.PI * 2); c.fill();
                c.strokeStyle = '#ffffff';
                c.lineWidth = 2;
                c.stroke();
            }} else {{
                c.setLineDash([]);
            }}

            // Falla o pozo cercano al cursor
            const fallaCerca = ultimoPerfilData.crucesFallas.find(fl => Math.abs(fl.t - s.t) < 0.018);
            const pozoCerca = ultimoPerfilData.pozosProy.find(w => Math.abs(w.t - s.t) < 0.022);

            const tip = document.getElementById('section-tooltip');
            if (tip) {{
                const cotaTxt = s.cota !== null ? s.cota.toFixed(1) + ' msnm' : 'Fuera del DEM';
                const unidadTxt = s.clave ? (escapeHtml(s.clave) + (s.litologia ? ' · ' + escapeHtml(s.litologia) : '')) : 'Sin unidad SGM';
                let htmlTip =
                    `<div style="font-weight:700; color:#38bdf8; margin-bottom:2px;">📍 ${{s.distKm.toFixed(2)}} km · Cota: ${{cotaTxt}}</div>` +
                    `<div><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${{escapeHtml(s.color || '#cbd5e1')}};margin-right:5px;border:1px solid rgba(255,255,255,0.5);"></span><b>SGM:</b> ${{unidadTxt}}</div>` +
                    `<div style="color:#cbd5e1; margin-top:2px;">Pendiente: <b>${{pendLocalTxt}}</b> · ${{s.lat.toFixed(4)}}°, ${{s.lon.toFixed(4)}}°</div>`;
                if (fallaCerca) {{
                    htmlTip += `<div style="color:#fca5a5; margin-top:2px;">⚡ <b>Falla:</b> ${{escapeHtml(fallaCerca.nombre)}} (${{fallaCerca.distKm.toFixed(2)}} km)</div>`;
                }}
                if (pozoCerca) {{
                    const neTxt = pozoCerca.ne !== null ? ` · NE: ${{pozoCerca.ne.toFixed(1)}} m` : '';
                    htmlTip += `<div style="color:#93c5fd; margin-top:2px;">🛢️ <b>Pozo:</b> ${{escapeHtml(pozoCerca.nombre)}} (Prof: ${{pozoCerca.prof.toFixed(0)}} m${{neTxt}})</div>`;
                }}
                tip.innerHTML = htmlTip;
                tip.style.display = 'block';
                const leftPx = (xCur > meta.W * 0.62) ? Math.max(meta.padL + 6, xCur - tip.offsetWidth - 14) : Math.min(meta.W - tip.offsetWidth - 8, xCur + 14);
                tip.style.left = Math.round(leftPx) + 'px';
            }}

            // Sincronización con marcador 3D sobre la traza A–A'
            if (s.zRel !== null) {{
                const mk = asegurarMarcadorHover3D();
                const px = ((s.lon - minX) / (maxX - minX) - 0.5) * geomWidth;
                const py = (0.5 - (maxY - s.lat) / (maxY - minY)) * geomHeight;
                const pz = (s.zRel * unitsPerMeter + 2.2) * exagRealActual;
                mk.position.set(px, py, pz);
                mk.visible = true;
                ultimoHoverSeccionMuestra = s;
                marcarRender();
            }} else if (marcadorHoverSeccion3D && marcadorHoverSeccion3D.visible) {{
                marcadorHoverSeccion3D.visible = false;
                ultimoHoverSeccionMuestra = null;
                marcarRender();
            }}
        }});
        canvas.addEventListener('mouseleave', ocultarHoverSeccion);
    }})();

    function exportarPerfilPNG() {{
        if (!ultimoPerfilData) return;
        const off = document.createElement('canvas');
        off.width = 1600;
        off.height = 480;
        dibujarCanvasPerfil(ultimoPerfilData, off);
        const link = document.createElement('a');
        link.download = 'Perfil_Geologico_AA_{clave_actual}.png';
        link.href = off.toDataURL('image/png');
        link.click();
    }}

    function exportarPerfilCSV() {{
        if (!ultimoPerfilData) return;
        const rowsCsv = ['Distancia_km,Lat,Lon,Cota_msnm,Clave_SGM,Litologia,Roca'];
        const q = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
        ultimoPerfilData.muestras.forEach(s => {{
            rowsCsv.push([
                s.distKm.toFixed(3),
                s.lat.toFixed(5),
                s.lon.toFixed(5),
                s.cota !== null ? s.cota.toFixed(1) : '',
                q(s.clave), q(s.litologia), q(s.roca)
            ].join(','));
        }});
        const blob = new Blob(['\\uFEFF' + rowsCsv.join('\\n')], {{ type: 'text/csv;charset=utf-8;' }});
        const link = document.createElement('a');
        link.download = 'Perfil_Geologico_AA_{clave_actual}.csv';
        link.href = URL.createObjectURL(blob);
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 2000);
    }}

    // ===================================================
    // 📸 9. LÁMINA HD PUBLICABLE (2400×1500) + EXPORTACIÓN glTF 2.0
    // ===================================================
    function capturarPantalla3D() {{
        actualizarBrujulaYEscala();
        renderer.render(scene, camera);
        const W = 2400, H = 1500;
        const off = document.createElement('canvas');
        off.width = W; off.height = H;
        const c = off.getContext('2d');

        c.fillStyle = '#f8fafc';
        c.fillRect(0, 0, W, H);

        // Encabezado oficial CONAGUA
        c.fillStyle = '#691C32';
        c.fillRect(0, 0, W, 112);
        c.fillStyle = '#DDC9A3';
        c.fillRect(0, 106, W, 6);
        c.fillStyle = '#ffffff';
        c.font = 'bold 34px Segoe UI, Arial';
        c.fillText(`MODELO CONCEPTUAL GEOLÓGICO 3D · ${{acuifMeta.clave}} - ${{acuifMeta.nombre}}`, 42, 54);
        c.font = '20px Segoe UI, Arial';
        c.fillStyle = '#f1f5f9';
        c.fillText(
            `Superficie oficial: ${{acuifMeta.area_km2.toLocaleString('es-MX')}} km²  |  Relieve DEM (~${{acuifMeta.px_m}} m · z${{acuifMeta.zoom_dem}}): ${{Math.round(acuifMeta.vmin)}} a ${{Math.round(acuifMeta.vmax)}} msnm  |  Exageración real: ${{exagRealActual.toFixed(1)}}x  |  Remuestreo: ${{remuestreoActual}}`,
            42, 90
        );

        // Escena 3D (izquierda)
        const viewX = 36, viewY = 136, viewW = 1840, viewH = 1245;
        c.fillStyle = '#ffffff';
        c.fillRect(viewX - 2, viewY - 2, viewW + 4, viewH + 4);
        const srcCanvas = renderer.domElement;
        const scaleFit = Math.min(viewW / srcCanvas.width, viewH / srcCanvas.height);
        const dw = srcCanvas.width * scaleFit, dh = srcCanvas.height * scaleFit;
        c.drawImage(srcCanvas, viewX + (viewW - dw) / 2, viewY + (viewH - dh) / 2, dw, dh);
        c.strokeStyle = '#cbd5e1';
        c.lineWidth = 2;
        c.strokeRect(viewX, viewY, viewW, viewH);

        // Panel lateral derecho: Norte, Escala y Simbología SGM
        const panX = 1904, panY = 136, panW = 460, panH = 1245;
        c.fillStyle = '#ffffff';
        c.fillRect(panX, panY, panW, panH);
        c.strokeStyle = '#cbd5e1';
        c.strokeRect(panX, panY, panW, panH);

        c.fillStyle = '#691C32';
        c.fillRect(panX, panY, panW, 44);
        c.fillStyle = '#ffffff';
        c.font = 'bold 20px Segoe UI, Arial';
        c.fillText('SIMBOLOGÍA Y METADATOS', panX + 18, panY + 29);

        // Flecha Norte rotada según cámara actual (letra N nítida sobre la punta roja)
        c.save();
        c.translate(panX + 74, panY + 122);
        c.beginPath(); c.arc(0, 0, 44, 0, Math.PI * 2); c.strokeStyle = '#cbd5e1'; c.lineWidth = 2; c.stroke();
        c.rotate((ultimoAnguloNorteDeg * Math.PI) / 180);
        c.fillStyle = '#691C32'; c.font = 'bold 17px Segoe UI, Arial'; c.textAlign = 'center';
        c.fillText('N', 0, -24);
        c.fillStyle = '#9F2241';
        c.beginPath(); c.moveTo(0, -20); c.lineTo(11, 5); c.lineTo(0, -1); c.lineTo(-11, 5); c.closePath(); c.fill();
        c.fillStyle = '#94a3b8';
        c.beginPath(); c.moveTo(0, 32); c.lineTo(11, 5); c.lineTo(0, 11); c.lineTo(-11, 5); c.closePath(); c.fill();
        c.beginPath(); c.arc(0, 5, 3, 0, Math.PI * 2); c.fillStyle = '#ffffff'; c.fill();
        c.strokeStyle = '#475569'; c.lineWidth = 1.5; c.stroke();
        c.restore();

        // Escala gráfica exacta en píxeles de la lámina HD (0 % error sin importar DPR o tamaño de ventana)
        const cssToPlate = dw / Math.max(window.innerWidth, 1);
        const plateMetersPerPx = ultimaMetersPerPx / Math.max(cssToPlate, 1e-6);
        const pasosPlateM = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000];
        let elegidoPlate = pasosPlateM[0];
        for (let i = 0; i < pasosPlateM.length; i++) {{
            if (pasosPlateM[i] / Math.max(plateMetersPerPx, 1e-6) <= 240) elegidoPlate = pasosPlateM[i];
        }}
        const sW = Math.max(40, Math.min(240, Math.round(elegidoPlate / Math.max(plateMetersPerPx, 1e-6))));
        const lblEscalaPlate = elegidoPlate >= 1000 ? (elegidoPlate / 1000) + ' km' : elegidoPlate + ' m';
        c.textAlign = 'left';
        c.fillStyle = '#1e293b';
        c.font = 'bold 18px Segoe UI, Arial';
        c.fillText('Escala (plano central): ' + lblEscalaPlate, panX + 145, panY + 106);
        c.strokeStyle = '#691C32'; c.lineWidth = 4;
        c.beginPath();
        c.moveTo(panX + 145, panY + 122); c.lineTo(panX + 145, panY + 136);
        c.lineTo(panX + 145 + sW, panY + 136); c.lineTo(panX + 145 + sW, panY + 122);
        c.stroke();

        // Unidades SGM (hasta 24 en 2 columnas)
        c.fillStyle = '#475569';
        c.font = 'bold 18px Segoe UI, Arial';
        c.fillText('Unidades Litológicas SGM:', panX + 20, panY + 210);
        const maxSw = Math.min(leyendaSgm.length, 28);
        c.font = 'bold 16px Segoe UI, Arial';
        for (let i = 0; i < maxSw; i++) {{
            const [clv, hex] = leyendaSgm[i];
            const colIdx = i >= 14 ? 1 : 0;
            const rowIdx = i % 14;
            const sx = panX + 20 + colIdx * 215;
            const sy = panY + 236 + rowIdx * 42;
            c.fillStyle = hex;
            c.fillRect(sx, sy, 26, 22);
            c.strokeStyle = '#334155'; c.lineWidth = 1;
            c.strokeRect(sx, sy, 26, 22);
            c.fillStyle = '#1e293b';
            c.fillText(String(clv).slice(0, 14), sx + 34, sy + 17);
        }}

        // Bloque de simbología auxiliar (fallas y pozos)
        const auxY = panY + 860;
        c.strokeStyle = '#e2e8f0'; c.lineWidth = 2;
        c.beginPath(); c.moveTo(panX + 20, auxY); c.lineTo(panX + panW - 20, auxY); c.stroke();
        c.font = '16px Segoe UI, Arial'; c.fillStyle = '#1e293b';
        c.strokeStyle = '#dc2626'; c.lineWidth = 4; c.setLineDash([10, 6]);
        c.beginPath(); c.moveTo(panX + 22, auxY + 34); c.lineTo(panX + 64, auxY + 34); c.stroke();
        c.setLineDash([]);
        c.fillText('Fallas y Fracturas 1:50k (SGM)', panX + 78, auxY + 40);

        c.fillStyle = '#008a3b'; c.beginPath(); c.arc(panX + 42, auxY + 74, 9, 0, Math.PI * 2); c.fill();
        c.fillStyle = '#1e293b'; c.fillText('Pozos existentes (columna azul = NE)', panX + 78, auxY + 80);

        c.fillStyle = '#9F2241'; c.beginPath(); c.arc(panX + 42, auxY + 112, 9, 0, Math.PI * 2); c.fill();
        c.fillStyle = '#1e293b'; c.fillText('Pozos requeridos / propuestos', panX + 78, auxY + 118);

        // Pie bibliográfico
        c.fillStyle = '#1e293b';
        c.font = '16px Segoe UI, Arial';
        const fechaHoy = new Date().toISOString().slice(0, 10);
        c.fillText(
            `CONAGUA · Gerencia de Aguas Subterráneas · Fuentes: Límites CONAGUA | Litología y Estructuras 1:50k SGM | DEM AWS Terrain/SRTM (EPSG:4326, WGS 84) · ${{fechaHoy}}`,
            42, H - 36
        );

        const link = document.createElement('a');
        link.download = 'Lamina_HD_Modelo_Conceptual_3D_{clave_actual}.png';
        link.href = off.toDataURL('image/png');
        link.click();
    }}

    function exportarGLTF() {{
        if (typeof THREE.GLTFExporter === 'undefined') {{
            alert('El exportador glTF 2.0 no pudo cargarse (requiere conexión al CDN).');
            return;
        }}
        const exportGroup = new THREE.Group();
        exportGroup.name = 'Modelo_Conceptual_3D_{clave_actual}';
        // Conversión Z-up (GIS) -> Y-up (especificación Khronos glTF 2.0 §3.4) para importación exacta en Blender, ArcGIS Pro y Leapfrog
        exportGroup.rotation.x = -Math.PI / 2;
        if (meshAcuifero) exportGroup.add(meshAcuifero.clone());
        if (meshFaldon && meshFaldon.visible) exportGroup.add(meshFaldon.clone());
        if (grupoPozos && grupoPozos.visible && grupoPozos.children.length > 0) exportGroup.add(grupoPozos.clone());
        if (meshFreatico && meshFreatico.visible) exportGroup.add(meshFreatico.clone());
        exportGroup.updateMatrixWorld(true);

        const exporter = new THREE.GLTFExporter();
        exporter.parse(
            exportGroup,
            (gltf) => {{
                const blob = new Blob([JSON.stringify(gltf)], {{ type: 'model/gltf+json' }});
                const link = document.createElement('a');
                link.download = 'Modelo_Conceptual_3D_{clave_actual}.gltf';
                link.href = URL.createObjectURL(blob);
                link.click();
                setTimeout(() => URL.revokeObjectURL(link.href), 3000);
            }},
            {{ binary: false }}
        );
    }}

    window.addEventListener('resize', () => {{
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
        actualizarBrujulaYEscala();
        if (ultimoPerfilData && document.getElementById('section-drawer')?.style.display === 'block') {{
            dibujarCanvasPerfil(ultimoPerfilData);
        }}
        marcarRender();
    }});

    // Render bajo demanda (ahorra CPU/GPU cuando la escena está en reposo)
    function animate() {{
        requestAnimationFrame(animate);
        const cambioCam = controls.update();
        if (needsRender || cambioCam) {{
            renderer.render(scene, camera);
            needsRender = false;
        }}
    }}
    animate();
</script>
</body>
</html>
"""


# =======================================================
# 🌐 11B. MOTOR MAPLIBRE: CON ENTORNO GEOGRÁFICO (MAPA MUNDIAL)
# =======================================================
def construir_html_mapa() -> str:
    int_base = dem_stats["intervalo_base"]
    paso_ini = dem_stats["paso_inicial"]
    max_sl = dem_stats["max_slider"]
    t1, t2, t3, t4 = max_sl // 5, (2 * max_sl) // 5, (3 * max_sl) // 5, (4 * max_sl) // 5
    repda_url_js = _json_seguro(json.dumps(obtener_url_pmtiles(nombre_archivo="repda_nacional.pmtiles") or ""))

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Modelo Conceptual 3D SGM</title>
    <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no" />
    <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
    <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <script src="https://unpkg.com/pmtiles@2.11.0/dist/index.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; background: #e2e8f0; }}

        .hud-elevation {{
            position: absolute; top: 12px; right: 85px; z-index: 1000;
            background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
            color: #1e293b; padding: 7px 12px; border-radius: 8px;
            border: 1.5px solid #691C32;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15); font-size: 11px;
            display: flex; gap: 12px; align-items: center; pointer-events: none;
        }}
        .hud-item b {{ color: #691C32; margin-right: 4px; }}

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

        .workbench-dock {{
            position: absolute; top: 12px; left: 12px; z-index: 1000;
            background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px);
            width: 295px; border-radius: 10px; overflow: hidden;
            box-shadow: 0 6px 20px rgba(0,0,0,0.25); border-top: 4px solid #691C32;
            border-left: 1px solid #E2E8F0; border-right: 1px solid #E2E8F0;
            font-size: 11.5px; color: #1E293B;
        }}
        .dock-header {{
            background: #691C32; color: white; padding: 9px 12px;
            font-weight: 700; display: flex; justify-content: space-between; align-items: center;
        }}
        .dock-body {{ padding: 12px 14px; max-height: 82vh; overflow-y: auto; }}
        .dock-section {{ margin-bottom: 11px; }}
        .dock-section label {{ font-weight: 700; color: #475569; display: block; margin-bottom: 5px; font-size: 11px; }}

        .btn-cam-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }}
        .btn-cam {{
            background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 5px;
            padding: 5px 8px; font-size: 11px; font-weight: 600; color: #334155;
            cursor: pointer; transition: all 0.2s;
        }}
        .btn-cam:hover {{ background: #DDC9A3; color: #691C32; border-color: #691C32; }}

        .slider-ctrl {{ width: 100%; accent-color: #691C32; cursor: pointer; }}

        .btn-screenshot {{
            width: 100%; background: #691C32; color: white; border: none;
            border-radius: 6px; padding: 8px; font-weight: 700; font-size: 11.5px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            gap: 6px; transition: background 0.2s; box-shadow: 0 2px 6px rgba(105,28,50,0.3);
        }}
        .btn-screenshot:hover {{ background: #88102B; }}
    </style>
</head>
<body>
<div id="map"></div>

<div class="hud-elevation">
    <div class="hud-item"><b>LON:</b><span id="hud-lon">--</span></div>
    <div class="hud-item"><b>LAT:</b><span id="hud-lat">--</span></div>
    <div style="color: #15803d;"><b>COTA:</b><span id="hud-ele">-- msnm</span></div>
</div>

<div id="btn-open-dock" class="btn-open-dock-circle" onclick="toggleDock()" title="Abrir Instrumentación 3D" style="display: none;">
    ☰
</div>

<div id="dock-panel" class="workbench-dock">
    <div class="dock-header">
        <div style="display:flex; align-items:center; gap:6px;">
            <span>🛠️ Instrumentación 3D</span>
            <span style="font-size: 10px; opacity: 0.85;">CONAGUA</span>
        </div>
        <button onclick="toggleDock()" style="background:transparent; border:none; color:white; font-size:16px; font-weight:bold; cursor:pointer; line-height:1; padding:2px 5px;" title="Contraer panel">✕</button>
    </div>
    <div class="dock-body">
        <div class="dock-section">
            <label>🧭 Proyección y Vistas:</label>
            <div class="btn-cam-grid">
                <button class="btn-cam" onclick="setCamera('top')">⬆️ Planta (2D)</button>
                <button class="btn-cam" onclick="setCamera('3d')">🧊 Perspectiva 3D</button>
                <button class="btn-cam" onclick="setCamera('south')">⬇️ Vista Sur</button>
                <button class="btn-cam" onclick="setCamera('east')">➡️ Perfil Este</button>
                <button class="btn-cam" onclick="setCamera('west')">⬅️ Perfil Oeste</button>
            </div>
        </div>

        <div class="dock-section">
            <label>📡 Detalle DEM Regional (SRTM):</label>
            <select id="sel-resolucion-dem" style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:5px; padding:6px 8px; font-size:11px; font-weight:600; color:#334155; width:100%; cursor:pointer;" onchange="cambiarResolucionDEM(this.value)">
                <option value="12" selected>Máximo (Zoom 12 · ~{resolucion_dem_m(12, centro_lat):.0f} m)</option>
                <option value="11">Medio (Zoom 11 · ~{resolucion_dem_m(11, centro_lat):.0f} m)</option>
                <option value="10">Regional (Zoom 10 · ~{resolucion_dem_m(10, centro_lat):.0f} m)</option>
            </select>
        </div>

        <div class="dock-section" style="background:#f8fafc; padding:8px; border-radius:6px; border:1px solid #e2e8f0; margin-top:8px;">
            <label style="color:#691C32;">☀️ Simulación Solar (Luz y Sombras):</label>
            <div style="font-size:10.5px; margin-bottom:4px;">Azimut del Sol: <b id="val-azimut" style="color:#691C32;">315° (Noroeste)</b></div>
            <input type="range" class="slider-ctrl" id="slider-azimut" min="0" max="360" step="5" value="315" oninput="cambiarAzimutSolar(this.value)">

            <div style="font-size:10.5px; margin-top:6px; margin-bottom:4px;">Sombreado de Laderas (Hillshade): <b id="val-shade">45%</b></div>
            <input type="range" class="slider-ctrl" id="slider-shade" min="0" max="1" step="0.05" value="0.45" oninput="cambiarIntensidadHillshade(this.value)">
        </div>

        <div class="dock-section" style="background:#f8fafc; padding:8px 10px; border-radius:6px; border:1px solid #e2e8f0;">
            <label style="color:#691C32; margin-bottom:3px;">📏 Curvas de Nivel (Cotas):</label>
            <div style="font-size:11px; margin-bottom:5px;">Equidistancia: <b id="val-cotas" style="color:#691C32;">Cada {paso_ini} m</b></div>
            <input type="range" class="slider-ctrl" id="slider-cotas" min="0" max="{max_sl}" step="{int_base}" value="{paso_ini}" oninput="cambiarEquidistanciaCotas(this.value)">
            <div style="display:flex; justify-content:space-between; font-size:9px; color:#64748B; margin-top:3px; padding:0 1px;">
                <span>Off</span>
                <span>{t1}m</span>
                <span>{t2}m</span>
                <span>{t3}m</span>
                <span>{t4}m</span>
                <span>{max_sl}m</span>
            </div>
        </div>

        <div class="dock-section">
            <label>⛰️ Exageración Relieve: <span id="val-exag" style="color:#691C32;">1.5x</span></label>
            <input type="range" class="slider-ctrl" id="slider-exag" min="1.0" max="5.0" step="0.1" value="1.5" oninput="cambiarExageracion(this.value)">
        </div>

        <div class="dock-section">
            <label>🎨 Opacidad Litología SGM: <span id="val-opac">85%</span></label>
            <input type="range" class="slider-ctrl" id="slider-opac" min="0" max="1" step="0.05" value="0.85" oninput="cambiarOpacidad(this.value)">

            <div style="margin-top: 8px; display: flex; flex-direction: column; gap: 5px;">
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-lines" checked onchange="toggleCapa('geologia-lines', this.checked)"> Contactos Geológicos SGM
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-border" checked onchange="toggleCapa('borde-line', this.checked)"> Límite Acuífero CONAGUA
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-estructuras-w" checked onchange="toggleCapa('estructuras-layer', this.checked)"> ⚡ Fallas y Fracturas 1:50k
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-pozos" checked onchange="toggleVisibilidadPozos(this.checked)"> 📍 Pozos en Superficie (2D)
                </label>
                <label style="font-weight:normal; display:flex; align-items:center; gap:6px;">
                    <input type="checkbox" id="chk-repda" onchange="toggleRepda(this.checked)"> 💧 Aprovechamientos REPDA (CONAGUA)
                </label>
            </div>
        </div>

        <button class="btn-screenshot" onclick="capturarPantalla()">
            📸 Capturar Lámina HD (PNG)
        </button>
    </div>
</div>

<script>
    const dataGeologia = {geojson_geologia};
    const dataEstructuras = {geojson_estructuras};
    const dataBorde = {geojson_borde};
    const dataCurvas = {geojson_curvas_cota};
    const dataPozos = {pozos_mapa_json};
    const leyendaSgm = {leyenda_sgm_json};
    const acuifMeta = {acuifero_meta_json};
    const REPDA_PMTILES_URL = {repda_url_js};

    if (typeof pmtiles !== 'undefined') {{
        const _pmtProto = new pmtiles.Protocol();
        maplibregl.addProtocol('pmtiles', _pmtProto.tile);
    }}

    const repdaUseColors = {{
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
    }};

    const bboxAcuifero = [[{minx}, {miny}], [{maxx}, {maxy}]];

    function escapeHtml(val) {{
        if (val === null || val === undefined) return '';
        return String(val)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }}

    function rumboCardinal8(deg) {{
        const rumbos = ['Norte', 'Noreste', 'Este', 'Sureste', 'Sur', 'Suroeste', 'Oeste', 'Noroeste'];
        const idx = Math.round((((deg % 360) + 360) % 360) / 45) % 8;
        return rumbos[idx];
    }}

    function limpiarFormacion(rawForm, litologia) {{
        const s = rawForm ? String(rawForm).trim() : '';
        const up = s.toUpperCase();
        if (!s || up === 'NINGUNO' || up === 'NULL' || up === 'NONE' || up === 'INDETERMINADO' || up === 'NO APLICABLE') {{
            return litologia && litologia !== 'No aplicable' ? litologia : 'Formación Sin Asignar';
        }}
        return s;
    }}

    function limpiarRoca(rawRoca) {{
        const s = rawRoca ? String(rawRoca).trim() : '';
        const up = s.toUpperCase();
        if (!s || up === 'NULL' || up === 'NONE' || up === 'NO APLICABLE' || up === 'NINGUNO') return 'S/D';
        return s;
    }}

    const iconExpandSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
    const iconCompressSVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#111111" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>`;

    const map = new maplibregl.Map({{
        container: 'map',
        preserveDrawingBuffer: true,
        style: {{
            version: 8,
            sources: {{
                'basemap-source': {{
                    'type': 'raster',
                    'tiles': ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}'],
                    'tileSize': 256,
                    'attribution': '© Esri'
                }},
                'terrainSource': {{
                    'type': 'raster-dem',
                    'encoding': 'terrarium',
                    'tiles': ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{{z}}/{{x}}/{{y}}.png'],
                    'tileSize': 256,
                    'maxzoom': 12
                }}
            }},
            layers: [
                {{
                    'id': 'basemap-layer',
                    'type': 'raster',
                    'source': 'basemap-source',
                    'minzoom': 0,
                    'maxzoom': 19
                }},
                {{
                    'id': 'hillshade-layer',
                    'type': 'hillshade',
                    'source': 'terrainSource',
                    'paint': {{
                        'hillshade-shadow-color': 'rgba(15, 23, 42, 0.45)',
                        'hillshade-highlight-color': 'rgba(255, 255, 255, 0.85)',
                        'hillshade-accent-color': 'rgba(71, 85, 105, 0.3)',
                        'hillshade-illumination-direction': 315,
                        'hillshade-exaggeration': 0.45
                    }}
                }}
            ],
            sky: {{
                'sky-color': '#bae6fd',
                'sky-horizon-blend': 0.5,
                'horizon-color': '#f8fafc'
            }}
        }},
        center: [{centro_lon}, {centro_lat}],
        zoom: 10.5,
        pitch: 52,
        bearing: -12,
        maxPitch: 85
    }});

    let estadoGuardado = localStorage.getItem('dock_3d_abierto');
    let dockAbierto = estadoGuardado !== null ? (estadoGuardado === 'true') : true;

    function aplicarEstadoVisualDock() {{
        const dock = document.getElementById('dock-panel');
        const btnOpen = document.getElementById('btn-open-dock');
        if (dock && btnOpen) {{
            dock.style.display = dockAbierto ? 'block' : 'none';
            btnOpen.style.display = dockAbierto ? 'none' : 'flex';
        }}
    }}

    let marcadoresDOM = [];
    let exageracionActualMap = 1.5;
    let maxZoomDemActual = 12;
    let capasInicializadas = false;
    let popupActivo = null;
    let clickConsumido = false;

    if (!REPDA_PMTILES_URL) {{
        const chkR = document.getElementById('chk-repda');
        if (chkR) {{
            chkR.disabled = true;
            if (chkR.parentElement) {{
                chkR.parentElement.style.opacity = '0.55';
                chkR.parentElement.title = 'Capa repda_nacional.pmtiles no disponible en este servidor.';
            }}
        }}
    }}

    function obtenerCotaRealMsnm(lngLat) {{
        if (!map.terrain) return null;
        try {{
            const ll = Array.isArray(lngLat)
                ? new maplibregl.LngLat(lngLat[0], lngLat[1])
                : lngLat;
            const z = Math.max(0, Math.min(maxZoomDemActual, Math.floor(map.getZoom())));
            const raw = map.terrain.getElevationForLngLatZoom(ll, z);
            if (raw === null || raw === undefined || Number.isNaN(raw)) return null;
            const ex = Math.max(exageracionActualMap, 0.01);
            const msnm = raw / ex;
            return Number.isFinite(msnm) ? msnm : null;
        }} catch (err) {{
            return null;
        }}
    }}

    aplicarEstadoVisualDock();

    map.on('style.load', () => {{
        if (capasInicializadas) return;
        capasInicializadas = true;

        map.setTerrain({{ 'source': 'terrainSource', 'exaggeration': exageracionActualMap }});

        const padLeftInicial = dockAbierto ? 320 : 40;
        map.fitBounds(bboxAcuifero, {{
            padding: {{ top: 60, bottom: 40, left: padLeftInicial, right: 40 }},
            pitch: 52,
            bearing: -12,
            duration: 0
        }});

        // 1. Geología SGM
        if (dataGeologia.features && dataGeologia.features.length > 0) {{
            map.addSource('geologia-sgm', {{ 'type': 'geojson', 'data': dataGeologia }});
            map.addLayer({{
                'id': 'geologia-fill',
                'type': 'fill',
                'source': 'geologia-sgm',
                'paint': {{ 'fill-color': ['get', 'COLOR_HEX'], 'fill-opacity': 0.85 }}
            }});
            map.addLayer({{
                'id': 'geologia-lines',
                'type': 'line',
                'source': 'geologia-sgm',
                'paint': {{ 'line-color': '#334155', 'line-width': 1.2, 'line-opacity': 0.75 }}
            }});

            map.on('mouseenter', 'geologia-fill', () => {{ map.getCanvas().style.cursor = 'pointer'; }});
            map.on('mouseleave', 'geologia-fill', () => {{ map.getCanvas().style.cursor = ''; }});

            map.on('click', 'geologia-fill', (e) => {{
                if (clickConsumido) return;
                if (e.originalEvent && e.originalEvent.target && e.originalEvent.target.closest('.maplibregl-marker')) return;

                if (popupActivo) {{ popupActivo.remove(); popupActivo = null; }}

                const p = e.features[0].properties;
                const litologia = p.LITOLOGIA || 'Indiferenciada';
                const formacion = limpiarFormacion(p.FORMACION, litologia);
                const claveSgm = p.CLAVE_SGM || p.ETIQUETA_LITO || 'S/C';
                const roca = limpiarRoca(p.ROCA);
                const colorHex = p.COLOR_HEX || '#B0BEC5';

                let edadGeo = p.PERIODO || '';
                if (p.EDINICIO || p.EDFINAL) {{
                    const ini = p.EDINICIO || '';
                    const fin = p.EDFINAL || '';
                    edadGeo += (ini === fin || !fin) ? ` (${{ini}})` : ` (${{ini}} - ${{fin}})`;
                }}
                if (!edadGeo.trim()) edadGeo = p.ERA || 'S/D';

                const elevTerreno = obtenerCotaRealMsnm(e.lngLat);
                const elevTxt = elevTerreno !== null ? Math.round(elevTerreno) + ' msnm' : 'S/D';

                popupActivo = new maplibregl.Popup({{ maxWidth: '320px', closeOnClick: true }})
                    .setLngLat(e.lngLat)
                    .setHTML(`
                        <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; line-height:1.5;">
                            <div style="display:flex; align-items:center; justify-content:space-between; gap:6px; border-bottom:1.5px solid #E2E8F0; padding-bottom:4px; margin-bottom:6px;">
                                <div style="display:flex; align-items:center; gap:6px;">
                                    <span style="width:13px; height:13px; background:${{escapeHtml(colorHex)}}; border-radius:3px; border:1px solid #475569; display:inline-block;"></span>
                                    <h4 style="margin:0; color:#691C32; font-size:13px; font-weight:700;">${{escapeHtml(formacion)}}</h4>
                                </div>
                                <span style="background:#F1F5F9; border:1px solid #CBD5E1; color:#334155; font-size:9.5px; font-weight:700; padding:1px 4px; border-radius:3px; white-space:nowrap;">${{escapeHtml(claveSgm)}}</span>
                            </div>
                            <b>Litología:</b> <span style="color:#0f172a; font-weight:600;">${{escapeHtml(litologia)}}</span><br>
                            <b>Tipo de Roca:</b> ${{escapeHtml(roca)}}<br>
                            <b>Edad Geológica:</b> ${{escapeHtml(edadGeo)}}<br>
                            <b>Cota Terreno:</b> <span style="color:#008A3B; font-weight:bold;">${{elevTxt}}</span><br>
                            <span style="color:#64748B; font-size:10px;">Coords: ${{e.lngLat.lat.toFixed(4)}}°, ${{e.lngLat.lng.toFixed(4)}}°</span>
                        </div>
                    `)
                    .addTo(map);
            }});
        }}

        // 2. Fallas y Fracturas 1:50k
        if (dataEstructuras.features && dataEstructuras.features.length > 0) {{
            map.addSource('estructuras-sgm-src', {{ 'type': 'geojson', 'data': dataEstructuras }});
            map.addLayer({{
                'id': 'estructuras-layer',
                'type': 'line',
                'source': 'estructuras-sgm-src',
                'paint': {{ 'line-color': '#dc2626', 'line-width': 2.8, 'line-dasharray': [3, 2] }}
            }});

            map.on('mouseenter', 'estructuras-layer', () => {{ map.getCanvas().style.cursor = 'pointer'; }});
            map.on('mouseleave', 'estructuras-layer', () => {{ map.getCanvas().style.cursor = ''; }});

            map.on('click', 'estructuras-layer', (e) => {{
                if (e.originalEvent && e.originalEvent.target && e.originalEvent.target.closest('.maplibregl-marker')) return;
                clickConsumido = true;
                setTimeout(() => {{ clickConsumido = false; }}, 200);

                if (popupActivo) {{ popupActivo.remove(); popupActivo = null; }}

                const p = e.features[0].properties;
                const azRaw = p.AZIMUTH ?? p.Azimuth ?? p.azimuth ?? p.AZIMUT;
                const azNum = parseFloat(azRaw);
                const azTxt = (azRaw !== undefined && azRaw !== null && !Number.isNaN(azNum) && azNum > 0) ? azNum.toFixed(1) + '°' : 'S/D';

                const incRaw = p.INCLINACION ?? p.Inclinacion ?? p.inclinacion;
                const incNum = parseFloat(incRaw);
                const incTxt = (incRaw !== undefined && incRaw !== null && !Number.isNaN(incNum) && incNum > 0) ? incNum.toFixed(0) + '°' : 'S/D';

                const tipoEstr = p.ESTRUCTURAS || p.TIPO_ESTR || 'Estructura Geológica';
                const rawNom = p.NOMBRE || p.NOM_ESTR;
                const tieneNom = rawNom && !['', 'NULL', 'NONE', 'NINGUNO', 'SIN NOMBRE'].includes(String(rawNom).trim().toUpperCase());
                const tituloMostrar = tieneNom ? String(rawNom).trim() : tipoEstr;

                const elevTerreno = obtenerCotaRealMsnm(e.lngLat);
                const elevTxt = elevTerreno !== null ? Math.round(elevTerreno) + ' msnm' : 'S/D';

                popupActivo = new maplibregl.Popup({{ maxWidth: '320px', closeOnClick: true }})
                    .setLngLat(e.lngLat)
                    .setHTML(`
                        <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; line-height:1.5;">
                            <div style="display:flex; align-items:center; gap:6px; border-bottom:1.5px solid #E2E8F0; padding-bottom:4px; margin-bottom:6px;">
                                <span style="color:#dc2626; font-size:15px;">⚡</span>
                                <h4 style="margin:0; color:#dc2626; font-size:13px; font-weight:700;">${{escapeHtml(tituloMostrar)}}</h4>
                            </div>
                            <b>Tipo de Estructura:</b> ${{escapeHtml(tipoEstr)}}<br>
                            <b>Azimut de Rumbo:</b> <span style="color:#0f172a; font-weight:bold;">${{azTxt}}</span><br>
                            <b>Inclinación / Echado:</b> ${{incTxt}}<br>
                            <b>Cota Terreno:</b> <span style="color:#008A3B; font-weight:bold;">${{elevTxt}}</span><br>
                            <span style="color:#64748B; font-size:10px;">Coords: ${{e.lngLat.lat.toFixed(4)}}°, ${{e.lngLat.lng.toFixed(4)}}°</span>
                        </div>
                    `)
                    .addTo(map);
            }});
        }}

        // 3. Curvas de Nivel
        if (dataCurvas.features && dataCurvas.features.length > 0) {{
            map.addSource('curvas-cota-src', {{ 'type': 'geojson', 'data': dataCurvas }});
            map.addLayer({{
                'id': 'curvas-cota-layer',
                'type': 'line',
                'source': 'curvas-cota-src',
                'filter': ['==', ['%', ['get', 'cota'], {paso_ini}], 0],
                'paint': {{ 'line-color': '#475569', 'line-width': 1.1, 'line-opacity': 0.7, 'line-dasharray': [2, 1] }}
            }});
        }}

        // 4. Límite Oficial Acuífero
        map.addSource('borde-acuifero', {{ 'type': 'geojson', 'data': dataBorde }});
        map.addLayer({{
            'id': 'borde-line',
            'type': 'line',
            'source': 'borde-acuifero',
            'paint': {{ 'line-color': '#691C32', 'line-width': 3.5, 'line-dasharray': [3, 2] }}
        }});

        // 5. Pozos en superficie (2D sobre terreno 3D)
        if (dataPozos && dataPozos.length > 0) {{
            dataPozos.forEach(p => {{
                const el = document.createElement('div');
                const tipo = (p.tipo || '').toLowerCase();
                let color = p.color_hex;
                if (!color) {{
                    color = (tipo.includes('requerid') || tipo.includes('nuevo') || tipo.includes('propuest')) ? '#9F2241' : '#008a3b';
                }}
                el.style.width = '14px';
                el.style.height = '14px';
                el.style.borderRadius = tipo.includes('tanque') ? '3px' : '50%';
                el.style.backgroundColor = color;
                el.style.border = '2px solid #ffffff';
                el.style.boxShadow = '0 2px 6px rgba(0,0,0,0.5)';
                el.style.cursor = 'pointer';

                const latNum = parseFloat(p.lat);
                const lonNum = parseFloat(p.lon);
                const profTxt = (p.profundidad && p.profundidad > 0) ? (p.profundidad + ' m') : 'Sin dato';

                const popupPozo = new maplibregl.Popup({{ offset: 12, maxWidth: '300px' }});
                popupPozo.on('open', () => {{
                    if (popupActivo && popupActivo !== popupPozo) popupActivo.remove();
                    popupActivo = popupPozo;
                    const elevP = (p.cota_geotiff !== null && p.cota_geotiff !== undefined)
                        ? p.cota_geotiff
                        : obtenerCotaRealMsnm([lonNum, latNum]);
                    const elevTxt = elevP !== null
                        ? ((p.cota_geotiff !== null && p.cota_geotiff !== undefined) ? elevP.toFixed(1) + ' msnm (DEM)' : Math.round(elevP) + ' msnm')
                        : 'S/D';
                    const neVal = (p.nivel_estatico !== null && p.nivel_estatico !== undefined) ? parseFloat(p.nivel_estatico) : null;
                    const neRow = neVal !== null
                        ? `<b>Nivel Estático:</b> <span style="color:#0284c7; font-weight:bold;">${{neVal}} m</span><br>`
                          + (elevP !== null ? `<b>Elev. Piezométrica:</b> <span style="color:#0369a1; font-weight:bold;">${{(elevP - neVal).toFixed(1)}} msnm</span><br>` : '')
                        : '';
                    popupPozo.setHTML(`
                        <div style="font-family:'Segoe UI',sans-serif; font-size:11.5px; line-height:1.5; min-width:160px;">
                            <div style="display:flex; align-items:center; gap:6px; border-bottom:1.5px solid #E2E8F0; padding-bottom:4px; margin-bottom:6px;">
                                <span style="color:#691C32; font-size:14px;">📍</span>
                                <h4 style="margin:0; color:#691C32; font-size:13px; font-weight:700;">${{escapeHtml(p.nombre || 'Pozo')}}</h4>
                            </div>
                            <b>Tipo:</b> ${{escapeHtml(p.tipo || 'Infraestructura')}}<br>
                            <b>Profundidad:</b> <span style="color:#691C32; font-weight:bold;">${{profTxt}}</span><br>
                            ${{neRow}}
                            <b>Cota Terreno:</b> <span style="color:#008A3B; font-weight:bold;">${{elevTxt}}</span><br>
                            <span style="color:#64748B; font-size:10px;">Coords: ${{latNum.toFixed(4)}}°, ${{lonNum.toFixed(4)}}°</span>
                        </div>
                    `);
                }});

                new maplibregl.Marker({{ element: el }})
                    .setLngLat([lonNum, latNum])
                    .setPopup(popupPozo)
                    .addTo(map);

                marcadoresDOM.push(el);
            }});
        }}
    }});

    map.on('mousemove', (e) => {{
        document.getElementById('hud-lon').innerText = e.lngLat.lng.toFixed(4) + '°';
        document.getElementById('hud-lat').innerText = e.lngLat.lat.toFixed(4) + '°';
        const elevation = obtenerCotaRealMsnm(e.lngLat);
        document.getElementById('hud-ele').innerText = elevation !== null ? Math.round(elevation) + ' msnm' : '--';
    }});

    function setCamera(mode) {{
        const padLeft = dockAbierto ? 320 : 40;
        const pad = {{ top: 60, bottom: 40, left: padLeft, right: 40 }};
        if (mode === 'top') map.fitBounds(bboxAcuifero, {{ padding: pad, pitch: 0, bearing: 0, duration: 800 }});
        else if (mode === '3d') map.fitBounds(bboxAcuifero, {{ padding: pad, pitch: 55, bearing: -15, duration: 800 }});
        else if (mode === 'south') map.fitBounds(bboxAcuifero, {{ padding: pad, pitch: 60, bearing: 180, duration: 800 }});
        else if (mode === 'east') map.fitBounds(bboxAcuifero, {{ padding: pad, pitch: 60, bearing: 90, duration: 800 }});
        else if (mode === 'west') map.fitBounds(bboxAcuifero, {{ padding: pad, pitch: 60, bearing: 270, duration: 800 }});
    }}

    function toggleDock() {{
        dockAbierto = !dockAbierto;
        localStorage.setItem('dock_3d_abierto', dockAbierto ? 'true' : 'false');
        aplicarEstadoVisualDock();
        const padLeft = dockAbierto ? 320 : 40;
        map.fitBounds(bboxAcuifero, {{
            padding: {{ top: 60, bottom: 40, left: padLeft, right: 40 }},
            pitch: map.getPitch(),
            bearing: map.getBearing(),
            duration: 500
        }});
    }}

    function toggleVisibilidadPozos(visible) {{
        marcadoresDOM.forEach(el => {{ el.style.display = visible ? 'block' : 'none'; }});
    }}

    function cambiarEquidistanciaCotas(val) {{
        const step = parseInt(val, 10);
        const lbl = document.getElementById('val-cotas');
        if (!map.getLayer('curvas-cota-layer')) return;

        if (step === 0) {{
            lbl.innerText = 'Desactivadas';
            lbl.style.color = '#64748B';
            map.setLayoutProperty('curvas-cota-layer', 'visibility', 'none');
        }} else {{
            lbl.innerText = 'Cada ' + step + ' m';
            lbl.style.color = '#691C32';
            map.setLayoutProperty('curvas-cota-layer', 'visibility', 'visible');
            map.setFilter('curvas-cota-layer', ['==', ['%', ['get', 'cota'], step], 0]);
        }}
        map.triggerRepaint();
    }}

    let idFuenteTerrenoActual = 'terrainSource';

    function cambiarResolucionDEM(zoomVal) {{
        const z = parseInt(zoomVal, 10);
        const exag = parseFloat(document.getElementById('slider-exag').value) || 1.5;
        const azimut = parseInt(document.getElementById('slider-azimut').value, 10) || 315;
        const shade = parseFloat(document.getElementById('slider-shade').value);

        const fuenteVieja = idFuenteTerrenoActual;
        const fuenteNueva = 'terrainSource-z' + z + '-' + Date.now();

        map.addSource(fuenteNueva, {{
            'type': 'raster-dem',
            'encoding': 'terrarium',
            'tiles': ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{{z}}/{{x}}/{{y}}.png'],
            'tileSize': 256,
            'maxzoom': z
        }});

        map.setTerrain({{ 'source': fuenteNueva, 'exaggeration': exag }});
        exageracionActualMap = exag;
        maxZoomDemActual = z;
        idFuenteTerrenoActual = fuenteNueva;

        if (map.getLayer('hillshade-layer')) map.removeLayer('hillshade-layer');
        map.addLayer({{
            'id': 'hillshade-layer',
            'type': 'hillshade',
            'source': fuenteNueva,
            'paint': {{
                'hillshade-shadow-color': 'rgba(15, 23, 42, 0.45)',
                'hillshade-highlight-color': 'rgba(255, 255, 255, 0.85)',
                'hillshade-accent-color': 'rgba(71, 85, 105, 0.3)',
                'hillshade-illumination-direction': azimut,
                'hillshade-exaggeration': Number.isNaN(shade) ? 0.45 : shade
            }}
        }}, map.getLayer('geologia-fill') ? 'geologia-fill' : undefined);

        setTimeout(() => {{
            if (map.getSource(fuenteVieja)) {{
                try {{ map.removeSource(fuenteVieja); }} catch (e) {{}}
            }}
        }}, 600);
        map.triggerRepaint();
    }}

    function cambiarExageracion(val) {{
        const exagNum = parseFloat(val);
        exageracionActualMap = exagNum;
        document.getElementById('val-exag').innerText = exagNum.toFixed(1) + 'x';
        map.setTerrain({{ 'source': idFuenteTerrenoActual, 'exaggeration': exagNum }});
        map.triggerRepaint();
    }}

    function cambiarAzimutSolar(val) {{
        const deg = parseInt(val, 10);
        document.getElementById('val-azimut').innerText = deg + '° (' + rumboCardinal8(deg) + ')';
        if (map.getLayer('hillshade-layer')) {{
            map.setPaintProperty('hillshade-layer', 'hillshade-illumination-direction', deg);
        }}
        map.triggerRepaint();
    }}

    function cambiarIntensidadHillshade(val) {{
        document.getElementById('val-shade').innerText = Math.round(val * 100) + '%';
        if (map.getLayer('hillshade-layer')) {{
            map.setPaintProperty('hillshade-layer', 'hillshade-exaggeration', parseFloat(val));
        }}
        map.triggerRepaint();
    }}

    function cambiarOpacidad(val) {{
        document.getElementById('val-opac').innerText = Math.round(val * 100) + '%';
        if (map.getLayer('geologia-fill')) {{
            map.setPaintProperty('geologia-fill', 'fill-opacity', parseFloat(val));
        }}
        map.triggerRepaint();
    }}

    function toggleCapa(id, checked) {{
        if (map.getLayer(id)) {{
            map.setLayoutProperty(id, 'visibility', checked ? 'visible' : 'none');
        }}
        map.triggerRepaint();
    }}

    // Capa bajo demanda REPDA Nacional (0 bytes hasta activar checkbox)
    let repdaInitialized = false;
    const repdaHoverPopup = new maplibregl.Popup({{ closeButton: false, closeOnClick: false, offset: 10 }});

    function ensureRepdaLayer() {{
        if (repdaInitialized || !REPDA_PMTILES_URL) return;
        repdaInitialized = true;

        map.addSource('repda-src', {{
            type: 'vector',
            url: 'pmtiles://' + REPDA_PMTILES_URL,
            minzoom: 4,
            maxzoom: 8
        }});

        const colorMatch = ['match', ['get', 'u']];
        Object.entries(repdaUseColors).forEach(([uso, col]) => colorMatch.push(uso, col));
        colorMatch.push('#64748b');

        map.addLayer({{
            id: 'repda-points',
            type: 'circle',
            source: 'repda-src',
            'source-layer': 'repda',
            layout: {{ visibility: 'visible' }},
            paint: {{
                'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 1.8, 8, 3.6, 11, 5.2, 14, 7.0],
                'circle-color': colorMatch,
                'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 4, 0.4, 9, 1.2],
                'circle-stroke-color': '#ffffff',
                'circle-opacity': 0.92
            }}
        }});

        let lastRepdaKey = null;
        map.on('mousemove', 'repda-points', (e) => {{
            if (!e.features || !e.features.length) return;
            map.getCanvas().style.cursor = 'pointer';
            const p = e.features[0].properties;
            const k = `${{p.f || ''}}|${{p.u || ''}}|${{p.v || ''}}`;
            if (lastRepdaKey !== k) {{
                lastRepdaKey = k;
                const vol = Number(p.v || 0).toLocaleString('es-MX');
                repdaHoverPopup.setLngLat(e.lngLat).setHTML(
                    `<div style="font-family:'Segoe UI',sans-serif;font-size:11px;"><b>REPDA · ${{escapeHtml(p.u || 'OTROS')}}</b><br>` +
                    `<span style="color:#475569;">Folio: ${{escapeHtml(p.f || 'S/D')}} · ${{vol}} m³/año</span></div>`
                );
            }} else {{
                repdaHoverPopup.setLngLat(e.lngLat);
            }}
            if (!repdaHoverPopup.isOpen()) repdaHoverPopup.addTo(map);
        }});
        map.on('mouseleave', 'repda-points', () => {{
            lastRepdaKey = null;
            map.getCanvas().style.cursor = '';
            repdaHoverPopup.remove();
        }});
        map.on('click', 'repda-points', (e) => {{
            if (!e.features || !e.features.length) return;
            if (e.originalEvent && e.originalEvent.target && e.originalEvent.target.closest('.maplibregl-marker')) return;
            clickConsumido = true;
            setTimeout(() => {{ clickConsumido = false; }}, 200);
            if (popupActivo) {{ popupActivo.remove(); popupActivo = null; }}

            const p = e.features[0].properties;
            const vol = Number(p.v || 0).toLocaleString('es-MX');
            const usoCol = repdaUseColors[p.u] || '#64748b';
            const elevR = obtenerCotaRealMsnm(e.lngLat);
            const elevTxt = elevR !== null ? Math.round(elevR) + ' msnm' : 'S/D';

            let geoHtml = '<span style="color:#64748B;">Fuera de cobertura SGM recortada</span>';
            if (map.getLayer('geologia-fill')) {{
                const gHits = map.queryRenderedFeatures(e.point, {{ layers: ['geologia-fill'] }});
                if (gHits && gHits.length) {{
                    const gp = gHits[0].properties;
                    const clv = gp.CLAVE_SGM || gp.ETIQUETA_LITO || 'S/C';
                    const col = gp.COLOR_HEX || '#B0BEC5';
                    const lito = gp.LITOLOGIA || 'Indiferenciada';
                    geoHtml = `<div style="display:flex;align-items:center;gap:6px;">` +
                        `<span style="width:11px;height:11px;background:${{escapeHtml(col)}};border:1px solid #475569;border-radius:2px;display:inline-block;"></span>` +
                        `<b>${{escapeHtml(clv)}}</b> · ${{escapeHtml(lito)}}</div>`;
                }}
            }}

            popupActivo = new maplibregl.Popup({{ maxWidth: '320px', closeOnClick: true }})
                .setLngLat(e.lngLat)
                .setHTML(`
                    <div style="font-family:'Segoe UI',sans-serif;font-size:11.5px;line-height:1.5;">
                        <div style="display:flex;align-items:center;justify-content:space-between;border-bottom:1.5px solid #E2E8F0;padding-bottom:4px;margin-bottom:6px;">
                            <b style="color:#691C32;font-size:12.5px;">💧 Aprovechamiento REPDA</b>
                            <span style="background:${{usoCol}};color:#fff;font-size:9.5px;font-weight:700;padding:1px 6px;border-radius:4px;">${{escapeHtml(p.u || 'OTROS')}}</span>
                        </div>
                        <b>Folio:</b> ${{escapeHtml(p.f || 'S/D')}}<br>
                        <b>Expediente:</b> ${{escapeHtml(p.e || 'S/D')}}<br>
                        <b>Titular:</b> ${{escapeHtml(p.t || 'S/D')}}<br>
                        <b>Volumen:</b> <b>${{vol}} m³/año</b><br>
                        <b>Cota Terreno:</b> <span style="color:#008A3B;font-weight:bold;">${{elevTxt}}</span><br>
                        <div style="margin-top:5px;padding-top:4px;border-top:1px dashed #cbd5e1;">
                            <span style="font-size:10px;font-weight:700;color:#691C32;">GEOLOGÍA SGM EN SITIO</span><br>
                            ${{geoHtml}}
                        </div>
                    </div>
                `)
                .addTo(map);
        }});
    }}

    function toggleRepda(checked) {{
        if (checked) {{
            ensureRepdaLayer();
            if (map.getLayer('repda-points')) {{
                map.setLayoutProperty('repda-points', 'visibility', 'visible');
            }}
        }} else if (map.getLayer('repda-points')) {{
            map.setLayoutProperty('repda-points', 'visibility', 'none');
            repdaHoverPopup.remove();
        }}
        map.triggerRepaint();
    }}

    function capturarPantalla() {{
        const srcCanvas = map.getCanvas();
        const W = 2400, H = 1500;
        const off = document.createElement('canvas');
        off.width = W; off.height = H;
        const c = off.getContext('2d');

        c.fillStyle = '#f8fafc';
        c.fillRect(0, 0, W, H);
        c.fillStyle = '#691C32';
        c.fillRect(0, 0, W, 112);
        c.fillStyle = '#DDC9A3';
        c.fillRect(0, 106, W, 6);
        c.fillStyle = '#ffffff';
        c.font = 'bold 34px Segoe UI, Arial';
        c.fillText(`MODELO CONCEPTUAL REGIONAL 3D · ${{acuifMeta.clave}} - ${{acuifMeta.nombre}}`, 42, 54);
        c.font = '20px Segoe UI, Arial';
        c.fillStyle = '#f1f5f9';
        c.fillText(
            `Superficie oficial: ${{acuifMeta.area_km2.toLocaleString('es-MX')}} km²  |  Relieve DEM: ${{Math.round(acuifMeta.vmin)}} a ${{Math.round(acuifMeta.vmax)}} msnm  |  Exageración terreno: ${{exageracionActualMap.toFixed(1)}}x`,
            42, 90
        );

        const viewX = 36, viewY = 136, viewW = 1840, viewH = 1245;
        c.fillStyle = '#ffffff';
        c.fillRect(viewX - 2, viewY - 2, viewW + 4, viewH + 4);
        const sf = Math.min(viewW / srcCanvas.width, viewH / srcCanvas.height);
        const dw = srcCanvas.width * sf, dh = srcCanvas.height * sf;
        c.drawImage(srcCanvas, viewX + (viewW - dw) / 2, viewY + (viewH - dh) / 2, dw, dh);
        c.strokeStyle = '#cbd5e1'; c.lineWidth = 2;
        c.strokeRect(viewX, viewY, viewW, viewH);

        const panX = 1904, panY = 136, panW = 460, panH = 1245;
        c.fillStyle = '#ffffff'; c.fillRect(panX, panY, panW, panH);
        c.strokeStyle = '#cbd5e1'; c.strokeRect(panX, panY, panW, panH);
        c.fillStyle = '#691C32'; c.fillRect(panX, panY, panW, 44);
        c.fillStyle = '#ffffff'; c.font = 'bold 20px Segoe UI, Arial';
        c.fillText('SIMBOLOGÍA Y METADATOS', panX + 18, panY + 29);

        // Flecha Norte rotada según rumbo actual del mapa (-bearing)
        const northRadMap = (-map.getBearing() * Math.PI) / 180;
        c.save();
        c.translate(panX + 74, panY + 122);
        c.beginPath(); c.arc(0, 0, 44, 0, Math.PI * 2); c.strokeStyle = '#cbd5e1'; c.lineWidth = 2; c.stroke();
        c.rotate(northRadMap);
        c.fillStyle = '#691C32'; c.font = 'bold 17px Segoe UI, Arial'; c.textAlign = 'center';
        c.fillText('N', 0, -24);
        c.fillStyle = '#9F2241';
        c.beginPath(); c.moveTo(0, -20); c.lineTo(11, 5); c.lineTo(0, -1); c.lineTo(-11, 5); c.closePath(); c.fill();
        c.fillStyle = '#94a3b8';
        c.beginPath(); c.moveTo(0, 32); c.lineTo(11, 5); c.lineTo(0, 11); c.lineTo(-11, 5); c.closePath(); c.fill();
        c.beginPath(); c.arc(0, 5, 3, 0, Math.PI * 2); c.fillStyle = '#ffffff'; c.fill();
        c.strokeStyle = '#475569'; c.lineWidth = 1.5; c.stroke();
        c.restore();

        // Escala métrica exacta en el centro del mapa (lat, zoom) escalada al tamaño real de la lámina HD
        const cLat = map.getCenter().lat;
        const mapCssW = Math.max(srcCanvas.clientWidth || window.innerWidth, 1);
        const mPerCssPx = (156543.03392 * Math.cos(cLat * Math.PI / 180.0)) / Math.pow(2, map.getZoom());
        const cssToPlateMap = dw / mapCssW;
        const plateMPerPx = mPerCssPx / Math.max(cssToPlateMap, 1e-6);
        const pasosMapM = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000];
        let elegidoMap = pasosMapM[0];
        for (let i = 0; i < pasosMapM.length; i++) {{
            if (pasosMapM[i] / Math.max(plateMPerPx, 1e-6) <= 240) elegidoMap = pasosMapM[i];
        }}
        const sWMap = Math.max(40, Math.min(240, Math.round(elegidoMap / Math.max(plateMPerPx, 1e-6))));
        const lblEscMap = elegidoMap >= 1000 ? (elegidoMap / 1000) + ' km' : elegidoMap + ' m';
        c.textAlign = 'left';
        c.fillStyle = '#1e293b'; c.font = 'bold 18px Segoe UI, Arial';
        c.fillText('Escala (centro): ' + lblEscMap, panX + 145, panY + 106);
        c.strokeStyle = '#691C32'; c.lineWidth = 4;
        c.beginPath();
        c.moveTo(panX + 145, panY + 122); c.lineTo(panX + 145, panY + 136);
        c.lineTo(panX + 145 + sWMap, panY + 136); c.lineTo(panX + 145 + sWMap, panY + 122);
        c.stroke();

        c.fillStyle = '#475569'; c.font = 'bold 18px Segoe UI, Arial';
        c.fillText('Unidades Litológicas SGM:', panX + 20, panY + 210);
        const maxSw = Math.min(leyendaSgm.length, 32);
        c.font = 'bold 16px Segoe UI, Arial';
        for (let i = 0; i < maxSw; i++) {{
            const [clv, hex] = leyendaSgm[i];
            const colIdx = i >= 16 ? 1 : 0;
            const rowIdx = i % 16;
            const sx = panX + 20 + colIdx * 215;
            const sy = panY + 236 + rowIdx * 42;
            c.fillStyle = hex; c.fillRect(sx, sy, 26, 22);
            c.strokeStyle = '#334155'; c.lineWidth = 1; c.strokeRect(sx, sy, 26, 22);
            c.fillStyle = '#1e293b'; c.fillText(String(clv).slice(0, 14), sx + 34, sy + 17);
        }}

        c.fillStyle = '#1e293b'; c.font = '16px Segoe UI, Arial';
        const fechaHoy = new Date().toISOString().slice(0, 10);
        c.fillText(
            `CONAGUA · Gerencia de Aguas Subterráneas · Fuentes: Límites CONAGUA | Litología y Estructuras 1:50k SGM | DEM AWS Terrain/SRTM | Mapa Base Esri · ${{fechaHoy}}`,
            42, H - 36
        );

        const link = document.createElement('a');
        link.download = 'Lamina_HD_Regional_3D_{clave_actual}.png';
        link.href = off.toDataURL('image/png');
        link.click();
    }}

    class FullscreenCustomControl {{
        onAdd(mapInstance) {{
            this._map = mapInstance;
            this._container = document.createElement('div');
            this._container.className = 'maplibregl-ctrl maplibregl-ctrl-group';

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.innerHTML = iconExpandSVG;
            btn.title = 'Pantalla Completa';
            btn.style.cssText = 'width:30px;height:30px;display:flex;align-items:center;justify-content:center;background:#ffffff;cursor:pointer;border:none;outline:none;';

            btn.onclick = () => {{
                if (!document.fullscreenElement) {{
                    document.documentElement.requestFullscreen().catch(() => {{}});
                }} else if (document.exitFullscreen) {{
                    document.exitFullscreen();
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
    map.addControl(new maplibregl.NavigationControl({{ showCompass: true, showZoom: true, visualizePitch: true }}), 'top-right');
    map.addControl(new maplibregl.ScaleControl({{ maxWidth: 120, unit: 'metric' }}), 'bottom-left');
</script>
</body>
</html>
"""


# =======================================================
# 🖥️ 12. RENDERIZADO CONDICIONAL DEL MOTOR SELECCIONADO
# =======================================================
if "Aislado" in modo_visualizacion:
    malla_json = preparar_malla_terreno_threejs(str(ruta_dem_local), mtime=dem_mtime)
    _render_html_visor(construir_html_aislado(malla_json), height=760)
else:
    _render_html_visor(construir_html_mapa(), height=760)

# =======================================================
# 🏷️ 13. LEYENDA CARTOGRÁFICA OFICIAL SGM Y TABLAS DE ATRIBUTOS
# =======================================================
if dic_leyenda_rocas:
    st.markdown(
        f"""
        <div style='background-color:#F8FAFC; border-left:4px solid #691C32; padding:10px 14px; border-radius:4px; margin-top:10px; margin-bottom:8px;'>
            <span style='font-size:12.5px; font-weight:bold; color:#691C32;'>SIMBOLOGÍA LITOLÓGICA OFICIAL (SGM)</span>
            <span style='font-size:11px; color:#64748B; margin-left:14px;'><b>Origen de Reglas:</b> {_html.escape(ORIGEN_SGM_GLOBAL)} | <b>Campo:</b> <code>{_html.escape(str(col_litologica))}</code></span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    items_html = [
        f"<div style='display:inline-flex; align-items:center; margin-right:18px; margin-bottom:6px;'>"
        f"<span style='width:16px; height:16px; background-color:{_html.escape(str(color))}; border-radius:3px; display:inline-block; margin-right:7px; border:1px solid rgba(0,0,0,0.3);'></span>"
        f"<span style='font-size:11.5px; font-weight:700; color:#1E293B;'>{_html.escape(str(roca))}</span>"
        f"</div>"
        for roca, color in sorted(dic_leyenda_rocas.items())
    ]
    st.markdown(
        f"<div style='background-color:#ffffff; padding:12px; border-radius:6px; border:1px solid #E2E8F0; line-height:1.6;'>{''.join(items_html)}</div>",
        unsafe_allow_html=True,
    )

st.caption(
    "Fuentes técnicas: Límites y superficie oficial de acuíferos: CONAGUA · Litología y estructuras 1:50,000: Servicio Geológico Mexicano (SGM) · "
    "Elevación digital: AWS Terrain Tiles / Mapzen Terrarium (base SRTM 1″ NASA/USGS, reproyectado a EPSG:4326, batimetría < −12 m filtrada) · "
    "Cálculos geodésicos sobre elipsoide WGS 84."
)

# =======================================================
# 📊 14. ANÁLISIS CUANTITATIVO SGM (ÁREAS EPSG:6372 + ROSETA ESTRUCTURAL)
# =======================================================
@st.cache_data(show_spinner=False, max_entries=8, ttl=3600)
def calcular_analisis_cuantitativo_sgm(clave_ac: str, _gdf_lito, _gdf_est, n_lito: int, n_est: int) -> dict:
    """Calcula áreas exactas por unidad litológica (EPSG:6372) y roseta bidireccional de estructuras."""
    res = {
        "df_areas": pd.DataFrame(),
        "roseta_r": [],
        "roseta_theta": [],
        "roseta_hover": [],
        "familia_dominante": "S/D",
        "long_total_km": 0.0,
        "n_con_azimut": 0,
        "df_tipos_est": pd.DataFrame(),
    }

    if _gdf_lito is not None and not _gdf_lito.empty:
        try:
            g_m = _gdf_lito.to_crs(epsg=6372)
            areas_km2 = g_m.geometry.area / 1e6
            clv_col = "CLAVE_SGM" if "CLAVE_SGM" in _gdf_lito.columns else "ETIQUETA_LITO"
            df_tmp = pd.DataFrame({
                "Clave_SGM": _gdf_lito[clv_col].astype(str).str.strip(),
                "Litologia": _gdf_lito["LITOLOGIA"].astype(str).str.strip() if "LITOLOGIA" in _gdf_lito.columns else "",
                "Roca": _gdf_lito["ROCA"].astype(str).str.strip() if "ROCA" in _gdf_lito.columns else "",
                "Color": _gdf_lito["COLOR_HEX"].astype(str).str.strip() if "COLOR_HEX" in _gdf_lito.columns else "#B0BEC5",
                "Area_km2": areas_km2.to_numpy(),
            })
            df_grp = (
                df_tmp.groupby("Clave_SGM", as_index=False)
                .agg(
                    Litologia=("Litologia", "first"),
                    Roca=("Roca", "first"),
                    Color=("Color", "first"),
                    Area_km2=("Area_km2", "sum"),
                )
                .sort_values("Area_km2", ascending=False)
                .reset_index(drop=True)
            )
            tot_area = float(df_grp["Area_km2"].sum())
            df_grp["Porcentaje"] = np.round(100.0 * df_grp["Area_km2"] / max(tot_area, 1e-9), 2)
            df_grp["Area_km2"] = np.round(df_grp["Area_km2"], 2)
            res["df_areas"] = df_grp
        except Exception:
            logger.exception("Error calculando áreas litológicas EPSG:6372 para %s", clave_ac)

    if _gdf_est is not None and not _gdf_est.empty:
        try:
            g_wgs = _gdf_est.to_crs(epsg=4326) if (_gdf_est.crs is not None and _gdf_est.crs.to_epsg() != 4326) else _gdf_est

            # Rumbo geográfico verdadero y longitud elipsoidal segmento por segmento sobre WGS 84
            # (elimina convergencia de meridianos de ±3° a ±6° de EPSG:6372 e incluye 100 % de las trazas)
            seg_az = []
            seg_km = []
            long_por_traza = np.zeros(len(g_wgs), dtype=float)
            bins = np.arange(0, 190, 10)
            trazas_por_sector = [set() for _ in range(18)]
            n_trazas_validas = 0

            for idx_f, geom_e in enumerate(g_wgs.geometry):
                if geom_e is None or geom_e.is_empty:
                    continue
                if geom_e.geom_type == "LineString":
                    lineas = [geom_e]
                elif geom_e.geom_type == "MultiLineString":
                    lineas = list(geom_e.geoms)
                else:
                    continue
                tuvo_seg = False
                km_traza = 0.0
                for ln in lineas:
                    coords = np.asarray(ln.coords, dtype=float)
                    if len(coords) < 2:
                        continue
                    lons1, lats1 = coords[:-1, 0], coords[:-1, 1]
                    lons2, lats2 = coords[1:, 0], coords[1:, 1]
                    az12, _, dist_m = GEOD_WGS84.inv(lons1, lats1, lons2, lats2)
                    dist_arr = np.asarray(dist_m, dtype=float)
                    az_raw = np.asarray(az12, dtype=float)
                    ok = np.isfinite(dist_arr) & np.isfinite(az_raw) & (dist_arr > 1e-3)
                    if not np.any(ok):
                        continue
                    tuvo_seg = True
                    az_arr = np.mod(az_raw[ok], 180.0)
                    km_arr = dist_arr[ok] / 1000.0
                    km_traza += float(km_arr.sum())
                    seg_az.append(az_arr)
                    seg_km.append(km_arr)
                    sec_idx = np.clip((az_arr // 10.0).astype(int), 0, 17)
                    for si in np.unique(sec_idx):
                        trazas_por_sector[int(si)].add(idx_f)
                if tuvo_seg:
                    n_trazas_validas += 1
                    long_por_traza[idx_f] = km_traza

            res["long_total_km"] = round(float(long_por_traza.sum()), 2)
            tipo_col = "ESTRUCTURAS" if "ESTRUCTURAS" in _gdf_est.columns else None
            if tipo_col:
                df_t = pd.DataFrame({
                    "Tipo_Estructura": _gdf_est[tipo_col].fillna("Sin clasificar").astype(str).str.strip(),
                    "Longitud_km": long_por_traza,
                })
                df_tg = (
                    df_t.groupby("Tipo_Estructura", as_index=False)
                    .agg(Conteo=("Longitud_km", "count"), Longitud_km=("Longitud_km", "sum"))
                    .sort_values("Longitud_km", ascending=False)
                    .reset_index(drop=True)
                )
                df_tg["Longitud_km"] = np.round(df_tg["Longitud_km"], 2)
                res["df_tipos_est"] = df_tg

            res["n_con_azimut"] = int(n_trazas_validas)
            if seg_az:
                az_all = np.concatenate(seg_az)
                km_all = np.concatenate(seg_km)
                hist_km, _ = np.histogram(az_all, bins=bins, weights=km_all)
                hist_cnt = np.array([len(s) for s in trazas_por_sector], dtype=int)
                centros_180 = np.arange(5, 185, 10)

                # Simetría bidireccional 0°–360° (estándar geología estructural)
                theta_360 = np.concatenate([centros_180, centros_180 + 180]).tolist()
                r_360 = np.concatenate([np.round(hist_km, 2), np.round(hist_km, 2)]).tolist()
                tot_km = max(float(hist_km.sum()), 1e-9)
                hover_180 = [
                    f"Rumbo geográfico {int(b)}°–{int(b+10)}° ({int(b+180)}°–{int(b+190)}°)<br>"
                    f"Longitud: {km:.2f} km ({100.0 * km / tot_km:.1f} %) · {int(cnt)} trazas"
                    for b, km, cnt in zip(bins[:-1], hist_km, hist_cnt)
                ]
                res["roseta_theta"] = theta_360
                res["roseta_r"] = r_360
                res["roseta_hover"] = hover_180 + hover_180

                idx_dom = int(np.argmax(hist_km))
                b0, b1 = int(bins[idx_dom]), int(bins[idx_dom + 1])
                pct_dom = 100.0 * hist_km[idx_dom] / tot_km
                if b0 < 90:
                    rumbo_txt = f"N{b0}°E – N{b1}°E"
                else:
                    rumbo_txt = f"N{180 - b1}°W – N{180 - b0}°W"
                res["familia_dominante"] = f"{rumbo_txt} ({hist_km[idx_dom]:.1f} km · {pct_dom:.1f} %)"
        except Exception:
            logger.exception("Error calculando roseta estructural para %s", clave_ac)

    return res


if (gdf_geologia_recortada is not None and not gdf_geologia_recortada.empty) or (
    gdf_estructuras_50k is not None and not gdf_estructuras_50k.empty
):
    with st.expander("📊 Análisis Cuantitativo SGM (Áreas Litológicas EPSG:6372 y Roseta Estructural)", expanded=False):
        analisis_sgm = calcular_analisis_cuantitativo_sgm(
            clave_actual,
            gdf_geologia_recortada,
            gdf_estructuras_50k,
            len(gdf_geologia_recortada) if gdf_geologia_recortada is not None else 0,
            len(gdf_estructuras_50k) if gdf_estructuras_50k is not None else 0,
        )
        import plotly.graph_objects as go

        col_q1, col_q2 = st.columns([1.15, 0.85])
        with col_q1:
            st.markdown("##### 🪨 Distribución Litológica Real (Proyección EPSG:6372)")
            df_ar = analisis_sgm["df_areas"]
            if not df_ar.empty:
                df_top = df_ar.head(12).iloc[::-1]
                max_pct = float(df_top["Porcentaje"].max()) if len(df_top) else 100.0
                fig_lito = go.Figure(
                    go.Bar(
                        x=df_top["Porcentaje"],
                        y=df_top["Clave_SGM"],
                        orientation="h",
                        marker=dict(color=df_top["Color"].tolist(), line=dict(color="#334155", width=0.8)),
                        text=[f"{p:.1f}% ({a:,.1f} km²)" for p, a in zip(df_top["Porcentaje"], df_top["Area_km2"])],
                        textposition="outside",
                        cliponaxis=False,
                        hovertext=[
                            f"{c} · {l} ({r})<br>{a:,.2f} km² ({p:.2f}%)"
                            for c, l, r, a, p in zip(
                                df_top["Clave_SGM"], df_top["Litologia"], df_top["Roca"], df_top["Area_km2"], df_top["Porcentaje"]
                            )
                        ],
                        hoverinfo="text",
                    )
                )
                fig_lito.update_layout(
                    height=340,
                    margin=dict(l=10, r=24, t=10, b=35),
                    xaxis=dict(
                        title="Cobertura superficial (%)",
                        range=[0, max(15.0, min(135.0, max_pct * 1.42))],
                    ),
                    yaxis_title="",
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                )
                st.plotly_chart(fig_lito, width="stretch")
                st.dataframe(
                    df_ar[["Clave_SGM", "Litologia", "Roca", "Area_km2", "Porcentaje"]].rename(
                        columns={"Clave_SGM": "Clave SGM", "Litologia": "Litología", "Area_km2": "Área (km²)", "Porcentaje": "%"}
                    ),
                    width="stretch",
                    height=210,
                )
                st.download_button(
                    label="⬇️ Descargar Resumen de Áreas Litológicas (CSV)",
                    data=lambda d=df_ar: d.drop(columns=["Color"], errors="ignore").to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"Areas_Litologia_SGM_{clave_actual}.csv",
                    mime="text/csv",
                    type="secondary",
                    width="stretch",
                    on_click="ignore",
                )
            else:
                st.info("Sin polígonos litológicos para cuantificar.")

        with col_q2:
            st.markdown("##### 🧭 Roseta Estructural 1:50k (0°–180° Simétrica)")
            if analisis_sgm["roseta_r"]:
                st.caption(
                    f"**Familia dominante:** {analisis_sgm['familia_dominante']}  \n"
                    f"**Longitud total:** {analisis_sgm['long_total_km']:,.2f} km ({analisis_sgm['n_con_azimut']:,} estructuras · rumbo geográfico WGS 84)"
                )
                escala_roseta = st.radio(
                    "Escala radial de roseta:",
                    ["Área proporcional (√km · Nemec 1988)", "Lineal (km)"],
                    index=0,
                    horizontal=True,
                    label_visibility="collapsed",
                    key="radio_escala_roseta_sgm",
                )
                r_raw = np.asarray(analisis_sgm["roseta_r"], dtype=float)
                r_max = float(np.max(r_raw)) if len(r_raw) else 1.0
                if "Nemec" in escala_roseta:
                    r_plot = np.sqrt(np.maximum(r_raw, 0.0)).tolist()
                    # Marcas radiales legibles en km reales sobre escala raíz cuadrada
                    raw_ticks = np.linspace(0.0, r_max, 5)[1:]
                    mag = 10.0 ** math.floor(math.log10(max(r_max / 4.0, 1e-6)))
                    paso_t = max(mag * round((r_max / 4.0) / mag), mag * 0.5)
                    km_ticks = np.arange(paso_t, r_max * 1.05, paso_t)
                    if len(km_ticks) < 2:
                        km_ticks = raw_ticks
                    radial_cfg = dict(
                        tickmode="array",
                        tickvals=[math.sqrt(v) for v in km_ticks],
                        ticktext=[f"{v:.0f} km" if v >= 10 else f"{v:.1f} km" for v in km_ticks],
                        showticklabels=True,
                        tickfont=dict(size=9),
                    )
                else:
                    r_plot = r_raw.tolist()
                    radial_cfg = dict(ticksuffix=" km", showticklabels=True, tickfont=dict(size=9))

                fig_rosa = go.Figure(
                    go.Barpolar(
                        r=r_plot,
                        theta=analisis_sgm["roseta_theta"],
                        width=[9.5] * len(analisis_sgm["roseta_theta"]),
                        marker_color="#9F2241",
                        marker_line_color="#691C32",
                        marker_line_width=1,
                        opacity=0.85,
                        hovertext=analisis_sgm["roseta_hover"],
                        hoverinfo="text",
                    )
                )
                fig_rosa.update_layout(
                    height=340,
                    margin=dict(l=30, r=30, t=25, b=25),
                    polar=dict(
                        angularaxis=dict(direction="clockwise", rotation=90, dtick=30),
                        radialaxis=radial_cfg,
                    ),
                    paper_bgcolor="#ffffff",
                )
                st.plotly_chart(fig_rosa, width="stretch")
                if not analisis_sgm["df_tipos_est"].empty:
                    st.dataframe(
                        analisis_sgm["df_tipos_est"].rename(
                            columns={"Tipo_Estructura": "Tipo de Estructura", "Longitud_km": "Longitud (km)"}
                        ),
                        width="stretch",
                        height=180,
                    )
            else:
                st.info("Sin fallas o fracturas con azimut registrado dentro de este acuífero.")

if gdf_geologia_recortada is not None and not gdf_geologia_recortada.empty:
    with st.expander(f"🔬 Inspeccionar Tabla de Atributos Vectoriales de la Capa SGM ({len(gdf_geologia_recortada):,} polígonos)", expanded=False):
        st.dataframe(gdf_geologia_recortada.drop(columns=["geometry"], errors="ignore"), width="stretch")

if gdf_estructuras_50k is not None and not gdf_estructuras_50k.empty:
    with st.expander(f"🔬 Inspeccionar Fallas y Estructuras SGM ({len(gdf_estructuras_50k):,} registradas)", expanded=False):
        cols_est = [c for c in gdf_estructuras_50k.columns if c != "geometry"]
        st.dataframe(gdf_estructuras_50k[cols_est], width="stretch")
