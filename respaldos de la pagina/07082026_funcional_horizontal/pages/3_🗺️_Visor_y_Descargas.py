# -*- coding: utf-8 -*-
import streamlit.components.v1 as components
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from streamlit_folium import st_folium
from difflib import SequenceMatcher
from folium import plugins
import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import requests
import tempfile
import folium
import time
import io
import re

# --- IMPORTACIONES CORE (ARQUITECTURA ENTERPRISE) ---
from core.data_loader import cargar_datos_maestros, cargar_fraccion, cargar_excel, cargar_csv, cargar_parquet, DIRECTORIO_RAIZ
from core.generador_word import (inyectar_tabla_vertices_en_word, inyectar_tabla_flujo_en_word,
                                inyectar_tabla_almacenamiento_en_word, inyectar_tabla_evapotranspiracion_en_word, 
                                modificar_censo_y_bombeo)
from utils.formatters import limpiar_texto, formatear_fecha, procesar_link_drive
from core.estandarizador_acuiferos import ejecutar_estandarizacion_v31

# =======================================================
# 🚀 1. CARGA DE DATOS GLOBAL
# =======================================================
gdf_maestro = cargar_datos_maestros()
with st.spinner("Cargando bases de datos de CONAGUA..."):
    df_repda_global = cargar_excel("REPDA.xlsx", "Clave de acuífero")
    df_aprov_global = cargar_excel("Aprovechamientos.xlsx", "Cve_Acuif")
    df_zonas_global = cargar_excel("ZONAS_DE_DISPONIBILIDAD.xlsx", "CLAVE DEL ACUÍFERO")
    df_vertices_global = cargar_excel("Vertices.xlsx", "ID_ACUIFERO")
    df_enlaces_docs = cargar_csv("Reporte de Enlaces Acuíferos - 5_8_2026 - Hoja 1.csv", "CLAVE_ACUIFERO")
    df_flujo_ent_global = cargar_parquet("Flujo_Horizontal_Entradas.parquet")
    df_flujo_sal_global = cargar_parquet("Flujo_Horizontal_Salidas.parquet")
    df_almacenamiento_global = cargar_parquet("Cambio_Almacenamiento.parquet")
    df_etr_global = cargar_parquet("Evapotranspiracion.parquet")
    df_bal_ent_global = cargar_parquet("Balance_Hidro_Entradas.parquet")
    df_bal_sal_global = cargar_parquet("Balance_Hidro_Salidas.parquet")
    df_bal_alm_global = cargar_parquet("Balance_Hidro_Almacenamiento.parquet")
    df_veas_global = cargar_parquet("VEAS_Administrativo.parquet")
    df_links_global = cargar_csv("Links.csv", "clave")

# =======================================================
# 🎨 2. ENCABEZADO NATIVO E INSTITUCIONAL
# =======================================================
css_optimo = """
<style>
    .block-container { 
        padding-top: 5rem !important; 
        padding-bottom: 1rem !important; 
    }
    
    [data-testid="stHeader"] {
        background-color: rgba(255, 255, 255, 0.95) !important;
        border-bottom: 3px solid #DDC9A3 !important;
        box-shadow: 0px 4px 10px rgba(0,0,0,0.05) !important;
        height: 4.5rem !important;
        z-index: 99999 !important; 
    }
    
    [data-testid="stHeader"]::after {
        content: "💧 Sistema de Consulta de Información para Documentos de Respaldo";
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        color: #691C32;
        font-size: 26px;
        font-weight: bold;
        font-family: 'Segoe UI', sans-serif;
        white-space: nowrap;
        pointer-events: none;
    }

    .stTabs [data-baseweb="tab-list"] { gap: 6px; overflow-x: auto; overflow-y: hidden; white-space: nowrap; padding-bottom: 4px; }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar { height: 4px; }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar-track { background: #f1f1f1; }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar-thumb { background: #98989A; border-radius: 4px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #f1f3f6; border-radius: 6px 6px 0px 0px; padding: 8px 16px;
        border: 1px solid #dcdde1; border-bottom: none; box-shadow: 0px -2px 4px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
    }
    .stTabs [data-baseweb="tab"]:hover { background-color: #DDC9A3; }
    .stTabs [aria-selected="true"] {
        background-color: #ffffff; border-top: 4px solid #9F2241;
        border-left: 1px solid #dcdde1; border-right: 1px solid #dcdde1;
    }
    .stTabs [data-baseweb="tab"] p { font-weight: bold; font-size: 15px; color: #6F7271; margin: 0; }
    .stTabs [aria-selected="true"] p { color: #691C32 !important; }
    
    button[kind="secondary"], button[kind="tertiary"] {
        color: #2980b9 !important; font-weight: 600 !important; padding: 0 !important; margin-top: 5px !important; margin-bottom: 15px !important; background-color: transparent !important; border: none !important; box-shadow: none !important;
    } 
    button[kind="secondary"]:hover, button[kind="tertiary"]:hover {
        color: #9F2241 !important; text-decoration: underline !important; background-color: transparent !important; border: none !important;
    }
    
    div[data-testid="stVerticalBlockBorderWrapper"]:has(#iman-subir-caja) {
        margin-top: 10px !important; 
        padding-top: 12px !important; padding-bottom: 12px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(#iman-subir-caja) button[kind="primary"] {
        font-size: 12px !important; padding: 0.2rem 0.5rem !important; min-height: 2rem !important;
        background-color: #9F2241 !important; color: white !important; border: 1px solid #9F2241 !important;
        transition: background-color 0.3s ease !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(#iman-subir-caja) button[kind="primary"]:hover {
        background-color: #691C32 !important; border-color: #691C32 !important; color: white !important;
    }

    @media (max-width: 991px) { 
        [data-testid="stHeader"]::after { font-size: 16px; left: 60px; transform: translate(0, -50%); }
    }
</style>
"""

st.markdown(css_optimo, unsafe_allow_html=True)
st.subheader("🗺️ Resumen Técnico de consulta")
st.caption("Filtra por estado, selecciona el acuífero y enciende las capas espaciales para visualizar recortes exactos.")

# =======================================================
# ⚙️ 3. FUNCIONES AUXILIARES
# =======================================================
def mostrar_dato(titulo, valor):
    val_limpio = limpiar_texto(valor)
    if val_limpio is None: st.write(f"**{titulo}:** Sin información")
    else: st.write(f"**{titulo}:** {val_limpio}")

def mostrar_pares_vertical(titulo_seccion, nombres, fechas, prefijo_fecha="DOF: "):
    nom_limpio = limpiar_texto(nombres)
    fec_limpia = limpiar_texto(fechas)
    if nom_limpio is None:
        st.write(f"**{titulo_seccion}:** Sin información")
        return
    st.write(f"**{titulo_seccion}:**")
    lista_nombres = nom_limpio.split(' | ')
    if fec_limpia:
        fec_limpia = fec_limpia.replace('[', '').replace(']', '').replace("'", "").replace('"', '')
        if ' | ' in fec_limpia: lista_fechas = [x.strip() for x in fec_limpia.split(' | ')]
        elif ',' in fec_limpia: lista_fechas = [x.strip() for x in fec_limpia.split(',')]
        else: lista_fechas = [fec_limpia.strip()]
    else: lista_fechas = []

    for i, nombre in enumerate(lista_nombres):
        fecha_raw = lista_fechas[i] if i < len(lista_fechas) else "S/F"
        st.markdown(f"*({prefijo_fecha}{formatear_fecha(fecha_raw)})* {nombre}")

def mostrar_pares_en_parrafo(titulo_seccion, nombres, extras, prefijo_extra="", es_fecha=False):
    nom_limpio = limpiar_texto(nombres)
    ext_limpio = limpiar_texto(extras)
    if nom_limpio is None: st.write(f"**{titulo_seccion}:** Sin información")
    else:
        lista_n = nom_limpio.split(' | ')
        if ext_limpio:
            ext_limpio = ext_limpio.replace('[', '').replace(']', '').replace("'", "").replace('"', '')
            if ' | ' in ext_limpio: lista_e = [x.strip() for x in ext_limpio.split(' | ')]
            elif ',' in ext_limpio: lista_e = [x.strip() for x in ext_limpio.split(',')]
            else: lista_e = [ext_limpio.strip()]
        else: lista_e = []

        formateados = []
        for i, nombre in enumerate(lista_n):
            extra_raw = lista_e[i] if i < len(lista_e) else "S/D"
            extra_final = formatear_fecha(extra_raw) if es_fecha else extra_raw
            formateados.append(f"({prefijo_extra}{extra_final}) {nombre}")
        st.write(f"**{titulo_seccion}:** {', '.join(formateados)}")

def mostrar_desde_fraccion_vertical(titulo_seccion, clave_ac, id_capa, campo_nombre, campo_fecha, prefijo_fecha="DOF: ", formato_titulo=False):
    df_capa = cargar_fraccion(id_capa)
    if df_capa is not None:
        fraccion = df_capa[df_capa['CLV_ACUI'] == clave_ac]
        if not fraccion.empty:
            unicos = fraccion.drop_duplicates(subset=[campo_nombre])
            pares = []
            for _, row in unicos.iterrows():
                nom = limpiar_texto(row.get(campo_nombre))
                if formato_titulo and nom: nom = nom.title()
                fec = row.get(campo_fecha)
                if nom:
                    f_limpia = formatear_fecha(fec)
                    try:
                        dt_obj = pd.to_datetime(f_limpia, format='%d/%m/%Y')
                        sk = (0, dt_obj.year, dt_obj.month, dt_obj.day)
                    except: sk = (1, 0, 0, 0)
                    pares.append({"nombre": nom, "fecha": f_limpia, "sk": sk})
            if pares:
                st.write(f"**{titulo_seccion}:**")
                pares = sorted(pares, key=lambda x: (x['sk'], x['nombre']))
                for p in pares: st.markdown(f"*({prefijo_fecha}{p['fecha']})* {p['nombre']}")
                return
    st.write(f"**{titulo_seccion}:** Sin información")

def mostrar_desde_fraccion_en_linea(titulo_seccion, clave_ac, id_capa, campo_nombre, campo_fecha, prefijo_fecha="DOF: ", formato_titulo=False):
    df_capa = cargar_fraccion(id_capa)
    if df_capa is not None:
        fraccion = df_capa[df_capa['CLV_ACUI'] == clave_ac]
        if not fraccion.empty:
            unicos = fraccion.drop_duplicates(subset=[campo_nombre])
            pares = []
            for _, row in unicos.iterrows():
                nom = limpiar_texto(row.get(campo_nombre))
                if formato_titulo and nom: nom = nom.title()
                fec = row.get(campo_fecha)
                if nom:
                    f_limpia = formatear_fecha(fec)
                    pares.append(f"({prefijo_fecha}{f_limpia}) {nom}")
            if pares:
                st.write(f"**{titulo_seccion}:** {', '.join(pares)}")
                return
    st.write(f"**{titulo_seccion}:** Sin información")

def mostrar_municipios_agrupados_y_condicion(clave_ac, str_total, str_parcial):
    def limpiar_acentos(texto):
        if not isinstance(texto, str): return ""
        reemplazos = {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U"}
        for a, b in reemplazos.items(): texto = texto.replace(a, b)
        return texto

    def normalizar_lista(texto_crudo):
        if pd.isna(texto_crudo) or str(texto_crudo).strip() == "": return []
        t = str(texto_crudo).upper()
        for char in ['[', ']', "'", '"']: t = t.replace(char, '')
        for sep in [' | ', '|', ';', '\n']: t = t.replace(sep, ',')
        return [limpiar_acentos(x.strip()) for x in t.split(',') if x.strip()]

    df_mun = cargar_fraccion("municipios")
    if df_mun is not None:
        fraccion = df_mun[df_mun['CLV_ACUI'] == clave_ac]
        if not fraccion.empty and 'CVE_ENT' in fraccion.columns and 'NOMGEO' in fraccion.columns:
            diccionario_estados = {
                "01": "Aguascalientes", "02": "Baja California", "03": "Baja California Sur",
                "04": "Campeche", "05": "Coahuila de Zaragoza", "06": "Colima",
                "07": "Chiapas", "08": "Chihuahua", "09": "Ciudad de México",
                "10": "Durango", "11": "Guanajuato", "12": "Guerrero",
                "13": "Hidalgo", "14": "Jalisco", "15": "México (Estado de México)",
                "16": "Michoacán de Ocampo", "17": "Morelos", "18": "Nayarit",
                "19": "Nuevo León", "20": "Oaxaca", "21": "Puebla",
                "22": "Querétaro", "23": "Quintana Roo", "24": "San Luis Potosí",
                "25": "Sinaloa", "26": "Sonora", "27": "Tabasco",
                "28": "Tamaulipas", "29": "Tlaxcala", "30": "Veracruz de Ignacio de la Llave",
                "31": "Yucatán", "32": "Zacatecas"
            }
            
            lista_totales = normalizar_lista(str_total)
            lista_parciales = normalizar_lista(str_parcial)
            
            st.write("**Municipios del Acuífero:**")
            agrupados = fraccion.groupby('CVE_ENT')
            
            for cve_ent, group in agrupados:
                try: cve_str = str(int(float(cve_ent))).zfill(2)
                except: cve_str = str(cve_ent).zfill(2)
                    
                nombre_estado = diccionario_estados.get(cve_str, f"Estado Desconocido ({cve_str})")
                totales = []
                parciales = []
                
                for m in group['NOMGEO'].dropna().unique().tolist():
                    m_safe = limpiar_acentos(str(m).upper().strip())
                    if m_safe in lista_totales: totales.append(str(m).title())
                    elif m_safe in lista_parciales: parciales.append(str(m).title())
                    else: parciales.append(str(m).title()) 
                        
                st.markdown(f"**{nombre_estado} (Clave {cve_str})**")
                if totales: st.markdown(f"  * *Totalmente contenidos:* {', '.join(totales)}")
                if parciales: st.markdown(f"  * *Parcialmente dentro:* {', '.join(parciales)}")
            return
            
    mostrar_dato("Municipios (Totalmente contenidos)", str_total)
    mostrar_dato("Municipios (Parcialmente dentro)", str_parcial)

def buscar_valor(df, palabra_clave, columna='VOLUMEN_hm3', es_total=False):
    if df is None or df.empty or columna not in df.columns: return 0.0
    if es_total:
        match = df[df['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, na=False)]
        if not match.empty:
            try: return float(match.iloc[-1][columna])
            except: return 0.0
    
    match = df[df['CONCEPTO'].astype(str).str.contains(rf'\b{palabra_clave}\b', case=True, regex=True, na=False)]
    if match.empty:
        match = df[df['CONCEPTO'].astype(str).str.contains(palabra_clave, case=False, regex=False, na=False)]
        
    if not match.empty:
        match = match[~match['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, na=False)]
        if not match.empty:
            try: return float(match.iloc[-1][columna])
            except: return 0.0
    return 0.0

# =======================================================
# 🧠 MOTOR DE BÚSQUEDA SEMÁNTICA LOCAL Y DICCIONARIO
# =======================================================
@st.cache_resource(show_spinner=False)
def cargar_modelo_embeddings_local():
    return SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

def responder_busqueda_semantica(prompt_usuario, contexto_completo_str, clave_ac, nombre_ac):
    parrafos = [p.strip() for p in contexto_completo_str.split("\n\n") if p.strip()]
    if not parrafos:
        return "No hay información disponible para este acuífero."

    reglas_busqueda = [
        (["cota", "cotas", "comite", "comite tecnico"], ["comité técnico de aguas subterráneas"]),
        (["consejo", "consejos", "consejo de cuenca"], ["consejo de cuenca del acuífero"]),
        (["organismo", "organismo de cuenca", "region", "region administrativa"], ["región administrativa y organismo de cuenca"]),
        (["direccion", "direccion local", "unidad administrativa", "dl"], ["dirección local y unidad administrativa"]),
        (["zona de disponibilidad", "disponibilidad zona", "zona disponibilidad"], ["zona de disponibilidad oficial"]),
        (["veda", "vedas", "decreto", "decretos"], ["decretos de veda aplicables"]),
        (["limite", "limites", "limte", "acuerdo de limites", "delimitacion"], ["acuerdo de límites oficiales"]),
        (["acuerdo", "acuerdos", "acuerdos generales", "facilidades"], ["acuerdos generales de facilidades"]),
        (["municipio", "municipios", "alcaldia", "alcaldias", "division municipal"], ["municipios ubicados dentro"]),
        (["balance", "dma", "disponibilidad media anual", "recarga", "entradas", "salidas"], ["disponibilidad media anual (dma)", "tabla de entradas al balance", "tabla de salidas del balance"]),
        (["vertice", "vertices", "poligonal", "coordenadas"], ["catálogo y poligonal de vértices"]),
        (["bombeo", "volumen", "volumenes", "concesionado", "extraccion", "repda"], ["volúmenes de extracción concesionados", "tabla de usos y volúmenes concesionados"]),
        (["aprovechamiento", "aprovechamientos", "pozo", "pozos", "censo"], ["censo de aprovechamientos", "tabla de conteo de aprovechamientos"]),
        (["riego", "unidades de riego", "unidad de riego", "unidades"], ["unidades de riego dentro"]),
        (["distritos de riego", "distrito de riego", "distritos"], ["distritos de riego dentro"]),
        (["uso agricola", "agricola"], ["distritos de riego dentro", "unidades de riego dentro"]),
        (["ramsar", "humedal", "humedales"], ["sitios ramsar"]),
        (["estatal", "anp estatal", "anps estatales"], ["áreas naturales protegidas estatales"]),
        (["federal", "anp federal", "anps federales"], ["áreas naturales protegidas federales"]),
        (["anp", "areas naturales", "area natural", "protegida", "protegidas", "medio ambiente"], ["áreas naturales protegidas federales", "áreas naturales protegidas estatales"]),
        (["reglamento", "reglamentos"], ["reglamentos específicos del acuífero"]),
        (["reglamentada", "reglamentadas"], ["zonas reglamentadas"]),
        (["reserva", "reservas"], ["zonas de reserva"])
    ]

    palabras_objetivo = []
    for lista_kw_usuario, lista_kw_texto in reglas_busqueda:
        for kw_u in lista_kw_usuario:
            if es_similitud_difusa(kw_u, prompt_usuario):
                palabras_objetivo.extend(lista_kw_texto)
                break

    if palabras_objetivo:
        bloques_coincidentes = []
        for p in parrafos:
            p_norm = normalizar_texto_ia(p)
            if any(normalizar_texto_ia(obj) in p_norm for obj in palabras_objetivo):
                bloques_coincidentes.append(p)
        
        if bloques_coincidentes:
            texto_base = bloques_coincidentes[0]
            return (f"De acuerdo con los registros oficiales del acuífero **{clave_ac} - {nombre_ac}**:\n\n"
                    f"{texto_base}\n\n"
                    f"Si necesitas consultar algún otro apartado, dímelo con gusto.")

    modelo_emb = cargar_modelo_embeddings_local()
    embeddings_parrafos = modelo_emb.encode(parrafos)
    embedding_pregunta = modelo_emb.encode([prompt_usuario])

    similitudes = cosine_similarity(embedding_pregunta, embeddings_parrafos)[0]
    indices_top = np.argsort(similitudes)[::-1]
    
    bloques_encontrados = []
    for idx in indices_top:
        if similitudes[idx] > 0.35:
            bloques_encontrados.append(parrafos[idx])
            if len(bloques_encontrados) >= 1: 
                break

    if bloques_encontrados:
        texto_base = bloques_encontrados[0]
        return (f"De acuerdo con los registros oficiales del acuífero **{clave_ac} - {nombre_ac}**:\n\n"
                f"{texto_base}\n\n"
                f"Si necesitas consultar algún otro apartado, dímelo con gusto.")
    else:
        return ("No encontré una coincidencia directa para esa consulta. "
                "Intenta buscar por palabras específicas como: *decretos*, *límites*, *municipios*, *balance*, *bombeo* o *vértices*.")

# =======================================================
# 💬 MODAL DE CHAT LOCAL
# =======================================================
@st.dialog("⚙️ Asistente Técnico CONAGUA (Local)", width="large")
def modal_chat_local(clave_ac, nombre_ac, contexto_global_str):
    chat_key = f"chat_history_{clave_ac}"
    if chat_key not in st.session_state: 
        st.session_state[chat_key] = []
        
    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "⚙️"): 
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("Ej: ¿Cuáles son los municipios del acuífero y su balance de agua?"):
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"): 
            st.markdown(prompt)
            
        with st.chat_message("assistant", avatar="⚙️"):
            respuesta = responder_busqueda_semantica(prompt, contexto_global_str, clave_ac, nombre_ac)
            st.markdown(respuesta)
            st.session_state[chat_key].append({"role": "assistant", "content": respuesta})

# =======================================================
# 🧠 CONSTRUCTOR DE CONTEXTO GLOBAL HÍDRICO (RAG ENTERPRISE)
# =======================================================
def obtener_resumen_fraccion(id_capa, clave_ac, campo_nombre, campo_fecha=None, prefijo_fecha="DOF: "):
    df_capa = cargar_fraccion(id_capa)
    if df_capa is None: return "Sin información."
    
    fraccion = df_capa[df_capa['CLV_ACUI'] == clave_ac]
    if fraccion.empty: return "Sin registros aplicables."
        
    unicos = fraccion.drop_duplicates(subset=[campo_nombre])
    elementos = []
    for _, row in unicos.iterrows():
        nom = limpiar_texto(row.get(campo_nombre))
        if nom:
            nom = nom.title()
            if campo_fecha and pd.notna(row.get(campo_fecha)):
                f_limpia = formatear_fecha(row.get(campo_fecha))
                elementos.append(f"{nom} ({prefijo_fecha}{f_limpia})")
            else: elementos.append(nom)
                
    return ", ".join(elementos) if elementos else "Sin registros aplicables."

def obtener_texto_municipios_ia(clave_ac):
    df_mun = cargar_fraccion("municipios")
    if df_mun is None: return "Sin información de municipios."
    
    fraccion = df_mun[df_mun['CLV_ACUI'] == clave_ac]
    if fraccion.empty or 'CVE_ENT' not in fraccion.columns or 'NOMGEO' not in fraccion.columns:
        return "Sin municipios registrados."
        
    diccionario_estados = {
        "01": "Aguascalientes", "02": "Baja California", "03": "Baja California Sur",
        "04": "Campeche", "05": "Coahuila", "06": "Colima", "07": "Chiapas", "08": "Chihuahua",
        "09": "CDMX", "10": "Durango", "11": "Guanajuato", "12": "Guerrero", "13": "Hidalgo",
        "14": "Jalisco", "15": "Estado de México", "16": "Michoacán", "17": "Morelos",
        "18": "Nayarit", "19": "Nuevo León", "20": "Oaxaca", "21": "Puebla", "22": "Querétaro",
        "23": "Quintana Roo", "24": "San Luis Potosí", "25": "Sinaloa", "26": "Sonora",
        "27": "Tabasco", "28": "Tamaulipas", "29": "Tlaxcala", "30": "Veracruz",
        "31": "Yucatán", "32": "Zacatecas"
    }
    
    resumen_mun = []
    agrupados = fraccion.groupby('CVE_ENT')
    for cve_ent, group in agrupados:
        try: cve_str = str(int(float(cve_ent))).zfill(2)
        except: cve_str = str(cve_ent).zfill(2)
        
        edo = diccionario_estados.get(cve_str, f"Estado {cve_str}")
        muns = sorted(group['NOMGEO'].dropna().astype(str).unique().tolist())
        if muns: resumen_mun.append(f"  * {edo}: {', '.join([m.title() for m in muns])}")
            
    return "\n".join(resumen_mun) if resumen_mun else "Sin información detallada."

# =======================================================
# 🛠️ FUNCIONES DE NORMALIZACIÓN Y MATCHER DIFUSO (FUZZY)
# =======================================================
def normalizar_texto_ia(texto):
    if not texto: return ""
    texto = str(texto).lower()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    return texto.strip()

def es_similitud_difusa(palabra_buscada, texto_usuario, umbral=0.82):
    palabra_norm = normalizar_texto_ia(palabra_buscada)
    prompt_norm = normalizar_texto_ia(texto_usuario)
    if palabra_norm in prompt_norm: return True
    palabras_prompt = prompt_norm.split()
    for p in palabras_prompt:
        if len(p) >= 4 and len(palabra_norm) >= 4:
            ratio = SequenceMatcher(None, palabra_norm, p).ratio()
            if ratio >= umbral: return True
    return False

# =======================================================
# 🧠 CONSTRUCTOR DE CONTEXTO ULTRA-ROBUSTO (RAG HYBRID)
# =======================================================
def construir_contexto_completo(clave_ac, nombre_ac, estado, datos_ac, 
                                 parrafo_vol, parrafo_aprov, parrafo_dma,
                                 df_resumen, conteo_usos, 
                                 df_bal_ent, df_bal_sal, df_bal_alm,
                                 df_verts, df_flujo_ent, df_flujo_sal, df_etr, df_alm, dato_zona_disp):
    ctx = []
    
    ctx.append(f"Acuífero Oficial: {clave_ac} - {nombre_ac} | Estado Principal: {estado}")
    org_cuenca = limpiar_texto(datos_ac.get('REGION_ADM'))
    ctx.append(f"Región Administrativa y Organismo de Cuenca del acuífero {clave_ac}:\n- {org_cuenca if org_cuenca else 'Sin información de Organismo de Cuenca.'}")
    dir_local = limpiar_texto(datos_ac.get('UNIDAD_ADM'))
    ctx.append(f"Dirección Local y Unidad Administrativa del acuífero {clave_ac}:\n- {dir_local if dir_local else 'Sin información de Dirección Local.'}")
    if dato_zona_disp and str(dato_zona_disp).lower() != 'nan': ctx.append(f"Zona de Disponibilidad Oficial del acuífero {clave_ac}:\n- Zona {dato_zona_disp}")
    else: ctx.append(f"Zona de Disponibilidad Oficial del acuífero {clave_ac}:\n- Sin información de zona registrada.")

    lim_nom = limpiar_texto(datos_ac.get('excel_LIM_NOM'))
    lim_fec = limpiar_texto(datos_ac.get('excel_LIM_FECHA'))
    if lim_nom:
        fec_str = f" (Publicado en DOF: {formatear_fecha(lim_fec)})" if lim_fec else ""
        ctx.append(f"Acuerdo de Límites Oficiales y Descripción Geográfica del acuífero {clave_ac}:\n- {lim_nom}{fec_str}")
    else: ctx.append(f"Acuerdo de Límites Oficiales del acuífero {clave_ac}:\n- Información de límites en proceso de validación o no disponible.")

    vedas_nom = limpiar_texto(datos_ac.get('vedas_NOM_OFI'))
    vedas_fec = limpiar_texto(datos_ac.get('vedas_FECHA_DOF'))
    if vedas_nom and str(vedas_nom).lower() != 'nan':
        fec_str = f" (DOF: {formatear_fecha(vedas_fec)})" if vedas_fec else ""
        ctx.append(f"Decretos de Veda Aplicables al acuífero {clave_ac}:\n- {vedas_nom}{fec_str}")
    else: ctx.append(f"Decretos de Veda del acuífero {clave_ac}:\n- No se encontraron Decretos de Veda registrados para este acuífero.")

    acuerdos_nom = limpiar_texto(datos_ac.get('acuerdos_generales_NOM_OFI'))
    acuerdos_fec = limpiar_texto(datos_ac.get('acuerdos_generales_FECHA_DOF'))
    if acuerdos_nom and str(acuerdos_nom).lower() != 'nan':
        fec_str = f" (DOF: {formatear_fecha(acuerdos_fec)})" if acuerdos_fec else ""
        ctx.append(f"Acuerdos Generales de Facilidades Administrativas en el acuífero {clave_ac}:\n- {acuerdos_nom}{fec_str}")
    else: ctx.append(f"Acuerdos Generales en el acuífero {clave_ac}:\n- Sin información de Acuerdos Generales.")

    z_reg = limpiar_texto(datos_ac.get('zonas_reglamentadas_NOM_OFI'))
    if z_reg and str(z_reg).lower() != 'nan': ctx.append(f"Zonas Reglamentadas en el acuífero {clave_ac}:\n- {z_reg}")
    else: ctx.append(f"Zonas Reglamentadas en el acuífero {clave_ac}:\n- Sin información de Zonas Reglamentadas.")

    z_res = limpiar_texto(datos_ac.get('zonas_reserva_NOM_OFI'))
    if z_res and str(z_res).lower() != 'nan': ctx.append(f"Zonas de Reserva en el acuífero {clave_ac}:\n- {z_res}")
    else: ctx.append(f"Zonas de Reserva en el acuífero {clave_ac}:\n- Sin información de Zonas de Reserva.")

    regl = limpiar_texto(datos_ac.get('reglamentos_NOM_OFI'))
    if regl and str(regl).lower() != 'nan': ctx.append(f"Reglamentos Específicos del acuífero {clave_ac}:\n- {regl}")
    else: ctx.append(f"Reglamentos Específicos del acuífero {clave_ac}:\n- Sin información de Reglamentos registrados.")

    cotas_nom = limpiar_texto(datos_ac.get('cotas_nom_cotas'))
    if cotas_nom and str(cotas_nom).lower() != 'nan': ctx.append(f"Comité Técnico de Aguas Subterráneas (COTAS) en el acuífero {clave_ac}:\n- {cotas_nom}")
    else: ctx.append(f"Comité Técnico de Aguas Subterráneas (COTAS) en el acuífero {clave_ac}:\n- Sin información de COTAS.")

    texto_muns = obtener_texto_municipios_ia(clave_ac)
    ctx.append(f"Municipios Ubicados Dentro del acuífero {clave_ac} (por Estado):\n{texto_muns if texto_muns else 'Sin información de municipios.'}")

    cons_cuenca = obtener_resumen_fraccion('consejos_cuenca', clave_ac, 'NOMCONSEJC', 'FECHA_INST', 'Instalado: ')
    ctx.append(f"Consejo de Cuenca del acuífero {clave_ac}:\n- {cons_cuenca if cons_cuenca and 'Sin registros' not in cons_cuenca else 'Sin información de Consejo de Cuenca.'}")

    anp_fed = obtener_resumen_fraccion('anp_federal', clave_ac, 'NOMBRE', 'PRIM_DEC', 'DOF: ')
    ctx.append(f"Áreas Naturales Protegidas Federales en el acuífero {clave_ac}:\n- {anp_fed if anp_fed and 'Sin registros' not in anp_fed else 'Sin información de ANPs Federales.'}")

    anp_est = obtener_resumen_fraccion('anp_estatal', clave_ac, 'NOMBRE', 'ULT_DEC', 'Últ. Dec: ')
    ctx.append(f"Áreas Naturales Protegidas Estatales en el acuífero {clave_ac}:\n- {anp_est if anp_est and 'Sin registros' not in anp_est else 'Sin información de ANPs Estatales.'}")

    ramsar_txt = obtener_resumen_fraccion('ramsar', clave_ac, 'RAMSAR', 'FECHA', 'Fecha: ')
    ctx.append(f"Sitios RAMSAR en el acuífero {clave_ac}:\n- {ramsar_txt if ramsar_txt and 'Sin registros' not in ramsar_txt else 'Sin información de Sitios RAMSAR.'}")

    dist_riego = limpiar_texto(datos_ac.get('distritos_riego_FIRST_NOMB'))
    ctx.append(f"Distritos de Riego dentro del acuífero {clave_ac}:\n- {dist_riego if dist_riego else 'Sin información de Distritos de Riego.'}")

    unid_riego = limpiar_texto(datos_ac.get('unidades_riego_rha'))
    ctx.append(f"Unidades de Riego dentro del acuífero {clave_ac}:\n- {unid_riego if unid_riego else 'Sin información de Unidades de Riego.'}")

    if parrafo_vol and "No hay información" not in parrafo_vol: ctx.append(f"Volúmenes de Extracción Concesionados (REPDA) en el acuífero {clave_ac}:\n{parrafo_vol}")
    if not df_resumen.empty: ctx.append("Tabla de Usos y Volúmenes Concesionados (REPDA):\n\n" + df_resumen.to_markdown(index=False))
        
    if parrafo_aprov and "No hay información" not in parrafo_aprov: ctx.append(f"Censo de Aprovechamientos de Agua Subterránea en el acuífero {clave_ac}:\n{parrafo_aprov}")
    if not conteo_usos.empty: ctx.append("Tabla de Conteo de Aprovechamientos por Tipo de Uso:\n\n" + conteo_usos.to_markdown(index=False))

    if parrafo_dma: ctx.append(f"Disponibilidad Media Anual (DMA) calculada para el acuífero {clave_ac}:\n{parrafo_dma}")
    
    if df_bal_ent is not None and not df_bal_ent[df_bal_ent['CLV_ACUI'] == clave_ac].empty:
        ent_ac = df_bal_ent[df_bal_ent['CLV_ACUI'] == clave_ac]
        ctx.append("Tabla de Entradas al Balance Hídrico (hm³/año):\n\n" + ent_ac[['CONCEPTO', 'VOLUMEN_hm3']].to_markdown(index=False))
        
    if df_bal_sal is not None and not df_bal_sal[df_bal_sal['CLV_ACUI'] == clave_ac].empty:
        sal_ac = df_bal_sal[df_bal_sal['CLV_ACUI'] == clave_ac]
        cols_sal = [c for c in ['CONCEPTO', 'VOLUMEN_hm3', 'DNC_hm3'] if c in sal_ac.columns]
        ctx.append("Tabla de Salidas del Balance Hídrico (hm³/año):\n\n" + sal_ac[cols_sal].to_markdown(index=False))

    if df_bal_alm is not None and not df_bal_alm[df_bal_alm['CLV_ACUI'] == clave_ac].empty:
        alm_ac = df_bal_alm[df_bal_alm['CLV_ACUI'] == clave_ac]
        ctx.append("Tabla de Cambio de Almacenamiento ΔV(S) (hm³/año):\n\n" + alm_ac[['CONCEPTO', 'VOLUMEN_hm3']].to_markdown(index=False))

    if df_flujo_ent is not None:
        fe = df_flujo_ent[df_flujo_ent['CLV_ACUI'] == clave_ac]
        if not fe.empty: ctx.append("Memoria de Cálculo: Entrada Horizontal Subterránea (Eh) detalle:\n\n" + fe.drop(columns=['CLV_ACUI'], errors='ignore').to_markdown(index=False))

    if df_flujo_sal is not None:
        fs = df_flujo_sal[df_flujo_sal['CLV_ACUI'] == clave_ac]
        if not fs.empty: ctx.append("Memoria de Cálculo: Salida Horizontal Subterránea (Sh) detalle:\n\n" + fs.drop(columns=['CLV_ACUI'], errors='ignore').to_markdown(index=False))

    if df_etr is not None:
        etr_ac = df_etr[df_etr['CLV_ACUI'] == clave_ac]
        if not etr_ac.empty: ctx.append("Memoria de Cálculo: Evapotranspiración Real (ETR) detalle:\n\n" + etr_ac.drop(columns=['CLV_ACUI'], errors='ignore').to_markdown(index=False))

    if df_alm is not None:
        alm_det = df_alm[df_alm['CLV_ACUI'] == clave_ac]
        if not alm_det.empty: ctx.append("Memoria de Cálculo: Cambio de Almacenamiento ΔV(S) detalle:\n\n" + alm_det.drop(columns=['CLV_ACUI'], errors='ignore').to_markdown(index=False))

    if df_verts is not None:
        v_ac = df_verts[df_verts['ID_ACUIFERO'] == clave_ac]
        if not v_ac.empty:
            ctx.append(f"Catálogo y Poligonal de Vértices en el DOF del acuífero {clave_ac}:\nTotal de vértices publicados: {len(v_ac)}\n\nCoordenadas de muestra:\n\n" + v_ac.head(6)[['VERTICE', 'LONG_G', 'LONG_M', 'LONG_S', 'LAT_G', 'LAT_M', 'LAT_S']].to_markdown(index=False))

    return "\n\n".join(ctx)

@st.dialog("📐 Catálogo de Vértices (Poligonal Oficial)", width="large")
def modal_vertices(clave_ac):
    if df_vertices_global is not None:
        df_verts_filtrado = df_vertices_global[df_vertices_global['ID_ACUIFERO'] == clave_ac].copy()
        
        if not df_verts_filtrado.empty:
            df_verts_filtrado = df_verts_filtrado.sort_values(by='VERTICE')
            fila_cierre = df_verts_filtrado[df_verts_filtrado.duplicated(subset=['VERTICE'], keep='first')]
            df_verts_filtrado = df_verts_filtrado.drop_duplicates(subset=['VERTICE'], keep='first')
            df_verts_filtrado = pd.concat([df_verts_filtrado, fila_cierre])
            df_verts_filtrado['OBSERVACIONES'] = df_verts_filtrado['OBSERVACIONES'].fillna('')
            
            st.write("Listado de coordenadas topográficas publicadas en el Diario Oficial de la Federación:")

            html = """
            <style>
                .tabla-oficial { width: 100%; border-collapse: collapse; font-family: 'Noto Sans', sans-serif; font-size: 13px; text-align: center; }
                .tabla-oficial th { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 8px; vertical-align: middle; font-weight: bold; }
                .tabla-oficial td { border: 1px solid #dee2e6; padding: 6px; }
            </style>
            <table class="tabla-oficial">
                <thead>
                    <tr>
                        <th rowspan="2">VÉRTICE</th>
                        <th colspan="3">LONGITUD OESTE</th>
                        <th colspan="3">LATITUD NORTE</th>
                        <th rowspan="2">OBSERVACIONES</th>
                    </tr>
                    <tr>
                        <th>GRADOS</th><th>MINUTOS</th><th>SEGUNDOS</th>
                        <th>GRADOS</th><th>MINUTOS</th><th>SEGUNDOS</th>
                    </tr>
                </thead>
                <tbody>
            """
            
            def a_float(val):
                try: return abs(float(val))
                except: return 0.0

            for _, row in df_verts_filtrado.iterrows():
                seg_long = f"{a_float(row.get('LONG_S', 0)):.1f}".replace("-0.0", "0.0")
                seg_lat  = f"{a_float(row.get('LAT_S', 0)):.1f}".replace("-0.0", "0.0")
                html += f"<tr><td>{row.get('VERTICE','')}</td><td>{row.get('LONG_G','')}</td><td>{row.get('LONG_M','')}</td><td>{seg_long}</td><td>{row.get('LAT_G','')}</td><td>{row.get('LAT_M','')}</td><td>{seg_lat}</td><td>{row.get('OBSERVACIONES','')}</td></tr>"
            
            html += "</tbody></table>"
            st.markdown("\n".join([line.strip() for line in html.split('\n')]), unsafe_allow_html=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                workbook = writer.book
                worksheet = workbook.add_worksheet('Poligonal_Oficial')
                
                fmt_header = workbook.add_format({'font_name': 'Noto Sans Condensed', 'font_size': 10, 'bold': True, 'bg_color': '#C0D7EE', 'align': 'center', 'valign': 'vcenter', 'border': 1})
                fmt_data = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1})
                fmt_segundos = workbook.add_format({'font_name': 'Noto Sans', 'font_size': 9, 'align': 'center', 'valign': 'vcenter', 'border': 1, 'num_format': '0.0'})
                
                worksheet.merge_range('A1:A2', 'VÉRTICE', fmt_header)
                worksheet.merge_range('B1:D1', 'LONGITUD OESTE', fmt_header)
                worksheet.merge_range('E1:G1', 'LATITUD NORTE', fmt_header)
                worksheet.merge_range('H1:H2', 'OBSERVACIONES', fmt_header)
                
                sub_headers = ['GRADOS', 'MINUTOS', 'SEGUNDOS', 'GRADOS', 'MINUTOS', 'SEGUNDOS']
                for i, text in enumerate(sub_headers): worksheet.write(1, i + 1, text, fmt_header)
                
                for r_idx, (_, row) in enumerate(df_verts_filtrado.iterrows()):
                    fila_excel = r_idx + 2
                    worksheet.write(fila_excel, 0, row.get('VERTICE'), fmt_data)
                    worksheet.write(fila_excel, 1, row.get('LONG_G'), fmt_data)
                    worksheet.write(fila_excel, 2, row.get('LONG_M'), fmt_data)
                    worksheet.write_number(fila_excel, 3, a_float(row.get('LONG_S')), fmt_segundos) 
                    worksheet.write(fila_excel, 4, row.get('LAT_G'), fmt_data)
                    worksheet.write(fila_excel, 5, row.get('LAT_M'), fmt_data)
                    worksheet.write_number(fila_excel, 6, a_float(row.get('LAT_S')), fmt_segundos)
                    worksheet.write(fila_excel, 7, row.get('OBSERVACIONES'), fmt_data)
                
                worksheet.set_column('A:A', 10)
                worksheet.set_column('B:G', 12)
                worksheet.set_column('H:H', 30)

            st.download_button(
                label="⬇️ Descargar Listado de Vértices (Excel)",
                data=buffer.getvalue(),
                file_name=f"Vertices_Acuifero_{clave_ac}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        else:
            st.warning("Aún no se ha digitalizado el catálogo de vértices para este acuífero.")
    else:
        st.error("Archivo 'Vertices.xlsx' no encontrado.")

@st.dialog("📊 Memoria de Cálculo Detallada", width="large")
def modal_tablas_calculo(clave_ac, tabla_tipo):
    mapeo_config = {
        "Eh": {
            "df": df_flujo_ent_global, 
            "titulo": "Entrada horizontal subterránea (Eh)",
            "cols": {"LONG_B_m": "LONGITUD B (m)", "ANCHO_a_m": "ANCHO a (m)", 
                     "h2_h1_m": "h₂-h₁ (m)", "GRADIENTE_i": "GRADIENTE i", "T_m2_s": "T (m²/s)", 
                     "CAUDAL_Q_m3_s": "CAUDAL Q (m³/s)", "VOLUMEN_hm3": "VOLUMEN (hm³/año)"}
        },
        "Sh": {
            "df": df_flujo_sal_global, 
            "titulo": "Salida horizontal subterránea (Sh)",
            "cols": {"LONG_B_m": "LONGITUD B (m)", "ANCHO_a_m": "ANCHO a (m)", 
                     "h2_h1_m": "h₂-h₁ (m)", "GRADIENTE_i": "GRADIENTE i", "T_m2_s": "T (m²/s)", 
                     "CAUDAL_Q_m3_s": "CAUDAL Q (m³/s)", "VOLUMEN_hm3": "VOLUMEN (hm³/año)"}
        },
        "ETR": {
            "df": df_etr_global, 
            "titulo": "Evapotranspiración Real (ETR)",
            "cols": {"RANGOS_DE_PROFUNDIDAD_m": "RANGOS DE PROFUNDIDAD (m)","PROFUNDIDAD_MEDIA_m": "PROFUNDIDAD MEDIA (m)", "AREA_km2": "ÁREA (km²)", 
                     "LAMINA_ETR_m": "LÁMINA ETR (m)", "PROF_MAX_EXTINCION_ETR": "PROFUNDIDAD MÁXIMA DE EXTINCIÓN DE LA ETR",
                     "PORCENTAJE_ETR": "% ETR", "VOLUMEN_ETR_hm3_ano": "VOLUMEN ETR (hm³/año)"}
        },
        "ΔV(S)": {
            "df": df_almacenamiento_global, 
            "titulo": "Cambio de Almacenamiento ΔV(S)",
            "cols": {"EVOLUCION_m": "EVOLUCIÓN (m)", "EVOLUCION_MEDIA_m": "EVOLUCIÓN MEDIA (m)",
                     "AREA_km2": "ÁREA (km²)", "Sy": "Sy", "VOLUMEN_hm3": "ΔV(S) (hm³/año)"}
        }
    }
    
    config = mapeo_config.get(tabla_tipo)
    if config and config["df"] is not None:
        df_base = config["df"][config["df"]['CLV_ACUI'] == clave_ac].copy()
        
        if not df_base.empty:
            df_mostrar = df_base.drop(columns=['CLV_ACUI'])
            col_texto = df_mostrar.columns[0]
            
            df_mostrar = df_mostrar[df_mostrar[col_texto].notna()]
            df_mostrar = df_mostrar[~df_mostrar[col_texto].astype(str).str.upper().isin(['CONCEPTO', 'NAN', ''])]
            df_mostrar = df_mostrar.rename(columns=config["cols"])
            
            if tabla_tipo in ["Eh", "Sh", "ETR"]:
                col_vol = next((c for c in df_mostrar.columns if "VOLUMEN" in c.upper()), None)
                if col_vol:
                    total_val = pd.to_numeric(df_mostrar[col_vol], errors='coerce').sum()
                    fila_total = pd.DataFrame({df_mostrar.columns[0]: ["TOTAL"], col_vol: [total_val]})
                    df_mostrar = pd.concat([df_mostrar, fila_total], ignore_index=True)
            
            if tabla_tipo == "ΔV(S)":
                for idx, row in df_mostrar.iterrows():
                    if "PROMEDIO" in str(row[df_mostrar.columns[0]]).upper():
                        for col in df_mostrar.columns[1:-1]:
                            df_mostrar.at[idx, col] = float('nan')
            
            df_final = df_mostrar.copy().astype(str)
            
            for col in df_mostrar.columns:
                if col != df_mostrar.columns[0]:
                    for idx in df_mostrar.index:
                        val_raw = df_mostrar.at[idx, col]
                        val = pd.to_numeric(val_raw, errors='coerce')
                        
                        if pd.isna(val):
                            df_final.at[idx, col] = ""
                        else:
                            if "EVOLUCIÓN (m)" in col: df_final.at[idx, col] = str(val_raw)
                            elif any(x in col.upper() for x in ["VOLUMEN", "ΔV(S)", "EVOLUCIÓN MEDIA", "PROFUNDIDAD MEDIA", "% ETR", "SY", "ÁREA (KM²)"]):
                                df_final.at[idx, col] = "{:.1f}".format(float(val))
                            elif any(x in col.upper() for x in ["LONGITUD B", "ANCHO A", "H₂-H₁", "PROFUNDIDAD MÁXIMA"]):
                                df_final.at[idx, col] = "{:.0f}".format(float(val))
                            else: df_final.at[idx, col] = "{:.4f}".format(float(val))
            
            def aplicar_estilos(df):
                styler = df.style
                styler.set_table_styles([{
                    'selector': 'th',
                    'props': [('background-color', '#BDD7EE'), ('color', '#244062'), 
                              ('font-family', 'Noto Sans'), ('text-align', 'center'),
                              ('font-weight', 'bold'), ('border', '1px solid #dee2e6')]
                }])
                col0 = df.iloc[:, 0].astype(str).str.upper()
                mask = col0.str.contains("TOTAL|PROMEDIO", na=False)
                if mask.any():
                    styler.map(lambda x: 'background-color: #BDD7EE', subset=pd.IndexSlice[mask, :])
                return styler
            
            st.write(f"**{config['titulo']}**")
            st.dataframe(aplicar_estilos(df_final), use_container_width=True, hide_index=True)
        else:
            st.warning("No hay registros.")
    else:
        st.error("Archivo Parquet no cargado.")

# =======================================================
# 🎛️ 5. INTERFAZ PRINCIPAL
# =======================================================
if gdf_maestro is not None:
    # --- SIDEBAR ---
    st.sidebar.header("🔍 Panel de Control")
    lista_estados = sorted(gdf_maestro['NOM_EDO'].dropna().astype(str).apply(limpiar_texto).unique())
    estado_seleccionado = st.sidebar.selectbox("1. Estado:", lista_estados, index=None, placeholder="Elige un estado...")
    
    seleccion_final, file_id_geo = None, None
    if estado_seleccionado:
        gdf_filtrado_estado = gdf_maestro[gdf_maestro['NOM_EDO'].astype(str).apply(limpiar_texto) == estado_seleccionado].copy()
        gdf_filtrado_estado['label_busqueda'] = (gdf_filtrado_estado['CLV_ACUI'].astype(str).apply(limpiar_texto) + " - " + gdf_filtrado_estado['NOM_ACUI'].astype(str).apply(limpiar_texto))
        opciones_acuiferos = sorted(gdf_filtrado_estado['label_busqueda'].unique())
        
        seleccion_final = st.sidebar.selectbox("2. Clave o Nombre del Acuífero:", opciones_acuiferos, index=None, placeholder="Teclea la clave o nombre...")
        
    st.sidebar.markdown("---")
    st.sidebar.subheader("🗺️ Capas Visuales (Mapa)")
    diccionario_capas = {
        "Acuerdos Generales": ("acuerdos_generales", "#34495e", "NOM_OFI"),
        "Áreas Naturales Protegidas Estatales": ("anp_estatal", "#27ae60", "NOMBRE"),
        "Áreas Naturales Protegidas Federales": ("anp_federal", "#2ecc71", "NOMBRE"),
        "Consejos de Cuenca": ("consejos_cuenca", "#2980b9", "NOMCONSEJC"),
        "COTAS": ("cotas", "#16a085", "nom_cotas"),
        "Cultivos": ("cultivos", "#d35400", "dr"),
        "Distritos de Riego": ("distritos_riego", "#e67e22", "FIRST_NOMB"),
        "Municipios": ("municipios", "#95a5a6", "NOMGEO"),
        "Organismos de Cuenca": ("organismos_cuenca", "#3498db", "NOMBRE"),
        "Reglamentos": ("reglamentos", "#c0392b", "NOM_OFI"),
        "Sitios RAMSAR": ("ramsar", "#00bcd4", "RAMSAR"),
        "Unidades de Riego": ("unidades_riego", "#f1c40f", "rha"),
        "Vedas": ("vedas", "#8e44ad", "NOM_OFI"),
        "Zonas de Reserva": ("zonas_reserva", "#e74c3c", "NOM_OFI"),
        "Zonas Reglamentadas": ("zonas_reglamentadas", "#9b59b6", "NOM_OFI")
    }
    capas_seleccionadas = st.sidebar.multiselect("Selecciona qué fracciones ver en el mapa:", list(diccionario_capas.keys()), placeholder="Elige una o más capas...")
    
    if seleccion_final:
        clave_sel = seleccion_final.split(" - ")[0]
        st.sidebar.markdown("---")
        st.sidebar.subheader("⛰️ Mapa Geológico")
        if df_links_global is not None:
            link_row = df_links_global[df_links_global['clave'] == clave_sel]
            if not link_row.empty:
                file_id_geo = procesar_link_drive(link_row.iloc[0].get('link'))
                if file_id_geo:
                    st.sidebar.link_button("⬇️ Descargar Mapa (PNG)", url=f"https://drive.google.com/uc?export=download&id={file_id_geo}", use_container_width=True)
            else: st.sidebar.info("📂 Mapa geológico próximamente disponible.")

    # --- CONTENIDO PRINCIPAL ---
    if seleccion_final:
        datos_ac = gdf_filtrado_estado[gdf_filtrado_estado['CLV_ACUI'].astype(str).apply(limpiar_texto) == clave_sel].iloc[0]
        nombre_ac = limpiar_texto(datos_ac['NOM_ACUI'])
        
        # PRE-CÁLCULO DE PÁRRAFOS (BOMBEO Y VOLÚMENES)
        parrafo_vol_ia, vol_total, df_resumen = "No hay información de volúmenes REPDA disponible.", 0.0, pd.DataFrame()
        if df_repda_global is not None:
            r_filtrado = df_repda_global[df_repda_global['Clave de acuífero'] == clave_sel]
            if not r_filtrado.empty:
                d_repda = r_filtrado.iloc[0]
                vol_total = float(d_repda.get('Volumen total (hm3/año)', 0.0)) if pd.notna(d_repda.get('Volumen total (hm3/año)')) else 0.0
                registros = [{"Tipo de Uso": c.replace(" (hm3/año)", "").strip(), "Volumen (hm³/año)": float(d_repda[c]), "Porcentaje (%)": (float(d_repda[c])/vol_total)*100} for c in df_repda_global.columns if c not in ['Clave de acuífero', 'Acuífero', 'Volumen total (hm3/año)', 'Porcentaje Total'] and pd.notna(d_repda.get(c)) and float(d_repda.get(c))>0]
                if registros:
                    df_resumen = pd.DataFrame(registros).sort_values(by="Volumen (hm³/año)", ascending=False).reset_index(drop=True)
                    df_texto = df_resumen[df_resumen['Volumen (hm³/año)'] >= 0.1].copy().reset_index(drop=True)
                    if not df_texto.empty:
                        dic_usos = {"Agrícola": "uso agrícola", "Público Urbano": "uso público-urbano", "Industrial": "uso industrial", "Pecuario": "uso pecuario", "Doméstico": "uso doméstico", "Acuacultura": "uso de acuacultura", "Diferentes usos": "diferentes usos", "Servicios": "servicios", "Comercio": "comercio", "Otros": "otros usos"}
                        frags = []
                        for i, r in df_texto.iterrows():
                            uso = dic_usos.get(r['Tipo de Uso'].strip(), r['Tipo de Uso'].strip().lower())
                            f = f"{r['Volumen (hm³/año)']:.1f} hm³/año ({r['Porcentaje (%)']:.1f} %) " + ("corresponde a " if i == 0 else "a ") + uso
                            frags.append(f)
                        parrafo_vol_ia = f"El volumen total de extracción para esa fecha asciende a {vol_total:.1f} hm³/año del cual {', '.join(frags[:-1]) + f', y {frags[-1]}' if len(frags)>1 else frags[0]}."

        parrafo_aprov_ia, total_aprov, conteo_usos = "No hay información de conteo de aprovechamientos disponible.", 0, pd.DataFrame()
        if df_aprov_global is not None:
            a_filtrado = df_aprov_global[df_aprov_global['Cve_Acuif'] == clave_sel]
            if not a_filtrado.empty:
                conteo_usos = a_filtrado['Uso'].value_counts().reset_index()
                conteo_usos.columns = ['Tipo de Uso', 'Cantidad']
                total_aprov = conteo_usos['Cantidad'].sum()
                conteo_usos['Porcentaje (%)'] = (conteo_usos['Cantidad'] / total_aprov) * 100
                dic_usos_aprov = {"Agrícola": "uso agrícola", "Público Urbano": "uso público-urbano", "Público-Urbano": "uso público-urbano", "Industrial": "uso industrial", "Pecuario": "uso pecuario", "Doméstico": "uso doméstico", "Acuacultura": "acuacultura", "Diferentes usos": "diferentes usos", "Diferentes Usos": "diferentes usos", "Servicios": "servicios", "Agroindustrial": "uso agroindustrial", "Comercio": "comercio", "Otros": "otros usos"}
                f_aprov = []
                for i, r in conteo_usos.iterrows():
                    uso = dic_usos_aprov.get(str(r['Tipo de Uso']).strip(), str(r['Tipo de Uso']).strip().lower())
                    pct = f" ({r['Porcentaje (%)']:.1f} %)" if r['Cantidad'] > 1 and r['Porcentaje (%)'] >= 0.1 else ""
                    frag = f"{r['Cantidad']:,}{pct} " + ("se destinan a " if i == 0 else "a ") + uso
                    if i == 0: frag = frag.replace("a uso", "al uso")
                    f_aprov.append(frag)
                parrafo_aprov_ia = f"De acuerdo con el Registro Público Nacional del Agua (REPNA) con fecha de corte al 30 de septiembre del 2025, se reportan un total de {total_aprov:,} aprovechamientos de agua subterránea, de los cuales {', '.join(f_aprov[:-1]) + f' y {f_aprov[-1]}' if len(f_aprov)>1 else f_aprov[0]}."

        dato_zona_disp = "Sin información"
        if df_zonas_global is not None:
            z_filt = df_zonas_global[df_zonas_global['CLAVE DEL ACUÍFERO'] == clave_sel]
            if not z_filt.empty and pd.notna(z_filt.iloc[0].get('ZONA DE DISPONIBILIDAD')):
                dato_zona_disp = str(z_filt.iloc[0].get('ZONA DE DISPONIBILIDAD')).strip()
        
        # =======================================================
        # 🧮 NUEVO: PRE-CÁLCULO DE DMA PARA EL ASISTENTE IA
        # =======================================================
        parrafo_dma_ia = "No hay información de balance disponible."
        if df_bal_ent_global is not None and df_bal_sal_global is not None:
            bal_ent = df_bal_ent_global[df_bal_ent_global['CLV_ACUI'] == clave_sel]
            bal_sal = df_bal_sal_global[df_bal_sal_global['CLV_ACUI'] == clave_sel]
            
            if not bal_ent.empty and not bal_sal.empty:
                v_r_total = buscar_valor(bal_ent, "R", es_total=True)
                
                # Rescate seguro de DNC
                match_dnc = bal_sal[bal_sal['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, na=False)]
                if not match_dnc.empty:
                    val_crudo = match_dnc.iloc[-1]['DNC_hm3']
                    if pd.isna(val_crudo) or str(val_crudo).strip().lower() in ['none', '', 'nan']: v_dnc_total = 0.0
                    else:
                        try: v_dnc_total = float(val_crudo)
                        except: v_dnc_total = 0.0
                else:
                    bal_sal_limpia = bal_sal['DNC_hm3'].astype(str).replace(['None', 'none', '', 'NaN'], '0')
                    v_dnc_total = pd.to_numeric(bal_sal_limpia, errors='coerce').fillna(0).sum()

                # Rescate de VEAS
                v_veas = 0.0
                if df_veas_global is not None:
                    veas_match = df_veas_global[df_veas_global['CLAVE'] == clave_sel]
                    if not veas_match.empty: v_veas = float(veas_match.iloc[0]['VEAS_hm3'])

                val_dma = round(v_r_total, 1) - round(v_dnc_total, 1) - v_veas
                parrafo_dma_ia = f"La Disponibilidad Media Anual (DMA) calculada para este acuífero es de {val_dma:,.6f} hm³."

        # =======================================================
        # 🧹 PREPARACIÓN DE RAM BÁSICA (PURGA DE DOCUMENTOS VIEJOS)
        # =======================================================
        if st.session_state.get("acuifero_actual_global") != clave_sel:
            st.session_state["acuifero_actual_global"] = clave_sel
            # Purga estricta de documentos viejos para liberar RAM al cambiar acuífero
            for k in list(st.session_state.keys()):
                if k.startswith("doc_listo_") and k != f"doc_listo_{clave_sel}":
                    del st.session_state[k]

        # Extracción de variables de texto
        nombre_acuifero = limpiar_texto(datos_ac['NOM_ACUI'])
        clave_acuifero = limpiar_texto(datos_ac['CLV_ACUI'])

        # -------------------------------------------------------
        # 👑 ENCABEZADO PRINCIPAL (A TODO EL ANCHO)
        # -------------------------------------------------------
        st.header(f"📋 RESUMEN: {clave_acuifero} - {nombre_acuifero}")
        st.caption(f"Estado: {estado_seleccionado}")

        # =======================================================
        # 🛡️ ESCUDO CSS ANTI-TRANSPARENCIA
        # =======================================================
        st.markdown("""
        <style>
            [data-stale="true"],
            [data-testid="stFragment"],
            [data-testid="stFragment"] * {
                opacity: 1 !important;
                transition: none !important;
                filter: none !important;
                pointer-events: auto !important;
            }
        </style>
        """, unsafe_allow_html=True)

        # =======================================================
        # 📄 TARJETA DE PROCESAMIENTO (LÓGICA ORIGINAL INTACTA)
        # =======================================================
        @st.fragment
        def procesador_fluido_estandarizacion(cve_ac, txt_aprov, txt_vol):
            import traceback
            doc_key = f"doc_listo_{cve_ac}"

            with st.container(border=True):
                st.markdown("""
                <div style="display: flex; align-items: center; gap: 15px; margin-top: -5px; margin-bottom: 15px;">
                    <div style="font-size: 26px; line-height: 1;">📄</div>
                    <div>
                        <p style="margin: 0px; font-weight: 600; color: #691C32; font-size: 14px; line-height: 1.2;">Documento de Actualización-BAS</p>
                        <p style="margin: 4px 0px 0px 0px; font-size: 11px; color: #666; line-height: 1.2;">Genera un nuevo documento con el formato actualizado a partir de la versión anterior almacenada en la base de datos.</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # CONEXIÓN DIRECTA Y SEGURA AL DATAFRAME
                if df_enlaces_docs is not None:
                    enlace_row = df_enlaces_docs[df_enlaces_docs['CLAVE_ACUIFERO'] == cve_ac]
                    if not enlace_row.empty:
                        link_drive = enlace_row.iloc[0]['ENLACE_DRIVE']
                        f_id = procesar_link_drive(link_drive) 
                        
                        if not f_id:
                            st.info("El enlace de Drive no es válido o está vacío.")
                            return

                        espacio_interactivo = st.empty()

                        if doc_key in st.session_state:
                            espacio_interactivo.download_button(
                                label="⬇️ Descargar Documento",
                                data=st.session_state[doc_key],
                                file_name=f"{cve_ac}_ESTANDARIZADO_V3.1.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                type="primary",
                                use_container_width=True,
                                key=f"btn_dl_{cve_ac}"
                            )
                        else:
                            if espacio_interactivo.button("⚙️ Procesar Documento", type="primary", use_container_width=True, key=f"btn_proc_{cve_ac}"):
                                espacio_interactivo.empty()
                                with espacio_interactivo.container():
                                    marcador = st.empty()
                                    barra = st.progress(0)
                                    exito = False

                                    try:
                                        marcador.info("⏳ Descargando archivo base de Google Drive...")
                                        barra.progress(25)

                                        url_export = f"https://docs.google.com/document/d/{f_id}/export?format=docx"
                                        respuesta = requests.get(url_export, timeout=30)
                                        if respuesta.status_code != 200:
                                            raise Exception(f"Drive rechazó la descarga (HTTP {respuesta.status_code}).")

                                        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_origen:
                                            tmp_origen.write(respuesta.content)
                                            tmp_origen.flush()
                                            ruta_origen = tmp_origen.name

                                        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_salida:
                                            ruta_salida = tmp_salida.name

                                        ruta_plantilla = str(DIRECTORIO_RAIZ / "assets" / "PLANTILLA_V3.1.docx")

                                        marcador.info("📐 Estandarizando y consolidando formatos...")
                                        barra.progress(50)
                                        ejecutar_estandarizacion_v31(ruta_plantilla, ruta_origen, ruta_salida)

                                        marcador.info("📊 Inyectando tablas de balance y poligonales...")
                                        barra.progress(75)
                                        inyectar_tabla_vertices_en_word(ruta_salida, cve_ac, df_vertices_global)
                                        inyectar_tabla_flujo_en_word(ruta_salida, cve_ac, df_flujo_ent_global, ["tabla", "entradas", "flujo"], "Entradas")
                                        inyectar_tabla_flujo_en_word(ruta_salida, cve_ac, df_flujo_sal_global, ["tabla", "salidas", "flujo"], "Salidas")
                                        modificar_censo_y_bombeo(ruta_salida, txt_aprov, txt_vol)
                                        inyectar_tabla_almacenamiento_en_word(ruta_salida, cve_ac, df_almacenamiento_global)
                                        inyectar_tabla_evapotranspiracion_en_word(ruta_salida, cve_ac, df_etr_global)

                                        marcador.success("✅ ¡Documento generado con éxito!")
                                        barra.progress(100)

                                        with open(ruta_salida, "rb") as f:
                                            st.session_state[doc_key] = f.read()

                                        exito = True

                                    except Exception as e:
                                        marcador.error(f"❌ Error técnico: {str(e)}")
                                        with st.expander("Ver detalle técnico (Traceback)", expanded=True):
                                            st.code(traceback.format_exc(), language="python")

                                if exito:
                                    espacio_interactivo.empty()
                                    espacio_interactivo.download_button(
                                        label="⬇️ Descargar Documento",
                                        data=st.session_state[doc_key],
                                        file_name=f"{cve_ac}_ESTANDARIZADO_V3.1.docx",
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                        type="primary",
                                        use_container_width=True,
                                        key=f"btn_dl_post_{cve_ac}"
                                    )
                    else:
                        st.info("Sin archivo Drive vinculado a este acuífero en la base de datos.")
                else:
                    st.error("Error al cargar la base de datos de enlaces.")

        # Invocamos la tarjeta pasando los valores directo como argumentos para que no falle
        procesador_fluido_estandarizacion(clave_sel, parrafo_aprov_ia, parrafo_vol_ia)

        st.divider()

        # =======================================================
        # 🗺️ VISORES GEOGRÁFICOS (A TODO EL ANCHO)
        # =======================================================
        st.header("🗺️ Visores Espaciales")
        
        if file_id_geo:
            tab_visor, tab_geo = st.tabs(["🗺️ Visor Interactivo (SIG)", "⛰️ Mapa Geológico Estático"])
        else:
            tab_visor, tab_geo = st.tabs(["🗺️ Visor Interactivo (SIG)", "⛰️ Mapa Geológico (No Disponible)"])
        
        with tab_visor:
            try:
                centroide = datos_ac.geometry.centroid
                m = folium.Map(location=[centroide.y, centroide.x], zoom_start=10, tiles="CartoDB positron", control_scale=True)
                b = datos_ac.geometry.bounds
                m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
                
                folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satélite (Esri)', overlay=False, control=True).add_to(m)
                folium.TileLayer(tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', attr='Map data: &copy; OpenStreetMap contributors, SRTM | Map style: &copy; OpenTopoMap', name='Topográfico', overlay=False, control=True).add_to(m)

                plugins.Fullscreen(position='topright', title='Pantalla completa', title_cancel='Salir de pantalla completa', force_separate_button=True).add_to(m)
                plugins.MeasureControl(position='topleft', primary_length_unit='kilometers', secondary_length_unit='meters', primary_area_unit='sqmeters', secondary_area_unit='hectares').add_to(m)
                plugins.MiniMap(toggle_display=True, position='bottomright', tile_layer='cartodbpositron', zoom_level_offset=-5).add_to(m)
                plugins.MousePosition(position='bottomleft', separator=' | ', empty_string='Fuera del mapa', lng_first=False, num_digits=5, prefix='Coordenadas:').add_to(m)
                
                estilos_mapa = """<style>.leaflet-interactive:focus { outline: none !important; } .leaflet-tooltip::before { display: none !important; }</style>"""
                m.get_root().html.add_child(folium.Element(estilos_mapa))

                estilo_acuifero = "background-color: #f8f9fa; color: #2c3e50; font-family: Arial, sans-serif; font-size: 14px; padding: 8px; border-radius: 6px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"
                
                folium.GeoJson(
                    datos_ac.geometry, name="Límite del Acuífero",
                    style_function=lambda x: {'fillColor': '#3186cc', 'color': '#1a5276', 'weight': 3, 'fillOpacity': 0.2},
                    tooltip=folium.Tooltip(f"<b>Acuífero:</b> {nombre_ac}", style=estilo_acuifero, sticky=True)
                ).add_to(m)
                
                def normalizar_clave_geo(val):
                    try: return str(int(float(val))).zfill(4)
                    except: return str(val).strip().zfill(4)

                for capa_visual in capas_seleccionadas:
                    id_archivo, color_hex, campo_nombre = diccionario_capas[capa_visual]
                    gdf_frac = cargar_fraccion(id_archivo)
                    if gdf_frac is not None:
                        gdf_frac['CLV_TEMP'] = gdf_frac['CLV_ACUI'].apply(normalizar_clave_geo)
                        clave_sel_norm = normalizar_clave_geo(clave_sel)
                        
                        frac_local = gdf_frac[gdf_frac['CLV_TEMP'] == clave_sel_norm]
                        
                        if not frac_local.empty:
                            frac_segura = frac_local.copy()
                            cols = [c for c in frac_segura.columns if c not in ['geometry', 'CLV_TEMP']]
                            for c in cols: frac_segura[c] = frac_segura[c].apply(lambda x: limpiar_texto(x) if pd.notna(x) else "")
                            frac_segura[cols] = frac_segura[cols].astype(str)
                            
                            def obtener_estilo_mosaico(feature, color_base, campo):
                                nombre = feature['properties'].get(campo, "X")
                                valor_texto = sum(ord(letra) for letra in str(nombre))
                                niveles_opacidad = [0.25, 0.45, 0.65, 0.85]
                                return {'fillColor': color_base, 'color': 'white', 'weight': 1.5, 'fillOpacity': niveles_opacidad[valor_texto % 4]}
                            
                            estilo_tooltip_elegante = """background-color: rgba(255,255,255,0.95); border: 1px solid #dcdde1; border-radius: 8px; box-shadow: 0px 6px 12px rgba(0,0,0,0.15); color: #2f3640; font-family: 'Segoe UI', Roboto, sans-serif; font-size: 13px; white-space: normal; max-width: 85vw; min-width: 250px; padding: 10px;"""
                            
                            folium.GeoJson(
                                frac_segura, name=capa_visual, 
                                style_function=lambda feature, c=color_hex, cmp=campo_nombre: obtener_estilo_mosaico(feature, c, cmp),
                                highlight_function=lambda x, c=color_hex: {'fillColor': c, 'color': '#ffeb3b', 'weight': 3, 'fillOpacity': 0.9},
                                tooltip=folium.GeoJsonTooltip(fields=[campo_nombre], aliases=[f"<b>{capa_visual}</b><br>"], localize=True, sticky=True, labels=True, style=estilo_tooltip_elegante)
                            ).add_to(m)
                
                folium.LayerControl(position='topright', collapsed=True).add_to(m)
                # Altura ajustada a 550px para dar espacio a la lectura de datos abajo
                st_folium(m, use_container_width=True, height=550, returned_objects=[])

            except Exception as e:
                import traceback
                st.error("🚨 ERROR FATAL: El mapa o los datos geográficos colapsaron.")
                with st.expander("Ver Traceback de Error (Python)", expanded=True):
                    st.code(traceback.format_exc(), language="python")

        with tab_geo:
            if file_id_geo:
                st.info("💡 Usa el ratón o los controles del recuadro para hacer zoom a la imagen.")
                with st.spinner("Cargando imagen interactiva desde Google Drive..."):
                    components.iframe(f"https://drive.google.com/file/d/{file_id_geo}/preview", height=650, scrolling=True)
            else:
                st.warning("Aún no se ha digitalizado el mapa geológico para este acuífero. Por favor selecciona otro o comunícate con el administrador de la base de datos.")

        st.divider()

        # =======================================================
        # 🗂️ PESTAÑAS DE DATOS (NUEVA DISTRIBUCIÓN)
        # =======================================================
        st.header("📊 Información Técnica y Documental")

        tab_legal, tab_entorno, tab_usos, tab_dma = st.tabs([
            "🏛️ Marco Legal", 
            "🌍 Entorno Socioambiental", 
            "🚰 Usos y Extracciones", 
            "⚖️ Balance (DMA)"
        ])

        # --- PESTAÑA 1: MARCO LEGAL Y ADMINISTRATIVO ---
        with tab_legal:
            with st.expander("📍 Límites Oficiales del Acuífero", expanded=True):
                nombres_limites = datos_ac.get('excel_LIM_NOM')
                fechas_limites = datos_ac.get('excel_LIM_FECHA')
                if pd.notna(nombres_limites) and str(nombres_limites).strip() != "":
                    mostrar_pares_en_parrafo("Acuerdo de Límites", nombres_limites, fechas_limites, prefijo_extra="DOF: ", es_fecha=True)
                else: st.info("Información de límites en proceso de validación o no disponible.")
                if st.button(" Ver Catálogo de Vértices de la Poligonal", type="secondary", key="btn_vert"): modal_vertices(clave_sel)

            with st.expander("⚖️ Decretos de Veda", expanded=True):
                nombres_vedas = datos_ac.get('vedas_NOM_OFI')
                fechas_vedas = datos_ac.get('vedas_FECHA_DOF')
                if pd.notna(nombres_vedas) and str(nombres_vedas).strip() != "" and str(nombres_vedas) != "nan":
                    mostrar_pares_vertical("Decretos Registrados", nombres_vedas, fechas_vedas)
                else: st.info("No se encontraron Decretos de Veda registrados para este acuífero.")

            with st.expander("📜 Acuerdos Generales y Regulaciones", expanded=True):
                nombres_acuerdos = datos_ac.get('acuerdos_generales_NOM_OFI')
                if pd.notna(nombres_acuerdos) and str(nombres_acuerdos).strip() != "" and str(nombres_acuerdos) != "nan":
                    mostrar_pares_vertical("Acuerdos Generales (Capa SIG)", nombres_acuerdos, datos_ac.get('acuerdos_generales_FECHA_DOF'))
                else: st.write("**Acuerdos Generales:** Sin información")
                st.divider()
                mostrar_pares_en_parrafo("Zonas Reglamentadas", datos_ac.get('zonas_reglamentadas_NOM_OFI'), datos_ac.get('zonas_reglamentadas_FECHA_DOF'), "DOF: ", True)
                mostrar_pares_en_parrafo("Zonas de Reserva", datos_ac.get('zonas_reserva_NOM_OFI'), datos_ac.get('zonas_reserva_FECHA_DOF'), "DOF: ", True)
                mostrar_pares_en_parrafo("Reglamentos", datos_ac.get('reglamentos_NOM_OFI'), datos_ac.get('reglamentos_FECHA_DOF'), "DOF: ", True)

            with st.expander("🏛️ Administración y Organismos", expanded=True):
                def formato_nombres(valor, proteger_primera=False):
                    texto_limpio = limpiar_texto(valor)
                    if texto_limpio is None: return None
                    if proteger_primera:
                        partes = texto_limpio.split(" ", 1)
                        if len(partes) > 1: return f"{partes[0].upper()} {partes[1].title()}"
                        else: return texto_limpio.upper()
                    else: return texto_limpio.title()

                mostrar_dato("Organismo de Cuenca (Región Adm.)", formato_nombres(datos_ac.get('REGION_ADM'), proteger_primera=True))
                unidad_adm = str(datos_ac.get('UNIDAD_ADM')).strip()
                if unidad_adm.upper().startswith("DL"): mostrar_dato("Dirección Local", formato_nombres(unidad_adm, proteger_primera=True))
                else: mostrar_dato("Dirección Local", None)

                mostrar_desde_fraccion_en_linea("Consejo de Cuenca", clave_sel, "consejos_cuenca", "NOMCONSEJC", "FECHA_INST", "Instalado: ", True)
                mostrar_pares_en_parrafo("COTAS", datos_ac.get('cotas_nom_cotas'), datos_ac.get('cotas_fecha_inst'), "Fecha: ", True)
                st.write(f"**Zona de Disponibilidad:** {dato_zona_disp}")

        # --- PESTAÑA 2: ENTORNO SOCIOAMBIENTAL ---
        with tab_entorno:
            with st.expander("📍 División Municipal", expanded=True):
                mostrar_municipios_agrupados_y_condicion(clave_sel, datos_ac.get('municipios_TOTAL'), datos_ac.get('municipios_PARCIAL'))

            with st.expander("🌿 Medio Ambiente", expanded=True):
                mostrar_desde_fraccion_vertical("Áreas Naturales Protegidas Federales", clave_sel, "anp_federal", "NOMBRE", "PRIM_DEC", "DOF: ")
                mostrar_desde_fraccion_vertical("Áreas Naturales Protegidas Estatales", clave_sel, "anp_estatal", "NOMBRE", "ULT_DEC", "Últ. Dec: ")
                mostrar_desde_fraccion_vertical("Sitios RAMSAR", clave_sel, "ramsar", "RAMSAR", "FECHA", "Fecha: ")

            with st.expander("🌾 Uso Agrícola", expanded=True):
                mostrar_pares_en_parrafo("Distritos de Riego", datos_ac.get('distritos_riego_FIRST_NOMB'), datos_ac.get('distritos_riego_DISTID'))
                mostrar_dato("Unidades de Riego", datos_ac.get('unidades_riego_rha'))

        # --- PESTAÑA 3: USOS Y EXTRACCIONES ---
        with tab_usos:
            st.subheader("📊 Resumen de Bombeo (REPDA)")
            if not df_resumen.empty:
                st.dataframe(df_resumen.style.format({"Volumen (hm³/año)": "{:.1f}", "Porcentaje (%)": "{:.1f}%"}), use_container_width=True, hide_index=True)
                st.metric("Volumen Total Concesionado (hm³/año)", f"{vol_total:.1f}")
                st.info(parrafo_vol_ia)
            else: st.warning(f"No se encontró la clave {clave_sel} en el archivo REPDA.")
            
            st.divider()
            
            st.subheader("💧 Conteo de Aprovechamientos")
            if not conteo_usos.empty:
                st.dataframe(conteo_usos.style.format({"Porcentaje (%)": "{:.1f}%"}), use_container_width=True, hide_index=True)
                st.metric("Total de Aprovechamientos Registrados", f"{total_aprov:,}")
                st.info(parrafo_aprov_ia)
            else: st.warning(f"No se encontraron registros de aprovechamientos.")

        # --- PESTAÑA 4: BALANCE Y DISPONIBILIDAD ---
        with tab_dma:
            st.subheader("Balance de Aguas Subterráneas y Cálculo de la DMA")
            st.caption("Valores de flujo y almacenamiento extraídos directamente de los Parquet")

            bal_ent = df_bal_ent_global[df_bal_ent_global['CLV_ACUI'] == clave_sel] if df_bal_ent_global is not None else pd.DataFrame()
            bal_sal = df_bal_sal_global[df_bal_sal_global['CLV_ACUI'] == clave_sel] if df_bal_sal_global is not None else pd.DataFrame()
            bal_alm = df_bal_alm_global[df_bal_alm_global['CLV_ACUI'] == clave_sel] if df_bal_alm_global is not None else pd.DataFrame()

            st.markdown("#### 📥 Entradas")
            v_r_total = buscar_valor(bal_ent, "R", es_total=True)
            st.dataframe(pd.DataFrame([
                {"Concepto": "Recarga vertical (Rv)", "Volumen (hm³)": buscar_valor(bal_ent, "Rv")},
                {"Concepto": "Retornos por riego (Rr)", "Volumen (hm³)": buscar_valor(bal_ent, "Rr")},
                {"Concepto": "Entrada horizontal subterránea (Eh)", "Volumen (hm³)": buscar_valor(bal_ent, "Eh")},
                {"Concepto": "Entrada horizontal salobre (Ehs)", "Volumen (hm³)": buscar_valor(bal_ent, "Ehs")},
                {"Concepto": "Recarga inducida (Ri)", "Volumen (hm³)": buscar_valor(bal_ent, "Ri")}
            ]).style.format({"Volumen (hm³)": "{:,.1f}"}), use_container_width=True, hide_index=True)
            if st.button("🔎 Ver tabla de cálculo: Entrada horizontal subterránea (Eh)", type="secondary", key="btn_eh"): modal_tablas_calculo(clave_sel, "Eh")

            st.markdown("#### 📤 Salidas")
            st.dataframe(pd.DataFrame([
                {"Concepto": "Bombeo (B)", "Volumen (hm³)": buscar_valor(bal_sal, "B")},
                {"Concepto": "Salida horizontal subterránea (Sh)", "Volumen (hm³)": buscar_valor(bal_sal, "Sh")},
                {"Concepto": "Salida horizontal por bombeo (Ssb)", "Volumen (hm³)": buscar_valor(bal_sal, "Ssb")},
                {"Concepto": "Evapotranspiración Real (ETR)", "Volumen (hm³)": buscar_valor(bal_sal, "ETR")},
                {"Concepto": "Flujo base (Dfb)", "Volumen (hm³)": buscar_valor(bal_sal, "Dfb") or buscar_valor(bal_sal, "Fb")},
                {"Concepto": "Descarga de manantiales (Dm)", "Volumen (hm³)": buscar_valor(bal_sal, "Dm")}
            ]).style.format({"Volumen (hm³)": "{:,.1f}"}), use_container_width=True, hide_index=True)
            
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                if st.button("🔎 Ver tabla de cálculo: Salida horizontal subterránea (Sh)", type="secondary", key="btn_sh"): modal_tablas_calculo(clave_sel, "Sh")
            with col_s2:
                if st.button("🔎 Ver tabla de cálculo: Evapotranspiración Real (ETR)", type="secondary", key="btn_etr"): modal_tablas_calculo(clave_sel, "ETR")

            st.markdown("#### 🧊 Cambio de almacenamiento ΔV(S)")
            st.dataframe(pd.DataFrame([{"Concepto": "ΔV(S)", "Volumen (hm³)": buscar_valor(bal_alm, "ΔV") or buscar_valor(bal_alm, "V(S)")}]).style.format({"Volumen (hm³)": "{:,.1f}"}), use_container_width=True, hide_index=True)
            if st.button("🔎 Ver tabla de cálculo: Cambio de Almacenamiento ΔV(S)", type="secondary", key="btn_dvs"): modal_tablas_calculo(clave_sel, "ΔV(S)")

            v_dnc_total = 0.0
            if not bal_sal.empty and 'DNC_hm3' in bal_sal.columns:
                match_dnc = bal_sal[bal_sal['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, na=False)]
                if not match_dnc.empty:
                    val_crudo = match_dnc.iloc[-1]['DNC_hm3']
                    if pd.isna(val_crudo) or str(val_crudo).strip().lower() in ['none', '', 'nan']: v_dnc_total = 0.0
                    else:
                        try: v_dnc_total = float(val_crudo)
                        except ValueError: v_dnc_total = 0.0
                else:
                    bal_sal_limpia = bal_sal['DNC_hm3'].astype(str).replace(['None', 'none', '', 'NaN'], '0')
                    v_dnc_total = pd.to_numeric(bal_sal_limpia, errors='coerce').fillna(0).sum()

            v_veas = 0.0
            if df_veas_global is not None:
                veas_match = df_veas_global[df_veas_global['CLAVE'] == clave_sel]
                if not veas_match.empty: v_veas = float(veas_match.iloc[0]['VEAS_hm3'])

            val_dma = round(v_r_total, 1) - round(v_dnc_total, 1) - v_veas

            st.markdown("#### 🧮 Cálculo de la DMA")
            st.dataframe(pd.DataFrame([
                {"Concepto": "Recarga total (R)", "Volumen (hm³)": f"{round(v_r_total, 1):,.1f}"},
                {"Concepto": "Descarga natural comprometida (DNC)", "Volumen (hm³)": f"{round(v_dnc_total, 1):,.1f}"},
                {"Concepto": "Volumen de extracción (VEAS)", "Volumen (hm³)": f"{v_veas:,.6f}"}
            ]), use_container_width=True, hide_index=True)
            st.divider()
            st.metric(label="Disponibilidad Media Anual (DMA)", value=f"{val_dma:,.6f} hm³")
            st.info(parrafo_dma_ia)

        # =======================================================
        # 🤖 ASISTENTE IA (MODAL AISLADO + CÍRCULO PERFECTO)
        # =======================================================
        @st.fragment
        def renderizar_boton_ia_flotante():
            # 1. El botón dentro del fragmento garantiza que al darle clic, la página y el mapa NO se recarguen
            if st.button("✨", type="primary", key="btn_ia_flotante_unico"):
                contexto_global_str = construir_contexto_completo(
                    clave_ac=clave_sel,
                    nombre_ac=nombre_ac,
                    estado=estado_seleccionado,
                    datos_ac=datos_ac,
                    parrafo_vol=parrafo_vol_ia,
                    parrafo_aprov=parrafo_aprov_ia,
                    parrafo_dma=parrafo_dma_ia,
                    df_resumen=df_resumen,
                    conteo_usos=conteo_usos,
                    df_bal_ent=df_bal_ent_global,
                    df_bal_sal=df_bal_sal_global,
                    df_bal_alm=df_bal_alm_global,
                    df_verts=df_vertices_global,
                    df_flujo_ent=df_flujo_ent_global,
                    df_flujo_sal=df_flujo_sal_global,
                    df_etr=df_etr_global,
                    df_alm=df_almacenamiento_global,
                    dato_zona_disp=dato_zona_disp
                )
                modal_chat_local(clave_sel, nombre_ac, contexto_global_str)

        # Invocamos el botón
        renderizar_boton_ia_flotante()

    else:
        st.info("👈 Selecciona un Acuífero en el panel lateral para ver su información.")
else:
    st.info("👈 Por favor, Selecciona un Estado en el panel lateral para comenzar.")

# =======================================================
# ⚙️ INYECCIÓN JAVASCRIPT (DISEÑO PERFECTO Y MUTATION OBSERVER)
# =======================================================
components.html(
    """
    <script>
    const doc = window.parent.document;
    
    function aplicarEstilosCirculares() {
        // 1. Buscamos el botón por el emoji
        const botones = doc.querySelectorAll('button');
        let btnIA = null;
        
        botones.forEach(b => {
            if(b.innerText.includes('✨')) {
                btnIA = b;
            }
        });

        if(!btnIA) return;
        
        // Quitamos tooltips nativos molestos
        btnIA.removeAttribute('title');
        
        // 2. FORZAMOS EL CÍRCULO PERFECTO
        btnIA.style.setProperty('width', '60px', 'important');
        btnIA.style.setProperty('height', '60px', 'important');
        btnIA.style.setProperty('min-width', '60px', 'important');
        btnIA.style.setProperty('min-height', '60px', 'important');
        btnIA.style.setProperty('border-radius', '50%', 'important');
        btnIA.style.setProperty('background-color', '#9F2241', 'important');
        btnIA.style.setProperty('color', 'white', 'important');
        btnIA.style.setProperty('padding', '0', 'important');
        btnIA.style.setProperty('margin', '0', 'important');
        btnIA.style.setProperty('border', 'none', 'important');
        btnIA.style.setProperty('box-shadow', '0px 6px 15px rgba(0,0,0,0.3)', 'important');
        btnIA.style.setProperty('display', 'flex', 'important');
        btnIA.style.setProperty('align-items', 'center', 'important');
        btnIA.style.setProperty('justify-content', 'center', 'important');
        btnIA.style.setProperty('transition', 'transform 0.2s ease, background-color 0.2s ease', 'important');
        
        // 3. LA MAGIA CONTRA EL CUADRADO: Anulamos el padding de los divs ocultos de Streamlit
        const hijos = btnIA.querySelectorAll('*');
        hijos.forEach(hijo => {
            hijo.style.setProperty('background-color', 'transparent', 'important');
            hijo.style.setProperty('padding', '0', 'important');
            hijo.style.setProperty('margin', '0', 'important');
            hijo.style.setProperty('min-width', '0', 'important');
        });
        
        // Agrandamos la estrella
        const p = btnIA.querySelector('p');
        if(p) {
            p.style.setProperty('font-size', '28px', 'important');
            p.style.setProperty('line-height', '1', 'important');
        }
        
        // Efecto Hover
        btnIA.onmouseover = function() {
            this.style.setProperty('transform', 'scale(1.15)', 'important');
            this.style.setProperty('background-color', '#691C32', 'important');
        };
        btnIA.onmouseout = function() {
            this.style.setProperty('transform', 'scale(1)', 'important');
            this.style.setProperty('background-color', '#9F2241', 'important');
        };

        // 4. Aislar la caja contenedora y hacerla flotar
        let contenedor = btnIA.closest('.element-container');
        if(!contenedor) {
            const wrapper = btnIA.closest('div[data-testid="stButton"]');
            if(wrapper) contenedor = wrapper.parentElement;
        }
        
        if(contenedor) {
            contenedor.style.setProperty('position', 'fixed', 'important');
            contenedor.style.setProperty('bottom', '30px', 'important');
            contenedor.style.setProperty('right', '30px', 'important');
            contenedor.style.setProperty('width', '60px', 'important');
            contenedor.style.setProperty('height', '60px', 'important');
            contenedor.style.setProperty('z-index', '999999', 'important');
        }
    }

    // 5. VIGÍA SILENCIOSO: Reemplazamos el reloj (setInterval) por un MutationObserver.
    // Esto evita parpadeos al hacer clic, ya que solo aplica CSS si Streamlit cambia algo en el DOM.
    const observer = new MutationObserver(() => {
        aplicarEstilosCirculares();
    });
    
    // Iniciar observación
    observer.observe(doc.body, { childList: true, subtree: true });
    
    // Ejecución inicial
    setTimeout(aplicarEstilosCirculares, 50);
    
    </script>
    """, height=0, width=0)