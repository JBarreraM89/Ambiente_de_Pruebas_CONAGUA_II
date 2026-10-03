# -*- coding: utf-8 -*-
import streamlit.components.v1 as components
from branca.element import MacroElement
from streamlit_folium import st_folium
from difflib import SequenceMatcher
from shapely.geometry import Point, box
from jinja2 import Template
from folium import plugins
import geopandas as gpd
import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import requests
import tempfile
import zipfile
import folium
import time
import io
import re
import math
import os
from pathlib import Path
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- IMPORTACIONES CORE (ARQUITECTURA ENTERPRISE) ---
from core.data_loader import (cargar_datos_maestros, cargar_fraccion, cargar_excel, 
                              cargar_csv, cargar_parquet, DIRECTORIO_RAIZ)
from utils.formatters import limpiar_texto, formatear_fecha, procesar_link_drive
from utils.styles import inyectar_css_oficial, banner_institucional
from xml.sax.saxutils import escape

# =======================================================
# 🚀 1. CARGA DE DATOS MAESTROS Y ACCESO BAJO DEMANDA (LAZY)
# =======================================================
gdf_maestro = cargar_datos_maestros()

@st.cache_data(show_spinner=False)
def get_df_repda(): return cargar_excel("REPDA.xlsx", "Clave de acuífero")
@st.cache_data(show_spinner=False)
def get_df_aprov(): return cargar_excel("Aprovechamientos.xlsx", "Cve_Acuif")
@st.cache_data(show_spinner=False)
def get_df_zonas(): return cargar_excel("ZONAS_DE_DISPONIBILIDAD.xlsx", "CLAVE DEL ACUÍFERO")
@st.cache_data(show_spinner=False)
def get_df_vertices(): return cargar_excel("Vertices.xlsx", "ID_ACUIFERO")
@st.cache_data(show_spinner=False)
def get_df_enlaces(): return cargar_csv("Reporte de Enlaces Acuíferos - 5_8_2026 - Hoja 1.csv", "CLAVE_ACUIFERO")
@st.cache_data(show_spinner=False)
def get_df_links(): return cargar_csv("Links.csv", "clave")
@st.cache_data(show_spinner=False)
def get_df_flujo_ent(): return cargar_parquet("Flujo_Horizontal_Entradas.parquet")
@st.cache_data(show_spinner=False)
def get_df_flujo_sal(): return cargar_parquet("Flujo_Horizontal_Salidas.parquet")
@st.cache_data(show_spinner=False)
def get_df_almacenamiento(): return cargar_parquet("Cambio_Almacenamiento.parquet")
@st.cache_data(show_spinner=False)
def get_df_etr(): return cargar_parquet("Evapotranspiracion.parquet")
@st.cache_data(show_spinner=False)
def get_df_bal_ent(): return cargar_parquet("Balance_Hidro_Entradas.parquet")
@st.cache_data(show_spinner=False)
def get_df_bal_sal(): return cargar_parquet("Balance_Hidro_Salidas.parquet")
@st.cache_data(show_spinner=False)
def get_df_bal_alm(): return cargar_parquet("Balance_Hidro_Almacenamiento.parquet")
@st.cache_data(show_spinner=False)
def get_df_veas(): return cargar_parquet("VEAS_Administrativo.parquet")

# =======================================================
# 🎨 2. ENCABEZADO NATIVO E INSTITUCIONAL
# =======================================================
inyectar_css_oficial()
banner_institucional()

# =======================================================
# ⚙️ 3. FUNCIONES AUXILIARES Y CACHÉ ESPACIAL OPTIMIZADO
# =======================================================
@st.cache_data(show_spinner=False)
def cargar_localidades_parquet():
    from pathlib import Path
    rutas = [
        DIRECTORIO_RAIZ / "localidades_2025.parquet",
        DIRECTORIO_RAIZ / "data" / "localidades_2025.parquet",
        Path("localidades_2025.parquet")
    ]
    for r in rutas:
        p = Path(r)
        if p.exists():
            try: return gpd.read_parquet(p)
            except Exception as e:
                st.error(f"Error al leer localidades_2025.parquet: {e}")
                return None
    return None

@st.cache_data(show_spinner=False)
def obtener_capa_exacta_cache(id_archivo, clave_ac):
    cve_norm = str(clave_ac).strip().zfill(4)
    
    if id_archivo == "localidades":
        # Las localidades a veces no tienen clave, aquí sí usamos el cruce espacial
        gdf_frac = cargar_localidades_parquet()
        if gdf_frac is None or gdf_frac.empty: return None
        if 'CLV_ACUI' in gdf_frac.columns:
            return gdf_frac[gdf_frac['CLV_ACUI'].astype(str).str.zfill(4) == cve_norm].copy()
            
        # Intersección espacial SOLO para localidades sin clave
        gdf_m = cargar_datos_maestros()
        geom_acuifero = gdf_m[gdf_m['CLV_ACUI'].astype(str).str.zfill(4) == cve_norm].iloc[0].geometry
        minx, miny, maxx, maxy = geom_acuifero.bounds
        candidatos = gdf_frac.cx[minx:maxx, miny:maxy]
        if candidatos.empty: return None
        posibles_idx = list(candidatos.sindex.intersection(geom_acuifero.bounds))
        posibles = candidatos.iloc[posibles_idx]
        res = posibles[posibles.geometry.intersects(geom_acuifero)].copy()
        return res if not res.empty else None
        
    else:
        # ⚡ MODO ESTRICTO PARA EL RESTO DE CAPAS (COTAS, VEDAS, ETC.)
        # Solo extrae lo que coincida exactamente con la clave en el disco duro.
        # Si la clave no existe, devuelve vacío y NO dibuja nada.
        gdf_frac = cargar_fraccion(id_archivo, cve_norm)
        
        if gdf_frac is not None and not gdf_frac.empty:
            return gdf_frac
        
        # Si no encontró la clave, retorna None (No activa ningún paracaídas espacial)
        return None

def exportar_acuifero_a_kmz(clave_ac, nom_ac, datos_ac, capas_seleccionadas, diccionario_capas, marcadores):
    def reparar_mojibake(texto):
        if texto is None: return ""
        s = str(texto).strip()
        try: s = s.encode('latin1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError): pass
        return escape(s)

    def hex_a_kml_color(hex_str, opacidad_hex="ff"):
        hex_clean = hex_str.lstrip('#')
        if len(hex_clean) == 6:
            r = hex_clean[0:2]; g = hex_clean[2:4]; b = hex_clean[4:6]
            return f"{opacidad_hex}{b}{g}{r}".lower()
        return f"{opacidad_hex}ffffff"

    def generar_html_atributos(row, cols_ignorar=None):
        if cols_ignorar is None: cols_ignorar = {'geometry', 'CLV_TEMP', 'CLV_ACUI'}
        filas = []
        for col in row.index:
            if col in cols_ignorar: continue
            val = row[col]
            if pd.isna(val) or str(val).strip() in ['', 'None', 'nan', 'NaT', '-']: continue
            nom_col = str(col).replace('_', ' ').strip().title()
            val_limpio = reparar_mojibake(val)
            filas.append(f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="font-weight: 600; color: #4a5568; padding: 4px 8px; background-color: #f7fafc; width: 40%;">{nom_col}</td>
                <td style="color: #1a202c; padding: 4px 8px;">{val_limpio}</td>
            </tr>
            """)
        if not filas: return ""
        return f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; font-size: 11px; max-width: 380px;">
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #cbd5e0; margin-top: 4px;">
                {"".join(filas)}
            </table>
        </div>
        """

    def coords_a_kml(geom):
        if geom is None or geom.is_empty: return ""
        gt = geom.geom_type
        if gt == 'Point': return f"<Point><coordinates>{geom.x},{geom.y},0</coordinates></Point>"
        elif gt == 'Polygon':
            ext = " ".join([f"{x},{y},0" for x, y in geom.exterior.coords])
            res = [f"<Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{ext}</coordinates></LinearRing></outerBoundaryIs>"]
            for interior in geom.interiors:
                inte = " ".join([f"{x},{y},0" for x, y in interior.coords])
                res.append(f"<innerBoundaryIs><LinearRing><coordinates>{inte}</coordinates></LinearRing></innerBoundaryIs>")
            res.append("</Polygon>")
            return "".join(res)
        elif gt == 'MultiPolygon':
            res = ["<MultiGeometry>"]
            for poly in geom.geoms: res.append(coords_a_kml(poly))
            res.append("</MultiGeometry>")
            return "".join(res)
        elif gt in ['LineString', 'LinearRing']:
            pts = " ".join([f"{x},{y},0" for x, y in geom.coords])
            return f"<LineString><tessellate>1</tessellate><coordinates>{pts}</coordinates></LineString>"
        elif gt == 'MultiLineString':
            res = ["<MultiGeometry>"]
            for ls in geom.geoms: res.append(coords_a_kml(ls))
            res.append("</MultiGeometry>")
            return "".join(res)
        return ""

    cve_limpia = reparar_mojibake(clave_ac)
    nom_limpio = reparar_mojibake(nom_ac)

    kml = ['<?xml version="1.0" encoding="UTF-8"?>']
    kml.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    kml.append('<Document>')
    kml.append(f'<name>{cve_limpia} - {nom_limpio}</name>')

    kml.append("""
    <Style id="estilo_acuifero">
        <LineStyle><color>ff76521a</color><width>3.5</width></LineStyle>
        <PolyStyle><color>22cc8631</color></PolyStyle>
    </Style>
    <Style id="pto_existente">
        <IconStyle><color>ff3b8a00</color><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle>
        <LabelStyle><scale>0.85</scale></LabelStyle>
    </Style>
    <Style id="pto_requerido">
        <IconStyle><color>ff41229f</color><scale>1.1</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle>
        <LabelStyle><scale>0.85</scale></LabelStyle>
    </Style>
    <Style id="estilo_localidades">
        <LineStyle><color>ff321c69</color><width>1.2</width></LineStyle>
        <PolyStyle><color>665c95bc</color></PolyStyle>
    </Style>
    """)

    for nombre_capa in capas_seleccionadas:
        id_arc, col_hex, _ = diccionario_capas[nombre_capa]
        if id_arc != "localidades":
            line_kml = hex_a_kml_color(col_hex, opacidad_hex="ff")
            poly_kml = hex_a_kml_color(col_hex, opacidad_hex="4d")
            kml.append(f"""
            <Style id="estilo_{id_arc}">
                <LineStyle><color>{line_kml}</color><width>2</width></LineStyle>
                <PolyStyle><color>{poly_kml}</color></PolyStyle>
            </Style>
            """)

    kml.append('<Folder><name>Límite Oficial</name>')
    tabla_acuifero = generar_html_atributos(datos_ac, cols_ignorar={'geometry', 'label_busqueda'})
    kml.append(f"""
    <Placemark>
        <name>{cve_limpia} - {nom_limpio}</name>
        <styleUrl>#estilo_acuifero</styleUrl>
        <description><![CDATA[
            <h4 style="margin: 0 0 6px 0; color: #691C32;">Polígono Oficial del Acuífero</h4>
            {tabla_acuifero}
        ]]></description>
        {coords_a_kml(datos_ac.geometry)}
    </Placemark>
    """)
    kml.append('</Folder>')

    if marcadores:
        kml.append('<Folder><name>Puntos de Referencia y Pozos</name>')
        for pt in marcadores:
            n_pt = reparar_mojibake(str(pt.get("nombre", "Punto")))
            t_pt = str(pt.get("tipo", "Pozo existente"))
            es_req = any(k in t_pt.lower() for k in ["requerid", "nuevo", "propuest"])
            style_id = "#pto_requerido" if es_req else "#pto_existente"
            lat, lon = pt.get("lat"), pt.get("lon")
            kml.append(f"""
            <Placemark>
                <name>{n_pt}</name>
                <styleUrl>{style_id}</styleUrl>
                <description><![CDATA[
                    <h4 style="margin: 0 0 6px 0; color: #691C32;">{n_pt}</h4>
                    <table style="width: 100%; border-collapse: collapse; font-family: 'Segoe UI', sans-serif; font-size: 11px;">
                        <tr style="border-bottom: 1px solid #e2e8f0;"><td style="font-weight: bold; padding: 3px;">Tipo:</td><td>{reparar_mojibake(t_pt)}</td></tr>
                        <tr style="border-bottom: 1px solid #e2e8f0;"><td style="font-weight: bold; padding: 3px;">Latitud:</td><td>{lat:.5f}</td></tr>
                        <tr><td style="font-weight: bold; padding: 3px;">Longitud:</td><td>{lon:.5f}</td></tr>
                    </table>
                ]]></description>
                <Point><coordinates>{lon},{lat},0</coordinates></Point>
            </Placemark>
            """)
        kml.append('</Folder>')

    for nombre_capa in capas_seleccionadas:
        id_archivo, color_hex, campo_nombre = diccionario_capas[nombre_capa]
        frac_local = obtener_capa_exacta_cache(id_archivo, clave_ac)

        if frac_local is not None and not frac_local.empty:
            nombre_carpeta = reparar_mojibake(nombre_capa)
            kml.append(f'<Folder><name>{nombre_carpeta}</name>')
            
            col_nombre = campo_nombre if campo_nombre in frac_local.columns else frac_local.columns[0]
            estilo_url = "#estilo_localidades" if id_archivo == "localidades" else f"#estilo_{id_archivo}"

            for _, row in frac_local.iterrows():
                nom_elem = reparar_mojibake(row.get(col_nombre, nombre_capa))
                geom_kml = coords_a_kml(row.geometry)
                tabla_html = generar_html_atributos(row)
                if geom_kml:
                    kml.append(f"""
                    <Placemark>
                        <name>{nom_elem}</name>
                        <styleUrl>{estilo_url}</styleUrl>
                        <description><![CDATA[
                            <h4 style="margin: 0 0 6px 0; color: #691C32;">{nom_elem}</h4>
                            <span style="font-size: 10px; color: #718096; font-style: italic;">Capa: {nombre_carpeta}</span>
                            {tabla_html}
                        ]]></description>
                        {geom_kml}
                    </Placemark>
                    """)
            kml.append('</Folder>')

    kml.append('</Document></kml>')
    kmz_buffer = io.BytesIO()
    with zipfile.ZipFile(kmz_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr("doc.kml", "\n".join(kml).encode('utf-8'))
    return kmz_buffer.getvalue()

@st.cache_data(show_spinner="Empaquetando KMZ con geometrías exactas...")
def obtener_kmz_cacheado(clave_ac, nom_ac, _datos_ac, capas_seleccionadas_tuple, marcadores_str, _diccionario_capas):
    marcadores_lista = eval(marcadores_str) if marcadores_str else []
    return exportar_acuifero_a_kmz(clave_ac, nom_ac, _datos_ac, list(capas_seleccionadas_tuple), _diccionario_capas, marcadores_lista)

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
    fraccion = cargar_fraccion(id_capa, clave_ac) # ⚡ Carga filtrada
    if fraccion is not None and not fraccion.empty:
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
    fraccion = cargar_fraccion(id_capa, clave_ac) # ⚡ Carga filtrada
    if fraccion is not None and not fraccion.empty:
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
    from core.config import DICCIONARIO_ESTADOS
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

    fraccion = cargar_fraccion("municipios", clave_ac) # ⚡ Carga filtrada
    if fraccion is not None and not fraccion.empty and 'CVE_ENT' in fraccion.columns and 'NOMGEO' in fraccion.columns:
        lista_totales = normalizar_lista(str_total)
        lista_parciales = normalizar_lista(str_parcial)
        st.write("**Municipios del Acuífero:**")
        agrupados = fraccion.groupby('CVE_ENT')
        
        for cve_ent, group in agrupados:
            try: cve_str = str(int(float(cve_ent))).zfill(2)
            except: cve_str = str(cve_ent).zfill(2)
            nombre_estado = DICCIONARIO_ESTADOS.get(cve_str, f"Estado Desconocido ({cve_str})")
            totales, parciales = [], []
            
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
        match = df[df['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, regex=False, na=False)]
        if not match.empty:
            try: return float(match.iloc[-1][columna])
            except: return 0.0
    palabra_escapada = re.escape(palabra_clave)
    match = df[df['CONCEPTO'].astype(str).str.contains(rf'\b{palabra_escapada}\b', case=True, regex=True, na=False)]   
    if match.empty:
        match = df[df['CONCEPTO'].astype(str).str.contains(palabra_clave, case=False, regex=False, na=False)]        
    if not match.empty:
        match = match[~match['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, regex=False, na=False)]
        if not match.empty:
            try: return float(match.iloc[-1][columna])
            except: return 0.0            
    return 0.0

# =======================================================
# 🧠 ASISTENTE TÉCNICO CONAGUA (GROQ LLAMA-3.1 ULTRA-LIGERO)
# =======================================================
def consultar_asistente_conagua(prompt, clave_ac, nombre_ac, contexto_str, historial):
    api_key = st.secrets.get("GROQ_API_KEY", None)
    
    if not api_key:
        return "⚠️ No se encontró la clave GROQ_API_KEY en los secretos de Streamlit Cloud. Por favor agrégala en Settings ➔ Secrets."

    try:
        from openai import OpenAI
        cliente = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        
        prompt_sistema = f"""
        Eres el Asistente Técnico y Geohidrólogo Senior de la Gerencia de Aguas Subterráneas de CONAGUA.
        Tu misión es responder preguntas técnicas sobre el acuífero: {clave_ac} - {nombre_ac}.
        
        DEBES responder con máxima precisión institucional basándote ESTRICTAMENTE en la siguiente información oficial:
        =====================================================
        {contexto_str}
        =====================================================
        
        REGLAS DE RESPUESTA:
        1. Responde de forma concisa, analítica y profesional en español.
        2. Siempre que menciones volúmenes incluye sus unidades oficiales (hm³/año, l/s, msnm, m).
        3. Cita fechas publicadas en el DOF cuando hables de Límites, Decretos o Acuerdos.
        4. Si te preguntan algo que NO está en el texto oficial, di con cortesía que esa variable no se encuentra registrada en el expediente oficial.
        5. Usa viñetas o negritas para estructurar tu respuesta.
        """

        mensajes = [{"role": "system", "content": prompt_sistema}]
        
        for msg in historial[-4:]:
            if "content" in msg and msg["content"]:
                mensajes.append({"role": msg["role"], "content": msg["content"]})
                
        mensajes.append({"role": "user", "content": prompt})

        stream = cliente.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=mensajes,
            temperature=0.1,
            stream=True
        )
        return stream

    except Exception as e:
        return f"⚠️ Error de conexión con la IA: {str(e)}"

# =======================================================
# 💬 MODAL DE CHAT INTERACTIVO (STREAMING)
# =======================================================
@st.dialog("💧 Asistente Técnico CONAGUA (Inteligencia Hídrica)", width="large")
def modal_chat_local(clave_ac, nombre_ac, contexto_global_str):
    st.caption(f"Expediente oficial: **{clave_ac} - {nombre_ac}** | Motor: `Llama-3.1 (Groq Cloud)`")
    chat_key = f"chat_history_{clave_ac}"
    
    if chat_key not in st.session_state:
        st.session_state[chat_key] = [{
            "role": "assistant", 
            "content": f"¡Hola! Soy tu Asistente Técnico para el acuífero **{clave_ac} - {nombre_ac}**. He cargado toda la información oficial: Límites DOF, Decretos de Veda, Balance de Aguas (DMA), Aprovechamientos REPDA y Vértices. ¿Qué deseas consultar?"
        }]
        
    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "💧"): 
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("Ej: ¿Cuáles son las extracciones del REPDA y qué decretos de veda aplican?"):
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="👤"): 
            st.markdown(prompt)
            
        with st.chat_message("assistant", avatar="💧"):
            resultado = consultar_asistente_conagua(
                prompt, clave_ac, nombre_ac, contexto_global_str, st.session_state[chat_key]
            )
            
            if isinstance(resultado, str):
                st.markdown(resultado)
                st.session_state[chat_key].append({"role": "assistant", "content": resultado})
            else:
                def generador_palabras():
                    for chunk in resultado:
                        texto = chunk.choices[0].delta.content
                        if texto:
                            yield texto
                            
                respuesta_completa = st.write_stream(generador_palabras())
                st.session_state[chat_key].append({"role": "assistant", "content": respuesta_completa})

# =======================================================
# 🧠 CONSTRUCTOR DE CONTEXTO GLOBAL HÍDRICO (RAG ENTERPRISE)
# =======================================================
def obtener_resumen_fraccion(id_capa, clave_ac, campo_nombre, campo_fecha=None, prefijo_fecha="DOF: "):
    fraccion = cargar_fraccion(id_capa, clave_ac) # ⚡ Carga filtrada
    if fraccion is None or fraccion.empty: return "Sin registros aplicables."
        
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
    from core.config import DICCIONARIO_ESTADOS
    fraccion = cargar_fraccion("municipios", clave_ac) # ⚡ Carga filtrada
    if fraccion is None or fraccion.empty or 'CVE_ENT' not in fraccion.columns or 'NOMGEO' not in fraccion.columns:
        return "Sin municipios registrados."
    
    resumen_mun = []
    agrupados = fraccion.groupby('CVE_ENT')
    for cve_ent, group in agrupados:
        try: cve_str = str(int(float(cve_ent))).zfill(2)
        except: cve_str = str(cve_ent).zfill(2)
        edo = DICCIONARIO_ESTADOS.get(cve_str, f"Estado {cve_str}")
        muns = sorted(group['NOMGEO'].dropna().astype(str).unique().tolist())
        if muns: resumen_mun.append(f"  * {edo}: {', '.join([m.title() for m in muns])}")
            
    return "\n".join(resumen_mun) if resumen_mun else "Sin información detallada."

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
    for p in prompt_norm.split():
        if len(p) >= 4 and len(palabra_norm) >= 4:
            if SequenceMatcher(None, palabra_norm, p).ratio() >= umbral: return True
    return False

def construir_contexto_completo(clave_ac, nombre_ac, estado, datos_ac, 
                                 parrafo_vol, parrafo_aprov, parrafo_dma,
                                 df_resumen, conteo_usos, 
                                 df_bal_ent, df_bal_sal, df_bal_alm,
                                 df_verts, df_flujo_ent, df_flujo_sal, df_etr, df_alm, dato_zona_disp):
    ctx = []
    ctx.append(f"Acuífero Oficial: {clave_ac} - {nombre_ac} | Estado Principal: {estado}")
    org_cuenca = limpiar_texto(datos_ac.get('REGION_ADM'))
    ctx.append(f"Región Administrativa y Organismo de Cuenca del acuífero {clave_ac}:\n- {org_cuenca if org_cuenca else 'Sin información.'}")
    dir_local = limpiar_texto(datos_ac.get('UNIDAD_ADM'))
    ctx.append(f"Dirección Local y Unidad Administrativa del acuífero {clave_ac}:\n- {dir_local if dir_local else 'Sin información.'}")
    if dato_zona_disp and str(dato_zona_disp).lower() != 'nan': ctx.append(f"Zona de Disponibilidad Oficial: Zona {dato_zona_disp}")

    lim_nom, lim_fec = limpiar_texto(datos_ac.get('excel_LIM_NOM')), limpiar_texto(datos_ac.get('excel_LIM_FECHA'))
    if lim_nom:
        fec_str = f" (Publicado en DOF: {formatear_fecha(lim_fec)})" if lim_fec else ""
        ctx.append(f"Acuerdo de Límites Oficiales:\n- {lim_nom}{fec_str}")

    vedas_nom, vedas_fec = limpiar_texto(datos_ac.get('vedas_NOM_OFI')), limpiar_texto(datos_ac.get('vedas_FECHA_DOF'))
    if vedas_nom and str(vedas_nom).lower() != 'nan':
        fec_str = f" (DOF: {formatear_fecha(vedas_fec)})" if vedas_fec else ""
        ctx.append(f"Decretos de Veda Aplicables:\n- {vedas_nom}{fec_str}")

    acuerdos_nom, acuerdos_fec = limpiar_texto(datos_ac.get('acuerdos_generales_NOM_OFI')), limpiar_texto(datos_ac.get('acuerdos_generales_FECHA_DOF'))
    if acuerdos_nom and str(acuerdos_nom).lower() != 'nan':
        fec_str = f" (DOF: {formatear_fecha(acuerdos_fec)})" if acuerdos_fec else ""
        ctx.append(f"Acuerdos Generales:\n- {acuerdos_nom}{fec_str}")

    cotas_nom = limpiar_texto(datos_ac.get('cotas_nom_cotas'))
    if cotas_nom and str(cotas_nom).lower() != 'nan': ctx.append(f"COTAS: {cotas_nom}")

    ctx.append(f"Municipios Ubicados Dentro:\n{obtener_texto_municipios_ia(clave_ac)}")
    ctx.append(f"Consejo de Cuenca: {obtener_resumen_fraccion('consejos_cuenca', clave_ac, 'NOMCONSEJC', 'FECHA_INST', 'Instalado: ')}")
    ctx.append(f"ANP Federales: {obtener_resumen_fraccion('anp_federal', clave_ac, 'NOMBRE', 'PRIM_DEC', 'DOF: ')}")
    ctx.append(f"ANP Estatales: {obtener_resumen_fraccion('anp_estatal', clave_ac, 'NOMBRE', 'ULT_DEC', 'Últ. Dec: ')}")
    ctx.append(f"Sitios RAMSAR: {obtener_resumen_fraccion('ramsar', clave_ac, 'RAMSAR', 'FECHA', 'Fecha: ')}")

    if parrafo_vol and "No hay información" not in parrafo_vol: ctx.append(f"Volúmenes de Extracción (REPDA):\n{parrafo_vol}")
    if not df_resumen.empty: ctx.append("Tabla de Usos REPDA:\n\n" + df_resumen.to_markdown(index=False))
    if parrafo_aprov and "No hay información" not in parrafo_aprov: ctx.append(f"Censo de Aprovechamientos:\n{parrafo_aprov}")
    if not conteo_usos.empty: ctx.append("Conteo de Aprovechamientos:\n\n" + conteo_usos.to_markdown(index=False))
    if parrafo_dma: ctx.append(f"Disponibilidad Media Anual (DMA):\n{parrafo_dma}")

    if df_bal_ent is not None and not df_bal_ent[df_bal_ent['CLV_ACUI'] == clave_ac].empty:
        ctx.append("Tabla Entradas Balance (hm³/año):\n\n" + df_bal_ent[df_bal_ent['CLV_ACUI'] == clave_ac][['CONCEPTO', 'VOLUMEN_hm3']].to_markdown(index=False))
    if df_bal_sal is not None and not df_bal_sal[df_bal_sal['CLV_ACUI'] == clave_ac].empty:
        cols_sal = [c for c in ['CONCEPTO', 'VOLUMEN_hm3', 'DNC_hm3'] if c in df_bal_sal.columns]
        ctx.append("Tabla Salidas Balance (hm³/año):\n\n" + df_bal_sal[df_bal_sal['CLV_ACUI'] == clave_ac][cols_sal].to_markdown(index=False))
    if df_bal_alm is not None and not df_bal_alm[df_bal_alm['CLV_ACUI'] == clave_ac].empty:
        ctx.append("Tabla ΔV(S) (hm³/año):\n\n" + df_bal_alm[df_bal_alm['CLV_ACUI'] == clave_ac][['CONCEPTO', 'VOLUMEN_hm3']].to_markdown(index=False))
    if df_flujo_ent is not None and not df_flujo_ent[df_flujo_ent['CLV_ACUI'] == clave_ac].empty:
        ctx.append("Memoria Eh:\n\n" + df_flujo_ent[df_flujo_ent['CLV_ACUI'] == clave_ac].drop(columns=['CLV_ACUI'], errors='ignore').to_markdown(index=False))
    if df_flujo_sal is not None and not df_flujo_sal[df_flujo_sal['CLV_ACUI'] == clave_ac].empty:
        ctx.append("Memoria Sh:\n\n" + df_flujo_sal[df_flujo_sal['CLV_ACUI'] == clave_ac].drop(columns=['CLV_ACUI'], errors='ignore').to_markdown(index=False))
    if df_etr is not None and not df_etr[df_etr['CLV_ACUI'] == clave_ac].empty:
        ctx.append("Memoria ETR:\n\n" + df_etr[df_etr['CLV_ACUI'] == clave_ac].drop(columns=['CLV_ACUI'], errors='ignore').to_markdown(index=False))
    if df_alm is not None and not df_alm[df_alm['CLV_ACUI'] == clave_ac].empty:
        ctx.append("Memoria ΔV(S):\n\n" + df_alm[df_alm['CLV_ACUI'] == clave_ac].drop(columns=['CLV_ACUI'], errors='ignore').to_markdown(index=False))
    if df_verts is not None and not df_verts[df_verts['ID_ACUIFERO'] == clave_ac].empty:
        ctx.append(f"Catálogo Vértices ({len(df_verts[df_verts['ID_ACUIFERO'] == clave_ac])} totales):\n\n" + df_verts[df_verts['ID_ACUIFERO'] == clave_ac].head(6)[['VERTICE', 'LONG_G', 'LONG_M', 'LONG_S', 'LAT_G', 'LAT_M', 'LAT_S']].to_markdown(index=False))

    return "\n\n".join(ctx)

@st.dialog("📐 Catálogo de Vértices (Poligonal Oficial)", width="large")
def modal_vertices(clave_ac):
    df_vertices_global = get_df_vertices()
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
            "archivo": "Flujo_Horizontal_Entradas.parquet", 
            "titulo": "Entrada horizontal subterránea (Eh)",
            "cols": {"LONG_B_m": "LONGITUD B (m)", "ANCHO_a_m": "ANCHO a (m)", 
                     "h2_h1_m": "h₂-h₁ (m)", "GRADIENTE_i": "GRADIENTE i", "T_m2_s": "T (m²/s)", 
                     "CAUDAL_Q_m3_s": "CAUDAL Q (m³/s)", "VOLUMEN_hm3": "VOLUMEN (hm³/año)"}
        },
        "Sh": {
            "archivo": "Flujo_Horizontal_Salidas.parquet", 
            "titulo": "Salida horizontal subterránea (Sh)",
            "cols": {"LONG_B_m": "LONGITUD B (m)", "ANCHO_a_m": "ANCHO a (m)", 
                     "h2_h1_m": "h₂-h₁ (m)", "GRADIENTE_i": "GRADIENTE i", "T_m2_s": "T (m²/s)", 
                     "CAUDAL_Q_m3_s": "CAUDAL Q (m³/s)", "VOLUMEN_hm3": "VOLUMEN (hm³/año)"}
        },
        "ETR": {
            "archivo": "Evapotranspiracion.parquet", 
            "titulo": "Evapotranspiración Real (ETR)",
            "cols": {"RANGOS_DE_PROFUNDIDAD_m": "RANGOS DE PROFUNDIDAD (m)", "PROFUNDIDAD_MEDIA_m": "PROFUNDIDAD MEDIA (m)", "AREA_km2": "ÁREA (km²)", 
                     "LAMINA_ETR_m": "LÁMINA ETR (m)", "PROF_MAX_EXTINCION_ETR": "PROFUNDIDAD MÁXIMA DE EXTINCIÓN DE LA ETR",
                     "PORCENTAJE_ETR": "% ETR", "VOLUMEN_ETR_hm3_ano": "VOLUMEN ETR (hm³/año)"}
        },
        "ΔV(S)": {
            "archivo": "Cambio_Almacenamiento.parquet", 
            "titulo": "Cambio de Almacenamiento ΔV(S)",
            "cols": {"EVOLUCION_m": "EVOLUCIÓN (m)", "EVOLUCION_MEDIA_m": "EVOLUCIÓN MEDIA (m)",
                     "AREA_km2": "ÁREA (km²)", "Sy": "Sy", "VOLUMEN_hm3": "ΔV(S) (hm³/año)"}
        }
    }
    
    config = mapeo_config.get(tabla_tipo)
    if config:
        df_fuente = cargar_parquet(config["archivo"])
        if df_fuente is not None:
            df_base = df_fuente[df_fuente['CLV_ACUI'] == clave_ac].copy()
            
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
    else:
        st.error("Configuración de tabla no válida.")

# =======================================================
# 🎛️ 4. INTERFAZ PRINCIPAL
# =======================================================
if "filtro_estado_sel" not in st.session_state:
    st.session_state["filtro_estado_sel"] = None
if "filtro_acuifero_sel" not in st.session_state:
    st.session_state["filtro_acuifero_sel"] = None

st.sidebar.header("🔍 Panel de Control")
lista_estados = sorted(gdf_maestro['NOM_EDO'].dropna().astype(str).apply(limpiar_texto).unique())

idx_edo = None
if st.session_state.get("filtro_estado_sel") in lista_estados:
    idx_edo = lista_estados.index(st.session_state["filtro_estado_sel"])

estado_seleccionado = st.sidebar.selectbox(
    "1. Estado:", 
    lista_estados, 
    index=idx_edo,
    key="sb_estado",
    placeholder="Elige un estado..."
)
st.session_state["filtro_estado_sel"] = estado_seleccionado

seleccion_final, file_id_geo = None, None
if estado_seleccionado:
    gdf_filtrado_estado = gdf_maestro[gdf_maestro['NOM_EDO'].astype(str).apply(limpiar_texto) == estado_seleccionado].copy()
    gdf_filtrado_estado['label_busqueda'] = (
        gdf_filtrado_estado['CLV_ACUI'].astype(str).apply(limpiar_texto) + " - " + 
        gdf_filtrado_estado['NOM_ACUI'].astype(str).apply(limpiar_texto)
    )
    opciones_acuiferos = sorted(gdf_filtrado_estado['label_busqueda'].unique())
    
    idx_ac = None
    if st.session_state.get("filtro_acuifero_sel") in opciones_acuiferos:
        idx_ac = opciones_acuiferos.index(st.session_state["filtro_acuifero_sel"])
        
    seleccion_final = st.sidebar.selectbox(
        "2. Clave o Nombre del Acuífero:", 
        opciones_acuiferos, 
        index=idx_ac,
        key="sb_acuifero",
        placeholder="Teclea la clave o nombre..."
    )
    st.session_state["filtro_acuifero_sel"] = seleccion_final
    if seleccion_final:
        clave_actual = seleccion_final.split(" - ")[0]
        if st.session_state.get("acuifero_en_pantalla_sig") != clave_actual:
            if not st.session_state.get("puntos_recien_cargados", False):
                st.session_state["lista_marcadores"] = []
            st.session_state["puntos_recien_cargados"] = False
            st.session_state["selector_capas_visuales"] = []
            st.session_state["acuifero_en_pantalla_sig"] = clave_actual
    
    datos_ac, clave_sel, nombre_ac = None, None, None
    if seleccion_final:
        clave_sel = seleccion_final.split(" - ")[0]
        datos_ac = gdf_filtrado_estado[gdf_filtrado_estado['CLV_ACUI'].astype(str).apply(limpiar_texto) == clave_sel].iloc[0]
        nombre_ac = limpiar_texto(datos_ac['NOM_ACUI'])

    # =======================================================
    # 🗺️ CAPAS VISUALES Y COORDENADAS (NIVEL RAÍZ)
    # =======================================================
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
        "Localidades": ("localidades", "#d35400", "NOMGEO"),
        "Municipios": ("municipios", "#95a5a6", "NOMGEO"),
        "Organismos de Cuenca": ("organismos_cuenca", "#3498db", "NOMBRE"),
        "Reglamentos": ("reglamentos", "#c0392b", "NOM_OFI"),
        "Sitios RAMSAR": ("ramsar", "#00bcd4", "RAMSAR"),
        "Unidades de Riego": ("unidades_riego", "#f1c40f", "rha"),
        "Vedas": ("vedas", "#8e44ad", "NOM_OFI"),
        "Zonas de Reserva": ("zonas_reserva", "#e74c3c", "NOM_OFI"),
        "Zonas Reglamentadas": ("zonas_reglamentadas", "#9b59b6", "NOM_OFI")
    }
    capas_seleccionadas = st.sidebar.multiselect(
        "Selecciona qué fracciones ver en el mapa:", 
        list(diccionario_capas.keys()),
        key="selector_capas_visuales",
        placeholder="Elige una o más capas..."
    )

if "lista_marcadores" not in st.session_state:
    st.session_state["lista_marcadores"] = []
if "selector_capas_visuales" not in st.session_state:
    st.session_state["selector_capas_visuales"] = []
if "csv_uploader_key" not in st.session_state:
    st.session_state["csv_uploader_key"] = 0

st.sidebar.markdown("---")
st.sidebar.subheader("📍 Puntos de Referencia / Pozos")
st.sidebar.markdown("""
    <div style="font-size: 11px; color: #666; margin-top: -14px; margin-bottom: 8px;">
        Ingresa coordenadas manuales o carga masiva vía CSV
    </div>
""", unsafe_allow_html=True)
st.sidebar.markdown("""
    <style>
        section[data-testid="stSidebar"] button[kind="secondary"],
        section[data-testid="stSidebar"] button[data-baseweb="button"]:not([kind="primary"]),
        section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button,
        section[data-testid="stSidebar"] div[data-testid="stLinkButton"] a {
            background-color: #e9ecef !important;
            border: 1px solid #ced4da !important;
            border-radius: 6px !important;
            color: #333333 !important;
            font-weight: 600 !important;
            width: 100% !important;
            min-height: 38px !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-decoration: none !important;
            transition: all 0.2s ease !important;
            margin-top: 4px !important;
        }

        section[data-testid="stSidebar"] button[kind="secondary"]:hover,
        section[data-testid="stSidebar"] button[data-baseweb="button"]:not([kind="primary"]):hover,
        section[data-testid="stSidebar"] div[data-testid="stDownloadButton"] button:hover,
        section[data-testid="stSidebar"] div[data-testid="stLinkButton"] a:hover {
            background-color: #dde2e6 !important;
            border-color: #adb5bd !important;
            color: #000000 !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        }

        /* ✨ AQUÍ RECUPERAMOS EL COLOR GUINDA INSTITUCIONAL */
        section[data-testid="stSidebar"] button[kind="primary"] {
            border-radius: 6px !important;
            min-height: 38px !important;
            font-weight: 600 !important;
            margin-top: 4px !important;
        }
    </style>
""", unsafe_allow_html=True)

class ElementoControlLeyenda(MacroElement):
    def __init__(self, marcadores):
        super().__init__()
        hay_tanque_ex, hay_pozo_ex, hay_ptar_ex = False, False, False
        hay_tanque_req, hay_pozo_req, hay_ptar_req = False, False, False

        for pt in marcadores:
            texto = str(pt.get('tipo', '')).strip().lower()
            es_requerido = any(k in texto for k in ["requerid", "nuevo", "propuest"])
            if "tanque" in texto:
                if es_requerido: hay_tanque_req = True
                else: hay_tanque_ex = True
            elif "ptar" in texto or "tratamiento" in texto:
                if es_requerido: hay_ptar_req = True
                else: hay_ptar_ex = True
            else:
                if es_requerido: hay_pozo_req = True
                else: hay_pozo_ex = True

        span_edit = 'contenteditable="true" spellcheck="false" title="Haz clic para editar este texto" class="txt-leyenda-editable"'
        html_existente = ""
        if hay_tanque_ex or hay_pozo_ex or hay_ptar_ex:
            html_existente += f'<div {span_edit} style="font-weight: bold; font-style: italic; font-size: 13px; margin-bottom: 6px; color: #111;">Infraestructura Existente</div>'
            if hay_tanque_ex:
                html_existente += f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;"><div style="width: 14px; height: 16px; background-color: #008a3b; border: 0.5px solid #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.4); border-radius: 2px; flex-shrink: 0;"></div><span {span_edit}>Tanque existente</span></div>'
            if hay_pozo_ex:
                html_existente += f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;"><div style="width: 15px; height: 15px; background-color: #008a3b; border-radius: 50%; border: 0.5px solid #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.4); flex-shrink: 0;"></div><span {span_edit}>Pozo existente</span></div>'
            if hay_ptar_ex:
                html_existente += f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;"><svg width="16" height="16" viewBox="0 0 20 20" style="filter: drop-shadow(0 1px 2px rgba(0,0,0,0.4)); flex-shrink: 0;"><polygon points="10,2 18,18 2,18" fill="#008a3b" stroke="#ffffff" stroke-width="0.5" stroke-linejoin="round"/></svg><span {span_edit}>PTAR existente</span></div>'

        html_requerido = ""
        if hay_tanque_req or hay_pozo_req or hay_ptar_req:
            separador = '<div style="margin-top: 8px;"></div>' if html_existente else ''
            html_requerido += f'{separador}<div {span_edit} style="font-weight: bold; font-style: italic; font-size: 13px; margin-bottom: 6px; color: #111;">Infraestructura Requerida</div>'
            if hay_tanque_req:
                html_requerido += f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;"><div style="width: 14px; height: 16px; background-color: #9F2241; border: 0.5px solid #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.4); border-radius: 2px; flex-shrink: 0;"></div><span {span_edit}>Tanque requerido</span></div>'
            if hay_pozo_req:
                html_requerido += f'<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;"><div style="width: 15px; height: 15px; background-color: #9F2241; border-radius: 50%; border: 0.5px solid #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.4); flex-shrink: 0;"></div><span {span_edit}>Pozo requerido</span></div>'
            if hay_ptar_req:
                html_requerido += f'<div style="display: flex; align-items: center; gap: 8px;"><svg width="16" height="16" viewBox="0 0 20 20" style="filter: drop-shadow(0 1px 2px rgba(0,0,0,0.4)); flex-shrink: 0;"><polygon points="10,2 18,18 2,18" fill="#9F2241" stroke="#ffffff" stroke-width="0.5" stroke-linejoin="round"/></svg><span {span_edit}>PTAR requerido</span></div>'

        contenido_interior = html_existente + html_requerido
        self._template = Template(f"""
            {{% macro script(this, kwargs) %}}
            var legend_infra = L.control({{position: 'bottomright'}});
            legend_infra.onAdd = function (map) {{
                var div = L.DomUtil.create('div', 'info legend-infraestructura');
                L.DomEvent.disableClickPropagation(div);
                L.DomEvent.disableScrollPropagation(div);
                div.addEventListener('keydown', function(e) {{ e.stopPropagation(); }});
                div.addEventListener('keyup', function(e) {{ e.stopPropagation(); }});
                div.addEventListener('keypress', function(e) {{ e.stopPropagation(); }});
                div.innerHTML = `
                    <style>
                        .txt-leyenda-editable {{ cursor: text; padding: 1px 4px; border-radius: 3px; outline: none; border-bottom: 1px dashed transparent; transition: background-color 0.2s; }}
                        .txt-leyenda-editable:hover {{ background-color: rgba(0,0,0,0.05); border-bottom: 1px dashed #888; }}
                        .txt-leyenda-editable:focus {{background-color: #ffffff; border-bottom: 1.5px solid #2980b9; box-shadow: 0 1px 3px rgba(0,0,0,0.15);}}
                    </style>
                    <div style="background-color: rgba(255, 255, 255, 0.95); padding: 10px 14px; border: 1px solid #bbb; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.25); font-family: 'Segoe UI', Arial, sans-serif; font-size: 12px; line-height: 1.4; margin-bottom: 25px; margin-right: 5px; pointer-events: auto; max-width: 280px;">
                        {contenido_interior}
                    </div>
                `;
                return div;
            }};
            legend_infra.addTo({{{{this._parent.get_name()}}}});
            {{% endmacro %}}
        """)

def obtener_icono_infraestructura(tipo_str, color_personalizado=None):
    texto = str(tipo_str).strip().lower()
    if color_personalizado and str(color_personalizado).strip().startswith("#"): color_final = str(color_personalizado).strip()
    elif "existente" in texto: color_final = "#008a3b"
    elif any(k in texto for k in ["requerid", "nuevo", "propuest"]): color_final = "#9F2241"
    else: color_final = "#008a3b" if "pozo" in texto else "#9F2241"

    if "tanque" in texto:
        return folium.DivIcon(html=f'<div style="width: 16px; height: 20px; background-color: {color_final}; border: 0.5px solid #ffffff; border-radius: 3px; box-shadow: 0 2px 5px rgba(0,0,0,0.5); box-sizing: border-box;"></div>', icon_size=(16, 20), icon_anchor=(8, 10))
    elif "ptar" in texto or "tratamiento" in texto:
        return folium.DivIcon(html=f'<svg width="22" height="22" viewBox="0 0 22 22" style="filter: drop-shadow(0px 2px 4px rgba(0,0,0,0.5));"><polygon points="11,2 20,19 2,19" fill="{color_final}" stroke="#ffffff" stroke-width="0.5" stroke-linejoin="round"/></svg>', icon_size=(22, 22), icon_anchor=(11, 11))
    else:
        return folium.DivIcon(html=f'<div style="width: 17px; height: 17px; background-color: {color_final}; border: 0.5px solid #ffffff; border-radius: 50%; box-shadow: 0 2px 5px rgba(0,0,0,0.5); box-sizing: border-box;"></div>', icon_size=(17, 17), icon_anchor=(8, 8))

def auto_identificar_acuifero(lat, lon):
    try:
        val_lat = float(lat)
        val_lon = -abs(float(lon))
        pt_geom = Point(val_lon, val_lat)
        
        gdf_consulta = gdf_maestro
        if gdf_consulta.crs is None: gdf_consulta = gdf_consulta.set_crs(epsg=4326)
        posibles = gdf_consulta.iloc[list(gdf_consulta.sindex.intersection(pt_geom.bounds))]
        if posibles.empty: 
            posibles = gdf_consulta.iloc[list(gdf_consulta.sindex.intersection(pt_geom.buffer(0.0001).bounds))]

        coincidencias = posibles[posibles.geometry.contains(pt_geom)]
        if coincidencias.empty: 
            coincidencias = posibles[posibles.geometry.intersects(pt_geom.buffer(0.0001))]
        
        if not coincidencias.empty:
            fila = coincidencias.iloc[0]
            edo = limpiar_texto(fila['NOM_EDO'])
            label = f"{limpiar_texto(fila['CLV_ACUI'])} - {limpiar_texto(fila['NOM_ACUI'])}"
            if st.session_state.get("sb_acuifero") != label:
                st.session_state["sb_estado"] = edo
                st.session_state["sb_acuifero"] = label
                st.session_state["filtro_estado_sel"] = edo
                st.session_state["filtro_acuifero_sel"] = label
                st.session_state["puntos_recien_cargados"] = True
            return True
    except Exception: pass
    return False

def agregar_punto():
    lat = st.session_state.get("visor_lat_punto", 0.0)
    lon = st.session_state.get("visor_lon_punto", 0.0)
    nom = st.session_state.get("visor_nombre_punto", "").strip()
    tipo = st.session_state.get("visor_tipo_punto", "Pozo existente")
    if lat != 0.0 and lon != 0.0:
        lon_final = -abs(float(lon))
        st.session_state["lista_marcadores"].append({"lat": float(lat), "lon": lon_final, "nombre": nom if nom else f"Punto {len(st.session_state['lista_marcadores'])+1}", "tipo": tipo})
        auto_identificar_acuifero(lat, lon_final)
        st.session_state["visor_lat_punto"] = 0.0
        st.session_state["visor_lon_punto"] = 0.0
        st.session_state["visor_nombre_punto"] = ""

def limpiar_coords():
    st.session_state["lista_marcadores"] = []
    st.session_state["visor_lat_punto"] = 0.0
    st.session_state["visor_lon_punto"] = 0.0
    st.session_state["visor_nombre_punto"] = ""
    st.session_state["csv_uploader_key"] += 1

# =======================================================
# 📍 CONTROLES DE PUNTOS AISLADOS (NO BLOQUEAN LA APP)
# =======================================================
@st.fragment
def renderizar_controles_puntos():
    tab_manual, tab_csv = st.tabs(["✍️ Manual", "📁 Carga CSV"])
    
    with tab_manual:
        st.text_input("Identificador:", key="visor_nombre_punto", placeholder="Ej. Pozo San Bernardo")
        tipo_infra = st.selectbox("Tipo de Infraestructura:", ["Pozo existente", "Pozo requerido", "PTAR existente", "PTAR requerido", "Tanque existente", "Tanque requerido"], key="visor_tipo_punto")
        col_lat, col_lon = st.columns(2)
        col_lat.number_input("Latitud (N):", value=0.0, format="%.5f", key="visor_lat_punto")
        col_lon.number_input("Longitud (W):", value=0.0, format="%.5f", key="visor_lon_punto")
        c_btn1, c_btn2 = st.columns(2)
        
        c_btn1.button("➕ Agregar", on_click=agregar_punto, use_container_width=True, type="primary")
        c_btn2.button("🧹 Limpiar", on_click=limpiar_coords, use_container_width=True, type="secondary", key="btn_limpiar_manual")

    with tab_csv:
        st.markdown("""<div style="background-color: #f8f9fa; border: 1px dashed #ced4da; border-radius: 4px; padding: 6px 10px; font-size: 10px; color: #495057; margin-bottom: 8px;">Requisitos: columnas <b>Latitud</b> y <b>Longitud</b>. <i>(Nombre opcional)</i></div>""", unsafe_allow_html=True)
        
        uploader_key = f"file_uploader_{st.session_state.get('csv_uploader_key', 0)}"
        archivo_csv = st.file_uploader("Seleccionar archivo CSV", type=['csv'], label_visibility="collapsed", key=uploader_key)
        
        c_csv1, c_csv2 = st.columns(2)
        c_csv2.button("🧹 Limpiar", on_click=limpiar_coords, use_container_width=True, type="secondary", key="btn_limpiar_csv")
        
        if archivo_csv is not None:
            if c_csv1.button("🚀 Cargar", use_container_width=True, type="primary", key="btn_cargar_csv"):
                try:
                    archivo_csv.seek(0)
                    try: 
                        df_puntos = pd.read_csv(archivo_csv, sep=None, engine='python', encoding='utf-8-sig')
                    except Exception: 
                        archivo_csv.seek(0)
                        df_puntos = pd.read_csv(archivo_csv, sep=';', encoding='latin1')
                        
                    df_puntos.columns = df_puntos.columns.astype(str).str.strip()
                    cols_upper = [c.upper() for c in df_puntos.columns]
                    
                    col_lat_csv = next((c for c, u in zip(df_puntos.columns, cols_upper) if any(k in u for k in ['LATITUD', 'LAT', 'Y', 'NORTE'])), None)
                    col_lon_csv = next((c for c, u in zip(df_puntos.columns, cols_upper) if any(k in u for k in ['LONGITUD', 'LON', 'LONG', 'X', 'OESTE'])), None)
                    col_infra_csv = next((c for c, u in zip(df_puntos.columns, cols_upper) if any(k in u for k in ['INFRAESTRUCTURA', 'INFRA', 'TIPO', 'CATEGORIA'])), None)
                    col_nom_csv = next((c for c, u in zip(df_puntos.columns, cols_upper) if any(k in u for k in ['NOMBRE/SITIO', 'NOMBRE', 'SITIO', 'NOM', 'ID', 'ESTACION'])), None)
                    col_color_csv = next((c for c, u in zip(df_puntos.columns, cols_upper) if any(k in u for k in ['COLOR', 'HEX'])), None)

                    if col_lat_csv and col_lon_csv:
                        nuevos_puntos = []
                        for _, row in df_puntos.iterrows():
                            lat_val = pd.to_numeric(str(row[col_lat_csv]).replace(',', '.').strip(), errors='coerce')
                            lon_val = pd.to_numeric(str(row[col_lon_csv]).replace(',', '.').strip(), errors='coerce')
                            
                            if pd.notna(lat_val) and pd.notna(lon_val):
                                infra_val = str(row[col_infra_csv]).strip() if col_infra_csv and pd.notna(row[col_infra_csv]) else "Pozo existente"
                                nom_val = str(row[col_nom_csv]).strip() if col_nom_csv and pd.notna(row[col_nom_csv]) else infra_val
                                color_val = str(row[col_color_csv]).strip() if col_color_csv and pd.notna(row[col_color_csv]) else None
                                nuevos_puntos.append({"lat": float(lat_val), "lon": -abs(float(lon_val)), "nombre": nom_val, "tipo": infra_val, "color_hex": color_val})
                        
                        if nuevos_puntos:
                            st.session_state["puntos_recien_cargados"] = True
                            st.session_state["lista_marcadores"].extend(nuevos_puntos)
                            
                            for pt in nuevos_puntos:
                                if auto_identificar_acuifero(pt["lat"], pt["lon"]): break
                            
                            st.success(f"✅ {len(nuevos_puntos)} puntos cargados correctamente.")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ No se encontraron coordenadas numéricas válidas en las filas.")
                    else: 
                        st.error(f"❌ Faltan columnas de Latitud/Longitud. Columnas detectadas: {', '.join(df_puntos.columns)}")
                except Exception as e: 
                    st.error(f"❌ Error al procesar el archivo: {e}")
        else:
            c_csv1.button("🚀 Cargar", use_container_width=True, type="primary", disabled=True, key="btn_cargar_csv_dis")

    if len(st.session_state["lista_marcadores"]) > 0:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        df_descarga = pd.DataFrame(st.session_state["lista_marcadores"]).rename(columns={"tipo": "Infraestructura", "nombre": "Nombre", "lat": "Latitud", "lon": "Longitud"})
        csv_data = df_descarga[[c for c in ["Infraestructura","Nombre", "Latitud", "Longitud"] if c in df_descarga.columns]].to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="⬇️ Descargar Puntos (CSV)", data=csv_data, file_name="puntos_guardados.csv", mime="text/csv", use_container_width=True)

with st.sidebar:
    renderizar_controles_puntos()

if seleccion_final and datos_ac is not None:
    st.sidebar.download_button(
        label="🌍 Descargar KMZ (Acuífero y Capas)",
        data=obtener_kmz_cacheado(
            clave_sel, 
            nombre_ac, 
            datos_ac, 
            tuple(capas_seleccionadas), 
            str(st.session_state.get("lista_marcadores", [])),
            diccionario_capas
        ),
        file_name=f"{clave_sel}_{nombre_ac.replace(' ', '_')}.kmz",
        mime="application/vnd.google-earth.kmz",
        use_container_width=True
    )

# =======================================================
# 🟢 SINCRONIZACIÓN Y PROCESAMIENTO BAJO DEMANDA (LAZY)
# =======================================================
if seleccion_final:
    clave_sel = seleccion_final.split(" - ")[0]
    if st.session_state.get("acuifero_en_pantalla_sig") != clave_sel:
        if st.session_state.get("puntos_recien_cargados", False):
            st.session_state["puntos_recien_cargados"] = False
        else:
            st.session_state["lista_marcadores"] = []
            
        st.session_state["acuifero_en_pantalla_sig"] = clave_sel
    
    st.session_state["clave_sig"] = clave_sel
    st.session_state["nombre_sig"] = nombre_ac
    if 'AREA_KM2' in datos_ac:
        st.session_state["area_total_sig"] = round(float(datos_ac['AREA_KM2']), 1)
    
    clave_acuifero = st.session_state["clave_sig"]
    nombre_acuifero = st.session_state["nombre_sig"]

    st.sidebar.markdown("---")
    st.sidebar.subheader("⛰️ Mapa Geológico")
    
    df_links_global = get_df_links()
    if df_links_global is not None:
        link_row = df_links_global[df_links_global['clave'] == clave_sel]
        if not link_row.empty:
            file_id_geo = procesar_link_drive(link_row.iloc[0].get('link'))
            if file_id_geo:
                st.sidebar.link_button("⬇️ Descargar Mapa (PNG)", url=f"https://drive.google.com/uc?export=download&id={file_id_geo}", use_container_width=True)
            else: st.sidebar.info("📂 Mapa geológico próximamente disponible.")
        else: st.sidebar.info("📂 Mapa geológico próximamente disponible.")
    
    parrafo_vol_ia, vol_total, df_resumen = "No hay información de volúmenes REPDA disponible.", 0.0, pd.DataFrame()
    df_repda_global = get_df_repda()
    if df_repda_global is not None:
        r_filtrado = df_repda_global[df_repda_global['Clave de acuífero'] == clave_acuifero]
        if not r_filtrado.empty:
            d_repda = r_filtrado.iloc[0]
            vol_total = float(d_repda.get('Volumen total (hm3/año)', 0.0)) if pd.notna(d_repda.get('Volumen total (hm3/año)')) else 0.0
            registros = [{"Tipo de Uso": c.replace(" (hm3/año)", "").strip(), "Volumen (hm³/año)": float(d_repda[c]), "Porcentaje (%)": (float(d_repda[c])/vol_total)*100} for c in df_repda_global.columns if c not in ['Clave de acuífero', 'Acuífero', 'Volumen total (hm3/año)', 'Porcentaje Total'] and pd.notna(d_repda.get(c)) and float(d_repda.get(c))>0]
            if registros:
                df_resumen = pd.DataFrame(registros).sort_values(by="Volumen (hm³/año)", ascending=False).reset_index(drop=True)
                df_texto = df_resumen[df_resumen['Volumen (hm³/año)'] >= 0.1].copy().reset_index(drop=True)
                if not df_texto.empty:
                    dic_usos = {"Agrícola": "uso agrícola", "Público Urbano": "uso público-urbano", "Industrial": "uso industrial", "Pecuario": "uso pecuario", "Doméstico": "uso doméstico", "Acuacultura": "uso de acuacultura", "Diferentes usos": "diferentes usos", "Servicios": "servicios", "Comercio": "comercio", "Otros": "otros usos"}
                    frags = [f"{r['Volumen (hm³/año)']:.1f} hm³/año ({r['Porcentaje (%)']:.1f} %) " + ("corresponde a " if i == 0 else "a ") + dic_usos.get(r['Tipo de Uso'].strip(), r['Tipo de Uso'].strip().lower()) for i, r in df_texto.iterrows()]
                    parrafo_vol_ia = f"El volumen total de extracción para esa fecha asciende a {vol_total:.1f} hm³/año del cual {', '.join(frags[:-1]) + f', y {frags[-1]}' if len(frags)>1 else frags[0]}."

    parrafo_aprov_ia, total_aprov, conteo_usos = "No hay información de conteo de aprovechamientos disponible.", 0, pd.DataFrame()
    df_aprov_global = get_df_aprov()
    if df_aprov_global is not None:
        a_filtrado = df_aprov_global[df_aprov_global['Cve_Acuif'] == clave_acuifero]
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
    df_zonas_global = get_df_zonas()
    if df_zonas_global is not None:
        z_filt = df_zonas_global[df_zonas_global['CLAVE DEL ACUÍFERO'] == clave_acuifero]
        if not z_filt.empty and pd.notna(z_filt.iloc[0].get('ZONA DE DISPONIBILIDAD')):
            dato_zona_disp = str(z_filt.iloc[0].get('ZONA DE DISPONIBILIDAD')).strip()
    
    parrafo_dma_ia = "No hay información de balance disponible."
    df_bal_ent_global = get_df_bal_ent()
    df_bal_sal_global = get_df_bal_sal()
    df_veas_global = get_df_veas()
    
    if df_bal_ent_global is not None and df_bal_sal_global is not None:
        bal_ent = df_bal_ent_global[df_bal_ent_global['CLV_ACUI'] == clave_acuifero]
        bal_sal = df_bal_sal_global[df_bal_sal_global['CLV_ACUI'] == clave_acuifero]
        
        if not bal_ent.empty and not bal_sal.empty:
            v_r_total = buscar_valor(bal_ent, "R", es_total=True)
            match_dnc = bal_sal[bal_sal['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, na=False)]
            if not match_dnc.empty:
                val_crudo = match_dnc.iloc[-1]['DNC_hm3']
                v_dnc_total = float(val_crudo) if pd.notna(val_crudo) and str(val_crudo).strip().lower() not in ['none', '', 'nan'] else 0.0
            else:
                v_dnc_total = pd.to_numeric(bal_sal['DNC_hm3'].astype(str).replace(['None', 'none', '', 'NaN'], '0'), errors='coerce').fillna(0).sum()

            v_veas = float(df_veas_global[df_veas_global['CLAVE'] == clave_acuifero].iloc[0]['VEAS_hm3']) if df_veas_global is not None and not df_veas_global[df_veas_global['CLAVE'] == clave_acuifero].empty else 0.0
            val_dma = round(v_r_total, 1) - round(v_dnc_total, 1) - v_veas
            parrafo_dma_ia = f"La Disponibilidad Media Anual (DMA) calculada para este acuífero es de {val_dma:,.6f} hm³."

    file_id_objetivo = None
    df_enlaces_docs = get_df_enlaces()
    if df_enlaces_docs is not None:
        enlace_row = df_enlaces_docs[df_enlaces_docs['CLAVE_ACUIFERO'] == clave_acuifero]
        if not enlace_row.empty:
            file_id_objetivo = procesar_link_drive(enlace_row.iloc[0]['ENLACE_DRIVE'])
    st.session_state[f"file_id_{clave_acuifero}"] = file_id_objetivo

    if st.session_state.get("last_purged_clave") != clave_acuifero:
        st.session_state["last_purged_clave"] = clave_acuifero
        for k in list(st.session_state.keys()):
            if k.startswith("doc_listo_") and k != f"doc_listo_{clave_acuifero}": del st.session_state[k]

    st.session_state[f"p_aprov_{clave_acuifero}"] = parrafo_aprov_ia
    st.session_state[f"p_vol_{clave_acuifero}"] = parrafo_vol_ia

    col_tit, col_btn = st.columns([0.50, 0.50], vertical_alignment="center")

    with col_tit:
        st.markdown(f"<h3 style='font-size: 35px; color: #691C32; margin: 0;'>📋 RESUMEN: {clave_acuifero} - {nombre_acuifero}</h3>", unsafe_allow_html=True)
        st.caption(f"Estado: {estado_seleccionado}")

    st.markdown("""<style>div[data-testid="stVerticalBlock"]:has(#alerta-card-doc)[data-stale="true"] { opacity: 1 !important; }</style>""", unsafe_allow_html=True)

    @st.fragment
    def procesador_fluido_estandarizacion():
        import traceback
        from core.estandarizador_acuiferos import ejecutar_estandarizacion_v31
        from core.generador_word import (inyectar_tabla_vertices_en_word, inyectar_tabla_flujo_en_word,
                                        inyectar_tabla_almacenamiento_en_word, inyectar_tabla_evapotranspiracion_en_word, 
                                        modificar_censo_y_bombeo)
        clave_ac = st.session_state["clave_sig"]
        f_id = st.session_state.get(f"file_id_{clave_ac}")
        p_a = st.session_state.get(f"p_aprov_{clave_ac}", "")
        p_v = st.session_state.get(f"p_vol_{clave_ac}", "")
        doc_key = f"doc_listo_{clave_ac}"

        with st.container(border=True):
            st.markdown('<span id="alerta-card-doc"></span>', unsafe_allow_html=True)
            c_text, c_btn = st.columns([0.65, 0.35], vertical_alignment="center")
        
            with c_text:
                st.markdown("""<div style="display: flex; align-items: center; gap: 10px; margin: 0px;"><div style="font-size: 18px; line-height: 1;">📄</div><div><p style="margin: 0px; font-weight: 600; color: #691C32; font-size: 11px; line-height: 1.2;">Documento de Actualización-BAS</p><p style="margin: 2px 0px 0px 0px; font-size: 9px; color: #666; line-height: 1.2;">Genera un nuevo documento con el formato actualizado a partir de la versión anterior almacenada en la base de datos.</p></div></div>""", unsafe_allow_html=True)
        
            with c_btn:
                if not f_id:
                    st.markdown("""<div style="background-color: #eef6fb; border: 1px solid #b8daff; padding: 4px 8px; border-radius: 4px; display: flex; align-items: center; gap: 6px; margin-top: 5px;"><span style="font-size: 12px; line-height: 1;">ℹ️</span><span style="color: #004085; font-size: 9px; font-weight: normal; line-height: 1.1;">Sin archivo Drive vinculado a este acuífero en la base de datos.</span></div>""", unsafe_allow_html=True)
                    return
        
                espacio_interactivo = st.empty()
                if doc_key in st.session_state:
                    espacio_interactivo.download_button(label="⬇️ Descargar Documento", data=st.session_state[doc_key], file_name=f"{clave_ac}_ESTANDARIZADO_V3.1.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary", use_container_width=True, key=f"btn_dl_{clave_ac}")
                else:
                    if espacio_interactivo.button("⚙️ Procesar", type="primary", use_container_width=True, key=f"btn_proc_{clave_ac}"):
                        espacio_interactivo.empty()
                        with espacio_interactivo.container():
                            marcador = st.empty()
                            barra = st.progress(0)
                            exito = False
        
                            try:
                                def alerta_mini(icono, texto, tipo="info"):
                                    colores = {"info": ("#eef6fb", "#b8daff", "#004085"), "success": ("#e6f4ea", "#c3e6cb", "#155724"), "error": ("#f8d7da", "#f5c6cb", "#721c24")}
                                    bg, borde, txt = colores[tipo]
                                    return f'''<div style="background-color: {bg}; border: 1px solid {borde}; padding: 4px 8px; border-radius: 4px; display: flex; align-items: center; gap: 6px; margin-bottom: 5px;"><span style="font-size: 12px; line-height: 1;">{icono}</span><span style="color: {txt}; font-size: 9px; font-weight: normal; line-height: 1.1;">{texto}</span></div>'''

                                marcador.markdown(alerta_mini("⏳", "Descargando archivo base de Google Drive..."), unsafe_allow_html=True)
                                barra.progress(25)
                                respuesta = requests.get(f"https://docs.google.com/document/d/{f_id}/export?format=docx", timeout=30)
                                if respuesta.status_code != 200: raise Exception(f"Drive rechazó la descarga (HTTP {respuesta.status_code}).")

                                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_origen:
                                    tmp_origen.write(respuesta.content)
                                    ruta_origen = tmp_origen.name

                                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_salida:
                                    ruta_salida = tmp_salida.name

                                marcador.markdown(alerta_mini("📐", "Estandarizando y consolidando formatos..."), unsafe_allow_html=True)
                                barra.progress(50)
                                ejecutar_estandarizacion_v31(str(DIRECTORIO_RAIZ / "assets" / "PLANTILLA_V3.1.docx"), ruta_origen, ruta_salida)

                                marcador.markdown(alerta_mini("📊", "Inyectando tablas de balance y poligonales..."), unsafe_allow_html=True)
                                barra.progress(75)
                                inyectar_tabla_vertices_en_word(ruta_salida, clave_ac, get_df_vertices())
                                inyectar_tabla_flujo_en_word(ruta_salida, clave_ac, get_df_flujo_ent(), ["tabla", "entradas", "flujo"], "Entradas")
                                inyectar_tabla_flujo_en_word(ruta_salida, clave_ac, get_df_flujo_sal(), ["tabla", "salidas", "flujo"], "Salidas")
                                modificar_censo_y_bombeo(ruta_salida, p_a, p_v)
                                inyectar_tabla_almacenamiento_en_word(ruta_salida, clave_ac, get_df_almacenamiento())
                                inyectar_tabla_evapotranspiracion_en_word(ruta_salida, clave_ac, get_df_etr())

                                marcador.markdown(alerta_mini("✅", "¡Documento generado con éxito!", "success"), unsafe_allow_html=True)
                                barra.progress(100)
                                with open(ruta_salida, "rb") as f: st.session_state[doc_key] = f.read()
                                exito = True
                            except Exception as e:
                                marcador.markdown(alerta_mini("❌", f"Error técnico: {str(e)}", "error"), unsafe_allow_html=True)
                                with st.expander("Ver detalle técnico (Traceback)", expanded=True): st.code(traceback.format_exc(), language="python")
        
                        if exito:
                            espacio_interactivo.empty()
                            espacio_interactivo.download_button(label="⬇️ Descargar", data=st.session_state[doc_key], file_name=f"{clave_ac}_ESTANDARIZADO_V3.1.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary", use_container_width=True, key=f"btn_dl_post_{clave_ac}")

    with col_btn:
        procesador_fluido_estandarizacion()
    
    st.divider()

    # =======================================================
    # 🗺️ VISOR GEOGRÁFICO INTERACTIVO (SIG)
    # =======================================================
    st.subheader("🗺️ Visores Espaciales")
    
    @st.fragment
    def renderizar_modulo_mapa(datos_ac, nombre_acuifero, capas_seleccionadas, diccionario_capas, file_id_geo, marcadores):
        def normalizar_clave_geo(val):
            try: return str(int(float(val))).zfill(4)
            except: return str(val).strip().zfill(4)

        clave_sel_norm = normalizar_clave_geo(datos_ac['CLV_ACUI'])

        if file_id_geo: 
            tab_visor, tab_geo = st.tabs(["🗺️ Visor Interactivo (SIG)", "⛰️ Mapa Geológico Estático"])
        else: 
            tab_visor, tab_geo = st.tabs(["🗺️ Visor Interactivo (SIG)", "⛰️ Mapa Geológico (No Disponible)"])

        with tab_visor:
            try:
                centroide = datos_ac.geometry.centroid
                
                if marcadores:
                    ultimo_pt = marcadores[-1]
                    map_center, map_zoom = [ultimo_pt["lat"], ultimo_pt["lon"]], 13
                else:
                    map_center, map_zoom = [centroide.y, centroide.x], 10
                    
                m = folium.Map(location=map_center, zoom_start=map_zoom, tiles=None, control_scale=True, prefer_canvas=True)
                
                if not marcadores:
                    b = datos_ac.geometry.bounds
                    m.fit_bounds([[b[1], b[0]], [b[3], b[2]]])
                
                estilos_arbol = """
                <style>
                    .leaflet-container { background-color: #ffffff !important; }
                    img.leaflet-tile[src*="google"], img.leaflet-tile[src*="lyrs=s"], .tile-Google Satelital Transparencia img {
                        filter: grayscale(100%) !important; -webkit-filter: grayscale(100%) !important; opacity: 0.30 !important;
                    }
                    .leaflet-top.leaflet-right { z-index: 1005 !important; }
                    .leaflet-control-layers, .leaflet-control-layers-expanded { z-index: 1006 !important; overflow: hidden !important; }
                    .leaflet-control-layers-list { max-height: 65vh !important; overflow-y: auto !important; overflow-x: hidden !important; padding-right: 6px !important; }
                    .leaflet-control-layers-list::-webkit-scrollbar { width: 6px !important; }
                    .leaflet-control-layers-list::-webkit-scrollbar-track { background: #f1f1f1 !important; border-radius: 4px !important; }
                    .leaflet-control-layers-list::-webkit-scrollbar-thumb { background: #c1c1c1 !important; border-radius: 4px !important; }
                    .leaflet-control-layers { font-size: 15px !important; font-family: Roboto, sans-serif; }
                    .leaflet-layerstree-children span { font-size: 15px !important; }
                    input.leaflet-control-layers-selector { margin-right: 8px !important; cursor: pointer; vertical-align: middle !important; }
                    .leaflet-layerstree-children { padding-left: 15px !important; margin-left: 8px !important; border-left: 1px solid #dcdde1; margin-top: 4px !important; }
                    .leaflet-layerstree-node { margin-bottom: 0.5px !important; }
                    .leaflet-layerstree-node label { padding: 4px 6px; border-radius: 4px; transition: background-color 0.2s ease; display: block; }
                    .leaflet-layerstree-node label:hover { background-color: #f1f3f6; }
                    .etiqueta-sin-fondo {background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important;}
                    .etiqueta-sin-fondo::before { display: none !important; }
                    .leaflet-bottom.leaflet-left { display: flex !important; flex-direction: column !important; align-items: flex-start !important; }
                    .leaflet-control-scale { order: 1 !important; margin: 0 0 4px 10px !important; }
                    .leaflet-control-mouseposition { order: 2 !important; position: static !important; transform: none !important; margin: 0 0 10px 10px !important; background-color: rgba(255, 255, 255, 0.85) !important; padding: 2px 8px !important; border: 1px solid #bbb !important; border-radius: 4px !important; font-family: 'Segoe UI', sans-serif !important; font-size: 11px !important; font-weight: 600 !important; color: #333333 !important; box-shadow: 0 1px 4px rgba(0,0,0,0.15) !important; pointer-events: auto !important; }
                </style>
                """
                m.get_root().header.add_child(folium.Element(estilos_arbol))
                
                mapa_neutral = folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Neutral (defecto)', overlay=False, control=False, show=True).add_to(m)
                mapa_osm = folium.TileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', attr='OpenStreetMap', name='OpenStreetMap', overlay=False, control=False, show=False).add_to(m)
                mapa_estandar = folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Estándar (ESRI)', overlay=False, control=False, show=False).add_to(m)
                mapa_satelite = folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satélite (ESRI)', overlay=False, control=False, show=False).add_to(m)
                mapa_topo = folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Topográfico (ESRI)', overlay=False, control=False, show=False).add_to(m)
                mapa_terreno = folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Terreno (ESRI)', overlay=False, control=False, show=False).add_to(m)
                mapa_oceanos = folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Océanos (ESRI)', overlay=False, control=False, show=False).add_to(m)
                mapa_oscuro = folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Gris Oscuro (ESRI)', show=False).add_to(m)
                mapa_topo_gris = folium.TileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google Satellite', name='Google Satelital Transparencia 35%', className="tile-satelital-qgis", overlay=False, control=False, show=False).add_to(m)

                plugins.Fullscreen(position='topright', title='Pantalla completa', force_separate_button=True).add_to(m)
                plugins.MeasureControl(position='topleft', primary_length_unit='kilometers', primary_area_unit='sqmeters').add_to(m)
                plugins.MousePosition(position='bottomleft', separator=' | ', empty_string='Fuera del mapa', lng_first=False, num_digits=5, prefix='Coordenadas:').add_to(m)
                
                estilo_acuifero = "background-color: #ffffff; color: #691C32; font-family: 'Segoe UI', sans-serif; font-size: 14px; font-weight: bold; padding: 10px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); border-left: 4px solid #691C32;"
                
                gdf_acuifero_ligero = gpd.GeoDataFrame(geometry=[datos_ac.geometry], crs="EPSG:4326")
                
                capa_acuifero = folium.GeoJson(
                    gdf_acuifero_ligero, name="Límite del Acuífero",
                    style_function=lambda x: {'fillColor': '#3186cc', 'color': '#1a5276', 'weight': 3, 'fillOpacity': 0.10},
                    tooltip=folium.Tooltip(f"Acuífero: {nombre_acuifero}", style=estilo_acuifero, sticky=True)
                ).add_to(m)

                nodos_capas = [] 

                with st.spinner("Procesando información espacial..."):
                    for capa_visual in capas_seleccionadas:
                        id_archivo, color_hex, campo_nombre = diccionario_capas[capa_visual]
                        
                        frac_local = obtener_capa_exacta_cache(id_archivo, clave_sel_norm)
                        
                        if frac_local is not None and not frac_local.empty:
                            frac_segura = frac_local.copy()
                            geom_acuifero = datos_ac.geometry.buffer(0)
                            nucleo_acuifero = geom_acuifero.buffer(-0.001)
                            es_punto_linea = frac_segura.geometry.geom_type.isin(['Point', 'MultiPoint', 'LineString', 'MultiLineString'])
                            toca_normal = frac_segura.geometry.intersects(geom_acuifero)
                            toca_nucleo = frac_segura.geometry.intersects(nucleo_acuifero)
                            
                            mascara_valida = (es_punto_linea & toca_normal) | (~es_punto_linea & toca_nucleo)
                            
                            frac_segura = frac_segura[mascara_valida].copy()
                            if frac_segura.empty:
                                continue 

                            col_nombre_final = campo_nombre
                            if col_nombre_final not in frac_segura.columns:
                                cols_upper = [c.upper() for c in frac_segura.columns]
                                for candidato in ['NOMGEO', 'NOM_LOC', 'NOMBRE', 'LOC']:
                                    if candidato in cols_upper:
                                        col_nombre_final = frac_segura.columns[cols_upper.index(candidato)]
                                        break

                            # Limpiar textos y evitar errores de codificación
                            cols = [c for c in frac_segura.columns if c not in ['geometry', 'CLV_TEMP', 'CLV_ACUI']]
                            for c in cols: frac_segura[c] = frac_segura[c].apply(lambda x: limpiar_texto(x) if pd.notna(x) else "")
                            frac_segura[cols] = frac_segura[cols].astype(str)
                            
                            estilo_tooltip = f"background-color: #ffffff; border: 1px solid #e0e0e0; border-left: 4px solid {color_hex}; border-radius: 6px; color: #2c3e50; font-family: 'Segoe UI', sans-serif; font-size: 13px; max-width: 85vw; padding: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"
                            
                            hijos_de_esta_capa = []
                            
                            # 🚀 OPTIMIZACIÓN EXTREMA 1: Usar groupby en lugar de iterar y filtrar el DataFrame
                            agrupado = frac_segura.groupby(col_nombre_final)
                            
                            for nombre_unico, gdf_individual in agrupado:
                                nom_mostrar = str(nombre_unico).strip()
                                
                                if capa_visual in ["Vedas", "Zonas Reglamentadas", "Zonas de Reserva"]:
                                    fecha_dof = ""
                                    if 'FECHA_DOF' in gdf_individual.columns:
                                        val = gdf_individual.iloc[0]['FECHA_DOF']
                                        if pd.notna(val) and str(val).strip() != "":
                                            try: fecha_dof = pd.to_datetime(val).strftime('%d-%m-%Y')
                                            except: fecha_dof = str(val).strip()[:10] 
                                    nom_mostrar = f"{fecha_dof}" if fecha_dof else "Sin Fecha"
                                else:
                                    if len(nom_mostrar) > 30: nom_mostrar = nom_mostrar[:27] + "..."
                                
                                if capa_visual == "Localidades":
                                    estilo_actual = {'fill': False, 'fillOpacity': 0.0, 'color': '#000000', 'weight': 2.5, 'dashArray': '8, 6', 'opacity': 1.0}
                                    resaltado_actual = {'color': '#2980b9', 'weight': 3.5, 'dashArray': '8, 6', 'fillOpacity': 0.0}
                                else:
                                    estilo_actual = {'fillColor': color_hex, 'color': color_hex, 'weight': 2, 'fillOpacity': 0.35}
                                    resaltado_actual = {'fillColor': color_hex, 'color': '#FFD700', 'weight': 3, 'fillOpacity': 0.85}

                                # 🚀 OPTIMIZACIÓN EXTREMA 2: Usar __geo_interface__ evita que Folium serialice el DataFrame desde cero
                                capa_individual = folium.GeoJson(
                                    data=gdf_individual.__geo_interface__, 
                                    name=nom_mostrar,
                                    show=True,
                                    style_function=lambda feature, est=estilo_actual: est,
                                    highlight_function=lambda x, res=resaltado_actual: res,
                                    tooltip=folium.GeoJsonTooltip(fields=[col_nombre_final], aliases=[f"<b>{capa_visual.upper()}</b><br>"], localize=True, sticky=True, labels=True, style=estilo_tooltip)
                                ).add_to(m)
                                
                                hijos_de_esta_capa.append({"label": f"{nom_mostrar}", "layer": capa_individual})
                                
                            if hijos_de_esta_capa:
                                # Ordenamos los hijos alfabéticamente para que el árbol se vea perfecto
                                hijos_de_esta_capa = sorted(hijos_de_esta_capa, key=lambda x: x["label"])
                                
                                nodos_capas.append({
                                    "label": f"<span style='color: #691C32; font-weight: bold;'>{capa_visual.upper()}</span>",
                                    "select_all_checkbox": "<span style='font-size: 0.9em; color: #2980b9;'>Seleccionar todo</span>", 
                                    "collapsed": True,
                                    "children": hijos_de_esta_capa
                                })

                arbol_base = {
                    "label": "<b>MAPAS DE FONDO</b>",
                    "children": [
                        {"label": "Neutral (defecto)", "layer": mapa_neutral},
                        {"label": "OpenStreetMap", "layer": mapa_osm},
                        {"label": "Estándar (ESRI)", "layer": mapa_estandar},
                        {"label": "Satélite (ESRI)", "layer": mapa_satelite},
                        {"label": "Topográfico (ESRI)", "layer": mapa_topo},
                        {"label": "Terreno (ESRI)", "layer": mapa_terreno},
                        {"label": "Océanos (ESRI)", "layer": mapa_oceanos},
                        {"label": "Gris Oscuro (ESRI)", "layer": mapa_oscuro},
                        {"label": "Google Satelital gris 35%", "layer": mapa_topo_gris}
                    ]
                }
                arbol_overlays = {
                    "label": "<b>INFORMACIÓN VECTORIAL</b>",
                    "children": [{"label": "<span style='color: #691C32; font-weight: bold;'>LÍMITE DEL ACUÍFERO</span>", "layer": capa_acuifero}] + nodos_capas
                }

                plugins.TreeLayerControl(base_tree=arbol_base, overlay_tree=arbol_overlays, closed_symbol='▶', opened_symbol='▼').add_to(m)
                
                slot_switch = st.empty()
                mostrar_todos_los_nombres = False
                if marcadores:
                    with slot_switch.container():
                        c_switch, _ = st.columns([0.45, 0.55])
                        with c_switch:
                            mostrar_todos_los_nombres = st.toggle("🏷️ Mostrar todos los nombres", value=False, key=f"toggle_pts_{clave_sel_norm}")

                    for pt in marcadores:
                        nom_pt = pt.get('nombre', 'Punto')
                        tipo_pt = pt.get('tipo', nom_pt)
                        html_texto = f"""<div style="font-family: 'Segoe UI', sans-serif; min-width: 140px;"><h4 style="margin: 0 0 4px 0; color: #691C32; font-size: 13px; border-bottom: 1px solid #ccc; padding-bottom: 2px;">{nom_pt}</h4><div style="font-size: 11px; color: #333; line-height: 1.4;"><b>Tipo:</b> {tipo_pt}<br><b>Lat:</b> {pt['lat']:.5f}<br><b>Lon:</b> {pt['lon']:.5f}</div></div>"""
                        marcador = folium.Marker([pt['lat'], pt['lon']], icon=obtener_icono_infraestructura(tipo_pt, pt.get('color_hex')))
                        marcador.add_child(folium.Popup(html_texto, max_width=300, auto_close=False, close_on_click=False))
                        if mostrar_todos_los_nombres:
                            marcador.add_child(folium.Tooltip(f"<span style='font-family: Arial, sans-serif; font-size: 13px; font-weight: bold; color: #000000;'>{nom_pt}</span>", permanent=True, direction="top", offset=(0, -10), class_name="etiqueta-sin-fondo", style="background: transparent; border: none; box-shadow: none;"))
                        marcador.add_to(m)
                    m.add_child(ElementoControlLeyenda(marcadores))

                hash_capas = "_".join([c[:3] for c in capas_seleccionadas])
                num_pts = len(marcadores)
                llave_dinamica = f"visor_mapa_{clave_sel_norm}_{hash_capas}_{num_pts}"

                st_folium(
                    m, 
                    use_container_width=True, 
                    height=550, 
                    returned_objects=[], 
                    key=llave_dinamica
                )

            except Exception as e:
                import traceback
                st.error("🚨 ERROR: El mapa colapsó.")
                with st.expander("Ver Traceback de Error", expanded=True): st.code(traceback.format_exc(), language="python")

        with tab_geo:
            if file_id_geo:
                st.markdown(f'<div style="text-align: center; margin-top: 10px;"><img src="https://drive.google.com/uc?export=view&id={file_id_geo}" style="max-width:100%; border-radius:8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);" /></div>', unsafe_allow_html=True)
            else:
                st.info("📂 Mapa geológico estático próximamente disponible para este acuífero.")

    renderizar_modulo_mapa(datos_ac, nombre_acuifero, capas_seleccionadas, diccionario_capas, file_id_geo, st.session_state.get("lista_marcadores", []))

    st.divider()

    # =======================================================
    # 🗂️ PESTAÑAS DE DATOS
    # =======================================================
    @st.fragment
    def renderizar_pestanas_datos(clave_acuifero, datos_ac, dato_zona_disp, df_resumen, vol_total, parrafo_vol_ia, conteo_usos, total_aprov, parrafo_aprov_ia, parrafo_dma_ia):
        st.header("📊 Información Técnica y Documental")
    
        tab_legal, tab_entorno, tab_usos, tab_dma = st.tabs([
            "🏛️ Ficha Administrativa", "🌍 Entorno Socioambiental", "💧 Usos y Extracciones", "⚖️ Balance (DMA)"
        ])
    
        with tab_legal:
            with st.expander("📍 Límites Oficiales del Acuífero", expanded=True):
                nombres_limites, fechas_limites = datos_ac.get('excel_LIM_NOM'), datos_ac.get('excel_LIM_FECHA')
                if pd.notna(nombres_limites) and str(nombres_limites).strip() != "":
                    mostrar_pares_en_parrafo("Acuerdo de Límites", nombres_limites, fechas_limites, prefijo_extra="DOF: ", es_fecha=True)
                else: st.info("Información de límites en proceso de validación o no disponible.")
                if st.button(" Ver Catálogo de Vértices de la Poligonal", type="secondary", key="btn_vert"): modal_vertices(clave_acuifero)
    
            with st.expander("⚖️ Decretos de Veda", expanded=True):
                nombres_vedas, fechas_vedas = datos_ac.get('vedas_NOM_OFI'), datos_ac.get('vedas_FECHA_DOF')
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
                        return f"{partes[0].upper()} {partes[1].title()}" if len(partes) > 1 else texto_limpio.upper()
                    return texto_limpio.title()
    
                mostrar_dato("Organismo de Cuenca (Región Adm.)", formato_nombres(datos_ac.get('REGION_ADM'), proteger_primera=True))
                unidad_adm = str(datos_ac.get('UNIDAD_ADM')).strip()
                mostrar_dato("Dirección Local", formato_nombres(unidad_adm, proteger_primera=True) if unidad_adm.upper().startswith("DL") else None)
                mostrar_desde_fraccion_en_linea("Consejo de Cuenca", clave_acuifero, "consejos_cuenca", "NOMCONSEJC", "FECHA_INST", "Instalado: ", True)
                mostrar_pares_en_parrafo("COTAS", datos_ac.get('cotas_nom_cotas'), datos_ac.get('cotas_fecha_inst'), "Fecha: ", True)
                st.write(f"**Zona de Disponibilidad:** {dato_zona_disp}")
    
        with tab_entorno:
            with st.expander("📍 División Municipal", expanded=True):
                mostrar_municipios_agrupados_y_condicion(clave_acuifero, datos_ac.get('municipios_TOTAL'), datos_ac.get('municipios_PARCIAL'))
            with st.expander("🌿 Medio Ambiente", expanded=True):
                mostrar_desde_fraccion_vertical("Áreas Naturales Protegidas Federales", clave_acuifero, "anp_federal", "NOMBRE", "PRIM_DEC", "DOF: ")
                mostrar_desde_fraccion_vertical("Áreas Naturales Protegidas Estatales", clave_acuifero, "anp_estatal", "NOMBRE", "ULT_DEC", "Últ. Dec: ")
                mostrar_desde_fraccion_vertical("Sitios RAMSAR", clave_acuifero, "ramsar", "RAMSAR", "FECHA", "Fecha: ")
            with st.expander("🌾 Uso Agrícola", expanded=True):
                mostrar_pares_en_parrafo("Distritos de Riego", datos_ac.get('distritos_riego_FIRST_NOMB'), datos_ac.get('distritos_riego_DISTID'))
                mostrar_dato("Unidades de Riego", datos_ac.get('unidades_riego_rha'))
    
        with tab_usos:
            st.subheader("📊 Resumen de Bombeo (REPDA)")
            if not df_resumen.empty:
                st.dataframe(df_resumen.style.format({"Volumen (hm³/año)": "{:.1f}", "Porcentaje (%)": "{:.1f}%"}), use_container_width=True, hide_index=True)
                st.metric("Volumen Total Concesionado (hm³/año)", f"{vol_total:.1f}")
                st.info(parrafo_vol_ia)
            else: st.warning(f"No se encontró la clave {clave_acuifero} en el archivo REPDA.")
            st.divider()
            st.subheader("💧 Conteo de Aprovechamientos")
            if not conteo_usos.empty:
                st.dataframe(conteo_usos.style.format({"Porcentaje (%)": "{:.1f}%"}), use_container_width=True, hide_index=True)
                st.metric("Total de Aprovechamientos Registrados", f"{total_aprov:,}")
                st.info(parrafo_aprov_ia)
            else: st.warning("No se encontraron registros de aprovechamientos.")
    
        with tab_dma:
            st.subheader("Balance de Aguas Subterráneas y Cálculo de la DMA")
            st.caption("Valores de flujo y almacenamiento extraídos directamente de los Parquet")
    
            df_bal_ent_global = get_df_bal_ent()
            df_bal_sal_global = get_df_bal_sal()
            df_bal_alm_data = get_df_bal_alm()
            df_veas_global = get_df_veas()
    
            bal_ent = df_bal_ent_global[df_bal_ent_global['CLV_ACUI'] == clave_acuifero] if df_bal_ent_global is not None else pd.DataFrame()
            bal_sal = df_bal_sal_global[df_bal_sal_global['CLV_ACUI'] == clave_acuifero] if df_bal_sal_global is not None else pd.DataFrame()
            bal_alm = df_bal_alm_data[df_bal_alm_data['CLV_ACUI'] == clave_acuifero] if df_bal_alm_data is not None else pd.DataFrame()
    
            st.markdown("#### 📥 Entradas")
            v_r_total = buscar_valor(bal_ent, "R", es_total=True)
            st.dataframe(pd.DataFrame([
                {"Concepto": "Recarga vertical (Rv)", "Volumen (hm³)": buscar_valor(bal_ent, "Rv")},
                {"Concepto": "Retornos por riego (Rr)", "Volumen (hm³)": buscar_valor(bal_ent, "Rr")},
                {"Concepto": "Entrada horizontal subterránea (Eh)", "Volumen (hm³)": buscar_valor(bal_ent, "Eh")},
                {"Concepto": "Entrada horizontal salobre (Ehs)", "Volumen (hm³)": buscar_valor(bal_ent, "Ehs")},
                {"Concepto": "Recarga inducida (Ri)", "Volumen (hm³)": buscar_valor(bal_ent, "Ri")}
            ]).style.format({"Volumen (hm³)": "{:,.1f}"}), use_container_width=True, hide_index=True)
            if st.button("🔎 Ver tabla de cálculo: Entrada horizontal subterránea (Eh)", type="secondary", key="btn_eh"): modal_tablas_calculo(clave_acuifero, "Eh")
    
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
                if st.button("🔎 Ver tabla de cálculo: Salida horizontal subterránea (Sh)", type="secondary", key="btn_sh"): modal_tablas_calculo(clave_acuifero, "Sh")
            with col_s2:
                if st.button("🔎 Ver tabla de cálculo: Evapotranspiración Real (ETR)", type="secondary", key="btn_etr"): modal_tablas_calculo(clave_acuifero, "ETR")
    
            st.markdown("#### 🧊 Cambio de almacenamiento ΔV(S)")
            st.dataframe(pd.DataFrame([{"Concepto": "ΔV(S)", "Volumen (hm³)": buscar_valor(bal_alm, "ΔV") or buscar_valor(bal_alm, "V(S)")}]).style.format({"Volumen (hm³)": "{:,.1f}"}), use_container_width=True, hide_index=True)
            if st.button("🔎 Ver tabla de cálculo: Cambio de Almacenamiento ΔV(S)", type="secondary", key="btn_dvs"): modal_tablas_calculo(clave_acuifero, "ΔV(S)")
    
            match_dnc = bal_sal[bal_sal['CONCEPTO'].astype(str).str.contains("TOTAL", case=False, na=False)]
            if not match_dnc.empty:
                val_crudo = match_dnc.iloc[-1]['DNC_hm3']
                v_dnc_total = float(val_crudo) if pd.notna(val_crudo) and str(val_crudo).strip().lower() not in ['none', '', 'nan'] else 0.0
            else:
                v_dnc_total = pd.to_numeric(bal_sal['DNC_hm3'].astype(str).replace(['None', 'none', '', 'NaN'], '0'), errors='coerce').fillna(0).sum()
    
            v_veas = float(df_veas_global[df_veas_global['CLAVE'] == clave_acuifero].iloc[0]['VEAS_hm3']) if df_veas_global is not None and not df_veas_global[df_veas_global['CLAVE'] == clave_acuifero].empty else 0.0
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

    renderizar_pestanas_datos(
        clave_acuifero=clave_acuifero,
        datos_ac=datos_ac,
        dato_zona_disp=dato_zona_disp,
        df_resumen=df_resumen,
        vol_total=vol_total,
        parrafo_vol_ia=parrafo_vol_ia,
        conteo_usos=conteo_usos,
        total_aprov=total_aprov,
        parrafo_aprov_ia=parrafo_aprov_ia,
        parrafo_dma_ia=parrafo_dma_ia
    )
    

    def renderizar_boton_ia_flotante(c_ac, n_ac, edo_sel, d_ac, p_vol, p_aprov, p_dma, df_res, c_usos, d_zona):
        if st.button("✨", type="primary", key=f"btn_ia_{c_ac}"):
            contexto_global_str = construir_contexto_completo(
                clave_ac=c_ac, nombre_ac=n_ac, estado=edo_sel,
                datos_ac=d_ac, parrafo_vol=p_vol, parrafo_aprov=p_aprov,
                parrafo_dma=p_dma, df_resumen=df_res, conteo_usos=c_usos,
                df_bal_ent=get_df_bal_ent(), df_bal_sal=get_df_bal_sal(), df_bal_alm=get_df_bal_alm(),
                df_verts=get_df_vertices(), df_flujo_ent=get_df_flujo_ent(), df_flujo_sal=get_df_flujo_sal(),
                df_etr=get_df_etr(), df_alm=get_df_almacenamiento(), dato_zona_disp=d_zona
            )
            modal_chat_local(c_ac, n_ac, contexto_global_str)

    renderizar_boton_ia_flotante(
        clave_acuifero, nombre_acuifero, estado_seleccionado, datos_ac,
        parrafo_vol_ia, parrafo_aprov_ia, parrafo_dma_ia, df_resumen, conteo_usos, dato_zona_disp
    )

else:
    st.info("👈 Selecciona un Acuífero en el panel lateral para ver su información.")

# =======================================================
# ⚙️ INYECCIÓN JAVASCRIPT (BOTÓN FLOTANTE CÍRCULO PERFECTO)
# =======================================================
components.html(
    """
    <script>
    const doc = window.parent.document;
    function aplicarEstilosCirculares() {
        const botones = doc.querySelectorAll('button');
        let btnIA = null;
        botones.forEach(b => { if(b.innerText.includes('✨')) { btnIA = b; } });
        if(!btnIA) return;
        btnIA.removeAttribute('title');
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
        
        const hijos = btnIA.querySelectorAll('*');
        hijos.forEach(hijo => {
            hijo.style.setProperty('background-color', 'transparent', 'important');
            hijo.style.setProperty('padding', '0', 'important');
            hijo.style.setProperty('margin', '0', 'important');
            hijo.style.setProperty('min-width', '0', 'important');
        });
        
        const p = btnIA.querySelector('p');
        if(p) {
            p.style.setProperty('font-size', '28px', 'important');
            p.style.setProperty('line-height', '1', 'important');
        }
        btnIA.onmouseover = function() { this.style.setProperty('transform', 'scale(1.15)', 'important'); this.style.setProperty('background-color', '#691C32', 'important'); };
        btnIA.onmouseout = function() { this.style.setProperty('transform', 'scale(1)', 'important'); this.style.setProperty('background-color', '#9F2241', 'important'); };

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
    const observer = new MutationObserver(() => { aplicarEstilosCirculares(); });
    observer.observe(doc.body, { childList: true, subtree: true });
    setTimeout(aplicarEstilosCirculares, 50);
    </script>
    """, height=0, width=0)
