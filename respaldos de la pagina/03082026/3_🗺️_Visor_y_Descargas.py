# -*- coding: utf-8 -*-
import streamlit.components.v1 as components
from streamlit_folium import st_folium
import google.generativeai as genai
from folium import plugins
from pathlib import Path
import geopandas as gpd
import streamlit as st
import pandas as pd
import requests
import tempfile
import folium
import time
import io
import os

from pathlib import Path
from core.generador_word import (inyectar_tabla_vertices_en_word, inyectar_tabla_flujo_en_word,
                                inyectar_tabla_almacenamiento_en_word, inyectar_tabla_evapotranspiracion_en_word, modificar_censo_y_bombeo)

# =======================================================
# 📌 GESTOR DE RUTAS (NIVEL ENTERPRISE)
# =======================================================
DIRECTORIO_RAIZ = Path(__file__).resolve().parent.parent
CARPETA_DATOS = DIRECTORIO_RAIZ / "data"



from estandarizador_acuiferos import ejecutar_estandarizacion_v31
# 1. Configuración general

def obtener_secreto(clave, default=None):
    try:
        if hasattr(st, "secrets"):
            try:
                return st.secrets.get(clave, default)
            except Exception:
                pass
        valor = os.getenv(clave)
        return valor if valor is not None else default
    except Exception:
        return default

# =======================================================
# --- NUEVO: CONFIGURACIÓN INTELIGENTE DE IA (GEMINI) ---
# =======================================================
api_key_geo = obtener_secreto("GEMINI_API_KEY")
ia_disponible = False
modelo_elegido = None

if api_key_geo:
    try:
        genai.configure(api_key=api_key_geo)
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'flash' in m.name.lower():
                    modelo_elegido = m.name
                    break
        if not modelo_elegido:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    modelo_elegido = m.name
                    break
        if modelo_elegido:
            model = genai.GenerativeModel(modelo_elegido)
            ia_disponible = True
    except Exception as e:
        st.error(f"Falla de conexión con Google Gemini: {e}")
        pass

# =======================================================
# --- CSS OFICIAL Y BANNER COMPACTO (CONAGUA) ---
# =======================================================
css_oficial = """
<style>
    /* 1. Pintar todos los títulos de guinda */
    h1, h2, h3, h4, h5, h6 { color: #691C32 !important; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    
    /* 2. Compactar el espacio muerto gigante de Streamlit en la parte superior */
    .block-container { padding-top: 1.9rem !important; padding-bottom: 1rem !important; }
    
    /* 3. Reducir márgenes entre títulos y textos */
    div[data-testid="stMarkdownContainer"] p { margin-bottom: 0.2rem !important; }
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
st.subheader("🗺️ Resumen Técnico de consulta")
st.caption("Filtra por estado, selecciona el acuífero y enciende las capas espaciales para visualizar recortes exactos.")


# --- FUNCIONES GLOBALES DE LIMPIEZA Y FORMATO ---
def limpiar_texto(valor):
    if pd.isna(valor) or str(valor).strip() == "" or str(valor) == "nan" or str(valor) == "None": return None
    texto = str(valor).strip()
    try: return texto.encode('latin1').decode('utf-8')
    except: return texto

def formatear_fecha(fecha_cruda):
    if pd.isna(fecha_cruda) or str(fecha_cruda).strip() in ["", "nan", "None", "S/F", "S/D"]: 
        return "S/F"
    try:
        texto = str(fecha_cruda).replace('[', '').replace(']', '').replace("'", "").replace('"', '').strip()
        if 'T' in texto:
            fecha_limpia = texto.split('T')[0]
        else:
            fecha_limpia = texto.split(' ')[0]
            
        if fecha_limpia[:4].isdigit() and len(fecha_limpia) >= 8:
            dt = pd.to_datetime(fecha_limpia, errors='coerce')
        else:
            dt = pd.to_datetime(fecha_limpia, errors='coerce', dayfirst=True)
            
        if pd.notna(dt): 
            return dt.strftime('%d/%m/%Y') 
        else: 
            return fecha_limpia.replace('-', '/')
    except: 
        return str(fecha_cruda)

def procesar_link_drive(url):
    if not isinstance(url, str) or not url: return None
    try:
        if "/d/" in url: return url.split("/d/")[1].split("/")[0]
        elif "id=" in url: return url.split("id=")[1].split("&")[0]
        return None
    except: return None

# --- CARGA DINÁMICA DE DATOS ---
@st.cache_data
def cargar_datos():
    ruta = CARPETA_DATOS / "Acuiferos_Dashboard_V4.geojson"
    if not ruta.exists(): return None
    return gpd.read_file(ruta, encoding="utf-8")

@st.cache_data
def cargar_fraccion(nombre_capa):
    ruta_parquet = CARPETA_DATOS / f"Fracciones_{nombre_capa}.parquet"
    if ruta_parquet.exists(): return gpd.read_parquet(ruta_parquet)
    ruta_geojson = CARPETA_DATOS / f"Fracciones_{nombre_capa}.geojson"
    if ruta_geojson.exists(): return gpd.read_file(ruta_geojson, encoding="utf-8")
    return None

@st.cache_data
def cargar_repda():
    ruta_repda = CARPETA_DATOS / "REPDA.xlsx"
    if ruta_repda.exists():
        try:
            df = pd.read_excel(ruta_repda)
            if 'Clave de acuífero' in df.columns:
                df['Clave de acuífero'] = df['Clave de acuífero'].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(4)
            return df
        except: return None
    return None

@st.cache_data
def cargar_aprovechamientos():
    ruta_aprov = CARPETA_DATOS / "Aprovechamientos.xlsx"
    if ruta_aprov.exists():
        try:
            df = pd.read_excel(ruta_aprov)
            if 'Cve_Acuif' in df.columns:
                df['Cve_Acuif'] = df['Cve_Acuif'].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(4)
            return df
        except: return None
    return None

@st.cache_data
def cargar_links_mapas():
    ruta_links = CARPETA_DATOS / "Links.csv"
    if ruta_links.exists():
        try:
            df = pd.read_csv(ruta_links)
            if 'clave' in df.columns:
                df['clave'] = df['clave'].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(4)
            return df
        except: return None
    return None

@st.cache_data
def cargar_resumen_dma():
    ruta_resumen = CARPETA_DATOS / "Resumen_rev.xlsx"
    if ruta_resumen.exists():
        try:
            df = pd.read_excel(ruta_resumen, header=4)
            if 'Clave' in df.columns:
                df['Clave'] = df['Clave'].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(4)
            return df
        except: return None
    return None
    
@st.cache_data
def cargar_zonas_disponibilidad():
    ruta = CARPETA_DATOS / "ZONAS_DE_DISPONIBILIDAD.xlsx"
    if ruta.exists():
        try:
            df = pd.read_excel(ruta)
            if 'CLAVE DEL ACUÍFERO' in df.columns:
                df['CLAVE DEL ACUÍFERO'] = df['CLAVE DEL ACUÍFERO'].astype(str).str.replace('.0', '', regex=False).str.strip().str.zfill(4)
            return df
        except:
            return None
    return None

@st.cache_data
def cargar_vertices():
    ruta_vertices = CARPETA_DATOS / "Vertices.xlsx"
    if ruta_vertices.exists():
        try:
            df = pd.read_excel(ruta_vertices, dtype={'ID_ACUIFERO': str})
            if 'ID_ACUIFERO' in df.columns:
                df['ID_ACUIFERO'] = df['ID_ACUIFERO'].str.replace('.0', '', regex=False).str.strip().str.zfill(4)
            return df
        except Exception as e:
            return None
    return None

@st.cache_data
def cargar_enlaces_docs():
    ruta = CARPETA_DATOS / "Reporte de Enlaces Acuíferos - 5_8_2026 - Hoja 1.csv"
    if ruta.exists():
        try:
            df = pd.read_csv(ruta)
            df['CLAVE_ACUIFERO'] = df['CLAVE_ACUIFERO'].astype(str).str.zfill(4)
            return df
        except: return None
    return None

@st.cache_data
def cargar_flujo_entradas():
    ruta = CARPETA_DATOS / "Flujo_Horizontal_Entradas.parquet"
    if ruta.exists(): return pd.read_parquet(ruta)
    return None

@st.cache_data
def cargar_flujo_salidas():
    ruta = CARPETA_DATOS / "Flujo_Horizontal_Salidas.parquet"
    if ruta.exists(): return pd.read_parquet(ruta)
    return None

@st.cache_data
def cargar_almacenamiento():
    ruta = CARPETA_DATOS / "Cambio_Almacenamiento.parquet"
    if ruta.exists(): return pd.read_parquet(ruta)
    return None

@st.cache_data
def cargar_evapotranspiracion():
    ruta = CARPETA_DATOS / "Evapotranspiracion.parquet"
    if ruta.exists(): return pd.read_parquet(ruta)
    return None

@st.cache_data
def cargar_balance_hidro_entradas():
    ruta = CARPETA_DATOS / "Balance_Hidro_Entradas.parquet"
    if ruta.exists(): return pd.read_parquet(ruta)
    return None

@st.cache_data
def cargar_balance_hidro_salidas():
    ruta = CARPETA_DATOS / "Balance_Hidro_Salidas.parquet"
    if ruta.exists(): return pd.read_parquet(ruta)
    return None

@st.cache_data
def cargar_balance_hidro_almacenamiento():
    ruta = CARPETA_DATOS / "Balance_Hidro_Almacenamiento.parquet"
    if ruta.exists(): return pd.read_parquet(ruta)
    return None

@st.cache_data
def cargar_veas():
    ruta = CARPETA_DATOS / "VEAS_Administrativo.parquet"
    if ruta.exists(): return pd.read_parquet(ruta)
    return None

# =======================================================
# 🌟 VARIABLES GLOBALES
# =======================================================
gdf_maestro = cargar_datos()
df_repda_global = cargar_repda()
df_aprov_global = cargar_aprovechamientos()
df_links_global = cargar_links_mapas()
df_resumen_global = cargar_resumen_dma()
df_zonas_global = cargar_zonas_disponibilidad()
df_vertices_global = cargar_vertices()
df_enlaces_docs = cargar_enlaces_docs()
df_flujo_ent_global = cargar_flujo_entradas() 
df_flujo_sal_global = cargar_flujo_salidas()
df_almacenamiento_global = cargar_almacenamiento()
df_etr_global = cargar_evapotranspiracion()
df_bal_ent_global = cargar_balance_hidro_entradas()
df_bal_sal_global = cargar_balance_hidro_salidas()
df_bal_alm_global = cargar_balance_hidro_almacenamiento()
df_veas_global = cargar_veas()




# =======================================================
# --- FUNCIÓN POP-UP (ST.DIALOG) PARA LA IA (STREAMING) ---
# =======================================================
@st.dialog("✨ Asistente de IA de CONAGUA", width="large")
def modal_chat(clave_ac, ctx):
    chat_history_key = f"chat_history_{clave_ac}"
    if chat_history_key not in st.session_state:
        st.session_state[chat_history_key] = []
        
    if len(st.session_state[chat_history_key]) >= 6:
        st.session_state[chat_history_key] = []
        st.info("🧹 Historial reiniciado para mantener velocidad óptima.")
        
    # Dibujar el historial anterior
    for message in st.session_state[chat_history_key]:
        avatar_img = "👤" if message["role"] == "user" else "✨"
        with st.chat_message(message["role"], avatar=avatar_img):
            st.markdown(message["content"])
            
    if prompt := st.chat_input("Ej: Haz un resumen de la ficha administrativa del acuífero"):
        st.session_state[chat_history_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
            
        with st.chat_message("assistant", avatar="✨"):
            # Usamos write_stream para un efecto "ChatGPT" en tiempo real
            try:
                full_prompt = f"{ctx}\n\nPREGUNTA DEL USUARIO:\n{prompt}"
                
                # Pedimos a Gemini que envíe la respuesta en "paquetes" (chunks)
                response = model.generate_content(full_prompt, stream=True)
                
                def generador_respuestas():
                    for chunk in response:
                        yield chunk.text
                
                # Streamlit pinta mágicamente el texto conforme va llegando
                respuesta_texto = st.write_stream(generador_respuestas)
                st.session_state[chat_history_key].append({"role": "assistant", "content": respuesta_texto})
                
            except Exception as e:
                st.error(f"Error en IA: Verifique su clave de API. Detalle: {e}")

# =======================================================
# --- FUNCIÓN POP-UP PARA TABLA DE VÉRTICES EN EXCEL ---
# =======================================================
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
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Aún no se ha digitalizado el catálogo de vértices para este acuífero.")
    else:
        st.error("Archivo 'Vertices.xlsx' no encontrado.")

# =======================================================
# --- LÓGICA PRINCIPAL (INTERFAZ DE USUARIO) ---
# =======================================================
    
if gdf_maestro is not None:
    
    st.sidebar.header("🔍 Panel de Control")
    lista_estados = sorted(gdf_maestro['NOM_EDO'].dropna().astype(str).apply(limpiar_texto).unique())
    estado_seleccionado = st.sidebar.selectbox("1. Estado:", lista_estados, index=None, placeholder="Elige un estado...")
    
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
        
        ver_mapa_geo = False
        file_id = None
        if seleccion_final:
            clave_sel = seleccion_final.split(" - ")[0]
            st.sidebar.markdown("---")
            st.sidebar.subheader("⛰️ Mapa Geológico")
            link_encontrado = False
            if df_links_global is not None and 'clave' in df_links_global.columns:
                link_filtrado = df_links_global[df_links_global['clave'] == clave_sel]
                if not link_filtrado.empty:
                    link_crudo = link_filtrado.iloc[0].get('link')
                    file_id = procesar_link_drive(link_crudo)
                    if file_id:
                        link_encontrado = True
                        url_descarga = f"https://drive.google.com/uc?export=download&id={file_id}"
                        st.sidebar.link_button("⬇️ Descargar Mapa (PNG)", url=url_descarga, use_container_width=True)
                        ver_mapa_geo = st.sidebar.toggle("👁️ Visualizar Mapa Geológico")
            if not link_encontrado:
                st.sidebar.info("📂 Mapa geológico próximamente disponible.")

        st.sidebar.markdown("---")
        contador_html = f"""
        <div style="text-align: center;">
            <p style="font-size: 13px; color: #691C32; font-weight: bold; margin-bottom: 5px;">📊 Visitas al Geovisor</p>
            <img src="https://komarev.com/ghpvc/?username=JBarreraM89-Geovisor&label=VISITAS&color=9F2241&style=flat&t={time.time()}" alt="Contador">
        </div>
        """
        st.sidebar.markdown(contador_html, unsafe_allow_html=True)
        
        st.sidebar.markdown("<br>", unsafe_allow_html=True) 
        disclaimer_lateral = """
        <div style="background-color: #fce4e4; padding: 15px; border-radius: 8px; border: 1px solid #f5c6c6; text-align: justify; margin-bottom: 10px; box-shadow: inset 0px 0px 5px rgba(0,0,0,0.05);">
            <p style="font-size: 11.5px; color: #9F2241; font-weight: 600; margin: 0; line-height: 1.4;">
            ⚠️ <b>AVISO IMPORTANTE:</b><br>Esta plataforma es una herramienta de consulta para uso estrictamente interno de la Gerencia de Aguas Subterráneas. La información y recortes espaciales aquí mostrados no tienen validez legal ni carácter de documento oficial.
            </p>
        </div>
        """
        st.sidebar.markdown(disclaimer_lateral, unsafe_allow_html=True)

        if seleccion_final:
            datos_filtrados = gdf_filtrado_estado[gdf_filtrado_estado['CLV_ACUI'].astype(str).apply(limpiar_texto) == clave_sel].iloc[0]
            
            # ====================================================
            # 🧠 PRE-CÁLCULO DE PÁRRAFOS (BOMBEO Y VOLÚMENES)
            # ====================================================
            parrafo_vol_ia = "No hay información de volúmenes REPDA disponible."
            if df_repda_global is not None:
                repda_filtrado = df_repda_global[df_repda_global['Clave de acuífero'] == clave_sel]
                if not repda_filtrado.empty:
                    datos_repda = repda_filtrado.iloc[0]
                    exclude_cols = ['Clave de acuífero', 'Acuífero', 'Volumen total (hm3/año)', 'Porcentaje Total']
                    vol_total = float(datos_repda.get('Volumen total (hm3/año)', 0.0)) if pd.notna(datos_repda.get('Volumen total (hm3/año)')) else 0.0
                    registros = []
                    for col in df_repda_global.columns:
                        if col not in exclude_cols:
                            vol = float(datos_repda.get(col, 0.0)) if pd.notna(datos_repda.get(col)) else 0.0
                            if vol > 0:
                                pct = (vol / vol_total) * 100 if vol_total > 0 else 0.0
                                registros.append({"Tipo de Uso": col.replace(" (hm3/año)", "").strip(), "Volumen (hm³/año)": vol, "Porcentaje (%)": pct})
                    if registros:
                        df_resumen = pd.DataFrame(registros).sort_values(by="Volumen (hm³/año)", ascending=False).reset_index(drop=True)
                        df_texto = df_resumen[df_resumen['Volumen (hm³/año)'] >= 0.1].copy().reset_index(drop=True)
                        if not df_texto.empty:
                            fragmentos = []
                            for i, row in df_texto.iterrows():
                                uso_crudo = row['Tipo de Uso'].strip()
                                nombre_uso = {"Agrícola": "uso agrícola", "Público Urbano": "uso público-urbano", "Industrial": "uso industrial", "Pecuario": "uso pecuario", "Doméstico": "uso doméstico", "Acuacultura": "uso de acuacultura", "Diferentes usos": "diferentes usos", "Servicios": "servicios", "Comercio": "comercio", "Otros": "otros usos"}.get(uso_crudo, uso_crudo.lower())
                                frag = f"{row['Volumen (hm³/año)']:.1f} hm³/año ({row['Porcentaje (%)']:.1f} %) " + ("corresponde a " if i == 0 else "a ") + nombre_uso
                                fragmentos.append(frag)
                            texto_enumerado = ", ".join(fragmentos[:-1]) + f", y {fragmentos[-1]}" if len(fragmentos) > 1 else fragmentos[0]
                            parrafo_vol_ia = f"El volumen total de extracción para esa fecha asciende a {vol_total:.1f} hm³/año del cual {texto_enumerado}."

            parrafo_aprov_ia = "No hay información de conteo de aprovechamientos disponible."
            if df_aprov_global is not None:
                aprov_filtrado = df_aprov_global[df_aprov_global['Cve_Acuif'] == clave_sel]
                if not aprov_filtrado.empty:
                    conteo_usos = aprov_filtrado['Uso'].value_counts().reset_index()
                    conteo_usos.columns = ['Tipo de Uso', 'Cantidad']
                    total_aprov = conteo_usos['Cantidad'].sum()
                    conteo_usos['Porcentaje (%)'] = (conteo_usos['Cantidad'] / total_aprov) * 100
                    fragmentos_aprov = []
                    for i, row in conteo_usos.iterrows():
                        uso_crudo = str(row['Tipo de Uso']).strip()
                        cant = row['Cantidad']
                        pct_float = row['Porcentaje (%)']
                        diccionario_usos_aprov = {"Agrícola": "uso agrícola", "Público Urbano": "uso público-urbano", "Público-Urbano": "uso público-urbano", "Industrial": "uso industrial", "Pecuario": "uso pecuario", "Doméstico": "uso doméstico", "Acuacultura": "acuacultura", "Diferentes usos": "diferentes usos", "Diferentes Usos": "diferentes usos", "Servicios": "servicios", "Agroindustrial": "uso agroindustrial", "Comercio": "comercio", "Otros": "otros usos"}
                        nombre_uso = diccionario_usos_aprov.get(uso_crudo, uso_crudo.lower())
                        str_pct = "" if (cant == 1 or pct_float < 0.1) else f" ({pct_float:.1f} %)"
                        cant_formateada = f"{cant:,}"
                        if i == 0:
                            frag = f"{cant_formateada}{str_pct} se destinan a {nombre_uso}"
                            frag = frag.replace("a uso", "al uso") 
                        else: frag = f"{cant_formateada}{str_pct} a {nombre_uso}"
                        fragmentos_aprov.append(frag)
                    if len(fragmentos_aprov) > 1: texto_aprov = ", ".join(fragmentos_aprov[:-1]) + f" y {fragmentos_aprov[-1]}"
                    else: texto_aprov = fragmentos_aprov[0]
                    parrafo_aprov_ia = f"De acuerdo con el Registro Público Nacional del Agua (REPNA) con fecha de corte al 30 de septiembre del 2025, se reportan un total de {total_aprov:,} aprovechamientos de agua subterránea, de los cuales {texto_aprov}."

            dato_zona_disp = "Sin información"
            if df_zonas_global is not None:
                zona_filtrada = df_zonas_global[df_zonas_global['CLAVE DEL ACUÍFERO'] == clave_sel]
                if not zona_filtrada.empty:
                    val_zona = zona_filtrada.iloc[0].get('ZONA DE DISPONIBILIDAD')
                    if pd.notna(val_zona): dato_zona_disp = str(val_zona).strip()
            
            col1, col2 = st.columns([1.2, 2])
            
            with col1:
                nombre_acuifero = limpiar_texto(datos_filtrados['NOM_ACUI'])
                clave_acuifero = limpiar_texto(datos_filtrados['CLV_ACUI'])
                
                st.header(f"📋 RESUMEN: {clave_acuifero} - {nombre_acuifero}")
                st.caption(f"Estado: {estado_seleccionado}")              

                @st.fragment
                def modulo_estandarizacion(clave_acuifero):
                    with st.container(border=True):
                        col_info, col_accion = st.columns([3.8, 1.2], vertical_alignment="center")
                        
                        with col_info:
                            st.markdown("""
                            <div id='iman-subir-caja'></div>
                            <style>
                            div[data-testid="stVerticalBlockBorderWrapper"]:has(#iman-subir-caja) {
                                margin-top: -35px !important; 
                                padding-top: 12px !important; padding-bottom: 12px !important;
                            }
                            button[kind="primary"] {
                                font-size: 12px !important; padding: 0.2rem 0.5rem !important; min-height: 2rem !important;
                                background-color: #9F2241 !important; color: white !important; border: 1px solid #9F2241 !important;
                                transition: background-color 0.3s ease !important;
                            }
                            button[kind="primary"]:hover {
                                background-color: #691C32 !important; border-color: #691C32 !important; color: white !important;
                            }
                            </style>
                            <div style="display: flex; align-items: center; gap: 15px;">
                                <div style="font-size: 26px; line-height: 1;">📄</div>
                                <div>
                                    <p style="margin: 0px; font-weight: 600; color: #691C32; font-size: 14px; line-height: 1.2;">Documento de Actualización-BAS</p>
                                    <p style="margin: 4px 0px 0px 0px; font-size: 11px; color: #666; line-height: 1.2;">Genera un nuevo documento con el formato actualizado a partir de la versión anterior almacenada en la base de datos.</p>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                        with col_accion:
                            if df_enlaces_docs is not None:
                                enlace_row = df_enlaces_docs[df_enlaces_docs['CLAVE_ACUIFERO'] == clave_acuifero]
                                if not enlace_row.empty:
                                    link_drive = enlace_row.iloc[0]['ENLACE_DRIVE']
                                    file_id = procesar_link_drive(link_drive) 
                                    doc_key = f"doc_listo_{clave_acuifero}"
                                    
                                    # Creamos un contenedor vacío para que el botón de descarga reemplace al de procesar
                                    boton_placeholder = st.empty()
                                    
                                    if doc_key not in st.session_state:
                                        if boton_placeholder.button("⚙️ Procesar", type="primary", use_container_width=True):
                                            
                                            with st.status("📄 Generando Documento Oficial...", expanded=True) as status:
                                                import requests
                                                import tempfile
                                                from estandarizador_acuiferos import ejecutar_estandarizacion_v31
                                                
                                                try:
                                                    st.write("☁️ Descargando formato base desde Drive...")
                                                    url_export = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
                                                    respuesta = requests.get(url_export)
                                                    
                                                    if respuesta.status_code == 200:
                                                        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_origen:
                                                            tmp_origen.write(respuesta.content)
                                                            ruta_origen = tmp_origen.name
                                                            
                                                        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_salida:
                                                            ruta_salida = tmp_salida.name
                                                            
                                                        st.write("⚙️ Estandarizando a Versión 3.1...")
                                                        ruta_plantilla = DIRECTORIO_RAIZ / "PLANTILLA_V3.1.docx" 
                                                        ejecutar_estandarizacion_v31(str(ruta_plantilla), ruta_origen, ruta_salida)
                                                        
                                                        st.write("📊 Inyectando datos vectoriales e hidrogeológicos...")
                                                        # Aquí enviamos las Variables Globales al módulo externo!
                                                        inyectar_tabla_vertices_en_word(ruta_salida, clave_acuifero, df_vertices_global)
                                                        inyectar_tabla_flujo_en_word(ruta_salida, clave_acuifero, df_flujo_ent_global, ["tabla", "entradas","flujo"], "Entradas")
                                                        inyectar_tabla_flujo_en_word(ruta_salida, clave_acuifero, df_flujo_sal_global, ["tabla", "salidas", "flujo"], "Salidas")
                                                        modificar_censo_y_bombeo(ruta_salida, parrafo_aprov_ia, parrafo_vol_ia)
                                                        inyectar_tabla_almacenamiento_en_word(ruta_salida, clave_acuifero, df_almacenamiento_global)
                                                        inyectar_tabla_evapotranspiracion_en_word(ruta_salida, clave_acuifero, df_etr_global)
                                                        
                                                        with open(ruta_salida, "rb") as f:
                                                            st.session_state[doc_key] = f.read()
                                                            
                                                        status.update(label="✅ ¡Documento Listo para Descarga!", state="complete", expanded=False)
                                                        # Forzamos una recarga para que el botón cambie mágicamente a "Descargar"
                                                        st.rerun()
                                                    else: 
                                                        status.update(label="❌ Error al conectar con Drive", state="error")
                                                except Exception as e: 
                                                    status.update(label=f"❌ Error crítico: {e}", state="error")
                                                    
                                    # Si el documento ya está en memoria, dibujamos el botón de descarga sobreescribiendo el placeholder
                                    if doc_key in st.session_state:
                                        boton_placeholder.download_button(
                                            label="⬇️ Descargar Archivo", data=st.session_state[doc_key],
                                            file_name=f"{clave_acuifero}_ESTANDARIZADO_V3.1.docx",
                                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                            type="primary", use_container_width=True
                                        )
                                                
                                else: st.info("Sin registro.")
                            else: st.error("Error BD.")
                
                modulo_estandarizacion(clave_sel)
                
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
                        fecha_lista = formatear_fecha(fecha_raw)
                        st.markdown(f"*({prefijo_fecha}{fecha_lista})* {nombre}")

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

                def mostrar_desde_fraccion_vertical(titulo_seccion, id_capa, campo_nombre, campo_fecha, prefijo_fecha="DOF: ", formato_titulo=False):
                    df_capa = cargar_fraccion(id_capa)
                    if df_capa is not None:
                        fraccion = df_capa[df_capa['CLV_ACUI'] == clave_sel]
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

                def mostrar_desde_fraccion_en_linea(titulo_seccion, id_capa, campo_nombre, campo_fecha, prefijo_fecha="DOF: ", formato_titulo=False):
                    df_capa = cargar_fraccion(id_capa)
                    if df_capa is not None:
                        fraccion = df_capa[df_capa['CLV_ACUI'] == clave_sel]
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

                tab_ficha, tab_repda, tab_aprov, tab_dma = st.tabs(["📋 Ficha Administrativa", "📊 Volúmenes", "💧 Aprovechamientos", "⚖️ Balance y Disponibilidad"])
                
                with tab_ficha:
                    with st.expander("📍 Límites Oficiales del Acuífero", expanded=True):
                        nombres_limites = datos_filtrados.get('excel_LIM_NOM')
                        fechas_limites = datos_filtrados.get('excel_LIM_FECHA')
                        if pd.notna(nombres_limites) and str(nombres_limites).strip() != "": 
                            mostrar_pares_en_parrafo("Acuerdo de Límites", nombres_limites, fechas_limites, prefijo_extra="DOF: ", es_fecha=True)
                        else: st.info("Información de límites en proceso de validación o no disponible.")
                        st.markdown("""<style>button[kind="secondary"] {color: #2980b9 !important; font-weight: bold !important; padding: 0 !important; margin-top: -15px !important; background-color: transparent !important;} button[kind="secondary"]:hover {color: #9F2241 !important; text-decoration: underline !important;}</style>""", unsafe_allow_html=True)
                        if st.button(" Ver Catálogo de Vértices de la Poligonal", type="secondary"): modal_vertices(clave_sel)
                    
                    with st.expander("⚖️ Decretos de Veda", expanded=True):
                        nombres_vedas = datos_filtrados.get('vedas_NOM_OFI')
                        fechas_vedas = datos_filtrados.get('vedas_FECHA_DOF')
                        tiene_vedas = pd.notna(nombres_vedas) and str(nombres_vedas).strip() != "" and str(nombres_vedas) != "nan"
                        if tiene_vedas: mostrar_pares_vertical("Decretos Registrados", nombres_vedas, fechas_vedas)
                        else: st.info("No se encontraron Decretos de Veda registrados para este acuífero.")

                    with st.expander("📜 Acuerdos Generales y Regulaciones", expanded=True):
                        nombres_acuerdos = datos_filtrados.get('acuerdos_generales_NOM_OFI')
                        fechas_acuerdos = datos_filtrados.get('acuerdos_generales_FECHA_DOF')
                        tiene_acuerdos = pd.notna(nombres_acuerdos) and str(nombres_acuerdos).strip() != "" and str(nombres_acuerdos) != "nan"
                        if tiene_acuerdos: mostrar_pares_vertical("Acuerdos Generales (Capa SIG)", nombres_acuerdos, fechas_acuerdos)
                        else: st.write("**Acuerdos Generales:** Sin información")
                        st.divider()
                        mostrar_pares_en_parrafo("Zonas Reglamentadas", datos_filtrados.get('zonas_reglamentadas_NOM_OFI'), datos_filtrados.get('zonas_reglamentadas_FECHA_DOF'), "DOF: ", es_fecha=True)
                        mostrar_pares_en_parrafo("Zonas de Reserva", datos_filtrados.get('zonas_reserva_NOM_OFI'), datos_filtrados.get('zonas_reserva_FECHA_DOF'), "DOF: ", es_fecha=True)
                        mostrar_pares_en_parrafo("Reglamentos", datos_filtrados.get('reglamentos_NOM_OFI'), datos_filtrados.get('reglamentos_FECHA_DOF'), "DOF: ", es_fecha=True)

                    with st.expander("🏛️ División Administrativa", expanded=True):
                        def formato_nombres(valor, proteger_primera=False):
                            texto_limpio = limpiar_texto(valor)
                            if texto_limpio is None: return None
                            if proteger_primera:
                                partes = texto_limpio.split(" ", 1)
                                if len(partes) > 1: return f"{partes[0].upper()} {partes[1].title()}"
                                else: return texto_limpio.upper()
                            else: return texto_limpio.title()
                        mostrar_dato("Organismo de Cuenca (Región Adm.)", formato_nombres(datos_filtrados.get('REGION_ADM'), proteger_primera=True))
                        unidad_adm = str(datos_filtrados.get('UNIDAD_ADM')).strip()
                        if unidad_adm.upper().startswith("DL"): mostrar_dato("Dirección Local", formato_nombres(unidad_adm, proteger_primera=True))
                        else: mostrar_dato("Dirección Local", None) 
                        mostrar_desde_fraccion_en_linea("Consejo de Cuenca", "consejos_cuenca", "NOMCONSEJC", "FECHA_INST", "Instalado: ", formato_titulo=True)
                        mostrar_pares_en_parrafo("COTAS", datos_filtrados.get('cotas_nom_cotas'), datos_filtrados.get('cotas_fecha_inst'), "Fecha: ", es_fecha=True)
                        st.write(f"**Zona de Disponibilidad:** {dato_zona_disp}")
                        st.divider()
                        mostrar_dato("Municipios (Totalmente contenidos)", datos_filtrados.get('municipios_TOTAL'))
                        mostrar_dato("Municipios (Parcialmente dentro)", datos_filtrados.get('municipios_PARCIAL'))
                        st.divider()
                        
                    with st.expander("🌾 Uso Agrícola", expanded=False):
                        mostrar_pares_en_parrafo("Distritos de Riego", datos_filtrados.get('distritos_riego_FIRST_NOMB'), datos_filtrados.get('distritos_riego_DISTID'))
                        mostrar_dato("Unidades de Riego", datos_filtrados.get('unidades_riego_rha'))

                    with st.expander("🌿 Medio Ambiente", expanded=False):
                        mostrar_desde_fraccion_vertical("Áreas Naturales Protegidas Federales", "anp_federal", "NOMBRE", "PRIM_DEC", "DOF: ")
                        mostrar_desde_fraccion_vertical("Áreas Naturales Protegidas Estatales", "anp_estatal", "NOMBRE", "ULT_DEC", "Últ. Dec: ")
                        mostrar_desde_fraccion_vertical("Sitios RAMSAR", "ramsar", "RAMSAR", "FECHA", "Fecha: ")
                        
                with tab_repda:
                    st.subheader("Resumen de Bombeo por Aprovechamiento")
                    if df_repda_global is not None:
                        repda_filtrado = df_repda_global[df_repda_global['Clave de acuífero'] == clave_sel]
                        if not repda_filtrado.empty:
                            datos_repda = repda_filtrado.iloc[0]
                            exclude_cols = ['Clave de acuífero', 'Acuífero', 'Volumen total (hm3/año)', 'Porcentaje Total']
                            vol_total = float(datos_repda.get('Volumen total (hm3/año)', 0.0)) if pd.notna(datos_repda.get('Volumen total (hm3/año)')) else 0.0
                            registros = []
                            for col in df_repda_global.columns:
                                if col not in exclude_cols:
                                    vol = float(datos_repda.get(col, 0.0)) if pd.notna(datos_repda.get(col)) else 0.0
                                    if vol > 0:
                                        pct = (vol / vol_total) * 100 if vol_total > 0 else 0.0
                                        registros.append({"Tipo de Uso": col.replace(" (hm3/año)", "").strip(), "Volumen (hm³/año)": vol, "Porcentaje (%)": pct})
                            if registros:
                                df_resumen = pd.DataFrame(registros).sort_values(by="Volumen (hm³/año)", ascending=False).reset_index(drop=True)
                                st.dataframe(df_resumen.style.format({"Volumen (hm³/año)": "{:.1f}", "Porcentaje (%)": "{:.1f}%"}), use_container_width=True, hide_index=True)
                                st.divider()
                                st.metric("Volumen Total Concesionado (hm³/año)", f"{vol_total:.1f}")
                                st.subheader("📝 Párrafo Redactado para Documento de Respaldo")
                                df_texto = df_resumen[df_resumen['Volumen (hm³/año)'] >= 0.1].copy().reset_index(drop=True)
                                if not df_texto.empty:
                                    fragmentos = []
                                    for i, row in df_texto.iterrows():
                                        uso_crudo = row['Tipo de Uso'].strip()
                                        nombre_uso = {"Agrícola": "uso agrícola", "Público Urbano": "uso público-urbano", "Industrial": "uso industrial", "Pecuario": "uso pecuario", "Doméstico": "uso doméstico", "Acuacultura": "uso de acuacultura", "Diferentes usos": "diferentes usos", "Servicios": "servicios", "Comercio": "comercio", "Otros": "otros usos"}.get(uso_crudo, uso_crudo.lower())
                                        frag = f"{row['Volumen (hm³/año)']:.1f} hm³/año ({row['Porcentaje (%)']:.1f} %) " + ("corresponde a " if i == 0 else "a ") + nombre_uso
                                        fragmentos.append(frag)
                                    texto_enumerado = ", ".join(fragmentos[:-1]) + f", y {fragmentos[-1]}" if len(fragmentos) > 1 else fragmentos[0]
                                    parrafo_vol_ia = f"El volumen total de extracción para esa fecha asciende a {vol_total:.1f} hm³/año del cual {texto_enumerado}."
                                    st.info(parrafo_vol_ia)
                                    st.code(parrafo_vol_ia, language="text")
                                else: st.warning("No hay usos con volumen suficiente (≥ 0.1 hm³/año) para generar el párrafo.")
                        else: st.warning(f"No se encontró la clave {clave_sel} en el archivo REPDA.")
                    else: st.error("No se pudo cargar el archivo REPDA. Verifica la ruta del Excel.")

                with tab_aprov:
                    st.subheader("Conteo de Aprovechamientos por Tipo de Uso")
                    if df_aprov_global is not None:
                        aprov_filtrado = df_aprov_global[df_aprov_global['Cve_Acuif'] == clave_sel]
                        if not aprov_filtrado.empty:
                            conteo_usos = aprov_filtrado['Uso'].value_counts().reset_index()
                            conteo_usos.columns = ['Tipo de Uso', 'Cantidad']
                            total_aprov = conteo_usos['Cantidad'].sum()
                            conteo_usos['Porcentaje (%)'] = (conteo_usos['Cantidad'] / total_aprov) * 100
                            st.dataframe(conteo_usos.style.format({"Porcentaje (%)": "{:.1f}%"}), use_container_width=True, hide_index=True)
                            st.divider()
                            st.metric("Total de Aprovechamientos Registrados", f"{total_aprov:,}")
                            st.subheader("📝 Párrafo Redactado para Documento de Respaldo")
                            fragmentos_aprov = []
                            for i, row in conteo_usos.iterrows():
                                uso_crudo = str(row['Tipo de Uso']).strip()
                                cant = row['Cantidad']
                                pct_float = row['Porcentaje (%)']
                                diccionario_usos_aprov = {"Agrícola": "uso agrícola", "Público Urbano": "uso público-urbano", "Público-Urbano": "uso público-urbano", "Industrial": "uso industrial", "Pecuario": "uso pecuario", "Doméstico": "uso doméstico", "Acuacultura": "acuacultura", "Diferentes usos": "diferentes usos", "Diferentes Usos": "diferentes usos", "Servicios": "servicios", "Agroindustrial": "uso agroindustrial", "Comercio": "comercio", "Otros": "otros usos"}
                                nombre_uso = diccionario_usos_aprov.get(uso_crudo, uso_crudo.lower())
                                str_pct = "" if (cant == 1 or pct_float < 0.1) else f" ({pct_float:.1f} %)"
                                cant_formateada = f"{cant:,}"
                                if i == 0:
                                    frag = f"{cant_formateada}{str_pct} se destinan a {nombre_uso}"
                                    frag = frag.replace("a uso", "al uso") 
                                else: frag = f"{cant_formateada}{str_pct} a {nombre_uso}"
                                fragmentos_aprov.append(frag)
                            if len(fragmentos_aprov) > 1: texto_aprov = ", ".join(fragmentos_aprov[:-1]) + f" y {fragmentos_aprov[-1]}"
                            else: texto_aprov = fragmentos_aprov[0]
                            parrafo_aprov_ia = f"De acuerdo con el Registro Público Nacional del Agua (REPNA) con fecha de corte al 30 de septiembre del 2025, se reportan un total de {total_aprov:,} aprovechamientos de agua subterránea, de los cuales {texto_aprov}."
                            st.info(parrafo_aprov_ia)
                            st.code(parrafo_aprov_ia, language="text")
                        else: st.warning(f"No se encontraron registros de aprovechamientos para la clave {clave_sel}.")
                    else: st.error("No se pudo cargar el archivo de Aprovechamientos. Verifica la ruta.")

                with tab_dma:
                    st.subheader("Balance de Aguas Subterráneas y Cálculo de la DMA")
                    st.caption("Valores de flujo y almacenamiento extraídos directamente de los Parquet")
                    parrafo_dma_ia = "No hay información de balance disponible."
                    
                    # ==========================================
                    # 🌟 NUEVO: DIÁLOGO CON TOTALES Y LIMPIEZA
                    # ==========================================
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
                                
                                # Totales y Promedios
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
                                                # Formato
                                                if "EVOLUCIÓN (m)" in col:
                                                    df_final.at[idx, col] = str(val_raw)
                                                elif any(x in col.upper() for x in ["VOLUMEN", "ΔV(S)", "EVOLUCIÓN MEDIA", "PROFUNDIDAD MEDIA", "% ETR", "SY", "ÁREA (KM²)"]):
                                                    df_final.at[idx, col] = "{:.1f}".format(float(val))
                                                elif any(x in col.upper() for x in ["LONGITUD B", "ANCHO A", "H₂-H₁", "PROFUNDIDAD MÁXIMA"]):
                                                    df_final.at[idx, col] = "{:.0f}".format(float(val))
                                                else:
                                                    df_final.at[idx, col] = "{:.4f}".format(float(val))
                                
                                # Aplicar estilo (Encabezados y Fila Total)
                                def aplicar_estilos(df):
                                    styler = df.style
                                    
                                    # Encabezados
                                    styler.set_table_styles([{
                                        'selector': 'th',
                                        'props': [('background-color', '#BDD7EE'), ('color', '#244062'), 
                                                  ('font-family', 'Noto Sans'), ('text-align', 'center'),
                                                  ('font-weight', 'bold'), ('border', '1px solid #dee2e6')]
                                    }])
                                    
                                    # Colorear fila de TOTAL o PROMEDIO
                                    # Convertimos toda la columna a string para buscar sin errores
                                    col0 = df.iloc[:, 0].astype(str).str.upper()
                                    mask = col0.str.contains("TOTAL|PROMEDIO", na=False)
                                    
                                    if mask.any():
                                        styler.map(
                                            lambda x: 'background-color: #BDD7EE', 
                                            subset=pd.IndexSlice[mask, :]
                                        )
                                        
                                    return styler
                                
                                st.write(f"**{config['titulo']}**")
                                st.dataframe(
                                    aplicar_estilos(df_final), 
                                    use_container_width=True, hide_index=True
                                )
                            else:
                                st.warning("No hay registros.")
                        else:
                            st.error("Archivo Parquet no cargado.")
                    
                    # Estilo para los botones tipo enlace
                    st.markdown("""<style>button[kind="secondary"] {color: #2980b9 !important; font-weight: 600 !important; padding: 0 !important; margin-top: 5px !important; margin-bottom: 15px !important; background-color: transparent !important;} button[kind="secondary"]:hover {color: #9F2241 !important; text-decoration: underline !important;}</style>""", unsafe_allow_html=True)
                    
                    # 1. 🌟 BUSCADOR INTELIGENTE EN PARQUETS RESUMEN
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

                    bal_ent = df_bal_ent_global[df_bal_ent_global['CLV_ACUI'] == clave_sel] if df_bal_ent_global is not None else pd.DataFrame()
                    bal_sal = df_bal_sal_global[df_bal_sal_global['CLV_ACUI'] == clave_sel] if df_bal_sal_global is not None else pd.DataFrame()
                    bal_alm = df_bal_alm_global[df_bal_alm_global['CLV_ACUI'] == clave_sel] if df_bal_alm_global is not None else pd.DataFrame()

                    # ==========================================
                    # 📥 MAPEO DE ENTRADAS
                    # ==========================================
                    val_rv = buscar_valor(bal_ent, "Rv")
                    val_rr = buscar_valor(bal_ent, "Rr")
                    val_eh = buscar_valor(bal_ent, "Eh")
                    val_ehs = buscar_valor(bal_ent, "Ehs")
                    val_ri = buscar_valor(bal_ent, "Ri")
                    val_r_total = buscar_valor(bal_ent, "R", es_total=True)

                    st.markdown("#### 📥 Entradas")
                    df_ent_ui = pd.DataFrame([
                        {"Concepto": "Recarga vertical (Rv)", "Volumen (hm³)": val_rv},
                        {"Concepto": "Retornos por riego (Rr)", "Volumen (hm³)": val_rr},
                        {"Concepto": "Entrada horizontal subterránea (Eh)", "Volumen (hm³)": val_eh},
                        {"Concepto": "Entrada horizontal salobre (Ehs)", "Volumen (hm³)": val_ehs},
                        {"Concepto": "Recarga inducida (Ri)", "Volumen (hm³)": val_ri}
                    ])
                    st.dataframe(df_ent_ui.style.format({"Volumen (hm³)": "{:,.1f}"}), use_container_width=True, hide_index=True)
                    
                    # Botón interactivo para Eh
                    if st.button("🔎 Ver tabla de cálculo: Entrada horizontal subterránea (Eh)", type="secondary", key="btn_eh"):
                        modal_tablas_calculo(clave_sel, "Eh")
                    
                    # ==========================================
                    # 📤 MAPEO DE SALIDAS
                    # ==========================================
                    val_b = buscar_valor(bal_sal, "B")
                    val_sh = buscar_valor(bal_sal, "Sh")
                    val_ssb = buscar_valor(bal_sal, "Ssb")
                    val_etr = buscar_valor(bal_sal, "ETR")
                    val_dfb = buscar_valor(bal_sal, "Dfb") or buscar_valor(bal_sal, "Fb")
                    val_dm = buscar_valor(bal_sal, "Dm")
                    
                    st.markdown("#### 📤 Salidas")
                    df_sal_ui = pd.DataFrame([
                        {"Concepto": "Bombeo (B)", "Volumen (hm³)": val_b},
                        {"Concepto": "Salida horizontal subterránea (Sh)", "Volumen (hm³)": val_sh},
                        {"Concepto": "Salida horizontal por bombeo (Ssb)", "Volumen (hm³)": val_ssb},
                        {"Concepto": "Evapotranspiración Real (ETR)", "Volumen (hm³)": val_etr},
                        {"Concepto": "Flujo base (Dfb)", "Volumen (hm³)": val_dfb},
                        {"Concepto": "Descarga de manantiales (Dm)", "Volumen (hm³)": val_dm}
                    ])
                    st.dataframe(df_sal_ui.style.format({"Volumen (hm³)": "{:,.1f}"}), use_container_width=True, hide_index=True)
                    
                    # Botones interactivos para Sh y ETR
                    col_s1, col_s2 = st.columns(2)
                    with col_s1:
                        if st.button("🔎 Ver tabla de cálculo: Salida horizontal subterránea (Sh)", type="secondary", key="btn_sh"):
                            modal_tablas_calculo(clave_sel, "Sh")
                    with col_s2:
                        if st.button("🔎 Ver tabla de cálculo: Evapotranspiración Real (ETR)", type="secondary", key="btn_etr"):
                            modal_tablas_calculo(clave_sel, "ETR")

                    # ==========================================
                    # 🧊 CAMBIO DE ALMACENAMIENTO (Tabla Independiente)
                    # ==========================================
                    val_dvas = buscar_valor(bal_alm, "ΔV") or buscar_valor(bal_alm, "V(S)")
                    
                    st.markdown("#### 🧊 Cambio de almacenamiento ΔV(S)")
                    df_alm_ui = pd.DataFrame([
                        {"Concepto": "ΔV(S)", "Volumen (hm³)": val_dvas}
                    ])
                    st.dataframe(df_alm_ui.style.format({"Volumen (hm³)": "{:,.1f}"}), use_container_width=True, hide_index=True)
                    
                    # Botón interactivo para ΔV(S)
                    if st.button("🔎 Ver tabla de cálculo: Cambio de Almacenamiento ΔV(S)", type="secondary", key="btn_dvs"):
                        modal_tablas_calculo(clave_sel, "ΔV(S)")
                    
                    # ==========================================
                    # 🧮 MAPEO DE ALMACENAMIENTO Y CÁLCULOS
                    # ==========================================
                    val_dnc_total = 0.0
                    if not bal_sal.empty and 'DNC_hm3' in bal_sal.columns:
                        match_dnc = bal_sal[bal_sal['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, na=False)]
                        if not match_dnc.empty:
                            try: val_dnc_total = float(match_dnc.iloc[-1]['DNC_hm3'])
                            except: pass
                        if val_dnc_total == 0.0:
                            val_dnc_total = pd.to_numeric(bal_sal['DNC_hm3'], errors='coerce').sum()

                    st.markdown("#### 🧮 Cálculo de la DMA")
                    
                    val_veas = 0.0
                    if df_veas_global is not None:
                        veas_filtrado = df_veas_global[df_veas_global['CLAVE'] == clave_sel]
                        if not veas_filtrado.empty:
                            try: val_veas = float(veas_filtrado.iloc[0]['VEAS_hm3'])
                            except: pass

                    # Aplicar fórmula: DMA = R - DNC - VEAS
                    val_dma = round(val_r_total, 1) - round(val_dnc_total, 1) - val_veas

                    df_cal = pd.DataFrame([
                        {"Concepto": "Recarga total (R)", "Volumen (hm³)": f"{round(val_r_total, 1):,.1f}"},
                        {"Concepto": "Descarga natural comprometida (DNC)", "Volumen (hm³)": f"{round(val_dnc_total, 1):,.1f}"},
                        {"Concepto": "Volumen de extracción (VEAS)", "Volumen (hm³)": f"{val_veas:,.6f}"}
                    ])
                    st.dataframe(df_cal, use_container_width=True, hide_index=True)
                    st.divider()
                    
                    st.metric(label="Disponibilidad Media Anual (DMA)", value=f"{val_dma:,.6f} hm³")
                    parrafo_dma_ia = f"La Disponibilidad Media Anual (DMA) calculada para este acuífero es de {val_dma:,.6f} hm³."

                ctx_admin = f"Acuífero Clave: {clave_acuifero}, Nombre: {nombre_acuifero}, Estado: {estado_seleccionado}. "
                ctx_admin += f"Región Administrativa: {limpiar_texto(datos_filtrados.get('REGION_ADM'))}. Dirección Local: {limpiar_texto(datos_filtrados.get('UNIDAD_ADM'))}. "
                limites_str = limpiar_texto(datos_filtrados.get('excel_LIM_NOM'))
                if limites_str: ctx_admin += f"Acuerdos de Límites: {limites_str}. "
                vedas_str = limpiar_texto(datos_filtrados.get('vedas_NOM_OFI'))
                if vedas_str: ctx_admin += f"Decretos de Veda: {vedas_str}. "
                acuerdos_str = limpiar_texto(datos_filtrados.get('acuerdos_generales_NOM_OFI'))
                if acuerdos_str: ctx_admin += f"Acuerdos Generales: {acuerdos_str}. "

                contexto_acuifero_ia = f"""
                Eres un asistente experto de CONAGUA especializado en aguas subterráneas.
                Tu tarea es responder basándote ÚNICAMENTE en la siguiente información del Acuífero {clave_acuifero} - {nombre_acuifero}. 
                INFORMACIÓN:
                {ctx_admin}
                REPDA: {parrafo_vol_ia}
                APROVECHAMIENTOS: {parrafo_aprov_ia}
                BALANCE Y DISPONIBILIDAD: {parrafo_dma_ia}
                """

                if ia_disponible:
                    st.sidebar.markdown("---")
                    if st.sidebar.button("✨ Preguntar al Asistente IA", type="primary", use_container_width=True):
                        modal_chat(clave_sel, contexto_acuifero_ia)

            with col2:
                st.header("🗺️ Visualizador Espacial")
                centroide = datos_filtrados.geometry.centroid
                
                m = folium.Map(location=[centroide.y, centroide.x], zoom_start=10, tiles="CartoDB positron", control_scale=True)
                b = datos_filtrados.geometry.bounds
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
                    datos_filtrados.geometry,
                    name="Límite del Acuífero",
                    style_function=lambda x: {'fillColor': '#3186cc', 'color': '#1a5276', 'weight': 3, 'fillOpacity': 0.2},
                    tooltip=folium.Tooltip(f"<b>Acuífero:</b> {limpiar_texto(datos_filtrados['NOM_ACUI'])}", style=estilo_acuifero, sticky=True)
                ).add_to(m)
                
                for capa_visual in capas_seleccionadas:
                    id_archivo, color_hex, campo_nombre = diccionario_capas[capa_visual]
                    gdf_frac = cargar_fraccion(id_archivo)
                    if gdf_frac is not None:
                        fraccion_local = gdf_frac[gdf_frac['CLV_ACUI'] == clave_sel]
                        if not fraccion_local.empty:
                            fraccion_segura = fraccion_local.copy()
                            columnas_atributos = [col for col in fraccion_segura.columns if col != 'geometry']
                            for col in columnas_atributos:
                                fraccion_segura[col] = fraccion_segura[col].apply(lambda x: limpiar_texto(x) if pd.notna(x) else x)
                            fraccion_segura[columnas_atributos] = fraccion_segura[columnas_atributos].astype(str)
                            def obtener_estilo_mosaico(feature, color_base, campo):
                                nombre = feature['properties'].get(campo, "X")
                                valor_texto = sum(ord(letra) for letra in str(nombre))
                                niveles_opacidad = [0.25, 0.45, 0.65, 0.85]
                                return {'fillColor': color_base, 'color': 'white', 'weight': 1.5, 'fillOpacity': niveles_opacidad[valor_texto % 4]}
                            estilo_tooltip_elegante = """background-color: rgba(255,255,255,0.95); border: 1px solid #dcdde1; border-radius: 8px; box-shadow: 0px 6px 12px rgba(0,0,0,0.15); color: #2f3640; font-family: 'Segoe UI', Roboto, sans-serif; font-size: 13px; white-space: normal; max-width: 85vw; min-width: 250px; padding: 10px;"""
                            folium.GeoJson(
                                fraccion_segura,
                                name=capa_visual, 
                                style_function=lambda feature, c=color_hex, cmp=campo_nombre: obtener_estilo_mosaico(feature, c, cmp),
                                highlight_function=lambda x, c=color_hex: {'fillColor': c, 'color': '#ffeb3b', 'weight': 3, 'fillOpacity': 0.9},
                                tooltip=folium.GeoJsonTooltip(fields=[campo_nombre], aliases=[f"<b>{capa_visual}</b><br>"], localize=True, sticky=True, labels=True, style=estilo_tooltip_elegante)
                            ).add_to(m)
                
                folium.LayerControl(position='topright', collapsed=True).add_to(m)
                st_folium(m, use_container_width=True, height=650, returned_objects=[])

                if ver_mapa_geo and file_id:
                    st.divider()
                    st.subheader(f"⛰️ Vista Previa: Mapa Geológico")
                    with st.spinner("Cargando imagen interactiva desde Google Drive..."):
                        url_iframe = f"https://drive.google.com/file/d/{file_id}/preview"
                        components.iframe(url_iframe, height=750, scrolling=True)
                        st.caption("🔍 Usa el ratón o los controles del recuadro para hacer zoom a la imagen.")
        else:
            st.info("👈 Selecciona un Acuífero en el panel lateral para ver su información.")
    else:
        st.info("👈 Por favor, Selecciona un Estado en el panel lateral para comenzar.")
