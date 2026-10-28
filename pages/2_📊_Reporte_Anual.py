# -*- coding: utf-8 -*-
"""
Módulo de Cierre Anual y Consolidación de Balances (Optimizado a Disco - Enterprise)
Incluye:
- Multithreading para descargas y generación de Excels.
- Aislamiento de sesiones por UUID.
- Exponential Backoff para Rate Limits de Google Drive.
- Escaneo Profundo Multi-Año (JSONs Históricos + Excel Oficial)
"""

import plotly.graph_objects as go
import plotly.express as px
from folium import plugins
import concurrent.futures
import streamlit as st
import pandas as pd
import datetime
import zipfile
import folium
import shutil
import uuid
import time
import json
import os
import gc
import logging
import numpy as np
from streamlit_folium import st_folium
from plotly.subplots import make_subplots

# --- IMPORTACIONES DEL CORE (FASE 1 y 2) ---
from utils.styles import inyectar_css_oficial, banner_institucional, inyectar_css_navegacion
from core.data_loader import (cargar_catalogo, cargar_historico_excel, obtener_datos_maestros_compartidos,
                              normalizar_serie_clave)

logger = logging.getLogger(__name__)

# =======================================================
# --- CSS OFICIAL Y BANNER COMPACTO ---
# =======================================================
inyectar_css_oficial()
banner_institucional()

st.subheader("📊 Reporte Anual de Balances de Aguas Subterráneas")
st.caption("Generación de resumen de resultados de Balances de Aguas Subterráneas y empaquetado de respaldos.")

# ==========================================
# 0. PREPARACIÓN DE CARPETAS Y SESIÓN (AISLAMIENTO UUID)
# ==========================================
if "sesion_id" not in st.session_state:
    st.session_state.sesion_id = uuid.uuid4().hex

CARPETA_TEMPORAL = "temp_balances_oficial"
CARPETA_JSONS = os.path.join(CARPETA_TEMPORAL, "jsons_cache_global")
USER_TEMP_DIR = os.path.join(CARPETA_TEMPORAL, st.session_state.sesion_id)

os.makedirs(CARPETA_JSONS, exist_ok=True)
os.makedirs(USER_TEMP_DIR, exist_ok=True)
INDEX_CACHE = os.path.join(CARPETA_JSONS, "smart_cache_oficial.json")

def limpiar_temporales_antiguos():
    try:
        now = time.time()
        for f in os.listdir(CARPETA_TEMPORAL):
            path = os.path.join(CARPETA_TEMPORAL, f)
            if os.path.isdir(path) and f != "jsons_cache_global":
                if os.stat(path).st_mtime < now - 7200:
                    shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass

limpiar_temporales_antiguos()

def guardar_json_atomico(data, ruta):
    ruta_tmp = f"{ruta}.{uuid.uuid4().hex}.tmp"
    with open(ruta_tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    os.replace(ruta_tmp, ruta)

# ==========================================
# 1. FUNCIONES WORKER (DESCARGA Y PROCESAMIENTO)
# ==========================================
def worker_extraccion(archivo, token, retries=3):
    id_arch = archivo['id']
    nom_arch = archivo['name']
    from core.drive_api import descargar_json_crudo_rapido  # import local: el módulo se reejecuta en cada rerun
    
    for intento in range(retries):
        try:
            data = descargar_json_crudo_rapido(id_arch, token)
            if not data:
                return {"estado": "error", "id": id_arch, "name": nom_arch}
            
            ruta_json_fisico = os.path.join(CARPETA_JSONS, f"{id_arch}.json")
            guardar_json_atomico(data, ruta_json_fisico)  # escritura atómica: otra sesión nunca lee un JSON a medias
                
            return {"estado": "exito", "id": id_arch, "modifiedTime": archivo.get('modifiedTime')}
            
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                time.sleep((intento + 1) * 2)
            else:
                if intento == retries - 1:
                    return {"estado": "error", "id": id_arch, "name": nom_arch, "error": str(e)}
    return {"estado": "error", "id": id_arch, "name": nom_arch, "error": "Max retries excedido"}

def calc_flujos_vectorizado(datos, cols):
    df = pd.DataFrame(datos)
    if df.empty: return pd.DataFrame(columns=cols)
    for c in ['Longitud B [m]', 'Ancho a [m]', 'h2-h1 [m]', 'Transmisividad T [m²/s]']:
        if c not in df.columns: df[c] = 0.0
    ancho = pd.to_numeric(df['Ancho a [m]'], errors='coerce').fillna(0.0)
    h2_h1 = pd.to_numeric(df['h2-h1 [m]'], errors='coerce').fillna(0.0)
    trans = pd.to_numeric(df['Transmisividad T [m²/s]'], errors='coerce').fillna(0.0)
    longB = pd.to_numeric(df['Longitud B [m]'], errors='coerce').fillna(0.0)
    df['Gradiente i'] = np.where(ancho > 0, h2_h1 / ancho, 0.0)
    df['Caudal Q [m³/s]'] = trans * df['Gradiente i'] * longB
    if 'Volumen [hm³/año]' not in df.columns or pd.to_numeric(df['Volumen [hm³/año]'], errors='coerce').fillna(0.0).sum() == 0:
        df['Volumen [hm³/año]'] = df['Caudal Q [m³/s]'] * 31.536
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df[cols]

def worker_generar_excel(f_maestra, anio_procesado, user_dir):
    try:
        from core.generador_excel import generar_excel_matriz  # import local (antes solo existía tras pulsar 'Escanear')
        ruta_json = f_maestra.get("ruta_fisica", "")
        if not os.path.exists(ruta_json):
            return None
            
        with open(ruta_json, 'r', encoding='utf-8') as json_f:
            dat = json.load(json_f)
            
        res = dat.get("resultados", {})
        conf = dat.get("configuracion", {})
        tabs = dat.get("tablas", {})
        
        cols_flujo = ['Celda', 'Longitud B [m]', 'Ancho a [m]', 'h2-h1 [m]', 'Transmisividad T [m²/s]', 'Gradiente i', 'Caudal Q [m³/s]', 'Volumen [hm³/año]']
        
        df_eh = calc_flujos_vectorizado(tabs.get('eh', []), cols_flujo)
        df_eas = calc_flujos_vectorizado(tabs.get('eas', []), cols_flujo)
        df_sh = calc_flujos_vectorizado(tabs.get('sh', []), cols_flujo)
        eh_acumulado = df_eh['Volumen [hm³/año]'].sum() if not df_eh.empty else 0.0
        eas_acumulado = df_eas['Volumen [hm³/año]'].sum() if not df_eas.empty else 0.0
        sh_acumulado = df_sh['Volumen [hm³/año]'].sum() if not df_sh.empty else 0.0

        df_usos = pd.DataFrame(tabs.get('usos', []))
        if not df_usos.empty:
            if 'Volumen [hm³/año]' not in df_usos.columns: df_usos['Volumen [hm³/año]'] = 0.0
            df_usos['Volumen [hm³/año]'] = pd.to_numeric(df_usos['Volumen [hm³/año]'], errors='coerce').fillna(0.0)
            bombeo_calc = df_usos['Volumen [hm³/año]'].sum()
        else: 
            df_usos = pd.DataFrame(columns=['Tipo de Uso', 'Volumen [hm³/año]', 'Porcentaje (%)'])
            bombeo_calc = float(res.get("B_total", 0.0))

        df_etr = pd.DataFrame(tabs.get('etr', []))
        etr_json = float(res.get("ETR", 0.0))
        if not df_etr.empty:
            pme = float(conf.get("PME", 5.0))
            lsup = pd.to_numeric(df_etr.get('Límite Sup [m]'), errors='coerce')
            linf = pd.to_numeric(df_etr.get('Límite Inf [m]'), errors='coerce')
            area_etr = pd.to_numeric(df_etr.get('Área [km²]'), errors='coerce').fillna(0.0)
            lamina = pd.to_numeric(df_etr.get('Lámina ETR [m]'), errors='coerce').fillna(0.0)
            df_etr['Prof. Media (PM) [m]'] = np.where(lsup.isna(), np.nan, np.where(linf.isna(), lsup, (lsup+linf)/2.0))
            pm = df_etr['Prof. Media (PM) [m]']
            df_etr['% ETR'] = np.where(pd.notna(pm) & (pm < pme) & (pme > 0), ((pme - pm)/pme)*100, 0.0)
            if 'Volumen [hm³/año]' not in df_etr.columns or pd.to_numeric(df_etr['Volumen [hm³/año]'], errors='coerce').fillna(0.0).sum() == 0:
                df_etr['Volumen [hm³/año]'] = area_etr * lamina * (df_etr['% ETR']/100.0)
            etr_acumulado_tabla = pd.to_numeric(df_etr['Volumen [hm³/año]'], errors='coerce').sum(skipna=True)
            etr_acumulado = etr_json if etr_acumulado_tabla == 0 else etr_acumulado_tabla
        else:
            etr_acumulado = etr_json
            if etr_acumulado > 0: df_etr = pd.DataFrame([{'Polígono / Zona': 'Valor Histórico', 'Volumen [hm³/año]': etr_acumulado}])
            else: df_etr = pd.DataFrame(columns=['Polígono / Zona', 'Límite Sup [m]', 'Límite Inf [m]', 'Prof. Media (PM) [m]', 'Área [km²]', 'Lámina ETR [m]', '% ETR', 'Volumen [hm³/año]'])

        df_dvs = pd.DataFrame(tabs.get('dvs', []))
        if not df_dvs.empty:
            l1 = pd.to_numeric(df_dvs.get('Límite 1 [m]'), errors='coerce')
            l2 = pd.to_numeric(df_dvs.get('Límite 2 [m]'), errors='coerce')
            area = pd.to_numeric(df_dvs.get('Área [km²]'), errors='coerce').fillna(0.0)
            sy = pd.to_numeric(df_dvs.get('Sy'), errors='coerce').fillna(0.0)
            df_dvs['Evolución Media [m]'] = np.where(l1.isna(), np.nan, np.where(l2.isna(), l1, (l1+l2)/2.0))
            if 'Volumen Parcial [hm³]' not in df_dvs.columns or pd.to_numeric(df_dvs['Volumen Parcial [hm³]'], errors='coerce').fillna(0.0).sum() == 0:
                df_dvs['Volumen Parcial [hm³]'] = np.where(pd.notna(df_dvs['Evolución Media [m]']), df_dvs['Evolución Media [m]'] * area * sy, np.nan)
            DVS_t = pd.to_numeric(df_dvs['Volumen Parcial [hm³]'], errors='coerce').sum(skipna=True)
        else:
            df_dvs = pd.DataFrame(columns=['Polígono / Rango', 'Límite 1 [m]', 'Límite 2 [m]', 'Evolución Media [m]', 'Área [km²]', 'Sy', 'Volumen Parcial [hm³]'])
            DVS_t = 0.0

        rr_val = round(float(conf.get("rr_val") or 0.0), 1)
        o_sal = conf.get("otras_salidas") or {}
        val_ssb = round(float(o_sal.get("Ssb") or 0.0), 1)
        val_dfb = round(float(o_sal.get("Dfb") or 0.0), 1)
        val_dm = round(float(o_sal.get("Dm") or 0.0), 1)
        val_rv_calc = round(float(res.get("Rv") or 0.0), 1)
        val_ri_calc = round(float(res.get("Ri") or 0.0), 1)
        dnc_total_calc = round(float(res.get("DNC_total") or 0.0), 1)
        veas_calc = float(res.get("VEAS") or 0.0)
        disponibilidad_calc = float(res.get("Disponibilidad_Oficial") or 0.0)

        periodo_dvs = conf.get("periodo_dvs") or {}
        a_base = int(periodo_dvs.get("a_base") or 2020)
        a_tope = int(periodo_dvs.get("a_tope") or 2025)
        rda = a_tope - a_base
        dvs_anualizado = round(float(res.get("DVS", DVS_t / rda if rda > 0 else 0.0)), 1)

        bombeo_1d = round(float(bombeo_calc), 1)
        sh_1d = round(float(sh_acumulado), 1)
        etr_1d = round(float(etr_acumulado), 1)
        eh_1d = round(float(eh_acumulado), 1)
        eas_1d = round(float(eas_acumulado), 1)

        recarga_t = float(res.get("Recarga_Total", round(rr_val + eh_1d + val_rv_calc, 1)))
        descarga_t = round(bombeo_1d + sh_1d + etr_1d + val_ssb + val_dfb + val_dm, 1)

        # Detalle de DNC por componente oficial (NOM-011-CONAGUA)
        dnc_params = conf.get("dnc_params") or {}
        p_etr = float(dnc_params.get("p_etr") or 0.0)
        p_sh = float(dnc_params.get("p_sh") or 0.0)
        p_ssb = float(dnc_params.get("p_ssb") or 0.0)
        p_dfb = float(dnc_params.get("p_dfb") or 0.0)
        p_dm = float(dnc_params.get("p_dm") or 0.0)

        d_etr = round(etr_1d * (p_etr / 100.0), 1)
        d_sh = round(sh_1d * (p_sh / 100.0), 1)
        d_ssb = round(val_ssb * (p_ssb / 100.0), 1)
        d_dfb = round(val_dfb * (p_dfb / 100.0), 1)
        d_dm = round(val_dm * (p_dm / 100.0), 1)
        dnc_detalle = [d_etr, d_sh, d_ssb, d_dfb, d_dm]
        pme_val = float(conf.get("PME") or 5.0)

        df_ind_resumen = pd.DataFrame([
            {"Concepto": "Retornos por Riego (Rr)", "Volumen (hm³)": rr_val},
            {"Concepto": "Entradas Horizontales (Eh)", "Volumen (hm³)": eh_1d},
            {"Concepto": "Entradas de Agua Salobre (Eas)", "Volumen (hm³)": eas_1d},
            {"Concepto": "Recarga Vertical Resultante (Rv)", "Volumen (hm³)": val_rv_calc},
            {"Concepto": "Recarga Incidental (Ri)", "Volumen (hm³)": val_ri_calc},
            {"Concepto": "RECARGA TOTAL (R)", "Volumen (hm³)": recarga_t},
            {"Concepto": "Extracción / Bombeo (B)", "Volumen (hm³)": bombeo_1d},
            {"Concepto": "Salidas Horizontales (Sh)", "Volumen (hm³)": sh_1d},
            {"Concepto": "Evapotranspiración (ETR)", "Volumen (hm³)": etr_1d},
            {"Concepto": "Salidas de Agua Salobre (Sas)", "Volumen (hm³)": val_ssb},      
            {"Concepto": "Descarga Flujo Base (Dfb)", "Volumen (hm³)": val_dfb},
            {"Concepto": "Descarga Manantiales (Dm)", "Volumen (hm³)": val_dm},
            {"Concepto": "DESCARGA TOTAL (S)", "Volumen (hm³)": descarga_t},
            {"Concepto": "Cambio de Almacenamiento ΔV(S)", "Volumen (hm³)": dvs_anualizado},
            {"Concepto": "Descarga Natural Comprometida (DNC)", "Volumen (hm³)": dnc_total_calc},
            {"Concepto": "DISPONIBILIDAD MEDIA ANUAL (DMA)", "Volumen (hm³)": disponibilidad_calc}
        ])
        
        fuente_b = conf.get("fuente_b", "Censo")
        anio_b = conf.get("anio_b", "2026")
        clave_ac = str(f_maestra.get("Clave", "ND"))
        nom_ac = str(f_maestra.get("Acuífero", "ND")).replace(" ", "_")
        nom_x = f"Balance_{clave_ac}_{nom_ac}_{anio_procesado}.xlsx"
        
        ruta_ind = os.path.join(user_dir, nom_x)
        generar_excel_matriz(
            df_ind_resumen, df_eh, df_usos, df_sh, df_etr, df_dvs, df_eas,
            dvs_anualizado, fuente_b, anio_b, a_base, a_tope, rda,
            destino_salida=ruta_ind, dnc_detalle=dnc_detalle, pme=pme_val
        )
        
        return (ruta_ind, f"Balances_Individuales/{nom_x}")
    except Exception as e:
        logger.exception("Error generando Excel para el acuífero %s", f_maestra.get('Clave'))
        return None

# ==========================================
# 2. ESCANEO PROFUNDO (DEEP SCAN) Y EXTRACCIÓN JSON
# ==========================================
def extraer_datos_balance(ruta_json):
    """Función maestra que saca las 30 variables de cualquier archivo JSON"""
    if not os.path.exists(ruta_json): return {}
    try:
        with open(ruta_json, 'r', encoding='utf-8') as f:
            dat = json.load(f)
        
        res = dat.get("resultados") or {}
        conf = dat.get("configuracion") or {}
        tabs = dat.get("tablas") or {}

        def _safe_float(v, default=0.0):
            if v is None: return default
            try: return float(v)
            except (ValueError, TypeError): return default
        
        df_usos = pd.DataFrame(tabs.get('usos', []))
        usos_totales = {
            "Uso_Agricola": 0.0, "Uso_Agroindustrial": 0.0, "Uso_Domestico": 0.0, 
            "Uso_Acuacultura": 0.0, "Uso_Servicios": 0.0, "Uso_Industrial": 0.0, 
            "Uso_Pecuario": 0.0, "Uso_Publico_Urbano": 0.0, "Uso_Diferentes": 0.0, 
            "Uso_Energia": 0.0, "Uso_Comercio": 0.0, "Uso_Otros": 0.0, "Uso_Ecologica": 0.0
        }
        
        if not df_usos.empty and 'Volumen [hm³/año]' in df_usos.columns:
            vols = pd.to_numeric(df_usos['Volumen [hm³/año]'], errors='coerce').fillna(0.0)
            tipos = df_usos.get('Tipo de Uso', pd.Series(dtype=str)).astype(str).str.strip().str.upper()
            for tipo, vol in zip(tipos, vols):
                if 'AGRÍCOLA' in tipo or 'AGRICOLA' in tipo: usos_totales["Uso_Agricola"] += vol
                elif 'AGROIND' in tipo: usos_totales["Uso_Agroindustrial"] += vol
                elif 'DOM' in tipo: usos_totales["Uso_Domestico"] += vol
                elif 'ACUA' in tipo: usos_totales["Uso_Acuacultura"] += vol
                elif 'SERV' in tipo: usos_totales["Uso_Servicios"] += vol
                elif 'INDUS' in tipo: usos_totales["Uso_Industrial"] += vol
                elif 'PECU' in tipo: usos_totales["Uso_Pecuario"] += vol
                elif 'URBANO' in tipo or 'PÚBLICO' in tipo or 'PUBLICO' in tipo: usos_totales["Uso_Publico_Urbano"] += vol
                elif 'DIFER' in tipo: usos_totales["Uso_Diferentes"] += vol
                elif 'ENERG' in tipo: usos_totales["Uso_Energia"] += vol
                elif 'COMER' in tipo: usos_totales["Uso_Comercio"] += vol
                elif 'ECOL' in tipo: usos_totales["Uso_Ecologica"] += vol
                else: usos_totales["Uso_Otros"] += vol

        # Extracción segura de flujos horizontales y salobres
        tab_eh = tabs.get('eh', [])
        vol_eh = sum(_safe_float(r.get('Volumen [hm³/año]')) for r in tab_eh) if tab_eh else 0.0
        if vol_eh == 0.0 and tab_eh:
            df_eh_tmp = calc_flujos_vectorizado(tab_eh, ['Volumen [hm³/año]'])
            vol_eh = _safe_float(df_eh_tmp['Volumen [hm³/año]'].sum())

        tab_sh = tabs.get('sh', [])
        vol_sh = sum(_safe_float(r.get('Volumen [hm³/año]')) for r in tab_sh) if tab_sh else 0.0
        if vol_sh == 0.0 and tab_sh:
            df_sh_tmp = calc_flujos_vectorizado(tab_sh, ['Volumen [hm³/año]'])
            vol_sh = _safe_float(df_sh_tmp['Volumen [hm³/año]'].sum())

        tab_eas = tabs.get('eas', [])
        vol_eas = sum(_safe_float(r.get('Volumen [hm³/año]')) for r in tab_eas) if tab_eas else 0.0
        if vol_eas == 0.0 and tab_eas:
            df_eas_tmp = calc_flujos_vectorizado(tab_eas, ['Volumen [hm³/año]'])
            vol_eas = _safe_float(df_eas_tmp['Volumen [hm³/año]'].sum())

        o_sal = conf.get("otras_salidas") or {}
        datos = {
            "Recarga (R)": round(_safe_float(res.get('Recarga_Total')), 1),
            "Rv": round(_safe_float(res.get("Rv")), 1), 
            "Ri": round(_safe_float(res.get("Ri")), 1), 
            "Rr": round(_safe_float(conf.get("rr_val")), 1),
            "Eh": round(vol_eh, 1),
            "Eas": round(vol_eas, 1),
            "Bombeo (B)": round(_safe_float(res.get('B_total')), 1),
            "Sh": round(vol_sh, 1),
            "ETR": round(_safe_float(res.get('ETR')), 1),
            "Ssb": round(_safe_float(o_sal.get("Ssb")), 1), 
            "Dfb": round(_safe_float(o_sal.get("Dfb")), 1), 
            "Dm": round(_safe_float(o_sal.get("Dm")), 1), 
            "DNC": round(_safe_float(res.get('DNC_total')), 1),
            "PME": round(_safe_float(conf.get("PME"), 5.0), 2),
            "VEAS": round(_safe_float(res.get('VEAS')), 6), 
            "ΔV(S)": round(_safe_float(res.get('DVS')), 1),
            "Disponibilidad (DMA)": round(_safe_float(res.get('Disponibilidad_Oficial')), 6)
        }
        datos.update({k: round(v, 2) for k, v in usos_totales.items()})
        return datos
    except Exception:
        logger.exception("No se pudo extraer el balance de %s", ruta_json)
        return {}


col_y1, col_y2 = st.columns(2)
anio_reporte = col_y1.number_input("Selecciona el Año de Evaluación a procesar:", min_value=2020, max_value=2100, value=datetime.datetime.now().year, step=1)
st.markdown("<br>", unsafe_allow_html=True)
activar_tendencia = st.checkbox("📈 Habilitar Análisis de Tendencia (Comparativa vs Publicación Anterior)")

anio_comparacion = None
if activar_tendencia:
    anio_comparacion = col_y2.number_input("Año de Publicación Anterior:", min_value=2015, max_value=2100, value=2023, step=1)

if st.button("🔍 Escanear Drive y Generar Reporte", type="primary"):
    from core.drive_api import buscar_metadatos_drive, obtener_token_acceso, ErrorDrive
    limpiar_temporales_antiguos()    
    if activar_tendencia and anio_comparacion >= anio_reporte:
        st.error("⚠️ Error de lógica temporal: El año histórico no puede ser mayor o igual al evaluado.")
        st.stop()
        
    dict_historico = cargar_historico_excel("DMA_VEAS.xlsx", anio_comparacion) if activar_tendencia else {}
    if activar_tendencia and dict_historico.get("error_columnas"):
        st.warning(f"⚠️ DMA_VEAS.xlsx no tiene las columnas {dict_historico.get('dma')} y {dict_historico.get('veas')}: la comparativa con el Excel oficial saldrá como N/D.")
        dict_historico = {}
    elif activar_tendencia and not dict_historico:
        st.warning("⚠️ No se encontró o no se pudo leer DMA_VEAS.xlsx: la comparativa con el Excel oficial saldrá como N/D.")

    # Buscar JSONs del año actual y del año histórico
    try:
        archivos_drive_actual = buscar_metadatos_drive(anio_reporte, estricto=True)
        archivos_drive_hist = buscar_metadatos_drive(anio_comparacion, estricto=True) if activar_tendencia else []
    except ErrorDrive as exc:
        st.error(f"❌ No se pudo completar el escaneo de Drive; el reporte quedaría incompleto. Detalle: {exc}")
        st.stop()
    # Si existen varias versiones del mismo balance se conserva la modificada más recientemente
    # (antes el orden de Drive era arbitrario y podía quedar una versión vieja).
    archivos_drive_actual.sort(key=lambda a: a.get('modifiedTime', ''), reverse=True)
    archivos_drive_hist.sort(key=lambda a: a.get('modifiedTime', ''), reverse=True)
    
    if not archivos_drive_actual:
        st.warning(f"No se encontraron archivos en Drive para el año {anio_reporte}.")
        st.stop()

    archivos_totales = archivos_drive_actual + archivos_drive_hist

    texto_progreso = st.empty()
    barra_progreso = st.progress(0)
    
    cache_index = {}
    if os.path.exists(INDEX_CACHE):
        try:
            with open(INDEX_CACHE, 'r') as f:
                cache_index = json.load(f)
        except (OSError, ValueError):
            cache_index = {}  # índice ilegible: se vuelve a descargar todo

    archivos_a_descargar = []
    for arch in archivos_totales:
        aid = arch['id']
        amod = arch.get('modifiedTime', '')
        ruta_archivo = os.path.join(CARPETA_JSONS, f"{aid}.json")
        
        if aid not in cache_index or cache_index[aid] != amod or not os.path.exists(ruta_archivo):
            archivos_a_descargar.append(arch)

    omitidos_errores = []
    if archivos_a_descargar:
        texto_progreso.info(f"🧠 Smart Sync: Descargando {len(archivos_a_descargar)} expedientes nuevos/históricos...")
        
        token = obtener_token_acceso()
        if not token:
            st.error("❌ No se pudo autenticar con Google Drive. Revisa las credenciales en secrets.toml.")
            st.stop()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futuros = {executor.submit(worker_extraccion, arch, token): arch for arch in archivos_a_descargar}
            for i, fut in enumerate(concurrent.futures.as_completed(futuros)):
                res = fut.result()
                if res['estado'] == 'exito':
                    cache_index[res['id']] = res['modifiedTime']
                else:
                    omitidos_errores.append(f"{res.get('name', 'Desconocido')} - Error interno")
                barra_progreso.progress((i + 1) / len(archivos_a_descargar))
                
        guardar_json_atomico(cache_index, INDEX_CACHE)

    texto_progreso.success("⚡ Ejecutando Deep Scan en expedientes JSON...")
    datos_maestros = []
    ids_procesados = set()
    omitidos_duplicados = []

    for arch in archivos_drive_actual:
        fid = arch['id']
        fnom = arch['name']
        clave = fnom.split('_')[0]
        
        if clave in ids_procesados:
            omitidos_duplicados.append(fnom)
            continue
            
        ruta_actual = os.path.join(CARPETA_JSONS, f"{fid}.json")
        if os.path.exists(ruta_actual):
            datos_actuales = extraer_datos_balance(ruta_actual)
            if not datos_actuales:
                omitidos_errores.append(f"{fnom} - JSON ilegible o incompleto")
                continue
            
            tokens_nom = fnom.replace('.json', '').split('_')[1:]
            if tokens_nom and tokens_nom[-1].upper().startswith('B') and len(tokens_nom[-1]) <= 4:
                tokens_nom = tokens_nom[:-1]
            nom_acuifero = " ".join(tokens_nom) if tokens_nom else "Acuífero"

            fila = {
                "Clave": clave,
                "Acuífero": nom_acuifero,
                "ruta_fisica": ruta_actual 
            }
            fila.update(datos_actuales)
            
            if activar_tendencia:
                # 1. Escaneo Profundo JSON: Extraemos todo lo del año pasado (Uso Agrícola, ETR, etc)
                arch_hist = next((a for a in archivos_drive_hist if a['name'].startswith(f"{clave}_")), None)
                if arch_hist:
                    ruta_hist = os.path.join(CARPETA_JSONS, f"{arch_hist['id']}.json")
                    datos_hist_json = extraer_datos_balance(ruta_hist)
                    for k, v in datos_hist_json.items():
                        # Evitamos duplicar la ruta física del histórico en la fila
                        if k != 'ruta_fisica':
                            fila[f"{k}_{anio_comparacion}"] = v
                
                # 2. Archivo Oficial (Excel): Sobrescribimos DMA y VEAS oficiales publicados
                hist_excel = dict_historico.get(clave, {})
                dma_hist = hist_excel.get('DMA', np.nan)
                veas_hist = hist_excel.get('VEAS', np.nan)
                
                try: dma_hist_num = float(dma_hist) if dma_hist != "N/D" and pd.notna(dma_hist) else np.nan
                except (ValueError, TypeError): dma_hist_num = np.nan

                try: veas_hist_num = float(veas_hist) if veas_hist != "N/D" and pd.notna(veas_hist) else np.nan
                except (ValueError, TypeError): veas_hist_num = np.nan
                
                fila[f"DMA {anio_comparacion}"] = dma_hist_num
                fila[f"VEAS_{anio_comparacion}"] = veas_hist_num
                
                # Recalculamos la evolución usando los datos oficiales de forma numérica limpia
                dma_act = fila.get("Disponibilidad (DMA)", 0.0)
                veas_act = fila.get("VEAS", 0.0)
                
                fila["Evolución DMA (hm³)"] = round(float(dma_act) - dma_hist_num, 6) if pd.notna(dma_hist_num) else np.nan
                fila["Crecimiento VEAS (hm³)"] = round(float(veas_act) - veas_hist_num, 6) if pd.notna(veas_hist_num) else np.nan
                
            datos_maestros.append(fila)
            ids_procesados.add(clave)

    st.session_state["datos_reporte_nacional"] = {
        "datos_maestros": datos_maestros,
        "omitidos_duplicados": omitidos_duplicados,
        "omitidos_errores": omitidos_errores,
        "anio_evaluado": anio_reporte,
        "activar_tendencia": activar_tendencia,
        "anio_base": anio_comparacion
    }
    
    if "ruta_zip_generado" in st.session_state:
        del st.session_state["ruta_zip_generado"]
    st.session_state.pop("aviso_excel_fallidos", None)
        
    time.sleep(1)
    barra_progreso.empty()
    texto_progreso.empty()

# ==========================================
# 3. DASHBOARD Y LAZY ZIPPING PARALELO
# ==========================================
if "datos_reporte_nacional" in st.session_state:
    data_rep = st.session_state["datos_reporte_nacional"]
    datos_maestros = data_rep["datos_maestros"]
    omitidos_duplicados = data_rep["omitidos_duplicados"]
    omitidos_errores = data_rep["omitidos_errores"]
    anio_procesado = data_rep["anio_evaluado"]
    activar_tendencia = data_rep.get("activar_tendencia", False)
    anio_comparacion = data_rep.get("anio_base", None)

    total_exitosos = len(datos_maestros)
    total_fallos = len(omitidos_duplicados) + len(omitidos_errores)
    
    if total_fallos > 0:
        st.warning(f"⚠️ **Auditoría:** Se procesaron {total_exitosos} balances, se omitieron {total_fallos}.")
        with st.expander("🔍 Ver detalles"):
            if omitidos_duplicados:
                st.error("Duplicados:")
                for f in omitidos_duplicados: st.write(f"- {f}")
            if omitidos_errores:
                st.error("Errores:")
                for f in omitidos_errores: st.write(f"- {f}")
    else:
        st.success(f"✅ Los {total_exitosos} balances se procesaron exitosamente.")

    if datos_maestros:
        df_maestro = pd.DataFrame(datos_maestros).replace([float('inf'), float('-inf')], np.nan)
        df_cat = cargar_catalogo("Acuiferos_2026.csv")
        total_nacional = len(df_cat) if not df_cat.empty else 653
        
        if not df_cat.empty:
            df_maestro = df_maestro.merge(df_cat[['CLAVE_SIGM', 'ESTADO']], left_on='Clave', right_on='CLAVE_SIGM', how='left')
            df_maestro['ESTADO'] = df_maestro['ESTADO'].fillna('DESCONOCIDO')
            columnas_finales = ['Clave', 'ESTADO', 'Acuífero'] + [c for c in df_maestro.columns if c not in ['Clave', 'ESTADO', 'Acuífero', 'CLAVE_SIGM', 'ruta_fisica']]
            df_maestro = df_maestro[columnas_finales]
        
        st.markdown("---")
        st.subheader("📊 Panel de Control y Avance de Procesamiento")
        
        with st.expander("🔎 Filtrar Resultados (Por Estado o Acuífero)", expanded=True):
            c_filtro1, c_filtro2 = st.columns(2)
            
            lista_estados = ["Todos (Nacional)"] + sorted(df_maestro['ESTADO'].unique().tolist())
            estado_seleccionado = c_filtro1.selectbox("1. Filtrar por Estado:", lista_estados)
            
            if estado_seleccionado != "Todos (Nacional)":
                df_filtrado = df_maestro[df_maestro['ESTADO'] == estado_seleccionado].copy()
            else:
                df_filtrado = df_maestro.copy()
                
            df_filtrado["Etiqueta_Busqueda"] = df_filtrado["Clave"] + " - " + df_filtrado["Acuífero"]
            lista_acuiferos = ["Todos los del filtro actual"] + sorted(df_filtrado['Etiqueta_Busqueda'].unique().tolist())
            acuif_seleccionado = c_filtro2.selectbox("2. Filtrar por Acuífero específico:", lista_acuiferos)
            
            if acuif_seleccionado != "Todos los del filtro actual":
                clave_filtro = acuif_seleccionado.split(" - ")[0]
                df_filtrado = df_filtrado[df_filtrado["Clave"] == clave_filtro]
                
        total_filtrado = len(df_filtrado)
        dma_filtrado_num = pd.to_numeric(df_filtrado["Disponibilidad (DMA)"], errors='coerce').fillna(0.0)
        acuiferos_deficit = int((dma_filtrado_num < 0).sum())
        porcentaje = (total_exitosos / total_nacional) * 100 if total_nacional > 0 else 0.0
        
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric("Acuíferos Procesados", f"{total_filtrado} de {total_exitosos}") 
        col_kpi2.metric("Avance Nacional", f"{porcentaje:.1f} %")
        col_kpi3.metric("Acuíferos con Déficit", f"{acuiferos_deficit}", delta="DMA < 0 (Déficit)", delta_color="inverse")
        
        es_acuifero_unico = (acuif_seleccionado != "Todos los del filtro actual") and (total_filtrado == 1)
        
        # 1️⃣ CASO: ACUÍFERO ÚNICO (Waterfall de Transición Histórica)
        if es_acuifero_unico and activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
            val_h = df_filtrado[f"DMA {anio_comparacion}"].iloc[0]
            val_a = df_filtrado["Disponibilidad (DMA)"].iloc[0]
            val_d = df_filtrado["Evolución DMA (hm³)"].iloc[0]
            
            if pd.notna(val_h) and pd.notna(val_d):
                fig = go.Figure(go.Waterfall(
                    name="Transición", orientation="v", measure=["absolute", "relative", "total"],
                    x=[f"DMA {anio_comparacion}", "Evolución", f"DMA {anio_procesado}"],
                    textposition="outside", text=[f"{val_h:.2f}", f"{val_d:.2f}", f"{val_a:.2f}"],
                    y=[val_h, val_d, val_a], connector={"line":{"color":"rgb(63, 63, 63)"}},
                    decreasing={"marker":{"color":"#ff6666"}}, increasing={"marker":{"color":"#99ccff"}}, totals={"marker":{"color":"#244062"}}
                ))
                fig.update_layout(height=450, title=f"Transición de Disponibilidad ({anio_comparacion} ➔ {anio_procesado})")
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No hay datos históricos para graficar.")
                
        # 2️⃣ CASO: MULTITUD DE ACUÍFEROS (Dashboard de Inteligencia Hídrica)
        else:
            st.markdown("<br>", unsafe_allow_html=True)
            tab_resumen, tab_riesgo, tab_mapa, tab_distribucion, tab_espacial, tab_ejecutiva, tab_gemelo = st.tabs([
                "📊 Diagnóstico General de Disponibilidad", 
                "⚠️ Condición de Explotación Relativa (R vs DNC + VEAS)", 
                "🗺️ Estructura de Extracción Concesionada (VEAS)", 
                "📈 Dispersión Regional de la Disponibilidad (DMA)",
                "🌎 Evolución Interanual de la Disponibilidad (DMA)",
                "💼 Balance Hidrológico Consolidado y Concentración del Déficit",
                "🔮 Simulación de Escenarios de Disponibilidad"
            ])
            
            # --- TAB 1: RESUMEN (BARRAS Y PASTEL) ---
            with tab_resumen:
                cg1, cg2 = st.columns(2)
                with cg1:
                    if activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
                        evol_serie = pd.to_numeric(df_filtrado['Evolución DMA (hm³)'], errors='coerce')
                        df_graf = df_filtrado[evol_serie.notna()].copy()
                        df_graf['Evolución DMA (hm³)'] = evol_serie[evol_serie.notna()]
                        df_def = df_graf[df_graf['Evolución DMA (hm³)'] < 0].sort_values(by='Evolución DMA (hm³)', ascending=True).head(10)
                        tit, eje = "Top 10 Acuíferos con Mayor Pérdida de Disponibilidad (hm³)", 'Evolución DMA (hm³)'
                    else:
                        dma_serie = pd.to_numeric(df_filtrado["Disponibilidad (DMA)"], errors='coerce')
                        df_graf = df_filtrado[dma_serie.notna()].copy()
                        df_graf['Disponibilidad (DMA)'] = dma_serie[dma_serie.notna()]
                        df_def = df_graf[df_graf["Disponibilidad (DMA)"] < 0].sort_values(by="Disponibilidad (DMA)", ascending=True).head(10)
                        tit, eje = "Top 10 Acuíferos con Mayor Déficit Hídrico (hm³)", "Disponibilidad (DMA)"
                        
                    if not df_def.empty:
                        df_def["E"] = df_def["Clave"] + " " + df_def["Acuífero"]
                        # Color Rojo Institucional
                        fig_d = px.bar(df_def, y="E", x=eje, orientation='h', title=tit, color_discrete_sequence=["#9f2241"], text=eje)
                        fig_d.update_traces(texttemplate='%{text:.2f}', textposition='outside')
                        fig_d.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis=dict(range=[df_def[eje].min()*1.2, 0]), height=400)
                        st.plotly_chart(fig_d, width="stretch")
                    else:
                        st.success("✨ No hay acuíferos con déficit o pérdida en este filtro.")
                        
                with cg2:
                    if activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
                        evol_serie = pd.to_numeric(df_filtrado['Evolución DMA (hm³)'], errors='coerce')
                        df_graf = df_filtrado[evol_serie.notna()].copy()
                        p = len(df_graf[evol_serie < 0])
                        df_p = pd.DataFrame({"Tendencia": ["Recuperación / Estable", "Pérdida Hídrica"], "C": [len(df_graf)-p, p]})
                        col, mapc = "Tendencia", {"Recuperación / Estable":"#285c4d", "Pérdida Hídrica":"#9f2241"}
                    else:
                        df_p = pd.DataFrame({"Condición": ["Con Disponibilidad (Superávit)", "Sin Disponibilidad (Déficit)"], "C": [total_filtrado-acuiferos_deficit, acuiferos_deficit]})
                        col, mapc = "Condición", {"Con Disponibilidad (Superávit)":"#285c4d", "Sin Disponibilidad (Déficit)":"#9f2241"}
                        
                    if total_filtrado > 0:
                        fig_p = px.pie(df_p, values="C", names=col, title="Condición Administrativa Oficial de Disponibilidad", color=col, color_discrete_map=mapc, hole=0.45)
                        fig_p.update_traces(textinfo='percent+label', textposition='inside')
                        fig_p.update_layout(height=400, showlegend=False)
                        st.plotly_chart(fig_p, width="stretch")

            df_riesgo = df_filtrado.copy()
            dnc_num = pd.to_numeric(df_riesgo['DNC'], errors='coerce').fillna(0.0)
            veas_num = pd.to_numeric(df_riesgo['VEAS'], errors='coerce').fillna(0.0)
            dma_num = pd.to_numeric(df_riesgo['Disponibilidad (DMA)'], errors='coerce').fillna(0.0)
            r_num = pd.to_numeric(df_riesgo['Recarga (R)'], errors='coerce').fillna(0.0)

            df_riesgo['Extracción_Total'] = dnc_num + veas_num
            df_riesgo['DMA_Abs'] = dma_num.abs()
            df_riesgo['VEAS_Mapa'] = veas_num.apply(lambda x: x if x > 0 else 0.1)
            df_riesgo['Recarga_Num'] = r_num
            df_riesgo['DMA_Num'] = dma_num

            # --- TAB 2: CONDICIÓN DE EXPLOTACIÓN RELATIVA (SCATTER PLOT) ---
            with tab_riesgo:
                if not df_riesgo.empty:
                    fig_scatter = px.scatter(
                        df_riesgo, 
                        x='Recarga_Num', 
                        y='Extracción_Total', 
                        color='ESTADO',
                        size='DMA_Abs',
                        hover_name='Acuífero',
                        hover_data={"Clave": True, "DMA_Num": ":.2f"},
                        title="Condición de Explotación: Recarga Total (R) vs Compromisos (DNC + VEAS)",
                        labels={"Extracción_Total": "Salidas Comprometidas (DNC + VEAS) [hm³/año]", "Recarga_Num": "Recarga Total (R) [hm³/año]", "DMA_Num": "DMA (hm³)"},
                        color_discrete_sequence=px.colors.qualitative.Prism
                    )
                    max_val = max(df_riesgo['Recarga_Num'].max(), df_riesgo['Extracción_Total'].max()) * 1.05
                    # Línea roja institucional
                    fig_scatter.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val, line=dict(color="#9f2241", dash="dash"))
                    fig_scatter.add_annotation(x=max_val*0.8, y=max_val*0.8, text="Línea de Equilibrio Hidrogeológico (R = DNC + VEAS)", showarrow=False, yshift=15, font=dict(color="#9f2241"))
                    fig_scatter.update_layout(height=500)
                    st.plotly_chart(fig_scatter, use_container_width=True)

            # --- TAB 3: ESTRUCTURA DE EXTRACCIÓN CONCESIONADA (TREEMAP) ---
            with tab_mapa:
                if not df_riesgo.empty:
                    fig_tree = px.treemap(
                        df_riesgo, 
                        path=[px.Constant("México"), 'ESTADO', 'Acuífero'], 
                        values='VEAS_Mapa', 
                        color='DMA_Num', 
                        color_continuous_scale="RdBu", 
                        color_continuous_midpoint=0,
                        hover_name='Acuífero',
                        title="Tamaño = Volumen Concesionado (VEAS) | Color = Disponibilidad Media Anual (Azul: Superávit / Rojo: Déficit)"
                    )
                    fig_tree.update_traces(root_color="lightgrey", marker=dict(line=dict(color='white', width=0.5)))
                    fig_tree.update_layout(height=600, margin=dict(t=40, l=10, r=10, b=10))
                    st.plotly_chart(fig_tree, use_container_width=True)

           # --- TAB 4: DISPERSIÓN REGIONAL (BOXPLOT) ---
            with tab_distribucion:
                if not df_riesgo.empty:
                    fig_box = px.box(
                        df_riesgo, 
                        x='ESTADO', 
                        y='DMA_Num', 
                        color='ESTADO',
                        title="Dispersión y Mediana de la Disponibilidad Media Anual (DMA) por Entidad Federativa",
                        points="all", 
                        hover_name="Acuífero",
                        color_discrete_sequence=px.colors.qualitative.Prism
                    )
                    fig_box.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="Límite 0 hm³", annotation_position="bottom right")
                    fig_box.update_layout(height=500, showlegend=False, xaxis_title="", yaxis_title="Disponibilidad (DMA) hm³")
                    st.plotly_chart(fig_box, use_container_width=True)
            
            # --- TAB 5: MAPAS SINCRONIZADOS (EVOLUCIÓN INTERANUAL) ---
            with tab_espacial:
                @st.fragment
                def _renderizar_mapas_dual(df_riesgo, anio_comparacion, anio_procesado, activar_tendencia):
                    if not activar_tendencia:
                        st.info("💡 Para ver la comparativa de mapas (Evolución Interanual), necesitas habilitar la casilla 'Análisis de Tendencia' al inicio de la página.")
                        return

                    st.write(f"**Comparativa Geoespacial:** Disponibilidad en {anio_comparacion} (Izquierda) vs {anio_procesado} (Derecha).")
                    st.caption("Pinta de rojo 🔴 los acuíferos en condición de déficit (DMA < 0) y de verde 🟢 los acuíferos con disponibilidad (DMA > 0). ¡Mueve un mapa y el otro te seguirá!")
                    
                    cargar_mapas = st.checkbox(
                        "🗺️ Cargar mapas comparativos (pueden tardar unos segundos)", 
                        key="chk_mapas_comparativos"
                    )

                    if cargar_mapas:
                        with st.spinner("Construyendo visualización geográfica de alta velocidad..."):
                            gdf_maestro = obtener_datos_maestros_compartidos()
                        
                            if gdf_maestro is not None and not df_riesgo.empty:
                                gdf_maestro = gdf_maestro.assign(CLV_ACUI=normalizar_serie_clave(gdf_maestro['CLV_ACUI']))
                                df_riesgo_local = df_riesgo.copy()
                                df_riesgo_local['Clave_Str'] = df_riesgo_local['Clave'].astype(str).str.zfill(4)
                            
                                gdf_mapa = gdf_maestro.merge(df_riesgo_local, left_on='CLV_ACUI', right_on='Clave_Str', how='inner')
                            
                                if not gdf_mapa.empty:
                                    # Optimización: Simplificación geométrica para escala nacional (acelera render)
                                    try:
                                        gdf_mapa['geometry'] = gdf_mapa['geometry'].simplify(tolerance=0.005)
                                    except Exception:
                                        pass

                                    # Sanitizar textos para evitar errores en JavaScript
                                    for col in gdf_mapa.columns:
                                        if col != 'geometry':
                                            gdf_mapa[col] = gdf_mapa[col].astype(str)

                                    def semaforo_hidrico(valor):
                                        if pd.isna(valor) or valor in ("N/D", "nan", "None", ""): 
                                            return "#9e9d9e"  # Gris institucional
                                        try:
                                            return "#9f2241" if float(valor) < 0 else "#285c4d"
                                        except (ValueError, TypeError):
                                            return "#9e9d9e"

                                    # Centroide instantáneo sin sobrecargar CPU
                                    minx, miny, maxx, maxy = gdf_mapa.total_bounds
                                    centro_lat = (miny + maxy) / 2.0
                                    centro_lon = (minx + maxx) / 2.0
                                
                                    m_dual = plugins.DualMap(
                                        location=[centro_lat, centro_lon], 
                                        zoom_start=6, 
                                        layout='horizontal',
                                        tiles=None 
                                    )
                                
                                    esri_url = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'
                                    esri_attr = 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ'
                                
                                    folium.TileLayer(tiles=esri_url, attr=esri_attr, name="Mapa Base (Esri)").add_to(m_dual.m1)
                                    folium.TileLayer(tiles=esri_url, attr=esri_attr, name="Mapa Base (Esri)").add_to(m_dual.m2)
                                
                                    titulos_flotantes = f"""
                                        <div style="position: absolute; top: 15px; left: 25%; transform: translateX(-50%); z-index: 9999; 
                                                    background-color: white; padding: 6px 20px; border-radius: 20px; 
                                                    box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-family: 'Segoe UI', sans-serif; 
                                                    font-size: 14px; font-weight: bold; color: #691C32; border: 2px solid #691C32;">
                                            Disponibilidad {anio_comparacion}
                                        </div>
                                        <div style="position: absolute; top: 15px; left: 75%; transform: translateX(-50%); z-index: 9999; 
                                                    background-color: white; padding: 6px 20px; border-radius: 20px; 
                                                    box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-family: 'Segoe UI', sans-serif; 
                                                    font-size: 14px; font-weight: bold; color: #244062; border: 2px solid #244062;">
                                            Disponibilidad {anio_procesado}
                                        </div>
                                    """
                                    m_dual.get_root().html.add_child(folium.Element(titulos_flotantes))

                                    # Capa Mapa Izquierdo (Histórico)
                                    folium.GeoJson(
                                        gdf_mapa,
                                        name=f"Año {anio_comparacion}",
                                        style_function=lambda feature: {
                                            'fillColor': semaforo_hidrico(feature['properties'].get(f'DMA {anio_comparacion}')),
                                            'color': '#333333', 'weight': 0.7, 'fillOpacity': 0.75
                                        },
                                        tooltip=folium.GeoJsonTooltip(
                                            fields=['NOM_ACUI', f'DMA {anio_comparacion}'], 
                                            aliases=['Acuífero:', f'DMA {anio_comparacion}:']
                                        )
                                    ).add_to(m_dual.m1)

                                    # Capa Mapa Derecho (Procesado)
                                    folium.GeoJson(
                                        gdf_mapa,
                                        name=f"Año {anio_procesado}",
                                        style_function=lambda feature: {
                                            'fillColor': semaforo_hidrico(feature['properties'].get('Disponibilidad (DMA)')),
                                            'color': '#333333', 'weight': 0.7, 'fillOpacity': 0.75
                                        },
                                        tooltip=folium.GeoJsonTooltip(
                                            fields=['NOM_ACUI', 'Disponibilidad (DMA)'], 
                                            aliases=['Acuífero:', f'DMA {anio_procesado}:']
                                        )
                                    ).add_to(m_dual.m2)

                                    # Renderizado unidireccional directo (sin eventos de retorno que causen reruns)
                                    import streamlit.components.v1 as _components
                                    mapa_html = m_dual.get_root().render()
                                    _components.html(mapa_html, height=620)
                                else:
                                    st.warning("No se encontraron coincidencias geográficas para estos acuíferos.")

                _renderizar_mapas_dual(df_riesgo, anio_comparacion, anio_procesado, activar_tendencia)

            # --- TAB 6: BALANCE HIDROLÓGICO CONSOLIDADO Y CONCENTRACIÓN DEL DÉFICIT ---
            with tab_ejecutiva:
                st.write("Visión Estratégica: Balance Hidrológico Consolidado y Concentración del Déficit.")
                
                col_exec1, col_exec2 = st.columns(2)
                
                with col_exec1:
                    # 1. MACRO-WATERFALL (Contabilidad del Agua Oficial)
                    r_tot = pd.to_numeric(df_filtrado['Recarga (R)'], errors='coerce').sum()
                    dnc_tot = pd.to_numeric(df_filtrado['DNC'], errors='coerce').sum()
                    veas_tot = pd.to_numeric(df_filtrado['VEAS'], errors='coerce').sum()
                    dma_tot = pd.to_numeric(df_filtrado['Disponibilidad (DMA)'], errors='coerce').sum()
                    
                    fig_macro = go.Figure(go.Waterfall(
                        orientation="v",
                        measure=["relative", "relative", "relative", "total"],
                        x=["1. Recarga Total Media Anual (R)", "2. Descarga Natural Comprometida (DNC)", "3. Volumen Concesionado (VEAS)", "4. Disponibilidad Media Anual (DMA)"],
                        textposition="outside",
                        text=[f"+{r_tot:,.1f}", f"-{dnc_tot:,.1f}", f"-{veas_tot:,.1f}", f"{dma_tot:,.1f}"],
                        y=[r_tot, -dnc_tot, -veas_tot, dma_tot],
                        connector={"line": {"color": "rgb(63, 63, 63)"}},
                        decreasing={"marker": {"color": "#9f2241"}},  # Rojo Inst
                        increasing={"marker": {"color": "#285c4d"}},  # Verde Inst
                        totals={"marker": {"color": "#b38e5d" if dma_tot >= 0 else "#691c32"}} # Dorado o Guinda Oscuro
                    ))
                    fig_macro.update_layout(
                        title="Balance Hidrológico Consolidado (Suma del Filtro Actual)",
                        height=500, margin=dict(t=75, b=50)
                    )
                    st.plotly_chart(fig_macro, use_container_width=True)
                    
                with col_exec2:
                    # 2. CURVA DE PARETO (Focalización del Déficit)
                    dma_serie_p = pd.to_numeric(df_filtrado['Disponibilidad (DMA)'], errors='coerce')
                    df_deficit = df_filtrado[dma_serie_p < 0].copy()
                    
                    if not df_deficit.empty:
                        df_deficit['Deficit_Abs'] = dma_serie_p[dma_serie_p < 0].abs()
                        df_deficit = df_deficit.sort_values(by='Deficit_Abs', ascending=False)
                        df_deficit['Porcentaje_Acumulado'] = (df_deficit['Deficit_Abs'].cumsum() / df_deficit['Deficit_Abs'].sum()) * 100
                        
                        fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
                        
                        fig_pareto.add_trace(
                            go.Bar(x=df_deficit['Acuífero'], y=df_deficit['Deficit_Abs'], name="Volumen de Déficit (hm³)", marker_color="#9f2241"), # Rojo Inst
                            secondary_y=False,
                        )
                        fig_pareto.add_trace(
                            go.Scatter(x=df_deficit['Acuífero'], y=df_deficit['Porcentaje_Acumulado'], name="% Acumulado", mode="lines+markers", line=dict(color="#244062", width=3)),
                            secondary_y=True,
                        )
                        
                        fig_pareto.update_layout(
                            title="Concentración Acumulada del Déficit (Análisis de Pareto)",
                            height=500, margin=dict(t=75, b=50), showlegend=False
                        )
                        fig_pareto.update_yaxes(title_text="Volumen de Déficit |DMA| (hm³)", secondary_y=False)
                        fig_pareto.update_yaxes(title_text="Porcentaje Acumulado (%)", range=[0, 105], secondary_y=True)
                        
                        st.plotly_chart(fig_pareto, use_container_width=True)
                    else:
                        st.success("✨ Excelente noticia: No hay déficit hídrico en la región seleccionada para generar la Curva de Pareto.")
        # --- TAB 7: GEMELO DIGITAL (SIMULADOR WHAT-IF) ---
            with tab_gemelo:
                @st.fragment
                def _renderizar_gemelo(df_filtrado):
                    st.write("### 🔮 Simulación de Escenarios de Disponibilidad")
                    st.caption("Ajusta las variables hidroclimáticas y de extracción para proyectar el impacto en la disponibilidad futura de la región seleccionada. (Los cambios son simulados y no afectan la base de datos oficial).")
                
                    with st.container(border=True):
                        col_sim1, col_sim2 = st.columns(2)
                        var_clima = col_sim1.slider(
                            "🌧️ Variación en la Recarga Total (R) [%]", 
                            min_value=-50, max_value=50, value=0, step=1, 
                            help="Simula periodos de sequía prolongada (valores negativos) o años atípicamente húmedos (valores positivos)."
                        )
                        var_demanda = col_sim2.slider(
                            "🏭 Variación en el Volumen de Extracción (VEAS) [%]", 
                            min_value=-50, max_value=100, value=0, step=1, 
                            help="Simula el impacto del incremento en concesiones del REPDA o mayor demanda de bombeo."
                        )

                    # ==========================================
                    # MOTOR MATEMÁTICO DEL SIMULADOR
                    # ==========================================
                    df_sim = df_filtrado.copy()
                    r_orig = pd.to_numeric(df_sim['Recarga (R)'], errors='coerce').fillna(0.0)
                    veas_orig = pd.to_numeric(df_sim['VEAS'], errors='coerce').fillna(0.0)
                    dma_orig = pd.to_numeric(df_sim['Disponibilidad (DMA)'], errors='coerce').fillna(0.0)
                    dnc_orig = pd.to_numeric(df_sim['DNC'], errors='coerce').fillna(0.0)
                
                    # 1. Calculamos el volumen diferencial (Delta) exacto generado por los sliders
                    delta_recarga = r_orig * (var_clima / 100.0)
                    delta_veas = veas_orig * (var_demanda / 100.0)
                
                    # 2. Aplicamos el Delta a los totales para visualización
                    df_sim['Recarga_Simulada'] = r_orig + delta_recarga
                    df_sim['VEAS_Simulado'] = veas_orig + delta_veas
                
                    # 3. Sumamos/Restamos el Delta directamente a la DMA original (Evita errores de redondeo)
                    df_sim['DMA_Simulada'] = (dma_orig + delta_recarga - delta_veas).round(6)
                
                    # Calcular Impactos Macro
                    r_tot_sim = df_sim['Recarga_Simulada'].sum()
                    dnc_tot = dnc_orig.sum() 
                    veas_tot_sim = df_sim['VEAS_Simulado'].sum()
                    dma_tot_sim = df_sim['DMA_Simulada'].sum()
                    dma_tot_original = dma_orig.sum()
                
                    diferencia_neta = dma_tot_sim - dma_tot_original

                    # Encontrar acuíferos críticos (Nuevos) y Agravados (Peores)
                    df_sim['Estado_Original'] = np.where(dma_orig < 0, 'Déficit', 'Superávit')
                    df_sim['Estado_Simulado'] = np.where(df_sim['DMA_Simulada'] < 0, 'Déficit', 'Superávit')
                
                    # 1. Los que acaban de pasar a números rojos
                    cond_nuevos = (df_sim['Estado_Original'] == 'Superávit') & (df_sim['Estado_Simulado'] == 'Déficit')
                    # 2. Los que ya estaban en rojo y perdieron AÚN MÁS agua
                    cond_agravados = (df_sim['Estado_Original'] == 'Déficit') & (df_sim['DMA_Simulada'] < dma_orig)
                
                    df_sim['Categoria_Alerta'] = "Sin peligro crítico"
                    df_sim.loc[cond_nuevos, 'Categoria_Alerta'] = "🚨 Nuevo Déficit"
                    df_sim.loc[cond_agravados, 'Categoria_Alerta'] = "📉 Déficit Agravado"
                
                    df_alertas = df_sim[df_sim['Categoria_Alerta'] != "Sin peligro crítico"].copy()
                
                    # ==========================================
                    # VISUALIZACIÓN DEL IMPACTO
                    # ==========================================
                    st.markdown("#### 📉 Resultados de la Simulación")
                
                    col_res1, col_res2, col_res3 = st.columns(3)
                    col_res1.metric("Nuevo Balance Neto (DMA)", f"{dma_tot_sim:,.1f} hm³", f"{diferencia_neta:,.1f} hm³", delta_color="normal")
                
                    total_deficit_sim = len(df_sim[df_sim['Estado_Simulado'] == 'Déficit'])
                    nuevos_count = len(df_sim[cond_nuevos])
                    agravados_count = len(df_sim[cond_agravados])
                
                    col_res2.metric("Total Acuíferos en Déficit", f"{total_deficit_sim}", f"+{nuevos_count} nuevos | {agravados_count} agravados", delta_color="inverse")
                
                    diferencia_recarga = r_tot_sim - r_orig.sum()
                    col_res3.metric("Impacto en Recarga", f"{r_tot_sim:,.1f} hm³", f"{diferencia_recarga:,.1f} hm³", delta_color="normal")

                    st.divider()
                
                    col_chart1, col_chart2 = st.columns(2)
                
                    with col_chart1:
                        fig_sim_macro = go.Figure(go.Waterfall(
                            orientation="v",
                            measure=["relative", "relative", "relative", "total"],
                            x=["1. Recarga Total Simulada", "2. DNC", "3. VEAS Simulado", "4. DMA Proyectada"],
                            textposition="outside",
                            text=[f"+{r_tot_sim:,.1f}", f"-{dnc_tot:,.1f}", f"-{veas_tot_sim:,.1f}", f"{dma_tot_sim:,.1f}"],
                            y=[r_tot_sim, -dnc_tot, -veas_tot_sim, dma_tot_sim],
                            connector={"line": {"color": "rgb(63, 63, 63)"}},
                            decreasing={"marker": {"color": "#9f2241"}},
                            increasing={"marker": {"color": "#285c4d"}},
                            totals={"marker": {"color": "#b38e5d" if dma_tot_sim >= 0 else "#691c32"}}
                        ))
                        fig_sim_macro.update_layout(title="Contabilidad Hídrica en Escenario Proyectado", height=450, margin=dict(t=50, b=50))
                        st.plotly_chart(fig_sim_macro, use_container_width=True)
                    
                    with col_chart2:
                        if not df_alertas.empty:
                            frases_alerta = []
                            if nuevos_count > 0:
                                frases_alerta.append(f"**{nuevos_count}** acuíferos sanos entrarían en déficit")
                            if agravados_count > 0:
                                frases_alerta.append(f"**{agravados_count}** acuíferos sobreexplotados empeorarían su situación")
                            
                            texto_unido = " y ".join(frases_alerta)
                            st.error(f"🚨 **ALERTA HÍDRICA:** Bajo este escenario, {texto_unido}.")
                        
                            df_alertas['Impacto (Pérdida)'] = df_alertas['DMA_Simulada'] - df_alertas['Disponibilidad (DMA)']
                        
                            st.dataframe(
                                df_alertas[['Acuífero', 'Categoria_Alerta', 'Disponibilidad (DMA)', 'DMA_Simulada', 'Impacto (Pérdida)']].rename(columns={'Disponibilidad (DMA)': 'DMA Actual'}),
                                use_container_width=True, hide_index=True
                            )
                        else:
                            st.success("✅ Bajo este escenario, ningún acuífero entra en nuevo déficit ni empeora su situación actual.")

                _renderizar_gemelo(df_filtrado)

        st.markdown("---")
        st.subheader(f"📑 Resumen de Balances ({anio_procesado})")
        
        def color_semaforo(val):
            if isinstance(val, (int, float)) and not pd.isna(val):
                # Fondo muy suave: Rosado institucional para negativo, Verde claro para positivo
                return f"background-color: {'#f5e6e8' if val < 0 else '#e8f0ec'}; color: {'#691c32' if val < 0 else '#1a3b32'}; font-weight: bold;"
            return ""
            
        col_c = ['Disponibilidad (DMA)']
        if activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
            col_c.append('Evolución DMA (hm³)')
            
        df_mostrar = df_filtrado.drop(columns=["Etiqueta_Busqueda", "ruta_fisica"], errors='ignore').copy().fillna("N/D")
        st.dataframe(df_mostrar.style.map(color_semaforo, subset=col_c), width="stretch", hide_index=True)

        # -----------------------------------------------------------
        # 🚀 DESCARGAS ENTERPRISE: MULTITHREADING A DISCO
        # -----------------------------------------------------------
        @st.fragment
        def renderizar_botones_descarga():
            cd1, cd2, _ = st.columns([1.5, 1.5, 1])
            
            with cd1:
                st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
                
                if "ruta_zip_generado" not in st.session_state or not os.path.exists(st.session_state["ruta_zip_generado"]):
                    if st.button("📦 1. Preparar Descarga de Balances (ZIP)", type="primary", width="stretch"):
                        
                        with st.status("🚀 Procesamiento Paralelo: Empaquetando en Disco...", expanded=True) as status:
                            st.write("Generando matriz del Resumen Nacional...")
                            
                            zip_path = os.path.join(USER_TEMP_DIR, f"Paquete_Balances_Nacionales_{anio_procesado}.zip")
                            
                            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                                
                                # 1. Resumen Maestro Nacional a disco temporal
                                ruta_resumen = os.path.join(USER_TEMP_DIR, f"00_Resumen_Nacional_{anio_procesado}.xlsx")
                                df_maestro.drop(columns=['Etiqueta_Busqueda', 'ruta_fisica'], errors='ignore').fillna("N/D").to_excel(ruta_resumen, index=False, sheet_name="Resumen_Nacional")
                                z.write(ruta_resumen, arcname=f"00_Resumen_Nacional_{anio_procesado}.xlsx")
                                try:
                                    os.remove(ruta_resumen)
                                except OSError:
                                    pass
                                
                                # 2. Generación Multi-hilo de Excels (Velocidad x8)
                                st.write("⚡ Calculando matrices en paralelo...")
                                avance = st.progress(0)
                                
                                total_archivos = len(datos_maestros)
                                procesados = 0
                                fallidos_excel = []
                                
                                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                                    futuros = {executor.submit(worker_generar_excel, f_m, anio_procesado, USER_TEMP_DIR): f_m for f_m in datos_maestros}
                                    
                                    for fut in concurrent.futures.as_completed(futuros):
                                        resultado = fut.result()
                                        if resultado:
                                            ruta_ind, arc_name = resultado
                                            z.write(ruta_ind, arcname=arc_name)
                                            os.remove(ruta_ind)
                                        else:
                                            fallidos_excel.append(str(futuros[fut].get("Clave", "?")))
                                            
                                        procesados += 1
                                        avance.progress(procesados / total_archivos)
                                        
                                        # Garbage collector para cuidar la RAM
                                        if procesados % 25 == 0:
                                            gc.collect()
                                        
                            st.session_state["ruta_zip_generado"] = zip_path
                            st.session_state["aviso_excel_fallidos"] = fallidos_excel
                            status.update(label="✅ Paquete ZIP generado a velocidad máxima", state="complete", expanded=False)
                            st.rerun()
                
                else:
                    _fallidos = st.session_state.get("aviso_excel_fallidos") or []
                    if _fallidos:
                        st.warning(f"⚠️ No se pudo generar el Excel individual de {len(_fallidos)} acuíferos (claves: {', '.join(_fallidos[:15])}{'…' if len(_fallidos) > 15 else ''}). El ZIP no los incluye.")
                    with open(st.session_state["ruta_zip_generado"], "rb") as f:
                        st.download_button(
                            label="📥 2. Descargar Balances (ZIP) Ahora", 
                            data=f, 
                            file_name=f"Paquete_Balances_Nacionales_{anio_procesado}.zip", 
                            mime="application/zip", 
                            type="primary", 
                            width="stretch"
                        )
                        
            with cd2:
                st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
                if not df_cat.empty and total_exitosos < total_nacional:
                    claves_listas = df_maestro["Clave"].tolist()
                    df_faltantes = df_cat[~df_cat["CLAVE_SIGM"].isin(claves_listas)].copy()
                    csv_f = df_faltantes.to_csv(index=False).encode('utf-8-sig')
                    
                    st.download_button("🚨 Descargar Faltantes (CSV)", data=csv_f, file_name=f"Acuiferos_Faltantes_{anio_procesado}.csv", mime="text/csv", type="secondary", width="stretch")

        renderizar_botones_descarga()
