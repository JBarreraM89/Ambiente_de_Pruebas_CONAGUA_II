# -*- coding: utf-8 -*-
import streamlit.components.v1 as components
from streamlit_folium import st_folium
from folium import plugins
import streamlit as st
import pandas as pd
import requests
import tempfile
import folium
import time
import io

# --- IMPORTACIONES CORE (ARQUITECTURA ENTERPRISE) ---
from core.data_loader import cargar_datos_maestros, cargar_fraccion, cargar_excel, cargar_csv, cargar_parquet, DIRECTORIO_RAIZ
from core.generador_word import (inyectar_tabla_vertices_en_word, inyectar_tabla_flujo_en_word,
                                inyectar_tabla_almacenamiento_en_word, inyectar_tabla_evapotranspiracion_en_word, 
                                modificar_censo_y_bombeo)
from core.ai_assistant import inicializar_ia, generar_respuesta_stream
from utils.formatters import limpiar_texto, formatear_fecha, procesar_link_drive
from core.estandarizador_acuiferos import ejecutar_estandarizacion_v31

# =======================================================
# 🚀 1. CARGA DE DATOS GLOBAL
# =======================================================
gdf_maestro = cargar_datos_maestros()
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

modelo_ia, ia_activa = inicializar_ia()

# =======================================================
# 🎨 2. ENCABEZADO Y CSS RESTAURADO AL 100%
# =======================================================
css_optimo = """
<style>
    /* Ocultar franja superior de Streamlit y ajustar padding */
    .block-container { padding-top: 1.9rem !important; padding-bottom: 1rem !important; }
    div[data-testid="stHeader"] { display: none !important; }
    
    /* Estilos Originales de Pestañas Institucionales */
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
    
    /* Botones Secundarios convertidos en hipervínculos (Soluciona el error de versiones anteriores) */
    button[kind="secondary"] {
        color: #2980b9 !important; font-weight: 600 !important; padding: 0 !important; 
        background-color: transparent !important; border: none !important; box-shadow: none !important;
    } 
    button[kind="secondary"]:hover {
        color: #9F2241 !important; text-decoration: underline !important; 
        background-color: transparent !important; border: none !important;
    }
</style>

<div style="background-color: #ffffff; padding: 10px 15px; border-bottom: 3px solid #DDC9A3; text-align: center; margin-bottom: 10px;">
    <h2 style="color: #691C32; margin: 0; font-size: 28px; font-weight: bold; font-family: 'Segoe UI', sans-serif;">
        💧 Sistema de Consulta de Información para Documentos de Respaldo
    </h2>
</div>
"""
st.markdown(css_optimo, unsafe_allow_html=True)
st.subheader("🗺️ Resumen Técnico de consulta")
st.caption("Filtra por estado, selecciona el acuífero y enciende las capas espaciales para visualizar recortes exactos.")

# =======================================================
# ⚙️ 3. FUNCIONES AUXILIARES RESTAURADAS
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
# ✨ 4. COMPONENTES EMERGENTES (DIALOGS) RESTAURADOS
# =======================================================
@st.dialog("✨ Asistente de IA de CONAGUA", width="large")
def modal_chat(clave_ac, ctx):
    chat_key = f"chat_history_{clave_ac}"
    if chat_key not in st.session_state: st.session_state[chat_key] = []
    if len(st.session_state[chat_key]) >= 6: 
        st.session_state[chat_key] = []
        st.info("🧹 Historial reiniciado para mantener velocidad óptima.")
        
    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "✨"): 
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("Ej: Haz un resumen de la ficha administrativa del acuífero"):
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"): st.markdown(prompt)
        with st.chat_message("assistant", avatar="✨"):
            if ia_activa:
                try:
                    respuesta = st.write_stream(generar_respuesta_stream(modelo_ia, ctx, prompt))
                    st.session_state[chat_key].append({"role": "assistant", "content": respuesta})
                except Exception as e: st.error(f"Error en IA: {e}")
            else: st.error("IA no disponible. Verifica API Key.")

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
    # --- SIDEBAR (RESTAURADA EXACTA A LA ORIGINAL) ---
    st.sidebar.header("🔍 Panel de Control")
    lista_estados = sorted(gdf_maestro['NOM_EDO'].dropna().astype(str).apply(limpiar_texto).unique())
    estado_seleccionado = st.sidebar.selectbox("1. Estado:", lista_estados, index=None, placeholder="Elige un estado...")
    
    seleccion_final, ver_mapa_geo, file_id_geo = None, False, None
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
                    ver_mapa_geo = st.sidebar.toggle("👁️ Visualizar Mapa Geológico")
            else: st.sidebar.info("📂 Mapa geológico próximamente disponible.")

    # Contador y Aviso Lateral
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"""<div style="text-align: center;"><p style="font-size: 13px; color: #691C32; font-weight: bold; margin-bottom: 5px;">📊 Visitas al Geovisor</p><img src="https://komarev.com/ghpvc/?username=JBarreraM89-Geovisor&label=VISITAS&color=9F2241&style=flat&t={time.time()}" alt="Contador"></div>""", unsafe_allow_html=True)
    st.sidebar.markdown("<br>", unsafe_allow_html=True) 
    st.sidebar.markdown("""<div style="background-color: #fce4e4; padding: 15px; border-radius: 8px; border: 1px solid #f5c6c6; text-align: justify; margin-bottom: 10px; box-shadow: inset 0px 0px 5px rgba(0,0,0,0.05);"><p style="font-size: 11.5px; color: #9F2241; font-weight: 600; margin: 0; line-height: 1.4;">⚠️ <b>AVISO IMPORTANTE:</b><br>Esta plataforma es una herramienta de consulta para uso estrictamente interno de la Gerencia de Aguas Subterráneas. La información y recortes espaciales aquí mostrados no tienen validez legal ni carácter de documento oficial.</p></div>""", unsafe_allow_html=True)

    # --- CONTENIDO PRINCIPAL ---
    if seleccion_final:
        datos_ac = gdf_filtrado_estado[gdf_filtrado_estado['CLV_ACUI'].astype(str).apply(limpiar_texto) == clave_sel].iloc[0]
        nombre_ac = limpiar_texto(datos_ac['NOM_ACUI'])
        
        # ====================================================
        # 🧠 PRE-CÁLCULO DE PÁRRAFOS (BOMBEO Y VOLÚMENES)
        # ====================================================
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

        col1, col2 = st.columns([1.2, 2])
        
        with col1:
            st.header(f"📋 RESUMEN: {clave_sel} - {nombre_ac}")
            st.caption(f"Estado: {estado_seleccionado}")              

            # 🌟 TARJETA DE ESTANDARIZACIÓN DE WORD (CON FRAGMENTO PARA EVITAR RECARGAS)
            @st.fragment
            def modulo_estandarizacion(clave_acuifero):
                with st.container(border=True):
                    col_i, col_a = st.columns([3.8, 1.2], vertical_alignment="center")
                    with col_i:
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
                    with col_a:
                        if df_enlaces_docs is not None:
                            en_row = df_enlaces_docs[df_enlaces_docs['CLAVE_ACUIFERO'] == clave_acuifero]
                            if not en_row.empty:
                                f_id_doc = procesar_link_drive(en_row.iloc[0]['ENLACE_DRIVE'])
                                doc_key = f"doc_{clave_acuifero}"
                                
                                # 1. SI EL DOCUMENTO YA FUE PROCESADO -> MOSTRAR BOTÓN DE DESCARGA
                                if doc_key in st.session_state:
                                    st.download_button(
                                        label="⬇️ Descargar", 
                                        data=st.session_state[doc_key], 
                                        file_name=f"{clave_acuifero}_ESTANDARIZADO_V3.1.docx", 
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                                        type="primary", 
                                        use_container_width=True,
                                        key=f"btn_dl_{clave_acuifero}"  # <--- LLAVE ÚNICA DE DESCARGA
                                    )
                                # 2. SI AÚN NO SE PROCESA -> MOSTRAR BOTÓN DE PROCESAR
                                else:
                                    # <--- LLAVE ÚNICA PARA EVITAR CRUCE DE DATOS ENTRE ACUÍFEROS
                                    if st.button("⚙️ Procesar", type="primary", use_container_width=True, key=f"btn_proc_{clave_acuifero}"):
                                        with st.spinner("⏳ Procesando..."):
                                            try:
                                                res = requests.get(f"https://docs.google.com/document/d/{f_id_doc}/export?format=docx")
                                                if res.status_code == 200:
                                                    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_in, tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_out:
                                                        tmp_in.write(res.content)
                                                        ejecutar_estandarizacion_v31(str(DIRECTORIO_RAIZ/"assets"/"PLANTILLA_V3.1.docx"), tmp_in.name, tmp_out.name)
                                                        
                                                        # 🌟 INYECCIÓN INTELIGENTE DE LAS TABLAS
                                                        msg_verts = inyectar_tabla_vertices_en_word(tmp_out.name, clave_acuifero, df_vertices_global)
                                                        msg_ent = inyectar_tabla_flujo_en_word(tmp_out.name, clave_acuifero, df_flujo_ent_global, ["tabla", "entradas", "flujo"], "Entradas")
                                                        msg_sal = inyectar_tabla_flujo_en_word(tmp_out.name, clave_acuifero, df_flujo_sal_global, ["tabla", "salidas", "flujo"], "Salidas")
                                                        msg_bombeo = modificar_censo_y_bombeo(tmp_out.name, parrafo_aprov_ia, parrafo_vol_ia)
                                                        msg_alm = inyectar_tabla_almacenamiento_en_word(tmp_out.name, clave_acuifero, df_almacenamiento_global)
                                                        msg_etr = inyectar_tabla_evapotranspiracion_en_word(tmp_out.name, clave_acuifero, df_etr_global)
                                                        
                                                        st.toast(msg_verts)
                                                        st.toast(msg_ent)
                                                        st.toast(msg_sal)
                                                        st.toast(msg_alm)
                                                        st.toast(msg_etr)
                                                        st.toast(msg_bombeo)
                                                        
                                                        # Guardar en Session State
                                                        with open(tmp_out.name, "rb") as f: 
                                                            st.session_state[doc_key] = f.read()
                                                    
                                                    # Recargar la app silenciosamente para sustituir el botón Procesar por el Descargar
                                                    st.rerun() 
                                                else: 
                                                    st.error("Error Drive.")
                                            except Exception as e: 
                                                st.error(f"Error: {e}")
                            else: 
                                st.info("Sin registro.")
            
            modulo_estandarizacion(clave_sel)
            # 🌟 PESTAÑAS ORIGINALES RESTAURADAS AL 100% 🌟
            tab_ficha, tab_repda, tab_aprov, tab_dma = st.tabs(["📋 Ficha Administrativa", "📊 Volúmenes", "💧 Aprovechamientos", "⚖️ Balance y Disponibilidad"])
            
            with tab_ficha:
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

                with st.expander("🏛️ División Administrativa", expanded=True):
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
                    st.divider()
                    mostrar_municipios_agrupados_y_condicion(clave_sel, datos_ac.get('municipios_TOTAL'), datos_ac.get('municipios_PARCIAL'))
                    
                with st.expander("🌾 Uso Agrícola", expanded=False):
                    mostrar_pares_en_parrafo("Distritos de Riego", datos_ac.get('distritos_riego_FIRST_NOMB'), datos_ac.get('distritos_riego_DISTID'))
                    mostrar_dato("Unidades de Riego", datos_ac.get('unidades_riego_rha'))

                with st.expander("🌿 Medio Ambiente", expanded=False):
                    mostrar_desde_fraccion_vertical("Áreas Naturales Protegidas Federales", clave_sel, "anp_federal", "NOMBRE", "PRIM_DEC", "DOF: ")
                    mostrar_desde_fraccion_vertical("Áreas Naturales Protegidas Estatales", clave_sel, "anp_estatal", "NOMBRE", "ULT_DEC", "Últ. Dec: ")
                    mostrar_desde_fraccion_vertical("Sitios RAMSAR", clave_sel, "ramsar", "RAMSAR", "FECHA", "Fecha: ")

            with tab_repda:
                st.subheader("Resumen de Bombeo por Aprovechamiento")
                if not df_resumen.empty:
                    st.dataframe(df_resumen.style.format({"Volumen (hm³/año)": "{:.1f}", "Porcentaje (%)": "{:.1f}%"}), use_container_width=True, hide_index=True)
                    st.divider()
                    st.metric("Volumen Total Concesionado (hm³/año)", f"{vol_total:.1f}")
                    st.subheader("📝 Párrafo Redactado para Documento de Respaldo")
                    st.info(parrafo_vol_ia)
                    st.code(parrafo_vol_ia, language="text")
                else: st.warning(f"No se encontró la clave {clave_sel} en el archivo REPDA o no hay volúmenes suficientes.")

            with tab_aprov:
                st.subheader("Conteo de Aprovechamientos por Tipo de Uso")
                if not conteo_usos.empty:
                    st.dataframe(conteo_usos.style.format({"Porcentaje (%)": "{:.1f}%"}), use_container_width=True, hide_index=True)
                    st.divider()
                    st.metric("Total de Aprovechamientos Registrados", f"{total_aprov:,}")
                    st.subheader("📝 Párrafo Redactado para Documento de Respaldo")
                    st.info(parrafo_aprov_ia)
                    st.code(parrafo_aprov_ia, language="text")
                else: st.warning(f"No se encontraron registros de aprovechamientos para la clave {clave_sel}.")

            with tab_dma:
                st.subheader("Balance de Aguas Subterráneas y Cálculo de la DMA")
                st.caption("Valores de flujo y almacenamiento extraídos directamente de los Parquet")
                parrafo_dma_ia = "No hay información de balance disponible."
                
                bal_ent = df_bal_ent_global[df_bal_ent_global['CLV_ACUI'] == clave_sel] if df_bal_ent_global is not None else pd.DataFrame()
                bal_sal = df_bal_sal_global[df_bal_sal_global['CLV_ACUI'] == clave_sel] if df_bal_sal_global is not None else pd.DataFrame()
                bal_alm = df_bal_alm_global[df_bal_alm_global['CLV_ACUI'] == clave_sel] if df_bal_alm_global is not None else pd.DataFrame()

                # Entradas
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

                # Salidas
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

                # Almacenamiento
                st.markdown("#### 🧊 Cambio de almacenamiento ΔV(S)")
                st.dataframe(pd.DataFrame([{"Concepto": "ΔV(S)", "Volumen (hm³)": buscar_valor(bal_alm, "ΔV") or buscar_valor(bal_alm, "V(S)")}]).style.format({"Volumen (hm³)": "{:,.1f}"}), use_container_width=True, hide_index=True)
                if st.button("🔎 Ver tabla de cálculo: Cambio de Almacenamiento ΔV(S)", type="secondary", key="btn_dvs"): modal_tablas_calculo(clave_sel, "ΔV(S)")

                # Cálculo DMA
                v_dnc_total = 0.0
                if not bal_sal.empty and 'DNC_hm3' in bal_sal.columns:
                    match_dnc = bal_sal[bal_sal['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, na=False)]
                    v_dnc_total = float(match_dnc.iloc[-1]['DNC_hm3']) if not match_dnc.empty else pd.to_numeric(bal_sal['DNC_hm3'], errors='coerce').sum()

                v_veas = float(df_veas_global[df_veas_global['CLAVE'] == clave_sel].iloc[0]['VEAS_hm3']) if df_veas_global is not None and not df_veas_global[df_veas_global['CLAVE'] == clave_sel].empty else 0.0
                val_dma = round(v_r_total, 1) - round(v_dnc_total, 1) - v_veas

                st.markdown("#### 🧮 Cálculo de la DMA")
                st.dataframe(pd.DataFrame([
                    {"Concepto": "Recarga total (R)", "Volumen (hm³)": f"{round(v_r_total, 1):,.1f}"},
                    {"Concepto": "Descarga natural comprometida (DNC)", "Volumen (hm³)": f"{round(v_dnc_total, 1):,.1f}"},
                    {"Concepto": "Volumen de extracción (VEAS)", "Volumen (hm³)": f"{v_veas:,.6f}"}
                ]), use_container_width=True, hide_index=True)
                st.divider()
                st.metric(label="Disponibilidad Media Anual (DMA)", value=f"{val_dma:,.6f} hm³")
                parrafo_dma_ia = f"La Disponibilidad Media Anual (DMA) calculada para este acuífero es de {val_dma:,.6f} hm³."

            # =======================================================
            # 🧠 CONTEXTO COMPLETO PARA LA IA Y BOTÓN FLOTANTE
            # =======================================================
            if ia_activa:
                if st.button("✨", help="Abrir Asistente de IA"):
                    ctx_admin = f"Acuífero Clave: {clave_sel}, Nombre: {nombre_ac}, Estado: {estado_seleccionado}. "
                    ctx_admin += f"Región Administrativa: {limpiar_texto(datos_ac.get('REGION_ADM'))}. Dirección Local: {limpiar_texto(datos_ac.get('UNIDAD_ADM'))}. "
                    if pd.notna(datos_ac.get('excel_LIM_NOM')): ctx_admin += f"Acuerdos de Límites: {limpiar_texto(datos_ac.get('excel_LIM_NOM'))}. "
                    if pd.notna(datos_ac.get('vedas_NOM_OFI')): ctx_admin += f"Decretos de Veda: {limpiar_texto(datos_ac.get('vedas_NOM_OFI'))}. "
                    if pd.notna(datos_ac.get('acuerdos_generales_NOM_OFI')): ctx_admin += f"Acuerdos Generales: {limpiar_texto(datos_ac.get('acuerdos_generales_NOM_OFI'))}. "
                    
                    contexto_acuifero_ia = f"""
                    Eres un asistente experto de CONAGUA especializado en aguas subterráneas.
                    Tu tarea es responder basándote ÚNICAMENTE en la siguiente información del Acuífero {clave_sel} - {nombre_ac}. 
                    INFORMACIÓN:
                    {ctx_admin}
                    REPDA: {parrafo_vol_ia}
                    APROVECHAMIENTOS: {parrafo_aprov_ia}
                    BALANCE Y DISPONIBILIDAD: {parrafo_dma_ia}
                    """
                    modal_chat(clave_sel, contexto_acuifero_ia)
                
                components.html(
                    """
                    <script>
                    const doc = window.parent.document;
                    const buttons = doc.querySelectorAll('button');
                    buttons.forEach(b => {
                        if(b.innerText.trim() === '✨') {
                            b.style.position = 'fixed';
                            b.style.top = '145px';
                            b.style.right = '30px';
                            b.style.width = '60px';     
                            b.style.minWidth = '60px';
                            b.style.height = '60px';    
                            b.style.minHeight = '60px';
                            b.style.borderRadius = '50%'; 
                            b.style.zIndex = '999999';  
                            b.style.backgroundColor = '#9F2241';
                            b.style.color = 'white';
                            b.style.padding = '0';
                            b.style.display = 'flex';
                            b.style.alignItems = 'center';
                            b.style.justifyContent = 'center';
                            b.style.boxShadow = '0px 4px 12px rgba(0,0,0,0.4)';
                            b.style.border = 'none';
                            b.style.fontSize = '24px'; 
                            b.style.fontWeight = 'bold';
                            b.style.transition = 'transform 0.3s ease';
                            
                            b.onmouseover = function() { this.style.transform = 'scale(1.1)'; }
                            b.onmouseout = function() { this.style.transform = 'scale(1)'; }
                            
                            if(b.parentElement) {
                                b.parentElement.style.position = 'fixed';
                                b.parentElement.style.top = '145px';
                                b.parentElement.style.right = '30px';
                                b.parentElement.style.width = '60px';
                                b.parentElement.style.height = '60px';
                                b.parentElement.style.zIndex = '999999';
                            }
                        }
                    });
                    </script>
                    """, height=0, width=0)

        # =======================================================
        # 🗺️ COLUMNA DERECHA: VISUALIZADOR ESPACIAL
        # =======================================================
        with col2:
            st.header("🗺️ Visualizador Espacial")
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
            
            for capa_visual in capas_seleccionadas:
                id_archivo, color_hex, campo_nombre = diccionario_capas[capa_visual]
                gdf_frac = cargar_fraccion(id_archivo)
                if gdf_frac is not None:
                    frac_local = gdf_frac[gdf_frac['CLV_ACUI'] == clave_sel]
                    if not frac_local.empty:
                        # 🛡️ Cast de columnas a string para evitar TypeError de Folium
                        frac_segura = frac_local.copy()
                        cols = [c for c in frac_segura.columns if c != 'geometry']
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
            st_folium(m, use_container_width=True, height=650, returned_objects=[])

            if ver_mapa_geo and file_id_geo:
                st.divider()
                st.subheader(f"⛰️ Vista Previa: Mapa Geológico")
                with st.spinner("Cargando imagen interactiva desde Google Drive..."):
                    components.iframe(f"https://drive.google.com/file/d/{file_id_geo}/preview", height=750, scrolling=True)
                    st.caption("🔍 Usa el ratón o los controles del recuadro para hacer zoom a la imagen.")
    else:
        st.info("👈 Selecciona un Acuífero en el panel lateral para ver su información.")
else:
    st.info("👈 Por favor, Selecciona un Estado en el panel lateral para comenzar.")