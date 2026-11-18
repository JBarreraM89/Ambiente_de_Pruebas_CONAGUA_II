# -*- coding: utf-8 -*-
"""
Servicio local de Vector Tiles PMTiles (REPDA, Vulnerabilidad y futuras capas).
Sirve archivos .pmtiles desde static/ o data/ mediante HTTP Range Requests (HTTP 206)
y CORS habilitado para consumo directo por MapLibre GL JS y pmtiles.js.
"""

import os
import posixpath
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

PMTILES_PORT = 8515
DEFAULT_PMTILES_FILENAME = "repda_nacional.pmtiles"
GITHUB_RAW_STATIC_BASE = (
    "https://raw.githubusercontent.com/JBarreraM89/Ambiente_de_Pruebas_CONAGUA_II/main/static/"
)
URL_GITHUB_RAW_DEFAULT = f"{GITHUB_RAW_STATIC_BASE}{DEFAULT_PMTILES_FILENAME}"

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVER_INSTANCE = None
_SERVER_LOCK = threading.Lock()


def _sanear_nombre_pmtiles(nombre_archivo):
    """Devuelve únicamente el nombre base seguro .pmtiles sin rutas ni parámetros."""
    limpio = unquote((nombre_archivo or "").split("?", 1)[0]).strip()
    limpio = posixpath.basename(limpio) or DEFAULT_PMTILES_FILENAME
    if not limpio.lower().endswith(".pmtiles"):
        return DEFAULT_PMTILES_FILENAME
    return limpio


def _resolver_ruta_pmtiles(request_path):
    """Busca estrictamente un archivo .pmtiles válido en static/ y luego en data/."""
    crudo = unquote((request_path or "").split("?", 1)[0]).strip()
    if crudo in ("", "/"):
        nombre = DEFAULT_PMTILES_FILENAME
    else:
        nombre = posixpath.basename(crudo)
        if not nombre.lower().endswith(".pmtiles"):
            return None
    for carpeta in ("static", "data"):
        candidato = os.path.join(_PROJECT_ROOT, carpeta, nombre)
        if os.path.isfile(candidato):
            return candidato
    return None


class PMTilesHandler(BaseHTTPRequestHandler):
    FILE_PATH = os.path.join(_PROJECT_ROOT, "data", DEFAULT_PMTILES_FILENAME)

    def log_message(self, format, *args):
        # Silenciar logs en consola para no interferir con la salida estándar de Streamlit
        pass

    def _enviar_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Length, Accept-Ranges")

    def do_OPTIONS(self):
        self.send_response(200)
        self._enviar_cors()
        self.end_headers()

    def _preparar_respuesta(self):
        ruta = _resolver_ruta_pmtiles(self.path)
        if ruta is None and os.path.isfile(self.FILE_PATH):
            if self.path in ("", "/"):
                ruta = self.FILE_PATH
        if ruta is None:
            self.send_error(404, "Archivo de teselas no encontrado")
            return None

        file_size = os.path.getsize(ruta)
        range_header = self.headers.get("Range")

        start = 0
        end = max(0, file_size - 1)
        status_code = 200

        if range_header and range_header.startswith("bytes=") and file_size > 0:
            try:
                parts = range_header.replace("bytes=", "", 1).split("-", 1)
                if parts[0]:
                    start = int(parts[0])
                    end = int(parts[1]) if parts[1] else file_size - 1
                elif parts[1]:
                    # Sufijo bytes=-N
                    suffix = int(parts[1])
                    start = max(0, file_size - suffix)
                    end = file_size - 1
                start = max(0, min(start, file_size - 1))
                end = max(start, min(end, file_size - 1))
                status_code = 206
            except Exception:
                start = 0
                end = file_size - 1
                status_code = 200

        length = max(0, end - start + 1) if file_size > 0 else 0

        self.send_response(status_code)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=3600")
        self._enviar_cors()
        if status_code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        return ruta, start, length

    def do_HEAD(self):
        self._preparar_respuesta()

    def do_GET(self):
        info = self._preparar_respuesta()
        if info is None:
            return
        ruta, start, length = info
        try:
            with open(ruta, "rb") as f:
                f.seek(start)
                bytes_left = length
                block_size = 64 * 1024
                while bytes_left > 0:
                    chunk = f.read(min(bytes_left, block_size))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    bytes_left -= len(chunk)
        except (ConnectionError, OSError):
            pass


def _is_port_in_use(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def asegurar_servidor_pmtiles(port=PMTILES_PORT):
    """
    Inicia el servidor local de teselas vectoriales en un hilo demonio si no está activo.
    Retorna la URL base del servicio.
    """
    global _SERVER_INSTANCE
    with _SERVER_LOCK:
        if _is_port_in_use(port):
            return f"http://127.0.0.1:{port}"

        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), PMTilesHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True, name="PMTilesServerThread")
            t.start()
            _SERVER_INSTANCE = server
            return f"http://127.0.0.1:{port}"
        except Exception:
            return f"http://127.0.0.1:{port}"


def _leer_config_url(clave):
    try:
        import streamlit as st
        if hasattr(st, "secrets") and clave in st.secrets:
            val = str(st.secrets[clave]).strip()
            if val:
                return val
    except Exception:
        pass
    return os.getenv(clave, "").strip()


def obtener_url_pmtiles(port=PMTILES_PORT, nombre_archivo=DEFAULT_PMTILES_FILENAME):
    """
    Retorna la URL adecuada para consumir un archivo PMTiles específico:
    1. Permite override por st.secrets / env (PMTILES_URL_<ARCHIVO> o PMTILES_URL para REPDA).
    2. En Streamlit Cloud apunta a la URL CDN HTTPS oficial de GitHub Raw / Fastly.
    3. En entorno local inicia el servidor en 127.0.0.1:port con HTTP 206 + CORS.
    """
    nombre_seguro = _sanear_nombre_pmtiles(nombre_archivo)
    clave_especifica = "PMTILES_URL_" + nombre_seguro.replace(".pmtiles", "").upper().replace("-", "_")
    url_esp = _leer_config_url(clave_especifica)
    if url_esp:
        return url_esp

    if nombre_seguro == DEFAULT_PMTILES_FILENAME:
        url_def = _leer_config_url("PMTILES_URL")
        if url_def:
            return url_def

    is_cloud = (
        os.getenv("STREAMLIT_SHARING_MODE") is not None
        or os.getenv("IS_STREAMLIT_CLOUD") == "true"
        or "STREAMLIT_SERVER_BASE_URL_PATH" in os.environ
        or (os.path.exists("/app") and not os.path.exists("C:\\"))
    )
    if is_cloud:
        return f"{GITHUB_RAW_STATIC_BASE}{nombre_seguro}"

    base_srv = asegurar_servidor_pmtiles(port=port)
    return f"{base_srv}/{nombre_seguro}"
