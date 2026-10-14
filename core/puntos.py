# -*- coding: utf-8 -*-
"""
core/puntos.py
Utilidades compartidas para puntos de referencia / pozos cargados desde CSV.

`detectar_columnas_puntos` reemplaza la detección por subcadenas que usaban las páginas del
Visor y del Modelo Conceptual. Aquel método tenía falsos positivos: 'ID' coincidía con
'PROFUNDIDAD' (el nombre de cada pozo salía igual a su profundidad), 'NE' con 'GENERO' o
'CONEXION', y 'Y'/'X' con cualquier columna que contuviera esas letras.

Ahora se compara por PALABRA COMPLETA (el nombre de la columna se divide en palabras, sin
acentos ni mayúsculas) y por orden de prioridad, y una columna no puede usarse en dos campos.
"""
import re
import unicodedata
from typing import Dict, Iterable, Optional, Set

# Palabras clave por campo, en orden de prioridad.
_CLAVES = {
    "lat": ("LATITUD", "LATITUDE", "LAT", "NORTE", "Y"),
    "lon": ("LONGITUD", "LONGITUDE", "LONG", "LON", "OESTE", "X"),
    "profundidad": ("PROFUNDIDAD", "PROF", "PERFORACION", "PERF", "DEPTH"),
    "nivel_estatico": ("ESTATICO", "NE"),
    "tipo": ("INFRAESTRUCTURA", "INFRA", "TIPO", "CATEGORIA"),
    "color": ("COLOR", "HEX"),
    "nombre": ("NOMBRE", "SITIO", "POZO", "NOM", "ESTACION", "ID"),
}
_ORDEN = ("lat", "lon", "profundidad", "nivel_estatico", "tipo", "color", "nombre")


def _palabras(nombre) -> Set[str]:
    """Palabras de un nombre de columna: sin acentos, en mayúsculas ('Nivel_Estático' -> {NIVEL, ESTATICO})."""
    ascii_ = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode("ascii")
    return {p for p in re.split(r"[^A-Z0-9]+", ascii_.upper()) if p}


def detectar_columnas_puntos(columnas: Iterable) -> Dict[str, Optional[str]]:
    """Identifica las columnas de un CSV de puntos.

    Devuelve {'lat','lon','profundidad','nivel_estatico','tipo','color','nombre'} -> nombre
    original de la columna, o None si no se encontró. Una columna llamada solo 'Nivel' también
    se acepta como nivel estático (pero 'Nivel dinámico' no).
    """
    originales = [str(c) for c in columnas]
    palabras = {c: _palabras(c) for c in originales}
    usadas: Set[str] = set()
    resultado: Dict[str, Optional[str]] = {}
    for campo in _ORDEN:
        elegida = None
        for clave in _CLAVES[campo]:
            elegida = next((c for c in originales if c not in usadas and clave in palabras[c]), None)
            if elegida:
                break
        if not elegida and campo == "nivel_estatico":
            elegida = next((c for c in originales if c not in usadas and palabras[c] == {"NIVEL"}), None)
        resultado[campo] = elegida
        if elegida:
            usadas.add(elegida)
    return resultado
