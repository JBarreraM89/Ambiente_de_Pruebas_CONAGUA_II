# -*- coding: utf-8 -*-
"""
Servicio local de Vector Tiles PMTiles para REPDA Nacional.
Permite servir data/repda_nacional.pmtiles mediante HTTP Range Requests (HTTP 206)
y CORS habilitado para consumo directo por MapLibre GL JS y pmtiles.js.
"""

import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PMTILES_PORT = 8515
_SERVER_INSTANCE = None
_SERVER_LOCK = threading.Lock()

class PMTilesHandler(BaseHTTPRequestHandler):
    FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "repda_nacional.pmtiles")

    def log_message(self, format, *args):
        # Silenciar logs en consola para no interferir con la salida estándar de Streamlit
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Length, Accept-Ranges")
        self.end_headers()

    def do_GET(self):
        if not os.path.exists(self.FILE_PATH):
            self.send_error(404, "Archivo de teselas no encontrado")
            return

        file_size = os.path.getsize(self.FILE_PATH)
        range_header = self.headers.get("Range")

        start = 0
        end = file_size - 1
        status_code = 200

        if range_header and range_header.startswith("bytes="):
            status_code = 206
            try:
                parts = range_header.replace("bytes=", "").split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else file_size - 1
                end = min(end, file_size - 1)
            except Exception:
                start = 0
                end = file_size - 1

        length = max(0, end - start + 1)

        self.send_response(status_code)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Content-Length, Accept-Ranges")
        if status_code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()

        try:
            with open(self.FILE_PATH, "rb") as f:
                f.seek(start)
                # Transmitir en bloques para eficiencia
                bytes_left = length
                block_size = 64 * 1024
                while bytes_left > 0:
                    chunk = f.read(min(bytes_left, block_size))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    bytes_left -= len(chunk)
        except (ConnectionResetError, BrokenPipeError):
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

URL_GITHUB_RAW_DEFAULT = "https://raw.githubusercontent.com/JBarreraM89/Ambiente_de_Pruebas_CONAGUA_II/main/static/repda_nacional.pmtiles"

def obtener_url_pmtiles(port=PMTILES_PORT):
    """
    Retorna la URL adecuada para consumir las teselas PMTiles:
    1. Si existe una variable de entorno o st.secrets 'PMTILES_URL', la usa directamente (ej. CDN / Cloudflare R2 / AWS S3).
    2. Si detecta entorno de Streamlit Cloud (o contenedor Linux de producción), retorna
       la URL CDN HTTPS oficial de GitHub Raw / Fastly con soporte nativo de HTTP 206 y CORS (*).
    3. En entorno local de desarrollo (Windows / localhost), asegura el microservicio local en 127.0.0.1:port
       con soporte estricto de HTTP 206 y CORS, y retorna esa URL.
    """
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "PMTILES_URL" in st.secrets:
            url_cfg = str(st.secrets["PMTILES_URL"]).strip()
            if url_cfg:
                return url_cfg
    except Exception:
        pass

    env_url = os.getenv("PMTILES_URL", "").strip()
    if env_url:
        return env_url

    is_cloud = (
        os.getenv("STREAMLIT_SHARING_MODE") is not None
        or os.getenv("IS_STREAMLIT_CLOUD") == "true"
        or "STREAMLIT_SERVER_BASE_URL_PATH" in os.environ
        or (os.path.exists("/app") and not os.path.exists("C:\\"))
    )
    if is_cloud:
        return URL_GITHUB_RAW_DEFAULT

    base_srv = asegurar_servidor_pmtiles(port=port)
    return f"{base_srv}/repda_nacional.pmtiles"

