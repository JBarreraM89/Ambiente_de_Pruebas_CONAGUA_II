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
    'Ca_mg_L': ['CA', 'CALCIO', 'CA_MG_L', 'CA2', 'CA_DISUELTO', 'CALCIO_TOTAL', 'CA_MEQ', 'CA_MEQ_L'],
    'Mg_mg_L': ['MG', 'MAGNESIO', 'MG_MG_L', 'MG2', 'MG_DISUELTO', 'MAGNESIO_TOTAL', 'MG_MEQ', 'MG_MEQ_L'],
    'Na_mg_L': ['NA', 'SODIO', 'NA_MG_L', 'NA1', 'NA_DISUELTO', 'SODIO_TOTAL', 'NA_MEQ', 'NA_MEQ_L'],
    'K_mg_L':  ['K', 'POTASIO', 'K_MG_L', 'K1', 'K_DISUELTO', 'POTASIO_TOTAL', 'K_MEQ', 'K_MEQ_L'],
    'Na_K_meq_L': ['NA_K', 'NA+K', 'NA_MAS_K', 'SODIO_POTASIO', 'NAK'],
    # Aniones
    'HCO3_mg_L': ['HCO3', 'BICARBONATOS', 'BICARBONATO', 'HCO3_MG_L', 'ALCALINIDAD_HCO3', 'ALC_HCO3', 'HCO3_MEQ', 'HCO3_MEQ_L'],
    'CO3_mg_L':  ['CO3', 'CARBONATOS', 'CARBONATO', 'CO3_MG_L', 'ALCALINIDAD_CO3', 'CO3_MEQ', 'CO3_MEQ_L'],
    'HCO3_CO3_meq_L': ['HCO3_CO3', 'HCO3+CO3', 'BICARBONATO_CARBONATO', 'ALCALINIDAD_TOTAL'],
    'Cl_mg_L':   ['CL', 'CLORUROS', 'CLORURO', 'CL_MG_L', 'CHLORIDE', 'CL_MEQ', 'CL_MEQ_L'],
    'SO4_mg_L':  ['SO4', 'SULFATOS', 'SULFATO', 'SO4_MG_L', 'SULFATE', 'SO4_MEQ', 'SO4_MEQ_L'],
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

def parse_concatenated_csv(raw_text):
    """
    Detecta y fusiona tablas hidroquimicas concatenadas en un mismo archivo de texto/CSV
    (por ejemplo, cuando se exporta una tabla de cationes/aniones combinados y otra con el desglose de Na, K, HCO3, CO3).
    """
    if not raw_text or not raw_text.strip():
        return pd.DataFrame()

    lines = [l.strip() for l in raw_text.strip().splitlines() if l.strip()]
    if not lines:
        return pd.DataFrame()

    header_indices = []
    for idx, line in enumerate(lines):
        parts = [p.strip() for p in line.split(',')]
        matches = [p for p in parts if any(k in p.upper() for k in ['CA', 'NA', 'K', 'MG', 'CL', 'SO4', 'HCO3', 'CO3', 'ID'])]
        if len(matches) >= 3:
            header_indices.append(idx)

    if len(header_indices) <= 1:
        return pd.read_csv(io.StringIO(raw_text))

    dfs = []
    for i, h_idx in enumerate(header_indices):
        end_idx = header_indices[i + 1] if i + 1 < len(header_indices) else len(lines)
        table_lines = lines[h_idx:end_idx]
        df_sub = pd.read_csv(io.StringIO('\n'.join(table_lines)))
        dfs.append(df_sub)

    if len(dfs) == 2 and len(dfs[0]) == len(dfs[1]):
        df_merged = dfs[0].copy()
        for col in dfs[1].columns:
            clean_col = col.strip()
            if clean_col not in df_merged.columns:
                df_merged[clean_col] = dfs[1][col].values
        return df_merged

    return dfs[0]


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
def procesar_muestras_hidroquimicas(df_muestras, unidad_forzada=None):
    """
    Calcula meq/L, suma de cationes/aniones, error de balance iónico (% CBE),
    facies de Piper, índices de riego (RAS, %Na, CSR) y coordenadas de Gibbs.
    Detecta automáticamente si los datos vienen en meq/L o mg/L.
    """
    if df_muestras is None or df_muestras.empty:
        return pd.DataFrame()

    df = df_muestras.copy()

    # Detección inteligente de unidades (meq/L vs mg/L)
    es_meq = False
    if unidad_forzada == 'meq_L':
        es_meq = True
    elif unidad_forzada == 'mg_L':
        es_meq = False
    else:
        # Si los iones mayores tienen percentil 75 < 20 y mediana < 10, están en meq/L
        cols_iones = [f"{ion}_mg_L" for ion in ['Ca', 'Mg', 'Na', 'Cl', 'HCO3', 'SO4'] if f"{ion}_mg_L" in df.columns]
        if cols_iones:
            vals = []
            for c in cols_iones:
                v = pd.to_numeric(df[c], errors='coerce').dropna()
                if len(v) > 0: vals.extend(v.tolist())
            if vals and np.percentile(vals, 75) < 20.0 and np.median(vals) < 10.0:
                es_meq = True

    # 1. Conversión de concentraciones
    for ion, datos in PESOS_EQUIVALENTES.items():
        col_mg = f"{ion}_mg_L"
        col_meq = f"{ion}_meq_L"
        if es_meq:
            if col_mg in df.columns:
                df[col_meq] = pd.to_numeric(df[col_mg], errors='coerce').fillna(0.0)
                df[col_mg] = df[col_meq] * datos['eq_wt']
            else:
                df[col_meq] = 0.0
                df[col_mg] = 0.0
        else:
            if col_mg in df.columns:
                df[col_meq] = pd.to_numeric(df[col_mg], errors='coerce').fillna(0.0) / datos['eq_wt']
            else:
                df[col_meq] = 0.0

    # Soporte para Na+K consolidado si no hay Na o K separados
    if ('Na_meq_L' not in df.columns or df['Na_meq_L'].sum() == 0) and 'Na_K_meq_L' in df.columns:
        nak = pd.to_numeric(df['Na_K_meq_L'], errors='coerce').fillna(0.0)
        df['Na_meq_L'] = nak * 0.90
        df['K_meq_L'] = nak * 0.10
        df['Na_mg_L'] = df['Na_meq_L'] * PESOS_EQUIVALENTES['Na']['eq_wt']
        df['K_mg_L'] = df['K_meq_L'] * PESOS_EQUIVALENTES['K']['eq_wt']

    # Soporte para HCO3+CO3 consolidado si no hay HCO3 o CO3 separados
    if ('HCO3_meq_L' not in df.columns or df['HCO3_meq_L'].sum() == 0) and 'HCO3_CO3_meq_L' in df.columns:
        hco3_co3 = pd.to_numeric(df['HCO3_CO3_meq_L'], errors='coerce').fillna(0.0)
        df['HCO3_meq_L'] = hco3_co3
        df['CO3_meq_L'] = 0.0
        df['HCO3_mg_L'] = df['HCO3_meq_L'] * PESOS_EQUIVALENTES['HCO3']['eq_wt']
        df['CO3_mg_L'] = 0.0

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
    df['Suma_Aniones_meq'] = df['HCO3_meq_L'] + df['CO3_meq_L'] + df['Cl_meq_L'] + df['SO4_meq_L'] + (df['NO3_meq_L'] if 'NO3_meq_L' in df.columns else 0.0)

    # Estimaciones físicas si no se reportaron CE o SDT (para diagramas de Wilcox, Riverside y Gibbs)
    if 'CE_uS_cm' not in df.columns or df['CE_uS_cm'].isna().all() or (df['CE_uS_cm'] == 0).all():
        df['CE_uS_cm'] = np.where(df['Suma_Aniones_meq'] > 0, (df['Suma_Aniones_meq'] * 100.0).round(1), 250.0)
    if 'SDT_mg_L' not in df.columns or df['SDT_mg_L'].isna().all() or (df['SDT_mg_L'] == 0).all():
        df['SDT_mg_L'] = (df['CE_uS_cm'] * 0.65).round(1)
    if 'pH' not in df.columns or df['pH'].isna().all():
        df['pH'] = 7.5

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
    Construye un Diagrama Trilineal de Piper de alta definición (OMM / UNESCO):
      - Triángulo de Cationes (izquierda) con rejilla ternaria completa cada 20%.
      - Triángulo de Aniones (derecha) con rejilla ternaria completa cada 20%.
      - Diamante Central (rombo equilátero real) con los 4 campos hidrogeoquímicos sombreados.
      - Ticks numéricos exteriores limpios (20, 40, 60, 80) y etiquetas de vértices.
      - Puntos de muestras de alta visibilidad con halo de contraste y líneas trilineales.
    """
    fig = go.Figure()

    h_tri = math.sqrt(3) / 2.0  # 0.866025
    x_gap = 0.45
    x_cat_orig = 0.0
    x_an_orig = 1.0 + x_gap  # 1.45

    # Vértices del Diamante Central (Rombo Equilátero de lados L=1.0)
    # Altura vertical del rombo = 2 * h_tri = 1.73205
    x_diam_bot, y_diam_bot = 1.225, h_tri
    x_diam_left, y_diam_left = 0.725, 2.0 * h_tri
    x_diam_right, y_diam_right = 1.725, 2.0 * h_tri
    x_diam_top, y_diam_top = 1.225, 3.0 * h_tri
    x_center, y_center = 1.225, 2.0 * h_tri

    # Puntos medios de las aristas del Diamante
    x_m_bl, y_m_bl = (x_diam_bot + x_diam_left) / 2.0, 1.5 * h_tri
    x_m_br, y_m_br = (x_diam_bot + x_diam_right) / 2.0, 1.5 * h_tri
    x_m_tl, y_m_tl = (x_diam_left + x_diam_top) / 2.0, 2.5 * h_tri
    x_m_tr, y_m_tr = (x_diam_right + x_diam_top) / 2.0, 2.5 * h_tri

    # 1. Sombreado de los 4 Cuadrantes del Diamante Central
    # Cuadrante Sur: Bicarbonatada Cálcica/Magnésica (Recarga de Montaña)
    fig.add_trace(go.Scatter(
        x=[x_diam_bot, x_m_bl, x_center, x_m_br, x_diam_bot],
        y=[y_diam_bot, y_m_bl, y_center, y_m_br, y_diam_bot],
        fill='toself', fillcolor='rgba(2, 132, 199, 0.08)', line=dict(width=0),
        hoverinfo='skip', showlegend=False
    ))
    # Cuadrante Norte: Clorurada Sódica (Salina Marina / Profunda)
    fig.add_trace(go.Scatter(
        x=[x_center, x_m_tl, x_diam_top, x_m_tr, x_center],
        y=[y_center, y_m_tl, y_diam_top, y_m_tr, y_center],
        fill='toself', fillcolor='rgba(220, 38, 38, 0.08)', line=dict(width=0),
        hoverinfo='skip', showlegend=False
    ))
    # Cuadrante Oeste: Bicarbonatada Sódica (Intercambio Catiónico / Ablandamiento)
    fig.add_trace(go.Scatter(
        x=[x_m_bl, x_diam_left, x_m_tl, x_center, x_m_bl],
        y=[y_m_bl, y_diam_left, y_m_tl, y_center, y_m_bl],
        fill='toself', fillcolor='rgba(124, 58, 237, 0.08)', line=dict(width=0),
        hoverinfo='skip', showlegend=False
    ))
    # Cuadrante Este: Sulfatada / Clorurada Cálcica (Disolución de Yeso)
    fig.add_trace(go.Scatter(
        x=[x_m_br, x_center, x_m_tr, x_diam_right, x_m_br],
        y=[y_m_br, y_center, y_m_tr, y_diam_right, y_m_br],
        fill='toself', fillcolor='rgba(217, 119, 6, 0.08)', line=dict(width=0),
        hoverinfo='skip', showlegend=False
    ))

    # 2. Rejilla Ternaria Completa en Triángulo de Cationes (cada 20%)
    for pct in [0.2, 0.4, 0.6, 0.8]:
        # Horizontales (Mg constante)
        y_h = pct * h_tri
        x1_h = x_cat_orig + pct * 0.5
        x2_h = x_cat_orig + 1.0 - pct * 0.5
        fig.add_trace(go.Scatter(x=[x1_h, x2_h], y=[y_h, y_h], mode='lines', line=dict(color='#e2e8f0', width=0.8), hoverinfo='skip', showlegend=False))
        # A 60° (Na+K constante)
        fig.add_trace(go.Scatter(x=[x_cat_orig + pct, x_cat_orig + 0.5 + 0.5 * pct], y=[0.0, h_tri * (1.0 - pct)], mode='lines', line=dict(color='#e2e8f0', width=0.8), hoverinfo='skip', showlegend=False))
        # A 120° (Ca constante)
        fig.add_trace(go.Scatter(x=[x_cat_orig + 1.0 - pct, x_cat_orig + 0.5 - 0.5 * pct], y=[0.0, h_tri * (1.0 - pct)], mode='lines', line=dict(color='#e2e8f0', width=0.8), hoverinfo='skip', showlegend=False))

    # 3. Rejilla Ternaria Completa en Triángulo de Aniones (cada 20%)
    for pct in [0.2, 0.4, 0.6, 0.8]:
        # Horizontales (SO4 constante)
        y_h = pct * h_tri
        x1_h = x_an_orig + pct * 0.5
        x2_h = x_an_orig + 1.0 - pct * 0.5
        fig.add_trace(go.Scatter(x=[x1_h, x2_h], y=[y_h, y_h], mode='lines', line=dict(color='#e2e8f0', width=0.8), hoverinfo='skip', showlegend=False))
        # A 60° (Cl constante)
        fig.add_trace(go.Scatter(x=[x_an_orig + pct, x_an_orig + 0.5 + 0.5 * pct], y=[0.0, h_tri * (1.0 - pct)], mode='lines', line=dict(color='#e2e8f0', width=0.8), hoverinfo='skip', showlegend=False))
        # A 120° (HCO3 constante)
        fig.add_trace(go.Scatter(x=[x_an_orig + 1.0 - pct, x_an_orig + 0.5 - 0.5 * pct], y=[0.0, h_tri * (1.0 - pct)], mode='lines', line=dict(color='#e2e8f0', width=0.8), hoverinfo='skip', showlegend=False))

    # 4. Rejilla Interna en Diamante Central (cada 20%)
    for pct in [0.2, 0.4, 0.6, 0.8]:
        # Paralelas a arista inferior-izquierda (hacia superior-derecha)
        x1_d = x_diam_bot + pct * (x_diam_right - x_diam_bot)
        y1_d = y_diam_bot + pct * (y_diam_right - y_diam_bot)
        x2_d = x_diam_left + pct * (x_diam_top - x_diam_left)
        y2_d = y_diam_left + pct * (y_diam_top - y_diam_left)
        fig.add_trace(go.Scatter(x=[x1_d, x2_d], y=[y1_d, y2_d], mode='lines', line=dict(color='#e2e8f0', width=0.8), hoverinfo='skip', showlegend=False))
        # Paralelas a arista inferior-derecha (hacia superior-izquierda)
        x3_d = x_diam_bot + pct * (x_diam_left - x_diam_bot)
        y3_d = y_diam_bot + pct * (y_diam_left - y_diam_bot)
        x4_d = x_diam_right + pct * (x_diam_top - x_diam_right)
        y4_d = y_diam_right + pct * (y_diam_top - y_diam_right)
        fig.add_trace(go.Scatter(x=[x3_d, x4_d], y=[y3_d, y4_d], mode='lines', line=dict(color='#e2e8f0', width=0.8), hoverinfo='skip', showlegend=False))

    # 5. Bordes Perimetrales Estructurales
    # Triángulo Cationes
    fig.add_trace(go.Scatter(
        x=[x_cat_orig, x_cat_orig + 1.0, x_cat_orig + 0.5, x_cat_orig],
        y=[0.0, 0.0, h_tri, 0.0],
        mode='lines', line=dict(color='#1e293b', width=2.2), hoverinfo='skip', showlegend=False
    ))
    # Triángulo Aniones
    fig.add_trace(go.Scatter(
        x=[x_an_orig, x_an_orig + 1.0, x_an_orig + 0.5, x_an_orig],
        y=[0.0, 0.0, h_tri, 0.0],
        mode='lines', line=dict(color='#1e293b', width=2.2), hoverinfo='skip', showlegend=False
    ))
    # Diamante Perímetro
    fig.add_trace(go.Scatter(
        x=[x_diam_bot, x_diam_right, x_diam_top, x_diam_left, x_diam_bot],
        y=[y_diam_bot, y_diam_right, y_diam_top, y_diam_left, y_diam_bot],
        mode='lines', line=dict(color='#1e293b', width=2.4), hoverinfo='skip', showlegend=False
    ))
    # Líneas divisorias medias del Diamante (50%)
    fig.add_trace(go.Scatter(x=[x_diam_left, x_diam_right], y=[y_diam_left, y_diam_right], mode='lines', line=dict(color='#64748b', width=1.1, dash='dash'), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scatter(x=[x_diam_bot, x_diam_top], y=[y_diam_bot, y_diam_top], mode='lines', line=dict(color='#64748b', width=1.1, dash='dash'), hoverinfo='skip', showlegend=False))

    # 6. Rotulación Pericial y Ticks Numéricos
    anotaciones = [
        # Vértices Cationes
        dict(x=x_cat_orig - 0.05, y=-0.05, text="<b>Ca²⁺</b>", showarrow=False, font=dict(color="#0f172a", size=13)),
        dict(x=x_cat_orig + 1.05, y=-0.05, text="<b>Na⁺+K⁺</b>", showarrow=False, font=dict(color="#0f172a", size=13)),
        dict(x=x_cat_orig + 0.5, y=h_tri + 0.06, text="<b>Mg²⁺</b>", showarrow=False, font=dict(color="#0f172a", size=13)),
        dict(x=x_cat_orig + 0.5, y=-0.11, text="<b>CATIONES (% meq/L)</b> →", showarrow=False, font=dict(color="#691C32", size=11.5)),
        # Vértices Aniones
        dict(x=x_an_orig - 0.05, y=-0.05, text="<b>HCO₃⁻+CO₃²⁻</b>", showarrow=False, font=dict(color="#0f172a", size=13)),
        dict(x=x_an_orig + 1.05, y=-0.05, text="<b>Cl⁻</b>", showarrow=False, font=dict(color="#0f172a", size=13)),
        dict(x=x_an_orig + 0.5, y=h_tri + 0.06, text="<b>SO₄²⁻</b>", showarrow=False, font=dict(color="#0f172a", size=13)),
        dict(x=x_an_orig + 0.5, y=-0.11, text="← <b>ANIONES (% meq/L)</b>", showarrow=False, font=dict(color="#691C32", size=11.5)),
        # Rotulación de Cuadrantes del Diamante
        dict(x=x_diam_bot, y=y_diam_bot - 0.06, text="<b>Bicarbonatada Cálcica</b><br><span style='font-size:9.5px;color:#166534;'>Aguas de Recarga Fresca</span>", showarrow=False, font=dict(color="#166534", size=11)),
        dict(x=x_diam_top, y=y_diam_top + 0.07, text="<b>Clorurada Sódica</b><br><span style='font-size:9.5px;color:#991b1b;'>Salina / Marina Profunda</span>", showarrow=False, font=dict(color="#991b1b", size=11)),
        dict(x=x_diam_left - 0.08, y=y_diam_left, text="<b>Bicarbonatada Sódica</b><br><span style='font-size:9px;color:#6b21a8;'>Intercambio Catiónico</span>", showarrow=False, font=dict(color="#6b21a8", size=10), textangle=-45),
        dict(x=x_diam_right + 0.08, y=y_diam_right, text="<b>Sulfatada Cálcica</b><br><span style='font-size:9px;color:#92400e;'>Disolución de Yeso</span>", showarrow=False, font=dict(color="#92400e", size=10), textangle=45),
    ]

    # Ticks numéricos discretos en bordes
    for pct, txt in [(0.2, "20"), (0.4, "40"), (0.6, "60"), (0.8, "80")]:
        anotaciones.append(dict(x=x_cat_orig + pct, y=-0.03, text=txt, showarrow=False, font=dict(color="#64748b", size=8.5)))
        anotaciones.append(dict(x=x_an_orig + pct, y=-0.03, text=txt, showarrow=False, font=dict(color="#64748b", size=8.5)))

    # 7. Proyección Trilineal de Muestras
    colores_paleta = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

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

        # Cationes
        xc = x_cat_orig + (na_k + 0.5 * mg) / 100.0
        yc = (mg / 100.0) * h_tri
        # Aniones (Estándar OMM: HCO3 a la izquierda, Cl a la derecha)
        xa = x_an_orig + (cl + 0.5 * so4) / 100.0
        ya = (so4 / 100.0) * h_tri

        # Diamante Central Proyección Exacta
        u_cat = na_k / 100.0
        v_an = (cl + so4) / 100.0
        xd = x_diam_bot + 0.5 * (v_an - u_cat)
        yd = y_diam_bot + h_tri * (v_an + u_cat)

        hover_txt = f"""
        <b>🧪 Muestra:</b> {id_m}<br>
        <b>Facies:</b> {facies}<br>
        <b>Error Balance CBE:</b> {r.get('CBE_pct', 0.0):+.2f}% ({r.get('CBE_Calidad', '')})<br>
        <b>SDT:</b> {r.get('SDT_mg_L', 0):,.1f} mg/L | <b>CE:</b> {r.get('CE_uS_cm', 0):,.0f} µS/cm<br>
        <hr style='margin:4px 0;'>
        <b>Cationes:</b> Ca²⁺={ca:.1f}%, Mg²⁺={mg:.1f}%, Na⁺+K⁺={na_k:.1f}%<br>
        <b>Aniones:</b> HCO₃⁻={hco3:.1f}%, SO₄²⁻={so4:.1f}%, Cl⁻={cl:.1f}%
        """

        # Punto Cationes
        fig.add_trace(go.Scatter(
            x=[xc], y=[yc], mode='markers',
            marker=dict(size=10, color=color_pt, line=dict(width=1.5, color='#0f172a')),
            name=id_m, hovertext=hover_txt, hoverinfo='text',
            legendgroup=id_m, showlegend=False
        ))
        # Punto Aniones
        fig.add_trace(go.Scatter(
            x=[xa], y=[ya], mode='markers',
            marker=dict(size=10, color=color_pt, line=dict(width=1.5, color='#0f172a')),
            hovertext=hover_txt, hoverinfo='text',
            legendgroup=id_m, showlegend=False
        ))
        # Punto Diamante (con símbolo de diamante)
        fig.add_trace(go.Scatter(
            x=[xd], y=[yd], mode='markers',
            marker=dict(size=12, color=color_pt, symbol='diamond', line=dict(width=1.5, color='#0f172a')),
            name=f"{id_m} ({facies})",
            hovertext=hover_txt, hoverinfo='text',
            legendgroup=id_m, showlegend=True
        ))
        # Líneas trilineales de conexión
        fig.add_trace(go.Scatter(
            x=[xc, xd, xa], y=[yc, yd, ya], mode='lines',
            line=dict(color=color_pt, width=1.1, dash='dot'),
            hoverinfo='skip', legendgroup=id_m, showlegend=False
        ))

    fig.update_layout(
        title=dict(text="<b>Diagrama Trilineal de Piper (OMM / UNESCO)</b>", font=dict(size=16, color="#1e293b"), x=0.5),
        annotations=anotaciones,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.25, 2.70]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.22, 3.0 * h_tri + 0.22], scaleanchor="x", scaleratio=1),
        height=720,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=50, b=40, l=30, r=30),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=10.5),
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#cbd5e1",
            borderwidth=1
        )
    )
    return fig




# =============================================================================
# 5.1 DIAGRAMA DE PIPER VECTORIAL D3.js / SVG (ALTA DEFINICIÓN CIENTÍFICA)
# =============================================================================
def generar_diagrama_piper_d3(df_procesado):
    """
    Construye un Diagrama de Piper vectorial interactivo en D3.js / SVG puro:
      - Renderizado en cliente acelerado por GPU (< 10 ms).
      - viewBox escalable 960x780 sin distorsión geométrica.
      - Cuadrantes sombreados con gradientes suaves SVG.
      - Líneas de conexión trilineales dinámicas con efecto glow interactivo.
      - Botones nativos para descarga en SVG vectorial (editable) y PNG a 300 DPI (alta resolución).
    """
    muestras_data = []
    colores_paleta = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        color_pt = colores_paleta[idx % len(colores_paleta)]
        muestras_data.append({
            "id": id_m,
            "fuente": str(r.get('Tipo_Fuente', 'Fuente')),
            "facies": str(r.get('Facies_Piper', 'N/D')),
            "cbe": float(r.get('CBE_pct', 0.0)),
            "cbe_calidad": str(r.get('CBE_Calidad', '')),
            "sdt": float(r.get('SDT_mg_L', 0.0)),
            "ce": float(r.get('CE_uS_cm', 0.0)),
            "revelle": float(r.get('Indice_Revelle', 0.0)),
            "ca_pct": float(r.get('pct_Ca', 0.0)),
            "mg_pct": float(r.get('pct_Mg', 0.0)),
            "nak_pct": float(r.get('pct_Na_K', 0.0)),
            "hco3_pct": float(r.get('pct_HCO3_CO3', 0.0)),
            "so4_pct": float(r.get('pct_SO4', 0.0)),
            "cl_pct": float(r.get('pct_Cl', 0.0)),
            "color": color_pt
        })

    muestras_json_str = json.dumps(muestras_data)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Piper D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{
          margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
          background: #ffffff; user-select: none; overflow: hidden;
        }}
        .toolbar-piper {{
          display: flex; justify-content: space-between; align-items: center;
          padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;
          border-radius: 6px 6px 0 0;
        }}
        .btn-toolbar {{
          background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px;
          padding: 5px 12px; font-size: 11.5px; font-weight: 600; color: #334155;
          cursor: pointer; display: inline-flex; align-items: center; gap: 5px;
          transition: all 0.2s ease;
        }}
        .btn-toolbar:hover {{
          background: #691C32; color: #ffffff; border-color: #691C32;
          box-shadow: 0 2px 6px rgba(105, 28, 50, 0.25);
        }}
        #piper-svg-container {{
          width: 100%; height: 750px; position: relative; background: #ffffff;
        }}
        svg {{
          width: 100%; height: 100%; display: block;
        }}
        /* Tooltip flotante con Glassmorphism */
        #piper-tooltip {{
          position: absolute; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 18px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11.5px; color: #1e293b;
          pointer-events: none; max-width: 280px; line-height: 1.45;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar-piper">
        <div style="font-size: 12px; font-weight: 700; color: #691C32;">
          ⚡ Diagrama de Piper Vectorial (D3.js / SVG Nativo - OMM / UNESCO)
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="btn-toolbar" onclick="descargarSVG()">
            <span>📥</span> Exportar SVG Vectorial
          </button>
          <button class="btn-toolbar" onclick="descargarPNG()">
            <span>🖼️</span> Exportar PNG 300 DPI
          </button>
        </div>
      </div>

      <div id="piper-svg-container">
        <div id="piper-tooltip"></div>
      </div>

      <script>
        const dataMuestras = {muestras_json_str};

        // Geometría Matemática del Piper
        const width = 960;
        const height = 780;
        const L = 260.0;
        const H = L * Math.sqrt(3) / 2.0; // 225.1666

        // Triángulo Cationes
        const x_c_left = 110.0, y_c_base = 730.0;
        const x_c_right = x_c_left + L, y_c_right = y_c_base;
        const x_c_top = (x_c_left + x_c_right) / 2.0, y_c_top = y_c_base - H;

        // Triángulo Aniones
        const x_a_left = 590.0, y_a_base = 730.0;
        const x_a_right = x_a_left + L, y_a_right = y_a_base;
        const x_a_top = (x_a_left + x_a_right) / 2.0, y_a_top = y_a_base - H;

        // Diamante Central (Rombo Equilátero de lados L=260)
        const x_d_bot = 480.0, y_d_bot = y_c_top;
        const x_d_left = x_d_bot - L / 2.0, y_d_left = y_d_bot - H;
        const x_d_right = x_d_bot + L / 2.0, y_d_right = y_d_bot - H;
        const x_d_top = x_d_bot, y_d_top = y_d_bot - 2.0 * H;
        const x_center = x_d_bot, y_center = y_d_left;

        // Puntos medios aristas Diamante
        const x_m_bl = (x_d_bot + x_d_left) / 2.0, y_m_bl = y_d_bot - H / 2.0;
        const x_m_br = (x_d_bot + x_d_right) / 2.0, y_m_br = y_d_bot - H / 2.0;
        const x_m_tl = (x_d_left + x_d_top) / 2.0, y_m_tl = y_d_left - H / 2.0;
        const x_m_tr = (x_d_right + x_d_top) / 2.0, y_m_tr = y_d_right - H / 2.0;

        const svg = d3.select("#piper-svg-container")
          .append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{width}} ${{height}}`)
          .attr("width", width)
          .attr("height", height)
          .attr("id", "svg-piper")
          .attr("preserveAspectRatio", "xMidYMid meet");

        // Fondo blanco opaco autocontenido
        svg.append("rect")
          .attr("width", width)
          .attr("height", height)
          .attr("fill", "#ffffff");

        // Estilos CSS incrustados directamente dentro de <defs> en el SVG
        const defs = svg.append("defs");
        defs.append("style").text(`
          .axis-label {{ font-size: 13px; font-weight: 700; fill: #0f172a; text-anchor: middle; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
          .axis-title-cat, .axis-title-an {{ font-size: 11.5px; font-weight: 700; fill: #691C32; text-anchor: middle; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
          .grid-line {{ stroke: #e2e8f0; stroke-width: 0.85; stroke-dasharray: 2, 2; fill: none; }}
          .border-line {{ stroke: #1e293b; stroke-width: 2.2; fill: none; }}
          .center-dash {{ stroke: #64748b; stroke-width: 1.1; stroke-dasharray: 4, 3; fill: none; }}
          .tick-label {{ font-size: 9px; fill: #64748b; font-weight: 600; text-anchor: middle; dominant-baseline: middle; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
          .quad-label {{ font-size: 10.5px; font-weight: 700; text-anchor: middle; dominant-baseline: middle; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
          .quad-sub {{ font-size: 8.5px; font-weight: 500; text-anchor: middle; dominant-baseline: middle; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
          .sample-pt {{ cursor: pointer; }}
          .connection-line {{ fill: none; stroke-dasharray: 3, 3; opacity: 0.65; }}
        `);

        // 1. Sombreado translúcido de los 4 cuadrantes
        // Sur: Recarga Bicarbonatada Cálcica (Azul fresco)
        svg.append("polygon")
          .attr("points", `${{x_d_bot}},${{y_d_bot}} ${{x_m_bl}},${{y_m_bl}} ${{x_center}},${{y_center}} ${{x_m_br}},${{y_m_br}}`)
          .attr("fill", "#0284c7")
          .attr("fill-opacity", 0.08);

        // Norte: Clorurada Sódica Salina (Rojo)
        svg.append("polygon")
          .attr("points", `${{x_center}},${{y_center}} ${{x_m_tl}},${{y_m_tl}} ${{x_d_top}},${{y_d_top}} ${{x_m_tr}},${{y_m_tr}}`)
          .attr("fill", "#dc2626")
          .attr("fill-opacity", 0.08);

        // Oeste: Bicarbonatada Sódica Intercambio (Violeta)
        svg.append("polygon")
          .attr("points", `${{x_m_bl}},${{y_m_bl}} ${{x_d_left}},${{y_d_left}} ${{x_m_tl}},${{y_m_tl}} ${{x_center}},${{y_center}}`)
          .attr("fill", "#7c3aed")
          .attr("fill-opacity", 0.08);

        // Este: Sulfatada Cálcica Yesos (Ámbar)
        svg.append("polygon")
          .attr("points", `${{x_m_br}},${{y_m_br}} ${{x_center}},${{y_center}} ${{x_m_tr}},${{y_m_tr}} ${{x_d_right}},${{y_d_right}}`)
          .attr("fill", "#d97706")
          .attr("fill-opacity", 0.08);

        // 2. Rejillas internas (cada 20%)
        const pcts = [0.2, 0.4, 0.6, 0.8];
        const gGrid = svg.append("g").attr("class", "grids");

        // Cationes
        pcts.forEach(pct => {{
          // Horizontales (Mg)
          const yh = y_c_base - pct * H;
          const x1 = x_c_left + pct * (L / 2.0);
          const x2 = x_c_right - pct * (L / 2.0);
          gGrid.append("line").attr("x1", x1).attr("y1", yh).attr("x2", x2).attr("y2", yh).attr("class", "grid-line").attr("fill", "none");

          // 60° (Na+K)
          const x_start = x_c_left + pct * L;
          const x_end = x_c_left + L / 2.0 + pct * (L / 2.0);
          const y_end = y_c_base - H * (1.0 - pct);
          gGrid.append("line").attr("x1", x_start).attr("y1", y_c_base).attr("x2", x_end).attr("y2", y_end).attr("class", "grid-line").attr("fill", "none");

          // 120° (Ca)
          const x_start_ca = x_c_right - pct * L;
          const x_end_ca = x_c_left + L / 2.0 - pct * (L / 2.0);
          gGrid.append("line").attr("x1", x_start_ca).attr("y1", y_c_base).attr("x2", x_end_ca).attr("y2", y_end).attr("class", "grid-line").attr("fill", "none");
        }});

        // Aniones
        pcts.forEach(pct => {{
          // Horizontales (SO4)
          const yh = y_a_base - pct * H;
          const x1 = x_a_left + pct * (L / 2.0);
          const x2 = x_a_right - pct * (L / 2.0);
          gGrid.append("line").attr("x1", x1).attr("y1", yh).attr("x2", x2).attr("y2", yh).attr("class", "grid-line").attr("fill", "none");

          // 60° (Cl)
          const x_start = x_a_left + pct * L;
          const x_end = x_a_left + L / 2.0 + pct * (L / 2.0);
          const y_end = y_a_base - H * (1.0 - pct);
          gGrid.append("line").attr("x1", x_start).attr("y1", y_a_base).attr("x2", x_end).attr("y2", y_end).attr("class", "grid-line").attr("fill", "none");

          // 120° (HCO3)
          const x_start_hco3 = x_a_right - pct * L;
          const x_end_hco3 = x_a_left + L / 2.0 - pct * (L / 2.0);
          gGrid.append("line").attr("x1", x_start_hco3).attr("y1", y_a_base).attr("x2", x_end_hco3).attr("y2", y_end).attr("class", "grid-line").attr("fill", "none");
        }});

        // Diamante rejilla
        pcts.forEach(pct => {{
          // Paralelas a arista inf-izq
          const x1 = x_d_bot + pct * (x_d_right - x_d_bot);
          const y1 = y_d_bot + pct * (y_d_right - y_d_bot);
          const x2 = x_d_left + pct * (x_d_top - x_d_left);
          const y2 = y_d_left + pct * (y_d_top - y_d_left);
          gGrid.append("line").attr("x1", x1).attr("y1", y1).attr("x2", x2).attr("y2", y2).attr("class", "grid-line").attr("fill", "none");

          // Paralelas a arista inf-der
          const x3 = x_d_bot + pct * (x_d_left - x_d_bot);
          const y3 = y_d_bot + pct * (y_d_left - y_d_bot);
          const x4 = x_d_right + pct * (x_d_top - x_d_right);
          const y4 = y_d_right + pct * (y_d_top - y_d_right);
          gGrid.append("line").attr("x1", x3).attr("y1", y3).attr("x2", x4).attr("y2", y4).attr("class", "grid-line").attr("fill", "none");
        }});

        // 3. Bordes estructurales con fill="none" explícito
        const gBorders = svg.append("g").attr("class", "borders");
        // Cationes
        gBorders.append("polygon")
          .attr("points", `${{x_c_left}},${{y_c_base}} ${{x_c_right}},${{y_c_base}} ${{x_c_top}},${{y_c_top}}`)
          .attr("fill", "none")
          .attr("stroke", "#1e293b")
          .attr("stroke-width", 2.2)
          .attr("class", "border-line");
        // Aniones
        gBorders.append("polygon")
          .attr("points", `${{x_a_left}},${{y_a_base}} ${{x_a_right}},${{y_a_base}} ${{x_a_top}},${{y_a_top}}`)
          .attr("fill", "none")
          .attr("stroke", "#1e293b")
          .attr("stroke-width", 2.2)
          .attr("class", "border-line");
        // Diamante
        gBorders.append("polygon")
          .attr("points", `${{x_d_bot}},${{y_d_bot}} ${{x_d_right}},${{y_d_right}} ${{x_d_top}},${{y_d_top}} ${{x_d_left}},${{y_d_left}}`)
          .attr("fill", "none")
          .attr("stroke", "#1e293b")
          .attr("stroke-width", 2.2)
          .attr("class", "border-line");
        // Ejes medios diamante
        gBorders.append("line").attr("x1", x_d_left).attr("y1", y_d_left).attr("x2", x_d_right).attr("y2", y_d_right).attr("class", "center-dash").attr("fill", "none");
        gBorders.append("line").attr("x1", x_d_bot).attr("y1", y_d_bot).attr("x2", x_d_top).attr("y2", y_d_top).attr("class", "center-dash").attr("fill", "none");

        // 4. Rotulación y Vértices
        const gLabels = svg.append("g").attr("class", "labels");
        // Cationes
        gLabels.append("text").attr("x", x_c_left - 15).attr("y", y_c_base + 8).text("Ca²⁺").attr("class", "axis-label");
        gLabels.append("text").attr("x", x_c_right + 25).attr("y", y_c_base + 8).text("Na⁺+K⁺").attr("class", "axis-label");
        gLabels.append("text").attr("x", x_c_top).attr("y", y_c_top - 12).text("Mg²⁺").attr("class", "axis-label");
        gLabels.append("text").attr("x", x_c_top).attr("y", y_c_base + 32).text("CATIONES (% meq/L) →").attr("class", "axis-title-cat");

        // Aniones
        gLabels.append("text").attr("x", x_a_left - 30).attr("y", y_a_base + 8).text("HCO₃⁻+CO₃²⁻").attr("class", "axis-label");
        gLabels.append("text").attr("x", x_a_right + 18).attr("y", y_a_base + 8).text("Cl⁻").attr("class", "axis-label");
        gLabels.append("text").attr("x", x_a_top).attr("y", y_a_top - 12).text("SO₄²⁻").attr("class", "axis-label");
        gLabels.append("text").attr("x", x_a_top).attr("y", y_a_base + 32).text("← ANIONES (% meq/L)").attr("class", "axis-title-an");

        // Rótulos Cuadrantes
        gLabels.append("text").attr("x", x_d_bot).attr("y", y_d_bot - 16).text("Bicarbonatada Cálcica").attr("class", "quad-label").attr("fill", "#166534");
        gLabels.append("text").attr("x", x_d_bot).attr("y", y_d_bot - 4).text("Recarga Fresca de Montaña").attr("class", "quad-sub").attr("fill", "#166534");

        gLabels.append("text").attr("x", x_d_top).attr("y", y_d_top + 16).text("Clorurada Sódica").attr("class", "quad-label").attr("fill", "#991b1b");
        gLabels.append("text").attr("x", x_d_top).attr("y", y_d_top + 28).text("Salina / Intrusión / Profunda").attr("class", "quad-sub").attr("fill", "#991b1b");

        gLabels.append("text").attr("x", x_d_left - 8).attr("y", y_d_left).text("Bicarbonatada Sódica").attr("class", "quad-label").attr("fill", "#6b21a8").attr("transform", `rotate(-45, ${{x_d_left - 8}}, ${{y_d_left}})`);
        gLabels.append("text").attr("x", x_d_right + 8).attr("y", y_d_right).text("Sulfatada Cálcica").attr("class", "quad-label").attr("fill", "#92400e").attr("transform", `rotate(45, ${{x_d_right + 8}}, ${{y_d_right}})`);

        // Ticks numéricos
        pcts.forEach(pct => {{
          const txt = Math.round(pct * 100);
          gLabels.append("text").attr("x", x_c_left + pct * L).attr("y", y_c_base + 12).text(txt).attr("class", "tick-label");
          gLabels.append("text").attr("x", x_a_left + pct * L).attr("y", y_a_base + 12).text(txt).attr("class", "tick-label");
        }});

        // 5. Muestras y Conexiones Interactivas
        const gConnections = svg.append("g").attr("class", "connections");
        const gSamples = svg.append("g").attr("class", "samples");
        const tooltip = d3.select("#piper-tooltip");

        dataMuestras.forEach((m, i) => {{
          const u_cat = m.nak_pct / 100.0;
          const mg_val = m.mg_pct / 100.0;
          const cl_val = m.cl_pct / 100.0;
          const so4_val = m.so4_pct / 100.0;
          const v_an = (m.cl_pct + m.so4_pct) / 100.0;

          // Coordenadas exactas
          const xc = x_c_left + u_cat * L + 0.5 * mg_val * L;
          const yc = y_c_base - mg_val * H;

          const xa = x_a_left + cl_val * L + 0.5 * so4_val * L;
          const ya = y_a_base - so4_val * H;

          const xd = x_d_bot + 0.5 * (v_an - u_cat) * L;
          const yd = y_d_bot - (u_cat + v_an) * H;

          // Línea trilineal de conexión con fill="none"
          const conn = gConnections.append("polyline")
            .attr("points", `${{xc}},${{yc}} ${{xd}},${{yd}} ${{xa}},${{ya}}`)
            .attr("stroke", m.color)
            .attr("stroke-width", 1.2)
            .attr("fill", "none")
            .attr("class", `connection-line conn-${{i}}`);

          // Hover handler
          const showTip = (event) => {{
            conn.classed("highlight", true).attr("stroke-width", 2.2).attr("stroke-opacity", 1.0);
            d3.selectAll(`.pt-group-${{i}}`).raise().selectAll("circle, polygon").attr("stroke-width", 3.0);

            const tipHtml = `
              <div style="font-weight:700; color:#691C32; margin-bottom:4px; font-size:12px;">🧪 ${{m.id}}</div>
              <div style="color:#475569; font-size:11px; margin-bottom:6px;"><b>Fuente:</b> ${{m.fuente}}</div>
              <div style="background:#f1f5f9; padding:4px 8px; border-radius:4px; margin-bottom:6px;">
                <b>Facies:</b> <span style="color:${{m.color}}; font-weight:700;">${{m.facies}}</span><br>
                <b>Error Balance (CBE):</b> ${{m.cbe >= 0 ? '+' : ''}}${{m.cbe.toFixed(2)}}% (${{m.cbe_calidad}})<br>
                <b>SDT:</b> ${{m.sdt.toLocaleString()}} mg/L | <b>CE:</b> ${{m.ce.toLocaleString()}} µS/cm<br>
                <b>Índice Revelle:</b> ${{m.revelle.toFixed(2)}}
              </div>
              <div style="font-size:10.5px; color:#334155;">
                <b>Cationes:</b> Ca²⁺=${{m.ca_pct.toFixed(1)}}%, Mg²⁺=${{m.mg_pct.toFixed(1)}}%, Na⁺+K⁺=${{m.nak_pct.toFixed(1)}}%<br>
                <b>Aniones:</b> HCO₃⁻=${{m.hco3_pct.toFixed(1)}}%, SO₄²⁻=${{m.so4_pct.toFixed(1)}}%, Cl⁻=${{m.cl_pct.toFixed(1)}}%
              </div>
            `;
            tooltip.html(tipHtml)
              .style("left", (event.pageX + 14) + "px")
              .style("top", (event.pageY - 28) + "px")
              .style("display", "block");
          }};

          const hideTip = () => {{
            conn.classed("highlight", false).attr("stroke-width", 1.2).attr("stroke-opacity", 0.65);
            d3.selectAll(`.pt-group-${{i}}`).selectAll("circle, polygon").attr("stroke-width", 1.8);
            tooltip.style("display", "none");
          }};

          const grp = gSamples.append("g").attr("class", `pt-group-${{i}}`);

          // Punto Cationes
          grp.append("circle")
            .attr("cx", xc).attr("cy", yc).attr("r", 5.5)
            .attr("fill", m.color).attr("stroke", "#ffffff").attr("stroke-width", 1.8)
            .attr("class", "sample-pt")
            .on("mouseover", showTip).on("mousemove", showTip).on("mouseout", hideTip);

          // Punto Aniones
          grp.append("circle")
            .attr("cx", xa).attr("cy", ya).attr("r", 5.5)
            .attr("fill", m.color).attr("stroke", "#ffffff").attr("stroke-width", 1.8)
            .attr("class", "sample-pt")
            .on("mouseover", showTip).on("mousemove", showTip).on("mouseout", hideTip);

          // Punto Diamante (Rombo de tamaño 7)
          const rd = 7.0;
          grp.append("polygon")
            .attr("points", `${{xd}},${{yd - rd}} ${{xd + rd}},${{yd}} ${{xd}},${{yd + rd}} ${{xd - rd}},${{yd}}`)
            .attr("fill", m.color).attr("stroke", "#ffffff").attr("stroke-width", 1.8)
            .attr("class", "sample-pt")
            .on("mouseover", showTip).on("mousemove", showTip).on("mouseout", hideTip);
        }});

        // Funciones de Descarga con corrección integral de secciones negras y tamaño intrínseco
        function descargarSVG() {{
          const svgEl = document.getElementById("svg-piper");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{type: "image/svg+xml;charset=utf-8"}});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "Diagrama_Piper_Vectorial_CONAGUA.svg";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarPNG() {{
          const svgEl = document.getElementById("svg-piper");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const img = new Image();
          const svgBlob = new Blob([source], {{type: "image/svg+xml;charset=utf-8"}});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0; // 300 DPI equivalente
            canvas.width = width * scale;
            canvas.height = height * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, width, height);
            ctx.drawImage(img, 0, 0, width, height);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Piper_300DPI_CONAGUA.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code
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


# =============================================================================
# 6.1 DIAGRAMAS DE STIFF VECTORIAL D3.js / SVG MULTIMUESTRA
# =============================================================================
def generar_diagrama_stiff_d3(df_procesado, muestra_sel=None):
    """
    Genera diagramas poligonales de Stiff en D3.js / SVG nativo:
      - 2 columnas responsivas con tarjetas individuales.
      - Convención Canónica Tri-Nivel de H.A. Stiff (1951):
          Nivel 0 (sup): Na++K+ (izq) | Cl- (der)
          Nivel 1 (med): Ca2+ (izq)   | HCO3- (der)
          Nivel 2 (inf): Mg2+ (izq)   | SO42- (der)
      - Ejes milimétricos en meq/L con escala simétrica regular sin solapamientos.
      - Descarga directa en SVG vectorial y PNG a 300 DPI por muestra y mosaico.
    """
    df_plot = df_procesado.copy()
    if muestra_sel and muestra_sel != "Todas las Muestras":
        df_plot = df_plot[df_plot['Muestra'].astype(str) == str(muestra_sel)]

    muestras_stiff = []
    colores_paleta = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, (_, r) in enumerate(df_plot.iterrows()):
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        na_k = float(r.get('Na_meq_L', 0) + r.get('K_meq_L', 0))
        ca = float(r.get('Ca_meq_L', 0))
        mg = float(r.get('Mg_meq_L', 0))
        cl = float(r.get('Cl_meq_L', 0))
        hco3 = float(r.get('HCO3_meq_L', 0) + r.get('CO3_meq_L', 0))
        so4 = float(r.get('SO4_meq_L', 0))

        color_pt = colores_paleta[idx % len(colores_paleta)]
        muestras_stiff.append({
            "id": id_m,
            "fuente": str(r.get('Tipo_Fuente', 'Fuente')),
            "facies": str(r.get('Facies_Piper', 'N/D')),
            "cbe": float(r.get('CBE_pct', 0.0)),
            "sdt": float(r.get('SDT_mg_L', 0.0)),
            "na_k": na_k, "ca": ca, "mg": mg,
            "cl": cl, "hco3": hco3, "so4": so4,
            "color": color_pt
        })

    json_stiff = json.dumps(muestras_stiff)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagramas de Stiff D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{
          margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
          background: #f8fafc; user-select: none;
        }}
        .toolbar-stiff {{
          display: flex; justify-content: space-between; align-items: center;
          padding: 8px 16px; background: #ffffff; border-bottom: 1px solid #e2e8f0;
          position: sticky; top: 0; z-index: 100;
        }}
        .btn-toolbar {{
          background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px;
          padding: 5px 12px; font-size: 11.5px; font-weight: 600; color: #334155;
          cursor: pointer; display: inline-flex; align-items: center; gap: 5px;
          transition: all 0.2s ease;
        }}
        .btn-toolbar:hover {{
          background: #691C32; color: #ffffff; border-color: #691C32;
        }}
        .btn-card-dl {{
          background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px;
          padding: 2px 7px; font-size: 10px; font-weight: 600; color: #475569;
          cursor: pointer; transition: all 0.15s ease;
        }}
        .btn-card-dl:hover {{
          background: #691C32; color: #ffffff; border-color: #691C32;
        }}
        .stiff-grid {{
          display: grid; grid-template-columns: repeat(auto-fit, minmax(440px, 1fr));
          gap: 16px; padding: 16px;
        }}
        .stiff-card {{
          background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.04); padding: 12px 14px;
          transition: transform 0.2s, box-shadow 0.2s;
        }}
        .stiff-card:hover {{
          transform: translateY(-2px); box-shadow: 0 4px 14px rgba(105, 28, 50, 0.12);
        }}
        .stiff-title {{
          font-size: 12.5px; font-weight: 700; color: #1e293b; margin-bottom: 6px;
          display: flex; justify-content: space-between; align-items: center;
        }}
        .badge-facies {{
          font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 10px; color: white;
        }}
        svg {{ width: 100%; height: 240px; display: block; }}
        #stiff-tooltip {{
          position: fixed; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11px; color: #1e293b; pointer-events: none;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar-stiff">
        <div style="font-size: 12px; font-weight: 700; color: #691C32;">
          ⚡ Huellas Iónicas de Stiff (meq/L) - Convención Canónica Tri-Nivel (Stiff, 1951)
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="btn-toolbar" onclick="descargarTodosSVGs()">
            <span>📥</span> Exportar SVGs
          </button>
        </div>
      </div>

      <div id="stiff-tooltip"></div>
      <div class="stiff-grid" id="stiff-container"></div>

      <script>
        const data = {json_stiff};
        const container = d3.select("#stiff-container");
        const tooltip = d3.select("#stiff-tooltip");

        // Escala máxima unificada con generador de pasos matemáticos limpios
        let maxVal = 2.0;
        data.forEach(d => {{
          const m = Math.max(d.na_k, d.ca, d.mg, d.cl, d.hco3, d.so4);
          if (m > maxVal) maxVal = m;
        }});

        function calcularEscalaStiff(val) {{
          let target = val * 1.15;
          let step = 1.0;
          if (target <= 2.5) step = 0.5;
          else if (target <= 5.0) step = 1.0;
          else if (target <= 10.0) step = 2.0;
          else if (target <= 20.0) step = 5.0;
          else if (target <= 50.0) step = 10.0;
          else if (target <= 100.0) step = 20.0;
          else step = Math.ceil(target / 4 / 10) * 10;

          let maxAxis = Math.ceil(target / step) * step;
          let ticks = [];
          for (let v = -maxAxis; v <= maxAxis + 0.0001; v += step) {{
            ticks.push(Math.round(v * 100) / 100);
          }}
          if (ticks.length > 9) {{
            ticks = [-maxAxis, -maxAxis/2, 0, maxAxis/2, maxAxis];
          }}
          return {{ maxAxis, ticks }};
        }}

        const escalaCfg = calcularEscalaStiff(maxVal);
        const maxAxis = escalaCfg.maxAxis;
        const tickValues = escalaCfg.ticks;

        data.forEach((m, idx) => {{
          const card = container.append("div").attr("class", "stiff-card");

          const header = card.append("div").attr("class", "stiff-title");
          const leftTitle = header.append("div").style("display", "flex").style("align-items", "center").style("gap", "8px");
          leftTitle.html(`<b>🧪 ${{m.id}}</b> <span style="font-size:10.5px;color:#64748b;font-weight:normal;">(${{m.fuente}})</span>`);
          
          const rightActions = header.append("div").style("display", "flex").style("align-items", "center").style("gap", "6px");
          rightActions.append("span").attr("class", "badge-facies").style("background", m.color).text(m.facies);
          rightActions.append("button").attr("class", "btn-card-dl").text("📥 SVG").on("click", () => descargarStiffIndividualSVG(idx, m.id));
          rightActions.append("button").attr("class", "btn-card-dl").text("🖼️ PNG").on("click", () => descargarStiffIndividualPNG(idx, m.id));

          const w = 460, h = 240;
          const padL = 85, padR = 85, padT = 25, padB = 40;
          const graphW = w - padL - padR;
          const xCenter = padL + graphW / 2.0;

          const svg = card.append("svg")
            .attr("xmlns", "http://www.w3.org/2000/svg")
            .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
            .attr("viewBox", `0 0 ${{w}} ${{h}}`)
            .attr("width", w)
            .attr("height", h)
            .attr("id", `stiff-svg-${{idx}}`)
            .attr("preserveAspectRatio", "xMidYMid meet");

          // Fondo blanco
          svg.append("rect")
            .attr("width", w)
            .attr("height", h)
            .attr("fill", "#ffffff");

          const defs = svg.append("defs");
          defs.append("style").text(`
            .stiff-poly {{ fill-opacity: 0.35; stroke-width: 2.2; cursor: pointer; }}
            .center-axis {{ stroke: #64748b; stroke-width: 1.2; stroke-dasharray: 4, 3; fill: none; }}
            .grid-line {{ stroke: #f1f5f9; stroke-width: 0.8; fill: none; }}
            .ion-label {{ font-size: 10px; font-weight: 600; fill: #334155; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; dominant-baseline: middle; }}
            .tick-text {{ font-size: 9.5px; fill: #64748b; font-weight: 600; text-anchor: middle; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
            .axis-title-stiff {{ font-size: 11px; fill: #691C32; font-weight: 700; text-anchor: middle; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
          `);

          const xScale = d3.scaleLinear().domain([-maxAxis, maxAxis]).range([padL, w - padR]);
          // 3 niveles canónicos de Stiff (1951)
          const yPos = [padT + 25, padT + 75, padT + 125]; 

          // Ejes de fondo y ticks
          tickValues.forEach(val => {{
            const x = xScale(val);
            svg.append("line")
              .attr("x1", x).attr("y1", padT)
              .attr("x2", x).attr("y2", padT + 145)
              .attr("stroke", val === 0 ? "#64748b" : "#e2e8f0")
              .attr("stroke-width", val === 0 ? 1.2 : 0.8)
              .attr("stroke-dasharray", val === 0 ? "4, 3" : null)
              .attr("fill", "none")
              .attr("class", val === 0 ? "center-axis" : "grid-line");

            const lblTxt = Math.abs(val) % 1 === 0 ? Math.abs(val).toFixed(0) : Math.abs(val).toFixed(1);
            svg.append("text")
              .attr("x", x).attr("y", padT + 160)
              .text(lblTxt)
              .attr("class", "tick-text");
          }});

          // Título del eje con separación vertical limpia (y = padT + 185)
          svg.append("text")
            .attr("x", xCenter).attr("y", padT + 185)
            .text("Cationes ← 0 → Aniones (meq/L)")
            .attr("class", "axis-title-stiff");

          // Etiquetas de Iones (izq Cationes, der Aniones)
          const niveles = [
            {{ y: yPos[0], cat: `Na⁺+K⁺: ${{m.na_k.toFixed(1)}}`, an: `Cl⁻: ${{m.cl.toFixed(1)}}` }},
            {{ y: yPos[1], cat: `Ca²⁺: ${{m.ca.toFixed(1)}}`, an: `HCO₃⁻: ${{m.hco3.toFixed(1)}}` }},
            {{ y: yPos[2], cat: `Mg²⁺: ${{m.mg.toFixed(1)}}`, an: `SO₄²⁻: ${{m.so4.toFixed(1)}}` }}
          ];

          niveles.forEach(n => {{
            svg.append("text").attr("x", padL - 10).attr("y", n.y).text(n.cat).attr("class", "ion-label").attr("text-anchor", "end");
            svg.append("text").attr("x", w - padR + 10).attr("y", n.y).text(n.an).attr("class", "ion-label").attr("text-anchor", "start");
            // Línea horizontal del nivel
            svg.append("line").attr("x1", padL).attr("y1", n.y).attr("x2", w - padR).attr("y2", n.y).attr("stroke", "#f1f5f9").attr("stroke-width", 0.8).attr("fill", "none");
          }});

          // Puntos del polígono canónico de Stiff (Hexágono)
          const polyPts = [
            [xScale(-m.na_k), yPos[0]],
            [xScale(-m.ca), yPos[1]],
            [xScale(-m.mg), yPos[2]],
            [xScale(m.so4), yPos[2]],
            [xScale(m.hco3), yPos[1]],
            [xScale(m.cl), yPos[0]]
          ];

          const ptsStr = polyPts.map(p => `${{p[0].toFixed(1)}},${{p[1].toFixed(1)}}`).join(" ");

          svg.append("polygon")
            .attr("points", ptsStr)
            .attr("fill", m.color)
            .attr("fill-opacity", 0.35)
            .attr("stroke", m.color)
            .attr("stroke-width", 2.2)
            .attr("class", "stiff-poly")
            .on("mouseover", (event) => {{
              tooltip.html(`
                <b>🧪 ${{m.id}}</b><br>
                <b>Facies:</b> ${{m.facies}}<br>
                <b>CBE:</b> ${{m.cbe >= 0 ? '+' : ''}}${{m.cbe.toFixed(2)}}% | <b>SDT:</b> ${{m.sdt.toLocaleString()}} mg/L<br>
                <hr style="margin:4px 0;">
                Na⁺+K⁺: ${{m.na_k.toFixed(2)}} | Cl⁻: ${{m.cl.toFixed(2)}} meq/L<br>
                Ca²⁺: ${{m.ca.toFixed(2)}} | HCO₃⁻: ${{m.hco3.toFixed(2)}} meq/L<br>
                Mg²⁺: ${{m.mg.toFixed(2)}} | SO₄²⁻: ${{m.so4.toFixed(2)}} meq/L
              `).style("left", (event.clientX + 14) + "px").style("top", (event.clientY - 20) + "px").style("display", "block");
            }})
            .on("mousemove", (event) => {{
              tooltip.style("left", (event.clientX + 14) + "px").style("top", (event.clientY - 20) + "px");
            }})
            .on("mouseout", () => {{ tooltip.style("display", "none"); }});

          // Vértices circulares
          polyPts.forEach(pt => {{
            svg.append("circle")
              .attr("cx", pt[0]).attr("cy", pt[1])
              .attr("r", 3.5)
              .attr("fill", m.color)
              .attr("stroke", "#ffffff")
              .attr("stroke-width", 1.5);
          }});
        }});

        function descargarStiffIndividualSVG(idx, idMuestra) {{
          const svgEl = document.getElementById(`stiff-svg-${{idx}}`);
          if (!svgEl) return;
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `Diagrama_Stiff_${{idMuestra}}.svg`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarStiffIndividualPNG(idx, idMuestra) {{
          const svgEl = document.getElementById(`stiff-svg-${{idx}}`);
          if (!svgEl) return;
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            const w = 460, h = 240;
            canvas.width = w * scale;
            canvas.height = h * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, w, h);
            ctx.drawImage(img, 0, 0, w, h);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = `Diagrama_Stiff_300DPI_${{idMuestra}}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}

        function descargarTodosSVGs() {{
          const svgs = document.querySelectorAll(".stiff-card svg");
          if (svgs.length === 0) return;
          descargarStiffIndividualSVG(0, data[0]?.id || "Muestra");
        }}
      </script>
    </body>
    </html>
    """
    return html_code
def generar_diagrama_schoeller_d3(df_procesado):
    """
    Construye el Perfil Semilogarítmico de Schöeller-Berkaloff en D3.js / SVG:
      - Secuencia de Chebotarev con escala logarítmica exacta.
      - Líneas vectoriales nítidas con resaltado interactivo al hover.
      - Leyenda superior totalmente separada de los ejes.
      - Exportación en SVG y PNG a 300 DPI (alta resolución).
    """
    muestras_data = []
    colores_paleta = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        color_pt = colores_paleta[idx % len(colores_paleta)]
        muestras_data.append({
            "id": id_m,
            "facies": str(r.get('Facies_Piper', 'N/D')),
            "ca": max(0.001, float(r.get('Ca_meq_L', 0.001))),
            "mg": max(0.001, float(r.get('Mg_meq_L', 0.001))),
            "nak": max(0.001, float(r.get('Na_meq_L', 0) + r.get('K_meq_L', 0))),
            "hco3": max(0.001, float(r.get('HCO3_meq_L', 0.001) + r.get('CO3_meq_L', 0))),
            "so4": max(0.001, float(r.get('SO4_meq_L', 0.001))),
            "cl": max(0.001, float(r.get('Cl_meq_L', 0.001))),
            "color": color_pt
        })

    json_str = json.dumps(muestras_data)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Schöeller D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{
          margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
          background: #ffffff; user-select: none;
        }}
        .toolbar-schoeller {{
          display: flex; justify-content: space-between; align-items: center;
          padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;
        }}
        .btn-toolbar {{
          background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px;
          padding: 5px 12px; font-size: 11.5px; font-weight: 600; color: #334155;
          cursor: pointer; display: inline-flex; align-items: center; gap: 5px;
          transition: all 0.2s ease;
        }}
        .btn-toolbar:hover {{ background: #691C32; color: #ffffff; border-color: #691C32; }}
        svg {{ width: 100%; height: 500px; display: block; }}
        .schoeller-line {{ fill: none; stroke-width: 2.2; transition: all 0.2s; }}
        .schoeller-line.faded {{ opacity: 0.18; stroke-width: 1.2; }}
        .schoeller-line.active {{ stroke-width: 3.5; opacity: 1; }}
        .schoeller-dot {{ cursor: pointer; transition: r 0.2s; }}
        .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
        .axis-text {{ font-size: 11px; fill: #475569; font-family: sans-serif; }}
        #schoeller-tooltip {{
          position: fixed; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11.5px; color: #1e293b; pointer-events: none;
        }}
        .legend-container {{
          display: flex; gap: 12px; flex-wrap: wrap; padding: 8px 24px; background: #ffffff;
        }}
        .leg-item {{
          display: flex; align-items: center; gap: 6px; font-size: 11px; cursor: pointer; padding: 2px 6px; border-radius: 4px;
        }}
        .leg-item:hover {{ background: #f1f5f9; }}
        .leg-bullet {{ width: 10px; height: 10px; border-radius: 50%; }}
      </style>
    </head>
    <body>
      <div class="toolbar-schoeller">
        <div style="font-size: 12px; font-weight: 700; color: #691C32;">
          ⚡ Perfil Semilogarítmico de Schöeller-Berkaloff - Motor D3.js / SVG
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="btn-toolbar" onclick="descargarSVG()">
            <span>📥</span> Exportar SVG
          </button>
          <button class="btn-toolbar" onclick="descargarPNG()">
            <span>🖼️</span> Exportar PNG 300 DPI
          </button>
        </div>
      </div>

      <div class="legend-container" id="legend-bar"></div>
      <div id="schoeller-tooltip"></div>
      <div id="schoeller-svg-container"></div>

      <script>
        const data = {json_str};
        const ions = [
          {{ key: "ca", label: "Ca²⁺" }},
          {{ key: "mg", label: "Mg²⁺" }},
          {{ key: "nak", label: "Na⁺+K⁺" }},
          {{ key: "hco3", label: "HCO₃⁻" }},
          {{ key: "so4", label: "SO₄²⁻" }},
          {{ key: "cl", label: "Cl⁻" }}
        ];

        const w = 900, h = 440;
        const padL = 70, padR = 40, padT = 30, padB = 55;

        const svg = d3.select("#schoeller-svg-container").append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{w}} ${{h}}`)
          .attr("width", w)
          .attr("height", h)
          .attr("id", "svg-schoeller")
          .attr("preserveAspectRatio", "xMidYMid meet");

        // Fondo blanco opaco
        svg.append("rect")
          .attr("width", w)
          .attr("height", h)
          .attr("fill", "#ffffff");

        const defs = svg.append("defs");
        defs.append("style").text(`
          .schoeller-line {{ fill: none; stroke-width: 2.2; }}
          .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
          .axis-text {{ font-size: 11px; fill: #475569; font-family: sans-serif; }}
        `);

        const tooltip = d3.select("#schoeller-tooltip");

        const xScale = d3.scalePoint().domain(ions.map(d => d.label)).range([padL, w - padR]).padding(0.4);
        const yScale = d3.scaleLog().domain([0.01, 100]).range([h - padB, padT]);

        // Rejilla Y (log)
        [0.01, 0.1, 1, 10, 100].forEach(val => {{
          const y = yScale(val);
          svg.append("line").attr("x1", padL).attr("y1", y).attr("x2", w - padR).attr("y2", y).attr("class", "grid-line").attr("fill", "none");
          svg.append("text").attr("x", padL - 10).attr("y", y).text(val).attr("class", "axis-text").attr("text-anchor", "end").attr("dominant-baseline", "middle");
        }});

        // Rejilla X
        ions.forEach(ion => {{
          const x = xScale(ion.label);
          svg.append("line").attr("x1", x).attr("y1", padT).attr("x2", x).attr("y2", h - padB).attr("class", "grid-line").attr("fill", "none");
          svg.append("text").attr("x", x).attr("y", h - padB + 22).text(ion.label).attr("class", "axis-text").attr("text-anchor", "middle").style("font-weight", "700").style("fill", "#1e293b").style("font-size", "12px");
        }});

        // Títulos de ejes
        svg.append("text").attr("x", (padL + w - padR)/2).attr("y", h - 10).text("Secuencia Hidrogeoquímica de Chebotarev").attr("class", "axis-text").attr("text-anchor", "middle").style("font-weight", "600");
        svg.append("text").attr("transform", "rotate(-90)").attr("x", -(padT + h - padB)/2).attr("y", 18).text("Concentración Iónica (meq/L, escala log)").attr("class", "axis-text").attr("text-anchor", "middle").style("font-weight", "600");

        // Barra de leyenda superior
        const legBar = d3.select("#legend-bar");

        data.forEach((m, idx) => {{
          const lineGen = d3.line()
            .x(d => xScale(d.label))
            .y(d => yScale(d.val));

          const pts = ions.map(ion => ({{ label: ion.label, val: m[ion.key] }}));

          const path = svg.append("path")
            .datum(pts)
            .attr("d", lineGen)
            .attr("stroke", m.color)
            .attr("fill", "none")
            .attr("stroke-width", 2.2)
            .attr("class", `schoeller-line line-${{idx}}`);

          const dots = svg.selectAll(`.dot-${{idx}}`)
            .data(pts)
            .enter().append("circle")
            .attr("cx", d => xScale(d.label))
            .attr("cy", d => yScale(d.val))
            .attr("r", 4.5)
            .attr("fill", m.color)
            .attr("stroke", "#ffffff")
            .attr("stroke-width", 1.5)
            .attr("class", `schoeller-dot dot-${{idx}}`);

          const highlight = () => {{
            d3.selectAll(".schoeller-line").classed("faded", true);
            path.classed("faded", false).classed("active", true).raise();
            dots.attr("r", 6.5).raise();
          }};

          const reset = () => {{
            d3.selectAll(".schoeller-line").classed("faded", false).classed("active", false);
            dots.attr("r", 4.5);
            tooltip.style("display", "none");
          }};

          dots.on("mouseover", (event, d) => {{
            highlight();
            tooltip.html(`<b>🧪 ${{m.id}}</b><br><b>${{d.label}}:</b> ${{d.val.toFixed(2)}} meq/L<br><b>Facies:</b> ${{m.facies}}`)
              .style("left", (event.clientX + 14) + "px").style("top", (event.clientY - 20) + "px").style("display", "block");
          }}).on("mouseout", reset);

          // Item de leyenda
          const item = legBar.append("div").attr("class", "leg-item")
            .on("mouseover", highlight).on("mouseout", reset);
          item.append("div").attr("class", "leg-bullet").style("background", m.color);
          item.append("span").text(m.id);
        }});

        function descargarSVG() {{
          const svgEl = document.getElementById("svg-schoeller");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "Diagrama_Schoeller_Vectorial.svg";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarPNG() {{
          const svgEl = document.getElementById("svg-schoeller");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            canvas.width = w * scale;
            canvas.height = h * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, w, h);
            ctx.drawImage(img, 0, 0, w, h);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Schoeller_300DPI.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code
def generar_diagrama_stiff(df_procesado, muestra_sel=None):
    """
    Construye diagramas poligonales de Stiff limpios sin solapamiento:
      - 2 columnas por fila para evitar compresión horizontal de títulos.
      - Títulos limpios y concisos con facies en subtítulo.
      - Vértice 4 con NO3 en el lado aniónico para rigor hidrogeoquímico.
    """
    df_plot = df_procesado.copy()
    if muestra_sel and muestra_sel != "Todas las Muestras":
        df_plot = df_plot[df_plot['Muestra'].astype(str) == str(muestra_sel)]

    n_muestras = len(df_plot)
    if n_muestras == 0:
        return go.Figure()

    from plotly.subplots import make_subplots
    cols_grid = min(2, n_muestras)
    rows_grid = math.ceil(n_muestras / cols_grid)

    titulos_sub = [f"<b>{r.get('Muestra')}</b> ({r.get('Facies_Piper', '')})" for _, r in df_plot.iterrows()]
    fig = make_subplots(
        rows=rows_grid, cols=cols_grid,
        subplot_titles=titulos_sub,
        vertical_spacing=0.22,
        horizontal_spacing=0.18
    )

    max_meq = max([
        df_plot['Ca_meq_L'].max(), df_plot['Mg_meq_L'].max(),
        (df_plot['Na_meq_L'] + df_plot['K_meq_L']).max(),
        (df_plot['HCO3_meq_L'] + df_plot['CO3_meq_L']).max(),
        df_plot['SO4_meq_L'].max(), df_plot['Cl_meq_L'].max(), 5.0
    ])
    escala_x = math.ceil(max_meq * 1.15)

    y_labels = ["Fe / NO₃", "Mg / SO₄", "Ca / HCO₃", "Na+K / Cl"]
    y_pos = [1, 2, 3, 4]
    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

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

        # Polígono cerrado conectando Cationes (izq) y Aniones (der)
        xs = [-na_k, -ca, -mg, -fe, no3, so4, hco3, cl, -na_k]
        ys = [4, 3, 2, 1, 1, 2, 3, 4, 4]
        color_fill = colores[idx % len(colores)]

        fig.add_trace(go.Scatter(
            x=xs, y=ys, fill='toself',
            fillcolor=hex_or_rgb_to_rgba(color_fill, 0.38),
            line=dict(color=color_fill, width=2.2),
            mode='lines+markers',
            marker=dict(size=6, color=color_fill),
            hoverinfo='text',
            hovertext=[
                f"Na+K: {na_k:.2f} meq/L", f"Ca: {ca:.2f} meq/L", f"Mg: {mg:.2f} meq/L", f"Fe: {fe:.2f} meq/L",
                f"NO₃: {no3:.2f} meq/L", f"SO₄: {so4:.2f} meq/L", f"HCO₃: {hco3:.2f} meq/L", f"Cl: {cl:.2f} meq/L",
                f"Na+K: {na_k:.2f} meq/L"
            ],
            showlegend=False
        ), row=row_i, col=col_i)

        fig.add_vline(x=0, line=dict(color="#64748b", width=1.4, dash="dash"), row=row_i, col=col_i)
        fig.update_xaxes(range=[-escala_x, escala_x], title="Cationes ← 0 → Aniones (meq/L)" if row_i == rows_grid else "", row=row_i, col=col_i)
        fig.update_yaxes(tickvals=y_pos, ticktext=y_labels, row=row_i, col=col_i)

    alt_total = max(380, rows_grid * 270)
    fig.update_layout(
        title=dict(text="<b>Diagramas Poligonales de Stiff (meq/L)</b>", font=dict(size=15, color="#1e293b")),
        height=alt_total,
        plot_bgcolor='#f8fafc',
        paper_bgcolor='white',
        margin=dict(t=70, b=40, l=40, r=40)
    )
    return fig


# =============================================================================
# 7. DIAGRAMA DE SCHÖELLER-BERKALOFF
# =============================================================================
def generar_diagrama_schoeller(df_procesado):
    """
    Gráfico semilogarítmico con la secuencia hidrogeoquímica de Chebotarev
    y leyenda superior totalmente separada de los ejes.
    """
    fig = go.Figure()
    iones_x = ["Ca²⁺", "Mg²⁺", "Na⁺+K⁺", "HCO₃⁻", "SO₄²⁻", "Cl⁻"]
    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

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

        hover_txt = f"<b>🧪 {id_m}</b><br>" + "<br>".join([f"{ion}: {v:.2f} meq/L" for ion, v in zip(iones_x, vals_y)])

        fig.add_trace(go.Scatter(
            x=iones_x, y=vals_y,
            mode='lines+markers',
            name=id_m,
            line=dict(color=color_linea, width=2.2),
            marker=dict(size=8, color=color_linea),
            hovertext=hover_txt,
            hoverinfo='text'
        ))

    fig.update_layout(
        title=dict(text="<b>Perfil Semilogarítmico de Schöeller-Berkaloff</b>", font=dict(size=15, color="#1e293b")),
        xaxis=dict(title="Secuencia Geoquímica (Chebotarev)", showgrid=True, gridcolor='#e2e8f0'),
        yaxis=dict(title="Concentración Iónica (meq/L)", type="log", showgrid=True, gridcolor='#e2e8f0'),
        height=520,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=65, b=60, l=55, r=25),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="center", x=0.5, font=dict(size=10.5))
    )
    return fig


# =============================================================================
# 8. DIAGRAMAS AGRÍCOLAS (WILCOX Y USSL RIVERSIDE)
# =============================================================================


# =============================================================================
# 8.1 DIAGRAMA DE WILCOX VECTORIAL D3.js / SVG (APTITUD PARA RIEGO)
# =============================================================================
def generar_diagrama_wilcox_d3(df_procesado):
    """
    Construye el Diagrama de Wilcox en D3.js / SVG nativo:
      - Zonas de aptitud sombreadas translúcidas (Excelente, Bueno, Permisible, Dudoso).
      - Ejes nítidos con leyendas superiores sin solapamiento.
      - Descarga directa en SVG vectorial y PNG a 300 DPI.
    """
    muestras = []
    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        ce = float(r.get('CE_uS_cm', 0.0) if pd.notna(r.get('CE_uS_cm')) else (r.get('SDT_mg_L', 0.0) / 0.65))
        pct_na = float(r.get('Pct_Na_Riego', 0.0))
        ras = float(r.get('RAS', 0.0))
        muestras.append({
            "id": id_m, "ce": ce, "pct_na": pct_na, "ras": ras,
            "color": colores[idx % len(colores)],
            "facies": str(r.get('Facies_Piper', ''))
        })

    json_str = json.dumps(muestras)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Wilcox D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #ffffff; user-select: none; }}
        .toolbar {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
        .btn-toolbar {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px; padding: 4px 10px; font-size: 11px; font-weight: 600; cursor: pointer; color: #334155; transition: all 0.2s ease; }}
        .btn-toolbar:hover {{ background: #691C32; color: white; border-color: #691C32; }}
        svg {{ width: 100%; height: 480px; display: block; }}
        .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; stroke-dasharray: 2, 2; fill: none; }}
        .zone-boundary {{ stroke-width: 1.8; stroke-dasharray: 4, 3; fill: none; }}
        .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
        .zone-text {{ font-size: 11px; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        .dot {{ cursor: pointer; transition: r 0.2s; }}
        #wilcox-tooltip {{
          position: fixed; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11px; color: #1e293b; pointer-events: none;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar">
        <div style="font-size: 11.5px; font-weight: 700; color: #691C32;">🌾 Diagrama de Wilcox (Aptitud Agronómica) - D3.js / SVG</div>
        <div style="display: flex; gap: 8px;">
          <button class="btn-toolbar" onclick="descargarSVG()"><span>📥</span> Exportar SVG</button>
          <button class="btn-toolbar" onclick="descargarPNG()"><span>🖼️</span> Exportar PNG 300 DPI</button>
        </div>
      </div>
      <div id="wilcox-tooltip"></div>
      <div id="wilcox-svg-container"></div>

      <script>
        const data = {json_str};
        const w = 700, h = 440;
        const padL = 60, padR = 30, padT = 30, padB = 55;

        const svg = d3.select("#wilcox-svg-container").append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{w}} ${{h}}`)
          .attr("width", w)
          .attr("height", h)
          .attr("id", "svg-wilcox")
          .attr("preserveAspectRatio", "xMidYMid meet");

        // Fondo blanco opaco
        svg.append("rect")
          .attr("width", w)
          .attr("height", h)
          .attr("fill", "#ffffff");

        const defs = svg.append("defs");
        defs.append("style").text(`
          .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; stroke-dasharray: 2, 2; fill: none; }}
          .zone-boundary {{ stroke-width: 1.8; stroke-dasharray: 4, 3; fill: none; }}
          .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
          .zone-text {{ font-size: 11px; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        `);

        const tooltip = d3.select("#wilcox-tooltip");

        const xScale = d3.scaleLinear().domain([0, 4000]).range([padL, w - padR]);
        const yScale = d3.scaleLinear().domain([0, 100]).range([h - padB, padT]);

        // Rejilla
        xScale.ticks(8).forEach(tick => {{
          svg.append("line").attr("x1", xScale(tick)).attr("y1", padT).attr("x2", xScale(tick)).attr("y2", h - padB).attr("class", "grid-line").attr("fill", "none");
          svg.append("text").attr("x", xScale(tick)).attr("y", h - padB + 18).text(tick).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "middle");
        }});
        yScale.ticks(5).forEach(tick => {{
          svg.append("line").attr("x1", padL).attr("y1", yScale(tick)).attr("x2", w - padR).attr("y2", yScale(tick)).attr("class", "grid-line").attr("fill", "none");
          svg.append("text").attr("x", padL - 8).attr("y", yScale(tick)).text(tick + "%").attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "end").attr("dominant-baseline", "middle");
        }});

        // Títulos de ejes
        svg.append("text").attr("x", (padL + w - padR)/2).attr("y", h - 12).text("Conductividad Eléctrica (µS/cm a 25 °C)").attr("class", "axis-label").attr("text-anchor", "middle");
        svg.append("text").attr("transform", "rotate(-90)").attr("x", -(padT + h - padB)/2).attr("y", 16).text("Porcentaje de Sodio Soluble (% Na)").attr("class", "axis-label").attr("text-anchor", "middle");

        // Curvas límites de zonas con fill="none" explícito
        const ceArr = d3.range(0, 4001, 100);
        const curveExc = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(20, Math.min(100, 100 - d / 40.0))));
        const curveBue = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(10, Math.min(80, 100 - d / 25.0))));
        const curvePer = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(5, Math.min(60, 100 - d / 18.0))));

        svg.append("path").datum(ceArr).attr("d", curveExc).attr("stroke", "#16a34a").attr("fill", "none").attr("class", "zone-boundary");
        svg.append("path").datum(ceArr).attr("d", curveBue).attr("stroke", "#2563eb").attr("fill", "none").attr("class", "zone-boundary");
        svg.append("path").datum(ceArr).attr("d", curvePer).attr("stroke", "#d97706").attr("fill", "none").attr("class", "zone-boundary");

        // Rótulos de zonas
        svg.append("text").attr("x", xScale(350)).attr("y", yScale(85)).text("Excelente").attr("class", "zone-text").attr("fill", "#16a34a");
        svg.append("text").attr("x", xScale(1000)).attr("y", yScale(55)).text("Bueno").attr("class", "zone-text").attr("fill", "#2563eb");
        svg.append("text").attr("x", xScale(1800)).attr("y", yScale(30)).text("Permisible").attr("class", "zone-text").attr("fill", "#d97706");
        svg.append("text").attr("x", xScale(2900)).attr("y", yScale(16)).text("Dudoso / Inadecuado").attr("class", "zone-text").attr("fill", "#dc2626");

        // Muestras
        data.forEach(m => {{
          svg.append("circle")
            .attr("cx", xScale(m.ce))
            .attr("cy", yScale(m.pct_na))
            .attr("r", 5.5)
            .attr("fill", m.color)
            .attr("stroke", "#ffffff")
            .attr("stroke-width", 1.8)
            .attr("class", "dot")
            .on("mouseover", (event) => {{
              tooltip.html(`
                <b>🌾 ${{m.id}}</b><br>
                <b>Conductividad:</b> ${{m.ce.toLocaleString()}} µS/cm<br>
                <b>% Sodio Soluble:</b> ${{m.pct_na.toFixed(1)}}%<br>
                <b>RAS:</b> ${{m.ras.toFixed(2)}}<br>
                <b>Facies:</b> ${{m.facies}}
              `).style("left", (event.clientX + 14) + "px").style("top", (event.clientY - 20) + "px").style("display", "block");
            }})
            .on("mouseout", () => {{ tooltip.style("display", "none"); }});
        }});

        function descargarSVG() {{
          const svgEl = document.getElementById("svg-wilcox");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = "Diagrama_Wilcox_Vectorial.svg";
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarPNG() {{
          const svgEl = document.getElementById("svg-wilcox");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            canvas.width = w * scale;
            canvas.height = h * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, w, h);
            ctx.drawImage(img, 0, 0, w, h);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Wilcox_300DPI.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code
def generar_diagrama_riverside_d3(df_procesado):
    """
    Construye el Diagrama de Riverside (USSL) en D3.js / SVG nativo:
      - Salinidad (C1-C4) vs Peligro de Sodificación (S1-S4).
      - Escala logarítmica de CE e isolíneas empíricas de RAS.
      - Descarga directa en SVG vectorial y PNG a 300 DPI.
    """
    muestras = []
    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        ce = float(r.get('CE_uS_cm', 0.0) if pd.notna(r.get('CE_uS_cm')) else (r.get('SDT_mg_L', 0.0) / 0.65))
        ce = max(100.0, ce)
        ras = float(r.get('RAS', 0.0))
        muestras.append({
            "id": id_m, "ce": ce, "ras": ras,
            "clasif": str(r.get('Clasif_RAS', '')),
            "color": colores[idx % len(colores)],
            "facies": str(r.get('Facies_Piper', ''))
        })

    json_str = json.dumps(muestras)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Riverside D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #ffffff; user-select: none; }}
        .toolbar {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
        .btn-toolbar {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px; padding: 4px 10px; font-size: 11px; font-weight: 600; cursor: pointer; color: #334155; transition: all 0.2s ease; }}
        .btn-toolbar:hover {{ background: #691C32; color: white; border-color: #691C32; }}
        svg {{ width: 100%; height: 480px; display: block; }}
        .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
        .c-boundary {{ stroke: #94a3b8; stroke-width: 1.2; stroke-dasharray: 4, 3; fill: none; }}
        .s-boundary {{ stroke-width: 1.2; stroke-dasharray: 3, 3; fill: none; }}
        .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
        .dot {{ cursor: pointer; transition: r 0.2s; }}
        #riv-tooltip {{
          position: fixed; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11px; color: #1e293b; pointer-events: none;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar">
        <div style="font-size: 11.5px; font-weight: 700; color: #691C32;">🌾 Diagrama de Riverside (USSL) - D3.js / SVG</div>
        <div style="display: flex; gap: 8px;">
          <button class="btn-toolbar" onclick="descargarSVG()"><span>📥</span> Exportar SVG</button>
          <button class="btn-toolbar" onclick="descargarPNG()"><span>🖼️</span> Exportar PNG 300 DPI</button>
        </div>
      </div>
      <div id="riv-tooltip"></div>
      <div id="riv-svg-container"></div>

      <script>
        const data = {json_str};
        const w = 700, h = 440;
        const padL = 60, padR = 30, padT = 30, padB = 55;

        const svg = d3.select("#riv-svg-container").append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{w}} ${{h}}`)
          .attr("width", w)
          .attr("height", h)
          .attr("id", "svg-riverside")
          .attr("preserveAspectRatio", "xMidYMid meet");

        // Fondo blanco opaco
        svg.append("rect")
          .attr("width", w)
          .attr("height", h)
          .attr("fill", "#ffffff");

        const defs = svg.append("defs");
        defs.append("style").text(`
          .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
          .c-boundary {{ stroke: #94a3b8; stroke-width: 1.2; stroke-dasharray: 4, 3; fill: none; }}
          .s-boundary {{ stroke-width: 1.2; stroke-dasharray: 3, 3; fill: none; }}
          .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
        `);

        const tooltip = d3.select("#riv-tooltip");

        const xScale = d3.scaleLog().domain([100, 5000]).range([padL, w - padR]);
        const yScale = d3.scaleLinear().domain([0, 32]).range([h - padB, padT]);

        // Ejes y Ticks
        [100, 250, 750, 2250, 5000].forEach(val => {{
          svg.append("line").attr("x1", xScale(val)).attr("y1", padT).attr("x2", xScale(val)).attr("y2", h - padB).attr("fill", "none").attr("class", val === 100 || val === 5000 ? "grid-line" : "c-boundary");
          svg.append("text").attr("x", xScale(val)).attr("y", h - padB + 18).text(val).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "middle");
        }});

        [0, 5, 10, 15, 20, 25, 30].forEach(val => {{
          svg.append("line").attr("x1", padL).attr("y1", yScale(val)).attr("x2", w - padR).attr("y2", yScale(val)).attr("class", "grid-line").attr("fill", "none");
          svg.append("text").attr("x", padL - 8).attr("y", yScale(val)).text(val).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "end").attr("dominant-baseline", "middle");
        }});

        // Rótulos de Salinidad C1 a C4
        svg.append("text").attr("x", xScale(160)).attr("y", padT - 8).text("C1: Baja").attr("font-size", "10px").attr("fill", "#16a34a").attr("text-anchor", "middle").style("font-weight", "700");
        svg.append("text").attr("x", xScale(430)).attr("y", padT - 8).text("C2: Media").attr("font-size", "10px").attr("fill", "#2563eb").attr("text-anchor", "middle").style("font-weight", "700");
        svg.append("text").attr("x", xScale(1300)).attr("y", padT - 8).text("C3: Alta").attr("font-size", "10px").attr("fill", "#d97706").attr("text-anchor", "middle").style("font-weight", "700");
        svg.append("text").attr("x", xScale(3350)).attr("y", padT - 8).text("C4: Muy Alta").attr("font-size", "10px").attr("fill", "#dc2626").attr("text-anchor", "middle").style("font-weight", "700");

        // Curvas límites S1 a S4 con fill="none" explícito
        const ceLogArr = d3.range(100, 5001, 100);
        const curveS1 = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, 10.0 - 0.001 * d)));
        const curveS2 = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, 18.0 - 0.0015 * d)));
        const curveS3 = d3.line().x(d => xScale(d)).y(d => yScale(Math.max(0, 26.0 - 0.002 * d)));

        svg.append("path").datum(ceLogArr).attr("d", curveS1).attr("stroke", "#16a34a").attr("fill", "none").attr("class", "s-boundary");
        svg.append("path").datum(ceLogArr).attr("d", curveS2).attr("stroke", "#d97706").attr("fill", "none").attr("class", "s-boundary");
        svg.append("path").datum(ceLogArr).attr("d", curveS3).attr("stroke", "#dc2626").attr("fill", "none").attr("class", "s-boundary");

        // Títulos de ejes
        svg.append("text").attr("x", (padL + w - padR)/2).attr("y", h - 12).text("Conductividad Eléctrica (µS/cm, escala log)").attr("class", "axis-label").attr("text-anchor", "middle");
        svg.append("text").attr("transform", "rotate(-90)").attr("x", -(padT + h - padB)/2).attr("y", 18).text("Relación de Adsorción de Sodio (RAS / SAR)").attr("class", "axis-label").attr("text-anchor", "middle");

        // Muestras
        data.forEach(m => {{
          svg.append("circle")
            .attr("cx", xScale(m.ce))
            .attr("cy", yScale(m.ras))
            .attr("r", 5.5)
            .attr("fill", m.color)
            .attr("stroke", "#ffffff")
            .attr("stroke-width", 1.8)
            .attr("class", "dot")
            .on("mouseover", (event) => {{
              tooltip.html(`
                <b>🌾 ${{m.id}}</b><br>
                <b>Conductividad:</b> ${{m.ce.toLocaleString()}} µS/cm<br>
                <b>RAS:</b> ${{m.ras.toFixed(2)}}<br>
                <b>Diagnóstico:</b> ${{m.clasif}}<br>
                <b>Facies:</b> ${{m.facies}}
              `).style("left", (event.clientX + 14) + "px").style("top", (event.clientY - 20) + "px").style("display", "block");
            }})
            .on("mouseout", () => {{ tooltip.style("display", "none"); }});
        }});

        function descargarSVG() {{
          const svgEl = document.getElementById("svg-riverside");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = "Diagrama_Riverside_Vectorial.svg";
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarPNG() {{
          const svgEl = document.getElementById("svg-riverside");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            canvas.width = w * scale;
            canvas.height = h * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, w, h);
            ctx.drawImage(img, 0, 0, w, h);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Riverside_300DPI.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code
def generar_diagrama_gibbs_d3(df_procesado):
    """
    Construye los diagramas duales de Gibbs en D3.js / SVG nativo:
      - Cationes: Na/(Na+Ca) vs SDT (log).
      - Aniones: Cl/(Cl+HCO3) vs SDT (log).
      - Zonas geomorfológicas rectoras sombreadas (Lluvia, Agua-Roca, Evaporación).
      - Descarga directa en SVG vectorial y PNG a 300 DPI.
    """
    muestras = []
    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]

    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        sdt = max(10.0, float(r.get('SDT_mg_L', 100.0) if pd.notna(r.get('SDT_mg_L')) else 100.0))
        g_cat = float(r.get('Gibbs_Cationes', np.nan))
        g_an = float(r.get('Gibbs_Aniones', np.nan))
        muestras.append({
            "id": id_m, "sdt": sdt, "g_cat": g_cat, "g_an": g_an,
            "color": colores[idx % len(colores)],
            "facies": str(r.get('Facies_Piper', ''))
        })

    json_str = json.dumps(muestras)

    html_code = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Diagrama de Gibbs D3.js</title>
      <script src="https://d3js.org/d3.v7.min.js"></script>
      <style>
        body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #ffffff; user-select: none; }}
        .toolbar {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; }}
        .btn-toolbar {{ background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px; padding: 4px 10px; font-size: 11px; font-weight: 600; cursor: pointer; color: #334155; transition: all 0.2s ease; }}
        .btn-toolbar:hover {{ background: #691C32; color: white; border-color: #691C32; }}
        svg {{ width: 100%; height: 500px; display: block; }}
        .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
        .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
        .panel-title {{ font-size: 12.5px; fill: #1e293b; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        .zone-rect {{ stroke: none; rx: 4; }}
        .zone-text {{ font-size: 9.5px; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        .dot {{ cursor: pointer; transition: r 0.2s; }}
        #gibbs-tooltip {{
          position: fixed; display: none; z-index: 9999;
          background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(8px);
          border: 1px solid #cbd5e1; border-top: 3px solid #691C32;
          border-radius: 6px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);
          padding: 8px 12px; font-size: 11px; color: #1e293b; pointer-events: none;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar">
        <div style="font-size: 11.5px; font-weight: 700; color: #691C32;">🌍 Diagramas de Gibbs (Identificación de Procesos Hidrogeoquímicos) - D3.js / SVG</div>
        <div style="display: flex; gap: 8px;">
          <button class="btn-toolbar" onclick="descargarSVG()"><span>📥</span> Exportar SVG</button>
          <button class="btn-toolbar" onclick="descargarPNG()"><span>🖼️</span> Exportar PNG 300 DPI</button>
        </div>
      </div>
      <div id="gibbs-tooltip"></div>
      <div id="gibbs-svg-container"></div>

      <script>
        const data = {json_str};
        const totalW = 920, h = 460;
        const padT = 45, padB = 55;
        const panelW = 400;
        const gap = 60;
        const padL1 = 65, padL2 = padL1 + panelW + gap;

        const svg = d3.select("#gibbs-svg-container").append("svg")
          .attr("xmlns", "http://www.w3.org/2000/svg")
          .attr("xmlns:xlink", "http://www.w3.org/1999/xlink")
          .attr("viewBox", `0 0 ${{totalW}} ${{h}}`)
          .attr("width", totalW)
          .attr("height", h)
          .attr("id", "svg-gibbs")
          .attr("preserveAspectRatio", "xMidYMid meet");

        // Fondo blanco opaco
        svg.append("rect")
          .attr("width", totalW)
          .attr("height", h)
          .attr("fill", "#ffffff");

        const defs = svg.append("defs");
        defs.append("style").text(`
          .grid-line {{ stroke: #e2e8f0; stroke-width: 0.8; fill: none; }}
          .axis-label {{ font-size: 11px; fill: #475569; font-weight: 600; font-family: sans-serif; }}
          .panel-title {{ font-size: 12.5px; fill: #1e293b; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
          .zone-rect {{ stroke: none; rx: 4; }}
          .zone-text {{ font-size: 9.5px; font-weight: 700; text-anchor: middle; font-family: sans-serif; }}
        `);

        const tooltip = d3.select("#gibbs-tooltip");
        const yScale = d3.scaleLog().domain([10, 10000]).range([h - padB, padT]);

        // Dibujar panel (1=Cationes, 2=Aniones)
        function dibujarPanel(offsetL, titulo, xField, xLabel) {{
          const xScale = d3.scaleLinear().domain([0, 1.0]).range([offsetL, offsetL + panelW]);

          // Título
          svg.append("text").attr("x", offsetL + panelW/2).attr("y", padT - 18).text(titulo).attr("class", "panel-title");

          // Zonas Geomorfológicas con fill y fill-opacity directos
          // 1. Precipitación
          svg.append("rect")
            .attr("x", xScale(0.5)).attr("y", yScale(80))
            .attr("width", xScale(1.0) - xScale(0.5)).attr("height", yScale(10) - yScale(80))
            .attr("fill", "#3b82f6").attr("fill-opacity", 0.12).attr("class", "zone-rect");
          svg.append("text").attr("x", xScale(0.75)).attr("y", (yScale(80) + yScale(10))/2).text("Precipitación (Lluvia)").attr("class", "zone-text").attr("fill", "#1d4ed8");

          // 2. Interacción Agua-Roca
          svg.append("rect")
            .attr("x", xScale(0.05)).attr("y", yScale(1000))
            .attr("width", xScale(0.55) - xScale(0.05)).attr("height", yScale(100) - yScale(1000))
            .attr("fill", "#22c55e").attr("fill-opacity", 0.12).attr("class", "zone-rect");
          svg.append("text").attr("x", xScale(0.30)).attr("y", (yScale(1000) + yScale(100))/2).text("Interacción Agua-Roca").attr("class", "zone-text").attr("fill", "#15803d");

          // 3. Evaporación / Salinidad
          svg.append("rect")
            .attr("x", xScale(0.55)).attr("y", yScale(10000))
            .attr("width", xScale(1.0) - xScale(0.55)).attr("height", yScale(1000) - yScale(10000))
            .attr("fill", "#ef4444").attr("fill-opacity", 0.12).attr("class", "zone-rect");
          svg.append("text").attr("x", xScale(0.78)).attr("y", (yScale(10000) + yScale(100))/2).text("Evaporación / Salinidad").attr("class", "zone-text").attr("fill", "#b91c1c");

          // Rejilla X
          [0, 0.2, 0.4, 0.6, 0.8, 1.0].forEach(val => {{
            svg.append("line").attr("x1", xScale(val)).attr("y1", padT).attr("x2", xScale(val)).attr("y2", h - padB).attr("class", "grid-line").attr("fill", "none");
            svg.append("text").attr("x", xScale(val)).attr("y", h - padB + 18).text(val.toFixed(1)).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "middle");
          }});

          // Rejilla Y (solo en panel 1)
          if (offsetL === padL1) {{
            [10, 100, 1000, 10000].forEach(val => {{
              svg.append("line").attr("x1", padL1).attr("y1", yScale(val)).attr("x2", padL1 + panelW).attr("y2", yScale(val)).attr("class", "grid-line").attr("fill", "none");
              svg.append("text").attr("x", padL1 - 8).attr("y", yScale(val)).text(val.toLocaleString()).attr("font-size", "9.5px").attr("fill", "#64748b").attr("text-anchor", "end").attr("dominant-baseline", "middle");
            }});
            svg.append("text").attr("transform", "rotate(-90)").attr("x", -(padT + h - padB)/2).attr("y", 16).text("SDT (mg/L, escala log)").attr("class", "axis-label").attr("text-anchor", "middle");
          }} else {{
            [10, 100, 1000, 10000].forEach(val => {{
              svg.append("line").attr("x1", offsetL).attr("y1", yScale(val)).attr("x2", offsetL + panelW).attr("y2", yScale(val)).attr("class", "grid-line").attr("fill", "none");
            }});
          }}

          // Título X
          svg.append("text").attr("x", offsetL + panelW/2).attr("y", h - 12).text(xLabel).attr("class", "axis-label").attr("text-anchor", "middle");

          // Muestras
          data.forEach(m => {{
            const xVal = m[xField];
            if (xVal !== null && !isNaN(xVal)) {{
              svg.append("circle")
                .attr("cx", xScale(xVal))
                .attr("cy", yScale(m.sdt))
                .attr("r", 5.5)
                .attr("fill", m.color)
                .attr("stroke", "#ffffff")
                .attr("stroke-width", 1.8)
                .attr("class", "dot")
                .on("mouseover", (event) => {{
                  tooltip.html(`
                    <b>🧪 ${{m.id}}</b><br>
                    <b>${{xLabel}}:</b> ${{xVal.toFixed(2)}}<br>
                    <b>SDT:</b> ${{m.sdt.toLocaleString()}} mg/L<br>
                    <b>Facies:</b> ${{m.facies}}
                  `).style("left", (event.clientX + 14) + "px").style("top", (event.clientY - 20) + "px").style("display", "block");
                }})
                .on("mouseout", () => {{ tooltip.style("display", "none"); }});
            }}
          }});
        }}

        dibujarPanel(padL1, "Cationes: Na⁺ / (Na⁺ + Ca²⁺)", "g_cat", "Relación Na⁺ / (Na⁺ + Ca²⁺)");
        dibujarPanel(padL2, "Aniones: Cl⁻ / (Cl⁻ + HCO₃⁻)", "g_an", "Relación Cl⁻ / (Cl⁻ + HCO₃⁻)");

        function descargarSVG() {{
          const svgEl = document.getElementById("svg-gibbs");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const xmlHeader = '<?xml version="1.0" encoding="UTF-8" standalone="no"?> ';
          const blob = new Blob([xmlHeader + source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = "Diagrama_Gibbs_Vectorial.svg";
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }}

        function descargarPNG() {{
          const svgEl = document.getElementById("svg-gibbs");
          const serializer = new XMLSerializer();
          let source = serializer.serializeToString(svgEl);
          if (!source.includes("xmlns=")) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"');
          }}
          const img = new Image();
          const svgBlob = new Blob([source], {{ type: "image/svg+xml;charset=utf-8" }});
          const url = URL.createObjectURL(svgBlob);
          img.onload = function() {{
            const canvas = document.createElement("canvas");
            const scale = 3.0;
            canvas.width = totalW * scale;
            canvas.height = h * scale;
            const ctx = canvas.getContext("2d");
            ctx.scale(scale, scale);
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, totalW, h);
            ctx.drawImage(img, 0, 0, totalW, h);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.href = pngUrl;
            a.download = "Diagrama_Gibbs_300DPI.png";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }};
          img.src = url;
        }}
      </script>
    </body>
    </html>
    """
    return html_code
def generar_diagrama_wilcox(df_procesado):
    """
    Diagrama de Wilcox con leyenda superior y zonas rotuladas sin solapamiento.
    """
    fig = go.Figure()

    ce_grid = np.linspace(50, 4000, 200)
    y_exc = np.clip(100 - (ce_grid / 40.0), 20, 100)
    y_bue = np.clip(100 - (ce_grid / 25.0), 10, 80)
    y_per = np.clip(100 - (ce_grid / 18.0), 5, 60)

    fig.add_trace(go.Scatter(x=ce_grid, y=y_exc, mode='lines', line=dict(color='#16a34a', width=1.4, dash='dash'), name='Límite Excelente/Bueno', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=ce_grid, y=y_bue, mode='lines', line=dict(color='#2563eb', width=1.4, dash='dash'), name='Límite Bueno/Permisible', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=ce_grid, y=y_per, mode='lines', line=dict(color='#d97706', width=1.4, dash='dash'), name='Límite Permisible/Dudoso', hoverinfo='skip'))

    # Anotaciones de zonas agronómicas
    fig.add_annotation(x=300, y=85, text="<b>Excelente</b>", showarrow=False, font=dict(color="#16a34a", size=10.5))
    fig.add_annotation(x=900, y=55, text="<b>Bueno</b>", showarrow=False, font=dict(color="#2563eb", size=10.5))
    fig.add_annotation(x=1700, y=32, text="<b>Permisible</b>", showarrow=False, font=dict(color="#d97706", size=10.5))
    fig.add_annotation(x=2800, y=18, text="<b>Dudoso / Inadecuado</b>", showarrow=False, font=dict(color="#dc2626", size=10.5))

    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]
    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        ce = float(r.get('CE_uS_cm', 0.0) if pd.notna(r.get('CE_uS_cm')) else (r.get('SDT_mg_L', 0.0) / 0.65))
        pct_na = float(r.get('Pct_Na_Riego', 0.0))
        ras = float(r.get('RAS', 0.0))
        color_pt = colores[idx % len(colores)]

        hover_txt = f"<b>🌾 {id_m}</b><br>CE: {ce:,.0f} µS/cm<br>%Na Soluble: {pct_na:.1f}%<br>RAS: {ras:.2f}"

        fig.add_trace(go.Scatter(
            x=[ce], y=[pct_na], mode='markers',
            marker=dict(size=11, color=color_pt, line=dict(width=1.5, color='#0f172a')),
            name=id_m, hovertext=hover_txt, hoverinfo='text'
        ))

    fig.update_layout(
        title=dict(text="<b>Diagrama de Wilcox - Aptitud para Riego</b>", font=dict(size=14, color="#1e293b")),
        xaxis=dict(title="Conductividad Eléctrica (µS/cm a 25 °C)", range=[0, 4200], showgrid=True, gridcolor='#e2e8f0'),
        yaxis=dict(title="Sodio Soluble (% Na)", range=[0, 100], showgrid=True, gridcolor='#e2e8f0'),
        height=520,
        plot_bgcolor='#fafafa',
        paper_bgcolor='white',
        margin=dict(t=65, b=60, l=55, r=25),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="center", x=0.5, font=dict(size=9.5))
    )
    return fig

def generar_diagrama_riverside(df_procesado):
    """
    Diagrama de Riverside (USSL): Salinidad (C1-C4) vs. Peligro de Sodificación (S1-S4).
    """
    fig = go.Figure()

    for ce_lim, label in [(250, "C1: Baja"), (750, "C2: Media"), (2250, "C3: Alta")]:
        fig.add_vline(x=ce_lim, line=dict(color="#cbd5e1", width=1.5, dash="dash"), annotation_text=label, annotation_position="top")

    ce_arr = np.linspace(100, 5000, 100)
    ras_s1 = 10.0 - 0.001 * ce_arr
    ras_s2 = 18.0 - 0.0015 * ce_arr
    ras_s3 = 26.0 - 0.002 * ce_arr

    fig.add_trace(go.Scatter(x=ce_arr, y=ras_s1, mode='lines', line=dict(color='#16a34a', width=1.2, dash='dot'), name='Límite S1/S2', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=ce_arr, y=ras_s2, mode='lines', line=dict(color='#d97706', width=1.2, dash='dot'), name='Límite S2/S3', hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=ce_arr, y=ras_s3, mode='lines', line=dict(color='#dc2626', width=1.2, dash='dot'), name='Límite S3/S4', hoverinfo='skip'))

    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]
    for idx, r in df_procesado.iterrows():
        id_m = str(r.get('Muestra', f'M-{idx+1}'))
        ce = float(r.get('CE_uS_cm', 0.0) if pd.notna(r.get('CE_uS_cm')) else (r.get('SDT_mg_L', 0.0) / 0.65))
        ras = float(r.get('RAS', 0.0))
        color_pt = colores[idx % len(colores)]

        hover_txt = f"<b>🌾 {id_m}</b><br>CE: {ce:,.0f} µS/cm<br>RAS: {ras:.2f}<br>Diagnóstico: {r.get('Clasif_RAS', '')}"

        fig.add_trace(go.Scatter(
            x=[ce], y=[ras], mode='markers',
            marker=dict(size=11, color=color_pt, line=dict(width=1.5, color='#0f172a')),
            name=id_m, hovertext=hover_txt, hoverinfo='text'
        ))

    fig.update_layout(
        title=dict(text="<b>Diagrama de Riverside (USSL) - Salinidad vs. Sodio</b>", font=dict(size=14, color="#1e293b")),
        xaxis=dict(title="Conductividad Eléctrica (µS/cm, escala log)", type="log", range=[2, 4], showgrid=True, gridcolor='#e2e8f0'),
        yaxis=dict(title="Relación de Adsorción de Sodio (RAS / SAR)", range=[0, 32], showgrid=True, gridcolor='#e2e8f0'),
        height=520,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=65, b=60, l=55, r=25),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="center", x=0.5, font=dict(size=9.5))
    )
    return fig


# =============================================================================
# 9. DIAGRAMA DE GIBBS (MECANISMOS GEOQUÍMICOS)
# =============================================================================
def generar_diagrama_gibbs(df_procesado):
    """
    Diagrama de Gibbs: Cationes y Aniones vs SDT (mg/L).
    """
    from plotly.subplots import make_subplots
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["<b>Cationes: (Na⁺+K⁺)/(Na⁺+K⁺+Ca²⁺)</b>", "<b>Aniones: Cl⁻/(Cl⁻+HCO₃⁻)</b>"],
        horizontal_spacing=0.12
    )

    for col_i in [1, 2]:
        fig.add_shape(type="rect", x0=0.5, y0=10, x1=1.0, y1=80, fillcolor="rgba(59, 130, 246, 0.12)", line=dict(width=0), row=1, col=col_i)
        fig.add_annotation(x=0.75, y=30, text="Dominancia de<br>Precipitación (Lluvia)", showarrow=False, font=dict(size=9.5, color="#1d4ed8"), row=1, col=col_i)

        fig.add_shape(type="rect", x0=0.05, y0=100, x1=0.55, y1=1000, fillcolor="rgba(34, 197, 94, 0.12)", line=dict(width=0), row=1, col=col_i)
        fig.add_annotation(x=0.30, y=350, text="Dominancia de<br>Interacción Agua-Roca", showarrow=False, font=dict(size=9.5, color="#15803d"), row=1, col=col_i)

        fig.add_shape(type="rect", x0=0.55, y0=1000, x1=1.0, y1=10000, fillcolor="rgba(239, 68, 68, 0.12)", line=dict(width=0), row=1, col=col_i)
        fig.add_annotation(x=0.78, y=3500, text="Dominancia de<br>Evaporación / Salinidad", showarrow=False, font=dict(size=9.5, color="#b91c1c"), row=1, col=col_i)

    colores = ["#0284c7", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#0891b2", "#d97706", "#4f46e5"]
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
                marker=dict(size=10, color=color_pt, line=dict(width=1.5, color='#0f172a')),
                name=id_m, hovertext=f"<b>🧪 {id_m}</b><br>Gibbs Cat: {g_cat:.2f}<br>SDT: {sdt:,.0f} mg/L", hoverinfo='text',
                legendgroup=id_m, showlegend=True
            ), row=1, col=1)

        if pd.notna(g_an):
            fig.add_trace(go.Scatter(
                x=[g_an], y=[sdt], mode='markers',
                marker=dict(size=10, color=color_pt, line=dict(width=1.5, color='#0f172a')),
                hovertext=f"<b>🧪 {id_m}</b><br>Gibbs An: {g_an:.2f}<br>SDT: {sdt:,.0f} mg/L", hoverinfo='text',
                legendgroup=id_m, showlegend=False
            ), row=1, col=2)

    fig.update_xaxes(title="Relación Na⁺ / (Na⁺ + Ca²⁺)", range=[0, 1.0], row=1, col=1)
    fig.update_xaxes(title="Relación Cl⁻ / (Cl⁻ + HCO₃⁻)", range=[0, 1.0], row=1, col=2)
    fig.update_yaxes(title="Sólidos Disueltos Totales (SDT, mg/L)", type="log", range=[1, 4], row=1, col=1)
    fig.update_yaxes(type="log", range=[1, 4], row=1, col=2)

    fig.update_layout(
        title=dict(text="<b>Diagramas de Gibbs - Identificación del Proceso Hidrogeoquímico Rector</b>", font=dict(size=15, color="#1e293b")),
        height=540,
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=65, b=60, l=55, r=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="center", x=0.5, font=dict(size=10))
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
