# -*- coding: utf-8 -*-
"""
Created on Fri Sep 25 11:56:08 2026

@author: dchable
"""

# -*- coding: utf-8 -*-
"""
Convertidor oficial de QGIS Style (.xml / .txt) a Diccionario JSON para el Modelo 3D
"""
import re
import json
from pathlib import Path

# Nombre de tu archivo con los 2 millones de tokens
ARCHIVO_ORIGEN = "estilos_unificados_COMPLETO.txt"  # 👈 Pon aquí el nombre exacto de tu archivo (ej. 123.txt)

diccionario_estilos = {}

print(f"📖 Leyendo {ARCHIVO_ORIGEN}...")

# Expresión regular ultrarrápida que extrae el nombre del símbolo y su color RGB
patron = re.compile(
    r'<symbol[^>]+name="([^"]+)"[\s\S]*?<Option[^>]+name="color"[^>]+value="(\d+),(\d+),(\d+)',
    re.MULTILINE
)

with open(ARCHIVO_ORIGEN, 'r', encoding='utf-8', errors='ignore') as f:
    contenido = f.read()

coincidencias = patron.findall(contenido)

for nombre_simbolo, r, g, b in coincidencias:
    hex_color = f"#{int(r):02X}{int(g):02X}{int(b):02X}"
    nombre_limpio = nombre_simbolo.strip().upper()
    
    # 1. Guardar con el nombre original exacto (ej. "TPLAR-TR" o "TPR")
    diccionario_estilos[nombre_limpio] = hex_color
    
    # 2. Si el símbolo viene compuesto (ej. "1.2.1TplAr-TRArenisca-Toba riolítica")
    # extraemos también la clave SGM aislada y la descripción
    match_compuesto = re.search(r'[\d\.]*([A-Za-z\(\)\-_/]+)(.*)', nombre_limpio)
    if match_compuesto:
        clave_aislada = match_compuesto.group(1).strip()
        descripcion = match_compuesto.group(2).strip()
        
        if clave_aislada:
            diccionario_estilos[clave_aislada] = hex_color
        if descripcion:
            diccionario_estilos[descripcion] = hex_color

# Guardar en la carpeta data/geologia/ de tu proyecto
ruta_salida = Path("estilos_oficiales_sgm.json")
with open(ruta_salida, 'w', encoding='utf-8') as out:
    json.dump(diccionario_estilos, out, indent=2, ensure_ascii=False)

print(f"\n🎉 ¡LISTO! Se extrajeron {len(diccionario_estilos)} reglas de color oficiales del SGM.")
print(f"📁 Archivo generado: {ruta_salida.resolve()}")
print("👉 Mueve 'estilos_oficiales_sgm.json' a tu carpeta: data/geologia/estilos_oficiales_sgm.json")