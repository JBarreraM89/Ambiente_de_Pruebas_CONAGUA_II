# -*- coding: utf-8 -*-
"""
Módulo de Cierre Anual y Consolidación de Balances (Optimizado a Disco)
"""

import plotly.graph_objects as go
import plotly.express as px
import concurrent.futures
import streamlit as st
import pandas as pd
import datetime
import zipfile
import time
import json
import os
import gc
import numpy as np
from google.auth.transport.requests import Request

# --- IMPORTACIONES DEL CORE (FASE 1 y 2) ---
from utils.styles import inyectar_css_oficial, banner_institucional, inyectar_css_navegacion
from core.drive_api import buscar_metadatos_drive, descargar_json_crudo_rapido, obtener_servicio_drive
from core.generador_excel import generar_excel_matriz
from core.data_loader import cargar_catalogo, cargar_historico_excel

# =======================================================
# --- CSS OFICIAL Y BANNER COMPACTO ---
# =======================================================
inyectar_css_oficial()
banner_institucional()

st.subheader("📊 Reporte Anual de Balances de Aguas Subterráneas")
st.caption("Generación de resumen de resultados de Balances de Aguas Subterráneas y empaquetado de respaldos.")

# ==========================================
# 0. PREPARACIÓN DE CARPETA TEMPORAL (CACHE A DISCO)
# ==========================================
CARPETA_TEMPORAL = "temp_balances_oficial"
os.makedirs(CARPETA_TEMPORAL, exist_ok=True)
INDEX_CACHE = os.path.join(CARPETA_TEMPORAL, "smart_cache_oficial.json")

# ==========================================
# 1. FUNCIONES AUXILIARES DE DRIVE
# ==========================================
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

# ==========================================
# 2. INTERFAZ: ESCANEO SMART SYNC 
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
        
        # Utilizamos las credenciales del Core
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
    
    if "ruta_zip_generado" in st.session_state:
        del st.session_state["ruta_zip_generado"]
        
    time.sleep(1)
    barra_progreso.empty()
    texto_progreso.empty()

# ==========================================
# 3. DASHBOARD Y LAZY ZIPPING (A DISCO)
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
        # 🚀 DESCARGAS ENTERPRISE: ESCRITURA EN DISCO (Anti-OOM)
        # -----------------------------------------------------------
        @st.fragment
        def renderizar_botones_descarga():
            cd1, cd2, _ = st.columns([1.5, 1.5, 1])
            
            with cd1:
                st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
                
                if "ruta_zip_generado" not in st.session_state or not os.path.exists(st.session_state["ruta_zip_generado"]):
                    if st.button("📦 1. Preparar Descarga de Balances (ZIP)", type="primary", use_container_width=True):
                        
                        with st.status("📦 Empaquetando Documentación Oficial en Disco...", expanded=True) as status:
                            st.write("Generando matriz del Resumen Nacional...")
                            
                            # Escribimos el ZIP directo a disco
                            zip_path = os.path.join(CARPETA_TEMPORAL, f"Paquete_Balances_Nacionales_{anio_procesado}.zip")
                            
                            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                                
                                # 1. Resumen Maestro Nacional a disco temporal
                                ruta_resumen = os.path.join(CARPETA_TEMPORAL, f"00_Resumen_Nacional_{anio_procesado}.xlsx")
                                df_maestro.drop(columns=['Etiqueta_Busqueda', 'ruta_fisica'], errors='ignore').to_excel(ruta_resumen, index=False, sheet_name="Resumen_Nacional")
                                z.write(ruta_resumen, arcname=f"00_Resumen_Nacional_{anio_procesado}.xlsx")
                                os.remove(ruta_resumen)
                                
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

                                        df_usos = pd.DataFrame(tabs.get('usos', []))
                                        if not df_usos.empty:
                                            if 'Volumen [hm³/año]' not in df_usos.columns: df_usos['Volumen [hm³/año]'] = 0.0
                                            df_usos['Volumen [hm³/año]'] = pd.to_numeric(df_usos['Volumen [hm³/año]'], errors='coerce').fillna(0.0)
                                            bombeo_calc = df_usos['Volumen [hm³/año]'].sum()
                                            df_usos['Porcentaje (%)'] = (df_usos['Volumen [hm³/año]'] / bombeo_calc) if bombeo_calc > 0 else 0.0
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
                                        
                                        # Escribimos el Excel al disco, lo metemos al ZIP y luego lo borramos de RAM y Disco
                                        ruta_ind = os.path.join(CARPETA_TEMPORAL, nom_x)
                                        generar_excel_matriz(df_ind_resumen, df_eh, df_usos, df_sh, df_etr, df_dvs, df_eas, dvs_anualizado, fuente_b, anio_b, a_base, a_tope, rda, destino_salida=ruta_ind)
                                        
                                        z.write(ruta_ind, arcname=f"Balances_Individuales/{nom_x}")
                                        os.remove(ruta_ind)
                                        
                                        if idx % 10 == 0: gc.collect()
                                        
                            st.session_state["ruta_zip_generado"] = zip_path
                            status.update(label="✅ Paquete ZIP generado exitosamente en Disco", state="complete", expanded=False)
                            st.rerun()
                
                else:
                    with open(st.session_state["ruta_zip_generado"], "rb") as f:
                        st.download_button(
                            label="📥 2. Descargar Balances (ZIP) Ahora", 
                            data=f, 
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