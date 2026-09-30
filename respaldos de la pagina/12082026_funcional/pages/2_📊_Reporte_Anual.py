# -*- coding: utf-8 -*-
"""
Módulo de Cierre Anual y Consolidación de Balances (Clon Oficial, Carga Íntegra y Anti-Flasheo)
"""

import plotly.graph_objects as go
import concurrent.futures
import streamlit as st
import pandas as pd
import datetime
import zipfile
import random
import time
import json
import io
import os
import shutil
import gc
import requests
import base64
import numpy as np
import plotly.express as px
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# =======================================================
# --- CSS OFICIAL Y CABECERA (CONAGUA NATIVO) ---
# =======================================================

# =======================================================
# --- CSS OFICIAL Y BANNER COMPACTO (CONAGUA) ---
# =======================================================
css_oficial = """
<style>
    /* 1. Pintar todos los títulos de guinda */
    h1, h2, h3, h4, h5, h6 { color: #691C32 !important; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    
    /* 2. Compactar espacio y FORZAR ANCHO FLUIDO (Corrección de expansión) */
    .block-container, 
    [data-testid="stMainBlockContainer"] { 
        padding-top: 2rem !important; 
        padding-bottom: 2rem !important; 
        max-width: 98vw !important;
        width: 100% !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }
    
    /* Asegurar que las pestañas se estiren al máximo */
    div[data-testid="stTabs"] {
        width: 100% !important;
    }
    
    /* 3. Reducir márgenes entre títulos y textos */
    div[data-testid="stMarkdownContainer"] p { margin-bottom: 0.5rem !important; }
    div[data-testid="stHeader"] { display: none !important; } /* Ocultar franja superior inútil */
    
    /* 4. Estilo institucional para tablas */
    .stDataFrame th { background-color: #bdd7ee !important; color: #244062 !important; font-weight: bold !important; }
    .stAppDeployButton {display:none;}
    
    /* 5. Estilos de Pestañas (Tabs) Preservados y Compactos */
    .stTabs [data-baseweb="tab-list"] { gap: 6px; padding-bottom: 2px; }
    .stTabs [data-baseweb="tab"] { background-color: #f1f3f6; border-radius: 6px 6px 0px 0px; padding: 6px 16px; border: 1px solid #dcdde1; border-bottom: none; }
    .stTabs [aria-selected="true"] { background-color: #ffffff; border-top: 4px solid #9F2241; }
    .stTabs [data-baseweb="tab"] p { font-weight: bold; font-size: 14px; color: #6F7271; margin: 0; }
    .stTabs [aria-selected="true"] p { color: #691C32 !important; }
</style>

<!-- BANNER PRINCIPAL COMPACTO -->
<div style="background-color: #ffffff; padding: 10px 15px; border-bottom: 3px solid #DDC9A3; text-align: center; margin-bottom: 10px;">
    <h2 style="color: #691C32; margin: 0; font-size: 28px; font-weight: bold;">
        💧 Sistema de Consulta de Información para Documentos de Respaldo
    </h2>
</div>
"""
st.markdown(css_oficial, unsafe_allow_html=True)

# Títulos de página compactos (Usamos subheader en lugar de header para ahorrar espacio)
st.subheader("📊 Reporte Anual de Balances de Aguas Subterráneas")
st.caption("Generación de resumen de resultados de Balances de Aguas Subterráneas y empaquetado de respaldos.")


# ==========================================
# 0. PREPARACIÓN DE CARPETA TEMPORAL (CACHE)
# ==========================================
CARPETA_TEMPORAL = "temp_balances_oficial"
os.makedirs(CARPETA_TEMPORAL, exist_ok=True)
INDEX_CACHE = os.path.join(CARPETA_TEMPORAL, "smart_cache_oficial.json") #


# ==========================================
# 1. AUTENTICACIÓN Y BÚSQUEDA EN DRIVE
# ==========================================
@st.cache_resource(show_spinner=False)
def obtener_credenciales():
    info_credenciales = dict(st.secrets["textkey"])
    llave = info_credenciales.get("private_key", "").replace("\\n", "\n").replace("\r", "").strip()
    info_credenciales["private_key"] = llave.replace("-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n").replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----").replace("\n\n\n", "\n").replace("\n\n", "\n")
    return Credentials.from_service_account_info(info_credenciales, scopes=["https://www.googleapis.com/auth/drive"])

def buscar_metadatos_drive(anio):
    query = f"name contains '_B{str(anio)[-2:]}.json' and trashed=false"
    credenciales = obtener_credenciales()
    servicio = build("drive", "v3", credentials=credenciales)
    archivos_encontrados = []
    page_token = None
    
    while True:
        try:
            resultados = servicio.files().list(
                q=query, 
                pageSize=1000, 
                fields="nextPageToken, files(id, name, modifiedTime)", 
                includeItemsFromAllDrives=True, 
                supportsAllDrives=True, 
                pageToken=page_token
            ).execute()
            archivos_encontrados.extend(resultados.get('files', []))
            page_token = resultados.get('nextPageToken', None)
            if not page_token:
                break
        except Exception:
            time.sleep(1)
            
    return archivos_encontrados

def descargar_json_crudo_rapido(file_id, token):
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                return json.loads(res.content.decode('utf-8-sig').strip())
        except Exception:
            time.sleep(1)
    return None

def worker_extraccion(archivo, token):
    id_arch = archivo['id']
    nom_arch = archivo['name']
    
    try:
        data = descargar_json_crudo_rapido(id_arch, token)
        if not data:
            return {"estado": "error", "id": id_arch, "name": nom_arch}
        
        ruta_json_fisico = os.path.join(CARPETA_TEMPORAL, f"{id_arch}.json")
        with open(ruta_json_fisico, 'w', encoding='utf-8') as f:
            json.dump(data, f)
            
        del data
        return {"estado": "exito", "id": id_arch, "modifiedTime": archivo.get('modifiedTime')}
        
    except Exception as e:
        return {"estado": "error", "id": id_arch, "name": nom_arch, "error": str(e)}


from pathlib import Path

# ==========================================
# 📌 GESTOR DE RUTAS Y LECTURA DE CATÁLOGOS
# ==========================================
DIRECTORIO_RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = DIRECTORIO_RAIZ / "data"

@st.cache_data(show_spinner=False)
def cargar_catalogo(nombre_archivo: str) -> pd.DataFrame:
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        return pd.DataFrame()
    df = pd.read_csv(ruta, encoding="utf-8")
    if 'CLAVE_SIGM' in df.columns:
        df["CLAVE_SIGM"] = df["CLAVE_SIGM"].astype(str).str.zfill(4)
    return df

@st.cache_data(show_spinner=False)
def cargar_historico_excel(nombre_archivo: str, anio: int) -> dict:
    ruta = CARPETA_DATOS / nombre_archivo
    if not ruta.exists():
        return {}
        
    df = pd.read_excel(ruta)
    df.columns = df.columns.str.upper().str.strip() 
    
    col_clave = 'CLAVE' if 'CLAVE' in df.columns else ('CLAVE_SIGM' if 'CLAVE_SIGM' in df.columns else None)
    if not col_clave:
        return {}
        
    col_dma = f"DMA_{anio}"
    col_veas = f"VEAS_{anio}"
    
    if col_dma not in df.columns or col_veas not in df.columns:
        return {"error_columnas": True, "dma": col_dma, "veas": col_veas}
        
    df[col_clave] = df[col_clave].astype(str).str.zfill(4)
    dict_hist = {}
    
    for _, row in df.iterrows():
        val_dma = float(row[col_dma]) if pd.notna(row[col_dma]) else "N/D"
        val_veas = float(row[col_veas]) if pd.notna(row[col_veas]) else "N/D"
        dict_hist[row[col_clave]] = {'DMA': val_dma, 'VEAS': val_veas}
        
    return dict_hist


# =========================================================================
# 2. MOTOR DE EXCEL (IDÉNTICO A CALCULADORA V33)
# =========================================================================
def generar_excel_matriz(df_resumen, df_eh, df_usos, df_sh, df_etr, df_dvs, df_eas, dvs_anualizado, fuente_b, anio_b, a_base, a_tope, rda, ruta_guardado):
    try:
        writer = pd.ExcelWriter(ruta_guardado, engine='xlsxwriter', engine_kwargs={'options': {'nan_inf_to_errors': True}})
    except TypeError:
        writer = pd.ExcelWriter(ruta_guardado, engine='xlsxwriter', options={'nan_inf_to_errors': True})
        
    with writer:
        workbook = writer.book
        f_cab = workbook.add_format({'bg_color': '#BED7EE', 'font_color': '#244062', 'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        f_base = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 11, 'align': 'center'})
        f_bor = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 11, 'border': 1, 'align': 'center'})
        f_tot_tex = workbook.add_format({'bg_color': '#BED7EE', 'font_color': '#244062', 'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'right', 'valign': 'vcenter'})
        f_tot_num = workbook.add_format({'bg_color': '#BED7EE', 'font_color': '#244062', 'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'center', 'num_format': '#,##0.000'})
        f_pct = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 11, 'border': 1, 'align': 'center', 'num_format': '0.00%'})
        f_tot_pct = workbook.add_format({'bg_color': '#BED7EE', 'font_color': '#244062', 'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'border': 1, 'align': 'center', 'num_format': '0.00%'})
        f_met = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 11, 'bold': True, 'font_color': '#1f497d', 'align': 'left'})

        df_resumen.to_excel(writer, sheet_name='Resumen_Balance', index=False)
        ws_res = writer.sheets['Resumen_Balance']
        ws_res.set_column('A:A', 40, f_base); ws_res.set_column('B:B', 20, f_base)
        for c, v in enumerate(df_resumen.columns.values): ws_res.write(0, c, v, f_cab)
        for r in range(1, len(df_resumen) + 1):
            for c in range(len(df_resumen.columns)): ws_res.write(r, c, df_resumen.iloc[r - 1, c], f_bor)

        def formatear_hoja(df, sheet_name, is_dvs=False, is_usos=False):
            if df.empty: return
            
            # Limpieza para que Pandas no pase nulos rotos
            df = df.replace([float('inf'), float('-inf')], "").fillna("")
            inicio_fila_tabla = 2 if (is_dvs or is_usos) else 0
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=inicio_fila_tabla)
            ws = writer.sheets[sheet_name]
            num_cols, num_rows = len(df.columns), len(df)
            
            if is_usos:
                ws.set_column(0, 0, 35, f_base); ws.set_column(1, 1, 25, f_base); ws.set_column(2, 2, 20, f_base) 
                ws.write(0, 0, f"Origen de datos: {fuente_b}", f_met); ws.write(0, 1, f"Año de info: {anio_b}", f_met)
            elif is_dvs:
                ws.set_column(0, num_cols - 1, 22, f_base)
                ws.write(0, 0, f"Año Base: {a_base}", f_met); ws.write(0, 1, f"Año Tope: {a_tope}", f_met); ws.write(0, 2, f"RDA: {rda} años", f_met)
            else: ws.set_column(0, num_cols - 1, 22, f_base)
            
            for col_num, value in enumerate(df.columns.values): ws.write(inicio_fila_tabla, col_num, value, f_cab)
            for row in range(1, num_rows + 1):
                fila_excel = inicio_fila_tabla + row
                for col in range(num_cols):
                    valor = df.iloc[row - 1, col]
                    if is_usos and col == (num_cols - 1): ws.write(fila_excel, col, valor, f_pct)
                    else: ws.write(fila_excel, col, valor, f_bor)
                
            fila_total = inicio_fila_tabla + num_rows + 1 
            if is_usos:
                ws.write(fila_total, 0, "Total", f_tot_tex)
                ws.write(fila_total, 1, pd.to_numeric(df['Volumen [hm³/año]'], errors='coerce').sum(), f_tot_num)
                ws.write(fila_total, 2, 1.0, f_tot_pct) 
            elif not is_dvs:
                ws.merge_range(fila_total, 0, fila_total, num_cols - 2, "Total", f_tot_tex)
                ws.write(fila_total, num_cols - 1, pd.to_numeric(df.iloc[:, -1], errors='coerce').sum(), f_tot_num)
            else:
                if 'Límite 2 [m]' in df.columns:
                    idx_l2, idx_area = df.columns.get_loc('Límite 2 [m]'), df.columns.get_loc('Área [km²]')
                    idx_evm, idx_vol = df.columns.get_loc('Evolución Media [m]'), df.columns.get_loc('Volumen Parcial [hm³]')
                    ws.merge_range(fila_total, 0, fila_total, idx_l2, "Total", f_tot_tex)
                    ws.write(fila_total, idx_area, pd.to_numeric(df['Área [km²]'], errors='coerce').sum(), f_tot_num)
                    ws.merge_range(fila_total, idx_area + 1, fila_total, idx_evm, "Total", f_tot_tex)
                    ws.write(fila_total, idx_vol, pd.to_numeric(df.iloc[:, -1], errors='coerce').sum(), f_tot_num)
                    fila_prom = fila_total + 1
                    ws.merge_range(fila_prom, 0, fila_prom, idx_vol - 1, "Promedio anual", f_tot_tex)
                    ws.write(fila_prom, idx_vol, dvs_anualizado, f_tot_num)

        formatear_hoja(df_eh, 'Entradas_Eh')
        formatear_hoja(df_eas, 'Entradas_Salobres_Eas')
        formatear_hoja(df_usos, 'Extraccion_Bombeo', is_usos=True)
        formatear_hoja(df_sh, 'Salidas_Sh')
        formatear_hoja(df_etr, 'Evapo_ETR')
        formatear_hoja(df_dvs, 'Almacenamiento_DVS', is_dvs=True)

# ==========================================
# 3. INTERFAZ: ESCANEO SMART SYNC 
# ==========================================
col_y1, col_y2 = st.columns(2)
anio_reporte = col_y1.number_input("Selecciona el Año de Evaluación a procesar:", min_value=2020, max_value=2100, value=datetime.datetime.now().year, step=1)
st.markdown("<br>", unsafe_allow_html=True)
activar_tendencia = st.checkbox("📈 Habilitar Análisis de Tendencia (Comparativa vs Publicación Anterior)")

anio_comparacion = None
if activar_tendencia:
    anio_comparacion = col_y2.number_input("Año de Publicación Anterior:", min_value=2015, max_value=2100, value=2023, step=1)

if st.button("🔍 Escanear Drive y Generar Reporte", type="primary"):
    
    if activar_tendencia and anio_comparacion >= anio_reporte:
        st.error("⚠️ Error de lógica temporal: El año histórico no puede ser mayor o igual al evaluado.")
        st.stop()
        
    dict_historico = cargar_historico_excel("DMA_VEAS.xlsx", anio_comparacion) if activar_tendencia else {}
    if dict_historico.get("error_columnas"):
        st.error(f"❌ Error: Columnas `{dict_historico['dma']}` o `{dict_historico['veas']}` no encontradas en DMA_VEAS.xlsx.")
        st.stop()

    archivos_drive = buscar_metadatos_drive(anio_reporte)
    if not archivos_drive:
        st.warning(f"No se encontraron archivos en Drive para el año {anio_reporte}.")
        st.stop()

    texto_progreso = st.empty()
    barra_progreso = st.progress(0)
    
    cache_index = {}
    if os.path.exists(INDEX_CACHE):
        with open(INDEX_CACHE, 'r') as f:
            cache_index = json.load(f)

    archivos_a_descargar = []
    for arch in archivos_drive:
        aid = arch['id']
        amod = arch.get('modifiedTime', '')
        ruta_archivo = os.path.join(CARPETA_TEMPORAL, f"{aid}.json")
        
        if aid not in cache_index or cache_index[aid] != amod or not os.path.exists(ruta_archivo):
            archivos_a_descargar.append(arch)

    omitidos_errores = []
    if archivos_a_descargar:
        texto_progreso.info(f"🧠 Smart Sync: Descargando {len(archivos_a_descargar)} archivos nuevos o modificados...")
        cred = obtener_credenciales()
        cred.refresh(Request())
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futuros = {executor.submit(worker_extraccion, arch, cred.token): arch for arch in archivos_a_descargar}
            for i, fut in enumerate(concurrent.futures.as_completed(futuros)):
                res = fut.result()
                if res['estado'] == 'exito':
                    cache_index[res['id']] = res['modifiedTime']
                else:
                    omitidos_errores.append(f"{res.get('name', 'Desconocido')} - Error interno")
                barra_progreso.progress((i + 1) / len(archivos_a_descargar))
                
        with open(INDEX_CACHE, 'w') as f:
            json.dump(cache_index, f)

    texto_progreso.success("⚡ Se localizaron balances en Drive. Procesando datos...")
    datos_maestros = []
    ids_procesados = set()
    omitidos_duplicados = []

    for arch in archivos_drive:
        fid = arch['id']
        fnom = arch['name']
        clave = fnom.split('_')[0]
        
        if clave in ids_procesados:
            omitidos_duplicados.append(fnom)
            continue
            
        ruta = os.path.join(CARPETA_TEMPORAL, f"{fid}.json")
        if os.path.exists(ruta):
            with open(ruta, 'r', encoding='utf-8') as f:
                dat = json.load(f)
            
            res = dat.get("resultados", {})
            dma = round(res.get('Disponibilidad_Oficial', 0.0), 6)
            veas = round(res.get('VEAS', 0.0), 6)
            
            fila = {
                "Clave": clave,
                "Acuífero": " ".join(fnom.split('_')[1:-1]),
                "Recarga (R)": round(res.get('Recarga_Total', 0.0), 1),
                "Bombeo (B)": round(res.get('B_total', 0.0), 1),
                "DNC": round(res.get('DNC_total', 0.0), 1),
                "VEAS": veas,
                "ΔV(S)": round(res.get('DVS', 0.0), 1),
                "Disponibilidad (DMA)": dma,
                "ruta_fisica": ruta 
            }
            
            if activar_tendencia:
                hist = dict_historico.get(clave, {})
                dma_hist = hist.get('DMA', "N/D")
                veas_hist = hist.get('VEAS', "N/D")
                
                fila[f"DMA {anio_comparacion}"] = dma_hist
                fila[f"Evolución DMA (hm³)"] = round(dma - dma_hist, 6) if dma_hist != "N/D" else "N/D"
                fila[f"Crecimiento VEAS (hm³)"] = round(veas - veas_hist, 6) if veas_hist != "N/D" else "N/D"
                
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
    
    if "paquete_zip_bytes" in st.session_state:
        del st.session_state["paquete_zip_bytes"]
        
    time.sleep(1)
    barra_progreso.empty()
    texto_progreso.empty()


# ==========================================
# 4. DASHBOARD Y LAZY ZIPPING
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
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No hay datos históricos para graficar.")
        else:
            cg1, cg2 = st.columns(2)
            with cg1:
                if activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
                    df_graf = df_filtrado[df_filtrado['Evolución DMA (hm³)'] != "N/D"].copy()
                    df_graf['Evolución DMA (hm³)'] = pd.to_numeric(df_graf['Evolución DMA (hm³)'] )
                    df_def = df_graf[df_graf['Evolución DMA (hm³)'] < 0].sort_values(by='Evolución DMA (hm³)', ascending=True).head(10)
                    tit, eje = "Top 10 Pérdidas (hm³)", 'Evolución DMA (hm³)'
                else:
                    df_def = df_filtrado[df_filtrado["Disponibilidad (DMA)"] < 0].sort_values(by="Disponibilidad (DMA)", ascending=True).head(10)
                    tit, eje = "Top 10 Déficit (hm³)", "Disponibilidad (DMA)"
                    
                if not df_def.empty:
                    df_def["E"] = df_def["Clave"] + " " + df_def["Acuífero"]
                    fig_d = px.bar(df_def, y="E", x=eje, orientation='h', title=tit, color_discrete_sequence=["#ff6666"], text=eje)
                    fig_d.update_traces(texttemplate='%{text:.2f}', textposition='outside')
                    fig_d.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis=dict(range=[df_def[eje].min()*1.2, 0]), height=400)
                    st.plotly_chart(fig_d, use_container_width=True)
                else:
                    st.info("Sin datos para gráfica de barras.")
                    
            with cg2:
                if activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
                    df_graf = df_filtrado[df_filtrado['Evolución DMA (hm³)'] != "N/D"].copy()
                    df_graf['Evolución DMA (hm³)'] = pd.to_numeric(df_graf['Evolución DMA (hm³)'] )
                    p = len(df_graf[df_graf['Evolución DMA (hm³)'] < 0])
                    df_p = pd.DataFrame({"Tendencia": ["Recuperación", "Pérdida"], "C": [len(df_graf)-p, p]})
                    col, mapc = "Tendencia", {"Recuperación":"#99ccff", "Pérdida":"#ff9996"}
                else:
                    df_p = pd.DataFrame({"E": ["Con Disponibilidad", "Con Déficit"], "C": [total_filtrado-acuiferos_deficit, acuiferos_deficit]})
                    col, mapc = "E", {"Con Disponibilidad":"#99ccff", "Con Déficit":"#ff9996"}
                    
                if total_filtrado > 0:
                    fig_p = px.pie(df_p, values="C", names=col, title="Distribución", color=col, color_discrete_map=mapc, hole=0.4)
                    fig_p.update_traces(textinfo='percent+label')
                    st.plotly_chart(fig_p, use_container_width=True)

        st.markdown("---")
        st.subheader(f"📑 Resumen de Balances ({anio_procesado})")
        
        def color_semaforo(val):
            if isinstance(val, (int, float)):
                return f"background-color: {'#ffcccc' if val < 0 else '#ccffcc'}"
            return ""
            
        col_c = ['Disponibilidad (DMA)']
        if activar_tendencia and 'Evolución DMA (hm³)' in df_filtrado.columns:
            col_c.append('Evolución DMA (hm³)')
            
        st.dataframe(df_filtrado.drop(columns=["Etiqueta_Busqueda", "ruta_fisica"], errors='ignore').style.map(color_semaforo, subset=col_c), use_container_width=True, hide_index=True)

        # -----------------------------------------------------------
        # 🚀 DESCARGAS ENTERPRISE: ZIP EN MEMORIA Y MATEMÁTICA SEGURA
        # -----------------------------------------------------------
        @st.fragment
        def renderizar_botones_descarga():
            cd1, cd2, _ = st.columns([1.5, 1.5, 1])
            
            with cd1:
                st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
                
                # Usamos st.session_state para almacenar el ZIP en RAM y evitar colisiones entre usuarios
                if "paquete_zip_bytes" not in st.session_state:
                    if st.button("📦 1. Preparar Descarga de Balances (ZIP)", type="primary", use_container_width=True):
                        
                        # Usamos st.status para una UX fluida sin parpadeos
                        with st.status("📦 Empaquetando Documentación Oficial...", expanded=True) as status:
                            st.write("Generando matriz del Resumen Nacional...")
                            
                            # Creamos el archivo ZIP flotando en la memoria RAM
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
                                
                                # 1. Resumen Maestro Nacional
                                ex_buf = io.BytesIO()
                                df_maestro.drop(columns=['Etiqueta_Busqueda', 'ruta_fisica'], errors='ignore').to_excel(ex_buf, index=False, sheet_name="Resumen_Nacional")
                                z.writestr(f"00_Resumen_Nacional_{anio_procesado}.xlsx", ex_buf.getvalue())
                                
                                # 2. Motor Matemático Vectorizado (Anti-NaN)
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

                                cols_flujo = ['Celda', 'Longitud B [m]', 'Ancho a [m]', 'h2-h1 [m]', 'Transmisividad T [m²/s]', 'Gradiente i', 'Caudal Q [m³/s]', 'Volumen [hm³/año]']

                                st.write("Calculando matrices individuales y generando Excels...")
                                for idx, f_maestra in enumerate(datos_maestros):
                                    ruta_json = f_maestra.get("ruta_fisica", "")
                                    if os.path.exists(ruta_json):
                                        with open(ruta_json, 'r', encoding='utf-8') as json_f:
                                            dat = json.load(json_f)
                                            
                                        res = dat.get("resultados", {})
                                        conf = dat.get("configuracion", {})
                                        tabs = dat.get("tablas", {})
                                        
                                        df_eh = calc_flujos_vectorizado(tabs.get('eh', []), cols_flujo)
                                        df_eas = calc_flujos_vectorizado(tabs.get('eas', []), cols_flujo)
                                        df_sh = calc_flujos_vectorizado(tabs.get('sh', []), cols_flujo)
                                        eh_acumulado = df_eh['Volumen [hm³/año]'].sum() if not df_eh.empty else 0.0
                                        eas_acumulado = df_eas['Volumen [hm³/año]'].sum() if not df_eas.empty else 0.0
                                        sh_acumulado = df_sh['Volumen [hm³/año]'].sum() if not df_sh.empty else 0.0

                                        # USOS
                                        df_usos = pd.DataFrame(tabs.get('usos', []))
                                        if not df_usos.empty:
                                            if 'Volumen [hm³/año]' not in df_usos.columns: df_usos['Volumen [hm³/año]'] = 0.0
                                            df_usos['Volumen [hm³/año]'] = pd.to_numeric(df_usos['Volumen [hm³/año]'], errors='coerce').fillna(0.0)
                                            bombeo_calc = df_usos['Volumen [hm³/año]'].sum()
                                            df_usos['Porcentaje (%)'] = (df_usos['Volumen [hm³/año]'] / bombeo_calc) if bombeo_calc > 0 else 0.0
                                        else: 
                                            df_usos = pd.DataFrame(columns=['Tipo de Uso', 'Volumen [hm³/año]', 'Porcentaje (%)'])
                                            bombeo_calc = float(res.get("B_total", 0.0))

                                        # ETR (Protección Blanca/NaN)
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

                                        # DVS (Protección Blanca/NaN)
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

                                        # Variables Finales y Resumen
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
                                        
                                        # Escribir el Excel individual directo al ZIP en memoria (Sin tocar el disco)
                                        excel_ind_buf = io.BytesIO()
                                        generar_excel_matriz(df_ind_resumen, df_eh, df_usos, df_sh, df_etr, df_dvs, df_eas, dvs_anualizado, fuente_b, anio_b, a_base, a_tope, rda, excel_ind_buf)
                                        z.writestr(f"Balances_Individuales/{nom_x}", excel_ind_buf.getvalue())
                                        
                                        # Limpieza de memoria para no saturar el servidor
                                        if idx % 10 == 0: gc.collect()
                                        
                            st.session_state["paquete_zip_bytes"] = zip_buffer.getvalue()
                            status.update(label="✅ Paquete ZIP generado exitosamente", state="complete", expanded=False)
                            st.rerun()
                
                else:
                    st.download_button(
                        label="📥 2. Descargar Balances (ZIP) Ahora", 
                        data=st.session_state["paquete_zip_bytes"], 
                        file_name=f"Paquete_Balances_Nacionales_{anio_procesado}.zip", 
                        mime="application/zip", 
                        type="primary", 
                        use_container_width=True
                    )
                        
            with cd2:
                st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
                if not df_cat.empty and total_exitosos < total_nacional:
                    claves_listas = df_maestro["Clave"].tolist()
                    df_faltantes = df_cat[~df_cat["CLAVE_SIGM"].isin(claves_listas)].copy()
                    csv_f = df_faltantes.to_csv(index=False).encode('utf-8-sig')
                    
                    st.download_button("🚨 Descargar Faltantes (CSV)", data=csv_f, file_name=f"Acuiferos_Faltantes_{anio_procesado}.csv", mime="text/csv", type="secondary", use_container_width=True)

        renderizar_botones_descarga()