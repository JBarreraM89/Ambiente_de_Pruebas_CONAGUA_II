# -*- coding: utf-8 -*-
"""
Created on Wed Apr 22 15:54:14 2026

@author: dchable
"""

# -*- coding: utf-8 -*-
"""
Created on Wed Apr 15 23:59:00 2026
@author: dchable
"""

import os
import re
import traceback
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

# 1. MAPA DE ADN
MAPA_ADN = {
    "TITULOS": ["GENERALIDADES", "ESTUDIOS TÉCNICOS REALIZADOS CON ANTERIORIDAD", "FISIOGRAFÍA", "GEOLOGÍA",
                "HIDROGEOLOGÍA", "CENSO DE APROVECHAMIENTOS E HIDROMETRÍA", "BALANCE DE AGUAS SUBTERRÁNEAS",
                "DISPONIBILIDAD", "BIBLIOGRAFÍA"],
    
    "SUBTITULOS": ["Localización", "Situación administrativa del acuífero", "Provincia fisiográfica", "Clima",
                   "Hidrografía", "Geomorfología", "Estratigrafía", "Geología estructural", "Geología del subsuelo",
                   "Tipo de acuífero", "Parámetros hidráulicos", "Piezometría", "Parámetros hidráulicos", "Piezometría", "Comportamiento hidráulico",
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

# 2. INTERCEPTOR DE TÍTULOS REBELDES
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

# --- TEXTOS OFICIALES PARA INYECCIÓN ---
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

# 3. EL SÚPER-DICCIONARIO HIDROGEOLÓGICO
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

# --- FIX CLAVE 1: Blindaje con re.escape() para que soporte corchetes en el diccionario ---
UNIDADES_LISTA = '|'.join(re.escape(k) for k in sorted(DICCIONARIO_UNIDADES.keys(), key=len, reverse=True))
PATRON_CIENTIFICO = re.compile(r'(?<![a-zA-Z])(?:' + UNIDADES_LISTA + r')(?![a-zA-Z0-9])')

def titulo_espanol_perfecto(texto):
    """Capitaliza estilo título respetando preposiciones y artículos en español."""
    excepciones = ['de', 'del', 'la', 'el', 'los', 'las', 'y', 'en', 'por', 'a', 'con', 'para']
    palabras = texto.lower().split()
    resultado = []
    for i, p in enumerate(palabras):
        # Siempre capitaliza la primera palabra, o si no está en la lista de excepciones
        if i == 0 or p not in excepciones:
            resultado.append(p.capitalize())
        else:
            resultado.append(p)
    return " ".join(resultado)

# --- FUNCIONES DE APOYO LÓGICO ---
def tiene_numero_previo(texto, start_pos):
    for i in range(start_pos - 1, -1, -1):
        char = texto[i]
        if char.isdigit(): return True
        elif char.isspace() or char in "([{": continue
        else: return False
    return False

def normalizar_para_logica(t):
    return re.sub(r'\s+', '', t.replace('Δ', 'D').replace('∆', 'D')).upper()

def es_elemento_de_indice(p):
    texto = p.text.strip()
    estilo = p.style.name.lower() if p.style else ""
    return ("...." in texto or 
            re.search(r'(\t|\s{2,})\s*\d+$', texto) or 
            texto.upper() in ["CONTENIDO", "ÍNDICE"] or
            'toc' in estilo or 
            'índice' in estilo or 
            'indice' in estilo)

def es_formula_manual(texto):
    t_limpio = texto.strip()
    return '=' in t_limpio and any(op in t_limpio for op in ['=', '+', 'Δ', '∆', 'Σ', '/', '*', '>', '<']) and len(t_limpio) < 150

def es_titulo_figura_tabla(texto):
    return re.match(r'^(Figura|Tabla)\s+\d+', texto, re.IGNORECASE) is not None

def clonar_y_procesar_parrafo(nuevo_p, p_orig, limpiar_numeracion=False):
    char_matrix = []
    for run in p_orig.runs:
        b = run.bold is True; i = run.italic is True
        for char in run.text: 
            # --- FIX CLAVE 2: Convertimos los espacios duros invisibles a normales ---
            if char == '\xa0': char = ' '
            char_matrix.append({'char': char, 'b': b, 'i': i})
            
    if not char_matrix: return
    
    if limpiar_numeracion:
        texto_crudo = "".join(c['char'] for c in char_matrix)
        match_num = re.match(r'^(\s*\d+(\.\d+)*\.?\s+)', texto_crudo)
        if match_num: char_matrix = char_matrix[len(match_num.group(1)):]
            
    if not char_matrix: return 
    
    matriz_sin_dobles = []
    for c in char_matrix:
        # Si el caracter actual es un espacio, y el ÚLTIMO caracter que guardamos también es un espacio... lo ignoramos.
        if c['char'] == ' ' and matriz_sin_dobles and matriz_sin_dobles[-1]['char'] == ' ':
            continue
        # Convertimos tabulaciones erróneas en espacios simples (opcional, pero muy recomendado)
        if c['char'] == '\t':
            c['char'] = ' '
            if matriz_sin_dobles and matriz_sin_dobles[-1]['char'] == ' ':
                continue
        matriz_sin_dobles.append(c)
    
    full_text = "".join(c['char'] for c in char_matrix)
    
    for var in VARIABLES_BALANCE:
        if full_text.lstrip().startswith(var):
            for j in range(full_text.find(var) + len(var)): char_matrix[j]['b'] = True
            break
            
    matches = list(PATRON_CIENTIFICO.finditer(full_text))
    for match in reversed(matches):
        start = match.start()
        end = match.end()
        unidad_pura = match.group(0) 
        rodeado_de_corchetes = (start > 0 and end < len(full_text) and 
                               ((full_text[start-1] == '[' and full_text[end] == ']') or 
                                (full_text[start-1] == '(' and full_text[end] == ')')))
        
        if unidad_pura in ["m", "mm", "km"]:
            if not (rodeado_de_corchetes or tiene_numero_previo(full_text, start)): 
                continue
        if rodeado_de_corchetes:
            start -= 1
            end += 1
            
        reemplazo_unicode = DICCIONARIO_UNIDADES.get(unidad_pura)
        if reemplazo_unicode:
            unit_start = match.start()
            base_b, base_i = char_matrix[unit_start]['b'], char_matrix[unit_start]['i']
            char_matrix[start:end] = [{'char': c, 'b': base_b, 'i': base_i} for c in reemplazo_unicode]
            
    current_b, current_i, current_text = char_matrix[0]['b'], char_matrix[0]['i'], []
    for c in char_matrix:
        if c['b'] == current_b and c['i'] == current_i: current_text.append(c['char'])
        else:
            r = nuevo_p.add_run("".join(current_text)); r.font.bold, r.font.italic = current_b, current_i
            current_b, current_i, current_text = c['b'], c['i'], [c['char']]
    if current_text:
        r = nuevo_p.add_run("".join(current_text)); r.font.bold, r.font.italic = current_b, current_i

# --- INYECTORES DE FORMATO ---
def inyectar_texto_versalitas_caratula(parrafo, nuevo_texto, aplicar_title_case=False):
    if not parrafo.runs:
        parrafo.text = nuevo_texto.title() if aplicar_title_case else nuevo_texto
        return
    run_base = parrafo.runs[0]
    negrita, tamano, fuente = run_base.font.bold, run_base.font.size, run_base.font.name
    color_rgb = run_base.font.color.rgb if run_base.font.color and run_base.font.color.rgb else None
    
    parrafo.text = ""
    texto_final = nuevo_texto.title() if aplicar_title_case else nuevo_texto
    nuevo_run = parrafo.add_run(texto_final)
    nuevo_run.font.small_caps = True 
    if negrita is not None: nuevo_run.font.bold = negrita
    if tamano is not None: nuevo_run.font.size = tamano
    if fuente is not None: nuevo_run.font.name = fuente
    if color_rgb is not None: nuevo_run.font.color.rgb = color_rgb

def actualizar_encabezado_quirurgico(header_paragraph, nombre_acuifero_puro, estado_puro):
    """V32: Reemplaza nombre y estado, inserta coma y fuerza cursivas en todo el encabezado."""
    char_matrix = []
    for run in header_paragraph.runs:
        b, i = run.bold is True, True  # <--- CAMBIO: Forzamos cursiva desde la extracción
        size, name = run.font.size, run.font.name
        color = run.font.color.rgb if run.font.color and run.font.color.rgb else None
        for char in run.text:
            char_matrix.append({'char': char, 'b': b, 'i': i, 'size': size, 'name': name, 'color': color})
            
    if not char_matrix: return
    full_text = "".join(c['char'] for c in char_matrix)
    
    # Busca la posición después de "Acuífero "
    match = re.search(r'(acu[íi]fero\s+)', full_text, re.IGNORECASE)
    
    if match:
        start_idx = match.end()
        
        # Construcción del nuevo bloque con la coma solicitada
        texto_a_inyectar = f"{nombre_acuifero_puro}, estado de {estado_puro}"
            
        base_format = char_matrix[start_idx] if start_idx < len(char_matrix) else char_matrix[-1]
        
        new_snippet = []
        for c in texto_a_inyectar:
            new_snippet.append({
                'char': c, 'b': base_format['b'], 'i': True, # <--- Aseguramos cursiva aquí también
                'size': base_format['size'], 'name': base_format['name'], 'color': base_format['color']
            })
            
        char_matrix[start_idx:] = new_snippet
        
        # Reconstrucción
        header_paragraph.text = ""
        current_format = char_matrix[0]
        current_text = []
        
        for c in char_matrix:
            if (c['b'] == current_format['b'] and c['i'] == current_format['i'] and 
                c['size'] == current_format['size'] and c['name'] == current_format['name'] and 
                c['color'] == current_format['color']):
                current_text.append(c['char'])
            else:
                r = header_paragraph.add_run("".join(current_text))
                r.bold, r.italic = current_format['b'], True # <--- Garantía final de cursiva
                r.font.size, r.font.name = current_format['size'], current_format['name']
                if current_format['color']: r.font.color.rgb = current_format['color']
                current_format = c
                current_text = [c['char']]
                
        if current_text:
            r = header_paragraph.add_run("".join(current_text))
            r.bold, r.italic = current_format['b'], True
            r.font.size, r.font.name = current_format['size'], current_format['name']
            if current_format['color']: r.font.color.rgb = current_format['color']

def actualizar_caratula_y_encabezado_v31(doc_mold, doc_crudo):
    titulo_crudo = ""; fecha_cruda = ""
    nombre_acuifero_puro = ""; estado_puro = ""
    titulo_formateado = "" 
    
    # 1. Extracción de información del documento original
    for p in doc_crudo.paragraphs[:15]:
        txt = p.text.strip()
        if "acuífero" in txt.lower() and len(txt) > 20: 
            titulo_crudo = txt
            
            # Extraemos el nombre del acuífero usando nuestra nueva función española
            match_acuifero = re.search(r'acu[íi]fero\s+(.*?(?=\s*\(|,|\s+estado|$))', txt, re.IGNORECASE)
            if match_acuifero: 
                nombre_acuifero_puro = titulo_espanol_perfecto(match_acuifero.group(1).strip())
                
            # Extraemos el estado usando nuestra nueva función española
            match_estado = re.search(r'estado\s+de\s+(.*)', txt, re.IGNORECASE)
            if match_estado: 
                estado_puro = titulo_espanol_perfecto(match_estado.group(1).strip())
            
            # --- INICIO LÓGICA DE CARÁTULA PERFECTA ---
            # 1. Aplanamos todo a minúsculas
            titulo_temp = titulo_crudo.lower()
            
            # 2. INYECCIÓN DE COMA: Si encuentra "(1234) estado", lo cambia a "(1234), estado"
            titulo_temp = re.sub(r'(\(\d+\))\s*estado', r'\1, estado', titulo_temp)
            
            # 3. Capitalizamos SOLO la primera letra de toda la oración
            titulo_temp = titulo_temp.capitalize() 
            
            # 4. Restauramos las mayúsculas de los nombres propios
            if nombre_acuifero_puro:
                titulo_temp = re.sub(re.escape(nombre_acuifero_puro), nombre_acuifero_puro, titulo_temp, flags=re.IGNORECASE)
                
            if estado_puro:
                titulo_temp = re.sub(re.escape(estado_puro), estado_puro, titulo_temp, flags=re.IGNORECASE)
                
            titulo_formateado = titulo_temp
            # --- FIN LÓGICA DE CARÁTULA PERFECTA ---
            
        elif "ciudad de méxico" in txt.lower(): 
            fecha_cruda = txt
            
    # 2. Inyección en la Carátula 
    for p in doc_mold.paragraphs[:15]:
        txt = p.text.strip()
        if "acuífero" in txt.lower() and len(txt) > 20 and titulo_formateado:
            # Apagamos aplicar_title_case para que respete nuestro diseño español
            inyectar_texto_versalitas_caratula(p, titulo_formateado, aplicar_title_case=False)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif "ciudad de méxico" in txt.lower() and fecha_cruda:
            inyectar_texto_versalitas_caratula(p, fecha_cruda, aplicar_title_case=False)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 3. Sustitución Quirúrgica en los Encabezados 
    if nombre_acuifero_puro:
        for section in doc_mold.sections:
            for p in section.header.paragraphs:
                if "acuífero" in p.text.lower():
                    actualizar_encabezado_quirurgico(p, nombre_acuifero_puro, estado_puro)

# --- MOTOR PRINCIPAL ---
def ejecutar_estandarizacion_v31(ruta_plantilla, ruta_origen, ruta_salida):
    doc_mold = Document(ruta_plantilla)
    doc_crudo = Document(ruta_origen)
    
    actualizar_caratula_y_encabezado_v31(doc_mold, doc_crudo)
    
    para_map = {p._element: p for p in doc_crudo.paragraphs}
    items = list(doc_crudo.element.body)
    modo_compacto = False; dentro_del_cuerpo = False

    # Variable de control para omitir párrafos de secciones reemplazadas
    seccion_activa_para_omitir = None

    p_inicio_mold = -1
    for i, p in enumerate(doc_mold.paragraphs):
        if "GENERALIDADES" in p.text.upper() and not es_elemento_de_indice(p):
            p_inicio_mold = i; break
            
    if p_inicio_mold != -1:
        # 1. Borramos el contenido viejo (de Generalidades hacia abajo)
        for i in range(len(doc_mold.paragraphs) - 1, p_inicio_mold - 1, -1):
            p_del = doc_mold.paragraphs[i]._element; p_del.getparent().remove(p_del)
            
        # 2. LA ASPIRADORA: Borramos los [Enters] fantasma residuales (de Generalidades hacia arriba)
        for i in range(p_inicio_mold - 1, -1, -1):
            p_check = doc_mold.paragraphs[i]
            texto_p = p_check.text.strip()
            # Si el párrafo está vacío y no es del índice, lo destruimos
            if not texto_p and "...." not in p_check.text:
                p_del = p_check._element
                p_del.getparent().remove(p_del)
            elif texto_p:
                # En cuanto topamos con texto real (el final del índice de la plantilla), nos detenemos
                break
                
        # 3. Borramos las tablas viejas de la plantilla
        for t in doc_mold.tables:
            t_del = t._element; t_del.getparent().remove(t_del)

    for idx, item in enumerate(items):
        if item.tag.endswith('p'):
            p_orig = para_map.get(item)
            if not p_orig: continue
            texto_completo = p_orig.text.strip()
            
            if "GENERALIDADES" in texto_completo.upper() and not es_elemento_de_indice(p_orig): dentro_del_cuerpo = True
            
            if dentro_del_cuerpo and texto_completo:
                
                # --- NUEVA LIMPIEZA ANTI-ERROR HUMANO ---
                # 1. Quitamos espacios extra y extirpamos puntos, dos puntos o guiones al final del párrafo
                texto_completo = texto_completo.strip()
                
                # 1. PLANCHADO INVISIBLE: Convierte espacios duros (\xa0), tabulaciones y dobles espacios en un espacio normal
                texto_completo = re.sub(r'\s+', ' ', texto_completo)
                
                # 2. HOMOGENEIZACIÓN DEL DELTA: Convierte el símbolo matemático de incremento al Delta griego del ADN
                texto_completo = texto_completo.replace('∆', 'Δ')
                
                # 3. Limpieza de puntuación y números
                texto_completo_eval = re.sub(r'[\.\-\:\s]+$', '', texto_completo)
                texto_limpio = re.sub(r'^([\d]+\s*\.?\s*)+', '', texto_completo_eval).strip()
                texto_upper = texto_limpio.upper()
                
                # --- INICIO DE LA LÓGICA DE INTERCEPCIÓN ACTUALIZADA ---
                estilo_orig = p_orig.style.name.lower() if p_orig.style else ""
                es_estilo_titulo = 'heading' in estilo_orig or 'título' in estilo_orig or 'titulo' in estilo_orig
                
                es_negrita_corta_orig = (0 < len(texto_completo) < 120) and any(r.bold for r in p_orig.runs if r.text.strip())
                es_mayusculas_corto = texto_completo.isupper() and (0 < len(texto_completo) < 120)
                
                # NUEVA REGLA SEGURA: Si el texto es una coincidencia 100% exacta de tu ADN o diccionario,
                # le permitimos pasar el filtro aunque le falte formato de negrita. No afecta a otros textos.
                es_coincidencia_exacta = texto_upper in CORRECCIONES_TITULOS or texto_upper in ADN_NORMALIZADO
                
                texto_oficial = None
                fue_corregido_el_titulo = False
                
                # Mantiene intacto el funcionamiento de tu bloque original
                if es_estilo_titulo or es_negrita_corta_orig or es_mayusculas_corto or es_coincidencia_exacta:
                    texto_oficial = CORRECCIONES_TITULOS.get(texto_upper)
                
                if texto_oficial:
                    texto_limpio = texto_oficial
                    texto_completo_eval = texto_oficial 
                    fue_corregido_el_titulo = True

                txt_norm = normalizar_para_logica(texto_completo_eval)
                if "CAMBIODEALMACENAMIENTO" in txt_norm or "SOLUCIONDELAECUACIONDEBALANCE" in txt_norm: modo_compacto = True
                
                estilo_asignado = 'Normal'
                es_cap_tecnico = es_titulo_figura_tabla(texto_completo_eval)
                es_cabecera = False
                
                # --- VALIDACIÓN CONTRA EL MAPA DE ADN (TOTALMENTE BLINDADA A MAYÚSCULAS/MINÚSCULAS) ---
                if es_cap_tecnico: 
                    estilo_asignado = 'Tablas y Figuras'
                elif es_formula_manual(texto_completo_eval): 
                    estilo_asignado = 'Formulas'
                elif texto_completo_eval.upper() in [t.upper() for t in MAPA_ADN["TITULOS"]] or texto_limpio.upper() in [t.upper() for t in MAPA_ADN["TITULOS"]]: 
                    estilo_asignado = 'Title'; es_cabecera = True
                elif texto_completo_eval.upper() == "ANTECEDENTES" or texto_limpio.upper() == "ANTECEDENTES": 
                    estilo_asignado = 'Antecedentes'; es_cabecera = True
                elif texto_completo_eval.upper() in [t.upper() for t in MAPA_ADN["SUBTITULOS"]] or texto_limpio.upper() in [t.upper() for t in MAPA_ADN["SUBTITULOS"]]: 
                    estilo_asignado = 'Subtitle'; es_cabecera = True
                elif texto_completo_eval.upper() in [t.upper() for t in MAPA_ADN["SUB_SUBTITULOS"]] or texto_limpio.upper() in [t.upper() for t in MAPA_ADN["SUB_SUBTITULOS"]]: 
                    estilo_asignado = 'Sub-subtitulo'; es_cabecera = True
                
                es_negrita_corta = (0 < len(texto_completo) < 100) and (p_orig.runs and p_orig.runs[0].bold)
                es_header_real = es_cabecera or es_negrita_corta
                
                # =========================================================================
                # INICIO DEL SISTEMA DE OMISIÓN PARA TEXTOS REEMPLAZADOS
                # =========================================================================
                texto_header_real = None
                if fue_corregido_el_titulo:
                    texto_header_real = texto_oficial.upper()
                elif es_cabecera:
                    clave_busqueda = texto_limpio.upper() if texto_limpio.upper() in ADN_NORMALIZADO else texto_completo_eval.upper()
                    texto_header_real = clave_busqueda

                if es_header_real:
                    if texto_header_real in TEXTOS_REEMPLAZO:
                        seccion_activa_para_omitir = texto_header_real
                    else:
                        seccion_activa_para_omitir = None
                elif seccion_activa_para_omitir:
                    # Ignorar los párrafos que estaban en el documento viejo bajo esta sección
                    if not es_cap_tecnico and 'w:drawing' not in p_orig._element.xml and 'v:imagedata' not in p_orig._element.xml:
                        continue 
                # =========================================================================

                # SALTO DE PÁGINA PARA BIBLIOGRAFÍA
                if texto_completo.upper() == "BIBLIOGRAFÍA":
                    doc_mold.add_page_break()
                
                nuevo_p = doc_mold.add_paragraph()
                nuevo_p.style = estilo_asignado
                nuevo_p.paragraph_format.widow_control = True
                
                if es_cabecera or es_negrita_corta:
                    nuevo_p.paragraph_format.keep_with_next = True
                
                if fue_corregido_el_titulo:
                    # Inyecta el texto corregido sin numeración (deja que Word numere)
                    nuevo_p.add_run(texto_oficial)
                elif es_cabecera:
                    # CAMBIO CLAVE: Extraemos la versión textualmente perfecta de nuestro ADN
                    # Comparamos en mayúsculas, pero extraemos la versión con formato oficial
                    clave_busqueda = texto_limpio.upper() if texto_limpio.upper() in ADN_NORMALIZADO else texto_completo_eval.upper()
                    titulo_perfecto = ADN_NORMALIZADO.get(clave_busqueda, texto_limpio)
                    
                    nuevo_p.add_run(titulo_perfecto)
                else:
                    # Texto normal
                    clonar_y_procesar_parrafo(nuevo_p, p_orig, limpiar_numeracion=False)
                    
                    # --- INICIO DETECTOR DE PUNTO FINAL PERDIDO ---
                    if estilo_asignado == 'Normal':
                        texto_limpio_final = texto_completo.strip()
                        cierres_validos = ('.', ':', '?', '!', '"', '”', '>', ']')
                        if len(texto_limpio_final) > 80 and not texto_limpio_final.endswith(cierres_validos):
                            nuevo_run_punto = nuevo_p.add_run(".")
                            if nuevo_p.runs and len(nuevo_p.runs) > 1:
                                run_anterior = nuevo_p.runs[-2]
                                nuevo_run_punto.font.size = run_anterior.font.size
                                nuevo_run_punto.font.name = run_anterior.font.name
                            texto_completo = texto_completo + "."
                    # --- FIN DETECTOR DE PUNTO FINAL PERDIDO ---
                
                if 'w:drawing' in p_orig._element.xml or es_cap_tecnico: nuevo_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                
                if es_cap_tecnico: doc_mold.add_paragraph("")
                elif estilo_asignado == 'Formulas':
                    if modo_compacto:
                        proximo_es_formula = False
                        for k in range(idx + 1, len(items)):
                            next_item = items[k]
                            if next_item.tag.endswith('p'):
                                p_next = para_map.get(next_item)
                                if p_next and p_next.text.strip():
                                    if es_formula_manual(p_next.text): proximo_es_formula = True
                                    break
                            elif next_item.tag.endswith('tbl'): break
                        if not proximo_es_formula: doc_mold.add_paragraph("")
                    else: doc_mold.add_paragraph("")
                elif estilo_asignado not in ['Title', 'Subtitle', 'Sub-subtitulo', 'Antecedentes']:
                    if texto_completo.endswith('.') or texto_completo.endswith(':'): doc_mold.add_paragraph("")
                
                if "DV(S)=S*A*H" in txt_norm: modo_compacto = True

                # =========================================================================
                # INYECCIÓN DE PÁRRAFOS OFICIALES DE LA CONAGUA
                # =========================================================================
                if es_header_real and texto_header_real in TEXTOS_REEMPLAZO:
                    for parrafo_nuevo in TEXTOS_REEMPLAZO[texto_header_real]:
                        p_reemplazo = doc_mold.add_paragraph()
                        p_reemplazo.style = 'Normal'
                        p_reemplazo.paragraph_format.widow_control = True
                        
                        # Procesar directamente el texto para arreglar unidades (evita duplicación)
                        texto_procesado = parrafo_nuevo
                        for match in reversed(list(PATRON_CIENTIFICO.finditer(texto_procesado))):
                            unidad_pura = match.group(0)
                            if unidad_pura in DICCIONARIO_UNIDADES:
                                texto_procesado = texto_procesado[:match.start()] + DICCIONARIO_UNIDADES[unidad_pura] + texto_procesado[match.end():]
                                
                        p_reemplazo.add_run(texto_procesado)
                        doc_mold.add_paragraph("")
                # =========================================================================

        elif item.tag.endswith('tbl') and dentro_del_cuerpo:
            t_orig = [t for t in doc_crudo.tables if t._element == item][0]
            nueva_t = doc_mold.add_table(rows=len(t_orig.rows), cols=len(t_orig.columns))
            try: nueva_t.style = 'Tablas y Figuras' 
            except: pass
            for r_idx, row in enumerate(t_orig.rows):
                for c_idx, cell in enumerate(row.cells):
                    nueva_celda = nueva_t.cell(r_idx, c_idx); p_celda = nueva_celda.paragraphs[0]
                    for p_orig_cell in cell.paragraphs:
                        clonar_y_procesar_parrafo(p_celda, p_orig_cell, limpiar_numeracion=False)
            doc_mold.add_paragraph("")

    doc_mold.save(ruta_salida)

def procesar_carpeta_masivamente(ruta_plantilla, carpeta_origen, carpeta_salida):
    print(f"\n{'='*50}\nINICIANDO PROCESAMIENTO MASIVO\n{'='*50}")
    
    # 1. Asegurarnos de que la carpeta de salida exista, si no, la creamos
    if not os.path.exists(carpeta_salida):
        os.makedirs(carpeta_salida)
        print(f"📁 Se creó la carpeta de salida: {carpeta_salida}")

    # 2. Obtener solo los archivos Word (.docx) de la carpeta origen, ignorando archivos temporales de Word (~$)
    archivos_docx = [f for f in os.listdir(carpeta_origen) if f.endswith('.docx') and not f.startswith('~$')]
    
    if not archivos_docx:
        print(f"⚠️ No se encontraron archivos .docx en {carpeta_origen}")
        return

    print(f"Encontrados {len(archivos_docx)} documentos. Comenzando trasplantes...\n")

    exitosos = 0
    fallidos = 0

    # 3. Iterar sobre cada archivo y pasarlo al motor principal
    for nombre_archivo in archivos_docx:
        ruta_origen_completa = os.path.join(carpeta_origen, nombre_archivo)
        
        # Generamos un nuevo nombre para evitar sobreescribir si ya existe
        nombre_sin_extension = os.path.splitext(nombre_archivo)[0]
        nombre_salida = f"{nombre_sin_extension}_ESTANDARIZADO.docx"
        ruta_salida_completa = os.path.join(carpeta_salida, nombre_salida)
        
        try:
            print(f"⏳ Procesando: {nombre_archivo} ...")
            ejecutar_estandarizacion_v31(ruta_plantilla, ruta_origen_completa, ruta_salida_completa)
            exitosos += 1
        except Exception as e:
            # Si un documento falla, el bloque try-except evita que el script colapse
            fallidos += 1
            print(f"❌ ERROR CRÍTICO al procesar '{nombre_archivo}': {str(e)}")
            # Opcional: Imprimir el rastro del error para depurar después
            # traceback.print_exc() 

    # 4. Resumen final
    print(f"\n{'='*50}")
    print(f"PROCESAMIENTO FINALIZADO")
    print(f"✅ Exitosos: {exitosos}")
    print(f"❌ Fallidos: {fallidos}")
    print(f"{'='*50}\n")

# --- PUNTO DE EJECUCIÓN ---
if __name__ == "__main__":
    # Define tus rutas base
    BASE = r"C:\Users\dchable\Desktop\Documentos_Respaldo"
    
    # Rutas dinámicas
    PLANTILLA = os.path.join(BASE, "plantilla", "Ejemplo.docx")
    CARPETA_ENTRADA = os.path.join(BASE, "Documentos_a_modificar") 
    CARPETA_SALIDA = os.path.join(BASE, "Documentos_procesados") # Nueva carpeta donde irán los limpios

    # Ejecutar el director de orquesta
    procesar_carpeta_masivamente(PLANTILLA, CARPETA_ENTRADA, CARPETA_SALIDA)