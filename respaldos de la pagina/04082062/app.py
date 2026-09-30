# -*- coding: utf-8 -*-
"""
Created on Thu Jul 30 11:08:45 2026

@author: dchable
"""

import streamlit as st
from pathlib import Path

# ==========================================
# CONFIGURACIÓN MAESTRA DE LA APP
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

# ==========================================
# 🦅 LOGO INSTITUCIONAL OMNIPRESENTE
# ==========================================
DIRECTORIO_RAIZ = Path(__file__).resolve().parent
logo_institucional = DIRECTORIO_RAIZ / "assets" / "image_177adb.png"

with st.sidebar:
    if logo_institucional.exists(): 
        st.image(str(logo_institucional), use_column_width=True)
    st.markdown("---") # Una rayita elegante para separar el logo del menú

# ==========================================
# ENRUTAMIENTO NATIVO (NIVEL ENTERPRISE)
# ==========================================
# 1. Definimos las páginas apuntando a los NOMBRES EXACTOS de los archivos
geovisor = st.Page("pages/3_🗺️_Visor_y_Descargas.py", title="1. SIG y Documentos", icon="🗺️")
calculadora = st.Page("pages/1_🧮_Balance_de_Aguas_Subtarraneas.py", title="2. Generador de BAS", icon="🧮")
reportes = st.Page("pages/2_📊_Reporte_Anual.py", title="3. Reporte de BAS", icon="📊")

# 2. Agrupamos el menú de navegación
paginas = {
    "Herramientas Hidrogeológicas": [geovisor, calculadora],
    "Reportes Oficiales": [reportes]
}

# 3. Encendemos el motor de navegación de Streamlit
rutas = st.navigation(paginas)
rutas.run()