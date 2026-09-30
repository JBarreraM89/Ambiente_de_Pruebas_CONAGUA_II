# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np   
import plotly.express as px
import duckdb
import os
import json
import re
import unicodedata
from openai import OpenAI
from utils.styles import inyectar_css_oficial, banner_institucional

inyectar_css_oficial()
banner_institucional()

st.subheader("🤖 Analista Hídrico Virtual (Llama-3.1 / Groq)")
st.caption("Consultas ultra-rápidas, seguras y 100% gratuitas a la base de datos nacional.")
col_vacia, col_btn = st.columns([0.8, 0.2])
if col_btn.button("🧹 Limpiar Chat"):
    st.session_state.ui_history_groq = [{
        "role": "assistant", 
        "content": "¡Hola! Memoria limpiada. ¿Qué necesitas investigar hoy?"
    }]
    st.rerun()

# ==========================================
# 0. CONFIGURACIÓN DE IA GRATUITA (GROQ)
# ==========================================
api_key = st.secrets.get("GROQ_API_KEY", None)

if not api_key:
    st.error("❌ No se encontró la API Key de Groq en los secretos (.streamlit/secrets.toml).")
    st.stop()

cliente_ia = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

@st.cache_resource(show_spinner="Buscando un servidor de IA disponible...")
def obtener_modelo_activo():
    try:
        lista_cruda = cliente_ia.models.list().data
        candidatos = [m.id for m in lista_cruda if "whisper" not in m.id.lower() and "guard" not in m.id.lower() and "vision" not in m.id.lower()]
        candidatos.sort(key=lambda x: (
            0 if "llama" in x.lower() and "8b" in x.lower() else 
            1 if "llama" in x.lower() else 
            2 if "gemma" in x.lower() else 3
        ))
        for modelo_test in candidatos:
            try:
                cliente_ia.chat.completions.create(model=modelo_test, messages=[{"role": "user", "content": "1"}], max_tokens=1)
                return modelo_test
            except Exception:
                continue
    except Exception:
        pass
    return "llama-3.1-8b-instant"

MODELO = obtener_modelo_activo()
st.caption(f"🟢 **Conectado al servidor:** `{MODELO}`")

# ==========================================
# 1. CARGA DE DATOS MULTI-TABLA (En Memoria)
# ==========================================
def cargar_datos_para_ia():
    # 1. Cargar datos actuales
    df_actual = pd.DataFrame()
    if "datos_reporte_nacional" in st.session_state:
        datos_crudos = st.session_state["datos_reporte_nacional"].get("datos_maestros", [])
        if datos_crudos:
            try:
                from core.data_loader import cargar_catalogo
                df_ram = pd.DataFrame(datos_crudos)
                df_cat = cargar_catalogo("Acuiferos_2026.csv")
                if not df_cat.empty:
                    df_ram = df_ram.merge(df_cat[['CLAVE_SIGM', 'ESTADO']], left_on='Clave', right_on='CLAVE_SIGM', how='left')
                    df_ram['ESTADO'] = df_ram['ESTADO'].fillna('DESCONOCIDO')
                df_actual = df_ram
            except:
                df_actual = pd.DataFrame(datos_crudos)

    if df_actual.empty:
        carpeta_base = "temp_balances_oficial"
        if os.path.exists(carpeta_base):
            for root, dirs, files in os.walk(carpeta_base):
                for file in files:
                    if file.startswith("00_Resumen_Nacional") and file.endswith(".xlsx"):
                        df_actual = pd.read_excel(os.path.join(root, file))
                        break

    if df_actual.empty:
        st.warning("⚠️ Base de datos no encontrada. Ve a 'Reportes' y da clic en 'Escanear Drive y Generar Reporte' primero.")
        st.stop()

    # 2. Cargar historial completo (DMA_VEAS.xlsx)
    df_hist = pd.DataFrame()
    try:
        from core.data_loader import CARPETA_DATOS
        ruta_hist = CARPETA_DATOS / "DMA_VEAS.xlsx"
        if ruta_hist.exists():
            df_hist = pd.read_excel(ruta_hist)
    except:
        pass

    return df_actual, df_hist

df_maestro, df_historico = cargar_datos_para_ia()

# ==========================================
# ETL EN TIEMPO REAL (Sanitización global)
# ==========================================
def limpiar_columna(col):
    col = ''.join(c for c in unicodedata.normalize('NFD', str(col)) if unicodedata.category(c) != 'Mn')
    col = col.replace('Δ', 'Delta_').replace(' ', '_')
    col = re.sub(r'[^a-zA-Z0-9_]', '', col)
    return re.sub(r'_+', '_', col).strip('_')

def limpiar_texto_extremo(texto):
    if pd.isna(texto): return texto
    t = str(texto).upper()
    t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    return t.strip()

# Preparar tabla MAESTRA (Actual)
df_maestro = df_maestro.replace(["N/D", "nan", "NaN", "None", ""], np.nan)
df_maestro.columns = [limpiar_columna(c) for c in df_maestro.columns]
for col_str in df_maestro.select_dtypes(include=['object', 'string']).columns:
    if col_str != 'ruta_fisica': 
        df_maestro[col_str] = df_maestro[col_str].apply(limpiar_texto_extremo)
        
for col in df_maestro.columns:
    if col not in ["Clave", "ESTADO", "Acuifero", "ruta_fisica"]:
        df_maestro[col] = pd.to_numeric(df_maestro[col], errors='coerce')

# Asegurar Clave para hacer JOIN exacto
df_maestro['Clave'] = df_maestro['Clave'].astype(str).str.replace('.0', '', regex=False).str.zfill(4)
lista_columnas_reales = ", ".join(df_maestro.columns)

# Preparar tabla HISTÓRICA
lista_cols_historicas = "No disponible"
if not df_historico.empty:
    df_historico.columns = [limpiar_columna(c) for c in df_historico.columns]
    # Forzar la clave a String de 4 dígitos para que cruce con df_maestro
    if 'CLAVE' in df_historico.columns:
        df_historico['CLAVE'] = df_historico['CLAVE'].astype(str).str.replace('.0', '', regex=False).str.zfill(4)
    lista_cols_historicas = ", ".join(df_historico.columns)

# ==========================================
# 2. INSTRUCCIONES ESTRICTAS (PROMPT RELACIONAL)
# ==========================================
instrucciones_sistema = f"""
Eres el Analista Hídrico Senior de CONAGUA. Tu función es traducir lenguaje natural a consultas SQL precisas.

[1. ESQUEMAS DE BASE DE DATOS]
Tienes acceso a DOS tablas en memoria:
TABLA 1: `df_maestro` (Datos Actuales/2026). Columnas válidas:
{lista_columnas_reales}

TABLA 2: `df_historico` (Datos del pasado). Columnas válidas (Contiene DMA y VEAS de años anteriores):
{lista_cols_historicas}

[2. DICCIONARIO Y REGLAS DE NEGOCIO]
- "Déficit", "Sobreexplotado" -> `Disponibilidad_DMA < 0`. (El peor déficit es el más negativo, usa ORDER BY ASC).
- "Disponibilidad", "Sano" -> `Disponibilidad_DMA > 0`. (Mayor disponibilidad usa ORDER BY DESC).
- "Tendencia", "Comparativa" o "Años pasados" -> ¡Usa un JOIN! Para comparar el año actual con un año histórico, une ambas tablas usando la columna Clave.
  EJEMPLO SQL DE COMPARATIVA: 
  `SELECT m.Acuifero, m.Disponibilidad_DMA AS DMA_Actual, h.DMA_2020 FROM df_maestro m JOIN df_historico h ON m.Clave = h.CLAVE WHERE m.ESTADO LIKE '%ZACATECAS%'`

[3. TAXONOMÍA GEOGRÁFICA Y BÚSQUEDAS]
- Todo texto está en MAYÚSCULAS Y SIN ACENTOS. Usa `LIKE '%TEXTO%'` (Ej: `ESTADO LIKE '%MEXICO%'`).
- Norte -> ESTADO IN ('BAJA CALIFORNIA', 'BAJA CALIFORNIA SUR', 'SONORA', 'CHIHUAHUA', 'COAHUILA', 'NUEVO LEON', 'TAMAULIPAS', 'SINALOA', 'DURANGO', 'ZACATECAS', 'SAN LUIS POTOSI')
- Sur -> ESTADO IN ('GUERRERO', 'OAXACA', 'CHIAPAS', 'VERACRUZ', 'TABASCO', 'CAMPECHE', 'YUCATAN', 'QUINTANA ROO')
- Centro -> Resto de los estados.

[4. REGLAS DE ORO PARA GRÁFICOS]
- ALIAS ESTRICTOS: Pon alias a las sumas (Ej: `SUM(VEAS) AS Total`).
- LIMIT 15: Si agrupas por estado/acuífero para PASTEL o BARRAS, OBLIGATORIO usar `LIMIT 15`.
- COMPARATIVAS MULTI-AÑO: En el JSON de gráfico, si comparas 2 o más años, "columna_y" DEBE ser una LISTA con los alias exactos (Ej: `["DMA_Actual", "DMA_2020"]`).

[5. ENRUTAMIENTO]
- "sql": Por defecto para análisis numérico y comparativas.
- "leer_expediente": ÚSALO EXCLUSIVAMENTE si piden "abrir expediente" de UN SOLO acuífero para ver detalles internos de celdas.

FORMATO DE RESPUESTA OBLIGATORIO (JSON PURO):
{{
  "accion": "sql" o "leer_expediente",
  "clave_acuifero": "0101",
  "sql_query": "SELECT m.ESTADO, SUM(m.Disponibilidad_DMA) AS DMA_Actual, SUM(h.DMA_2015) AS DMA_2015 FROM df_maestro m JOIN df_historico h ON m.Clave = h.CLAVE GROUP BY m.ESTADO LIMIT 15",
  "mensaje_usuario": "Aquí tienes la comparativa...",
  "grafico": {{
    "necesita_grafico": true,
    "tipo": "barras",
    "titulo": "Comparativa Histórica",
    "columna_x": "ESTADO",
    "columna_y": ["DMA_Actual", "DMA_2015"]
  }}
}}
"""

if "ui_history_groq" not in st.session_state:
    st.session_state.ui_history_groq = [{
        "role": "assistant", 
        "content": "¡Hola! Soy tu Analista Hídrico Virtual. Puedo hacer **consultas nacionales (SQL)** o **abrir expedientes específicos** para revisar cálculos celda por celda. ¿Qué necesitas investigar hoy?"
    }]

# ==========================================
# 3. MOTOR DE INTERFAZ, SQL Y RENDERIZADO
# ==========================================
for msg in st.session_state.ui_history_groq:
    with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
        if "content" in msg and msg["content"]:
            st.markdown(msg["content"])
        if "dataframe" in msg:
            st.dataframe(msg["dataframe"], use_container_width=True, hide_index=True)
        if "figura" in msg:
            st.plotly_chart(msg["figura"], use_container_width=True)

if prompt := st.chat_input("Ej: Compara en barras la disponibilidad de Sonora actual vs la de 2020"):
    st.session_state.ui_history_groq.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Procesando consulta avanzada..."):
            try:
                # OPTIMIZACIÓN DE TOKENS
                mensajes_ia = [{"role": "system", "content": instrucciones_sistema}]
                historial_reciente = st.session_state.ui_history_groq[-4:]
                
                for m in historial_reciente:
                    if "content" in m:
                        mensajes_ia.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
                
                response = cliente_ia.chat.completions.create(
                    model=MODELO,
                    messages=mensajes_ia,
                    temperature=0.0 
                )
                
                respuesta_texto = response.choices[0].message.content
                
                # EXTRACCIÓN INTELIGENTE DE JSON
                match_md = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", respuesta_texto, re.DOTALL)
                if match_md:
                    json_puro = match_md.group(1)
                else:
                    inicio = respuesta_texto.find('{')
                    fin = respuesta_texto.rfind('}')
                    json_puro = respuesta_texto[inicio:fin + 1] if inicio != -1 and fin != -1 else ""

                if not json_puro:
                    st.error("❌ La IA se confundió con el formato. Mira lo que intentó responder:")
                    with st.expander("Ver respuesta cruda de la IA"):
                        st.write(respuesta_texto)
                    st.stop()
                    
                datos_ia = json.loads(json_puro)
                
                accion = datos_ia.get("accion", "sql")
                mensaje = datos_ia.get("mensaje_usuario", "Aquí tienes la información solicitada:")
                
                if accion == "leer_expediente":
                    clave_req = str(datos_ia.get("clave_acuifero", "")).replace('.0', '').zfill(4)
                    st.info(f"📂 Extrayendo archivo físico del expediente técnico: Acuífero {clave_req}...")
                    
                    df_filtro = df_maestro[df_maestro['Clave'].astype(str) == clave_req]
                    
                    if not df_filtro.empty:
                        ruta_fisica = df_filtro.iloc[0].get('ruta_fisica', '')
                        if os.path.exists(ruta_fisica):
                            with open(ruta_fisica, 'r', encoding='utf-8') as f:
                                archivo_crudo = json.load(f)
                            
                            st.info("🧠 Analizando memoria de cálculo celda por celda...")
                            prompt_auditor = f"El usuario preguntó: '{prompt}'. Aquí tienes el expediente JSON del acuífero {clave_req}: {json.dumps(archivo_crudo)[:20000]}. Responde basándote estrictamente en los valores de este archivo sin usar JSON."
                            
                            resp_auditor = cliente_ia.chat.completions.create(
                                model=MODELO,
                                messages=[{"role": "system", "content": "Eres un auditor técnico de CONAGUA."}, {"role": "user", "content": prompt_auditor}],
                                temperature=0.2
                            )
                            texto_final = resp_auditor.choices[0].message.content
                            st.markdown(texto_final)
                            st.session_state.ui_history_groq.append({"role": "assistant", "content": texto_final})
                        else:
                            st.error(f"El archivo físico no se encuentra en el servidor para el acuífero {clave_req}.")
                    else:
                        st.error(f"No se encontró el acuífero {clave_req} en la base de datos.")

                else:
                    st.markdown(mensaje)
                    msg_memoria = {"role": "assistant", "content": mensaje}

                    query_sql = datos_ia.get("sql_query", "")
                    if not query_sql.strip():
                        st.error("❌ La IA no generó una consulta SQL válida.")
                        st.stop()
                        
                    if any(cmd in query_sql.upper() for cmd in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]):
                        st.error("❌ Operación denegada. Solo consultas de lectura.")
                        st.stop()
                        
                    # ========================================================
                    # EJECUCIÓN DIRECTA Y SEGURA (DuckDB Multi-Tabla)
                    # ========================================================
                    try:
                        con = duckdb.connect(database=':memory:')
                        con.register('df_maestro', df_maestro)
                        if not df_historico.empty:
                            con.register('df_historico', df_historico)
                            
                        df_resultado = con.execute(query_sql).df()
                        con.close()
                    except Exception as e:
                        st.error(f"❌ Error en SQL generado por la IA:\n\nConsulta intentada:\n{query_sql}")
                        with st.expander("Ver Traceback de DuckDB"):
                            st.code(str(e))
                        st.stop()

                    info_grafico = datos_ia.get("grafico", {})
                    
                    if info_grafico.get("necesita_grafico") and not df_resultado.empty:
                        tipo = info_grafico.get("tipo")
                        cx = info_grafico.get("columna_x")
                        cy = info_grafico.get("columna_y")
                        tit = info_grafico.get("titulo")
                        
                        try:
                            if tipo == "barras":
                                fig = px.bar(df_resultado, x=cx, y=cy, title=tit, barmode='group', color_discrete_sequence=px.colors.qualitative.Prism)
                            elif tipo == "pastel":
                                val_y = cy[0] if isinstance(cy, list) else cy
                                fig = px.pie(df_resultado, names=cx, values=val_y, title=tit, hole=0.4)
                            else:
                                fig = px.scatter(df_resultado, x=cx, y=cy, title=tit, color_discrete_sequence=px.colors.qualitative.Prism)
                                
                            st.plotly_chart(fig, use_container_width=True)
                            msg_memoria["figura"] = fig
                            
                        except Exception:
                            st.warning("⚠️ No se pudo graficar automáticamente, pero aquí están los datos exactos:")
                            st.dataframe(df_resultado, use_container_width=True, hide_index=True)
                            msg_memoria["dataframe"] = df_resultado
                    else:
                        st.dataframe(df_resultado, use_container_width=True, hide_index=True)
                        msg_memoria["dataframe"] = df_resultado

                    st.session_state.ui_history_groq.append(msg_memoria)

            except Exception as e:
                import traceback
                st.error(f"Lo siento, encontré un error técnico procesando la solicitud: {str(e)}")
                with st.expander("Ver detalle técnico"):
                    st.code(traceback.format_exc(), language="python")