# -*- coding: utf-8 -*-
"""
Sistema Integral CONAGUA - Módulo de Navegación y Estilos Globales

Cambios respecto a la versión anterior:
- La limpieza de DataFrames huérfanos en session_state (df_*, geojson_*) ahora se hace
  SOLO cuando el usuario cambia de página. Antes corría en cada interacción (app.py se
  ejecuta en cada rerun con st.navigation) y borraba tablas editadas a mitad de trabajo.
- El logo se reduce una sola vez (Pillow) antes de incrustarlo en el CSS: antes se
  reenviaba un PNG de ~200 KB (≈267 KB en base64) en cada interacción.
- El contador de visitas se lee una sola vez por sesión y se escribe de forma atómica y
  con candado. Nota: en Streamlit Cloud el disco es efímero, así que el conteo se
  reinicia con cada reinicio o redeploy; para un conteo permanente usar un almacén externo.
- Corregida la errata "Estádistico".
"""

import base64
import gc
import io
import logging
import os
import threading
from pathlib import Path

import streamlit as st
from PIL import Image

# Importamos los estilos centralizados
from utils.styles import inyectar_css_navegacion

logger = logging.getLogger(__name__)

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
# 2. FUNCIONES CON CACHÉ (OPTIMIZACIÓN I/O)
# ==========================================
@st.cache_data(show_spinner=False)
def obtener_logo_b64(path_imagen: Path, ancho_max: int = 480, alto_max: int = 160) -> str:
    """Logo en base64, reducido a un tamaño suficiente para el panel lateral (~70 px de alto).

    Se calcula una sola vez y queda en caché. Si Pillow no puede procesar la imagen,
    se usa el archivo original.
    """
    if not path_imagen.exists():
        return ""
    try:
        with Image.open(path_imagen) as img:
            img.thumbnail((ancho_max, alto_max))  # conserva la proporción
            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)
        return base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        logger.exception("No se pudo optimizar el logo; se usa el original")
        return base64.b64encode(path_imagen.read_bytes()).decode()


@st.cache_resource(show_spinner=False)
def _candado_visitas() -> threading.Lock:
    """Un único candado para todas las sesiones (app.py se reejecuta en cada rerun)."""
    return threading.Lock()


def registrar_visita() -> int:
    """Incrementa el contador de visitas y devuelve el total (una llamada por sesión nueva)."""
    with _candado_visitas():
        ARCHIVADOR_VISITAS.parent.mkdir(parents=True, exist_ok=True)
        try:
            conteo = int(ARCHIVADOR_VISITAS.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            conteo = 0
        conteo += 1
        try:
            temporal = ARCHIVADOR_VISITAS.with_suffix(".tmp")
            temporal.write_text(str(conteo), encoding="utf-8")
            os.replace(temporal, ARCHIVADOR_VISITAS)  # escritura atómica
        except OSError:
            logger.warning("No se pudo guardar el contador de visitas", exc_info=True)
        return conteo


# ==========================================
# 3. ESTILOS Y CONTADOR (UNA VEZ POR SESIÓN)
# ==========================================
inyectar_css_navegacion(obtener_logo_b64(LOGO_PATH))

if "total_visitas" not in st.session_state:
    st.session_state["total_visitas"] = registrar_visita()
total_visitas = st.session_state["total_visitas"]

# ==========================================
# 4. PIE DE PÁGINA GLOBAL (BARRA LATERAL)
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
# 5. ENRUTAMIENTO NATIVO (ST.NAVIGATION)
# ==========================================
geovisor = st.Page("pages/3_🗺️_Visor_y_Descargas.py", title="SIG", icon="📍")
calculadora = st.Page("pages/1_🧮_Balance_de_Aguas_Subtarraneas.py", title="Generador BAS", icon="⚙️")
reportes = st.Page("pages/2_📊_Reporte_Anual.py", title="Reportes", icon="📊")
analista_virtual = st.Page("pages/4_🤖_Analista_Virtual.py", title="Analista Estadístico", icon="🤖")
red_piezometrica = st.Page("pages/6_📉_Red_Piezometrica.py", title="Red Piezométrica", icon="📉")
vulnerabilidad = st.Page("pages/5_🗺️_Geovisor_Vulnerabilidad.py", title="Vulnerabilidad", icon="🌍")
modelo_conceptual = st.Page("pages/7_🧊_Modelo_Conceptual.py", title="Modelo Conceptual", icon="🧊")

paginas = {
    "Herramientas Base": [geovisor, calculadora],
    "Reportes y Análisis": [reportes, analista_virtual, red_piezometrica],
    "Vulnerabilidad": [vulnerabilidad],
    "Modelo Conceptual": [modelo_conceptual]
}

pagina_actual = st.navigation(paginas)

# ==========================================
# 6. WATCHDOG DE MEMORIA (SOLO AL CAMBIAR DE PÁGINA)
# ==========================================
# Libera DataFrames/GeoJSON huérfanos de la página anterior. app.py se ejecuta en cada
# interacción, por eso se compara contra la última página visitada.
_id_pagina = getattr(pagina_actual, "url_path", None) or getattr(pagina_actual, "title", "")
if st.session_state.get("_pagina_previa") != _id_pagina:
    for _k in [k for k in st.session_state.keys() if k.startswith(("df_", "geojson_"))]:
        del st.session_state[_k]
    gc.collect()
    st.session_state["_pagina_previa"] = _id_pagina

pagina_actual.run()
