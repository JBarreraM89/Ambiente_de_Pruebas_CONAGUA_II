# -*- coding: utf-8 -*-
"""
Calculadora de Balance de Aguas Subterráneas
Versión final con auto-cálculo al cargar balances desde Drive.
"""

import plotly.graph_objects as go
import streamlit as st
import pandas as pd
import numpy as np
import datetime
import math

# --- IMPORTACIONES DEL CORE (FASE 1 y 2) ---
from utils.styles import inyectar_css_oficial, banner_institucional, inyectar_css_navegacion
from core.drive_api import listar_balances_json, descargar_balance_json_por_id, guardar_balance_drive
from core.generador_excel import generar_excel_matriz
from core.data_loader import cargar_catalogo, CARPETA_DATOS

# =======================================================
# --- CSS OFICIAL Y BANNER COMPACTO ---
# =======================================================
inyectar_css_oficial()
banner_institucional()

st.subheader("🧮 Calculadora de Balance de Aguas Subterráneas")
st.caption("Evaluación y Disponibilidad Oficial (NOM-011-CONAGUA-2015).")

# =======================================================
# Función para obtener VEAS desde catálogo
# =======================================================
@st.cache_data(show_spinner="Buscando VEAS oficial en base de datos...")
def obtener_veas_excel(clave_ac):
    ruta_completa = CARPETA_DATOS / "VEAS_SEP25.xlsx"
    if not ruta_completa.exists():
        return None
    try:
        df = pd.read_excel(ruta_completa)
        df.columns = df.columns.str.strip()
        df['CLVE_ACUIF'] = df['CLVE_ACUIF'].astype(str).str.zfill(4)
        clave_str = str(clave_ac).zfill(4)
        fila = df[df['CLVE_ACUIF'] == clave_str]
        if not fila.empty:
            return float(fila.iloc[0]['VEAS_SEP_2025'])
        return None
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def listar_balances_json_cache(clave):
    """Versión cacheada de listar_balances_json con TTL de 5 minutos."""
    return listar_balances_json(clave)

# ==========================================
# 1️⃣ INTERFAZ: GESTIÓN DE ENTORNO SINCRO-GEOVISOR
# ==========================================
# Obtenemos los valores de sesión (iniciarán en None)
clave_actual = st.session_state.get("clave_bal")
nombre_actual = st.session_state.get("nombre_bal")
area_actual = st.session_state.get("area_total_bal")

# Hacemos que el buscador se abra automáticamente si no hay nada seleccionado
abrir_buscador = True if not clave_actual else False

with st.expander("📍 Búsqueda Alternativa en Catálogo", expanded=abrir_buscador):
    df_cat = cargar_catalogo("Acuiferos_2026.csv")
    if not df_cat.empty:
        try:
            c_est, c_clav = st.columns(2)
            estados = sorted(df_cat["ESTADO"].dropna().unique().tolist())
            
            estado_sel = c_est.selectbox("1. Selecciona el Estado", estados, key="calc_sel_edo", index=None, placeholder="Elige un estado...")

            opciones_acuiferos = []
            if estado_sel:
                df_est = df_cat[df_cat["ESTADO"] == estado_sel].copy()
                df_est["ETIQUETA_BUSQUEDA"] = df_est["CLAVE_SIGM"].astype(str) + " - " + df_est["ACUÍFERO"].astype(str)
                opciones_acuiferos = sorted(df_est["ETIQUETA_BUSQUEDA"].unique().tolist())

            seleccion = c_clav.selectbox("2. Escribe o selecciona (Clave o Nombre)", opciones_acuiferos, key="calc_sel_clv", index=None, placeholder="Elige un acuífero...")

            if seleccion:
                clave_sel = seleccion.split(" - ")[0]
                
                # ESTA ES LA CONDICIÓN CLAVE QUE EVITA EL BUCLE INFINITO
                if clave_sel != st.session_state.get("clave_bal"):
                    
                    datos_acu = df_est[df_est["CLAVE_SIGM"] == clave_sel].iloc[0]

                    # Actualizamos la memoria maestra global
                    st.session_state["clave_bal"] = str(datos_acu["CLAVE_SIGM"])
                    st.session_state["nombre_bal"] = str(datos_acu["ACUÍFERO"])
                    st.session_state["area_total_bal"] = round(float(datos_acu["AREA_KM2"]), 1)
                    
                    # Ahora el rerun solo se ejecuta UNA VEZ cuando hay un cambio real
                    st.rerun()
                
        except Exception as e:
            st.error(f"Error en catálogo: {e}")

# BLOQUEO DE PÁGINA: Si no hay clave, mostramos aviso y detenemos la ejecución aquí
if not clave_actual:
    st.info("👆 **Bienvenido.** Por favor, selecciona un Estado y un Acuífero en el buscador de arriba para comenzar a capturar o visualizar el balance.")
    st.stop()

# Si pasamos el stop, aseguramos que el área sea un número para evitar el TypeError
area_actual = float(area_actual)

st.markdown("<h3 style='text-align: center;'>🌊 Datos del Acuífero Evaluado</h3>", unsafe_allow_html=True)
st.write("")

col_g1, col_g2, col_g3 = st.columns(3)
def metric_centrada(etiqueta, valor):
    return f'<div style="text-align: center;"><p style="font-size: 18px; margin-bottom: 0px; opacity: 0.7;">{etiqueta}</p><p style="font-size: 20px; font-weight: bold; margin-top: 0px;">{valor}</p></div>'

col_g1.markdown(metric_centrada("Clave Oficial", clave_actual), unsafe_allow_html=True)
col_g2.markdown(metric_centrada("Nombre del Acuífero", nombre_actual), unsafe_allow_html=True)
col_g3.markdown(metric_centrada("Área Total", f"{area_actual:,.1f} km²"), unsafe_allow_html=True)

st.markdown("---")

# ==========================================
# 2️⃣ ALERTA PASIVA (Carga de Drive)
# ==========================================
if "lista_archivos_nube" not in st.session_state or st.session_state.get("last_clave_cache") != clave_actual:
    with st.spinner(f"Buscando el historial de balances del acuífero {clave_actual} en Drive..."):
        st.session_state["lista_archivos_nube"] = listar_balances_json_cache(clave_actual)

    if st.session_state.get("last_clave_cache") is not None and st.session_state.get("last_clave_cache") != clave_actual:
        clave_vieja = st.session_state["last_clave_cache"]
        llaves_huerfanas = [k for k in st.session_state.keys() if str(k).endswith(f"_{clave_vieja}")]
        for k in llaves_huerfanas:
            del st.session_state[k]
        st.session_state["datos_drive_cargados"] = "LIMPIO"
        st.session_state["modo_historico"] = False
        st.session_state["veas_historico"] = None

    st.session_state["last_clave_cache"] = clave_actual

    if st.session_state.get("datos_drive_cargados") != "LIMPIO":
        st.session_state["datos_drive_cargados"] = None

archivos_nube = st.session_state.get("lista_archivos_nube", [])

if archivos_nube:
    st.warning(f"⚠️ **REGISTROS HISTÓRICOS:** Se localizaron {len(archivos_nube)} balances históricos guardados para el Acuífero {clave_actual}.")
    opciones_archivos = {arch['name']: arch['id'] for arch in archivos_nube}
    col_sel, col_btn1, col_btn2, col_vacia = st.columns([3, 1.5, 1.5, 1])

    with col_sel:
        archivo_seleccionado_nombre = st.selectbox("📅 Selecciona el año / archivo histórico:",
                                                   options=list(opciones_archivos.keys()),
                                                   key=f"select_hist_{clave_actual}")

    with col_btn1:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("✅ Cargar datos", type="primary", use_container_width=True):
            with st.spinner(f"Descargando {archivo_seleccionado_nombre}..."):
                id_seleccionado = opciones_archivos[archivo_seleccionado_nombre]
                datos_nube = descargar_balance_json_por_id(id_seleccionado)

                if datos_nube:
                    st.session_state["datos_drive_cargados"] = datos_nube
                    try:
                        anio_str = archivo_seleccionado_nombre.split('_B')[-1].split('.json')[0]
                        if (2000 + int(anio_str)) < datetime.datetime.now().year:
                            st.session_state["modo_historico"] = True
                        else:
                            st.session_state["modo_historico"] = False
                    except:
                        st.session_state["modo_historico"] = False

                    resultados_nube = datos_nube.get("resultados", {})
                    st.session_state["historico_resultados"] = resultados_nube
                    if "VEAS" in resultados_nube:
                        st.session_state["veas_historico"] = float(resultados_nube["VEAS"])
                    else:
                        st.session_state["veas_historico"] = None

                    # Activar bandera para auto-cálculo al recargar
                    st.session_state["auto_calc"] = True

                    st.rerun()
                else:
                    st.error("Error al descargar el archivo desde Google Drive.")

    with col_btn2:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🌟 empezar captura nueva", type="primary", use_container_width=True):
            st.session_state["datos_drive_cargados"] = "LIMPIO"
            st.session_state["modo_historico"] = False
            st.session_state["veas_historico"] = None
            st.session_state.pop("historico_resultados", None)
            st.rerun()

    st.markdown("---")

# ========================================================
# 3️⃣ INICIALIZACIÓN DE ESTADO
# ========================================================
def safe_val(val, default=0.0):
    if val is None:
        return default
    try:
        v = float(val)
        return default if math.isnan(v) else v
    except:
        return default

decision = st.session_state.get("datos_drive_cargados")

# DataFrames plantilla
df_def_eh = pd.DataFrame([{"Celda": "Celda 1", "Longitud B [m]": 0.0, "Ancho a [m]": 1.0, "h2-h1 [m]": 0.0, "Transmisividad T [m²/s]": 0.0}])
df_def_usos = pd.DataFrame({"Tipo de Uso": ["Agrícola", "Agroindustrial", "Doméstico", "Acuacultura", "Servicios", "Industrial", "Pecuario", "Público Urbano", "Diferentes Usos", "Generación Energía", "Comercio", "Otros", "Conservación Ecológica"], "Volumen [hm³/año]": [0.0]*13})
df_def_sh = pd.DataFrame([{"Celda": "Celda 1", "Longitud B [m]": 0.0, "Ancho a [m]": 1.0, "h2-h1 [m]": 0.0, "Transmisividad T [m²/s]": 0.0}])
df_def_etr = pd.DataFrame([{"Polígono / Zona": "Zona 1", "Límite Sup [m]": 0.0, "Límite Inf [m]": 1.0, "Área [km²]": 0.0, "Lámina ETR [m]": 0.0}])
df_def_dvs = pd.DataFrame([{"Polígono / Rango": "Rango 1", "Límite 1 [m]": 0.0, "Límite 2 [m]": None, "Área [km²]": 0.0, "Sy": 0.0}])
df_def_eas = pd.DataFrame([{"Celda": "Celda 1", "Longitud B [m]": 0.0, "Ancho a [m]": 1.0, "h2-h1 [m]": 0.0, "Transmisividad T [m²/s]": 0.0}])

init_vals = {"rr": 0.0, "pme": 5.0, "base": 2020, "tope": 2025, "ssb": 0.0, "dfb": 0.0, "dm": 0.0, "p_ri": 0.0, "p_dnc": [0.0]*5}

if isinstance(decision, dict):
    conf = decision.get("configuracion", {})
    dnc = conf.get("dnc_params", {})

    llaves_editores = [k for k in st.session_state.keys() if "editor_reactivo_" in k]
    for k in llaves_editores:
        st.session_state.pop(k, None)

    rr_init = safe_val(conf.get("rr_val", 0.0))
    pme_init = safe_val(conf.get("PME", 5.0), 5.0)

    periodo_dvs = conf.get("periodo_dvs") or {}
    a_base_init = int(safe_val(periodo_dvs.get("a_base", 2020), 2020))
    a_tope_init = int(safe_val(periodo_dvs.get("a_tope", 2025), 2025))

    otras_salidas = conf.get("otras_salidas") or {}
    ssb_init = safe_val(otras_salidas.get("Ssb", 0.0))
    dfb_init = safe_val(otras_salidas.get("Dfb", 0.0))
    dm_init = safe_val(otras_salidas.get("Dm", 0.0))
    p_ri_init = safe_val(conf.get("p_ri", 0.0))

    p_dnc_init = [
        safe_val(dnc.get("p_etr")), safe_val(dnc.get("p_sh")),
        safe_val(dnc.get("p_ssb")), safe_val(dnc.get("p_dfb")),
        safe_val(dnc.get("p_dm"))
    ]

    fuente_b_init = conf.get("fuente_b", "CENSO")
    anio_b_init = int(safe_val(conf.get("anio_b", 2026), 2026))

    st.session_state[f"rr_field_{clave_actual}"] = rr_init
    st.session_state[f"etr_pme_{clave_actual}"] = pme_init
    st.session_state[f"dvs_base_{clave_actual}"] = a_base_init
    st.session_state[f"dvs_tope_{clave_actual}"] = a_tope_init
    st.session_state[f"oa_ssb_{clave_actual}"] = ssb_init
    st.session_state[f"oa_dfb_{clave_actual}"] = dfb_init
    st.session_state[f"oa_dm_{clave_actual}"] = dm_init
    st.session_state[f"p_ri_field_{clave_actual}"] = p_ri_init
    st.session_state[f"b_src_{clave_actual}"] = fuente_b_init
    st.session_state[f"b_yr_{clave_actual}"] = anio_b_init

    st.session_state[f"p_dnc_etr_{clave_actual}"] = p_dnc_init[0]
    st.session_state[f"p_dnc_sh_{clave_actual}"] = p_dnc_init[1]
    st.session_state[f"p_dnc_ssb_{clave_actual}"] = p_dnc_init[2]
    st.session_state[f"p_dnc_dfb_{clave_actual}"] = p_dnc_init[3]
    st.session_state[f"p_dnc_dm_{clave_actual}"] = p_dnc_init[4]

    tabs = decision.get("tablas", {})
    def restaurar_tabla(clave, df_plantilla):
        if clave not in tabs:
            return df_plantilla.copy()
        df_restaurado = pd.DataFrame(tabs[clave])
        return df_restaurado if not df_restaurado.empty else pd.DataFrame(columns=df_plantilla.columns)

    st.session_state.table_eh = restaurar_tabla("eh", df_def_eh)
    st.session_state.table_usos = restaurar_tabla("usos", df_def_usos)
    st.session_state.table_sh = restaurar_tabla("sh", df_def_sh)
    st.session_state.table_etr = restaurar_tabla("etr", df_def_etr)
    st.session_state.table_dvs = restaurar_tabla("dvs", df_def_dvs)
    st.session_state.table_eas = restaurar_tabla("eas", df_def_eas)
    st.session_state["datos_drive_cargados"] = None

elif decision == "LIMPIO":
    llaves_editores = [
        f"editor_eh_{clave_actual}", f"editor_usos_{clave_actual}",
        f"editor_sh_{clave_actual}", f"editor_etr_{clave_actual}",
        f"editor_dvs_{clave_actual}", f"editor_eas_{clave_actual}",
    ]
    for k in llaves_editores:
        st.session_state.pop(k, None)

    # Limpiar resultados calculados, mensajes y bandera de auto-cálculo
    claves_resultados = [
        "eh_acumulado", "eas_acumulado", "sh_acumulado", "etr_acumulado", "dvs_anualizado",
        "df_calculado_eh", "df_calculado_eas", "df_calculado_sh", "df_calculado_etr", "df_calculado_dvs",
        "mensaje_table_eh", "mensaje_table_eas", "mensaje_table_sh", "mensaje_etr", "mensaje_dvs",
        "auto_calc"
    ]
    for clave in claves_resultados:
        st.session_state.pop(clave, None)

    st.session_state.table_eh = df_def_eh.copy()
    st.session_state.table_usos = df_def_usos.copy()
    st.session_state.table_sh = df_def_sh.copy()
    st.session_state.table_etr = df_def_etr.copy()
    st.session_state.table_dvs = df_def_dvs.copy()
    st.session_state.table_eas = df_def_eas.copy()

    rr_init, pme_init, a_base_init, a_tope_init = init_vals["rr"], init_vals["pme"], init_vals["base"], init_vals["tope"]
    ssb_init, dfb_init, dm_init, p_ri_init, p_dnc_init = init_vals["ssb"], init_vals["dfb"], init_vals["dm"], init_vals["p_ri"], init_vals["p_dnc"]
    fuente_b_init = "CENSO"
    anio_b_init = 2026

    st.session_state[f"rr_field_{clave_actual}"] = rr_init
    st.session_state[f"etr_pme_{clave_actual}"] = pme_init
    st.session_state[f"dvs_base_{clave_actual}"] = a_base_init
    st.session_state[f"dvs_tope_{clave_actual}"] = a_tope_init
    st.session_state[f"oa_ssb_{clave_actual}"] = ssb_init
    st.session_state[f"oa_dfb_{clave_actual}"] = dfb_init
    st.session_state[f"oa_dm_{clave_actual}"] = dm_init
    st.session_state[f"p_ri_field_{clave_actual}"] = p_ri_init
    st.session_state[f"b_src_{clave_actual}"] = fuente_b_init
    st.session_state[f"b_yr_{clave_actual}"] = anio_b_init

    st.session_state[f"p_dnc_etr_{clave_actual}"] = p_dnc_init[0]
    st.session_state[f"p_dnc_sh_{clave_actual}"] = p_dnc_init[1]
    st.session_state[f"p_dnc_ssb_{clave_actual}"] = p_dnc_init[2]
    st.session_state[f"p_dnc_dfb_{clave_actual}"] = p_dnc_init[3]
    st.session_state[f"p_dnc_dm_{clave_actual}"] = p_dnc_init[4]

    st.session_state["datos_drive_cargados"] = None

else:
    if "table_eh" not in st.session_state:
        st.session_state.table_eh = df_def_eh.copy()
        st.session_state.table_usos = df_def_usos.copy()
        st.session_state.table_sh = df_def_sh.copy()
        st.session_state.table_etr = df_def_etr.copy()
        st.session_state.table_dvs = df_def_dvs.copy()
        st.session_state.table_eas = df_def_eas.copy()

    rr_init, pme_init, a_base_init, a_tope_init = init_vals["rr"], init_vals["pme"], init_vals["base"], init_vals["tope"]
    ssb_init, dfb_init, dm_init, p_ri_init, p_dnc_init = init_vals["ssb"], init_vals["dfb"], init_vals["dm"], init_vals["p_ri"], init_vals["p_dnc"]
    fuente_b_init = "CENSO"
    anio_b_init = 2026

# ==========================================
# Inicialización de variables globales para evitar NameError
# ==========================================
if "df_calculado_eh" not in st.session_state:
    st.session_state.df_calculado_eh = pd.DataFrame()
if "df_calculado_eas" not in st.session_state:
    st.session_state.df_calculado_eas = pd.DataFrame()
if "df_calculado_sh" not in st.session_state:
    st.session_state.df_calculado_sh = pd.DataFrame()
if "df_calculado_etr" not in st.session_state:
    st.session_state.df_calculado_etr = pd.DataFrame()
if "df_calculado_dvs" not in st.session_state:
    st.session_state.df_calculado_dvs = pd.DataFrame()

if "eh_acumulado" not in st.session_state:
    st.session_state.eh_acumulado = 0.0
if "eas_acumulado" not in st.session_state:
    st.session_state.eas_acumulado = 0.0
if "sh_acumulado" not in st.session_state:
    st.session_state.sh_acumulado = 0.0
if "etr_acumulado" not in st.session_state:
    st.session_state.etr_acumulado = 0.0
if "dvs_anualizado" not in st.session_state:
    st.session_state.dvs_anualizado = 0.0

hist_res = st.session_state.get("historico_resultados", {})
veas_oficial = None

# ==========================================
# Función de cálculo vectorizado para tablas de flujo
# ==========================================
def calcular_flujo_vectorizado(df_in, modo_historico=False):
    df = df_in.copy()
    cols_editables = ['Longitud B [m]', 'Ancho a [m]', 'h2-h1 [m]', 'Transmisividad T [m²/s]']
    for col in cols_editables:
        if col not in df.columns:
            df[col] = np.nan
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    filas_completas = df[cols_editables].notna().all(axis=1)
    df['Gradiente i'] = np.nan
    df['Caudal Q [m³/s]'] = np.nan
    df['Volumen [hm³/año]'] = np.nan
    if filas_completas.any():
        ancho = df.loc[filas_completas, 'Ancho a [m]']
        h2_h1 = df.loc[filas_completas, 'h2-h1 [m]']
        trans = df.loc[filas_completas, 'Transmisividad T [m²/s]']
        longB = df.loc[filas_completas, 'Longitud B [m]']
        gradiente = np.where(ancho > 0, h2_h1 / ancho, 0.0)
        caudal = trans * gradiente * longB
        df.loc[filas_completas, 'Gradiente i'] = gradiente
        df.loc[filas_completas, 'Caudal Q [m³/s]'] = caudal
        df.loc[filas_completas, 'Volumen [hm³/año]'] = caudal * 31.536
    return df

# ==========================================
# Función para editor de tabla de flujo
# ==========================================
def editor_tabla_flujo(df_guardado, widget_key, titulo, modo_hist, tabla_session_key):
    if 'Gradiente i' not in df_guardado.columns:
        df_guardado = calcular_flujo_vectorizado(df_guardado, modo_hist)

    if st.session_state.get("auto_calc", False):
        df_calculado = calcular_flujo_vectorizado(df_guardado, modo_hist)
        total = df_calculado['Volumen [hm³/año]'].sum(skipna=True)
        st.session_state[f'{tabla_session_key.split("_")[-1]}_acumulado'] = total
        st.session_state[f"mensaje_{tabla_session_key}"] = f"**Total {titulo}: {total:,.1f} hm³/año**"
        st.session_state[tabla_session_key] = df_calculado.reset_index(drop=True)
        df_guardado = df_calculado

    df_editado = st.data_editor(
        df_guardado,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=widget_key,
        column_config={
            "Celda": st.column_config.TextColumn("Celda ✏️"),
            "Longitud B [m]": st.column_config.NumberColumn("Longitud B [m] ✏️", format="%.2f", min_value=0.0),
            "Ancho a [m]": st.column_config.NumberColumn("Ancho a [m] ✏️", format="%.2f", min_value=0.001),
            "h2-h1 [m]": st.column_config.NumberColumn("h2-h1 [m] ✏️", format="%.2f"),
            "Transmisividad T [m²/s]": st.column_config.NumberColumn("Transmisividad T [m²/s] ✏️", format="%.6f", min_value=0.0),
            "Gradiente i": st.column_config.NumberColumn("Gradiente i 🔒", disabled=True, format="%.6f"),
            "Caudal Q [m³/s]": st.column_config.NumberColumn("Caudal Q (m³/s) 🔒", disabled=True, format="%.6f"),
            "Volumen [hm³/año]": st.column_config.NumberColumn("Volumen (hm³) 🔒", disabled=True, format="%.2f")
        }
    )

    if st.button(f"Calcular {titulo}", key=f"btn_calc_{widget_key}", type="primary"):
        cols_guardar = ['Celda', 'Longitud B [m]', 'Ancho a [m]', 'h2-h1 [m]', 'Transmisividad T [m²/s]']
        st.session_state[tabla_session_key] = df_editado[cols_guardar].copy().reset_index(drop=True)
        df_calculado = calcular_flujo_vectorizado(df_editado, modo_hist)
        total = df_calculado['Volumen [hm³/año]'].sum(skipna=True)
        st.session_state[f'df_calculado_{tabla_session_key.split("_")[-1]}'] = df_calculado.reset_index(drop=True)
        st.session_state[f'{tabla_session_key.split("_")[-1]}_acumulado'] = total
        st.session_state[f"mensaje_{tabla_session_key}"] = f"**Total {titulo}: {total:,.1f} hm³/año**"
        st.session_state[tabla_session_key] = df_calculado.reset_index(drop=True)
        st.rerun()

    mensaje_key = f"mensaje_{tabla_session_key}"
    if mensaje_key in st.session_state:
        st.success(st.session_state[mensaje_key])
        del st.session_state[mensaje_key]

    return df_editado, st.session_state.get(f'{tabla_session_key.split("_")[-1]}_acumulado', 0.0)

# ==========================================
# PESTAÑAS
# ==========================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📥 1. Entradas", "📤 2. Salidas", "📊 3. Almacenamiento", "🌿 4. DNC y Recargas", "⚖️ 5. Balance Final"
])

# --- PESTAÑA 1: Entradas ---
with tab1:
    st.header("Entradas al Sistema")

    c_rr, c_info = st.columns([1, 2])
    rr_val = c_rr.number_input(
        "Recarga por lluvia (Rr) [hm³/año]:",
        min_value=0.0, value=rr_init, format="%.2f", key=f"rr_field_{clave_actual}"
    )

    modo_hist = st.session_state.get("modo_historico", False)

    sub_tab_eh, sub_tab_eas = st.tabs(["🌊 Entradas Horizontales (Eh)", "🧂 Entradas Salobres (Eas)"])

    with sub_tab_eh:
        key_eh = f"editor_reactivo_eh_{clave_actual}"
        df_base_eh = st.session_state.table_eh.copy()
        df_editado_eh, eh_total = editor_tabla_flujo(
            df_base_eh, key_eh, "Entradas Horizontales (Eh)", modo_hist, "table_eh"
        )
        st.session_state.eh_acumulado = eh_total

    with sub_tab_eas:
        key_eas = f"editor_reactivo_eas_{clave_actual}"
        df_base_eas = st.session_state.table_eas.copy()
        df_editado_eas, eas_total = editor_tabla_flujo(
            df_base_eas, key_eas, "Entradas Salobres (Eas)", modo_hist, "table_eas"
        )
        st.session_state.eas_acumulado = eas_total

# --- PESTAÑA 2: Salidas ---
with tab2:
    st.header("Salidas del Sistema")
    st.subheader("1. Extracción / Bombeo (B)")
    col_b1, col_b2 = st.columns(2)

    k_src = f"b_src_{clave_actual}"
    k_yr = f"b_yr_{clave_actual}"

    fuente_actual = st.session_state.get(k_src, fuente_b_init)
    opciones_fuente = ["CENSO", "REPNA"]
    if fuente_actual not in opciones_fuente:
        opciones_fuente.append(fuente_actual)
    fuente_b = col_b1.selectbox("Origen de datos:", opciones_fuente,
                                index=opciones_fuente.index(fuente_actual), key=k_src)

    try:
        anio_seguro = int(float(anio_b_init))
    except (ValueError, TypeError):
        anio_seguro = 2026
    anio_b = col_b2.number_input("Año de info:", min_value=1900,
                                 value=st.session_state.get(k_yr, anio_seguro), key=k_yr)

    widget_key_usos = f"editor_reactivo_usos_{clave_actual}"

    df_base_usos = st.session_state.table_usos.copy()
    df_base_usos['Volumen [hm³/año]'] = pd.to_numeric(
        df_base_usos['Volumen [hm³/año]'], errors='coerce'
    ).fillna(0.0)

    bombeo_bruto_base = df_base_usos['Volumen [hm³/año]'].sum()
    df_base_usos['Porcentaje (%)'] = np.where(
        bombeo_bruto_base > 0,
        (df_base_usos['Volumen [hm³/año]'] / bombeo_bruto_base) * 100,
        0.0
    )

    df_editado_usos = st.data_editor(
        df_base_usos[['Tipo de Uso', 'Volumen [hm³/año]', 'Porcentaje (%)']],
        use_container_width=True,
        hide_index=True,
        key=widget_key_usos,
        column_config={
            "Tipo de Uso": st.column_config.TextColumn("Clasificación del Uso 🔒", disabled=True),
            "Volumen [hm³/año]": st.column_config.NumberColumn(
                "Volumen (hm³/año) ✏️",
                min_value=0.0,
                format="%.6f",
            ),
            "Porcentaje (%)": st.column_config.ProgressColumn(
                "Impacto (%) 🔒",
                format="%.1f %%",
                min_value=0.0,
                max_value=100.0
            )
        }
    )

    # Auto-cálculo para bombeo si viene de carga
    if st.session_state.get("auto_calc", False):
        st.session_state.table_usos = df_editado_usos[['Tipo de Uso', 'Volumen [hm³/año]']].copy()
        st.session_state.table_usos['Volumen [hm³/año]'] = pd.to_numeric(
            st.session_state.table_usos['Volumen [hm³/año]'], errors='coerce'
        ).fillna(0.0)
        st.session_state.table_usos = st.session_state.table_usos.reset_index(drop=True)

    bombeo_bruto_actual = pd.to_numeric(
        df_editado_usos['Volumen [hm³/año]'], errors='coerce'
    ).fillna(0.0).sum()
    bombeo_calc = round(bombeo_bruto_actual, 1)

    with st.container(border=True):
        c_res1, c_res2 = st.columns([1, 2])
        c_res1.metric("Volumen Total Concesionado (B)", f"{bombeo_bruto_actual:,.6f} hm³")
        if bombeo_bruto_actual > 0:
            df_top = df_editado_usos.sort_values(by='Volumen [hm³/año]', ascending=False).head(3)
            top_text = ", ".join([
                f"**{row['Tipo de Uso']}** ({row['Porcentaje (%)']/100:.1%})"
                for _, row in df_top.iterrows() if row['Volumen [hm³/año]'] > 0
            ])
            c_res2.info(f"📌 **Principales demandantes:** {top_text}")
        else:
            c_res2.info("📌 Ingrese volúmenes para visualizar la distribución.")

    if st.button("Calcular bombeo", key=f"btn_calc_usos_{clave_actual}", type="primary"):
        st.session_state.table_usos = df_editado_usos[['Tipo de Uso', 'Volumen [hm³/año]']].copy()
        st.session_state.table_usos['Volumen [hm³/año]'] = pd.to_numeric(
            st.session_state.table_usos['Volumen [hm³/año]'], errors='coerce'
        ).fillna(0.0)
        st.session_state.table_usos = st.session_state.table_usos.reset_index(drop=True)
        st.rerun()

    veas_oficial = obtener_veas_excel(clave_actual)
    if st.session_state.get("modo_historico", False) and st.session_state.get("veas_historico") is not None:
        veas_calc = st.session_state["veas_historico"]
    elif veas_oficial is not None:
        veas_calc = veas_oficial
    else:
        veas_calc = bombeo_bruto_actual

    st.markdown("---")
    st.subheader("2. Salidas Horizontales (Sh)")

    key_sh = f"editor_reactivo_sh_{clave_actual}"
    df_base_sh = st.session_state.table_sh.copy()
    df_editado_sh, sh_total = editor_tabla_flujo(
        df_base_sh, key_sh, "Salidas Horizontales (Sh)", modo_hist, "table_sh"
    )
    st.session_state.sh_acumulado = sh_total

    st.markdown("---")
    st.subheader("3. Evapotranspiración (ETR)")
    PME = st.number_input("Prof. Máxima de Extinción (PME) [m]:", min_value=0.0,
                          value=pme_init, key=f"etr_pme_{clave_actual}")

    key_etr = f"editor_reactivo_etr_{clave_actual}"
    df_base_etr = st.session_state.table_etr.copy()
    lsup = pd.to_numeric(df_base_etr['Límite Sup [m]'], errors='coerce')
    linf = pd.to_numeric(df_base_etr['Límite Inf [m]'], errors='coerce')
    area_etr = pd.to_numeric(df_base_etr['Área [km²]'], errors='coerce')
    lamina = pd.to_numeric(df_base_etr['Lámina ETR [m]'], errors='coerce')
    filas_completas = df_base_etr[['Límite Sup [m]', 'Área [km²]', 'Lámina ETR [m]']].notna().all(axis=1)
    df_base_etr['Prof. Media (PM) [m]'] = np.nan
    df_base_etr['% ETR'] = np.nan
    df_base_etr['Volumen [hm³/año]'] = np.nan
    if filas_completas.any():
        lsup_c = lsup[filas_completas]
        linf_c = linf[filas_completas]
        pm = np.where(linf_c.isna(), lsup_c, (lsup_c + linf_c) / 2.0)
        pct_etr = np.where((pm < PME) & (PME > 0), ((PME - pm) / PME) * 100, 0.0)
        vol = area_etr[filas_completas] * lamina[filas_completas] * (pct_etr / 100.0)
        df_base_etr.loc[filas_completas, 'Prof. Media (PM) [m]'] = pm
        df_base_etr.loc[filas_completas, '% ETR'] = pct_etr
        df_base_etr.loc[filas_completas, 'Volumen [hm³/año]'] = vol

    df_editado_etr = st.data_editor(
        df_base_etr,
        num_rows="dynamic", use_container_width=True, hide_index=True,
        key=key_etr,
        column_config={
            "Polígono / Zona": st.column_config.TextColumn("Zona ✏️"),
            "Límite Sup [m]": st.column_config.NumberColumn("Límite Sup [m] ✏️", format="%.2f"),
            "Límite Inf [m]": st.column_config.NumberColumn("Límite Inf [m] (Opcional) ✏️", default=None, format="%.2f"),
            "Área [km²]": st.column_config.NumberColumn("Área [km²] ✏️", min_value=0.0, format="%.2f"),
            "Lámina ETR [m]": st.column_config.NumberColumn("Lámina ETR [m] ✏️", min_value=0.0, format="%.6f"),
            "Prof. Media (PM) [m]": st.column_config.NumberColumn("PM [m] 🔒", disabled=True, format="%.2f"),
            "% ETR": st.column_config.NumberColumn("% ETR 🔒", disabled=True, format="%.1f %%"),
            "Volumen [hm³/año]": st.column_config.NumberColumn("Volumen (hm³) 🔒", disabled=True, format="%.2f")
        }
    )

    # Auto-cálculo para ETR
    if st.session_state.get("auto_calc", False):
        cols_guardar_etr = ['Polígono / Zona', 'Límite Sup [m]', 'Límite Inf [m]', 'Área [km²]', 'Lámina ETR [m]']
        st.session_state.table_etr = df_editado_etr[cols_guardar_etr].copy().reset_index(drop=True)

        lsup = pd.to_numeric(df_editado_etr['Límite Sup [m]'], errors='coerce')
        linf = pd.to_numeric(df_editado_etr['Límite Inf [m]'], errors='coerce')
        area_etr = pd.to_numeric(df_editado_etr['Área [km²]'], errors='coerce')
        lamina = pd.to_numeric(df_editado_etr['Lámina ETR [m]'], errors='coerce')
        filas_completas = df_editado_etr[['Límite Sup [m]', 'Área [km²]', 'Lámina ETR [m]']].notna().all(axis=1)

        df_calculado_etr = df_editado_etr.copy()
        df_calculado_etr['Prof. Media (PM) [m]'] = np.nan
        df_calculado_etr['% ETR'] = np.nan
        df_calculado_etr['Volumen [hm³/año]'] = np.nan

        if filas_completas.any():
            lsup_c = lsup[filas_completas]
            linf_c = linf[filas_completas]
            pm = np.where(linf_c.isna(), lsup_c, (lsup_c + linf_c) / 2.0)
            pct_etr = np.where((pm < PME) & (PME > 0), ((PME - pm) / PME) * 100, 0.0)
            vol = area_etr[filas_completas] * lamina[filas_completas] * (pct_etr / 100.0)
            df_calculado_etr.loc[filas_completas, 'Prof. Media (PM) [m]'] = pm
            df_calculado_etr.loc[filas_completas, '% ETR'] = pct_etr
            df_calculado_etr.loc[filas_completas, 'Volumen [hm³/año]'] = vol

        etr_acumulado_tabla = df_calculado_etr['Volumen [hm³/año]'].sum(skipna=True)
        hist_res = st.session_state.get("historico_resultados", {}) if st.session_state.get("modo_historico", False) else {}        
        if st.session_state.get("modo_historico", False) and etr_acumulado_tabla == 0:
            etr_acumulado = float(hist_res.get("ETR", 0.0))
        else:
            etr_acumulado = etr_acumulado_tabla
        st.session_state.etr_acumulado = etr_acumulado
        st.session_state.df_calculado_etr = df_calculado_etr.reset_index(drop=True)
        st.session_state.table_etr = df_calculado_etr.reset_index(drop=True)
        st.session_state["mensaje_etr"] = f"**Total Evapotranspiración (ETR): {etr_acumulado:,.1f} hm³/año**"

    if st.button("Calcular ETR", key=f"btn_calc_etr_{clave_actual}", type="primary"):
        cols_guardar_etr = ['Polígono / Zona', 'Límite Sup [m]', 'Límite Inf [m]', 'Área [km²]', 'Lámina ETR [m]']
        st.session_state.table_etr = df_editado_etr[cols_guardar_etr].copy().reset_index(drop=True)

        lsup = pd.to_numeric(df_editado_etr['Límite Sup [m]'], errors='coerce')
        linf = pd.to_numeric(df_editado_etr['Límite Inf [m]'], errors='coerce')
        area_etr = pd.to_numeric(df_editado_etr['Área [km²]'], errors='coerce')
        lamina = pd.to_numeric(df_editado_etr['Lámina ETR [m]'], errors='coerce')
        filas_completas = df_editado_etr[['Límite Sup [m]', 'Área [km²]', 'Lámina ETR [m]']].notna().all(axis=1)

        df_calculado_etr = df_editado_etr.copy()
        df_calculado_etr['Prof. Media (PM) [m]'] = np.nan
        df_calculado_etr['% ETR'] = np.nan
        df_calculado_etr['Volumen [hm³/año]'] = np.nan

        if filas_completas.any():
            lsup_c = lsup[filas_completas]
            linf_c = linf[filas_completas]
            pm = np.where(linf_c.isna(), lsup_c, (lsup_c + linf_c) / 2.0)
            pct_etr = np.where((pm < PME) & (PME > 0), ((PME - pm) / PME) * 100, 0.0)
            vol = area_etr[filas_completas] * lamina[filas_completas] * (pct_etr / 100.0)
            df_calculado_etr.loc[filas_completas, 'Prof. Media (PM) [m]'] = pm
            df_calculado_etr.loc[filas_completas, '% ETR'] = pct_etr
            df_calculado_etr.loc[filas_completas, 'Volumen [hm³/año]'] = vol

        etr_acumulado_tabla = df_calculado_etr['Volumen [hm³/año]'].sum(skipna=True)
        hist_res = st.session_state.get("historico_resultados", {}) if st.session_state.get("modo_historico", False) else {}        
        if st.session_state.get("modo_historico", False) and etr_acumulado_tabla == 0:
            etr_acumulado = float(hist_res.get("ETR", 0.0))
        else:
            etr_acumulado = etr_acumulado_tabla
        st.session_state.etr_acumulado = etr_acumulado
        st.session_state.df_calculado_etr = df_calculado_etr.reset_index(drop=True)
        st.session_state.table_etr = df_calculado_etr.reset_index(drop=True)
        st.session_state["mensaje_etr"] = f"**Total Evapotranspiración (ETR): {etr_acumulado:,.1f} hm³/año**"
        st.rerun()

    if "mensaje_etr" in st.session_state:
        st.success(st.session_state["mensaje_etr"])
        del st.session_state["mensaje_etr"]

    st.markdown("---")
    st.subheader("4. Otras Salidas Naturales")
    col_oa1, col_oa2, col_oa3 = st.columns(3)
    val_ssb = col_oa1.number_input("Salidas Subterráneas (Ssb) [hm³/año]:", min_value=0.0,
                                   value=ssb_init, key=f"oa_ssb_{clave_actual}")
    val_dfb = col_oa2.number_input("Descarga Flujo Base (Dfb) [hm³/año]:", min_value=0.0,
                                   value=dfb_init, key=f"oa_dfb_{clave_actual}")
    val_dm = col_oa3.number_input("Descarga Manantiales (Dm) [hm³/año]:", min_value=0.0,
                                  value=dm_init, key=f"oa_dm_{clave_actual}")

# --- PESTAÑA 3: Almacenamiento ---
with tab3:
    st.header("Cambio de Almacenamiento (ΔV(S))")
    c_y1, c_y2 = st.columns(2)
    a_base = c_y1.number_input("Año Base:", value=st.session_state.get(f"dvs_base_{clave_actual}", a_base_init),
                               key=f"dvs_base_{clave_actual}")
    a_tope = c_y2.number_input("Año Tope:", value=st.session_state.get(f"dvs_tope_{clave_actual}", a_tope_init),
                               key=f"dvs_tope_{clave_actual}")
    RDA = a_tope - a_base
    st.session_state["bloqueo_dvs"] = False

    if RDA > 0:
        st.write(f"**Años de evaluación (RDA):** {RDA}")
        st.info("💡 **Nota:** Si el rango no tiene Límite 2, déjelo en blanco. El sistema tomará el Límite 1 como promedio directo.")

        key_dvs = f"editor_reactivo_dvs_{clave_actual}"
        df_base_dvs = st.session_state.table_dvs.copy()
        l1 = pd.to_numeric(df_base_dvs['Límite 1 [m]'], errors='coerce')
        l2 = pd.to_numeric(df_base_dvs['Límite 2 [m]'], errors='coerce')
        area = pd.to_numeric(df_base_dvs['Área [km²]'], errors='coerce')
        sy = pd.to_numeric(df_base_dvs['Sy'], errors='coerce')
        filas_completas = df_base_dvs[['Límite 1 [m]', 'Área [km²]', 'Sy']].notna().all(axis=1)
        df_base_dvs['Evolución Media [m]'] = np.nan
        df_base_dvs['Volumen Parcial [hm³]'] = np.nan
        if filas_completas.any():
            ev_media = np.where(l2[filas_completas].isna(), l1[filas_completas],
                                (l1[filas_completas] + l2[filas_completas]) / 2.0)
            vol_parcial = ev_media * area[filas_completas] * sy[filas_completas]
            df_base_dvs.loc[filas_completas, 'Evolución Media [m]'] = ev_media
            df_base_dvs.loc[filas_completas, 'Volumen Parcial [hm³]'] = vol_parcial

        df_editado_dvs = st.data_editor(
            df_base_dvs,
            num_rows="dynamic", use_container_width=True, hide_index=True,
            key=key_dvs,
            column_config={
                "Polígono / Rango": st.column_config.TextColumn("Rango ✏️"),
                "Límite 1 [m]": st.column_config.NumberColumn("Límite 1 [m] ✏️", format="%.2f"),
                "Límite 2 [m]": st.column_config.NumberColumn("Límite 2 [m] (Opcional) ✏️", default=None, format="%.2f"),
                "Área [km²]": st.column_config.NumberColumn("Área [km²] ✏️", min_value=0.0, format="%.2f"),
                "Sy": st.column_config.NumberColumn("Coef. Almacenamiento (Sy) ✏️", min_value=0.0, format="%.6f"),
                "Evolución Media [m]": st.column_config.NumberColumn("Evolución Media 🔒", disabled=True, format="%.2f"),
                "Volumen Parcial [hm³]": st.column_config.NumberColumn("Volumen Parcial 🔒", disabled=True, format="%.2f")
            }
        )

        # Auto-cálculo para DVS
        if st.session_state.get("auto_calc", False):
            cols_guardar_dvs = ['Polígono / Rango', 'Límite 1 [m]', 'Límite 2 [m]', 'Área [km²]', 'Sy']
            st.session_state.table_dvs = df_editado_dvs[cols_guardar_dvs].copy().reset_index(drop=True)

            l1 = pd.to_numeric(df_editado_dvs['Límite 1 [m]'], errors='coerce')
            l2 = pd.to_numeric(df_editado_dvs['Límite 2 [m]'], errors='coerce')
            area = pd.to_numeric(df_editado_dvs['Área [km²]'], errors='coerce')
            sy = pd.to_numeric(df_editado_dvs['Sy'], errors='coerce')
            filas_completas = df_editado_dvs[['Límite 1 [m]', 'Área [km²]', 'Sy']].notna().all(axis=1)

            df_calculado_dvs = df_editado_dvs.copy()
            df_calculado_dvs['Evolución Media [m]'] = np.nan
            df_calculado_dvs['Volumen Parcial [hm³]'] = np.nan

            if filas_completas.any():
                ev_media = np.where(l2[filas_completas].isna(), l1[filas_completas],
                                    (l1[filas_completas] + l2[filas_completas]) / 2.0)
                vol_parcial = ev_media * area[filas_completas] * sy[filas_completas]
                df_calculado_dvs.loc[filas_completas, 'Evolución Media [m]'] = ev_media
                df_calculado_dvs.loc[filas_completas, 'Volumen Parcial [hm³]'] = vol_parcial

            DVS_t = df_calculado_dvs['Volumen Parcial [hm³]'].sum(skipna=True)
            dvs_anualizado = DVS_t / RDA
            st.session_state.dvs_anualizado = dvs_anualizado
            st.session_state.df_calculado_dvs = df_calculado_dvs.reset_index(drop=True)
            st.session_state.table_dvs = df_calculado_dvs.reset_index(drop=True)
            st.session_state["mensaje_dvs"] = f"**Cambio de Almacenamiento Anualizado ΔV(S):** {dvs_anualizado:,.1f} hm³/año"

        if st.button("Calcular ΔV(S)", key=f"btn_calc_dvs_{clave_actual}", type="primary"):
            cols_guardar_dvs = ['Polígono / Rango', 'Límite 1 [m]', 'Límite 2 [m]', 'Área [km²]', 'Sy']
            st.session_state.table_dvs = df_editado_dvs[cols_guardar_dvs].copy().reset_index(drop=True)

            l1 = pd.to_numeric(df_editado_dvs['Límite 1 [m]'], errors='coerce')
            l2 = pd.to_numeric(df_editado_dvs['Límite 2 [m]'], errors='coerce')
            area = pd.to_numeric(df_editado_dvs['Área [km²]'], errors='coerce')
            sy = pd.to_numeric(df_editado_dvs['Sy'], errors='coerce')
            filas_completas = df_editado_dvs[['Límite 1 [m]', 'Área [km²]', 'Sy']].notna().all(axis=1)

            df_calculado_dvs = df_editado_dvs.copy()
            df_calculado_dvs['Evolución Media [m]'] = np.nan
            df_calculado_dvs['Volumen Parcial [hm³]'] = np.nan

            if filas_completas.any():
                ev_media = np.where(l2[filas_completas].isna(), l1[filas_completas],
                                    (l1[filas_completas] + l2[filas_completas]) / 2.0)
                vol_parcial = ev_media * area[filas_completas] * sy[filas_completas]
                df_calculado_dvs.loc[filas_completas, 'Evolución Media [m]'] = ev_media
                df_calculado_dvs.loc[filas_completas, 'Volumen Parcial [hm³]'] = vol_parcial

            DVS_t = df_calculado_dvs['Volumen Parcial [hm³]'].sum(skipna=True)
            dvs_anualizado = DVS_t / RDA
            st.session_state.dvs_anualizado = dvs_anualizado
            st.session_state.df_calculado_dvs = df_calculado_dvs.reset_index(drop=True)
            st.session_state.table_dvs = df_calculado_dvs.reset_index(drop=True)
            st.session_state["mensaje_dvs"] = f"**Cambio de Almacenamiento Anualizado ΔV(S):** {dvs_anualizado:,.1f} hm³/año"
            st.rerun()
        else:
            dvs_anualizado = st.session_state.get('dvs_anualizado', 0.0)

        if "mensaje_dvs" in st.session_state:
            st.success(st.session_state["mensaje_dvs"])
            del st.session_state["mensaje_dvs"]

    else:
        st.error("🛑 El Año Tope debe ser estrictamente mayor al Año Base.")
        st.session_state["bloqueo_dvs"] = True
        dvs_anualizado = 0.0
        st.session_state.df_calculado_dvs = pd.DataFrame()

# --- PESTAÑA 4: DNC y Recargas ---
with tab4:
    st.header("Descarga Natural Comprometida (DNC)")
    st.caption("Ajuste los porcentajes aplicables para el cálculo de la DNC.")

    cp1, cp2, cp3, cp4, cp5 = st.columns(5)
    p_etr = cp1.number_input("% DNC ETR", value=p_dnc_init[0], key=f"p_dnc_etr_{clave_actual}")
    p_sh  = cp2.number_input("% DNC Sh", value=p_dnc_init[1], key=f"p_dnc_sh_{clave_actual}")
    p_ssb = cp3.number_input("% DNC Ssb", value=p_dnc_init[2], key=f"p_dnc_ssb_{clave_actual}")
    p_dfb = cp4.number_input("% DNC Dfb", value=p_dnc_init[3], key=f"p_dnc_dfb_{clave_actual}")
    p_dm  = cp5.number_input("% DNC Dm", value=p_dnc_init[4], key=f"p_dnc_dm_{clave_actual}")

    suma_porcentajes = p_etr + p_sh + p_ssb + p_dfb + p_dm
    if suma_porcentajes > 100:
        st.warning(f"⚠️ La suma de porcentajes de DNC es {suma_porcentajes:.1f}%, lo cual excede el 100%. Revise los valores.")

    etr_acumulado = st.session_state.get('etr_acumulado', 0.0)
    sh_acumulado = st.session_state.get('sh_acumulado', 0.0)
    eh_acumulado = st.session_state.get('eh_acumulado', 0.0)
    eas_acumulado = st.session_state.get('eas_acumulado', 0.0)
    dvs_anualizado = st.session_state.get('dvs_anualizado', 0.0)

    DNC_ETR = etr_acumulado * (p_etr / 100)
    DNC_Sh  = sh_acumulado * (p_sh / 100)
    DNC_Ssb = val_ssb * (p_ssb / 100)
    DNC_Dfb = val_dfb * (p_dfb / 100)
    DNC_Dm  = val_dm * (p_dm / 100)

    if st.session_state.get("modo_historico", False) and hist_res:
        dnc_total_calc = hist_res.get("DNC_total", 0.0)
        etiqueta_dnc = "DNC Total (Histórico Oficial)"
    else:
        dnc_total_calc = sum([DNC_ETR, DNC_Sh, DNC_Ssb, DNC_Dfb, DNC_Dm])
        etiqueta_dnc = "DNC Total Calculada"

    with st.container(border=True):
        st.metric(etiqueta_dnc, f"{dnc_total_calc:,.1f} hm³/año")

    st.markdown("---")
    st.subheader("Cálculo Automático de Recarga Vertical (Rv) por Balance")

    if st.session_state.get("modo_historico", False) and hist_res:
        val_rv_calc = hist_res.get("Rv", 0.0)
        etiqueta_rv = "Recarga Vertical (Rv) (Histórico Oficial)"
    else:
        val_rv_calc = (bombeo_calc + etr_acumulado + sh_acumulado + val_ssb + val_dfb + val_dm +
                       dvs_anualizado - eh_acumulado - eas_acumulado - rr_val)
        etiqueta_rv = "Recarga Vertical Resultante (Rv)"

    with st.container(border=True):
        st.metric(etiqueta_rv, f"{val_rv_calc:,.1f} hm³/año")

    st.markdown("---")
    p_ri = st.number_input("¿Qué porcentaje (%) de la Rv constituye la Recarga Incidental (Ri)?",
                           min_value=0.0, value=p_ri_init, key=f"p_ri_field_{clave_actual}")

    if st.session_state.get("modo_historico", False) and hist_res:
        val_ri_calc = hist_res.get("Ri", 0.0)
        etiqueta_ri = "Recarga Incidental (Ri) (Histórico Oficial)"
    else:
        val_ri_calc = round(val_rv_calc * (p_ri / 100), 1)
        etiqueta_ri = "Recarga Incidental Resultante (Ri)"

    with st.container(border=True):
        st.metric(etiqueta_ri, f"{val_ri_calc:,.1f} hm³/año")

# --- PESTAÑA 5: Balance Final ---
with tab5:
    st.header("⚖️ Balance Final y Disponibilidad")

    Recarga_Total = round(rr_val + eh_acumulado + val_rv_calc + val_ri_calc, 1)
    Descarga_Total = round(bombeo_calc + sh_acumulado + etr_acumulado + val_ssb + val_dfb + val_dm, 1)
    Disponibilidad = round(Recarga_Total - dnc_total_calc - veas_calc, 6)

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Recarga Total (R)", f"{Recarga_Total:,.1f} hm³", delta="Entradas al sistema", delta_color="normal")
        c2.metric("Descarga Total (S)", f"{Descarga_Total:,.1f} hm³", delta="Salidas del sistema", delta_color="inverse")

        if Recarga_Total == 0 and dnc_total_calc == 0:
            c3.metric("Disponibilidad (DMA)", "Pendiente")
        else:
            if Disponibilidad >= 0:
                c3.metric("Disponibilidad (DMA)", f"{Disponibilidad:,.6f} hm³", delta="Superávit", delta_color="normal")
            else:
                c3.metric("Disponibilidad (DMA)", f"{Disponibilidad:,.6f} hm³", delta="Déficit (Sobreexplotado)", delta_color="inverse")

    if st.session_state.get("modo_historico", False) and st.session_state.get("veas_historico") is not None:
        st.info(f"🕰️ **VEAS HISTÓRICO UTILIZADO:** {veas_calc:,.6f} hm³/año (Congelado para auditar este año)")
    elif veas_oficial is not None:
        st.info(f"⚖️ **VEAS OFICIAL SEP 2025:** {veas_calc:,.6f} hm³/año (Directo del Catálogo Central)")
    else:
        st.warning(f"⚠️ No se encontró la clave en el Catálogo VEAS. Se usó el volumen de bombeo capturado ({veas_calc:,.6f} hm³) como VEAS.")

    st.markdown("---")

    col_graf, col_docs = st.columns([2, 1])

    with col_graf:
        st.subheader("Visualización del Balance")
        fig = go.Figure(go.Waterfall(
            name="Balance", orientation="v",
            measure=["relative", "relative", "relative", "total"],
            x=["Recarga (R)", "DNC", "VEAS", "DMA Final"],
            textposition="outside",
            text=[f"{Recarga_Total:.1f}", f"-{dnc_total_calc:.1f}", f"-{veas_calc:.2f}", f"{Disponibilidad:.2f}"],
            y=[Recarga_Total, -dnc_total_calc, -veas_calc, Disponibilidad],
            connector={"line": {"color": "rgb(63, 63, 63)"}},
            decreasing={"marker": {"color": "#ff6666"}},
            increasing={"marker": {"color": "#27ae60"}},
            totals={"marker": {"color": "#2980b9" if Disponibilidad >= 0 else "#c0392b"}}
        ))
        fig.update_layout(height=400, margin=dict(l=20, r=20, t=30, b=20), plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    with col_docs:
        st.subheader("📑 Documentación")

        df_resumen_excel = pd.DataFrame([
            {"Concepto": "Recarga Vertical por Lluvia (Rr)", "Volumen (hm³)": rr_val},
            {"Concepto": "Entradas Horizontales (Eh)", "Volumen (hm³)": eh_acumulado},
            {"Concepto": "Entradas de Agua Salobre (Eas)", "Volumen (hm³)": eas_acumulado},
            {"Concepto": "Recarga Vertical Resultante (Rv)", "Volumen (hm³)": val_rv_calc},
            {"Concepto": "Recarga Incidental (Ri)", "Volumen (hm³)": val_ri_calc},
            {"Concepto": "RECARGA TOTAL (R)", "Volumen (hm³)": Recarga_Total},
            {"Concepto": "Extracción / Bombeo (B)", "Volumen (hm³)": bombeo_calc},
            {"Concepto": "Salidas Horizontales (Sh)", "Volumen (hm³)": sh_acumulado},
            {"Concepto": "Evapotranspiración (ETR)", "Volumen (hm³)": etr_acumulado},
            {"Concepto": "Salidas Subterráneas (Ssb)", "Volumen (hm³)": val_ssb},
            {"Concepto": "Descarga Flujo Base (Dfb)", "Volumen (hm³)": val_dfb},
            {"Concepto": "Descarga Manantiales (Dm)", "Volumen (hm³)": val_dm},
            {"Concepto": "DESCARGA TOTAL (S)", "Volumen (hm³)": Descarga_Total},
            {"Concepto": "Cambio de Almacenamiento ΔV(S)", "Volumen (hm³)": dvs_anualizado},
            {"Concepto": "Descarga Natural Comprometida (DNC)", "Volumen (hm³)": dnc_total_calc},
            {"Concepto": "DISPONIBILIDAD MEDIA ANUAL (DMA)", "Volumen (hm³)": Disponibilidad}
        ])

        dvs_excel = df_editado_dvs.copy() if 'df_editado_dvs' in locals() else pd.DataFrame()
        modo_hist_excel = st.session_state.get("modo_historico", False)

        bytes_excel = generar_excel_matriz(
            df_resumen=df_resumen_excel,
            df_eh=calcular_flujo_vectorizado(df_editado_eh, modo_hist_excel),
            df_usos=df_editado_usos.copy(),
            df_sh=calcular_flujo_vectorizado(df_editado_sh, modo_hist_excel),
            df_etr=df_editado_etr.copy(),
            df_dvs=dvs_excel,
            df_eas=calcular_flujo_vectorizado(df_editado_eas, modo_hist_excel),
            dvs_anualizado=dvs_anualizado,
            fuente_b=fuente_b,
            anio_b=anio_b,
            a_base=a_base,
            a_tope=a_tope,
            rda=RDA if 'RDA' in locals() else 5,
            dnc_detalle=[DNC_ETR, DNC_Sh, DNC_Ssb, DNC_Dfb, DNC_Dm],
            pme=PME  
        )

        error_critico = st.session_state.get("bloqueo_dvs", False)

        st.download_button(
            "📊 Descargar Matriz de Cálculo (Excel)",
            data=bytes_excel,
            file_name=f"Matriz_Calculo_{clave_actual}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
            disabled=error_critico
        )

        if error_critico:
            st.error("⚠️ La descarga y el guardado están bloqueados porque hay errores en la Pestaña 3 (Años de Evaluación).")

        st.write("☁️ **Sincronización**")

        if st.session_state.get("modo_historico", False):
            st.warning("🔒 Guardado bloqueado (Histórico)")
            if st.button("🔄 Capturar nuevo año", use_container_width=True):
                st.session_state["datos_drive_cargados"] = "LIMPIO"
                st.session_state["modo_historico"] = False
                st.session_state["veas_historico"] = None
                st.rerun()
        else:
            anio_guardado = st.number_input("Año de evaluación:", min_value=1900, max_value=2100,
                                            value=datetime.datetime.now().year, key=f"save_yr_{clave_actual}")
            anio_corto_guardado = str(anio_guardado)[-2:]

            if st.button("📤 Guardar en Drive", type="primary", use_container_width=True, disabled=error_critico):
                def df_to_records(df):
                    if df.empty:
                        return []
                    return df.astype(object).where(pd.notnull(df), None).to_dict('records')

                diccionario_balance = {
                    "configuracion": {
                        "rr_val": rr_val, "PME": PME,
                        "periodo_dvs": {"a_base": a_base, "a_tope": a_tope},
                        "otras_salidas": {"Ssb": val_ssb, "Dfb": val_dfb, "Dm": val_dm},
                        "dnc_params": {"p_etr": p_etr, "p_sh": p_sh, "p_ssb": p_ssb, "p_dfb": p_dfb, "p_dm": p_dm},
                        "p_ri": p_ri, "fuente_b": fuente_b, "anio_b": anio_b
                    },
                    "resultados": {
                        "Rv": val_rv_calc, "Ri": val_ri_calc, "Recarga_Total": Recarga_Total,
                        "B_total": bombeo_calc, "DNC_total": dnc_total_calc, "VEAS": veas_calc,
                        "DVS": dvs_anualizado, "ETR": etr_acumulado, "Disponibilidad_Oficial": Disponibilidad
                    },
                    "tablas": {
                        "eh": df_to_records(st.session_state.table_eh),
                        "usos": df_to_records(st.session_state.table_usos),
                        "sh": df_to_records(st.session_state.table_sh),
                        "etr": df_to_records(st.session_state.table_etr),
                        "dvs": df_to_records(st.session_state.table_dvs),
                        "eas": df_to_records(st.session_state.table_eas),
                    }
                }
                with st.spinner("☁️ Subiendo a Drive..."):
                    if guardar_balance_drive(clave_actual, nombre_actual, diccionario_balance, anio_corto_guardado):
                        import time
                        st.success("✅ ¡Guardado exitoso!")
                        time.sleep(2)
                        st.session_state.pop("lista_archivos_nube", None)
                        st.session_state.pop("last_clave_cache", None)
                        st.rerun()

# Desactivar bandera de auto-cálculo para que no se repita en la siguiente interacción
st.session_state["auto_calc"] = False
