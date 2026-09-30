# -*- coding: utf-8 -*-
"""
Sistema Integral CONAGUA - Módulo de Navegación y Estilos Globales
"""

from pathlib import Path
import base64
import streamlit as st

# ==========================================
# 1. CONFIGURACIÓN MAESTRA DE LA APP
# ==========================================
st.set_page_config(
    page_title="Sistema Integral CONAGUA",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "Sistema Interno de CONAGUA"
    }
)

DIRECTORIO_RAIZ = Path(__file__).resolve().parent
LOGO_PATH = DIRECTORIO_RAIZ / "assets" / "image_177adb.png"

# ==========================================
# 2. FUNCIONES CON CACHÉ (OPTIMIZACIÓN I/O)
# ==========================================
@st.cache_data(show_spinner=False)
def obtener_logo_b64(path_imagen: Path) -> str:
    """Lee y codifica la imagen del logotipo en base64 una sola vez en memoria."""
    if path_imagen.exists():
        with open(path_imagen, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    return ""

imagen_b64 = obtener_logo_b64(LOGO_PATH)

# ==========================================
# 3. INYECCIÓN CSS ENTERPRISE
# ==========================================
logo_css_rule = f'background-image: url("data:image/png;base64,{imagen_b64}");' if imagen_b64 else ''

css_enterprise = f"""
<style>
    /* 1. ESTRUCTURA Y FONDO (Contraste ligero respecto al lienzo principal) */
    [data-testid="stSidebar"] {{
        background-color: #F8FAFC !important;
        border-right: 1px solid #E2E8F0 !important;
    }}
    
    [data-testid="stSidebarNavItems"] a:hover {{ 
        background-color: #FFFFFF !important; 
        color: #0F172A !important; 
    }}

    [data-testid="stSidebar"] ::-webkit-scrollbar {{ width: 5px; height: 5px; }}
    [data-testid="stSidebar"] ::-webkit-scrollbar-thumb {{ background: transparent; border-radius: 10px; }}
    [data-testid="stSidebar"]:hover ::-webkit-scrollbar-thumb {{ background: #CBD5E1; }}

    /* 2. HEADER Y LOGOTIPO */
    [data-testid="stSidebarNav"]::before {{
        content: ""; display: block; width: 70%; height: 70px;
        {logo_css_rule}
        background-size: contain; background-position: center; background-repeat: no-repeat;
        margin: 20px auto 10px auto; 
    }}
    [data-testid="stSidebarNavGroup"]:first-of-type {{
        border-top: 1px solid rgba(221, 201, 163, 0.4); 
        margin-top: 25px !important; padding-top: 15px !important;
    }}
    
    /* 3. TÍTULOS DE NAVEGACIÓN */
    [data-testid="stSidebarNavGroup"] > div:first-child,
    [data-testid="stSidebarNav"] span[data-testid="stSidebarNavGroupLabel"] {{
        color: #64748B !important; font-size: 10px !important; text-transform: uppercase !important;
        letter-spacing: 1.5px !important; font-weight: 700 !important; padding-left: 18px !important; margin-bottom: 5px !important;
    }}

    /* 4. BOTONES DEL MENÚ */
    [data-testid="stSidebarNavItems"] a {{
        border-radius: 6px !important; margin: 2px 16px !important; padding: 8px 12px !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important; color: #334155 !important; 
    }}
    [data-testid="stSidebarNavItems"] a span {{ font-size: 13.5px !important; font-weight: 500 !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
    [data-testid="stSidebarNavItems"] a:hover {{ background-color: #FFFFFF !important; color: #0F172A !important; }}
    [data-testid="stSidebarNavItems"] a[aria-current="page"] {{ background-color: #FDF4F6 !important; color: #691C32 !important; }}
    [data-testid="stSidebarNavItems"] a[aria-current="page"] span {{ color: #691C32 !important; font-weight: 600 !important; }}
    [data-testid="stSidebarNavItems"] a[aria-current="page"]::before {{
        content: ""; position: absolute; left: 0; top: 20%; bottom: 20%; width: 4px; background-color: #691C32; border-radius: 0px 4px 4px 0px;
    }}
    [data-testid="stSidebarNav"] svg {{ opacity: 0.7 !important; margin-right: 5px; }}

    [data-testid="stSidebarUserContent"] {{ padding-top: 10px !important; }}
    
    [data-testid="stSidebarUserContent"] label p {{
        font-size: 11px !important; font-weight: 700 !important; color: #475569 !important;
        text-transform: uppercase !important; letter-spacing: 0.5px !important; margin-bottom: 4px !important;
    }}

    [data-testid="stSidebarUserContent"] h2, [data-testid="stSidebarUserContent"] h3 {{
        color: #1E293B !important; font-size: 15px !important; margin-top: 15px !important; margin-bottom: 10px !important;
    }}

    /* CAJA DEL SELECTBOX: Fondo blanco puro para hacer contraste con el sidebar gris */
    [data-testid="stSidebarUserContent"] [data-baseweb="select"] > div {{
        height: auto !important; min-height: 36px !important;
        border-radius: 6px !important; border: 1px solid #CBD5E1 !important;
        background-color: #FFFFFF !important; /* <--- Blanco puro */
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05) !important; transition: all 0.2s ease !important;
        padding-top: 2px !important; padding-bottom: 2px !important;
    }}
    
    /* Hover en el selectbox: Borde dorado institucional y sombra suave */
    [data-testid="stSidebarUserContent"] [data-baseweb="select"] > div:hover {{ 
        border-color: #DDC9A3 !important; 
        background-color: #FFFFFF !important; 
    }}
    
    [data-testid="stSidebarUserContent"] [data-baseweb="select"] span {{ 
        font-size: 11.5px !important; 
        color: #0F172A !important; 
        white-space: normal !important; 
        line-height: 1.3 !important;
    }}
    
    ul[role="listbox"] li {{
        font-size: 11px !important;
        padding-top: 6px !important;
        padding-bottom: 6px !important;
        white-space: normal !important; 
        border-bottom: 1px solid #f1f5f9; 
    }}

    /* 6. ORDENAMIENTO DE CONTENEDORES (Mandar footer al fondo) */
    [data-testid="stSidebarUserContent"] {{
        display: flex;
        flex-direction: column;
        min-height: 80vh;
    }}
    
    div.element-container:has(.global-sidebar-footer) {{
        order: 9999 !important;
        margin-top: auto !important; 
    }}
</style>
"""
st.markdown(css_enterprise, unsafe_allow_html=True)

# ==========================================
# 4. SISTEMA DE CONTADOR DE VISITAS LOCAL
# ==========================================
ARCHIVADOR_VISITAS = DIRECTORIO_RAIZ / "assets" / "contador_visitas.txt"

def obtener_y_registrar_visita() -> int:
    """
    Lee el archivo de visitas local e incrementa el contador solo una vez
    por cada nueva sesión de usuario en Streamlit.
    """
    # 1. Crear el directorio assets o archivo si no existen
    ARCHIVADOR_VISITAS.parent.mkdir(parents=True, exist_ok=True)
    if not ARCHIVADOR_VISITAS.exists():
        ARCHIVADOR_VISITAS.write_text("0", encoding="utf-8")

    # 2. Leer conteo actual
    try:
        conteo_actual = int(ARCHIVADOR_VISITAS.read_text(encoding="utf-8").strip())
    except ValueError:
        conteo_actual = 0

    # 3. Incrementar solo si es la primera ejecución de la sesión del usuario
    if "visita_registrada" not in st.session_state:
        conteo_actual += 1
        try:
            ARCHIVADOR_VISITAS.write_text(str(conteo_actual), encoding="utf-8")
        except Exception:
            pass  # Previene errores de escritura concurrentes
        st.session_state["visita_registrada"] = True

    return conteo_actual

# Registrar / Obtener número de visitas
total_visitas = obtener_y_registrar_visita()

# ==========================================
# 5. PIE DE PÁGINA GLOBAL (BARRA LATERAL)
# ==========================================
with st.sidebar:
    footer_html = f"""
    <div class="global-sidebar-footer">
        <div style="text-align: center; margin-top: 25px; margin-bottom: 15px;">
            <p style="font-size: 11px; color: #691C32; font-weight: 700; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.8px;">
                📊 Visitas Totales
            </p>
            <div style="display: inline-flex; align-items: center; border-radius: 4px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 1px 3px rgba(0,0,0,0.12);">
                <span style="background-color: #555555; color: #FFFFFF; font-size: 10px; font-weight: 700; padding: 4px 8px; text-transform: uppercase; letter-spacing: 0.5px;">VISITAS</span>
                <span style="background-color: #9F2241; color: #FFFFFF; font-size: 11px; font-weight: 700; padding: 4px 10px;">{total_visitas:,}</span>
            </div>
        </div>
        <div style="background-color: #FDF4F6; padding: 12px; border-radius: 6px; border: 1px solid #FBCED8; text-align: justify; margin-top: 10px; margin-bottom: 5px;">
            <p style="font-size: 10px; color: #88102B; font-weight: 600; margin: 0; line-height: 1.4;">
            ⚠️ <b>AVISO IMPORTANTE:</b><br>Plataforma para uso interno de la Gerencia de Aguas Subterráneas. Su información y mapas espaciales carecen de validez legal.
            </p>
        </div>
    </div>
    """
    st.markdown(footer_html, unsafe_allow_html=True)

# ==========================================
# . ENRUTAMIENTO NATIVO (ST.NAVIGATION)
# ==========================================
geovisor = st.Page("pages/3_🗺️_Visor_y_Descargas.py", title="SIG", icon="📍")
calculadora = st.Page("pages/1_🧮_Balance_de_Aguas_Subtarraneas.py", title="Generador BAS", icon="⚙️")
reportes = st.Page("pages/2_📊_Reporte_Anual.py", title="Reportes", icon="📊")

paginas = {
    "Herramientas Base": [geovisor, calculadora],
    "Reportes y Análisis": [reportes]
}

rutas = st.navigation(paginas)
rutas.run()