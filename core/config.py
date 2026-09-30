# -*- coding: utf-8 -*-
"""
Created on Wed Aug 12 12:12:54 2026

@author: dchable
"""
import re

# =======================================================
# 🗺️ 1. DICCIONARIOS GEOESPACIALES
# =======================================================
DICCIONARIO_ESTADOS = {
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

# =======================================================
# 🧬 2. MAPAS DE ADN PARA EL ESTANDARIZADOR DE WORD
# =======================================================
MAPA_ADN = {
    "TITULOS": ["GENERALIDADES", "ESTUDIOS TÉCNICOS REALIZADOS CON ANTERIORIDAD", "FISIOGRAFÍA", "GEOLOGÍA",
                "HIDROGEOLOGÍA", "CENSO DE APROVECHAMIENTOS E HIDROMETRÍA", "BALANCE DE AGUAS SUBTERRÁNEAS",
                "DISPONIBILIDAD", "BIBLIOGRAFÍA"],
    
    "SUBTITULOS": ["Localización", "Situación administrativa del acuífero", "Provincia fisiográfica", "Clima",
                   "Hidrografía", "Geomorfología", "Estratigrafía", "Geología estructural", "Geología del subsuelo",
                   "Tipo de acuífero", "Parámetros hidráulicos", "Piezometría", "Comportamiento hidráulico",
                   "Hidrogeoquímica y calidad del agua subterránea", "Entradas", "Salidas", "Cambio de almacenamiento ΔV(S)",
                   "Recarga total media anual (R)", "Descarga natural comprometida (DNC)", "Volumen de extracción de aguas subterráneas (VEAS)",
                   "Disponibilidad media anual de agua subterránea (DMA)", "Situación Administrativa del Acuífero"],
    
    "SUB_SUBTITULOS": ["Profundidad al nivel estático", "Elevación del nivel estático", "Evolución del nivel estático", "Recarga vertical (Rv)",
                       "Retornos por riego (Rr)", "Recarga incidental (Ri)", "Entradas por flujo subterráneo horizontal (Eh)",
                       "Entradas por flujo subterráneo horizontal de agua salobre (Es)", "Bombeo (B)", "Salidas de agua salobre por bombeo (Ssb)",
                       "Evapotranspiración (ETR)", "Salidas por flujo subterráneo horizontal (Sh)", "Descarga de manantiales (Dm)",
                       "Descarga por flujo base (Dfb)","Recarga inducida (Ri)","Recarga natural (Rn)"]
}

ADN_NORMALIZADO = {}
for lista_titulos in MAPA_ADN.values():
    for t in lista_titulos:
        ADN_NORMALIZADO[t.upper()] = t
ADN_NORMALIZADO["ANTECEDENTES"] = "Antecedentes"

CORRECCIONES_TITULOS = {
    "RECARGA INCIDENTAL (RR)": "Recarga incidental (Ri)",
    "DESCARGA A TRAVÉS DE MANANTIALES (DM)":"Descarga de manantiales (Dm)",
    "DESCARGAS A TRAVÉS DE MANANTIALES (DM)":"Descarga de manantiales (Dm)",
    "DESCARGA POR MANANTIALES (DM)": "Descarga de manantiales (Dm)",
    "RECARGA POR RETORNO DE RIEGO (RR)": "Retornos por riego (Rr)",
    "RECARGA POR RETORNOS DE RIEGO (RR)": "Retornos por riego (Rr)",
    "SALIDAS SUBTERRÁNEAS (SH)": "Salidas por flujo subterráneo horizontal (Sh)",
    "SALIDAS POR FLUJO SUBTERRÁNEO (SH)": "Salidas por flujo subterráneo horizontal (Sh)",
    "CAMBIO DE ALMACENAMIENTO ∆V(S)": "Cambio de almacenamiento ΔV(S)",
    "CAMBIO DE ALMACENAMIENTO DV(S)": "Cambio de almacenamiento ΔV(S)",
    "CAMBIO DE ALMACENAMIENTO (VS)": "Cambio de almacenamiento ΔV(S)",
    "CAMBIO DE ALMACENAMIENTO (ΔVS)": "Cambio de almacenamiento ΔV(S)",
    "EXTRACCIÓN POR BOMBEO (B)":"Bombeo (B)",
    "ENTRADAS SUBTERRÁNEAS HORIZONTALES (EH)":"Entradas por flujo subterráneo horizontal (Eh)",
    "BALANCE DE AGUA SUBTERRÁNEA":"BALANCE DE AGUAS SUBTERRÁNEAS",
    "GEOLOGIA": "GEOLOGÍA",
    "HIDROGEOLOGIA": "HIDROGEOLOGÍA",
    "CENSO DE APROVECHAMIENTOS": "CENSO DE APROVECHAMIENTOS E HIDROMETRÍA",
    "BALANCE DE AGUA SUBTERRANEA": "BALANCE DE AGUAS SUBTERRÁNEAS",
    "DISPONIBILIDAD DE AGUA SUBTERRÁNEA": "DISPONIBILIDAD",
    "DISPONIBILIDAD DE AGUAS SUBTERRÁNEAS": "DISPONIBILIDAD",
    "DISPONIBILIDAD MEDIA ANUAL DE AGUAS SUBTERRÁNEAS (DMA)": "Disponibilidad media anual de agua subterránea (DMA)",
    "DISPONIBILIDAD MEDIA ANUAL DE AGUA SUBTERRANEA (DMA)": "Disponibilidad media anual de agua subterránea (DMA)",
    "TIPO DEL ACUÍFERO": "Tipo de acuífero",
    "PROVINCIAS FISIOGRÁFICAS": "Provincia fisiográfica",
    "RETORNOS DE RIEGO": "Retornos por riego (Rr)",
    "RECARGA INCIDENTAL(RI)": "Recarga incidental (Ri)",
    "DESCARGA POR FLUJO BASE DE RÍOS (DFB)":"Descarga por flujo base (Dfb)",
    "LOCALIZACIÓN DEL ACUÍFERO":"Localización",
}

TEXTOS_REEMPLAZO = {
    "ANTECEDENTES": [
        "La Ley de Aguas Nacionales (LAN) y su Reglamento contemplan que la Comisión Nacional del Agua (CONAGUA) debe publicar en el Diario Oficial de la Federación (DOF), la disponibilidad de las aguas nacionales, en el caso de las aguas subterráneas esto debe ser por acuífero, de acuerdo con los estudios técnicos correspondientes y conforme a las disposiciones que considera la “Norma Oficial Mexicana NOM-011-CONAGUA-2015. Que establece el método para determinar la disponibilidad media anual de las aguas nacionales”, publicada en el DOF el 27 de marzo de 2015.",
        "Esta norma ha sido preparada por un grupo de especialistas de la iniciativa privada, instituciones académicas, asociaciones de profesionales, gobiernos estatales y municipales y de la CONAGUA.",
        "La NOM establece para el cálculo de la disponibilidad de aguas subterráneas la realización de un balance de las mismas donde se defina de manera precisa la recarga, de ésta deducir los volúmenes comprometidos con otros acuíferos, la demanda de los ecosistemas y el volumen concesionado vigente en el Registro Público Nacional del Agua (REPNA). Los resultados técnicos que se publiquen deberán estar respaldados por un documento en el que se sintetice la información, se especifique claramente el balance de aguas subterráneas y la disponibilidad de agua subterránea susceptible de concesionar.",
        "La publicación de la disponibilidad servirá de sustento técnico-legal para la administración de las aguas nacionales del subsuelo."
    ],
    "BOMBEO (B)": [
        "De acuerdo con el REPNA con fecha de corte al 30 de septiembre del 2025, se reportan un total de 53,087 aprovechamientos de agua subterránea, de los cuales 21,826 (41.1%) se destinan al uso agrícola, 18,330 (34.5%) a diferentes usos, 5,535 (10.4%) a uso pecuario, 3,241 (6.1%) a servicios, 2,198 (4.1%) a uso público-urbano, 1,020 (1.9%) a uso industrial, 800 (1.5%) a uso doméstico, 135 (0.3%) a acuacultura, 1 a generación de energía eléctrica y 1 a uso agroindustrial.",
        "El volumen total en conjunto para esa fecha asciende a 5,127.1 hm3/año del cual 1,994.5 hm3/año (38.9%) corresponde a uso agrícola, 1,667.7 hm3/año (32.5%) a usos múltiples , 669.4 hm3/año (13%) a servicios, 651.5 hm3/año (12.7%) a uso público-urbano, 89 hm3/año (1.7%) a uso industrial, 34.3 hm3/año (0.7 %) a uso pecuario, 18.4 hm3/año (0.4%) a acuacultura y 2.4 hm3/año (0.1%) a otros usos como generación de energía eléctrica, doméstico y agroindustrial."
    ],
    "RECARGA VERTICAL (RV)":["Es uno de los términos que mayor incertidumbre implica su cálculo. La recarga vertical incluye las componentes de recarga natural: infiltración de agua de lluvia y de los escurrimientos de agua superficial, así como, en su caso, los excedentes del agua destinada al uso agrícola y de las pérdidas en las redes de distribución de agua potable y alcantarillado.",
                             "Por lo anterior, su valor será despejado de la ecuación general de balance:"],
    
    "VOLUMEN DE EXTRACCIÓN DE AGUAS SUBTERRÁNEAS (VEAS)":["El  volumen de extracción de aguas subterráneas se determina sumando los volúmenes anuales de agua asignados o concesionados por la Comisión mediante títulos inscritos en el REPNA, los volúmenes de agua que se encuentren en proceso de registro y titulación y, en su caso, los volúmenes de agua correspondientes a reservas, reglamentos y programación hídrica, todos ellos referidos a una fecha de corte específica, así como los volúmenes de extracción en  zonas de libre alumbramiento suspendido, estimados con base en los estudios técnicos, que sean efectivamente extraídos, aunque no hayan sido titulados ni registrados.",
    "El volumen anual de extracción, de acuerdo con los valores proporcionados por la Subdirección General de Administración del Agua y la Gerencia de Planificación Hídrica, con fecha de corte 30 de septiembre de 2025, es de 19.116755 hm3/año."],
    
    "ENTRADAS":["De acuerdo con el modelo conceptual de funcionamiento hidrodinámico del acuífero, la recarga total que recibe (R) ocurre por flujo subterráneo horizontal (Eh) y por recarga vertical (Rv)."]
}

VARIABLES_BALANCE = ["Rv:", "Ed:", "Es:", "Ri:", "B:", "Ssb:", "ΔV(S):", "∆V(S):"]

DICCIONARIO_UNIDADES = {
    "m": "m", "mm": "mm", "km": "km",
    "m2": "m²", "m3": "m³", "km2": "km²", "km3": "km³", "km²":"km²",
    "Mm3": "Mm³", "hm3": "hm³", "cm2": "cm²", "cm3": "cm³", "mm/año":"mm/año",
    "hm3anuales": "hm³/año", "hm3 anuales": "hm³/año", "hm3/año": "hm³/año", "hm3/ano": "hm³/año", "hm³/año":"hm³/año", "hm³":"hm³",
    "Mm3anuales": "Mm³/año", "Mm3 anuales": "Mm³/año", "Mm3/año": "Mm³/año", "Mm3/ano": "Mm³/año", "[hm3] anuales": "hm³/año","hm³ anuales":"hm³/año", "[hm³] anuales":"hm³/año",
    "m3anuales": "m³/año", "m3 anuales": "m³/año", "m3/año": "m³/año", "m3/ano": "m³/año",
    "m³  anuales":"m³/año","m3  anuales":"m³/año",
    "m3/s": "m³/s", "m3/d": "m³/d", "m3/h": "m³/h",
    "l/s": "L/s", "L/s": "L/s", "l/m": "L/min", "L/min": "L/min", "l/h": "L/h", "L/h": "L/h",
    "m2/d": "m²/d", "m2/s": "m²/s", "cm2/s": "cm²/s","m²/s":"m²/s", "m³/s":"m³/s",
    "m/d": "m/d", "m/s": "m/s", "cm/s": "cm/s", "m/año": "m/año", "m/ano": "m/año",
    "mg/L": "mg/L", "mg/l": "mg/L", "µg/L": "µg/L", "ug/L": "µg/L", "ug/l": "µg/L",
    "meq/L": "meq/L", "meq/l": "meq/L", 
    "µS/cm": "µS/cm", "uS/cm": "µS/cm",
    "g/cm3": "g/cm³", "kg/m3": "kg/m³",
    "SO4": "SO₄", "NO3": "NO₃", "CO3": "CO₃", "HCO3": "HCO₃", 
    "CaCO3": "CaCO₃", "PO4": "PO₄",
    "m.s.n.m.":"msnm","m/día":"m/día", "hm³/ año":"hm³/año", "V":"∆V","V":"∆V", "hm³ /año":"hm³/año"
}

UNIDADES_LISTA = '|'.join(re.escape(k) for k in sorted(DICCIONARIO_UNIDADES.keys(), key=len, reverse=True))
PATRON_CIENTIFICO = re.compile(r'(?<![a-zA-Z])(?:' + UNIDADES_LISTA + r')(?![a-zA-Z0-9])')