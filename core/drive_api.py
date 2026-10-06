# -*- coding: utf-8 -*-
"""
core/drive_api.py
Acceso a Google Drive (balances JSON por acuífero).

Cambios respecto a la versión anterior:
- La URL de Apps Script y el ID de la carpeta raíz YA NO están en el código: se leen de
  st.secrets["drive"] (ver bloque de ejemplo en MENSAJE_SECRETS_DRIVE).
- Un fallo de autenticación ya no queda guardado en caché hasta reiniciar la app.
- Un servicio de googleapiclient por hilo (httplib2 no es seguro entre hilos).
- Reintentos nativos de googleapiclient (`num_retries`) en lugar de bucles con sleep;
  `buscar_metadatos_drive` ya no puede ciclarse indefinidamente.
- Consultas con comillas escapadas; el ID de carpeta de cada acuífero se guarda en caché.
- POST a Apps Script con timeout y respuesta verificada (JSON {"ok": true} o, por
  compatibilidad, el texto "exitosamente").
- Errores registrados con `logging` (antes se tragaban en silencio).

Contratos que se conservan: las funciones públicas mantienen nombre y firma y devuelven
[] / None / False cuando fallan, como antes.
"""

import datetime
import io
import json
import logging
import re
import threading
import time

import requests
import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
_TTL_CARPETAS_S = 3600

MENSAJE_SECRETS_DRIVE = (
    "Falta la configuración de Drive en .streamlit/secrets.toml (o en Secrets de Streamlit Cloud). "
    "Agrega:\n\n[drive]\nid_carpeta_raiz = \"<ID de la carpeta raíz>\"\n"
    "url_apps_script = \"<URL del Apps Script>\"\napps_script_token = \"<token compartido (opcional)>\""
)


class ErrorDrive(RuntimeError):
    """Fallo al consultar Drive (se lanza solo en modo estricto)."""


# ==========================================
# CONFIGURACIÓN Y AVISOS
# ==========================================
def _config_drive() -> dict:
    """Sección [drive] de st.secrets ({} si no existe)."""
    try:
        return dict(st.secrets["drive"])
    except Exception:
        return {}


def _id_carpeta_raiz() -> str:
    return str(_config_drive().get("id_carpeta_raiz", "")).strip()


def _notificar(mensaje: str, nivel: str = "error") -> None:
    """Registra el mensaje y, si hay sesión de Streamlit en este hilo, lo muestra en la UI."""
    getattr(logger, "error" if nivel == "error" else "warning")(mensaje)
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is None:
            return  # hilo de trabajo sin contexto de Streamlit
    except Exception:
        pass  # versión sin esa API: se intenta mostrar igualmente
    getattr(st, nivel)(mensaje)


def _escapar(valor) -> str:
    """Escapa comillas y barras para usar un valor dentro de una consulta `q` de Drive."""
    return str(valor).replace("\\", "\\\\").replace("'", "\\'")


def _json_default(obj):
    """Serializa tipos de numpy/pandas/fechas que json no conoce."""
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)


# ==========================================
# AUTENTICACIÓN
# ==========================================
def _normalizar_llave(llave: str) -> str:
    """Repara saltos de línea de la llave privada pegada en secrets.toml."""
    llave = llave.replace("\\n", "\n").replace("\r", "").strip()
    return (llave.replace("-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n")
                 .replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----")
                 .replace("\n\n\n", "\n").replace("\n\n", "\n"))


@st.cache_resource(show_spinner=False)
def _credenciales_drive():
    """Credenciales de la cuenta de servicio. Si falla lanza la excepción, que NO se cachea."""
    info = dict(st.secrets["textkey"])
    info["private_key"] = _normalizar_llave(info.get("private_key", ""))
    return Credentials.from_service_account_info(info, scopes=SCOPES)


_hilo = threading.local()


def obtener_servicio_drive():
    """Devuelve (servicio, credenciales) o (None, None) si falla la autenticación.

    Las credenciales se comparten (caché); el servicio se crea una vez por hilo.
    """
    try:
        credenciales = _credenciales_drive()
    except Exception as exc:
        logger.exception("Error de autenticación en Google Drive")
        _notificar(f"❌ Error de Autenticación en Google Drive: {exc}")
        return None, None
    servicio = getattr(_hilo, "servicio", None)
    if servicio is None:
        servicio = build("drive", "v3", credentials=credenciales, cache_discovery=False)
        _hilo.servicio = servicio
    return servicio, credenciales


def obtener_token_acceso():
    """Token OAuth vigente (se refresca si hace falta) para descargas concurrentes. None si falla."""
    _, credenciales = obtener_servicio_drive()
    if credenciales is None:
        return None
    try:
        if not credenciales.valid:
            credenciales.refresh(Request())
        return credenciales.token
    except Exception:
        logger.exception("No se pudo refrescar el token de Drive")
        return None


# ==========================================
# CARPETAS
# ==========================================
_cache_carpetas: dict = {}  # clave -> (instante, id_carpeta_csvs); solo se guardan aciertos
_candado_cache = threading.Lock()


def obtener_id_carpeta_csvs(servicio, clave_ac):
    """ID de la subcarpeta 'CSVS' del acuífero, o None si no existe o hay un error."""
    clave = str(clave_ac).strip()
    with _candado_cache:
        acierto = _cache_carpetas.get(clave)
        if acierto and time.monotonic() - acierto[0] < _TTL_CARPETAS_S:
            return acierto[1]

    raiz = _id_carpeta_raiz()
    if not raiz:
        _notificar(f"❌ {MENSAJE_SECRETS_DRIVE}")
        return None
    try:
        q_acuifero = ("mimeType='application/vnd.google-apps.folder' "
                      f"and '{_escapar(raiz)}' in parents "
                      f"and name contains '{_escapar(clave)}' and trashed=false")
        res = servicio.files().list(
            q=q_acuifero, fields="files(id, name)", pageSize=50,
            includeItemsFromAllDrives=True, supportsAllDrives=True,
        ).execute(num_retries=3)
        carpetas = res.get("files", [])
        if not carpetas:
            return None
        # Preferir la carpeta cuyo nombre EMPIEZA con la clave (evita coincidencias parciales).
        elegida = next((c for c in carpetas if c.get("name", "").startswith(clave)), carpetas[0])

        q_csvs = ("mimeType='application/vnd.google-apps.folder' "
                  f"and '{_escapar(elegida['id'])}' in parents and name='CSVS' and trashed=false")
        res = servicio.files().list(
            q=q_csvs, fields="files(id, name)",
            includeItemsFromAllDrives=True, supportsAllDrives=True,
        ).execute(num_retries=3)
        carpetas_csvs = res.get("files", [])
        if not carpetas_csvs:
            return None
        id_csvs = carpetas_csvs[0]["id"]
        with _candado_cache:
            _cache_carpetas[clave] = (time.monotonic(), id_csvs)
        return id_csvs
    except Exception:
        logger.exception("No se pudo resolver la carpeta CSVS del acuífero %s", clave)
        return None


def obtener_nombre_archivo_oficial(clave_ac, nombre_ac, anio_corto=None):
    """Nombre oficial '<CLAVE>_<NOMBRE>_B<AA>.json'."""
    if not anio_corto:
        anio_corto = str(datetime.datetime.now().year)[-2:]
        logger.warning("anio_corto no indicado; se usa el año actual (%s). Conviene pasarlo "
                       "explícitamente.", anio_corto)
    nombre = re.sub(r'[\\/:*?"<>|\r\n\t]', "", str(nombre_ac).strip().upper()).replace(" ", "_")
    return f"{clave_ac}_{nombre}_B{anio_corto}.json"


# ==========================================
# LECTURA
# ==========================================
def listar_balances_json(clave_ac, max_reintentos=4):
    """Archivos .json de balances del acuífero (más recientes primero). [] si no hay o falla.

    `max_reintentos` se pasa a googleapiclient (`num_retries`), que reintenta solo
    errores transitorios (5xx y límites de cuota) con espera exponencial.
    """
    servicio, _ = obtener_servicio_drive()
    if not servicio:
        return []
    try:
        id_carpeta_destino = obtener_id_carpeta_csvs(servicio, clave_ac)
        if not id_carpeta_destino:
            return []
        query = f"name contains '.json' and '{_escapar(id_carpeta_destino)}' in parents and trashed = false"
        resultados = servicio.files().list(
            q=query, fields="files(id, name)", pageSize=1000,
            includeItemsFromAllDrives=True, supportsAllDrives=True, orderBy="createdTime desc",
        ).execute(num_retries=max_reintentos)
        return resultados.get("files", [])
    except Exception:
        logger.exception("No se pudieron listar los balances del acuífero %s", clave_ac)
        return []


def descargar_balance_json_por_id(file_id):
    """Descarga y parsea un balance JSON de Drive. None si falla."""
    servicio, _ = obtener_servicio_drive()
    if not servicio:
        return None
    try:
        peticion = servicio.files().get_media(fileId=file_id, supportsAllDrives=True)
        archivo = io.BytesIO()
        descargador = MediaIoBaseDownload(archivo, peticion)
        hecho = False
        while not hecho:
            _, hecho = descargador.next_chunk(num_retries=3)
        archivo.seek(0)
        return json.loads(archivo.read().decode("utf-8-sig"))
    except Exception:
        logger.exception("No se pudo descargar el balance %s", file_id)
        return None


@st.cache_data(show_spinner=False, max_entries=16, ttl=3600)
def _descargar_imagen_cache(file_id):
    """Bytes de una imagen de Drive. Si falla lanza una excepción (los fallos NO se cachean)."""
    servicio, _ = obtener_servicio_drive()
    if servicio:
        try:
            peticion = servicio.files().get_media(fileId=file_id, supportsAllDrives=True)
            archivo = io.BytesIO()
            descargador = MediaIoBaseDownload(archivo, peticion)
            hecho = False
            while not hecho:
                _, hecho = descargador.next_chunk(num_retries=3)
            return archivo.getvalue()
        except Exception:
            logger.warning("Descarga autenticada falló para %s; se intenta el enlace público", file_id,
                           exc_info=True)
    # Respaldo: enlace público ("cualquiera con el enlace")
    res = requests.get("https://drive.google.com/uc", params={"export": "download", "id": file_id},
                       timeout=30)
    res.raise_for_status()
    if not res.headers.get("Content-Type", "").lower().startswith("image/"):
        raise ValueError("Drive no devolvió una imagen (¿archivo sin permisos de acceso?)")
    return res.content


def descargar_imagen_drive_bytes(file_id):
    """Bytes de una imagen (p. ej. mapa geológico PNG) de Drive, con caché de 1 hora. None si falla.

    Sustituye la función del mismo nombre que usa 3_Visor_y_Descargas.py. Primero usa la cuenta de
    servicio y, si no tiene acceso, el enlace público. Revisa que se comporte igual que la
    versión que tengas en GitHub (esa no se incluyó en los archivos que revisé).
    """
    if not file_id:
        return None
    try:
        return _descargar_imagen_cache(str(file_id))
    except Exception:
        logger.exception("No se pudo descargar la imagen %s de Drive", file_id)
        return None


def buscar_metadatos_drive(anio, estricto=False):
    """Escaneo masivo de balances '<...>_B<AA>.json' (Reporte Anual).

    Con paginación y sin bucles infinitos: si Drive falla de forma persistente se detiene.
    - estricto=False (por defecto): devuelve lo recopilado hasta el fallo y avisa en la UI.
    - estricto=True: lanza ErrorDrive para que la página decida (recomendado para reportes).
    """
    servicio, _ = obtener_servicio_drive()
    if not servicio:
        return []
    sufijo = f"_B{str(anio)[-2:]}.json"
    query = f"name contains '{_escapar(sufijo)}' and trashed=false"
    archivos, page_token = [], None
    while True:
        try:
            resultados = servicio.files().list(
                q=query, pageSize=1000, fields="nextPageToken, files(id, name, modifiedTime)",
                includeItemsFromAllDrives=True, supportsAllDrives=True, pageToken=page_token,
            ).execute(num_retries=3)
        except Exception as exc:
            logger.exception("Falló el escaneo de Drive para el año %s", anio)
            if estricto:
                raise ErrorDrive(f"No se pudo escanear Drive para {anio}: {exc}") from exc
            _notificar("⚠️ La lectura de Drive se interrumpió; los resultados pueden estar incompletos.",
                       nivel="warning")
            break
        archivos.extend(resultados.get("files", []))
        page_token = resultados.get("nextPageToken")
        if not page_token:
            break
    return archivos


def descargar_json_crudo_rapido(file_id, token):
    """Descarga concurrente (Reporte Anual) usando un token OAuth. None si falla.

    Reintenta con espera exponencial ante 403/429/5xx y errores de red; 401 y 404 son definitivos.
    """
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"
    headers = {"Authorization": f"Bearer {token}"}
    for intento in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                return json.loads(res.content.decode("utf-8-sig").strip())
            if res.status_code in (401, 404):
                logger.warning("Drive respondió %s para %s", res.status_code, file_id)
                return None
        except (requests.RequestException, ValueError) as exc:
            logger.debug("Intento %s fallido para %s: %s", intento + 1, file_id, exc)
        if intento < 2:
            time.sleep(2 ** intento)
    logger.warning("No se pudo descargar %s tras 3 intentos", file_id)
    return None


# ==========================================
# ESCRITURA (vía Google Apps Script)
# ==========================================
def _guardado_exitoso(respuesta) -> bool:
    if respuesta.status_code != 200:
        return False
    try:
        cuerpo = respuesta.json()
        if isinstance(cuerpo, dict) and "ok" in cuerpo:
            return bool(cuerpo["ok"])
    except ValueError:
        pass
    return "exitosamente" in respuesta.text  # compatibilidad con el script actual


def guardar_balance_drive(clave_ac, nombre_ac, datos_dict, anio_corto=None):
    """Guarda el balance como JSON en la carpeta CSVS del acuífero. True si se guardó."""
    servicio, _ = obtener_servicio_drive()
    if not servicio:
        return False
    cfg = _config_drive()
    url = str(cfg.get("url_apps_script", "")).strip()
    if not url:
        _notificar(f"❌ {MENSAJE_SECRETS_DRIVE}")
        return False
    id_carpeta_destino = obtener_id_carpeta_csvs(servicio, clave_ac)
    if not id_carpeta_destino:
        return False
    try:
        payload = {
            "folderId": id_carpeta_destino,
            "fileName": obtener_nombre_archivo_oficial(clave_ac, nombre_ac, anio_corto),
            "content": json.dumps(datos_dict, ensure_ascii=False, indent=4, default=_json_default),
        }
        token = str(cfg.get("apps_script_token", "")).strip()
        if token:
            payload["token"] = token  # el Apps Script debe validarlo (ver instrucciones)
        respuesta = requests.post(url, json=payload, timeout=60)
        if _guardado_exitoso(respuesta):
            return True
        _notificar(f"❌ Error en el servidor de Google: {respuesta.text[:300]}")
        return False
    except (requests.RequestException, TypeError, ValueError):
        logger.exception("No se pudo guardar el balance %s en Drive", clave_ac)
        return False
