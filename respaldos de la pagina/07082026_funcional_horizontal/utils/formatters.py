# -*- coding: utf-8 -*-
"""
Created on Mon Aug  3 11:51:24 2026

@author: dchable
"""

# utils/formatters.py
import pandas as pd

def limpiar_texto(valor):
    if pd.isna(valor) or str(valor).strip() == "" or str(valor) == "nan" or str(valor) == "None": 
        return None
    texto = str(valor).strip()
    try: 
        return texto.encode('latin1').decode('utf-8')
    except: 
        return texto

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