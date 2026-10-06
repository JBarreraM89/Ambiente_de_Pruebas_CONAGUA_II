# -*- coding: utf-8 -*-
"""
utils/formatters.py
Utilidades de formato de texto, fechas y enlaces de Drive.

Cambios respecto a la versión anterior:
- Sin `except:` desnudos (solo se capturan errores concretos).
- `reparar_mojibake` única y reutilizable (cp1252 y latin-1). Las páginas 3 y 7
  pueden importarla en lugar de mantener su propia copia.
- `limpiar_texto` ya no falla con listas ni arreglos.
- `procesar_link_drive` extrae el ID con regex (soporta ?usp=sharing y carpetas).
"""

import re
from typing import Optional

import pandas as pd

_TEXTOS_NULOS = {"", "nan", "none", "<na>", "nat"}
_FECHAS_NULAS = {"", "nan", "none", "s/f", "s/d"}

# Caracteres que delatan texto UTF-8 mal decodificado (Ã©, Ã±, â€“, Â°, Å…)
_MARCAS_MOJIBAKE = ("Ã", "Â", "â", "Å")

_RE_ID_RUTA = re.compile(r"/d/([A-Za-z0-9_-]+)")
_RE_ID_CARPETA = re.compile(r"/folders/([A-Za-z0-9_-]+)")
_RE_ID_QUERY = re.compile(r"[?&]id=([A-Za-z0-9_-]+)")


def _es_nulo(valor) -> bool:
    """True si el valor es None/NaN/NA. Los contenedores (list, dict...) no son nulos."""
    if valor is None:
        return True
    if isinstance(valor, (list, tuple, set, dict)):
        return False
    try:
        return bool(pd.isna(valor))
    except (TypeError, ValueError):  # arreglos u objetos con isna() vectorial
        return False


def reparar_mojibake(texto):
    """Corrige texto UTF-8 que fue leído como cp1252/latin-1 ('QuerÃ©taro' -> 'Querétaro').

    Si el texto no parece mojibake, se devuelve sin cambios. Valores que no son
    cadenas se devuelven tal cual.
    """
    if not isinstance(texto, str) or not texto:
        return texto
    if not any(marca in texto for marca in _MARCAS_MOJIBAKE):
        return texto
    for codec in ("cp1252", "latin-1"):
        try:
            return texto.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return texto


def limpiar_texto(valor) -> Optional[str]:
    """Devuelve el texto limpio o None si el valor está vacío/nulo. Repara mojibake."""
    if _es_nulo(valor):
        return None
    texto = str(valor).strip()
    if texto.lower() in _TEXTOS_NULOS:
        return None
    return reparar_mojibake(texto)


def formatear_fecha(fecha_cruda) -> str:
    """Normaliza una fecha cruda a 'dd/mm/YYYY'. Devuelve 'S/F' si no hay dato."""
    if _es_nulo(fecha_cruda) or str(fecha_cruda).strip().lower() in _FECHAS_NULAS:
        return "S/F"
    try:
        texto = (str(fecha_cruda).replace("[", "").replace("]", "")
                 .replace("'", "").replace('"', "").strip())
        if "T" in texto:
            fecha_limpia = texto.split("T")[0]
        else:
            fecha_limpia = texto.split(" ")[0]

        if fecha_limpia[:4].isdigit() and len(fecha_limpia) >= 8:
            dt = pd.to_datetime(fecha_limpia, errors="coerce")
        else:
            dt = pd.to_datetime(fecha_limpia, errors="coerce", dayfirst=True)

        if pd.notna(dt):
            return dt.strftime("%d/%m/%Y")
        return fecha_limpia.replace("-", "/")
    except (ValueError, TypeError, OverflowError, IndexError):
        return str(fecha_cruda)


def procesar_link_drive(url) -> Optional[str]:
    """Extrae el ID de un enlace de Google Drive (archivo, carpeta o ?id=). None si no hay."""
    if not isinstance(url, str) or not url:
        return None
    for patron in (_RE_ID_RUTA, _RE_ID_CARPETA, _RE_ID_QUERY):
        coincidencia = patron.search(url)
        if coincidencia:
            return coincidencia.group(1)
    return None
