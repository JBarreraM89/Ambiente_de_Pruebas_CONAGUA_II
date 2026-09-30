# -*- coding: utf-8 -*-
"""
Script de Descarga Masiva del Continuo Nacional de Estructuras 1:50,000 del SGM
Conserva el 100% de los campos y atributos oficiales del SGM en el GeoParquet.
"""

import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString
import time
import os
from pathlib import Path

# Configuración de carpetas del proyecto
DIRECTORIO_RAIZ = Path(__file__).resolve().parent.parent if "pages" in str(Path(__file__).resolve()) else Path(__file__).resolve().parent
CARPETA_SALIDA = DIRECTORIO_RAIZ / "data" / "geologia"
CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
RUTA_PARQUET_FINAL = CARPETA_SALIDA / "Estructuras_Nacional_SGM.parquet"

# URL Oficial Exacta del SGM (Capa 5: Estructuras 1:50,000)
URL_SERVICIO_SGM = "https://portal.sgm.gob.mx/arcgis/rest/services/SGM/SUNGeologiaContinuoMineDatosEs/MapServer/5/query"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.sgm.gob.mx/GeoInfoMexGobMx/"
}

def esri_geom_a_shapely(geom_dict):
    """Convierte geometrías nativas de ESRI (paths) a geometrías Shapely."""
    if not geom_dict: return None
    paths = geom_dict.get("paths", [])
    if len(paths) == 1:
        return LineString(paths[0])
    elif len(paths) > 1:
        return MultiLineString([LineString(p) for p in paths if len(p) >= 2])
    return None

def descargar_capa_nacional_sgm():
    print("=" * 75)
    print("🛰️ INICIANDO EXTRACCIÓN DEL CONTINUO NACIONAL DE ESTRUCTURAS 1:50,000 (SGM)")
    print(f"📡 Endpoint oficial: {URL_SERVICIO_SGM}")
    print("=" * 75)

    # 1. Consultar conteo total de registros
    print("1️⃣ Consultando total de estructuras en la base de datos nacional...")
    params_count = {
        "where": "1=1",
        "returnCountOnly": "true",
        "f": "json"
    }

    try:
        r_c = requests.get(URL_SERVICIO_SGM, params=params_count, headers=headers, timeout=25, verify=False)
        total = r_c.json().get("count", 0)
    except Exception as e:
        print(f"Error consultando el total: {e}")
        total = 0

    if total == 0:
        print("❌ No se pudo conectar con el servidor de SGM. Verifica que tengas conexión.")
        return

    print(f"📊 Total de fallas y fracturas registradas en México: {total:,} elementos.")
    print("=" * 75)

    tamano_lote = 1500
    offset = 0
    lotes_gdf = []
    t0 = time.time()

    # 2. Descarga por paginación en lotes de 1,500 solicitando TODOS los campos (outFields="*")
    while offset < total:
        print(f"⏳ Descargando registros {offset:,} a {min(offset + tamano_lote, total):,} de {total:,}...", end="\r")

        params_query = {
            "where": "1=1",
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": tamano_lote,
            "returnGeometry": "true"
        }

        descargado = False
        for intento in range(3):
            try:
                res = requests.get(URL_SERVICIO_SGM, params=params_query, headers=headers, timeout=40, verify=False)
                if res.status_code == 200:
                    try:
                        data = res.json()
                        if "features" in data and len(data["features"]) > 0:
                            gdf_chunk = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")
                            lotes_gdf.append(gdf_chunk)
                            descargado = True
                            break
                        elif "features" in data and "geometry" in data["features"][0]:
                            records = []
                            geoms = []
                            for f in data["features"]:
                                g = esri_geom_a_shapely(f.get("geometry"))
                                if g is not None:
                                    records.append(f.get("attributes", {}))
                                    geoms.append(g)
                            if geoms:
                                gdf_chunk = gpd.GeoDataFrame(records, geometry=geoms, crs="EPSG:4326")
                                lotes_gdf.append(gdf_chunk)
                                descargado = True
                                break
                    except Exception:
                        pass
                time.sleep(1)
            except Exception:
                time.sleep(2)

        if not descargado:
            # Fallback a f=json nativo de ESRI si geojson no responde
            params_query["f"] = "json"
            try:
                res = requests.get(URL_SERVICIO_SGM, params=params_query, headers=headers, timeout=40, verify=False)
                if res.status_code == 200:
                    data = res.json()
                    feats = data.get("features", [])
                    records, geoms = [], []
                    for f in feats:
                        g = esri_geom_a_shapely(f.get("geometry"))
                        if g is not None:
                            records.append(f.get("attributes", {}))
                            geoms.append(g)
                    if geoms:
                        gdf_chunk = gpd.GeoDataFrame(records, geometry=geoms, crs="EPSG:4326")
                        lotes_gdf.append(gdf_chunk)
                        descargado = True
            except Exception:
                pass

        offset += tamano_lote

    # 3. Consolidación y guardado con TODOS los campos
    print("\n" + "=" * 75)
    print("📦 Consolidando y generando GeoParquet con todos sus atributos...")

    if not lotes_gdf:
        print("❌ No se pudieron descargar registros.")
        return

    gdf_nacional = pd.concat(lotes_gdf, ignore_index=True)

    # Identificar columnas estándar para búsquedas rápidas
    cols_u = [c.upper() for c in gdf_nacional.columns]
    c_tipo = next((c for c in gdf_nacional.columns if any(k in c.upper() for k in ["ESTRUCTUR", "TIPO", "CLASE"])), gdf_nacional.columns[0])
    c_nom = next((c for c in gdf_nacional.columns if any(k in c.upper() for k in ["NOMBRE", "NOM", "FALLA"])), c_tipo)

    # 🎯 GUARDAR CON EL 100% DE SUS COLUMNAS ORIGINALES
    gdf_nacional.to_parquet(RUTA_PARQUET_FINAL, compression="snappy")

    peso_mb = os.path.getsize(RUTA_PARQUET_FINAL) / (1024 * 1024)
    tiempo_total = time.time() - t0

    print("🎉 ¡DESCARGA Y COMPILACIÓN NACIONAL CON TODOS LOS CAMPOS EXITOSA!")
    print(f"📁 Archivo guardado: {RUTA_PARQUET_FINAL.resolve()}")
    print(f"📊 Total de fallas registradas: {len(gdf_nacional):,}")
    print(f"📋 Columnas oficiales guardadas: {', '.join(gdf_nacional.columns)}")
    print(f"💾 Peso en disco: {peso_mb:.2f} MB")
    print(f"⏱️ Tiempo total: {tiempo_total:.1f} segundos.")
    print("=" * 75)

if __name__ == "__main__":
    descargar_capa_nacional_sgm()