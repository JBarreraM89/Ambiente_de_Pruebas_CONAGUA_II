# -*- coding: utf-8 -*-
"""
Sistema Integral CONAGUA - Módulo de Navegación y Estilos Globales
"""

from pathlib import Path
import base64
import streamlit as st

# Importamos los estilos centralizados de la Fase 1
from utils.styles import inyectar_css_navegacion

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
ARCHIVADOR_VISITAS = DIRECTORIO_RAIZ / "assets" / "contador_visitas.txt"

# ==========================================
# 2. INICIALIZACIÓN DEL ESTADO GLOBAL (Sincronización)
# ==========================================
# Estas variables serán la única fuente de verdad para todas las páginas
if "clave_global" not in st.session_state:
    st.session_state["clave_global"] = None
if "nombre_global" not in st.session_state:
    st.session_state["nombre_global"] = None
if "area_total_global" not in st.session_state:
    st.session_state["area_total_global"] = None

# ==========================================
# 3. FUNCIONES CON CACHÉ (OPTIMIZACIÓN I/O)
# ==========================================
@st.cache_data(show_spinner=False)
def obtener_logo_b64(path_imagen: Path) -> str:
    """Lee y codifica la imagen del logotipo en base64 una sola vez en memoria."""
    if path_imagen.exists():
        with open(path_imagen, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode()
    return ""

imagen_b64 = obtener_logo_b64(LOGO_PATH)

# Inyectamos el CSS limpio desde nuestro módulo de utilidades
inyectar_css_navegacion(imagen_b64)

# ==========================================
# 4. SISTEMA DE CONTADOR DE VISITAS LOCAL
# ==========================================
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
# 6. ENRUTAMIENTO NATIVO (ST.NAVIGATION)
# ==========================================
geovisor = st.Page("pages/3_🗺️_Visor_y_Descargas.py", title="SIG", icon="📍")
calculadora = st.Page("pages/1_🧮_Balance_de_Aguas_Subtarraneas.py", title="Generador BAS", icon="⚙️")
reportes = st.Page("pages/2_📊_Reporte_Anual.py", title="Reportes", icon="📊")
analista_virtual = st.Page("pages/4_🤖_Analista_Virtual.py", title="Analista Virtual", icon="🤖")

paginas = {
    "Herramientas Base": [geovisor, calculadora],
    "Reportes y Análisis": [reportes],
    "Reportes y Análisis": [reportes, analista_virtual]
}

rutas = st.navigation(paginas)
rutas.run()