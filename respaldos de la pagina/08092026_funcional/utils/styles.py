# -*- coding: utf-8 -*-
import streamlit as st

def inyectar_css_navegacion(imagen_b64=""):
    """Inyecta los estilos de la barra lateral (Sidebar) en app.py"""
    logo_css_rule = f'background-image: url("data:image/png;base64,{imagen_b64}");' if imagen_b64 else ''
    
    css_enterprise = f"""
    <style>
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
        [data-testid="stSidebarNavGroup"] > div:first-child,
        [data-testid="stSidebarNav"] span[data-testid="stSidebarNavGroupLabel"] {{
            color: #64748B !important; font-size: 10px !important; text-transform: uppercase !important;
            letter-spacing: 1.5px !important; font-weight: 700 !important; padding-left: 18px !important; margin-bottom: 5px !important;
        }}
        [data-testid="stSidebarNavItems"] a {{
            border-radius: 6px !important; margin: 2px 16px !important; padding: 8px 12px !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important; color: #334155 !important; 
        }}
        [data-testid="stSidebarNavItems"] a span {{ font-size: 15.5px !important; font-weight: 500 !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }}
        [data-testid="stSidebarNavItems"] a:hover {{ background-color: #FFFFFF !important; color: #0F172A !important; }}
        [data-testid="stSidebarNavItems"] a[aria-current="page"] {{ background-color: #FDF4F6 !important; color: #691C32 !important; }}
        [data-testid="stSidebarNavItems"] a[aria-current="page"] span {{ color: #691C32 !important; font-weight: 600 !important; }}
        [data-testid="stSidebarNavItems"] a[aria-current="page"]::before {{
            display: none;
        }}
        [data-testid="stSidebarNav"] svg {{ opacity: 0.7 !important; margin-right: 5px; }}
        [data-testid="stSidebarUserContent"] {{ padding-top: 10px !important; }}
        [data-testid="stSidebarUserContent"] label p {{
            font-size: 13px !important; font-weight: 700 !important; color: #475569 !important;
            text-transform: uppercase !important; letter-spacing: 0.5px !important; margin-bottom: 4px !important;
        }}
        [data-testid="stSidebarUserContent"] h2, [data-testid="stSidebarUserContent"] h3 {{
            color: #1E293B !important; font-size: 15px !important; margin-top: 15px !important; margin-bottom: 10px !important;
        }}
        [data-testid="stSidebarUserContent"] [data-baseweb="select"] > div {{
            height: auto !important; min-height: 36px !important;
            border-radius: 6px !important; border: 1px solid #CBD5E1 !important;
            background-color: #FFFFFF !important;
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05) !important; transition: all 0.2s ease !important;
            padding-top: 2px !important; padding-bottom: 2px !important;
        }}
        [data-testid="stSidebarUserContent"] [data-baseweb="select"] > div:hover {{ 
            border-color: #DDC9A3 !important; background-color: #FFFFFF !important; 
        }}
        [data-testid="stSidebarUserContent"] [data-baseweb="select"] span {{ 
            font-size: 11.5px !important; color: #0F172A !important; white-space: normal !important; line-height: 1.3 !important;
        }}
        ul[role="listbox"] li {{
            font-size: 11px !important; padding-top: 6px !important; padding-bottom: 6px !important;
            white-space: normal !important; border-bottom: 1px solid #f1f5f9; 
        }}
        [data-testid="stSidebarUserContent"] {{ display: flex; flex-direction: column; min-height: 80vh; }}
        div.element-container:has(.global-sidebar-footer) {{ order: 9999 !important; margin-top: auto !important; }}
    </style>
    """
    st.markdown(css_enterprise, unsafe_allow_html=True)

def inyectar_css_oficial():
    """Inyecta la estética avanzada del Visor en todas las páginas internas"""
    css_oficial = """
    <style>
        /* 1. Globales y Títulos (CON RESPIRACIÓN REFORZADA) */
        h1, h2, h3, h4, h5, h6 { 
            color: #691C32 !important; 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important; 
            line-height: 1.4 !important;       
            margin-top: 0.0rem !important;     
            margin-bottom: 1.2rem !important;  
        }
        
        .block-container, [data-testid="stMainBlockContainer"] { 
            padding-top: 5rem !important; 
            padding-bottom: 2rem !important; 
            max-width: 98vw !important; width: 100% !important;
            padding-left: 2rem !important; padding-right: 2rem !important;
        }
        
        .stDataFrame th { background-color: #bdd7ee !important; color: #244062 !important; font-weight: bold !important; }
        .stAppDeployButton {display:none;}
        
        /* 2. ENCABEZADO NATIVO E INSTITUCIONAL FLOTANTE */
        [data-testid="stHeader"] {
            background-color: rgba(255, 255, 255, 0.95) !important;
            border-bottom: 3px solid #DDC9A3 !important;
            box-shadow: 0px 4px 10px rgba(0,0,0,0.05) !important;
            height: 4.5rem !important;
            z-index: 99999 !important; 
            display: block !important; 
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

        @media (max-width: 991px) { 
            [data-testid="stHeader"]::after { font-size: 16px; left: 60px; transform: translate(0, -50%); }
        }
        
        /* 3. Estilos de Pestañas Interactivas */
        div[data-testid="stTabs"] { width: 100% !important; }
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
        
        /* 4. Botones Secundarios y Terciarios Tipo Link */
        button[kind="secondary"], button[kind="tertiary"] {
            color: #2980b9 !important; font-weight: 600 !important; padding: 0 !important; 
            margin-top: 5px !important; margin-bottom: 15px !important; 
            background-color: transparent !important; border: none !important; box-shadow: none !important;
        } 
        button[kind="secondary"]:hover, button[kind="tertiary"]:hover {
            color: #9F2241 !important; text-decoration: underline !important; 
            background-color: transparent !important; border: none !important;
        }
        
        /* 5. Reglas blindadas exclusivas de la tarjeta BAS */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(#alerta-card-doc) div[data-testid="stButton"] > button,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(#alerta-card-doc) div[data-testid="stDownloadButton"] > button {
            min-height: 32px !important; height: 32px !important; padding: 2px 10px !important; border-radius: 6px !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(#alerta-card-doc) div[data-testid="stButton"] button *,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(#alerta-card-doc) div[data-testid="stDownloadButton"] button * {
            font-size: 14px !important; line-height: 1 !important; font-weight: 600 !important; white-space: nowrap !important;
        }
        div[data-testid="stElementContainer"]:has(#alerta-card-doc) { display: none !important; }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(#alerta-card-doc) [data-testid="stVerticalBlock"] { gap: 0rem !important; }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(#alerta-card-doc) [data-testid="stHorizontalBlock"] { align-items: center !important; }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(#alerta-card-doc) { padding: 14px 10px !important; }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(#alerta-card-doc) [data-testid="stColumn"] { padding: 0px !important; }

        /* 6. Estilos para los Expander (Pestañas colapsables / Acordeones) */
        [data-testid="stExpander"] {
            margin-bottom: 15px !important; 
        }

        [data-testid="stExpander"] summary {
            background-color: #f1f3f6 !important; 
            border: 1px solid #dcdde1 !important;
            border-radius: 6px !important;
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
            transition: all 0.3s ease !important;
        }
        
        [data-testid="stExpander"] summary:hover {
            background-color: #DDC9A3 !important; 
            border-color: #DDC9A3 !important;
        }
        
        [data-testid="stExpander"] summary p {
            color: #691C32 !important; 
            font-weight: 700 !important;
            font-size: 15px !important;
        }
        
        [data-testid="stExpander"] summary svg {
            fill: #691C32 !important; 
            color: #691C32 !important;
        }
        
        /* 7. Espaciado interno de los Expander (Controles de respiración) */
        [data-testid="stExpanderDetails"] {
            padding-top: 1.5rem !important;  /* ⬅️ Espacio inicial entre la pestaña y el primer texto */
        }
        
        [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] p {
            margin-bottom: 1.8rem !important; /* ⬅️ Espacio extra después de cada resultado (párrafos) */
        }
        
        [data-testid="stExpanderDetails"] ul {
            margin-bottom: 1.8rem !important; /* ⬅️ Espacio extra después de cada resultado (listas/viñetas) */
        }
    </style>
    """
    st.markdown(css_oficial, unsafe_allow_html=True)
    
def banner_institucional():
    """El banner estático ha sido desactivado. Ahora todas las páginas usan el encabezado flotante nativo."""
    pass