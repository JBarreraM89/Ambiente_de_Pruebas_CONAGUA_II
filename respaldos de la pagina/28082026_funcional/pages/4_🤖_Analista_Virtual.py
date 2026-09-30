# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np   
import plotly.express as px
import duckdb
import os
import json
from openai import OpenAI
from utils.styles import inyectar_css_oficial, banner_institucional

inyectar_css_oficial()
banner_institucional()

st.subheader("🤖 Analista Hídrico Virtual (Llama-3 / Groq)")
st.caption("Consultas ultra-rápidas, seguras y 100% gratuitas a la base de datos nacional.")

# ==========================================
# 0. CONFIGURACIÓN DE IA GRATUITA (GROQ)
# ==========================================
api_key = st.secrets.get("GROQ_API_KEY", None)

if not api_key:
    st.error("❌ No se encontró la API Key de Groq en los secretos (.streamlit/secrets.toml).")
    st.stop()

# Conectamos la librería a los servidores ultra-rápidos de Groq
cliente_ia = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1"
)

# ==========================================
# BÚSQUEDA DINÁMICA MEDIANTE "PING" (100% SEGURO)
# ==========================================
@st.cache_resource(show_spinner="Buscando un servidor de IA disponible...")
def obtener_modelo_activo():
    try:
        # 1. Pedimos todos los modelos de Groq
        lista_cruda = cliente_ia.models.list().data
        
        # 2. Descartamos los que sabemos que no sirven para chat
        candidatos = [m.id for m in lista_cruda if "whisper" not in m.id.lower() and "guard" not in m.id.lower() and "vision" not in m.id.lower()]
        
        # 3. Ordenamos: Preferimos los modelos "8b" (Ligeros, gratuitos y rápidos)
        candidatos.sort(key=lambda x: (
            0 if "llama" in x.lower() and "8b" in x.lower() else 
            1 if "llama" in x.lower() else 
            2 if "gemma" in x.lower() else 3
        ))
        
        # 4. PRUEBA DE FUEGO: Les mandamos un mensaje de 1 token. El primero que responda, gana.
        for modelo_test in candidatos:
            try:
                cliente_ia.chat.completions.create(
                    model=modelo_test,
                    messages=[{"role": "user", "content": "1"}],
                    max_tokens=1
                )
                return modelo_test # ¡Encontramos uno vivo y con permisos!
            except Exception:
                continue # Si está apagado o no hay permisos, probamos el siguiente
                
    except Exception:
        pass
    
    # Si todo falla horriblemente, devolvemos el último estándar conocido
    return "llama-3.1-8b-instant"

MODELO = obtener_modelo_activo()

# Mostrar en pantalla el modelo real conectado
st.caption(f"🟢 **Conectado al servidor:** `{MODELO}`")

# ==========================================
# 1. CARGA DE DATOS (En Memoria o Disco)
# ==========================================
def cargar_datos_para_ia():
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
                return df_ram
            except:
                return pd.DataFrame(datos_crudos)

    carpeta_base = "temp_balances_oficial"
    if os.path.exists(carpeta_base):
        for root, dirs, files in os.walk(carpeta_base):
            for file in files:
                if file.startswith("00_Resumen_Nacional") and file.endswith(".xlsx"):
                    return pd.read_excel(os.path.join(root, file))
    return pd.DataFrame()

df_maestro = cargar_datos_para_ia()

if df_maestro.empty:
    st.warning("⚠️ Base de datos no encontrada. Ve a 'Reportes' y da clic en 'Escanear Drive y Generar Reporte' primero.")
    st.stop()

df_maestro = df_maestro.replace(["N/D", "nan", "NaN", "None", ""], np.nan)

# ==========================================
# 2. INSTRUCCIONES ESTRICTAS (JSON MODE)
# ==========================================
# ==========================================
# 2. INSTRUCCIONES ESTRICTAS (JSON MODE)
# ==========================================
instrucciones_sistema = """
Eres el Analista Hídrico en Jefe de CONAGUA.
Tienes acceso a la tabla SQL 'df_maestro' con: "Clave", "ESTADO", "Acuifero", "Recarga", "Bombeo", "DNC", "VEAS", "DVS", "DMA".

REGLA DE ORO: TU RESPUESTA DEBE SER ÚNICA Y EXCLUSIVAMENTE UN OBJETO JSON VÁLIDO. 
NO escribas saludos ni texto fuera del JSON. Si te piden gráficos de pastel con muchos datos, AGRUPA por ESTADO usando SUM() y LIMIT 15 para que la gráfica no colapse.

Estructura obligatoria:
{
  "sql_query": "SELECT ESTADO, SUM(DMA) as DMA_Total FROM df_maestro WHERE DMA > 0 GROUP BY ESTADO ORDER BY DMA_Total DESC LIMIT 15",
  "mensaje_usuario": "Mensaje amable explicando qué mostrarás.",
  "grafico": {
    "necesita_grafico": true,
    "tipo": "pastel",
    "titulo": "Acuíferos con Disponibilidad por Estado",
    "columna_x": "ESTADO",
    "columna_y": "DMA_Total"
  }
}
"""

# ==========================================
# 3. MOTOR DE INTERFAZ, SQL Y RENDERIZADO
# ==========================================
# Mostrar el historial
for msg in st.session_state.ui_history_groq:
    with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
        if "content" in msg and msg["content"]:
            st.markdown(msg["content"])
        if "dataframe" in msg:
            st.dataframe(msg["dataframe"], use_container_width=True, hide_index=True)
        if "figura" in msg:
            st.plotly_chart(msg["figura"], use_container_width=True)

# Capturar pregunta
if prompt := st.chat_input("Ej: Muestra un gráfico de pastel con el bombeo total (B) de Nuevo León"):
    st.session_state.ui_history_groq.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Llama-3 procesando consulta a velocidad de la luz..."):
            try:
                # Armamos el historial para que Llama-3 entienda el contexto
                mensajes_ia = [{"role": "system", "content": instrucciones_sistema}]
                for m in st.session_state.ui_history_groq:
                    # Llama-3 solo acepta texto en el historial
                    if "content" in m:
                        mensajes_ia.append({"role": m["role"], "content": m["content"]})
                
                # Petición a Groq (One-Shot obligando formato JSON)
                response = cliente_ia.chat.completions.create(
                    model=MODELO,
                    messages=mensajes_ia,
                    temperature=0.1
                )
                
                respuesta_texto = response.choices[0].message.content
                
                # --- NUEVO: EXTRACCIÓN INTELIGENTE DE JSON ---
                import re
                datos_ia = None
                
                # 1. Buscar si la IA lo metió en un bloque markdown (```json ... ```)
                match_md = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", respuesta_texto, re.DOTALL)
                if match_md:
                    json_puro = match_md.group(1)
                else:
                    # 2. Si no hay markdown, aislar usando las llaves
                    inicio = respuesta_texto.find('{')
                    fin = respuesta_texto.rfind('}')
                    if inicio != -1 and fin != -1:
                        json_puro = respuesta_texto[inicio:fin + 1]
                    else:
                        json_puro = ""

                try:
                    if json_puro:
                        datos_ia = json.loads(json_puro)
                    else:
                        raise ValueError("No se encontraron llaves de JSON.")
                except Exception as e:
                    # Si la IA falló por completo, mostramos qué intentó decir para no quedarnos a ciegas
                    st.error("❌ La IA se confundió con el formato. Mira lo que intentó responder:")
                    with st.expander("Ver respuesta cruda de la IA"):
                        st.write(respuesta_texto)
                        st.code(str(e))
                    st.stop()
                # ---------------------------------------------
                
                # Mostrar el mensaje amable que redactó la IA
                mensaje = datos_ia.get("mensaje_usuario", "Aquí tienes los datos solicitados:")
                st.markdown(mensaje)
                msg_memoria = {"role": "assistant", "content": mensaje}

                # Ejecutar el SQL de forma segura
                query_sql = datos_ia.get("sql_query", "")
                
                if any(cmd in query_sql.upper() for cmd in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]):
                    st.error("❌ Operación denegada. Solo se permiten consultas de lectura.")
                    st.stop()
                    
                query_sql = datos_ia.get("sql_query", "")
                
                if any(cmd in query_sql.upper() for cmd in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]):
                    st.error("❌ Operación denegada. Solo se permiten consultas de lectura.")
                    st.stop()
                    
                query_sql = datos_ia.get("sql_query", "")
                
                if any(cmd in query_sql.upper() for cmd in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]):
                    st.error("❌ Operación denegada. Solo se permiten consultas de lectura.")
                    st.stop()
                    
                # 👇 --- NUEVO: RENOMBRADO INTELIGENTE (A PRUEBA DE COLUMNAS EXTRA) --- 👇
                df_sql = df_maestro.copy()
                df_sql = df_sql.rename(columns={
                    "Acuífero": "Acuifero",
                    "Recarga (R)": "Recarga",
                    "Bombeo (B)": "Bombeo",
                    "ΔV(S)": "DVS",
                    "Disponibilidad (DMA)": "DMA"
                })
                # 👆 ------------------------------------------------------------------ 👆
                
                con = duckdb.connect(database=':memory:')
                con.register('df_maestro', df_sql)
                
                con = duckdb.connect(database=':memory:')
                con.register('df_maestro', df_sql)
                df_resultado = con.execute(query_sql).df()
                con.close()

                # Revisar si la IA pidió un gráfico
                info_grafico = datos_ia.get("grafico", {})
                
                if info_grafico.get("necesita_grafico") and not df_resultado.empty:
                    tipo = info_grafico.get("tipo")
                    cx = info_grafico.get("columna_x")
                    cy = info_grafico.get("columna_y")
                    tit = info_grafico.get("titulo")
                    
                    try:
                        if tipo == "barras":
                            fig = px.bar(df_resultado, x=cx, y=cy, title=tit, color_discrete_sequence=["#244062"])
                        elif tipo == "pastel":
                            fig = px.pie(df_resultado, names=cx, values=cy, title=tit, hole=0.4)
                        else:
                            fig = px.scatter(df_resultado, x=cx, y=cy, title=tit, color_discrete_sequence=["#e74c3c"])
                            
                        st.plotly_chart(fig, use_container_width=True)
                        msg_memoria["figura"] = fig
                    except Exception as e_graf:
                        st.warning(f"No se pudo graficar automáticamente, pero aquí están los datos:")
                        st.dataframe(df_resultado, use_container_width=True, hide_index=True)
                        msg_memoria["dataframe"] = df_resultado
                else:
                    st.dataframe(df_resultado, use_container_width=True, hide_index=True)
                    msg_memoria["dataframe"] = df_resultado

                st.session_state.ui_history_groq.append(msg_memoria)

            except json.JSONDecodeError:
                st.error("La IA devolvió un formato no válido. Intenta preguntar de otra forma.")
            except Exception as e:
                import traceback
                st.error(f"Lo siento, encontré un error procesando el SQL o los datos: {str(e)}")
                with st.expander("Ver detalle técnico"):
                    st.code(traceback.format_exc(), language="python")