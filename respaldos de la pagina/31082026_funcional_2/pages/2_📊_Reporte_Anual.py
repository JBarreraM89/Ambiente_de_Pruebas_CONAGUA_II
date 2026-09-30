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
import numpy as np
from google.auth.transport.requests import Request
from streamlit_folium import st_folium
from plotly.subplots import make_subplots

# --- IMPORTACIONES DEL CORE (FASE 1 y 2) ---
from utils.styles import inyectar_css_oficial, banner_institucional, inyectar_css_navegacion
from core.drive_api import buscar_metadatos_drive, descargar_json_crudo_rapido, obtener_servicio_drive
from core.generador_excel import generar_excel_matriz
from core.data_loader import cargar_catalogo, cargar_historico_excel, cargar_datos_maestros

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
    
    for intento in range(retries):
        try:
            data = descargar_json_crudo_rapido(id_arch, token)
            if not data:
                return {"estado": "error", "id": id_arch, "name": nom_arch}
            
            ruta_json_fisico = os.path.join(CARPETA_JSONS, f"{id_arch}.json")
            with open(ruta_json_fisico, 'w', encoding='utf-8') as f:
                json.dump(data, f)
                
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

        rr_val = float(conf.get("rr_val", 0.0))
        o_sal = conf.get("otras_salidas", {})
        val_ssb = float(o_sal.get("Ssb", 0.0))
        val_dfb = float(o_sal.get("Dfb", 0.0))
        val_dm = float(o_sal.get("Dm", 0.0))
        val_rv_calc = float(res.get("Rv", 0.0))
        val_ri_calc = float(res.get("Ri", 0.0))
        dnc_total_calc = float(res.get("DNC_total", 0.0))
        veas_calc = float(res.get("VEAS", 0.0))
        disponibilidad_calc = float(res.get("Disponibilidad_Oficial", 0.0))

        periodo_dvs = conf.get("periodo_dvs", {})
        a_base = int(periodo_dvs.get("a_base", 2020))
        a_tope = int(periodo_dvs.get("a_tope", 2025))
        rda = a_tope - a_base
        dvs_anualizado = float(res.get("DVS", DVS_t / rda if rda > 0 else 0.0))

        recarga_t = round(rr_val + eh_acumulado + eas_acumulado + val_rv_calc + val_ri_calc, 1)
        descarga_t = round(bombeo_calc + sh_acumulado + etr_acumulado + val_ssb + val_dfb + val_dm, 1)

        df_ind_resumen = pd.DataFrame([
            {"Concepto": "Recarga Vertical por Lluvia (Rr)", "Volumen (hm³)": rr_val},
            {"Concepto": "Entradas Horizontales (Eh)", "Volumen (hm³)": eh_acumulado},
            {"Concepto": "Entradas de Agua Salobre (Eas)", "Volumen (hm³)": eas_acumulado},
            {"Concepto": "Recarga Vertical Resultante (Rv)", "Volumen (hm³)": val_rv_calc},
            {"Concepto": "Recarga Incidental (Ri)", "Volumen (hm³)": val_ri_calc},
            {"Concepto": "RECARGA TOTAL (R)", "Volumen (hm³)": recarga_t},
            {"Concepto": "Extracción / Bombeo (B)", "Volumen (hm³)": bombeo_calc},
            {"Concepto": "Salidas Horizontales (Sh)", "Volumen (hm³)": sh_acumulado},
            {"Concepto": "Evapotranspiración (ETR)", "Volumen (hm³)": etr_acumulado},
            {"Concepto": "Salidas Subterráneas (Ssb)", "Volumen (hm³)": val_ssb},      
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
        generar_excel_matriz(df_ind_resumen, df_eh, df_usos, df_sh, df_etr, df_dvs, df_eas, dvs_anualizado, fuente_b, anio_b, a_base, a_tope, rda, destino_salida=ruta_ind)
        
        return (ruta_ind, f"Balances_Individuales/{nom_x}")
    except Exception as e:
        print(f"Error generando Excel para Acuífero {f_maestra.get('Clave')}: {e}")
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
        
        res = dat.get("resultados", {})
        conf = dat.get("configuracion", {})
        tabs = dat.get("tablas", {})
        
        df_usos = pd.DataFrame(tabs.get('usos', []))
        usos_totales = {
            "Uso_Agricola": 0.0, "Uso_Agroindustrial": 0.0, "Uso_Domestico": 0.0, 
            "Uso_Acuacultura": 0.0, "Uso_Servicios": 0.0, "Uso_Industrial": 0.0, 
            "Uso_Pecuario": 0.0, "Uso_Publico_Urbano": 0.0, "Uso_Diferentes": 0.0, 
            "Uso_Energia": 0.0, "Uso_Comercio": 0.0, "Uso_Otros": 0.0, "Uso_Ecologica": 0.0
        }
        
        if not df_usos.empty and 'Volumen [hm³/año]' in df_usos.columns:
            df_usos['Volumen [hm³/año]'] = pd.to_numeric(df_usos['Volumen [hm³/año]'], errors='coerce').fillna(0.0)
            for _, r_uso in df_usos.iterrows():
                tipo = str(r_uso.get('Tipo de Uso', '')).strip().upper()
                vol = float(r_uso['Volumen [hm³/año]'])
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

        datos = {
            "Recarga (R)": round(res.get('Recarga_Total', 0.0), 1),
            "Rv": round(float(res.get("Rv", 0.0)), 1), 
            "Ri": round(float(res.get("Ri", 0.0)), 1), 
            "Rr": float(conf.get("rr_val", 0.0)),
            "Bombeo (B)": round(res.get('B_total', 0.0), 1),
            "DNC": round(res.get('DNC_total', 0.0), 1),
            "ETR": round(float(res.get('ETR', 0.0)), 1),
            "Ssb": float(conf.get("otras_salidas", {}).get("Ssb", 0.0)), 
            "Dfb": float(conf.get("otras_salidas", {}).get("Dfb", 0.0)), 
            "Dm": float(conf.get("otras_salidas", {}).get("Dm", 0.0)), 
            "PME": float(conf.get("PME", 5.0)),
            "VEAS": round(res.get('VEAS', 0.0), 6), 
            "ΔV(S)": round(res.get('DVS', 0.0), 1),
            "Disponibilidad (DMA)": round(res.get('Disponibilidad_Oficial', 0.0), 6)
        }
        datos.update({k: round(v, 2) for k, v in usos_totales.items()})
        return datos
    except:
        return {}


col_y1, col_y2 = st.columns(2)
anio_reporte = col_y1.number_input("Selecciona el Año de Evaluación a procesar:", min_value=2020, max_value=2100, value=datetime.datetime.now().year, step=1)
st.markdown("<br>", unsafe_allow_html=True)
activar_tendencia = st.checkbox("📈 Habilitar Análisis de Tendencia (Comparativa vs Publicación Anterior)")

anio_comparacion = None
if activar_tendencia:
    anio_comparacion = col_y2.number_input("Año de Publicación Anterior:", min_value=2015, max_value=2100, value=2023, step=1)

if st.button("🔍 Escanear Drive y Generar Reporte", type="primary"):
    limpiar_temporales_antiguos()    
    if activar_tendencia and anio_comparacion >= anio_reporte:
        st.error("⚠️ Error de lógica temporal: El año histórico no puede ser mayor o igual al evaluado.")
        st.stop()
        
    dict_historico = cargar_historico_excel("DMA_VEAS.xlsx", anio_comparacion) if activar_tendencia else {}

    # Buscar JSONs del año actual y del año histórico
    archivos_drive_actual = buscar_metadatos_drive(anio_reporte)
    archivos_drive_hist = buscar_metadatos_drive(anio_comparacion) if activar_tendencia else []
    
    if not archivos_drive_actual:
        st.warning(f"No se encontraron archivos en Drive para el año {anio_reporte}.")
        st.stop()

    archivos_totales = archivos_drive_actual + archivos_drive_hist

    texto_progreso = st.empty()
    barra_progreso = st.progress(0)
    
    cache_index = {}
    if os.path.exists(INDEX_CACHE):
        with open(INDEX_CACHE, 'r') as f:
            cache_index = json.load(f)

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
        
        _, cred = obtener_servicio_drive()
        if cred: cred.refresh(Request())
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futuros = {executor.submit(worker_extraccion, arch, cred.token): arch for arch in archivos_a_descargar}
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
            
            fila = {
                "Clave": clave,
                "Acuífero": " ".join(fnom.split('_')[1:-1]),
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
                dma_hist = hist_excel.get('DMA', "N/D")
                veas_hist = hist_excel.get('VEAS', "N/D")
                
                fila[f"DMA {anio_comparacion}"] = dma_hist
                fila[f"VEAS_{anio_comparacion}"] = veas_hist
                
                # Recalculamos la evolución usando los datos oficiales
                dma_act = fila.get("Disponibilidad (DMA)", 0.0)
                veas_act = fila.get("VEAS", 0.0)
                
                fila[f"Evolución DMA (hm³)"] = round(dma_act - dma_hist, 6) if dma_hist != "N/D" else "N/D"
                fila[f"Crecimiento VEAS (hm³)"] = round(veas_act - veas_hist, 6) if veas_hist != "N/D" else "N/D"
                
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
        df_maestro = pd.DataFrame(datos_maestros).replace([float('inf'), float('-inf')], 0.0).fillna("N/D")
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
        acuiferos_deficit = len(df_filtrado[df_filtrado["Disponibilidad (DMA)"] < 0])
        porcentaje = (total_exitosos / total_nacional) * 100 if total_nacional > 0 else 0.0
        
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric("Acuíferos Procesados", f"{total_filtrado} de {total_exitosos}") 
        col_kpi2.metric("Avance Nacional", f"{porcentaje:.1f} %")
        col_kpi3.metric("Acuíferos con Déficit", f"{acuiferos_deficit}", delta="Sobreexplotados", delta_color="inverse")
        
        es_acuifero_unico = (acuif_seleccionado != "Todos los del filtro actual") and (total_filtrado == 1)
        
        # 1️⃣ CASO: ACUÍFERO ÚNICO (Waterfall de Transición Histórica)
        if es_acuifero_unico and activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
            val_h = df_filtrado[f"DMA {anio_comparacion}"].iloc[0]
            val_a = df_filtrado["Disponibilidad (DMA)"].iloc[0]
            val_d = df_filtrado["Evolución DMA (hm³)"].iloc[0]
            
            if val_h != "N/D" and val_d != "N/D":
                fig = go.Figure(go.Waterfall(
                    name="20", orientation="v", measure=["absolute", "relative", "total"],
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
            tab_resumen, tab_riesgo, tab_mapa, tab_distribucion, tab_espacial, tab_ejecutiva = st.tabs([
                "📊 Resumen y Alertas", 
                "⚠️ Matriz de Estrés", 
                "🗺️ Radiografía Nacional", 
                "📈 Distribución Estadística",
                "🌎 Mapas (Antes y Después)",
                "💼 Contabilidad y Prioridades"
            ])
            
            # --- TAB 1: RESUMEN (BARRAS Y PASTEL) ---
            with tab_resumen:
                cg1, cg2 = st.columns(2)
                with cg1:
                    if activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
                        df_graf = df_filtrado[df_filtrado['Evolución DMA (hm³)'] != "N/D"].copy()
                        df_graf['Evolución DMA (hm³)'] = pd.to_numeric(df_graf['Evolución DMA (hm³)'] )
                        df_def = df_graf[df_graf['Evolución DMA (hm³)'] < 0].sort_values(by='Evolución DMA (hm³)', ascending=True).head(10)
                        tit, eje = "Top 10 Mayores Pérdidas de Agua (hm³)", 'Evolución DMA (hm³)'
                    else:
                        df_def = df_filtrado[df_filtrado["Disponibilidad (DMA)"] < 0].sort_values(by="Disponibilidad (DMA)", ascending=True).head(10)
                        tit, eje = "Top 10 Déficit Hídrico más severo (hm³)", "Disponibilidad (DMA)"
                        
                    if not df_def.empty:
                        df_def["E"] = df_def["Clave"] + " " + df_def["Acuífero"]
                        fig_d = px.bar(df_def, y="E", x=eje, orientation='h', title=tit, color_discrete_sequence=["#e74c3c"], text=eje)
                        fig_d.update_traces(texttemplate='%{text:.2f}', textposition='outside')
                        fig_d.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis=dict(range=[df_def[eje].min()*1.2, 0]), height=400)
                        st.plotly_chart(fig_d, width="stretch")
                    else:
                        st.success("✨ No hay acuíferos con déficit o pérdida en este filtro.")
                        
                with cg2:
                    if activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
                        df_graf = df_filtrado[df_filtrado['Evolución DMA (hm³)'] != "N/D"].copy()
                        df_graf['Evolución DMA (hm³)'] = pd.to_numeric(df_graf['Evolución DMA (hm³)'])
                        p = len(df_graf[df_graf['Evolución DMA (hm³)'] < 0])
                        df_p = pd.DataFrame({"Tendencia": ["Recuperación / Estable", "Pérdida Hídrica"], "C": [len(df_graf)-p, p]})
                        col, mapc = "Tendencia", {"Recuperación / Estable":"#3498db", "Pérdida Hídrica":"#e74c3c"}
                    else:
                        df_p = pd.DataFrame({"E": ["Con Disponibilidad (Superávit)", "Con Déficit (Sobreexplotados)"], "C": [total_filtrado-acuiferos_deficit, acuiferos_deficit]})
                        col, mapc = "E", {"Con Disponibilidad (Superávit)":"#3498db", "Con Déficit (Sobreexplotados)":"#e74c3c"}
                        
                    if total_filtrado > 0:
                        fig_p = px.pie(df_p, values="C", names=col, title="Proporción Nacional / Regional", color=col, color_discrete_map=mapc, hole=0.45)
                        fig_p.update_traces(textinfo='percent+label', textposition='inside')
                        fig_p.update_layout(height=400, showlegend=False)
                        st.plotly_chart(fig_p, width="stretch")

            # Preparar DataFrames especiales para los siguientes gráficos
            df_riesgo = df_filtrado.copy()
            df_riesgo['Extracción_Total'] = pd.to_numeric(df_riesgo['DNC']) + pd.to_numeric(df_riesgo['VEAS'])
            df_riesgo['DMA_Abs'] = pd.to_numeric(df_riesgo['Disponibilidad (DMA)']).abs()
            # El treemap requiere valores positivos para el tamaño
            df_riesgo['VEAS_Mapa'] = pd.to_numeric(df_riesgo['VEAS']).apply(lambda x: x if x > 0 else 0.1)

            # --- TAB 2: MATRIZ DE ESTRÉS HÍDRICO (SCATTER PLOT) ---
            with tab_riesgo:
                if not df_riesgo.empty:
                    fig_scatter = px.scatter(
                        df_riesgo, 
                        x='Recarga (R)', 
                        y='Extracción_Total', 
                        color='ESTADO',
                        size='DMA_Abs',
                        hover_name='Acuífero',
                        hover_data={"Clave": True, "Disponibilidad (DMA)": ":.2f"},
                        title="Matriz de Estrés: Recarga Natural (Entradas) vs Compromisos (DNC + VEAS)",
                        labels={"Extracción_Total": "Salidas Comprometidas (hm³)", "Recarga (R)": "Recarga Total (hm³)"},
                        color_discrete_sequence=px.colors.qualitative.Prism
                    )
                    # Línea de equilibrio donde Recarga = Extracción
                    max_val = max(df_riesgo['Recarga (R)'].max(), df_riesgo['Extracción_Total'].max()) * 1.05
                    fig_scatter.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val, line=dict(color="red", dash="dash"))
                    fig_scatter.add_annotation(x=max_val*0.8, y=max_val*0.8, text="Línea de Sobreexplotación", showarrow=False, yshift=15, font=dict(color="red"))
                    fig_scatter.update_layout(height=500)
                    st.plotly_chart(fig_scatter, use_container_width=True)

            # --- TAB 3: RADIOGRAFÍA NACIONAL (TREEMAP JERÁRQUICO) ---
            with tab_mapa:
                if not df_riesgo.empty:
                    fig_tree = px.treemap(
                        df_riesgo, 
                        path=[px.Constant("México"), 'ESTADO', 'Acuífero'], 
                        values='VEAS_Mapa', 
                        color='Disponibilidad (DMA)', 
                        color_continuous_scale="RdBu", 
                        color_continuous_midpoint=0,
                        hover_name='Acuífero',
                        title="Tamaño = Volumen Concesionado (VEAS) | Color = Salud del Acuífero (Azul: Sano / Rojo: Crítico)"
                    )
                    fig_tree.update_traces(root_color="lightgrey", marker=dict(line=dict(color='white', width=0.5)))
                    fig_tree.update_layout(height=600, margin=dict(t=40, l=10, r=10, b=10))
                    st.plotly_chart(fig_tree, use_container_width=True)

           # --- TAB 4: DISTRIBUCIÓN ESTADÍSTICA (BOXPLOT) ---
            with tab_distribucion:
                if not df_riesgo.empty:
                    fig_box = px.box(
                        df_riesgo, 
                        x='ESTADO', 
                        y='Disponibilidad (DMA)', 
                        color='ESTADO',
                        title="Dispersión y Mediana de Disponibilidad por Estado",
                        points="all", 
                        hover_name="Acuífero",
                        color_discrete_sequence=px.colors.qualitative.Prism
                    )
                    fig_box.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="Límite 0 hm³", annotation_position="bottom right")
                    fig_box.update_layout(height=500, showlegend=False, xaxis_title="", yaxis_title="Disponibilidad (DMA) hm³")
                    st.plotly_chart(fig_box, use_container_width=True)
            
            # --- TAB 5: MAPAS SINCRONIZADOS (ANTES Y DESPUÉS) ---
            with tab_espacial:
                if not activar_tendencia:
                    st.info("💡 Para ver la comparativa de mapas (Antes y Después), necesitas habilitar la casilla 'Análisis de Tendencia' al inicio de la página.")
                else:
                    st.write(f"**Comparativa Espacial:** Disponibilidad en {anio_comparacion} (Izquierda) vs {anio_procesado} (Derecha).")
                    st.caption("Pinta de rojo 🔴 los acuíferos sobreexplotados (Déficit) y de azul 🔵 los que tienen superávit. ¡Mueve un mapa y el otro te seguirá!")
                    
                    with st.spinner("Cargando geometrías oficiales de CONAGUA..."):
                        gdf_maestro = cargar_datos_maestros()
                        
                        if gdf_maestro is not None and not df_riesgo.empty:
                            # Normalizamos claves para el cruce
                            gdf_maestro['CLV_ACUI'] = gdf_maestro['CLV_ACUI'].astype(str).str.zfill(4)
                            df_riesgo['Clave_Str'] = df_riesgo['Clave'].astype(str).str.zfill(4)
                            
                            gdf_mapa = gdf_maestro.merge(df_riesgo, left_on='CLV_ACUI', right_on='Clave_Str', how='inner')
                            
                            if not gdf_mapa.empty:
                                # SANITIZAR DATOS PARA FOLIUM
                                for col in gdf_mapa.columns:
                                    if col != 'geometry':
                                        gdf_mapa[col] = gdf_mapa[col].astype(str)

                                def semaforo_hidrico(valor):
                                    if pd.isna(valor) or valor == "N/D" or valor == "nan": return "#95a5a6"
                                    try:
                                        return "#e74c3c" if float(valor) < 0 else "#3498db"
                                    except: return "#95a5a6"

                                centroide = gdf_mapa.geometry.unary_union.centroid
                                
                                m_dual = plugins.DualMap(
                                    location=[centroide.y, centroide.x], 
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
                                                font-size: 15px; font-weight: bold; color: #691C32; border: 2px solid #691C32;">
                                        Disponibilidad {anio_comparacion}
                                    </div>
                                    <div style="position: absolute; top: 15px; left: 75%; transform: translateX(-50%); z-index: 9999; 
                                                background-color: white; padding: 6px 20px; border-radius: 20px; 
                                                box-shadow: 0 4px 6px rgba(0,0,0,0.3); font-family: 'Segoe UI', sans-serif; 
                                                font-size: 15px; font-weight: bold; color: #244062; border: 2px solid #244062;">
                                        Disponibilidad {anio_procesado}
                                    </div>
                                """
                                m_dual.get_root().html.add_child(folium.Element(titulos_flotantes))

                                # 6. MAPA IZQUIERDO (AÑO HISTÓRICO)
                                folium.GeoJson(
                                    gdf_mapa,
                                    name=f"Año {anio_comparacion}",
                                    style_function=lambda feature: {
                                        'fillColor': semaforo_hidrico(feature['properties'].get(f'DMA {anio_comparacion}')),
                                        'color': 'black', 'weight': 0.5, 'fillOpacity': 0.7
                                    },
                                    tooltip=folium.GeoJsonTooltip(
                                        fields=['NOM_ACUI', f'DMA {anio_comparacion}'], 
                                        aliases=['Acuífero:', f'DMA {anio_comparacion}:']
                                    )
                                ).add_to(m_dual.m1)

                                # 7. MAPA DERECHO (AÑO PROCESADO)
                                folium.GeoJson(
                                    gdf_mapa,
                                    name=f"Año {anio_procesado}",
                                    style_function=lambda feature: {
                                        'fillColor': semaforo_hidrico(feature['properties'].get('Disponibilidad (DMA)')),
                                        'color': 'black', 'weight': 0.5, 'fillOpacity': 0.7
                                    },
                                    tooltip=folium.GeoJsonTooltip(
                                        fields=['NOM_ACUI', 'Disponibilidad (DMA)'], 
                                        aliases=['Acuífero:', f'DMA {anio_procesado}:']
                                    )
                                ).add_to(m_dual.m2)

                                # Renderizar en Streamlit
                                st_folium(m_dual, use_container_width=True, height=600, returned_objects=[])
                            else:
                                st.warning("No se encontraron coincidencias geográficas para estos acuíferos.")

            # --- TAB 6: RESUMEN EJECUTIVO (MACRO-BALANCE Y PARETO) ---
            with tab_ejecutiva:
                st.write("Visión Estratégica: Balance Hídrico Global y Focalización de la Sobreexplotación.")
                
                col_exec1, col_exec2 = st.columns(2)
                
                with col_exec1:
                    # 1. MACRO-WATERFALL (Contabilidad del Agua)
                    r_tot = df_filtrado['Recarga (R)'].sum()
                    dnc_tot = df_filtrado['DNC'].sum()
                    veas_tot = df_filtrado['VEAS'].sum()
                    dma_tot = df_filtrado['Disponibilidad (DMA)'].sum()
                    
                    fig_macro = go.Figure(go.Waterfall(
                        orientation="v",
                        measure=["relative", "relative", "relative", "total"],
                        x=["1. Recarga (Ingresos)", "2. DNC (Naturaleza)", "3. VEAS (Concesiones)", "4. Saldo Neto (DMA)"],
                        textposition="outside",
                        text=[f"+{r_tot:,.1f}", f"-{dnc_tot:,.1f}", f"-{veas_tot:,.1f}", f"{dma_tot:,.1f}"],
                        y=[r_tot, -dnc_tot, -veas_tot, dma_tot],
                        connector={"line": {"color": "rgb(63, 63, 63)"}},
                        decreasing={"marker": {"color": "#e74c3c"}},
                        increasing={"marker": {"color": "#3498db"}},
                        totals={"marker": {"color": "#2ecc71" if dma_tot >= 0 else "#c0392b"}}
                    ))
                    fig_macro.update_layout(
                        title="Contabilidad Hídrica Global (Suma del Filtro Actual)",
                        height=500, margin=dict(t=75, b=50)
                    )
                    st.plotly_chart(fig_macro, use_container_width=True)
                    
                with col_exec2:
                    # 2. CURVA DE PARETO (Focalización del Déficit)
                    df_deficit = df_filtrado[df_filtrado['Disponibilidad (DMA)'] < 0].copy()
                    
                    if not df_deficit.empty:
                        df_deficit['Deficit_Abs'] = df_deficit['Disponibilidad (DMA)'].abs()
                        df_deficit = df_deficit.sort_values(by='Deficit_Abs', ascending=False)
                        df_deficit['Porcentaje_Acumulado'] = (df_deficit['Deficit_Abs'].cumsum() / df_deficit['Deficit_Abs'].sum()) * 100
                        
                        fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
                        
                        fig_pareto.add_trace(
                            go.Bar(x=df_deficit['Acuífero'], y=df_deficit['Deficit_Abs'], name="Volumen de Déficit (hm³)", marker_color="#e74c3c"),
                            secondary_y=False,
                        )
                        fig_pareto.add_trace(
                            go.Scatter(x=df_deficit['Acuífero'], y=df_deficit['Porcentaje_Acumulado'], name="% Acumulado", mode="lines+markers", line=dict(color="#244062", width=3)),
                            secondary_y=True,
                        )
                        
                        fig_pareto.update_layout(
                            title="Curva de Pareto: ¿Qué acuíferos concentran la sobreexplotación?",
                            height=500, margin=dict(t=75, b=50), showlegend=False
                        )
                        fig_pareto.update_yaxes(title_text="Déficit Absoluto (hm³)", secondary_y=False)
                        fig_pareto.update_yaxes(title_text="Porcentaje Acumulado (%)", range=[0, 105], secondary_y=True)
                        
                        st.plotly_chart(fig_pareto, use_container_width=True)
                    else:
                        st.success("✨ Excelente noticia: No hay déficit hídrico en la región seleccionada para generar la Curva de Pareto.")

        st.markdown("---")
        st.subheader(f"📑 Resumen de Balances ({anio_procesado})")
        
        def color_semaforo(val):
            if isinstance(val, (int, float)):
                return f"background-color: {'#ffcccc' if val < 0 else '#ccffcc'}"
            return ""
            
        col_c = ['Disponibilidad (DMA)']
        if activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
            col_c.append('Evolución DMA (hm³)')
            
        st.dataframe(df_filtrado.drop(columns=["Etiqueta_Busqueda", "ruta_fisica"], errors='ignore').style.map(color_semaforo, subset=col_c), width="stretch", hide_index=True)

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
                                df_maestro.drop(columns=['Etiqueta_Busqueda', 'ruta_fisica'], errors='ignore').to_excel(ruta_resumen, index=False, sheet_name="Resumen_Nacional")
                                z.write(ruta_resumen, arcname=f"00_Resumen_Nacional_{anio_procesado}.xlsx")
                                #os.remove(ruta_resumen)
                                
                                # 2. Generación Multi-hilo de Excels (Velocidad x8)
                                st.write("⚡ Calculando matrices en paralelo...")
                                avance = st.progress(0)
                                
                                total_archivos = len(datos_maestros)
                                procesados = 0
                                
                                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                                    futuros = [executor.submit(worker_generar_excel, f_m, anio_procesado, USER_TEMP_DIR) for f_m in datos_maestros]
                                    
                                    for fut in concurrent.futures.as_completed(futuros):
                                        resultado = fut.result()
                                        if resultado:
                                            ruta_ind, arc_name = resultado
                                            z.write(ruta_ind, arcname=arc_name)
                                            os.remove(ruta_ind)
                                            
                                        procesados += 1
                                        avance.progress(procesados / total_archivos)
                                        
                                        # Garbage collector para cuidar la RAM
                                        if procesados % 25 == 0:
                                            gc.collect()
                                        
                            st.session_state["ruta_zip_generado"] = zip_path
                            status.update(label="✅ Paquete ZIP generado a velocidad máxima", state="complete", expanded=False)
                            st.rerun()
                
                else:
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