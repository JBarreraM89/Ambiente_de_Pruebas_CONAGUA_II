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
import zipfile
from openai import OpenAI
from utils.styles import inyectar_css_oficial, banner_institucional

inyectar_css_oficial()
banner_institucional()

st.subheader("🤖 Analista Estadístico e Hidrogeológico Virtual")
st.caption("Consultas especializadas con rigor técnico (NOM-011-CONAGUA-2015), análisis SQL en memoria y visualización avanzada.")

# ==========================================
# 0. BOTÓN DE LIMPIEZA Y MEMORIA
# ==========================================
if "ui_history_groq" not in st.session_state:
    st.session_state.ui_history_groq = [{
        "role": "assistant", 
        "content": "¡Hola! Soy tu Analista Hidrogeológico y Estadístico Oficial. Puedo ejecutar **consultas analíticas nacionales en SQL**, generar **gráficos avanzados**, realizar **consultas normativas y conceptuales (NOM-011)** o **auditar expedientes técnicos** celda por celda. ¿Qué deseas analizar hoy?"
    }]

col_vacia, col_btn = st.columns([0.8, 0.2])
if col_btn.button("🧹 Limpiar Chat"):
    st.session_state.ui_history_groq = [{
        "role": "assistant", 
        "content": "¡Hola! Memoria limpiada. ¿Qué consulta o análisis deseas realizar hoy?"
    }]
    st.rerun()

# ==========================================
# 1. CONFIGURACIÓN DE IA DE ALTA PRECISIÓN (GROQ)
# ==========================================
api_key = st.secrets.get("GROQ_API_KEY", None)

if not api_key:
    st.error("❌ No se encontró la API Key de Groq en los secretos (.streamlit/secrets.toml).")
    st.stop()

cliente_ia = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

@st.cache_resource(show_spinner="Verificando servidor de IA de alta precisión...")
def obtener_modelo_activo():
    try:
        lista_cruda = cliente_ia.models.list().data
        candidatos = [
            m.id for m in lista_cruda 
            if "whisper" not in m.id.lower() 
            and "guard" not in m.id.lower() 
            and "vision" not in m.id.lower() 
            and "embed" not in m.id.lower()
            and "safeguard" not in m.id.lower()
            and "orpheus" not in m.id.lower()
        ]
        
        # Priorizar modelos de mayor capacidad de razonamiento
        def ranking_modelo(mid):
            m = mid.lower()
            if "120b" in m: return 0
            if "70b" in m: return 1
            if "llama-3.3" in m: return 2
            if "qwen" in m and "27b" in m: return 3
            if "27b" in m: return 4
            if "20b" in m: return 5
            if "llama-3.1" in m and "8b" in m: return 6
            if "8b" in m: return 7
            return 8

        candidatos.sort(key=ranking_modelo)
        for modelo_test in candidatos:
            try:
                cliente_ia.chat.completions.create(
                    model=modelo_test,
                    messages=[{"role": "user", "content": "1"}],
                    max_tokens=2
                )
                return modelo_test
            except Exception:
                continue
    except Exception:
        pass
    return "openai/gpt-oss-120b"

MODELO = obtener_modelo_activo()
st.caption(f"🟢 **Motor analítico activo:** `{MODELO}`")

# ==========================================
# 2. CARGA DE DATOS MULTI-TABLA (En Memoria y Resiliente)
# ==========================================
def cargar_datos_para_ia():
    df_actual = pd.DataFrame()
    
    # 1. Intentar desde st.session_state (en memoria)
    if "datos_reporte_nacional" in st.session_state:
        datos_crudos = st.session_state["datos_reporte_nacional"].get("datos_maestros", [])
        if datos_crudos:
            try:
                from core.data_loader import cargar_catalogo
                df_ram = pd.DataFrame(datos_crudos)
                df_cat = cargar_catalogo("Acuiferos_2026.csv")
                if not df_cat.empty:
                    if 'ESTADO' not in df_ram.columns or df_ram['ESTADO'].isna().all():
                        df_ram = df_ram.merge(df_cat[['CLAVE_SIGM', 'ESTADO']], left_on='Clave', right_on='CLAVE_SIGM', how='left')
                        df_ram['ESTADO'] = df_ram['ESTADO'].fillna('DESCONOCIDO')
                df_actual = df_ram
            except Exception:
                df_actual = pd.DataFrame(datos_crudos)

    # 2. Si está vacío, buscar archivo Excel suelto en temp_balances_oficial
    if df_actual.empty:
        carpeta_base = "temp_balances_oficial"
        if os.path.exists(carpeta_base):
            for root, dirs, files in os.walk(carpeta_base):
                for file in files:
                    if file.startswith("00_Resumen_Nacional") and file.endswith(".xlsx"):
                        try:
                            df_actual = pd.read_excel(os.path.join(root, file))
                            if not df_actual.empty:
                                break
                        except Exception:
                            pass
                if not df_actual.empty:
                    break

    # 3. Si sigue vacío, buscar dentro de paquetes ZIP generados
    if df_actual.empty:
        carpeta_base = "temp_balances_oficial"
        if os.path.exists(carpeta_base):
            for root, dirs, files in os.walk(carpeta_base):
                for file in files:
                    if file.endswith(".zip"):
                        try:
                            ruta_zip = os.path.join(root, file)
                            with zipfile.ZipFile(ruta_zip, 'r') as z:
                                resumenes = [f for f in z.namelist() if "00_Resumen_Nacional" in f and f.endswith(".xlsx")]
                                if resumenes:
                                    with z.open(resumenes[0]) as arch_excel:
                                        df_actual = pd.read_excel(arch_excel)
                                        if not df_actual.empty:
                                            break
                        except Exception:
                            pass
                if not df_actual.empty:
                    break

    if df_actual.empty:
        st.warning("⚠️ Base de datos no encontrada en memoria ni en temporales. Ve a 'Reportes' y da clic en 'Escanear Drive y Generar Reporte' primero.")
        st.stop()

    df_hist = pd.DataFrame()
    try:
        from core.data_loader import CARPETA_DATOS
        ruta_hist = CARPETA_DATOS / "DMA_VEAS.xlsx"
        if ruta_hist.exists():
            df_hist = pd.read_excel(ruta_hist)
    except Exception:
        pass

    return df_actual, df_hist

df_maestro, df_historico = cargar_datos_para_ia()

# ==========================================
# 3. ETL EN TIEMPO REAL (Sanitización global)
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

# PREPARAR TABLA MAESTRA (Actual)
df_maestro = df_maestro.replace(["N/D", "nan", "NaN", "None", ""], np.nan)
df_maestro.columns = [limpiar_columna(c) for c in df_maestro.columns]

# Normalizar nombre de columna de Acuífero
for c in list(df_maestro.columns):
    if c.lower() in ['acuifero', 'acufero', 'nombre']:
        df_maestro.rename(columns={c: 'Acuifero'}, inplace=True)
        break

for col_str in df_maestro.select_dtypes(include=['object', 'string']).columns:
    if col_str != 'ruta_fisica': 
        df_maestro[col_str] = df_maestro[col_str].apply(limpiar_texto_extremo)

for col in df_maestro.columns:
    if col not in ["Clave", "ESTADO", "Acuifero", "ruta_fisica"]:
        df_maestro[col] = pd.to_numeric(df_maestro[col], errors='coerce')

if 'Clave' in df_maestro.columns:
    df_maestro['Clave'] = df_maestro['Clave'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(4)

lista_columnas_reales = ", ".join(df_maestro.columns)

# PREPARAR TABLA HISTÓRICA
lista_cols_historicas = "NO DISPONIBLE. EL USUARIO NO ACTIVÓ LA COMPARATIVA."
if not df_historico.empty:
    df_historico = df_historico.replace(["N/D", "nan", "NaN", "None", ""], np.nan)
    df_historico.columns = [limpiar_columna(c) for c in df_historico.columns]
    if 'CLAVE' in df_historico.columns:
        df_historico['CLAVE'] = df_historico['CLAVE'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(4)
    elif 'Clave' in df_historico.columns:
        df_historico['CLAVE'] = df_historico['Clave'].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(4)
        
    for col in df_historico.columns:
        if col not in ["CLAVE", "ESTADO", "ACUIFERO", "Acuifero"]:
            df_historico[col] = pd.to_numeric(df_historico[col], errors='coerce')
            
    lista_cols_historicas = ", ".join(df_historico.columns)
    instruccion_historica = "Para comparar el año actual con un año histórico, une ambas tablas usando: `m.Clave = h.CLAVE`."
else:
    instruccion_historica = "PROHIBIDO usar df_historico y PROHIBIDO usar JOINs. La tabla histórica no está cargada. Si piden comparativas históricas no disponibles, indícalo claramente."

# ==========================================
# 4. INSTRUCCIONES ESTRICTAS (PROMPT ENGINEERING TÉCNICO)
# ==========================================
instrucciones_sistema = f"""
Eres el Analista Hídrico y Estadístico Senior de la Comisión Nacional del Agua (CONAGUA), especialista en la NOM-011-CONAGUA-2015.
Tu función es proporcionar respuestas altamente certeras, concisas, directas y fundamentadas técnica y numéricamente. NO divagues, no uses rodeos innecesarios ni frases de relleno.

[1. ESQUEMAS DE BASE DE DATOS (DUCKDB EN MEMORIA)]
TABLA 1: `df_maestro` (Evaluación Actual Nacional).
Columnas disponibles: {lista_columnas_reales}

SEMÁNTICA OFICIAL DE COLUMNAS (NOM-011-CONAGUA-2015):
- Clave: Clave oficial de 4 dígitos del acuífero (ej: '0101').
- Acuifero: Nombre oficial del acuífero (MAYÚSCULAS sin acentos).
- ESTADO: Entidad federativa (MAYÚSCULAS sin acentos, ej: 'GUANAJUATO', 'SONORA').
- Disponibilidad_DMA: Disponibilidad Media Anual (hm³/año).
  * Si Disponibilidad_DMA < 0: Representa DÉFICIT.
  * Si Disponibilidad_DMA > 0: Representa DISPONIBILIDAD FAVORABLE (Superávit).
- Recarga_R: Recarga Total Media Anual (hm³/año). Ecuación: R = Rv + Rr + Eh + Ri.
- Rv: Recarga vertical natural (hm³/año).
- Ri: Recarga inducida por retornos de riego y pérdidas de red (hm³/año).
- Rr: Recarga por riego superficial (hm³/año).
- Eh: Entradas por flujo subterráneo horizontal (hm³/año).
- Eas: Entradas de agua salobre / marina (hm³/año).
- Bombeo_B: Extracción total por bombeo real (hm³/año).
- Sh: Salidas por flujo subterráneo horizontal (hm³/año).
- ETR: Evapotranspiración real del manto freático (hm³/año).
- Ssb: Salidas subterráneas hacia el mar / aguas salobres (hm³/año).
- DNC: Descarga Natural Comprometida para la conservación ecológica (hm³/año).
- VEAS: Volumen de Extracción de Aguas Subterráneas concesionado e inscrito en el REPDA (hm³/año).
- Delta_VS: Cambio de almacenamiento del acuífero (hm³/año).
- PME: Profundidad media del agua al nivel estático (metros).
- Usos concesionados (hm³/año): Uso_Agricola, Uso_Publico_Urbano, Uso_Industrial, Uso_Pecuario, Uso_Domestico, Uso_Servicios, Uso_Acuacultura, Uso_Agroindustrial, etc.

TABLA 2: `df_historico` (Datos Oficiales Históricos).
Columnas: {lista_cols_historicas}

[2. REGLAS CONCEPTUALES INQUEBRANTABLES]
- DÉFICIT: Se calcula EXCLUSIVAMENTE con `Disponibilidad_DMA < 0`. El déficit más grave o peor es el más negativo (usa `ORDER BY Disponibilidad_DMA ASC`).
- SUPERÁVIT / DISPONIBILIDAD: Se calcula con `Disponibilidad_DMA > 0` (`ORDER BY Disponibilidad_DMA DESC`).
- VOLUMEN CONCESIONADO (REPDA): Es `VEAS`.
- BOMBEO / EXTRACCIÓN REAL: Es `Bombeo_B`.
- COMPARATIVAS HISTÓRICAS: {instruccion_historica}

[3. REGIONES GEOGRÁFICAS DE MÉXICO]
- NOROESTE: ESTADO IN ('BAJA CALIFORNIA', 'BAJA CALIFORNIA SUR', 'SONORA', 'SINALOA')
- NORTE: ESTADO IN ('CHIHUAHUA', 'COAHUILA', 'DURANGO', 'ZACATECAS', 'SAN LUIS POTOSI')
- NORESTE: ESTADO IN ('NUEVO LEON', 'TAMAULIPAS')
- OCCIDENTE: ESTADO IN ('NAYARIT', 'JALISCO', 'COLIMA', 'MICHOACAN')
- BAJIO / CENTRO-NORTE: ESTADO IN ('GUANAJUATO', 'QUERETARO', 'AGUASCALIENTES', 'SAN LUIS POTOSI')
- CENTRO: ESTADO IN ('CIUDAD DE MEXICO', 'ESTADO DE MEXICO', 'HIDALGO', 'PUEBLA', 'TLAXCALA', 'MORELOS')
- SUR / SURESTE: ESTADO IN ('GUERRERO', 'OAXACA', 'CHIAPAS', 'VERACRUZ', 'TABASCO')
- PENINSULA DE YUCATAN: ESTADO IN ('CAMPECHE', 'YUCATAN', 'QUINTANA ROO')
- Si el usuario dice 'Norte', abarca NOROESTE, NORTE y NORESTE.
- Si el usuario dice 'Sur', abarca SUR / SURESTE y PENINSULA DE YUCATAN.
- Siempre busca texto con `LIKE '%TEXTO%'` en mayúsculas sin acentos.

[4. REGLAS SQL (DUCKDB)]
- Consultas de solo lectura (SELECT).
- Alias claros y sin espacios (ej: SUM(VEAS) AS Concesiones_Total).
- Respeta los límites que pida el usuario (Top 5, Top 10, Top 20). Si pide análisis por estado a nivel nacional, NO uses LIMIT 15, muestra los 32 estados.
- NUNCA uses comillas tipográficas en el SQL.

[5. ENRUTAMIENTO Y ACCIONES]
- "sql": Para cálculos, estadísticas, rankings, agrupaciones y gráficos de la base de datos.
- "leer_expediente": Cuando el usuario solicite abrir, revisar o auditar un acuífero específico por clave o nombre (ej: 'abre el expediente 0101', 'audita el acuífero de Aguascalientes').
- "conceptual": Cuando el usuario haga una pregunta conceptual, normativa (NOM-011), metodológica o teórica (ej: '¿Cómo se define el DMA?', '¿Qué es la DNC?').

[6. FORMATO DE RESPUESTA OBLIGATORIO (JSON PURO)]
Debes responder ÚNICAMENTE con un JSON válido con esta estructura exacta:
{{
  "accion": "sql" | "leer_expediente" | "conceptual",
  "clave_acuifero": "0101",
  "sql_query": "SELECT m.Acuifero, m.Disponibilidad_DMA AS DMA FROM df_maestro m WHERE m.Disponibilidad_DMA < 0 ORDER BY m.Disponibilidad_DMA ASC LIMIT 10",
  "mensaje_usuario": "Resumen directo y técnico del resultado (sin divagar).",
  "grafico": {{
    "necesita_grafico": true,
    "tipo": "barras" | "pastel" | "lineas" | "dispersion",
    "titulo": "Título formal del gráfico",
    "columna_x": "Acuifero",
    "columna_y": "DMA"
  }}
}}
Si no requiere gráfico o la acción es conceptual, coloca "necesita_grafico": false.
"""

# ==========================================
# 5. MOTOR DE INTERFAZ, SQL Y RENDERIZADO
# ==========================================
for msg in st.session_state.ui_history_groq:
    with st.chat_message(msg["role"], avatar="🤖" if msg["role"] == "assistant" else "👤"):
        if "content" in msg and msg["content"]:
            st.markdown(msg["content"])
        if "dataframe" in msg:
            st.dataframe(msg["dataframe"], use_container_width=True, hide_index=True)
        if "figura" in msg:
            st.plotly_chart(msg["figura"], use_container_width=True)

if prompt := st.chat_input("Ej: Top 10 acuíferos con peor déficit, Concesiones por Estado, o Abre el expediente 0101"):
    st.session_state.ui_history_groq.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Procesando consulta especializada..."):
            try:
                mensajes_ia = [{"role": "system", "content": instrucciones_sistema}]
                historial_reciente = st.session_state.ui_history_groq[-6:]
                
                for m in historial_reciente:
                    if "content" in m:
                        mensajes_ia.append({"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]})
                
                # Ejecución con intento de JSON estructurado
                kwargs_ia = {
                    "model": MODELO,
                    "messages": mensajes_ia,
                    "temperature": 0.0
                }
                try:
                    response = cliente_ia.chat.completions.create(
                        **kwargs_ia,
                        response_format={"type": "json_object"}
                    )
                except Exception:
                    response = cliente_ia.chat.completions.create(**kwargs_ia)
                
                respuesta_texto = response.choices[0].message.content.strip()
                
                # Decodificación resiliente de JSON
                datos_ia = None
                try:
                    datos_ia = json.loads(respuesta_texto)
                except Exception:
                    match_md = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", respuesta_texto, re.DOTALL)
                    if match_md:
                        try: datos_ia = json.loads(match_md.group(1))
                        except Exception: pass
                    if not datos_ia:
                        inicio = respuesta_texto.find('{')
                        fin = respuesta_texto.rfind('}')
                        if inicio != -1 and fin != -1 and fin > inicio:
                            try: datos_ia = json.loads(respuesta_texto[inicio:fin + 1])
                            except Exception: pass

                if not datos_ia:
                    # Si no es JSON, se interpreta como respuesta conceptual directa
                    datos_ia = {
                        "accion": "conceptual",
                        "mensaje_usuario": respuesta_texto,
                        "grafico": {"necesita_grafico": False}
                    }
                    
                accion = datos_ia.get("accion", "sql")
                mensaje = datos_ia.get("mensaje_usuario", "Aquí tienes la información solicitada:")

                # ==========================================
                # ACCIÓN 1: RESPUESTA CONCEPTUAL / NORMATIVA
                # ==========================================
                if accion == "conceptual":
                    st.markdown(mensaje)
                    st.session_state.ui_history_groq.append({"role": "assistant", "content": mensaje})

                # ==========================================
                # ACCIÓN 2: LEER EXPEDIENTE TÉCNICO
                # ==========================================
                elif accion == "leer_expediente":
                    clave_req = str(datos_ia.get("clave_acuifero", "")).strip().zfill(4)
                    st.info(f"📂 Consultando expediente técnico del Acuífero {clave_req}...")
                    
                    df_filtro = df_maestro[df_maestro['Clave'].astype(str) == clave_req]
                    if df_filtro.empty:
                        nom_busqueda = limpiar_texto_extremo(datos_ia.get("clave_acuifero", ""))
                        df_filtro = df_maestro[df_maestro['Acuifero'].str.contains(nom_busqueda, na=False)]
                        if not df_filtro.empty:
                            clave_req = str(df_filtro.iloc[0]['Clave']).zfill(4)
                    
                    if not df_filtro.empty:
                        fila_info = df_filtro.iloc[0].to_dict()
                        ruta_fisica = fila_info.get('ruta_fisica', '')
                        archivo_crudo = None

                        # Búsqueda en ruta física
                        if ruta_fisica and os.path.exists(str(ruta_fisica)):
                            try:
                                with open(ruta_fisica, 'r', encoding='utf-8') as f:
                                    archivo_crudo = json.load(f)
                            except Exception:
                                archivo_crudo = None

                        # Búsqueda alternativa en temporales
                        if not archivo_crudo:
                            carpeta_base = "temp_balances_oficial"
                            if os.path.exists(carpeta_base):
                                for root, dirs, files in os.walk(carpeta_base):
                                    for f in files:
                                        if f.startswith(f"{clave_req}_") and f.endswith(".json"):
                                            try:
                                                with open(os.path.join(root, f), 'r', encoding='utf-8') as jf:
                                                    archivo_crudo = json.load(jf)
                                                    break
                                            except Exception:
                                                pass
                                    if archivo_crudo:
                                        break

                        resumen_seguro = {
                            "Clave": clave_req,
                            "Acuífero": fila_info.get("Acuifero", "N/D"),
                            "Estado": fila_info.get("ESTADO", "N/D"),
                            "Balance_Oficial": {k: v for k, v in fila_info.items() if k not in ["ruta_fisica", "Clave", "Acuifero", "ESTADO"] and pd.notna(v)}
                        }
                        if archivo_crudo:
                            if "resultados" in archivo_crudo:
                                resumen_seguro["Resultados_Detallados"] = archivo_crudo["resultados"]
                            if "configuracion" in archivo_crudo:
                                resumen_seguro["Parametros_Configuracion"] = archivo_crudo["configuracion"]
                            if "tablas" in archivo_crudo and "usos" in archivo_crudo["tablas"]:
                                resumen_seguro["Detalle_Usos"] = archivo_crudo["tablas"]["usos"]

                        prompt_auditor = (
                            f"El usuario solicitó auditar o consultar el expediente del acuífero {clave_req} ('{fila_info.get('Acuifero', '')}').\n"
                            f"Pregunta original: '{prompt}'.\n"
                            f"Datos del expediente:\n{json.dumps(resumen_seguro, default=str, ensure_ascii=False)}\n\n"
                            "Instrucciones:\n"
                            "- Responde en lenguaje técnico hidrogeológico oficial (NOM-011-CONAGUA-2015).\n"
                            "- Sé directo, certero, numérico y analítico. NO divagues ni uses rodeos.\n"
                            "- No respondas en JSON, responde en markdown técnico bien formateado."
                        )

                        resp_auditor = cliente_ia.chat.completions.create(
                            model=MODELO,
                            messages=[
                                {"role": "system", "content": "Eres un auditor técnico senior de CONAGUA. Responde con lenguaje técnico claro y riguroso. NO uses formato JSON."},
                                {"role": "user", "content": prompt_auditor}
                            ],
                            temperature=0.1
                        )
                        texto_final = resp_auditor.choices[0].message.content
                        st.markdown(texto_final)
                        st.session_state.ui_history_groq.append({"role": "assistant", "content": texto_final})
                    else:
                        st.error(f"No se encontró el acuífero {clave_req} en la base de datos nacional.")

                # ==========================================
                # ACCIÓN 3: CONSULTA SQL Y GRÁFICOS
                # ==========================================
                else:
                    st.markdown(mensaje)
                    msg_memoria = {"role": "assistant", "content": mensaje}

                    query_sql = str(datos_ia.get("sql_query") or "").strip()
                    
                    if not query_sql or query_sql.lower() == "null":
                        st.stop()
                        
                    if any(cmd in query_sql.upper() for cmd in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]):
                        st.error("❌ Operación denegada. Solo se permiten consultas de lectura.")
                        st.stop()

                    try:
                        con = duckdb.connect(database=':memory:')
                        con.execute("PRAGMA memory_limit='500MB'")
                        con.register('df_maestro', df_maestro)
                        if not df_historico.empty:
                            con.register('df_historico', df_historico)
                            
                        df_resultado = con.execute(query_sql).df()
                        con.close()
                    except Exception as e_sql:
                        st.error(f"❌ Error al ejecutar SQL en DuckDB:\n`{query_sql}`")
                        with st.expander("Ver detalle técnico"):
                            st.code(str(e_sql))
                        st.stop()

                    info_grafico = datos_ia.get("grafico", {})
                    
                    if info_grafico.get("necesita_grafico") and not df_resultado.empty:
                        tipo = str(info_grafico.get("tipo", "barras")).lower()
                        cx = info_grafico.get("columna_x")
                        cy = info_grafico.get("columna_y")
                        tit = info_grafico.get("titulo", "Resultado de Consulta")
                        
                        try:
                            # Sanitización de columnas
                            if isinstance(cy, str):
                                if cy.startswith("[") and cy.endswith("]"):
                                    cy = cy.strip("[]").replace("'", "").replace('"', "")
                                    cy = [c.strip() for c in cy.split(",")]
                                elif "," in cy:
                                    cy = [c.strip() for c in cy.split(",")]
                            if isinstance(cy, list) and len(cy) == 1:
                                cy = cy[0]

                            cols_reales = list(df_resultado.columns)
                            if isinstance(cy, list):
                                cy = [c for c in cy if c in cols_reales]
                                if not cy: raise ValueError("Ninguna columna Y válida en el DataFrame")
                            else:
                                if cy not in cols_reales:
                                    num_cols = df_resultado.select_dtypes(include=np.number).columns.tolist()
                                    cy = num_cols[0] if num_cols else cols_reales[-1]
                            
                            if cx not in cols_reales:
                                cat_cols = df_resultado.select_dtypes(include=['object', 'string']).columns.tolist()
                                cx = cat_cols[0] if cat_cols else cols_reales[0]

                            # Renderizado
                            aviso_autocorreccion = None
                            if tipo in ["barras", "barra", "bar"]:
                                fig = px.bar(df_resultado, x=cx, y=cy, title=tit, barmode='group', color_discrete_sequence=px.colors.qualitative.Prism)
                            elif tipo in ["pastel", "pie"]:
                                if isinstance(cy, list) and len(cy) > 1:
                                    aviso_autocorreccion = "💡 **Auto-corrección:** Se adaptó a gráfico de barras (Pastel no soporta múltiples series)."
                                    fig = px.bar(df_resultado, x=cx, y=cy, title=tit, barmode='group', color_discrete_sequence=px.colors.qualitative.Prism)
                                elif (pd.to_numeric(df_resultado[cy], errors='coerce') < 0).any():
                                    aviso_autocorreccion = "💡 **Auto-corrección:** Se adaptó a gráfico de barras (Pastel no soporta valores negativos de déficit)."
                                    fig = px.bar(df_resultado, x=cx, y=cy, title=tit, barmode='group', color_discrete_sequence=px.colors.qualitative.Prism)
                                else:
                                    val_y = cy[0] if isinstance(cy, list) else cy
                                    fig = px.pie(df_resultado, names=cx, values=val_y, title=tit, hole=0.35)
                            elif tipo in ["lineas", "linea", "line"]:
                                fig = px.line(df_resultado, x=cx, y=cy, title=tit, markers=True, color_discrete_sequence=px.colors.qualitative.Prism)
                            else:
                                if isinstance(cy, list):
                                    fig = px.scatter(df_resultado, x=cx, y=cy, title=tit, color_discrete_sequence=px.colors.qualitative.Prism)
                                    fig.update_traces(mode='markers+lines')
                                else:
                                    fig = px.scatter(df_resultado, x=cx, y=cy, title=tit, color_discrete_sequence=["#e74c3c"])
                                
                            if aviso_autocorreccion:
                                st.info(aviso_autocorreccion)
                                msg_memoria["content"] += f"\n\n{aviso_autocorreccion}"

                            st.plotly_chart(fig, use_container_width=True)
                            msg_memoria["figura"] = fig
                            
                        except Exception:
                            st.warning("⚠️ No se pudo renderizar el gráfico, pero aquí tienes los datos exactos:")
                            st.dataframe(df_resultado, use_container_width=True, hide_index=True)
                            msg_memoria["dataframe"] = df_resultado
                    else:
                        st.dataframe(df_resultado, use_container_width=True, hide_index=True)
                        msg_memoria["dataframe"] = df_resultado

                    st.session_state.ui_history_groq.append(msg_memoria)

            except Exception as e:
                import traceback
                st.error(f"Lo siento, ocurrió un error técnico procesando la solicitud: {str(e)}")
                with st.expander("Ver detalle técnico"):
                    st.code(traceback.format_exc(), language="python")
