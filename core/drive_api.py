# -*- coding: utf-8 -*-
"""
Created on Wed Aug 12 12:20:06 2026

@author: dchable
"""

import streamlit as st
import datetime
import requests
import json
import time
import io
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==========================================
# CONSTANTES DE DRIVE
# ==========================================
ID_CARPETA_RAIZ = "1We79gU5F_y6OSO_8bGj44I86qD7dKqZp"
URL_APPS_SCRIPT = "https://script.google.com/macros/s/AKfycbyaLNX0Ljwcq53mb5n_mLiyhJhrzu7J5xIl0NeWeFBEdhEUp0-kOlXBjjBWb3GneXpY/exec"

@st.cache_resource(show_spinner=False)
def obtener_servicio_drive():
    """Unifica la conexión y retorna el servicio de Drive."""
    try:
        info_credenciales = dict(st.secrets["textkey"])
        llave = info_credenciales.get("private_key", "").replace("\\n", "\n").replace("\r", "").strip()
        info_credenciales["private_key"] = llave.replace("-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n").replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----").replace("\n\n\n", "\n").replace("\n\n", "\n")
        credenciales = Credentials.from_service_account_info(info_credenciales, scopes=["https://www.googleapis.com/auth/drive"])
        return build("drive", "v3", credentials=credenciales), credenciales
    except Exception as e:
        st.error(f"❌ Error de Autenticación en Google Drive: {e}")
        return None, None

def obtener_id_carpeta_csvs(servicio, clave_ac):
    try:
        query_acuifero = f"mimeType='application/vnd.google-apps.folder' and '{ID_CARPETA_RAIZ}' in parents and name contains '{clave_ac}' and trashed=false"
        res_acuifero = servicio.files().list(q=query_acuifero, fields="files(id, name)", includeItemsFromAllDrives=True, supportsAllDrives=True).execute()
        carpetas_acuifero = res_acuifero.get('files', [])
        if not carpetas_acuifero: return None
        id_carpeta_acuifero = carpetas_acuifero[0]['id']
        query_csvs = f"mimeType='application/vnd.google-apps.folder' and '{id_carpeta_acuifero}' in parents and name='CSVS' and trashed=false"
        res_csvs = servicio.files().list(q=query_csvs, fields="files(id, name)", includeItemsFromAllDrives=True, supportsAllDrives=True).execute()
        carpetas_csvs = res_csvs.get('files', [])
        if not carpetas_csvs: return None
        return carpetas_csvs[0]['id']
    except Exception: return None

def obtener_nombre_archivo_oficial(clave_ac, nombre_ac, anio_corto=None):
    if not anio_corto: anio_corto = str(datetime.datetime.now().year)[-2:]
    nombre_limpio = str(nombre_ac).strip().upper().replace(" ", "_")
    return f"{clave_ac}_{nombre_limpio}_B{anio_corto}.json"

def listar_balances_json(clave_ac, max_reintentos=4):
    servicio, _ = obtener_servicio_drive()
    if not servicio: return []
    for intento in range(max_reintentos):
        try:
            id_carpeta_destino = obtener_id_carpeta_csvs(servicio, clave_ac)
            if not id_carpeta_destino: return []
            query = f"name contains '.json' and '{id_carpeta_destino}' in parents and trashed = false"
            resultados = servicio.files().list(
                q=query, fields="files(id, name)", includeItemsFromAllDrives=True, supportsAllDrives=True, orderBy="createdTime desc"
            ).execute()
            return resultados.get('files', [])
        except Exception:
            time.sleep(1)
    return []

def descargar_balance_json_por_id(file_id):
    servicio, _ = obtener_servicio_drive()
    if not servicio: return None
    try:
        peticion = servicio.files().get_media(fileId=file_id, supportsAllDrives=True)
        archivo_descargado = io.BytesIO()
        descargador = MediaIoBaseDownload(archivo_descargado, peticion)
        hecho = False
        while not hecho: _, hecho = descargador.next_chunk()
        archivo_descargado.seek(0)
        return json.loads(archivo_descargado.read().decode('utf-8'))
    except Exception: return None

def buscar_metadatos_drive(anio):
    """Utilizado por el Reporte Anual para escaneo masivo."""
    query = f"name contains '_B{str(anio)[-2:]}.json' and trashed=false"
    servicio, _ = obtener_servicio_drive()
    if not servicio: return []
    archivos_encontrados = []
    page_token = None
    while True:
        try:
            resultados = servicio.files().list(
                q=query, pageSize=1000, fields="nextPageToken, files(id, name, modifiedTime)", 
                includeItemsFromAllDrives=True, supportsAllDrives=True, pageToken=page_token
            ).execute()
            archivos_encontrados.extend(resultados.get('files', []))
            page_token = resultados.get('nextPageToken', None)
            if not page_token: break
        except Exception: time.sleep(1)
    return archivos_encontrados

def descargar_json_crudo_rapido(file_id, token):
    """Utilizado por el Reporte Anual para descarga concurrente."""
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                return json.loads(res.content.decode('utf-8-sig').strip())
        except Exception: time.sleep(1)
    return None

def guardar_balance_drive(clave_ac, nombre_ac, datos_dict, anio_corto=None):
    servicio, _ = obtener_servicio_drive()
    if not servicio: return False
    id_carpeta_destino = obtener_id_carpeta_csvs(servicio, clave_ac)
    if not id_carpeta_destino: return False
    try:
        nombre_archivo = obtener_nombre_archivo_oficial(clave_ac, nombre_ac, anio_corto)
        payload = {"folderId": id_carpeta_destino, "fileName": nombre_archivo, "content": json.dumps(datos_dict, ensure_ascii=False, indent=4)}
        respuesta = requests.post(URL_APPS_SCRIPT, json=payload)
        if respuesta.status_code == 200 and "exitosamente" in respuesta.text: return True
        else:
            st.error(f"❌ Error en el servidor de Google: {respuesta.text}")
            return False
    except Exception: return False