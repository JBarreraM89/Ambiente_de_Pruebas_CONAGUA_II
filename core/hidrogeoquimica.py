# -*- coding: utf-8 -*-
"""
core/hidrogeoquimica.py
===============================================================================
MÓDULO CIENTÍFICO DE HIDROGEOQUÍMICA Y AUDITORÍA DE CALIDAD DEL AGUA
Comisión Nacional del Agua (CONAGUA) - Gerencia de Aguas Subterráneas

Funcionalidades:
  1. Conversión de concentraciones mg/L <-> meq/L <-> mmol/L.
  2. Auditoría de Balance Iónico (% CBE - Charge Balance Error).
  3. Diagrama de Piper interactivo con proyección ternaria y diamante de facies.
  4. Diagramas de Stiff multiescala por pozo/manantial.
  5. Diagrama de Schöeller-Berkaloff semilogarítmico.
  6. Evaluación de aptitud para riego: RAS (SAR), %Na, CSR, Wilcox y USSL (Riverside).
  7. Génesis y procesos geoquímicos: Diagrama de Gibbs y relaciones molares.
  8. Auditoría normativa NOM-127-SSA1-2021 (Agua para uso y consumo humano).
  9. Generación de plantilla Excel oficial normalizada (.xlsx).
 10. Normalizador universal de datos (mapeo flexible de columnas de laboratorio).
===============================================================================
"""

import math
import zipfile
import tempfile
import os
import html
import io
import json
import re
import unicodedata
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# =============================================================================
# 1. CONSTANTES HIDROGEOQUÍMICAS Y PESOS EQUIVALENTES
# =============================================================================
# Peso atómico / molecular y valencia iónica para cálculo de meq/L
# meq/L = mg/L / (peso_molecular / valencia)
PESOS_EQUIVALENTES = {
    # Cationes principales
    'Ca': {'mw': 40.078, 'z': 2, 'eq_wt': 20.039, 'nombre': 'Calcio (Ca²⁺)', 'tipo': 'catión'},
    'Mg': {'mw': 24.305, 'z': 2, 'eq_wt': 12.1525, 'nombre': 'Magnesio (Mg²⁺)', 'tipo': 'catión'},
    'Na': {'mw': 22.990, 'z': 1, 'eq_wt': 22.990, 'nombre': 'Sodio (Na⁺)', 'tipo': 'catión'},
    'K':  {'mw': 39.098, 'z': 1, 'eq_wt': 39.098, 'nombre': 'Potasio (K⁺)', 'tipo': 'catión'},
    # Aniones principales
    'HCO3': {'mw': 61.017, 'z': 1, 'eq_wt': 61.017, 'nombre': 'Bicarbonato (HCO₃⁻)', 'tipo': 'anión'},
    'CO3':  {'mw': 60.009, 'z': 2, 'eq_wt': 30.0045, 'nombre': 'Carbonato (CO₃²⁻)', 'tipo': 'anión'},
    'Cl':   {'mw': 35.453, 'z': 1, 'eq_wt': 35.453, 'nombre': 'Cloruro (Cl⁻)', 'tipo': 'anión'},
    'SO4':  {'mw': 96.063, 'z': 2, 'eq_wt': 48.0313, 'nombre': 'Sulfato (SO₄²⁻)', 'tipo': 'anión'},
    'NO3':  {'mw': 62.005, 'z': 1, 'eq_wt': 62.005, 'nombre': 'Nitrato (NO₃⁻)', 'tipo': 'anión'},
    'F':    {'mw': 18.998, 'z': 1, 'eq_wt': 18.998, 'nombre': 'Fluoruro (F⁻)', 'tipo': 'anión'}
}

# Límites Máximos Permisibles (LMP) NOM-127-SSA1-2021 para agua de uso y consumo humano
LIMITES_NOM_127_2021 = {
    # Fisicoquímicos y Estéticos
    'pH_min': {'lmp': 6.5, 'unidad': 'UpH', 'tipo': 'min', 'categoria': 'Fisicoquímicos', 'nombre': 'Potencial de Hidrógeno (pH Mínimo)'},
    'pH_max': {'lmp': 8.5, 'unidad': 'UpH', 'tipo': 'max', 'categoria': 'Fisicoquímicos', 'nombre': 'Potencial de Hidrógeno (pH Máximo)'},
    'SDT':    {'lmp': 1000.0, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Fisicoquímicos', 'nombre': 'Sólidos Disueltos Totales (SDT)'},
    'Dureza': {'lmp': 500.0, 'unidad': 'mg/L CaCO₃', 'tipo': 'max', 'categoria': 'Fisicoquímicos', 'nombre': 'Dureza Total (como CaCO₃)'},
    'Turbiedad': {'lmp': 4.0, 'unidad': 'UNT', 'tipo': 'max', 'categoria': 'Fisicoquímicos', 'nombre': 'Turbiedad'},
    'Color':  {'lmp': 15.0, 'unidad': 'u Pt-Co', 'tipo': 'max', 'categoria': 'Fisicoquímicos', 'nombre': 'Color Verdadero'},
    # Aniones y Nutrientes
    'Cl':     {'lmp': 250.0, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Aniones', 'nombre': 'Cloruros (Cl⁻)'},
    'SO4':    {'lmp': 400.0, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Aniones', 'nombre': 'Sulfatos (SO₄²⁻)'},
    'F':      {'lmp': 1.5, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Aniones', 'nombre': 'Fluoruros (F⁻)'},
    'NO3':    {'lmp': 45.0, 'unidad': 'mg/L NO₃', 'tipo': 'max', 'categoria': 'Nutrientes', 'nombre': 'Nitratos (como NO₃⁻)'},
    'N_NO3':  {'lmp': 10.0, 'unidad': 'mg/L N', 'tipo': 'max', 'categoria': 'Nutrientes', 'nombre': 'Nitrógeno de Nitratos (N-NO₃)'},
    'N_NO2':  {'lmp': 0.9, 'unidad': 'mg/L N', 'tipo': 'max', 'categoria': 'Nutrientes', 'nombre': 'Nitrógeno de Nitritos (N-NO₂)'},
    'N_NH3':  {'lmp': 0.5, 'unidad': 'mg/L N', 'tipo': 'max', 'categoria': 'Nutrientes', 'nombre': 'Nitrógeno Amoniacal'},
    'Cianuros': {'lmp': 0.05, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Tóxicos Inorgánicos', 'nombre': 'Cianuros Totales'},
    'SAAM':   {'lmp': 0.5, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Surfactantes', 'nombre': 'Sustancias Activas al Azul de Metileno'},
    # Metales y Metaloides Tóxicos (NOM-127-SSA1-2021)
    'As':     {'lmp': 0.010, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales Tóxicos', 'nombre': 'Arsénico Total (As)'},
    'Pb':     {'lmp': 0.010, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales Tóxicos', 'nombre': 'Plomo Total (Pb)'},
    'Cd':     {'lmp': 0.005, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales Tóxicos', 'nombre': 'Cadmio Total (Cd)'},
    'Cr':     {'lmp': 0.050, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales Tóxicos', 'nombre': 'Cromo Total (Cr)'},
    'Hg':     {'lmp': 0.001, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales Tóxicos', 'nombre': 'Mercurio Total (Hg)'},
    'Ba':     {'lmp': 0.700, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales', 'nombre': 'Bario Total (Ba)'},
    'Al':     {'lmp': 0.200, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales', 'nombre': 'Aluminio Total (Al)'},
    'Cu':     {'lmp': 1.500, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales', 'nombre': 'Cobre Total (Cu)'},
    'Fe':     {'lmp': 0.300, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales', 'nombre': 'Hierro Total (Fe)'},
    'Mn':     {'lmp': 0.150, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales', 'nombre': 'Manganeso Total (Mn)'},
    'Zn':     {'lmp': 5.000, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales', 'nombre': 'Zinc Total (Zn)'},
    'Ni':     {'lmp': 0.070, 'unidad': 'mg/L', 'tipo': 'max', 'categoria': 'Metales', 'nombre': 'Níquel Total (Ni)'},
    # Microbiológicos
    'E_Coli': {'lmp': 0.0, 'unidad': 'NMP/100 mL', 'tipo': 'max', 'categoria': 'Microbiológicos', 'nombre': 'Escherichia coli (Ausente)'},
    'Coliformes': {'lmp': 0.0, 'unidad': 'NMP/100 mL', 'tipo': 'max', 'categoria': 'Microbiológicos', 'nombre': 'Coliformes Totales'}
}

# =============================================================================
# 2. MAPEO Y NORMALIZACIÓN INTELIGENTE DE COLUMNAS
# =============================================================================
ALIAS_COLUMNAS = {
    'Muestra': ['MUESTRA', 'ID_MUESTRA', 'NOMBRE', 'SITIO', 'POZO', 'MANANTIAL', 'ID', 'ESTACION', 'CLAVE', 'IDENTIFICADOR'],
    'Tipo_Fuente': ['TIPO_FUENTE', 'TIPO', 'FUENTE', 'MATRIZ', 'ORIGEN', 'SUBTIPO'],
    'Fecha': ['FECHA', 'FECHA_MUESTREO', 'DATE', 'FECHA_TOMA', 'ANO', 'AÑO'],
    'Latitud': ['LATITUD', 'LAT', 'Y', 'NORTH', 'NORTE'],
    'Longitud': ['LONGITUD', 'LON', 'LNG', 'X', 'WEST', 'OESTE'],
    'Elevacion': ['ELEVACION', 'ELEV', 'ALTITUD', 'COTA', 'MSNM', 'Z'],
    'Temp_C': ['TEMP', 'TEMPERATURA', 'TEMP_C', 'T_C', 'GRADOS_C'],
    'pH': ['PH', 'POTENCIAL_HIDROGENO', 'UPH'],
    'CE_uS_cm': ['CE', 'CONDUCTIVIDAD', 'COND', 'CE_US_CM', 'COND_ELEC', 'EC'],
    'SDT_mg_L': ['SDT', 'TDS', 'SOLIDOS_DISUELTOS_TOTALES', 'SDT_MG_L', 'SOLIDOS_TOTALES_DISUELTOS'],
    'Dureza_mg_L': ['DUREZA', 'DUREZA_TOTAL', 'DUREZA_MG_L', 'DUREZA_CACO3', 'TH'],
    # Cationes
    'Ca_mg_L': ['CA', 'CALCIO', 'CA_MG_L', 'CA2', 'CA_DISUELTO', 'CALCIO_TOTAL'],
    'Mg_mg_L': ['MG', 'MAGNESIO', 'MG_MG_L', 'MG2', 'MG_DISUELTO', 'MAGNESIO_TOTAL'],
    'Na_mg_L': ['NA', 'SODIO', 'NA_MG_L', 'NA1', 'NA_DISUELTO', 'SODIO_TOTAL'],
    'K_mg_L':  ['K', 'POTASIO', 'K_MG_L', 'K1', 'K_DISUELTO', 'POTASIO_TOTAL'],
    # Aniones
    'HCO3_mg_L': ['HCO3', 'BICARBONATOS', 'BICARBONATO', 'HCO3_MG_L', 'ALCALINIDAD_HCO3', 'ALC_HCO3'],
    'CO3_mg_L':  ['CO3', 'CARBONATOS', 'CARBONATO', 'CO3_MG_L', 'ALCALINIDAD_CO3'],
    'Cl_mg_L':   ['CL', 'CLORUROS', 'CLORURO', 'CL_MG_L', 'CHLORIDE'],
    'SO4_mg_L':  ['SO4', 'SULFATOS', 'SULFATO', 'SO4_MG_L', 'SULFATE'],
    'NO3_mg_L':  ['NO3', 'NITRATOS', 'NITRATO', 'NO3_MG_L', 'NITRATE'],
    'N_NO3_mg_L': ['N_NO3', 'N-NITRATOS', 'N_NITRATOS', 'NITROGENO_NITRATOS'],
    'F_mg_L':    ['F', 'FLUORUROS', 'FLUORURO', 'F_MG_L', 'FLUOR'],
    # Metales
    'As_mg_L': ['AS', 'ARSENICO', 'AS_TOTAL', 'AS_MG_L', 'ARSENICO_TOTAL'],
    'Pb_mg_L': ['PB', 'PLOMO', 'PB_TOTAL', 'PB_MG_L', 'PLOMO_TOTAL'],
    'Cd_mg_L': ['CD', 'CADMIO', 'CD_TOTAL', 'CD_MG_L'],
    'Cr_mg_L': ['CR', 'CROMO', 'CR_TOTAL', 'CR_MG_L'],
    'Hg_mg_L': ['HG', 'MERCURIO', 'HG_TOTAL', 'HG_MG_L'],
    'Fe_mg_L': ['FE', 'HIERRO', 'FE_TOTAL', 'FE_MG_L'],
    'Mn_mg_L': ['MN', 'MANGANESO', 'MN_TOTAL', 'MN_MG_L'],
    'Zn_mg_L': ['ZN', 'ZINC', 'ZN_TOTAL', 'ZN_MG_L'],
    'Al_mg_L': ['AL', 'ALUMINIO', 'AL_TOTAL', 'AL_MG_L'],
    'Ba_mg_L': ['BA', 'BARIO', 'BA_TOTAL', 'BA_MG_L'],
    'Cu_mg_L': ['CU', 'COBRE', 'CU_TOTAL', 'CU_MG_L'],
    'Ni_mg_L': ['NI', 'NIQUEL', 'NI_TOTAL', 'NI_MG_L'],
    # Microbiológicos
    'E_Coli': ['E_COLI', 'ESCHERICHIA_COLI', 'ECOLI', 'COLI']
}

def normalizar_texto_col(col):
    if not col: return ""
    t = str(col).strip().upper()
    t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    t = re.sub(r'[^A-Z0-9]', '_', t)
    return re.sub(r'_+', '_', t).strip('_')

def mapear_dataframe_hidroquimico(df_raw):
    """
    Toma un DataFrame crudo proveniente de Excel, CSV o tabla de laboratorio
    y normaliza sus columnas hacia los nombres canónicos estandarizados.
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()

    df = df_raw.copy()
    mapa_renombrado = {}
    canonicos_usados = set()

    for col_orig in df.columns:
        c_norm = normalizar_texto_col(col_orig)

        # 1. Si ya coincide exactamente con un canónico
        if col_orig in ALIAS_COLUMNAS:
            mapa_renombrado[col_orig] = col_orig
            canonicos_usados.add(col_orig)
            continue

        # 2. Si su versión normalizada coincide con algún canónico
        c_matched = None
        for canonico in ALIAS_COLUMNAS.keys():
            if c_norm == normalizar_texto_col(canonico):
                c_matched = canonico
                break
        if c_matched and c_matched not in canonicos_usados:
            mapa_renombrado[col_orig] = c_matched
            canonicos_usados.add(c_matched)
            continue

        # 3. Buscar en la lista de aliases explícitos (coincidencia exacta)
        for canonico, aliases in ALIAS_COLUMNAS.items():
            if canonico in canonicos_usados:
                continue
            if c_norm in aliases:
                mapa_renombrado[col_orig] = canonico
                canonicos_usados.add(canonico)
                break

    df = df.rename(columns=mapa_renombrado)

    # Si no tiene columna 'Muestra', usar la primera columna de texto o índice
    if 'Muestra' not in df.columns:
        primera_col = df.columns[0]
        df['Muestra'] = df[primera_col].astype(str)

    # Limpiar cadenas de texto numéricas con '<' (ej. '< 0.010' -> 0.005, límite de detección / 2)
    for col in df.columns:
        if col in ['Muestra', 'Tipo_Fuente', 'Fecha']:
            continue
        try:
            if df[col].dtype == object:
                # Detectar valores tipo '< 0.010' o '<0.002'
                def limpiar_num(v):
                    if pd.isna(v): return np.nan
                    v_str = str(v).strip()
                    if v_str.startswith('<'):
                        try:
                            num = float(v_str.replace('<', '').strip())
                            return num / 2.0  # Criterio estándar OMM/EPA: mitad del límite de detección
                        except Exception:
                            return np.nan
                    try:
                        return float(re.sub(r'[^\d\.\-]', '', v_str))
                    except Exception:
                        return np.nan
                df[col] = df[col].apply(limpiar_num)
            else:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        except Exception:
            pass

    return df

# =============================================================================
# 3. CÁLCULOS HIDROGEOQUÍMICOS (meq/L, CBE, ÍNDICES Y FACIES)
# =============================================================================
def procesar_muestras_hidroquimicas(df_muestras):
    """
    Calcula meq/L, suma de cationes/aniones, error de balance iónico (% CBE),
    facies de Piper, índices de riego (RAS, %Na, CSR) y coordenadas de Gibbs.
    """
    if df_muestras is None or df_muestras.empty:
        return pd.DataFrame()

    df = df_muestras.copy()

    # 1. Conversión de concentraciones mg/L a meq/L
    for ion, datos in PESOS_EQUIVALENTES.items():
        col_mg = f"{ion}_mg_L"
        col_meq = f"{ion}_meq_L"
        if col_mg in df.columns:
            df[col_meq] = df[col_mg].fillna(0.0) / datos['eq_wt']
        else:
            df[col_meq] = 0.0

    # Si se reportó N-NO3 en lugar de NO3, convertir: NO3 = N-NO3 * 4.427
    if 'NO3_mg_L' not in df.columns and 'N_NO3_mg_L' in df.columns:
        df['NO3_mg_L'] = df['N_NO3_mg_L'] * 4.427
        df['NO3_meq_L'] = df['NO3_mg_L'] / PESOS_EQUIVALENTES['NO3']['eq_wt']

    # Si no hay HCO3 pero hay alcalinidad o CO3
    if 'HCO3_mg_L' not in df.columns and 'Alcalinidad_mg_L' in df.columns:
        df['HCO3_mg_L'] = df['Alcalinidad_mg_L'] * 1.22
        df['HCO3_meq_L'] = df['HCO3_mg_L'] / PESOS_EQUIVALENTES['HCO3']['eq_wt']

    # 2. Sumas iónicas
    df['Suma_Cationes_meq'] = df['Ca_meq_L'] + df['Mg_meq_L'] + df['Na_meq_L'] + df['K_meq_L']
    df['Suma_Aniones_meq'] = df['HCO3_meq_L'] + df['CO3_meq_L'] + df['Cl_meq_L'] + df['SO4_meq_L'] + df['NO3_meq_L']

    # 3. Error de Balance Iónico (% CBE - Charge Balance Error)
    # CBE = (Cationes - Aniones) / (Cationes + Aniones) * 100
    denom = df['Suma_Cationes_meq'] + df['Suma_Aniones_meq']
    df['CBE_pct'] = np.where(denom > 0, ((df['Suma_Cationes_meq'] - df['Suma_Aniones_meq']) / denom) * 100.0, np.nan)

    def clasificar_cbe(val):
        if pd.isna(val): return "Sin datos de iones mayores"
        abs_v = abs(val)
        if abs_v <= 5.0: return "Excelente (≤ 5%)"
        elif abs_v <= 10.0: return "Aceptable (5 - 10%)"
        else: return "Discrepancia Analítica (> 10%)"

    df['CBE_Calidad'] = df['CBE_pct'].apply(clasificar_cbe)

    # 4. Porcentajes para Piper
    cat_tot = df['Suma_Cationes_meq']
    df['pct_Ca'] = np.where(cat_tot > 0, (df['Ca_meq_L'] / cat_tot) * 100.0, 0.0)
    df['pct_Mg'] = np.where(cat_tot > 0, (df['Mg_meq_L'] / cat_tot) * 100.0, 0.0)
    df['pct_Na_K'] = np.where(cat_tot > 0, ((df['Na_meq_L'] + df['K_meq_L']) / cat_tot) * 100.0, 0.0)

    an_tot = df['Suma_Aniones_meq']
    df['pct_HCO3_CO3'] = np.where(an_tot > 0, ((df['HCO3_meq_L'] + df['CO3_meq_L']) / an_tot) * 100.0, 0.0)
    df['pct_SO4'] = np.where(an_tot > 0, (df['SO4_meq_L'] / an_tot) * 100.0, 0.0)
    df['pct_Cl'] = np.where(an_tot > 0, (df['Cl_meq_L'] / an_tot) * 100.0, 0.0)

    # 5. Determinación de Facies Hidroquímica
    def clasificar_facies(row):
        if row['Suma_Cationes_meq'] == 0 or row['Suma_Aniones_meq'] == 0:
            return "Indeterminada (Sin Iones Mayores)"

        # Catión dominante
        ca = row['pct_Ca']
        mg = row['pct_Mg']
        na_k = row['pct_Na_K']

        if ca >= 50: cat_dom = "Cálcica"
        elif mg >= 50: cat_dom = "Magnésica"
        elif na_k >= 50: cat_dom = "Sódica"
        elif ca >= mg and ca >= na_k: cat_dom = "Cálcica-Magnésica"
        elif na_k >= ca and na_k >= mg: cat_dom = "Sódica-Cálcica"
        else: cat_dom = "Mixta Catiónica"

        # Anión dominante
        hco3 = row['pct_HCO3_CO3']
        so4 = row['pct_SO4']
        cl = row['pct_Cl']

        if hco3 >= 50: an_dom = "Bicarbonatada"
        elif so4 >= 50: an_dom = "Sulfatada"
        elif cl >= 50: an_dom = "Clorurada"
        elif hco3 >= so4 and hco3 >= cl: an_dom = "Bicarbonatada-Sulfatada"
        elif cl >= hco3 and cl >= so4: an_dom = "Clorurada-Sulfatada"
        else: an_dom = "Mixta Aniónica"

        return f"{an_dom} {cat_dom}"

    df['Facies_Piper'] = df.apply(clasificar_facies, axis=1)

    # 6. Índices para Uso Agrícola y Riego
    # Relación de Adsorción de Sodio (RAS / SAR)
    ca_mg_half = (df['Ca_meq_L'] + df['Mg_meq_L']) / 2.0
    df['RAS'] = np.where(ca_mg_half > 0, df['Na_meq_L'] / np.sqrt(ca_mg_half), np.nan)

    # % Sodio Soluble (%Na)
    cat_suma = df['Suma_Cationes_meq']
    df['Pct_Na_Riego'] = np.where(cat_suma > 0, ((df['Na_meq_L'] + df['K_meq_L']) / cat_suma) * 100.0, np.nan)

    # Carbonato de Sodio Residual (CSR en meq/L)
    # CSR = (HCO3 + CO3) - (Ca + Mg)
    df['CSR'] = (df['HCO3_meq_L'] + df['CO3_meq_L']) - (df['Ca_meq_L'] + df['Mg_meq_L'])

    def clasificar_ras(val):
        if pd.isna(val): return "N/D"
        if val < 10.0: return "S1 - Bajo Riesgo (Excelente)"
        elif val < 18.0: return "S2 - Riesgo Medio (Bueno)"
        elif val < 26.0: return "S3 - Riesgo Alto (Dudoso)"
        else: return "S4 - Muy Alto (Inadecuado)"

    def clasificar_csr(val):
        if pd.isna(val): return "N/D"
        if val < 1.25: return "Seguro (Apto para todo suelo)"
        elif val <= 2.50: return "Marginal (Requiere manejo)"
        else: return "Inadecuado (Peligro de sodificación)"

    df['Clasif_RAS'] = df['RAS'].apply(clasificar_ras)
    df['Clasif_CSR'] = df['CSR'].apply(clasificar_csr)

    # 7. Diagrama de Gibbs
    # Cationes: (Na + K) / (Na + K + Ca)
    denom_gibbs_cat = df['Na_meq_L'] + df['K_meq_L'] + df['Ca_meq_L']
    df['Gibbs_Cationes'] = np.where(denom_gibbs_cat > 0, (df['Na_meq_L'] + df['K_meq_L']) / denom_gibbs_cat, np.nan)

    # Aniones: Cl / (Cl + HCO3)
    denom_gibbs_an = df['Cl_meq_L'] + df['HCO3_meq_L']
    df['Gibbs_Aniones'] = np.where(denom_gibbs_an > 0, df['Cl_meq_L'] / denom_gibbs_an, np.nan)

    # 8. Relaciones Molares / Iónicas e Indicadores Geoquímicos (en meq/meq)
    df['rNa_rCl'] = np.where(df['Cl_meq_L'] > 0, df['Na_meq_L'] / df['Cl_meq_L'], np.nan)
    df['rCa_rSO4'] = np.where(df['SO4_meq_L'] > 0, df['Ca_meq_L'] / df['SO4_meq_L'], np.nan)
    hco3_tot = df['HCO3_meq_L'] + df['CO3_meq_L']
    df['rCaMg_rHCO3'] = np.where(hco3_tot > 0, (df['Ca_meq_L'] + df['Mg_meq_L']) / hco3_tot, np.nan)
    df['rMg_rCa'] = np.where(df['Ca_meq_L'] > 0, df['Mg_meq_L'] / df['Ca_meq_L'], np.nan)

    # Índice de Revelle (Cl / HCO3): trazador sensible de salinización e intrusión marina
    df['Indice_Revelle'] = np.where(hco3_tot > 0, df['Cl_meq_L'] / hco3_tot, np.nan)
    def clasif_revelle(val):
        if pd.isna(val): return 'N/D'
        if val < 1.0: return 'Agua Continental Dulce (Sin afectación)'
        elif val <= 2.8: return 'Ligera Salinización'
        elif val <= 6.6: return 'Afectación Salina Moderada'
        else: return 'Fuerte Intrusión Marina / Salinidad Crítica'
    df['Clasif_Revelle'] = df['Indice_Revelle'].apply(clasif_revelle)

    # Dureza Total Calculada como CaCO3 (mg/L)
    df['Dureza_Calculada_mg_L'] = (df['Ca_meq_L'] + df['Mg_meq_L']) * 50.04

    # Si no hay SDT medido pero hay CE, estimar SDT aprox = CE * 0.65
    if 'SDT_mg_L' not in df.columns or df['SDT_mg_L'].isna().all():
        if 'CE_uS_cm' in df.columns:
            df['SDT_mg_L'] = df['CE_uS_cm'] * 0.65

    return df

# =============================================================================
# 4. AUDITORÍA NORMATIVA NOM-127-SSA1-2021
# =============================================================================
def auditar_norma_127(df_muestras):
    """
    Evalúa cada muestra frente a los Límites Máximos Permisibles de la NOM-127-SSA1-2021.
    Retorna un diccionario con resumen estadístico y DataFrame detallado con semáforos.
    """
    if df_muestras is None or df_muestras.empty:
        return {}, pd.DataFrame()

    df = df_muestras.copy()
    resultados_auditoria = []

    for idx, row in df.iterrows():
        id_m = str(row.get('Muestra', f"Muestra-{idx+1}"))
        tipo = str(row.get('Tipo_Fuente', 'Agua Subterránea'))

        total_evaluados = 0
        conformes = 0
        alertas = 0
        no_conformes = 0
        parametros_excedidos = []
        parametros_alerta = []

        for p_key, info in LIMITES_NOM_127_2021.items():
            col_nom = f"{p_key}_mg_L" if p_key not in ['pH_min', 'pH_max', 'SDT', 'Dureza', 'Color', 'Turbiedad', 'E_Coli', 'Coliformes', 'pH'] else p_key
            if col_nom not in row:
                col_nom = p_key

            val = row.get(col_nom)
            if pd.isna(val):
                continue

            try:
                val = float(val)
            except Exception:
                continue

            total_evaluados += 1
            lmp = info['lmp']
            tipo_lim = info['tipo']

            if tipo_lim == 'max':
                if lmp == 0.0:  # Microbiológico (debe ser 0)
                    if val > 0:
                        no_conformes += 1
                        parametros_excedidos.append(f"{info['nombre']} ({val:g} {info['unidad']} > {lmp:g})")
                    else:
                        conformes += 1
                else:
                    if val > lmp:
                        no_conformes += 1
                        parametros_excedidos.append(f"{info['nombre']} ({val:.3f} {info['unidad']} > LMP {lmp})")
                    elif val >= (lmp * 0.80):
                        alertas += 1
                        parametros_alerta.append(f"{info['nombre']} ({val:.3f} {info['unidad']}, ≥80% LMP)")
                    else:
                        conformes += 1
            elif tipo_lim == 'min':
                if val < lmp:
                    no_conformes += 1
                    parametros_excedidos.append(f"{info['nombre']} ({val:.2f} < Mín {lmp})")
                else:
                    conformes += 1

        if no_conformes > 0:
            estatus_global = "🚨 No Conforme (Excede Norma)"
            color_estatus = "#9f2241"
        elif alertas > 0:
            estatus_global = "⚠️ Alerta Preventiva (≥ 80% LMP)"
            color_estatus = "#d97706"
        elif total_evaluados > 0:
            estatus_global = "✅ Conforme (Dentro de Norma)"
            color_estatus = "#16a34a"
        else:
            estatus_global = "ℹ️ Sin Parámetros Evaluados"
            color_estatus = "#64748b"

        resultados_auditoria.append({
            'Muestra': id_m,
            'Tipo_Fuente': tipo,
            'Estatus_NOM127': estatus_global,
            'Color_Estatus': color_estatus,
            'Total_Evaluados': total_evaluados,
            'Conformes': conformes,
            'Alertas': alertas,
            'No_Conformes': no_conformes,
            'Parametros_Excedidos': "; ".join(parametros_excedidos) if parametros_excedidos else "Ninguno",
            'Parametros_Alerta': "; ".join(parametros_alerta) if parametros_alerta else "Ninguno"
        })

    df_res = pd.DataFrame(resultados_auditoria)
    resumen = {
        'total_muestras': len(df_res),
        'conformes': len(df_res[df_res['Estatus_NOM127'].str.contains(r"Conforme \(Dentro")]),
        'alertas': len(df_res[df_res['Estatus_NOM127'].str.contains("Alerta")]),
        'no_conformes': len(df_res[df_res['Estatus_NOM127'].str.contains("No Conforme")])
    }
    return resumen, df_res

# =============================================================================
# 5. DIAGRAMA DE PIPER INTERACTIVO (PLOTLY)
# =============================================================================
def generar_diagrama_piper(df_procesado):
    """
    Construye un Diagrama de Piper interactivo con Plotly:
      - Triángulo de Cationes (Ca - Mg - Na+K) a la izquierda.
      - Triángulo de Aniones (HCO3 - SO4 - Cl) a la derecha (Estándar Internacional).
      - Diamante Central de Facies Hidrogeoquímicas con proyección geométrica rigurosa.
    """
    fig = go.Figure()

    # Geometría y escala de Piper
    h_tri = math.sqrt(3) / 2.0  # 0.866025
    x_gap = 0.5  # Espacio entre triángulos y diamante
    x_cat_orig = 0.0
    x_an_orig = 1.0 + x_gap  # 1.5

    # 1. Líneas guía y bordes del Triángulo de Cationes
    fig.add_trace(go.Scatter(
        x=[x_cat_orig, x_cat_orig + 1.0, x_cat_orig + 0.5, x_cat_orig],
        y=[0.0, 0.0, h_tri, 0.0],
        mode='lines',
        line=dict(color='#334155', width=1.8),
        hoverinfo='skip',
        showlegend=False
    ))
    for pct in [0.2, 0.4, 0.6, 0.8]:
        y_t = pct * h_tri
        x1_t = x_cat_orig + pct * 0.5
        x2_t = x_cat_orig + 1.0 - pct * 0.5
        fig.add_trace(go.Scatter(x=[x1_t, x2_t], y=[y_t, y_t], mode='lines', line=dict(color='#cbd5e1', width=0.8, dash='dot'), hoverinfo='skip', showlegend=False))

    # 2. Líneas guía y bordes del Triángulo de Aniones
    fig.add_trace(go.Scatter(
        x=[x_an_orig, x_an_orig + 1.0, x_an_orig + 0.5, x_an_orig],
        y=[0.0, 0.0, h_tri, 0.0],
        mode='lines',
        line=dict(color='#334155', width=1.8),
        hoverinfo='skip',
        showlegend=False
    ))
    for pct in [0.2, 0.4, 0.6, 0.8]:
        y_t = pct * h_tri
        x1_t = x_an_orig + pct * 0.5
        x2_t = x_an_orig + 1.0 - pct * 0.5
        fig.add_trace(go.Scatter(x=[x1_t, x2_t], y=[y_t, y_t], mode='lines', line=dict(color='#cbd5e1', width=0.8, dash='dot'), hoverinfo='skip', showlegend=False))

    # 3. Diamante Central
    x_diam_bot, y_diam_bot = 1.25, h_tri
    x_diam_left, y_diam_left = 0.75, h_tri * 1.5
    x_diam_right, y_diam_right = 1.75, h_tri * 1.5
    x_diam_top, y_diam_top = 1.25, h_tri * 2.0

    fig.add_trace(go.Scatter(
        x=[x_diam_bot, x_diam_right, x_diam_top, x_diam_left, x_diam_bot],
        y=[y_diam_bot, y_diam_right, y_diam_top, y_diam_left, y_diam_bot],
        mode='lines',
        line=dict(color='#1e293b', width=2.0),
        hoverinfo='skip',
        showlegend=False
    ))
    # Ejes medios punteados del Diamante
    fig.add_trace(go.Scatter(x=[x_diam_left, x_diam_right], y=[y_diam_left, y_diam_right], mode='lines', line=dict(color='#94a3b8', width=1.0, dash='dash'), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=[x_diam_bot, x_diam_top], y=[y_diam_bot, y_diam_top], mode='lines', line=dict(color='#94a3b8', width=1.0, dash='dash'), hoverinfo='skip', showlegend=False))

    # Rotulación de Esquinas y Facies
    anotaciones = [
        # Cationes (Triángulo Izquierdo)
        dict(x=x_cat_orig - 0.04, y=-0.04, text='<b>Ca²⁺</b> (100%)', showarrow=False, font=dict(color='#1e293b', size=11)),
        dict(x=x_cat_orig + 1.04, y=-0.04, text='<b>Na⁺ + K⁺</b> (100%)', showarrow=False, font=dict(color='#1e293b', size=11)),
        dict(x=x_cat_orig + 0.5, y=h_tri + 0.05, text='<b>Mg²⁺</b> (100%)', showarrow=False, font=dict(color='#1e293b', size=11)),
        dict(x=x_cat_orig + 0.5, y=-0.08, text='<b>CATIONES (% meq/L)</b>', showarrow=False, font=dict(color='#691C32', size=11.5)),
        # Aniones (Triángulo Derecho - Estándar Internacional Piper)
        dict(x=x_an_orig - 0.04, y=-0.04, text='<b>HCO₃⁻ + CO₃²⁻</b> (100%)', showarrow=False, font=dict(color='#1e293b', size=11)),
        dict(x=x_an_orig + 1.04, y=-0.04, text='<b>Cl⁻</b> (100%)', showarrow=False, font=dict(color='#1e293b', size=11)),
        dict(x=x_an_orig + 0.5, y=h_tri + 0.05, text='<b>SO₄²⁻</b> (100%)', showarrow=False, font=dict(color='#1e293b', size=11)),
        dict(x=x_an_orig + 0.5, y=-0.08, text='<b>ANIONES (% meq/L)</b>', showarrow=False, font=dict(color='#691C32', size=11.5)),
        # Diamante Facies
        dict(x=x_diam_bot, y=y_diam_bot - 0.05, text='<b>Bicarbonatada Cálcica / Magnésica (Recarga)</b>', showarrow=False, font=dict(color='#166534', size=10)),
        dict(x=x_diam_top, y=y_diam_top + 0.05, text='<b>Clorurada Sódica (Salina Marina / Profunda)</b>', showarrow=False, font=dict(color='#991b1b', size=10)),
        dict(x=x_diam_left - 0.05, y=y_diam_left, text='<b>Bicarbonatada Sódica</b>', showarrow=False, font=dict(color='#475569', size=9.5), textangle=-45),
        dict(x=x_diam_right + 0.05, y=y_diam_right, text='<b>Sulfatada / Clorurada Cálcica</b>', showarrow=False, font=dict(color='#475569', size=9.5), textangle=45),
    ]

    # 4. Proyección de Muestras
    colores_paleta = px.colors.qualitative.Dark24

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        facies = str(r.get('Facies_Piper', 'N/D'))
        color_pt = colores_paleta[idx % len(colores_paleta)]

        ca = float(r.get('pct_Ca', 0.0))
        mg = float(r.get('pct_Mg', 0.0))
        na_k = float(r.get('pct_Na_K', 0.0))

        cl = float(r.get('pct_Cl', 0.0))
        so4 = float(r.get('pct_SO4', 0.0))
        hco3 = float(r.get('pct_HCO3_CO3', 0.0))

        # Triángulo Cationes:
        xc = x_cat_orig + (na_k + 0.5 * mg) / 100.0
        yc = (mg / 100.0) * h_tri

        # Triángulo Aniones (Estándar Piper):
        # HCO3 (izq 0%), Cl (der 100%), SO4 (arriba 100%)
        xa = x_an_orig + (cl + 0.5 * so4) / 100.0
        ya = (so4 / 100.0) * h_tri

        # Diamante Central:
        u_cat = na_k / 100.0
        v_an = (cl + so4) / 100.0

        xd = x_diam_bot + 0.5 * (v_an - u_cat)
        yd = y_diam_bot + 0.5 * h_tri * (v_an + u_cat)

        hover_txt = f"""
        <b>Muestra:</b> {id_m}<br>
        <b>Facies:</b> {facies}<br>
        <b>CBE:</b> {r.get('CBE_pct', 0.0):+.2f}%<br>
        <b>Cationes:</b> Ca={ca:.1f}%, Mg={mg:.1f}%, Na+K={na_k:.1f}%<br>
        <b>Aniones:</b> HCO₃={hco3:.1f}%, SO₄={so4:.1f}%, Cl={cl:.1f}%
        """

        # Punto Cationes
        fig.add_trace(go.Scatter(
            x=[xc], y=[yc], mode='markers',
            marker=dict(size=9, color=color_pt, line=dict(width=1, color='#0f172a')),
            name=id_m, hovertext=hover_txt, hoverinfo='text',
            legendgroup=id_m, showlegend=False
        ))

        # Punto Aniones
        fig.add_trace(go.Scatter(
            x=[xa], y=[ya], mode='markers',
            marker=dict(size=9, color=color_pt, line=dict(width=1, color='#0f172a')),
            hovertext=hover_txt, hoverinfo='text',
            legendgroup=id_m, showlegend=False
        ))

        # Punto Diamante
        fig.add_trace(go.Scatter(
            x=[xd], y=[yd], mode='markers',
            marker=dict(size=10, color=color_pt, symbol='diamond', line=dict(width=1.2, color='#0f172a')),
            name=f"{id_m} ({facies})",
            hovertext=hover_txt, hoverinfo='text',
            legendgroup=id_m, showlegend=True
        ))

        # Líneas de proyección punteadas conectando triángulos al diamante
        fig.add_trace(go.Scatter(
            x=[xc, xd, xa], y=[yc, yd, ya], mode='lines',
            line=dict(color=color_pt, width=0.8, dash='dot'),
            hoverinfo='skip', legendgroup=id_m, showlegend=False
        ))

    fig.update_layout(
        title='<b>Diagrama Trilineal de Piper - Clasificación de Facies Hidrogeoquímicas</b>',
        annotations=anotaciones,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.15, 2.75]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.15, 1.95], scaleanchor='x', scaleratio=1),
        height=660,
        plot_bgcolor='rgba(255,255,255,1)',
        paper_bgcolor='rgba(255,255,255,1)',
        margin=dict(t=50, b=40, l=20, r=220),
        legend=dict(
            orientation='v',
            yanchor='top',
            y=0.98,
            xanchor='left',
            x=1.02,
            font=dict(size=10),
            bgcolor='rgba(255,255,255,0.92)',
            bordercolor='#cbd5e1',
            borderwidth=1
        )
    )
    return fig

# =============================================================================
# 6. DIAGRAMAS DE STIFF MULTIMUESTRA
# =============================================================================
def hex_or_rgb_to_rgba(c, alpha=0.45):
    c = str(c).strip()
    if c.startswith('#'):
        c = c.lstrip('#')
        if len(c) == 6:
            r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            return f"rgba({r}, {g}, {b}, {alpha})"
    elif c.startswith('rgb'):
        nums = re.findall(r'\d+', c)
        if len(nums) >= 3:
            return f"rgba({nums[0]}, {nums[1]}, {nums[2]}, {alpha})"
    return f"rgba(100, 100, 100, {alpha})"

def generar_diagrama_stiff(df_procesado, muestra_sel=None):
    """
    Construye diagramas poligonales de Stiff para una o varias muestras.
    Iones en meq/L:
      Fila 1: Na+K (izq) vs Cl (der)
      Fila 2: Ca (izq) vs HCO3+CO3 (der)
      Fila 3: Mg (izq) vs SO4 (der)
      Fila 4: Fe (izq) vs NO3 (der)
    """
    df_plot = df_procesado.copy()
    if muestra_sel and muestra_sel != "Todas las Muestras":
        df_plot = df_plot[df_plot['Muestra'].astype(str) == str(muestra_sel)]

    n_muestras = len(df_plot)
    if n_muestras == 0:
        return go.Figure()

    # Si hay múltiples muestras, armar una cuadrícula con subplots
    from plotly.subplots import make_subplots
    cols_grid = min(3, n_muestras)
    rows_grid = math.ceil(n_muestras / cols_grid)

    titulos_sub = [f"<b>{r.get('Muestra')}</b> ({r.get('Facies_Piper', '')})" for _, r in df_plot.iterrows()]
    fig = make_subplots(rows=rows_grid, cols=cols_grid, subplot_titles=titulos_sub, vertical_spacing=0.15, horizontal_spacing=0.1)

    # Determinar escala máxima en meq/L para eje simétrico
    max_meq = max([
        df_plot['Ca_meq_L'].max(), df_plot['Mg_meq_L'].max(),
        (df_plot['Na_meq_L'] + df_plot['K_meq_L']).max(),
        (df_plot['HCO3_meq_L'] + df_plot['CO3_meq_L']).max(),
        df_plot['SO4_meq_L'].max(), df_plot['Cl_meq_L'].max(), 5.0
    ])
    escala_x = math.ceil(max_meq * 1.15)

    y_labels = ["Fe / NO₃", "Mg / SO₄", "Ca / HCO₃", "Na+K / Cl"]
    y_pos = [1, 2, 3, 4]

    colores = px.colors.qualitative.Bold

    for idx, (_, r) in enumerate(df_plot.iterrows()):
        row_i = (idx // cols_grid) + 1
        col_i = (idx % cols_grid) + 1

        na_k = float(r.get('Na_meq_L', 0) + r.get('K_meq_L', 0))
        ca = float(r.get('Ca_meq_L', 0))
        mg = float(r.get('Mg_meq_L', 0))
        fe = float(r.get('Fe_meq_L', 0.0) if 'Fe_meq_L' in r else (r.get('Fe_mg_L', 0.0) / 27.92))

        cl = float(r.get('Cl_meq_L', 0))
        hco3 = float(r.get('HCO3_meq_L', 0) + r.get('CO3_meq_L', 0))
        so4 = float(r.get('SO4_meq_L', 0))
        no3 = float(r.get('NO3_meq_L', 0))

        # Coordenadas del polígono cerrado (izq negativos, der positivos)
        xs = [-na_k, -ca, -mg, -fe, fe, so4, hco3, cl, -na_k]
        ys = [4, 3, 2, 1, 1, 2, 3, 4, 4]

        color_fill = colores[idx % len(colores)]

        # Polígono de Stiff
        fig.add_trace(go.Scatter(
            x=xs, y=ys, fill='toself',
            fillcolor=hex_or_rgb_to_rgba(color_fill, 0.45),
            line=dict(color=color_fill, width=2.0),
            mode='lines+markers',
            marker=dict(size=5, color=color_fill),
            hoverinfo='text',
            hovertext=[
                f"Na+K: {na_k:.2f} meq/L", f"Ca: {ca:.2f} meq/L", f"Mg: {mg:.2f} meq/L", f"Fe: {fe:.2f} meq/L",
                f"NO₃: {no3:.2f} meq/L", f"SO₄: {so4:.2f} meq/L", f"HCO₃: {hco3:.2f} meq/L", f"Cl: {cl:.2f} meq/L",
                f"Na+K: {na_k:.2f} meq/L"
            ],
            showlegend=False
        ), row=row_i, col=col_i)

        # Eje cero vertical central
        fig.add_vline(x=0, line=dict(color="#64748b", width=1.2, dash="dash"), row=row_i, col=col_i)

        fig.update_xaxes(range=[-escala_x, escala_x], title="Cationes (meq/L) ← 0 → Aniones (meq/L)" if row_i == rows_grid else "", row=row_i, col=col_i)
        fig.update_yaxes(tickvals=y_pos, ticktext=y_labels, row=row_i, col=col_i)

    alt_total = max(350, rows_grid * 240)
    fig.update_layout(
        title="<b>Diagramas de Huella Iónica de Stiff (meq/L)</b>",
        height=alt_total,
        plot_bgcolor='#f8fafc',
        paper_bgcolor='white',
        margin=dict(t=60, b=40, l=40, r=40)
    )
    return fig

# =============================================================================
# 7. DIAGRAMA DE SCHÖELLER-BERKALOFF
# =============================================================================
def generar_diagrama_schoeller(df_procesado):
    """
    Gráfico semilogarítmico para trazar líneas de evolución hidrogeoquímica.
    Eje X: Ca, Mg, Na+K, Cl, SO4, HCO3
    Eje Y: Concentración en meq/L (escala log10).
    """
    fig = go.Figure()
    iones_x = ["Ca²⁺", "Mg²⁺", "Na⁺+K⁺", "HCO₃⁻", "SO₄²⁻", "Cl⁻"]
    colores = px.colors.qualitative.Dark24

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        color_linea = colores[idx % len(colores)]

        vals_y = [
            max(0.001, float(r.get('Ca_meq_L', 0.001))),
            max(0.001, float(r.get('Mg_meq_L', 0.001))),
            max(0.001, float(r.get('Na_meq_L', 0) + r.get('K_meq_L', 0))),
            max(0.001, float(r.get('HCO3_meq_L', 0.001) + r.get('CO3_meq_L', 0))),
            max(0.001, float(r.get('SO4_meq_L', 0.001))),
            max(0.001, float(r.get('Cl_meq_L', 0.001)))
        ]

        hover_txt = f"<b>{id_m}</b><br>" + "<br>".join([f"{ion}: {v:.2f} meq/L" for ion, v in zip(iones_x, vals_y)])

        fig.add_trace(go.Scatter(
            x=iones_x, y=vals_y,
            mode='lines+markers',
            name=id_m,
            line=dict(color=color_linea, width=2.0),
            marker=dict(size=7, color=color_linea),
            hovertext=hover_txt,
            hoverinfo='text'
        ))

    fig.update_layout(
        title="<b>Diagrama Semilogarítmico de Schöeller-Berkaloff</b>",
        xaxis=dict(title="Iones Mayores", showgrid=True, gridcolor='#e2e8f0'),
        yaxis=dict(title="Concentración (meq/L)", type="log", showgrid=True, gridcolor='#e2e8f0'),
        height=500,
        plot_bgcolor='white',
        paper_bgcolor='white',
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5)
    )
    return fig

# =============================================================================
# 8. DIAGRAMAS AGRÍCOLAS (WILCOX Y USSL RIVERSIDE)
# =============================================================================
def generar_diagrama_wilcox(df_procesado):
    """
    Diagrama de Wilcox: Conductividad Eléctrica (µS/cm) vs. % Sodio Soluble (%Na).
    Clasifica la aptitud del agua para riego en 5 categorías.
    """
    fig = go.Figure()

    # Polígonos de zonas de Wilcox
    # Excelente (< 250 µS/cm y < 20% Na)
    # Buena (250 - 750 µS/cm y 20 - 40% Na)
    # Permisible (750 - 2000 µS/cm y 40 - 60% Na)
    # Dudosa (2000 - 3000 µS/cm y 60 - 80% Na)
    # Inadecuada (> 3000 µS/cm o > 80% Na)

    # Curvas límite de Wilcox (parábolas estándar de Wilcox)
    ce_grid = np.linspace(50, 4000, 200)
    # Límite Excelente / Bueno
    y_exc = np.clip(100 - (ce_grid / 40.0), 20, 100)
    # Límite Bueno / Permisible
    y_bue = np.clip(100 - (ce_grid / 25.0), 10, 80)
    # Límite Permisible / Dudoso
    y_per = np.clip(100 - (ce_grid / 18.0), 5, 60)

    fig.add_trace(go.Scatter(x=ce_grid, y=y_exc, mode='lines', line=dict(color='#16a34a', width=1.5, dash='dash'), name='Límite Excelente/Bueno', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=ce_grid, y=y_bue, mode='lines', line=dict(color='#2563eb', width=1.5, dash='dash'), name='Límite Bueno/Permisible', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=ce_grid, y=y_per, mode='lines', line=dict(color='#d97706', width=1.5, dash='dash'), name='Límite Permisible/Dudoso', hoverinfo='skip'))

    # Puntos de Muestras
    colores = px.colors.qualitative.Dark24
    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        ce = float(r.get('CE_uS_cm', 0.0) if pd.notna(r.get('CE_uS_cm')) else (r.get('SDT_mg_L', 0.0) / 0.65))
        pct_na = float(r.get('Pct_Na_Riego', 0.0))
        ras = float(r.get('RAS', 0.0))
        color_pt = colores[idx % len(colores)]

        hover_txt = f"<b>{id_m}</b><br>CE: {ce:.0f} µS/cm<br>%Na: {pct_na:.1f}%<br>RAS: {ras:.2f}"

        fig.add_trace(go.Scatter(
            x=[ce], y=[pct_na], mode='markers',
            marker=dict(size=10, color=color_pt, line=dict(width=1, color='#0f172a')),
            name=id_m, hovertext=hover_txt, hoverinfo='text'
        ))

    fig.update_layout(
        title="<b>Diagrama de Wilcox - Aptitud de Agua Subterránea para Riego Agrícola</b>",
        xaxis=dict(title="Conductividad Eléctrica (µS/cm a 25 °C)", range=[0, 4200], showgrid=True, gridcolor='#e2e8f0'),
        yaxis=dict(title="Sodio Soluble (% Na)", range=[0, 100], showgrid=True, gridcolor='#e2e8f0'),
        height=500,
        plot_bgcolor='#fafafa',
        paper_bgcolor='white',
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5)
    )
    return fig

def generar_diagrama_riverside(df_procesado):
    """
    Diagrama de Riverside (USSL): Salinidad (C1-C4) vs. Peligro de Sodificación (S1-S4).
    """
    fig = go.Figure()

    # Zonas de Salinidad en X (CE en escala log)
    # C1: < 250, C2: 250 - 750, C3: 750 - 2250, C4: > 2250
    # Líneas divisorias de salinidad
    for ce_lim, label in [(250, "C1: Baja"), (750, "C2: Media"), (2250, "C3: Alta")]:
        fig.add_vline(x=ce_lim, line=dict(color="#cbd5e1", width=1.5, dash="dash"), annotation_text=label, annotation_position="top")

    # Curvas de Sodio en Y (RAS en función de CE según curvas estándar de Richards, 1954):
    # S1 límite: RAS = 1.88e-5 * CE + 10.0 (aprox)
    ce_arr = np.linspace(100, 5000, 100)
    ras_s1 = 10.0 - 0.001 * ce_arr
    ras_s2 = 18.0 - 0.0015 * ce_arr
    ras_s3 = 26.0 - 0.002 * ce_arr

    fig.add_trace(go.Scatter(x=ce_arr, y=ras_s1, mode='lines', line=dict(color='#16a34a', width=1.2, dash='dot'), name='Límite S1/S2 (Bajo/Medio)', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=ce_arr, y=ras_s2, mode='lines', line=dict(color='#d97706', width=1.2, dash='dot'), name='Límite S2/S3 (Medio/Alto)', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=ce_arr, y=ras_s3, mode='lines', line=dict(color='#dc2626', width=1.2, dash='dot'), name='Límite S3/S4 (Alto/Muy Alto)', hoverinfo='skip'))

    colores = px.colors.qualitative.Dark24
    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        ce = float(r.get('CE_uS_cm', 0.0) if pd.notna(r.get('CE_uS_cm')) else (r.get('SDT_mg_L', 0.0) / 0.65))
        ras = float(r.get('RAS', 0.0))
        color_pt = colores[idx % len(colores)]

        hover_txt = f"<b>{id_m}</b><br>CE: {ce:.0f} µS/cm<br>RAS: {ras:.2f}<br>Clasif: {r.get('Clasif_RAS', '')}"

        fig.add_trace(go.Scatter(
            x=[ce], y=[ras], mode='markers',
            marker=dict(size=10, color=color_pt, line=dict(width=1, color='#0f172a')),
            name=id_m, hovertext=hover_txt, hoverinfo='text'
        ))

    fig.update_layout(
        title="<b>Diagrama de Riverside (USSL) - Clasificación Salinidad (C) vs. Sodio (S)</b>",
        xaxis=dict(title="Conductividad Eléctrica (µS/cm)", type="log", range=[2, 4], showgrid=True, gridcolor='#e2e8f0'),
        yaxis=dict(title="Relación de Adsorción de Sodio (RAS / SAR)", range=[0, 32], showgrid=True, gridcolor='#e2e8f0'),
        height=500,
        plot_bgcolor='white',
        paper_bgcolor='white',
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5)
    )
    return fig

# =============================================================================
# 9. DIAGRAMA DE GIBBS (MECANISMOS GEOQUÍMICOS)
# =============================================================================
def generar_diagrama_gibbs(df_procesado):
    """
    Diagrama de Gibbs:
      Panel 1: Cationes [(Na+K)/(Na+K+Ca)] vs SDT (mg/L)
      Panel 2: Aniones [Cl/(Cl+HCO3)] vs SDT (mg/L)
      Identifica: Precipitación, Interacción Agua-Roca (Meteorización), Evaporación.
    """
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=1, cols=2, subplot_titles=["<b>Gibbs Cationes: (Na+K)/(Na+K+Ca)</b>", "<b>Gibbs Aniones: Cl/(Cl+HCO₃)</b>"])

    # Zonas de Gibbs estándar (forma de boomerang / bota)
    sdt_vals = np.logspace(1, 4, 100)

    # Cajas referenciales de Gibbs
    for col_i in [1, 2]:
        # Zona Precipitación (SDT bajo 10-50, relación alta)
        fig.add_shape(type="rect", x0=0.5, y0=10, x1=1.0, y1=80, fillcolor="rgba(59, 130, 246, 0.15)", line=dict(width=0), row=1, col=col_i)
        fig.add_annotation(x=0.75, y=30, text="Dominancia de<br>Precipitación (Lluvia)", showarrow=False, font=dict(size=9.5, color="#1d4ed8"), row=1, col=col_i)

        # Zona Interacción Agua-Roca (SDT 100-1000, relación baja/media)
        fig.add_shape(type="rect", x0=0.05, y0=100, x1=0.55, y1=1000, fillcolor="rgba(34, 197, 94, 0.15)", line=dict(width=0), row=1, col=col_i)
        fig.add_annotation(x=0.30, y=350, text="Dominancia de<br>Interacción Agua-Roca", showarrow=False, font=dict(size=9.5, color="#15803d"), row=1, col=col_i)

        # Zona Evaporación (SDT > 1000, relación alta)
        fig.add_shape(type="rect", x0=0.55, y0=1000, x1=1.0, y1=10000, fillcolor="rgba(239, 68, 68, 0.15)", line=dict(width=0), row=1, col=col_i)
        fig.add_annotation(x=0.78, y=3500, text="Dominancia de<br>Evaporación / Salinidad", showarrow=False, font=dict(size=9.5, color="#b91c1c"), row=1, col=col_i)

    colores = px.colors.qualitative.Dark24
    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        sdt = float(r.get('SDT_mg_L', 100.0) if pd.notna(r.get('SDT_mg_L')) else 100.0)
        sdt = max(10.0, sdt)
        g_cat = float(r.get('Gibbs_Cationes', np.nan))
        g_an = float(r.get('Gibbs_Aniones', np.nan))
        color_pt = colores[idx % len(colores)]

        if pd.notna(g_cat):
            fig.add_trace(go.Scatter(
                x=[g_cat], y=[sdt], mode='markers',
                marker=dict(size=9, color=color_pt, line=dict(width=1, color='#0f172a')),
                name=id_m, hovertext=f"<b>{id_m}</b><br>Gibbs Cat: {g_cat:.2f}<br>SDT: {sdt:,.0f} mg/L", hoverinfo='text',
                legendgroup=id_m, showlegend=True
            ), row=1, col=1)

        if pd.notna(g_an):
            fig.add_trace(go.Scatter(
                x=[g_an], y=[sdt], mode='markers',
                marker=dict(size=9, color=color_pt, line=dict(width=1, color='#0f172a')),
                hovertext=f"<b>{id_m}</b><br>Gibbs An: {g_an:.2f}<br>SDT: {sdt:,.0f} mg/L", hoverinfo='text',
                legendgroup=id_m, showlegend=False
            ), row=1, col=2)

    fig.update_xaxes(title="Relación Na⁺ / (Na⁺ + Ca²⁺)", range=[0, 1.0], row=1, col=1)
    fig.update_xaxes(title="Relación Cl⁻ / (Cl⁻ + HCO₃⁻)", range=[0, 1.0], row=1, col=2)
    fig.update_yaxes(title="Sólidos Disueltos Totales (SDT, mg/L)", type="log", range=[1, 4], row=1, col=1)
    fig.update_yaxes(type="log", range=[1, 4], row=1, col=2)

    fig.update_layout(
        title="<b>Diagramas de Gibbs - Identificación del Proceso Hidrogeoquímico Rector</b>",
        height=520,
        plot_bgcolor='white',
        paper_bgcolor='white',
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5)
    )
    return fig

# =============================================================================
# 10. GENERADOR DE PLANTILLA EXCEL OFICIAL (.XLSX)
# =============================================================================
def generar_plantilla_excel_hidroquimica():
    """
    Genera un archivo Excel normalizado en memoria con dos hojas:
      1. Muestras_Hidroquimicas (con encabezados, tipos y datos de ejemplo reales).
      2. Guia_Parametros_NOM127 (definición, LMP y métodos).
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_ejemplo = pd.DataFrame([
            {
                'Muestra': 'MAN-01_Pancho_Poza',
                'Tipo_Fuente': 'Manantial',
                'Fecha': '2026-10-07',
                'Latitud': 19.7485,
                'Longitud': -97.2452,
                'Elevacion_msnm': 1720.0,
                'pH': 7.42,
                'CE_uS_cm': 365.0,
                'SDT_mg_L': 235.0,
                'Dureza_mg_L': 185.0,
                'Ca_mg_L': 52.4,
                'Mg_mg_L': 13.2,
                'Na_mg_L': 14.8,
                'K_mg_L': 2.1,
                'HCO3_mg_L': 210.0,
                'CO3_mg_L': 0.0,
                'Cl_mg_L': 11.5,
                'SO4_mg_L': 18.0,
                'NO3_mg_L': 2.7,
                'F_mg_L': 0.35,
                'As_mg_L': 0.003,
                'Pb_mg_L': 0.002,
                'Fe_mg_L': 0.045,
                'Mn_mg_L': 0.012,
                'Zn_mg_L': 0.080,
                'E_Coli': 0.0
            },
            {
                'Muestra': 'MAN-02_Techocoapa',
                'Tipo_Fuente': 'Manantial',
                'Fecha': '2026-10-07',
                'Latitud': 19.7610,
                'Longitud': -97.2618,
                'Elevacion_msnm': 1680.0,
                'pH': 7.65,
                'CE_uS_cm': 240.0,
                'SDT_mg_L': 156.0,
                'Dureza_mg_L': 120.0,
                'Ca_mg_L': 34.0,
                'Mg_mg_L': 8.5,
                'Na_mg_L': 9.2,
                'K_mg_L': 1.5,
                'HCO3_mg_L': 142.0,
                'CO3_mg_L': 0.0,
                'Cl_mg_L': 7.8,
                'SO4_mg_L': 12.0,
                'NO3_mg_L': 1.9,
                'F_mg_L': 0.20,
                'As_mg_L': 0.002,
                'Pb_mg_L': 0.001,
                'Fe_mg_L': 0.020,
                'Mn_mg_L': 0.005,
                'Zn_mg_L': 0.040,
                'E_Coli': 0.0
            },
            {
                'Muestra': 'PZ-01_Jesus_Orozco',
                'Tipo_Fuente': 'Pozo Profundo',
                'Fecha': '2026-10-07',
                'Latitud': 19.7820,
                'Longitud': -97.2890,
                'Elevacion_msnm': 1610.0,
                'pH': 7.85,
                'CE_uS_cm': 720.0,
                'SDT_mg_L': 468.0,
                'Dureza_mg_L': 310.0,
                'Ca_mg_L': 84.0,
                'Mg_mg_L': 24.5,
                'Na_mg_L': 42.0,
                'K_mg_L': 5.2,
                'HCO3_mg_L': 295.0,
                'CO3_mg_L': 0.0,
                'Cl_mg_L': 38.0,
                'SO4_mg_L': 76.0,
                'NO3_mg_L': 8.4,
                'F_mg_L': 0.82,
                'As_mg_L': 0.012,  # Alerta NOM-127
                'Pb_mg_L': 0.004,
                'Fe_mg_L': 0.285,
                'Mn_mg_L': 0.040,
                'Zn_mg_L': 0.105,
                'E_Coli': 3.0  # No conforme microbiológico
            },
            {
                'Muestra': 'PZ-02_Agricola_Sur',
                'Tipo_Fuente': 'Pozo Profundo',
                'Fecha': '2026-10-08',
                'Latitud': 19.7315,
                'Longitud': -97.2105,
                'Elevacion_msnm': 1750.0,
                'pH': 7.20,
                'CE_uS_cm': 1250.0,
                'SDT_mg_L': 812.0,
                'Dureza_mg_L': 520.0,  # Excede dureza NOM-127
                'Ca_mg_L': 142.0,
                'Mg_mg_L': 40.5,
                'Na_mg_L': 88.0,
                'K_mg_L': 7.8,
                'HCO3_mg_L': 340.0,
                'CO3_mg_L': 0.0,
                'Cl_mg_L': 125.0,
                'SO4_mg_L': 220.0,
                'NO3_mg_L': 14.2,  # Excede nitratos
                'F_mg_L': 1.65,   # Excede fluoruros
                'As_mg_L': 0.015,  # Excede arsénico
                'Pb_mg_L': 0.008,
                'Fe_mg_L': 0.420,  # Excede hierro
                'Mn_mg_L': 0.180,  # Excede manganeso
                'Zn_mg_L': 0.350,
                'E_Coli': 0.0
            }
        ])
        df_ejemplo.to_excel(writer, sheet_name='Muestras_Hidroquimicas', index=False)

        # Hoja de Guía y Parámetros
        guia_data = []
        for k, v in LIMITES_NOM_127_2021.items():
            guia_data.append({
                'Columna_Excel': f"{k}_mg_L" if k not in ['pH_min', 'pH_max', 'SDT', 'Dureza', 'Color', 'Turbiedad', 'E_Coli', 'Coliformes'] else k,
                'Parametro': v['nombre'],
                'Categoria': v['categoria'],
                'LMP_NOM_127_2021': v['lmp'],
                'Unidades': v['unidad'],
                'Criterio': "Máximo Permisible" if v['tipo'] == 'max' else "Mínimo"
            })
        df_guia = pd.DataFrame(guia_data)
        df_guia.to_excel(writer, sheet_name='Guia_Parametros_NOM127', index=False)

    return output.getvalue()


# =============================================================================
# 11. EXPORTACIÓN PERICIAL: KMZ, SHAPEFILE Y LIBRO EXCEL
# =============================================================================
def generar_kmz_hidrogeoquimico(df_procesado, df_auditoria=None, clave_ac="Acuifero", nom_ac="Acuífero Oficial", geojson_delim=None):
    """
    Genera un archivo KMZ completo para Google Earth Móvil y Desktop:
      - LookAt automático centrado en el acuífero.
      - Puntos 3D con clamping al terreno y simbología doble (Facies y NOM-127).
      - Popups interactivos con tabla HTML de análisis de laboratorio.
      - Polígono perimetral del acuífero oficial (si se suministra).
    """
    if df_procesado is None or df_procesado.empty:
        return b""

    df_geo = df_procesado.dropna(subset=['Latitud', 'Longitud']).copy()
    if df_geo.empty:
        return b""

    c_lat = float(df_geo['Latitud'].mean())
    c_lon = float(df_geo['Longitud'].mean())

    lat_min, lat_max = df_geo['Latitud'].min(), df_geo['Latitud'].max()
    lon_min, lon_max = df_geo['Longitud'].min(), df_geo['Longitud'].max()
    diag_km = math.sqrt((lat_max - lat_min)**2 + (lon_max - lon_min)**2) * 111.0
    alt_range = max(14000, int(diag_km * 2500))

    if 'Estatus_NOM127' not in df_geo.columns and df_auditoria is not None and not df_auditoria.empty:
        df_geo = df_geo.merge(df_auditoria[['Muestra', 'Estatus_NOM127', 'Parametros_Excedidos', 'Parametros_Alerta']], on='Muestra', how='left')

    kml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '<Document>',
        f'  <name>Auditoría Hidrogeoquímica - {html.escape(str(nom_ac))} ({clave_ac})</name>',
        '  <open>1</open>',
        '  <LookAt>',
        f'    <longitude>{c_lon:.6f}</longitude>',
        f'    <latitude>{c_lat:.6f}</latitude>',
        '    <altitude>0</altitude>',
        '    <heading>0</heading>',
        '    <tilt>20</tilt>',
        f'    <range>{alt_range}</range>',
        '    <altitudeMode>clampToGround</altitudeMode>',
        '  </LookAt>',
        '  <Style id="est-conf"><IconStyle><scale>0.9</scale><color>ff34a853</color><Icon><href>https://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>',
        '  <Style id="est-alert"><IconStyle><scale>0.9</scale><color>ff00a5ff</color><Icon><href>https://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>',
        '  <Style id="est-noconf"><IconStyle><scale>1.0</scale><color>ff2222b0</color><Icon><href>https://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>',
        '  <Style id="est-bic-ca"><IconStyle><scale>0.9</scale><color>ffd35400</color><Icon><href>https://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>',
        '  <Style id="est-clor-na"><IconStyle><scale>0.9</scale><color>ff1665d9</color><Icon><href>https://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>',
        '  <Style id="est-fac-gral"><IconStyle><scale>0.85</scale><color>ff7e3af2</color><Icon><href>https://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>'
    ]

    # Polígono oficial
    if geojson_delim and 'geometry' in geojson_delim:
        geom = geojson_delim['geometry']
        kml.append('  <Folder><name>1. Límite Oficial del Acuífero</name>')
        kml.append('    <Placemark>')
        kml.append(f'      <name>Polígono Oficial ({clave_ac})</name>')
        kml.append('      <Style><LineStyle><color>ff321c69</color><width>2.5</width></LineStyle><PolyStyle><color>22321c69</color><fill>1</fill><outline>1</outline></PolyStyle></Style>')
        if geom['type'] == 'Polygon':
            coords_str = " ".join([f"{c[0]},{c[1]},0" for c in geom['coordinates'][0]])
            kml.append(f'      <Polygon><altitudeMode>clampToGround</altitudeMode><outerBoundaryIs><LinearRing><coordinates>{coords_str}</coordinates></LinearRing></outerBoundaryIs></Polygon>')
        elif geom['type'] == 'MultiPolygon':
            kml.append('      <MultiGeometry>')
            for poly in geom['coordinates']:
                coords_str = " ".join([f"{c[0]},{c[1]},0" for c in poly[0]])
                kml.append(f'        <Polygon><altitudeMode>clampToGround</altitudeMode><outerBoundaryIs><LinearRing><coordinates>{coords_str}</coordinates></LinearRing></outerBoundaryIs></Polygon>')
            kml.append('      </MultiGeometry>')
        kml.append('    </Placemark>')
        kml.append('  </Folder>')

    # Carpeta Facies
    kml.append('  <Folder><name>2. Muestras por Facies Hidroquímica (Piper)</name>')
    for _, r in df_geo.iterrows():
        id_m = html.escape(str(r.get('Muestra', 'Muestra')))
        facies = str(r.get('Facies_Piper', 'N/D'))
        lat = float(r['Latitud'])
        lon = float(r['Longitud'])
        s_id = "#est-bic-ca" if "Bicarbonatada Cálcica" in facies else ("#est-clor-na" if "Clorurada Sódica" in facies else "#est-fac-gral")

        desc = f"""<![CDATA[
        <div style="font-family: Arial, sans-serif; font-size: 12px; color: #1e293b; max-width: 320px;">
          <div style="background: #691C32; color: white; padding: 6px 10px; font-weight: bold; border-radius: 4px 4px 0 0;">
            🧪 {id_m} ({r.get('Tipo_Fuente', 'Captación')})
          </div>
          <div style="padding: 8px; border: 1px solid #cbd5e1; border-top: none; background: #ffffff;">
            <b>Facies Piper:</b> <span style="color:#691C32; font-weight:bold;">{facies}</span><br>
            <b>Balance Iónico (CBE):</b> {r.get('CBE_pct', 0.0):+.2f}% ({r.get('CBE_Calidad', '')})<br>
            <b>SDT:</b> {r.get('SDT_mg_L', 0):,.1f} mg/L | <b>CE:</b> {r.get('CE_uS_cm', 0):,.0f} µS/cm<br>
            <b>Dureza Total:</b> {r.get('Dureza_mg_L', 0):,.1f} mg/L CaCO₃<br>
            <hr style="border:0; border-top:1px dashed #cbd5e1; margin:6px 0;">
            <b>Cationes (mg/L):</b> Ca={r.get('Ca_mg_L', 0):.1f}, Mg={r.get('Mg_mg_L', 0):.1f}, Na={r.get('Na_mg_L', 0):.1f}, K={r.get('K_mg_L', 0):.1f}<br>
            <b>Aniones (mg/L):</b> HCO₃={r.get('HCO3_mg_L', 0):.1f}, Cl={r.get('Cl_mg_L', 0):.1f}, SO₄={r.get('SO4_mg_L', 0):.1f}<br>
            <hr style="border:0; border-top:1px dashed #cbd5e1; margin:6px 0;">
            <b>Riego:</b> RAS={r.get('RAS', 0):.2f} ({r.get('Clasif_RAS', '')}) | CSR={r.get('CSR', 0):+.2f} meq/L
          </div>
        </div>
        ]]>"""

        kml.append('    <Placemark>')
        kml.append(f'      <name>{id_m} - {html.escape(facies)}</name>')
        kml.append(f'      <styleUrl>{s_id}</styleUrl>')
        kml.append(f'      <description>{desc}</description>')
        kml.append(f'      <Point><altitudeMode>clampToGround</altitudeMode><coordinates>{lon:.6f},{lat:.6f},0</coordinates></Point>')
        kml.append('    </Placemark>')
    kml.append('  </Folder>')

    # Carpeta NOM-127
    kml.append('  <Folder><name>3. Semáforo Normativo NOM-127-SSA1-2021</name>')
    for _, r in df_geo.iterrows():
        id_m = html.escape(str(r.get('Muestra', 'Muestra')))
        estatus = str(r.get('Estatus_NOM127', 'N/D'))
        exc = str(r.get('Parametros_Excedidos', 'Ninguno'))
        lat = float(r['Latitud'])
        lon = float(r['Longitud'])

        if "No Conforme" in estatus:
            s_id = "#est-noconf"
            color_badge = "#991b1b"
        elif "Alerta" in estatus:
            s_id = "#est-alert"
            color_badge = "#b45309"
        else:
            s_id = "#est-conf"
            color_badge = "#166534"

        desc = f"""<![CDATA[
        <div style="font-family: Arial, sans-serif; font-size: 12px; color: #1e293b; max-width: 320px;">
          <div style="background: {color_badge}; color: white; padding: 6px 10px; font-weight: bold; border-radius: 4px 4px 0 0;">
            🚨 {id_m} - Dictamen NOM-127-SSA1-2021
          </div>
          <div style="padding: 8px; border: 1px solid #cbd5e1; border-top: none; background: #ffffff;">
            <b>Dictamen Sanitario:</b> <span style="color:{color_badge}; font-weight:bold;">{estatus}</span><br>
            <b>Parámetros Fuera de Norma:</b> <span style="color:#b91c1c;">{exc}</span><br>
            <hr style="border:0; border-top:1px dashed #cbd5e1; margin:6px 0;">
            <b>Arsénico:</b> {r.get('As_mg_L', 0):.4f} mg/L (LMP 0.010)<br>
            <b>Fluoruros:</b> {r.get('F_mg_L', 0):.2f} mg/L (LMP 1.5)<br>
            <b>Hierro:</b> {r.get('Fe_mg_L', 0):.3f} mg/L (LMP 0.300)<br>
            <b>E. coli:</b> {r.get('E_Coli', 0)} NMP/100 mL (LMP 0)<br>
          </div>
        </div>
        ]]>"""

        kml.append('    <Placemark>')
        kml.append(f'      <name>{id_m} - {html.escape(estatus)}</name>')
        kml.append(f'      <styleUrl>{s_id}</styleUrl>')
        kml.append(f'      <description>{desc}</description>')
        kml.append(f'      <Point><altitudeMode>clampToGround</altitudeMode><coordinates>{lon:.6f},{lat:.6f},0</coordinates></Point>')
        kml.append('    </Placemark>')
    kml.append('  </Folder>')

    kml.append('</Document>')
    kml.append('</kml>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('doc.kml', "\n".join(kml).encode('utf-8'))
    buf.seek(0)
    return buf.getvalue()


def generar_shapefile_hidrogeoquimico(df_procesado, df_auditoria=None, nombre_base="muestras_hidroquimicas"):
    """
    Genera un archivo Shapefile (.zip) con geometría puntual y tabla de atributos completa.
    """
    import tempfile
    import zipfile
    import os
    import shutil
    import geopandas as gpd
    from shapely.geometry import Point

    if df_procesado is None or df_procesado.empty:
        return b""

    df_geo = df_procesado.dropna(subset=['Latitud', 'Longitud']).copy()
    if df_geo.empty:
        return b""

    if df_auditoria is not None and not df_auditoria.empty and 'Estatus_NOM127' not in df_geo.columns:
        df_geo = df_geo.merge(df_auditoria[['Muestra', 'Estatus_NOM127', 'Parametros_Excedidos']], on='Muestra', how='left')

    rename_dbf = {
        'Muestra': 'MUESTRA',
        'Tipo_Fuente': 'TIPO_FUEN',
        'Fecha': 'FECHA',
        'Latitud': 'LATITUD',
        'Longitud': 'LONGITUD',
        'Elevacion': 'ELEV_MSNM',
        'pH': 'PH',
        'CE_uS_cm': 'CE_US_CM',
        'SDT_mg_L': 'SDT_MG_L',
        'Dureza_mg_L': 'DUREZA_MG',
        'Ca_mg_L': 'CA_MG_L',
        'Mg_mg_L': 'MG_MG_L',
        'Na_mg_L': 'NA_MG_L',
        'K_mg_L': 'K_MG_L',
        'HCO3_mg_L': 'HCO3_MG_L',
        'CO3_mg_L': 'CO3_MG_L',
        'Cl_mg_L': 'CL_MG_L',
        'SO4_mg_L': 'SO4_MG_L',
        'NO3_mg_L': 'NO3_MG_L',
        'F_mg_L': 'F_MG_L',
        'As_mg_L': 'AS_MG_L',
        'Pb_mg_L': 'PB_MG_L',
        'Fe_mg_L': 'FE_MG_L',
        'Mn_mg_L': 'MN_MG_L',
        'Zn_mg_L': 'ZN_MG_L',
        'E_Coli': 'E_COLI',
        'Suma_Cationes_meq': 'SUM_CAT_ME',
        'Suma_Aniones_meq': 'SUM_ANI_ME',
        'CBE_pct': 'CBE_PCT',
        'CBE_Calidad': 'CBE_CALID',
        'Facies_Piper': 'FACIES_PIP',
        'RAS': 'RAS_SAR',
        'Clasif_RAS': 'CLASIF_RAS',
        'Pct_Na_Riego': 'PCT_NA_RIE',
        'CSR': 'CSR_MEQ_L',
        'Clasif_CSR': 'CLASIF_CSR',
        'Gibbs_Cationes': 'GIBBS_CAT',
        'Gibbs_Aniones': 'GIBBS_ANI',
        'rNa_rCl': 'R_NA_CL',
        'rCa_rSO4': 'R_CA_SO4',
        'Indice_Revelle': 'IND_REVELL',
        'Clasif_Revelle': 'CLAS_REVEL',
        'Estatus_NOM127': 'NOM127_EST',
        'Parametros_Excedidos': 'NOM127_EXC'
    }

    cols_to_keep = [c for c in df_geo.columns if c in rename_dbf]
    df_dbf = df_geo[cols_to_keep].copy().rename(columns=rename_dbf)

    for col in df_dbf.select_dtypes(include='object').columns:
        df_dbf[col] = df_dbf[col].astype(str).str.slice(0, 250)

    geometrias = [Point(xy) for xy in zip(df_geo['Longitud'], df_geo['Latitud'])]
    gdf = gpd.GeoDataFrame(df_dbf, geometry=geometrias, crs="EPSG:4326")

    temp_dir = tempfile.mkdtemp()
    shp_base = os.path.join(temp_dir, f"{nombre_base}")
    shp_file = f"{shp_base}.shp"
    gdf.to_file(shp_file, driver='ESRI Shapefile', encoding='utf-8')

    buf_zip = io.BytesIO()
    with zipfile.ZipFile(buf_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(temp_dir):
            full_p = os.path.join(temp_dir, fname)
            zf.write(full_p, arcname=fname)

    buf_zip.seek(0)
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass
    return buf_zip.getvalue()


def generar_reporte_excel_hidrogeoquimico(df_procesado, df_auditoria=None, clave_ac="Acuifero", nom_ac="Acuífero Oficial"):
    """
    Genera un libro técnico Excel (.xlsx) estructurado en 5 hojas analíticas.
    """
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        if df_auditoria is not None and not df_auditoria.empty:
            df_auditoria.to_excel(writer, sheet_name='Auditoria_NOM127', index=False)
        df_procesado.to_excel(writer, sheet_name='Resultados_Completos', index=False)

        cols_meq = ['Muestra', 'Tipo_Fuente', 'Facies_Piper', 'CBE_pct', 'CBE_Calidad',
                    'Ca_meq_L', 'Mg_meq_L', 'Na_meq_L', 'K_meq_L', 'Suma_Cationes_meq',
                    'HCO3_meq_L', 'CO3_meq_L', 'Cl_meq_L', 'SO4_meq_L', 'NO3_meq_L', 'Suma_Aniones_meq']
        c_meq_pres = [c for c in cols_meq if c in df_procesado.columns]
        df_procesado[c_meq_pres].to_excel(writer, sheet_name='Concentraciones_meq_L', index=False)

        cols_riego = ['Muestra', 'Tipo_Fuente', 'CE_uS_cm', 'SDT_mg_L', 'RAS', 'Clasif_RAS', 'Pct_Na_Riego', 'CSR', 'Clasif_CSR']
        c_r_pres = [c for c in cols_riego if c in df_procesado.columns]
        df_procesado[c_r_pres].to_excel(writer, sheet_name='Aptitud_Riego_Agricola', index=False)

        cols_geoq = ['Muestra', 'Tipo_Fuente', 'rNa_rCl', 'rCa_rSO4', 'rCaMg_rHCO3', 'rMg_rCa', 'Indice_Revelle', 'Clasif_Revelle', 'Gibbs_Cationes', 'Gibbs_Aniones']
        c_g_pres = [c for c in cols_geoq if c in df_procesado.columns]
        df_procesado[c_g_pres].to_excel(writer, sheet_name='Geoquimica_Relaciones', index=False)

    return out.getvalue()
